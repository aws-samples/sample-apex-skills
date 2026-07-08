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

### 6.2 — Log Routing (awslogs / FireLens)

**What to check:**
- Log driver per container: `awslogs` (→ CloudWatch Logs) or `awsfirelens` (Fluent Bit/Fluentd → CloudWatch/OpenSearch/S3/3rd-party).
- Containers with no log driver.

**How to check:**
1. Task definitions → `containerDefinitions[].logConfiguration.logDriver` and options.

**Rating:**
- 🟢 GREEN: All containers route logs via `awslogs` or FireLens to a durable, queryable destination, with `awslogs-stream-prefix` set so streams are traceable to task/container.
- 🟡 AMBER: Logging present but inconsistent across services, `awslogs` where FireLens routing/filtering is warranted, or `awslogs` on EC2 tasks with no `awslogs-stream-prefix` (logs land under bare Docker container IDs, making incident triage hard).
- 🔴 RED: Containers with no log driver — logs unrecoverable.
- ⬜ UNKNOWN: Cannot read task definitions.

**Key talking point:** FireLens routes ECS logs to AWS services or partner destinations via Fluent Bit/Fluentd with filtering and multi-destination fan-out. Also confirm `awslogs-stream-prefix` is set — it is **required on Fargate** and optional (but strongly recommended) on EC2; with it, streams take the form `prefix/container-name/ecs-task-id` (use the service name as the prefix), without it logs are named by opaque Docker container ID. Routing/design choices → **`ecs-observability`**. See [FireLens for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html).

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

**Rating:**
- 🟢 GREEN: Alarms cover the critical signals (service unhealthy/running-count drop, high CPU/memory, deployment failure) and route to on-call.
- 🟡 AMBER: Some alarms but incomplete coverage, or no notification action wired.
- 🔴 RED: No alarms — issues found only by customer reports.
- ⬜ UNKNOWN: Cannot list alarms.

**Minimum viable alert set:** running-task-count below desired, service CPU/memory saturation, deployment failure/rollback, target-group unhealthy-host count.

**Commonly omitted:** an EventBridge rule on ECS service-action / deployment-failure events — the earliest reliable signal of capacity pressure and rollout trouble. Filter `source: ["aws.ecs"]` with `eventName` in `SERVICE_TASK_PLACEMENT_FAILURE` (scoped by `reason` such as `RESOURCE:CPU`, `RESOURCE:MEMORY`, `RESOURCE:INSTANCE`, `RESOURCE:FARGATE`) and `SERVICE_DEPLOYMENT_FAILED`, routed to on-call. See [monitor ECS events with EventBridge filtering](https://aws.amazon.com/blogs/containers/monitor-amazon-ecs-events-with-amazon-eventbridge-filtering/).

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
- ⬜ UNKNOWN / N/A: Simple single-service estate, or cannot determine call topology. Design → **`ecs-observability`**.

**Key talking point:** Application Signals is supported/tested on Amazon ECS (Java, Python, Node.js, .NET) and gives standardized latency/availability/error metrics, SLOs, and an application map without custom dashboards; on ECS you set it up explicitly (sidecar) rather than relying on auto-discovery. See [enable Application Signals on Amazon ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-ECSMain.html).
