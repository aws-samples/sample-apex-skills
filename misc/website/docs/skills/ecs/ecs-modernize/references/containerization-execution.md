---
title: "Module: Containerization Execution"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/containerization-execution.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/references/containerization-execution.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/containerization-execution.md). Edit the source, not this page.
:::

# Module: Containerization Execution

> **Part of:** [ecs-modernize](../)
> **Purpose:** Turn the approved migration plan into working container images: generate the Containerization_Artifact as real files in a user-approved location, keep the generated content aligned with the assessed containerization policy (or obtain the three-item policy confirmation when the assessment was skipped), determine whether the target image can be built locally, build and push to Amazon ECR behind the per-action-class confirmations — and, when a local build is impossible, route honestly to the CodeBuild Windows remote-build path or to a manual build hand-off instead of claiming success
> **Prerequisites:** **Execution_Gate passage** (Requirement 14); **code transformation completion** when code transformation is part of the approved plan (containerize the transformed code, not the pre-transformation baseline); **the assessed containerization policy** from the Replatform / Rearchitect path outputs — or, when the assessment was skipped, the [three-item policy confirmation](#no-assessed-policy--the-three-item-confirmation) obtained BEFORE any artifact is generated

This module owns containerization during Migration_Execution: producing the Containerization_Artifact (Dockerfile, `.dockerignore`, entrypoint script where needed, and the task-definition input values) as **real files** — the first point in the whole skill where artifacts stop being report code blocks and become files — then building the image and pushing it to Amazon ECR where the environment permits. Its outputs (the pushed image URI and the task-definition input values) feed [windows-environment-build.md](windows-environment-build) and the handoff in [deploy-verify-handoff.md](deploy-verify-handoff).

Most of this module is orchestrator-neutral: Dockerfile generation, image builds, and ECR pushes do not depend on where the container will run. Only the **task-definition input values** portion is ECS-specific.

## Table of Contents

- [Inputs](#inputs)
- [Containerization Flow](#containerization-flow)
- [Containerization Policy Alignment](#containerization-policy-alignment)
  - [Assessed policy exists — consistency and deviation reporting](#assessed-policy-exists--consistency-and-deviation-reporting)
  - [No assessed policy — the three-item confirmation](#no-assessed-policy--the-three-item-confirmation)
- [Containerization_Artifact Generation](#containerization_artifact-generation)
  - [Artifact set](#artifact-set)
  - [Output destination rules](#output-destination-rules)
  - [Generation report](#generation-report)
- [Local Build Feasibility](#local-build-feasibility)
- [Build and Push Flow](#build-and-push-flow)
- [Fallback Paths](#fallback-paths)
  - [Windows image on a non-Windows host — remote build](#windows-image-on-a-non-windows-host--remote-build)
  - [Other local-build infeasibility — manual build hand-off](#other-local-build-infeasibility--manual-build-hand-off)
- [Failure Reporting](#failure-reporting)
- [Determination Criteria](#determination-criteria)
- [Execution_Log](#execution_log)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **Execution_Gate passage** (required) — the gate's two conditions hold AND containerization is part of the approved migration plan. This module never runs before the gate.
- **The containerization policy** (required before generation) — one of:
  - the **assessed policy** from the Replatform path ([replatform-path.md](replatform-path) — base image selection, app-server bundling judgment, configuration intake method; for .NET Framework, the Windows base-image matrix) or the Rearchitect path ([rearchitect-path.md](rearchitect-path)) presented during the Assessment_Phase, or
  - when the assessment was skipped (Requirement 14's equivalent-inputs route), the **user-confirmed three-item policy** obtained by this module BEFORE generation (see [below](#no-assessed-policy--the-three-item-confirmation)).
- **The source code to containerize** — the transformed code (the code-transformation working branch or AWS Transform target branch) when code transformation was in the approved plan and has completed; otherwise the original source. Never containerize a pre-transformation baseline when the plan says the code is being transformed first.
- **Source_Analysis findings** (when the assessment ran) — `tech_stack` (runtime versions for base-image tags), the Replatform path's persistent-vs-temporary write mapping (volume inputs for the task definition), and session/health findings that shape the task-definition input values.
- **Host environment facts** (established by inspection or by asking the user): the presence of a **container build tool** (docker / finch / podman), the **host OS** and **CPU architecture**, and whether cross-architecture emulation (buildx/QEMU) is available. These drive the [local build feasibility](#local-build-feasibility) determination.
- **Action-class confirmation state** — two of Requirement 14's action classes belong to this module: **file generation** (the Containerization_Artifact files, and the CodeBuild build definition on the remote path — confirmation presents the output paths) and **image push** (confirmation presents the destination ECR repository name and whether it must be newly created). The image **build** is additionally gated by its own user confirmation (Requirement 16.4). Content changes after a confirmation (a different output path, a different repository) require re-confirmation per Requirement 14.

---

## Containerization Flow

Run the steps in this order. Every attempted action is recorded per the [Execution_Log](#execution_log) rules before the next action starts.

```
0. Verify the gate and prerequisites   -> Execution_Gate passed; code transformation
                                          (if planned) completed
1. Establish the policy                -> assessed policy loaded, or the three-item
                                          confirmation obtained (assessment skipped)
2. File-generation confirmation        -> action class of Req 14, presenting the
                                          output paths (user-approved destination)
3. Generate the Containerization_Artifact
                                       -> real files; report the list and each role
4. Determine local build feasibility   -> build tool presence x target OS/arch vs host
5a. Locally buildable  -> build + push  -> build confirmation -> build -> push
                                          confirmation (image push class) -> push
5b. Windows image, non-Windows host    -> remote-build fallback (CodeBuild definition;
                                          never start the remote build unconfirmed)
5c. Otherwise not buildable            -> manual build hand-off (artifacts still
                                          generated; command procedure presented)
6. Report outcomes                     -> image URI on success; honest failure
                                          reporting otherwise
```

**Why this order:** the policy (step 1) precedes generation because Requirement 16.9 forbids generating without a policy — assessed or confirmed. The file-generation confirmation (step 2) precedes generation because files may only be written into a user-approved destination. Feasibility (step 4) comes after generation because the artifacts are generated **regardless** of whether a local build is possible (Requirements 16.7 / 16.10 both keep generation going); feasibility only decides which of the three build routes (5a/5b/5c) follows.

---

## Containerization Policy Alignment

### Assessed policy exists — consistency and deviation reporting

When the Assessment_Phase presented a containerization policy, the generated content **must align with it** on all three items:

| Policy item | What alignment means in the generated files |
|---|---|
| **Base image selection** | The Dockerfile's `FROM` uses the image family and version-parity rule the policy stated (e.g. matching-major `eclipse-temurin` JRE; matching `tomcat` image; `icr.io/appcafe/websphere-traditional` at the matching tWAS version line with app + properties-file configuration baked in at build time; `icr.io/appcafe/websphere-liberty` / `open-liberty` for Liberty apps; `mcr.microsoft.com/dotnet/aspnet` at the matching version; the Windows base-image matrix selection for .NET Framework) |
| **App-server bundling judgment** | Bundle → the server is the container's main process via the server-included base image; no bundling → the artifact's embedded server is the entrypoint. The generated Dockerfile does not contradict the judgment |
| **Configuration intake method** | Each config artifact lands via the method the policy mapped it to: bake-in → `COPY` into the image; environment variables → task-definition `environment` entries; EFS → a mount point in the task-definition input values (no bake-in); SSM/Secrets Manager → task-definition `secrets` entries or entrypoint materialization. When `secrets` are used, the **task execution role must be extended** with `ssm:GetParameters` / `secretsmanager:GetSecretValue` (+ `kms:Decrypt` for a CMK) — the base `AmazonECSTaskExecutionRolePolicy` does not grant read access to your parameters/secrets |

**Deviation rule (Requirement 16.3):** deviating from the assessed policy is permitted only with the reason reported — name the policy item deviated from, the assessed value, the generated value, and why (e.g. "the assessed base image tag has been deprecated upstream since the assessment; the current supported tag of the same family is used instead"). A silent deviation is a violation. Record deviations in `policy_deviations` (see [Output Schema](#output-schema)).

### No assessed policy — the three-item confirmation

When the assessment was skipped (Migration_Execution started on user-supplied equivalent inputs per Requirement 14), there is no assessed policy to align with. In that case, **BEFORE generating any artifact** (Requirement 16.9):

1. **Present all three policy items** with a concrete proposal for each, derived from what is known about the stack (user statements, visible build files):
   - **Base image selection** — the proposed image and tag, with the version-parity grounds;
   - **App-server bundling judgment** — bundle or not, with the grounds (does the deployable artifact embed its server?);
   - **Configuration intake method** — per known config artifact, the proposed intake method (bake-in / environment variables / EFS / SSM-Secrets Manager).
2. **Obtain the user's confirmation** of the three items. An ambiguous response confirms nothing — re-present and ask for an unambiguous answer (the Requirement 14 discipline).
3. **Generate based on the confirmed policy.** The confirmed items then play the role of the assessed policy for the deviation rule above.

Do not generate first and confirm later, and do not substitute a guessed policy for the confirmation.

---

## Containerization_Artifact Generation

### Artifact set

The Containerization_Artifact comprises the following, generated as **real files** (Requirement 16.1):

| Artifact | Content | Always generated? |
|---|---|---|
| **Dockerfile** | `FROM` per the policy's base image; the existing deployable artifact copied in; the entrypoint set to the existing start command (Replatform) or the modernized start command (Rearchitect); `EXPOSE` for the app's ports | Yes |
| **`.dockerignore`** | Excludes VCS metadata, build intermediates, local tooling dirs, and anything the image must not contain (never let detected credential files into the build context) | Yes |
| **Entrypoint script** | Startup glue that plain Dockerfile directives cannot express — e.g. materializing config files from SSM/Secrets Manager values at startup, pre-start environment wiring, graceful-shutdown signal forwarding | **Conditional** — when NOT generated, report the grounds for judging it unnecessary (e.g. "the artifact embeds its server and starts with a single command; config intake is environment variables only — no startup glue is required") |
| **Task-definition input values** | The ECS-specific portion: container name, image reference (or placeholder pending push), port mappings, CPU/memory sizing inputs, `environment` / `secrets` entries per the config intake method, mount points for EFS-classified write targets, health check, and log configuration | Yes |

Silently omitting the entrypoint script is a violation: the choice is generate it, or report why it is not needed.

### Output destination rules

(Requirement 16.2)

- The generation destination is the **user-approved output destination** — the paths presented at the **file generation** action-class confirmation.
- The destination is **outside the target source code directory**, UNLESS the user has **explicitly approved an in-repository write** — a new branch or a new directory (an AWS Transform target branch or the code-transformation working branch are eligible, subject to that same explicit approval). Absent that explicit approval, never write into the source tree.
- These rules govern **every file this module writes**, including the CodeBuild build definition of the [remote-build fallback](#windows-image-on-a-non-windows-host--remote-build).
- A destination change after confirmation triggers re-confirmation (Requirement 14) before generating at the new destination.

### Generation report

After generation, report the **complete list of generated files, each with its role** (Requirement 16.1) — e.g.:

| File | Role |
|---|---|
| `<dest>/Dockerfile` | Builds the application image on `<base image>` per the confirmed policy |
| `<dest>/.dockerignore` | Keeps VCS metadata and build intermediates out of the build context |
| `<dest>/docker-entrypoint.sh` | Materializes `app.config` values from SSM at startup, then launches the server |
| `<dest>/task-definition-inputs.md` (or `.json`) | The task-definition input values consumed by the environment build / `ecs-build` handoff |

When the entrypoint script is absent from the list, the report states the grounds for its omission in the same breath.

---

## Local Build Feasibility

A local build is **feasible** if and only if BOTH hold:

| # | Condition | How it is determined |
|---|---|---|
| 1 | **A container build tool is available** on the local host | docker / finch / podman (or equivalent) is installed AND operational — a CLI whose daemon/VM is unreachable does not count. Verify by inspection (e.g. the tool's version/info command) or by asking the user |
| 2 | **The target image's OS and architecture can be built on this host** | **OS:** Windows container images can be built ONLY on a Windows host — a Linux/macOS host can never build them, in any configuration. Linux images build on Linux hosts and on macOS/Windows via the build tool's Linux VM. **Architecture:** a target architecture differing from the host's (e.g. arm64 target on an x86_64 host) is buildable only when cross-architecture emulation (buildx + QEMU or equivalent) is available; otherwise it fails condition 2 |

Routing on the outcome:

| Outcome | Route |
|---|---|
| Both conditions hold | [Build and Push Flow](#build-and-push-flow) |
| Condition 2 fails because the target is a **Windows image and the host is not Windows** | [Remote-build fallback](#windows-image-on-a-non-windows-host--remote-build) (Requirement 16.7) — this route takes precedence whenever the Windows × non-Windows condition holds, even if condition 1 also fails |
| Any other failure (no build tool; non-Windows OS/arch mismatch without emulation) | [Manual build hand-off](#other-local-build-infeasibility--manual-build-hand-off) (Requirement 16.10) |

Whichever route applies, **report the determination and its grounds** — which condition failed and the facts behind it. Never skip artifact generation because a build is infeasible: generation has already happened (or continues) on every route.

---

## Build and Push Flow

When the local build is feasible, run: **build confirmation → build → push confirmation → (repository creation if needed) → push**.

### Build (Requirement 16.4)

- **Obtain the user's confirmation before building** — present the image name and tag to be built and the build context directory.
- Run the build with the available tool (e.g. `docker build -t <name>:<tag> <context>`).
- **Report the build result**: success or failure, and the **image tag** on success. On failure, follow [Failure Reporting](#failure-reporting).

### ECR repository — existence check and creation (Requirement 16.5)

- Check whether the destination ECR repository exists (`aws ecr describe-repositories --repository-names <repo>`).
- **If it does not exist:** create it only behind the user's confirmation — the **image push** action-class confirmation already presents the repository name and whether it must be newly created; the creation itself proceeds only when the user has confirmed with the new-creation fact visible. Record the created repository in the Execution_Log (`ecr_repository_create`).
- Never create a repository the user has not confirmed, and never push to a repository other than the confirmed one.

### Push (Requirement 16.6)

- Push only after BOTH: the build succeeded, AND the user confirmed the push destination — **the ECR repository and the image tag** (the image push action-class confirmation).
- Authenticate to ECR, tag the image with the full registry path, and push.
- **Report the pushed image URI as the complete URI including repository and tag** — e.g. `123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/myapp:v1` — never an abbreviation. This URI is the primary handoff value for [windows-environment-build.md](windows-environment-build) and the `ecs-build` handoff in [deploy-verify-handoff.md](deploy-verify-handoff).
- A destination change after confirmation (different repository or tag) requires re-confirmation before pushing.

---

## Fallback Paths

### Windows image on a non-Windows host — remote build

(Requirement 16.7 — applies when the target is a **Windows container image** and the local host OS is **not Windows**.)

1. **Report that a local build is impossible, with the reason**: Windows container images can be built only on a Windows host — there is no emulation or VM workaround on Linux/macOS build tools.
2. **Present the remote-build path as the alternative**: an AWS CodeBuild project using a **Windows Server build environment** (environment type `WINDOWS_SERVER_2019_CONTAINER` or `WINDOWS_SERVER_2022_CONTAINER` — verify current availability and supported Regions against the live CodeBuild documentation before presenting), building the image from the generated Dockerfile and pushing to the confirmed ECR repository.
3. **Generate the build definition files** needed for the remote build — a `buildspec.yml` (build + ECR login + push phases) and, where useful, the CodeBuild project definition — following the [output destination rules](#output-destination-rules) (these are files: the file-generation action class and the user-approved destination apply). **Disclose the service-role prerequisite:** a CodeBuild project requires a CodeBuild *service role*, and the skill's [IAM policy](../#iam-permissions) intentionally cannot pass a role to `codebuild.amazonaws.com` — so `codebuild:CreateProject` cannot mint one under that policy. Tell the user that an operator must create the CodeBuild service role out of band and supply its ARN as an input; `codebuild:StartBuild` / `BatchGetBuilds` then run against the resulting pre-existing project. Do not assume an agent-driven `CreateProject` with a fresh role will succeed.
4. **Never start the remote build without the user's explicit confirmation.** Generating the definition is not approval to run it. Starting a CodeBuild build creates AWS activity and cost; it happens only on an explicit, unambiguous go-ahead — and is then recorded in the Execution_Log.
5. Until the remote build has run and pushed, the image URI is **unresolved** — downstream consumers handle it per their rules (e.g. [windows-environment-build.md](windows-environment-build) defines it as a Terraform input variable).

### Other local-build infeasibility — manual build hand-off

(Requirement 16.10 — applies when the local build is infeasible and the Windows × non-Windows condition does NOT hold: no operational container build tool, or a non-Windows OS/architecture mismatch without emulation.)

1. **Report that the build is impossible and the grounds of the determination** — which feasibility condition failed and the observed facts (e.g. "no container build tool found on this host", "target is arm64, host is x86_64, and buildx emulation is unavailable").
2. **Continue Containerization_Artifact generation** — the artifacts are generated in full per [Containerization_Artifact Generation](#containerization_artifact-generation); infeasibility of the build never truncates generation.
3. **Present the command procedure for the user to build and push in another environment**, concrete enough to run as-is after placeholder substitution — for example:

   ```bash
   # On a host that satisfies the feasibility conditions:
   # 1. Build (from the directory containing the generated Dockerfile)
   docker build -t <app-name>:<tag> <build-context-path>

   # 2. Authenticate to ECR
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

   # 3. Tag with the full registry path
   docker tag <app-name>:<tag> <account-id>.dkr.ecr.<region>.amazonaws.com/<repo>:<tag>

   # 4. Push
   docker push <account-id>.dkr.ecr.<region>.amazonaws.com/<repo>:<tag>
   ```

   Include the ECR repository creation command (`aws ecr create-repository --repository-name <repo> --region <region>`) when the repository does not exist yet, noting that creating it remains subject to the user's own decision in the manual flow.
4. Ask the user to report back the pushed **image URI** — the downstream modules block on it exactly as under the refusal-handling rules of [SKILL.md](../).

---

## Failure Reporting

(Requirement 16.8 — applies whenever an image build or push fails, on any route.)

- **Report the failed step and the error content** — which stage failed (build / ECR authentication / repository creation / tag / push / remote build) and the actual error output, not a paraphrase that hides it.
- **Never claim the failed step succeeded**, in whole or in part. A partially completed flow is reported as exactly that: what succeeded (e.g. "the build succeeded; the push failed") and what did not.
- **Present the command procedure for manual execution** of the failed step onward — the same concrete form as the [manual build hand-off](#other-local-build-infeasibility--manual-build-hand-off), scoped to what remains.
- **Log the failure** in the Execution_Log (action, `result: failure`, targets, timestamp, confirmation state) before any next action.

---

## Determination Criteria

| Decision | Criterion |
|---|---|
| Generation may start | Execution_Gate passed AND (assessed policy exists OR the three-item policy confirmation is complete) AND the file-generation action-class confirmation is complete for the current output paths — all three; a missing policy blocks generation (Req 16.9) |
| Output destination is valid | It is the user-approved destination AND (it is outside the target source directory OR the user explicitly approved an in-repository write to a new branch/directory) |
| Entrypoint script is omitted | Only with the grounds for judging it unnecessary reported alongside the generation report |
| Generated content deviates from the policy | Only with the deviated item, assessed value, generated value, and reason reported |
| Local build is feasible | An operational container build tool exists AND the target image's OS/architecture is buildable on this host (Windows targets require a Windows host; cross-architecture requires emulation) |
| Remote-build fallback applies | Target is a Windows container image AND the host OS is not Windows — takes precedence over the manual hand-off whenever it holds |
| Manual hand-off applies | The local build is infeasible AND the remote-build condition does not hold |
| Build may run | The local build is feasible AND the user confirmed the build (image name, tag, context) |
| ECR repository may be created | The repository does not exist AND the user confirmed its creation (the image-push confirmation presented the new-creation fact) |
| Push may run | The build succeeded AND the user confirmed the push destination (repository + tag) — both; a changed destination re-opens the confirmation |
| Remote build may start | The user gave an explicit, unambiguous confirmation to start it — definition generation alone never suffices |
| A step may be reported as succeeded | Its success was observed (tool exit status / API response) — never inferred or assumed |

---

## Execution_Log

Every action this module attempts — Containerization_Artifact file generation, build definition generation, image builds, ECR repository creation, image pushes, remote build starts — is recorded in the **Execution_Log**, success or failure alike, before the next action starts. The recording rules, required fields, storage forms, and save-failure fallback are canonical in [deploy-verify-handoff.md — Execution_Log Rules](deploy-verify-handoff#execution_log-rules); this module records against them rather than restating them. Typical action types from this module: `file_generation`, `image_build`, `ecr_repository_create`, `image_push`, `remote_build_start`.

---

## Output Schema

This module produces the `containerization_execution` block. Hold the structure in conversation context; the durable record is the Execution_Log.

```yaml
containerization_execution:
  policy:
    source: assessed | confirmed_at_execution   # assessed path outputs, or the Req 16.9 confirmation
    items:                                      # the three items in force during generation
      base_image: string
      app_server_bundling: string
      config_intake: string
  artifacts:                                    # every generated file, with its role (Req 16.1)
    - {path: string, role: string}
  entrypoint_script:
    generated: bool
    omission_grounds: string | null             # required when generated: false
  output_destination:
    path: string
    in_repo_write_approved: bool                # explicit user approval for an in-repo destination
  policy_deviations: [string]                   # each: item, assessed value, generated value, reason (Req 16.3)
  build:
    locally_buildable: bool
    reason: string                              # the feasibility grounds (both conditions, with facts)
    result: success | failed | skipped          # skipped = infeasible or user declined
    image_tag: string | null
  push:
    repository: string
    created_repo: bool                          # ECR repository newly created (Req 16.5)
    image_uri: string | null                    # the COMPLETE URI on success (Req 16.6)
  remote_build:
    required: bool                              # Windows image x non-Windows host (Req 16.7)
    build_definition_path: string | null        # generated per the output destination rules
    started: bool                               # true only after the explicit start confirmation
  manual_procedure_presented: bool              # Req 16.8 / 16.10 command hand-off went out
```

**Reporting invariants:**

- No `artifacts` entry exists before the policy (`assessed` or `confirmed_at_execution`) was in force — generation never precedes the policy.
- `entrypoint_script.generated: false` always carries non-null `omission_grounds`.
- `push.image_uri` is non-null only after a successful push to a confirmed destination — and is always the complete registry/repository:tag URI.
- `push.created_repo: true` implies a corresponding user confirmation and an `ecr_repository_create` Execution_Log entry.
- `remote_build.started: true` never appears without an explicit user confirmation recorded for the start.
- `build.result: failed` (or a failed push) coexists with `manual_procedure_presented: true` — a failure without the manual hand-off is incomplete reporting.
- `build.locally_buildable: false` never empties `artifacts` — generation continues on every route.

---

## Edge Cases

### The assessment was skipped and the user's policy response is ambiguous

The three-item confirmation is not obtained: generate nothing, re-present the three items, and ask for an unambiguous answer. Generation stays blocked until the policy is confirmed (Requirement 16.9's precondition is hard).

### The user refuses the file-generation action class

Follow the refusal handling in [SKILL.md](../): write no files, present the artifact contents in the conversation (code blocks) so the user can create them manually, and continue only the confirmed classes that do not depend on the generated files. Classes that need the files (build, push) block until the user reports having created them.

### The build tool exists but turns out to be inoperative at build time

Feasibility judged the tool operational, but the build command fails on a daemon/VM error. This is a build failure: report it per [Failure Reporting](#failure-reporting) (the failed step is the build; the error content is the daemon error), then offer the [manual hand-off](#other-local-build-infeasibility--manual-build-hand-off) procedure. Do not silently re-classify the environment.

### The target is a Windows image, the host is non-Windows, AND no build tool exists

The Windows × non-Windows condition holds, so the [remote-build fallback](#windows-image-on-a-non-windows-host--remote-build) takes precedence: the missing build tool is irrelevant to a build that could never run locally anyway. Report both facts; route to CodeBuild.

### Cross-architecture target with emulation available

An arm64 target on an x86_64 host (or the reverse) with buildx/QEMU available is **locally buildable** — proceed with the build, noting the emulation in the build report (emulated builds are slower and, rarely, behave differently; the note keeps the report honest).

### The image built but the user declines the push

Per the refusal handling: do not push; present the manual push procedure (authentication, tag, push commands with the built tag); downstream modules that need the image URI block until the user supplies it.

### The push destination changes after confirmation

A different repository or tag than what the image-push confirmation presented: re-obtain the confirmation with the changed content before pushing (Requirement 14). The old confirmation does not carry over.

### The ECR repository already exists

No creation is needed: the existence check passes, `created_repo` stays false, and the push proceeds under the existing repository (still behind the push confirmation naming it).

### The remote build definition is generated but the user never starts the build

That is a valid resting state: the definition files exist at the approved destination, `remote_build.started` stays false, and the image URI stays unresolved. Downstream modules treat the URI per their unresolved-value rules ([windows-environment-build.md](windows-environment-build) input-variable rule; [deploy-verify-handoff.md](deploy-verify-handoff) unresolved-item handling). Never start the build to "unblock" things without the explicit confirmation.

### Code transformation is in the approved plan but has not completed

The prerequisite fails: do not generate against the untransformed source. Report that containerization waits on the transformation's completion (or on the user's decision to re-scope the plan), per the module routing prerequisites in [SKILL.md](../).

---

## Sources

- Amazon ECR — pushing a Docker image (authentication, tag, push command sequence): https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html
- Amazon ECR — creating a private repository: https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-create.html
- AWS CodeBuild — build environment compute types (Windows Server 2019 / 2022 container environment types and Region availability — verify against the live page before presenting the remote-build path): https://docs.aws.amazon.com/codebuild/latest/userguide/build-env-ref-compute-types.html
- AWS CodeBuild — Docker sample (buildspec for building and pushing images to ECR): https://docs.aws.amazon.com/codebuild/latest/userguide/sample-docker.html
- Docker — multi-platform builds (buildx / QEMU emulation for cross-architecture builds): https://docs.docker.com/build/building/multi-platform/
- Windows container version compatibility (Windows images require Windows hosts; host/image version coupling): https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/version-compatibility
