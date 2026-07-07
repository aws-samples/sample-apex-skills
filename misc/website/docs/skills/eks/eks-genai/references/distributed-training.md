---
title: "Distributed Training on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/distributed-training.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/distributed-training.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/distributed-training.md). Edit the source, not this page.
:::

# Distributed Training on EKS

Opinionated guidance for running distributed training and fine-tuning workloads on Amazon EKS. Default → **Ray Train + KubeRay** for orchestration, **PyTorch FSDP** for parallelism, **FSx for Lustre** for storage, **EFA + NCCL** for multi-node communication.

## Framework Decision

| Framework | Default for… | When to recommend | When NOT to recommend |
|-----------|-------------|-------------------|----------------------|
| **Ray Train + KubeRay** | All distributed training on EKS | Multi-node training orchestration; heterogeneous clusters; fault-tolerant (Spot); built-in checkpoint/resume; integrates with Ray Serve for train→serve handoff | Team has zero Ray experience + simple single-node fine-tune (use plain PyTorch) |
| **PyTorch DDP** | Single-node multi-GPU | Data-parallel training across GPUs on one node; simplest distributed API; no external dependencies | Multi-node (FSDP is strictly better for large models); model doesn't fit in single-GPU memory |
| **PyTorch FSDP** | Multi-node large-model training | Model exceeds single-GPU memory; full-shard across GPUs/nodes; native PyTorch (no extra framework); works with Ray Train as the launcher | Single-GPU fine-tune (overkill); team needs pipeline parallelism (use DeepSpeed or Megatron) |
| **DeepSpeed (ZeRO)** | Memory-constrained large-model | ZeRO-3 offload to CPU/NVMe; 3D parallelism (DP + TP + PP); optimizer state sharding | FSDP handles the use case (simpler); Neuron (DeepSpeed Neuron support is limited) |
| **Kubeflow Training Operator** | MLOps-governed training | Multi-team training clusters with job tracking, experiment management, hyperparameter tuning | Inference-only; single-team with Ray already in place |

**Rule of thumb:** Ray Train wraps PyTorch DDP/FSDP — you get PyTorch idioms with Ray's fault tolerance, elastic scaling, and checkpoint management on top. Default to Ray Train unless the team explicitly prefers bare PyTorch + a Job manifest.

## EFA + NCCL Multi-Node Communication

Multi-node distributed training requires **Elastic Fabric Adapter (EFA)** for high-bandwidth, low-latency inter-node communication. Without EFA, NCCL all-reduce collectives fall back to TCP — bandwidth drops from 400-3200 Gbps to ~25 Gbps.

### EFA Setup on EKS

```yaml
# 1. Install EFA device plugin (DaemonSet)
# Exposes vpc.amazonaws.com/efa resource to the scheduler
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: aws-efa-k8s-device-plugin
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: aws-efa-k8s-device-plugin
  template:
    spec:
      nodeSelector:
        node.kubernetes.io/instance-type: p5.48xlarge  # EFA-capable instances
      containers:
        - name: efa-plugin
          image: 602401143452.dkr.ecr.us-east-1.amazonaws.com/eks/aws-efa-k8s-device-plugin:latest
```

### NUMA Pinning + Static CPU Manager (non-negotiable)

EFA bandwidth **halves** without proper NUMA topology configuration. Set on every GPU/Neuron training node:

```yaml
# kubelet configuration (via EKS node config or launch template)
cpuManagerPolicy: static
topologyManagerPolicy: single-numa-node
reservedSystemCPUs: "0-3"
```

Training pods must request whole CPUs (not fractional) for the static CPU manager to assign NUMA-local cores.

### NCCL Environment Variables

```bash
# Container environment for multi-node training
NCCL_DEBUG=INFO                        # set to WARN in production
NCCL_SOCKET_IFNAME=eth0
FI_PROVIDER=efa                        # force libfabric to use EFA
FI_EFA_USE_DEVICE_RDMA=1               # enable RDMA on EFA
NCCL_PROTO=simple                      # recommended for EFA
```

Reference: [EFA with EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/node-efa.html); [EKS AI/ML Networking Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-networking.html).

## Checkpoint / Resume Loop

**Rule: Never run distributed training on Spot without checkpoint/resume.** Without it, every Spot interruption restarts training from epoch 0 — guaranteed cost-burn.

