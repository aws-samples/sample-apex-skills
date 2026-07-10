# ECS Best-Practices Corpus (Shared Knowledge)

> **Part of:** [ecs-architect](../SKILL.md)
> **Purpose:** The shared "what good looks like" knowledge that `ecs-architect`, `ecs-operation-review`, and `ecs-cost-intelligence` all draw on. This is the shared **design baseline** for ECS fundamentals; a factor-out to a standalone `ecs-best-practices` skill is deferred. It is not the sole authority on any deep domain — security, cost, observability, and other sibling skills own the depth over their own areas and may carry their own, more detailed per-domain references; where they do, defer to them. Facts verified against the AWS ECS Best Practices Guide and Developer Guide on **2026-07-09**.
>
> **How to use:** In `ecs-architect` this informs design decisions — synthesize it into project-specific recommendations, don't paste it into deliverables. Deep audit/scoring of a live estate against these belongs to `ecs-operation-review`; dollar-quantified cost work to `ecs-cost-intelligence`.

---

## Table of Contents

1. [Shared Responsibility by Model](#shared-responsibility-by-model)
2. [Task-Definition Hygiene](#task-definition-hygiene)
3. [Container Images and SOCI](#container-images-and-soci)
4. [Capacity Correctness](#capacity-correctness)
5. [Deployment Safety](#deployment-safety)
6. [Health Checks and Draining](#health-checks-and-draining)
7. [Observability and Security Pointers](#observability-and-security-pointers)
8. [Sources](#sources)

---

## Shared Responsibility by Model

| Component | Fargate | ECS on EC2 | Managed Instances | ECS Anywhere (EXTERNAL) |
|-----------|---------|-----------|-------------------|-------------------------|
| Control plane | AWS | AWS | AWS | AWS (in-cloud) |
| Compute (provision/patch/scale) | AWS (no instances) | **You** | AWS (drain-and-replace, 14-21 day lifecycle) | **You** (own the physical/VM host) |
| ECS agent | AWS | **You** | AWS | **You** (install/run agent + SSM agent) |
| Host OS / AMI currency | AWS | **You** | AWS | **You** (+ physical security of the host) |
| Task definition + sizing | You | You | You | You |
| Application, IAM roles, secrets | You | You | You | You |

The further left, the less you operate. This table drives the ops-overhead criterion in [model-selection-framework.md](model-selection-framework.md). On **ECS Anywhere** you own the most — the host OS *and* its physical security — while AWS runs only the control plane. On **Managed Instances**, AWS patches by drain-and-replace on a **standardized 14-21 day instance lifecycle**: ECS initiates graceful draining at day 14 from launch and terminates the instance no later than day 21 (max lifetime 21 days), rescheduling its tasks onto a freshly patched replacement — a security benefit *and* an operational side-effect, so design for graceful draining and schedule the churn with EC2 event windows. ([Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html), verified 2026-07-10 · [Managed Instances launch post](https://aws.amazon.com/about-aws/whats-new/2025/09/amazon-ecs-managed-instances/))

---

## Task-Definition Hygiene

- **Task role vs execution role are different.** The **task execution role** lets the ECS agent pull images and write logs / fetch secrets at launch; the **task role** is the identity the *application* assumes at runtime. Confusing them is a top source of "unable to assume role" errors. Deep IAM trust guidance is in `ecs-security`.
- **Pin image tags to digests or immutable tags** — never rely on mutable `:latest` in production; it breaks reproducibility and rollbacks.
- **Set memory limits deliberately.** A hard `memory` limit too close to real usage causes OOM kills; use `memoryReservation` as the soft floor for placement. See [architecture-design.md](architecture-design.md#task-sizing-ec2--managed-instances).
- **Inject secrets, don't bake them** — reference Secrets Manager / SSM Parameter Store from the task definition (mechanics + least-privilege in `ecs-security`).
- **One concern per container**; use sidecars for logging/proxy, but keep the main app container sized as the primary consumer.
- **`stopTimeout`** — give containers enough time to shut down gracefully (important for Spot/interruption); default is short.

---

## Container Images and SOCI

- **SOCI (Seekable OCI)** lets Fargate lazily load large images so tasks start before the whole image downloads. Requires Fargate Linux **PV 1.4.0**; supports x86_64 and ARM64; not for Windows-on-Fargate. ([fargate-tasks-services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html))
- **SOCI Index Manifest v2 is the standard** as of **July 2025** — it uses a cryptographic link between image and index for deployment consistency. v1 still works but AWS strongly advises migrating; generate v2 with the `convert` subcommand of the `soci` CLI. ([Fargate supports SOCI Index Manifest v2](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-fargate-soci-index-manifest-v2-deployment-consistency/) · [Improving ECS deployment consistency with SOCI v2](https://aws.amazon.com/blogs/containers/improving-amazon-ecs-deployment-consistency-with-soci-index-manifest-v2/))
- **Selective SOCI:** you can index only large images in a task and let small sidecars download eagerly. ([Fargate selectively leverage SOCI](https://aws.amazon.com/about-aws/whats-new/2023/11/aws-fargate-amazon-ecs-tasks-selectively-leverage-soci/))
- Only use SOCI indexes from trusted sources — the index is authoritative for image contents.
- Prefer **Graviton (arm64)** images where the app supports it for price/performance (quantify with `ecs-cost-intelligence`).

---

## Capacity Correctness

- **One resource profile per ASG + capacity provider.** Managed scaling bin-packs against the *smallest* instance type in a mixed ASG; larger tasks hang in `PROVISIONING`. Full detail: [capacity-and-scaling.md](capacity-and-scaling.md#the-mixed-instance-type-asg-constraint).
- **Enable managed instance draining** (on by default) so tasks reschedule gracefully before an instance terminates.
- **Use task protection / scale-in protection** for critical tasks so scale-in doesn't kill them.
- **A service uses a launch type OR a capacity-provider strategy, never both.**

---

## Deployment Safety

- **Enable the deployment circuit breaker** with rollback so a bad deployment auto-reverts instead of leaving a half-failed service.
- **Tune min/max healthy percent** to your capacity headroom — 100/200 for zero-loss deploys if you can afford the spare capacity. See [architecture-design.md](architecture-design.md#service-parameters).
- **Native blue/green** (July 2025) consolidates blue/green into the ECS service with lifecycle hooks, bake time, and managed rollback — no CodeDeploy needed; works with ALB, NLB, and Service Connect. ([ECS built-in blue/green deployments — launch](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-ecs-built-in-blue-green-deployments/)) Strategy selection and pipeline design belong to `ecs-devops`.

---

## Health Checks and Draining

- **Set `healthCheckGracePeriodSeconds` longer than real cold-start** or slow-starting tasks get killed before they pass their first ELB check — a crash-loop footgun.
- **Enable ELB connection draining / deregistration delay** so in-flight requests complete before a task is removed.
- **Use container health checks** (task-def `healthCheck`) in addition to ELB checks for non-LB tasks.
- **Service Connect** adds automatic connection draining for east-west traffic during deployments. See [networking-and-eni-density.md](networking-and-eni-density.md#service-connect-vs-service-discovery).

---

## Observability and Security Pointers

These domains have dedicated skills — this corpus only flags the design-time defaults:

- **Observability:** enable CloudWatch Container Insights; choose `awslogs` vs FireLens for log routing. Full stack selection (Container Insights vs Prometheus/ADOT vs 3rd-party APM) → `ecs-observability`.
- **Security:** distinct least-privilege task/execution roles, secrets injection, SG-per-task, private subnets + VPC endpoints, GuardDuty ECS Runtime Monitoring, ECR image scanning. Full hardening + compliance scope → `ecs-security`.

---

## Sources

- [Amazon ECS Best Practices Guide](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [Amazon ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html) — SOCI, task sizing
- [AWS Fargate supports SOCI Index Manifest v2 (July 2025)](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-fargate-soci-index-manifest-v2-deployment-consistency/) · [Improving ECS deployment consistency with SOCI v2](https://aws.amazon.com/blogs/containers/improving-amazon-ecs-deployment-consistency-with-soci-index-manifest-v2/)
- [Fargate selectively leverage SOCI (Nov 2023)](https://aws.amazon.com/about-aws/whats-new/2023/11/aws-fargate-amazon-ecs-tasks-selectively-leverage-soci/)
- [Amazon ECS built-in blue/green deployments (July 2025)](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-ecs-built-in-blue-green-deployments/) · [Choosing between ECS Blue/Green Native or CodeDeploy (blog)](https://aws.amazon.com/blogs/devops/choosing-between-amazon-ecs-blue-green-native-or-aws-codedeploy-in-aws-cdk/)
- [Announcing Amazon ECS Managed Instances](https://aws.amazon.com/about-aws/whats-new/2025/09/amazon-ecs-managed-instances/) · [Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html) — 14-21 day drain-and-replace lifecycle
- [ECS clusters for external instances (ECS Anywhere)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html) — customer owns host OS + physical security
