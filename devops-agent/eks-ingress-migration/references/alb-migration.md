# ALB Controller Migration Path

> **Rating model:** Express every finding as **Impact 0–5** using the *Impact Indicator* rubric, weighing three dimensions **in priority order: (1) business logic / revenue — the live traffic at stake · (2) security / reputation · (3) effort to remediate**. **Effort is NOT a severity driver** — a fix being easy or hard never moves the score (it depends on who implements it). **Presence is decided by estate state** — absent controller / empty estate / orphaned dead config = **non-event (0)**; a broken controller is **tech debt (1)** with zero bound routes or a **suspected active outage** (flagged outside the score) with bound routes; a running controller with a **control-plane CVE counts even at zero routes**. See `ingress-discovery.md` for the full presence/stacking rules. Band mapping is a starting point — 🟢 0 / 🟡 1–2 / 🟠 3–4 / 🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (Kubernetes API `get`/`list`, AWS `Describe`/`List`).


## Purpose
Guide migration from NGINX Ingress Controller to AWS Load Balancer Controller (ALB Ingress), converting all NGINX-specific annotations to their ALB equivalents.

> **This is the first hop of the complete path.** After NGINX → **LBC ALB Ingress** (this file), the *second hop* **LBC Ingress → Gateway API** can be automated with the official **`lbc-migrate` toolkit** — see `references/lbc-migrate-toolkit.md`. Full path: NGINX Ingress → LBC ALB Ingress → Gateway API.

## When to Recommend This Path

- Customer wants to stay on Ingress API (not ready for Gateway API)
- Customer needs ALB features (WAF, Cognito/OIDC, Shield)
- Customer has AWS Transform (ATX) access → fully automated migration
- Customer is on Classic Load Balancer via NGINX and wants ALB

## Annotation Mapping: NGINX → ALB

### Core Changes (Every Ingress)

| Step | Before (NGINX) | After (ALB) |
|------|----------------|-------------|
| IngressClass | `ingressClassName: nginx` | `ingressClassName: alb` |
| Deprecated class | `kubernetes.io/ingress.class: "nginx"` annotation | Remove annotation, add `spec.ingressClassName: alb` |
| Scheme | (implicit: CLB) | `alb.ingress.kubernetes.io/scheme: internet-facing` or `internal` |
| Target type | (implicit: NodePort) | `alb.ingress.kubernetes.io/target-type: ip` |

### URI Rewrite

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `nginx.ingress.kubernetes.io/use-regex: "true"` | Remove |
| `nginx.ingress.kubernetes.io/rewrite-target: /$2` | `alb.ingress.kubernetes.io/transforms.<svc>` with url-rewrite JSON |
| `path: /something(/\|$)(.*)` + `pathType: ImplementationSpecific` | `path: /something` + `pathType: Prefix` |

**Transforms JSON format:**
```yaml
alb.ingress.kubernetes.io/transforms.<service-name>: |
  [
    {
      "type": "url-rewrite",
      "urlRewriteConfig": {
        "rewrites": [
          {
            "regex": "^\\/something(\\/|$)(.*)$",
            "replace": "/$2"
          }
        ]
      }
    }
  ]
```

