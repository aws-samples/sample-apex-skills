# Runner trial: results

Repo line cites are at commit 7efa0776.

## Status

The trial ran in part on 2026-11-20 and has not passed: score-sheet.md's pass needs every cell filled, and several read "not run" or "cannot run" below. No runner is picked. The run outputs are kept on the operator's host, not in the repo; each figure below names its out dir and file.

What stopped it, each needing an action only the maintainers can take:
- The eval-role session could not be renewed: the sign-in behind profile `apex-eval-admin` refused the renewal at 07:53:31Z (the identity provider rejected the refresh as `used_too_late`), so the driver stopped at that renewal, as designed ("eval-role session refused or failed to refresh, stopping", `c1-full-stderr.txt`), and C2 stopped before its third suite. T3's other arms, T4 to T6 on C1 and T2, T3 and T6 on C2 did not run. They need a fresh sign-in and a re-run.
- T7 (C1): ran, 6 of 6 runs on one minted session (Runs, below). No run read "mint it again", so no re-mint was needed.
- T7 (C2): cannot run on this host. Given the same minted session as C1 (a temp kubeconfig and an `aws` shim carrying only that session), the subject still had no shell: `claude plugin eval` grants a shell tool only with a sandbox backend, which is not installed on the operator's host (Findings, below).
- Codex: the eval role is refused `bedrock:InvokeModel` on the `us.openai.gpt-5.6-sol` inference profile (HTTP 401, `codex-t1-20261120T0730Z/T1/codex_with_skill/run-1/events.jsonl`). It needs a policy change in the eval account.
- C3: the eval role is refused `bedrock-agentcore:Evaluate` (AccessDeniedException, `c3-onecall-20261120T0830Z/evaluate-stderr.txt`), so the one-call check of whether Evaluate scores spans never ingested (score-sheet.md) did not settle. It needs a policy change in the eval account.

## Runs

The gate: `CLAUDE_CODE_USE_BEDROCK=1 python3 misc/runner-trial/drive_c1.py --case T4 --paid --out <new dir> --spend-limit-usd 0.01` (cost-estimate.md, Gate) stopped after its first subject run, which recorded $0.5404 (`gate-20261120T0630Z/runs.jsonl:1`). The gate passed. That run failed T4's pass condition (below).

C1, claude harness: one invocation, `--case T1` to `--case T6`, `--spend-limit-usd 95` (`c1-full-20261120T0700Z/runs.jsonl`, 21 runs; no summary.json, since the stop ends the invocation before it is written). Pass count, subject cost and wall time per arm:

| Case | Arm | Pass | Subject cost | duration_ms per run |
|---|---|---|---|---|
| T1 | with_skill | 3/3 | $1.28 | 44160, 38835, 41760 |
| T1 | without_skill | 3/3 | $0.41 | 21559, 22141, 20894 |
| T1 | old_skill | 3/3 | $0.77 | 37784, 42917, 35228 |
| T2 | with_skill | 3/3 | $3.03 | 137360, 117130, 192056 |
| T2 | without_skill | 0/3 | $0.67 | 35373, 38983, 36158 |
| T2 | old_skill | 0/3 | $2.36 | 88504, 108016, 98199 |
| T3 | with_skill | 3/3 | $10.23 | 514210, 755148, 1023680 |
| T4 | with_skill | 0/1 (gate run only) | $0.54 | 104001 |

C1, T7 on its own: `--case T7 --paid --spend-limit-usd 15 --kubeconfig <read-only kubeconfig> --cluster-credentials <minted file>`, run right after one mint whose `expiration` printed as `2026-11-20T11:01:10+00:00`, the CLI's ISO form, which the driver parsed (`c1-t7-20261120T1003Z/runs.jsonl`, `summary.json`: subject cost $5.259). All six runs started inside that one session.

| Case | Arm | Pass | Subject cost | wall_seconds per run |
|---|---|---|---|---|
| T7 | with_skill | 0/3 (grader 3/4 each) | $4.53 | 267.8, 250.66, 248.15 |
| T7 | without_skill | 0/3 (grader 3/4 each) | $0.73 | 67.36, 54.56, 86.12 |

