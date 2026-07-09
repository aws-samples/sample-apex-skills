---
name: ecs-genai
description: "Use whenever someone runs a GPU / ML / GenAI / LLM workload on Amazon ECS — GPU on ECS, ECS GPU-optimized AMI, g4dn/g5/g6/p4/p5 on ECS, which ECS launch type for GPU, Inferentia/Trainium/Neuron on ECS, distributed training on ECS, model inference on ECS, Capacity Blocks for ECS, GPU sharing, or ASG per GPU type. Covers GPU compute on ECS-on-EC2 and ECS Managed Instances (GPU-optimized AMIs, NVIDIA runtime, instance families); the capacity pattern where mixed-instance ASGs are supported but constrained (no weighting; managed scaling protects on the smallest type, so one homogeneous ASG per GPU type is best practice); Capacity Blocks; inference/serving; Neuron; distributed ML; GPU observability; a GPU/ML security slice. AWS Fargate has NO GPU — use ECS-on-EC2, Managed Instances, or ECS Anywhere. Trigger even if GenAI is unsaid. Use eks-genai for Kubernetes/EKS; SageMaker for fully-managed ML; Bedrock for managed foundation models; ecs-architect for non-accelerator ECS design; ecs-security for deep compliance."
---

<!-- Note: ecs-genai intentionally ships no `apex:ecs-genai` steering command (eks-genai has one). This is an omission, not by design — steering-command wiring is deferred repo-wide, so it is left unwired for now to match the rest of the ECS skills. Freshness: instance/spec claims verified against live AWS docs 2026-07-09. -->

# GenAI / GPU / ML Workloads on Amazon ECS

End-to-end opinionated guidance for running GPU-accelerated, ML-training, and GenAI inference workloads on **Amazon ECS-on-EC2**. This skill is scoped to the compute-and-capacity mechanics that are unique to ECS: the GPU-optimized AMI + NVIDIA container runtime, the **one-homogeneous-ASG-per-GPU-type capacity-provider pattern** — cluster auto scaling *supports* multiple instance types in one ASG, but managed scaling has no instance weighting and bin-packs and protects on the **smallest** instance type, so mixing GPU types (with different GPU counts / VRAM) breaks the scaling math; one homogeneous ASG per GPU type is therefore the best practice, not a hard limit — plus EC2 Capacity Blocks for ML, AWS Neuron (Inferentia/Trainium) on ECS, container inference/serving, distributed ML, and accelerator observability.

**The single most important constraint, stated first: AWS Fargate has no GPU support.** GPUs and AWS accelerators (Inferentia/Trainium) are available only on **ECS-on-EC2**, **ECS Managed Instances**, and **ECS Anywhere/External** — never on Fargate. Every GPU/ML answer on ECS begins by ruling Fargate out for the accelerated container. See [service-boundaries.md](references/service-boundaries.md) for the exact evidence and the "use EKS / SageMaker / Bedrock instead" routing.

For "which ECS launch model should I use" with no accelerator or ML workload, use `ecs-architect`. For Kubernetes-based GenAI, use `eks-genai`. This skill is the GPU/ML *workload* layer on ECS specifically.

## When to Use This Skill

**Activate when the user wants to:**
- Run a GPU workload on ECS — choose an instance family (g4dn/g5/g6/g6e/p3/p4d/p5), the ECS GPU-optimized AMI, and the NVIDIA container runtime
- Serve an LLM / model inference container on ECS, or run ML training/fine-tuning on ECS
- Design GPU capacity on ECS at scale — the separate-ASG-per-GPU-type + capacity-provider-strategy pattern, Managed Instances, Spot, and Capacity Blocks for ML
- Use AWS Neuron (Inferentia/Trainium) on ECS — device allocation, compilation, Inf/Trn instance selection
- Wire GPU/accelerator observability on ECS — agentless DCGM metrics via Container Insights enhanced observability are **Managed-Instances-only**; the EC2 launch type needs the CloudWatch agent (`nvidia_smi`, host-level) or a DCGM exporter for per-task metrics
- Decide **when NOT to use ECS** — when EKS (`eks-genai`), SageMaker, or Bedrock is the better home

