---
title: "eks-genai"
description: "Use whenever someone is building, training, fine-tuning, or serving a generative AI / LLM workload on Amazon EKS — phrased as \"GPU vs Trainium/Inferentia\", \"vLLM on EKS\", \"Ray Serve / KubeRay\", \"distributed training on EKS\", \"FSx for Lustre for ML\", \"Karpenter for GPU\", \"EFA / NCCL multi-node\", \"DCGM / Neuron Monitor\", \"LiteLLM / AI gateway\", \"RAG on EKS\", \"agentic AI on EKS\", or \"self-host Llama / Mistral / Qwen\". Walks the opinionated 6-layer stack (compute → cluster/scheduler → frameworks → storage → observability → AI gateway), the GPU-vs-Neuron decision, the JARK + vLLM + LiteLLM canonical reference, KV-cache tiering, cost levers (Neuron, Spot, Capacity Blocks), and a non-negotiable security baseline. Trigger even if \"GenAI\" is never said — any GPU/Neuron, inference-serving, or distributed-training decision on EKS qualifies. Skip for SageMaker-only or Bedrock-only (no self-hosting) asks, and for generic cluster design/build with no AI/ML workload (use eks-design / eks-build)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/SKILL.md). Edit the source, not this page.
:::


# GenAI on Amazon EKS

End-to-end opinionated guidance for running generative AI / LLM workloads on Amazon EKS, structured as a **6-layer stack** from compute hardware up through the AI gateway. This skill is opinionated: it recommends one AWS-canonical reference stack — the **JARK stack** (JupyterHub + Argo + Ray + Karpenter) extended with **vLLM** serving and a **LiteLLM** gateway — and surfaces the alternatives plus the customer-context flags that justify deviating.

Two sources are the canonical foundation and every recommendation must align with one or both: the [EKS AI/ML Best Practices guide](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html) and the [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) reference implementation. For "how do I run a single EKS cluster well" (compute, networking, upgrades) use `eks-best-practices`; for designing/building the cluster itself use `eks-design` / `eks-build`. This skill is the GenAI *workload* layer on top.

## When to Use This Skill

**Activate when the user wants to:**
- Choose GenAI hardware — NVIDIA GPU (p5/g6/g6e) vs AWS Neuron (Trainium/Inferentia)
- Serve an LLM (vLLM, Ray Serve, Triton, KServe) or run distributed training/fine-tuning on EKS
- Design GPU/Neuron scheduling (Karpenter NodePools, device plugins, EFA, Capacity Blocks, Spot)
- Pick ML storage (FSx for Lustre, Mountpoint S3 CSI, EFS, S3 Vectors) or wire GPU/Neuron observability
- Stand up an AI gateway (LiteLLM/Envoy), RAG pipeline, or agentic platform on EKS
- Optimize GenAI cost (Neuron migration, Spot+checkpoint, KV-cache tiering, consolidation)

**Don't use this skill for:**
- SageMaker-only or Bedrock-only (no self-hosting) — defer to ML/Bedrock guidance; this skill covers Bedrock only as a *gateway target* alongside self-hosted models
- "Is EKS the right base?" not yet decided — run container-service selection first
- Generic cluster design/build with no AI/ML workload → `eks-design` / `eks-build`
- Self-service golden paths / Internal Developer Platform for ML teams (Backstage templates, ML-pipelines-as-a-service, multi-tenant self-serve) → `eks-platform-engineering`. This skill is the GenAI *workload* layer (how to serve/train the model); platform-engineering is the *self-service delivery* layer (how teams request it). Ray Serve can appear in both — use this skill for the serving architecture, that one for the golden-path wrapper.
- Generic Kubernetes concepts (Claude knows these)

## The 6-Layer Stack

```text
Layer 6  AI Gateway / App   LiteLLM · Envoy AI Gateway · RAG · Bedrock AgentCore · Strands
Layer 5  Observability      DCGM Exporter · Neuron Monitor · Prometheus/Grafana · AMP/AMG
Layer 4  Storage            FSx for Lustre · Mountpoint S3 CSI · EFS · S3 Vectors
Layer 3  Frameworks         Ray + KubeRay · vLLM · Triton/Dynamo · Kubeflow/KServe (JARK)
Layer 2  Cluster/Scheduler  Karpenter · NVIDIA + Neuron device plugins · EFA · Capacity Blocks
Layer 1  Compute/Hardware   NVIDIA GPU (p5/g6/g6e) · AWS Neuron (Trainium/Inferentia)
```

Walk the customer **bottom-up** (Layer 1 → 6) on first engagement; revisit top-down for optimization. Each layer below gives the decision rule; depth is in the references.

### Layer 1 — Compute / Hardware (the single most-impactful decision)

AWS docs explicitly recommend Neuron *when the workload permits it*. **Do not reflexively pick NVIDIA GPU** — the most common SA mistake.

