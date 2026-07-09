# Distributed ML Training on Amazon ECS

Running multi-GPU and multi-node training / fine-tuning on ECS-on-EC2. ECS is a viable orchestrator for distributed ML — AWS documents an end-to-end pattern using **PyTorch + Ray Train** with distributed data parallel on ECS ([Distributed machine learning with Amazon ECS](https://aws.amazon.com/blogs/containers/distributed-machine-learning-with-amazon-ecs/)). Training runs on ECS-on-EC2 (or Managed Instances); **not Fargate** (no GPU/accelerator).

> **Managed Instances caveat for long training runs:** Managed Instances is convenient, but it **initiates security patching every ~14 days by replacing (drain-and-replace) the instance** ([capacity-and-scaling.md](capacity-and-scaling.md)). A multi-week pre-training/fine-tuning run **will be interrupted** by this cadence — so on MI you must have robust checkpoint/resume, schedule patching into a maintenance window, or prefer a **self-managed ASG / Capacity Block** for uninterrupted multi-week jobs.

## When ECS Fits Distributed Training — and When It Doesn't

- **ECS fits** when the team wants a simple control plane (no Kubernetes to operate), IAM-native auth, and transparent control-plane upgrades, and the job is **single-node multi-GPU** (all GPUs on one instance; PyTorch DDP/FSDP inside one task with `GPU: ALL`) or a moderate multi-node data-parallel run driven by Ray. AWS's reference shows distributed data parallel (DDP) with Ray Train on ECS.
- **Know the hard gap:** ECS has **no native multi-node distributed-training job primitive** — there is no equivalent to the Kubeflow `PyTorchJob`/`MPIJob`, the KubeRay operator, or `torchrun` auto peer-discovery across nodes. On ECS you wire rendezvous yourself (Ray head/worker tasks, or Cloud Map service discovery + `MASTER_ADDR`/`MASTER_PORT`), and you own job-level restart/checkpoint-resume on node failure. Multi-node scale beyond a Ray-managed run is where teams feel the absence most.
- **Prefer EKS (`eks-genai`)** for large or multi-tenant training platforms needing gang scheduling (Volcano/Kueue), KubeRay operators, distributed-job CRDs, and Karpenter-driven elastic GPU provisioning.
- **Prefer SageMaker** (training jobs / HyperPod) for fully-managed large-scale training where you don't want to own capacity or the training harness — including managed Spot with automatic checkpoint/resume.

## Parallelism Techniques (choose by model size)

Per the AWS ECS distributed-training reference:
- **Distributed Data Parallel (DDP)** — a full copy of the model on each GPU; data split across GPUs. Simplest; use when the model fits in a single GPU's memory.
- **Pipeline parallelism** — different model layers on different GPUs. For models too large for one GPU.
- **Tensor parallelism** — a single layer split across GPUs. For very large layers.

Frameworks run inside the container: **PyTorch (DDP/FSDP)**, **Ray Train** (wraps PyTorch with fault tolerance + orchestration), DeepSpeed, or Megatron. For Neuron training, use `neuronx-distributed` on Trn1/Trn2 ([neuron-on-ecs.md](neuron-on-ecs.md)).

## Multi-Node Networking — EFA + Placement Groups

Multi-node training is bottlenecked by inter-node collective communication (NCCL all-reduce). Without a high-bandwidth fabric, throughput collapses to standard TCP.

- **Elastic Fabric Adapter (EFA):** attach EFA interfaces to the GPU instances (p4d/p5/trn) for low-latency, high-throughput RDMA. EFA is optimized for **NCCL** on AWS ([EFA for ML](https://aws.amazon.com/hpc/efa/)). The container image must include NCCL + the EFA/libfabric stack (use AWS Deep Learning Containers or build with `aws-ofi-nccl`).
- **Cluster placement group:** launch the training ASG's instances into a **cluster placement group** so they are physically close for lowest latency ([Get started with EFA and NCCL for ML on EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-start-nccl.html)).
- **Capacity Blocks for ML** colocate reserved P/Trn instances in EC2 UltraClusters with EFA already — the simplest way to get a well-connected multi-node training cluster ([capacity-and-scaling.md](capacity-and-scaling.md)).

Typical NCCL/EFA container environment:

```bash
FI_PROVIDER=efa
FI_EFA_USE_DEVICE_RDMA=1
NCCL_DEBUG=WARN
```

(Don't set `NCCL_PROTO=simple` — it's a legacy workaround that disables faster NCCL protocols and is not needed on recent `aws-ofi-nccl`; leave NCCL to auto-select.)

**Exposing EFA to the container — the mechanism (get this right):** EFA attaches to the **instance at launch** via the launch template (an EFA-enabled ENI plus the EFA/libfabric driver baked into the AMI). To let the container use it you must **map the EFA device into the container with `linuxParameters.devices`** — `hostPath` (and, if set, `containerPath`) `/dev/infiniband/uverbs0`, with `permissions` `READ | WRITE | MKNOD` (multi-EFA instances such as p4d expose `uverbs0..uverbs3`). This is the documented device-mapping mechanism ([EFA on AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/efa.html)); also set the `memlock` ulimit to unlimited, and place all instances in the **same cluster placement group and AZ** (EFA OS-bypass traffic is limited to one AZ). Important: an `awsvpc` task ENI is a **plain interface ENI — it is never the EFA device**, so choosing `awsvpc` networking does not by itself grant EFA access; the `devices` mapping is what does (host networking is the other documented option). Because a heterogeneous GPU ASG breaks managed scaling ([capacity-and-scaling.md](capacity-and-scaling.md)), a multi-node training job uses **one homogeneous ASG of one GPU type** sized to the job.

## Orchestrating the Job on ECS

Two common patterns:

1. **Ray on ECS** — run a Ray head task + Ray worker tasks (each a GPU task) as ECS services/tasks; Ray Train handles worker placement, checkpointing, and fault-tolerant resume. This is the AWS-documented ECS distributed-training approach.
2. **Rank-addressed tasks** — launch N training tasks (one per node) with a shared rendezvous (torchrun/`c10d` or an MPI launcher); each task pins its GPUs via `resourceRequirements`. Use a placement constraint to spread one task per instance.

Keep the **whole job on one homogeneous GPU ASG** and size the ASG to the node count; ECS cluster auto scaling reacts with latency, so pre-provision (or use Capacity Blocks) for large runs rather than relying on reactive scale-out.

## Checkpoint / Resume — Mandatory for Spot

**Never run distributed training on Spot without checkpoint/resume.** Every interruption otherwise restarts from epoch 0 — a guaranteed cost-burn.

```text
Training task → checkpoint to FSx for Lustre (fast, same-AZ)  ── or ──  directly to S3
FSx for Lustre → S3 Data Repository Association (async durable offload)
On interruption → replacement task launches → loads latest checkpoint from S3/FSx → resumes
```

- Checkpoint every **15–30 min** on Spot (Spot gives a 2-minute warning; managed instance draining helps drain gracefully).
- Keep checkpoint storage **same-AZ** as the GPU instances — cross-AZ latency dwarfs FSx's native performance ([storage.md](storage.md)).
- Set the training tasks to **not be disrupted** by scale-in during an active run (schedule on On-Demand/Capacity Blocks, or isolate Spot to interruption-tolerant phases).

## Train → Register → Serve Handoff

The trained artifact (e.g. SafeTensors weights) is written to **S3**; the inference service reads from the same S3 path ([inference-serving.md](inference-serving.md), [storage.md](storage.md)). Version with an S3 key path (`s3://models/llama-7b-ft/v3/`); promote by updating the inference task definition to the new version and forcing a rolling service deployment. For richer pipelines, orchestrate `data-prep → train → eval → register → deploy` with Step Functions or an external workflow engine (Argo/Airflow) — ECS itself has no built-in ML-pipeline DAG.

## Sources

- [Distributed machine learning with Amazon ECS](https://aws.amazon.com/blogs/containers/distributed-machine-learning-with-amazon-ecs/)
- [Elastic Fabric Adapter (EFA) for ML](https://aws.amazon.com/hpc/efa/) · [Get started with EFA and NCCL for ML workloads on Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-start-nccl.html) · [EFA device mapping into containers (AWS Batch)](https://docs.aws.amazon.com/batch/latest/userguide/efa.html)
- [EC2 Capacity Blocks for ML](https://aws.amazon.com/ec2/capacityblocks/)
- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html) · [ECS task definitions for AWS Neuron ML workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-inference.html)
- [Amazon FSx for Lustre](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html)