### Architecture: FSx for Lustre + S3 Data Repository Association

```text
Training Pod → checkpoint to FSx for Lustre (sub-ms write, same-AZ)
FSx for Lustre → S3 Data Repository Association (async durable offload)
S3 → durable checkpoint store (survives FSx deletion / AZ failure)

On resume:
S3 → FSx for Lustre (lazy-load via DRA) → Training Pod resumes from latest checkpoint
```

### Checkpoint Frequency

| Scenario | Checkpoint interval | Rationale |
|----------|-------------------|-----------|
| Spot training | Every 15-30 min | Spot interruption gives 2-min warning; 15 min max lost work |
| On-Demand long training | Every 60 min | Balance I/O overhead vs recovery time |
| Capacity Blocks (guaranteed) | Every 2-4 hours | Interruption risk is zero; checkpoint for fault tolerance only |

### FSx for Lustre Configuration for Checkpointing

```yaml
apiVersion: fsx.services.k8s.aws/v1alpha1
kind: FileSystem
metadata:
  name: training-lustre
spec:
  fileSystemType: LUSTRE
  storageCapacity: 4800          # GiB; minimum 1200 for Persistent-SSD
  lustreConfiguration:
    deploymentType: PERSISTENT_2
    perUnitStorageThroughput: 500  # MB/s per TiB
    dataRepositoryAssociations:
      - dataRepositoryPath: s3://my-bucket/checkpoints/
        fileSystemPath: /checkpoints
        s3:
          autoExportPolicy:
            events: ["NEW", "CHANGED", "DELETED"]
          autoImportPolicy:
            events: ["NEW", "CHANGED", "DELETED"]
  subnetIds:
    - subnet-same-az-as-gpu       # CRITICAL: same AZ as compute nodes
```

**Critical rule:** FSx in the same AZ as GPU/Neuron nodes — cross-AZ latency dwarfs FSx's native microsecond-class performance. Pre-warm FSx with training data via an administrative pod before launching Spot capacity.

