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

**Output per node group:**
- Name, version, AMI type, instance types, scaling config
- Version skew against target (calculated in version-validation)

### 5.2 — AL2 to AL2023 Migration Assessment

**Why this matters:**
- AL2 EKS-optimized AMIs: the last AL2 AMIs were published 2025-11-26 (1.32 is the last Kubernetes version to receive AL2 AMIs); the AL2 OS itself reaches end-of-life 2026-06-30
- EKS 1.33+ does NOT publish AL2 AMIs — cannot create new AL2 node groups
- AL2 uses cgroup v1; AL2023 uses cgroup v2 (required for EKS 1.35+)

**How to check:**
1. From node group descriptions, identify AMI type
2. From node Kubernetes API, check `kernelVersion` for `amzn2` or `osImage` for `Amazon Linux 2`
3. Count AL2 nodes and node groups

**AMI provenance matters** — distinguish an EKS-optimized AL2 AMI from a CUSTOM AL2-based AMI.
An operator who brings their own AL2 AMI bypasses the "no AL2 AMI available" logic, so the
no-AMI reasoning below does NOT cover custom AL2 nodes. The rule that catches BOTH is cgroup
version: AL2 runs cgroup v1 only; AL2023/Bottlerocket run cgroup v2. As of 2026-07-21, K8s
1.31–1.34 treat cgroup v1 as a warning / maintenance mode (kubelet still starts), but at K8s
1.35 `failCgroupV1` defaults to `true` and the kubelet REFUSES TO START on a cgroup v1 node.
The `failCgroupV1: false` override exists but is non-prod-only. So a custom AL2 AMI survives
1.33 and 1.34 but DIES at 1.35, regardless of AMI provenance.

**Rating — fork on node group type first, then AMI provenance.** Reuse the classification
from checks 5.1 / 5.4 (managed node group, Fargate, self-managed, Karpenter, Auto Mode). The
managed/Fargate vs self-managed fork matters because the EKS `update-cluster-version` API
REJECTS a control-plane upgrade until MANAGED node groups and Fargate nodes EQUAL the control
plane's CURRENT version (stricter than the N-3 skew tolerance; as of 2026-07-21, per the EKS
troubleshooting doc "Node groups must match Kubernetes version before upgrading control
plane"). Self-managed nodes are NOT named in this gate — their kubelet version is invisible to
the EKS API, so the operator owns skew (subject only to the N-3 kubelet skew policy).

- No AL2 nodes → PASS
- AL2 nodes present, target < 1.33 → WARN (plan migration; AL2 merely deprecated, not fatal)

- **Managed node group (or Fargate) on AL2, target >= 1.33 → HARD BLOCKER.** The
  `update-cluster-version` API is rejected until every managed node group and Fargate node
  matches the control plane's current version, but there is NO EKS-optimized AL2 AMI past 1.32
  (1.32 is the last; as of 2026-07-21, per the EKS AMI deprecation FAQ). So the managed group
  cannot be advanced to the target version. The control plane can complete exactly ONE hop
  (1.32 → 1.33: managed nodes at 1.32 equal the pre-hop current minor) but is then REJECTED at
  the next hop (1.33 → 1.34, which requires the managed group at 1.33 — impossible with no AL2
  AMI past 1.32). So a multi-minor target (anything beyond 1.33) is unreachable while an AL2
  managed group exists, and this blocks BEFORE the cgroup-v1/1.35 issue is ever reached. The ONLY path is
  to migrate the managed group to AL2023/Bottlerocket (route to the **eks-al2-to-al2023** skill)
  BEFORE the control-plane upgrade. Caps the readiness score (see Score Impact and the Hard
  Blocker Override in SKILL.md). (Applies regardless of AMI provenance: even a custom AL2 AMI on
  a managed node group must be advanced to a matching-version image the operator cannot build
  from AL2 past 1.32.)

