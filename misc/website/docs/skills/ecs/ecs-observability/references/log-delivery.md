---
title: "ECS Observability — Log Delivery Architecture"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/log-delivery.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-observability/references/log-delivery.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-observability/references/log-delivery.md). Edit the source, not this page.
:::

# ECS Observability — Log Delivery Architecture

> **Part of:** [ecs-observability](../)
> **Purpose:** Deep guidance on awslogs delivery modes (blocking vs non-blocking), buffer sizing, FireLens/Fluent Bit routing, and high-throughput logging patterns for Amazon ECS

**For the per-capability launch-type matrix, see:** [launch-type-matrix.md](launch-type-matrix)

---

## Table of Contents

1. [The delivery-mode decision gate](#the-delivery-mode-decision-gate)
2. [Buffer sizing for non-blocking mode](#buffer-sizing-for-non-blocking-mode)
3. [awslogs configuration essentials](#awslogs-configuration-essentials)
4. [FireLens (Fluent Bit) routing](#firelens-fluent-bit-routing)
5. [High-throughput logging](#high-throughput-logging)
6. [Choosing awslogs vs FireLens](#choosing-awslogs-vs-firelens)

---

## The delivery-mode decision gate

> ⚠️ **Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html**

**On June 25, 2025, Amazon ECS changed the default log driver delivery mode from `blocking` to `non-blocking`** "to prioritize task availability over logging." When neither the container definition `mode` nor the `defaultLogDriverMode` account setting says otherwise, the effective mode is `non-blocking` (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html, "Default log driver mode").

Why this is a compliance-grade decision and not a tuning knob:

- **Non-blocking mode can silently lose logs.** Logs flow through an in-memory buffer sized by `max-buffer-size`; per the API reference, "When the buffer fills up, further logs cannot be stored. Logs that cannot be stored are lost." There is **no Docker daemon log statement and no metric emitted when logs are dropped** — the loss is silent (per https://aws.amazon.com/blogs/containers/preventing-log-loss-with-non-blocking-mode-in-the-awslogs-container-log-driver/).
- **Blocking mode can take the application down instead.** If log flow to the destination is interrupted, writes to stdout/stderr block, which "may cause the application to become unresponsive and lead to container healthcheck failure" (per https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html).
- The `mode` / `max-buffer-size` options apply to **all supported log drivers**, not only awslogs (same API reference).

So the customer is choosing between two failure modes:

| Mode | On log-pipeline backpressure | Fails toward | Choose when |
|---|---|---|---|
| `non-blocking` (default since 2025-06-25) | Buffer fills → newest logs silently dropped | **Availability** | User-facing services where uptime beats log completeness; loss tolerance documented |
| `blocking` (pre-2025 default) | stdout/stderr writes stall → app may hang, health checks fail, task may be replaced | **Log completeness** | Audit, financial, security, or regulated logs where a dropped record is a compliance event |

How to set it:

- Per container: `logConfiguration.options.mode: "blocking"` in the container definition.
- Account-wide: `aws ecs put-account-setting-default --name defaultLogDriverMode --value "blocking"` (per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html).
- Audit the effective default before advising — the account setting may already have been changed: `aws ecs list-account-settings --name defaultLogDriverMode --effective-settings`.

**Advisory rule:** never let a compliance-sensitive customer discover this default by accident. If they need both completeness and availability, the answer is usually FireLens with filesystem buffering (below), not either awslogs mode.

## Buffer sizing for non-blocking mode

> ⚠️ **Point-in-time benchmark data — verified 2026-07-09 against https://aws.amazon.com/blogs/containers/preventing-log-loss-with-non-blocking-mode-in-the-awslogs-container-log-driver/ (blog published Aug 3, 2023, when the Docker-level default buffer was 1 MB). The current ECS `max-buffer-size` default is `10m` (10 MiB) per https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html.**

AWS's own benchmarks (~17,000 test runs) found:

| Log throughput | Buffer needed for no observed loss |
|---|---|
| ≤ 2 MB/s | ≥ 4 MiB |
| ≤ 5 MB/s | ≥ 25 MiB |
| ≥ 6 MB/s | Unreliable at any tested buffer size |
| Cross-Region delivery | Unreliable even at 40+ MiB |

Practical guidance derived from that blog:

- **Recommend ~25 MiB `max-buffer-size` for in-Region CloudWatch logging** when the customer stays on non-blocking mode and cares about loss.
- The 10 MiB default is not sized for high-throughput containers — treat any service logging multiple MB/s as a buffer-sizing conversation.
- **Do not architect cross-Region log delivery through the awslogs driver** — route in-Region and replicate at the destination instead.
- Loss detection has no built-in signal. The only practical watch is comparing CloudWatch `IncomingLogEvents`/incoming bytes against expected application volume (framing borrowed from aws/agent-toolkit-for-aws@43e9d50, `references/ecs-logging-and-firelens.md:121` — cite, don't fork).

## awslogs configuration essentials

Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html:

- IAM: `logs:CreateLogStream` and `logs:PutLogEvents`, normally on the **task execution role** (`ecsTaskExecutionRole`).
- `awslogs-stream-prefix` is **required on Fargate**, optional on the EC2 launch type, and required for logs to appear in the ECS console Logs pane.
- EC2 launch type: requires container agent ≥ 1.9.0; custom AMIs must register the driver in `ECS_AVAILABLE_LOGGING_DRIVERS`.
- Supported log drivers by launch type: **Fargate** = `awslogs`, `splunk`, `awsfirelens`; **EC2** = `awslogs`, `fluentd`, `gelf`, `json-file`, `journald`, `syslog`, `splunk`, `awsfirelens`. The extra Docker drivers are documented for EC2 only — do not extend them to Managed Instances or ECS Anywhere without verification.
- Tasks in private subnets with no internet path need a CloudWatch Logs (`logs`) interface VPC endpoint for delivery.

## FireLens (Fluent Bit) routing

Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html:

- FireLens (`awsfirelens` log driver) routes container stdout/stderr to AWS services or AWS Partner destinations via Fluent Bit or Fluentd; AWS publishes the `aws-for-fluent-bit` image. Documented destinations with first-class options: Firehose, Kinesis Data Streams, OpenSearch Service, S3, plus partner outputs (Splunk, Datadog, etc.) via Fluent Bit output plugins (per https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html).
- **Launch-type scope: FireLens is documented for Linux tasks on Fargate and on the EC2 launch type. Windows containers do not support FireLens. Managed Instances and ECS Anywhere (EXTERNAL) support is not stated in the FireLens documentation — verify against current AWS docs before advising FireLens on those launch types.**
- FireLens adds ECS metadata (`ecs_cluster`, `ecs_task_arn`, `ecs_task_definition`) to records by default (disable with `enable-ecs-log-metadata: false`); ECS auto-orders the router container to start before and stop after app containers.
- Security: the router listens on TCP 24224 — do not allow inbound on that port in task or instance security groups.
- IAM split that trips people up: **destination permissions (e.g., `firehose:PutRecordBatch`) go on the task role** — Fluent Bit runs as the task; custom config pulled from S3 needs `s3:GetObject` on the **task execution role**. Fluent Bit can run as non-root with agent ≥ 1.96.0 and ECS-optimized AMI ≥ v20250716.
- Operational rules worth restating (framing per aws/agent-toolkit-for-aws@43e9d50, `references/ecs-logging-and-firelens.md:240-248` — verified consistent with the AWS FireLens docs): the log-router container should be essential (otherwise app logs silently stop while the task keeps running), and the router's own logs should use `awslogs`, never `awsfirelens` (self-routing can prevent task start).

## High-throughput logging

Facts verified 2026-07-09 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/firelens-docker-buffer-limit.html:

- Fluent Bit defaults to **memory buffering** (`storage.type memory`); when `Mem_Buf_Limit` is exceeded the input pauses and **new records are lost**. For production pipelines where loss matters, AWS recommends **filesystem buffering**: `storage.path`, `storage.max_chunks_up` (default 128 chunks can consume 500 MB+), `storage.total_limit_size` per output (oldest records dropped when full), `storage.backlog.flush_on_shutdown On`, `threaded true`, `Grace 120`.
- `log-driver-buffer-limit` controls the Docker→Fluent Bit buffer in log **lines** (default 1,048,576; max 536,870,911); valid only with `awsfirelens`; supported on the EC2 launch type and on Fargate platform version ≥ 1.4.0.
- Escape hatches documented on the same page: tail-input file-based logging (bypass the Docker log driver entirely), logging directly to FireLens over the Fluent Forward protocol, and multi-destination outputs for redundancy.
- Foundational best practice regardless of stack: applications write to stdout/stderr so log handling stays an infrastructure decision, not a code change (per https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/application.html).

## Choosing awslogs vs FireLens

| Criterion | awslogs | FireLens (Fluent Bit) |
|---|---|---|
| Destination | CloudWatch Logs only | CloudWatch, Firehose, Kinesis, OpenSearch, S3, third-party (Splunk, Datadog, SIEMs) |
| Filtering / enrichment / multiline parsing | Driver options only | Full Fluent Bit pipeline |
| Loss control | `mode` + in-memory `max-buffer-size` only | Filesystem buffering, per-output limits, multi-destination |
| Cost of operation | None extra | Sidecar CPU/memory per task + buffer engineering |
| Launch types (documented) | EC2, Fargate, Managed Instances, EXTERNAL | EC2 (Linux), Fargate (Linux); MI/EXTERNAL undocumented — verify |
| Compliance posture | Choose blocking (availability risk) or non-blocking (silent-loss risk) | Filesystem buffering gives loss resistance without blocking the app |

Rule of thumb: single destination + CloudWatch-centric + modest throughput → awslogs with an explicit, documented `mode` decision. Third-party destination, transformation, PII filtering, multi-destination, or "we cannot lose logs AND cannot block the app" → FireLens with filesystem buffering.
