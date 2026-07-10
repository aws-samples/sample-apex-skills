---
title: "Security & Compliance for GPU / ML Workloads on Amazon ECS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/security-and-compliance.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-genai/references/security-and-compliance.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-genai/references/security-and-compliance.md). Edit the source, not this page.
:::

# Security & Compliance for GPU / ML Workloads on Amazon ECS

This file is the **GPU/ML-specific security slice only.** The generic ECS security baseline — task/execution-role least-privilege and the `ecs-tasks.amazonaws.com` trust policy, secrets via Secrets Manager/SSM, ECR enhanced scanning, private subnets + VPC endpoints, `awsvpc` security-group-per-task, non-root/read-only-rootfs container hardening, CloudTrail + Container Insights audit — is **owned by the `ecs-security` skill; route deep compliance and CDE design there** and don't restate it in full here. What follows is only what changes because the workload is GPU/ML/GenAI.

## Baseline pointer (apply via `ecs-security`)

Every GPU/ML-on-ECS response still MUST include the standard baseline (roles, secrets, ECR scanning, private subnets + endpoints, hardening, audit) — see **`ecs-security`** for the how. Two baseline items have GPU/ML-specific twists worth stating inline:

- **Task role** grants the model server/trainer its S3 (weights/checkpoints), Secrets Manager, and — if the app calls Bedrock as a model target — **`bedrock-runtime`** permissions; scope to exact buckets/prefixes/secrets, never static keys.
- **Container hardening exception:** the GPU-sharing pattern (making `nvidia` the default Docker runtime) **loosens isolation** — reserve it for dev/test ([compute-hardware.md](compute-hardware)).

## GPU/ML-Specific Controls (the reason this file exists)

### Model-artifact provenance (the top GenAI supply-chain risk)

A poisoned model artifact executes arbitrary inference on customer data — treat weights like application binaries. Verify integrity before serving: pin **exact model revisions** (not floating tags/branches); verify **SHA256 checksums** for downloaded weights; use **image signing** (AWS Signer / Sigstore) for baked-in models; enable **S3 Object Lock** for production artifact buckets. Never pull weights from Hugging Face at task start in prod — stage in S3/ECR first ([storage.md](storage)).

### GPU/ML-specific supply chain

GPU/ML images (CUDA, cuDNN, PyTorch, Neuron SDK, DLC) carry **far larger dependency trees** than typical microservices — ECR enhanced scanning matters more here; scan on push and periodically for base-image drift, and block critical/high CVEs.

### `bedrock-runtime` VPC endpoint

If the ECS app calls Bedrock as a downstream model target, add the **`bedrock-runtime` interface endpoint** so that traffic stays private — this is the one VPC endpoint beyond the standard S3/ECR/Secrets/logs set that GenAI-on-ECS specifically adds.

### Inference-endpoint authentication

A self-hosted model endpoint has **no built-in auth**. Decide **internal vs internet-facing** (internal ALB/NLB in private subnets reached via VPC/PrivateLink is the default for internal consumers), and always put an authN/authZ layer in front — Cognito/OIDC on the ALB, API Gateway, or a JWT/mTLS-validating reverse proxy — plus WAF for internet-facing. Deep endpoint-security design → **`ecs-security`**. See [inference-serving.md](inference-serving) for the streaming/idle-timeout interaction.

### GuardDuty Runtime Monitoring — MI carve-out

Enable **GuardDuty ECS Runtime Monitoring** on **ECS-on-EC2** container instances for runtime threat detection. **Critical caveat given how heavily this skill promotes Managed Instances:** Runtime Monitoring is **not supported on ECS Managed Instances**, and also **not on ECS Anywhere or the Windows OS** ([Runtime Monitoring considerations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html)). An MI-based GPU fleet therefore cannot rely on GuardDuty RM for the host — name a concrete alternative: (1) a **third-party runtime-security agent deployed as a sidecar container or a per-instance daemon task** (e.g. Falco-based tooling or a commercial CWPP/CNAPP agent that supports ECS), or (2) **keep the workloads that require runtime threat detection on the ECS-on-EC2 launch type**, where GuardDuty RM is supported. Pair with CloudTrail (management + S3 model-bucket data events).

## Compliance-Regime Notes (GPU/ML angle; full regime design → `ecs-security`)

- **HIPAA:** GPU tasks processing PHI on a HIPAA-eligible account (BAA in place); KMS-CMK encryption for EBS/S3/EFS; verify Bedrock/other model targets' HIPAA status at deployment.
- **PCI-DSS:** isolate GPU/ML workloads within the CDE using **ECS-native** boundaries — a **dedicated cluster** *or* a **dedicated capacity provider / ASG** + **security-group-per-task** (`awsvpc`) + **separate task/execution roles (and ideally separate accounts)**. (Node groups and namespaces are **Kubernetes** constructs that **don't exist in ECS** — don't prescribe them here; that's an `eks-genai` pattern.) Encrypt task-to-task traffic; retain quarterly image scans.
- **FedRAMP:** GovCloud or FedRAMP-authorized Regions; FIPS-validated modules; images only from an approved in-boundary ECR (no Docker Hub / HF pulls in prod).
- **GDPR:** EU-region deployment for EU personal data; design right-to-erasure so deleting source documents cascades to derived embeddings; treat stored prompts/outputs as personal data.

## When to Escalate to a Specialist Review

1. Regulated data (HIPAA/PCI/FedRAMP/GDPR) processed by the GenAI workload — GenAI compliance is materially harder (prompts, outputs, embeddings are all data-processing).
2. Multi-tenant SaaS needing cross-tenant isolation of models/data on shared GPU capacity.
3. Agentic workloads with autonomous code/tool execution — sandbox-escape risk.
4. Air-gapped environments with no VPC-endpoint path — custom supply-chain design.

## Quick-Reference Checklist

Baseline items (details in **`ecs-security`**):
- [ ] Task + execution role least-privilege; trust policy allows `ecs-tasks.amazonaws.com`; `iam:PassRole` scoped
- [ ] Secrets via Secrets Manager / SSM — never in image/env
- [ ] ECR enhanced scanning — critical/high blocked
- [ ] Private subnets + VPC endpoints (S3, ECR, Secrets Manager, logs); non-root, read-only rootfs, dropped capabilities
- [ ] CloudTrail + Container Insights audit

GPU/ML-specific (this file):
- [ ] Model provenance — pinned revision + SHA256 checksum / signing; S3 Object Lock on prod artifact buckets
- [ ] `bedrock-runtime` VPC endpoint if the app calls Bedrock
- [ ] Inference-endpoint authN/authZ + internal-vs-internet-facing decision
- [ ] GuardDuty ECS Runtime Monitoring on **ECS-on-EC2** hosts — **not available on Managed Instances / Anywhere / Windows** (MI fleets: third-party runtime agent as sidecar/daemon task, or keep runtime-monitored workloads on the EC2 launch type)

## Sources

- [Amazon ECS security best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security.html) · [Amazon ECS Best Practices Guide — security](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)
- [Amazon ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [Task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [Passing sensitive data to a container (Secrets Manager / SSM)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html)
- [Amazon ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html)
- [GuardDuty Runtime Monitoring for Amazon ECS — considerations (not supported on Managed Instances / Anywhere / Windows)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html)
- [Interface VPC endpoints for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html)
- For the full ECS security baseline and regulated-compliance design: the **`ecs-security`** skill
