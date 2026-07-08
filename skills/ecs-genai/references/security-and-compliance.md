# Security & Compliance for GPU / ML Workloads on Amazon ECS

Non-negotiable security baseline for every GPU/ML-on-ECS deployment. GenAI workloads add supply-chain (model artifacts, huge dependency images) and data-processing (prompts, outputs, embeddings) risk on top of standard ECS hardening. For deep, general ECS security use the `ecs-security` skill; this file is the GPU/ML-specific slice.

## The Non-Negotiable Baseline

Include every item in every GPU/ML-on-ECS response.

### 1. Task role + execution role — least-privilege, no static keys

- **Task role** grants the *application* (model server / trainer) its AWS permissions — S3 for weights/checkpoints, Bedrock-runtime if used as a gateway target, Secrets Manager. Scope to specific buckets/prefixes/secrets; **never** put `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in env vars, the task definition, or the image.
- **Execution role** grants the *ECS agent* rights to pull the ECR image and inject secrets/logs — keep it separate and minimal.
- The recurring hard failure on ECS is the **task-role trust-relationship error** ("ECS was unable to assume the role"): the role's trust policy must allow `ecs-tasks.amazonaws.com` to `sts:AssumeRole`, and `iam:PassRole` must be granted to whoever registers/runs the task. Get the trust policy right first.

```json
// Task role trust policy
{ "Version": "2012-10-17", "Statement": [{
  "Effect": "Allow",
  "Principal": { "Service": "ecs-tasks.amazonaws.com" },
  "Action": "sts:AssumeRole"
}]}
```

### 2. Secrets — Secrets Manager / SSM Parameter Store injection

Store model-registry tokens, API keys, and gateway keys in **AWS Secrets Manager** or **SSM Parameter Store**; inject via the task definition `secrets` block (resolved by the execution role) — never bake secrets into the (often cached, widely-pulled) model image or a ConfigMap-style env.

```json
"secrets": [
  { "name": "HF_TOKEN", "valueFrom": "arn:aws:secretsmanager:REGION:ACCT:secret:hf-token" }
]
```

### 3. ECR image scanning

Enable **ECR enhanced scanning (Amazon Inspector)** and block deployment of critical/high CVEs. GPU/ML images (CUDA, cuDNN, PyTorch, Neuron SDK, DLC) carry **far larger dependency trees** than typical microservices — scan on push and periodically for base-image drift.

### 4. Model-artifact provenance

A poisoned model artifact executes arbitrary inference on customer data — treat weights like application binaries. Verify integrity before serving: pin **exact model revisions** (not floating tags/branches); verify **SHA256 checksums** for downloaded weights; use **image signing** (AWS Signer / Sigstore) for baked-in models; enable **S3 Object Lock** for production artifact buckets.

### 5. Network isolation

Place GPU/Neuron container instances in **private subnets** with no direct inbound internet. Route AWS API calls through **VPC endpoints**:

| Endpoint | Why |
|---|---|
| `s3` (Gateway) | Model weights, checkpoints, training data |
| `ecr.api` + `ecr.dkr` | Image pull |
| `secretsmanager` | Secrets injection |
| `logs` / `monitoring` | CloudWatch Logs / metrics |
| `bedrock-runtime` (Interface) | Only if the app calls Bedrock as a model target |

Egress for any unavoidable downloads via a NAT gateway with restrictive SGs — or eliminate by pre-caching all artifacts to S3/ECR. Use **security-group-per-task** (`awsvpc` mode) to scope task-to-task traffic.

### 6. Container hardening

Run containers **non-root**, with **read-only root filesystem** where the framework allows, and drop unneeded Linux capabilities. Note the GPU-sharing exception: making `nvidia` the default Docker runtime for GPU sharing loosens isolation — reserve that pattern for dev/test ([compute-hardware.md](compute-hardware.md)).

### 7. GuardDuty ECS Runtime Monitoring + audit logging

Enable **GuardDuty ECS Runtime Monitoring** on the EC2 container instances for runtime threat detection. Enable **CloudTrail** (management + S3 model-bucket data events) and **Container Insights** for audit and forensics. Retain per compliance requirement.

## Compliance-Regime Notes

- **HIPAA:** GPU tasks processing PHI on a HIPAA-eligible account (BAA in place); KMS-CMK encryption for EBS/S3/EFS; audit all access; verify Bedrock/other targets' HIPAA status at deployment.
- **PCI-DSS:** isolate GPU/ML workloads in a dedicated cluster or node group + namespace + SG boundary within the CDE; encrypt task-to-task traffic; quarterly image scans retained.
- **FedRAMP:** GovCloud or FedRAMP-authorized Regions; FIPS-validated modules; images only from an approved ECR in-boundary (no Docker Hub / HF pulls in prod).
- **GDPR:** EU-region deployment for EU personal data; design right-to-erasure so deleting source documents cascades to derived embeddings; treat stored prompts/outputs as personal data.

## When to Escalate to a Specialist Review

1. Regulated data (HIPAA/PCI/FedRAMP/GDPR) processed by the GenAI workload — GenAI compliance is materially harder (prompts, outputs, embeddings are all data-processing).
2. Multi-tenant SaaS needing cross-tenant isolation of models/data on shared GPU capacity.
3. Agentic workloads with autonomous code/tool execution — sandbox-escape risk.
4. Air-gapped environments with no VPC-endpoint path — custom supply-chain design.

## Quick-Reference Checklist

- [ ] Task role + execution role least-privilege; trust policy allows `ecs-tasks.amazonaws.com`; `iam:PassRole` scoped
- [ ] Secrets via Secrets Manager / SSM — never in image/env
- [ ] ECR enhanced scanning — critical/high blocked
- [ ] Model provenance — pinned revision + checksum/signing
- [ ] Private subnets + VPC endpoints (S3, ECR, Secrets Manager, logs; Bedrock if used)
- [ ] Non-root, read-only rootfs, dropped capabilities
- [ ] GuardDuty ECS Runtime Monitoring + CloudTrail + Container Insights

## Sources

- [Amazon ECS security best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security.html) · [Amazon ECS Best Practices Guide — security](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)
- [Amazon ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [Task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [Passing sensitive data to a container (Secrets Manager / SSM)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html)
- [Amazon ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html)
- [GuardDuty Runtime Monitoring for Amazon ECS](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html)
- [Interface VPC endpoints for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html)
