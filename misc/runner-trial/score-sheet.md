# Runner trial: score sheet (pass or fail)

Repo line cites are at commit 7efa0776.

The sheet compares three candidate runners on the same seven cases (cases.md). No row needs a runner to win, and the sheet picks none: the pick is written in results.md.

What "pass" means: the trial passes when every cell S1 to S10 is filled for all three candidates (a measured value, a value read from the tool or code where the cell says so, the S10 estimate, 'cannot run (why)' or 'n/a (why)'), and results.md states the pick with its reasons from S2, S6 and S10; otherwise it fails. A case's own pass is its condition in cases.md, counted per run in S2.

Candidates C1 to C3: README.md. C1's extension is sized, not built, in this trial (results.md), except two pieces the trial's driver does itself (old against new by git archive, and three runs); C2 is `claude plugin eval` in Claude Code 2.1.325.

## Grid

Every C1, C2 and C3 cell not filled below waits on the maintainers' spend decision and a subject credential limited to the model calls. The remaining cells read "pending".

| Row | Measured | Cell values | How it is filled | C1 | C2 | C3 |
|---|---|---|---|---|---|---|
| S1 | each case T1 to T7: did the runner execute it as written | ran / cannot run (why), per case | from the run log of the first run of each case | pending | pending; T5 cannot run (C2 cases, below) | n/a: needs a subject runner (C3 runs no agent, cost-estimate.md, C3) |
| S2 | each case: pass count out of 3 runs, with the skill and without | n/3, n/3, or n/a (cannot run, see S1), per case | count of runs meeting the case's pass condition (cases.md); T6 has one arm (drive_c1.py summary.json `both_queries`); T7: a run whose cluster reads fail is re-marked cannot run by hand first (cases.md T7), then the same-answer result (same-answer-rule.md) is worked out by hand from <out>/T7/<arm>/run-1..3: the driver saves no live snapshot, so each run's live values are read from its own tool output in its transcript, and a field whose tool output differs between two runs is the rule's skipped field; a run marked cannot run has no run dir, so any pair holding it reads cannot compare | pending | pending | pending |
| S3 | old against new on T1 to T4 | supported (how) / not supported | from the old-against-new runs of T1 to T4; "how" names the mechanism; for C1, scored on the shipped runner, not on the trial's driver; the driver's git-archive arm is named in "how" | pending | not supported (`--ablation` offers only none or with-without) | pending |
| S4 | three runs per case with no hand work | yes / no | yes if one command or config gives 3 runs of every case; for C1, scored on the shipped runner (`--runs 3`, one command per suite), not on the trial's driver script (misc/runner-trial/drive_c1.py, which drives the runner's functions one case and arm at a time) | pending | yes (`--runs`, default case.runs ?? 3) | pending |
| S5 | which harnesses it drives (Claude Code, Kiro, Codex) | list | the harnesses the runner itself drove T1 on; for C1 the Kiro and Codex T1 runs are driven by hand (adapters sized, not built) and are recorded as adapter evidence, not as harnesses C1 drives | pending | pending | n/a: needs a subject runner (C3 runs no agent, cost-estimate.md, C3) |
| S6 | tokens and wall time recorded per case | yes (field name) / no | the field in the runner's output that holds each | yes (`token_usage` misc/evals/scripts/run_task_evals.py:972, `duration_ms` :302) | pending | pending |
| S7 | a nonzero exit on a failed case, usable as a CI gate | yes (flag) / no | run a case set where one case fails, read the exit code | no as shipped (exit 1 only on a suite error, not a failed case, misc/evals/scripts/run_task_evals.py:1080), confirmed at run | yes (`--threshold`, exit 1 below threshold), confirmed at run | pending |
| S8 | what leaves the host (reports, traces, published pages) | list | read the runner's output and network targets during T1 and T7 | pending | pending | pending |
| S9 | setup needed before the first run (accounts, services, mocks) | list | everything done before S1's first run | the read-only kubeconfig for T7 (cases.md, T7); Kiro CLI and Codex CLI installed and signed in for the hand-driven T1 runs; a subject credential limited to the model calls (cases.md, Credentials and permissions) | a plugin wrapper per skill outside the repo and a `case.yaml` per case (C2 cases, below); the read-only kubeconfig for T7; the same subject credential as C1 | the on-demand Evaluate API in us-west-2; a converter from C1's events.jsonl to OpenInference spans (results.md, Spans for C3); a subject runner, C1 or C2 |
| S10 | the trial's own cost, estimated before it is spent | (runs plus judge calls) x a per-run figure | cost-estimate.md | $26.21 to $58.80 (claude harness), plus Kiro $0.30 to $1.20 and Codex $1.80 to $9.12 | $11.01 to $25.58 | $3.80 to $46.43 |

