# Layer 7a — Audit Logging & Monitoring

Proving *what happened* is the backbone of every compliance audit. On ECS three sources compound: AWS-API-level (**CloudTrail**), cluster/service metrics (**Container Insights**), and application/container logs (**`awslogs` / FireLens**).

## CloudTrail — the ECS API audit trail

CloudTrail is on by default in every account (Event history), but for compliance you need a **trail delivering to S3** for durable, long-term retention. It records all ECS control-plane API calls (`RegisterTaskDefinition`, `CreateService`, `UpdateService`, `PutAccountSettingDefault`, role-assumption events, …). Because **task-role credentials carry a `taskArn` session context**, CloudTrail shows *which task* made a downstream API call — use CloudTrail + CloudTrail Insights to detect suspicious write activity by an assumed task role (see the ECS [roles recommendations — CloudTrail monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html#security-iam-roles-recommendations-cloudtrail-monitoring)). Reference: [Log ECS API calls with CloudTrail](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/logging-using-cloudtrail.html).

## Container Insights — metrics & performance/observability

**Amazon CloudWatch Container Insights** collects cluster/service/task-level metrics (CPU, memory, network, task counts) and, with enhanced observability, container-level detail. It's the metrics backbone for detecting anomalous resource use (e.g. crypto-mining spikes) and for the operational side of an audit. (Deep observability *design* — FireLens routing, Prometheus/ADOT, third-party APM selection — belongs to `ecs-observability`; here it's the security/audit-evidence angle.)

## Application & container logs — `awslogs` vs FireLens

- **`awslogs` log driver** — the simplest path: container stdout/stderr → CloudWatch Logs. The **task execution role** needs the CloudWatch Logs permissions (in `AmazonECSTaskExecutionRolePolicy`). Reference: [Send ECS logs to CloudWatch](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html).
  > **Reliability caveat — the default log mode is now `non-blocking` (silent log loss).** On **June 25, 2025** AWS changed the ECS default `defaultLogDriverMode` from `blocking` to `non-blocking` to prioritize task availability over logging. In `non-blocking` mode, when the in-memory buffer (`max-buffer-size`, default **10m** = 10 MiB per the [LogConfiguration API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html)) fills faster than logs drain to CloudWatch, **logs are dropped silently** — a real problem when the logs *are* your compliance/audit evidence. Mitigate by (a) setting `mode: blocking` in the container's `logConfiguration`, (b) setting the account default back with `aws ecs put-account-setting-default --name defaultLogDriverMode --value blocking`, and/or (c) raising `max-buffer-size` if you keep non-blocking. Weigh log-completeness vs the availability risk `blocking` reintroduces (a stalled CloudWatch path can block the app / fail health checks). Verified 2026-07-10 — [ECS account settings — default log driver mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html).
- **FireLens (Fluent Bit / Fluentd)** — for routing to CloudWatch Logs / OpenSearch / S3 / SIEM / third-party, log filtering, and multi-destination fan-out. Use when you need SIEM forwarding or log-cost control.
- For **Windows tasks using `awslogs`** with a task execution role, also set `ECS_ENABLE_AWSLOGS_EXECUTIONROLE_OVERRIDE=true` on the container instance ([Bootstrapping Windows container instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/bootstrap_windows_container_instance.html), verified 2026-07-10).

## Encryption + retention by regime (set deliberately)

- **Encrypt** the CloudWatch Logs groups and the CloudTrail S3 bucket with a **customer-managed KMS key** for high-sensitivity workloads.
- **Retention** — set the log-group and trail retention to the regime minimum (illustrative, verify per regime): PCI-DSS commonly **1 year** (3 months immediately available); **HIPAA** documentation retention is **6 years**; **SOX (§802)** is typically **7 years**; FedRAMP per the System Security Plan / continuous-monitoring cadence. Don't over-retain sensitive logs beyond requirement.

## SIEM forwarding

CloudWatch Logs subscription → Kinesis Data Streams → Firehose → SIEM (Splunk, Elastic, Datadog, Microsoft Sentinel), or route directly via **FireLens** from the tasks. Keep the pipeline in-Region (and EU-resident where the customer's GDPR data-residency policy requires it — EU-only residency is a customer choice, not a GDPR mandate; see [compliance-regimes.md](compliance-regimes.md)).

## Shared responsibility (Layer 7a)

| AWS manages | Customer manages |
|---|---|
| CloudTrail capture of ECS API calls; Container Insights collection; CloudWatch Logs/S3 durability | Creating a durable trail; enabling Container Insights; choosing `awslogs` vs FireLens + execution-role log permissions; log encryption (CMK) + retention to the regime; SIEM pipeline; log review/alerting |

## Sources
- [Log ECS API calls with CloudTrail](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/logging-using-cloudtrail.html) · [Roles recommendations — CloudTrail monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html#security-iam-roles-recommendations-cloudtrail-monitoring)
- [Send ECS logs to CloudWatch (`awslogs`)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html) · [Logging and Monitoring in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-logging-monitoring.html) · [ECS account settings — default log driver mode (non-blocking default, June 25 2025)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html)
