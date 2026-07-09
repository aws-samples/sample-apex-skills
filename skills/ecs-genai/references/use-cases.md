# Worked Use Cases — GPU / ML on Amazon ECS

Four condensed scenarios. Each gives: customer profile, the ECS-specific decisions, and a build path. All keep the first-class constraint in view — **GPU is never on Fargate**.

---

## Use Case 1 — Single-Model LLM Inference on ECS-on-EC2

**Profile:** Team already runs services on ECS (non-AI). Wants to self-host an open Transformer LLM (Llama/Mistral/Qwen) for a product feature. Balanced cost, no strong hardware preference, no Kubernetes appetite.

**ECS-specific decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| D1 Host | ECS-on-EC2 (or Managed Instances) | Fargate has no GPU |
| D2 Accelerator | g6e (NVIDIA L40S) for 7B–13B; evaluate Inf2 as phase-2 cost play | Broad ecosystem first; Neuron savings later |
| D3 Capacity | One homogeneous g6e capacity-provider ASG + service capacity-provider strategy | Mixed-GPU ASGs are allowed but managed scaling protects on the smallest type — keep one type per ASG ([capacity-and-scaling.md](capacity-and-scaling.md)) |
| D4 Shape | Single GPU task behind an ALB; Service Auto Scaling on requests/latency; raise ALB idle timeout for token streaming | Standard inference service ([inference-serving.md](inference-serving.md)) |
| Storage | Weights in S3, pulled at task start | Decoupled model/image release; on EC2 the image downloads fully first (no SOCI) ([storage.md](storage.md)) |
| Observability | **On g6e MI:** agentless DCGM via Container Insights **enhanced**. **On g6e ECS-on-EC2:** CloudWatch agent (`nvidia_smi`) or DCGM exporter — the agentless MI metrics don't exist there. Plus serving-engine latency metric | Pick the path by launch model ([observability.md](observability.md)) |
| Security | Task role → S3 (prefix-scoped); private subnet + S3/ECR VPC endpoints; ECR scanning | Baseline ([security-and-compliance.md](security-and-compliance.md)) |

**Build path:** stand up the g6e capacity provider + service; validate the model + a generous health-check grace period; wire enhanced Container Insights + latency-based Service Auto Scaling; harden (task role, secrets, private subnets, image scanning); then run a g6e-vs-inf2 cost comparison and migrate to Neuron if the savings justify the compilation ramp.

**Route out if:** the team wants scale-to-zero or **scheduler-driven** fractional-GPU multi-model packing (MIG/time-slicing/DRA) → `eks-genai`; or a fully-managed endpoint → SageMaker. (Hardware-fractional L4 via G6f/Gr6f on Managed Instances stays on ECS — see [compute-hardware.md](compute-hardware.md).)

---

## Use Case 2 — Distributed Multi-Node Training on ECS

**Profile:** Team fine-tuning / pre-training a 7B–70B Transformer across multiple GPU nodes. Cost-conscious. PyTorch + Ray. No Kubernetes platform team.

**ECS-specific decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| D1 Host | ECS-on-EC2 | Custom AMI/kernel + EFA control; not Fargate |
| D2 Accelerator | p4d/p5 (GPU) or trn1/trn2 (Neuron) | Model-family + cost dependent |
| D3 Capacity | One homogeneous ASG of the chosen type in a **cluster placement group**; **Capacity Blocks for ML** for guaranteed multi-day capacity | UltraCluster + EFA; capacity assurance ([capacity-and-scaling.md](capacity-and-scaling.md)) |
| D4 Shape | Ray head + worker tasks (DDP/FSDP); EFA + NCCL in the image | AWS-documented ECS distributed-training pattern |
| Storage | FSx for Lustre same-AZ + S3 DRA for checkpoints | Fast I/O; durable offload ([distributed-training.md](distributed-training.md)) |

