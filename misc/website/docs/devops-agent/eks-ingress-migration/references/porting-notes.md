---
title: "Porting Notes — eks-ingress-migration"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/porting-notes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-ingress-migration/references/porting-notes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/porting-notes.md). Edit the source, not this page.
:::

# Porting Notes — eks-ingress-migration

This file documents the differences between the Claude Code version (`skills/eks-ingress-migration/`) and this DevOps Agent port. It is for maintainers, not for the agent to read during execution. **Exclude it from the uploaded skill zip** (`zip -r ../eks-ingress-migration-skill.zip . -x './references/porting-notes.md'`) — it ships in the repository for maintainers only.

> **Staleness check:** the tables below describe the upstream skill at a point in time and can drift as `skills/eks-ingress-migration/` evolves. Re-verify each row against upstream when materially changing either copy, and update the date here. Last verified: 2026-08-30, against upstream `main` (post-#129/#153/#154).

## Differences from the Claude Code version

| Aspect | Claude Code (`skills/eks-ingress-migration/`) | DevOps Agent (this skill) |
|--------|-----------------------------------------------|---------------------------|
| Execution model | Interactive — asks "assess all clusters, or select specific ones?" on ambiguity | Fully autonomous — Step 0 hard-stop decision table, no interactive prompts |
| Cluster selection | Discovers all clusters across regions, assesses many per run | Discovers across regions, assesses **one** cluster per run; **HARD STOP** when more than one is found and none was named (never auto-selects, never assesses all) |
| Tool access | `aws` CLI, `kubectl`, EKS MCP server | AWS control-plane APIs (read-only) + Kubernetes API via the Agent Space EKS access entry (read-only). No Bash, no kubectl, no MCP. |
| Kubernetes reads | `kubectl get/describe`, or MCP `list_k8s_resources` | Expressed as "**Via Kubernetes API**" capability descriptions, not `kubectl` pipelines |
| Report output | Markdown file written to `~/ingress_migration/<cluster>/report.md` | Markdown rendered **inline in the response**; no files written, no output path reported |
| HTML report | `tools/report_to_html.py` renders an interactive dashboard with a 3D routing diagram, score gauge, gate badge, cluster dropdown, and per-option download buttons | **Omitted** — no script execution. Report generation is expressed as instructions + the markdown template; the tool's deterministic renders became literal text (see "Renderer tokens" below). |
| Topology JSON | Written to `~/ingress_migration/<cluster>/topology.json`, consumed by the 3D view | Emitted as one fenced `json` block in the report's References section; same schema, same controller-naming contract, now joined against the Routing Topology table instead of a 3D renderer |
| Manifest export | YAML files written under `<cluster>-manifests/current/` and `target/` | Same content rendered inline as labelled fenced `yaml` blocks, with a **volume guard** (all routes at ≤ 10; above that, shared target resources + the 10 highest-Impact routes + a table of the deferred remainder, counts stated) |
| Snippet route enumeration | `kubectl exec <nginx-pod> -- nginx -T` as an optional deep read | **Not reachable** — no pod exec. The snippet blind spot becomes a permanent, mandatory caveat and the routing inventory is marked Unverified (see below). |
| Directory naming | `references/samples/`, `references/atx/` nested under `references/` | `assets/samples/`, `assets/atx/` — matches the port convention (`references/` stays flat; data files live in `assets/`) |
| Prerequisites | AWS credentials, Python 3.10+, EKS MCP server, AWS CLI | `references/iam-policy.json` for the Agent Space role + an EKS access entry; no Python, no CLI, no MCP |
| `allowed-tools` frontmatter | Not present upstream either | Not present (prohibited in this runtime) |

## Renderer tokens → literal text

`report_to_html.py` substituted four token families that plain markdown would show literally. Each became text carrying the same information:

| Upstream token | Port replacement |
|---|---|
| `[[SCORE:nn:LABEL]]` (colored gauge) | `**Migration Difficulty Score: <nn> / 100 — <LABEL>**` |
| `[[GATE:n]]` (badge) | The tool's own strings, verbatim: `✓ No re-architecture blockers` (n = 0) / `⛔ <n> blocker(s) need(s) redesign / approval` (n > 0) |
| `[[DL:current]]` / `[[DL:gateway-api]]` / `[[DL:alb]]` / `[[DL:atx]]` (download buttons) | Cross-references to the **Export Materials** section, where the YAML is rendered inline |
| `!!red highlight!!` | `**bold**` |

The `!!…!!` conversion is not cosmetic: `report_to_html.py`'s `inline()` implements `**bold**`, backticks, links and `!!hot!!`, so an unrendered `!!…!!` in a markdown-only runtime would reach the reader as literal exclamation marks. The same applies to the `[[…]]` tokens.

## Capability losses (and how each fails closed)

Every loss below is a **runtime reachability** gap, not a content cut. In each case the port fails closed — it reports reduced confidence rather than a clean negative.

1. **Snippet-injected route enumeration.** Upstream can `exec` into the controller pod and read `nginx -T`. This runtime has no shell, no pod exec, and no in-cluster network path, and `pods/exec` is not granted by the access entry. `traffic-routing.md` §5.5 therefore states that the snippet under-count is permanent and unmeasured, requires the report to say the true route count is **≥** the counted one, and hands both deep reads to the cluster owner as verification steps with the inventory marked Unverified. It never infers "no hidden routes".
2. **Admission-webhook exposure.** `ValidatingWebhookConfiguration` lives in `admissionregistration.k8s.io`, outside the built-in groups an access entry is likely to grant (see the caveat below — the managed policy's rules are unpublished). The #153 tri-state already fails closed, so a `403` lands in **Unverified → treated as exposed** and keeps the 🔴 5 CVE-2025-1974 band. The controller Deployment args (`apps`, which *is* covered) are the primary signal; the VWC read is corroboration.
3. **Gateway API adoption state.** `gateway.networking.k8s.io` and `apiextensions.k8s.io` are CRD groups, which an access-entry policy scoped to built-in groups would not reach. A denied read reports Gateway API as **unconfirmed** and sets `"gatewayApi": { "readStatus": "unconfirmed" }` — never `crdsInstalled: false`, and never a recommendation to install CRDs on the strength of a `403`.
4. **Interactive multi-cluster selection.** Replaced by a hard stop, so the port never silently assesses the wrong cluster.

## Supplementary ClusterRole (optional — closes losses 2 and 3)

**Source caveat (verified 2026-08-30).** `AmazonAIOpsAssistantPolicy` — the policy `devops-agent/setup.sh` associates — is listed among the available cluster-access policies in [Review access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html) but, unlike every other policy on that page, **its rules are not enumerated there**. So its exact API-group coverage is *not* confirmable from an authoritative AWS source. The `eks-recon` port's notes state it grants read-only `get`/`list` on built-in groups only and no CRD groups; that is a **secondary, unverified** claim and this port does not depend on it — every read fails closed instead.

Binding the ClusterRole below removes the guesswork: it grants exactly the reads this skill needs, so the webhook tri-state and the Gateway API adoption check resolve definitively rather than degrading. Without it the assessment still completes — it just reports Unverified/unconfirmed where it would otherwise be definitive. Confirm the result with `kubectl auth can-i ... --as-group eks-ingress-migration` rather than assuming.

```yaml
# eks-ingress-migration-rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-ingress-migration
rules:
  # Gateway API adoption state (Option 1 readiness, topology gatewayApi block)
  - apiGroups: ["gateway.networking.k8s.io"]
    resources: ["gatewayclasses", "gateways", "httproutes", "grpcroutes", "referencegrants"]
    verbs: ["get", "list"]
  # Whether the Gateway API CRDs are installed, and at which version
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
  # ingress-nginx admission-webhook exposure (CVE-2025-1974 tri-state)
  - apiGroups: ["admissionregistration.k8s.io"]
    resources: ["validatingwebhookconfigurations"]
    verbs: ["get", "list"]
  # AWS LB Controller route ownership / IngressClassParams (self-managed LBC)
  - apiGroups: ["elbv2.k8s.aws"]
    resources: ["targetgroupbindings", "ingressclassparams"]
    verbs: ["get", "list"]
  # EKS Auto Mode managed load balancing (IngressClassParams in the managed group)
  - apiGroups: ["eks.amazonaws.com"]
    resources: ["ingressclassparams"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: eks-ingress-migration
subjects:
  - kind: Group
    name: eks-ingress-migration
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: eks-ingress-migration
  apiGroup: rbac.authorization.k8s.io
```

Bind the group on the access entry (`--kubernetes-groups eks-ingress-migration`). Note that `aws eks update-access-entry --kubernetes-groups` **replaces** the entry's group list rather than appending — if the role already carries groups from other tooling, pass them all in one comma-separated list. See the `eks-upgrade-check` port's notes for the full access-entry walkthrough; the mechanism is identical.

No Secret access is requested at any point: TLS posture comes from the `secretName` references in `Ingress.spec.tls[]` plus the ACM inventory, never from key material.

## Scoring model — carried over unchanged

The Migration Difficulty Score is the part most at risk from a port, so it was copied without modification and re-derived by hand after porting:

- The deduction model (Impact 5→10, 4→6, 3→4, 2→2, 1→1, non-event 0), the per-category caps, `score = max(0, 100 − Σ)`, and the bands (90–100 TRIVIAL · 80–89 EASY · 70–79 MODERATE · 60–69 HARD · 0–59 VERY HARD) are byte-identical to upstream.
- The **#129 learning is present**: an empty/absent estate is **not rated** — no controller + no IngressClass + no Ingress → 100 / TRIVIAL with a "nothing to migrate" note (`report-generation.md` §1.0), including the §1.0-A carve-out that a reachable CVE/EOL controller is still a security finding at zero routes, and the orphaned-Ingress "Migration Crew Alert" path.
- The #153 auth-tier resolution (Basic Auth → OIDC is Tier-B, escalating to Tier-A only with **both** a closed/unmodifiable backend **and** non-interactive callers) and the #154 `lbc-migrate` toolkit path with its assessor/operator fence are carried over intact.
- The §1.7 worked example still totals 10+6+6+4+4+4 = 34 → **66 HARD**, gate 1 — unchanged by the port.

## Mutating commands are documentation, not actions

The skill is assessment-only upstream; here it is also *incapable* of mutation. Operator steps (Gateway API CRD install, LBC feature-gate enable, `lbc-migrate` applies, DNS cutover, `kubectl delete ingress` cleanup) remain in the references as instructions **for the cluster owner to run under their change-management process**. The #154 assessor/operator fence in `lbc-migrate-toolkit.md` is unchanged, and `SKILL.md` Tool Usage Rule 17 states the agent never executes them. Fenced command blocks use plain fences rather than ` ```bash `, matching the other ports, so nothing implies a shell.

## Upstream observations (not fixed here)

Found while porting; these are defects in the **upstream** skill, left alone so this PR does not edit `skills/`:

1. **`SKILL.md` heading says "Report Structure (5 Navigation Pages)" but the table lists 6 rows** (Overview, Assessment Summary, Routing Topology, Migration Approach, Analysis, References). The port states 6, since it would otherwise carry a wrong count. Worth a one-word fix upstream.
2. **`report-generation.md` upstream `:283` / port `:293`** — the tail of the "Execution risk counts" blockquote says *"moving a feature that has **no faithful equivalent** (CORS, rate-limit, external auth) to WAF/app usually needs **application/code changes**"*. "No faithful equivalent" is the literal **Tier-A** phrase, while §1.3 classifies those same three as **Tier-B precisely because a faithful workaround exists**. An executor reading only that line could score them Tier-A. Pre-existing (`git blame` predates #129), already disclosed on #153; carried over verbatim here rather than silently diverging the port from upstream.
3. **`ingress-resources.md:31`** says "No equivalent — use ALB + Cognito/OIDC" where the sibling CORS row says "No **native** equivalent". Cosmetic, disclosed on #153.
