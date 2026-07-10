---
title: "Section 05 — Service Health & Autoscaling"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/service-health-scaling.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/service-health-scaling.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/service-health-scaling.md). Edit the source, not this page.
:::

# Section 05 — Service Health & Autoscaling

## Purpose
Assess runtime resilience of services: load-balancer **health-check grace period**, container/LB health checks, **connection draining** (deregistration delay + `stopTimeout`), **service auto scaling**, **Availability Zone rebalancing**, and task **placement strategy**. Grounded in the ECS Best Practices Guide tasks-and-services pillar.

## Checks to Execute

### 5.1 — Health-Check Grace Period

**What to check (services with a load balancer):**
- `healthCheckGracePeriodSeconds` on the service.
- Whether it's long enough for the app's real startup time.

**How to check:**
1. `aws ecs describe-services --cluster <c> --services <s>` → `healthCheckGracePeriodSeconds`.
2. Compare against known/expected task startup time.

**Rating:**
- 🟢 GREEN: Grace period set to comfortably exceed cold-start time for slow-starting apps (JVM, large images), preventing premature task kills.
- 🟡 AMBER: Default `0` on an app that starts slowly but currently survives, or a value only marginally above startup time.
- 🔴 RED: Grace period `0`/too short on a slow-starting LB-backed service, causing a task-launch/kill loop (tasks killed before they become healthy).
- ⚪ N/A: No load balancer (for non-LB services use the task-definition health-check `startPeriod` instead).
- ⬜ UNKNOWN: Cannot read the service.

**Key talking point:** The health-check grace period is the window (default `0`) during which the ECS scheduler ignores unhealthy Elastic Load Balancing, **VPC Lattice**, and container health checks after a task first starts — critical for slow-starting apps so they aren't killed before they come up. If none of those health checks are used, `healthCheckGracePeriodSeconds` is unused; for services without an ELB, use `startPeriod` in the task-definition health check. Note: if the service has more running tasks than desired, unhealthy tasks in the grace period may still be stopped to reach the desired count. The `healthCheckGracePeriodSeconds` parameter is defined on the [CreateService API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html) (the [load-balancer health-check tuning guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-healthcheck.html) covers the LB health check itself). Verified 2026-07-09.

---

### 5.2 — Load-Balancer Health-Check Parameters

**What to check (target groups behind the service):**
- Health-check path, interval, timeout, healthy/unhealthy thresholds.
- Deregistration delay (see 5.3).

**How to check:**
1. From the service's `loadBalancers[].targetGroupArn`, run `aws elbv2 describe-target-groups` and `aws elbv2 describe-target-group-attributes`.

