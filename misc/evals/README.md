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

These scores are the baseline runner's (`make task-<skill>` and `make composite-<skill>`, run on the date below), not the merge gate's: the gate compares old against new per change and records no grade.

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

Scored eval runs are maintainer-run: you run them locally when a skill changes and commit the updated scores. A deterministic hygiene pre-flight (`check_hygiene.py`, wired into CI via `.github/workflows/evals.yml`) runs on every PR that touches `misc/evals/**` or `skills/**`. The scored and coverage layers are maintainer-run (see "Merge gate" below).

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
make snapshot-<skill>       # freeze current scores (reads the run's base arm: base_skill or without_skill)
make regression-<skill>     # compare against baseline, exit 2 on regression
```

## Merge gate (old against new)

The gate compares each skill as it is now (arm `with_skill`) with the same skill at a git ref (arm `base_skill`, default `v1.3.0`; pass `BASE_REF=<ref>` for another ref). A skill absent at the ref, such as a new skill, runs its task cases against `without_skill`; its trigger queries are scored on `with_skill` alone, since the triggering runner has no `without_skill` arm.

```bash
make gate SKILL=<run key>                   # one run key
make gate SKILL=eks-recon HARNESS=codex     # another harness
make gate-all                               # every run key with a runnable case
make gate-changed BASE=<commit>             # each run key changed between BASE and HEAD
make gate-stages                            # the deterministic stages only, no model call
```

`gate-changed` gates the run keys `run_task_evals.py --list-targets --changed-since <BASE>` prints: those with a file changed between `BASE` and `HEAD` under the skill folder, `misc/evals/<run key>/` or the `evals/` folder or `class.yaml` of one of its classes, each with a runnable case; a change to one of the gate's own files (`GATE_PATHS` in `scripts/run_task_evals.py`) gates every run key. A changed key with no runnable case is named on stderr as `<run key> changed but has no runnable case: not gated`, and a changed skill folder with no run key (no `misc/evals/<skill>` folder and no class target) as `skills/<skill> changed but has no run key: not gated`. Each key's old arm is the skill at `BASE`, its previous version; a skill absent there runs its task cases against `without_skill` and its trigger queries on `with_skill` alone (the triggering runner has no `without_skill` arm). When no key with a runnable case changed it gates nothing and exits 0.

`gate` runs the deterministic stages, then the evals. The stages are one ordered shell command list, the Makefile variable `GATE_STAGES` (class admission checks, schema validation, link check, size check, in that order); it is empty here, so `gate` prints that no stage is wired, and the changes that own those checks set it. The first stage that exits non-zero stops the gate before any model call. Then `run_task_evals.py` runs each case `regression.pass_k` times per arm; only when it exits 0, `run_triggering.py --run-key` runs each trigger query three times on `with_skill` and three times on the skill at the base ref (`base_skill`; a key with no trigger case skips it); and `regression.py --gate` scores both results. `SKILL` takes any run key `run_task_evals.py --list-targets` prints: a `misc/evals/<skill>` folder or a class target, each with at least one runnable case. Keys with no runnable case (listed on stderr by `--list-targets`, for example `setup`) are not gated.

What blocks (exit 2):

- A case that fails Pass@k: none of its k `with_skill` runs passed. A run passes only when it is valid and every grader expectation, process assertion and artifact check passed; an invalid run (for example no events, no init event, a non-zero exit or a timeout) never passes. One failed case fails the gate on its own, and a case that also fails on the base arm still blocks. A skill's own cases always block; a shared class case blocks only on a blocking target (`CLASS_TARGETS` in `run_triggering.py`: every skill whose SKILL.md frontmatter names the class, or a child of it, in `metadata.apex-classes`; no `devops-agent` copy is a target, since the copies are tested only inside a real DevOps Agent environment), and on a report-only target (the explicit list) it is listed without blocking.
- A pooled pass-rate drop past `THRESHOLD` points (rounded to 0.1), when the key has a blocking case: the `with_skill` mean less the base arm's mean, of the grader pass rate only (process and artifact checks count per case, above), with an invalid run scoring 0.
- A trigger query that fails on `with_skill`, or that ran fewer than three valid runs. A shared class query blocks only on a blocking target, as a shared task case does. So one invalid run of three fails a trigger query, while a task case passes Pass@k on a single valid run that passes. Under `gate` a class's shared negatives run in the key's one triggering call at the default threshold 0.5 (`run_triggering.py --trigger-threshold`; the Makefile passes none), so a shared negative that triggers on 1 run in 3 passes; the 0.01 call in classes/apex-base/evals/README.md is a separate hand run.
- A pooled triggering drop past `THRESHOLD` points (rounded to 0.1) against the skill at the base ref, when the key has a blocking query: the share of `with_skill` runs that triggered as expected (triggered on a should-trigger query, did not on a should-not one), averaged over the queries, less the same share on `base_skill`. The should-trigger and should-not shares pool into this one delta, so a gain on one can offset a loss on the other; a should-not query that fails still blocks on its own (above). A skill absent at the base ref is scored on `with_skill` alone.

Tokens and time per case and per skill are in the report and do not block: only pass rate blocks. Tokens per run are input plus output tokens as the runner's `token_usage` records them; a run with no token count records none, and a run with no recorded time records none, so neither pulls a mean down. `regression.py --gate` exits 1, never 0, when there is nothing to score (a runner error, a refused eval-role session or a run key with no runnable case) or the run had other than three runs per case on either arm or per trigger query on either arm (`pass_k` not 3, which the task runner's `--gate` also refuses before any model call, and the triggering stage then does not run), or a trigger query on the base arm had fewer than three valid runs (it would score as 0 and hide a drop); through `make`, any failure exits 2 (the log tells them apart). The report goes to stderr, to `gate-report.md` in the run key's workspace and, in GitHub Actions, to the job summary; per case it shows each arm's passes out of three, Pass@3, pass^3 and the mean tokens and time per run, per trigger query the runs that triggered on each arm, and a summary per arm.

The runs of one case on one arm run at the same time, one thread each, and the two arms run one after the other, so at most `pass_k` subjects, then at most `pass_k` graders, run at once per run key in the task stage; the triggering stage then runs up to `NUM_WORKERS` subjects at once (10 by default). Each run keeps its own sandbox, clean HOME, bubblewrap wall, `run-<k>` folder and `timing.json` (its own wall time and tokens); the runs share one eval-role session, refreshed by one run at a time. Process assertions and artifact checks run once every subject on the arm has ended, then the graders of the valid runs run side by side. A case should then take about as long as its slowest run, not the sum of its runs, for the same number of model calls; no eval run has measured that yet. A run that fails (a non-zero exit, an error in its stream, a throttled call the harness gives up on) or hangs until the subject or grader timeout is an invalid run or a grader failure of its own, and the other runs go on and are scored; the runner adds no retry or backoff. An error the runner cannot score, such as a refused eval-role refresh, stops the run once the other runs have ended. Records keep run order, so the report is the one a serial run of the same results gives. Running several run keys at once (`make task-all-parallel`) multiplies the runs in flight, and with them the Bedrock request rate.

A failed eval holds the merge line. The report's `Merge line` row reads `HELD: this pull request stays off the merge list until this gate passes` on a regression and when there is nothing to score (that report replaces any earlier one), else `not held by this gate`. The maintainer's host gate run is a step of each skill-changing pull request's review: its case and score table goes in the pull request body below the review, and the merge line stays held until the gate passes.

Runner flags the gate uses (`run_task_evals.py`):

| Flag | Default | Meaning |
|---|---|---|
| `--harness {claude,kiro,codex}` | `claude` | Subject harness, one adapter each; the grader is `claude -p` on every harness |
| `--base-ref REF` | `v1.3.0` | Git ref of the base arm; `none` runs `with_skill` against `without_skill` |
| `--subject-model ID` | `--model` on claude, else the harness's default | The subject's model; the grader keeps `--model` |
| `--runs N` | the skill's `regression.pass_k` | Runs per case and arm |
| `--list-targets` | | Prints one JSON line per run key with a runnable case (a `live_only` case counts only with `--include-live-only`) and exits; mints no credential, runs nothing. `blocking` covers shared class cases; own cases always block |
| `--changed-since REF` | | With `--list-targets`: only the run keys with a file changed between REF and `HEAD` (what `gate-changed` gates) |

`run_triggering.py` takes `--harness` too, plus `--class CLASS` (repeatable: adds that class's shared trigger cases from `classes/<class>/evals/trigger/triggering.json`, parents first, for a skill on the class's target list; a class with no such file is skipped with a message), `--runs-per-query` (default 3) and `--base-ref REF` (default `none`, or `v1.3.0` under `--run-key`, the form `gate` runs: also runs every query on the skill as it was at REF, read from git objects as the task runner does, printed under `base`; a skill absent there gets no base arm); `make triggering-<skill>` and `make task-<skill>` pass `HARNESS`, `SUBJECT_MODEL` and `BASE_REF`. `--eval-set` is needed unless `--class` is given. A triggering run that is invalid (for example no init event, a non-zero exit, a timeout or an error result) is left out of the trigger count. A query with no valid run fails on both the should and the should-not side, and a shared class should-not query fails when any of its runs is invalid.

Harnesses: `claude` (`claude -p`), `kiro` (`kiro-cli chat --no-interactive`) and `codex` (`codex exec --json`). The claude and codex subjects call Bedrock on the eval-role session. Kiro's model calls go to Kiro's own service, not to Bedrock on the eval role: a kiro subject uses the operator's existing kiro-cli sign-in (the runner passes its own `XDG_DATA_HOME`, else `~/.local/share`, where kiro-cli is assumed to keep it), or `KIRO_API_KEY` when that is set. So a kiro subject reads and writes the operator's kiro-cli data (its sign-in and chat history) and runs as the operator's Kiro identity. With no sign-in and no `KIRO_API_KEY`, every kiro run is invalid and the run still exits 0: check `kiro-cli whoami` first. CI does not run kiro and does not get a Kiro key. The kiro and codex adapters are built and tested on recorded output only, and no gate run has happened yet on any harness. On kiro and codex a multi-turn case runs as one turn, with no canned answers: today that is `eks-build` case 3, the one case with canned answers (`canned-multiturn`).

Before any run, both runners read each CLI's `--version` and compare it with `HARNESS_CLI_VERSIONS` in `run_triggering.py` (claude 2.1.328, codex 0.163.0, kiro-cli 3.5.0; `run_task_evals.py` also checks claude, its grader): any other installed version, or a missing CLI, stops the run with exit 2.

The CI job `eval-gate` in `.github/workflows/evals.yml` runs once per harness in its matrix (`claude` and `codex`), and only by hand (`workflow_dispatch`), reading the repository secrets `APEX_EVAL_AWS_CONFIG` (the `~/.apex-eval/aws-config` contents) and `APEX_EVAL_EXPECTED_ACCOUNT` (the eval account id). Without them the job fails at its first step, and a pull request from a fork gets no secrets, so it fails there too; there is no pass without them. On a dispatch it runs `gate SKILL=<input>` or `gate-all`. This repository gives GitHub no AWS sign-in, so the model-backed job stays dispatch-only and never runs on a pull request; live gate runs are local (`make -C misc/evals gate`). It must not be a required check while the `if:` is there, since GitHub counts a job that did not run as passing a required check.

`generate_eval_manifest.py --check` compares the committed `misc/website/static/manifests/evals.json` with a fresh build and exits 1 on a difference, writing nothing. Each manifest entry carries `tokens_per_run`, the `with_skill` mean tokens per run from the skill's latest task history row on the claude harness; it is null in every entry until a task run records tokens (the website shows "not recorded").

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
| `MODEL` | `global.anthropic.claude-opus-4-6-v1` | A Bedrock model or inference-profile ID: the grader on every harness, and the claude subject |
| `SUBJECT_MODEL` | empty: the runners' per-harness default (`MODEL` on claude, `HARNESS_SUBJECT_MODELS` in `run_triggering.py` on codex and kiro) | The subject's model (`--subject-model`). Codex on Bedrock takes OpenAI model IDs only; kiro takes a Kiro model ID (`kiro-cli chat --list-models`) |
| `RUNS_PER_QUERY` | `3` | ≥3 for meaningful confidence intervals |
| `NUM_WORKERS` | `10` | Parallelism for triggering runs |
| `RUNS_PER_PROMPT` | empty | Task eval runs per case and arm; empty uses the skill's `regression.pass_k` in `.skilleval.yaml` (3 when unset) |
| `HARNESS` | `claude` | Subject harness for `gate`, `gate-all`, `gate-changed`, `task-<skill>` and `triggering-<skill>`: `claude`, `kiro` or `codex` (the grader is `claude -p` on all three) |
| `BASE_REF` | empty (the task runner's `v1.3.0`; the triggering runner's `v1.3.0` under `--run-key`, as `gate` runs it, else `none`) | Git ref the base arm of `gate`, `task-<skill>` and `triggering-<skill>` takes the skill from (`gate-changed` sets it to `BASE`); `none` runs against `without_skill` (task) or no base arm (triggering), so `gate` with `none` fails (exit 2) on a run key with a trigger case, after its task and triggering stages ran: `regression.py --gate` needs the triggering base arm |
| `THRESHOLD` | `5` | Pooled pass-rate drop, in percentage points, that fails `regression` and the gate |

```bash
make triggering-all                                     # default: Bedrock Opus
make triggering-eks-best-practices RUNS_PER_QUERY=1     # cheap iteration
```

### Eval-role setup (`~/.apex-eval`)

Every eval run gets its AWS access from a short-lived session of one IAM role used only for evals, never from your own keys. Each subject runs as your OS user under bubblewrap (`bwrap`, required: without it no subject starts). Your home directory, the repo, the runner's temp directory (`tempfile.gettempdir()`, which follows `TMPDIR`), `/tmp` and your user runtime directory (`/run/user/<uid>` and `XDG_RUNTIME_DIR`, which hold the user session bus) read as empty, except the run's own sandbox and clean home (read-write), for a Kiro subject only the kiro-cli data folder (`$XDG_DATA_HOME/kiro-cli`, else `~/.local/share/kiro-cli`, read-write: the subject reads and writes your kiro-cli data, its sign-in and chat history; that kiro-cli keeps its sign-in there is assumed, since no kiro run has signed in under the wall yet; never the rest of `~/.local/share`, and not when that folder resolves to your home directory, `~/.local`, `~/.local/share`, an outermost walled folder (HOME, /tmp, the runtime dir; the repo or temp dir only when outside those) or a folder above one), the staged skill folder and the run's own harness CLI (read-only: the CLI's files and its interpreter's, plus an npm CLI's package folder or the folder another script shares with its interpreter, but never your home directory, `~/.local` or a folder above either) and any PATH dir the caller adds, such as the runner-trial T7 `aws` shim (read-only; not your home directory, `~/.local`, a walled folder or one above it, and otherwise not checked: a caller adds only a private dir it created); the container engine sockets (only `/run/docker.sock`, containerd's and a rootless docker's) read as `/dev/null`, and the subject gets a new session, so it cannot push input into your terminal itself. The rest of the host filesystem and the network are unchanged, so it is not a hard fence: the subject can still read and write, by path, what your OS user can elsewhere on the host (it reads `/etc`, writes `/var/tmp` and `/dev/shm`), and reach any network service the host can, the instance metadata service included (a session bus outside the runtime directory, such as an abstract socket, is reachable too). The subject gets its own process table (`--unshare-pid` and a fresh `/proc`), so it cannot list or signal host processes. The grader (`claude -p`, bypassPermissions, with a clean HOME and the eval-role environment) and the artifact validators a case configures (today terraform fmt and eks-build's validate_project.sh, which runs terraform validate when the subject wrote `.terraform`; the runner also supports terraform init and validate, checkov, shellcheck, markdownlint, kubectl and mmdc), with the runner's environment, run outside the wall as your OS user, on what the subject wrote, so a subject can run code there (a planted terraform provider) or steer the grader, and reach what the wall hides, ~/.aws included. For a hard fence, run the gate as another OS user that holds no keys. Do not run the gate as root or with a setuid-root bwrap: either way bwrap makes no user namespace. Before the first model call the runner assumes that role and checks the session with `sts get-caller-identity`. If anything below is missing or wrong it refuses to start, with no fallback.

- `~/.apex-eval/aws-config`: an AWS CLI config file with a `[profile apex-eval-admin]` section. It sets `region` (the Region the evals call Bedrock in) and a `credential_process` line that prints credentials allowed to assume the eval role, such as your organisation's sign-in helper.
- `~/.apex-eval/expected-account`: the 12-digit id of the eval account, on one line. The runner builds the role ARN from it and refuses a session in any other account.
- Role `apex-eval-bedrock-invoke` in that account. Its trust policy trusts the IAM principal that profile `apex-eval-admin` signs in as (its ARN, a role or an IAM user). Its permissions allow `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`. For a global inference profile, such as the default model, allow the profile ARN, the model in your Region and `arn:aws:bedrock:::foundation-model/<model>` (Amazon Bedrock User Guide, [Global cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/global-cross-region-inference.html)). Claude Code's [Amazon Bedrock IAM configuration](https://code.claude.com/docs/en/amazon-bedrock#iam-configuration) also lists `bedrock:ListInferenceProfiles`, `bedrock:GetInferenceProfile` and two `aws-marketplace` subscription actions. For live-cluster evals the role also allows the AWS read actions in `setup/readonly-session-policy.json`, the read set the live prompts call: the `Describe*`, `List*` and `Get*` actions that file lists for EKS, EC2, IAM, CloudFormation, Auto Scaling, Elastic Load Balancing, CloudWatch and CloudWatch Logs, plus `logs:FilterLogEvents` and `sts:GetCallerIdentity`. Its `eks:Describe*` and `eks:List*` cover `eks:DescribeCluster` and `eks:ListClusters`, what `aws eks update-kubeconfig` needs ([Amazon EKS identity-based policy examples](https://docs.aws.amazon.com/eks/latest/userguide/security-iam-id-based-policy-examples.html)). Kubernetes reads go only through the read-only kubeconfig (`KUBECONFIG_RO`, from `setup/bootstrap-readonly.sh`): a ServiceAccount token with get, list and watch and no Secrets, a credential separate from the role. The runner trial's C1 driver gives its live case its reads another way (misc/runner-trial/cases.md, T7), and the grants the trial added to this role, with their expiry, are in misc/runner-trial/cases.md, Credentials and permissions. The role has no build rights: no IAM action that creates, changes or deletes cluster resources.
- `CLAUDE_CODE_USE_BEDROCK=1` (the Makefile sets it for `PROVIDER=bedrock`), so `claude -p` sends its model calls through Bedrock on that session.

AWS caps a role-chained session at one hour, so a subject or grader timeout plus 120 seconds must stay under 3600 seconds.

## Adding evals for a new skill

Contributors only need to author `triggering.json`. Maintainers run the full eval suite after merge. The merge gate (see "Merge gate") runs only by hand, before merge: on the maintainer's host, or through the dispatch-only `eval-gate` job in `.github/workflows/evals.yml`, which needs the eval secrets.

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