- **Self-managed AL2 nodes** (not in any managed node group / Fargate — NOT API-gated):
  - target == 1.33 or == 1.34 → WARN / at-risk (NOT a hard blocker) — **SELF-MANAGED ONLY**.
    A MANAGED node group / Fargate at the same target is the HARD BLOCKER above (the
    `update-cluster-version` API gate), NOT this WARN — do not apply the hold-at-1.32 path to a
    managed group. This WARN/hold path is available ONLY because a self-managed kubelet is
    invisible to the API gate. Viable path (self-managed only): hold kubelet at 1.32 (within the
    N-3 kubelet skew policy — supported for self-managed nodes since K8s 1.28, as of 2026-07-21)
    while the control plane advances 1.32 → 1.33 → 1.34, THEN migrate to AL2023/Bottlerocket
    before/at 1.35. Note N-3 is the LIMIT: a 1.32 kubelet under a 1.34 CP is N-2 (one minor of
    headroom); under a 1.35 CP it would be exactly N-3 (no headroom) — migrate before the CP
    would force a 4th minor of skew. (A custom AL2 AMI can still run at 1.33/1.34 on cgroup v1 —
    warning/maintenance mode.)
  - target >= 1.35 → **HARD BLOCKER** (the cgroup-v1 rule below).

- AL2 nodes present, target >= 1.35 → **HARD BLOCKER** (regardless of node group type OR whether
  the AMI is EKS-optimized OR CUSTOM): AL2 = cgroup v1, and at K8s 1.35 `failCgroupV1` defaults
  `true` so the kubelet refuses to start on a cgroup v1 node (as of 2026-07-21). Caps the
  readiness score (see Score Impact and the Hard Blocker Override in SKILL.md). Migrate to
  AL2023/Bottlerocket (cgroup v2) first.

**Migration guidance (report as recommended remediation steps):**
1. Recommend: create a new node group with the AL2023 AMI type
2. Recommend: cordon the old AL2 nodes to mark them unschedulable so no new pods land on them
3. Recommend: drain the workloads off the old AL2 nodes (ignoring DaemonSets, and clearing emptyDir data) so pods reschedule onto the AL2023 node group
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
3. Nodes not in any managed node group or Karpenter → self-managed

**Rating:**
- No self-managed nodes → PASS
- Self-managed nodes present → WARN (no automated upgrade path, manual AMI update required)

### 5.5 — Subnet IP Capacity

**Why this matters:**
- EKS places control-plane ENIs for the upgraded API server across the cluster's subnets. A
  single subnet with < 5 available IPs is a warning, not a failure — EKS can place the ENIs in
  other subnets. The `update-cluster-version` API call fails only when the cluster subnets
  COLLECTIVELY cannot provide enough free IPs for ENI placement (collective insufficiency = sum
  of `AvailableIpAddressCount` across all cluster subnets < 5).
- During node group rolling updates, new nodes are launched before old nodes are terminated
  (surge). Each new node consumes 1 IP for its primary ENI plus additional IPs for the VPC CNI
  warm pool (pod IPs). Insufficient capacity causes the node group update to hang.

**How to check:**
1. Get the cluster subnet IDs from the cluster description (already retrieved in pre-flight
   Action 2 — `resourcesVpcConfig.subnetIds`).
2. Call the EC2 `DescribeSubnets` API with `SubnetIds: [<subnet-id-1>, <subnet-id-2>, ...]`
   and record, for each subnet: `SubnetId`, `AvailabilityZone`,
   `AvailableIpAddressCount`, and `CidrBlock`.
3. For each subnet, evaluate `AvailableIpAddressCount` against thresholds.

**Thresholds:**

| Available IPs (single subnet) | Verdict | Severity |
|---------------|---------|----------|
| < 5 — single low subnet among otherwise-healthy subnets | **WARNING** — control plane OK (ENIs placed in other subnets); becomes a hard blocker ONLY under collective insufficiency (see below) | MEDIUM |
| 5–15 | **WARNING** — control plane OK, but node rolling update at risk if surge needs more IPs | MEDIUM |
| > 15 | PASS | — |
| Collective: sum of `AvailableIpAddressCount` across ALL cluster subnets < 5 | **HARD BLOCKER** — control plane upgrade will fail (EKS cannot place ENIs in any subnet) | CRITICAL |

**Important context for the 5–15 warning:**
The exact number of IPs needed during node group surge depends on:
- Instance type (determines max ENIs and IPs per ENI)
- VPC CNI configuration (`WARM_IP_TARGET`, `MINIMUM_IP_TARGET`, `ENABLE_PREFIX_DELEGATION`)
- Node group `maxSurge` setting (default: 1 additional node)

