---
name: ecs-operation-review
description: Run a structured Amazon ECS operational-excellence assessment against a live estate and score it GREEN/AMBER/RED. Skip for EKS/Kubernetes (use eks-operation-review). Covers 8 domains — clusters & capacity, networking, task definitions, services & deployment safety (circuit breaker, blue/green, canary), service health & autoscaling (grace period, draining, AZ rebalancing), observability, security posture, and operational processes — producing a rated report with prioritized actions. Activate for "audit my ECS estate", "ECS health check", "score my ECS posture", "review my ECS services", "GREEN/AMBER/RED my ECS clusters", including section-scoped reviews of a single domain. For Day-0 design/selection use ecs-architect; for deep security hardening use ecs-security; for cost/TCO use ecs-cost-intelligence; for observability design use ecs-observability; for CI/CD engineering use ecs-devops; for replatform/refactor use ecs-modernize; for read-only inventory/discovery use ecs-recon (siblings once available).
---

# ECS Operation Review

This skill performs a structured, evidence-based operational-excellence assessment of a **live** Amazon ECS estate — clusters, capacity providers, services, task definitions, and their supporting AWS resources — and produces a rated report (GREEN / AMBER / RED / UNKNOWN) with prioritized, cited recommendations.

It is the **umbrella Day-2 audit** that walks the major domains of the Amazon ECS Best Practices Guide ([`ecs-best-practices.html`](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)). It is evaluative (it *grades* what exists), not generative — it does not design or build new environments, and it **defers to the deep ECS skills** for remediation depth rather than duplicating them (see "Defers to deep skills").

**This skill is for Amazon ECS only. Skip it for EKS / Kubernetes estates — use `eks-operation-review` instead.**

### Scope & limitations (known blind spots)

This review is deliberately bounded. It does **not** currently assess, and should state as out-of-scope in the report:

- **Scheduled and standalone tasks** — the audit enumerates workloads via `list-services`; EventBridge-scheduled tasks and one-off `run-task` workloads are not examined.
- **ECS Express Mode** services — their ALB, security groups, and deployment config are auto-managed by AWS, so checks 2.2 / 4.x / 5.2 would mis-rate them. Mark N/A.
- **Windows and ECS Anywhere (`EXTERNAL`) workloads** — several container-hardening and runtime-monitoring checks (3.x, 7.3, 7.4) assume Linux on Fargate/EC2 and would false-RED Windows or external tasks. Note their presence and mark the affected items N/A.
- **API throttling on large estates** — when iterating over many services/task definitions, expect ECS API throttling; paginate and back off (see the pagination note in `references/operational-processes.md`).

State any of these that apply to the estate explicitly in the report's Scope block rather than silently omitting them.

## When to use

Activate for any request to **audit, review, health-check, or score** an ECS estate's operational posture:

- "Run an operational review on my ECS cluster / estate"
- "ECS health check", "score my ECS posture", "GREEN/AMBER/RED my services"
- "Review my ECS deployment safety / capacity / networking / observability / security posture"
- Section-scoped reviews of a single domain (e.g., "check my ECS capacity-provider scale-in", "review connection draining on my services", "audit my task-definition hygiene")

## Don't use for (route elsewhere)

| Request | Route to |
|---|---|
| "Which launch type should I use — Fargate vs EC2 vs Managed Instances?", greenfield architecture/design/selection | **`ecs-architect`** (Day-0 design; generative) |
| Read-only inventory / "what's in my estate" / discovery report before an audit | **`ecs-recon`** (discovery front door; until then inventory with `aws ecs describe-*`) |
| Deep security hardening, task/execution-role trust remediation, PCI/HIPAA/FedRAMP scoping | **`ecs-security`** |
| Dollar-quantified cost / TCO / Savings Plans / Spot / Graviton right-sizing | **`ecs-cost-intelligence`** |
| Designing the logs/metrics/traces stack (FireLens vs ADOT vs Datadog) | **`ecs-observability`** |
| Building deployment pipelines / choosing rollout strategy / CI-CD engineering | **`ecs-devops`** |
| Replatform vs refactor of an existing application | **`ecs-modernize`** |

The deep ECS sibling skills named above (`ecs-architect`, `ecs-recon`, `ecs-cost-intelligence`, `ecs-observability`, `ecs-devops`, `ecs-modernize`) are part of the ECS skill family and may be **rolled out over time**; route to them by name where relevant, and if one is not yet available, note that and fall back to the AWS CLI / this skill's audit-depth guidance. General container questions, one-off `aws ecs` commands, and cluster creation should be handled directly without this skill.

## Defers to deep skills

This review scores each domain at **audit depth** — enough to rate it and flag the top gaps — then hands off. When a finding warrants deeper work, name the sibling skill in the recommendation rather than reproducing its guidance here:

- **Security posture** findings (Section 07) → `ecs-security` for role-trust hardening, secrets, compliance scope.
- **Cost / capacity-efficiency** angles surfaced during the capacity review (Section 01) → `ecs-cost-intelligence` for $-denominated TCO.
- **Observability** findings (Section 06) → `ecs-observability` for stack design.
- **Deployment / release-engineering** findings (Section 04) → `ecs-devops` for pipeline and rollout-strategy design.

The review's own output is an assessment report. Acting on it (mutations, pipeline changes) is a separate, deliberate step the user chooses.

## Access model — READ-ONLY

