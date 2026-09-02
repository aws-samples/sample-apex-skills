# 💰 Cost Optimization Analysis

Identify cost savings opportunities from cluster data. Prioritized by impact tier and implementation effort.

---

## Opportunity 1: Graviton Migration (Tier 1 — High Impact)

**Detection:**
```bash
# EC2 capacity only. Fargate nodes carry NO instance-type label (they would read as
# `null`, which naively counts as "not Graviton"), and EKS Auto Mode provisions nodes
# AWS-side. A cluster with no EC2 capacity has nothing to migrate.
jq -r '[.items[]|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")] as $ec2
  | if ($ec2|length)==0 then "NO EC2 CAPACITY — Graviton migration is NOT APPLICABLE"
    else ($ec2|map(.metadata.labels["node.kubernetes.io/instance-type"]//"unlabelled")
               |group_by(.)|map({(.[0]):length})|add|tostring) end' "$WORK/nodes.json"
jq -r 'if .cluster.computeConfig.enabled==true then "AUTO MODE — AWS selects instance types; recommend arm64-compatible workloads + a NodePool architecture requirement, NOT a node migration" else "not Auto Mode (customer-managed compute)" end' "$WORK/cluster.json"
```

**Analysis:** Graviton families carry a `g` in the generation suffix — `m7g`, `c7g`, `r7g`, `m8g`,
`c8g`, `m6g`, `c6g`, `t4g`. Anything else on EC2 is x86.

**Raise this whenever ANY x86 EC2 capacity remains.** It is the single largest compute lever the
skill can act on that is not workload-dependent: unlike Spot it costs nothing in availability, and
unlike a version upgrade it is not time-boxed. Same vCPU, same memory, lower hourly rate, and
typically equal or better throughput per core. Treat "we have not looked at Graviton" as the default
state to challenge, not as a preference to respect.

**Get the saving from the Price List API, do not quote a fixed percentage.** The long-standing
"~20%" in this file is the **Graviton2** delta; current-generation Graviton3 is nearer **15%**.
Verified live in `ap-southeast-5` (Price List, published 2026-08-31):

| From (x86) | To (Graviton) | Hourly | Delta |
|---|---|---|---|
| `m6i.large` $0.1020 | `m7g.large` $0.0867 | −$0.0153 | **−15.0%** |
| `c6i.large` $0.0833 | `c7g.large` $0.0708 | −$0.0125 | **−15.0%** |
| `m6i.large` $0.1020 | `m6g.large` $0.0816 | −$0.0204 | −20.0% (Gen2) |

Quote the real pair for the customer's region and node types. An inflated number is worse than no
number: it is the fastest way to lose the operator's trust in the whole report.

**The one real prerequisite — check it before recommending, and say which:**
- **Container images must be `linux/arm64`.** Most official images are multi-arch already; anything
  built in-house needs a `docker buildx --platform linux/amd64,linux/arm64` build. This is the work.
- Anything with a compiled x86-only dependency or a vendor-supplied amd64-only image stays x86. That
  is a legitimate answer — name the blocker rather than repeating the recommendation.

**Report as:**
- **Title:** Migrate the remaining x86 capacity to Graviton
  (Scope the title and the saving to the x86 nodes that are LEFT. On a fleet that is
  already part-Graviton, "migrate to Graviton" reads as though nothing has been done.)
- **Current State:** X of Y nodes on x86 (list the types and their hourly rate)
- **Recommended State:** equivalent Graviton types (`m5`/`m6i`→`m7g`, `c5`/`c6i`→`c7g`, `r5`→`r7g`),
  with the region's real hourly delta
- **Estimated Savings:** (x86 rate − Graviton rate) × node count × 730, shown as $/month
- **Effort:** Medium — confirm arm64 images, then roll a new node group (or set an
  architecture requirement on the Karpenter/Auto Mode NodePool) and drain the old one
- **Prerequisite:** arm64 images for every workload that will land on those nodes

---

## Opportunity 2: Spot Instance Adoption (Tier 1 — High Impact)

