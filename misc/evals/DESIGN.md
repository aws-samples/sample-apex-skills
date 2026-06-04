# Eval Framework v2 — Design Document

**Issue:** #29
**Status:** Active
**Date:** 2026-06-03

## Problem Statement

The current eval framework answers "is this skill better than no skill?" but fails to answer the three questions that actually matter:

1. **Did this change improve the skill?** — We compare with-skill vs without-skill, but we need version-N vs version-N-1.
2. **How do we eval skills that produce deployable artifacts?** — eks-build produces Terraform, eks-design produces architecture docs. The conversation is not the output — the artifact is.
3. **Can we trust the grader?** — The skill IS the expert knowledge source. An LLM judge without that knowledge can't verify what the skill teaches. It confidently approves wrong answers it can't distinguish from right ones.

### Evidence of Current Pain

- Task evals penalize expert skills (clarifying questions = timeout/failure)
- LLM grader assertions are too easy (existence checks) or too brittle (exact strings)
- Eval setup preconditions sometimes don't exist in sandbox (systematic 0% scores)
- eks-mcp-server 53% TNR from sibling leakage that's hard to diagnose
- Wide confidence intervals (31%-100%) from small samples
- No version-over-version regression signal — only point-in-time scores

## Research Foundation

### Academic Benchmarks

| Framework | Key Insight for Us |
|-----------|-------------------|
| **SWE-bench** | Gold standard: binary pass/fail on real test suites. No subjective judgment. |
| **tau-bench** | pass^k metric — reliability drops fast over K trials. Compare DB state at end vs goal state. |
| **MINT** | Better single-turn ≠ better multi-turn. Process matters. |
| **ToolBench** | Depth-first search decision trees evaluate multiple reasoning paths. |

### Eval Tooling

| Tool | Pattern We Adopt |
|------|-----------------|
| **Promptfoo** | Trajectory assertions: `tool-used`, `tool-args-match`, `tool-sequence`, `step-count` |
| **DeepEval** | Typed agent metrics: Task Completion, Tool Correctness, Argument Correctness |
| **Braintrust** | Immutable snapshots + CI regression gates per PR |
| **Conftest/OPA** | Rego policy validation for structured artifacts (Terraform, K8s YAML) |
| **Terratest** | Apply → assert → destroy for functional artifact verification |

### The Judge Problem (Research)

- **Zheng et al. (NeurIPS 2023)** — GPT-4 as judge: >80% human agreement but has position, verbosity, and self-enhancement biases. Fails on complex reasoning.
- **Hamel Husain** — "LLM judges are a meta-problem requiring their own mini-evaluation." Binary labels > scores. Track judge-human correlation.
- **AgentEval** — Generate domain-specific criteria rather than using one generic judge.

**Our conclusion:** LLM judge is valid for subjective quality (clarity, structure, actionability). It is NOT valid for expert knowledge verification. An LLM without the skill cannot tell if the skill's recommendations are correct.

## Design: Layered Evaluation

Five layers, increasing in cost and decreasing in frequency:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 0: Triggering (existing)                          │
│ → Did the right skill fire? TPR/TNR/flake/sibling leak  │
├─────────────────────────────────────────────────────────┤
│ Layer 1: Process Assertions (new, deterministic)        │
│ → Did it call the right tools in the right order?       │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Artifact Validation (new, deterministic)       │
│ → Does the output pass static analysis / policy?        │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Knowledge Assertions (new, deterministic)      │
│ → Does it contain/avoid specific expert claims?         │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Quality Judgment (existing, LLM, optional)     │
│ → Is it well-structured, clear, actionable?             │
│ → NEVER used for factual correctness.                   │
└─────────────────────────────────────────────────────────┘
```

### Layer 0: Triggering (keep as-is)

No changes needed. TPR/TNR/flake/sibling-leakage is mature.

### Layer 1: Process Assertions

Evaluate the tool-call trajectory from stream-json output. Deterministic, no LLM.

**Assertion types:**

```yaml
assertions:
  - type: tool-called
    tool: Read
    min: 1
  - type: tool-called
    tool: Skill
    args_match:
      skill: eks-best-practices
  - type: tool-sequence
    sequence: [Read, Bash, Edit]
  - type: tool-call-count
    tool: Bash
    min: 2
    max: 10
  - type: step-count
    min: 3
    max: 20
  - type: no-tool-called
    tool: Write  # should not create new files
  - type: tool-effectiveness
    description: "Each tool call after the first must advance toward goal"
    max_consecutive_no_progress: 2
