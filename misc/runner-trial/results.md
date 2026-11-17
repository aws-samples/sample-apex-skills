# Runner trial: results

Repo line cites are at commit 7efa0776.

## Status

No paid run has happened. The runs wait on the maintainers' spend decision for the paid runs (cost-estimate.md: $43.12 to $141.13). They also wait on a subject credential limited to the model calls, since the subject can use whatever AWS credentials the host holds (cases.md, Credentials and permissions). Until both are given, these sections hold that line, except the cost per pull request, which is estimated now:

- Results per candidate (score-sheet.md S1 to S10): waits on the maintainers' spend decision and a subject credential limited to the model calls.
- The runner pick, with its reasons from S2, S6 and S10: waits on the maintainers' spend decision and a subject credential limited to the model calls.
- The eval gate's cost per pull request: estimated now, re-measured from S2, S6 and S10 after the runs: C1 claude harness $19.79 to $44.64 per pull request (subject $16.19 to $30.24 plus 36 grader calls); C2 $11.01 to $25.58; C3 adds $2.85 to $34.82 to the runner that drives the subject (72 judged evaluations, cost-estimate.md, C3); each figure holds if the gate runs all seven cases on each pull request.
- Spend against the estimate: $0 of $43.12 to $141.13.

The shared prompt-injection case is not in this trial: it is built later, on the runner this trial picks.

Everything below is settled without a paid run.

## How the trial grades

Each case is graded on its own single pass condition (cases.md). That condition is checked by the candidate's own grader, and where it is mechanical by a script as well: T3 runs validate_project.sh, T4 and T1 read the verdict, and T6 reads which Skill loaded. The trial does not use the SREGym LLM judge. SREGym's judge grades an incident diagnosis against a root cause, and the trial's cases are our skills' own prompts with our own expectations (sregym-feasibility.md, section 4).

## Extending the homegrown runner (C1), sized

The trial drives C1 from a separate script, misc/runner-trial/drive_c1.py, so the runner code is not changed here. The driver itself does two of the pieces below, old against new (git archive of tag v1.3.0; both arms run, no comparison written) and three runs; the rest of the table is sized, not built. Building the extension for real touches these files (misc/evals/scripts/ unless noted):

| Piece | Files | What changes | Size |
|---|---|---|---|
| Old against new | run_task_evals.py (`run_skill` :764, `run_subject` :415) | a second skill path per case (the skill at a given tag, staged from `git archive`), a third config beside `with_skill` and `without_skill`, and the comparison written into the benchmark | 1 file changed |
| Three runs per case | misc/evals/Makefile (`RUNS_PER_PROMPT ?= 1` at :65, passed as `--runs` at :265) | default 3 for scored runs; the option exists (`--runs`, run_task_evals.py:997) | 1 line in 1 file |
| Kiro and Codex adapters | run_task_evals.py (command at :473-482, Popen at :483), elicitation.py (`run_multiturn_subject` :148), run_triggering.py (`run_single_query` :322, `stage_skill_sandbox` :74, `build_subprocess_env` :121), parse_trajectory.py (`parse_events` :141, token keys :21-33), the evals.json process assertions (Claude tool names; process_assertions.py:91 compares them), a new harness module, and a Makefile HARNESS variable | each harness gets its own command line, its own skill staging (Kiro reads `~/.kiro/skills/` and the workspace `.kiro/skills/` (kiro.dev/docs/skills/); Codex reads skills from `.agents/skills` under the working directory and repo root, `$HOME/.agents/skills` and `/etc/codex/skills` (Codex docs, Skills, read 2026-11-16), so the adapter stages each skill at `<sandbox HOME>/.agents/skills/<skill>/`), its own event parser for JSON Lines output (`kiro-cli chat --output-format stream-json`, `codex exec --json`), and a tool-name map so the process assertions read the same on every harness | 5 files changed, 1 new module, 1 Makefile variable |
| Clean credentials per run | run_triggering.py (`stage_skill_sandbox` :92-94 and `stage_empty_sandbox` :112-114 both link the host ~/.aws into the sandbox HOME; the second serves the without_skill arm, run_task_evals.py:441, and the grader, :604) | the existing `--aws-session-policy` mode (run_task_evals.py:1034-1047, a GetFederationToken session) covers only the subject, needs long-term access keys, leaves the ~/.aws link in place and does not cover the grader (:604-605); the change is to drop the ~/.aws link when a scoped mode is on, apply it to the grader, and take credentials that do not need long-term keys | 2 files changed |
| Nonzero exit on a failed case | run_task_evals.py (`main` return at :1080) | a C1 pick needs exit 1 when a case fails, not only on a suite error (score sheet S7) | 1 line in 1 file |
| Spans for C3 | a new module beside parse_trajectory.py | a new module beside parse_trajectory.py that converts each run's events.jsonl into OpenInference spans (scope `openinference.instrumentation.<name>`, `openinference.span.kind`, `input.value`/`output.value`), the shape AgentCore's generic framework support reads. AgentCore reads a span only when its scope starts with `opentelemetry.instrumentation.` or `openinference.instrumentation.` and it carries an identifying attribute (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/supported-frameworks-generic.html, read 2026-11-16), and it lists the Claude Agent SDK (`openinference.instrumentation.claude_agent_sdk`), not the Claude Code CLI the runner calls. Claude Code's own OpenTelemetry export does not fill the gap: it exports traces only with `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` and `OTEL_TRACES_EXPORTER` set, names its meter `com.anthropic.claude_code` and documents no instrumentation scope and no OpenInference attributes (https://code.claude.com/docs/en/monitoring-usage, read 2026-11-16) | 1 new module and its test |

## Moving the runner's dependencies out of the vendored folder

Facts:
- No runner code of ours sits in skills/skill-creator/. The eval tooling calls six pieces in it. Four are live: `scripts/quick_validate.py` (misc/evals/Makefile:118, misc/evals/scripts/run_all_evals.py:98), `scripts.aggregate_benchmark` (Makefile:155), `agents/grader.md` (misc/evals/scripts/run_task_evals.py:71) and `scripts.package_skill` (Makefile:175, which itself imports `scripts.quick_validate`). Two are on targets the Makefile marks orphaned: `scripts.generate_report` (Makefile:159-168) and `eval-viewer/generate_review.py` (Makefile:177-184).
- skills/skill-creator/ is vendored (it holds .vendor-sha, 1780c5e5). .github/scripts/vendored-guard.sh:2-5 fails any pull request that edits a vendored folder unless it is a vendor sync, and "the next sync overwrites local edits". So those pieces can change under the runner at any sync, and we cannot fix them in place.

Recommendation: if C1 is picked, copy the four live pieces into misc/evals/scripts/ once, each with the vendored sha it was copied from, a copy of skills/skill-creator/LICENSE.txt and an entry in THIRD_PARTY_NOTICES.md, and point the Makefile, run_all_evals.py and run_task_evals.py at the copies. skills/skill-creator/ stays vendored and unchanged; a later sync then changes nothing under the live runner, and the two orphaned targets still read the vendored folder until they are removed. A change to a copy modifies Apache 2.0 code: each changed file carries a prominent change notice (Apache 2.0 section 4(b)), and THIRD_PARTY_NOTICES.md:5 is updated in the same change. If C2 is picked, the runner is retired and no move is needed. If C3 is picked, C1 or C2 still runs the subject and C3 grades it. No file is moved in this trial.

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
