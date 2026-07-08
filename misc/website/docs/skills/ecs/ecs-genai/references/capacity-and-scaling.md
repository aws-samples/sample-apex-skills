---
title: "Capacity & Scaling — GPU at Scale on Amazon ECS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/capacity-and-scaling.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-genai/references/capacity-and-scaling.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/capacity-and-scaling.md). Edit the source, not this page.
:::

# Capacity & Scaling — GPU at Scale on Amazon ECS

The mechanics that make ECS-GPU capacity different from EKS. There is **no Karpenter on native ECS** — capacity is Auto Scaling groups + ECS capacity providers, with a hard structural constraint that dictates the whole pattern.

## The Separate-ASG-Per-GPU-Type Pattern (the crux)

**An ECS capacity-provider Auto Scaling group can't have instance weighting settings** ([ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)). ECS cluster auto scaling drives the ASG via a single `CapacityProviderReservation` target-tracking metric that assumes the instances in that ASG are effectively **homogeneous** — the formula is `(instances needed) / (running instances) × 100` ([Automatically manage ECS capacity with cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html)). Mixing heterogeneous GPU types (e.g. g5 + p4d) in one ASG breaks the scaling math and makes task placement non-deterministic.

There is a second, sharper failure mode: **ECS task placement has no native "GPU model / VRAM" attribute** — a `resourceRequirements` `GPU: 1` only counts GPUs, not their memory. If a g4dn (16 GiB, T4) and a g5 (24 GiB, A10G) share one ASG, ECS can place a task needing 24 GiB onto the 16 GiB T4, and the model OOMs at load time. Homogeneous per-type ASGs (pin `allowedInstanceTypes` in the launch template) are what keep placement correct; use a placement constraint on `ecs.instance-type` to steer within a mixed cluster.

**Therefore, the pattern for GPU at scale on native ECS:**

1. **One Auto Scaling group per GPU instance type** (one for g5, one for g6e, one for p4d, …), each homogeneous.
2. **One ECS capacity provider per ASG**, with **managed scaling** and **managed termination protection** on.
3. **Blend them with a capacity-provider strategy** on the service — `base`/`weight` to prefer one pool and spill to another, rather than one mixed ASG.

```json
// Service capacity-provider strategy: prefer g6e for inference, spill to g5
{
  "capacityProviderStrategy": [
    { "capacityProvider": "cp-g6e", "base": 1, "weight": 3 },
    { "capacityProvider": "cp-g5",  "base": 0, "weight": 1 }
  ]
}
```

