# Eval runner trial

A short trial to choose the eval runner before more eval work is built on one. It runs three candidates on the same fixed case set and fills one score sheet, so the candidates can be compared on the same evidence:

- C1: the homegrown runner in misc/evals/, extended with old against new, three runs per case and Kiro and Codex adapters (sized here, not built);
- C2: `claude plugin eval`;
- C3: Amazon Bedrock AgentCore Evaluations, on-demand Evaluate API only.

## Files

| File | What it holds |
|---|---|
| cases.md | The eight cases T1 to T8, their sources, pass conditions, arms and run count |
| score-sheet.md | The grid S1 to S10 for each candidate, and the facts settled before any run |
| same-answer-rule.md | When two runs, or two runners, give the same answer |
| cost-estimate.md | The trial's cost, stated before any paid run, with its basis and the $205 cap |
| results.md | Results, the runner pick, the sized C1 extension and the vendored-folder recommendation |
| sregym-feasibility.md | Whether SREGym can be adapted for EKS, and what it would add |
| fixtures/t8/bulletin.txt | T8's fixture: a recorded bulletin with one planted instruction |

## How it runs

- One model for every candidate: `global.anthropic.claude-opus-4-6-v1`, the runner's default (misc/evals/Makefile:35).
- C1 is driven by a separate script that calls the existing runner's functions one case and arm at a time. The runner code in misc/evals/scripts/ is not changed by the trial. Kiro and Codex are driven directly for T1.
- C2 runs on a plugin wrapper outside the repo, with `--no-publish` and `--max-cost-usd 60`.
- C3 scores C1's runs through the on-demand Evaluate API. It creates no AWS resource and changes no account setting.
- T7 reads a test cluster through an existing read-only kubeconfig. T8 runs with no AWS credentials that can write and no kubeconfig.
- No terraform, cluster write or account write anywhere in the trial.

## Status

No paid run has happened yet. The runs wait on the owner's spend decision for the paid runs (cost-estimate.md). The first paid run is one C1 run on T4, and the total is re-stated from its measured cost before the rest run.
