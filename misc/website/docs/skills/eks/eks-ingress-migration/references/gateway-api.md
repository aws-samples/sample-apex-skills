---
title: "Gateway API Prerequisites (input to Migration Options → Option 1)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-ingress-migration/references/gateway-api.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-ingress-migration/references/gateway-api.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-ingress-migration/references/gateway-api.md). Edit the source, not this page.
:::

# Gateway API Prerequisites (input to Migration Options → Option 1)

> **Not a standalone rated section.** These findings feed **Option 1 (Gateway API)** in the report (`report-generation.md`). "Not yet installed" prerequisites are **🟡 Low impact** — the reason is that **no live traffic is at stake** (a prerequisite serves nothing until routes cut over), **not** that they are easy to deploy (effort never sets severity) — per the *Impact Indicator*; never a standalone blocker. All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).
>
> **Automation:** when routes are already on **LBC ALB Ingress**, prefer the official **`lbc-migrate` toolkit** to auto-translate Ingress → Gateway API rather than hand-authoring HTTPRoutes — see `references/lbc-migrate-toolkit.md`. The CLI **ships in the LBC v3.4.0 release** (build it from that tag); its Gateway API *runtime* prerequisite is the same as the hand-authored path — the **production floor below (v3.0.0)**. Pair the controller with the **standard Gateway API CRDs that release targets**: **v1.5.0** for the v3.4.0 tag, **v1.6.0** for the current v3.5.0 line. If the controller is **below the production floor**, Option 1 is blocked until it is upgraded — recommend **upgrading to the current v3.5.0 release line**, which clears the floor *and* still carries the `lbc-migrate` CLI, rather than hand-authoring routes against a controller upstream did not recommend for production.

## Version & naming facts (cite these)
- AWS LB Controller Gateway API **reconciliation** exists since **L4 (TCP/UDP/TLSRoute) v2.13.3** and **L7 (HTTPRoute/GRPCRoute) v2.14.0**. ⚠️ **The production floor is higher — v3.0.0.** Through **v2.15.x** the upstream Gateway API guide carried the warning *"Using the LBC and Gateway API together is not suggested for production workloads (yet!)"*; that warning is **absent from v3.0.0** (released 2026-01-23) onward. So `< v3.0.0` reconciles Gateway API but is **pre-production** — do not pass it as production-ready.
- GatewayClass `controllerName`: **`gateway.k8s.aws/alb`**. Install the **standard Gateway API CRDs the controller release targets** — **v1.5.0** for LBC v3.4.0, **v1.6.0** for the current v3.5.0 line (upstream Gateway API's own latest release is v1.6.1). From Gateway API **v1.6.0** TCPRoute/UDPRoute are in the **standard** channel, so the experimental install is no longer required for L4 routes. The LBC reconciles the Gateway API **`v1`** API.
- On **EKS Auto Mode** the **built-in** controller (`eks.amazonaws.com` API group) covers **Ingress** (the `eks.amazonaws.com/alb` IngressClass) and **Service `type: LoadBalancer`** — **not Gateway API**. As of 2026-09-01 the Auto Mode load-balancing documentation describes Service and Ingress only, so a **Gateway API target still needs a self-managed LBC at ≥ v3.0.0**, even on Auto Mode.

## Caveats & Risks (MUST surface in Option 1)
- **L7 feature parity is still maturing** — verify the TLS handling and routing filters each route needs against the installed LBC version **before** cutover.
- **EKS Auto Mode + self-managed LBC ownership conflict** — if both run, two reconcilers contend for the same load balancer; scope distinct `GatewayClass`/`IngressClass` per controller, or reconcile to a single owner before any apply. Flag whenever both are present.
- **Blast radius** — prefer **per-security-boundary Gateways** (e.g. `public-gateway` for web, separate `private-gateway` for payments) over one shared Gateway, even at extra cost.

## Prerequisite checks (read-only — gather for Option 1, Phase 1)
1. **CRDs** — `kubectl get crd | grep gateway.networking.k8s.io`; need `GatewayClass`, `Gateway`, `HTTPRoute`, `ReferenceGrant` at v1. If missing → install the standard release `standard-install.yaml` matching the controller line (**v1.6.0** for v3.5.0, **v1.5.0** for v3.4.0) — a low-impact Phase-1 step.
2. **Controller version** — `aws-load-balancer-controller` image tag **≥ v3.0.0** (the production floor for Gateway API; see Version facts); IRSA/Pod Identity present; healthy with 2+ replicas. `< v3.0.0` → upgrade in Phase 1, even if it reconciles routes (v2.13.3/v2.14.0 only mark where L4/L7 reconciliation *began*, and upstream flagged those lines as not for production). **Not** covered by Auto Mode's built-in controller — Gateway API needs a self-managed LBC.
3. **GatewayClass** — `spec.controllerName: gateway.k8s.aws/alb`, status `Accepted: True`. None → create in Phase 1.
4. **Adoption status** — list existing `Gateway`/`HTTPRoute`/`GRPCRoute` to tell greenfield from a partial migration (informational).

Record these as **Option 1 Phase-1 foundation steps**, not standalone high-impact findings.
