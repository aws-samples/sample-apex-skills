---
title: "Reference Implementations — Blueprints, Workshops & Validated Stacks"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/reference-implementations.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/reference-implementations.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/reference-implementations.md). Edit the source, not this page.
:::

# Reference Implementations — Blueprints, Workshops & Validated Stacks

Canonical `awslabs/ai-on-eks` blueprint catalog, current workshops, AWS Solutions Library guidance, and a concrete validated stack with pinned versions from the GenAI-on-EKS NVIDIA workshop.

---

## awslabs/ai-on-eks Blueprint Catalog

The [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) repository is the **TFC-endorsed** canonical reference implementation (Containers TFC + Machine Learning TFC). Point customers here as the fastest credible path from idea to production.

> **Verify paths before quoting them to a customer.** `awslabs/ai-on-eks` reorganizes its directory layout periodically; the paths below were confirmed against the repo's `main` in June 2026. Always `git clone` and confirm the current tree (or browse the repo) before scripting against a path — treat these as a current map, not a permanent contract.

### Infrastructure Blueprints (`infra/`)

Each infra blueprint is a Terraform root under `infra/<name>/terraform`.

| Blueprint path | What it provisions | Use when |
|---------------|-------------------|----------|
| `infra/jark-stack/terraform` | Full JARK dev environment — JupyterHub + Argo + Ray + Karpenter + GPU/Neuron NodePools | Greenfield; team needs experimentation + training + inference on one cluster |
| `infra/base/terraform` | Base EKS cluster — Karpenter, core add-ons, GPU/Neuron NodePools (the foundation the workload blueprints deploy onto) | Inference- or general-purpose cluster; layer a workload blueprint on top |
| `infra/trainium-inferentia/terraform` | Neuron-optimized cluster — Inf2/Trn1/Trn2 NodePools, Neuron device plugin | Neuron-first / cost-optimized training or inference |
| `infra/nvidia-dynamo`, `infra/aibrix`, `infra/nvidia-triton-server` | Serving-stack-specific infra (Dynamo disaggregated, AIBrix, Triton) | When standardizing on that specific serving stack |

### Inference Blueprints (`blueprints/inference/`)

| Blueprint path | Stack | Use when |
|---------------|-------|----------|
| `blueprints/inference/vllm-rayserve-gpu` | vLLM + Ray Serve on NVIDIA GPU | Default LLM inference (Mistral/Llama/Qwen on g6/g6e) |
| `blueprints/inference/neuron/ray-vllm` | vLLM + Ray Serve on Neuron (Inf2/Trn1) | Neuron cost-optimized inference |
| `blueprints/inference/vllm-nvidia-triton-server-gpu` | vLLM behind NVIDIA Triton Server | Multi-model / Triton-fronted serving |
| `blueprints/inference/inference-charts` | Helm charts for quick model deploy (Llama/Mistral/Qwen, GPU + Inf2 variants) | Fastest "deploy a model" path |

(Plus model-specific examples — e.g. `mistral-7b-rayserve-inf2`, `llama3-8b-instruct-rayserve-inf2`, `vllm-llama3.1-405b-trn1` — browse `blueprints/inference/` for the current list.)

### Gateway & Agentic Blueprints

| Blueprint path | Stack | Use when |
|---------------|-------|----------|
| `blueprints/gateways/envoy-ai-gateway` | Envoy AI Gateway — header-based routing + rate limiting | L7 multi-model routing at ingress |
| `blueprints/agent-sandbox` | Sandboxed agent execution environment | Agentic AI reference / isolated agent tool execution |

### Training Blueprints (`blueprints/training/`)

| Blueprint path | Stack | Use when |
|---------------|-------|----------|
| `blueprints/training/raytrain-llama2-pretrain-trn1` | Ray Train pre-training on Trainium | Multi-node distributed pre-training on Neuron |
| `blueprints/training/llama-lora-finetuning-trn1` | LoRA fine-tuning on Trainium | Parameter-efficient fine-tuning on Neuron |
| `blueprints/training/slinky-slurm` | Slurm-on-Kubernetes (Slinky) | Teams that want a Slurm scheduler interface for training |

### How to Use the Blueprints

