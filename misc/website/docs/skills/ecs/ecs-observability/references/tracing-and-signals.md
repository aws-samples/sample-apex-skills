---
title: "ECS Observability — Tracing and Application Signals"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/tracing-and-signals.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-observability/references/tracing-and-signals.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/tracing-and-signals.md). Edit the source, not this page.
:::

# ECS Observability — Tracing and Application Signals

> **Part of:** [ecs-observability](../)
> **Purpose:** Deep guidance on distributed tracing stack selection for Amazon ECS — X-Ray legacy status, ADOT/OpenTelemetry as the recommended path, and CloudWatch Application Signals deployment strategies

**For metrics stack selection, see:** [metrics-stacks.md](metrics-stacks)
**For the per-capability launch-type matrix, see:** [launch-type-matrix.md](launch-type-matrix)

---

## Table of Contents

1. [X-Ray SDK/daemon: maintenance mode — steer new builds to OTel](#x-ray-sdkdaemon-maintenance-mode--steer-new-builds-to-otel)
2. [ADOT collector on ECS (the recommended tracing path)](#adot-collector-on-ecs-the-recommended-tracing-path)
3. [CloudWatch Application Signals on ECS](#cloudwatch-application-signals-on-ecs)
4. [Sidecar vs daemon placement by launch type](#sidecar-vs-daemon-placement-by-launch-type)

---

## X-Ray SDK/daemon: maintenance mode — steer new builds to OTel

> Facts verified 2026-07-10 against https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-ecs.html and https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html

- **On February 25, 2026, the AWS X-Ray SDKs and X-Ray daemon entered maintenance mode** (security fixes only). AWS explicitly recommends migrating to OpenTelemetry. That date has passed — treat the X-Ray SDK/daemon as legacy for all new tracing builds.
- **Scope the claim precisely:** the maintenance-mode timeline covers only the SDKs and daemon. It says nothing about the X-Ray backend service — the inference that the backend remains fully supported is consistent with the migration guide (which keeps X-Ray as the OTel trace destination), but the timeline page itself does not affirm backend status; state it as an inference, not a documented fact.
- Migration guide (includes "Using the OpenTelemetry collector on ECS"): https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-migration.html
- Existing-estate facts, for customers already running the daemon (documented for the EC2 launch type via daemon/sidecar and, per the matrix's X-Ray-daemon row, verify before extending to MI/EXTERNAL; the xray-daemon-ecs page does not enumerate Fargate — see the matrix): sidecar image `amazon/aws-xray-daemon` / `public.ecr.aws/xray/aws-xray-daemon`, UDP/TCP 2000; `bridge` mode needs container links + `AWS_XRAY_DAEMON_ADDRESS`; `awsvpc` reaches it on localhost; task role needs X-Ray write permissions. Advise these customers to plan an OTel migration, not to expand daemon usage.
- Migration gotchas worth flagging (per the aws/agent-toolkit-for-aws observability skill's tracing reference, aws/agent-toolkit-for-aws@43e9d50, `skills/core-skills/aws-observability/references/tracing.md:213-238` — verify against the X-Ray migration guide before relying on them): OTel span attributes become X-Ray *metadata* by default (list keys in `aws.xray.annotations` to keep searchable annotations), and centralized sampling requires the `awsproxy` extension in the collector.

## ADOT collector on ECS (the recommended tracing path)

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/trace-data.html and https://aws-otel.github.io/docs/setup/ecs

- ECS integrates with ADOT via a **sidecar collector container**: "Amazon ECS uses an AWS Distro for OpenTelemetry sidecar container to collect and route trace data to AWS X-Ray." The same sidecar can route metrics to CloudWatch or AMP. The ECS console can inject it via the task-definition "Use metric collection" option.
- Official image: `public.ecr.aws/aws-observability/aws-otel-collector`; built-in configs selected via `command` (e.g., `--config=/etc/ecs/ecs-amp.yaml`); custom config via SSM Parameter Store. Default pipelines cover X-Ray traces, StatsD, ECS container metrics, EMF, and Prometheus→AMP.
- Task IAM role for the X-Ray path: `xray:PutTraceSegments`, `xray:PutTelemetryRecords`, `xray:GetSampling*`, `ssm:GetParameters`, plus CloudWatch Logs permissions for collector logs.
- **Launch-type scope:** documented for Fargate + EC2 only; EXTERNAL explicitly unsupported; MI not documented as of 2026-07-10 — see the **ADOT sidecar row of [launch-type-matrix.md](launch-type-matrix)** for the source quote and URL; verify the live doc before advising MI.
- Project health: the ADOT collector is actively maintained (no maintenance-mode notice as of 2026-07-09; note planned removal of the `datadog`/`logzio`/`sapm`/`signalfx` exporters from the distro — per https://github.com/aws-observability/aws-otel-collector).

## CloudWatch Application Signals on ECS

> Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-ECSMain.html and the sidecar/daemon subpages

Application Signals (APM-style service maps, SLOs, RED metrics via ADOT SDK auto-instrumentation) works on ECS, but set expectations correctly:

- **Custom setup only — no autodiscovery on ECS.** "Application Signals doesn't autodiscover the names of your services or the hosts or clusters they run on"; service/environment names are wired manually through environment variables. Compare EKS, where enablement is far more automated — don't let EKS experience inflate ECS expectations.
- Two deployment strategies for the CloudWatch agent:

| Strategy | Launch types (documented) | Constraints | Source |
|---|---|---|---|
| **Sidecar** (agent container per task definition) | EC2, Fargate | **Requires `awsvpc` network mode**; per-task resource overhead | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Sidecar.html |
| **Daemon** (one agent service per cluster) | EC2 (the only documented launch type; Fargate is **explicitly unsupported**; MI/EXTERNAL undocumented — verify, per the matrix) | With `awsvpc`/`bridge` app networking you must wire instance private IPs into app env vars | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-ECS-Daemon.html |

- Managed Instances and EXTERNAL are not documented for either strategy — don't claim them. (Note also the sidecar's `awsvpc` requirement structurally rules out ECS Anywhere, which supports only `bridge`/`host`/`none`.)
- Language support (per https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-supportmatrix.html): ADOT SDK auto-instrumentation for Java, Python, .NET, Node.js (CJS recommended; ESM experimental); PHP/Ruby/Go go through vanilla OTel zero-code + Transaction Search instead. Platforms listed as supported and tested: Amazon EKS, native Kubernetes, Amazon ECS, Amazon EC2.
- Worked per-language ECS recipes (init-container SDK injection + agent sidecar + OTEL env vars) exist in aws/agent-toolkit-for-aws@43e9d50, `skills/core-skills/aws-observability/references/appsignals-guides/ecs-*.md` — usable as implementation references; pin image tags rather than copying their `:latest` usage.

## Sidecar vs daemon placement by launch type

The general placement rule (grounded in https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html — on Fargate, "any additional software needed must be installed outside of the task" is impossible host-side — and https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-ecs.html):

| Launch type | Collector placement |
|---|---|
| Fargate | **Sidecar only** — no host access, no daemon scheduling |
| EC2 | Sidecar (per-task isolation, per-task IAM) or daemon-scheduled service (one collector per instance, lower aggregate overhead) |
| Managed Instances | **Neither placement is documented for MI as of 2026-07-10** — the ADOT integration page enumerates Fargate + EC2 only (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-prometheus.html), and ECS "Managed Daemons" exist as a scheduling construct without documented observability-collector support. Per the matrix's ADOT row: verify against the live doc before advising either pattern on MI — do not present the sidecar as safe-by-default there |
| EXTERNAL | ADOT integration unsupported (per the ECS AMP page); the classic X-Ray daemon would additionally need outbound reachability to X-Ray endpoints from on-prem |

Note on terminology inside this skill: "daemon" here means the ECS **daemon scheduling strategy** (one task per container instance) or the legacy X-Ray daemon process — both are ECS/X-Ray terms of art, unrelated to Kubernetes.
