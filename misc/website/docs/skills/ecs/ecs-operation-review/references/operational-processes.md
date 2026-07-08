---
title: "Section 08 — Operational Processes"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/operational-processes.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/operational-processes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/operational-processes.md). Edit the source, not this page.
:::

# Section 08 — Operational Processes

## Purpose
Assess operational maturity: IaC provenance, tagging discipline, disaster-recovery/backup, Fargate task-retirement awareness, and process readiness (runbooks, on-call). Much of this is **not fully detectable from estate state** — those items are marked UNKNOWN with specific questions to investigate.

## Automation Note
The skill detects tool/config presence (IaC tags, backup resources, current health signals). Process maturity (runbooks, on-call rotation, post-incident reviews) cannot be read from the API and is marked UNKNOWN with guidance.

## Checks to Execute

### 8.1 — Infrastructure-as-Code Provenance

**What to check:**
- Cluster/service/task-definition tags indicating IaC management (`aws:cloudformation:stack-name`, `terraform`, `managed-by`, `aws:cdk:*`).
- Whether services are recreatable from code.

**How to check:**
1. `aws ecs describe-clusters --include TAGS` and `aws ecs list-tags-for-resource --resource-arn <service-arn>` → inspect tags.

**Rating:**
- 🟢 GREEN: Clear IaC provenance (CloudFormation/CDK/Terraform tags) across cluster and services.
- 🟡 AMBER: IaC tags on some resources but not all, or unclear if current.
- 🔴 RED: No IaC provenance — estate appears console/CLI-created and not reproducible.
- ⬜ UNKNOWN: Tags alone can't confirm the code is pipeline-applied vs manually run — suggest user verify.

**Investigate manually:** Is IaC applied via CI/CD or manually? Could you recreate a service from code today?

---

### 8.2 — Tagging & Environment Classification

**What to check:**
- Consistent `Environment`/`env`, ownership, and cost-allocation tags on clusters and services.

**How to check:**
1. Inspect tags from 8.1 for environment and ownership keys.

**Rating:**
- 🟢 GREEN: Consistent environment + ownership tags enabling clear scoping and cost allocation.
- 🟡 AMBER: Partial/inconsistent tagging.
- 🔴 RED: No environment/ownership tags — can't distinguish prod from non-prod or attribute cost/ownership.
- ⬜ UNKNOWN: Cannot read tags.

**Note:** Consistent env tags also improve the accuracy of every other section's production-vs-non-production rating.

---

### 8.3 — Disaster Recovery & Backup

**What to check:**
- Backup coverage for stateful data attached to tasks (EFS backups via AWS Backup, EBS snapshots, database backups).
- Multi-Region / multi-AZ posture for critical services.

**How to check:**
1. Identify stateful workloads (EFS/EBS volumes in task definitions).
2. `aws backup list-backup-plans` (best-effort) and check for relevant selections.

**Rating:**
- 🟢 GREEN: Backups configured and (ideally) restore-tested for stateful data; DR posture matches RTO/RPO.
- 🟡 AMBER: Backups exist but never tested, or only partial coverage.
- 🔴 RED: Stateful workloads with no backup strategy.
- ⬜ N/A: Stateless estate with all config in Git/IaC.
- ⬜ UNKNOWN: Cannot determine restore testing — suggest user verify.

---

### 8.4 — Fargate Task Retirement / Maintenance Awareness

**What to check (Fargate services):**
- Whether the team understands Fargate task retirement (AWS retires tasks on old platform versions) and runs enough replicas + safe deploy config to absorb a task replacement without impact.
- `minimumHealthyPercent` and multi-AZ spread (cross-refs Sections 04/05) so a retirement-driven replacement is non-disruptive.

**How to check:**
1. For Fargate services, confirm `desiredCount` ≥ 2, `minimumHealthyPercent` and AZ spread support graceful single-task replacement.

**Rating:**
- 🟢 GREEN: Fargate services run ≥ 2 replicas across AZs with deploy config that absorbs a retirement/replacement transparently.
- 🟡 AMBER: Single replica or tight `minimumHealthyPercent` that would cause a brief gap during a forced task replacement.
- 🔴 RED: Single-task critical Fargate service — a task retirement is a full outage.
- ⬜ UNKNOWN: Cannot determine service criticality.

**Key talking point:** AWS periodically retires Fargate tasks running on outdated platform versions; design for it with multiple replicas and safe deploy bounds so a replacement is invisible. See [task retirement and maintenance for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-maintenance.html).

---

### 8.5 — Runbooks, On-Call & Post-Incident Review

**What to check (process — not API-detectable):**
- Current health signals that suggest which runbooks should exist (stopped tasks with failure reasons, deployment rollbacks).

**How to check:**
1. `aws ecs list-tasks --desired-status STOPPED` and describe a sample for `stoppedReason` (e.g., `CannotPullContainerError`, `OutOfMemory`, `ResourceInitializationError`).

**Rating:**
- ⬜ UNKNOWN: Runbook/on-call/PIR maturity cannot be read from estate state.

**Investigate manually:**
- Do you have runbooks for `CannotPullContainerError`, OOM task kills, `ResourceInitializationError`, capacity-provider scale-out failures, and deployment rollbacks?
- Is there a formal on-call rotation and escalation path? What AWS Support tier?
- Do you run blameless post-incident reviews and track action items to completion?

**If active failures are found:** cite them as evidence that the corresponding runbooks should exist and be tested.

---

### 8.6 — Task-Definition Revision Hygiene & Service Quotas

**What to check:**
- Whether stale task-definition revisions accumulate unbounded. Long-lived families can carry thousands of `ACTIVE` revisions, adding noise to `ListTaskDefinitions` and console navigation, and revisions are never cleaned up unless deregistered/deleted deliberately.
- Whether relevant ECS service quotas (e.g., services per cluster, tasks per service, ASG max capacity vs projected peak) are monitored rather than discovered at the limit.

**How to check:**
1. `aws ecs list-task-definitions --family-prefix <family> --status ACTIVE` → count revisions per family; spot-check for thousands of stale revisions.
2. `aws ecs list-task-definitions --status INACTIVE` → gauge cleanup backlog.
3. Cross-check ASG max (from Section 01) and Application Auto Scaling max (Section 05) against projected peak.

**Rating:**
- 🟢 GREEN: Old revisions pruned (deregistered, and deleted where appropriate); quotas tracked with headroom to peak.
- 🟡 AMBER: Revisions growing unbounded with no lifecycle process, or quotas checked only ad hoc.
- 🔴 RED: Quota already reached/blocking launches, or revision sprawl demonstrably slowing operations.
- ⬜ UNKNOWN: Cannot enumerate revisions or quota usage.

**Key talking point:** A revision must be **deregistered** (→ `INACTIVE`) before it can be **deleted** (`DeleteTaskDefinition` → `DELETE_IN_PROGRESS`); existing tasks/services referencing an `INACTIVE`/`DELETE_IN_PROGRESS` revision keep running and can still scale. `INACTIVE` revisions currently persist indefinitely, so treat cleanup as a deliberate lifecycle task rather than assuming AWS reclaims them. See [deregistering a task-definition revision](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deregister-task-definition-v2.html) and [ECS task-definition deletion](https://aws.amazon.com/blogs/containers/announcing-amazon-ecs-task-definition-deletion/).
