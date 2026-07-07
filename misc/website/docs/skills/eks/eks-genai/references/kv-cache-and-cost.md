---
title: "KV-Cache Tiering & Cost Optimization"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/kv-cache-and-cost.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/kv-cache-and-cost.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/kv-cache-and-cost.md). Edit the source, not this page.
:::

# KV-Cache Tiering & Cost Optimization

Opinionated guidance for KV-cache tiering with LMCache and the priority-ordered cost-optimization levers for GenAI workloads on EKS. Always directional ranges with caveats — never point estimates.

## KV-Cache Tiering with LMCache

[LMCache](https://github.com/LMCache/LMCache) adds a multi-tier cache for KV tensors in front of vLLM — reusing computed attention states across requests that share prompt prefixes. This eliminates redundant prefill computation for system prompts, RAG contexts, and tool-call preambles.

### Cache Hierarchy

```text
L0  GPU VRAM     — vLLM's native PagedAttention cache (always present)
L1  CPU RAM      — LMCache local CPU tensor store (same pod, DRAM)
L2  Remote store — Amazon ElastiCache Serverless (Valkey) via TLS
```

| Tier | Latency | Capacity | When it helps |
|------|---------|----------|---------------|
| **L0 GPU VRAM** | ~0 (in-place) | Limited by `--gpu-memory-utilization` | Every request (vLLM built-in) |
| **L1 CPU RAM** | ~1-5 ms | Configurable via `LMCACHE_MAX_LOCAL_CPU_SIZE` (GB) | Same-pod repeated prefixes; single-replica workloads |
| **L2 Remote Valkey** | ~5-15 ms (same-AZ TLS) | Effectively unbounded (ElastiCache Serverless scales) | Multi-pod prefix sharing; long/shared contexts across replicas |

**When L2 adds value:** Multi-pod deployments where different replicas serve requests with overlapping prefixes (RAG contexts, system prompts, agentic tool preambles). For short, unique prompts on a single pod, L1 CPU is sufficient — the network fetch to L2 can be slower than recompute.

### Measured Performance

Workshop-validated on **g6e.2xlarge (L40S)**, Ministral-3-8B-Instruct-2512, 90% prompt overlap:

| Metric | Cold (no cache) | Warm (L1/L2 hit) | Speedup |
|--------|----------------|-------------------|---------|
| **TTFT** | 0.43 s | 0.12 s | **~3.6×** |

The speedup scales with prompt overlap percentage and prompt length — longer shared prefixes yield larger savings. Short unique prompts see negligible benefit.

### LMCache Configuration

```bash
# Environment variables on vLLM pod
LMCACHE_LOCAL_CPU=True                              # enable L1 CPU tier
LMCACHE_MAX_LOCAL_CPU_SIZE=8                        # GB of CPU RAM for L1
LMCACHE_REMOTE_URL=rediss://my-valkey.cache.amazonaws.com:6379  # TLS (double-s)
LMCACHE_CHUNK_SIZE=256                              # tokens per cache chunk
LMCACHE_REMOTE_SERDE=naive                          # serialization format

# Required vLLM settings when LMCache is active
VLLM_ATTENTION_BACKEND=FLASHINFER                   # required
PYTHONHASHSEED=0                                    # cross-pod cache-key stability
```

vLLM launch args when LMCache is wired:

```bash
--enforce-eager                                     # required with FLASHINFER + LMCache
--kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
```

### ElastiCache Serverless (Valkey) for L2

Deploy Amazon ElastiCache Serverless with Valkey engine as the L2 backing store:

- **TLS required** — the `rediss://` (double-s) scheme enables in-transit encryption
- **Same-AZ as vLLM pods** — cross-AZ adds 1-3 ms round-trip that erodes the cache benefit
- **Security group** — allow inbound TCP 6379 from the vLLM pod security group only
- **IAM auth** — use ElastiCache IAM authentication with EKS Pod Identity for zero-secret configuration

### Prefix Caching Strategy

LMCache is most effective when requests share long prefixes. Design your prompts to maximize prefix overlap:

| Pattern | Prefix overlap | LMCache benefit |
|---------|---------------|-----------------|
| System prompt + user query | High (system prompt cached) | ✅ Strong — system prompt computed once |
| RAG context + question | High (same retrieved docs across users) | ✅ Strong — context block cached |
| Agentic tool preamble + tool call | High (tool definitions cached) | ✅ Strong — tool schema computed once |
| Unique user conversations (no shared prefix) | Low | ⚠️ Minimal — recompute is faster than cache fetch |

**Decision rule:** Enable LMCache when ≥ 50% of request tokens are shared prefixes across requests. Skip for workloads with unique, short prompts.

### Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│  EKS Cluster                                                │
│                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐      │
│  │ vLLM Pod 1  │   │ vLLM Pod 2  │   │ vLLM Pod 3  │      │
│  │ L0: GPU KV  │   │ L0: GPU KV  │   │ L0: GPU KV  │      │
│  │ L1: CPU RAM │   │ L1: CPU RAM │   │ L1: CPU RAM │      │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘      │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │ rediss:// (TLS)                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────┐       │
│  │  Amazon ElastiCache Serverless (Valkey) — L2    │       │
│  │  Same-AZ as vLLM pods                          │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Cost-Optimization Levers (Priority Order)

Savings levers ordered by impact. Apply top-down — each lever is independent; stack them for compounding savings.

| Priority | Lever | Directional savings | When to apply | Caveat |
|----------|-------|--------------------:|---------------|--------|
| **1** | **Capacity Blocks for ML** | Capacity assurance (not a fixed discount) | Planned multi-day training runs; guaranteed p5/p5e/trn2 capacity | Reservation-fee pricing set by supply/demand — AWS publishes no fixed discount vs on-demand; primary value is *guaranteed* access, not savings. Requires advance reservation; not elastic |
| **2** | **Neuron over GPU** | 40-50% price-perf | Transformer-family models (Llama, Mistral, Qwen); steady-state production inference on Inf2; training on Trn1/Trn2 | 1-2 week compilation ramp; not all architectures supported |
| **3** | **Spot + Checkpoint/Resume** | 60-90% vs on-demand | Fault-tolerant training with FSx checkpoint loop; dev/experimentation | Requires checkpoint logic; interruption risk; NOT for SLA-bound inference |
| **4** | **MIG / Time-Slicing** | 2-7× density | Shared dev clusters; small models that don't need a full GPU; multi-tenant experimentation | Reduced per-slice memory; not for latency-critical production |
| **5** | **Karpenter Consolidation** | 20-40% off-peak | Inference clusters with variable traffic; off-peak GPU node reclamation | Set `do-not-disrupt` on training pods; aggressive consolidation can increase cold-start |
| **6** | **KV-Cache Tiering + S3 Lazy-Load** | 10-30% compute reduction | High-overlap prompt workloads (RAG, agentic, system prompts); reduce redundant prefill GPU-seconds | Requires LMCache + ElastiCache setup; benefit proportional to prefix overlap |

### Lever 1 — Capacity Blocks for ML

Reserve GPU/Neuron capacity for defined time windows (1-14+ days) at substantially-below-on-demand pricing. Best for:

- Planned pre-training runs with known duration
- Fine-tuning campaigns (e.g., weekly retrain cycle)
- Benchmark/eval jobs that must not be interrupted

Reference: [EC2 Capacity Blocks for ML Pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/).

### Lever 2 — Neuron Over GPU

For supported Transformer-family models, Inferentia2 delivers up to ~40% better price-performance than comparable GPU instances, and Trainium delivers up to ~50% cost-to-train savings. The savings are real but require:

- One-time model compilation (`neuron_compile`) — budget 1-2 weeks for first model
- Verification that the specific model architecture is supported
- Neuron Monitor for observability (different metrics than DCGM)

Reference: [AWS EC2 Trn1 Instance Types](https://aws.amazon.com/ec2/instance-types/trn1/); [AWS EC2 Inf2 Instance Types](https://aws.amazon.com/ec2/instance-types/inf2/).

### Lever 3 — Spot + Checkpoint

Spot instances for training deliver 60-90% savings vs on-demand — but ONLY when checkpoint/resume is wired:

```text
Without checkpoint: Spot interruption → restart from epoch 0 → COST BURN
With checkpoint:    Spot interruption → resume from last checkpoint → max 15-30 min lost
```

See [distributed-training.md](distributed-training) for the FSx + S3 DRA checkpoint architecture.

### Lever 4 — MIG / Time-Slicing

**Multi-Instance GPU (MIG)** partitions H100/A100 into isolated GPU slices — each slice gets dedicated memory, compute, and L2 cache. Use for multi-tenant dev clusters where teams share expensive GPU nodes.

**Time-slicing** shares a single GPU across pods via time-multiplexing — no memory isolation, no compute guarantee. Use only for dev/test where latency doesn't matter.

| Technique | Isolation | Best for | Not for |
|-----------|-----------|----------|---------|
| MIG | Memory + compute + L2 | Multi-tenant dev; small model experimentation; CI/CD GPU tests | Production inference (per-slice memory limits model size) |
| Time-slicing | None (cooperative) | Dev notebooks; very small models; experimentation | Any production workload; latency-sensitive serving |

### Lever 5 — Karpenter Consolidation

Karpenter automatically right-sizes GPU node count during off-peak. Configure:

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu-inference
spec:
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 5m    # reclaim empty GPU nodes after 5 min idle
```

**Guard:** Set `karpenter.sh/do-not-disrupt: "true"` on training pods — consolidation must not preempt multi-hour training runs.

### Lever 6 — KV-Cache Tiering + S3 Lazy-Load

KV-cache tiering (LMCache) reduces redundant GPU compute for overlapping prefixes — each cache hit is prefill GPU-seconds you don't pay for. Compound with S3 lazy-load (Mountpoint S3 CSI or Run:ai Streamer) to eliminate persistent storage costs for model weights.

Combined savings: fewer GPU-seconds per request (cache) + zero EBS/FSx cost for inference-only model storage (S3).

## Cost Guardrails

- **Never give point estimates.** GenAI costs depend on model size, sequence length, batch profile, traffic pattern, Spot mix, and KV-cache hit rate. Use directional ranges: "expect 30-50% savings with Neuron migration" or "Spot training typically saves 60-90% vs on-demand with proper checkpoint/resume."
- **Always caveat.** "Actual savings depend on your specific workload profile — validate with a 2-week pilot before committing capacity changes."
- **Stack levers.** Levers 1-6 are independent and composable — a customer using Capacity Blocks (1) + Neuron (2) + KV-cache (6) compounds savings multiplicatively across training + inference.
- **Account for engineering cost.** Neuron compilation, checkpoint/resume logic, LMCache integration, and Karpenter tuning all require engineering time. The payback period is typically 4-8 weeks for a dedicated platform team; longer for teams splitting attention.

## Anti-Patterns

| Anti-pattern | Why it's wrong | Correct approach |
|-------------|---------------|-----------------|
| Spot for SLA-bound inference | Interruptions break per-request SLAs | On-Demand + Karpenter consolidation for cost savings |
| GPU for all training (no Neuron evaluation) | 40-50% savings left on the table | Evaluate Neuron for Transformer-family; GPU for novel architectures |
| No checkpoint + Spot training | Every interruption = full restart | FSx + S3 DRA checkpoint every 15-30 min |
| Full GPU node 24/7 for bursty inference | Paying for idle GPU hours | Karpenter consolidation or KServe scale-to-zero |
| Pulling model from HF at every pod start | Egress cost + rate limits + cold-start | Pre-cache to S3; use Run:ai Streamer or Mountpoint S3 CSI |
| Cross-AZ FSx for Lustre | Latency penalty dwarfs FSx's native performance | Same-AZ FSx + compute nodes |

## Sources

- [EKS AI/ML Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html)
- [EC2 Capacity Blocks for ML Pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/)
- [AWS EC2 Trn1 Instance Types](https://aws.amazon.com/ec2/instance-types/trn1/)
- [AWS EC2 Inf2 Instance Types](https://aws.amazon.com/ec2/instance-types/inf2/)
- [LMCache GitHub](https://github.com/LMCache/LMCache)
- [Generative AI on EKS using NVIDIA GPU Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — inference + training blueprints
- [How Vannevar Labs cut ML inference costs by 45% using Ray on Amazon EKS](https://aws.amazon.com/blogs/containers/how-vannevar-labs-cut-ml-inference-costs-by-45-using-ray-on-amazon-eks)
- [Architecting scalable checkpoint storage for large-scale ML training on AWS](https://aws.amazon.com/blogs/storage/architecting-scalable-checkpoint-storage-for-large-scale-ml-training-on-aws/)
