---
title: "eks-well-architected-review"
description: "Deterministic AWS Well-Architected Framework review of an Amazon EKS cluster. Unofficial — not the AWS Well-Architected Tool; no official EKS lens exists. Collects live data via kubectl and aws, scores it across five of the Framework's six pillars (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization; not Sustainability, which is not cluster-observable) using fixed jq detections so scores are stable, separates measured from governance findings, applies a coverage gate so thin clusters cannot score well, and renders a self-contained HTML report. Use when asked to run a Well-Architected review of an EKS cluster, measure how far it complies with the Framework, score or audit it across the five pillars, or get a prioritized plan to raise that score. Not for operational audits (eks-operation-review), dollar cost analysis (eks-cost-intelligence), fact-only inventory (eks-recon), static advice (eks-best-practices), hardening (eks-security), or design documents (eks-design)."
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

> ## Read-only — hard rule
>
> **This skill assesses. It does not change anything.** Every AWS call it makes is a
> `describe-*`/`list-*`, and every Kubernetes call is `kubectl get`. You must not run a call that
> creates, modifies, deletes, tags, scales, drains, patches, applies or annotates — not to "verify" a
> finding, not to "test" a remediation, not because the user's phrasing sounded like consent to fix
> something. If a review appears to need a write to proceed, it does not: report what you could not
> observe instead.
>
> `allowed-tools` above is an explicit allowlist of the read calls this skill uses, plus
> `aws eks update-kubeconfig`, which writes only to the local kubeconfig and never to AWS. It used to
> read `Bash(aws:*) Bash(kubectl:*)`, which pre-authorised `delete-cluster` and `kubectl delete` on a
> cluster the operator may well have believed was only being looked at.
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
| `report.html` (via `assets/render-report.py`) | **yes** — every number copied from `scores.json`; byte-identical for the same work dir |
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
- **`interactive`**: same as `auto`, then present the governance questions as one batch at the **end**
  (after collection, so questions the data already answers or moots are skipped), and report a separate
  Governance score.

Default to `auto` unless the user asks to be interviewed.

## Prerequisites

Verify all four succeed. The last confirms cluster connectivity.

```bash
kubectl version --client && aws --version && aws sts get-caller-identity
kubectl --context "$KCTX" get nodes      # KCTX is set in Step 1; a bare kubectl here proves nothing
```

## Workflow

### Step 1 — Identify the cluster

```bash
aws eks list-clusters --region <REGION> --output json
aws eks describe-cluster --name <CLUSTER> --region <REGION> --output json
```

Record: cluster name, region, Kubernetes version, VPC ID.

**Then bind `kubectl` to that same cluster explicitly.** This is required, not optional:

```bash
aws eks update-kubeconfig --name <CLUSTER> --region <REGION> --alias <CLUSTER>
export KCTX=<CLUSTER>          # the context name, used on EVERY kubectl call
export SKILL_DIR=<absolute path to this skill directory>   # the one holding assets/ and references/
```

`SKILL_DIR` must be set here, and it must be absolute. Steps 7 and 8 invoke `assets/reduce.sh` and
`assets/render-report.py` through it, and `$WORK` is not inside the skill directory, so a relative
`assets/...` path resolves only if the shell happens to be sitting in the skill root. It cannot be
derived either: a fenced block pasted into a shell has no file identity of its own. The collection
block in `references/workflow.md` refuses to run without it, rather than letting a whole collection
complete and then failing at the render.

The AWS half of this review comes from `describe-cluster`; the Kubernetes half comes from whatever
`kubectl` points at. If those are different clusters the review still completes and still passes the
validation gate — every required file present and valid JSON — but the report names one cluster
while grading another's
workloads. `references/workflow.md` therefore refuses to collect unless the kubeconfig endpoint for
`$KCTX` matches `.cluster.endpoint` from `describe-cluster`, and routes every `kubectl` call through
`--context "$KCTX"`.

Do **not** rely on `kubectl config current-context`. It makes an unattended run silently inherit
whichever context was last selected, which is the exact failure this binding prevents.

### Step 2 — Collect cluster data into a work directory

Set a work directory and collect **once** into fixed filenames. All later steps read these files, so
collection is the only place that touches the cluster. Run the full command set in
[references/workflow.md](references/workflow) — it writes `cluster.json`, `pods.json`, `nodes.json`,
`deployments.json`, `sg.json`, … into `$WORK`. Set it up first:

```bash
export WORK="$(pwd)/eks-war-<CLUSTER>"; mkdir -p "$WORK"; : > "$WORK/results.jsonl"
```

Missing/empty collections are expected on some clusters — the detections treat an empty list as "none of
that resource exists," which is a valid state, not an error.

### Step 3 — Detect cluster mode and set flags (deterministic)

