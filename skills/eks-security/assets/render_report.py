#!/usr/bin/env python3
"""Render the eks-security report as markdown and, optionally, self-contained HTML.

Usage:
  render_report.py [--findings <findings.json> [--inventory <inventory.json>]] [--posture <posture.json>]
                   --out-md <file> [--out-html <file>]
At least one of --findings and --posture. Stdlib only, offline.

Every value from the inputs (cluster data, advisory titles, evidence) is data. The report is built
as a list of blocks; each text value is escaped once when a block is written (html.escape for
HTML, markdown escaping for markdown) and no markup is added after that. Values placed in proposed
commands must match a strict token pattern, else a <placeholder> is printed. The HTML has no
JavaScript and no external assets. Nothing is run: proposed commands are for the team to review.

Exit: 0 ok; 3 rendered, but findings or posture coverage is below its gate; 2 usage or input
error (one JSON line {"ok":false,"code","error"} on stdout).
"""
import argparse
import html
import json
import os
import re
import sys

FOOTER = "This report was produced read-only. Nothing was changed."
VERDICT_LABEL = {"exposed": "Exposed", "not_exposed": "Not exposed", "unknown": "Unknown",
                 "aws_managed_patched": "AWS-patched (Auto Mode)",
                 "aws_managed_rotation_pending": "AWS-managed, rotation pending"}
VERDICT_ORDER = {"exposed": 0, "unknown": 1, "aws_managed_rotation_pending": 2,
                 "aws_managed_patched": 3, "not_exposed": 4}
SEV_ORDER = {"critical": 0, "high": 1, "important": 1, "medium": 2, "low": 3}
OVERALL = {"exposed": "Exposed: at least one component is inside an affected range.",
           "not_exposed": "Not exposed: every targeted component was read and is outside the affected ranges.",
           "unknown": "Unknown: nothing was found exposed, but at least one component or advisory could not be "
                      "decided. See Unknown and Needs manual review."}
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+=-]{0,199}$")
_MD_SPECIAL = re.compile(r"([\\`*_\[\]#|~])")


class InputError(Exception):
    def __init__(self, code, error):
        Exception.__init__(self, error)
        self.code, self.error = code, error