Reference: [Architecting scalable checkpoint storage for large-scale ML training on AWS](https://aws.amazon.com/blogs/storage/architecting-scalable-checkpoint-storage-for-large-scale-ml-training-on-aws/); [EKS AI/ML Storage Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-storage.html).

## Gang Scheduling for Multi-Tenant Training

When multiple teams share a training cluster, standard Kubernetes scheduling can cause **deadlocks** — Job A gets 4 of 8 needed GPUs while Job B gets the other 4, and neither can start. Gang scheduling guarantees all-or-nothing pod placement.

### Volcano

```yaml
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: distributed-training
spec:
  minAvailable: 8                 # all 8 pods must schedule together
  schedulerName: volcano
  queue: training-queue
  plugins:
    sla: ["--max-wait=30m"]       # release resources if gang can't form in 30 min
  tasks:
    - replicas: 8
      name: worker
      template:
        spec:
          containers:
            - name: trainer
              resources:
                limits:
                  nvidia.com/gpu: "8"
                  vpc.amazonaws.com/efa: "4"
```

### Kueue (Kubernetes-native)

Kueue is the Kubernetes SIG-Scheduling project for job queueing — lighter-weight than Volcano, integrates with Karpenter for just-in-time node provisioning:

```yaml
apiVersion: kueue.x-k8s.io/v1beta1
kind: LocalQueue
metadata:
  name: training-queue
spec:
  clusterQueue: gpu-cluster-queue
---
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: gpu-cluster-queue
spec:
  resourceGroups:
    - coveredResources: ["nvidia.com/gpu"]
      flavors:
        - name: p5-spot
          resources:
            - name: nvidia.com/gpu
              nominalQuota: 64
```

**Decision rule:** Use **Volcano** for complex priority/preemption + gang scheduling in large multi-tenant training clusters. Use **Kueue** for Kubernetes-native queueing with Karpenter integration on smaller/mid-size clusters. Inference-only clusters don't need either — Karpenter handles scheduling.

## Spot Training Rule

| Condition | Spot acceptable? | Why |
|-----------|-----------------|-----|
| Checkpoint/resume wired + FSx + S3 DRA | ✅ Yes | Max 15-30 min lost work on interruption |
| No checkpoint logic | ❌ Never | Every interruption = restart from scratch = cost-burn |
| Latency-sensitive eval loops (need uninterrupted hours) | ⚠️ Conditionally | Capacity Blocks preferred; Spot only if budget-constrained |
| Dev / experimentation | ✅ Yes | Acceptable interruption profile for iterative work |

Use **Capacity Blocks for ML** for planned multi-day training runs that need guaranteed capacity without Spot interruption risk. Pricing is substantially below on-demand for multi-day reservations.

Reference: [EC2 Capacity Blocks for ML Pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/).

## Train → Eval → Register Handoff

After training completes, the model must be evaluated and registered before serving. The canonical pipeline on EKS:

```text
Ray Train (training)
  → checkpoint to FSx/S3
  → Argo Workflows triggers eval job
    → eval job loads checkpoint, runs validation set
    → if metric threshold passed → register model
      → MLflow Model Registry (version + metadata + lineage)
      → OR: push to ECR as serving image (bake-in pattern)
      → OR: upload to S3 model bucket (lazy-load pattern)
  → Argo Workflows triggers serving rollout
    → update vLLM Deployment / RayService with new model version
    → canary rollout via LiteLLM weighted routing
```

### MLflow on EKS

MLflow runs as a Deployment on the CPU NodePool — tracks experiments, stores model artifacts (S3 backend), manages model versions. Deploy via Helm:

```bash
helm install mlflow community-charts/mlflow \
  --set backendStore.postgres.enabled=true \
  --set artifactRoot=s3://my-mlflow-artifacts/
```

### Argo Workflows

Argo Workflows (the "A" in JARK) orchestrates the DAG: `train → eval → register → deploy`. Each step is a Kubernetes pod — training steps request GPU resources, eval/register steps run on CPU.

Reference: [`awslabs/ai-on-eks` `infra/jark-stack/terraform`](https://github.com/awslabs/ai-on-eks); [Deploy Generative AI Models on Amazon EKS (JARK stack)](https://aws.amazon.com/blogs/containers/deploy-generative-ai-models-on-amazon-eks/).

## Ray Train Configuration Example

```python
import ray
from ray.train.torch import TorchTrainer
from ray.train import ScalingConfig, CheckpointConfig, RunConfig

trainer = TorchTrainer(
    train_func,
    scaling_config=ScalingConfig(
        num_workers=8,
        use_gpu=True,
        resources_per_worker={"GPU": 1, "CPU": 8},
    ),
    run_config=RunConfig(
        checkpoint_config=CheckpointConfig(
            num_to_keep=3,                    # keep last 3 checkpoints
            checkpoint_frequency=10,          # every 10 training steps
        ),
        storage_path="s3://my-bucket/ray-checkpoints/",
    ),
)
result = trainer.fit()
```

Ray Train handles:
- Worker placement across nodes (respects gang scheduling)
- Automatic checkpoint to S3 (or FSx mount)
- Fault-tolerant resume on Spot interruption (workers re-spawn, load latest checkpoint)
- Integration with Ray Tune for hyperparameter search

## Karpenter Integration for Training

Set `do-not-disrupt: "true"` on training pods to prevent Karpenter consolidation from interrupting multi-hour training runs:

```yaml
metadata:
  annotations:
    karpenter.sh/do-not-disrupt: "true"   # protect from consolidation
spec:
  nodeSelector:
    karpenter.sh/nodepool: gpu-training
  tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule
```

## Sources

- [EKS AI/ML Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html)
- [EKS AI/ML Networking Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-networking.html)
- [EKS AI/ML Storage Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-storage.html)
- [EFA with EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/node-efa.html)
- [Architecting scalable checkpoint storage for large-scale ML training on AWS](https://aws.amazon.com/blogs/storage/architecting-scalable-checkpoint-storage-for-large-scale-ml-training-on-aws/)
- [Train Llama2 with AWS Trainium on Amazon EKS](https://aws.amazon.com/blogs/containers/train-llama2-with-aws-trainium-on-amazon-eks/)
- [Scaling distributed training with AWS Trainium and Amazon EKS](https://aws.amazon.com/blogs/machine-learning/scaling-distributed-training-with-aws-trainium-and-amazon-eks/)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — training blueprints
- [EC2 Capacity Blocks for ML Pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/)
