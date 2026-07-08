---
title: "Model Inference & Serving on Amazon ECS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/inference-serving.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-genai/references/inference-serving.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/inference-serving.md). Edit the source, not this page.
:::

# Model Inference & Serving on Amazon ECS

Patterns for serving ML / LLM inference from containers on ECS-on-EC2 (or Managed Instances) GPU/Neuron capacity. ECS gives you the container primitives — task definition, service, load balancer, autoscaling — and you bring the serving engine inside the container.

## The Inference Service Shape on ECS

A production inference service on ECS is a standard **ECS Service** with GPU/Neuron tasks behind a load balancer:

```text
ALB / NLB
   │  target group (health check → /health or /v1/models)
   ▼
ECS Service  (desired count N, capacity-provider strategy → GPU ASG)
   │
   ├── Task: [ serving-engine container ]  resourceRequirements GPU:1
   │        weights loaded from S3 / EFS (see storage.md)
   └── Task: …  (Service Auto Scaling on request/latency metric)
```

Key choices:
- **Launch host:** ECS-on-EC2 or Managed Instances (never Fargate — no GPU). CPU-only pre/post-processing sidecars can share the task.
- **Capacity:** route the service to the right GPU pool with a **capacity-provider strategy** (one ASG per GPU type — see [capacity-and-scaling.md](capacity-and-scaling)).
- **Load balancer:** ALB for HTTP/gRPC inference APIs; NLB for raw TCP / ultra-low-overhead. Tune the **health-check grace period** generously — model load + warmup can take minutes, and a too-short grace period kills tasks mid-warmup.
- **Networking:** `awsvpc` mode (task ENI) is the default for services behind a load balancer.

## Serving Engine — Bring Your Own Container

ECS is engine-agnostic; the engine runs inside your image. Common choices (all deployable as an ECS task):

| Engine | Fit | Notes on ECS |
|---|---|---|
| **vLLM** | High-throughput LLM inference (GPU or Neuron via `neuronx-distributed-inference`) | OpenAI-compatible API; PagedAttention; run as a single GPU task or scale via ECS Service Auto Scaling |
| **NVIDIA Triton Inference Server** | Multi-framework / ensembles / TensorRT | One server, multiple model formats; model repo on S3 |
| **TorchServe / TensorFlow Serving** | Framework-native serving | Straightforward container; good for classic models |
| **Text Generation Inference (TGI)** | HF-ecosystem LLM serving | Container image + weights from S3/HF |
| **Custom (FastAPI + framework)** | Bespoke pre/post-processing | Full control; you own batching/metrics |

Note: **KubeRay / Ray Serve, KServe, and the JARK stack are Kubernetes constructs** — they belong to `eks-genai`, not ECS. On ECS you can still run **Ray** inside a task (see [distributed-training.md](distributed-training)), but the K8s-operator serving stacks do not apply.

## Model Loading — Get Weights to the Task

Choose based on model size and cold-start tolerance (full matrix in [storage.md](storage)):

| Pattern | Model size | Cold-start | Best for |
|---|---|---|---|
| **Bake into image** | < ~5 GB | Zero (in image layers) | Small/classic models; air-gapped |
| **Pull from S3 at start** | 5–200+ GB | Seconds–minutes | LLMs; decoupled model/image release |
| **Mount EFS** | Any (shared) | Low | Multiple tasks/nodes sharing weights (ReadWriteMany) |
| **FSx for Lustre** | Very large | Zero if pre-warmed | High-throughput weight/checkpoint I/O |

Rules: **pre-cache large model images** (SOCI/parallel pull helps GPU-pod start; huge CUDA/DLC images dominate task launch time); **never pull weights from Hugging Face at every task start** (egress cost, rate limits, cold-start) — stage in S3/ECR first. For Neuron, **pre-compile and ship the compiled artifact** — never compile at task startup ([neuron-on-ecs.md](neuron-on-ecs)).

## Autoscaling the Inference Service

Use **ECS Service Auto Scaling** (Application Auto Scaling) — target-tracking on a meaningful signal:

- **ALB request count per target** (`ALBRequestCountPerTarget`) — simplest proxy for load.
- **Custom CloudWatch metric** — publish queue depth / in-flight requests / TTFT from the serving engine for a truer signal; GPU utilization from Container Insights enhanced observability (see [observability.md](observability)).
- Cluster-level: ECS **cluster auto scaling** grows the GPU ASG when tasks can't place (`PROVISIONING`). Remember the **~15-minute scale-in latency** — factor it into GPU cost. Use warm pools to cut GPU-instance warm-up.

```json
// Application Auto Scaling target tracking on ALB requests per target
{
  "TargetValue": 30.0,
  "PredefinedMetricSpecification": { "PredefinedMetricType": "ALBRequestCountPerTarget" },
  "ScaleInCooldown": 300,
  "ScaleOutCooldown": 60
}
```

Set `scale-out` faster than `scale-in` for GPU services — losing a warm GPU task is expensive to re-warm; adding one late hurts latency.

## Serving Availability & Deployment Safety

- **Min-healthy-% / max-%** tuned for GPU scarcity: a rolling deploy that briefly needs 2× GPU capacity may not place if the ASG can't scale. Confirm headroom or use a slower rollout.
- **Deployment circuit breaker** with rollback protects against a bad model image.
- **Health-check grace period** long enough for model load + warmup, or ECS will kill healthy-but-warming tasks.
- **Connection draining** so in-flight inference requests complete before task stop.

## When to Route Off ECS for Serving

- Need **scale-to-zero**, **fractional-GPU (MIG/time-slicing) multi-model packing**, or a **Kubernetes-native serving mesh (KServe/Ray Serve/JARK)** → **`eks-genai`**.
- Want a **fully-managed inference endpoint** (autoscaling, multi-model endpoints, no cluster to run) → **Amazon SageMaker** real-time/serverless/async inference.
- Just need a **managed foundation-model API** with no self-hosting → **Amazon Bedrock**.

See [service-boundaries.md](service-boundaries).

## Sources

- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)
- [Amazon ECS Best Practices Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html) (tasks & services, health checks, autoscaling)
- [Target tracking scaling for Amazon ECS Service Auto Scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [Automatically manage Amazon ECS capacity with cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html)
- [Using Amazon ECS with NVIDIA GPUs to accelerate drug discovery](https://aws.amazon.com/blogs/containers/using-amazon-ecs-with-nvidia-gpus-to-accelerate-drug-discovery/)