1. **Clone the repo:** `git clone https://github.com/awslabs/ai-on-eks.git`
2. **Pick an infra blueprint** (`infra/base`, `infra/jark-stack`, or `infra/trainium-inferentia`) matching your workload.
3. **Deploy with Terraform:** `cd infra/<blueprint>/terraform && terraform init && terraform apply` (or use the blueprint's `install.sh`).
4. **Layer an inference/training blueprint** on top for the specific model/framework.
5. **Add gateway + observability** (LiteLLM, Langfuse, kube-prometheus-stack) from the workshop patterns.

The infra blueprints provision the cluster, NodePools, add-ons, and IAM. The workload blueprints (inference/training/gateway) deploy into the running cluster. This separation lets teams upgrade independently.

### Use-Case → Blueprint Mapping

| Customer use case | Start with blueprint | Then add |
|-------------------|---------------------|----------|
| Greenfield 7B-30B LLM inference | `infra/base/terraform` | `blueprints/inference/vllm-rayserve-gpu` + LiteLLM |
| Cost-optimized inference (Neuron) | `infra/trainium-inferentia/terraform` | `blueprints/inference/neuron/ray-vllm` |
| Distributed training / fine-tuning | `infra/trainium-inferentia/terraform` | `blueprints/training/raytrain-llama2-pretrain-trn1` or `llama-lora-finetuning-trn1` |
| Full dev + train + serve lifecycle | `infra/jark-stack/terraform` | All of the above layered on |
| Agentic AI multi-model platform | `infra/base/terraform` | `blueprints/gateways/envoy-ai-gateway` + `blueprints/agent-sandbox` + LiteLLM + Langfuse |
| Hybrid Trainium training + GPU inference | `infra/jark-stack/terraform` | Neuron NodePool (training) + GPU NodePool (inference) via Karpenter |

---

## Concrete Validated Stack — GenAI-on-EKS NVIDIA Workshop

These are the **pinned, tested versions** from the current [Generative AI on EKS using NVIDIA GPU](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15) workshop, running on EKS Auto Mode. Use these as the credible "this works today" reference.

| Component | Version / Detail |
|-----------|-----------------|
| **EKS** | Auto Mode, Kubernetes **1.34** |
| **Terraform EKS module** | `terraform-aws-modules/eks` **v21.15.1** |
| **Terraform VPC module** | `terraform-aws-modules/vpc` **v6.6.0** |
| **Infra source** | `awslabs/ai-on-eks` → `infra/workshops/genai-on-eks` |
| **GPU instance** | **g6e.2xlarge** (NVIDIA L40S) |
| **Model** | **Ministral-3-8B-Instruct-2512** |
| **Inference engine** | **vLLM** (AWS Deep Learning Container) |
| **Model loading** | **Run:ai Streamer** from S3 (`RUNAI_STREAMER_S3_*` env vars) |
| **Serving framework** | **Ray Serve** via **KubeRay operator 1.1.0** |
| **Storage** | **Mountpoint for S3 CSI** (`s3.csi.aws.com`) |
| **RAG vector store** | **Amazon S3 Vectors** |
| **Observability — metrics** | **kube-prometheus-stack 69.7.4** + **grafana-operator 5.16.0** |
| **Observability — GPU** | **NVIDIA DCGM Exporter** |
| **Observability — managed** | **Amazon Managed Prometheus** (AMP) |
| **Agents** | **Strands Agents SDK** |
| **KV cache** | **LMCache** — L1 CPU + L2 ElastiCache Serverless (Valkey) |
| **Chat UI** | **Open WebUI** |
| **Auth** | **EKS Pod Identity** (`pods.eks.amazonaws.com`) |

### Agentic Workshop Stack

The [Advanced Agentic AI Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7) adds:

| Component | Implementation |
|-----------|---------------|
| AI gateway | **LiteLLM** |
| Agent framework | **LangGraph** + **Strands Agents SDK** |
| Tracing | **Langfuse** (self-hosted on EKS) |
| Self-hosted model | **Qwen 3 8B** via vLLM |
| Managed model | **Claude** on Amazon Bedrock |

---

## Current Workshops (TFC-Endorsed)

| Workshop | Focus | URL |
|----------|-------|-----|
| **Generative AI on EKS using NVIDIA GPU** | vLLM, Ray Serve, Ministral-8B, g6e, DCGM, Prometheus/Grafana, LMCache, Strands, S3 Vectors | [Workshop link](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15) |
| **Generative AI on EKS using AWS Neuron** | vLLM + neuronx-distributed-inference, Inf2/Trn1, Ray Serve, Neuron Monitor, CloudWatch | [Workshop link](https://catalog.us-east-1.prod.workshops.aws/workshops/e21aadbd-23cb-4207-bd09-625e6de08a6c) |
| **Architect and Deploy Advanced Agentic AI on EKS** | LiteLLM gateway, LangGraph agents, Langfuse tracing, Qwen 3 8B + Claude on Bedrock | [Workshop link](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7) |

> **Deprecated workshop:** "Generative AI with Data on EKS" — do NOT recommend. Direct customers to the three workshops above.

---

## AWS Solutions Library Guidance

| Guidance | What it covers | URL |
|----------|---------------|-----|
| **Scalable Model Inference and Agentic AI on Amazon EKS** | Enterprise architecture — Karpenter + GPU/Graviton/Inferentia + LLM gateway + MCP server + agentic AI | [Link](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/) |
| **Automated Deployment of Inference-ready Amazon EKS Clusters** | Pre-configured Terraform for production inference — Karpenter + FluentBit + Prometheus/Grafana | [Link](https://aws.amazon.com/solutions/guidance/automated-deployment-of-inference-ready-amazon-eks-clusters/) |
| **Low Latency, High Throughput Inference using Efficient Compute on Amazon EKS** | Multi-model PyTorch inference with mixed instance families (Graviton + Inferentia) | [Link](https://aws.amazon.com/solutions/guidance/low-latency-high-throughput-inference-using-efficient-compute-on-amazon-eks/) |

---

## Deployment Architecture — Workshop Stack

The NVIDIA workshop deploys the following architecture on EKS Auto Mode:

```text
┌─────────────────────────────────────────────────────────────────┐
│ EKS Auto Mode (K8s 1.34) — g6e.2xlarge NodePool                │
├─────────────────────────────────────────────────────────────────┤
│ vLLM (DLC) + Run:ai Streamer          Ray Serve (KubeRay 1.1.0)│
│     ↑ model weights from S3                ↑ auto-scales pods   │
├─────────────────────────────────────────────────────────────────┤
│ LMCache (L1 CPU → L2 ElastiCache Valkey)   S3 Vectors (RAG)    │
├─────────────────────────────────────────────────────────────────┤
│ Strands Agents SDK          Open WebUI          LiteLLM*        │
├─────────────────────────────────────────────────────────────────┤
│ kube-prometheus-stack 69.7.4 + DCGM Exporter → AMP             │
│ grafana-operator 5.16.0 → Amazon Managed Grafana               │
└─────────────────────────────────────────────────────────────────┘
 * LiteLLM shown in Agentic workshop; NVIDIA workshop uses direct vLLM API
```

Key architectural decisions validated by the workshop:
- **Run:ai Streamer** streams model weights from S3 on-demand — eliminates cold-start delay vs full download.
- **LMCache L1+L2** provides prefix-cache reuse across pods — reduces redundant KV computation for common system prompts.
- **S3 Vectors** replaces heavier vector DBs for RAG — serverless, no provisioned capacity.
- **EKS Pod Identity** for all AWS API access — no static credentials anywhere.
- **Mountpoint S3 CSI** for persistent volume claims — model weights and RAG data via S3 without EBS.

## Version Currency Notes

- Versions above are validated as of **June 2026**. Before recommending to a customer, verify the `awslabs/ai-on-eks` repo's `main` branch for any updates — Terraform module versions and Helm chart versions move quarterly.
- **Kubernetes version — pinned ≠ latest.** The table pins **K8s 1.34** because that is what the workshop was validated on (1.34 reached EKS in Oct 2025 and remains in standard support). It is **not the newest** — EKS added **1.36** on June 2, 2026. For a *new* cluster, default to the latest EKS-supported version after confirming the accelerator add-ons (NVIDIA/Neuron device plugins, Karpenter, KubeRay) support it; treat the pinned 1.34 as "known-good for this workshop," not "the version to deploy today." Current standard-support list: [EKS Kubernetes version lifecycle](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html).
- **Amazon S3 Vectors is GA** (general availability since Dec 2, 2025) — safe as a production default for cost-efficient RAG; see the latency profile in [storage.md](storage) before using it for low-latency, high-concurrency retrieval.
- The workshop infra lives under `infra/workshops/genai-on-eks` in the repo — separate from the production blueprints under `infra/`.
- KubeRay operator, kube-prometheus-stack, and grafana-operator versions are pinned in the workshop's Terraform; production deployments should track these or newer patch versions.

---

## Sources

- [`awslabs/ai-on-eks`](https://github.com/awslabs/ai-on-eks) — canonical reference implementation
- [GenAI on EKS using NVIDIA GPU Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/029d6c4e-4775-41c9-85ff-9f5360f32a15)
- [GenAI on EKS using AWS Neuron Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/e21aadbd-23cb-4207-bd09-625e6de08a6c)
- [Advanced Agentic AI on EKS Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/26ab2b07-9621-4e0c-bc44-3f7fef388cb7)
- [Guidance for Scalable Model Inference and Agentic AI on Amazon EKS](https://aws.amazon.com/solutions/guidance/scalable-model-inference-and-agentic-ai-on-amazon-eks/)
