# 💰 Cost Optimization Analysis

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

Identify cost savings opportunities from cluster data. Prioritized by impact tier and implementation effort.

---

## Table of Contents

1. [Opportunity 1: Graviton Migration (Tier 1 — High Impact)](#opportunity-1-graviton-migration-tier-1--high-impact)
2. [Opportunity 2: Spot Instance Adoption (Tier 1 — High Impact)](#opportunity-2-spot-instance-adoption-tier-1--high-impact)
3. [Opportunity 3: gp2 to gp3 Storage Migration (Tier 2 — Medium Impact)](#opportunity-3-gp2-to-gp3-storage-migration-tier-2--medium-impact)
4. [Opportunity 4: Idle Persistent Volume Cleanup (Tier 2 — Medium Impact)](#opportunity-4-idle-persistent-volume-cleanup-tier-2--medium-impact)
5. [Opportunity 5: Container Rightsizing (Tier 2 — Medium Impact)](#opportunity-5-container-rightsizing-tier-2--medium-impact)
6. [Opportunity 6: Karpenter Adoption (Tier 3 — Quick Win)](#opportunity-6-karpenter-adoption-tier-3--quick-win)
7. [Opportunity 7: Extended Support Pricing (Tier 1 — High Impact)](#opportunity-7-extended-support-pricing-tier-1--high-impact)
8. [Cost Score Calculation (NON-AUTHORITATIVE — do not print this as "the cost score")](#cost-score-calculation-non-authoritative--do-not-print-this-as-the-cost-score)
9. [Presenting Cost Opportunities](#presenting-cost-opportunities)
   - [🔴 High Impact — Act Now (Tier 1)](#-high-impact--act-now-tier-1)
   - [🟡 Medium Impact — Plan This Quarter (Tier 2)](#-medium-impact--plan-this-quarter-tier-2)
   - [🟢 Quick Wins — Low Effort (Tier 3)](#-quick-wins--low-effort-tier-3)

---

## Opportunity 1: Graviton Migration (Tier 1 — High Impact)

**Detection:**
```bash
# EC2 capacity only. Fargate nodes carry NO instance-type label (they would read as
# `null`, which naively counts as "not Graviton"), and EKS Auto Mode provisions nodes
# AWS-side. A cluster with no EC2 capacity has nothing to migrate.
# EKS Hybrid Nodes are excluded for a second reason as well as the first: Graviton is AWS
# silicon, and an on-premises ARM machine reports `kubernetes.io/arch=arm64` truthfully while
# being hardware the customer already bought — crediting it as Graviton adoption, or billing it
# as an x86 node to migrate, are both fabrications. `ishy` is the same predicate the scorers use
# (`references/*.md`, the `B='def b(...)'` prelude), and it is NOT the label OR the providerID: the
# providerID decides and the label only breaks a tie. `eks-hybrid:` means hybrid, an `aws:` providerID
# VETOES the label (a node AWS says is an EC2 instance is one, whatever it is labelled), and the label
# is consulted only when no providerID contradicts it. Under OR, labelling two real EC2 nodes
# `compute-type=hybrid` would drop them out of every node question -- an evasion path, not a synonym.
# Windows nodes are excluded as well, and counted: this skill supports Linux nodes only. `iswin` is the
# scorers' predicate too -- the `kubernetes.io/os` label, or the kubelet's `operatingSystem` when the
# label is absent.
jq -r 'def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end;
  def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows";
  [.items[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not))] as $all | ([$all[]|select(iswin)]|length) as $w
  | [$all[]|select(iswin|not)] as $ec2
  | if ($ec2|length)==0 and $w>0 then "NO LINUX EC2 CAPACITY — Graviton migration is NOT APPLICABLE"+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end)
    elif ($ec2|length)==0 then "NO EC2 CAPACITY — Graviton migration is NOT APPLICABLE"
    else ($ec2|map(.metadata.labels["node.kubernetes.io/instance-type"]//"unlabelled")
               |group_by(.)|map({(.[0]):length})|add|tostring)+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end) end' "$WORK/nodes.json"
jq -r 'if .cluster.computeConfig.enabled==true then "AUTO MODE — AWS selects instance types; recommend arm64-compatible workloads + a NodePool architecture requirement, NOT a node migration" else "not Auto Mode (customer-managed compute)" end' "$WORK/cluster.json"
```

**Split arm64 from x86 by reading the node's architecture, not by parsing its instance type:**

```bash
# kubernetes.io/arch is set by the kubelet from the machine it is running on. It is authoritative and
# already collected, so no name matching is needed and no allowlist can go stale.
# Windows nodes are left out of both numbers: this skill supports Linux nodes only, so an x86 Windows
# node is counted as not assessed, never as migratable.
jq -r 'def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end;
  def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows";
  [.items[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not))] as $all | ([$all[]|select(iswin)]|length) as $w
  | [$all[]|select(iswin|not)] as $ec2
  | ($ec2|length) as $t
  | ([$ec2[]|select(.metadata.labels["kubernetes.io/arch"]=="arm64")]|length) as $arm
  | if $t==0 and $w>0 then "NO LINUX EC2 CAPACITY"+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end)
    elif $t==0 then "NO EC2 CAPACITY"
    else "\($arm)/\($t) Linux EC2 nodes on arm64 (Graviton); \($t-$arm) on x86 and migratable"+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end) end' "$WORK/nodes.json"
```

**Do not classify by instance name.** An instruction such as "Graviton families carry a `g` in
the generation suffix — `m7g`, `c7g`, `r7g`, `m8g`, `c8g`, `m6g`, `c6g`, `t4g`. Anything else on EC2 is
x86" is a closed list applied by judgment, which is the opposite of how the rest of this skill
decides anything, and it is wrong in three ways. If you ever do need to reason from a name, AWS's
[naming convention](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-type-names.html)
splits a type into **series → generation → options → size** (`c7gn.xlarge` = series `c`, generation `7`,
options `gn`, size `xlarge`), and:

| Trap | Example | Why the closed list or a naive "contains `g`" gets it wrong |
|---|---|---|
| A **new** Graviton generation | `m9g` | Not on the list, so read as x86 — the list needs editing every generation. |
| Series `G` is **Graphics**, not Graviton | `g5`, `g6e` | The `g` is the *series*, meaning "graphics intensive" — these are NVIDIA GPU instances on x86 hosts. A "contains `g`" rule calls them Graviton. |
| Series `A` **is** Graviton, with no `g` | `a1` | "Powered by Arm-based AWS Graviton processors" per AWS, but there is no `g` anywhere in the name. |

`g` means Graviton only in the **options** position. Reading `kubernetes.io/arch` avoids all of this.

**Raise this whenever ANY x86 EC2 capacity remains.** It is the single largest compute lever the
skill can act on that is not workload-dependent: unlike Spot it costs nothing in availability, and
unlike a version upgrade it is not time-boxed. Same vCPU, same memory, lower hourly rate, and
typically equal or better throughput per core. Treat "we have not looked at Graviton" as the default
state to challenge, not as a preference to respect.

**Get the saving from the Price List API, do not quote a fixed percentage.** The command, so this is an
instruction and not an aspiration:

```bash
# On-Demand $/hr for one instance type in one region. Repeat for the x86 type and its Graviton peer.
aws pricing get-products --service-code AmazonEC2 --region us-east-1 \
  --filters Type=TERM_MATCH,Field=instanceType,Value=<TYPE> \
            Type=TERM_MATCH,Field=regionCode,Value=<REGION> \
            Type=TERM_MATCH,Field=operatingSystem,Value=Linux \
            Type=TERM_MATCH,Field=tenancy,Value=Shared \
            Type=TERM_MATCH,Field=preInstalledSw,Value=NA \
            Type=TERM_MATCH,Field=capacitystatus,Value=Used \
  --query 'PriceList[0]' --output text \
  | jq -r '.terms.OnDemand|to_entries[0].value.priceDimensions|to_entries[0].value.pricePerUnit.USD'
```

The Price List API is served from three endpoints only — `us-east-1`, `ap-south-1` and `eu-central-1`
([service endpoints](https://docs.aws.amazon.com/general/latest/gr/billing.html),
[price change notifications](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html))
— which is why a fixed `--region us-east-1` is used above while the *priced* region goes in `regionCode`.
Any of the three works; the endpoint you call does not change the answer. If the call is unavailable,
say the percentage is unverified rather than quoting the example table below. The commonly quoted
"~20%" is the **Graviton2** delta; Graviton3 (`m7g`/`c7g`) is nearer **15%**, and Graviton4
(`m8g`/`c8g`, the newest generation offered in `ap-southeast-5`) is nearer **6.5%** against the same
x86 6th-generation pair (`m8g.large` $0.09538 and `c8g.large` $0.07788 in `ap-southeast-5`).
Verified live in `ap-southeast-5` (Price List, published 2026-09-25). This is a price table for every
Graviton generation the region offers at this size, not a recommendation: the row marked **recommended** is
the one the Recommended State rule below picks, the newest generation still cheaper than the x86 type.

| From (x86) | To (Graviton) | Hourly | Delta |
|---|---|---|---|
| `m6i.large` $0.1020 | `m8g.large` $0.09538 (Gen4, **recommended**) | −$0.00662 | **−6.5%** |
| `m6i.large` $0.1020 | `m7g.large` $0.0867 (Gen3) | −$0.0153 | −15.0% |
| `m6i.large` $0.1020 | `m6g.large` $0.0816 (Gen2) | −$0.0204 | −20.0% |
| `c6i.large` $0.0833 | `c8g.large` $0.07788 (Gen4, **recommended**) | −$0.00542 | **−6.5%** |
| `c6i.large` $0.0833 | `c7g.large` $0.0708 (Gen3) | −$0.0125 | −15.0% |
| `c6i.large` $0.0833 | `c6g.large` $0.0666 (Gen2) | −$0.0167 | −20.0% |

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
- **Current State:** X of Y Linux EC2 nodes on x86 (list the types and their hourly rate)
- **Recommended State:** the same **series** and **size**, with `g` in the **options** position and the
  **newest** Graviton **generation** the region offers whose hourly rate is still below the current
  type's: `m6i.large` → `m<gen>g.large`. List the generations the region offers (below), price each one
  with the command above, and walk them from newest to oldest; recommend the first one that is cheaper
  than the current type. Not simply the newest — the newest can cost more than the x86 type it
  replaces — and not simply the cheapest, which is usually the oldest generation. Against `m6i.large`
  ($0.0960) in `us-east-1` (Price List, read 2026-09-29), `m9g.large` is $0.09784 (+1.9%), so the rule
  passes over it to `m8g.large` at $0.08976 (−6.5%), although `m7g.large` ($0.0816, −15.0%) and
  `m6g.large` ($0.0770, −19.8%) are cheaper still. In `ap-southeast-5`, which offers no `m9g`, the
  rule picks `m8g.large` ($0.09538 against $0.1020, −6.5%). If no offered generation is cheaper than
  the current type, report no saving for that type rather than a negative one. Quote the delta of the
  pair you recommend. Do not carry a fixed map
  (`m6i`→`m7g`, `c6i`→`c7g`) in your head: that is the closed list this section just argued against, and
  it goes stale the day a generation ships. Quote the region's real hourly delta alongside it.

  ```bash
  # Which Graviton generations of this series and size does the region offer? Ask; don't assume.
  # Substitute the series letter and size from the node you are migrating.
  aws ec2 describe-instance-type-offerings --location-type region --region <REGION> \
    --filters Name=instance-type,Values='m*g.large' \
    --query 'InstanceTypeOfferings[].InstanceType' --output text
  ```

  Price every generation returned and take the newest one that is cheaper than the current type. The rule holds across series, including the ones the trap table
  warns about: `g5g` is series `g` (graphics), generation `5`, options `g` — a Graviton GPU instance —
  so the `g`-in-options test is what distinguishes it from the x86 `g5`. Options also carry `d` (local
  NVMe) and `n` (extra network); keep whichever the current type has if the workload depends on it.
- **Estimated Savings:** (x86 rate − rate of the recommended Graviton type) × node count × 730, shown as $/month
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
# `karpenter.sh/capacity-type` (`on-demand`, not `ON_DEMAND`, so the value is upcased and `-`
# becomes `_` to keep On-Demand in one bucket). Reading only the first bucketed genuinely-Spot
# nodes as UNKNOWN, understating existing Spot adoption and inviting a fabricated saving.
# EKS Hybrid Nodes are excluded: Spot is an EC2 purchase option, neither capacity label is set on a
# hybrid node, so counting one would bucket it UNKNOWN or On-Demand and understate Spot adoption
# against a machine that can never be Spot.
# Windows nodes are excluded and counted: this skill supports Linux nodes only.
jq -r 'def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end;
  def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows";
  [.items[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not))] as $all | ([$all[]|select(iswin)]|length) as $w
  | [$all[]|select(iswin|not)]
  | if length==0 and $w>0 then "NO LINUX EC2 CAPACITY — Spot adoption is NOT APPLICABLE"+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end)
    elif length==0 then "NO EC2 CAPACITY — Spot adoption is NOT APPLICABLE"
    else (map((.metadata.labels["eks.amazonaws.com/capacityType"]
               // .metadata.labels["karpenter.sh/capacity-type"] // "UNKNOWN")|ascii_upcase|gsub("-";"_"))
          |group_by(.)|map({(.[0]):length})|add|tostring)+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end) end' "$WORK/nodes.json"
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
serverless cluster cannot fall through into a recommendation it cannot act on. Windows nodes, and the
Deployments and StatefulSets whose pod template targets Windows (`spec.os.name`, or a nodeSelector or required
node affinity that admits Windows and no Linux node on `[beta.]kubernetes.io/os` or `node.kubernetes.io/windows-build`), are left out and
counted: this skill supports Linux nodes only.

```bash
jq -r -s 'def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end;
  def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows";
  def iswinspec: ((.os.name // "")=="windows") or ((.nodeSelector["kubernetes.io/os"] // "")=="windows") or ((.nodeSelector["beta.kubernetes.io/os"] // "")=="windows") or (.nodeSelector["node.kubernetes.io/windows-build"] != null) or (((.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms)//[]) as $ts|(($ts|length)>0) and ($ts|any(.[]; any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|any(.[]; .=="windows")) and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux")) and ($v|all(.[]; . != "windows"))))) or (($k=="node.kubernetes.io/windows-build") and ((($o=="In") and (($v|length)>0)) or ($o=="Exists"))))))) and ($ts|all(.[]; ((((.matchExpressions//[])|length)==0) and (((.matchFields//[])|length)==0)) or any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux"))) or ($o=="DoesNotExist"))) or (($k=="node.kubernetes.io/windows-build") and (($o=="In") or ($o=="Exists"))))))));
  .[0] as $d|.[1] as $s|.[2] as $n
  | [$n.items[]?|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not))] as $all | ([$all[]|select(iswin)]|length) as $w
  | [$all[]|select(iswin|not)] as $ec2
  | if ($ec2|length)==0 and $w>0 then "NO LINUX EC2 CAPACITY — Spot readiness is NOT APPLICABLE"+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end)
    elif ($ec2|length)==0 then "NO EC2 CAPACITY — Spot readiness is NOT APPLICABLE" else
    ([$d.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $dall
    | [$s.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $sall
    | ([$dall[],$sall[]|select(.spec.template.spec|iswinspec)]|length) as $ww
    | [$dall[]|select(.spec.template.spec|iswinspec|not)] as $dep
    | [$dep[]|select(((.spec.replicas//1)>=2) and ((((.spec.template.spec.volumes//[])|map(select(.persistentVolumeClaim//empty)))|length)==0))|.metadata.namespace+"/"+.metadata.name] as $ready
    | [$dep[]|select(((.spec.replicas//1)<2) or ((((.spec.template.spec.volumes//[])|map(select(.persistentVolumeClaim//empty)))|length)>0))|.metadata.namespace+"/"+.metadata.name] as $hold
    | [$sall[]|select(.spec.template.spec|iswinspec|not)|.metadata.namespace+"/"+.metadata.name] as $sts
    | "SPOT-READY TODAY (>=2 replicas, no PVC): \($ready|length) \($ready)",
      "NOT YET SPOT-SAFE (single replica or PVC-backed): \($hold|length) \($hold)",
      "STATEFULSETS (keep On-Demand unless the app tolerates node loss): \($sts|length) \($sts)",
      (if $w>0 then "WINDOWS NODES (not assessed — this skill supports Linux nodes only): \($w)" else empty end),
      (if $ww>0 then "WINDOWS WORKLOADS (Deployments/StatefulSets targeting Windows, not assessed — this skill supports Linux nodes only): \($ww)" else empty end))
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
  PDBs, and handle the 2-minute notice: the AWS Node Termination Handler on self-managed nodes only.
  Managed node groups and Auto Mode drain Spot nodes themselves, and Karpenter has its own
  interruption handling (an SQS queue), which AWS advises against running alongside the Handler
- **Do not recommend for:** the StatefulSets and single-replica Deployments listed above

---

## Opportunity 3: gp2 to gp3 Storage Migration (Tier 2 — Medium Impact)

**Detection:**
```bash
# NB: compare the StorageClass `parameters.type`, never its NAME — nothing stops a class
# named `gp3` from provisioning gp2, or a class named `gp2` from provisioning gp3.
jq -r '.items[] | {name: .metadata.name, provisioner: .provisioner, type: .parameters.type}' "$WORK/storageclasses.json"
jq -r -s '.[1].cluster.name as $cn | [.[0].Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0)|select(.VolumeType=="gp2")|{Id:.VolumeId,Size:.Size,State:.State}]' "$WORK/volumes.json" "$WORK/cluster.json"
```

**Analysis:** Check for gp2 volumes or StorageClasses still using gp2.

**The performance comparison — get this right; confusing gp2's floor with its rate is off by 33×.**

| | gp2 | gp3 |
|---|---|---|
| Baseline IOPS | **3 IOPS/GiB**, minimum 100, maximum 16,000 | flat **3,000**, any size |
| Baseline throughput | up to 128 MiB/s at 170 GiB and smaller; bursts to 250 MiB/s above 170 GiB; 250 MiB/s at 334 GiB and larger | flat **125 MiB/s**, any size |
| Burst | to 3,000 IOPS below 1,000 GiB | none — baseline is not a credit pool |
| Price | ~$0.10/GiB-mo | ~$0.08/GiB-mo (**~20% less**) |

**Price row verified live** in `us-east-1` via the AWS Price List API, 2026-09-11: gp2 $0.100/GiB-mo,
gp3 $0.080/GiB-mo — exactly 20% less. Prices are per-region and change over time; re-check before
quoting, the same discipline Opportunity 1 applies to the Graviton percentage:
```bash
aws pricing get-products --service-code AmazonEC2 --region us-east-1 \
  --filters Type=TERM_MATCH,Field=volumeApiName,Value=<gp2-or-gp3> \
            Type=TERM_MATCH,Field=regionCode,Value=<REGION> \
            Type=TERM_MATCH,Field=productFamily,Value=Storage \
  --query 'PriceList[0]' --output text \
  | jq -r '.terms.OnDemand|to_entries[0].value.priceDimensions|to_entries[0].value.pricePerUnit.USD'
```

Do not write *"3000 IOPS vs 100 IOPS/GiB"*: that confuses gp2's 100-IOPS **floor** with
its 3 IOPS/GiB **rate** and overstates gp2 by 33× — a 100 GiB gp2 volume gets 300 baseline IOPS, not
10,000.

**gp3 is not universally faster — the IOPS crossover is 1,000 GiB, and the `size × 3` parity formula has its
own ceiling.** gp2 reaches 3,000 baseline IOPS at exactly 1,000 GiB and keeps climbing — but **gp2's
baseline stops climbing at 16,000 IOPS, reached at 5,334 GiB, and every larger gp2 volume gets the same
16,000** ([EBS User Guide, General Purpose SSD volumes](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html),
verified live 2026-09-11). So:

- **Below ~1,000 GiB** → gp3 is cheaper and matches or beats gp2 on baseline IOPS. Throughput is the
  exception: gp3's default 125 MiB/s is below the 250 MiB/s a gp2 volume of 334 GiB or larger sustains,
  so provision `throughput: 250` on those volumes to hold parity. Between 170 and 334 GiB gp2 reaches
  250 MiB/s only by burst, and gp3 throughput above 125 MiB/s costs about $0.04 per MiB/s-month
  (`us-east-1`; region-dependent), so the extra 125 MiB/s (about $5/month) costs more than the storage
  saving below about 250 GiB — provision it there only where the workload needs sustained throughput.
- **1,000 GiB up to 5,334 GiB** → gp3 is still ~20% cheaper on storage, but its default 3,000 IOPS is a
  **downgrade**. Provision `iops: size × 3` (and matching throughput) on the gp3 volume to hold parity,
  and note that provisioned IOPS above the free 3,000 carry their own charge, which erodes part of the
  20%. Do not present these as free wins.
- **5,334 GiB and larger** → cap it: provision `iops: 16000` flat, never `size × 3`. Past this size the
  uncapped formula asks gp3 for more IOPS than gp2 ever delivered — an 8,192 GiB volume would request
  24,576 IOPS against gp2's real ceiling of 16,000, over-paying by roughly **$43/month** at gp3's
  provisioned-IOPS rate of $0.005/IOPS-month (`us-east-1`, AWS Price List API, verified live 2026-09-11),
  rising to roughly **$166/month** at gp2's own 16 TiB size limit. From 1,000 GiB up, the net gp2→gp3
  saving stays positive at every size, the `throughput: 250` charge included and `size × 3` left uncapped
  or not. The over-payment alone takes about 26% at 8 TiB and 51% at 16 TiB of the ~20% storage-only
  saving, on top of the charge for the IOPS gp2 did deliver, but never inverts it into a loss.

Because gp2 also bursts to 3,000 IOPS below 1 TiB (1,024 GiB — AWS states the burst boundary in TiB; the ~1,000 GiB figure used here is the round number where baseline IOPS crosses 3,000, which is close but not the documented threshold), a small volume that relies on **sustained**
burst is a genuine gp3 improvement (gp3's 3,000 is baseline, not a depleting credit balance) — worth
one sentence when the cluster's gp2 volumes are small.

**Criteria for opportunity:**
- Any gp2 volume or gp2 StorageClass exists → opportunity exists
- Split the finding by volume size at the 1,000 GiB **and** 5,334 GiB crossovers, using the sizes the
  detection printed

**Report as:**
- **Title:** Migrate gp2 volumes to gp3 for ~20% storage savings
- **Current State:** X gp2 volumes totalling Y GiB (list sizes; flag any ≥1,000 GiB separately)
- **Recommended State:** gp3 — default 3,000 IOPS for volumes under 1,000 GiB, plus `throughput: 250`
  for volumes of 334 GiB and larger (from 170 to 334 GiB only where the workload needs sustained
  throughput, since gp2's 250 MiB/s there is burst only; default 125 MiB/s otherwise); `iops = size
  × 3` for volumes from 1,000 GiB up to 5,334 GiB; `iops = 16000` (gp2's own ceiling, never `size × 3`)
  for volumes 5,334 GiB and larger
- **Estimated Savings:** ~20% of the gp2 storage line, minus any provisioned IOPS added above 3,000 and
  any throughput provisioned above 125 MiB/s (about $0.04 per MiB/s-month in `us-east-1`) — and minus
  the excess IOPS charge if `size × 3` was provisioned uncapped past 5,334 GiB
- **Effort:** Easy — `modify-volume` is an online volume-type change, no downtime

---

## Opportunity 4: Idle Persistent Volume Cleanup (Tier 2 — Medium Impact)

**Detection:**
```bash
jq -r '.items[] | select(.status.phase != "Bound") | {name: .metadata.name, capacity: .spec.capacity.storage, phase: .status.phase}' "$WORK/pv.json"
jq -r -s '.[1].cluster.name as $cn | ([.[2].items[]?|(.spec.csi.volumeHandle?,.spec.awsElasticBlockStore.volumeID?)]|map(select((type=="string") and .!="")|split("/")|last)|unique) as $pvid | [.[0].Volumes[]?|select(([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0) or ((.VolumeId//"")|IN($pvid[])))|select((.State!="in-use") and (.State!="error") and (.State!="deleted"))|{Id:.VolumeId,Size:.Size,State:.State}]' "$WORK/volumes.json" "$WORK/cluster.json" "$WORK/pv.json"
# THESE TWO QUERIES MUST AGREE WITH `cost-6` AND `cost-8` in references/cost-optimization.md, and
# they are written to return the same objects those scorers put in `resources.fail`. Both test
# POSITIVELY and report the complement, for the reason those scorers give: `Bound` is the only PV
# phase that is serving a claim and `in-use` is the only volume state that is attached, so a
# denylist of `Released`/`Available` misses a PV whose reclamation FAILED -- the longest-lived PV
# leak, with nothing to clear it. `error` (failed EBS hardware, not billed) and `deleted` volumes are
# excluded, as `cost-8` excludes them. On a 4-PV / 6-volume shape the denylist forms `phase ==
# "Released" or "Available"` and `State == "available"` both return NOTHING while the scorers
# fail a 500Gi `Failed` PV, a 200Gi `Pending` PV and a 100 GiB `creating` volume. `creating`/`deleting`
# are transient and normally clear on their own; treat a volume that stays there as real.
# Volume lists MUST be cluster-scoped. `describe-volumes` is collected region-wide with no
# filter, so an unscoped read names volumes owned by OTHER clusters as this cluster's savings —
# in a shared region most volumes can belong to other clusters. The tag predicate is
# `cost-8`'s and `sec-21`'s, which bind the cluster NAME to a cluster-ish KEY: a bare
# `.Value==$cn` would accept an unrelated volume merely tagged
# `Name=<cluster>`. On a shape carrying one such volume the bare form
# reports 5 volumes where the scorers report 4, claiming 900 GiB of someone else's disk as this
# cluster's saving. An ordinary cluster rarely carries such a tag, so only a hostile shape
# shows it — which is why the form is copied from the scorer rather than re-derived.
```

**Analysis:** PVs in any phase other than `Bound` — `Released`, `Available`, `Failed` or `Pending` — are serving no claim; the EBS volume behind a `Released` or `Failed` one still exists and still bills.

**Criteria for opportunity:**
- If any PVs are not `Bound` → opportunity exists

**Report as:**
- **Title:** Clean up idle Persistent Volumes
- **Current State:** X PVs not Bound (Y GiB total)
- **Recommended State:** Delete unused PVs and their backing EBS volumes
- **Effort:** Easy (verify data is backed up, then delete)

---

## Opportunity 5: Container Rightsizing (Tier 2 — Medium Impact)

**Detection:**
```bash
# Workload containers only — AWS-managed kube-*/amazon-* pods are context, not the
# operator's to rightsize (matches the scope rule the pillar scorers use). Windows pods (`spec.os.name`,
# a nodeSelector or required node affinity admitting Windows and no Linux node on `[beta.]kubernetes.io/os` or `node.kubernetes.io/windows-build`, on the
# pod or its DaemonSet's template) are left out and counted: this skill supports Linux nodes only.
jq -r 'def iswinspec: ((.os.name // "")=="windows") or ((.nodeSelector["kubernetes.io/os"] // "")=="windows") or ((.nodeSelector["beta.kubernetes.io/os"] // "")=="windows") or (.nodeSelector["node.kubernetes.io/windows-build"] != null) or (((.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms)//[]) as $ts|(($ts|length)>0) and ($ts|any(.[]; any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|any(.[]; .=="windows")) and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux")) and ($v|all(.[]; . != "windows"))))) or (($k=="node.kubernetes.io/windows-build") and ((($o=="In") and (($v|length)>0)) or ($o=="Exists"))))))) and ($ts|all(.[]; ((((.matchExpressions//[])|length)==0) and (((.matchFields//[])|length)==0)) or any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux"))) or ($o=="DoesNotExist"))) or (($k=="node.kubernetes.io/windows-build") and (($o=="In") or ($o=="Exists")))))))); def winds: [.items[]?|select((.spec.template.spec//{})|iswinspec)|{key:((.metadata.namespace//"")+"/"+(.metadata.name//"")),value:true}]|from_entries; def iswinpod($w): (.spec|iswinspec) or ((.metadata.namespace//"") as $ns|any(.metadata.ownerReferences[]?; ((.kind//"")=="DaemonSet") and ($w[$ns+"/"+(.name//"")]//false))); (input|winds) as $wds|
  [.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $wl
  | ([$wl[]|select(iswinpod($wds))]|length) as $wp
  | [$wl[]|select(iswinpod($wds)|not)|.spec.containers[] | {name: .name, requests_cpu: .resources.requests.cpu, requests_mem: .resources.requests.memory, limits_cpu: .resources.limits.cpu, limits_mem: .resources.limits.memory}],
    (if $wp>0 then "\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only" else empty end)' "$WORK/pods.json" "$WORK/daemonsets.json"
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
# `wc -l` counts any line that comes back, a message or a blank one included, so a cluster can
# look like it has Karpenter installed when it does not.
jq -r '[.items[]|select((.metadata.namespace//"")=="karpenter" or (.metadata.name|test("karpenter")))]|length' "$WORK/pods.json"
# Identify the autoscaler by IMAGE and app label, never by Deployment NAME — the same discipline
# Opportunity 3 applies to StorageClasses. Nothing stops a Deployment being
# NAMED `cluster-autoscaler` while its image is public.ecr.aws/karpenter/controller, so a name match
# reports "using Cluster Autoscaler" about a cluster already running Karpenter.
jq -r '[.items[]|{name:.metadata.name, ns:.metadata.namespace,
                  app:(.metadata.labels["app.kubernetes.io/name"]//""),
                  image:([.spec.template.spec.containers[]?.image]|join(","))}]
        |map(select((.image|test("karpenter"))or(.app=="karpenter")or(.image|test("cluster-autoscaler"))or(.app|test("cluster-autoscaler"))))' "$WORK/deployments.json"
# Auto Mode AND Fargate both make this a NON-finding: AWS already provisions the compute, so
# there is no in-cluster provisioner to adopt. (Fargate needs the nodes.json check; the Auto Mode
# test alone is only half of this guard.) Windows nodes are not assessed -- this skill supports Linux
# nodes only -- so a cluster whose only non-Fargate nodes are Windows gets no Karpenter recommendation,
# and a mixed one says how many Windows nodes the recommendation does not cover.
jq -r -s 'def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows";
  .[0] as $cl | .[1] as $n
  | ([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")] as $nf | [$nf[]|select(iswin)]|length) as $w
  | ([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $nfn
  | if $cl.cluster.computeConfig.enabled==true then "AUTO MODE — node provisioning is AWS-managed; Karpenter adoption NOT APPLICABLE"
    elif (([$n.items[]?]|length)>0 and ([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")]|length)==([$n.items[]?]|length))
      then "FARGATE-ONLY — no EC2 capacity to provision; Karpenter adoption NOT APPLICABLE"
    elif ($w>0 and $w==$nfn) then "WINDOWS NODES ONLY — \($w) Windows node(s) not assessed (this skill supports Linux nodes only); Karpenter adoption NOT ASSESSED"
    else "standard/EC2 compute — Karpenter adoption applies"+(if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end) end' "$WORK/cluster.json" "$WORK/nodes.json"
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

When billing applies, the surcharge is $0.60/hr vs $0.10/hr standard = ~$365/month extra. **Verified
live** via the AWS Price List API, 2026-09-11: `AmazonEKS` standard cluster usage is $0.10/hr and the
`extendedSupport` line item is $0.50/hr **on top of** the standard charge (both continue to be billed),
for a combined $0.60/hr — consistent in both `us-east-1` and `ap-southeast-5`. This is an AWS list price
that can be repriced; re-check it with `aws pricing get-products --service-code AmazonEKS --filters
Type=TERM_MATCH,Field=usagetype,Value=<REGION-PREFIX>-AmazonEKS-Hours:extendedSupport` before quoting a
dollar figure to a customer, rather than carrying this number forward from memory.

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
- **Current State:** Cluster on Kubernetes <version>, past end of standard support (<date>), billed at
  $0.60/hr (rate verified live 2026-09-11 — re-check via the Price List API above before quoting; do not
  carry this figure forward without re-checking on a later run)
- **Recommended State:** Upgrade to a version still in standard support, at $0.10/hr (same as-of date)
- **Estimated Savings:** ~$365/month (derived from the two rates above; re-derive if either changes)
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
