---
title: "Module: Observability"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/observability.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/observability.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/observability.md). Edit the source, not this page.
:::

# Module: Observability

> **Part of:** [ecs-recon](../)
> **Purpose:** Discover monitoring, logging, and telemetry configuration for ECS clusters and services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Container Insights Setting](#1-container-insights-setting)
  - [Log Configuration per Container](#2-log-configuration-per-container)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **Service name(s) required:** Yes (one or more services to inspect)
- **Active task definition required:** Yes (resolved from each service's `taskDefinition` field)
- **AWS APIs used:**
  - `ecs:DescribeClusters` — cluster-level Container Insights setting
  - `ecs:DescribeTaskDefinition` — per-container log configuration from the active task definition
- **CLI commands:** `aws ecs describe-clusters`, `aws ecs describe-task-definition`
- **IAM permissions:** Read-only (`ecs:DescribeClusters`, `ecs:DescribeTaskDefinition`)

---

## Detection Strategy

Run detections in this order to build the observability picture from cluster level down to container level:

```
1. Container Insights Setting  -> Get cluster-level monitoring configuration
2. Log Configuration           -> Extract log driver and options per container from the active task definition
```

**Why this order matters:**
- Container Insights is a cluster-wide setting and provides the monitoring baseline — it tells you whether CloudWatch metrics and (optionally) enhanced observability are active
- Log configuration is per-container within a task definition — it reveals how each container ships logs and where they go
- Together, these two layers give a complete picture of what telemetry is available before making changes

**Key decision logic:**
- Container Insights: look at the cluster's `settings` array for a setting with `name: "containerInsights"` — the `value` determines the state
- Log configuration: each container definition's `logConfiguration` field holds the driver and its options
- If `logConfiguration` is absent or null → report the container as `not_configured`
- If `logConfiguration` is present → report the `logDriver` value as-is, regardless of whether the configuration is valid or complete

---

## Detection Commands

### 1. Container Insights Setting

Retrieve the Container Insights setting from the cluster. This is a cluster-level toggle that controls whether CloudWatch collects ECS metrics automatically.

**CLI:**
```bash
aws ecs describe-clusters \
  --clusters <cluster-name> \
  --include SETTINGS \
  --query 'clusters[0].settings'
```

**Example output (Container Insights enabled):**
```json
[
  {
    "name": "containerInsights",
    "value": "enabled"
  }
]
```

**Example output (Container Insights enhanced):**
```json
[
  {
    "name": "containerInsights",
    "value": "enhanced"
  }
]
```

**Example output (Container Insights disabled or not present):**
```json
[]
```

**Interpret the result:**
- Setting present with `value: "enabled"` → report `container_insights: "enabled"` (standard CloudWatch metrics)
- Setting present with `value: "enhanced"` → report `container_insights: "enhanced"` (enhanced observability: task- and container-level metric granularity plus log correlation)
- Setting absent from the array, or the array is empty → report `container_insights: "disabled"`
- Setting present with `value: "disabled"` → report `container_insights: "disabled"`

### 2. Log Configuration per Container

For each service, retrieve the active task definition and extract the `logConfiguration` block from each container definition. This reveals what log driver is in use and where logs are shipped.

**Step 2a — Get the active task definition ARN from the service:**

If not already known from a prior module (e.g., task-definitions), resolve the active task definition ARN:

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].taskDefinition'
```

**Example output:**
```
"arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:7"
```

**Step 2b — Describe the task definition and extract log configuration:**

Do NOT pull the full `logConfiguration` object. Non-awslogs drivers (especially `awsfirelens`) can carry credentials such as API keys in their `options` values. Scope the query to the `logDriver`, the awslogs-specific options, and the option **keys** only:

**CLI:**
```bash
aws ecs describe-task-definition \
  --task-definition <task-definition-arn> \
  --query 'taskDefinition.containerDefinitions[].{name: name, logDriver: logConfiguration.logDriver, awslogsGroup: logConfiguration.options."awslogs-group", awslogsRegion: logConfiguration.options."awslogs-region", awslogsStreamPrefix: logConfiguration.options."awslogs-stream-prefix", optionKeys: keys(not_null(logConfiguration.options, `{}`))}'
```

**Example output (awslogs driver):**
```json
[
  {
    "name": "web",
    "logDriver": "awslogs",
    "awslogsGroup": "/ecs/my-app",
    "awslogsRegion": "us-east-1",
    "awslogsStreamPrefix": "web",
    "optionKeys": ["awslogs-group", "awslogs-region", "awslogs-stream-prefix"]
  },
  {
    "name": "sidecar",
    "logDriver": "awslogs",
    "awslogsGroup": "/ecs/my-app-sidecar",
    "awslogsRegion": "us-east-1",
    "awslogsStreamPrefix": "sidecar",
    "optionKeys": ["awslogs-group", "awslogs-region", "awslogs-stream-prefix"]
  }
]
```

**Example output (awsfirelens driver — note option keys only, no values):**
```json
[
  {
    "name": "app",
    "logDriver": "awsfirelens",
    "awslogsGroup": null,
    "awslogsRegion": null,
    "awslogsStreamPrefix": null,
    "optionKeys": ["Name", "Host", "TLS", "apikey", "dd_service", "dd_source", "provider"]
  },
  {
    "name": "log-router",
    "logDriver": "awslogs",
    "awslogsGroup": "/ecs/firelens",
    "awslogsRegion": "us-east-1",
    "awslogsStreamPrefix": "firelens",
    "optionKeys": ["awslogs-group", "awslogs-region", "awslogs-stream-prefix"]
  }
]
```

**Example output (no log configuration):**
```json
[
  {
    "name": "worker",
    "logDriver": null,
    "awslogsGroup": null,
    "awslogsRegion": null,
    "awslogsStreamPrefix": null,
    "optionKeys": []
  }
]
```

**Interpret the result:**
- `logDriver` is present → report the driver name as-is (e.g., `awslogs`, `awsfirelens`, `fluentd`, `splunk`, `json-file`)
- `logDriver` is `null` (logConfiguration absent) → report `log_driver: "not_configured"`
- For `awslogs` driver, extract these options:
  - `awslogs-group` → the CloudWatch Logs log group name
  - `awslogs-region` → the AWS region for the log group
  - `awslogs-stream-prefix` → the stream prefix for log streams
- For other drivers (`awsfirelens`, `fluentd`, `splunk`, etc.), report the driver name but do not attempt to parse driver-specific options into the standard awslogs fields — leave `awslogs_group`, `awslogs_region`, and `awslogs_stream_prefix` as `null`
- **Never reproduce non-awslogs `logConfiguration.options` values in output or the report — report the driver name and option keys only.** Option values for FireLens and other third-party drivers can contain API keys and other credentials.

---

## Output Schema

```yaml
observability:
  cluster:
    name: string
    container_insights: string    # "enabled" | "enhanced" | "disabled"
  services:
    - service_name: string
      error: string | null                        # Set when a describe call failed for this service; containers may be empty
      containers:
        - container_name: string
          log_driver: string | "not_configured"   # awslogs | awsfirelens | fluentd | splunk | json-file | etc.
          awslogs_group: string | null            # Present when log_driver is "awslogs"
          awslogs_region: string | null           # Present when log_driver is "awslogs"
          awslogs_stream_prefix: string | null    # Present when log_driver is "awslogs"
```

**Field details:**

| Field | Type | Description |
|-------|------|-------------|
| `cluster.name` | string | The cluster name |
| `cluster.container_insights` | string | One of `"enabled"`, `"enhanced"`, or `"disabled"` |
| `services[].service_name` | string | The ECS service name |
| `services[].error` | string \| null | `null` on success; the failing API call and error code when a describe call failed for this service |
| `services[].containers[].container_name` | string | The container name from the task definition |
| `services[].containers[].log_driver` | string | The declared log driver, or `"not_configured"` if absent |
| `services[].containers[].awslogs_group` | string \| null | CloudWatch log group (only for `awslogs` driver) |
| `services[].containers[].awslogs_region` | string \| null | AWS region for the log group (only for `awslogs` driver) |
| `services[].containers[].awslogs_stream_prefix` | string \| null | Stream prefix (only for `awslogs` driver) |

---

## Edge Cases

Handle these scenarios to ensure accurate observability reporting.

### No log configuration on a container

A container definition may have `logConfiguration` set to `null` or the field may be absent entirely. This happens when the container uses Docker's default logging (typically `json-file` on the container instance) without explicit ECS configuration.

**How to handle:**
- Report `log_driver: "not_configured"` for that container
- Set `awslogs_group`, `awslogs_region`, and `awslogs_stream_prefix` to `null`
- Do NOT infer or guess a log driver — only report what is explicitly declared

**Example output:**
```yaml
containers:
  - container_name: worker
    log_driver: "not_configured"
    awslogs_group: null
    awslogs_region: null
    awslogs_stream_prefix: null
```

### awsfirelens driver

The `awsfirelens` log driver routes logs through a Firelens (Fluent Bit or Fluentd) sidecar container. Its options are entirely different from `awslogs` — they configure the destination (Datadog, Splunk, S3, etc.) rather than CloudWatch.

**How to handle:**
- Report `log_driver: "awsfirelens"` — report the driver name exactly as declared
- Set `awslogs_group`, `awslogs_region`, and `awslogs_stream_prefix` to `null` (these fields are specific to the `awslogs` driver)
- Do NOT attempt to parse Firelens-specific options into the awslogs fields
- Note: the Firelens sidecar container itself typically uses `awslogs` for its own logs — report that container separately with its actual log config

**Example output:**
```yaml
containers:
  - container_name: app
    log_driver: "awsfirelens"
    awslogs_group: null
    awslogs_region: null
    awslogs_stream_prefix: null
  - container_name: log-router
    log_driver: "awslogs"
    awslogs_group: "/ecs/firelens"
    awslogs_region: "us-east-1"
    awslogs_stream_prefix: "firelens"
```

### Container Insights — enhanced vs basic

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html

ECS Container Insights has two modes:
- **Basic (`enabled`)** — collects CloudWatch metrics at the cluster, service, and task level (CPU, memory, network, storage)
- **Enhanced (`enhanced`)** — includes everything in basic mode plus additional performance metrics at task and container granularity, with log correlation for faster problem isolation. Enhanced observability does NOT collect traces; CloudWatch Application Signals is a separate feature that requires its own instrumentation.

**How to handle:**
- Check the `value` field of the `containerInsights` setting exactly:
  - `"enabled"` → report `"enabled"` (basic mode)
  - `"enhanced"` → report `"enhanced"` (enhanced observability)
- Do NOT conflate the two modes — they have different cost and metric coverage implications
- If the setting is absent or set to `"disabled"` → report `"disabled"`

### Invalid or incomplete log configuration still reported as declared

A container definition may declare a `logConfiguration` with a `logDriver` value but have missing or invalid options (e.g., `awslogs` driver without an `awslogs-group` option, or an unrecognized driver name).

**How to handle:**
- Report the `logDriver` value exactly as declared — do NOT validate whether the options are complete or correct
- If `awslogs` driver is declared but `awslogs-group` is missing from options → report `awslogs_group: null`
- If `awslogs` driver is declared but `awslogs-region` is missing from options → report `awslogs_region: null`
- The skill discovers and reports — it does not validate or audit

**Example (incomplete awslogs config):**
```yaml
containers:
  - container_name: broken-logger
    log_driver: "awslogs"
    awslogs_group: null        # Missing from options — reported as null
    awslogs_region: "us-east-1"
    awslogs_stream_prefix: null  # Missing from options — reported as null
```

**Example (unrecognized driver):**
```yaml
containers:
  - container_name: custom-app
    log_driver: "gelf"         # Uncommon but valid Docker log driver
    awslogs_group: null
    awslogs_region: null
    awslogs_stream_prefix: null
```

### Describe request fails (access denied or resource not found)

If `ecs:DescribeClusters` or `ecs:DescribeTaskDefinition` returns an error:

**How to handle:**
- Record the error on the affected service's entry (set `error` to the failing API call and error code) and continue with the remaining services
- Do NOT present the errored service's partial data as complete — report `containers: []` for it
- Use module-level `unavailable: true` ONLY when the module cannot produce any data at all (e.g., `ecs:DescribeClusters` fails and every per-service call also fails)

**Example — cluster-level query succeeds but one task definition fails:**

```yaml
observability:
  cluster:
    name: prod-cluster
    container_insights: "enabled"
  services:
    - service_name: healthy-service
      error: null
      containers:
        - container_name: web
          log_driver: "awslogs"
          awslogs_group: "/ecs/healthy"
          awslogs_region: "us-east-1"
          awslogs_stream_prefix: "web"
    - service_name: inaccessible-service
      error: "ecs:DescribeTaskDefinition failed: AccessDeniedException"
      containers: []
```

**Example — total failure only:**

```yaml
observability:
  unavailable: true
  reason: "ecs:DescribeClusters failed for 'prod-cluster': AccessDeniedException"
```

---

## Sources

- Container Insights for ECS (basic vs enhanced observability, metric coverage): https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html
- Task definition `logConfiguration` parameter: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html
- awslogs log driver options: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html
- FireLens custom log routing: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html
