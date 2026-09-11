---
title: "eks-well-architected-review"
description: "Deterministic AWS Well-Architected Framework review of an Amazon EKS cluster. Unofficial — not the AWS Well-Architected Tool, no official EKS lens exists, and it maps to no compliance framework (CIS, PCI or otherwise). Collects live data via kubectl and aws, scores it across five of the six pillars (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization; not Sustainability, not cluster-observable) using fixed jq detections so scores are stable, separates measured from governance findings, applies a coverage gate so thin clusters cannot score well, and renders a self-contained HTML report. Use when asked to review, audit or score an EKS cluster against the Well-Architected Framework, assess its cost hygiene, or get a prioritized plan to raise that score. Not for operational audits (eks-operation-review), dollar cost analysis (eks-cost-intelligence), inventory (eks-recon), static advice (eks-best-practices), hardening (eks-security), or design documents (eks-design)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/SKILL.md). Edit the source, not this page.
:::


# EKS Well-Architected Review

Guide a complete, **deterministic** AWS Well-Architected Framework review of an Amazon EKS cluster.
You collect live cluster data once, score it with **fixed `jq` detections** (the thresholds live inside
the commands, not in your judgment), and render a scored HTML report with a deterministic renderer.

**All data stays local. No external services are called.**

## When NOT to use this

This skill does one thing: a full, scored, five-pillar Well-Architected review of **one** EKS cluster from
a single point-in-time snapshot. It always collects everything and always scores all five pillars — there
is no partial mode. Reach for something else when:

| You want | Use instead |
|---|---|
| Only a cost number, or a bill breakdown | `eks-cost-intelligence` — it is the dollar-denominated one. This skill's Cost pillar measures cost *hygiene*, and getting it means running the whole review. |
| Only a security scan, or a compliance benchmark (CIS, PCI, HIPAA) | `eks-security`. This skill's Security questions are configuration-presence checks, not a benchmark, and they map to no compliance framework. |
| To know whether a cluster is healthy or an incident is ongoing | `eks-operation-review` for operational posture; a live health check for an incident. Every score here describes *declared configuration*; the liveness ratios are disclosure, not diagnosis. |
| To plan or validate a Kubernetes version upgrade | `eks-upgrade-check`. This skill reports the support status of the version it finds; it does not test workload compatibility. |
| An inventory of what is running | `eks-recon`. Collection produces one as a byproduct, but scoring 132 questions to get it is the wrong shape. |
| Advice, or a design document, rather than a score | `eks-best-practices` for a judgement call; `eks-design` for a written design. This skill grades what exists and does not propose an architecture. |
| To *change* anything | Nothing here. This skill is read-only — see the hard rule below. |
| To review more than one cluster | Run it once per cluster. There is no multi-cluster mode, and the collection is bound to a single cluster on purpose. |

### Framework areas with no question at all

The list below is exhaustive for whole areas, not a wishlist. **Those are genuine gaps, not implied
passes** — and because the list is specific, read it as the boundary of what was checked:

- **Sustainability** — the whole pillar. Not deterministically observable from cluster state.
- **Security / Incident response** — none of the 57 Security questions covers it, on either track.
- **Security / Detection** — near-absent rather than absent. `ope-6` checks control-plane audit-log
  types and `sec-33` credits runtime monitoring, but `sec-33` passes on an *addon name* containing
  `guardduty` or a pod named `guardduty`/`falco`/`sysdig`/`tetragon`; it never reads a GuardDuty
  detector or its EKS Protection state. There is no VPC Flow Logs question.
- **Reliability / Foundations** — no service-quota question (REL01). Nothing checks EKS, EC2, ENI or
  ELB limits against current usage. The `quota` questions in this skill are Kubernetes
  `ResourceQuota` objects (`cost-1`), which is a different thing.
- **Reliability / Failure management** — no tested-restore or recovery-drill question at any severity.
  `rel-10`/`rel-12` ask whether snapshot classes and snapshot *policies* exist, on the governance
  track only; nothing asks whether a restore has ever been performed.
- **Cost / Practice Cloud Financial Management** — no AWS Budgets and no Cost Anomaly Detection question.
- **Operational Excellence / Evolve** — no game-day and no post-incident-review question.

Narrower gaps: **IPv6** clusters and **multi-tenancy isolation depth** are not assessed. **Windows**
is partly assessed: `podsec-1` deliberately includes Windows pods and reads
`windowsOptions.runAsUserName` alongside `runAsNonRoot`, while `podsec-5` explicitly excludes them.
Windows node pools as such — node hardening, GMSA, the Windows-specific parts of the CNI — are not
assessed.

