# Service Auto Scaling

> **Part of:** [ecs-build](../SKILL.md)

Application Auto Scaling for ECS services. Cluster-level capacity scaling (managed scaling on ASG providers, MI decision logic) lives in [capacity-provider-guide.md](capacity-provider-guide.md) -- this file is task-count scaling.

> Facts verified 2026-07-10 against https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html

## Scalable target

```hcl
resource "aws_appautoscaling_target" "this" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 2
  max_capacity       = 20
}
```

The module's service submodule creates this by default (min 1 / max 10, CPU + memory target tracking at 75%) -- override rather than duplicate.

## desired_count and autoscaling never coexist in plans

- **Module path:** the service submodule **unconditionally ignores `desired_count` drift** -- `lifecycle { ignore_changes = [desired_count] }` is hardcoded on both service resource variants with no opt-out variable. Corollary: changing the module's `desired_count` input never changes the running task count directly, but it can still widen the scalable-target bounds via the module's `min(autoscaling_min_capacity, desired_count)` / `max(autoscaling_max_capacity, desired_count)` clamp -- prefer autoscaling `min_capacity`/`max_capacity` as the single source of truth. Source: https://github.com/terraform-aws-modules/terraform-aws-ecs/blob/master/modules/service/main.tf (verified 2026-07-10).
- **Raw path:** on any autoscaled `aws_ecs_service`, generate `lifecycle { ignore_changes = [desired_count] }` yourself, per the provider docs' "Ignoring Changes to Desired Count" section (https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service) -- otherwise every plan fights Application Auto Scaling's runtime changes.

## Target tracking (default choice)

Predefined metrics for ECS:

- `ECSServiceAverageCPUUtilization`
- `ECSServiceAverageMemoryUtilization`
- `ALBRequestCountPerTarget` -- requires `resource_label` tying the ALB and target group (`app/<lb-name>/<lb-id>/targetgroup/<tg-name>/<tg-id>`). **Not supported for the blue/green deployment type** (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html) -- never generate it for BLUE_GREEN/LINEAR/CANARY services.

```hcl
resource "aws_appautoscaling_policy" "cpu" {
  name               = "<service>-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 60
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
```

- **High-resolution (20-second) variants** `ECSServiceAverageCPUUtilizationHighResolution` / `ECSServiceAverageMemoryUtilizationHighResolution` exist but require the service's `monitoring` metricConfigurations at `resolutionSeconds=20` first (new revision + deployment), are ALB/NLB services only, and are unsupported with `CODE_DEPLOY`/`EXTERNAL` controllers. Verify current Terraform provider support for the service `monitoring` block before generating -- as of the 2026-07-10 research pass, provider exposure of that block was unconfirmed; if absent, generate standard-resolution policies and note the limitation.

## SQS workers: backlog per task, never raw queue depth

Raw target tracking on `ApproximateNumberOfMessagesVisible` misbehaves (queue depth does not fall proportionally as tasks scale). Generate the **backlog-per-task** pattern:

1. Publish a custom metric `backlog_per_task = ApproximateNumberOfMessagesVisible / running task count` (Lambda or metric math).
2. Target-track on it with `customized_metric_specification`, target = `acceptable_latency_seconds * messages_per_task_per_second`.
3. Alternative for spiky queues: step scaling on queue depth bands.

Pair with graceful SIGTERM handling within `stopTimeout` (<= 120s on Fargate) so scale-in does not drop in-flight messages.

## Scheduled scaling

`aws_appautoscaling_scheduled_action` for predictable diurnal load -- set `min_capacity`/`max_capacity` per schedule window; combine with target tracking inside the window.

## Sources

- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-faster-auto-scaling.html
- https://github.com/terraform-aws-modules/terraform-aws-ecs/blob/master/modules/service/README.md
- Backlog-per-task pattern: aws/agent-toolkit-for-aws `aws-containers` skill, Gotcha 16 (Apache-2.0, retrieved 2026-07-10)
