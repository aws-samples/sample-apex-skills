# Module: Code Transformation

> **Part of:** [ecs-modernize](../SKILL.md)
> **Purpose:** Construct exactly one Transformation_Plan for the code transformation in the approved migration plan, decide per work item whether AWS Transform augmentation (Transform_Augmentation) is applicable and worth proposing, and orchestrate the plan so that augmented items run as AWS Transform jobs while everything else runs as Agent_Executed_Items — all inside one uninterrupted transformation process
> **Prerequisites:** **Execution_Gate passage** (Requirement 14). When Source_Analysis results exist, use them to derive the work items and to propose job scopes and transformation targets; when the assessment was skipped, derive the work items from the transformation targets the user specified at the gate

This module owns code transformation during Migration_Execution: .NET Framework → modern .NET porting, and Java / Node.js / Python runtime version upgrades, among others. The module spans **two reference files**: this file defines the transformation process model (plan construction, augmentation determination, plan-change and availability-change handling), the evidence base for augmentation proposals, and the execution knowledge for Transform-augmented items. The hands-on porting and upgrade knowledge for **Agent_Executed_Items** lives in [code-transformation-agent-led.md](code-transformation-agent-led.md) — load it whenever the plan contains at least one agent-executed item.

This knowledge is application-level and orchestrator-neutral: it describes how the code is transformed, not where it will be deployed. Deployment-target knowledge lives in the path and environment modules.

## Table of Contents

