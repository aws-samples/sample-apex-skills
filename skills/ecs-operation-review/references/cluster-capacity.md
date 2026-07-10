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

**Key talking point:** **All launch type → capacity provider updates are supported without service recreation** — an existing `launchType: EC2` (or `FARGATE`/`EXTERNAL`) service can be moved to a capacity-provider strategy in place with `UpdateService` (ensure the task definition's `requiresCompatibilities` includes the target). The switch itself does **not** trigger a deployment; running tasks migrate to the new capacity on the next forced/rolling deployment. The restrictions are narrower: capacity-provider → launch-type is *not* supported except reverting to the launch type the service was originally created with (pass an empty `capacityProviderStrategy`), and launch-type → launch-type is not supported (use the equivalent capacity provider). Capacity-provider strategy is the flexible, recommended model. Verified 2026-07-09. See [ECS launch types and capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html) and [Auto scaling and capacity management best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability.html).

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
- ⚪ N/A: No EC2 ASG capacity providers (Fargate/Managed-Instances-only estate).
- ⬜ UNKNOWN: Cannot describe capacity providers.

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
4. Optionally list stopped tasks / service events for `RESOURCE:CPU` / `RESOURCE:MEMORY` placement failures (`RESOURCE:ENI` failures are rated in check **2.6**, not here).

**Rating:**
- 🟢 GREEN: `targetCapacity` tuned (typically 90–100 for cost, lower for burst headroom), ASG max provides headroom, no chronic pending tasks.
- 🟡 AMBER: `targetCapacity` = 100 with bursty workloads (scale-out lag risk), or ASG max close to desired.
- 🔴 RED: Persistent pending tasks blocked on `RESOURCE:CPU` / `RESOURCE:MEMORY`, or ASG max reached with unplaced tasks. (`RESOURCE:ENI` exhaustion is scored once, in check **2.6** — cross-reference it, do not re-rate it here.)
- ⚪ N/A: Fargate/Managed-Instances only (cluster scaling is managed by AWS).
- ⬜ UNKNOWN: Cannot read capacity-provider or ASG metrics.

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
- 🟢 GREEN: Managed Instances configured with auto-repair on and instance requirements matched to workload; AWS handles the instance lifecycle (drain-and-replace) and scaling.
- 🟡 AMBER: Auto-repair off, or overly narrow instance-type constraints limiting placement flexibility.
- 🔴 RED: Misconfigured infrastructure role blocking provisioning, or instance requirements so narrow that tasks cannot place.
- ⚪ N/A: Managed Instances not in use.
- ⬜ UNKNOWN: Cannot describe capacity providers.

**Key talking point:** ECS Managed Instances (GA Sep 2025; now available in **all commercial AWS Regions** and **AWS GovCloud (US-East/US-West)** — verified 2026-07-09) gives Fargate-like operational offload with full EC2 instance-type access; AWS provisions, scales, and cost-optimizes placement. Its "patching" is **not in-place**: instances run on a standardized **14–21 day maximum lifetime** — ECS begins graceful workload draining at day 14 from launch and terminates the instance no later than day 21, replacing it with a freshly patched one (early draining can occur for security vulnerabilities, hardware degradation, or to honor a configured EC2 event window). Schedule the disruption via EC2 event windows. **GuardDuty caveat:** GuardDuty Runtime Monitoring does **not** support ECS Managed Instances (see Section 07, check 7.4). See [Architect for ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html), [Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html), [Managed Instances capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-capacity-providers-concept.html), and the [all-commercial-Regions](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-managed-instances-commercial-regions/) / [GovCloud](https://aws.amazon.com/about-aws/whats-new/2025/11/ecs-managed-instances-govcloud-us-regions/) availability posts.

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
- ⚪ N/A: No Spot capacity in use anywhere in the estate (no `FARGATE_SPOT` in any strategy, no Spot in any ASG `MixedInstancesPolicy`) — there is no Spot posture to rate.
- ⬜ UNKNOWN: Cannot determine workload criticality — flag for manual review. Dollar-level Spot economics → **`ecs-cost-intelligence`**.

**Note:** This item rates *resilience of the Spot posture*, not cost savings. Deep Spot-strategy and TCO analysis belongs to `ecs-cost-intelligence`. See [best practices for handling EC2 Spot interruptions](https://aws.amazon.com/blogs/compute/best-practices-for-handling-ec2-spot-instance-interruptions/).

---

### 1.6 — EC2 Container-Instance Currency & Agent Connectivity (self-managed EC2 only)

**What to check (EC2 Auto Scaling group capacity providers / self-managed EC2 container instances only — N/A for Fargate and Managed Instances, where AWS owns the instance):**
- Each container instance's `agentConnected` status — `false` means the ECS agent has lost contact with the control plane, so the instance can't place new tasks even though EC2 shows it healthy (a top re:Post failure mode).
- ECS container agent version (`versionInfo.agentVersion`) currency against the latest release.
- Age of the underlying ECS-optimized AMI (stale AMIs miss agent, kernel, and CVE fixes).

**How to check:**
1. `aws ecs list-container-instances --cluster <name>` → `aws ecs describe-container-instances --cluster <name> --container-instances <arns>` → read `agentConnected`, `versionInfo.agentVersion`, `versionInfo.dockerVersion`, and `ec2InstanceId`.
2. Map `ec2InstanceId` → `aws ec2 describe-instances` → resolve the AMI (`ImageId`) and its age via `aws ec2 describe-images`.
3. Compare the agent version against the [amazon-ecs-agent releases](https://github.com/aws/amazon-ecs-agent/releases).

**Rating:**
- 🟢 GREEN: All container instances `agentConnected: true`, running a recent agent, on a recent ECS-optimized AMI.
- 🟡 AMBER: Agent or AMI several versions behind (missing fixes) but all connected, or no AMI-refresh process.
- 🔴 RED: One or more container instances with `agentConnected: false` (silently unable to place tasks), or markedly stale AMIs on production capacity.
- ⚪ N/A: Fargate/Managed-Instances only (AWS manages the instance and agent).
- ⬜ UNKNOWN: Cannot describe container instances.

**Key talking point:** `agentConnected: false` is a common, easily-missed cause of "tasks won't place / stuck PENDING" on EC2 capacity — EC2 reports the instance healthy while ECS can't schedule to it. Keep the agent current (it ships with the ECS-optimized AMI) and roll AMIs regularly. Verified 2026-07-09. See [ECS EC2 container instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-versions.html) and [describe-container-instances](https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-container-instances.html).
