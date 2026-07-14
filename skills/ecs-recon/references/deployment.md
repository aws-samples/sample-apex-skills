# Module: Deployment Configuration

> **Part of:** [ecs-recon](../SKILL.md)
> **Purpose:** Discover deployment mechanisms and safety controls for ECS services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Deployment Controller Type and Strategy](#1-deployment-controller-type-and-strategy)
  - [Deployment Configuration](#2-deployment-configuration)
  - [Active Deployments](#3-active-deployments-ecs-controller)
  - [Task Sets](#4-task-sets-code_deploy-and-external-controllers)
- [Output Schema](#output-schema)
- [Controller Type Classification](#controller-type-classification)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Prerequisites

- **Service name(s) required:** Yes
- **Cluster name required:** Yes
- **APIs used:** `ecs:DescribeServices`
- **CLI commands:** `aws ecs describe-services`
- **IAM permissions:** `ecs:DescribeServices` (read-only)

---

## Detection Strategy

All deployment configuration data is available from a single `DescribeServices` API call. The response contains the deployment controller, deployment strategy, deployment configuration (min/max healthy percent, circuit breaker, bake time, alarms), the list of active deployments with rollout state, and — for CodeDeploy/external controllers — the task sets that carry the actual rollout state.

Run detection in this order:

```
1. Describe Services       -> Get full service details including deployment fields
2. Extract Controller      -> Read deploymentController.type
3. Extract Strategy        -> Read deploymentConfiguration.strategy (ROLLING | BLUE_GREEN | LINEAR | CANARY)
4. Classify                -> Combine controller type + strategy into controller_type
5. Extract Configuration   -> Pull minimumHealthyPercent, maximumPercent, circuit breaker, bakeTimeInMinutes, alarms
6. Extract Deployments     -> ECS controller: list deployments[] with rollout state progression
7. Extract Task Sets       -> CODE_DEPLOY / EXTERNAL controllers: list taskSets[] (same response)
```

**Why this order matters:**
- The controller type alone is NOT enough to classify the deployment mechanism. ECS-native blue/green, linear, and canary deployments (GA July 2025) keep `deploymentController.type == "ECS"` and are distinguished only by `deploymentConfiguration.strategy` — classifying on controller type alone silently misreports them as rolling updates
- CodeDeploy-controlled services may have limited deployment configuration in the ECS response since CodeDeploy manages the rollout
- Circuit breaker only applies to ECS rolling update deployments
- The `deployments[]` list is used only with the `ECS` deployment controller; for `CODE_DEPLOY` and `EXTERNAL` controllers the rollout state lives in `taskSets[]` (same DescribeServices response — no extra call)

---

## Detection Commands

### 1. Deployment Controller Type and Strategy

Determine how the service is deployed. Query BOTH the controller type and the deployment strategy — the controller type alone cannot distinguish ECS rolling updates from ECS-native blue/green, linear, or canary deployments.

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].{controller:deploymentController.type,strategy:deploymentConfiguration.strategy}'
```

**Example output (ECS rolling update):**
```json
{
    "controller": "ECS",
    "strategy": "ROLLING"
}
```

**Example output (ECS-native blue/green — note the controller is still "ECS"):**
```json
{
    "controller": "ECS",
    "strategy": "BLUE_GREEN"
}
```

**Example output (CodeDeploy blue/green):**
```json
{
    "controller": "CODE_DEPLOY",
    "strategy": null
}
```

**Example output (External controller):**
```json
{
    "controller": "EXTERNAL",
    "strategy": null
}
```

**Interpret the result:**
- `"ECS"` + strategy `"ROLLING"` (or strategy absent/null) → ECS manages rolling deployments with configurable min/max percent and circuit breaker
- `"ECS"` + strategy `"BLUE_GREEN"` → ECS-native blue/green: ECS runs blue and green service revisions simultaneously and shifts traffic, with an optional bake time before the old revision is retired
- `"ECS"` + strategy `"LINEAR"` → ECS-native linear: traffic shifts in equal percentage increments with configurable bake times between steps (see `linearConfiguration`)
- `"ECS"` + strategy `"CANARY"` → ECS-native canary: a fixed percentage of traffic shifts first for testing, the remainder shifts after a bake period (see `canaryConfiguration`)
- `"CODE_DEPLOY"` → AWS CodeDeploy manages blue/green deployments; deployment configuration in ECS response may be limited
- `"EXTERNAL"` → A third-party controller manages deployments; ECS does not orchestrate rollouts

### 2. Deployment Configuration

Extract the safety controls that govern how deployments roll out. These values control how aggressively ECS replaces tasks during a deployment, and — for ECS-native blue/green, linear, and canary strategies — the bake time, alarms, and traffic-shifting configuration.

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

**Example output (ECS-native blue/green — real service response):**
```json
{
    "strategy": "BLUE_GREEN",
    "bakeTimeInMinutes": 15,
    "deploymentCircuitBreaker": {
        "enable": true,
        "rollback": true
    },
    "maximumPercent": 200,
    "minimumHealthyPercent": 100
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
- `strategy`: The deployment strategy (`ROLLING | BLUE_GREEN | LINEAR | CANARY`); absent on services created before strategies existed — treat absent as rolling
- `minimumHealthyPercent`: The lower bound on tasks that must remain healthy during a deployment (e.g., 100 means no tasks are stopped before new ones are healthy)
- `maximumPercent`: The upper bound on total tasks during deployment (e.g., 200 means up to 2x desired count can run simultaneously)
- `deploymentCircuitBreaker.enable`: When `true`, ECS monitors deployment health and can stop a failing deployment
- `deploymentCircuitBreaker.rollback`: When `true`, a failed deployment automatically rolls back to the previous stable state
- `bakeTimeInMinutes`: For `BLUE_GREEN`, the period both blue and green revisions run simultaneously after production traffic has shifted
- `alarms`: CloudWatch alarms (`alarmNames`, `enable`, `rollback`) that ECS monitors during the deployment; when `rollback` is true, an alarm in ALARM state rolls the deployment back
- `lifecycleHooks`, `linearConfiguration`, `canaryConfiguration`: Additional strategy-specific configuration — report them when present rather than dropping them

### 3. Active Deployments (ECS Controller)

List the current deployments to understand rollout state and progression. A service can have multiple deployments active simultaneously during a rolling update.

**Scope:** The `deployments[]` list is used only when the service uses the `ECS` deployment controller. For `CODE_DEPLOY` and `EXTERNAL` controllers, use [Task Sets](#4-task-sets-code_deploy-and-external-controllers) instead.

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
- `rolloutState: FAILED` — The service failed to reach a steady state AND the deployment circuit breaker is enabled. Without the circuit breaker, a deployment that cannot stabilize stays `IN_PROGRESS` indefinitely — it never transitions to `FAILED`

### 4. Task Sets (CODE_DEPLOY and EXTERNAL Controllers)

For services using the `CODE_DEPLOY` or `EXTERNAL` deployment controller, the `Deployment` object does not carry rollout state — per the API reference, it "is used only when a service uses the `ECS` deployment controller type." The rollout state for these services lives in `Service.taskSets[]`, which is returned in the same DescribeServices response (no extra API call).

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].taskSets[*].{id:id,status:status,stabilityStatus:stabilityStatus,taskDefinition:taskDefinition,computedDesiredCount:computedDesiredCount,runningCount:runningCount}'
```

**Example output (CodeDeploy blue/green mid-deployment):**
```json
[
    {
        "id": "ecs-svc/4567890123456789012",
        "status": "PRIMARY",
        "stabilityStatus": "STEADY_STATE",
        "taskDefinition": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-api:42",
        "computedDesiredCount": 3,
        "runningCount": 3
    },
    {
        "id": "ecs-svc/5678901234567890123",
        "status": "ACTIVE",
        "stabilityStatus": "STABILIZING",
        "taskDefinition": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-api:43",
        "computedDesiredCount": 3,
        "runningCount": 1
    }
]
```

**Interpret the result:**
- `status: PRIMARY` — The task set serving production traffic
- `status: ACTIVE` — A task set not serving production traffic (e.g., the green fleet before cutover)
- `status: DRAINING` — Tasks are being stopped and deregistered from their target group
- `stabilityStatus: STEADY_STATE` — Running count matches computed desired count, nothing pending, all health checks passing
- `stabilityStatus: STABILIZING` — The task set has not yet reached steady state
- `computedDesiredCount` — The service `desiredCount` multiplied by the task set's `scale` percentage, rounded up

---

## Output Schema

```yaml
deployment:
  services:
    - service_name: string
      controller_type: string     # "ecs_rolling" | "ecs_blue_green" | "ecs_linear" | "ecs_canary" | "code_deploy" | "external" | "unknown"
      strategy: string | null     # Raw deploymentConfiguration.strategy: ROLLING | BLUE_GREEN | LINEAR | CANARY, null if absent
      minimum_healthy_percent: int | null   # Integer percentage
      maximum_percent: int | null           # Integer percentage
      bake_time_in_minutes: int | null      # BLUE_GREEN only; null otherwise
      circuit_breaker:
        enabled: bool
        rollback_enabled: bool
      alarms:                     # null when deploymentConfiguration.alarms is absent
        alarm_names: list[string]
        enable: bool
        rollback: bool
      deployments:                # Populated for the ECS controller
        - id: string
          status: string          # PRIMARY | ACTIVE | INACTIVE
          desired_count: int
          running_count: int
          rollout_state: string | null  # COMPLETED | IN_PROGRESS | FAILED
      task_sets:                  # Populated for CODE_DEPLOY and EXTERNAL controllers
        - id: string
          status: string          # PRIMARY | ACTIVE | DRAINING
          stability_status: string  # STEADY_STATE | STABILIZING
          task_definition: string
          computed_desired_count: int
          running_count: int
      error: string | null        # Populated when DescribeServices fails for this service
```

---

## Controller Type Classification

Map the raw API response values to the standardized output value. Classification requires BOTH `deploymentController.type` and `deploymentConfiguration.strategy` — the controller type alone cannot distinguish ECS rolling updates from ECS-native blue/green, linear, or canary deployments.

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html

| API `deploymentController.type` | API `deploymentConfiguration.strategy` | Output `controller_type` |
|---------------------------------|----------------------------------------|--------------------------|
| `"ECS"` | `"ROLLING"` or absent | `"ecs_rolling"` |
| `"ECS"` | `"BLUE_GREEN"` | `"ecs_blue_green"` |
| `"ECS"` | `"LINEAR"` | `"ecs_linear"` |
| `"ECS"` | `"CANARY"` | `"ecs_canary"` |
| `"CODE_DEPLOY"` | (any) | `"code_deploy"` |
| `"EXTERNAL"` | (any) | `"external"` |
| Missing or unrecognized | (any) | `"unknown"` |

**Classification logic:**
```
if deploymentController is null or missing:
    controller_type = "unknown"
elif deploymentController.type == "ECS":
    strategy = deploymentConfiguration.strategy  # may be absent
    if strategy is null or missing or strategy == "ROLLING":
        controller_type = "ecs_rolling"
    elif strategy == "BLUE_GREEN":
        controller_type = "ecs_blue_green"
    elif strategy == "LINEAR":
        controller_type = "ecs_linear"
    elif strategy == "CANARY":
        controller_type = "ecs_canary"
    else:
        controller_type = "unknown"
elif deploymentController.type == "CODE_DEPLOY":
    controller_type = "code_deploy"
elif deploymentController.type == "EXTERNAL":
    controller_type = "external"
else:
    controller_type = "unknown"
```

**For ECS-native blue/green, linear, and canary services:** also extract `strategy`, `bakeTimeInMinutes`, `alarms`, and any `lifecycleHooks` / `linearConfiguration` / `canaryConfiguration` from `deploymentConfiguration` — dropping them misrepresents the service's deployment safety controls.

---

## Edge Cases

Handle these special scenarios to provide accurate deployment reporting.

### CodeDeploy Controller — Limited ECS Response

When a service uses `CODE_DEPLOY`, the ECS DescribeServices response may not include full deployment configuration because CodeDeploy manages the rollout externally.

**What to expect:**
- `deploymentConfiguration` may still have `minimumHealthyPercent` and `maximumPercent` (these are ECS-level settings)
- `deploymentCircuitBreaker` is typically absent because CodeDeploy has its own rollback mechanism
- Rollout state lives in `taskSets[]`, not `deployments[]` — the `Deployment` object is used only with the `ECS` deployment controller

**How to handle:**
- Report `controller_type: "code_deploy"` and note that CodeDeploy governs the deployment
- Report `minimum_healthy_percent` and `maximum_percent` if present, `null` if absent
- Report `circuit_breaker.enabled: false` and `circuit_breaker.rollback_enabled: false` since circuit breaker is an ECS-rolling-update feature
- Report `task_sets` from `services[0].taskSets[]` (see [Task Sets](#4-task-sets-code_deploy-and-external-controllers)); the CodeDeploy deployment ID is available in each task set's `externalId`

### External Controller — Minimal ECS Visibility

When a service uses `EXTERNAL`, an external deployment controller (such as a custom pipeline or third-party tool) manages task placement.

**What to expect:**
- ECS does not manage deployments; rollout state lives in `taskSets[]` created by the external controller
- `deploymentConfiguration` may be absent or have default values
- No circuit breaker configuration applies

**How to handle:**
- Report `controller_type: "external"`
- Report any configuration values present, `null` if absent
- Report `circuit_breaker.enabled: false` and `circuit_breaker.rollback_enabled: false`
- Report `task_sets` from `services[0].taskSets[]` (see [Task Sets](#4-task-sets-code_deploy-and-external-controllers)); the list may be empty if the external controller has not created any task sets

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

Per the API reference, `rolloutState` "is only returned for services that use the rolling update (`ECS`) deployment type that aren't behind a Classic Load Balancer." A `null` or missing `rolloutState` therefore indicates the service uses a non-ECS deployment controller (CODE_DEPLOY or EXTERNAL) or sits behind a Classic Load Balancer.

**How to handle:**
- Report `rollout_state: null` when the field is missing or null
- This is not an error — check the deployment controller type and load balancer type to explain why the field is absent

### Service Describe Failure

If `DescribeServices` fails for a specific service (access denied, service not found, throttling):

**How to handle:**
- Report an error for that specific service by setting its `error` field (e.g., `error: "Failed to describe service: AccessDeniedException"`), leaving the other fields absent
- Continue processing remaining services
- Do not terminate the entire deployment module for a single service failure

---

## Sources

- Deployment configuration fields (`strategy`, `bakeTimeInMinutes`, `alarms`, `lifecycleHooks`, `linearConfiguration`, `canaryConfiguration`, circuit breaker, min/max percent): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html
- Deployment object semantics (`rolloutState` conditions, `status` values, ECS-controller-only scope): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Deployment.html
- Task set semantics for CodeDeploy/external deployments (`status`, `stabilityStatus`, `computedDesiredCount`, `externalId`): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_TaskSet.html
- ECS-native blue/green deployments (developer guide): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html
- Rolling update deployments and circuit breaker behavior: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html
