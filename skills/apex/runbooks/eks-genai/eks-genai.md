---
name: eks-genai
description: Day 1 GenAI-on-EKS workflow. Guides building, training, fine-tuning, and serving generative AI / LLM workloads on Amazon EKS through the opinionated 6-layer stack — hardware (GPU vs Neuron), Karpenter scheduling, vLLM/Ray serving, distributed training, ML storage, GPU/Neuron observability, and the LiteLLM AI gateway — with a non-negotiable security baseline and cost levers.
---

# GenAI on EKS Workflow

> **Lifecycle:** Day 1 — Build
> **Skill:** eks-genai | compute-hardware.md, inference-serving.md
> **Access Model:** advisory

This workflow guides a team through architecting and building a generative AI / LLM workload on Amazon EKS. It produces an opinionated, layer-by-layer stack recommendation and a build path; it does not read or mutate a live cluster. All domain knowledge comes from the `eks-genai` skill (the 6-layer stack, the GPU-vs-Neuron decision, the JARK + vLLM + LiteLLM canonical reference); this workflow supplies the engagement structure.

## How to Route Requests

| User intent | Mode / Phase |
|---|---|
| "Build / serve a GenAI workload on EKS" / "self-host an LLM" | Full → Phase 1 → 2 → 3 → 4 |
| "GPU or Neuron (Trainium/Inferentia) for my model?" | Scoped → Phase 1 (abbreviated) → 2 |
| "Set up vLLM / Ray Serve" or "distributed training on EKS" | Scoped → Phase 1 (abbreviated) → 3 |
| "Migrate my GPU inference to Inferentia for cost" | Scoped → Phase 2 → 3 (cost lens) |
| "Wire GPU observability / an AI gateway / RAG / agentic on EKS" | Scoped → Phase 3 (the relevant layer) |
| "What does a production GenAI-on-EKS stack look like?" | Summary → Phase 1 → 2 → 3 condensed |

If the request is a single GenAI-on-EKS concept question rather than a build engagement, answer directly from the `eks-genai` skill and skip the phases.

## Phases

### Phase 1: Workload scoping

Source: knowledge

The single most-common mistake is recommending a stack before knowing the workload. Get crisp answers before touching any layer — a fuzzy scope produces a stack nobody asked for.

Required inputs — ask for these in one turn:

- **Workload type** — training / fine-tuning / inference serving / agentic / RAG / mixed.
- **Model family and size** — small (<7B), mid (7B-30B), large (30B-70B), frontier (70B+), embedding, or multi-modal.
- **Latency target** (if inference) — sub-100ms TTFT (interactive), 100-500ms, >500ms acceptable, or throughput-only/batch.
- **Cost posture** — cost-first / balanced / stability-first / TCO-driven.
- **Hardware preference or constraint** — NVIDIA GPU required (CUDA-only/novel arch), Neuron acceptable (PyTorch/vLLM), or no preference.
- **Compliance regime** — none/commercial, or HIPAA/PCI-DSS/FedRAMP/GDPR/other.

If the user already has an `eks-recon` report, an architecture doc, or a prior design, read it first and skip answered questions.

**STOP.** Restate the workload type, model size, latency target, cost posture, and hardware constraint. Confirm before recommending hardware. If the ask is SageMaker-only or Bedrock-only with no self-hosting, say so and redirect rather than forcing an EKS stack.

### Phase 2: Compute and cluster selection (Layers 1-2)

Source: knowledge

Frame the two foundational layers. Load `../../../eks-genai/references/compute-hardware.md` for the GPU-vs-Neuron decision and `cluster-and-scheduling.md` for the scheduler.

- **Hardware (Layer 1).** Default to **Neuron** (Trn2/Trn1 training, Inf2 inference) for Transformer-family models when cost-conscious and the team can absorb the compilation ramp; default to **NVIDIA GPU** (g6/g6e inference, p5 training) for fastest time-to-value, CUDA-only dependencies, or novel/multi-modal architectures. Present the trade-off, do not pick reflexively.
- **Cluster (Layer 2).** Karpenter (only recommended autoscaler) with separate GPU + Neuron NodePools; EKS-optimized accelerated AMI; Neuron device plugin (not the DRA driver) with Karpenter; EFA + NUMA pinning + static CPU manager for multi-node training; Capacity Blocks for planned training; Spot only with checkpoint/resume.

**STOP.** Confirm the accelerator choice and scheduling approach. Flag any conflict with a Phase 1 constraint (e.g., compliance requiring a CIS-hardened AMI rules out EKS Auto Mode).

### Phase 3: Serving / training, storage, observability, gateway (Layers 3-6)

Source: knowledge

