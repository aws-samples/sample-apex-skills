# Capacity Provider Guide

> **Part of:** [ecs-build](../SKILL.md)

How to wire each capacity model in Terraform, and the constraints that break strategies.

> Facts verified 2026-07-10 against https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_capacity_provider, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html, and https://github.com/terraform-aws-modules/terraform-aws-ecs/blob/master/examples/managed-instances/main.tf

## Universal rules

1. **`launch_type` and `capacity_provider_strategy` are mutually exclusive** on a service. Generated services use strategies; never emit both.
2. **One provider TYPE per strategy** (MI, ASG, or Fargate/Fargate Spot). A cluster can hold all types; a strategy cannot mix them.
3. **Only one capacity provider in a strategy may have a `base` defined** (https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CapacityProviderStrategyItem.html).
4. **Migration is in-place via UpdateService** (in Terraform: change the service arguments; no resource replacement needed): launch type -> any capacity provider type, and any provider type -> any other provider type, are supported. Provider -> launch type is NOT supported, except reverting to the service's original launch type by passing an empty strategy. For MI targets, the task definition must first add `MANAGED_INSTANCES` to `requires_compatibilities` or the update fails validation. Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html (verified 2026-07-10).

## Fargate + FARGATE_SPOT

`FARGATE` and `FARGATE_SPOT` are AWS-managed capacity providers -- no `aws_ecs_capacity_provider` resource. Associate them with the cluster and express the mix in the strategy. On-demand base + Spot overflow:

```hcl
# terraform-aws-modules/ecs cluster submodule
default_capacity_provider_strategy = {
  FARGATE = {
    base   = 2   # steady-state floor on on-demand
    weight = 1
  }
  FARGATE_SPOT = {
    weight = 4   # overflow goes 4:1 to Spot
  }
}
```

- Spot tasks get a SIGTERM + 2-minute interruption notice -- ensure `stopTimeout` and graceful shutdown handling in the task definition.
- Never write `launch_type = "FARGATE_SPOT"` (Critical Rule 1).

## EC2 -- Auto Scaling group capacity providers

