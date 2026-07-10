---
title: "Section 07 — Security Posture"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/security-posture.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/security-posture.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/security-posture.md). Edit the source, not this page.
:::

# Section 07 — Security Posture

## Purpose
Assess ECS security posture at **audit depth** — enough to rate it and flag top gaps. Deep hardening, role-trust remediation, and compliance-scope work (PCI/HIPAA/FedRAMP) belong to **`ecs-security`**; every RED here should hand off to it. Grounded in the [ECS security best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html).

## Checks to Execute

### 7.1 — Task / Execution Role Least Privilege & Trust

**What to check:**
- Task roles and execution roles attached to task definitions.
- Overly-broad managed policies (`*FullAccess`, `AdministratorAccess`) on task roles.
- Execution role scoped to only image pull, secrets, and log push.

**How to check:**
1. From task definitions collect `taskRoleArn` / `executionRoleArn`.
2. `aws iam list-attached-role-policies --role-name <role>` and `aws iam list-role-policies` → inspect for broad grants.
3. Optionally `aws iam get-role` → check the trust policy targets `ecs-tasks.amazonaws.com`.

**Rating:**
- 🟢 GREEN: Task roles scoped to the specific resources/actions the app needs; execution role limited to pull/secrets/logs; trust policies correct.
- 🟡 AMBER: Somewhat broad policies, or execution role reused as task role.
- 🔴 RED: `*FullAccess`/`AdministratorAccess` on task roles, or a single broad role shared across dissimilar services.
- ⬜ UNKNOWN: Cannot read IAM roles/policies.

