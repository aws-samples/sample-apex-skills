# Baseline Defaults

> **Part of:** [ecs-build](../SKILL.md)

Opinionated defaults applied to every generated ECS project. Deviate only when the user explicitly asks, and note the deviation in `validation-checklist.md`.

> Facts verified 2026-07-10 against https://github.com/terraform-aws-modules/terraform-aws-ecs (cluster/service/container-definition submodule READMEs), https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html, and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service-options.html

## Cluster

- **Container Insights: enabled.** The `terraform-aws-modules/ecs` cluster submodule already defaults to `setting = [{ name = "containerInsights", value = "enabled" }]` -- keep it. For GPU telemetry on Managed Instances, use enhanced observability (`value = "enhanced"`); basic Container Insights does not collect GPU metrics.
- **Execute-command logging:** if ECS Exec is enabled, configure `configuration.execute_command_configuration` with KMS key and CloudWatch log group so Exec sessions are audited.
- One cluster per environment (dev/staging/prod), never per service.

## Task definitions

- **CPU architecture:** default `ARM64` (Graviton) for Linux services unless the image is x86-only -- state the assumption in the README. Windows requires `X86_64`.
- **Logging:** awslogs with an **explicit `mode`** (Critical Rule 4). Default `"non-blocking"` with `"max-buffer-size": "25m"`; use `"blocking"` only when the user states audit-grade log delivery outranks task availability. The container-definition submodule auto-creates the log group with 14-day retention (`cloudwatch_log_group_retention_in_days = 14` in modules/container-definition/variables.tf, verified 2026-07-10) -- override retention per compliance need.
- **`readonlyRootFilesystem = true`** (submodule default: `variable "readonlyRootFilesystem"` `default = true` in modules/container-definition/variables.tf, verified 2026-07-10) -- relax per-container only where ECS Exec or the app requires writes (Critical Rule 12).
- **Roles:** always separate execution role and task role (Critical Rule 5). Never attach app permissions to the execution role.
- **Health checks:** every container behind a load balancer or a `dependsOn` `HEALTHY` condition gets a container health check. A `HEALTHY` dependency on a container without a health check blocks startup forever.
- **stopTimeout:** set explicitly for workers that need graceful SIGTERM handling (max 120s on Fargate).
- **Image references:** immutable tags or digests; never `latest` in production code.

## Services

- **Circuit breaker / failure detection:** rolling gets the circuit breaker, blue/green-family gets bake time + `alarms` -- rules and HCL in [service-and-deployment.md](service-and-deployment.md).
- **`health_check_grace_period_seconds`:** 60-120s for slow-starting runtimes (JVM); 30s default otherwise.
- **ALB target groups:** `deregistration_delay = 30`-60 (down from the 300s default) to speed deployments.
- **`availability_zone_rebalancing`:** leave `ENABLED` -- ECS defaults it to `ENABLED` for create-service requests (https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html, verified 2026-07-10; update requests keep the existing value).
- **Service Connect** for service-to-service traffic (Critical Rule 7); one Cloud Map namespace per environment.
- **Module service submodule defaults** -- min 1 / max 10 autoscaling with CPU+memory target tracking at 75% (`autoscaling_min_capacity = 1`, `autoscaling_max_capacity = 10`, `autoscaling_policies` cpu+memory with `target_value` defaulting to 75 in modules/service/variables.tf, verified 2026-07-10) -- acceptable starting points; tune per [autoscaling.md](autoscaling.md).

## Networking

- `awsvpc` network mode for all task definitions this skill generates (mandatory on Fargate; the consistent choice on EC2/MI).
- Tasks in **private subnets**, `assign_public_ip = false`; image pulls via VPC endpoints or NAT (see [networking-security.md](networking-security.md)).
- One security group per service; ingress only from the LB security group or Service Connect peers.

## Tagging

- Provider `default_tags` with at minimum: `Project`, `Environment`, `ManagedBy = "terraform"`.
- Capacity providers: set `propagate_tags` deliberately (`CAPACITY_PROVIDER` for MI providers; `TASK_DEFINITION` or `SERVICE` on services).

## State and versions

- Remote state via `configs/backend.hcl` (S3 backend with lockfile or DynamoDB locking per org standard).
- Terraform >= 1.5.7 and AWS provider >= 6.34 are the module floor as of 2026-07-10 -- always re-check per [version-matrix.md](version-matrix.md).

## Sources

- https://github.com/terraform-aws-modules/terraform-aws-ecs -- submodule defaults verified in modules/service/variables.tf and modules/container-definition/variables.tf (retrieved 2026-07-10)
- https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html (availabilityZoneRebalancing default) · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html (defaultLogDriverMode)
- Deregistration delay / grace period / circuit-breaker hygiene: aws/agent-toolkit-for-aws `aws-containers` skill, Gotchas 5-7 -- https://github.com/aws/agent-toolkit-for-aws/blob/main/skills/core-skills/aws-containers/SKILL.md (Apache-2.0, retrieved 2026-07-10)
