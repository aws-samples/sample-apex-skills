# Eval runner trial

Repo line cites are at commit 7efa0776.

A short trial to choose the eval runner before more eval work is built on one. It runs three candidates on the same fixed case set and fills one score sheet, so the candidates can be compared on the same evidence:

- C1: the homegrown runner in misc/evals/, extended with old against new, three runs per case and Kiro and Codex adapters (sized here, not built);
- C2: `claude plugin eval`;
- C3: Amazon Bedrock AgentCore Evaluations, on-demand Evaluate API only.

## Files

| File | What it holds |
|---|---|
| cases.md | The seven cases T1 to T7, their sources, pass conditions, arms, run count and the credentials each subject can reach |
| score-sheet.md | The grid S1 to S10 for each candidate, and the facts settled before any run |
| same-answer-rule.md | When two runs, or two runners, give the same answer |
| cost-estimate.md | The trial's cost, stated before any paid run, with its basis |
| results.md | Results, the runner pick, the sized C1 extension and the vendored-folder recommendation |
| sregym-feasibility.md | Whether SREGym can be adapted for EKS, and what it would add |

## How it runs

- The subject model for the claude harness is `global.anthropic.claude-opus-4-6-v1`, the runner's default (misc/evals/Makefile:35); Claude Code also calls Haiku 4.5 inside a run, C2's judge is Haiku, Codex runs gpt-5.6-sol and C3 uses its built-in evaluators' models.
- C1 is to be driven by a separate script, not yet written, at misc/runner-trial/drive_c1.py, that calls the existing runner's functions one case and arm at a time. The runner code in misc/evals/scripts/ is not changed by the trial. Kiro and Codex are driven directly for T1.
- C2 runs on a plugin wrapper outside the repo, with `--no-publish` and `--max-cost-usd 60`.
- C3 scores C1's runs through the on-demand Evaluate API. It is planned to create no AWS resource and change no account setting; that holds only if Evaluate scores spans never ingested (score-sheet.md).
- T7 reads a test cluster through an existing read-only kubeconfig. Every case's subject can still reach the trial host's AWS credentials (cases.md, Credentials and permissions).
- No terraform, cluster write or account write anywhere in the trial.

## Status

No paid run has happened yet. The runs wait on the maintainers' spend decision and a subject credential limited to the model calls (cost-estimate.md; cases.md, Credentials and permissions).
