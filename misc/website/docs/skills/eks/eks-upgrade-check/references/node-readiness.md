---
title: "Node Readiness"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-upgrade-check/references/node-readiness.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-upgrade-check/references/node-readiness.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-upgrade-check/references/node-readiness.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [eks-upgrade-check](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-upgrade-check), also maintained by the APEX team.
:::

# Node Readiness

## Purpose
Assess node groups, AMI types, version alignment, and migration requirements for the target version.

## Checks to Execute

### 5.1 — Node Group Inventory

**How to check:**
1. List all managed node groups → describe each for:
   - Kubernetes version
   - AMI type (AL2, AL2023, AL2_ARM_64, BOTTLEROCKET_x86_64, etc.)
   - Instance types
   - Scaling config (min/max/desired)
   - Update config (`updateStrategy`, `maxUnavailable` or `maxUnavailablePercentage`)
   - Capacity type (ON_DEMAND, SPOT)
   - Health status
2. List nodes via Kubernetes API → get:
   - `status.nodeInfo.kubeletVersion`
   - `status.nodeInfo.osImage`
   - `status.nodeInfo.kernelVersion`
   - `status.nodeInfo.containerRuntimeVersion`
   - Labels: `topology.kubernetes.io/zone`, `node.kubernetes.io/instance-type`
3. Check for Karpenter NodePools (`nodepools.karpenter.sh`)
4. Check for EKS Auto Mode (`computeConfig` in cluster describe)

> **Nodegroup mid-rotation gate:** check each managed node group's lifecycle `status`
> (from `eks:DescribeNodegroup` — already in the IAM policy, no new permission). If any
> node group `status == UPDATING`, flag the whole assessment as **potentially unstable**:
> a node group mid-rotation returns a mixed old/new node snapshot, so the Kubernetes-API
> reads above (kubelet version, OS image, container runtime) may reflect a transient blend
> of pre- and post-rotation nodes. Note this in the report and recommend re-running the
> assessment after the rotation completes. (`health.issues` can be empty during a healthy
> mid-rotation, so it does not catch this — the lifecycle `status` field does.)

**Output per node group:**
- Name, version, AMI type, instance types, scaling config
- Version skew against target (calculated in version-validation)

### 5.2 — AL2 to AL2023 Migration Assessment

