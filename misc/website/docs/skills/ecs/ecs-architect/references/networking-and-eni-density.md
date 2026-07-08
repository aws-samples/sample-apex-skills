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
> **Purpose:** Design task networking for ECS — `awsvpc` task ENIs, ENI density and trunking on EC2, subnet/SG placement, load-balancer choice, and Service Connect vs Service Discovery. Facts verified against AWS docs on 2026-07-08.

---

## Table of Contents

1. [Network Modes](#network-modes)
2. [awsvpc Task ENIs](#awsvpc-task-enis)
3. [ENI Density and Trunking on EC2](#eni-density-and-trunking-on-ec2)
4. [Subnet and Security-Group Design](#subnet-and-security-group-design)
5. [Load Balancer Selection](#load-balancer-selection)
6. [Service Connect vs Service Discovery](#service-connect-vs-service-discovery)
7. [Sources](#sources)

---

## Network Modes

| Mode | Where it applies | Notes |
|------|------------------|-------|
| **`awsvpc`** | Fargate (required), EC2, Managed Instances | Each task gets its own ENI, its own private IP, and its own security group. Recommended for security and observability. |
| **`bridge`** | EC2 only | Docker's built-in virtual network; dynamic port mapping. Legacy. |
| **`host`** | EC2 only | Task binds directly to the host's network. No per-task isolation. |
| **`none`** | EC2 only | No external connectivity. |

**Default recommendation: `awsvpc`.** It gives each task EC2-like networking — security groups, VPC Flow Logs, and granular monitoring per task — and is mandatory on Fargate. ([Allocate a network interface for an Amazon ECS task](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html))

---

## awsvpc Task ENIs

With `awsvpc`, ECS creates one ENI per task, attaches it to the host with the task's security group, and assigns a private IPv4 address (plus IPv6 in a dual-stack subnet). **Each task can only have one ENI.** These ENIs are ECS-managed — visible in the EC2 console but you can't detach or modify them; they're deleted when the task stops or the service scales in. ([task-networking-awsvpc](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html))

**Consequence for IP planning:** every task consumes a VPC IP. In IP-constrained VPCs, high task counts can exhaust subnets — size subnets for peak task count, not just instance count.

---

## ENI Density and Trunking on EC2

On EC2, the biggest disadvantage of `awsvpc` is that EC2 instances cap how many ENIs can attach, which caps tasks per instance. By default a `c5.large` supports 3 ENIs; the primary counts as one, leaving 2 — so **only ~2 awsvpc tasks per `c5.large`**. ([container-instance-eni](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html))

**ENI trunking** raises this. Turn on the **`awsvpcTrunking` account setting** and ECS attaches a managed "trunk" ENI to newly-launched (supported) instances. A `c5.large` with trunking has an ENI limit of **12**, so it can run **10 tasks instead of 2** — roughly a 5x density gain, with no latency/bandwidth penalty. ([container-instance-eni](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html) · [Optimizing ECS task density using awsvpc](https://aws.amazon.com/blogs/compute/optimizing-amazon-ecs-task-density-using-awsvpc-network-mode/))

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
| **NLB** | TCP/UDP, ultra-low latency, static IPs, gRPC | UDP to Fargate requires platform version 1.4+. |
| **None (Service Connect)** | Service-to-service traffic inside/across clusters | No LB needed for east-west; see below. |

External instances (ECS Anywhere) have **no ELB support** — factor this into inbound-traffic designs. ([launch-type-external](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch-type-external.html))

---

## Service Connect vs Service Discovery

Both solve service-to-service connectivity without a load balancer. **Service Connect is the recommended choice** for new designs. ([Interconnect Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html))

| | **Service Connect** (recommended) | **Service Discovery** (Cloud Map) |
|--|-----------------------------------|-----------------------------------|
| **Mechanism** | ECS-managed proxy agent in each task; logical short names + standard ports | AWS Cloud Map DNS records per task |
| **Scope** | Same cluster, other clusters, across VPCs in the same Region | DNS-resolvable endpoints |
| **Telemetry** | Rich traffic telemetry in the ECS console and CloudWatch | None built-in |
| **Deployment safety** | Config changes apply **at deployment**; automatic **connection draining** lets clients cut over to a new endpoint version without traffic errors | DNS TTL means clients may keep hitting old IPs until TTL expires — a classic migration pain |
| **App changes** | Usually none if the app already uses DNS names | None |

Why Service Connect wins: with DNS-based discovery, changing a name to new IPs waits out the max TTL before all clients switch. Service Connect updates config by replacing client tasks during a normal deployment, so you control the cutover with the deployment circuit breaker and other deployment settings. ([Networking between ECS services in a VPC](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-connecting-services.html))

**Coming off App Mesh?** AWS App Mesh is discontinued **September 30, 2026** (no new-customer onboarding since September 24, 2024); Service Connect is the recommended ECS target (managed data plane, no self-managed Envoy sidecars, built-in retries/outlier detection and CloudWatch metrics). Migrate per service, running both in parallel during cutover. Note current Service Connect gaps vs App Mesh: no fine-grained retry/circuit-breaker tuning, weighted A/B traffic splits, or cross-account sharing. ([Migrating from AWS App Mesh to Amazon ECS Service Connect](https://aws.amazon.com/blogs/containers/migrating-from-aws-app-mesh-to-amazon-ecs-service-connect/))

Migration from Service Discovery → Service Connect is covered in [launch-type-migration.md](launch-type-migration).

---

## Sources

- [Allocate a network interface for an Amazon ECS task](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html)
- [Increasing Amazon ECS Linux container instance network interfaces](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html) — trunking, `awsvpcTrunking`, "not available on Fargate"
- [Access Amazon ECS features with account settings](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html)
- [Optimizing Amazon ECS task density using awsvpc network mode](https://aws.amazon.com/blogs/compute/optimizing-amazon-ecs-task-density-using-awsvpc-network-mode/)
- [AWSVPC mode — best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-networkmode-awsvpc.html)
- [Interconnect Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/interconnecting-services.html) · [Networking between ECS services in a VPC](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/networking-connecting-services.html)
- [Migrating from AWS App Mesh to Amazon ECS Service Connect](https://aws.amazon.com/blogs/containers/migrating-from-aws-app-mesh-to-amazon-ecs-service-connect/) — App Mesh EOL Sept 30, 2026
- [Amazon ECS FAQs — service-to-service communication](https://aws.amazon.com/ecs/faqs/)