```bash
jq -r '.cluster.computeConfig.enabled == true' "$WORK/cluster.json"        # AUTO_MODE
jq '[.items[]] | length' "$WORK/nodes.json"                                 # NODE_COUNT
jq '[.items[] | select(.metadata.namespace|test("^kube-system$|^kube-node-lease$|^kube-public$")|not)] | length' "$WORK/pods.json"  # WORKLOAD_PODS
jq '[.items[] | select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")] | length' "$WORK/nodes.json"  # FARGATE_NODES
jq '.fargateProfileNames | length' "$WORK/fargate.json"                     # FARGATE_PROFILES
jq '[.items[] | select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")] | length' "$WORK/nodes.json"  # EC2_NODES
```

Set flags for the scorers (export so the pillar blocks can read them):
- `AUTO_MODE=true` → EKS Auto Mode. Node-lifecycle questions auto-answer `all` (AWS manages nodes).
- `FARGATE_PROFILES>0` **and** `EC2_NODES==0` → Fargate-only. EC2/DaemonSet/node-hardening questions → `na`.
- Otherwise → Standard.

```bash
export AUTO_MODE=$(jq -r '.cluster.computeConfig.enabled == true' "$WORK/cluster.json")
export EC2_NODES=$(jq '[.items[]|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length' "$WORK/nodes.json")
export FARGATE_PROFILES=$(jq '.fargateProfileNames | length' "$WORK/fargate.json")
```

### Step 4 — Viability precondition (kills inflated scores on empty clusters)

```bash
NODE_COUNT=$(jq '[.items[]]|length' "$WORK/nodes.json")
WORKLOAD_PODS=$(jq '[.items[]|select(.metadata.namespace|test("^kube-system$|^kube-node-lease$|^kube-public$")|not)]|length' "$WORK/pods.json")
if [ "$NODE_COUNT" -eq 0 ] && [ "$WORKLOAD_PODS" -eq 0 ]; then echo "NOT_VIABLE"; fi
```

If `NOT_VIABLE`: **stop scoring.** Report `Overall: NOT VIABLE — no data plane`, list only the
control-plane facts, and state how many questions were applicable. Do **not** emit
pillar scores. An empty cluster must never score "Excellent."

### Step 4b — Liveness gate (a dead cluster must not band normally)

The viability gate above only fires when a cluster has **both** zero nodes and zero workload pods.
That leaves a large hole: a cluster whose nodes are all `NotReady`, or whose pods are all `Pending`,
still has objects with complete `spec` sections, so every spec-side detection passes and the cluster
bands like a healthy one. Nothing in the scorers reads a readiness condition or a pod phase.

```bash
NODES_TOTAL=$(jq '[.items[]]|length' "$WORK/nodes.json")
NODES_READY=$(jq '[.items[]|select([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0)]|length' "$WORK/nodes.json")
PODS_WL=$(jq '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)]|length' "$WORK/pods.json")
PODS_RUN=$(jq '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)")|not) and .status.phase=="Running")]|length' "$WORK/pods.json")
echo "nodes Ready: $NODES_READY/$NODES_TOTAL   workload pods Running: $PODS_RUN/$PODS_WL"
```

**Judge only what is running, but do not filter the denominators.** These two are different things and
conflating them inverts the score:

- **Do NOT** restrict the ratio detections to `Running` pods. A cluster where 10 of 15 pods are
  `Pending` for want of schedulable resources would then score `perf-1` as `5/5 = all` — a perfect
  result on resource requests, for a cluster that cannot schedule its workload. Excluding broken
  resources rewards being broken. `CrashLoopBackOff` also reports `phase: Running`, so phase filtering
  would not even catch the commonest failure.
- **DO** withhold the headline when the cluster is not healthy enough for its configuration scores to
  describe a working system:

| Condition | Action |
|---|---|
| `NODES_TOTAL > 0` and `NODES_READY == 0` | Withhold the technical overall. State `NOT HEALTHY — no node is Ready`. Pillar scores may still be shown, labelled as describing declared configuration only. |
| `PODS_WL > 0` and `PODS_RUN * 2 < PODS_WL` (under half running) | Publish the overall, but carry a prominent health warning naming the counts. |
| otherwise | Score normally. |

**Always report the two ratios in the header**, healthy or not, next to the node count — `3 nodes
(3 Ready) · 14 workload pods (14 Running)`. A reader must be able to see `3 nodes (0 Ready)` beside any
score without expanding anything.

**This is a disclosure, not a refusal.** A cluster mid-deploy or mid-upgrade legitimately shows Pending
pods and NotReady nodes, and a batch cluster legitimately sits at zero running pods between jobs.
Refusing to score those would be a false alarm. Say what was observed and let the reader judge.

### Step 5 — Run the measured detections (per pillar)

Load each pillar reference and run its **"Pillar scorer"** block verbatim. Each block appends one JSONL
line per measured question to `$WORK/results.jsonl`:

```
{"pillar":"security","id":"sec-1","track":"measured","state":"all","detail":"private endpoint enabled"}
```

Run each pillar's scorer block:
- **Operational Excellence** — [references/operational-excellence.md](references/operational-excellence)
- **Security** (all 54 questions, one consolidated block) — [references/security/identity-access.md](references/security/identity-access). The other four security files (data-protection, network, workload-security, governance-compliance) hold per-question rationale and remediation you load when writing findings.
- **Reliability** — [references/reliability.md](references/reliability)
- **Performance Efficiency** — [references/performance-efficiency.md](references/performance-efficiency)
- **Cost Optimization** — [references/cost-optimization.md](references/cost-optimization)

