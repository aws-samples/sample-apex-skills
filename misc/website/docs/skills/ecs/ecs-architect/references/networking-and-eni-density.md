---
title: "ECS Networking and ENI Density"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/references/networking-and-eni-density.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-architect/references/networking-and-eni-density.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-architect/references/networking-and-eni-density.md). Edit the source, not this page.
:::

# ECS Networking and ENI Density

> **Part of:** [ecs-architect](../)
> **Purpose:** Design task networking for ECS — `awsvpc` task ENIs, ENI density and trunking on EC2, subnet/SG placement, load-balancer choice, and Service Connect vs Service Discovery. Facts verified against AWS docs on **2026-07-09**.

---

## Table of Contents

1. [Network Modes](#network-modes)
2. [awsvpc Task ENIs](#awsvpc-task-enis)
3. [ENI Density and Trunking on EC2](#eni-density-and-trunking-on-ec2)
4. [Subnet and Security-Group Design](#subnet-and-security-group-design)
5. [Load Balancer Selection](#load-balancer-selection)
6. [Service Connect vs Service Discovery](#service-connect-vs-service-discovery)
7. [VPC Lattice (cross-account / cross-VPC east-west)](#vpc-lattice-cross-account--cross-vpc-east-west)
8. [Sources](#sources)

---

## Network Modes

| Mode | Where it applies | Notes |
|------|------------------|-------|
| **`awsvpc`** | Fargate (required), EC2, Managed Instances | Each task gets its own ENI, its own private IP, and its own security group. Recommended for security and observability. **Not available on ECS Anywhere (`EXTERNAL`).** |
| **`bridge`** | EC2, **ECS Anywhere (`EXTERNAL`)** | Docker's built-in virtual network; dynamic port mapping. Legacy. |
| **`host`** | EC2, **ECS Anywhere (`EXTERNAL`)** | Task binds directly to the host's network. No per-task isolation. |
| **`none`** | EC2, **ECS Anywhere (`EXTERNAL`)** | No external connectivity. |

**Default recommendation: `awsvpc`.** It gives each task EC2-like networking — security groups, VPC Flow Logs, and granular monitoring per task — and is mandatory on Fargate. ([Allocate a network interface for an Amazon ECS task](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html))

> **ECS Anywhere (`EXTERNAL`) caveat.** External-instance Linux tasks must use **`bridge`, `host`, or `none` — `awsvpc` is not supported** ([ECS clusters for external instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html)). Because `awsvpc` is unavailable on external instances, you get **no per-task ENI and no security-group-per-task** there, and the per-task isolation/observability benefits below do not apply.

---

## awsvpc Task ENIs

With `awsvpc`, ECS creates one ENI per task, attaches it to the host with the task's security group, and assigns a private IPv4 address (plus IPv6 in a dual-stack subnet). **Each task can only have one ENI.** These ENIs are ECS-managed — visible in the EC2 console but you can't detach or modify them; they're deleted when the task stops or the service scales in. ([task-networking-awsvpc](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html))

**Consequence for IP planning:** every task consumes a VPC IP. In IP-constrained VPCs, high task counts can exhaust subnets — size subnets for peak task count, not just instance count.

---

## ENI Density and Trunking on EC2

On EC2, the biggest disadvantage of `awsvpc` is that EC2 instances cap how many ENIs can attach, which caps tasks per instance. By default a `c5.large` supports 3 ENIs; the primary counts as one, leaving 2 — so **only ~2 awsvpc tasks per `c5.large`**. ([container-instance-eni](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html))

**ENI trunking** raises this. Turn on the **`awsvpcTrunking` account setting** and ECS attaches a managed "trunk" ENI to newly-launched (supported) instances. A `c5.large` with trunking has an ENI limit of **12**, so it can run **10 tasks instead of 2** — roughly a 5x density gain. ([container-instance-eni](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html)) The frequently-cited claim that trunking adds **no latency or bandwidth penalty** is **blog-sourced** (AWS Compute Blog), not a hard doc guarantee — treat it as a strong indication rather than an SLA, and load-test if latency is critical. ([Optimizing ECS task density using awsvpc — blog](https://aws.amazon.com/blogs/compute/optimizing-amazon-ecs-task-density-using-awsvpc-network-mode/))

**Design notes:**
- `awsvpcTrunking` is **not available on Fargate** (Fargate is one task = one microVM anyway). ([container-instance-eni](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html))
- On **self-managed ECS on EC2, trunking is an explicit opt-in** (account setting) — a commonly-missed step that leaves the bulk of a Fargate→EC2 migration's density unrealized. On **ECS Managed Instances, ENI trunking is on by default**, so density planning is automatic there.
- Trunking uses two ENI attachments by default (the instance's primary ENI plus the ECS-managed trunk ENI). Density scales with instance size on supported types — e.g. larger Graviton instances host many tens of tasks. Check the supported-instance-type list before assuming a density number.
- The trunk ENI is fully managed by ECS and deleted on instance termination/deregistration.
- Trunking must be enabled **before** launching the instances that should benefit — it applies to newly-launched instances.
- Denser bin-packing via trunking improves cost efficiency for tasks that don't hit CPU/memory limits; quantify with `ecs-cost-intelligence`.

---

## Subnet and Security-Group Design

- **Private subnets for tasks**, public subnets for internet-facing load balancers. Tasks reach the internet via NAT or, better for cost, VPC endpoints for AWS services (ECR, S3, CloudWatch Logs, Secrets Manager).
- **Security group per task** (`awsvpc`) — apply least-privilege SGs at task granularity rather than one broad host SG. Detailed SG/least-privilege hardening belongs to `ecs-security`.
- **VPC endpoints** eliminate NAT data-processing cost for pulls/logs/secrets and keep traffic private; strongly recommended for private clusters.

---

## Load Balancer Selection

| Load balancer | Best for | Notes |
|---------------|----------|-------|
| **ALB** | HTTP/HTTPS web apps and APIs, path/host routing, WebSockets | Native TLS termination, WAF, Cognito auth. Express Mode uses ALB with an AWS-managed ACM cert. |
| **NLB** | TCP/UDP, ultra-low latency, static IPs, gRPC | UDP to Fargate requires platform version 1.4+ ([Architect for Fargate — service load balancing](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)). |
| **None (Service Connect)** | Service-to-service traffic inside/across clusters | No LB needed for east-west; see below. |

External instances (ECS Anywhere) have **no ELB support** — factor this into inbound-traffic designs. ([launch-type-external](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch-type-external.html))

---

## Service Connect vs Service Discovery

Both solve service-to-service connectivity without a load balancer. **Service Connect is the recommended choice** for new designs. ([Interconnect Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html))

| | **Service Connect** (recommended) | **Service Discovery** (Cloud Map) |
|--|-----------------------------------|-----------------------------------|
| **Mechanism** | ECS-managed proxy (Envoy) sidecar in each task; logical short names + standard ports | AWS Cloud Map DNS records per task |
| **Scope** | Same cluster, other clusters, across VPCs in the same Region | DNS-resolvable endpoints |
| **Telemetry** | Rich traffic telemetry in the ECS console and CloudWatch | None built-in |
| **Deployment safety** | Config changes apply **at deployment**; automatic **connection draining** lets clients cut over to a new endpoint version without traffic errors | DNS TTL means clients may keep hitting old IPs until TTL expires — a classic migration pain |
| **Resource cost** | **Adds a managed proxy sidecar that consumes task CPU/memory** — AWS recommends budgeting +256 CPU units and ≥64 MiB (more at high RPS/large namespaces); requires a task-level memory limit ([Service Connect components](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html)) | No sidecar; near-zero task overhead |
| **Change model** | **Config changes take effect only via a new deployment** (replaces tasks) — no live reconfig | DNS records update without redeploying tasks |
| **Network-mode support** | `awsvpc` and `bridge` only — **not `host`, and not ECS Anywhere/`EXTERNAL`** ([Interconnect ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html)) | `awsvpc`, `bridge`, `host` |
| **App changes** | Usually none if the app already uses DNS names | None |

Why Service Connect wins: with DNS-based discovery, changing a name to new IPs waits out the max TTL before all clients switch. Service Connect updates config by replacing client tasks during a normal deployment, so you control the cutover with the deployment circuit breaker and other deployment settings. ([Networking between ECS services in a VPC](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-connecting-services.html))

**Coming off App Mesh?** AWS App Mesh is discontinued **September 30, 2026** (confirmed in the App Mesh doc-history end-of-support notice; no new-customer onboarding since September 24, 2024). Service Connect is the recommended ECS target (managed data plane, no self-managed Envoy sidecars, built-in retries/outlier detection and CloudWatch metrics). Migrate per service, running both in parallel during cutover. The commonly-cited **Service Connect gaps vs App Mesh — no fine-grained retry/circuit-breaker tuning, weighted A/B traffic splits, or cross-account sharing — are blog-sourced** (the AWS App-Mesh→Service-Connect migration blog), not an authoritative feature matrix; verify against current docs before relying on any specific gap. Where you need cross-account/traffic-split, VPC Lattice (below) is the doc-backed answer. ([App Mesh EOL — doc history](https://docs.aws.amazon.com/app-mesh/latest/userguide/doc-history.html) · [Migrating from AWS App Mesh to Amazon ECS Service Connect — blog](https://aws.amazon.com/blogs/containers/migrating-from-aws-app-mesh-to-amazon-ecs-service-connect/))

Migration from Service Discovery → Service Connect is covered in [launch-type-migration.md](launch-type-migration).

---

## VPC Lattice (cross-account / cross-VPC east-west)

Amazon VPC Lattice has **built-in Amazon ECS support**: an ECS service can be associated directly with a VPC Lattice target group, and ECS auto-registers/deregisters task IPs as targets and replaces tasks that fail VPC Lattice health checks — **no intermediate load balancer required**. ([Use VPC Lattice with ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-vpc-lattice.html) · [ECS + VPC Lattice launch](https://aws.amazon.com/blogs/aws/streamline-container-application-networking-with-native-amazon-ecs-support-in-amazon-vpc-lattice/))

**When VPC Lattice over Service Connect:** VPC Lattice answers Service Connect's gaps — it connects services **across accounts** (shared via AWS RAM), across VPCs, and supports **weighted/blue-green/canary traffic splitting** and IAM auth policies. It works with `bridge`, `awsvpc`, and `host` network modes ([interconnect network-mode table](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html)).

**Constraints:**
- **Only ECS rolling deployments work with VPC Lattice — CodeDeploy and blue/green deployment controllers are not supported** ([Use VPC Lattice with ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-vpc-lattice.html)). If you need native blue/green *and* Lattice, that is a conflict to resolve at design time.
- **Not supported on ECS Anywhere (`EXTERNAL`).**
- Attaching multiple (up to five) VPC Lattice configurations can lengthen deployment time.

---

## Sources

- [Allocate a network interface for an Amazon ECS task](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html)
- [Increasing Amazon ECS Linux container instance network interfaces](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html) — trunking, `awsvpcTrunking`, "not available on Fargate"
- [Access Amazon ECS features with account settings](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html)
- [Optimizing Amazon ECS task density using awsvpc network mode](https://aws.amazon.com/blogs/compute/optimizing-amazon-ecs-task-density-using-awsvpc-network-mode/)
- [AWSVPC mode — best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-networkmode-awsvpc.html)
- [Interconnect Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html) · [Networking between ECS services in a VPC](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-connecting-services.html)
- [Migrating from AWS App Mesh to Amazon ECS Service Connect](https://aws.amazon.com/blogs/containers/migrating-from-aws-app-mesh-to-amazon-ecs-service-connect/) — App Mesh EOL Sept 30, 2026 (blog); [App Mesh doc-history EOL notice](https://docs.aws.amazon.com/app-mesh/latest/userguide/doc-history.html)
- [Amazon ECS Service Connect components](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html) — proxy sidecar CPU/memory, task-memory-limit requirement
- [ECS clusters for external instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-anywhere.html) — EXTERNAL supports bridge/host/none only (no awsvpc), no ELB/service discovery
- [Use Amazon VPC Lattice with ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-vpc-lattice.html) · [ECS + VPC Lattice launch blog](https://aws.amazon.com/blogs/aws/streamline-container-application-networking-with-native-amazon-ecs-support-in-amazon-vpc-lattice/) — rolling-only, not on ECS Anywhere
- [Architect for AWS Fargate — service load balancing](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html) — UDP via NLB requires PV 1.4+
- [Amazon ECS FAQs — service-to-service communication](https://aws.amazon.com/ecs/faqs/)
