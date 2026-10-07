---
title: "eks-well-architected-review"
description: "Deterministic AWS Well-Architected Framework review of an Amazon EKS cluster (Linux nodes only). Unofficial — not the AWS Well-Architected Tool, no official EKS lens exists, and it maps to no compliance framework (CIS, PCI or otherwise). Collects live data via kubectl and aws, scores it across five of the six pillars (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization; not Sustainability, not cluster-observable) using fixed jq detections so scores are stable, separates measured from governance findings, withholds a pillar score when under half its measured questions apply, and the overall when fewer than four pillars score or no Linux node is Ready, and renders a self-contained HTML report. Use ONLY when the user explicitly asks to run a Well-Architected review (WAFR) of an EKS cluster. Any other request — a cluster audit, score, cost, security, inventory, upgrade, best-practice or design question, even one naming a pillar — belongs to another skill."
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

**Collected files are written only to the work directory, and the rendered report makes no network
requests.** Collection calls the AWS and Kubernetes APIs, and whatever this review prints or reads
(cluster ARNs, the account id, scores, findings) enters this conversation like any other tool output.

## When NOT to use this

This skill does one thing: a full, scored, five-pillar Well-Architected review of **one** EKS cluster from
a single point-in-time snapshot. It always collects everything and always scores all five pillars — there
is no partial mode. Reach for something else when:

| You want | Why this is the wrong tool |
|---|---|
| Only a cost number, or a bill breakdown | A dollar figure is out of scope. This skill's Cost pillar measures cost *hygiene*, and getting it means running the whole review. |
| Only a security scan, or a compliance benchmark (CIS, PCI, HIPAA) | This skill's Security questions are configuration-presence checks, not a benchmark, and they map to no compliance framework. |
| To know whether a cluster is healthy or an incident is ongoing | Every score here describes *declared configuration*, not health; the liveness ratios are disclosure, not diagnosis. |
| To plan or validate a Kubernetes version upgrade | This skill reports, in `ope-20`, whether the upgrade-readiness insights AWS already computes for the cluster pass — it does not itself test workload compatibility or plan an upgrade. |
| An inventory of what is running | Collection produces one as a byproduct, but scoring 132 questions to get it is the wrong shape. |
| Advice, or a design document, rather than a score | This skill grades what exists; it gives no judgement-call advice and does not propose an architecture. |
| To *change* anything | Nothing here. This skill is read-only — see the hard rule below. |
| To review more than one cluster | Run it once per cluster. There is no multi-cluster mode, and the collection is bound to a single cluster on purpose. |

### What counts as "an EKS cluster" here

**Only Amazon EKS running on AWS, and Linux nodes only.** Within that, both compute modes are in scope and judged: **EKS Auto
Mode** (`computeConfig.enabled`) and **EC2** compute — managed node groups, self-managed nodes, Fargate
profiles, and any mix of them. A cluster combining Auto Mode with EC2 node groups is called **mixed-mode**
throughout this skill, and several questions have a dedicated mixed-mode arm so they describe both
populations rather than crediting one and ignoring the other.

**Before Step 1, read [references/workflow.md](references/workflow) §*What counts as "an EKS cluster" here***: what else is judged (EKS Hybrid
Nodes, with the node population partitioned) and what is not (Windows nodes, EKS Anywhere, EKS Connector
clusters), and why. `render-report.py` prints its `SCOPE-PLATFORMS` block verbatim in the report.

In this skill the word **hybrid** means EKS Hybrid Nodes and nothing else: the scorers carry `ishy`,
`hyna()` and `$hy` bindings that all refer to them. A cluster that combines EKS Auto Mode with EC2 node
groups is **mixed-mode**, never "hybrid", precisely so the two cannot be confused.

### Framework areas with no question at all

The list below is exhaustive for whole areas, not a wishlist. **Those are genuine gaps, not implied
passes** — and because the list is specific, read it as the boundary of what was checked.

This list is report content, printed verbatim by `assets/render-report.py`; see [references/workflow.md](references/workflow) §*Report content read from SKILL.md and from this file*.

<!-- NOT-ASSESSED-AREAS:BEGIN — read verbatim by assets/render-report.py. One `- ` bullet per area;
     continuation lines indented two spaces; `**bold**` and `` `code` `` only, no other markup. -->
