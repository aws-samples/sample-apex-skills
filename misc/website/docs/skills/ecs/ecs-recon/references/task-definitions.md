---
title: "Module: Task Definitions"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/task-definitions.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/task-definitions.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/task-definitions.md). Edit the source, not this page.
:::

# Module: Task Definitions

> **Part of:** [ecs-recon](../)
> **Purpose:** Discover task definition details behind services — resource allocation, containers, and images in use

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Get Active Task Definition ARN](#1-get-active-task-definition-arn)
  - [Describe Task Definition](#2-describe-task-definition)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Prerequisites

- **Service name(s) required:** Yes (one or more ECS service names within a cluster)
- **Cluster name required:** Yes (to scope the service lookup)
- **APIs used:** `ecs:DescribeServices`, `ecs:DescribeTaskDefinition`
- **CLI commands:** `aws ecs describe-services`, `aws ecs describe-task-definition`
- **IAM permissions:** `ecs:DescribeServices`, `ecs:DescribeTaskDefinition` (read-only)

---

## Detection Strategy

Run detections in this order to build up from service to task definition details:

```
1. Get active task definition ARN  -> DescribeServices returns the taskDefinition field
2. Describe task definition        -> DescribeTaskDefinition returns full resource allocation and container details
3. Extract and normalize           -> Pull family, revision, CPU/memory, network mode, containers
```

**Why this order matters:**
- The active task definition ARN is only available from the service description — you cannot guess the current revision
- Describing the task definition in a separate call gives you the full container definitions, resource allocations, and configuration
- Normalizing at the end ensures consistent output whether the task definition uses task-level or container-level resource allocation

---

## Detection Commands

### 1. Get Active Task Definition ARN

Retrieve the currently active task definition ARN for each service. This is the revision ECS is actively using to launch tasks.

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].taskDefinition' \
  --output text
```

**Example output:**
```
arn:aws:ecs:us-east-1:123456789012:task-definition/my-api:42
```

**Interpret the result:** The ARN contains the family (`my-api`) and revision (`42`). Use the full ARN in the next step.

### 2. Describe Task Definition

Retrieve the full task definition to extract resource allocation, network mode, and container details.

**CLI:**
```bash
aws ecs describe-task-definition \
  --task-definition arn:aws:ecs:us-east-1:123456789012:task-definition/my-api:42 \
  --query 'taskDefinition.{
    family:family,
    revision:revision,
    cpu:cpu,
    memory:memory,
    networkMode:networkMode,
    containerDefinitions:containerDefinitions[].{
      name:name,
      image:image,
      cpu:cpu,
      memory:memory,
      memoryReservation:memoryReservation,
      essential:essential
    }
  }'
```

**Example output (Fargate task with task-level resources):**
```json
{
  "family": "my-api",
  "revision": 42,
  "cpu": "512",
  "memory": "1024",
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "app",
      "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-api:v2.3.1",
      "cpu": 256,
      "memory": null,
      "memoryReservation": 512,
      "essential": true
    },
    {
      "name": "envoy",
      "image": "840364872350.dkr.ecr.us-east-1.amazonaws.com/aws-appmesh-envoy:v1.27.3.0-prod",
      "cpu": 128,
      "memory": null,
      "memoryReservation": 256,
      "essential": true
    }
  ]
}
```

**Example output (EC2 task without task-level resources):**
```json
{
  "family": "worker-batch",
  "revision": 7,
  "cpu": null,
  "memory": null,
  "networkMode": "bridge",
  "containerDefinitions": [
    {
      "name": "worker",
      "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/worker@sha256:a1b2c3d4e5f6...",
      "cpu": 512,
      "memory": 1024,
      "memoryReservation": 768,
      "essential": true
    },
    {
      "name": "datadog-agent",
      "image": "datadog/agent:7.50.0",
      "cpu": 128,
      "memory": 256,
      "memoryReservation": 128,
      "essential": false
    }
  ]
}
```

**Interpret the results:**
- `cpu` and `memory` at the top level are task-level resource allocations (strings like `"512"`, `"1024"`)
- `null` for task-level CPU/memory means resources are not set at task level (common on EC2 launch type)
- Per-container `cpu` and `memory` are integers (CPU units and MiB respectively)
- `memoryReservation` is the soft memory limit — ECS places tasks based on this value when hard limit is not set
- `essential: true` means the container stopping causes the whole task to stop

---

## Output Schema

```yaml
task_definitions:
  services:
    - service_name: string
      family: string              # Task definition family
      revision: int               # Active revision number
      task_cpu: string | null     # CPU units (e.g., "256", "1024") or null if not set
      task_memory: string | null  # MiB (e.g., "512", "2048") or null if not set
      network_mode: string        # awsvpc | bridge | host | none
      containers:
        - name: string
          image: string           # Full image reference (tag or digest)
          cpu: int | null         # Per-container CPU units
          memory: int | null      # Per-container memory (MiB)
          memory_reservation: int | null  # Soft limit
          essential: bool
      error: string | null        # Populated when DescribeServices or DescribeTaskDefinition fails for this service
