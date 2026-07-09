---
title: "Layer 1 — Compute & Shared Responsibility"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/shared-responsibility.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/shared-responsibility.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/shared-responsibility.md). Edit the source, not this page.
:::

# Layer 1 — Compute & Shared Responsibility

The ECS-specific first question is **launch type**, because it moves the line between what AWS secures and what you secure. Get this right before anything else — it changes which controls at Layers 3, 5, and 6 are even available.

## The shared-responsibility line by launch type

AWS's model is *security **of** the cloud* (AWS) vs *security **in** the cloud* (you); what "in the cloud" means for you shrinks as you move toward Fargate. Reference: [Security in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html) · [AWS shared responsibility model for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-shared-model.html) · [Shared responsibility model for ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-shared-model-managed-instances.html).

| Launch type | AWS secures | You secure | Task isolation? |
|---|---|---|---|
| **AWS Fargate** | Physical host, hypervisor, **host OS + kernel + container runtime**, per-task VM-level isolation | Task definition hardening, IAM roles, network config, secrets, image contents, app | **Yes** — each task has its own isolation boundary; no shared kernel/CPU/memory/ENI |
| **ECS on EC2** | Physical host, hypervisor | **Container-instance AMI + OS patching**, ECS agent version, **IMDS lockdown**, plus everything Fargate leaves to you | **No** — tasks share the instance kernel |
| **ECS Managed Instances** | Host, and **AWS manages the EC2 instance lifecycle/patching** of the managed fleet | Task hardening, IAM, network, secrets, image, app (AWS handles the instance OS) | **No** — tasks share the instance kernel; **GuardDuty Runtime Monitoring not supported** here |
| **ECS Anywhere (external)** | The ECS control plane / agent registration only | **Everything else** — the on-prem host, OS, kernel, network, physical security | **No** — customer-owned host |

> **The boundary statement to use verbatim (verified against AWS docs):** *"Containers are not a security boundary and the use of task IAM roles does not change this."* On Fargate each task is isolated; on **EC2, Managed Instances, and ECS Anywhere there is no task isolation** — a compromised container can access credentials for other tasks on the same instance, the [container instance role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/instance_IAM_role.html), and instance metadata via IMDS. For workloads with strict isolation requirements, **use Fargate**. Source: [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

## Hardening the container instance (ECS on EC2 only)

Fargate makes this section moot (AWS owns the OS). On **ECS on EC2** you own the container-instance operating system:

- **AMI choice.** Use the **ECS-optimized Amazon Linux 2023 AMI** (current, patched, minimal) or **Bottlerocket** (immutable, SELinux-enforcing, container-purpose-built, minimal attack surface — the strongest option for regulated workloads). AWS publishes ECS-optimized Bottlerocket variants. Keep AMIs current; treat instance replacement (not in-place patching) as the clean default with immutable OSes.
- **Patch cadence.** You own kernel/OS CVE patching. Rebuild/replace instances from a refreshed AMI on a defined cadence; document it for auditors.
- **ECS agent + Docker/containerd version.** Keep the ECS container agent current ([Updating the ECS container agent](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-update.html)).
- **IMDS lockdown — critical, because there is no task isolation on EC2.** Prevent tasks from reaching the EC2 Instance Metadata Service (which would expose the instance role's credentials). The concrete controls (verified 2026-07-09 against [ECS roles recommendations — block access to EC2 metadata](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)):
  - **`awsvpc`-mode tasks:** set `ECS_AWSVPC_BLOCK_IMDS=true` in `/etc/ecs/ecs.config` on the instance.
  - **`bridge`-mode tasks:** an iptables `DROP` on the docker interface to the IMDS IP — `iptables --insert FORWARD 1 --in-interface docker+ --destination 169.254.169.254/32 --jump DROP` (persist it across reboots).
  - **`host`-network tasks:** set `ECS_ENABLE_TASK_IAM_ROLE_NETWORK_HOST=false`.
  - Enforce **IMDSv2** (token-required) with **hop limit 1** on the instance so a container one hop away can't reach IMDS. On Fargate this concern does not exist.
- **`ECS_DISABLE_PRIVILEGED=true`** as an agent env var (in `/etc/ecs/ecs.config`) on hosts where privileged containers are never needed, to defense-in-depth against a privileged task. Reference: [Amazon ECS container agent configuration](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-config.html) (see [task-container-hardening.md](task-container-hardening)).

## Managed Instances nuance

**ECS Managed Instances** shifts the EC2 instance lifecycle and patching to AWS (a security *benefit* — no customer-owned OS patch cadence), but tasks still share the instance kernel (no per-task isolation like Fargate), and **GuardDuty Runtime Monitoring is not supported** on Managed Instances (verified — see [runtime-security.md](runtime-security)). Weigh that detection gap against the reduced-patching benefit for a regulated workload.

## Shared responsibility (Layer 1)

| AWS manages | Customer manages |
|---|---|
| Fargate: host OS/kernel/runtime + per-task isolation. EC2: host/hypervisor only. Managed Instances: instance lifecycle + patching. All: ECS control plane | EC2: AMI + OS patching + IMDS lockdown + agent version. All launch types: task definition, IAM roles, network, secrets, image, app. ECS Anywhere: the entire on-prem host |

## Sources
- [Security in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html) · [AWS shared responsibility model for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-shared-model.html) · [Shared responsibility model for ECS Managed Instances](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-shared-model-managed-instances.html)
- [ECS task IAM role — containers are not a boundary](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [ECS container instance IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/instance_IAM_role.html) · [Updating the ECS container agent](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-update.html)
- [ECS roles recommendations — block access to EC2 metadata (`ECS_AWSVPC_BLOCK_IMDS`)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) · [Amazon ECS container agent configuration (`ECS_DISABLE_PRIVILEGED`)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-config.html)
