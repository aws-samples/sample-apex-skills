---
name: eks-backup
description: EKS backup-readiness posture assessment — evaluates how well an EKS cluster is
  protected across BOTH AWS Backup for EKS and Velero, then emits a guided, human-executed
  runbook. Detects AWS Backup coverage (backup plans, resource assignments for the cluster,
  recovery points, vaults, the EKS access entry) via read-only AWS APIs, and Velero posture
  (controller, BackupStorageLocation, Schedules, its CRDs) via the Kubernetes API. Reports a
  READY / PARTIAL / UNPROTECTED posture with evidence, and a runbook to close gaps. Triggers
  on "is my cluster backed up", "EKS backup", "disaster
  recovery for EKS", "set up Velero", "AWS Backup for EKS", "can I restore my cluster",
  "backup readiness". Read-only — it assesses and emits a runbook; it never runs a backup or
  restore. Route elsewhere for raw backup-tool detection as one fact among many (eks-recon),
  or storage/volume inventory (eks-recon storage). Restore ≠ control-plane rollback (stated
  as a hard limitation, not a capability).
---

# EKS Backup Readiness — DevOps Agent Port

## Overview

This skill assesses an EKS cluster's **backup and recovery posture** — how well its Kubernetes state and persistent data are protected — across the two mainstream approaches: **AWS Backup for EKS** (announced November 10, 2025, as of 2026-07-19; source: [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/11/aws-backup-supports-amazon-eks/)) and the open-source **Velero**. It connects via AWS control-plane APIs and the Kubernetes API, detects what protection is actually configured, and produces two artifacts: a **backup-posture report** with a `READY` / `PARTIAL` / `UNPROTECTED` verdict, and a **guided backup runbook** the human executes to close any gaps.

It answers the question: *"If I lost this cluster's state or a volume, could I get it back — and if not, how do I fix that?"* It is **read-only**: it never starts a backup, creates a plan, installs Velero, or performs a restore. The runbook is instructions for a human (or a change-management pipeline) to execute.

> **A backup/restore is not a control-plane rollback.** Both AWS Backup for EKS and Velero restore **Kubernetes API objects plus persistent-volume data** into a running (pre-provisioned or new) cluster — they do **not** restore etcd, and they do **not** roll back the cluster's Kubernetes version. EKS etcd is AWS-managed and envelope-encrypted; customers never restore it directly. An AWS Backup for EKS restore is explicitly non-destructive and **will not overwrite the target cluster's Kubernetes version** (as of 2026-07-19; source: [Restoring EKS](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-eks.html)). This skill assesses data/object recoverability, **never** version or control-plane rollback — see `references/backup-approaches.md`.

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. It proceeds through discovery and detection without pausing
> for user input. When the target cluster is ambiguous (multiple clusters, none named),
> it assesses **all** discovered clusters. When a non-recoverable error occurs (API
> permission failure, no clusters found), it logs the error in the report and terminates
> per the Step 0 decision table.

## Prerequisites

### Required IAM Permissions (Agent Space Role)

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](references/iam-policy.json) — attach it directly to your Agent Space execution role. It grants **read-only AWS control-plane access** (EKS/Backup `Describe`/`List`/`Get`). It intentionally does **not** grant `eks:AccessKubernetesApi` — Kubernetes-API authentication is handled by the access entry below, not by IAM.

| Service | Actions (read-only) | Purpose |
|---------|--------------------|---------|
| **EKS** | `ListClusters`, `DescribeCluster`, `ListAccessEntries`, `DescribeAccessEntry`, `ListAssociatedAccessPolicies`, `ListAddons`, `DescribeAddon` | Cluster config, `authenticationMode`, the AWS Backup access entry + policy, CSI add-on presence |
| **AWS Backup** | `ListBackupPlans`, `GetBackupPlan`, `ListBackupSelections`, `GetBackupSelection`, `ListProtectedResources`, `ListProtectedResourcesByBackupVault`, `ListRecoveryPointsByResource`, `ListBackupVaults`, `ListBackupJobs`, `DescribeBackupJob` | Whether the cluster is assigned to a plan, has recovery points, has a vault, and recent job outcomes |