> ## Read-only — hard rule
>
> **This skill assesses. It does not change anything.** Every AWS call it makes is a
> `describe-*`/`list-*`, and every Kubernetes call is `kubectl get`. You must not run a call that
> creates, modifies, deletes, tags, scales, drains, patches, applies or annotates — not to "verify" a
> finding, not to "test" a remediation, not because the user's phrasing sounded like consent to fix
> something. If a review appears to need a write to proceed, it does not: report what you could not
> observe instead.
>
> **`allowed-tools` grants three scripts, two `export` forms, and the handful of bare `aws`/`kubectl`/`jq`
> commands the workflow runs directly — nothing else.** The bulk of the work happens inside
> `assets/collect.sh`, `assets/reduce.sh` and `assets/render-report.py`, all of which ship and can be read
> before you approve them. That is the point: one reviewable grant per script beats a long list of command
> prefixes.
>
> `allowed-tools` **grants; it never restricts.** A command it does not cover is not blocked — it falls
> through to the normal permission flow, which prompts in the interactive modes and is denied outright in
> `dontAsk`, where an unattended run lives. So an unmatched command in this workflow is a bug, not a
> safety feature. Every command in the steps below is written in the form its grant spells, with one
> disclosed exception — the Step 5 scorer blocks, at the end of this block.
>
> It used to read `Bash(aws:*) Bash(kubectl:*)`, which pre-authorised `delete-cluster` and `kubectl
> delete` on a cluster the operator may well have believed was only being looked at. Replacing that with
> a list of narrow `Bash(aws eks describe-cluster:*)`-style grants looked safer but was **worse in
> practice**: collection ran through retry wrappers, so the command text a permission rule sees began
> with the wrapper name, the narrow grants matched almost nothing, every call prompted, and the only
> escape from the prompting was to re-grant `Bash(aws:*)`. A guard that produces prompt fatigue is a
> guard that gets switched off.
>
> **The script paths are `${CLAUDE_SKILL_DIR}` in the grant and `${CLAUDE_SKILL_DIR}` in the body, and
> that identity is the whole mechanism.** Claude Code substitutes `${CLAUDE_SKILL_DIR}` in two places —
> the skill's markdown content and the Bash rules in `allowed-tools` — precisely so a skill can run a
> bundled script without a prompt. Both sides expand to the same absolute path, so the rule matches the
> command the body tells you to run. Keep them character-identical: a Bash rule matches literal command
> text, and quotes are not stripped (`Bash(git push *)` does not match `git 'push' origin main`), so
> re-quoting or re-spelling an invocation stops it matching and puts the prompt back. Both sides are
> written unquoted, which is the form the documented example uses; a skill directory path containing a
> space would still word-split once the shell has it. The substitution applies to Bash rules only, which
> is why the `Read`/`Edit` rules below use a path glob rather than the variable.
>
> **`Read`/`Edit` are scoped too** — the skill's own tree, to load `references/`, and the `eks-war-*`
> work dir, for `$WORK/analysis.md` and the collected JSON. Granted bare, as they once were, they
> authorise every file the process can reach, `~/.aws/credentials` and `~/.ssh` included, inside a
> frontmatter whose whole argument is narrow grants. `Edit`, not `Write`: Claude Code checks file
> permissions against `Edit(path)` and `Read(path)` rules only, accepts a `Write(path)` rule without
> ever consulting it, and warns about it at startup — so the `Write(//**/eks-war-*/**)` this line used
> to carry did nothing at all.
>
> **Those three rules scope the native `Read`/`Write`/`Edit` tools, and nothing else.** A script invoked
> through a Bash grant does its own file I/O as a subprocess, which no `Read`/`Edit` rule reaches: what
> `collect.sh` writes and where `render-report.py -o` writes are decided inside those programs, not by
> the glob. So a work dir renamed off `eks-war-*` does **not** prompt — `collect.sh` still writes it.
> Confinement of the work dir comes from `collect.sh` validating `$CLUSTER` before that name is used to
> build `$WORK` — an unvalidated `$CLUSTER` was itself the escape, since `$WORK` is derived from it — and
> not from the glob. An explicitly exported `$WORK` is a caller's deliberate choice and is not
> path-restricted. Two of the grants above are the wide ones and it is worth naming them:
> `Bash(jq:*)` can read any file this process can reach, and `render-report.py -o` can write anywhere
> the process can write. Both are read-then-write-one-file tools rather than destructive verbs, but
> "narrow grants" describes the `aws`/`kubectl` list, not these.
>
> `aws eks update-kubeconfig` writes only to the local kubeconfig, never to AWS — but note it mutates the
> shared `~/.kube/config` and will overwrite an existing context of the same `--alias`. The only
> `mkdir`/`rm` in the skill are inside `collect.sh`, and they act on the `$WORK` that `collect.sh`
> itself derives from the cluster name it has just validated.
>
> **The Step 5 pillar scorer blocks are the one part of the run no grant can cover, and that is a known
> defect.** Each block defines shell functions (`emit`, `g`, `m`, `m2`, …) and then calls them dozens of
> times; a Bash rule matches literal command text, and `m sec-1 cluster '…'` matches nothing in the list
> above. Those calls therefore go through the normal permission flow. Moving the blocks into a script,
> the way collection already is, is the fix; it has not been done. Do not "solve" it by re-granting
> `Bash(aws:*)` or `Bash(kubectl:*)` — the scorers do not call either; they only read `$WORK/*.json`.
>
> **The remediation commands in `references/` are report content, not a script to run.** They are
> written for the reader to apply themselves, deliberately, against their own change process — some
> delete PersistentVolumes or revoke security group rules. Quote them in the report. Never execute
> them, and never offer to.

> **Unofficial review.** This is not the AWS Well-Architected Tool and produces no AWS-recorded
> workload review. AWS publishes no Well-Architected lens for Amazon EKS or Kubernetes — the closest
> official lens, Container Build, covers the container build process rather than cluster operation. The
> questions here are this skill's own interpretation of Well-Architected guidance applied to EKS, and
> cover **five of the framework's six pillars** (Sustainability is not assessed — it is not
> deterministically observable from cluster state).
>
> **Every score measures configuration present at collection time** — not runtime behaviour, and not
> compliance with any standard. A pass means the setting was found, not that it works or was tested.

## Why this skill is deterministic