- **Sustainability** — the whole pillar. Not deterministically observable from cluster state.
- **Security / Incident response** — none of the 57 Security questions covers it, on either track.
- **Security / Detection** — near-absent rather than absent. `ope-6` checks control-plane audit-log
  types and `sec-33` credits runtime monitoring, but `sec-33` passes on an **addon name** containing
  `guardduty` or a DaemonSet pod named `<ds>-<5 chars>` where `<ds>` is `aws-guardduty-agent`, `falco`,
  `sysdig`/`sysdig-<word>…` or `tetragon`, optionally after a `<release>-` prefix; it never
  reads a GuardDuty detector or its EKS Protection state. There is no VPC Flow Logs question.
- **Reliability / Foundations** — no question about service quotas (REL01). Nothing checks EKS, EC2, ENI or
  ELB limits against current usage. The `quota` questions in this skill are Kubernetes
  `ResourceQuota` objects (`cost-1`), which is a different thing.
- **Reliability / Failure management** — no tested-restore or recovery-drill question at any severity.
  `rel-10`/`rel-12` ask whether snapshot classes and snapshot *policies* exist, on the governance
  track only; nothing asks whether a restore has ever been performed.
- **Cost / Practice Cloud Financial Management** — no AWS Budgets and no Cost Anomaly Detection question.
- **Cost / Optimize over time** — nothing asks whether you regularly check for newer, cheaper AWS services,
  or whether the time spent saving money is worth what it saves; without that habit, costs stay higher than
  they need to as better options appear.
- **Operational Excellence / Organization** — nothing asks who owns each workload, how priorities are set,
  or whether people can raise problems; unclear ownership is a common reason problems go unfixed.
- **Operational Excellence / Evolve** — no game-day and no post-incident-review question.
<!-- NOT-ASSESSED-AREAS:END -->

<!-- NOT-ASSESSED-NARROWER:BEGIN — read verbatim by assets/render-report.py; one paragraph. -->
Narrower gaps: **IPv6** clusters and **multi-tenancy isolation depth** are not assessed.
<!-- NOT-ASSESSED-NARROWER:END -->

> ## Read-only on the cluster — and on your disk too
>
> **This skill assesses. It changes nothing in AWS or Kubernetes.** Every AWS call it makes is a
> `describe-*`/`list-*`/`get-*` read, an EC2 permission probe run with `--dry-run` (which checks the
> permission without making the request), or `aws eks update-kubeconfig`, which writes only the
> kubeconfig Step 1 points it at inside the work directory. Every Kubernetes call is `kubectl get`, apart
> from three reads: `kubectl version --client` and `kubectl config view`, which read only the local client
> and kubeconfig, and the preflight's `kubectl auth can-i` probes, which only ask whether a read is
> allowed. You must not run a call that creates, modifies, deletes, tags, scales, drains, patches, applies
> or annotates — not to "verify" a
> finding, not to "test" a remediation, not because the user's phrasing sounded like consent to fix
> something. If a review appears to need a write to proceed, it does not: report what you could not
> observe instead.
>
> **Before Step 1, read [references/workflow.md](references/workflow) §*Read-only, grants and the work directory*.** It carries the rest of this rule: what a run
> writes and where, why `allowed-tools` grants what it does and must not be widened, the work-directory
> refusals, and why the Step 5 scorer blocks run through `score.sh`.
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
Which surface is machine-generated and which is yours: [references/workflow.md](references/workflow) §*Which surfaces are machine-generated*.

Your free-form work is the narrative — never the numbers. If you find yourself retyping a score into a
table by hand, render the HTML instead: a transcribed number is not a deterministic one.

## Two tracks — never blended

| Track | What | How scored |
|-------|------|-----------|
| **Measured** | Anything provable from `aws`/`kubectl` JSON | Deterministic `jq`. This is the headline score. |
| **Governance** | Process/organizational questions with no cluster-observable signal (upgrade process, change management, compliance-scanning cadence, environment separation, secret-rotation policy) | Not scored. Reported separately as Not Assessed. Never folded into the measured score. |

## Mode

Collect, run measured detections, apply the coverage gate, report the measured score. Governance
questions are listed as **Not Assessed** — never guessed, never scored `none`.