Constraints to respect (from the capacity-providers doc):
- A capacity-provider strategy can specify **at most 20 capacity providers**.
- At least one capacity provider must have **weight > 0**; only one may set a **base**.
- A strategy can contain **either** ASG capacity providers **or** Fargate capacity providers — **not both**. (And Fargate can't run GPU anyway.)
- You **can't switch** a service between an ASG capacity provider and a Fargate capacity provider without recreating/redeploying; moving a service from `launchType` to a capacity-provider strategy requires a **forced new deployment**.
- Create the empty ASG with **desired = 0**; ECS scales it out via managed scaling.

### Karpenter equivalent? No.

There is no Karpenter for native ECS. The closest "AWS picks the instance" experience is **ECS Managed Instances** (below), or, if the customer truly wants Karpenter-style provisioning, that is an argument for **EKS (`eks-genai`)**.

## ECS Managed Instances — the AWS-managed alternative

Instead of hand-rolling one ASG per GPU type, **ECS Managed Instances** lets AWS provision, configure, patch (every 14 days), scale, and place tasks on optimal EC2 instances, while you declare requirements ([Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/)). You still select GPU/accelerator families through the capacity provider's **`instanceRequirements`** launch template (see [compute-hardware.md](compute-hardware) and [neuron-on-ecs.md](neuron-on-ecs)). Trade-offs:

- **Pro:** No ASG plumbing, no AMI/driver management, faster to stand up, per-type homogeneity handled by AWS.
- **Con:** A management charge on top of EC2 cost; less control than self-managed EC2 (no custom kernel/AMI). For custom AMI/kernel or the most demanding multi-node EFA training, self-managed ECS-on-EC2 remains the choice.
- GA Sept 2025; available in all commercial Regions since Oct 2025.

## EC2 Capacity Blocks for ML — securing scarce GPU capacity

GPU capacity is scarce. **EC2 Capacity Blocks for ML** let you reserve accelerated instances for a future window, colocated in EC2 UltraClusters with EFA ([EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/)). Verified current facts:

- **Supported instance types** (per the Capacity Blocks page): P6e-GB200, P6-B300, P6-B200, P5en, P5e, P5, and P4d (NVIDIA Blackwell / H200 / H100 / A100), plus **Trn2 and Trn1** (AWS Trainium).
- **Reservation duration** is 1–14 days, or a multiple of 7 days up to **182 days** (e.g. 21, 28 days); reservable with a start time **up to 8 weeks in advance**. Each Capacity Block can have **up to 64 instances**, and **up to 256 instances across Capacity Blocks** ([How Capacity Blocks work](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-how.html)). Instance Capacity Blocks are shareable across accounts (UltraServer Capacity Blocks are not).
- **Pricing = reservation fee + OS fee.** AWS publishes **no fixed discount vs on-demand** — the value is **guaranteed capacity assurance**, not a headline discount. Do not claim a percentage saving.
- Best for: planned pre-training/fine-tuning runs, benchmark campaigns, guaranteed-capacity demos. Not for elastic inference (Capacity Blocks don't autoscale).

Use with ECS by launching the reserved instances into a **self-managed GPU ASG capacity provider** for the reservation window: create the ASG's launch template to target the Capacity Block reservation, and — because managed scaling doesn't know the block's expiration — **schedule scale-up at the block start** (Auto Scaling scheduled scaling handles retries) and **drain/checkpoint before it ends** (the block begins terminating instances 30 minutes before end time; an EventBridge event fires 10 minutes before that). The reserved-capacity ASG path is the documented integration; wiring Capacity Blocks directly into an ECS Managed Instances capacity provider is not a documented pattern — fall back to the self-managed ASG for reserved-capacity use cases. Reference: [Capacity Blocks for ML (EC2 User Guide)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html), [How Capacity Blocks work](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-how.html).

## Spot vs On-Demand for GPU on ECS

| Workload | Capacity type | Condition |
|---|---|---|
| **Training** | Spot | ✅ Only with checkpoint/resume wired (see [distributed-training.md](distributed-training)) |
| **Training** | On-Demand / Capacity Blocks | When the job can't tolerate interruption |
| **Inference (production, SLA-bound)** | On-Demand | Always — Spot interruptions break per-request SLAs |
| **Dev / experimentation** | Spot | ✅ Tolerable interruption profile |

**Spot without checkpoint/resume is a guaranteed cost-burn** — every interruption restarts training. Use **managed instance draining** (on by default) for graceful task rebalancing when instances terminate ([ECS capacity providers for EC2](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)). Note: separate **Spot and On-Demand into different ASGs/capacity providers** (a single ASG mixing purchase options with per-type homogeneity is fine via a MixedInstancesPolicy for *sizes*, but keep GPU *types* separated per the crux above).

## Cluster Auto Scaling Behavior & Latency

ECS cluster auto scaling is a **CloudWatch-driven, latent** process ([Optimize ECS cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html)):

- Scale-out/in reacts to the `CapacityProviderReservation` metric breaching alarms; there is inherent lag from metric publish + alarm evaluation + EC2 warm-up.
- **Scale-in requires ~15 minutes of data points** before reducing capacity, then steps down gradually ([Faster Scaling-in for ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/faster-scaling-in-for-amazon-ecs-cluster-auto-scaling/)). This matters for expensive GPU nodes — idle GPU minutes are costly.
- Speed levers: use **warm pools** of pre-initialized GPU instances (supported by ECS ASG capacity providers) to cut GPU-instance warm-up time; keep GPU AMIs lean; pre-cache large model images (see [storage.md](storage)).

## Cost Levers (priority order)

| Priority | Lever | Directional value | Caveat |
|---|---|---|---|
| 1 | **Capacity Blocks for ML** | Capacity *assurance* (not a fixed discount) | Reservation + OS fee; no autoscale; advance reservation |
| 2 | **Neuron over GPU** | Cost-optimized for supported Transformer models | Compilation ramp; verify model support ([neuron-on-ecs.md](neuron-on-ecs)) |
| 3 | **Spot + checkpoint/resume** | Large savings for fault-tolerant training | Requires checkpoint logic; not for SLA inference |
| 4 | **Right-size GPU instance family** | Avoids paying for idle GPU memory/compute | Match model size to instance; measure first |
| 5 | **Cluster auto scaling / Managed Instances consolidation** | Reclaims idle GPU nodes off-peak | Scale-in latency (~15 min); warm pools mitigate cold-start |
| 6 | **GPU sharing (dev only)** | Density for dev/test | No isolation — dev/test only ([compute-hardware.md](compute-hardware)) |

Always give **directional ranges with caveats** — never point estimates. Actual savings depend on model size, traffic pattern, batch size, sequence length, and configuration.

## Sources

- [Amazon ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)
- [Automatically manage Amazon ECS capacity with cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html)
- [Optimize Amazon ECS cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html)
- [Deep Dive on Amazon ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/deep-dive-on-amazon-ecs-cluster-auto-scaling/)
- [Faster Scaling-in for Amazon ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/faster-scaling-in-for-amazon-ecs-cluster-auto-scaling/)
- [Optimize cost for container workloads with ECS capacity providers and EC2 Spot Instances](https://aws.amazon.com/blogs/containers/optimize-cost-for-container-workloads-with-ecs-capacity-providers-and-ec2-spot-instances/)
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/) · [Capacity Blocks for ML (EC2 User Guide)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html)
- [Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/) · [Managed Instances now in all commercial Regions](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-managed-instances-commercial-regions/)
