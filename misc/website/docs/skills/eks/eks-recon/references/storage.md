---
title: "Module: Storage"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/storage.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/storage.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/storage.md). Edit the source, not this page.
:::

# Module: Storage

> **Part of:** [eks-recon](../)
> **Purpose:** Detect storage configuration - CSI drivers, StorageClasses, PVs, PVCs, snapshots, backup tooling

This module OWNS the canonical PVC block (the workloads module defers PVCs here) and OWNS
backup-tooling detection (Velero / AWS Backup / Kasten K10).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [1. CSI Drivers](#1-csi-drivers)
  - [2. StorageClasses](#2-storageclasses)
  - [3. Persistent Volumes (PVs)](#3-persistent-volumes-pvs)
  - [4. Persistent Volume Claims](#4-persistent-volume-claims)
  - [5. Volume Snapshots](#5-volume-snapshots)
  - [6. Backup Tooling](#6-backup-tooling)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `describe_eks_resource`, `list_k8s_resources`
- **CLI fallback:** `aws eks`, `kubectl`

---

## Detection Strategy

Storage detection covers the full stack from drivers to volumes:

```
1. CSI Drivers       -> What storage backends are available (EBS, EFS, S3, FSx)
2. StorageClasses    -> How storage is provisioned
3. PVs               -> Cluster-scoped volume inventory (bound/released/orphaned)
4. PVCs              -> What storage is currently claimed
5. Snapshots         -> VolumeSnapshotClasses + snapshot CRD presence
6. Backup Tooling    -> Velero / AWS Backup / Kasten K10 presence
```

---

## Detection Commands

### 1. CSI Drivers

Detect which CSI drivers are installed. EKS commonly uses EBS, EFS, and S3 Mountpoint drivers.

**EKS-Managed CSI Add-ons:**

**MCP:**
```
describe_eks_resource(
  resource_type="addon",
  cluster_name="<cluster-name>",
  resource_name="aws-ebs-csi-driver"
)
```

**CLI:**
```bash
# Check EBS CSI driver (EKS add-on)
aws eks describe-addon --cluster-name <cluster-name> --addon-name aws-ebs-csi-driver \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null

# Check EFS CSI driver (EKS add-on)
aws eks describe-addon --cluster-name <cluster-name> --addon-name aws-efs-csi-driver \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null

# Check S3 Mountpoint CSI driver (EKS add-on)
aws eks describe-addon --cluster-name <cluster-name> --addon-name aws-mountpoint-s3-csi-driver \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null

# Check FSx CSI driver (self-managed only — no EKS-managed add-on exists today).
# Detect via the in-cluster CSIDriver object below; the driver name is fsx.csi.aws.com
# and the controller Deployment is aws-fsx-csi-driver.
kubectl get deploy -A -l app.kubernetes.io/name=aws-fsx-csi-driver -o json 2>/dev/null | \
  jq -r '.items[] | {namespace: .metadata.namespace, name: .metadata.name}'
```

**Example output (EBS CSI detected):**
```json
{
  "name": "aws-ebs-csi-driver",
  "version": "v1.28.0-eksbuild.1",
  "status": "ACTIVE"
}
```

**All CSI Drivers (including self-managed):**
```bash
# List all CSI drivers in cluster
kubectl get csidrivers -o json | jq '.items[] | {name: .metadata.name, attachRequired: .spec.attachRequired}'
```

**Example output (self-managed / EKS add-on cluster):**
```json
{"name": "ebs.csi.aws.com", "attachRequired": true}
{"name": "efs.csi.aws.com", "attachRequired": false}
{"name": "s3.csi.aws.com", "attachRequired": false}
{"name": "fsx.csi.aws.com", "attachRequired": false}
```

**Example output (EKS Auto Mode cluster — note the `.eks.amazonaws.com` EBS name):**
```json
{"name": "ebs.csi.eks.amazonaws.com", "attachRequired": true}
```
Here `ebs.csi.eks.amazonaws.com` maps to the `ebs` block with `managed_by: auto-mode`.

Map CSIDriver names to the schema `csi_drivers` sub-blocks: `ebs.csi.aws.com` → `ebs`,
`efs.csi.aws.com` → `efs`, `s3.csi.aws.com` → `s3`, `fsx.csi.aws.com` → `fsx`. Any other
driver name goes into `other`.

**EKS Auto Mode CSIDriver names (important — do not misclassify):** On EKS Auto Mode the
EBS CSI driver is EKS-managed and registers under a DIFFERENT CSIDriver name,
`ebs.csi.eks.amazonaws.com` (note the `.eks.amazonaws.com` suffix), NOT the self-managed
`ebs.csi.aws.com`. This is the same driver, just the Auto Mode-managed variant — it is a
fact about how it is managed, not a different driver. Map it to the SAME `ebs` block:
- `ebs.csi.aws.com`          → `ebs` block; `managed_by` = `eks-addon` or `self-managed`
- `ebs.csi.eks.amazonaws.com` → `ebs` block; set `csi_drivers.ebs.detected = true` and
  `managed_by = auto-mode`

Treat both names as aliases for the `ebs` block. Do NOT let the Auto Mode name fall into
`other` — doing so produces a false-negative `csi_drivers.ebs.detected = false` on a cluster
where EBS is the default provisioner and backs live PVs. EFS on Auto Mode still uses
`efs.csi.aws.com` (no `.eks.amazonaws.com` variant observed); no change there.

**Check if EKS Auto Mode manages storage:**
```bash
# Auto Mode includes EBS CSI automatically
aws eks describe-cluster --name <cluster-name> \
  --query 'cluster.storageConfig.blockStorage.enabled'
```

### 2. StorageClasses

Enumerate StorageClasses to understand provisioning options.

**CLI:**
```bash
# List all StorageClasses.
# default: match BOTH the GA annotation AND the deprecated beta annotation
# (storageclass.beta.kubernetes.io/is-default-class) still present on older clusters.
# volume_type: read from parameters.type (gp2 | gp3 | io1 | io2 | ...) for EBS classes.
kubectl get storageclasses -o json | jq '.items[] | {
  name: .metadata.name,
  provisioner: .provisioner,
  default: ((.metadata.annotations["storageclass.kubernetes.io/is-default-class"] == "true")
            or (.metadata.annotations["storageclass.beta.kubernetes.io/is-default-class"] == "true")),
  volumeBindingMode: .volumeBindingMode,
  reclaimPolicy: .reclaimPolicy,
  volumeType: .parameters.type,
  encrypted: (.parameters.encrypted == "true"),
  parameters: .parameters
}'
```

**Example output:**
```json
{
  "name": "gp3",
  "provisioner": "ebs.csi.aws.com",
  "default": true,
  "volumeBindingMode": "WaitForFirstConsumer",
  "reclaimPolicy": "Delete",
  "parameters": {"type": "gp3", "encrypted": "true"}
}
{
  "name": "efs-sc",
  "provisioner": "efs.csi.aws.com",
  "default": false,
  "volumeBindingMode": "Immediate",
  "reclaimPolicy": "Delete",
  "parameters": {"provisioningMode": "efs-ap"}
}
```

**Count and identify default:**
```bash
# Count StorageClasses
kubectl get storageclasses --no-headers | wc -l

# Find default StorageClass — match GA OR deprecated beta annotation (older clusters)
kubectl get storageclasses -o json | jq -r '.items[] | select((.metadata.annotations["storageclass.kubernetes.io/is-default-class"] == "true") or (.metadata.annotations["storageclass.beta.kubernetes.io/is-default-class"] == "true")) | .metadata.name'
```

### 3. Persistent Volumes (PVs)

Inventory cluster-scoped PVs. `kubectl get pv` is VERIFIED live. Capture count, capacity,
the actual `reclaimPolicy`, bound vs Released/orphaned status, provisioner (CSI vs in-tree),
and the backing StorageClass.

**CLI:**
```bash
# PV inventory (verified live)
kubectl get pv -o json | jq '.items[] | {
  name: .metadata.name,
  capacity: .spec.capacity.storage,
  reclaimPolicy: .spec.persistentVolumeReclaimPolicy,
  status: .status.phase,
  storageClass: .spec.storageClassName,
  # provisioner: CSI driver name when CSI-backed, else the in-tree provisioner annotation
  provisioner: (.spec.csi.driver // .metadata.annotations["pv.kubernetes.io/provisioned-by"]),
  provisionerType: (if .spec.csi then "csi" else "in-tree" end),
  claim: (if .spec.claimRef then (.spec.claimRef.namespace + "/" + .spec.claimRef.name) else null end)
}'

# Count PVs and group by phase (Bound / Released / Available / Failed)
kubectl get pv -o json | jq -r '.items | group_by(.status.phase)[] | "\(.[0].status.phase): \(length)"'
```

**Example output:**
```json
{
  "name": "pvc-a1b2c3d4",
  "capacity": "10Gi",
  "reclaimPolicy": "Delete",
  "status": "Bound",
  "storageClass": "gp3",
  "provisioner": "ebs.csi.aws.com",
  "provisionerType": "csi",
  "claim": "default/data-postgres-0"
}
```

- `status: Released` = the bound PVC was deleted but the PV (and its underlying volume)
  remains — an orphaned volume when `reclaimPolicy: Retain`. Record these as facts under
  `pvs.by_status.released`.
- A PV with no `claimRef` is unbound (`Available`).
- `provisionerType` distinguishes CSI-provisioned volumes from in-tree provisioners.

### 4. Persistent Volume Claims

Inventory PVCs to understand actual storage usage. This module OWNS the canonical `pvcs`
block; the workloads module defers PVC reporting here.

**CLI:**
```bash
# PVC summary by storage class
kubectl get pvc -A -o json | jq '[
  .items | 
  group_by(.spec.storageClassName) | 
  .[] | 
  {
    storageClass: .[0].spec.storageClassName,
    count: length,
    totalRequested: ([.[].spec.resources.requests.storage] | join(", ")),
    statuses: (group_by(.status.phase) | map({status: .[0].status.phase, count: length}))
  }
]'
```

**Example output:**
```json
[
  {
    "storageClass": "gp3",
    "count": 5,
    "totalRequested": "10Gi, 20Gi, 50Gi, 10Gi, 100Gi",
    "statuses": [{"status": "Bound", "count": 5}]
  },
  {
    "storageClass": "efs-sc",
    "count": 2,
    "totalRequested": "5Gi, 5Gi",
    "statuses": [{"status": "Bound", "count": 2}]
  }
]
```

**Detailed PVC list:**
```bash
# List all PVCs with details
kubectl get pvc -A -o json | jq '.items[] | {
  namespace: .metadata.namespace,
  name: .metadata.name,
  storageClass: .spec.storageClassName,
  capacity: .status.capacity.storage,
  status: .status.phase,
  accessModes: .spec.accessModes
}'
```

**Find pending PVCs (potential issues):**
```bash
kubectl get pvc -A --field-selector status.phase=Pending -o json | jq '.items[] | {
  namespace: .metadata.namespace,
  name: .metadata.name,
  storageClass: .spec.storageClassName
}'
```

### 5. Volume Snapshots

Check snapshot capability. The VolumeSnapshot* CRDs are supplied by the external-snapshotter
project and are NOT installed by default; guard every snapshot query with `2>/dev/null`.

**Snapshot CRD presence (explicit check):**
```bash
# Are the external-snapshotter CRDs installed at all? Zero output = not installed (a fact).
kubectl get crd | grep snapshot.storage.k8s.io
```

**Snapshot Controller:**
```bash
# Check if snapshot controller is installed
kubectl get deploy -n kube-system snapshot-controller 2>/dev/null

# Or check EKS add-on
aws eks describe-addon --cluster-name <cluster-name> --addon-name snapshot-controller \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null
```

<!-- UNVALIDATED LIVE: the snapshot.storage.k8s.io CRDs are absent on both Auto Mode/Fargate
     test clusters, so the two queries below were NOT exercised against live resources. The
     field paths are correct per the external-snapshotter API schema. Validate on a cluster
     with the external-snapshotter CRDs installed. -->
**VolumeSnapshotClasses (emit a LIST — name, driver, deletionPolicy — not just a count):**
```bash
# Use the fully-qualified resource name and guard against the CRD being absent
kubectl get volumesnapshotclasses.snapshot.storage.k8s.io -o json 2>/dev/null | jq '.items[] | {
  name: .metadata.name,
  driver: .driver,
  deletionPolicy: .deletionPolicy
}'
```

**Existing snapshots:**
```bash
# Count snapshots
kubectl get volumesnapshots.snapshot.storage.k8s.io -A --no-headers 2>/dev/null | wc -l

# List snapshots with details
kubectl get volumesnapshots.snapshot.storage.k8s.io -A -o json 2>/dev/null | jq '.items[] | {
  namespace: .metadata.namespace,
  name: .metadata.name,
  sourcePVC: .spec.source.persistentVolumeClaimName,
  readyToUse: .status.readyToUse,
  restoreSize: .status.restoreSize
}'
```

### 6. Backup Tooling

This module OWNS backup-tooling detection. Report presence of each tool as a boolean fact.
Detection only — record no backup-strategy conclusions.

**CRD scan (VERIFIED — zero output is itself a fact):**
```bash
# Detects Velero, Kasten K10, and generic backup CRDs in one pass
kubectl get crd | grep -iE 'velero|backup|kasten|k10'
```

**Velero (deployment + its CRDs):**
```bash
# Controller deployment (any namespace)
kubectl get deploy -A -l app.kubernetes.io/name=velero -o json 2>/dev/null | \
  jq -r '.items[] | {namespace: .metadata.namespace, name: .metadata.name}'

# Velero-specific CRDs / resources: BackupStorageLocation + Schedule
kubectl get backupstoragelocations,schedules -A 2>/dev/null
```

**AWS Backup (in-cluster AWS Backup CSI hook / controller):**
```bash
# AWS Backup for EKS surfaces via the aws-backup / backup-controller components
kubectl get deploy -A -l 'app.kubernetes.io/name in (aws-backup,backup-controller)' -o json 2>/dev/null | \
  jq -r '.items[] | {namespace: .metadata.namespace, name: .metadata.name}'
```

**Kasten K10:**
```bash
# K10 installs into the kasten-io namespace by default
kubectl get deploy -n kasten-io 2>/dev/null
```

- `velero.detected` = Velero deployment OR its CRDs (backupstoragelocations / schedules) present.
- `aws_backup.detected` = an in-cluster AWS Backup controller/hook present.
- `kasten.detected` = K10 deployments / CRDs present.
- Zero output from any command means the tool is not detected — record `false`, not an error.

---

## Output Schema

This is the **single canonical schema** for the storage module — it carries every storage
fact, and it is the authoritative `pvcs` block (the workloads module defers PVCs here). The
`storage-recon` agent emits exactly this shape (plus the shared `cluster:` block from
`references/cluster-basics.md`). Use `null` where a fact was not detected; never omit a key.

```yaml
storage:
  csi_drivers:
    ebs:
      detected: bool
      version: string          # null if not detected
      managed_by: string       # eks-addon | self-managed | auto-mode
    efs:
      detected: bool
      version: string
      managed_by: string       # eks-addon | self-managed
    s3:
      detected: bool
      version: string
      managed_by: string       # eks-addon | self-managed
    fsx:                       # fsx.csi.aws.com — self-managed only (no EKS-managed add-on today)
      detected: bool
      version: string
      managed_by: string       # self-managed
    other:                     # any CSI driver not in the four blocks above
      count: int
      list: list               # CSIDriver names

  storage_classes:
    count: int
    default: string            # name of default StorageClass (GA or deprecated beta annotation), null if none
    list:
      - name: string
        provisioner: string
        volume_type: string    # parameters.type for EBS (gp2 | gp3 | io1 | io2 | ...), null otherwise
        volume_binding_mode: string
        reclaim_policy: string
        encrypted: bool

  pvs:                         # cluster-scoped PV inventory (kubectl get pv — VERIFIED live)
    count: int
    total_capacity: string     # sum/list of capacities across PVs
    by_status:
      bound: int
      released: int            # PVC deleted, PV (and volume) retained — orphaned when reclaimPolicy: Retain
      available: int           # unbound, no claimRef
      failed: int
    list:
      - name: string
        capacity: string
        reclaim_policy: string           # actual .spec.persistentVolumeReclaimPolicy
        status: string                   # Bound | Released | Available | Failed
        storage_class: string
        provisioner: string              # CSI driver name or in-tree provisioner
        provisioner_type: string         # csi | in-tree
        claim: string                    # "<namespace>/<name>" of bound PVC, null if unbound

  pvcs:                        # CANONICAL PVC block (workloads module defers here)
    count: int
    by_storage_class:
      - class: string
        count: int
        total_capacity: string
    by_status:
      bound: int
      pending: int
      lost: int

  snapshots:
    snapshot_crds_present: bool    # kubectl get crd | grep snapshot.storage.k8s.io
    controller_installed: bool
    controller_version: string     # null if not installed
    # UNVALIDATED: snapshot CRDs absent on test clusters — validate on a cluster with the
    # external-snapshotter CRDs installed.
    snapshot_classes:              # LIST, not just a count
      count: int
      list:
        - name: string
          driver: string
          deletion_policy: string  # Delete | Retain
    volume_snapshots: int          # count of VolumeSnapshot objects

  backup_tooling:                  # storage OWNS this — facts only, no backup-strategy advice
    velero:
      detected: bool               # deployment OR BackupStorageLocation/Schedule CRDs present
      version: string
      namespace: string
    aws_backup:
      detected: bool               # in-cluster AWS Backup controller/hook present
    kasten:
      detected: bool               # Kasten K10 (kasten-io namespace / K10 CRDs)
      version: string
```

---

## Edge Cases

### Auto Mode Storage

EKS Auto Mode includes EBS CSI automatically:
- Check `cluster.storageConfig.blockStorage.enabled`
- Don't flag missing EBS CSI add-on if Auto Mode is enabled
- **CSIDriver name is `ebs.csi.eks.amazonaws.com`** (not `ebs.csi.aws.com`). This is the
  Auto Mode-managed EBS driver — map it to the `ebs` block with `managed_by: auto-mode`
  (see section 1). This is a fact about management, not a different driver.
- **Default StorageClass on Auto Mode:** the default class (commonly named `ebs`) uses
  `provisioner: ebs.csi.eks.amazonaws.com`. The StorageClass detection (section 2) and PV
  inventory (section 3) read `.provisioner` / `.spec.csi.driver` verbatim and do NOT key off
  the classic driver name, so default-SC detection and PV provisioner reporting work
  unchanged — just record the Auto Mode driver name as the provisioner fact.

### No Default StorageClass

Record `storage_classes.default: null` as a fact. (PVCs that omit `storageClassName` bind
to whatever the cluster default is; when there is none, they stay `Pending` — report the
`pvcs.by_status.pending` count, draw no conclusion.)

### Pending PVCs

Report pending PVCs as a fact under `pvcs.by_status.pending`, with the storageClassName each
requested (from the pending-PVC query in section 4). State the observation; draw no conclusion.

---

## Shared Cluster Block

The `cluster:` block emitted alongside `storage:` is defined once in
`references/cluster-basics.md` under "## Shared Cluster Block". The `storage-recon` agent
emits it via the pointer in its Output Format section. Do not redefine it here.
