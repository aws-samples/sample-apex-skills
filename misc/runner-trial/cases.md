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
- Pass, per run: the positive query loads eks-mcp-server and the negative does not; S2 counts those runs out of 3. A query run that times out or whose process dies keeps triggered and invalid both false, as the runner reads it (misc/evals/scripts/run_triggering.py:170-192 at 7efa0776), so such a run of the negative query counts as a correct negative.
- Runs: 2 queries x 3, with the skill only. The without-skill arm cannot load an absent skill.

### T7: a live read-only run, repeated for the same-answer rule
- Source: misc/evals/eks-recon/evals.json:5 (id 1, live_only at :15).
- Fixtures: none. Needs a running cluster and a read-only kubeconfig. The trial uses an existing read-only kubeconfig for its test cluster. It does not run misc/evals/setup/bootstrap-readonly.sh, so the trial creates no IAM role, policy or access entry. That kubeconfig gets its token by `aws eks get-token` through the profile its exec env names, which the subject's empty HOME does not have, so for each T7 run the C1 driver, as the parent process, assumes that profile's role for a one-hour session from the AWS config file the operator names with `--cluster-aws-config`: name a file outside ~/.aws whose source profile holds no keys. That file holds the profile in `role_arn` plus `source_profile` form, and its source profile must sign in through a `credential_process` line that gives the helper its home back, `/usr/bin/env HOME=<your home> <command>` (the driver does not check this); an SSO or `aws login` source reads its token under ~/.aws and does not qualify. The driver reads only that file: it drops the parent's AWS_* variables, sets the shared credentials file and the boto config to /dev/null and turns off the instance metadata lookup, and runs its `aws` calls with HOME set to an empty private temp dir that it removes after, so nothing in your ~/.aws is read, the AWS CLI's cache, alias file and models included. The helper runs as you, with the home its line gives it; what it reads is your choice. Without `--cluster-aws-config` T7 reads "cannot run". Each run mints its session anew, so a source sign-in that expires or waits for input mid-trial makes that run "cannot run" once the call's 120 s timeout passes. An example file, the first profile named as the kubeconfig's exec env names it, the placeholders yours:

  ```
  [profile cluster-ro]
  role_arn = arn:aws:iam::<account>:role/<read-only role>
  source_profile = signin
  [profile signin]
  credential_process = /usr/bin/env HOME=<your home> <a command that prints credentials as JSON>
  ```

  The subject is not handed that sign-in, though as your OS user it can use it, reaching whatever the source profile's role can (which may be an admin role, not the read-only one), and read the host keys in ~/.aws (Credentials and permissions, below). The driver does not check which role the profile names, so pass the read-only kubeconfig. The subject gets a kubeconfig, mode 600 in a private temp dir, that carries only that session and names no profile or config file. The same dir holds `bin/aws`, a shim that runs the real `aws` on that session with no config file. The runner starts the subject with the shim first on PATH, while the subject's AWS environment, which Claude Code's credential chain reads for the model calls, stays the eval-role session. The shim sets no Region, so a subject `aws` call without `--region` uses the eval run's `AWS_REGION`, not the cluster's. The session keys sit in plain text in the kubeconfig and the shim, so a subject that prints either (`kubectl config view` does) puts them in the run's transcript.md, which the grader reads, and its events.jsonl, from which C3's spans are built: send no T7 run to C3, and share none of it, until the hour has passed. The dir is removed when the run ends (drive_c1.py `live_env`).
- Pass, per run: the report holds each compared field; S2 counts those runs out of 3, and the same-answer result across the three (same / differs / cannot compare) is recorded beside it. A runner that cannot reach the cluster is marked "cannot run", not fail. The C1 driver marks it so when no kubeconfig is given or the cluster session cannot be minted, and, with `--paid`, refuses a kubeconfig path that does not exist, and a `--cluster-aws-config` path that is not a file, which stops the whole invocation; a run whose cluster reads fail is re-marked "cannot run" by hand from its transcript.
- Runs: 2 arms x 3. The same-answer test applies within each arm.

## Credentials and permissions per case

Cites in this section are at main 528dde41. The runner gives the subject and the grader an empty HOME, with no link to the host's ~/.aws, and drops every AWS_* variable of the parent (misc/evals/scripts/run_triggering.py:92 `stage_skill_sandbox`, :117 `stage_empty_sandbox`, :132 `build_subprocess_env`). The only AWS credentials they get are a session of role `apex-eval-bedrock-invoke` in a separate eval account, plus, in T7 only, the cluster session in the subject's kubeconfig and `aws` shim (T7, above). Before the first run the runner assumes that role through profile `apex-eval-admin` of `~/.apex-eval/aws-config` and checks the session with `sts get-caller-identity` against `~/.apex-eval/expected-account`; it refuses to start, with no fallback, when any of that is missing or wrong (run_triggering.py:270 `mint_eval_role_credentials`; misc/evals/README.md:218, Eval-role setup). The C1 driver makes the same check before its first paid run. The subject runs as your OS user with bypassPermissions, so it can read, write and run anything your user can, the runner's environment included (and on an EC2 host, the instance role through the metadata endpoint unless that is blocked); run it as another OS user or in a container for a hard fence (misc/evals/README.md, Eval-role setup); the flag is `--permission-mode bypassPermissions` (misc/evals/scripts/run_task_evals.py:498 and :517).

Role status, 2026-11-19: the eval role exists in the eval account. Its trust names only that account's Admin role, its one inline policy allows only Bedrock model calls and inference-profile reads, and one assume-role through profile `apex-eval-admin` succeeded; no model call has been made on it yet. It has none of the live-eval AWS read set (T7, above, for where T7's reads come from).

| Case | What the case needs from AWS | What the subject gets |
|---|---|---|
| T1, T2, T3, T4, T6 | Model calls on Bedrock only; the prompts are offline (T1 and T4 say not to run aws or kubectl) | The eval-role session |
| T5 | Model calls on Bedrock only | The eval-role session |
| T7 | Model calls on Bedrock, plus read-only cluster and EKS API reads | The eval-role session (model calls only, see Role status above), and a one-hour session of the role the kubeconfig's profile names, minted by the driver for each run (T7, above) |

## Run count

Per runner, for the claude harness:

| Cases | Arms x runs | Old against new | Runs |
|---|---|---|---|
| T1 to T4 | 2 x 3 | 3 each | 9 each, 36 |
| T5, T7 | 2 x 3 | none | 6 each, 12 |
| T6 | 2 queries x 3, with the skill only | none | 6 query runs |

That is 48 task runs plus 6 triggering query runs, and at most one grader call per task run (the driver grades T1, T4 and T7 only: 24 calls, cost-estimate.md:48). Kiro and Codex each run T1 three times with the skill only, staged in a sandbox HOME (`~/.kiro/skills/`, `~/.agents/skills/`), graded by C1's grader: 6 more grader calls (by hand, as evidence for the sized adapters; S5 counts only harnesses a runner drives itself). A runner with no old-against-new mode runs 36 task runs.
