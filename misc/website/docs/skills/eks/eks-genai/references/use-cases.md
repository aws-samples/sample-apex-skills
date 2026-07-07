---
title: "Worked Use Cases — GenAI on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/use-cases.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/use-cases.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/use-cases.md). Edit the source, not this page.
:::

# Worked Use Cases — GenAI on EKS

Five condensed scenarios from the playbook. Each gives: customer profile, per-layer recommendation, and 30/60/90 build path.

---

## Use Case 1 — Greenfield 7B-30B LLM Inference

**Profile:** Mid-to-large enterprise with EKS for non-AI workloads. ML team wants to self-host an open-source LLM (Llama 3 / Mistral / Qwen) for product features. Latency: 100-500 ms TTFT. Cost: balanced. No hardware preference.

**Per-Layer Recommendation:**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| 1 — Compute | **g6e.2xlarge** (L40S) for 7B-13B; g6e.12xlarge for 30B | Fastest time-to-first-success; Neuron as phase-2 cost optimization |
| 2 — Cluster | Karpenter + NVIDIA device plugin + Bottlerocket accelerated AMI | Auto Mode compatible; driver pre-installed |
| 3 — Framework | **vLLM** (AWS DLC) + **Ray Serve** (KubeRay 1.1.0) | OpenAI-compatible API; auto-scaling built-in |
| 4 — Storage | **Mountpoint S3 CSI** + Run:ai Streamer | Lazy-load weights from S3; per-pod cache |
| 5 — Observability | DCGM Exporter + kube-prometheus-stack + AMP | Pre-built ai-on-eks Grafana dashboards |
| 6 — Gateway | **LiteLLM** + Langfuse | Multi-model routing; per-tenant cost tracking |

**30/60/90 Build Path:**

- **Days 1-30:** Deploy `infra/inference-ready-cluster` blueprint. Validate model on g6e with vLLM. Confirm DCGM dashboards show GPU utilization + TTFT metrics.
- **Days 31-60:** Wire LiteLLM gateway. Integrate with customer application. Add Langfuse tracing. Validate per-tenant cost attribution.
- **Days 61-90:** Production cutover with rollback plan. Run cost comparison: g6e vs inf2 for the validated model. Execute Neuron migration if savings justify the compilation ramp.

**Escalate when:** Compliance-regulated workload (HIPAA/PCI/FedRAMP) — Specialist + compliance review required before production.

**Why not SageMaker/Bedrock:** If the customer has EKS skills + wants Kubernetes flexibility + needs custom routing/gateway, EKS wins. SageMaker wins if no K8s skills and wants fully-managed. Bedrock wins if zero-infrastructure managed FMs are acceptable (no self-hosting, no fine-tune control).

---

## Use Case 2 — 30B-70B+ Distributed Training / Fine-Tuning

**Profile:** Research lab or product team training a 30B-70B+ model (pre-training or full fine-tune). Distributed across 8-64+ accelerators. Cost-first. PyTorch + Hugging Face stack.

**Per-Layer Recommendation:**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| 1 — Compute | **trn2.48xlarge** (16× Trainium2) default; p5.48xlarge fallback for CUDA-only | Up to 50% cost-to-train savings for Transformer models |
| 2 — Cluster | Karpenter + Neuron device plugin + EFA device plugin + NUMA pinning + static CPU manager | EFA bandwidth halves without NUMA; use Capacity Blocks for guaranteed p5 |
| 3 — Framework | **Ray Train** + KubeRay (or PyTorch FSDP direct) | ai-on-eks `infra/training` blueprint; gang scheduling via Volcano/Kueue |
| 4 — Storage | **FSx for Lustre (Persistent-SSD)** same-AZ + S3 DRA for checkpoint offload | Sub-ms latency; async durable checkpoint to S3 every 15-30 min |
| 5 — Observability | Neuron Monitor (or DCGM) + Prometheus + Grafana | Per-step GPU/Neuron util, EFA throughput, NCCL all-reduce latency |
| 6 — Gateway | N/A (training-only) | Model handoff via MLflow registry or Bedrock model import |

**30/60/90 Build Path:**

- **Days 1-30:** Deploy `infra/training` blueprint. Provision Neuron (or GPU) NodePool + FSx for Lustre in same AZ. Run single-node training to validate Neuron compilation (or CUDA setup). Wire checkpoint-to-S3 loop.
- **Days 31-60:** Scale to multi-node (8-16 accelerators). Validate EFA throughput (>90% theoretical). Run full training job with Spot + checkpoint/resume. Monitor cost vs On-Demand baseline.
- **Days 61-90:** Production training pipeline with Argo Workflows. Automate: data prep → train → eval → register. Capacity Blocks reservation for next planned training run.

