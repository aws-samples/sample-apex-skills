# Module: Scoring and Recommendation

> **Part of:** [ecs-modernize](../SKILL.md)
> **Purpose:** Compute the 0–100 Fit_Score from the Source_Analysis evidence using the scoring criteria defined in this file — the single source of truth for every evaluation item, classification, score band, and weight — and derive the migration-strategy recommendation from it
> **Prerequisites:** Tech Stack Detection ([tech-stack-detection.md](tech-stack-detection.md)) and Blocker Detection ([blocker-detection.md](blocker-detection.md)) — every dimension score is grounded in their outputs

This module is deliberately orchestrator-neutral: the scoring criteria (evaluation items, weights, legacy/modern classifications, the modernity ladder) and the strategy classification logic are expressed exclusively in strategy-level vocabulary — Replatform and Rearchitect. Target-platform vocabulary does not appear in this file at all; mapping a strategy onto concrete compute models belongs to the path modules. This file covers scoring criteria and recommendation rules only; tech stack detection and blocker detection are each defined in their own reference file.

**Single source of truth.** This file is the sole definition of the Fit_Score scoring criteria: the evaluation items of every Scoring_Dimension, the default weights summing to 100%, the legacy and modern classifications with their score bands, and the modernity ladder are defined here and nowhere else. SKILL.md requires the agent to read this file **before** performing any scoring, and every dimension score must be computed **exclusively** from the evaluation items and weights defined in this file — never from general knowledge, from SKILL.md itself, or from any other document. If a criterion seems missing, that is a gap to report, not a license to improvise one.

## Table of Contents

