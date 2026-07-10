---
title: "Section 06 — Observability Posture"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/observability.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/observability.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/observability.md). Edit the source, not this page.
:::

# Section 06 — Observability Posture

## Purpose
Assess whether the estate is observable enough to detect and diagnose issues fast: **Container Insights with enhanced observability**, log routing/retention (`awslogs` vs FireLens), alerting, and tracing. This section **rates posture at audit depth**; designing the logs/metrics/traces stack (FireLens vs ADOT vs Datadog, routing, cost control) belongs to **`ecs-observability`**.

## Checks to Execute

### 6.1 — Container Insights (enhanced observability)

**What to check:**
- Cluster `containerInsights` setting: `disabled`, `enabled` (standard), or `enhanced`.
- Account-level default (new clusters inherit it).

**How to check:**
1. `aws ecs describe-clusters --clusters <name> --include SETTINGS` → `settings[].name == "containerInsights"` value.
2. `aws ecs list-account-settings --name containerInsights` for the account default.

**Rating:**
- 🟢 GREEN: **Container Insights with enhanced observability** enabled — task- and container-level metrics, curated dashboards, deployment/task-set tracking, log correlation.
- 🟡 AMBER: Standard Container Insights (`enabled`) only — cluster/service aggregates but not the enhanced task/container granularity.
- 🔴 RED: Container Insights disabled — no CloudWatch container telemetry, blind during incidents.
- ⬜ UNKNOWN: Cannot read cluster settings.

**Key talking point:** Container Insights **with enhanced observability** (GA for ECS Dec 2, 2024; supports Fargate, EC2, and Managed Instances) adds task/container-level granularity and out-of-the-box dashboards that reduce MTTD/MTTR; AWS recommends it over standard Container Insights. Note it is billed as custom metrics. See [monitor ECS with Container Insights enhanced observability](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html) and [enhanced-observability metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html).

---

### 6.2 — Log Routing & Delivery Mode (awslogs / FireLens)

**This is the single scoring home for all log-driver checks** (driver presence, routing, `awslogs-stream-prefix`, and delivery mode). Task-definition check 3.3 defers here — do not double-score.

**What to check:**
- Log driver per container: `awslogs` (→ CloudWatch Logs) or `awsfirelens` (Fluent Bit/Fluentd → CloudWatch/OpenSearch/S3/3rd-party). **Containers with no log driver (logs unrecoverable).**
- `awslogs-stream-prefix` set (traceable streams).
- **Delivery mode** — `logConfiguration.options.mode` (`blocking` vs `non-blocking`) and, for `non-blocking`, `max-buffer-size`. Since **June 25, 2025** the ECS default (when neither the container `mode` nor the `defaultLogDriverMode` account setting is set) is **`non-blocking`**, which **silently drops** log lines under back-pressure once the buffer fills. Blocking mode preserves all logs but can stall the app if the log driver is unavailable.

**How to check:**
1. Task definitions → `containerDefinitions[].logConfiguration.logDriver` and `.options` (`mode`, `max-buffer-size`, `awslogs-stream-prefix`).
2. `aws ecs list-account-settings --name defaultLogDriverMode` for the account default that applies when `mode` is unset.

**Rating:**
- 🟢 GREEN: Every container routes logs via `awslogs` or FireLens to a durable, queryable destination, with `awslogs-stream-prefix` set, and a **deliberate** delivery mode — either `blocking`, or `non-blocking` with a `max-buffer-size` sized to the workload.
- 🟡 AMBER: Logging present but inconsistent across services, `awslogs` where FireLens routing/filtering is warranted, `awslogs` on EC2 tasks with no `awslogs-stream-prefix` (logs land under bare Docker container IDs), **or** relying on the implicit `non-blocking` default with no `max-buffer-size` set on log-sensitive services (silent-drop risk).
- 🔴 RED: Containers with no log driver — logs unrecoverable.
- ⬜ UNKNOWN: Cannot read task definitions.

**Key talking point:** FireLens routes ECS logs to AWS services or partner destinations via Fluent Bit/Fluentd with filtering and multi-destination fan-out. Confirm `awslogs-stream-prefix` is set — it is **required when using Fargate** and optional (but strongly recommended) on EC2; with it, streams take the form `prefix-name/container-name/ecs-task-id` (use the service name as the prefix), without it logs are named by the opaque Docker container ID. Also confirm the **delivery mode** is intentional: the June 25 2025 default flip to `non-blocking` prioritizes task availability over log completeness, so audit/compliance-critical services should set `blocking` explicitly or size `max-buffer-size` (default `10m`) for `non-blocking`. Routing/design choices → **`ecs-observability`**. Verified 2026-07-10. See the [LogConfiguration API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html) (stream-prefix requirement, `mode`, `max-buffer-size`), [ECS account settings — default log driver mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html), and [FireLens for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html).

