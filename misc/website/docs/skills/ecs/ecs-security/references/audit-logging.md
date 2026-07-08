---
title: "Layer 7a — Audit Logging & Monitoring"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/audit-logging.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/audit-logging.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/audit-logging.md). Edit the source, not this page.
:::

# Layer 7a — Audit Logging & Monitoring

Proving *what happened* is the backbone of every compliance audit. On ECS three sources compound: AWS-API-level (**CloudTrail**), cluster/service metrics (**Container Insights**), and application/container logs (**`awslogs` / FireLens**).

## CloudTrail — the ECS API audit trail

CloudTrail is on by default in every account (Event history), but for compliance you need a **trail delivering to S3** for durable, long-term retention. It records all ECS control-plane API calls (`RegisterTaskDefinition`, `CreateService`, `UpdateService`, `PutAccountSettingDefault`, role-assumption events, …). Because **task-role credentials carry a `taskArn` session context**, CloudTrail shows *which task* made a downstream API call — use CloudTrail + CloudTrail Insights to detect suspicious write activity by an assumed task role (see the ECS [roles recommendations — CloudTrail monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html#security-iam-roles-recommendations-cloudtrail-monitoring)). Reference: [Log ECS API calls with CloudTrail](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/logging-using-cloudtrail.html).

## Container Insights — metrics & performance/observability

**Amazon CloudWatch Container Insights** collects cluster/service/task-level metrics (CPU, memory, network, task counts) and, with enhanced observability, container-level detail. It's the metrics backbone for detecting anomalous resource use (e.g. crypto-mining spikes) and for the operational side of an audit. (Deep observability *design* — FireLens routing, Prometheus/ADOT, third-party APM selection — belongs to `ecs-observability`; here it's the security/audit-evidence angle.)

## Application & container logs — `awslogs` vs FireLens

- **`awslogs` log driver** — the simplest path: container stdout/stderr → CloudWatch Logs. The **task execution role** needs the CloudWatch Logs permissions (in `AmazonECSTaskExecutionRolePolicy`). Reference: [Send ECS logs to CloudWatch](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html).
- **FireLens (Fluent Bit / Fluentd)** — for routing to CloudWatch Logs / OpenSearch / S3 / SIEM / third-party, log filtering, and multi-destination fan-out. Use when you need SIEM forwarding or log-cost control.
- For **Windows tasks using `awslogs`**, also set `ECS_ENABLE_AWSLOGS_EXECUTIONROLE_OVERRIDE=true` on the container instance (verified).

## Encryption + retention by regime (set deliberately)

- **Encrypt** the CloudWatch Logs groups and the CloudTrail S3 bucket with a **customer-managed KMS key** for high-sensitivity workloads.
- **Retention** — set the log-group and trail retention to the regime minimum (illustrative, verify per regime): PCI-DSS commonly **1 year** (3 months immediately available); HIPAA/SOX often **6 years**; FedRAMP per the System Security Plan / continuous-monitoring cadence. Don't over-retain sensitive logs beyond requirement.

## SIEM forwarding

CloudWatch Logs subscription → Kinesis Data Streams → Firehose → SIEM (Splunk, Elastic, Datadog, Microsoft Sentinel), or route directly via **FireLens** from the tasks. Keep the pipeline in-Region (and in-EU for GDPR).

## Shared responsibility (Layer 7a)

| AWS manages | Customer manages |
|---|---|
| CloudTrail capture of ECS API calls; Container Insights collection; CloudWatch Logs/S3 durability | Creating a durable trail; enabling Container Insights; choosing `awslogs` vs FireLens + execution-role log permissions; log encryption (CMK) + retention to the regime; SIEM pipeline; log review/alerting |

## Sources
- [Log ECS API calls with CloudTrail](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/logging-using-cloudtrail.html) · [Roles recommendations — CloudTrail monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html#security-iam-roles-recommendations-cloudtrail-monitoring)
- [Send ECS logs to CloudWatch (`awslogs`)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html) · [Logging and Monitoring in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-logging-monitoring.html)
