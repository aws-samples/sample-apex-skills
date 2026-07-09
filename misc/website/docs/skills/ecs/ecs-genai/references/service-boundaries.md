---
title: "Service Boundaries — Fargate-GPU Exclusion & When to Leave ECS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/service-boundaries.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-genai/references/service-boundaries.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/service-boundaries.md). Edit the source, not this page.
:::

# Service Boundaries — Fargate-GPU Exclusion & When to Leave ECS

This skill's most important job is to keep GPU/ML workloads on the *right* AWS service. Two questions: (1) is Fargate viable? (never, for GPU) and (2) is ECS-on-EC2 the right home, or should this be EKS / SageMaker / Bedrock?

## 1. AWS Fargate Has No GPU — the Evidence

State this as fact, not opinion. GPU is a **container-instance (EC2)** capability on ECS; Fargate exposes only CPU + memory.

- AWS lists the **`gpu` task-definition parameter among those "not valid in Fargate tasks"** (alongside `placementConstraints`); `devices` and `privileged` appear separately under **`linuxParameters` limitations** on the same page — either way none work for a Fargate GPU task ([ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)).
- The **Fargate task-size model** enumerates valid CPU/memory combinations only — 256 (.25 vCPU) through 32768 (32 vCPU), with matching memory ranges — and **no GPU dimension**.
- AWS documents the GPU `resourceRequirements` type as the number of physical GPUs the **ECS container agent** reserves on the **container instance**. The ECS GPU documentation is entirely about **EC2 GPU-based container instances** and the GPU-optimized AMI — there is no Fargate GPU path ([ECS GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)).

**Consequence:** any GPU/accelerator container must run on **ECS-on-EC2**, **ECS Managed Instances**, or **ECS Anywhere/External**. Fargate can still host **CPU-only** parts of a GenAI app (an API front-end, an orchestrator, a RAG retriever calling Bedrock) — just not the accelerated container.

**Guidance for the CPU-only orchestrator/RAG/gateway pieces** (so this isn't a dead-end blessing): a **RAG retriever or agent orchestrator** that calls a model runs fine on Fargate — the boundary to name is **Amazon Bedrock AgentCore** for a fully-managed agent runtime (memory/tools/identity) vs **self-hosting the framework on ECS** when you want to own it. A self-hosted **AI gateway (e.g. LiteLLM)** — model routing, key management, cost attribution across your ECS-hosted models and Bedrock — is a documented `ai-gateway` target and also runs as a CPU-only ECS/Fargate service. See [inference-serving.md](inference-serving) for the gateway/agentic patterns; agentic workloads with autonomous tool/code execution → also loop in `ecs-security`.

## 2. Stay on ECS vs Route Elsewhere

| Signal | Right home | Why |
|---|---|---|
| Team wants a **simple control plane**, IAM-native, no Kubernetes to operate; GPU/Neuron container inference or moderate training | **ECS-on-EC2 (this skill)** | ECS gives container + capacity primitives without K8s operational surface |
| Needs **Karpenter-style GPU provisioning**, **KubeRay/Ray Serve/JARK**, **KServe scale-to-zero**, **fractional-GPU (MIG/time-slicing/DRA)**, or a **Kubernetes serving mesh** | **EKS (`eks-genai`)** | These are Kubernetes-native constructs with no native-ECS equivalent |
| Wants **fully-managed training** (no capacity/harness to own) or a **managed inference endpoint** (real-time/serverless/async, multi-model, autoscaling) | **Amazon SageMaker** | SageMaker manages the training/hosting plane end-to-end; HyperPod for large clusters |
| Wants a **managed foundation-model API** with **no self-hosting** (no GPU at all) | **Amazon Bedrock** | Zero infrastructure; pay-per-use FMs, Knowledge Bases, Agents, Guardrails |
| Generic **ECS launch-type / cluster design** with **no accelerator or ML workload** | **`ecs-architect`** | Model selection/design without the GPU/ML specialization |

### Sharper EKS boundary (vs `eks-genai`)

Route to **`eks-genai`** the moment the requirement names a Kubernetes primitive: Karpenter, node pools, device plugins, KubeRay, Ray Serve on K8s, KServe, JARK, Kubeflow, gang scheduling (Volcano/Kueue), MIG/time-slicing/DRA fractional-GPU, or an existing EKS estate the team wants to extend. ECS deliberately has **no** Karpenter and **no** fractional-GPU scheduler — if those are hard requirements, ECS is the wrong tool.

### Sharper SageMaker boundary

Route to **SageMaker** when the customer does **not want to own container orchestration or GPU capacity** at all: managed training jobs, managed endpoints, built-in model registry/pipelines, HyperPod for very large training. If they *want* to own the container/service (custom serving stack, existing ECS estate, tight infra control), ECS-on-EC2 is the fit.

### Sharper Bedrock boundary

Route to **Bedrock** when there is **no self-hosting** — the customer just wants to call managed FMs. This skill covers Bedrock only as a *downstream target* a self-hosted ECS app might also call (hybrid: self-host cost-sensitive models on ECS-GPU, call Bedrock for best-of-breed).

## 3. Quick Router

```text
GPU / accelerator container?
  ├─ No GPU, just "which ECS model"      → ecs-architect
  ├─ Fargate?                            → NO (no GPU) — use ECS-on-EC2 / Managed Instances / Anywhere
  ├─ Kubernetes primitive named / EKS    → eks-genai
  ├─ Fully-managed train/host, no infra  → SageMaker
  ├─ Managed FM API, no self-hosting     → Bedrock
  └─ Self-hosted GPU/Neuron on ECS       → THIS SKILL (ecs-genai)
```

## Sources

- [Amazon ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)
- [Amazon ECS task definitions for GPU workloads](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html)
- [Use GPUs with Amazon ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-gpu.html)
- [Amazon SageMaker](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) · [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)
- [Best Practices for AI/ML Workloads on Amazon EKS](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html) (the eks-genai counterpart)
