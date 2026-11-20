# Evals — eks-genai

## What these evals target

These inputs exercise the `eks-genai` skill's declared scope: building, training, fine-tuning, and serving generative AI / LLM workloads on Amazon EKS across the 6-layer stack (compute/hardware → cluster/scheduler → frameworks → storage → observability → AI gateway). `triggering.json` checks the skill fires on GenAI-workload prompts (hardware selection, vLLM/Ray serving, distributed training, Neuron migration, GPU/vLLM observability, AI gateway, agentic/RAG) and stays quiet for generic EKS architecture/build prompts, developer-platform prompts, and managed-service (Bedrock/SageMaker) prompts with no EKS self-hosting. `evals.json` checks the quality of two representative answers (greenfield inference stack + cost-first distributed training).

## Neighbour-skill disambiguation

The discriminator for `eks-genai` is a **GenAI/LLM workload running on EKS with GPU or Neuron** — the user is choosing accelerators, an inference engine, distributed-training mechanics, ML storage, or an AI gateway. It is not a generic cluster decision, an architecture document, infrastructure code generation, a self-service developer platform, or a fully-managed (Bedrock/SageMaker) ask.

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** (general EKS architecture, networking, IAM, reliability — no GenAI workload) — negatives 9, 10 ("VPC CNI mode and subnet sizing for a general-purpose cluster", "Pod Identity vs IRSA and PDB settings for web services").
- **`eks-design`** (architecture design documents and ADRs for EKS solutions) — negative 11 ("Produce an architecture design document and an ADR for a multi-tenant EKS platform").
- **`eks-build`** (generating deployable EKS Terraform / addon infrastructure code) — negative 12 ("Generate the Terraform to provision an EKS cluster with Karpenter and the LB controller").
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service paved paths on EKS) — negatives 13, 14 ("self-service golden paths via Backstage and ArgoCD", "progressive delivery with Argo Rollouts and multi-stage promotion").
- **Generic / managed-service (no EKS self-hosting)** (Amazon Bedrock managed LLM API, or SageMaker training — not a self-hosted EKS workload) — negatives 15, 16 ("managed LLM API with no infrastructure — just use Bedrock?", "fine-tune a model using SageMaker training jobs").
- **`eks-security`** (EKS security & compliance hardening — CIS, HIPAA/PCI/FedRAMP/GDPR, Pod Identity/Access Entries, PSA, GuardDuty, image signing, audit logging) — negative 17 ("What's the EKS security baseline and CI…").
<!-- SIBLING_MAP_END -->

The key discriminator: the prompt is about a self-hosted GenAI/LLM workload on EKS (accelerator choice, vLLM/Ray serving, distributed training, ML storage, GPU/Neuron observability, AI gateway, agentic/RAG) — not a generic EKS cluster decision, an architecture doc/ADR, Terraform generation, a developer self-service platform, or a fully-managed Bedrock/SageMaker path.

## Live-MCP caveat

Both `evals.json` prompts are advisory and fully scenario-described — each gives the model enough context (workload type, model size, latency target, cost posture, existing stack) to produce a quality stack recommendation without reaching into a live cluster or MCP server. Running these evals does **not** require a live EKS cluster or the EKS MCP server. Triggering evals are matched against the skill's `description` frontmatter only and are unaffected by MCP availability. There are no `live_only` prompts.

## How to run

From `misc/evals/`:
- `make validate-eks-genai` — frontmatter + 64/1024-char limits
- `make triggering-eks-genai` — triggering accuracy score
- `make benchmark-eks-genai` — aggregate task-eval stats
