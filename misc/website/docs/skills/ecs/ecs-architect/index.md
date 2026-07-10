---
title: "ecs-architect"
description: "Use when choosing and architecting an Amazon ECS deployment model for a NEW workload — Fargate vs ECS on EC2 vs Managed Instances vs Express Mode vs ECS Anywhere/External — plus capacity-provider strategy, task sizing, awsvpc/ENI density, networking, service parameters, and launch-type or topology migration (EC2 launch type to capacity providers/Managed Instances; Service Discovery to Service Connect). Also the shared ECS best-practices corpus. Triggers include \"which ECS launch type\", \"Fargate or EC2\", \"should I use Managed Instances\", \"ECS capacity provider strategy\", \"how to size ECS tasks\", \"migrate off EC2 launch type\", \"App Mesh to Service Connect\", \"ECS on-prem\". Skip for existing-app replatform (ecs-modernize); auditing a live estate (ecs-operation-review); cost/TCO (ecs-cost-intelligence); inventory (ecs-recon); security (ecs-security); deployment/CICD (ecs-devops); observability (ecs-observability); GPU/ML design AND GPU launch-type choice (ecs-genai); Kubernetes/EKS (eks-design)."
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

- **Existing application** you want to replatform or refactor onto ECS (assess app → replatform vs refactor → target design) — use the `ecs-modernize` skill once available. This skill is greenfield model selection; `ecs-modernize` starts from an app and adds the assessment + replatform/refactor decision on top, then leans on this skill for the target design.
- **Auditing / scoring a live estate** GREEN/AMBER/RED across best-practices domains — use the `ecs-operation-review` skill once available (Day-2 evaluative). This skill is Day-0 generative.
- **Dollar-denominated cost / TCO** analysis (Fargate vs EC2 vs Spot economics, Savings Plans, right-sizing with $ findings) — use the `ecs-cost-intelligence` skill once available. This skill covers cost *posture* as a selection criterion, not quantified TCO.
- **Discovering what is already running** (inventory launch types, capacity providers, task defs) — use the `ecs-recon` skill once available (until then, inventory with `aws ecs list-*` / `describe-*`).
- **Security / compliance hardening** (task-role trust, secrets injection, GuardDuty, PCI/HIPAA/FedRAMP scope) — use `ecs-security`.
- **Deployment strategy + CI/CD** (rolling/blue-green/canary mechanics, circuit breaker, pipelines) — use the `ecs-devops` skill once available. This skill names *which* deployment controller a model supports; `ecs-devops` designs the release process.
- **Observability stack** (FireLens vs awslogs, Container Insights vs Prometheus/ADOT vs 3rd-party) — use the `ecs-observability` skill once available.
- **GPU / ML / inference workload** design — use `ecs-genai`. This skill states only the Fargate-has-no-GPU boundary; **the GPU launch-type choice itself (EC2 vs Managed Instances, instance families, Capacity Blocks) and the workload design are `ecs-genai`'s** — defer "which ECS launch type for GPU" there.
- **App Runner** ("should I use App Runner instead?", App Runner→ECS migration) — App Runner is moving to maintenance (no new customers as of April 30, 2026); route App Runner selection and migration to the `aws-containers` skill.
- **Kubernetes / EKS** — use `eks-design` / `eks-best-practices`. ECS is AWS-proprietary orchestration; if the customer needs the Kubernetes API or cross-cloud portability, ECS is the wrong service.

## How This Skill Works

This skill is **advisory and generative**. It produces recommendations, decision tables, ASCII/Mermaid architecture sketches, and migration plans — WHAT to build and WHY. It does not generate production IaC (that is deferred to a future `ecs-build`; today, point customers at Express Mode, the CDK `ecs-patterns` L3 constructs, or Terraform `terraform-aws-modules/terraform-aws-ecs`).

> **Tech-currency is mandatory.** The ECS surface moves fast (e.g. Managed Instances went GA Sept 2025 and keeps adding purchase options; Express Mode and native blue/green are both recent; Fargate PV 1.3.0 and the AWS Copilot CLI both hit end of support in 2026). **The full, dated fact list — GA status, Region availability, purchase-option and lifecycle dates, each with its exact AWS URL — is maintained in the reference files, not here, to avoid drift. Before asserting any such claim, read the relevant reference and re-verify it against the live AWS docs.** Never state a preview feature as GA, and name lifecycle status precisely.

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
| **ECS Managed Instances** | EC2 provisioning, patching (drain from day 14, replace by day 21), placement, scaling | Task def, instance-type constraints | Yes | EC2 flexibility (incl. GPU), Spot/Reserved capacity, without lifecycle ops | China Regions (not available; GovCloud (US) is supported) |
| **ECS Express Mode** | ALB, ACM cert, target groups, SGs, autoscaling, cluster | Container image + 2 IAM roles | No (Fargate-backed) | Fast-path web apps/APIs, demos, internal tools | Fine-grained infra control from day one |
| **ECS Anywhere (EXTERNAL)** | Control plane (in AWS) | On-prem/VM external instances, agents | Depends on host | Hybrid, edge, on-prem, data-processing/outbound | Inbound-heavy apps (no ELB support) |

