# `misc/evals/` — 5-layer skill evaluation framework

This directory hosts the evaluation framework for all 10 maintained skills. The framework uses a 5-layer architecture where layers 0–3 are fully deterministic and only layer 4 (quality) uses an LLM judge.

```
┌─────────────────────────────────────────────────────┐
│  Layer 0: Triggering                                │
│  Does the skill fire on the right prompts?          │
│  (run_triggering.py — LIVE)                         │
├─────────────────────────────────────────────────────┤
│  Layer 1: Process Assertions                        │
│  Did the agent use the right tools in the right     │
│  order? (process_assertions.py — deterministic)     │
├─────────────────────────────────────────────────────┤
│  Layer 2: Artifact Validation                       │
│  Are the outputs structurally correct?              │
│  (artifact_validation.py — deterministic)           │
├─────────────────────────────────────────────────────┤
│  Layer 3: Knowledge Assertions                      │
│  Does the output contain must-have facts?           │
│  (knowledge_assertions.py — deterministic)          │
├─────────────────────────────────────────────────────┤
│  Layer 4: Quality Judgment                          │
│  Is the response well-structured and complete?      │
│  (grader.md — LIVE, LLM-as-judge)                   │
└─────────────────────────────────────────────────────┘
```

Composite scoring combines all layers via configurable weights in `.skilleval.yaml`, producing a letter grade (A–F).

## Scorecard

*Baseline: 2026-06-04 · model: claude-opus-4-6 via Bedrock · pass@3*

| Skill | Grade | Score | Triggering | Process | Artifact | Knowledge | Quality |
|---|---|---|---|---|---|---|---|
| eks-best-practices | **A** | 93.1 | 86% (w=0.20) | 100% (w=0.10) | — | 90% (w=0.40) | 100% (w=0.30) |
| eks-build | **A** | 90.7 | 90% (w=0.15) | 75% (w=0.10) | 83% (w=0.20) | 93% (w=0.25) | 100% (w=0.30) |
| eks-design | **A** | 90.8 | 90% (w=0.15) | 67% (w=0.15) | 100% (w=0.20) | 96% (w=0.20) | 94% (w=0.30) |
| eks-mcp-server | **A** | 100.0 | 100% (w=0.35) | 100% (w=0.10) | — | 100% (w=0.30) | 100% (w=0.25) |
| eks-operation-review | **A** | 95.0 | 100% (w=0.25) | 88% (w=0.10) | 100% (w=0.15) | 100% (w=0.20) | 88% (w=0.30) |
| eks-platform-engineering | **A** | 98.8 | 100% (w=0.20) | 75% (w=0.05) | — | 100% (w=0.45) | 100% (w=0.30) |
| eks-recon | **A** | 96.3 | 92% (w=0.15) | 100% (w=0.10) | 100% (w=0.30) | 100% (w=0.20) | 90% (w=0.25) |
| eks-upgrade-check | **A** | 97.0 | 100% (w=0.25) | 80% (w=0.15) | — | 100% (w=0.35) | 100% (w=0.25) |
| steering-workflow-creator | **D** | 64.9 | 88% (w=0.15) | 45% (w=0.15) | 50% (w=0.25) | 55% (w=0.25) | 94% (w=0.20) |
| update-docs | **B** | 82.6 | 100% (w=0.20) | 62% (w=0.25) | — | 84% (w=0.30) | 88% (w=0.25) |

> **—** = layer not applicable (skill has no artifact outputs). Weight is redistributed to other layers via `.skilleval.yaml`.

### How to read the scorecard

- **Score** — weighted composite (0–100) across all applicable layers.
- **Grade** — A (≥90), B (≥80), C (≥70), D (≥60), F (<60).
- **Per-layer %** — raw pass rate for that layer. `w=` shows the weight applied.
- **—** — layer doesn't apply to this skill (e.g. advisory skills produce no artifacts).

---

## How to update evals (manual process)

Evals are maintainer-run. There is no CI gate — you run them locally when a skill changes and commit the updated scores.

### Step 1 — Run evals

```bash
cd misc/evals

# Triggering (layer 0) — tests description routing
make triggering-<skill> RUNS_PER_QUERY=3

# Task evals (layers 1–4) — runs the skill, grades output
make task-<skill> RUNS_PER_PROMPT=3

# Composite score — combines all layers into a grade
make composite-<skill>
```

Or run everything at once:

```bash
make task-all-parallel RUNS_PER_PROMPT=3    # all skills, all layers
make composite-all                          # recompute all grades
```

### Step 2 — Update the scorecard in this README

After running evals, read the composite scores from each skill's output and manually update the scorecard table above. The composite score output shows the grade, overall score, and per-layer breakdown.

To freeze scores as a baseline for future regression checks:

```bash
make snapshot-<skill>
```

### Step 3 — Update the docs site

The docs site at `misc/website/` has an evals page. After updating scores:

```bash
cd misc/website
npm install
npm run build        # verify it builds
npm run start        # preview locally
```

Then commit and push — the GitHub Pages deploy runs on push to main.

---

## The 5 layers

### Layer 0 — Triggering

