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
- **Capacity:** route the service to the right GPU pool with a **capacity-provider strategy** (one ASG per GPU type — see [capacity-and-scaling.md](capacity-and-scaling.md)).
- **Load balancer:** ALB for HTTP/gRPC inference APIs; NLB for raw TCP / ultra-low-overhead. Tune the **health-check grace period** generously — model load + warmup can take minutes, and a too-short grace period kills tasks mid-warmup.
- **Networking:** `awsvpc` mode (task ENI) is the default for services behind a load balancer.
- **Endpoint authentication + exposure:** decide **internal (internal ALB/NLB in private subnets, reached over VPC/PrivateLink)** vs **internet-facing** up front. A self-hosted model endpoint has **no built-in auth** — put authentication in front of it: Cognito/OIDC on the ALB, an API Gateway or a mutual-TLS/JWT-validating reverse-proxy sidecar, or WAF + an authorizer. Never expose a raw model API to the internet unauthenticated. Deep endpoint-security / compliance design → route to **`ecs-security`**.

### Token streaming vs ALB idle timeout (the canonical self-hosted-LLM gotcha)

Streaming LLM responses (SSE / chunked `text/event-stream`) that keep a single HTTP connection open longer than the **ALB idle timeout (default 60s)** get **severed mid-generation** — the client sees a truncated stream on long completions. Fix by **raising the ALB idle timeout** to exceed the longest expected generation (e.g. several minutes), ensuring the serving engine **emits tokens/keep-alive frequently** (regular SSE chunks reset the idle timer), and setting client and target-group timeouts consistently. This is the most common "streaming works in dev, breaks in prod" failure for self-hosted LLMs on ECS behind an ALB.

## Serving Engine — Bring Your Own Container

ECS is engine-agnostic; the engine runs inside your image. Common choices (all deployable as an ECS task):

| Engine | Fit | Notes on ECS |
|---|---|---|
| **vLLM** | High-throughput LLM inference (GPU or Neuron via `neuronx-distributed-inference`) | OpenAI-compatible API; PagedAttention; run as a single GPU task or scale via ECS Service Auto Scaling |
| **NVIDIA Triton Inference Server** | Multi-framework / ensembles / TensorRT | One server, multiple model formats; model repo on S3 |
| **TorchServe / TensorFlow Serving** | Framework-native serving | Straightforward container; good for classic models |
| **Text Generation Inference (TGI)** | HF-ecosystem LLM serving | Container image + weights from S3/HF |
| **Custom (FastAPI + framework)** | Bespoke pre/post-processing | Full control; you own batching/metrics |

Note: **KubeRay / Ray Serve, KServe, and the JARK stack are Kubernetes constructs** — they belong to `eks-genai`, not ECS. On ECS you can still run **Ray** inside a task (see [distributed-training.md](distributed-training.md)), but the K8s-operator serving stacks do not apply.

## Model Loading — Get Weights to the Task

Choose based on model size and cold-start tolerance (full matrix in [storage.md](storage.md)):

| Pattern | Model size | Cold-start | Best for |
|---|---|---|---|
| **Bake into image** | < ~5 GB | Zero (in image layers) | Small/classic models; air-gapped |
| **Pull from S3 at start** | 5–200+ GB | Seconds–minutes | LLMs; decoupled model/image release |
| **Mount EFS** | Any (shared) | Low | Multiple tasks/nodes sharing weights (ReadWriteMany) |
| **FSx for Lustre** | Very large | Zero if pre-warmed | High-throughput weight/checkpoint I/O |

Rules: **on the EC2 launch type the container image downloads fully before the task starts** — SOCI lazy loading is a **Fargate-PV1.4-only** feature, and Fargate has no GPU, so SOCI is unavailable on every host this skill covers ([storage.md](storage.md)). Mitigate the multi-GB CUDA/DLC image tax with **warm pools of pre-pulled instances, image caching on the instance NVMe, and lean/baked AMI layers** — not SOCI. **Never pull weights from Hugging Face at every task start** (egress cost, rate limits, cold-start) — stage in S3/ECR first. For Neuron, **pre-compile and ship the compiled artifact** — never compile at task startup ([neuron-on-ecs.md](neuron-on-ecs.md)).

## Sizing the GPU to the Model — VRAM Method (not just size buckets)

The coarse "7B–13B → g6e" buckets are a starting point; size VRAM explicitly before choosing an instance:

- **Weights:** `params × bytes-per-param` — FP16/BF16 = 2 bytes (a 7B model ≈ 14 GB; 70B ≈ 140 GB), INT8 ≈ 1 byte, INT4/AWQ/GPTQ ≈ 0.5 byte.
- **KV cache (often the silent OOM):** grows with `batch × sequence_length × 2 (K+V) × num_layers × hidden_dim × bytes` — at long context and high concurrency this can rival or exceed the weights. Size for peak concurrent context, not just the model.
- **Overhead:** add headroom for activations, CUDA context, and fragmentation (rule of thumb ~10–20%).
- Sum the three, then pick a GPU whose memory (from the [compute-hardware.md](compute-hardware.md) table) fits with margin — or shard across GPUs (tensor parallel) when it doesn't. This is why a 70B model at long context needs multi-GPU (e.g. g6e.48xlarge / p4d) even though the weights alone might "fit."

## Autoscaling the Inference Service

Use **ECS Service Auto Scaling** (Application Auto Scaling) — target-tracking on a meaningful signal:

- **ALB request count per target** (`ALBRequestCountPerTarget`) — simplest proxy for load.
- **Custom CloudWatch metric** — publish queue depth / in-flight requests / TTFT from the serving engine for a truer signal. GPU utilization as an autoscaling signal is **agentless only on Managed Instances**; on the **EC2 launch type** you must publish it via the CloudWatch agent (`nvidia_smi`, host-level) or a DCGM exporter (per-task) — the agentless MI metrics won't exist (see [observability.md](observability.md)).
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

See [service-boundaries.md](service-boundaries.md).

## AI Gateway / Agentic & RAG on ECS

- **AI gateway:** a self-hosted model-routing/observability/rate-limiting gateway such as **LiteLLM** runs well as a CPU-only ECS service in front of both your ECS-hosted models and Bedrock — this is a documented `ai-gateway` target. Use it to give clients one OpenAI-compatible endpoint, centralize auth/keys, and do cost attribution across self-hosted + managed models.
- **Agentic / RAG orchestrators:** a CPU-only orchestrator/RAG retriever (calling your GPU inference service and/or Bedrock) fits fine on ECS — including on Fargate for the non-accelerated part ([service-boundaries.md](service-boundaries.md)). Boundary to name: for a **fully-managed agent runtime with memory/tools/identity**, route to **Amazon Bedrock AgentCore**; **self-host on ECS** when you need to own the framework/serving stack. Agentic workloads with autonomous tool/code execution raise sandbox-escape risk → loop in **`ecs-security`**.

## Sources

- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)
- [Amazon ECS Best Practices Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html) (tasks & services, health checks, autoscaling)
- [Target tracking scaling for Amazon ECS Service Auto Scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [Automatically manage Amazon ECS capacity with cluster auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html)
- [Using Amazon ECS with NVIDIA GPUs to accelerate drug discovery](https://aws.amazon.com/blogs/containers/using-amazon-ecs-with-nvidia-gpus-to-accelerate-drug-discovery/)
