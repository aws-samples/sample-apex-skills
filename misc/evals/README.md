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
| update-docs | **B** | 82.6 | 100% (w=0.20) | 62% (w=0.25) | — | 84% (w=0.30) | 88% (w=0.25) |

> **—** = layer not applicable (skill has no artifact outputs). Weight is redistributed to other layers via `.skilleval.yaml`.

### How to read the scorecard

- **Score** — weighted composite (0–100) across all applicable layers.
- **Grade** — A (≥90), B (≥80), C (≥70), D (≥60), F (<60).
- **Per-layer %** — raw pass rate for that layer. `w=` shows the weight applied.
- **—** — layer doesn't apply to this skill (e.g. advisory skills produce no artifacts).

---

## How to update evals (manual process)

Scored eval runs are maintainer-run: you run them locally when a skill changes and commit the updated scores. A deterministic hygiene pre-flight (`check_hygiene.py`, wired into CI via `.github/workflows/evals.yml`) runs on every PR that touches `misc/evals/**` or `skills/**`. The scored and coverage layers are maintainer-run; the model-backed `eval-gate` CI job runs by hand until its secrets are added (see "Merge gate" below).

### Step 1 — Run evals

```bash
cd misc/evals

# Triggering (layer 0) — tests description routing
make triggering-<skill> RUNS_PER_QUERY=3

# Task evals (layers 1–4): runs the skill, grades output; each case runs
# the skill's regression.pass_k times (3 when unset) unless RUNS_PER_PROMPT is set
make task-<skill>

# Composite score — combines all layers into a grade
make composite-<skill>
```

Or run everything at once:

```bash
make task-all-parallel                      # all skills, all layers
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

## Merge gate (old against new)

The gate compares each skill as it is now (arm `with_skill`) with the same skill at a git ref (arm `base_skill`, default the `v1.3.0` tag, then the skill's last released tag). A skill absent at the ref, such as a new skill, runs against `without_skill`.

```bash
make gate SKILL=<run key>                   # one run key
make gate SKILL=eks-recon HARNESS=codex     # another harness
make gate-all                               # every run key with a runnable case
make gate-stages                            # the deterministic stages only, no model call
```

`gate` runs, in this order, the deterministic stages (class admission checks, schema validation, link check, size check), then the evals. The four stage commands are the Makefile variables `GATE_ADMISSION_CMD`, `GATE_SCHEMA_CMD`, `GATE_LINK_CMD` and `GATE_SIZE_CMD`. They are empty here, and the stage prints that it is not wired; the checks are owned by later changes, which set the commands from `.github/workflows/evals.yml`. A stage that exits non-zero stops the gate before any model call. Then `run_task_evals.py` runs each case `regression.pass_k` times per arm, and `regression.py --gate` scores that run's own result. `SKILL` takes any run key `run_task_evals.py --list-targets` prints: a `misc/evals/<skill>` folder or a class target.

What blocks (exit 2):

- A case that fails Pass@k: none of its k `with_skill` runs passed. A run passes only when it is valid and every grader expectation, process assertion and artifact check passed; an invalid run (no events, no init event, a non-zero exit, a timeout) never passes. One failed case fails the gate on its own. A skill's own cases always block; a shared class case blocks only on a blocking target (`CLASS_TARGETS`: today the three repo-owned `devops-agent` copies), and on a report-only target it is listed without blocking.
- A pooled pass-rate drop (the `with_skill` mean less the base arm's mean) past `THRESHOLD` points.

Tokens and time per case and per skill are in the report and do not block: until the maintainers decide whether tokens or time may block a merge, only pass rate blocks. The gate exits 1, never 0, when there is nothing to score: a runner error, a refused eval-role session or a run key with no runnable case. The report goes to stderr, to `gate-report.md` in the run key's workspace and, in GitHub Actions, to the job summary.

Runner flags the gate uses (`run_task_evals.py`):

| Flag | Default | Meaning |
|---|---|---|
| `--harness {claude,kiro,codex}` | `claude` | Subject harness, one adapter each; the grader is `claude -p` on every harness |
| `--base-ref REF` | `v1.3.0` | Git ref of the base arm; `none` runs `with_skill` against `without_skill` |
| `--runs N` | the skill's `regression.pass_k` | Runs per case and arm |
| `--list-targets` | | Prints one JSON line per run key and exits; mints no credential, runs nothing |

`run_triggering.py` takes `--harness` too, plus `--class CLASS` (repeatable: adds that class's shared trigger cases from `classes/<class>/evals/trigger/triggering.json`, parents first, for a skill on the class's target list), `--list-class-targets CLASS` (prints the target list and exits), `--kubeconfig PATH` (each run gets its own 0600 copy) and `--runs-per-query` (default 3). `--eval-set` is needed unless `--class` is given. A triggering run that is invalid (no init event, a non-zero exit, a timeout, an error result) is left out of the trigger count, and a query with no valid run fails on both the should and the should-not side.

Harnesses: `claude` (`claude -p`), `kiro` (`kiro-cli chat --no-interactive`) and `codex` (`codex exec --json`). The claude and codex subjects call Bedrock on the eval-role session. Kiro's model calls go to Kiro's own service, signed in with `KIRO_API_KEY`, not to Bedrock on the eval role, so a live Kiro run needs a maintainer's approval first. The kiro and codex adapters are built and tested on recorded output only.

Every real run, on any harness, waits on the decision on whether evals may run on a shared host and on the dedicated eval role. The CI job `eval-gate` in `.github/workflows/evals.yml` runs only by hand (`workflow_dispatch`) until a maintainer adds its CI credentials and repository secrets: `APEX_EVAL_AWS_CONFIG` (the `~/.apex-eval/aws-config` contents), `APEX_EVAL_EXPECTED_ACCOUNT` (the eval account id) and, for `HARNESS=kiro`, `KIRO_API_KEY`. How CI gets its AWS credential is not yet decided. Without the secrets the job fails at its first step, and a pull request from a fork gets no secrets, so it fails there too; there is no pass without them.

`make eval-manifest-check` (`generate_eval_manifest.py --check`) compares the committed `misc/website/static/manifests/evals.json` with a fresh build and exits 1 on a difference, writing nothing. Each manifest entry carries `tokens_per_run`, the `with_skill` mean tokens per run from the skill's latest task history row, null until a run records it.

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
| `PROVIDER` | `bedrock` | `bedrock` is the only value: every run needs `CLAUDE_CODE_USE_BEDROCK=1` and goes to Bedrock in the eval account (setup below) |
| `MODEL` | `global.anthropic.claude-opus-4-6-v1` | A Bedrock model or inference-profile ID |
| `RUNS_PER_QUERY` | `3` | ≥3 for meaningful confidence intervals |
| `NUM_WORKERS` | `10` | Parallelism for triggering runs |
| `RUNS_PER_PROMPT` | empty | Task eval runs per case and arm; empty uses the skill's `regression.pass_k` in `.skilleval.yaml` (3 when unset) |
| `HARNESS` | `claude` | Gate subject harness: `claude`, `kiro` or `codex` (the grader is `claude -p` on all three) |
| `BASE_REF` | `v1.3.0` | Git ref the gate's base arm takes the skill from; `none` runs against `without_skill` |
| `THRESHOLD` | `5` | Pooled pass-rate drop, in percentage points, that fails `regression` and the gate |

```bash
make triggering-all                                     # default: Bedrock Opus
make triggering-eks-best-practices RUNS_PER_QUERY=1     # cheap iteration
```

### Eval-role setup (`~/.apex-eval`)

Every eval run gets its AWS access from a short-lived session of one IAM role used only for evals, never from your own keys. The subject still runs as your OS user, so it can read your files and the runner's environment by path; run it as another OS user or in a container for a hard fence. Before the first model call the runner assumes that role and checks the session with `sts get-caller-identity`. If anything below is missing or wrong it refuses to start, with no fallback.

- `~/.apex-eval/aws-config`: an AWS CLI config file with a `[profile apex-eval-admin]` section. It sets `region` (the Region the evals call Bedrock in) and a `credential_process` line that prints credentials allowed to assume the eval role, such as your organisation's sign-in helper.
- `~/.apex-eval/expected-account`: the 12-digit id of the eval account, on one line. The runner builds the role ARN from it and refuses a session in any other account.
- Role `apex-eval-bedrock-invoke` in that account. Its trust policy trusts the IAM principal that profile `apex-eval-admin` signs in as (its ARN, a role or an IAM user). Its permissions allow `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`. For a global inference profile, such as the default model, allow the profile ARN, the model in your Region and `arn:aws:bedrock:::foundation-model/<model>` (Amazon Bedrock User Guide, [Global cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/global-cross-region-inference.html)). Claude Code's [Amazon Bedrock IAM configuration](https://code.claude.com/docs/en/amazon-bedrock#iam-configuration) also lists `bedrock:ListInferenceProfiles`, `bedrock:GetInferenceProfile` and two `aws-marketplace` subscription actions. For live-cluster evals the role also allows the AWS read actions in `setup/readonly-session-policy.json`, the read set the live prompts call: the `Describe*`, `List*` and `Get*` actions that file lists for EKS, EC2, IAM, CloudFormation, Auto Scaling, Elastic Load Balancing, CloudWatch and CloudWatch Logs, plus `logs:FilterLogEvents` and `sts:GetCallerIdentity`. Its `eks:Describe*` and `eks:List*` cover `eks:DescribeCluster` and `eks:ListClusters`, what `aws eks update-kubeconfig` needs ([Amazon EKS identity-based policy examples](https://docs.aws.amazon.com/eks/latest/userguide/security-iam-id-based-policy-examples.html)). Kubernetes reads go only through the read-only kubeconfig (`KUBECONFIG_RO`, from `setup/bootstrap-readonly.sh`): a ServiceAccount token with get, list and watch and no Secrets, a credential separate from the role. The role has no build rights: no IAM action that creates, changes or deletes cluster resources.
- `CLAUDE_CODE_USE_BEDROCK=1` (the Makefile sets it for `PROVIDER=bedrock`), so `claude -p` sends its model calls through Bedrock on that session.

AWS caps a role-chained session at one hour, so a subject or grader timeout plus 120 seconds must stay under 3600 seconds.

## Adding evals for a new skill

Contributors only need to author `triggering.json`. Maintainers run the full eval suite after merge.

### Steps

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
pip install pyyaml jsonschema
```

## Reference

- **Source mapping**: [`SOURCE-MAPPING.md`](./SOURCE-MAPPING.md) — research sources per layer
- **Skill-creator schemas**: [`skills/skill-creator/references/schemas.md`](../../skills/skill-creator/references/schemas.md)