Every scored question is answered by a `jq` command that reads the collected JSON and prints exactly one
token — `all`, `most`, `some`, `none`, or `na`. You run the command; you do **not** eyeball JSON or do
arithmetic. Given the same cluster data, the score is identical on every run.

**The guarantee is scoped to one path: collected JSON → scorers → `reduce.sh` → `render-report.py`.**
Know which surface you are reading:

| Surface | Machine-generated? |
|---|---|
| `results.jsonl`, `scores.json` | **yes** — fixed `jq`, no judgement |
| `report.html` (via `assets/render-report.py`) | **yes** — scores copied from `scores.json`, resource lists re-derived from the collected JSON; byte-identical for the same work dir |
| Anything you type in chat, or a hand-written markdown report | **no** — agent-transcribed |
| Governance answers in `interactive` mode | **no** — interview-transcribed |
| Cost opportunities, action-plan ordering, remediation prose | **no** — your judgement, deliberately |

Your free-form work is the narrative — never the numbers. If you find yourself retyping a score into a
table by hand, render the HTML instead: a transcribed number is not a deterministic one.

## Two tracks — never blended

| Track | What | How scored |
|-------|------|-----------|
| **Measured** | Anything provable from `aws`/`kubectl` JSON | Deterministic `jq`. This is the headline score. |
| **Governance** | Process/organizational questions with no cluster-observable signal (upgrade process, change management, compliance-scanning cadence, environment separation, secret-rotation policy) | Only from user answers. Reported separately as "N of M answered." Never folded into the measured score. |

## Two modes

- **`auto`** (default): collect, run measured detections, apply the coverage gate, report the measured
  score. Governance questions are listed as **Not Assessed** — never guessed, never scored `none`.
- **`interactive`**: same as `auto`, plus one batched governance interview — **after collection**, so
  questions the data already answers or moots are skipped, but **before** the pillar scorer blocks run
  (Step 6 says why) — and a separate Governance score.

Default to `auto` unless the user asks to be interviewed.

## Prerequisites

Verify all three succeed:

```bash
kubectl version --client && aws --version && aws sts get-caller-identity
```

These prove the tooling and your AWS identity, not that you can reach the cluster under review — a bare
`kubectl get nodes` here would only prove that *some* context works. Connectivity to the right cluster is
confirmed at the end of Step 1, against the context Step 1 has just created.

## Workflow

> **Every fenced block below is one Bash call, and environment variables do not survive to the next
> one.** Claude Code runs each Bash command in its own process: an `export` in one call is gone in the
> next. Commands joined inside a single block — on separate lines or with `&&` — do share one shell, so
> an `export` reaches the commands *below it in the same block*. That is why this preamble is repeated at
> the head of every block that reads one of these four variables, including each pillar scorer block in
> Step 5 (they open with `W="$WORK"`):
>
> ```bash
> export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
> export WORK="$PWD/eks-war-$CLUSTER"
> ```
>
> Run every block from the same working directory, since `$WORK` is derived from `$PWD`. Two grants —
> `Bash(export CLUSTER=*)` and `Bash(export WORK=*)` — cover these two lines wherever they appear, and
> nothing else: a permission rule matching `export CLUSTER=…` authorises one shell builtin that sets a
> variable. Keep the values literal. Write them as two separate `export` commands, not as an inline
> `CLUSTER=… REGION=… some-script` prefix: Claude Code strips a leading assignment only for a fixed
> known-safe set of variable names, and an allow rule will not match past an assignment of any other
> variable, so the inline form stops the script's own grant matching.

### Step 1 — Identify the cluster

```bash
aws eks list-clusters --region <REGION> --output json
aws eks describe-cluster --name <CLUSTER> --region <REGION> --output json
```

Record: cluster name, region, Kubernetes version, VPC ID.

**Then bind `kubectl` to that same cluster explicitly.** This is required, not optional:

```bash
aws eks update-kubeconfig --name <CLUSTER> --region <REGION> --alias <CLUSTER>
kubectl get nodes --context <CLUSTER>     # the connectivity check deferred from Prerequisites
```

`--alias <CLUSTER>` makes the context name equal to the cluster name. That is what `KCTX` is set to in
the preamble above and what `--context` names on every `kubectl` call — one string, so the two halves of
the review cannot drift apart. Substitute the literal name here rather than `$KCTX`: this block runs
before any preamble and needs no variable.

The three bundled scripts are invoked as `${CLAUDE_SKILL_DIR}/assets/…`. There is nothing to export for
them: Claude Code substitutes that variable into both the command and its grant, so the paths resolve
from any working directory without a prompt.

The AWS half of this review comes from `describe-cluster`; the Kubernetes half comes from whatever
`kubectl` points at. If those are different clusters the review still completes and still passes the
validation gate — every required file present and valid JSON — but the report names one cluster while
grading another's workloads. `assets/collect.sh` therefore refuses to collect unless the kubeconfig endpoint for
`$KCTX` matches `.cluster.endpoint` from `describe-cluster`, and routes every `kubectl` call it makes
through `--context "$KCTX"`.

Do **not** rely on `kubectl config current-context`. It makes an unattended run silently inherit
whichever context was last selected, which is the exact failure this binding prevents.

### Step 2 — Collect cluster data into a work directory

Collect **once** into fixed filenames. All later steps read those files, so this is the only step that
touches the cluster.

```bash
export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
export WORK="$PWD/eks-war-$CLUSTER"
${CLAUDE_SKILL_DIR}/assets/collect.sh
```