Tests whether the skill's `description:` field in SKILL.md correctly routes prompts. Each skill has ≥16 prompts (≥8 positives, ≥8 near-miss negatives). Scored via Wilson confidence interval across multiple runs.

```bash
make triggering-<skill>
make triggering-all
```

### Layer 1 — Process Assertions

Deterministic assertions against the agent's tool-call trajectory (extracted from `events.jsonl`). Tests: did it call the right tools, in the right order, the right number of times?

Assertion types: `tool-called`, `tool-sequence`, `tool-call-count`, `step-count`, `no-tool-called`, `tool-effectiveness`.

```bash
make process-<skill>
make process-all
```

### Layer 2 — Artifact Validation

Deterministic structural checks on output files (Terraform, YAML, Markdown, etc.).

Assertion types: `file-exists`, `file-not-exists`, `contains`, `not-contains`, `yaml-valid`, `json-valid`, `file-count`, `hcl-resource-exists`, `mermaid-valid`.

Validator runners: `terraform-fmt`, `terraform-validate`, `checkov`, `shellcheck`, `markdownlint`, `kubectl-dry-run`, `script`.

```bash
make artifact-<skill>
make artifact-all
```

### Layer 3 — Knowledge Assertions

Expert-authored must-contain/must-not-contain assertions with required `source` field grounding each to an authoritative reference.

Assertion types: `must-contain`, `must-not-contain`, `must-contain-one-of`, `regex-match`.

### Layer 4 — Quality Judgment

LLM-as-judge (via `grader.md` subagent) evaluates subjective quality: structure, completeness, tone, actionability. This is the only non-deterministic layer — it never judges correctness (layers 1–3 handle that).

```bash
make task-<skill>           # runs subject + grader, produces all layer scores
make task-all-parallel      # all skills in parallel
```

## Composite scoring

Each skill has a `.skilleval.yaml` config that defines weight distribution across layers:

```yaml
weights:
  triggering: 20
  process: 15
  artifact: 25
  knowledge: 25
  quality: 15
timeout: 1800
```

Skills without artifacts (advisory skills) redistribute that weight to knowledge + quality.

```bash
make composite-<skill>
make composite-all
```

## Regression detection

Baselines are committed under `<skill>/baselines/baseline.json`. Compare current scores against the baseline:

```bash
make snapshot-<skill>       # freeze current scores
make regression-<skill>     # compare against baseline, exit 2 on regression
```

## Per-skill layout

```
misc/evals/<skill>/
├── triggering.json       # trigger prompts: [{query, should_trigger}, ...]
├── evals.json            # task prompts: {skill_name, evals: [{id, prompt, expectations, ...}]}
├── .skilleval.yaml       # weight config for composite scoring
├── baselines/            # committed — baseline.json from `make snapshot`
│   └── baseline.json
├── files/                # fixtures referenced from evals[].files
├── workspace/            # gitignored — run outputs live here
└── README.md             # scope, sibling disambiguation, live-MCP caveats
```

## Model & provider configuration

| Variable | Default | Notes |
|---|---|---|
| `PROVIDER` | `bedrock` | `bedrock` or `anthropic` |
| `MODEL` | provider-aware | `bedrock` → `global.anthropic.claude-opus-4-6-v1`; `anthropic` → `claude-opus-4-6-v1` |
| `RUNS_PER_QUERY` | `3` | ≥3 for meaningful confidence intervals |
| `NUM_WORKERS` | `10` | Parallelism for triggering runs |
| `RUNS_PER_PROMPT` | `1` | Task eval runs per prompt (3 for stddev) |

```bash
make triggering-all                                     # default: Bedrock Opus
make triggering-all PROVIDER=anthropic                  # Anthropic API
make triggering-eks-best-practices RUNS_PER_QUERY=1     # cheap iteration
```

## Adding evals for a new skill

Contributors only need to author `triggering.json`. Maintainers run the full eval suite after merge.

### Happy path — `/apex:new-skill`

The workflow handles: scope intake → skill draft → sibling survey → repo fan-out → triggering.json scaffold → PR prep. Full spec at [`steering/workflows/new-skill.md`](../../steering/workflows/new-skill.md).

### Manual path

```bash
cd misc/evals
make init-evals SKILL=<name>                    # scaffold from _template/
make init-evals SKILL=<name> SIBLINGS="a,b,c"   # with sibling placeholders
```

Fill in `triggering.json` — expand to ≥16 prompts (≥8 positives, ≥8 negatives).

Update neighbours when the new skill is a sibling:

```bash
python scripts/update_sibling_map.py \
  --new-skill <name> --target-sibling <sibling> \
  --scope "<one-line scope>" \
  --negative-prompt "<near-miss prompt>"
```

## Python dependencies

```bash
pip install pyyaml
```

## Reference

- **Design doc**: [`DESIGN.md`](./DESIGN.md) — full 5-layer architecture
- **Source mapping**: [`SOURCE-MAPPING.md`](./SOURCE-MAPPING.md) — research sources per layer
- **Skill-creator schemas**: [`skills/skill-creator/references/schemas.md`](../../skills/skill-creator/references/schemas.md)
