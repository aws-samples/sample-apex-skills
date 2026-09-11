#!/usr/bin/env python3
"""Render an EKS Well-Architected review as a self-contained Cloudscape-styled HTML report.

Usage:  python3 render-report.py <WORK_DIR> [-o report.html]

Reads ONLY the files the collection step wrote and the scorers produced:
  scores.json      pillar + overall scores (authoritative — never recomputed here)
  results.jsonl    one line per question: pillar, id, track, state, detail
  cluster.json     header facts (name, region, version, compute mode)
  nodes.json       node count
  podidentity.json / oidcproviders.json / fargate.json  compute + identity context

WHY THIS IS A SCRIPT AND NOT PROSE INSTRUCTIONS
Every number in the output is copied from scores.json / results.jsonl. The renderer does no
arithmetic and makes no judgement, so the HTML inherits the skill's determinism property: the
same work dir always produces byte-identical HTML. Asking an agent to hand-write every finding
as styled HTML would be slower, non-deterministic, and would drift from the design tokens.
(A finding count is deliberately not stated here: it is exactly the kind of number this file's own
comments elsewhere warn against typing into a comment, because it goes stale the moment a question
is added or removed. Count `^### [a-z]+-[0-9]+` across references/ if you need the current figure.)

DESIGN
Cloudscape Design System (https://cloudscape.aws.dev). Token values are transcribed from the
design-tokens reference and carried as CSS custom properties, with the documented light and dark
values wired to prefers-color-scheme. No network requests, no external CSS or JS — the report is
one file that opens offline, which the skill's "all data stays local" contract requires.
"""
import argparse
import html
import json
import os
import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# Severity weights — MUST stay identical to SKILL.md Step 7 / reduce.sh sev().
# Used only to LABEL a finding, never to compute a score.
# ---------------------------------------------------------------------------
SEV3 = {
    "sec-2", "sec-38", "sec-6", "sec-18", "rbac-1", "sec-21", "sec-29", "sec-4", "sec-30",
    "net-2", "sec-11", "podsec-2", "podsec-4", "lens-11", "sec-26",
    "ope-5", "ope-6", "ope-11", "ope-12",
    "rel-1", "rel-6", "rel-7", "rel-12", "rel-13", "lens-15", "perf-1",
    "cost-6", "cost-8", "cost-9",
}
SEV1 = {
    "sec-5", "sec-17", "sec-8", "sec-23", "sec-27", "sec-28", "net-1", "net-3",
    "sec-12", "sec-32", "sec-35", "sec-36", "sec-37",
    "ope-3", "ope-4", "ope-10", "ope-14", "ope-17", "ope-18",
    "fargate-1", "fargate-2", "fargate-3", "fargate-4", "lens-1",
    "rel-11", "rel-15", "rel-16", "rel-17", "rel-19", "rel-20", "rel-23", "lens-2", "lens-3",
    "perf-2", "perf-4", "perf-5", "perf-6", "lens-5", "lens-8", "lens-9", "lens-10",
    "cost-3", "cost-4", "lens-4", "lens-13", "lens-16",
}

PILLARS = [
    ("operational-excellence", "Operational Excellence"),
    ("security", "Security"),
    ("reliability", "Reliability"),
    ("performance-efficiency", "Performance Efficiency"),
    # "(hygiene)" on the DISPLAY NAME, not just in prose somewhere else on the page, so the qualifier
    # travels with the score wherever this tuple's name is used — the executive-summary pillar table,
    # this pillar's own section heading, and the governance grouping. Measured: graviton-spot (100%
    # Spot, 100% Graviton) and mixed-fleet (33% Spot, one unsupported instance family) both scored
    # Cost 50 / Poor / High risk with no visible reason a reader could tell those two clusters apart
    # from the score alone. See _cost_posture_note() for the measured Spot/Graviton/support facts that
    # sit beside every rendering of this score.
    ("cost-optimization", "Cost Optimization (hygiene)"),
]

# ---------------------------------------------------------------------------
# WHY EACH GOVERNANCE QUESTION WAS NOT ASSESSED. ADD AN ENTRY WHEN YOU ADD A GOVERNANCE QUESTION —
# an id missing from this table renders in an "unclassified" group that names it, rather than
# inheriting a reason nobody checked.
#
# The report used to give ONE reason for all 29: they "have no signal in `aws` or `kubectl` output".
# The same report refuted it. `rel-15` (LoadBalancer services) sat here while `lens-9` scored from
# `services.json`; `rel-17` (CoreDNS/ExternalDNS) sat here while `ope-16` measured the coredns add-on
# and `ope-2` matched external-dns over `deployments.json`; `rel-14` (ingress replicas) sat here while
# `rel-7` computed `.spec.replicas>1` over the same file; and `sec-22`/`sec-23` were declared
# unobservable in `aws` output when `aws efs describe-file-systems` returns `Encrypted` directly — a
# collection choice presented as an observability impossibility. The distinction matters to a reader
# who has to record either "not verifiable by automated review" or "not verified": those are different
# audit lines, and only one of them was true.
#
#   process        Nothing in the collected output states the answer: it is a fact about how a team
#                  works, about the wider environment, or a judgement cluster state cannot settle.
#                  Where a PARTIAL signal exists, the note says so — a signal that can only prove a
#                  yes is not an answer.
#   not-collected  A documented AWS or Kubernetes API returns the answer and this skill does not call
#                  it. The call is named, so it can be added.
#   collected      The files this run already wrote contain the answer, and for most of these a
#                  neighbouring question is scored from the same field. Routed to the interview by
#                  choice, not by necessity.
GOV_UNASSESSED = {
    # ---- process or policy
    "ope-1": ("process", "a CloudFormation or eksctl stack tag on the cluster proves those two tools "
                         "were used; Terraform leaves none, so absence is not an answer"),
    "ope-4": ("process", "Helm labels what it installs `app.kubernetes.io/managed-by=Helm`, which "
                         "`deployments.json` carries; Kustomize leaves no marker at all, so absence "
                         "is not an answer"),
    "ope-13": ("process", ""),
    "ope-14": ("process", "asks about a different cluster from the one under review"),
    "ope-19": ("process", ""),
    "sec-5": ("process", "CloudTrail's `CreateCluster` event names the principal that created the "
                         "cluster, but only the trail's configuration is collected, never its events"),
    "sec-7": ("process", "the RoleBindings and ClusterRoleBindings are collected, and `rbac-2` scores "
                         "their scope; which subjects count as super-administrators is not a field"),
    "sec-13": ("process", "asks about the fleet and its AWS accounts, not about this cluster"),
    "sec-19": ("process", "a kube-bench Job or CronJob would appear in `jobs.json`/`cronjobs.json`; a "
                          "scan run from outside the cluster leaves nothing inside it"),
    "sec-20": ("process", ""),
    "sec-24": ("process", "`sec-8` already measures External Secrets Operator and `sec-38` the KMS "
                          "key; which of the mechanisms is the strategy is a decision, not a field"),
    "sec-32": ("process", "an admission policy that verifies signatures would appear in "
                          "`kyverno.json`, which `adm-2` reads; signing itself happens in the build "
                          "pipeline, which this review never sees"),
    "sec-34": ("process", ""),
    "sec-35": ("process", "the tools are partly visible — `sec-8` measures ESO, and cert-manager "
                          "would be in `deployments.json` — but the rotation cadence is not"),
    "sec-36": ("process", "same as sec-19: an in-cluster scan Job would be visible, an external "
                          "scanner or Security Hub standard is not"),
    "sec-37": ("process", "same as sec-19: an in-cluster scan Job would be visible, an external "
                          "scanner or Security Hub standard is not"),
    "cost-4": ("process", "the spend is in Cost Explorer and a budget or anomaly monitor is one API "
                          "call away, but whether anyone reviews them is not a cluster fact"),
    # ---- observable, not collected
    "ope-9": ("not-collected", "`aws cloudwatch describe-alarms` (and the log-group metric filters "
                               "the alarms would watch) answers this; CloudWatch is not called"),
    "rel-10": ("not-collected", "`kubectl get volumesnapshotclasses,volumesnapshots` — the CSI "
                                "snapshot CRDs are not collected"),
    "rel-12": ("not-collected", "a schedule lives in an AWS Backup plan "
                                "(`aws backup list-backup-plans`) or a snapshot-scheduler CRD; "
                                "neither is collected"),
    "sec-22": ("not-collected", "`aws efs describe-file-systems` returns `Encrypted` directly; EFS "
                                "is not collected. This is a collection choice, not an "
                                "observability limit"),
    "sec-23": ("not-collected", "`aws efs describe-file-systems` plus the EFS CSI driver's mount "
                                "options; EFS is not called, and a PersistentVolume without an "
                                "explicit `tls` option does not prove TLS is off — the driver "
                                "enables it by default"),
    # ---- observable from data already collected
    "rel-14": ("collected", "`deployments.json` carries `.spec.replicas`, and `rel-7` already "
                            "computes `>1` over the same file"),
    "rel-15": ("collected", "`services.json` carries `.spec.type`, and `lens-9` already reports on "
                            "LoadBalancer services from it"),
    "rel-17": ("collected", "`ope-16` already measures the `coredns` managed add-on and `ope-2` "
                            "matches `external-dns` over `deployments.json`"),
    "sec-3": ("collected", "`awsauth.json` is collected and `rbac-1` reads it; `data.mapRoles` versus "
                           "`data.mapUsers` is exactly this question. On an `API`-mode cluster the "
                           "equivalent evidence is `aws eks list-access-entries`, which is not "
                           "collected"),
    "sec-14": ("collected", "`sec-4` already scores NetworkPolicy coverage — and whether the CNI can "
                            "enforce it — over `namespaces.json` and `networkpolicies.json`"),
    "perf-7": ("collected", "`nodes.json` carries `capacity` and `allocatable`, and `pods.json` the "
                            "requests `perf-1` already reads"),
    "cost-5": ("collected", "`pvc.json` carries `.spec.resources.requests.storage`, and "
                            "`pv.json`/`volumes.json` the provisioned size `cost-6`/`sec-21` read"),
}

GOV_GROUPS = [
    ("process", "Process or policy &mdash; no cluster field states the answer",
     "Nothing in <code>aws</code> or <code>kubectl</code> output settles these: they are facts about "
     "how a team works, about the wider environment, or judgements cluster state cannot make. Where a "
     "partial signal exists it is named, because a signal that can only prove a <em>yes</em> is not an "
     "answer."),
    ("not-collected", "Observable, but not collected by this skill",
     "A documented AWS or Kubernetes API returns the answer and this review does not call it. That is "
     "a collection choice, not a limit on what can be seen &mdash; the call is named on each line."),
    ("collected", "Observable from data already collected &mdash; routed to the interview",
     "The files this run already wrote contain the answer, and for most of these another question in "
     "this report is scored from the same field. They are asked rather than measured by choice, so "
     "treat them as <em>not verified</em>, not as unverifiable."),
    ("unclassified", "Reason not recorded",
     "These ids are missing from <code>GOV_UNASSESSED</code> in <code>render-report.py</code>. The "
     "report will not invent a reason for them: add one there when you add the question."),
]

# ---------------------------------------------------------------------------
# Why a question came back `na`. One state in results.jsonl, three completely different situations —
# and the report used to describe all three as coverage that better observation would improve:
#
#   STRUCTURAL   the question can NEVER apply to this cluster as built. fargate-1..4 on an EC2
#                cluster, a DaemonSet question on Fargate, an instance-type question on serverless
#                compute, a retired question, one deduplicated against another. No amount of extra
#                collection makes these measurable, so counting them as missing coverage
#                permanently caps a pillar: Operational Excellence sits at 12/19 = 63% on EVERY
#                non-Fargate cluster and cannot exceed 74%, which fired the "thin evidence,
#                provisional, not a verdict" marker on all of them — including over a genuinely
#                broken score of 38, which it then pre-discounted for the reader.
#   NO_SUBJECT   the question applies, but there is nothing of that kind on the cluster to look at:
#                0 workload Deployments, no Jobs, no LoadBalancer Services. Deploy one and it becomes
#                measurable. Nothing was unobservable — there was nothing there. Saying "too little
#                of this cluster is observable" about an empty cluster is simply the wrong statement.
#   UNOBSERVED   anything else: the honest default. A reason this table does not recognise must not
#                be silently promoted into either of the two categories above.
#
# Matched against the scorer's own `na~...` reason text, which is already carried in `detail`.
NA_STRUCTURAL = re.compile(r"fargate|impossible|serverless compute|no EC2 nodes"
                           r"|deduplicat|same signal as|^retired\b", re.I)
NA_NO_SUBJECT = re.compile(r"^(?:no\b|0/0\b)", re.I)


def na_reason(detail):
    """Classify one `na` detail as 'structural', 'no_subject' or 'unobserved'."""
    d = (detail or "").strip()
    if NA_STRUCTURAL.search(d):
        return "structural"
    if NA_NO_SUBJECT.match(d):
        return "no_subject"
    return "unobserved"


def na_split(recs):
    """(structural, no_subject, unobserved) counts over the `na` records given."""
    kinds = [na_reason(r.get("detail")) for r in recs if r.get("state") == "na"]
    return (kinds.count("structural"), kinds.count("no_subject"), kinds.count("unobserved"))


# state -> (Cloudscape status-indicator type, label)
STATE_UI = {
    "all":  ("success", "Pass"),
    "most": ("info", "Mostly"),
    "some": ("warning", "Partial"),
    "none": ("error", "Fail"),
    "na":   ("inactive", "Not applicable"),
}


def sev_of(qid):
    return 3 if qid in SEV3 else 1 if qid in SEV1 else 2


def rating(score):
    if not isinstance(score, (int, float)):
        return "—"
    return ("Excellent" if score >= 90 else "Good" if score >= 80 else
            "Fair" if score >= 70 else "Needs improvement" if score >= 60 else "Poor")


def risk(score):
    """Band derived from the configuration score alone: >=80 Low, >=60 Medium, <60 High.

    NOT an assessed threat level. Nothing about exposure, exploitability, data sensitivity or blast
    radius feeds this — it is a restatement of the same number in the adjacent column. The table header
    says "Risk (from score)" for that reason: a bare green "Low" beside a Security row reads as "this
    cluster is at low risk", when it means "this cluster scored >=80 on configuration presence".
    """
    if not isinstance(score, (int, float)):
        # NOT "Not assessed". A pillar reaches this branch because it fell below the 50% coverage gate,
        # which withholds the BAND — every applicable question in it was asked and answered, and they
        # are all listed in the pillar section below. On /tmp/r2/micro, Reliability answered 10 of its
        # 22 questions and this cell told the reader none of them had been assessed.
        return ("inactive", "No band published")
    return (("success", "Low") if score >= 80 else
            ("warning", "Medium") if score >= 60 else ("error", "High"))


