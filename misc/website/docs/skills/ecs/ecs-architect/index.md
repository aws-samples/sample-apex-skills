---
title: "ecs-architect"
description: "Use when choosing and architecting an Amazon ECS deployment model for a new workload — Fargate vs ECS on EC2 vs ECS Managed Instances vs ECS Express Mode vs ECS Anywhere/External, capacity-provider strategy, task sizing, awsvpc/ENI density, networking, and service parameters — and when planning launch-type or topology migration (EC2 launch type → capacity providers / Managed Instances, Service Discovery → Service Connect). Triggers on \"which ECS launch type\", \"Fargate or EC2\", \"should I use Managed Instances\", \"ECS capacity provider strategy\", \"how do I size my ECS tasks\", \"Fargate vs Fargate Spot\", \"migrate off EC2 launch type\", \"Service Discovery to Service Connect\", \"App Mesh to Service Connect on ECS\", \"ECS on-prem\". Also the shared ECS best-practices knowledge corpus for design decisions. Skip for: existing-application replatform/refactor (use ecs-modernize); auditing or scoring a live estate (use ecs-operation-review); dollar-denominated cost/TCO analysis (use ecs-cost-intelligence); discovering what is already running (use ecs-recon); security/compliance hardening (use ecs-security); deployment strategy and CI/CD pipelines (use ecs-devops); observability stack selection (use ecs-observability); GPU/ML workload design (use ecs-genai); and Kubernetes/EKS (use eks-design)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-architect/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/SKILL.md). Edit the source, not this page.
:::


# Amazon ECS Deployment-Model Design and Selection

Choose the right Amazon ECS compute/launch model for a workload, architect the cluster + services around it, and plan the transition when a customer is moving off an older topology. This is the anchor ECS skill — the decision framework every other ECS skill leans on. It answers two coupled questions:

1. **Selection** — Which of Fargate, ECS on EC2, ECS Managed Instances, ECS Express Mode, or ECS Anywhere/External fits this workload, and what capacity-provider strategy backs it?
2. **Design + migration** — How is the task sized, how is the network laid out (awsvpc/ENI density), what service parameters are set, and — if an estate already exists — how does it move from EC2 launch type to capacity providers / Managed Instances, or from Service Discovery to Service Connect?

## When to Use

- Picking a compute model for a **new** containerized workload on ECS ("Fargate or EC2?", "should I use Managed Instances?", "is Express Mode right for this?").
- Designing a capacity-provider strategy (Fargate / FARGATE_SPOT / EC2 ASG / Managed Instances mixes) and base/weight ratios.
- Sizing tasks (CPU/memory combinations, ephemeral storage) and planning awsvpc ENI density on EC2.
- Choosing a networking model (awsvpc, task ENI, load-balancer placement) and core service parameters (min/max healthy percent, health-check grace period, placement).
- Planning a **launch-type or topology migration**: EC2 launch type → capacity providers or Managed Instances; Service Discovery (Cloud Map) → Service Connect.
- Answering "which model + how to architect it, by criteria" for hybrid/edge (ECS Anywhere) or air-gapped constraints.

## Don't Use

- **Existing application** you want to replatform or refactor onto ECS (assess app → replatform vs refactor → target design) — use `ecs-modernize`. This skill is greenfield model selection; `ecs-modernize` starts from an app and adds the assessment + replatform/refactor decision on top, then leans on this skill for the target design.
- **Auditing / scoring a live estate** GREEN/AMBER/RED across best-practices domains — use `ecs-operation-review` (Day-2 evaluative). This skill is Day-0 generative.
- **Dollar-denominated cost / TCO** analysis (Fargate vs EC2 vs Spot economics, Savings Plans, right-sizing with $ findings) — use `ecs-cost-intelligence`. This skill covers cost *posture* as a selection criterion, not quantified TCO.
- **Discovering what is already running** (inventory launch types, capacity providers, task defs) — use the `ecs-recon` skill once available (until then, inventory with `aws ecs list-*` / `describe-*`).
- **Security / compliance hardening** (task-role trust, secrets injection, GuardDuty, PCI/HIPAA/FedRAMP scope) — use `ecs-security`.
- **Deployment strategy + CI/CD** (rolling/blue-green/canary mechanics, circuit breaker, pipelines) — use `ecs-devops`. This skill names *which* deployment controller a model supports; `ecs-devops` designs the release process.
- **Observability stack** (FireLens vs awslogs, Container Insights vs Prometheus/ADOT vs 3rd-party) — use `ecs-observability`.
- **GPU / ML / inference workload** design — use `ecs-genai`. This skill states the Fargate-has-no-GPU boundary and routes GPU workloads to ECS on EC2 / Managed Instances; `ecs-genai` designs the GPU workload.
- **Kubernetes / EKS** — use `eks-design` / `eks-best-practices`. ECS is AWS-proprietary orchestration; if the customer needs the Kubernetes API or cross-cloud portability, ECS is the wrong service.