### Kubernetes API Access (via Agent Space Access Entry)

**Velero** posture is read entirely through the Kubernetes API — its controller Deployment lives in-cluster and its configuration is held in CRDs. This is read through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy at **cluster scope**, provisioned by `devops-agent/setup.sh` (or manually — see the project README "EKS Access Setup").

- The cluster's `authenticationMode` **must include `API`** (i.e. `API` or `API_AND_CONFIG_MAP`). A `CONFIG_MAP`-only cluster cannot be reached via the access entry. (This is also a prerequisite for AWS Backup for EKS itself — it needs `API` mode to create its own access entry.)
- The access entry (not an IAM action) provides the K8s-API **authentication**; the `AmazonAIOpsAssistantPolicy` provides the **authorization** (RBAC).
- **What `AmazonAIOpsAssistantPolicy` actually authorizes (read-only get/list):** built-in API groups only — core (`pods`, `services`, `nodes`, `namespaces`, `configmaps`, `persistentvolumes`, `persistentvolumeclaims`), `apps` (deployments/daemonsets/statefulsets), `batch`, `events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. **It grants NO CustomResourceDefinition groups** (and not `apiextensions.k8s.io`).
- **Consequence for Velero detection — this is the central limitation of this skill.** Velero's configuration lives in CRDs on the `velero.io` API group (`Backup`, `Restore`, `Schedule`, `BackupStorageLocation`, `VolumeSnapshotLocation`; group/version `velero.io/v1`, as of 2026-07-19 — source: [Velero API types](https://velero.io/docs/main/api-types/)). Under a plain `AmazonAIOpsAssistantPolicy`-only association, **reads of `velero.io` CRDs and of `apiextensions.k8s.io` return `403 Forbidden`**. The skill can still see Velero's *controller Deployment* (the `apps` group IS authorized), which is a strong presence signal — but it **cannot** read the Schedules or BackupStorageLocation that prove backups are actually configured and current. In that case those Velero sub-facts are reported as **`unconfirmed`** with the reason, **never** as "no Velero" / `false`. To confirm full Velero posture, bind the Agent Space role to a **supplementary read-only ClusterRole** granting `get`/`list` on `backups.velero.io`, `schedules.velero.io`, `backupstoragelocations.velero.io`, `restores.velero.io`, `volumesnapshotlocations.velero.io`, and `customresourcedefinitions.apiextensions.k8s.io` (or associate a broader access policy). See `references/velero-assessment.md` ("Lifting the limitation") for the exact ClusterRole.

> **Availability hedge.** AWS Backup for EKS posture is read entirely via the **AWS control-plane API** and is **unaffected** by the K8s access entry — it works even when the access entry is absent. When the access entry is absent (or `authenticationMode` excludes `API`), only the **Velero** half degrades: the skill reports the full AWS Backup posture and marks every Velero sub-fact as `unavailable`/`unconfirmed` in Coverage, **never** as `false`/`count: 0`. A cluster is never labeled `UNPROTECTED` on the strength of unread Velero facts alone (see the posture rubric).

## When to Use

**Activate when the goal involves:**
- Assessing whether an EKS cluster is backed up and recoverable — "is my cluster backed up?", "disaster recovery for EKS", "can I restore my cluster?"
- Evaluating AWS Backup for EKS and/or Velero coverage and finding the gaps
- Getting a guided runbook to set up or improve backup coverage

**Out of scope — route elsewhere:**
- **Raw backup-tool detection as one fact among many** ("do I have Velero installed?") → `eks-recon` (its storage module reports Velero/AWS Backup/Kasten as boolean facts, no posture verdict or runbook).
- **Storage / volume / PV inventory** → `eks-recon` storage module.
- Actually running a backup, creating a plan, installing Velero, or restoring (this skill is strictly read-only).
- **Control-plane / etcd / Kubernetes-version rollback** — not a capability of any backup tool; see the limitation callout above.

---

## Backup Assessment Workflow

**Error output format** (used by the Step 0 hard-stops):

```
## Backup Check Error — <one-line reason>
**Condition:** <which check failed>
**What was found:** <observed state>
**Recommendation:** <remediation guidance for next run>
```

### Step 0: Pre-flight — Cluster Discovery and Validation

**Action 1 — Discover clusters.** Use the EKS ListClusters API to discover available clusters in the target region.

| Condition | Action |
|-----------|--------|
| API call fails (auth/permission error) | **Abort with error** — log "Cannot access EKS. The agent role requires `eks:ListClusters` for the configured region." and terminate. |
| Zero clusters returned | **Abort with error** — log "No EKS clusters found in this region." and terminate. |
| Exactly one cluster found, none named in request | **Proceed** — state which cluster was auto-selected. |
| Multiple clusters found, one named in request | **Proceed** — use the named cluster. |
| Multiple clusters found, none named in request | **Proceed** — assess **all** discovered clusters. Note in the report that no specific cluster was targeted. |

**Action 2 — Describe the selected cluster.** Use DescribeCluster. Extract name, region, status, ARN, `authenticationMode`. The cluster ARN is the resource key for the AWS Backup detection in Step 1.

| Cluster Status | Action |
|----------------|--------|
| `ACTIVE` | **Proceed** |
| `CREATING` / `UPDATING` / `DELETING` | **Skip cluster** — log the state. If it is the only cluster, terminate with error report. |
| `FAILED` | **Skip cluster** — log FAILED state. If it is the only cluster, terminate with error report. |

**Action 3 — Probe Kubernetes API reachability.** Attempt one lightweight K8s-API read (list nodes). If it fails, **do not abort** — set `k8s_api_available: false`, run the AWS Backup half fully, and record the Velero half as `unavailable`/`unconfirmed` in Coverage.

### Step 1: Assess AWS Backup for EKS Coverage

Load `references/aws-backup-assessment.md`. Using read-only AWS Backup + EKS APIs (no cluster access needed), determine whether the cluster is assigned to a backup plan, whether recovery points exist and how recent, whether a vault holds them, and whether the AWS Backup access entry is present. This half always runs.

### Step 2: Assess Velero Coverage

Load `references/velero-assessment.md`. Via the Kubernetes API, detect the Velero controller Deployment (authorized), then attempt to read Schedules / BackupStorageLocation / recent Backups (CRD reads — may be `403` under the managed policy alone). Report confirmed facts; mark blocked CRD reads `unconfirmed`, never `false`.

### Step 2.5: Detect Cluster Data Shape

Via the Kubernetes API, detect the cluster's **data shape** — StatefulSets (`apps`), bound PVCs and their StorageClasses / volume types (EBS/EFS/S3/FSx/other-CSI), and PVs (core + `storage.k8s.io`). These are **all authorized built-in-group reads** under `AmazonAIOpsAssistantPolicy` (no CRD, no new AWS IAM). Classify as `stateful` (StatefulSets and/or persistent PVs — data node/cluster loss would destroy) or `stateless` (no StatefulSets and no bound PVCs, confirmed). If `k8s_api_available: false` from Step 0, set `data_shape: unconfirmed` and never infer `stateless`. See `references/backup-approaches.md` → Cluster Data-Shape Detection.

### Step 3: Determine Posture + Urgency + Emit the Runbook

Load `references/backup-approaches.md` (the posture rubric, the data-shape **urgency dimension**, and the restore-vs-rollback limitation) and `references/runbook.md`. Combine both tooling halves into a `READY` / `PARTIAL` / `UNPROTECTED` posture per the rubric, honoring the unconfirmed-never-false rule. Then add the **urgency** dimension from the detected data shape (verdict × data shape — e.g. UNPROTECTED + stateful EBS/EFS = HIGH; UNPROTECTED + stateless = LOW; unconfirmed shape never downgrades urgency). Emit a runbook tailored to both the tooling gap and the data shape (prioritize volume-level backup for stateful clusters; lighter object-level backup for stateless).

---

## How to Use the References

| Intent / when to use | Reference file |
|----------------------|----------------|
| The two approaches, what each backs up / does NOT, the posture rubric, the data-shape detection + urgency dimension, restore ≠ rollback | [backup-approaches.md](references/backup-approaches.md) |
| Detect AWS Backup for EKS coverage via read-only AWS APIs | [aws-backup-assessment.md](references/aws-backup-assessment.md) |
| Detect Velero posture via the Kubernetes API (+ the CRD-403 handling) | [velero-assessment.md](references/velero-assessment.md) |
| Build the guided, human-executed backup runbook (both tools, gap-driven) | [runbook.md](references/runbook.md) |

Load `backup-approaches.md` first for the rubric and definitions, then the two assessment modules, then `runbook.md`. Each reference describes detection **declaratively** as capability blocks (AWS API calls, and "**Via Kubernetes API**" blocks for K8s resources). There is no Agent tool and no subagents in this environment — analysis isolation is achieved by loading one reference at a time, not by spawning subagents.

---

## Report Output

Produce **two** artifacts. The agent generates both directly — no external conversion tools or scripts.

The report structure below is a **contract**: emit these sections in this order, and include a section even if empty (write "none detected" / "unconfirmed" rather than omitting it) so a reader can trust that a missing item means "assessed and absent," not "skipped."

### 1. Backup-posture report (primary)

- **Filename:** `EKS-Backup-Posture-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

