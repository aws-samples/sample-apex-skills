---
name: ecs-security
description: Security and compliance guidance for Amazon ECS — "ECS was unable to assume the role", task role vs execution role, iam:PassRole, confused-deputy aws:SourceArn trust, Fargate vs EC2 shared responsibility, injecting Secrets Manager/SSM secrets (trailing-colon JSON-key gotcha), readonlyRootFilesystem / non-root / drop capabilities, ECS Exec governance, security-group-per-task, VPC endpoint policies, GuardDuty ECS Runtime Monitoring, ECR Inspector scanning, image signing, Fargate FIPS, or PCI/HIPAA/FedRAMP. Walks a discovery-driven 7-layer stack plus the AWS-canonical baseline and a 30/60/90 roadmap. Trigger even if "compliance" is never said — any ECS hardening, task-trust fix, or secrets-injection qualifies. Skip for EKS/Kubernetes (eks-security), GenAI/GPU security (ecs-genai), App Runner/Lambda, auditing a live estate's operational posture (ecs-operation-review — "audit my ECS security posture" matches both), or account-level security with no ECS angle.
---

# ECS Security & Compliance

End-to-end, opinionated security and compliance guidance for Amazon ECS, structured as a **7-layer stack** plus a **compliance-regime cross-cutting view**. This skill is **discovery-driven** — the right hardening stack is a function of *(launch type × compliance regime × workload sensitivity × audit timeline × team skill × network topology × operational-overhead tolerance)*. The single biggest ECS-specific variable is **launch type (Fargate vs EC2 vs Managed Instances vs ECS Anywhere)**, because it moves the shared-responsibility line and changes which controls are even available. Skipping discovery makes the recommendation wrong about half the time.

The AWS-published foundation for every recommendation is the [ECS Best Practices: Security](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html) guide (task & container security, network security, IAM roles) and the [ECS security documentation set](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security.html) (IAM, shared-responsibility, Fargate FIPS, infrastructure security). For "which launch/deployment model should I use" (non-security) use `ecs-architect`; for auditing a live estate's operational posture use `ecs-operation-review`.

> **The accuracy bar (non-negotiable for this skill).** Compliance is the one domain where customers validate *every* claim against an auditor. **Compliance status changes over time — always defer to the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage** in any customer-facing document; the ECS-specific pointer is [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html). Never state a cryptographic-module status, FedRAMP boundary, or certification you cannot cite to an AWS-published source. When you can't ground a claim, say so — do not synthesize.

## When to Use This Skill

**Activate when the user wants to:**
- Fix the **#1 recurring ECS error — "ECS was unable to assume the role …"** (task/execution-role trust misconfiguration)
- Get the **task role vs task execution role vs container instance role vs infrastructure role** distinction right, and least-privilege each one
- Add **confused-deputy protection** (`aws:SourceArn` / `aws:SourceAccount`) to a task-role trust policy, or scope **`iam:PassRole`**
- Understand the **Fargate vs EC2 vs Managed Instances shared-responsibility split** for a security/audit conversation
- **Inject secrets** from Secrets Manager / SSM Parameter Store into a task definition (and dodge the trailing-colon JSON-key gotcha)
- **Harden containers** — `readonlyRootFilesystem`, non-root `user`, `privileged: false`, drop Linux capabilities, distroless images
- **Isolate the network** — `awsvpc` security-group-per-task, private subnets, VPC endpoints for ECR/S3/Secrets Manager/CloudWatch
- Add **runtime detection** (GuardDuty ECS Runtime Monitoring + Extended Threat Detection) and **image supply-chain** controls (ECR enhanced scanning, AWS Signer + Notation signing)
- Prepare an ECS workload for a **PCI-DSS / HIPAA / FedRAMP / SOC 2 / ISO** audit, or turn on **Fargate FIPS**

**Don't use this skill for:**
- **EKS / Kubernetes** container security (RBAC, Pod Identity/IRSA, PSA, NetworkPolicy, kube-bench) → `eks-security`
- **GenAI / GPU / ML-workload** security specifically (model-artifact provenance, GPU-node compliance) → `ecs-genai` (or `eks-genai` on EKS)
- **AWS App Runner / Lambda / Batch** — different services with different security models
- **AWS account-level / org-wide** security with no ECS-specific angle (SCPs, SSO, org GuardDuty) → Security guidance, not this skill
- Choosing a launch/deployment model with no security driver (→ `ecs-architect`), auditing live operational posture (→ `ecs-operation-review`), or discovery/inventory of an estate (→ `ecs-recon`, once available)

