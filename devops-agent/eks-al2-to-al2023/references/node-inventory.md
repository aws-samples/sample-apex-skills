# Module: Node Inventory (AL2 footprint)

> **Part of:** [eks-al2-to-al2023](../SKILL.md)
> **Purpose:** Detect which nodes and node groups are on Amazon Linux 2 (AL2) vs Amazon Linux 2023 (AL2023), broken down by compute type, and capture the per-node-group launch-template and AMI facts that scope every later migration-risk check

This is the **first** module loaded. It establishes the **AL2 footprint** — the set of
node groups and nodes that still run the AL2 EKS-optimized AMI — which is the scope every
risk (`migration-risks.md`) and runbook path (`runbook.md`) narrows to. It reads facts only;
it never cordons, drains, or changes a node group.

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. Managed Node Group AMI Type](#1-managed-node-group-ami-type)
  - [2. Instance AMI Names (self-managed + verification)](#2-instance-ami-names-self-managed--verification)
  - [3. Launch Templates](#3-launch-templates)
  - [4. Node OS via Kubernetes API](#4-node-os-via-kubernetes-api)
  - [5. Karpenter / Auto Mode AMI family (CRD note)](#5-karpenter--auto-mode-ami-family-crd-note)
- [Lifting the limitation (supplementary ClusterRole)](#lifting-the-limitation-supplementary-clusterrole)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS + EC2) — node-group `amiType` / `releaseVersion` /
  `launchTemplate` (`eks:DescribeNodegroup`), running instance AMI IDs and their names
  (`ec2:DescribeInstances` → `ec2:DescribeImages`), and launch-template `ImageId` / userData /
  IMDS settings (`ec2:DescribeLaunchTemplates`, `ec2:DescribeLaunchTemplateVersions`). These
  require the read-only permissions in `references/iam-policy.json`. **All AL2-vs-AL2023
  detection for managed and self-managed node groups is possible via the AWS API alone.**
- **Kubernetes API** (via the Agent Space EKS access entry) — per-node `status.nodeInfo`
  (`osImage`, `kernelVersion`, `containerRuntimeVersion`) and node labels. Requires
  `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry to
  be present. RBAC verbs needed: `get`, `list` on `nodes`.

If the Kubernetes API is unreachable (access entry absent, or `authenticationMode` excludes
`API`), report whatever the AWS-API calls return — node-group `amiType`, instance AMI names,
launch-template facts — and mark every K8s-dependent sub-fact (per-node `osImage` /
`kernelVersion`, labels) as `unconfirmed` in the report's Coverage section, **never** as
`false` or a false AL2023-clean reading.

> **Reference declarative note.** The "**Via Kubernetes API**" blocks below describe the
> resource, group/version, fields, and RBAC verbs for each K8s-API read. They are **not**
> executable `kubectl ... | jq` pipelines and are not an operational path — the agent reads
> these resources through its Kubernetes-API capability, then applies the described
> classification logic. The "**Via AWS API**" blocks may show example `aws ...` calls.

---

## Detection Strategy

AL2-footprint detection layers three independent signals so no compute type is missed:

```
1. MNG amiType        -> authoritative AL2/AL2023 label for managed node groups
2. Instance AMI name  -> catches self-managed nodes with no node-group amiType
3. Node osImage/kernel -> in-cluster confirmation across ALL nodes (any compute type)
   + Launch templates  -> custom LT? -> drives nodeadm/bootstrap + IMDS risk in module 2
   + Karpenter/AutoMode -> AMI family lives in a CRD (may be 403 -> unconfirmed)
```

The three signals are cross-checked: a node group whose `amiType` says AL2 should have
instances on an `amazon-eks-node-*` AMI and nodes whose `osImage` contains `Amazon Linux 2`.
When signals disagree (e.g. a custom AMI baked from AL2023 attached to a node group whose
`amiType` still reads `CUSTOM`), report each signal as its own fact and mark the AMI family
`unconfirmed` rather than forcing a label.

---

## Detection Capabilities

### 1. Managed Node Group AMI Type

The authoritative AL2/AL2023 label for a managed node group (MNG) is its `amiType`.

**Via AWS API** — list node groups, then describe each for `amiType`, `releaseVersion`, and
`launchTemplate`:

```bash
# List managed node groups for the cluster
aws eks list-nodegroups --cluster-name <cluster-name> \
  --query 'nodegroups' --output text

# Describe each node group
aws eks describe-nodegroup --cluster-name <cluster-name> --nodegroup-name <ng-name> \
  --query 'nodegroup.{amiType:amiType,releaseVersion:releaseVersion,launchTemplate:launchTemplate,instanceTypes:instanceTypes,capacityType:capacityType,status:status}'
```

**`amiType` → OS family mapping:**

| `amiType` value | OS family |
|-----------------|-----------|
| `AL2_x86_64` | **AL2** |
| `AL2_ARM_64` | **AL2** |
| `AL2_x86_64_GPU` | **AL2** |
| `AL2023_x86_64_STANDARD` | **AL2023** |
| `AL2023_ARM_64_STANDARD` | **AL2023** |
| the AL2023 NVIDIA GPU amiType | **AL2023** |
| `BOTTLEROCKET_*` | Bottlerocket (out of AL2→AL2023 scope — see Edge Cases) |
| `CUSTOM` | unknown from `amiType` alone → resolve via the launch-template `ImageId` (section 3) + instance AMI name (section 2); mark `unconfirmed` if still unresolved |

> **UNVERIFIED — AL2023 NVIDIA GPU amiType enum spelling.** The exact enum string AWS uses
> for the AL2023 NVIDIA GPU AMI type (the AL2023 successor to `AL2_x86_64_GPU`) is **not
> verified here**. Do **not** hardcode a guessed value such as `AL2023_x86_64_NVIDIA`. Read
> the `amiType` string **verbatim** from `DescribeNodegroup` and classify any value that
> begins with `AL2023` as AL2023. Record the observed enum string as a fact.

- `releaseVersion` records the specific EKS AMI release the node group is pinned to (a fact;
  useful evidence for the report). For AL2 node groups this is an AL2 release that AWS stopped
  publishing new versions of on 2025-11-26 — see `migration-risks.md`.
- `launchTemplate` (present/absent, id, version) drives the nodeadm/bootstrap and IMDS
  hop-limit risks in `migration-risks.md`; capture it here and resolve its contents in
  section 3.

**Example (one AL2 node group):**
```json
{
  "amiType": "AL2_x86_64",
  "releaseVersion": "1.32.0-20251101",
  "launchTemplate": null,
  "instanceTypes": ["m5.large"],
  "capacityType": "ON_DEMAND",
  "status": "ACTIVE"
}
```

### 2. Instance AMI Names (self-managed + verification)

Self-managed node groups have **no** node-group `amiType`. Their OS family is read from the
AMI backing the running instances. This also cross-checks MNG results.

**Via AWS API** — find the cluster's instances by cluster tag, collect their AMI IDs, then
resolve each AMI's Name:

```bash
# Instances tagged for this cluster (self-managed + MNG nodes both carry the tag)
aws ec2 describe-instances \
  --filters "Name=tag:kubernetes.io/cluster/<cluster-name>,Values=owned,shared" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].{InstanceId:InstanceId,ImageId:ImageId,Lt:Tags[?Key==`aws:ec2launchtemplate:id`].Value|[0]}'

# Resolve AMI names
aws ec2 describe-images --image-ids <ami-id-1> <ami-id-2> \
  --query 'Images[].{ImageId:ImageId,Name:Name}'
```

**AMI Name → OS family mapping (EKS-optimized AMIs):**

| AMI Name pattern | OS family |
|------------------|-----------|
| `amazon-eks-node-<k8s>-*` (no `al2023`) | **AL2** |
| `amazon-eks-arm64-node-*`, `amazon-eks-gpu-node-*` | **AL2** |
| `amazon-eks-node-al2023-*` | **AL2023** |
| `bottlerocket-aws-k8s-*` | Bottlerocket (out of scope) |

- This signal **catches self-managed nodes** that never appear as an MNG `amiType`, and
  custom AMIs whose Name still follows the EKS-optimized naming.
- A custom-baked AMI with a non-standard Name resolves to neither pattern → record the AMI
  Name as a fact and mark the OS family `unconfirmed` (do not guess).

### 3. Launch Templates

Whether a node group uses a **custom launch template** — and whether that template pins an
`ImageId` — is the single biggest driver of migration effort: it decides the
nodeadm/NodeConfig userData rewrite and the IMDS hop-limit default (both in
`migration-risks.md`).

**Via AWS API** — read the launch template and the specific version the node group uses:

```bash
aws ec2 describe-launch-templates --launch-template-ids <lt-id> \
  --query 'LaunchTemplates[].{Id:LaunchTemplateId,Name:LaunchTemplateName,Default:DefaultVersionNumber,Latest:LatestVersionNumber}'

aws ec2 describe-launch-template-versions --launch-template-id <lt-id> --versions <version> \
  --query 'LaunchTemplateVersions[].LaunchTemplateData.{ImageId:ImageId,UserData:UserData,Metadata:MetadataOptions}'
```

- **`ImageId`** — if set, the template pins a specific AMI. Resolve its Name via
  `ec2:DescribeImages` (section 2 mapping) to classify AL2/AL2023. If absent, EKS supplies
  the AMI from the node group `amiType`.
- **`UserData`** — base64-encoded. When it contains `/etc/eks/bootstrap.sh`, this is AL2-style
  bootstrap that must be rewritten to nodeadm `NodeConfig` for AL2023 (see
  `migration-risks.md` → nodeadm/bootstrap). Record its presence as a fact; do not decode and
  emit secrets.
- **`MetadataOptions.HttpPutResponseHopLimit`** — records the IMDS hop limit set on the
  template (evidence for the IMDS risk). When the template does not set it, the default
  depends on whether a custom AMI is used — see `migration-risks.md` → IMDSv2 hop limit.

### 4. Node OS via Kubernetes API

In-cluster confirmation across **all** nodes regardless of compute type (MNG, self-managed,
Karpenter, Auto Mode). This confirms the AWS-API labels and is the only direct signal for
Karpenter/Auto Mode nodes when their CRDs are unreadable.

**Via Kubernetes API** — list nodes and read OS/runtime facts and identifying labels:

- **Resource:** `Node`, group/version `v1` (core), cluster-scoped.
- **Fields to extract:**
  - `status.nodeInfo.osImage` — **AL2** when it contains `Amazon Linux 2` **and NOT** `2023`
    (e.g. `Amazon Linux 2`); **AL2023** when it contains `Amazon Linux 2023`.
  - `status.nodeInfo.kernelVersion` — **AL2** when it contains `amzn2` (AL2 ships kernel
    `5.10`, string contains `amzn2`); **AL2023** kernels are `6.1` / `6.12` (string contains
    `amzn2023`). (Matches the upstream `eks-upgrade-check` node-readiness detection.)
  - `status.nodeInfo.containerRuntimeVersion` — records the containerd version (a fact).
  - `metadata.labels` — `eks.amazonaws.com/nodegroup` (MNG membership),
    `karpenter.sh/nodepool` (Karpenter-owned), `node.kubernetes.io/instance-type`. Use the
    label to attribute each node to a compute type.
- **RBAC verbs:** `get`, `list` on `nodes`.

**Classification precedence:** `osImage` and `kernelVersion` must agree; when both are
present and agree, that is the authoritative in-cluster OS family for the node. A node with no
`eks.amazonaws.com/nodegroup` label and no `karpenter.sh/nodepool` label is **self-managed**
(reconcile with sections 1–2). Nodes attributed to Karpenter/Auto Mode still get their OS
family from `osImage`/`kernelVersion` here even when the driving CRD (section 5) is 403.

### 5. Karpenter / Auto Mode AMI family (CRD note)

For Karpenter- and Auto-Mode-provisioned compute, the **desired** AMI family is declared in a
CustomResourceDefinition, not in a node-group `amiType`:

- **Karpenter `EC2NodeClass`** — group `karpenter.k8s.aws`; the `spec.amiFamily` /
  `spec.amiSelectorTerms` decide whether new nodes come up on AL2 or AL2023.
- **EKS Auto Mode `NodeClass`** — group `eks.amazonaws.com`; declares the managed AMI family.

**CRD read constraint.** Under the `AmazonAIOpsAssistantPolicy` access entry **alone**, these
CRD groups are **not** authorized — reads of `karpenter.k8s.aws`, `karpenter.sh`, and
`eks.amazonaws.com` return `403 Forbidden` (the managed policy grants only built-in API
groups; see SKILL.md and `references/porting-notes.md`). When the CRD read is blocked:

- Report the Karpenter/Auto-Mode desired AMI family as **`unconfirmed`** — never guess
  `AL2` or `AL2023`, and never record `false`.
- You may still classify the **running** Karpenter/Auto-Mode nodes' OS from
  `status.nodeInfo.osImage` / `kernelVersion` (section 4) — that is a separate, allowed
  signal. Report "N Karpenter nodes currently on AL2 (from node osImage); EC2NodeClass AMI
  family unconfirmed (CRD read blocked)". Distinguish the confirmed running-OS fact from the
  unconfirmed desired-AMI fact.
- To confirm the desired AMI family, a supplementary read-only ClusterRole granting
  `get`/`list` on those CRD groups is required (see SKILL.md).

**Fargate** — Fargate pods run on AWS-managed infrastructure with **no** customer AL2/AL2023
node AMI. **Fargate has no AL2 concern** — state this as a fact and exclude Fargate profiles
from the migration scope entirely.

---

## Lifting the limitation (supplementary ClusterRole)

To confirm the **desired** Karpenter / Auto-Mode AMI family (the CRD reads that return `403`
under `AmazonAIOpsAssistantPolicy` alone — see section 5), bind the Agent Space role's
Kubernetes identity to this read-only ClusterRole via a `ClusterRoleBinding` to the same
subject the EKS access entry maps the role to (or associate a broader access policy). It grants
only `get`/`list` on the Karpenter/Auto-Mode CRD groups and on `customresourcedefinitions`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-al2023-migration-crd-readonly
rules:
  - apiGroups: ["karpenter.k8s.aws"]
    resources:
      - ec2nodeclasses
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.sh"]
    resources:
      - nodepools
      - nodeclaims
    verbs: ["get", "list"]
  - apiGroups: ["eks.amazonaws.com"]
    resources:
      - nodeclasses
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources:
      - customresourcedefinitions
    verbs: ["get", "list"]
```

Without this binding (or a broader access policy), the Karpenter/Auto-Mode desired-AMI facts
stay `unconfirmed` and the skill reports this ClusterRole as the fix in the Coverage section.
(This same YAML is documented for maintainers in `references/porting-notes.md`, which is
excluded from the uploaded skill zip — it is duplicated here so the runbook and Coverage note
can surface it at runtime.)

---

## Output Schema

The agent emits this shape (alongside the shared cluster block). Use `null` where a fact was
not detected; use `unconfirmed` counts (not `0`) where a read was blocked. Never omit a key.
This schema is the internal fact structure the markdown migration-readiness report is assembled
from — this skill emits a markdown report plus a runbook, not a separate YAML artifact.

```yaml
al2_footprint:
  scope_summary:
    node_groups_on_al2: int         # count of node groups (any compute type) confirmed on AL2
    nodes_on_al2: int               # count of nodes confirmed AL2 via osImage/kernel or AMI name
    unconfirmed: int                # compute whose OS family could not be confirmed (e.g. CRD 403)

  nodes:                            # per-node in-cluster facts (Kubernetes API), null if K8s unreachable
    total: int
    on_al2: int                     # osImage contains "Amazon Linux 2" not "2023", or kernel contains amzn2
    on_al2023: int                  # osImage contains "Amazon Linux 2023", or kernel 6.1/6.12
    other_or_unconfirmed: int       # Bottlerocket / unread / disagreeing signals
    list:
      - name: string
        os_image: string            # status.nodeInfo.osImage verbatim
        kernel_version: string      # status.nodeInfo.kernelVersion verbatim
        container_runtime: string   # status.nodeInfo.containerRuntimeVersion verbatim
        os_family: string           # al2 | al2023 | bottlerocket | unconfirmed
        compute_type: string        # managed | self-managed | karpenter | auto-mode
        nodegroup: string           # eks.amazonaws.com/nodegroup label, null if not MNG

  node_groups:
    managed:                        # from eks:DescribeNodegroup amiType (authoritative)
      count: int
      on_al2: int
      on_al2023: int
      list:
        - name: string
          ami_type: string          # amiType verbatim (e.g. AL2_x86_64, AL2023_x86_64_STANDARD)
          os_family: string         # al2 | al2023 | unconfirmed (CUSTOM unresolved)
          release_version: string
          launch_template:          # null if the node group uses no custom launch template
            id: string
            version: string
            image_id: string        # LaunchTemplateData.ImageId, null if EKS-supplied
            uses_bootstrap_sh: bool  # userData contains /etc/eks/bootstrap.sh
            imds_hop_limit: int      # MetadataOptions.HttpPutResponseHopLimit, null if unset
    self_managed:                   # instances with no MNG amiType, classified via AMI Name
      count: int
      on_al2: int
      on_al2023: int
      unconfirmed: int              # custom AMI Name matching neither pattern
    karpenter:
      node_count_on_al2: int        # running Karpenter nodes on AL2 (from node osImage) — a fact
      ec2nodeclass_ami_family: string  # al2 | al2023 | unconfirmed (CRD read blocked -> unconfirmed)
    auto_mode:
      node_count_on_al2: int
      nodeclass_ami_family: string  # unconfirmed when CRD read blocked
    fargate:
      profiles: int                 # Fargate has no AL2 concern — excluded from migration scope
```

---

## Edge Cases

### Karpenter / Auto Mode AMI family unconfirmed (CRD blocked)

When `karpenter.k8s.aws` / `eks.amazonaws.com` CRD reads return `403` under
`AmazonAIOpsAssistantPolicy` alone, the **desired** AMI family is `unconfirmed`. Still report
the **running** OS family of Karpenter/Auto-Mode nodes from `status.nodeInfo.osImage`
(section 4) — that is a confirmed, separate fact. Never guess the CRD's `amiFamily`, and never
record it as `false`. A supplementary ClusterRole is required to confirm it.

### Mixed AMIs in one cluster

A single cluster commonly runs several node groups on different AMI families at once (e.g.
`ng-a` on AL2, `ng-b` already on AL2023, plus Karpenter). Report each node group's OS family
independently — do not collapse to a single cluster-wide label. The migration scope is the
**subset** of node groups still on AL2; the AL2023 ones are already done and are reported as a
fact, not re-migrated.

### Bottlerocket nodes

Nodes on a `BOTTLEROCKET_*` `amiType` (or `bottlerocket-aws-k8s-*` AMI Name) run
**Bottlerocket**, which is **neither AL2 nor AL2023**. Bottlerocket is **out of AL2→AL2023
migration scope** — it is not affected by the AL2 EKS AMI deprecation. Report Bottlerocket
node counts as a fact and exclude them from the AL2 footprint and the runbook; do not classify
them as AL2 or AL2023.

### Node group `amiType: CUSTOM`

`CUSTOM` does not by itself reveal the OS family. Resolve it via the launch-template `ImageId`
(section 3) → AMI Name (section 2 mapping), cross-checked against the running nodes' `osImage`
(section 4). If none of those resolve to a known pattern, record the AMI Name / `osImage`
verbatim as facts and mark the OS family `unconfirmed` — do not guess.
