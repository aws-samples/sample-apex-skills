---
title: "Module: Deployment Configuration"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/deployment.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/deployment.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/deployment.md). Edit the source, not this page.
:::

# Module: Deployment Configuration

> **Part of:** [ecs-recon](../)
> **Purpose:** Discover deployment mechanisms and safety controls for ECS services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Deployment Controller Type](#1-deployment-controller-type)
  - [Deployment Configuration](#2-deployment-configuration)
  - [Active Deployments](#3-active-deployments)
- [Output Schema](#output-schema)
- [Controller Type Classification](#controller-type-classification)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Service name(s) required:** Yes
- **Cluster name required:** Yes
- **APIs used:** `ecs:DescribeServices`
- **CLI commands:** `aws ecs describe-services`
- **IAM permissions:** `ecs:DescribeServices` (read-only)

---

## Detection Strategy

All deployment configuration data is available from a single `DescribeServices` API call. The response contains the deployment controller, deployment configuration (min/max healthy percent, circuit breaker), and the list of active deployments with rollout state.

Run detection in this order:

```
1. Describe Services       -> Get full service details including deployment fields
2. Extract Controller      -> Classify the deploymentController.type value
3. Extract Configuration   -> Pull minimumHealthyPercent, maximumPercent, circuit breaker
4. Extract Deployments     -> List active deployments with rollout state progression
```

**Why this order matters:**
- The controller type determines whether deployment configuration fields are meaningful in the ECS response
- CodeDeploy-controlled services may have limited deployment configuration in the ECS response since CodeDeploy manages the rollout
- Circuit breaker only applies to ECS rolling update deployments
- Active deployments show in-flight rollout status regardless of controller type

---

## Detection Commands

### 1. Deployment Controller Type

Determine how the service is deployed. The controller type fundamentally affects what other deployment fields are available and meaningful.

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name>"]
)
-> Check response for services[].deploymentController.type
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].deploymentController'
```

**Example output (ECS rolling update):**
```json
{
    "type": "ECS"
}
```

**Example output (CodeDeploy blue/green):**
```json
{
    "type": "CODE_DEPLOY"
}
```

**Example output (External controller):**
```json
{
    "type": "EXTERNAL"
}
```

**Interpret the result:**
- `"ECS"` → ECS manages rolling deployments with configurable min/max percent and circuit breaker
- `"CODE_DEPLOY"` → AWS CodeDeploy manages blue/green deployments; deployment configuration in ECS response may be limited
- `"EXTERNAL"` → A third-party controller manages deployments; ECS does not orchestrate rollouts

### 2. Deployment Configuration

Extract the safety controls that govern how deployments roll out. These values control how aggressively ECS replaces tasks during a deployment.

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name>"]
)
-> Check response for services[].deploymentConfiguration
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].deploymentConfiguration'
```

**Example output (ECS rolling with circuit breaker):**
```json
{
    "deploymentCircuitBreaker": {
        "enable": true,
        "rollback": true
    },
    "maximumPercent": 200,
    "minimumHealthyPercent": 100
}
```

**Example output (ECS rolling without circuit breaker):**
```json
{
    "maximumPercent": 200,
    "minimumHealthyPercent": 50
}
```

**Example output (CodeDeploy service — limited config):**
```json
{
    "maximumPercent": 200,
    "minimumHealthyPercent": 100
}
```

**Interpret the result:**
- `minimumHealthyPercent`: The lower bound on tasks that must remain healthy during a deployment (e.g., 100 means no tasks are stopped before new ones are healthy)
- `maximumPercent`: The upper bound on total tasks during deployment (e.g., 200 means up to 2x desired count can run simultaneously)
- `deploymentCircuitBreaker.enable`: When `true`, ECS monitors deployment health and can stop a failing deployment
- `deploymentCircuitBreaker.rollback`: When `true`, a failed deployment automatically rolls back to the previous stable state

### 3. Active Deployments

List the current deployments to understand rollout state and progression. A service can have multiple deployments active simultaneously during a rolling update.

**MCP (future):**
```
ecs_describe_services(
  cluster="<cluster-name>",
  services=["<service-name>"]
)
-> Check response for services[].deployments[]
```

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].deployments[*].{id:id,status:status,desiredCount:desiredCount,runningCount:runningCount,rolloutState:rolloutState,rolloutStateReason:rolloutStateReason}'
```

**Example output (stable service with single PRIMARY deployment):**
```json
[
    {
        "id": "ecs-svc/1234567890123456789",
        "status": "PRIMARY",
        "desiredCount": 3,
        "runningCount": 3,
        "rolloutState": "COMPLETED",
        "rolloutStateReason": "ECS deployment ecs-svc/1234567890123456789 completed."
    }
]
```

**Example output (in-progress rolling update with two deployments):**
```json
[
    {
        "id": "ecs-svc/2345678901234567890",
        "status": "PRIMARY",
        "desiredCount": 3,
        "runningCount": 1,
        "rolloutState": "IN_PROGRESS",
        "rolloutStateReason": "ECS deployment ecs-svc/2345678901234567890 in progress."
    },
    {
        "id": "ecs-svc/1234567890123456789",
        "status": "ACTIVE",
        "desiredCount": 3,
        "runningCount": 2,
        "rolloutState": "COMPLETED",
        "rolloutStateReason": "ECS deployment ecs-svc/1234567890123456789 completed."
    }
]
```

**Example output (failed deployment with rollback):**
```json
[
    {
        "id": "ecs-svc/3456789012345678901",
        "status": "PRIMARY",
        "desiredCount": 3,
        "runningCount": 3,
        "rolloutState": "COMPLETED",
        "rolloutStateReason": "ECS deployment ecs-svc/3456789012345678901 completed."
    },
    {
        "id": "ecs-svc/2345678901234567890",
        "status": "INACTIVE",
        "desiredCount": 0,
        "runningCount": 0,
        "rolloutState": "FAILED",
        "rolloutStateReason": "ECS deployment circuit breaker: tasks failed to start."
    }
]
```

**Interpret the result:**
- `PRIMARY` — The target deployment that ECS is rolling towards
- `ACTIVE` — A previous deployment still running tasks (being drained during rollout)
- `INACTIVE` — A completed or failed deployment with no running tasks
- `rolloutState: COMPLETED` — Deployment reached steady state successfully
- `rolloutState: IN_PROGRESS` — Deployment is actively rolling out
- `rolloutState: FAILED` — Deployment failed (circuit breaker triggered or tasks could not stabilize)

---

## Output Schema

```yaml
deployment:
  services:
    - service_name: string
      controller_type: string     # "ecs_rolling" | "code_deploy" | "external" | "unknown"
      minimum_healthy_percent: int | null   # Integer percentage
      maximum_percent: int | null           # Integer percentage
      circuit_breaker:
        enabled: bool
        rollback_enabled: bool
      deployments:
        - id: string
          status: string          # PRIMARY | ACTIVE | INACTIVE
          desired_count: int
          running_count: int
          rollout_state: string | null  # COMPLETED | IN_PROGRESS | FAILED
```

---

## Controller Type Classification

Map the raw API response value to the standardized output value:

| API Response `deploymentController.type` | Output `controller_type` |
|------------------------------------------|--------------------------|
| `"ECS"` | `"ecs_rolling"` |
| `"CODE_DEPLOY"` | `"code_deploy"` |
| `"EXTERNAL"` | `"external"` |
| Missing or unrecognized | `"unknown"` |

**Classification logic:**
```
if deploymentController is null or missing:
    controller_type = "unknown"
elif deploymentController.type == "ECS":
    controller_type = "ecs_rolling"
elif deploymentController.type == "CODE_DEPLOY":
    controller_type = "code_deploy"
elif deploymentController.type == "EXTERNAL":
    controller_type = "external"
else:
    controller_type = "unknown"
```

---

## Edge Cases

Handle these special scenarios to provide accurate deployment reporting.

### CodeDeploy Controller — Limited ECS Response

When a service uses `CODE_DEPLOY`, the ECS DescribeServices response may not include full deployment configuration because CodeDeploy manages the rollout externally.

**What to expect:**
- `deploymentConfiguration` may still have `minimumHealthyPercent` and `maximumPercent` (these are ECS-level settings)
- `deploymentCircuitBreaker` is typically absent because CodeDeploy has its own rollback mechanism
- The `deployments` list shows ECS-tracked deployments, but the actual blue/green state lives in CodeDeploy

**How to handle:**
- Report `controller_type: "code_deploy"` and note that CodeDeploy governs the deployment
- Report `minimum_healthy_percent` and `maximum_percent` if present, `null` if absent
- Report `circuit_breaker.enabled: false` and `circuit_breaker.rollback_enabled: false` since circuit breaker is an ECS-rolling-update feature
- Still report active deployments as returned by DescribeServices

### External Controller — Minimal ECS Visibility

When a service uses `EXTERNAL`, an external deployment controller (such as a custom pipeline or third-party tool) manages task placement.

**What to expect:**
- ECS does not manage deployments; the `deployments` list may be empty or show only the current PRIMARY
- `deploymentConfiguration` may be absent or have default values
- No circuit breaker configuration applies

**How to handle:**
- Report `controller_type: "external"`
- Report any configuration values present, `null` if absent
- Report `circuit_breaker.enabled: false` and `circuit_breaker.rollback_enabled: false`

### Absent Circuit Breaker Configuration

When `deploymentCircuitBreaker` is missing from the `deploymentConfiguration` response, this means circuit breaker was never enabled for the service.

**How to handle:**
- Report `circuit_breaker.enabled: false`
- Report `circuit_breaker.rollback_enabled: false`

**Important:** Do not confuse an absent field with `"enable": false`. Both cases mean the circuit breaker is not active, but the absence means the service was created before the circuit breaker feature was available or the feature was never configured.

### Multiple Active Deployments

During a rolling update, a service can have multiple entries in the `deployments` list:
- One `PRIMARY` deployment (the target)
- One or more `ACTIVE` deployments (being drained)
- Zero or more `INACTIVE` deployments (completed or failed)

**How to handle:**
- Report all deployments returned by the API
- The deployment list shows the progression from old to new
- A service with only one `PRIMARY` deployment at `COMPLETED` state is stable

### Rollout State Null

The `rolloutState` field may be `null` for older deployments that were created before ECS added rollout state tracking.

**How to handle:**
- Report `rollout_state: null` when the field is missing or null
- This is not an error — it indicates a deployment from before the feature existed

### Service Describe Failure

If `DescribeServices` fails for a specific service (access denied, service not found, throttling):

**How to handle:**
- Report an error for that specific service
- Continue processing remaining services
- Do not terminate the entire deployment module for a single service failure