## Prerequisites

Verify all three succeed:

```bash
kubectl version --client && aws --version && aws sts get-caller-identity
```

These prove the tooling and your AWS identity, not that you can reach the cluster under review — a bare
`kubectl get nodes` here would only prove that *some* context works. Connectivity to the right cluster is
confirmed at the end of Step 1, against the context Step 1 has just created.

### Credentials

The commands here use your default credential chain. **If you use a named profile, an SSO session or an
assumed role, pass `--profile <name>` to every `aws` command** and to `collect.sh`. `update-kubeconfig`
writes it into the `exec` block as `AWS_PROFILE`, so `kubectl` needs nothing further — verified: with
`AWS_PROFILE` unset, `aws sts get-caller-identity` fails while `kubectl get nodes` still succeeds.
Exported credentials (`AWS_ACCESS_KEY_ID` and the rest) outrank `AWS_PROFILE`, in that block too;
`collect.sh --profile` unsets them for its run. `update-kubeconfig` takes `--role-arn` for assume-role.
There is **no** grant for `export AWS_PROFILE=…`: it has the trailing-assignment weakness described in
[references/workflow.md](references/workflow) §*Why parameters are arguments*.

### Permissions — checked automatically, before anything is collected

**Do not assume you hold cluster-admin or an unrestricted AWS role.** `collect.sh` runs a preflight
before it collects anything, and refuses with the exact list of what is missing.

Before Step 2, read [references/workflow.md](references/workflow) §*Permission preflight and the read-only IAM policy*: how each half is probed, the five cases it refuses
on, the Kubernetes RBAC the built-in `view` role does not cover, and the 23-action read-only policy.

## Workflow

Every command below passes its parameters as arguments, and that is a security property, not a style
choice: before Step 1, read [references/workflow.md](references/workflow) §*Why parameters are arguments*.

> `collect.sh` also accepts the four variables from its environment when the flags are omitted, so a
> caller that sets them keeps working — but the documented path is flags, and there is no grant for an `export`.
> Substitute the literal cluster name, region and work-directory path into each command.

### Step 1 — Identify the cluster

Before running Step 1, read [references/workflow.md](references/workflow) §*Step 1 detail: binding the review to one cluster*.

```bash
aws eks list-clusters --region <REGION> --output json
aws eks describe-cluster --name <CLUSTER> --region <REGION> --output json
```

Record: cluster name, region, Kubernetes version, VPC ID.

**Then create the work directory and bind `kubectl` to that same cluster explicitly, inside it.** This
is required, not optional. Run these from the directory Step 2 runs from, because Step 2 names the same
directory as `$PWD/eks-war-<CLUSTER>`:

```bash
mkdir -p -m 700 eks-war-<CLUSTER>
aws eks update-kubeconfig --name <CLUSTER> --region <REGION> --alias <CLUSTER> --kubeconfig eks-war-<CLUSTER>/kubeconfig   # add --profile <PROFILE> if you use one
kubectl get nodes --context <CLUSTER> --kubeconfig eks-war-<CLUSTER>/kubeconfig --cache-dir eks-war-<CLUSTER>/.kube-cache     # the connectivity check deferred from Prerequisites
```

Do **not** rely on `kubectl config current-context`. It makes an unattended run silently inherit
whichever context was last selected, which is the exact failure this binding prevents.

### Step 2 — Collect cluster data into a work directory

Before running Step 2, read [references/workflow.md](references/workflow) §*Step 2 detail: the kubeconfig, the parameters, the work directory and the exit status*.

Collect **once** into fixed filenames. All later steps read those files, so this is the only step that
touches the cluster.

```bash
${CLAUDE_SKILL_DIR}/assets/collect.sh --cluster <CLUSTER> --region <REGION> --context <CLUSTER> --work "$PWD/eks-war-<CLUSTER>" --kubeconfig "$PWD/eks-war-<CLUSTER>/kubeconfig"
```

Add `--profile <PROFILE>` if your credentials come from a named profile or an SSO session. `collect.sh`
runs a **permission preflight** first — see *Prerequisites* — and refuses before collecting anything if the
credentials in use cannot make a call the review needs.

