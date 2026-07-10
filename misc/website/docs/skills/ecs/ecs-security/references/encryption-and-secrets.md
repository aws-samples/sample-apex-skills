---
title: "Encryption & Secrets Management"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/encryption-and-secrets.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/encryption-and-secrets.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/encryption-and-secrets.md). Edit the source, not this page.
:::

# Encryption & Secrets Management

A first-class security area in the ECS Best Practices guide. Two concerns: **secrets injection** (the recurring ECS pain) and **encryption at rest / in transit**.

## Secrets injection — the ECS mechanism

Never put credentials in the task definition's `environment` (plaintext env vars — visible to anyone with `DescribeTaskDefinition`, and flagged by Security Hub). Instead use the task definition **`secrets`** block, which injects from **AWS Secrets Manager** or **SSM Parameter Store** at task start. The **task execution role** (not the task role) needs the retrieval permission (`secretsmanager:GetSecretValue` / `ssm:GetParameters`, plus `kms:Decrypt` if CMK-encrypted). Reference: [Pass sensitive data to an ECS container](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html).

```json
"secrets": [
  { "name": "DB_PASSWORD",
    "valueFrom": "arn:aws:secretsmanager:us-east-1:111122223333:secret:prod/db-AbCdEf:password::" }
]
```

### The trailing-colon JSON-key gotcha (verified)

The full `valueFrom` ARN syntax for Secrets Manager is:

```
arn:aws:secretsmanager:region:aws_account_id:secret:secret-name:json-key:version-stage:version-id
```

The last three fields — **`json-key`**, **`version-stage`**, **`version-id`** — are optional, **but if you omit them you must still include the colons** to select the defaults. So to reference the whole secret you end with `...secret-name` (no trailing colons needed via the base ARN), but to pick a single JSON key `password` at the default version you write `...secret-name:password::` — **the two trailing colons are required**. Getting this wrong is a classic silent failure (wrong value injected, or launch failure). Source: [Pass Secrets Manager secrets via env vars](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html).

Platform/agent version requirements (verified 2026-07-09 — [Pass Secrets Manager secrets via env vars](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html)):
- **Single JSON key or specific version:** Fargate platform version **1.4.0+** (Linux) / **1.0.0** (Windows); EC2 container agent **1.37.0+**.
- **Full secret contents:** Fargate **1.3.0+**; EC2 agent **1.22.0+**.

### Injected env-var secrets are NOT auto-rotated

A secret injected as an environment variable is read **only at container start**. If the secret is rotated afterward, the running container keeps the stale value — you must **launch a new task** or force a **new deployment**. For values that must always be current, use **SSM Parameter Store programmatic retrieval** (AWS recommends this because the app fetches the latest version on each read) or have the app call Secrets Manager directly via the task role. Sources: [secrets via env vars](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html) · [SSM Parameter Store programmatic retrieval](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-app-ssm-paramstore.html).

### Keep secret retrieval private

Create an **interface VPC endpoint for Secrets Manager (and SSM)** so retrieval doesn't traverse the public internet — required for fully private subnets and recommended under compliance regimes. See [network-isolation.md](network-isolation).

## Encryption at rest

- **ECR images** — encrypted at rest by default with **SSE-S3 (AES-256)**; KMS is opt-in (the `aws/ecr` AWS-managed key or a **CMK** for control under compliance) (verified 2026-07-10 — [ECR encryption at rest](https://docs.aws.amazon.com/AmazonECR/latest/userguide/encryption-at-rest.html)).
- **Fargate ephemeral storage** — encrypted with **AES-256 by default for tasks on platform version 1.4.0 or later** (earlier PVs don't get this default — pin/verify the PV); you can bring a CMK for the ephemeral volume on supported platform versions ([Fargate ephemeral storage encryption](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html)).
- **EBS volumes attached to tasks** (Fargate or EC2, via the infrastructure role) — enable encryption, with a CMK for compliance.
- **EFS volumes** — support encryption at rest (CMK) and in-transit (TLS mount).
- **CloudWatch Logs / CloudTrail S3** — encrypt with a CMK for high-sensitivity workloads (see [audit-logging.md](audit-logging)).

## Encryption in transit

- Terminate TLS at the **ALB/NLB**; for service-to-service, **Service Connect** supports TLS (via the infrastructure role) and **VPC Lattice** authenticates with SigV4.
- EFS in-transit via the `tls` mount option.

## Fargate FIPS 140-3 (verified — GovCloud only)

**AWS Fargate FIPS-140 (140-3) compliance is available only in AWS GovCloud (US) Regions** (verified 2026-07-09), is **off by default** (you must enable it via account setting), and requires: `operatingSystemFamily = LINUX`, `cpuArchitecture = X86_64`, and Fargate **platform version 1.4.0+**. Verify status inside a task with `cat /proc/sys/crypto/fips_enabled` (returns `1`). Do **not** claim Fargate FIPS in commercial Regions. Source: [AWS Fargate FIPS-140](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-fips-compliance.html).

## Shared responsibility (encryption & secrets)

| AWS manages | Customer manages |
|---|---|
| Secrets Manager/SSM services; injection mechanism at task start; default at-rest encryption (ECR, Fargate ephemeral AES-256); KMS service; Fargate FIPS modules (GovCloud) | Using `secrets` not plaintext env vars; execution-role retrieval + `kms:Decrypt` permission; the correct `valueFrom` colon syntax; rotation strategy; CMK selection + key policy; VPC-endpoint privacy; enabling Fargate FIPS |

## Sources
- [Pass sensitive data to an ECS container](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html) · [Secrets via env vars (Secrets Manager)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html) · [SSM Parameter Store programmatic retrieval](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-app-ssm-paramstore.html)
- [ECR encryption at rest](https://docs.aws.amazon.com/AmazonECR/latest/userguide/encryption-at-rest.html) · [AWS Fargate FIPS-140](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-fips-compliance.html)
