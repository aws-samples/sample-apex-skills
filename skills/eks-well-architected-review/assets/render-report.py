#!/usr/bin/env python3
"""Render an EKS Well-Architected review as a self-contained Cloudscape-styled HTML report.

Usage:  python3 -B render-report.py <WORK_DIR> [-o report.html]

Reads ONLY the files the collection step wrote and the scorers produced:
  scores.json      pillar + overall scores (authoritative — never recomputed here), plus the `severity`
                   map: the per-question weights those scores were computed with, which reduce.sh parsed
                   out of references/severity.md. The Severity column and the action-plan tiering are
                   read from that map, so they cannot rank a finding by a weight the score did not use
  results.jsonl    one line per question: pillar, id, track, state, detail — plus, on the questions
                   whose scorer runs an `rl` line, a sixth `resources` key holding the NAMES of the
                   objects that check counted. That field is the report's evidence list; the renderer
                   sorts, labels and truncates it and derives nothing of its own from it. `null` there
                   means the scorer could not build the list; an absent key means the question
                   publishes none. See the "Observed resources" section below
  .collection.json the collection fingerprint assets/collect.sh writes: the UTC instant the data was
                   read (this is where "Data collected" comes from), the cluster and region as
                   collected, and a sha256 over every collected file. Asserted, not trusted — see
                   collection_digest() and load()'s provenance gate
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
one file that opens offline, which the skill's "the report makes no network requests" contract requires.
"""
import sys
# Before any other import: stop this process compiling bytecode for the modules it imports from here on.
# Apple's command-line-tools python3 would otherwise write them under ~/Library/Caches/com.apple.python,
# outside the work directory. SKILL.md runs this file as `python3 -B`, which also covers the modules the
# interpreter loads at startup, before this line; this line covers a run started without `-B`.
sys.dont_write_bytecode = True
import argparse
import hashlib
import html
import json
import os
import pathlib
import re

# ---------------------------------------------------------------------------
# SEVERITY WEIGHTS — READ FROM scores.json, NOT DEFINED HERE.
#
# Do not keep a local SEV3/SEV1 set here. A second copy of reduce.sh's `sev()` map kept identical by
# hand is checked by nothing, and references/severity.md would then be a third statement of the same
# fact — the only one a reader sees — free to document a question Low while both code maps omit it and
# the reducer's default scores it Medium.
#
# So the weights are restated nowhere. references/severity.md is the single source, reduce.sh
# parses it, and reduce.sh publishes the parsed map in scores.json under `severity`. This file reads
# that. The weight labelling a finding is therefore the same byte the published score was weighted with
# — not a copy that agrees today. It also brings severity under the rule this file already follows for
# every other number: "Every number in the output is copied from scores.json / results.jsonl."
#
# Populated once in main(), after the map has been validated. Empty until then, and sev_of() refuses
# rather than defaulting: a default weight here would be a report ranking findings by a severity the
# score did not use, which is exactly the failure this design prevents.
# ---------------------------------------------------------------------------
_SEV = {}

PILLARS = [
    ("operational-excellence", "Operational Excellence"),
    ("security", "Security"),
    ("reliability", "Reliability"),
    ("performance-efficiency", "Performance Efficiency"),
    # "(hygiene)" on the DISPLAY NAME, not just in prose somewhere else on the page, so the qualifier
    # travels with the score wherever this tuple's name is used — the executive-summary pillar table,
    # this pillar's own section heading, and the governance grouping. A cluster that is 100% Spot and
    # 100% Graviton and one that is 33% Spot with an unsupported instance family can both score
    # Cost 50 / Poor / High risk with no visible reason a reader could tell those two clusters apart
    # from the score alone. See _cost_posture_note() for the measured Spot/Graviton/upgrade-policy facts that
    # sit beside every rendering of this score.
    ("cost-optimization", "Cost Optimization (hygiene)"),
]

# ---------------------------------------------------------------------------
# WHY EACH GOVERNANCE QUESTION WAS NOT ASSESSED. ADD AN ENTRY WHEN YOU ADD A GOVERNANCE QUESTION —
# an id missing from this table renders in an "unclassified" group that names it, rather than
# inheriting a reason nobody checked.
#
# Do not give ONE reason for all of them, such as "no signal in `aws` or `kubectl` output": the report
# itself refutes it. `rel-15` (LoadBalancer services) sits here while `lens-9` scores from
# `services.json`; `rel-17` (CoreDNS/ExternalDNS) sits here while `ope-16` measures the coredns add-on
# and `ope-2` matches external-dns over `deployments.json`; `rel-14` (ingress replicas) sits here while
# `rel-7` computes `.spec.replicas>1` over the same file; and `sec-22`/`sec-23` are not unobservable in
# `aws` output, since `aws efs describe-file-systems` returns `Encrypted` directly — calling that an
# observability impossibility hides a collection choice. The distinction matters to a reader
# who has to record either "not verifiable by automated review" or "not verified": those are different
# audit lines, and only one of them is true for any given question.
#
#   process        Nothing in the collected output states the answer: it is a fact about how a team
#                  works, about the wider environment, or a judgement cluster state cannot settle.
#                  Where a PARTIAL signal exists, the note says so — a signal that can only prove a
#                  yes is not an answer.
#   not-collected  A documented AWS or Kubernetes API returns the answer and this skill does not call
#                  it. The call is named, so it can be added.
#   collected      The files this run already wrote contain the answer, and for most of these a
#                  neighbouring question is scored from the same field. Left unmeasured by
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
    ("collected", "Observable from data already collected",
     "The files this run already wrote contain the answer, and for most of these another question in "
     "this report is scored from the same field. They are not measured, by choice, so "
     "treat them as <em>not verified</em>, not as unverifiable."),
    ("unclassified", "Reason not recorded",
     "These ids are missing from <code>GOV_UNASSESSED</code> in <code>render-report.py</code>. The "
     "report will not invent a reason for them: add one there when you add the question."),
]

# ---------------------------------------------------------------------------
# Why a question came back `na`. One state in results.jsonl, three completely different situations —
# and describing all three as coverage that better observation would improve is wrong for two of them:
#
#   STRUCTURAL   the question can NEVER apply to this cluster as built. fargate-1/2/4 on an EC2
#                cluster, a DaemonSet question on Fargate, an instance-type question on serverless
#                compute, a retired question, one deduplicated against another. No amount of extra
#                collection makes these measurable, so counting them as missing coverage
#                permanently caps a pillar: four of Operational Excellence's `na`s are structural on
#                EVERY non-Fargate cluster, so its raw coverage can never exceed 14/18 = 77%. Counted
#                as missing coverage, they would fire the "thin evidence, provisional,
#                not a verdict" marker on clusters whose evidence is not thin at all — including
#                over a genuinely broken score, which the marker would then pre-discount for the reader.
#   NO_SUBJECT   the question applies, but there is nothing of that kind on the cluster to look at:
#                0 workload Deployments, no CronJobs, no LoadBalancer Services. Deploy one and it becomes
#                measurable. Nothing was unobservable — there was nothing there. Saying "too little
#                of this cluster is observable" about an empty cluster is simply the wrong statement.
#   UNOBSERVED   anything else: the honest default. A reason this table does not recognise must not
#                be silently promoted into either of the two categories above.
#
# Matched against the scorer's own `na~...` reason text, which is already carried in `detail`.
#
# THE KEYWORD SNIFF IS A HEURISTIC AND IT IS SUBSTRING-WIDE, so `NA_NOT_ASSESSED` outranks it. A
# structural `na` is SUBTRACTED from the thin-evidence denominator below (`eff_tot = max(tot -
# n_struct, appl)`), which is the whole reason the classification exists — so a COLLECTION-GAP `na`
# misread as structural does not merely mislabel one question, it silently suppresses the
# "thin evidence" caveat on the pillar that question sits in. The sniff cannot tell the two apart:
# `lens-11`'s gap detail names Fargate in order to explain when the gap is NOT a gap ("On a
# cluster with no EC2 nodes that is correct and complete ... On a cluster that lists EC2 nodes it means
# their instances are missing from the collection or already gone"), and `rel-1`'s gap arm is about Fargate profiles.
# `rel-1`'s gap arm says "compute profiles" rather than "Fargate profiles", but relying on that wording
# would be a fix in the wrong file: the next author to write the clearer sentence would reintroduce the
# defect, silently, with no gate able to see it.
#
# So a detail that OPENS with `NOT ASSESSED` (the phrase the scorers already use for exactly this —
# `lens-12`, `lens-13`, `rel-1`'s gap arm) is a collection gap by the author's own declaration, and
# no keyword can promote it to structural. It stays `unobserved`, in the denominator, where it keeps
# the caveat honest. Anchored at the start deliberately: `sec-28` says "mTLS mode and configuration
# are NOT assessed" mid-sentence as ordinary prose, and a substring test would swallow every
# structural detail that happens to explain itself the same way.
#
# `lens-11` cannot be classified from its text: one `na` sentence, opening "no EC2 instance that still exists
# was collected" and naming Fargate later, covers both shapes. With no EC2 nodes it is structural. On a cluster
# whose nodes include EC2 nodes (every instance listed terminated or shutting down, which `collect.sh`'s canary
# accepts) it is a collection gap, so build() passes `ec2` (some node is neither Fargate nor hybrid) and
# na_reason() files that opening as `unobserved` then: in the thin-evidence denominator, badge "Not observed".
NA_NOT_ASSESSED = re.compile(r"^NOT ASSESSED\b", re.I)
# `cannot be deployed` and `every EC2 node is an Auto Mode node` are the EKS Auto Mode family, added
# for `ope-10`: "auto mode manages VPC CNI IP and ENI allocation itself: every EC2 node is an Auto
# Mode node ... so there is no VPC CNI DaemonSet for a cni-metrics-helper to instrument and it cannot
# be deployed". That is a textbook structural exclusion — the object the question asks about does not
# exist on a cluster built this way and no extra collection conjures one — and without these phrases it
# lands in `unobserved` on EVERY Auto Mode cluster, inflating that pillar's thin-evidence denominator by one.
# It does NOT catch `perf-6`'s Auto Mode `na`, and must not: that detail says the answer "lives in the
# NodePool spec ... and this review does not collect it", which is a collection gap and belongs in the
# denominator. The two are only distinguishable from the prose, which is why this stays a phrase list
# and not a rule about Auto Mode.
# DELIBERATELY NOT EXTENDED FOR HYBRID NODES. The scorers' shared `hyna()` arm opens
# with "no EC2 nodes", which the existing alternative already matches, so every hybrid `na` that IS
# structural is classified correctly with no new phrase. Adding `hybrid node` would buy exactly one arm
# (`sec-4`) and cost two hazards: `re.I` plus a substring match means `hyx()`'s own disclosure text --
# which is APPENDED to graded details and to `na` details alike -- would promote anything it touched,
# and any future `na` that merely MENTIONS hybrid nodes while being a genuine collection gap would be
# silently subtracted from the thin-evidence denominator. `sec-4` is a collection gap (Cilium and Calico
# do enforce NetworkPolicy on hybrid nodes; this review does not collect them) and opens with
# `NOT ASSESSED`, which NA_NOT_ASSESSED routes to `unobserved` where it belongs.
NA_STRUCTURAL = re.compile(r"fargate|impossible|serverless compute|no EC2 nodes"
                           r"|deduplicat|same signal as|^retired\b"
                           r"|cannot be deployed|every EC2 node is an Auto Mode node", re.I)
NA_NO_SUBJECT = re.compile(r"^(?:no\b|0/0\b)", re.I)


def na_reason(detail, ec2=False):
    """Classify one `na` detail as 'structural', 'no_subject' or 'unobserved' (`ec2`: the cluster has EC2 nodes).

    Order is load-bearing: an explicit `NOT ASSESSED` opening outranks the keyword sniff, because the
    author of the detail knows whether more collection would answer the question and a substring
    match does not. See the comment above NA_NOT_ASSESSED for what getting it wrong silently costs.
    """
    d = (detail or "").strip()
    if NA_NOT_ASSESSED.match(d) or (ec2 and d.startswith("no EC2 instance that still exists was collected")):
        return "unobserved"
    if NA_STRUCTURAL.search(d):
        return "structural"
    if NA_NO_SUBJECT.match(d):
        return "no_subject"
    return "unobserved"


_WINDOWS_SCOPE = re.compile(r"supports Linux nodes only|attached only to Windows nodes")


def _unobs_label(detail):
    """Result-column badge for an `unobserved` na. A `NOT ASSESSED` detail that excludes a Windows
    population (the standard "this skill supports Linux nodes only" disclosure) was collected and
    observed -- the skill declines to assess it -- so "Not observed" would be false of it and its
    badge is "Not assessed". Every other `unobserved` na (ECR scan settings no repository matched, a
    regional NAT gateway with no succeeded address naming an AZ, a CNI this review does not collect) is one the
    collected data could not answer, and keeps "Not observed"."""
    d = (detail or "").strip()
    return "Not assessed" if NA_NOT_ASSESSED.match(d) and _WINDOWS_SCOPE.search(d) else "Not observed"


def na_split(recs, ec2=False):
    """(structural, no_subject, unobserved) counts over the `na` records given."""
    kinds = [na_reason(r.get("detail"), ec2) for r in recs if r.get("state") == "na"]
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
    try:
        return _SEV[qid]
    except KeyError:
        # Unreachable through main(): the guards there refuse a scores.json whose `severity` map does
        # not cover every id in results.jsonl, and every caller passes a record's own id. Kept as a
        # refusal rather than a `2` default so that if this file is ever driven another way, the failure
        # is a message naming the question rather than a silently mis-ranked report.
        raise SystemExit(
            f"render-report.py: no severity weight for {qid!r}. The weights come from scores.json's "
            f"`severity` map, which reduce.sh builds from references/severity.md; this id is not in it. "
            f"Re-run assets/reduce.sh over this work dir.")


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
        # are all listed in the pillar section below. A Reliability pillar that answered 10 of its
        # 23 questions reaches this branch — reduce.sh withholds at `applicable*2 < total`, and
        # 10*2 < 23 — and "Not assessed" here would tell the reader none of them had been.
        return ("inactive", "No band published")
    return (("success", "Low") if score >= 80 else
            ("warning", "Medium") if score >= 60 else ("error", "High"))


# Codepoints that render as something other than what they are, or as nothing at all. Cluster data is
# operator-controlled text: a namespace, a ClusterRole, a node name or a tag value reaches this report
# verbatim, and `html.escape` neutralises only `& < > " '`. Everything below survives it untouched.
#
#   U+202A-202E, U+2066-2069, U+200E, U+200F, U+061C   bidi embedding/override/isolate. A name carrying
#       RIGHT-TO-LEFT OVERRIDE renders in a different character order than it stores, so a resource list
#       entry can be made to READ differently from the value it names — the report's whole job is naming
#       objects accurately, so a silently-reordered name is a correctness defect, not a cosmetic one.
#   U+2028, U+2029, U+0085   line/paragraph separators. Invisible in HTML, and Python's `splitlines()`
#       treats them as line breaks (see the JSONL loader).
#   C0 except TAB/LF, U+007F, C1   control characters. A raw BEL rings a terminal when the HTML is
#       catted; the rest are invisible and can pad a name to hide its tail.
#
# Rendered as a visible `\uXXXX` escape rather than dropped: dropping would ALSO make the display differ
# from the stored value, which is the defect this prevents. The reader sees that something is there.
_UNSAFE_CHARS = re.compile(
    "["
    "\u0000-\u0008\u000b\u000c\u000e-\u001f"   # C0 controls, keeping TAB and LF
    "\u007f-\u009f"                             # DEL and the C1 block (U+0085 NEL included)
    "\u2028\u2029"                               # LINE SEPARATOR, PARAGRAPH SEPARATOR
    "\u061c\u200e\u200f"                         # ALM, LRM, RLM
    "\u202a-\u202e\u2066-\u2069"                 # bidi embeddings/overrides and isolates
    "]")


def e(s):
    return html.escape(_UNSAFE_CHARS.sub(lambda m: "\\u%04x" % ord(m.group()), str(s)), quote=True)


# ---------------------------------------------------------------------------
# Collection provenance
# ---------------------------------------------------------------------------
# `assets/collect.sh` writes this at the end of a successful collection and `assets/reduce.sh` asserts
# it before publishing a score; this file asserts it before publishing a report. The full argument, and
# the reason a collection timestamp inside it does not break the byte-identical-across-two-
# runs requirement, live in collect.sh where it is written. Two things it buys this file specifically:
#
#  1. "Data collected" is a fact the COLLECTOR recorded, not the results.jsonl mtime. An mtime is a
#     fact about a filesystem: `cp -r`, `tar -x`, `git checkout`, a re-score or a bare `touch` all
#     rewrite it, so a work dir that moved between machines would publish a collection date nobody
#     collected on — under a masthead that says "Scores describe configuration at collection time".
#     A single `touch -t 209901011230 results.jsonl` would date the report 2099.
#  2. Provenance. This renderer does not re-derive questions' resource lists from the collected JSON:
#     that would be a second implementation of the checks. Without it, nothing incidental compares
#     scores.json with its data, so a scores.json a step behind the collected files would render with
#     no printed disagreement. The link is made deliberately instead: the digest over the collected
#     files is compared before anything is published.
FINGERPRINT = ".collection.json"


