---
title: "Operational Processes"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-operation-review/references/operational-processes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-operation-review/references/operational-processes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-operation-review/references/operational-processes.md). Edit the source, not this page.
:::

# Operational Processes

## Purpose
Assess operational process maturity: runbooks, on-call, incident response, and disaster recovery.

## Automation Note
This section is mostly NOT automatable from cluster state. The skill checks for tool presence (Velero, AWS Backup) and current cluster health indicators. Process maturity (runbooks, on-call rotation, PIR process) cannot be detected — these items are marked UNKNOWN with suggestions for what to investigate on your own.

## Checks to Execute

### 9.1 — Runbooks for Common Failure Scenarios

**What to check (cluster health indicators that suggest which runbooks should exist):**
- Nodes not in Ready state
- Pods not Running (excluding Completed jobs)
- Recent Warning events
- CrashLoopBackOff pods, Pending pods, OOMKilled events, FailedScheduling events

**How to check:**
1. List nodes → check for any not Ready
2. List pods with field selector `status.phase=Pending`
3. Get events with type=Warning (recent)
4. Get events with reason=BackOff, OOMKilling, FailedScheduling

**Rating:**
- ⬜ UNKNOWN: Cannot determine if runbooks exist from cluster state.

**Investigate manually:**
- Do you have runbooks for node NotReady, CrashLoopBackOff, IP exhaustion, DNS failures?
- Are alerts linked directly to runbooks?
- When was the last time a runbook was updated?

**If active issues found:** Note them as evidence that runbooks for those scenarios should exist and be tested.

---

### 9.2 — On-Call Rotation & Escalation

**What to check:**
- AWS Support plan tier — not probed (Support API not granted); captured as a manual-investigation question only

**How to check:**
1. Do not probe the Support API (not granted). Support plan tier is a manual-investigation question — list it under Investigate Manually.

**Rating:**
- ⬜ UNKNOWN: Primarily a process question.

**Investigate manually:**
- Do you have a formal on-call rotation?
- What's the escalation path when on-call can't resolve within 30 minutes?
- What AWS Support plan are you on?
- How many people can handle a critical EKS incident independently?

---

### 9.3 — Post-Incident Review Process

**What to check:**
- Recent significant events (NodeNotReady, BackOff, rollbacks) that would warrant a PIR

**How to check:**
1. Get events with reason=NodeNotReady
2. Get recent Deployment-related events (e.g. rollout/scaling activity). Note: Kubernetes emits a dedicated `DeploymentRollback` event reason only via the server-side `rollbackTo` path, which was REMOVED in Kubernetes 1.16 and now survives only via the `deprecated.deployment.rollback.to` annotation round-trip; modern `kubectl rollout undo` is a client-side patch that does not fire it, so rollback history cannot be reliably reconstructed from events alone — treat any signal here as best-effort and flag it in the report under "Investigate manually" for confirmation.

**Rating:**
- ⬜ UNKNOWN: Cannot determine PIR process from cluster state.

**Investigate manually:**
- Do you conduct blameless post-mortems after incidents?
- Are action items tracked to completion?
- Can you point to a change made as a result of a post-incident review?

---

### 9.4 — Disaster Recovery & Backup Strategy

**What to check:**
- Velero pods and backup schedules
- AWS Backup plans
- VolumeSnapshot resources
- StatefulSets and PVCs (data at risk if no backup)

