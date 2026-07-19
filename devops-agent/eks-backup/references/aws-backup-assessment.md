# Module: AWS Backup for EKS Assessment

> **Part of:** [eks-backup](../SKILL.md)
> **Purpose:** Detect AWS Backup for EKS coverage — plan assignment, recovery points, vault,
> recent job outcomes, and the AWS Backup access entry — via read-only AWS control-plane APIs

This module runs **always** and needs **no cluster access**. All detection is via the AWS
control-plane API using the read-only actions in `references/iam-policy.json`. See
`backup-approaches.md` for what AWS Backup for EKS does and does not cover (with sources) and
for the posture rubric this module feeds.

## Table of Contents

- [Access Model](#access-model)
- [Detection Capabilities](#detection-capabilities)
  - [1. Is the cluster assigned to a backup plan](#1-is-the-cluster-assigned-to-a-backup-plan)
  - [2. Recovery points for the cluster](#2-recovery-points-for-the-cluster)
  - [3. Backup vaults](#3-backup-vaults)
  - [4. Recent backup job outcomes](#4-recent-backup-job-outcomes)
  - [5. The AWS Backup access entry](#5-the-aws-backup-access-entry)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

This half of the assessment is **entirely AWS control-plane API** and requires **no
Kubernetes-API access at all** — no EKS access entry, no `authenticationMode` requirement.
It works even when the cluster's K8s API is unreachable to the agent. It reads only the
read-only `backup:*` and `eks:*` actions in `references/iam-policy.json` (all `Resource: "*"`).

- **AWS control-plane APIs (AWS Backup + EKS)** — backup plans, selections, protected
  resources, recovery points, vaults, backup jobs, and EKS access entries. RBAC is IAM, not
  Kubernetes RBAC.
- The cluster **ARN** (from `eks:DescribeCluster` in Step 0) is the resource key that ties
  AWS Backup facts to this specific cluster:
  `arn:aws:eks:<region>:<account>:cluster/<name>`.

> **Example-command note.** The `aws ...` commands below illustrate the exact read-only API
> action, its resource, and the fields to extract. The agent issues these as read-only AWS API
> calls; do not chain them into `| jq` mutation pipelines. Each block names the purpose and the
> fields that feed the posture rubric.

---

## Detection Capabilities

### 1. Is the cluster assigned to a backup plan

**Purpose:** determine whether this cluster is covered by a backup plan's resource assignment
(the single most important AWS Backup fact for the posture rubric).

**Via AWS API** — walk plans → selections and look for the cluster ARN or the EKS resource
type:

```bash
# List backup plans, then read each plan
aws backup list-backup-plans --query 'BackupPlansList[].{id:BackupPlanId,name:BackupPlanName}'
aws backup get-backup-plan --backup-plan-id <plan-id>

# For each plan, list its selections and read each one
aws backup list-backup-selections --backup-plan-id <plan-id>
aws backup get-backup-selection --backup-plan-id <plan-id> --selection-id <selection-id>
```

- **Fields to extract:** from each selection, `BackupSelection.Resources` (explicit ARNs) and
  `BackupSelection.Conditions` / resource-type filters. A match exists when a selection lists
  the cluster ARN directly, or selects by resource type `Amazon EKS` (tag-based selection) in
  a way that covers the cluster.
- Cross-check via the protected-resources view (more direct when the cluster has been backed
  up at least once):

```bash
# All resources AWS Backup considers protected, filtered to this cluster / EKS type
aws backup list-protected-resources \
  --query "Results[?ResourceType=='EKS' || ResourceArn=='<cluster-arn>']"

# Same, scoped to a specific vault
aws backup list-protected-resources-by-backup-vault --backup-vault-name <vault> \
  --query "Results[?ResourceArn=='<cluster-arn>']"
```

- **Result fact:** `assigned_to_plan: true` with the plan name(s) when a selection covers the
  cluster; `false` (a confirmed AWS-side fact, not `unconfirmed`) when no plan/selection
  references it. Absence here IS confirmable — the AWS API returns the full plan set.

### 2. Recovery points for the cluster

**Purpose:** confirm that real, restorable backups exist and how recent they are.

**Via AWS API** — list recovery points by the cluster ARN:

```bash
aws backup list-recovery-points-by-resource --resource-arn <cluster-arn> \
  --query 'RecoveryPoints[].{arn:RecoveryPointArn,created:CreationDate,status:Status}'
```

- **Fields to extract:** count of recovery points, and the **most-recent `CreationDate`**
  (drives the "stale vs recent" test in the rubric).
- **Result fact:** `recovery_points.count` and `recovery_points.most_recent`. Zero recovery
  points with a plan assignment present → PARTIAL (assigned but nothing captured yet).

### 3. Backup vaults

**Purpose:** confirm a vault exists to hold the recovery points.

**Via AWS API** — list vaults:

```bash
aws backup list-backup-vaults \
  --query 'BackupVaultList[].{name:BackupVaultName,points:NumberOfRecoveryPoints}'
```

- **Fields to extract:** vault name(s) and recovery-point counts. Correlate with the vault
  referenced by the cluster's recovery points from capability 2.
- **Result fact:** `vault` (name of the vault holding the cluster's recovery points, or the
  candidate default vault).

### 4. Recent backup job outcomes

**Purpose:** confirm the last backup actually succeeded (vs failed or "Completed with issues").

**Via AWS API** — list recent jobs, then describe the relevant one:

```bash
# Recent backup jobs (filter by resource ARN where supported)
aws backup list-backup-jobs --by-resource-arn <cluster-arn> \
  --query 'BackupJobs[].{id:BackupJobId,state:State,statusMsg:StatusMessage,created:CreationDate}'

# Full detail of a specific job
aws backup describe-backup-job --backup-job-id <job-id>
```

- **Fields to extract:** `State` (`COMPLETED` / `FAILED` / `RUNNING` / `ABORTED`) and
  `StatusMessage`. A `COMPLETED` state with a status message noting skipped resources is the
  **"Completed with issues"** case (e.g. `metrics.k8s.io` skipped — see `backup-approaches.md`
  Limitations); report it distinctly, not as a clean success and not as a failure.
- **Result fact:** `last_job_status` with the raw state and, where present, the "completed
  with issues" nuance.

### 5. The AWS Backup access entry

**Purpose:** confirm AWS Backup created its own EKS access entry (evidence the integration is
wired into the cluster), and check `authenticationMode` compatibility.

**Via AWS API** — list access entries and their associated access policies:

```bash
aws eks list-access-entries --cluster-name <cluster-name>
aws eks list-associated-access-policies --cluster-name <cluster-name> \
  --principal-arn <backup-service-role-arn>
```

- **What to look for:** an access entry whose associated access policy is
  `AWSBackupFullAccessPolicyForBackup` (the policy AWS Backup uses for its in-cluster
  permissions — source: [EKS access policy
  permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html),
  as of 2026-07-19).
- **Result fact:** `access_entry_present: true/false`. Its presence corroborates an active
  AWS Backup for EKS configuration; its absence on an otherwise-assigned cluster is worth
  noting in Coverage.

---

## Output Schema

The schema below is the **internal fact structure** the markdown posture report is assembled
from — this skill emits a markdown report + runbook, not a separate YAML artifact.

The agent emits this `aws_backup:` block (alongside the shared cluster identity). Use `null`
where a fact was not detected; never omit a key. All facts here are AWS-API-confirmable, so
`false`/`0` are genuine facts (not `unconfirmed`) unless the AWS API call itself failed — a
failed call is recorded in the report's Coverage section.

```yaml
aws_backup:
  assessable: bool                 # true — AWS API reachable; false only if backup:* / eks:* calls failed
  authentication_mode: string      # API | API_AND_CONFIG_MAP | CONFIG_MAP (from DescribeCluster)
  configurable: bool               # false when authentication_mode is CONFIG_MAP-only (cannot use AWS Backup for EKS)
  assigned_to_plan: bool           # cluster covered by a plan's resource assignment
  plan_names: list                 # names of plans covering the cluster, [] if none
  recovery_points:
    count: int
    most_recent: string            # ISO CreationDate of newest recovery point, null if none
  vault: string                    # vault holding the cluster's recovery points, null if none
  last_job_status: string          # COMPLETED | FAILED | RUNNING | ABORTED | "COMPLETED_WITH_ISSUES", null if no jobs
  last_job_message: string         # StatusMessage when present (e.g. skipped metrics.k8s.io), null otherwise
  access_entry_present: bool       # AWS Backup's own EKS access entry (AWSBackupFullAccessPolicyForBackup)
```

---

## Edge Cases

### `authenticationMode` is not `API` / `API_AND_CONFIG_MAP`

If `DescribeCluster` reports `authenticationMode: CONFIG_MAP` (only), **AWS Backup for EKS
cannot be configured at all** — the integration requires `API` mode so AWS Backup can create
its own access entry (source: [AWS Backup EKS
backups](https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html), as of
2026-07-19). This is a real, confirmable fact, not an assessor limitation: set
`configurable: false` and report it. In this state the AWS Backup half of the posture is a
genuine gap for the cluster (and, separately, the Velero access entry also cannot be used —
see `velero-assessment.md`).

### Brand-new cluster: plan assigned but no run yet

If the cluster is assigned to a plan (capability 1) but `recovery_points.count == 0` and there
is no completed job, this is **PARTIAL**, not UNPROTECTED — coverage is configured but has not
yet produced a restorable point. Report the assignment as present and the recovery points as
`0` (a real fact), and note "assigned, awaiting first backup run".

### AWS API call fails

Do not retry more than once. If a `backup:*` or `eks:*` call fails, set the affected fact to
`unconfirmed` in the report's Coverage section with the reason — never infer `false` from a
failed call. If `ListClusters`/`DescribeCluster` itself failed, Step 0 has already hard-stopped.
