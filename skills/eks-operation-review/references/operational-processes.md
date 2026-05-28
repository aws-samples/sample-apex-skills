# Operational Processes

## Purpose
Assess operational process maturity: runbooks, on-call, incident response, and disaster recovery.

## Automation Note
This section is mostly NOT automatable from cluster state. The skill checks for tool presence (Velero, AWS Backup, AWS Support tier) and current cluster health indicators. Process maturity (runbooks, on-call rotation, PIR process) cannot be detected — these items are marked UNKNOWN with suggestions for what to investigate on your own.

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
- AWS Support plan tier (Business/Enterprise = Support API accessible)

**How to check:**
1. This check is limited — AWS Support API access indicates Business or Enterprise plan

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
2. Get events with reason=DeploymentRollback

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
2. List Backup resources (`backups.velero.io`) and Schedule resources (`schedules.velero.io`)
3. List VolumeSnapshots across all namespaces
4. List StatefulSets across all namespaces
5. List PVCs across all namespaces → count

**Rating:**
- 🟢 GREEN: Backup tool in place, scheduled backups running, restore tested
- 🟡 AMBER: Backups exist but never tested, or only PV data backed up
- 🔴 RED: Stateful workloads with no backup strategy
- N/A: No stateful workloads and all config is in Git/IaC
- ⬜ UNKNOWN: Cannot determine if restore has been tested — suggest user investigate