**Rating:**
- 🟢 GREEN: Meaningful health-check path (not `/` if that doesn't reflect readiness), tuned interval/thresholds for fast-but-stable failure detection.
- 🟡 AMBER: Default health check that may not reflect true readiness, or thresholds slow to detect failure.
- 🔴 RED: Health check hitting an endpoint that returns 200 while the app is not truly ready (false-healthy), causing traffic to broken tasks.
- ⚪ N/A: No load balancer on the service (same condition as 5.1's N/A).
- ⬜ UNKNOWN: Cannot read target-group attributes.

See [optimize load-balancer health-check parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-healthcheck.html).

---

### 5.3 — Connection Draining (deregistration delay + stopTimeout)

**What to check:**
- Target-group `deregistration_delay.timeout_seconds`.
- Container `stopTimeout` and whether the app handles `SIGTERM` gracefully.
- Alignment: task stop timeout should cover the deregistration/drain window.

**How to check:**
1. `aws elbv2 describe-target-group-attributes` → `deregistration_delay.timeout_seconds`.
2. Task definition → container `stopTimeout`.

**Rating:**
- 🟢 GREEN: Deregistration delay tuned to the app's in-flight request duration, and `stopTimeout` covers the drain window — no dropped connections on deploy/scale-in.
- 🟡 AMBER: Defaults left in place (300s dereg delay slows deploys; short `stopTimeout` may cut connections) without evidence of tuning.
- 🔴 RED: Draining misaligned and the service experiences 5xx/reset connections during deployments or scale-in.
- ⚪ N/A: No load balancer on the service (same condition as 5.1's N/A).
- ⬜ UNKNOWN: Cannot correlate the settings.

**Key talking point:** During task shutdown the LB keeps sending traffic until deregistration completes; the container `stopTimeout` must be long enough to finish in-flight requests after `SIGTERM`. See [optimize load-balancer connection draining](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-connection-draining.html).

---

### 5.4 — Service Auto Scaling

**What to check:**
- Application Auto Scaling target registered for the service (`ecs:service:DesiredCount`).
- Scaling policies (target tracking on CPU/memory/ALB request count, or step scaling) and min/max capacity.

**How to check:**
1. `aws application-autoscaling describe-scalable-targets --service-namespace ecs`.
2. `aws application-autoscaling describe-scaling-policies --service-namespace ecs`.

**Rating:**
- 🟢 GREEN: Target-tracking (or well-justified step) scaling with sensible min ≥ 2 for HA and a max that covers peak; scaling metric reflects real load.
- 🟡 AMBER: Scaling configured but `minCapacity: 1` (single point of failure) for a production service, or a metric poorly correlated with load.
- 🔴 RED: No autoscaling on a variable-load production service — fixed desired count risks both outage and waste.
- ⬜ UNKNOWN: Cannot read scalable targets/policies.

**Key talking point:** ECS service auto scaling uses Application Auto Scaling on CloudWatch metrics; target tracking on `ECSServiceAverageCPUUtilization`/memory or ALB `RequestCountPerTarget` is the common pattern. See [automatically scale your ECS service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html) and [optimizing service auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-autoscaling-best-practice.html).

---

### 5.5 — AZ Resilience: Placement Strategy & AZ Rebalancing

**What to check:**
- Task placement strategy (`spread` on `attribute:ecs.availability-zone`) vs none.
- Whether **Availability Zone rebalancing** is enabled.
- Subnets span ≥ 2 (ideally 3) AZs.

**How to check:**
1. `aws ecs describe-services` → `placementStrategy`, `availabilityZoneRebalancing`, and `networkConfiguration` subnets → map subnets to AZs via `aws ec2 describe-subnets`.

**Rating:**
- 🟢 GREEN: Tasks spread across ≥ 3 AZs with AZ-spread placement (or default replica strategy) **and** AZ rebalancing ENABLED so post-disruption imbalance self-heals.
- 🟡 AMBER: Multi-AZ subnets but AZ rebalancing disabled (imbalance persists after an AZ event, eroding static stability), or only 2 AZs.
- 🔴 RED: Single-AZ deployment, or a multi-replica production service pinned to one AZ.
- ⬜ UNKNOWN: Cannot map subnets to AZs or read placement config.

**Key talking point:** AZ spread doesn't self-correct after an AZ disruption — imbalance can persist and threaten static stability. **AZ rebalancing** continuously redistributes tasks to keep AZs even. It supports Fargate, EC2, and Managed Instances, and works with the Replica strategy; it is **not** compatible with the Daemon strategy, `EXTERNAL` launch type, `maximumPercent: 100`, or a Classic Load Balancer. **Default gotcha:** starting September 5, 2025, ECS enabled AZ rebalancing for all *eligible* services (eligible = AZ spread is the first placement strategy, or no placement strategy) — but ineligible services (Daemon strategy, `EXTERNAL` launch type, `maximumPercent: 100`, Classic Load Balancer, or an `ecs.availability-zone` placement constraint) remain OFF. Confirm the observed `availabilityZoneRebalancing` value rather than assuming it is on. See [balancing an ECS service across AZs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-rebalancing.html) and [resilience best practices](https://aws.amazon.com/blogs/containers/best-practices-for-resilience-and-availability-on-amazon-ecs/).
