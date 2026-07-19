---
title: "Module: Compute"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/compute.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-recon/references/compute.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/compute.md). Edit the source, not this page.
:::

# Module: Compute

> **Part of:** [eks-recon](../)
> **Purpose:** Detect compute strategy — Karpenter, Managed Node Groups, Auto Mode, Fargate, self-managed

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
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

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS/EC2) — cluster compute config, node groups, Fargate profiles. Requires the read-only permissions in `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — nodes, Karpenter/Auto Mode CRDs (`NodePool`, `EC2NodeClass`, `NodeClass`). Requires `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry to be present. RBAC verbs needed: `get`, `list`.

If the Kubernetes API is unreachable (access entry absent), report the AWS-API facts and mark every K8s-dependent sub-fact (`nodes[]`, `karpenter.*`, Auto Mode `node_classes`) as `unconfirmed` in the report's Coverage section — never as `false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes client)* below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They are **not executable** in the Agent Space and are not an operational path — do not emit `kubectl ... | jq` pipelines. The agent reads these resources through its Kubernetes-API capability.

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

## Detection Capabilities

### 1. Auto Mode Detection

Check Auto Mode first because it fundamentally changes how the cluster provisions compute. Auto Mode clusters let EKS manage nodes automatically, so you may not see traditional node groups.

**Via AWS API** — call EKS DescribeCluster and read `cluster.computeConfig`:

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

**Via Kubernetes API** — list Karpenter `NodePool` custom resources:

- **Resource:** `NodePool`, group/version `karpenter.sh/v1` (fall back to `karpenter.sh/v1beta1` for older Karpenter versions if `v1` returns nothing).
- **Fields to extract:** `metadata.name` (NodePool names), and record which `api_version` returned resources (`v1` or `v1beta1`).
- **RBAC verbs:** `get`, `list` on `nodepools.karpenter.sh`.

**Via Kubernetes API** — detect the Karpenter controller and its version. Search **ALL namespaces** — do not hardcode `kube-system`. Karpenter is commonly installed into its own `karpenter` namespace (observed live on a Fargate+Karpenter cluster), so a `kube-system`-scoped lookup returns null and misses the version.

- **Resource:** `Deployment`, group/version `apps/v1`, label selector `app.kubernetes.io/name=karpenter`, all namespaces.
- **Fields to extract:** `spec.template.spec.containers[0].image` → parse the image tag for the Karpenter version (e.g. `public.ecr.aws/karpenter/controller:1.0.5` → `1.0.5`).
- **RBAC verbs:** `get`, `list` on `deployments.apps` (cluster-wide).

*Reference pseudocode (kubernetes client), not executable:*
```python
# NodePool CRDs — try v1, fall back to v1beta1
custom = client.CustomObjectsApi()
for ver in ("v1", "v1beta1"):
    resp = custom.list_cluster_custom_object("karpenter.sh", ver, "nodepools")
    if resp["items"]:
        nodepool_names = [i["metadata"]["name"] for i in resp["items"]]
        api_version = ver
        break

# Controller image — search ALL namespaces, not just kube-system
apps = client.AppsV1Api()
deploys = apps.list_deployment_for_all_namespaces(
    label_selector="app.kubernetes.io/name=karpenter")
image = deploys.items[0].spec.template.spec.containers[0].image if deploys.items else None
```

**Auto Mode note:** On EKS Auto Mode there is NO Karpenter controller Deployment at all
(EKS runs provisioning internally). A null controller image here is a valid fact on Auto
Mode clusters, not a detection miss — record `karpenter.version: null` accordingly.

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

**Via Kubernetes API** — list NodeClass resources for each group:

- **Self-managed:** `EC2NodeClass`, group/version `karpenter.k8s.aws/v1`. Extract `metadata.name` and `spec.amiFamily` (fall back to `spec.amiSelectorTerms[].alias` when null). RBAC: `get`, `list` on `ec2nodeclasses.karpenter.k8s.aws`.
- **Auto Mode:** `NodeClass`, group/version `eks.amazonaws.com/v1`. Extract `metadata.name` only (no `amiFamily` field exists; AMI is EKS-managed). RBAC: `get`, `list` on `nodeclasses.eks.amazonaws.com`.

*Reference pseudocode (kubernetes client), not executable:*
```python
custom = client.CustomObjectsApi()

# Self-managed Karpenter EC2NodeClasses (name + amiFamily, falling back to
# amiSelectorTerms[].alias when amiFamily is null — Karpenter v1 uses aliases)
ec2ncs = custom.list_cluster_custom_object("karpenter.k8s.aws", "v1", "ec2nodeclasses")
for item in ec2ncs["items"]:
    name = item["metadata"]["name"]
    spec = item.get("spec", {})
    ami = spec.get("amiFamily") or ",".join(
        t["alias"] for t in spec.get("amiSelectorTerms", []) if t.get("alias"))

# Auto Mode NodeClasses (name only — no amiFamily field; AMI is EKS-managed)
autoncs = custom.list_cluster_custom_object("eks.amazonaws.com", "v1", "nodeclasses")
names = [i["metadata"]["name"] for i in autoncs["items"]]
```

### 3. Managed Node Group Detection

Detect Managed Node Groups (MNG) to identify AWS-managed EC2 capacity. MNGs are the most common compute strategy and handle node lifecycle, patching, and scaling automatically.

**Via AWS API** — list node groups:

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

<!-- UNVALIDATED LIVE: both test clusters are Auto Mode/Fargate (zero MNGs). The field
     paths below (releaseVersion, version, amiType, capacityType, taints) are correct per
     the EKS API schema (source-grounding confirmed) but were NOT exercised on a live cluster.
     Validate on a cluster with managed node groups. -->
