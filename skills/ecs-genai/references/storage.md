# Storage for GPU / ML Workloads on Amazon ECS

Where model weights, training data, and checkpoints live — and how to get them to GPU/Neuron tasks fast enough that expensive accelerators aren't idle waiting on I/O.

## Decision Table — Workload Pattern → Storage

| Workload pattern | Recommended storage | Why |
|---|---|---|
| **Inference weights (single task)** | S3 (pull at start) or bake into image (<5 GB) | Decoupled model/image release; lazy availability |
| **Inference weights shared across many tasks/nodes** | Amazon EFS (ReadWriteMany) | Concurrent read from multiple tasks; simple, elastic |
| **Distributed training data + checkpoints** | FSx for Lustre (same-AZ) + S3 DRA | Sub-ms latency, high aggregate throughput, durable offload |
| **Training checkpoints (durable)** | FSx for Lustre → S3 Data Repository Association | Fast local write; async durable copy to S3 |
| **Very large weights, I/O-bound cold start** | FSx for Lustre (pre-warmed) | Eliminates S3 cold-start when bandwidth-bound |

## Model Artifact Handling — Getting Weights to the Task

| Strategy | Model size | Cold-start | Coupling | Best for |
|---|---|---|---|---|
| **Bake into container image** | < ~5 GB | Zero (in layers) | Model release = image release | Small/classic models; air-gapped |
| **Pull from S3 at task start** | 5 GB – 200+ GB | Seconds–minutes | Decoupled | LLMs; frequent model updates |
| **Mount EFS** | Any (shared) | Low | Decoupled | Many tasks/nodes sharing the same weights |
| **Pre-cache on FSx for Lustre** | Any | Zero if pre-warmed | FSx lifecycle to manage | Training; very large weights where S3 is the bottleneck |

Rules:
- **Never pull weights from Hugging Face at every task start** — egress cost, rate limits, and cold-start. Stage in **S3** (or ECR for baked images) first.
- **Pre-compile Neuron models offline** and ship the compiled artifact via S3/image — never compile at task startup ([neuron-on-ecs.md](neuron-on-ecs.md)).
- **Access S3 via the task role** (least-privilege, per-bucket/prefix) — never static keys ([security-and-compliance.md](security-and-compliance.md)).

## Container Image Size — the Cold-Start Tax

CUDA / Deep Learning Container / Neuron images are large (often 5–15+ GB). **On the ECS-on-EC2 launch type the container image downloads completely before the container starts** — the same behavior as all non-1.4.0 Fargate platform versions ([ECS task definition differences for Fargate — SOCI lazy loading](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)). **SOCI lazy loading is Fargate-PV1.4-only, and Fargate has no GPU**, so SOCI is **unavailable on every host this skill covers** — do not plan around it for GPU/Neuron cold-start. Real EC2 mitigations: **pre-pull the image onto warm-pool instances**, **cache images on the instance NVMe**, **bake heavy layers into the AMI**, and keep images lean (multi-stage builds, drop build toolchains). Decouple weights from the image (pull from S3) so a model update doesn't force a full image re-pull.

## FSx for Lustre — Training I/O

For distributed training and checkpoint-heavy workloads, FSx for Lustre delivers high aggregate throughput and low latency, with an **S3 Data Repository Association (DRA)** for import (training data) and async export (checkpoints):

- **Same-AZ rule (critical):** deploy FSx in the **same Availability Zone** as the GPU/Neuron instances. Cross-AZ round-trip latency dwarfs FSx's native performance — a top silent-bad-architecture decision.
- **Pre-warm** FSx with training data (via an admin task) **before** launching Spot GPU capacity, so you don't burn expensive accelerator minutes waiting on data ingest.
- **Checkpoint flow:** training task writes to FSx → DRA async-exports to S3 → on interruption a replacement task lazy-loads the latest checkpoint from S3 into a fresh FSx volume. See [distributed-training.md](distributed-training.md).

## Amazon EFS — Shared Weights

Use EFS when multiple inference tasks (possibly across instances) must read the same weights concurrently (ReadWriteMany) and FSx's throughput/complexity isn't warranted. EFS is elastic (no sizing), mounts in each AZ, and is simple to attach as an ECS volume — moderate throughput, low-single-digit-ms latency. Good for 5–20 model variants shared across an inference fleet.

## Amazon S3 — the Backbone

S3 is the durable source of truth for weights, checkpoints, and the train→serve handoff artifact. Access via the **task role**; reach it privately from GPU instances in private subnets via an **S3 VPC endpoint** ([security-and-compliance.md](security-and-compliance.md)). Version models by key path (`s3://models/<name>/v3/`) to make promotion a task-definition update.

## Storage + Capacity Notes

- **FSx same-AZ:** pin the training ASG to the FSx AZ; accept reduced Spot diversity in exchange for correct latency.
- **EFS / S3:** regional/multi-AZ — no zone pinning needed for tasks.
- **Checkpoint safety:** ensure training tasks aren't scaled-in mid-write — schedule long runs on On-Demand/Capacity Blocks, or checkpoint frequently on Spot.

## Sources

- [Amazon FSx for Lustre](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html) · [FSx for Lustre and Amazon S3](https://docs.aws.amazon.com/fsx/latest/LustreGuide/fsx-data-repositories.html)
- [Amazon EFS volumes for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html)
- [Amazon ECS Best Practices Guide — task definitions (volumes, images)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)
- [Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html)
