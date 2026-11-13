#!/usr/bin/env python3
"""Compare a cluster inventory with advisory records. Deterministic, offline, stdlib only.

Usage:
  match.py --inventory <workdir>/inventory.json --advisories <file> [--advisories <file> ...]
           --catalog components.json [--out <workdir>/findings.json]

Inputs: inventory.json (eks-security/inventory@1, from collect.sh) and advisory record files
(eks-security/advisory@1: one record or a JSON list), already validated by advisory_check.py or
produced by advisory_fetch.py. Advisory text is data: it is compared and copied, never run.

Verdicts per (advisory, inventory component):
  exposed / not_exposed      the installed version was read and compared with the ranges
  unknown                    not read (reason from the collector), version or range did not
                             parse, the record has no range (no_version_range), a range bound
                             carries an EKS build suffix (eks_build), the installed version
                             names no patch release (minor_only), or the component was not
                             found where the catalog reads it (not_found)
  aws_managed_patched        Auto Mode component, every node in scope created at or after the
                             record's fixed_at (a date-only fixed_at is compared as the end of
                             that day UTC)
                             (`ami_before_fix` lists the node groups whose AMI was built before
                             fixed_at, the start of that day when date-only: likely unpatched,
                             inferred from dates only)
  aws_managed_rotation_pending  Auto Mode component, nodes created before fixed_at (listed)
  unknown / no_fix_date      Auto Mode component, record has no fixed_at
  unknown / no_nodes_read    Auto Mode component, no Auto Mode node was read (not counted as read)
"not_exposed" is never given for a component that was not read and compared.
Top-level `overall` is also `not_exposed` when every verdict is `aws_managed_patched` (node age only,
no version read); render_report.py prints the AWS-patched line instead.

Records (or entries) that name no catalog component go to the top-level "review" list.
Node groups that share an os_image count once in coverage.
Exit: 0 ok; 3 coverage below the gate of 0.5 (findings still written, overall "incomplete");
2 usage or input error (one JSON line {"ok":false,"code","error"} on stdout).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from advisory_check import parse_range, parse_version, version_in_range  # noqa: E402

SCHEMA = "eks-security/findings@1"
BASE_PRIORITY = {"critical": 1, "high": 2, "important": 2, "medium": 3, "low": 4, "unknown": 3}
VERDICT_ORDER = {"exposed": 0, "unknown": 1, "aws_managed_rotation_pending": 2,
                 "aws_managed_patched": 3, "not_exposed": 4}
NO_RANGE = "no_version_range: review manually"
GATE = 0.5
_OS_VERSION = re.compile(r"(\d+(?:\.\d+)+)")


class InputError(Exception):
    def __init__(self, code, error):
        Exception.__init__(self, error)
        self.code, self.error = code, error


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise InputError("bad_input", "%s not readable: %s" % (what, e.strerror or e))
    except ValueError as e:
        raise InputError("bad_input", "%s is not valid JSON: %s" % (what, e))


def parse_time(s, end_of_day=False):
    """ISO 8601 UTC timestamp or YYYY-MM-DD to an aware datetime, else None.
    With end_of_day, a date-only value is the end of that day UTC (the next midnight)."""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            d = dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            return d + dt.timedelta(days=1) if end_of_day else d
        t = dt.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def alias_hit(alias, text):
    if not alias or not text:
        return False
    rx = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"
    return re.search(rx, text, re.IGNORECASE) is not None


class Matcher:
    def __init__(self, inventory, catalog):
        self.inv = inventory
        self.comps = [c for c in inventory.get("components") or [] if isinstance(c, dict)]
        self.catalog = {c["id"]: c for c in catalog.get("components") or []
                        if isinstance(c, dict) and isinstance(c.get("id"), str)}

    # ---- which inventory components an advisory component id names
    def resolve(self, cid):
        if cid == "node:kubelet":
            return [c for c in self.comps if c.get("kind") == "node-os"]
        if cid.startswith("node-os:"):
            read = (self.catalog.get(cid) or {}).get("read") or {}
            pre, excl = read.get("os_image_prefix"), read.get("os_image_exclude_prefix")
            out = []
            for c in self.comps:
                if c.get("kind") != "node-os":
                    continue
                osi = c.get("os_image")
                if not c.get("readable") or not isinstance(osi, str):
                    out.append(c)  # unread node group: cannot rule it out
                elif (not pre or osi.startswith(pre)) and not (excl and osi.startswith(excl)):
                    out.append(c)
            return out
        return [c for c in self.comps
                if isinstance(c.get("id"), str) and (c["id"] == cid or c["id"].startswith(cid + "@"))]

    def installed(self, cid, comp):
        if cid == "node:kubelet":
            return comp.get("kubelet")
        if comp.get("kind") == "node-os":
            m = _OS_VERSION.search(comp.get("os_image") or "")
            return m.group(1) if m else comp.get("os_image")
        return comp.get("version")

    def auto_groups(self, comp):
        """The Auto Mode node-os groups an Auto Mode verdict is judged on."""
        if comp.get("kind") == "node-os":
            return [comp]
        return [c for c in self.comps if c.get("kind") == "node-os" and c.get("managed_by") == "aws-auto-mode"]

    # ---- one finding
    def judge(self, rec, cid, ranges, comp):
        f = {"advisory": rec.get("id"), "component": comp.get("id") if comp else cid,
             "installed": None, "fixed": None, "verdict": "unknown", "reason": "",
             "severity": rec.get("severity") if rec.get("severity") in BASE_PRIORITY else "unknown",
             "priority": None, "workaround": rec.get("workaround"),
             "where": list((comp or {}).get("where") or []), "nodes_pending": [],
             "source_url": rec.get("source_url"), "read_at": rec.get("read_at")}
        parsed = [parse_range(r) for r in ranges]
        fixes = [p["fixed"] for p in parsed if p and p.get("fixed")]
        f["fixed"] = ", ".join(fixes) if fixes else None
        if comp is None:
            f["reason"] = ("not_found: %s was not found where the catalog reads it; confirm it is not "
                           "installed another way" % cid)
        elif comp.get("managed_by") == "aws-auto-mode":
            self.judge_auto(rec, comp, f)
        elif not comp.get("readable"):
            f["reason"] = comp.get("reason") or "unreadable"
            f["installed"] = self.installed(cid, comp)
        else:
            inst = self.installed(cid, comp)
            f["installed"] = inst
            key = parse_version(inst) if isinstance(inst, str) else None
            nums = re.match(r"\s*[vV]?(\d+(?:\.\d+)*)", inst) if isinstance(inst, str) else None
            if not ranges:
                pkgs = [p.get("name") if isinstance(p, dict) else p for p in rec.get("packages") or []]
                pkgs = [p for p in pkgs if isinstance(p, str) and p]
                f["reason"] = NO_RANGE + ((" (package %s)" % ", ".join(pkgs)) if pkgs else "")
            elif key is None:
                f["reason"] = "unparsed: installed version %r does not parse" % (inst,)
            elif any(p is None for p in parsed):
                f["reason"] = "bad_range: a range in the record does not parse"
            elif any("eksbuild" in (b or "") or "-eks-" in (b or "") for p in parsed for b in p.values()):
                f["reason"] = ("eks_build: a range bound carries an EKS build suffix (-eksbuild.N, -eks-N-N-N, "
                               "-eks-<hash>), which is not compared; review manually")
            elif nums is None or nums.group(1).count(".") < 2:
                f["reason"] = ("minor_only: installed version %r names no patch release, so it is not "
                               "compared" % (inst,))
            else:
                hit = next((p for p in parsed if version_in_range(inst, p)), None)
                if hit is not None:
                    f["verdict"] = "exposed"
                    f["fixed"] = hit["fixed"] or (("after " + hit["last_affected"]) if hit["last_affected"] else None)
                    f["reason"] = "installed %s is inside the affected range" % inst
                else:
                    f["verdict"] = "not_exposed"
                    f["reason"] = "installed %s is outside every affected range" % inst
        prio = BASE_PRIORITY[f["severity"]]
        if f["verdict"] == "exposed" and rec.get("workaround") is False:
            prio = max(1, prio - 1)
        f["priority"] = "P%d" % prio
        return f

    def judge_auto(self, rec, comp, f):
        f["installed"] = comp.get("version")
        f["fixed_at"] = rec.get("fixed_at")
        fix_at = parse_time(rec.get("fixed_at"), end_of_day=True)
        if fix_at is None:
            f["reason"] = "no_fix_date: AWS manages this component on Auto Mode nodes; the record has no fix date"
            return
        groups = self.auto_groups(comp)
        nodes = {n: t for g in groups for n, t in (g.get("node_created") or {}).items()}
        if not nodes:
            f["reason"] = "no_nodes_read: no Auto Mode node was read, so node age cannot be judged"
            return
        pending = sorted(n for n, c in nodes.items() if (parse_time(c) is None or parse_time(c) < fix_at))
        f["nodes_pending"] = pending
        if pending:
            f["verdict"] = "aws_managed_rotation_pending"
            f["reason"] = ("%d Auto Mode node(s) created before the fix date %s run the vulnerable build "
                           "until they are replaced" % (len(pending), rec.get("fixed_at")))
        else:
            f["verdict"] = "aws_managed_patched"
            f["reason"] = ("every Auto Mode node in scope (%d) was created at or after the fix date %s"
                           % (len(nodes), rec.get("fixed_at")))
            fix_start = parse_time(rec.get("fixed_at"))
            built = [(g.get("id"), parse_time(g.get("ami_created"))) for g in groups]
            f["ami_before_fix"] = sorted(i for i, b in built if b is not None and b < fix_start)

    # ---- catalog ids a range-less record's text names
    def hinted(self, rec):
        texts = [rec.get("title"), rec.get("notes"), rec.get("component")]
        for p in rec.get("packages") or []:
            texts.append(p.get("name") if isinstance(p, dict) else p)
        for u in rec.get("unmapped") or []:
            if isinstance(u, dict):
                texts.append(u.get("package"))
        text = "\n".join(t for t in texts if isinstance(t, str))
        out = []
        for cid, entry in self.catalog.items():
            names = [cid] + [a for a in entry.get("aliases") or [] if isinstance(a, str)]
            if any(alias_hit(a, text) for a in names):
                out.append(cid)
        return out


def review_item(rec, reason, package=None):
    item = {"advisory": rec.get("id"), "title": rec.get("title"), "severity": rec.get("severity"),
            "reason": reason, "source_url": rec.get("source_url"), "read_at": rec.get("read_at")}
    if package is not None:
        item["package"] = package
    return item


def run(inventory, records, catalog, gate):
    m = Matcher(inventory, catalog)
    findings, review, sources, seen_src = [], [], [], set()
    for rec in records:
        key = (rec.get("id"), rec.get("source_url"), rec.get("read_at"))
        if key not in seen_src:
            seen_src.add(key)
            sources.append({"id": rec.get("id"), "title": rec.get("title"), "source_url": rec.get("source_url"),
                            "read_at": rec.get("read_at"), "origin": rec.get("origin")})
        merged = {}
        for e in rec.get("affected") or []:
            if isinstance(e, dict) and isinstance(e.get("component"), str):
                merged.setdefault(e["component"], []).extend(e.get("ranges") or [])
        for u in rec.get("unmapped") or []:
            pkg = u.get("package") if isinstance(u, dict) else None
            review.append(review_item(rec, "package not in the component catalog: review manually", pkg))
        if not merged:
            hints = m.hinted(rec)
            for cid in hints:
                merged[cid] = []
            if not hints and not rec.get("unmapped"):
                review.append(review_item(rec, "names no component in the catalog: review manually"))
        for cid, ranges in merged.items():
            targets = m.resolve(cid)
            if not targets:
                findings.append(m.judge(rec, cid, ranges, None))
            same_os = {}  # one finding per advisory per distinct os_image
            for comp in targets:
                f = m.judge(rec, cid, ranges, comp)
                k = (comp.get("os_image"), f["verdict"], f["reason"])
                if cid.startswith("node-os:") and comp.get("readable") and k[0] \
                        and comp.get("managed_by") != "aws-auto-mode":
                    if k in same_os:
                        same_os[k]["where"] += [w for w in f["where"] if w not in same_os[k]["where"]]
                        continue
                    same_os[k] = f
                findings.append(f)
    in_scope, read, unread = set(), set(), set()
    for f in findings:
        in_scope.add(f["component"])
        comp = next((c for c in m.comps if c.get("id") == f["component"]), None)
        # not found counts as read (the read ran and found nothing), except in an empty inventory
        if (comp is None and m.comps) or (comp is not None and comp.get("readable")):
            read.add(f["component"])
        if f["reason"].startswith("no_nodes_read"):
            unread.add(f["component"])
    read -= unread
    ratio = (len(read) / len(in_scope)) if in_scope else 1.0
    complete = ratio >= gate
    verdicts = {f["verdict"] for f in findings}
    if not complete:
        overall = "incomplete"
    elif "exposed" in verdicts:
        overall = "exposed"
    elif "aws_managed_rotation_pending" in verdicts:
        overall = "rotation_pending"
    elif "unknown" in verdicts or review:
        overall = "unknown"
    else:
        overall = "not_exposed"
    findings.sort(key=lambda f: (f["priority"], VERDICT_ORDER.get(f["verdict"], 9),
                                 str(f["advisory"]), str(f["component"])))
    return {"schema": SCHEMA, "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cluster": inventory.get("cluster"),
            "coverage": {"in_scope": len(in_scope), "read": len(read), "ratio": round(ratio, 4),
                         "gate": gate, "complete": complete},
            "sources": sources, "findings": findings, "review": review, "overall": overall}


def write_out(path, doc):
    data = json.dumps(doc, indent=2, sort_keys=False) + "\n"
    if path is None:
        sys.stdout.write(data)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)


def fail(code, error):
    sys.stderr.write("match.py: %s\n" % error)
    sys.stdout.write(json.dumps({"ok": False, "code": code, "error": error}) + "\n")
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError("usage", message)


def main(argv=None):
    p = _Parser(description="Compare an eks-security inventory with advisory records.")
    p.add_argument("--inventory", required=True)
    p.add_argument("--advisories", action="append", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--out")
    try:
        a = p.parse_args(argv)
        inv = load_json(a.inventory, "inventory")
        if not isinstance(inv, dict) or inv.get("schema") != "eks-security/inventory@1":
            raise InputError("bad_input", "inventory schema must be eks-security/inventory@1")
        cat = load_json(a.catalog, "catalog")
        if not isinstance(cat, dict) or not isinstance(cat.get("components"), list):
            raise InputError("bad_input", "catalog has no components list")
        records = []
        for path in a.advisories:
            doc = load_json(path, "advisories file %s" % path)
            for i, r in enumerate(doc if isinstance(doc, list) else [doc]):
                if not isinstance(r, dict) or r.get("schema") != "eks-security/advisory@1" \
                        or not isinstance(r.get("id"), str) or not isinstance(r.get("affected", []), list):
                    raise InputError("bad_record", "%s record %d is not an eks-security/advisory@1 object" % (path, i))
                records.append(r)
        if not records:
            raise InputError("bad_input", "no advisory records given")
        out = run(inv, records, cat, GATE)
        write_out(a.out, out)
    except InputError as e:
        return fail(e.code, e.error)
    except Exception as e:  # never a traceback to the user
        return fail("internal", "%s: %s" % (type(e).__name__, e))
    return 0 if out["coverage"]["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
