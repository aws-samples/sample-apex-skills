# Module: Auto Scaling

> **Part of:** [ecs-recon](../SKILL.md)
> **Purpose:** Discover Application Auto Scaling configuration for ECS services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Scalable Targets](#1-scalable-targets)
  - [Scaling Policies](#2-scaling-policies)
- [Output Schema](#output-schema)
- [Policy Type Classification](#policy-type-classification)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Service name(s) required:** Yes
- **Cluster name required:** Yes
- **APIs used:** `application-autoscaling:DescribeScalableTargets`, `application-autoscaling:DescribeScalingPolicies`
- **CLI commands:** `aws application-autoscaling describe-scalable-targets`, `aws application-autoscaling describe-scaling-policies`
- **IAM permissions:** `application-autoscaling:DescribeScalableTargets`, `application-autoscaling:DescribeScalingPolicies` (read-only)

---

## Detection Strategy

Application Auto Scaling for ECS operates on resource IDs in the format `service/{cluster-name}/{service-name}`. Detection is a two-step process: first check whether a scalable target is registered (indicating auto scaling is configured), then retrieve the scaling policies that define how scaling behaves.

Run detection in this order:

```
1. Build Resource ID       -> Construct "service/{cluster}/{service}" for each service
2. Describe Scalable Targets -> Check if auto scaling is configured for each service
3. Describe Scaling Policies -> Get policy details for services that have scalable targets
```

**Why this order matters:**
- The resource ID format is fixed for ECS (`service/{cluster}/{service}`) and must be constructed before querying
- If no scalable target exists, the service has no auto scaling configured — skip the policies query
- Scaling policies reference the scalable target, so targets must be confirmed first
- Querying policies for a service without a scalable target returns an empty list (wasted API call)

---

## Detection Commands

### 1. Scalable Targets

Determine whether Application Auto Scaling is configured for ECS services. A scalable target defines the min/max capacity boundaries for auto scaling.

**MCP (future):**
```
application_autoscaling_describe_scalable_targets(
  service_namespace="ecs",
  resource_ids=["service/<cluster-name>/<service-name>"]
)
-> Check response for ScalableTargets[]
```

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

**MCP (future):**
```
application_autoscaling_describe_scaling_policies(
  service_namespace="ecs",
  resource_id="service/<cluster-name>/<service-name>"
)
-> Check response for ScalingPolicies[]
```

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
      scaling_policies:           # empty list if no policies, null if configured is false
        - policy_name: string
          policy_type: string     # "target_tracking" | "step_scaling" | "unrecognized"
          # For target_tracking:
          target_metric: string | null    # e.g., "ECSServiceAverageCPUUtilization"
          target_value: float | null
          # For step_scaling:
          step_adjustments: list[StepAdjustment] | null

# Supporting type
StepAdjustment:
  lower_bound: float | null       # MetricIntervalLowerBound (null = negative infinity)
  upper_bound: float | null       # MetricIntervalUpperBound (null = positive infinity)
  scaling_adjustment: int         # Number of tasks to add/remove
```

---

## Policy Type Classification

Map the raw API response value to the standardized output value:

| API Response `PolicyType` | Output `policy_type` |
|---------------------------|---------------------|
| `"TargetTrackingScaling"` | `"target_tracking"` |
| `"StepScaling"` | `"step_scaling"` |
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
- Report `scaling_policies: null`
- This is a valid state — many services run at a fixed task count

### Target Tracking vs Step Scaling

A service can have multiple scaling policies of different types simultaneously (e.g., a target tracking policy for CPU and a step scaling policy for a custom metric).

**How to handle:**
- Report each policy individually with its own classification
- A target tracking policy will have `target_metric` and `target_value` filled in
- A step scaling policy will have `step_adjustments` filled in
- Both types can coexist on the same service and scalable target

### Unrecognized Policy Types

AWS may introduce new scaling policy types in the future (e.g., predictive scaling for ECS is not currently available but may be added).

**What to expect:**
- A `PolicyType` value that is not `"TargetTrackingScaling"` or `"StepScaling"`

**How to handle:**
- Report `policy_type: "unrecognized"`
- Set `target_metric: null`, `target_value: null`, `step_adjustments: null`
- Include the `policy_name` so the user can investigate manually
- Do not fail the entire module for an unrecognized type

### Permission Errors on application-autoscaling

The `application-autoscaling` APIs require separate IAM permissions from `ecs` APIs. A user may have ECS permissions but lack auto scaling permissions.

**What to expect:**
- `AccessDeniedException` when calling `DescribeScalableTargets` or `DescribeScalingPolicies`
- Other ECS modules will still work correctly

**How to handle:**
- Report an error indicating that auto scaling configuration could not be retrieved due to insufficient permissions
- Continue reconnaissance of remaining services and modules without terminating
- Include the specific API that failed in the error message
- Do not report `configured: false` — the absence of permissions does not mean scaling is not configured

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

A scalable target can exist without any associated scaling policies. This means auto scaling infrastructure is registered but no automatic scaling behavior is defined.

**What to expect:**
- `DescribeScalableTargets` returns a target with min/max capacity
- `DescribeScalingPolicies` returns an empty list

**How to handle:**
- Report `configured: true` (a scalable target exists)
- Report the `scalable_target` with `min_capacity` and `max_capacity`
- Report `scaling_policies: []` (empty list, not null)
- This state can occur when scheduled scaling is used without dynamic policies, or when policies were deleted but the target was retained

### Suspended Scaling Actions

A scalable target can have its scaling actions temporarily suspended without being deregistered.

**What to expect:**
- `SuspendedState` in the scalable target response with `DynamicScalingInSuspended`, `DynamicScalingOutSuspended`, or `ScheduledScalingSuspended` set to `true`

**How to handle:**
- Report `configured: true` (scaling is still configured, just paused)
- The min/max capacity and policies still apply when scaling resumes
- This is a normal operational state during maintenance windows or investigations

### Multiple Services in One Query

You can query scalable targets for multiple services in a single API call by providing multiple resource IDs.

**How to handle:**
- Batch resource IDs when querying multiple services: `--resource-ids "service/cluster/svc1" "service/cluster/svc2"`
- Map each returned scalable target back to its service using the `ResourceId` field
- Services with no matching target in the response have `configured: false`
