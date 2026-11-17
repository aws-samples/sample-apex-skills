# Runner trial: fixed case set

Seven cases, T1 to T7. Each tests one capability a runner has to show, and each is reduced to one pass condition for the trial; the source suites' other expectations are not scored. T1 to T7 reuse existing suites, so the trial needs no new fixtures.

The trial uses each case's text as it stands at commit 7efa0776. Whether to keep or redo a case is the eval layer's call, not the trial's. Paths are relative to the repo root.

## Arms and runs

- With the skill and without it, on every candidate runner.
- Old against new: the skill at tag v1.3.0 (0678d921) against 7efa0776, on T1 to T4, wherever a runner can express it (score sheet S3). All four skills exist at v1.3.0 (`git cat-file -t 0678d921:skills/<skill>/SKILL.md` prints `blob` for each).
- Three runs per arm.

## Cases

Only T4's pass condition rests on an EKS fact (below); the others use fixture data or an exit code.

### T1: fixtures staged; a verdict a user acts on
- Source: misc/evals/eks-security/evals.json:45 (id 4, "c1-exposed-no-workaround").
- Fixtures: misc/evals/eks-security/files/eval-4/inventory.json, advisory-record.json, bulletin.txt (listed at :48-51).
- Pass: the verdict is exposed for both recorded components (the vpc-cni add-on and the aws-network-policy-agent image), with the installed and fixed versions from the fixture (:54). A "not exposed" verdict for either fails.
- Runs: 2 arms x 3, plus 3 old against new.

### T2: an artifact written to disk; an exact field check
- Source: misc/evals/eks-recon/evals.json:276 (id 3, offline).
- Fixtures: misc/evals/eks-recon/files/eval-3/prior.yaml, current.yaml.
- Pass: in reports/delta.md, the change table's Changed row for the blue node group reads desired_size 2 then 3 (the pattern at :330).
- Runs: 2 arms x 3, plus 3 old against new.

### T3: a generated project checked by a script
- Source: misc/evals/eks-build/evals.json:5 (id 1).
- Fixtures: none (`files` is empty).
- Pass: the skill's own skills/eks-build/scripts/validate_project.sh exits 0 on the generated folder (validator at :138). The old arm is checked by the 7efa0776 validator, one yardstick for all arms.
- Runs: 2 arms x 3, plus 3 old against new.

### T4: a scored report with a hard-blocker override
- Source: misc/evals/eks-upgrade-check/evals.json:203 (id 4, "hard-blocker-subnet-ips"; the mock findings are in the prompt at :205).
- Fixtures: none (`files` is empty). The prompt points at skills/eks-upgrade-check/references/report-generation.md.
- Pass: the rating is NOT READY (score 59 or lower, the hard-blocker cap, report-generation.md:341-342 and :353), read from the headline rating field, not by substring (every report prints READY in its caveat, :575), and subnet-aaa (3 available IPs) is named as the blocker.
- Runs: 2 arms x 3, plus 3 old against new.
- EKS fact: the blocker rests on the EKS Best Practices Guide (aws/aws-eks-best-practices at edc514fac86518b50129401c0cffd1f7981d7ec5, latest/bpg/upgrades/index.adoc:293-295, and again at :306-308): "Amazon EKS requires up to five available IP addresses from the subnets you specified when you created the cluster in order to update the cluster." That supports the suite's under-5 threshold. The 5 to 15 IP warning band in the suite's expectations is the skill's own rule, not the guide's.

### T5: multi-turn, the skill asks and the runner answers
- Source: misc/evals/eks-build/evals.json:252 (id 3, with an `elicitation` block).
- Fixtures: none.
- Pass: the run is resumed at least once with a canned answer (the elicitation block at :347-359, up to 8 turns), and the last turn's result text names one pattern (:262-264). The runner's multi-turn path gives a second turn only when a run ends on an AskUserQuestion call (misc/evals/scripts/elicitation.py:58, `detect_pending_question`), so a runner that cannot answer a plain-text question fails this case.
- Runs: 2 arms x 3.

