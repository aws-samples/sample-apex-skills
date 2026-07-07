---
title: "Security & Compliance for GenAI on EKS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/security-and-compliance.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-genai/references/security-and-compliance.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-genai/references/security-and-compliance.md). Edit the source, not this page.
:::

# Security & Compliance for GenAI on EKS

Non-negotiable security baseline for every GenAI-on-EKS deployment, plus compliance-regime notes and escalation triggers. Every item in this file must be present in responses — no exceptions, no "we'll add security later."

---

## The Non-Negotiable Security Baseline

These controls apply to **every** GenAI workload on EKS — training, inference, RAG, agentic — regardless of environment or compliance regime.

### 1. Pod Credentials — EKS Pod Identity / IRSA

**Rule:** Pods MUST use [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) (preferred, K8s 1.24+) or IRSA for AWS API access. **NEVER** static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in env vars, ConfigMaps, or baked into images.

```yaml
# EKS Pod Identity association (preferred)
apiVersion: eks.amazonaws.com/v1
kind: PodIdentityAssociation
metadata:
  name: vllm-s3-access
spec:
  serviceAccountName: vllm-inference
  roleArn: arn:aws:iam::ACCOUNT:role/vllm-model-reader
```

Why for GenAI: model-serving pods need S3 (weights), Bedrock (gateway routing), and Secrets Manager (API keys). Static creds leak in logs, crash dumps, and large cached images.

The GenAI-on-EKS NVIDIA workshop uses `pods.eks.amazonaws.com` (Pod Identity) for all service accounts.

### 2. ECR Image Scanning

**Rule:** Enable **ECR enhanced scanning** (Inspector-powered) or integrate third-party (Snyk/Aqua/Wiz) in CI/CD. Block deployment of images with critical/high CVEs.

GenAI concern: DLCs and vLLM images carry massive dependency trees (PyTorch, CUDA, cuDNN, Neuron SDK). CVE surface is far larger than typical microservices. Scan on push AND weekly for base-image drift.

### 3. Secrets — Secrets Store CSI Driver

