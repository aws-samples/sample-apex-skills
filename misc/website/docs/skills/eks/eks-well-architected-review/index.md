---
title: "eks-well-architected-review"
description: "Runs a deterministic AWS Well-Architected Framework review of an Amazon EKS cluster. Collects live data with kubectl and the aws CLI, scores it across the five pillars (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization) using fixed jq detections so scores are reproducible, separates measured findings from governance questions, applies a coverage gate so empty or under-observed clusters cannot score well, and renders a self-contained Cloudscape-styled HTML report naming the resources behind each finding. Use when the user asks to run a Well-Architected review of an EKS cluster, measure how far it complies with the AWS Well-Architected Framework, score or audit it across the five pillars, or get a prioritized plan of improvements to raise that score. Not for operational-posture-only audits (eks-operation-review), dollar-quantified cost analysis (eks-cost-intelligence), fact-only inventory (eks-recon), static advice (eks-best-practices), or design documents (eks-design)."
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

## Why this skill is deterministic

Every scored question is answered by a `jq` command that reads the collected JSON and prints exactly one
token — `all`, `most`, `some`, `none`, or `na`. You run the command; you do **not** eyeball JSON or do
arithmetic. Given the same cluster data, the score is identical on every run. Your only free-form work is
the narrative (findings prose, remediation ordering) — never the numbers.

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
kubectl version --client && aws --version && aws sts get-caller-identity && kubectl get nodes
```

## Workflow

### Step 1 — Identify the cluster

```bash
aws eks list-clusters --region <REGION> --output json
aws eks describe-cluster --name <CLUSTER> --region <REGION> --output json
```

Record: cluster name, region, Kubernetes version, VPC ID.

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

**Drift detection is out of scope.** An earlier version shipped 10 "drift" checks; they were retired
because they were a spot check, not drift detection — nothing stored a prior state to compare against.
8 of the 10 duplicated a scored question verbatim; 2 contradicted theirs (their NetworkPolicy and PDB
rows passed on "more than zero covered" while `sec-4`/`rel-2` graded the ratio, so a High-severity gap
showed green); and 2 mapped only to a governance question the report declines to assess. The headline
"10 of 10 passing" then undercut the actual verdict. Real drift detection needs a stored previous run
to diff against.

### Step 6 — Governance questions

- **`auto` mode:** for each governance question append `{"...","track":"governance","state":"unknown"}`.
  (The pillar scorer blocks already do this.) They are reported as Not Assessed.
- **`interactive` mode:** present the governance questions (each pillar file lists them) as one batch.
  Map answers with the fixed rule below and append `track:"governance"` lines with the answered state.

### Step 7 — Reduce to scores (deterministic)

Run this reducer verbatim. It computes per-pillar measured scores with the coverage gate, the technical
overall, and the separate governance summary:

```bash
jq -s -r '
  def sc: {all:100,most:75,some:50,none:0}[.];
  # WAF risk weight per question: High=3, Medium=2 (default), Low=1
  def sev($id): ({
    "sec-2":3,"sec-6":3,"sec-18":3,"rbac-1":3,"sec-21":3,"sec-29":3,"sec-4":3,"sec-30":3,
    "net-2":3,"sec-11":3,"podsec-2":3,"podsec-4":3,"lens-11":3,"sec-26":3,
    "ope-5":3,"ope-6":3,"ope-11":3,"ope-12":3,
    "rel-1":3,"rel-6":3,"rel-7":3,"rel-12":3,"rel-13":3,"lens-15":3,"perf-1":3,
    "cost-6":3,"cost-8":3,"cost-9":3,
    "sec-5":1,"sec-17":1,"sec-8":1,"sec-23":1,"sec-27":1,"sec-28":1,"net-1":1,"net-3":1,
    "sec-12":1,"sec-32":1,"sec-35":1,"sec-36":1,"sec-37":1,
    "ope-3":1,"ope-4":1,"ope-10":1,"ope-14":1,"ope-17":1,"ope-18":1,
    "fargate-1":1,"fargate-2":1,"fargate-3":1,"fargate-4":1,"lens-1":1,
    "rel-11":1,"rel-15":1,"rel-16":1,"rel-17":1,"rel-19":1,"rel-20":1,"rel-23":1,"lens-2":1,"lens-3":1,
    "perf-2":1,"perf-4":1,"perf-5":1,"perf-6":1,"lens-5":1,"lens-8":1,"lens-9":1,"lens-10":1,
    "cost-3":1,"cost-4":1,"lens-4":1,"lens-13":1,"lens-16":1
  }[$id]) // 2;
  def pillars: ["operational-excellence","security","reliability","performance-efficiency","cost-optimization"];
  (map(select(.track=="measured"))) as $m |
  (map(select(.track=="governance"))) as $g |
  (pillars | map(. as $p |
     ($m|map(select(.pillar==$p))) as $q |
     ($q|map(select(.state!="na"))) as $appl |
     ($q|length) as $tot |
     ($appl|length) as $ac |
     ($q|map(select(.state=="na"))|length) as $na |
     { pillar:$p, total:$tot, applicable:$ac, na:$na,
       coverage: (if $tot==0 then 0 else (($ac*100/$tot)|floor) end),
       score: (if $tot==0 or ($ac*2 < $tot) then "INSUFFICIENT"
               else (($appl|map((.state|sc)*sev(.id))|add) / ($appl|map(sev(.id))|add) | round) end) }
  )) as $ps |
  ($ps|map(select(.score|type=="number"))) as $scored |
  ($g|map(select(.state!="unknown" and .state!="na"))) as $ga |
  { technical_overall: (if ($scored|length) >= 4 then ($scored|map(.score)|add)/($scored|length)|round else "WITHHELD (insufficient pillar coverage)" end),
    pillars: $ps,
    governance: { answered: ($ga|length), total: ($g|length),
                  score: (if ($ga|length)==0 then "Not Assessed" else (($ga|map(.state|sc)|add)/($ga|length)|round) end) } }
