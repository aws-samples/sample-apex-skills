# AWS Neuron (Inferentia / Trainium) on Amazon ECS

Running AWS purpose-built ML accelerators — **AWS Inferentia (Inf1, Inf2)** and **AWS Trainium (Trn1, Trn2)** — as ECS workloads. Neuron is the cost-optimized alternative to NVIDIA GPU for **supported Transformer-family models**, at the cost of an ahead-of-time compilation step. Like GPU, **Neuron is not available on Fargate** — it runs on ECS-on-EC2 and, for **Inf2 and Trn1 only**, ECS Managed Instances; **Trn2 and Inf1 are EC2-launch-type only** (see the doc-conflict caveats below).

## Supported Instances & What Each Is For

Per [ECS task definitions for AWS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html) and the [ECS Managed Instances instance types](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-instance-types.html) supported list (both verified 2026-07-10):

| Family | Chip | Role | ECS support |
|---|---|---|---|
| **Trn1** | AWS Trainium | High-performance, low-cost **training** (also large-model inference) | EC2 launch type + Managed Instances |
| **Trn2** | AWS Trainium2 | Highest-performance Trainium **training** | **EC2 launch type only** (not on the MI supported list — see caveat) |
| **Inf2** | AWS Inferentia2 | High-performance, low-cost **inference** | EC2 launch type + Managed Instances |
| **Inf1** | AWS Inferentia | Inference (first-gen) | **EC2 launch type only** |