```markdown
# EKS Backup Posture — <cluster> (<region>)
_generated <timestamp> · source: AWS API + K8s API_

## Posture: PARTIAL
<one-line rationale tied to the rubric>

## Data shape & urgency
<data_shape: stateful | stateless | unconfirmed; if stateful, the volume-type mix (e.g. 3 StatefulSets on gp3 EBS); urgency: HIGH | MEDIUM | LOW | unconfirmed per the verdict × data-shape table. Never downgrade urgency on an unconfirmed shape.>

## AWS Backup for EKS
| Fact | Value |
|------|-------|
| cluster assigned to a backup plan | yes (plan: daily-eks) |
| recovery points | 14 (most recent 2026-07-18) |
| backup vault | eks-vault |
| AWS Backup access entry present | yes |
| last backup job status | COMPLETED |

## Velero
| Fact | Value |
|------|-------|
| controller deployment | present (ns: velero) |
| schedules | unconfirmed (CRD read 403 — supplementary ClusterRole needed) |
| backup storage location | unconfirmed (CRD read 403) |

## Notable facts
<flat neutral bullets>

## Coverage
<facts that could not be confirmed + reason — never a false negative>
- velero.schedules: unconfirmed (velero.io CRD read 403 under AmazonAIOpsAssistantPolicy)
```