```

**Implementation:** Parse stream-json events, extract tool_use blocks, run assertions against the sequence. Returns pass/fail per assertion with evidence (the matching tool call or its absence).

**Per-turn marginal gain (from MINT research):** Beyond bounding step count, measure whether each tool call advances state. The `tool-effectiveness` assertion catches the "agent loops without progress" failure mode common in RLHF-tuned models. MINT showed single-turn performance does not predict multi-turn performance — a model that performs well on isolated tool calls may degrade across a multi-step trajectory.

**Applicable to:** All skills. Multi-step skills (eks-build, eks-design) get process assertions that verify the expected workflow happened.

### Layer 2: Artifact Validation

Run static analysis on produced files. Deterministic, no LLM.

**Validation pipelines per artifact type:**

| Artifact Type | Validators |
|---------------|-----------|
| Terraform (.tf) | `terraform validate`, `terraform fmt -check`, tflint, checkov, trivy |
| Kubernetes YAML | `kubectl --dry-run=client`, conftest/OPA policies |
| Mermaid diagrams | mermaid-cli render (exit code = valid) |
| Markdown (ADRs, docs) | markdownlint, section-header assertions |
| Shell scripts | shellcheck, bash -n |
| JSON/YAML config | jsonschema validation |

**Skill declares its artifact type in eval config:**

```yaml
# evals.json (v2)
{
  "skill_name": "eks-build",
  "artifact_type": "terraform",
  "validators": ["terraform-validate", "checkov", "structural"],
  "structural_assertions": [
    {"type": "file-exists", "path": "main.tf"},
    {"type": "contains", "file": "main.tf", "pattern": "aws_eks_cluster"},
    {"type": "contains", "file": "main.tf", "pattern": "module.*karpenter"},
    {"type": "hcl-resource-exists", "resource": "aws_eks_cluster"}
  ]
}
```

**Implementation:** After skill run completes, scan outputs directory. Run configured validators. Each returns pass/fail + detail. Aggregate into artifact_score.

### Layer 3: Knowledge Assertions

Expert-authored ground-truth checks. Deterministic string/regex matching — no LLM needed.

**Assertion types:**

```yaml
knowledge_assertions:
  - type: must-contain
    pattern: "gp3"
    context: "EBS volume type recommendation"
    source: "https://docs.aws.amazon.com/eks/latest/best-practices/storage.html"
  - type: must-not-contain
    pattern: "kube2iam"
    context: "Deprecated credential approach"
    source: "https://github.com/jtblin/kube2iam#archived"
  - type: must-contain-one-of
    patterns: ["Pod Identity", "IRSA"]
    context: "Credential strategy recommendation"
  - type: must-warn
    pattern: "PodSecurityPolicy.*deprecated"
    context: "PSP removal in 1.25"
  - type: regex-match
    pattern: "Karpenter.*consolidat"
    context: "Should mention Karpenter consolidation"
  # Hierarchical assertions (group-level scoring with conditional checks)
  - group: "compute_strategy"
    weight: 0.3
    assertions:
      - type: must-contain-one-of
        patterns: ["Karpenter", "managed node groups", "Auto Mode"]
        context: "Must recommend a compute strategy"
        source: "https://docs.aws.amazon.com/eks/latest/best-practices/compute.html"
      - type: must-contain
        pattern: "consolidat"
        when_parent_matches: "Karpenter"
        context: "Karpenter requires consolidation policy discussion"
        source: "https://karpenter.sh/docs/concepts/disruption/"