def collection_digest(work, names):
    """(digest, {name: sha256}) over the collected files `names` — the fingerprint's own list.

    Byte-compatible with the two bash implementations (assets/collect.sh, assets/reduce.sh) — for
    each name in LC_ALL=C order, the line
    `"<name>  <sha256 hex>\\n"`; a listed name that is no longer a readable file contributes NO line, so
    the digest cannot match and the caller can report it as removed. The digest is the sha256 of that
    concatenation. If you change this, change all three.

    An ALLOWLIST of what the collector wrote, not a glob of the work dir. The full argument is in
    assets/collect.sh; the short version is that a caller may legitimately create a file in the work dir
    — `reduce.sh "$WORK" > "$WORK/out.json"` creates that target before reduce.sh even runs — and a
    glob-based digest would refuse those correct runs. It also means this function never has to reason about
    `pathlib.glob("*.json")` matching dot-files (it does, unlike a bash `*` glob), because it does not
    glob at all.
    """
    files = {}
    for name in sorted(names):
        p = work / name
        # Guarded, for the same reason as every other stat on this path: a collected file that is a
        # symlink to an unstattable target makes `is_file()` raise PermissionError here. Refused rather
        # than skipped -- skipping would drop the file from the digest and surface as a FINGERPRINT
        # MISMATCH, which is a true statement with a misleading diagnosis. This says which file and why,
        # matching the read's own refusal three lines down.
        try:
            if not p.is_file():
                continue
        except OSError as exc:
            sys.exit(f"render-report: could not examine {p} ({exc}) — refusing to fingerprint a work "
                     f"dir holding a collected file this process cannot stat")
        try:
            files[name] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError as exc:
            sys.exit(f"render-report: could not read {p} ({exc}) — refusing to render a report from "
                     f"data the scorers could not have read either")
    blob = "".join(f"{n}  {h}\n" for n, h in sorted(files.items()))
    return hashlib.sha256(blob.encode()).hexdigest(), files


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load(work):
    work = pathlib.Path(work)

    # Unchecked, a work-dir argument that names a FILE would fall through to the generic "required file
    # missing: <work>/scores.json" refusal below — true, but the wrong diagnosis: the problem is the
    # argument itself, not any one file under it. Checked before anything is read.
    # Not `work.exists()`: that is itself an os.stat(), so a work dir under a mode-000 PARENT would raise
    # a raw PermissionError out of THIS guard — the same stat-ordering hazard as the two sites below.
    # os.path.isfile() answers False for any path it cannot stat rather than raising, and "cannot stat
    # it" is not "it is a file", so the wrong branch is never taken: an unreadable path falls through to
    # the per-file refusals in j(), which name the file and the errno.
    if os.path.isfile(work):
        sys.exit(f"render-report: {work} is a file, not a directory — pass the work directory that "
                 f"contains scores.json and results.jsonl")

    def j(name, default=None):
        p = work / name
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            # Not gated by `if not p.exists()`: that call is an os.stat() too, and on a work dir at
            # mode 000 it raises a raw PermissionError out of the GUARD instead of reaching the
            # refusal immediately below it. Letting the read raise and sorting the outcomes out
            # here is the same ordering the `-o` parent check in main() uses; every arm here
            # ends in a `render-report:` line, which a bare `exists()` could not.
            if default is None:
                sys.exit(f"render-report: required file missing: {p}")
            return default
        except OSError as exc:
            # A file being THERE is not a file being READABLE. A mode-000 or otherwise-unreadable
            # collection file would otherwise raise a raw PermissionError traceback out of load(), the
            # one failure mode in this loader without the clean `render-report: ...`
            # refusal every neighbouring guard gives. This arm also takes IsADirectoryError and
            # NotADirectoryError, so a directory named scores.json is refused here too.
            sys.exit(f"render-report: could not read {p} ({exc}) — refusing to render a report from "
                     f"data the scorers could not have read either")
        except UnicodeDecodeError as exc:
            # NOT an OSError — it is a ValueError — so the handler above does not catch it, and a single
            # non-UTF-8 byte in ANY collected file would come out as a raw traceback. This is the widest
            # of the three sites that need this arm: `j()` reads every collected file and `scores.json`.
            sys.exit(f"render-report: {p} is not valid UTF-8 ({exc}) — refusing to render a report "
                     f"from data that cannot be decoded")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            sys.exit(f"render-report: {p} is not valid JSON ({exc}) — refusing to render a "
                     f"report from data the scorers could not have read either")

    # Shape helpers. A guard on a MISSING key alone misses a present-but-wrong value, so
    # `{"items": null}`, `{"cluster": "oops"}`, `"pillars": {...}` and `scores.json` as `[]` would
    # all produce raw tracebacks instead of the graceful refusal the rest of this loader gives.
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
    # `need_list`, NOT `opt_list`: `.pillars` is not an optional API field, it is the body of the score
    # contract, and `reduce.sh` emits it on every successful run. Read as optional, a `"pillars": null`
    # would be coerced to `[]` and render a half-megabyte report with no pillar table at exit 0 — the
    # renderer publishing a document the reducer would have refused outright.
    scores["pillars"] = need_list(scores.get("pillars"), "scores.json .pillars")
    for i, pil in enumerate(scores["pillars"]):
        need_obj(pil, f"scores.json .pillars[{i}]")
    # ASSIGNED BACK, not just validated. Coercing a null/absent `.governance` to an empty dict, checking
    # THAT and throwing it away would pass the guard and leave `scores["governance"]` still None one
    # function later, where `g.get("score")` raises AttributeError mid-build.
    #
    # `is None`, NOT `or {}`, AND THE DIFFERENCE IS MEASURABLE. `or {}` fires on any FALSY value, so
    # `"governance": []`, `0`, `false` and `""` would all be silently accepted and rendered at exit 0,
    # while only a truthy non-dict such as `42` is refused — an accidental split that lets four malformed
    # shapes through the guard whose whole job is to reject malformed shapes. Absent or null is the one
    # tolerance this key is meant to have (it means "no governance block", which the Governance section
    # renders as Not Assessed); every other non-dict is a malformed scores.json and is refused, for the
    # same reason `need_list` above refuses a null `.pillars`: a malformed file must not be read as an
    # empty one.
    _gov = scores.get("governance")
    scores["governance"] = need_obj({} if _gov is None else _gov, "scores.json .governance")

    # Non-finite and out-of-range scores render as confident nonsense: 200 would become
    # "200 / 100 · Excellent · Low risk", and NaN would draw a FULL-WIDTH bar beside a red "Poor / High"
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
    # above, so it needs the same guard as every one of THOSE: unguarded, the same class of bug
    # reaches the page — 250 would render "250 / 100" and NaN would draw a full-width
    # bar, both at exit 0.
    sane_score((scores.get("governance") or {}).get("score"), "scores.json .governance.score")

    # The question counts reach more than e(), where a non-integer would render as harmless
    # text. They also feed arithmetic — the coverage denominator adds the pillar's process
    # questions, and the thin-evidence basis subtracts its structurally-inapplicable ones — so a
    # string here would be a TypeError mid-render. Same treatment as sane_score: rejected at the
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

    # ---- severity weights: read, never restated -------------------------------------------------
    # Shape first, coverage after results.jsonl is parsed. Same treatment as the `liveness` block: a
    # scores.json without this came from a reducer that does not publish the map, and rendering anyway
    # would mean guessing the weights the score was computed with — which is precisely
    # the drift reading the map prevents. No default, at either end.
    sev_map = scores.get("severity")
    if not isinstance(sev_map, dict) or not sev_map:
        sys.exit("render-report: scores.json has no `severity` map. The report's Severity column and the "
                 "Immediate/Short-term/Strategic ordering are taken from the weights the score was "
                 "computed with, and this file keeps no copy of them. Either this scores.json "
                 "was produced by a reducer that does not publish that map, "
                 "or it was hand-assembled. Re-run assets/reduce.sh and render again.")
    # The `(1, 2, 3)` here is a RANGE CHECK, not the tier->number mapping, and it cannot police that
    # mapping: severity.md owns which TIER a question is in, but what a tier is WORTH is a constant that
    # also lives in reduce.sh's parser and in prose in severity.md and SKILL.md. Changing reduce.sh's
    # `tier = 3` to `tier = 1` moves every score and passes this guard, because 1 is still legal. Those
    # four copies are edited together or not at all; see SKILL.md Step 7.
    bad_w = sorted(f"{k}={v!r}" for k, v in sev_map.items()
                   if isinstance(v, bool) or not isinstance(v, int) or v not in (1, 2, 3))
    if bad_w:
        sys.exit("render-report: scores.json .severity holds weight(s) that are not 1, 2 or 3: "
                 + ", ".join(bad_w[:10])
                 + (f" and {len(bad_w) - 10} more" if len(bad_w) > 10 else "")
                 + " — the weight comes from a `### High`/`### Medium`/`### Low` heading in "
                   "references/severity.md, so it can only be 3, 2 or 1. Re-run assets/reduce.sh.")
    _SEV.clear()
    _SEV.update(sev_map)

    results = []
    rp = work / "results.jsonl"
    try:
        rp_text = rp.read_text(encoding="utf-8")
    except FileNotFoundError:         # not exists(): that raises on an unstattable symlink
        sys.exit(f"render-report: required file missing: {rp}")
    except OSError as exc:            # same point as j(): exists() is not readable()
        sys.exit(f"render-report: could not read {rp} ({exc})")
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError is a ValueError, not an OSError, so the handler above does not see it and a
        # non-UTF-8 byte would escape as a raw traceback. Same guard as `.collection.json`'s reader.
        sys.exit(f"render-report: {rp} is not valid UTF-8 ({exc}) — refusing to render a report from "
                 f"records this file cannot even be decoded from")
    # `split("\n")`, NOT `splitlines()`. This file is JSON Lines: the ONLY record separator is `\n`,
    # written by the scorers' `>> results.jsonl`. `splitlines()` additionally breaks on U+2028 (LINE
    # SEPARATOR), U+2029 (PARAGRAPH SEPARATOR) and U+0085 (NEL) — and `jq --arg` escapes only C0
    # controls, so those three travel RAW inside a JSON string value. A Kubernetes namespace or
    # StorageClass name carrying one would therefore split a record mid-string and kill the whole run
    # with "line N is not valid JSON (Unterminated string)" under the advice "re-run them rather than
    # render this", which no re-run can satisfy — one object name would make the report permanently
    # unrenderable. The scorers emit object names, so ordinary cluster data can reach this.
    for n, line in enumerate(rp_text.split("\n"), 1):
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
        # the pillar sort below is a bare `r["id"]`, not `.get("id")` — so a record missing one would raise
        # a raw `KeyError` instead of the `render-report: …` refusal every other malformed-input path
        # in this file gives. `reduce.sh` has the same presence/emptiness check (MISSINGFIELDS; this adds type), matched
        # here in wording so the two read as one system, since a results.jsonl that never went through
        # the reducer must refuse the same way one that did would have.
        # PRESENCE, NON-EMPTINESS, AND TYPE. The first two are not enough: every one of these four
        # fields is a STRING at every point of use -- `", ".join(ids)`, `sorted(ids)`, dict keys,
        # `== "governance"`, `STATE_UI[state]`. So `"id": 7`, present and truthy, would sail straight
        # past a presence check: it would reach the aggregate formatter in check_prose_coverage() -- the
        # first code in the program that actually requires a str -- as `TypeError: sequence item 0:
        # expected str instance, int found`, and a MIXED int/str set would raise out of `sorted()`.
        # `1.5` and `true` do the same. Checked HERE, not with a `str()` at the point of formatting:
        # coercing would silence the traceback and then render a report keyed on `7`, presenting a
        # wrong-shaped value as a question id. A loader whose entire purpose is to reject wrong-shaped
        # values must type-check the one field the whole report is indexed by.
        missing = [f for f in ("pillar", "id", "track", "state")
                   if not isinstance(rec.get(f), str) or not rec.get(f)]
        if missing:
            sys.exit(f"render-report: {rp} line {n} has record(s) with a bad required field -- every "
                     f"record must carry pillar, id, track and state as non-empty strings -- "
                     f"missing, empty or not a string: {','.join(missing)} -- {json.dumps(rec)[:80]}")
        # `track` IS AN ENUM TOO, for the same reason and with a worse symptom. Every consumer tests it by
        # equality — `is_gov` two lines down, and the two table loops that select `measured` — so a record
        # whose track is `process`, `Measured` or `measured ` matches NEITHER and DISAPPEARS FROM THE
        # REPORT ENTIRELY: unchecked, a retracked question's row is simply gone from its table, at exit 0
        # with no ERROR block. It would also silently exempt itself from check_prose_coverage()'s
        # `track == "measured"` predicate, and silently narrow which states are legal here, because
        # `is_gov` goes False and takes `unknown` out of the legal set.
        #
        # reduce.sh already gates this ("legal tracks: measured governance"), so a work dir it produced
        # cannot carry a third value — which is exactly why this belongs here: a renderer must not accept
        # what the reducer refuses, and a hand-edited or hand-merged results.jsonl is the input this whole
        # loader exists to distrust. Same reasoning as the required-field check above it.
        if rec["track"] not in ("measured", "governance"):
            sys.exit(f"render-report: {rp} line {n} has illegal track {rec['track']!r} for id "
                     f"{rec['id']!r} -- legal: governance, measured -- refusing to render a record that "
                     f"would silently vanish from the report, since every consumer selects a track by "
                     f"equality")
        # `state` is an enum, not free text. An unrecognised value — a typo, or a future state this
        # renderer predates — would otherwise fall through a STATE_UI.get(state, ("inactive", state)) and
        # render in the identical muted grey as a legitimate `na`, with no sign anything was wrong.
        # `unknown` is legal ONLY on the governance track (the state every `g` call emits) — same
        # exception reduce.sh's own BADSTATE gate makes.
        is_gov = rec.get("track") == "governance"
        legal_states = set(STATE_UI) | ({"unknown"} if is_gov else set())
        if rec.get("state") not in legal_states:
            sys.exit(f"render-report: {rp} line {n} has illegal state {rec.get('state')!r} for id "
                     f"{rec.get('id')!r} -- legal: {', '.join(sorted(STATE_UI))}"
                     + (", unknown" if is_gov else "")
                     + " -- refusing to render a state this report has no styling for")
        results.append(rec)

    # A results.jsonl with no records is not a cluster with no findings — it is a scoring run that did
    # not happen, or one whose output was truncated to nothing. `reduce.sh` already refuses this input
    # at rc=1; a renderer that accepted it would publish a report whose hero reads
    # "60 / 100 · Needs improvement · ⚠ Medium risk" directly beneath its own disclosure "Of 0
    # questions: 0 scored" — a headline score computed from no measurements at all, which is the single
    # worst thing this file can emit. The two consumers of the same file must agree about whether it is
    # scorable.
    if not results:
        sys.exit(f"render-report: {rp} contains no records — every question is missing, so there is "
                 f"nothing to report on. A score rendered from zero measurements is not a low score, "
                 f"it is no score; reduce.sh refuses this same file. Re-run the scorer blocks.")

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

    # Coverage half of the severity guard above. Reachable the same way the duplicate check is — a
    # stale scores.json beside a freshly re-scored results.jsonl — and it is the case that matters most,
    # because a question added to the scorers but not to references/severity.md would otherwise render
    # with a made-up severity. reduce.sh refuses that combination outright; the renderer must not depend
    # on having been the second step of the same run.
    unsourced = sorted({r["id"] for r in results} - set(_SEV))
    if unsourced:
        sys.exit(f"render-report: {rp} contains question(s) with no weight in scores.json .severity: "
                 + ", ".join(unsourced[:20])
                 + (f" and {len(unsourced) - 20} more" if len(unsourced) > 20 else "")
                 + " — the two files describe different question sets, so the report would label these "
                   "findings with a severity nothing assigned them. Re-run assets/reduce.sh over this "
                   "work dir (it refuses a question that references/severity.md does not document) and "
                   "render again.")

    # THE OTHER DIRECTION, present for symmetry with reduce.sh rather than to prevent a mislabelling. An
    # EXTRA id in `.severity` — one the map documents and results.jsonl does not contain — cannot corrupt
    # this report: `_SEV` is only ever read as `_SEV[qid]` for a qid that came out of results.jsonl, and as
    # `set(_SEV)` in the check above. Unguarded, an extra id would render at rc=0 with
    # byte-identical output and no complaint. It is refused anyway because reduce.sh refuses exactly this
    # input (its staleness gate), and a renderer that accepts a scores.json its own reducer would have
    # rejected is a second opinion on the score contract — which is the thing this whole block exists to
    # prevent. The guard above and this one are the two halves of ONE statement: the two files describe
    # the same question set or the report is not written.
    unscored = sorted(set(_SEV) - {r["id"] for r in results})
    if unscored:
        sys.exit(f"render-report: scores.json .severity documents weight(s) for question(s) that {rp} "
                 "does not contain: "
                 + ", ".join(unscored[:20])
                 + (f" and {len(unscored) - 20} more" if len(unscored) > 20 else "")
                 + " — the two files describe different question sets, so one of them is stale. Nothing "
                   "in the report would have been mislabelled by this (an unscored weight is never read), "
                   "but assets/reduce.sh refuses this same pairing, so accepting it here would make the "
                   "renderer a second opinion on the score contract. Re-run assets/reduce.sh over this "
                   "work dir and render again.")

    # ---- collection provenance, asserted before a single collected file is read ------------------
    # Ordered here on purpose: AFTER the scores.json and results.jsonl guards above, so those keep
    # reporting their own diagnosis (a truncated scores.json still says so, rather than being reported
    # as a provenance problem), and BEFORE the collected files below, none of which may be read on
    # trust. See collection_digest() and assets/collect.sh for the contract.
    fp_path = work / FINGERPRINT
    try:
        # UnicodeDecodeError is a ValueError, and so is JSONDecodeError: a fingerprint holding a
        # non-UTF-8 byte must produce this refusal, not a traceback out of the middle of load().
        fp = json.loads(fp_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # No `exists()` check above this try: it raises PermissionError when the fingerprint is a
        # symlink to an unstattable target. Folded into the read for the same reason as j(): one stat
        # fewer, and every outcome lands on a `render-report:` line.
        sys.exit(f"render-report: required file missing: {fp_path} — this work dir carries no record "
                 f"of having been collected, so the report has no collection time to state and no way "
                 f"to prove these files are the ones that were scored. assets/collect.sh writes it at "
                 f"the end of a successful collection; a work dir without it is either from a "
                 f"collection that REFUSED or one assembled by hand. Re-run collection.")
    except OSError as exc:
        sys.exit(f"render-report: could not read {fp_path} ({exc})")
    except ValueError as exc:
        sys.exit(f"render-report: {fp_path} is not valid JSON ({exc}) — the collection fingerprint is "
                 f"where this report's \"Data collected\" line and its provenance both come from, so a "
                 f"malformed one is not a weaker fingerprint, it is none. Re-run collection.")
    if not isinstance(fp, dict):
        sys.exit(f"render-report: {fp_path} should be a JSON object, got {type(fp).__name__} — "
                 f"refusing to render from a fingerprint of the wrong shape")
    # `files` is required, not optional, even though only the mismatch message below reads it. Two
    # reasons, and the first is the load-bearing one: reduce.sh requires it, so accepting a fingerprint
    # the reducer refuses would put the two asserters into disagreement about the same file — a
    # fingerprint put through `jq del(.files)` is refused by reduce.sh, and must be refused here too. The
    # second is that without it a mismatch can only be reported as "something moved", which is the
    # absent-vs-empty confusion in a new place: absent and empty must not be indistinguishable.
    if not isinstance(fp.get("files"), dict):
        sys.exit(f"render-report: {fp_path} has no `files` object — a fingerprint written by "
                 f"assets/collect.sh always carries one, so this file came from something else. It is "
                 f"what lets a mismatch name WHICH collected file moved instead of only that one did.")
    # The stamp is presented to the reader as this report's provenance, so it is validated as a shape
    # rather than reformatted hopefully: an unparseable one would otherwise reach the masthead verbatim
    # and be read as a collection time. One UTC ISO-8601 instant, exactly as collect.sh writes it.
    stamp = fp.get("collected_at")
    if not isinstance(stamp, str) or not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", stamp):
        sys.exit(f"render-report: {fp_path} has collected_at {stamp!r} — expected one UTC ISO-8601 "
                 f"instant of the form 2026-01-31T12:30:00Z, which is what assets/collect.sh writes. "
                 f"Refusing to present an unreadable timestamp as the collection time.")
    collected = f"{stamp[:10]} {stamp[11:16]} UTC"
    want = fp.get("digest")
    if not isinstance(want, str) or not re.match(r"^[0-9a-f]{64}$", want):
        sys.exit(f"render-report: {fp_path} has digest {want!r} — expected a 64-character hex sha256. "
                 f"Refusing to render a report whose data cannot be checked against it.")
    was = fp["files"]                          # guaranteed a dict by the shape check above
    have, now_files = collection_digest(work, was)
    if want != have:
        # No "added" arm: the recomputation walks the RECORDED names, so a file that merely appeared in
        # the work dir is not part of this comparison. That is the allowlist's whole point — see
        # collection_digest().
        changed = []
        for name in sorted(was):
            if name not in now_files:
                changed.append(f"{name}: removed since collection")
            elif was[name] != now_files[name]:
                changed.append(f"{name}: modified since collection")
        detail = ("; ".join(changed[:10]) + (f" and {len(changed) - 10} more"
                                             if len(changed) > 10 else "")) if changed else \
            (f"the digest recorded in {fp_path} does not match the files that same file lists, so the "
             f"fingerprint has been altered rather than the collected data")
        sys.exit(f"render-report: {work} does not match its own collection fingerprint — {detail}. "
                 f"Every finding below was answered from these files as they were at collection time, "
                 f"so rendering the current ones would publish one cluster state's score under another "
                 f"state's evidence. Re-run collection, re-score all five pillars, and re-reduce.")

    # No bulk slurp of every collected file here. The scorers name the objects each check looked at
    # themselves (`rl` lines -> `_scorer_resources`), so nothing in this file needs every collected
    # file, and no Python code re-derives what a check counted.
    # The six collections the report itself needs are loaded individually below, via `j()`.
    return {
        "scores": scores,
        "results": results,
        # id -> record, for the evidence lists the SCORERS emit (see `_scorer_resources`). Built
        # here rather than scanned per panel because a question renders its panel twice (Top
        # priorities and its pillar table) and the duplicate-id refusal above has already
        # established that this mapping loses nothing.
        "by_id": {r["id"]: r for r in results},
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


# Defects in the renderer's OWN INPUTS — the reference files and SKILL.md — as opposed to
# contradictions between a score and a resource list (DISAGREEMENTS, further down). Both lists are
# rendered as a banner at the top of the report AND make main() exit non-zero, because every entry
# means the customer's report is missing text the skill's own source files say it must carry, and a
# warning on stderr alone is invisible to everyone who only ever sees the HTML.
PROSE_DEFECTS = []          # (reference file, question id, what went wrong)
PRELUDE_SHADOW = []        # (reference file, question id, prelude name the panel cannot print)
SKILL_BLOCK_DEFECTS = []    # (marker name, what went wrong)


def _strip_quote_markers(text):
    """Remove the leading `>` from EVERY line of a markdown blockquote, not just the first.

    The rationale regex consumes the opening `>` and nothing else, so a rationale authored as a
    multi-line blockquote — the correct style for anything longer than one line — would keep a marker
    at every wrap point and print them mid-sentence in a customer-facing report: "…Enabling it >
    wraps the data key with a customer-managed KMS key…". Every multi-line rationale and remediation
    note would be exposed, and the number would only grow as rationales get longer.

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


# THREE PATHS FROM OUTSIDE THIS FILE CARRY HUMAN-AUTHORED ENGLISH INTO A CUSTOMER'S REPORT, and the rule
# below governs all three. This file's own string literals are a fourth path, and the check below does not
# scan them. Getting that inventory wrong leaves the guard blind to a whole path, so it is written out first:
#   1. question_prose()  -- each question's `title`, `rationale`, `remediation` and `source`.
#   2. skill_blocks()    -- the six marked blocks, five in SKILL.md; SCOPE-PLATFORMS, in references/workflow.md,
#                           alone is ~10 KB of prose and carries the change-log bullets, so this is not a minor path.
#   3. SCORER `detail` LITERALS -- the English inside `"state~detail"` on every `m`-family line in
#                           references/. The scorer's own words are printed as the finding.
# A bare line under a `### qid:` heading is NOT one of these: it is neither extracted nor rendered
# (verified by planting one), so the absence of a plant showing up there is a true negative.
#
#   NO RENDERED PROSE MAY NAME A CLUSTER, A REGION OR AN ACCOUNT. Not the cluster a figure was measured
#   on, not a maintainer's test cluster, not the region or the account either of them ran in. The reviewed
#   cluster's own name and region are already on the page, printed from `.collection.json`; any OTHER
#   identifier in a panel is a different cluster's identity inside a deliverable, and the reader has no way
#   to tell which one they are looking at. Say "a captured all-Auto-Mode cluster", "one real cluster", "a
#   Bottlerocket-based managed node group" -- the shape of the evidence, never its address. `<CLUSTER>`,
#   `<REGION>` and `<ACCOUNT_ID>` placeholders are the rule being followed, not exceptions to it, and an
#   AWS-managed policy ARN (`arn:aws:iam::aws:policy/...`) carries no account at all.
#
# This is a RULE OVER THE WHOLE CLASS rather than a list of literals, because catching literals one at a
# time does not converge: one cluster's name plus a few of its scores can reach the reports of clusters
# that share nothing with it, and a criterion written around that one string still lets another question
# print a different cluster's name AND its region.
#
# THE CHECK. From eks-well-architected-review/:
#
#   python3 - <<'EOF'
#   import importlib.util, re, pathlib
#   s = importlib.util.spec_from_file_location("rr", "assets/render-report.py")
#   rr = importlib.util.module_from_spec(s); s.loader.exec_module(rr)
#   PATS = {
#     "region":     r"\b[a-z]{2}(?:-gov|-iso[a-z]?)?-(?:east|west|north|south|central"
#                   r"|northeast|southeast|northwest|southwest)-\d[a-z]?\b",
#     "account":    r"(?<![\w.-])\d{12}(?![\d-])",
#     "attributed": r"(?i)\b(?:measured|verified|observed|checked|reproduced|tested)\b[^.\n]{0,40}?"
#                   r"\b(?:on|against)\b[^.\n]{0,40}?`([^`\n]+)`",
#   }
#   # No exemption list: every `attributed` hit is reported, a synthetic test-shape name included.
#   # (Rendered prose names such a shape without the "measured on `X`" idiom -- see below.)
#   def scan(where, t):
#       t = re.sub(r"<[A-Z][A-Z0-9_]*>", "PH", t or "")
#       out = []
#       for n, p in PATS.items():
#           for m in re.finditer(p, t):
#               out.append((where, n, m.group(0)[:70]))
#       return out
#   bad = {}
#   for q, v in sorted(rr.question_prose("references").items()):
#       for f in ("title", "rationale", "remediation", "source"):
#           for h in scan(f, v.get(f)): bad.setdefault(q, []).append(h)
#   for name, txt in rr.skill_blocks("SKILL.md").items():
#       for h in scan("skill-block", txt): bad.setdefault(name, []).append(h)
#   for md in sorted(pathlib.Path("references").rglob("*.md")):
#       for ln in md.read_text().splitlines():
#           if re.match(r"^(m\d*|rl|g) ", ln):
#               for h in scan("scorer:" + md.name, ln): bad.setdefault(ln.split()[1], []).append(h)
#   for q in bad: print(q, bad[q][:4])
#   print("FLAGGED:", sorted(bad) or "[]")
#   EOF
#
# THERE IS NO SHAPE EXEMPTION. `attributed` skips nothing, not even a backticked name that matches a
# synthetic test shape. SCOPE-PLATFORMS names such a shape without the idiom, so the check has nothing to
# exempt, and a shape name written in the idiom is flagged like any other attributed name. Do not add an
# exemption list read from outside the skill folder: nothing shipped could keep it current, and every
# name it listed would be one the check stops seeing.
#
# WHAT THE CHECK IS WORTH, STATED HONESTLY BECAUSE PART OF IT IS NOT COMPLETE.
#   `region` and `account` are MECHANICAL over the forms that disclose an address, and the corner cases
#     are deliberate: `\d[a-z]?` on the region tail so an AZ id (`ap-southeast-5c`) is caught, since an AZ
#     id discloses its region; `(?![\d-])` rather than `(?![\w.-])` on the account so a SENTENCE-FINAL
#     account number ("...in account 123456789012.") and an ECR registry host
#     ("123456789012.dkr.ecr...") are caught -- `(?![\w.-])` refuses a following period and would
#     miss both, which is the commonest form either takes in prose. There is deliberately no separate
#     endpoint pattern: every EKS cluster endpoint embeds its own region, so `region` already catches a
#     pasted endpoint, while an endpoint pattern would only produce false positives on
#     `ebs.csi.eks.amazonaws.com` -- a service principal, not an address.
#   `attributed` IS AN IDIOM MATCH AND IS NOT A PROOF OF ABSENCE. It fires on "measured / verified /
#     checked ... on / against `X`", which is the form such an attribution takes, and a bare
#     unattributed mention of a cluster name would slip past it. Cluster names have no
#     machine-recognisable shape, so that half is a tripwire on the idiom that produces them and nothing
#     stronger. Do not report a clean run as proof that no cluster is named.
# DEMONSTRATE IT BITES, IN EVERY PATH, every time this comment is edited. Plant `verified live against
# `x-y-z` in `ap-southeast-5`, account 210987654321` into a remediation block, into SCOPE-PLATFORMS, and
# into an `m`-line detail literal; confirm the check names all three; then remove them and confirm
# `FLAGGED: []`. THIS IS NOT OPTIONAL PROCESS -- a guard of this kind fails in exactly the way that
# returns the value meaning "clean":
#   a PLACEHOLDER predicate, such as a search for the literal string `cluster-name-or-region-regex`,
#     prints `[]` on every possible input, including a tree with a cluster name planted into `lens-6`.
#   a real predicate run over path 1 ONLY, while claiming to cover "rendered prose", prints `[]` for
#     plants in paths 2 and 3 with all three planted strings present in out.html -- and path 2 alone
#     carries the ~10 KB SCOPE-PLATFORMS block.
# A guard that cannot fail is worse than no guard, because the comment around it says `[]` means clean.
# Grepping the rendered HTML cannot settle this instead: the reviewed cluster's own name and region are
# legitimately all over it.
#
# The `**Remediation:**` marker, with an OPTIONAL parenthetical qualifier after the word —
# `**Remediation (EC2 node groups and self-managed/Karpenter fleets only):**`. Group 1 is that
# qualifier, its parentheses included, and it is PRESERVED in the rendered output: it states the scope
# of the fix, so dropping it would present a node-group-only procedure as applying to the whole
# cluster. Without the optional group, such a heading matches nothing and the question renders
# an EMPTY "How to fix" panel — the fix text simply vanishes from the
# report while the run still exits 0.
_REM_MARKER = re.compile(r"^\*\*Remediation\b[ \t]*(\([^)\n]*\))?[ \t]*:?\*\*[ \t]*:?[ \t]*", re.M)
# Deliberately looser: anything that LOOKS like the marker. Used only to decide that a body which has
# one but produced no text is a defect worth shouting about, never to extract text.
_REM_LOOSE = re.compile(r"^\*\*Remediation\b", re.M)
# A markdown thematic break: the section separator between two questions in every reference file.
_HR_RE = re.compile(r"^-{3,}\s*$")


def _remediation_body(body, start):
    """Remediation text from `start` to the first terminator that is OUTSIDE a fenced code block.

    A `---` used as a YAML document separator INSIDE a ```bash block is not the end of the
    remediation, and treating it as one silently truncates the fix: the fence never closes, the
    report prints a literal ```bash, and everything after the separator — a ConfigMap, a later step, a
    list of constraints — never reaches the reader. Nothing fails — the panel just stops mid-fix, which
    looks exactly like a short remediation. Tracking fence state here means no author has to split a
    heredoc in two to work around the parser.

    A SECTION heading (`## `) is a terminator too. Without it, a question block with no `---` after it
    and a `## ` heading on the next line would carry this loop straight through: the literal heading
    text and the whole of the next question's body would render INSIDE the first one's "How to fix"
    panel, twice in the HTML, at exit 0 with PROSE_DEFECTS empty. Stopping at `## ` bounds the damage;
    recording it as a defect is what keeps it from passing silently, because a question block that
    needs a `## ` to end it is a question block missing its
    `---`.

    Returns (text, unbalanced, bled). `unbalanced` is True when a fence was still open at the
    terminator, which is a defect in its own right: the rest of the fix would render inside a <pre>.
    `bled` is True when the block was ended by a `## ` section heading rather than by `---` or `### `.
    """
    kept, fenced, bled = [], False, False
    for ln in body[start:].split("\n"):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and (_HR_RE.match(ln) or ln.startswith("### ")):
            break
        elif not fenced and ln.startswith("## "):
            bled = True
            break
        kept.append(ln)
    return "\n".join(kept), fenced, bled


def question_prose(ref_dir):
    """Map question id -> {title, rationale, remediation, source_file}, from the reference files.

    results.jsonl carries only an id and a machine detail, so without this the report would be a
    wall of `sec-11  none  0/4 PSS labels` with no statement of what to DO about it.

    WHAT READING THEM FROM THE REFERENCE FILES DOES AND DOES NOT GUARANTEE. All four fields are parsed
    out of the same file that carries the question's scorer line, so the report can never quote a
    remediation from a different version of the skill than the one that scored the cluster, and a
    question that loses its prose shows up as an empty panel here rather than as stale text — and not
    QUIETLY: a body that carries a `**Remediation` line this parser could not read, or leaves a
    fence open, is recorded in PROSE_DEFECTS, named in a banner at the top of the report, and exits the
    run non-zero. It does
    NOT guarantee that the prose and the detection agree: co-location is not agreement, and a
    remediation can name a mechanism that its own scorer's cluster shape
    does not have. Keeping them in step is a human editing rule, and one this file cannot enforce.
    """
    prose = {}
    ref = pathlib.Path(ref_dir)
    # os.path.isdir(), not Path.is_dir(): `--references` is an operator-supplied path like `-o`, and
    # `is_dir()` raises rather than answering for a path it cannot stat — an over-long `--references`
    # (OSError [Errno 63]) and one under a mode-000 directory (PermissionError [Errno 13]) would both
    # come out as raw tracebacks, the same hazard as the `-o` block in main(). "Cannot stat it" lands on this
    # same degraded branch as "is not there", which is the behaviour already defined for a missing
    # references dir: titles go missing, PROSE_DEFECTS flags it, and the run exits non-zero. Failing
    # loudly through the existing path beats failing with a stack trace.
    #
    # AND THE DEGRADED RETURN IS RECORDED. Answering False instead of raising, unrecorded, would
    # convert an over-long `--references` from a traceback into something worse: a REPORT WITH EVERY
    # "How to fix" PANEL EMPTY -- and when SKILL.md happens to be findable beside the bogus parent there
    # would be no diagnostic at all and the run would exit 0, in silence, with a plausible-looking
    # report on disk. Two more shapes reach this same line: a missing directory, and any layout where
    # the references dir is not where it is expected. A mode-000 references directory does NOT reach it
    # -- `os.path.isdir` answers True for one, so it falls through to the zero-questions arm at the end
    # of this function, which is where its message comes from. Do not list it among the shapes this arm
    # catches.
    #
    # A plausible-looking report missing its entire remediation half is worse than a refusal, which is
    # this skill's own standard; one PROSE_DEFECTS entry puts it in the banner at the top of the report
    # and makes the run exit non-zero. This arm returns immediately, so nothing later in this function can
    # add a second entry for the same run -- which is true of THIS arm only: the per-file read arm below
    # and the zero-questions arm at the end DO both fire when every .md is unreadable, and that is
    # deliberate (one names each file, one names the total outcome).
    if not os.path.isdir(ref):
        PROSE_DEFECTS.append((str(ref), "(all questions)",
                              "the references directory could not be read as a directory, so EVERY "
                              "question lost its title and its \"How to fix\" text"))
        return prose
    for md in sorted(ref.rglob("*.md")):
        try:
            txt = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # A mode-000 or undecodable reference .md would raise a raw traceback out of this line, one
            # of the reads on the `--references` path. It must not be swallowed either: this file holds
            # question titles and remediation text, so losing it quietly ships findings with no fix text,
            # which is precisely what PROSE_DEFECTS exists to make loud. Recorded against the FILE rather
            # than a question id, because which questions it defined is now unknowable.
            PROSE_DEFECTS.append((md.name, "(whole file)",
                                  f"could not be read ({exc}), so every question defined in it has lost "
                                  f"its title and its fix text"))
            continue
        # [pre, id, title, body, id, title, body, ...]
        parts = re.split(r"^###\s+([a-z]+-\d+)\s*:\s*(.+?)\s*$", txt, flags=re.M)
        for i in range(1, len(parts) - 2, 3):
            qid, title, body = parts[i], parts[i + 1], parts[i + 2]
            if qid in prose:
                continue
            rat = re.search(r"^>\s*(.+?)(?:\n\n|\n[^>])", body, re.S | re.M)
            src = str(md.relative_to(ref))
            rem_m = _REM_MARKER.search(body)
            rem_text, unbalanced, bled = "", False, False
            if rem_m:
                rem_text, unbalanced, bled = _remediation_body(body, rem_m.end())
                rem_text = _strip_quote_markers(rem_text).strip()
                qual = rem_m.group(1)
                if qual and rem_text:
                    # The qualifier is carried into the panel rather than discarded, as its own bold
                    # lead-in. `qual` already includes its parentheses, and md_inline() escapes before
                    # it emits markup, so nothing in it can reach the HTML as live markup.
                    rem_text = f"**{qual}** {rem_text}"
            # A variant marker -- a typo, an em dash, a parenthetical this pattern still does not
            # cover -- would otherwise fail SILENTLY: the panel would render an empty "How to fix" for
            # that question, indistinguishable from a question that legitimately has none, with at most
            # a warning on stderr that nobody holding only the HTML ever sees. That is not a warning-level
            # event: a High-severity finding shipped with no fix text is the single worst thing this
            # parser can do quietly. Both of these put a red banner at the top of the report and
            # make the run exit non-zero.
            if _REM_LOOSE.search(body) and not rem_text:
                PROSE_DEFECTS.append((
                    src, qid, "has a line starting '**Remediation' that this parser could not read "
                              "as a remediation marker, so its \"How to fix\" panel is EMPTY"))
            elif unbalanced:
                PROSE_DEFECTS.append((
                    src, qid, "leaves a ``` code fence unclosed inside its remediation, so part of "
                              "the fix renders as preformatted text instead of prose"))
            elif bled:
                PROSE_DEFECTS.append((
                    src, qid, "has no `---` after its block, so its remediation ran on until the next "
                              "`## ` SECTION heading -- the heading text, and everything under it as "
                              "far as the next question, rendered inside this question's \"How to "
                              "fix\" panel. Add `---` at the end of the block"))
            prose[qid] = {
                "title": title,
                "rationale": (" ".join(_strip_quote_markers(rat.group(1)).split())
                              if rat else ""),
                "remediation": rem_text,
                "source": src,
            }
    # ---- two outcome checks, and note WHICH outcome each one measures --------------------------------
    #
    # ZERO QUESTIONS PARSED. The isdir() guard at the top catches a path that is not a directory; it does
    # NOT catch a directory that IS one and still yields nothing. At mode 000 `os.path.isdir` answers True
    # -- it stats the directory itself, which needs permission on the PARENT, not on it -- while `rglob`
    # quietly yields no entries, because Python's glob swallows the PermissionError out of scandir. It
    # also catches causes nobody enumerated: renaming every `### id:` header defeats the parser without
    # touching a permission bit.
    #
    # THIS MEASURES TITLES, NOT REMEDIATION, AND IT DOES NOT COVER EVERY SHAPE THERE IS. Two
    # shapes prove it: `references/security/` at mode 000
    # leaves 75 of 132 questions parsed, so this stays silent while 57 questions -- the whole Security
    # pillar -- lose their titles AND their entire fix text at exit 0; and a tree where no
    # `**Remediation:**` marker is readable parses all 132 titles with zero remediation, also silently.
    # `prose` being non-empty says the parser found HEADINGS. It says nothing about fix text, which is
    # what the report actually promises. Hence the second check below, and check_prose_coverage() in
    # main() for the per-id half that needs the scored list to compare against.
    if not prose:
        PROSE_DEFECTS.append((str(ref), "(all questions)",
                              "no question prose could be read from this references directory, so EVERY "
                              "question lost its title and its \"How to fix\" text"))
    # REMEDIATION COVERAGE IS NOT CHECKED HERE, because this function only knows files. Counting
    # remediation PER SOURCE FILE -- refusing any file that defines questions but yields no
    # `**Remediation:**` block, on the theory that "zero is never a healthy reading" -- is wrong in both
    # directions:
    #
    #   FALSE POSITIVE -- move sec-31 into its own reference file, an ordinary one-file refactor, and a
    #   per-file check refuses a completely healthy tree ("defines 1 question(s) and not one readable
    #   `**Remediation:**` block") with every panel present. sec-31 carries no remediation BY DESIGN,
    #   so the real precondition is not "zero is unhealthy" but "no
    #   file happens to contain only remediation-less questions" -- a property of today's file layout, not
    #   of health, and one a maintainer can break by splitting a file.
    #
    #   AND IT MISSES THE THING IT IS FOR -- demote every marker but one per file to `#### Remediation`
    #   and every file still reports a remediation, so the run exits 0 with nearly every panel gone:
    #   most of the fix text lost, silently.
    #
    # File granularity is the error. The promise this report makes is per QUESTION, so the check belongs
    # where the scored questions are known -- check_prose_coverage() in main(). See its docstring.
    return prose


def check_prose_coverage(prose, data):
    """Every question this run SCORES must have prose, and every one that renders a panel must have fix text.

    WHICH OUTCOME CARRIES THE GUARANTEE, since it is easy to measure the wrong one. What the
    report promises a reader is fix text for the questions it scored. So the assertion has to be keyed on
    QUESTION, not on file, and compared against the SCORED SET, not against whatever the parser happened
    to find -- which is why it lives here and not in question_prose(): that function is handed a
    directory, never a results file, so it can tell it parsed *some* questions but never that it parsed
    *the ones this report is about*.

    Two checks, both per-id:

    1. NO PROSE AT ALL. Where `references/security/` at mode 000 lands: 77 questions parsed, `prose`
       non-empty, every check inside question_prose() satisfied, and 57 scored questions would render with
       no title and no fix text at exit 0 with one `wrote` line for company.

    2. NO REMEDIATION on a MEASURED question whose verdict is ACTIONABLE -- `state` not in
       (`all`, `na`). One violation is a defect; no tolerance band is invented.

       THE EXCLUSIONS ARE JUSTIFIED BY THE VERDICT, NOT BY THE RENDERER. Do not justify them by saying
       `na` questions "render no 'How to fix' panel": that is
       FALSE. The panel condition in evidence_panel() is `state != "all" and p.get("remediation")`, so
       `na` DOES render one and `all` does NOT, and governance renders no panel at all (evidence_panel()
       is called only from the two `measured` table loops). A printed message resting on that premise is
       untrue of many of the ids it names -- every governance id and every one at `state == "all"` -- and
       passes only because those ids happen to carry remediation: it over-fires in the
       safe direction and nothing complains.

       The reason that IS true: `all` and `na` are non-actionable verdicts. `all` means the cluster
       already does the thing, `na` means the question does not apply -- neither owes the reader a fix.
       That is a statement about the score contract, which is what this check can actually see.

       DO NOT "FIX" THIS BY QUOTING THE RENDERER'S CONDITION BACK (`measured and state != "all"`). That
       is circular -- the renderer only shows a fix when it HAS one -- and it violates on sec-31, which has
       no fix by design, on any cluster where sec-31 is `na`. Keyed on the verdict, sec-31 needs no exemption.

    KNOWN GAP, ACCEPTED DELIBERATELY: excluding `na` means an `na` question's remediation can vanish with
    no diagnostic, and `na` DOES render a panel, so panels really do disappear -- one for every `na` id
    that carries remediation, a number that rises with how much of the cluster is `na`. Move the three
    fargate-* questions to their own file and demote every marker in it, and on a cluster where they are
    `na` the run exits 0 three panels short. This is accepted because `na` means no fix is owed, so
    the lost text is text the reader was never promised -- but it is a gap, not an absence of one.

    CLUSTER-DEPENDENT BY CONSTRUCTION, which matters when comparing two runs. THE VERDICT is a property of
    the cluster, not of the references -- both excluded verdicts, not just `na` -- so the SAME broken
    references tree gives opposite results on different clusters: demote only ope-15's remediation and a
    cluster where it is `some` is flagged rc=1, while one where it is `na` and one where it is
    `all` both exit 0 silently. Three outcomes, two different exclusion reasons, and many ids differ in
    `na`-ness between an EC2 cluster and one with no data plane. A clean run on one cluster is therefore
    NOT evidence that the references are intact for another.

    AND THE GAP IS WIDEST WHERE THE REPORT IS WEAKEST. The count tracks `na`, `na` tracks how little of the
    cluster could be assessed, so the most panels are at risk on a cluster with no data plane -- the
    one this tool scores `NOT VIABLE -- no data plane`. The cluster where the review establishes least
    is the cluster where the most fix text can go missing without a diagnostic.

    Each reported as ONE aggregate entry naming the count and the first ten ids, in the house style of the
    duplicate-id refusal in load(), rather than 57 separate ones: the operator needs the scale and a
    handle, not a list as long as the pillar. Both skipped when `prose` is empty, because the
    total-collapse arm in question_prose() has already said so in one line and 132 more would bury it.

    Every `id` here is guaranteed a non-empty `str` by load()'s required-field guard, which is what makes
    `sorted()` and `", ".join()` below safe. Presence and truthiness alone would let a
    `"id": 7` reach this formatter as a TypeError; the type check belongs there, not here.
    """
    if not prose:
        return

    def _report(ids, qid_label, why):
        shown = ", ".join(ids[:10]) + (f" and {len(ids) - 10} more" if len(ids) > 10 else "")
        PROSE_DEFECTS.append(("(references)", f"{len(ids)} {qid_label}", f"{why}: {shown}"))

    missing = sorted(r["id"] for r in data["results"] if r["id"] not in prose)
    if missing:
        _report(missing, "scored question(s)",
                "are being scored but have no question prose at all, so each renders with no title and "
                "no \"How to fix\" panel")
    # `measured` and an ACTIONABLE verdict. See the docstring for why the exclusions are keyed on the
    # verdict rather than on the renderer's own panel condition, and for what this deliberately does not
    # cover. Every id this names does render a panel when its remediation is present, which is what makes
    # the sentence below true of all of them.
    norem = sorted(r["id"] for r in data["results"]
                   if r["id"] in prose and r["track"] == "measured"
                   and r["state"] not in ("all", "na")
                   and not prose[r["id"]].get("remediation"))
    if norem:
        # "no panel", not "an empty panel": the condition is `state != "all" and p.get("remediation")`, so
        # absent remediation appends no row at all. The reader cannot tell that from a question that
        # legitimately has no fix -- which is worse than an empty panel, not better. Render with one
        # question's remediation demoted: its row is present, carries no "How to fix", and the report's
        # rows-with-a-fix count drops by one with no other visible change. NOTE the raw string
        # "How to fix" does NOT drop across that change, because the banner text contains it too -- so
        # `grep -c "How to fix"` hides this defect completely, and the `<dt>` rows are the only count that
        # measures what the reader sees. Do not take the raw count.
        #
        # THREE OUTCOMES AT THAT SITE, NOT TWO. The branch above this `elif` emits a `<dt>How to fix</dt>`
        # carrying the "Withheld. This finding contradicts itself" notice, so a question that is BOTH
        # contradicted AND missing its remediation keeps its panel and loses nothing -- the count holds.
        # This check cannot tell which case it is in: it runs before build(), so DISAGREEMENTS is
        # necessarily empty when it reads. Hence the message names both outcomes instead of asserting
        # only the commoner one.
        _report(norem, "measured question(s) with an actionable verdict",
                "carry no remediation text, so each renders no fix -- no \"How to fix\" panel at all, or, "
                "where the finding is also contradicted, the withheld notice in its place. A reader "
                "cannot tell the first from a question that legitimately has no fix, and the report "
                "promises one")


# Scorer helper -> number of collection files it reads before the jq program. DERIVED from the name,
# never tabulated.
#
# Do not make this a literal dict {"m": 1, "m2": 2, "m3": 3, "m4": 4} beside a regex `^(m[234]?)\s+`.
# `sec-4` is an `m7` line -- NetworkPolicy enforcement is opt-in on both cluster shapes and the two
# opt-ins live in different files, so its minimum evidence set is five -- and such a regex misses it:
# `sec-4` falls out of the provenance map entirely and renders with no "Data read", no "Exact command
# used" and no "Returned": the audit trail gone from a High-severity finding, at exit 0. A check that
# compares label counts against the measured question total does not catch that, because the
# report renders more panels than that total, so one missing trio hides in the slack.
#
# A table that must be edited whenever a helper is added is a drift surface. `m` reads one
# file and `mN` reads N, so the number is in the name -- read it from there and
# a future `m5`/`m8` needs no edit here.
_SCORER_RE = re.compile(r"^(m\d*)\s+([a-z]+-\d+)\s+(.*)$")
# The member-list line that sits directly above a question's scorer line. Same shape, except the file
# list is variable-length rather than implied by a helper name.
_LIST_RE = re.compile(r"^rl\s+([a-z]+-\d+)\s+(.*)$")
# Deliberately looser: anything that LOOKS like a scorer call. Used only to notice a line the strict
# pattern failed to parse, so the next arity surprise is loud instead of silent.
_SCORER_LOOSE_RE = re.compile(r"^(m\S*)\s+([a-z]+-\d+)\b")


def _helper_arity(helper):
    return 1 if helper == "m" else int(helper[1:])


# THE FIRST FENCED bash BLOCK ONLY, because that is the only text score.sh executes (score.sh:109 extracts
# it with this same awk shape). Running the prelude reader over the WHOLE file would put the printer's
# population ahead of every validator's: reduce.sh's gate, its per-file bound and score.sh all read the first
# block, while prelude_shadow() keys on MALFORMED assignments rather than on location. So a WELL-FORMED prelude
# in a second fenced block would be in the printer's population and in nobody's validator: appending a
# block containing `XX='def kyenf: false;'` leaves reduce.sh rc=0, prelude_shadow() empty and render rc=0,
# while the panel would print `def kyenf: false` and re-running the printed program flips all four
# admission questions. prelude_shadow() does not cover that case; scoping this reader to the first block does.
_SCORER_FENCE_RE = re.compile(r"^```bash$(.*?)^```$", re.M | re.S)


def _scorer_block(md_text):
    """The first fenced bash block, which is the only text score.sh runs -- or "" if there is none."""
    m = _SCORER_FENCE_RE.search(md_text)
    return m.group(1) if m else ""


def _preludes(md_text):
    """[(compiled call-site pattern, definition text)] for one reference file's scorer preludes."""
    out = []
    for _var, body in _PRELUDE_RE.findall(_scorer_block(md_text)):
        for name, params in _PRELUDE_DEF_RE.findall(body):
            pat = (r"\b%s\s*\(" % re.escape(name)) if params else (r"\b%s\b" % re.escape(name))
            out.append((re.compile(pat), body))
    return out


def _prelude_for(program, preludes):
    """The definition texts `program` actually calls, in file order, de-duplicated."""
    seen, keep = set(), []
    for call, body in preludes:
        if body not in seen and program and call.search(program):
            seen.add(body); keep.append(body)
    return "".join(keep)


def scorer_provenance(ref_dir):
    """Map question id -> {files, jq, helper}: exactly which collected JSON the detection read and
    the expression it evaluated.

    This is the audit trail. A finding that says `0/4 PSS labels` is only trustworthy if the reader
    can see it came from `namespaces.json` and check the expression that produced it. Parsed from the
    committed scorer lines, so it is the real detection, not a paraphrase of one.
    """
    prov = {}
    lists = {}
    ref = pathlib.Path(ref_dir)
    if not os.path.isdir(ref):        # non-raising, for the reason given in question_prose()
        return prov
    for md in sorted(ref.rglob("*.md")):
        try:
            _md_text = md.read_text(encoding="utf-8")
            _md_lines = _scorer_block(_md_text).splitlines()
        except (OSError, UnicodeDecodeError):
            # Same guard, same reason as question_prose(), and DELIBERATELY SILENT. A
            # `render-report: WARNING ...` line here would break the triage rule references/workflow.md tells
            # the operator to apply: that rule is POSITIONAL ("before any `wrote …` line it refused the
            # inputs and wrote no report"), such a line carries the same `render-report:` prefix as every
            # refusal, and it would land AHEAD of a `wrote` line for a run that does write a report.
            # Arguing that the read genuinely precedes the write defends the causality, not the rule the
            # operator is handed. Nothing is lost by staying silent: question_prose() walks this identical
            # file list and has already recorded a PROSE_DEFECTS entry naming this file, which prints as
            # an ERROR block AFTER `wrote` -- the correct side of the rule -- and makes the run exit
            # non-zero. One diagnostic, in the right place, instead of two in two different registers.
            continue
        _pre = _preludes(_md_text)
        for line in _md_lines:
            # `rl` lines are parsed too, and they must be: a question whose scorer emits a member list
            # renders that list as evidence, and without this the report would show the objects while the
            # "Exact command used" block printed only the VERDICT expression -- so the one part of the
            # panel a reader could not verify would be the part naming their resources. `rl` takes a variable
            # number of files before its quoted program, so the file list is taken from the head rather
            # than from a helper arity.
            lt = _LIST_RE.match(line)
            if lt:
                lqid, lrest = lt.group(1), lt.group(2)
                lhead, _, ljq = lrest.partition("'")
                _ljq = ljq.rstrip("'")
                lists[lqid] = {"list_files": lhead.split(), "list_jq": _ljq,
                               "list_prelude": _prelude_for(_ljq, _pre)}
                continue
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
            _jq = jq.rstrip("'")
            prov[qid] = {
                "files": head.split()[:_helper_arity(helper)],
                "jq": _jq,
                "helper": helper,
                # Display only. `jq` stays the raw scorer line, because name_pattern_based() classifies
                # the DETECTION and must not see a prelude's regexes.
                "jq_prelude": _prelude_for(_jq, _pre),
            }
    for qid, extra in lists.items():
        # A stray `rl` with no `m` line is a scorer-authoring bug, not something to render around: the
        # question has no verdict expression, so there is no panel to attach the list program to.
        if qid in prov:
            prov[qid].update(extra)
        else:
            sys.stderr.write(
                "render-report: WARNING `rl %s` has no matching scorer line -- its member list will "
                "render with no audit trail\n" % qid)
    return prov


# The six blocks of report content that are READ FROM THE SKILL at render time: five live in SKILL.md, and
# SCOPE-PLATFORMS lives in references/workflow.md, which SKILL.md points to (SKILL_BLOCK_SOURCES below).
#
# WHY THEY ARE READ RATHER THAN COPIED. Each of these paragraphs is a disclosure SKILL.md makes about
# what this skill did not check, or about what its own arithmetic means. A hand-maintained paraphrase
# of them in this file drifts short: one that kept the Sustainability bullet and dropped the other six
# areas outright would leave "incident response", "failure
# management", "service quotas" and "financial management" nowhere in the rendered HTML,
# beside a Security score that reads as complete. A gap the skill states and the report omits is a gap
# the reader takes for a pass. Extracting the text at render time is the only version of "the report
# says what the skill says" that a comment cannot make false: edit the block and the next report
# follows, with no second place to remember.
#
# A missing or empty marker pair is therefore an ERROR, not a cue to print less: it puts a visible
# alert naming the marker where the block should have been and makes the run exit non-zero. Falling
# back to a shorter disclosure is precisely the defect these blocks exist to close.
SKILL_BLOCK_NAMES = ("NOT-ASSESSED-AREAS", "NOT-ASSESSED-NARROWER", "SCOPE-PLATFORMS",
                     "SCORE-DISCLOSURE", "PLATFORM-CREDIT-NOTE", "PLATFORM-CREDIT-NONE")
# The file each block is read from, as the report and stderr name it. Every name not listed is in SKILL.md.
SKILL_BLOCK_SOURCES = {"SCOPE-PLATFORMS": "references/workflow.md"}


def skill_block_source(name):
    return SKILL_BLOCK_SOURCES.get(name, "SKILL.md")


def skill_blocks(skill_md, workflow_md=None):
    """Extract the marked report-content blocks from SKILL.md and, for SCOPE-PLATFORMS, from
    references/workflow.md (`workflow_md`; default: `references/workflow.md` beside `skill_md`).
    Returns {name: text or None}.

    The opening marker carries maintainer notes after the name (`:BEGIN — read verbatim by ...`), so
    the pattern consumes the rest of that comment and starts the text at the next line. Anything
    missing, unmatched or whitespace-only is recorded in SKILL_BLOCK_DEFECTS and returned as None for
    the caller to render as an alert; nothing here substitutes text of its own.
    """
    blocks = dict.fromkeys(SKILL_BLOCK_NAMES)
    paths = {"SKILL.md": pathlib.Path(skill_md),
             "references/workflow.md": (pathlib.Path(workflow_md) if workflow_md is not None
                                        else pathlib.Path(skill_md).parent / "references" / "workflow.md")}
    texts = {}   # source -> (text, None) or (None, why every block in it is missing)
    # os.path.isfile(), non-raising, for the reason given in question_prose(): this path is derived from
    # the operator's `--references`, and an unstattable one must reach the defect list below rather than
    # raise. Every arm here already fails loudly — one SKILL_BLOCK_DEFECTS entry per block that file
    # holds, and a non-zero exit.
    def read(src):
        path = paths[src]
        if not os.path.isfile(path):
            return None, f"no {src} at {path}, so this block could not be read"
        # THE READ IS GUARDED TOO. Guarding the stat on the line above and leaving this one bare would be
        # the mistake the `-o` block in main() is written to avoid -- catching one stat and not its
        # neighbour is not a fix, it is a narrower bug. Unguarded, a mode-000 SKILL.md or workflow.md
        # (PermissionError) and a non-UTF-8 one (UnicodeDecodeError) would both raise straight past this
        # line. The arm above already has exactly the right behaviour to route them into, so they take it:
        # one SKILL_BLOCK_DEFECTS entry per block that file holds, the alert naming each missing marker,
        # and a non-zero exit -- with the errno stated instead of a stack trace.
        try:
            return path.read_text(encoding="utf-8"), None
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"{src} at {path} could not be read ({exc}), so this block is missing"
    for name in SKILL_BLOCK_NAMES:
        src = skill_block_source(name)
        if src not in texts:
            texts[src] = read(src)
        text, why = texts[src]
        if text is None:
            SKILL_BLOCK_DEFECTS.append((name, why))
            continue
        m = re.search(r"<!--\s*" + re.escape(name) + r":BEGIN\b.*?-->\n(.*?)\n<!--\s*"
                      + re.escape(name) + r":END\s*-->", text, re.S)
        if not m:
            SKILL_BLOCK_DEFECTS.append(
                (name, f"no matching <!-- NAME:BEGIN ... --> / <!-- NAME:END --> pair in {src}"))
            continue
        if not m.group(1).strip():
            SKILL_BLOCK_DEFECTS.append((name, f"the marker pair in {src} is empty"))
            continue
        blocks[name] = m.group(1)
    return blocks


def skill_block_html(blocks, name, subs=None):
    """One marked block as HTML, or a visible alert naming the marker and its file if it could not be read.

    Substitution is an explicit `.replace()` per placeholder, NOT `str.format`: this text is prose a
    maintainer edits, it already contains literal braces (`{.items[*]}`-shaped field paths and JSON
    fragments appear in neighbouring blocks), and `str.format` would raise KeyError or silently eat
    them. The values are inserted BEFORE md_inline(), so a substituted value is escaped by the same
    e() call as the surrounding prose and cannot introduce markup.
    """
    text = blocks.get(name)
    if text is None:
        return ('<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
                f'<div><h3>Report content missing: <code>{e(name)}</code></h3>'
                f'<p>This report is meant to carry the text between the <code>{e(name)}</code> '
                f'markers in the skill&rsquo;s own <code>{e(skill_block_source(name))}</code>, and that block could not be '
                'read. What is missing is a disclosure about the limits of this review, so treat this '
                'report as incomplete rather than as saying less. The renderer exits non-zero when '
                'this alert appears.</p></div></div>')
    for key, value in (subs or {}).items():
        text = text.replace(key, value)
    return md_inline(text)


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
# An `image` test that examines the SHAPE OF A REFERENCE -- its tag/digest grammar -- rather than an
# identity substring inside it. Stripped before _JQ_NAME_TEST runs, because the disclaimer that fires
# off that pattern is specifically about identity: its stated failure mode is "a tool that does the job
# under a name the pattern does not know is reported as absent (Vector rather than Fluent Bit)", which
# is meaningless for `sec-12`, whose regex asks whether an image reference carries a tag or a digest.
# Left as prose beside the "images pinned to a digest or an explicit tag" question, the caveat would tell
# the reader to go and check the pattern against the tools they run -- advice about the wrong thing.
#
# THE TEST IS STRUCTURAL, NOT A LIST OF IDS, for the reason name_pattern_based() already gives: a
# hardcoded list of ids goes stale the same way a count typed into a comment does.
# A shape pattern is anchored (`$`) or carries a character class (`[`); an identity pattern is a plain
# substring or alternation of proper nouns. SIX questions run a `test()` against an `.image` value --
# `lens-12` and `lens-13` (`dkr.ecr`), `rel-4` (`karpenter/controller|cluster-autoscaler`), `ope-5` and `rel-13`
# (`prometheus|grafana|cloudwatch|...`), and `sec-12` (`:latest$`, `@sha256:|:[^/]+$`). On today's tree
# the split is exact: `rel-4` keeps it for two reasons: its Deployment-name test is a literal `test("karpenter|cluster-autoscaler")`,
# which _JQ_NAME_TEST matches, and so do its image tests, whose patterns are jq variables (`image|test($aimg;"i")`); the others carry neither an anchor nor a class; `sec-12` alone loses it. Do not trust that sentence -- re-derive it,
# because it is a statement about six programs on one day, not about regexes:
#   python3 -c "import re,importlib.util; ..." over scorer_provenance(), grouping by matched field.
#
# ANCHORED-OR-CLASSED DOES NOT *IMPLY* REFERENCE-SHAPE, so this rule is a heuristic and IS guarded --
# on its OUTCOME, not on its syntax. `test("gcr\.io$")` is an identity test that is anchored, and
# `test("dkr\.ecr\..*\.amazonaws\.com$")` is `lens-12`'s own pattern one character from being stripped.
# Do not guard _JQ_IMG_SHAPE's own syntax: that asserts the property in the
# wrong terms. _JQ_IMG_SHAPE is not the only suppressor in this expression, and a one-line edit evades
# such a guard two different ways. `_JQ_SCOPING` runs FIRST and is itself a suppressor, so
# renaming `lens-12`'s regex to the literal AWS image name `test("amazon-k8s-cni")` drops its
# disclaimer while a syntax guard reports nothing; and `_JQ_NAME_TEST` needs the field token within 14
# characters of `test(`, so the semantics-preserving refactor
# `.image as $iref|$iref|select(test("dkr.ecr"))` drops it too. Neither is namable by an allowlist over
# regexes -- the first would need a second list of every `^system:`-style scoping test in the tree, and
# the second is a DISTANCE in the program text rather than a pattern at all. That is an argument against
# guarding the CLASSIFIER, not against guarding the PROPERTY: see disclosure_drift() below, which checks
# the only thing the promise is about -- which questions end up carrying the disclosure -- and is
# therefore blind to which of the three suppressors fired.
#
# DELIBERATELY SCOPED TO `image`. A `name` or `namespace` test that happens to be anchored is still an
# identity test (`test("^system:")` is scoping, and _JQ_SCOPING already handles that case), so widening
# this to those fields would silently drop disclosures the report needs.
_JQ_IMG_SHAPE = re.compile(r'\bimage\b[^;]{0,14}?\|\s*(?:(?:select|any|map|all)\(\s*)?'
                           r'test\(\s*"[^"]*[\[$][^"]*"\s*\)')


def name_pattern_based(jq):
    """True when the scorer decides this question by matching a regex against a resource NAME
    (or namespace, or container image, or add-on id) rather than by reading a field that states the
    answer.

    Read off the scorer's own jq — the same text the panel prints under "Exact command used" — rather
    than a hardcoded list of question ids, because a hardcoded list goes stale the same way a count
    typed into a comment does.
    """
    if not jq:
        return False
    return bool(_JQ_NAME_TEST.search(_JQ_IMG_SHAPE.sub("", _JQ_SCOPING.sub("", jq))))


# A block-local scorer prelude: `B='def b(...);'`, `PE='def gkenf: ...;'`. Each pillar block assigns a
# few of these and the helpers prepend them to every jq they run, so the program on a scorer line is not
# self-contained -- it calls `b(...)`, or `gkenf`, without carrying their definitions.
#
# WHY THE PANEL NEEDS THEM. "Exact command used" exists so a reader can run the detection themselves and
# check a verdict. Most scorers call `b(...)`, so the scorer line printed alone is a program that fails
# pasted with `b/2 is not defined` -- an audit trail one step short of being usable. A missing scoring
# band is a nuisance a reader can guess past; a missing `gkenf`/`kyenf` is not, because those
# encode a SECURITY judgement -- which Gatekeeper
# and Kyverno states count as refusing at admission -- and a reader cannot audit a judgement they cannot
# see. So the panel prints the definitions the program calls, and only those.
#
# DERIVED, NOT LISTED: the variable names, the function names and the arity all come out of the file
# being parsed, so a new prelude or a new helper needs no edit here. Arity decides how a call is
# recognised -- `def b($ok;$t):` is only a call as `b(`, while a zero-parameter `def gkenf:` is called as
# a bare word inside `select(gkenf)` -- which is why this reads the signature instead of assuming parens.
_PRELUDE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)='(def .*)'$", re.M)
_PRELUDE_DEF_RE = re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*(\([^)]*\))?\s*:")


