---
name: ecs-observability
description: 'Advise on Amazon ECS observability architecture — select the logs/metrics/traces stack (CloudWatch, Container Insights, X-Ray, ADOT/OpenTelemetry, Managed Prometheus/Grafana, FireLens to third-party) by compliance needs, existing tooling, scale, budget, and launch types (EC2, Fargate, Managed Instances, ECS Anywhere). Use for "how should we monitor our ECS services", "Container Insights or Prometheus for ECS", "are we losing ECS container logs", "set up tracing on Fargate", "ECS logging best practices", "Datadog vs CloudWatch for ECS", "GPU metrics for ECS tasks", or "plan live-debug access to an ECS task". Any ECS logging, metrics, tracing, or alerting design question qualifies even if "observability" is never said. Skip for EKS/Kubernetes (eks-* skills), deployment mechanics/CI-CD/deploy-failure diagnosis (ecs-devops; deploy-failure alerting stays here), security posture beyond observability audit logging (ecs-security), live-estate audits (ecs-operation-review), and FinOps audits of observability spend.'
---

# ECS Observability

Advisory skill for designing the observability architecture of Amazon ECS workloads — which logging pipeline, which metrics stack, which tracing path, driven by the customer's compliance posture, existing tooling, scale, budget, and the launch types they actually run. This is **primarily a design-and-selection brain**: it produces recommendations and decision rationale, with AWS documentation URLs for every load-bearing fact — and it carries the diagnostic facts (the log-loss gate, ECS Exec constraints) that troubleshooting asks need, without being a step-by-step runbook.

> **The accuracy bar (non-negotiable for this skill).** Launch-type scope-bleed is the #1 error class in this domain — capabilities documented for one launch type get silently generalized to all four. Every capability claim in this skill is scoped to EC2 / Fargate / Managed Instances (MI) / ECS Anywhere (EXTERNAL), and where AWS docs are silent the claim is marked "undocumented — verify". Never state launch-type support you cannot cite to an AWS-published source. When you can't ground a claim, say so — do not synthesize.

## When to Use This Skill

**Activate when the user wants to:**
- Choose between CloudWatch-native (Container Insights, X-Ray, Application Signals), open-source-flavored (ADOT, Amazon Managed Prometheus, Amazon Managed Grafana), or third-party (Datadog, Splunk, SIEM via FireLens) observability for ECS
- Design log delivery — awslogs vs FireLens, blocking vs non-blocking mode, buffer sizing, multi-destination routing
- Decide standard vs enhanced Container Insights, or how to get GPU telemetry from ECS tasks
- Pick a tracing path for new or existing ECS services (ADOT/OTel vs legacy X-Ray SDK/daemon)
- Understand what observability each launch type (EC2, Fargate, Managed Instances, ECS Anywhere) can and cannot support
- Plan live-debugging access (ECS Exec) including private-subnet VPC endpoint requirements
- Weigh compliance requirements (no log loss, session auditing, KMS encryption) against availability and cost

**Do NOT use this skill for:**
- EKS or any Kubernetes observability → use `eks-best-practices` (design guidance) or `eks-operation-review` (live-cluster audit), or the other `eks-*` skills
- ECS deployment *mechanics* — circuit breaker configuration, rollback strategy, CI/CD pipelines → use `ecs-devops`. Deployment-failure *alerting and visibility* (e.g., EventBridge on `SERVICE_DEPLOYMENT_FAILED`) stays here.
- ECS security posture, IAM hardening, compliance audits beyond observability's audit-logging angle → use `ecs-security`
- Scoring or auditing a live ECS estate against a rubric → use `ecs-operation-review`
- Overall ECS architecture — compute selection, networking, service design → use `ecs-architect`
- GenAI/LLM workload design on ECS (GPU serving stacks, model hosting) → use `ecs-genai`; come back here for the GPU *telemetry* question
- Cost optimization of an existing observability bill as a FinOps exercise — this skill flags cost levers during design but does not audit spend

## The Decision Framework

Elicit these five criteria before recommending a stack — each one prunes the option space:

| Criterion | Ask | Why it decides |
|---|---|---|
| **Launch types in use** | EC2, Fargate, Managed Instances, EXTERNAL — which, today and planned? | Hard eliminator. ADOT/AMP is unsupported on EXTERNAL; agentless GPU metrics are MI-only; Fargate forbids host agents; App Signals daemon strategy excludes Fargate. Check [references/launch-type-matrix.md](references/launch-type-matrix.md) before every claim. |
| **Compliance needs** | Can any log record be lost? Are debug sessions audited? Customer-managed KMS? | Drives the blocking vs non-blocking log gate, FireLens filesystem buffering, ECS Exec session logging, and KMS endpoint/key-policy work. |
| **Existing tooling** | Grafana/PromQL estate? Datadog/Splunk/SIEM contract? OTel standardization? | Existing Grafana → ADOT+AMP+AMG. Third-party APM/SIEM → FireLens routing. No estate → CloudWatch-native is the lowest-friction default. |
| **Scale** | Log MB/s per task, task count, metric cardinality | High log throughput breaks default buffers (silent loss); container-level enhanced CI multiplies metric series; sidecar-per-task overhead compounds with task count. |
| **Budget** | Appetite for custom-metric, log-ingestion, and AMP/AMG spend | Free vended metrics + EventBridge events are the zero-cost floor; enhanced CI and high-cardinality Prometheus are the main cost levers. Link https://aws.amazon.com/cloudwatch/pricing/ — never quote prices. |

### Default recommendation shape

For a CloudWatch-centric customer with no contrary criteria (EC2/Fargate fleets — EXTERNAL needs a different shape, since ADOT and Container Insights are not documented there): **awslogs (with an explicit, documented delivery-mode decision) + Container Insights enhanced + ADOT sidecar for traces + EventBridge alerting on service action ERROR events.** Enhanced is AWS's recommended Container Insights tier (per https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-cluster.html) — but it adds container-level metric cardinality, a cost lever to surface (Advisory Rule 3; cost posture in [references/metrics-stacks.md](references/metrics-stacks.md)). For MI fleets the logs + metrics + EventBridge parts carry over, but the ADOT-sidecar tracing leg is **not documented for Managed Instances as of 2026-07-10** (the ADOT integration page enumerates Fargate + EC2 only, per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html) — verify against the live doc before recommending it there (see the matrix's ADOT row). Deviate per the criteria above.

## Logs — the decision gate every engagement must surface

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html

