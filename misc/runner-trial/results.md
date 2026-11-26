# Runner trial: results

Repo line cites are at commit 7efa0776, except T4's case text, at 8f16c66b (cases.md, T4).

## Status

The trial ran on 2026-11-20 and 2026-11-21. score-sheet.md:7 reads: "the trial passes when every cell S1 to S10 is filled for all three candidates (a measured value, a value read from the tool or code where the cell says so, the S10 estimate, 'cannot run (why)' or 'n/a (why)'), and results.md states the pick with its reasons from S2, S6 and S10; otherwise it fails. It fails if any candidate the pick names has no measured S2 n/3, or if a pick reason rests on a 'cannot run' or 'n/a' cell." Every cell is filled in those forms; C2's S8 reads 'n/a' for T1, whose traces are not kept. No pick reason rests on a 'cannot run' or 'n/a' cell, so the sheet's pass rule is met as written; the pick, C1, rests on S6 alone and waits on the user's acceptance (Pick). The run outputs are kept on the operator's host, not in the repo; each figure below names its out dir and file, except the CloudTrail count for the first C2 T4 call and the S7 exit in score-sheet.md, which rest on records not kept in this repo and say so at their site.

What stopped runs on the way, and how each was cleared:
- The eval-role session could not be renewed: the sign-in behind profile `apex-eval-admin` refused the renewal (the identity provider rejected the refresh as `used_too_late`), so the driver stopped at that renewal at 07:53:31Z, as designed ("eval-role session refused or failed to refresh, stopping", `c1-full-stderr.txt`), and C2 stopped before its third suite at 07:42:13Z (`c2-run-20261120T0820Z/driver-log.txt`). After a fresh sign-in they were re-run (Runs, below). That second sign-in was refused the same way before C1's T6 re-run (next item) could start; after a third sign-in on 2026-11-21 it ran.
- T6 (C1): ran on 2026-11-21, 6 of 6 runs, on a runner whose built-in list holds the nine names below, which this branch adds to run_triggering.py; T6 ran on 29eea21f plus the same nine names, and the T6 path reads the same tree (Runs, below). In the 2026-11-20 re-run, on the list before this branch, every run was invalid: the runner checks that a triggering run's system/init lists only the skill under test and its known built-in skills (misc/evals/scripts/run_triggering.py `BUILTIN_SKILLS` and `_check_init`), and Claude Code 2.1.328 lists nine more built-ins (deep-research, dataviz, verify, code-review, doctor, workflow-authoring, run, run-skill-generator, plugin-authoring), so all six runs read "error" (`c1-resume-20261120T1000Z/runs.jsonl`).
- T7 (C1): ran, 6 of 6 runs on one minted session (Runs, below). No run read "mint it again", so no re-mint was needed.
- T7 (C2): cannot run as a read-only case. On 2026-11-20 the subject had no shell: `claude plugin eval` grants a shell tool only with a sandbox backend, which was not installed on the operator's host. On 2026-11-21, with a sandbox backend installed, a probe call (one run per arm) still gave neither subject a shell: pattern-scoped grants such as `Bash(kubectl get:*)` give no Bash tool, and only a plain `Bash` grant does, which T7's read-only tool set excludes (Findings, below).
- Codex: the eval role is refused `bedrock:InvokeModel` (HTTP 401). On 2026-11-20 it was refused on the `us.openai.gpt-5.6-sol` inference profile (`codex-t1-20261120T0730Z/T1/codex_with_skill/run-1/events.jsonl`). On 2026-11-21, with a grant on that profile and its foundation models, it was refused on the account's `project/default` resource, which Bedrock's OpenAI-compatible responses endpoint that Codex calls authorizes against (`codex-c3-20261121/codex-t1/T1/codex_with_skill/run-1/events.jsonl`). With a grant that covers `project/default`, Codex T1 ran 3 of 3 on 2026-11-21 (Runs, below).
- C3: on 2026-11-20 the eval role was refused `bedrock-agentcore:Evaluate` (AccessDeniedException, `c3-onecall-20261120T0830Z/evaluate-stderr.txt`). On 2026-11-21 Evaluate was authorized, but the call failed validation: "Field 'start_time' is required but got None" (`codex-c3-20261121/c3-onecall/evaluate-stderr.txt`), since the trial's converter (misc/runner-trial/drive_c1.py `events_to_spans`) wrote no span start or end time. With span times added to the converter (the C3 runs used a local edit of `events_to_spans`, the one this branch commits), the one-call check scored, and so did every recorded C1 run (Runs, below).

## Pick

The trial picks C1, the homegrown runner, with the extension sized below (Extending the homegrown runner). The pick rests on S6 alone; S2 does not separate C1 and C2, and S10 does not decide (both C1 and C2 ran over their estimates); the pick waits on the user's acceptance. S1 is used only to rule out C3:

- S2, with the skill: C1 passed T1 3/3, T2 3/3 and T4 3/3 (corrected text); C2 passed T1 2/3, T2 2/3 and T4 2/3. On T6, C1 did better on the near-miss negative (q18 2/3 against C2's 1/3), and both passed q3 3/3. T3 is not compared: C2's first T3 call started none of its 3 runs (S1 cannot run, S2 n/a). Two of C2's misses come from how C2 runs a case: T1's failed run hit the 900 s case timeout, and T4's failed run did not find the skill at the prompt's path, which does not exist under `claude plugin eval` (Runs, Findings). On T1, T2, T4 and T6 the gap is one run in three, which three runs cannot tell from chance, so S2 does not separate C1 and C2.
- S6: C1 records tokens and wall time for each run (`token_usage`, `duration_ms`); C2 records wall time and cost, but no tokens; C3 records tokens only.
- S10 does not decide: on subject cost alone, C1's estimate was $21.11 to $37.80 for 48 task runs (cost-estimate.md, C1, grader and T6 left out) and its 60 recorded task runs cost $57.83 (the gate left out), so C1 ran over its estimate; C2's was $11.01 to $25.58 for fewer runs (no old-against-new arm, no T5), and it spent $31.32, so C2 also ran over its estimate; C3 spent $9.54. C1 spent the most, but all three are inside the $205 budget, so on this sheet cost does not decide between them.

C2 is not picked: it records no tokens (S6). Its S2 is lower on T1, T2, T4 and T6 by gaps three runs cannot separate, and its T3 cell is n/a, so the pick rests on S6. C3 is not picked: it runs no agent, so it cannot be the runner (S1), and as a grader of C1's runs it matched C1's own grader on 33 of 33 runs whose condition reads the answer and disagreed with it on 18 of the 27 runs whose condition is an artifact or a resumed turn (S2; T5 re-graded, 17 on runs.jsonl's `pass`); on this sheet it adds no result C1's grader lacks.

What the pick does not settle:
- C1 at 7efa0776 has no old-against-new mode (S3), drives no harness but Claude Code (S5) and exits 0 on a failed case (S7), where C2 exits 1. Those are pieces of the sized extension below; the trial sized them and did not build them. Main's runner has since gained `--base-ref` (old against new) and `--harness {claude,kiro,codex}`, with `--runs` defaulting to the skill's regression.pass_k (commit 582cdfe5); the trial did not run those options.
- C1's T6 cells: T6 ran on 29eea21f plus the nine names this branch adds (Status); the T6 path reads the same tree. On the list before those names every T6 run is invalid (Status).
- C1's sandbox for these runs had no wall, so its without-skill arm was not a hard baseline; the wall since added is not a hard fence either (cases.md, Credentials and permissions), and no run here was repeated under it (Findings).
- C2 loads the user's Claude Code settings, so its first T4 call's judge ran on the operator's admin role session, not the eval role (Findings).
- Case quality is the eval layer's (cases.md): the eval-file items (T7's IaC expectation) and the elicitation fix (T5 on C1) are tracked outside this repo; T4's text is corrected (8f16c66b) (Findings).
- What leaves the host (S8) is read from the run files, which do not record the model endpoint host, and C2's T1 traces are not kept (S8).
- The eval gate's cost per pull request is an estimate (Spend).
- With C1 picked, the vendored-folder recommendation below applies.

## Runs

The gate: `CLAUDE_CODE_USE_BEDROCK=1 python3 misc/runner-trial/drive_c1.py --case T4 --paid --out <new dir> --spend-limit-usd 0.01` (cost-estimate.md, Gate) stopped after its first subject run, which recorded $0.5404 (`gate-20261120T0630Z/runs.jsonl:1`). The gate passed. That run failed T4's pass condition (below).

C1, claude harness: one invocation, `--case T1` to `--case T6`, `--spend-limit-usd 95` (`c1-full-20261120T0700Z/runs.jsonl`, 21 runs; no summary.json, since the stop ends the invocation before it is written). Pass count, subject cost and wall time per arm:

| Case | Arm | Pass | Subject cost | duration_ms per run |
|---|---|---|---|---|
| T1 | with_skill | 3/3 | $1.28 | 44160, 38835, 41760 |
| T1 | without_skill | 3/3 | $0.41 | 21559, 22141, 20894 |
| T1 | old_skill | 3/3 | $0.76 | 37784, 42917, 35228 |
| T2 | with_skill | 3/3 | $3.03 | 137360, 117130, 192056 |
| T2 | without_skill | 0/3 | $0.67 | 35373, 38983, 36158 |
| T2 | old_skill | 0/3 | $2.36 | 88504, 108016, 98199 |
| T3 | with_skill | 3/3 | $10.23 | 514210, 755148, 1023680 |
| T4 | with_skill | 0/1 (gate run only) | $0.54 | 104001 |

C1, the re-run after the fresh sign-in: one invocation, `--case T3` to `--case T6`, `--spend-limit-usd 70` (`c1-resume-20261120T1000Z/runs.jsonl` and `summary.json`, subject cost $30.618). The driver has no per-arm option, so T3's with-skill arm ran again. Per-arm subject cost in every C1 table here is the sum of the arm's `total_cost_usd` in its runs.jsonl, at two decimals.

| Case | Arm | Pass | Subject cost | wall_seconds per run |
|---|---|---|---|---|
| T3 | with_skill | 2/3 | $7.27 | 434.4, 657.15, 515.43 |
| T3 | without_skill | 0/3 | $2.84 | 158.87, 188.48, 182.93 |
| T3 | old_skill | 1/3 | $5.57 | 568.79, 408.23, 288.13 |
| T4 | with_skill | 0/3 | $1.46 | 128.07, 118.43, 126.47 |
| T4 | without_skill | 0/3 | $0.50 | 35.67, 35.27, 35.69 |
| T4 | old_skill | 0/3 | $1.70 | 97.85, 124.22, 734.98 |
| T5 | with_skill | 0/3 | $5.68 | 423.06, 287.45, 368.77 |
| T5 | without_skill | 0/3 (re-graded on cases.md:45's condition; runs.jsonl's `pass` (without_skill 1/3: false, false, true) is the older grader's) | $5.60 | 234.09, 243.2, 203.22 |
| T6 | with_skill_q3 | invalid on the list before this branch, 0 of 3 ran (Status) | $0.00 | 5.29, 5.08, 4.87 |
| T6 | with_skill_q18 | invalid on the list before this branch, 0 of 3 ran (Status) | $0.00 | 61.35, 4.41, 44.59 |

C1, T7 on its own: `--case T7 --paid --spend-limit-usd 15 --kubeconfig <read-only kubeconfig> --cluster-credentials <minted file>`, run right after one mint whose `expiration` printed as `2026-11-20T11:01:10+00:00`, the CLI's ISO form, which the driver parsed (`c1-t7-20261120T1003Z/runs.jsonl`, `summary.json`: subject cost $5.259). All six runs started inside that one session.

| Case | Arm | Pass | Subject cost | wall_seconds per run |
|---|---|---|---|---|
| T7 | with_skill | 0/3 (grader 3/4 each); same answer | $4.53 | 267.8, 250.66, 248.15 |
| T7 | without_skill | 0/3 (grader 3/4 each); differs | $0.72 | 67.36, 54.56, 86.12 |

Same answer (same-answer-rule.md, from each run's transcript.md, report and grading.json): with the skill, the three runs fail the same expectation (IaC) and agree on version 1.36, platform eks.17, strategy Mixed and the same 7 EKS-managed add-ons and versions, and none names an IaC tool. Without it they differ: run-1 reports a single managed node group and runs 2 and 3 a managed node group plus Karpenter, though the Karpenter node shows in all three runs' reads (not a live change), and run-2 gives no platform version and pod identity v0.2.4 against v1.4.0-eksbuild.4 in runs 1 and 3. C2's T7 arms read cannot compare (its runs cannot run).

C1, T6 on its own, 2026-11-21: a throwaway clone of 29eea21f with one change, the nine built-in names above added to run_triggering.py's list of known built-ins (the same names this branch adds), run as `CLAUDE_CODE_USE_BEDROCK=1 python3 -B misc/runner-trial/drive_c1.py --case T6 --paid --spend-limit-usd 5` on Claude Code 2.1.328 (`c1-t6-rerun-20261121T0523Z/runs.jsonl` and `summary.json`, `both_queries` 2/3). No triggering run records a cost (cost-estimate.md, T6), so summary.json's subject cost reads $0.0.

| Case | Arm | Pass | Subject cost | wall_seconds per run |
|---|---|---|---|---|
| T6 | with_skill_q3 | 3/3 | not recorded | 5.39, 5.14, 5.23 |
| T6 | with_skill_q18 | 2/3 (run 3 loaded the skill) | not recorded | 31.89, 35.9, 4.35 |

C1, T4 on its corrected text, 2026-11-21: `CLAUDE_CODE_USE_BEDROCK=1 python3 -B misc/runner-trial/drive_c1.py --case T4 --paid --out <new dir> --spend-limit-usd 8` (`c1-t4-505-20261121T2014Z/runs.jsonl` and `summary.json`, subject cost $3.2108). That checkout read T4 at ed5bfadc, where T4's case text and skill are the same as at 8f16c66b (`git diff --stat 8f16c66b ed5bfadc -- misc/evals/eks-upgrade-check skills/eks-upgrade-check` prints nothing), and graded with a local edit of drive_c1.py whose T4_PASS matches this commit's (the driver at ed5bfadc still held the 7efa0776 T4_PASS); this commit's T4_PIN path has not had a paid run. The 9 grader calls record no cost.

| Case | Arm | Pass | Subject cost | wall_seconds per run |
|---|---|---|---|---|
| T4 | with_skill | 3/3 | $1.35 | 116.74, 128.33, 122.93 |
| T4 | without_skill | 0/3 | $0.69 | 55.3, 70.86, 59.45 |
| T4 | old_skill | 3/3 | $1.18 | 102.96, 102.06, 115.55 |

Each pass rated the cluster "59%: NOT READY" under the hard-blocker cap and named subnet IP capacity in its Blockers section; the without-skill runs scored 77 to 88 with no blocker (`c1-t4-505-20261121T2014Z/T4/<arm>/run-<n>/grading.json`).

Kiro, T1 with the skill, three runs by hand, graded by C1's grader: 3/3 (`kiro-t1-20261120T0715Z/runs.jsonl:1-3`). Each run had a new HOME holding only the skill at 7efa0776 in `~/.kiro/skills/` and a workspace holding only the three fixtures, run as `kiro-cli chat --no-interactive --output-format stream-json --trust-tools=fs_read --trust-workspace <prompt>`. Each run read the staged SKILL.md (its events.jsonl). `--trust-all-tools` was refused by the operator's permission check, so Kiro could read but not run the skill's offline scripts; its runs are narrower than C1's. Kiro bills to its own subscription, with no AWS charge.

Codex, T1 with the skill, three runs by hand on 2026-11-21, after the `project/default` grant, graded by C1's grader: 3/3 (`codex-t1-20261121T2025Z/runs.jsonl`). Each grader named both exposed components with their installed and fixed versions. Codex records no dollar cost: priced from each run's token usage in its events.jsonl at the regional gpt-5.6-sol rates (cost-estimate.md, Codex), the runs cost $0.22, $0.21 and $0.25, $0.69 in all, in 37.82, 34.4 and 32.27 s. The earlier attempts were refused (Status), at no cost.

C2, `claude plugin eval` 2.1.328, one wrapper per skill at 7efa0776, `--model global.anthropic.claude-opus-4-6-v1 --no-publish --ablation with-without --runs 3 --scaffold`, under one $60 ceiling across the calls (`c2-run-20261120T0820Z/c2-ledger.jsonl`):

| Case | With | Without | Cost | Out file |
|---|---|---|---|---|
| T1 | 2/3 (two runs hit the 900 s case timeout; one of them still passed) | 3/3 | $2.36 | eks-security.json |
| T4 | 0/3 (graded on the 7efa0776 text, Findings) | 1/3 (a judge false pass, Findings) | $2.39 | eks-upgrade-check.json |

After the fresh sign-in, a second invocation of the same calls under a $40 ceiling (`c2-resume-20261120T1006Z/c2-ledger.jsonl`, $4.74), and T7 on its own under $10 with `-j 6` (`c2-t7-20261120T1012Z`, $6.76):

| Case | With | Without | Cost | Out file |
|---|---|---|---|---|
| T2 | 2/3 | 0/3 | $3.37 | eks-recon.json |
| T3 | cannot run: 0 of 3 started (no sandbox backend, Findings) | cannot run: 0 of 3 started | $0.02 | eks-build.json |
| T6 q3 (should load the skill) | 3/3 | 3/3 | $1.35 (both queries) | eks-mcp-server.json |
| T6 q18 (should not load it) | 1/3 (two runs called the Skill tool on eks-mcp-server, "Skill called 1x"; C2 leaves that grader unscored) | 2/3 (one 90 s timeout) | | eks-mcp-server.json |
| T7 | cannot run: no shell (Findings), 0/3 | cannot run: no shell, 0/3 | $6.76 | eks-recon-t7.json |

C2 on 2026-11-21, with a sandbox backend (bubblewrap and socat) installed: T3 under a $40 ceiling with `--allow-tools Bash Write Edit --keep-temp` (`c2-t3t7-20261121/c2-ledger.jsonl`, $10.48), graded by the 7efa0776 validate_project.sh on copies of the six kept workspaces (`c2-t3t7-20261121/t3-validate.jsonl`); and a T7 probe with one run per arm under $3 (`c2-t3t7-20261121/t7-probe/eks-recon-t7.json`, $2.23). The full T7 call was not run, since the probe showed it measures nothing.

| Case | With | Without | Cost | Out file |
|---|---|---|---|---|
| T3 | 0/3 (two fail only `terraform fmt -check`, one wrote no .tf) | 0/3 | $10.48 | eks-build.json |
| T7 probe | 0/1 (no shell) | 0/1 (no shell) | $2.23 | t7-probe/eks-recon-t7.json |

C2, T4 on its corrected text, 2026-11-21: the wrapper's T4 case.yaml regenerated from the 8f16c66b text (prompt and criterion), under a $6 ceiling (`c2-t4-505-20261121T2017Z/c2-ledger.jsonl`, $2.27, judge included):

| Case | With | Without | Cost | Out file |
|---|---|---|---|---|
| T4 | 2/3 (the failed run never loaded the skill, Findings) | 0/3 | $2.27 | eks-upgrade-check.json |

C2's own LLM grader passed T3 in 2 of 3 with-skill runs and 3 of 3 without, against the validator's 0 of 3 each; T3's pass is the validator (cases.md, T3).

A first T4 call (`c2-20261120T0800Z/eks-upgrade-check.json`, $0.10) had every subject fail with "Could not load AWS credentials": `claude plugin eval` loads the user's Claude Code settings, and an AWS profile set there overrode the eval-role session. Its judge calls ran on that profile: a read of the eval account's CloudTrail on 2026-11-21 found 18 Haiku model calls in the run's window, made as the operator's admin role session, while the eval-role session the call minted made no model call (attributed by time, model and agent; the run files record no caller). That CloudTrail read is not kept in this repo; the run file backs 18 judge votes, 3 on each of its 6 runs over 2 arms. The calls above ran with `CLAUDE_CONFIG_DIR` set to an empty dir, so no user setting applied.

C3, one Evaluate call on 2026-11-21, on C1 T1 with_skill run-1 (12 spans, each with a start and end time): rc 0, `Builtin.Correctness` 1.0, "Perfectly Correct", 14,137 input and 339 output tokens (`c3-onecall-20261121T2010Z/evaluate-stdout.json`). So Evaluate scores spans never ingested into CloudWatch, and C3 needs no Transaction Search (cost-estimate.md, C3).

C3, every recorded C1 run with an events.jsonl, 60 in all (the 51 of `c1-full-20261120T0700Z`, `c1-resume-20261120T1000Z` and `c1-t7-20261120T1003Z`, and the 9 of `c1-t4-505-20261121T2014Z`), each scored by `Builtin.GoalSuccessRate` and `Builtin.Correctness`: 120 of 120 calls scored (`c3-full-20261121T2048Z`, with 5 runs scored again in `c3-full-rerun5-20261121T2055Z`). GoalSuccessRate's assertion is the condition C1 judged the run on: the grader's expectation text for T1, T4 and T7, and the case's Pass line (cases.md) for T2, T3 and T5. Correctness had no expected answer. `Builtin.TrajectoryAnyOrderMatch` was not called: no case defines an expected tool list, and making one up would grade against an invented answer. In the first pass, the 5 runs with more than one result event (the session going on by itself after a background task or subagent finished) failed: the converter made each extra result its own turn, with no prompt and no times, and Evaluate refused it ("Field 'start_time' is required but got None"; "Failed to parse user_query from agent-span"). The converter now folds such a turn into the one before (drive_c1.py `events_to_spans`); the other 55 runs' spans are unchanged by that, and the 5 then scored.

| Case | Arm | C3 pass (GoalSuccessRate 1.0) | C1 pass | Runs where C3 and C1 agree |
|---|---|---|---|---|
| T1 | with_skill / without_skill / old_skill | 3/3, 3/3, 3/3 | 3/3, 3/3, 3/3 | 9/9 |
| T2 | with_skill / without_skill / old_skill | 3/3, 3/3, 3/3 | 3/3, 0/3, 0/3 | 3/9 |
| T3 | with_skill (both invocations) / without_skill / old_skill | 2/6, 2/3, 0/3 | 5/6, 0/3, 1/3 | 4/12 |
| T4, 7efa0776 text | with_skill / without_skill / old_skill | 0/3, 0/3, 0/3 | 0/3, 0/3, 0/3 | 9/9 |
| T4, corrected text | with_skill / without_skill / old_skill | 3/3, 0/3, 3/3 | 3/3, 0/3, 3/3 | 9/9 |
| T5 | with_skill / without_skill | 2/3, 2/3 | 0/3, 0/3 (re-graded on cases.md:45's condition; runs.jsonl's `pass` (without_skill 1/3: false, false, true) is the older grader's) | 2/6 (3/6 on runs.jsonl's `pass`) |
| T7 | with_skill / without_skill | 0/3, 0/3 | 0/3, 0/3 | 6/6 |

C3 agrees with C1 on 42 of 60 runs: 33 of 33 on the cases C1 grades with an LLM (T1, T4, T7), 9 of 27 on T2, T3 and T5 (Findings). These use the re-graded T5; on runs.jsonl's `pass` they are 43 of 60 and 10 of 27. GoalSuccessRate read 1.0 or 0.0 on every run; Correctness read 1.0 on 46 runs, 0.5 on 13 and 0.0 on 1. Cost, priced from each call's token usage at $2.40 per 1M input and $12.00 per 1M output tokens (AgentCore records no dollar cost): $0.04 for the one call, $9.50 for the scoring, both passes included.

## Findings

- **T4's pass condition, not the skill, is wrong.** The gate's run rated the cluster 87, GOOD, with "No blockers identified" (`gate-20261120T0630Z/T4/with_skill/run-1/grading.json`), and so did C2's three with-skill runs and the six C1 with-skill and v1.3.0 runs of the re-run (`c1-resume-20261120T1000Z`). Each applied the skill's own rule: both versions cap the score only when the available IPs summed over all cluster subnets are under 5 (skills/eks-upgrade-check/references/report-generation.md:105 and :321-323; v1.3.0 :103-108), and the 7efa0776 mock (subnet-aaa 3, subnet-bbb 12, total 15) is that spec's own worked example of no blocker (:108). The pass condition wanted subnet-aaa named as a blocker on its own, which the skill's rule does not do; the EKS Best Practices Guide's "up to five available IP addresses from the subnets" (cases.md, T4) does not say whether that is a total or per subnet. The eval text was since corrected (commit 8f16c66b: subnet-aaa 3 and subnet-bbb 1, total 4), and cases.md T4 now uses it. On that text C1 passed with the skill 3/3 and with v1.3.0 3/3 and failed without it 0/3, and C2 passed with 2/3 and without 0/3 (Runs). A separate gap for the skill's rebuild: it gives no caveat that the subnets you specify must each have at least six IP addresses (EKS User Guide, network-reqs.html). The three C1 without-skill runs failed for want of the spec (below).
- **C1's sandbox for these runs had no wall, so its without-skill arm was not a hard baseline; the wall since added is not a hard fence either (cases.md, Credentials and permissions), and no run here was repeated under it.** In T4, C1 old_skill run 3 found no skill copy in its sandbox, ran `find /` and read a report-generation.md elsewhere on the host (`c1-resume-20261120T1000Z/T4/old_skill/run-3/events.jsonl`). So a with-against-without comparison cannot assume the without arm cannot reach a skill. Every run ran as the operator's own OS user with no container or other fence; none of the 69 events.jsonl files shows a read of a credential file, and whether the instance metadata endpoint was blocked was not checked. The without arm has no skill copy by design (misc/runner-trial/drive_c1.py:505 at ed5bfadc), so its failure on the missing spec is the expected baseline.
- **C2's T4 with-skill result rests on a Skill tool fallback.** The corrected T4 prompt tells the subject to read `.claude/skills/eks-upgrade-check/references/report-generation.md`, and `claude plugin eval` installs the skill as a plugin, so that path does not exist in a C2 run. The two passing runs fell back to the Skill tool and read the spec from the plugin's own install folder, which the Skill tool names (not a read outside the sandbox); the failing run never called the Skill tool after its search found nothing and scored 82, the score before the cap (each run's trace.jsonl, kept with `--keep-temp`). On C1 the path exists for the with-skill and v1.3.0 arms, and all six passed.
- **C3's GoalSuccessRate stands in for a grader that reads the answer, not for an artifact or process check.** It agrees with C1 on 33 of 33 runs of T1, T4 and T7, whose condition is a reading of the answer. On T2 it passed 6 runs C1's pattern check failed: it reads the meaning, and the Pass line asks for a "Changed" row by form (T2 old_skill run-1 counted a row "| MNG modified | **blue** desired\_size 2 -> 3 |" as meeting it). On T3 it cannot run validate_project.sh and judged the generated content instead (8 runs disagree). On T5 it sees one prompt per run, so it judged the last answer, not whether the run was resumed (4 runs disagree on the re-graded T5, 3 on runs.jsonl's `pass`). This is the limit cost-estimate.md states for C3 ("an LLM reading, not the condition checked directly"). Correctness, with no expected answer, says little about the pass condition: T4 on the 7efa0776 text failed every arm, and its with-skill runs still scored 1, 1, 1.
- **C2's judge passed a T4 run its condition rules out.** C2's without-skill run 2 of 3 passed on 2 of 3 judge votes while its report scored 72 / 100, above the condition's 59 or lower (`c2-run-20261120T0820Z/eks-upgrade-check.json`). A candidate finding for the score sheet, not a case change.
- **C2's first T4 call ran its judge on the operator's admin role session, not the eval role.** `claude plugin eval` loads the user's Claude Code settings, and an AWS profile set there overrode the eval-role session (Runs); the later C2 calls set `CLAUDE_CONFIG_DIR` to an empty dir.
- **A known runner gap: the C1 driver's `aws` shim puts the cluster session secret on the `env` command line**, so `ps` shows it while a subject's `aws` call runs, and the driver does not check the `--cluster-credentials` file's mode (drive_c1.py `live_env`).
- **T7 fails on its IaC expectation in all six runs, with the skill and without.** Each grading.json fails only "The output identifies the IaC tool managing the cluster" (`c1-t7-20261120T1003Z/T7/<arm>/run-<n>/grading.json`). T7's prompt (misc/evals/eks-recon/evals.json, id 1) asks the skill to "focus on version info, compute strategy, and addon inventory", and the with-skill runs ran only those modules, reporting `iac` as not in scope. The case's prompt and its fourth expectation disagree; the expectations still carry "TODO: human review". The other three expectations passed in every run.
- **C2 gives no shell on a host without a sandbox backend.** A call that grants Bash refuses each run before it starts ("Refusing to start without a working sandbox", bubblewrap and socat not installed), and a call that grants only pattern-scoped Bash rules (`Bash(kubectl get:*)` and the like) runs with no shell at all: T7's six C2 runs ($6.76, `c2-t7-20261120T1012Z/eks-recon-t7.json`) made no Bash call: one reported "No shell or MCP tools available in this environment" (1 of 6), and the other five said in their own words that they had no shell, and each scored 0 of 4. So T3 and T7 could not run on C2 on this host without a sandbox backend. With one installed (2026-11-21), T3 runs but not as written: the sandboxed shell is read-only and offline, so every Bash write failed "Read-only file system", only the Write tool wrote files, and calls to registry.terraform.io were refused, so no subject could run `terraform fmt` or the skill's validator. T7 still gets no shell from pattern-scoped grants (Status).
- **C1's list of built-in skills was behind Claude Code 2.1.328.** On the list before this branch every T6 run is invalid (Status); this branch adds the nine names; T6 ran on 29eea21f with them, 6 of 6.
- **T6's near-miss negative loaded eks-mcp-server in one of three C1 runs** (q18 run 3); in C2's with-skill arm it loaded in two of three.
- **T1 passes without the skill** on both runners (C1 3/3, C2 3/3), so T1's single pass condition does not separate the arms.
- **T2 separates the arms**: with the skill 3/3, without 0/3, and the v1.3.0 skill 0/3 on C1; with 2/3, without 0/3 on C2.
- **T5 fails as written on C1.** T5's grader checks that a turn ended on an AskUserQuestion that one of the case's canned answers matches, and a later turn followed; the events do not record the injected text, so a background turn can still stand in for the answer turn (cases.md, T5). No run called AskUserQuestion, so no run was resumed, and all six fail: the with-skill runs wrote the whole project in one turn, and one ended on a plain-text question, which the runner cannot answer. One without-skill run went to five result events, from background agents finishing, not from an answer turn.
- **T3's cost is above its basis**: $2.20 to $4.48 per with-skill run over both invocations against the measured $0.831 to $1.211 (cost-estimate.md, Per-run basis). Re-stated at the highest measured run, T3 is about $30 against $10.32, and the total stays under the $205 budget. T1's runs ($0.135 to $0.472) sit inside its assumed $0.30 to $0.80 or below it; T4's with-skill runs on the corrected text ($0.43 to $0.49) and the gate run ($0.54) are above its $0.309, and its without-skill runs ($0.22 to $0.25) above its $0.177.

## Spend

| Day | Candidate | Recorded | Priced from tokens | From |
|---|---|---|---|---|
| 2026-11-20 | C1 | $55.16 | | the gate $0.5404, T1 to T3 $18.7426, T3 to T6 $30.618, T7 $5.259 (each runs.jsonl) |
| 2026-11-20 | C2 | $16.35 | | $4.8527 (the $0.1026 first call included), $4.7413, T7 $6.7557, judge included (each c2-ledger.jsonl) |
| 2026-11-20 | Kiro, Codex, C3 | $0 | | Kiro bills its own subscription; every Codex and C3 call was refused (Status) |
| 2026-11-21 | C1 | $3.21 | | T4 on the corrected text $3.2108; the T6 re-run records no cost |
| 2026-11-21 | C2 | $14.97 | | T3 $10.4768, T7 probe $2.2277, T4 $2.2664, judge included (each c2-ledger.jsonl) |
| 2026-11-21 | Codex | $0 | $0.69 | T1, three runs (Runs) |
| 2026-11-21 | C3 | $0 | $9.54 | the one-call check $0.04 and the scoring $9.50 (Runs) |

**$89.69 recorded.** Grader calls and T6 query runs record no cost: 40 grader calls (C1's 9 on T1, 9 and 9 on T4 and 6 on T7, the gate's 1, Kiro's 3 and Codex's 3) at the assumed $0.10 to $0.40 each, $4.00 to $16.00, and 12 T6 query runs (6 on 2026-11-20, 6 on 2026-11-21) at the assumed $0.05 to $0.30 each, $0.60 to $3.60 (cost-estimate.md, T6). With Codex and C3 priced from their tokens ($10.22) and every unrecorded call at the top of its assumed range, the trial spent **at most $119.51 of the $205 budget**.

- The eval gate's cost per pull request, estimated on cost-estimate.md's per-run basis (the measured runs above cost more than that basis on T3 and T4, Findings): C1 claude harness $19.79 to $44.64 for a pull request that adds a skill, which runs with and without the skill (subject $16.19 to $30.24 plus 36 grader calls), and $23.55 to $50.42 for one that changes a skill, which runs it against its previous version (the old arm priced at the with-skill rate, as in cost-estimate.md: subject $19.95 to $36.02 plus 36 grader calls); C2 $11.01 to $25.58 for six cases (T5 cannot run; C1 without T5: $13.41 to $34.58); C3 adds $2.85 to $34.82 to the runner that drives the subject (72 judged evaluations, cost-estimate.md, C3); at the trial's measured $0.079 per evaluation ($9.43 for the 120 that scored), about $5.66. Each figure is one gate pass of the trial's cases (seven; six for C2 and for C1 without T5), three runs each, not of main's 93 task cases (misc/evals/*/evals.json at 528dde41, _template left out), and holds if the gate runs those cases on each pull request.

The shared prompt-injection case is not in this trial: it is its own eval piece (classes/apex-base/evals/injection/), built on the runner this trial picks.

Everything below is settled without a paid run.

## How the trial grades

Each case is graded on its own single pass condition (cases.md). That condition is checked by the candidate's own grader, and where it is mechanical by a script as well: T3 runs validate_project.sh, T4 and T1 read the verdict, and T6 reads which Skill loaded. The trial does not use the SREGym LLM judge. SREGym's judge grades an incident diagnosis against a root cause, and the trial's cases are our skills' own prompts with our own expectations (sregym-feasibility.md, section 4).

## Extending the homegrown runner (C1), sized

The trial drives C1 from a separate script, misc/runner-trial/drive_c1.py, so the runner code is not changed here, except run_triggering.py's list of built-in skills (Status, T6). The driver itself does two of the pieces below, old against new (git archive of tag v1.3.0; both arms run, no comparison written) and three runs, and it holds the span converter for C3 (Spans for C3, below); the rest of the table is sized against the runner at 7efa0776, not built. Building the extension for real touches these files (misc/evals/scripts/ unless noted):

| Piece | Files | What changes | Size |
|---|---|---|---|
| Old against new | run_task_evals.py (`run_skill` :764, `run_subject` :415) | a second skill path per case (the skill at a given tag, staged from `git archive`), a third config beside `with_skill` and `without_skill`, and the comparison written into the benchmark | 1 file changed |
| Three runs per case | misc/evals/Makefile (`RUNS_PER_PROMPT ?= 1` at :65, passed as `--runs` at :265) | default 3 for scored runs; the option exists (`--runs`, run_task_evals.py:997) | 1 line in 1 file |
| Kiro and Codex adapters | run_task_evals.py (command at :473-482, Popen at :483), elicitation.py (`run_multiturn_subject` :148), run_triggering.py (`run_single_query` :322, `stage_skill_sandbox` :74, `build_subprocess_env` :121), parse_trajectory.py (`parse_events` :141, token keys :21-33), the evals.json process assertions (Claude tool names; process_assertions.py:91 compares them), a new harness module, and a Makefile HARNESS variable | each harness gets its own command line, its own skill staging (Kiro reads `~/.kiro/skills/` and the workspace `.kiro/skills/` (kiro.dev/docs/skills/); Codex reads skills from `.agents/skills` under the working directory and repo root, `$HOME/.agents/skills` and `/etc/codex/skills` (Codex docs, Skills, read 2026-11-16), so the adapter stages each skill at `<sandbox HOME>/.agents/skills/<skill>/`), its own event parser for JSON Lines output (`kiro-cli chat --output-format stream-json`, `codex exec --json`), and a tool-name map so the process assertions read the same on every harness | 5 files changed, 1 new module, 1 Makefile variable |
| Nonzero exit on a failed case | run_task_evals.py (`main` return at :1080) | a C1 pick needs exit 1 when a case fails, not only on a suite error (score sheet S7) | 1 line in 1 file |
| Spans for C3 | misc/runner-trial/drive_c1.py (`events_to_spans`), tested in misc/tests/test_drive_c1.py (`Spans`) | built in this trial as a pure function that converts each run's events.jsonl into OpenInference spans labelled with the Claude Agent SDK scope `openinference.instrumentation.claude_agent_sdk` (`openinference.span.kind`, `input.value`/`output.value`). AgentCore reads a span only when its scope starts with `opentelemetry.instrumentation.` or `openinference.instrumentation.` and it carries an identifying attribute (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/supported-frameworks-generic.html, read 2026-11-16), and it lists the Claude Agent SDK (`openinference.instrumentation.claude_agent_sdk`), not the Claude Code CLI the runner calls. Claude Code's own OpenTelemetry export does not fill the gap: it exports traces only with `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` and `OTEL_TRACES_EXPORTER` set ("To enable it, set both `CLAUDE_CODE_ENABLE_TELEMETRY=1` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, then set `OTEL_TRACES_EXPORTER` to choose where spans are sent", read 2026-11-17), names its meter `com.anthropic.claude_code` and documents no instrumentation scope and no OpenInference attributes (https://code.claude.com/docs/en/monitoring-usage, read 2026-11-16). The function makes no AWS call and nothing in the repo calls it; the trial's C3 calls passed its output as `evaluationInput.sessionSpans` (Runs) | 1 function and its tests, built |

## Moving the runner's dependencies out of the vendored folder

Facts:
- No runner code of ours sits in skills/skill-creator/. The eval tooling calls six pieces in it. Four are live: `scripts/quick_validate.py` (misc/evals/Makefile:118, misc/evals/scripts/run_all_evals.py:98), `scripts.aggregate_benchmark` (Makefile:155), `agents/grader.md` (misc/evals/scripts/run_task_evals.py:71) and `scripts.package_skill` (Makefile:175, which itself imports `scripts.quick_validate`). Two are on targets the Makefile marks orphaned: `scripts.generate_report` (Makefile:159-168) and `eval-viewer/generate_review.py` (Makefile:177-184).
- skills/skill-creator/ is vendored (it holds .vendor-sha, 1780c5e5). .github/scripts/vendored-guard.sh:2-5 fails any pull request that edits a vendored folder unless it is a vendor sync, and "the next sync overwrites local edits". So those pieces can change under the runner at any sync, and we cannot fix them in place.

Recommendation, with C1 picked (Pick): copy the four live pieces into misc/evals/scripts/ once, each with the vendored sha it was copied from, a copy of skills/skill-creator/LICENSE.txt and an entry in THIRD_PARTY_NOTICES.md, and point the Makefile, run_all_evals.py and run_task_evals.py at the copies. skills/skill-creator/ stays vendored and unchanged; each sync after the copy then changes nothing under the live runner, and the two orphaned targets still read the vendored folder until they are removed. A change to a copy modifies Apache 2.0 code: each changed file carries a prominent change notice (Apache 2.0 section 4(b)), and THIRD_PARTY_NOTICES.md:5 is updated in the same change. No file is moved in this trial.

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