Assemble the upper layers for the confirmed workload. Load the matching references: `inference-serving.md` and/or `distributed-training.md` (Layer 3), `storage.md` (Layer 4), `observability.md` (Layer 5), and `ai-gateway.md` plus `agentic-and-rag.md` (Layer 6). For optimization-led asks, also load `kv-cache-and-cost.md`.

Default to the JARK + **vLLM** + **LiteLLM** canonical stack: vLLM (optionally with Ray Serve) for serving; Ray Train or PyTorch FSDP for training; Mountpoint S3 CSI for inference weights and FSx for Lustre (same-AZ, S3 DRA checkpointing) for training; DCGM/Neuron Monitor → Prometheus → Grafana (+ AMP/AMG in production); LiteLLM gateway for multi-model (self-hosted + Bedrock). Present each layer's choice with its trade-off, not a generic matrix.

**STOP.** Confirm the per-layer choices before moving to the security baseline and build path.

### Phase 4: Security baseline, cost, and build path

Source: knowledge

Apply the non-negotiable security baseline and turn the decisions into a sequenced plan. Load `security-and-compliance.md`, `kv-cache-and-cost.md`, and `reference-implementations.md`.

- **Security baseline (always).** EKS Pod Identity / IRSA (never static keys), ECR image scanning, secrets via Secrets Manager + Secrets Store CSI, model artifact provenance, private subnets + VPC endpoints, audit logging, and PSA `restricted` + CIS-hardened AMI for regulated/shared clusters.
- **Cost levers.** Capacity Blocks, Neuron-over-GPU, Spot+checkpoint, MIG/time-slicing, Karpenter consolidation, KV-cache tiering — directional ranges with caveats, never point estimates.
- **Build path.** Point at the matching `awslabs/ai-on-eks` blueprint, then a 30/60/90 sequence (deploy a small reference model end-to-end → validate observability → wire the gateway → instrument cost → production cutover). Run the Quality Checklist before presenting.

**STOP.** Present the stack, the security baseline, and the build path. Wait for the user's reaction before chaining into a design or build follow-up. Escalate (SpecReq) for regulated mission-critical workloads, frontier-scale training (>32 accelerator nodes), or strict multi-tenant cross-tenant isolation.

## Defaults

| Default | Value | Override when |
|---|---|---|
| Hardware (inference) | NVIDIA GPU (g6/g6e) for time-to-value; Neuron/Inf2 as cost phase-2 | Cost-first + Transformer model → lead with Neuron |
| Hardware (training) | AWS Neuron (Trn2/Trn1) for Transformer; p5 (H100) fallback | Novel/non-Transformer or CUDA-only → GPU |
| Autoscaler | Karpenter with separate GPU + Neuron NodePools | Never Cluster Autoscaler for new GenAI clusters |
| Serving engine | vLLM (+ Ray Serve for autoscaling) | Multi-framework/TensorRT → Triton; scale-to-zero → KServe |
| Training framework | Ray Train or PyTorch FSDP | Full MLOps pipeline governance → Kubeflow |
| Storage | Mountpoint S3 CSI (inference) + FSx for Lustre (training) | Shared multi-model weights → EFS; RAG vectors → S3 Vectors |
| Observability | DCGM / Neuron Monitor → Prometheus → Grafana (+ AMP/AMG prod) | — |
| Gateway | LiteLLM (multi-model self-hosted + Bedrock) | L7 routing at ingress → Envoy AI Gateway |
| Spot (training) | Acceptable only with checkpoint/resume | Interruption-intolerant → On-Demand + Capacity Blocks |
| Cost estimates | Directional ranges with caveats | Never point estimates |

## Quality Checklist

Self-grade before presenting. Each item is binary — passes or fails.

- [ ] Phase 1 required inputs (workload type, model size, latency, cost posture, hardware constraint, compliance) are all answered before any hardware recommendation.
- [ ] The hardware recommendation evaluated Neuron explicitly — it did not default to NVIDIA GPU reflexively.
- [ ] Every layer in scope cites its trade-off and the condition that would justify the alternative, not just the default.
- [ ] The security baseline is present in full (Pod Identity, ECR scanning, secrets, provenance, private networking, audit) — never omitted.
- [ ] Cost guidance is directional with caveats — no point estimates.
- [ ] The build path names a concrete `awslabs/ai-on-eks` blueprint and a sequenced 30/60/90 plan, and flags any escalation trigger.

Pass threshold: 5/6. Below 4/6 means rework — most often the hardware choice skipped Neuron or the security baseline was dropped.

## Conversation Style

- Be concise. Group Phase 1's questions into one turn, not six.
- If given an `eks-recon` report or an architecture doc, read it first and only ask what is missing.
- Explain routing when activating a mode — say which layers you are scoping to and why.
- Recommend, don't enumerate. Name the default and the trade-off; reach for the full matrix in the skill only when the user pushes back.
- When a STOP gate fires, name the one decision you need before proceeding.