**Key talking point:** The **task role** vends AWS permissions to the app; the **execution role** is used by the ECS agent (image pull, secrets injection, log push) and is **not** accessible to your container. Keep them distinct and least-privilege. Deep least-privilege + role-trust remediation → **`ecs-security`**. See [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

---

### 7.2 — Secrets Handling

**What to check:**
- Sensitive values injected via task-definition `secrets` (Secrets Manager / SSM Parameter Store `valueFrom`) rather than plaintext `environment`.
- Plaintext credentials in `environment` variables.

**How to check:**
1. Task definitions → `containerDefinitions[].secrets` (good) vs `environment` entries whose names look like credentials (`*_PASSWORD`, `*_KEY`, `*_TOKEN`) (bad).

**Rating:**
- 🟢 GREEN: All sensitive values injected via `secrets` from Secrets Manager or SSM Parameter Store; execution role scoped to those secret ARNs.
- 🟡 AMBER: Mostly `secrets` but a few sensitive-looking plaintext env vars, or overly broad secret-read permissions.
- 🔴 RED: Credentials in plaintext `environment` variables (visible in the task definition and console).
- ⬜ UNKNOWN: Cannot read task definitions.

**Key talking point:** ECS injects secrets at runtime from Secrets Manager or SSM Parameter Store via the `secrets` block referencing the secret ARN — never store credentials as plaintext in the task definition. Deep secrets rotation, KMS scoping, and least-privilege secret-read remediation → **`ecs-security`**. See [specifying sensitive data with Secrets Manager](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data-tutorial.html) and [SSM Parameter Store secrets](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-app-ssm-paramstore.html).

---

### 7.3 — Container Hardening

**What to check:**
- `readonlyRootFilesystem: true`.
- `privileged: false`.
- `user` set to a non-root UID.
- Linux capabilities dropped where possible.

**How to check:**
1. Task definitions → `containerDefinitions[]`: `readonlyRootFilesystem`, `privileged`, `user`, `linuxParameters.capabilities`.

**Rating:**
- 🟢 GREEN: Read-only root filesystem, non-root user, no privileged containers, unneeded capabilities dropped.
- 🟡 AMBER: Some hardening (e.g., non-root) but writable rootfs or capabilities not reviewed.
- 🔴 RED: Privileged containers, or running as root with a writable root filesystem on internet-facing workloads.
- ⬜ UNKNOWN: Cannot read task definitions.

These checks map directly to AWS **Security Hub CSPM ECS controls** — e.g., **ECS.4** (`privileged` must not be `true`, High) and **ECS.5** (`readonlyRootFilesystem` must be `true`, High; `NOT_APPLICABLE` for Windows containers). If the account runs Security Hub, cross-reference its ECS findings rather than re-deriving them by hand; both controls evaluate only the latest active task-definition revision. Deep hardening → **`ecs-security`**. See [task and container security best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-tasks-containers.html) and [Security Hub CSPM controls for Amazon ECS](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html).

---

### 7.4 — GuardDuty Runtime Monitoring for ECS

**What to check:**
- GuardDuty enabled with **Runtime Monitoring** covering ECS (required for any Fargate threat detection).
- **Applicability first:** Runtime Monitoring supports only ECS clusters running on **EC2 or Fargate**. It does **not** support ECS **Managed Instances**, **Windows** containers, or **ECS Anywhere / `EXTERNAL`** workloads. Determine the estate's compute mix before rating.

**How to check:**
1. `aws guardduty list-detectors` → `aws guardduty get-detector --detector-id <id>` and check the Runtime Monitoring feature status (best-effort; may be UNKNOWN without permissions).

**Rating:**
- 🟢 GREEN: GuardDuty Runtime Monitoring enabled for the ECS clusters in scope (Fargate and/or EC2), with the automated agent covering the Fargate clusters.
- 🟡 AMBER: GuardDuty enabled but Runtime Monitoring off (only foundational data sources), or on but not covering the in-scope ECS clusters.
- 🔴 RED: Fargate/EC2 workloads with GuardDuty Runtime Monitoring off — **no** runtime findings are generated for Fargate without it.
- ⚪ N/A: The estate runs **only** on ECS Managed Instances, Windows containers, or ECS Anywhere (`EXTERNAL`) — Runtime Monitoring does not support these, so there is no correct GREEN/RED path; state this and mark N/A (the same dedicated "⚪ N/A:" branch used in 1.2 / 1.4 / 1.6 / 2.6). Route runtime-threat-detection design to **`ecs-security`**.
- ⬜ UNKNOWN: Cannot read GuardDuty configuration.

**Key talking point:** For **Fargate**, GuardDuty Runtime Monitoring is *required* for threat detection — no other data source sees inside Fargate containers, so without it no findings are produced, and existing tasks are only covered **after they restart** (the agent sidecar is injected into new tasks / new service deployments). On EC2 it adds container-aware attribution (e.g., `AttackSequence:ECS/CompromisedCluster`). It is **not supported on Managed Instances, Windows, or ECS Anywhere**. The deep configuration of automated agent management, per-cluster scoping via GuardDuty tags, and remediation belong to **`ecs-security`** → route there rather than expanding here. Verified 2026-07-09. See [how Runtime Monitoring works with Fargate (ECS)](https://docs.aws.amazon.com/guardduty/latest/ug/how-runtime-monitoring-works-ecs-fargate.html) and [ECS compliance & security best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-compliance.html).

---

### 7.5 — ECR Image Scanning & Tag Immutability

**What to check:**
- ECR repositories used by the estate: scan-on-push (basic or enhanced/Inspector), tag immutability.

**How to check:**
1. Resolve repos from task-definition image URIs → `aws ecr describe-repositories` → `imageScanningConfiguration.scanOnPush`, `imageTagMutability`.

**Rating:**
- 🟢 GREEN: Scan-on-push (ideally enhanced scanning via Amazon Inspector) and immutable tags on production repos.
- 🟡 AMBER: Scanning on but tags mutable, or basic scanning where enhanced is warranted.
- 🔴 RED: No image scanning, or images pulled from untrusted public registries.
- ⬜ UNKNOWN: Cannot read ECR repositories (or images are not in ECR).

Deep supply-chain/signing posture → **`ecs-security`**.

---

### 7.6 — ECS Exec Posture (enableExecuteCommand)

**What to check:**
- Whether services/tasks have **ECS Exec** enabled (`enableExecuteCommand: true`) — interactive shell access into running containers. Useful for debugging, but on production it is an audit-relevant access path that should be deliberate, logged, and least-privilege (the task role governs what the session can do; session logging to CloudWatch Logs / S3 should be configured).

**How to check:**
1. `aws ecs describe-services --cluster <c> --services <s>` → `enableExecuteCommand`.
2. `aws ecs describe-tasks` → `enableExecuteCommand` on running tasks.
3. Where enabled, check cluster `configuration.executeCommandConfiguration` for logging (`logging`, `logConfiguration`) and KMS encryption.

**Rating:**
- 🟢 GREEN: ECS Exec disabled on production services, or enabled deliberately with session logging + KMS encryption and a least-privilege task role.
- 🟡 AMBER: ECS Exec enabled without session logging/encryption configured, or enabled broadly without a documented reason.
- 🔴 RED: ECS Exec enabled on sensitive/production workloads with a broad task role and no logging — an unaudited interactive access path into containers.
- ⬜ UNKNOWN: Cannot read service/task or cluster exec configuration.

**Key talking point:** ECS Exec opens an interactive channel into a running container via SSM; treat it as privileged access — enable per-need, log every session, encrypt with KMS, and keep the task role least-privilege. Deep hardening → **`ecs-security`**. See [using Amazon ECS Exec for debugging](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html).