## Discovery First — the Required Questions

**Do NOT recommend a hardening stack before answering these.** The single most common mistake is prescribing controls without confirming the launch type — a Fargate answer and an ECS-on-EC2 answer differ at Layers 1, 3, 5, and 6. The first four answers determine ~80% of the recommendation.

1. **Launch type(s)?** AWS Fargate / ECS on EC2 / ECS Managed Instances / ECS Anywhere (external) / mixed. *(This is the ECS-specific first question — it sets the shared-responsibility line.)*
2. **Compliance regime(s)?** None / SOC 2 / HIPAA / PCI-DSS / FedRAMP Moderate / FedRAMP High / GDPR / ISO 27001 / NIST 800-53/171 / IL4-IL5 — rank primary/secondary if multiple.
3. **Workload sensitivity?** Public / internal / PII / PHI (HIPAA) / cardholder data (PCI) / federal.
4. **Audit timeline?** None / <3 mo (urgent) / 3-6 mo / 6-12 mo / continuous.
5. **Network topology?** Public subnets + IGW / private subnets + NAT / fully private + VPC endpoints; single vs multi-account; multi-region; GovCloud.
6. **Secrets & config posture?** Plaintext env vars (bad) / Secrets Manager / SSM Parameter Store / hybrid; rotation requirement.
7. **Team ECS/security skill?** Low / moderate / high / mixed.
8. **Current security tooling baseline?** None / AWS-native / third-party CNAPP / OSS / hybrid.

Full required + recommended question set, adoption-challenge archetypes, and the response framework: [references/engagement-and-response.md](references/engagement-and-response.md).

## The 7-Layer Security & Compliance Stack

Walk the layers bottom-up on a first engagement; each layer's controls compound on the previous. The **AWS-canonical default** column assumes a new commercial Fargate workload — the launch-type substitutions are noted per layer.

| Layer | Focus | AWS-canonical default | Reference |
|-------|-------|----------------------|-----------|
| **1 — Compute / Shared Responsibility** | Who secures what; node OS | **Fargate** (AWS manages OS/kernel/runtime — smallest customer surface); on **EC2/Managed Instances**, harden the container instance (ECS-optimized AL2023 or **Bottlerocket**, patch cadence, IMDSv2, lock down IMDS from tasks) | [shared-responsibility.md](references/shared-responsibility.md) |
| **2 — Identity & Access** | Role trust & least privilege | **Task role** (app → AWS) + **task execution role** (agent → ECR/logs/secrets) as *separate* least-privileged roles; **confused-deputy** `aws:SourceArn`/`aws:SourceAccount` on trust policies; scoped **`iam:PassRole`** | [identity-and-access.md](references/identity-and-access.md) |
| **3 — Task & Container Hardening** | What a container may do | **`readonlyRootFilesystem: true`** + non-root **`user`** + **`privileged: false`** + drop Linux capabilities + distroless image + CPU/memory limits | [task-container-hardening.md](references/task-container-hardening.md) |
| **4 — Image Supply Chain** | Trust what you run | **ECR Enhanced Scanning** (Amazon Inspector) + **immutable tags** + **AWS Signer + Notation** signing + CMK-encrypted repos | [image-supply-chain.md](references/image-supply-chain.md) |
| **5 — Network Isolation** | What a task may reach | **`awsvpc` mode** + **security-group-per-service** + **private subnets** + **VPC endpoints** (ECR api/dkr, S3 gateway, Secrets Manager, CloudWatch Logs) + no public IPs | [network-isolation.md](references/network-isolation.md) |
| **6 — Runtime Security** | Detect at runtime | **GuardDuty ECS Runtime Monitoring** (Fargate + EC2; **not** Managed Instances, Windows, or ECS Anywhere; running Fargate tasks covered only after restart/redeploy) + **Extended Threat Detection** (automatic, no *additional* cost atop paid GuardDuty); findings → Security Hub | [runtime-security.md](references/runtime-security.md) |
| **7 — Audit Logging & Compliance** | Prove what happened + continuous evidence | **CloudTrail** (ECS API) + **Container Insights** + app logs via `awslogs`/FireLens + **Config** rules + **Security Hub** ECS controls + **Audit Manager** + **Artifact** | [audit-logging.md](references/audit-logging.md) · [compliance-accelerators.md](references/compliance-accelerators.md) |