### 2. Guided backup runbook

- **Filename:** `EKS-Backup-Runbook-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

A step-by-step runbook a human executes, assembled per `references/runbook.md` and tailored to the detected gaps (e.g. "AWS Backup plan exists but no EKS resource assignment" → the assignment steps; "no protection at all" → both the AWS Backup and Velero setup paths with a decision aid). Every command is presented as an instruction for the operator, prefixed with a note that **this skill does not run it**.

---

## Read-Only Guardrails

1. **Assess and instruct — never act.** This skill reads facts and emits a runbook. It never starts backups, creates plans/vaults, installs Velero, or restores. Runbook commands are for a human to run.
2. **Restore is not control-plane rollback.** Never describe any backup tool as restoring etcd or rolling back a Kubernetes version. State the limitation wherever recovery is discussed.
3. **Cite the source and date for every capability/support claim.** The AWS Backup for EKS announcement, what each tool backs up, and restore semantics carry a source URL and "as of <date>" — see `references/backup-approaches.md`. Do not assert support from memory.
4. **Distinguish absence from unconfirmed.** A Velero CRD read that returns `403` is `unconfirmed` (with the reason + the ClusterRole fix), never `false`/"no Velero". A cluster is never labeled `UNPROTECTED` on unread facts alone.
5. **Do NOT hardcode or guess cluster names.** Discover via ListClusters first (Step 0).
6. **Do NOT retry a failed API call more than once.** If it fails twice, record the gap in Coverage and continue.

---

*This skill is provided as sample code for educational and demonstration purposes only. Findings are point-in-time facts and should be validated before acting on them. Backup and restore procedures must be reviewed and tested in a non-production environment first. See the project's README and LICENSE for full terms.*