Kiro, T1 with the skill, three runs by hand, graded by C1's grader: 3/3 (`kiro-t1-20261120T0715Z/runs.jsonl:1-3`). Each run had a new HOME holding only the skill at 7efa0776 in `~/.kiro/skills/` and a workspace holding only the three fixtures, run as `kiro-cli chat --no-interactive --output-format stream-json --trust-tools=fs_read --trust-workspace <prompt>`. Each run read the staged SKILL.md (its events.jsonl). `--trust-all-tools` was refused by the operator's permission check, so Kiro could read but not run the skill's offline scripts; its runs are narrower than C1's. Kiro bills to its own subscription, with no AWS charge.

Codex, T1: cannot run (above); its first run stopped the arm, at no cost.

C2, `claude plugin eval` 2.1.328, one wrapper per skill at 7efa0776, `--model global.anthropic.claude-opus-4-6-v1 --no-publish --ablation with-without --runs 3 --scaffold`, under one $60 ceiling across the calls (`c2-run-20261120T0820Z/c2-ledger.jsonl`):

| Case | With | Without | Cost | Out file |
|---|---|---|---|---|
| T1 | 2/3 (two runs hit the 900 s case timeout; one of them still passed) | 3/3 | $2.36 | eks-security.json |
| T4 | 0/3 | 1/3 | $2.39 | eks-upgrade-check.json |

A first T4 call (`c2-20261120T0800Z/eks-upgrade-check.json`, $0.10) had every subject fail with "Could not load AWS credentials": `claude plugin eval` loads the user's Claude Code settings, and an AWS profile set there overrode the eval-role session; its judge calls may have run on that profile. The calls above ran with `CLAUDE_CONFIG_DIR` set to an empty dir, so no user setting applied.

C3: cannot run (above).

## Findings

- **T4 fails on the skill at 7efa0776, on both runners.** The gate's run rated the cluster 87, GOOD, with "No blockers identified": it read the hard blocker for subnet IPs as the total over all subnets (3 + 12 = 15), not per subnet, so subnet-aaa with 3 IPs was a medium warning (`gate-20261120T0630Z/T4/with_skill/run-1/grading.json`). C2's three with-skill runs also failed T4's pass condition (0/3). The case's pass rests on the EKS Best Practices Guide's five-IP rule per subnet (cases.md, T4); the skill's scoring text needs a fix.
- **T7 fails on its IaC expectation in all six runs, with the skill and without.** Each grading.json fails only "The output identifies the IaC tool managing the cluster" (`c1-t7-20261120T1003Z/T7/<arm>/run-<n>/grading.json`). T7's prompt (misc/evals/eks-recon/evals.json, id 1) asks the skill to "focus on version info, compute strategy, and addon inventory", and the with-skill runs ran only those modules, reporting `iac` as not in scope. The case's prompt and its fourth expectation disagree; the expectations still carry "TODO: human review". The other three expectations passed in every run.
- **C2 gives no shell on a host without a sandbox backend.** A call that grants Bash refuses each run before it starts ("Refusing to start without a working sandbox", bubblewrap and socat not installed), and a call that grants only pattern-scoped Bash rules (`Bash(kubectl get:*)` and the like) runs with no shell at all: T7's six C2 runs ($6.76, `c2-t7-20261120T1012Z/eks-recon-t7.json`) made no Bash call: five reported "No shell execution or MCP tools available", the sixth listed the commands for the user to run, and each scored 0 of 4. So T3 and T7 cannot run on C2 on this host until a sandbox backend is installed.
- **T1 passes without the skill** on both runners (C1 3/3, C2 3/3), so T1's single pass condition does not separate the arms.
- **T2 separates the arms**: with the skill 3/3, without 0/3, and the v1.3.0 skill 0/3 on C1.
- **T3's cost is above its basis**: $2.64 to $4.48 per with-skill run against the measured $0.831 to $1.211 (cost-estimate.md, Per-run basis). Re-stated at the highest measured run, T3 is about $30 against $10.32, and the total stays under the $205 budget. T1's runs ($0.135 to $0.472) sit inside its assumed $0.30 to $0.80 or below it; T4's one run ($0.54) is above its $0.309.

## Spend

