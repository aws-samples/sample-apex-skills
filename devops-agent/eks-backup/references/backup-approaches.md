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
- [Posture Rubric: READY / PARTIAL / UNPROTECTED](#posture-rubric-ready--partial--unprotected)

---

## The Two Approaches at a Glance

An EKS cluster's recoverable state is protected by one (or both) of two mainstream
approaches. This skill assesses both and rates the combined posture.

| Dimension | AWS Backup for EKS | Velero |
|-----------|--------------------|--------|
| Origin | AWS-managed service; GA November 10, 2025 (source: [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/11/aws-backup-supports-amazon-eks/), as of 2026-07-19) | Open-source; recommended by AWS EKS docs as a self-managed alternative (source: [EKS envelope encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html), as of 2026-07-19) |
| In-cluster agent | **None required** — no add-on, no controller pod (source: [AWS Backup EKS backups](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html), as of 2026-07-19) | Requires a controller Deployment installed in-cluster (source: [How Velero works](https://velero.io/docs/main/how-velero-works/), as of 2026-07-19) |
| Assessed via | AWS control-plane API only — **no cluster access needed** | Kubernetes API — controller Deployment + `velero.io` CRDs |
| Backs up | Kubernetes cluster state + metadata + PV data (EBS/EFS/S3 via CSI) | Kubernetes API objects + PV snapshots + file-system backup |
| Where backups land | AWS Backup vault | Object storage (S3) via a BackupStorageLocation |

Neither approach restores etcd or the Kubernetes version — see [Restore ≠ Control-Plane
Rollback](#restore--control-plane-rollback).

---

## AWS Backup for EKS

AWS Backup added support for Amazon EKS at GA on November 10, 2025 (source: [AWS What's
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
- **File System Backup** — file-level backup of volume contents via restic or kopia.

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

## Posture Rubric: READY / PARTIAL / UNPROTECTED

Unlike `eks-recon` (which reports raw detection as facts, no verdict), this skill **does rate
posture**. Combine the AWS Backup half and the Velero half into one verdict using this rubric.

### READY

At least one approach is **confirmed configured AND producing recent recovery points /
backups**. Concretely, either:

- **AWS Backup:** the cluster is assigned to a backup plan (resource assignment covering the
  cluster ARN / resource type `Amazon EKS`) **AND** a recent recovery point exists **AND** the
  last backup job for the cluster succeeded (`COMPLETED`); **or**
- **Velero:** a `BackupStorageLocation` is `Available` **AND** a `Schedule` exists **AND** a
  recent `Backup` completed.

### PARTIAL

A tool is **present or installed but coverage is incomplete or stale.** Examples:

- An AWS Backup plan exists but has **no EKS resource assignment** for this cluster.
- The Velero controller Deployment is present but there is **no Schedule**.
- Recovery points / backups exist but are **older than the plan's (or schedule's) cadence**
  (stale).
- A cluster is brand new: it is assigned to a plan but **no backup job has run yet**.

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
absent, the posture is **PARTIAL-or-unknown** with a note that Velero could not be assessed —
**never** UNPROTECTED.

### CRITICAL RULE — never label UNPROTECTED on unread Velero facts

A cluster is **NEVER** labeled `UNPROTECTED` on the strength of **unread or unconfirmed**
Velero facts. If the Velero CRD reads are `403`-blocked (see `velero-assessment.md`), the AWS
Backup half **stands on its own**, and any Velero gap is reported as **`unconfirmed`** — never
as `false` / "no Velero". In that case the posture note **must state that Velero could not be
fully assessed** (e.g. "Velero coverage unconfirmed — supplementary ClusterRole needed"). A
`403` is an authorization gap in the assessor, not evidence of absence. Distinguish **absence**
(confirmed no resource) from **unconfirmed** (could not read) everywhere in the verdict.