**How to check:**
1. List pods in `velero` namespace
2. List Velero Backup resources (`backups.velero.io`) and Schedule resources (`schedules.velero.io`); also list **AWS Backup** plans (e.g. `backup:ListBackupPlans`) to catch EBS/EFS-level backups configured outside the cluster. If the CRD list returns 404/NotFound → Velero not installed (assess AWS Backup instead); if 403/Forbidden → mark the Velero signal UNKNOWN rather than assuming absence. Likewise, if the AWS Backup read (`backup:ListBackupPlans`) returns 403/Forbidden or is otherwise not permitted (note this permission is optional in the prerequisites, so it is commonly ungranted) → mark the AWS-Backup signal *not confirmed* rather than assuming no plans exist, attach the caveat "AWS Backup plans not checked — grant `backup:ListBackupPlans` for full coverage" to the finding, and note it under Investigate Manually; an unavailable AWS Backup read does not by itself force the whole check to UNKNOWN (the in-cluster signals can still decide the band — see Rating). A successful empty list means no AWS Backup plans exist.
3. List VolumeSnapshots across all namespaces. If 404/NotFound (CRD not installed) → no VolumeSnapshot resources; if 403/Forbidden → mark the snapshot signal UNKNOWN rather than assuming absence.
4. List StatefulSets across all namespaces
5. List PVCs across all namespaces → count. If 403/Forbidden when listing StatefulSets or PVCs → mark the stateful-workload-presence signal UNKNOWN (do not conclude zero stateful workloads); StatefulSet (apps/v1) and PVC (core v1) are core APIs so 404 is not expected; an empty successful list means none exist. Do NOT rate N/A ('no stateful workloads') on a forbidden list — rate UNKNOWN and note the forbidden read under Investigate Manually.