Wrap an ASG in `aws_ecs_capacity_provider` (or the cluster submodule's `capacity_providers` map with an `auto_scaling_group_provider` object):

```hcl
resource "aws_ecs_capacity_provider" "ec2" {
  name = "<name>"

  auto_scaling_group_provider {
    auto_scaling_group_arn         = aws_autoscaling_group.this.arn
    managed_termination_protection = "ENABLED"
    managed_draining               = "ENABLED"

    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 100  # or <100 for headroom
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 10
      instance_warmup_period    = 300
    }
  }
}
```

- `managed_termination_protection = "ENABLED"` requires the ASG itself to have `protect_from_scale_in = true`.
- `managed_draining` gracefully drains instances on instance refresh, max-lifetime replacement, scale-in, and Spot interruption/rebalance.
- ASG uses the ECS-optimized AMI (resolve via SSM parameter, see [version-matrix.md](version-matrix.md)) and an instance profile with the container-instance role (`AmazonEC2ContainerServiceforEC2Role`) -- distinct from execution/task roles.

### Mixed instance types: supported but constrained (Critical Rule 11)

Verified 2026-07-10 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html:

- Cluster auto scaling supports multiple instance types and attribute-based selection, **but instance weights are not supported** ("Specifying a weight isn't supported at this time") -- place larger types higher in the priority list, no weights.
- The scale-out estimate binpacks against the ASG's instance-type parameters and **protects on the smallest type**: a task group whose requirements exceed the smallest instance type is excluded from scale-out and remains in `PROVISIONING`.
- **Best practice: separate homogeneous ASGs + capacity providers per minimum-resource class** (AWS's own recommendation on that page). "Managed scaling works best if your Auto Scaling group uses the same or similar instance types."

### EC2 task placement (services on ASG providers)

With no strategy specified, EC2 **standalone tasks place randomly** and EC2 **service** tasks default to AZ spread; generate placement explicitly for EC2 services (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement.html, verified 2026-07-10). MI does not support placement strategies (constraints only) -- ECS spreads across AZs itself; Fargate has neither.

- `ordered_placement_strategy` -- order matters, the first entry is applied first: `spread` on `attribute:ecs.availability-zone` for HA, then `binpack` on `cpu` or `memory` for cost (fills instances before scale-out). Max 5 entries.
- `placement_constraints` -- `memberOf` with a Cluster Query Language expression (e.g. instance type/attribute), or `distinctInstance` (one task per instance; not valid in task definitions, service-level only).

```hcl
# aws_ecs_service (EC2 services)
ordered_placement_strategy {
  type  = "spread"
  field = "attribute:ecs.availability-zone"
}
ordered_placement_strategy {
  type  = "binpack"
  field = "memory"
}
placement_constraints {
  type       = "memberOf"
  expression = "attribute:ecs.instance-type =~ m5.*"
}
```

## Managed Instances (MI)

MI is configured on `aws_ecs_capacity_provider` via `managed_instances_provider` -- no separate resource. Constraints (provider docs, verified 2026-07-10):

- `managed_instances_provider` is **mutually exclusive with `auto_scaling_group_provider`** in one resource.
- The top-level **`cluster` argument is REQUIRED** for MI providers (and prohibited for ASG providers).
- MI task definitions must include `MANAGED_INSTANCES` in `requires_compatibilities` (combinable with `FARGATE`; MI is compatible with Fargate PV 1.4.0 task definitions).

### Full raw-HCL wiring

```hcl
# 1. Infrastructure role — trusted by ecs.amazonaws.com (NOT ecs-tasks)
resource "aws_iam_role" "ecs_infrastructure" {
  name = "<name>-ecs-infrastructure"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_infrastructure_mi" {
  role = aws_iam_role.ecs_infrastructure.name
  # NOTE: not under the service-role/ path (unlike the Volumes policy)
  policy_arn = "arn:aws:iam::aws:policy/AmazonECSInfrastructureRolePolicyForManagedInstances"
}

# 2. EC2 instance profile for the managed instances
resource "aws_iam_role" "mi_instance" {
  name = "<name>-mi-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "mi" {
  name = "<name>-mi"
  role = aws_iam_role.mi_instance.name
}

# 3. Capacity provider
resource "aws_ecs_capacity_provider" "managed_instances_provider" {
  name    = "<name>-mi"
  cluster = aws_ecs_cluster.this.name # REQUIRED for MI

  managed_instances_provider {
    infrastructure_role_arn = aws_iam_role.ecs_infrastructure.arn
    propagate_tags          = "CAPACITY_PROVIDER"

    instance_launch_template {
      ec2_instance_profile_arn = aws_iam_instance_profile.mi.arn
      capacity_option_type     = "ON_DEMAND" # or "SPOT"
      monitoring               = "BASIC"     # or "DETAILED" (per-metric charges)

      network_configuration {
        subnets         = var.private_subnet_ids # REQUIRED
        security_groups = [aws_security_group.mi.id]
      }

      instance_requirements {
        vcpu_count { min = 2, max = 16 }        # REQUIRED
        memory_mib { min = 4096, max = 65536 }  # REQUIRED
        # optional: allowed_instance_types, cpu_manufacturers, accelerator_types, ...
      }

      storage_configuration {
        storage_size_gib = 100
      }
    }

    infrastructure_optimization {
      scale_in_after = 300 # seconds idle before scale-in; null/-1/0-3600
    }
  }
}
```

Or with the module: cluster submodule `capacity_providers = { <name> = { managed_instances_provider = { instance_launch_template = {...} } } }` -- the submodule **creates the infrastructure role by default** (`create_infrastructure_iam_role = true`); services reference `module.ecs_cluster.capacity_providers["<name>"].name`.

### Two-step-apply network caveat

The upstream `terraform-aws-modules/ecs` `managed-instances` example documents a network-readiness caveat: the MI capacity provider needs network connectivity (NAT/egress in place) early in the creation process -- on a fully fresh apply where the VPC is created in the same run, `CreateCapacityProvider` fails with a `ServiceAccessDeniedException` on the ECSInfrastructureRole. The upstream example uses a targeted first apply (`terraform apply -target=module.vpc`) before the full apply; networking in a separate workspace/state avoids the issue entirely. Generated READMEs must say: **if the first `terraform apply` fails on the MI capacity provider, apply the VPC first (`-target`) or re-run `terraform apply`**. The same network dependency bites late in destroy (agents cannot connect to drain). Source: https://github.com/terraform-aws-modules/terraform-aws-ecs/tree/master/examples/managed-instances (verified 2026-07-10).

### MI platform constraints (do not attribute these to other launch types)

Verified 2026-07-10 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html:

- **Bottlerocket only, Linux containers only**, X86_64 and ARM64. AWS owns the AMI; no custom AMIs; no SSH (use ECS Exec).
- **14-21-day drain-and-replace lifecycle:** graceful draining starts at day 14 from launch, final termination no later than day 21; EC2 event windows can begin draining earlier than day 14. Services are unaffected -- tasks are drained and replaced gracefully (start-before-stop requires the default `maximumPercent` 200); the lifecycle only bites tasks that need >14 uninterrupted days on one instance.
- Instance selection: `allowedInstanceTypes`/`excludedInstanceTypes` (wildcards) or attribute-based; if unspecified, ECS picks cost-optimized types. GPU/accelerated families are supported (MI-only relative to Fargate, which has no GPU support) -- family choice belongs to `ecs-genai` (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-instance-types.html, verified 2026-07-10). Instances are always >1 vCPU, never nano/micro.
- **GPU metrics are agentless on MI:** Container Insights with enhanced observability collects DCGM GPU metrics at container/task/instance level with no agent installation (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html, verified 2026-07-10). On the EC2 launch type you deploy and manage the CloudWatch agent yourself.
- **Purchase options:** On-Demand (default), Spot (`capacity_option_type = "SPOT"`), or Capacity Reservations (`capacityOptionType=Reserved` + a capacity reservation group); Savings Plans/RIs apply automatically. GPU Capacity Blocks mechanics (single-AZ, extendable): https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-how.html -- details with `ecs-genai`.
- With `capacityOptionType=Reserved`, remember default deployments burst to 200% of steady state -- reserve headroom or tune `maximumPercent`.
- **GuardDuty Runtime Monitoring is NOT supported for workloads on ECS Managed Instances** as of 2026-07-10 (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html). Do not generate GuardDuty agent expectations for MI; see [networking-security.md](networking-security.md).

## Known Terraform/provider issues (check before generating)

Known issues affecting apply-readiness, as of 2026-07-10:

- Target-group replacement deadlocks against a live ECS service -- generate `name_prefix` + `lifecycle { create_before_destroy = true }` on target groups (https://github.com/hashicorp/terraform-provider-aws/issues/16889).
- Services that inherit the cluster **default** capacity provider strategy show a perpetual diff -- prefer explicit per-service strategies (https://github.com/hashicorp/terraform-provider-aws/issues/44776).
- `capacity_provider_strategy` can produce "Provider produced inconsistent final plan" (open: https://github.com/hashicorp/terraform-provider-aws/issues/25203).
- Fargate service destroy can hang waiting on draining (open: https://github.com/hashicorp/terraform-provider-aws/issues/3414).
- MI capacity provider deletion can wedge on stuck instances -- force-deregister per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/troubleshooting-managed-instances.html.
- Provider >= 6.53.0 auto-adds `replace_triggered_by` so a replaced capacity provider is detached from its cluster association before deletion -- older provider versions need manual ordering.

### Quotas that shape generation (verified 2026-07-10)

Per https://docs.aws.amazon.com/general/latest/gr/ecs-service.html: **20 capacity providers per cluster (non-adjustable)** -- this bounds Rule 11's one-ASG-provider-per-size-class pattern; 300 services per Cloud Map namespace; 5 target groups per service; 5 security groups and 16 subnets per `awsvpcConfiguration`; 1,000 tasks per service when service discovery is used (Cloud Map instance quota).

## Sources

- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_capacity_provider
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-instance-types.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html
- https://github.com/terraform-aws-modules/terraform-aws-ecs (cluster submodule README + examples/managed-instances)
- Fargate Spot base/weight pattern: aws/agent-toolkit-for-aws `aws-containers` fargate-spot.md (Apache-2.0, retrieved 2026-07-10)
