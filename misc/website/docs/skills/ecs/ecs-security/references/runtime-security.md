---
title: "Layer 6 — Runtime Security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/runtime-security.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/runtime-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/runtime-security.md). Edit the source, not this page.
:::

# Layer 6 — Runtime Security

Detect threats *while tasks run* — container breakouts, reverse shells, privilege escalation, crypto-mining, connections to malicious IPs. On ECS the AWS-native answer is **Amazon GuardDuty Runtime Monitoring**.

## GuardDuty Runtime Monitoring for ECS

An eBPF/kernel-level security agent observes on-host behavior (file access, process execution, network connections) and reports to GuardDuty. Coverage for ECS (verified 2026-07-09 against current docs):

| ECS launch type | Runtime Monitoring support | Agent management |
|---|---|---|
| **AWS Fargate** | **Supported** | GuardDuty deploys a **sidecar container** into each task; managed **only through GuardDuty** (no manual agent). A Fargate task is immutable, so the sidecar is injected at task start — a **running** task must be **stopped and restarted** to gain coverage. |
| **ECS on EC2** | **Supported** | Deploy the GuardDuty agent on the EC2 container instances (GuardDuty can manage it). |
| **ECS Managed Instances** | **NOT supported** | Verified — *"Runtime Monitoring doesn't support applications running on Amazon ECS Managed Instances."* This is a real detection gap to weigh against the reduced-patching benefit of Managed Instances. |
| **ECS Anywhere (external)** | Not covered by ECS Runtime Monitoring | Customer-owned host; use host-based tooling. |

Other verified coverage limits (state these precisely): Runtime Monitoring is **not supported for the Windows operating system**, **not supported on ECS Anywhere**, and **not supported on ECS Managed Instances** ([ECS GuardDuty integration considerations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html)). When using **ECS Exec on Fargate** you must specify the container name (the GuardDuty agent runs as a sidecar), and you cannot ECS Exec into the sidecar itself.

Setup notes (verified):
- The **task execution role** needs `guardduty:SendSecurityTelemetry`-type permission for the Fargate sidecar; if a **permissions boundary** is attached to the execution role, confirm it doesn't block that action ([ECS Runtime Monitoring prerequisites](https://docs.aws.amazon.com/guardduty/latest/ug/prereq-runtime-monitoring-ecs-support.html)).
- GuardDuty creates a **VPC endpoint + security group** for the agent's telemetry; the sidecar image pulls from ECR (layers in S3) so restrictive networks must allow the **S3 managed prefix list** — a frequent cause of "Unhealthy" coverage. See [assess ECS coverage](https://docs.aws.amazon.com/guardduty/latest/ug/gdu-assess-coverage-ecs.html).
- Runtime Monitoring is **designed not to block tasks** if the sidecar can't start healthy.

References: [GuardDuty Runtime Monitoring](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html) · [How it works with ECS-Fargate](https://docs.aws.amazon.com/guardduty/latest/ug/how-runtime-monitoring-works-ecs-fargate.html) · [ECS GuardDuty integration](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-guard-duty-integration.html).

## GuardDuty Extended Threat Detection for ECS (automatic, no *additional* cost atop paid GuardDuty)

GuardDuty **Extended Threat Detection** now correlates signals across runtime behavior, malware execution, and AWS API activity to surface **multi-stage attacks** as a single critical finding — for ECS the finding type is **`AttackSequence:ECS/CompromisedCluster`** (and `AttackSequence:EC2/CompromisedInstanceGroup` for the EC2 layer). It is **enabled automatically for GuardDuty customers at no additional cost**, but its comprehensiveness depends on the protection plans you've enabled — **enable Runtime Monitoring (Fargate or EC2) to feed it** for ECS clusters. This is the highest-value detection lever to call out for SOC/compliance customers. Reference: [GuardDuty Extended Threat Detection now supports EC2 and ECS (Dec 2025)](https://aws.amazon.com/about-aws/whats-new/2025/12/guardduty-extended-threat-detection-ec2-ecs/) · [Extended Threat Detection docs](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty-extended-threat-detection.html).

## Security Hub — unified findings

GuardDuty, Inspector (ECR scanning), and Config findings all flow into **AWS Security Hub**, which also evaluates the **ECS controls pack** (ECS.4 non-privileged, ECS.5 read-only rootfs, plaintext-secret checks, host-mode checks, …) and standards (AWS FSBP, CIS, NIST 800-53, PCI-DSS). This is the single pane for ECS posture. Reference: [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html).

## Third-party CNAPP runtime

Wiz, Prisma Cloud, Aqua, Sysdig, CrowdStrike, and SentinelOne offer ECS runtime detection (often as a sidecar or EC2-host agent) via AWS Marketplace. Use for multi-cloud posture or an existing enterprise contract; on Fargate confirm the vendor supports sidecar deployment.

## Shared responsibility (Layer 6)

| AWS manages | Customer manages |
|---|---|
| GuardDuty detection engine + threat intel; Fargate sidecar lifecycle; Extended Threat Detection correlation; Security Hub aggregation | Enabling Runtime Monitoring (and knowing MI is excluded); execution-role permission + boundary check; network path for the agent; restart of running Fargate tasks for coverage; triage + response runbooks |

## Sources
- [GuardDuty Runtime Monitoring](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html) · [How it works with ECS-Fargate](https://docs.aws.amazon.com/guardduty/latest/ug/how-runtime-monitoring-works-ecs-fargate.html) · [ECS Runtime Monitoring prerequisites](https://docs.aws.amazon.com/guardduty/latest/ug/prereq-runtime-monitoring-ecs-support.html) · [Assess ECS coverage](https://docs.aws.amazon.com/guardduty/latest/ug/gdu-assess-coverage-ecs.html)
- [Extended Threat Detection for EC2 & ECS (Dec 2025)](https://aws.amazon.com/about-aws/whats-new/2025/12/guardduty-extended-threat-detection-ec2-ecs/) · [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html)