The script does the whole collection and ends with a validation gate. **If it exits non-zero, stop** —
scoring incomplete or mis-bound data would produce a confident wrong answer. Do not work around it, and do
not re-run the individual commands by hand to "get past" it. **The exit status says whether retrying can
ever help:** the exit table is in [references/workflow.md](references/workflow) §*Step 2 detail: the kubeconfig, the parameters, the work directory and the exit status*.

[references/workflow.md](references/workflow) documents what it collects and why it refuses.

Missing/empty collections are expected on some clusters — the detections treat an empty list as "none of
that resource exists," which is a valid state, not an error. That is different from a call *failing*,
which the script treats as a hard error.

### Step 3 — Read the cluster's compute mode (for the narrative, not for the scorers)

```bash
jq -r '.cluster.computeConfig.enabled == true' "$PWD/eks-war-<CLUSTER>/cluster.json"        # EKS Auto Mode?
jq '[.items[]] | length' "$PWD/eks-war-<CLUSTER>/nodes.json"                                 # all nodes, Windows included (the mode label's population; the header's Linux count is .liveness.nodes_total)
jq '[.items[] | select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not) | select((.status.phase//"")!="Succeeded")] | length' "$PWD/eks-war-<CLUSTER>/pods.json"  # workload pods (the reducer's filter, the same number as .liveness.workload_pods)
jq '[.items[] | select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")] | length' "$PWD/eks-war-<CLUSTER>/nodes.json"  # Fargate nodes
jq '.fargateProfileNames | length' "$PWD/eks-war-<CLUSTER>/fargate.json"                     # Fargate profiles
jq 'def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end; [.items[] | select(ishy)] | length' "$PWD/eks-war-<CLUSTER>/nodes.json"  # EKS Hybrid Nodes (the scorers' `ishy`: an `aws:` providerID vetoes the label)
jq 'def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end; [.items[] | select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not))] | length' "$PWD/eks-war-<CLUSTER>/nodes.json"  # EC2 nodes (neither Fargate nor hybrid — the scorers' `isec2`)
```

Name the mode exactly as `render-report.py` does, because it prints its own label in the report header and
a narrative that disagrees with the header is worse than no narrative. Its seven possible strings, in the
order it tests them, and why these numbers set no flags, are in [references/workflow.md](references/workflow) §*Step 3 detail: the seven mode labels, and why the numbers set no flags*.

### Step 4 — Viability and liveness are enforced by the reducer, not by you

**You do not implement these gates.** `assets/reduce.sh` evaluates them from `nodes.json` and
`pods.json` and writes the outcome into `scores.json`, so every surface — the chat headline, the
markdown table and the HTML report — reads the same verdict. Report what it emits; do not re-derive it.

Before reporting the outcome, read [references/workflow.md](references/workflow) §*Step 4 detail: why the gates are shaped this way*.

| `scores.json` | Condition | What to report |
|---|---|---|
| `technical_overall: "NOT VIABLE — no data plane"` | `nodes_total == 0` (Linux nodes; Windows nodes are not counted) | Report the withholding verbatim — an empty cluster must never carry an overall score. Pillar scores **are** still shown, each labelled **declared configuration only** and marked not comparable to a running cluster's. |
| `technical_overall: "NOT HEALTHY — no Linux node is Ready"` | Linux nodes exist, `nodes_ready == 0` | Report the withholding and its reason. Pillar scores **may** still be shown, labelled as describing declared configuration only. |
| `liveness.warning` is non-null | under half the workload pods are `Running` | Publish the score, and carry the warning prominently with the counts. |
| otherwise | — | Score normally. |