**Don't use this skill for:**
- **Kubernetes / EKS GenAI** (Karpenter, KubeRay, JARK, device plugins, vLLM-on-EKS) → `eks-genai`
- **Fully-managed ML training or model hosting** with no container orchestration to own → **Amazon SageMaker** (training jobs, endpoints, HyperPod)
- **Managed foundation-model API with no self-hosting** (no GPU to manage) → **Amazon Bedrock**
- **Generic ECS launch-type selection / cluster design** with no accelerator or ML workload → `ecs-architect`
- **Deep Neuron kernel / NKI / model-porting** work → the Neuron-specific skills, not this one
- **Deep ECS security / regulated-compliance baseline** (PCI/HIPAA/FedRAMP CDE design, org-wide guardrails, threat modeling) → `ecs-security`; this skill carries only the GPU/ML-specific security slice
- Any assumption that **Fargate can run a GPU** — it cannot; do not design around it

## The ECS-GPU Decision Framework

Walk the customer through five decisions, top to bottom. Depth for each is in the references.

```text
D1  Compute host      ECS-on-EC2 · ECS Managed Instances · ECS Anywhere   (NEVER Fargate for GPU)
D2  Accelerator       NVIDIA GPU (g4dn/g5/g6/g6e/p3/p4d/p5) · AWS Neuron (Inf2/Trn1/Trn2)
D3  Capacity model    separate ASG per GPU type + capacity-provider strategy · Managed Instances · Capacity Blocks · Spot
D4  Workload shape    single-container inference · distributed multi-node training · GPU-shared dev
D5  Boundary check    stay on ECS · or route to eks-genai / SageMaker / Bedrock
```

### D1 — Compute host: Fargate is out for GPU (first-class caveat)

**AWS Fargate cannot run GPU or AWS-accelerator workloads.** AWS lists the `gpu` parameter among the task-definition parameters that are **"not valid in Fargate tasks"** (alongside `devices` and `placementConstraints`), and the Fargate task-size model exposes only CPU and memory — valid task sizes run from 256 (.25 vCPU) up to 32768 (32 vCPU), with no GPU dimension at all ([ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)). The `resourceRequirements` `GPU` type and `NeuronDevice` allocation are container-instance (EC2) concepts only. GPU is supported on:

- **ECS-on-EC2** — you own the Auto Scaling group and the GPU-optimized AMI; full control (custom AMI/kernel, EFA, multi-node). The default for training and demanding inference.
- **ECS Managed Instances** — AWS provisions/patches (~every 14 days) the EC2 lifecycle for you; supports GPU (e.g. `g4dn`, `g5`, `p3`, `p4d`) with pre-installed NVIDIA drivers + CUDA ([Use GPUs with ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html)), and the managed `NeuronDevice` allocation path ([ECS task definitions for AWS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html)). GA Sept 2025, all commercial Regions Oct 2025.
- **ECS Anywhere / External** — on-prem/hybrid GPU hosts registered with `--enable-gpu`.

Also note: **GPUs are not supported on Windows containers on ECS** ([ECS GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)). Details: [compute-hardware.md](references/compute-hardware.md).

### D2 — Accelerator: NVIDIA GPU vs AWS Neuron

- **NVIDIA GPU** (g4dn/g5/g6/g6e inference; p3/p4d/p5 training) — broadest ecosystem, CUDA, fastest time-to-first-success, multi-modal/novel architectures. The ECS GPU-optimized AMI ships NVIDIA kernel drivers + the NVIDIA Docker runtime pre-installed.
- **AWS Neuron** (Inf2 inference; Trn1/Trn2 training; Inf1 legacy, EC2 launch type only) — cost-optimized for supported Transformer-family models on the ECS Neuron-optimized AL2023 AMI, at the price of a compilation ramp. Details: [compute-hardware.md](references/compute-hardware.md), [neuron-on-ecs.md](references/neuron-on-ecs.md).

Do not synthesize per-chip specs — cite the ECS GPU/Neuron doc tables. Right accelerator = f(model family × latency × cost posture × team skill × timeline).

### D3 — Capacity: one homogeneous ASG per GPU type (the ECS-specific crux)

