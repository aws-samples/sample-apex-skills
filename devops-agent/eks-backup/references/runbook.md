# Module: Guided Backup Runbook

> **Part of:** [eks-backup](../SKILL.md)
> **Purpose:** A template the agent fills to emit a **human-executed** backup runbook, driven
> by the gap between the current posture (READY / PARTIAL / UNPROTECTED) and a protected
> cluster. This skill assembles and instructs — it **never** runs a backup, restore, install,
> or any command below.

**This skill does not run any command in this runbook.** Every command below is an **operator
instruction**. The agent selects the section that matches the posture verdict from Step 3,
fills in the cluster/account/region specifics, and emits the assembled runbook as the second
output artifact. All commands are presented in fenced blocks prefixed
`Operator runs (this skill does not):`.

AWS recommends **testing any restore in a non-production cluster before relying on it**. A
backup/restore is **not** a control-plane rollback — see the caveat below. Sources:
<https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html> and
<https://velero.io/docs/main/> (both as of 2026-07-19).

## Table of Contents

- [How the agent uses this template](#how-the-agent-uses-this-template)
- [Data-shape branching (urgency + what to prioritize)](#data-shape-branching-urgency--what-to-prioritize)
- [The restore ≠ control-plane-rollback caveat](#the-restore--control-plane-rollback-caveat)
- [READY — verify and validate](#ready--verify-and-validate)
- [PARTIAL — close the gap](#partial--close-the-gap)
- [UNPROTECTED — full setup (choose a path)](#unprotected--full-setup-choose-a-path)
  - [Decision aid: AWS Backup vs Velero](#decision-aid-aws-backup-vs-velero)
  - [Path A — AWS Backup for EKS](#path-a--aws-backup-for-eks)
  - [Path B — Velero](#path-b--velero)
- [Runbook output template](#runbook-output-template)

---

## How the agent uses this template

The runbook is **gap-driven from the posture verdict** produced in Step 3:

1. **READY** → emit the [verify/validate](#ready--verify-and-validate) runbook only: confirm
   recent recovery points and recommend a periodic restore test.
2. **PARTIAL** → emit only the [close-the-gap](#partial--close-the-gap) steps for whatever is
   missing (e.g. a plan exists but no EKS resource assignment → the assignment steps; a Velero
   controller is present but no `Schedule` → create a `Schedule`).
3. **UNPROTECTED** → emit the [full setup](#unprotected--full-setup-choose-a-path), presenting
   **both** paths (AWS Backup and Velero) with the [decision aid](#decision-aid-aws-backup-vs-velero).
4. **unknown** (both halves unconfirmed — AWS Backup API calls failed AND the K8s API was
   unreachable) → emit **no** runbook; report `posture: unknown` with the Coverage note and the
   Step 0 error output, and recommend re-running once access is restored.

The agent fills every `<placeholder>` with the detected cluster name, region, account, ARN,
etc. It does **not** execute any step — it produces the runbook as a document for an operator
(or a change-management pipeline) to run.

The verdict picks the section; the **detected data shape** (see `backup-approaches.md` →
[Cluster Data-Shape Detection](backup-approaches.md#cluster-data-shape-detection) and the
[urgency dimension](backup-approaches.md#data-shape-urgency-dimension)) then picks the
**emphasis and ordering within it** — see the next section.

---

## Data-shape branching (urgency + what to prioritize)

The verdict says *whether* tooling is configured; the data shape says *how urgent* the gap is
and *what to protect first*. Apply this branching **on top of** the verdict section, keying off
the `data_shape` / `urgency` facts from Step 3. This is deterministic — do not editorialize
beyond the detected facts.

- **Detected StatefulSets and/or EBS/EFS/other-CSI bound PVs, and no volume-level backup**
  (UNPROTECTED, or PARTIAL where volumes are out of scope) → **HIGH urgency. Prioritize
  volume-level backup.** Lead the runbook with whichever path covers the PV data:
  - **AWS Backup path:** the EKS resource assignment (Path A, step 5) covers the cluster's PVs
    via the EKS CSI driver (EBS/EFS/S3) — this is the fastest agentless route to volume
    coverage. State the detected volume-type mix (e.g. "3 StatefulSets on gp3 EBS").
  - **Velero path:** ensure CSI snapshots (VolumeSnapshotLocation) **or** Kopia
    file-system backup is configured — a Velero install that backs up only K8s objects does
    **not** protect the volume data. Call this out explicitly.
- **Detected EFS-backed PVs** → note EFS specifics: AWS Backup for EKS backs EFS via the CSI
  driver **but not cross-account EFS and not non-root subpath mounts** (see `backup-approaches.md`
  Limitations); for those, Velero file-system backup is the fallback. EFS data often persists
  independently of the cluster, but a backup still guards against accidental deletion.
- **Detected FSx-backed PVs** → AWS Backup for EKS does **not** support FSx-via-CSI. Direct the
  operator to Velero file-system backup for FSx volumes (or native FSx backups outside this
  skill's scope), even under an otherwise-AWS-Backup posture.
- **Stateless (StatefulSet and PVC reads both succeeded and returned zero)** → **`LOW` urgency.
  Lighter recommendation:** object-level backup for fast namespace re-creation (either AWS
  Backup EKS or Velero object backup); no volume snapshots needed. State plainly that the K8s
  objects are reconstructible from GitOps/IaC, so this is a convenience/RTO improvement, not a
  data-loss emergency. Still recommend it; just do not frame it as urgent.
- **Data shape `unconfirmed`** (K8s API unavailable — `k8s_api_available: false`) → emit the
  **full tooling-verdict runbook unchanged**, and add a note: "Data shape could not be assessed
  (K8s API unreachable); urgency is treated as at-least the verdict warrants and volume-level
  backup is assumed potentially in scope. Re-run with K8s-API access to tailor." **Never**
  emit the lighter stateless recommendation on an unconfirmed shape.

---

## The restore ≠ control-plane-rollback caveat

Restate this wherever a restore is discussed. A backup/restore is **not** a control-plane
rollback:

- Both AWS Backup for EKS and Velero restore **Kubernetes API objects plus persistent-volume
  data** into a **running** cluster — one that is pre-provisioned or freshly created. They do
  **not** restore etcd, and they do **not** roll back the cluster's Kubernetes version.
- **Validate every restore against a pre-provisioned or new NON-PROD cluster.** There is no
  etcd or Kubernetes-version rollback to fall back on.

(Sources: [Restoring EKS](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-eks.html),
[EKS envelope encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html),
both as of 2026-07-19. See `backup-approaches.md`.)

---

## READY — verify and validate

The cluster already has at least one approach confirmed configured and producing recent
recovery points / backups. The runbook here **confirms** that state and recommends a periodic
restore test — it does not set anything up.

1. **Confirm recent recovery points (AWS Backup path).** Verify the newest recovery point is
   within the plan's cadence.

   Operator runs (this skill does not):
   ```bash
   aws backup list-recovery-points-by-resource --resource-arn <cluster-arn> \
     --query 'RecoveryPoints[].{arn:RecoveryPointArn,created:CreationDate,status:Status}'
   ```

2. **Confirm a recent completed Backup (Velero path).** Confirm the newest `Backup` is
   `Completed` and within the schedule's cadence (operator has cluster access):

   Operator runs (this skill does not):
   ```bash
   velero backup get
   ```

3. **Recommend a periodic restore test.** A backup is only proven by a successful restore.
   Schedule a **recurring restore drill** (e.g. quarterly) that restores the newest recovery
   point / Backup into a **NON-PROD** target cluster and validates workloads come up — see the
   validate steps in each setup path below. This is the single most valuable durability check
   for a READY cluster.

---

## PARTIAL — close the gap

A tool is present but coverage is incomplete or stale. Emit **only** the block matching the
detected gap.

- **AWS Backup plan exists but no EKS resource assignment for this cluster** → emit
  [Path A, step 5 (resource assignment)](#path-a--aws-backup-for-eks) only. Everything upstream
  (auth mode, role, vault, plan) is already in place.
- **Recovery points / backups are stale (older than the plan's or schedule's cadence)** →
  investigate the last job outcome and the schedule cadence; re-run the assignment or fix the
  schedule. For AWS Backup, inspect the last job:

  Operator runs (this skill does not):
  ```bash
  aws backup list-backup-jobs --by-resource-arn <cluster-arn> \
    --query 'BackupJobs[].{id:BackupJobId,state:State,statusMsg:StatusMessage,created:CreationDate}'
  ```

- **Assigned to a plan but no backup job has run yet (brand-new cluster)** → optionally kick a
  one-off job to seed the first recovery point (see Path A, step 5 ad-hoc form), then let the
  plan take over.
- **Velero controller present but no `Schedule`** → emit
  [Path B, step 5 (create a Schedule)](#path-b--velero) only. The controller,
  `BackupStorageLocation`, and S3 access are already present.
- **Velero controller present but `BackupStorageLocation` is `Unavailable`** → emit
  [Path B, step 3 (BackupStorageLocation + S3 access)](#path-b--velero) to fix the bucket /
  credentials.

---

## UNPROTECTED — full setup (choose a path)

No confirmed backup mechanism exists. Present **both** paths with the decision aid, then emit
the chosen path's full setup. (If the operator is undecided, emit AWS Backup first — it needs
no in-cluster agent.)

### Decision aid: AWS Backup vs Velero

| Dimension | AWS Backup for EKS (Path A) | Velero (Path B) |
|-----------|-----------------------------|-----------------|
| Management | **AWS-managed** — no in-cluster agent or controller pod | Self-managed — a controller Deployment + CRDs run in-cluster |
| Where it integrates | AWS Backup vaults, backup policies, and audit/compliance tooling | Kubernetes-native CRDs; S3 for backup storage |
| Portability | AWS-native | **Portable / multicloud** — same tool across clouds |
| Volume backup | EBS/EFS/S3 via the EKS CSI driver | CSI snapshots **plus** Kopia file-system backup |
| Prerequisites | `authenticationMode` includes `API`; IAM backup role; a vault | S3 bucket; IRSA or EKS Pod Identity; in-cluster CRDs |

Rule of thumb: choose **AWS Backup** for an AWS-managed, agentless posture that plugs into
existing AWS Backup vaults/policies/audit; choose **Velero** for a portable/multicloud tool
with Kopia file-system backup (accepting the in-cluster CRDs and S3 you must run).

### Path A — AWS Backup for EKS

Source: <https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html> (as of
2026-07-19).

1. **Ensure the cluster `authenticationMode` includes `API`.** AWS Backup for EKS requires
   `API` or `API_AND_CONFIG_MAP` so it can create its own access entry. If the cluster is
   `CONFIG_MAP`-only, update it first (a one-way move toward `API`):

   Operator runs (this skill does not):
   ```bash
   aws eks update-cluster-config --name <cluster-name> \
     --access-config authenticationMode=API_AND_CONFIG_MAP
   ```

2. **Create the AWS Backup IAM role.** Attach the managed policy
   `AWSBackupServiceRolePolicyForBackup` (add `AWSBackupServiceRolePolicyForS3Backup` when S3
   PVs are in scope):

   Operator runs (this skill does not):
   ```bash
   aws iam create-role --role-name <backup-role-name> \
     --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"backup.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
   aws iam attach-role-policy --role-name <backup-role-name> \
     --policy-arn arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForBackup
   # If S3 persistent volumes are in scope, also:
   aws iam attach-role-policy --role-name <backup-role-name> \
     --policy-arn arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Backup
   ```

3. **Create a backup vault** to hold the recovery points:

   Operator runs (this skill does not):
   ```bash
   aws backup create-backup-vault --backup-vault-name <vault-name>
   ```

4. **Create a backup plan** (cadence + retention + target vault):

   Operator runs (this skill does not):
   ```bash
   aws backup create-backup-plan --backup-plan '{"BackupPlanName":"<plan-name>","Rules":[{"RuleName":"daily","TargetBackupVaultName":"<vault-name>","ScheduleExpression":"cron(0 5 ? * * *)","Lifecycle":{"DeleteAfterDays":35}}]}'
   ```

5. **Create a resource assignment for resource type "Amazon EKS"** (the cluster ARN), so the
   plan actually covers this cluster:

   Operator runs (this skill does not):
   ```bash
   aws backup create-backup-selection --backup-plan-id <plan-id> \
     --backup-selection '{"SelectionName":"eks-cluster","IamRoleArn":"<backup-role-arn>","Resources":["<cluster-arn>"]}'
   ```

   Or, to seed a first recovery point immediately with a one-off job:

   Operator runs (this skill does not):
   ```bash
   aws backup start-backup-job --resource-arn <cluster-arn> --iam-role-arn <backup-role-arn> \
     --backup-vault-name <vault-name>
   ```

   > **Note:** AWS Backup **associates its own EKS access entry** (access policy
   > `AWSBackupFullAccessPolicyForBackup`) with the cluster automatically as part of the
   > backup — you do not create that access entry by hand.

6. **Validate by restoring to a NON-PROD target cluster.** The restore is non-destructive and
   **will not overwrite the target cluster's Kubernetes version** — it restores objects + PV
   data into a running cluster, never etcd or the K8s version. Restore into a
   **pre-provisioned or new** non-prod cluster and confirm workloads come up:

   Operator runs (this skill does not):
   ```bash
   aws backup start-restore-job --recovery-point-arn <recovery-point-arn> \
     --iam-role-arn <restore-role-arn> --metadata <eks-restore-metadata>
   ```

### Path B — Velero

Source: <https://velero.io/docs/main/> (as of 2026-07-19).

1. **Install Velero** — via the Helm chart or the `velero install` CLI:

   Operator runs (this skill does not):
   ```bash
   helm repo add vmware-tanzu https://vmware-tanzu.github.io/helm-charts
   helm install velero vmware-tanzu/velero --namespace velero --create-namespace \
     --set configuration.backupStorageLocation[0].bucket=<bucket> \
     --set configuration.backupStorageLocation[0].provider=aws
   # or, with the CLI:
   # velero install --provider aws --bucket <bucket> --backup-location-config region=<region> ...
   ```

2. **Provision an S3 bucket** for backup storage:

   Operator runs (this skill does not):
   ```bash
   aws s3api create-bucket --bucket <bucket> --region <region> \
     --create-bucket-configuration LocationConstraint=<region>
   ```

3. **Configure the `BackupStorageLocation` and grant S3 access via IRSA or EKS Pod Identity.**
   Grant the Velero service account S3 access (do **not** use static keys) — either an IRSA
   role bound to the SA, or an EKS Pod Identity association:

   Operator runs (this skill does not):
   ```bash
   aws eks create-pod-identity-association --cluster-name <cluster-name> \
     --namespace velero --service-account velero --role-arn <velero-s3-role-arn>
   ```

4. **Verify the `BackupStorageLocation` is `Available`** (operator has cluster access):

   Operator runs (this skill does not):
   ```bash
   kubectl -n velero get backupstoragelocation
   ```

5. **Create a `Schedule`** for recurring backups:

   Operator runs (this skill does not):
   ```bash
   velero schedule create <schedule-name> --schedule "0 5 * * *" --ttl 840h0m0s
   ```

6. **Verify a `Backup` completes**, then validate by restoring to a **NON-PROD** target
   cluster (restores objects + PV data into a running cluster — never etcd or the K8s version):

   Operator runs (this skill does not):
   ```bash
   velero backup create <backup-name> --wait
   velero backup get
   # In the pre-provisioned/new non-prod cluster (Velero installed, same BackupStorageLocation):
   velero restore create --from-backup <backup-name>
   ```

---

## Runbook output template

The agent emits the second artifact
(`EKS-Backup-Runbook-{cluster}-{YYYY-MM-DD}-{HHMM}.md`) using this skeleton, filled per the
posture verdict. Every command block is prefixed `Operator runs (this skill does not):`.

```markdown
# EKS Backup Runbook — <cluster> (<region>)
_generated <timestamp> · posture: <READY|PARTIAL|UNPROTECTED> · urgency: <HIGH|MEDIUM|LOW|unconfirmed> · THIS RUNBOOK IS EXECUTED BY A HUMAN — this skill does not run any step_

## Posture summary
<the verdict from Step 3 and the specific gap(s) this runbook closes>

## Data shape & urgency
<data_shape: stateful | stateless | unconfirmed; if stateful, the volume-type mix (e.g. "3 StatefulSets on gp3 EBS, 2 EFS PVCs"); the urgency from backup-approaches.md's urgency table and why. If unconfirmed, state the K8s API was unreachable and urgency is treated as at-least the verdict warrants.>

## Caveat: restore ≠ control-plane rollback
<restores objects + PV data into a running cluster; no etcd / K8s-version rollback; validate in NON-PROD>

## Steps
<only the section that matches the posture, with data-shape branching applied on top:>
<  READY      → verify recent recovery points (incl. that PV data is covered, if stateful) + recommend a periodic restore test>
<  PARTIAL    → only the close-the-gap block(s) for the missing piece; lead with volume-level coverage if stateful volumes are uncovered>
<  UNPROTECTED → decision aid, then Path A (AWS Backup) and/or Path B (Velero) full setup; if stateful, prioritize volume-level backup; if stateless, lighter object-level backup>

## Validation
<restore into a pre-provisioned/new NON-PROD cluster and confirm workloads come up>
```
