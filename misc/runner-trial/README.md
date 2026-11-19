# Eval runner trial

Repo line cites are at commit 7efa0776.

A short trial to choose the eval runner before more eval work is built on one. It runs three candidates on the same fixed case set and fills one score sheet, so the candidates can be compared on the same evidence:

- C1: the homegrown runner in misc/evals/, extended with old against new, three runs per case and Kiro and Codex adapters (sized here, not built; the trial's driver, drive_c1.py, does old against new and three runs itself, score-sheet.md and results.md);
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
| drive_c1.py | The C1 driver: runs the seven cases through the existing runner's functions, one case and arm at a time |
| ../tests/test_drive_c1.py | The driver's tests, with the runner's functions mocked and no model call |

## How it runs

- The subject model for the claude harness is `global.anthropic.claude-opus-4-6-v1`, the runner's default (misc/evals/Makefile:35); Claude Code also calls Haiku 4.5 inside a run, C2's judge is Haiku, Codex runs gpt-5.6-sol and C3 uses its built-in evaluators' models.
- C1 is driven by misc/runner-trial/drive_c1.py, which calls the existing runner's functions one case and arm at a time: a dry run by default, and `--paid` only with an empty or new `--out`, a spend limit and an eval-role session the runner mints and checks, stopping before the next run once the subjects' recorded cost reaches the limit (what that stop counts: cost-estimate.md). The driver's tests run from the repo root, `python3 -B -m unittest misc.tests.test_drive_c1 -v`, and in CI by .github/workflows/runner-trial-tests.yml. The runner code in misc/evals/scripts/ is not changed by the trial. Kiro and Codex are driven directly for T1.
- C2 runs on a plugin wrapper outside the repo, with `--model global.anthropic.claude-opus-4-6-v1`, `--no-publish` and `--max-cost-usd 60`.
- C3 scores C1's runs through the on-demand Evaluate API. It is planned to create no AWS resource and change no account setting; that holds only if Evaluate scores spans never ingested (score-sheet.md).
- Eval runs use a separate eval account through the eval role `apex-eval-bedrock-invoke`, the only AWS credential the runner hands a subject or grader; the subject runs as your OS user with bypassPermissions, so it can read, write and run anything your user can, the runner's environment included (and on an EC2 host, the instance role through the metadata endpoint unless that is blocked); run it as another OS user or in a container for a hard fence (misc/evals/README.md, Eval-role setup). The role's status is in cases.md, Credentials and permissions.
- T7 reads a test cluster through an existing read-only kubeconfig.
- No terraform, cluster write or account write anywhere in the trial.

## Status

No paid run has happened yet. The runs wait on the eval role (its status: cases.md, Credentials and permissions) and one proven end-to-end run (cost-estimate.md). Main has changed the case text of T1 to T5 and T7, T2's fixtures, and the skills of T1, T2, T3, T5 and T7 since 7efa0776, so the driver reads every case file, fixture and skill from 7efa0776 with `git archive`, never from the working tree; the old arm reads its skill from 0678d921 the same way.
