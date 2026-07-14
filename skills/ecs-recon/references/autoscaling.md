# Module: Auto Scaling

> **Part of:** [ecs-recon](../SKILL.md)
> **Purpose:** Discover Application Auto Scaling configuration for ECS services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Scalable Targets](#1-scalable-targets)
  - [Scaling Policies](#2-scaling-policies)
  - [Scheduled Actions](#3-scheduled-actions)
- [Output Schema](#output-schema)
- [Policy Type Classification](#policy-type-classification)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Service name(s) required:** Yes
- **Cluster name required:** Yes
- **APIs used:** `application-autoscaling:DescribeScalableTargets`, `application-autoscaling:DescribeScalingPolicies`, `application-autoscaling:DescribeScheduledActions`
- **CLI commands:** `aws application-autoscaling describe-scalable-targets`, `aws application-autoscaling describe-scaling-policies`, `aws application-autoscaling describe-scheduled-actions`
- **IAM permissions:** `application-autoscaling:DescribeScalableTargets`, `application-autoscaling:DescribeScalingPolicies`, `application-autoscaling:DescribeScheduledActions` (read-only)

---

## Detection Strategy

Application Auto Scaling for ECS operates on resource IDs in the format `service/{cluster-name}/{service-name}`. Detection is a three-step process: first check whether a scalable target is registered (indicating auto scaling is configured), then retrieve the scaling policies that define how dynamic scaling behaves, then retrieve any scheduled actions that define time-based scaling.

Run detection in this order:

```
1. Build Resource ID          -> Construct "service/{cluster}/{service}" for each service
2. Describe Scalable Targets  -> Check if auto scaling is configured for each service
3. Describe Scaling Policies  -> Get dynamic-scaling policy details for services that have scalable targets
4. Describe Scheduled Actions -> Get time-based scaling actions for services that have scalable targets
```

**Why this order matters:**
- The resource ID format is fixed for ECS (`service/{cluster}/{service}`) and must be constructed before querying
- If no scalable target exists, the service has no auto scaling configured — skip the policies and scheduled-actions queries
- Scaling policies and scheduled actions reference the scalable target, so targets must be confirmed first
- Querying policies or scheduled actions for a service without a scalable target returns an empty list (wasted API call)
- Scheduled actions must be queried explicitly — a service can be scaled purely on a schedule with zero scaling policies, and skipping this step would hide its active time-based scaling

---

## Detection Commands

### 1. Scalable Targets

Determine whether Application Auto Scaling is configured for ECS services. A scalable target defines the min/max capacity boundaries for auto scaling.

**CLI:**
```bash
aws application-autoscaling describe-scalable-targets \
  --service-namespace ecs \
  --resource-ids "service/<cluster-name>/<service-name>"
```

**Example output (auto scaling configured):**
```json
{
    "ScalableTargets": [
        {
            "ServiceNamespace": "ecs",
            "ResourceId": "service/prod-cluster/api-service",
            "ScalableDimension": "ecs:service:DesiredCount",
            "MinCapacity": 2,
            "MaxCapacity": 10,
            "RoleARN": "arn:aws:iam::123456789012:role/aws-service-role/ecs.application-autoscaling.amazonaws.com/AWSServiceRoleForApplicationAutoScaling_ECSService",
            "CreationTime": "2024-01-15T10:30:00.000Z",
            "SuspendedState": {
                "DynamicScalingInSuspended": false,
                "DynamicScalingOutSuspended": false,
                "ScheduledScalingSuspended": false
            }
        }
    ]
}
```

**Example output (no auto scaling configured):**
```json
{
    "ScalableTargets": []
}
```

**Interpret the result:**
- Non-empty `ScalableTargets` list → auto scaling is configured for the service
- Empty `ScalableTargets` list → no auto scaling configured, report `configured: false`
- `MinCapacity` and `MaxCapacity` → the boundaries within which auto scaling operates
- `ScalableDimension` should always be `ecs:service:DesiredCount` for ECS services
- `SuspendedState` → indicates if scaling actions are temporarily paused (scaling is still configured but not actively responding)

### 2. Scaling Policies

Retrieve the scaling policies that define how and when the service scales. Only query policies for services that have a confirmed scalable target.

**CLI:**
```bash
aws application-autoscaling describe-scaling-policies \
  --service-namespace ecs \
  --resource-id "service/<cluster-name>/<service-name>"
```

**Example output (target tracking policy):**
```json
{
    "ScalingPolicies": [
        {
            "PolicyARN": "arn:aws:autoscaling:us-east-1:123456789012:scalingPolicy:12345678-1234-1234-1234-123456789012:resource/ecs/service/prod-cluster/api-service:policyName/cpu-target-tracking",
            "PolicyName": "cpu-target-tracking",
            "ServiceNamespace": "ecs",
            "ResourceId": "service/prod-cluster/api-service",
            "ScalableDimension": "ecs:service:DesiredCount",
            "PolicyType": "TargetTrackingScaling",
            "TargetTrackingScalingPolicyConfiguration": {
                "TargetValue": 70.0,
                "PredefinedMetricSpecification": {
                    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
                },
                "ScaleOutCooldown": 300,
                "ScaleInCooldown": 300,
                "DisableScaleIn": false
            },
            "CreationTime": "2024-01-15T10:35:00.000Z"
        }
    ]
}
```

**Example output (step scaling policy):**
```json
{
    "ScalingPolicies": [
        {
            "PolicyARN": "arn:aws:autoscaling:us-east-1:123456789012:scalingPolicy:12345678-1234-1234-1234-123456789012:resource/ecs/service/prod-cluster/api-service:policyName/high-cpu-step",
            "PolicyName": "high-cpu-step",
            "ServiceNamespace": "ecs",
            "ResourceId": "service/prod-cluster/api-service",
            "ScalableDimension": "ecs:service:DesiredCount",
            "PolicyType": "StepScaling",
            "StepScalingPolicyConfiguration": {
                "AdjustmentType": "ChangeInCapacity",
                "StepAdjustments": [
                    {
                        "MetricIntervalLowerBound": 0.0,
                        "MetricIntervalUpperBound": 20.0,
                        "ScalingAdjustment": 1
                    },
                    {
                        "MetricIntervalLowerBound": 20.0,
                        "ScalingAdjustment": 3
                    }
                ],
                "Cooldown": 300,
                "MetricAggregationType": "Average"
            },
            "CreationTime": "2024-01-15T10:35:00.000Z"
        }
    ]
}
```

**Example output (multiple policies on one service):**
```json
{
    "ScalingPolicies": [
        {
            "PolicyName": "cpu-target-tracking",
            "PolicyType": "TargetTrackingScaling",
            "ResourceId": "service/prod-cluster/api-service",
            "ScalableDimension": "ecs:service:DesiredCount",
            "TargetTrackingScalingPolicyConfiguration": {
                "TargetValue": 70.0,
                "PredefinedMetricSpecification": {
                    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
                },
                "ScaleOutCooldown": 300,
                "ScaleInCooldown": 300,
                "DisableScaleIn": false
            }
        },
        {
            "PolicyName": "memory-target-tracking",
            "PolicyType": "TargetTrackingScaling",
            "ResourceId": "service/prod-cluster/api-service",
            "ScalableDimension": "ecs:service:DesiredCount",
            "TargetTrackingScalingPolicyConfiguration": {
                "TargetValue": 80.0,
                "PredefinedMetricSpecification": {
                    "PredefinedMetricType": "ECSServiceAverageMemoryUtilization"
                },
                "ScaleOutCooldown": 300,
                "ScaleInCooldown": 300,
                "DisableScaleIn": false
            }
        }
    ]
}
```

**Interpret the result:**
- `PolicyType: "TargetTrackingScaling"` → target tracking policy; check `TargetTrackingScalingPolicyConfiguration` for the metric and target value
- `PolicyType: "StepScaling"` → step scaling policy; check `StepScalingPolicyConfiguration` for step adjustments
- `PredefinedMetricType` → identifies what metric drives the scaling (CPU, memory, ALB request count)
- `TargetValue` → the desired metric value that auto scaling tries to maintain
- `StepAdjustments` → defines how many tasks to add/remove based on metric breach severity
- `MetricIntervalLowerBound`/`MetricIntervalUpperBound` → define the range of metric breach for each step (relative to the alarm threshold)
- A missing `MetricIntervalUpperBound` means the step applies to all breaches above the lower bound

### 3. Scheduled Actions

Retrieve time-based scaling actions. A service can be scaled purely on a schedule (scalable target present, zero scaling policies) — without this step, such services would look like they have no active scaling behavior.

**CLI:**
```bash
aws application-autoscaling describe-scheduled-actions \
  --service-namespace ecs \
  --resource-id "service/<cluster-name>/<service-name>"
```

**Example output:**
```json
{
    "ScheduledActions": [
        {
            "ScheduledActionName": "scale-up-business-hours",
            "ScheduledActionARN": "arn:aws:autoscaling:us-east-1:123456789012:scheduledAction:12345678-1234-1234-1234-123456789012:resource/ecs/service/prod-cluster/api-service:scheduledActionName/scale-up-business-hours",
            "ServiceNamespace": "ecs",
            "Schedule": "cron(0 8 ? * MON-FRI *)",
            "Timezone": "America/New_York",
            "ResourceId": "service/prod-cluster/api-service",
            "ScalableDimension": "ecs:service:DesiredCount",
            "ScalableTargetAction": {
                "MinCapacity": 4,
                "MaxCapacity": 20
            },
            "CreationTime": "2024-01-15T10:40:00.000Z"
        }
    ]
}
```

**Interpret the result:**
- `Schedule` → `at(...)` for one-time, `cron(...)` for recurring, or `rate(...)` expressions
- `ScalableTargetAction` → the new `MinCapacity`/`MaxCapacity` applied when the action fires (either may be absent)
- Empty `ScheduledActions` list → no time-based scaling; report `scheduled_actions: []`
- Scope with `--resource-id` per service, or omit it to list all scheduled actions in the `ecs` namespace and map entries back to services via `ResourceId`

---

## Output Schema

```yaml
autoscaling:
  services:
    - service_name: string
      configured: bool            # true if scalable target exists, false otherwise
      scalable_target:            # null if configured is false
        min_capacity: int         # >= 0
        max_capacity: int         # >= 0
        resource_id: string       # "service/{cluster}/{service}"
      suspended_state:            # null if configured is false
        dynamic_scaling_in_suspended: bool
        dynamic_scaling_out_suspended: bool
        scheduled_scaling_suspended: bool
      scaling_policies:           # empty list if no policies, null if configured is false
        - policy_name: string
          policy_type: string     # "target_tracking" | "step_scaling" | "predictive_scaling" | "unrecognized"
          # For target_tracking:
          target_metric: string | null    # e.g., "ECSServiceAverageCPUUtilization"
          target_value: float | null
          # For step_scaling:
          step_adjustments: list[StepAdjustment] | null
      scheduled_actions:          # empty list if no scheduled actions, null if configured is false
        - name: string            # ScheduledActionName
          schedule: string        # at(...) | cron(...) | rate(...) expression
          min_capacity: int | null  # ScalableTargetAction.MinCapacity (null if not set by the action)
          max_capacity: int | null  # ScalableTargetAction.MaxCapacity (null if not set by the action)
      error: string | null        # Failing API call + error code for this service; null otherwise

# Supporting type
StepAdjustment:
  lower_bound: float | null       # MetricIntervalLowerBound (null = negative infinity)
  upper_bound: float | null       # MetricIntervalUpperBound (null = positive infinity)
  scaling_adjustment: int         # Number of tasks to add/remove
```

---

## Policy Type Classification

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/autoscaling/application/APIReference/API_ScalingPolicy.html (PolicyType enum: StepScaling | TargetTrackingScaling | PredictiveScaling) and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/predictive-auto-scaling.html

Map the raw API response value to the standardized output value:

| API Response `PolicyType` | Output `policy_type` |
|---------------------------|---------------------|
| `"TargetTrackingScaling"` | `"target_tracking"` |
| `"StepScaling"` | `"step_scaling"` |
| `"PredictiveScaling"` | `"predictive_scaling"` |
| Any other value | `"unrecognized"` |

**Classification logic:**
```
if policy.PolicyType == "TargetTrackingScaling":
    policy_type = "target_tracking"
    target_metric = policy.TargetTrackingScalingPolicyConfiguration
                         .PredefinedMetricSpecification.PredefinedMetricType
                    OR policy.TargetTrackingScalingPolicyConfiguration
                         .CustomizedMetricSpecification.MetricName
    target_value = policy.TargetTrackingScalingPolicyConfiguration.TargetValue
    step_adjustments = null

elif policy.PolicyType == "StepScaling":
    policy_type = "step_scaling"
    target_metric = null
    target_value = null
    step_adjustments = [
        {
            lower_bound: step.MetricIntervalLowerBound or null,
            upper_bound: step.MetricIntervalUpperBound or null,
            scaling_adjustment: step.ScalingAdjustment
        }
        for step in policy.StepScalingPolicyConfiguration.StepAdjustments
    ]

elif policy.PolicyType == "PredictiveScaling":
    policy_type = "predictive_scaling"
    target_metric = null
    target_value = null
    step_adjustments = null
    # Forecast/metric details live in PredictiveScalingPolicyConfiguration;
    # report the policy_name so the user can inspect the full configuration

else:
    policy_type = "unrecognized"
    target_metric = null
    target_value = null
    step_adjustments = null
```

**Target metric extraction:**
- For predefined metrics: use `PredefinedMetricSpecification.PredefinedMetricType` (e.g., `ECSServiceAverageCPUUtilization`, `ECSServiceAverageMemoryUtilization`, `ALBRequestCountPerTarget`)
- For custom metrics: use `CustomizedMetricSpecification.MetricName`
- If neither is present (unexpected): report `target_metric: null`

---

## Edge Cases

Handle these special scenarios to provide accurate auto scaling reporting.

### No Scaling Configured

When `DescribeScalableTargets` returns an empty `ScalableTargets` list, the service has no Application Auto Scaling configured.

**What to expect:**
- Empty response from the scalable targets API
- No need to query scaling policies

**How to handle:**
- Report `configured: false`
- Report `scalable_target: null`
- Report `suspended_state: null`
- Report `scaling_policies: null`
- Report `scheduled_actions: null`
- This is a valid state — many services run at a fixed task count

### Target Tracking vs Step Scaling

A service can have multiple scaling policies of different types simultaneously (e.g., a target tracking policy for CPU and a step scaling policy for a custom metric).

**How to handle:**
- Report each policy individually with its own classification
- A target tracking policy will have `target_metric` and `target_value` filled in
- A step scaling policy will have `step_adjustments` filled in
- Both types can coexist on the same service and scalable target

### Unrecognized Policy Types

AWS may introduce new scaling policy types beyond the three recognized ones (as of 2026-07-14: `TargetTrackingScaling`, `StepScaling`, and `PredictiveScaling` — predictive scaling for ECS launched in December 2024).

**What to expect:**
- A `PolicyType` value that is not `"TargetTrackingScaling"`, `"StepScaling"`, or `"PredictiveScaling"`

**How to handle:**
- Report `policy_type: "unrecognized"`
- Set `target_metric: null`, `target_value: null`, `step_adjustments: null`
- Include the `policy_name` so the user can investigate manually
- Do not fail the entire module for an unrecognized type

### Permission Errors on application-autoscaling

The `application-autoscaling` APIs require separate IAM permissions from `ecs` APIs. A user may have ECS permissions but lack auto scaling permissions.

**What to expect:**
- `AccessDeniedException` when calling `DescribeScalableTargets`, `DescribeScalingPolicies`, or `DescribeScheduledActions`
- Other ECS modules will still work correctly

**How to handle:**
- Record the failure on the affected service's `error` field (failing API + error code) and continue with the remaining services — never discard already-collected data
- Use module-level `unavailable: true` ONLY for total failure (e.g., the first `DescribeScalableTargets` call fails before any per-service data was gathered)
- Continue reconnaissance of remaining services and modules without terminating
- Do not report `configured: false` — the absence of permissions does not mean scaling is not configured; leave `configured` unset/null and rely on the `error` field

### Custom Metric in Target Tracking

Target tracking policies can use custom CloudWatch metrics instead of predefined ECS metrics.

**What to expect:**
- `CustomizedMetricSpecification` instead of `PredefinedMetricSpecification` in the policy configuration
- Custom metrics have a `MetricName`, `Namespace`, `Statistic`, and optionally `Dimensions`

**How to handle:**
- Extract `MetricName` from `CustomizedMetricSpecification` as the `target_metric`
- The `target_value` still comes from `TargetValue`
- Report the metric name as-is (do not attempt to map it to a predefined metric)

### Scalable Target with No Policies

A scalable target can exist without any associated scaling policies. This means auto scaling infrastructure is registered but no dynamic scaling behavior is defined — the service may still be actively scaled on a schedule.

**What to expect:**
- `DescribeScalableTargets` returns a target with min/max capacity
- `DescribeScalingPolicies` returns an empty list
- `DescribeScheduledActions` may still return scheduled actions

**How to handle:**
- Report `configured: true` (a scalable target exists)
- Report the `scalable_target` with `min_capacity` and `max_capacity`
- Report `scaling_policies: []` (empty list, not null)
- Always run Step 3 (`describe-scheduled-actions`) for this state — scheduled scaling without dynamic policies is a common pattern, and reporting `scaling_policies: []` alone would hide the active time-based scaling
- If scheduled actions exist, populate `scheduled_actions`; if none, report `scheduled_actions: []` — then the target was likely retained after policies were deleted

### Suspended Scaling Actions

A scalable target can have its scaling actions temporarily suspended without being deregistered.

**What to expect:**
- `SuspendedState` in the scalable target response with `DynamicScalingInSuspended`, `DynamicScalingOutSuspended`, or `ScheduledScalingSuspended` set to `true`

**How to handle:**
- Report `configured: true` (scaling is still configured, just paused)
- Populate the `suspended_state` schema field from the response (`dynamic_scaling_in_suspended`, `dynamic_scaling_out_suspended`, `scheduled_scaling_suspended`) so a suspended target is distinguishable from an active one — do not report suspended and active targets identically
- The min/max capacity and policies still apply when scaling resumes
- This is a normal operational state during maintenance windows or investigations

### Multiple Services in One Query

You can query scalable targets for multiple services in a single API call by providing multiple resource IDs.

**How to handle:**
- Batch resource IDs when querying multiple services: `--resource-ids "service/cluster/svc1" "service/cluster/svc2"`
- **Batch limit:** `DescribeScalableTargets` accepts a maximum of **50 resource IDs per call**. For more than 50 services, batch resource IDs into groups of 50.
- Map each returned scalable target back to its service using the `ResourceId` field
- Services with no matching target in the response have `configured: false`

---

## Sources

- ScalingPolicy API shape and `PolicyType` enum (StepScaling | TargetTrackingScaling | PredictiveScaling): https://docs.aws.amazon.com/autoscaling/application/APIReference/API_ScalingPolicy.html
- Predictive scaling for Amazon ECS services (available since December 2024): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/predictive-auto-scaling.html
- DescribeScalableTargets request limits (max 50 resource IDs per call) and `SuspendedState`: https://docs.aws.amazon.com/autoscaling/application/APIReference/API_DescribeScalableTargets.html
- DescribeScheduledActions API (schedule expressions, `ScalableTargetAction`): https://docs.aws.amazon.com/autoscaling/application/APIReference/API_DescribeScheduledActions.html
- Scheduled scaling for Application Auto Scaling: https://docs.aws.amazon.com/autoscaling/application/userguide/application-auto-scaling-scheduled-scaling.html