S10 is the trial's own cost only. The eval gate's cost per pull request is worked out in results.md from S2, S6 and S10.

Beside S5: Kiro and Codex T1 runs driven by hand are not comparable with runs through a built adapter, so they show only that each harness can run the skill headless.

## Facts settled before the runs

- **Adapters.** C1's Kiro and Codex adapters are sized, not built, in this trial: the files are in results.md. Kiro CLI 3.3.0 has a headless mode (`kiro-cli chat --no-interactive`, `--output-format stream-json`), and Codex CLI 0.163.0 has one (`codex exec --json`). Both are driven directly for T1.
- **C2 target.** `claude plugin validate` rejects a bare skill folder (`claude plugin validate <skill dir>` prints "No manifest found in directory. Expected .claude-plugin/marketplace.json or .claude-plugin/plugin.json" and exits 1); `claude plugin eval` accepts a path, but the trial uses a wrapper so validate and eval read the same manifest. A wrapper folder outside the repo, holding `.claude-plugin/plugin.json` (name, version, description) and `skills/<skill>`, prints "Validation passed with warnings" and exits 0. It warns that no author is set, and its plugin-directory checks list README_MISSING, LICENSE_MISSING and ICON_MISSING, which do not affect eval. C2 runs on such a wrapper, with `--no-publish` so the HTML report stays local (publishing to claude.ai is "already the default when your account supports it", claude plugin eval --help, under --publish-report).
- **C3 account and cost.** C3 runs in an account in us-west-2 (the priced Region), through the on-demand Evaluate API only (`POST /evaluations/evaluate/{evaluatorId}`, with the spans passed in `evaluationInput.sessionSpans`). It creates no resource. Batch and online evaluation, datasets and CloudWatch Transaction Search are not used: Transaction Search is an account-wide setting that switches all span ingestion, which a trial should not change. AWS documents this API only for spans first ingested into CloudWatch with Transaction Search enabled (getting-started-on-demand.html; supported-frameworks-telemetry.html step 1). Whether it scores spans never ingested is untested; one Evaluate call on one converted run settles it, and C3 is 'cannot run (why)' if it fails. The cost is in cost-estimate.md.
- **Skill evaluators.** AgentCore also has two skill evaluators, `Builtin.SkillSelectionAccuracy` and `Builtin.SkillInstructionFollowing`, which detect a skill from a read of its SKILL.md file (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/skill-evaluators.html, read 2026-11-16); they fit this repo's skill cases.
- **Judges.** C1's grader is a second `claude -p` on the same model as the subject (misc/evals/scripts/run_task_evals.py:581 `run_grader`, model passed at :612; default model `global.anthropic.claude-opus-4-6-v1`, :1025 and misc/evals/Makefile:35). C2's judge is Haiku by default ("--judge-model <model> Override LLM-grader model (default: haiku)"). C3 uses AgentCore's built-in evaluators, whose model cost is included in the evaluator price ("Model usage costs are included for built-in evaluators", https://aws.amazon.com/bedrock/agentcore/pricing/).
- **AgentCore pricing.** cost-estimate.md.
- **Moving the runner.** The trial also weighs moving the runner's dependencies out of the vendored skill-creator folder. That is not a score row; the recommendation is in results.md.

## C2 cases

Each case becomes one `case.yaml` under the wrapper's `evals/` folder (`claude plugin eval --help`: "<eval dir>/**/case.yaml or prompt.md + graders/*.md").
- Arms: `--ablation with-without`, the with-skill and no-plugin arms.
- Gated tools: `--allow-tools Bash` for T3 (the validator) and T7 (the cluster read).
- T5: cannot run (no multi-turn option in `claude plugin eval --help`).
- T7: `--help` names no kubeconfig option, so the read-only kubeconfig is set as `KUBECONFIG` in the environment of the `claude plugin eval` call; whether the child run reads it is recorded in S1.
- The wrapper's `plugin.json` holds `name`, `version` and `description`, and its `skills/` holds the one skill under test.