> **The AWS-canonical reference stack for a new commercial Fargate service:** Fargate (L1) + separate least-privileged task role & execution role with confused-deputy-scoped trust (L2) + `readonlyRootFilesystem`/non-root/`privileged:false`/dropped-capabilities/distroless (L3) + ECR Enhanced Scanning + immutable tags + AWS Signer signing (L4) + `awsvpc` SG-per-service in private subnets + VPC endpoints (L5) + GuardDuty ECS Runtime Monitoring + Extended Threat Detection (L6) + CloudTrail + Container Insights + Config + Security Hub ECS controls (L7). The **ECS-on-EC2 path** adds container-instance OS hardening + IMDS lockdown at L1/L5 and loses Fargate's per-task kernel isolation (see the boundary note below). **Managed Instances** loses GuardDuty Runtime Monitoring support at L6.

**Cross-cutting concerns** (span every layer, aligned to the AWS ECS Best Practices security areas): **secrets & data encryption** (Secrets Manager/SSM injection, the JSON-key syntax, at-rest/in-transit, EBS volume & ephemeral-storage encryption, Fargate FIPS) → [encryption-and-secrets.md](references/encryption-and-secrets.md); **incident response & forensics** (the runbook when a detection fires) → [incident-response-and-forensics.md](references/incident-response-and-forensics.md); and the **shared-responsibility model** itself → [shared-responsibility.md](references/shared-responsibility.md). Each reference includes its per-layer shared-responsibility split.

