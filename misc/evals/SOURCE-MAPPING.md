# Eval Framework v2 — Source Mapping & Best-Practice Validation

**Phase:** 4.5
**Date:** 2026-06-03
**Status:** Complete

## Purpose

Map each eval layer (Phases 1–4) to the research sources it draws from, deep-dive our implementation against those sources, and document gaps with priority.

---

## Layer-to-Source Matrix

| Layer | Primary Sources | Secondary Sources |
|-------|----------------|-------------------|
| **Phase 1 (Process)** | tau-bench (fault classification), MINT (per-turn marginal gain), Promptfoo (trajectory assertions) | DeepEval (tool correctness), Inspect AI (solver/scorer separation) |
| **Phase 2 (Artifact)** | Conftest/OPA (policy-as-code), SWE-bench (binary pass/fail), WebArena (environment state) | AgentBench (multi-env scoring), Terratest (apply/destroy) |
| **Phase 3 (Knowledge)** | Agent-as-a-Judge (hierarchical requirements) | DeepEval (faithfulness), Promptfoo (contains/regex) |
| **Phase 4 (Regression)** | tau-bench (pass^k), Braintrust (snapshots + CI gates) | Langfuse (versioned baselines), Phoenix (experiment tracking) |

---

## Phase 1 — Process Assertions

### Source Alignment

| Source | Alignment | Gap |
|--------|-----------|-----|
| tau-bench | Strong — failure taxonomy covers 4/5 modes | Missing `premature_termination` class |
| MINT | Partial — `tool-effectiveness` uses output-diff heuristic, not goal-state advancement | Could add optional `progress_indicators` |
| Promptfoo | Strong — superset of their trajectory types | No standalone `tool-args-match` (ours is nested under `tool-called`) |
| DeepEval | Partial — binary arg matching, not per-call scoring | Missing `tool-args-schema` (JSON Schema validation of tool inputs) |
| Inspect AI | Strong — Trajectory dataclass is clean contract boundary | No gap |

### Gaps to Close

| # | Gap | Effort | Priority | Rationale |
|---|-----|--------|----------|-----------|
| P1-1 | Add `tool-args-schema` assertion type (validate tool args against JSON Schema) | ~30 LOC | **P0** | Closes DeepEval granularity gap; catches arg regressions without LLM |
| P1-2 | Add `progress_indicators` optional field to `tool-effectiveness` | ~15 LOC | **P1** | Partial MINT semantics; regex patterns in tool results that count as progress |
| P1-3 | Add `premature_termination` failure class when step-count < min and no final output | ~5 LOC | **P1** | Closes tau-bench coverage gap |

### What We Do Well

- `no-tool-called` (negative assertion) has no Promptfoo/DeepEval equivalent
- Failure taxonomy with `failure_class` enables triage — DeepEval only gives scores
- Elicitation/scorer separation matches Inspect AI without requiring base class adapters
- Subprocess-based elicitation means any CLI tool can be the subject

---

## Phase 2 — Artifact Validation

### Source Alignment

| Source | Alignment | Gap |
|--------|-----------|-----|
| Conftest/OPA | Low — we use regex, not parsed HCL/YAML queries | `hcl-resource-exists` is regex-based, can't check attributes |
| SWE-bench | Partial — static analysis only, no `terraform plan` | Plan-level semantic errors missed |
| Terratest | Conscious gap — no apply/destroy (cost, credentials, speed) | Correct scope decision |
| AgentBench | N/A — text file artifacts don't need multi-env scoring | Skip-on-missing handles portability |
| WebArena | Minimal — our "environment state" IS the file tree | Correct for IaC artifacts |

### Gaps to Close

| # | Gap | Effort | Priority | Rationale |
|---|-----|--------|----------|-----------|
| P2-1 | Add `hcl-attribute-check` assertion (parse HCL, query attributes) | ~60 LOC + `python-hcl2` dep | **P0** | Closes Conftest gap; enables "every eks_cluster has encryption" checks |
| P2-2 | Add `terraform-plan` validator (mock providers, no apply) | ~40 LOC | **P1** | Catches semantic errors `validate` misses (invalid refs, circular deps) |
| P2-3 | Add Conftest as optional validator type | ~30 LOC | **P2** | For teams that already have Rego policies |
| P2-4 | Add `kustomize build` validator for K8s | ~20 LOC | **P2** | Closer to "final state" than raw YAML parse |

### What We Do Well

- Graceful skip-on-missing pattern (tool not on PATH → status=skipped, not failure)
- Plugin-style `_STRUCTURAL_EVALUATORS` registry makes adding new types trivial
- Binary pass/fail with failure taxonomy matches SWE-bench scoring model
- No apply/destroy is correct — keeps evals fast, cheap, repeatable

---

## Phase 3 — Knowledge Assertions

### Source Alignment

| Source | Alignment | Gap |
|--------|-----------|-----|
| Agent-as-a-Judge | **Design gap** — hierarchy specified in DESIGN.md but NOT implemented | No group/weight/when_parent_matches in code |
| DeepEval | Divergent approach — we use mandatory `source` annotation vs their LLM entailment | Our approach is deterministic and auditable; their approach catches semantic equivalence |
| Promptfoo | Strong — our types cover contains/regex/not-contains | Missing: callable/script assertion type |