**Via AWS API** — describe each node group:

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

Detect Fargate profiles to identify serverless compute. Fargate eliminates node management entirely — pods run on AWS-managed infrastructure. Use this when you see no nodes or need to understand which namespaces run serverless.

**Via AWS API** — list Fargate profiles:

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

**Via Kubernetes API** — list nodes and filter for self-managed:

- **Resource:** `Node`, group/version `v1` (core).
- **Fields to extract:** `metadata.labels` (`eks.amazonaws.com/nodegroup`, `karpenter.sh/nodepool`, `eks.amazonaws.com/compute-type`), `metadata.name`.
- **Filter:** a node is self-managed only if it has NO nodegroup label AND NO `karpenter.sh/nodepool` label AND `eks.amazonaws.com/compute-type != fargate` AND the name does not start with `fargate-`.
- **RBAC verbs:** `get`, `list` on `nodes`.

*Reference pseudocode (kubernetes client), not executable:*
```python
v1 = client.CoreV1Api()
nodes = v1.list_node()
self_managed = [
    n.metadata.name for n in nodes.items
    if not (n.metadata.labels or {}).get("eks.amazonaws.com/nodegroup")
    and not (n.metadata.labels or {}).get("karpenter.sh/nodepool")
    and (n.metadata.labels or {}).get("eks.amazonaws.com/compute-type") != "fargate"
    and not n.metadata.name.startswith("fargate-")
]
```

**Example (self-managed nodes found):** `ip-10-0-1-50.ec2.internal`, `ip-10-0-2-75.ec2.internal`
**Example (no self-managed nodes):** empty — all nodes belong to MNGs or Karpenter.

### 6. Per-Node Inventory (nodes[])

Enumerate every joined node and extract per-node facts. This is the authoritative source
for the `nodes[]` schema block. Runs regardless of strategy (Auto Mode, MNG, Karpenter,
self-managed all surface here).

**Via Kubernetes API** — list all nodes:

- **Resource:** `Node`, group/version `v1` (core).
- **Fields to extract:**
  - `metadata.labels["node.kubernetes.io/instance-type"]` → `instance_type`
  - `capacity_type` — check BOTH `karpenter.sh/capacity-type` (Auto Mode / Karpenter) AND `eks.amazonaws.com/capacityType` (classic MNG). Values normalize to `spot` / `on-demand`.
  - `nodepool` — `karpenter.sh/nodepool` (Karpenter/Auto Mode) OR `eks.amazonaws.com/nodegroup` (MNG).
  - `status.nodeInfo.kubeletVersion` → `kubelet_version`
  - `status.nodeInfo.operatingSystem` (`linux` / `windows`) → `os`; also read label `kubernetes.io/os`.
  - `status.nodeInfo.osImage` → `os_image` (e.g. `Bottlerocket OS 1.20.0`, `Amazon Linux 2`).
- **Windows presence:** a node with `os: windows` (or label `kubernetes.io/os=windows`) means Windows nodes are present; record `nodes_windows_present: true` at the compute level.
- **RBAC verbs:** `get`, `list` on `nodes`.

*Reference pseudocode (kubernetes client), not executable:*
```python
v1 = client.CoreV1Api()
inventory = []
for n in v1.list_node().items:
    labels = n.metadata.labels or {}
    info = n.status.node_info
    inventory.append({
        "name": n.metadata.name,
        "instance_type": labels.get("node.kubernetes.io/instance-type"),
        "capacity_type": labels.get("karpenter.sh/capacity-type")
                         or labels.get("eks.amazonaws.com/capacityType"),
        "nodepool": labels.get("karpenter.sh/nodepool")
                    or labels.get("eks.amazonaws.com/nodegroup"),
        "kubelet_version": info.kubelet_version,
        "os": info.operating_system,
        "os_image": info.os_image,
    })
```

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
fact (plus the shared `cluster:` block from `references/cluster-basics.md`). Use `null`
where a fact was not detected; never omit a key. Where a fact could not be checked (e.g.
Kubernetes API unreachable), record it as `unconfirmed` in the report's Coverage section
rather than emitting a misleading `false`/`0`.

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

  nodes:                          # per-node inventory (Kubernetes API: list nodes)
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

This is the fact-labeling ladder — it assigns the `strategy` fact from what was detected.
It classifies observed state; it draws no verdict and makes no recommendation.

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

**Via Kubernetes API:** list `Deployment` (`apps/v1`) named `cluster-autoscaler` in namespace `kube-system`; presence = CAS installed. RBAC: `get`, `list` on `deployments.apps`.

**Why this matters (fact, not verdict):** if CAS is present, MNG scaling is automated; if neither CAS nor Karpenter is present, MNGs use static sizing only. Record the observation; draw no conclusion.

### Bottlerocket Nodes

Identify Bottlerocket nodes by checking the AMI type. Bottlerocket is a security-hardened OS that affects troubleshooting (no SSH, read-only filesystem).

Look for these values in `amiType` (MNG) or the node `os_image` string:
- `BOTTLEROCKET_x86_64`
- `BOTTLEROCKET_ARM_64`

### GPU Nodes

Detect GPU nodes for clusters running ML/AI workloads.

**Via Kubernetes API:** list `Node` (`v1`) and select nodes whose `status.allocatable` (or labels) include `nvidia.com/gpu`. Record the node names as a fact. RBAC: `get`, `list` on `nodes`.

### Graviton/ARM Nodes

Identify ARM-based Graviton nodes as a fact. Graviton instances use the ARM architecture and require ARM-compatible container images.

Look for these indicators:
- `amiType: AL2_ARM_64` or `AL2023_ARM_64_STANDARD`
- Instance types: `m6g`, `m7g`, `c6g`, `c7g`, `r6g`, `r7g`