`collect.sh` reads `CLUSTER`, `REGION` and `KCTX` from its environment and has no defaults for any of
them, which is why the preamble is in this block and not left behind in Step 1. It validates the cluster
name before deriving `$WORK` from it, and takes `$WORK` from the environment if set, otherwise
`./eks-war-$CLUSTER` — the same path the preamble computes.

The script does the whole collection and ends with a validation gate. **If it exits non-zero, stop** —
it has refused because the data is incomplete or the kubeconfig points at a different cluster than
`--name`, and scoring either would produce a confident wrong answer. Do not work around it, and do not
re-run the individual commands by hand to "get past" it.

[references/workflow.md](references/workflow) documents what it collects and why it refuses.

Missing/empty collections are expected on some clusters — the detections treat an empty list as "none of
that resource exists," which is a valid state, not an error. That is different from a call *failing*,
which the script treats as a hard error.

### Step 3 — Read the cluster's compute mode (for the narrative, not for the scorers)

```bash
export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
export WORK="$PWD/eks-war-$CLUSTER"
jq -r '.cluster.computeConfig.enabled == true' "$WORK/cluster.json"        # EKS Auto Mode?
jq '[.items[]] | length' "$WORK/nodes.json"                                 # nodes
jq '[.items[] | select(.metadata.namespace|test("^kube-system$|^kube-node-lease$|^kube-public$")|not)] | length' "$WORK/pods.json"  # workload pods
jq '[.items[] | select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")] | length' "$WORK/nodes.json"  # Fargate nodes
jq '.fargateProfileNames | length' "$WORK/fargate.json"                     # Fargate profiles
jq '[.items[] | select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")] | length' "$WORK/nodes.json"  # EC2 nodes
```

Name the mode in your narrative and in the report header — `Standard`, `Auto` (`computeConfig.enabled`
is true), or `Fargate-only` (Fargate profiles exist and no EC2 node does).

**These numbers set no flags and the scorers do not read them.** Every mode-dependent question decides
applicability inside its own `jq`, from the same collected files: `fargate-4` returns `na` when
`fargateProfileNames` is empty, `ope-15` returns `na` when no node is an EC2 node, `sec-28` returns `na`
on a Consul mesh. There is no `$AUTO_MODE` and no `$EC2_NODES` — no scorer reads a shell variable other than
`$WORK`, and a flag exported here would silently do nothing. Recomputing per question is also what
keeps the detection and its published `jq` the same text, which is the determinism guarantee.

### Step 4 — Viability and liveness are enforced by the reducer, not by you

**You do not implement these gates.** `assets/reduce.sh` evaluates them from `nodes.json` and
`pods.json` and writes the outcome into `scores.json`, so every surface — the chat headline, the
markdown table and the HTML report — reads the same verdict. Report what it emits; do not re-derive it.

They were previously prose here plus Python in the renderer, and the two disagreed: the HTML withheld a
dead cluster's score while the reducer still emitted a number, so the chat and markdown paths published
the number the report itself refused to.

| `scores.json` | Condition | What to report |
|---|---|---|
| `technical_overall: "NOT VIABLE — no data plane"` | `nodes_total == 0` | **Stop scoring.** Report the control-plane facts, the applicable-question count, and nothing else. An empty cluster must never score "Excellent". |
| `technical_overall: "NOT HEALTHY — no node is Ready"` | nodes exist, `nodes_ready == 0` | Report the withholding and its reason. Pillar scores **may** still be shown, labelled as describing declared configuration only. |
| `liveness.warning` is non-null | under half the workload pods are `Running` | Publish the score, and carry the warning prominently with the counts. |
| otherwise | — | Score normally. |

`nodes_total == 0` is sufficient on its own. It used to require zero nodes **and** zero workload pods,
which let a cluster with no nodes but declared pods escape both gates — viability wanted zero pods, and
liveness needed at least one node to inspect — and publish a full numeric score. Pods without nodes are
manifests, not running software.

**Always report both ratios in the header**, healthy or not: `3 nodes (3 Ready) · 14 workload pods
(14 Running)`, straight from `liveness`. A reader must be able to see `3 nodes (0 Ready)` beside any
score without expanding anything.

**Judge only what is running, but do not filter the denominators.** These are different things and
conflating them inverts the score. Do **not** restrict the ratio detections to `Running` pods: a cluster
where 10 of 15 pods are `Pending` for want of schedulable resources would then score `perf-1` as
`5/5 = all` — a perfect result on resource requests, for a cluster that cannot schedule its workload.
`CrashLoopBackOff` also reports `phase: Running`, so phase filtering would not even catch the commonest
failure. Withhold the headline instead.

**This is a disclosure, not a refusal** in the `NOT HEALTHY` and warning cases. A cluster mid-deploy or
mid-upgrade legitimately shows Pending pods and NotReady nodes, and a batch cluster legitimately sits at
zero running pods between jobs. Say what was observed and let the reader judge.

### Step 5 — Run the measured detections (per pillar)

Run all five pillar scorers. Each appends one JSONL line per question to `$WORK/results.jsonl`:

```
{"pillar":"security","id":"sec-1","track":"measured","state":"all","detail":"private endpoint enabled"}
```

```bash
export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
export WORK="$PWD/eks-war-$CLUSTER"
${CLAUDE_SKILL_DIR}/assets/score.sh operational-excellence "$WORK"
${CLAUDE_SKILL_DIR}/assets/score.sh security "$WORK"
${CLAUDE_SKILL_DIR}/assets/score.sh reliability "$WORK"
${CLAUDE_SKILL_DIR}/assets/score.sh performance-efficiency "$WORK"
${CLAUDE_SKILL_DIR}/assets/score.sh cost-optimization "$WORK"
```

