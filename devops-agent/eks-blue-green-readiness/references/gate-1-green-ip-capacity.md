# Module: Gate 1 — Green IP Capacity

> **Part of:** [eks-blue-green-readiness](../SKILL.md)
> **Purpose:** Decide whether the shared subnets can hold a **whole second cluster's node fleet**
> (green) while blue is still live. This is *not* the in-place surge question (a few extra nodes)
> — it is the *parallel-fleet* question (green's full node/pod IP need, concurrent with blue's).
> Load [readiness-model.md](readiness-model.md) first for the gate vocabulary and roll-up.

## Table of Contents

- [What this gate guards](#what-this-gate-guards)
- [The mechanics: shared-subnet aggregate contention](#the-mechanics-shared-subnet-aggregate-contention)
- [Escape hatches: secondary CIDR and prefix delegation](#escape-hatches-secondary-cidr-and-prefix-delegation)
- [What to read](#what-to-read)
- [The gate table](#the-gate-table)
- [Worked example](#worked-example)

---

## What this gate guards

Blue-green stands up green's node fleet **without tearing blue down** — both fleets are live
during the overlap window. On EKS with the VPC CNI, **every pod gets a routable VPC IP** from the
node's subnet(s). So green's arrival does not consume "a few surge IPs" — it consumes IPs for its
**entire projected pod population**, on top of everything blue is already using **in the same
shared subnets**. If that aggregate exceeds the free IPs in the shared pool, green's nodes come up
but pods stay `Pending` with `failed to assign an IP address` — a silent, capacity-driven cutover
failure.

This is the parallel-fleet extension of the *node-surge* IP check that `eks-upgrade-check` and
`eks-upgrade-advisor` (Phase 1 Gate 5) apply for in-place upgrades. Those check headroom for a
*surge* (old fleet + a bit); this gate checks headroom for a *second whole fleet* (blue-live +
green-projected), which is a materially larger number.

## The mechanics: shared-subnet aggregate contention

The contention is over the **aggregate free IPs across the subnets green's fleet will land in**,
evaluated **while blue is still consuming its share**:

**Prefix delegation OFF** (`ENABLE_PREFIX_DELEGATION` unset/false — one VPC IP per pod):

```
required_green ≈ (green projected pod count)     # one VPC IP per pod (VPC CNI, prefix-off)
              + (green node count × ENIs-per-node × 1)   # each attached ENI's PRIMARY IP (not pod-assignable)
              + (green node count × 1)            # each node's own PRIMARY IP
              + (warm-pool slack: WARM_ENI_TARGET / WARM_IP_TARGET the CNI keeps hot)

available_at_overlap ≈ Σ(subnet free IPs, from ec2:DescribeSubnets AvailableIpAddressCount)
                        # measured NOW, while blue is live — this already nets out blue's usage
```

> **Why the ENI-primary and node-primary IP terms matter.** Each attached ENI consumes one
> **primary IP** that is **not** pod-assignable, and the node itself has a primary IP. The
> authoritative shared capacity model in `eks-upgrade-advisor/references/blue-green-mode.md`
> (Capacity strategies section) adds these terms explicitly and warns that **omitting them treats
> a floor as the real figure and biases toward a false GREEN**. This gate carries the same terms so
> its verdict matches that model. *(The advisor file is the authoritative capacity source; do not
> edit it — this is a copy for single-gate use. Factoring a shared `capacity-model` fragment is a
> porting-notes follow-up.)*

**Prefix delegation ON** (`ENABLE_PREFIX_DELEGATION=true` — /28 prefixes, 16 IPs each): the per-pod
IP term does **not** apply. Consumption rounds **up to /28-prefix granularity** per node per
`WARM_PREFIX_TARGET` (default 1 → one full spare /28 held per node even if one pod uses it), plus
the ENI-primary and node-primary IP terms above. Do **not** apply the prefix-off `1 IP/pod` formula
when prefix delegation is on — it undercounts. **Branch the formula on the confirmed prefix state**
(read from the `aws-node` DaemonSet env, see *What to read*); if the prefix state is unreadable, the
headroom is `unconfirmed` (never computed on a guessed prefix state). *(As of 2026-07-20; source:
[Prefix Mode for Linux](https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html).)*

If green and blue share subnets, `AvailableIpAddressCount` read *now* (blue live) is exactly the
pool green must fit into. The gate compares `required_green` (computed with the correct prefix
branch) against that live-measured free pool.

> **Aggregate is necessary but NOT sufficient — check a per-AZ (per-subnet) floor too.** Summing
> free IPs across subnets can *pass* while a **single AZ** that green must occupy has **zero** free.
> A pod/node cannot borrow another AZ's IPs. Some green placements are **AZ-pinned** and cannot
> spread away from the starved AZ: a `topologySpreadConstraint`/`podAntiAffinity` that forces a pod
> into every AZ, an **AZ-pinned StatefulSet**, or an **EBS-backed PV bound to a specific AZ** (the
> replacement pod must schedule in that AZ). For those, a per-subnet shortfall in the pinned AZ is a
> real RED even when the aggregate passes. So evaluate **both** the aggregate `required_green` vs
> aggregate free **and**, for each AZ green must occupy, that AZ's subnet free count vs green's
> per-AZ need. If green's AZ-pinned placement need for any single AZ exceeds that AZ's subnet free
> IPs, the gate is **not-GREEN** regardless of the aggregate. Whether a green placement is AZ-pinned
> (spread constraints / AZ-bound StatefulSet / EBS-AZ-bound PV) is part of the operator's placement
> intent (row 2); when it is stated, apply the per-AZ floor.

> **Green's placement intent and projected fleet size are REQUIRED operator inputs.** Green does
> not exist yet: a read-only pre-flight can see the VPC's secondary CIDR exists
> (`ec2:DescribeVpcs`) and read blue's fleet, but it **cannot** read (a) whether green will be
> placed in the shared pool or in dedicated secondary-CIDR subnets, nor (b) green's projected node/
> pod count. Both are **operator-asserted**. If placement intent or projected size is **unstated**,
> the gate is `unconfirmed` (not-GREEN) — it is **never** GREEN off an assumed placement or an
> assumed size. When projected size is given only as "green replicates blue," state that assumption
> explicitly in the report and size `required_green` from blue's current fleet.

> **Skill-internal heuristic — NOT an AWS-published number.** The pass/fail thresholds below are a
> **deterministic heuristic internal to this skill**, **analogous but distinct** from the sibling
> skills' node-subnet bands: the advisor/upgrade-check use **absolute** free-IP bands (`<5 / 5–15 /
> >15`), whereas this gate uses a **15% *relative* margin** on the aggregate `required_green`. They
> are the same heuristic *family* (same honesty stance) but **not** the same rule — on identical
> facts they can return different verdicts, so this is deliberately not claimed as strict
> consistency. AWS does **not** publish a "green parallel-fleet free-IP" figure. (AWS
> publishes only a control-plane-subnet requirement of "up to 5 available IPs" for the cluster
> ENIs — a different thing; source: [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
> → "Verify available IP addresses", as of 2026-07-20.) Applied to the **aggregate** free-IP
> headroom **after** subtracting green's projected need:
> - **`available_at_overlap` < `required_green`** → **RED** (green will not fit; pods `Pending`).
> - **`available_at_overlap` ≥ `required_green` but headroom margin < 15%** → **AMBER** (fits, but
>   tight — CNI warm-pool churn or pod bursts can still exhaust it).
> - **`available_at_overlap` ≥ `required_green` with ≥ 15% margin** → **GREEN**.
>
> When green's projected pod count is unknown, use blue's *current* pod population as the
> conservative proxy (green replicates blue) and **state the assumption** in the report.

> **EC2 On-Demand vCPU / instance service quotas are a second, IP-independent standup failure
> mode.** Standing up a *whole second fleet* can hit the account's **On-Demand vCPU** (or
> instance-count) **service quota** in the region even when subnet IPs pass this gate — green's
> nodes then fail to launch with an `InsufficientInstanceCapacity`/quota error, not an IP error.
> This skill does **not** read Service Quotas / current vCPU usage (out of read scope), so headroom
> for the parallel fleet's instance types is **operator-asserted**. An unverified quota is an
> **unread hard standup blocker** (nodes never launch → `InsufficientInstanceCapacity`), not a
> discipline-accept caveat — so it grades exactly like gate-4's unverified RPO and Gate 1 row 2's
> unstated size: **if the operator has AFFIRMATIVELY confirmed sufficient vCPU/instance quota for
> green alongside live blue, note it (does not block); if it is unverified, it is `unconfirmed`**
> ("parallel-fleet EC2 vCPU quota headroom unverified — confirm Service Quotas before standing green
> up") — **not** a silent AMBER caveat, **not** a silent deferral, and never a false GREEN. Treated
> as not-GREEN, it rolls up to NO-GO (unconfirmed) until the operator confirms headroom. This is
> read-only and operator-framed — the skill flags the risk; the operator verifies the quota.

## Escape hatches: secondary CIDR and prefix delegation

When Gate 1 is RED or AMBER on the primary shared pool, two AWS-documented escapes let green land
without contending with blue — surface whichever applies:

- **Dedicated green subnets via a VPC secondary CIDR.** Attach a secondary CIDR to the VPC (e.g.
  a `100.64.0.0/16` carrier-grade block) and carve **green-only** subnets (e.g. **2× /25** — 256
  nominal, but AWS reserves **5 IPs per subnet**, so ~**246 usable** / ~123 per /25) from it, then
  place green's node group / Karpenter pool in those subnets. Green stops
  competing with blue for the primary pool entirely. **Two distinct paths — do not conflate them:**
  - **Whole green node group *in* the secondary-CIDR subnets (no custom networking).** If green's
    entire node group launches in the secondary-CIDR subnets, both the **node primary IPs and the
    pod IPs** come from those subnets — green gets green-subnet IPs **without** CNI custom networking
    / `ENIConfig` at all. This path is fully confirmable read-only (`ec2:DescribeVpcs` for the CIDR
    association + `ec2:DescribeSubnets` for the green subnets' free count); **the ENIConfig-CRD-
    unreadable caveat does NOT apply here**, so the 2×/25 escape is *not* inherently unconfirmable.
  - **Pods in a *different* subnet than the node (custom networking).** Only if pods must land in a
    secondary-CIDR subnet while nodes stay on the primary pool do you need CNI **custom networking**
    (`AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG=true` + an `ENIConfig` selecting the pod subnet). In *that*
    variant only, the `ENIConfig` lives on the `crd.k8s.amazonaws.com` CRD group and is **not**
    readable under the managed policy — so the effective pod-subnet mapping is `unconfirmed`.
  (As of 2026-07-20; sources:
  [VPC secondary CIDR](https://docs.aws.amazon.com/vpc/latest/userguide/configure-your-vpc.html),
  [CNI custom networking with secondary CIDR](https://docs.aws.amazon.com/eks/latest/userguide/cni-custom-network.html).)
  Detectable read-only: `ec2:DescribeVpcs` shows the extra CIDR association (in
  `CidrBlockAssociationSet`) and `ec2:DescribeSubnets` shows the free count of the green subnets.
- **Prefix delegation (denser IP packing, fewer ENIs).** With VPC CNI prefix delegation
  (`ENABLE_PREFIX_DELEGATION=true`), each ENI is assigned **/28 prefixes (16 IPs each)** instead of
  individual secondary IPs, sharply raising pods-per-node and reducing ENI/IP pressure per node —
  which can make green fit in the existing pool. (As of 2026-07-20; source:
  [CNI increase available IPs / prefix delegation](https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses.html).)
  Prefix delegation changes the IP-consumption math but does **not** create address space — if the
  subnet CIDR itself is nearly full, prefix delegation alone will not save it; a secondary CIDR
  will. Whether it is enabled is a CNI config fact (see *What to read*).

## What to read

**Via AWS API (readable under `iam-policy.json`):**
- `eks:DescribeCluster` → the cluster's `resourcesVpcConfig.subnetIds` and VPC.
- `eks:ListNodegroups` / `eks:DescribeNodegroup` → blue's node subnets, scaling config (to size the
  projected green fleet as a blue replica), launch template.
- `ec2:DescribeSubnets` → **`AvailableIpAddressCount`** per subnet (the live free pool, already net
  of the 5 AWS-reserved IPs per subnet) and the subnet CIDR size. It does **not** return the VPC's
  secondary-CIDR association — that lives in `DescribeVpcs` `CidrBlockAssociationSet` (below).
- `ec2:DescribeVpcs` → the VPC's additional CIDR blocks (`CidrBlockAssociationSet`) — the
  secondary-CIDR escape detection. This is a standalone call, **not** part of the `DescribeSubnets`
  response.
- `ec2:DescribeLaunchTemplates` / `DescribeLaunchTemplateVersions` → instance type → **max ENIs /
  IPs-per-ENI** for the node's per-node IP ceiling.

**Via Kubernetes API (`AmazonAIOpsAssistantPolicy`, built-in groups only):**
- The **VPC CNI configuration** is read from the `aws-node` DaemonSet's env (`apps` group — **is**
  authorized): `ENABLE_PREFIX_DELEGATION`, `WARM_PREFIX_TARGET`, `WARM_ENI_TARGET`,
  `WARM_IP_TARGET`, custom-networking flags. This is how prefix-delegation state is confirmed.
- Current pod population (proxy for green's projected need) from `pods` (core group — authorized).

> **Unreadable CNI/ENI facts = unconfirmed.** If the `aws-node` DaemonSet env is unreadable (K8s
> API down) **or** `ec2:DescribeSubnets` is blocked, the prefix-delegation state and/or the free-IP
> pool are `unconfirmed`. Report `unconfirmed` (not a guessed "prefix delegation on" and not a
> false GREEN); it holds the gate at not-GREEN per the combinator. `ENIConfig` custom-networking
> objects live on the `crd.k8s.amazonaws.com` CRD group and are **not** authorized by the managed
> policy — if custom networking is in play, that config is `unconfirmed` (never assumed absent).

## The gate table

**Evaluation order: rows are evaluated top-down; the first matching row wins.** The physical order
places the **unconfirmed** rows (1–2) first, then RED (3–4), then AMBER (5), then GREEN (6–7). This
is still **safe-first**: the unconfirmed rows require a *failed* read (or unstated operator input),
which is mutually exclusive with the RED/AMBER/GREEN rows (those all require the reads to have
*succeeded* and intent+size to be stated), so no input matches both an unconfirmed row and a
graded row — the first-match order cannot let a not-GREEN input reach a false GREEN. `required_green`
is computed with the correct prefix-delegation branch (see
[the mechanics](#the-mechanics-shared-subnet-aggregate-contention)).

| # | Condition (first match wins, top-down) | Outcome |
|---|----------------------------------------|---------|
| 1 | `ec2:DescribeSubnets` free-IP read **blocked**, or the prefix-delegation state / pod population **unreadable** (K8s API down), or custom networking (`ENIConfig`, `crd.k8s.amazonaws.com`) is in use but the CRD is **unreadable** (403) | **unconfirmed** — cannot compute headroom or the effective pod-subnet mapping; report the failed read + fix in Coverage. Treated as not-GREEN. Never a guessed "fits" / GREEN, never "custom networking absent". |
| 2 | Green's **placement intent** (shared pool vs dedicated subnets) **or** projected node/pod size is **unstated** by the operator, **or** the parallel-fleet **EC2 On-Demand vCPU / instance service-quota headroom is unverified** (not affirmatively confirmed by the operator) | **unconfirmed** — a read-only pre-flight cannot read green's intent, projected size, or Service Quotas usage. Unstated placement/size means `required_green` cannot be computed against the right pool; an unverified vCPU/instance quota is an unread hard standup blocker (`InsufficientInstanceCapacity`, nodes never launch) — same grading as gate-4's unverified RPO. Not-GREEN. Never GREEN off an assumed placement, assumed fleet size, or unverified quota; never a silent AMBER for the quota. |
| 3 | Green will use the **shared pool** and **either** aggregate `available_at_overlap` (live, blue-consuming) **<** `required_green`, **or** any single AZ green must occupy (AZ-pinned via spread constraints / AZ-bound StatefulSet / EBS-AZ-bound PV) has **that AZ's subnet free IPs < green's per-AZ need** even though the aggregate passes | **RED** — green will not fit; pods will stay `Pending`. The per-AZ shortfall is a real RED because a pod cannot borrow another AZ's IPs — an aggregate pass does not rescue a starved pinned AZ. A secondary CIDR that merely *exists* on the VPC does **not** rescue this: unless green is actually **planned** for dedicated secondary-CIDR subnets (that is row 4), an unused CIDR changes nothing. Resolve via a VPC secondary CIDR (green-only subnets, e.g. 2× /25 — in the starved AZ) or prefix delegation before standing green up. |
| 4 | Green is **planned for dedicated secondary-CIDR subnets**, but those subnets' free IPs **<** `required_green` (or the required dedicated subnets do not yet exist / are undersized) | **RED** — the dedicated green subnets cannot hold green's projected fleet; size them up (more /25s, larger blocks) before standing green up. Record the shortfall. |
| 5 | Green will use the **shared pool**, `available_at_overlap` **≥** `required_green` but headroom margin **< 15%** | **AMBER** — fits but tight; CNI warm-pool churn or a pod burst can exhaust it. Recommend a secondary CIDR for green or prefix delegation before cutover; record per-subnet free IPs. |
| 6 | Green is **placed in dedicated secondary-CIDR subnets** with free IPs **≥** `required_green` (whole node group in those subnets), **and** `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` is confirmed **OFF** (read from the `aws-node` env) so both node and pod IPs come from the green subnets with no `ENIConfig`-CRD dependency | **GREEN** — green does not contend with blue's pool; record the green subnets + free count. If custom networking is **on** (or the flag is unreadable), the pod-subnet mapping depends on the unreadable `ENIConfig` CRD → row 1 (unconfirmed), not GREEN. |
| 7 | Green will use the **shared pool** and `available_at_overlap` **≥** `required_green` with **≥ 15%** margin, in the subnets green will use, **and** every AZ green must occupy has its own subnet free IPs **≥** green's per-AZ need (no per-AZ shortfall — row 3 not triggered) | **GREEN** — the shared pool holds a full green fleet alongside live blue, with per-AZ headroom for any AZ-pinned placement. |

## Worked example

**Facts:** blue cluster `prod-blue`, 2 managed node groups totalling 20 nodes, ~380 running pods.
Node subnets: `subnet-a` /24 with `AvailableIpAddressCount` **60**, `subnet-b` /24 with **48** →
aggregate free **108** (measured now, blue live). **Operator states green will use the shared pool
and replicate blue** (~20 nodes + ~380 pods) — so both required inputs (placement intent + size)
are supplied (row 2 does not fire). `aws-node` env: `ENABLE_PREFIX_DELEGATION` **not set** (prefix
delegation off), so the prefix-off formula applies: `required_green ≈ 380 pods + (20 nodes ×
ENIs/node × 1 ENI-primary) + (20 node primaries) + warm slack ≈ 400+`. No secondary CIDR on the VPC.

**Evaluation:** reads all succeed and intent+size are stated (rows 1–2 skip). Green uses the shared
pool, `available_at_overlap` = 108, `required_green` ≈ 400 → **108 < 400**, and no dedicated green
subnets / secondary CIDR exist → **row 3 → RED**. Recommendation in the report: attach a secondary CIDR (e.g. `100.64.0.0/16`) and carve
green-only subnets (2× /25 ≈ 246 *usable* IPs — 256 nominal less 5 reserved per subnet — plus prefix delegation to raise pods-per-node), **or** shrink
the overlap window — before standing green up. Prefix delegation alone on the existing /24s does
not create address space, so it is not sufficient here.
</content>
