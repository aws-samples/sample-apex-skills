# `lbc-migrate` — AWS Load Balancer Controller (LBC) Ingress → Gateway API Automation Toolkit

> **Not a standalone rated section.** This describes the **automation sub-path for Option 1 (Gateway API)** in the report (`report-generation.md`). It is the *second hop* of the complete path this skill covers: **NGINX Ingress → LBC Ingress** (`alb-migration.md`) **→ Gateway API** (this file). Use it when the estate is **already on the AWS Load Balancer Controller (ALB Ingress)** and the target is Gateway API. All discovery is **read-only**.

> **⚠️ Assessor scope — this skill assesses, it does not perform the migration.** Only **Step 1 (Translate)**, the **local generation** of dry-run manifests, and **read-only inspection** of the resulting plans/diffs are safe for the assessor to run: `lbc-migrate` reads the cluster read-only (`get`/`list`) and writes YAML to a local directory. **Everything that changes the cluster or AWS is an OPERATOR / DevOps action the assessor documents but MUST NOT execute** — installing the Gateway API / LBC Gateway CRDs (`kubectl apply`), enabling the `IngressPlanAnnotation` feature gate (`helm upgrade`), **applying the generated dry-run manifests (Step 2 — creates live `Gateway` objects in the cluster, even though no ALB is provisioned)**, applying Gateway manifests with `--dry-run=false` or `kubectl annotate` (Step 3 — creates real ALBs), and `kubectl delete ingress` (Step 6). Present these as steps for the cluster owner to run under their change-management process, never as commands the assessment runs. (Matches the sibling references: *all assessment checks are read-only.*)

## What it is

The **Ingress-to-Gateway API migration toolkit** for the AWS Load Balancer Controller (LBC) automates the conversion that `migration-plan.md` Phase 2 otherwise hand-authors. It shipped in the **LBC v3.4.0 release (2026-06-03)** and was announced on the AWS networking blog in **July 2026**. It is recent — cite the sources at the bottom of this file and do not over-generalize beyond them. It has two parts:

- **`lbc-migrate` CLI** — translates LBC **Ingress** resources into equivalent **Gateway API** manifests (annotations, path rules, IngressGroups). Reads static YAML/JSON or a live cluster (`--from-cluster`). Cluster access is **read-only** (list/get only); it never creates, updates, or deletes cluster resources. Existing **Deployments and Services are reused as-is** — the tool generates only routing-layer resources.
- **Migration Console** — a local, read-only web UI bundled in the same binary (`lbc-migrate --console`) that shows a **field-by-field diff** of the AWS resource plans the *ingress* controller and the *gateway* controller would each produce, so equivalence can be confirmed before any production change.

## Prerequisites (CRDs + build tag)

The toolkit is a **build artifact of the LBC v3.4.0 release** (see the callout below for why that is not a controller runtime requirement). What the path needs:

- **The `lbc-migrate` CLI, built from the LBC v3.4.0 tag** (see Install below). The **controller runtime** requirement is the same as the manual path — **≥ v3.0.0**, the Gateway API production floor, per `gateway-api.md` — and Gateway API support turns on automatically once the CRDs are present.
- **Gateway API *standard* CRDs v1.5.0** **and** the **LBC Gateway CRDs** *(OPERATOR action — cluster change; the assessor documents these, does not run them)*:
  ```bash
  # Standard Gateway API CRDs
  kubectl apply --server-side=true \
    -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.0/standard-install.yaml
  # LBC Gateway CRDs (LoadBalancerConfiguration, TargetGroupConfiguration, ...)
  kubectl apply \
    -f https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v3.4.0/config/crd/gateway/gateway-crds.yaml
  ```
- Confirm the ALB Gateway controller is live:
  ```bash
  kubectl -n kube-system logs deploy/aws-load-balancer-controller | grep "gateway.k8s.aws/alb"
  ```

