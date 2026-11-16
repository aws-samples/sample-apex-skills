# Runner trial: results

## Status

No paid run has happened. The runs wait on the owner's spend decision for the paid runs (cost-estimate.md: $55.36 to $191.50). Until it is given, these sections hold that line and nothing else:

- Results per candidate (score-sheet.md S1 to S10): waits on the owner's spend decision for the paid runs.
- The runner pick, with its reasons from S2, S6 and S10: waits on the owner's spend decision for the paid runs.
- The eval gate's cost per pull request, from S2, S6 and S10: waits on the owner's spend decision for the paid runs.
- The head commits of the open pull requests that touch the trial's suites, recorded at run time: waits on the owner's spend decision for the paid runs.
- Spend against the estimate: $0 of $55.36 to $191.50.

Everything below is settled without a paid run.

## How the trial grades

Each case is graded on its own single pass condition (cases.md). That condition is checked by the candidate's own grader, and where it is mechanical by a script as well: T3 runs validate_project.sh, T4 and T1 read the verdict, T6 reads which Skill loaded, and T8 reads the trajectory for Bash calls. The trial does not use the SREGym LLM judge. SREGym's judge grades an incident diagnosis against a root cause, and the trial's cases are our skills' own prompts with our own expectations (sregym-feasibility.md, section 4).

## Extending the homegrown runner (C1), sized

The trial drives C1 "as extended" from a separate script, so the runner code is not changed here. Building the extension for real touches these files (misc/evals/scripts/ unless noted):

| Piece | Files | What changes |
|---|---|---|
| Old against new | run_task_evals.py (`run_skill` :764, `run_subject` :415) | a second skill path per case (the skill at a given tag, staged from `git archive`), a third config beside `with_skill` and `without_skill`, and the comparison written into the benchmark |
| Three runs per case | misc/evals/Makefile (`--runs`, task default 1, :65) | default 3 for scored runs; the option exists (`--runs`, run_task_evals.py:997) |
| One case at a time | run_task_evals.py (`main` :994) | a `--case <id>` filter; today `--skill` runs every case of a suite |
| Kiro and Codex adapters | run_task_evals.py (command at :473-482, Popen at :483), elicitation.py (`run_multiturn_subject` :148), run_triggering.py (`run_single_query` :322, `stage_skill_sandbox` :74, `build_subprocess_env` :121), parse_trajectory.py (`parse_events` :141, token keys :21-33), process_assertions.py (Claude tool names), a new harness module, and a Makefile HARNESS variable | each harness gets its own command line, its own skill staging (Kiro reads `~/.kiro/skills/`; `codex --help` and `codex exec --help` do not name Codex's skill path, so the adapter starts by finding it), its own event parser for JSON Lines output (`kiro-cli chat --output-format stream-json`, `codex exec --json`), and a tool-name map so the process assertions read the same on every harness |
| Clean credentials per run | run_triggering.py (`stage_skill_sandbox` links the host ~/.aws into the sandbox HOME, :92-94) | a scoped-credential mode, so a case such as T8 can run with no write credentials through the runner itself |

## Moving the runner's dependencies out of the vendored folder

Facts:
- No runner code of ours sits in skills/skill-creator/. The runner calls three pieces in it: `scripts.aggregate_benchmark` (misc/evals/Makefile:155), `agents/grader.md` (misc/evals/scripts/run_task_evals.py:71) and `scripts/quick_validate.py` (misc/evals/scripts/run_all_evals.py:98).
- skills/skill-creator/ is vendored (it holds .vendor-sha, 1780c5e5). .github/scripts/vendored-guard.sh:2-5 fails any pull request that edits a vendored folder unless it is a vendor sync, and "the next sync overwrites local edits". So those three pieces can change under the runner at any sync, and we cannot fix them in place.

Recommendation: if C1 is picked, copy the three pieces into misc/evals/scripts/ once, each with the vendored sha it was copied from, and point the runner at the copies. skills/skill-creator/ stays vendored and unchanged. A later sync then changes nothing under the runner, and a change to a copy is an ordinary reviewed change. If C2 or C3 is picked, the runner is retired and no move is needed. No file is moved in this trial.

## SREGym for EKS

The feasibility note is sregym-feasibility.md. In short: an EKS adaptation is feasible with conditions. The lighter problem set fits an EKS managed node group cluster, but SREGym's own diagnose-and-fix prompt and judge would mostly measure the agent, not our skills. The fitting use is its apps, fault injectors and ground truth as seeded-fault fixtures for our own skill prompts, graded by our expectations as above.

## Sources read for this trial (2026-11-16)

- This repo at 7efa0776, paths cited inline.
- EKS Best Practices Guide, aws/aws-eks-best-practices at edc514fac86518b50129401c0cffd1f7981d7ec5 (latest/bpg/).
- AWS Price List (GetProducts): AmazonBedrockFoundationModels (Claude Opus 4.6, OpenAI GPT-5.6 Sol, us-west-2), AmazonBedrockAgentCore (us-west-2), AmazonEC2 (NAT Gateway, gp3, m7i.2xlarge, US West (Oregon)), AWSDataTransfer (US West (Oregon)), AmazonEKS (US West (Oregon)).
- https://aws.amazon.com/bedrock/agentcore/pricing/ and https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_Evaluate.html.
- `claude plugin eval --help`, `claude plugin validate`, `kiro-cli --help`, `codex exec --help`, run with no model call.
- Docs and source for the SREGym note, listed in its Sources table.
