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
same work dir always produces byte-identical HTML. Asking an agent to hand-write 131 findings
as styled HTML would be slower, non-deterministic, and would drift from the design tokens.

DESIGN
Cloudscape Design System (https://cloudscape.aws.dev). Token values are transcribed from the
design-tokens reference and carried as CSS custom properties, with the documented light and dark
values wired to prefers-color-scheme. No network requests, no external CSS or JS — the report is
one file that opens offline, which the skill's "all data stays local" contract requires.
"""
import argparse
import html
import json
import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# Severity weights — MUST stay identical to SKILL.md Step 7 / reduce.sh sev().
# Used only to LABEL a finding, never to compute a score.
# ---------------------------------------------------------------------------
SEV3 = {
    "sec-2", "sec-6", "sec-18", "rbac-1", "sec-21", "sec-29", "sec-4", "sec-30",
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
    ("cost-optimization", "Cost Optimization"),
]

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
    """Risk band per SKILL.md Step 7: >=80 LOW, >=60 MEDIUM, <60 HIGH."""
    if not isinstance(score, (int, float)):
        return ("inactive", "Not assessed")
    return (("success", "Low") if score >= 80 else
            ("warning", "Medium") if score >= 60 else ("error", "High"))


def e(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load(work):
    work = pathlib.Path(work)

    def j(name, default=None):
        p = work / name
        if not p.exists():
            if default is None:
                sys.exit(f"render-report: required file missing: {p}")
            return default
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            sys.exit(f"render-report: {p} is not valid JSON ({exc}) — refusing to render a "
                     f"report from data the scorers could not have read either")

    scores = j("scores.json")
    results = []
    rp = work / "results.jsonl"
    if not rp.exists():
        sys.exit(f"render-report: required file missing: {rp}")
    for line in rp.read_text().splitlines():
        if line.strip():
            results.append(json.loads(line))

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
        "cluster": j("cluster.json", {}).get("cluster", {}),
        "nodes": j("nodes.json", {"items": []}).get("items", []),
        "fargate": j("fargate.json", {}).get("fargateProfileNames", []),
        "podidentity": j("podidentity.json", {}).get("associations", []),
        "oidcproviders": j("oidcproviders.json", {}).get("OpenIDConnectProviderList", []),
        "pods": j("pods.json", {"items": []}).get("items", []),
    }


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
            prose[qid] = {
                "title": title,
                "rationale": " ".join(rat.group(1).split()) if rat else "",
                "remediation": rem.group(1).strip() if rem else "",
                "source": str(md.relative_to(ref)),
            }
    return prose


# Scorer helper -> number of collection files it reads before the jq program.
_HELPER_ARITY = {"m": 1, "m2": 2, "m3": 3, "m4": 4}


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
            mt = re.match(r"^(m[234]?)\s+([a-z]+-\d+)\s+(.*)$", line)
            if not mt:
                continue
            helper, qid, rest = mt.group(1), mt.group(2), mt.group(3)
            head, _, jq = rest.partition("'")
            prov[qid] = {
                "files": head.split()[:_HELPER_ARITY[helper]],
                "jq": jq.rstrip("'"),
                "helper": helper,
            }
    return prov


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


def _res_addons(d):
    have = (d["raw"].get("addons") or {}).get("addons") or []
    core = [a for a in have if a in CORE_ADDONS]
    return {"pass": sorted(core),
            "fail": sorted(a for a in CORE_ADDONS if a not in have),
            "context": sorted(a for a in have if a not in CORE_ADDONS),
            "context_label": "other add-ons installed (not counted by this check)"}


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


def _res_volumes(d, want_encrypted=True):
    vols = (d["raw"].get("volumes") or {}).get("Volumes") or []
    cn = d["cluster"].get("name", "")
    mine = [v for v in vols
            if any(t.get("Key") == f"kubernetes.io/cluster/{cn}" or t.get("Value") == cn
                   for t in (v.get("Tags") or []))]
    others = [v.get("VolumeId", "?") for v in vols if v not in mine]
    p, f = [], []
    for v in mine:
        vid = f'{v.get("VolumeId","?")} ({v.get("Size","?")} GiB, {v.get("VolumeType","?")})'
        (p if v.get("Encrypted") else f).append(vid)
    return {"pass": sorted(p), "fail": sorted(f),
            "context": sorted(others)[:10],
            "context_label": "volumes in the VPC NOT tagged to this cluster (correctly excluded)"}


def _res_unattached(d):
    vols = (d["raw"].get("volumes") or {}).get("Volumes") or []
    cn = d["cluster"].get("name", "")
    mine = [v for v in vols
            if any(t.get("Key") == f"kubernetes.io/cluster/{cn}" or t.get("Value") == cn
                   for t in (v.get("Tags") or []))]
    p, f = [], []
    for v in mine:
        vid = f'{v.get("VolumeId","?")} ({v.get("State","?")})'
        (p if v.get("State") != "available" else f).append(vid)
    return {"pass": sorted(p), "fail": sorted(f)}


def _res_sg(d, ok):
    sgs = (d["raw"].get("sg") or {}).get("SecurityGroups") or []
    v = d["cluster"].get("resourcesVpcConfig") or {}
    mine = set(v.get("securityGroupIds") or []) | {v.get("clusterSecurityGroupId")}
    scoped = [g for g in sgs if g.get("GroupId") in mine]
    others = [f'{g.get("GroupId","?")} ({g.get("GroupName","?")})'
              for g in sgs if g.get("GroupId") not in mine]
    p, f = _split(scoped, ok, lambda g: f'{g.get("GroupId","?")} ({g.get("GroupName","?")})')
    return {"pass": p, "fail": f, "context": sorted(others)[:10],
            "context_label": "security groups in the VPC not used by this cluster "
                             "(correctly excluded)"}


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
    for perm in g.get("IpPermissions") or []:
        lo, hi = perm.get("FromPort") or 0, perm.get("ToPort") or 0
        if lo <= 22 <= hi and (perm.get("IpRanges") or perm.get("UserIdGroupPairs")):
            return False
    return True


def _res_subnets(d, ok, label):
    subs = (d["raw"].get("subnets") or {}).get("Subnets") or []
    mine = set((d["cluster"].get("resourcesVpcConfig") or {}).get("subnetIds") or [])
    scoped = [s for s in subs if s.get("SubnetId") in mine]
    others = [f'{s.get("SubnetId","?")} ({s.get("AvailabilityZone","?")})'
              for s in subs if s.get("SubnetId") not in mine]
    rt = (d["raw"].get("routetables") or {}).get("RouteTables") or []

    def nm(s):
        return (f'{s.get("SubnetId","?")} ({s.get("AvailabilityZone","?")}, '
                f'{s.get("AvailableIpAddressCount","?")} free IPs)')
    p, f = _split(scoped, lambda s: ok(s, rt), nm)
    return {"pass": p, "fail": f, "context": sorted(others)[:10],
            "context_label": f"subnets in the VPC not used by this cluster ({label}); "
                             "correctly excluded"}


def _subnet_private(s, rts):
    for rt in rts:
        if not any(a.get("SubnetId") == s.get("SubnetId") for a in rt.get("Associations") or []):
            continue
        return not any(r.get("GatewayId", "").startswith("igw-") for r in rt.get("Routes") or [])
    return True


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
    scs = [s for s in _items(d, "storageclasses")
           if re.search(r"ebs\.csi\.aws\.com|kubernetes\.io/aws-ebs", s.get("provisioner") or "")]
    others = [f'{_nm(s)} ({s.get("provisioner","?")})'
              for s in _items(d, "storageclasses") if s not in scs]
    p, f = _split(scs, ok,
                  lambda s: f'{_nm(s)} (type={(s.get("parameters") or {}).get("type","?")}, '
                            f'encrypted={(s.get("parameters") or {}).get("encrypted","unset")})')
    return {"pass": p, "fail": f, "context": sorted(others),
            "context_label": "non-EBS StorageClasses (correctly excluded)"}


def _res_ns_label(d, prefix):
    ns = [n for n in _items(d, "namespaces") if not SYS_NS.match(_nm(n))]
    p, f = _split(ns, lambda n: any(k.startswith(prefix) for k in _labels(n)), _nm)
    return {"pass": p, "fail": f,
            "context": sorted(_nm(n) for n in _items(d, "namespaces") if SYS_NS.match(_nm(n))),
            "context_label": "AWS-managed namespaces (correctly excluded)"}


def _res_ns_has(d, other_file, key="namespace", drop_default=False):
    # `drop_default` mirrors sec-4, whose denominator ALSO excludes `default` — the agreement check
    # caught this as 0/4 against the scorer's 0/3.
    ns = [_nm(n) for n in _items(d, "namespaces")
          if not SYS_NS.match(_nm(n)) and not (drop_default and _nm(n) == "default")]
    covered = {(i.get("metadata") or {}).get(key) for i in _items(d, other_file)}
    return {"pass": sorted(n for n in ns if n in covered),
            "fail": sorted(n for n in ns if n not in covered)}


def _res_pdb_coverage(d):
    """rel-2: match PDB selectors against each Deployment's pod-template labels.

    Denominator is DEPLOYMENTS, not namespaces — a namespace-level check read 0/4 where the scorer
    said 0/8. This is also the exact question CONTEXT.md records as having once compared PDB
    *cardinality* to Deployment count, so the shape matters more here than anywhere.
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


def _res_deploy(d, ok):
    p, f = _split(_workload(_items(d, "deployments")), ok)
    return {"pass": p, "fail": f,
            "context": sorted(_qn(i) for i in _items(d, "deployments")
                              if SYS_NS.match(((i.get("metadata") or {}).get("namespace") or ""))),
            "context_label": "AWS-installed Deployments (correctly excluded — not the "
                             "operator's to configure)"}


def _res_containers(d, ok):
    p, f = [], []
    for pod, c in _containers(_workload(d["pods"])):
        nm = f'{_qn(pod)} / {c.get("name","?")}'
        (p if ok(c) else f).append(nm)
    return {"pass": sorted(p), "fail": sorted(f)}


def _res_pods(d, ok):
    p, f = _split(_workload(d["pods"]), ok)
    return {"pass": p, "fail": f}


def _res_containers_ctx(d, ok):
    """Container-level check where the POD securityContext is inherited (podsec-1's shape)."""
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
    if (d["cluster"].get("computeConfig") or {}).get("enabled") is True:
        return {"kind": "field",
                "pass": ["computeConfig.enabled = true (EKS Auto Mode provisions nodes; "
                         "no in-cluster autoscaler is expected)"],
                "fail": [], "pass_label": "Cluster setting read"}
    return _res_match(d, "deployments", "karpenter|cluster-autoscaler")


def _res_rbac1(d):
    binds = [b for b in _items(d, "clusterrolebindings")
             if (b.get("roleRef") or {}).get("name") == "cluster-admin"]
    p, f = [], []
    for b in binds:
        for s in b.get("subjects") or []:
            nm = s.get("name", "?")
            entry = f'{_nm(b)} -> {s.get("kind","?")} {nm}'
            builtin = re.match(r"^(system:|eks:)", nm) or nm == "system:masters"
            (p if builtin else f).append(entry)
    return {"pass": sorted(p), "fail": sorted(f),
            "pass_label": "Built-in subjects (expected)",
            "fail_label": "Non-system subjects with cluster-admin (findings)"}


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
    v = d["cluster"].get("resourcesVpcConfig") or {}
    cp = v.get("securityGroupIds") or []
    csg = v.get("clusterSecurityGroupId") or ""
    return {"kind": "field",
            "pass": [f"{s} (resourcesVpcConfig.securityGroupIds)" for s in cp],
            "fail": [], "pass_label": "Control plane security groups",
            "context": [f"{csg} (resourcesVpcConfig.clusterSecurityGroupId)"] if csg else [],
            "context_label": "cluster security group — the check passes when it is NOT in the "
                             "list above"}


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
            "context": ([f"cluster issuer: {stripped or 'absent'}"]
                        + [f"other provider in account: {a}" for a in provs if a not in match]),
            "context_label": "matched against"}


