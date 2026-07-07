---
title: "Storage for GenAI on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/storage.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/storage.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/storage.md). Edit the source, not this page.
:::

# Storage for GenAI on EKS

The storage layer is where training jobs stall and inference cold-starts hide. Pick wrong and you burn GPU-hours waiting on I/O; pick right and storage becomes invisible. This reference covers the four storage surfaces — FSx for Lustre, Mountpoint for S3 CSI, Amazon EFS, and Amazon S3 Vectors — with the decision rules that map workload pattern → storage choice.

## Decision Table — Workload Pattern → Storage

| Workload pattern | Recommended storage | Why |
|---|---|---|
| **Distributed training (multi-GPU/Neuron, multi-node)** | FSx for Lustre — Persistent SSD | Sub-ms latency, hundreds GB/s aggregate throughput, EFA-connected, full POSIX, S3 DRA for data ingest |
| **Training checkpoints** | FSx for Lustre → S3 Data Repository Association | Fast local checkpoint write; async durable offload to S3 |
| **Short-lived / ephemeral training runs** | FSx for Lustre — Scratch SSD | Cheaper than Persistent; auto-deleted when the filesystem is torn down |
| **Single-GPU/Neuron inference (large weights)** | Mountpoint for S3 CSI | Per-pod isolation, lazy-load weights on demand, local cache per pod |
| **Multi-model serving (shared weights, ReadWriteMany)** | Amazon EFS | Concurrent read from multiple pods/nodes; simpler than FSx for moderate throughput |
| **Multi-GPU inference cluster (I/O-bound weight loading)** | FSx for Lustre — Persistent SSD | When I/O is the bottleneck and EFS throughput is insufficient |
| **RAG vector storage (cost-efficient)** | Amazon S3 Vectors | Up to ~90% cost reduction vs traditional vector databases; serverless, no cluster to manage |

Source: [EKS AI/ML Storage Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-storage.html).

## FSx for Lustre

### When to Use

Any workload that demands **high aggregate throughput + low latency + POSIX semantics** — distributed training is the canonical case. FSx for Lustre delivers hundreds of GB/s read throughput with sub-millisecond access latency, connected via EFA for the fastest path between compute and storage.

### Persistent vs Scratch