- **Default to AWS Neuron** (Trn2/Trn1 training, Inf2 inference) when the model is Transformer-family (Llama, Mistral, Qwen, Falcon) + framework is PyTorch/vLLM + cost-conscious + the team can absorb a 1-2 week compilation ramp. Up to ~50% cost-to-train (Trainium) / ~40% better price-performance (Inferentia2).
- **Default to NVIDIA GPU** (g6/g6e inference, p5/p5e training) for fastest time-to-first-success, CUDA-only dependencies, novel/non-Transformer architectures, or multi-modal models.

Right hardware = f(workload type × model family × latency × cost posture × team skill × timeline) — never one dimension alone. Full instance matrix + MIG/time-slicing: [compute-hardware.md](references/compute-hardware).

### Layer 2 — Cluster / Scheduler

**Karpenter is the only recommended autoscaler** for GPU/Neuron (Cluster Autoscaler is not). Provision **two NodePools** (GPU + Neuron) from day one so future hardware migration is a cost experiment, not a re-architecture. Use EKS-optimized accelerated AMIs (Bottlerocket/AL2023) so drivers are pre-installed. Multi-node training needs **EFA + NUMA pinning + static CPU manager** (bandwidth halves without them) and NCCL/MPI in the image. Use the **Neuron device plugin** (not the DRA driver) with Karpenter/Auto Mode. Guarantee planned training capacity with **Capacity Blocks for ML**. Spot rule: training only with checkpoint/resume; inference On-Demand. Details: [cluster-and-scheduling.md](references/cluster-and-scheduling).

### Layer 3 — Orchestration / Frameworks (most opinionated layer)

Default to the **JARK stack** + **vLLM**. vLLM is the default LLM inference engine (PagedAttention, OpenAI-compatible, GPU + Neuron via `neuronx-distributed-inference`); Ray + KubeRay is the default for distributed training and multi-replica serving. Reach for Triton (multi-framework/TensorRT), Dynamo (disaggregated prefill/decode), Kubeflow (full MLOps), or KServe (scale-to-zero) only when their specific flag applies. Decision table: [inference-serving.md](references/inference-serving) and [distributed-training.md](references/distributed-training).

### Layer 4 — Storage

Default → **Mountpoint for S3 CSI** for inference (lazy-load weights, per-pod cache) + **FSx for Lustre** for training (sub-ms, EFA-connected, S3 DRA for checkpoint offload). Use **EFS** only for shared multi-model weights, and **S3 Vectors** for cost-efficient RAG vector storage. Critical rule: **FSx in the same AZ as the GPU/Neuron nodes** — cross-AZ latency dwarfs FSx's native performance. Pre-warm FSx before launching Spot capacity. Details: [storage.md](references/storage).

### Layer 5 — Observability

GenAI observability adds three first-class concerns over standard EKS: accelerator utilization/memory, per-token/per-request latency, and per-workload cost attribution. Stack: **NVIDIA DCGM Exporter** (GPU) + **AWS Neuron Monitor** (Trn/Inf) → Prometheus → Grafana, with vLLM metrics (TTFT, time-per-output-token, queue time). Use **Amazon Managed Prometheus + Managed Grafana** in production; keep observability pods off the GPU/Neuron nodes. Details: [observability.md](references/observability).

### Layer 6 — AI Gateway / Application

For multi-model (self-hosted + Bedrock) serving, a gateway is non-negotiable. Default → **LiteLLM** (OpenAI-compatible proxy, per-tenant rate limiting + token cost accounting, Langfuse tracing); **Envoy AI Gateway** when you need L7 routing at ingress. For RAG, default the vector store to **Bedrock Knowledge Bases** (or **S3 Vectors** for cost) unless self-managed is required. For agents, default to **Bedrock AgentCore** (managed) or **Strands Agents SDK** for self-hosted. Details: [ai-gateway.md](references/ai-gateway), [agentic-and-rag.md](references/agentic-and-rag).

## The Opinionated Reference Stack

The AWS-canonical default, shipped end-to-end in `awslabs/ai-on-eks` and the GenAI-on-EKS workshops:

| Layer | Default | Notes |
|-------|---------|-------|
| Compute | Neuron (Inf2/Trn2) for Transformer LLMs; g6/g6e or p5 for GPU | Provision both NodePools |
| Scheduler | Karpenter + device plugin + (EFA for multi-node) | Bottlerocket/AL2023 accelerated AMI |
| Serving | vLLM (+ Ray Serve for scale) | OpenAI-compatible; Run:ai Streamer to stream weights from S3 |
| Training | Ray Train / PyTorch FSDP | FSx for Lustre + S3 DRA checkpointing |
| Storage | Mountpoint S3 CSI (inference) + FSx Lustre (training) | EFS for shared weights; S3 Vectors for RAG |
| Observability | DCGM / Neuron Monitor → Prometheus → Grafana + AMP/AMG | vLLM + Ray dashboards |
| Gateway | LiteLLM (+ Langfuse) | Routes self-hosted + Bedrock |
| Optimization | LMCache KV-cache tiering (L1 CPU / L2 Valkey) | Prefix-cache reuse across pods |

