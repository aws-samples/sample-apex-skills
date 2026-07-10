# Gateway API Prerequisites (input to Migration Options → Option 1)

> **Not a standalone rated section.** These findings feed **Option 1 (Gateway API)** in the report (`report-generation.md`). "Not yet installed" prerequisites are **🟡 Low impact** (easy to deploy) per the *Impact Indicator* — never a standalone blocker. All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).

## Version & naming facts (cite these)
- AWS LB Controller Gateway API support: **L4 (TCP/UDP/TLSRoute) ≥ v2.13.3**, **L7 (HTTPRoute/GRPCRoute) ≥ v2.14** (GA from the 2026 release line).
- GatewayClass `controllerName`: **`gateway.k8s.aws/alb`**. The LBC targets Gateway API CRDs **v1.3.0**.
- On **EKS Auto Mode**, Gateway API / load balancing is provided **built-in** via the `eks.amazonaws.com` API group — no self-managed LBC install needed.

## Caveats & Risks (MUST surface in Option 1)
- **L7 feature parity is still maturing** — verify the TLS handling and routing filters each route needs against the installed LBC version **before** cutover.
- **EKS Auto Mode + self-managed LBC ownership conflict** — if both run, two reconcilers contend for the same load balancer; scope distinct `GatewayClass`/`IngressClass` per controller, or reconcile to a single owner before any apply. Flag whenever both are present.
- **Blast radius** — prefer **per-security-boundary Gateways** (e.g. `public-gateway` for web, separate `private-gateway` for payments) over one shared Gateway, even at extra cost.

## Prerequisite checks (read-only — gather for Option 1, Phase 1)
1. **CRDs** — `kubectl get crd | grep gateway.networking.k8s.io`; need `GatewayClass`, `Gateway`, `HTTPRoute`, `ReferenceGrant` at v1. If missing → install `standard-install.yaml` **v1.3.0** (a low-impact Phase-1 step).
2. **Controller version** — `aws-load-balancer-controller` image tag **≥ v2.14** (L7) / **≥ v2.13.3** (L4); IRSA/Pod Identity present; healthy with 2+ replicas. `< v2.14` → upgrade in Phase 1. Built-in on Auto Mode.
3. **GatewayClass** — `spec.controllerName: gateway.k8s.aws/alb`, status `Accepted: True`. None → create in Phase 1.
4. **Adoption status** — list existing `Gateway`/`HTTPRoute`/`GRPCRoute` to tell greenfield from a partial migration (informational).

Record these as **Option 1 Phase-1 foundation steps**, not standalone high-impact findings.