**Always report both ratios in the header**, healthy or not: `3 Linux nodes (3 Ready) · 14 workload pods
(14 Running)`, straight from `liveness`, whose node counts leave Windows nodes out. When the cluster has
Windows nodes, the HTML report's header also carries a segment between the two, `2 Windows node(s) not
assessed — this skill supports Linux nodes only`; with no Windows node it is absent. A reader must be able
to see `3 Linux nodes (0 Ready)` beside any score without expanding anything.

### Step 5 — Run the measured detections (per pillar)

Run all five pillar scorers. Each appends one JSONL line per question to `$WORK/results.jsonl`:

```
{"pillar":"security","id":"rbac-3","track":"measured","state":"all","detail":"2/2 resolve"}
```

66 of the 132 records carry a sixth key, `resources`, so a consumer must not assume exactly five. Before
parsing `results.jsonl` yourself, read [references/workflow.md](references/workflow) §*Step 5 detail: the `resources` key*.

```bash
${CLAUDE_SKILL_DIR}/assets/score.sh operational-excellence "$PWD/eks-war-<CLUSTER>"
${CLAUDE_SKILL_DIR}/assets/score.sh security "$PWD/eks-war-<CLUSTER>"
${CLAUDE_SKILL_DIR}/assets/score.sh reliability "$PWD/eks-war-<CLUSTER>"
${CLAUDE_SKILL_DIR}/assets/score.sh performance-efficiency "$PWD/eks-war-<CLUSTER>"
${CLAUDE_SKILL_DIR}/assets/score.sh cost-optimization "$PWD/eks-war-<CLUSTER>"
```

**Check each exit status. If any is non-zero, stop** — a partial `results.jsonl` must never be scored.
`score.sh` also refuses a pillar that has already been scored, rather than appending every id a second
time and leaving `reduce.sh` to discover the duplicates two steps later.

**Do not paste the blocks into a shell instead.** Why, and what `score.sh` extracts from which file: [references/workflow.md](references/workflow) §*Step 5 detail: how `score.sh` runs the scorer blocks, and why there is no drift detection*.

The measured (`m`-family: `m` … `m7`) thresholds are the determinism guarantee and are not yours to edit.

Also run [references/cost-analysis.md](references/cost-analysis) (savings opportunities) to
inform the narrative, substituting the work-directory path for `$WORK` in each of its blocks — as with
every command here, nothing exports `WORK`.

**This review has no drift detection.** A single review therefore cannot say whether a finding is new, and
must not imply it: report the state observed, not a trend. Why: [references/workflow.md](references/workflow) §*Step 5 detail: how `score.sh` runs the scorer blocks, and why there is no drift detection*.

### Step 6 — Governance questions

Governance questions are not asked: each pillar's `g` calls emit `"state":"unknown"` for every
governance id, and the report lists them as Not Assessed.

### Step 7 — Reduce to scores (deterministic)

Before running this step, read [references/workflow.md](references/workflow) §*Step 7 detail: `-o`, four more refusals, and where severity lives*.
Run the reducer and **write its output to `$WORK/scores.json`**. It computes per-pillar measured
scores with the coverage gate, the technical overall, and the separate governance summary:

```bash
${CLAUDE_SKILL_DIR}/assets/reduce.sh -o "$PWD/eks-war-<CLUSTER>/scores.json" "$PWD/eks-war-<CLUSTER>"
# The headline, then the liveness line that must accompany it, then the pillars.
jq -r '.technical_overall,
       "Linux nodes \(.liveness.nodes_total) (\(.liveness.nodes_ready) Ready) · workload pods \(.liveness.workload_pods) (\(.liveness.pods_running) Running)",
       (.liveness.withheld_reason // .liveness.warning // empty),
       (.pillars[]|"\(.pillar) \(.score) (coverage \(.coverage)%)")' "$PWD/eks-war-<CLUSTER>/scores.json"
```

`.technical_overall` is the **only** headline you may report. When it is a string — `NOT VIABLE — no
data plane` or `NOT HEALTHY — no Linux node is Ready` — report that string, not a number, and not
`liveness.suppressed_overall`. That field exists so the report can say what configuration alone would
have scored; it is context, never the verdict. Quoting it as the headline publishes exactly the
number the report withholds.

`-o` is not optional. `assets/render-report.py` reads `$WORK/scores.json` and exits without it, and nothing else writes that file.

**Check the exit status, and if it is non-zero stop and fix the cause** — the same discipline Step 2
applies to `collect.sh`, and do not work around it either. It refuses on a missing or empty
`results.jsonl`, a missing / non-JSON / `.items`-less `nodes.json` or `pods.json`, a `results.jsonl` line
that is not one JSON object, a record with any of `pillar`/`id`/`track`/`state` absent or empty, a
duplicate question id, and an illegal `state`. Four more are easy to hit; they are listed in
[references/workflow.md](references/workflow) §*Step 7 detail: `-o`, four more refusals, and where severity lives*.

Every one of these exits 1 with a `reduce.sh:` diagnostic *before* a byte of output. With `-o` that means
**no `scores.json` is written at all**, so the failure cannot resurface two steps later as a renderer
complaint about a malformed file — which is what a `>` redirect would produce, a 0-byte file. Read the
message here, where it names what is wrong.

Do not retype the reducer's jq inline either: a transcribed reducer is a second source of truth for
every score in the report.

**What a tier is *worth* is a different fact, and it is not single-sourced.** `High = 3 / Medium = 2 /
Low = 1` appears in `reduce.sh`'s parser, in `render-report.py`'s weight validator, and in prose in both
`severity.md` and this file — four copies, with nothing enforcing that they agree. Changing one changes
every pillar score, and the renderer's "is this weight 1, 2 or 3" guard cannot detect it because the
altered value is still one of the three. Treat those four as edited together or not at all. They are a
constant rather than per-question data, which is why they are kept as copies.

**Rating bands** (technical overall and each pillar): ≥90 Excellent, 80–89 Good, 70–79 Fair,
60–69 Needs improvement, <60 Poor. **Risk:** ≥80 LOW, ≥60 MEDIUM, <60 HIGH — that same number restated,
not an assessed threat level, and liftable by clearing Low-severity items while a High-severity control
stays missing. See **Scoring model** before presenting either as a verdict.

### Step 8 — Render the HTML report (deterministic)

Before running this step, read [references/workflow.md](references/workflow) §*Step 8 detail: themes, the internal report, resource lists and what the renderer reads*.

Run the renderer. **Do not hand-write the HTML** — it is generated from the same files the scorers
wrote, so the report inherits the determinism the rest of the skill guarantees:

```bash
python3 -B ${CLAUDE_SKILL_DIR}/assets/render-report.py "$PWD/eks-war-<CLUSTER>" -o "$PWD/eks-war-<CLUSTER>/report.html"        # follows the reader's OS
python3 -B ${CLAUDE_SKILL_DIR}/assets/render-report.py "$PWD/eks-war-<CLUSTER>" -o "$PWD/eks-war-<CLUSTER>/report.html" --both # also writes report-dark.html
```

**Tell the user the report is internal before they forward it.** It names the cluster, region, node and
volume IDs, security group and subnet IDs, and IAM role/OIDC ARNs — which carry the AWS account ID — and
those identifiers should be masked before it leaves the cluster owner's circle.
**Say *the work directory* is internal, not just `report.html`**: `results.jsonl` and the collected JSON
name the same identifiers, and the collected workload JSON holds every container's literal env values and arguments: treat the work directory as credential material, keep it out of version control and delete it after the review. Detail: [references/workflow.md](references/workflow) §*Step 8 detail: themes, the internal report, resource lists and what the renderer reads*.

Tell the user where the file is and summarise the headline result in chat: the technical score and
rating (or the withheld/not-viable reason), the per-pillar table, and the top 3 priorities — and, where
any row's detail says Windows nodes or Windows pods were not assessed, that they are excluded from this
review because the skill supports Linux nodes only.

**If the renderer exits non-zero, say so in that summary.** Where the failure sits relative to the
`wrote …` line tells you which kind it is; before you write that summary, read [references/workflow.md](references/workflow) §*Step 8 detail: if the renderer exits non-zero*.

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
sections in [references/workflow.md](references/workflow) §*Markdown-only report* instead of the HTML. Otherwise prefer the renderer — it is faster,
cannot miscount, and cannot drift from the design.

## Scoring model

- **Before presenting a score, a band or the overall, read [references/workflow.md](references/workflow) §*Scoring model detail: buckets, states, bands and pillar weights***:
  the bucket rule, what each state scores, why `na` is the only not-applicable token, how a band can be
  bought with Low-severity items, and why pillars are averaged equally although they are not comparable
  in size.
- **Severity weight** — this skill's own, not AWS's: each question is High (3), Medium (2) or Low (1),
  with no default — every question carries an explicit tier. The three tiers are an editorial ordering
  assigned here; no Well-Architected Tool risk level, CIS severity or EKS Best Practices tiering maps
  onto them, so cite them as this review's judgement rather than as a published AWS classification.
  They are still the right thing to prioritise by — the tier, and the reasoning for it, are in
  [references/severity.md](references/severity), which is the single source: the reducer parses that
  file and the report reads back the weights the reducer used.
  A missing High-risk control (public API, no encryption) costs far more than a missing Low-risk extra
  (service mesh, ndots tuning). This lets a cluster that clears all High/Medium risks score high without
  every aspirational practice.
- **Scope:** object checks assess only cluster-owned resources — workload pods (managed `kube-*`/`amazon-*`
  pods reported as context, not scored), custom RBAC roles (built-in `system:`/`eks:` excluded), EBS volumes
  tagged to the cluster or named by one of its PersistentVolumes (for `sec-21`, also those attached to its EC2 nodes), ECR repos referenced by cluster images. You are scored on what you control.
- **Pillar score** = severity-weighted average of applicable measured states, **only if** applicable ≥ 50%
  of the pillar's measured questions (coverage gate). Below that → `INSUFFICIENT` (no number).
- **Technical overall** = rounded average of numeric pillar scores, only if ≥4 pillars are numeric; else
  `WITHHELD`.

### What the report must disclose about the score

`assets/render-report.py` prints the paragraph below verbatim, directly under the headline score; see [references/workflow.md](references/workflow) §*Report content read from SKILL.md and from this file*.

<!-- SCORE-DISCLOSURE:BEGIN — read verbatim by assets/render-report.py and printed under the headline
     score. One paragraph; `**bold**` and `` `code` `` only, no other markup. -->
**How to read this score.** It is the equal-weight average of the five pillars — or of the four that
remain when one pillar's question coverage was too thin to score at all, since below four pillars no
number is published here. They hold very different
numbers of questions — 9 to 42 — so it tracks how many questions were cleared, not how much risk they
carried: one Medium-severity Cost question moves it further than one High-severity Security question. The
Rating and Risk labels are that same number restated, so both can be lifted by clearing Low-severity
items while a High-severity control stays missing. **Top priorities** and the **improvement plan** are
ordered by severity weight instead. Decide what to fix from those, and use this number to compare this
cluster with itself over time.
<!-- SCORE-DISCLOSURE:END -->

**Platform-credited answers must be counted too, per pillar and in total.** The rule `render-report.py`
applies, and why the count is load-bearing: [references/workflow.md](references/workflow) §*Platform-credited answers*.

<!-- PLATFORM-CREDIT-NOTE:BEGIN — read by assets/render-report.py and printed with the pillar table when
     the count is above zero. Substitutions: {n} = credited total; {answered} = summed `applicable`;
     {per_pillar} = "<Pillar> <credited> of <applicable>" for each pillar with a credit, comma-separated,
     in the pillar table's order; {coverage_without} = "<Pillar> <coverage>%" for the same pillars, adding
     " (below the 50% coverage gate, so this pillar would report no number)" where the recomputed figure
     drops under 50. `**bold**` and `` `code` `` only. -->
**Credited to the platform, not measured here: {n} of {answered} answered questions.** They pass because
AWS manages that function on this cluster — {per_pillar} — so no configuration of yours was read for them.
Coverage without them would be {coverage_without}.
<!-- PLATFORM-CREDIT-NOTE:END -->

<!-- PLATFORM-CREDIT-NONE:BEGIN — printed in the same place when the count is zero. -->
**Platform-credited answers: none.** All {answered} answered questions were measured on this cluster
rather than credited to a managed platform.
<!-- PLATFORM-CREDIT-NONE:END -->

## Notes

- Detections read only from `$WORK/*.json`. An empty **collection** — a file holding zero resources — is a
  valid state and scores as "none of that resource exists". An **absent file** is not the same thing and is
  not yours to substitute for: `assets/reduce.sh` exits 1 when `nodes.json` or `pods.json` is missing,
  because viability and liveness cannot be evaluated without them. Do not fabricate an empty `nodes.json`
  to get past that refusal — it converts a hard stop into `NOT VIABLE — no data plane` on a cluster that
  has nodes. Re-run collection instead.
- Keep numbers from `jq`; keep prose from yourself. If you ever find yourself counting containers by hand,
  stop and run the detection instead.
