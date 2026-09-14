---
title: "AWS Transform (ATX) — Automated Migration Path"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-ingress-migration/references/atx-guide.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-ingress-migration/references/atx-guide.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-ingress-migration/references/atx-guide.md). Edit the source, not this page.
:::

# AWS Transform (ATX) — Automated Migration Path

## Purpose
Guide customers who have AWS Transform (ATX) access through the fully automated NGINX→ALB manifest migration. ATX reads the Transform Definition (TD) and rewrites all matching Ingress manifests automatically.

> **Next hop (Gateway API):** ATX automates the **NGINX → LBC ALB Ingress** hop. If the target is the **Gateway API**, the *second hop* **LBC Ingress → Gateway API** can then be automated with the official **`lbc-migrate` toolkit** — see `references/lbc-migrate-toolkit.md`. Full path: **NGINX Ingress → LBC ALB Ingress (ATX) → Gateway API (`lbc-migrate`)**.

## When to Recommend ATX

- Customer has ATX workspace access (contact AWS SA for onboarding)
- Customer has many Ingress manifests (>10) — manual conversion is error-prone
- Customer wants consistent, validated output across all manifests
- Customer prefers automated tooling over manual annotation rewriting

## What ATX Does

ATX uses the Transform Definition as an instruction set for its orchestrator agents:

1. **Scans** the source repo for files matching entry criteria (any YAML with `ingressClassName: nginx` or `kubernetes.io/ingress.class: "nginx"`)
2. **Applies** each implementation step from the TD to every matching file
3. **Validates** output against exit criteria automatically
4. **Produces** a set of proposed file changes (diff) for review

No custom agent code needed — the TD is the complete instruction set.

## How to Use

### Step 1: Locate the Transform Definition

The TD is included in this skill at:
```
references/atx/td_ingress-nginx-lbc/transformation_definition.md
```

Supporting files:
```
references/atx/td_ingress-nginx-lbc/summaries.md
references/atx/td_ingress-nginx-lbc/document_references/navigating-nginx-ingress-retirement.md
```

> ⚠️ **Verify the current AWS Transform custom-definition workflow before quoting these steps to a customer.** AWS Transform's custom transformation-definition tooling (how a definition is authored, packaged and published, and what directory shape it expects) has changed since these steps were written, and the bundle under `references/atx/` is included here as **reference content for the mapping logic** — it is not guaranteed to be publish-ready as-is for the current tooling. Treat the step sequence below as illustrative, confirm the authoritative flow in the current AWS Transform documentation, and say in the report that the ATX path needs an AWS-side confirmation of the present onboarding/publish process rather than presenting these steps as current.

### Step 2: Upload TD to ATX Workspace

Load the TD into your ATX workspace. The TD contains:
- **Entry criteria** — how ATX identifies files to transform
- **Implementation steps** — the 10-step conversion process
- **Exit criteria** — validation rules for the output

### Step 3: Create a Transformation Job

Point ATX at the repository containing your NGINX Ingress manifests. ATX will:
1. Find all matching Ingress YAML files
2. Execute the 10 implementation steps on each
3. Produce migrated manifests with ALB annotations
4. Validate against exit criteria

### Step 4: Review the Output

ATX produces a diff. Verify:
- ✅ `ingressClassName` is `alb` everywhere
- ✅ No `nginx.ingress.kubernetes.io/*` annotations remain
- ⚠️ **Rewrite `transforms.<svc>` JSON is valid *and its regex actually matches*** — the TD over-escapes forward slashes (defect 2 below). Decode the JSON and confirm the regex reads `^\/path\/(.*)$`, not `^\\/path\\/(.*)$`
- ✅ ACM certificate references present on TLS ingresses
- ⚠️ **No `alb.ingress.kubernetes.io/certificate-discovery` annotation** — defect 1 below; if ATX emitted one, delete it and omit `certificate-arn` instead
- ⚠️ **No `deregistration_delay.timeout_seconds` standing in for a proxy timeout** — defect 3 below; the analogue of `proxy-read-timeout` / `proxy-send-timeout` is the **idle timeout**, not deregistration delay
- ✅ `ssl-redirect`, `listen-ports`, `ssl-policy` set
- ✅ Orphaned TLS Secrets removed