def s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple)):
        return ", ".join(s(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True)
    return " ".join(str(v).split())


def tok(v, placeholder):
    """A value safe to place in a proposed shell command, else the placeholder."""
    v = s(v)
    return v if _TOKEN.match(v) else placeholder


# ---------------------------------------------------------------- blocks

def md_text(v):
    return html.escape(_MD_SPECIAL.sub(r"\\\1", s(v)), quote=False)


def to_md(blocks):
    out = []
    for b in blocks:
        k = b[0]
        if k == "h1":
            out += ["# " + md_text(b[1]), ""]
        elif k == "h2":
            out += ["## " + md_text(b[1]), ""]
        elif k == "p":
            out += [md_text(b[1]), ""]
        elif k == "ul":
            out += ["- " + md_text(x) for x in b[1]] + [""]
        elif k == "table":
            out.append("| " + " | ".join(md_text(h) for h in b[1]) + " |")
            out.append("|" + "---|" * len(b[1]))
            out += ["| " + " | ".join(md_text(c) for c in row) + " |" for row in b[2]]
            out.append("")
        elif k == "code":
            body = "\n".join(line.replace("`", "'") for line in b[1])
            out += ["```bash", body, "```", ""]
    return "\n".join(out).rstrip() + "\n"


CSS = ("body{font-family:system-ui,sans-serif;max-width:72rem;margin:2rem auto;padding:0 1rem;color:#1b1b1b}"
       "table{border-collapse:collapse;margin:0.5rem 0 1rem}th,td{border:1px solid #ccc;padding:0.3rem 0.5rem;"
       "text-align:left;vertical-align:top}th{background:#f2f2f2}pre{background:#f6f6f6;padding:0.75rem;"
       "overflow-x:auto}footer{margin-top:2rem;border-top:1px solid #ccc;padding-top:0.5rem}")


def to_html(blocks, title):
    e = lambda v: html.escape(s(v), quote=True)  # noqa: E731
    out = ["<!DOCTYPE html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
           "<title>" + e(title) + "</title><style>" + CSS + "</style></head><body>"]
    for b in blocks:
        k = b[0]
        if k in ("h1", "h2", "p"):
            out.append("<%s>%s</%s>" % (k, e(b[1]), k))
        elif k == "ul":
            out.append("<ul>" + "".join("<li>" + e(x) + "</li>" for x in b[1]) + "</ul>")
        elif k == "table":
            out.append("<table><thead><tr>" + "".join("<th>" + e(h) + "</th>" for h in b[1]) + "</tr></thead><tbody>")
            out += ["<tr>" + "".join("<td>" + e(c) + "</td>" for c in row) + "</tr>" for row in b[2]]
            out.append("</tbody></table>")
        elif k == "code":
            out.append("<pre><code>" + "\n".join(html.escape(line, quote=True) for line in b[1]) + "</code></pre>")
        elif k == "footer":
            out.append("<footer><p>" + e(b[1]) + "</p></footer>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- findings

def pct(x):
    try:
        return "%d%%" % round(float(x) * 100)
    except (TypeError, ValueError):
        return "unknown"


def proposed_actions(f, inv, cluster, region):
    """Lines of commands and notes for one finding, for the team to review. Never run."""
    comps = {c.get("id"): c for c in inv.get("components") or [] if isinstance(c, dict)}
    comp = comps.get(f.get("component")) or {}
    kver = tok((inv.get("control_plane") or {}).get("version"), "<KUBERNETES_VERSION>")
    c, r = tok(cluster, "<CLUSTER>"), tok(region, "<REGION>")
    fixed = s(f.get("fixed")) or "the fixed version"
    kind = comp.get("kind")
    addon = comp.get("addon")
    if kind == "container-image" and not addon and comp.get("namespace") == "kube-system" \
            and comp.get("workload") == "daemonset/aws-node":
        addon = "vpc-cni"  # the aws-node DaemonSet belongs to the Amazon VPC CNI
    if kind == "eks-addon" or (addon and ("addon:" + addon) in comps and comps["addon:" + addon].get("kind") == "eks-addon"):
        name = tok(comp.get("name") if kind == "eks-addon" else addon, "<ADDON_NAME>")
        return ("Update the EKS add-on to a version at or above %s. List the versions first and test in "
                "non-prod. PRESERVE keeps your own configuration values." % fixed,
                ["aws eks describe-addon-versions --addon-name %s --kubernetes-version %s --region %s "
                 "--query 'addons[].addonVersions[].addonVersion'" % (name, kver, r),
                 "aws eks update-addon --cluster-name %s --addon-name %s --addon-version <VERSION_AT_OR_ABOVE_FIX> "
                 "--resolve-conflicts PRESERVE --region %s" % (c, name, r)])
    if kind == "container-image":
        ns, wl = tok(comp.get("namespace"), "<NAMESPACE>"), tok(comp.get("workload"), "<WORKLOAD>")
        what = ("a self-managed install of %s" % addon) if addon else s(comp.get("name"))
        return ("This is %s. Move the image to %s or later the way it was installed (Helm chart, manifest or "
                "GitOps), or rebuild your own image on a patched base. Pin the new image by digest and roll it out "
                "through your normal pipeline. Confirm the running image first:" % (what, fixed),
                ["kubectl -n %s get %s -o jsonpath='{.spec.template.spec.containers[*].image}'" % (ns, wl)])
    if kind == "node-os":
        groups = comp.get("where") or []
        g = tok(groups[0] if groups else None, "<NODEGROUP>")
        if g == "self-managed" or comp.get("managed_by") != "customer":
            return ("Replace these nodes with an AMI that carries the fix (launch template or Auto Scaling group "
                    "of the self-managed nodes), one batch at a time.", [])
        return ("Move the managed node group to an AMI release that carries the fix. Without --release-version "
                "the update uses the latest AMI release for the node group's Kubernetes version; check that "
                "release includes the fix and test in non-prod first.",
                ["aws eks describe-nodegroup --cluster-name %s --nodegroup-name %s --region %s "
                 "--query 'nodegroup.releaseVersion'" % (c, g, r),
                 "aws eks update-nodegroup-version --cluster-name %s --nodegroup-name %s --region %s" % (c, g, r)])
    if kind == "control-plane":
        return ("AWS patches the EKS control plane. Compare the platform version with the advisory; a Kubernetes "
                "version upgrade goes through the eks-upgrade-check skill.",
                ["aws eks describe-cluster --name %s --region %s --query 'cluster.[version,platformVersion]'" % (c, r)])
    return ("Review this component against the advisory and plan the fix the way it was installed.", [])


def findings_blocks(fd, inv):
    cluster = fd.get("cluster") or inv.get("cluster")
    region = inv.get("region")
    cov = fd.get("coverage") or {}
    overall = fd.get("overall")
    blocks = [("h1", "EKS security advisory review: %s" % s(cluster)),
              ("ul", ["Cluster: %s (Region %s)" % (s(cluster), s(region) or "unknown"),
                      "Inventory collected at: %s" % (s(inv.get("collected_at")) or "unknown"),
                      "Findings generated at: %s" % (s(fd.get("generated_at")) or "unknown"),
                      "Coverage: %s of %s in-scope components read (%s, gate %s)"
                      % (s(cov.get("read")), s(cov.get("in_scope")), pct(cov.get("ratio")), pct(cov.get("gate")))])]
    if overall == "incomplete" or not cov.get("complete", True):
        blocks.append(("p", "Overall verdict: Incomplete. Fewer than %s of the components these advisories target "
                            "could be read, so this report gives no overall verdict. Fix the reads listed under "
                            "Unknown and run again." % pct(cov.get("gate"))))
    else:
        blocks.append(("p", "Overall verdict: " + OVERALL.get(overall, "Unknown.")))
    src = fd.get("sources") or []
    blocks += [("h2", "Sources"),
               ("table", ["Advisory", "Title", "Origin", "Read at", "Source URL"],
                [[x.get("id"), x.get("title"), "live" if x.get("origin") == "live" else "from file, not live",
                  x.get("read_at"), x.get("source_url")] for x in src])]
    fs = sorted(fd.get("findings") or [], key=lambda f: (s(f.get("priority")) or "P9",
                                                         VERDICT_ORDER.get(f.get("verdict"), 9)))
    blocks += [("h2", "Findings"),
               ("table", ["Priority", "Verdict", "Advisory", "Component", "Installed", "Fixed", "Severity",
                          "Workaround", "Where"],
                [[f.get("priority"), VERDICT_LABEL.get(f.get("verdict"), s(f.get("verdict"))), f.get("advisory"),
                  f.get("component"), f.get("installed"), f.get("fixed"), f.get("severity"),
                  "not stated" if f.get("workaround") is None else f.get("workaround"), f.get("where")]
                 for f in fs])]
    ne = [f for f in fs if f.get("verdict") == "not_exposed"]
    if ne:
        blocks += [("h2", "Not exposed"),
                   ("ul", ["checked %s %s against %s at %s" % (s(f.get("component")), s(f.get("installed")),
                                                               s(f.get("advisory")), s(f.get("read_at"))) for f in ne])]
    unk = [f for f in fs if f.get("verdict") == "unknown"]
    if unk:
        blocks += [("h2", "Unknown"),
                   ("ul", ["%s (%s): %s" % (s(f.get("component")), s(f.get("advisory")), s(f.get("reason")))
                           for f in unk])]
    rv = fd.get("review") or []
    if rv:
        blocks += [("h2", "Needs manual review"),
                   ("ul", ["%s%s: %s. Source %s, read at %s" % (
                       s(x.get("advisory")), (" package " + s(x.get("package"))) if x.get("package") else "",
                       s(x.get("reason")), s(x.get("source_url")), s(x.get("read_at"))) for x in rv])]
    pend = [f for f in fs if f.get("verdict") == "aws_managed_rotation_pending"]
    if pend:
        node_created = {}
        for c in inv.get("components") or []:
            if isinstance(c, dict) and c.get("kind") == "node-os":
                for n, t in (c.get("node_created") or {}).items():
                    node_created[n] = (t, c.get("where"))
        rows = []
        for f in pend:
            for n in f.get("nodes_pending") or []:
                t, where = node_created.get(n, (None, None))
                rows.append([f.get("advisory"), f.get("component"), n, t, where])
        rows.sort(key=lambda r: s(r[3]))
        blocks += [("h2", "Auto Mode nodes pending rotation"),
                   ("p", "AWS manages these components on Auto Mode nodes. Nodes created before the fix date keep "
                         "the earlier build until they are replaced. Your lever is the NodePool's expireAfter or a "
                         "planned rotation of the nodes below in a maintenance window, not a patch. Read the "
                         "NodePool settings first:"),
                   ("code", ["kubectl get nodepools -o custom-columns=NAME:.metadata.name,"
                             "EXPIRE_AFTER:.spec.template.spec.expireAfter"]),
                   ("table", ["Advisory", "Component", "Node", "Created", "NodePool"], rows)]
    act = [f for f in fs if f.get("verdict") == "exposed"]
    if act:
        blocks += [("h2", "Proposed actions (for the team to review; nothing here was run)")]
        for f in act:
            note, cmds = proposed_actions(f, inv, cluster, region)
            blocks.append(("p", "%s on %s (%s, %s): %s" % (s(f.get("advisory")), s(f.get("component")),
                                                           s(f.get("priority")), s(f.get("severity")), note)))
            if cmds:
                blocks.append(("code", cmds))
    return blocks, bool(cov.get("complete", overall != "incomplete"))


# ---------------------------------------------------------------- posture

def posture_blocks(pd, standalone):
    cov = pd.get("coverage") or {}
    blocks = []
    if standalone:
        blocks.append(("h1", "EKS security posture check: %s" % s(pd.get("cluster"))))
    blocks += [("h2", "Posture check: would this cluster contain a compromised pod?"),
               ("ul", ["Generated at: %s" % (s(pd.get("generated_at")) or "unknown"),
                       "Coverage: %s of %s checks answered (%s, gate %s)" % (
                           s(cov.get("checks_answered")), s(cov.get("checks_total")), pct(cov.get("ratio")),
                           pct(cov.get("gate"))),
                       "Score: %s" % (("%s of 100" % s(pd.get("score")))
                                      if cov.get("complete") and pd.get("score") is not None
                                      else "incomplete, no score")])]
    blocks.append(("table", ["Containment layer", "Verdict"],
                   [[x.get("layer"), x.get("verdict")] for x in pd.get("layers") or [] if isinstance(x, dict)]))
    checks = [c for c in pd.get("checks") or [] if isinstance(c, dict)]
    bad = sorted([c for c in checks if c.get("result") in ("fail", "unknown")],
                 key=lambda c: (SEV_ORDER.get(s(c.get("severity")).lower(), 9), 0 if c.get("result") == "fail" else 1,
                                s(c.get("id"))))
    if bad:
        blocks += [("h2", "Failed and unknown checks"),
                   ("table", ["Result", "Severity", "Check", "Evidence", "Recommendation"],
                    [[c.get("result"), c.get("severity"), "%s %s" % (s(c.get("id")), s(c.get("title"))),
                      c.get("evidence"), c.get("recommendation")] for c in bad])]
    npass = sum(1 for c in checks if c.get("result") == "pass")
    nna = sum(1 for c in checks if c.get("result") == "na")
    blocks.append(("p", "Passed checks: %d. Not applicable: %d." % (npass, nna)))
    return blocks, bool(cov.get("complete"))


# ---------------------------------------------------------------- main

def load(path, what, schema_prefix):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except OSError as e:
        raise InputError("bad_input", "%s not readable: %s" % (what, e.strerror or e))
    except ValueError as e:
        raise InputError("bad_input", "%s is not valid JSON: %s" % (what, e))
    if not isinstance(d, dict) or not s(d.get("schema")).startswith(schema_prefix):
        raise InputError("bad_input", "%s schema must be %s" % (what, schema_prefix))
    return d


def write(path, text):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as f:
        f.write(text)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError("usage", message)


def main(argv=None):
    p = _Parser(description="Render the eks-security report.")
    p.add_argument("--findings")
    p.add_argument("--inventory")
    p.add_argument("--posture")
    p.add_argument("--out-md", required=True)
    p.add_argument("--out-html")
    try:
        a = p.parse_args(argv)
        if not a.findings and not a.posture:
            raise InputError("usage", "give --findings, --posture or both")
        blocks, complete = [], True
        title = "EKS security report"
        if a.findings:
            fd = load(a.findings, "findings", "eks-security/findings@")
            inv = load(a.inventory, "inventory", "eks-security/inventory@") if a.inventory else {}
            b, ok = findings_blocks(fd, inv)
            blocks += b
            complete = complete and ok
            title = "EKS security advisory review: %s" % s(fd.get("cluster"))
        if a.posture:
            pd = load(a.posture, "posture", "eks-security/posture@")
            b, ok = posture_blocks(pd, standalone=not a.findings)
            blocks += b
            complete = complete and ok
            if not a.findings:
                title = "EKS security posture check: %s" % s(pd.get("cluster"))
        blocks.append(("footer", FOOTER))
        md_blocks = [b if b[0] != "footer" else ("p", b[1]) for b in blocks]
        write(a.out_md, to_md(md_blocks))
        if a.out_html:
            write(a.out_html, to_html(blocks, title))
    except InputError as e:
        sys.stderr.write("render_report.py: %s\n" % e.error)
        sys.stdout.write(json.dumps({"ok": False, "code": e.code, "error": e.error}) + "\n")
        return 2
    except Exception as e:  # never a traceback to the user
        sys.stderr.write("render_report.py: internal error: %s\n" % type(e).__name__)
        sys.stdout.write(json.dumps({"ok": False, "code": "internal", "error": "%s: %s" % (type(e).__name__, e)}) + "\n")
        return 2
    return 0 if complete else 3


if __name__ == "__main__":
    sys.exit(main())