**Build path:** reserve capacity (Capacity Blocks) into a placement-group ASG; validate single-node training + Neuron compilation (if Trn); wire checkpoint→FSx→S3 every 15–30 min; scale to multi-node and confirm EFA/NCCL throughput; run with Spot only on interruption-tolerant phases with checkpoint/resume.

**Route out if:** the team needs gang scheduling / a multi-tenant training platform → `eks-genai`; or fully-managed large-scale training → SageMaker HyperPod.

---

## Use Case 3 — Cost-Optimized Inference via Neuron Migration on ECS

**Profile:** Production inference on ECS using g5/g6 GPUs, steady high-volume traffic, cost-first. Models are Transformer-family. Considering Inf2.

**ECS-specific decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| D2 Accelerator | Add Inf2 alongside existing GPU | Cost-optimized for supported models |
| D3 Capacity | New Inf2 capacity provider/ASG beside the GPU one; blend via capacity-provider strategy during canary | Separate homogeneous ASGs; shift weight gradually |
| Neuron | Managed device allocation (`NeuronDevice: ALL`) on Managed Instances, or manual `linuxParameters.devices` on EC2 | ([neuron-on-ecs.md](neuron-on-ecs.md)) |
| Compilation | Pre-compile offline, ship artifact via S3 | Never compile at task start |

**Build path:** verify the model architecture is Neuron-supported; compile offline (budget 1–2 weeks for the first model); deploy an Inf2 service; run an eval suite comparing GPU vs Neuron output quality; canary traffic 5%→100% by shifting the capacity-provider-strategy weights; decommission the GPU pool; document the compilation pipeline for future model versions.

**Risk callouts:** compilation ramp adds lead time to each new model version; not all HF models are Neuron-supported; validate output parity before shifting production traffic.

---

## Use Case 4 — Shared GPU Dev Cluster on ECS

**Profile:** A data-science team wants several people to share a couple of GPU instances for experimentation. Cost-sensitive; isolation not critical.

**ECS-specific decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| D1 Host | ECS-on-EC2, g5/g6 | Not Fargate |
| Sharing | Remove GPU `resourceRequirements`; set `nvidia` as default Docker runtime via user data; set `NVIDIA_VISIBLE_DEVICES` per container | The only ECS GPU-sharing path ([compute-hardware.md](compute-hardware.md)) |
| Guardrail | **Dev/test only — no memory/compute isolation** | One container can starve/OOM others |

**Build path:** launch a small g5/g6 ASG with the default-runtime user data; publish task-definition templates with `NVIDIA_VISIBLE_DEVICES` set; document the no-isolation caveat.

**Route out if:** the team needs **dynamic multi-model GPU packing** — a MIG / time-slicing / DRA *scheduler* — → `eks-genai`; or managed notebooks/experiments → SageMaker Studio. (But note: **hardware-fractional L4 instances (G6f/Gr6f)** are supported on ECS **Managed Instances** for small/cost-sensitive inference — the slice is the instance shape, no scheduler needed; see [compute-hardware.md](compute-hardware.md). Route to EKS only when the requirement is a *scheduler-driven* fractional-GPU platform.)

---

## Pattern Summary

| Scenario | Primary lever | Key ECS-specific gotcha |
|---|---|---|
| Single-model inference | Right-size GPU family; enhanced Container Insights | Health-check grace period for model warmup |
| Distributed training | Capacity Blocks + EFA + placement group | One homogeneous ASG; checkpoint or lose Spot progress |
| Neuron migration | Neuron over GPU for supported models | Pre-compile offline; verify model support + output parity |
| Shared GPU dev | GPU sharing via default runtime | No isolation — dev/test only |

## Sources

- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html) · [ECS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html)
- [Distributed machine learning with Amazon ECS](https://aws.amazon.com/blogs/containers/distributed-machine-learning-with-amazon-ecs/)
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/)
- [Amazon ECS capacity providers for EC2 workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html)
- [Monitoring Amazon ECS Managed Instances (GPU / DCGM)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/monitoring-managed-instances.html)