- [Inputs](#inputs)
- [Transformation Process Model](#transformation-process-model)
- [Determination Criteria](#determination-criteria)
  - [Augmentation Applicability — the Two-Condition Test](#augmentation-applicability--the-two-condition-test)
  - [The Four Proposal Dimensions](#the-four-proposal-dimensions)
  - [Bundling Rule for Proposals](#bundling-rule-for-proposals)
  - [Adoption Rules](#adoption-rules)
  - [Non-Applicable and Non-Adopted Items — Agent_Executed_Item](#non-applicable-and-non-adopted-items--agent_executed_item)
  - [Plan Changes](#plan-changes)
  - [Availability Changes During Execution](#availability-changes-during-execution)
  - [Execution Ordering, Confirmations, and Logging](#execution-ordering-confirmations-and-logging)
- [Evidence Comparison and Technical Freshness Directive](#evidence-comparison-and-technical-freshness-directive)
- [Transform-Augmented Item Execution](#transform-augmented-item-execution)
  - [Prerequisite Checklist and Satisfaction Confirmation](#prerequisite-checklist-and-satisfaction-confirmation)
  - [Job Scope — Proposal and Confirmation](#job-scope--proposal-and-confirmation)
  - [The Five-Step Job Workflow](#the-five-step-job-workflow)
  - [Progress Monitoring](#progress-monitoring)
  - [Job Completion — Target-Branch Output and Mandatory Human Review](#job-completion--target-branch-output-and-mandatory-human-review)
  - [Job Failure or Incompletion — Honest Reporting and Fallback Options](#job-failure-or-incompletion--honest-reporting-and-fallback-options)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **Execution_Gate passage** (required) — the gate's two conditions hold: decision inputs exist (completed assessment or user-supplied equivalents) AND the user has explicitly approved the Migration_Strategy and target path. This module never runs before the gate.
- **The approved migration plan** (required) — code transformation must be part of what the user approved. If the approved plan contains no code transformation, this module does not run.
- **Source_Analysis results** (when available) — `tech_stack` (runtimes, frameworks, EOL flags), `blockers` (OS-specific API dependencies with .NET alternatives), and the path modules' modernization items with their `aws_transform_applicability` annotations. These drive work-item derivation and job-scope proposals. When the assessment was skipped, the **user-specified transformation targets** provided at the gate take their place.
- **User-environment facts** (gathered by asking the user, never assumed):
  - **AWS Transform availability** — established exclusively by user confirmation. Cost, organizational policy, connectivity, and region are the user's domain; the skill never infers availability.
  - **Host OS and toolchain presence** — determines local verifiability (dimension (b) below).
- **Action-class confirmation state** — the "code transformation start" confirmation of Requirement 14 gates the execution of every work item (see [Execution Ordering, Confirmations, and Logging](#execution-ordering-confirmations-and-logging)).

---

## Transformation Process Model

Code transformation is **one integrated process with exactly one Transformation_Plan as its backbone** — never a mode choice between "Transform runs everything" and "the agent runs everything". AWS Transform, when available and applicable, augments individual work items inside that single plan; everything it does not cover, the user does not adopt, or it leaves unfinished is executed by the agent inside the same plan.

Run the steps in this order:

```
0. Verify the gate and the action class   -> no work item executes before the
                                             "code transformation start" confirmation
1. Derive the work items                  -> from Source_Analysis results
                                             (or the user-specified targets)
2. Construct exactly ONE Transformation_Plan
                                          -> an ordered work-item list
3. Present the plan to the user           -> list and order, BEFORE any item starts
4. Determine augmentation applicability   -> the two-condition test, per work item
5. Propose Transform_Augmentation         -> four-dimension rationale; bundling allowed
6. Obtain adoption per work item          -> no AWS Transform job without adoption
7. Partition the plan                     -> transform-augmented vs agent-executed,
                                             with a per-item reason for every agent item
8. Execute in plan order                  -> augmented items: Transform-augmented
                                             execution below; agent items:
                                             code-transformation-agent-led.md
9. Record every action                    -> Execution_Log entry before the next
                                             action starts
```

**Why this order:**

- The gate and action-class check (step 0) precedes everything because Requirement 14 makes it the hard precondition: plan *construction and presentation* are preparation, but no work item — augmented or agent-executed — may **start executing** before the "code transformation start" confirmation is complete.
- Derivation (step 1) precedes plan construction because the plan is defined as the ordered list of derived items — items are never invented during execution.
- Presentation (step 3) precedes determination and proposal only in the sense that the user must see the full plan before anything runs; in practice steps 3–6 are one conversation: present the plan, annotate each item with its augmentation determination, propose, and collect adoptions.
- Partitioning (step 7) must complete before execution so that every item has exactly one execution route (`transform` or `agent`) and every agent item has its reason recorded — the user sees the complete picture before the first item runs.
- Logging (step 9) is not a final step but a per-action discipline: each action is recorded before the next action begins.

### Step 0 — Verify the gate and the action class

Confirm Execution_Gate passage and, before executing any work item, confirm the **code transformation start** action class per Requirement 14, presenting: the Transformation_Plan work-item list, the items receiving Transform_Augmentation and the AWS Transform job scope, and the working branch / working directory for Agent_Executed_Items. An ambiguous response is not a confirmation — re-present and ask for an unambiguous answer.

### Step 1 — Derive the work items

Derive transformation work items from the available decision inputs:

| Source | Derived work items (examples) |
|---|---|
| `tech_stack.runtimes` with `eol: true` | Runtime version upgrade per affected project (e.g. Java 8 → a supported LTS; Node.js / Python EOL version upgrades) |
| `tech_stack.runtimes` classified `dotnet_framework`, when the approved target path requires modern .NET | .NET Framework → .NET port, per project or per dependency-ordered project group |
| Path-module modernization items the user adopted into the approved plan (framework migrations, porting prerequisites) | One work item per adopted modernization item |
| `blockers` with `os_specific_api` category and documented .NET alternatives, when the port is approved | API replacement items, ordered after the base port |
| **Assessment skipped** | The user-specified transformation targets, decomposed at the same granularity (per project / per dependency-ordered group) |

Each work item names its target (project(s) / code group), its transformation type (e.g. ".NET Framework 4.8 → .NET 8 port", "Java 8 → 17 upgrade"), and the evidence that produced it (Source_Analysis finding or user statement). Do not add work items that no decision input supports.

### Step 2 — Construct exactly one Transformation_Plan

Order the derived items into **exactly one** Transformation_Plan. Ordering principles, in priority order:

1. **Dependency order** — items whose outputs other items consume come first (shared libraries before the applications that reference them; the base runtime/project-format port before API-replacement items within the same codebase).
2. **Verification friendliness** — prefer an order in which each completed item leaves the codebase in a buildable, verifiable state wherever local verification is possible.
3. **Risk front-loading** — among independent items, schedule the ones with the highest uncertainty earlier, so plan adjustments happen while most of the plan is still pending.

The **exactly-one invariant**: this plan is the single backbone of the whole transformation. Every later change (additions, deletions, reordering — see [Plan Changes](#plan-changes)) mutates *this* plan; never construct a second plan, and never run transformation work outside the plan.

### Step 3 — Present the plan

Present the Transformation_Plan — the work-item list and its order — to the user **before any work item starts executing**. The presentation includes, per item: name, order position, transformation type, target, and (once steps 4–6 have run) the augmentation determination, proposal, and adoption state.

### Steps 4–7 — Determine, propose, obtain adoption, partition

Apply the [Determination Criteria](#determination-criteria) below. The outcome is a fully partitioned plan: every work item carries `execution: transform` (adopted augmentation) or `execution: agent` (not applicable or not adopted, with the reason recorded).

### Step 8 — Execute in plan order

Execute work items in plan order. Transform-augmented items follow [Transform-Augmented Item Execution](#transform-augmented-item-execution); Agent_Executed_Items follow [code-transformation-agent-led.md](code-transformation-agent-led.md). Residual work that an AWS Transform job leaves unfinished is executed as Agent_Executed_Items inside the same plan.

### Step 9 — Record every action

Record each action in the Execution_Log per the rules in [Execution Ordering, Confirmations, and Logging](#execution-ordering-confirmations-and-logging).

---

## Determination Criteria

### Augmentation Applicability — the Two-Condition Test

For each work item, Transform_Augmentation is **applicable** if and only if BOTH conditions hold:

| # | Condition | How it is established |
|---|---|---|
| 1 | **AWS Transform is available** in the user's environment | **Exclusively by asking the user.** Availability is never assumed, inferred, or probed. If it has not been confirmed, it does not hold. The reasons behind unavailability — cost, organizational policy, connectivity, region — are the user's domain and are not second-guessed |
| 2 | **The item's transformation type is within AWS Transform's documented coverage** | Checked against the documented coverage: .NET Framework 3.5+ / .NET Core 3.1 / .NET 5–7 → .NET 8 LTS or .NET 10 porting, and Java / Node.js / Python version upgrades for which out-of-the-box transformation definitions exist. The authoritative, source-cited coverage detail lives in [Evidence Comparison and Technical Freshness Directive](#evidence-comparison-and-technical-freshness-directive) — re-verify against the live sources before relying on it |

Outcomes:

- **Both conditions hold** → the item is applicable; propose augmentation (next section).
- **Either condition fails** → the item is **not applicable**; it becomes an [Agent_Executed_Item](#non-applicable-and-non-adopted-items--agent_executed_item) with the failed condition recorded as its reason.
- **Coverage cannot be confirmed** for the item's transformation type (documentation ambiguous or unreachable) → fail safe: treat the type as **outside coverage**, record that the coverage determination is unconfirmed, and re-check the live sources before repeating the claim.

Applicability is a property of the item, not of the plan: a single plan routinely mixes applicable and non-applicable items.

### The Four Proposal Dimensions

Every augmentation proposal is grounded in the four verifiable dimensions below. A proposal states, per dimension that bears on the item, what the facts are and which execution route they favor — it does not assert unstated preferences.

| Dimension | What it measures | How it is determined |
|---|---|---|
| **(a) Operational factors** | Cost, organizational policy, AWS Transform availability and connectivity | **The user's judgment.** The skill surfaces these as decision points and never decides them on the user's behalf |
| **(b) Local verifiability** | Whether the agent can verify the transformation by building (and testing) locally | **Mechanical**: language × host OS × toolchain presence. Key facts: a **.NET Framework baseline cannot be built on a non-Windows host**, while the **ported, cross-platform .NET result is verifiable with the dotnet SDK on any host**; Java / Node.js / Python items are locally verifiable wherever the matching toolchain is present. When the baseline cannot be verified locally, AWS Transform's managed build environment weighs in favor of augmentation |
| **(c) Scale** | The number of target repositories / projects and their coupling | Counted from the plan's targets. **Multi-repository assets requiring dependency-ordered transformation favor AWS Transform's managed job orchestration**; a single small project weakens that advantage |
| **(d) Transformation-type coverage** | Where the item sits in AWS Transform's documented supported / preview / unsupported ranges, and what published capability evidence exists for agent execution of the same type | Checked against the source-cited [evidence comparison](#evidence-comparison-and-technical-freshness-directive). Capability claims inside a proposal follow that section's evidence and wording rules — including the explicit "no capability-difference evidence" statement when no published evidence distinguishes the two routes |

### Bundling Rule for Proposals

When multiple work items share the **same transformation type AND the same rationale** across the four dimensions, they MAY be bundled into a single proposal — provided the proposal:

1. **Enumerates every covered work item** by name — no "and similar items".
2. **Keeps adoption resolvable per work item** — present the bundle so the user can adopt all, some, or none of the enumerated items (e.g. a per-item checklist). A response of "adopt the bundle" resolves to adopting each enumerated item; a partial answer resolves to exactly the named items.

Items that share a type but differ in rationale (e.g. one is a lone project, another is a dependency-ordered multi-repo group) are proposed separately — bundling never blurs a rationale difference.

### Adoption Rules

- **Adoption is obtained per work item.** Even under a bundled proposal, the record of who adopted what is item-granular.
- **Never start an AWS Transform job for a work item the user has not adopted.** No exceptions — not for "obviously beneficial" items, not for items inside a partially adopted bundle.
- **Ambiguous responses are not adoption.** If the user's answer cannot be clearly resolved to per-item adopt/decline decisions, treat it as neither, do not start any job, and re-present the options asking for an unambiguous answer (consistent with the Requirement 14 confirmation rules).
- Adoption is the user's operational decision (dimension (a)); the skill informs it and never overrides it.

### Non-Applicable and Non-Adopted Items — Agent_Executed_Item

Every work item to which Transform_Augmentation is not applied is positioned as an **Agent_Executed_Item within the same Transformation_Plan** — it is not dropped, deferred, or moved to a separate plan. This covers items where:

- **AWS Transform is not available** — as identified by the user's statement or confirmation (organizational policy, cost, connectivity, or region among the possible causes);
- **the transformation type is outside the documented coverage** (or coverage could not be confirmed — fail safe);
- **the user did not adopt** the proposed augmentation.

**Per-item reason reporting is mandatory**: report, for each Agent_Executed_Item, which of the above reasons applies (naming more than one when more than one holds). Agent_Executed_Items are executed with the knowledge in [code-transformation-agent-led.md](code-transformation-agent-led.md), in plan order, interleaved with augmented items as the order dictates.

### Plan Changes

When the user requests a change to the presented Transformation_Plan — adding, deleting, or reordering work items — before or during execution:

1. **Apply the change to the same, exactly-one Transformation_Plan.** Never fork a second plan or keep a shadow copy; the plan mutates in place.
2. **Re-present the updated plan**: the full work-item list, the updated order, and each item's execution state — **completed / in progress / pending** — so the user sees exactly what the change affects.
3. **Run the augmentation determination for added items**: apply the [two-condition test](#augmentation-applicability--the-two-condition-test) to every newly added work item, and propose augmentation for the applicable ones per the proposal rules.
4. **Preserve completed work**: never discard the outputs or checkpoints (commits) of completed work items as part of a plan change. Deleting a completed item from the plan removes it from the go-forward list only; its recorded results and Execution_Log entries stand.
5. **Hold pending items until re-confirmation**: a plan change alters the content presented at the "code transformation start" confirmation, so per the Requirement 14 re-confirmation rule, do NOT start executing any pending (not-yet-started) work item under the changed plan until the user re-confirms the changed content. An item already in progress at the moment of the change is not interrupted by this rule.

### Availability Changes During Execution

If, during plan execution, a change in AWS Transform's availability is identified — by the user's statement or by user confirmation, in either direction:

1. **Re-run the applicability determination for pending work items** (the two-condition test, with the new availability fact).
2. **Newly applicable items**: propose Transform_Augmentation for them per the [proposal rules](#the-four-proposal-dimensions), with per-item adoption as always.
3. **Items no longer applicable** — including items the user had adopted whose AWS Transform job has **not yet started**: position them as Agent_Executed_Items per the [rule above](#non-applicable-and-non-adopted-items--agent_executed_item), and report the reason per item (availability lost).
4. **Completed and in-progress items are untouched**: an availability change never alters how completed items are recorded, and never interrupts or re-routes an item already in progress.

### Execution Ordering, Confirmations, and Logging

- **Confirmation before execution.** No work item — Transform-augmented or agent-executed — starts executing until the **code transformation start** action-class confirmation of Requirement 14 is complete. The confirmation presents: the Transformation_Plan work-item list, the items receiving augmentation and the AWS Transform job scope, and the working branch / working directory for Agent_Executed_Items. If any of that presented content later changes (plan changes, scope changes, working-location changes), re-obtain the confirmation with the changed content before executing under it.
- **Every action is logged, before the next action starts.** Record each attempted action of this module — AWS Transform job starts, Agent_Executed_Item executions, checkpoint commits, plan mutations — in the **Execution_Log**, success or failure alike, before beginning the next action. Each entry carries at least: the action type, the result (success or failure), the created/modified targets (repository, branch, file paths, and/or resource identifiers as applicable), a timestamp in a timezone-identifiable format, and whether a corresponding user confirmation existed. The log's storage forms and save-failure fallback follow the canonical [deploy-verify-handoff.md — Execution_Log Rules](deploy-verify-handoff.md#execution_log-rules).

---

## Evidence Comparison and Technical Freshness Directive

This section is the evidence base for the coverage condition of the [two-condition test](#augmentation-applicability--the-two-condition-test) and for dimension (d) of the [proposal dimensions](#the-four-proposal-dimensions). Every coverage or capability claim this module makes — in an applicability determination, an augmentation proposal, or a user-facing explanation — traces to a row of the table below and its cited source.

### Technical Freshness Directive

> **Re-verify against the live sources before making any coverage or capability claim.** AWS Transform's coverage AND the published model/agent capability evidence both change quickly. The table below records a **snapshot taken at authoring time**; the live documentation and benchmarks at the cited URLs are authoritative. Before relying on a row — to decide the coverage condition, to ground a proposal dimension, or to state a capability fact to the user — check the row's source URL and use what the live source says today. If the live source contradicts a row, follow the live source, treat the row as stale, and say so when the discrepancy is relevant to the user's decision. If a live source is unreachable, apply the fail-safe rule of the two-condition test (treat coverage as unconfirmed) and record that the claim rests on the unverified snapshot.

The directive applies to **both sides** of the comparison — AWS Transform's documented coverage and the published evidence of agent capability — because both are moving targets.

### Evidence Comparison Table

Snapshot facts, each with its source. Re-verify per the directive above before use.

| Area | Verified facts (authoring-time snapshot) | Source |
|---|---|---|
| **AWS Transform for .NET — documented coverage** | **Source versions:** .NET Framework 3.5 and later, .NET Core 3.1, .NET 5.x and later, .NET 8. **Target versions:** .NET 8 (LTS) / .NET 10 — C# only. **Supported project types:** MVC + Razor, SPA backends, Web API, Web Forms (including UI conversion to Blazor Server), unit tests, WCF. **In preview:** WinForms, WPF, Xamarin, VB.NET | [AWS Transform for .NET](https://docs.aws.amazon.com/transform/latest/userguide/dotnet.html) |
| **Documented gaps — work AWS Transform defers to "manual or AI code companion"** | `.svc` / `.ashx` handlers, service references (WSDL), mixed aspx + cshtml codebases, third-party UI libraries, and Web Site projects are documented as requiring manual or AI-code-companion follow-up. Architecture refactoring and non-.NET languages are out of scope — AWS's own guidance directs those to "AWS Transform custom or Kiro" | [UI porting scope and gaps](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-porting-ui.html); [Before you transform](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-bp-before-transform.html) |
| **Transform harness advantages** | A network-isolated managed build environment with an AI-driven build-repair loop; private NuGet feed resolution; dependency-ordered multi-repository job orchestration. These are properties of the execution harness — they weigh on dimensions (b) and (c) regardless of any model-capability comparison | [AWS Transform FAQ](https://aws.amazon.com/transform/faq/) |
| **Transform-side assessment capabilities — and their boundary** | Job-level code assessment report (inside the 5-step job plan); continuous modernization analyses, including modernization-readiness (identifies containerization candidates); infrastructure / TCO migration assessment. **Boundary note:** none of these cover this skill's Assessment_Phase core — Fit_Score scoring, Replatform / Rearchitect strategy determination, or the mapping to ECS computing models. Treat them as optional complementary inputs, never as substitutes for this skill's assessment | [Creating a job plan](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-creating-job-plan.html); [Assessment and planning](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-bp-assessment-planning.html); [Continuous modernization](https://docs.aws.amazon.com/transform/latest/userguide/continuous-modernization.html); [AWS Transform launch guide](https://docs.aws.amazon.com/transform/latest/launchguide/aws-transform.html) |
| **Agent-side capability evidence** | MigrationBench — a repository-level Java 8 → 17/21 migration benchmark (full set 5,102 repositories; curated subset 300). On the curated 300-repository subset, an agentic framework with Claude 4.5 Sonnet achieves **pass@1 71.67% (minimal migration) / 53.33% (maximal migration)**. This is evidence that agent execution is capable on Java version upgrades — it is NOT a head-to-head comparison against AWS Transform. **No published benchmark exists for agent-led .NET Framework porting**: .NET porting sits in the "no capability-difference evidence" zone | [MigrationBench, arXiv:2505.09569](https://arxiv.org/abs/2505.09569) |

### The "No Capability-Difference Evidence" Wording Rule

Where no published evidence distinguishes the capability of Transform_Augmentation from agent execution for a given transformation type, apply ALL three of the following, verbatim in spirit:

1. **State explicitly that no capability-difference evidence exists** for that transformation type — say "no capability-difference evidence"; do not soften it into an implied preference or omit it.
2. **Guide the adoption decision by the operational factors** of dimension (a) — cost, organizational policy, availability, connectivity — together with the mechanically determinable dimensions (b) local verifiability and (c) scale. These are decidable without capability evidence.
3. **Never claim that either execution route is superior or inferior without citable evidence.** A capability claim in a proposal must trace to a row of the table above (re-verified per the freshness directive) or to another citable source named in the proposal.

Where the rule applies, per the snapshot:

- **.NET Framework → modern .NET porting** is squarely in the zone: AWS Transform's coverage is documented (table row 1), but no published benchmark measures agent-led .NET porting, and no published head-to-head comparison exists — so no capability-difference claim is permitted in either direction. The proposal instead leans on the harness facts (row 3: managed Windows-capable build + repair loop, decisive when the baseline is not locally verifiable per dimension (b)) and the operational factors.
- **Java version upgrades**: MigrationBench evidences agent capability (row 5), but evidence of one route's capability is not evidence of a capability *difference* — absent a published comparison against AWS Transform, the wording rule still applies to comparative claims.

Distinguish carefully between **capability claims** (what quality of transformation each route achieves — evidence-gated by this rule) and **harness/process facts** (managed build environment, private NuGet resolution, multi-repo orchestration, local verifiability — mechanically or documentably true and citable from the table without a capability comparison). Proposals may freely use the latter; the former only with evidence.

---

## Transform-Augmented Item Execution

This section is the execution knowledge for work items whose augmentation the user adopted (`execution: transform`). An adopted item — or a bundled group of adopted items sharing one job — is executed as an **AWS Transform job driven through AWS Transform's own service experience (Web / IDE)**: a workflow with built-in human approval points, guided by the skill but never run unattended by it. The stages below are strict gates, in order:

```
A. Prerequisite checklist   -> every item user-confirmed satisfied, or STOP
B. Job scope                -> proposed from adopted items; user-confirmed, or STOP
C. Five-step job workflow   -> connector -> discover -> assess -> plan approval -> transform
D. Progress monitoring      -> Web dashboard / IDE worklog, presented to the user
E. Completion               -> target-branch output + mandatory human review; the skill NEVER merges
F. Failure / incompletion   -> honest report + options; NEVER claimed as success
```

Two framing rules govern every stage:

- **Human-in-the-loop by design.** Present the AWS Transform job as progressing through AWS Transform's own service experience, which interposes human approvals — connector approval, transformation-plan approval, and human-input requests surfaced in the collaboration pane / chat. Never claim that the skill performs — or that adopting augmentation results in — a fully autonomous, unattended transformation. Even where the Transform experience offers lower-touch settings, the skill's guidance keeps the human decision points (plan approval, post-job code review) explicit and in the user's hands.
- **The gate and the log still apply.** The "code transformation start" confirmation of Requirement 14 gates job starts exactly as it gates agent-executed work, and every stage's actions — prerequisite confirmations, scope confirmations, job starts, completion/failure findings — are recorded in the Execution_Log per [the logging rules](#execution-ordering-confirmations-and-logging).

Procedural details in this section (prerequisite specifics, workflow step names, monitoring surfaces) are snapshot facts: re-verify them against the cited live documentation per the [Technical Freshness Directive](#technical-freshness-directive) before presenting them to the user.

### Prerequisite Checklist and Satisfaction Confirmation

Before anything else, present the prerequisite checklist to the user and establish each item's satisfaction **by asking the user** — the same never-probe discipline as the availability condition. Baseline checklist (add job-type-specific items the live documentation requires):

| # | Prerequisite | "Satisfied" means | Fulfillment steps when unsatisfied |
|---|---|---|---|
| 1 | **Environment readiness — AWS Transform enabled + user access** | AWS Transform is enabled for the organization and the user can sign in to the AWS Transform web experience via IAM Identity Center (the web application URL is known) | An administrator enables AWS Transform from the AWS console and assigns the user or group in IAM Identity Center; guide per [Setting up AWS Transform](https://docs.aws.amazon.com/transform/latest/userguide/transform-setup.html) |
| 2 | **Workspace readiness** | A workspace exists (or the user is ready to create one) in which the job will run, and collaborators who must approve or review are invited | Create a workspace in the AWS Transform web experience — or via the IDE flow, which creates/selects a workspace at job start; guide per [AWS Transform environment](https://docs.aws.amazon.com/transform/latest/userguide/transform-environment.html) and [Modernizing .NET in Visual Studio](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-ide-vs.html) |
| 3 | **Source repository connector** | A connector to the source host exists or can be created — GitHub / GitLab / Bitbucket via AWS CodeConnections **in the same Region as the job**, or the documented Amazon S3 alternative — and any repository-admin approval it needs is obtainable. One source repository connector per job | Create the connector in the job's first phase; where repository permissions require it, a repository admin approves the connector; guide per [Creating a source code repository connector](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-creating-repo-connector.html) |
| 4 | **Output-branch write access** | The connector's permissions allow AWS Transform to write the transformed code to a **new target branch** in the repository (the source branch is never the write target) | Resolve the permission scope with the repository admin — same source as #3 |

Rules:

- **Present the full checklist first**, then confirm the items one by one; record `{item, satisfied}` per the [output schema](#output-schema).
- **For every unsatisfied prerequisite, present its fulfillment steps** (the table above, re-verified against the live docs) — never silently skip an item or assume it satisfied.
- **Hard gate: do not proceed to job-scope confirmation until EVERY prerequisite is confirmed satisfied.** Partial satisfaction unlocks nothing, and an unconfirmed item counts as unsatisfied — the same fail-safe posture as the two-condition test.

### Job Scope — Proposal and Confirmation

- **Derive the proposal from the adopted work items.** The proposed job scope is the set of projects / code groups the adopted items name, tracing back to Source_Analysis findings (or the user-specified targets when the assessment was skipped). The scope covers adopted items only — never fold non-adopted or non-applicable items into a job scope.
- **Propose, then confirm.** Present the proposed scope — repositories, projects / code groups, and which adopted work item each entry serves — and obtain the user's confirmation. The scope is **fixed only on an unambiguous confirmation**; an ambiguous response fixes nothing — re-present and ask again (the Requirement 14 discipline).
- **Scope changes reopen this stage.** A scope change requested before the job starts is re-proposed and re-confirmed; once the job is running, scope adjustments happen through re-runs (see [failure / incompletion](#job-failure-or-incompletion--honest-reporting-and-fallback-options)).

### The Five-Step Job Workflow

Guide the user through AWS Transform's five-step job plan ([Creating the AWS Transform .NET job plan](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-creating-job-plan.html)). The steps are AWS Transform's own; the skill's role at each step is to keep the job aligned with the confirmed scope and to surface Transform's human-input requests to the user:

| Step | Transform phase | What happens | The skill's guidance |
|---|---|---|---|
| 1 | **Connector** — "Get resources to be transformed" | The source repository connector is created or selected; a repository admin may need to approve it | Reuse the connector confirmed in the prerequisite stage; surface any pending approval request to the user |
| 2 | **Discover** | AWS Transform discovers repositories in source control; the user selects repositories for assessment | Guide the selection to match the confirmed job scope — no more, no less |
| 3 | **Assess** | Selected repositories are assessed; assessment reports become available | Point the user to the assessment reports. Discrepancies with this skill's own Source_Analysis are surfaced, not hidden — and per the boundary note in the [evidence table](#evidence-comparison-table), Transform's job-level assessment never substitutes for this skill's Assessment_Phase |
| 4 | **Plan approval** — "Prepare for transformation" | Transform reports missing dependencies (upload or ignore); the target branch name, target version, and job settings are set; the transformation plan is approved — by a repository admin where required ([Confirming your repositories](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-confirming-repos.html)) | Present the plan-approval decision to the user, and confirm the **target branch name** here — everything downstream (review, the no-merge rule, residual work location) keys on it |
| 5 | **Transform** | The transformation runs with ongoing status until it completes; transformation reports explain what changed and why | Hand off to [progress monitoring](#progress-monitoring); do not represent the run as finished until completion is confirmed |

The IDE experience (Visual Studio: "Port with AWS Transform") compresses the same workflow into an in-IDE flow — workspace selection, an assessment report and transformation plan surfaced for review, and plan approval before the transformation begins ([dotnet-ide-vs](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-ide-vs.html)). The plan-review-and-approval decision point exists in the IDE flow too; the skill's guidance keeps it in the user's hands regardless of the mode settings the extension offers.

### Progress Monitoring

When the job starts, present how to check its progress — in both experiences:

- **Web experience** ([Transforming your .NET code](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-transforming-code.html)): the **Dashboard** tab shows the job status (Awaiting user input / Time elapsed / Running), the job details (target branch destination, target version, job ID), the transformation summary, and real-time Repository / Package / Unit-test status; the **Tasks** tab shows per-step status (Not started / Await user input / In Progress / Completed); the **Approvals** tab holds pending approvals; the **Worklog** tab is the action-by-action log.
- **IDE experience** ([dotnet-ide-vs](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-ide-vs.html); [dotnet-ide-troubleshoot](https://docs.aws.amazon.com/transform/latest/userguide/dotnet-ide-troubleshoot.html)): the **AWS Transform Job Plan**, **Chat**, and **Worklog** windows track the job; whether the job is still active is verifiable in Visual Studio's Output tab (Amazon Q Language Client output).

**Grounding rule:** every job-status statement the skill makes is grounded in what the Transform experience shows or what the user reports — never inferred from elapsed time or optimistic defaults. Surface "Await user input" states promptly: the job does not advance without the human input they wait on.

### Job Completion — Target-Branch Output and Mandatory Human Review

Completion is established **by confirmation** — observed in the Transform experience or reported by the user. On confirmed completion:

1. **Present the output location.** The transformed code is written to the **target branch** AWS Transform created in the repository; the original source branch is untouched — consistent with the Migration_Execution safety rails.
2. **Present human code review as a mandatory step** before the output is used for anything — merging, deploying, or serving as the base for residual work. Report the review perspectives, at minimum:
   - **Buildability** — whether the transformed code builds. Transform's managed build ran during the job, and post-transformation unit-test results are available where the repositories contained runnable tests, but the review verifies buildability in the user's own environment (the ported cross-platform .NET result is verifiable with the dotnet SDK on any host — dimension (b));
   - **Untransformed parts** — what the job did not convert: read the transformation reports, and check the documented gap classes of the [evidence table](#evidence-comparison-table) (`.svc` / `.ashx` handlers, WSDL service references, mixed aspx + cshtml, third-party UI libraries, Web Site projects). These are the candidate residual Agent_Executed_Items;
   - **Behavioral verification** — the need for functional testing beyond a successful build.
3. **Never merge.** The skill does not merge the target branch into the source branch — under any circumstances. Report explicitly that the merge decision belongs to the user, after their code review.
4. **Route residual work into the same plan.** Untransformed parts the user wants completed become Agent_Executed_Items in the same Transformation_Plan, executed per [code-transformation-agent-led.md](code-transformation-agent-led.md) — including the working-location choice that offers the Transform target branch, or a branch derived from it, as user-approved options.
5. **Log the completion** in the Execution_Log before the next action starts.

### Job Failure or Incompletion — Honest Reporting and Fallback Options

When the job's failure — or its ending without completing the transformation — is confirmed (including by the user's report):

1. **Report the failure as a fact.** Never claim the transformation succeeded, in whole or in any part beyond what is confirmed. Partial output on the target branch is material for review, not grounds for a success claim.
2. **Report how to check the failure reasons**: in the Web experience, the Dashboard's repository status table (In-progress / Failed / Success), the per-step status on the Tasks tab, the Worklog's action log, and the assessment / transformation reports; in the IDE experience, the Worklog window and the Visual Studio Output logs.
3. **Present the options** — at minimum both of:
   - **Re-run with an adjusted scope** — narrow or split the job scope (for example, excluding the failing repository or project) and return to the [job-scope stage](#job-scope--proposal-and-confirmation) for re-confirmation before the re-run;
   - **Execute as an Agent_Executed_Item within the SAME Transformation_Plan** — reposition the affected work item(s) to agent execution with the reason recorded ("Transform job failed / did not complete"), following the per-item reason-reporting discipline of the [Agent_Executed_Item rule](#non-applicable-and-non-adopted-items--agent_executed_item) and executed per [code-transformation-agent-led.md](code-transformation-agent-led.md).
   Where the failure cause is identifiable and fixable (for example, missing dependencies flagged at plan approval), a third option — resolve the cause and re-run the same scope — may be presented alongside.
4. **The choice is the user's** — the same operational-factors judgment as adoption (dimension (a)); the skill informs it and never decides it.
5. **Log the failure** — action, result = failure, targets, timestamp, confirmation state — in the Execution_Log before the next action starts.

---

## Output Schema

This module produces the `code_transformation` block. Hold the structure in conversation context; the durable record is the Execution_Log (per the logging rules above).

```yaml
code_transformation:
  transformation_plan:               # exactly ONE plan per execution — the invariant backbone
    presented: bool                  # plan (list + order) presented before any item started
    items:
      - name: string                 # e.g. "Port OrderService to .NET 8"
        order: int                   # position in the plan
        augmentation:
          applicable: bool           # result of the two-condition test
          reason: string             # grounds: which conditions held/failed
                                     # (availability per user confirmation; coverage per the
                                     #  evidence comparison)
          proposed: bool             # a proposal (possibly bundled) covered this item
          adopted: bool | null       # per-item adoption; null when no proposal was made
        execution: transform | agent | null
                                     # transform = adopted augmentation; agent = Agent_Executed_Item
                                     # (not applicable or not adopted); null = not yet partitioned
        status: pending | in_progress | done | verification_failed | skipped
        build_verified: bool | not_possible    # agent-executed items only (see agent-led file)
        test_verified: bool | not_available    # agent-executed items only
        checkpoint_commit: string | null       # agent-executed items only
  transform_jobs:                    # one entry per adopted item group with a started/planned job
    - prerequisites: [{item: string, satisfied: bool}]
      scope: [string]                # projects / code groups in the job scope
      status: string                 # job progress as confirmed via the Transform experience
      target_branch: string          # where AWS Transform outputs the result
  agent_work_location:               # user-approved working location for Agent_Executed_Items
    branch_or_dir: string
    based_on_transform_target: bool  # continuing on a Transform target branch (user-approved)
  local_verification_gaps: [string]  # items whose local verification was not possible, with why
  human_review_required: true        # constant: human code review precedes any merge, always
```

**Reporting invariants:**

- Exactly one `transformation_plan` exists per execution; plan changes mutate it in place.
- Every item with `execution: agent` has a `reason` naming why augmentation was not applied.
- `adopted: true` never appears on an item where `applicable: false`.
- No `transform_jobs` entry exists for an item without `adopted: true`.
- Item status transitions to `in_progress` only after the "code transformation start" confirmation is complete.

---

## Edge Cases

### Assessment was skipped

Derive the work items from the transformation targets the user specified when passing the gate. If the targets are too coarse to decompose into ordered work items (e.g. "modernize the app" with no project detail), ask the user to identify the concrete targets — do not invent items. The skipped-assessment risk disclosure itself belongs to the gate, not this module; here it only means Source_Analysis evidence is unavailable for derivation and proposals.

### The approved plan includes code transformation, but no work items are derivable

If neither Source_Analysis results nor user statements yield any transformation work item, report that finding and ask the user whether code transformation should be removed from the migration plan or whether they can name targets. Do not fabricate work items to fill the plan.

### AWS Transform availability was never established

Unconfirmed availability is **not** availability: condition 1 fails and items route to Agent_Executed_Item — but before settling that, ask the user once, since availability is cheap to confirm and changes the proposal landscape. Record the user's answer; never probe the environment to find out.

### Coverage cannot be confirmed for a transformation type

Treat the type as outside coverage (fail safe), record that the determination is unconfirmed, and note what would settle it (the live documentation listed in the evidence comparison). Re-verify against the live sources before repeating the coverage claim elsewhere.

### Ambiguous adoption response

A reply that cannot be resolved to per-item adopt/decline decisions (including an ambiguous answer to a bundled proposal) is treated as neither adoption nor refusal: start no job, and re-present the per-item options asking for an unambiguous answer.

### Plan change arrives while an item is in progress

The in-progress item continues under its existing confirmation; the change applies to the plan around it. Re-present the updated plan with per-item states, run augmentation determination on added items, and hold all pending items until the re-confirmation completes. Completed items' outputs and checkpoints are preserved unconditionally.

### Availability is lost after adoption but before the job starts

The adopted item's job has not started, so it is repositioned as an Agent_Executed_Item with the reason "availability lost before job start". The adoption record remains in the log; the item's `execution` route changes to `agent`.

### An item is both outside coverage and unavailable

Report both reasons on the single Agent_Executed_Item entry — reasons are not mutually exclusive, and the user should see the complete grounds.

---

## Sources

- AWS Transform for .NET — service documentation (coverage baseline for the two-condition test): https://docs.aws.amazon.com/transform/latest/userguide/dotnet.html
- AWS Transform — user guide root (job workflow, transformation definitions for language version upgrades): https://docs.aws.amazon.com/transform/latest/userguide/
- AWS Transform for .NET — UI porting scope and documented gaps: https://docs.aws.amazon.com/transform/latest/userguide/dotnet-porting-ui.html
- AWS Transform for .NET — pre-transformation guidance (out-of-scope work routed to "AWS Transform custom or Kiro"): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-bp-before-transform.html
- AWS Transform — FAQ (harness properties: managed build + repair loop, private NuGet, multi-repo orchestration): https://aws.amazon.com/transform/faq/
- AWS Transform for .NET — creating a job plan (5-step workflow, job-level code assessment): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-creating-job-plan.html
- AWS Transform for .NET — assessment and planning best practices: https://docs.aws.amazon.com/transform/latest/userguide/dotnet-bp-assessment-planning.html
- AWS Transform — setting up (service enablement, IAM Identity Center user assignment): https://docs.aws.amazon.com/transform/latest/userguide/transform-setup.html
- AWS Transform — environment (workspaces, views, human-in-the-loop collaboration pane): https://docs.aws.amazon.com/transform/latest/userguide/transform-environment.html
- AWS Transform for .NET — creating a source code repository connector (AWS CodeConnections, same-Region rule, S3 alternative): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-creating-repo-connector.html
- AWS Transform for .NET — confirming repositories (target branch name, target version, job settings): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-confirming-repos.html
- AWS Transform for .NET — transforming your code (Dashboard progress monitoring, job status, target branch destination): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-transforming-code.html
- AWS Transform for .NET — Visual Studio IDE experience (in-IDE workflow, plan review and approval): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-ide-vs.html
- AWS Transform for .NET — IDE troubleshooting (progress verification via Worklog / Output logs): https://docs.aws.amazon.com/transform/latest/userguide/dotnet-ide-troubleshoot.html
- AWS Transform — continuous modernization (modernization-readiness analysis): https://docs.aws.amazon.com/transform/latest/userguide/continuous-modernization.html
- AWS Transform — launch guide (infrastructure / TCO migration assessment): https://docs.aws.amazon.com/transform/latest/launchguide/aws-transform.html
- MigrationBench — repository-level Java 8 → 17/21 migration benchmark (agent-capability evidence): https://arxiv.org/abs/2505.09569

The full source-cited evidence comparison (coverage detail, documented gaps, harness advantages, capability benchmarks) lives in [Evidence Comparison and Technical Freshness Directive](#evidence-comparison-and-technical-freshness-directive); its freshness directive governs every coverage and capability claim in this file.
