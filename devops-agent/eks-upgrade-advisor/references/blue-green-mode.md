# Module: Blue-Green Mode (Overlay)

> **Part of:** [eks-upgrade-advisor](../SKILL.md)
> **Purpose:** The **blue-green cutover mode** — an overlay on Phases 2–3, not a phase of its
> own. It replaces the in-place node roll (Phase 2 Step 3) with a parallel target-version fleet
> and a traffic cutover, and it changes the Phase 3 recovery path to a **cut-back**. Selected in
> Phase 1. Load [upgrade-model.md](upgrade-model.md) and [phase-2-execute.md](phase-2-execute.md)
> first — this file only describes what changes under the mode.

## Table of Contents

- [What "blue-green" means here (altitude)](#what-blue-green-means-here-altitude)
- [When to choose it](#when-to-choose-it)
- [The two blue-green shapes](#the-two-blue-green-shapes)
- [How it overlays each phase](#how-it-overlays-each-phase)
- [Cutover gate](#cutover-gate)
- [Cut-back (the payoff)](#cut-back-the-payoff)
- [Cost & capacity note](#cost--capacity-note)
- [Capacity strategies under blue-green (shared-subnet contention)](#capacity-strategies-under-blue-green-shared-subnet-contention)

---

## What "blue-green" means here (altitude)

This is the **cluster-upgrade cutover** strategy: the target-version data plane (or an entire
target-version cluster) is stood up **in parallel** to the old one, workloads/traffic are
shifted to it, and the old ("blue") capacity is kept intact as an instant fallback until the
new ("green") side is validated.

> **Not to be confused with:** the **node-group-level canary blue-green** for an AL2→AL2023 AMI
> change, which is owned by `eks-al2-to-al2023`. That is a data-plane-only AMI swap within one
> cluster/version; this is an *upgrade cutover* across a version change. When a blue-green
> upgrade also crosses AL2→AL2023 (target 1.33+), route the node-OS mechanics to
> `eks-al2-to-al2023` and keep the cutover orchestration here.

## When to choose it

Deterministic selection (mirrors Phase 1's decision table):

| Prefer blue-green when | Prefer in-place (default) when |
|------------------------|-------------------------------|
| Instant node-level fallback required (regulated / high-stakes workload) | Standard risk tolerance, maintenance window available |
| Validating a large or multi-hop upgrade on isolated parallel capacity before committing | Simple single-minor hop |
| Wanting to test the target version under real traffic with a fast escape | Surge headroom is available but full parallel capacity is not |
| Subnet IPs / quota can accommodate a **full parallel fleet** | IPs only support a modest surge |

If subnet IPs/quota cannot support a parallel fleet, blue-green is **not** available — Phase 1
Gate 5 flags this. The verdict then depends on **who chose blue-green** (see Phase 1 → Decision):
when the advisor merely *suggested* it (a multi-hop jump or RISKY band), record **AMBER** and fall
back to in-place; when the **user explicitly requested** blue-green, the outcome is **RED**
(NOT-READY) — the advisor does not silently downgrade the user's chosen path to in-place. In both
cases the operator may resolve capacity first (secondary-CIDR / rolling-drain-down / quota
increase).

## The two blue-green shapes

| Shape | What is parallel | Cutover mechanism | Use when |
|-------|------------------|-------------------|----------|
| **In-cluster (node-fleet) blue-green** | A new target-version node group / Karpenter pool alongside the old, **same cluster & (already-upgraded) control plane** | Cordon blue nodes, shift pods to green via reschedule, keep blue cordoned-not-deleted as fallback | Most upgrades wanting fast node fallback; control plane already upgraded in place (one minor) |
| **Cluster blue-green** | An entire new cluster at the target version | Shift traffic at the ingress/DNS/load-balancer layer from old cluster to new | Big multi-minor jumps, or when you want the target control plane validated in full isolation before any production traffic |

For the **in-cluster** shape the control plane is still upgraded in place in Phase 2 Step 1
(one minor, 7-day rollback net). For the **cluster** shape the new cluster is provisioned at the
target version directly (no in-place control-plane hop on the old cluster).

## How it overlays each phase

- **Phase 1 (Prepare):** same gates, plus confirm **parallel-fleet capacity** (subnet IPs **and**
  EC2 vCPU quota) and — for the cluster shape — a **traffic-shift mechanism** (ingress/DNS/LB
  weighting), a **consumer re-point plan** (below), and a **state/data strategy** (below).

> **Cluster-shape blue-green changes the cluster's identity — plan the consumer re-point.** A new
> cluster has a **new API endpoint and a new OIDC issuer URL**. That breaks two things silently:
> (1) **IRSA** — every IAM role trust policy scoped to the old cluster's OIDC provider must be
> updated (or re-created) for green's issuer, or pods lose their AWS credentials; Pod Identity
> associations must likewise be re-created on green. (2) **Every consumer of the endpoint** —
> `kubectl` configs, CI/CD deploy targets, GitOps controllers — must be re-pointed. Also,
> **load balancers and external-DNS do not span two clusters**, so ingress/cert wiring is
> re-created on green (target-group registration, connection draining, external-dns records, cert
> re-issue/validation). None of this exists in the in-cluster shape (same endpoint/OIDC). State it
> in the plan; it is the most common cluster-blue-green surprise (as of 2026-07-20; source:
> [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
> → "Evaluate Blue/Green Clusters").

> **Stateful workloads are the hard part of cluster blue-green — do not hand-wave this.** For the
> **cluster shape**, persistent data does **not** move for free: an EBS volume is bound to one AZ
> and one cluster's PV/PVC objects, so a green cluster cannot simply reuse it; and cutting a
> stateful service over at the DNS/LB layer while both clusters can write risks **split-brain /
> data divergence**. Cluster-shape blue-green generally cannot cover a stateful service **without
> either downtime** (quiesce writes on blue, snapshot/restore or re-mount to green, then cut over)
> **or app-level replication** (e.g. a database's own replica + failover). Route the actual
> data-movement/restore mechanics to `eks-backup`, but state this constraint plainly in the plan.
> When stateful cluster-blue-green isn't feasible, prefer the **in-cluster (node-fleet) shape**
> (same cluster, same PVs — no data migration) or in-place rolling.
- **Phase 2 (Execute):** Steps 0–2 unchanged (Karpenter, then control plane, then add-ons).
  **Step 3 is replaced** by: stand up green at the target version → bring green
  add-ons/controllers to new-control-plane-compatible versions → shift workloads/traffic to green
  → **keep blue intact**.
- **Phase 3 (Validate/Debug):** validate on **green** using the standard checklist; the recovery
  path becomes **cut-back to blue** (below) instead of a node-group version rollback. Blue is
  torn down only at the Phase 3 tear-down gate, after green is GREEN.

## Cutover gate

| Condition | Action |
|-----------|--------|
| Green fully provisioned, add-ons `ACTIVE` at target-compatible versions, canary workloads healthy on green | **Proceed** — shift the remaining traffic/workloads to green. |
| Green unhealthy before cutover | **Hold on blue** — do not shift traffic; blue is still serving. Diagnose green via Phase 3. |
| Stateful data not yet replicated/consistent on green | **Hard-stop** — do not cut over stateful traffic until data is consistent on green (route to `eks-backup` for the data strategy); a premature cutover risks split or lost state. |

## Cut-back (the payoff)

The reason to pay for blue-green: recovery is a **traffic/scheduling shift back to blue**, which
is untouched and already at the known-good prior version — far faster than a version rollback or
a node-group AMI revert, and it covers data-plane *and* (cluster-shape) control-plane regressions.

| Situation | Cut-back |
|-----------|----------|
| Green misbehaves after partial cutover | Shift traffic/workloads back to blue; blue never changed. |
| Green misbehaves after full cutover, blue not yet torn down | Re-point ingress/DNS/LB (cluster shape) or un-cordon blue + reschedule (node-fleet shape) back to blue. |
| Blue already torn down | Cut-back is gone — this is why the tear-down gate (Phase 3) holds until green is GREEN. |

## Cost & capacity note

Blue-green runs **two fleets (or two clusters) concurrently** for the overlap window — roughly
double the compute cost during cutover, plus enough subnet IPs / instance quota for both sides.
State this in the plan so the operator accepts the cost trade for the faster, safer fallback.
The advisor never silently assumes the capacity exists — Phase 1 Gate 5 must confirm it.

> **The ~2× peak is a function of overlap duration — cap it with rolling drain-down.** The double
> consumption is only "full BLUE-live + full GREEN-projected at once" if blue stays at full size
> while green comes up to full size. An **incremental cutover / rolling drain-down** — scale blue
> down in step as green scales up, draining and cordoning blue nodes as green absorbs their pods —
> caps the peak aggregate **below** 2× and shrinks the window in which the shared pool must hold
> both sides. The magnitude of double-consumption is proportional to the overlap-window duration:
> a long, all-at-once overlap approaches 2×; a tight, rolling overlap stays near 1×-plus-a-batch.
> This is the **primary escape** when the shared subnet is contended and no secondary CIDR is
> available (it trades some of blue's instant-full-fleet fallback for capacity headroom, so state
> the trade). It is a first-class contention mitigation alongside the three strategies below.

## Capacity strategies under blue-green (shared-subnet contention)

The Cost & capacity note above — roughly double the compute cost plus enough subnet IPs and EC2
instance quota for both sides — is the *minimum* model. It is insufficient the moment blue and
green draw pod/node IPs from the **same subnet pool** — the common case when node subnets are
shared across fleets (or across clusters, as in the
[shared-subnet reference architecture](https://github.com/aws-samples/sample-eks-clusters-with-shared-subnets)
(as of 2026-07-20)). During the overlap window **both sides** are alive, so the pool must hold
blue's *live* consumption **and** green's *projected* demand at once. Treat the rolling-drain-down
mitigation (Cost & capacity note above) plus the three items below as a decision aid, applied
before the mode is confirmed and re-checked at Gate 5.

### 1. Shared-subnet aggregate contention (the failure mode)

The VPC CNI assigns every pod a real VPC IP from the node's subnet CIDR (as of 2026-07-20; source:
[Optimizing IP Address Utilization](https://docs.aws.amazon.com/eks/latest/best-practices/ip-opt.html)).
When blue and green share that CIDR, the check is **aggregate, not per-fleet**:

> **The authoritative overlap check is `GREEN-projected demand ≤ current free IPs in the pool`.**
> `current free` already nets out **every** other consumer of the shared pool — BLUE-live *and* any
> third tenant X (another cluster/fleet on the same subnet, as in the shared-subnet reference arch)
> — so this form stays correct no matter how many consumers share the CIDR. Estimate GREEN-projected
> as below and compare it against the pool's current free count. If it exceeds free, cutover stalls:
> green nodes fail to attach ENIs / get pod IPs while the other consumers still hold their share.
> This is the *multi-fleet-same-subnet* failure mode; a per-fleet "surge headroom" reading hides it
> because each fleet looks fine alone.
>
> The total-pool form `BLUE-live + GREEN-projected ≤ total usable IPs` (usable = subnet size minus
> the 5 AWS-reserved addresses; a `/25` = 128 − 5 = 123 usable) is **equal to the free-IP form only
> when blue and green are the pool's SOLE consumers.** In a genuinely shared subnet a third consumer
> X exists, so `free = total usable − BLUE-live − X`; the total-usable form drops the −X term and
> **over-states capacity → false GREEN** in exactly the shared-subnet case this section targets. Use
> the total-usable form only for a single-consumer (blue-only) pool, or subtract the other consumers
> explicitly: `BLUE-live + GREEN-projected ≤ total usable − other-consumers`. Gate 5 and the
> mode-decision definition use this same free-IP-primary comparison.

Estimate each side from readable facts (route raw capacity inventory to `eks-recon`; the advisor
only needs the counts):

- **BLUE-live:** in **secondary-IP mode**, ≈ `running pods` (one VPC IP per pod) **plus** each
  node's warm pool — `WARM_ENI_TARGET`/`WARM_IP_TARGET` pre-allocation held idle per node — **plus**
  each attached ENI's **primary IP** (one per ENI, not pod-assignable) **and** the node's own
  **primary IP**. In **prefix mode**, blue holds whole **/28 prefixes** (16 IPs each) per node per
  `WARM_PREFIX_TARGET`, so live consumption rounds *up* to prefix granularity, not the raw pod
  count. Treat any estimate that omits the ENI/node primary IPs as a conservative **floor** — real
  consumption is higher, so a floor-based "fits" biases toward a false GREEN; prefer to include the
  `(ENIs/node × 1 primary) + node primary IP` terms.
- **GREEN-projected:** `projected node count × per-node IP demand`, where per-node demand =
  `expected pods/node × 1 IP` **plus** the same warm-target pre-allocation green's CNI will hold
  (default `WARM_PREFIX_TARGET=1` allocates one full spare /28 per node even if one pod uses it;
  as of 2026-07-20; source: [Prefix Mode for Linux](https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html)).
  **If green uses custom networking (item 2), `projected node count` itself rises** — custom
  networking lowers max-pods per node, so recompute the node count upward (see item 2's node-count
  note), which inflates both this IP demand and the vCPU-quota half.
- Compare **GREEN-projected against the one pool's current free IP count** (per the formula above —
  free already nets out BLUE-live *and* any third consumer, so it is the safe primary form in a
  shared subnet). Only fall back to the total-usable form when blue is the pool's sole consumer, or
  subtract the other consumers explicitly. Do **not** compare against "each subnet's headroom" as if
  the fleets were isolated.

### 2. Secondary-CIDR for green subnets (escape the shared pool)

A first-class blue-green capacity strategy: carve green's node/pod subnets from a **second VPC CIDR
block** so green does not compete with blue's pool at all. A VPC takes up to four secondary CIDR
blocks after creation **by default** (5 total incl. the primary); this is the *default* quota, not
a hard cap — the "IPv4 CIDR blocks per VPC" quota is adjustable via Service Quotas up to ~50, so do
not treat 4 as a ceiling (as of 2026-07-20; source:
[Amazon VPC FAQs](https://aws.amazon.com/vpc/faqs/) and
[Amazon VPC quotas](https://docs.aws.amazon.com/vpc/latest/userguide/amazon-vpc-limits.html)). The
reference architecture pairs a small primary CIDR for nodes with a large secondary (e.g.
`100.64.0.0/16`, RFC 6598 shared space) for pods (as of 2026-07-20; source:
[Custom Networking](https://docs.aws.amazon.com/eks/latest/best-practices/custom-networking.html)).
Green gets **one `/25` per AZ it spans**, carved from the secondary CIDR; **blue stays on its
existing primary pool** (blue does *not* get a new subnet). For a small single-AZ fleet a single
`/25` for green is a minimal starting shape; a multi-AZ green needs one subnet **per AZ** (a `/25`
is single-AZ, like any subnet).

- **The CNI must be pointed at the new subnets** — this does not happen automatically, and it is an
  **operator action**, not something this advisor performs. Note that
  `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG=true` is a **cluster-wide `aws-node` (VPC CNI) toggle**: a
  bare AZ-named `ENIConfig` (selected by node AZ) would capture **blue** nodes in that AZ too,
  pulling existing blue pods onto the secondary CIDR — the opposite of clean scoping. To scope the
  secondary CIDR to **green only**, instruct the operator to (1) enable custom networking on
  `aws-node`, (2) set `ENI_CONFIG_LABEL_DEF=k8s.amazonaws.com/eniConfig` so ENIConfig is chosen by a
  **node label** rather than AZ, and (3) apply a **green-only node label** matching the green
  `ENIConfig`, leaving blue nodes unlabeled and therefore on the primary pool. New (green) nodes
  must be created **after** the ENIConfig exists (as of 2026-07-20; source: Custom Networking,
  above; verified against AWS custom-networking best practices).
- **The green `ENIConfig` should specify BOTH subnet AND security groups.** Under custom networking a
  pod's **secondary ENI takes its security groups from the `ENIConfig` when they are set**; when the
  `ENIConfig` **omits** `securityGroups`, the CNI falls back to the **node primary ENI's security
  groups** — often workable, but not necessarily what green pods need (they may need reachability to
  blue services, data stores, or the API server that the node-primary SGs don't grant). So an
  `ENIConfig` that names the secondary-CIDR subnet but omits the SGs can leave green pods with IPs
  yet the wrong SGs for their intended connectivity, even though the IP-capacity check reads GREEN.
  Instruct the operator to set `securityGroups` (the cluster/node SGs green pods need) alongside
  `subnet` in every green `ENIConfig` (as of 2026-07-20; source:
  [VPC CNI custom networking (ENIConfig reference)](https://docs.aws.amazon.com/eks/latest/userguide/cni-custom-network.html)).
- **Phase 1 reachability caveat.** Confirming that green's CNI actually targets the secondary CIDR
  means reading the `ENIConfig` — a `crd.k8s.amazonaws.com` custom resource that
  `AmazonAIOpsAssistantPolicy` does not authorize — and at Phase 1 **no green nodes exist yet** to
  observe the effective config instead. So, absent a **supplementary ClusterRole**, secondary-CIDR
  targeting normally resolves to **`unconfirmed`** at Phase 1 — it is **not** a routinely-reachable
  GREEN. Plan for it as the durable escape, but expect Gate 5 to hold it `unconfirmed` (never GREEN,
  per the cardinal rule) until the read is granted or green nodes are up.
- **Solves:** IP contention at overlap — green's IPs come from a pool blue never touches.
- **Raises green's node count — recompute both capacity halves.** Enabling custom networking makes
  the node's **primary ENI stop assigning pod IPs** (its slots are reserved for the node itself),
  so **max-pods per node drops** (e.g. an `m5.large` falls from 29 to 20 without prefix delegation;
  as of 2026-07-20; source:
  [Custom Networking](https://docs.aws.amazon.com/eks/latest/best-practices/custom-networking.html)
  → "Calculate Max Pods per Node"). Fewer pods per node means green needs **more nodes** for the
  same workload — which pushes **both** halves of the capacity model upward: green's secondary-pool
  IP demand (more nodes × per-node warm-target pre-allocation) **and** its EC2 vCPU-quota need (more
  real instances). Recompute the GREEN-projected side (formula in item 1) with the reduced max-pods,
  not blue's original density. Prefix delegation (item 3) recovers much of the lost density and
  brings the node count back down — pair the two when green is on a secondary CIDR.
- **Cluster-shape only — IPv6 pod networking is a first-class escape from IPv4 contention.** When
  green is a **brand-new cluster** (cluster shape), standing it up in **IPv6 mode** removes the
  shared-IPv4-pool contention outright — pods draw from a vastly larger address space — so it is a
  first-class capacity strategy for the green *cluster*, not just a "durable fix" footnote (as of
  2026-07-20; source: [IPv6 / Optimizing IP Address Utilization](https://docs.aws.amazon.com/eks/latest/best-practices/ipv6.html)).
  This applies to the green cluster only; it is **not** a retrofit for blue (an existing cluster's
  IP family is fixed at creation).
- **Does NOT solve:** AZ placement, route-table / NAT / peering reachability for the new range, or
  **EC2 vCPU / instance service-quota** — green still consumes real instances. On AZ placement:
  EBS PersistentVolumes are **AZ-bound**, so carve **one green subnet per AZ that blue spans** so a
  green pod re-binding an existing PV can be scheduled in the **same AZ** as its volume (this is the
  two-AZ `2×/25` shape — one `/25` per AZ). Secondary-CIDR is an IP-exhaustion fix only; the
  vCPU-quota half of the capacity model (see Cost & capacity note) still applies.

### 3. Prefix delegation (double-edged under a contended pool)

Prefix delegation raises **pods-per-node** by assigning each ENI /28 prefixes instead of individual
secondary IPs (as of 2026-07-20; source:
[VPC CNI increases pods per node limits](https://aws.amazon.com/blogs/containers/amazon-vpc-cni-increases-pods-per-node-limits/)).
It lets green run its workload on **fewer nodes** (fewer ENIs, fewer instances) — attractive when
vCPU quota is the tighter constraint.

- **The green instance type's ENI limit is the hard ceiling on pod density.** Max-pods per node is
  ultimately bounded by the chosen instance type's **maximum ENIs × IPs (or /28 prefixes) per ENI**
  (e.g. an `m5.large` supports 3 ENIs) — prefix delegation raises density *within* that ceiling but
  cannot exceed it, so pick green's instance type with its ENI limit in mind when sizing the node
  count (as of 2026-07-20; source: Prefix Mode for Linux, above).

- **Double-edged under contention:** it consumes IPs from the pool in **whole /28 (16-IP) chunks**.
  With `WARM_PREFIX_TARGET=1` a node grabs a full spare prefix even if one pod is running, so a
  green fleet can burn 16-IP blocks *faster* than secondary-IP mode would during ramp — worsening
  the shared-pool contention in item 1 exactly when both fleets are live.
- **Tuning knob:** `WARM_IP_TARGET`/`MINIMUM_IP_TARGET` override `WARM_PREFIX_TARGET`; setting
  `WARM_IP_TARGET` below 16 stops the CNI holding a full idle prefix per node (as of 2026-07-20;
  source: Prefix Mode for Linux, above). AWS labels warm-target minimization a *temporary* measure
  and names secondary CIDRs / IPv6 as the durable fix (source: Optimizing IP Address Utilization,
  above) — so under blue-green, prefer strategy 2 for the durable escape and use prefix tuning only
  to shave green's node count when vCPU quota, not IPs, is the binding limit.

### Decision aid (when to pick which)

The qualitative bands below ("comfortable residual headroom" / "tight" / "cannot hold both sides")
map to the **numeric residual-headroom bands** Gate 5 applies — `headroom = current free IPs −
GREEN-projected` (the free-IP form, which nets out BLUE-live **and** any third consumer; equal to
`total usable − (BLUE-live + GREEN-projected)` only when blue+green are the pool's sole consumers),
banded **< 5** = RED (cannot hold), **5–15** = AMBER (tight), **> 15** = GREEN (comfortable). Those
thresholds are a **skill-internal heuristic, NOT an AWS-published node-surge number** (see
[phase-1-prepare.md](phase-1-prepare.md) → Gate 5). Read the numbers there if you are working from
this file alone.

| Situation at overlap | Strategy |
|----------------------|----------|
| `GREEN-projected ≤ current free IPs` with comfortable residual headroom (item 1 fits) | No change — the minimum model holds; proceed to Gate 5. |
| Aggregate fits but residual headroom is tight, **or** the overlap window is long | **Rolling drain-down** (Cost & capacity note) — scale blue down as green scales up to cap peak aggregate below 2×; the primary escape for a contended shared subnet with no secondary CIDR. |
| Aggregate cannot hold both sides; second VPC CIDR available (or addable) | **Secondary-CIDR for green subnets** (item 2) — the durable escape. Size green's pool for its projected demand + warm targets; the operator must enable custom networking (green-only label scoping — see item 2) before creating green nodes. |
| IPs are fine but **EC2 vCPU / instance quota** is the binding limit | **Prefix delegation** (item 3) to raise pod density and cut green's node count — but watch its /28 pull on the shared pool if green has *not* also been moved to a secondary CIDR. |
| Pool consumption cannot be read (CNI/ENI facts blocked), **or** secondary-CIDR scoping depends on an unreadable `ENIConfig` CRD | **Do not assume it fits** — `ENIConfig` is a **custom resource** (`crd.k8s.amazonaws.com`) that `AmazonAIOpsAssistantPolicy` does not authorize, and at Phase 1 no green nodes exist to observe the effective config instead; Gate 5 reports `unconfirmed`, **never GREEN** (a supplementary ClusterRole is needed, as with Gate 6's Karpenter CRDs). Resolve the read or fall back to in-place. |
