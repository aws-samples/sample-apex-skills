# `lbc-migrate` — LBC Ingress → Gateway API Automation Toolkit

> **Not a standalone rated section.** This describes the **automation sub-path for Option 1 (Gateway API)** in the report (`report-generation.md`). It is the *second hop* of the complete path this skill covers: **NGINX Ingress → LBC Ingress** (`alb-migration.md`) **→ Gateway API** (this file). Use it when the estate is **already on the AWS Load Balancer Controller (ALB Ingress)** and the target is Gateway API. All discovery is **read-only**.

## What it is (cite the sources below; do not over-generalize — this shipped 2026-07-20)

The **Ingress-to-Gateway API migration toolkit** for the AWS Load Balancer Controller (LBC) automates the conversion that `migration-plan.md` Phase 2 otherwise hand-authors. It has two parts:

- **`lbc-migrate` CLI** — translates LBC **Ingress** resources into equivalent **Gateway API** manifests (annotations, path rules, IngressGroups). Reads static YAML/JSON or a live cluster (`--from-cluster`). Cluster access is **read-only** (list/get only); it never creates, updates, or deletes cluster resources. Existing **Deployments and Services are reused as-is** — the tool generates only routing-layer resources.
- **Migration Console** — a local, read-only web UI bundled in the same binary (`lbc-migrate --console`) that shows a **field-by-field diff** of the AWS resource plans the *ingress* controller and the *gateway* controller would each produce, so equivalence can be confirmed before any production change.

## Version gate (prerequisites)

Per the launch blog, the toolkit ships with and requires:

- **AWS Load Balancer Controller v3.4.0** (Gateway API support turns on automatically once the CRDs are present).
- **Gateway API *standard* CRDs v1.5.0** **and** the **LBC Gateway CRDs**:
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

> **Higher than the manual-path baseline.** `gateway-api.md` documents the *minimum* Gateway API support in LBC (**≥ v2.14** L7 / **≥ v2.13.3** L4, CRDs **v1.3.0**). The **toolkit** needs a **higher** baseline — **v3.4.0 + standard CRDs v1.5.0**. When recommending `lbc-migrate`, require v3.4.0/v1.5.0; the lower baseline only covers hand-authored HTTPRoutes. On **EKS Auto Mode**, Gateway API is provided built-in via `eks.amazonaws.com` — confirm toolkit compatibility before assuming `lbc-migrate` applies.

## Install (build from source)

