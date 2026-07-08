# Section 03 — Task Definitions

## Purpose
Assess task-definition hygiene: right-sized task CPU/memory, container image discipline, logging configuration, storage/volumes, and presence of task + execution roles. Grounded in the [task-definition best-practices pillar](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html) (container images, task size, volumes).

## Checks to Execute

### 3.1 — Task Size (CPU / Memory) Set and Reasonable

**What to check:**
- Task-level `cpu` and `memory` set (required for Fargate; strongly recommended for EC2).
- Container-level `memory` (hard) vs `memoryReservation` (soft) limits.
- Obvious over/under-provisioning signals.

**How to check:**
1. `aws ecs describe-task-definition --task-definition <arn>` → read task `cpu`/`memory` and each container's `memory`/`memoryReservation`/`cpu`.

**Rating:**
- 🟢 GREEN: Task size set; container soft/hard limits present; sized to a valid Fargate CPU/memory combination where applicable.
- 🟡 AMBER: Only task-level limits, no container reservations (poor bin-packing on EC2), or suspected over-provisioning.
- 🔴 RED: No memory limit/reservation on EC2 tasks (a runaway container can starve the instance), or invalid/edge Fargate sizing.
- ⬜ UNKNOWN: Cannot describe task definitions.

**Key talking point:** On EC2, a container with no memory limit can consume the whole instance and destabilize co-located tasks. Dollar-level right-sizing → **`ecs-cost-intelligence`**. See [ECS task sizes](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-tasksize.html).

---

### 3.2 — Container Image Discipline

**What to check:**
- Images pinned to immutable digests/tags vs `:latest`.
- Registry source (private ECR vs public/Docker Hub).

**How to check:**
1. From each container definition, inspect `image` for `:latest`/no tag and registry host.

**Rating:**
- 🟢 GREEN: Specific version tags or digests from private ECR.
- 🟡 AMBER: Versioned but from public registries, or occasional `:latest`.
- 🔴 RED: `:latest` widely used (non-reproducible deployments) or images from untrusted public registries.
- ⬜ UNKNOWN: Cannot read task definitions.

**Key talking point:** `:latest` breaks reproducibility and rollback — a re-pull can silently change the running code. See [ECS container images](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-considerations.html). Image scanning/signing posture → Section 07 and **`ecs-security`**.

---

### 3.3 — Log Configuration Present

**What to check:**
- `logConfiguration` on each container (`awslogs`, `awsfirelens`, etc.).
- Containers with no log driver (logs unreachable).

**How to check:**
1. Inspect `containerDefinitions[].logConfiguration.logDriver` and options.

**Rating:**
- 🟢 GREEN: Every container has a log driver configured (`awslogs` or `awsfirelens`).
- 🟡 AMBER: Log driver set but no obvious retention/routing strategy (rated fully in Section 06).
- 🔴 RED: Containers with no log configuration — logs are lost.
- ⬜ UNKNOWN: Cannot read task definitions.

Full observability rating (retention, routing, tracing) is Section 06; design help → **`ecs-observability`**.

---

### 3.4 — Task Role and Execution Role Assigned

**What to check:**
- `taskRoleArn` (application AWS access) and `executionRoleArn` (image pull, secrets injection, log push) presence and separation.

**How to check:**
1. `aws ecs describe-task-definition` → `taskRoleArn`, `executionRoleArn`.

**Rating:**
- 🟢 GREEN: Distinct task role (for app AWS calls) and execution role (for the agent); task role present only when the app needs AWS access.
- 🟡 AMBER: Execution role reused as task role, or one broad role for both concerns.
- 🔴 RED: No execution role where secrets/private-ECR pulls are used (tasks will fail to start), or a single over-broad role.
- ⬜ UNKNOWN: Cannot read task definitions.

**Key talking point:** The **task role** vends permissions to your app; the **execution role** lets the ECS agent pull images, inject secrets, and ship logs. Keep them separate and least-privilege. Deep role-trust and least-privilege remediation → **`ecs-security`**. See [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

---

### 3.5 — Storage / Volumes

**What to check:**
- Volume types (ephemeral, bind mounts, EFS, Fargate ephemeral storage sizing, EBS volumes for tasks).
- Sensitive data written to ephemeral storage without encryption considerations.

**How to check:**
1. Inspect `volumes` and `containerDefinitions[].mountPoints` in the task definition; for services, check configured EBS volume attachment.

**Rating:**
- 🟢 GREEN: Volume choice matches durability needs (EFS/EBS for persistence; ephemeral for scratch), encryption in place.
- 🟡 AMBER: Ephemeral storage used for data that should persist, or default sizing under pressure.
- 🔴 RED: Stateful data on ephemeral task storage with no backup/persistence path.
- ⬜ UNKNOWN: Cannot determine data criticality — flag for manual review.

**Key talking point:** See [storage options for ECS tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_data_volumes.html). Backup/DR posture is rated in Section 08.