**Escalate when:** >32 accelerator nodes per job — ML TFC joint review. Novel architecture not in Neuron supported list — GPU-only with Specialist review.

**Spot strategy for training:** Spot is acceptable ONLY with checkpoint-resume wired into the training loop. Pattern: checkpoint every 15-30 min to FSx → async DRA offload to S3 → on Spot interruption, Karpenter provisions replacement → resume from latest checkpoint. Without this loop, Spot is a guaranteed cost-burn. For planned multi-day runs, use **Capacity Blocks for ML** (substantially below on-demand pricing for reserved GPU/Neuron).

---

## Use Case 3 — Cost-Optimized Inference via Neuron Migration

**Profile:** Production GenAI on EKS using g5/g6 GPUs. Steady-state high-volume traffic. Cost-first. Considering Inf2 migration for 40%+ savings. Models: Llama/Mistral/Qwen (Transformer family). Existing vLLM stack.

**Per-Layer Recommendation:**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| 1 — Compute | **inf2.48xlarge** (production); inf2.8xlarge (compilation/dev) | 40% better price-performance vs comparable GPU |
| 2 — Cluster | Add Neuron NodePool alongside existing GPU NodePool; Neuron device plugin | Canary cutover — both pools active during migration |
| 3 — Framework | **vLLM + `neuronx-distributed-inference`** backend | Same OpenAI-compatible API; Neuron-native tensor parallelism |
| 4 — Storage | Same Mountpoint S3 CSI | Pre-compile model for Neuron offline; ship compiled artifacts via S3 |
| 5 — Observability | Add **Neuron Monitor** alongside DCGM | Side-by-side GPU vs Neuron metrics during canary |
| 6 — Gateway | **LiteLLM weighted routing** — 95% GPU / 5% Neuron → gradual shift | Zero application change; same API |

**30/60/90 Build Path:**

- **Days 1-30:** Compile model for Neuron (`neuronx-distributed-inference` requires 1-2 week ramp for first model). Deploy Neuron NodePool + Neuron vLLM Deployment. Run validation set — compare output distributions GPU vs Neuron.
- **Days 31-60:** Canary cutover via LiteLLM: 5% → 25% → 50% → 100% over 2 weeks. Monitor latency, error rate, cost at each step.
- **Days 61-90:** Decommission GPU NodePool. Finalize cost-savings report. Document compilation pipeline for next model version release.

**Escalate when:** >5 model variants in parallel migration — architecture review warranted. Model architecture not in Neuron supported list — verify before committing.