**Check each exit status. If any is non-zero, stop** — a partial `results.jsonl` must never be scored.
`score.sh` also refuses a pillar that has already been scored, rather than appending every id a second
time and leaving `reduce.sh` to discover the duplicates two steps later.

`score.sh` does not carry a copy of the detections. It extracts the first fenced `bash` block — the
`## <Pillar> scorer` block — from the reference file below and runs it, so what executes is exactly what
a reader sees. It refuses a block that does not define `emit()`, so a per-question `**Commands:**` or
`**Remediation:**` snippet can never be executed by mistake; some of those delete PersistentVolumes.

| Pillar | Block extracted from |
|---|---|
| Operational Excellence | [references/operational-excellence.md](references/operational-excellence) |
| Security — all 57 questions in one block | [references/security/identity-access.md](references/security/identity-access) |
| Reliability | [references/reliability.md](references/reliability) |
| Performance Efficiency | [references/performance-efficiency.md](references/performance-efficiency) |
| Cost Optimization | [references/cost-optimization.md](references/cost-optimization) |

The other four security files (data-protection, network, workload-security, governance-compliance) hold
per-question rationale and remediation you load when writing findings; they carry no scorer block.

**Do not paste the blocks into a shell instead.** That was the previous instruction and it could not be
authorised: each block defines shell functions (`emit`, `g`, `m`, `m2`, `m3`, `m4`) and then calls them
~130 times as `m sec-1 cluster '…'`. A Bash permission rule matches literal command text, so no rule can
match a shell-function name — every one of those calls fell through to the normal permission flow,
prompting interactively and failing outright under a no-prompt policy, so an unattended run could not
reach a score. This is the same wrapper-function problem that moved collection into `collect.sh`; it was
still sitting in the scoring half. One grant per `score.sh` invocation covers all of it, and the
extraction is what the test harness has always used — so the tested path and the shipped path are now
the same path.

The measured (`m`/`m2`/`m3`/`m4`) thresholds are the determinism guarantee and are not yours to edit. The
`g` calls are the one thing that varies, and only in `interactive` mode — see Step 6, which now feeds the
interview in through a file rather than asking you to rewrite the block.

Also run [references/cost-analysis.md](references/cost-analysis) (savings opportunities) to
inform the narrative.

**Drift detection was removed** (the file `references/drift-detection.md` no longer exists). Its 10 checks were a spot
check, not drift detection — nothing stored a prior state to compare against. 8 of the 10 duplicated
a scored question verbatim; 2 contradicted theirs (its NetworkPolicy and PDB rows passed on
"more than zero covered" while `sec-4`/`rel-2` graded the ratio, so a High-severity gap showed green);
and 2 mapped only to a governance question the report declines to assess. The headline
"10 of 10 passing" then undercut the actual verdict. Real drift detection needs a stored previous run
to diff against. A single review therefore cannot say whether a finding is new, and must not imply it: report the state observed, not a trend.

### Step 6 — Governance questions

- **`auto` mode:** nothing to do. Each pillar's `g` calls already emit
  `{"...","track":"governance","state":"unknown"}` for every governance id, and they are reported as
  Not Assessed.
- **`interactive` mode:** **interview first, then run Step 5** — in that order. Present the governance
  questions (each pillar file lists them) as one batch, map the answers with the fixed rule below, and
  write them to **`$WORK/governance.tsv`**, one per line, tab-separated — `<id>` `<state>` `<note>`:

  ```
  ope-9	all	quarterly upgrade window, owned by the platform team
  rel-12	none	no snapshot policy; team confirmed none exists
  sec-13	na	single-tenant cluster, no tenant isolation requirement
  ```

  `score.sh` substitutes each answer into the block as it extracts it, so the interview reaches the
  scorer without anyone editing a detection. `<state>` must be one of `all most some none na unknown`;
  `score.sh` rejects anything else by name, and an id belonging to another pillar is ignored by the
  pillar that does not own it. Lines starting `#` are comments. Omit an id entirely and it stays
  `unknown` → Not Assessed, which is the honest answer for a question nobody answered.

  Write the file **before** Step 5, not after. There is one record per question: `reduce.sh` refuses a
  duplicate question id and exits 1 without writing `scores.json`, naming the ids — so a second record
  appended after the fact does not inflate the governance denominator, it blocks the whole review.

  This replaces an earlier instruction to hand-edit each `g <id>` call inside the fenced block into an
  `emit <id> governance <state> "<note>"` call. That asked the agent to retype the one part of the
  determinism spine that is meant to be executed rather than transcribed, and it cannot be permission-
  matched — see Step 5.

### Step 7 — Reduce to scores (deterministic)

Run the reducer and **write its output to `$WORK/scores.json`**. It computes per-pillar measured
scores with the coverage gate, the technical overall, and the separate governance summary:

```bash
export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
export WORK="$PWD/eks-war-$CLUSTER"
${CLAUDE_SKILL_DIR}/assets/reduce.sh "$WORK" > "$WORK/scores.json"
# The headline, then the liveness line that must accompany it, then the pillars.
jq -r '.technical_overall,
       "nodes \(.liveness.nodes_total) (\(.liveness.nodes_ready) Ready) · workload pods \(.liveness.workload_pods) (\(.liveness.pods_running) Running)",
       (.liveness.withheld_reason // .liveness.warning // empty),
       (.pillars[]|"\(.pillar) \(.score) (coverage \(.coverage)%)")' "$WORK/scores.json"
```