**Rating:**
- 🟢 GREEN: Backup tool in place, scheduled backups running with broad coverage (all stateful namespaces / StatefulSets / PVCs covered)
- 🟡 AMBER: Two cases. **(i) Partial coverage** — backup tooling present AND actual backups exist but coverage is partial: some Velero Backups/Schedules, AWS Backup plans, or VolumeSnapshots exist but cover only PV data, or only some namespaces / StatefulSets / PVCs. At least one backup/schedule/snapshot/plan must actually exist. **(ii) In-cluster empty but AWS Backup unverified** — stateful workloads present, the in-cluster backup signals (Velero Backups/Schedules and VolumeSnapshots) were *successfully* read and are conclusively empty, but the AWS Backup read was **unavailable** (`backup:ListBackupPlans` not granted or 403/Forbidden). This is AMBER-with-note, NOT RED, because AWS Backup — which protects EBS/EFS at the volume level and creates no Velero objects and no VolumeSnapshot CRs (invisible in-cluster) — may be providing full coverage that the unread optional permission is hiding. Attach the note: "no in-cluster backup (Velero/VolumeSnapshots) found; AWS Backup coverage could not be verified — grant `backup:ListBackupPlans` to confirm. If AWS Backup is not in use either, this is effectively unprotected." Zero coverage with *all* channels confirmed absent is RED, not AMBER (see RED).
- 🔴 RED: Stateful workloads present AND **all backup channels confirmed absent** — i.e. the in-cluster backup signals were *successfully* read and are conclusively empty (zero Velero Backups, zero Velero Schedules, no VolumeSnapshots) AND the AWS Backup read **succeeded returning zero plans** (`backup:ListBackupPlans` returned an empty list). Two sub-cases, both RED and both still requiring the successful zero-plan AWS read: (a) **tooling absent** — Velero conclusively absent (404/NotFound) AND no VolumeSnapshots AND AWS Backup confirmed-empty; (b) **tooling present but idle** — Velero installed (velero-namespace pods Running and/or `backups.velero.io` / `schedules.velero.io` resolve) but the Velero Backup list and the Velero Schedule list return zero AND no VolumeSnapshots exist AND AWS Backup confirmed-empty. Installed-but-idle backup tooling is not coverage. Critically, RED now requires the **AWS Backup read to have SUCCEEDED with zero plans** in addition to the conclusively-empty in-cluster reads: a cluster backed up entirely by AWS Backup at the EBS/EFS level creates no Velero objects and no VolumeSnapshot CRs, so an *unavailable* AWS Backup read (not granted, or 403/Forbidden) leaves open the possibility of full AWS-Backup coverage — that state is **AMBER-with-note, not RED** (see AMBER (ii)). An unread signal that could only *refute* the RED must not drive an unearned RED (the mirror of "no unearned GREEN").
- N/A: No stateful workloads on EKS. **Orphaned-PV precedence:** if an orphaned in-tree PV is present but the StatefulSet AND PVC enumerations both succeeded and returned zero (zero StatefulSets, zero PVCs), N/A still wins over RED — RED requires stateful *workloads* present, and an unbound/released PV with no consuming PVC or StatefulSet is not a stateful workload, so the RED predicate is unmet. Rate N/A and note the orphaned PV (and its reclaim policy) under Investigate Manually; do not earn a RED off a workload-less PV.
- ⬜ UNKNOWN: The home for indeterminate backup coverage: when stateful workloads are present but an **in-cluster** backup signal read was forbidden (Velero CRD 403 or VolumeSnapshot 403) and no backup was affirmatively found, rate UNKNOWN — a forbidden in-cluster read cannot confirm "no backup strategy," so the RED arm is unreachable in that state. Note: an *unavailable AWS Backup read alone* (`backup:ListBackupPlans` not granted or 403/Forbidden), with the in-cluster signals successfully read and conclusively empty, is NOT UNKNOWN and NOT RED — it is **AMBER-with-note** (see AMBER (ii)): the in-cluster reads succeeded (so the state is not indeterminate), but they cannot rule out AWS-Backup-level coverage, so RED is not earned either. **Also** when the StatefulSet/PVC list (stateful-workload presence, step 5) returned 403/Forbidden, rate UNKNOWN rather than N/A — a forbidden list cannot confirm "no stateful workloads," so the N/A arm is unreachable in that state. Whether a restore has ever been *tested* is NOT an UNKNOWN-band trigger — it is an always-true unobservable (never determinable from cluster state, so it would compete with the whole partition and could rate a fully-backed-up GREEN cluster as UNKNOWN); it is recorded under Investigate Manually below, not here.
- **Evaluation order:** If N/A applies (no stateful workloads — successful empty StatefulSet AND PVC enumeration), N/A takes precedence over the colored bands. Otherwise assess RED first; if not RED, assess AMBER; otherwise GREEN. The colored bands pivot on whether any backup **actually exists** (a Velero Backup, a Velero Schedule, an AWS Backup plan, or a VolumeSnapshot) and on whether *every* backup channel has been confirmed: zero across all channels **with AWS Backup confirmed-empty by a successful read** → RED; at least one backup exists but coverage is partial → AMBER (i); in-cluster empty but AWS Backup **unverified** (read unavailable) → AMBER-with-note (ii); broad coverage → GREEN. **Guard on RED:** the RED "no effective backup" conclusion requires two things together — (1) the **in-cluster** backup-signal reads succeeded and are conclusively empty (Velero Backup/Schedule lists returned 404 or an empty result, VolumeSnapshot list returned 404 or an empty result) while stateful workloads exist, AND (2) the **AWS Backup read succeeded and returned zero plans**. If an *in-cluster* read (Velero CRD or VolumeSnapshot) was forbidden (403) and no backup was affirmatively found, route to UNKNOWN instead of RED — you cannot confirm the absence of a backup strategy from a forbidden in-cluster read. If the *AWS Backup read is unavailable* (not granted or 403) while the in-cluster signals are conclusively empty, route to **AMBER-with-note instead of RED** — an AWS-Backup-only cluster (EBS/EFS-level backups, invisible in-cluster) would present exactly these in-cluster signals, so the unread optional permission could be hiding full coverage; an unread signal that can only *refute* the RED must not force an unearned RED. A successful AWS Backup read returning zero plans is what *earns* the RED; a successful AWS Backup read returning ≥1 plan means a backup exists (AMBER (i)/GREEN, not RED).
- **Scoring authority:** this check owns backup/DR coverage scoring (Velero / AWS Backup / VolumeSnapshots / no-backup-strategy); check 5.5 defers here for the backup-strategy signal and scores only storage-class / in-tree-plugin / PV-StatefulSet configuration facts (reclaim policy is a non-scoring note in 5.5).

**Investigate manually:**
- Has a restore actually been tested (not just backups running)? Restore-testing is never observable from cluster state — flag it in the report under "Investigate manually" for confirmation; it does not move the band.
- What is the documented RTO/RPO, and does the current backup cadence meet it?
- Are backups stored in a separate account/region to survive a regional or account-level failure?