# A DELIBERATELY SLOPPIER READER THAN _PRELUDE_RE, used only to catch the strict one going blind.
#
# _PRELUDE_RE is anchored `^NAME='(def .*)'$`, which is right for extraction -- it is the exact shape the
# scorer helpers and reduce.sh read -- and wrong as a detector, because every way of breaking that shape
# makes it match NOTHING and a prelude that matches nothing is indistinguishable from a file that has no
# prelude. One space before `PE=`, one space after the
# opening quote, a trailing comment, or a line split in two each make this reader match no `def gkenf`
# while every score stays identical; reduce.sh refuses all four (rc=1), which this reader must not rely on.
# That is precisely the silent loss of a SECURITY disclosure the panel exists to prevent.
#
# So this reader drops the two anchors that can be evaded -- it allows leading whitespace and does not
# require the closing quote or a `def ` immediately inside it -- and the check below reports any name a
# prelude-shaped assignment appears to define, which a scorer in the same file calls, and which the strict
# reader did NOT resolve. The predicate is in the same terms as the promise: not "is the line shaped
# correctly" but "is the definition this program calls actually going to be printed".
# `re.S` AND A NON-GREEDY BODY, both load-bearing. Captured as `(.*)$` without `re.S`, this would read
# only the remainder of the line the `=` is on -- so a SPLIT assignment (body moved to
# the next line) would capture nothing, "apparently defined" would be empty, and the one shape this reader
# must backstop would be invisible to it: a split `B='` keeps every score identical and drops definitions
# from the report; reduce.sh's one-line-assignment gate refuses it (rc=1), but this reader must not rely on that.
# `[^']*` rather than `.*?` because a scorer prelude contains no internal single quote -- that is already a
# documented constraint of scorer-line quoting (see `m rel-20`) -- and it keeps the match bounded.
_PRELUDE_LOOSE = re.compile(r"^[ \t]*([A-Z][A-Z0-9_]*)[ \t]*=[ \t]*'([^']*)'", re.M | re.S)