> **Where the versions come from.** The `lbc-migrate` CLI **ships in the AWS Load Balancer Controller v3.4.0 release** — build it from that tag (see Install below). It is **not** a higher controller *runtime* tier than the hand-authored path: the controller's Gateway API runtime requirement is the same either way (**≥ v3.0.0**, the production floor, per `gateway-api.md`). What the toolkit path needs is the **standard Gateway API CRDs v1.5.0** — the version the v3.4.0 tag targets (the current v3.5.0 line targets **v1.6.0**) — plus the LBC Gateway CRDs (installed above). On **EKS Auto Mode**, Gateway API is **not** part of the built-in `eks.amazonaws.com` load balancing (Ingress + Service `type: LoadBalancer` only), so the Gateway API target needs a self-managed LBC there too; the upstream guide does **not** document whether `lbc-migrate` targets an Auto Mode estate — do not assume it applies, verify against the guide before recommending it there.

## Install (build from source)

```bash
# Pin to the v3.4.0 tag — the lbc-migrate CLI ships in that release
git clone --branch v3.4.0 --depth 1 https://github.com/kubernetes-sigs/aws-load-balancer-controller.git
cd aws-load-balancer-controller
make lbc-migrate          # binary at bin/lbc-migrate
make install-lbc-migrate  # optional: symlink onto PATH
# or run without building: go run ./cmd/lbc-migrate/ [flags]
```

## Input modes (pick one; `--from-cluster` recommended)

| Mode | Command | Notes |
|------|---------|-------|
| Individual files | `lbc-migrate -f ingress1.yaml,ingress2.yaml` | Combine with `--input-dir`; warns on missing referenced Services/IngressClass/IngressClassParams |
| Directory | `lbc-migrate --input-dir ./manifests/` | Same missing-resource warnings |
| Live cluster | `lbc-migrate --from-cluster --namespaces prod` (or `--all-namespaces`; add `--ingress-name my-api` to narrow to a single Ingress) | **Recommended** — auto-fetches referenced Services/IngressClass/IngressClassParams for the most accurate translation. Read-only RBAC (`get`/`list`) is sufficient. |

Useful flags: `--output-dir` (default `./gateway-output`), `--output-format yaml|json`, `--split=namespace` (one file per namespace + a `gatewayclass` file), `--dry-run` (**default `true`**), `--console`/`--port`.

## Output resources

| Kind | API group | Notes |
|------|-----------|-------|
| `GatewayClass` | `gateway.networking.k8s.io` | Always `controllerName: gateway.k8s.aws/alb`; one per run |
| `Gateway` | `gateway.networking.k8s.io` | One per Ingress (or per `group.name` group); listeners from `listen-ports` |
| `HTTPRoute` | `gateway.networking.k8s.io` | One or more per Ingress; `ssl-redirect` becomes a `RequestRedirect` filter |
| `LoadBalancerConfiguration` | `gateway.k8s.aws` | LB-level settings; only when LB-level annotations present |
| `TargetGroupConfiguration` | `gateway.k8s.aws` | Per-service TG settings; only when TG-level annotations present |
| `ListenerRuleConfiguration` | `gateway.k8s.aws` | Auth, fixed-response, source-IP conditions |

Existing `Deployment`/`Service` are reused — HTTPRoute `backendRefs` point at your Services by name. You replace only the Ingress manifest.

## The 6-step guided flow (each step is safe to pause at)

