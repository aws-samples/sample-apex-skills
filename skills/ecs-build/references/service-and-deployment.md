# Service and Deployment

> **Part of:** [ecs-build](../SKILL.md)

How to generate `aws_ecs_service` (or the module's service submodule) with the right deployment configuration. Strategy *selection* and pipeline wiring belong to `ecs-devops` -- this file covers rendering the Terraform for a strategy that is already chosen.

> Facts verified 2026-07-10 against https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html

## Deployment controller and strategies

- `deployment_controller.type`: `ECS` (default -- generate this), `CODE_DEPLOY` (this skill generates native strategies instead; the CodeDeploy controller remains AWS-supported -- house rule, not deprecation), `EXTERNAL` (own tooling -- out of scope).
- Under the `ECS` controller, `deployment_configuration.strategy` selects: `ROLLING` (default) | `BLUE_GREEN` | `LINEAR` | `CANARY` -- all native, no CodeDeploy resources.
- **Managed traffic shifting requires ALB, NLB, or Service Connect.** For headless services (no LB/Service Connect), BLUE_GREEN replaces blue tasks with green tasks but does NOT manage traffic shifting (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html) -- usually not what the user wants; confirm before generating, default to ROLLING.
- As of 2026-07-10, **NLB is supported for blue/green, linear and canary** (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/nlb-resources-for-blue-green.html -- note NLB adds a 10-minute delay to the TEST/PRODUCTION_TRAFFIC_SHIFT stages). The CreateService API-reference text still lists only ALB/Service Connect for linear/canary -- it is stale; the dev guide wins.
- All strategies work on Fargate, EC2, and Managed Instances capacity.

### Rolling

```hcl
deployment_minimum_healthy_percent = 100
deployment_maximum_percent         = 200

deployment_circuit_breaker {
  enable   = true
  rollback = true
}
```

- Circuit breaker is **rolling-only** -- never combine with BLUE_GREEN/LINEAR/CANARY.
- min 100 / max 200 gives zero-downtime at any desired count (incl. desiredCount=1), at the cost of 2x burst capacity -- headroom on EC2, spend on Fargate/MI.

### Blue/green family

```hcl
deployment_configuration {
  strategy             = "BLUE_GREEN"      # or "LINEAR" / "CANARY"
  bake_time_in_minutes = 15                 # 0-1440; REQUIRED when strategy = BLUE_GREEN
                                            # (API_DeploymentConfiguration.html); both revisions run through bake

  # LINEAR only:
  # linear_configuration { step_percent = 20.0, step_bake_time_in_minutes = 10 }
  # step_percent valid range 3.0-100.0

  # CANARY only:
  # canary_configuration { canary_percent = 10.0, canary_bake_time_in_minutes = 30 }

  # Optional lifecycle hooks -- target types AWS_LAMBDA (default) or PAUSE. Stages:
  # RECONCILE_SERVICE, PRE_SCALE_UP, POST_SCALE_UP, TEST_TRAFFIC_SHIFT,
  # POST_TEST_TRAFFIC_SHIFT, PRE_PRODUCTION_TRAFFIC_SHIFT,
  # PRODUCTION_TRAFFIC_SHIFT, POST_PRODUCTION_TRAFFIC_SHIFT
  # PAUSE hooks are NOT allowed at TEST_TRAFFIC_SHIFT / PRODUCTION_TRAFFIC_SHIFT
  # (AWS_LAMBDA only there); PRE_PRODUCTION_TRAFFIC_SHIFT fires before every
  # linear/canary shift step. (API_DeploymentLifecycleHook.html)
  # lifecycle_hook { hook_target_arn = ..., role_arn = ..., lifecycle_stages = [...] }
}
```

- `canary_configuration` is required when strategy=CANARY; `linear_configuration` when strategy=LINEAR.
- ALB/NLB blue/green needs the alternate-target-group plumbing: a production listener rule with two weighted target groups, plus per-`load_balancer` `advanced_configuration` (`alternate_target_group_arn`, `production_listener_rule`, optional `test_listener_rule`, and a role carrying `AmazonECSInfrastructureRolePolicyForLoadBalancers`). The module service submodule supports alternate target groups + listener rules for this.
- Both revisions run simultaneously until cleanup -- plan for up to 2x capacity during the deployment.
- **Failure detection on blue/green-family:** use the `alarms { alarm_names, enable, rollback }` block (works with any strategy under the `ECS` controller) plus bake time; NOT the circuit breaker.
- Autoscaling caveat: `ALBRequestCountPerTarget` target tracking is not compatible with the blue/green deployment type -- re-check https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html before combining (see [autoscaling.md](autoscaling.md)).

## Load balancing

- Service `load_balancer { target_group_arn, container_name, container_port }`; target group `target_type = "ip"` for awsvpc tasks.
- Target group hygiene (see [baseline-defaults.md](baseline-defaults.md)): `deregistration_delay` 30-60s, health check path/matcher explicit, `health_check_grace_period_seconds` on the service for slow starters.
- Both target groups referenced by blue/green listener rules must actually be associated with the listener, or deployments fail with an invalid-networking-configuration rollback.

## Service Connect (Critical Rule 7)

App Mesh reaches end of support 2026-09-30 (https://docs.aws.amazon.com/app-mesh/latest/userguide/what-is-app-mesh.html, verified 2026-07-10) -- never generate App Mesh. Generate Service Connect for service-to-service:

```hcl
service_connect_configuration {
  enabled   = true
  namespace = aws_service_discovery_http_namespace.this.arn

  service {
    port_name      = "http"           # must match a named portMapping
    discovery_name = "<service>"
    client_alias {
      port     = 80
      dns_name = "<service>"
    }
  }

  log_configuration { ... }            # give the Envoy proxy its own log stream
}
```

- One Cloud Map namespace per environment; a namespace can span clusters in a Region and be RAM-shared.
- The Envoy proxy is ECS-managed at no extra charge beyond its vCPU/memory; size task CPU/memory to include it.
- TLS via AWS Private CA uses the infrastructure role with `AmazonECSInfrastructureRolePolicyForServiceConnectTransportLayerSecurity` (5-day automatic rotation).
- Consumers outside the namespace (or non-ECS) cannot resolve Service Connect endpoints -- give them an ALB or classic Cloud Map `service_registries` instead.
- Launch-type scoping: Service Connect needs Fargate Linux platform >= 1.4.0, or ECS agent >= 1.67.2 on EC2. It is not available on ECS Anywhere.

## Express services (distinct generation path)

Verified 2026-07-10; availability and delegation model per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html:

- Generate via the upstream `modules/express-service` submodule (wraps `aws_ecs_express_gateway_service`; in the module since v7.2.0).
- **Different paradigm:** ECS creates and manages the ALB, ACM certificate, autoscaling and CloudWatch resources itself via an infrastructure role carrying the `AmazonECSInfrastructureRoleforExpressGatewayServices` managed policy (policy name per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html). Those resources are **NOT in Terraform state** -- `terraform plan` won't show them and `terraform destroy` won't remove them directly; ECS owns their lifecycle. Scope this role deliberately: it grants ECS broad resource-creation rights (ELB, EC2 security groups, ACM, Application Auto Scaling) on your behalf.
- Constraints: a single traffic-serving `Main` (primary) container with one TCP port; sidecars are permitted via the custom-task-definition path (`taskDefinitionArn`); Fargate-only, HTTP(S) workloads, built-in canary traffic shifting (https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateExpressGatewayService.html). ALBs are shared across Express services with the same networking configuration.
- **Prefer over full service generation** for simple stateless web apps/APIs where the user wants minimal Terraform surface; use the full path when they need custom listener rules, non-HTTP protocols, multi-container tasks, EC2/MI capacity, or explicit control of the LB in state.

## Daemons (per-instance agents)

Two mechanisms, by capacity model (verified 2026-07-10):

- **ECS Managed Daemons (June 2026, Managed Instances only):** dedicated `CreateDaemon` API -- one daemon task per MI-provisioned instance, started before application tasks, auto-repair (instance drained/replaced if the daemon stops), rolling `drainPercent`/`bakeTimeInMinutes` deployments. Generate with the provider's `aws_ecs_daemon` + `aws_ecs_daemon_task_definition` resources (provider >= 6.50.0; daemon references `cluster_arn`, `daemon_task_definition_arn`, `capacity_provider_arns`). Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-daemons-deployments.html.
- **Classic `scheduling_strategy = "DAEMON"` on `aws_ecs_service`, EC2 launch type:** one task per container instance meeting the placement constraints; no `desired_count`, no placement strategy, no service autoscaling; `maximumPercent` must be 100. Not supported on Fargate or with `CODE_DEPLOY`/`EXTERNAL` controllers (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html). For MI, the dev guide positions Managed Daemons as the daemon mechanism -- classic DAEMON services on MI are not documented as supported as of 2026-07-10; verify live before generating.
- When each applies: Managed Daemons for agents on MI capacity; classic DAEMON for agents on self-managed EC2 ASG capacity; Fargate gets per-task sidecars only.

## Other service arguments worth generating deliberately

- `enable_execute_command = true` only when the user wants ECS Exec -- it drags in `ssmmessages` endpoint + task-role permissions + writable-filesystem implications (Critical Rules 8, 12).
- `propagate_tags = "SERVICE"` (or `TASK_DEFINITION`) so tasks inherit cost-allocation tags.
- `force_new_deployment` stays out of generated code -- it is an operational knob, not configuration.
- `wait_for_steady_state = true` on the module makes `terraform apply` block until the deployment settles -- good default for CI-applied projects.

## Sources

- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-linear.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/nlb-resources-for-blue-green.html
- https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html · https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentLifecycleHook.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html · https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateExpressGatewayService.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html · https://github.com/terraform-aws-modules/terraform-aws-ecs/tree/master/modules/express-service
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-daemons.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-daemons-deployments.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect.html · https://docs.aws.amazon.com/app-mesh/latest/userguide/what-is-app-mesh.html
- https://github.com/terraform-aws-modules/terraform-aws-ecs/blob/master/modules/service/README.md
- Zero-downtime min/max and LB hygiene framing: aws/agent-toolkit-for-aws `aws-containers` skill (Apache-2.0, retrieved 2026-07-10)