# id -> extractor. Absent id simply means no resource list is shown for that question.
RESOURCES = {
    # ---- Operational Excellence
    "ope-16": _res_addons,
    "lens-7": lambda d: {"pass": [a for a in
                                  ((d["raw"].get("addons") or {}).get("addons") or [])
                                  if a == "vpc-cni"],
                         "fail": [] if "vpc-cni" in ((d["raw"].get("addons") or {}).get("addons") or [])
                                 else ["vpc-cni not a managed add-on"]},
    "ope-11": _res_trails,
    "ope-6": _res_logtypes,
    "ope-15": lambda d: {"pass": sorted((d["raw"].get("nodegroups") or {}).get("nodegroups") or []),
                         "fail": []},
    "ope-17": lambda d: {"pass": [], "fail": [],
                         "context": sorted(_qn(i) for i in _items(d, "jobs")),
                         "context_label": "Jobs collected"},
    "ope-18": lambda d: {"pass": [], "fail": [],
                         "context": sorted(_qn(i) for i in _items(d, "cronjobs")),
                         "context_label": "CronJobs collected"},
    # ---- Security
    "sec-6": _res_identity,
    "sec-11": lambda d: _res_ns_label(d, "pod-security.kubernetes.io/"),
    "sec-4": lambda d: _res_ns_has(d, "networkpolicies", drop_default=True),
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
    # MapPublicIpOnLaunch is what the scorer reads; route-table inspection disagreed 3/3 vs 0/3.
    "lens-15": lambda d: _res_subnets(
        d, lambda s, rt: s.get("MapPublicIpOnLaunch") is False, "private addressing"),
    "lens-11": _res_imdsv2,
    "rbac-4": lambda d: (lambda sas: {
        "pass": sorted(_qn(s) for s in sas if s.get("automountServiceAccountToken") is False),
        "fail": sorted(_qn(s) for s in sas if s.get("automountServiceAccountToken") is not False)})(
        [s for s in _items(d, "serviceaccounts")
         if _nm(s) == "default" and not re.match(r"^kube-",
                                                 (s.get("metadata") or {}).get("namespace", ""))]),
    # Denominator is CONTAINERS, with the pod-level securityContext inherited — a pod-level
    # extractor read 11/15 against the scorer's 15/19.
    "podsec-1": lambda d: _res_containers_ctx(
        d, lambda c, ps: (c.get("securityContext") or {}).get("runAsNonRoot") is True
        or (ps or {}).get("runAsNonRoot") is True),
    "podsec-2": lambda d: _res_containers(
        d, lambda c: not ((c.get("securityContext") or {}).get("privileged"))),
    "podsec-3": lambda d: _res_pods(
        d, lambda p: not any(v.get("hostPath") for v in (p.get("spec") or {}).get("volumes") or [])),
    "podsec-5": lambda d: _res_containers(
        d, lambda c: "ALL" in (((c.get("securityContext") or {}).get("capabilities") or {})
                               .get("drop") or [])),
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
            r"^(a1|m[1-5]|c[1-5]|r[3-5]|t[12]|i[23]|d2|h1|x1|p[23]|g[23])[a-z]*\.",
            _labels(n).get("node.kubernetes.io/instance-type", ""))),
    "perf-6": lambda d: {"pass": sorted({_labels(n).get("node.kubernetes.io/instance-type", "?")
                                         for n in d["nodes"]}), "fail": []},
    "lens-6": lambda d: _res_nodes(
        d, lambda n: re.search(r"Bottlerocket|Amazon Linux 20[0-9][0-9]",
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
    # ---- the 17 that previously showed nothing --------------------------------
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
    "perf-5": lambda d: _res_deploy(
        d, lambda i: bool((((i.get("spec") or {}).get("template") or {}).get("spec") or {})
                          .get("affinity"))
        or bool((((i.get("spec") or {}).get("template") or {}).get("spec") or {})
                .get("topologySpreadConstraints"))),
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
        lines, in_ul = [], False
        for ln in txt.split("\n"):
            if re.match(r"^\s*[-*]\s+", ln):
                if not in_ul:
                    lines.append("<ul class='plain'>")
                    in_ul = True
                item = re.sub(r"^\s*[-*]\s+", "", ln)   # kept out of the f-string: py3.9 rejects
                lines.append(f"<li>{item}</li>")        # a backslash inside an f-string expression
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
    --color-severity-critical:#d63f38;
    --color-severity-high:#fe6e73;
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

/* --- Table --- */
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
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.qid{font-family:var(--font-family-monospace);white-space:nowrap;color:var(--color-text-body-secondary)}
td.detail{color:var(--color-text-body-secondary);font-family:var(--font-family-monospace);font-size:var(--font-size-body-s)}
.shaded{background:var(--color-background-cell-shaded)}

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
.badge-critical{background:var(--color-severity-critical)}
.badge-high{background:var(--color-severity-high)}
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
    """The WAF risk weight (High=3 / Medium=2 / Low=1) that `sev()` applies to this question.

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


MAX_LIST = 12   # cap per list; a 40-node / 800-pod cluster would otherwise dominate the page


def _res_list(names, cls):
    if not names:
        return ""
    shown = names[:MAX_LIST]
    more = len(names) - len(shown)
    lis = "".join(f"<li>{e(n)}</li>" for n in shown)
    tail = (f'<li class="muted">&hellip; and {more} more</li>' if more > 0 else "")
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
        rows.append(f"<dt>Why it matters</dt><dd>{e(p['rationale'])}</dd>")

    res = observed_resources(r["id"], data)
    body = ""
    if res:
        agree, why = resource_agreement(r, res)
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
        elif res.get("kind") == "existence":
            note = ('<div class="unverified">This check answers yes/no rather than counting, so '
                    "there is no total for the report to check this list against. Worth confirming "
                    "by eye: an object that merely <em>matches the name pattern</em> would also "
                    "satisfy the check.</div>")
        elif res.get("kind") == "field":
            note = ('<div class="unverified">This check reads cluster settings rather than counting '
                    "objects. The field paths and their values are printed above so the verdict is "
                    "checkable directly; there is no total to cross-check.</div>")
        else:
            note = ""
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

    if state != "all" and p.get("remediation"):
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
        for r in items:
            p = prose.get(r["id"], {})
            v = prov.get(r["id"], {})
            src = (", ".join(f"<code>{e(f)}.json</code>" for f in v.get("files", []))
                   or "<span class='muted'>&mdash;</span>")
            blocks.append(
                '<div class="fix">'
                f'<div class="head"><span class="qid">{e(r["id"])}</span>{sev_badge(r["id"], r.get("state"))}'
                f'{si(*STATE_UI[r["state"]])}'
                f'<span class="what">{e(p.get("title","(question text unavailable)"))}</span></div>'
                f'<p class="now">Measured now: <span class="measured">{e(r.get("detail","") or r["state"])}</span>'
                f' &middot; from {src}</p>'
                + (f'<div class="do">{md_inline(p["remediation"])}</div>'
                   if p.get("remediation") else
                   '<div class="do muted">No remediation recorded for this question.</div>')
                + '</div>')
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
# Report
# ---------------------------------------------------------------------------
def build(data, prose, prov, toggle=True):
    sc = data["scores"]
    res = data["results"]
    cl = data["cluster"]
    overall = sc.get("technical_overall")
    measured = [r for r in res if r.get("track") == "measured"]
    governance = [r for r in res if r.get("track") == "governance"]
    by_pillar = {k: {p["pillar"]: p for p in sc.get("pillars", [])}.get(k, {})
                 for k, _ in PILLARS}

    region = (cl.get("arn", "").split(":")[3] if cl.get("arn") else "")
    node_count = len(data["nodes"])
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
    out.append(
        '<div class="page-header" style="display:flex;align-items:flex-end;gap:var(--space-m);'
        'flex-wrap:wrap"><div><h1>Well-Architected review</h1>'
        f'<p>Deterministic review of <code>{e(cl.get("name",""))}</code>. '
        f'{len(measured)} measured questions answered from one data collection; '
        f'{len(governance)} governance questions are process-only.</p></div>'
        '<div class="bulk" id="bulk" hidden>'
        '<button type="button" data-act="open">Expand all evidence</button>'
        '<button type="button" data-act="close">Collapse all</button>'
        '</div></div>')

    # ---- alert when the overall is withheld --------------------------------
    if not isinstance(overall, (int, float)):
        insufficient = [n for (k, n) in PILLARS
                        if not isinstance(by_pillar[k].get("score"), (int, float))]
        out.append(
            '<div class="alert alert-warning"><span class="ico" aria-hidden="true">&#9888;</span>'
            '<div><h3>Overall score withheld</h3>'
            f'<p>{e(str(overall))}. A technical overall is only published when at least four '
            'pillars clear the 50% coverage gate.</p>'
            f'<p class="small">Below the gate: {e(", ".join(insufficient)) or "none"}. '
            'Too little of this cluster is observable to compress into a single number; the '
            'pillar detail below is still valid.</p></div></div>')

    # ---- executive summary -------------------------------------------------
    if isinstance(overall, (int, float)):
        kind, label = risk(overall)
        hero = (f'<div class="score-hero"><span class="val">{overall}</span>'
                f'<span class="den">/ 100</span>'
                f'<span class="rating">{e(rating(overall))}</span>'
                f'<span>{si(kind, label + " risk")}</span></div>')
    else:
        hero = f'<div class="score-hero"><span class="val muted">&mdash;</span>' \
               f'<span class="rating">{e(str(overall))}</span></div>'

    rows = []
    for key, name in PILLARS:
        p = by_pillar[key]
        s = p.get("score")
        appl, tot = p.get("applicable", 0), p.get("total", 0)
        rk, rl = risk(s)
        shown = f"{s}" if isinstance(s, (int, float)) else "Insufficient coverage"
        rows.append(
            f'<tr><td>{e(name)}</td>'
            f'<td class="num">{e(shown)}</td>'
            f'<td>{bar(s)}</td>'
            f'<td>{e(rating(s))}</td>'
            f'<td>{si(rk, rl)}</td>'
            f'<td class="num">{appl}&thinsp;/&thinsp;{tot}</td></tr>')
    table = (
        '<table><thead><tr><th>Pillar</th><th class="num">Score</th><th></th>'
        '<th>Rating</th><th>Risk</th><th class="num">Coverage</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')
    out.append(container("Executive summary",
                         f'<div class="bd" style="padding:0 0 var(--space-l)">{hero}</div>' + table,
                         desc="Technical score is the mean of the numeric pillar scores. "
                              "Coverage is applicable of measured questions.",
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
            "Top priorities", '<table><thead><tr><th>ID</th><th>Risk weight</th><th>Question</th>'
            '<th>Result</th><th>Evidence &amp; fix</th></tr></thead>'
            f'<tbody>{items}</tbody></table>',
            counter=str(len(prio)),
            desc="Highest WAF risk weight first, then the weakest result. Expand any row for the "
                 "data it was measured from and the fix.", flush=True))

    # ---- cluster facts -----------------------------------------------------
    workload_pods = sum(
        1 for p in data["pods"]
        if not re.match(r"^(kube-|amazon-)", (p.get("metadata", {}).get("namespace") or ""))
    )
    facts = [
        ("Cluster", cl.get("name", "—")),
        ("Region", region or "—"),
        ("Kubernetes version", cl.get("version", "—")),
        ("Platform version", cl.get("platformVersion", "—")),
        ("Compute mode", mode),
        ("Nodes", f"{node_count}"),
        ("Workload pods", f"{workload_pods}"),
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
        head = (f'{s}/100' if isinstance(s, (int, float)) else "Insufficient coverage")
        counts = {k: sum(1 for r in qs if r.get("state") == k)
                  for k in ("all", "most", "some", "none", "na")}
        summary = (f'{head} &middot; {counts["all"]} pass, {counts["most"]} mostly, '
                   f'{counts["some"]} partial, {counts["none"]} fail, {counts["na"]} n/a')
        out.append(container(
            name,
            '<table><thead><tr><th>ID</th><th>Risk weight</th><th>Question</th>'
            '<th>Result</th><th>Evidence &amp; fix</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>',
            counter=f'{p.get("applicable",0)} of {p.get("total",0)} applicable',
            desc=re.sub("<[^>]+>", "", summary).replace("&middot;", "·"),
            flush=True))

    # ---- improvement plan --------------------------------------------------
    plan = improvement_plan(measured, prose, prov)
    if plan:
        plan_html, n_open = plan
        out.append(container(
            "Improvement plan", plan_html,
            counter=f"{n_open} open item(s)",
            desc="Every question not scoring `all`, tiered by risk weight and how far short the "
                 "result fell, with the remediation from the reference for that question. "
                 "Effort is deliberately not estimated — it depends on the environment, "
                 "not on the collected data."))

    # ---- governance --------------------------------------------------------
    g = sc.get("governance", {})
    gscore = g.get("score")
    if gscore == "Not Assessed" or not governance:
        body = (
            '<div class="alert alert-info"><span class="ico" aria-hidden="true">&#8505;</span>'
            f'<div><h3>{g.get("answered",0)} of {g.get("total",len(governance))} answered '
            '&mdash; Not Assessed</h3>'
            '<p>Governance questions cover process rather than cluster state (upgrade cadence, '
            'change management, environment separation, secret rotation, compliance scanning, '
            'incident response, DR testing). They have no signal in <code>aws</code> or '
            '<code>kubectl</code> output.</p>'
            '<p class="small">They were not guessed and are excluded from every score above. '
            'Re-run in interactive mode to have them asked and scored separately.</p>'
            '</div></div>')
    else:
        body = (f'<div class="score-hero"><span class="val">{e(gscore)}</span>'
                f'<span class="den">/ 100</span><span class="rating">'
                f'{g.get("answered",0)} of {g.get("total",0)} answered</span></div>')
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
        '<li>Each question carries a WAF risk weight — High=3, Medium=2, Low=1 — shown in the '
        'Severity column. A pillar score is the severity-weighted mean of its applicable '
        'questions.</li>'
        '<li>A pillar scores only if applicable questions reach 50% of its measured total; '
        'otherwise it reports insufficient coverage. Fewer than four numeric pillars withholds '
        'the overall.</li>'
        '<li>Object checks assess cluster-owned resources only: workload namespaces (AWS-managed '
        '<code>kube-*</code>/<code>amazon-*</code> excluded), custom RBAC roles, volumes tagged '
        'to this cluster, ECR repositories referenced by cluster images.</li>'
        '<li>The Cost Optimization score measures cost <em>hygiene</em>. Spot, Graviton and '
        'Extended Support are workload- or date-dependent and are reported as narrative '
        'opportunities, not scored.</li>'
        '</ul>')))

    out.append('<footer class="page">Generated locally from collected cluster data. '
               'No data left this machine. Styled with the Cloudscape Design System.</footer>')
    out.append('</div>')
    return "\n".join(out)


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
    targets = [(base, "light" if args.both else args.theme)]
    if args.both:
        targets.append((base.with_name(base.stem + "-dark" + base.suffix), "dark"))

    for out, theme in targets:
        doc = document(theme)
        out.write_text(doc)
        print(f"wrote {out} ({len(doc):,} bytes, {theme} theme)")


if __name__ == "__main__":
    main()
