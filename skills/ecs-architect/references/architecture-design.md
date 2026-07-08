# ECS Architecture Design — Task Sizing and Service Parameters

> **Part of:** [ecs-architect](../SKILL.md)
> **Purpose:** Size ECS tasks and set the core service parameters once the compute model is chosen. Covers Fargate CPU/memory combinations, ephemeral storage, deployment percentages, health-check grace period, deployment controller choice, and placement. Facts verified against AWS docs on 2026-07-08.

---

## Table of Contents

1. [Task Sizing (Fargate)](#task-sizing-fargate)
2. [Task Sizing (EC2 / Managed Instances)](#task-sizing-ec2--managed-instances)
3. [Ephemeral Storage and Volumes](#ephemeral-storage-and-volumes)
4. [Service Parameters](#service-parameters)
5. [Deployment Controller Choice](#deployment-controller-choice)
6. [Task Placement (EC2)](#task-placement-ec2)
7. [Sources](#sources)

---

## Task Sizing (Fargate)

Fargate requires CPU and memory at the **task** level. Only specific combinations are valid ([ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)):

| CPU | Memory | OS |
|-----|--------|-----|
| 256 (.25 vCPU) | 512 MiB, 1 GB, 2 GB | Linux |
| 512 (.5 vCPU) | 1–4 GB (1 GB steps) | Linux |
| 1024 (1 vCPU) | 2–8 GB (1 GB steps) | Linux, Windows |
| 2048 (2 vCPU) | 4–16 GB (1 GB steps) | Linux, Windows |
| 4096 (4 vCPU) | 8–30 GB (1 GB steps) | Linux, Windows |
| 8192 (8 vCPU) | 16–60 GB (4 GB steps) — **requires Linux PV 1.4.0+** | Linux |
| 16384 (16 vCPU) | 32–120 GB (8 GB steps) — **requires Linux PV 1.4.0+** | Linux |
| 32768 (32 vCPU) | 60 GB, 120 GB, 244 GB — **requires Linux PV 1.4.0+** | Linux |

**Notes:**
- The largest Fargate task is **16 vCPU / 120 GB** in the general table; **32 vCPU** with 60/120/244 GB is also available on Linux PV 1.4.0+. Anything larger, or GPU, must go to EC2/Managed Instances.
- CPU can be given in units (`1024`) or vCPUs (`1 vCPU`); memory in MiB (`3072`) or GB (`3 GB`).
- Windows containers on Fargate have a narrower set of combinations.
- Right-size to the P95 of real usage, not peak — over-provisioning Fargate is a direct dollar cost (see `ecs-cost-intelligence`).

---

## Task Sizing (EC2 / Managed Instances)

On EC2 you can set CPU/memory at the task level and/or the container level. Task-level limits cap the whole task; container-level `cpu` (shares) and `memory`/`memoryReservation` (hard/soft limits) control per-container allocation and bin-packing.

- **Hard vs soft memory:** `memory` is a hard cap (container is killed if exceeded — a common OOM cause); `memoryReservation` is a soft floor used for placement. Set both thoughtfully; a hard limit too close to real usage causes OOM kills.
- **Bin-packing:** size tasks so an integer number fit the chosen instance type with minimal waste. This interacts with the [mixed-ASG constraint](capacity-and-scaling.md#the-mixed-instance-type-asg-constraint) — keep one resource profile per ASG.
- Managed Instances handles instance selection/placement for you; you still size the task.

---

## Ephemeral Storage and Volumes

- **Fargate** provides ephemeral storage per task (default 20 GB, expandable up to 200 GB on PV 1.4.0+). For shared/persistent data, mount **Amazon EFS**; PV 1.4.0 added EFS support. ([FargatePlatformVersion — 1.4 features](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.FargatePlatformVersion.html))
- **EC2** tasks can use bind mounts, Docker volumes, EFS, and (for EC2) FSx for Windows File Server.
- Choose EFS for shared state across tasks; don't rely on ephemeral storage surviving task replacement.

---

## Service Parameters

| Parameter | What it controls | Design guidance |
|-----------|------------------|-----------------|
| **`minimumHealthyPercent`** | Floor of running/desired tasks kept healthy during a rolling deployment | 100% for zero-capacity-loss during deploys (needs headroom); lower (e.g. 50%) trades availability for fewer spare tasks |
| **`maximumPercent`** | Ceiling of running tasks during a deployment | 200% lets a full parallel set start before old ones drain; constrain if capacity/cost is tight |
| **`healthCheckGracePeriodSeconds`** | Grace window before ELB health checks can mark a task unhealthy and kill it | Set to longer than real cold-start time for slow-starting apps, or healthy tasks get killed in a restart loop |
| **`deploymentCircuitBreaker`** | Auto-rollback on failed deployments | Enable for services; pairs with health checks (mechanics live in `ecs-devops`) |
| **`enableExecuteCommand`** | ECS Exec shell into a running task | Useful for debugging; gate with IAM (see `ecs-security`) |

The health-check grace period is a frequent production footgun: too short and a slow-booting app never passes its first check before ELB kills it, causing a crash loop. Size it against measured startup time.

---

## Deployment Controller Choice

This skill names which controller a model supports; `ecs-devops` designs the release process.

| Controller | What it does | Notes |
|------------|--------------|-------|
| **`ECS` (rolling)** | Default; replaces tasks per min/max healthy percent | Simplest; add the circuit breaker for auto-rollback |
| **`ECS` (native blue/green)** | ECS-native blue/green (launched **July 2025**): provisions a green revision on a second target group, shifts traffic all-at-once / canary / linear, holds a bake period, then retires blue or rolls back on alarm/hook failure | Set `deploymentConfiguration.strategy` to `BLUE_GREEN`; deployment config lives inside the ECS service itself. ([ECS-native blue/green](https://aws.amazon.com/blogs/devops/choosing-between-amazon-ecs-blue-green-native-or-aws-codedeploy-in-aws-cdk/)) |
| **`CODE_DEPLOY`** | Blue/green orchestrated by AWS CodeDeploy | Pre-2025 path; still supported. Native blue/green consolidates this into ECS — see [migrate CodeDeploy to ECS blue/green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html) |
| **`EXTERNAL`** | Third-party deployment orchestration | For custom/GitOps controllers |

Choosing between native blue/green and CodeDeploy, canary/linear tuning, and pipeline wiring are `ecs-devops` decisions.

---

## Task Placement (EC2)

On EC2 (not Fargate — Fargate places for you), use placement strategies and constraints:

- **Strategies:** `binpack` (cost — pack tasks tight), `spread` (availability — across AZs/instances), `random`.
- **Constraints:** `distinctInstance` (one task per instance), `memberOf` with attribute expressions (e.g. instance type, AZ, custom attributes).
- **Bin-pack on `memory`, not `cpu`.** CPU on EC2 is a soft/burstable limit, so CPU bin-packing overcommits invisibly and can still schedule tasks onto a "full" instance; memory is a hard limit and over-packing OOM-kills containers. Memory bin-packing gives a predictable, safe density guarantee.
- Combine `spread` across `availabilityZone` for AZ resilience with `binpack` on memory for cost. For GPU-per-type layouts, use constraints alongside the separate-ASG pattern (`ecs-genai`).

---

## Sources

- [Amazon ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html) — CPU/memory table, ephemeral storage, SOCI
- [FargatePlatformVersion (CDK) — 1.4 feature list](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.FargatePlatformVersion.html) — EFS support, 20 GB ephemeral
- [Choosing between ECS Blue/Green Native or CodeDeploy](https://aws.amazon.com/blogs/devops/choosing-between-amazon-ecs-blue-green-native-or-aws-codedeploy-in-aws-cdk/)
- [Migrate CodeDeploy blue/green to Amazon ECS blue/green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html)