```

**Key design decisions:**
- Every assertion has a `source` field linking to the authoritative reference
- `must-not-contain` catches knowledge regression when best practices change
- Assertions are versioned — when AWS deprecates something, add a must-not + remove the must-contain
- Humans write these. They are the expert ground truth. Not auto-generated.
- Hierarchical assertions allow group-level partial credit and conditional checks (`when_parent_matches`) — prevents flat assertion lists from growing unwieldy for knowledge-heavy skills (inspired by Agent-as-a-Judge's hierarchical requirement decomposition)

**Applicable to:** Knowledge-heavy skills (eks-best-practices, eks-platform-engineering, terraform-skill). Not meaningful for process-heavy skills (eks-recon, update-docs).

### Layer 4: Quality Judgment (existing LLM grader, scoped down)

Keep the existing grader but restrict its scope:
- Structure and formatting (headings, sections, readability)
- Actionability (are recommendations specific and implementable?)
- Completeness (did it address all parts of the question?)
- Clarity (is it well-organized and understandable?)

**Explicitly NOT judging:** factual correctness, best-practice validity, technical accuracy. Those are Layer 3's job.

## Regression Detection

### Snapshot Model

```
misc/evals/<skill>/
  baselines/
    v1.0.0.json       # frozen snapshot at release
    v1.1.0.json
    latest.json        # most recent full run
  runs/
    2026-06-03T14:30:00Z/
      eval-1/
        with-skill/
          transcript.md
          outputs/
          timing.json
        without-skill/
          transcript.md
          outputs/
      grading.json
      process-assertions.json
      artifact-validation.json
      knowledge-assertions.json
```

### Baseline Command

```bash
make snapshot SKILL=eks-build  # freezes current scores as baseline
make regression SKILL=eks-build  # runs evals, compares against baseline
```

### Regression Signal

```
Δ = current_score - baseline_score

If Δ < -threshold:
  REGRESSION — block merge (CI gate)
If Δ >= 0:
  IMPROVEMENT or STABLE — pass
If -threshold <= Δ < 0:
  NOISE — pass with warning
```

Threshold is configurable per skill (default: -5% for triggering, -10% for task layers).

### pass^k Reliability (from tau-bench)

Run each eval K times (default K=3). Report:
- pass^1: any single run passes
- pass^3: all 3 runs pass (reliability metric)
- flake rate: pass^1 - pass^3

Skills with high flake rate need attention regardless of absolute score.

### Failure Taxonomy

Classify assertion failures into named categories (inspired by tau-bench's fault diagnosis). Every failed assertion produces a `failure_class` enabling fast regression debugging:

| Failure Class | Layer | Meaning |
|---------------|-------|---------|
| `missed_tool` | 1 | Expected tool never called |
| `wrong_sequence` | 1 | Tools called in wrong order |
| `excess_steps` | 1 | Too many tool calls (efficiency regression) |
| `no_progress_loop` | 1 | Consecutive tool calls without state advancement |
| `artifact_invalid` | 2 | Static analysis failure (syntax, lint, policy) |
| `artifact_missing` | 2 | Expected output file not produced |
| `knowledge_gap` | 3 | Must-contain assertion failed (never knew it) |
| `knowledge_regression` | 3 | Must-not-contain triggered OR previously-passing must-contain now fails |
| `quality_decline` | 4 | LLM grader score dropped below threshold |

Failure classes enable:
- **Prioritized debugging** — `knowledge_regression` is more urgent than `knowledge_gap` (it worked before)
- **Trend analysis** — track which failure classes increase across versions
- **Targeted remediation** — `excess_steps` → optimize prompting; `artifact_invalid` → fix templates

### Elicitation Strategy

Borrowed from Inspect AI's Solver/Scorer separation: explicitly name how the agent is prompted during eval, separate from how the output is scored.

| Strategy | Description | When to use |
|----------|-------------|-------------|
| `single-shot` | One prompt, evaluate first response | Simple skills, triggering evals |
| `canned-multiturn` | Pre-scripted follow-up answers | Skills that ask clarifying questions (eks-build, eks-design) |
| `user-simulator` | LLM-driven user with persona/goal | Complex multi-turn workflows needing realistic interaction |

Configured in `.skilleval.yaml`:

```yaml
elicitation:
  strategy: canned-multiturn
  turns:
    - question_match: "which region"
      answer: "us-west-2"
    - question_match: "how many environments"
      answer: "3 (dev, staging, prod)"
