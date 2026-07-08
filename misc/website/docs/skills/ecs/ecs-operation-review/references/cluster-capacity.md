---
title: "Section 01 — Clusters & Capacity"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/cluster-capacity.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/cluster-capacity.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/cluster-capacity.md). Edit the source, not this page.
:::

# Section 01 — Clusters & Capacity

## Purpose
Assess how the cluster obtains compute (Fargate / EC2 Auto Scaling Group capacity providers / ECS Managed Instances), and whether **capacity-provider scale-in is correct** — the single richest source of ECS production incidents ("empty instance won't terminate", "instance running tasks got terminated", "won't scale out"). This section deals with capacity *correctness and resilience*; dollar-denominated efficiency (Savings Plans, Graviton, Spot economics, right-sizing) is out of scope here — defer to **`ecs-cost-intelligence`**.

## Checks to Execute

### 1.1 — Capacity-Provider Strategy Present

**What to check:**
- Cluster's registered capacity providers and default capacity-provider strategy.
- Whether services use a capacity-provider strategy vs the legacy `launchType` field.

**How to check:**
1. `aws ecs describe-clusters --clusters <name> --include CONFIGURATIONS SETTINGS` → read `capacityProviders` and `defaultCapacityProviderStrategy`.
2. For each service: `aws ecs describe-services --cluster <name> --services <svc>` → check `capacityProviderStrategy` vs `launchType`.

**Rating:**
- 🟢 GREEN: Services use a capacity-provider strategy (Fargate, `FARGATE_SPOT`, EC2-ASG, or Managed Instances) rather than a hardcoded `launchType`.
- 🟡 AMBER: Mix of capacity-provider strategy and `launchType: EC2`/`FARGATE`.
- 🔴 RED: All services pinned to `launchType` with no capacity providers registered — no path to blended Spot/On-Demand or managed capacity.
- ⬜ UNKNOWN: Cannot list services or describe the cluster.

**Key talking point:** A service created with `launchType: EC2` cannot be migrated to capacity providers in place — the service must be recreated. Capacity-provider strategy is the flexible, recommended model. See [Auto scaling and capacity management best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability.html).

---

### 1.2 — Managed Termination Protection & Managed Draining (EC2 ASG capacity providers)

**What to check (EC2 Auto Scaling Group capacity providers only):**
- `managedScaling` enabled on the capacity provider.
- `managedTerminationProtection` enabled.
- `managedDraining` enabled.

**How to check:**
1. `aws ecs describe-capacity-providers` → for each ASG provider read `autoScalingGroupProvider.managedScaling.status`, `managedTerminationProtection`, and `managedDraining`.

**Rating:**
- 🟢 GREEN: Managed scaling ON **and** managed termination protection ON **and** managed draining ON.
- 🟡 AMBER: Managed scaling ON but managed draining OFF (ungraceful task interruption on scale-in), or termination protection ON without draining.
- 🔴 RED: Managed termination protection OFF while managed scaling is ON — the ASG can terminate instances that are running tasks during scale-in, causing avoidable task disruption.
- ⬜ UNKNOWN: No EC2 ASG capacity providers (N/A — Fargate/Managed-Instances only), or cannot describe providers.

