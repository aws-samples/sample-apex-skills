---
title: "Layer 3 — Task & Container Hardening"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/task-container-hardening.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/task-container-hardening.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/task-container-hardening.md). Edit the source, not this page.
:::

# Layer 3 — Task & Container Hardening

What a container is *allowed to do*. These are task-definition and image controls; most are one-line additions to a container definition that materially shrink the attack surface. Reference: [ECS task and container security best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-tasks-containers.html).

## The container-definition hardening set

| Control | Task-definition field | Why | Notes |
|---|---|---|---|
| **Read-only root filesystem** | `readonlyRootFilesystem: true` | The container FS is writable by default; read-only forces explicit, minimal writable mounts and blocks tampering | **Test first** — apps that write to disk break; add `tmpfs`/volume mounts for the paths they need. Checked by Security Hub **ECS.5**. **Not applicable to Windows containers, and incompatible with ECS Exec** (the SSM agent must write to the FS — verified). |
| **Non-root user** | `user: "1000:1000"` (or a named non-root) | Containers run as `root` by default unless the image `USER` directive or this field says otherwise | Lint Dockerfiles for a `USER` directive in CI. |
| **Non-privileged** | `privileged: false` | A privileged container inherits all host `root` Linux capabilities — near-total host access | **Not supported on Fargate** at all (privileged can't be set). On EC2, set agent `ECS_DISABLE_PRIVILEGED=true` on hosts that never need it. Checked by Security Hub **ECS.4**. |
| **Drop Linux capabilities** | `linuxParameters.capabilities.drop` | Docker grants ~14 default capabilities; most workloads need almost none | `drop: ["ALL"]` is valid on **every** launch type. **`add` is severely limited on Fargate: the only addable capability is `SYS_PTRACE`** (verified — [Fargate security](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-fargate.html)); `NET_BIND_SERVICE` etc. can only be added on EC2. Reference: [KernelCapabilities](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_KernelCapabilities.html). |
| **CPU & memory limits** | `cpu`, `memory` (task and/or container) | Prevents one task from starving co-located tasks (a availability-isolation control on EC2) | **Fargate requires** task-level CPU/memory (used for billing). On EC2, unset limits let a task consume the host. |
| **No new privileges** | via `dockerSecurityOptions` (`"no-new-privileges"`) / capability hygiene | Prevent privilege escalation through setuid binaries | **`dockerSecurityOptions` (incl. `no-new-privileges`, SELinux `label:…`, AppArmor `apparmor:PROFILE`) is EC2-only — it is not valid for the Fargate launch type** (verified — [ContainerDefinition.dockerSecurityOptions](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ContainerDefinition.html)); the agent must also register `ECS_SELINUX_CAPABLE=true`/`ECS_APPARMOR_CAPABLE=true`. On Fargate, rely on capability hygiene + non-root + read-only rootfs instead. Combine with removing `setuid`/`setgid` binaries from the image (below). |
| **Init process (zombie reaping)** | `linuxParameters.initProcessEnabled: true` | Runs a tiny init as PID 1 to reap defunct child processes | For containers that fork children; without it, zombie processes can accumulate and exhaust PID limits. Reference: [LinuxParameters API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LinuxParameters.html). |

Example hardened container definition fragment:

```json
{
  "name": "app",
  "image": "111122223333.dkr.ecr.region.amazonaws.com/app@sha256:...",
  "user": "1000:1000",
  "readonlyRootFilesystem": true,
  "privileged": false,
  "linuxParameters": { "capabilities": { "drop": ["ALL"] }, "initProcessEnabled": true },
  "portMappings": [{ "containerPort": 8080, "protocol": "tcp" }],
  "cpu": 512,
  "memory": 1024,
  "mountPoints": [{ "sourceVolume": "tmp", "containerPath": "/tmp" }]
}
```

> **Why no `add: ["NET_BIND_SERVICE"]` here.** This fragment is portable across launch types, so it only uses `drop: ["ALL"]` (valid everywhere). Adding `NET_BIND_SERVICE` would **fail on Fargate**, where the only addable capability is `SYS_PTRACE`. And it is unnecessary: the container runs as **UID 1000** (which can't bind ports below 1024 regardless of capabilities), so listen on a **high port** (e.g. `8080`) and let the ALB/NLB target group front it on 80/443. Only if you genuinely must bind a low port *and* run on EC2 should you add `NET_BIND_SERVICE`.

## Harden the image itself

- **Minimal / distroless base images** — remove package managers, shells, and utilities (`nc`, `curl`) that aid an attacker. AWS recommends distroless or `scratch` (e.g. a statically linked Go binary) and multi-stage builds to strip build tooling.
- **Remove `setuid`/`setgid` binaries** — they enable privilege escalation. AWS suggests a Dockerfile line: `RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} \; || true`.
- **Curated base images** — vet a set of organization-approved base images rather than letting developers pull arbitrary Docker Hub images (unknown contents + rate limits).
- **Static code analysis** before build (e.g. Amazon Inspector / SAST tooling).
- **Immutable ECR tags** — prevents an attacker from overwriting a good tag with a compromised image; also see [image-supply-chain.md](image-supply-chain).

## Verify with Security Hub ECS controls

AWS Security Hub publishes ECS-specific controls that check exactly these settings across your task definitions — use them as the automated audit for this layer:
- **ECS.4** — containers should run as non-privileged.
- **ECS.5** — containers should be limited to read-only root filesystems.
- Plus controls for logging, secrets in plaintext env vars, host networking, and privilege escalation.

Reference: [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html). AWS Config rule **`ecs-containers-nonprivileged`** is the Config-side equivalent.

## Shared responsibility (Layer 3)

| AWS manages | Customer manages |
|---|---|
| Enforcing the task-definition settings at launch; Fargate per-task isolation; Security Hub/Config control evaluation | Setting `readonlyRootFilesystem`/`user`/`privileged`/dropped capabilities/limits; image minimization + setuid removal; curated base images; remediating Security Hub ECS findings |

## Sources
- [ECS task and container security best practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-tasks-containers.html) · [Task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) · [KernelCapabilities API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_KernelCapabilities.html) · [Fargate security (SYS_PTRACE only)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-fargate.html) · [ContainerDefinition API (dockerSecurityOptions)](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ContainerDefinition.html) · [ECS Exec (read-only rootfs unsupported)](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html)
- [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html)
