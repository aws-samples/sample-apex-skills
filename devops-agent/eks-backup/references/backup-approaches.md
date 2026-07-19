# Module: Backup Approaches & Posture Rubric

> **Part of:** [eks-backup](../SKILL.md)
> **Purpose:** Define the two backup approaches side by side, what each does and does NOT
> protect, the READY / PARTIAL / UNPROTECTED posture rubric, and the hard limitation that a
> restore is not a control-plane rollback

This module is the conceptual foundation for the skill. Load it first — the two assessment
modules (`aws-backup-assessment.md`, `velero-assessment.md`) produce the raw facts, and this
module's rubric turns those facts into the posture verdict. Every capability or support claim
below carries a source URL and an "as of 2026-07-19" date; do not assert support from memory.

## Table of Contents

- [The Two Approaches at a Glance](#the-two-approaches-at-a-glance)
- [AWS Backup for EKS](#aws-backup-for-eks)
  - [What it backs up](#what-aws-backup-for-eks-backs-up)
  - [What it does NOT cover](#what-aws-backup-for-eks-does-not-cover)
  - [Configuration surface](#aws-backup-for-eks-configuration-surface)
  - [Documented limitations](#aws-backup-for-eks-documented-limitations)
- [Velero](#velero)
  - [What it backs up](#what-velero-backs-up)
  - [Configuration surface](#velero-configuration-surface)
- [Restore ≠ Control-Plane Rollback](#restore--control-plane-rollback)
- [Cluster Data-Shape Detection](#cluster-data-shape-detection)
  - [StatefulSets (stateful workload signal)](#1-statefulsets-stateful-workload-signal)
  - [PVCs and their StorageClasses / volume types](#2-pvcs-and-their-storageclasses--volume-types)
  - [Persistent Volumes (corroboration + orphan/Retain signal)](#3-persistent-volumes-corroboration--orphanretain-signal)
  - [Deriving the data shape](#deriving-the-data-shape)
  - [When the Kubernetes API is unavailable](#when-the-kubernetes-api-is-unavailable)
- [Posture Rubric: READY / PARTIAL / UNPROTECTED](#posture-rubric-ready--partial--unprotected)
  - [READY](#ready)
  - [PARTIAL](#partial)
  - [UNPROTECTED](#unprotected)
  - [CRITICAL RULE](#critical-rule--never-label-unprotected-on-unread-velero-facts)
- [Data-Shape Urgency Dimension](#data-shape-urgency-dimension)
  - [Worked example (facts → verdict → urgency)](#worked-example-facts--verdict--urgency)

---

## The Two Approaches at a Glance

An EKS cluster's recoverable state is protected by one (or both) of two mainstream
approaches. This skill assesses both and rates the combined posture.

| Dimension | AWS Backup for EKS | Velero |
|-----------|--------------------|--------|
| Origin | AWS-managed service; announced November 10, 2025 (source: [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/11/aws-backup-supports-amazon-eks/), as of 2026-07-19) | Open-source; recommended by AWS EKS docs as a self-managed alternative (source: [EKS envelope encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html), as of 2026-07-19) |
| In-cluster agent | **None required** — no add-on, no controller pod (source: [AWS Backup EKS backups](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html), as of 2026-07-19) | Requires a controller Deployment installed in-cluster (source: [How Velero works](https://velero.io/docs/main/how-velero-works/), as of 2026-07-19) |
| Assessed via | AWS control-plane API only — **no cluster access needed** | Kubernetes API — controller Deployment + `velero.io` CRDs |
| Backs up | Kubernetes cluster state + metadata + PV data (EBS/EFS/S3 via CSI) | Kubernetes API objects + PV snapshots + file-system backup |
| Where backups land | AWS Backup vault | Object storage (S3) via a BackupStorageLocation |

Neither approach restores etcd or the Kubernetes version — see [Restore ≠ Control-Plane
Rollback](#restore--control-plane-rollback).

---

## AWS Backup for EKS

AWS Backup announced support for Amazon EKS on November 10, 2025 (source: [AWS What's
New](https://aws.amazon.com/about-aws/whats-new/2025/11/aws-backup-supports-amazon-eks/), as
of 2026-07-19). It is available in all Regions where **both** AWS Backup and Amazon EKS are
available. It is an AWS-managed capability of AWS Backup — there is no in-cluster agent to run.

### What AWS Backup for EKS backs up

Sources: [AWS Backup EKS backups](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html)
and [EKS integration with AWS Backup](https://docs.aws.amazon.com/eks/latest/userguide/integration-backup.html)
(both as of 2026-07-19).

- **Cluster state (Kubernetes manifests):** secrets, configmaps, statefulsets, daemonsets,
  storage classes, replicasets, PVCs, CRDs, roles, and rolebindings.
- **Cluster metadata:** name, IAM role, VPC config, logging, encryption, add-ons, access
  entries, managed node groups, Fargate profiles, and pod identity associations.
- **Persistent storage:** EBS, EFS, and S3 volumes attached via PVCs, supported by the EKS
  CSI driver add-on.

### What AWS Backup for EKS does NOT cover

Source: [AWS Backup EKS backups](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html)
(as of 2026-07-19).

- **Container images** from external repositories (ECR / Docker).
- **EKS infrastructure** such as VPCs and subnets.
- **Auto-generated resources:** nodes, auto-generated pods, events, leases, and jobs.

### AWS Backup for EKS configuration surface

Sources: [AWS Backup EKS backups](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html)
and [EKS access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html)
(both as of 2026-07-19).

- **No in-cluster agent or EKS add-on is required.** AWS Backup operates through the AWS
  control plane.
- The cluster's `authenticationMode` **must be `API` or `API_AND_CONFIG_MAP`** so AWS Backup
  can create an EKS **access entry** for itself.
- **IAM roles:** the managed policy `AWSBackupServiceRolePolicyForBackup` (plus
  `AWSBackupServiceRolePolicyForS3Backup` when S3 PVs are in scope) for backup; and
  `AWSBackupServiceRolePolicyForRestores` for restore.
- **EKS access policy:** `AWSBackupFullAccessPolicyForBackup` grants AWS Backup its in-cluster
  permissions via the access entry it creates.
- **Constructs:** a backup vault, a backup plan, and a resource assignment (resource type
  `Amazon EKS`) — or an ad-hoc job via
  `aws backup start-backup-job --resource-arn arn:aws:eks:<region>:<account>:cluster/<name>`.

### AWS Backup for EKS documented limitations

Source: [AWS Backup EKS backups — Limitations](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html)
(as of 2026-07-19).

- In-tree plugins, CSI-migration volumes, and ACK-controller-provisioned PVs are **not
  supported**.
- S3 PV backup is **whole-bucket snapshot only** — no prefix-scoped backups.
- **No cross-account EFS** backup via the EKS integration.
- **No EFS non-root subpath** mounts.
- **No FSx-via-CSI** support.
- **Not supported on EKS on Outposts.**
- Subject to AWS Backup service quotas.
- Metrics API groups (`metrics.k8s.io`) may be skipped, producing a
  **"Completed with issues"** job status.

---

## Velero

Velero is an open-source backup tool; the AWS EKS documentation recommends it as a
self-managed alternative for cluster backup and migration (source: [EKS envelope
encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html), as of
2026-07-19).

### What Velero backs up

Sources: [How Velero works](https://velero.io/docs/main/how-velero-works/) and [EKS envelope
encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html) (both
as of 2026-07-19).

- **Kubernetes API objects** — captured as a tarball written to object storage.
- **Persistent-volume snapshots** — via the cloud provider or CSI snapshot APIs.
- **File System Backup** — file-level backup of volume contents via Kopia (the restic uploader was deprecated in Velero v1.15 and removed for new backups in v1.17; Kopia is the only supported uploader as of the current v1.18 release, as of 2026-07-19; source: https://velero.io/docs/main/file-system-backup/).

### Velero configuration surface

- **Deployment:** installed via the `velero install` CLI or a Helm chart; needs an S3 bucket,
  a `BackupStorageLocation`, and IRSA or EKS Pod Identity for AWS credentials (source: [How
  Velero works](https://velero.io/docs/main/how-velero-works/), as of 2026-07-19).
- **CRDs (group/version `velero.io/v1`):** `Backup`, `Restore`, `Schedule`,
  `BackupStorageLocation`, `VolumeSnapshotLocation` (source: [Velero API
  types](https://velero.io/docs/main/api-types/), as of 2026-07-19). These CRDs hold the proof
  that backups are configured and current, and are the reads that a plain
  `AmazonAIOpsAssistantPolicy` association cannot see (see `velero-assessment.md`).

---

## Restore ≠ Control-Plane Rollback

**Confirmed for both tools.** A backup/restore is **not** a control-plane rollback.

- Both AWS Backup for EKS and Velero restore **Kubernetes API objects plus persistent-volume
  data** into a **running** cluster — one that is pre-provisioned or freshly created. They do
  **not** restore etcd, and they do **not** roll back the cluster's Kubernetes version.
- An AWS Backup for EKS restore is explicitly **non-destructive** and **will not overwrite the
  target cluster's Kubernetes version** (source: [Restoring
  EKS](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-eks.html), as of
  2026-07-19).
- EKS etcd is **AWS-managed and envelope-encrypted**; customers never restore etcd directly
  (source: [EKS envelope
  encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html), as
  of 2026-07-19).

This skill assesses **data / object recoverability only**. Never describe any backup tool as
restoring etcd or rolling back a Kubernetes version — state this limitation wherever recovery
is discussed in the report or runbook.

---

## Cluster Data-Shape Detection

The posture verdict (below) says whether backup **tooling** is configured; it is blind to
**what data the cluster actually holds**. Two clusters can both be `UNPROTECTED`, yet one runs
databases on EBS volumes (losing the cluster destroys data that lives nowhere else) while the
other is purely stateless (every object is reconstructible from GitOps/IaC). The **urgency** of
closing an identical tooling gap differs sharply between them. This section detects the
cluster's data shape via read-only Kubernetes-API reads; the [urgency
dimension](#data-shape-urgency-dimension) then combines it with the verdict.

All reads here are on **built-in API groups that `AmazonAIOpsAssistantPolicy` authorizes** —
`apps` (StatefulSets), core (`persistentvolumeclaims`, `persistentvolumes`), and
`storage.k8s.io` (`storageclasses`). **No CRD, no `apiextensions.k8s.io`, and no new AWS IAM
action** is involved — these are the same authorized reads the Velero controller-Deployment
probe relies on (contrast the `velero.io` CRDs, which `403`). If Step 0 Action 3 set
`k8s_api_available: false`, **every** data-shape fact below is `unconfirmed` (see
[the unavailable case](#when-the-kubernetes-api-is-unavailable)) — never `count: 0`.

> **Declarative-read note.** The blocks below describe each read as a resource + group/version
> + fields + RBAC verbs. They are **not** executable `kubectl` pipelines. The agent reads these
> through its Kubernetes-API capability and applies the described aggregation.

### 1. StatefulSets (stateful workload signal)

**Authorized under `AmazonAIOpsAssistantPolicy`** (the `apps` group — same group as the Velero
controller probe).

**Via Kubernetes API** — list StatefulSets across all namespaces:

- **Resource:** `StatefulSet`, group/version `apps/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.replicas`,
  `spec.volumeClaimTemplates[].spec.storageClassName` (→ the StorageClass each per-replica PVC
  provisions from), `spec.volumeClaimTemplates[].spec.resources.requests.storage`.
- **RBAC verbs:** `get`, `list` on `statefulsets.apps`.
- **Result fact:** `statefulsets.count`, and the set of StorageClasses their
  `volumeClaimTemplates` reference. A non-zero count with volumeClaimTemplates is the strongest
  "this cluster holds data that node/cluster loss would destroy" signal.

### 2. PVCs and their StorageClasses / volume types

**Authorized under `AmazonAIOpsAssistantPolicy`** (core group).

**Via Kubernetes API** — list PVCs across all namespaces, then the StorageClasses they name:

- **Resource:** `PersistentVolumeClaim`, group/version `v1` (core), all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.storageClassName`,
  `status.phase` (Bound | Pending), `status.capacity.storage`.
- **Resource:** `StorageClass`, group/version `storage.k8s.io/v1` (cluster-scoped).
- **Fields to extract:** `metadata.name`, `provisioner`, `parameters.type` (EBS volume type
  `gp3`/`gp2`/`io1`/`io2` when the provisioner is an EBS driver; null otherwise).
- **RBAC verbs:** `get`, `list` on `persistentvolumeclaims` and `storageclasses.storage.k8s.io`.
- **Volume-type classification** — map each bound PVC to its backing technology via the
  StorageClass `provisioner` (and, for EBS, `parameters.type`):
  - `ebs.csi.aws.com` / `ebs.csi.eks.amazonaws.com` (Auto Mode) → **EBS** (record gp3/gp2/io*).
  - `efs.csi.aws.com` → **EFS**.
  - `s3.csi.aws.com` → **S3 (Mountpoint)**.
  - `fsx.csi.aws.com` → **FSx** (note: **not** supported by AWS Backup for EKS — see
    Limitations; Velero file-system backup is the fallback).
  - any other provisioner → **other CSI** (record the driver name).
- **Result fact:** `pvcs.count` (bound), and a `by_volume_type` breakdown (ebs / efs / s3 /
  fsx / other, with counts). EBS/EFS-backed bound PVCs are the volume-level data that a
  volume-aware backup (AWS Backup EKS resource assignment, or Velero + CSI snapshots) protects.

### 3. Persistent Volumes (corroboration + orphan/Retain signal)

**Authorized under `AmazonAIOpsAssistantPolicy`** (core group).

**Via Kubernetes API** — list PVs (cluster-scoped):

- **Resource:** `PersistentVolume`, group/version `v1` (core).
- **Fields to extract:** `spec.csi.driver`, `spec.persistentVolumeReclaimPolicy`,
  `status.phase` (Bound | Released | Available), `spec.capacity.storage`.
- **RBAC verbs:** `get`, `list` on `persistentvolumes`.
- **Result fact:** corroborates the PVC volume-type mix from the backing side, and surfaces
  `Released`/`Retain` PVs (data that outlived its claim). A cluster whose PVs would be
  destroyed on node replacement / cluster loss (CSI-backed, not externally replicated) is the
  data at risk.

### Deriving the data shape

From the three reads, classify the cluster into one shape (a deterministic fact, not advice):

- **Stateful — persistent data at risk:** `statefulsets.count > 0` **OR** any bound PVC on
  EBS/EFS/S3/FSx/other-CSI. Record the volume-type mix. This is data whose only copy may be the
  cluster's volumes.
- **Stateless:** StatefulSets read **succeeded and returned zero** **AND** PVC read
  **succeeded and returned zero bound PVCs**. Only Deployments/DaemonSets/etc. with no
  persistent claims. K8s objects are reconstructible from GitOps/IaC; there is no volume data
  to lose. (Assert "stateless" only on **successful** zero reads — never on an unavailable API.)

`data_shape` fact: `stateful` | `stateless` | `unconfirmed`.

### When the Kubernetes API is unavailable

If `k8s_api_available: false` (Step 0 Action 3), the StatefulSet/PVC/PV/StorageClass reads did
not run. Set `data_shape: unconfirmed` and every sub-fact to `unconfirmed` in Coverage with the
reason ("K8s API unreachable — data shape not assessed"). **Never** infer `stateless` or
`count: 0` from an unavailable API, and **never** downgrade urgency on unread data-shape facts
— treat urgency as **at least the tooling verdict warrants**, and note that the data shape could
not be assessed. This mirrors the unconfirmed-never-false discipline used for Velero CRDs.

If one workload read succeeds while another returns 403/partial (e.g. StatefulSets readable but
PVCs blocked), set `data_shape: unconfirmed` — do not classify on a partial read.

---

## Posture Rubric: READY / PARTIAL / UNPROTECTED

Unlike `eks-recon` (which reports raw detection as facts, no verdict), this skill **does rate
posture**. Combine the AWS Backup half and the Velero half into one verdict using this rubric. The combined verdict is the **stronger of the two halves** (`READY` > `PARTIAL` > `UNPROTECTED`): if either approach is `READY`, the cluster is `READY`; else if either is `PARTIAL`, it is `PARTIAL`; `UNPROTECTED` only when both halves are confirmed-absent per the rule below. An `unconfirmed` half never pulls the verdict down. **When one half is confirmed-absent and the other is `unconfirmed`** (the common AWS-Backup-absent + Velero-CRDs-403 case), the verdict is neither READY nor UNPROTECTED — emit **`PARTIAL`** (deterministic — never "UNPROTECTED", because the unconfirmed half could still hold protection, and never READY, because no protection was confirmed) with a mandatory Coverage note naming which half is confirmed-absent and which is unconfirmed plus the fix for the unconfirmed half (see the CRITICAL RULE and the "unconfirmed" handling below). If **both** halves are `unconfirmed` (AWS Backup API calls failed AND the K8s API was unreachable), emit no posture verdict — report `posture: unknown` with a Coverage note that neither half could be assessed, and the error output from Step 0.

### READY

At least one approach is **confirmed configured AND producing recent recovery points /
backups**. Concretely, either:

- **AWS Backup:** the cluster is assigned to a backup plan (resource assignment covering the
  cluster ARN / resource type `Amazon EKS`) **AND** a recovery point exists within the plan's
  backup-frequency window (not stale — see PARTIAL) **AND** the
  last backup job for the cluster succeeded (`COMPLETED`); **or**
- **Velero:** a `BackupStorageLocation` is `Available` **AND** a `Schedule` exists **AND** a
  `Backup` completed within the Schedule's cron cadence (not stale).

### PARTIAL

A tool is **present or installed but coverage is incomplete or stale.** Examples:

- An AWS Backup plan exists but has **no EKS resource assignment** for this cluster.
- The Velero controller Deployment is present but there is **no Schedule**.
- Recovery points / backups exist but are **older than the plan's (or schedule's) cadence**
  (stale).
- A cluster is brand new: it is assigned to a plan but **no backup job has run yet**.
- **One half confirmed-absent, the other `unconfirmed`** (e.g. AWS Backup confirmed absent and
  Velero's `velero.io` CRDs returned 403): PARTIAL per the combinator — no protection was
  confirmed, but the unconfirmed half could still hold some, so it is neither READY nor
  UNPROTECTED. Emit the mandatory Coverage note naming the unconfirmed half + its fix.

### UNPROTECTED

**No confirmed backup mechanism** exists for the cluster. This verdict requires **all** of the
following to be **confirmed absent** — it can never be reached on unconfirmed/unread facts:

- **AWS Backup confirmed-absent:** no resource assignment covering the cluster AND no recovery
  points (both AWS-API-confirmable facts, per `aws-backup-assessment.md`); **AND**
- **Velero confirmed-absent:** the controller Deployment read **succeeded and found nothing**
  AND the `velero.io` CRD scan **read SUCCEEDED and returned zero** `velero.io` CRDs (per
  `velero-assessment.md`).

By this definition, a `403`-blocked / **unconfirmed** Velero can **never** yield `UNPROTECTED`
— the Velero-confirmed-absent condition is not met, so the verdict cannot be UNPROTECTED,
independent of the CRITICAL RULE prose below. If Velero is **unconfirmed** and AWS Backup is
absent, the posture is **`PARTIAL`** (deterministic, per the combinator above) with a mandatory
Coverage note that Velero could not be assessed — **never** UNPROTECTED, and never READY.

### CRITICAL RULE — never label UNPROTECTED on unread Velero facts

A cluster is **NEVER** labeled `UNPROTECTED` on the strength of **unread or unconfirmed**
Velero facts. If the Velero CRD reads are `403`-blocked (see `velero-assessment.md`), the AWS
Backup half **stands on its own**, and any Velero gap is reported as **`unconfirmed`** — never
as `false` / "no Velero". In that case the posture note **must state that Velero could not be
fully assessed** (e.g. "Velero coverage unconfirmed — supplementary ClusterRole needed"). A
`403` is an authorization gap in the assessor, not evidence of absence. Distinguish **absence**
(confirmed no resource) from **unconfirmed** (could not read) everywhere in the verdict.

---

## Data-Shape Urgency Dimension

The `READY` / `PARTIAL` / `UNPROTECTED` verdict measures **tooling**; it does **not** change
based on data shape. This dimension is **additive** — it does **not** alter the verdict
definitions above. It answers *"how urgent is closing this gap?"* by combining the verdict with
the [detected data shape](#cluster-data-shape-detection). Report it as a distinct
`urgency:` line alongside the posture, and let it drive which runbook branch `runbook.md` emits.

**Deterministic urgency table** (verdict × data shape):

| Verdict | Stateful (StatefulSets and/or EBS/EFS/other-CSI PVs) | Stateless (no StatefulSets and no bound PVCs, confirmed) | Data shape `unconfirmed` |
|---------|------------------------------------------------------|--------------------------------|--------------------------|
| **UNPROTECTED** | **HIGH** — persistent data with no backup; a lost volume/cluster is unrecoverable. Prioritize **volume-level** backup now (AWS Backup EKS resource assignment covering the PVs, or Velero + CSI snapshots). | **LOW** — no volume data to lose; K8s objects are reconstructible from GitOps/IaC. Still worth **object-level** backup for fast namespace re-creation, but not an emergency. | **HIGH** (do not downgrade) — treat as at-least-HIGH; note data shape unassessed. Never label lower-urgency on unread facts. |
| **PARTIAL** | **HIGH** if the gap leaves volumes uncovered (plan assigned but PVs not in scope, or Velero has no CSI/file-system volume backup); else **MEDIUM**. | **LOW** — close the object-backup gap at normal cadence. | **MEDIUM** (do not downgrade) — note data shape unassessed. |
| **READY** | **LOW** — but first verify volume coverage (confirm the recovery points/backups actually include the EBS/EFS PV data, not just K8s objects), then schedule a periodic restore test. | **LOW** — periodic restore test. | **LOW** — verify volume coverage; note data shape unassessed. |

**Rules:**

1. **Urgency never overrides the verdict.** A stateless `UNPROTECTED` cluster is still
   `UNPROTECTED`; only its *urgency* is `LOW`.
2. **Never downgrade urgency on unread data-shape facts.** If `data_shape: unconfirmed`
   (K8s API unavailable), urgency is **at least** what the verdict alone warrants, and the note
   states the data shape could not be assessed — mirroring the unconfirmed-never-false rule.
3. **Stateful + no volume-level backup is the top-priority finding this skill emits.** Call it
   out explicitly with the detected volume-type mix (e.g. "3 StatefulSets on gp3 EBS, 0 recovery
   points, no Velero volume snapshots → HIGH").
4. **FSx-backed PVs on the AWS Backup path:** AWS Backup for EKS does **not** support FSx-via-CSI
   (see Limitations). If FSx PVs are present, note that Velero file-system backup is the volume
   protection path for them even under an otherwise-AWS-Backup posture.

### Worked example (facts → verdict → urgency)

Two walkthroughs a second agent should reproduce identically from the same facts:

1. **PARTIAL case.** AWS Backup: plan `daily-eks` exists but no resource assignment covers the
   cluster ARN (confirmed via list-protected-resources). Velero: controller Deployment present in
   ns `velero`, but Schedule/BSL CRD reads returned 403 (unconfirmed). Data shape: 3 StatefulSets
   on gp3 EBS PVCs (confirmed) → stateful. → AWS Backup half = PARTIAL (plan but no assignment).
   Velero half = unconfirmed. Combined = PARTIAL (stronger-of-two; unconfirmed never downgrades).
   Urgency = HIGH (PARTIAL × stateful with volumes uncovered — the plan doesn't cover the PVs).
   Runbook leads with the AWS Backup resource-assignment path covering the EBS PVs.
2. **UNPROTECTED × stateless case.** AWS Backup: no plan, no recovery points (confirmed absent via
   API). Velero: controller Deployment read succeeded and found nothing AND velero.io CRD scan read
   succeeded returning zero CRDs (confirmed absent). Data shape: 0 StatefulSets, 0 bound PVCs (both
   reads succeeded) → stateless. → both halves confirmed-absent → Combined = UNPROTECTED.
   Urgency = `LOW` (no volume data to lose; K8s objects reconstructible from GitOps/IaC). Runbook
   recommends object-level backup for fast namespace re-creation, not an emergency.