> **The one boundary you must state precisely (verified, verbatim from AWS docs):** *"Containers are not a security boundary and the use of task IAM roles does not change this."* On **Fargate**, each task has its own isolation boundary — no shared kernel, CPU, memory, or ENI with another task. On **EC2, ECS Managed Instances, and ECS Anywhere** there is **no task isolation**: a compromised container can reach credentials for co-located tasks, the container instance role, and instance metadata (IMDS). For strict workload isolation, use **Fargate**; on EC2, lock down IMDS access from tasks. Source: [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

## Compliance-Regime Scope (cross-cutting)

Amazon ECS and AWS Fargate are broadly in scope for AWS's major compliance programs (PCI-DSS, HIPAA eligibility, SOC 1/2/3, ISO, FedRAMP, and more) — but **program scope changes over time and is not the same across services or Regions**, so this skill **does not quote a fixed ECS scope table from memory**. Instead, defer to the authoritative live pages every time: [AWS Services in Scope by Compliance Program](https://aws.amazon.com/compliance/services-in-scope/) and the ECS-specific [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html). Per-regime nuance, the verify-against-live-page discipline, and worked HIPAA/PCI/FedRAMP scenarios: [references/compliance-regimes.md](references/compliance-regimes.md).

> **Always include the disclaimer in customer-facing output:** "Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage." And precision matters: ECS/Fargate are **HIPAA-*eligible*** (with a signed BAA), not "HIPAA-compliant"; **Fargate FIPS 140-3 is GovCloud (US) only, LINUX + X86_64 + platform version 1.4.0+, and off by default** (verified: [Fargate FIPS-140](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-fips-compliance.html)).

## Security Baseline (non-negotiable — every recommendation includes this)

Regardless of regime, every ECS hardening recommendation MUST include:
- **Separate task role and task execution role**, each least-privileged — never one over-broad shared role, never static AWS keys in the container
- **Confused-deputy protection** (`aws:SourceArn` scoped to your account via the all-clusters wildcard `arn:aws:ecs:region:acct:*`, plus `aws:SourceAccount`) on the `ecs-tasks.amazonaws.com` trust policy for cross-service roles — cluster/task scoping in `aws:SourceArn` is not supported ([task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html))
- **Scoped `iam:PassRole`** — grant it only for the specific execution/task/infrastructure role ARNs, never `Resource: "*"`
- **Secrets via Secrets Manager or SSM Parameter Store** injected through the task definition `secrets` block (execution role needs the retrieval permission) — never plaintext in `environment` env vars
- **Container hardening** — `readonlyRootFilesystem: true`, non-root `user`, `privileged: false` (privileged is unsettable on Fargate anyway), drop unneeded Linux capabilities (on Fargate the only *addable* capability is `SYS_PTRACE`), distroless/minimal base image, explicit CPU/memory limits, immutable ECR tags. Note the **ECS Exec interplay**: `readonlyRootFilesystem: true` is **incompatible with ECS Exec** (the SSM agent must write to the container filesystem), and ECS Exec sessions run as **`root` regardless of the container `user`** — govern Exec accordingly (below). **Windows:** `readonlyRootFilesystem`, `user`, and Linux-capability drops don't apply — see the Layer 3/6 caveats
- **`awsvpc` network mode** with a **least-privilege security group per service**, tasks in **private subnets**, no auto-assigned public IPs, and **VPC endpoints** for ECR (api + dkr), S3 (gateway, for layers), Secrets Manager, and CloudWatch Logs
- **ECR Enhanced Scanning** (Amazon Inspector) on all production repositories; image signing (AWS Signer + Notation) where the regime requires provenance
- **GuardDuty ECS Runtime Monitoring** (Fargate + EC2 — **not** Managed Instances, Windows, or ECS Anywhere; see Layer 3/6 caveats) + **Extended Threat Detection** (automatic, no additional cost atop paid GuardDuty); route findings to **Security Hub**. On a **fully-private default-deny build (Layer 5), the GuardDuty telemetry path must be explicitly allowed** — the GuardDuty-created VPC endpoint plus the S3 managed prefix list (for the agent/sidecar image) — or detection silently goes dark
- **CloudTrail** for the ECS API audit trail + **Container Insights** + application logs to CloudWatch via `awslogs` or FireLens
- **Encryption** — EBS volumes and ephemeral storage encrypted (Fargate ephemeral storage is AES-256 encrypted by default on **platform version 1.4.0+**); CMK for ECR/EBS/logs under compliance regimes; **lock down IMDS from tasks on EC2** — the actual controls are `ECS_AWSVPC_BLOCK_IMDS=true` in `/etc/ecs/ecs.config` for `awsvpc` tasks, an iptables `DROP` to `169.254.169.254` for `bridge`-mode tasks, and IMDSv2 with hop-limit 1 on the instance (see [shared-responsibility.md](references/shared-responsibility.md))
- **ECS Exec governance** (if Exec is enabled) — restrict `ecs:ExecuteCommand` via IAM condition keys (`ecs:cluster`, `ecs:container-name`, resource tags), turn on cluster `executeCommandConfiguration` **session logging to S3/CloudWatch** with **KMS session encryption**, audit **ExecuteCommand** events in CloudTrail, and **disable Exec in production** unless break-glass is required (see [identity-and-access.md](references/identity-and-access.md))
- **Preventive governance** — ECS itself won't refuse a non-compliant task definition at launch, so enforce what IAM *can* see with **SCPs / IAM condition keys**: `ecs:RegisterTaskDefinition` supports the `ecs:privileged`, `ecs:compute-compatibility`, `ecs:task-cpu`/`ecs:task-memory`, and tag condition keys — so you can deny `privileged` task definitions ([Service Authorization Reference — ECS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html)). **No condition key inspects `environment`/secret contents as of 2026-07-10**, so plaintext-secret registration is *not* IAM/SCP-deniable — catch it with detective/pipeline controls instead (Security Hub ECS.8 — note it matches only the three fixed key names `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`ECS_ENGINE_AUTH_DATA`, not arbitrary secrets, so cfn-guard/OPA in CI carries the broad coverage — plus AWS Config) and require image signing in the pipeline. Add **VPC Flow Logs** on task subnets (assumed by IR; PCI Req 10) and **AWS WAF + Shield** on any internet-facing ALB

## Hardening Roadmap (30 / 60 / 90)

- **Days 1-30 (baseline, non-disruptive):** enable CloudTrail (if not already) + GuardDuty ECS Runtime Monitoring + ECR Enhanced Scanning + Security Hub (AWS FSBP + the ECS controls) + Container Insights. *Establish the baseline and the finding inventory.* **Caveat:** enabling Runtime Monitoring does **not** retroactively cover **already-running Fargate tasks** — the security sidecar is injected only at task start, so existing tasks stay uncovered until they are **restarted/redeployed** (plan a rolling redeploy). On a locked-down network, also allow the GuardDuty telemetry path (its VPC endpoint + the S3 managed prefix list) or coverage reports "Unhealthy."
- **Days 31-60 (identity + secrets):** split any over-broad shared role into least-privileged task role + execution role; add confused-deputy conditions to trust policies; scope `iam:PassRole`; migrate plaintext env-var secrets to Secrets Manager/SSM injection; lock down IMDS from tasks on EC2.
- **Days 61-90 (workload + network + image):** roll out `readonlyRootFilesystem`/non-root/`privileged:false`/dropped-capabilities (test first — read-only rootfs breaks apps that expect to write); move tasks to private subnets + VPC endpoints + SG-per-service; enable immutable tags + image signing; wire Audit Manager to the applicable framework and validate Security Hub against it.
- **Greenfield:** deploy the full 7-layer stack in the task definition and service at creation, not retrofitted.

## Top Guardrails (the high-cost mistakes)

- **Don't recommend a stack before confirming launch type** — the #1 ECS mistake; Fargate vs EC2 vs Managed Instances changes Layers 1, 3, 5, and 6.
- **Don't confuse the task role with the execution role.** The **execution role** grants the *ECS/Fargate agent* permission to pull images, write logs, and fetch secrets *at launch*; the **task role** vends credentials to *your application code at runtime*. Putting app permissions on the execution role (or ECR/secrets permissions only on the task role) is a classic misconfiguration.
- **Don't leave the "ECS was unable to assume the role" error unresolved by guessing** — it is almost always (a) a missing/incorrect trust policy (`Principal: ecs-tasks.amazonaws.com` + `sts:AssumeRole`), (b) a deleted/renamed role, or (c) an over-restrictive confused-deputy condition. See [identity-and-access.md](references/identity-and-access.md) and [re:Post: ECS unable to assume role](https://repost.aws/knowledge-center/ecs-unable-to-assume-role).
- **Don't forget the trailing colons in a secret ARN.** The full `valueFrom` syntax is `arn:aws:secretsmanager:region:acct:secret:name:json-key:version-stage:version-id`; the last three fields are optional **but if you omit them you must still include the colons** to select defaults. A single JSON key requires Fargate platform version **1.4.0+** (Linux) or EC2 agent **1.37.0+**. Source: [Pass Secrets Manager secrets via env vars](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html).
- **Don't claim GuardDuty Runtime Monitoring covers Managed Instances** — it covers Fargate and EC2 container instances; **Runtime Monitoring does not support ECS Managed Instances** (verified). Injected env-var secrets are also **not auto-rotated** — the container gets the value only at start; use SSM Parameter Store programmatic retrieval or force a new deployment to refresh.
- **Don't treat containers as a security boundary on EC2** — no task isolation there; a compromised container can reach co-located tasks' credentials, the instance role, and IMDS. Use Fargate for strict isolation, or lock down IMDS.
- **Don't promise "HIPAA-compliant"** — ECS/Fargate are HIPAA-*eligible*; a signed BAA is required and the customer owns workload-level controls.
- **Don't claim Fargate FIPS in commercial Regions** — Fargate FIPS 140-3 is **GovCloud (US) only** and must be explicitly enabled.
- **Watch ECS Express Mode's secure-by-default gaps.** Express Mode auto-creates the service, task definition, networking, and ALB, and defaults to **internet-facing** when given the default/public subnets (internal ALB only if you supply private subnets). The **infrastructure role is a required customer-supplied input** (`infrastructureRoleArn`, with the `AmazonECSInfrastructureRoleforExpressGatewayServices` managed policy), as is the execution role — only service-linked roles (ECS, ELB, Application Auto Scaling) are auto-created (verified 2026-07-10). If a workload is regulated or sensitive, drive it to **private subnets + internal ALB**, keep the infrastructure role you supply least-privileged, and layer the Layer 3-7 baseline on top — the fast path is not the hardened path. Source: [Resources created by ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-work.html).
- **Don't let the default log mode silently drop your audit evidence.** Since June 25, 2025 the ECS default log driver mode is **`non-blocking`** — under backpressure logs are **dropped silently**, fatal when logs are the compliance evidence. Set `mode: blocking` (or the account default) for audit-critical services and weigh the availability trade-off. See [audit-logging.md](references/audit-logging.md).
- **Don't conflate the `ssm` and `ssmmessages` VPC endpoints.** `ssm` serves Parameter Store retrieval; **ECS Exec needs `ssmmessages`** — `ssm` alone leaves Exec broken on private networks. See [network-isolation.md](references/network-isolation.md).
- **Don't synthesize compliance/crypto claims** — cite an AWS-published source or recommend escalation.

## Escalation

Create a SpecReq / escalate for: first-time certification on a mission-critical regulated workload; XXL+ segment; FedRAMP High / GovCloud; IL4/IL5; ECS Anywhere inside a compliance boundary (customer owns the on-prem host entirely); multi-tenant SaaS with cross-tenant PHI/cardholder/federal isolation on shared EC2 container instances; customer-vs-auditor disagreement on AWS-managed-control acceptability; or any claim you cannot ground. Full criteria: [references/engagement-and-response.md](references/engagement-and-response.md).

## How to Use the References

Progressive disclosure — the essentials are above; load a reference only when the task needs that depth:

| Reference | Load when the task is about… |
|-----------|------------------------------|
| [engagement-and-response.md](references/engagement-and-response.md) | Full discovery question set, adoption-challenge archetypes, response framework, escalation criteria |
| [shared-responsibility.md](references/shared-responsibility.md) | Layer 1 — Fargate vs EC2 vs Managed Instances vs Anywhere responsibility split; container-instance AMI hardening (AL2023/Bottlerocket); IMDS lockdown; patch cadence |
| [identity-and-access.md](references/identity-and-access.md) | Layer 2 — task vs execution vs instance vs infrastructure roles; the "unable to assume the role" error; confused-deputy trust (all-clusters wildcard); `iam:PassRole`; credential delivery; **ECS Exec governance**; operator-side/cluster-admin IAM (ABAC, MFA) |
| [task-container-hardening.md](references/task-container-hardening.md) | Layer 3 — `readonlyRootFilesystem`, non-root user, `privileged`, Linux capabilities, `dockerSecurityOptions`, distroless, CPU/memory limits, Security Hub ECS controls |
| [image-supply-chain.md](references/image-supply-chain.md) | Layer 4 — ECR Enhanced (Inspector) vs basic scanning, immutable tags, CMK-encrypted repos, AWS Signer + Notation signing, third-party scanners |
| [network-isolation.md](references/network-isolation.md) | Layer 5 — `awsvpc` mode, SG-per-task/service, private subnets, VPC endpoints (incl. `ssmmessages`/`kms` for Exec, ECS control-plane endpoints on EC2), VPC Flow Logs, WAF/Shield, multi-tenancy isolation, ingress via ALB/NLB, egress control |
| [runtime-security.md](references/runtime-security.md) | Layer 6 — GuardDuty ECS Runtime Monitoring (Fargate/EC2 coverage, the Managed-Instances exclusion), Extended Threat Detection, Security Hub, third-party CNAPP |
| [audit-logging.md](references/audit-logging.md) | Layer 7a — CloudTrail, Container Insights, `awslogs`/FireLens, log encryption + retention by regime |
| [compliance-accelerators.md](references/compliance-accelerators.md) | Layer 7b — Config rules for ECS, Security Hub ECS controls, Audit Manager, Artifact |
| [encryption-and-secrets.md](references/encryption-and-secrets.md) | Secrets Manager/SSM injection + the JSON-key syntax; at-rest/in-transit; EBS + ephemeral-storage encryption; Fargate FIPS |
| [compliance-regimes.md](references/compliance-regimes.md) | Per-regime scope (HIPAA/PCI/FedRAMP/GDPR/…), the verify-against-live-page discipline, worked scenarios |
| [incident-response-and-forensics.md](references/incident-response-and-forensics.md) | IR runbook for a compromised task/container, isolation, credential revocation, forensic capture |

## Sources

- [ECS Best Practices: Security](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html) · [Task & container security](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-tasks-containers.html) · [IAM roles best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)
- [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) · [re:Post — "ECS unable to assume role"](https://repost.aws/knowledge-center/ecs-unable-to-assume-role)
- [Pass sensitive data to a container](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html) · [Secrets via env vars (Secrets Manager)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html)
- [GuardDuty Runtime Monitoring](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html) · [How it works with ECS-Fargate](https://docs.aws.amazon.com/guardduty/latest/ug/how-runtime-monitoring-works-ecs-fargate.html) · [ECR Enhanced Scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html) · [Sign images in ECR (AWS Signer + Notation)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing.html)
- [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html) · [Fargate FIPS-140](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-fips-compliance.html) · [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [AWS Artifact](https://aws.amazon.com/artifact/)