> **Known AWS doc conflicts (state these when advising, don't paper over them):**
> - **Trn2 on Managed Instances:** [ecs-inference.html](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html) describes Trn2 selection on MI (e.g. `acceleratorNames: trainium2`), but the [MI supported-types list](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-instance-types.html) ends its accelerated list at Trn1 and the ECS API reference's [`InstanceRequirementsRequest.acceleratorNames`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_InstanceRequirementsRequest.html) valid values include **no** `trainium`/`trainium2`/`inferentia2` values — as of 2026-07-10, Trn2 is **not** documented as supported on MI. **Verify against the live pages before advising Trn2 on MI**; scope Trn2 to the EC2 launch type (self-managed ASG) until the docs agree.
> - **Inf1:** the same page pair disagrees the other way — ecs-inference.html says Inf1 is **EC2 launch type only**, while the MI supported-types list includes Inf1. Treat Inf1 as EC2-launch-type only (the explicit Neuron-page scoping note wins for device allocation), and flag the conflict.

Verbatim device mapping from the ECS Neuron doc (subset — chips per instance, used for manual device specification; table re-verified against the live doc **2026-07-10** — the Inf/Trn family list moves fast, re-check before quoting):

| Instance | vCPUs | RAM (GiB) | Neuron chips | Device paths |
|---|---|---|---|---|
| trn1.2xlarge | 8 | 32 | 1 | /dev/neuron0 |
| trn1.32xlarge | 128 | 512 | 16 | /dev/neuron0 … /dev/neuron15 |
| trn2.48xlarge | 192 | 2048 | 16 | /dev/neuron0 … /dev/neuron15 |
| inf1.xlarge | 4 | 8 | 1 | /dev/neuron0 |
| inf1.24xlarge | 96 | 192 | 16 | /dev/neuron0 … /dev/neuron15 |
| inf2.xlarge | 4 | 16 | 1 | /dev/neuron0 |
| inf2.24xlarge | 96 | 384 | 6 | /dev/neuron0 … /dev/neuron5 |
| inf2.48xlarge | 192 | 768 | 12 | /dev/neuron0 … /dev/neuron11 |

Depending on the launch type, clusters can mix Trn1, Trn2, Inf1, Inf2, and other instances (subject to the per-type-ASG capacity rule in [capacity-and-scaling.md](capacity-and-scaling.md) and the launch-model scoping above). The workload must be a **Linux** container using a framework with Neuron support (PyTorch, TensorFlow) via the **AWS Neuron SDK** (compiler + runtime + profiling tools). Non-Neuron frameworks won't get accelerated performance on these instances.

## The ECS Neuron-Optimized AMI

ECS provides a **Neuron-optimized Amazon Linux 2023 AMI** with the AWS Neuron drivers and Docker runtime pre-installed — recommended for launching Trn1, Inf1, and Inf2 instances ([ECS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html)):

```bash
aws ssm get-parameters \
  --names /aws/service/ecs/optimized-ami/amazon-linux-2023/neuron/recommended
```

> **CDK caveat (AL2 vs AL2023 mismatch):** `EcsOptimizedImage.amazonLinux2(AmiHardwareType.NEURON)` returns the **Amazon Linux 2 (Neuron)** AMI — *not* the AL2023 Neuron AMI recommended above ([CDK aws-ecs — Amazon Linux 2 (Neuron) Instances](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs-readme.html)). To launch the **AL2023** Neuron AMI in CDK, don't rely on `amazonLinux2(...NEURON)`; use the **SSM parameter above directly** (e.g. `MachineImage.fromSsmParameter(...)`) so the launch template actually gets AL2023.

## Two Ways to Give a Container Neuron Devices

ECS supports **two approaches** for Neuron device access — use one consistently to avoid conflicts:

### 1. Managed Neuron device allocation (Managed Instances only)

Use `resourceRequirements` type **`NeuronDevice`** with value `ALL`. ECS discovers Neuron devices on the instance, assigns them, and gives the container access to **all** Neuron devices — so **only one Neuron task runs per instance** (exclusive access).

```json
{
  "containerDefinitions": [
    {
      "name": "neuron-inference",
      "image": "<account>.dkr.ecr.<region>.amazonaws.com/vllm-neuron:latest",
      "resourceRequirements": [
        { "type": "NeuronDevice", "value": "ALL" }
      ]
    }
  ]
}
```

Constraints: at most one container definition may specify `NeuronDevice`; you can't combine `NeuronDevice` `resourceRequirements` with `linuxParameters.devices` for Neuron in the same task definition. After launch, verify via `DescribeTasks` (`neuronDeviceIds` per container) or `DescribeContainerInstances` (`NEURON_DEVICES` in registered/remaining resources). Select Neuron instances in the Managed Instances launch template with `instanceRequirements` — use `acceleratorManufacturers` plus `allowedInstanceTypes`:

```json
{
  "instanceRequirements": {
    "vCpuCount": { "min": 4 },
    "memoryMiB": { "min": 16384 },
    "acceleratorManufacturers": ["amazon-web-services"],
    "allowedInstanceTypes": ["inf2.*", "trn1.*"]
  }
}
```

`vCpuCount` and `memoryMiB` are **required** fields of `instanceRequirements` (`Required: Yes` in the API reference — a request without them fails validation; AWS's own ecs-inference.html example omits them). Size the min values to your smallest acceptable instance. ([`InstanceRequirementsRequest`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_InstanceRequirementsRequest.html), verified 2026-07-10)

> **API caveat:** [ecs-inference.html](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html) suggests `acceleratorNames` values `inferentia2`/`trainium`/`trainium2`, but the ECS API reference's [`InstanceRequirementsRequest.acceleratorNames`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_InstanceRequirementsRequest.html) valid-values enum (`a100 | inferentia | k520 | k80 | m60 | radeon-pro-v520 | t4 | vu9p | v100 | a10g | h100 | t4g`, verified 2026-07-10) contains **none of those values** — only first-gen `inferentia`. Don't rely on Neuron `acceleratorNames`; select via `acceleratorManufacturers: ["amazon-web-services"]` and `allowedInstanceTypes`, and scope to Inf2/Trn1 per the MI supported list.

### 2. Manual Neuron device specification (EC2 launch type + Managed Instances)

Explicitly map device paths with `linuxParameters.devices`. **Only one inference/training task can run per Trainium/Inferentia chip**; you can run as many tasks as there are chips by assigning different devices to each. The **task definition must be specific to a single instance type** (device paths differ per instance — see the table above). Use task placement constraints on `ecs.instance-type` to land the task on the right family.

```json
{
  "containerDefinitions": [
    {
      "name": "neuron-inference",
      "image": "…/vllm-neuron:latest",
      "linuxParameters": {
        "devices": [
          { "hostPath": "/dev/neuron0", "containerPath": "/dev/neuron0", "permissions": ["read","write"] }
        ]
      }
    }
  ]
}
```

## Compilation — The Ramp Cost

Neuron requires **ahead-of-time compilation** of the model (via `torch-neuronx` / `neuronx-distributed-inference` for Inf2/Trn; `torch-neuron` for Inf1). This is the primary adoption friction vs NVIDIA GPU:

- Budget **1–2 weeks** for the first model (SDK learning, graph-break debugging, tensor/pipeline-parallel tuning). Subsequent versions are much faster (reuse compilation cache).
- **Pre-compile offline** in CI and ship the compiled artifact via S3 or bake it into the container image. **Never compile at task startup** in production — it puts a multi-minute step on the critical path.
- **Verify the specific model architecture is Neuron-supported before committing budget** — not all Hugging Face models have Neuron support; verify against the [AWS Neuron](https://aws.amazon.com/ai/machine-learning/neuron/) supported-models list, and run an eval suite comparing GPU vs Neuron output quality before shifting production traffic.

## When Neuron Wins (and When It Doesn't)

- **Recommend Neuron when:** the model is Transformer-family (Llama, Mistral, Qwen, etc.), framework is PyTorch/TensorFlow with Neuron support, the workload is steady-state production (inference on Inf2) or cost-sensitive training (Trn1/Trn2), and the team can absorb the compilation ramp.
- **Stay on NVIDIA GPU when:** fastest time-to-first-success matters, there are CUDA-only dependencies, the architecture is novel/non-Transformer or multi-modal, or Neuron support for the model is unverified.

AWS-published price-performance claims for Inferentia2/Trainium live on the EC2 instance-type pages — cite those pages rather than restating a percentage here. Give directional ranges with caveats.

## Sources

- [Amazon ECS task definitions for AWS Neuron machine learning workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html)
- [Example Neuron task definitions for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference-task-def.html)
- [AWS Neuron](https://aws.amazon.com/ai/machine-learning/neuron/) · [AWS Inferentia](https://aws.amazon.com/ai/machine-learning/inferentia/) · [AWS Trainium](https://aws.amazon.com/ai/machine-learning/trainium/)
- [Amazon ECS task definitions for AWS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html) — the authoritative source for the managed `NeuronDevice` allocation path and `instanceRequirements` Neuron selection (the NVIDIA-only [managed-instances-gpu.html](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html) does *not* cover Neuron device allocation)
- [aws-cdk-lib.aws_ecs — Amazon Linux 2 (Neuron) Instances](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs-readme.html)