## How This Skill Works

This skill is **advisory and generative**. It produces recommendations, decision tables, ASCII/Mermaid architecture sketches, and migration plans — WHAT to build and WHY. It does not generate production IaC (that is deferred to a future `ecs-build`; today, point customers at Express Mode, the CDK `ecs-patterns` L3 constructs, or Terraform `terraform-aws-modules/terraform-aws-ecs`).

> **Tech-currency is mandatory.** The ECS surface moves fast — Managed Instances went GA Sept 2025 (six Regions), reached all commercial Regions Oct 2025 and **GovCloud (US) Nov 2025**, added **EC2 Spot Dec 2025** and **Capacity Reservations Feb 2026**; Express Mode launched Nov 2025; native blue/green launched July 2025; SOCI Index Manifest v2 became the standard July 2025; Fargate **PV 1.3.0 reaches end of support June 30, 2026** (Retired June 15, 2026); and the **AWS Copilot CLI reaches end of support June 12, 2026**. **Before asserting any GA status, Region availability, quota, or retirement date, verify it against the live AWS docs** (the reference files cite exact URLs). Never state a preview feature as GA, and name lifecycle status precisely.

## Discovery-Driven Decision Framework

Do not recommend a model before you have the answers to these. If the workload is an existing estate rather than greenfield, run a discovery/inventory pass first (the `ecs-recon` skill once available, or `aws ecs describe-*`), then return here.

| Dimension | Question | Why it steers the decision |
|-----------|----------|----------------------------|
| **Workload shape** | Long-running service, batch/scheduled, or event-driven? Steady or spiky? | Spiky/low-density → Fargate per-task billing. Steady/dense → EC2 or Managed Instances bin-packing. |
| **GPU / specialized hardware** | Needs GPU, Inferentia/Trainium, or Elastic Fabric Adapter? | **Fargate has no GPU** — GPU forces ECS on EC2 or Managed Instances. |
| **Ops-overhead tolerance** | Does the team want to manage EC2 (AMIs, patching, scaling) at all? | None → Fargate or Managed Instances. Willing → ECS on EC2 for full control. |
| **Control needs** | Custom AMI/kernel, privileged mode, host access, daemon workloads, specific instance families? | Full control → ECS on EC2. Instance-type choice without lifecycle ops → Managed Instances. |
| **Scale + density** | How many tasks, how tightly packed? IP-constrained VPC? | High density on EC2 needs ENI trunking planning; Fargate is 1 ENI per task. |
| **Cost posture** | Interruption-tolerant (Spot)? Committed spend (Savings Plans)? Graviton? | Spot/Graviton mix → capacity-provider strategy. Deep TCO → hand to `ecs-cost-intelligence`. |
| **Compliance / residency** | PCI/HIPAA/FedRAMP? Data residency, air-gap, on-prem? | On-prem/edge → ECS Anywhere (EXTERNAL). China Regions → **Managed Instances not available there** (GovCloud (US) *is* supported since Nov 2025, incl. FIPS on Graviton/GPU). |
| **Speed to first deploy** | Simple web app/API, want a URL fast, demo or internal tool? | Opinionated fast path → **Express Mode**. |
| **Team skill** | Container-native, or lifting a legacy app? | Legacy/minimal-change → EC2 launch type (or `ecs-modernize` replatform). |