**Detection:**
```bash
# Read the capacity type off the NODES rather than iterating node groups — Auto Mode and
# Karpenter clusters have none to iterate, and a Fargate cluster has no EC2 capacity to move to
# Spot at all. Coalesce BOTH capacity labels: managed node groups set
# `eks.amazonaws.com/capacityType`, while Karpenter and Auto Mode set
# `karpenter.sh/capacity-type` (lowercase value). Reading only the first bucketed genuinely-Spot
# nodes as UNKNOWN, understating existing Spot adoption and inviting a fabricated saving.
jq -r '[.items[]|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]
  | if length==0 then "NO EC2 CAPACITY — Spot adoption is NOT APPLICABLE"
    else (map((.metadata.labels["eks.amazonaws.com/capacityType"]
               // .metadata.labels["karpenter.sh/capacity-type"] // "UNKNOWN")|ascii_upcase)
          |group_by(.)|map({(.[0]):length})|add|tostring) end' "$WORK/nodes.json"
jq -r '"node groups: \((.nodegroups//[])|length)"' "$WORK/nodegroups.json"
# Auto Mode: Spot is still available but the MECHANISM differs — there is no node group and no
# mixed-instances policy; you set `capacity-type: spot` in a NodePool. Say that, and never quote
# a node-group count.
jq -r 'if .cluster.computeConfig.enabled==true then "AUTO MODE — express Spot as a NodePool `capacity-type: spot` requirement; do NOT reference node groups or mixed instance policies" else "" end' "$WORK/cluster.json"
```
(Detection is node-level; there is no per-nodegroup loop. Report findings in NODE terms — "N of M nodes on On-Demand" — never "N of M node groups", which cannot be filled from this data and reads as nonsense on a cluster with zero node groups.)

**Which workloads could actually take Spot.** "You are 100% On-Demand" is not actionable on its own —
the operator's next question is always *which of my workloads is safe to move*. Answer it from data
already collected. The EC2-capacity guard is inside the jq, not a note beside it, so a Fargate or
serverless cluster cannot fall through into a recommendation it cannot act on:

```bash
jq -r -s '.[0] as $d|.[1] as $s|.[2] as $n
  | [$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")] as $ec2
  | if ($ec2|length)==0 then "NO EC2 CAPACITY — Spot readiness is NOT APPLICABLE" else
    ([$d.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $dep
    | [$dep[]|select(((.spec.replicas//1)>=2) and ((((.spec.template.spec.volumes//[])|map(select(.persistentVolumeClaim//empty)))|length)==0))|.metadata.namespace+"/"+.metadata.name] as $ready
    | [$dep[]|select(((.spec.replicas//1)<2) or ((((.spec.template.spec.volumes//[])|map(select(.persistentVolumeClaim//empty)))|length)>0))|.metadata.namespace+"/"+.metadata.name] as $hold
    | [$s.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|.metadata.namespace+"/"+.metadata.name] as $sts
    | "SPOT-READY TODAY (>=2 replicas, no PVC): \($ready|length) \($ready)",
      "NOT YET SPOT-SAFE (single replica or PVC-backed): \($hold|length) \($hold)",
      "STATEFULSETS (keep On-Demand unless the app tolerates node loss): \($sts|length) \($sts)")
    end' "$WORK/deployments.json" "$WORK/statefulsets.json" "$WORK/nodes.json"
```

**Analysis:** Spot capacity runs at a large discount (commonly 60–90% off On-Demand; check the current
rate for the region and instance type) in exchange for a 2-minute interruption notice. The discount is
real and large — the constraint is never price, it is whether the workload survives losing a node.

**Highlight the gap precisely.** Report three numbers, not one: how much capacity is On-Demand, how
many workloads are already Spot-safe as configured, and what the remainder needs. A cluster that is
100% On-Demand while running five multi-replica stateless Deployments has a much bigger gap than one
that is 100% On-Demand because everything it runs is a single-replica StatefulSet.