**Risk callouts:** (1) Neuron compilation adds 1-2 weeks to new model version deployments — factor into release cadence. (2) Some Neuron metrics lack CloudWatch integration out-of-box — verify Neuron Monitor + Container Insights coverage. (3) Not all HF models have Neuron support — verify architecture against [Neuron supported models](https://aws.amazon.com/ai/machine-learning/neuron/) before committing budget. (4) Output quality parity is not guaranteed — always run an eval suite comparing GPU vs Neuron outputs before shifting traffic.

---

## Use Case 4 — Agentic AI Multi-Tool Platform

**Profile:** Customer building agentic AI — multi-step LLM-driven processes calling tools, knowledge bases, and other models. Mix of self-hosted (cost-sensitive long-context) + Bedrock managed (best-of-breed). Needs multi-tenant rate limiting, per-agent cost attribution, audit trail.

**Per-Layer Recommendation:**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| 1 — Compute | Self-hosted on inf2 or g6e (model-dependent); Bedrock for Claude/Nova (no self-hosting needed) | Agent orchestration is CPU-only; model serving on accelerator NodePool |
| 2 — Cluster | CPU NodePool (agents) + GPU/Neuron NodePool (models) | Don't waste accelerator capacity on reasoning loop |
| 3 — Framework | **Strands Agents SDK** + **LangGraph** for self-hosted; **Bedrock AgentCore** for managed | Workshop-validated; full tool-dispatch control |
| 4 — Storage | S3 for agent state/logs; DynamoDB for low-latency session state | TTL via Lifecycle policies |
| 5 — Observability | **Langfuse** — every agent step traced (LLM call, tool call, retrieval) with cost + latency | Critical for debugging agent quality |
| 6 — Gateway | **LiteLLM** — per-agent/per-tenant keys; routes self-hosted + Bedrock; OpenAI-compatible | Token cost attribution per agent built-in |

**30/60/90 Build Path:**

- **Days 1-30:** Deploy inference-ready-cluster + LiteLLM + Langfuse. Self-host Qwen 3 8B for high-volume classification. Configure LiteLLM to route to Bedrock Claude for reasoning. Deploy first Strands agent with 2-3 tools.
- **Days 31-60:** Add multi-tenant isolation — per-tenant LiteLLM keys, namespace-level resource quotas. Validate Langfuse cost rollup per agent per tenant. Wire audit export to S3.
- **Days 61-90:** Scale to 5+ agent types. Add graceful fallback (self-hosted → Bedrock on saturation). Production hardening — max_steps limits, circuit breakers on tool calls, prompt injection guardrails.

**Escalate when:** Agents with autonomous code execution — Security TFC review. Cross-tenant data leakage risk — isolation architecture review.

---

## Use Case 5 — Hybrid Trainium Training + GPU Inference

**Profile:** Team doing both training/fine-tuning AND inference of same model family. Cost-optimization across full lifecycle. PyTorch + Hugging Face. Production traffic via OpenAI-compatible API.

**Per-Layer Recommendation:**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| 1 — Compute | **trn1/trn2 NodePool** (training) + **g6e or inf2 NodePool** (inference) | Lowest cost per stage; same EKS cluster |
| 2 — Cluster | Single cluster, **3 NodePools** — CPU (orchestration), Neuron-Training, GPU/Neuron-Inference | Karpenter routes by workload selector |
| 3 — Framework | **Ray Train** (training) + **vLLM** (inference) + **Argo Workflows** (pipeline) | Train → eval → register → deploy automated |
| 4 — Storage | **FSx for Lustre** (training data + checkpoints) + **Mountpoint S3 CSI** (inference weights) | Trained model artifact is the handoff between stages |
| 5 — Observability | DCGM (GPU inference) + Neuron Monitor (Trainium training) + per-workload cost attribution (Kubecost/SCAD) | Separate dashboards per workload type |
| 6 — Gateway | **LiteLLM** for inference endpoint | Training is internal — not gateway-fronted |

**30/60/90 Build Path:**

- **Days 1-30:** Deploy `infra/jark-stack/terraform` (full JARK). Provision Trainium NodePool for training + GPU NodePool for inference. Run LoRA fine-tune of 7B model on Trn1. Validate checkpoint pipeline (FSx → S3).
- **Days 31-60:** Build Argo Workflow: data prep → fine-tune (Trn1) → eval → register (MLflow) → deploy to vLLM (GPU). Validate end-to-end latency from training completion to production serving.
- **Days 61-90:** Operationalize — scheduled retraining cadence, automated model promotion with quality gates, cost reporting per stage (training $/run vs inference $/1K tokens).

**Escalate when:** Multi-model + multi-tenant + multi-region — cross-AZ cost optimization review. >32 Trainium nodes per job — capacity planning with ML TFC.

**Model handoff pattern:** The trained model artifact (weights in SafeTensors format) is written to S3 by the training pipeline. The inference pipeline reads from the same S3 path via Mountpoint S3 CSI. Model promotion uses a version tag in the S3 key path (e.g., `s3://models/llama-7b-ft/v3/`) — Argo Workflows updates the vLLM Deployment to point at the new version, then Ray Serve does a rolling update with zero-downtime.

---

## Pattern Summary

| Scenario | Primary cost lever | Time to production | Key risk |
|----------|-------------------|-------------------|----------|
| Greenfield 7B-30B inference | Neuron phase-2 migration | 30-60 days | GPU lock-in if Neuron not planned |
| 30B-70B+ training | Trainium + Capacity Blocks | 60-90 days | Spot without checkpoint = cost-burn |
| Neuron inference migration | 40%+ savings over GPU | 45-60 days | Compilation ramp + output quality parity |
| Agentic AI platform | Per-agent cost visibility via LiteLLM | 60-90 days | Runaway tool loops; cross-tenant leakage |
| Hybrid training + inference | Different hardware per stage | 60-90 days | Model artifact handoff complexity |

---

## Sources

- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — all blueprints referenced above
- [GenAI on EKS using NVIDIA GPU Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15)
- [GenAI on EKS using AWS Neuron Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/e21aadbd-23cb-4207-bd09-625e6de08a6c)
- [Advanced Agentic AI on EKS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7)
- [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/)