> **Freshness gate — apply BEFORE citing the AL2 support date below:**
> The AL2 support milestone is hardcoded and time-sensitive. Verify the AL2 support
> status live before reporting (`search_documentation` for "Amazon Linux 2 end of
> support", or check the [AL2 FAQ end-of-support notice](https://aws.amazon.com/amazon-linux-2/faqs/)).
> Phrase the finding as "AL2 standard support ended 2026-06-30 (as of <assessment date>)".
> If live lookup fails, use the hardcoded date as fallback and note "AL2 support status
> unverified — date may be stale".

**Why this matters:**
- AL2 EKS-optimized AMIs: the last AL2 AMIs were published 2025-11-26 (1.32 is the last Kubernetes version to receive AL2 AMIs); AL2 standard support ENDED 2026-06-30 (as of the assessment date; verify live per the freshness gate above) — the AL2 OS no longer receives standard security updates. See https://aws.amazon.com/amazon-linux-2/faqs/
- EKS 1.33+ does NOT publish AL2 AMIs — cannot create new AL2 node groups
- AL2 uses cgroup v1; AL2023 uses cgroup v2 (required for EKS 1.35+)

**How to check:**
1. From node group descriptions, identify AMI type
2. From node Kubernetes API, check `kernelVersion` for `amzn2` or `osImage` for `Amazon Linux 2`
3. Count AL2 nodes and node groups

**Rating:**
- No AL2 nodes → PASS
- AL2 nodes present, target < 1.33 → WARN (plan migration)
- AL2 nodes present, target >= 1.33 → FAIL (HIGH — no AL2 AMI available; migrate to AL2023). Scoring is deferred to `report-generation.md` (see Score Impact below): a cluster with a mix of AL2 and AL2023 nodes is not a hard score-cap override — the deduction is applied per that category, not treated as an automatic hard blocker here.

**Migration guidance (report as recommended remediation steps):**
1. Recommend: create a new node group with the AL2023 AMI type
2. Recommend: cordon the old AL2 nodes to stop new scheduling — e.g. `kubectl cordon <node-name>`
3. Recommend: drain workloads off the old nodes so pods reschedule onto AL2023 — e.g. `kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data`
4. Recommend: delete the old node group once all pods have rescheduled
5. Note the key differences to plan for: cgroup v2 default, dnf instead of yum, different kernel

### 5.3 — Container Runtime Version

**Why this matters:** Kubernetes 1.35 is the LAST release supporting containerd 1.x. The 1.36
kubelet will not operate against a containerd 1.x runtime. How this surfaces depends on node type:
EKS-managed node groups (and Bottlerocket) pull containerd 2.0+ automatically when you upgrade the
node group to 1.36, so they self-heal. Self-managed nodes and custom AMIs that pin containerd 1.x
do NOT — their 1.36 kubelet will fail to run. This is an assessment-time finding, not a launch
failure at the point of the control-plane upgrade — managed nodes self-heal during the node-group
upgrade, so it is scored HIGH but is NOT a hard blocker.

**How to check:**
1. List nodes → `status.nodeInfo.containerRuntimeVersion`
2. Check for containerd 1.x vs 2.x
3. For any node on containerd 1.x, determine whether it is **managed** (part of an EKS managed
   node group / Bottlerocket) or **self-managed / custom AMI** — reuse the classification from
   check 5.4.

**Rating:**
- All nodes on containerd 2.x → PASS
- Any node on containerd 1.x, target < 1.35 → WARN (plan upgrade)
- Any node on containerd 1.x, target == 1.35 → WARN (last version supporting containerd 1.x;
  the next version, 1.36, requires 2.0+)
- Any node on containerd 1.x, target >= 1.36:
  - **Managed node group / Bottlerocket** → INFO (auto-handled), scored +2 (warning tier — not a
    hard blocker). Upgrading the node group to 1.36 replaces the AMI and pulls containerd 2.0+
    automatically. No manual action, but call it out so the user knows the runtime jump happens
    during node rotation.
  - **Self-managed / custom AMI** → FAIL (HIGH) — outside containerd's tested matrix. The 1.36
    kubelet is validated against containerd 2.x; running it on containerd 1.x is unsupported.
    The AMI must be rebuilt with containerd 2.0+ BEFORE upgrading the node. Scored +5 under
    Category 3 (Node Readiness); HIGH severity but NOT a hard blocker (no score cap).

### 5.4 — Self-Managed Nodes

**How to check:**
1. List all nodes
2. Compare against managed node group nodes (by labels or node group membership)
3. Exclude AWS-managed Fargate and Auto Mode nodes using compute-type labels and
   cluster configuration. An empty managed-node-group list alone does not establish
   self-managed nodes. Classify remaining nodes outside managed groups and Karpenter
   as self-managed; if ownership is unresolved, record it as unverified.

**Rating:**
- No self-managed nodes → PASS
- Self-managed nodes present → WARN (no automated upgrade path, manual AMI update required)

### 5.5 — Subnet IP Capacity

**Why this matters:**
- AWS documents **up to five** available IP addresses for control-plane updates, not a
  universal five-address minimum. ENIs can be placed in different configured cluster
  subnets than before. Subnet existence, address availability, and security-group
  communication all matter; a sum of free addresses is not an ENI placement test.
- This skill retains `sum(AvailableIpAddressCount) < 5` as a **conservative capacity
  review guard** (5 additional points and the existing hard-blocker score cap). Describe
  it as "capacity review required by the assessment policy", not proof that AWS will
  reject the update. A total >= 5 only clears this numeric guard; it does not prove
  the upgrade will succeed. Individual subnets with <= 15 addresses remain warnings.
- The default managed-node update strategy launches replacement nodes before terminating
  old ones. The minimal strategy terminates old nodes first. Address demand and temporary
  spare compute capacity therefore depend on the selected strategy and VPC CNI settings.

**How to check:**
1. Get the cluster subnet IDs from the cluster description (already retrieved in pre-flight
   Action 2 — `resourcesVpcConfig.subnetIds`).
2. Run:
   ```bash
   aws ec2 describe-subnets --subnet-ids <subnet-id-1> <subnet-id-2> ... \
     --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,AvailableIPs:AvailableIpAddressCount,CIDR:CidrBlock}' \
     --output table
   ```
3. For each subnet, evaluate `AvailableIpAddressCount` against the policy thresholds below.
   Missing, denied, or partial subnet reads are Unassessed; never sum an incomplete list.
   Report these as address-count checks only. Do not claim that security groups, subnet
   reservations, prefix fragmentation, EC2 quotas, or actual ENI placement were verified
   unless separately inspected.

**Thresholds:**

| Available IPs (single subnet) | Verdict | Severity |
|---------------|---------|----------|
| < 5 — single low subnet among otherwise-healthy subnets | **WARNING** — review capacity; this alone does not trigger the numeric score cap | MEDIUM |
| 5–15 | **WARNING** — review control-plane and node-update capacity | MEDIUM |
| > 15 | No address-count warning; not a placement guarantee | — |
| Total `AvailableIpAddressCount` across ALL cluster subnets < 5 | **ASSESSMENT POLICY BLOCKER** — capacity review required; retain the existing score cap, without asserting AWS rejection | CRITICAL |

**Important context for the 5–15 warning:**
The exact number of IPs needed during node group surge depends on:
- Instance type (determines max ENIs and IPs per ENI)
- VPC CNI configuration (`WARM_IP_TARGET`, `MINIMUM_IP_TARGET`, `WARM_PREFIX_TARGET`,
  `ENABLE_PREFIX_DELEGATION`)
- Managed node group `updateConfig`: strategy, `maxUnavailable` or
  `maxUnavailablePercentage`, and the Availability Zones used by its Auto Scaling group.
  EKS does not expose a node-group `maxSurge` setting. For the default strategy, AWS
  describes a scale-up allowance based on the larger of up to twice the AZ count and
  the maximum unavailable count. For example, five AZs with `maxUnavailable: 1` can
  launch up to ten additional nodes, not one. Percentage settings must be resolved
  against the relevant group size before estimating concurrency.
- The minimal strategy avoids that surge by terminating old nodes first; it reduces
  available capacity during replacement. Do not recommend switching strategies solely
  to avoid an IP warning without reviewing workload availability.

Do NOT report a precise "you need X IPs" number — instead flag the risk and advise the user
to verify capacity is sufficient for their instance type and CNI config.

**If a subnet has < 5 IPs (single low subnet among otherwise-healthy subnets), report as a WARNING:**

> **⚠️ Subnet low on free IPs**
>
> Subnet `<subnet-id>` in `<az>` has only `<N>` available IPs (CIDR: `<cidr>`).
> EKS may use other configured cluster subnets, but this count alone cannot establish
> successful placement. The skill's capacity-review score cap applies when the total
> across all cluster subnets is < 5; this is an assessment policy, not an AWS failure guarantee.
>
> **Owner review options (recommendations only):**
> 1. Inspect ENI ownership and dependencies before reclaiming unused addresses.
> 2. Add suitable cluster subnets with sufficient address capacity and required connectivity.
> 3. If the VPC lacks address space, plan an additional VPC CIDR and new subnets.
>    Do not propose enlarging an existing subnet's CIDR in place.

**If subnet has 5–15 IPs, report:**

> **⚠️ Low subnet IP capacity — node group upgrade may stall**
>
> Subnet `<subnet-id>` in `<az>` has `<N>` available IPs. The total may clear the skill's
> numeric control-plane guard while still being insufficient for a node update. Review
> the actual update strategy, replacement-node demand, and VPC CNI warm pool.
>
> **Before upgrading:** Verify capacity is sufficient for your configuration, or consider
> adding suitable subnets. Prefix delegation improves ENI utilization and pod density;
> it does not remove the need for a pod IP. IPv4 prefix mode allocates contiguous /28
> blocks, so fragmentation and warm-prefix allocation can worsen address pressure.
> Check contiguous space and warm-pool settings before recommending it; it is not a
> generic remedy for an exhausted subnet.

**AWS sources (verified 2026-10-01; recheck live when assessing):**
- https://docs.aws.amazon.com/eks/latest/userguide/update-cluster.html
- https://docs.aws.amazon.com/eks/latest/userguide/managed-node-update-behavior.html
- https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html
- https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 3 (Node Readiness) and §Category 8 (AL2 Nodes).**
> AL2 findings for target >= 1.33 deduct under TWO separate categories: the HIGH
> breaking-change finding is scored under Category 1 (Breaking Changes), and the
> node-count deduction under Category 8 (capped at 5 pts). Do NOT combine them into
> a single deduction under one category.

| Finding | Deduction |
|---------|-----------|
| Subnet IPs < 5 — single low subnet (warning) | 2 pts (always applies, per low subnet) |
| Capacity-review policy guard — total reported available IPs across ALL cluster subnets < 5; not a prediction of AWS rejection | 5 pts + hard blocker override (caps score ≤ 59%); additional to any +2 warnings |
| Subnet IPs 5–15 (warning) | 2 pts |
| AL2 nodes (target < 1.33) — Node count (Category 8) | 2-5 pts (max 5) |
| AL2 nodes (target >= 1.33) — Breaking Change "AL2 AMI Not Available" (Category 1) | 10 pts (HIGH) |
| AL2 nodes (target >= 1.33) — Node count (Category 8) | 2-5 pts (max 5) |
| Containerd 1.x (target < 1.36, or managed node on any target) | 2 pts |
| Containerd 1.x on self-managed/custom AMI (target >= 1.36) | 5 pts (HIGH — outside containerd's tested matrix; NOT a score-cap blocker) |
| Self-managed nodes present | 3 pts (binary — Category 3, scored in report-generation.md pseudocode) |
| Max category (combined with version-validation skew) | 20 pts |