**Critical gotcha:** Managed termination protection **requires** managed scaling to also be enabled, and the ASG (and its instances) must have scale-in protection enabled — otherwise it silently does nothing. Enable **both** managed termination protection and managed draining for maximum protection against interruptions. See [Deep dive on ECS cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html) and the [managed instance draining launch post](https://aws.amazon.com/blogs/containers/amazon-ecs-enables-easier-ec2-capacity-management-with-managed-instance-draining/).

---

### 1.3 — Cluster Auto Scaling Health (target capacity / scale-out latency)

**What to check (EC2 ASG capacity providers):**
- `targetCapacity` of managed scaling (100 = pack tightly, lower = keep headroom).
- ASG min/max/desired and whether max is high enough to avoid pending-task starvation.
- Presence of pending tasks that can't be placed (`RESOURCE:CPU` / `RESOURCE:MEMORY`).

**How to check:**
1. `aws ecs describe-capacity-providers` → `managedScaling.targetCapacity`.
2. `aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names <asg>` → min/max/desired.
3. `aws ecs describe-clusters --include STATISTICS` → `pendingTasksCount`.
4. Optionally list stopped tasks / service events for `RESOURCE:*` placement failures.

**Rating:**
- 🟢 GREEN: `targetCapacity` tuned (typically 90–100 for cost, lower for burst headroom), ASG max provides headroom, no chronic pending tasks.
- 🟡 AMBER: `targetCapacity` = 100 with bursty workloads (scale-out lag risk), or ASG max close to desired.
- 🔴 RED: Persistent pending tasks blocked on `RESOURCE:*`, or ASG max reached with unplaced tasks.
- ⬜ UNKNOWN: N/A for Fargate/Managed Instances (managed by AWS), or cannot read metrics.

**Key talking point:** `targetCapacity` below 100 intentionally keeps spare instances warm to reduce scale-out latency; 100 optimizes cost at the expense of launch time. See [Optimize ECS cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html).

---

### 1.4 — Managed Instances Configuration (if used)

**What to check (Managed Instances capacity providers only):**
- Infrastructure role present; instance requirements (attributes) reasonable.
- Auto-repair enabled.
- Infrastructure optimization (bin-packing) settings.

**How to check:**
1. `aws ecs describe-capacity-providers` → providers of type Managed Instances → inspect `managedInstancesProvider` (`infrastructureRoleArn`, `instanceLaunchTemplate`, `autoRepairConfiguration`, `infrastructureOptimization`).

**Rating:**
- 🟢 GREEN: Managed Instances configured with auto-repair on and instance requirements matched to workload; AWS handles patching (every 14 days) and scaling.
- 🟡 AMBER: Auto-repair off, or overly narrow instance-type constraints limiting placement flexibility.
- 🔴 RED: Misconfigured infrastructure role blocking provisioning, or instance requirements so narrow that tasks cannot place.
- ⬜ UNKNOWN: Managed Instances not in use (N/A), or cannot describe providers.

**Key talking point:** ECS Managed Instances (GA 2025; available for new and existing clusters in all AWS Regions **except AWS GovCloud (US) and China**) gives Fargate-like operational offload with full EC2 instance-type access; AWS provisions, scales, patches (security patching initiated ~every 14 days, schedulable via EC2 event windows), and cost-optimizes placement. See [Architect for ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html) and [Managed Instances capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-capacity-providers-concept.html).

---

### 1.5 — Fargate Spot / Spot Strategy Resilience

**What to check:**
- Use of `FARGATE_SPOT` or EC2 Spot in capacity-provider strategy.
- Whether Spot is mixed with a base of On-Demand (`base` on the On-Demand provider) for interruption resilience.
- **(EC2 Spot ASGs only)** Instance-type diversification across families/sizes and AZs, and `capacityRebalancing` enabled on the ASG. A single instance type on Spot means one capacity pool — when that pool is reclaimed, a large fraction of tasks are evicted simultaneously.

**How to check:**
1. Read `capacityProviderStrategy` on services and the cluster default → check for `FARGATE_SPOT` with a `base`/`weight` mix.
2. For EC2 Spot: `aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names <asg>` → inspect `MixedInstancesPolicy` (instance-type count/diversity, `SpotAllocationStrategy` such as `price-capacity-optimized`) and `CapacityRebalance`.

**Rating:**
- 🟢 GREEN: Spot used with an On-Demand `base` for critical services (interruption-tolerant design); EC2 Spot ASGs diversify across ≥ 3 instance types + multiple AZs with `capacityRebalancing` on.
- 🟡 AMBER: Spot used for stateful/critical services with no On-Demand base, or an EC2 Spot ASG on only 1–2 instance types (concentrated capacity-pool risk).
- 🔴 RED: 100% Spot for a production, interruption-sensitive service with no fallback, or a single-instance-type Spot ASG behind a production service.
- ⬜ UNKNOWN: Cannot determine workload criticality — flag for manual review. Dollar-level Spot economics → **`ecs-cost-intelligence`**.

**Note:** This item rates *resilience of the Spot posture*, not cost savings. Deep Spot-strategy and TCO analysis belongs to `ecs-cost-intelligence`. See [best practices for handling EC2 Spot interruptions](https://aws.amazon.com/blogs/compute/best-practices-for-handling-ec2-spot-instance-interruptions/).