```

This resolves the "multi-step timeout" open question — skills that ask clarifying questions get pre-canned answers, making eval reproducible and deterministic.

## Scoring Model

### Per-Layer Scores

```
Layer 0 (Triggering):   TPR × TNR (existing Wilson CI formula)
Layer 1 (Process):      assertions_passed / assertions_total
Layer 2 (Artifact):     validators_passed / validators_total
Layer 3 (Knowledge):    assertions_passed / assertions_total
Layer 4 (Quality):      grader_pass_rate (existing)
```

### Composite Score

```
composite = (
    0.20 × triggering_score +
    0.15 × process_score +
    0.25 × artifact_score +
    0.25 × knowledge_score +
    0.15 × quality_score
)
```

Weights are configurable per skill. Skills without artifacts (e.g., eks-best-practices) redistribute artifact weight to knowledge. Skills without knowledge assertions (e.g., update-docs) redistribute to process + artifact.

### Grade Thresholds

```
A: >= 90  (release-ready)
B: >= 80  (good, minor gaps)
C: >= 70  (functional, needs work)
D: >= 60  (significant gaps)
F: <  60  (broken or unmaintained)
```

## Config: `.skilleval.yaml`

Per-skill configuration, discovered by walking up from eval directory:

```yaml
skill_name: eks-build
artifact_type: terraform

artifacts:
  - glob: "**/*.tf"
    type: terraform
  - glob: "design/**/*.md"
    type: markdown
  - glob: "**/*.mermaid"
    type: mermaid

layers:
  triggering:
    enabled: true
    runs_per_query: 3
    threshold_tpr: 0.85
    threshold_tnr: 0.80
  process:
    enabled: true
  artifact:
    enabled: true
    validators: [terraform-validate, checkov, structural]
  knowledge:
    enabled: true
  quality:
    enabled: true
    model: claude-sonnet-4-6-20250514

weights:
  triggering: 0.20
  process: 0.15
  artifact: 0.25
  knowledge: 0.25
  quality: 0.15

regression:
  threshold: -0.05
  pass_k: 3

