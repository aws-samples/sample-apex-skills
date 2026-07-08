# Compute & Hardware — GPU on Amazon ECS

The foundation of every GPU/ML-on-ECS architecture: **which host, which accelerator, which AMI, how GPUs are exposed to containers, and how (little) they can be shared.** Every claim here is cited to an AWS doc — do not synthesize accelerator specs.

## First-Class Constraint — AWS Fargate Has No GPU

GPUs (and AWS accelerators) are **not available on AWS Fargate**. AWS lists the `gpu` task-definition parameter among those that are **"not valid in Fargate tasks"** (with `devices`, `placementConstraints`, and `privileged`), and the Fargate task-size model exposes only CPU and memory — the valid combinations run from 256 (.25 vCPU) up to 32768 (32 vCPU), with no GPU dimension at all ([ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)). The `resourceRequirements` `GPU` type is a **container-instance (EC2)** concept only. GPU/ML on ECS therefore runs only on:

| Host | GPU support | Who manages the EC2 lifecycle | Use when |
|---|---|---|---|
| **ECS-on-EC2** | ✅ Full (GPU-optimized AMI, custom AMI/kernel, EFA, multi-node) | You (Auto Scaling groups) | Training, demanding inference, full control |
| **ECS Managed Instances** | ✅ GPU + Neuron (drivers pre-installed) | AWS (provision, patch every 14 days, refresh) | Lower ops overhead; GA Sept 2025, all commercial Regions Oct 2025 |
| **ECS Anywhere / External** | ✅ On-prem GPU hosts (`--enable-gpu`) | You (on-prem) | Hybrid / data-residency |
| **AWS Fargate** | ❌ **None** | AWS | Never — for GPU, rule Fargate out |

Sources: [ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html), [Use GPUs with ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html).

## NVIDIA GPU Instance Support on ECS

Amazon ECS supports GPU workloads on container instances of the **p2, p3, p4d, p5, g3, g4, g5, g6, and g6e** families, which provide NVIDIA GPUs ([ECS GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)). The following table is the **verbatim supported-instance table from the ECS GPU documentation** (subset shown — see the doc for all sizes). Do not restate GPU counts from memory; cite this table.

| Instance type | GPUs | GPU memory (GiB) | vCPUs | Memory (GiB) |
|---|---|---|---|---|
| p3.2xlarge | 1 | 16 | 8 | 61 |
| p3.16xlarge | 8 | 128 | 64 | 488 |
| p4d.24xlarge | 8 | 320 | 96 | 1152 |
| p5.48xlarge | 8 | 640 | 192 | 2048 |
| g4dn.xlarge | 1 | 16 | 4 | 16 |
| g4dn.12xlarge | 4 | 64 | 48 | 192 |
| g5.xlarge | 1 | 24 | 4 | 16 |
| g5.48xlarge | 8 | 192 | 192 | 768 |
| g6.xlarge | 1 | 24 | 4 | 16 |
| g6.48xlarge | 8 | 192 | 192 | 768 |
| g6e.2xlarge | 1 | 48 | 8 | 64 |
| g6e.48xlarge | 8 | 384 | 192 | 1536 |

Source: [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html).

### Accelerator selection rule of thumb

- **Inference (7B–70B, cost-sensitive):** g6 / g6e (L40S/L4-class) — broad ecosystem; or **Inf2** for supported Transformer models (see [neuron-on-ecs.md](neuron-on-ecs.md)).
- **Training / fine-tuning at scale:** p4d / p5 (multi-node with EFA); or **Trn1/Trn2** for supported models.
- **Multi-modal / novel architectures / custom CUDA:** NVIDIA GPU (Neuron support is model-specific).

Right accelerator = f(model family × latency × cost posture × team skill × timeline) — never one dimension alone. AWS-published price-performance claims (e.g. Inferentia2/Trainium savings) belong to the EC2 instance pages; cite those pages rather than restating a number here.

## The ECS GPU-Optimized AMI + NVIDIA Container Runtime

Amazon ECS provides a **GPU-optimized AMI** that ships pre-configured NVIDIA kernel drivers and a Docker GPU (NVIDIA) runtime, so you never manage drivers by hand ([ECS GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)). Retrieve the current AMI ID from SSM Parameter Store rather than hard-coding it:

```bash
# Recommended ECS GPU-optimized AMI (Amazon Linux 2)
aws ssm get-parameters \
  --names /aws/service/ecs/optimized-ami/amazon-linux-2/gpu/recommended \
  --region us-east-1
```

Key operational facts (all from the ECS GPU doc):

