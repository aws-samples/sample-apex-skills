---
title: "Gateway API Prerequisites (input to Migration Options → Option 1)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/gateway-api.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-ingress-migration/references/gateway-api.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/gateway-api.md). Edit the source, not this page.
:::

# Gateway API Prerequisites (input to Migration Options → Option 1)

> **Not a standalone rated section.** These findings feed **Option 1 (Gateway API)** in the report (`report-generation.md`). "Not yet installed" prerequisites are **🟡 Low impact** — the reason is that **no live traffic is at stake** (a prerequisite serves nothing until routes cut over), **not** that they are easy to deploy (effort never sets severity) — per the *Impact Indicator*; never a standalone blocker. All checks are **read-only** (Kubernetes API `get`/`list`, AWS `Describe`/`List`).
>
> **Automation:** when routes are already on **LBC ALB Ingress**, prefer the official **`lbc-migrate` toolkit** to auto-translate Ingress → Gateway API rather than hand-authoring HTTPRoutes — see `references/lbc-migrate-toolkit.md`. The CLI **ships in the LBC v3.4.0 release** (build it from that tag); its Gateway API *runtime* prerequisite is the same as the hand-authored path (controller **≥ v2.13.3** L4 / **≥ v2.14** L7). Install the current **standard Gateway API CRDs (v1.5.0)** for either path. If the controller is **below that baseline**, Option 1 is blocked until it is upgraded — recommend **upgrading to the current v3.4.0 release line**, which clears the baseline *and* ships the `lbc-migrate` CLI, rather than hand-authoring routes against an unsupported controller.

## Version & naming facts (cite these)
- AWS LB Controller Gateway API support: **L4 (TCP/UDP/TLSRoute) ≥ v2.13.3**, **L7 (HTTPRoute/GRPCRoute) ≥ v2.14** (GA from the 2026 release line).
- GatewayClass `controllerName`: **`gateway.k8s.aws/alb`**. Install the current **standard Gateway API CRDs (v1.5.0)**; the LBC reconciles the Gateway API **`v1`** API.
- On **EKS Auto Mode**, Gateway API / load balancing is provided **built-in** via the `eks.amazonaws.com` API group — no self-managed LBC install needed.

## Caveats & Risks (MUST surface in Option 1)
- **L7 feature parity is still maturing** — verify the TLS handling and routing filters each route needs against the installed LBC version **before** cutover.
- **EKS Auto Mode + self-managed LBC ownership conflict** — if both run, two reconcilers contend for the same load balancer; scope distinct `GatewayClass`/`IngressClass` per controller, or reconcile to a single owner before any apply. Flag whenever both are present.
- **Blast radius** — prefer **per-security-boundary Gateways** (e.g. `public-gateway` for web, separate `private-gateway` for payments) over one shared Gateway, even at extra cost.

## Prerequisite checks (read-only — gather for Option 1, Phase 1)
1. **CRDs** — list `CustomResourceDefinition` (`apiextensions.k8s.io/v1`) and filter for `gateway.networking.k8s.io`; need `GatewayClass`, `Gateway`, `HTTPRoute`, `ReferenceGrant` at v1. If missing → install the current standard release `standard-install.yaml` **v1.5.0** (a low-impact Phase-1 step, run by the cluster owner).
   > **Runtime caveat:** `apiextensions.k8s.io` and the `gateway.networking.k8s.io` CRD group are **not** covered by the default access-entry RBAC — a denied read means Gateway API adoption is **unconfirmed**, never "not installed". Do not recommend installing CRDs on the strength of a `403`. See `references/porting-notes.md`.
2. **Controller version** — `aws-load-balancer-controller` image tag **≥ v2.14** (L7) / **≥ v2.13.3** (L4); IRSA/Pod Identity present; healthy with 2+ replicas. `< v2.14` → upgrade in Phase 1. Built-in on Auto Mode.
3. **GatewayClass** — `spec.controllerName: gateway.k8s.aws/alb`, status `Accepted: True`. None → create in Phase 1.
4. **Adoption status** — list existing `Gateway`/`HTTPRoute`/`GRPCRoute` to tell greenfield from a partial migration (informational).

Record these as **Option 1 Phase-1 foundation steps**, not standalone high-impact findings.