---

### 6.3 — Log Retention

**What to check:**
- CloudWatch log-group retention for the `awslogs`/FireLens destination groups (no retention = kept forever at cost; too-short = lost audit trail).

**How to check:**
1. `aws logs describe-log-groups --log-group-name-prefix <prefix>` → `retentionInDays`.

**Rating:**
- 🟢 GREEN: Retention policy set appropriate to the workload (e.g., ≥ 30 days for operational logs; longer where compliance requires).
- 🟡 AMBER: No retention policy (logs retained indefinitely, growing cost), or retention shorter than incident-investigation needs.
- 🔴 RED: Retention set so short that recent-incident logs are already gone.
- ⬜ UNKNOWN: Cannot read log groups.

---

### 6.4 — Alerting

**What to check:**
- CloudWatch alarms on ECS/Container Insights metrics (service CPU/memory, running task count vs desired, deployment failures).
- Whether alarms route to a notification target (SNS/on-call).

**How to check:**
1. `aws cloudwatch describe-alarms` → filter for ECS/`ContainerInsights` namespace dimensions and check `AlarmActions`.

**Rating (health/capacity alerting; deployment-failure alerting is scored once, in check 4.5 — do not double-count):**
- 🟢 GREEN: Alarms cover the critical health/capacity signals (service unhealthy/running-count drop, high CPU/memory, target-group unhealthy hosts) and route to on-call.
- 🟡 AMBER: Some alarms but incomplete coverage, or no notification action wired.
- 🔴 RED: No alarms — issues found only by customer reports.
- ⬜ UNKNOWN: Cannot list alarms.

**Minimum viable alert set:** running-task-count below desired, service CPU/memory saturation, target-group unhealthy-host count. (Deployment failure/rollback alerting — the `SERVICE_DEPLOYMENT_FAILED` signal — is rated in **check 4.5**, not here.)

**Commonly omitted:** an EventBridge rule on ECS service-action events — the earliest reliable signal of capacity pressure. Filter `source: ["aws.ecs"]` with `eventName == SERVICE_TASK_PLACEMENT_FAILURE` (scoped by `reason` such as `RESOURCE:CPU`, `RESOURCE:MEMORY`, `RESOURCE:INSTANCE`, `RESOURCE:FARGATE`), routed to on-call. The `SERVICE_DEPLOYMENT_FAILED` deployment-failure rule belongs to check 4.5. See [monitor ECS events with EventBridge filtering](https://aws.amazon.com/blogs/containers/monitor-amazon-ecs-events-with-amazon-eventbridge-filtering/).

---

### 6.5 — Tracing (optional, criticality-dependent)

**What to check:**
- Distributed tracing via ADOT (OpenTelemetry) or X-Ray sidecar for request-path services.
- **CloudWatch Application Signals** (APM: SLOs, service map, correlated traces) on critical services — enabled on ECS via a custom setup that installs the CloudWatch agent + ADOT SDK as a sidecar (ECS is not auto-discovered the way EKS is, so service/environment names must be supplied).

**How to check:**
1. Task definitions → look for an ADOT collector, CloudWatch-agent sidecar (Application Signals), or X-Ray daemon sidecar container.

**Rating:**
- 🟢 GREEN: Tracing instrumented for multi-hop request-path services (and/or Application Signals with SLOs on critical services).
- 🟡 AMBER: Partial or ad-hoc tracing.
- 🔴 RED: Complex microservice call graph with no tracing (blind to cross-service latency).
- ⚪ N/A: Simple single-service estate (no multi-hop request path to trace).
- ⬜ UNKNOWN: Cannot determine the call topology. Design → **`ecs-observability`**.

**Key talking point:** Application Signals is supported/tested on Amazon ECS (Java, Python, Node.js, .NET) and gives standardized latency/availability/error metrics, SLOs, and an application map without custom dashboards; on ECS you set it up explicitly (sidecar) rather than relying on auto-discovery. See [enable Application Signals on Amazon ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-ECSMain.html).
