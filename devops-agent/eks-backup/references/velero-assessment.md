# Module: Velero Assessment

> **Part of:** [eks-backup](../SKILL.md)
> **Purpose:** Detect Velero posture — controller Deployment, BackupStorageLocation,
> Schedules, and recent Backups — via the Kubernetes API, honoring the CRD-`403` limitation

This module reads Velero posture through the **Kubernetes API**. Load `backup-approaches.md`
first for what Velero backs up (with sources) and the posture rubric. The central caveat here:
the Velero **controller Deployment is readable**, but Velero's `velero.io` **CRDs are not**
under the managed policy alone — so the facts that prove backups are configured and current
are `unconfirmed` unless a supplementary ClusterRole is bound.

## Table of Contents

- [Access Model](#access-model)
- [Lifting the limitation (supplementary ClusterRole)](#lifting-the-limitation-supplementary-clusterrole)
- [Detection Capabilities](#detection-capabilities)
  - [1. Velero controller Deployment](#1-velero-controller-deployment)
  - [2. BackupStorageLocation](#2-backupstoragelocation)
  - [3. Schedules](#3-schedules)
  - [4. Recent Backups](#4-recent-backups)
  - [5. Velero CRD scan](#5-velero-crd-scan)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

Velero posture requires **Kubernetes-API reads** through the Agent Space EKS access entry
(binding the role to the AWS-managed `AmazonAIOpsAssistantPolicy` at cluster scope). The
cluster's `authenticationMode` must include `API`. RBAC verbs needed throughout: `get`, `list`.

**What is and is not authorized under `AmazonAIOpsAssistantPolicy` alone:**

- The **Velero controller Deployment is READABLE** — the `apps` API group is authorized. This
  is a strong presence signal.
- The **`velero.io` CRDs are NOT readable**, and neither is `apiextensions.k8s.io`. The managed
  policy grants **no CRD groups**. Consequently the `BackupStorageLocation`, `Schedule`, and
  `Backup` reads — and the CRD scan — return **`403 Forbidden`**.
- When those reads `403`, the corresponding facts are reported as **`unconfirmed`** with the
  reason, **never** as `false` / "no Velero" / `count: 0`. Distinguish absence from unconfirmed.
- To confirm full Velero posture, bind the Agent Space role to a **supplementary read-only
  ClusterRole** granting `get`/`list` on `backups.velero.io`, `restores.velero.io`,
  `schedules.velero.io`, `backupstoragelocations.velero.io`,
  `volumesnapshotlocations.velero.io`, and `customresourcedefinitions.apiextensions.k8s.io`
  (exact YAML in [Lifting the limitation](#lifting-the-limitation-supplementary-clusterrole)
  below), or associate a broader access policy.

If the Kubernetes API is entirely unreachable (access entry absent, or `authenticationMode`
excludes `API`), record the whole Velero half as `unconfirmed`/`unavailable` in Coverage — the
AWS Backup half (see `aws-backup-assessment.md`) still stands on its own.

---

## Lifting the limitation (supplementary ClusterRole)

The `403` on `velero.io` CRD reads is an authorization gap, not evidence of absence. To confirm
full Velero posture, bind the Agent Space role's **Kubernetes identity** to the read-only
ClusterRole below (or associate a broader access policy). This is the authoritative runtime
copy — surface it to the user when Velero sub-facts come back `unconfirmed`.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-backup-velero-readonly
rules:
  - apiGroups: ["velero.io"]
    resources:
      - backups
      - restores
      - schedules
      - backupstoragelocations
      - volumesnapshotlocations
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources:
      - customresourcedefinitions
    verbs: ["get", "list"]
```

**Bind it to the Agent Space role's Kubernetes identity** via a `ClusterRoleBinding` to the
same subject the **EKS access entry** maps the Agent Space role to (the group/username the
access entry assigns). Without this binding (or a broader access policy), the Velero CRD
sub-facts stay `unconfirmed`, and the skill reports this ClusterRole as the fix in the posture
note and Coverage section.

---

> **Declarative-read note.** The capability blocks below describe each Kubernetes-API read as a
> resource + group/version + fields + RBAC verbs — they are **not** executable `kubectl`
> pipelines. The agent reads these resources through its Kubernetes-API capability and applies
> the described selection/aggregation logic. Do not emit `kubectl ... | jq`.

---

## Detection Capabilities

### 1. Velero controller Deployment

**Authorized under `AmazonAIOpsAssistantPolicy`** (the `apps` group). This is the presence
signal that survives even when every CRD read is blocked.

**Via Kubernetes API** — detect the Velero controller Deployment:

- **Resource:** `Deployment`, group/version `apps/v1`, label selector
  `app.kubernetes.io/name=velero`, **all namespaces**.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `status.availableReplicas`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.
- **Result fact:** `controller_detected: true` (with `namespace`) when the Deployment is
  found. This alone does **not** prove backups are configured or current — that requires the
  CRD reads below.

### 2. BackupStorageLocation

**CRD read — `403` under the managed policy alone → `unconfirmed`.**

**Via Kubernetes API** — read the BackupStorageLocation objects:

- **Resource:** `BackupStorageLocation`, group/version `velero.io/v1`, all namespaces.
- **Fields to extract:** `metadata.name`, `spec.provider`, `spec.objectStorage.bucket`,
  `status.phase` (`Available` | `Unavailable`).
- **RBAC verbs:** `get`, `list` on `backupstoragelocations.velero.io`.
- **Result fact:** `backup_storage_location.phase` when readable; `unconfirmed` (with reason
  "velero.io CRD read 403 under AmazonAIOpsAssistantPolicy") when the read is blocked.

### 3. Schedules

**CRD read — `403` under the managed policy alone → `unconfirmed`.**

**Via Kubernetes API** — read the Schedule objects (proof that recurring backups are set up):

- **Resource:** `Schedule`, group/version `velero.io/v1`, all namespaces.
- **Fields to extract:** `metadata.name`, `spec.schedule` (the cron cadence),
  `status.lastBackup`.
- **RBAC verbs:** `get`, `list` on `schedules.velero.io`.
- **Result fact:** `schedules` list (names + cadences) when readable; `unconfirmed` when
  blocked. A controller present with **no Schedule** is a PARTIAL signal — but only assert
  "no Schedule" when the read actually **succeeded** and returned zero; a `403` is
  `unconfirmed`, not zero.

### 4. Recent Backups

**CRD read — `403` under the managed policy alone → `unconfirmed`.**

**Via Kubernetes API** — read the Backup objects (proof backups actually ran and how recently):

- **Resource:** `Backup`, group/version `velero.io/v1`, all namespaces.
- **Fields to extract:** `metadata.name`, `status.phase`
  (`Completed` | `PartiallyFailed` | `Failed` | `InProgress`), and the **most-recent
  `status.completionTimestamp`**.
- **RBAC verbs:** `get`, `list` on `backups.velero.io`.
- **Result fact:** `recent_backup` (phase + most-recent completionTimestamp) when readable;
  `unconfirmed` when blocked. The most-recent completion drives the stale-vs-recent test in
  the rubric.

### 5. Velero CRD scan

**CRD read — `403` under the managed policy alone → `unconfirmed`.**

**Via Kubernetes API** — confirm the Velero CRDs are installed:

- **Resource:** `CustomResourceDefinition`, group/version `apiextensions.k8s.io/v1`. Select
  CRDs whose `metadata.name` contains `velero.io`.
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io`.
- **Result fact:** corroborates a Velero install. When the `apiextensions.k8s.io` read itself
  `403`s, this is `unconfirmed` — a blocked scan is **not** evidence that Velero is absent.

---

## Output Schema

The schema below is the **internal fact structure** the markdown posture report is assembled
from — this skill emits a markdown report + runbook, not a separate YAML artifact.

The agent emits this `velero:` block. Every CRD-derived sub-fact is either the read value or
the literal token `unconfirmed` (with a reason recorded in Coverage) — never `false`/`0` when
the read was blocked.

```yaml
velero:
  controller_detected: bool          # Velero Deployment found (apps group — authorized)
  namespace: string                  # namespace of the controller, null if not detected
  backup_storage_location:           # CRD read — may be unconfirmed (403)
    detected: string                 # true | false | unconfirmed
    phase: string                    # Available | Unavailable | unconfirmed
  schedules:                         # CRD read — may be unconfirmed (403)
    detected: string                 # true | false | unconfirmed
    list: list                       # [{name, cadence}], or "unconfirmed"
  recent_backup:                     # CRD read — may be unconfirmed (403)
    detected: string                 # true | false | unconfirmed
    phase: string                    # Completed | PartiallyFailed | Failed | unconfirmed
    most_recent: string              # completionTimestamp, or "unconfirmed"
  crds_present: string               # true | false | unconfirmed (apiextensions.k8s.io read)
```

---

## Edge Cases

### Controller present but all CRD reads `403`

`controller_detected: true`, and every CRD-derived sub-fact (`backup_storage_location`,
`schedules`, `recent_backup`, `crds_present`) is `unconfirmed`. Posture note: **"Velero
present but coverage unconfirmed — bind the supplementary ClusterRole"** (see
[Lifting the limitation](#lifting-the-limitation-supplementary-clusterrole) above). Do **not**
contribute a Velero gap to an UNPROTECTED verdict on these
unread facts — the AWS Backup half decides posture, and the Velero gap is flagged
`unconfirmed`.

### No controller AND no CRDs readable

- If the controller read **succeeded** and found nothing **and** the CRD scan **succeeded** and
  found no `velero.io` CRDs → Velero **not detected** (a confirmed fact; `detected: false`).
- If the CRD scan itself **`403`'d**, the CRD half is **`unconfirmed`, not `false`** — the
  absence of the controller is a fact, but "no Velero CRDs" cannot be asserted from a blocked
  read. Report `crds_present: unconfirmed` and note it in Coverage.
