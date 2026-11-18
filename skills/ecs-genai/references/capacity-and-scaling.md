# Capacity & Scaling — GPU at Scale on Amazon ECS

The mechanics that make ECS-GPU capacity different from EKS. There is **no Karpenter on native ECS** — capacity is Auto Scaling groups + ECS capacity providers, with a scaling behavior that dictates the whole GPU pattern. (Freshness: Capacity Blocks instance list + Managed Instances facts verified against live AWS docs **2026-07-10** — this is a fast-moving list; re-verify against the cited pages.)

> **Scope note:** This file covers the GPU-specific capacity story. For the generic capacity-provider mechanics — the `CapacityProviderReservation` formula, strategy-shape constraints, managed instance draining — route to **`ecs-architect`** / [ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html). What follows is only what changes because the instances carry GPUs.

## Step Zero — EC2 Service Quotas (the most common first blocker)

Before any ASG or capacity provider exists, the account must have vCPU quota for the GPU/accelerated families. **Running On-Demand P, G/VT, Inf, and Trn instances each have their own vCPU-based quota** (e.g. "Running On-Demand P instances"), and default quotas for accelerated families can be **0 vCPUs** (the quota table shows e.g. Running On-Demand DL instances default 0) — often too low to launch even one large GPU instance ([EC2 On-Demand Instance quotas](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-on-demand-instances.html#ec2-on-demand-instances-limits)); Spot has separate per-family vCPU quotas. Check and request increases in the **Service Quotas console** (or `aws service-quotas request-service-quota-increase`) *before* the capacity design — a `PROVISIONING`-stuck task or an ASG that won't scale out is frequently a quota failure, not a capacity one. Quota increases for large P-family counts can take days and are not guaranteed.

## One Homogeneous ASG Per GPU Type (the crux)

Cluster auto scaling **does support an Auto Scaling group with multiple instance types** ([ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html) explicitly lists this) — so this is **best practice, not a hard limit**. The reasons a heterogeneous *GPU* ASG is nonetheless a trap:

1. **No instance weighting.** An ECS capacity-provider ASG **can't have instance weighting settings** ([ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)), so the scaling math can't account for one GPU type being worth more than another.
2. **Managed scaling bin-packs and protects on the *smallest* instance type.** When an ASG has multiple instance types, ECS sorts them by vCPU/memory/ENI/port/GPU parameters and uses the **smallest** type's values as *protection*: "If a group of tasks have resource requirements that are greater than the smallest instance type in the Auto Scaling group, then that group of tasks can't run with this capacity provider… The tasks remain in the `PROVISIONING` state." AWS's own recommendation is to "create separate Auto Scaling groups and capacity providers for different minimum resource requirements" ([ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html)).
3. **No native "GPU model / VRAM" placement attribute.** A `resourceRequirements` `GPU: 1` only counts GPUs, not their memory. If a g4dn (16 GiB, T4) and a g5 (24 GiB, A10G) share one ASG, ECS can place a task needing 24 GiB onto the 16 GiB T4 and the model OOMs at load time. Homogeneous per-type ASGs (pin `allowedInstanceTypes` in the launch template) keep placement correct; use a placement constraint on `ecs.instance-type` to steer within a mixed cluster.

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

GPU-relevant reminders (the full strategy-shape rules — the ≤20-provider limit, base/weight semantics, ASG-vs-Fargate exclusivity, launchType migration — are generic capacity-provider mechanics; see `ecs-architect` / the capacity-providers doc):
- Create the empty GPU ASG with **desired = 0**; ECS scales it out via managed scaling.
- A strategy can't mix ASG and Fargate capacity providers — moot here, since Fargate can't run GPU anyway.

### Karpenter equivalent? No.

There is no Karpenter for native ECS. The closest "AWS picks the instance" experience is **ECS Managed Instances** (below), or, if the customer truly wants Karpenter-style provisioning, that is an argument for **EKS (`eks-genai`)**.

## ECS Managed Instances — the AWS-managed alternative

Instead of hand-rolling one ASG per GPU type, **ECS Managed Instances** lets AWS provision, configure, patch (drain initiated every 14 days; termination no later than day 21), scale, and place tasks on optimal EC2 instances, while you declare requirements ([Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/)). You still select GPU/accelerator families through the capacity provider's **`instanceRequirements`** launch template (see [compute-hardware.md](compute-hardware.md) and [neuron-on-ecs.md](neuron-on-ecs.md)). Trade-offs:

- **Pro:** No ASG plumbing, no AMI/driver management, faster to stand up, per-type homogeneity handled by AWS.
- **Con:** A **management charge** on top of the EC2 instance price, billed per-second with a one-minute minimum ([ECS Managed Instances pricing](https://aws.amazon.com/ecs/managed-instances/pricing/)); less control than self-managed EC2 (no custom kernel/AMI). For custom AMI/kernel or the most demanding multi-node EFA training, self-managed ECS-on-EC2 remains the choice.
- **Instance lifetime caveat for training:** Managed Instances patches by drain-and-replace on a **14-21 day instance lifecycle** — draining initiated at day 14 from launch, termination no later than day 21; you can use EC2 event windows to schedule it into weekly maintenance windows ([ECS Managed Instances FAQs](https://aws.amazon.com/ecs/managed-instances/faqs/), [Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html)). That is fine for inference, but a **multi-week training run can be interrupted mid-flight** — so multi-week runs need robust checkpoint/resume (see [distributed-training.md](distributed-training.md)), or should run on a self-managed ASG / Capacity Block instead.
- GA Sept 2025; available in all commercial Regions since Oct 2025.

## EC2 Capacity Blocks for ML — securing scarce GPU capacity

GPU capacity is scarce. **EC2 Capacity Blocks for ML** let you reserve accelerated instances for a future window, colocated in EC2 UltraClusters with EFA ([EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/)). Current facts (**verified against live AWS docs 2026-07-10 — the supported-type list moves fast; always re-check the cited pages**):

- **Single Availability Zone.** A Capacity Block is delivered as a **`targeted` Capacity Reservation in one AZ** ([Use Capacity Blocks for ML workloads (EC2 Auto Scaling)](https://docs.aws.amazon.com/autoscaling/ec2/userguide/launch-template-capacity-blocks.html)). This is not stated as a passing detail: it means you must **pin the ASG to that AZ's subnet** and **co-locate FSx for Lustre in the same AZ** ([storage.md](storage.md)) — a cross-AZ block/FSx layout silently underperforms or won't place.
- **Supported instance types** (per the Capacity Blocks page, verified 2026-07-10). *Instance* Capacity Blocks: **P6-B300, P6-B200, P5en, P5e, P5, P4d, P4de** (NVIDIA Blackwell / H200 / H100 / A100), plus **Trn2 and Trn1** (AWS Trainium). *UltraServer* Capacity Blocks (a separate table with extra rules — non-shareable across accounts, and P6e-GB200 instances must be terminated ≥60 minutes before the block end time): **Trn2 and P6e-GB200** — P6e-GB200 is UltraServer-only, not an Instance Capacity Block type ([Capacity Blocks for ML — supported instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html)). Capacity Blocks cover **P- and Trn-family only** — there is no g6e Capacity Block, so for assured g6e/inference capacity use **ODCRs** or Managed Instances Capacity Reservations instead (below).
- **Reservation duration** is 1–14 days, or a multiple of 7 days up to **182 days**; reservable with a start time **up to 8 weeks in advance**. Each Capacity Block can have **up to 64 instances**, and **up to 256 instances across Capacity Blocks** ([How Capacity Blocks work](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-how.html)). Instance Capacity Blocks are shareable across accounts (UltraServer Capacity Blocks are not).
- **Cancellations aren't allowed, but a block CAN be extended.** An `active` or `scheduled` block can be extended (subject to available capacity) in 1-day increments up to 14 days and 7-day increments up to 182 days total, from 1 hour to 57 days before it expires, with no limit on the number of extensions — the reservation ID stays the same ([Extend Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-extend.html)). Plan the initial window, but know you can extend a run rather than re-reserving.
- **Pricing = reservation fee + OS fee.** AWS publishes **no fixed discount vs on-demand** — the value is **guaranteed capacity assurance**, not a headline discount. Do not claim a percentage saving.
- Best for: planned pre-training/fine-tuning runs, benchmark campaigns, guaranteed-capacity demos. Not for elastic inference (Capacity Blocks don't autoscale).

Use with ECS by launching the reserved instances into a **self-managed GPU ASG capacity provider** for the reservation window: create the ASG's launch template to target the Capacity Block reservation, **restrict the ASG to the block's AZ subnet**, and — because managed scaling doesn't know the block's expiration — **schedule scale-up at the block start** (Auto Scaling scheduled scaling handles retries) and **drain/checkpoint before it ends** (the block begins terminating instances 30 minutes before end time; an EventBridge event fires 10 minutes before that). The reserved-capacity ASG path is the documented integration; wiring Capacity Blocks directly into an ECS Managed Instances capacity provider is not a documented pattern — fall back to the self-managed ASG for reserved-capacity use cases. Reference: [Capacity Blocks for ML (EC2 User Guide)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html), [How Capacity Blocks work](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-how.html).

### Assured capacity without a Capacity Block (P/Trn only cover part of the story)

For inference families that Capacity Blocks don't cover (e.g. g6e), get capacity assurance with:
- **On-Demand Capacity Reservations (ODCRs)** in a specific AZ, consumed by a self-managed ASG launch template — the general-purpose assured-capacity lever for g-family inference.
- **Managed Instances Capacity Reservations:** set `capacityOptionType: Reserved` on the capacity provider and supply a **Capacity Reservation group** ([ECS Managed Instances instance types — billing and purchase options](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-instance-types.html)); you can also set a reservation preference (`reservations-only`, `reservations-first`, `reservations-excluded`).
> **Reservation-vs-support mismatch to flag:** Capacity Blocks / ODCRs can reserve instance types (P6, P5en, …) that the **ECS-on-EC2 GPU support table stops short of** (it currently ends at p5/g6e). Managed Instances' accelerated list is broader (see [compute-hardware.md](compute-hardware.md)). Before reserving, confirm the target instance type is actually consumable by the ECS launch model you intend to use, or you may reserve a block ECS-on-EC2 can't schedule onto.

## Spot vs On-Demand for GPU on ECS

| Workload | Capacity type | Condition |
|---|---|---|
| **Training** | Spot | ✅ Only with checkpoint/resume wired (see [distributed-training.md](distributed-training.md)) — but see the P-family caveat below |
| **Training** | On-Demand / Capacity Blocks | When the job can't tolerate interruption |
| **Inference (production, SLA-bound)** | On-Demand | Always — Spot interruptions break per-request SLAs |
| **Dev / experimentation** | Spot | ✅ Tolerable interruption profile |

**P-family Spot availability caveat:** the "Large savings" story for Spot training assumes the capacity exists. GPU capacity is scarce (the whole reason Capacity Blocks exist), and **large NVIDIA GPU instances — p4d/p5/p5en — are frequently unobtainable on Spot and carry high interruption rates** — verify the current picture for your type/Region with the [Spot Instance Advisor](https://aws.amazon.com/ec2/spot/instance-advisor/) (interruption frequency) and the [Spot placement score](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-placement-score.html) (likelihood a Spot request succeeds). Treat P-family Spot as opportunistic, not a capacity plan: for guaranteed multi-day training use **On-Demand or Capacity Blocks**; reserve Spot for smaller/interruption-tolerant phases with checkpoint/resume, and check the placement score / interruption history for the type and AZ first.

**Spot without checkpoint/resume is a guaranteed cost-burn** — every interruption restarts training. Use **managed instance draining** (on by default) for graceful task rebalancing when instances terminate ([ECS capacity providers for EC2](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)). Note: separate **Spot and On-Demand into different ASGs/capacity providers**, and keep GPU *types* separated per the crux above (one homogeneous GPU type per ASG).

## Cluster Auto Scaling Behavior & Latency

ECS cluster auto scaling is a **CloudWatch-driven, latent** process ([Optimize ECS cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html)):

- Scale-out/in reacts to the `CapacityProviderReservation` metric breaching alarms; there is inherent lag from metric publish + alarm evaluation + EC2 warm-up.
- **Scale-in requires ~15 minutes of data points** before reducing capacity, then steps down gradually ([Faster Scaling-in for ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/faster-scaling-in-for-amazon-ecs-cluster-auto-scaling/)). This matters for expensive GPU nodes — idle GPU minutes are costly.
- Speed levers: use **warm pools** of pre-initialized GPU instances (supported by ECS ASG capacity providers) to cut GPU-instance warm-up time; keep GPU AMIs lean; pre-cache large model images (see [storage.md](storage.md)).

## Cost Levers (priority order)

| Priority | Lever | Directional value | Caveat |
|---|---|---|---|
| 1 | **Capacity Blocks for ML** | Capacity *assurance* (not a fixed discount) | Reservation + OS fee; no autoscale; advance reservation |
| 2 | **Neuron over GPU** | Cost-optimized for supported Transformer models | Compilation ramp; verify model support ([neuron-on-ecs.md](neuron-on-ecs.md)) |
| 3 | **Spot + checkpoint/resume** | Large savings for fault-tolerant training | Requires checkpoint logic; not for SLA inference |
| 4 | **Right-size GPU instance family** | Avoids paying for idle GPU memory/compute | Match model size to instance; measure first |
| 5 | **Cluster auto scaling / Managed Instances consolidation** | Reclaims idle GPU nodes off-peak | Scale-in latency (~15 min); warm pools mitigate cold-start |
| 6 | **GPU sharing (dev only)** | Density for dev/test | No isolation — dev/test only ([compute-hardware.md](compute-hardware.md)) |

Always give **directional ranges with caveats** — never point estimates. Actual savings depend on model size, traffic pattern, batch size, sequence length, and configuration.

## Sources

- [Amazon ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)
- [Amazon ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html) (multiple instance types supported; bin-packs/protects on the smallest type)
- [Automatically manage Amazon ECS capacity with cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html)
- [Extend Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-extend.html) · [Use Capacity Blocks for ML workloads (single-AZ, EC2 Auto Scaling)](https://docs.aws.amazon.com/autoscaling/ec2/userguide/launch-template-capacity-blocks.html)
- [ECS Managed Instances instance types (billing / Capacity Reservations)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-instance-types.html) · [Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html) · [ECS Managed Instances pricing](https://aws.amazon.com/ecs/managed-instances/pricing/)
- [Optimize Amazon ECS cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html)
- [Deep Dive on Amazon ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/deep-dive-on-amazon-ecs-cluster-auto-scaling/)
- [Faster Scaling-in for Amazon ECS Cluster Auto Scaling](https://aws.amazon.com/blogs/containers/faster-scaling-in-for-amazon-ecs-cluster-auto-scaling/)
- [Optimize cost for container workloads with ECS capacity providers and EC2 Spot Instances](https://aws.amazon.com/blogs/containers/optimize-cost-for-container-workloads-with-ecs-capacity-providers-and-ec2-spot-instances/)
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/) · [Capacity Blocks for ML (EC2 User Guide)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html)
- [Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/) · [Managed Instances now in all commercial Regions](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-managed-instances-commercial-regions/)