**Since June 25, 2025, the ECS default log delivery mode is `non-blocking`** — and non-blocking mode **silently drops logs** when its in-memory buffer (default `max-buffer-size`: 10 MiB) fills. No metric, no daemon log line, no signal (per https://aws.amazon.com/blogs/containers/preventing-log-loss-with-non-blocking-mode-in-the-awslogs-container-log-driver/). The alternative, `blocking`, preserves every record but can hang the application and fail health checks if the log pipeline backs up. This is a **compliance-versus-availability decision**, and since the 2025 default change the risky posture is what customers get by *not* deciding:

- **Availability-first** (user-facing services, tolerable loss): keep `non-blocking`, size `max-buffer-size` to ~25 MB for in-Region delivery at up to ~5 MB/s per container (AWS benchmark guidance — "no observed loss" in AWS's test runs, not a guarantee); above 6 MB/s AWS calls the driver's behavior "less predictable and consistent" — that becomes a FireLens conversation (see reference). Document the accepted loss risk.
- **Completeness-first** (audit/financial/security logs): set `mode: blocking` per container or set the `defaultLogDriverMode` account setting — a **per-Region** setting, repeat it in every Region running tasks — and accept that a CloudWatch disruption can stall the app.
- **Both required**: FireLens (Fluent Bit) with filesystem buffering — loss-resistant without blocking stdout/stderr.
- Always audit the effective account default first: `aws ecs list-account-settings --name defaultLogDriverMode --effective-settings`.

FireLens is also the usual routing layer when the destination is not CloudWatch (Splunk, Datadog, OpenSearch, S3, Firehose, SIEMs) — though the native `splunk` log driver is documented on both Fargate and EC2 as a FireLens-free path to Splunk. FireLens is documented for **Linux tasks on Fargate and EC2 only**; MI and EXTERNAL support is undocumented — verify before advising.

**For buffer benchmarks, FireLens rules, and high-throughput patterns, see:** [Log Delivery Reference](references/log-delivery.md)

## Metrics — Container Insights tiers and the GPU trap

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html and https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html

- **Standard** Container Insights (`containerInsights=enabled`): task/service/cluster-level metrics. **Enhanced** (`enhanced`, released Dec 2024): adds container-level metrics, per-TaskId dimensions, and health-status metrics — **AWS's recommended default**, at the cost of more metric series (cardinality is the main cost lever — link https://aws.amazon.com/cloudwatch/pricing/, never quote prices). Documented launch types: EC2 (agent ≥ 1.29), Fargate, Managed Instances; EXTERNAL is not listed — don't claim it.
- **GPU telemetry is the sharpest launch-type trap:** agentless GPU/DCGM metrics (utilization, memory, power, temperature at container/task/instance level) are **Managed Instances-ONLY** and require enhanced CI (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html). The **EC2 launch type gets only the free GPU *reservation* metric** — GPU utilization there means customer-managed DCGM/CloudWatch-agent tooling. Never generalize in either direction.
- Prometheus/Grafana route: ADOT sidecar remote-writes to Amazon Managed Service for Prometheus, visualized in Amazon Managed Grafana — **documented for Fargate and EC2 only; EXTERNAL explicitly unsupported, MI not documented as of 2026-07-10** (see the ADOT row of [references/launch-type-matrix.md](references/launch-type-matrix.md) for the source quote) — verify before advising MI. Alternative keeping data in CloudWatch: the CloudWatch agent's Prometheus scrape support.
- Zero-cost floor available everywhere: free vended CPU/memory metrics + EventBridge service/task/deployment events + container health checks.

**For metric tables, instance-level collection, and AMP vs CloudWatch-agent-Prometheus selection, see:** [Metrics Stacks Reference](references/metrics-stacks.md)

## Traces — OTel is the path; X-Ray SDK/daemon is legacy

> Facts verified 2026-07-10 against https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html

- **The X-Ray SDKs and daemon entered maintenance mode on February 25, 2026** (security fixes only); AWS recommends OpenTelemetry. Steer all new tracing to the **ADOT sidecar collector** (`public.ecr.aws/aws-observability/aws-otel-collector`), which still delivers traces to the X-Ray backend — the maintenance-mode timeline names only the SDKs and daemon, not the backend service (inference from https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html, which covers SDKs/daemon only; the migration guide keeps X-Ray as the trace destination).
- **CloudWatch Application Signals on ECS is custom setup with no autodiscovery** — service names are wired via env vars. Sidecar strategy: EC2 + Fargate, requires `awsvpc`. Daemon strategy: one agent per cluster, **excludes Fargate**. MI: not documented for either strategy as of 2026-07-10; EXTERNAL: sidecar structurally excluded (`awsvpc` required), daemon undocumented (see the App Signals rows of the matrix).
- Placement rule: Fargate → sidecar only (no host access); EC2 → sidecar or daemon-scheduled collector; MI → **neither pattern is documented as of 2026-07-10** (the ADOT page enumerates Fargate + EC2 only — per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html; verify against the live doc before advising, see the matrix's ADOT row); EXTERNAL → ADOT unsupported.

**For migration gotchas, IAM, and Application Signals strategy details, see:** [Tracing and Signals Reference](references/tracing-and-signals.md)

## Live debugging — ECS Exec

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html

- Works on **all four launch types** (one of the few capabilities that does), and is the **sole shell path on Managed Instances** (no SSH there).
- Private-subnet precision, **for tasks in a VPC (EC2/Fargate/MI)**: ECS Exec needs the **`ssmmessages`** interface VPC endpoint — **not** the full `ssm`/`ec2messages` trio (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) — plus a **KMS endpoint only when** sessions are encrypted with a customer-managed key. On EXTERNAL (ECS Anywhere) the host must reach `ssm` + `ec2messages` + `ssmmessages` regardless — an SSM Agent registration prerequisite (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html).
- Compliance anchors: session logging via cluster `executeCommandConfiguration`, CloudTrail `ExecuteCommand` events, and an IAM deny on `ssm:StartSession` to close the unlogged side door. Commands run as root; `readonlyRootFilesystem` unsupported.

**For full constraints and audit setup, see:** [Native Visibility and ECS Exec Reference](references/native-visibility-and-exec.md)

## Launch-Type Discipline

Before asserting any capability, check [references/launch-type-matrix.md](references/launch-type-matrix.md) — the per-capability EC2/Fargate/MI/EXTERNAL matrix with a source URL per row. The matrix is the single source of truth for these facts; the recurring traps (restated here per the matrix, verified 2026-07-10 — re-check the matrix row before load-bearing use):

- Agentless GPU/DCGM → **MI only** (EC2 gets reservation-only).
- ADOT/AMP → documented for **Fargate + EC2**; EXTERNAL explicitly unsupported; **MI undocumented — verify before advising**.
- FireLens → Linux Fargate/EC2 documented; **MI/EXTERNAL undocumented — verify before advising**.
- Application Signals daemon → **no Fargate**; sidecar → requires `awsvpc` (which EXTERNAL cannot run).
- EXTERNAL supports bridge/host/none networking only — anything demanding `awsvpc` is structurally out.
- Fargate has no host — every agent is an in-task sidecar; MI's AMI is AWS-owned — nothing can be baked into it.

## How to Use the References

This skill uses **progressive disclosure** — essential decision guidance is in this file; detailed reference material is loaded on demand:

| Reference | Load when the task is about… |
|---|---|
| [log-delivery.md](references/log-delivery.md) | blocking vs non-blocking details, buffer-size benchmarks, awslogs options, FireLens/Fluent Bit configuration, filesystem buffering, high-throughput logging, routing to third-party destinations (Datadog, Splunk, SIEMs) and awslogs-vs-FireLens selection |
| [metrics-stacks.md](references/metrics-stacks.md) | Container Insights standard vs enhanced metric tables, GPU/DCGM scoping, instance-level metrics, ADOT+AMP+AMG vs CloudWatch-agent Prometheus, metric cost levers |
| [tracing-and-signals.md](references/tracing-and-signals.md) | X-Ray maintenance-mode details and migration, ADOT collector setup and IAM, Application Signals sidecar vs daemon, language support |
| [launch-type-matrix.md](references/launch-type-matrix.md) | any "does X work on launch type Y" question — check before every capability claim |
| [native-visibility-and-exec.md](references/native-visibility-and-exec.md) | EventBridge events, service events, container health checks, ECS Exec constraints and VPC endpoints, monitoring-plan baseline |

## Advisory Rules

1. **Scope every capability claim by launch type.** If the matrix row says "undocumented — verify", say exactly that to the customer and check the live AWS doc.
2. **Always surface the log delivery-mode gate** in any logging discussion — the customer must consciously choose a failure mode; the post-2025 default chooses silent loss for them.
3. **Never quote prices or assert the enhanced-CI pricing model for ECS** — link https://aws.amazon.com/cloudwatch/pricing/ instead.
4. **Do not recommend X-Ray SDK/daemon for new builds** — ADOT/OTel, always, since the 2026-02-25 maintenance date.
5. **Recommend the zero-cost floor first** (vended metrics, EventBridge ERROR-event alerting, health checks) — it survives every stack decision and every launch type.
6. **Cite as you advise** — every load-bearing recommendation carries its AWS documentation URL, dated where the fact is volatile.

## Sources

- [ECS account settings — default log driver mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html) · [LogConfiguration API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html) · [Using the awslogs driver](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html) · [Preventing log loss with non-blocking mode (AWS Containers blog)](https://aws.amazon.com/blogs/containers/preventing-log-loss-with-non-blocking-mode-in-the-awslogs-container-log-driver/)
- [Using FireLens](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html) · [High-throughput log configuration](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/firelens-docker-buffer-limit.html)
- [Container Insights for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html) · [Setting up Container Insights on ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-cluster.html) · [Enhanced observability metrics for ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html) · [Container Insights enhanced observability What's New (Dec 2024)](https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-cloudwatch-container-insights-observability-ecs/)
- [Monitoring Managed Instances (incl. agentless DCGM)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html) · [ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html) · [Free vended CloudWatch metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html)
- [ADOT/AMP for ECS application metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html) · [ECS trace data via ADOT](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/trace-data.html) · [ADOT ECS setup](https://aws-otel.github.io/docs/setup/ecs) · [AMP query onboarding](https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-onboard-query.html) · [CloudWatch agent Prometheus for ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights-Prometheus-Setup-ECS.html)
- [X-Ray daemon on ECS](https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-ecs.html) · [X-Ray SDK/daemon maintenance timeline](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html) · [X-Ray to OTel migration](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-migration.html)
- [Application Signals on ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-ECSMain.html) · [Sidecar strategy](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Sidecar.html) · [Daemon strategy](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Daemon.html) · [Support matrix](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-supportmatrix.html)
- [ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) · [Session Manager PrivateLink](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-privatelink.html)
- [ECS EventBridge events](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_cwe_events.html) · [Service action events](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service_events.html) · [Service event messages](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-event-messages.html) · [Container health checks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/healthcheck.html) · [ECS monitoring overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_monitoring.html) · [Recommended alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Best_Practice_Recommended_Alarms_AWS_Services.html#ECS)
- [ECS Anywhere](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html) · [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) · [CloudWatch cost guidance](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html)
- Structural framing borrowed with citation (not forked) from [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws) `skills/core-skills/aws-containers` and `aws-observability` @ commit 43e9d50.

---

*This skill is provided as sample code for educational and demonstration purposes only. Recommendations should be validated against current AWS documentation before acting on them. See the project's README and LICENSE for full terms.*
