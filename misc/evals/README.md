# `misc/evals/` — per-skill evaluation home

This directory hosts evaluation inputs for the four in-scope skills so every capability that `skills/skill-creator/` ships with has usable inputs per skill:

- `eks-recon`
- `eks-best-practices`
- `eks-upgrader`
- `eks-mcp-server`

There is **no custom harness here.** The only new code is the top-level `Makefile`, which encodes the exact invocation patterns for `skill-creator`'s existing scripts. All eval logic lives upstream at `skills/skill-creator/`.

## Per-skill layout

```
misc/evals/<skill>/
├── triggering.json   # [{"query": str, "should_trigger": bool}, …]  — for run_eval / run_loop
├── evals.json        # {skill_name, evals: [{id, prompt, expected_output, expectations?, files?}]} — for grader.md
├── files/            # fixtures referenced from evals[].files (empty until needed)
├── workspace/        # gitignored — run_loop / run_eval write results here
└── README.md         # what the evals target, neighbour-skill disambiguation, live-MCP caveats
```

## Python dependencies

`skill-creator`'s scripts don't ship a `requirements.txt`. The only third-party import is **PyYAML** (used by `quick_validate.py` and `package_skill.py`). Live-model scripts shell out to `claude -p` rather than using the Anthropic SDK, so the only pip install you need is:

```bash
pip install pyyaml
```

## Adding evals for a new skill

Every skill in `skills/` must have a matching entry in `misc/evals/` (except upstream-synced skills: `skill-creator` and `terraform-skill`, which are maintained externally). The onboarding path is scripted:

```bash
cd misc/evals
make init-evals SKILL=<your-skill>
```

This copies `_template/` to `misc/evals/<your-skill>/` and substitutes `<REPLACE>` → `<your-skill>` across every file. The resulting directory has:

- `triggering.json` — 2-entry skeleton (1 positive + 1 negative). Expand to ≥16 prompts with balanced positives and near-miss negatives.
- `evals.json` — 1-entry skeleton; add 2–4 realistic task prompts. Every assertion is tagged `TODO: human review` until a human tunes it.
- `README.md` — fill in the four `<REPLACE>` sections (scope, neighbor-skill disambiguation, live-MCP caveat, how to run).
- `files/` — empty; drop input fixtures here as prompts demand.

To verify every skill has an eval entry:

```bash
make check-evals-coverage
```

Fails with a list of missing skills. Exits 0 when every `skills/<name>/` (minus the upstream-synced pair) has a corresponding `misc/evals/<name>/`.

See `CONTRIBUTING.md` for the full new-skill workflow including when in the PR lifecycle these pieces land.

## The working-directory quirk

`skills/skill-creator/scripts/__init__.py` exists (it marks `scripts/` as a Python package) and intra-package imports use `from scripts.xxx import yyy`. That forces **module-mode invocation** with cwd set to `skills/skill-creator/`:

```bash
cd skills/skill-creator
python3 -m scripts.run_eval --eval-set <path> --skill-path skills/<skill> …
```

Running `python3 scripts/run_eval.py` directly fails with `ModuleNotFoundError: No module named 'scripts'`.

The `Makefile` in this directory `cd`s to `skills/skill-creator/` before every `-m scripts.<name>` call and passes absolute paths to `--eval-set` / output dirs, so from your shell you can just run `make triggering-<skill>` from `misc/evals/` without thinking about it.

Two exceptions:

- `scripts/quick_validate.py` has no `scripts.` imports — it runs fine as `python3 scripts/quick_validate.py <skill>` (plain script-mode).
- `eval-viewer/generate_review.py` lives outside the `scripts/` package — invoked directly as `python3 eval-viewer/generate_review.py …`.

## Live-Claude vs deterministic

| Capability | Needs live model? |
|---|---|
| A `quick_validate` | deterministic |
| B `run_eval` | **live** (`claude -p`) |
| C `improve_description` | **live** |
| D `run_loop` | **live** |
| E `aggregate_benchmark` | deterministic |
| F `generate_report` | deterministic |
| G `package_skill` | deterministic |
| H `grader.md` (Task subagent) | **live** |
| I `comparator.md` (Task subagent) | **live** |
| J `analyzer.md` (Task subagent) | **live** |
| K `generate_review --static` | deterministic |

Live tools inherit Claude Code session auth — run them from a terminal that's logged into `claude -p`.

## MCP-dependent skills

`eks-recon` and `eks-mcp-server` are designed around the EKS MCP Server. When running **triggering** evals (B/D), MCP availability is not required — triggering tests the skill's description, not its body, so no EKS tools are invoked. When running **task** evals (H — grader against `evals.json` prompts), some prompts may need mocked fixtures in `files/` or a `live-only` marker if a real cluster is the only way to satisfy the expectation.

Per-skill `README.md` calls out which prompts are safe to run without MCP.

## Capability catalogue (A–K)

All invocations run from `misc/evals/` via the `Makefile` targets shown. The direct command equivalents — the ones the Makefile expands to — are included for reference.

### A — `quick_validate.py` (frontmatter + 64/1024-char limits)

```bash
make validate-<skill>
# → python3 <repo>/skills/skill-creator/scripts/quick_validate.py <repo>/skills/<skill>
```

Output: one-line verdict on stdout. Exit 0 valid / 1 invalid. No disk writes. Plain script-mode — no `cd` needed because `quick_validate.py` doesn't import from the `scripts.` package.

### B — `run_eval.py` (triggering score)