**Rule:** Store all secrets (API keys, model registry tokens, Langfuse keys) in **AWS Secrets Manager** or **SSM Parameter Store**. Mount via the [Secrets Store CSI Driver](https://docs.aws.amazon.com/secretsmanager/latest/userguide/integrating_csi_driver.html). Avoid **plain Kubernetes Secrets alone** — even with [KMS envelope encryption enabled](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html) (which addresses encryption-at-rest in etcd), a Secret is readable by anyone with namespace `get/list secrets` RBAC, isn't audited or rotated like Secrets Manager, and is trivially exposed if it lands in Git. The CSI-driver path keeps the source of truth in Secrets Manager (rotation, fine-grained IAM, CloudTrail audit) and never persists a Kubernetes Secret object. Never put secrets in ConfigMaps, env vars in Deployment specs, or baked into images.

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: genai-secrets
spec:
  provider: aws
  parameters:
    objects: |
      - objectName: "genai/litellm-master-key"
        objectType: "secretsmanager"
      - objectName: "genai/langfuse-secret-key"
        objectType: "secretsmanager"
```

### 4. Model Artifact Provenance

**Rule:** Verify integrity of every model artifact before serving.

| Model source | Verification method |
|-------------|---------------------|
| Baked into container image | **Image signing** via AWS Signer or Sigstore Cosign + admission controller (Kyverno/OPA) to reject unsigned images |
| Downloaded from Hugging Face | Verify **SHA256 checksums** against model card; pin exact revision hashes, not branch names |
| Downloaded from S3 | Enable **S3 Object Lock** (compliance mode) for production artifacts; verify ETag/checksum |

A compromised model artifact is the most dangerous GenAI supply-chain vector — it executes arbitrary inference on customer data. Treat model weights with the same rigor as application binaries.

### 5. Network Isolation

**Rule:** GPU/Neuron nodes in **private subnets** with no direct internet. All AWS API calls through **VPC endpoints**.

Required VPC endpoints for GenAI on EKS:

| Endpoint | Why |
|----------|-----|
| `com.amazonaws.REGION.s3` (Gateway) | Model weights, checkpoints, training data |
| `com.amazonaws.REGION.bedrock-runtime` (Interface) | LiteLLM → Bedrock calls |
| `com.amazonaws.REGION.ecr.api` + `ecr.dkr` | Image pull |
| `com.amazonaws.REGION.secretsmanager` | Secrets Store CSI |
| `com.amazonaws.REGION.sts` | Pod Identity / IRSA token exchange |
| `com.amazonaws.REGION.logs` | CloudWatch Logs |
| `com.amazonaws.REGION.monitoring` | CloudWatch Metrics / AMP remote-write |

Egress to internet (HF download, pip) via **NAT Gateway** with restrictive SG — or eliminate by pre-caching all artifacts in S3/ECR.

### 6. Audit Logging

**Rule:** Enable and retain:
- **CloudTrail** (management + data events for S3 model buckets)
- **EKS control plane audit logging** (minimum: `audit` + `authenticator` log types)
- **VPC Flow Logs**
- **Langfuse traces** — full prompt/response audit trail for GenAI-specific compliance

Retention: 90 days hot (CloudWatch), 1 year cold (S3 Glacier) for regulated workloads.

### 7. Pod Security Admission + CIS-Hardened AMI

**Rule:** Enforce [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/) at **`restricted`** for all GenAI namespaces. Use namespace-level exceptions for device-plugin DaemonSets — never cluster-wide `privileged`.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: genai-inference
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
```

For regulated workloads: **CIS-hardened AMIs** (AL2023 CIS Level 1 or Bottlerocket — hardened by design). EKS Auto Mode uses Bottlerocket by default.

---

## Compliance-Regime Notes

### HIPAA

- Model serving pods processing PHI: **HIPAA-eligible EKS cluster** (BAA in place).
- PHI in Langfuse traces: Langfuse must be in HIPAA-scoped environment with KMS CMK encryption at rest + access logging.
- Vector stores with PHI embeddings: use **Aurora PostgreSQL** (HIPAA-eligible) + PGVector; verify Bedrock KB HIPAA status at deployment time.
- Encrypt all EBS volumes and S3 buckets with **KMS CMK** (not default SSE-S3).

### PCI-DSS

- Isolate GenAI workloads in **dedicated cluster** (or dedicated node group + namespace + network policies) within CDE boundary.
- All pod-to-pod traffic encrypted — mTLS via service mesh or native pod encryption.
- Quarterly vulnerability scans of all DLC/vLLM images; retain scan reports.
- RBAC + IAM identity mapping restricting kubectl to GenAI namespace.

### FedRAMP (Moderate / High)

- Deploy in **GovCloud** or FedRAMP-authorized commercial regions.
- FIPS 140-2 validated modules — FIPS-enabled AMIs; TLS libraries in DLCs support FIPS mode.
- Continuous monitoring: EKS audit logs + CloudTrail → organization SIEM.
- Supply chain: all base images from approved registry (ECR in same boundary); no Docker Hub/HF pulls in production.

### GDPR

- RAG stores with EU personal data: deploy in **EU region** (eu-west-1, eu-central-1).
- **Right-to-erasure** for vector embeddings — deletion of source documents must cascade to deletion of derived embeddings (design upfront).
- Langfuse traces containing user prompts are personal data — configure retention + ensure same-region deployment.

---

## When to Escalate to SpecReq

1. **Regulated compliance** (HIPAA/PCI/FedRAMP/GDPR) AND GenAI processes regulated data — Specialist compliance review required. GenAI compliance is materially harder (prompts, outputs, embeddings are all data-processing activities).
2. **Multi-tenant SaaS** with cross-tenant data isolation — KV-cache isolation, prompt leakage, per-tenant vector partitioning need Security + ML TFC joint review.
3. **Agentic with autonomous code execution** — sandbox escape risk requires Security TFC review.
4. **Air-gapped environment** with no VPC endpoint path — custom supply chain design.
5. **Model distribution to third parties** — legal + security review beyond deployment hardening.

---

## Quick-Reference Checklist

Include in every GenAI-on-EKS response:

- [ ] Pod Identity / IRSA — no static credentials
- [ ] ECR image scanning — critical/high CVEs blocked
- [ ] Secrets via Secrets Manager + Secrets Store CSI
- [ ] Model provenance — image signing or checksum verification
- [ ] Private subnets + VPC endpoints (S3, Bedrock, ECR, STS, Secrets Manager)
- [ ] CloudTrail + EKS audit logs + VPC Flow Logs
- [ ] Pod Security Admission `restricted` + CIS-hardened AMI
- [ ] Langfuse traces encrypted + retained per compliance requirement

---

## Sources

- [EKS AI/ML Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml.html)
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Secrets Store CSI Driver](https://docs.aws.amazon.com/secretsmanager/latest/userguide/integrating_csi_driver.html)
- [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)
- [AWS Signer](https://docs.aws.amazon.com/signer/latest/developerguide/Welcome.html)
- [EKS Control Plane Logging](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [Container Security Hardening for EKS](https://docs.aws.amazon.com/eks/latest/best-practices/security.html)