timeout: 600
model: claude-sonnet-4-6-20250514
```

Layering: `.skilleval.yaml` in skill dir < project-level `misc/evals/.skilleval.yaml` < CLI flags.

**Artifact extraction** uses declared globs rather than heuristic workspace scanning. This makes extraction deterministic — the skill author declares what outputs are expected, and the framework knows exactly where to find them. Resolves Open Question #5.

## Migration Path

### Phase 1: Process Assertions (week 1-2)

- Add stream-json parser to extract tool-call trajectory
- Implement assertion engine (tool-called, tool-sequence, tool-call-count, step-count)
- Add `process_assertions` field to evals.json schema
- Write process assertions for 3 pilot skills (eks-build, eks-recon, update-docs)
- Run alongside existing grader — additive, non-breaking

### Phase 2: Artifact Validation (week 2-3)

- Add artifact_type to evals.json schema
- Implement validator runners (terraform, kubectl, shellcheck, markdownlint)
- Write structural assertions for eks-build and eks-design
- Add `make validate SKILL=<name>` target

### Phase 3: Knowledge Assertions (week 3-4)

- Add knowledge_assertions field to evals.json schema
- Implement contains/regex/must-not assertion engine
- Author knowledge assertions for eks-best-practices (pilot — richest knowledge)
- Each assertion requires `source` field (forces grounding)

### Phase 4: Regression + Snapshots (week 4-5)

- Implement `make snapshot` and `make regression`
- Structured run directory layout (iteration/eval/mode/)
- Baseline comparison logic with configurable thresholds
- pass^k reliability metric
- CI gate: regression check on PRs touching skills/

### Phase 5: Config + Scoring (week 5-6)

- .skilleval.yaml parser with upward traversal
- Composite scoring with configurable weights
- Letter grades
- Updated scorecard in README
- Migrate existing evals.json files to v2 schema (backwards-compatible)

## What We Keep

- Layer 0 triggering (mature, working)
- CI hygiene checks (coverage, counts, attribution)
- History JSONL tracking
- Sibling-map attribution for negatives
- make targets as primary interface
- Sandbox isolation model

## What We Change

- Layer 4 (LLM grader) no longer judges factual correctness
- evals.json gains process_assertions, artifact_type, knowledge_assertions
- New structured run directory layout replaces flat workspace/runs/
- Snapshot/regression replaces ad-hoc scoring
- Composite score replaces single-axis benchmarks

## What We Remove

- expected_output field in evals.json (never used meaningfully by grader)
- Grader self-critique step (adds noise, not actionable)
- The implicit assumption that higher with-skill vs without-skill delta = better skill

## Open Questions

1. **Sandbox for artifact validation** — terraform validate needs provider plugins. Pre-bake a Docker image? Or validate structure only (HCL parse)?
2. **Knowledge assertion authoring UX** — Writing 20+ assertions per skill is tedious. Should we scaffold from existing skill references?
3. **Cost budget** — Full eval suite across 10 skills at K=3 is 60+ Claude calls. Run nightly? Per-PR only for changed skills?

## References

- Issue #29: https://github.com/aws-samples/sample-apex-skills/issues/29
- sample-agent-skill-eval: https://github.com/aws-samples/sample-agent-skill-eval
- tau-bench: https://arxiv.org/abs/2406.12045
- SWE-bench: https://github.com/princeton-nlp/SWE-bench
- Promptfoo trajectory assertions: https://www.promptfoo.dev/docs/configuration/expected-outputs/deterministic/#trajectory
- DeepEval agentic metrics: https://docs.confident-ai.com/docs/metrics-tool-correctness
- Zheng et al. LLM-as-Judge: https://arxiv.org/abs/2306.05685

### Research Papers (2023-2026)

- Agent-as-a-Judge (Zhuge et al. 2024): https://arxiv.org/abs/2410.10934 — agentic evaluators with hierarchical requirements
- tau-bench (Yao et al. 2024): https://arxiv.org/abs/2406.12045 — pass^k reliability, deterministic state evaluation
- AgentBench (Liu et al. 2023): https://arxiv.org/abs/2308.03688 — multi-environment capability profiling
- MINT (Wang et al. 2023): https://arxiv.org/abs/2309.10691 — per-turn marginal gain, multi-turn ≠ single-turn
- WebArena (Zhou et al. 2023): https://arxiv.org/abs/2307.13854 — functional correctness via environment state

### Eval Framework Repos

- promptfoo/promptfoo (21.8k★) — YAML-driven trajectory assertions, CI/CD regression gates
- confident-ai/deepeval (15.8k★) — pytest-style agent metrics, tool correctness scoring
- UKGovernmentBEIS/inspect_ai (2.1k★) — Solver/Scorer separation, 200+ evals, Docker sandboxing
- SWE-bench/SWE-bench (5k★) — deterministic test-suite validation, Docker per task
- sierra-research/tau-bench (1.2k★) — pass^k metric, fault classification, three-party simulation
- THUDM/AgentBench (3.4k★) — multi-environment deterministic scoring
- braintrustdata/autoevals (910★) — composable Score(0-1) interface, experiment comparison
- langfuse/langfuse (28.4k★) — versioned dataset baselines, trace-level scoring
- Arize-ai/phoenix (9.9k★) — experiment tracking, OpenTelemetry-native traces
- open-policy-agent/conftest (3.1k★) — Rego policy-as-code for structured artifact validation