`.technical_overall` is the **only** headline you may report. When it is a string — `NOT VIABLE — no
data plane` or `NOT HEALTHY — no node is Ready` — report that string, not a number, and not
`liveness.suppressed_overall`. That field exists so the report can say what configuration alone would
have scored; it is context, never the verdict. Quoting it as the headline reintroduces exactly the
defect this contract removes.

The redirect is not optional. `assets/render-report.py` reads `$WORK/scores.json` and exits without
it, and nothing else writes that file — Step 7 used to print to stdout only, leaving the agent to infer
a redirect on the one path the determinism guarantee depends on. The `>` target is checked separately
from the command: Claude Code checks a redirect target against your `Edit` rules and working
directories, not against the reducer's Bash grant. `$WORK` sits under `$PWD`, so it is inside a working
directory; the `Edit(//**/eks-war-*/**)` grant covers it wherever it is.

**Check the exit status, and if it is non-zero stop and fix the cause** — the same discipline Step 2
applies to `collect.sh`, and do not work around it either. It refuses on a missing or empty
`results.jsonl`, a missing / non-JSON / `.items`-less `nodes.json` or `pods.json`, a `results.jsonl` line
that is not one JSON object, a duplicate question id, and an illegal `state`. All of them exit 1 with a
`reduce.sh:` diagnostic *before* a byte of output, so the redirect leaves a **0-byte `scores.json`** and
the failure resurfaces two steps later as a renderer complaint about a malformed file. Read the message
here, where it still names what was wrong.

The severity weights live in `assets/reduce.sh` (`sev()`). `assets/render-report.py` keeps its own copy
(`SEV3`/`SEV1`) for the risk-weight chips and the improvement-plan ordering. **Nothing enforces that the
two agree** — no shipped check diffs them — so **edit both or neither**: changing one alone silently
leaves the report's risk chips and plan ordering ranking questions by a severity the scores were not
computed from. Do not retype the reducer's jq inline either: a transcribed reducer is a second source of
truth for every score in the report.

**Rating bands** (technical overall and each pillar): ≥90 Excellent, 80–89 Good, 70–79 Fair,
60–69 Needs improvement, <60 Poor. **Risk:** ≥80 LOW, ≥60 MEDIUM, <60 HIGH — that same number restated,
not an assessed threat level, and liftable by clearing Low-severity items while a High-severity control
stays missing. See **Scoring model** before presenting either as a verdict.

### Step 8 — Render the HTML report (deterministic)

Run the renderer. **Do not hand-write the HTML** — it is generated from the same files the scorers
wrote, so the report inherits the determinism the rest of the skill guarantees:

```bash
export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
export WORK="$PWD/eks-war-$CLUSTER"
python3 ${CLAUDE_SKILL_DIR}/assets/render-report.py "$WORK" -o "$WORK/report.html"        # follows the reader's OS
python3 ${CLAUDE_SKILL_DIR}/assets/render-report.py "$WORK" -o "$WORK/report.html" --both # also writes report-dark.html
```

`${CLAUDE_SKILL_DIR}` is what makes the bare `assets/...` form unnecessary: that only resolved when the
shell happened to be sitting in the skill root, which is not where `$WORK` is. The renderer finds
`references/` from its own file location, so nothing has to point it there. `-o` is an argument, not a
shell redirect, so the file it names is written by the program itself and no `Edit` rule is consulted
for it.

`--theme auto` (default) ships both token sets, starts from the reader's `prefers-color-scheme`, and
puts a **light/dark toggle in the top right** that remembers the choice in `localStorage`. All four
states (base light, OS dark, OS-dark-but-pinned-light, pinned dark) are resolved by CSS, so the
report is correct before any script runs; the toggle button ships `hidden` and is revealed by the
inline script, so a viewer with JavaScript stripped sees no dead control.

Use `--theme dark` or `--theme light` to **pin** one — no toggle, no script — for when the file is
emailed, attached to a ticket, or printed and the reader's OS setting is not yours to predict.

**Tell the user the report is internal before they forward it.** It names the cluster, region, node and
volume IDs, security group and subnet IDs, and IAM role/OIDC ARNs — which carry the AWS account ID.
That specificity is deliberate: it is what lets a reader verify a finding instead of trusting it. It also
describes the environment to anyone who receives the file, so the account ID and resource identifiers
should be masked before it leaves the cluster owner's circle. Identifiers for resources *outside* the
reviewed cluster are reported as counts, not named, so the report does not widen its own blast radius.
`--both` writes the light file plus a pinned `-dark` sibling. `--no-toggle` keeps `auto` behaviour
but ships no script at all.

Still one file either way: the toggle adds ~20 lines of inline JavaScript and two inline SVG icons.
No `src`, no `@import`, no `fetch` — verifiable by grepping the output file, because a report that
reached the network on open would break the skill's "all data stays local" contract.

**Each finding carries a named resource list.** "3/3 core addons" is a claim the reader cannot check;
`coredns, kube-proxy, vpc-cni` is one they can verify in seconds. Every historic scoping bug in this
skill was a *correct count over the wrong set* — an unrelated security group, another cluster's
volumes, AWS-installed Deployments counted as the operator's. The lists make that visible, and they
also name what was **excluded** and why, so the scoping rule is auditable rather than trusted.