```bash
make triggering-<skill>  [MODEL=claude-sonnet-4-5] [NUM_WORKERS=10] [RUNS_PER_QUERY=3]
# → cd <repo>/skills/skill-creator && python3 -m scripts.run_eval \
#       --eval-set   <repo>/misc/evals/<skill>/triggering.json \
#       --skill-path <repo>/skills/<skill> \
#       --num-workers 10 --runs-per-query 3 --model <MODEL>
```

Output: full results JSON on stdout (redirect to save). Writes nothing to disk itself; creates/deletes ephemeral files under `<repo>/.claude/commands/` during each query.

### C — `improve_description.py` (propose a description rewrite)

Not exposed as a standalone Make target — it's driven by `run_loop`. To invoke manually:

```bash
cd <repo>/skills/skill-creator
python3 -m scripts.improve_description \
  --eval-results <run_eval.json> \
  --skill-path   <repo>/skills/<skill> \
  --model        claude-sonnet-4-5
```

Output: `{"description": "...", "history": [...]}` on stdout.

### D — `run_loop.py` (iterative description optimizer)

```bash
make optimize-<skill>  [MODEL=…] [MAX_ITER=5] [NUM_WORKERS=10] [RUNS_PER_QUERY=3]
# → cd <repo>/skills/skill-creator && python3 -m scripts.run_loop \
#       --eval-set   <repo>/misc/evals/<skill>/triggering.json \
#       --skill-path <repo>/skills/<skill> \
#       --model <MODEL> --max-iterations 5 --num-workers 10 --runs-per-query 3 \
#       --results-dir <repo>/misc/evals/<skill>/workspace \
#       --report none
```

Output: final JSON on stdout plus `<workspace>/<TIMESTAMP>/{results.json,report.html,logs/improve_iter_*.json}`. The Makefile passes `--report none` to suppress the auto-opened browser.

### E — `aggregate_benchmark.py` (aggregate grading.json stats across runs)

```bash
make benchmark-<skill> BENCHMARK_DIR=<path-containing-eval-*/…/grading.json>
# → cd <repo>/skills/skill-creator && python3 -m scripts.aggregate_benchmark <BENCHMARK_DIR> \
#       --skill-name <skill> --skill-path <repo>/skills/<skill>
```

Output: `<BENCHMARK_DIR>/benchmark.json` + `benchmark.md`. Supports both `<dir>/eval-*` and `<dir>/runs/eval-*` layouts (see `skills/skill-creator/scripts/aggregate_benchmark.py`).

`BENCHMARK_DIR` defaults to `<skill>/workspace/` — override when the grading runs live elsewhere.

### F — `generate_report.py` (HTML viz of `run_loop` results.json)

```bash
make report-<skill>  [RESULTS_JSON=<path>]
# → cd <repo>/skills/skill-creator && python3 -m scripts.generate_report <RESULTS_JSON> \
#       --skill-name <skill> -o <repo>/misc/evals/<skill>/workspace/report.html
```

`RESULTS_JSON` defaults to `<skill>/workspace/results.json`. Standalone HTML file; no server.

### G — `package_skill.py` (zip to `<skill>.skill`)

```bash
make package-<skill>
# → cd <repo>/skills/skill-creator && python3 -m scripts.package_skill \
#       <repo>/skills/<skill> <repo>/misc/evals/<skill>/workspace
```

Output: `<workspace>/<skill>.skill`. Validates first (imports `quick_validate`); exit 1 on failure. Excludes `__pycache__`, `node_modules`, `*.pyc`, `.DS_Store`, and `evals/` at the skill root.

### H — `agents/grader.md` (subagent grades a run)

No Make target — invoked via the `Task` tool by the agent running the eval. The grader spec expects inputs `expectations[]`, `transcript_path`, `outputs_dir`. Writes `grading.json` to `<run-dir>/grading.json`. Schema: `skills/skill-creator/references/schemas.md` §grading.json.

### I — `agents/comparator.md` (blind A/B compare two variants)

Task invocation; spec at `skills/skill-creator/agents/comparator.md`. Inputs: `output_a_path`, `output_b_path`, `eval_prompt`, optional `expectations`. Writes `comparison-<N>.json`.

### J — `agents/analyzer.md` (post-hoc analysis)

Task invocation; spec at `skills/skill-creator/agents/analyzer.md`. Inputs: winner/loser skill+transcript paths, `comparison_result_path`, `output_path`. Writes `analysis.json` to the specified `output_path`.

### K — `eval-viewer/generate_review.py --static`

```bash
make review-<skill> WORKSPACE=<dir-from-a-prior-optimize-run>
# → python3 <repo>/skills/skill-creator/eval-viewer/generate_review.py <WORKSPACE> \
#       --skill-name <skill> --static <repo>/misc/evals/<skill>/workspace/review.html
```

Writes a self-contained HTML file. No server, no `webbrowser.open()`.

## Score interpretation cheat sheet

- **Triggering (B/D)**: reported as `passed/total` in `run_eval` output; `run_loop` also reports a train/holdout split (default holdout = 0.4) and per-iteration deltas.
- **Task evals (H → E)**: `aggregate_benchmark` reports mean ± stddev of pass-rate across runs, plus per-expectation hit rate. `benchmark.md` renders a summary table.

## Workspace hygiene

`misc/evals/.gitignore` excludes `*/workspace/` and `*.html`. Don't commit run artefacts — regenerate them when you need them.

## Useful upstream references

- `skills/skill-creator/SKILL.md` §"Running and evaluating test cases" and §"Description Optimization".
- `skills/skill-creator/references/schemas.md` — authoritative schemas for `evals.json`, `grading.json`, `benchmark.json`, `comparison.json`, `analysis.json`.
- `skills/skill-creator/scripts/run_eval.py`, `run_loop.py`, `aggregate_benchmark.py`, `package_skill.py`, `generate_report.py` — canonical source for CLI args.