1. **Translate** *(assessor-safe — read-only)* — `lbc-migrate --from-cluster --namespaces <ns> --output-dir ./gw/`. Reads the cluster (`get`/`list`) only and writes YAML locally. Rollback: delete the generated files.
2. **Dry-run preview (recommended)** *(generating the manifests locally and inspecting a plan are read-only; enabling the feature gate and applying the dry-run manifests are OPERATOR actions)* — verify the generated Gateway will produce the *same* ALB config before creating anything:
   - Enable the ingress-side plan *(OPERATOR action — `helm upgrade` restarts the controller)*: set the LBC feature gate **`IngressPlanAnnotation=true`** (Helm: `--set controllerConfig.featureGates.IngressPlanAnnotation=true`). The ingress controller then writes its model to each Ingress as `alb.ingress.kubernetes.io/dry-run-plan`. **Sensitive-data caveat:** the `dry-run-plan` annotation embeds the controller's full built model (listener/target-group config, cert ARNs, auth settings) on the live object and is readable by anyone with `get` on Ingresses/Gateways — treat it as potentially sensitive, avoid pasting it verbatim into reports, and disable the gate at cleanup (Step 6) so the annotation is removed.
   - Apply the generated manifests *(OPERATOR action — the cluster owner applies; the assessor documents it and never runs it)*. They carry `gateway.k8s.aws/dry-run: "true"` by default, so the gateway controller writes `gateway.k8s.aws/dry-run-plan` **without creating an ALB** — but the `Gateway` objects themselves are **real, live cluster resources**, which is why this is not an assessment action.
   - Compare *(assessor-safe — read-only)*: `lbc-migrate --console` (field-by-field diff) or inspect `gateway.k8s.aws/dry-run-plan` directly with `kubectl get gateway … -o jsonpath=…`.
   - Rollback *(OPERATOR action)*: delete the dry-run Gateway. (Dry-run is ignored on an *already-provisioned* Gateway — it is for previewing **new** Gateways, not pausing live ones.)
3. **Apply** *(OPERATOR action — creates real ALBs)* — regenerate with `--dry-run=false` (GitOps-clean) **or** `kubectl annotate … gateway.k8s.aws/dry-run-` in place. LBC creates **new ALBs alongside** the existing Ingress ALBs, pointing at the **same** Services/Pods. Rollback: delete the Gateway resources.
4. **Verify** *(read-only checks)* — `Programmed: True` on the Gateway, `status.addresses` has the new ALB DNS, `aws elbv2 describe-target-health` all `healthy`, CloudWatch `HealthyHostCount`/`HTTPCode_ELB_5XX_Count`/`TargetResponseTime` nominal; `curl` the Gateway ALB directly.
5. **Shift traffic** *(OPERATOR action)* — move from the Ingress ALB to the Gateway ALB gradually. The upstream guide leaves the exact mechanism to your environment (DNS provider / traffic tooling) and gives **AWS Global Accelerator** as *one* example; **Route 53 weighted records** are another common DNS-based option. Whichever you use, plan for quick rollback and gradual shifting. Rollback: shift back.
6. **Cleanup** *(OPERATOR action — deletes the Ingress and its ALB)* — `kubectl delete ingress <name>` (LBC removes the old ALB/target groups/listener rules), delete any leftover dry-run Gateway, and disable the `IngressPlanAnnotation` gate when no migrations are in progress.

> **Dual-ALB cost during Steps 3–5.** The original Ingress ALBs and the new Gateway ALBs run **in parallel** until cleanup — expect duplicate ALB-hours and LCU-hours on the bill for the migration window. This is the trade for a non-disruptive, reversible cutover.

> **Traffic-shift blocker — direct ALB DNS.** If clients reach the app **directly via the Ingress ALB DNS name** (not a Route 53 / custom domain), traffic **cannot be shifted without updating every client**. Confirm the traffic path before Step 5.

## Known gaps — where the tool skips or warns (hand-edit required)