| Variant | Lifecycle | Cost | Use when… |
|---------|-----------|------|-----------|
| **Persistent SSD** | Survives filesystem delete; data persists | Higher | Multi-day training, shared datasets across jobs, checkpoint store |
| **Scratch SSD** | Ephemeral — deleted with filesystem | Lower (AWS's most cost-effective Lustre option; exact delta varies by Persistent throughput tier — check the [FSx for Lustre pricing page](https://aws.amazon.com/fsx/lustre/pricing/)) | Single training run, throwaway experimentation, benchmarking |

### S3 Data Repository Association (DRA)

FSx for Lustre links bidirectionally to an S3 bucket:

- **Import:** Training data staged in S3 is lazily loaded into FSx on first access — or bulk-imported via `hsm_restore`.
- **Export:** Checkpoints written to FSx are asynchronously exported to S3 for durability (fire-and-forget from the training script's perspective).
- **Checkpoint pattern:** Training script writes checkpoint to `/fsx/checkpoints/step-N/`; DRA exports to `s3://bucket/checkpoints/step-N/` in the background. On Spot interruption, recovery reads the latest S3 checkpoint into a fresh FSx volume.

### EFA Connectivity

For p5/trn1/trn2 training nodes, FSx for Lustre can be accessed over **EFA** (Elastic Fabric Adapter) for the lowest latency path. Ensure:

- FSx filesystem and GPU/Neuron nodes are in the **same VPC subnet** and **same Availability Zone**.
- Security groups allow Lustre client traffic (TCP 988, 1018-1023).

### The Same-AZ Rule (Critical)

> **Deploy FSx in the same AZ as the GPU/Neuron nodes.** Cross-AZ adds 1-2 ms round-trip latency that dwarfs FSx's native microsecond-class performance. This is one of the top-3 silently-bad architecture decisions for ML on EKS.

Karpenter `topology.kubernetes.io/zone` constraint + FSx `subnetId` must align. If using Spot, anchor the NodePool to a single AZ (the one with FSx) and accept reduced Spot diversity — the latency penalty of cross-AZ FSx is worse than slightly reduced Spot pool.

### Pre-Warming Before Spot

**Pre-warm FSx with training data before launching Spot GPU/Neuron nodes.** Spot capacity is bursty and expensive per-second; burning Spot allocation on data download wastes money.

Pattern:
1. Deploy an administrative CPU pod with the Lustre client mounted.
2. Run bulk `hsm_restore` or `lfs hsm_restore` to pull training data from S3 into FSx.
3. Once data is resident, launch the Karpenter-managed Spot GPU/Neuron NodePool.
4. Training pods mount the pre-warmed FSx — zero download wait.

```yaml
# PersistentVolumeClaim for FSx for Lustre (static provisioning)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: fsx-training-data
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  resources:
    requests:
      storage: 1200Gi
  volumeName: fsx-pv
```

## Mountpoint for Amazon S3 CSI Driver

### When to Use

**Inference workloads** loading model weights from S3 — the default for single-model serving (7B–70B+). The workshop validates this as the canonical inference storage path: EKS managed add-on, CSI driver `s3.csi.aws.com`, `ReadOnlyMany` PV/PVC serving weights from an S3 bucket.

### How It Works

- Each pod gets an **isolated mount** of an S3 bucket (or prefix) as a read-only POSIX-like filesystem.
- Weights are **lazily loaded on first read** — the pod starts immediately; bytes stream from S3 as the model framework (`torch.load`, vLLM weight loader) reads them.
- A **per-pod local cache** (configurable, typically 5–10 GB on NVMe instance storage) accelerates repeated reads — second pod startup on the same node is near-instant.
- Auth via **EKS Pod Identity** or IRSA — each pod assumes a role scoped to its bucket/prefix.

### Key Properties

| Property | Value |
|----------|-------|
| CSI driver name | `s3.csi.aws.com` |
| Access mode | `ReadOnlyMany` (production) — `ReadWriteMany` not supported for model serving |
| Cache | Per-pod; backed by node local storage |
| Auth | EKS Pod Identity / IRSA (IAM role per ServiceAccount) |
| Install | EKS managed add-on (console / `eksctl` / Terraform) |

### Example PV/PVC

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: model-weights-pv
spec:
  capacity:
    storage: 100Gi          # informational — S3 is effectively unlimited
  accessModes:
    - ReadOnlyMany
  csi:
    driver: s3.csi.aws.com
    volumeHandle: s3-model-weights
    volumeAttributes:
      bucketName: my-model-weights-bucket
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: model-weights-pvc
spec:
  accessModes:
    - ReadOnlyMany
  storageClassName: ""
  resources:
    requests:
      storage: 100Gi
  volumeName: model-weights-pv
```

### When NOT to Use

- **Distributed training** needing high write throughput → FSx for Lustre.
- **Checkpoint writes** → FSx for Lustre + S3 DRA (Mountpoint is read-optimized).
- **Sub-millisecond random access** (e.g., embedding lookup during training) → FSx for Lustre or EFS.

## Amazon EFS

### When to Use

**Multi-model serving** where the same model weights must be concurrently readable by pods on **multiple nodes** (ReadWriteMany) and FSx's complexity/cost isn't justified. EFS is simpler to provision and manage — no filesystem sizing, automatic scaling.

### Trade-offs vs FSx and Mountpoint S3

| Dimension | EFS | FSx for Lustre | Mountpoint S3 CSI |
|-----------|-----|----------------|-------------------|
| Access mode | ReadWriteMany | ReadWriteMany | ReadOnlyMany |
| Throughput | Moderate (GiB/s class with Elastic throughput) | Hundreds GB/s | S3 bandwidth (5-10 Gbps per pod typical) |
| Latency | Low-single-digit ms | Sub-ms | Depends on object size + S3 region |
| Cost model | Per-GB-month + throughput | Per-GB-month (provisioned) | S3 request + storage pricing |
| Best for | Shared weights across many pods | Training I/O, checkpoint, massive throughput | Per-pod isolated inference weight loading |

### Pattern

Use EFS when you have 5–20 model variants (each 5–30 GB) served by different pods on different nodes, all reading from a shared `/models/` mount:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-models-efs
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: efs-sc
  resources:
    requests:
      storage: 500Gi
```

## Amazon S3 Vectors

### When to Use

**RAG vector storage** when cost efficiency matters more than single-digit-ms latency. S3 Vectors (GA since Dec 2025) provides a serverless, cost-efficient vector store — AWS states it reduces the cost to upload, store, and query vectors **by up to 90%** versus specialized vector databases ([S3 Vectors GA announcement](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-vectors-generally-available)). No cluster provisioning, no capacity planning.

### Properties

- **Serverless** — no instances to manage; scales automatically.
- **S3-native** — vectors stored as S3 objects; inherits S3 durability (11 nines), encryption, lifecycle policies.
- **Cost model** — S3 storage pricing + request pricing; dramatically cheaper than provisioned vector DB clusters for large corpora with moderate query rates.
- **Query latency** — higher than in-memory vector DBs; suitable for async RAG, batch enrichment, and agentic retrieval where 50–200 ms is acceptable.

### When NOT to Use

- **Real-time chat with <20 ms vector lookup** → PGVector on Aurora or OpenSearch with k-NN.
- **Hybrid search (vector + keyword + filtering)** with complex query patterns → OpenSearch.
- Customer already running and satisfied with an existing vector database.

## Model Artifact Handling

Per [EKS AI/ML Performance Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-performance.html), three patterns for getting model weights to pods:

| Strategy | Model size | Cold-start | Coupling | Best for |
|----------|-----------|------------|----------|----------|
| **Bake into container image** | <5 GB | Zero (weights in image layers) | Model release = image release | Small models, embeddings, classifiers |
| **Download at runtime via Mountpoint S3 CSI** | 5 GB – 200+ GB | Seconds to minutes (lazy-load + cache) | Decoupled — update S3, pods pick up new weights on restart | 7B–70B+ LLMs, frequent model updates |
| **Pre-cache on FSx for Lustre** | Any | Zero (if pre-warmed) | Requires FSx lifecycle management | Training data, very large weights where S3 latency is unacceptable |

**Decision rule:** Default → Mountpoint S3 CSI for inference weights (decoupled, lazy-load, per-pod cache). Use FSx pre-cache only when S3 bandwidth is the cold-start bottleneck (rare for inference; common for training). Bake-in only for tiny models where zero cold-start is critical and model release cadence matches image release cadence.

## Storage + Karpenter Integration Notes

- **FSx same-AZ:** Pin the training NodePool's `topology.kubernetes.io/zone` to the FSx AZ. Accept reduced Spot diversity in exchange for correct latency behavior.
- **Mountpoint S3 — no zone pin needed:** S3 is regional; pods on any AZ get equivalent bandwidth.
- **EFS — no zone pin needed:** EFS mount targets exist in each AZ.
- **Consolidation safety:** Karpenter consolidation can evict pods from underutilized nodes. Training pods with active FSx mounts must carry `karpenter.sh/do-not-disrupt: "true"` to prevent mid-write eviction.

## Sources

- [EKS AI/ML Storage Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-storage.html)
- [EKS AI/ML Performance Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-performance.html)
- [Mountpoint for Amazon S3 CSI Driver](https://docs.aws.amazon.com/eks/latest/userguide/s3-csi.html)
- [FSx for Lustre CSI Driver](https://docs.aws.amazon.com/eks/latest/userguide/fsx-csi.html)
- [Architecting scalable checkpoint storage for large-scale ML training on AWS](https://aws.amazon.com/blogs/storage/architecting-scalable-checkpoint-storage-for-large-scale-ml-training-on-aws/)
- [Amazon S3 Vectors](https://aws.amazon.com/s3/features/vectors/)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — `infra/training` (FSx + S3 DRA), `infra/inference-ready-cluster` (Mountpoint S3 CSI)