This is where ECS diverges hardest from EKS. ECS cluster auto scaling **does support an Auto Scaling group with multiple instance types**, but the constraints make heterogeneous *GPU* ASGs a trap: **an ECS capacity-provider ASG can't have instance weighting settings** ([ECS capacity providers for EC2](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)), and managed scaling **bin-packs and protects on the smallest instance type in the ASG** — if a group of tasks needs more than the smallest type provides, that group can't run and the tasks stay `PROVISIONING` ([Amazon ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html)). Because `resourceRequirements` `GPU` counts GPUs but not VRAM, mixing GPU types (e.g. g5 24 GiB + p4d 40 GiB) also lets ECS place a large-VRAM task onto a small-VRAM instance and OOM at load. The best practice therefore: **use one homogeneous ASG (and one capacity provider) per GPU instance type**, and blend them with a **capacity-provider strategy**. There is no Karpenter equivalent on native ECS. Details: [capacity-and-scaling.md](references/capacity-and-scaling.md).

For scarce accelerator capacity, use **EC2 Capacity Blocks for ML** (reserve P/Trn UltraCluster capacity for a future window) — a Capacity Block is delivered in a **single Availability Zone**, so restrict the ASG to that AZ's subnet (and co-locate FSx in the same AZ). For assured non-block inference capacity use **On-Demand Capacity Reservations (ODCRs)** or, on Managed Instances, `capacityOptionType: Reserved` with a Capacity Reservation group. For cost, layer Spot only on interruption-tolerant work with checkpoint/resume. Managed Instances offers an AWS-managed alternative to hand-rolled ASGs.

### D4 — Workload shape

- **Single-container inference** — GPU task with `resourceRequirements` type `GPU`; model weights from S3/EFS. [inference-serving.md](references/inference-serving.md).
- **Distributed multi-node training** — placement groups + EFA + NCCL; Ray Train / PyTorch on ECS. [distributed-training.md](references/distributed-training.md).
- **GPU sharing for dev** — ECS pins whole GPUs by default; sharing is coarse (see the caveat below). [compute-hardware.md](references/compute-hardware.md).

### D5 — Boundary check

If the answer is "Kubernetes," "fully-managed training/hosting," or "no self-hosting at all," route out. [service-boundaries.md](references/service-boundaries.md).

## GPU Sharing on ECS — State the Limit Precisely

ECS, by default, **pins whole physical GPUs to containers** — the scheduler assigns the number of GPUs in `resourceRequirements` and sets `NVIDIA_VISIBLE_DEVICES` accordingly ([ECS GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)). Native ECS has **no MIG-partitioning or time-slicing-replica scheduler primitive** like the EKS NVIDIA device plugin. To share a GPU across ECS tasks you must **remove the GPU `resourceRequirements`** from the task definitions and make `nvidia` the **default Docker runtime** on the instance via user data, then set `NVIDIA_VISIBLE_DEVICES` per container — a manual, unisolated pattern suitable for dev/test only (no memory isolation between co-located containers). If the customer needs first-class fractional-GPU scheduling (MIG, time-slicing, DRA), that is an argument for **EKS (`eks-genai`)** or SageMaker. Details: [compute-hardware.md](references/compute-hardware.md).

## Security Baseline (non-negotiable)

Every GPU/ML-on-ECS recommendation MUST include: **task role + execution role least-privilege** (never static keys in the image/env); **secrets via Secrets Manager / SSM Parameter Store** injected into the task definition (never baked into the model image); **ECR image scanning** (DLC/CUDA/Neuron images carry huge CVE surfaces); **model-artifact provenance** (checksum/signing; pin exact model revisions); **private subnets + VPC endpoints** (S3 for weights, ECR, Secrets Manager, Bedrock-runtime if used) for GPU instances; **inference-endpoint authentication** (internal vs internet-facing ALB/NLB + auth in front of the model API — see [security-and-compliance.md](references/security-and-compliance.md)); and **CloudTrail + Container Insights** audit. Add **GuardDuty ECS Runtime Monitoring** on **ECS-on-EC2** hosts — but note it is **not supported on ECS Managed Instances, ECS Anywhere, or Windows** ([GuardDuty Runtime Monitoring considerations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html)), so an MI-based fleet needs a different runtime-threat control. For the deep, general ECS security baseline and regulated-compliance design, route to **`ecs-security`**; this skill carries only the GPU/ML-specific slice. Details: [security-and-compliance.md](references/security-and-compliance.md).

## Cost Optimization