> **Disclaimer to include in the report, verbatim in substance:**
> Spot suits **stateless, interruption-tolerant** workloads — multi-replica Deployments with a PDB,
> queue consumers, batch and CI. Move those if you can; the saving is the largest on this list.
> **Staying on On-Demand is a legitimate choice**, and this review does not treat it as a defect. If a
> workload is single-replica, holds state on local disk, is latency-critical, cannot tolerate a
> 2-minute eviction, or is bound by a contractual availability target, keep it On-Demand and say so.
> A blended fleet — Spot for the tolerant tier, On-Demand for the rest — is the normal end state, not
> a compromise.

**This is deliberately NOT a scored question**, and neither is Graviton. Both depend on workload
intent that no `aws`/`kubectl` call reveals: Spot under a stateful tier is *wrong*, not merely
un-optimised, and Graviton is blocked by image architecture the cluster cannot report. Scoring them
would manufacture a finding against clusters that are correct by design — the same failure mode as
grading a Fargate cluster on node hardening. They belong here, in the narrative, where the
recommendation can carry its own preconditions. Do not move them into `cost-optimization.md`.

**Report as:**
- **Title:** Move the interruption-tolerant tier to Spot capacity
- **Current State:** X of Y nodes On-Demand; of Z workload Deployments, N are already Spot-safe
  (multi-replica, no PVC) and M are not (name them and say why)
- **Recommended State:** Spot for the N Spot-safe workloads, On-Demand retained for StatefulSets and
  single-replica services. On managed node groups use a second Spot node group with several instance
  types; on Karpenter/Auto Mode set `capacity-type: spot` in the NodePool alongside an On-Demand pool.
- **Estimated Savings:** current On-Demand spend for the movable share × the region's Spot discount —
  state the assumed discount, and state the share you assumed is movable
- **Effort:** Medium — diversify instance types so a single pool reclaim cannot drain the tier, add
  PDBs, and install the AWS Node Termination Handler (not needed on Auto Mode, which handles it)
- **Do not recommend for:** the StatefulSets and single-replica Deployments listed above

---

## Opportunity 3: gp2 to gp3 Storage Migration (Tier 2 — Medium Impact)

**Detection:**
```bash
# NB: compare the StorageClass `parameters.type`, never its NAME — captures have been seen
# with a class named `gp3` that provisions gp2, and a class named `gp2` that provisions gp3.
jq -r '.items[] | {name: .metadata.name, provisioner: .provisioner, type: .parameters.type}' "$WORK/storageclasses.json"
jq -r -s '.[1].cluster.name as $cn | [.[0].Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0)|select(.VolumeType=="gp2")|{Id:.VolumeId,Size:.Size,State:.State}]' "$WORK/volumes.json" "$WORK/cluster.json"
```

**Analysis:** Check for gp2 volumes or StorageClasses still using gp2.

**The performance comparison — get this right, the old wording was wrong by 33×.**

| | gp2 | gp3 |
|---|---|---|
| Baseline IOPS | **3 IOPS/GiB**, minimum 100, maximum 16,000 | flat **3,000**, any size |
| Baseline throughput | up to 250 MiB/s, scales with size | flat **125 MiB/s**, any size |
| Burst | to 3,000 IOPS below 1,000 GiB | none — baseline is not a credit pool |
| Price | ~$0.10/GiB-mo | ~$0.08/GiB-mo (**~20% less**) |

This file previously said *"3000 IOPS vs 100 IOPS/GiB"*, which confuses gp2's 100-IOPS **floor** with
its 3 IOPS/GiB **rate** and overstates gp2 by 33× — a 100 GiB gp2 volume gets 300 baseline IOPS, not
10,000.

**gp3 is not universally faster — the crossover is 1,000 GiB.** gp2 reaches 3,000 baseline IOPS at
exactly 1,000 GiB and keeps climbing to 16,000 at 5,334 GiB. So:

