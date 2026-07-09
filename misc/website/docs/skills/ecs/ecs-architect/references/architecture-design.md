---
title: "ECS Architecture Design — Task Sizing and Service Parameters"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/references/architecture-design.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-architect/references/architecture-design.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/references/architecture-design.md). Edit the source, not this page.
:::

# ECS Architecture Design — Task Sizing and Service Parameters

> **Part of:** [ecs-architect](../)
> **Purpose:** Size ECS tasks and set the core service parameters once the compute model is chosen. Covers Fargate CPU/memory combinations, ephemeral storage (incl. EBS task volumes), deployment percentages, health-check grace period, deployment controller choice, and placement. Facts verified against AWS docs on **2026-07-09**.

---

## Table of Contents

1. [Task Sizing (Fargate)](#task-sizing-fargate)
2. [Task Sizing (EC2 / Managed Instances)](#task-sizing-ec2--managed-instances)
3. [Ephemeral Storage and Volumes](#ephemeral-storage-and-volumes)
4. [Service Parameters](#service-parameters)
5. [Service Auto Scaling (task-count scaling)](#service-auto-scaling-task-count-scaling)
6. [Deployment Controller Choice](#deployment-controller-choice)
7. [Task Placement (EC2)](#task-placement-ec2)
8. [Sources](#sources)

---

## Task Sizing (Fargate)

Fargate requires CPU and memory at the **task** level. Only specific combinations are valid ([ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)). *(Full table below reproduced from the AWS docs — **last verified 2026-07-09**; the docs page is authoritative if it has since changed.)*

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
- **Bin-packing:** size tasks so an integer number fit the chosen instance type with minimal waste. This interacts with the [mixed-ASG constraint](capacity-and-scaling#the-mixed-instance-type-asg-constraint) — keep one resource profile per ASG.
- Managed Instances handles instance selection/placement for you; you still size the task.

---

## Ephemeral Storage and Volumes

- **Fargate ephemeral storage** — each task gets a default **20 GiB**, expandable up to **200 GiB** (minimum settable value 21 GiB) via the task-definition `ephemeralStorage` parameter (Linux PV 1.4.0+ / Windows PV 1.0.0+). ([Fargate task ephemeral storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html))
- **Amazon EBS task volumes (high-IOPS per-task block storage)** — GA since Jan 2024, ECS attaches and manages **one EBS volume per task** at deployment time. Supported on **Fargate (Linux PV 1.4.0+), EC2 (Nitro-based instances, ECS-optimized AMI `20231219`+), and ECS Managed Instances (Linux)**. Use it for data-intensive/transaction-intensive workloads that need block storage with specific IOPS/throughput, and for **snapshot-seeded scratch** (configure a new volume from an existing snapshot, optionally with `volumeInitializationRate`). Key gotcha: **for tasks managed by a service the volume is always deleted on task termination** — `deleteOnTermination=false` (preserve) is only honored for *standalone* tasks. Requires an infrastructure IAM role and the `ECS` deployment controller (rolling or blue/green). ([Use Amazon EBS volumes with ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ebs-volumes.html) · [EBS volume termination policy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/configure-ebs-volume.html))
- **Amazon EFS (shared/persistent across tasks)** — for state shared across tasks; PV 1.4.0 added Fargate EFS support. ([FargatePlatformVersion — 1.4 features](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.FargatePlatformVersion.html))
- **EC2** tasks can also use bind mounts, Docker volumes, and (for EC2/Windows) FSx for Windows File Server.
- Choose EFS for shared state across tasks, EBS for high-IOPS single-task block storage; don't rely on ephemeral storage surviving task replacement.

---

## Service Parameters

| Parameter | What it controls | Design guidance |
|-----------|------------------|-----------------|
| **`minimumHealthyPercent`** | Floor of running/desired tasks kept healthy during a rolling deployment | 100% for zero-capacity-loss during deploys (needs headroom); lower (e.g. 50%) trades availability for fewer spare tasks |
| **`maximumPercent`** | Ceiling of running tasks during a deployment | 200% lets a full parallel set start before old ones drain; constrain if capacity/cost is tight |
| **`healthCheckGracePeriodSeconds`** | Grace window before ELB health checks can mark a task unhealthy and kill it | Set to longer than real cold-start time for slow-starting apps, or healthy tasks get killed in a restart loop |
| **`deploymentCircuitBreaker`** | Auto-rollback on failed deployments | Enable for services; pairs with health checks (mechanics live in `ecs-devops`) |
| **`enableExecuteCommand`** | ECS Exec shell into a running task | Useful for debugging; gate with IAM (see `ecs-security`) |
| **`availabilityZoneRebalancing`** | Lets ECS automatically redistribute a service's tasks to keep AZs balanced after an infrastructure event | Enable for multi-AZ services to cut mean-time-to-recovery (launched Nov 2024). ([ECS AZ rebalancing](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-ecs-az-rebalancing-speeds-mean-time-recovery-event/)) |

Parameter semantics (min/max healthy percent, grace period) are defined in the service definition parameters reference. ([Amazon ECS service parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_definition_parameters.html)) The health-check grace period is a frequent production footgun: too short and a slow-booting app never passes its first check before ELB kills it, causing a crash loop. Size it against measured startup time.

---

## Service Auto Scaling (task-count scaling)

Distinct from **cluster** capacity scaling ([capacity-and-scaling.md](capacity-and-scaling), which scales the *instances* under EC2/ASG capacity providers), **service auto scaling** scales the **number of tasks** in a service via **Application Auto Scaling**. Both layers matter: service scaling adds tasks, cluster scaling makes room for them. Design both for EC2-backed services; on Fargate only service scaling applies (capacity is implicit). ([Amazon ECS service auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html))

**Policy types:**

| Policy | How it works | Use when |
|--------|--------------|----------|
| **Target tracking** | Pick a metric + target value; ECS creates/manages the CloudWatch alarms and adjusts task count to hold the metric near target. Scales *out* fast, *in* gradually; scale-in is paused during a deployment. | Default choice — CPU/memory utilization or `ALBRequestCountPerTarget`. ([target tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html)) |
| **Step scaling** | You define CloudWatch alarm thresholds and step adjustments. | You need custom, non-proportional reactions to a specific alarm. |
| **Scheduled scaling** | Change min/max capacity on a schedule (cron/rate). | Predictable diurnal or business-hours patterns. |

**Queue-backlog pattern (worker services):** for SQS-driven workers, target-tracking on raw `ApproximateNumberOfMessagesVisible` scales poorly because queue depth isn't proportional to task count. Use a **backlog-per-task** custom metric — `ApproximateNumberOfMessagesVisible / RunningTaskCount` — with the target set to `acceptable-latency / per-message-processing-time`. ([backlog-per-task metric math](https://docs.aws.amazon.com/autoscaling/application/userguide/application-auto-scaling-target-tracking-metric-math.html) · [ECS auto scaling using custom metrics](https://aws.amazon.com/blogs/containers/amazon-elastic-container-service-ecs-auto-scaling-using-custom-metrics/))

**Design notes:** set sensible min/max task bounds; combine policies (e.g. scheduled floor + target-tracking on top); remember scale-in is suppressed during deployments; and pair service scaling with cluster capacity scaling so scaled-out tasks have somewhere to land. Deep tuning and pipeline wiring belong to `ecs-devops`/`ecs-observability`.

### Resilience, multi-AZ, and multi-Region posture

- **Multi-AZ is the default resilience unit.** Spread tasks across ≥2 AZs (`spread` on `availabilityZone`, or subnets in multiple AZs on Fargate) and enable **`availabilityZoneRebalancing`** so ECS re-balances after an AZ event. ([ECS AZ rebalancing](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-ecs-az-rebalancing-speeds-mean-time-recovery-event/))
- **Multi-Region / DR** (active-active or pilot-light across Regions, Route 53 failover, cross-Region ECR replication, data-tier replication) is a broader architecture decision — sketch it here, but the detailed DR design and RTO/RPO targets belong to a Well-Architected reliability review, not this skill.
- **Operating at scale:** ECS service quotas (tasks per service, services per cluster, etc.) and **Fargate task retirement** (platform-version revisions retire periodically; long-running tasks get replaced) shape large designs — budget for task churn and check the relevant quotas before committing to a topology. ([Fargate task retirement notifications](https://aws.amazon.com/blogs/containers/improving-operational-visibility-with-aws-fargate-task-retirement-notifications/))
- **Tenancy / cluster topology** (one cluster per team vs shared, namespace strategy, account boundaries) interacts with the isolation criterion in the SKILL — for regulated multi-tenant isolation, take it to `ecs-security`.

---

## Deployment Controller Choice

This skill names which controller a model supports; `ecs-devops` designs the release process.

| Controller | What it does | Notes |
|------------|--------------|-------|
| **`ECS` (rolling)** | Default; replaces tasks per min/max healthy percent | Simplest; add the circuit breaker for auto-rollback |
| **`ECS` (native blue/green)** | ECS-native blue/green (launched **July 2025**): provisions a green revision on a second target group, shifts traffic all-at-once / canary / linear, holds a bake period, then retires blue or rolls back on alarm/hook failure. Works with ALB, NLB, and Service Connect | Set `deploymentConfiguration.strategy` to `BLUE_GREEN`; deployment config lives inside the ECS service itself. ([ECS built-in blue/green deployments — launch](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-ecs-built-in-blue-green-deployments/)) |
| **`CODE_DEPLOY`** | Blue/green orchestrated by AWS CodeDeploy | Pre-2025 path; still supported. Native blue/green consolidates this into ECS — see [migrate CodeDeploy to ECS blue/green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html) |
| **`EXTERNAL`** | Third-party deployment orchestration | For custom/GitOps controllers |

Choosing between native blue/green and CodeDeploy, canary/linear tuning, and pipeline wiring are `ecs-devops` decisions.

---

## Task Placement (EC2)

On EC2 (not Fargate — Fargate places for you), use placement strategies and constraints:

- **Strategies:** `binpack` (cost — pack tasks tight), `spread` (availability — across AZs/instances), `random`.
- **Constraints:** `distinctInstance` (one task per instance), `memberOf` with attribute expressions (e.g. instance type, AZ, custom attributes).
- **Bin-pack on `memory`, not `cpu`** (field heuristic). Container-level `cpu` is a *soft* CPU share — containers burst into unused CPU, so CPU bin-packing overcommits invisibly and can still schedule tasks onto a "full" instance; the container `memory` hard limit OOM-kills on breach, so memory bin-packing gives a predictable, safe density guarantee. Note this softness is at the *container-share* level — the **task-level `cpu` value is itself a hard ceiling** for the whole task. ([task definition CPU/memory parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html))
- Combine `spread` across `availabilityZone` for AZ resilience with `binpack` on memory for cost. For GPU-per-type layouts, use constraints alongside the separate-ASG pattern (`ecs-genai`). ([task placement strategy examples](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/strategy-examples.html))

---

## Sources

- [Amazon ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html) — CPU/memory table, SOCI
- [Fargate task ephemeral storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html) — 20 GiB default / 200 GiB max
- [Use Amazon EBS volumes with Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ebs-volumes.html) · [EBS volume termination policy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/configure-ebs-volume.html) — Fargate PV1.4+/EC2 Nitro/MI, delete-on-termination
- [FargatePlatformVersion (CDK) — 1.4 feature list](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.FargatePlatformVersion.html) — EFS support
- [Amazon ECS service definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_definition_parameters.html) — min/max healthy percent, grace period
- [Amazon ECS service auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html) · [target tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html) · [backlog-per-task metric math](https://docs.aws.amazon.com/autoscaling/application/userguide/application-auto-scaling-target-tracking-metric-math.html)
- [Amazon ECS AZ rebalancing (Nov 2024)](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-ecs-az-rebalancing-speeds-mean-time-recovery-event/)
- [Amazon ECS task placement strategy examples](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/strategy-examples.html) · [task definition CPU/memory parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Amazon ECS built-in blue/green deployments (July 2025)](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-ecs-built-in-blue-green-deployments/)
- [Migrate CodeDeploy blue/green to Amazon ECS blue/green](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/migrate-codedeploy-to-ecs-bluegreen.html)
