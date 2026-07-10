# ECS Deployment-Model Selection Framework

> **Part of:** [ecs-architect](../SKILL.md)
> **Purpose:** The full criteria matrix and per-model deep dives for choosing an Amazon ECS compute/launch model. Every GA-status, Region-availability, and pricing claim is cited to an AWS doc URL and was verified live against the AWS docs on **2026-07-09**. Re-verify fast-moving facts before asserting them to a customer.

---

## Table of Contents

1. [Criteria Matrix](#criteria-matrix)
2. [AWS Fargate](#aws-fargate)
3. [ECS on EC2](#ecs-on-ec2)
4. [ECS Managed Instances](#ecs-managed-instances)
5. [ECS Express Mode](#ecs-express-mode)
6. [ECS Anywhere (EXTERNAL)](#ecs-anywhere-external)
7. [Decision Walkthroughs](#decision-walkthroughs)
8. [Sources](#sources)

---

## Criteria Matrix

Score the workload against each criterion, then read the model that wins the most weighted criteria. No single criterion decides in isolation except the hard constraints (GPU, on-prem, Region).

| Criterion | Fargate | ECS on EC2 | Managed Instances | Express Mode | ECS Anywhere |
|-----------|---------|-----------|-------------------|--------------|--------------|
| **Infra ops overhead** | None | High (AMIs, patch, scale) | Low (AWS drain-and-replaces instances on a 14-21 day lifecycle) | None | High (you own the host) |
| **GPU / specialized HW** | No | Yes | Yes (GPU, network-optimized, burstable) | No | Depends on host |
| **Custom AMI / kernel / privileged** | No | Yes | Limited (AWS-controlled instances) | No | Yes |
| **Instance-type choice** | N/A | Full | Full (attributes or explicit types) | N/A | Your hardware |
| **Bin-packing density** | 1 task = 1 microVM | High (ENI trunking) | High (AWS optimizes placement) | Fargate-backed | Your capacity |
| **Spot / discount** | FARGATE_SPOT | EC2 Spot in ASG | Spot (`capacityOptionType: spot`) + Capacity Reservations (`reserved`) | Fargate pricing | N/A |
| **Speed to first deploy** | Fast | Slow | Medium | Fastest (URL out of the box) | Slow |
| **Fine-grained infra control** | Low | Highest | Medium | Lowest | High |
| **Air-gap / on-prem** | No | No | No | No | Yes |
| **Region breadth** | All | All | All commercial + GovCloud (US); **not** the China Regions | All | All (agent-based) |
| **Billing model** | Per-vCPU/GB/sec | Per EC2 instance | Per EC2 instance **+** management fee | Underlying resources | $0.01025 per managed instance-hour (capacity-independent) |

**Hard constraints that end the discussion early:**
- Need GPU → not Fargate, not Express Mode.
- On-prem / edge / another cloud → ECS Anywhere.
- China Regions → Managed Instances is unavailable there ([ECS Managed Instances FAQs](https://aws.amazon.com/ecs/managed-instances/faqs/)); choose Fargate or ECS on EC2. (GovCloud (US) *is* supported since Nov 2025 — [GovCloud availability](https://aws.amazon.com/about-aws/whats-new/2025/11/ecs-managed-instances-govcloud-us-regions/).)
- Need the Kubernetes API or cross-cloud portability → ECS is the wrong service; use EKS.

---

## AWS Fargate

Serverless compute for ECS: AWS runs each task in its own managed microVM. You specify only the task definition and its CPU/memory; there are no instances to provision, patch, or scale.

**Choose Fargate when:** the workload is a standard long-running service or batch job, traffic is spiky or density is low, and the team wants zero infrastructure operations. It is the default recommendation for most services.

**Do not choose Fargate when:**
- **GPU is required.** Fargate has **no GPU support** — this is a hard, frequently-restated constraint. GPU resource requirements are not available on Fargate resources ([Batch resource requirement — GPUs aren't available on Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)); GPU workloads must run on ECS on EC2 or Managed Instances (see `ecs-genai`).
- You need a custom AMI/kernel, privileged mode, host device access, or DaemonSet-style per-host tasks.
- You need ENI trunking-style density economics (Fargate is one ENI per task by design).

**Key facts:**
- **Platform versions.** Fargate exposes a Linux "platform version" (kernel + runtime). PV `1.4.0` is current. **PV 1.3.0 ends support June 30, 2026**; from **June 15, 2026** it is marked Retired (no new tasks/services on 1.3.0), and on June 30, 2026 remaining 1.3.0 tasks are terminated. Migrate to 1.4.0. ([Fargate Linux platform version deprecation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform-versions-retired.html))
- **Platform version revisions** are immutable and retired periodically (historically 1–2/month) for security/performance; long-running tasks are the ones that feel retirements. ([Fargate task retirement notifications](https://aws.amazon.com/blogs/containers/improving-operational-visibility-with-aws-fargate-task-retirement-notifications/))
- **SOCI lazy loading** (faster task starts) requires PV `1.4.0`; **SOCI Index Manifest v2 is now the standard** method (v1 still works but migrate) — see [best-practices-corpus.md](best-practices-corpus.md).
- **Migration gotcha — PV 1.3.0 → 1.4.0 shifts ECR/Secrets Manager/SSM traffic onto the task ENI (inside your VPC).** Previously that traffic flowed over the AWS-managed Fargate ENI; on 1.4.0 tasks that pull private ECR images or reference Secrets Manager/SSM secrets need a route to those endpoints (NAT or interface VPC endpoints for `ecr.dkr` **and** `ecr.api`, plus S3 gateway, Secrets Manager, SSM) and matching security-group rules — otherwise tasks fail to start after migration. Don't confuse this platform-version migration with routine same-PV task-retirement patching. ([Migrating to Linux PV 1.4.0](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform-version-migration.html) · [PV 1.4.0 launch — traffic-flow change](https://aws.amazon.com/blogs/containers/aws-fargate-launches-platform-version-1-4/))

---

## ECS on EC2

You register EC2 instances (via Auto Scaling groups) to the cluster and run tasks on them. You own the fleet: AMI selection, patching, scaling, and the ECS agent.

**Choose ECS on EC2 when:**
- **GPU** or other specialized hardware is required (GPU-optimized AMIs, g/p instance families).
- You need a **custom AMI or kernel**, privileged containers, host device/volume access, or specific instance families not otherwise reachable. **Caveat on privileged mode:** it is a significant security-posture decision, not a neutral capability — `ecs-security` treats `privileged: false` as the default and requires explicit justification to enable it. Route the decision there; needing privileged mode is a *reason it lands on EC2*, not an endorsement of turning it on.
- You want the **densest bin-packing** and are willing to run ENI trunking (see [networking-and-eni-density.md](networking-and-eni-density.md)).
- You have deep, steady utilization where per-instance economics (with Savings Plans/Spot/Graviton) beat per-task billing (quantify with `ecs-cost-intelligence`).

**Trade-off:** highest operational overhead — you are responsible for AMI currency, security patching, capacity, and agent health. If the only reason you're on EC2 is instance flexibility (not custom AMI/kernel), Managed Instances removes that ops burden.

---

## ECS Managed Instances

A fully managed compute option (GA) that runs EC2 instances in your account while AWS handles provisioning, configuration, workload placement, patching, scaling, and maintenance. You get EC2 instance-type flexibility (including **GPU-accelerated, network-optimized, and burstable** families) without owning the lifecycle.

**Status / availability (verify before quoting):**
- Announced **Sept 2025**; initially six Regions. ([Announcing Amazon ECS Managed Instances](https://aws.amazon.com/about-aws/whats-new/2025/09/amazon-ecs-managed-instances/))
- Extended to **all commercial AWS Regions Oct 2025**. ([Managed Instances now in all commercial Regions](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-managed-instances-commercial-regions/))
- Now in **AWS GovCloud (US-East / US-West) since Nov 2025** ([GovCloud availability](https://aws.amazon.com/about-aws/whats-new/2025/11/ecs-managed-instances-govcloud-us-regions/)). Separately, **from March 26, 2026** MI in the GovCloud (US) Regions supports **FIPS-certified workloads on Graviton-based and GPU-accelerated instances** (FIPS-compliant endpoints, kernel booted in FIPS mode) ([FIPS on Graviton/GPU in GovCloud](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-ecs-mi-supports-fips-graviron-gpu/)).
- **Not available in the China Regions.** ([ECS Managed Instances FAQs](https://aws.amazon.com/ecs/managed-instances/faqs/) — "all AWS Regions, except AWS GovCloud (US) and the China Regions"; note the FAQ text lags the GovCloud launch, so treat GovCloud as supported and re-verify.)

**How it works:**
- By default ECS selects the most cost-optimized instance types by grouping pending tasks; you can constrain by attributes (20+ available: vCPU, memory, and more) or specify explicit instance types in the **Managed Instances Capacity Provider** configuration. ([Announcing Amazon ECS Managed Instances — News Blog](https://aws.amazon.com/blogs/aws/announcing-amazon-ecs-managed-instances-for-containerized-applications/)) **Task placement strategies are not supported** — ECS places for you (best-effort AZ spread; launch-template/task-definition requirements and placement *constraints* apply). ([task placement](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement.html))
- **The OS is Bottlerocket, and only Bottlerocket** (Linux containers; X86_64 and ARM64) — directly relevant to the custom-AMI/kernel selection criterion: if the workload needs a specific AMI, kernel module, or Windows, MI is out. ([Architect for MI — operating system](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html))
- **Isolation:** by default MI **bin-packs multiple tasks per shared instance** ("Unlike Fargate, there is no task isolation" in that default mode); an optional **single-task mode** runs each task on its own dedicated instance for a VM-level isolation boundary equivalent to Fargate's default model — at a cost/startup-time trade-off. ([MI security — single-task mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-security.html) · [MI shared responsibility](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-shared-model-managed-instances.html))
- **Purchase options** via `capacityOptionType`: `on-demand` (default), `spot` (up to 90% off — added Dec 2025; interruptions carry the standard EC2 Spot **two-minute warning**), or `reserved` (EC2 Capacity Reservations — added Feb 2026). ([Managed Instances + Spot](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-ecs-managed-instances-ec2-spot-instances/) · [EC2 Spot interruption notices — two-minute warning](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html) · [Managed Instances + Capacity Reservations](https://aws.amazon.com/about-aws/whats-new/2026/02/ecs-mi-ec2-capacity-reservations/))
- AWS patches by **drain-and-replace on a standardized 14-21 day instance lifecycle**: ECS initiates graceful workload draining at **day 14** from instance launch and terminates the instance **no later than day 21**, rescheduling its tasks onto a freshly patched replacement (maximum instance lifetime: 21 days; early draining can occur for security vulnerabilities, hardware degradation, or configured event windows) ([Patching in ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html), verified 2026-07-10). This is both a security benefit and an operational side-effect — tasks *will* be cycled, so design for graceful draining and schedule the disruption with **EC2 event windows** (maintenance windows you configure). ([MI security / patching](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-security.html) · [Managed Instances launch post](https://aws.amazon.com/about-aws/whats-new/2025/09/amazon-ecs-managed-instances/))
- **`awsvpc` and `host` network modes only** — no `bridge` ([MI task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instance-networking.html)). AWS fully controls the instances: **no SSH access** to the host, an immutable root filesystem, SELinux, and no instance-role/root-volume changes ([MI security](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-security.html)). This is host-level lockdown only — **ECS Exec still works** to shell into your running tasks (it uses SSM Session Manager into the *container*, not the host). **ENI trunking is on by default** on supported instance types (unlike self-managed EC2, which needs an opt-in), so ENI-density planning is automatic here ([MI awsvpc mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-awsvpc-mode.html)).
- Enabled on new or existing clusters via Console, ECS MCP Server, or IaC. It is a **capacity-provider strategy**, so services using it must set `capacityProviderStrategy` (not a `launchType`). ([update-service CLI reference](https://docs.aws.amazon.com/cli/v1/reference/ecs/update-service.html))

**Pricing:** regular EC2 costs **plus** a per-instance management fee for the compute provisioned. At low task-per-instance density this can exceed Fargate per-task billing — Managed Instances wins at moderate-to-high density. Model TCO with `ecs-cost-intelligence`. ([Managed Instances FAQs](https://aws.amazon.com/ecs/managed-instances/faqs/))

**Choose Managed Instances when:** you want EC2 instance-type flexibility (including GPU) and Spot/Reserved capacity access, but do not want to operate the fleet. It is the recommended "modern workloads" target in `ecs-modernize`'s refactor path.

**Do not choose it when:** you're in the China Regions, you need `bridge` networking or a truly custom AMI/kernel (instances are AWS-controlled), or the management fee outweighs the ops savings for a small/low-density steady fleet.

---

## ECS Express Mode

An opinionated fast path (launched **Nov 2025**) that deploys a production-ready containerized web app/API from just a container image plus two IAM roles (task execution role + infrastructure role). ECS provisions and manages the cluster, Fargate task definition, Application Load Balancer, target groups, security groups, and autoscaling for you. ([Announcing Amazon ECS Express Mode](https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/))

**What you get:**
- An **AWS-provided domain name** and **HTTPS/TLS termination at the ALB with an AWS-managed ACM certificate** — no manual cert handling. ([Copilot end-of-support / Express Mode migration](https://aws.amazon.com/blogs/containers/announcing-the-end-of-support-for-the-aws-copilot-cli/))
- **Up to 25 Express Mode services behind one ALB** via rule-based routing — services stay isolated at the *task* level while sharing load-balancer cost, but the ALB itself is shared fate (listener-rule quotas, cert, SGs, availability blast radius). ([Announcing Amazon ECS Express Mode](https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/))
- Autoscaling on `AVERAGE_CPU`, `AVERAGE_MEMORY`, or `REQUEST_COUNT_PER_TARGET`; canary deployments managed for you.
- Available in **all Regions at no additional charge** — you pay only for the underlying resources. Deployable via the **ECS Console, AWS CLI, AWS SDKs, CloudFormation, Terraform, and the AWS Labs MCP Server for Amazon ECS** ([Express Mode overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)). CDK is not a first-class option in the docs — you can reach Express Mode from CDK only indirectly via a CloudFormation resource.

**API:** `aws ecs create-express-gateway-service`. You can pass a `primaryContainer` (image + port) for the simplest path, or your own `taskDefinition` for full task-level control (the task def must have a container named `Main` with a single TCP port mapping and `FARGATE` compatibility; `taskDefinitionArn` cannot be combined with `primaryContainer`/role/cpu/memory in the same call). ([Create your first Express Mode service (CLI)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html) · [create_express_gateway_service API](https://docs.aws.amazon.com/cli/latest/reference/ecs/create-express-gateway-service.html))

**Choose Express Mode when:** a team wants a web app/API online quickly with AWS best-practice defaults (HTTPS, autoscaling, shared ALB), and is happy to hand off infrastructure decisions. It is also the recommended migration path for **AWS Copilot CLI users — Copilot reaches end of support June 12, 2026** (migrate to Express Mode or CDK L3 constructs). ([Copilot end-of-support](https://aws.amazon.com/blogs/containers/announcing-the-end-of-support-for-the-aws-copilot-cli/))

**Do not choose it when:** you need fine-grained control over the ALB/network/task from day one, non-HTTP protocols (batch, gRPC, NLB-fronted services), or a model other than Fargate. Note the ALB is shared: Express Mode **consolidates up to 25 services onto one ALB when appropriate** ([launch announcement](https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/)). The exact behavior beyond 25 same-subnet services is not documented in a way we can cite — assume additional ALBs may be created and confirm/factor ALB cost into TCO for large service counts (hand $ modeling to `ecs-cost-intelligence`). Graduation is documented and by design a non-event: AWS states there is "no graduation path or break glass" *because* "the entire Amazon ECS feature set is always available for your Express Mode service" — you manage the provisioned resources directly with standard APIs, and "Express Mode will not overwrite changes unless requested as part of an Express Mode update." To fully detach, remove the Managed Tag on the resources (ECS can then no longer identify and operate on them as an Express Mode service) or use IAM to restrict access to the Express Mode APIs. ([Updating Resources Outside of Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-advanced-customization.html), verified 2026-07-10)

---

## ECS Anywhere (EXTERNAL)

ECS Anywhere registers an **external instance** — an on-prem server or VM (including other clouds) — to an ECS cluster using the `EXTERNAL` launch type. The ECS control plane stays in AWS; the host runs the ECS agent and the SSM agent. ([External (Amazon ECS Anywhere)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch-type-external.html))

**Choose ECS Anywhere when:** you need a consistent ECS control experience across hybrid infrastructure — modernizing/migrating legacy on-prem apps, edge data-processing, or running closer to end users for low latency. ([ECS clusters for external instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html))

**Key constraint:** external instances are **optimized for outbound / data-processing workloads**; there is **no Elastic Load Balancing support** for external instances, so inbound-heavy apps run less efficiently. ([launch-type-external](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch-type-external.html)) You still use the same ECS task definitions, APIs, IAM, CloudFormation, and ECR.

---

## Decision Walkthroughs

**"We have a Django web app, small team, want it live this week."**
→ Express Mode. It gives an HTTPS URL, ALB, and autoscaling from just the image. The full ECS feature set stays available on the provisioned resources, so "graduating" later is just managing them directly ([Updating Resources Outside of Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-advanced-customization.html)).

**"Batch inference on GPUs, bursty, a few hours a day."**
→ Not Fargate (no GPU). ECS on EC2 or Managed Instances with GPU instance types; use EC2 Capacity Blocks for scarce GPU capacity. Hand the workload design to `ecs-genai`.

**"Hundreds of steady microservices, cost-sensitive, willing to tune."**
→ ECS on EC2 with Graviton + Spot in a capacity-provider strategy, or Managed Instances if they want to shed fleet ops. Quantify with `ecs-cost-intelligence`; design capacity in [capacity-and-scaling.md](capacity-and-scaling.md).

**"Regulated workload in GovCloud (US)."**
→ All of Fargate, ECS on EC2, and Managed Instances are available in GovCloud (US) (Managed Instances since Nov 2025; FIPS-certified workloads on Graviton/GPU instances since March 26, 2026). Choose on the usual ops/control axis. In the **China Regions**, Managed Instances is not available — fall back to Fargate or ECS on EC2. Take hardening to `ecs-security`.

**"Legacy app on VMs in our own datacenter, can't move yet."**
→ ECS Anywhere (EXTERNAL) for a consistent control plane on-prem; plan the eventual cloud move with `ecs-modernize`.

---

## Sources

- [Amazon ECS FAQs](https://aws.amazon.com/ecs/faqs/) — Managed Instances Region availability, service-to-service options
- [Amazon ECS Managed Instances](https://aws.amazon.com/ecs/managed-instances/) · [FAQs](https://aws.amazon.com/ecs/managed-instances/faqs/)
- [Announcing Amazon ECS Managed Instances (Sept 2025)](https://aws.amazon.com/about-aws/whats-new/2025/09/amazon-ecs-managed-instances/) · [all commercial Regions (Oct 2025)](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-managed-instances-commercial-regions/) · [GovCloud (US) (Nov 2025)](https://aws.amazon.com/about-aws/whats-new/2025/11/ecs-managed-instances-govcloud-us-regions/)
- [Managed Instances + EC2 Spot (Dec 2025)](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-ecs-managed-instances-ec2-spot-instances/) · [Managed Instances + Capacity Reservations (Feb 2026)](https://aws.amazon.com/about-aws/whats-new/2026/02/ecs-mi-ec2-capacity-reservations/)
- [Announcing Amazon ECS Express Mode (Nov 2025)](https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/) · [Express Mode getting started (CLI)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html)
- [ECS task definition differences for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html) — Fargate no-GPU, SOCI, task sizing
- [Fargate Linux platform version deprecation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform-versions-retired.html) · [Migrating to Linux PV 1.4.0](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform-version-migration.html) · [PV 1.4.0 launch — traffic-flow change](https://aws.amazon.com/blogs/containers/aws-fargate-launches-platform-version-1-4/)
- [External (Amazon ECS Anywhere)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch-type-external.html) · [ECS clusters for external instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html)
- [Announcing the end-of-support for the AWS Copilot CLI](https://aws.amazon.com/blogs/containers/announcing-the-end-of-support-for-the-aws-copilot-cli/)
- [Amazon ECS Express Mode overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html) — deploy methods (Console/CLI/SDK/CFN/Terraform/MCP), shared ALB
- [Architect for Amazon ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html) · [MI security](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-security.html) · [MI task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instance-networking.html) · [MI awsvpc mode / trunking-by-default](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-awsvpc-mode.html)
- [MI FIPS on Graviton/GPU in GovCloud (US) (Mar 2026)](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-ecs-mi-supports-fips-graviron-gpu/)
- [Amazon ECS Anywhere pricing](https://aws.amazon.com/ecs/anywhere/pricing/) · [ECS Anywhere FAQs](https://aws.amazon.com/ecs/anywhere/faqs/) — $0.01025 per managed instance-hour