- **Below ~1,000 GiB** → gp3 is cheaper *and* faster at baseline. Straight win, say so.
- **At or above ~1,000 GiB** → gp3 is still ~20% cheaper on storage, but its default 3,000 IOPS is a
  **downgrade**. Provision `iops: size × 3` (and matching throughput) on the gp3 volume to hold
  parity, and note that provisioned IOPS above the free 3,000 carry their own charge, which erodes
  part of the 20%. Do not present these as free wins.

Because gp2 also bursts to 3,000 IOPS below 1,000 GiB, a small volume that relies on **sustained**
burst is a genuine gp3 improvement (gp3's 3,000 is baseline, not a depleting credit balance) — worth
one sentence when the cluster's gp2 volumes are small.

**Criteria for opportunity:**
- Any gp2 volume or gp2 StorageClass exists → opportunity exists
- Split the finding by volume size at the 1,000 GiB crossover, using the sizes the detection printed

**Report as:**
- **Title:** Migrate gp2 volumes to gp3 for ~20% storage savings
- **Current State:** X gp2 volumes totalling Y GiB (list sizes; flag any ≥1,000 GiB separately)
- **Recommended State:** gp3 — default 3,000 IOPS / 125 MiB/s for volumes under 1,000 GiB; for
  volumes at or above 1,000 GiB, provision `iops = size × 3` to match the gp2 baseline
- **Estimated Savings:** ~20% of the gp2 storage line, minus any provisioned IOPS added above 3,000
- **Effort:** Easy — `modify-volume` is an online volume-type change, no downtime

---

## Opportunity 4: Idle Persistent Volume Cleanup (Tier 2 — Medium Impact)

**Detection:**
```bash
jq -r '.items[] | select(.status.phase == "Released" or .status.phase == "Available") | {name: .metadata.name, capacity: .spec.capacity.storage, phase: .status.phase}' "$WORK/pv.json"
jq -r -s '.[1].cluster.name as $cn | [.[0].Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0)|select(.State=="available")|{Id:.VolumeId,Size:.Size}]' "$WORK/volumes.json" "$WORK/cluster.json"
# Volume lists MUST be cluster-scoped. `describe-volumes` is collected region-wide with no
# filter, so an unscoped read names volumes owned by OTHER clusters as this cluster's savings —
# in the reference capture only 4 of 11 volumes carry a cluster tag.
```

**Analysis:** PVs in Released or Available state are not attached to any workload but still incur EBS charges.

**Criteria for opportunity:**
- If any PVs are in Released or Available state → opportunity exists

**Report as:**
- **Title:** Clean up idle Persistent Volumes
- **Current State:** X PVs in Released/Available state (Y GiB total)
- **Recommended State:** Delete unused PVs and their backing EBS volumes
- **Effort:** Easy (verify data is backed up, then delete)

---

## Opportunity 5: Container Rightsizing (Tier 2 — Medium Impact)

**Detection:**
```bash
# Workload containers only — AWS-managed kube-*/amazon-* pods are context, not the
# operator's to rightsize (matches the scope rule the pillar scorers use).
jq -r '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[] | {name: .name, requests_cpu: .resources.requests.cpu, requests_mem: .resources.requests.memory, limits_cpu: .resources.limits.cpu, limits_mem: .resources.limits.memory}]' "$WORK/pods.json"
```

Also check for deployments without HPA:
```bash
# Same workload-only scope as the pods query above: AWS-managed kube-*/amazon-* Deployments are
# not the operator's to rightsize, and recommending it for coredns is a false finding by this
# file's own rule.
jq -r '.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not) | {name: .metadata.name, ns: .metadata.namespace, replicas: .spec.replicas}' "$WORK/deployments.json"
jq -r '.items[] | {name: .spec.scaleTargetRef.name, ns: .metadata.namespace}' "$WORK/hpa.json"
```

**Analysis:**
- Containers with very high resource requests but low actual usage are over-provisioned
- Deployments with fixed replicas (no HPA) and replicas > 3 may be over-scaled

**Criteria for opportunity:**
- Deployments with >3 fixed replicas and no HPA → potential over-provisioning
- Containers where limits are >4x requests → may be over-provisioned

**Report as:**
- **Title:** Right-size container resources and enable autoscaling
- **Current State:** X deployments with fixed replicas, no HPA
- **Recommended State:** Deploy VPA for recommendations, add HPA for stateless workloads
- **Effort:** Medium (requires load testing to validate new values)

---

## Opportunity 6: Karpenter Adoption (Tier 3 — Quick Win)

**Detection:**
```bash
# Count JSON items, never `wc -l` on non-JSON: `kubectl get ... --no-headers` piped to
# `wc -l` returns 1 for an empty result under replay, so every cluster looked like it had
# Karpenter installed.
jq -r '[.items[]|select((.metadata.namespace//"")=="karpenter" or (.metadata.name|test("karpenter")))]|length' "$WORK/pods.json"
# Identify the autoscaler by IMAGE and app label, never by Deployment NAME — the same discipline
# Opportunity 3 applies to StorageClasses. A captured cluster has been seen with a Deployment
# NAMED `cluster-autoscaler` whose image is public.ecr.aws/karpenter/controller, so a name match
# reports "using Cluster Autoscaler" about a cluster already running Karpenter.
jq -r '[.items[]|{name:.metadata.name, ns:.metadata.namespace,
                  app:(.metadata.labels["app.kubernetes.io/name"]//""),
                  image:([.spec.template.spec.containers[]?.image]|join(","))}]
        |map(select((.image|test("karpenter"))or(.app=="karpenter")or(.image|test("cluster-autoscaler"))or(.app|test("cluster-autoscaler"))))' "$WORK/deployments.json"
# Auto Mode AND Fargate both make this a NON-finding: AWS already provisions the compute, so
# there is no in-cluster provisioner to adopt. (Fargate needs the nodes.json check — an earlier
# revision promised this guard in a comment but only implemented the Auto Mode half.)
jq -r -s '.[0] as $cl | .[1] as $n
  | if $cl.cluster.computeConfig.enabled==true then "AUTO MODE — node provisioning is AWS-managed; Karpenter adoption NOT APPLICABLE"
    elif (([$n.items[]?]|length)>0 and ([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")]|length)==([$n.items[]?]|length))
      then "FARGATE-ONLY — no EC2 capacity to provision; Karpenter adoption NOT APPLICABLE"
    else "standard/EC2 compute — Karpenter adoption applies" end' "$WORK/cluster.json" "$WORK/nodes.json"
```

**Analysis:** Check if Cluster Autoscaler is used instead of Karpenter.

**Criteria for opportunity:**
- If Cluster Autoscaler is deployed but Karpenter is not → opportunity exists
- Karpenter provides better bin-packing, faster scaling, and automatic instance type selection

**Report as:**
- **Title:** Migrate from Cluster Autoscaler to Karpenter
- **Current State:** Using Cluster Autoscaler with fixed instance types
- **Recommended State:** Deploy Karpenter for intelligent instance selection and better bin-packing
- **Effort:** Medium (requires NodePool configuration and CA removal)

---

## Opportunity 7: Extended Support Pricing (Tier 1 — High Impact)

**Detection:**
```bash
jq -r '{version: .cluster.version, supportType: .cluster.upgradePolicy.supportType}' "$WORK/cluster.json"
```

**Analysis:** Extended-support billing is driven by the **EKS release calendar**, not by the
`upgradePolicy.supportType` field. AWS: *"Billing for extended support starts at the beginning of
the day that the version reaches end of standard support."* `supportType: EXTENDED` is only the
opt-in that permits a cluster to *enter* extended support at that date instead of being
force-upgraded — a current-version cluster can carry `EXTENDED` and pay nothing.

So a cluster is being billed for extended support only if **today is on or after its version's
end-of-standard-support date**. End-of-standard-support dates (UTC+0), from the
[Kubernetes version lifecycle](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)
— re-check this table, it moves as versions ship:

| Version | End of standard support | Version | End of standard support |
|---|---|---|---|
| `1.28` | 2024-11-26 | `1.33` | 2026-07-29 |
| `1.29` | 2025-03-23 | `1.34` | 2026-12-02 |
| `1.30` | 2025-07-23 | `1.35` | 2027-03-27 |
| `1.31` | 2025-11-26 | `1.36` | 2027-08-02 |
| `1.32` | 2026-03-23 | | |

**Version not in the table?** If it is NUMERICALLY BELOW the lowest row, treat it as long past end
of standard support and raise the charge — do not fall silent, because that is the population most
likely to be genuinely billed. If it is above the highest row, the table is stale: re-check the
[lifecycle page](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html) before
asserting anything.

When billing applies, the surcharge is $0.60/hr vs $0.10/hr standard = ~$365/month extra.

**Criteria for opportunity:**
- Version's end-of-standard-support date has passed → opportunity exists (bill is being incurred now)
- Date is within ~3 months → raise as an **upgrade-planning** item, NOT a cost finding. Word it as
  *"Kubernetes \<version\> reaches end of standard support on \<date\> (N days); plan the upgrade
  before then"*. Do **not** write "Extended Support pricing", do **not** quote an hourly rate, and
  do **not** state a saving — no charge is being incurred yet, and naming the billed state reads to
  a customer as though it already applies. The charge belongs in the report only once the date has
  passed.
- Date is further out → **no finding**, regardless of `supportType`. Claiming a saving here invents
  money the customer is not spending, which is worse than missing a real one.

**Report as (only when the date has passed):**
- **Title:** Upgrade cluster to exit Extended Support pricing
- **Current State:** Cluster on Kubernetes <version>, past end of standard support (<date>), billed at $0.60/hr
- **Recommended State:** Upgrade to a version still in standard support, at $0.10/hr
- **Estimated Savings:** ~$365/month
- **Effort:** Medium (plan and execute Kubernetes version upgrade)

---

## Cost Score Calculation (NON-AUTHORITATIVE — do not print this as "the cost score")

> **This table is not the Cost Optimization pillar score and is computed by nothing.**
> The authoritative Cost score is produced by the Step 7 reducer from the measured
> `cost-*`/`lens-*` questions in `cost-optimization.md`. This rubric predates that reducer
> and disagrees with it (a Graviton+Spot cluster scores far higher here than its measured
> pillar). Use it only as a qualitative checklist when writing the narrative; never emit a
> number from it, and never present two different cost scores in one report.

Score the cluster's cost efficiency across these dimensions (total 100):

| Dimension | Max Points | How to Score |
|-----------|-----------|--------------|
| Graviton adoption | 20 | (graviton_nodes / total_nodes) × 20 |
| Spot adoption | 15 | (spot_nodegroups / total_nodegroups) × 15 |
| Node utilization | 15 | If CPU requests/capacity is 50-85%: 15, ≥30%: 10, else: 5 |
| Storage efficiency | 10 | No gp2: 10, has gp2: 5 |
| Autoscaling coverage | 10 | (HPAs / deployments) × 10 |
| Savings Plans/RI | 10 | Default 5 (can't detect from cluster) |
| Resource request accuracy | 10 | (containers_with_requests / total_containers) × 10 |
| No idle resources | 5 | No idle PVs: 5, has idle: 2 |
| Network efficiency | 5 | Default 3 (topology routing helps) |

---

## Presenting Cost Opportunities

Report cost findings with this structure:

### 🔴 High Impact — Act Now (Tier 1)
[Extended support, Graviton, Spot]

### 🟡 Medium Impact — Plan This Quarter (Tier 2)
[gp2→gp3, idle PVs, rightsizing]

### 🟢 Quick Wins — Low Effort (Tier 3)
[Karpenter, topology routing]

For each opportunity:
- Title
- Effort level (Easy/Medium/Hard)
- Current state (what was observed)
- Target state (recommendation)
- Affected resources (list specific nodes/volumes/deployments)
- Implementation steps