### Gaps to Close

| # | Gap | Effort | Priority | Rationale |
|---|-----|--------|----------|-----------|
| P3-1 | Implement hierarchical assertions (`group`, `weight`, `when_parent_matches`) | ~100 LOC | **P0** | Largest design-implementation gap; designed in DESIGN.md, never built |
| P3-2 | Add per-assertion `weight` field (even without groups) | ~20 LOC | **P1** | Improves scoring fidelity; some assertions matter more |
| P3-3 | Add `script` assertion type (run arbitrary command, exit code = pass/fail) | ~25 LOC | **P2** | Closes Promptfoo `javascript` gap; enables structural checks without new types |
| P3-4 | Consider `must-contain-semantic` (embedding similarity) | ~80 LOC + dep | **P3** | Bridges DeepEval gap; catches paraphrases that regex misses |

### What We Do Well

- Mandatory `source` field creates auditable chain — zero-hallucination alternative to LLM faithfulness checks
- `must-contain-one-of` has no Promptfoo equivalent (useful OR-group)
- Schema validation before eval catches malformed assertions early

---

## Phase 4 — Regression + Snapshots

### Source Alignment

| Source | Alignment | Gap |
|--------|-----------|-----|
| tau-bench | Strong — pass^k implemented correctly, K configurable | No explicit flake_rate = pass^1 - pass^k metric |
| Braintrust | Partial — baseline exists but single-file, no content hash | Overwrites baseline; no dataset pinning |
| Langfuse | Partial — git SHA recorded but no per-eval traceability | Regression report is layer-level, not per-eval-case |
| Phoenix | Weak — stddev stored but unused for significance | No significance test; no historical trend |

### Gaps to Close

| # | Gap | Effort | Priority | Rationale |
|---|-----|--------|----------|-----------|
| P4-1 | Add eval-set content hash to baseline schema | ~15 LOC | **P0** | Prevents silent invalidation when eval prompts change between runs |
| P4-2 | Per-eval-case delta in regression report | ~40 LOC | **P0** | Enables tracing regression to specific eval/assertion |
| P4-3 | Statistical significance gate (z-test using stored stddev) | ~30 LOC | **P1** | Avoids false alarms on small N; uses already-captured stddev |
| P4-4 | Timestamped baseline history (baselines/<timestamp>.json) | ~20 LOC | **P1** | Braintrust immutability; enables trend analysis |

### What We Do Well

- pass^k as CI gate dimension matches tau-bench exactly
- Configurable threshold per skill
- Structured baseline schema with git SHA + model metadata
- WARNING vs REGRESSION exit code distinction (borderline handling)

---

## Phase 5 Design Validation

The Phase 5 design (`.skilleval.yaml` + composite scoring + letter grades) maps to:

| Feature | Source Pattern | Alignment |
|---------|---------------|-----------|
| Composite score with weights | Braintrust composable Score(0-1) | Strong |
| Per-skill weight redistribution | DeepEval configurable metrics | Strong |
| Letter grades | No direct source — our addition | N/A |
| Config traversal | Promptfoo per-project config | Strong |
| Eval-set pinning | Braintrust dataset pinning | **Must-add** (see P4-1) |

Phase 5 design is sound. The only addition needed before implementation: ensure the `.skilleval.yaml` schema includes an `eval_set_hash` field that the regression engine validates.

---

## Consolidated Priority List

### P0 — Must-do before Phase 5

| ID | Layer | Change |
|----|-------|--------|
| P3-1 | Knowledge | Implement group/weight/when_parent_matches hierarchy |
| P2-1 | Artifact | Add `hcl-attribute-check` (parsed HCL, not regex) |
| P4-1 | Regression | Add eval-set content hash to baseline schema |
| P4-2 | Regression | Per-eval-case delta in regression report |
| P1-1 | Process | Add `tool-args-schema` assertion type |

### P1 — Should-do before Phase 5

| ID | Layer | Change |
|----|-------|--------|
| P1-2 | Process | `progress_indicators` on tool-effectiveness |
| P1-3 | Process | `premature_termination` failure class |
| P2-2 | Artifact | `terraform-plan` validator |
| P3-2 | Knowledge | Per-assertion `weight` field |
| P4-3 | Regression | Statistical significance gate |
| P4-4 | Regression | Timestamped baseline history |

### P2 — Nice-to-have (future)

| ID | Layer | Change |
|----|-------|--------|
| P2-3 | Artifact | Conftest as optional validator |
| P2-4 | Artifact | `kustomize build` validator |
| P3-3 | Knowledge | `script` assertion type |
| P3-4 | Knowledge | `must-contain-semantic` (embeddings) |

---

## Conclusion

The implementation is well-aligned with source patterns across all 4 layers. The largest gap is **P3-1** (hierarchical assertions) — specified in DESIGN.md but never built. The P0 items (5 total) should land before Phase 5 begins, as they affect the scoring model that Phase 5 builds on.