- **`url-rewrite` / `host-header-rewrite` with capture groups** (e.g. `replace: "/$1"`, `"$1.example.org"`) — **no Gateway API equivalent.** The `URLRewrite` filter does **static** replacements only (`ReplaceFullPath`/`ReplacePrefixMatch` for paths, `PreciseHostname` for hostnames), which cannot reproduce a capture-group substitution. The tool **skips the dynamic transform** — the original regex/`replace` is **discarded** from the generated manifest (upstream documents the skip but *not* a warning for this specific case, so diff the output rather than relying on one) — and it **stays a Tier-A / Re-architecture-Gate item**: a hand *redesign*, not a mechanical fill-in. (Only **static prefix strips** — e.g. a fixed `/api` strip — map cleanly to `ReplacePrefixMatch`; those translate automatically.) This reinforces the skill's existing snippet/rewrite blind-spot warnings.
- **ALB listener-rule count & priority differences** — the generated Gateway can yield a **different number of ALB listener rules** and a **different rule-priority order** than the source Ingress (Gateway API expresses precedence differently). Review the dry-run diff and the upstream [Known Differences from Ingress](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/lbc_migrate_reference/#known-differences-from-ingress) before cutover.
- **WAF Classic (`alb.ingress.kubernetes.io/waf-acl-id`, `web-acl-id`) — not supported.** Migrate to **WAFv2** (`wafv2-acl-arn`) on the source Ingress **before** running `lbc-migrate`, or the generated Gateway has **no WAF protection**.
- **Frontend NLB (`alb.ingress.kubernetes.io/frontend-nlb-*`) — not supported yet.**
- **`group.order` — no Gateway API equivalent for ALB rule priority.** The tool uses it to pick the primary group member, then **warns**. If Ingresses rely on `group.order` to resolve **overlapping** host+path rules, verify precedence with the dry-run before shifting.
- **External Target Groups in `actions.*`** — an external TG can attach to **only one ALB at a time**. During the side-by-side window, delete the Ingress rules referencing it (cutover) or duplicate the TG.
- **`defaultBackend` + host rules** — Gateway API has no `defaultBackend`; the tool emits a separate catch-all HTTPRoute → **one extra ALB listener rule and its own target group** vs the Ingress. Expected behavior; note it in the report.
- **Complex host-header wildcards / regex** that don't conform to Gateway API hostname format are rejected by the API server on apply — review before applying.

## When to recommend `lbc-migrate` vs the manual path

- **Recommend `lbc-migrate`** when the estate is on **LBC ALB Ingress** and the target is Gateway API — it automates the bulk translation and gives dry-run validation. This is the preferred Option 1 sub-path once the prerequisites above are in place: controller at or above the Gateway API **production floor (≥ v3.0.0)**, the **standard Gateway API CRDs the controller line targets** (v1.5.0 for v3.4.0, v1.6.0 for v3.5.0) plus the LBC Gateway CRDs installed, and the CLI built from the **v3.4.0** tag.
- **Keep the manual HTTPRoute authoring** (`migration-plan.md` Phase 2, `gateway-api.md`) as the fallback for the **skip-or-warn** cases above, or on EKS Auto Mode where the built-in provider path differs. For an estate **below the Gateway API production floor** (controller `< v3.0.0`) or **without the standard CRDs its controller line targets**, note that Option 1 *itself* is blocked until the operator upgrades — beyond a handful of Ingresses, recommend **upgrading the controller to the current v3.5.0 release line first** (it clears the production floor *and* still carries the CLI) rather than hand-authoring HTTPRoutes against a controller upstream did not recommend for production.
- Note: `lbc-migrate` migrates **LBC Ingress → Gateway API**. It does **not** convert raw **NGINX** annotations — do the NGINX → LBC Ingress hop first (`alb-migration.md`), then run `lbc-migrate`.

## Reference URLs (cite these; do not invent)

- Launch blog (2026-07-20): https://aws.amazon.com/blogs/networking-and-content-delivery/introducing-the-lbc-ingress-to-gateway-api-migration-toolkit/
- Migrate-from-Ingress guide (6-step flow, feature gate): https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/migrate_from_ingress/
- `lbc-migrate` CLI reference (flags, output, annotation support table): https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/lbc_migrate_reference/
- Migration Console (UI + RBAC): https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/in_cluster_console/
- Kubernetes Gateway API concept: https://kubernetes.io/docs/concepts/services-networking/gateway/
- Companion first-hop blog (NGINX → LBC): https://aws.amazon.com/blogs/networking-and-content-delivery/navigating-the-nginx-ingress-retirement-a-practical-guide-to-migration-on-aws/