def prelude_shadow(ref_dir):
    """[(file, qid, name)] for every prelude definition a scorer calls that the panel will not print."""
    out = []
    ref = pathlib.Path(ref_dir)
    if not os.path.isdir(ref):
        return out
    for md in sorted(ref.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue          # question_prose() already records this file, with a better message
        def names(rx):
            return {n for _v, body in rx.findall(text) for n, _p in _PRELUDE_DEF_RE.findall(body)}
        unresolved = names(_PRELUDE_LOOSE) - names(_PRELUDE_RE)
        if not unresolved:
            continue
        for line in text.splitlines():
            mt = _SCORER_RE.match(line) or _LIST_RE.match(line)
            if not mt:
                continue
            qid = mt.group(1) if mt.re is _LIST_RE else mt.group(2)
            for n in sorted(unresolved):
                if re.search(r"\b%s\b" % re.escape(n), mt.group(0).partition("'")[2]):
                    out.append((md.name, qid, n))
    return out


# Every question that carries the regex/heuristic disclosure, pinned as the OUTCOME it is.
#
# WHY A LIST HERE WHEN name_pattern_based() REFUSES ONE. The two lists are not the same kind of thing.
# A list of ids used to DECIDE the disclosure goes stale silently: a new name-matching question is simply
# absent from it and quietly loses its caveat, and nothing notices. This list decides
# nothing. name_pattern_based() still classifies, from the scorer's own jq; this only records what the
# classification came out as, so a difference in EITHER direction is a fact about the code, not an
# omission from a list, and cannot pass unnoticed. reduce.sh already carries two assertions of exactly
# this shape (`RATIO_STATE_EXEMPT`, and the one-distinct-`B` check).
#
# WHY THE OUTCOME AND NOT THE CLASSIFIER. The promise is "a security judgement is never SILENTLY
# suppressed". Three separate things in name_pattern_based() can suppress -- `_JQ_SCOPING`,
# `_JQ_IMG_SHAPE`, and `_JQ_NAME_TEST`'s 14-character window -- and the window is not a pattern that any
# allowlist can enumerate. A guard on one of the three is evadable by editing either of the other two;
# a guard on the set they jointly produce is not, because it never asks which one fired. It
# fires on the scoping rename, on the out-of-window refactor, AND on the anchored-identity case that a
# syntax guard would be built for.
#
# 23 IDS, AND `sec-12` IS DELIBERATELY NOT ONE OF THEM -- its regex asks whether
# an image reference carries a tag or a digest, so the identity caveat ("Vector rather than Fluent Bit")
# would be advice about the wrong thing. Keep it out when this list is edited.
_DISCLOSED_EXPECTED = frozenset({
    "cost-3", "fargate-4", "lens-1", "lens-2", "lens-3", "lens-4", "lens-12", "lens-13",
    "ope-3", "ope-5", "ope-7", "ope-8", "ope-10", "perf-2", "rel-4", "rel-13", "rel-16", "rel-23",
    "sec-8", "sec-10", "sec-27", "sec-28", "sec-33",
})


def disclosure_drift(prov):
    """(lost, gained): questions that stopped, or started, carrying the regex/heuristic disclosure.

    Takes the already-parsed provenance rather than re-reading references/, so the set checked is the
    same one evidence_panel() renders from and the two cannot disagree.
    """
    now = frozenset(q for q, v in prov.items() if name_pattern_based(v.get("jq")))
    return sorted(_DISCLOSED_EXPECTED - now), sorted(now - _DISCLOSED_EXPECTED)














def _labels(i):
    return (i.get("metadata") or {}).get("labels") or {}


# THE SAME PARTITION THE SCORERS USE, in the one language this file shares with them.
# The scorers' `B='def b(...)'` prelude carries `ishy`/`isec2`; every Python re-derivation of the node
# population below must agree with them or the report and the verdicts describe different fleets. Label
# THE PROVIDER ID DECIDES AND THE LABEL ONLY BREAKS A TIE, which is not the same as OR-ing them.
# `eks-hybrid:///<region>/<cluster>/<name>` is written by nodeadm; `eks.amazonaws.com/compute-type` is
# an ordinary label that anyone with node-patch RBAC can set. Under OR the mutable signal ALONE would be
# sufficient, so labelling two real EC2 nodes `compute-type=hybrid` would drop them out of every node
# question -- `lens-14` would go from `some~1 NAT/2 AZ` to `all~1 NAT/1 AZ`, turning a NAT-redundancy
# failure into a pass, by an edit to two labels. So an
# `aws:` providerID VETOES the label: a node that AWS says is an EC2 instance is one, whatever it is
# labelled. The label is consulted only when there is no providerID to contradict it, which is the
# real case of a hybrid node still registering.
#
# `isinstance(..., dict)` and not `or {}`: `or {}` rescues only FALSY values, so a `.spec` that is a
# STRING sails through and `.get` raises AttributeError, crashing the whole renderer on a
# cluster that scores fine. A malformed field must never cost the report.
def _is_hybrid(n):
    """True for an EKS Hybrid Node -- an on-premises or other-cloud machine, not an EC2 instance."""
    spec = n.get("spec")
    pid = spec.get("providerID") if isinstance(spec, dict) else None
    pid = pid if isinstance(pid, str) else ""
    if pid.startswith("eks-hybrid:"):
        return True
    if pid.startswith("aws:"):
        return False
    return _labels(n).get("eks.amazonaws.com/compute-type") == "hybrid"


# The scorers' `iswin`, term for term: jq's `//` falls through only on null/false (an empty-string
# label does NOT fall through), and `tostring` compares a non-string value by its JSON text.
def _is_windows(n):
    """True for a Windows node -- one this skill does not assess (Linux nodes only)."""
    v = _labels(n).get("kubernetes.io/os")
    if v is None or v is False:
        st = n.get("status")
        ni = st.get("nodeInfo") if isinstance(st, dict) else None
        v = ni.get("operatingSystem") if isinstance(ni, dict) else None
    if v is None or v is False:
        v = ""
    return (v if isinstance(v, str) else json.dumps(v, separators=(",", ":"))) == "windows"
















































































































# ---------------------------------------------------------------------------
# The presentation layer for the names the SCORER emitted. This is where new questions go.
#
# There is no second provenance to contrast this with: no Python code here extracts resources, so
# every named object in every report comes out of the same jq program that decided the verdict.
#
# The scorer's contract is one shape for all of them: `pass` and `fail` arrays of plain strings, plus
# three optional keys the scorer alone can know — `context` (scope notes), `kind` (`field` when the
# list is settings rather than objects, `existence` when the question answers yes/no), `excluded` (a
# COUNT of objects deliberately not named), and `context_only` (this arm was settled before any object
# was counted). Everything else is PRESENTATION and lives here: labels, sorting, the "showing 12 of N"
# cap, and the sentence built around `excluded`. A scorer that started choosing those would make the
# panels disagree about what a list looks like, and the cap stops working the moment one pre-truncates.
#
# So this table holds TEXT ONLY. If an entry here ever needs to look at the collected data, that is the
# signal the thing belongs in the scorer instead. Its one structural limit, worth knowing before you
# fight it: entries are flat per question id, so a question whose arms want DIFFERENT labels cannot
# express that here — pick one label that is true on every arm, and let the arm-specific fact live in
# the member strings or the scorer's own `detail`.
SCORER_LIST_UI = {
    # -- Operational Excellence ------------------------------------------------------------------
    "ope-5":  {"pass_label": "Monitoring workloads and images this check matched",
               "context": ["Deployment names: prometheus|grafana|cloudwatch|datadog|adot|opentelemetry",
                           "DaemonSet names: prometheus|grafana|cloudwatch|datadog|adot|opentelemetry",
                           "container images: prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel",
                           "excluded from all three: any name or image matching node-exporter or operator, any Deployment or DaemonSet whose pod template runs an operator image, and any Windows-pinned workload or pod (this skill supports Linux nodes only)"],
               "context_label": "the three name/image patterns this check matches, one per source, and "
                                "what it excludes"},
    "ope-7":  {"pass_label": "Matched the detection",
               "context_label": "EC2 nodes the DaemonSet could run on (the check is n/a with none)"},
    "ope-15": {"pass_label": "Lifecycle managed by AWS (managed node group or EKS Auto Mode) \u2014 or, on "
                             "the Auto Mode arm, the cluster setting that says so",
               "fail_label": "No eks.amazonaws.com/nodegroup label and no eks.amazonaws.com/compute-type=auto label",
               "context_label": "scope of this verdict: the nodes and node groups it did not count"},
    # THE PARTITION IS "MANAGED AND HEALTHY" vs "NOT THAT", so both halves have to say so. The scorer's
    # pass set is the installed core add-ons whose describe-addon detail reports `status ACTIVE` with
    # zero `health.issues`, which puts a managed-but-sick add-on on the FAIL side -- so a
    # `fail_label` saying the members are "not EKS managed add-ons" would sit directly under a member
    # saying it is one: a heading "Core add-ons that are not
    # EKS managed add-ons here (1)" over "coredns (an EKS managed add-on, but status DEGRADED, health
    # issue(s): InsufficientNumberOfReplicas)". The same list also holds genuinely-unmanaged add-ons
    # (a self-managed coredns, kube-proxy or vpc-cni lands there with no such annotation), so
    # the label has to be true of BOTH populations and names the two reasons rather than one.
    # The `pass_label` names the health half of the same partition too -- every member IS managed, and
    # healthy -- so the fail side does not look arbitrary. It is there for symmetry; the fail label is
    # the one that has to be exact.
    "ope-16": {"pass_label": "Core add-ons EKS manages here and that report ACTIVE with no health "
                             "issues (or the Auto Mode setting that makes them AWS\u0027s to manage)",
               "fail_label": "Core add-ons not counted here \u2014 not an EKS managed add-on, or "
                             "managed but not ACTIVE and healthy",
               "context_label": "other add-ons installed (not counted by this check)"},
    "ope-18": {"pass_label": "Guarded (concurrencyPolicy is not Allow)",
               "fail_label": "Unguarded (concurrencyPolicy Allow, the default)"},
    # rel-24 is a `kind:"field"` question, and without an override here its single member -- the value
    # of the field it read -- would file under the default "Counted as passing". On a cluster with
    # protection off the panel would print "Counted as passing (1) deletionProtection =
    # false" beneath a `none` verdict: the label contradicting the verdict beside it.
    "rel-24": {"pass_label": "Cluster settings read"},
    "lens-7": {"pass_label": "How the VPC CNI is managed here (EKS managed add-on, Auto Mode setting, or "
                             "Fargate node fact)",
               "fail_label": "Not managed as an EKS add-on",
               "context_label": "add-ons installed on the cluster (not what decided this)"},
    # -- Security --------------------------------------------------------------------------------
    "sec-1":  {"pass_label": "Cluster settings read"},
    "sec-2":  {"pass_label": "Cluster settings read"},
    "sec-6":  {"context_label": "identity plumbing"},
    # A fixed sentence, not a list of objects: sec-9's scorer excludes the built-in roles by name and
    # the reader needs to be told so. It lives here rather than in `rl` for exactly that
    # reason -- there is no object to name.
    "sec-9":  {"context": ["built-in system:/eks: roles excluded"], "context_label": "scope"},
    "sec-11": {"context_label": "namespaces excluded by the kube-*/amazon-* name prefix "
                                "(may include namespaces you created)"},
    "sec-17": {"pass_label": "Cluster settings read"},
    # The `rl` line puts the IRSA ServiceAccounts in `pass` only when a provider matching this issuer
    # is registered; otherwise they are `context`, each marked NOT credited. So `pass_label` is true of
    # every list it heads, and `context_label` has to cover those uncredited accounts too -- under a
    # `none` verdict a pass-only heading would read "Registered provider and the accounts that depend on it"
    # over IRSA ServiceAccounts that no provider matches at all.
    "sec-18": {"pass_label": "Registered provider and the accounts that depend on it",
               "context_label": "matched against, and any IRSA ServiceAccount left NOT credited because "
                                "no provider matched",
               # NOT "they belong to other clusters". An IAM OIDC provider that does not match this
               # cluster's issuer is just as likely to be a GitHub Actions or other non-EKS federation,
               # and this check reads only the issuer URLs -- it learns nothing about whose a provider
               # is. `sec-21`'s note follows the same rule.
               "excluded_note": "{n} other IAM OIDC provider(s) exist in this account and do not match "
                                "this issuer (identifiers omitted \u2014 an unmatched provider may "
                                "belong to another cluster or to any non-EKS federation; all this check "
                                "establishes is that it does not match the issuer of this one)"},
    # NOT "{n} volume(s) in the VPC are not tagged to this cluster ... they belong to workloads outside
    # this review". THREE separate claims, none of them supportable:
    #   "in the VPC"   -- collect.sh:1650 is `aws ec2 describe-volumes --region "$REGION"` with NO
    #                     vpc-id filter, and an EBS volume carries no VPC field at all (16 keys, none of
    #                     them a VPC), so the population is every volume in the account and Region.
    #                     `sec-30`/`net-2`/`net-1`/`lens-15` may say "in the VPC" -- collect.sh:1429-1433
    #                     DO pass Name=vpc-id for sg.json, subnets.json and vpcendpoints.json. This one
    #                     cannot.
    #   "not tagged"   -- the tag is not the only thing that ties a volume to this cluster. A
    #                     managed-node-group / launch-template node root or data volume carries no
    #                     cluster tag (a Karpenter-provisioned one does).
    #   "they belong to workloads outside this review" -- a cluster's OWN node disks can be among them:
    #                     a managed-node-group root or data volume carries no cluster tag and may be
    #                     unencrypted; volumes.json ties such disks by Attachments[].InstanceId against the
    #                     nodes' providerIDs, which this check reads and counts.
    # So the note says what THIS CHECK found and no more, and points at the expression that decides it,
    # which keeps it true whatever that expression counts as this cluster's.
    "sec-21": {"context_label": "scope of this check",
               "excluded_note": "{n} other EBS volume(s) in this account and Region were not "
                                "attributed to this cluster by this check and were excluded from the "
                                "score (identifiers omitted). Not attributed means this check found "
                                "nothing tying them to this cluster \u2014 it is not a finding that "
                                "they are another workload's; the detection expression at the bottom "
                                "of this panel is what decides."},
    "sec-25": {"context_label": "non-EBS StorageClasses, excluded by provisioner \u2014 the EBS "
                                "parameter this check reads does not exist on them"},
    "sec-26": {"pass_label": "Control-plane log types enabled"},
    # `sec-30` and `net-2` share this sentence verbatim and must keep sharing it. NOT "they belong to
    # other workloads": an excluded group may belong to another workload or to nothing at all -- an
    # orphaned security group is nobody's -- and this check only ever established the three facts the
    # note names (a group on a Windows node instance is listed in `context`, not excluded). "in the
    # VPC" STAYS here, unlike in `sec-21`'s note: collect.sh:1429 passes Name=vpc-id,Values="$VPC" for
    # sg.json, so that half is measured.
    "sec-30": {"context_label": "scope of this check",
               "excluded_note": "{n} security group(s) in the VPC are not the cluster's own, carry no "
                                "cluster tag and are on no instance collected for this cluster, and "
                                "were excluded (identifiers omitted \u2014 that is all that is "
                                "claimed: an excluded group may serve another workload, or nothing "
                                "at all)"},
    "sec-33": {"pass_label": "Matched the detection (either branch satisfies it)",
               "context": ["GuardDuty add-on installed",
                           "or a DaemonSet-owned pod named <daemonset>-<5 characters>, where the "
                           "DaemonSet name is aws-guardduty-agent, falco, sysdig, sysdig-<word>\u2026 "
                           "or tetragon, alone or after a Helm release prefix ending in -"],
               "context_label": "the two branches this check accepts"},
    "sec-4":  {"context_label": "the setting that decided this, and the workload namespaces it was not "
                                "measured against (not a pass/fail set)"},
    # NOT "Built-in subjects (expected)", and NOT a claim about the SHAPE of a subject's name. What puts
    # a subject in this list is an allowlist of exactly two (kind, name) pairs -- Group system:masters and
    # User eks:addon-manager -- so this heading can name the rule. Do not widen it to a
    # `system:`/`eks:` PREFIX: that would wave through `system:anonymous`,
    # `system:unauthenticated` and `system:authenticated`, the worst RBAC misconfiguration in Kubernetes,
    # and printing those under "expected" would steer the eye-audit away from the one finding it exists to
    # catch. The look is still asked for, because a pass list is worth reading even when the rule is
    # closed. No trailing period: `.reshead` is uppercased in CSS and no other label in this table ends
    # with one.
    "rbac-1": {"pass_label": "Not counted as findings \u2014 subjects this check exempted as "
                             "Kubernetes/EKS built-ins. Confirm by eye",
               # NOT "that are not built-in", and NOT "that are not platform identities" either. BOTH
               # denied a property the listed entries have. The fail side carries every subject outside
               # the two allowlisted pairs, and plenty of those ARE built-in platform identities:
               # `Group system:nodes` is every kubelet, `User system:kube-controller-manager` is a control
               # plane component, and `Group eks:addon-manager` differs from the identity EKS itself binds
               # only in its `kind`. Being built-in is the whole reason a cluster-admin binding to them is
               # catastrophic, not a reason to excuse it. A heading such as "Paths to
               # cluster-admin that are not built-in" would sit directly above
               # system:anonymous/system:unauthenticated/system:authenticated, denying the very property
               # that makes the finding a finding. So this states the RULE the check applied and nothing
               # about what the subjects are -- in the same words the scorer's own detail string uses, so
               # the heading and the verdict cannot drift apart.
               "fail_label": "Paths to cluster-admin this review counts as findings \u2014 binding "
                             "subjects outside Group system:masters and User eks:addon-manager, and "
                             "aws-auth IAM mappings into system:masters"},
    "net-1":  {"context_label": "scope of this check",
               "excluded_note": "{n} subnet(s) in the VPC are not registered to this cluster and were "
                                "excluded (identifiers omitted)"},
    # Shares `sec-30`'s sentence verbatim -- edit both or neither; see the note there.
    "net-2":  {"context_label": "scope of this check",
               "excluded_note": "{n} security group(s) in the VPC are not the cluster's own, carry no "
                                "cluster tag and are on no instance collected for this cluster, and "
                                "were excluded (identifiers omitted \u2014 that is all that is "
                                "claimed: an excluded group may serve another workload, or nothing "
                                "at all)"},
    "net-4":  {"pass_label": "Egress rules on the cluster security group",
               "fail_label": "Counted as failing",
               "context_label": "Cluster security group"},
    "podsec-5": {"context_label": "scope of this check \u2014 pods that run only on Windows "
                                  "(spec.os.name, or a nodeSelector or required node affinity admitting Windows and no Linux node on "
                                  "[beta.]kubernetes.io/os or node.kubernetes.io/windows-build, on the pod or its DaemonSet's template) are "
                                  "not assessed and not counted; this skill supports Linux nodes only"},
    # -- Reliability -----------------------------------------------------------------------------
    "rel-1":  {"pass_label": "AZs this cluster can place workloads in \u2014 the Ready, uncordoned Linux EC2 nodes\u0027 zone "
                             "labels; with no Linux EC2 node, the fault domains Ready, uncordoned hybrid nodes declare by that label or, with no hybrid node either, the Fargate profile subnets\u0027 AZs",
               "context_label": "how the AZ list was resolved, and the AZs the VPC has subnets in"},
    "rel-2":  {"context_label": "all PodDisruptionBudget objects in the cluster"},
    "rel-4":  {"pass_label": "What the check accepted \u2014 the cluster setting, or the autoscaler "
                             "signals it matched",
               "fail_label": "What the check did not accept \u2014 a cluster setting it could not credit, or an autoscaler match with nothing ready behind it",
               "context_label": "how this was detected: the patterns and labels read, or the node fact that settled it"},
    # rel-13 and ope-5 are the same detection in two files ("EDIT BOTH OR NEITHER"), so their labels
    # must not drift apart either.
    "rel-13": {"pass_label": "Monitoring workloads and images this check matched"},
    # ALL THREE LABELS DESCRIBE THE PER-AZ SHAPE, NOT A GATEWAY LIST. The check counts per AZ:
    # `pass`/`fail` hold AVAILABILITY ZONES (`$azs`): the Linux EC2 nodes' `topology.kubernetes.io/zone`
    # labels (Ready, uncordoned nodes; an AZ only NotReady or cordoned ones occupy stays in, failed, when it has no NAT gateway, and all such AZs are counted when no other AZ is left)
    # plus, when Fargate nodes exist, the Fargate profile subnets' AZs (a Fargate node's own zone label is not read), and `context` holds the gateways (`$g`, every NAT gateway in
    # `nat.json`, which collect.sh filters to this VPC), each as `id (state, AZ)`. Headings written for a
    # gateway list would print AZs under "NAT gateways in some other state" and a gateway id under
    # "AZs checked", inverting both halves on any cluster with nodes; one with no data plane
    # (`na~no nodes`) renders only the context half, and that half would be
    # inverted. Hybrid and Windows nodes are excluded from the AZ set by the scorer; `hyx`/`winx` in the
    # detail say so (so the label stays short), and no Windows row goes into this gateway-list `context`.
    "lens-14": {"pass_label": "AZs checked (zones of Ready, uncordoned Linux EC2 nodes, plus Fargate profile subnet AZs when "
                              "Fargate nodes run, plus the zones of NotReady or cordoned ones where the detail says so) where every node subnet routes 0.0.0.0/0 to an available public NAT gateway serving that AZ",
                "fail_label": "AZs checked where not every node subnet routes 0.0.0.0/0 to an available public NAT gateway serving that AZ (findings)",
                "context_label": "every NAT gateway in the VPC, with its state and its AZ"},
    # THIS STRING AND `net-1`'s ARE DELIBERATELY DIFFERENT. Do not
    # re-unify them: `lens-15` scores the subnets the collected node instances are actually in, falling
    # back to the registered set when no instance was collected and to every subnet when neither
    # resolves -- three populations, and the verdict's own detail names which one it used. `net-1`'s
    # scoping is the registered set only (its scorer lines do not read node subnets),
    # so its note says "not registered to this cluster" and is right to.
    # The predicate is not named here, for the same reason as `sec-21`'s note: under the node-subnet
    # population a REGISTERED subnet can be excluded and an UNREGISTERED one can be scored, so "not
    # registered to this cluster" would be false in both directions: whenever the nodes use only some
    # of the registered subnets, a registered subnet that no node uses is excluded, and that
    # sentence would assert of it exactly what it is not.
    # The detail is the authority and this points at it.
    # "HOLD NONE OF THIS CLUSTER'S NODES" IS THE OBVIOUS ALTERNATIVE AND IT IS WORSE. It is true on the
    # node-subnet tier and non-discriminating on the fallback tier: with no node instance collected the
    # scope falls back to the registered set, and then the SCORED subnets hold none of the cluster's
    # nodes either -- with no node instance collected the detail reads `N/N private ... scored over the N
    # subnet(s) the cluster registers, no node instance having been collected`. A reason
    # clause that is equally true of the included set explains nothing.
    # `context_label` covers BOTH rows this list can hold, and they are opposite in kind: the scorer's own
    # unresolved-subnet row is "in the population, could not be read", while the note above is "not in the
    # population". "scope of this check" flattened that; naming them as exclusions-with-reasons does not,
    # and it stays true when only one of the two renders (when the scorer's `$unres` is 0,
    # only the note does).
    "lens-15": {"context_label": "what this check did not score, and why",
                "excluded_note": "{n} other subnet(s) in this VPC were not in the population this check "
                                 "scored and were excluded from the score (identifiers omitted). The "
                                 "result beside this list names which population that was; a subnet "
                                 "registered to the cluster that no node uses can sit in this count."},
    # The five questions that share the Deployment shape (it lives in their five `rl` lines)
    # share one excluded-Deployment note, and it
    # stays one string.
    "rel-5":  {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    "rel-7":  {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    "rel-8":  {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    "rel-9":  {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    "rel-18": {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    # -- Performance Efficiency ------------------------------------------------------------------
    "perf-3": {"context_label": "the nodes set aside and not judged, and, where nothing was counted, "
                                "why (not a pass/fail set)"},
    "perf-4": {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    "perf-5": {"context_label": "Deployments in kube-*/amazon-* namespaces, excluded by namespace "
                                "(may include components you installed)"},
    "perf-6": {"pass_label": "Distinct instance types across the EC2 nodes",
               "context_label": "the node population and instance types this answer was read from, or "
                                "the reason there was nothing to count (not a pass/fail set)"},
    "lens-6": {"context_label": "scope of this verdict \u2014 which nodes it leaves out, and why"},
    # -- Cost Optimization -----------------------------------------------------------------------
    # THE TOKEN LIST HERE IS A CLAIM ABOUT THE SCORER'S REGEX, so it moves when the regex moves. Two
    # rules follow from that: `nightly`, `offpeak` and `off-peak` are not tokens (they name WHEN a
    # CronJob runs, not what it does, so a nightly or off-peak backup would score as a scale-down), and
    # this list must not advertise a token the check does not test. It must also be complete, or a
    # reader checking their own CronJob against it would conclude, wrongly, that a name the scorer
    # does match would not.
    # These are exactly the six tokens `m3`/`rl cost-3` test (`scale-?down`,
    # `down-?scal`, `scale-?in` and `scale-?to-?0` at the end or before a `-`, `to-?zero`,
    # `shutdown`); a bare `scale` is not one, because it names no direction, and neither is
    # a bare `to-0`, which `upgrade-to-0-9` would match.
    "cost-3": {"pass_label": "Scale-down evidence found (a scheduled CronJob scores all; KEDA or an HPA "
                             "alone scores some)",
               "context": ["a CronJob whose name contains, in any case and with each hyphen "
                           "optional, scale-down, down-scal, to-zero or shutdown, or "
                           "ends in (or has a hyphen after) scale-in or scale-to-0",
                           "a Deployment named like KEDA with a ready replica", "any HorizontalPodAutoscaler"],
               "context_label": "the three signals this check looks for, strongest first"},
    "cost-7": {"context_label": "all cluster tags collected"},
    # Stated explicitly rather than defaulted, because "passing" this check means the volume is IN
    # USE. The scorer emits passes/total and `rl` names the same set. Do not flip either one alone to
    # failures ("1/4 unattached"): the two would disagree on direction -- a false contradiction whenever
    # idle is not exactly half, and a false agreement when it is.
    "cost-8": {"pass_label": "Attached, doing work",
               "fail_label": "Unattached and still billing"},
    # `context` HOLDS TWO POPULATIONS, so a heading that describes one of them is false about the
    # other. It holds the non-EBS classes, and also any EBS class that sets no
    # `parameters.type` and reclaims with Delete (an untyped class with any other reclaim is graded and
    # fails) -- e.g. on `ebs.csi.aws.com`, which a "non-EBS" heading would mislabel to the reader's face.
    # Both are classes the scorer did not grade -- the heading says only that. Each member string still
    # carries its own reason (the untyped ones: no volume type it can read).
    "cost-9": {"context_label": "StorageClasses this check did not grade \u2014 the non-EBS ones "
                                "(neither an EBS provisioner nor an EBS volume type), and any EBS class "
                                "that sets no parameters.type and has a Delete reclaim policy, whose "
                                "volume type comes from a CSI driver default this review does not collect"},
    "lens-16": {"context_label": "all VPC endpoints in the VPC"},
}


def _scorer_resources(qid, data):
    """The evidence list the scorer emitted for `qid`, or None when it emitted none.

    THREE STATES, AND THEY MUST NOT LOOK ALIKE — absent and empty must never be indistinguishable:
      - no `resources` key      -> None. This question publishes no list, by design (a cluster-flag
                                   question has no objects to name), and the panel says so.
      - `resources` is `null`   -> {"unbuilt": True, ...}. The scorer TRIED and its name expression
                                   failed on this cluster's data. The verdict is unaffected, because
                                   `rl` swallows the failure AND refuses multi-document output (the
                                   latter is not cosmetic: without it a name program that yielded two
                                   results, or that left an input file unconsumed, would cost the whole
                                   pillar its score) — but the reader is told the difference, because
                                   "nobody wrote a list for this" and "the list broke here" call for
                                   different actions.
      - `resources` is an object -> the lists, normalised.

    NORMALISATION, AND ONLY NORMALISATION, HAPPENS HERE. Sorting is the renderer's job (the contract
    says so, and it is also the only way the ordering is the same for every question no matter which
    of the 103 scorers produced it); `_res_list` still owns truncation. Nothing is deduped and nothing
    is dropped — either would change a count the scorer already published in `detail`.

    A malformed value degrades to the `unbuilt` state rather than raising. That includes a STRING where
    a list belongs: `sorted("abcd")` is four one-character strings, which would pass the element check
    and render as four fabricated object names, so `pass`/`fail`/`context` must each be a list (or
    absent or null) first -- and `0`, `false`, `""` or `{}` is not, because reading one as an empty
    list would print "found none" against a verdict that counted some. `rl` validates the shape in jq before it writes anything, so this is defence in depth
    against a hand-edited results.jsonl.
    """
    rec = (data.get("by_id") or {}).get(qid)
    if rec is None or "resources" not in rec:
        return None
    raw = rec["resources"]
    ui = SCORER_LIST_UI.get(qid, {})
    if not isinstance(raw, dict) or not all(raw.get(k) is None or isinstance(raw.get(k), list)
                                            for k in ("pass", "fail", "context")):
        return {"unbuilt": True, "pass": [], "fail": []}
    out = {"pass": sorted(raw.get("pass") or []), "fail": sorted(raw.get("fail") or []),
           "from_scorer": True}
    if not all(isinstance(x, str) for x in out["pass"] + out["fail"]):
        return {"unbuilt": True, "pass": [], "fail": []}
    ctx = sorted(raw.get("context") or []) + list(ui.get("context") or [])
    if ctx:
        out["context"] = ctx
    # `kind` selects which caveat the panel prints, and it is the SCORER's to declare because the
    # scorer is what knows whether it counted objects, read a field, or answered yes/no. The panel
    # reads the key from here only; the scorer's list is the single provenance, so every question with
    # the same `kind` renders the same caveat.
    if raw.get("kind") in ("field", "existence"):
        out["kind"] = raw["kind"]
    # `context_only` is the SCORER declaring "this arm was settled before any of these objects was
    # counted" — a cluster setting or a node fact decided it. It is forwarded, not inferred, because
    # `resource_agreement()`'s docstring is explicit that it must never be guessed from "both lists are
    # empty": a list that comes out empty BY ACCIDENT has to keep tripping the gate.
    #
    # It is needed, and `kind` is not a substitute for it. `kind` only
    # picks a caveat; `context_only` is the one thing that EXITS the count comparison. Without it, an arm
    # whose verdict came from a cluster setting is safe only for as long as its `detail` happens to carry
    # no leading `n/m` — the day it gains one, the gate reports a contradiction against a correct verdict
    # and the renderer exits 1. `ope-15`'s Auto Mode arm is exactly one ratio away from that.
    if raw.get("context_only") is True:
        out["context_only"] = True
    # `excluded` is a COUNT WITH NO IDENTIFIERS, and that is the point. Several questions scope
    # themselves to cluster-tagged resources and must disclose how many they skipped -- "22 volume(s)
    # ... were excluded" -- without naming them, because this report does not publish identifiers for
    # objects it could not attribute to the cluster under review. (It must not also say they belong to
    # someone else: see `sec-21`'s note above for why that claim is unsupportable; `sec-18`, `sec-30` and
    # `net-2` make the same point.) A list cannot carry a count with no names, so it is
    # a number: the disclosure is kept
    # without publishing a single identifier.
    if isinstance(raw.get("excluded"), (int, float)) and not isinstance(raw.get("excluded"), bool):
        out["excluded"] = int(raw["excluded"])
        # Turned into the disclosure sentence HERE, in Python, not in the scorer. The scorer emits the
        # NUMBER; the words are the renderer's, like every other label in `SCORER_LIST_UI`. The
        # alternative -- let the scorer emit the finished sentence in its `context` array, which the
        # contract already allows -- would put report prose inside a jq program, where a verdict-shaped
        # sentence can silently drop its own leading ratio.
        # THE WHOLE SENTENCE COMES FROM `SCORER_LIST_UI`, not just a noun, and the default asserts
        # NOTHING about who owns the omitted objects. A hardcoded "they belong
        # to workloads outside this review" would be true for the questions that scope to cluster-tagged
        # resources and FALSE for the ones whose out-of-scope set is the cluster's own Fargate nodes:
        # `ope-15` on a Fargate-only cluster would publish "14 … belong to workloads outside this
        # review" about 14 of the cluster's own nodes. A fixed reason clause cannot be right for every
        # question that needs to disclose a count, so the reason is the question's to state.
        # `excluded_note` is a format string taking `{n}`.
        if out["excluded"] > 0:
            note = ui.get("excluded_note")
            out.setdefault("context", [])
            out["context"] = out["context"] + [
                note.format(n=out["excluded"]) if note else
                f"{out['excluded']} object(s) were outside this check's scope and are not named here"]
    for key in ("pass_label", "fail_label", "context_label"):
        if ui.get(key):
            out[key] = ui[key]
    return out


def observed_resources(qid, data):
    """The named objects for `qid`, or None if the scorer emitted no list for it.

    THERE IS ONLY ONE PROVENANCE. No Python extractor re-reads the collected JSON to build a second,
    independent list per question: a second reading can name a different set from the one the verdict
    counted. The scorer that decides the verdict also names the objects the verdict was about, in the
    same jq program, from the same file, on the line above.
    """
    return _scorer_resources(qid, data)


def resource_agreement(r, res):
    """Compare the resource list's counts with the scorer's own `N/M` from the detail string.

    Returns (verdict, message). `verdict` is True (agree), False (DISAGREE — a real bug) or None
    (nothing to compare). The gate treats False as a failure: a resource list that contradicts the
    score is worse than no list at all.

    `context_only` IS THE ONLY *LIST-DECLARED* WAY OUT OF THE COMPARISON, AND IT IS DELIBERATELY
    EXPLICIT. (There is one other exit, checked before it: `unbuilt`, for a scorer `rl` program that
    failed. That one is not a claim an author makes — it is a fact about this run — so it does not
    weaken the rule below.) A scorer list
    that publishes no pass/fail set has to say so in its own result, because "the pass list
    came out empty" and "this question has no pass/fail set on this cluster shape" look
    the same on inspection -- and the difference decides whether comparing 0 against a
    scorer's 1 is a bug or a category error. Without the marker, a context-only list under a scorer
    whose detail leads with a ratio ("1/1 CronJobs guarded ...") would be compared as 0
    against 1, called a contradiction, and fail the whole run on a correct finding -- on any
    real cluster that happens to have exactly one CronJob, a shape a fixture set
    can easily lack.

    Everything without the marker is still compared, INCLUDING a list that comes out empty by
    accident: that case must keep tripping the gate. So this must never be relaxed into a heuristic
    such as "no passes and no failures means skip" -- the marker has to be a claim the scorer
    author makes on purpose.
    """
    if not res:
        return None, "no extractor"
    if res.get("unbuilt"):
        # The scorer's `rl` line failed, so there are no counts to compare and comparing its two
        # empty lists against the scorer's own ratio would report a contradiction that does not
        # exist. Checked BEFORE the ratio match for that reason.
        return None, ("the check named no objects on this cluster because the step that builds the "
                      "list failed; the verdict itself was produced separately and stands")
    if res.get("context_only"):
        # "a cluster setting OR a node fact": the marker is set on `sec-4`/`sec-30`, where a
        # cluster field decides the verdict, but `perf-3`, `perf-6`, `lens-6` and `rel-4` reach it
        # through the NODE population instead (every node is a Fargate node, no node carries an
        # instance-type label). Naming only the cluster setting would misdescribe four of the six.
        return None, ("this check was decided by a cluster setting or a node fact rather than by "
                      "counting these objects, so there is no pass/fail list to cross-check")
    m = re.match(r"^(\d+)/(\d+)", r.get("detail", "") or "")
    if not m:
        return None, "this check answers yes/no rather than counting"
    n, tot = int(m.group(1)), int(m.group(2))
    gp, gt = len(res["pass"]), len(res["pass"]) + len(res["fail"])
    if gp == n and gt == tot:
        # STATE BOTH SIDES OF THE COMPARISON, in the same terms as the lists rendered directly above
        # it. "0 items listed, and the check counted 0 -- they agree" would print the pass count twice and
        # the total never, so on a 0/5 question it would appear as a tick and the word "agree" immediately
        # under "Counted as failing (5)": a success message that reads as a contradiction of the very
        # list it was about. The failing count is named for the same reason -- it is the number the
        # reader can already see.
        # DO NOT PRINT THE WORD "AGREE". It would claim an independent confirmation -- a second
        # derivation of the list matching the scorer's ratio -- and there is none: the list and the ratio
        # come from the same scorer, and the report would not say WHAT agreed.
        # A separately derived list is not the answer either: an independent re-reading can name a
        # different set from the one its own verdict counted -- for `net-4`, a security group open to the
        # world among the PASSES -- and then "agree" is actively false.
        # So every list comes from the same jq program that decided the verdict, and the honest
        # sentence is the one below: these are the objects the check counted. Keep it that way: build
        # any new list in the same program as the verdict it sits under.
        #
        # The counts are still asserted -- the `if` above -- because `rl` and `m` are two jq programs on
        # two adjacent lines, and drift between them is exactly what this comparison can still catch.
        # That is a narrow claim, and a true one.
        return True, (f"these are the objects the check itself counted: {gp} passing, "
                      f"{gt - gp} failing ({gt} in scope), and it reported {n}/{tot}")
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
# the skill's own tree, not a URL. A regex that recognised only the `https://` form would never
# match it, and the whole `[text](target)` would fall through unrendered, appearing to the reader as
# literal bracket syntax wherever a cost or security question cross-
# reference `cost-analysis.md` or `identity-access.md` this way. Rendering it as a live `<a href>`
# would be worse, not better: the target is a file in the skill's own `references/` tree, which a
# reader holding only the forwarded HTML report does not have, so the link would be dead on click.
# So that branch drops the bracket/paren syntax and keeps the link TEXT as plain text — the reader still
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


# Single-asterisk *emphasis*. Every constraint below is load-bearing, and the ORDER matters:
#   - it runs AFTER the `**bold**` rule, so a bold run has already become <strong> and there is no `**`
#     left for this rule to bite half of. Running it first would turn `**x**` into `<em>*x*</em>`.
#   - it runs BEFORE _linkify(), so at substitution time the only markup in the text is <code> and
#     <strong>, and no `href="..."` attribute exists that a match could reach into. e() has already
#     run, so `<`, `>`, `"` and `'` from the SOURCE are entities and cannot be produced here.
#   - code spans are MASKED OUT of the text before it runs, and restored after. An asterisk inside
#     backticks is part of a command or a field path, never emphasis -- `rel-12`'s remediation carries
#     `kubectl ... -o jsonpath='{.items[*].spec.containers[*].name}'`, and a rule
#     trusting the `<`/`>` exclusion alone turns it into `{.items[<em>].spec.containers[</em>].name}`
#     in the customer's report: both asterisks sit inside ONE code span, so no tag boundary is crossed
#     and no other exclusion can see it. Masking rather than splitting, because an emphasis run may
#     legitimately CONTAIN a code span -- one of `sec-4`'s two node-kind sub-headings does -- and
#     splitting on code spans protects the field path at the cost of that heading. See _emphasise().
#   - the content may not contain `*`, a newline, `<` or `>`. No `*`: it cannot span two emphasis runs.
#     No newline: it cannot touch the `- `/`* ` bullet markers the loop below reads -- a rule allowing
#     newlines turns "* one\n* two" into one <em> that swallows the second bullet, because `[^*]`
#     matches a newline in Python by default. No `<`/`>`: a match stays inside ONE already-escaped text
#     run, so it can never straddle a generated tag.
#   - the opening `*` must start a line or follow whitespace, `(`, or the `;` that ends an escaped quote
#     entity, and must not be followed by a space. The closing `*` must not be preceded by a space and
#     must not be followed by a word character or another `*`. `[` and `{` are deliberately NOT openers:
#     that is what a bracketed index path looks like. Together these keep a glob (`kube-*/amazon-*`,
#     `[a-z]*\.`), an arithmetic `2*3`, a path (`/tmp/*.json`), a trailing footnote marker and a lone `*`
#     out of emphasis: none of them has a delimiter pair in that shape.
# Without this rule a single-asterisk run leaks with its asterisks showing, including the whole
# of `sec-4`'s two node-kind sub-headings, printed to the customer that way. The
# defect would be the formatter, not the source text -- rewriting those strings as `**` would leave the
# next `*emphasis*` anyone writes to leak in exactly the same way.
_EM_RE = re.compile(r"""(^|[\s(;—–])   # line start, space, '(', entity ';', em/en dash
                        \*(?!\s)                    # opening delimiter, not followed by a space
                        ([^*\n<>]+?)                # the emphasised text: one line, one escaped run
                        (?<!\s)\*(?![\w*])          # closing delimiter, not preceded by a space""",
                    re.M | re.X)


_CODE_SPAN = re.compile(r"<code>.*?</code>", re.S)
_EM_MASK = re.compile("\ue000(\\d+)\ue001")


def _emphasise(txt):
    """Emphasis with code spans held out of reach, then put back.

    The sentinel is a private-use code point, so it cannot arrive from e()'s output and cannot collide
    with anything a reference file could contain. It also contains no whitespace, `*`, `<` or `>`, so
    a masked code span is transparent to every lookaround in _EM_RE: emphasis may span one, and the
    asterisks inside one are invisible to the rule.
    """
    spans = []

    def _mask(m):
        spans.append(m.group(0))
        return f"\ue000{len(spans) - 1}\ue001"

    out = _EM_RE.sub(r"\1<em>\2</em>", _CODE_SPAN.sub(_mask, txt))
    return _EM_MASK.sub(lambda m: spans[int(m.group(1))], out)


def md_inline(s):
    """Render the small markdown subset the reference remediation prose actually uses.

    THE PARAGRAPH MODEL. Body lines are not emitted bare, separated by `\\n`, with blank lines
    dropped: a newline is whitespace in HTML, so every paragraph of a remediation would run
    into the next one as a single wall of text. `cost-1` and `rel-1`, for example, each have
    paragraphs with no command block between them (a fence already renders as its own block) that
    would render as one, and many other remediations are multi-paragraph the same way. Each
    blank-line-separated run of body lines is one
    `<p class="mdp">`, the smallest markup that makes the boundary visible: bullet lists,
    fenced blocks, `` `code` ``, `**bold**` and single-asterisk emphasis are unaffected, and the text
    inside a paragraph is joined with the reference file's own newlines rather than reflowed.
    """
    out, blocks = [], re.split(r"```(?:bash|yaml|json)?\n(.*?)```", s, flags=re.S)
    for i, chunk in enumerate(blocks):
        if i % 2:                                   # fenced code block
            out.append(f"<pre><code>{e(chunk.rstrip())}</code></pre>")
            continue
        txt = e(chunk)
        txt = re.sub(r"`([^`]+)`", r"<code>\1</code>", txt)
        txt = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", txt)
        txt = _emphasise(txt)
        txt = _linkify(txt)
        lines, in_ul, para = [], False, []

        def flush_para():
            # Mutated in place (`del para[:]`) rather than rebound, so this needs no `nonlocal` —
            # consistent with the py3.9 floor the comments below already assume.
            if para:
                lines.append('<p class="mdp">' + "\n".join(para) + "</p>")
                del para[:]

        for ln in txt.split("\n"):
            if re.match(r"^\s*[-*]\s+", ln):
                flush_para()                        # a bullet ends the paragraph before it
                # A nested bullet ("  - sub-point") matches this too, and is deliberately handled the
                # SAME as a top-level one — this function has no nesting model, so it becomes a sibling
                # <li> rather than being silently folded into its parent's text. Only an indented, un-bulleted
                # continuation line, handled by the next branch, is joined to the <li> above it.
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
                # treating this line as "the list just ended" would split
                # "- a bullet whose text wraps\n  onto a continuation line\n- second bullet" into a
                # one-item <ul>, a dangling sentence fragment at body level, and a second one-item
                # <ul> for whatever followed. So a bullet in a reference file may hard-wrap freely, and
                # does not need to be kept on a single line to render as one
                # list item.
                # A blank line, a fresh bullet, and a line starting at column 0 all end the list
                # as usual — none of those can reach this branch.
                lines[-1] = lines[-1][:-len("</li>")] + " " + ln.strip() + "</li>"
            else:
                if in_ul:
                    lines.append("</ul>")
                    in_ul = False
                if ln.strip():
                    para.append(ln)
                else:
                    # The blank line is what the author uses to mark the paragraph break. It
                    # is the only thing that ends a paragraph, so it is not discarded.
                    flush_para()
        flush_para()
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
       #fe6e73 measures 2.59:1 at 12px/700 where 4.5:1 is required, on every
       failing High row. So the text inverts to near-black (6.78:1) rather than darkening the chip,
       which would collide with the dark surface behind it. Critical is #e0554e (4.91:1), not #d63f38 --
       which fails against BOTH text colours (4.31:1 light, 4.08:1 dark). */
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
/* The config-not-behaviour qualifier, as a chip rather than 12px grey body text, so that it
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
/* The platform-credit row. Inside the table for the same reason caption.tbl-caveat is: it qualifies
   every number above it, and a note placed after the table is cropped out of a screenshot of the rows.
   Spans every column, so it reads as a statement about the table rather than about one pillar. */
tfoot td.tbl-note{
  padding:var(--space-xs) var(--space-l);
  border-top:1px solid var(--color-border-divider-default);
  color:var(--color-text-body-secondary);
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-m);
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
.evidence-panel dt .ro{
  text-transform:none;letter-spacing:0;font-size:var(--font-size-body-s);
  font-weight:var(--font-weight-normal);color:var(--color-text-status-warning);
}
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
  background:var(--color-background-container-content);padding:0 3px;border-radius:2px;
  overflow-wrap:anywhere}
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
  /* Resource lists hold the longest unbreakable tokens in the report: a CloudFormation stack-id tag
     value measures 141 characters with no break opportunity. On screen the container scrolls, but the
     print stylesheets add no wrap rule and paper does not scroll, so the tail of a name would leave
     the page. `overflow-wrap:anywhere` breaks only when there is no other option, so ordinary
     namespace/name pairs still wrap at the slash. */
  overflow-wrap:anywhere;word-break:break-word;
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
  background:var(--color-background-cell-shaded);padding:0 3px;border-radius:2px;
  overflow-wrap:anywhere}

.muted{color:var(--color-text-body-secondary)}
.small{font-size:var(--font-size-body-s);line-height:var(--line-height-body-s)}
ul.plain{margin:0;padding-left:var(--space-l)}
ul.plain li+li{margin-top:var(--space-xxs)}
/* Paragraphs md_inline() produces. A CLASS, not a bare `p` selector: every other <p> on this page is
   written directly as HTML (the alerts, the hero notes, the page header) and already has its own
   margins, and restyling those from here would be an invisible side effect of a prose fix. First and
   last margins collapse so a single-paragraph remediation sits in its <dd> exactly where bare
   text would — only multi-paragraph prose is spaced differently. */
p.mdp{margin:var(--space-s) 0}
p.mdp:first-child{margin-top:0}
p.mdp:last-child{margin-bottom:0}
/* The SCORE-DISCLOSURE block, between the headline number and the pillar table. Deliberately does
   not quote that block's opening words: a grep for them over the rendered HTML is how the gate checks
   the block itself arrived, and a copy in a stylesheet comment would satisfy it falsely. Same
   quiet, bordered treatment the table caveat gets — it qualifies the number above it rather than
   competing with it — but at body-s with body-m leading, because it is a paragraph to read, not a
   chip to glance at. */
.score-note{
  margin-top:var(--space-s);padding:var(--space-xxs) 0 var(--space-xxs) var(--space-s);
  border-left:2px solid var(--color-border-divider-default);
  color:var(--color-text-body-secondary);
  font-size:var(--font-size-body-s);line-height:var(--line-height-body-m);
}
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
    """This skill's own risk weight (High=3 / Medium=2 / Low=1) the reducer weighted this question with
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
# exits non-zero if it is non-empty, so the guarantee lives in the SHIPPED renderer itself rather
# than in a separate check that a review run might never execute.
DISAGREEMENTS = []

# qid -> cross-check verdict, also populated by evidence_panel(): True = the scorer's resource list
# was counted and its N/M matched the scorer's own detail, False = it contradicted it, None = no
# cross-check was possible (no extractor for the question, or a yes/no detection with no total to
# compare against). The banner reports these counts instead of claiming that everything it did not
# name was verified: only some of the measured questions have an extractor at all, so "unaffected"
# would quietly promote "never checked" to "checked and fine".
VERIFIED = {}

MAX_LIST = 12   # cap per list; a 40-node / 800-pod cluster would otherwise dominate the page

# THE READ-ONLY CAVEAT, IN THE HEADING, so it cannot be reached after the commands it is about.
# The same remediation text renders in the Improvement plan (see build()), in the Top-priorities
# table and in every per-pillar findings table through this panel -- and those tables come EARLIER
# in the document than the plan, so a caveat attached to the plan alone would reach every
# "How to fix" panel, and every mutating command inside one, only AFTER the reader has seen it.
# The `na` findings are the sharpest case: improvement_plan() filters them out entirely, so
# `cost-6` on a cluster with zero PersistentVolumes prints `kubectl delete pv` and
# `aws ec2 delete-volume` here and nowhere else in the document.
# WHAT IT MAY NOT SAY IS "this review ran none of these commands". That is
# false: `collect.sh` runs several of the exact strings printed in these panels -- `sec-6` and `sec-18`
# print `aws iam list-open-id-connect-providers` with no arguments and collect.sh:1162 runs precisely
# that, and `aws ec2 describe-volumes`, `describe-instances`, `describe-nat-gateways`,
# `aws eks describe-addon` and a dozen `kubectl get` lines are all collected commands too. The true and
# sufficient claim is the narrower one: the review is read-only and CHANGED nothing. Every aws/kubectl
# call collect.sh makes is a describe/list/get (its one `aws ec2 --dry-run` is a permission probe), so
# that claim holds; "never ran" does not, and a caveat added to stop the report making an unsupported
# claim must not make one itself.
# SHORT ON PURPOSE. This renders once per open finding, often dozens of times, and a paragraph repeated
# that often is its own defect; the long form stays in the plan, where it is always visible rather than
# behind a <details>.
FIX_CAVEAT = (' <span class="ro">Reference text, not a script to run &mdash; this review is '
              'read-only and changed nothing on this cluster.</span>')


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

    The verbatim jq sits last, behind its own nested toggle. It serves a narrow audience (auditing
    the tool, disputing a finding, maintaining the skill), and above the fix it would push the
    actionable part out of view.
    """
    p, v = prose.get(r["id"], {}), prov.get(r["id"], {})
    state = r.get("state", "?")
    rows = []

    if p.get("rationale"):
        # md_inline(), not e(). The rationale is authored in the same markdown as the remediation and
        # eight of them use `code` spans or **bold**; through e() alone, not the inline renderer, a
        # High-severity caveat emphasised precisely to stand out
        # ("**Above that size it is a performance downgrade unless you provision IOPS.**", cost-9)
        # would print its asterisks and read as a typo. md_inline() escapes BEFORE it emits any markup,
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
            # A field-reading check's `pass` list is the settings it READ, not settings that passed:
            # under the success colour it would label a failing value (`endpointPublicAccess = true`
            # on a Fail) as good. Only a full Pass keeps the success colour; otherwise it is neutral.
            _pc = "ctx" if res.get("kind") == "field" and state != "all" else "ok"
            body += (f'<div class="reshead {_pc}">'
                     f'{e(res.get("pass_label", "Counted as passing"))} '
                     f'({len(res["pass"])})</div>' + _res_list(res["pass"], _pc))
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
            # A list that contradicts its own score is worse than no list. Falling through to
            # `note = ""` would render a contradiction EXACTLY like a not-comparable check, with the
            # run exiting 0 and the absence of a green tick as the only signal. The file's own rule is
            # that absent-by-design must not look like absent-by-accident; this is that rule applied
            # to the contradicted case. DISAGREEMENTS is checked by main(), which exits non-zero.
            #
            # Keyed by question id because a question that appears in BOTH Top priorities and its
            # pillar table renders this panel twice, and appending twice would make the banner and
            # the stderr line report "2 finding(s)" for one contradicted question, listing it twice:
            # a number and the thing it counts, never asserted against each other. Keep the
            # membership test below.
            if r["id"] not in {q for q, _ in DISAGREEMENTS}:
                DISAGREEMENTS.append((r["id"], why))
            note = ('<div class="disagree">&#9888; <strong>Unverified:</strong> this list does not '
                    f'match the count the check reported ({e(why)}). Treat both the list and the '
                    'result as unconfirmed and re-run the detection.</div>')
        elif res.get("context_only"):
            # The verdict came from a cluster setting, and the objects above are listed as context
            # rather than as a pass/fail split. Said plainly, because without it a green High-severity
            # Pass would sit over objects labelled "Counted as passing" by a rule that never ran on
            # them.
            note = ('<div class="unverified">The objects above are <strong>context, not a verdict about '
                    'them</strong>: on this cluster shape the question was settled before any of them '
                    'was counted &mdash; by a cluster setting, or by what the nodes themselves are '
                    '&mdash; and the counting rule this check normally uses never ran. '
                    'There is therefore no total for the report to cross-check, and nothing above '
                    'should be read as an object that passed or failed.</div>')
        elif res.get("kind") == "existence":
            # The name-pattern caveat does NOT live here: inside `if body:` it would reach only the
            # questions an extractor has already produced a list for, the one place it is least
            # needed. It is emitted from the scorer's jq for every name-pattern question, list or no
            # list, in the row below.
            note = ('<div class="unverified">This check answers yes/no rather than counting, so '
                    "there is no total for the report to check this list against. Confirm it by "
                    "eye.</div>")
        elif res.get("kind") == "field":
            note = ('<div class="unverified">This check reads cluster settings rather than counting '
                    "objects. The field paths and their values are printed above so the verdict is "
                    "checkable directly; there is no total to cross-check.</div>")
        else:
            # An honest default, NOT "". A list with no note renders exactly like a cross-checked
            # one, so the strongest and the weakest evidence in the report would look identical and
            # hide a scorer/extractor divergence. sec-30 is the case: its detail ("no port-22
            # rule from 0.0.0.0/0 or ::/0 on the cluster security groups — ...") has no N/M and its `rl`
            # sets no `kind` outside its Auto Mode arm, so its list falls through to here.
            note = ('<div class="unverified">The check reported a result rather than a countable '
                    "total, so the report cannot cross-check this list against it. The list is what "
                    "the detection looked at; confirm it matches what you expect to be in "
                    "scope.</div>")
        rows.append(f"<dt>What we found</dt><dd>{body}{note}</dd>")
    elif res and res.get("unbuilt"):
        # A THIRD KIND OF ABSENCE, and it must not be dressed as either of the other two. The check
        # ran and its verdict above is the check's own; what failed is the separate step that names the
        # objects it counted. That step cannot take the question down with it — but only because `rl`
        # is written to make sure of it, NOT because separating the two programs is enough on its own.
        # It is not: a name program that yields TWO results, or that leaves one of its input files
        # unconsumed (which makes jq re-run the whole program once per unread document), produces
        # multi-line output that `emit`'s `--argjson` rejects, and the SCORER ABORT costs the entire
        # pillar its score. At `sec-21`, for example, security would stop after the 17 records that
        # precede sec-21, while the
        # other four pillars still contribute all of theirs.
        # `rl` refuses anything but a single document, which is why this branch can be honest.
        # Saying "not generated for this question" here would blame the design for a fault, and saying
        # nothing would leave a hole the reader reads as "nothing to show".
        srcs = (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                or "the collected data")
        rows.append(
            '<dt>Resource list</dt><dd><p class="nolist">This question does normally name the objects '
            'it counted, and on this cluster that step <strong>failed</strong> &mdash; so there is no '
            f'list here. The verdict above was produced separately, from {srcs}, and is unaffected: '
            'it is not a finding about your cluster and not a scoring error. Open the section below '
            'and run the command yourself to see the objects. <em>Stated rather than left blank, so a '
            'list that broke is never mistaken for a question that has none.</em></p></dd>')
    elif res is not None and not res.get("context_only"):
        # A FOURTH KIND: the list mechanism RAN and legitimately found nothing. `body` is empty when
        # both lists are, so without this branch the case would fall into the one below and
        # print "Not generated for this question ... an absent list is never mistaken for an empty one"
        # — the exact confusion that sentence promises to prevent, about the exact case it names. It
        # applies to any non-context scorer-list question that finds nothing: `ope-18` lands here wherever a cluster has no CronJobs
        # (`na~no CronJobs`), which makes it the commonest reading of the list field.
        srcs = (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                or "the collected data")
        who = ("The check" if res.get("from_scorer") else "This report's own reading of "
               f"{srcs}")
        rows.append(
            '<dt>Resource list</dt><dd><p class="nolist">'
            f'{who} looked for objects to name here and <strong>found none</strong> on this cluster '
            f'&mdash; the list is empty, not missing. The verdict above came from {srcs}. '
            '<em>Said explicitly, because an empty list and an unwritten one mean different '
            'things.</em></p></dd>')
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
    # ones an extractor happens to produce a list for. Inside `if body:` the disclosure would miss
    # `ope-3`, `ope-8`, `ope-10`, `lens-1`, `lens-4`, `rel-23`, `perf-2`, `lens-2` and `lens-3`,
    # which would then render a bare red "Fail" with no hint that the
    # verdict was a substring match on a resource name — a cluster running Vector, Dynatrace or
    # Jenkins+Kustomize would read as having no logging, no monitoring and no GitOps, with no caveat
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
    # cluster-wide change to make. rbac-4's fix is a `kubectl patch sa` sweep across every non-system namespace;
    # printed directly under its own "Treat both the list and the result as unconfirmed" warning, the
    # two halves of one panel would give opposite instructions, the actionable half winning by default.
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
        rows.append(f"<dt>How to fix{FIX_CAVEAT}</dt><dd>{md_inline(p['remediation'])}</dd>")

    method = [f"<dt>Data read</dt><dd class='src'>"
              + (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                 or "&mdash;") + "</dd>",
              f"<dt>Returned</dt><dd><code>{e(state)}</code>"
              + (f" &mdash; {e(r.get('detail',''))}" if r.get("detail") else "") + "</dd>"]
    if v.get("jq"):
        method.append("<dt>Exact command used</dt><dd><pre>"
                      f"{e(v.get('jq_prelude', '') + v['jq'])}</pre></dd>")
    if v.get("list_jq"):
        # The expression that produced the NAMES shown under "What we found", which is a different
        # program from the one that produced the verdict. Printing only the verdict expression would leave the
        # objects the reader most wants to check as the one claim with no audit trail behind it.
        lf = (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("list_files", [])) or "&mdash;")
        method.append("<dt>Objects named by</dt><dd>"
                      f"<p class='src'>from {lf} &mdash; a separate expression from the verdict "
                      "above, which is why a failure to build this list cannot change the score."
                      f"</p><pre>{e(v.get('list_prelude', '') + v['list_jq'])}</pre></dd>")
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
        ("soon", "Short-term", "High-risk gaps that are mostly covered, plus medium-risk "
                               "controls that are absent or only partly in place."),
        ("later", "Strategic", "Medium-risk controls that are mostly in place, and the low-risk "
                               "practices. "
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
        # if the panel withholds the fix for a contradicted finding and this section prints it in full
        # a few sections later, a reader working the Immediate tier top-down — which is how this
        # section is meant to be used — never sees the withholding at all.
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


def container(title, body, counter=None, desc=None, flush=False, anchor=None):
    c = f' <span class="counter">({e(counter)})</span>' if counter else ""
    d = f'<div class="desc">{e(desc)}</div>' if desc else ""
    # `anchor` exists so a section can be LINKED TO from the top of the report. The boundary
    # disclosures -- what was not assessed, which platforms this applies to, that the review is
    # unofficial -- sit near the end of a long page, and without a link to them a reader
    # who stops at the score never reaches them, which makes the most important caveats
    # in the report the least likely to be read.
    a = f' id="{anchor}"' if anchor else ""
    return (f'<section class="container"{a}><div class="hd"><h2>{e(title)}</h2>{c}{d}</div>'
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
# A `detail` that OPENS with `N/M` is what `b($ok;$t)` emits when the question counted objects, so the
# question passed on its own measurement even where the detail goes on to name Auto Mode. Rule 4
# keeps such answers out of the platform-credit count, and on an all-Auto-Mode cluster it can be
# the only thing keeping one out while several others are credited:
#   `sec-21` on an all-Auto-Mode cluster -- state `all`, names Auto Mode, opens with a ratio:
#   `11/11 encrypted (cluster vols) — every EC2 node is an EKS Auto Mode node, so the root and data
#    volumes AWS attaches at launch are encrypted by design …`
# COPIED BYTE-EXACTLY OUT OF A results.jsonl RECORD: never compose one here. On a cluster with no
# Auto Mode nodes the same question emits `N/M encrypted (cluster vols)` with NO Auto Mode clause,
# so a quote joining that ratio to the Auto Mode clause would describe output no run emits.
# sec-21 is not the only answer rule 4 can exclude, either.
# Rule 4 also excludes `sec-4`,
# whose ratio arm in identity-access.md opens with `N/M` and, scoring `most`/`all`, can name Auto
# Mode one way: all-Auto-Mode with the Network Policy Controller enabled appends `(Auto Mode Network
# Policy Controller enabled …)`. Its mixed-mode caveat, `— but N of M EC2 nodes are EKS Auto Mode nodes,
# whose enforcement is gated separately …`, never needs rule 4: that arm caps the state at `some`
# wherever the ratio would bucket `most`/`all`, so rule 2 already keeps it out of the count.
# Without rule 4 the count silently absorbs any question whose detail merely mentions the platform,
# which would make the number this note publishes wrong in the flattering direction — more credited,
# less measured.
_LEADING_RATIO = re.compile(r"^\s*\d+\s*/\s*\d+")
_AUTO_MODE_RE = re.compile(r"auto mode", re.I)


def platform_credits(measured, sc):
    """Count the answers that passed because AWS manages the function, not because anything was read.

    COMPUTED FROM results.jsonl, NEVER FROM A LIST OF IDS. A hand-maintained set of "the Auto Mode
    questions" would drift the moment a scorer gained or lost an Auto Mode branch — which happened
    twice while this was being written: `net-3` was rewritten and stopped being a credit, and `perf-6`
    became `na` and left the answered denominator. Both moved this count with no edit here, which is
    the point.

    A record is a platform credit when all four hold (references/workflow.md, *Platform-credited answers*):
      1. `track == "measured"`;
      2. `state` is `all` or `most` — the states the report shows as a pass;
      3. its `detail` mentions Auto Mode, the only platform the scorers credit today;
      4. its `detail` does NOT open with a measured ratio. See _LEADING_RATIO above.

    Returns (n, subs) where `subs` is the substitution map for either marked block. The per-pillar
    denominator is that pillar's own `applicable` from scores.json — identical to its measured records
    with a state other than `na` — and `answered` is the sum of those, so this note and the pillar
    table can never quote different totals. Coverage without the credits is the reducer's own formula,
    floor(applicable * 100 / total), with the credits removed from the numerator only.
    """
    by_pillar = {p["pillar"]: p for p in sc.get("pillars", [])}
    credited = {}
    for r in measured:
        detail = r.get("detail") or ""
        if (r.get("state") in ("all", "most")
                and _AUTO_MODE_RE.search(detail)
                and not _LEADING_RATIO.match(detail)):
            credited[r.get("pillar")] = credited.get(r.get("pillar"), 0) + 1
    answered = sum(by_pillar.get(key, {}).get("applicable", 0) for key, _ in PILLARS)
    per_pillar, coverage_without = [], []
    for key, name in PILLARS:
        c = credited.get(key, 0)
        if not c:
            continue
        appl = by_pillar.get(key, {}).get("applicable", 0)
        tot = by_pillar.get(key, {}).get("total", 0)
        per_pillar.append(f"{name} {c} of {appl}")
        cov = (appl - c) * 100 // tot if tot else 0
        # The 50% gate is the reducer's publication rule, so a pillar that drops under it here would
        # have published NO number at all without the credits. That is the difference between "this
        # pillar scored well" and "this pillar could not be scored", and it is the whole reason the
        # count is not cosmetic. (No score is quoted: the contrast is the point, and a stand-in figure
        # reads as a measurement of some cluster and goes stale unnoticed as the scorers change, as
        # any Auto Mode numbers in reliability.md's rel-1 remediation would. rel-1, not
        # rel-9: that block is rel-1's and only REFERS to rel-9, so a pointer naming rel-9
        # aims at the wrong block.)
        coverage_without.append(f"{name} {cov}%" + (
            " (below the 50% coverage gate, so this pillar would report no number)"
            if cov < 50 else ""))
    return sum(credited.values()), {
        "{n}": str(sum(credited.values())),
        "{answered}": str(answered),
        "{per_pillar}": ", ".join(per_pillar),
        "{coverage_without}": ", ".join(coverage_without),
    }


# ---------------------------------------------------------------------------
def _cost_posture(data):
    """(spot, graviton, total Linux EC2 nodes, upgrade-policy support type, Windows EC2 nodes) for
    the cluster under review.

    Fargate nodes carry neither a capacity-type nor an architecture label in the sense these two
    levers mean, so they are excluded from the denominator the same way the compute-mode detection
    elsewhere in this file excludes them — a Fargate-only cluster reports 0 EC2 nodes rather than a
    misleading 0%.

    EKS Hybrid Nodes are excluded for the same reason and one more. Spot is an EC2 purchase option and
    neither `karpenter.sh/capacity-type` nor `eks.amazonaws.com/capacityType` is set on a hybrid node,
    so counting one dilutes the Spot percentage with a machine that could never be Spot. And Graviton
    is AWS silicon: `kubernetes.io/arch=arm64` is reported truthfully by the kubelet on an on-premises
    ARM box, but crediting that as Graviton adoption would be a false credit for hardware the customer
    already bought. Both levers are EC2 levers, so the denominator is EC2 nodes.

    Windows nodes are excluded and counted separately (the scorers' `islinux`): this skill supports
    Linux nodes only, so a Windows node is disclosed as not assessed rather than folded into a ratio.
    """
    ec2_nodes = [n for n in data["nodes"]
                 if _labels(n).get("eks.amazonaws.com/compute-type") != "fargate"
                 and not _is_hybrid(n)]
    win = sum(1 for n in ec2_nodes if _is_windows(n))
    ec2_nodes = [n for n in ec2_nodes if not _is_windows(n)]

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
    return spot, graviton, total, support, win


def _cost_posture_note(data):
    """The lever-posture disclosure, as one `<p>` fragment — called from every place the Cost score
    renders, so the score is never shown without it."""
    spot, graviton, total, support, win = _cost_posture(data)
    lead = ('<strong>Cost Optimization (hygiene):</strong> this score measures whether cost controls '
            'are configured, not total cost efficiency. Spot, Graviton adoption and the '
            'extended-support upgrade policy are not scored &mdash; a cluster that has taken every one '
            'of those three levers reads identically here to one that has taken none. ')
    if not total and win:
        body = (f'Spot/Graviton posture: NOT ASSESSED &mdash; the only EC2 nodes are {e(win)} Windows '
                f'node(s); this skill supports Linux nodes only.')
    elif not total:
        body = "This cluster has no EC2 nodes to measure Spot/Graviton posture against."
    else:
        pct = lambda n: round(100 * n / total)
        body = (f'Measured posture: {e(spot)}/{e(total)} Linux EC2 node(s) on Spot ({pct(spot)}%), '
                f'{e(graviton)}/{e(total)} on Graviton ({pct(graviton)}%)'
                + (f' ({e(win)} Windows node(s) not assessed &mdash; this skill supports Linux nodes '
                   f'only)' if win else '') + '. '
                f'Upgrade policy (upgradePolicy.supportType &mdash; what happens at the end of standard '
                f'support, not whether this version is in it): {e(support)}.')
    return f'<p class="small muted">{lead}{body}</p>'


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def build(data, prose, prov, blocks, toggle=True):
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
    # READ from scores.json, never recomputed. Deriving the ratios and applying the withhold here
    # would make the renderer a second implementation of a rule the reducer
    # owns — and two implementations can disagree: `reduce.sh` emitting a number for an all-NotReady cluster
    # while the HTML withholds it would let the chat and markdown surfaces publish the number the report
    # refuses to. Deriving it in one place, and only reading it here, keeps the surfaces in step.
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

    # `nodes_total`/`nodes_ready` count Linux nodes only (reduce.sh excludes Windows nodes, which this
    # skill does not assess), so every place they render says "Linux node(s)". The compute-mode label
    # below describes the whole fleet, so it adds the Windows nodes back.
    win_nodes = sum(1 for n in data["nodes"] if _is_windows(n))
    all_nodes = node_count + win_nodes
    # The standard Windows disclosure, for the liveness wording below: with Windows nodes present,
    # "0 Linux nodes" does not mean nothing ran, only that nothing this review assesses did.
    win_note = (f" ({win_nodes} Windows node(s) not assessed \u2014 this skill supports Linux nodes only)"
                if win_nodes else "")
    fargate_nodes = sum(1 for n in data["nodes"]
                        if (n.get("metadata", {}).get("labels") or {})
                        .get("eks.amazonaws.com/compute-type") == "fargate")
    hybrid_nodes = sum(1 for n in data["nodes"] if _is_hybrid(n))
    # Nodes that really are EC2 instances in this account: neither Fargate nor hybrid.
    ec2_like = all_nodes - hybrid_nodes - fargate_nodes
    # NAMED, not folded into "Standard". "Standard" reads as EC2 compute in an AWS account, and a
    # reader who takes it that way will read every node-population answer below as describing EC2
    # instances -- which on such a cluster is the one thing they do not describe. The node-scoped
    # questions exclude hybrid nodes and say so per question; this is the same fact at the top.
    #
    # EVERY branch that can coexist with hybrid nodes has to name them. Two ways to get it wrong:
    # "EKS Auto Mode" swallowing the hybrid nodes silently (the exact case where the
    # scorers' all-Auto-Mode arms do not fire, so the label would contradict the findings), and
    # "Standard + EKS Hybrid Nodes" firing on a Fargate + hybrid cluster with zero EC2 nodes, where
    # "Standard" names a population that does not exist.
    hyb = " + EKS Hybrid Nodes" if hybrid_nodes else ""
    if cl.get("computeConfig", {}).get("enabled") is True:
        mode = "EKS Auto Mode" + hyb
    elif data["fargate"] and fargate_nodes == all_nodes and all_nodes:
        mode = "Fargate only"
    elif hybrid_nodes and hybrid_nodes == all_nodes:
        mode = "EKS Hybrid Nodes"
    elif hybrid_nodes and fargate_nodes and not ec2_like:
        mode = "Fargate + EKS Hybrid Nodes"
    else:
        mode = "Standard" + hyb

    out = []

    # ---- top navigation -----------------------------------------------------
    out.append(
        '<div class="top-nav"><span class="product">EKS Well-Architected Review</span>'
        f'<span class="sep">/</span><span class="ctx">{e(cl.get("name","(unknown cluster)"))}</span>'
        f'<span class="sep">/</span><span class="ctx">{e(region or "unknown region")}</span>'
        f'{TOGGLE_HTML if toggle else ""}</div>')

    out.append('<div class="layout stack">')

    # ---- page header --------------------------------------------------------
    # The header counts scored, not-applicable, could-not-be-assessed and governance questions
    # separately. An `na` is not an answer: a question that did not apply was NOT answered, one whose
    # `na` na_reason() classes `unobserved` may well apply but this review cannot answer it (out of
    # scope, such as a Windows population, or not in the collected data), and the governance questions
    # are never asked at all. Four different states, four different words. Every figure in the sentence
    # comes from this run's own records (`n_scored`, `na_recs`, `governance`), so a reader can re-derive each
    # one from results.jsonl.
    out.append(
        '<div class="page-header" style="display:flex;align-items:flex-end;gap:var(--space-m);'
        'flex-wrap:wrap"><div><h1>Well-Architected review</h1>'
        f'<p>Deterministic review of <code>{e(cl.get("name",""))}</code>. '
        f'Of {len(measured) + len(governance)} questions: <strong>{n_scored} scored</strong> from one '
        f'data collection, {len(na_recs) - na_split(na_recs, ec2_like > 0)[2]} did not apply to this cluster, '
        f'{na_split(na_recs, ec2_like > 0)[2]} could not be assessed from the collected data (never a pass), and '
        f'{sum(1 for g in governance if g.get("state") == "unknown")} were '
        f'not assessed (governance questions, not measured &mdash; the '
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

    # ---- reference-prose defect banner -----------------------------------------------------------
    # Remediation text this renderer could not read out of a reference file. Known before build() runs
    # (question_prose() fills PROSE_DEFECTS), rendered here so it sits above the tables with the other
    # banners. A line on stderr alone is one nobody holding only the HTML ever sees, and the
    # symptom in the report would be an empty "How to fix" panel, indistinguishable from a question that
    # legitimately has no fix. Naming the question here is what makes the two tellable apart.
    if PROSE_DEFECTS:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            # "problem(s)", not "question(s)": this counts ENTRIES, and two aggregate entries are not
            # one question each: the scored-coverage one stands for as many questions as are missing
            # and a per-file one for that file's whole set, so "question(s)" would put "1 question(s)"
            # above a line naming dozens. Counting "problem(s)" is true for every entry shape, and
            # each <li> still states its own scale.
            f'<div><h3>{len(PROSE_DEFECTS)} problem(s) with question fix text</h3>'
            '<ul class="plain">'
            + "".join(f'<li><code>{e(qid)}</code> in <code>references/{e(src)}</code> {e(why)}</li>'
                      for src, qid, why in PROSE_DEFECTS)
            + '</ul><p class="small">The text exists in the reference file named above; this renderer '
              'could not extract it, so the panel below is missing content rather than reporting that '
              'there is none. The renderer exits non-zero when this banner appears.</p></div></div>')

    # ---- unprintable-prelude banner -------------------------------------------------------------
    # A scorer calls a definition its own file supplies, and the panel below will print the call without
    # the definition -- so a reader cannot re-run the judgement. Fires on any break in the `PE='def …'`
    # shape, including the ones `^PE='` itself cannot see. Banner and not stderr for the usual reason:
    # the symptom in the report is a panel that looks complete.
    _shadow = PRELUDE_SHADOW
    if _shadow:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>A scorer prelude could not be read, so some panels below print a program that '
            'will not run</h3><ul class="plain">'
            + "".join(f'<li><code>{e(q)}</code> calls <code>{e(n)}</code>, defined in a prelude in '
                      f'<code>references/{e(f)}</code> that this renderer could not extract</li>'
                      for f, q, n in _shadow)
            + '</ul><p class="small">The verdicts are unaffected &mdash; the scorer ran with the '
              'definitions. What is lost is the audit trail: "Exact command used" shows a call with no '
              'definition, which a reader cannot paste and run. The prelude line must read exactly '
              "<code>PE='def &hellip;'</code> with no leading space, nothing between the quote and "
              '<code>def</code>, nothing after the closing quote, and all on one line. That applies to '
              "every prelude assignment in a scorer block &mdash; <code>B='def b(&hellip;)'</code> as "
              "much as <code>PE='def gkenf:&hellip;'</code>.</p></div></div>")

    # ---- disclosure-set drift banner --------------------------------------------------------------
    # A question that stops carrying the "detected by matching a regular expression" caveat loses it
    # SILENTLY: the panel simply renders one fewer paragraph, which no reader can notice. That is why
    # this is a banner and not only a line on stderr -- the same reason given for the block just above.
    # The message says what happened and does not claim to have refused, because the report below IS
    # published; the renderer exits non-zero so a pipeline still fails.
    _lost, _gained = disclosure_drift(prov)
    if _lost or _gained:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>The regex/heuristic disclosure set has changed</h3><ul class="plain">'
            + "".join(f'<li><code>{e(q)}</code> no longer carries the disclosure &mdash; confirm '
                      'whether its detection changed or its reference file could not be read</li>'
                      for q in _lost)
            + "".join(f'<li><code>{e(q)}</code> now carries the disclosure and did not before</li>'
                      for q in _gained)
            + '</ul><p class="small">Each entry is a question whose panel below discloses more, or less, '
              'about how its verdict was reached than it did on the reviewed tree. A lost disclosure is '
              'the serious direction: the finding still rests on a pattern match, but the report below '
              'no longer says so. Decide which is right and update <code>_DISCLOSED_EXPECTED</code> in '
              'render-report.py, or restore the detection. This report is published as it stands.'
              '</p></div></div>')

    # ---- liveness alerts (SKILL.md Step 4) --------------------------------
    # Above the summary, because a score read without them is misleading. Step 4 is explicit that
    # this is "a disclosure, not a refusal": a cluster mid-upgrade legitimately shows NotReady nodes
    # and a batch cluster legitimately sits at zero running pods, so the wording states what was
    # observed and leaves the judgement to the reader.
    if not_viable:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>NOT VIABLE &mdash; no data plane</h3>'
            f'<p>This cluster had <strong>0 Linux nodes</strong> when collected{e(win_note)}, so '
            + ('nothing this review assesses was running on it' if win_nodes else 'nothing was running on it')
            + ' and <strong>no overall score</strong> is published. The pillar scores below '
            '<em>are</em> published, and describe what the cluster <em>declares</em> — '
            + ('nothing they assess was running' if win_nodes else 'its workloads were not running')
            + ' when collected. They are worth acting on; they are not comparable to a '
            'running cluster’s.</p>'
            + (f'<p class="small">Configuration alone would have scored {e(suppressed)}/100. That '
               'number is stated here rather than as the verdict, because a cluster with no Linux '
               'nodes cannot be said to score anything.</p>' if isinstance(suppressed, (int, float)) else "")
            + f'<p class="small">{wl_pod_count} workload pod(s) are declared.'
            + ('' if win_nodes else ' Pods without nodes are manifests, not running software.')
            + '</p></div></div>')
    elif no_node_ready:
        out.append(
            '<div class="alert alert-error"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>NOT HEALTHY &mdash; no Linux node is Ready</h3>'
            f'<p>{node_count} Linux node(s) exist{e(win_note)} and <strong>0 are Ready</strong>, so the technical '
            'overall is withheld: the pillar scores below describe the configuration this cluster '
            '<em>declares</em>, and nothing here shows whether it can run a '
            + ('Linux workload' if win_nodes else 'workload') + '.</p>'
            # `reduce.sh` populates `suppressed_overall` identically for NOT VIABLE and NOT HEALTHY,
            # so this branch discloses it exactly as the NOT VIABLE banner above does. Same
            # framing as that branch: the number is context for why the withholding matters, not the
            # verdict, and SKILL.md Step 7 forbids presenting it as the headline.
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
        # "Too little of this cluster is observable" is the wrong diagnosis for the common case. On a
        # 1-node cluster with no workload pods, every `na` under Reliability and Performance reads
        # "no workload Deployments" / "no workload containers": nothing was unobservable, there was
        # nothing there to observe. The three reasons are counted and named instead of merged.
        below_na = [r for r in na_recs
                    if r.get("pillar") in {k for k, _ in insufficient}]
        n_struct, n_nosub, n_unobs = na_split(below_na, ec2_like > 0)
        why_bits = []
        if n_nosub:
            why_bits.append(f"{n_nosub} have no subject on this cluster (nothing of that kind is "
                            f"deployed, so there was nothing to measure &mdash; not something that "
                            f"could not be seen)")
        if n_struct:
            why_bits.append(f"{n_struct} can never apply to a cluster built this way")
        if n_unobs:
            why_bits.append(f"{n_unobs} could not be assessed from the collected data")
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
    # rather than the facts table so no score can be read without them. Windows nodes are named here
    # too, in the standard disclosure wording: the node count beside the score is Linux-only, and a
    # reader of the headline alone must not take it for the whole fleet.
    live_cls = "live bad" if (no_node_ready or most_pods_down) else "live"
    win_head = (f' &middot; {win_nodes} Windows node(s) not assessed &mdash; this skill supports Linux '
                'nodes only' if win_nodes else '')
    live_html = (f'<span class="{live_cls}">{node_count} Linux node(s) ({nodes_ready} Ready){win_head}'
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

    # Every value taken from scores.json goes through e(), not just the ones sourced from the cluster -- the
    # coverage cell and the governance counts included: an unescaped scores.json holding `<script>` would
    # EXECUTE in the rendered report. scores.json is machine-written, so this is a consistency rule rather
    # than a live injection path — but it is the kind that stops being theoretical the moment anything
    # downstream starts editing that file.
    rows = []
    thin_cover = []
    no_band = []
    # NOT VIABLE LABELS the pillar numbers; it does not withhold them. Both directions carry a real cost, so
    # the reasoning is recorded rather than the conclusion alone.
    #
    # Withholding every pillar score on a 0-node cluster answers a real hazard: the
    # questions the missing objects would have failed become `na` and leave the
    # denominator, so the emptier the cluster the fewer ways its score can be pulled down
    # — a synthetic shape of orphaned pods can score Operational Excellence ABOVE a
    # healthy synthetic one, which on a trend chart reads as improvement during an
    # outage.
    #
    # But withholding all five numbers would leave the operator of a cluster mid-setup — a legitimate review
    # target, and arguably the reader best served by a configuration review — with a banner and a question
    # count. And on a REAL 0-node cluster the effect usually runs the other way, with pillar scores well
    # below a healthy sibling's, because a cluster still being built genuinely has less configured. So the
    # hazard is a comparison hazard, not a correctness one, and the answer is to say so where the numbers
    # are: every score is published, every one is labelled "declared configuration only", the risk chip
    # carries "(config only)" so it cannot travel out of the table meaning something else, and the caption
    # states the numbers are not comparable to a running cluster's.
    #
    # The OVERALL stays withheld — one headline number for a cluster nothing runs on is the claim that
    # cannot be made honestly — and `technical_overall` is still the string reduce.sh emitted. This
    # makes NOT VIABLE consistent with the NOT HEALTHY row beside it, which also labels rather than
    # withholds; the two rows differ only in wording, not in what the report gives the reader.
    # `label_pillars` is not `not_viable` ALONE: without the NOT HEALTHY branch -- nodes exist and
    # none of them is Ready -- the pillar rows would render BYTE-IDENTICAL to a healthy cluster's: no
    # chip qualifier, no caption, no per-pillar subtitle note, while the hero directly above reads "3
    # node(s) exist and 0 are Ready, so the technical overall is withheld: the pillar scores below
    # describe the configuration this cluster declares". The banner would promise a label the table
    # does not carry, and SKILL.md's reporting table makes the same promise. This is the MORE
    # dangerous of the two cases, because the hero states a node count that makes the cluster look
    # alive.
    label_pillars = not_viable or no_node_ready
    # The two cases need different words, and reusing NOT VIABLE's would introduce a
    # false statement. NOT VIABLE has no Linux nodes, so nothing this review assesses was running (a
    # Windows node, if present, is not assessed and is disclosed where this is said). NOT HEALTHY
    # HAS nodes -- the configuration is on them -- but nothing on them is Ready to serve, so the claim is
    # about what is RUNNING, not about what is deployed; "this cluster has 0 nodes" would be a lie on a
    # 3-node cluster.
    label_chip = "(config only)" if not_viable else "(nothing Ready)"
    label_head = ("declared configuration only" if not_viable
                  else "declared configuration only \u2014 no Linux node is Ready")
    n_also_uncovered = sum(1 for key, _ in PILLARS
                           if not isinstance(by_pillar[key].get("score"), (int, float)))
    for key, name in PILLARS:
        p = by_pillar[key]
        s = p.get("score")
        appl, tot = p.get("applicable", 0), p.get("total", 0)
        rk, rl = risk(s)
        if label_pillars and isinstance(s, (int, float)):
            # A bare "Low risk" chip beside a cluster nothing runs on is the one cell in this table that
            # would be read as reassurance. The band is kept -- it is what the score says -- and
            # qualified in place, so the chip cannot travel out of the table meaning something else.
            rl = f"{rl} {label_chip}"
        # Two statements, not one conditional expression, so that the
        # Score-cell placeholder stays on one line: the "No band
        # published" literal is written ONCE for the Score cell, on its own
        # line, so it is greppable. risk() (the Risk chip) and the no_band
        # note below carry the same words as separate strings; nothing ties
        # them together automatically, so it is maintained BY HAND. If you
        # fold this into one expression or reword it, update those two in
        # step.
        shown = f"{s}" if isinstance(s, (int, float)) else "No band published"
        pillar_na = [r for r in na_recs if r.get("pillar") == key]
        n_struct, n_nosub, n_unobs = na_split(pillar_na, ec2_like > 0)
        # THE THIN-EVIDENCE TEST RUNS ON QUESTIONS THAT COULD STILL BECOME MEASURABLE. A pillar that
        # only just cleared the 50% gate can still show a TOP band — at 1 applicable question of 2,
        # a single `all` renders "100 · Excellent · Low risk" off one observation — so the marker
        # exists to stop a thin band reading as a strong one. Measured against the RAW total it
        # would fire on clusters whose evidence is not thin: four of Operational Excellence's
        # questions are structurally `na` on non-Fargate compute (fargate-1, -2 and -4, plus ope-12
        # deduplicated against ope-6), so raw OpEx coverage cannot exceed 14/18 = 77% there, and two
        # ordinary `na`s put it at 12/18 = 66% -- under the marker's own 70% threshold, although
        # OpEx has answered 12 of the 14 questions that CAN apply (86%). The marker would then label
        # a genuinely broken OpEx score "provisional, not a verdict", pre-discounting a real
        # failure. Structurally-inapplicable questions are excluded from the denominator; the
        # published score and the published `coverage` are untouched, this decides only whether a
        # caveat is shown.
        eff_tot = max(tot - n_struct, appl)
        eff_cov = round(100 * appl / eff_tot) if eff_tot else 0
        thin = isinstance(s, (int, float)) and eff_cov < 70
        if thin:
            thin_cover.append((name, appl, eff_tot, eff_cov, s, n_struct))
        if not isinstance(s, (int, float)):
            no_band.append((name, appl, tot, n_struct, n_nosub, n_unobs))
        # e() on every one of these too. A title="" attribute is still an HTML sink: an unescaped value here
        # breaks out of the attribute and injects live markup, exactly as it would in the coverage cell or
        # the governance counts.
        mark = (' <span class="thin" title="Scored from '
                f'{e(appl)} of the {e(eff_tot)} questions that can apply to this cluster '
                f'({e(eff_cov)}%) — a narrow basis for this band.">thin&nbsp;evidence</span>'
                ) if thin else ""
        # The coverage cell counts governance questions as well as MEASURED ones. Counting measured
        # questions only, Reliability would read "23 / 23" — 100%, nothing left to look at — while five
        # governance questions in that pillar, one of them the High-severity backup question, have never
        # been assessed at all. The process questions are in the denominator and named, because "100%" next
        # to an unassessed backup question is the single most misleading cell in this report.
        # The note counts only the questions still `unknown` -- the header's and the Governance
        # section's definition of "not assessed".
        gov_n = len(gov_by_pillar[key])
        gov_unk = sum(1 for g in gov_by_pillar[key] if g.get("state") == "unknown")
        cover_cell = f'{e(appl)}&thinsp;/&thinsp;{e(tot + gov_n)}'
        if gov_unk:
            cover_cell += (f'<div class="small muted" style="white-space:normal">{e(gov_unk)} process '
                           f'question(s) not assessed</div>')
        rows.append(
            f'<tr><td>{e(name)}</td>'
            f'<td class="num">{e(shown)}</td>'
            f'<td>{bar(s)}</td>'
            f'<td>{e(rating(s))}{mark}</td>'
            f'<td>{si(rk, rl)}</td>'
            f'<td class="num">{cover_cell}</td></tr>')
    # Computed here so the <tfoot> row below can quote it. `platform_credits()` derives the count
    # from results.jsonl and scores.json; the WORDS all come from SKILL.md, so the two documents cannot
    # say different things about what a platform credit is.
    n_credited, credit_subs = platform_credits(measured, sc)
    credit_html = skill_block_html(
        blocks, "PLATFORM-CREDIT-NOTE" if n_credited else "PLATFORM-CREDIT-NONE", credit_subs)
    # The config-not-behaviour caveat belongs on the pillar table, not only on the OVERALL score: the pillar
    # table is the part of this report that gets screenshotted and forwarded. A <caption> travels with the
    # table — in a screenshot, in a copy-paste, in print — which a note above or below it does not.
    table = (
        '<div class="tablewrap"><table><caption class="tbl-caveat">Configuration only '
        '&middot; not behaviour or compliance '
        '&mdash; every pillar score below states which settings were found at collection time, not '
        'whether they work, are effective, or were tested.</caption>'
        '<thead><tr><th>Pillar</th><th class="num">Score</th><th></th>'
        # "Coverage" here and the chat/markdown headline's own "coverage" percentage are two different
        # numbers under one word: this cell is applicable/(total+governance) -- for an Operational
        # Excellence pillar with 14 applicable of 18 measured questions and 6 governance ones it renders
        # `14 / 24` -- while the 50% publication gate that headline quotes is applicable/measured-total, 14
        # of 18. THIS CELL PRINTS NO PERCENTAGE AT ALL, and the two percentages behind it are not
        # symmetrical: `77%` is reduce.sh's `coverage` field for that pillar, published in the chat
        # summary, while 14/24 as a percentage is published nowhere -- not in the HTML, not in the chat
        # summary. Naming it as though the page printed it would re-create the confusion the column rename
        # exists to stop. If you divide it yourself, floor it (14*100//24 = 58) so it is comparable with
        # the reducer's.
        # TWO ROUNDING CONVENTIONS SHIP. Say which one any figure came from:
        #   FLOORED -- reduce.sh's `coverage` field, `(($ac*100/$tot)|floor)`, which reaches the chat
        #     summary; and platform_credits()'s coverage-without-credits, `(appl - c) * 100 // tot`.
        #   ROUNDED -- `eff_cov = round(100 * appl / eff_tot)` behind the thin-evidence tooltip, and
        #     `pct = lambda n: round(100 * n / total)` behind the Spot/Graviton posture line. BOTH reach
        #     the reader, so "the pipeline floors its percentages" is false: a pillar at 7 of 11 publishes
        #     64% in that tooltip where the floor is 63.
        # Both denominators are disclosed elsewhere on the page
        # (the executive-summary prose above, and the "N process question(s) not assessed" note inside
        # the cell itself), so this is a naming fix, not a second caveat: renaming the column stops the
        # HTML and the chat headline from printing different values under the same word.
        '<th>Rating</th><th>Risk (from score)</th><th class="num">Questions answered</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        # The platform-credit count, as a full-width row INSIDE the table rather than a note after
        # it, for the same reason the caveat above is a <caption> — this table is the part of the report
        # that gets screenshotted and forwarded, and a note outside it does not travel. Exactly one of
        # the two marked blocks prints: NOTE when there is at least one credit, NONE when there is not,
        # so the reader is never left to infer that a report with no note had nothing to disclose.
        f'<tfoot><tr><td colspan="6" class="tbl-note">{credit_html}</td></tr></tfoot>'
        '</table></div>')
    if thin_cover:
        # e() on a/t/c too. Escaping the name and the score but not the counts would leave the injection
        # open: the same three values feed three different sinks (the coverage cell, the row's title
        # attribute, and this note) and all three need it.
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
        # Not "Insufficient coverage / too little of this cluster is observable" for an empty cluster,
        # whose every `na` reads "no workload Deployments". Say which of the three it was.
        bits = []
        for n, a, t, st, ns, un in no_band:
            parts = []
            if ns:
                parts.append(f"{e(ns)} had no subject on this cluster")
            if st:
                parts.append(f"{e(st)} can never apply to a cluster built this way")
            if un:
                parts.append(f"{e(un)} could not be assessed")
            bits.append(f"<strong>{e(n)}</strong> answered {e(a)} of {e(t)} measured questions"
                        + (" (" + ", ".join(parts) + ")" if parts else ""))
        table += ('<p class="small muted"><strong>No band published:</strong> ' + "; ".join(bits) +
                  '. A pillar needs half its measured questions to apply before a number is '
                  'published. Where the reason is that nothing of that kind is deployed, nothing was '
                  'unobservable &mdash; there was nothing there to observe, and the questions that '
                  'did apply were all asked and are listed below.</p>')
    if label_pillars and not not_viable:
        # NOT HEALTHY: nodes exist, so the "0 nodes" sentence below would be false. What is true here is
        # that nothing on those nodes is Ready, so every answer is about what the cluster DECLARES and
        # none of it about what it is actually doing.
        table += ('<p class="small muted"><strong>Declared configuration only &mdash; no Linux node '
                  'is Ready:</strong> this cluster has '
                  f'<strong>{e(node_count)} Linux node(s) and none of them is Ready</strong>{e(win_note)}, '
                  + ('so nothing it declares is serving on a Linux node. ' if win_nodes
                     else 'so nothing it declares is currently serving anything. ')
                  + 'Every pillar number above grades the '
                  'configuration as written and is worth acting on &mdash; but it is <strong>not '
                  'comparable to a running cluster\u2019s score</strong>, and must not be plotted on a '
                  'trend beside one. The overall score is withheld for that reason; the pillar numbers '
                  'are labelled instead of hidden because an operator recovering a cluster needs them.'
                  + (f' {e(n_also_uncovered)} of the five did not clear the coverage gate.'
                     if n_also_uncovered else "")
                  + '</p>')
    elif label_pillars:
        # Stated where the numbers are, because this table is the part of the report that gets
        # screenshotted away from the banner above it.
        table += ('<p class="small muted"><strong>Declared configuration only:</strong> this cluster had '
                  f'<strong>{e(node_count)} Linux nodes</strong> when collected{e(win_note)}, so '
                  + ('nothing this review assesses was running. ' if win_nodes
                     else 'none of its workloads were running. ')
                  + 'Every pillar number above grades the configuration as written and is worth acting on '
                  '&mdash; but it is <strong>not comparable to a running cluster\u2019s score</strong>, '
                  'and must not be plotted on a trend beside one: every question the missing objects '
                  'would have failed becomes <em>not applicable</em> and leaves the denominator, so the '
                  'emptier the cluster, the fewer ways these numbers can be pulled down. The overall '
                  'score is withheld for that reason; the pillar numbers are labelled instead of hidden '
                  'because an operator building a cluster needs them.'
                  + (f' {e(n_also_uncovered)} of the five did not clear the coverage gate.'
                     if n_also_uncovered else "")
                  + '</p>')
    # Beside the Cost score here too — this is the first place in the report the score appears.
    table += _cost_posture_note(data)
    # SKILL.md's own "How to read this score" paragraph, printed verbatim directly under the
    # headline number and above the pillar table. Two bullets in that file explain that the overall is
    # an equal-weight average of pillars holding 9 to 42 questions, so it tracks question count rather
    # than risk, and that the Rating and Risk labels are the same number restated — facts about this
    # skill's own arithmetic that every reader of the number needs. It is
    # OUTSIDE every withholding branch on purpose: NOT VIABLE, NOT HEALTHY and the coverage-gate
    # WITHHELD paths all reach this line, because a reader who is told no number could be published
    # still needs to know what the number would have meant. Nothing here can shorten it — a missing
    # block renders an alert naming the marker and exits non-zero.
    score_note = (f'<div class="score-note">{skill_block_html(blocks, "SCORE-DISCLOSURE")}</div>')
    # A POINTER, NOT A SECOND COPY. The boundary disclosures are the part of this report most likely to
    # change what a reader concludes and least likely to be reached: they sit near the end of the
    # document, far below the score. Duplicating the text here would create exactly the drift this file
    # is built to prevent, so this is one line naming what is down there and a link to it.
    boundary_link = (
        '<p class="score-note"><strong>Before you act on this number, read '
        '<a href="#method">Method and boundaries</a></strong> at the end of this report: which '
        'Well-Architected areas have <em>no question here at all</em> (they are gaps, not passes), '
        'which platforms this review does and does not judge (Windows nodes and Windows pods are not '
        'assessed &mdash; Linux nodes only), the severity weights being this '
        'skill&rsquo;s own editorial judgement rather than an AWS classification, and that this is not '
        'the AWS Well-Architected Tool.</p>')
    out.append(container("Executive summary",
                         f'<div class="bd" style="padding:0 0 var(--space-l)">{hero}{score_note}'
                         f'{boundary_link}'
                         f'</div>' + table,
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
        ("Linux nodes", f"{node_count} ({nodes_ready} Ready)"),
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
            # An `na` na_reason() classes `unobserved` is not "not applicable": the question may well
            # apply and this review cannot answer it, so its badge says so (_unobs_label).
            f'<td>{si("inactive", _unobs_label(r.get("detail"))) if r.get("state") == "na" and na_reason(r.get("detail"), ec2_like > 0) == "unobserved" else si(*STATE_UI.get(r.get("state"), ("inactive", r.get("state","?"))))}</td>'
            f'<td class="detail">{e(r.get("detail",""))}'
            f'{evidence_panel(r, prose, prov, data)}</td></tr>' for r in qs)
        s = p.get("score")
        # Withheld here too, or the number the summary table refuses to publish is published one
        # section down in this pillar's own subtitle.
        head = (f'{s}/100 ({label_head})'
                if label_pillars and isinstance(s, (int, float))
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
        # Dozens of mutating commands (kubectl delete pv, aws ec2 delete-volume, aws ec2
        # revoke-security-group-egress, a mesh-wide PeerAuthentication STRICT, ...) sit directly under
        # measured evidence here, in a plan with schedule-shaped tier names ("Immediate", "Short-term").
        # THIS IS THE LONG FORM, AND IT IS NOT THE ONLY ONE. Scoping the caveat to this section alone
        # would miss most of them: the identical remediation text renders in the Top-priorities table and in
        # every per-pillar findings table, both EARLIER in the document, and an `na` finding never
        # reaches this section at all. `FIX_CAVEAT` travels with the remediation in
        # evidence_panel(). This copy stays because it is always visible rather than behind a
        # <details>, and because it is the one that also names the change process.
        readonly_note = (
            '<p class="small muted" style="margin:0 0 var(--space-m)">This review is '
            '<strong>read-only</strong>: nothing on this cluster was changed to produce it, and none '
            'of the commands below has been run or tested against this cluster. Apply them through '
            'your own change process, not directly from this page.</p>')
        plan_html = readonly_note + plan_html
        out.append(container(
            "Improvement plan", plan_html,
            counter=f"{n_open} open item(s)",
            # PLAIN PROSE, NO MARKDOWN. container() renders `desc` through e() only -- as it must,
            # because every other caller hands it plain text -- so a backtick-quoted word here would
            # print its backticks in every report. Rewriting the one literal is a
            # tighter bound than routing eight callers' `desc` through md_inline().
            # AND IT MAY NOT SAY "every question not scoring a full Pass" EITHER, which is false.
            # open_items above filters on `order`, i.e. {none, some, most} ONLY, so `na` and the
            # governance `unknown` questions never enter this section. Count the results.jsonl records
            # whose state is not `all` and compare with this section's own counter: the gap is every
            # `na` and every governance question, typically dozens -- questions that sentence would
            # claim are listed here and are not, in a section a reader works top-down as a checklist.
            # The three names below are the exact STATE_UI labels in the Result column, so a row can be
            # matched by eye, and the populations that are NOT here are named with where they are
            # instead -- the `na` rows by their Result-column labels, "Not applicable", "Not assessed"
            # and "Not observed".
            desc="Every question that scored Fail, Partial or Mostly, tiered by risk weight and how "
                 "far short the result fell, with the remediation from the reference for that "
                 "question. Passes and not-applicable, not-assessed or not-observed results stay in the pillar "
                 "tables above; the "
                 "governance questions this review does not measure are in the Governance "
                 "section. Effort is deliberately not estimated — it depends on the environment, "
                 "not on the collected data."))

    # ---- governance --------------------------------------------------------
    # The unassessed questions are NAMED here, grouped by the pillar whose coverage cell they are missing
    # from. Describing the category only in the abstract ("29 governance questions — Not Assessed") would leave a
    # reader unable to find out WHICH questions had gone unasked — and unable to discover that one of
    # Reliability's five is the High-severity backup question, in a pillar whose measured questions would
    # otherwise read as fully covered.
    # Listed in full, not through _res_list(): these are the whole point of the section, so the
    # MAX_LIST cap (and its "run the command below" tail, which has no command here) must not apply.
    # Grouped by WHY each was not assessed (GOV_UNASSESSED), not by pillar — one blanket reason for all
    # 29 would be false for several of them, and a reader deciding between "not verifiable by automated
    # review" and "not verified" needs the difference. The pillar is kept on every line, because that
    # is what the coverage cells above are missing these questions from.
    # Only `unknown` records: this section lists the questions that were not assessed.
    pillar_name = dict(PILLARS)
    gov_by_group = {}
    for r in [x for x in governance if x.get("state") == "unknown"]:
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
    body = (
        '<div class="alert alert-info"><span class="ico" aria-hidden="true">&#8505;</span>'
        f'<div><h3>{e(g.get("total",len(governance)))} governance questions'
        ' &mdash; Not Assessed</h3>'
        # No "incident response, DR testing" here: NO question among these asks about either.
        # rel-10/rel-12 ask whether snapshot objects and schedules are configured, not whether a
        # restore was ever tested. Advertising those domains would tell a reader they are in scope.
        # The domains named here are ones a listed question covers.
        '<p>These questions are not measured. Between them they '
        'cover infrastructure-as-code and manifest templating, upgrade planning and capacity '
        'review, change management, environment separation, RBAC and cluster-creation practice, '
        'secret and certificate rotation, compliance scanning, image signing, backup and snapshot '
        'configuration, EFS encryption, and cost-visibility practice. '
        '<strong>Why each one was not assessed differs, and is stated per question below</strong> '
        '&mdash; for some, nothing in the collected output states the answer; for others the '
        'answer is one uncollected API call away, or is already in the data this run wrote.</p>'
        '<p class="small">They were not guessed and are excluded from every score above. '
        'They are also '
        'excluded from every pillar <em>score</em>, but they are counted in the coverage cells '
        'above, so a pillar showing full coverage of its measured questions still has these '
        'open.</p>'
        + (f'<div class="evidence-panel" style="margin-top:var(--space-s)">{gov_ids}</div>'
           if gov_ids else "")
        + '</div></div>')
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
        # The bands are b() in every pillar file's scorer prelude, and reduce.sh's state<->ratio gate
        # refuses any measured record leading with `n/m` whose state disagrees with them, bar RATIO_STATE_EXEMPT.
        '<li>Where a result leads with a count <em>x</em>/<em>y</em>, its state is a band on the share '
        'that passes: <strong>Pass</strong> (<code>all</code>) at 90% or more, <strong>Mostly</strong> '
        '(<code>most</code>) at 70% or more, <strong>Partial</strong> (<code>some</code>) above 0%, '
        '<strong>Fail</strong> (<code>none</code>) at 0%. A Pass therefore need not mean every object '
        'passed: any listed under &ldquo;Counted as failing&rdquo; still fail. <code>podsec-1</code> to '
        '<code>podsec-5</code> are not banded: one offending container or pod fails them.</li>'
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
        # The volume half follows the two selectors: `cost-8` reads a cluster tag or a PV's volume id,
        # `sec-21` those OR an attachment to one of this cluster's EC2 nodes -- so neither
        # fits both, and SKILL.md's Scope line splits them the same way. `select(isec2)` is why this says
        # EC2 nodes: a hybrid node's disks are not in the instance-id set sec-21 builds, and widening
        # the wording past the selector would be the same defect in the other direction.
        '<li>Object checks assess cluster-owned resources only: workload namespaces (AWS-managed '
        '<code>kube-*</code>/<code>amazon-*</code> excluded), custom RBAC roles, volumes tagged '
        'to this cluster or named by one of its PersistentVolumes (for <code>sec-21</code>, also those '
        'attached to one of its EC2 nodes), ECR repositories referenced by cluster images.</li>'
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
        # The skill's scope disclosure, READ FROM SKILL.md at render time rather than copied.
        #
        # A hand-maintained paraphrase of the two adjacent SKILL.md
        # paragraphs goes short in a way that matters: one that
        # reproduces the Sustainability bullet and the "narrower
        # gaps" sentence but drops the other six whole-area bullets
        # leaves "Incident response", "failure management", "service
        # quotas" and "financial management" appearing NOWHERE in
        # the rendered HTML, beside a Security score and a
        # Reliability coverage cell that give no hint of them. A
        # reader then has no way to learn that no question in this
        # skill asks about any of them. SKILL.md calls its list
        # exhaustive; this bullet is the same list, because it IS
        # that list.
        #
        # Neither a comment nor an editing rule can make two documents agree.
        # Reading the text at render time can, and that is the only reason the
        # guarantee is real: edit the marked block in SKILL.md and the next
        # report carries the edit, with nothing here to remember. Do not
        # introduce a "cannot drift" claim for anything this file does not
        # extract.
        #
        # The wrapper below is structural only — an <li> and one sentence of framing. Every statement
        # about WHAT was not assessed comes from the skill, including the Linux-nodes-only statement
        # in its SCOPE-PLATFORMS block (references/workflow.md), which is why there is no second copy of it here to fall out
        # of step with the scorers.
        '<li><strong>What is not assessed at all.</strong> These are whole Well-Architected areas with '
        'no question in this skill, on either track. The list is reproduced from the skill&rsquo;s own '
        '<code>SKILL.md</code> as it stood when this report was rendered, and it is exhaustive for '
        'whole areas &mdash; read it as the boundary of what was checked. They are genuine gaps, not '
        'implied passes: nothing in this report should be read as having checked them.'
        + skill_block_html(blocks, "NOT-ASSESSED-AREAS")
        + skill_block_html(blocks, "NOT-ASSESSED-NARROWER")
        + '</li>'
        # WHICH PLATFORM was reviewed, beside WHICH AREAS were not. Both are boundary statements and a
        # reader needs them together: "no incident-response question" and "this is not how an
        # on-premises hybrid node would be graded" are the same kind of fact about the same report.
        # Extracted from references/workflow.md (SKILL_BLOCK_SOURCES) for the same reason as the list
        # above -- so the boundary the customer
        # reads is the boundary the skill actually enforces, not a paraphrase of it.
        '<li><strong>Which platforms this applies to.</strong> This review judges Amazon EKS running on '
        'AWS, on Linux nodes. Everything it grades below was collected from the EKS API and the '
        'cluster&rsquo;s Kubernetes API; where a platform is listed as not judged, no question in this '
        'report grades it.'
        + skill_block_html(blocks, "SCOPE-PLATFORMS")
        + '</li>'
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
        '</ul>'), anchor="method"))

    out.append('<footer class="page">Rendered locally from collected cluster data; this file makes no '
               'network requests. Styled with the Cloudscape Design System.</footer>')
    out.append('</div>')

    banner = ""
    if DISAGREEMENTS:
        ids = ", ".join(f"<code>{e(q)}</code>" for q, _ in DISAGREEMENTS[:12])
        more = f" and {len(DISAGREEMENTS) - 12} more" if len(DISAGREEMENTS) > 12 else ""
        # "Everything else in this report is unaffected" would claim a cross-check the report has not
        # performed. Only the questions with an extractor AND a countable total get one — only some
        # of the measured questions — so that sentence would quietly promote "never checked" to "checked and
        # fine". Both counts are stated, and both come from VERIFIED, which evidence_panel() fills as it
        # renders each panel.
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
    # THE TRIAGE DISCRIMINATOR MUST NOT BE THE THING THAT CRASHES. sys.stderr has carried
    # errors="backslashreplace" since 3.5, so every `render-report:` refusal survives a non-UTF-8 stdio
    # encoding; sys.stdout is strict, so without this the one line printed to it — `wrote <path> …` — would
    # raise UnicodeEncodeError for a non-ASCII `-o` path under, say, PYTHONIOENCODING=ascii. That fires
    # AFTER a complete, correct, mode-600 report has been written, so the operator would get a traceback and
    # a non-zero exit for a fully successful render, with no `wrote` line to apply references/workflow.md's
    # before/after-`wrote` rule to — and under --both the dark sibling would never be written at all. This
    # gives stdout the SAME error handler stderr already has, which is why it is a widening and not a new
    # policy.
    #
    # reconfigure(errors=...) changes ONLY the error handler: it flushes first and leaves
    # line_buffering and write_through as they were, so stdout stays block-buffered under a pipe and the
    # deliberate flush=True on the `wrote` line keeps doing the ordering work it exists for.
    # Guarded because sys.stdout is not a TextIOWrapper under every harness that imports this module.
    #
    # STATED PLAINLY: for `PYTHONIOENCODING=utf-8` and the like this is a widening of an accident, but
    # for an explicit `PYTHONIOENCODING=ascii:strict` it OVERRIDES a handler the caller asked for by
    # name. That is deliberate. The alternative honours the request by crashing after a complete report
    # is on disk, destroying the one line the documented triage rule reads and, under --both, the dark
    # sibling as well. A path this program was told to write to is not content it may refuse to name.
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, OSError, ValueError):
        pass
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
    # Cross-checked against the scored set here, where both halves exist for the first time. See the
    # docstring: this is the coverage question question_prose() cannot ask, because it never sees results.
    check_prose_coverage(prose, data)
    prov = scorer_provenance(ref)
    PRELUDE_SHADOW[:] = prelude_shadow(ref)
    # SKILL.md sits beside the references directory, and workflow.md inside it; the lookup follows whichever of the two ways
    # that directory was found. `--references` is how a harness points this renderer at a COPY of the
    # skill; resolving SKILL.md from __file__ regardless would read the installed skill's disclosures
    # while scoring the copy's questions, which is the drift this extraction exists to remove.
    blocks = skill_blocks(pathlib.Path(ref).parent / "SKILL.md", pathlib.Path(ref) / "workflow.md")

    cl = data["cluster"].get("name", "cluster")

    def document(theme):
        # The toggle only makes sense in `auto`: --theme light/dark exist precisely to PIN a theme
        # for print, email or a ticket attachment, where an interactive control would be misleading.
        show_toggle = theme == "auto" and not args.no_toggle
        body = build(data, prose, prov, blocks, toggle=show_toggle)
        script = f"<script>{TOGGLE_JS}</script>" if show_toggle else ""
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="{COLOR_SCHEME[theme]}">'
            f"<title>EKS Well-Architected Review — {e(cl)}</title>"
            f"<style>{stylesheet(theme)}</style></head><body>\n{body}\n{script}\n</body></html>\n")

    base = pathlib.Path(args.out) if args.out else pathlib.Path(args.work) / "report.html"
    # CHECKED BEFORE with_name(). The validation loop below catches what its stats
    # can raise, but the raise for `-o .` and `-o /` — a raw `ValueError:
    # PosixPath('.') has an empty name` — is HERE, above the loop, and a ValueError
    # is not an OSError, so no enumerated catch below could ever see it. `--both` is
    # the only flag that reaches into the operator's path before it has been
    # validated at all.
    #
    # THREE distinct Paths have an empty `.name` -- `.`, `/` and `//` (`//` survives normalisation because
    # POSIX leaves exactly two leading slashes implementation-defined) -- and the guard covers ANY spelling
    # that normalises onto one of those three. `os.path.isdir()` is True for all three, so the message
    # below is accurate for every such spelling.
    #
    # NO LIST OF SPELLINGS HERE, AND THAT IS THE POINT. Any enumeration comes up short:
    # `.///`, `./././`, `///`, `////`, `/././`, `//./` and more all normalise onto the same
    # three. The set is unbounded: any run of slashes and `.` segments works. Naming the three
    # NORMALISED FORMS is both complete and checkable; counting the ways to spell them is
    # neither.
    #
    # Refused on `base.name` rather than by wrapping with_name() in try/except ValueError: an empty name
    # means `-o` names a DIRECTORY, which the loop below already refuses in plain words for every other
    # spelling (`-o ..`, `-o /tmp/x` both say "is a directory, not a file"). Making the two agree is worth
    # more than catching the exception, because the operator gets the same sentence whichever spelling
    # they typed. Not gated on args.both: `-o .` is a directory under every flag combination, so saying so
    # unconditionally is both simpler and more accurate than only saying it when --both would crash.
    #
    # `/`, `//`, `/.` and `/./` are refused HERE, not one step later, where the refusal
    # would read "-o parent directory is not writable: /" -- true but the wrong
    # diagnosis, since the problem is that the target is a directory, not that / is
    # read-only.
    #
    # ORDERED BEFORE the --theme note below, deliberately: that note comments on how two flags interact,
    # and printing it for a run about to be rejected outright is advice about output that will not exist.
    if not base.name:
        sys.exit(f"render-report: -o {args.out or base} is a directory, not a file")
    if args.both and args.theme != "auto":
        # --both always writes a light file plus a dark sibling, so a --theme alongside it is silently
        # discarded. Say so rather than producing output that does not match the flags given.
        print(f"note: --both writes a light file and a -dark sibling; --theme {args.theme} is ignored",
              file=sys.stderr)
    targets = [(base, "light" if args.both else args.theme)]
    if args.both:
        targets.append((base.with_name(base.stem + "-dark" + base.suffix), "dark"))

    # Validate every destination BEFORE building anything. Otherwise a nonexistent parent directory or a
    # directory given as the target raises FileNotFoundError / IsADirectoryError after the entire report has
    # been rendered — all the work done, a raw traceback, and nothing written.
    for out, _ in targets:
        # The parent is checked FIRST, and that order is load-bearing, not a preference: `out.is_dir()` has to
        # stat a path *inside* the parent, so a parent with no traverse permission (mode 000) reaches the
        # refusal below instead of raising out of that stat.
        #
        # EVERY STAT IN THIS LOOP IS INSIDE A try. `out.parent.exists()` is an os.stat()
        # of its own with exactly the same failure set as the `out.is_dir()` below it, so
        # wrapping only the latter would leave two raw tracebacks: an `-o` whose PARENT
        # component exceeds NAME_MAX (OSError [Errno 63] File name too long) and an `-o`
        # two levels beneath a mode-000 directory (PermissionError [Errno 13]), both
        # straight out of `out.parent.exists()`. Catching one stat and not its neighbour
        # is not a fix, it is a narrower bug. `os.access` is inside the try for uniformity
        # only -- it reports failure by returning False and does not raise for these
        # cases.
        try:
            parent_missing = not out.parent.exists()
            parent_unusable = (not os.access(out.parent, os.W_OK)
                               or not os.access(out.parent, os.X_OK))
        except OSError as exc:
            sys.exit(f"render-report: -o parent {out.parent} is not a usable path ({exc})")
        if parent_missing:
            sys.exit(f"render-report: -o parent directory does not exist: {out.parent}")
        if parent_unusable:
            sys.exit(f"render-report: -o parent directory is not writable: {out.parent}")
        # `is_dir()` is an os.stat() and stat has more ways to fail than ENOENT: an `-o` path whose final
        # component exceeds NAME_MAX raises OSError [Errno 63] File name too long here. Caught rather than
        # routed through os.path.isdir(), which swallows the errno and answers False: that would let an
        # unusable path past a check headed "validate every destination BEFORE building anything" and
        # surface the same error from the write, after the whole report was built.
        try:
            out_is_dir = out.is_dir()
        except OSError as exc:
            sys.exit(f"render-report: -o {out} is not a usable path ({exc})")
        if out_is_dir:
            sys.exit(f"render-report: -o {out} is a directory, not a file")

    for out, theme in targets:
        doc = document(theme)
        # WRITE PRIVATE, THEN RENAME. Both halves are load-bearing.
        #
        # The report carries the account id, node/volume/SG/subnet ids and OIDC ARNs. collect.sh sets `umask
        # 077` for its own process only; this renderer runs as a separate Bash call and inherits the shell
        # default (022 on macOS), so without this the most forwardable file in the work dir would be the
        # only world-readable one.
        #
        # `write_text()` followed by `chmod` would have two defects, and a FAILED write hits both. It is not
        # atomic, and the chmod runs only after it returns, so a write that dies part-way leaves a TRUNCATED
        # report at mode 644 (`ulimit -f 800` reproduces it) -- world-readable, carrying the account id,
        # instance ids and the OIDC provider ARN, where a successful write is 600 -- and references/workflow.md's triage
        # rule ("before any `wrote …` line it wrote no report") would be false for exactly this case.
        # Opening the temp with 0o600 means the bytes are never group- or world-readable even for an
        # instant, and os.replace() is atomic within a directory, so a reader sees either the previous
        # report or this one and never a half-written one.
        tmp = out.with_name(out.name + ".part")
        try:
            # os.fdopen takes ownership of the descriptor, and the `with` closes it on the error path
            # too, so there is no descriptor to leak here.
            with os.fdopen(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
                           "w", encoding="utf-8") as fh:
                fh.write(doc)
            os.replace(tmp, out)
        except OSError as exc:
            # Nothing is deleted. A write that fails leaves whatever it wrote at `<report>.part` (opened
            # 0o600, so never group- or world-readable) and never at `out`, because os.replace() did not
            # run: `out` keeps the previous report, or stays absent. The message names the .part when one
            # exists, so the operator can inspect or discard it; a rerun truncates it (O_TRUNC above).
            left = f"; what it wrote is left at {tmp}" if os.path.lexists(tmp) else ""
            sys.exit(f"render-report: could not write {out}: {exc}{left}")
        # len(doc) is a CODE-POINT count; the file is written as UTF-8, so every em dash, tick, arrow and
        # chevron in the report costs 2-3 bytes and a printed len(doc) would understate the real file.
        # Report what is on disk, falling back to the encoded length if stat() is unavailable.
        try:
            nbytes = out.stat().st_size
        except OSError:
            nbytes = len(doc.encode("utf-8"))
        # flush=True is load-bearing, not cosmetic: stderr is unbuffered but stdout is block-buffered when
        # it is not a tty, so under a pipe this line would otherwise arrive AFTER the error blocks below it
        # and invert the before/after-"wrote" triage rule references/workflow.md tells the operator to use.
        print(f"wrote {out} ({nbytes:,} bytes, {theme} theme)", flush=True)

    # Fail the run when any resource list contradicts its own score. The report is still written — it
    # names the affected questions and carries the banner — but the exit code makes the contradiction
    # impossible to miss in a pipeline. This is what makes the guarantee true for a consumer holding
    # only the skill directory, with no test harness.
    rc = 0
    if DISAGREEMENTS:
        print(f"\nERROR: {len(DISAGREEMENTS)} finding(s) have a resource list that contradicts the "
              f"count their detection reported:", file=sys.stderr)
        for qid, why in DISAGREEMENTS:
            print(f"  {qid}: {why}", file=sys.stderr)
        print("The report was written and flags them, but do not trust those findings.",
              file=sys.stderr)
        rc = 1
    # Same treatment for the renderer's own INPUTS. A report that silently prints less than the skill
    # says, or drops a question's fix text, is the defect these two checks exist to close, so neither
    # may pass quietly: the report names what is missing and the exit code makes it impossible to miss
    # in a pipeline. There is deliberately no shorter fallback text for either.
    if SKILL_BLOCK_DEFECTS:
        srcs = " and ".join(dict.fromkeys(skill_block_source(n) for n, _ in SKILL_BLOCK_DEFECTS))
        print(f"\nERROR: {len(SKILL_BLOCK_DEFECTS)} block(s) of report content could not be read "
              f"from {srcs}:", file=sys.stderr)
        for name, why in SKILL_BLOCK_DEFECTS:
            print(f"  {name}: {why}", file=sys.stderr)
        print("Each of those blocks is a disclosure about what this review did NOT check. The report "
              "names the missing marker where the text should have been; it was not replaced with a "
              "shorter version.", file=sys.stderr)
        rc = 1
    if PROSE_DEFECTS:
        # "problem(s)", not "question(s)": this counts ENTRIES, and two entry shapes each stand for many
        # questions (the scored-coverage one, and a per-file one), so "question(s)" would print "1
        # question(s) lost their remediation text" directly above a line reporting dozens of them.
        print(f"\nERROR: {len(PROSE_DEFECTS)} problem(s) with question remediation text:",
              file=sys.stderr)
        for src, qid, why in PROSE_DEFECTS:
            print(f"  {qid} ({src}): {why}", file=sys.stderr)
        rc = 1
    shadow = PRELUDE_SHADOW
    if shadow:
        print(f"\nERROR: {len(shadow)} scorer call(s) whose prelude definition could not be extracted, "
              "so the report prints a program that will not run:", file=sys.stderr)
        for f, qid, n in shadow:
            print(f"  {qid}: calls {n}, defined in a prelude in references/{f} that could not be read -- "
                  "the assignment must read NAME='def ...' with no leading space, nothing between the "
                  "quote and `def`, nothing after the closing quote, and all on one line (this applies to "
                  "B= as much as to PE=)", file=sys.stderr)
        rc = 1
    lost, gained = disclosure_drift(prov)
    if lost or gained:
        print(f"\nERROR: the regex/heuristic disclosure set changed -- {len(lost)} lost, "
              f"{len(gained)} gained:", file=sys.stderr)
        for qid in lost:
            print(f"  {qid}: no longer carries the disclosure -- confirm whether its detection changed "
                  "or its reference file could not be read", file=sys.stderr)
        for qid in gained:
            print(f"  {qid}: GAINED the disclosure", file=sys.stderr)
        print("The report was written and carries a banner saying the same thing. Update "
              "_DISCLOSED_EXPECTED if the change is intended, or restore the detection.",
              file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
