# Runner trial: score sheet (pass or fail)

The sheet compares three candidate runners on the same eight cases (cases.md). No row needs a runner to win, and the sheet picks none: the pick is written in results.md.

What "pass" means: the trial's only stated exit is "a fixed case set and a score sheet, so the trial passes or fails". No rule defines when a single cell, a case or the trial as a whole passes. This sheet adds none. Each cell holds the measured value, and the pick in results.md gives its reasons from those values.

Candidates:
- C1: the homegrown runner (misc/evals/) extended with old against new, three runs per case and Kiro and Codex adapters. The extension is sized, not built, in this trial (results.md). C1 is driven from a separate script that calls the existing runner's functions per case and arm, and Kiro and Codex are driven directly for T1. The runner code is not changed.
- C2: `claude plugin eval` (Claude Code 2.1.325).
- C3: Amazon Bedrock AgentCore Evaluations, on-demand Evaluate API only.

## Grid

| Row | Measured | Cell values | How it is filled | C1 | C2 | C3 |
|---|---|---|---|---|---|---|
| S1 | each case T1 to T8: did the runner execute it as written | ran / cannot run (why), per case | from the run log of the first run of each case | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S2 | each case: pass count out of 3 runs, with the skill and without | n/3, n/3, or n/a (cannot run, see S1), per case | count of runs meeting the case's pass condition (cases.md); T6 has one arm | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S3 | old against new on T1 to T4 | supported (how) / not supported | from the old-against-new runs of T1 to T4; "how" names the mechanism | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S4 | three runs per case with no hand work | yes / no | yes if one command or config gives 3 runs of every case | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S5 | which harnesses it drives (Claude Code, Kiro, Codex) | list | the harnesses on which T1 ran | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S6 | tokens and wall time recorded per case | yes (field name) / no | the field in the runner's output that holds each | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S7 | a nonzero exit on a failed case, usable as a CI gate | yes (flag) / no | run a case set where one case fails, read the exit code | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S8 | what leaves the host (reports, traces, published pages) | list | read the runner's output and network targets during T1 and T7 | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S9 | setup needed before the first run (accounts, services, mocks) | list | everything done before S1's first run | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |
| S10 | the trial's own cost, estimated before it is spent | (runs plus judge calls) x a per-run figure | cost-estimate.md; the per-run figure is re-measured on one T4 run first | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs | waits on the owner's spend decision for the paid runs |

S10 is the trial's own cost only. The eval gate's cost per pull request is worked out in results.md from S2, S6 and S10.

## Facts settled before the runs

- **Adapters.** C1's Kiro and Codex adapters are sized, not built, in this trial: the files and hours are in results.md. Kiro CLI 3.3.0 has a headless mode (`kiro-cli chat --no-interactive`, `--output-format stream-json`), and Codex CLI 0.163.0 has one (`codex exec --json`). Both are driven directly for T1.
- **C2 target.** A bare skill folder is not a target. `claude plugin validate <skill dir>` prints "No manifest found in directory. Expected .claude-plugin/marketplace.json or .claude-plugin/plugin.json" and exits 1. A wrapper folder outside the repo, holding `.claude-plugin/plugin.json` (name, version, description) and `skills/<skill>`, prints "Validation passed with warnings" and exits 0; the only warning is a missing author. C2 runs on such a wrapper, with `--no-publish` so the HTML report stays local (publishing to claude.ai "is already the default when your account supports it", `claude plugin eval --help`).
- **C3 account and cost.** C3 runs in the same AWS account and Region (us-west-2) as the trial's test cluster, through the on-demand Evaluate API only (`POST /evaluations/evaluate/{evaluatorId}`, with the spans passed in `evaluationInput.sessionSpans`). It creates no resource. Batch and online evaluation, datasets and CloudWatch Transaction Search are not used: Transaction Search is an account-wide setting that switches all span ingestion, which a trial should not change. The cost is in cost-estimate.md.
- **Judges.** C1's grader is a second `claude -p` on the same model as the subject (misc/evals/scripts/run_task_evals.py:581 `run_grader`, model passed at :612; default model `global.anthropic.claude-opus-4-6-v1`, :1025 and misc/evals/Makefile:35). C2's judge is Haiku by default ("--judge-model <model> Override LLM-grader model (default: haiku)"). C3 uses AgentCore's built-in evaluators, whose model cost is included in the evaluator price ("Model usage costs are included for built-in evaluators", https://aws.amazon.com/bedrock/agentcore/pricing/).
- **AgentCore pricing.** From the AWS Price List (service AmazonBedrockAgentCore, regionCode us-west-2, read 2026-11-16): "$2.40 per 1M Input Token for Evaluations:Consumption-based:BuiltIn-Input:Tier1 in US West (Oregon)" and "$12.00 per 1M Output Token for Evaluations:Consumption-based:BuiltIn-Output:Tier1 in US West (Oregon)", effective 2026-11-05. The trial uses no custom evaluator. The pricing page gives batch at $0.0018 and $0.009 per 1K tokens, a 25% discount. The trial does not use batch.
- **Moving the runner.** The trial also weighs moving the runner's dependencies out of the vendored skill-creator folder. That is not a score row; the recommendation is in results.md.
