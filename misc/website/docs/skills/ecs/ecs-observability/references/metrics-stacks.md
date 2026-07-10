---
title: "ECS Observability — Metrics Stack Selection"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/metrics-stacks.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-observability/references/metrics-stacks.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/metrics-stacks.md). Edit the source, not this page.
:::

# ECS Observability — Metrics Stack Selection

> **Part of:** [ecs-observability](../)
> **Purpose:** Deep guidance on Container Insights (standard vs enhanced), free vended metrics, ADOT + Amazon Managed Service for Prometheus (AMP) + Amazon Managed Grafana (AMG), and GPU telemetry scoping for Amazon ECS

**For traces and Application Signals, see:** [tracing-and-signals.md](tracing-and-signals)
**For the per-capability launch-type matrix, see:** [launch-type-matrix.md](launch-type-matrix)

---

## Table of Contents

1. [Free vended CloudWatch metrics (the floor)](#free-vended-cloudwatch-metrics-the-floor)
2. [Container Insights: standard vs enhanced](#container-insights-standard-vs-enhanced)
3. [GPU telemetry — the launch-type trap](#gpu-telemetry--the-launch-type-trap)
4. [Instance-level metrics](#instance-level-metrics)
5. [Prometheus paths: ADOT+AMP+AMG vs CloudWatch agent](#prometheus-paths-adotampamg-vs-cloudwatch-agent)
6. [Cost posture](#cost-posture)

---

## Free vended CloudWatch metrics (the floor)

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html

Every ECS customer gets these before any stack decision:

- 1-minute periods, 2-week retention: cluster and service `CPUUtilization` / `MemoryUtilization`; `CPUReservation` / `MemoryReservation` / `GPUReservation` for EC2-hosted clusters; EBS filesystem utilization (the free-metric pages state only "when there is an EBS volume attached" with no version gate; the Fargate platform version ≥ 1.4.0 / EC2 agent ≥ 1.79.0 gate is documented on the Container Insights metrics table — assuming it also gates the free metric is an inference, not documented; see the tier table below and https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-metrics-ECS.html).
- Fargate services get CPU/memory utilization automatically; EC2-hosted needs container agent ≥ 1.4.0 (Linux) / ≥ 1.0.0 (Windows) and `ecs:StartTelemetrySession` on the instance role; disable with `ECS_DISABLE_METRICS=true`.
- On ECS Anywhere (EXTERNAL), task/container metrics flow through the `ecs-t-*` regional endpoints, which must be reachable from the on-prem network (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html).
- AWS-recommended alarms for ECS (with and without Container Insights): https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Best_Practice_Recommended_Alarms_AWS_Services.html#ECS

## Container Insights: standard vs enhanced

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-cluster.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html, and https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html

Mechanics common to both tiers:

- Metrics arrive as performance log events (embedded metric format) in `/aws/ecs/containerinsights/<cluster>/performance`; aggregated metrics live in the `ECS/ContainerInsights` CloudWatch metric namespace.
- Enablement: cluster setting `containerInsights` = `enabled` (standard) or `enhanced`, settable per cluster (`update-cluster-settings`) or account-wide (`put-account-setting-default`).
- EC2 launch type requires ECS agent ≥ 1.29 on the instance.
- Customer-managed KMS on the performance log group requires key-policy work; CloudWatch Logs supports only symmetric KMS keys (per https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html).

| | Standard (`enabled`) | Enhanced (`enhanced`) |
|---|---|---|
| Granularity | Task / service / cluster | Adds **container-level** metrics and per-TaskId dimensions |
| Metric families | CPU/memory utilized+reserved, network rx/tx, storage r/w, ephemeral storage (Fargate PV ≥ 1.4.0), EBS filesystem (Fargate PV ≥ 1.4.0 or EC2 agent ≥ 1.79.0), task/service/deployment counts, RestartCount (restart-policy containers) | Adds ContainerCpu*/ContainerMemory*/ContainerNetwork*/ContainerStorage*, TaskCpuUtilization / TaskMemoryUtilization / TaskEphemeralStorageUtilization, UnHealthyContainerHealthStatus (health-check containers), Managed Daemon metrics (`ServiceName = daemon:<name>`), GPU/DCGM metrics (MI only — next section) |
| Launch types (documented) | EC2 (agent ≥ 1.29), Fargate, Managed Instances | Fargate, Managed Instances, EC2 (agent ≥ 1.29 applies to both tiers; the enhanced *tier* was released Dec 2024). EXTERNAL is not listed for either tier — don't claim it |
| AWS's stance | Available | **Recommended** — AWS positions enhanced as the default choice ("reducing the mean time to resolution", per the deploy page) |
| Cost signal | Charged as CloudWatch custom metrics | More metric series (container-level + per-TaskId cardinality) — see [Cost posture](#cost-posture) below and link https://aws.amazon.com/cloudwatch/pricing/; never quote prices |

Release date for enhanced observability: December 2024 (What's New: https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-cloudwatch-container-insights-observability-ecs/).

Container Insights can also be produced via an ADOT collector instead of the ECS-native path — relevant when a customer already standardizes on OTel pipelines: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-adot.html. Launch-type scope: that setup page does not enumerate launch types (its console walkthrough is launch-type-agnostic), but the ADOT-on-ECS integration itself is documented for Fargate + EC2 only — see the ADOT row of [launch-type-matrix.md](launch-type-matrix); support beyond Fargate/EC2 is not documented as of 2026-07-10 — verify before advising.

## GPU telemetry — the launch-type trap

This is the highest-risk scope-bleed in this domain. The precise facts (verified 2026-07-09):

- **Agentless GPU/DCGM metrics are Managed Instances-ONLY.** "For Amazon ECS Managed Instances running NVIDIA GPU-enabled Amazon EC2 instance types, Container Insights with enhanced observability collects GPU metrics from NVIDIA Data Center GPU Manager (DCGM) at the container, task, and instance levels. GPU metrics are not collected with basic Container Insights ... No additional agent installation is required." (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)
- Every GPU metric in the enhanced-observability table (`ContainerGPUUtilization`, `ContainerGPUMemory{Utilization,Total,Used}`, `ContainerGPUPowerDraw`, `ContainerGPUTemperature`, `ContainerGPURestartAppXidCount`, `TaskGPU*`, `InstanceGPULimit`, `InstanceGPUUsageTotal`) is documented as "Available only for Amazon ECS Managed Instances running NVIDIA GPU-enabled Amazon EC2 instance types" (per https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html).
- **The EC2 launch type gets GPU reservation only** as a free vended metric ("For tasks hosted on EC2 instances, Amazon ECS provides CPU, memory, and GPU reservation metrics", per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html). GPU *utilization* telemetry on the EC2 launch type requires the customer to run their own DCGM exporter / CloudWatch agent tooling.
- Fargate has no GPU tasks, so the question is moot there.

Advisory consequence: a customer who wants agentless GPU utilization/temperature/power telemetry has exactly one path — **Managed Instances + Container Insights enhanced**. Never present this as available on the EC2 launch type, and never present EC2's GPU reservation metric as utilization data.

## Instance-level metrics

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-instancelevel.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html

- **EC2 launch type:** instance-level Container Insights metrics (`instance_cpu_*`, `instance_memory_*`, `instance_filesystem_utilization`, `instance_network_total_bytes`, `instance_number_of_running_tasks`) require **deploying the CloudWatch agent as a daemon service** — they are not agentless.
- **Managed Instances:** each instance has two EBS volumes (root/OS + data); with Container Insights enabled, ECS auto-publishes OS and data filesystem utilization — no agent to install (the AMI is AWS-owned; you cannot bake agents into it, and there is no SSH). EC2 basic (5-min) vs detailed (1-min, paid) monitoring is toggled on the MI capacity provider (requires `ec2:MonitorInstances`-class permission).
- **Fargate:** no host access, so instance-level collection is not applicable — task-level metrics are the deepest native layer.
- **EXTERNAL:** instance-level Container Insights collection is not documented — don't claim it.

## Prometheus paths: ADOT+AMP+AMG vs CloudWatch agent

Two documented ways to get Prometheus-format metrics off ECS (facts verified 2026-07-09):

**Path A — ADOT sidecar → AMP → Amazon Managed Grafana** (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html):

- The ADOT collector runs as a **sidecar container per task** (`public.ecr.aws/aws-observability/aws-otel-collector`), remote-writing task-level CPU/memory/network/storage and custom app metrics to an AMP workspace (`AWS_PROMETHEUS_ENDPOINT`, built-in `ecs-amp.yaml` config; custom config via SSM Parameter Store). The ECS console can inject the sidecar ("Use metric collection").
- App exposes `/metrics` via Prometheus client libraries or uses the OTel SDK.
- **Launch-type scope:** Fargate + EC2 only; **EXTERNAL explicitly unsupported**; MI not documented as of 2026-07-10 — the source quote and URL live in the **ADOT sidecar row of [launch-type-matrix.md](launch-type-matrix)** (single source of truth); verify the live doc before advising MI.
- Task role needs the collector's destination permissions (CloudWatch logs for collector logging, `cloudwatch:PutMetricData` or AMP remote-write per path).
- Querying AMP needs Grafana or the API; Amazon Managed Grafana connects via the Prometheus data source with SigV4, and a dedicated AMP data source exists from AMG version 12 (per https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-onboard-query.html and https://docs.aws.amazon.com/grafana/latest/userguide/amazon-prometheus-data-source.html).

**Path B — CloudWatch agent with Prometheus support** (per https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights-Prometheus-Setup-ECS.html):

- Discovers ECS scrape targets via docker-label / task-definition-based service discovery, writes to log group `/aws/ecs/containerinsights/<cluster>/prometheus`, publishes to the `ECS/ContainerInsights/Prometheus` CloudWatch metric namespace. Keeps everything in CloudWatch.

**Decision cue:** choose Path A when the customer wants PromQL/Grafana portability, existing Grafana dashboards, or multi-cluster/hybrid Prometheus consolidation. Choose Path B when they want Prometheus-format app metrics but a single-pane CloudWatch experience (single vendor, single IAM story, no AMP/AMG bill).

## Cost posture

Do not quote Container Insights prices — link and let the customer check live:

- Container Insights metrics are charged as CloudWatch custom metrics for the standard tier (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html). The pricing model for the enhanced tier on ECS is described inconsistently across AWS pages (the per-observation model is documented in an EKS context; the ECS What's New says "flat metric pricing") — **always defer to https://aws.amazon.com/cloudwatch/pricing/** rather than asserting a model.
- Cost levers to raise with the customer: enhanced tier adds container-level cardinality (more series), high-cardinality Prometheus scrape configs, and log-group retention on the performance log group. CloudWatch cost guidance: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html
