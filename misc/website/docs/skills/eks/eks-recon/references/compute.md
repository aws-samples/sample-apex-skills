---
title: "Module: Compute"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/compute.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/compute.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/compute.md). Edit the source, not this page.
:::

# Module: Compute

> **Part of:** [eks-recon](../)
> **Purpose:** Detect compute strategy - Karpenter, Managed Node Groups, Auto Mode, Fargate, self-managed

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Auto Mode Detection](#1-auto-mode-detection)
  - [Karpenter Detection](#2-karpenter-detection)
  - [Managed Node Group Detection](#3-managed-node-group-detection)
  - [Fargate Detection](#4-fargate-detection)
  - [Self-Managed Node Detection](#5-self-managed-node-detection)
  - [Per-Node Inventory (nodes[])](#6-per-node-inventory-nodes)
- [Output Schema](#output-schema)
- [Strategy Determination Logic](#strategy-determination-logic)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `describe_eks_resource`, `list_eks_resources`, `list_k8s_resources`
- **CLI fallback:** `aws eks`, `kubectl`

---

## Detection Strategy

Run detections in this order because later strategies depend on ruling out earlier ones:

```
1. Auto Mode      -> If enabled, strategy is "Auto Mode" (may have MNG for system)
2. Karpenter      -> Check for NodePool CRDs and controller
3. MNG            -> List managed node groups
4. Fargate        -> List Fargate profiles
5. Self-managed   -> Nodes without MNG labels
```

**Why this order matters:**
- Auto Mode can coexist with MNG for system workloads, so check it first
- Karpenter clusters often have a bootstrap MNG that should not define the strategy
- Fargate-only clusters are rare; check MNG before assuming Fargate-only
- Self-managed is the fallback when no managed solution is detected

**Determine the final strategy:**
- Single method detected -> Use that method
- Multiple methods detected -> Report "Mixed" and detail which methods
- Nothing detected -> Report "Self-managed" or "Unknown"

---

## Detection Commands

### 1. Auto Mode Detection

Check Auto Mode first because it fundamentally changes how the cluster provisions compute. Auto Mode clusters let EKS manage nodes automatically, so you may not see traditional node groups.

**MCP:**
```
describe_eks_resource(
  resource_type="cluster",
  cluster_name="<cluster-name>"
)
-> Check response for cluster.computeConfig.enabled
```

**CLI:**
```bash
aws eks describe-cluster \
  --name <cluster-name> \
  --query 'cluster.computeConfig.{enabled:enabled,nodePools:nodePools,nodeRoleArn:nodeRoleArn}'
```

**Example output (Auto Mode enabled):**
```json
{
  "enabled": true,
  "nodePools": ["general-purpose", "system"],
  "nodeRoleArn": "arn:aws:iam::111122223333:role/eks-auto-node-role"
}
```

**Example output (Auto Mode not enabled):**
```json
{
  "enabled": null,
  "nodePools": null,
  "nodeRoleArn": null
}
```

**Interpret the result:** `enabled: true` = Auto Mode enabled, `false` or `null` = Not
using Auto Mode. When enabled, record the built-in `nodePools` list and the `nodeRoleArn`
that EKS uses for managed nodes. Absence of the `computeConfig` block entirely is a valid
state (classic cluster) — record `auto_mode.enabled: false`, do not treat it as an error.

### 2. Karpenter Detection

Detect Karpenter to identify clusters using just-in-time node provisioning. Karpenter provisions nodes directly in response to pending pods rather than adjusting node group sizes.

**MCP (check for NodePools):**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="NodePool",
  api_version="karpenter.sh/v1"
)
```

If empty, try v1beta1 (older Karpenter versions use this API):
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="NodePool",
  api_version="karpenter.sh/v1beta1"
)
```

**MCP (check for controller):** Search ALL namespaces — do not hardcode `kube-system`.
Karpenter is commonly installed into its own `karpenter` namespace (observed live on a
Fargate+Karpenter cluster), so a `kube-system`-scoped lookup returns null and misses the
version. Omit `namespace` to search cluster-wide.
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Deployment",
  api_version="apps/v1",
  label_selector="app.kubernetes.io/name=karpenter"
)
```

**CLI:**
```bash
# Check for NodePools
kubectl get nodepools.karpenter.sh 2>/dev/null

# Check for controller deployment (search ALL namespaces, not just kube-system)
kubectl get deploy -A -l app.kubernetes.io/name=karpenter -o json 2>/dev/null | \
  jq -r '.items[0].spec.template.spec.containers[0].image'
```

**Auto Mode note:** On EKS Auto Mode there is NO Karpenter controller Deployment at all
(EKS runs provisioning internally). A null controller image here is a valid fact on Auto
Mode clusters, not a detection miss — record `karpenter.version: null` accordingly.

**Example output (Karpenter detected):**
```
NAME      NODECLASS
default   default
gpu-pool  gpu-nodes
```

**Example controller image:**
```
public.ecr.aws/karpenter/controller:1.0.5
```

**Extract version:** Parse the image tag from the controller deployment to report the Karpenter version.

**Record `api_version`:** whichever NodePool API returns resources — `v1` or `v1beta1`.

**Detect NodeClasses (two distinct groups — record which one appears):**

- **Self-managed Karpenter** uses `EC2NodeClass` in the `karpenter.k8s.aws` API group.
- **EKS Auto Mode** uses `NodeClass` in the `eks.amazonaws.com` API group.

These are different resources; distinguish them explicitly (do not conflate). Record the
resource names for each. AMI reporting differs by resource (both confirmed live):

- **Self-managed `EC2NodeClass`:** Karpenter v1 specifies the AMI via
  `spec.amiSelectorTerms[].alias` (e.g. `bottlerocket@latest`), and `spec.amiFamily` is
  often null. Read `amiFamily`, and fall back to the `amiSelectorTerms[].alias` values
  when it is null.
- **Auto Mode `NodeClass` (`eks.amazonaws.com`):** has NO `amiFamily` field at all — the
  AMI is EKS-managed. Do not emit a null `amiFamily` that looks like a bug; record it as
  absent/EKS-managed by design.

**MCP (self-managed EC2NodeClass):**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="EC2NodeClass",
  api_version="karpenter.k8s.aws/v1"
)
```

**MCP (Auto Mode NodeClass):**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="NodeClass",
  api_version="eks.amazonaws.com/v1"
)
```

**CLI:**
```bash
# Self-managed Karpenter EC2NodeClasses (name + amiFamily, falling back to
# amiSelectorTerms[].alias when amiFamily is null — Karpenter v1 uses aliases).
kubectl get ec2nodeclasses.karpenter.k8s.aws -o json 2>/dev/null | \
  jq -r '.items[] | {
    name: .metadata.name,
    ami: (.spec.amiFamily // ([.spec.amiSelectorTerms[]?.alias] | map(select(. != null)) | join(",") | select(. != "")))
  }'

# Auto Mode NodeClasses (name only — no amiFamily field exists; AMI is EKS-managed).
kubectl get nodeclasses.eks.amazonaws.com -o json 2>/dev/null | \
  jq -r '.items[] | {name: .metadata.name}'
```

### 3. Managed Node Group Detection

Detect Managed Node Groups (MNG) to identify AWS-managed EC2 capacity. MNGs are the most common compute strategy and handle node lifecycle, patching, and scaling automatically.

**MCP:**
```
list_eks_resources(
  resource_type="nodegroup",
  cluster_name="<cluster-name>"
)
```

**CLI:**
```bash
aws eks list-nodegroups --cluster-name <cluster-name> --query 'nodegroups'
```

**Example output:**
```json
["system-ng", "app-ng-spot", "app-ng-ondemand"]
```

**Empty result is a valid state, not an error:** Auto Mode and Fargate-only clusters
routinely return `[]` here. Record `mng.detected: false, mng.count: 0` and move on — do
not treat zero managed node groups as a failure.

For each node group, get details to understand instance types and scaling configuration:

**MCP:**
```
describe_eks_resource(
  resource_type="nodegroup",
  cluster_name="<cluster-name>",
  resource_name="<nodegroup-name>"
)
```

<!-- UNVALIDATED LIVE: both test clusters are Auto Mode/Fargate (zero MNGs). The field
     paths below (releaseVersion, version, amiType, capacityType, taints) are correct per
     the EKS API schema (source-grounding confirmed) but were NOT exercised on a live cluster.
     Validate on a cluster with managed node groups. -->
**CLI:**
```bash
aws eks describe-nodegroup \
  --cluster-name <cluster-name> \
  --nodegroup-name <nodegroup-name> \
  --query 'nodegroup.{
    name:nodegroupName,
    status:status,
    amiType:amiType,
    version:version,
    releaseVersion:releaseVersion,
    capacityType:capacityType,
    instanceTypes:instanceTypes,
    desiredSize:scalingConfig.desiredSize,
    minSize:scalingConfig.minSize,
    maxSize:scalingConfig.maxSize,
    nodeRole:nodeRole,
    launchTemplate:launchTemplate,
    maxUnavailable:updateConfig.maxUnavailable,
    taints:taints
  }'
```

- `version` = the node group's Kubernetes version. `releaseVersion` = the AMI release version.
- `capacityType` = `ON_DEMAND` or `SPOT`.
- `taints` = list of `{key, value, effect}` applied to nodes in the group (null/empty when none).
- `launchTemplate` = `{id, name, version}` when a launch template backs the group, else null.
- `updateConfig.maxUnavailable` = max nodes unavailable during a rolling update (may be expressed as `maxUnavailablePercentage` instead).

**Example output:**
```json
{
  "name": "app-ng-spot",
  "status": "ACTIVE",
  "amiType": "AL2_x86_64",
  "version": "1.30",
  "releaseVersion": "1.30.0-20240625",
  "capacityType": "SPOT",
  "instanceTypes": ["m5.large", "m5a.large", "m5d.large"],
  "desiredSize": 3,
  "minSize": 1,
  "maxSize": 10,
  "nodeRole": "arn:aws:iam::111122223333:role/eks-node-role",
  "launchTemplate": {"id": "lt-0abc123", "name": "app-ng-lt", "version": "3"},
  "maxUnavailable": 1,
  "taints": [{"key": "dedicated", "value": "gpu", "effect": "NO_SCHEDULE"}]
}
```

### 4. Fargate Detection

Detect Fargate profiles to identify serverless compute. Fargate eliminates node management entirely - pods run on AWS-managed infrastructure. Use this when you see no nodes or need to understand which namespaces run serverless.

**MCP:** Not available, use CLI

**CLI:**
```bash
aws eks list-fargate-profiles --cluster-name <cluster-name> --query 'fargateProfileNames'
```

**Example output:**
```json
["fp-default", "fp-kube-system"]
```

For each profile, get selectors to understand which pods run on Fargate:
```bash
aws eks describe-fargate-profile \
  --cluster-name <cluster-name> \
  --fargate-profile-name <profile-name> \
  --query 'fargateProfile.{
    name:fargateProfileName,
    status:status,
    selectors:selectors,
    podExecutionRoleArn:podExecutionRoleArn,
    subnets:subnets
  }'
```

**Example output:**
```json
{
  "name": "fp-default",
  "status": "ACTIVE",
  "selectors": [
    {"namespace": "default"},
    {"namespace": "app", "labels": {"fargate": "true"}}
  ],
  "podExecutionRoleArn": "arn:aws:iam::111122223333:role/fargate-pod-exec",
  "subnets": ["subnet-0aaa111", "subnet-0bbb222"]
}
```

### 5. Self-Managed Node Detection

Detect self-managed nodes when other strategies are not found. Self-managed nodes are EC2 instances joined to the cluster manually or via custom automation (Terraform, CloudFormation ASGs). These require manual patching and lifecycle management.

**Do not select on the absence of the MNG label alone.** Fargate nodes and Karpenter
nodes also lack `eks.amazonaws.com/nodegroup`, so a bare `== null` check miscounts every
Fargate and Karpenter node as self-managed (observed live: a Fargate+Karpenter cluster
reported `self_managed=5` when the true count was 0). A node is self-managed only if it
has NO nodegroup label, NO `karpenter.sh/nodepool` label, and is not a Fargate node
(`eks.amazonaws.com/compute-type != fargate`, or a node name starting with `fargate-`).

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Node",
  api_version="v1"
)
```

**CLI:**
```bash
# Find nodes that belong to NO managed compute method (indicates self-managed).
# A node is self-managed ONLY if it has no MNG label AND no Karpenter nodepool
# label AND is not a Fargate node. Fargate and Karpenter nodes also lack the
# nodegroup label, so selecting on that label alone yields false positives.
kubectl get nodes -o json | jq -r '
  .items[] |
  select(
    .metadata.labels["eks.amazonaws.com/nodegroup"] == null and
    .metadata.labels["karpenter.sh/nodepool"] == null and
    (.metadata.labels["eks.amazonaws.com/compute-type"] // "") != "fargate" and
    (.metadata.name | startswith("fargate-") | not)
  ) |
  .metadata.name'
```

**Example output (self-managed nodes found):**
```
ip-10-0-1-50.ec2.internal
ip-10-0-2-75.ec2.internal
```

**Example output (no self-managed nodes):**
```
(empty - all nodes belong to MNGs or Karpenter)
```

### 6. Per-Node Inventory (nodes[])

Enumerate every joined node and extract per-node facts. This is the authoritative source
for the `nodes[]` schema block. Runs regardless of strategy (Auto Mode, MNG, Karpenter,
self-managed all surface here).

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Node",
  api_version="v1"
)
```

**CLI:**
```bash
kubectl get nodes -o json | jq -r '
  .items[] | {
    name: .metadata.name,
    instance_type: .metadata.labels["node.kubernetes.io/instance-type"],
    # capacity_type: check BOTH labels — karpenter.sh for Auto Mode/Karpenter,
    # eks.amazonaws.com for classic MNG
    capacity_type: (.metadata.labels["karpenter.sh/capacity-type"]
                    // .metadata.labels["eks.amazonaws.com/capacityType"]),
    nodepool: (.metadata.labels["karpenter.sh/nodepool"]
               // .metadata.labels["eks.amazonaws.com/nodegroup"]),
    kubelet_version: .status.nodeInfo.kubeletVersion,
    os: .status.nodeInfo.operatingSystem,
    os_label: .metadata.labels["kubernetes.io/os"],
    os_image: .status.nodeInfo.osImage
  }'
```

- `capacity_type` — check BOTH `karpenter.sh/capacity-type` (Auto Mode / Karpenter) AND
  `eks.amazonaws.com/capacityType` (classic MNG). Values normalize to `spot` / `on-demand`.
- `nodepool` — `karpenter.sh/nodepool` for Karpenter/Auto Mode, `eks.amazonaws.com/nodegroup` for MNG.
- `os` — `.status.nodeInfo.operatingSystem` (`linux` / `windows`).
- `os_image` — the node AMI / OS image string (e.g. `Bottlerocket OS 1.20.0`, `Amazon Linux 2`).
- **Windows presence** — a node with `os: windows` (or label `kubernetes.io/os=windows`)
  means Windows nodes are present; record `nodes_windows_present: true` at the compute level.

**Example output:**
```json
{
  "name": "ip-10-0-1-50.ec2.internal",
  "instance_type": "m5.large",
  "capacity_type": "on-demand",
  "nodepool": "general-purpose",
  "kubelet_version": "v1.30.0-eks-036c24b",
  "os": "linux",
  "os_label": "linux",
  "os_image": "Bottlerocket OS 1.20.0 (aws-k8s-1.30)"
}
```

---

## Output Schema

This is the **single canonical schema** for the compute module — it carries every compute
fact. The `compute-recon` agent emits exactly this shape (plus the shared `cluster:` block
from `references/cluster-basics.md`). Use `null` where a fact was not detected; never omit a key.

```yaml
compute:
  strategy: string  # Karpenter | MNG | Auto Mode | Fargate | Mixed | Self-managed | Unknown

  auto_mode:
    enabled: bool
    node_pools: list          # built-in Auto Mode nodePools (cluster.computeConfig.nodePools), null if absent
    node_role_arn: string     # cluster.computeConfig.nodeRoleArn, null if absent

  karpenter:
    detected: bool
    version: string           # e.g., "1.0.5" (from controller image tag)
    api_version: string       # v1 or v1beta1 (whichever NodePool API returned resources)
    nodepools: int            # count of NodePool resources
    nodepool_names: list      # names of NodePools
    ec2_node_classes:         # self-managed Karpenter (group karpenter.k8s.aws)
      detected: bool
      names: list             # EC2NodeClass resource names
      ami_families: list      # spec.amiFamily per EC2NodeClass; when null (Karpenter v1),
                              # fall back to spec.amiSelectorTerms[].alias (e.g. "bottlerocket@latest")
    node_classes:             # EKS Auto Mode (group eks.amazonaws.com) — distinct from above
      detected: bool
      names: list             # NodeClass resource names
      # NOTE: no amiFamily key — Auto Mode NodeClass has no amiFamily field (AMI is EKS-managed, absent by design)

  mng:
    detected: bool
    count: int
    groups:
      - name: string
        status: string
        ami_type: string              # amiType (e.g., AL2_x86_64, BOTTLEROCKET_ARM_64)
        version: string               # nodegroup Kubernetes version
        release_version: string       # releaseVersion (AMI release version)
        capacity_type: string         # capacityType: ON_DEMAND | SPOT
        instance_types: list
        desired_size: int
        min_size: int
        max_size: int
        node_role: string             # nodeRole ARN
        launch_template:              # launchTemplate, null if not backed by one
          id: string
          name: string
          version: string
        update_config:
          max_unavailable: int        # updateConfig.maxUnavailable (or maxUnavailablePercentage)
        taints: list                  # [{key, value, effect}], null/empty when none

  fargate:
    detected: bool
    profiles: int
    profile_names: list
    profile_details:
      - name: string
        status: string
        pod_execution_role_arn: string   # podExecutionRoleArn
        subnets: list
        selectors: list                  # [{namespace, labels}]

  self_managed:
    detected: bool                # nodes with NO nodegroup label AND NO karpenter.sh/nodepool
                                   # label AND not Fargate (compute-type != fargate / name not fargate-*)
    node_count: int

  nodes:                          # per-node inventory (kubectl get nodes -o json)
    - name: string
      instance_type: string       # label node.kubernetes.io/instance-type
      capacity_type: string       # spot | on-demand (karpenter.sh/capacity-type OR eks.amazonaws.com/capacityType)
      nodepool: string            # karpenter.sh/nodepool OR eks.amazonaws.com/nodegroup, null if neither
      kubelet_version: string     # .status.nodeInfo.kubeletVersion
      os: string                  # .status.nodeInfo.operatingSystem (linux | windows)
      os_image: string            # .status.nodeInfo.osImage (AMI / OS image string)

  nodes_windows_present: bool     # true if any node reports os: windows (or kubernetes.io/os=windows)
```

---

## Strategy Determination Logic

```
if auto_mode.enabled:
    if mng.detected and mng.count > 0:
        strategy = "Auto Mode"  # Auto Mode may have MNG for system workloads
    else:
        strategy = "Auto Mode"
        
elif karpenter.detected and karpenter.nodepools > 0:
    # Karpenter can coexist with MNG and/or Fargate. Collect every coexisting method
    # so Fargate is not hidden behind a bare "Karpenter" label (observed live: a
    # Karpenter+Fargate cluster with fargate.detected=true was mislabeled "Karpenter").
    coexisting = []
    if mng.detected and mng.count > 0:
        coexisting.append("MNG")
    if fargate.detected:
        coexisting.append("Fargate")
    if coexisting:
        strategy = "Mixed"
        note = "Karpenter + " + " + ".join(coexisting)  # e.g. "Karpenter + Fargate"
    else:
        strategy = "Karpenter"
        
elif mng.detected and mng.count > 0:
    if fargate.detected:
        strategy = "Mixed"
        note = "MNG + Fargate"
    else:
        strategy = "MNG"
        
elif fargate.detected:
    strategy = "Fargate"
    
elif self_managed.detected:
    strategy = "Self-managed"
    
else:
    strategy = "Unknown"
```

---

## Edge Cases

Handle these special scenarios to provide accurate compute reporting.

### Cluster Autoscaler vs Karpenter

Check for Cluster Autoscaler when Karpenter is not detected. CAS predates Karpenter and affects how you interpret MNG scaling behavior.

```bash
kubectl get deploy -n kube-system cluster-autoscaler 2>/dev/null
```

**Why this matters:** If CAS is present, MNG scaling is automated. If neither CAS nor Karpenter is present, MNGs use static sizing only.

### Bottlerocket Nodes

Identify Bottlerocket nodes by checking the AMI type. Bottlerocket is a security-hardened OS that affects troubleshooting (no SSH, read-only filesystem).

Look for these values in `amiType`:
- `BOTTLEROCKET_x86_64`
- `BOTTLEROCKET_ARM_64`

### GPU Nodes

Detect GPU nodes for clusters running ML/AI workloads. GPU nodes require special scheduling consideration.

```bash
kubectl get nodes -l "nvidia.com/gpu" -o name
```

**Example output:**
```
node/ip-10-0-3-100.ec2.internal
```

### Graviton/ARM Nodes

Identify ARM-based Graviton nodes as a fact. Graviton instances use the ARM architecture and require ARM-compatible container images.

Look for these indicators:
- `amiType: AL2_ARM_64` or `AL2023_ARM_64_STANDARD`
- Instance types: `m6g`, `m7g`, `c6g`, `c7g`, `r6g`, `r7g`