$24.14 recorded: the gate $0.5404, C1 $18.7426 (subjects only), C2 $4.8527 (subjects and judge, the $0.10 first call included), Codex and C3 $0. Grader calls record no cost: 13 were made (C1's 9 on T1, the gate's 1, Kiro's 3), at the assumed $0.10 to $0.40 each, $1.30 to $5.20.

- The eval gate's cost per pull request: estimated, not yet re-measured: C1 claude harness $19.79 to $44.64 for a pull request that adds a skill, which runs with and without the skill (subject $16.19 to $30.24 plus 36 grader calls), and $23.55 to $50.42 for one that changes a skill, which runs it against its previous version (the old arm priced at the with-skill rate, as in cost-estimate.md: subject $19.95 to $36.02 plus 36 grader calls); C2 $11.01 to $25.58 for six cases (T5 cannot run; C1 without T5: $13.41 to $34.58); C3 adds $2.85 to $34.82 to the runner that drives the subject (72 judged evaluations, cost-estimate.md, C3). Each figure is one gate pass of the trial's cases (seven; six for C2 and for C1 without T5), three runs each, not of main's 93 task cases (misc/evals/*/evals.json at 528dde41, _template left out), and holds if the gate runs those cases on each pull request.

The shared prompt-injection case is not in this trial: it is its own eval piece (classes/apex-base/evals/injection/), built on the runner this trial picks.

Everything below is settled without a paid run.

## How the trial grades

Each case is graded on its own single pass condition (cases.md). That condition is checked by the candidate's own grader, and where it is mechanical by a script as well: T3 runs validate_project.sh, T4 and T1 read the verdict, and T6 reads which Skill loaded. The trial does not use the SREGym LLM judge. SREGym's judge grades an incident diagnosis against a root cause, and the trial's cases are our skills' own prompts with our own expectations (sregym-feasibility.md, section 4).

## Extending the homegrown runner (C1), sized

The trial drives C1 from a separate script, misc/runner-trial/drive_c1.py, so the runner code is not changed here. The driver itself does two of the pieces below, old against new (git archive of tag v1.3.0; both arms run, no comparison written) and three runs, and it holds the span converter for C3 (Spans for C3, below); the rest of the table is sized, not built. Building the extension for real touches these files (misc/evals/scripts/ unless noted):

| Piece | Files | What changes | Size |
|---|---|---|---|
| Old against new | run_task_evals.py (`run_skill` :764, `run_subject` :415) | a second skill path per case (the skill at a given tag, staged from `git archive`), a third config beside `with_skill` and `without_skill`, and the comparison written into the benchmark | 1 file changed |
| Three runs per case | misc/evals/Makefile (`RUNS_PER_PROMPT ?= 1` at :65, passed as `--runs` at :265) | default 3 for scored runs; the option exists (`--runs`, run_task_evals.py:997) | 1 line in 1 file |
| Kiro and Codex adapters | run_task_evals.py (command at :473-482, Popen at :483), elicitation.py (`run_multiturn_subject` :148), run_triggering.py (`run_single_query` :322, `stage_skill_sandbox` :74, `build_subprocess_env` :121), parse_trajectory.py (`parse_events` :141, token keys :21-33), the evals.json process assertions (Claude tool names; process_assertions.py:91 compares them), a new harness module, and a Makefile HARNESS variable | each harness gets its own command line, its own skill staging (Kiro reads `~/.kiro/skills/` and the workspace `.kiro/skills/` (kiro.dev/docs/skills/); Codex reads skills from `.agents/skills` under the working directory and repo root, `$HOME/.agents/skills` and `/etc/codex/skills` (Codex docs, Skills, read 2026-11-16), so the adapter stages each skill at `<sandbox HOME>/.agents/skills/<skill>/`), its own event parser for JSON Lines output (`kiro-cli chat --output-format stream-json`, `codex exec --json`), and a tool-name map so the process assertions read the same on every harness | 5 files changed, 1 new module, 1 Makefile variable |
| Nonzero exit on a failed case | run_task_evals.py (`main` return at :1080) | a C1 pick needs exit 1 when a case fails, not only on a suite error (score sheet S7) | 1 line in 1 file |
| Spans for C3 | misc/runner-trial/drive_c1.py (`events_to_spans`), tested in misc/tests/test_drive_c1.py (`Spans`) | built in this trial as a pure function that converts each run's events.jsonl into OpenInference spans labelled with the Claude Agent SDK scope `openinference.instrumentation.claude_agent_sdk` (`openinference.span.kind`, `input.value`/`output.value`). AgentCore reads a span only when its scope starts with `opentelemetry.instrumentation.` or `openinference.instrumentation.` and it carries an identifying attribute (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/supported-frameworks-generic.html, read 2026-11-16), and it lists the Claude Agent SDK (`openinference.instrumentation.claude_agent_sdk`), not the Claude Code CLI the runner calls. Claude Code's own OpenTelemetry export does not fill the gap: it exports traces only with `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` and `OTEL_TRACES_EXPORTER` set ("To enable it, set both `CLAUDE_CODE_ENABLE_TELEMETRY=1` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, then set `OTEL_TRACES_EXPORTER` to choose where spans are sent", read 2026-11-17), names its meter `com.anthropic.claude_code` and documents no instrumentation scope and no OpenInference attributes (https://code.claude.com/docs/en/monitoring-usage, read 2026-11-16). The function makes no AWS call and nothing calls it yet: a C3 run passes its output as `evaluationInput.sessionSpans` | 1 function and its tests, built |

## Moving the runner's dependencies out of the vendored folder

Facts:
- No runner code of ours sits in skills/skill-creator/. The eval tooling calls six pieces in it. Four are live: `scripts/quick_validate.py` (misc/evals/Makefile:118, misc/evals/scripts/run_all_evals.py:98), `scripts.aggregate_benchmark` (Makefile:155), `agents/grader.md` (misc/evals/scripts/run_task_evals.py:71) and `scripts.package_skill` (Makefile:175, which itself imports `scripts.quick_validate`). Two are on targets the Makefile marks orphaned: `scripts.generate_report` (Makefile:159-168) and `eval-viewer/generate_review.py` (Makefile:177-184).
- skills/skill-creator/ is vendored (it holds .vendor-sha, 1780c5e5). .github/scripts/vendored-guard.sh:2-5 fails any pull request that edits a vendored folder unless it is a vendor sync, and "the next sync overwrites local edits". So those pieces can change under the runner at any sync, and we cannot fix them in place.

Recommendation: if C1 is picked, copy the four live pieces into misc/evals/scripts/ once, each with the vendored sha it was copied from, a copy of skills/skill-creator/LICENSE.txt and an entry in THIRD_PARTY_NOTICES.md, and point the Makefile, run_all_evals.py and run_task_evals.py at the copies. skills/skill-creator/ stays vendored and unchanged; each sync after the copy then changes nothing under the live runner, and the two orphaned targets still read the vendored folder until they are removed. A change to a copy modifies Apache 2.0 code: each changed file carries a prominent change notice (Apache 2.0 section 4(b)), and THIRD_PARTY_NOTICES.md:5 is updated in the same change. If C2 is picked, the runner is retired and no move is needed. If C3 is picked, C1 or C2 still runs the subject and C3 grades it. No file is moved in this trial.

## SREGym for EKS

The feasibility note is sregym-feasibility.md.

## Sources read for this trial (2026-11-16)

- This repo at 7efa0776, paths cited inline.
- EKS Best Practices Guide, aws/aws-eks-best-practices at edc514fac86518b50129401c0cffd1f7981d7ec5 (latest/bpg/).
- AWS Price List (GetProducts): AmazonBedrockFoundationModels (Claude Opus 4.6, Claude Haiku 4.5, OpenAI GPT-5.6 Sol, us-west-2), AmazonBedrockAgentCore (us-west-2), AmazonEC2 (NAT Gateway, gp3, m7i.2xlarge, US West (Oregon)), AWSDataTransfer (US West (Oregon)), AmazonEKS (US West (Oregon)).
- https://aws.amazon.com/bedrock/agentcore/pricing/ and https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_Evaluate.html.
- AgentCore developer guide: getting-started-on-demand.html, supported-frameworks-telemetry.html, supported-frameworks-generic.html, ground-truth-evaluations.html and skill-evaluators.html, under https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/.
- Codex docs, Skills (https://developers.openai.com/codex/skills, which redirects to https://learn.chatgpt.com/docs/build-skills); https://kiro.dev/docs/skills/ and https://kiro.dev/pricing; https://code.claude.com/docs/en/monitoring-usage.
- `claude plugin eval --help`, `claude plugin validate`, `kiro-cli --help`, `codex exec --help`, run with no model call.
- Docs and source for the SREGym note, listed in its Sources table.