```

**Field notes:**
- `task_cpu` / `task_memory` are strings when set (e.g., `"256"`, `"512"`) because the ECS API returns them as strings, or `null` when not declared
- `image` is reported exactly as declared in the task definition — preserving tags (`v2.3.1`), digests (`sha256:...`), or `latest`
- `cpu` / `memory` per container are integers (CPU units and MiB) or `null` if not set on that container
- `memory_reservation` is the soft limit used for task placement on EC2
- `error` is `null` on success; when retrieval fails for a service, set `error` to a description of the failure and omit the other fields (see [Task Definition Retrieval Failure](#task-definition-retrieval-failure))

---

## Edge Cases

Handle these scenarios to provide accurate task definition reporting.

### Task-Level CPU/Memory Not Set

On EC2 launch type, task-level `cpu` and `memory` are optional. When absent, ECS relies on per-container resource declarations for placement.

**How to handle:** Report `task_cpu: null` and `task_memory: null`. The per-container `cpu` and `memory` fields become the primary resource reference.

**Why this matters:** Fargate requires task-level CPU/memory, but EC2 does not. A `null` value signals the operator is using EC2-style resource allocation where the sum of container resources determines placement.

### Multiple Containers (Sidecar Patterns)

Many production services use sidecar containers for proxies (Envoy, nginx), monitoring agents (Datadog, CloudWatch agent), or log routers (Firelens, Fluentd).

**How to handle:** Report all containers in the `containers` list. The `essential` field distinguishes primary containers from sidecars:
- `essential: true` — stopping this container stops the task (usually the application)
- `essential: false` — this container can stop without affecting the task (usually sidecars)

**Common sidecar patterns:**
- App Mesh Envoy proxy: `essential: true` (ECS requires this for App Mesh)
- Datadog/CloudWatch agent: `essential: false`
- AWS FireLens log router: `essential: true` (log loss if stopped)
- X-Ray daemon: `essential: false`

### Image Tags vs Digests

Container images can be referenced by tag or by digest. Report the image reference exactly as declared.

**Tag format:** `123456789012.dkr.ecr.us-east-1.amazonaws.com/my-api:v2.3.1`
**Digest format:** `123456789012.dkr.ecr.us-east-1.amazonaws.com/my-api@sha256:a1b2c3d4...`
**Latest (implicit):** `123456789012.dkr.ecr.us-east-1.amazonaws.com/my-api:latest`

**How to handle:** Do not resolve tags to digests or modify the image reference. Report it verbatim from the task definition. This preserves the operator's intent and makes it easy to spot mutable tags (like `latest`) versus immutable digests.

### Task Definition Retrieval Failure

If `DescribeTaskDefinition` fails (e.g., access denied, task definition deleted but service still references it):

**How to handle:** Report an error for that specific service and continue processing remaining services:
```yaml
task_definitions:
  services:
    - service_name: "my-api"
      error: "Failed to retrieve task definition: AccessDeniedException"
    - service_name: "worker"
      family: "worker-batch"
      # ... normal output continues
```

### Fargate vs EC2 Resource Requirements

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html

| Field | Fargate | EC2 |
|-------|---------|-----|
| `task_cpu` | Required (string) | Optional (null allowed) |
| `task_memory` | Required (string) | Optional (null allowed) |
| Per-container `cpu` | Optional | Used for placement |
| Per-container `memory` | Optional | Hard limit for OOM kill |
| `memory_reservation` | Not used | Soft limit for placement |

**Why this matters:** When `task_cpu` and `task_memory` are both `null`, the service is almost certainly running on EC2 launch type. This is a signal for the compute module's launch type classification.

### Network Mode Implications

The `network_mode` field affects how containers communicate:
- `awsvpc` — Each task gets its own ENI (required for Fargate, recommended for EC2)
- `bridge` — Containers share the host's Docker bridge network (EC2 only)
- `host` — Containers share the host's network namespace directly (EC2 only)
- `none` — No external networking (rare, used for batch processing)

**How to handle:** Report the mode as declared. The networking module uses this value for deeper connectivity analysis.

---

## Sources

- Task definition parameters (task/container CPU and memory semantics, `memoryReservation`, `essential`, `networkMode`): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html
- TaskDefinition API object (field types — task-level `cpu`/`memory` as strings, container-level as integers): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_TaskDefinition.html
- ContainerDefinition API object (`image`, `cpu`, `memory`, `memoryReservation`, `essential`): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ContainerDefinition.html
- Fargate task CPU/memory requirements: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html
- DescribeTaskDefinition API: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeTaskDefinition.html
