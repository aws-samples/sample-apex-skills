---
title: "Module: Compute and Capacity"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/compute.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/compute.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/compute.md). Edit the source, not this page.
:::

# Module: Compute and Capacity

> **Part of:** [ecs-recon](../)
> **Purpose:** Detect compute model (launch type vs capacity provider strategy) and capacity configuration for ECS clusters and services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Cluster Capacity Providers](#1-cluster-capacity-providers)
  - [Service Launch Type and Capacity Provider Strategy](#2-service-launch-type-and-capacity-provider-strategy)
  - [Task Counts](#3-task-counts)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **Service name(s) required:** Yes (one or more services to inspect)
- **AWS APIs used:**
  - `ecs:DescribeClusters` — cluster-level capacity providers and default strategy
  - `ecs:DescribeServices` — per-service launch type, capacity provider strategy, task counts
- **CLI commands:** `aws ecs describe-clusters`, `aws ecs describe-services`
- **IAM permissions:** Read-only (`ecs:DescribeClusters`, `ecs:DescribeServices`)

---

## Detection Strategy

Run detections in this order to build the compute picture from cluster down to service:

```
1. Cluster Capacity Providers  -> Enumerate providers associated with the cluster
2. Service Compute Model       -> Determine launch type vs capacity provider strategy per service
3. Task Counts                 -> Collect running/desired/pending counts per service
```

**Why this order matters:**
- Cluster-level capacity providers establish the available compute pool — services reference these
- A service either specifies an explicit `launchType` (FARGATE, EC2, EXTERNAL, or MANAGED_INSTANCES) **or** a `capacityProviderStrategy` — never both
- Task counts confirm whether the compute model is delivering the desired capacity

**Key decision logic:**
- If a service has `launchType` set → report it as `FARGATE`, `EC2`, `EXTERNAL`, or `MANAGED_INSTANCES`
- If a service has `capacityProviderStrategy` set (and no explicit `launchType`) → report launch type as `not_applicable` and enumerate the strategy entries
- Both fields empty is an edge case — see [Edge Cases](#edge-cases)

---

## Detection Commands

### 1. Cluster Capacity Providers

Retrieve the capacity providers associated with the cluster and the cluster's default capacity provider strategy. This tells you what compute backends are available.

**MCP (future):**
```
ecs_describe_clusters(
  clusters=["<cluster-name>"],
  include=["SETTINGS"]
)
-> Extract capacityProviders, defaultCapacityProviderStrategy
```

**CLI:**
```bash
aws ecs describe-clusters \
  --clusters <cluster-name> \
  --include SETTINGS \
  --query 'clusters[0].{capacityProviders:capacityProviders,defaultCapacityProviderStrategy:defaultCapacityProviderStrategy,settings:settings}'
```

**Example output:**
```json
{
  "capacityProviders": [
    "FARGATE",
    "FARGATE_SPOT",
    "my-asg-provider"
  ],
  "defaultCapacityProviderStrategy": [
    {
      "capacityProvider": "FARGATE",
      "weight": 1,
      "base": 1
    },
    {
      "capacityProvider": "FARGATE_SPOT",
      "weight": 3,
      "base": 0
    }
  ],
  "settings": [
    {
      "name": "containerInsights",
      "value": "enabled"
    }
  ]
}
```

**Interpret the result:**
- `capacityProviders` lists all providers attached to this cluster
- Built-in providers: `FARGATE`, `FARGATE_SPOT`
- Custom providers reference an Auto Scaling Group (ASG)
- `defaultCapacityProviderStrategy` is used when a service does not define its own strategy

To get full details on a custom capacity provider (including the ASG ARN):

**CLI:**
```bash
aws ecs describe-capacity-providers \
  --capacity-providers my-asg-provider \
  --query 'capacityProviders[0].{name:name,status:status,autoScalingGroupProvider:autoScalingGroupProvider}'
```

**Example output:**
```json
{
  "name": "my-asg-provider",
  "status": "ACTIVE",
  "autoScalingGroupProvider": {
    "autoScalingGroupArn": "arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:12345678-1234-1234-1234-123456789012:autoScalingGroupName/my-ecs-asg",
    "managedScaling": {
      "status": "ENABLED",
      "targetCapacity": 80,
      "minimumScalingStepSize": 1,
      "maximumScalingStepSize": 10
    },
    "managedTerminationProtection": "ENABLED"
  }
}
```

### 2. Service Launch Type and Capacity Provider Strategy

For each service, determine whether it uses an explicit launch type or a capacity provider strategy. These are mutually exclusive — a service uses one or the other.

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name-1>", "<service-name-2>"]
)
-> Extract launchType, capacityProviderStrategy per service
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name-1> <service-name-2> \
  --query 'services[].{serviceName:serviceName,launchType:launchType,capacityProviderStrategy:capacityProviderStrategy,runningCount:runningCount,desiredCount:desiredCount,pendingCount:pendingCount}'
```

**Example output (service with explicit launch type):**
```json
[
  {
    "serviceName": "web-api",
    "launchType": "FARGATE",
    "capacityProviderStrategy": [],
    "runningCount": 3,
    "desiredCount": 3,
    "pendingCount": 0
  }
]
```

**Example output (service with capacity provider strategy):**
```json
[
  {
    "serviceName": "worker-service",
    "launchType": null,
    "capacityProviderStrategy": [
      {
        "capacityProvider": "FARGATE",
        "weight": 1,
        "base": 2
      },
      {
        "capacityProvider": "FARGATE_SPOT",
        "weight": 3,
        "base": 0
      }
    ],
    "runningCount": 8,
    "desiredCount": 8,
    "pendingCount": 0
  }
]
```

**Interpret the result:**
- `launchType` is `"FARGATE"` or `"EC2"` → report that value directly
- `launchType` is `null` and `capacityProviderStrategy` is non-empty → report launch type as `not_applicable`, enumerate the strategy
- `launchType` is `null` and `capacityProviderStrategy` is empty → see [Edge Cases](#edge-cases)

### 3. Task Counts

Task counts are returned in the same `describe-services` call. Extract them for each service to understand current capacity.

**Fields from `describe-services` response:**
- `runningCount` — tasks currently in RUNNING state (>= 0)
- `desiredCount` — tasks the service is trying to maintain (>= 0)
- `pendingCount` — tasks in PENDING state waiting for placement (>= 0)

**CLI (if querying separately or for verification):**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].{running:runningCount,desired:desiredCount,pending:pendingCount}'
```

**Example output:**
```json
{
  "running": 5,
  "desired": 5,
  "pending": 0
}
```

**Interpret the result:**
- `running == desired` and `pending == 0` → service is healthy and at target
- `running < desired` with `pending > 0` → tasks are being placed
- `running < desired` with `pending == 0` → possible placement failure (compute capacity issue)

---

## Output Schema

```yaml
compute:
  cluster:
    name: string
    capacity_providers:
      - name: string
        type: string  # FARGATE | FARGATE_SPOT | ASG
        status: string
        auto_scaling_group_arn: string | null
    default_capacity_provider_strategy:
      - provider: string
        weight: int   # 0-1000
        base: int     # 0-100000
  services:
    - name: string
      launch_type: string | "not_applicable"  # FARGATE | EC2 | EXTERNAL | MANAGED_INSTANCES | not_applicable
      capacity_provider_strategy:
        - provider: string
          weight: int     # 0-1000
          base: int       # 0-100000
      task_counts:
        running: int      # >= 0
        desired: int      # >= 0
        pending: int      # >= 0
```

**Type classification for capacity providers:**
- Provider name is `FARGATE` → type is `FARGATE`
- Provider name is `FARGATE_SPOT` → type is `FARGATE_SPOT`
- Provider has an `autoScalingGroupProvider` in describe response → type is `ASG`

**Strategy entry fields:**
- `weight` — relative proportion of tasks to place on this provider (0–1000)
- `base` — minimum number of tasks to run on this provider before weight distribution applies (0–100000)

---

## Edge Cases

Handle these scenarios to ensure accurate compute reporting.

### Service with no explicit launch type and empty capacity provider strategy

When a service has neither `launchType` nor `capacityProviderStrategy` set, the service inherits the cluster's default capacity provider strategy.

**How to handle:**
- Report `launch_type: "not_applicable"`
- Report the cluster's `defaultCapacityProviderStrategy` as the effective strategy for that service
- Add a note indicating the strategy is inherited from the cluster default

**Detection:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].{launchType:launchType,strategy:capacityProviderStrategy}'
```

If both are null/empty, cross-reference with the cluster's `defaultCapacityProviderStrategy`.

### Empty capacity provider list on cluster

A cluster may have no capacity providers associated. This happens with legacy clusters created before capacity providers were available, or clusters that use only explicit `launchType` on each service.

**How to handle:**
- Report `capacity_providers: []` (empty list)
- Services on this cluster must each specify their own `launchType` explicitly
- If a service also has no launch type set on such a cluster, report an error — the service configuration is incomplete

### Mixed Fargate + EC2 clusters

A cluster can have both Fargate and EC2 (ASG) capacity providers. Different services in the same cluster may use different compute models.

**How to handle:**
- Report all capacity providers on the cluster, regardless of type
- Report each service's compute model independently
- One service might use `launchType: FARGATE` while another uses a capacity provider strategy mixing `FARGATE_SPOT` and an ASG provider

**Example mixed cluster output:**
```yaml
compute:
  cluster:
    name: prod-mixed
    capacity_providers:
      - name: FARGATE
        type: FARGATE
        status: ACTIVE
        auto_scaling_group_arn: null
      - name: FARGATE_SPOT
        type: FARGATE_SPOT
        status: ACTIVE
        auto_scaling_group_arn: null
      - name: ec2-ondemand
        type: ASG
        status: ACTIVE
        auto_scaling_group_arn: "arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:abc123:autoScalingGroupName/ecs-ec2-asg"
    default_capacity_provider_strategy:
      - provider: FARGATE
        weight: 1
        base: 1
  services:
    - name: api-service
      launch_type: FARGATE
      capacity_provider_strategy: []
      task_counts:
        running: 3
        desired: 3
        pending: 0
    - name: batch-worker
      launch_type: not_applicable
      capacity_provider_strategy:
        - provider: ec2-ondemand
          weight: 1
          base: 2
        - provider: FARGATE_SPOT
          weight: 3
          base: 0
      task_counts:
        running: 10
        desired: 10
        pending: 0
```

### Describe request fails (access denied or resource not found)

If `ecs:DescribeServices` or `ecs:DescribeClusters` returns an error:

**How to handle:**
- Do NOT present partial data as complete
- Report the error with the specific API call that failed
- Use the unavailable output schema:

```yaml
compute:
  unavailable: true
  reason: "ecs:DescribeServices failed for cluster 'prod-api': AccessDeniedException"
```

### Capacity provider in INACTIVE or DELETE_IN_PROGRESS status

Capacity providers can be in transitional states. Always report the actual status value so the user knows if a provider is being decommissioned.

**How to handle:**
- Include the capacity provider in the list with its actual `status` value
- Do not filter out non-ACTIVE providers — they are still associated with the cluster
