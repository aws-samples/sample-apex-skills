---
title: "Module: Storage"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/storage.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-recon/references/storage.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/storage.md). Edit the source, not this page.
:::

# Module: Storage

> **Part of:** [eks-recon](../)
> **Purpose:** Detect storage configuration — CSI drivers, StorageClasses, PVs, PVCs, snapshots, backup tooling

This module OWNS the canonical PVC block (the workloads module defers PVCs here) and OWNS
backup-tooling detection (Velero / AWS Backup / Kasten K10).

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. CSI Drivers](#1-csi-drivers)
  - [2. StorageClasses](#2-storageclasses)
  - [3. Persistent Volumes (PVs)](#3-persistent-volumes-pvs)
  - [4. Persistent Volume Claims](#4-persistent-volume-claims)
  - [5. Volume Snapshots](#5-volume-snapshots)
  - [6. Backup Tooling](#6-backup-tooling)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

This module reads facts from two sources, both read-only. The storage stack is mostly
in-cluster: `CSIDriver`, `StorageClass`, `PersistentVolume`, `PersistentVolumeClaim`,
`VolumeSnapshotClass`/`VolumeSnapshot`, and the backup-tooling CRDs/deployments are all
**Kubernetes-API** reads. A small amount of CSI add-on status comes from the AWS API:

- **Kubernetes API** (via the Agent Space EKS access entry) — CSIDrivers, StorageClasses,
  PVs, PVCs, VolumeSnapshotClasses/VolumeSnapshots, and backup CRDs/deployments. Requires
  `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry
  to be present. RBAC verbs needed: `get`, `list`.
- **AWS control-plane APIs** (EKS) — EKS-managed CSI **add-on** status/version for
  EBS/EFS/S3-Mountpoint/snapshot-controller (`eks:DescribeAddon`), and Auto Mode block
  storage (`cluster.storageConfig.blockStorage.enabled` via `eks:DescribeCluster`). Requires
  the read-only permissions in `references/iam-policy.json`.

If the Kubernetes API is unreachable (access entry absent), report whatever the AWS-API CSI
add-on calls return and mark every K8s-dependent sub-fact (StorageClasses, PVs, PVCs,
snapshots, in-cluster CSIDriver names, backup tooling) as `unconfirmed` in the report's
Coverage section — never as `false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes
> client)* below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They
> are **not executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its Kubernetes-API
> capability, then applies the described selection/aggregation logic.

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

## Detection Capabilities

### 1. CSI Drivers

Detect which CSI drivers are installed. EKS commonly uses EBS, EFS, and S3 Mountpoint drivers.

**Via AWS API** — check EKS-managed CSI add-on status/version for each managed driver:

```bash
# EBS CSI driver (EKS add-on)
aws eks describe-addon --cluster-name <cluster-name> --addon-name aws-ebs-csi-driver \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null

# EFS CSI driver (EKS add-on)
aws eks describe-addon --cluster-name <cluster-name> --addon-name aws-efs-csi-driver \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null

# S3 Mountpoint CSI driver (EKS add-on)
aws eks describe-addon --cluster-name <cluster-name> --addon-name aws-mountpoint-s3-csi-driver \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null
```

There is **no** EKS-managed add-on for FSx today; FSx is self-managed only and surfaces via
the in-cluster `CSIDriver` object (driver name `fsx.csi.aws.com`, controller Deployment
`aws-fsx-csi-driver`) — see the Kubernetes-API read below.

**Example output (EBS CSI add-on detected):**
```json
{
  "name": "aws-ebs-csi-driver",
  "version": "v1.28.0-eksbuild.1",
  "status": "ACTIVE"
}
```

**Via Kubernetes API** — list all CSI drivers registered in-cluster (includes
self-managed drivers and the Auto Mode-managed variant):

- **Resource:** `CSIDriver`, group/version `storage.k8s.io/v1`.
- **Fields to extract:** `metadata.name`, `spec.attachRequired`.
- **RBAC verbs:** `get`, `list` on `csidrivers.storage.k8s.io`.

**Via Kubernetes API** — detect a self-managed FSx CSI controller:

- **Resource:** `Deployment`, group/version `apps/v1`, label selector
  `app.kubernetes.io/name=aws-fsx-csi-driver`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

**Example (in-cluster CSIDriver names, self-managed / EKS add-on cluster):**
```json
{"name": "ebs.csi.aws.com", "attachRequired": true}
{"name": "efs.csi.aws.com", "attachRequired": false}
{"name": "s3.csi.aws.com", "attachRequired": false}
{"name": "fsx.csi.aws.com", "attachRequired": false}
```

**Example (EKS Auto Mode cluster — note the `.eks.amazonaws.com` EBS name):**
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

**Via AWS API** — check whether EKS Auto Mode manages block storage:

```bash
# Auto Mode includes EBS CSI automatically
aws eks describe-cluster --name <cluster-name> \
  --query 'cluster.storageConfig.blockStorage.enabled'
```

### 2. StorageClasses

Enumerate StorageClasses to understand provisioning options.

**Via Kubernetes API** — list StorageClasses (cluster-scoped):

- **Resource:** `StorageClass`, group/version `storage.k8s.io/v1`.
- **Fields to extract:** `metadata.name`, `provisioner`, `volumeBindingMode`,
  `reclaimPolicy`, `parameters.type` (→ `volume_type`, e.g. `gp2`/`gp3`/`io1`/`io2` for EBS
  classes, null otherwise), `encrypted` = (`parameters.encrypted == "true"`), full
  `parameters`.
- **Default detection:** a StorageClass is the default when EITHER
  `metadata.annotations["storageclass.kubernetes.io/is-default-class"] == "true"` OR the
  **deprecated beta annotation** `storageclass.beta.kubernetes.io/is-default-class == "true"`
  (still present on older clusters) is set. Match both.
- **RBAC verbs:** `get`, `list` on `storageclasses.storage.k8s.io`.

The `storage_classes.count` and `storage_classes.default` (name) facts are derived by the
agent from the enumerated list above — count the items, and select the item(s) whose GA or
deprecated-beta default annotation is `"true"`.

**Example (two storage classes):**
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

### 3. Persistent Volumes (PVs)

Inventory cluster-scoped PVs (VERIFIED live). Capture count, capacity, the actual
`reclaimPolicy`, bound vs Released/orphaned status, provisioner (CSI vs in-tree), and the
backing StorageClass.

**Via Kubernetes API** — list PVs (cluster-scoped):

- **Resource:** `PersistentVolume`, group/version `v1` (core).
- **Fields to extract:** `metadata.name`, `spec.capacity.storage` (→ `capacity`),
  `spec.persistentVolumeReclaimPolicy` (→ `reclaim_policy`), `status.phase` (→ `status`),
  `spec.storageClassName` (→ `storage_class`), `claim` = `<namespace>/<name>` from
  `spec.claimRef` (null when unbound).
- **provisioner:** `spec.csi.driver` when CSI-backed, else the
  `metadata.annotations["pv.kubernetes.io/provisioned-by"]` in-tree provisioner annotation.
- **provisioner_type:** `csi` when `spec.csi` is present, else `in-tree`.
- **Aggregation:** group items by `status.phase` to produce the `by_status` counts
  (Bound / Released / Available / Failed).
- **RBAC verbs:** `get`, `list` on `persistentvolumes`.

**Example (one PV):**
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
- `provisioner_type` distinguishes CSI-provisioned volumes from in-tree provisioners.

### 4. Persistent Volume Claims

Inventory PVCs to understand actual storage usage. This module OWNS the canonical `pvcs`
block; the workloads module defers PVC reporting here.

**Via Kubernetes API** — list PVCs across all namespaces:

- **Resource:** `PersistentVolumeClaim`, group/version `v1` (core), all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.storageClassName`
  (→ `storage_class`), `status.capacity.storage` (→ `capacity`), `status.phase`
  (→ `status`), `spec.accessModes`, `spec.resources.requests.storage` (requested capacity).
- **by_storage_class aggregation:** group items by `spec.storageClassName`; per group record
  count, the joined list of requested capacities, and a status breakdown.
- **by_status aggregation:** count items by `status.phase` (Bound / Pending / Lost).
- **Pending PVCs:** items with `status.phase == Pending`; record each with the
  `storageClassName` it requested (a fact — draw no conclusion).
- **RBAC verbs:** `get`, `list` on `persistentvolumeclaims`.

**Example (by storage class):**
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

### 5. Volume Snapshots

Check snapshot capability. The VolumeSnapshot* CRDs are supplied by the external-snapshotter
project and are NOT installed by default; treat their absence as a clean fact.

**Via Kubernetes API** — detect the external-snapshotter CRDs:

- **Resource:** `CustomResourceDefinition`, group/version `apiextensions.k8s.io/v1`. Select
  CRDs whose name contains `snapshot.storage.k8s.io`. Zero matches = not installed (a fact);
  set `snapshots.snapshot_crds_present: false` and skip the snapshot reads below.
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io`.

**Via Kubernetes API** — detect the snapshot controller:

- **Resource:** `Deployment`, group/version `apps/v1`, name `snapshot-controller`, namespace
  `kube-system`. Presence = controller installed.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

**Via AWS API** — alternatively read the EKS-managed snapshot-controller add-on:

```bash
aws eks describe-addon --cluster-name <cluster-name> --addon-name snapshot-controller \
  --query 'addon.{name:addonName,version:addonVersion,status:status}' 2>/dev/null
```

<!-- UNVALIDATED LIVE: the snapshot.storage.k8s.io CRDs are absent on both Auto Mode/Fargate
     test clusters, so the two reads below were NOT exercised against live resources. The
     field paths are correct per the external-snapshotter API schema. Validate on a cluster
     with the external-snapshotter CRDs installed. -->
**Via Kubernetes API** — list VolumeSnapshotClasses (emit a LIST — name, driver,
deletionPolicy — not just a count):

- **Resource:** `VolumeSnapshotClass`, group/version `snapshot.storage.k8s.io/v1`
  (cluster-scoped).
- **Fields to extract:** `metadata.name`, `driver`, `deletionPolicy` (Delete | Retain).
- **RBAC verbs:** `get`, `list` on `volumesnapshotclasses.snapshot.storage.k8s.io`.

**Via Kubernetes API** — list existing VolumeSnapshots:

- **Resource:** `VolumeSnapshot`, group/version `snapshot.storage.k8s.io/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`,
  `spec.source.persistentVolumeClaimName` (→ `sourcePVC`), `status.readyToUse`,
  `status.restoreSize`. Count for the `volume_snapshots` fact.
- **RBAC verbs:** `get`, `list` on `volumesnapshots.snapshot.storage.k8s.io`.

### 6. Backup Tooling

This module OWNS backup-tooling detection. Report presence of each tool as a boolean fact.
Detection only — record no backup-strategy conclusions.

**Via Kubernetes API** — one-pass CRD scan (VERIFIED — zero matches is itself a fact):

- **Resource:** `CustomResourceDefinition`, group/version `apiextensions.k8s.io/v1`. Select
  CRDs whose name matches (case-insensitive) `velero`, `backup`, `kasten`, or `k10`.
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io`.

**Via Kubernetes API** — Velero (controller deployment + its CRDs):

- **Resource:** `Deployment`, group/version `apps/v1`, label selector
  `app.kubernetes.io/name=velero`, all namespaces. Extract `metadata.namespace`,
  `metadata.name`.
- **Resource:** `BackupStorageLocation` and `Schedule`, group/version `velero.io/v1`, all
  namespaces — presence indicates Velero-managed backup config.
- **RBAC verbs:** `get`, `list` on `deployments.apps`,
  `backupstoragelocations.velero.io`, `schedules.velero.io`.

**Via Kubernetes API** — AWS Backup (in-cluster AWS Backup controller/hook):

- **Resource:** `Deployment`, group/version `apps/v1`, label selector
  `app.kubernetes.io/name in (aws-backup, backup-controller)`, all namespaces. Extract
  `metadata.namespace`, `metadata.name`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

**Via Kubernetes API** — Kasten K10 (installs into the `kasten-io` namespace by default):

- **Resource:** `Deployment`, group/version `apps/v1`, namespace `kasten-io`. Presence
  indicates K10 installed.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

- `velero.detected` = Velero deployment OR its CRDs (backupstoragelocations / schedules) present.
- `aws_backup.detected` = an in-cluster AWS Backup controller/hook present.
- `kasten.detected` = K10 deployments / CRDs present.
- No matching resource for any tool means it is not detected — record `false`, not an error.

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

  pvs:                         # cluster-scoped PV inventory (Kubernetes API: list PVs — VERIFIED live)
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
    snapshot_crds_present: bool    # snapshot.storage.k8s.io CRDs present
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
- Check `cluster.storageConfig.blockStorage.enabled` (AWS API — `eks:DescribeCluster`)
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
requested (from the pending-PVC selection in section 4). State the observation; draw no conclusion.

---

## Shared Cluster Block

The `cluster:` block emitted alongside `storage:` is defined once in
`references/cluster-basics.md` under "## Shared Cluster Block". The `storage-recon` agent
emits it via the pointer in its Output Format section. Do not redefine it here.