Also run [references/cost-analysis.md](references/cost-analysis) (savings opportunities) to
inform the narrative.

**`references/drift-detection.md` is no longer rendered in the report.** Its 10 checks were a spot
check, not drift detection — nothing stored a prior state to compare against. 8 of the 10 duplicated
a scored question verbatim; 2 contradicted theirs (its NetworkPolicy and PDB rows passed on
"more than zero covered" while `sec-4`/`rel-2` graded the ratio, so a High-severity gap showed green);
and 2 mapped only to a governance question the report declines to assess. The headline
"10 of 10 passing" then undercut the actual verdict. Real drift detection needs a stored previous run
to diff against — see the open item in CONTEXT.md.

### Step 6 — Governance questions

- **`auto` mode:** for each governance question append `{"...","track":"governance","state":"unknown"}`.
  (The pillar scorer blocks already do this.) They are reported as Not Assessed.
- **`interactive` mode:** present the governance questions (each pillar file lists them) as one batch.
  Map answers with the fixed rule below and append `track:"governance"` lines with the answered state.

### Step 7 — Reduce to scores (deterministic)

Run the reducer and **write its output to `$WORK/scores.json`**. It computes per-pillar measured
scores with the coverage gate, the technical overall, and the separate governance summary:

```bash
"$SKILL_DIR/assets/reduce.sh" "$WORK" > "$WORK/scores.json"
jq -r '.technical_overall, (.pillars[]|"\(.pillar) \(.score) (coverage \(.coverage)%)")' "$WORK/scores.json"
```

The redirect is not optional. `assets/render-report.py` reads `$WORK/scores.json` and exits without
it, and nothing else writes that file — Step 7 used to print to stdout only, leaving the agent to infer
a redirect on the one path the determinism guarantee depends on.

The severity weights live in `assets/reduce.sh`, which is the single source for them. Do not retype the
jq inline: a transcribed reducer is a second source of truth for every score in the report.

**Rating bands** (technical overall and each pillar): ≥90 Excellent, 80–89 Good, 70–79 Fair,
60–69 Needs Improvement, <60 Poor. **Risk:** ≥80 LOW, ≥60 MEDIUM, <60 HIGH.

### Step 8 — Render the HTML report (deterministic)

Run the renderer. **Do not hand-write the HTML** — it is generated from the same files the scorers
wrote, so the report inherits the determinism the rest of the skill guarantees:

```bash
python3 "$SKILL_DIR/assets/render-report.py" "$WORK" -o "$WORK/report.html"        # follows the reader's OS
python3 "$SKILL_DIR/assets/render-report.py" "$WORK" -o "$WORK/report.html" --both # also writes report-dark.html
```

`$SKILL_DIR` is exported by the collection block in `references/workflow.md`. Both asset paths go
through it because the bare `assets/...` form only resolved when the shell happened to be sitting in
the skill root, which is not where `$WORK` is.

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

Every number in the HTML is copied from `scores.json` and `results.jsonl`. The renderer performs no
arithmetic and makes no judgement — if a score looks wrong, the scorer is wrong, not the report.

Tell the user where the file is and summarise the headline result in chat: the technical score and
rating (or the withheld/not-viable reason), the per-pillar table, and the top 3 priorities.

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
Nodes: <count> (<ready> Ready) | Workload pods: <count> (<running> Running)   # Step 4b, always shown

Technical Score: X/100 (Rating)      # or "NOT VIABLE — no data plane" / "WITHHELD — insufficient
                                     # coverage" / "NOT HEALTHY — no node is Ready"

| Pillar                  | Score        | Coverage | Risk   |
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
  A control that is entirely absent earns nothing — there is no participation floor.
- **`na` is the only not-applicable token**, on both the measured and the governance track. Not
  `not-applicable`, not `n/a`, not an empty state. The reducer matches the literal string, so any other
  spelling is counted as a real answer: a question emitted as `not-applicable` stays in the denominator
  and scores 0, which reads in the report as a failed control on a cluster the question does not apply
  to. `na` is excluded from **both** the numerator and the denominator — it does not dilute the score,
  it leaves the question out of it, and the coverage figure is what discloses how many were left out. (Before
  2026-08-21 `none` scored 25, which put a hard floor of 25 under every pillar and compressed
  populated clusters into a narrow ~53–75 band regardless of how bad they were.)
- **Severity weight** (WAF risk): each question is High (3), Medium (2, default), or Low (1) — see `sev()`
  in the reducer, with the full per-question rationale in [references/severity.md](references/severity).
  A missing High-risk control (public API, no encryption) costs far more than a missing Low-risk extra
  (service mesh, ndots tuning). This lets a cluster that clears all High/Medium risks score high without
  every aspirational practice.
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

- Detections read only from `$WORK/*.json`. If a file is absent, treat it as an empty collection.
- Keep numbers from `jq`; keep prose from yourself. If you ever find yourself counting containers by hand,
  stop and run the detection instead.