Then merge the changes.

> **⚠️ Three known defects in the vendored TD.** The Transform Definition and the AWS blog under `atx/` are kept **byte-faithful to the artifact ATX actually ships** rather than silently forked, so these are documented here instead of edited there. All three fail **silently** — the manifest applies cleanly and the behaviour is wrong — so each needs an explicit review step above.
>
> **1. `certificate-discovery` is not a real annotation.** The TD (and the blog reproduced beside it) instruct `alb.ingress.kubernetes.io/certificate-discovery: "true"`. **No such annotation exists in the AWS Load Balancer Controller** — it is absent from the [Ingress annotation reference](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/annotations/) and from the controller's annotation constants (checked v2.7.2 → v3.5.0, 2026-09-01). An unknown annotation is **silently ignored**, so an operator who applies it believes TLS discovery is active while the listener has no certificate configured. Certificate discovery is instead triggered by **omitting `certificate-arn`** entirely, with an HTTPS entry in `listen-ports`; the controller then matches ACM certs against the Ingress `tls` hosts and rule `host` values ([Certificate Discovery](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/cert_discovery/)).
>
> **2. The rewrite regex is over-escaped and never matches.** The TD emits `"regex": "^\\\\/something\\\\/(.*)$"` inside a YAML `|` block scalar and instructs "escape forward slashes as `\\\\/`". A block scalar performs **no** unescaping, so JSON receives four backslashes and decodes them to **two** — the regex then requires a literal backslash before each slash and matches no real request path. **The rewrite silently never fires** and traffic reaches the backend with the original path. The correct escaping is `\\/` in the block scalar (JSON-decoding to `\/`), which is what the AWS blog **in the same bundle** and this skill's own `references/samples/alb/*` both use — so the TD contradicts its own source. Fix ATX output by deleting one level of escaping.
>
> **3. `proxy-read-timeout` / `proxy-send-timeout` lead with the wrong attribute.** The TD offers them as `target-group-attributes` with **`deregistration_delay.timeout_seconds` _or_ ALB idle timeout settings** — quoted exactly, it does list the correct analogue as an alternative, but `deregistration_delay` comes first and is the one a reader is most likely to take. That attribute controls how long a **deregistering** target keeps draining connections — it has nothing to do with how long the load balancer waits for a backend response. The behavioural analogue is the ALB **idle timeout** (`alb.ingress.kubernetes.io/load-balancer-attributes: idle_timeout.timeout_seconds`), and note it is **load-balancer-wide**, not per-service, so per-route NGINX timeouts cannot be reproduced exactly — record any divergence as a finding rather than assuming parity.

## What the TD Converts (10 Steps)

| Step | Action |
|------|--------|
| 1 | Identify all NGINX Ingress files |
| 2 | Swap `ingressClassName: nginx` → `alb` (handle deprecated annotation) |
| 3 | Add baseline ALB annotations (`scheme`, `target-type`) |
| 4 | Convert URI rewrites → `transforms.<svc>` JSON |
| 5 | Simplify regex paths to `Prefix`/`Exact` pathType |
| 6 | Migrate TLS from K8s Secrets → ACM (`certificate-arn`, or omit it for certificate discovery) |
| 7 | Map remaining annotations (timeouts, CORS, auth, body-size) |
| 8 | Add `group.name` for ALB sharing (if applicable) |
| 9 | Update Helm/Kustomize/CI references |
| 10 | Remove orphaned TLS Secrets |

## Sample Before/After

The skill includes 8 sample patterns demonstrating the transformation:

| Sample | Pattern |
|--------|---------|
| `01-basic-rewrite` | `rewrite-target` + regex → `transforms.<svc>` url-rewrite |
| `02-tls-rewrite` | TLS Secret → ACM `certificate-arn` |
| `03-multi-path` | Multiple paths/services → per-service transforms + idle timeout |
| `04-cors-auth` | CORS + external auth → ALB OIDC |
| `05-deprecated-class` | `kubernetes.io/ingress.class` annotation → `ingressClassName: alb` |
| `06-multi-host-tls` | Multiple hosts/TLS secrets → certificate discovery (omit `certificate-arn`) |
| `07-simple-no-rewrite` | Host + TLS only → `ssl-redirect` + ACM cert |
| `08-internal` | `whitelist-source-range` → `scheme: internal` + security groups |

