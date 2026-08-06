# Module: Report Generation

> **Part of:** [ecs-modernize](../SKILL.md)
> **Purpose:** Assemble the outputs of every assessment module into exactly one Markdown Modernization_Report file — the deliverable of the Assessment_Phase and its only file-system write
> **Prerequisites:** All assessment modules — tech stack detection, blocker detection, scoring and recommendation, Replatform path, Rearchitect path

This is the final module of the Assessment_Phase. It performs no analysis of its own: it renders the blocks the prerequisite modules produced (`analysis`, `tech_stack`, `blockers`, `scoring`, `recommendation`, `replatform_path` with `windows_container_path`, `rearchitect_path`) into a single Markdown file. Writing that file is the **only** file-system write the Assessment_Phase ever performs — no drafts, no intermediate files, no companion files. All the read-only invariants from [SKILL.md](../SKILL.md) stay in force while this module runs.

## Table of Contents

- [Inputs](#inputs)
- [Generation Procedure](#generation-procedure)
- [File Name and Destination Rules](#file-name-and-destination-rules)
  - [Default File Name](#default-file-name)
  - [Default Destination](#default-destination)
  - [User-Specified Destination](#user-specified-destination)
  - [Overwrite Confirmation](#overwrite-confirmation)
- [Report Structure](#report-structure)
  - [Mandatory Section Order](#mandatory-section-order)
  - [Report Template](#report-template)
  - [Section-by-Section Rules](#section-by-section-rules)
  - [Windows_Container_Path Placement](#windows_container_path-placement)
- [Cross-Cutting Content Rules](#cross-cutting-content-rules)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Inputs

Every assessment module must have completed before this module runs — partial completion counts (undetermined items excluded from scoring, unreadable paths excluded from analysis), but a module that never ran does not. The inputs are the blocks those modules hold in conversation context:

| Block | Producing module | Feeds report section(s) |
|---|---|---|
| `analysis` envelope (`target.source_path`, `target.app_name`, `partial`, `excluded_paths`) | Tech stack detection (updated by blocker detection) | Header, §1, §1.5, file name |
| `tech_stack` (languages, frameworks, runtimes, app servers, `undetermined_items`) | [tech-stack-detection.md](tech-stack-detection.md) | §1, §1.5 |
| `blockers` | [blocker-detection.md](blocker-detection.md) | §2, §4, §5, §6 |
| `scoring` (dimensions, exclusions, renormalization, `fit_score`) | [scoring-and-recommendation.md](scoring-and-recommendation.md) | §3, §1.5 |
| `recommendation` (thresholds, default/constraint-adjusted recommendation, grounds, confidence) | [scoring-and-recommendation.md](scoring-and-recommendation.md) | §4, §7 |
| `replatform_path` + `windows_container_path` | [replatform-path.md](replatform-path.md) | §5, §7 |
| `rearchitect_path` | [rearchitect-path.md](rearchitect-path.md) | §6, §7 |
| User-specified output file name and/or directory (optional) | Conversation | File name and destination |

**Write discipline** — reiterated from SKILL.md because this module is where it bites: exactly one file is written, it lands outside the target source code directory, and nothing else touches the file system. The report content is assembled entirely in conversation context and written in a single operation.

---

## Generation Procedure

Run the steps in this order:

```
0. Verify prerequisites          -> every assessment module completed (partial counts)
1. Determine the file name       -> user-specified value, else the default rule
2. Determine the destination     -> user-specified value, else CWD; source-tree containment check
3. Check for an existing file    -> same name at the destination => overwrite confirmation
4. Assemble the report           -> the template below, all eight sections in order,
                                    plus §1.5 when the analysis is incomplete
5. Audit the content             -> evidence citation per recommendation, credential
                                    non-disclosure, code-blocks-only artifacts, no IaC
6. Write the file                -> exactly one write; on failure, the fallback (Edge Cases)
7. Report the result             -> the saved path to the user (never claim a save that failed)
```

**Why this order:** the file name and destination questions (steps 1–3) can require user confirmation — settle them before assembling content so a refused destination never strands a finished report. The content audit (step 5) runs after assembly and before the write, because a report that fails the audit must be fixed in context, not on disk. Step 7's honesty rule depends on step 6's actual outcome.

### Step 0 — Verify prerequisites

Report generation is the final stage of a full assessment (routing table module 6). Confirm that tech stack detection, blocker detection, scoring and recommendation, the Replatform path, and the Rearchitect path have all produced their output blocks. A partially complete analysis — `analysis.partial: true`, undetermined items, excluded dimensions — is still complete for this purpose: the report carries the incompleteness (§1.5) rather than blocking on it. A module that never ran is different — see [Edge Cases](#report-requested-before-the-assessment-is-complete).

### Steps 1–3 — Name, destination, overwrite

Apply the [File Name and Destination Rules](#file-name-and-destination-rules) below.

### Step 4 — Assemble

Render the [Report Template](#report-template). All eight mandated sections appear in the mandated order; none may be omitted. Include §1.5 exactly when the analysis is incomplete (see [Section-by-Section Rules](#section-by-section-rules)).

### Step 5 — Content audit

Before writing, verify every rule in [Cross-Cutting Content Rules](#cross-cutting-content-rules):

- [ ] All eight sections present, in order; every section with no applicable content states the absence explicitly.
- [ ] Every recommendation item cites at least one of {detected file path, dimension score, applied threshold} **within its own section**.
- [ ] No part of any detected credential value appears anywhere.
- [ ] Containerization artifact examples (Dockerfile, task definition) appear only as fenced code blocks; no Terraform / CloudFormation / CDK code appears anywhere.
- [ ] §1.5 present iff the analysis is incomplete, immediately after §1.

### Steps 6–7 — Write and report

Write the single file. On success, report the saved path. On any failure, apply the [write-failure fallback](#file-write-fails) — never claim the report was saved.

---

## File Name and Destination Rules

These rules expand the orchestration-level summary in SKILL.md's Report Output section; the two must never disagree.

### Default File Name

When the user has not specified an output file name:

```
ECS-Modernize-{application name}-{YYYY-MM-DD}.md
```

- **`{application name}`** — the application name identified by Source_Analysis (`analysis.target.app_name`, captured from build definitions by tech stack detection). When it is null (not identifiable), fall back to the **root directory name** of `analysis.target.source_path`.
- **Character replacement** — in the chosen name, replace **every** whitespace character and **every** path separator (`/` and `\`) with a hyphen (`-`), one hyphen per replaced character, no collapsing, no trimming. The resulting name segment therefore contains no whitespace and no path separators. Example: `Order Processing/legacy` → `Order-Processing-legacy` → `ECS-Modernize-Order-Processing-legacy-2025-06-01.md`.
- **`{YYYY-MM-DD}`** — the **local date at report generation time**, zero-padded (for example `2025-06-01`). Local means the environment's local time zone, not UTC.

The rule is deterministic: the same application name and date always produce the same file name.

### Default Destination

When the user has not specified an output directory, the destination is the **current working directory** — with one check first:

- Resolve the absolute paths of the destination directory and of `analysis.target.source_path`. If the destination **is** the source root or **any directory under it**, do not write there. State that the report must land outside the target source tree (the Assessment_Phase write invariant), and **confirm an external location with the user** before writing.

### User-Specified Destination

A user-specified file name and/or output directory **takes priority over the defaults** — each independently (a user file name combines with the default directory, and vice versa).

- If the specified destination is inside the target source code directory, **surface the conflict explicitly** (the specified path vs. the phase invariant that the report lands outside the source tree), **confirm an alternative destination**, and never write into the source tree without that explicit confirmation. Do not silently relocate the file either — the user decides.

### Overwrite Confirmation

If a file with the resolved name already exists at the resolved destination:

- **Ask the user before overwriting.** Present the existing file's path and offer the choices: overwrite, write under a different name (for example a numbered suffix), or write to a different directory.
- **Never overwrite without confirmation.** A response that cannot be clearly identified as approval is not confirmation — re-present the choices.

---

## Report Structure

### Mandatory Section Order

The Modernization_Report contains these eight sections **in exactly this order** — no section may be omitted, reordered, or merged:

| # | Section | Source block(s) |
|---|---|---|
| 1 | Analysis summary (detected tech stack) | `tech_stack`, `analysis` |
| 1.5 | Incomplete analysis items — **conditional**, immediately after §1 | `analysis`, `tech_stack.undetermined_items`, `scoring.excluded_dimensions` |
| 2 | Blocker list | `blockers` |
| 3 | Fit_Score and Scoring_Dimension breakdown | `scoring` |
| 4 | Recommended Migration_Strategy and grounds | `recommendation` |
| 5 | Replatform path details (incl. Windows_Container_Path when applicable) | `replatform_path`, `windows_container_path` |
| 6 | Rearchitect path details | `rearchitect_path` |
| 7 | Strategy comparison table (both strategies, always) | `recommendation`, both path blocks |
| 8 | Next steps of the migration plan | all |

§1.5 is not one of the eight mandated sections: it appears **exactly when** the analysis is incomplete (see its rules below) and is always placed immediately after §1. Its absence from a fully complete analysis does not violate the no-omission rule.

### Report Template

```markdown
# ECS Modernization Report — {application name}
_generated {YYYY-MM-DD} · source: {source_path} · fit score: {N}/100 · recommendation: {strategy}_

## 1. Analysis Summary
(Detected tech stack: languages / frameworks / runtimes / app servers,
 with the evidence for every determination)

## 1.5 Incomplete Analysis Items        <- only when the analysis is incomplete
(Undetermined items and excluded ranges: each with its reason and its
 impact on the results, incl. exclusion from the Fit_Score computation)

## 2. Blocker List
(Per blocker: category, remediation class, evidence paths, reason.
 Zero blockers => the explicit "no blockers detected" statement.
 Credential values never appear)

## 3. Fit_Score and Scoring_Dimension Breakdown
(Total score; per-dimension score, weight, contribution; renormalization
 flag and excluded dimensions)

## 4. Recommended Migration_Strategy and Grounds
(Recommendation or parallel presentation; Fit_Score, applied thresholds,
 ALL must_fix blockers or their explicit absence, lowest-scoring dimension;
 confidence note; labeled constraint-adjusted recommendation when present)

## 5. Replatform Path Details
(ECS on EC2 static configuration; the three containerization policy items;
 persistence and session handling; must-fix minimal remediations and
 unresolved items. Windows_Container_Path as a subsection when applicable;
 the not-applicable judgment + grounding blockers when ruled out)

## 6. Rearchitect Path Details
(The three compute-model candidates with applicability judgments;
 modernization items with evidence and effort tier; AWS Transform
 applicability notes; framework migration options; the ecs-architect
 delegation statement)

## 7. Strategy Comparison Table
(Both strategies, always: advantages / drawbacks / effort classification
 (small / medium / large) / assumed target configuration / decision-factor
 mapping)

## 8. Next Steps
(Actions in recommended order; hand-off points to ecs-architect, ecs-build,
 ecs-security; AWS Transform tooling as a recommended next step where
 applicable — recommendation only, never executed here)
```

### Section-by-Section Rules

**Header** — the title carries the application name (before hyphen replacement — the readable form); the subtitle line carries the generation date, the analyzed source path, the Fit_Score, and the default recommendation. When `scoring.fit_score` is null, render `fit score: not computable`; when the recommendation is the parallel presentation, render `recommendation: both strategies presented`.

**§1 Analysis summary** — the detected tech stack from `tech_stack`: every detected language (with the primary-language selection and its rationale when several were detected), every framework, every runtime (with version and EOL status), every application server. Every determination carries its evidence (file path + matching detail), exactly as the tech stack detection module reported it.

**§1.5 Incomplete analysis items** — include this section **exactly when** the analysis is incomplete: `analysis.partial` is true, **or** at least one item was reported undetermined — `tech_stack.undetermined_items` non-empty, `scoring.excluded_dimensions` non-empty, or any blocker carrying `class_unconfirmed: true`. Place it **immediately after §1**, before §2. For each incomplete item, state three things:

1. **what** is incomplete — the undetermined item, or the excluded path/directory range;
2. **why** — the missing evidence, or the read failure reason;
3. **the impact on the results** — including, where it applies, exclusion of a Scoring_Dimension from the Fit_Score computation, the weight renormalization, and the reduced-confidence note on the recommendation.

When the analysis is fully complete, omit §1.5 entirely.

**§2 Blocker list** — every blocker from `blockers`: id, category (with the category rationale for `other`), remediation class (flagging `class_unconfirmed` entries as not settled by evidence), evidence paths, and the reason it obstructs. When the list is empty, do not leave the section thin or omit it — carry the **explicit zero-blocker statement** ("no blockers were detected") from the blocker detection module. Credential values never appear in any form (see cross-cutting rules).

**§3 Fit_Score and breakdown** — the total Fit_Score; a per-dimension table of score, weight, normalized weight, and contribution; whether renormalization occurred and which dimensions were excluded (mirroring `scoring`). When `fit_score` is null, state that the score could not be computed and carry the per-dimension reasons — never render a fabricated number.

**§4 Recommended strategy and grounds** — the default recommendation (or the parallel presentation with its decision-factor table), together with **all** the grounds from `recommendation.grounds`: the Fit_Score, the applied thresholds (flagged when non-default; a rejected override is reported with its reason), **every** must_fix blocker by id — or the explicit statement that there are none — and the lowest-scoring dimension(s). When `low_confidence` is true, the reduced-confidence note and the excluded-dimension list appear here. When a constraint-adjusted recommendation exists, both labeled recommendations appear side by side (with the explicit agreement statement when they agree).

**§5 Replatform path details** — render the `replatform_path` block: the ECS on EC2 target statement, the static configuration (task count policy, capacity plan, kept/changed operational procedures), the three containerization policy items (base image, app-server bundling, config intake — with the generic-policy limitations when applicable), the local-write mappings or the explicit not-needed statement, the session handling (sticky sessions with their constraint), and the must-fix handling (addressed items with their minimal remediations; unresolved items named as user-resolution work). The Windows_Container_Path subsection follows the [placement rules](#windows_container_path-placement) below.

**§6 Rearchitect path details** — render the `rearchitect_path` block: all three compute-model candidates with their applicability judgments and grounds; the modernization items with evidence, effort tier, and AWS Transform applicability notes (recommendation only — execution belongs behind the Execution_Gate); the framework migration options (or the no-established-path note); the zero-item statement when `no_items` is true; and the **ecs-architect delegation statement** (`delegation_note`) — the section never appears without it, and no concrete design values (capacity strategy, sizing numbers, network design) appear.

**§7 Strategy comparison table** — both strategies always appear, regardless of the recommendation outcome, each with at least one advantage, at least one drawback, an effort classification on the three-tier scale defined in [rearchitect-path.md](rearchitect-path.md), the assumed target configuration (ECS on EC2 static for Replatform; the applicable candidates for Rearchitect), and — when the recommendation was the parallel presentation — the decision-factor mapping.

**§8 Next steps** — the recommended-order actions to proceed, and the named hand-off points: detailed target design to `ecs-architect`, Linux container path environment Terraform to `ecs-build` (with the structured input list), security hardening to `ecs-security`. When AWS Transform applies to any modernization or porting item, list adopting it as a next step — **as a recommendation only**; the Assessment_Phase never starts a transformation. When the migration source is VMware, AWS Transform for VMware (discovery, dependency mapping, wave planning) may be mentioned here, flagged as outside this skill's analysis scope. State that Migration_Execution requires the Execution_Gate: assessment completion plus the user's explicit approval of the strategy and target path.

> After Migration_Execution, the Execution_Log is appended to this report or saved as a referenced sibling file — those rules belong to [deploy-verify-handoff.md](deploy-verify-handoff.md), not here.

### Windows_Container_Path Placement

The `windows_container_path` block is rendered **inside §5 (Replatform path details)** — never as a top-level section, never inside §6:

- **`mode: option | variant`** (.NET Framework detected, path applicable) — render a subsection of §5 containing: the applicability judgment and its mode; **both** compute options (ECS on EC2 Windows instances AND Fargate Windows support, each with its Windows Server versions, licensing considerations, and feature constraints — including the features unavailable on Fargate Windows); the base image policy (or, when it is null, the named undetermined items that prevent it — the subsection still appears); the constraints; and the .NET porting alternative with its AWS Transform applicability note when `dotnet_port_alternative` is present.
- **`mode: not_applicable`** (.NET Framework detected, ruled out) — §5 carries the **judgment** ("Windows_Container_Path: not applicable") **and the grounding blockers** (`blocking_dependencies`, each a reported must-fix blocker id) instead of the option. The path is not presented as a choice.
- **`mode: null`** (.NET Framework not detected) — no Windows subsection is rendered. This does not violate the no-omission rule: the subsection is conditional content within §5, not one of the eight mandated sections.

---

## Cross-Cutting Content Rules

### No omitted sections — explicit absence

Every one of the eight mandated sections appears in every report, in order. When a section has no applicable findings or results, the section still appears and **states the absence explicitly** inside itself — never an empty heading, never a dropped section. The canonical examples:

| Section | Explicit-absence statement |
|---|---|
| §2 with zero blockers | "No blockers were detected." (the checked-and-found-none statement) |
| §3 with no computable score | "The Fit_Score could not be computed" + per-dimension reasons |
| §5 with zero must-fix blockers | Empty addressed/unresolved lists + the explicit absence statement |
| §5 with no local writes detected | The not-needed statement with its grounds (no writes detected) |
| §6 with zero modernization items | "The application can move to the Rearchitect path with zero modernization items." |

### Evidence citation per recommendation — same section

Every **recommendation item** in the report must include, **within the same section as the item itself**, at least one reference to the analysis results that ground it — at least one of:

1. a **detected file path** (evidence path from tech stack detection or blocker detection),
2. a **Scoring_Dimension score** (the dimension name and its value), or
3. an **applied threshold** (the threshold name and value in effect).

This applies to — at minimum — the recommended Migration_Strategy (or the parallel presentation) in §4, every Rearchitect modernization item in §6, every Replatform containerization policy item in §5, the Windows_Container_Path applicability judgment and base image policy, and the compute-candidate applicability judgments. A citation living in a different section does not satisfy the rule — the reader of any single section must see the grounding without jumping. The prerequisite modules attach evidence to every output entry precisely so this rule can be satisfied mechanically; a recommendation item arriving without evidence indicates an assembly error upstream, not license to publish without grounding.

### Credential non-disclosure

No part of any detected credential value — whole or partial — appears anywhere in the report. Blockers of category `hardcoded_credentials` are rendered with file path, category, and a value-free description only (naming the credential type is allowed). This is the all-phases invariant from SKILL.md; the report is where it is most easily violated, so audit for it explicitly (procedure step 5).

### Artifact examples: code blocks only, no IaC

When any section illustrates a containerization artifact (a Dockerfile sketch, a task-definition fragment), the illustration appears **only as a fenced code block inside the report** — never as a separate file on disk. **No IaC code** (Terraform, CloudFormation, CDK) appears anywhere in the report: Linux container path environment IaC is delegated to `ecs-build` by name (§8), and Windows_Environment_Terraform is generated only during Migration_Execution, behind the Execution_Gate.

---

## Output Schema

The primary output of this module **is the Modernization_Report file itself** — structured by the [Report Template](#report-template) above. Alongside the file, the module reports its generation state in conversation:

```yaml
report_generation:
  file:
    name: string                   # resolved file name (default rule or user-specified)
    directory: string              # resolved destination (outside the source tree)
    written: bool                  # true only when the write actually succeeded
  confirmations:
    external_destination: obtained | not_needed   # source-tree conflict confirmation
    overwrite: obtained | not_needed              # same-name file confirmation
  sections_rendered: [string]      # the eight mandated sections (+ "1.5" when included)
  fallback:
    triggered: bool                # true when the write failed
    error: {path: string, reason: string} | null  # the failed path and reason
```

**Reporting invariants:**

- `written: true` requires an actual successful write — never claim a save that did not happen.
- `sections_rendered` always contains all eight mandated sections in order; `"1.5"` appears exactly when the analysis was incomplete.
- `fallback.triggered: true` implies `written: false`, a non-null `error`, and the full report content presented in conversation.
- Exactly one file is ever written; `directory` never resolves to the source root or any path under it without the explicit user confirmation recorded in `confirmations`.

---

## Edge Cases

### File write fails

If writing the Modernization_Report fails for any reason (permissions, disk, invalid path, destination removed between confirmation and write):

- **Report the error** — the exact output path that failed and the failure reason.
- **Never claim the report was saved.** Not partially, not "probably".
- **Present the complete generated report content as conversational output** — the user gets the full report either way; only the persistence failed.
- Offer to retry to a different destination; a retry re-enters the destination rules (containment check, overwrite check).

### Default destination is inside the source tree

The CWD resolves to the source root or a descendant of it: do not write. State the phase invariant (the report lands outside the target source tree), and ask the user for an external destination. Suggest a sensible candidate (for example the source tree's parent directory), but do not write anywhere without the user settling the destination.

### User-specified destination is inside the source tree

Surface the conflict explicitly — the user's specified path versus the outside-the-source-tree invariant — and confirm an alternative destination. Never write into the source tree without the user's explicit confirmation, and never silently redirect the file to a different location the user did not choose.

### Same-name file exists

Ask before overwriting, presenting the existing file's path. A refusal or an ambiguous response is not confirmation: offer a different file name (suffix) or a different directory instead. Never overwrite silently — even when the existing file looks like an earlier run's report of the same application.

### Application name cannot be determined

`analysis.target.app_name` is null: fall back to the root directory name of the analyzed source path, then apply the same character replacement (whitespace and path separators to hyphens). The report title uses the same fallback name. Note in §1 that the application name was not declared in any build definition.

### Partial analysis or undetermined items

`analysis.partial: true`, or any undetermined item exists: include §1.5 immediately after §1 with every incomplete item, its reason, and its impact on the results — including Fit_Score exclusions and the renormalization they caused. The rest of the report renders the partial results as usual; §1.5 is where the incompleteness is consolidated, and the confidence notes in §4 point back to it.

### Fit_Score could not be computed

`scoring.fit_score` is null: the header renders `fit score: not computable`, §3 states the score could not be computed with per-dimension reasons, and §4 renders the parallel presentation with decision factors (per the recommendation module's no-score handling). No section is dropped.

### Report requested before the assessment is complete

Report generation's prerequisites are all five assessment modules (routing table module 6). If the user asks for the report while prerequisite modules have not run, do not fabricate the missing sections: resolve the prerequisites transitively per the SKILL.md routing rules — run the missing modules first, then generate. If a prerequisite module was aborted (for example its reference file could not be read), report that the assessment is incomplete and which module is missing; do not generate a report that silently omits a mandated section's underlying analysis.

### User asks for a different format or multiple files

The Modernization_Report is exactly one Markdown file — the Assessment_Phase writes nothing else. If the user asks for additional formats or a split report, explain the single-file invariant, deliver the Markdown report, and note that the user can convert or split the delivered file themselves.