def e(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load(work):
    work = pathlib.Path(work)

    # A work-dir argument that names a FILE used to fall through to the generic "required file
    # missing: <work>/scores.json" refusal below — true, but the wrong diagnosis: the problem is the
    # argument itself, not any one file under it. Checked before anything is read.
    if work.exists() and work.is_file():
        sys.exit(f"render-report: {work} is a file, not a directory — pass the work directory that "
                 f"contains scores.json and results.jsonl")

    def j(name, default=None):
        p = work / name
        if not p.exists():
            if default is None:
                sys.exit(f"render-report: required file missing: {p}")
            return default
        try:
            text = p.read_text()
        except OSError as exc:
            # `p.exists()` says the file is THERE, not that it is readable. A mode-000 or
            # otherwise-unreadable collection file raised a raw PermissionError traceback out of the
            # middle of load(), which is the one failure mode in this loader that did not get the
            # clean `render-report: ...` refusal every neighbouring guard gives.
            sys.exit(f"render-report: could not read {p} ({exc}) — refusing to render a report from "
                     f"data the scorers could not have read either")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            sys.exit(f"render-report: {p} is not valid JSON ({exc}) — refusing to render a "
                     f"report from data the scorers could not have read either")

    import datetime
    collected = datetime.datetime.utcfromtimestamp(
        (work / "results.jsonl").stat().st_mtime).strftime("%Y-%m-%d %H:%M UTC") \
        if (work / "results.jsonl").exists() else "unknown"

    # Shape helpers. Every one of these guarded only a MISSING key before, not a present-but-wrong
    # value, so `{"items": null}`, `{"cluster": "oops"}`, `"pillars": {...}` and `scores.json` as `[]`
    # all produced raw tracebacks instead of the graceful refusal the rest of this loader gives.
    def need_obj(val, what):
        if not isinstance(val, dict):
            sys.exit(f"render-report: {what} should be a JSON object, got {type(val).__name__} — "
                     f"refusing to render from data of the wrong shape")
        return val

    def opt_list(val, what):
        """For keys that are legitimately absent (an optional API field)."""
        return [] if val is None else need_list(val, what)

    def need_list(val, what):
        if val is None:
            sys.exit(f"render-report: {what} is null — a malformed collection file must not be read as "
                     f"an empty one. With viability in the score contract, an empty node list means "
                     f"NOT VIABLE, so this would report a dead cluster instead of a bad file.")
        if not isinstance(val, list):
            sys.exit(f"render-report: {what} should be a JSON list, got {type(val).__name__} — "
                     f"refusing to render from data of the wrong shape")
        return val

    scores = need_obj(j("scores.json"), "scores.json")
    scores["pillars"] = opt_list(scores.get("pillars"), "scores.json .pillars")
    for i, pil in enumerate(scores["pillars"]):
        need_obj(pil, f"scores.json .pillars[{i}]")
    need_obj(scores.get("governance") or {}, "scores.json .governance")

    # Non-finite and out-of-range scores render as confident nonsense: 200 became
    # "200 / 100 · Excellent · Low risk", and NaN drew a FULL-WIDTH bar beside a red "Poor / High"
    # badge, because min(100, nan) is 100 in Python. Rejected at the door instead.
    def sane_score(v, what):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return v                                  # strings like "INSUFFICIENT" are legitimate
        if v != v or v in (float("inf"), float("-inf")):
            sys.exit(f"render-report: {what} is {v!r} — not a number this report can present")
        if not 0 <= v <= 100:
            sys.exit(f"render-report: {what} is {v}, outside 0-100 — refusing to present it as a score")
        return v

    sane_score(scores.get("technical_overall"), "scores.json .technical_overall")
    for pil in scores["pillars"]:
        sane_score(pil.get("score"), f"scores.json .pillars[{pil.get('pillar')}].score")
    # The governance score renders in the identical 42px .score-hero treatment as the pillar scores
    # above — sane_score guarded every one of THOSE, but not this one, which is the same class of bug
    # the guard's own comment says it eliminated: 250 rendered "250 / 100" and NaN drew a full-width
    # bar, both at exit 0.
    sane_score((scores.get("governance") or {}).get("score"), "scores.json .governance.score")

    # The question counts used to reach e() and nothing else, so a non-integer rendered as harmless
    # text. They now also feed arithmetic — the coverage denominator adds the pillar's process
    # questions, and the thin-evidence basis subtracts its structurally-inapplicable ones — so a
    # string here is a TypeError mid-render instead. Same treatment as sane_score: rejected at the
    # door, because a count that is not a count cannot be presented as one either way.
    def sane_count(v, what):
        if v is None:
            return
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            sys.exit(f"render-report: {what} is {v!r} — a question count must be a non-negative "
                     f"integer")

    for pil in scores["pillars"]:
        for ck in ("applicable", "total", "na"):
            sane_count(pil.get(ck), f"scores.json .pillars[{pil.get('pillar')}].{ck}")

    results = []
    rp = work / "results.jsonl"
    if not rp.exists():
        sys.exit(f"render-report: required file missing: {rp}")
    try:
        rp_text = rp.read_text()
    except OSError as exc:            # same hole as j(): exists() is not readable()
        sys.exit(f"render-report: could not read {rp} ({exc})")
    for n, line in enumerate(rp_text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.exit(f"render-report: {rp} line {n} is not valid JSON ({exc}) — a truncated results "
                     f"file means the scorers were interrupted; re-run them rather than render this")
        if not isinstance(rec, dict):
            sys.exit(f"render-report: {rp} line {n} is a {type(rec).__name__}, not an object")
        # Every downstream read of a record assumes these four keys are present without checking —
        # the pillar sort below is a bare `r["id"]`, not `.get("id")` — so a record missing one raised
        # a raw `KeyError` instead of the `render-report: …` refusal every other malformed-input path
        # in this file gives. `reduce.sh` gained the identical MISSINGFIELDS guard this round; matched
        # here in wording so the two read as one system, since a results.jsonl that never went through
        # the reducer must refuse the same way one that did would have.
        missing = [f for f in ("pillar", "id", "track", "state")
                   if rec.get(f) is None or (isinstance(rec.get(f), str) and rec.get(f) == "")]
        if missing:
            sys.exit(f"render-report: {rp} line {n} has record(s) missing a required field -- every "
                     f"record must carry pillar, id, track and state -- missing/empty: "
                     f"{','.join(missing)} -- {json.dumps(rec)[:80]}")
        # `state` is an enum, not free text. An unrecognised value — a typo, or a future state this
        # renderer predates — used to fall through STATE_UI.get(state, ("inactive", state)) below and
        # render in the identical muted grey as a legitimate `na`, with no sign anything was wrong.
        # `unknown` is legal ONLY on the governance track (the interactive-mode placeholder before an
        # interview answer lands) — same exception reduce.sh's own BADSTATE gate makes.
        is_gov = rec.get("track") == "governance"
        legal_states = set(STATE_UI) | ({"unknown"} if is_gov else set())
        if rec.get("state") not in legal_states:
            sys.exit(f"render-report: {rp} line {n} has illegal state {rec.get('state')!r} for id "
                     f"{rec.get('id')!r} -- legal: {', '.join(sorted(STATE_UI))}"
                     + (", unknown" if is_gov else "")
                     + " -- refusing to render a state this report has no styling for")
        results.append(rec)

    # A repeated id renders twice in the same pillar table with two opposite verdicts and no sign
    # anything is wrong — the reader sees one question listed as both Pass and Fail. `reduce.sh`
    # refuses duplicates before this file ever runs, so this is only reachable with a stale
    # `scores.json` sitting beside a freshly re-scored `results.jsonl`, but the renderer must not
    # depend on that having happened. Refuses rather than dedupes: which of two contradictory verdicts
    # would be "right" is not this file's decision to make silently.
    dup_counts = {}
    for r in results:
        dup_counts[r["id"]] = dup_counts.get(r["id"], 0) + 1
    dup_ids = sorted(rid for rid, c in dup_counts.items() if c > 1)
    if dup_ids:
        sys.exit(f"render-report: {rp} has duplicate question id(s) -- each question must appear "
                 f"exactly once: {', '.join(dup_ids[:10])}"
                 + (f" and {len(dup_ids) - 10} more" if len(dup_ids) > 10 else ""))

    # Every collected file, so the resource extractors can name what a check actually looked at.
    raw = {}
    for p in sorted(work.glob("*.json")):
        if p.name in ("scores.json",):
            continue
        try:
            raw[p.stem] = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            raw[p.stem] = None
    return {
        "scores": scores,
        "results": results,
        "raw": raw,
        "collected": collected,
        "cluster": need_obj(need_obj(j("cluster.json", {}), "cluster.json").get("cluster") or {},
                            "cluster.json .cluster"),
        "nodes": need_list(need_obj(j("nodes.json", {"items": []}), "nodes.json").get("items"),
                           "nodes.json .items"),
        "fargate": opt_list(j("fargate.json", {}).get("fargateProfileNames"),
                            "fargate.json .fargateProfileNames"),
        "podidentity": opt_list(j("podidentity.json", {}).get("associations"),
                                "podidentity.json .associations"),
        "oidcproviders": opt_list(j("oidcproviders.json", {}).get("OpenIDConnectProviderList"),
                                  "oidcproviders.json .OpenIDConnectProviderList"),
        "pods": need_list(need_obj(j("pods.json", {"items": []}), "pods.json").get("items"),
                          "pods.json .items"),
    }


def _strip_quote_markers(text):
    """Remove the leading `>` from EVERY line of a markdown blockquote, not just the first.

    The rationale regex consumes the opening `>` and nothing else, so a rationale authored as a
    multi-line blockquote — the correct style for anything longer than one line — kept a marker at
    every wrap point and printed them mid-sentence in a customer-facing report: "…Enabling it >
    wraps the data key with a customer-managed KMS key…". Eight rationales and four remediation
    notes were affected, and the count only grows as rationales get longer.

    Anchored to the line START and fence-aware, so `>` characters that are part of the CONTENT
    survive untouched — shell redirects and jq comparisons such as `select(.spec.replicas//1)>1`
    are mid-line, and nothing inside a ``` fence is touched at all.
    """
    out, fenced = [], False
    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            out.append(ln)
            continue
        out.append(ln if fenced else re.sub(r"^\s*>\s?", "", ln))
    return "\n".join(out)


def question_prose(ref_dir):
    """Map question id -> {title, rationale, remediation, source_file}, from the reference files.

    results.jsonl carries only an id and a machine detail, so without this the report would be a
    wall of `sec-11  none  0/4 PSS labels` with no statement of what to DO about it. All four fields
    come from the same files that define the questions, so the advice cannot drift from the scorer
    that produced the finding.
    """
    prose = {}
    ref = pathlib.Path(ref_dir)
    if not ref.is_dir():
        return prose
    for md in sorted(ref.rglob("*.md")):
        txt = md.read_text()
        # [pre, id, title, body, id, title, body, ...]
        parts = re.split(r"^###\s+([a-z]+-\d+)\s*:\s*(.+?)\s*$", txt, flags=re.M)
        for i in range(1, len(parts) - 2, 3):
            qid, title, body = parts[i], parts[i + 1], parts[i + 2]
            if qid in prose:
                continue
            rat = re.search(r"^>\s*(.+?)(?:\n\n|\n[^>])", body, re.S | re.M)
            rem = re.search(r"^\*\*Remediation:?\*\*:?\s*(.*?)(?=\n---|\n### |\Z)",
                            body, re.S | re.M)
            # A variant marker -- "**Remediation — path 1:**", a typo, anything the strict pattern
            # above does not match exactly -- used to fail SILENTLY: `rem` is None, `remediation`
            # becomes "", and the panel just renders an empty "How to fix" for that question, which
            # looks identical to a question that legitimately has no remediation. On a High-severity
            # finding that is the worst place for a silent failure to land. This is a loose match
            # against the same line start, so it fires whenever the strict one did not.
            if not rem and re.search(r"^\*\*Remediation\b", body, re.M):
                print(f"render-report: WARNING: {md} question {qid!r} has a line starting "
                      f"'**Remediation' that did not match the expected '**Remediation:**' marker "
                      f"-- its \"How to fix\" panel will render EMPTY.", file=sys.stderr)
            prose[qid] = {
                "title": title,
                "rationale": (" ".join(_strip_quote_markers(rat.group(1)).split())
                              if rat else ""),
                "remediation": (_strip_quote_markers(rem.group(1)).strip() if rem else ""),
                "source": str(md.relative_to(ref)),
            }
    return prose


# Scorer helper -> number of collection files it reads before the jq program. DERIVED from the name,
# never tabulated.
#
# This was the literal dict {"m": 1, "m2": 2, "m3": 3, "m4": 4} alongside a regex `^(m[234]?)\s+`.
# When `sec-4` grew to `m7` -- NetworkPolicy enforcement is opt-in on both cluster shapes and the two
# opt-ins live in different files, so its minimum evidence set is five -- the line stopped matching and
# `sec-4` fell out of the provenance map entirely. It rendered with no "Data read", no "Exact command
# used" and no "Returned": the audit trail gone from a High-severity finding, at exit 0. No gate caught
# it, because `validate-render.sh` compared label counts against the measured question total while the
# report renders more panels than that, so one missing trio hid in the slack.
#
# A table that must be edited whenever a helper is added is the drift surface this project keeps
# finding. `m` reads one file and `mN` reads N, so the number is in the name -- read it from there and
# a future `m5`/`m8` needs no edit here.
_SCORER_RE = re.compile(r"^(m\d*)\s+([a-z]+-\d+)\s+(.*)$")
# Deliberately looser: anything that LOOKS like a scorer call. Used only to notice a line the strict
# pattern failed to parse, so the next arity surprise is loud instead of silent.
_SCORER_LOOSE_RE = re.compile(r"^(m\S*)\s+([a-z]+-\d+)\b")


def _helper_arity(helper):
    return 1 if helper == "m" else int(helper[1:])


def scorer_provenance(ref_dir):
    """Map question id -> {files, jq, helper}: exactly which collected JSON the detection read and
    the expression it evaluated.

    This is the audit trail. A finding that says `0/4 PSS labels` is only trustworthy if the reader
    can see it came from `namespaces.json` and check the expression that produced it. Parsed from the
    committed scorer lines, so it is the real detection, not a paraphrase of one.
    """
    prov = {}
    ref = pathlib.Path(ref_dir)
    if not ref.is_dir():
        return prov
    for md in sorted(ref.rglob("*.md")):
        for line in md.read_text().splitlines():
            mt = _SCORER_RE.match(line)
            if not mt:
                loose = _SCORER_LOOSE_RE.match(line)
                if loose:
                    sys.stderr.write(
                        "render-report: WARNING scorer line for %s uses helper %r and could not be "
                        "parsed for provenance -- that question will render with no audit trail. "
                        "%s\n" % (loose.group(2), loose.group(1), md.name))
                continue
            helper, qid, rest = mt.group(1), mt.group(2), mt.group(3)
            head, _, jq = rest.partition("'")
            prov[qid] = {
                "files": head.split()[:_helper_arity(helper)],
                "jq": jq.rstrip("'"),
                "helper": helper,
            }
    return prov


# Two kinds of jq `test(` appear in these scorers, and only one of them is a detection:
#   SCOPING     `select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)` and the RBAC
#               `^(system:|eks:)` equivalents. These EXCLUDE objects from a denominator. Nearly every
#               counting scorer has one and none of them is matching a name to find a tool, so they
#               are removed before the question is asked.
#   DETECTION   `select(.metadata.name|test("prometheus|grafana"))`. Here the name match IS the
#               verdict, which is a materially weaker kind of evidence and has to be disclosed.
_JQ_SCOPING = re.compile(r'test\(\s*"\^?\(?(?:kube-|amazon-|system:|eks:)[^"]*"\s*\)')
_JQ_NAME_TEST = re.compile(r'(?:\bname\b|\bnamespace\b|\bimage\b|\baddons\b)[^;]{0,14}?'
                           r'\|\s*(?:(?:select|any|map|all)\(\s*)?test\(')


def name_pattern_based(jq):
    """True when the scorer decides this question by matching a regex against a resource NAME
    (or namespace, or container image, or add-on id) rather than by reading a field that states the
    answer.

    Read off the scorer's own jq — the same text the panel prints under "Exact command used" — rather
    than a hardcoded list of question ids, because a hardcoded list is exactly what went stale in
    RESOURCES and in every count-in-a-comment this file has had to remove.
    """
    if not jq:
        return False
    return bool(_JQ_NAME_TEST.search(_JQ_SCOPING.sub("", jq)))


# ---------------------------------------------------------------------------
# Observed resources — WHICH objects a check looked at, and which side each fell on.
#
# Why this exists: "3/3 core addons" is a claim the reader cannot check. "vpc-cni, coredns,
# kube-proxy" is one they can verify in seconds. Every historic scoping bug in this project was a
# CORRECT COUNT OVER THE WRONG SET — net-2's clean-SG offender was an unrelated ECS security group,
# sec-21 read 4/4 encrypted while most cluster EBS was not, rel-7's passes were all AWS-installed
# Deployments. A count hides all three; a named list exposes them immediately.
#
# THE SAFETY PROPERTY. These extractors are a SECOND reading of the same data, so they could disagree
# with the scorer that produced the score. That would be worse than showing nothing. So every
# extractor is checked against the scorer's own `N/M` in the detail string, and a mismatch FAILS the
# gate rather than rendering a plausible-looking list. Read `resource_agreement()` before adding one.
# ---------------------------------------------------------------------------
SYS_NS = re.compile(r"^(kube-|amazon-)")
CORE_ADDONS = ("vpc-cni", "coredns", "kube-proxy")


def _items(data, f):
    d = data["raw"].get(f) or {}
    return d.get("items") or []


def _nm(i):
    return (i.get("metadata") or {}).get("name", "?")


def _qn(i):
    m = i.get("metadata") or {}
    return f'{m.get("namespace","")}/{m.get("name","?")}'


def _workload(items):
    return [i for i in items
            if not SYS_NS.match(((i.get("metadata") or {}).get("namespace") or ""))]


def _split(items, ok, name=_qn):
    """Partition a list into (passing names, failing names)."""
    p, f = [], []
    for i in items:
        (p if ok(i) else f).append(name(i))
    return sorted(p), sorted(f)


def _labels(i):
    return (i.get("metadata") or {}).get("labels") or {}


def _containers(pods):
    out = []
    for p in pods:
        for c in (p.get("spec") or {}).get("containers") or []:
            out.append((p, c))
    return out


def _automode_compute(d):
    """The one place that reads the Auto Mode compute flag, for every extractor that branches on it.

    Three hand-copies of `(cluster.computeConfig or {}).get("enabled") is True` is the shape this
    project keeps finding drifted, so there is one.

    Deliberately NOT the gate for load-balancing or block-storage credit: those are separate fields
    (`kubernetesNetworkConfig.elasticLoadBalancing.enabled`, `storageConfig.blockStorage.enabled`).
    AWS requires all three to be set together -- docs.aws.amazon.com/eks/latest/userguide/auto-disable.html
    "The compute, block storage, and load balancing capabilities must all be enabled or disabled in the
    same request" -- but the API models them independently, so an extractor that means "storage" must
    read the storage field rather than assume this one implies it.
    """
    return (d["cluster"].get("computeConfig") or {}).get("enabled") is True


def _automode_all_nodes(d):
    """True only when EVERY EC2 node is an Auto Mode node. The gate for NODE-scoped capabilities.

    `_automode_compute` says Auto Mode is enabled on the CLUSTER. It says nothing about whether a
    given node got the capability, and AWS is explicit that a mixed cluster does not:
    docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html -- "However, if your cluster combines
    Auto mode with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS
    Fargate, these add-ons remain necessary." Coexistence is a supported state, not a misconfiguration:
    automode-learn-instances.html -- "You can install both during a migration or in an advanced
    configuration."

    Using the cluster flag for a node-scoped panel printed "there is no managed add-on to update" and
    "AWS owns the VPC CNI's version and health" on a cluster where two of three nodes still ran
    `aws-node` and `kube-proxy` -- next to the scorer's own honest hybrid detail saying so. No
    cross-check caught it, because the hybrid arms spell their counts in prose rather than as `n/m`, so
    `resource_agreement` had no ratio to compare.

    Mirrors the scorers' membership test exactly -- `references/operational-excellence.md` and
    `reliability.md` both use `computeConfig.enabled==true and $t>0 and $auto==$t` over non-Fargate
    nodes, in eight places. CHANGE ONE, CHANGE ALL: this is the ninth.
    """
    if not _automode_compute(d):
        return False
    ec2 = [n for n in _items(d, "nodes")
           if (_labels(n).get("eks.amazonaws.com/compute-type") or "") != "fargate"]
    if not ec2:
        return False
    return all((_labels(n).get("eks.amazonaws.com/compute-type") or "") == "auto" for n in ec2)


def _res_addons(d):
    # On Auto Mode this question loses its subject rather than failing it. AWS runs the VPC CNI, CoreDNS
    # and kube-proxy as service functionality, so there is no managed add-on to inspect and the three
    # names are not absences an operator can act on. Rendering them as "Counted as failing (3)" beneath
    # the scorer's Pass verdict made the panel contradict itself in the reader's face -- a Pass and its
    # own evidence of failure, on the same card.
    # docs.aws.amazon.com/eks/latest/userguide/auto-upgrade.html -- "Additionally, you no longer need to
    # update components like: Amazon VPC CNI / AWS Load Balancer Controller / CoreDNS / kube-proxy /
    # Karpenter / AWS EBS CSI driver ... EKS Auto Mode replaces these components with service
    # functionality."
    if _automode_all_nodes(d):
        return {"kind": "field",
                "pass": ["computeConfig.enabled = true (EKS Auto Mode runs the VPC CNI, CoreDNS and "
                         "kube-proxy as service functionality, so there is no managed add-on to update)"],
                "fail": [], "pass_label": "Cluster setting read",
                "context": sorted((d["raw"].get("addons") or {}).get("addons") or []),
                "context_label": "add-ons the operator installed on top of Auto Mode's built-in components"}
    have = (d["raw"].get("addons") or {}).get("addons") or []
    core = [a for a in have if a in CORE_ADDONS]
    return {"pass": sorted(core),
            "fail": sorted(a for a in CORE_ADDONS if a not in have),
            "context": sorted(a for a in have if a not in CORE_ADDONS),
            "context_label": "other add-ons installed (not counted by this check)"}


def _res_lens7(d):
    # Same reason as _res_addons, for the VPC CNI alone. Was a lambda that always emitted
    # "vpc-cni not a managed add-on" as a failure line, which on Auto Mode is true and irrelevant:
    # docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html -- "With Amazon EKS Auto Mode, you
    # don't need to install or upgrade networking add-ons. Auto Mode includes pod networking and load
    # balancing capabilities."
    if _automode_all_nodes(d):
        return {"kind": "field",
                "pass": ["computeConfig.enabled = true (AWS owns the VPC CNI's version and health; "
                         "a new node AMI ships roughly weekly)"],
                "fail": [], "pass_label": "Cluster setting read"}
    have = (d["raw"].get("addons") or {}).get("addons") or []
    return {"pass": [a for a in have if a == "vpc-cni"],
            "fail": [] if "vpc-cni" in have else ["vpc-cni not a managed add-on"]}


def _res_trails(d):
    trails = (d["raw"].get("cloudtrail") or {}).get("trailList") or []
    region = (d["cluster"].get("arn", "").split(":")[3] if d["cluster"].get("arn") else "")
    p, f = [], []
    for t in trails:
        nm = t.get("Name", "?")
        multi, home = t.get("IsMultiRegionTrail"), t.get("HomeRegion", "")
        why = "multi-region" if multi else f"home region {home}"
        (p if (multi or home == region) else f).append(f"{nm} ({why})")
    return {"pass": sorted(p), "fail": sorted(f)}


def _res_logtypes(d):
    want = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
    on = set()
    for grp in (d["cluster"].get("logging") or {}).get("clusterLogging") or []:
        if grp.get("enabled"):
            on |= set(grp.get("types") or [])
    return {"pass": [t for t in want if t in on], "fail": [t for t in want if t not in on]}


def _vol_is_ours(v, cn):
    """Is this EBS volume tagged to the cluster under review?

    `describe-volumes` is collected account- and region-wide with no filter, so this predicate is the
    only thing separating the reviewed cluster's disks from every other cluster's in the same account.
    Two tag forms count, and both bind the CLUSTER NAME:
      - `kubernetes.io/cluster/<name>`  — the in-tree/ALB ownership tag; the name is in the KEY and the
        value is `owned`/`shared`, so the key alone is sufficient.
      - any key mentioning "cluster" whose VALUE is the cluster name — covers
        `ebs.csi.aws.com/cluster-name`, which the EBS CSI driver sets.

    What is deliberately NOT accepted, because each produced a wrong denominator on a High-severity
    question:
      - a bare `Value == cn` with no constraint on the key: a volume tagged `Name=<cluster>` — an
        unrelated disk someone named after the cluster — counted as in scope.
      - `Key == "ebs.csi.aws.com/cluster-name"` with no constraint on the value: a volume belonging to a
        DIFFERENT cluster using the same standard CSI tag counted as in scope. On an account running two
        clusters in one region — the common case — another cluster's unencrypted volume turned this
        cluster's `all` (1/1) into `some` (1/2), a 50-point swing at severity weight 3.
    Kept identical to the `sec-21`/`cost-8` jq in references/, which has the same two clauses. EDIT ALL
    OF THEM OR NONE — nothing enforces the agreement, and a mismatch here surfaces as a contradiction
    banner rather than a wrong number.
    """
    for t in v.get("Tags") or []:
        k, val = t.get("Key") or "", t.get("Value") or ""
        if k == f"kubernetes.io/cluster/{cn}":
            return True
        if cn and val == cn and "cluster" in k.lower():
            return True
    return False


def _res_volumes(d, want_encrypted=True):
    vols = (d["raw"].get("volumes") or {}).get("Volumes") or []
    cn = d["cluster"].get("name", "")
    mine = [v for v in vols if _vol_is_ours(v, cn)]
    others = [v.get("VolumeId", "?") for v in vols if v not in mine]
    p, f = [], []
    for v in mine:
        vid = f'{v.get("VolumeId","?")} ({v.get("Size","?")} GiB, {v.get("VolumeType","?")})'
        (p if v.get("Encrypted") else f).append(vid)
    # The scoping rule is what the reader needs to check here, not the identity of other workloads'
    # disks. Listing up to 10 out-of-scope volume IDs put account-scoped identifiers for resources
    # OUTSIDE the review into a report written to be emailed and pasted into tickets. The count still
    # proves the exclusion happened and is still falsifiable against `describe-volumes`.
    return {"pass": sorted(p), "fail": sorted(f),
            "context": ([f"{len(others)} volume(s) in the VPC are not tagged to this cluster and were "
                         f"excluded from the score (identifiers omitted \u2014 they belong to workloads "
                         f"outside this review)"] if others else []),
            "context_label": "scope of this check"}


def _res_unattached(d):
    vols = (d["raw"].get("volumes") or {}).get("Volumes") or []
    cn = d["cluster"].get("name", "")
    mine = [v for v in vols if _vol_is_ours(v, cn)]
    p, f = [], []
    for v in mine:
        vid = f'{v.get("VolumeId","?")} ({v.get("State","?")})'
        (p if v.get("State") != "available" else f).append(vid)
    # Labels stated explicitly rather than defaulted, because "passing" on this check means the volume
    # is IN USE. The scorer used to emit failures/total ("1/4 unattached") while this list counts
    # passes, so the two disagreed on direction: guaranteed a false contradiction whenever idle was not
    # exactly half, and a false agreement when it was. The scorer now emits passes/total.
    return {"pass": sorted(p), "fail": sorted(f),
            "pass_label": "Attached, doing work",
            "fail_label": "Unattached and still billing"}


def _res_sg(d, ok):
    sgs = (d["raw"].get("sg") or {}).get("SecurityGroups") or []
    v = d["cluster"].get("resourcesVpcConfig") or {}
    mine = set(v.get("securityGroupIds") or []) | {v.get("clusterSecurityGroupId")}
    scoped = [g for g in sgs if g.get("GroupId") in mine]
    # COUNT, not names. These are security groups belonging to OTHER workloads in a possibly-shared
    # VPC; naming them widens the report's blast radius past the cluster under review, and the Method
    # section promises out-of-scope identifiers are counted rather than named. _res_volumes and
    # _res_sec18 were fixed for this; these two were missed.
    others = [g for g in sgs if g.get("GroupId") not in mine]
    p, f = _split(scoped, ok, lambda g: f'{g.get("GroupId","?")} ({g.get("GroupName","?")})')
    return {"pass": p, "fail": f, "context": ([f"{len(others)} security group(s) in the VPC are not used by this "
                        f"cluster and were excluded (identifiers omitted \u2014 they belong to "
                        f"other workloads)"] if others else []),
            "context_label": "scope of this check"}


def _sg_clean(g):
    for perm in g.get("IpPermissions") or []:
        openv4 = any(r.get("CidrIp") == "0.0.0.0/0" for r in perm.get("IpRanges") or [])
        if not openv4:
            continue
        lo, hi = perm.get("FromPort"), perm.get("ToPort")
        if lo in (80, 443) and hi in (80, 443):
            continue
        return False
    return True


def _sg_no_ssh(g):
    """IpProtocol "-1" means ALL protocols on ALL ports and carries NO FromPort/ToPort (both are
    `Required: No` in the EC2 API). The old `lo <= 22 <= hi` test therefore read 0 <= 22 <= 0, which is
    false, and a security group open to the entire internet on every port PASSED this High-severity
    SSH check. Twin of the scorer in references/security/identity-access.md — change both together.

    The source of the rule must be 0.0.0.0/0, exactly as the scorer requires
    (`.IpRanges[]?.CidrIp=="0.0.0.0/0"`). Accepting any non-empty IpRanges OR UserIdGroupPairs
    diverged from it in two ways, both of which listed a security group as "counted as failing"
    underneath a panel the scorer had marked Pass:
      - EKS's own default cluster SG carries an ALL-protocols rule whose source is the SG itself
        (`UserIdGroupPairs`, described "Allows EFA traffic, which is not matched by CIDR rules")
        with `IpRanges: []`. That is self-referencing node-to-node traffic, not internet exposure.
      - An SSH rule correctly narrowed to a private CIDR such as 10.0.0.0/8 was flagged too, so
        the customers who had done exactly the right thing saw their SG named as the problem."""
    for perm in g.get("IpPermissions") or []:
        lo, hi = perm.get("FromPort") or 0, perm.get("ToPort") or 0
        covers_22 = perm.get("IpProtocol") == "-1" or lo <= 22 <= hi
        world_open = any(r.get("CidrIp") == "0.0.0.0/0" for r in (perm.get("IpRanges") or []))
        if covers_22 and world_open:
            return False
    return True


def _res_subnets(d, ok, label):
    subs = (d["raw"].get("subnets") or {}).get("Subnets") or []
    mine = set((d["cluster"].get("resourcesVpcConfig") or {}).get("subnetIds") or [])
    scoped = [s for s in subs if s.get("SubnetId") in mine]
    # COUNT, not names — same reason as _res_sg: subnet ids and AZs describe another workload's network
    # layout in a shared VPC, and the report promises out-of-scope identifiers are counted.
    others = [x for x in subs if x.get("SubnetId") not in mine]
    rt = (d["raw"].get("routetables") or {}).get("RouteTables") or []

    def nm(s):
        return (f'{s.get("SubnetId","?")} ({s.get("AvailabilityZone","?")}, '
                f'{s.get("AvailableIpAddressCount","?")} free IPs)')
    p, f = _split(scoped, lambda s: ok(s, rt), nm)
    return {"pass": p, "fail": f, "context": ([f"{len(others)} subnet(s) in the VPC are not registered to this cluster "
                         f"and were excluded (identifiers omitted)"] if others else []),
            "context_label": "scope of this check"}


def _subnet_private(s, rts):
    """A subnet is private when its route table has no route to an internet gateway.

    THE MAIN-TABLE FALLBACK IS THE WHOLE POINT. AWS: "You can explicitly associate a subnet with a
    particular route table. Otherwise, the subnet is implicitly associated with the main route table."
    An implicitly-associated subnet returns an EMPTY per-subnet association list, so the earlier version
    of this function fell through its loop and returned True for every such subnet — which is why it
    disagreed with the scorer and got replaced by a MapPublicIpOnLaunch proxy. The proxy was the wrong
    fix: auto-assign-public-IP can be false while the subnet still routes 0.0.0.0/0 to an IGW.

    Unresolvable table -> NOT private. Never claim private without evidence.
    Twin of the m3 lens-15 scorer in references/reliability.md — change both together."""
    sid = s.get("SubnetId")
    table = next((rt for rt in rts
                  if any(a.get("SubnetId") == sid for a in rt.get("Associations") or [])), None)
    if table is None:
        table = next((rt for rt in rts
                      if any(a.get("Main") is True for a in rt.get("Associations") or [])), None)
    if table is None:
        return False
    return not any((r.get("GatewayId") or "").startswith("igw-")
                   for r in table.get("Routes") or [])


def _res_nodes(d, ok, extra=None):
    def nm(n):
        lb = _labels(n)
        bits = [lb.get("node.kubernetes.io/instance-type", "?"),
                lb.get("topology.kubernetes.io/zone", "?")]
        if extra:
            bits.append(extra(n))
        return f'{_nm(n)} ({", ".join(str(b) for b in bits if b)})'
    p, f = _split(d["nodes"], ok, nm)
    return {"pass": p, "fail": f}


def _res_pv(d):
    p, f = _split(_items(d, "pv"),
                  lambda v: (v.get("status") or {}).get("phase") not in ("Released", "Available"),
                  lambda v: f'{_nm(v)} ({(v.get("status") or {}).get("phase","?")})')
    return {"pass": p, "fail": f}


def _res_tags(d):
    tags = d["cluster"].get("tags") or {}
    classes = [("project", "project"), ("environment", "environment|^env$"),
               ("cost-centre", "cost|billing"), ("team", "team|owner")]
    p, f = [], []
    for label, pat in classes:
        hit = [k for k in tags if re.search(pat, k, re.I)]
        (p if hit else f).append(f'{label}: {", ".join(hit) if hit else "absent"}')
    return {"pass": p, "fail": f,
            "context": [f"{k}={v}" for k, v in sorted(tags.items())],
            "context_label": "all cluster tags collected"}


def _res_endpoints(d):
    have = [(v.get("ServiceName") or "") for v in
            ((d["raw"].get("vpcendpoints") or {}).get("VpcEndpoints") or [])]
    want = ["s3", "ecr.api", "ecr.dkr", "sts"]
    p = [w for w in want if any(s.endswith(w) for s in have)]
    return {"pass": p, "fail": [w for w in want if w not in p],
            "context": sorted(have),
            "context_label": "all VPC endpoints in the VPC"}


def _res_storageclasses(d, ok):
    # This provisioner set is CANONICAL and MUST stay character-identical to the jq form used by cost-9
    # (references/cost-optimization.md) and sec-25 (references/security/identity-access.md); EDIT ALL
    # THREE OR NONE. It is the extractor half of a cross-checked pair, so any drift between the two
    # halves is reported to the reader as a DISAGREEMENT rather than being silently wrong -- which is
    # exactly how the missing `ebs.csi.eks.amazonaws.com` was caught. All three names must remain:
    # `ebs.csi.aws.com` (self-managed EBS CSI driver), `ebs.csi.eks.amazonaws.com` (EKS Auto Mode) and
    # `kubernetes.io/aws-ebs` (in-tree legacy).
    #
    # cost-9 formerly used a loose `test("ebs|aws-ebs")`. It appeared to work on Auto Mode, but only
    # because the unanchored `ebs` matched `ebs.csi.eks.amazonaws.com` as a substring by accident -- and
    # it would have matched an unrelated `example.com/ebs-fake` just as readily. The accident is what
    # concealed the real defect: this list stayed strict, so on an Auto Mode cluster the check counted
    # 1/1 while the resource list said 0/0, and sec-25 -- which already used this strict regex -- went
    # `na` on a cluster whose only StorageClass was an encrypted one. Auto Mode has its own provisioner:
    # "EKS Auto Mode does not create a `StorageClass` for you. You must create a `StorageClass`
    # referencing `ebs.csi.eks.amazonaws.com` to use the storage capability of EKS Auto Mode"
    # (https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html).
    scs = [s for s in _items(d, "storageclasses")
           if re.search(r"ebs\.csi\.aws\.com|ebs\.csi\.eks\.amazonaws\.com|kubernetes\.io/aws-ebs",
                        s.get("provisioner") or "")]
    others = [f'{_nm(s)} ({s.get("provisioner","?")})'
              for s in _items(d, "storageclasses") if s not in scs]
    p, f = _split(scs, ok,
                  lambda s: f'{_nm(s)} (type={(s.get("parameters") or {}).get("type","?")}, '
                            f'encrypted={(s.get("parameters") or {}).get("encrypted","unset")})')
    return {"pass": p, "fail": f, "context": sorted(others),
            # Named by the mechanism, and this one earns its reason: sec-25 reads `parameters.encrypted`
            # and cost-9 reads `parameters.type`, both EBS-CSI parameters, so a non-EBS provisioner has
            # no field for either question to be about. That is why it says WHY rather than "correctly".
            "context_label": "non-EBS StorageClasses, excluded by provisioner — the EBS parameter "
                             "this check reads does not exist on them"}


def _res_ns_label(d, prefix):
    # No owner annotation here, unlike _res_deploy: a Namespace carries no owner signal to annotate
    # with — `kubernetes.io/metadata.name` is set by the API server on every namespace and says nothing
    # about who created it — so the heading discloses the mechanism and claims nothing further. Guessing
    # from the name alone would just restate the rule as if it were evidence.
    ns = [n for n in _items(d, "namespaces") if not SYS_NS.match(_nm(n))]
    p, f = _split(ns, lambda n: any(k.startswith(prefix) for k in _labels(n)), _nm)
    return {"pass": p, "fail": f,
            "context": sorted(_nm(n) for n in _items(d, "namespaces") if SYS_NS.match(_nm(n))),
            "context_label": "namespaces excluded by the kube-*/amazon-* name prefix "
                             "(may include namespaces you created)"}


def _res_ns_has(d, other_file, key="namespace"):
    # The denominator is EVERY namespace whose name does not match ^(kube-|amazon-), `default`
    # included — the same `select(.metadata.name|test("^(kube-|amazon-)")|not)` the sec-4, cost-1 and
    # cost-2 scorers use. This used to drop `default` for sec-4 on the belief that its scorer excluded
    # it too; it does not, and the agreement check caught the extractor at 2/3 against the scorer's
    # 3/4. `default` is a workload namespace an operator can put a NetworkPolicy in, so excluding it
    # would also have understated the gap this question exists to find.
    ns = [_nm(n) for n in _items(d, "namespaces") if not SYS_NS.match(_nm(n))]
    covered = {(i.get("metadata") or {}).get(key) for i in _items(d, other_file)}
    return {"pass": sorted(n for n in ns if n in covered),
            "fail": sorted(n for n in ns if n not in covered)}


def _res_pdb_coverage(d):
    """rel-2: match PDB selectors against each Deployment's pod-template labels.

    Denominator is DEPLOYMENTS, not namespaces — a namespace-level check read 0/4 where the scorer
    said 0/8. This question has a history of exactly that mistake: it once compared PDB *cardinality*
    to Deployment count, passing a cluster whose single PDB selected something the Deployment did not,
    so the shape of the comparison matters more here than anywhere.
    """
    pdbs = _items(d, "pdb")
    p, f = [], []
    for dep in _workload(_items(d, "deployments")):
        lb = (((dep.get("spec") or {}).get("template") or {}).get("metadata") or {}).get("labels") or {}
        ns = (dep.get("metadata") or {}).get("namespace")
        hit = None
        for pdb in pdbs:
            if (pdb.get("metadata") or {}).get("namespace") != ns:
                continue
            sel = ((pdb.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
            if sel and all(lb.get(k) == v for k, v in sel.items()):
                hit = _nm(pdb)
                break
        (p if hit else f).append(f"{_qn(dep)}" + (f"  <- {hit}" if hit else ""))
    return {"pass": sorted(p), "fail": sorted(f),
            "context": sorted(_qn(x) for x in pdbs),
            "context_label": "all PodDisruptionBudget objects in the cluster"}


# Self-declared AWS-owner labels, tried in this order. Used ONLY to annotate an excluded list, NEVER
# to decide what is scored: the denominator stays `_workload()`'s namespace-prefix rule, because moving
# an object into or out of it would move scores.
AWS_OWNER_LABELS = (("eks.amazonaws.com/component", None),
                    ("addonmanager.kubernetes.io/mode", None),
                    ("app.kubernetes.io/managed-by", re.compile(r"^(eks|amazon|aws)", re.I)),
                    ("k8s-app", None))


def _aws_owner_signal(i):
    """The AWS-owner label an object sets on ITSELF, or "" when it sets none.

    Deliberately a weak signal, and said to be one in the report: it reports what the object declares,
    not who installed it. The case that forced it to exist is `kube-system/…karpenterhelm…`, which
    declares `app.kubernetes.io/managed-by: Helm` under a name generated from the operator's own CDK
    construct ids and runs `public.ecr.aws/karpenter/controller` — an AWS-PUBLISHED image the OPERATOR
    installed. Registry is therefore NOT a signal here; that one would have certified it as AWS's.
    An operator-installed component in a `kube-*` namespace reads as "no AWS owner label", which is
    the disclosure an excluded list owes its reader.
    """
    lb = _labels(i)
    for key, pat in AWS_OWNER_LABELS:
        v = str(lb.get(key) or "")
        if v and (pat is None or pat.match(v)):
            return f"{key}={v}"
    return ""


def _res_deploy(d, ok):
    """Denominator is `_workload()` — Deployments OUTSIDE `kube-*`/`amazon-*`. Unchanged, deliberately.

    The excluded list used to be headed as AWS-installed Deployments, excluded rightly, and none of the
    operator's business to configure. The rule is a namespace-NAME prefix and nothing more, so that
    heading certified the operator's own Karpenter controller — `kube-system/…karpenterhelm…`, installed
    from their own CDK — as somebody else's, and with it every PDB, anti-affinity and topology-spread
    question that would have found it. Both halves were true and the conjunction was false. It now states
    the mechanism, and each entry carries the owner label it declares, or the fact that it declares
    none. Disclosure only: no object changed sides, so no score moved.
    """
    p, f = _split(_workload(_items(d, "deployments")), ok)
    return {"pass": p, "fail": f,
            "context": sorted(
                f"{_qn(i)}  <- {_aws_owner_signal(i) or 'no AWS owner label (may be yours)'}"
                for i in _items(d, "deployments")
                if SYS_NS.match(((i.get("metadata") or {}).get("namespace") or ""))),
            "context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                             "(may include components you installed)"}


def _is_windows_pod(pod):
    """Windows pods are excluded from `podsec-5` — and from nothing else.

    Mirrors the same two signals that scorer uses: the `spec.os.name` field (Kubernetes 1.25+) and the
    `kubernetes.io/os` nodeSelector, which is how a Windows workload is actually scheduled.

    ONLY podsec-5. `securityContext.capabilities` is rejected by the API server on a pod declaring
    `spec.os.name: windows` and is inert on a Windows node either way, so `drop: [ALL]` is unsettable
    there and counting a Windows container as one that failed to set it reports a fact about Kubernetes
    as a finding about the cluster.

    NOT podsec-1. `runAsNonRoot` is admissible on Windows pods, required by PSS Restricted on them, and
    enforced by the kubelet (`security_context_windows.go`, `windowsRootUserName =
    "ContainerAdministrator"`). Excluding Windows there produced an implied pass on exactly the cluster
    shape SKILL.md calls a genuine gap — see the comment above `m podsec-1` in
    references/security/identity-access.md, and do not widen this helper back to it.
    NOT podsec-2 or podsec-4 either — a Windows container legitimately passes both.
    """
    spec = pod.get("spec") or {}
    return ((spec.get("os") or {}).get("name") == "windows"
            or (spec.get("nodeSelector") or {}).get("kubernetes.io/os") == "windows")


def _linux_workload(pods):
    """Workload pods minus Windows ones, with the excluded count, for podsec-5."""
    wl = _workload(pods)
    keep = [p for p in wl if not _is_windows_pod(p)]
    return keep, len(wl) - len(keep)


def _win_run_as_user(c, ps):
    """Effective `windowsOptions.runAsUserName` for a container, lower-cased ("" when unset).

    Container level overrides pod level, which is what the scorer's
    `.sc.windowsOptions.runAsUserName // .ps.windowsOptions.runAsUserName` does, and the comparison is
    case-insensitive because the kubelet's Windows `verifyRunAsNonRoot` compares with
    `strings.EqualFold`. `runAsNonRoot: true` is necessary but not sufficient on Windows: the check
    passes vacuously on an image with no USER directive, so a container that names
    ContainerAdministrator explicitly must still fail podsec-1. Twin of the `m podsec-1` scorer in
    references/security/identity-access.md — change both together.
    """
    for sc in ((c or {}).get("securityContext") or {}, ps or {}):
        u = (sc.get("windowsOptions") or {}).get("runAsUserName")
        if u is not None:
            return str(u).lower()
    return ""


def _win_note(n, why):
    return [f"{n} Windows pod(s) excluded — {why}"] if n else []


def _res_containers(d, ok, linux_only=False, why=""):
    pods, nwin = (_linux_workload(d["pods"]) if linux_only
                  else (_workload(d["pods"]), 0))
    p, f = [], []
    for pod, c in _containers(pods):
        nm = f'{_qn(pod)} / {c.get("name","?")}'
        (p if ok(c) else f).append(nm)
    out = {"pass": sorted(p), "fail": sorted(f)}
    if nwin:
        out["context"] = _win_note(nwin, why)
        out["context_label"] = "scope of this check"
    return out


def _res_pods(d, ok):
    p, f = _split(_workload(d["pods"]), ok)
    return {"pass": p, "fail": f}


def _res_containers_ctx(d, ok):
    """Container-level check where the POD securityContext is inherited (podsec-1's shape).

    No `linux_only` knob, deliberately: both callers (podsec-1, sec-15) count EVERY workload
    container, Windows included, because both read `runAsNonRoot`, which Windows pods can and must
    set. The knob existed only for podsec-1's since-removed Windows exclusion, and leaving it here
    would be an invitation to switch that exclusion back on. podsec-5's exclusion lives on
    `_res_containers`, where it belongs.
    """
    p, f = [], []
    for pod in _workload(d["pods"]):
        ps = (pod.get("spec") or {}).get("securityContext") or {}
        for c in (pod.get("spec") or {}).get("containers") or []:
            nm = f'{_qn(pod)} / {c.get("name","?")}'
            (p if ok(c, ps) else f).append(nm)
    return {"pass": sorted(p), "fail": sorted(f)}


def _res_imdsv2(d):
    """lens-11 reads EC2 INSTANCES, not Kubernetes nodes — Fargate has neither, which is why the
    scorer returns 0/0 there while a node-based extractor claimed 14/14."""
    inst = [i for r in ((d["raw"].get("instances") or {}).get("Reservations") or [])
            for i in (r.get("Instances") or [])]
    p, f = _split(inst,
                  lambda i: (i.get("MetadataOptions") or {}).get("HttpTokens") == "required",
                  lambda i: f'{i.get("InstanceId","?")} ({i.get("InstanceType","?")}, '
                            f'HttpTokens='
                            f'{(i.get("MetadataOptions") or {}).get("HttpTokens","unset")})')
    return {"pass": p, "fail": f}


def _res_identity(d):
    pia = [f'{a.get("namespace","?")}/{a.get("serviceAccount","?")} -> '
           f'{(a.get("roleArn") or "?").split("/")[-1]}' for a in d["podidentity"]]
    irsa = [f'{_qn(s)} -> '
            f'{(_labels(s) and "" ) or ((s.get("metadata") or {}).get("annotations") or {}).get("eks.amazonaws.com/role-arn","").split("/")[-1]}'
            for s in _items(d, "serviceaccounts")
            if ((s.get("metadata") or {}).get("annotations") or {}).get("eks.amazonaws.com/role-arn")]
    prov = [a.get("Arn", "?").split("oidc-provider/")[-1] for a in d["oidcproviders"]]
    issuer = ((d["cluster"].get("identity") or {}).get("oidc") or {}).get("issuer", "")
    return {"pass": sorted(pia) + sorted(irsa), "fail": [],
            "context": [f"cluster issuer: {issuer.replace('https://','') or 'absent'}"]
                       + [f"IAM OIDC provider: {x}" for x in sorted(prov)],
            "context_label": "identity plumbing"}


# ---- shapes B and C: existence checks and cluster-field checks -------------
# These have NO count in the scorer's output, so `resource_agreement()` cannot cross-check them.
# They still name the object or field that decided the verdict, which is the part a reader can
# check by eye — and the panel says plainly that no total was available to verify against.
def _res_match(d, f, pattern, label="Matched the detection", nm=_qn):
    """Name-match existence: which objects matched the regex, plus the regex itself."""
    hits = [nm(i) for i in _items(d, f) if re.search(pattern, _nm(i))]
    return {"kind": "existence", "pass": sorted(hits), "fail": [],
            "pass_label": label,
            "context": [pattern],
            "context_label": "pattern the names were matched against"}


def _res_field(d, fields, label="Cluster settings read"):
    """Cluster-field check: print each field path and its literal value."""
    out = []
    for path in fields:
        cur, ok = d["cluster"], True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur, ok = None, False
                break
        out.append(f"{path} = {json.dumps(cur) if ok else 'not set'}")
    return {"kind": "field", "pass": out, "fail": [], "pass_label": label}


def _res_cost3(d):
    keda = [_qn(i) for i in _items(d, "deployments") if re.search("keda", _nm(i))]
    hpas = [_qn(i) for i in _items(d, "hpa")]
    return {"kind": "existence",
            "pass": sorted(keda) + [f"HPA: {h}" for h in sorted(hpas)], "fail": [],
            "pass_label": "Both conditions matched (KEDA present, and at least one autoscaler)",
            "context": ["Deployment name matches 'keda'", "hpa.json is non-empty"],
            "context_label": "the two conditions this check requires"}


def _res_ope7(d):
    ds = [_qn(i) for i in _items(d, "daemonsets") if re.search("node-exporter", _nm(i))]
    ec2 = [_nm(n) for n in d["nodes"]
           if _labels(n).get("eks.amazonaws.com/compute-type") != "fargate"]
    return {"kind": "existence", "pass": sorted(ds), "fail": [],
            "pass_label": "Matched the detection",
            "context": ec2, "context_label": "EC2 nodes the DaemonSet could run on "
                                             "(the check is n/a with none)"}


def _res_ope15(d):
    """ope-15 scores node COVERAGE, so the denominator is EC2 NODES — every node whose
    `eks.amazonaws.com/compute-type` label is not "fargate" — and a node passes when it carries a
    non-empty `eks.amazonaws.com/nodegroup` label.

    Listing the managed node GROUP names instead read 1/1 against the scorer's 2/3, and did so in the
    most misleading direction available: a self-managed or Karpenter-provisioned node belongs to no
    group, so it never appears in `nodegroups.json` at all and the group list is 1/1 precisely when
    coverage is worst. Twin of the m3 ope-15 scorer in references/operational-excellence.md — change
    both together.

    EKS AUTO MODE SHORT-CIRCUITS THE LIST. The scorer answers `all` there — AWS owns the node
    lifecycle — while Auto Mode nodes carry no `eks.amazonaws.com/nodegroup` label, so the ratio path
    below would print every node under "In no managed node group" beneath a green Pass. Same shape as
    `_res_rel4`: state the cluster field that decided it, and keep the nodes as context rather than as
    a verdict about them."""
    if _automode_all_nodes(d):
        return {"kind": "field",
                "pass": ["computeConfig.enabled = true (EKS Auto Mode launches, patches, upgrades "
                         "and replaces these nodes; a managed node group is not the mechanism)"],
                "fail": [],
                "pass_label": "Cluster setting read",
                "context": sorted(_nm(n) for n in d["nodes"])
                           + sorted(f"managed node group alongside Auto Mode: {g}"
                                    for g in (d["raw"].get("nodegroups") or {}).get("nodegroups") or []),
                "context_label": "nodes AWS is managing on this cluster (not a pass/fail set)"}
    ec2 = [n for n in d["nodes"]
           if _labels(n).get("eks.amazonaws.com/compute-type") != "fargate"]

    # A node is managed if it is in a node group OR it is an Auto Mode node -- the UNION, matching the
    # scorer. On a HYBRID cluster (Auto Mode enabled, some nodes still from a node group) the
    # nodegroup-label test alone listed the Auto Mode node under "In no managed node group" beneath the
    # scorer's `all`: 2 of 3 shown passing under a green Pass that counted 3 of 3. The cross-check could
    # not see it, because the scorer's hybrid detail spells its counts in prose ("3 of 3") rather than as
    # `n/m`, so `resource_agreement` had no ratio to compare -- the same blind spot that hid the missing
    # provenance for `sec-4`. An Auto Mode node has no `eks.amazonaws.com/nodegroup` label by
    # construction, so this is not an extra credit, it is the other half of the same denominator.
    def _managed(n):
        lb = _labels(n)
        return ((lb.get("eks.amazonaws.com/nodegroup") or "") != ""
                or (lb.get("eks.amazonaws.com/compute-type") or "") == "auto")

    def _how(n):
        lb = _labels(n)
        if (lb.get("eks.amazonaws.com/compute-type") or "") == "auto":
            return f"{_nm(n)} (EKS Auto Mode node)"
        return f'{_nm(n)} (nodegroup={lb.get("eks.amazonaws.com/nodegroup") or "none"})'

    p, f = _split(ec2, _managed, _how)
    return {"pass": p, "fail": f,
            "pass_label": "Lifecycle managed by AWS (managed node group or EKS Auto Mode)",
            "fail_label": "Lifecycle not managed by AWS (self-managed or Karpenter-provisioned)",
            "context": sorted((d["raw"].get("nodegroups") or {}).get("nodegroups") or []),
            "context_label": "managed node groups the cluster has (not the denominator)"}


def _res_sec33(d):
    addons = [f"add-on: {a}" for a in ((d["raw"].get("addons") or {}).get("addons") or [])
              if "guardduty" in a]
    pods = [f"pod: {_qn(p)}" for p in d["pods"]
            if re.search("guardduty|falco|sysdig|tetragon", _nm(p))
            or "guardduty" in ((p.get("metadata") or {}).get("namespace") or "")]
    return {"kind": "existence", "pass": sorted(addons) + sorted(pods), "fail": [],
            "pass_label": "Matched the detection (either branch satisfies it)",
            "context": ["GuardDuty add-on installed",
                        "or a pod named guardduty|falco|sysdig|tetragon"],
            "context_label": "the two branches this check accepts"}


def _res_rel4(d):
    # THE ONE EXTRACTOR THAT DELIBERATELY KEEPS THE CLUSTER FLAG, not `_automode_all_nodes`.
    #
    # `rel-4` asks whether the cluster has node autoscaling at all. That is a CLUSTER property: with
    # `computeConfig.enabled`, Auto Mode provisions nodes for the cluster, and it keeps doing so on a
    # hybrid cluster where some nodes happen to have come from a node group. Contrast `ope-16`,
    # `lens-7`, `lens-1` and `ope-15`, which ask whether a capability reached each NODE -- there a
    # non-Auto node is a real gap, so those gate on the node population.
    #
    # Re-gating this one would also be a no-op today: on the hybrid fixture the fall-through returns
    # `all` anyway, because the Auto Mode node carries `karpenter.sh/nodepool`. Left as-is on the
    # reasoning, not on the arithmetic, so a future reader does not "align" it and quietly change what
    # the question means.
    if _automode_compute(d):
        return {"kind": "field",
                "pass": ["computeConfig.enabled = true (EKS Auto Mode provisions nodes; "
                         "no in-cluster autoscaler is expected)"],
                "fail": [], "pass_label": "Cluster setting read"}
    return _res_match(d, "deployments", "karpenter|cluster-autoscaler")


def _yaml_top_items(txt):
    """Split a YAML sequence into its TOP-LEVEL `- ` items, by indentation.

    Splitting on every `- ` line instead cuts each mapping apart at its own nested `groups:` list, so
    the fragment holding `system:masters` is the bare line `    - system:masters` with no ARN in it,
    and every entry falls through to the "could not be attributed" branch. Indentation is the only
    thing that distinguishes a new entry from a member of the entry's group list here.
    """
    lines = txt.split("\n")
    indents = [len(ln) - len(ln.lstrip()) for ln in lines if re.match(r"\s*-\s", ln)]
    if not indents:
        return [txt]
    top, out, cur = min(indents), [], []
    for ln in lines:
        if cur and re.match(r"\s*-\s", ln) and (len(ln) - len(ln.lstrip())) == top:
            out.append("\n".join(cur))
            cur = []
        cur.append(ln)
    if cur:
        out.append("\n".join(cur))
    return out


def _aws_auth_masters(d):
    """IAM principals that `kube-system/aws-auth` maps into `system:masters`.

    THIS IS NOT A YAML PARSE. `data.mapRoles` / `data.mapUsers` are YAML documents carried as JSON
    strings; the scorer that produced the verdict (`m2 rbac-1`) can only run a substring test over
    them, because jq cannot parse YAML. This splits the same text at YAML list-item boundaries so the
    report can name the principal rather than just assert one exists — and falls back to naming the
    block when the split attributes nothing, because a `fail` whose list shows only built-in subjects
    is exactly the confusion this list is here to prevent.

    Attribution only. The scorer decides; if these two ever disagree the scorer wins, and neither the
    count nor the attribution feeds `resource_agreement()` — rbac-1's detail carries no `N/M`.
    """
    aa = d["raw"].get("awsauth")
    data = (aa or {}).get("data") if isinstance(aa, dict) else None
    out = []
    for key in ("mapRoles", "mapUsers"):
        txt = (data or {}).get(key) if isinstance(data, dict) else None
        if not isinstance(txt, str) or "system:masters" not in txt:
            continue
        named = []
        for chunk in _yaml_top_items(txt):
            if "system:masters" not in chunk:
                continue
            arn = re.search(r"arn:[^\s\"',]+", chunk)
            usr = re.search(r"username:\s*(\S+)", chunk)
            who = arn.group(0) if arn else (usr.group(1) if usr else None)
            if who:
                named.append(f"aws-auth data.{key}: {who}  ->  system:masters "
                             f"(cluster-admin via IAM)")
        out += named or [f"aws-auth data.{key} contains a system:masters group entry; the principal "
                         f"could not be attributed by text alone — read the ConfigMap"]
    return out


def _res_rbac1(d):
    """rbac-1 has TWO paths to cluster-admin and the list must show both.

    `system:masters` is a built-in group: the API server grants it cluster-admin with no
    ClusterRoleBinding, so it is correctly filtered out of the binding subjects here — and that is
    precisely why an aws-auth entry mapping an IAM role into it is invisible to the RBAC half. Twin of
    the `m2 rbac-1` scorer in references/security/identity-access.md — change both together.
    """
    binds = [b for b in _items(d, "clusterrolebindings")
             if (b.get("roleRef") or {}).get("name") == "cluster-admin"]
    p, f = [], []
    for b in binds:
        for s in b.get("subjects") or []:
            nm = s.get("name", "?")
            entry = f'ClusterRoleBinding {_nm(b)} -> {s.get("kind","?")} {nm}'
            builtin = re.match(r"^(system:|eks:)", nm) or nm == "system:masters"
            (p if builtin else f).append(entry)
    return {"pass": sorted(p), "fail": sorted(f) + _aws_auth_masters(d),
            "pass_label": "Built-in subjects (expected)",
            "fail_label": "Paths to cluster-admin that are not built-in — binding subjects, and "
                          "aws-auth IAM mappings into system:masters (findings)"}


def _res_logtypes_audit(d):
    on = set()
    for grp in (d["cluster"].get("logging") or {}).get("clusterLogging") or []:
        if grp.get("enabled"):
            on |= set(grp.get("types") or [])
    return {"kind": "field",
            "pass": [f"{t}{'  <- required by this check' if t == 'audit' else ''}"
                     for t in sorted(on)] or ["no log types enabled"],
            "fail": [], "pass_label": "Control-plane log types enabled"}


def _res_net4(d):
    """net-4 was RESCOPED from "are control-plane and node SGs separate" to "has the cluster SG's
    default allow-all egress been narrowed". This extractor kept implementing the old premise, so the
    panel listed the control-plane SGs and explained that the check passes when the cluster SG is
    absent from them — while the verdict line directly above it read "cluster SG ... still allows ALL
    egress to 0.0.0.0/0" and the jq printed below it tested IpPermissionsEgress. Three parts of one
    panel described three different checks. Twin of the net-4 scorer in security/identity-access.md."""
    v = d["cluster"].get("resourcesVpcConfig") or {}
    csg = v.get("clusterSecurityGroupId") or ""
    groups = [g for g in ((d["raw"].get("sg") or {}).get("SecurityGroups") or [])
              if g.get("GroupId") == csg]
    if not csg:
        return {"kind": "field", "pass": [], "fail": [],
                "context": ["no clusterSecurityGroupId on this cluster"],
                "context_label": "Cluster security group"}
    if not groups:
        return {"kind": "field", "pass": [], "fail": [],
                "context": [f"{csg} (not present in the collected security groups)"],
                "context_label": "Cluster security group"}
    openv4, narrowed = [], []
    for g in groups:
        for perm in g.get("IpPermissionsEgress") or []:
            dests = [r.get("CidrIp") for r in (perm.get("IpRanges") or [])]
            proto = perm.get("IpProtocol")
            desc = f"{g['GroupId']} egress {'ALL protocols' if proto == '-1' else proto} -> " \
                   f"{', '.join(d for d in dests if d) or 'security group / prefix list'}"
            if proto == "-1" and "0.0.0.0/0" in dests:
                openv4.append(desc + "   <- the default rule this check looks for")
            else:
                narrowed.append(desc)
    return {"kind": "field", "pass": narrowed, "fail": openv4,
            "pass_label": "Egress rules on the cluster security group",
            "fail_label": "Counted as failing"}


def _res_sec18(d):
    issuer = ((d["cluster"].get("identity") or {}).get("oidc") or {}).get("issuer", "")
    provs = [a.get("Arn", "?") for a in d["oidcproviders"]]
    irsa = [_qn(s) for s in _items(d, "serviceaccounts")
            if ((s.get("metadata") or {}).get("annotations") or {})
            .get("eks.amazonaws.com/role-arn")]
    stripped = issuer.replace("https://", "")
    match = [a for a in provs if a.endswith("oidc-provider/" + stripped)]
    return {"kind": "field",
            "pass": ([f"IAM OIDC provider: {a}" for a in match]
                     + [f"IRSA ServiceAccount: {s}" for s in sorted(irsa)]),
            "fail": [], "pass_label": "Registered provider and the accounts that depend on it",
            # list-open-id-connect-providers is ACCOUNT-scoped, so the non-matching entries are other
            # clusters' providers -- full ARNs, account id included, for workloads outside this
            # review. What the reader must be able to check is that a provider matching THIS cluster's
            # issuer was found, and the count establishes that the others were considered and rejected.
            "context": ([f"cluster issuer: {stripped or 'absent'}"]
                        + ([f"{len([a for a in provs if a not in match])} other IAM OIDC provider(s) "
                            f"exist in this account and do not match this issuer (identifiers omitted "
                            f"\u2014 they belong to other clusters)"]
                           if [a for a in provs if a not in match] else [])),
            "context_label": "matched against"}


# id -> extractor. Absent id simply means no resource list is shown for that question.
RESOURCES = {
    # ---- Operational Excellence
    "ope-16": _res_addons,
    "lens-7": _res_lens7,
    "ope-11": _res_trails,
    "ope-6": _res_logtypes,
    "ope-15": _res_ope15,
    "ope-17": lambda d: {"pass": [], "fail": [],
                         "context": sorted(_qn(i) for i in _items(d, "jobs")),
                         "context_label": "Jobs collected"},
    "ope-18": lambda d: {"pass": [], "fail": [],
                         "context": sorted(_qn(i) for i in _items(d, "cronjobs")),
                         "context_label": "CronJobs collected"},
    # ---- Security
    "sec-6": _res_identity,
    "sec-11": lambda d: _res_ns_label(d, "pod-security.kubernetes.io/"),
    "sec-4": lambda d: _res_ns_has(d, "networkpolicies"),
    "sec-9": lambda d: (lambda roles: {
        "pass": sorted(_nm(r) for r in roles
                       if not any(("*" in (rr.get("resources") or []))
                                  or ("*" in (rr.get("verbs") or []))
                                  for rr in r.get("rules") or [])),
        "fail": sorted(_nm(r) for r in roles
                       if any(("*" in (rr.get("resources") or []))
                              or ("*" in (rr.get("verbs") or []))
                              for rr in r.get("rules") or [])),
        "context": ["built-in system:/eks: roles excluded"],
        "context_label": "scope"})(
        [r for r in _items(d, "clusterroles")
         if not re.match(r"^(system:|eks:|cluster-admin$)", _nm(r))]),
    "sec-21": _res_volumes,
    "sec-25": lambda d: _res_storageclasses(
        d, lambda s: str((s.get("parameters") or {}).get("encrypted", "")).lower() == "true"),
    "sec-30": lambda d: _res_sg(d, _sg_no_ssh),
    "net-2": lambda d: _res_sg(d, _sg_clean),
    "net-1": lambda d: _res_subnets(
        d, lambda s, rt: (s.get("AvailableIpAddressCount") or 0) >= 100, "IP capacity"),
    "lens-15": lambda d: _res_subnets(d, _subnet_private, "private routing"),
    "lens-11": _res_imdsv2,
    # Denominator is EVERY workload ServiceAccount, not only the one literally named `default`, and
    # the namespace exclusion is ^(kube-|amazon-) rather than ^kube- alone. Filtering to the `default`
    # SA read 0/5 against the scorer's 1/14; the scorer's own comment rejects that premise ("Real
    # workloads use named SAs, so the old check was blind to the normal case").
    "rbac-4": lambda d: (lambda sas: {
        "pass": sorted(_qn(s) for s in sas if s.get("automountServiceAccountToken") is False),
        "fail": sorted(_qn(s) for s in sas if s.get("automountServiceAccountToken") is not False)})(
        _workload(_items(d, "serviceaccounts"))),
    # Denominator is CONTAINERS, with the pod-level securityContext inherited — a pod-level
    # extractor read 11/15 against the scorer's 15/19. WINDOWS CONTAINERS ARE COUNTED: `runAsNonRoot`
    # is admissible, PSS-Restricted-required and kubelet-enforced on Windows pods, and a container
    # that names ContainerAdministrator fails even with `runAsNonRoot: true`.
    "podsec-1": lambda d: _res_containers_ctx(
        d, lambda c, ps: ((c.get("securityContext") or {}).get("runAsNonRoot") is True
                          or (ps or {}).get("runAsNonRoot") is True)
        and _win_run_as_user(c, ps) != "containeradministrator"),
    "podsec-2": lambda d: _res_containers(
        d, lambda c: not ((c.get("securityContext") or {}).get("privileged"))),
    "podsec-3": lambda d: _res_pods(
        d, lambda p: not any(v.get("hostPath") for v in (p.get("spec") or {}).get("volumes") or [])),
    "podsec-5": lambda d: _res_containers(
        d, lambda c: "ALL" in (((c.get("securityContext") or {}).get("capabilities") or {})
                               .get("drop") or []),
        # Same wording as the scorer's own `na`/exclusion note, so one panel does not give two
        # different reasons for the same exclusion.
        linux_only=True, why="securityContext.capabilities is rejected by the API server on a "
                             "Windows pod, so drop ALL cannot be set there"),
    "sec-12": lambda d: _res_containers(
        d, lambda c: ":" in (c.get("image") or "") and "latest" not in (c.get("image") or "")),
    # ---- Reliability
    "rel-1": lambda d: {"pass": sorted({_labels(n).get("topology.kubernetes.io/zone", "?")
                                        for n in d["nodes"]}),
                        "fail": [],
                        "context": sorted({s.get("AvailabilityZone", "?") for s in
                                           ((d["raw"].get("subnets") or {}).get("Subnets") or [])}),
                        "context_label": "AZs the VPC has subnets in"},
    "rel-2": _res_pdb_coverage,
    "rel-5": lambda d: _res_deploy(d, lambda i: any(
        ((h.get("spec") or {}).get("scaleTargetRef") or {}).get("name") == _nm(i)
        for h in _items(d, "hpa"))),
    "rel-7": lambda d: _res_deploy(d, lambda i: ((i.get("spec") or {}).get("replicas") or 1) > 1),
    # podAntiAffinity specifically: any-affinity read 2/8 where the scorer said 0/8.
    "rel-8": lambda d: _res_deploy(
        d, lambda i: bool(((((i.get("spec") or {}).get("template") or {}).get("spec") or {})
                           .get("affinity") or {}).get("podAntiAffinity"))),
    "rel-9": lambda d: _res_deploy(
        d, lambda i: bool((((i.get("spec") or {}).get("template") or {}).get("spec") or {})
                          .get("topologySpreadConstraints"))),
    "rel-3": lambda d: _res_containers(
        d, lambda c: bool(((c.get("resources") or {}).get("limits") or {}))),
    "rel-6": lambda d: _res_containers(d, lambda c: bool(c.get("readinessProbe"))),
    "rel-11": lambda d: _split(_items(d, "pvc"),
                              lambda v: (v.get("status") or {}).get("phase") == "Bound")
                        and {"pass": _split(_items(d, "pvc"),
                                            lambda v: (v.get("status") or {}).get("phase") == "Bound")[0],
                             "fail": _split(_items(d, "pvc"),
                                            lambda v: (v.get("status") or {}).get("phase") == "Bound")[1]},
    "rel-18": lambda d: _res_deploy(
        d, lambda i: ((i.get("spec") or {}).get("strategy") or {}).get("type") in
        ("RollingUpdate", None)),
    "rel-22": lambda d: (lambda sts: {
        "pass": sorted(_qn(s) for s in sts if ((s.get("spec") or {}).get("replicas") or 1) > 1),
        "fail": sorted(_qn(s) for s in sts if ((s.get("spec") or {}).get("replicas") or 1) <= 1)})(
        _workload(_items(d, "statefulsets"))),
    "lens-14": lambda d: {"pass": sorted(n.get("NatGatewayId", "?") + " (" +
                                         n.get("SubnetId", "?") + ")" for n in
                                         ((d["raw"].get("nat") or {}).get("NatGateways") or [])),
                          "fail": [],
                          "context": sorted({_labels(n).get("topology.kubernetes.io/zone", "?")
                                             for n in d["nodes"]}),
                          "context_label": "AZs the nodes occupy"},
    # ---- Performance
    "perf-1": lambda d: _res_containers(
        d, lambda c: bool(((c.get("resources") or {}).get("requests") or {}).get("cpu"))
        and bool(((c.get("resources") or {}).get("requests") or {}).get("memory"))),
    "perf-3": lambda d: _res_nodes(
        d, lambda n: not re.match(
            r"^(a1|m[1-4]|t1|c1|c3|c4|r3|r4|i2|g3|p3)[a-z]*\.",
            _labels(n).get("node.kubernetes.io/instance-type", ""))),
    "perf-6": lambda d: {"pass": sorted({_labels(n).get("node.kubernetes.io/instance-type", "?")
                                         for n in d["nodes"]}), "fail": []},
    # Windows nodes are excluded, matching the scorer: this asks about the LINUX AMI families EKS
    # supports, and a Windows node is not an unsupported image — it is a family out of scope.
    "lens-6": lambda d: _res_nodes(
        {**d, "nodes": [n for n in d["nodes"]
                        if _labels(n).get("kubernetes.io/os") != "windows"]},
        lambda n: re.search(r"Bottlerocket|Amazon Linux 20[0-9][0-9]",
                            ((n.get("status") or {}).get("nodeInfo") or {}).get("osImage", "")),
        extra=lambda n: ((n.get("status") or {}).get("nodeInfo") or {}).get("osImage", "?")),
    "lens-5": lambda d: _res_pods(
        d, lambda p: bool(_labels(p).get("app.kubernetes.io/name"))),
    # ---- Cost
    "cost-1": lambda d: _res_ns_has(d, "resourcequotas"),
    "cost-2": lambda d: _res_ns_has(d, "limitranges"),
    "cost-6": _res_pv,
    "cost-7": _res_tags,
    "cost-8": _res_unattached,
    "cost-9": lambda d: _res_storageclasses(
        d, lambda s: (s.get("parameters") or {}).get("type") == "gp3"),
    # ---- the checks that previously showed nothing ----------------------------
    # Not stated as a count: the number drifted from 17 to 18 the moment one was added, and a
    # stale number in a comment is the same defect as a stale number in the report.
    # A. name-match existence: which object matched, and the pattern it matched against
    "ope-5": lambda d: _res_match(d, "deployments", "prometheus|grafana|cloudwatch"),
    "rel-13": lambda d: _res_match(d, "deployments", "prometheus|grafana|datadog|cloudwatch"),
    "rel-4": _res_rel4,
    "cost-3": _res_cost3,
    "ope-7": _res_ope7,
    "sec-33": _res_sec33,
    # B. cluster-field: the field path and its literal value, so the verdict is checkable
    "sec-1": lambda d: _res_field(d, ["resourcesVpcConfig.endpointPrivateAccess"]),
    "sec-2": lambda d: _res_field(d, ["resourcesVpcConfig.endpointPublicAccess",
                                      "resourcesVpcConfig.publicAccessCidrs"]),
    "sec-17": lambda d: _res_field(d, ["accessConfig.authenticationMode"]),
    "sec-26": _res_logtypes_audit,
    "net-4": _res_net4,
    "sec-18": _res_sec18,
    # C. ratio checks that simply had no extractor — these DO get the count cross-check
    "perf-4": lambda d: _res_deploy(
        d, lambda i: ((i.get("spec") or {}).get("strategy") or {}).get("type") in
        ("RollingUpdate", None)),
    # SPREADING, not any affinity — the same distinction rel-8 makes. A bare `affinity.nodeAffinity`
    # PINS placement instead of spreading it, so it must not pass: accepting any `affinity` read 2/8
    # where the scorer said 0/8 and would have credited a Deployment pinning every replica to one AZ.
    "perf-5": lambda d: _res_deploy(
        d, lambda i: bool((((i.get("spec") or {}).get("template") or {}).get("spec") or {})
                          .get("topologySpreadConstraints"))
        or bool(((((i.get("spec") or {}).get("template") or {}).get("spec") or {})
                 .get("affinity") or {}).get("podAntiAffinity"))),
    "rel-19": lambda d: (lambda ds: {
        "pass": sorted(_qn(i) for i in ds
                       if ((i.get("spec") or {}).get("updateStrategy") or {})
                       .get("type") == "RollingUpdate"),
        "fail": sorted(_qn(i) for i in ds
                       if ((i.get("spec") or {}).get("updateStrategy") or {})
                       .get("type") != "RollingUpdate")})(_items(d, "daemonsets")),
    "sec-15": lambda d: _res_containers_ctx(
        d, lambda c, ps: (c.get("securityContext") or {}).get("runAsNonRoot") is True
        or (c.get("securityContext") or {}).get("readOnlyRootFilesystem") is True
        or (c.get("securityContext") or {}).get("allowPrivilegeEscalation") is False
        or (ps or {}).get("runAsNonRoot") is True),
    "rbac-1": _res_rbac1,
    "lens-16": _res_endpoints,
}


def observed_resources(qid, data):
    """Run the extractor for `qid`, or None. Never raises: a broken extractor must not take the
    report down, it just shows no list (and the agreement gate will flag the absence)."""
    fn = RESOURCES.get(qid)
    if not fn:
        return None
    try:
        r = fn(data)
    except Exception:
        return None
    if not isinstance(r, dict):
        return None
    r.setdefault("pass", [])
    r.setdefault("fail", [])
    return r


def resource_agreement(r, res):
    """Compare an extractor's counts with the scorer's own `N/M` from the detail string.

    Returns (verdict, message). `verdict` is True (agree), False (DISAGREE — a real bug) or None
    (no ratio in the detail, so nothing to compare). The gate treats False as a failure: a resource
    list that contradicts the score is worse than no list at all.
    """
    if not res:
        return None, "no extractor"
    m = re.match(r"^(\d+)/(\d+)", r.get("detail", "") or "")
    if not m:
        return None, "this check answers yes/no rather than counting"
    n, tot = int(m.group(1)), int(m.group(2))
    gp, gt = len(res["pass"]), len(res["pass"]) + len(res["fail"])
    if gp == n and gt == tot:
        return True, f"{gp} items listed, and the check counted {gp} \u2014 they agree"
    return False, f"resource list says {gp}/{gt} but the check counted {n}/{tot}"


# Links in the reference prose. Deliberately narrow on every axis:
#   - `https://` only, and `[text](https://…)`. A rule that matched anything URL-shaped would turn an
#     ARN, an image reference such as `602401143452.dkr.ecr.us-east-1.amazonaws.com/eks/coredns:v1.11`
#     or a bare hostname in a resource name into a link.
#   - `)` and `]` terminate the match, and the match must END on a word/path character, so a URL
#     written parenthetically in prose — `(https://docs.aws.amazon.com/…/enable-kms.html).` — links
#     the URL and leaves the punctuation outside it.
#   - THE SUBSTITUTION RUNS AFTER e(). `"`, `'`, `<` and `>` cannot survive escaping, so none of them
#     can be in a matched URL, so nothing matched here can close the href attribute it is written
#     into or open a tag. That ordering is the security property, not a detail.
#   - no `target`: the report still issues no request when opened, and a link is inert until clicked.
#
# A THIRD case: `[cost-analysis.md](cost-analysis.md)` — a markdown link whose target is a path in
# THIS repo, not a URL. The old regex only recognised the `https://` form, so the `https://` branch
# never matched and the whole `[text](target)` fell through unrendered, appearing to the reader as
# literal bracket syntax — 2 to 6 times per report, since several cost and security questions cross-
# reference `cost-analysis.md` or `identity-access.md` this way. Rendering it as a live `<a href>`
# would be worse, not better: the target is a file in the skill's own `references/` tree, which a
# reader holding only the forwarded HTML report does not have, so the link would be dead on click.
# The fix drops the bracket/paren syntax and keeps the link TEXT as plain text — the reader still
# learns which reference document backs the claim, with nothing that looks clickable and isn't.
_LINK_RE = re.compile(r"\[([^\]<>]+)\]\((https://[^)\s<>\"']+)\)"
                      r"|\[([^\]<>]+)\]\((?!https://)[^)\s<>\"']+\)"
                      r"|(https://[^\s<>\"'`)\]]*[A-Za-z0-9/#=_-])")


def _link_sub(m):
    if m.group(2):
        return f'<a href="{m.group(2)}" rel="noopener noreferrer">{m.group(1)}</a>'
    if m.group(3) is not None:
        return m.group(3)                      # relative/repo-path link: text only, no dead <a href>
    return f'<a href="{m.group(4)}" rel="noopener noreferrer">{m.group(4)}</a>'


def _linkify(txt):
    """Linkify outside code spans only.

    A URL inside backticks is part of a command the reader is meant to select and copy —
    `kubectl apply -f https://raw.githubusercontent.com/…/node-problem-detector.yaml` appears in two
    remediations — and an <a> in the middle of a shell line makes it uncopyable. Fenced blocks never
    reach here at all; md_inline() emits those before any inline rule runs.
    """
    parts = re.split(r"(<code>.*?</code>)", txt, flags=re.S)
    return "".join(p if i % 2 else _LINK_RE.sub(_link_sub, p)
                   for i, p in enumerate(parts))


def md_inline(s):
    """Render the small markdown subset the reference remediation prose actually uses."""
    out, blocks = [], re.split(r"```(?:bash|yaml|json)?\n(.*?)```", s, flags=re.S)
    for i, chunk in enumerate(blocks):
        if i % 2:                                   # fenced code block
            out.append(f"<pre><code>{e(chunk.rstrip())}</code></pre>")
            continue
        txt = e(chunk)
        txt = re.sub(r"`([^`]+)`", r"<code>\1</code>", txt)
        txt = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", txt)
        txt = _linkify(txt)
        lines, in_ul = [], False
        for ln in txt.split("\n"):
            if re.match(r"^\s*[-*]\s+", ln):
                # A nested bullet ("  - sub-point") matches this too, and is deliberately handled the
                # SAME as a top-level one — this function has no nesting model, so it becomes a sibling
                # <li> rather than being silently folded into its parent's text. That is pre-existing
                # behaviour, unchanged here; only the ELSE branch below is new.
                if not in_ul:
                    lines.append("<ul class='plain'>")
                    in_ul = True
                item = re.sub(r"^\s*[-*]\s+", "", ln)   # kept out of the f-string: py3.9 rejects
                lines.append(f"<li>{item}</li>")        # a backslash inside an f-string expression
            elif (in_ul and lines and lines[-1].endswith("</li>")
                  and ln.strip() and ln[:1] in (" ", "\t")):
                # A wrapped bullet's continuation line: indented, non-blank, no "- "/"* " prefix, with
                # a list already open. The reference files hard-wrap remediation prose near 100
                # columns, so a bullet whose text runs long is the ORDINARY case, not an edge case —
                # treating this line as "the list just ended" (the old, only, behaviour) split
                # "- a bullet whose text wraps\n  onto a continuation line\n- second bullet" into a
                # one-item <ul>, a dangling sentence fragment at body level, and a second one-item
                # <ul> for whatever followed. Reproduced against sec-6's shipped remediation (High
                # severity) before that question's bullets were reflowed onto single lines as a
                # workaround; this is the durable fix, so the workaround stops being load-bearing.
                # A blank line, a fresh bullet, and a line starting at column 0 all still end the list
                # exactly as before — none of those can reach this branch.
                lines[-1] = lines[-1][:-len("</li>")] + " " + ln.strip() + "</li>"
            else:
                if in_ul:
                    lines.append("</ul>")
                    in_ul = False
                if ln.strip():
                    lines.append(ln)
        if in_ul:
            lines.append("</ul>")
        joined = "\n".join(lines)
        if joined.strip():
            out.append(joined)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Cloudscape stylesheet — token values transcribed from the design-tokens reference.
#
# Split three ways so a theme can be FORCED, not just offered to prefers-color-scheme:
#   TOKENS_SHARED  typography, spacing, radius — identical in both visual modes
#   TOKENS_LIGHT / TOKENS_DARK   the two colour sets Cloudscape documents
#   BASE           every selector, written against the token names only
# `--theme auto` (default) ships both and lets the OS choose; `dark`/`light` pin one, which is what
# you need when the report is emailed, attached to a ticket, or printed, since the viewer's OS
# setting is not yours to predict.
# ---------------------------------------------------------------------------
TOKENS_LIGHT = """
  /* Colors — Cloudscape design tokens, light mode */
  --color-background-layout-main:#ffffff;
  --color-background-container-content:#ffffff;
  --color-background-home-header:#0f141a;
  --color-background-layout-panel:#f9f9fa;
  --color-background-cell-shaded:#f6f6f9;
  --color-text-heading-default:#0f141a;
  --color-text-body-default:#0f141a;
  --color-text-body-secondary:#424650;
  --color-text-status-error:#db0000;
  --color-text-status-success:#00802f;
  --color-text-status-warning:#855900;
  --color-text-status-info:#006ce0;
  --color-text-status-inactive:#656871;
  --color-text-link-default:#006ce0;
  --color-text-inverted:#ffffff;
  --color-border-divider-default:#c6c6cd;
  --color-border-divider-secondary:#ebebf0;
  --color-background-status-error:#fff5f5;
  --color-background-status-success:#effff1;
  --color-background-status-warning:#fffef0;
  --color-background-status-info:#f0fbff;
  --color-border-status-error:#db0000;
  --color-border-status-success:#00802f;
  --color-border-status-warning:#855900;
  --color-border-status-info:#006ce0;
  --color-severity-critical:#870303;
  --color-severity-high:#ce3311;
  --color-severity-medium:#f89256;
  --color-severity-low:#f2cd54;
  --color-severity-neutral:#656871;
  --color-text-badge-severity:#f9f9fa;   /* on the dark red/critical chips */
  --color-background-badge-grey:#424650;
  --shadow-container:0 1px 8px 2px rgba(0,7,22,.12);
"""

TOKENS_SHARED = """
  /* Typography */
  --font-family-base:"Amazon Ember","Amazon Ember Display",Helvetica,Arial,sans-serif;
  --font-family-monospace:Monaco,Menlo,Consolas,"Courier Prime",Courier,"Courier New",monospace;
  --font-size-display-l:42px;   --line-height-display-l:48px;
  --font-size-heading-xl:24px;  --line-height-heading-xl:30px;
  --font-size-heading-l:20px;   --line-height-heading-l:24px;
  --font-size-heading-m:18px;   --line-height-heading-m:22px;
  --font-size-heading-s:16px;   --line-height-heading-s:20px;
  --font-size-body-m:14px;      --line-height-body-m:20px;
  --font-size-body-s:12px;      --line-height-body-s:16px;
  --font-weight-heavy:700; --font-weight-normal:400; --font-weight-lighter:300;

  /* Spacing + radius */
  --space-xxxs:2px; --space-xxs:4px; --space-xs:8px; --space-s:12px;
  --space-m:16px; --space-l:20px; --space-xl:24px; --space-xxl:32px; --space-xxxl:40px;
  --border-radius-container:16px; --border-radius-badge:4px; --border-radius-input:8px;
"""

TOKENS_DARK = """
    /* Colors — Cloudscape design tokens, dark mode */
    --color-background-layout-main:#0f141a;
    --color-background-container-content:#161d26;
    --color-background-layout-panel:#1b232d;
    --color-background-cell-shaded:#1b232d;
    --color-text-heading-default:#ebebf0;
    --color-text-body-default:#c6c6cd;
    --color-text-body-secondary:#c6c6cd;
    --color-text-status-error:#ff7a7a;
    --color-text-status-success:#2bb534;
    --color-text-status-warning:#fbd332;
    --color-text-status-info:#42b4ff;
    --color-text-status-inactive:#a4a4ad;
    --color-text-link-default:#42b4ff;
    --color-border-divider-default:#424650;
    --color-border-divider-secondary:#232b37;
    --color-background-status-error:#1f0000;
    --color-background-status-success:#001401;
    --color-background-status-warning:#191100;
    --color-background-status-info:#001129;
    --color-border-status-error:#ff7a7a;
    --color-border-status-success:#2bb534;
    --color-border-status-warning:#fbd332;
    --color-border-status-info:#42b4ff;
    /* Dark-theme severity chips are LIGHT reds, so light text on them fails WCAG AA: #f9f9fa on
       #fe6e73 measures 2.59:1 at 12px/700 where 4.5:1 is required, and it was reachable on every
       failing High row. The text inverts to near-black (6.78:1) rather than darkening the chip,
       which would have collided with the dark surface behind it. Critical is lifted from #d63f38 --
       which fails against BOTH text colours (4.31:1 light, 4.08:1 dark) -- to #e0554e, 4.91:1. */
    --color-severity-critical:#e0554e;
    --color-severity-high:#fe6e73;
    --color-text-badge-severity:#0f141a;
    --color-background-badge-grey:#656871;
    --shadow-container:0 1px 8px 2px rgba(0,7,22,.6);
"""

BASE = """
*,*::before,*::after{box-sizing:border-box}
body{
  margin:0;background:var(--color-background-layout-main);
  color:var(--color-text-body-default);
  font-family:var(--font-family-base);
  font-size:var(--font-size-body-m);line-height:var(--line-height-body-m);
  -webkit-font-smoothing:antialiased;
}
code,.mono,td.num{font-family:var(--font-family-monospace)}

/* --- Top navigation (Cloudscape home header surface) --- */
.top-nav{
  background:var(--color-background-home-header);color:#ffffff;
  padding:var(--space-s) var(--space-xl);
  display:flex;align-items:center;gap:var(--space-s);flex-wrap:wrap;
}
.top-nav .product{font-size:var(--font-size-heading-s);font-weight:var(--font-weight-heavy)}
.top-nav .sep{color:#8c8c94}
.top-nav .ctx{font-size:var(--font-size-body-s);color:#c6c6cd;font-family:var(--font-family-monospace)}

/* --- Theme toggle (top right) ---
   `hidden` in the markup and un-hidden by the inline script, so a viewer with JavaScript disabled
   or stripped (some mail clients, CSP-restricted wikis) never sees a dead control — the report just
   follows prefers-color-scheme, which needs no script at all. */
.theme-toggle{
  margin-left:auto;display:inline-flex;align-items:center;gap:var(--space-xxs);
  background:transparent;color:#ebebf0;cursor:pointer;
  border:1px solid #424650;border-radius:var(--border-radius-input);
  padding:var(--space-xxs) var(--space-xs);
  font-family:inherit;font-size:var(--font-size-body-s);font-weight:var(--font-weight-heavy);
}
.theme-toggle:hover{background:#232b37;border-color:#656871}
.theme-toggle:focus-visible{outline:2px solid #42b4ff;outline-offset:2px}
.theme-toggle svg{width:14px;height:14px;flex:none}
.theme-toggle[hidden]{display:none}
/* Show the icon for the mode you will GET, not the one you are in. */
.theme-toggle .i-sun{display:none}
.theme-toggle[aria-pressed="true"] .i-sun{display:inline}
.theme-toggle[aria-pressed="true"] .i-moon{display:none}
@media print{.theme-toggle{display:none}}

/* --- Layout --- */
.layout{max-width:1200px;margin:0 auto;padding:var(--space-xl)}
.stack>*+*{margin-top:var(--space-l)}
.grid{display:grid;gap:var(--space-l)}
@media(min-width:900px){.grid.cols-2{grid-template-columns:repeat(2,1fr)}
  .grid.cols-3{grid-template-columns:repeat(3,1fr)}
  .grid.cols-4{grid-template-columns:repeat(4,1fr)}}

/* --- Page header --- */
.page-header h1{
  font-size:var(--font-size-heading-xl);line-height:var(--line-height-heading-xl);
  font-weight:var(--font-weight-heavy);margin:0;color:var(--color-text-heading-default)
}
.page-header p{margin:var(--space-xxs) 0 0;color:var(--color-text-body-secondary)}

/* --- Container --- */
.container{
  background:var(--color-background-container-content);
  border-radius:var(--border-radius-container);
  box-shadow:var(--shadow-container);
  border:1px solid transparent;overflow:hidden;
}
.container>.hd{
  padding:var(--space-m) var(--space-l);
  border-bottom:1px solid var(--color-border-divider-secondary);
  display:flex;align-items:baseline;gap:var(--space-xs);flex-wrap:wrap;
}
.container>.hd h2{
  margin:0;font-size:var(--font-size-heading-l);line-height:var(--line-height-heading-l);
  font-weight:var(--font-weight-heavy);color:var(--color-text-heading-default)
}
.container>.hd .counter{color:var(--color-text-body-secondary);font-weight:var(--font-weight-normal)}
.container>.hd .desc{flex-basis:100%;color:var(--color-text-body-secondary);font-size:var(--font-size-body-s)}
.container>.bd{padding:var(--space-l)}
.container>.bd.flush{padding:0}

/* --- Key/value pairs --- */
.kv dt{
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-s);
  color:var(--color-text-body-secondary);margin:0 0 var(--space-xxxs)
}
.kv dd{margin:0 0 var(--space-m);font-family:var(--font-family-monospace)}
.kv dd:last-child{margin-bottom:0}

/* --- Big score --- */
.score-hero{display:flex;align-items:baseline;gap:var(--space-s);flex-wrap:wrap}
.score-hero .val{
  font-size:var(--font-size-display-l);line-height:var(--line-height-display-l);
  font-weight:var(--font-weight-heavy);font-family:var(--font-family-monospace)
}
.score-hero .den{color:var(--color-text-body-secondary);font-size:var(--font-size-heading-l)}
.score-hero .rating{font-size:var(--font-size-heading-s);color:var(--color-text-body-secondary)}
/* Liveness ratios, per SKILL.md Step 4: visible beside the score without expanding anything. */
.score-hero .live{
  font-size:var(--font-size-body-s);color:var(--color-text-body-secondary);
  font-family:var(--font-family-monospace);margin-left:auto
}
.score-hero .live.bad{color:var(--color-text-status-error);font-weight:var(--font-weight-heavy)}
/* #4b: the config-not-behaviour qualifier, promoted out of 12px grey body text into a chip that
   sits in the hero. Bordered rather than coloured so it reads as a qualifier on the score, not
   as another status badge competing with the risk indicator. */
.thin{
  font-size:var(--font-size-body-s);color:var(--color-text-status-warning);
  font-weight:var(--font-weight-heavy);white-space:nowrap;cursor:help
}
.score-hero .chip-caveat{
  font-size:var(--font-size-body-s);line-height:18px;padding:0 var(--space-xs);
  border:1px solid var(--color-border-divider-default);border-radius:var(--border-radius-badge);
  color:var(--color-text-body-secondary);background:var(--color-background-layout-main);
  white-space:nowrap;cursor:help
}

/* --- Table --- */
/* .container has overflow:hidden so its own rounded corners clip cleanly, but that rule also clips a
   wide table's rightmost column — "Evidence & fix" — instead of letting the reader scroll to it, at
   narrow viewport widths or in print. Same pattern the evidence panel and improvement-plan <pre>
   blocks already use for the same reason (overflow-x:auto on the thing that might overflow, not on
   its container). Every <table> in this file is wrapped in a .tablewrap div for this. */
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:var(--font-size-body-m)}
thead th{
  text-align:left;padding:var(--space-xs) var(--space-l);
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-s);
  font-weight:var(--font-weight-heavy);color:var(--color-text-body-secondary);
  border-bottom:1px solid var(--color-border-divider-default);white-space:nowrap;
}
tbody td{
  padding:var(--space-xs) var(--space-l);vertical-align:top;
  border-bottom:1px solid var(--color-border-divider-secondary);
}
tbody tr:last-child td{border-bottom:none}
/* Table-level caveat. Bordered and quiet, so it reads as a qualifier on the whole table rather than
   as a status message competing with the risk column — but it is INSIDE the table, so it cannot be
   cropped out of a screenshot of the rows. */
table>caption.tbl-caveat{
  caption-side:top;text-align:left;
  padding:var(--space-xs) var(--space-l);
  color:var(--color-text-body-secondary);
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-m);
  border-bottom:1px solid var(--color-border-divider-secondary);
}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.qid{font-family:var(--font-family-monospace);white-space:nowrap;color:var(--color-text-body-secondary)}
td.detail{color:var(--color-text-body-secondary);font-family:var(--font-family-monospace);font-size:var(--font-size-body-s)}

/* --- Status indicator --- */
.si{display:inline-flex;align-items:center;gap:var(--space-xxs);white-space:nowrap}
.si-success{color:var(--color-text-status-success)}
.si-error{color:var(--color-text-status-error)}
.si-warning{color:var(--color-text-status-warning)}
.si-info{color:var(--color-text-status-info)}
.si-inactive{color:var(--color-text-status-inactive)}
.si .ico{font-weight:var(--font-weight-heavy)}

/* --- Badge --- */
.badge{
  display:inline-block;border-radius:var(--border-radius-badge);
  padding:0 var(--space-xxs);font-size:var(--font-size-body-s);line-height:18px;
  font-weight:var(--font-weight-heavy);color:#f9f9fa;background:var(--color-background-badge-grey);
  white-space:nowrap;
}
.badge-critical{background:var(--color-severity-critical);color:var(--color-text-badge-severity)}
.badge-high{background:var(--color-severity-high);color:var(--color-text-badge-severity)}
.badge-medium{background:var(--color-severity-medium);color:#0f141a}
.badge-low{background:var(--color-severity-low);color:#0f141a}
.badge-neutral{background:var(--color-severity-neutral)}
/* passing rows: the weight without the alarm colour */
.badge.wt-quiet{background:transparent;color:var(--color-text-body-secondary);
  border:1px solid var(--color-border-divider-default);font-weight:var(--font-weight-normal)}
.unverified{margin-top:var(--space-xs);color:var(--color-text-body-secondary);
  font-size:11px;font-style:italic}
.nolist{margin:0;color:var(--color-text-body-secondary);font-size:var(--font-size-body-s)}

/* --- Alert --- */
.alert{
  border:2px solid;border-radius:var(--border-radius-input);
  padding:var(--space-s) var(--space-m);display:flex;gap:var(--space-xs);align-items:flex-start;
}
.alert .ico{font-weight:var(--font-weight-heavy);flex:none}
.alert h3{margin:0 0 var(--space-xxs);font-size:var(--font-size-body-m);font-weight:var(--font-weight-heavy)}
.alert p{margin:0}
.alert p+p{margin-top:var(--space-xs)}
.alert-error{background:var(--color-background-status-error);border-color:var(--color-border-status-error)}
.alert-warning{background:var(--color-background-status-warning);border-color:var(--color-border-status-warning)}
.alert-info{background:var(--color-background-status-info);border-color:var(--color-border-status-info)}
.alert-success{background:var(--color-background-status-success);border-color:var(--color-border-status-success)}

/* --- Progress bar (pillar score) --- */
/* inline-block, not inline: a bare <span> ignores height and the bar renders as an empty cell */
.bar{display:inline-block;width:120px;height:var(--space-xs);border-radius:var(--space-xxs);
  background:var(--color-border-divider-secondary);overflow:hidden;vertical-align:middle}
.bar>i{display:block;height:100%;border-radius:var(--space-xxs)}

/* --- Expandable "how it was measured / how to fix" (native <details>, no JS) --- */
details.expand{margin-top:var(--space-xxs)}
details.expand>summary{
  cursor:pointer;list-style:none;display:inline-flex;align-items:center;gap:var(--space-xxs);
  color:var(--color-text-link-default);font-family:var(--font-family-base);
  font-size:var(--font-size-body-s);font-weight:var(--font-weight-heavy);
}
details.expand>summary::-webkit-details-marker{display:none}
details.expand>summary::before{content:"▸";font-size:10px}
details.expand[open]>summary::before{content:"▾"}
details.expand>summary:hover{text-decoration:underline}
details.expand>summary:focus-visible{outline:2px solid var(--color-text-status-info);outline-offset:2px}
.evidence-panel{
  margin-top:var(--space-xs);padding:var(--space-s);
  background:var(--color-background-cell-shaded);
  border-radius:var(--border-radius-input);
  border-left:3px solid var(--color-border-divider-default);
  font-family:var(--font-family-base);font-size:var(--font-size-body-s);
  line-height:var(--line-height-body-m);color:var(--color-text-body-default);
}
.evidence-panel dt{
  font-weight:var(--font-weight-heavy);color:var(--color-text-body-secondary);
  text-transform:uppercase;letter-spacing:.04em;font-size:10px;margin-top:var(--space-s);
}
.evidence-panel dt:first-child{margin-top:0}
.evidence-panel dd{margin:var(--space-xxxs) 0 0}
.evidence-panel pre{
  margin:var(--space-xxs) 0 0;padding:var(--space-xs);overflow-x:auto;
  background:var(--color-background-container-content);
  border:1px solid var(--color-border-divider-secondary);
  border-radius:var(--border-radius-badge);
  font-family:var(--font-family-monospace);font-size:11px;line-height:16px;white-space:pre-wrap;
  word-break:break-word;
}
.evidence-panel code{font-family:var(--font-family-monospace);font-size:11px;
  background:var(--color-background-container-content);padding:0 3px;border-radius:2px}
.evidence-panel .src{font-family:var(--font-family-monospace)}
.evidence-panel details.nested>summary{
  cursor:pointer;list-style:none;color:var(--color-text-body-secondary);
  font-size:var(--font-size-body-s);font-weight:var(--font-weight-normal);
}
.evidence-panel details.nested>summary::-webkit-details-marker{display:none}
.evidence-panel details.nested>summary::before{content:"▸ ";font-size:10px}
.evidence-panel details.nested[open]>summary::before{content:"▾ "}
.evidence-panel details.nested>summary:hover{text-decoration:underline}
.evidence-panel dl.inner{margin:var(--space-xs) 0 0;padding:0;background:none;border:none}

/* Named resources: the list a reader checks by eye */
.reshead{
  font-weight:var(--font-weight-heavy);font-size:11px;text-transform:uppercase;
  letter-spacing:.04em;margin-top:var(--space-xs);
}
.reshead:first-child{margin-top:0}
.reshead.ok{color:var(--color-text-status-success)}
.reshead.bad{color:var(--color-text-status-error)}
.reshead.ctx{color:var(--color-text-status-inactive)}
ul.reslist{
  margin:var(--space-xxxs) 0 0;padding-left:var(--space-m);
  font-family:var(--font-family-monospace);font-size:11px;line-height:17px;
}
ul.reslist.ok>li{color:var(--color-text-body-default)}
ul.reslist.bad>li{color:var(--color-text-body-default)}
ul.reslist.ctx>li{color:var(--color-text-body-secondary)}
.agree{
  margin-top:var(--space-xs);color:var(--color-text-status-success);
  font-size:11px;font-weight:var(--font-weight-heavy);
}
.disagree{
  margin-top:var(--space-xs);padding:var(--space-xs);
  background:var(--color-background-status-error);
  border-left:3px solid var(--color-border-status-error);
  border-radius:var(--border-radius-badge);
  color:var(--color-text-status-error);font-size:11px;line-height:16px;
}

/* Expand all / collapse all */
.bulk{margin-left:auto;display:inline-flex;gap:var(--space-xs)}
.bulk button{
  background:transparent;border:1px solid var(--color-border-divider-default);
  color:var(--color-text-link-default);cursor:pointer;
  border-radius:var(--border-radius-input);padding:2px var(--space-xs);
  font-family:inherit;font-size:var(--font-size-body-s);font-weight:var(--font-weight-heavy);
}
.bulk button:hover{background:var(--color-background-cell-shaded)}
.bulk button:focus-visible{outline:2px solid var(--color-text-status-info);outline-offset:2px}
.bulk[hidden]{display:none}
@media print{.bulk{display:none}}

/* --- Improvement plan --- */
.tier{border-left:3px solid var(--color-border-divider-default);padding-left:var(--space-m)}
.tier+.tier{margin-top:var(--space-xl)}
.tier-now{border-left-color:var(--color-text-status-error)}
.tier-soon{border-left-color:var(--color-text-status-warning)}
.tier-later{border-left-color:var(--color-text-status-info)}
.tier>h3{
  margin:0 0 var(--space-xxs);font-size:var(--font-size-heading-s);
  line-height:var(--line-height-heading-s);font-weight:var(--font-weight-heavy);
  color:var(--color-text-heading-default);
}
.tier>.when{margin:0 0 var(--space-s);color:var(--color-text-body-secondary);font-size:var(--font-size-body-s)}
.fix{padding:var(--space-s) 0;border-top:1px solid var(--color-border-divider-secondary)}
.fix:first-of-type{border-top:none;padding-top:0}
.fix>.head{display:flex;align-items:baseline;gap:var(--space-xs);flex-wrap:wrap}
.fix>.head .qid{font-family:var(--font-family-monospace);color:var(--color-text-body-secondary);font-size:var(--font-size-body-s)}
.fix>.head .what{font-weight:var(--font-weight-heavy)}
.fix>.now{margin:var(--space-xxs) 0 0;color:var(--color-text-body-secondary);font-size:var(--font-size-body-s)}
.fix>.now .measured{font-family:var(--font-family-monospace)}
.fix>.do{margin:var(--space-xs) 0 0}
.fix>.do pre{
  margin:var(--space-xxs) 0 0;padding:var(--space-xs);overflow-x:auto;
  background:var(--color-background-cell-shaded);border-radius:var(--border-radius-badge);
  font-family:var(--font-family-monospace);font-size:11px;line-height:16px;white-space:pre-wrap;
  word-break:break-word;
}
.fix>.do code{font-family:var(--font-family-monospace);font-size:12px;
  background:var(--color-background-cell-shaded);padding:0 3px;border-radius:2px}

.muted{color:var(--color-text-body-secondary)}
.small{font-size:var(--font-size-body-s);line-height:var(--line-height-body-s)}
ul.plain{margin:0;padding-left:var(--space-l)}
ul.plain li+li{margin-top:var(--space-xxs)}
footer.page{
  margin-top:var(--space-xl);padding:var(--space-l) 0 0;
  border-top:1px solid var(--color-border-divider-secondary);
  color:var(--color-text-body-secondary);font-size:var(--font-size-body-s);
}
@media print{
  .container{box-shadow:none;border:1px solid var(--color-border-divider-default);break-inside:avoid}
  .top-nav{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

# A dark report must not be bleached to white paper on print: the surfaces stay dark and the browser
# is told to honour them. Only the auto/light themes fall back to white for ink economy.
PRINT_LIGHT = "@media print{body{background:#fff}}\n"
PRINT_DARK = ("@media print{body,.container{-webkit-print-color-adjust:exact;"
              "print-color-adjust:exact}}\n")


def stylesheet(theme):
    """Assemble the stylesheet for one of: auto (default, togglable), light, dark.

    In `auto` the resolution order is CSS-only, so the report is correct before any script runs:
      1. light tokens as the base;
      2. OS dark  -> dark tokens, UNLESS the reader has pinned light via [data-theme=light];
      3. reader pinned dark -> dark tokens, whatever the OS says.
    The toggle only sets/clears `data-theme` on <html>; all four states are decided by CSS.
    """
    if theme == "light":
        return f":root {{{TOKENS_LIGHT}{TOKENS_SHARED}}}\n{BASE}{PRINT_LIGHT}"
    if theme == "dark":
        # Dark values override the light ones in the SAME rule, so a token missed in TOKENS_DARK
        # falls back to its light value rather than to nothing — a missing colour is visible as a
        # contrast bug, whereas an unset custom property silently renders as `initial`.
        return f":root {{{TOKENS_LIGHT}{TOKENS_DARK}{TOKENS_SHARED}}}\n{BASE}{PRINT_DARK}"
    return (
        f":root {{{TOKENS_LIGHT}{TOKENS_SHARED}}}\n"
        f'@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) '
        f"{{{TOKENS_DARK}}} }}\n"
        f':root[data-theme="dark"] {{{TOKENS_DARK}}}\n'
        f"{BASE}"
        # Print always uses the light set, whichever theme is on screen. Printing a dark report onto
        # white paper would otherwise mix a forced-white background with light-on-dark text colours,
        # which is the one combination that is actually unreadable.
        f'@media print {{ :root, :root[data-theme="dark"] {{{TOKENS_LIGHT}}} body{{background:#fff}} }}\n'
    )


# `color-scheme` makes the browser render its OWN widgets — scrollbars, focus rings, form controls —
# to match. Without it a dark report keeps a bright white scrollbar down the side.
COLOR_SCHEME = {"auto": "light dark", "light": "light", "dark": "dark"}

# Sun / moon drawn inline: no icon font, no sprite, no network. Two paths, both currentColor.
ICON_MOON = ('<svg class="i-moon" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
             'stroke-width="1.5" aria-hidden="true"><path d="M13.5 10.2A6 6 0 1 1 5.8 2.5'
             'a4.8 4.8 0 0 0 7.7 7.7Z"/></svg>')
ICON_SUN = ('<svg class="i-sun" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
            'stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="3.1"/>'
            '<path d="M8 .9v1.8M8 13.3v1.8M.9 8h1.8M13.3 8h1.8M2.98 2.98 4.25 4.25'
            'M11.75 11.75l1.27 1.27M13.02 2.98 11.75 4.25M4.25 11.75 2.98 13.02"/></svg>')

TOGGLE_HTML = (
    '<button id="theme-toggle" class="theme-toggle" type="button" hidden '
    'aria-pressed="false" aria-live="polite" title="Switch between light and dark theme">'
    f'{ICON_MOON}{ICON_SUN}<span class="label">Dark</span></button>')

# Inline, ~20 lines, no network of any kind: no fetch, no XHR, no import, no remote src.
# Wrapped in try/catch because localStorage throws on file:// in some browsers, and a theme
# preference is not worth breaking the report over.
TOGGLE_JS = """
(function(){
  var r=document.documentElement,b=document.getElementById('theme-toggle'),K='eks-war-theme';
  if(!b)return;
  var mq=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;
  function isDark(){var p=r.getAttribute('data-theme');
    return p?p==='dark':!!(mq&&mq.matches);}
  function paint(){var d=isDark();
    b.setAttribute('aria-pressed',d?'true':'false');
    b.querySelector('.label').textContent=d?'Light':'Dark';
    b.title='Switch to '+(d?'light':'dark')+' theme';}
  var saved=null;try{saved=localStorage.getItem(K);}catch(e){}
  if(saved==='dark'||saved==='light')r.setAttribute('data-theme',saved);
  paint();b.hidden=false;
  b.addEventListener('click',function(){
    var next=isDark()?'light':'dark';
    r.setAttribute('data-theme',next);
    try{localStorage.setItem(K,next);}catch(e){}
    paint();});
  if(mq&&mq.addEventListener)mq.addEventListener('change',function(){
    if(!r.getAttribute('data-theme'))paint();});
})();
(function(){
  var bar=document.getElementById('bulk');
  if(!bar)return;
  bar.addEventListener('click',function(ev){
    var b=ev.target.closest('button');if(!b)return;
    var open=b.getAttribute('data-act')==='open';
    var all=document.querySelectorAll('details.expand,details.nested');
    for(var i=0;i<all.length;i++)all[i].open=open;});
  bar.hidden=false;
})();
"""


def si(kind, label):
    ico = {"success": "✔", "error": "✕", "warning": "⚠",
           "info": "ℹ", "inactive": "–"}[kind]
    return (f'<span class="si si-{kind}"><span class="ico" aria-hidden="true">{ico}</span>'
            f'<span>{e(label)}</span></span>')


def sev_badge(qid, state=None):
    """This skill's own risk weight (High=3 / Medium=2 / Low=1) that `sev()` applies to this question
    — styled after the Well-Architected Tool's High/Medium Risk Issue labels, but not that
    classification. No AWS-published mapping backs High=3/Medium=2/Low=1; it is this skill's editorial
    tiering, kept only to order findings within a pillar (references/severity.md).

    It is NOT a severity rating of the cluster. On a failing row the colour is the priority signal;
    on a PASSING row a red "High" pill beside a green tick reads as an alarm, so passes and n/a get
    a muted neutral chip. Same number, different reading: on a fail "how urgent", on a pass "how
    much the score would lose if this regressed".
    """
    s = sev_of(qid)
    cls, label = {3: ("high", "High"), 2: ("medium", "Medium"), 1: ("low", "Low")}[s]
    if state in ("all", "na"):
        return f'<span class="badge wt-quiet">{label}</span>'
    return f'<span class="badge badge-{cls}">{label}</span>'


def bar(score):
    if not isinstance(score, (int, float)):
        return '<span class="muted">&mdash;</span>'
    kind = risk(score)[0]
    color = {"success": "var(--color-text-status-success)",
             "warning": "var(--color-text-status-warning)",
             "error": "var(--color-text-status-error)",
             "inactive": "var(--color-text-status-inactive)"}[kind]
    return (f'<span class="bar" role="img" aria-label="{score} out of 100">'
            f'<i style="width:{max(0,min(100,score))}%;background:{color}"></i></span>')


# Populated by evidence_panel() whenever a resource list contradicts its scorer's own count. main()
# exits non-zero if it is non-empty, so the guarantee lives in the SHIPPED renderer rather than in a
# test-harness gate that does not ship with the skill.
DISAGREEMENTS = []

# qid -> cross-check verdict, also populated by evidence_panel(): True = an independent resource list
# was re-derived and its N/M matched the scorer's own, False = it contradicted it, None = no
# cross-check was possible (no extractor for the question, or a yes/no detection with no total to
# compare against). The banner reports these counts instead of claiming that everything it did not
# name was verified: only ~2/3 of the measured questions have an extractor at all, so "unaffected"
# quietly promoted "never checked" to "checked and fine".
VERIFIED = {}

MAX_LIST = 12   # cap per list; a 40-node / 800-pod cluster would otherwise dominate the page


def _res_list(names, cls):
    if not names:
        return ""
    shown = names[:MAX_LIST]
    more = len(names) - len(shown)
    lis = "".join(f"<li>{e(n)}</li>" for n in shown)
    # State the real total, not just the remainder. "… and 288 more" leaves the reader to add 12 to it
    # to learn what the check actually looked at, and a truncated list read as the whole set is how a
    # 300-container finding gets argued about on the strength of 12 names.
    tail = (f'<li class="muted">showing {len(shown)} of {len(names)} &mdash; run the command in '
            f'&ldquo;How this was measured&rdquo; below for the full set</li>' if more > 0 else "")
    return f'<ul class="reslist {cls}">{lis}{tail}</ul>'


def evidence_panel(r, prose, prov, data):
    """What the reader needs, in the order they need it:
         1. why it matters
         2. WHAT WE FOUND — the named resources, so the verdict can be checked by eye
         3. how to fix
         4. how it was measured — file + expression, demoted to the bottom

    The verbatim jq used to sit above the fix. It serves a narrow audience (auditing the tool,
    disputing a finding, maintaining the skill) and pushed the actionable part out of view, so it is
    now last and behind its own nested toggle.
    """
    p, v = prose.get(r["id"], {}), prov.get(r["id"], {})
    state = r.get("state", "?")
    rows = []

    if p.get("rationale"):
        # md_inline(), not e(). The rationale is authored in the same markdown as the remediation and
        # eight of them use `code` spans or **bold**, but only the remediation was passed through the
        # inline renderer — so a High-severity caveat that was emphasised precisely to stand out
        # ("**Above that size it is a performance downgrade unless you provision IOPS.**", cost-9)
        # printed its asterisks and read as a typo. md_inline() escapes BEFORE it emits any markup,
        # so this widens what renders, not what executes.
        rows.append(f"<dt>Why it matters</dt><dd>{md_inline(p['rationale'])}</dd>")

    res = observed_resources(r["id"], data)
    body = ""
    agree, why = resource_agreement(r, res)
    # Recorded for EVERY question that renders a panel, not only the contradicted ones, so the banner
    # can say how many findings were actually cross-checked. setdefault because a question in both Top
    # priorities and its pillar table renders this panel twice.
    VERIFIED.setdefault(r["id"], agree)
    if res:
        if res["pass"]:
            body += (f'<div class="reshead ok">'
                     f'{e(res.get("pass_label", "Counted as passing"))} '
                     f'({len(res["pass"])})</div>' + _res_list(res["pass"], "ok"))
        if res["fail"]:
            body += (f'<div class="reshead bad">'
                     f'{e(res.get("fail_label", "Counted as failing"))} '
                     f'({len(res["fail"])})</div>' + _res_list(res["fail"], "bad"))
        if res.get("context"):
            body += (f'<div class="reshead ctx">{e(res.get("context_label","context"))} '
                     f'({len(res["context"])})</div>' + _res_list(res["context"], "ctx"))
    if body:
        # Three verification strengths must not LOOK equally verified. A counting check can be
        # cross-checked against its own total; an existence or field check cannot, and saying so is
        # the difference between evidence and a confident-looking assertion.
        if agree is True:
            note = f'<div class="agree">&#10003; {e(why)}</div>'
        elif agree is False:
            # A list that contradicts its own score is worse than no list. This used to fall through
            # to `note = ""`, so a contradiction rendered EXACTLY like a not-comparable check and the
            # run exited 0 — the only signal was the absence of a green tick. The file's own rule is
            # that absent-by-design must not look like absent-by-accident; this is that rule applied
            # to the contradicted case. DISAGREEMENTS is checked by main(), which exits non-zero.
            #
            # Keyed by question id because a question that appears in BOTH Top priorities and its
            # pillar table renders this panel twice, and appending twice made the banner and the
            # stderr line report "2 finding(s)" for one contradicted question, listing it twice. That
            # is the same defect that shipped once before in a summary counter: a number and the thing
            # it counts, never asserted against each other.
            if r["id"] not in {q for q, _ in DISAGREEMENTS}:
                DISAGREEMENTS.append((r["id"], why))
            note = ('<div class="disagree">&#9888; <strong>Unverified:</strong> this list does not '
                    f'match the count the check reported ({e(why)}). Treat both the list and the '
                    'result as unconfirmed and re-run the detection.</div>')
        elif res.get("kind") == "existence":
            # The name-pattern caveat used to live HERE, which is the one place it was least needed —
            # inside `if body:`, so it reached only the questions an extractor had already produced a
            # list for. It is now emitted from the scorer's jq for every name-pattern question, list
            # or no list, in the row below.
            note = ('<div class="unverified">This check answers yes/no rather than counting, so '
                    "there is no total for the report to check this list against. Confirm it by "
                    "eye.</div>")
        elif res.get("kind") == "field":
            note = ('<div class="unverified">This check reads cluster settings rather than counting '
                    "objects. The field paths and their values are printed above so the verdict is "
                    "checkable directly; there is no total to cross-check.</div>")
        else:
            # An honest default, NOT "". A list with no note rendered exactly like a cross-checked
            # one, so the strongest and the weakest evidence in the report looked identical — and
            # that is what hid a real scorer/extractor divergence on sec-30, whose detail
            # ("no ssh open (cluster SGs)") carries no N/M and whose extractor set no `kind`, so the
            # contradicted list fell through to here and rendered clean at exit 0.
            note = ('<div class="unverified">The check reported a result rather than a countable '
                    "total, so the report cannot cross-check this list against it. The list is what "
                    "the detection looked at; confirm it matches what you expect to be in "
                    "scope.</div>")
        rows.append(f"<dt>What we found</dt><dd>{body}{note}</dd>")
    else:
        # NEVER a silent omission. Absent-by-design and absent-by-accident must look different, or
        # the reader cannot tell "nothing to show" from "nobody implemented this".
        srcs = (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                or "the collected data")
        rows.append(
            '<dt>Resource list</dt><dd><p class="nolist">Not generated for this question. '
            f"The verdict came from {srcs} &mdash; open the section below and run the command "
            "yourself to see the objects. <em>This line exists so an absent list is never "
            "mistaken for an empty one.</em></p></dd>")

    # Emitted from the SCORER'S OWN jq, so it reaches every name-pattern question rather than only the
    # ones an extractor happened to produce a list for. That was the whole defect: the disclosure
    # existed, but lived inside `if body:`, so `ope-3`, `ope-8`, `ope-10`, `lens-1`, `lens-4`,
    # `rel-23`, `perf-2`, `lens-2` and `lens-3` rendered a bare red "Fail" with no hint that the
    # verdict was a substring match on a resource name — a cluster running Vector, Dynatrace or
    # Jenkins+Kustomize was reported as having no logging, no monitoring and no GitOps, with no caveat
    # anywhere near the finding.
    if name_pattern_based(v.get("jq")):
        rows.append(
            '<dt>How this was detected</dt><dd><p class="nolist">By <strong>matching a regular '
            'expression against resource names</strong> (or namespaces, or container images) '
            '&mdash; see the expression at the bottom of this panel &mdash; not by reading a field '
            'that states the answer. That cuts both ways, and both ways change the verdict: a tool '
            'that does the job under a name the pattern does not know is reported as '
            '<em>absent</em> (Vector rather than Fluent&nbsp;Bit, Dynatrace rather than Prometheus, '
            'Jenkins&nbsp;+&nbsp;Kustomize rather than Argo&nbsp;CD), and any object whose name '
            'merely matches is reported as <em>present</em>, whether or not it does anything. '
            'Check the pattern against what you actually run before accepting this result.</p></dd>')

    # A finding the report has just told the reader not to trust must not also hand them a
    # cluster-wide change to make. rbac-4 printed a `kubectl patch sa` sweep across every namespace
    # directly under its own "Treat both the list and the result as unconfirmed" warning — the two
    # halves of one panel giving opposite instructions, with the actionable half winning by default.
    # The remediation is still in the reference; it is withheld here until the contradiction is
    # resolved, because acting on a verdict that may be wrong is the expensive mistake.
    if r["id"] in {q for q, _ in DISAGREEMENTS}:
        rows.append(
            '<dt>How to fix</dt><dd><p class="nolist">Withheld. This finding contradicts itself '
            '(see above), so the result it would be fixing is not established. Re-run the detection '
            'in the section below against this cluster and confirm the count before changing '
            'anything &mdash; the remediation for this question is in the reference file named '
            'there.</p></dd>')
    elif state != "all" and p.get("remediation"):
        rows.append(f"<dt>How to fix</dt><dd>{md_inline(p['remediation'])}</dd>")

    method = [f"<dt>Data read</dt><dd class='src'>"
              + (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                 or "&mdash;") + "</dd>",
              f"<dt>Returned</dt><dd><code>{e(state)}</code>"
              + (f" &mdash; {e(r.get('detail',''))}" if r.get("detail") else "") + "</dd>"]
    if v.get("jq"):
        method.append(f"<dt>Exact command used</dt><dd><pre>{e(v['jq'])}</pre></dd>")
    if p.get("source"):
        method.append(f"<dt>Reference</dt><dd class='src'><code>references/{e(p['source'])}</code>"
                      f" &middot; question <code>{e(r['id'])}</code></dd>")
    rows.append('<dt>How this was measured</dt><dd>'
                '<details class="nested"><summary>Data source and detection expression</summary>'
                f'<dl class="evidence-panel inner">{"".join(method)}</dl></details></dd>')

    label = "Evidence &amp; fix" if state != "all" else "Evidence"
    return (f'<details class="expand"><summary>{label}</summary>'
            f'<dl class="evidence-panel">{"".join(rows)}</dl></details>')


def improvement_plan(measured, prose, prov):
    """Group everything that is not passing into three tiers and state the fix for each.

    Tiering is mechanical — severity weight x how far short the result fell — so the ordering is as
    reproducible as the scores. It deliberately does NOT invent effort estimates: the reference
    remediation says what to do, and how long it takes depends on the environment, not the data.

    Reads DISAGREEMENTS, which is why it must run AFTER the pillar sections: evidence_panel() is what
    populates it. build() already calls it last of the finding sections, and the withholding below is
    silently a no-op if that ever changes — so if this moves, move it back.
    """
    order = {"none": 0, "some": 1, "most": 2}
    open_items = [r for r in measured if r.get("state") in order]
    if not open_items:
        return None

    def tier_of(r):
        sev, st = sev_of(r["id"]), r["state"]
        if sev == 3 and st in ("none", "some"):
            return 0
        if (sev == 3 and st == "most") or (sev == 2 and st in ("none", "some")):
            return 1
        return 2

    tiers = [
        ("now", "Immediate", "High-risk controls that are absent or only partly in place. "
                             "Each is a High-severity question scoring below 75."),
        ("soon", "Short-term", "High-risk gaps that are mostly covered, plus absent "
                               "medium-risk controls."),
        ("later", "Strategic", "Remaining medium-risk partials and the low-risk practices. "
                               "Worth planning, not worth an interrupt."),
    ]
    out = []
    for idx, (cls, name, why) in enumerate(tiers):
        items = [r for r in open_items if tier_of(r) == idx]
        items.sort(key=lambda r: (-sev_of(r["id"]), order[r["state"]], r["id"]))
        if not items:
            continue
        blocks = []
        # Same suppression as the evidence panel, or the suppression is defeated in the same document:
        # the panel withheld the fix for a contradicted finding and this section printed it in full a
        # few sections later, so a reader working the Immediate tier top-down — which is how this
        # section is meant to be used — never saw the withholding at all.
        #
        # The item is KEPT, with a pointer to its own panel. Dropping it would trade one wrong for
        # another: an item vanishing from a prioritised list is indistinguishable from an item that
        # does not need doing, and the contradiction is a bug to chase, not a finding to ignore.
        contradicted = {q for q, _ in DISAGREEMENTS}
        for r in items:
            p = prose.get(r["id"], {})
            v = prov.get(r["id"], {})
            src = (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                   or "<span class='muted'>&mdash;</span>")
            if r["id"] in contradicted:
                do = ('<div class="do muted"><strong>Fix withheld &mdash; this finding contradicts '
                      'itself.</strong> The resource list for it does not match the count its own '
                      'detection reported, so the result this would be fixing is not established. '
                      'Kept in the plan rather than dropped, because an item disappearing from a '
                      'prioritised list reads as an item that does not need doing. See the '
                      '&ldquo;Evidence &amp; fix&rdquo; panel for this question above, resolve the '
                      'contradiction, then act.</div>')
            elif p.get("remediation"):
                do = f'<div class="do">{md_inline(p["remediation"])}</div>'
            else:
                do = '<div class="do muted">No remediation recorded for this question.</div>'
            blocks.append(
                '<div class="fix">'
                f'<div class="head"><span class="qid">{e(r["id"])}</span>{sev_badge(r["id"], r.get("state"))}'
                f'{si(*STATE_UI[r["state"]])}'
                f'<span class="what">{e(p.get("title","(question text unavailable)"))}</span></div>'
                f'<p class="now">Measured now: <span class="measured">{e(r.get("detail","") or r["state"])}</span>'
                f' &middot; from {src}</p>'
                + do + '</div>')
        out.append(f'<div class="tier tier-{cls}"><h3>{e(name)} '
                   f'<span class="muted">({len(items)})</span></h3>'
                   f'<p class="when">{e(why)}</p>{"".join(blocks)}</div>')
    return "".join(out), len(open_items)


def container(title, body, counter=None, desc=None, flush=False):
    c = f' <span class="counter">({e(counter)})</span>' if counter else ""
    d = f'<div class="desc">{e(desc)}</div>' if desc else ""
    return (f'<section class="container"><div class="hd"><h2>{e(title)}</h2>{c}{d}</div>'
            f'<div class="bd{" flush" if flush else ""}">{body}</div></section>')


# ---------------------------------------------------------------------------
# Cost hygiene posture. The Cost Optimization score cannot distinguish a fully-optimised fleet from
# an unoptimised one BY DESIGN — references/cost-optimization.md is explicit that Spot, Graviton and
# Extended Support are deliberately not scored, because each depends on intent the cluster cannot
# report, and a cluster at 100% on all three reads identically to one at 0%. That file requires the
# cluster's ACTUAL posture on those three levers to sit beside the score in every surface, including
# this HTML — not just the word "hygiene" once at the top. Derived here from data already collected
# (never restated from a scorer): node labels for Spot and Graviton, the cluster's own support type
# for Extended Support.
# ---------------------------------------------------------------------------
def _cost_posture(data):
    """(spot, graviton, total EC2 nodes, support type) for the cluster under review.

    Fargate nodes carry neither a capacity-type nor an architecture label in the sense these two
    levers mean, so they are excluded from the denominator the same way the compute-mode detection
    elsewhere in this file excludes them — a Fargate-only cluster reports 0 EC2 nodes rather than a
    misleading 0%.
    """
    ec2_nodes = [n for n in data["nodes"]
                 if _labels(n).get("eks.amazonaws.com/compute-type") != "fargate"]

    def is_spot(n):
        lb = _labels(n)
        return (lb.get("karpenter.sh/capacity-type") == "spot"
                or lb.get("eks.amazonaws.com/capacityType") == "SPOT")

    def is_graviton(n):
        return _labels(n).get("kubernetes.io/arch") == "arm64"

    total = len(ec2_nodes)
    spot = sum(1 for n in ec2_nodes if is_spot(n))
    graviton = sum(1 for n in ec2_nodes if is_graviton(n))
    support = data["cluster"].get("upgradePolicy", {}).get("supportType") or "unknown"
    return spot, graviton, total, support


def _cost_posture_note(data):
    """The lever-posture disclosure, as one `<p>` fragment — called from every place the Cost score
    renders, so the score is never shown without it."""
    spot, graviton, total, support = _cost_posture(data)
    lead = ('<strong>Cost Optimization (hygiene):</strong> this score measures whether cost controls '
            'are configured, not total cost efficiency. Spot, Graviton adoption and support status '
            'are not scored &mdash; a cluster that has taken every one of those three levers reads '
            'identically here to one that has taken none. ')
    if not total:
        body = "This cluster has no EC2 nodes to measure Spot/Graviton posture against."
    else:
        pct = lambda n: round(100 * n / total)
        body = (f'Measured posture: {e(spot)}/{e(total)} EC2 node(s) on Spot ({pct(spot)}%), '
                f'{e(graviton)}/{e(total)} on Graviton ({pct(graviton)}%), support status '
                f'{e(support)}.')
    return f'<p class="small muted">{lead}{body}</p>'


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def build(data, prose, prov, toggle=True):
    del DISAGREEMENTS[:]          # per-render: --both calls build() twice
    VERIFIED.clear()
    sc = data["scores"]
    res = data["results"]
    cl = data["cluster"]
    overall = sc.get("technical_overall")
    measured = [r for r in res if r.get("track") == "measured"]
    governance = [r for r in res if r.get("track") == "governance"]
    by_pillar = {k: {p["pillar"]: p for p in sc.get("pillars", [])}.get(k, {})
                 for k, _ in PILLARS}
    # Counted once, used by the page header, the coverage cells and the Governance panel, so those
    # three can never disagree about how many questions were asked.
    na_recs = [r for r in measured if r.get("state") == "na"]
    n_scored = len(measured) - len(na_recs)
    gov_by_pillar = {k: [r for r in governance if r.get("pillar") == k] for k, _ in PILLARS}

    region = (cl.get("arn", "").split(":")[3] if cl.get("arn") else "")

    # ---- liveness (SKILL.md Step 4) ---------------------------------------------------------------
    # No scorer reads a readiness condition or a pod phase, so a cluster whose nodes are all NotReady
    # has complete `spec` sections, passes every spec-side detection, and bands like a healthy one.
    # Computed HERE, before the hero, because Step 4 requires the ratios beside the score and the
    # withholding decision to be made from them.
    #
    # READ from scores.json, never recomputed. This block used to derive the ratios and apply the
    # withhold itself, which made the renderer a second implementation of a rule the reducer also
    # owned — and the two disagreed: `reduce.sh` emitted a numeric 69 for an all-NotReady cluster
    # while the HTML withheld it, so the chat and markdown surfaces published the number the report
    # refused to. Deriving it in one place is the fix; reading it here is what keeps it fixed.
    #
    # Deliberately NOT used to filter any denominator: excluding broken pods from a ratio would make a
    # cluster that cannot schedule its workload score BETTER. Judge what is declared; disclose what is
    # actually running.
    live = sc.get("liveness")
    if not isinstance(live, dict):
        raise SystemExit(
            "render-report.py: scores.json has no `liveness` block. It was produced by a reducer that "
            "predates the viability/liveness gates, so a dead or empty cluster may be carrying a "
            "numeric score. Re-run assets/reduce.sh and render again.")
    nodes_ready = live.get("nodes_ready", 0)
    pods_running = live.get("pods_running", 0)
    wl_pod_count = live.get("workload_pods", 0)
    not_viable = live.get("viable") is False
    no_node_ready = not not_viable and live.get("healthy") is False
    most_pods_down = bool(live.get("warning"))
    suppressed = live.get("suppressed_overall")
    # From the liveness block, not len(data["nodes"]), so the facts table and the gates cannot
    # disagree about how many nodes there were. data["nodes"] is still used for per-node detail
    # such as instance type, where the list itself is what is needed.
    node_count = live.get("nodes_total", 0)

    fargate_nodes = sum(1 for n in data["nodes"]
                        if (n.get("metadata", {}).get("labels") or {})
                        .get("eks.amazonaws.com/compute-type") == "fargate")
    if cl.get("computeConfig", {}).get("enabled") is True:
        mode = "EKS Auto Mode"
    elif data["fargate"] and fargate_nodes == node_count and node_count:
        mode = "Fargate only"
    else:
        mode = "Standard"

    out = []

    # ---- top navigation -----------------------------------------------------
    out.append(
        '<div class="top-nav"><span class="product">EKS Well-Architected Review</span>'
        f'<span class="sep">/</span><span class="ctx">{e(cl.get("name","(unknown cluster)"))}</span>'
        f'<span class="sep">/</span><span class="ctx">{e(region or "unknown region")}</span>'
        f'{TOGGLE_HTML if toggle else ""}</div>')

    out.append('<div class="layout stack">')

    # ---- page header --------------------------------------------------------
    # "103 measured questions answered" counted the `na`s as answers. They are the opposite: a question
    # that did not apply was NOT answered, and on the shipped example 15 of the 103 were `na` while the
    # 29 governance questions were never asked at all. Three different states, three different words.
    out.append(
        '<div class="page-header" style="display:flex;align-items:flex-end;gap:var(--space-m);'
        'flex-wrap:wrap"><div><h1>Well-Architected review</h1>'
        f'<p>Deterministic review of <code>{e(cl.get("name",""))}</code>. '
        f'Of {len(measured) + len(governance)} questions: <strong>{n_scored} scored</strong> from one '
        f'data collection, {len(na_recs)} did not apply to this cluster, and {len(governance)} were '
        f'not assessed (governance questions, put to the operator rather than measured &mdash; the '
        f'Governance section below groups them by why, which is not the same reason for all of them). '
        f'Data collected {e(data.get("collected","unknown"))}.</p>'
        '<p class="small muted">Unofficial review &mdash; not the AWS Well-Architected Tool. '
        'Covers five of the six Well-Architected pillars (no Sustainability). Scores describe '
        'configuration at collection time, not runtime behaviour or compliance.</p></div>'
        '<div class="bulk" id="bulk" hidden>'
        '<button type="button" data-act="open">Expand all evidence</button>'
        '<button type="button" data-act="close">Collapse all</button>'
        '</div></div>')

    # ---- disagreement banner ---------------------------------------------------------------------
    # Must appear ABOVE the tables, but is only knowable AFTER them: evidence_panel() is what detects a
    # contradiction. So reserve the slot now and fill it at the end of build().
    out.append("<!--DISAGREE_BANNER-->")

    # ---- liveness alerts (SKILL.md Step 4) --------------------------------
    # Above the summary, because a score read without them is misleading. Step 4 is explicit that
    # this is "a disclosure, not a refusal": a cluster mid-upgrade legitimately shows NotReady nodes
    # and a batch cluster legitimately sits at zero running pods, so the wording states what was
    # observed and leaves the judgement to the reader.
    if not_viable:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>NOT VIABLE &mdash; no data plane</h3>'
            f'<p>This cluster has <strong>0 nodes</strong>, so nothing can run on it and no score is '
            'published. The pillar detail below describes what the cluster '
            '<em>declares</em>; with no data plane, none of it is in effect.</p>'
            + (f'<p class="small">Configuration alone would have scored {e(suppressed)}/100. That '
               'number is stated here rather than as the verdict, because a cluster with no nodes '
               'cannot be said to score anything.</p>' if isinstance(suppressed, (int, float)) else "")
            + f'<p class="small">{wl_pod_count} workload pod(s) are declared. Pods without nodes are '
              'manifests, not running software — this case used to escape both gates and publish a '
              'full numeric score, because the viability check required zero pods as well as zero '
              'nodes.</p></div></div>')
    elif no_node_ready:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>NOT HEALTHY &mdash; no node is Ready</h3>'
            f'<p>{node_count} node(s) exist and <strong>0 are Ready</strong>, so the technical '
            'overall is withheld: the pillar scores below describe the configuration this cluster '
            '<em>declares</em>, and nothing here shows whether it can run a workload.</p>'
            # `reduce.sh` populates `suppressed_overall` identically for NOT VIABLE and NOT HEALTHY,
            # but only the NOT VIABLE banner above disclosed it — this branch simply never asked. Same
            # framing as that branch: the number is context for why the withholding matters, not the
            # verdict, and SKILL.md Step 4 forbids presenting it as the headline.
            + (f'<p class="small">Configuration alone would have scored {e(suppressed)}/100. That '
               'number is stated here rather than as the verdict, because a cluster with no Ready '
               'node cannot be said to be running the configuration it declares.</p>'
               if isinstance(suppressed, (int, float)) else "")
            + '<p class="small">Pillar scores are still shown, and are still valid as a description of '
              'declared configuration. A cluster mid-upgrade or mid-scale-up can legitimately look '
              'like this; check the nodes before reading anything below as a verdict.</p></div></div>')
    elif most_pods_down:
        out.append(
            '<div class="alert alert-warning"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>Fewer than half of the workload pods are Running</h3>'
            f'<p>{pods_running} of {wl_pod_count} workload pods are Running. The scores below are '
            'published, but they measure declared configuration &mdash; a pod that never starts is '
            'graded on the spec it would have run with.</p>'
            '<p class="small">Deliberate: filtering the ratios to Running pods would make a cluster '
            'that cannot schedule its workload score higher, not lower.</p></div></div>')

    # ---- alert when the overall is withheld --------------------------------
    # `not no_node_ready` because the liveness gate above also replaces the overall with a string, and
    # this alert would then blame the coverage gate for a withholding the coverage gate did not cause.
    # Two reasons, two messages: whichever one actually applied is the one shown.
    if not isinstance(overall, (int, float)) and not no_node_ready and not not_viable:
        insufficient = [(k, n) for (k, n) in PILLARS
                        if not isinstance(by_pillar[k].get("score"), (int, float))]
        # "Too little of this cluster is observable" was the wrong diagnosis for the common case. On a
        # 1-node cluster with no workload pods, every `na` under Reliability and Performance reads
        # "no workload Deployments" / "no workload containers": nothing was unobservable, there was
        # nothing there to observe. The three reasons are counted and named instead of merged.
        below_na = [r for r in na_recs
                    if r.get("pillar") in {k for k, _ in insufficient}]
        n_struct, n_nosub, n_unobs = na_split(below_na)
        why_bits = []
        if n_nosub:
            why_bits.append(f"{n_nosub} have no subject on this cluster (nothing of that kind is "
                            f"deployed, so there was nothing to measure &mdash; not something that "
                            f"could not be seen)")
        if n_struct:
            why_bits.append(f"{n_struct} can never apply to a cluster built this way")
        if n_unobs:
            why_bits.append(f"{n_unobs} could not be observed from the collected data")
        out.append(
            '<div class="alert alert-warning"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>Overall score withheld</h3>'
            f'<p>{e(str(overall))}. A technical overall is only published when at least four '
            'pillars clear the 50% coverage gate.</p>'
            f'<p class="small">Below the gate: {e(", ".join(n for _, n in insufficient)) or "none"}. '
            + (f'Of the {len(below_na)} question(s) those pillars could not score, '
               + "; ".join(why_bits) + ". " if why_bits else "")
            + 'Every question that did apply there was asked and answered, and is listed in the '
              'pillar detail below &mdash; what is withheld is the single number, not the '
              'assessment.</p></div></div>')

    # ---- executive summary -------------------------------------------------
    # Step 4: "Always report the two ratios in the header, healthy or not... A reader must be able to
    # see `3 nodes (0 Ready)` beside any score without expanding anything." They sit in the hero itself
    # rather than the facts table so no score can be read without them.
    live_cls = "live bad" if (no_node_ready or most_pods_down) else "live"
    live_html = (f'<span class="{live_cls}">{node_count} node(s) ({nodes_ready} Ready)'
                 f' &middot; {wl_pod_count} workload pod(s) ({pods_running} Running)</span>')
    # The config-not-behaviour caveat also renders once at the top in `small muted` — 12px grey against
    # a 42px bold score, a 3.5x size ratio, which is not a fair contest for the reader's attention.
    # Repeated here as a chip in the hero itself so the qualifier travels with the number it qualifies,
    # including when someone screenshots just the summary.
    caveat_chip = ('<span class="chip-caveat" title="This score reflects configuration found at '
                   'collection time. It is not a test of runtime behaviour and not a compliance '
                   'assessment.">configuration only &middot; not behaviour or compliance</span>')
    if isinstance(overall, (int, float)):
        kind, label = risk(overall)
        hero = (f'<div class="score-hero"><span class="val">{e(overall)}</span>'
                f'<span class="den">/ 100</span>'
                f'<span class="rating">{e(rating(overall))}</span>'
                f'<span>{si(kind, label + " risk")}</span>{caveat_chip}{live_html}</div>')
    else:
        hero = f'<div class="score-hero"><span class="val muted">&mdash;</span>' \
               f'<span class="rating">{e(str(overall))}</span>{caveat_chip}{live_html}</div>'

    # Every value taken from scores.json goes through e(), not just the ones sourced from the
    # cluster. The coverage cell and the governance counts did not, and a scores.json holding
    # `<script>` had it EXECUTE in the rendered report. scores.json is machine-written, so this
    # is a consistency defect rather than a live injection path — but it is the kind that stops
    # being theoretical the moment anything downstream starts editing that file.
    rows = []
    thin_cover = []
    no_band = []
    # NOT VIABLE withholds every pillar number, not just the overall. SKILL.md Step 4: "Stop scoring.
    # Report the control-plane facts, the applicable-question count, and nothing else. An empty cluster
    # must never score 'Excellent'." The renderer published five bands and five risk chips beside that
    # banner — and they rise as the cluster empties out, because the questions the missing objects would
    # have failed become `na` and leave the denominator: `orphaned-pods` (0 nodes) scored Operational
    # Excellence 73 where the healthy `well-configured` cluster scores 71, so a trend chart built from
    # these reports shows improvement during an outage, with "Medium risk" attached to a cluster that
    # has no data plane. Treated exactly like the coverage-gate withholding the `empty` fixture already
    # renders, so there is one visual language for "no number here" rather than two.
    #
    # NOT HEALTHY is deliberately NOT included: SKILL.md's own table says pillar scores "may still be
    # shown, labelled as describing declared configuration only" for that row, and the alert above says
    # so. Nodes that exist but are NotReady still declare a configuration; zero nodes declare nothing
    # that is in effect.
    withhold_pillars = not_viable
    n_also_uncovered = sum(1 for key, _ in PILLARS
                           if not isinstance(by_pillar[key].get("score"), (int, float)))
    for key, name in PILLARS:
        p = by_pillar[key]
        s = p.get("score")
        appl, tot = p.get("applicable", 0), p.get("total", 0)
        if withhold_pillars:
            s = None
        rk, rl = risk(s)
        if withhold_pillars:
            rl = "No score published"
        # Two statements, not one conditional expression, because `test-harness/validate-render.sh`
        # gate 11 §2 EXTRACTS the coverage-gate placeholder from this exact line rather than
        # transcribing it (`grep -oE 'shown = f"\{s\}" if isinstance\(s, \(int, float\)\) else "..."'`),
        # after a hand-copied literal there once went stale. Folding this into one expression breaks
        # that extraction silently.
        shown = f"{s}" if isinstance(s, (int, float)) else "No band published"
        if withhold_pillars:
            shown = "No score published"
        pillar_na = [r for r in na_recs if r.get("pillar") == key]
        n_struct, n_nosub, n_unobs = na_split(pillar_na)
        # THE THIN-EVIDENCE TEST RUNS ON QUESTIONS THAT COULD STILL BECOME MEASURABLE.
        # A pillar that only just cleared the 50% gate can still show a TOP band — at 1 applicable
        # question of 2, a single `all` renders "100 · Excellent · Low risk" off one observation — so the
        # marker exists to stop a thin band reading as a strong one. But measuring it against the RAW
        # total made it fire on every cluster: five of Operational Excellence's seven `na`s are
        # structural (fargate-1..4 on non-Fargate compute, plus ope-12 deduplicated against ope-6), so
        # OpEx is pinned at 12/19 = 63% and no non-Fargate cluster can exceed 74%. The marker then
        # labelled the `disaster` scenario's genuinely broken OpEx score of 38 "provisional, not a
        # verdict", pre-discounting a real failure. Structurally-inapplicable questions are excluded
        # from the denominator; the published score and the published `coverage` are untouched, this
        # decides only whether a caveat is shown.
        eff_tot = max(tot - n_struct, appl)
        eff_cov = round(100 * appl / eff_tot) if eff_tot else 0
        thin = isinstance(s, (int, float)) and eff_cov < 70
        if thin:
            thin_cover.append((name, appl, eff_tot, eff_cov, s, n_struct))
        # Not appended when the whole table is withheld for viability: the coverage gate is not why
        # these numbers are missing, and saying "a pillar needs half its measured questions to apply"
        # under a 0-node cluster would name the wrong cause. The count of pillars that WOULD also have
        # been gated is carried in the viability note below instead, so nothing is lost.
        if not isinstance(s, (int, float)) and not withhold_pillars:
            no_band.append((name, appl, tot, n_struct, n_nosub, n_unobs))
        # e() on every one of these too. A title="" attribute is still an HTML sink: an unescaped
        # value here breaks out of the attribute and injects live markup, which was the one gap left
        # after the coverage cell and the governance counts were fixed.
        mark = (' <span class="thin" title="Scored from '
                f'{e(appl)} of the {e(eff_tot)} questions that can apply to this cluster '
                f'({e(eff_cov)}%) — a narrow basis for this band.">thin&nbsp;evidence</span>'
                ) if thin else ""
        # FIX: the coverage cell counted MEASURED questions only, so Reliability read "22 / 22" — 100%,
        # nothing left to look at — while five governance questions in that pillar, one of them the
        # High-severity backup question, had never been assessed at all. The process questions are now
        # in the denominator and named, because "100%" next to an unassessed backup question is the
        # single most misleading cell in this report.
        gov_n = len(gov_by_pillar[key])
        cover_cell = f'{e(appl)}&thinsp;/&thinsp;{e(tot + gov_n)}'
        if gov_n:
            cover_cell += (f'<div class="small muted" style="white-space:normal">{e(gov_n)} process '
                           f'question(s) not assessed</div>')
        rows.append(
            f'<tr><td>{e(name)}</td>'
            f'<td class="num">{e(shown)}</td>'
            f'<td>{bar(s)}</td>'
            f'<td>{e(rating(s))}{mark}</td>'
            f'<td>{si(rk, rl)}</td>'
            f'<td class="num">{cover_cell}</td></tr>')
    # #10a: the config-not-behaviour caveat was attached to the OVERALL score only, and the pillar table
    # is the part of this report that gets screenshotted and forwarded. A <caption> travels with the
    # table — in a screenshot, in a copy-paste, in print — which a note above or below it does not.
    table = (
        '<div class="tablewrap"><table><caption class="tbl-caveat">Configuration only '
        '&middot; not behaviour or compliance '
        '&mdash; every pillar score below states which settings were found at collection time, not '
        'whether they work, are effective, or were tested.</caption>'
        '<thead><tr><th>Pillar</th><th class="num">Score</th><th></th>'
        # "Coverage" here and the chat/markdown headline's own "coverage" percentage are two different
        # numbers under one word: this cell is applicable/(total+governance) — 12/25, 48% — while the
        # 50% publication gate that headline quotes is applicable/measured-total — 12/19, 63%. Both
        # denominators are disclosed elsewhere on the page (the executive-summary prose above, and the
        # "N process question(s) not assessed" note inside the cell itself), so this is a naming fix,
        # not a second caveat: renaming the column stops the HTML and the chat headline from printing
        # different values under the same word.
        '<th>Rating</th><th>Risk (from score)</th><th class="num">Questions answered</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>')
    if thin_cover:
        # e() on a/t/c too. Escaping the name and the score but not the counts is how the injection
        # survived the previous fix: the same three values feed three different sinks (the coverage
        # cell, the row's title attribute, and this note) and all three need it.
        items = "; ".join(
            f"{e(n)} scored {e(sc_)} from {e(a)} of the {e(t)} questions that can apply here "
            f"({e(c)}%)" + (f", after excluding {e(st)} that can never apply to a cluster built "
                            f"this way" if st else "")
            for n, a, t, c, sc_, st in thin_cover)
        table += ('<p class="small muted"><strong>Thin evidence:</strong> ' + items +
                  '. These bands rest on few observations of questions that <em>could</em> have been '
                  'measured here, so they should move as more of the cluster is configured or '
                  'collected. Questions that can never apply to this cluster type are excluded from '
                  'that judgement, so this marker is about missing observation, not about a cluster '
                  'being small or serverless.</p>')
    if no_band:
        # #8: "Insufficient coverage / too little of this cluster is observable" for an empty cluster,
        # whose every `na` reads "no workload Deployments". Say which of the three it was.
        bits = []
        for n, a, t, st, ns, un in no_band:
            parts = []
            if ns:
                parts.append(f"{e(ns)} had no subject on this cluster")
            if st:
                parts.append(f"{e(st)} can never apply to a cluster built this way")
            if un:
                parts.append(f"{e(un)} could not be observed")
            bits.append(f"<strong>{e(n)}</strong> answered {e(a)} of {e(t)} measured questions"
                        + (" (" + ", ".join(parts) + ")" if parts else ""))
        table += ('<p class="small muted"><strong>No band published:</strong> ' + "; ".join(bits) +
                  '. A pillar needs half its measured questions to apply before a number is '
                  'published. Where the reason is that nothing of that kind is deployed, nothing was '
                  'unobservable &mdash; there was nothing there to observe, and the questions that '
                  'did apply were all asked and are listed below.</p>')
    if withhold_pillars:
        # One reason, stated where the numbers would have been, because this table is the part of the
        # report that gets screenshotted away from the banner above it.
        table += ('<p class="small muted"><strong>No pillar score published:</strong> this cluster has '
                  f'<strong>{e(node_count)} nodes</strong>, so nothing it declares is in effect and no '
                  'pillar can be said to score anything &mdash; the same withholding the overall gets, '
                  'applied consistently. Emptiness would otherwise raise these numbers rather than '
                  'lower them: every question the missing objects would have failed becomes '
                  '<em>not applicable</em> and leaves the denominator. The question counts and the '
                  'coverage column are kept &mdash; they are facts about what was asked and answered, '
                  'and every answer is listed in the pillar sections below.'
                  + (f' {e(n_also_uncovered)} of the five would also have been withheld for '
                     f'insufficient coverage.' if n_also_uncovered else "")
                  + '</p>')
    # Beside the Cost score here too — this is the first place in the report the score appears.
    table += _cost_posture_note(data)
    out.append(container("Executive summary",
                         f'<div class="bd" style="padding:0 0 var(--space-l)">{hero}</div>' + table,
                         desc="Technical score is the mean of the numeric pillar scores. "
                              "\"Questions answered\" is applicable measured questions over every "
                              "question in the pillar, process questions included; the 50% "
                              "publication gate is measured over the measured questions alone.",
                         flush=False))

    # ---- top priorities: worst High-severity findings first ----------------
    order = {"none": 0, "some": 1, "most": 2}
    prio = sorted((r for r in measured if r.get("state") in order),
                  key=lambda r: (-sev_of(r["id"]), order[r["state"]]))[:5]
    if prio:
        items = "".join(
            f'<tr data-qid="{e(r["id"])}" data-state="{e(r["state"])}" '
            f'data-severity="{sev_of(r["id"])}" data-pillar="{e(r.get("pillar",""))}">'
            f'<td class="qid">{e(r["id"])}</td><td>{sev_badge(r["id"], r.get("state"))}</td>'
            f'<td>{e(prose.get(r["id"],{}).get("title","(question text unavailable)"))}</td>'
            f'<td>{si(*STATE_UI[r["state"]])}</td>'
            f'<td class="detail">{e(r.get("detail",""))}'
            f'{evidence_panel(r, prose, prov, data)}</td></tr>'
            for r in prio)
        out.append(container(
            "Top priorities",
            '<div class="tablewrap"><table><thead><tr><th>ID</th><th>Risk weight</th>'
            '<th>Question</th><th>Result</th><th>Evidence &amp; fix</th></tr></thead>'
            f'<tbody>{items}</tbody></table></div>',
            counter=str(len(prio)),
            desc="Highest risk weight first (this skill's own editorial tiering, not an AWS "
                 "Well-Architected risk classification), then the weakest result. Expand any row "
                 "for the data it was measured from and the fix.", flush=True))

    # ---- cluster facts -----------------------------------------------------
    # The liveness ratios repeated here for the reader who scrolls to the facts table; the values are
    # computed once at the top of build() so the header and this table can never disagree.
    facts = [
        ("Cluster", cl.get("name", "—")),
        ("Region", region or "—"),
        ("Kubernetes version", cl.get("version", "—")),
        ("Platform version", cl.get("platformVersion", "—")),
        ("Compute mode", mode),
        ("Nodes", f"{node_count} ({nodes_ready} Ready)"),
        ("Workload pods", f"{wl_pod_count} ({pods_running} Running)"),
        ("Support type", cl.get("upgradePolicy", {}).get("supportType", "—")),
        ("Endpoint access", "private only" if cl.get("resourcesVpcConfig", {})
            .get("endpointPublicAccess") is False else "public enabled"),
        ("Pod Identity associations", f"{len(data['podidentity'])}"),
    ]
    cols = ['<dl class="kv">' + "".join(
        f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in facts[i::3]) + "</dl>"
        for i in range(3)]
    out.append(container("Cluster", f'<div class="grid cols-3">{"".join(cols)}</div>'))

    # ---- per-pillar findings ----------------------------------------------
    for key, name in PILLARS:
        p = by_pillar[key]
        qs = [r for r in measured if r.get("pillar") == key]
        if not qs:
            continue
        rank = {"none": 0, "some": 1, "most": 2, "all": 3, "na": 4}
        qs.sort(key=lambda r: (rank.get(r.get("state"), 9), -sev_of(r["id"]), r["id"]))
        rows = "".join(
            f'<tr data-qid="{e(r["id"])}" data-state="{e(r.get("state",""))}" '
            f'data-severity="{sev_of(r["id"])}" data-pillar="{e(key)}">'
            f'<td class="qid">{e(r["id"])}</td><td>{sev_badge(r["id"], r.get("state"))}</td>'
            f'<td>{e(prose.get(r["id"],{}).get("title","(question text unavailable)"))}</td>'
            f'<td>{si(*STATE_UI.get(r.get("state"), ("inactive", r.get("state","?"))))}</td>'
            f'<td class="detail">{e(r.get("detail",""))}'
            f'{evidence_panel(r, prose, prov, data)}</td></tr>' for r in qs)
        s = p.get("score")
        # Withheld here too, or the number the summary table refuses to publish is published one
        # section down in this pillar's own subtitle.
        head = ("No score published (0 nodes)" if withhold_pillars
                else f'{s}/100' if isinstance(s, (int, float)) else "Insufficient coverage")
        counts = {k: sum(1 for r in qs if r.get("state") == k)
                  for k in ("all", "most", "some", "none", "na")}
        summary = (f'{head} &middot; {counts["all"]} pass, {counts["most"]} mostly, '
                   f'{counts["some"]} partial, {counts["none"]} fail, {counts["na"]} n/a')
        # references/cost-optimization.md requires the cluster's actual Spot/Graviton/support-status
        # posture beside the Cost score in EVERY surface, including the HTML — the score above measures
        # cost hygiene only and reads identically whether every lever below has been pulled or none has.
        pillar_lead = f'<div style="padding:var(--space-m) var(--space-l) 0">{_cost_posture_note(data)}</div>' \
                      if key == "cost-optimization" else ""
        out.append(container(
            name,
            pillar_lead +
            '<div class="tablewrap"><table><thead><tr><th>ID</th><th>Risk weight</th>'
            '<th>Question</th><th>Result</th><th>Evidence &amp; fix</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>',
            counter=f'{p.get("applicable",0)} of {p.get("total",0)} applicable',
            desc=re.sub("<[^>]+>", "", summary).replace("&middot;", "·"),
            flush=True))

    # ---- improvement plan --------------------------------------------------
    plan = improvement_plan(measured, prose, prov)
    if plan:
        plan_html, n_open = plan
        # ~47 mutating commands (kubectl delete pv, aws ec2 delete-volume, aws ec2
        # revoke-security-group-egress, a mesh-wide PeerAuthentication STRICT, ...) sit directly under
        # measured evidence here, in a plan with schedule-shaped tier names ("Immediate", "Short-term").
        # Nothing on the page told the reader this review never ran any of them — grepping a rendered
        # report for "read-only" or "change process" returned nothing. One sentence, at the top of the
        # one section that is a checklist of things to go DO, closes that gap.
        readonly_note = (
            '<p class="small muted" style="margin:0 0 var(--space-m)">This review is '
            '<strong>read-only</strong>: nothing on this cluster was changed to produce it, and none '
            'of the commands below has been run or tested against this cluster. Apply them through '
            'your own change process, not directly from this page.</p>')
        plan_html = readonly_note + plan_html
        out.append(container(
            "Improvement plan", plan_html,
            counter=f"{n_open} open item(s)",
            desc="Every question not scoring `all`, tiered by risk weight and how far short the "
                 "result fell, with the remediation from the reference for that question. "
                 "Effort is deliberately not estimated — it depends on the environment, "
                 "not on the collected data."))

    # ---- governance --------------------------------------------------------
    # The unassessed questions are NAMED here, grouped by the pillar whose coverage cell they are
    # missing from. The panel used to say "29 of 29 answered — Not Assessed" and describe the category
    # in the abstract, so a reader could not find out WHICH questions had gone unasked — and could not
    # discover that one of Reliability's five is the High-severity backup question, in a pillar whose
    # coverage cell read 100%.
    # Listed in full, not through _res_list(): these are the whole point of the section, so the
    # MAX_LIST cap (and its "run the command below" tail, which has no command here) must not apply.
    # Grouped by WHY each was not assessed (GOV_UNASSESSED), not by pillar — one blanket reason for all
    # 29 was false for several of them, and a reader deciding between "not verifiable by automated
    # review" and "not verified" needs the difference. The pillar is kept on every line, because that
    # is what the coverage cells above are missing these questions from.
    pillar_name = dict(PILLARS)
    gov_by_group = {}
    for r in governance:
        gov_by_group.setdefault(
            GOV_UNASSESSED.get(r.get("id"), ("unclassified", ""))[0], []).append(r)
    gov_ids = ""
    for gkey, glabel, gwhy in GOV_GROUPS:
        grs = sorted(gov_by_group.get(gkey, []), key=lambda x: x["id"])
        if not grs:
            continue
        lis = []
        for r in grs:
            note = GOV_UNASSESSED.get(r["id"], ("", ""))[1]
            lis.append(
                f'<li><strong>{e(r["id"])}</strong> <span class="muted">'
                f'({e(pillar_name.get(r.get("pillar"), r.get("pillar", "?")))})</span> '
                f'{e(prose.get(r["id"], {}).get("title", ""))}'
                + (f'<div class="small muted">{md_inline(note)}</div>' if note else "")
                + '</li>')
        gov_ids += (f'<div class="reshead ctx">{glabel} ({len(grs)})</div>'
                    f'<p class="small muted">{gwhy}</p>'
                    f'<ul class="reslist ctx">{"".join(lis)}</ul>')
    g = sc.get("governance", {})
    gscore = g.get("score")
    if gscore == "Not Assessed" or not governance:
        body = (
            '<div class="alert alert-info"><span class="ico" aria-hidden="true">&#8505;</span>'
            f'<div><h3>{e(g.get("answered",0))} of {e(g.get("total",len(governance)))} answered '
            '&mdash; Not Assessed</h3>'
            # "incident response, DR testing" was struck: NO question among these asks about either.
            # rel-10/rel-12 ask whether snapshot objects and schedules are configured, not whether a
            # restore was ever tested. Advertising those domains told a reader they were in scope and
            # merely pending an interview. The domains named here are ones a listed question covers.
            '<p>These questions are put to the operator instead of being measured. Between them they '
            'cover infrastructure-as-code and manifest templating, upgrade planning and capacity '
            'review, change management, environment separation, RBAC and cluster-creation practice, '
            'secret and certificate rotation, compliance scanning, image signing, backup and snapshot '
            'configuration, EFS encryption, and cost-visibility practice. '
            '<strong>Why each one was not assessed differs, and is stated per question below</strong> '
            '&mdash; for some, nothing in the collected output states the answer; for others the '
            'answer is one uncollected API call away, or is already in the data this run wrote.</p>'
            '<p class="small">They were not guessed and are excluded from every score above. '
            'Re-run in interactive mode to have them asked and scored separately. They are also '
            'excluded from every pillar <em>score</em>, but they are counted in the coverage cells '
            'above, so a pillar showing full coverage of its measured questions still has these '
            'open.</p>'
            + (f'<div class="evidence-panel" style="margin-top:var(--space-s)">{gov_ids}</div>'
               if gov_ids else "")
            + '</div></div>')
    else:
        # The label sits ON the hero, not below it. A governance score is the ONLY number in this
        # report that is not measured from cluster data — it is what a human said in an interview — and
        # it renders in the same 42px treatment as the machine-derived technical score, inside a report
        # headed "Deterministic review". A forwarded report reads it as machine-derived unless the hero
        # itself says otherwise.
        body = (f'<div class="score-hero"><span class="val">{e(gscore)}</span>'
                f'<span class="den">/ 100</span><span class="rating">'
                f'{e(g.get("answered",0))} of {e(g.get("total",0))} answered</span>'
                f'<span class="live">self-reported &mdash; not measured</span></div>'
                '<p class="small muted">These answers came from the interview, not from '
                '<code>aws</code> or <code>kubectl</code> output. Nothing in this section was verified '
                'against the cluster, and it is excluded from the technical score above. Treat it as '
                'the operator&rsquo;s own account of process, which is what governance questions ask '
                'for.</p>'
                + (f'<div class="evidence-panel">{gov_ids}</div>' if gov_ids else ""))
    out.append(container("Governance", body))

    # ---- method ------------------------------------------------------------
    out.append(container("Method", (
        '<ul class="plain">'
        '<li>Every score is produced by a fixed <code>jq</code> detection over a single data '
        'collection. Thresholds live in the detections, not in judgement, so the same collected '
        'data always yields the same score.</li>'
        '<li>State to score: <code>all</code>=100, <code>most</code>=75, <code>some</code>=50, '
        '<code>none</code>=0. <code>na</code> is excluded from both numerator and denominator, '
        'so a question that does not apply cannot earn or cost points.</li>'
        '<li>Each question carries a risk weight this skill assigns &mdash; High=3, Medium=2, '
        'Low=1 &mdash; shown in the Severity column, and used to order findings within a pillar. '
        'This tiering is this skill&rsquo;s own editorial judgement, not an AWS Well-Architected '
        'risk classification &mdash; no published AWS mapping backs High/Medium/Low here, and the '
        'Well-Architected Tool&rsquo;s own Risk Issue labels are scoped to Framework lens '
        'questions, not to these derived checks. The ordering is still the right one to '
        'prioritise by. A pillar score is the severity-weighted mean of its applicable '
        'questions.</li>'
        '<li>A pillar scores only if applicable questions reach 50% of its measured total; '
        'otherwise it reports insufficient coverage. Fewer than four numeric pillars withholds '
        'the overall.</li>'
        '<li>Object checks assess cluster-owned resources only: workload namespaces (AWS-managed '
        '<code>kube-*</code>/<code>amazon-*</code> excluded), custom RBAC roles, volumes tagged '
        'to this cluster, ECR repositories referenced by cluster images.</li>'
        '<li>The <strong>Cost Optimization (hygiene)</strong> score measures <em>cost hygiene</em> '
        '&mdash; whether quotas, tagging, storage class and idle-resource controls are configured '
        '&mdash; not total cost efficiency. Spot adoption, Graviton adoption and Extended Support '
        'status are workload- or date-dependent and are not scored: a cluster that has taken every '
        'one of those levers scores exactly the same here as one that has taken none. The '
        'cluster&rsquo;s actual measured posture on all three is reported as a fact beside the score '
        'itself, not folded into it &mdash; see the note under the Cost Optimization row above and '
        'in its own section below.</li>'
        '<li><strong>Every pillar score measures configuration present at collection time</strong> '
        '&mdash; not runtime behaviour, and not compliance with any standard. A pass means the '
        'setting was found, not that it works, that it is effective, or that it was tested. This '
        'applies to Security and Reliability exactly as much as to Cost.</li>'
        # The report reproduced only the Sustainability half of the skill's own scope disclosure, so
        # "IPv6", "multi-tenancy" and "Windows" appeared nowhere in the rendered HTML. A gap the skill
        # states in SKILL.md and the report omits is a gap the reader reasonably takes for a pass —
        # a Windows-node-pool or IPv6 cluster would read this as having been reviewed. Carried over
        # verbatim from SKILL.md so the two cannot drift.
        '<li><strong>What is not assessed at all.</strong> Sustainability (one of the six pillars) '
        '&mdash; it is not deterministically observable from cluster state. And, equally: '
        '<strong>IPv6 clusters</strong> and <strong>multi-tenancy isolation depth</strong>. '
        # Windows moved from "not assessed at all" to "partly assessed" when podsec-1 stopped
        # excluding Windows pods: `runAsNonRoot` is admissible, PSS-Restricted-required and
        # kubelet-enforced on them, so a Windows container is now counted and can fail. Saying
        # "not assessed" here while a Windows pod is being scored two sections above would be the
        # same drift this bullet exists to prevent, in the opposite direction. Kept in step with
        # SKILL.md's own scope paragraph.
        '<strong>Windows is partly assessed:</strong> <code>podsec-1</code> counts Windows '
        'containers and reads <code>windowsOptions.runAsUserName</code> alongside '
        '<code>runAsNonRoot</code>, while <code>podsec-5</code> excludes them because the '
        'capabilities field is rejected by the API server on a Windows pod. Windows node pools '
        '<em>as such</em> &mdash; node hardening, GMSA, the Windows-specific parts of the CNI '
        '&mdash; are not assessed. These are genuine gaps, not implied '
        'passes &mdash; nothing in this report should be read as having checked them.</li>'
        '<li><strong>Unofficial.</strong> This is not the AWS Well-Architected Tool and produces no '
        'AWS-recorded workload review. AWS publishes no Well-Architected lens for Amazon EKS or '
        'Kubernetes &mdash; the closest official lens, Container Build, covers the container build '
        'process rather than cluster operation. These questions are this skill&rsquo;s own '
        'interpretation of Well-Architected guidance applied to EKS.</li>'
        '<li><strong>Before sharing this report:</strong> it names real infrastructure &mdash; the '
        'cluster and its region, node and volume identifiers, security group and subnet IDs, IAM role '
        'and OIDC provider ARNs (which contain the AWS account ID), and workload namespaces and pod '
        'names. That detail is the point: it is what makes each finding checkable. But it is also '
        'enough to describe the environment to someone outside it, so treat the file as internal and '
        'mask the account ID and resource identifiers before sending it anywhere the cluster owner '
        'would not. Identifiers for resources <em>outside</em> this cluster are already reduced to '
        'counts rather than named.</li>'
        '</ul>')))

    out.append('<footer class="page">Generated locally from collected cluster data. '
               'No data left this machine. Styled with the Cloudscape Design System.</footer>')
    out.append('</div>')

    banner = ""
    if DISAGREEMENTS:
        ids = ", ".join(f"<code>{e(q)}</code>" for q, _ in DISAGREEMENTS[:12])
        more = f" and {len(DISAGREEMENTS) - 12} more" if len(DISAGREEMENTS) > 12 else ""
        # "Everything else in this report is unaffected" claimed a cross-check the report had not
        # performed. Only the questions with an extractor AND a countable total get one — roughly two
        # thirds of the measured questions — so the sentence quietly promoted "never checked" to
        # "checked and fine". Both counts are now stated, and both come from VERIFIED, which
        # evidence_panel() fills as it renders each panel.
        n_agree = sum(1 for v in VERIFIED.values() if v is True)
        n_unchecked = sum(1 for v in VERIFIED.values() if v is None)
        banner = (
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            f'<div><h3>{len(DISAGREEMENTS)} finding(s) could not be verified</h3>'
            '<p>For these questions the named resource list does not match the count the detection '
            f'reported: {ids}{more}.</p>'
            '<p class="small">A resource list is a second reading of the same collected data, so a '
            'mismatch means one of the two is wrong and neither should be trusted. '
            f'Of the remaining findings, <strong>{n_agree}</strong> were cross-checked the same way '
            f'and agreed, and <strong>{n_unchecked}</strong> carry no independent cross-check at all '
            '&mdash; either no resource list is derived for the question, or its detection answers '
            'yes/no and offers no total to check a list against. Those are unchallenged, not '
            'confirmed. The renderer exits non-zero when this banner appears.</p>'
            '</div></div>')
    return "\n".join(out).replace("<!--DISAGREE_BANNER-->", banner)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work", help="work directory containing scores.json and results.jsonl")
    ap.add_argument("-o", "--out", help="output HTML file (default: <work>/report.html)")
    ap.add_argument("--references", help="skill references dir, for question titles")
    ap.add_argument("--theme", choices=("auto", "light", "dark"), default="auto",
                    help="auto (default) follows the reader's OS via prefers-color-scheme; "
                         "light/dark pin one set, for when the report is emailed, attached to a "
                         "ticket, or printed and the reader's OS setting is not yours to predict")
    ap.add_argument("--both", action="store_true",
                    help="write two PINNED files: <out> in light and <out>-dark.html in dark, "
                         "neither with a toggle (for print, email or a ticket attachment)")
    ap.add_argument("--no-toggle", action="store_true",
                    help="omit the theme toggle from the auto theme; the report still follows "
                         "prefers-color-scheme, it just carries no script")
    args = ap.parse_args()

    data = load(args.work)
    ref = args.references or (pathlib.Path(__file__).resolve().parent.parent / "references")
    prose = question_prose(ref)
    prov = scorer_provenance(ref)

    cl = data["cluster"].get("name", "cluster")

    def document(theme):
        # The toggle only makes sense in `auto`: --theme light/dark exist precisely to PIN a theme
        # for print, email or a ticket attachment, where an interactive control would be misleading.
        show_toggle = theme == "auto" and not args.no_toggle
        body = build(data, prose, prov, toggle=show_toggle)
        script = f"<script>{TOGGLE_JS}</script>" if show_toggle else ""
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="{COLOR_SCHEME[theme]}">'
            f"<title>EKS Well-Architected Review — {e(cl)}</title>"
            f"<style>{stylesheet(theme)}</style></head><body>\n{body}\n{script}\n</body></html>\n")

    base = pathlib.Path(args.out) if args.out else pathlib.Path(args.work) / "report.html"
    if args.both and args.theme != "auto":
        # --both always writes a light file plus a dark sibling, so a --theme alongside it is silently
        # discarded. Say so rather than producing output that does not match the flags given.
        print(f"note: --both writes a light file and a -dark sibling; --theme {args.theme} is ignored",
              file=sys.stderr)
    targets = [(base, "light" if args.both else args.theme)]
    if args.both:
        targets.append((base.with_name(base.stem + "-dark" + base.suffix), "dark"))

    # Validate every destination BEFORE building anything. A nonexistent parent directory or a directory
    # given as the target used to raise FileNotFoundError / IsADirectoryError after the entire report had
    # been rendered — all the work done, a raw traceback, and nothing written.
    for out, _ in targets:
        if out.is_dir():
            sys.exit(f"render-report: -o {out} is a directory, not a file")
        if not out.parent.exists():
            sys.exit(f"render-report: -o parent directory does not exist: {out.parent}")
        if not os.access(out.parent, os.W_OK):
            sys.exit(f"render-report: -o parent directory is not writable: {out.parent}")

    for out, theme in targets:
        doc = document(theme)
        try:
            out.write_text(doc)
        except OSError as exc:
            sys.exit(f"render-report: could not write {out}: {exc}")
        print(f"wrote {out} ({len(doc):,} bytes, {theme} theme)")

    # Fail the run when any resource list contradicts its own score. The report is still written — it
    # names the affected questions and carries the banner — but the exit code makes the contradiction
    # impossible to miss in a pipeline. This is what makes the guarantee true for a consumer holding
    # only the skill directory, with no test harness.
    if DISAGREEMENTS:
        print(f"\nERROR: {len(DISAGREEMENTS)} finding(s) have a resource list that contradicts the "
              f"count their detection reported:", file=sys.stderr)
        for qid, why in DISAGREEMENTS:
            print(f"  {qid}: {why}", file=sys.stderr)
        print("The report was written and flags them, but do not trust those findings.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