### First-cut selection heuristic

```
Need Kubernetes API / cross-cloud portability?      -> Wrong service. Use EKS (eks-design).
Runs on-prem / edge / another cloud?                -> ECS Anywhere (EXTERNAL launch type).
Simple web app/API + want HTTPS URL fast?           -> ECS Express Mode (managed ALB + ACM + autoscaling).
Needs GPU / custom AMI / privileged / host access?  -> ECS on EC2  (Fargate has NO GPU).
Wants EC2 instance flexibility, zero lifecycle ops? -> ECS Managed Instances (AWS provisions + patches EC2).
Serverless, no instance management, standard sizes? -> AWS Fargate (default for most services).
```

Full criteria matrix, per-model deep dives, and the exact GA/Region/pricing facts (each cited): **[references/model-selection-framework.md](references/model-selection-framework)**.

## The Five Deployment Models (at a glance)

| Model | AWS manages | You manage | GPU | Best for | Not for |
|-------|-------------|------------|-----|----------|---------|
| **AWS Fargate** | Everything below the task | Task def, sizing | **No** | Most services, spiky/low-density, no-ops | GPU, custom AMI, host access |
| **ECS on EC2** | Control plane | EC2 fleet (AMI, patch, scale), agent | Yes | Full control, GPU, dense bin-packing, custom kernel | Teams that don't want EC2 ops |
| **ECS Managed Instances** | EC2 provisioning, patching (every 14 days), placement, scaling | Task def, instance-type constraints | Yes | EC2 flexibility (incl. GPU), Spot/Reserved capacity, without lifecycle ops | China Regions (not available; GovCloud (US) is supported) |
| **ECS Express Mode** | ALB, ACM cert, target groups, SGs, autoscaling, cluster | Container image + 2 IAM roles | No (Fargate-backed) | Fast-path web apps/APIs, demos, internal tools | Fine-grained infra control from day one |
| **ECS Anywhere (EXTERNAL)** | Control plane (in AWS) | On-prem/VM external instances, agents | Depends on host | Hybrid, edge, on-prem, data-processing/outbound | Inbound-heavy apps (no ELB support) |

Read the deep dive before recommending: **[references/model-selection-framework.md](references/model-selection-framework)**.

## Capacity-Provider Strategy

Capacity providers decouple *where tasks run* from *how the underlying capacity scales*. They apply to Fargate (`FARGATE`, `FARGATE_SPOT`), EC2 Auto Scaling groups (with managed scaling + managed termination protection), and Managed Instances.

Key correctness facts (verified — see reference for citations):

- **A task/service uses either a launch type OR a capacity-provider strategy, never both** in the same call.
- **Managed scaling with a mixed-instance-type ASG is supported but constrained**: ECS bin-packs against the *smallest* instance type in the ASG, so tasks whose resource requirements exceed the smallest instance stay stuck in `PROVISIONING`. Best practice: **one resource profile per ASG + capacity provider**, not one giant mixed ASG. (This is the precise form of the common "capacity providers don't support mixed ASGs" claim.)
- **FARGATE_SPOT** gives interruption-tolerant capacity at a discount; combine with a `FARGATE` base for resilience via `base`/`weight`. Managed Instances also supports Spot (`capacityOptionType: spot`, Dec 2025) and Capacity Reservations (`reserved`, Feb 2026).
- **Bin-pack on memory, not CPU**, on EC2/Managed Instances: CPU is a soft/burstable limit so overcommit is invisible, whereas memory is a hard limit and OOM-kills tasks — memory bin-packing gives a predictable, safe density guarantee.

Strategy design, base/weight math, scale-in edge cases, and the `CapacityProviderReservation` metric: **[references/capacity-and-scaling.md](references/capacity-and-scaling)**.

## Architecture Design

Once the model is chosen, design the task and service:

- **Task sizing** — valid Fargate CPU/memory combinations (0.25 vCPU up to 16 vCPU / 120 GB, and 32 vCPU with 60/120/244 GB on platform 1.4.0+), ephemeral storage, when to split into sidecars.
- **Networking** — `awsvpc` task ENIs, ENI density and trunking on EC2 (`awsvpcTrunking`), subnet/SG placement, load-balancer choice (ALB/NLB), Service Connect vs Service Discovery.
- **Service parameters** — deployment min/max healthy percent, health-check grace period, deployment controller choice, placement strategies/constraints.

Design deep dive: **[references/architecture-design.md](references/architecture-design)** · Networking + ENI density: **[references/networking-and-eni-density.md](references/networking-and-eni-density)**.

## Launch-Type and Topology Migration

Folded into this skill because "should I move off EC2 launch type?" is the same decision surface as "which model should I be on?".

- **EC2 launch type → capacity providers / Managed Instances** — how to transition, and the **immutability trap**: `launchType` cannot be changed on an existing service via update, so switching from a launch type to a capacity-provider strategy through CloudFormation/CDK **replaces** (deletes + recreates) the service unless you use the documented escape hatch. The `UpdateService` API does support specific launch-type ↔ capacity-provider transitions directly.
- **Service Discovery (Cloud Map DNS) → Service Connect** — why Service Connect is the recommended target, and how the cutover works (config changes apply at deployment, connection draining).

Migration playbook with exact supported transitions and citations: **[references/launch-type-migration.md](references/launch-type-migration)**.

## Shared ECS Best-Practices Corpus

The "what good looks like" knowledge that this skill, `ecs-operation-review`, and `ecs-cost-intelligence` all draw on — task-definition hygiene, image/SOCI, capacity correctness, deployment safety, health checks, and the shared-responsibility split per model. Factor-out to a standalone skill is deferred; it lives here as the single source of truth: **[references/best-practices-corpus.md](references/best-practices-corpus)**.

## Output Discipline

- **Recommend, then justify against the customer's stated criteria** — never lead with a model before the discovery table is answered.
- **Cite every GA/Region/quota/date claim** to an AWS doc URL (the references carry them). If you cannot verify a fast-moving claim live, say so explicitly rather than asserting it.
- **State constraints precisely**: "Fargate has no GPU", "Managed Instances is not available in the China Regions" (it *is* in GovCloud (US) since Nov 2025), "PV 1.3.0 reaches end of support June 30, 2026" — exact, not hand-wavy.
- Produce decision tables, an architecture sketch, a capacity-provider strategy, and (when migrating) a step-ordered transition plan. Hand off cost to `ecs-cost-intelligence`, security to `ecs-security`, deployment mechanics to `ecs-devops`.

## Detailed References

Progressive disclosure — essential guidance is above; load a reference when the task needs it:

- **[references/model-selection-framework.md](references/model-selection-framework)** — Read when choosing the compute/launch model. Full criteria matrix; per-model deep dives (Fargate, ECS on EC2, Managed Instances, Express Mode, ECS Anywhere) with GA/Region/pricing facts, each cited.
- **[references/capacity-and-scaling.md](references/capacity-and-scaling)** — Read when designing capacity-provider strategy or cluster auto scaling. Base/weight, managed scaling, mixed-ASG constraint, scale-in edge cases, Spot.
- **[references/networking-and-eni-density.md](references/networking-and-eni-density)** — Read when planning task networking. awsvpc, task ENIs, ENI trunking on EC2, subnet/SG design, ALB vs NLB, Service Connect vs Service Discovery.
- **[references/architecture-design.md](references/architecture-design)** — Read when sizing tasks and setting service parameters. Fargate CPU/memory table, ephemeral storage, deployment percentages, health-check grace period, placement.
- **[references/launch-type-migration.md](references/launch-type-migration)** — Read when moving off EC2 launch type or from Service Discovery to Service Connect. Supported transitions, the launchType-immutability trap, cutover steps.
- **[references/best-practices-corpus.md](references/best-practices-corpus)** — Read for the shared "what good looks like" knowledge. Task-def hygiene, images/SOCI, deployment safety, health, shared responsibility per model.

## Sources

- [Amazon ECS Developer Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/)
- [Amazon ECS Best Practices Guide](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [Amazon ECS FAQs](https://aws.amazon.com/ecs/faqs/)