```bash
git clone https://github.com/kubernetes-sigs/aws-load-balancer-controller.git
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
| Live cluster | `lbc-migrate --from-cluster --namespaces prod` (or `--all-namespaces`, or `+ --ingress-name my-api`) | **Recommended** — auto-fetches referenced Services/IngressClass/IngressClassParams for the most accurate translation. Read-only RBAC (`get`/`list`) is sufficient. |

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

1. **Translate** — `lbc-migrate --from-cluster --namespaces <ns> --output-dir ./gw/`. Rollback: delete the generated files.
2. **Dry-run preview (recommended)** — verify the generated Gateway will produce the *same* ALB config before creating anything:
   - Enable the ingress-side plan: set the LBC feature gate **`IngressPlanAnnotation=true`** (Helm: `--set controllerConfig.featureGates.IngressPlanAnnotation=true`). The ingress controller then writes its model to each Ingress as `alb.ingress.kubernetes.io/dry-run-plan`.
   - Apply the generated manifests — they carry `gateway.k8s.aws/dry-run: "true"` by default, so the gateway controller writes `gateway.k8s.aws/dry-run-plan` **without creating an ALB**.
   - Compare: `lbc-migrate --console` (field-by-field diff) or inspect `gateway.k8s.aws/dry-run-plan` directly with `kubectl get gateway … -o jsonpath=…`.
   - Rollback: delete the dry-run Gateway. (Dry-run is ignored on an *already-provisioned* Gateway — it is for previewing **new** Gateways, not pausing live ones.)
3. **Apply** — regenerate with `--dry-run=false` (GitOps-clean) **or** `kubectl annotate … gateway.k8s.aws/dry-run-` in place. LBC creates **new ALBs alongside** the existing Ingress ALBs, pointing at the **same** Services/Pods. Rollback: delete the Gateway resources.
4. **Verify** — `Programmed: True` on the Gateway, `status.addresses` has the new ALB DNS, `aws elbv2 describe-target-health` all `healthy`, CloudWatch `HealthyHostCount`/`HTTPCode_ELB_5XX_Count`/`TargetResponseTime` nominal; `curl` the Gateway ALB directly.
5. **Shift traffic** — move from the Ingress ALB to the Gateway ALB gradually. Two options: **Route 53 weighted routing** (DNS-based, **no extra cost**) or **AWS Global Accelerator** (per-request split, no domain needed). Rollback: shift back.
6. **Cleanup** — `kubectl delete ingress <name>` (LBC removes the old ALB/target groups/listener rules), delete any leftover dry-run Gateway, and disable the `IngressPlanAnnotation` gate when no migrations are in progress.

> **Dual-ALB cost during Steps 3–5.** The original Ingress ALBs and the new Gateway ALBs run **in parallel** until cleanup — expect duplicate ALB-hours and LCU-hours on the bill for the migration window. This is the trade for a non-disruptive, reversible cutover.

> **Traffic-shift blocker — direct ALB DNS.** If clients reach the app **directly via the Ingress ALB DNS name** (not a Route 53 / custom domain), traffic **cannot be shifted without updating every client**. Confirm the traffic path before Step 5.

## Known gaps — where the tool skips + warns (hand-edit required)

- **`url-rewrite` / `host-header-rewrite` with capture groups** (e.g. `replace: "/$1"`, `"$1.example.org"`) — Gateway API's `URLRewrite` filter supports only **static** replacements (`ReplaceFullPath`/`ReplacePrefixMatch` for paths, `PreciseHostname` for hostnames). The tool **skips the dynamic transform and warns**; you finish the HTTPRoute by hand with the equivalent filter (e.g. a `/api`-strip becomes `urlRewrite.path.type: ReplacePrefixMatch`). Static-replacement transforms translate automatically. This reinforces the skill's existing snippet/rewrite blind-spot warnings.
- **WAF Classic (`alb.ingress.kubernetes.io/waf-acl-id`, `web-acl-id`) — not supported.** Migrate to **WAFv2** (`wafv2-acl-arn`) on the source Ingress **before** running `lbc-migrate`, or the generated Gateway has **no WAF protection**.
- **Frontend NLB (`alb.ingress.kubernetes.io/frontend-nlb-*`) — not supported yet.**
- **`group.order` — no Gateway API equivalent for ALB rule priority.** The tool uses it to pick the primary group member, then **warns**. If Ingresses rely on `group.order` to resolve **overlapping** host+path rules, verify precedence with the dry-run before shifting.
- **External Target Groups in `actions.*`** — an external TG can attach to **only one ALB at a time**. During the side-by-side window, delete the Ingress rules referencing it (cutover) or duplicate the TG. 
- **`defaultBackend` + host rules** — Gateway API has no `defaultBackend`; the tool emits a separate catch-all HTTPRoute → **one extra ALB listener rule and its own target group** vs the Ingress. Expected behavior; note it in the report.
- **Complex host-header wildcards / regex** that don't conform to Gateway API hostname format are rejected by the API server on apply — review before applying.

## When to recommend `lbc-migrate` vs the manual path

- **Recommend `lbc-migrate`** when the estate is on **LBC ALB Ingress** and the target is Gateway API — it automates the bulk translation and gives dry-run validation. This is the preferred Option 1 sub-path when prerequisites (v3.4.0 / CRD v1.5.0) are met.
- **Keep the manual HTTPRoute authoring** (`migration-plan.md` Phase 2, `gateway-api.md`) as the fallback for the **skip-and-warn** cases above, for estates below the toolkit's version gate, or on EKS Auto Mode where the built-in provider path differs.
- Note: `lbc-migrate` migrates **LBC Ingress → Gateway API**. It does **not** convert raw **NGINX** annotations — do the NGINX → LBC Ingress hop first (`alb-migration.md`), then run `lbc-migrate`.

## Reference URLs (cite these; do not invent)

- Launch blog (2026-07-20): https://aws.amazon.com/blogs/networking-and-content-delivery/introducing-the-lbc-ingress-to-gateway-api-migration-toolkit/
- Migrate-from-Ingress guide (6-step flow, feature gate): https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/migrate_from_ingress/
- `lbc-migrate` CLI reference (flags, output, annotation support table): https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/lbc_migrate_reference/
- Migration Console (UI + RBAC): https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress2gateway/in_cluster_console/
- Kubernetes Gateway API concept: https://kubernetes.io/docs/concepts/services-networking/gateway/
- Companion first-hop blog (NGINX → LBC): https://aws.amazon.com/blogs/networking-and-content-delivery/navigating-the-nginx-ingress-retirement-a-practical-guide-to-migration-on-aws/