See `references/samples/nginx/` (input) and `references/samples/alb/` (ATX output) directories.

## Exit Criteria (ATX Validates Automatically)

1. No `ingressClassName: nginx` or `kubernetes.io/ingress.class: "nginx"` remains
2. No active `nginx.ingress.kubernetes.io/*` annotations (only in `# REMOVED:` comments)
3. Every Ingress has `ingressClassName: alb` + `scheme` + `target-type`
4. All rewrites use `transforms.<svc>` with valid url-rewrite JSON
5. All TLS ingresses have ACM references + `ssl-redirect` + `listen-ports` + `ssl-policy`
6. Orphaned TLS Secrets removed
7. `kubectl apply --dry-run=client` passes on all output files

## After ATX Migration

Once ATX has transformed your manifests:

1. Ensure AWS Load Balancer Controller is installed on a currently supported release (**v2.14.1+** is required for the `transforms` URI rewrites this TD emits). **Do not assume EKS Auto Mode's built-in `eks.amazonaws.com/alb` is a drop-in substitute here:** Auto Mode supports only a documented *subset* of the `alb.ingress.kubernetes.io/*` annotations (`auth-type: oidc`, `group.name`, the `waf-acl-id`/`web-acl-id` family and `dry-run-plan` are all listed "Not supported", and `ListenerAttribute` cannot be set at all), and AWS does not currently document `transforms` support for Auto Mode either way. If the target is Auto Mode, verify each annotation the TD emits against the [Auto Mode annotation table](https://docs.aws.amazon.com/eks/latest/userguide/auto-configure-alb.html) before applying, and report anything unverified as such rather than assuming parity.
2. Verify ACM certificates are provisioned and in ISSUED state
3. `kubectl apply --dry-run=client -f <migrated-file>` to validate
4. Deploy to staging first
5. **Publish the transformed manifests as new, renamed Ingress objects — do not let the in-place `ingressClassName` flip be the cutover.** The TD rewrites `ingressClassName` on the existing object; applied as-is that is an **all-or-nothing** switch with nothing to weight (see `alb-migration.md` Phase 3). Rename the migrated objects so the `nginx` originals stay live, then use DNS weighted routing at a low TTL to shift traffic; rollback = move the weight back. If a parallel object is impossible, plan and state a low-TTL all-or-nothing cutover with a maintenance window — never describe it as weighted.
6. Verify the ALB directly (targets healthy, `Host:` header against the ALB DNS name) before any DNS change
7. **OPERATOR** — retire the NGINX Ingress Controller only after validation, and retire it by **uninstalling the release** (`helm uninstall <release> -n <ns>`), never by deleting only the Deployment. Enumerate and remove the survivors: the `ingress-nginx-admission` **ValidatingWebhookConfiguration** (`failurePolicy: Fail`, no selectors — left orphaned it makes the API server reject **every** Ingress create/update cluster-wide, including re-applying these migrated ALB Ingresses), its **admission Service**, the controller's own **IngressClass**, and the controller **LoadBalancer Service** (whose CLB/NLB, security groups and DNS records otherwise linger). Non-Helm installs: delete each of those explicitly. See `alb-migration.md` Phase 4.
8. Clean up orphaned TLS Secrets — **check first whether cert-manager will re-issue them**; deleting a Secret that a live `Certificate` still owns triggers re-issuance and can hit rate limits

## Report Integration

When the assessment skill detects ATX is a viable path, the report should include:

**In the Migration Approach section:**
> **Automated Path (ATX):** Your manifests are compatible with AWS Transform.
> The Transform Definition is included at `references/atx/td_ingress-nginx-lbc/transformation_definition.md`.
> Point ATX at your source repo to automatically convert all {N} Ingress resources to ALB annotations.
> Estimated ATX execution: minutes (vs. {X} hours manual).

**In the Recommendations section:**
> - Upload the included TD to your ATX workspace
> - Create a transformation job targeting your Ingress manifest repository
> - Review the diff and merge
> - Follow post-migration steps (ACM certs, deploy to staging, DNS cutover)