' "$WORK/results.jsonl"
```

**Rating bands** (technical overall and each pillar): ≥90 Excellent, 80–89 Good, 70–79 Fair,
60–69 Needs Improvement, <60 Poor. **Risk:** ≥80 LOW, ≥60 MEDIUM, <60 HIGH.

### Step 8 — Render the HTML report (deterministic)

Run the renderer. **Do not hand-write the HTML** — it is generated from the same files the scorers
wrote, so the report inherits the determinism the rest of the skill guarantees:

```bash
python3 assets/render-report.py "$WORK" -o "$WORK/report.html"          # follows the reader's OS
python3 assets/render-report.py "$WORK" -o "$WORK/report.html" --both   # also writes report-dark.html
```

`--theme auto` (default) ships both token sets, starts from the reader's `prefers-color-scheme`, and
puts a **light/dark toggle in the top right** that remembers the choice in `localStorage`. All four
states (base light, OS dark, OS-dark-but-pinned-light, pinned dark) are resolved by CSS, so the
report is correct before any script runs; the toggle button ships `hidden` and is revealed by the
inline script, so a viewer with JavaScript stripped sees no dead control.

Use `--theme dark` or `--theme light` to **pin** one — no toggle, no script — for when the file is
emailed, attached to a ticket, or printed and the reader's OS setting is not yours to predict.
`--both` writes the light file plus a pinned `-dark` sibling. `--no-toggle` keeps `auto` behaviour
but ships no script at all.

Still one file either way: the toggle adds ~20 lines of inline JavaScript and two inline SVG icons.
No `src`, no `@import`, no `fetch` — asserted by gate 11, because a report that reached the network
on open would break the skill's "all data stays local" contract.

**Each finding carries a named resource list.** "3/3 core addons" is a claim the reader cannot check;
`coredns, kube-proxy, vpc-cni` is one they can verify in seconds. Every historic scoping bug in this
skill was a *correct count over the wrong set* — an unrelated security group, another cluster's
volumes, AWS-installed Deployments counted as the operator's. The lists make that visible, and they
also name what was **excluded** and why, so the scoping rule is auditable rather than trusted.

The lists are a second reading of the same data, so the renderer checks each one against the scorer's
own `N/M` and gate 11 **fails on any disagreement** — a list that contradicts its score would be worse
than no list. Currently 48 extractors, 585 agreements, 0 disagreements across the fixture suite.
Questions without an extractor simply show no list.

Panel order is deliberate: *why it matters* → *what we found* → *how to fix* → *how this was measured*
(nested, collapsed). The verbatim `jq` serves a narrow audience — auditing the tool, disputing a
finding, maintaining the skill — so it sits last rather than pushing the fix out of view.

**No JSON export.** Measured, not assumed: scraping the rendered HTML for all findings takes 0.33 ms
versus 0.06 ms to parse an equivalent JSON blob — a 0.0003 s difference. For an LLM the numbers point
the other way: it reads the whole file regardless, so an embedded copy would add ~5,000 tokens and
save nothing. Rows instead carry `data-qid` / `data-state` / `data-severity` attributes, which makes
scraping reliable at zero cost.

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
Region: <region> | Kubernetes: <version> | Nodes: <count> | Mode: <Standard|Auto|Fargate-only>

Technical Score: X/100 (Rating)      # or "NOT VIABLE — no data plane" / "WITHHELD — insufficient coverage"

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
  A control that is entirely absent earns nothing — there is no participation floor. (Before
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
