---
title: "Module: Windows Environment Build"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/windows-environment-build.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/references/windows-environment-build.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/windows-environment-build.md). Edit the source, not this page.
:::

# Module: Windows Environment Build

> **Part of:** [ecs-modernize](../)
> **Purpose:** Generate the Windows_Environment_Terraform for an approved Windows_Container_Path — cluster and capacity conditioned on the approved compute option (ECS on EC2 Windows instances or Fargate Windows), a task definition with the Windows `runtime_platform`, the service, and the load balancer (with session affinity when the in-process session Blocker was detected) — conforming to the repository terraform-skill's conventions, verified by `terraform validate` as the sole applicability check, with an unresolved image URI handled as a Terraform input variable
> **Prerequisites:** **Execution_Gate passage** (Requirement 14) + **Containerization execution** ([containerization-execution.md](containerization-execution)) — the image URI for the task definition; when the URI is unresolved, define it as a Terraform input variable per the [unresolved image URI rule](#unresolved-image-uri--input-variable-rule)

This module builds the target environment for the **Windows_Container_Path** (Requirement 17.2). It exists because **`ecs-build`'s generation scope is limited to Linux containers** — there is no sibling skill that generates Windows container environments, so this skill generates the Windows_Environment_Terraform itself. State that rationale explicitly whenever this module runs: the user should know *why* the Linux paths hand off to `ecs-build` (see [deploy-verify-handoff.md](deploy-verify-handoff)) while the Windows path does not. Never route a Windows container path environment IaC request to `ecs-build` (Requirement 12.5); the delegation boundary and the future-support note — if `ecs-build` gains Windows container generation, this module's generation is replaced by a delegation — are canonical in [SKILL.md](../).

This module is ECS-specific: it depends on the ECS resource model (cluster, capacity provider, task definition `runtime_platform`, service) and does not port to other orchestrators.

**Scope boundary:** this module ends at a validated Terraform configuration. It never runs `terraform plan` or `terraform apply` — the pre-apply destroy check, the apply confirmation, and steady-state verification belong to [deploy-verify-handoff.md](deploy-verify-handoff). Detailed design values (capacity-provider strategy tuning, task sizing numbers, network design) remain delegated to `ecs-architect` per [SKILL.md](../); this module wires the environment from the values the migration produced, it does not design new ones.

## Table of Contents

- [Inputs](#inputs)
- [Generation Flow](#generation-flow)
- [terraform-skill Conventions Conformance](#terraform-skill-conventions-conformance)
- [Generated Elements](#generated-elements)
  - [Cluster and capacity — conditioned on the approved compute option](#cluster-and-capacity--conditioned-on-the-approved-compute-option)
  - [Task definition — Windows runtime_platform](#task-definition--windows-runtime_platform)
  - [Service](#service)
  - [Load balancer — session affinity conditioned on the Blocker finding](#load-balancer--session-affinity-conditioned-on-the-blocker-finding)
  - [Supporting inputs and resources](#supporting-inputs-and-resources)
- [Unresolved Image URI — Input Variable Rule](#unresolved-image-uri--input-variable-rule)
- [terraform validate — the Applicability Check](#terraform-validate--the-applicability-check)
- [Value Traceability](#value-traceability)
- [Determination Criteria](#determination-criteria)
- [Execution_Log](#execution_log)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **Execution_Gate passage** (required) — the gate's two conditions hold AND the approved target path is the Windows_Container_Path. This module never runs before the gate.
- **The approved compute option** (required) — exactly one of **ECS on EC2 Windows instances** or **Fargate Windows support**, as approved with the target path at the gate. If the approval did not uniquely identify the compute option, do not pick one: re-present both options (with the three-item comparison from [replatform-path.md — Compute Options for Windows Containers](replatform-path#compute-options-for-windows-containers)) and obtain an unambiguous choice first (the Requirement 14 discipline).
- **Containerization execution results** ([containerization-execution.md](containerization-execution)) — the **image URI** from the push result (or its unresolved status), and the **task-definition input values** (container name, port mappings, CPU/memory sizing inputs, `environment` / `secrets` entries, mount points, health check, log configuration). These are the source of truth for the task definition this module generates.
- **Source_Analysis findings** (when the assessment ran) — the **in-process session state Blocker** finding (present/absent, with its Blocker id) drives the [session affinity decision](#load-balancer--session-affinity-conditioned-on-the-blocker-finding); persistent-write-target findings surface the storage constraints of the chosen compute option (see [Edge Cases](#edge-cases)).
- **The Requirement 14-confirmed output destination** — the Terraform output paths presented at the **file generation** action-class confirmation. The [output destination rules of containerization-execution.md](containerization-execution#output-destination-rules) apply identically to every file this module writes: user-approved destination, outside the target source directory unless an in-repository write was explicitly approved, re-confirmation on destination change.
- **The repository terraform-skill's conventions** — read BEFORE generating, per [terraform-skill Conventions Conformance](#terraform-skill-conventions-conformance).

---

## Generation Flow

Run the steps in this order. Every attempted action is recorded per the [Execution_Log](#execution_log) rules before the next action starts.

```
0. Verify the gate and prerequisites   -> Execution_Gate passed; Windows_Container_Path
                                          approved with a unique compute option;
                                          containerization execution state known
1. State the generation rationale      -> ecs-build generates Linux container
                                          environments only; this skill generates the
                                          Windows_Environment_Terraform itself
2. Read the terraform-skill conventions-> block ordering, variable/output contracts,
                                          file layout, version constraints (below)
3. File-generation confirmation        -> action class of Req 14, presenting the
                                          Terraform output paths (approved destination)
4. Resolve the image URI status        -> settled (full URI from the Req 16 push) or
                                          unresolved (-> input variable rule)
5. Generate the Terraform              -> the four generated elements, conforming to
                                          the terraform-skill conventions
6. Run terraform validate              -> init -backend=false, then validate, in the
                                          output directory
7. Report                              -> generated files + roles, validate outcome
                                          (applicability claim ONLY on error-free
                                          completion), value traceability, and any
                                          unresolved items with their remaining work
```

**Why this order:** the conventions read (step 2) precedes generation because Requirement 17.4 makes conformance a precondition of generation, not a cleanup pass. The file-generation confirmation (step 3) precedes generation because files may only be written into the user-approved destination. The image URI status (step 4) is resolved before generation because it changes what is generated (a literal reference vs. an input variable). Validation (step 6) follows generation completion because Requirement 17.7 attaches the applicability check to the completed configuration.

---

## terraform-skill Conventions Conformance

(Requirement 17.4 — read the conventions BEFORE generating, and make the generated code conform.)

The repository ships a dedicated Terraform authoring skill. **Before generating any Terraform, read:**

- [terraform-skill/SKILL.md](../../../general/terraform-skill/) — the convention summary (naming, block ordering, file layout, version management),
- [terraform-skill/references/code-patterns.md](../../../general/terraform-skill/references/code-patterns) — the full block-ordering rules, variable/output structure, `count` vs `for_each` decision rules, and version-constraint syntax,
- [terraform-skill/references/module-patterns.md](../../../general/terraform-skill/references/module-patterns) — variable/output contracts and naming conventions.

The generated Windows_Environment_Terraform conforms to at least the following (summarized here for orientation; the terraform-skill files are the authoritative source — where this summary and the live files disagree, the live files win):

| Convention | What the generated code honors |
|---|---|
| **Resource block ordering** | `count` / `for_each` first (blank line after) → other arguments → `tags` as the last real argument → `depends_on` → `lifecycle` at the very end |
| **Variable block ordering & contract** | `description` (always) → `type` (always explicit) → `default` → `sensitive` (secrets) → `nullable` → `validation`. Prefer `optional()` with typed defaults over untyped maps |
| **Output contract** | Always `description`; name as `{name}_{type}_{attribute}` (e.g. `service_name`, `alb_dns_name`); never a `this_` prefix; mark sensitive outputs |
| **Naming** | Descriptive resource names (`aws_ecs_service.app`, not `aws_ecs_service.main`); reserve `this` for genuine singletons; prefix variables with context (`image_uri`, `alb_subnet_ids`, not `uri`, `subnets`) |
| **File layout** | Standard files: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf` in the approved output directory |
| **Version constraints** | `versions.tf` pins the runtime to a minor (`required_version = "~> 1.x"`) and the AWS provider to a major (`version = "~> N.0"`), per the terraform-skill version-management table |
| **`count` vs `for_each`** | Boolean toggles use `count = condition ? 1 : 0`; keyed collections use `for_each`; never a list index as long-lived identity |
| **Secrets** | No secret values in variables, defaults, or state-bound arguments — task `secrets` entries reference SSM Parameter Store / Secrets Manager ARNs, mirroring the Containerization_Artifact's config intake method. Credential values never appear in the generated files (the all-phases non-disclosure invariant of [SKILL.md](../)) |

**If the terraform-skill files cannot be read** (missing or unreadable): do not silently generate. Report the load failure, and ask the user whether to proceed in a degraded mode using only the summary table above — stating explicitly that conformance to the live conventions could not be verified — or to stop until the skill is available.

---

## Generated Elements

(Requirement 17.3 — the generated Terraform contains at least the four elements below. Every generated value follows the [Value Traceability](#value-traceability) rule.)

### Cluster and capacity — conditioned on the approved compute option

Generate exactly the capacity model of the **approved** compute option — never both, never the unapproved one.

**Approved option: ECS on EC2 Windows instances**

| Element | Content |
|---|---|
| Cluster | `aws_ecs_cluster` (Windows and Linux tasks do not share container instances — a dedicated cluster keeps the boundary clean) |
| Windows container instances | Launch template on an **Amazon ECS-optimized Windows AMI** (resolve the AMI via the SSM public parameter for the chosen Windows Server release, e.g. `/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-ECS_Optimized/image_id`), instance profile with the ECS container-instance role, and Windows user data (`<powershell>Initialize-ECSAgent -Cluster ...</powershell>`) joining the cluster |
| Capacity | `aws_autoscaling_group` sized per the Replatform static configuration template (fixed capacity from the assessed peak-load calculation — [replatform-path.md](replatform-path)), an `aws_ecs_capacity_provider` bound to the ASG, and `aws_ecs_cluster_capacity_providers` attaching it |
| Version coupling | The Windows Server release is **one decision across three places**: the AMI, the base-image tag of the pushed image (ltsc2019 / ltsc2022 / ltsc2025 — process isolation requires host/image version match), and the task definition's `runtime_platform` family. Generate them from a single variable/local so they cannot drift. Confirm the chosen base image actually publishes a tag for the selected release — e.g. .NET Framework 4.x has no `4.8` ltsc2025 tag, so a Windows Server 2025 host uses `4.8.1-windowsservercore-ltsc2025` ([replatform-path.md](replatform-path#windows-base-image-selection-matrix)) |

**Approved option: Fargate Windows support**

| Element | Content |
|---|---|
| Cluster | `aws_ecs_cluster` with `aws_ecs_cluster_capacity_providers` attaching `FARGATE` (Fargate **Spot** is not available for Windows — do not attach it) |
| Capacity | No instances to manage — capacity is expressed by the service's Fargate launch configuration and the task definition's `requires_compatibilities = ["FARGATE"]` |
| Constraints honored | The generated configuration must not use features unavailable on Fargate Windows — no EFS / EBS / FSx volumes, no FireLens, and the other constraints listed in [replatform-path.md — Compute Options](replatform-path#compute-options-for-windows-containers). Re-verify the constraint list against the live Windows-considerations documentation before generating; these facts change |

### Task definition — Windows runtime_platform

`aws_ecs_task_definition` with an explicit Windows **`runtime_platform`** block (Requirement 17.3):

```hcl
runtime_platform {
  operating_system_family = "WINDOWS_SERVER_2022_CORE" # or _FULL / 2019_CORE / 2019_FULL — match the pushed base image
  cpu_architecture        = "X86_64"                   # Windows containers are x86_64 only
}
```

- **`operating_system_family`** matches the Windows Server release and Full/Core edition of the **pushed container image's base** (from the Windows base-image matrix selection in [replatform-path.md](replatform-path) as realized by the Containerization_Artifact). On Fargate, the family must be one the platform supports (2019/2022 families at the time of writing — re-verify); on EC2, it must match the container-instance OS.
- **Container definition** values come from the Containerization_Artifact's task-definition input values ([containerization-execution.md](containerization-execution)): container name, the image reference (the settled URI or the [input variable](#unresolved-image-uri--input-variable-rule)), port mappings, CPU/memory, `environment` / `secrets` entries per the confirmed config intake method, health check, and `awslogs` log configuration (with the log group generated alongside).
- **Set the `awslogs` `mode` explicitly.** Since 2025-06-25 an unset mode defaults to `non-blocking`, and a non-blocking driver buffers up to its `max-buffer-size` — **10 MiB by default** (the ECS `max-buffer-size` default is `10m`, per the [ECS `LogConfiguration` API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html)) — before it starts discarding lines, which lands precisely on the steady-state verification that follows, where the logs are the diagnosis. Generate `mode` plus, in non-blocking mode, a `max-buffer-size` widened beyond the 10 MiB default when a chatty legacy application warrants it; choose `blocking` only when complete logs matter more than task availability, and say so. This applies identically to the Replatform skeleton ([replatform-environment-build.md](replatform-environment-build)).
- `network_mode = "awsvpc"` on Fargate (required); on EC2 Windows, use the mode the task-definition input values specify (`default`/NAT is the Windows-native mode on EC2; `awsvpc` where the inputs call for it).
- Honor the Windows task-definition parameter differences (several Linux parameters are unsupported or behave differently on Windows — see Sources) — do not carry Linux-only parameters into the Windows task definition.

### Service

`aws_ecs_service` wiring the task definition to the capacity:

- **Desired count is a fixed value** per the Replatform static configuration template (no autoscaling resources are generated — the Windows_Container_Path is a Replatform variant and inherits the static-configuration discipline of [replatform-path.md](replatform-path)).
- **Launch configuration matches the approved option**: capacity-provider strategy referencing the generated EC2 capacity provider, or `launch_type = "FARGATE"` (with `platform_version` left to the current Windows-supporting default).
- Load-balancer attachment referencing the target group below; deployment settings stay at conservative defaults (this module does not design deployment strategy — that is `ecs-devops` / `ecs-architect` territory).

### Load balancer — session affinity conditioned on the Blocker finding

Application Load Balancer, target group, and listener fronting the service:

- `aws_lb` (application), `aws_lb_target_group` (target type per the network mode: `instance` for EC2/NAT mode with dynamic port mapping, `ip` for `awsvpc`), `aws_lb_listener`, and the security groups they need.
- **Session affinity (Requirement 17.3):**
  - **The in-process session state Blocker was detected** (Source_Analysis, category `in_process_session`) → generate the target group **stickiness** configuration (`stickiness { type = "lb_cookie" ... enabled = true }`), cite the Blocker id as the grounds, and repeat the assessed constraint in the report: sessions on a task are lost when that task stops or is replaced ([replatform-path.md — In-Process Sessions](replatform-path#in-process-sessions-alb-sticky-sessions)).
  - **The Blocker was not detected** (the assessment ran and found none) → no stickiness configuration; cite the absence as the grounds.
  - **No Blocker information exists** (the assessment was skipped) → do not guess in either direction: ask the user whether the application keeps in-process session state, and generate per the answer, recording the answer as the grounds.

### Supporting inputs and resources

- **Existing network identifiers enter as input variables** — VPC ID, subnet IDs (ALB and service), and any pre-existing security group references are typed, described variables. This module does not create VPCs or subnets: AWS resource creation stays limited to the resources enumerated in the approved migration plan ([SKILL.md](../) safety rails); networking that is not in the plan is an input, not a resource.
- IAM roles generated are limited to what the environment needs: the task execution role (ECR pull, logs, and `secrets` access per the config intake method), the task role when the app needs AWS API access, and (EC2 option) the container-instance role. No delete-granting or plan-external permissions.
- Every generated file is reported with its role, e.g.:

| File | Role |
|---|---|
| `<dest>/main.tf` | Cluster + capacity (per the approved option), task definition with the Windows `runtime_platform`, service, ALB/target group/listener, IAM roles, log group |
| `<dest>/variables.tf` | Typed, described inputs — network identifiers, sizing inputs, and `image_uri` (variable form per the unresolved rule when applicable) |
| `<dest>/outputs.tf` | Described outputs (e.g. `alb_dns_name`, `service_name`, `cluster_arn`) |
| `<dest>/versions.tf` | `required_version` (minor-pinned) + `required_providers` (major-pinned AWS provider) |

---

## Unresolved Image URI — Input Variable Rule

(Requirement 17.9 — applies when, at generation time, the image URI for the task definition is not settled: the Requirement 16 build or push has not run, failed, or the remote-build path has not been started/completed.)

1. **Define the image URI as a Terraform input variable** — typed, described, no default:

   ```hcl
   variable "image_uri" {
     description = "Complete ECR image URI (registry/repository:tag) of the pushed Windows container image. Unresolved at generation time - supply after the image is pushed (see the report's remaining-work list)."
     type        = string
   }
   ```

   The task definition's container `image` references `var.image_uri`. The configuration stays `terraform validate`-clean with the variable unset; the value is supplied at plan/apply time (e.g. via `-var` or a `.tfvars` file).

2. **Report that the value is unresolved** — never imply the environment is ready to apply end-to-end while the URI is missing.

3. **Report the remaining work to settle it**, concretely, including the Requirement 16 remote-build path where it applies:
   - **Windows image × non-Windows host**: complete the CodeBuild remote build ([containerization-execution.md — remote build](containerization-execution#windows-image-on-a-non-windows-host--remote-build)) — the build definition exists (or is generated on request); starting the build requires its own explicit confirmation; the push then yields the URI.
   - **Build/push failed or declined**: the manual build-and-push procedure from [containerization-execution.md](containerization-execution), after which the user reports the pushed URI.
   - Then: supply the URI as the `image_uri` variable value before `terraform plan` / `apply` in [deploy-verify-handoff.md](deploy-verify-handoff).

When the URI **is** settled, reference the complete pushed URI (traceable to the Requirement 16 push result). Either way the schema records which form was used (`image_uri_variable`).

---

## terraform validate — the Applicability Check

(Requirements 17.7, 17.8 — `terraform validate` is the confirmation of applicability. Nothing weaker substitutes for it, and nothing about a failed or impossible validation is papered over.)

**When:** after the generation of the Windows_Environment_Terraform completes.

**How:** in the output directory, run — as separate commands —

1. `terraform init -backend=false` (installs providers so validation can resolve schemas; no backend/state is touched), then
2. `terraform validate`.

**Outcome handling:**

| Outcome | Report |
|---|---|
| `validate` completes **without errors** | Report the validation result AND that the configuration is **applicable** — `terraform apply` executable — with the error-free validation as the confirmation (Requirement 17.7). The apply itself still belongs to [deploy-verify-handoff.md](deploy-verify-handoff) with its destroy check and apply confirmation |
| `validate` exits **with errors** | Report the error content (the actual validator output, not a paraphrase). Do **NOT** claim the configuration is applicable. Fix and re-validate, or hand the errors to the user — but the applicability claim exists only after an error-free run |
| `validate` (or the init it needs) **cannot be executed** — no Terraform binary on the host, provider installation impossible (e.g. no network), or the command fails to run | Report the reason it could not be executed. Do **NOT** claim the configuration is applicable, and do not substitute a weaker check (a visual review is not `terraform validate`). Present the user the commands to run the validation themselves (the two commands above, with the output directory) |

Both `terraform_init` and `terraform_validate` attempts are recorded in the Execution_Log, success or failure alike.

---

## Value Traceability

Every concrete value placed in the generated Terraform — the image URI, ports, health check, CPU/memory sizing inputs, mount/volume decisions, the session-affinity decision — is reported **mapped to its origin**: the Requirement 16 output (Containerization_Artifact task-definition input values, push result) and/or the Source_Analysis finding that grounds it. This is the same traceability discipline as the `ecs-build` handoff in [deploy-verify-handoff.md — Rearchitect Compute-Model Handoff](deploy-verify-handoff#rearchitect-compute-model-handoff); a value with no traceable origin is not silently invented — it becomes an input variable or an explicit user-confirmed value, and the report says which.

---

## Determination Criteria

| Decision | Criterion |
|---|---|
| This module may run | Execution_Gate passed AND the approved target path is the Windows_Container_Path AND the approved compute option is uniquely identified — all three |
| Generation may start | The terraform-skill conventions were read (or the degraded mode was explicitly user-approved after a reported load failure) AND the file-generation action-class confirmation is complete for the current output paths |
| The compute option conditions the capacity code | ECS on EC2 Windows → cluster + Windows ASG + capacity provider; Fargate Windows → cluster + FARGATE capacity provider (no Spot) — exactly the approved one, never both |
| Session affinity is generated | The in-process session state Blocker was detected (or, assessment skipped, the user affirmed in-process session state) — otherwise no stickiness, with the grounds cited either way |
| The image URI is a variable | The URI is unresolved at generation time (build/push not run, failed, or remote build pending) — then Requirement 17.9's variable + unresolved report + remaining-work report all apply |
| "Applicable (apply-executable)" may be reported | `terraform validate` was executed AND completed without errors — both. Execution-impossible or error exit → the claim is forbidden; report the reason/errors instead |
| A generated value is settled | It traces to a Requirement 16 output and/or a Source_Analysis finding; otherwise it is an input variable or an explicitly user-confirmed value, reported as such |
| Windows path IaC goes to `ecs-build` | Never (Requirement 12.5) — until `ecs-build` gains Windows support, at which point the SKILL.md replacement note governs |

---

## Execution_Log

Every action this module attempts — the Terraform file generation, `terraform init`, `terraform validate` — is recorded in the **Execution_Log**, success or failure alike, before the next action starts. The recording rules, required fields, storage forms, and save-failure fallback are canonical in [deploy-verify-handoff.md — Execution_Log Rules](deploy-verify-handoff#execution_log-rules); this module records against them rather than restating them. Typical action types from this module: `file_generation`, `terraform_init`, `terraform_validate`.

---

## Output Schema

This module produces the windows side of the `environment_construction` block. Hold the structure in conversation context; the durable record is the Execution_Log.

```yaml
environment_construction:
  path: windows
  compute_option: ecs_ec2_windows | fargate_windows   # the approved option that conditioned the capacity code
  windows_terraform:
    output_dir: string                     # the Req 14-confirmed destination
    files:                                 # every generated file, with its role
      - {path: string, role: string}
    conventions_read: [string]             # the terraform-skill files read before generation
    degraded_conventions_mode: bool        # true only after a reported load failure + user approval
    validate:
      executed: bool
      result: pass | fail | unavailable    # unavailable = could not be executed (Req 17.8)
      errors: [string]                     # validator output on fail; the reason on unavailable
    image_uri_variable: bool               # true = unresolved URI defined as an input variable (Req 17.9)
    unresolved_remaining_work: [string]    # the work that settles the URI (incl. the Req 16 remote-build path)
    session_affinity:
      included: bool
      grounds: string                      # Blocker id / assessed absence / user answer (assessment skipped)
  value_traceability:                      # Req 17.6 — every used value mapped to its origin
    - {name: string, value: string, origin: string}
```

**Reporting invariants:**

- `files` is non-empty only after the conventions were read (or `degraded_conventions_mode: true` with its recorded approval) AND the file-generation confirmation completed — generation never precedes either.
- An applicability claim exists only when `validate.executed: true` AND `validate.result: pass`. `result: fail` carries the error content; `result: unavailable` carries the reason — and both forbid the claim.
- `image_uri_variable: true` always coexists with a non-empty `unresolved_remaining_work` and an explicit unresolved statement in the report.
- `session_affinity.grounds` is never empty — the stickiness decision is grounded in a Blocker id, an assessed absence, or a recorded user answer, in every case.
- Exactly one compute option's capacity resources appear in `files` — never both models in one generation.
- Every `value_traceability.origin` names a Requirement 16 output, a Source_Analysis finding, an input variable, or a user confirmation — never "assumed".

---

## Edge Cases

### The approved compute option cannot be uniquely identified

The gate approval named the Windows_Container_Path but not which compute option (or the response was ambiguous). Do not default to either: re-present ECS on EC2 Windows vs. Fargate Windows with the three-item comparison from [replatform-path.md](replatform-path) and obtain an unambiguous choice. Generation stays blocked until then.

### Fargate Windows was approved but persistent write targets exist

Source_Analysis classified one or more write targets as persistent, and the parent path mapped them to external storage — but EFS, FSx, and EBS volumes are all unavailable on Fargate Windows. Surface the conflict explicitly (the findings vs. the platform constraint), and do not generate a configuration that silently drops the persistent storage. The user decides: switch the compute option to ECS on EC2 Windows (an approval change → the gate's target-path approval is re-obtained for the changed content), or accept an application-level alternative they name. Never resolve this silently.

### The assessment was skipped and session-state is unknown

No Blocker data exists to condition the load balancer. Ask whether the application keeps in-process session state; generate stickiness (or not) per the answer and record the answer as the grounds. An ambiguous answer confirms nothing — re-ask.

### The image URI is unresolved

Not an error — the [input variable rule](#unresolved-image-uri--input-variable-rule) applies: `variable "image_uri"`, the unresolved statement, and the remaining-work report (including the Requirement 16 remote-build path where it applies). Validation still runs; only plan/apply need the value.

### The terraform-skill files cannot be read

Report the load failure and ask whether to proceed in the degraded mode (the summary table in [terraform-skill Conventions Conformance](#terraform-skill-conventions-conformance), with the limitation stated) or wait. Never generate silently as if the conventions had been checked.

### terraform is not installed / init cannot fetch providers

`validate.result: unavailable` — report the reason, make no applicability claim, and present the two validation commands and the output directory so the user can validate in an environment that has Terraform. The generated files remain valid deliverables; only the applicability confirmation is missing.

### terraform validate fails on the generated code

Report the validator's error output. Fix the configuration and re-validate (each attempt logged), or hand the errors to the user — but never report applicability on anything less than an error-free run, and never downgrade the check to "it looks correct".

### The user refuses the file-generation action class

Follow the refusal handling in [SKILL.md](../): write no files, present the full Terraform content as code blocks in the conversation so the user can create the files manually, and note that validation and the downstream apply ([deploy-verify-handoff.md](deploy-verify-handoff)) block until the files exist.

### The output destination changes after confirmation

Re-obtain the file-generation confirmation with the changed paths before writing anything at the new destination (Requirement 14). The old confirmation does not carry over.

### The user asks `ecs-build` to generate the Windows environment

Do not route it there: state that `ecs-build`'s generation scope is limited to Linux containers, generate here per this module, and note the [SKILL.md](../) future-support replacement — if `ecs-build` gains Windows container generation, this generation becomes a delegation.

### Sizing inputs are missing

CPU/memory values absent from the task-definition input values are not invented: expose them as described input variables with the absence reported, or obtain the values from the user. Concrete sizing design remains `ecs-architect`'s scope — this module only wires values that exist.

---

## Sources

- Amazon ECS task definition `runtime_platform` (operating system family and CPU architecture): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html
- Windows containers on AWS Fargate considerations (supported OS families, unsupported features, no Fargate Spot): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/windows-considerations.html
- Amazon ECS-optimized Windows AMIs (EC2 Windows container instances): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-optimized_windows_AMI.html
- Amazon ECS-optimized Windows AMI versions (2025/2022/2019 lineup and SSM parameter names): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-windows-ami-versions.html
- Task definition differences for Windows on EC2 (unsupported/differing parameters): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/windows_task_definitions.html
- Bootstrapping Windows container instances (`Initialize-ECSAgent` user data): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/bootstrap_windows_container_instance.html
- Amazon ECS capacity providers (Auto Scaling group capacity providers): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html
- ALB sticky sessions (target group stickiness, session-loss semantics): https://docs.aws.amazon.com/elasticloadbalancing/latest/application/sticky-sessions.html
- Windows container version compatibility (host/image version matching under process isolation): https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/version-compatibility
- Terraform CLI — `terraform validate` (what validation checks; init requirement): https://developer.hashicorp.com/terraform/cli/commands/validate
- Terraform CLI — `terraform init` `-backend=false` (plugin installation without backend configuration): https://developer.hashicorp.com/terraform/cli/commands/init