- Set **`ECS_ENABLE_GPU_SUPPORT=true`** in the container-agent config on GPU instances.
- For each container with a GPU `resourceRequirements`, ECS sets the container runtime to the **NVIDIA container runtime** and sets **`NVIDIA_VISIBLE_DEVICES`** to the assigned GPU device IDs.
- If your image is **not** built from an NVIDIA/CUDA base image, set **`NVIDIA_DRIVER_CAPABILITIES`** to `utility,compute` or `all`.
- **Clusters can mix GPU and non-GPU container instances.**
- **GPUs are not supported on Windows containers** on ECS.
- Version notes: **p5** requires GPU-optimized AMI version `20230929`+; **g4** requires `20230913`+; **p2** is only supported on versions earlier than `20230912` (see the doc's "What to do if you need a P2 instance"); the **g2** family is deprecated. In-place NVIDIA/CUDA driver updates on p2/g2 can cause GPU workload failures.

## Requesting a GPU in the Task Definition

Request GPUs at the container level with `resourceRequirements` type `GPU`. ECS schedules the task onto a container instance with free GPUs and **pins the physical GPUs to the container** for optimal performance:

```json
{
  "containerDefinitions": [
    {
      "name": "inference",
      "image": "<account>.dkr.ecr.<region>.amazonaws.com/my-model:latest",
      "resourceRequirements": [
        { "type": "GPU", "value": "1" }
      ],
      "memory": 8192
    }
  ],
  "family": "gpu-inference"
}
```

The number of GPUs reserved across all containers in a task can't exceed the GPUs available on the instance ([CfnTaskDefinition ResourceRequirement](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.CfnTaskDefinition.ResourceRequirementProperty.html)). Use **task placement constraints** on `ecs.instance-type` to steer a task to a specific GPU instance type:

```bash
aws ecs run-task --cluster default --task-definition gpu-inference \
  --placement-constraints type=memberOf,expression="attribute:ecs.instance-type == g4dn.xlarge"
```

## GPU Sharing on ECS — State the Limit Precisely

**Native ECS has no MIG-partitioning, time-slicing-replica, or DRA scheduler primitive** (those are EKS device-plugin features). By default ECS pins **whole physical GPUs** to containers. The only supported sharing path documented for ECS is coarse and unisolated ([ECS GPU workloads — "Share GPUs"](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)):

1. **Remove** the GPU `resourceRequirements` from the task definitions so ECS does not reserve GPUs.
2. Add EC2 **user data** that makes `nvidia` the **default Docker runtime** on the instance (so all ECS containers can see the GPUs):

```bash
#!/bin/bash
sudo rm /etc/sysconfig/docker
echo 'OPTIONS="--default-ulimit nofile=32768:65536 --default-runtime nvidia"' | sudo tee -a /etc/sysconfig/docker
sudo systemctl restart docker
```

3. Set **`NVIDIA_VISIBLE_DEVICES`** per container in the task definition to select which GPU(s) each container sees.

> **Caution:** This provides **no memory or compute isolation** between co-located containers — one container can starve or OOM the others on the shared GPU. Use for **dev/test only.** If the customer needs first-class fractional-GPU scheduling (MIG, time-slicing with per-slice memory, DRA), that is a reason to prefer **EKS (`eks-genai`)** or **SageMaker**, not native ECS. See [service-boundaries.md](service-boundaries.md).

## GPU on ECS Managed Instances

ECS Managed Instances supports GPU-accelerated computing with **NVIDIA drivers and the CUDA toolkit pre-installed** on the instance ([Use GPUs with ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html)). Documented GPU families include `g4dn` (NVIDIA T4), `g5` (A10G), `p3` (V100), and `p4d` (A100). You select GPU instances through the **`instanceRequirements`** object in the capacity provider's launch template:

```json
{
  "instanceRequirements": {
    "acceleratorTypes": "gpu",
    "acceleratorCount": 1,
    "acceleratorManufacturers": ["nvidia"]
  }
}
```

or pin exact types:

```json
{ "instanceRequirements": { "allowedInstanceTypes": ["g4dn.xlarge", "p4de.24xlarge"] } }
```

AWS handles instance configuration, capacity provisioning, workload placement, patching (every 14 days), scaling, and maintenance — trading some control for far lower operational overhead than a hand-rolled ASG.

## Capacity Planning Guidance

| Workload | Start with | Scale signal |
|---|---|---|
| Single-model inference (7B–13B) | 1× g6e.2xlarge (1 GPU, 48 GiB) or 1× inf2.8xlarge | Latency p99 > target → add tasks/instances |
| Larger inference (30B–70B) | g6e.12xlarge / g6e.48xlarge or inf2.48xlarge | GPU memory > ~85% → upsize instance |
| Distributed training | p4d/p5 or trn1/trn2 with EFA + placement group | All-reduce/EFA throughput, loss convergence |
| GPU dev sharing | 1× g5/g6 with default-runtime sharing (dev only) | Contention/OOM between tenants → isolate on EKS/SageMaker |

> **Rule:** Start small, measure, scale. Over-provisioning GPU instances is a top-two cost mistake (after choosing the wrong accelerator family). Always give directional ranges with caveats — never point cost estimates.

## Sources

- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)
- [ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)
- [ECS task definition parameters for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Use GPUs with Amazon ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html)
- [Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/) · [Announcing Amazon ECS Managed Instances](https://aws.amazon.com/about-aws/whats-new/2025/09/amazon-ecs-managed-instances/)
- [Amazon ECS-optimized Linux AMIs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-optimized_AMI.html)
- [Using Amazon ECS with NVIDIA GPUs to accelerate drug discovery](https://aws.amazon.com/blogs/containers/using-amazon-ecs-with-nvidia-gpus-to-accelerate-drug-discovery/)