**Rules:**
- **Requires LBC ≥ v2.14.1** — the `transforms.<svc>` annotation was introduced in [v2.14.1](https://github.com/kubernetes-sigs/aws-load-balancer-controller/releases/tag/v2.14.1) (2025-10-17). It is absent from v2.14.0 and from every v2.13.x line. Below the floor it is an unknown annotation and is **silently ignored — no rewrite happens** and traffic reaches the backend with the original path. This is the one hard controller floor on the ALB Ingress path. Do not confuse this Ingress annotation with the Gateway API `HTTPRoute` `URLRewrite` filter, a separate feature that landed in v2.15.0.
- `<service-name>` must match the backend service name in `spec.rules`
- Forward slashes in regex must be escaped as `\\/` in JSON — **exactly one** level. Over-escaping to `\\\\/` makes the pattern require a literal backslash, so it matches nothing and the rewrite silently never fires (the vendored ATX TD has this bug — see `atx-guide.md`).
- **Keep the separator group — do not "simplify" it away.** Mirror NGINX's `(/|$)` and keep the payload in `$2`. The three forms compared below:

  ```
  NGINX source          path: /something(/|$)(.*)      rewrite-target: /$2
  ALB, correct          regex: ^\/something(\/|$)(.*)$   replace: /$2     <- use this
  ALB, over-simplified  regex: ^\/something\/(.*)$       replace: /$1     <- silently wrong
  ```

  | Request | NGINX | ALB correct | ALB over-simplified |
  |---|---|---|---|
  | `/something` | `/` | `/` ✅ | **no match → forwarded as `/something`** ❌ |
  | `/something/foo` | `/foo` | `/foo` ✅ | `/foo` ✅ |
  | `/somethingelse` | no match | no match ✅ | no match ✅ |

  The over-simplified form is the tempting one and it is **wrong for the bare prefix**: ALB sends the original request to the target when no pattern matches, so `/something` silently reaches the backend un-rewritten while `/something/foo` works. That asymmetry is easy to miss in testing. The correct form is exactly NGINX-equivalent on every input, and needs only plain alternation plus capturing groups — ALB's rewrite engine excludes lookarounds, backreferences, atomic groups, possessive quantifiers, subroutines, recursion and Unicode character classes, none of which this uses. ([Transforms for listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/rule-transforms.html))
- Multi-path Ingress needs separate `transforms.<svc>` per backend service

### TLS / Certificates

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `spec.tls[].secretName: my-secret` | Remove `spec.tls` section entirely |
| K8s Secret with cert/key | `alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:...` |
| Multiple TLS secrets | Comma-separated ARNs, or **omit `certificate-arn`** to let the controller discover ACM certs from the Ingress `tls` hosts / rule `host` values |
| `nginx...ssl-redirect: "true"` | `alb.ingress.kubernetes.io/ssl-redirect: "443"` |
| (none) | `alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'` |
| (none) | `alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS13-1-2-2021-06` |

**Post-migration:** Remove orphaned K8s TLS Secrets that are no longer referenced.

> **Edge termination ≠ done — address the ALB→pod hop (Zero-Trust / compliance).** Moving TLS to ACM edge termination on the ALB and then sending **plaintext HTTP to pods** may **violate organizational/Zero-Trust requirements**, especially on EKS Auto Mode where in-cluster traffic is expected to be encrypted. When recommending edge termination, you MUST state how the ALB→backend hop is protected: e.g. `alb.ingress.kubernetes.io/backend-protocol: HTTPS` to pods, a `TargetGroupBinding` with HTTPS health/traffic, or a **service mesh (mTLS)**. Never present "terminate at ALB, plaintext to pods" as the finished state without calling out the in-cluster encryption decision.

### Proxy Timeouts

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `nginx...proxy-read-timeout: "120"` | `alb.ingress.kubernetes.io/load-balancer-attributes: idle_timeout.timeout_seconds=120` |
| `nginx...proxy-send-timeout: "120"` | (same — ALB uses single idle timeout) |

### CORS

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `nginx...enable-cors: "true"` | Remove — handle via AWS WAF or application-level |
| `nginx...cors-allow-origin` | Remove — handle via AWS WAF or application-level |
| `nginx...cors-allow-methods` | Remove — handle via AWS WAF or application-level |
| `nginx...cors-allow-headers` | Remove — handle via AWS WAF or application-level |

**Note:** Add comment in manifest: `# REMOVED: CORS — configure via AWS WAF rules or application middleware`

> **Fidelity gap (not a simple annotation swap):** CORS has **no *faithful* ALB/WAF equivalent for the dynamic case**. ALB *can* inject **static** CORS response headers via listener-rule **response-header** actions (added Nov 2024), which covers a fixed `Access-Control-Allow-Origin`; but **dynamic origin reflection** (echoing the request `Origin` against an allowlist) and **preflight `OPTIONS` short-circuiting** have no native ALB/WAF equivalent and still need the **application backend** (or a Lambda/edge layer). AWS WAF cannot inject CORS response headers at all. NGINX `rate-limit`/`limit-rps` is per-second, per-path/per-client; **AWS WAF rate-based rules** are coarser — they **default to per-IP aggregation** (custom aggregation keys are available) over a configurable **evaluation window (60–600s)**, **cost extra**, and use a completely different config model. Rate these by the **Impact Indicator** and the Feature-Gap classification in `report-generation.md` — by the live traffic/security the lost fidelity affects, **not** by remediation effort (the app/WAF rework is an operator note, never a severity input). Because they lack a faithful equivalent they are **not** trivial swaps, but the band comes from the rubric, not from how much work the change is.

### Authentication

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `nginx...auth-url` + `nginx...auth-signin` | `alb.ingress.kubernetes.io/auth-type: oidc` |
| (external auth service) | `alb.ingress.kubernetes.io/auth-idp-oidc: '{"issuer":"...","authorizationEndpoint":"...","tokenEndpoint":"...","userInfoEndpoint":"...","secretName":"..."}'` |

> **⚠️ Behavior change — NOT a like-for-like conversion.** Basic Auth (`auth-type: basic`, an `Authorization: Basic` header — commonly used by **scripts, cron jobs and machine/API clients**) → ALB **OIDC/Cognito** replaces header auth with an **interactive browser login redirect** to an Identity Provider. Every **non-interactive** caller (automation, CI, partner APIs) **breaks immediately**. This requires client re-architecture (e.g. OIDC client-credentials flow, app-level token auth, or mTLS) and stakeholder coordination — never present `auth-*` → OIDC as a simple annotation swap. **Score it via `report-generation.md` §1.3 as Tier-B** — the faithful workaround is **app-level credential validation** — **escalating to Tier-A (up to 5) only when non-interactive clients are present *and* the backend is a closed/unmodifiable third-party app**, so the credential check cannot be moved into it. Always call out the affected client types.

### Body Size

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `nginx...proxy-body-size: "50m"` | Remove — no ALB annotation equivalent |

**Note:** Add comment: `# REMOVED: proxy-body-size — configure at application level`

### Access Control / Internal

| Before (NGINX) | After (ALB) |
|----------------|-------------|
| `nginx...whitelist-source-range: "10.0.0.0/8"` | `alb.ingress.kubernetes.io/scheme: internal` |
| (IP restriction) | Use ALB security groups for IP-based access control |

> **Verify before switching internet-facing → internal (High-risk if skipped):**
> 1. **Subnet readiness (read-only):** an internal ALB needs private subnets tagged `kubernetes.io/role/internal-elb` in ≥2 AZs. Check `aws ec2 describe-subnets` for the cluster VPC; if absent, the internal ALB **will fail to provision**. Internet-facing ALBs likewise need `kubernetes.io/role/elb` tags.
> 2. **External-consumer impact:** `whitelist-source-range` on an internet-facing endpoint still served **external** callers (partners, devices, off-cluster clients). Switching to `scheme: internal` makes it reachable **only from inside the VPC** — every external consumer is cut off. Confirm no off-VPC client depends on it, or keep it internet-facing and restrict via `alb.ingress.kubernetes.io/inbound-cidrs` / security groups instead. Do not silently convert a public allowlisted endpoint to internal.

### ALB Grouping (Cost Optimization)

To share a single ALB across multiple Ingress resources:
```yaml
alb.ingress.kubernetes.io/group.name: shared-alb
alb.ingress.kubernetes.io/group.order: "10"
```

> **Blast radius — do NOT default to one shared ALB/Gateway across all teams.** Consolidating `team-api`, `team-payments`, `team-web` onto a single shared ALB (or a single Gateway) maximizes blast radius: one team's broken route, bad annotation, or traffic overload degrades **everyone**. Split by **security boundary**, e.g. a `public` group/Gateway for general web and a separate **`private`/payments** group/Gateway for sensitive systems — accept the extra LB cost for isolation. Recommend grouping by trust/security boundary, not "one group to save money." This applies equally to Gateway API: prefer per-boundary `Gateway`s over a single shared listener.

## Migration Phases (ALB Path)

### Phase 1: Prerequisites
1. Install AWS Load Balancer Controller. There is no separately documented minimum for the plain ALB Ingress path — the controller has reconciled Ingress since its 2.x line, so use a **currently supported release** (pin the **v3.5.0** line unless a constraint prevents it) rather than a floor. The floors that *are* documented and do bite are feature-specific: **v2.14.1+** if any route needs a `transforms` URI rewrite (see Rewrites above), **v3.0.0+** for Gateway API.
2. Provision ACM certificates for all TLS hosts
3. Ensure IAM roles/policies for LB Controller

### Phase 2: Convert Manifests
1. Apply annotation mapping (above) to each Ingress
2. Use ATX for automated conversion (if available) — see `references/atx-guide.md`
3. Validate with `kubectl apply --dry-run=client -f <file>`

### Phase 3: Deploy & Shift Traffic

> ⚠️ **Do not flip `ingressClassName` in place on the live Ingress.** The moment the class changes from `nginx` to `alb`, the NGINX controller stops serving that object and the ALB starts provisioning — there is no period where both paths are live, so there is nothing to weight and no rollback except editing the class back and waiting for NGINX to re-converge. An in-place flip is an **all-or-nothing cutover**, not a parallel run.

1. Create the migrated Ingress as a **new object with a new name** (e.g. `web-alb`) carrying `ingressClassName: alb`, leaving the original `nginx` Ingress untouched and serving. Both now answer for the same host on **different load balancers**, which is what makes step 3 possible.
2. Wait for the ALB to provision and its target groups to report healthy; validate directly against the ALB DNS name (`Host:` header) before any DNS change.
3. Use DNS weighted routing to shift traffic from the NGINX load balancer to the ALB, at a low TTL. **Rollback = move the weight back**; the NGINX path is still live and unmodified.
4. Monitor error rates and latency at each weight step.
5. Only once traffic is fully on the ALB, delete the original `nginx` Ingress (Phase 4).

**If a parallel object is not possible** (e.g. a GitOps repo that enforces one Ingress per host, or an admission policy blocking duplicate hosts), then say so plainly in the report and plan it as a **low-TTL all-or-nothing cutover with a documented maintenance window** — do not describe it as weighted or zero-downtime. The Gateway API path (Option 1) does not have this constraint, because the HTTPRoute/Gateway objects are new resources by construction and the Ingress keeps serving until deleted.

### Phase 4: Cleanup
1. Delete old NGINX Ingress resources
2. Remove the NGINX Ingress Controller by **uninstalling its release** (`helm uninstall <release> -n <ns>`) — **not** by deleting the Deployment. The chart also installs an `ingress-nginx-admission` ValidatingWebhookConfiguration with `failurePolicy: Fail` and no selectors; left behind with no endpoints it makes the API server reject **every** Ingress create/update cluster-wide, including re-applying these migrated ALB Ingresses. Non-Helm installs: delete the admission webhook config and its Service explicitly.
3. Remove orphaned TLS Secrets
4. Update IaC/GitOps references

## Checks to Execute

### ALB.1 — Annotation Conversion Completeness

**What to check:**
- All `nginx.ingress.kubernetes.io/*` annotations identified
- Each has a mapped ALB equivalent or documented removal reason

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Only mechanical changes (class swap on the *same* controller, scheme/target-type, simple path) — but see the cutover note below.
- 🟠 3–4 (Medium): URI rewrites → `transforms`, TLS → ACM, timeouts; plus the **new-ALB + DNS cutover** every class switch incurs.
- 🔴 5 (High), no workaround (Tier-A): `configuration-snippet`/`server-snippet` (and the other no-equivalent features — Lua, mirror-to-arbitrary-backend, regex rewrite with capture groups, TLS passthrough, mTLS client-cert). These need **application/code changes** and raise the Re-architecture Gate.
- **Tier-B — score via the rubric, NOT automatically 🔴 5:** **CORS, rate-limit, IP-allowlist, Basic Auth → OIDC** have a faithful workaround (app/backend layer, or WAF / Security Group), so they are rated per the `report-generation.md` §1.3 Feature-Gap rubric — **Impact 2–3 while that workaround can be applied**, escalating to Tier-A (up to 5) only when it cannot (a closed/unmodifiable backend whose loss degrades a live business flow). For **Basic Auth → OIDC** the escalation additionally requires **non-interactive clients** — where every caller is a browser, ALB OIDC/Cognito is a faithful substitute. `report-generation.md` §1.3 is the source of truth for their score.
- ⬜ Unknown: Cannot parse annotations

> **Cutover note (applies to EVERY nginx→alb conversion):** switching `ingressClassName: nginx → alb` is a **cross-controller** change — the AWS LB Controller provisions a **new ALB**, and **traffic does not move until DNS is cut over** to it. This is a parallel-run + DNS cutover, **never** a zero-impact file edit. Therefore a bare class switch is **at least Medium**, even when the YAML diff is one line. (Changing the deprecated `kubernetes.io/ingress.class` annotation to `spec.ingressClassName` on the **same** class is the only genuinely Low case.)

### ALB.2 — ACM Certificate Readiness

**What to check:**
- All TLS hosts have matching ACM certificates (or rely on certificate discovery by omitting `certificate-arn`)
- Certificates are in ISSUED state in the correct region

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): All certs available in ACM
- 🟠 3–4 (Medium): Some certs need provisioning
- 🔴 5 (High): Certs use private CA or non-standard issuance
- ⬜ Unknown: Cannot check ACM

### ALB.3 — AWS LB Controller Readiness

**What to check:**
- AWS LB Controller installed and on a **currently supported release** (no documented minimum for the plain Ingress path; **≥ v2.14.1** if `transforms` URI rewrites are used)
- IAM role with correct policy attached
- IngressClass `alb` exists

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Controller installed, correct version, IAM ready
- 🟠 3–4 (Medium): Controller present but needs upgrade
- 🔴 5 (High): Controller not installed
- ⬜ Unknown: Cannot determine