Do NOT report a precise "you need X IPs" number — instead flag the risk and advise the user
to verify capacity is sufficient for their instance type and CNI config.

**If a subnet has < 5 IPs (single low subnet among otherwise-healthy subnets), report as a WARNING:**

> **⚠️ Subnet low on free IPs**
>
> Subnet `<subnet-id>` in `<az>` has only `<N>` available IPs (CIDR: `<cidr>`).
> EKS places control-plane ENIs across the cluster's subnets during an upgrade; a single low
> subnet is a warning. This becomes a hard blocker ONLY under collective insufficiency —
> defined as the sum of `AvailableIpAddressCount` across ALL cluster subnets being < 5.
>
> **Remediation (choose one):**
> 1. Remove unused ENIs: `aws ec2 describe-network-interfaces --filters Name=subnet-id,Values=<subnet-id> Name=status,Values=available --query 'NetworkInterfaces[].NetworkInterfaceId'`
> 2. Add a new subnet to the cluster: `aws eks update-cluster-config --name <cluster> --resources-vpc-config subnetIds=<subnet-1>,<subnet-2>,<new-subnet>` — this call REPLACES the entire subnet set, so list ALL current cluster subnets PLUS the new one (>= 2 subnets across different AZs, all in the same VPC); passing only the new subnet would drop the existing ones
> 3. Expand the subnet CIDR (if VPC allows)

**If subnet has 5–15 IPs, report:**

> **⚠️ Low subnet IP capacity — node group upgrade may stall**
>
> Subnet `<subnet-id>` in `<az>` has `<N>` available IPs. While this is sufficient for the
> control plane upgrade (minimum 5), the node group rolling update launches new nodes before
> terminating old ones. If your instance type + VPC CNI warm pool requires more IPs than are
> available, the surge node will fail to launch.
>
> **Before upgrading:** Verify capacity is sufficient for your configuration, or consider
> adding subnets / enabling VPC CNI prefix delegation to reduce per-pod IP consumption.

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 3 (Node Readiness) and §Category 8 (AL2 Nodes).**
> AL2 findings for target >= 1.33 deduct under TWO separate categories: the HIGH
> breaking-change finding is scored under Category 1 (Breaking Changes), and the
> node-count deduction under Category 8 (capped at 5 pts). Do NOT combine them into
> a single deduction under one category.

| Finding | Deduction |
|---------|-----------|
| Subnet IPs < 5 — single low subnet (warning) | 2 pts (always applies, per low subnet) |
| Control-plane subnets collectively can't place ENIs — sum of `AvailableIpAddressCount` across ALL subnets < 5 (hard blocker) | 5 pts + hard blocker override (caps score ≤ 59%); additional to any +2 warnings |
| Subnet IPs 5–15 (warning) | 2 pts |
| AL2 nodes (target < 1.33) — Node count (Category 8) | 2-5 pts (max 5) |
| AL2 nodes (target >= 1.33, EKS-optimized AMI) — Breaking Change "AL2 AMI Not Available" (Category 1) | 10 pts (HIGH) |
| **Managed node group (or Fargate) on AL2, target >= 1.33** — `update-cluster-version` API-rejected (nodes must match CP-current) AND no AL2 AMI past 1.32 to advance them | 10 pts + hard blocker override (caps score ≤ 59%) |
| AL2 nodes (target >= 1.35, EKS-optimized OR CUSTOM AMI, any node group type) — cgroup v1 kubelet won't start (`failCgroupV1` defaults true) | 10 pts + hard blocker override (caps score ≤ 59%) |
| AL2 nodes (target >= 1.33) — Node count (Category 8) | 2-5 pts (max 5) |
| Containerd 1.x (target < 1.36, or managed node on any target) | 2 pts |
| Containerd 1.x on self-managed/custom AMI (target >= 1.36) | 5 pts (HIGH — outside containerd's tested matrix; NOT a score-cap blocker) |
| Self-managed nodes present | 3 pts (binary — Category 3, scored in report-generation.md pseudocode) |
| Max category (combined with version-validation skew) | 20 pts |