Levers in priority order: (1) **Capacity Blocks for ML** for planned multi-day training (capacity assurance, not a fixed discount); (2) **Neuron over GPU** for supported Transformer models (compilation ramp, verify support first); (3) **Spot + checkpoint/resume** for fault-tolerant training only; (4) **right-size the GPU instance family** to the model (over-provisioning GPUs is a top cost mistake); (5) **cluster auto scaling / Managed Instances consolidation** for off-peak inference; (6) **share GPUs for dev** (dev/test only). Always give directional ranges with caveats — never point estimates. Details: [capacity-and-scaling.md](references/capacity-and-scaling.md).

## Top Guardrails (the high-cost mistakes)

- **Never design a GPU workload on Fargate** — it has no GPU; use ECS-on-EC2 / Managed Instances / Anywhere.
- **Don't mix GPU instance types in one capacity-provider ASG** — it's *allowed* but managed scaling protects on the smallest type and can't weight, so use one homogeneous ASG per GPU type + a capacity-provider strategy.
- **Don't assume native ECS has a MIG/time-slicing scheduler** — there is no fractional-GPU *scheduler* primitive; hardware-fractional L4 instances (G6f/Gr6f) exist on Managed Instances, but dynamic multi-model GPU packing (MIG/time-slicing/DRA) → EKS/SageMaker.
- **Don't compile Neuron models at task startup** — pre-compile offline, ship the artifact via S3/image.
- **Don't run distributed multi-node training without EFA + placement groups** — bandwidth collapses to TCP.
- **Don't use Spot for training without checkpoint/resume**, or for latency-SLA inference.
- **Don't skip the security baseline** — task-role trust, secrets, private subnets, image scanning, provenance.
- **Don't give point cost estimates** — directional ranges with caveats only.
- **Don't synthesize accelerator specs** — cite the ECS GPU/Neuron doc tables.

## How to Use the References

Progressive disclosure — the essentials are above; load a reference only when the task needs that depth:

| Reference | Load when the task is about… |
|-----------|------------------------------|
| [compute-hardware.md](references/compute-hardware.md) | GPU instance families, GPU-optimized AMI, NVIDIA runtime, GPU sharing limits, capacity planning |
| [capacity-and-scaling.md](references/capacity-and-scaling.md) | Separate-ASG-per-GPU-type, capacity-provider strategy, cluster auto scaling, Managed Instances, Capacity Blocks, Spot |
| [inference-serving.md](references/inference-serving.md) | Model inference containers on ECS, serving engines, model loading, autoscaling inference services |
| [distributed-training.md](references/distributed-training.md) | Multi-node GPU/Neuron training, EFA + placement groups, NCCL, Ray Train on ECS, checkpointing |
| [neuron-on-ecs.md](references/neuron-on-ecs.md) | Inferentia/Trainium on ECS, Neuron device allocation (managed vs manual), compilation, Inf/Trn selection |
| [storage.md](references/storage.md) | Model artifact handling, S3, EFS, FSx for Lustre, checkpoints, container image size |
| [observability.md](references/observability.md) | GPU metrics (Container Insights enhanced = MI-only; CloudWatch agent / DCGM exporter on EC2), Neuron metrics, CloudWatch, alerting |
| [security-and-compliance.md](references/security-and-compliance.md) | Task/execution-role trust, secrets, private subnets, ECR scanning, provenance, GuardDuty, compliance |
| [service-boundaries.md](references/service-boundaries.md) | Fargate-GPU exclusion evidence; when to use eks-genai / SageMaker / Bedrock / ecs-architect instead |
| [use-cases.md](references/use-cases.md) | Worked end-to-end scenarios (inference, distributed training, Neuron migration, GPU dev-sharing) with build paths |

## Sources

- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html) · [ECS task definitions for AWS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html) · [Use GPUs with ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html)
- [ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html) · [ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html) · [Automatically manage ECS capacity with cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html)
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/) · [Capacity Blocks for ML (EC2 User Guide)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-blocks.html) · [Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/)
- [Amazon ECS Best Practices Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html) · [Monitoring ECS Managed Instances (GPU / DCGM)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)
- [Distributed machine learning with Amazon ECS](https://aws.amazon.com/blogs/containers/distributed-machine-learning-with-amazon-ecs/) · [Using Amazon ECS with NVIDIA GPUs to accelerate drug discovery](https://aws.amazon.com/blogs/containers/using-amazon-ecs-with-nvidia-gpus-to-accelerate-drug-discovery/) · [Running GPU-based container applications with ECS Anywhere](https://aws.amazon.com/blogs/containers/running-gpu-based-container-applications-with-amazon-ecs-anywhere/)