The lists are a second reading of the same data, so wherever a check reports an `N/M` count the
renderer recomputes it from its own list and **marks the finding unverified, banners it at the top of
the report, and exits non-zero** on any disagreement — a list that contradicts its score would be worse
than no list. Currently 65 extractors (countable from `assets/render-report.py`).
Questions without an extractor simply show no list.

Where a check is boolean or reads a field rather than counting objects, there is no total to recompute
against, and the panel says so in those words instead of showing a tick. That distinction is the point:
a check the report *cannot* cross-check must not look as though it did.

Panel order is deliberate: *why it matters* → *what we found* → *how to fix* → *how this was measured*
(nested, collapsed). The verbatim `jq` serves a narrow audience — auditing the tool, disputing a
finding, maintaining the skill — so it sits last rather than pushing the fix out of view.

**No JSON export.** Scraping the rendered HTML for all findings and parsing an equivalent JSON blob
differ by well under a millisecond, so a second artifact buys nothing for a program; and an LLM reads
the whole file regardless, so an embedded copy would only add tokens. Rows instead carry
`data-qid` / `data-state` / `data-severity` / `data-pillar` attributes, which makes scraping reliable at
zero cost.

It reads `scores.json`, `results.jsonl` and the collected cluster JSON, and emits one
self-contained file — no network requests, no external CSS or JS, so it opens offline and no data
leaves the machine. Styling is the [Cloudscape Design System](https://cloudscape.aws.dev): Amazon
Ember with the documented monospace fallback for IDs and measured values, container/table/status
indicator/badge/alert surfaces, and the light **and** dark token sets wired to
`prefers-color-scheme`. Question text is read from the `references/` files, so it cannot drift from
the scorers.

Every **score** in the HTML is copied from `scores.json` and `results.jsonl` — the renderer never
recomputes one, so if a score looks wrong the scorer is wrong. Four things it does derive itself: the
resource lists above (each reimplementing its question's scoping), the thin-evidence marker (coverage
under 70%), the Immediate/Short-term/Strategic tiering (severity weight × how far short the state
fell), and the rating and risk labels (mapped from the score). A list that contradicts its score
therefore means one of the two halves is wrong and neither is presumed right — hence the banner and the
non-zero exit instead of a chosen winner.

Tell the user where the file is and summarise the headline result in chat: the technical score and
rating (or the withheld/not-viable reason), the per-pillar table, and the top 3 priorities.

**If the renderer exits non-zero, say so in that summary.** After a `wrote …` line, that is the
resource-list cross-check failing: findings whose list contradicts their own count, named on stderr and
bannered in the report. Name them and say the report flags them as untrustworthy — summarising such a run
as clean is the one failure that cross-check exists to prevent. Before any `wrote …` line, it refused the
inputs (missing or malformed `scores.json`, unwritable `-o` target): fix that and re-run, and do not
hand-write the HTML instead.

#### The narrative half — you still write this

The renderer covers the scored, tabular half. Append the parts that need judgement as markdown
alongside the HTML (`$WORK/analysis.md`), or paste them into chat:

- **Cost Opportunities** — from [references/cost-analysis.md](references/cost-analysis), in
  particular Graviton (Opportunity 1) and the per-workload Spot gap (Opportunity 2). Carry the Spot
  disclaimer verbatim in substance: **staying On-Demand is a legitimate choice.** Label the Cost
  pillar score as **cost hygiene** and state that Spot, Graviton and Extended Support are narrative
  opportunities and **not** in that score, with the cluster's actual posture on all three — a bare
  Cost number reads as "no cost levers taken", which it does not measure. The renderer prints this
  caveat in its Method section, but the specific opportunities are yours to write.
- **Action Plan** — immediate / short-term / strategic, ordered by severity then effort.
- **Remediation wording** for the failing questions, from the per-question prose in each pillar file.

#### If a markdown-only report is explicitly requested

Some contexts (a ticket, a code review, a chat-only session) need plain markdown. Then produce the
sections below instead of the HTML. Otherwise prefer the renderer — it is faster, cannot miscount,
and cannot drift from the design.

1. **Header** — cluster, region, K8s version, node count, mode.

2. **Executive Summary** — technical overall (or `NOT VIABLE` / `WITHHELD`), the pillar table, top 3 priorities.
3. **Coverage & method** — for each pillar: `score (coverage: applicable/total)`. State the mode and, in
   `auto` mode, that governance questions were Not Assessed.
4. **Detailed findings per pillar** — critical / improvement / passing, each citing the question id and the
   `detail` from its JSONL line.
5. **Cost Opportunities** — from cost-analysis.md. Label the Cost pillar score as **cost hygiene**
   and state, next to it, that Spot, Graviton and Extended Support are reported here as narrative
   opportunities and are **not** in that score, together with the cluster's actual posture on all
   three. A bare Cost number reads as "no cost levers taken", which it does not measure — a 100%
   Spot + Graviton cluster scores identically to one on neither. See the disclosure block at the top
   of [references/cost-optimization.md](references/cost-optimization).
6. **Governance** — `interactive`: the score + answers. `auto`: the list of Not Assessed questions.
7. **Action Plan** — immediate / short-term / strategic.

Report header block:

```
EKS Well-Architected Review — <cluster>
Region: <region> | Kubernetes: <version> | Mode: <Standard|Auto|Fargate-only>
Nodes: <count> (<ready> Ready) | Workload pods: <count> (<running> Running)   # from liveness, always shown

Technical Score: <.technical_overall verbatim>
# A number with its Rating, or the withholding string exactly as the reducer emitted it:
#   "NOT VIABLE — no data plane" | "NOT HEALTHY — no node is Ready"
#   "WITHHELD (insufficient pillar coverage)"
# Never substitute liveness.suppressed_overall here.

| Pillar                  | Score        | Coverage | Risk (from score) |
|-------------------------|--------------|----------|--------|
| Operational Excellence  | X/100        | a/t      | LOW    |
| Security                | X/100        | a/t      | MEDIUM |
| Reliability             | X/100        | a/t      | HIGH   |
| Performance Efficiency  | X/100        | a/t      | LOW    |
| Cost Optimization       | X/100        | a/t      | MEDIUM |

Governance: Not Assessed (auto mode)   # or Y/100 (g answered of G) in interactive mode
```

## Scoring model

- **Bucket rule** (inside every detection): percentage ≥90 → `all`, ≥70 → `most`, >0 → `some`, 0 → `none`;
  boolean/presence true → `all`, false → `none`; nothing applicable to measure → `na`.
- **State → score:** all=100, most=75, some=50, none=0. `na` and `unknown` are excluded.
  A control that is entirely absent earns nothing — there is no participation floor. `unknown` is legal
  on the **governance track only**; a measured record carrying it is a bug, and the reducer refuses it.
- **`na` is the only not-applicable token**, on both the measured and the governance track. Not
  `not-applicable`, not `n/a`, not an empty state. The reducer validates the enum before it scores
  anything, and any other spelling costs you the whole reduce step: it prints `illegal state value(s) …
  legal: all most some none na; unknown is legal on the governance track ONLY` and exits 1, having
  written nothing. Fix the scorer that emitted it rather than re-running.
  `na` is excluded from **both** the numerator and the denominator — it does not dilute the score,
  it leaves the question out of it, and the coverage figure is what discloses how many were left out. (Before
  2026-08-21 `none` scored 25, which put a hard floor of 25 under every pillar and compressed
  populated clusters into a narrow ~53–75 band regardless of how bad they were.)
- **Severity weight** — this skill's own, not AWS's: each question is High (3), Medium (2, default), or
  Low (1). The three tiers are an editorial ordering assigned here; no Well-Architected Tool risk level,
  CIS severity or EKS Best Practices tiering maps onto them, so cite them as this review's judgement
  rather than as a published AWS classification. They are still the right thing to prioritise by — see
  `sev()` in the reducer, with the per-question reasoning in [references/severity.md](references/severity).
  A missing High-risk control (public API, no encryption) costs far more than a missing Low-risk extra
  (service mesh, ndots tuning). This lets a cluster that clears all High/Medium risks score high without
  every aspirational practice.
- **A band can be bought with Low-severity items — never read one as a risk summary.** Weights are
  relative *within* a pillar, so where the Lows outnumber the Highs they dominate: Performance
  Efficiency's 8 Low questions carry 8 of its 15 severity points against 3 for its one High question
  (`perf-1`, resource requests). Clearing only the Lows lifts that pillar from Poor to Good — and the
  Risk column, being the score restated, from HIGH to LOW — while `perf-1` still reports most containers
  with no requests at all. Report the High-severity findings directly; the band summarises the
  arithmetic, not the exposure.
- **Pillars are averaged equally although they are not comparable in size — disclose this.** The five hold
  9 to 42 measured questions and 15 to 91 severity points (Performance Efficiency 15, Cost 18,
  Operational Excellence 33, Reliability 42, Security 91), and each still contributes one fifth of the
  overall. A question's pull on the headline is its weight ÷ its pillar's weight ÷ 5, so one
  Medium-severity Cost question moves it several times as far as one High-severity Security question: on
  a real cluster, adding ResourceQuotas to four namespaces raised the overall twice as much as opening
  the Kubernetes API server to `0.0.0.0/0` lowered it. **Take priority from severity weight** — what the
  report's Top priorities and improvement plan are ordered by — never from what would move the number most.
- **Scope:** object checks assess only cluster-owned resources — workload pods (managed `kube-*`/`amazon-*`
  pods reported as context, not scored), custom RBAC roles (built-in `system:`/`eks:` excluded), EBS volumes
  tagged to the cluster, ECR repos referenced by cluster images. You are scored on what you control.
- **Pillar score** = severity-weighted average of applicable measured states, **only if** applicable ≥ 50%
  of the pillar's measured questions (coverage gate). Below that → `INSUFFICIENT` (no number).
- **Technical overall** = rounded average of numeric pillar scores, only if ≥4 pillars are numeric; else
  `WITHHELD`.
- **Governance answer mapping** (interactive): "Yes, fully" → `all`, "Mostly" → `most`, "Partially" →
  `some`, "No" → `none`, "Doesn't apply" → `na`, no answer → `unknown`.

## Notes

- Detections read only from `$WORK/*.json`. An empty **collection** — a file holding zero resources — is a
  valid state and scores as "none of that resource exists". An **absent file** is not the same thing and is
  not yours to substitute for: `assets/reduce.sh` exits 1 when `nodes.json` or `pods.json` is missing,
  because viability and liveness cannot be evaluated without them. Do not fabricate an empty `nodes.json`
  to get past that refusal — it converts a hard stop into `NOT VIABLE — no data plane` on a cluster that
  has nodes. Re-run collection instead.
- Keep numbers from `jq`; keep prose from yourself. If you ever find yourself counting containers by hand,
  stop and run the detection instead.