**Isolation is also a security selection criterion.** Fargate runs one task per microVM, so a container escape is contained to a single task. Managed Instances **by default bin-packs multiple tasks onto a shared instance — the docs state plainly there is no task isolation in that default mode**; its optional **single-task mode** places each task on its own dedicated instance for a VM-level isolation boundary equivalent to Fargate's default model. ECS on EC2 with dense bin-packing likewise shares one kernel across many tasks, widening the container-escape blast radius. For multi-tenant or regulated workloads this can favor Fargate (or MI single-task mode) over shared-instance density regardless of cost — take the hardening decision to `ecs-security`. ([MI security — single-task mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-security.html) · [MI shared responsibility — no task isolation by default](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-shared-model-managed-instances.html))

Read the deep dive before recommending: **[references/model-selection-framework.md](references/model-selection-framework)**.

## Capacity-Provider Strategy

Capacity providers decouple *where tasks run* from *how the underlying capacity scales*. They apply to Fargate (`FARGATE`, `FARGATE_SPOT`), EC2 Auto Scaling groups (with managed scaling + managed termination protection), and Managed Instances.

Key correctness facts (verified — see reference for citations):

- **A task/service uses either a launch type OR a capacity-provider strategy, never both** in the same call.
- **Managed scaling with a mixed-instance-type ASG is supported but constrained**: ECS bin-packs against the *smallest* instance type in the ASG, so tasks whose resource requirements exceed the smallest instance stay stuck in `PROVISIONING`. Best practice: **one resource profile per ASG + capacity provider**, not one giant mixed ASG. (This is the precise form of the common "capacity providers don't support mixed ASGs" claim.)
- **FARGATE_SPOT** gives interruption-tolerant capacity at a discount; combine with a `FARGATE` base for resilience via `base`/`weight`. Managed Instances also supports Spot (`capacityOptionType: spot`, Dec 2025) and Capacity Reservations (`reserved`, Feb 2026).
- **Bin-pack on memory, not CPU**, on EC2 (field heuristic): container-level `cpu` is a *soft* share (containers burst into unused CPU, so overcommit is invisible), whereas the container `memory` hard limit OOM-kills on breach. Note that task-level `cpu` *is* a hard ceiling for the whole task — the softness is at the container-share level. Memory bin-packing gives a predictable, safe density guarantee. The `binpack`/`spread` strategy configuration applies to **EC2/ASG capacity only — Managed Instances does not support task placement strategies** (it places for you: best-effort AZ spread, driven by launch-template/task requirements and placement *constraints*). ([task definition CPU/memory](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) · [task placement](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement.html))

Strategy design, base/weight math, scale-in edge cases, and the `CapacityProviderReservation` metric: **[references/capacity-and-scaling.md](references/capacity-and-scaling)**.

## Architecture Design

Once the model is chosen, design the task and service:

- **Task sizing** — valid Fargate CPU/memory combinations (0.25 vCPU up to 16 vCPU / 120 GB, and 32 vCPU with 60/120/244 GB on platform 1.4.0+), ephemeral storage, when to split into sidecars.
- **Networking** — `awsvpc` task ENIs, ENI density and trunking on EC2 (`awsvpcTrunking`), subnet/SG placement, load-balancer choice (ALB/NLB), Service Connect vs Service Discovery.
- **Service parameters** — deployment min/max healthy percent, health-check grace period, deployment controller choice, placement strategies/constraints (strategies are EC2-only; Fargate and Managed Instances place for you).

Design deep dive: **[references/architecture-design.md](references/architecture-design)** · Networking + ENI density: **[references/networking-and-eni-density.md](references/networking-and-eni-density)**.

## Launch-Type and Topology Migration

Folded into this skill because "should I move off EC2 launch type?" is the same decision surface as "which model should I be on?".

- **EC2 launch type → capacity providers / Managed Instances** — how to transition, and the **immutability trap**: `launchType` cannot be changed on an existing service via update, so switching from a launch type to a capacity-provider strategy through CloudFormation/CDK **replaces** (deletes + recreates) the service unless you use the documented escape hatch. The `UpdateService` API does support launch-type → capacity-provider transitions directly (the reverse is mostly unsupported — you can only revert to the launch type the service was *originally* created with; see reference).
- **Service Discovery (Cloud Map DNS) → Service Connect** — why Service Connect is the recommended target, and how the cutover works (config changes apply at deployment, connection draining).

Migration playbook with exact supported transitions and citations: **[references/launch-type-migration.md](references/launch-type-migration)**.

## Shared ECS Best-Practices Corpus

The "what good looks like" knowledge that this skill, `ecs-operation-review`, and `ecs-cost-intelligence` all draw on — task-definition hygiene, image/SOCI, capacity correctness, deployment safety, health checks, and the shared-responsibility split per model. Factor-out to a standalone skill is deferred; it lives here as the *shared design baseline* — deep domains (security, cost, observability) own the depth in their own references: **[references/best-practices-corpus.md](references/best-practices-corpus)**.

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