Pointing customers at the [`awslabs/ai-on-eks` blueprints](https://github.com/awslabs/ai-on-eks) is the fastest credible path from idea to production. The current NVIDIA workshop validates this stack on **EKS Auto Mode (K8s 1.34)** with **g6e (L40S)**, **vLLM + KubeRay**, **Strands Agents**, **LMCache**, and **kube-prometheus-stack + AMP**. Concrete versions and use-case → blueprint mapping: [reference-implementations.md](references/reference-implementations).

## Security Baseline (non-negotiable)

Every GenAI-on-EKS recommendation MUST include: **EKS Pod Identity / IRSA** for pod credentials (never static keys); **ECR image scanning**; **secrets via Secrets Manager/Parameter Store + Secrets Store CSI** (never baked into images); **model artifact provenance** (image signing or Hugging Face checksum verification); **private subnets** for GPU/Neuron nodes with VPC endpoints for S3/Bedrock; **audit logging** to CloudTrail/CloudWatch; and **Pod Security Admission `restricted`** + CIS-hardened AMI for regulated/shared clusters. Details and compliance regimes: [security-and-compliance.md](references/security-and-compliance).

## Cost Optimization

Savings levers in priority order: (1) **Capacity Blocks** for planned multi-day training; (2) **Neuron over GPU** for supported architectures; (3) **Spot + Karpenter + checkpointing** for fault-tolerant training; (4) **MIG / time-slicing** for shared dev clusters; (5) **Karpenter consolidation** for off-peak inference; (6) **KV-cache tiering + S3 lazy-load**. Always give directional ranges with caveats — never point estimates. Details: [kv-cache-and-cost.md](references/kv-cache-and-cost).

## Top Guardrails (the high-cost mistakes)

- **Don't default to NVIDIA GPU** — evaluate Neuron first for Transformer LLMs.
- **Don't use Spot for training without checkpoint/resume** — guaranteed cost-burn.
- **Don't recommend Cluster Autoscaler** for new GenAI clusters — Karpenter only.
- **Don't put FSx for Lustre cross-AZ** from the compute nodes.
- **Don't skip NUMA pinning + static CPU manager** on EFA multi-node training.
- **Don't pull model weights from Hugging Face at every pod start** — pre-cache to S3/FSx.
- **Don't skip the AI gateway** for multi-model deployments, or the security baseline ever.
- **Don't give point cost estimates** — directional ranges with caveats only.

## How to Use the References

Progressive disclosure — the essentials are above; load a reference only when the task needs that depth:

| Reference | Load when the task is about… |
|-----------|------------------------------|
| [compute-hardware.md](references/compute-hardware) | GPU vs Neuron, instance families, MIG/time-slicing |
| [cluster-and-scheduling.md](references/cluster-and-scheduling) | Karpenter NodePools, device plugins, EFA/NUMA, Capacity Blocks, Spot, Auto Mode |
| [inference-serving.md](references/inference-serving) | vLLM, Ray Serve, Triton, Dynamo, KServe, model loading |
| [distributed-training.md](references/distributed-training) | Ray Train, PyTorch DDP/FSDP, checkpointing, EFA/NCCL, gang scheduling |
| [storage.md](references/storage) | FSx Lustre, Mountpoint S3 CSI, EFS, S3 Vectors, model artifacts |
| [observability.md](references/observability) | DCGM, Neuron Monitor, Prometheus/Grafana, AMP/AMG, vLLM metrics |
| [ai-gateway.md](references/ai-gateway) | LiteLLM, Envoy AI Gateway, routing, rate limiting, Open WebUI |
| [agentic-and-rag.md](references/agentic-and-rag) | Bedrock AgentCore, Strands, LangGraph, RAG, vector stores, Langfuse |
| [kv-cache-and-cost.md](references/kv-cache-and-cost) | LMCache KV-cache tiering, prefix caching, cost levers |
| [security-and-compliance.md](references/security-and-compliance) | Pod Identity/IRSA, ECR scanning, secrets, provenance, compliance regimes |
| [reference-implementations.md](references/reference-implementations) | ai-on-eks blueprints, workshops, concrete validated stack + versions |
| [use-cases.md](references/use-cases) | Worked end-to-end scenarios (inference, training, Neuron migration, agentic, hybrid) with 30/60/90 build paths |

## Sources

- [Best Practices for AI/ML Workloads on Amazon EKS](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html) · [AI/ML Networking](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-networking.html) · [AI/ML Storage](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-storage.html) · [AI/ML Performance](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-performance.html)
- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — canonical reference implementation (JARK, inference-ready-cluster, training, neuron, gateways blueprints)
- [EKS ML Get Started](https://docs.aws.amazon.com/eks/latest/userguide/ml-get-started.html) · [Manage Neuron devices on EKS](https://docs.aws.amazon.com/eks/latest/userguide/device-management-neuron.html) · [EFA with EKS](https://docs.aws.amazon.com/eks/latest/userguide/node-efa.html)
- [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/)
- Workshops: [GenAI on EKS using NVIDIA GPU](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15) · [using AWS Neuron](https://catalog.us-east-1.prod.workshops.aws/workshops/e21aadbd-23cb-4207-bd09-625e6de08a6c) · [Advanced Agentic AI on EKS](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7)