- [Inputs](#inputs)
- [Scoring Procedure](#scoring-procedure)
- [Scoring Criteria](#scoring-criteria)
  - [Dimensions and Default Weights](#dimensions-and-default-weights)
  - [1. State Management (`state_management`, 25%)](#1-state-management-state_management-25)
  - [2. OS and Host Dependency (`os_host_dependency`, 20%)](#2-os-and-host-dependency-os_host_dependency-20)
  - [3. Configuration Externalization (`config_externalization`, 15%)](#3-configuration-externalization-config_externalization-15)
  - [4. Framework and Runtime Modernity (`framework_modernity`, 15%)](#4-framework-and-runtime-modernity-framework_modernity-15)
  - [5. External Dependency Coupling (`dependency_coupling`, 15%)](#5-external-dependency-coupling-dependency_coupling-15)
  - [6. Build and Deploy Reproducibility (`build_reproducibility`, 10%)](#6-build-and-deploy-reproducibility-build_reproducibility-10)
- [Computation Rules](#computation-rules)
  - [Dimension Scores and Fit_Score](#dimension-scores-and-fit_score)
  - [Evidence Mapping](#evidence-mapping)
  - [Breakdown Reporting](#breakdown-reporting)
  - [Undeterminable Dimensions and Weight Renormalization](#undeterminable-dimensions-and-weight-renormalization)
  - [Worked Example](#worked-example)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Recommendation Rules](#recommendation-rules)
  - [Thresholds and Default Classification](#thresholds-and-default-classification)
  - [Threshold Overrides](#threshold-overrides)
  - [Grey Zone: Parallel Presentation with Decision Factors](#grey-zone-parallel-presentation-with-decision-factors)
  - [Always Present Both Strategies](#always-present-both-strategies)
  - [Recommendation Grounds](#recommendation-grounds)
  - [User Constraints: Default vs Constraint-Adjusted](#user-constraints-default-vs-constraint-adjusted)
  - [Confidence Notes](#confidence-notes)
  - [No-Score Handling](#no-score-handling)
  - [Strategy-to-Compute-Model Boundary](#strategy-to-compute-model-boundary)
  - [Recommendation Output Schema](#recommendation-output-schema)
- [Sources](#sources)

---

## Inputs

- **`tech_stack` block** (required) — the output of tech stack detection: languages, frameworks with their classification families, runtimes with version and `eol` status, application servers, and undetermined items.
- **`blockers` block** (required) — the output of blocker detection: every blocker with category, remediation class, evidence paths, and reason; or the explicit zero-blocker statement.
- **`analysis` envelope** (required) — target identity and the partial-analysis state (`partial`, `excluded_paths`), which propagates into confidence reporting.
- **Read-only discipline** — scoring is a pure computation over the Source_Analysis outputs. It reads no additional files, executes no commands, and writes nothing; the results are held in conversation context for the recommendation and report modules.

Do not run this module before both prerequisite modules have produced their outputs. Scoring performed on a partial evidence base without those outputs is not a valid Fit_Score.

---

## Scoring Procedure

Run the steps in this order:

```
0. Confirm this file has been read in full        -> SKILL.md mandate; criteria below are the only basis
1. Verify prerequisite outputs are present         -> tech_stack + blockers + analysis envelope
2. Score each dimension against its evaluation items
   (any order), attaching >= 1 evidence entry each
3. Mark undeterminable dimensions                  -> record exactly what evidence is missing
4. Renormalize weights over determinable dimensions
5. Compute Fit_Score                               -> rounded weighted mean of determinable dimensions
6. Assemble the breakdown                          -> score, weight, normalized weight, contribution;
                                                      verify contributions sum to Fit_Score within +/- 1
7. Hand off to the recommendation rules
```

**Why this order:**

- Step 0 exists because this file is the single source of truth (see above): scoring from memory of "typical" criteria instead of the criteria actually written here is the exact drift this rule prevents.
- Step 1 gates everything: every evaluation item below is phrased in terms of the prerequisite modules' findings, so without them there is nothing legitimate to score.
- Undeterminable marking (step 3) precedes renormalization (step 4) because the renormalized weights are defined over the set of determinable dimensions only.
- The breakdown check (step 6) is a self-verification: if the contributions do not sum to the reported Fit_Score within ±1, the arithmetic is wrong — fix it before reporting anything.

---

## Scoring Criteria

### Dimensions and Default Weights

Fit_Score is composed of exactly these six Scoring_Dimensions. The default weights sum to 100%.

| # | Dimension | Schema name | Weight | What it evaluates |
|---|---|---|---|---|
| 1 | State management (statelessness) | `state_management` | **25%** | Local state and in-process sessions — whether instances can be replaced and scaled horizontally without losing authoritative data |
| 2 | OS and host dependency | `os_host_dependency` | **20%** | OS-specific APIs, application-server coupling, process model — whether the application can cross the container boundary |
| 3 | Configuration externalization | `config_externalization` | **15%** | Degree to which connection info and environment-specific values are hardcoded into the artifact |
| 4 | Framework and runtime modernity | `framework_modernity` | **15%** | Position on the modernity ladder, governed by the legacy (cap 40) and modern (floor 60) classifications below |
| 5 | External dependency coupling | `dependency_coupling` | **15%** | How databases, messaging, and external services are integrated — abstraction and protocol standardization |
| 6 | Build and deploy reproducibility | `build_reproducibility` | **10%** | Completeness of build definitions and the degree of dependence on manual deployment procedures |

**Weight rationale.** What most decides the Replatform / Rearchitect split is *whether the unchanged application runs in a container at all* (state management + OS/host dependency = 45%), then *whether it fits cloud-native operations* (configuration externalization + dependency coupling = 30%), and finally *how healthy the starting point for remediation is* (modernity + build reproducibility = 25%).

Each dimension below defines its evaluation items, the evidence it consumes, and scoring anchors. Anchors are bands, not lookup tables: position the score inside a band using the scope and severity of the actual findings, and justify the position with the attached evidence.

### 1. State Management (`state_management`, 25%)

**Evaluation items:**

- Local filesystem **state** writes — business data persisted to the local filesystem (blocker category `local_state`)
- In-process session state held as the authoritative copy (blocker category `in_process_session`)
- Authoritative in-memory state (static/singleton stores keyed by user or entity)
- Positive evidence of externalized state — external session store dependencies (e.g. a session-management library backed by an external store), all persistence going through external data stores

**Evidence inputs:** `blockers` entries of the two state categories (or the explicit zero-blocker statement together with the artifacts examined), plus `tech_stack` evidence of external state stores in build definitions and configuration.

**Scoring anchors:**

| Band | Condition |
|---|---|
| 90–100 | No state-category blockers, **and** externalization positively evidenced (external session store configured, persistence exclusively via external stores) |
| 60–89 | No state-category blockers, but externalization only partially evidenced; or local writes confirmed to be regenerable caches only |
| 30–59 | Exactly one of the two state blocker categories present, with bounded scope (identified write targets or session usage in a contained area) |
| 0–29 | Both state blocker categories present, or authoritative in-memory state pervasive across the codebase |

### 2. OS and Host Dependency (`os_host_dependency`, 20%)

**Evaluation items:**

- OS-specific API usage — registry, OS service plumbing, COM interop, P/Invoke, JNI with platform-specific native libraries (blocker category `os_specific_api`)
- Container-incompatible process models — host-supervised multi-process arrangements, host scheduler dependence (blocker category `process_model`)
- Application-server coupling — vendor-specific deployment descriptors versus standard containers (`tech_stack.app_servers`). Coupling has two depths, and the deeper one scores lower: **descriptor-level** coupling (vendor binding/extension descriptors only — e.g. `ibm-web-bnd.xml`, `weblogic.xml`) is remediable by descriptor rework, while **code-level** coupling (proprietary server APIs in application code — e.g. `com.ibm.websphere.*` / `com.ibm.wsspi.*`, CommonJ WorkManager, `weblogic.*`) binds the application logic itself to the vendor server and travels with the code wherever it goes
- Hardcoded OS-specific filesystem paths

**Evidence inputs:** `blockers` entries of `os_specific_api` and `process_model` with their remediation classes, and `tech_stack.app_servers`.

**Scoring anchors:**

| Band | Condition |
|---|---|
| 90–100 | No OS-specific API or process-model findings; no vendor-specific application-server coupling |
| 60–89 | Standard application-server hosting only (servlet container, standard web-server hosting) with no OS-specific API findings |
| 30–59 | OS-specific API or process-model findings present, but all carry remediation class `replatform_ok` (they function inside a container of the matching OS); **or** vendor application-server coupling with no `must_fix` findings — position descriptor-level coupling near the top of the band and code-level proprietary-API coupling (e.g. `com.ibm.websphere.*` usage across the codebase) near the bottom, since the code-level dependence must be unwound before the app can leave the vendor server |
| 0–29 | One or more `must_fix` findings in these categories (interactive desktop UI, hardware drivers, kernel-mode components, host-managed daemon arrangements) |

### 3. Configuration Externalization (`config_externalization`, 15%)

**Evaluation items:**

- Hardcoded connection endpoints and credentials (blocker category `hardcoded_credentials`)
- Environment-specific values baked into the deployable artifact (hosts, paths, feature toggles fixed at build time)
- Positive evidence of environment-driven configuration (environment variables, externalized configuration files, per-environment overrides that keep the artifact environment-agnostic)

**Evidence inputs:** `blockers` entries of `hardcoded_credentials`, and the configuration artifacts recorded during Source_Analysis. Credential secrecy rules from blocker detection carry through: no part of a credential value ever appears in scoring evidence.

**Scoring anchors:**

| Band | Condition |
|---|---|
| 90–100 | No hardcoded endpoint/credential findings; environment-driven configuration positively evidenced |
| 60–89 | Environment-specific values present but cleanly separable (per-environment configuration files, no secrets among them) |
| 30–59 | Hardcoded endpoints or credentials present in committed configuration files |
| 0–29 | Secrets embedded in source code, or environment-specific configuration entangled with code such that the same build cannot move across environments |

### 4. Framework and Runtime Modernity (`framework_modernity`, 15%)

This dimension is governed by three definitions — the legacy classification, the modern classification, and the modernity ladder — all defined here and only here.

**Legacy classification** (score **cap 40** — the dimension score never exceeds 40 when the governing determination target falls in this classification):

- Struts (Struts 1 and Struts 2)
- .NET Framework (4.x and earlier)
- ASP.NET Web Forms
- WCF
- Language runtime versions whose provider support has ended (EOL) at analysis time (`eol: true` from tech stack detection)

**Modern classification** (score **floor 60** — the dimension score is at least 60 when the governing determination target falls in this classification):

- Spring Boot on a provider-supported version line
- ASP.NET Core
- .NET (Core / 5 and later) on a provider-supported version

Note the qualifier in the first and third entries: **support status is part of the classification, not a footnote to it.** A framework line whose provider support has ended is in the *legacy* classification by the EOL entry above, however modern its family looks — so an EOL Spring Boot line does not reach the modern floor even though "Spring Boot" appears here.

The legacy cap (40) is strictly below the modern floor (60); the interval 41–59 belongs to classifications that are neither legacy nor modern.

**Modernity ladder** (most modern first) with the score band of each tier:

| Tier | Classifications | Score band |
|---|---|---|
| 1 (most modern) | ASP.NET Core; Spring Boot 3.x — on supported lines | 80–100 |
| 2 | Spring Boot 2.x; .NET 6–8 — **only while the line is provider-supported** | 60–79 |
| 3 | Spring Framework (non-Boot); ASP.NET MVC; Jakarta EE / Java EE | 41–59 |
| 4 (legacy) | Struts; ASP.NET Web Forms; WCF; .NET Framework; **any EOL framework or runtime line, whatever tier its family would otherwise sit in** | 0–40 |

Tiers 1–2 sit at or above the modern floor; tier 4 sits at or below the legacy cap; tier 3 occupies the interval between them. Within a tier, position the score by version currency and support status (a framework on its newest supported line scores near the top of its band; an aging line near the bottom).

**EOL beats the tier — check support status before banding.** Tier 2 in particular lists lines that have since gone end of life: Spring Boot 2.x left OSS support in November 2023, and .NET 6 and 7 are both past their end of support. An EOL line belongs to the legacy classification (see the EOL entry above) and is therefore **capped at 40**, whichever tier its family appears in here. The runtime-constraint rule below catches this when the *runtime* is EOL; this note is what catches it when the **framework line** is EOL on a still-supported runtime — an EOL Spring Boot 2.x application on Java 17 is the case that would otherwise slip through at 60–79. Verify the support status of the detected line at analysis time rather than reading the tier off this table, and record the support fact in the dimension's evidence.

**Scoring rules:**

1. **Governing classification = the most modern detected.** When multiple frameworks are detected — including when legacy and modern classifications coexist — the dimension score is computed from the score band of the **most modern** classification on the ladder, never from the band of a lower tier. Every coexisting framework detection (including the legacy ones not used for the band) **must** be recorded in this dimension's evidence, so the coexistence is visible in the breakdown.
2. **Runtime constraint.** The runtime targeted by the deployable application participates in the determination: if the governing runtime (the most modern runtime actually targeted by the deployable application, with coexistence recorded as evidence when runtimes are mixed) is in the legacy classification — EOL, or .NET Framework — the legacy cap applies to the dimension regardless of framework tier. The modern floor applies only when both the governing framework classification is modern **and** the governing runtime is provider-supported.
3. **Stacks not named on the ladder** (other languages, frameworks outside the listed families, "no framework (plain Java)") — see [Edge Cases](#stack-not-named-on-the-ladder).

**Evidence inputs:** `tech_stack.frameworks` (classification families and evidence), `tech_stack.runtimes` (version, `eol` flag, evidence). The ladder maps the classification *families* reported by tech stack detection; tech stack detection collects facts, this file alone ranks them.

### 5. External Dependency Coupling (`dependency_coupling`, 15%)

**Evaluation items:**

- Integration style with databases, messaging systems, and external services — abstraction layers (data-access layers, standard driver interfaces) versus direct proprietary coupling
- Protocol standardization — standard network protocols versus proprietary or host-local mechanisms
- Repointability — whether an external dependency can be redirected by configuration alone
- Licensing-constrained components binding execution to specific hosts (blocker category `licensing`)

**Evidence inputs:** dependency declarations in build definitions, connection configuration, `blockers` entries of `licensing` and any `other`-category coupling findings.

**Scoring anchors:**

| Band | Condition |
|---|---|
| 90–100 | All external integrations via standard protocols behind abstraction layers; endpoints repointable by configuration |
| 60–89 | Standard protocols, but endpoint or vendor specifics leak into code (repointing requires small code changes) |
| 30–59 | Proprietary protocols or vendor-specific integrations requiring code change to repoint |
| 0–29 | Host-local IPC to co-located systems, hardware-bound integrations, or licensing-constrained components that pin execution to specific hosts |

### 6. Build and Deploy Reproducibility (`build_reproducibility`, 10%)

**Evaluation items:**

- Build definition completeness — can the deployable artifact be produced from the tree with the declared toolchain alone
- Dependency declaration completeness — declared, resolvable dependencies versus unmanaged binaries checked into the tree
- Deployment automation — scripted, repeatable deployment versus documented (or undocumented) manual host procedures

**Evidence inputs:** `tech_stack` build-definition inventory and version declarations, deployment scripts and descriptors found during Source_Analysis. Note: this is judged from static evidence only — no build is ever executed to "verify" reproducibility.

**Scoring anchors:**

| Band | Condition |
|---|---|
| 90–100 | Complete build definition; all dependencies declared and resolvable; deployment fully scripted |
| 60–89 | Complete build definition; minor unmanaged dependencies or partially documented deployment steps |
| 30–59 | Incomplete build definitions (unmanaged libraries in the tree) or deployment relying on documented manual steps |
| 0–29 | No build definition, or deployment dependent on undocumented manual host configuration |

---

## Computation Rules

### Dimension Scores and Fit_Score

- Every determinable dimension receives an **integer score from 0 to 100**, positioned per its anchors above.
- **Fit_Score = the weighted mean of the determinable dimensions' scores, rounded to the nearest integer** (halves round up). Weights are the normalized weights (see renormalization below); when all six dimensions are determinable, the normalized weights equal the default weights.
- Fit_Score is therefore always an integer in 0–100. It is computed only when Source_Analysis has completed and at least one dimension is determinable.

### Evidence Mapping

Every determinable dimension's score carries **at least one** concrete evidence entry: a file path from Source_Analysis, or a finding reference that uniquely identifies a detection (e.g. a blocker ID such as `BLK-003`, or a named `tech_stack` entry). Two disciplines:

- **High scores need positive evidence too.** A 90+ on state management is grounded in the explicit zero-blocker statement *plus* the artifacts examined, or in positive externalization evidence — never in mere silence.
- **Evidence stays attached even in partial analyses.** Dimensions that are determinable keep their full evidence regardless of other dimensions being undetermined.

A dimension score without evidence is not a determination — treat it as undetermined instead.

### Breakdown Reporting

Whenever Fit_Score is reported, report the per-dimension breakdown alongside it. For every determinable dimension:

- the individual **score** (integer 0–100),
- the applied **weight** (default) and **normalized weight** (post-renormalization; equal to the default when nothing was excluded),
- the **contribution** = score × normalized weight (normalized weight as a fraction).

The sum of the contributions must equal the reported Fit_Score within the rounding tolerance of **±1**. If it does not, the computation is wrong — recompute before reporting.

### Undeterminable Dimensions and Weight Renormalization

- If the evidence needed to score a dimension is absent from the Source_Analysis outputs, report that dimension as **undetermined** and state explicitly **which evidence is missing** (what would be needed to settle it). Never substitute a neutral-looking default score for missing evidence.
- Undetermined dimensions are **excluded** from the Fit_Score computation. The weights of the remaining determinable dimensions are **renormalized to sum to 100% while preserving their original ratios**: `normalized_weight_i = weight_i / Σ(weights of determinable dimensions)`.
- The Fit_Score report must state the **list of excluded dimensions** and the fact that the score was **computed under renormalization** — this is what flags the reduced confidence downstream.
- If **all** dimensions are undetermined, report **no numeric Fit_Score** at all (`fit_score: null`). Report that the score could not be computed, together with the per-dimension reason each one was undetermined. Never emit a number synthesized without evidence.

### Worked Example

Suppose `config_externalization` is undetermined (no configuration artifacts were readable) and the other five score: state 80, OS/host 70, modernity 90, coupling 60, build 50.

| Dimension | Score | Weight | Normalized weight | Contribution |
|---|---|---|---|---|
| state_management | 80 | 25% | 25/85 ≈ 0.2941 | 23.53 |
| os_host_dependency | 70 | 20% | 20/85 ≈ 0.2353 | 16.47 |
| framework_modernity | 90 | 15% | 15/85 ≈ 0.1765 | 15.88 |
| dependency_coupling | 60 | 15% | 15/85 ≈ 0.1765 | 10.59 |
| build_reproducibility | 50 | 10% | 10/85 ≈ 0.1176 | 5.88 |
| config_externalization | undetermined | (15%) | excluded | — |

Sum of contributions = 72.35 → **Fit_Score = 72** (contributions sum within ±1 ✓). The report lists `config_externalization` as excluded and states the score was computed under renormalization.

---

## Output Schema

This module produces the `scoring` block. Hold the structure in conversation context — the assessment phase writes no intermediate files. (The `recommendation` block is defined under [Recommendation Rules](#recommendation-rules).)

```yaml
scoring:
  dimensions:
    - name: state_management | config_externalization | os_host_dependency |
            framework_modernity | build_reproducibility | dependency_coupling
      score: int (0-100) | undetermined
      weight: float                # default weight from the table above
      normalized_weight: float     # post-renormalization; equals weight when nothing excluded
      contribution: float          # score x normalized_weight (fraction)
      evidence: [{path_or_finding: string}]   # >= 1 entry for every determinable dimension
      insufficient_evidence: string | null    # required when score == undetermined:
                                              # exactly what evidence is missing
  excluded_dimensions: [string]    # names of dimensions excluded as undetermined
  renormalized: bool               # true when any dimension was excluded
  fit_score: int (0-100) | null    # null when all dimensions are undetermined
```

**Reporting invariants:**

- All six dimensions appear in `dimensions` — determinable ones with score + evidence, undetermined ones with `insufficient_evidence`.
- `excluded_dimensions` lists exactly the dimensions whose `score` is `undetermined`; `renormalized` is `true` iff that list is non-empty.
- `fit_score` is an integer in 0–100 whenever at least one dimension is determinable, and `null` otherwise.
- Σ contributions of determinable dimensions = `fit_score` ± 1.
- No evidence entry contains any part of a credential value (secrecy rules carry through from blocker detection).

---

## Edge Cases

### A dimension has no evidence either way

Absence of findings is not automatically a high score, and not automatically undetermined either. Distinguish:

- **Checked and found none** — the prerequisite modules examined the relevant artifacts and reported no findings (e.g. the explicit zero-blocker statement): the dimension is determinable, scored per its anchors, with the examined artifacts as evidence.
- **Could not check** — the relevant artifacts were unreadable or absent from the analysis (e.g. no configuration files readable for `config_externalization`): the dimension is **undetermined**, with the missing evidence named.

### All dimensions undetermined

Report no numeric Fit_Score (`fit_score: null`), report per-dimension reasons, and hand off to the recommendation rules' no-score handling. Do not average nothing into something.

### Compiled artifacts only — no readable source

When the target path is readable but contains **no readable source code and no build definition** (only packaged or compiled artifacts — WAR/JAR/DLL/EXE), **every** dimension is `undetermined` and `fit_score` is `null`. This is stated explicitly because one dimension invites the opposite reading: `build_reproducibility`'s 0–29 band begins "No build definition", which looks satisfied here. It is not. That band describes a **readable source tree in which no build definition was found** — a determinable "checked and found none". With only artifacts there is no tree to check, so the honest state is "could not check", and a score of ~10 would be a fabricated determination dressed as a finding.

What to report instead: the artifact inventory that *was* observed (file names and types are evidence of the stack, and tech stack detection may legitimately determine a language or framework from them), and what would settle the scoring — the source repository, or an artifact-level inventory tool. The recommendation follows the no-score handling: both strategies in parallel with decision factors, and no score-based pick.

### Partial analysis (`analysis.partial: true`)

Score the determinable dimensions on the readable evidence as usual, but remember the exclusions: a dimension whose decisive artifacts fall inside the excluded ranges is undetermined (missing evidence = the excluded paths). The partial-analysis state also propagates into the recommendation's confidence reporting and the report's incomplete-analysis section.

### Coexisting frameworks

Never resolve coexistence by averaging or by picking the most prevalent framework: the most modern classification on the ladder governs the band (scoring rule 1), and every coexisting detection is recorded in the dimension's evidence. Example: Struts and Spring Boot 3.x in one tree → band 80–100 governs, with the Struts detection (path evidence) explicitly listed in the same dimension's evidence.

### Mixed runtimes

A repository whose deployable projects target both a legacy runtime and a modern runtime (e.g. a solution mixing .NET Framework 4.8 and .NET 8 projects): the most modern runtime actually targeted by the deployable application governs, and the coexistence is recorded as evidence. If which project is the deployable application cannot be settled, the governing runtime is undetermined — apply the fail-safe below.

### Undetermined EOL status

`eol: undetermined` from tech stack detection neither triggers the legacy cap nor supports the modern floor. If the modernity determination cannot be settled at all (framework family and runtime status both undetermined), report `framework_modernity` as undetermined with the missing information named — do not guess a tier.

### Stack not named on the ladder

For languages and frameworks outside the ladder's listed families (other-language stacks, unlisted frameworks, "no framework (plain Java)"):

- An **EOL runtime** places the stack in the legacy classification — the cap (40) applies. This is by definition, not analogy: EOL runtimes are an explicit member of the legacy classification.
- Otherwise, position the stack by analogy to the ladder using runtime support status and framework maintenance status: an actively maintained framework on a fully supported runtime behaves like tier 2; an unmaintained-but-not-EOL stack behaves like tier 3. State the analogy used in the evidence so the banding is auditable.
- If no analogy can be grounded in evidence, the dimension is undetermined.

### Conflicting evidence between dimensions

The same finding may legitimately feed several dimensions (a hardcoded connection string is `config_externalization` evidence; its licensing-constrained driver is `dependency_coupling` evidence). That is not double-counting — the dimensions evaluate different questions. What is prohibited is citing a finding as evidence for a score it does not support.

---

## Recommendation Rules

The rules below are the second half of this module: they turn the `scoring` block into the `recommendation` block, running immediately after scoring completes (step 7 of the scoring procedure). Their inputs are the `scoring` block, the `blockers` block (for the must-fix grounds), and any user-stated constraints or threshold overrides. Like the scoring criteria, these rules are expressed exclusively in strategy vocabulary — Replatform and Rearchitect — see the [boundary rule](#strategy-to-compute-model-boundary) at the end.

### Thresholds and Default Classification

Two thresholds partition the Fit_Score range:

- **Rearchitect_Threshold** — default **70**
- **Replatform_Threshold** — default **40**

```
Fit_Score:  0 ─────────── 40 ──────────────── 70 ─────────── 100
            │  Replatform  │     grey zone     │  Rearchitect  │
            │  recommended │ (parallel, no     │  recommended  │
            │              │  single pick)     │               │
                           ↑ 40 belongs to the  ↑ 70 belongs to
                             grey zone            Rearchitect
```

The default recommendation is exactly one of three outcomes:

| Condition | Default recommendation |
|---|---|
| Fit_Score ≥ Rearchitect_Threshold — equality **included** | **Rearchitect** |
| Replatform_Threshold ≤ Fit_Score < Rearchitect_Threshold — lower-bound equality **included** | **No single strategy** — parallel presentation with decision factors (below) |
| Fit_Score < Replatform_Threshold | **Replatform** |

For any integer Fit_Score 0–100 under a valid threshold pair, exactly one row applies. The boundary assignments are deliberate and must not drift: a Fit_Score equal to Rearchitect_Threshold is a Rearchitect recommendation; a Fit_Score equal to Replatform_Threshold is in the grey zone.

### Threshold Overrides

Both thresholds may be overridden when the user explicitly requests it. **Validation rule:** an override pair is valid if and only if both values are integers within 0–100 **and** Replatform_Threshold < Rearchitect_Threshold (strictly).

- **Valid override** — apply the overridden values to the classification above and report that the applied values are not the defaults.
- **Invalid override** (either value outside 0–100, or Replatform_Threshold ≥ Rearchitect_Threshold) — **reject the override, apply the defaults (70/40), and report the reason for rejection**. Record the rejected values and reason in `recommendation.thresholds.rejected_override`.

Overrides change only the classification boundaries — never the Fit_Score itself.

### Grey Zone: Parallel Presentation with Decision Factors

When the Fit_Score falls in the grey zone, do **not** settle on a single strategy. Present both strategies in parallel, and map **at least** the following decision factors to the strategy each favors, with a rationale grounded in this analysis's findings:

| Decision factor | Favors Rearchitect when... | Favors Replatform when... |
|---|---|---|
| Remediation effort tolerance | The organization can absorb code-change work (budget, staffing) | Little to no capacity for application code changes |
| Migration deadline | The timeline accommodates remediation before migration | A hard near-term deadline leaves no room for remediation |
| Team container proficiency | The team is comfortable operating container-native workloads | Container experience is limited; minimizing operational novelty matters |

Additional factors surfaced by the analysis (e.g. a heavy must-fix blocker load pushing effort up) may be appended, but the three above always appear. Every factor entry carries `favors` (which strategy) and `rationale`.

### Always Present Both Strategies

Regardless of where the Fit_Score lands — firm Rearchitect, firm Replatform, grey zone, or no score at all — the Modernization_Report **always** records both strategies, each with:

- at least **one advantage**,
- at least **one drawback**, and
- an **effort classification** on the three-tier scale (small / medium / large) as defined in [rearchitect-path.md](rearchitect-path.md) — small = localized configuration/code changes, medium = cross-cutting but mechanical changes, large = architecture/framework-level changes. Use that module's criteria as-is; this file does not define a competing scale.

A recommendation is a weighting of the two options, never the suppression of one.

### Recommendation Grounds

Whenever a recommendation is reported — including the parallel presentation — report all of the following as its grounds:

1. the **Fit_Score**,
2. the **applied thresholds** (the defaults, or the overridden values flagged as non-default),
3. **every** blocker whose remediation class is `must_fix` (the ones that must be resolved even under Replatform) — list all IDs; when there are none, **state the absence explicitly** (an empty list plus the statement, never silence),
4. the **lowest-scoring Scoring_Dimension** — at least one; when several tie for lowest, list all tied dimensions.

### User Constraints: Default vs Constraint-Adjusted

When the user has explicitly stated constraints (remediation effort limits, deadlines, team skills, etc.), report **two labeled recommendations, distinctly marked**:

- **Default recommendation (score-based)** — derived from the thresholds alone, as above.
- **Constraint-adjusted recommendation** — the recommendation after weighing the stated constraint.

When the two agree, **state the agreement explicitly** — do not collapse them into a single unlabeled recommendation. The constraint-adjusted recommendation never silently replaces the default; both labels always appear side by side.

### Confidence Notes

If the Fit_Score was computed under weight renormalization (one or more dimensions excluded as undetermined — `scoring.renormalized: true`), attach to the recommendation (including the parallel presentation):

- a note that the recommendation's **confidence is reduced**, and
- the **list of excluded dimension names**.

### No-Score Handling

If the Fit_Score could not be computed at all (every dimension undetermined — `fit_score: null`):

- make **no score-based recommendation**,
- present **both strategies in parallel with the decision factors** exactly as in the grey zone, and
- state explicitly that the Fit_Score could not be computed, carrying the per-dimension reasons from the scoring output.

### Strategy-to-Compute-Model Boundary

The scoring criteria and the strategy classification logic in this file are expressed **exclusively** in strategy-level vocabulary — **Replatform** and **Rearchitect**. Target-platform compute-model vocabulary does not appear anywhere in this file, by design. Mapping a chosen strategy onto the concrete compute models of the target platform is performed **only by the path modules** — [replatform-path.md](replatform-path.md) and [rearchitect-path.md](rearchitect-path.md). This module hands them a strategy classification and nothing more; the separation keeps the scoring and recommendation knowledge portable across orchestrators.

### Recommendation Output Schema

This module produces the `recommendation` block alongside the `scoring` block. Hold it in conversation context — the assessment phase writes no intermediate files.

```yaml
recommendation:
  thresholds:
    rearchitect: int               # default 70
    replatform: int                # default 40
    overridden: bool               # true when user-supplied values were applied
    rejected_override: {values: string, reason: string} | null
                                   # non-null when an invalid override was rejected
  default_recommendation: rearchitect | replatform | parallel
                                   # parallel = grey zone, or no-score handling
  decision_factors:                # required whenever default_recommendation == parallel
    - {factor: string, favors: rearchitect | replatform, rationale: string}
  constraint_adjusted: {constraint: string, recommendation: string} | null
                                   # non-null iff the user stated constraints
  low_confidence: bool             # true when scoring.renormalized == true
  grounds:
    fit_score: int | null          # null when the score could not be computed
    must_fix_blockers: [string]    # ALL must_fix blocker ids; empty list = explicit absence stated
    lowest_dimension: string       # lowest-scoring dimension (>= 1; ties list all)
```

**Reporting invariants:**

- `default_recommendation` takes exactly one of the three values, determined by the threshold table; it is `parallel` whenever `grounds.fit_score` is `null`.
- `decision_factors` is non-empty whenever `default_recommendation` is `parallel`, and always includes the three named factors (effort tolerance, deadline, container proficiency).
- `constraint_adjusted` is non-null exactly when the user stated constraints; when its recommendation equals the default, the explicit agreement statement accompanies it.
- `low_confidence` equals `scoring.renormalized`; when `true`, the excluded-dimension list accompanies the recommendation.
- `grounds.must_fix_blockers` lists every `must_fix` blocker without exception; an empty list is always paired with the explicit absence statement.
- The report shown to the user always contains both strategies with advantages, drawbacks, and effort classifications, regardless of `default_recommendation`.

---

## Sources

- The Twelve-Factor App — processes, config, backing services (the principles behind the state management, configuration externalization, and dependency coupling dimensions): https://12factor.net/processes , https://12factor.net/config , https://12factor.net/backing-services
- .NET and .NET Framework support lifecycles (EOL and supported-version checks): https://learn.microsoft.com/en-us/lifecycle/products/
- .NET releases and support policy (.NET Core / 5+ version lines): https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core
- Java SE support roadmap (EOL checks): https://www.oracle.com/java/technologies/java-se-support-roadmap.html
- Spring Boot support timeline (2.x / 3.x version lines): https://spring.io/projects/spring-boot#support
- Apache Struts 1 end of life announcement: https://struts.apache.org/struts1eol-announcement.html
- ASP.NET official support policy (Web Forms / MVC on .NET Framework): https://dotnet.microsoft.com/en-us/platform/support/policy/aspnet
