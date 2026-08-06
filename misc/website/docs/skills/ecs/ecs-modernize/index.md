---
title: "ecs-modernize"
description: "Assess an existing app (VMware/EC2) by source code analysis for the replatform vs rearchitect decision, and execute the approved migration onto Amazon ECS. Scope: assessment, strategy decision, migration execution. Covers: source code analysis; language/framework detection (Java, .NET, Spring, Struts, WebSphere tWAS/Liberty); cloud/container fit scoring; strategy recommendation; Windows container support; tWAS containerization and Liberty migration; migration plan generation; AWS Transform orchestration; containerization and ECR push; Windows-container-path environment build; deploy and steady-state verification. Triggers: \"migrate this app from EC2 to ECS\", \"can we containerize this VMware-hosted app?\", \"replatform or rearchitect for ECS?\", \"modernize this WebSphere app\". Skip for greenfield deployment-model design (ecs-architect), Linux container path ECS Terraform generation (ecs-build), live ECS inventory (ecs-recon), security/compliance hardening (ecs-security), Kubernetes/EKS migration (eks-design)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/SKILL.md). Edit the source, not this page.
:::


# ECS Modernize

Assess an existing application (VMware / EC2) through read-only source code analysis, decide between replatform and rearchitect, and execute the approved migration onto Amazon ECS.

## Overview

This skill runs a **two-phase pipeline** with an explicit control point between the phases:

1. **Assessment_Phase (strictly read-only)** — static Source_Analysis of the target source code (tech-stack detection, then Blocker detection), cloud/container fit scoring (a 0–100 Fit_Score over six weighted Scoring_Dimensions), and a migration-strategy recommendation: **Replatform** (containerize as-is onto ECS on EC2 with a static configuration) vs **Rearchitect** (modernize the app for ECS Express Mode / Fargate / Managed Instances). Both strategies are always presented with trade-offs regardless of the score. **Deliverable:** exactly one Markdown **Modernization_Report**.
2. **Execution_Gate** — Migration_Execution never starts until (a) the assessment is complete or the user supplies equivalent decision inputs, AND (b) the user explicitly approves the Migration_Strategy and target path. See [Execution_Gate and Execution Workflow](#execution_gate-and-execution-workflow).
3. **Migration_Execution (approved plan only)** — code transformation as a single Transformation_Plan (with optional per-work-item AWS Transform augmentation), containerization execution (real Containerization_Artifact files, image build, ECR push), target environment construction (Linux container paths hand off Terraform generation to `ecs-build`; the Windows_Container_Path generates Windows_Environment_Terraform within this skill), and deploy + steady-state verification. **Deliverable:** an **Execution_Log** recording every action, appended to or referenced from the Modernization_Report.

## When to Use

- Migrating an **existing application** from EC2 or VMware onto Amazon ECS ("migrate this app from EC2 to ECS").
- Assessing whether an existing app can be containerized ("can we containerize this VMware-hosted app?").
- Comparing migration strategies ("replatform or rearchitect for ECS?"), including the Windows container path for .NET Framework apps.
- Modernizing **WebSphere Application Server workloads** ("modernize this WebSphere app to containers"): traditional WAS (tWAS) apps containerized as-is on IBM's `websphere-traditional` image (Replatform), or migrated to WebSphere Liberty / Open Liberty as a Rearchitect modernization item — with IBM's assessment tooling (Transformation Advisor, binary scanner) surfaced as accelerators.
- Executing an approved migration: code transformation (.NET Framework → .NET, runtime upgrades, tWAS → Liberty migration), Dockerfile generation, image build + ECR push, Windows container environment build, deploy and steady-state verification — all gated behind the Execution_Gate.
- Mixed requests that combine in-scope work with out-of-scope topics — run the in-scope portion and include delegation guidance in the same response (see [Delegation Boundaries](#delegation-boundaries)).

## Don't Use

- **Greenfield deployment-model selection and detailed target design** (capacity-provider strategy, task sizing, network design) — use `ecs-architect`. This skill starts from an existing app; `ecs-architect` owns the Day-0 design depth.
- **Linux container path ECS environment Terraform generation** (Express Mode / Fargate / Managed Instances / ECS on EC2 Linux) — use `ecs-build`. This skill hands off with a structured input list.
- **Inventorying a live ECS estate** (clusters, services, task definitions already running) — use `ecs-recon`.
- **Security / compliance hardening** (IAM permission design, detailed secrets-management design, compliance audits) — use `ecs-security`.
- **Kubernetes / EKS migration** — use `eks-design`. If the request mentions only Kubernetes/EKS and not ECS, do not run any analysis here.

## Execution Model and Non-Destructive Guardrails

Safety guarantees are phase-specific: the Assessment_Phase is strictly read-only, while Migration_Execution writes — but only inside explicit safety rails. One invariant spans every phase: credential values are never disclosed.

### Assessment_Phase — read-only invariants

While in the Assessment_Phase, ALL of the following invariants hold without exception:

- **Target source is immutable.** Treat the target source code — including build definitions and deploy configuration — as strictly read-only. Never create, modify, delete, move, or rename any file or directory under the target source directory.
- **No build, test, or packaging commands.** Analysis is static reading of file contents only. Never run compilation, dependency resolution or fetching, test execution, or package generation against the target source — regardless of where the output would land.
- **AWS APIs: `Describe*` / `List*` / `Get*` only.** When the analysis queries the AWS environment, restrict AWS API calls to read-only operations whose names start with `Describe`, `List`, or `Get`. Never call APIs that create, modify, or delete AWS resources.
- **No "effectively read-only" exceptions.** If an operation useful to the analysis is not named with a `Describe`/`List`/`Get` prefix, do NOT invoke it — even when it is effectively read-only. Report that the information was not obtained and why (the operation name does not satisfy the read-only naming rule).
- **Exactly one file write.** The only permissible file-system write is the single Modernization_Report file. Do not create any other file — no temp files, no intermediate files, no scratch output.
- **The report lands outside the source tree.** Write the Modernization_Report outside the target source code directory (see [Report Output](#report-output)).
- **Artifact examples are code blocks, not files.** When recommendations include containerization artifacts (Dockerfile, task definition, and similar), embed them as code blocks inside the Modernization_Report only. Never create them as individual files on the file system during the assessment.
- **No IaC during assessment.** Artifact examples never include Terraform, CloudFormation, or CDK code. Linux container path IaC is delegated to `ecs-build` (see [Delegation Boundaries](#delegation-boundaries)); Windows_Container_Path IaC is generated only during Migration_Execution.

### Migration_Execution — safety rails

Migration_Execution creates and changes things, but only inside these rails:

- **The original source stays untouched.** Never directly modify the original source branch, nor any file that existed under the target source directory at the start of Migration_Execution. Code changes are limited to: AWS Transform output to its target branch; file generation and code-copy modification in a **user-approved new location** (a new branch or new directory — including an AWS Transform target branch or a branch derived from it, subject to user approval); and modification of files this skill itself generated into approved locations during Migration_Execution.
- **Never delete existing AWS resources.** Do not call APIs that delete existing AWS resources.
- **`terraform plan` destroy check before every apply.** Before running `terraform apply`, inspect the execution plan (`terraform plan` output) and confirm it contains no delete/destroy actions against existing AWS resources. If the plan contains one or more such actions, do NOT apply — report the full list of existing resources planned for deletion to the user instead.
- **Only planned resources.** Limit AWS resource creation and modification to the resources enumerated — with resource type and name (or naming convention) — in the migration plan approved at the Execution_Gate. If creating or modifying a resource outside the approved plan becomes necessary, present the target resource and the reason it is needed, and obtain the user's confirmation BEFORE executing. Never perform the unplanned operation without that confirmation.
- **Confirmed action classes only.** File generation/modification and AWS resource creation/modification are permitted only as operations belonging to an action class whose per-class user confirmation has been completed (see [Execution_Gate and Execution Workflow](#execution_gate-and-execution-workflow)).
- **Git history is sacrosanct.** Never delete existing branches, force-push to existing branches, or rewrite commit history in the target source code repository.

### All phases — credential non-disclosure

Regardless of phase, never include the value of any detected credential — in whole or in part — in the Modernization_Report, the Execution_Log, any generated file, or any conversational output. Refer to detected credentials only by file path, category, and a value-free description (naming the credential type is allowed).

## Analysis Workflow (Assessment_Phase)

### Step 0: Precondition check

Before any analysis, verify the target source code path exists and is readable.

- **If the path does not exist or cannot be read**: abort Source_Analysis, report an error naming the inaccessible path, and do not run scoring or recommendation.
- **If the path is accessible but some files cannot be read**: continue the analysis, record the excluded paths and reasons, and mark the result as partial.

### Module execution order

For a **full modernization assessment**, execute the assessment modules in prerequisite order:

1. **Tech-stack detection** — languages, frameworks, runtimes, app servers ([references/tech-stack-detection.md](references/tech-stack-detection))
2. **Blocker detection** — modernization blockers in six categories, each classified as replatform-tolerable or must-fix ([references/blocker-detection.md](references/blocker-detection))
3. **Scoring and recommendation** — Fit_Score and threshold-based strategy recommendation ([references/scoring-and-recommendation.md](references/scoring-and-recommendation))
4. **Path details** — Replatform path incl. the Windows_Container_Path decision ([references/replatform-path.md](references/replatform-path)) and Rearchitect path ([references/rearchitect-path.md](references/rearchitect-path))
5. **Report generation** — the Modernization_Report ([references/report-generation.md](references/report-generation))

For a **single-module request** (e.g. "just identify the language and framework"), load and run only that module and its transitive prerequisites, per the routing table below. Execution modules never run as part of an assessment — they require the Execution_Gate.

> **IMPORTANT: Load Reference Files**
>
> Before executing **any** module — assessment, recommendation, or execution — you MUST read that module's reference file(s). The references contain the detection criteria, decision rules, output schemas, and edge-case handling; this SKILL.md provides orchestration only. Working from general knowledge instead of the reference produces non-compliant results.
>
> **If a module's reference file cannot be read** (missing, unreadable, or unresolved path): abort that module, report the load failure to the user, and do not generate the module's result without the reference knowledge.

## Module Routing Table

Route each request to the module whose user intent it matches, load the listed reference file(s), and satisfy the prerequisites first. Modules with no prerequisite say **None** explicitly. The four Migration_Execution modules (7–10) all list **Execution_Gate passage** as a prerequisite — they never run without it.

| # | User intent (what routes here) | Module | Reference file(s) | Prerequisite modules |
|---|---|---|---|---|
| 1 | "Identify the language and framework" — detect languages, frameworks, runtimes, app servers | Tech-stack detection | [references/tech-stack-detection.md](references/tech-stack-detection) | None |
| 2 | "Find the problems blocking containerization" — detect modernization Blockers | Blocker detection | [references/blocker-detection.md](references/blocker-detection) | Tech-stack detection |
| 3 | "Score the containerization fit" / "recommend a migration strategy" | Scoring and recommendation | [references/scoring-and-recommendation.md](references/scoring-and-recommendation) | Tech-stack detection, Blocker detection |
| 4 | "Give me the steps to containerize as-is" — Replatform details, incl. the Windows_Container_Path decision | Replatform path | [references/replatform-path.md](references/replatform-path) | Scoring and recommendation |
| 5 | "Give me the modernization plan for a modern target" — Rearchitect details | Rearchitect path | [references/rearchitect-path.md](references/rearchitect-path) | Scoring and recommendation |
| 6 | "Put the assessment report together" (final stage of a full assessment) | Report generation | [references/report-generation.md](references/report-generation) | All assessment modules (1–5) |
| 7 | "Port this .NET Framework app" / "upgrade the runtime" / "migrate this app off tWAS to Liberty" — code transformation | Code transformation | [references/code-transformation.md](references/code-transformation) (+ [references/code-transformation-agent-led.md](references/code-transformation-agent-led) when agent-executed items exist) | **Execution_Gate passage** (when Source_Analysis results exist, use them to propose the job scope and transformation targets) |
| 8 | "Create the Dockerfile, build and push the image" | Containerization execution | [references/containerization-execution.md](references/containerization-execution) | **Execution_Gate passage**; code transformation completion when it is part of the approved plan; the assessed containerization policy — or, if the assessment was skipped, policy confirmation per the module's rules |
| 9 | "Build the Windows container environment" | Windows environment build | [references/windows-environment-build.md](references/windows-environment-build) | **Execution_Gate passage** + Containerization execution (the image URI for the task definition; if unresolved, define it as a Terraform input variable) |
| 10 | "Deploy it and verify it's running" | Deploy, verify and handoff | [references/deploy-verify-handoff.md](references/deploy-verify-handoff) | **Execution_Gate passage** + availability of the environment Terraform (`ecs-build` output or Windows_Environment_Terraform) |

### Full-assessment execution order

For a **full modernization assessment**, run the assessment modules (1–6) in the topological order of the prerequisite graph — each module starts only after all of its prerequisites have completed:

1. **Tech-stack detection**
2. **Blocker detection**
3. **Scoring and recommendation**
4. **Both path details** — Replatform path and Rearchitect path (both depend only on scoring; their relative order is free)
5. **Report generation** (last — it requires every assessment module above)

A full assessment never triggers the execution modules (7–10): they are not part of the assessment prerequisite graph, and their Execution_Gate prerequisite is unmet.

### Single-module requests: transitive prerequisite resolution

- **Requested module has no prerequisites** (module 1): load only that module's reference file and run only that module. Do not load any other module's reference file.
- **Requested module has prerequisites**: resolve them **transitively** — load the reference files for the requested module plus every module in the transitive closure of its prerequisites, and nothing else, then execute in topological order so each prerequisite completes before its dependent starts. Example: "score the containerization fit" alone loads modules 1, 2 and 3 (tech-stack detection is a transitive prerequisite via blocker detection) and runs them in the order 1 → 2 → 3.
- **Execution modules (7–10)**: Execution_Gate passage is a gate condition, not a module — it cannot be satisfied by loading a file. If the gate has not been passed, do not run the module; respond with the gate's entry conditions instead (see [Execution_Gate and Execution Workflow](#execution_gate-and-execution-workflow)). Once the gate is passed, resolve the remaining module prerequisites transitively as above.

## Execution_Gate and Execution Workflow

The Execution_Gate is the explicit control point between assessment and execution. Migration_Execution never starts before the gate is passed, and each action class requires its own confirmation even after the gate.

### Gate passage conditions

The gate is passed only when BOTH of the following hold:

1. **Decision inputs exist** — the full modernization assessment has completed, OR the user has supplied equivalent decision inputs: the Migration_Strategy to adopt AND the target compute model.
2. **Explicit approval** — the user has explicitly approved the Migration_Strategy and target path to adopt.

While the gate is NOT passed, do not execute any action belonging to Migration_Execution: starting an AWS Transform job, starting execution of any Transformation_Plan work item, generating Containerization_Artifact files, building or pushing images, or generating/applying Terraform.

**On passage**, present to the user: the approved Migration_Strategy, the target path, and the list of action classes planned for this execution — then begin Migration_Execution per the routing table (modules 7–10).

### Requests to execute before the gate

If the user asks for migration-artifact file generation or code rework before the gate has been passed, do NOT perform the work immediately. Present the gate's entry conditions — assessment completion (or user-supplied equivalent decision inputs) plus explicit approval of the strategy and target path — and ask the user how to proceed.

### Skipping the assessment

When the user requests Migration_Execution without an assessment:

- **Equivalent inputs provided** (the Migration_Strategy AND the target compute model): report that no assessment was performed and the risks that follow from skipping it (including Blockers going undetected), then confirm the user's explicit approval before starting Migration_Execution.
- **Equivalent inputs missing, in whole or in part**: do NOT start Migration_Execution. Name the missing decision inputs and present two options for the user to choose between: (1) run the modernization assessment, or (2) supply the missing decision inputs.

### Per-action-class confirmations

Before the FIRST execution of each action class below, obtain an individual user confirmation for that specific class, presenting the concrete content listed:

| Action class | Present at confirmation time |
|---|---|
| **Code transformation start** | The Transformation_Plan work-item list; the items receiving Transform augmentation and the AWS Transform job scope; the working branch / working directory for agent-executed items |
| **File generation** | The output paths for Containerization_Artifact files and Terraform |
| **Image push** | The destination ECR repository name and whether it must be newly created |
| **`terraform apply`** | The Terraform directory to be applied |

- **Re-confirmation on change:** if, after a class was confirmed, the content presented at confirmation time changes (a file-generation output path, the push destination repository, the apply target directory, or similar), re-obtain that class's confirmation — presenting the changed content — before executing the class's action under the changed content.
- **Only clear approval counts:** if the user's response to a strategy/target-path approval request or to an action-class confirmation cannot be clearly identified as approval or refusal — or the Migration_Strategy / target path being approved cannot be uniquely identified — do NOT treat the response as approval or confirmation, do not execute the action, and re-present the options asking for an unambiguous answer.

### Refusal handling

If the user refuses the confirmation for an action class:

1. **Do not execute** any action in the refused class.
2. **Enable manual execution** — provide the user with the information needed to perform the refused class themselves (the generated content or a step-by-step procedure).
3. **Continue independent classes** — among the classes that DID receive confirmation, continue executing those that do not depend on the refused class's outputs.
4. **Block dependent classes** — for confirmed classes whose execution depends on the refused class's outputs (for example, `terraform apply` needing a pushed image URI), state explicitly that the prerequisite output is missing and do not execute them until the user provides the result of their manual execution (such as the image URI).

## Scoring and Recommendation (Overview)

Full criteria live in [references/scoring-and-recommendation.md](references/scoring-and-recommendation) — the **single source of truth** for the six Scoring_Dimensions, their weights, the legacy/modern framework classifications and score bands, and the recommendation rules. **Before scoring, you MUST read that file and compute every dimension score exclusively from the criteria and weights defined there** — never from memory or general knowledge.

Default thresholds and bands:

```
Fit_Score:  0 ────────── 40 ─────────── 70 ────────── 100
            │ Replatform │   gray zone   │ Rearchitect │
            │ recommended│ (present both)│ recommended │
                         ↑ 40 belongs to the gray zone  ↑ 70 belongs to Rearchitect
```

- **Fit_Score ≥ Rearchitect_Threshold (default 70, equality inclusive)** → recommend Rearchitect.
- **Fit_Score < Replatform_Threshold (default 40)** → recommend Replatform.
- **Gray zone (40 ≤ score < 70)** → do not settle on a single recommendation; present both strategies in parallel, mapping each decision factor (rework tolerance, migration deadline, container maturity) to the strategy it favors.
- Regardless of the band, the Modernization_Report always presents both strategies with at least one advantage, one disadvantage, and an effort classification each.

**Threshold overrides:** when the user explicitly overrides `Rearchitect_Threshold` or `Replatform_Threshold`, apply the override and report that non-default values are in effect. Validate first: both values must be within 0–100 and `Replatform_Threshold < Rearchitect_Threshold`. If the override is invalid, reject it, apply the defaults (70/40), and report the reason for rejection.

## Report Output

Full template and generation rules: [references/report-generation.md](references/report-generation). The orchestration-level rules:

- **Default filename:** `ECS-Modernize-{application name}-{YYYY-MM-DD}.md` — replace whitespace and path separators in the application name with hyphens (`-`); use the local date at generation time. If the application name cannot be determined, use the source root directory name.
- **Default output location:** the current working directory. The report must be written **outside** the target source code directory — if the CWD is inside the source tree, confirm an external location with the user before writing.
- **User-specified filename/directory takes priority** over the defaults. If the specified destination is inside the target source directory, surface the conflict, confirm an alternative destination, and never write into the source tree without that confirmation.
- **Overwrite confirmation:** if a file with the same name already exists at the destination, ask the user before overwriting. Never overwrite without confirmation.

## Delegation Boundaries

Five sibling skills bound this skill's scope. When a hand-off applies, **name the sibling skill explicitly**, state what it covers, and list the inputs to carry over — do not perform the delegated work yourself.

| Out-of-scope work | Delegate to | Boundary rule |
|---|---|---|
| Greenfield deployment-model design; detailed target design (capacity-provider strategy, task sizing, network design) | `ecs-architect` | Present the compute-model candidates and their applicability conditions, then hand off. Do not produce concrete design values (capacity strategy, sizing numbers, network layouts) in the answer or the report. |
| **Linux container path** environment Terraform (Express Mode / Fargate / Managed Instances / ECS on EC2 Linux) | `ecs-build` | Include a named hand-off with the structured input list (image URI, ports, health check, sizing inputs, volume/EFS needs, session affinity needs). Do not generate Linux container path environment IaC — neither in the answer nor in the Modernization_Report. |
| Live ECS estate inventory (when the migration source already runs on ECS) | `ecs-recon` | Include a named hand-off for the estate inventory. Do not issue AWS API calls to enumerate the running environment; continue Source_Analysis on the source code. |
| Security / compliance hardening (IAM permission design, detailed secrets-management design, compliance audits) | `ecs-security` | Include a named hand-off; do not generate the hardening design. Exception: flagging secret externalization as a Rearchitect modernization item stays in scope. |
| Kubernetes / EKS migration (request mentions only K8s/EKS, not ECS) | `eks-design` | Respond with the named hand-off only. Do not run Source_Analysis, compute a Fit_Score, or recommend a Migration_Strategy. |

**Work this skill does NOT delegate** — no sibling skill covers these, so they remain in scope and are executed here (behind the Execution_Gate):

- **Code transformation** — the integrated Transformation_Plan, including AWS Transform orchestration and agent-executed items.
- **Containerization execution** — Containerization_Artifact generation, image build, and ECR push.
- **Windows_Container_Path environment build** — `ecs-build`'s generation scope is limited to Linux containers, so this skill generates Windows_Environment_Terraform itself. Requests for Windows container path environment IaC are NOT routed to `ecs-build`.

Dockerfile or task-definition **examples inside the Modernization_Report** are not IaC-generation requests: include them as code blocks in the report without an `ecs-build` hand-off.

**Mixed requests:** when a request contains both in-scope work (assessment, strategy decision, or Migration_Execution) and any of the five out-of-scope items above, execute the in-scope work and include the named delegation guidance for each out-of-scope item **in the same response** — do not drop either half.

## IAM Permissions

A ready-to-use least-privilege IAM policy document is available at [`references/iam-policy.json`](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/iam-policy.json). Statements are split by phase via their `Sid` prefix: `Assessment*` statements grant read-only access only (`Describe`/`List`/`Get` operations, matching the Assessment_Phase invariants), while `Execution*` statements grant the per-action-class permissions Migration_Execution needs — ECR repository creation, image push, CodeBuild remote Windows builds, `terraform apply` infrastructure (ECS, capacity, load balancing, IAM roles, logs), and read-only deploy verification. No statement grants delete actions on existing AWS resources. For assessment-only use, attach the `Assessment*` statements alone.

## Note: Future `ecs-build` Windows Support

`ecs-build` currently generates Linux container environments only, which is why this skill generates Windows_Environment_Terraform itself. **If `ecs-build` gains Windows container generation support in the future, replace this skill's Windows_Environment_Terraform generation with a delegation to `ecs-build`**, following the same hand-off format as the Linux container path.
