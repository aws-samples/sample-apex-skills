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

Scored eval runs are maintainer-run: you run them locally when a skill changes and commit the updated scores. A deterministic hygiene pre-flight (`check_hygiene.py`, wired into CI via `.github/workflows/evals.yml`) runs on every PR that touches `misc/evals/**` or `skills/**`. The scored and coverage layers stay maintainer-run and out of CI for now, pending proper eval automation.

### Step 0: Host setup (once per host)

Every `claude -p` the runners start (subject, each multi-turn turn, grader) runs in its own transient systemd unit as the system user `apex-eval`, with an empty `/home`, no cluster credential and a fresh Bedrock-only role session per launch (`scripts/confined.py`). Before the first run:

1. The host must be an EC2 instance with IMDSv2 reachable (the runner reads the instance's public IPv4 there, so the units cannot reach it), and the AWS CLI (`aws`) must be on PATH. The runners check both before any session is minted, and refuse to start with a named error if either fails.
2. Install the boundary, as root from a normal shell (the runners never run it): `sudo bash misc/evals/setup/install-eval-boundary.sh`. It adds the `apex-eval` user, `/var/lib/apex-eval` and a root-owned copy of your `claude` under `/opt/apex-eval/bin`. After a `claude` upgrade, rerun it with `--refresh-bin`; `--uninstall` undoes it.
3. Give the user who runs the evals passwordless sudo for `sudo -n true`, `sudo -n systemd-run` and `sudo -n systemctl kill`. The install script does not grant it, and the runners refuse to start without it. The grant is root-equivalent for that user (`systemd-run` can start any command as root), so give it only on a dedicated eval host.
4. Create the role the units use, `apex-eval-bedrock-invoke`, in the account that pays for the evals. `setup/eval-bedrock-invoke-trust.json` and `setup/eval-bedrock-invoke-permissions.json` are a documented example of its two policies: replace `<ACCOUNT_ID>` with that account's id and `<ADMIN_ROLE>` with the role of the admin session in item 5 (with its path, if it has one), and change `us-west-2` in the ARNs if you set another Region. The runner builds the role's ARN at run time, from the account that `aws sts get-caller-identity` reports for the item 5 profile, so every run is Bedrock-only and billed to that one account.
5. Write `~/.apex-eval/aws-config` (the install script does not create it) with a profile `apex-eval-admin` whose credentials may call `sts:AssumeRole` on that role, for example through `credential_process`:

   ```ini
   [profile apex-eval-admin]
   region = us-west-2
   credential_process = <command that prints a credential_process JSON for that principal>
   ```

   The runner reads only this file (never `~/.aws`), mints each unit's session from it, and passes the session to the unit in a 0600 env file, never in argv. Three optional environment variables change the names and the Region used here: `APEX_EVAL_ROLE_NAME` (default `apex-eval-bedrock-invoke`), `APEX_EVAL_PROFILE` (default `apex-eval-admin`) and `APEX_EVAL_REGION` (default `us-west-2`).
6. `/etc/resolv.conf` must name a nameserver the unit can reach: the runner allows only the first IPv4 `nameserver` there and refuses a loopback one.
7. The units always hide `/var/log`. List any other path on this host that a unit must not see (another service's data under `/var/lib`, for example), one absolute path per line, in `~/.apex-eval/inaccessible-paths`. No file means no extra path. Anything world-readable that is not listed stays readable to a unit (`ProtectSystem=strict` makes it read-only, not hidden).

Launches run one at a time on the whole host (a host-wide lock), read-back and cleanup units included, so `NUM_WORKERS` and `task-all-parallel` only queue them, and a run set takes as long as its launches added together. Prompts marked `live_only` are always off: no unit gets a cluster credential, and `--include-live-only` is refused.

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

## Model configuration

Runs reach Bedrock only (Step 0), so `MODEL` is a Bedrock inference-profile ID.

| Variable | Default | Notes |
|---|---|---|
| `MODEL` | `global.anthropic.claude-opus-4-6-v1` | Bedrock inference-profile ID |
| `RUNS_PER_QUERY` | `3` | ≥3 for meaningful confidence intervals |
| `NUM_WORKERS` | `10` | Triggering worker processes; launches still run one at a time (Step 0), so workers only queue them |
| `RUNS_PER_PROMPT` | `1` | Task eval runs per prompt (3 for stddev) |

```bash
make triggering-all                                     # default: Bedrock Opus
make triggering-eks-best-practices RUNS_PER_QUERY=1     # cheap iteration
```

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
