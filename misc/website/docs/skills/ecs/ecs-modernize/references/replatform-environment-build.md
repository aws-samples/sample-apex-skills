---
title: "Module: Replatform Environment Build"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/replatform-environment-build.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/references/replatform-environment-build.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/replatform-environment-build.md). Edit the source, not this page.
:::

# Module: Replatform Environment Build

> **Part of:** [ecs-modernize](../)
> **Purpose:** Generate the Replatform_Environment_Terraform for an approved **Linux** Replatform path — an ECS on EC2 cluster with an Auto Scaling group, a `bridge`-mode task definition with dynamic host port mapping, a fixed-`desiredCount` service with no scaling policy, and an ALB whose target group carries `stickiness` exactly when the in-process session Blocker was detected — conforming to the repository terraform-skill's conventions, verified by `terraform validate` as the sole applicability check, with an unresolved image URI handled as a Terraform input variable
> **Prerequisites:** **Execution_Gate passage** + **Containerization execution** ([containerization-execution.md](containerization-execution)) — the image URI for the task definition; when the URI is unresolved, define it as a Terraform input variable per the [unresolved image URI rule](#unresolved-image-uri--input-variable-rule)

This module builds the target environment for an approved **Linux Replatform path** — ECS on EC2, containerize-as-is. It exists because **`ecs-build`'s generation scope does not cover the Replatform shape**: `ecs-build` generates `network_mode = "awsvpc"` task definitions exclusively and services that always use a `capacity_provider_strategy`, and it carries no knowledge of ALB target-group `stickiness`, `bridge` networking, or dynamic host port mapping. Those four elements are precisely what the Replatform path requires ([replatform-path.md](replatform-path)), so handing this path to `ecs-build` would produce an environment that contradicts the approved strategy.

State that rationale explicitly whenever this module runs: the user should know *why* the Rearchitect compute models hand off to `ecs-build` (see [deploy-verify-handoff.md](deploy-verify-handoff)) while the Replatform path does not. Never route a Replatform environment IaC request to `ecs-build`; the delegation boundary and the future-support note — if `ecs-build` gains `bridge`/stickiness/launch-type generation, this module's generation is replaced by a delegation — are canonical in [SKILL.md](../).

This module is the sibling of [windows-environment-build.md](windows-environment-build): same generation discipline, same `terraform validate` applicability check, same unresolved-URI rule, different target shape. When the approved path is the **Windows_Container_Path**, that module owns the generation and this one does not run — the Windows path's own compute options and base-image matrix govern there.

This module is ECS-specific: it depends on the ECS resource model (cluster, ASG capacity, task definition network modes, service, ALB target groups) and does not port to other orchestrators.

## Table of Contents

- [Inputs](#inputs)
- [Generation Flow](#generation-flow)
- [terraform-skill Conventions Conformance](#terraform-skill-conventions-conformance)
- [Generated Elements](#generated-elements)
  - [Cluster and capacity — EC2 Auto Scaling group](#cluster-and-capacity--ec2-auto-scaling-group)
  - [Task definition — bridge mode and dynamic host ports](#task-definition--bridge-mode-and-dynamic-host-ports)
  - [Service — fixed desiredCount, no scaling policy](#service--fixed-desiredcount-no-scaling-policy)
  - [Load balancer — session affinity conditioned on the Blocker finding](#load-balancer--session-affinity-conditioned-on-the-blocker-finding)
  - [Persistent write targets — EFS conditioned on the Blocker finding](#persistent-write-targets--efs-conditioned-on-the-blocker-finding)
  - [Supporting inputs and resources](#supporting-inputs-and-resources)
- [Unresolved Image URI — Input Variable Rule](#unresolved-image-uri--input-variable-rule)
- [terraform validate — the Applicability Check](#terraform-validate--the-applicability-check)
- [Value Traceability](#value-traceability)
- [Execution_Log](#execution_log)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **The approved Migration_Strategy and target path** (required) — a **Linux** Replatform path. If the approved path is the Windows_Container_Path, this module does not run ([windows-environment-build.md](windows-environment-build) does). If the approved path is a Rearchitect compute model, this module does not run (`ecs-build` generates it).
- **The image URI** (required, or explicitly unresolved) — from the containerization execution push result (`containerization_execution.push.image_uri`). An unresolved URI does not block generation; it becomes an input variable per the [rule below](#unresolved-image-uri--input-variable-rule).
- **The `replatform_path` block** (required) — from [replatform-path.md](replatform-path): the static configuration decisions (fixed task count and its derivation state, capacity derivation policy), the containerization policy, the persistent-vs-temporary write mapping, and the session-affinity decision. This module renders those decisions; it does not re-make them.
- **The `blockers` block** (required) — the `in_process_session` finding drives stickiness, and the `local_state` findings drive the persistent-volume decision. Both are conditioned on the finding's presence, never generated by default.
- **The `tech_stack` block** (required) — the container port comes from the containerization artifact, and the health check path from the app-provided endpoint when Source_Analysis identified one.
- **Sizing inputs** — CPU/memory from the containerization artifact's task-definition input values; the instance type from the capacity derivation. When either is missing, the [missing-sizing edge case](#sizing-inputs-are-missing) governs — never invent a number.
- **The repository terraform-skill conventions** (required) — read them before generating, per [conformance](#terraform-skill-conventions-conformance).

---

## Generation Flow

Run the steps in this order:

```
0. Confirm this file has been read in full   -> SKILL.md mandate before executing this module
1. Verify the gate and the approved path      -> Execution_Gate passed AND the approved path is
                                                a Linux Replatform path (not Windows, not
                                                a Rearchitect compute model)
2. Read the terraform-skill conventions       -> the generated code conforms to them
3. Obtain the file-generation confirmation    -> presenting the output directory (action class)
4. Copy the skeleton                          -> assets/replatform-terraform/ verbatim; the
                                                skeleton is not re-derived per run
5. Resolve the conditioned elements           -> stickiness from the in_process_session finding;
                                                persistent volumes from the local_state mapping;
                                                image URI resolved or left to apply time
6. Write terraform.tfvars                     -> every value with its origin in a comment
7. Run terraform fmt + validate               -> the sole applicability check; on failure, fix
                                                and re-validate before reporting success
8. Record the Execution_Log entry              -> files written, validate result, unresolved items
9. Hand to the deploy procedure                -> deploy-verify-handoff.md owns plan/apply/verify
```

### The skeleton is copied, not written from scratch

A verified skeleton ships with this skill at **[`assets/replatform-terraform/`](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/assets/replatform-terraform)**. Copy it; do not regenerate its contents from memory. The point is determinism: the same assessment findings produce the same environment, so a reviewer can diff two runs and see only the values change.

| File | Role |
|---|---|
| `main.tf` | The fixed skeleton — security groups, ALB with the conditioned `stickiness` block, cluster, launch template, ASG, `bridge` task definition with `hostPort = 0`, service with fixed `desired_count` |
| `variables.tf` | Every input, each with a `description` naming its traceable source. No fabricated defaults |
| `iam.tf` | Instance role, execution role, and the ECS-Exec-only task role |
| `outputs.tf` | The three the deploy procedure needs, plus the resolved conditioned decisions |
| `OPTIONAL-efs.tf.fragment` | **Not** part of the skeleton — added only per the [persistent write targets](#persistent-write-targets--efs-conditioned-on-the-blocker-finding) rule |

**What varies per run, and only this:**

1. **`terraform.tfvars`** — the values. Write each with its origin as a comment (`# BLK-002 (in_process_session): cart held in HttpSession`), which is how the [traceability rule](#value-traceability) is satisfied mechanically.
2. **`session_affinity_required`** — `true` only when the `in_process_session` blocker exists. The `stickiness` block itself stays in the skeleton either way; the variable decides. This is deliberate: a reviewer can see that the decision was *made* rather than that the block was forgotten.
3. **The EFS fragment** — added, renamed to `efs.tf`, and wired into the task definition **only** when a `local_state` finding was classified persistent. Both shapes — skeleton alone, and skeleton plus fragment — are `terraform validate`-clean as shipped.

**`validate` is not `plan`, and the difference has bitten this skeleton.** `terraform validate` checks syntax and references without resolving values, so it passes on configurations that cannot plan. The EFS fragment originally keyed its mount targets with `for_each = toset(local.subnet_ids)`; in CREATE mode those ids do not exist until apply, and `for_each` keys must be known at plan time, so `terraform plan` failed outright with *"Invalid for_each argument … cannot be determined until apply"* while `validate` stayed green. The fragment now uses `count`, whose value is known in both modes. Both network modes have since been **plan-verified** with the fragment added — but the general rule is what matters: when a generated shape depends on values, a clean `validate` is necessary and not sufficient. Say which check was run, and do not describe `validate` coverage as though it were plan coverage.

### What "verified" means here, and what the skeleton is not

The skeleton is verified in a specific, limited sense: it formats, validates, plans and has been applied and destroyed against a real account. That is **not** the same as production-hardened, and it must not be presented as a hardened baseline. As shipped it carries, deliberately:

| As shipped | Why, and what to do before production |
|---|---|
| **HTTP:80 only, no TLS** | The skeleton ships no certificate, and inventing an ACM domain would be a fabricated value. Add an HTTPS listener with a real certificate and redirect 80 → 443 |
| **Egress `0.0.0.0/0`** | The unmodified application's outbound dependencies are not known from source analysis. Narrow it once they are enumerated |
| **ECS Exec off by default** | Turning it on with no `execute_command_configuration` means an unaudited interactive shell. Enable it deliberately, and pair it with cluster-level Exec logging |
| **No Container Insights** | Left off so the exercise's CloudWatch cost is near zero. Enable it for anything you intend to operate |
| **IMDSv2 required, hop limit 1** | Already set — the hop limit is what keeps bridge-networked containers off the instance credentials |

State this boundary when handing the environment over, and name **`ecs-security`** for the hardening pass. A migration cutover environment and a production environment are not the same artifact, and the difference is the user's to close.

**Deviating from the skeleton.** A concrete migration finding may require something the skeleton does not carry (a second port, a sidecar, an extra egress rule). Add it, and state in the Execution_Log what was added and which finding required it. What is not permitted is silently changing the four elements that define this path — `bridge` networking, `hostPort = 0`, `target_type = "instance"`, and the fixed-count-no-scaling service. Changing those makes it a different path, and the approved strategy no longer describes what was built.

**Why this order:** the approved-path check (step 1) gates everything, because generating an ECS on EC2 environment for a path the user approved as Fargate is a worse outcome than generating nothing. The conditioned elements (step 4) are resolved before generation so that stickiness and volumes are present exactly when their grounding findings are, rather than being added or removed after the fact. `terraform validate` (step 6) precedes any success report: unvalidated Terraform is not a deliverable.

---

## terraform-skill Conventions Conformance

The generated code conforms to the repository `terraform-skill`'s conventions — the same requirement the Windows sibling carries, for the same reason: a user who already has Terraform in the repository should not receive code in a foreign style.

- **Read the conventions before generating.** If the terraform-skill files cannot be read, apply the [edge case](#the-terraform-skill-files-cannot-be-read) — report the gap and generate with conservative, documented defaults rather than silently improvising a style.
- **Pinned versions** — `required_version` and provider `version` constraints are explicit, never floating.
- **Variables carry `description` and `type`**; defaults only where a default is genuinely safe.
- **Outputs expose what the next step needs** — at minimum the ALB DNS name, the cluster name, and the service name, because [deploy-verify-handoff.md](deploy-verify-handoff) needs them for steady-state verification.
- **No secrets in the code** — secret values arrive via task-definition `secrets` referencing SSM/Secrets Manager, never as literals or variable defaults.

---

## Generated Elements

Every element below is generated with its grounding stated. The elements marked **conditioned** are generated **only** when their grounding finding exists — generating them unconditionally is an error, because it would silently add infrastructure the analysis did not justify.

### Cluster and capacity — EC2 Auto Scaling group

The Replatform path's target compute model is **ECS on EC2** ([replatform-path.md](replatform-path)), so capacity is an Auto Scaling group of container instances:

- **Cluster** — one ECS cluster.
- **Launch template** — the **ECS-optimized AMI**, resolved from the SSM public parameter rather than a hardcoded AMI id, so the code stays valid as AMIs are refreshed: `/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id` ([ECS-optimized AMI parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/retrieve-ecs-optimized_AMI.html)). The instance profile carries `AmazonEC2ContainerServiceforEC2Role`, and the user data writes `ECS_CLUSTER` into `/etc/ecs/ecs.config` — without that the instances never join the cluster.
- **Instance type and count** — from the capacity derivation of the Replatform path (per-task footprint × fixed task count ÷ instance capacity, plus N+1 headroom, across ≥ 2 AZs). When the derivation could not produce numbers because the current-environment inputs were not in evidence, they become input variables with the derivation stated in their `description` — never invented values.
- **Capacity provider vs launch type** — either is valid for this path; state which was generated and why. A `launch_type = "EC2"` service is the simpler mapping of "fixed fleet, fixed count" and is the default here; an ASG capacity provider with managed scaling **disabled** is the alternative when the user wants the capacity-provider abstraction. Note which direction is reversible before choosing. A service created with `launch_type` (as here) can later move to a capacity-provider strategy **in place** via `UpdateService`, and — because it was created with a launch type — can also revert **in place** by passing an empty `capacityProviderStrategy`. The genuinely one-way case is the opposite starting point: a service created *with* a capacity-provider strategy has no original launch type to revert to and cannot be switched to one without recreating the service ([capacity/launch-type comparison](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html)). Never emit both on one service — they are mutually exclusive.

### Task definition — bridge mode and dynamic host ports

This is the element `ecs-build` cannot generate, and the reason this module exists:

- **`network_mode = "bridge"`** — the unmodified application is not being adapted to per-task ENIs, and `bridge` allows several tasks per instance without ENI density limits. State the grounds: this is a containerize-as-is path, and `awsvpc` would change the network model the application and its operators know.
- **Dynamic host port mapping** — `hostPort = 0` against the application's `containerPort`, so ECS assigns an ephemeral host port and multiple tasks of the same service coexist on one instance ([dynamic port mapping](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-load-balancing.html)). The ALB target group discovers the assigned port through the service registration; the container-instance security group must therefore admit the **ephemeral port range** from the ALB security group, not a single fixed port.
- **`containerPort`** — from the containerization artifact (the Dockerfile `EXPOSE` / task-definition input values), never guessed.
- **CPU/memory** — from the containerization artifact's task-definition input values, grounded in the capacity derivation. Memory is a hard reservation on EC2: set it below the instance's allocatable memory or tasks never place.
- **Log configuration** — the `awslogs` driver to a generated log group, which is the "changed" side of the Replatform path's operational-procedures table (host log tailing becomes the container log driver).
- **Execution role** — for image pull and log writes. **Task role**: generated only when the application actually calls an AWS API, or when the environment needs ECS Exec for the diagnostics the operational-procedures table names; otherwise omitted, and the omission stated as deliberate least privilege.

### Service — fixed desiredCount, no scaling policy

- **`desired_count`** — the fixed value from the static configuration template. When the current instance count was not in evidence, it is an input variable whose `description` states that parity with the current environment is the derivation basis. **No `aws_appautoscaling_target` and no scaling policy is generated** — their absence is the static configuration, and it is stated explicitly rather than left as a silent omission.
- **Deployment configuration** — the deployment circuit breaker with rollback enabled is a safe default for a first containerized deployment; state it as a generated default so the user can decline it.
- **Placement across AZs** — the `spread` strategy across `attribute:ecs.availability-zone`, so the fixed fleet's failure characteristics match the multi-AZ capacity plan.

### Load balancer — session affinity conditioned on the Blocker finding

- **ALB, listener, target group** — the target group's `target_type` is **`instance`** (the correct pairing with `bridge` mode and dynamic host ports; `ip` targets belong to `awsvpc`).
- **Health check** — the path from the app-provided health endpoint when Source_Analysis identified one (cite the finding); otherwise the application's root path, with the substitution stated.
- **`stickiness` — conditioned.** Generate the target group's `stickiness` block **enabled** exactly when the `in_process_session` Blocker was detected, and cite the Blocker id in a comment on the block. When the Blocker was **not** detected, generate `stickiness` **disabled** (or omit it) and state that the absence of the finding is the grounds. Carry the constraint the Replatform path states: affinity keeps a user on one task but does **not** survive that task's replacement — sessions are still lost then. Never generate stickiness unconditionally: an application with no session state does not need it, and enabling it would degrade load distribution for no reason.
- **When the session state is unknown** (assessment skipped, or the tWAS-style caveat where server-side session persistence lives outside the source tree) — apply the [edge case](#the-assessment-was-skipped-and-session-state-is-unknown): generate affinity **enabled** as the fail-safe and state that it is provisional pending user confirmation.

### Persistent write targets — EFS conditioned on the Blocker finding

- **Conditioned on the `local_state` findings** and the Replatform path's persistent-vs-temporary mapping. For each write target classified **persistent**, generate an EFS file system, mount targets in the task subnets, an access point, and the task-definition `volumes` + `mountPoints` entry at that path — citing the Blocker id and the classification.
- **Targets classified temporary** get no volume: container-local storage is correct for them, and that decision is stated rather than silently applied.
- **When no `local_state` finding exists**, generate no volume and state the not-needed conclusion with its grounds. This is the same explicit-absence discipline as stickiness.
- The EFS security group admits NFS (2049) from the container-instance security group only.

### Supporting inputs and resources

- **VPC and subnets — two modes, neither of them the default.** Which one applies is a decision to settle from the migration's actual starting point, not an assumption:
  - **CREATE** — the target network does not exist yet. This is the normal case for an **on-premises or VMware migration**, and for any move into a fresh account or a landing-zone spoke. The skeleton builds a VPC, two subnets across two AZs, an internet gateway, and routes.
  - **REUSE** — an existing VPC receives the workload. Typical when the source already runs on EC2 in the same account, or when a landing zone dictates the network. The skeleton creates no network resources and never modifies the supplied VPC.

  **Never assume an existing VPC:** a migration from outside AWS has none, so requiring `vpc_id` would block the most common lift-and-shift starting point. State which mode was chosen and why. In CREATE mode, also state the CIDR choice — it must not overlap the source environment's network, since an overlap breaks the hybrid connectivity a cutover usually needs. Public-subnet container instances need public IPs or a NAT route to pull images; the choice and its cost implication are stated either way.
- **Security groups** — one for the ALB (ingress from the user-specified CIDR, defaulting to nothing wider than the user approves), one for the container instances (ingress from the ALB SG on the **ephemeral port range**, per the dynamic-port design).
- **Log group** — with an explicit `retention_in_days`; an unset retention means "never expire", which is a cost surprise rather than a default.

---

## Unresolved Image URI — Input Variable Rule

Identical to the Windows sibling's rule, because the situation is identical: the environment can be generated before the image exists.

When the image URI is not resolved at generation time (the push has not run, or it failed):

- **Define it as a Terraform input variable** (`image_uri`) with no default, and a `description` naming the condition that settles it (typically "the ECR push of the containerization execution").
- **Generate the rest of the environment normally** — an unresolved URI never blocks generation.
- **Record the item as unresolved** in the Execution_Log and in the module output, with its settling condition. Never invent a placeholder URI that would apply successfully against the wrong image, and never silently substitute `:latest`.
- The deploy procedure ([deploy-verify-handoff.md](deploy-verify-handoff)) will not apply until the variable has a value; state that dependency at hand-off.

---

## terraform validate — the Applicability Check

`terraform validate` is the **sole** applicability check for the generated code — the same rule the Windows sibling states, and for the same reason: it is the one check that runs without AWS credentials and without creating anything.

- **Run `terraform init` then `terraform validate`** in the output directory after generation.
- **On failure:** fix the generated code and re-validate. Do **not** report the generation as successful while validate fails, and do not hand the code to the deploy procedure. If it cannot be made to validate, report exactly what fails and hand over the partial code labelled as not-validating.
- **`terraform fmt`** is run as well, so the delivered code is canonically formatted.
- **What validate does not check:** whether the AMI parameter resolves in the target region, whether the instance type is available in the chosen AZs, whether quotas allow the fleet. Those surface at `plan`/`apply` time — say so rather than implying validate proves deployability.
- **When terraform is not installed or `init` cannot fetch providers** — see the [edge case](#terraform-is-not-installed--init-cannot-fetch-providers): report the gap honestly and mark the code as generated-but-unvalidated. Never claim a validation that did not run.

---

## Value Traceability

Every value in the generated code is traceable to its origin, and the origin is stated in a comment or the variable `description`:

| Generated value | Origin |
|---|---|
| Image URI | The containerization execution push result, or the input variable and its settling condition |
| Container port | The containerization artifact (`EXPOSE` / task-definition inputs) |
| Health check path | The app-provided health endpoint finding from Source_Analysis, or the stated substitution |
| CPU / memory | The containerization artifact's task-definition input values |
| `desired_count` | The static configuration template's fixed count, or the input variable with the parity derivation in its description |
| Instance type and count | The capacity derivation policy inputs, or input variables with the derivation stated |
| `stickiness` enabled/disabled | The `in_process_session` Blocker id, or the explicit absence of that finding |
| EFS volumes | The `local_state` Blocker ids and their persistent classification |

A value with no traceable origin is not generated as a settled value: it becomes an input variable with its settling condition, or the generation reports it as unresolved.

---

## Execution_Log

Record, per the canonical [Execution_Log Rules](deploy-verify-handoff#execution_log-rules):

- the file-generation action-class confirmation and the output directory presented at confirmation time;
- every file written, by path;
- the `terraform fmt` and `terraform validate` results (and, on failure, the fixes applied and the re-validate result);
- every unresolved item with its settling condition;
- the conditioned elements' resolutions — stickiness enabled/disabled and why, volumes generated or not and why — so the log shows the findings drove the infrastructure.

---

## Output Schema

```yaml
replatform_environment_build:
  approved_path: string            # the Linux Replatform path this environment targets
  output_directory: string         # the confirmed generation destination
  files: [string]                  # every file written, by path
  compute:
    capacity_model: launch_type_ec2 | asg_capacity_provider
    rationale: string              # why this one, incl. the reversibility asymmetry note
    instance_type: {value: string, source: string} | unresolved
    instance_count: {value: int, source: string} | unresolved
  task_definition:
    network_mode: bridge           # always bridge on this path
    container_port: {value: int, source: string}
    host_port: 0                   # dynamic mapping
    cpu: {value: int, source: string} | unresolved
    memory: {value: int, source: string} | unresolved
    task_role: generated | omitted
    task_role_rationale: string    # why generated (AWS API use / ECS Exec) or why omitted
  service:
    desired_count: {value: int, source: string} | unresolved
    autoscaling: none              # always none on this path — stated, not omitted
  load_balancer:
    target_type: instance          # always instance with bridge + dynamic ports
    health_check_path: {value: string, source: string}
    stickiness:
      enabled: bool
      grounds: string              # the in_process_session blocker id, or its explicit absence
      provisional: bool            # true when enabled as the unknown-session fail-safe
  volumes:                         # empty list => the explicit not-needed statement is required
    - {path: string, blocker_id: string, mechanism: efs}
  unresolved_items:
    - {item: string, settles_when: string}
  validation:
    fmt: passed | failed | not_run
    validate: passed | failed | not_run
    not_run_reason: string | null   # required when either is not_run
```

**Reporting invariants:**

- `network_mode` is always `bridge` and `target_type` always `instance` on this path; a generated `awsvpc` task definition here is an error.
- `service.autoscaling` is always `none`, and its absence is stated in the report rather than left implicit.
- `load_balancer.stickiness.grounds` is non-empty in every output — either a Blocker id or the explicit absence statement.
- `volumes: []` obliges the explicit not-needed statement with its grounds.
- `validation.validate: passed` requires an actual successful run; `not_run` requires a reason.
- Every unresolved item carries its settling condition; none is silently dropped.

---

## Edge Cases

### The approved path is a Rearchitect compute model

This module does not run. Express Mode, Fargate, and Managed Instances environments are `ecs-build`'s scope — hand off per [deploy-verify-handoff.md](deploy-verify-handoff). Generating an ECS on EC2 environment for an approved Fargate path contradicts the approval.

### The approved path is the Windows_Container_Path

This module does not run; [windows-environment-build.md](windows-environment-build) owns it. The Windows path has its own compute options (ECS on EC2 Windows instances / Fargate Windows) and licensing considerations that this module does not carry.

### The assessment was skipped and session state is unknown

Generate `stickiness` **enabled** as the fail-safe, and state explicitly that it is provisional: the `in_process_session` finding that would justify it was never established, so the user must confirm whether the application holds server-side session state. The same applies to the tWAS caveat where session persistence is cell configuration outside the source tree ([blocker-detection.md](blocker-detection)).

### The image URI is unresolved

Apply the [input variable rule](#unresolved-image-uri--input-variable-rule). Generation proceeds; the item is recorded as unresolved with its settling condition.

### The terraform-skill files cannot be read

Report the gap explicitly, then generate with conservative documented defaults (pinned versions, described variables, no secrets in code) and state that conventions conformance could not be verified against the repository's terraform-skill.

### terraform is not installed / init cannot fetch providers

Report exactly what could not run and why. Deliver the generated code labelled **generated but not validated**, set `validation.validate: not_run` with the reason, and present the commands the user can run themselves. Never claim a validation that did not happen.

### terraform validate fails on the generated code

Fix the code in the output directory and re-validate. Report the failure, the fix, and the re-validate result. If it cannot be made to validate, hand over the code labelled as not-validating with the exact error — do not report success.

### The user refuses the file-generation action class

Do not write files. Present the complete Terraform content in conversation so the user can create it themselves, and state that the deploy procedure's `terraform apply` cannot proceed until the code exists on disk.

### The output destination changes after confirmation

Re-obtain the file-generation confirmation presenting the changed directory before writing anything there, per the re-confirmation rule.

### Sizing inputs are missing

Instance type, instance count, CPU, memory, or `desired_count` not in evidence: generate each as an input variable whose `description` names the derivation basis (parity with the current environment; peak-load capacity derivation with N+1 headroom). Never invent a number, and never omit the variable so that apply fails obscurely.

### The user asks `ecs-build` to generate the Replatform environment

State the gap rather than routing the request: `ecs-build` generates `awsvpc` task definitions and capacity-provider services exclusively, and carries no `stickiness`, `bridge`, or dynamic-host-port knowledge — so it cannot produce this path's shape. This module generates it instead. If `ecs-build` later gains that coverage, the delegation replaces this module per the note in [SKILL.md](../).

---

## Sources

- Retrieving ECS-optimized AMI ids from SSM public parameters: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/retrieve-ecs-optimized_AMI.html
- VPC CIDR planning and non-overlapping ranges (why the CREATE-mode CIDR must not collide with the source network): https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cidr-blocks.html
- ECS task networking modes (`bridge`, `awsvpc`, `host`): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking.html
- Service load balancing and dynamic host port mapping: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-load-balancing.html
- ALB target group stickiness (duration-based, application-based): https://docs.aws.amazon.com/elasticloadbalancing/latest/application/sticky-sessions.html
- ECS capacity providers vs launch types, and the mutability asymmetry: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html
- ECS deployment circuit breaker with rollback: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html
- Task placement strategies (`spread` across AZs): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement-strategies.html
- Amazon EFS volumes in ECS task definitions: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html
- Using ECS Exec for container diagnostics (task-role requirements): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html
- Using the awslogs log driver: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html
