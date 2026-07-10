---
title: "ECS Capacity Providers and Scaling"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/references/capacity-and-scaling.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-architect/references/capacity-and-scaling.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/references/capacity-and-scaling.md). Edit the source, not this page.
:::

# ECS Capacity Providers and Scaling

> **Part of:** [ecs-architect](../)
> **Purpose:** Design a capacity-provider strategy and cluster auto scaling correctly. Covers the base/weight model, managed scaling, the mixed-instance-type ASG constraint, scale-in edge cases, and Spot. Facts verified against AWS docs on **2026-07-09**.

---

## Table of Contents

1. [What Capacity Providers Are](#what-capacity-providers-are)
2. [Launch Type vs Capacity-Provider Strategy](#launch-type-vs-capacity-provider-strategy)
3. [Base and Weight](#base-and-weight)
4. [Cluster Auto Scaling (EC2 ASG capacity providers)](#cluster-auto-scaling-ec2-asg-capacity-providers)
5. [The Mixed-Instance-Type ASG Constraint](#the-mixed-instance-type-asg-constraint)
6. [Scale-In Edge Cases](#scale-in-edge-cases)
7. [Fargate Spot](#fargate-spot)
8. [Managed Instances Capacity Provider](#managed-instances-capacity-provider)
9. [Sources](#sources)

---

## What Capacity Providers Are

A capacity provider decouples *where a task runs* from *how the underlying capacity scales*. ECS supports capacity providers for:

- **Fargate** — the built-in `FARGATE` and `FARGATE_SPOT` providers.
- **EC2 Auto Scaling groups** — an `AsgCapacityProvider` wrapping an ASG, usually with **managed scaling** and **managed termination protection** enabled.
- **Managed Instances** — a Managed Instances capacity provider where AWS provisions/operates the EC2 fleet.

A **capacity-provider strategy** is a list of `{capacityProvider, base, weight}` entries attached to a service, standalone task, or cluster default.

---

## Launch Type vs Capacity-Provider Strategy

**A task or service uses either a `launchType` OR a `capacityProviderStrategy` — never both in the same call.** ([managed-scaling-behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html)) Tasks without a capacity-provider strategy are ignored by capacity providers and will not cause any provider to scale out.

**Important for Managed Instances:** because it is delivered as a capacity provider, a service that uses Managed Instances **must** set `capacityProviderStrategy`, not `launchType`. ([update-service CLI reference](https://docs.aws.amazon.com/cli/v1/reference/ecs/update-service.html))

Supported transitions between launch types and capacity providers (and the immutability trap) are covered in [launch-type-migration.md](launch-type-migration).

---

## Base and Weight

- **`base`** — a minimum number of tasks to run on that provider before weight is applied. **Only one capacity provider in a strategy can have a (non-zero) `base` defined**; the default is `0`, valid range 0–100,000. ([CapacityProviderStrategyItem — base](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-ecs-service-capacityproviderstrategyitem.html))
- **`weight`** — the relative share of *remaining* tasks across providers after base is satisfied.

**Common resilient pattern (Fargate + Spot):**

| Provider | base | weight | Effect |
|----------|------|--------|--------|
| `FARGATE` | 1 | 1 | At least 1 on-demand task always; then 1-in-2 of the rest on-demand |
| `FARGATE_SPOT` | 0 | 1 | ~half of scaled tasks on cheaper interruptible capacity |

Tune weights toward Spot for interruption-tolerant workloads, toward on-demand for latency-critical ones. Quantify the savings with `ecs-cost-intelligence`.

---

## Cluster Auto Scaling (EC2 ASG capacity providers)

When you enable **managed scaling** and **managed termination protection** on an ASG capacity provider, ECS:

1. Creates a target-tracking scaling policy driven by a CloudWatch metric ECS publishes, **`CapacityProviderReservation`**, at one-minute frequency.
2. Manages instance termination protection so instances running non-daemon tasks aren't terminated by ASG scale-in.

`CapacityProviderReservation` compares capacity needed (`M`) to capacity running (`N`); target capacity 100% means "run instances fully utilized." Special cases: if `M=0` and `N=0`, the metric is 100; if `M>0` and `N=0` (tasks pending, no instances), it drives scale-out. ([Deep Dive on Amazon ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/deep-dive-on-amazon-ecs-cluster-auto-scaling/))

**Configuration facts** ([asg-capacity-providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)):
- The ASG must have `MaxSize > 0` to scale out.
- The ASG **can't use instance weighting settings**.
- Prefer a **new, empty ASG** (desired count 0). Reusing an ASG whose instances were already registered can leave them not properly associated with the capacity provider.
- Don't hand-edit the scaling policy ECS created.
- Use **managed instance draining** (on by default) for graceful termination so tasks reschedule before the instance goes away.

---

## The Mixed-Instance-Type ASG Constraint

This is the precise, correct form of the widely-repeated "capacity providers don't support mixed-instance ASGs" claim. **Managed scaling with a mixed-instance-type ASG is supported, but bin-packs against the smallest instance type**, which creates a trap:

When an ASG has multiple instance types, ECS sorts them by vCPU, memory, ENIs, ports, and GPUs, and selects the smallest and largest for each parameter. **If a group of tasks has resource requirements greater than the smallest instance type in the ASG, that group cannot run with this capacity provider — the provider does not scale the ASG, and the tasks stay stuck in `PROVISIONING`.** ([managed-scaling-behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html))

**Best practice (from the same doc):** create **separate ASGs and capacity providers for different minimum resource requirements**, and only add a capacity provider to a strategy if the task can run on the smallest instance type in that ASG. Use placement constraints for other parameters.

**Practical rule:** one resource profile per ASG + capacity provider. Don't mix a `c5.large` and a `c5.24xlarge` in one managed-scaling ASG expecting large tasks to land — they'll hang. This is also the basis of the **separate-ASG-per-GPU-type** pattern (see `ecs-genai`).

**Bin-pack on the hard limit — memory, not CPU** (field heuristic). When you pack tasks onto shared instances, size and reason off **memory**: container-level `cpu` is a *soft* share (containers burst into unused CPU), so CPU overcommit is invisible and tasks still get placed even when CPU looks "full," whereas the container `memory` hard limit OOM-kills on breach. Note the softness is at the container-share level — the **task-level `cpu` value is itself a hard ceiling** for the whole task. The strategy *configuration* is **EC2/ASG-only**: memory bin-packing (`binpack` on `memory`) combined with `spread` across `availabilityZone` gives a predictable, safe density guarantee on EC2 capacity providers (see [architecture-design.md](architecture-design#task-placement-ec2)). **Managed Instances does not support task placement strategies** — ECS places for you (best-effort AZ spread, driven by the capacity-provider launch template, task requirements, and placement *constraints*); the memory-not-CPU sizing heuristic still applies to MI task definitions, but there is no `binpack`/`spread` knob to set. ([task definition CPU/memory parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) · [task placement — "Amazon ECS Managed Instances does not support task placement strategies"](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement.html))

---

## Scale-In Edge Cases

The richest source of production pain (from the field). Design against these:

- **Instances won't scale in / "empty" instances linger** — managed termination protection intentionally keeps instances that host non-daemon tasks. Combine ASG scale-in protection + capacity-provider managed termination protection, and use **managed instance draining** so tasks drain gracefully. ([Configure capacity provider to retain instances with running tasks](https://repost.aws/knowledge-center/ecs-retain-instances-running-tasks-auto-scaling))
- **Tasks stuck in `PROVISIONING`** — usually the mixed-ASG constraint above, or `MaxSize` too low, or the ASG can't scale to accommodate the tasks. ([asg-capacity-providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html))
- **Critical tasks killed on scale-in** — use **task protection** (`update-task-protection`) to stop ECS from stopping the task; note this doesn't stop the *instance* from terminating on its own, so pair with the ASG/capacity-provider protections. ([re:Post — retain instances](https://repost.aws/knowledge-center/ecs-retain-instances-running-tasks-auto-scaling))

Deeper scale-in scoring for a *live* estate belongs to `ecs-operation-review`; this reference is for designing the strategy up front.

---

## Fargate Spot

`FARGATE_SPOT` provides interruptible Fargate capacity at a discount. Interruptions come with a **two-minute warning** before the task is stopped (sent as a task state change event to EventBridge and a SIGTERM to the task), so pair it with graceful shutdown (`stopTimeout` ≤ 120s) and, for services, a `FARGATE` base for a resilient floor (see the base/weight table above). Suitable for stateless, retry-tolerant, and batch workloads. Quantify the discount and blast-radius trade-off with `ecs-cost-intelligence`. ([Fargate Spot termination notices — ECS clusters for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html))

---

## Managed Instances Capacity Provider

The Managed Instances capacity provider lets you constrain instance selection by attributes or explicit types (GPU, network-optimized, burstable), while AWS handles provisioning, placement, patching (drain from day 14, instance replaced no later than day 21 — [Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html)), and scaling. Because it is a capacity provider, services must use `capacityProviderStrategy`. The `capacityOptionType` parameter picks the purchase model — `on-demand` (default), `spot` (up to 90% off, two-minute warning; Dec 2025), or `reserved` (EC2 Capacity Reservations with reservations-only / reservations-first / reservations-excluded preferences; Feb 2026). See [model-selection-framework.md](model-selection-framework#ecs-managed-instances) for GA/Region facts and pricing. ([Announcing Amazon ECS Managed Instances — News Blog](https://aws.amazon.com/blogs/aws/announcing-amazon-ecs-managed-instances-for-containerized-applications/) · [Managed Instances + Spot](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-ecs-managed-instances-ec2-spot-instances/) · [Managed Instances + Capacity Reservations](https://aws.amazon.com/about-aws/whats-new/2026/02/ecs-mi-ec2-capacity-reservations/))

---

## Sources

- [Amazon ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html) — scale-out algorithm, mixed-ASG constraint, PROVISIONING
- [Amazon ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html) — ASG requirements, managed draining
- [Deep Dive on Amazon ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/deep-dive-on-amazon-ecs-cluster-auto-scaling/) — `CapacityProviderReservation` metric
- [Configure capacity provider to retain instances with running tasks](https://repost.aws/knowledge-center/ecs-retain-instances-running-tasks-auto-scaling) — scale-in protection, task protection
- [update-service CLI reference](https://docs.aws.amazon.com/cli/v1/reference/ecs/update-service.html) — capacity-provider strategy for Managed Instances, valid transitions
- [Amazon ECS Managed Instances now supports EC2 Spot Instances (Dec 2025)](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-ecs-managed-instances-ec2-spot-instances/) · [Managed Instances + EC2 Capacity Reservations (Feb 2026)](https://aws.amazon.com/about-aws/whats-new/2026/02/ecs-mi-ec2-capacity-reservations/) — `capacityOptionType`
- [AWS::ECS::Service CapacityProviderStrategyItem — `base`](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-ecs-service-capacityproviderstrategyitem.html) — only one provider may define a non-zero base
- [Amazon ECS clusters for Fargate — Fargate Spot termination notices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html) — two-minute warning, SIGTERM/EventBridge, `stopTimeout`
- [Amazon ECS task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) — soft container CPU share vs hard task-level CPU ceiling
- [How Amazon ECS places tasks on container instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement.html) — MI does not support placement strategies; EC2 strategy/constraint semantics
