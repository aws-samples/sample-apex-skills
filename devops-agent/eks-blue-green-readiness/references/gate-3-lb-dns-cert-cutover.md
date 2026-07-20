# Module: Gate 3 — LB / DNS / Cert Cutover

> **Part of:** [eks-blue-green-readiness](../SKILL.md)
> **Purpose:** At cutover, traffic must move from blue to green cleanly. Three wiring facts
> decide whether it can: **load-balancer targets** (blue's target groups point at blue's
> nodes/IPs — green needs its own), **DNS records + TTL** (a cutover record and its TTL bleed
> window), and **TLS cert coverage** (an ACM cert that covers the cutover hostname for green's
> endpoint). None of this spans two clusters automatically. Load
> [readiness-model.md](readiness-model.md) first for the gate vocabulary and roll-up.

## Table of Contents

- [Why none of this spans two clusters](#why-none-of-this-spans-two-clusters)
- [The three cutover facts](#the-three-cutover-facts)
- [What to read](#what-to-read)
- [The gate table](#the-gate-table)
- [Worked example](#worked-example)

---

## Why none of this spans two clusters

In a cluster-shape blue-green, green is a **separate cluster** with its **own** AWS Load Balancer
Controller, its **own** external-dns, and its **own** node/pod IPs. Load balancers, target groups,
DNS records, and cert attachments provisioned for blue **do not automatically extend to green**
(as of 2026-07-20; source: [EKS blue/green upgrade guidance](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
→ "Evaluate Blue/Green Clusters"). Cutover is therefore a deliberate re-wiring at the LB/DNS/cert
layer, and each of the three facts below is a place it can silently fail:
- **LB targets** — green's pods/nodes are not in blue's target groups; if green isn't registered,
  traffic shifted to it hits nothing.
- **DNS + TTL** — a DNS cutover only takes effect as resolvers expire the old record; a long TTL
  means clients keep hitting blue **after** cutover (TTL bleed) — a rollback/cut-back must account
  for the same bleed in reverse.
- **TLS cert** — green's endpoint terminates TLS with a cert that must **cover the cutover
  hostname**; if the ACM cert doesn't include that name (or isn't attached to green's listener),
  clients get cert errors the moment traffic lands on green.

## The three cutover facts

**(a) LB target de-registration / re-registration.** Determine how blue is fronted (an
ALB/NLB via the AWS Load Balancer Controller Ingress/Service, or a shared ALB with
`TargetGroupBinding`), and confirm green has (or has a plan for) its **own** targets. Two shapes:
- **Separate LBs per cluster** (green stands up its own ALB/NLB) → cutover is a **DNS** shift from
  blue's LB DNS name to green's (Gate 3b carries it). Cleanest; each cluster owns its LB.
- **Shared LB, weighted target groups** (both clusters' targets in one ALB, shifted by weight) →
  requires `TargetGroupBinding` (`elbv2.k8s.aws` CRD) wiring on green and target-group weight
  changes. This CRD is **not** readable under the managed policy (see *What to read*).
Confirm green's targets will be **healthy and registered** before traffic shifts; de-registration
of blue uses connection draining (deregistration delay) so in-flight requests complete.

> **Ruling out the shared-LB shape requires the `TargetGroupBinding` CRD — which is unreadable.**
> Concluding "green fronts with its **own** LB" (the clean separate-LB case) means **ruling out** a
> shared-LB weighted-target arrangement, and that shape is expressed through the
> `TargetGroupBinding` (`elbv2.k8s.aws`) CRD, which returns **403** under `AmazonAIOpsAssistantPolicy`
> (the same CRD-unconfirmed pattern the advisor applies to Karpenter/ENIConfig). So the target
> sub-fact can only be **GREEN when the `TargetGroupBinding` CRD read has **succeeded** (via the
> supplementary read-only ClusterRole) and confirmed no shared binding**. If the CRD is unreadable,
> the target sub-fact is **`unconfirmed`** (not-GREEN) — never inferred as "separate LBs / no shared
> target groups" from a blocked read.

> **Session stickiness during a shared/weighted shift.** A weighted or shared-LB shift can break
> sticky sessions (an established session pinned to a blue target lands on green mid-flight, or
> vice-versa). Whether sticky sessions are in use, and whether the shift tolerates them, is an
> **operator-asserted** input (target-group stickiness attributes are not fully in this skill's read
> scope); if unstated it is `unconfirmed`, surfaced as a caveat — never assumed clean. (Distinct
> from deregistration/connection-draining delay above, which only covers in-flight requests, not
> session affinity.)

**(b) DNS record cutover + TTL bleed.** Identify the **cutover hostname** (the app's public record)
and its current **TTL** in Route 53. The TTL is the **bleed window**: after the record is
re-pointed to green, resolvers/clients keep using blue for up to the TTL. A high TTL (e.g. 300s+
or a legacy 3600s) means a slow cutover and a slow cut-back. Best practice is to **lower the TTL
ahead of cutover** (e.g. to 60s) so the shift — and any rollback — is fast; the gate flags a high
TTL as a caveat (for **non-alias** records — see below).

> **ALIAS records to an ELB have a fixed 60s TTL you cannot read or lower.** For a Route 53 **ALIAS**
> record targeting an ELB/ALB/NLB, Route 53 answers with a **fixed 60-second TTL** and
> `ListResourceRecordSets` returns **no `TTL` element** for the record (only `AliasTarget`) — there
> is no TTL field to read and none to lower. (Verified as of 2026-07-20.) So for an alias→ELB record
> (the AWS Load Balancer Controller's default, and the worked example's app hostname) the **TTL
> sub-fact is effectively a fixed 60s and is treated as GREEN** — do **not** gate it on a TTL field
> that does not exist. **TTL gating (and the dead-band rule) applies ONLY to non-alias CNAME/A
> records** that carry an explicit, readable `TTL`.

**(c) TLS cert reissue / attach.** Confirm an **ACM certificate covers the cutover hostname** and
is available in the region for green's listener. Green's new ALB/NLB listener needs a cert
attachment; an ACM cert can be **reused** across LBs in the same account/region if it covers the
name (a wildcard `*.example.com` or a SAN including the host). If no cert covers the hostname,
green must get one **issued and validated** (DNS validation itself takes time) before cutover.

## What to read

**Via AWS API (readable under `iam-policy.json`):**
- `elasticloadbalancing:Describe*` → load balancers, listeners, **target groups**, and **target
  health** (which nodes/IPs are registered and healthy) — confirms blue's fronting and whether
  green targets exist/are healthy.
- `route53:ListHostedZones` / `GetHostedZone` / `ListResourceRecordSets` → the cutover record, its
  type (A/AAAA/ALIAS/CNAME), its **TTL**, and its current target (blue's LB).
- `acm:ListCertificates` / `DescribeCertificate` → certs in-region, their domain + **SANs**, status
  (`ISSUED` vs `PENDING_VALIDATION`), and whether one **covers the cutover hostname**.

**Via Kubernetes API (`AmazonAIOpsAssistantPolicy` — built-in groups only):**
- `Ingress` (`networking.k8s.io` — authorized) and `Service` type LoadBalancer (core — authorized)
  on blue → the hostnames and LB annotations that reveal how blue is fronted. This is the
  readable signal for the fronting shape.

> **Unreadable ELB / Route 53 / ACM = unconfirmed.** If any of `elasticloadbalancing:Describe*`,
> the Route 53 reads, or the ACM reads are blocked, that sub-fact is **`unconfirmed`** — report the
> failed read + the missing IAM permission (all three are in `iam-policy.json` under
> `CutoverReadAccess`); do not report "no LB" / "cert covers it" / GREEN from a blocked read.
> **CRD caveat:** the AWS Load Balancer Controller's `TargetGroupBinding` and `IngressClassParams`
> (`elbv2.k8s.aws`) and any **external-dns** CRD live on **CRD groups NOT authorized** by
> `AmazonAIOpsAssistantPolicy` — reads return `403`. So the *shared-LB weighted-target* shape and
> the external-dns-managed record ownership are **`unconfirmed`** under the managed policy alone
> (supplementary ClusterRole in `references/porting-notes.md`). Never infer "separate LBs" or
> "no shared target groups" from a blocked CRD read.

## The gate table

Gate 3 has **three independent sub-facts** — **(a) LB targets**, **(b) DNS/TTL**, **(c) TLS cert**.
Evaluate each sub-fact to GREEN / AMBER / RED / unconfirmed using its sub-table below, then:

> **Gate 3 outcome = the WORST of the three sub-facts** (RED < unconfirmed < AMBER < GREEN). One RED
> makes the gate RED; absent a RED, one unconfirmed makes it unconfirmed; absent those, one AMBER
> makes it AMBER; only all-three-GREEN is GREEN. Within each sub-table, rows are evaluated top-down
> and the **first matching row wins**. Each sub-table physically places its **unconfirmed** row
> first (it requires a *blocked/failed* read), then the graded RED/AMBER/GREEN rows (which all
> require the read to have *succeeded*); because a blocked read is mutually exclusive with a
> successful one, no input matches both — the first-match order is safe regardless of the physical
> RED-vs-unconfirmed placement.

**Sub-fact (a) — LB targets:**

| # | Condition (first match wins) | Sub-outcome |
|---|------------------------------|-------------|
| 1 | `elasticloadbalancing:Describe*` blocked, **or** the `TargetGroupBinding` (`elbv2.k8s.aws`) / external-dns CRD is **unreadable** (403) so a shared-LB weighted-target arrangement cannot be ruled out | **unconfirmed** — never infer "separate LBs / no shared target groups" from a blocked read. |
| 2 | Green has **no target story at all** (no separate green LB and no shared-LB registration plan) | **RED** — traffic shifted to green would hit no healthy targets. |
| 3 | **Shared LB** requires `TargetGroupBinding` weight wiring that isn't in place yet, or green targets not yet registered but a confirmable plan exists | **AMBER** — name the target groups + green's registration plan. |
| 4 | Green fronts with its **own** LB, confirmed by a **successful `TargetGroupBinding` CRD read** ruling out a shared binding, and green's targets are (or are planned) healthy/registered | **GREEN** — record the LB names. (GREEN is unreachable without the CRD read succeeding — see row 1.) |

**Sub-fact (b) — DNS / TTL:**

| # | Condition (first match wins) | Sub-outcome |
|---|------------------------------|-------------|
| 1 | Route 53 read **blocked**, or the cutover hostname cannot be identified | **unconfirmed** — report the failed read + fix. |
| 2 | Cutover record is an **ALIAS to an ELB** (fixed 60s TTL, no readable/lowerable TTL element) | **GREEN** — effectively a fixed 60s bleed window; TTL gating does not apply to aliases. |
| 3 | Non-alias CNAME/A record with a readable **TTL > 60s** (this closes the old dead-band: anything above 60s, including the 61–300s range and legacy 3600s) | **AMBER** — cutover and cut-back will be slow (TTL bleed). Recommend lowering the TTL to ≤ 60s *before* cutover; record the current TTL. |
| 4 | Non-alias CNAME/A record with a readable **TTL ≤ 60s** | **GREEN** — fast cutover/cut-back; record the TTL. |

**Sub-fact (c) — TLS cert:**

| # | Condition (first match wins) | Sub-outcome |
|---|------------------------------|-------------|
| 1 | ACM read **blocked** | **unconfirmed** — report the failed read + fix; never "cert covers it" from a blocked read. |
| 2 | **No IN-REGION ACM cert covers** the cutover hostname (no wildcard/SAN match, or the only covering `ISSUED` cert is in a **different region** than green's ALB/NLB — ALB/NLB certs must be co-regional), or the only in-region match is `PENDING_VALIDATION` | **RED** — green's TLS endpoint will error at cutover. A cert must be issued + validated **in green's region** (DNS validation takes time) before cutover. |
| 3 | An ACM cert **covers** the cutover hostname, `ISSUED`, **in green's region** | **GREEN** — record the cert ARN. |

> **Cross-cluster service discovery during overlap.** While blue and green run together, a green pod
> may still resolve an in-cluster `Service` to blue (or vice-versa) if service discovery / mesh
> routing is shared or misconfigured across the two clusters. Whether cross-cluster discovery is in
> play and how it is scoped is an **operator-asserted** input (it is not fully readable from the
> built-in K8s API alone); if unstated it is surfaced as an `unconfirmed` caveat on Gate 3, never
> assumed clean.

## Worked example

**Facts:** blue `prod-blue` fronts a public app `app.example.com` via an ALB provisioned by the AWS
Load Balancer Controller (one `Ingress`, own ALB). Route 53: `app.example.com` is an **ALIAS** to
blue's ALB, and the client-facing CNAME `www` has **TTL 3600**. ACM: a wildcard `*.example.com`
cert exists, `ISSUED`, in-region. `elasticloadbalancing:Describe*`, Route 53, and ACM reads all
succeed. The `TargetGroupBinding` CRD read returns **403** (managed policy).

**Evaluation (worst-of-three sub-facts):**
- **(c) cert** — wildcard `*.example.com`, `ISSUED`, in-region, covers the hostname → **GREEN**.
- **(b) DNS/TTL** — `app.example.com` is an **ALIAS to the ALB** (fixed 60s, no readable TTL) → that
  record is **GREEN** by sub-table row 2. The client-facing **`www` CNAME has TTL 3600s** (non-alias,
  readable) → sub-table row 3 → **AMBER**, with "lower `www` TTL to ≤ 60s before cutover". The DNS
  sub-fact is the worst of its records → **AMBER**.
- **(a) LB targets** — green will get its own ALB (separate-LB path), *but* the `TargetGroupBinding`
  CRD read returns **403**, so a shared-LB weighted-target arrangement **cannot be ruled out** →
  sub-table row 1 → **unconfirmed**.

Worst of {GREEN, AMBER, unconfirmed} = **unconfirmed**. **Gate 3 result: unconfirmed** (holds
not-GREEN), with the AMBER `www`-TTL note attached and the Coverage line `gate3.lb_targets:
unconfirmed (elbv2.k8s.aws TargetGroupBinding read 403 — supplementary ClusterRole needed)`;
recommend lowering the `www` CNAME TTL to 60s before cutover. (Had the CRD read succeeded and
confirmed the separate-LB shape, sub-fact (a) would be GREEN and the gate would be AMBER on the
`www` TTL alone.)
</content>