This skill is strictly read-only. It **CAN** issue read-only calls (`aws ecs describe-*`/`list-*`, `application-autoscaling describe-*`, `autoscaling describe-*`, `cloudwatch describe-*`/`get-*`, `ec2 describe-*`, `ecr describe-*`, `iam get-*`/`list-*`, `elbv2 describe-*`, `logs describe-*`, `events list-*`, `backup list-*`, `guardduty list-*`/`get-*`, `service-quotas get-*`/`list-*`) to discover estate state, and **CAN** write a markdown/HTML report to the workspace. It **CANNOT** mutate any resource (no `create`, `update`, `delete`, `register`, `deregister`, `run-task`, or scale operations). Operational reviews are discovery activities; remediation belongs to whatever path the user chooses afterward.

## Prerequisites

- AWS credentials with ECS read access (and read access to CloudWatch, ECR, IAM, ELBv2, Application Auto Scaling, GuardDuty for full coverage). ReadOnly/least-privilege credentials are preferred.
- AWS CLI v2 configured with a default Region (`aws configure get region`).
- Python 3.10+ for the optional HTML report conversion.
- **Optional:** the Amazon ECS MCP server (preview) for richer live-estate inspection. If configured, its read tools may be used; the skill works fully with the AWS CLI alone. See [ECS MCP server docs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-mcp-introduction.html). The ECS MCP server is in **preview** and subject to change — do not depend on it; the AWS CLI is the reliable primary path.

## Tool usage rules (invariants)

1. **Do NOT call any tools when this skill is first activated.** Wait for the user to explicitly ask for a review.
2. **Do NOT hardcode or guess cluster/service names.** Always discover them by listing first.
3. **Do NOT read config files as a connectivity "check".** Verify access by making one real read call.
4. **Do NOT retry a failed call more than once.** If it fails twice, mark the affected items UNKNOWN with the failure reason and continue.
5. **Always load the relevant `references/` file before executing that section's checks.**
6. **Never mutate.** Only `describe`/`list`/`get` verbs. If a check would require a write, mark UNKNOWN and note it for manual investigation.
7. **Only rate on observed evidence.** If a check returns no data, mark UNKNOWN — never assume.

## Methodology

### Step 0 — Pre-flight

**Action 1 — List clusters.**
```
aws ecs list-clusters --output json
```
- Success → show the list. If one cluster, confirm: "I found one cluster: <name>. Assess this one?" If many, ask which cluster(s) or whether to assess the whole estate.
- Failure → STOP (do not retry more than once). Show:
  > **Cannot list ECS clusters.** Check: (1) `aws sts get-caller-identity`, (2) `aws configure get region`, (3) that the credentials have `ecs:ListClusters`.

**Action 2 — Describe the selected cluster(s).**
```
aws ecs describe-clusters --clusters <name> --include SETTINGS CONFIGURATIONS TAGS STATISTICS ATTACHMENTS --output json
```
Show: cluster name, Region, account ID, status, registered capacity providers, default capacity-provider strategy, `containerInsights` setting, running/pending task counts, and tags.

**Action 3 — Enumerate services and capacity providers (verifies read access).**
```
aws ecs list-services --cluster <name> --output json
aws ecs describe-capacity-providers --output json
```
- Success → proceed. Failure → mark the affected sections UNKNOWN and continue.

**Action 4 — Confirm.** Ask: *"Ready to start the operational review on <cluster> (<N> services)?"* Proceed only after the user confirms.

### Steps 1–8 — Run the assessment

For each domain, in section order, **read the corresponding `references/` file first**, then execute its checks and rate each item with the rubric below. If a whole section fails (permissions, timeouts), mark all its items UNKNOWN with a note and continue — one failed section must not block the rest.

| # | Section | Reference file |
|---|---------|----------------|
| 01 | Clusters & Capacity (scale-in correctness, Managed Instances, capacity-provider strategy) | `references/cluster-capacity.md` |
| 02 | Networking (awsvpc, ENI/SG-per-task, subnet IP capacity, VPC endpoints, Service Connect) | `references/networking.md` |
| 03 | Task Definitions (task size, images, volumes, log config, task/execution roles referenced) | `references/task-definitions.md` |
| 04 | Services & Deployment Safety (circuit breaker + rollback, native blue/green, canary/linear, min/max healthy %) | `references/services-deployment.md` |
| 05 | Service Health & Autoscaling (health-check grace period, LB health check, connection draining, service auto scaling, AZ rebalancing, placement) | `references/service-health-scaling.md` |
| 06 | Observability (Container Insights enhanced, FireLens/awslogs, retention, alerting, tracing) | `references/observability.md` |
| 07 | Security Posture (role trust & least privilege, secrets, container hardening, GuardDuty, ECR scanning) | `references/security-posture.md` |
| 08 | Operational Processes (IaC provenance/tagging, DR/backup, runbooks, on-call, Fargate task retirement) | `references/operational-processes.md` |

**Section-scoped requests** load only the matching file(s) and produce a focused report.

### Step 9 — Generate the report

Read `references/report-generation.md` and follow it exactly. See `references/scoring-rubric.md` for the full rating rules and the mandatory consistency contract.

## Rating rubric (summary)

| Rating | Meaning |
|--------|---------|
| 🟢 GREEN | Fully implemented — matches ECS best practices |
| 🟡 AMBER | Partial or inconsistent — improvement opportunity |
| 🔴 RED | Not implemented or significant gap — action needed |
| ⬜ UNKNOWN | Cannot be determined from estate data — investigate manually |

Prioritize by blast radius: **security > availability > cost**. Every RED must carry a specific, cited, actionable recommendation. Full rules: `references/scoring-rubric.md`.
