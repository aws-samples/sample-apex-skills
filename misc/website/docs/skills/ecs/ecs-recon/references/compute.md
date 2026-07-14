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
  - `ecs:DescribeCapacityProviders` — capacity provider type and backing configuration (ASG or Managed Instances)
- **CLI commands:** `aws ecs describe-clusters`, `aws ecs describe-services`, `aws ecs describe-capacity-providers`
- **IAM permissions:** Read-only (`ecs:DescribeClusters`, `ecs:DescribeServices`, `ecs:DescribeCapacityProviders`)

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
- Custom providers are backed either by an Auto Scaling Group (ASG) or by ECS Managed Instances
- `defaultCapacityProviderStrategy` is used when a service does not define its own strategy

To get full details on a custom capacity provider (including its type and backing configuration):

**CLI:**
```bash
aws ecs describe-capacity-providers \
  --capacity-providers my-asg-provider \
  --query 'capacityProviders[0].{name:name,status:status,type:type,autoScalingGroupProvider:autoScalingGroupProvider,managedInstancesProvider:managedInstancesProvider}'
```

**Example output (ASG-backed provider):**
```json
{
  "name": "my-asg-provider",
  "status": "ACTIVE",
  "type": "EC2_AUTOSCALING",
  "autoScalingGroupProvider": {
    "autoScalingGroupArn": "arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:12345678-1234-1234-1234-123456789012:autoScalingGroupName/my-ecs-asg",
    "managedScaling": {
      "status": "ENABLED",
      "targetCapacity": 80,
      "minimumScalingStepSize": 1,
      "maximumScalingStepSize": 10
    },
    "managedTerminationProtection": "ENABLED"
  },
  "managedInstancesProvider": null
}
```

**Example output (Managed Instances provider):**
```json
{
  "name": "SampleManagedInstances",
  "status": "ACTIVE",
  "type": "MANAGED_INSTANCES",
  "autoScalingGroupProvider": null,
  "managedInstancesProvider": {
    "infrastructureRoleArn": "arn:aws:iam::123456789012:role/ecsInfrastructureRole",
    "propagateTags": "NONE"
  }
}
```

### 2. Service Launch Type and Capacity Provider Strategy

For each service, determine whether it uses an explicit launch type or a capacity provider strategy. These are mutually exclusive — a service uses one or the other.

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name-1> <service-name-2> \
  --query 'services[].{serviceName:serviceName,launchType:launchType,capacityProviderStrategy:capacityProviderStrategy,runningCount:runningCount,desiredCount:desiredCount,pendingCount:pendingCount}'
```

**Batch limit:** `DescribeServices` accepts a maximum of **10 services per call** — passing more than 10 raises a `ClientException`. For clusters with more than 10 services, batch service names into groups of 10 (mirroring the 100-cluster cap on `DescribeClusters`).

**Example output (service with explicit launch type):**
```json
[
  {
    "serviceName": "web-api",
    "launchType": "FARGATE",
    "capacityProviderStrategy": null,
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
- `launchType` is set (`"FARGATE"`, `"EC2"`, `"EXTERNAL"`, or `"MANAGED_INSTANCES"`) → report that value directly
- `launchType` is `null` and `capacityProviderStrategy` is non-empty → report launch type as `not_applicable`, enumerate the strategy
- `launchType` is `null` and `capacityProviderStrategy` is `null`/empty → see [Edge Cases](#edge-cases)

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
- `running == desired` and `pending == 0` → task counts are at target (a factual state, not a health verdict — a crash-looping service can also match this momentarily; this skill reports facts, not health judgments)
- `running < desired` with `pending > 0` → tasks are being placed
- `running < desired` with `pending == 0` → possible placement failure (compute capacity issue)

---

## Output Schema

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CapacityProvider.html (CapacityProvider.type enum: EC2_AUTOSCALING | MANAGED_INSTANCES | FARGATE | FARGATE_SPOT) and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Service.html (launchType enum: EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES)

```yaml
compute:
  cluster:
    name: string
    capacity_providers:
      - name: string
        type: string  # EC2_AUTOSCALING | MANAGED_INSTANCES | FARGATE | FARGATE_SPOT | unrecognized
        status: string
        auto_scaling_group_arn: string | null  # null unless type is EC2_AUTOSCALING
    default_capacity_provider_strategy:
      - provider: string
        weight: int   # 0-1000
        base: int     # 0-100000
    error: string | null  # Failing API call + error code for cluster-level lookups; null otherwise
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
      error: string | null  # Failing API call + error code for this service; null otherwise
```

**Type classification for capacity providers:**

Classify on the API's first-class `type` field from `describe-capacity-providers` — do not infer from the provider name:
- `type: "FARGATE"` → `FARGATE`
- `type: "FARGATE_SPOT"` → `FARGATE_SPOT`
- `type: "EC2_AUTOSCALING"` → `EC2_AUTOSCALING` (carries `autoScalingGroupProvider`; extract `auto_scaling_group_arn` from it)
- `type: "MANAGED_INSTANCES"` → `MANAGED_INSTANCES` (carries `managedInstancesProvider`, not an ASG)
- Any other value → `unrecognized` (AWS may add new provider types; do not fail the module)

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
        type: EC2_AUTOSCALING
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

If a describe call fails partway through, retain everything already collected — never discard already-collected inventory (see overview.md, Partial Failure Retention).

**How to handle (per-resource failure — the normal case):**
- If `ecs:DescribeServices` fails for a batch of services, or `ecs:DescribeCapacityProviders` fails for a provider, record the error on the affected entries (set `error` to the failing API call + error code), omit the fields you could not retrieve, and continue with the remaining services/providers
- Do NOT present an errored entry's partial data as complete — the `error` field marks it as incomplete

```yaml
compute:
  cluster:
    name: prod-api
    capacity_providers: [...]
    error: null
  services:
    - name: web-api
      error: "ecs:DescribeServices failed: AccessDeniedException"
    - name: worker-service
      launch_type: FARGATE
      task_counts: {running: 3, desired: 3, pending: 0}
      error: null
```

**How to handle (total failure — module-level `unavailable`):**
- Use module-level `unavailable: true` ONLY when the module cannot produce any data at all — i.e., the initial `ecs:DescribeClusters` call fails, or the first `ListServices`/`DescribeServices` call fails before any per-service data was gathered

```yaml
compute:
  unavailable: true
  reason: "ecs:DescribeClusters failed for cluster 'prod-api': AccessDeniedException"
```

### Capacity provider in INACTIVE or DELETE_IN_PROGRESS status

Capacity providers can be in transitional states. Always report the actual status value so the user knows if a provider is being decommissioned.

**How to handle:**
- Include the capacity provider in the list with its actual `status` value
- Do not filter out non-ACTIVE providers — they are still associated with the cluster

---

## Sources

- CapacityProvider API shape, `type` enum (EC2_AUTOSCALING | MANAGED_INSTANCES | FARGATE | FARGATE_SPOT), `autoScalingGroupProvider`, `managedInstancesProvider`: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CapacityProvider.html
- Service API shape, `launchType` enum (EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES), mutual exclusivity with `capacityProviderStrategy`: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Service.html
- DescribeServices request limit (max 10 services per call): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeServices.html
- DescribeCapacityProviders API: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeCapacityProviders.html
- Capacity provider strategy semantics (base/weight): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-capacity-providers.html