### T6: triggering, did the Skill load
- Source: misc/evals/eks-mcp-server/triggering.json (20 queries, 8 with `should_trigger` true).
- Positive (index 3): "I added the eks-mcp config to my mcp.json but when I restart Claude Code no EKS tools show up. What's wrong?" It is a troubleshooting request, not a setup keyword match.
- Near-miss negative (index 18): "Set up the arm migration mcp (arm-mcp) so I can scan this repo for arm64 readiness before moving to Graviton." It names an MCP server set-up, and the skill's description routes the Arm migration MCP server to graviton-migration, so it is the closest negative in the file.
- Fixtures: none.
- Pass, per run: the positive query loads eks-mcp-server and the negative does not; S2 counts those runs out of 3.
- Runs: 2 queries x 3, with the skill only. The without-skill arm cannot load an absent skill.

### T7: a live read-only run, repeated for the same-answer rule
- Source: misc/evals/eks-recon/evals.json:5 (id 1, live_only at :15).
- Fixtures: none. Needs a running cluster and a read-only kubeconfig. The trial uses an existing read-only kubeconfig for its test cluster. It does not run misc/evals/setup/bootstrap-readonly.sh, so the trial creates no IAM role, policy or access entry.
- Pass, per run: the report holds each compared field; S2 counts those runs out of 3, and the same-answer result across the three (same / differs / cannot compare) is recorded beside it. A runner that cannot reach the cluster is marked "cannot run", not fail. The C1 driver marks it so when no kubeconfig is given and refuses a kubeconfig path that does not exist; a run whose cluster reads fail is re-marked "cannot run" by hand from its transcript.
- Runs: 2 arms x 3. The same-answer test applies within each arm.

## Credentials and permissions per case

The runner links the host ~/.aws into every sandbox HOME (misc/evals/scripts/run_triggering.py:92-94 and :112-114) and passes the parent environment through, `AWS_PROFILE` included (`build_subprocess_env`, :126). The subject runs with `--permission-mode bypassPermissions` (misc/evals/scripts/run_task_evals.py:480), so a Bash call in any case can use whatever AWS credentials the host holds. A case is safe to run only when those credentials allow nothing beyond what the case needs (below).

| Case | What the case needs from AWS | What the subject can reach | Safe to run |
|---|---|---|---|
| T1, T2, T3, T4, T6 | Model calls on Bedrock only; the prompts are offline (T1 and T4 say not to run aws or kubectl) | Whatever the host's AWS credentials allow | Only with credentials limited to that need |
| T5 | Model calls on Bedrock only | Whatever the host's AWS credentials allow | Only with credentials limited to that need |
| T7 | Model calls on Bedrock, plus read-only cluster and EKS API reads through the read-only kubeconfig | Whatever the host's AWS credentials allow (and the read-only kubeconfig, whose role those credentials may reach) | Only with credentials limited to that need |

No read-only path the runner already has removes the host's credentials from the subject's reach. The runner's one scoped mode, `--aws-session-policy` (run_task_evals.py:1034-1047), mints a federation token per run, and it still leaves the ~/.aws link and `AWS_PROFILE` in place, where `--profile` in a Bash call outranks the session's environment variables. So every case, T1 to T7, is "not shown safe to run as written" until the subject and the grader get a HOME with no ~/.aws link and an environment holding only credentials limited to the model calls (and, for T7, the cluster reads). That runner change is sized in results.md (Clean credentials per run); the credential itself is for the maintainers to provide.

## Run count

Per runner, for the claude harness:

| Cases | Arms x runs | Old against new | Runs |
|---|---|---|---|
| T1 to T4 | 2 x 3 | 3 each | 9 each, 36 |
| T5, T7 | 2 x 3 | none | 6 each, 12 |
| T6 | 2 queries x 3, with the skill only | none | 6 query runs |

That is 48 task runs plus 6 triggering query runs, and at most one grader call per task run (the driver grades T1, T4 and T7 only: 24 calls, cost-estimate.md:48). Kiro and Codex each run T1 three times with the skill only, staged in a sandbox HOME (`~/.kiro/skills/`, `~/.agents/skills/`), graded by C1's grader: 6 more grader calls (by hand, as evidence for the sized adapters; S5 counts only harnesses a runner drives itself). A runner with no old-against-new mode runs 36 task runs.
