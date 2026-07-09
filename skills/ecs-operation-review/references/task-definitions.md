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

### 3.3 — Log Configuration Present (pointer — rated in 6.2)

**What to check:**
- Whether every container carries a `logConfiguration` at all (`awslogs`, `awsfirelens`, etc.) — a task-definition-hygiene sanity check.

**How to check:**
1. Inspect `containerDefinitions[].logConfiguration.logDriver` while collecting task-definition data.

**Rating:** **Do not score this item here.** The presence/absence of a log driver (including the "no log driver → 🔴 RED" case), log routing, `awslogs-stream-prefix`, and delivery-mode are all rated **once** in **observability check 6.2** to avoid double-counting across domains (see `scoring-rubric.md`). If you observe a container with no log driver while parsing task definitions, record the evidence and carry it into 6.2 — do not emit a separate 3.3 rating.

Full observability rating (driver presence, retention, routing, delivery mode, tracing) is Section 06; design help → **`ecs-observability`**.

---

### 3.4 — Task Role and Execution Role Assigned

**What to check:**
- `taskRoleArn` (application AWS access) and `executionRoleArn` (image pull, secrets injection, log push) presence and separation.

**How to check:**
1. `aws ecs describe-task-definition` → `taskRoleArn`, `executionRoleArn`.

**Rating (presence/separation only — least-privilege & role-reuse are rated once, in check 7.1, to avoid double-counting):**
- 🟢 GREEN: Distinct task role (for app AWS calls) and execution role (for the agent) both present as needed; task role present only when the app needs AWS access.
- 🟡 AMBER: Roles present but a single role serves both concerns (the least-privilege/reuse judgment on this is scored in **7.1**, not here — flag it and defer).
- 🔴 RED: No execution role where secrets/private-ECR pulls are used (tasks will fail to start).
- ⬜ UNKNOWN: Cannot read task definitions.

**Scope note:** This check rates **presence and role separation** at the task-definition level. The **least-privilege, over-broad-policy, and execution-role-reused-as-task-role** ratings live in **security check 7.1** — do not re-score them here (see the consistency note in `scoring-rubric.md` on cross-domain duplicates). For the task-role vs execution-role explainer and deep role-trust remediation, see **7.1** and **`ecs-security`**. See [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

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
