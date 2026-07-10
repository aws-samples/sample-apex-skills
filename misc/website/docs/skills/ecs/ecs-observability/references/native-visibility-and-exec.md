---
title: "ECS Observability — Native Visibility and ECS Exec"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/native-visibility-and-exec.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-observability/references/native-visibility-and-exec.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/native-visibility-and-exec.md). Edit the source, not this page.
:::

# ECS Observability — Native Visibility and ECS Exec

> **Part of:** [ecs-observability](../)
> **Purpose:** The zero-extra-cost visibility layer every ECS observability design should exploit before buying anything — service events, EventBridge, container health checks — plus ECS Exec for live debugging and its precise VPC endpoint requirements

**For the per-capability launch-type matrix, see:** [launch-type-matrix.md](launch-type-matrix)

---

## Table of Contents

1. [Service events and EventBridge](#service-events-and-eventbridge)
2. [Container health checks](#container-health-checks)
3. [ECS Exec](#ecs-exec)
4. [Monitoring plan baseline](#monitoring-plan-baseline)

---

## Service events and EventBridge

> Facts verified 2026-07-10 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_cwe_events.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service_events.html

- ECS emits EventBridge events for: container instance state change, task state change, deployment state change, hook state change, service action, container instance health change, daemon deployment state change, and daemon service action. For **container instance and task state-change events**, the `detail.version` field enables deduplication (events can be sent multiple times); **service action events carry `version` only in the main event body**, not in `detail` — don't build dedup logic on `detail.version` for those.
- **Service action events** carry `eventType` INFO/WARN/ERROR — the ERROR set is the natural alerting hook. As of 2026-07-10 the doc lists **seven** ERROR events: `SERVICE_TASK_PLACEMENT_FAILURE`, `SERVICE_DEPLOYMENT_FAILED`, `ECS_OPERATION_THROTTLED`, `SERVICE_DAEMON_PLACEMENT_CONSTRAINT_VIOLATED`, `SERVICE_DISCOVERY_OPERATION_THROTTLED`, `SERVICE_TASK_CONFIGURATION_FAILURE`, `SERVICE_HEALTH_UNKNOWN` (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service_events.html). **Match on `detail.eventType = ERROR`, not an enumerated name list** — a name-enumerated rule silently misses events AWS adds later. WARN includes `SERVICE_TASK_START_IMPAIRED`; INFO includes `SERVICE_STEADY_STATE`, `SERVICE_DEPLOYMENT_COMPLETED`.
- **Service event messages** (console / `describe-services`) are the first stop for troubleshooting: the console shows the 100 most recent scheduler + Service Auto Scaling events; duplicate messages are suppressed until resolved or 6 hours elapse (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-event-messages.html).
- Design cue: EventBridge rules on ERROR service actions + task state changes give deployment/placement alerting on every launch type with zero agents and zero per-metric cost — recommend this layer regardless of which metrics/traces stack wins.

## Container health checks

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/healthcheck.html

- Defined in the task definition (command/interval/timeout/retries/startPeriod); requires container agent ≥ 1.17.0; Fargate platform version ≥ 1.1.0.
- **ECS ignores Docker HEALTHCHECKs embedded in the image** unless the check is specified in the container definition — a common silent-gap surprise.
- Statuses: HEALTHY / UNHEALTHY / UNKNOWN; task health derives from essential containers that have health checks.
- Agent disconnect does NOT flip containers to UNHEALTHY — the last-heard-from status persists, so "healthy" can be stale during agent outages.

## ECS Exec

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html

Live interactive debugging over SSM Session Manager — no SSH, no inbound ports, no bastion.

**Launch-type support (one of the few capabilities spanning all four):**

| Launch type | Support |
|---|---|
| EC2 | Linux on any ECS-optimized AMI (incl. Bottlerocket); Windows on listed AMIs with agent ≥ 1.56 |
| Fargate | Linux + Windows |
| Managed Instances | Yes — and it is the **only** shell access (no SSH exists on MI) |
| EXTERNAL (ECS Anywhere) | Yes — explicitly supported |

**VPC endpoint requirements — be precise, this is commonly gotten wrong:**

- **For tasks in a VPC (EC2/Fargate/MI)** using interface VPC endpoints (or EC2-hosted `awsvpc` tasks with no internet path/NAT), ECS Exec requires the **`ssmmessages`** interface endpoint — the Session Manager channel endpoint. The ECS Exec doc names only `ssmmessages`; that it does **not** require the full `ssm` + `ec2messages` + `ssmmessages` trio generic SSM node management needs is an inference from that omission (the doc does not state the negative explicitly) — per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html.
- **On EXTERNAL (ECS Anywhere), the "only ssmmessages" simplification does not apply:** the on-prem host must already reach `ssm.<region>.amazonaws.com`, `ec2messages.<region>.amazonaws.com`, and `ssmmessages.<region>.amazonaws.com` — SSM Agent registration and credential rotation depend on them, and Exec rides on that same SSM plumbing (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html).
- Add a **KMS interface endpoint only if** you encrypt Exec sessions with your own customer-managed KMS key.
- Cross-reference: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-privatelink.html

**Operational and compliance constraints:**

- Task IAM role must carry SSM permissions (on EC2, ECS falls back to the instance role if the task has no role — an audit consideration in itself).
- Commands run as **root**; `readonlyRootFilesystem` is unsupported; IPv6-only tasks unsupported; cannot be enabled on already-running tasks; fixed 20-minute idle timeout; one session per Linux PID namespace; use `--container` to target sidecars (Runtime Monitoring, Service Connect); `initProcessEnabled: true` recommended to reap zombie processes.
- **Audit posture:** enable session logging to CloudWatch Logs/S3 via the cluster `executeCommandConfiguration` (logging = NONE/DEFAULT/OVERRIDE — needs extra task-role IAM and `script` + `cat` binaries in the image); every invocation is a CloudTrail `ExecuteCommand` event; **deny `ssm:StartSession`** in IAM to prevent unlogged side-channel sessions.

## Monitoring plan baseline

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_monitoring.html

The ECS developer guide's monitoring section frames the plan the skill should elicit from the customer: monitoring goals, resources to monitor, cadence, tools, owners, and alerting; establish a performance baseline; minimum viable coverage = cluster + service CPU/memory reservation and utilization.

AWS-recommended alarm set for ECS (with and without Container Insights): https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Best_Practice_Recommended_Alarms_AWS_Services.html#ECS

Note (verified 2026-07-10): the former ECS Best Practices Guide has been folded into the developer guide, and no standalone observability chapter is documented there as of 2026-07-10 — observability-relevant guidance is scattered (stdout/stderr logging in container considerations, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-considerations.html; VPC Flow Logs for per-task traffic with `awsvpc`, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-network.html; LB health-check tuning pages). Don't cite a best-practices observability chapter — none is documented.
