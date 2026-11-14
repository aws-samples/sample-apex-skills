#!/usr/bin/env python3
"""Offline regression tests for the eks-security advisory scripts.

Covers skills/eks-security/assets/: advisory_check.py (version and range helpers, record
validation), advisory_fetch.py (saved feed responses through --input), match.py (verdicts,
priority, coverage gate, exit codes), render_report.py (escaping, footer, origin) and
collect.sh (read-only command guard, run against fake aws and kubectl on PATH).

Stdlib only, no network, no cluster. All data comes from
misc/tests/fixtures/eks_security_cases.json. Run from the repo root:
  python3 -B misc/tests/test_eks_security_match.py -v
"""
import base64
import copy
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "skills", "eks-security", "assets")
CATALOG = os.path.join(ASSETS, "components.json")
FIXTURES = os.path.join(ROOT, "misc", "tests", "fixtures", "eks_security_cases.json")
sys.path.insert(0, ASSETS)

import advisory_check  # noqa: E402
import match  # noqa: E402

with open(FIXTURES, "r", encoding="utf-8") as _f:
    CASES = json.load(_f)
with open(CATALOG, "r", encoding="utf-8") as _f:
    CAT = json.load(_f)


def run_py(script, args, timeout=60):
    """Run an asset script; return (rc, stdout, stderr)."""
    p = subprocess.run([sys.executable, "-B", os.path.join(ASSETS, script)] + list(args),
                       capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    return p.returncode, p.stdout, p.stderr


def last_json(out):
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="eks-sec-test-")
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def write(self, name, data, mode="w"):
        path = os.path.join(self.tmp, name)
        if mode == "wb":
            with open(path, "wb") as f:
                f.write(data)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(data if isinstance(data, str) else json.dumps(data))
        return path


# ------------------------------------------------------------------ versions and ranges

class VersionParsing(unittest.TestCase):
    V = CASES["versions"]

    def test_equal_forms(self):
        # v prefix, -eksbuild.N, -eks-<hash>, -eks-1-33-N, trailing zeros, +build metadata
        for a, b in self.V["equal"]:
            with self.subTest(a=a, b=b):
                ka, kb = advisory_check.parse_version(a), advisory_check.parse_version(b)
                self.assertIsNotNone(ka, a)
                self.assertEqual(ka, kb, "%s should compare equal to %s" % (a, b))

    def test_less_than(self):
        # prerelease sorts before its release; numeric parts compare numerically
        for a, b in self.V["less"]:
            with self.subTest(a=a, b=b):
                self.assertLess(advisory_check.parse_version(a), advisory_check.parse_version(b))

    def test_garbage_is_none(self):
        for g in self.V["none"]:
            with self.subTest(value=g):
                self.assertIsNone(advisory_check.parse_version(g))


class RangeParsing(unittest.TestCase):
    R = CASES["ranges"]

    def test_parse_forms(self):
        for text, want in self.R["parse"]:
            with self.subTest(range=text):
                self.assertEqual(advisory_check.parse_range(text), want)

    def test_unsupported_forms_are_none(self):
        # "> X" (no upper bound form), duplicate bounds, inverted, bare version, junk
        for text in self.R["none"]:
            with self.subTest(range=text):
                self.assertIsNone(advisory_check.parse_range(text))

    def test_version_in_range(self):
        # includes: boundary equal to fixed is not affected, eksbuild suffix at fixed is not affected
        for v, r, want in self.R["in_range"]:
            with self.subTest(v=v, r=r):
                self.assertIs(advisory_check.version_in_range(v, r), want)

    def test_multi_interval_or(self):
        ranges = self.R["multi"]["ranges"]
        for v, want in self.R["multi"]["cases"]:
            with self.subTest(v=v):
                got = any(advisory_check.version_in_range(v, r) for r in ranges)
                self.assertIs(got, want)


# ------------------------------------------------------------------ match verdicts

def build_case(case):
    m = CASES["match"]
    inv = copy.deepcopy(m["inventory_base"])
    inv["components"] = copy.deepcopy(case["components"])
    rec = copy.deepcopy(m["advisory_base"])
    rec.update(copy.deepcopy(case["advisory"]))
    return inv, rec


class MatchVerdicts(TmpCase):
    def check_case(self, case):
        inv, rec = build_case(case)
        doc = match.run(inv, [rec], CAT, 0.5)
        by_comp = {f["component"]: f for f in doc["findings"]}
        for exp in case["expect"]:
            f = by_comp.get(exp["component"])
            self.assertIsNotNone(f, "%s: no finding for %s in %s" % (case["name"], exp["component"], list(by_comp)))
            self.assertEqual(f["verdict"], exp["verdict"], "%s: %s" % (case["name"], f))
            if "reason_prefix" in exp:
                self.assertTrue(f["reason"].startswith(exp["reason_prefix"]), "%s: reason %r" % (case["name"], f["reason"]))
            for k in ("priority", "fixed", "installed", "nodes_pending", "ami_before_fix"):
                if k in exp:
                    self.assertEqual(f[k], exp[k], "%s: %s" % (case["name"], k))
            if f["verdict"] == "not_exposed":
                comp = next((c for c in inv["components"] if c["id"] == f["component"]), None)
                self.assertTrue(comp and comp["readable"], "not_exposed given for a component that was not read")
        for absent in case.get("absent", []):
            self.assertNotIn(absent, by_comp, "%s: %s should not be targeted" % (case["name"], absent))
        self.assertEqual(doc["overall"], case["overall"], "%s: overall" % case["name"])
        self.assertEqual(doc["coverage"]["complete"], case["exit"] == 0, "%s: coverage %s" % (case["name"], doc["coverage"]))
        # the same case through the CLI, for the exit code and the written file
        ip = self.write("inv-%s.json" % case["name"], inv)
        ap = self.write("adv-%s.json" % case["name"], [rec])
        op = os.path.join(self.tmp, "findings-%s.json" % case["name"])
        rc, out, err = run_py("match.py", ["--inventory", ip, "--advisories", ap, "--catalog", CATALOG, "--out", op])
        self.assertEqual(rc, case["exit"], "%s: exit %d, stderr %s" % (case["name"], rc, err))
        with open(op, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["overall"], case["overall"])
        self.assertEqual(stat.S_IMODE(os.stat(op).st_mode), 0o600)


def _add_match_tests():
    for case in CASES["match"]["cases"]:
        def t(self, case=case):
            self.check_case(case)
        t.__doc__ = "match: %s" % case["name"]
        setattr(MatchVerdicts, "test_%s" % case["name"], t)


_add_match_tests()


class MatchInputErrors(TmpCase):
    def test_bad_inventory_schema_exit_2(self):
        ip = self.write("inv.json", {"schema": "something-else"})
        ap = self.write("adv.json", [CASES["match"]["advisory_base"]])
        rc, out, _ = run_py("match.py", ["--inventory", ip, "--advisories", ap, "--catalog", CATALOG])
        self.assertEqual(rc, 2)
        self.assertEqual(last_json(out)["ok"], False)

    def test_no_traceback_on_garbage(self):
        ip = self.write("inv.json", "not json")
        ap = self.write("adv.json", "[]")
        rc, out, err = run_py("match.py", ["--inventory", ip, "--advisories", ap, "--catalog", CATALOG])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err + out)


# ------------------------------------------------------------------ advisory_check

class AdvisoryCheck(TmpCase):
    AC = CASES["advisory_check"]

    def check(self, record, source_text=None, source_path=None):
        rp = self.write("record.json", record)
        sp = source_path or self.write("source.txt", source_text if source_text is not None else self.AC["saved_page"])
        return run_py("advisory_check.py", ["--record", rp, "--source", sp, "--catalog", CATALOG])

    def refused(self, record, code, **kw):
        rc, out, err = self.check(record, **kw)
        self.assertEqual(rc, 2, out + err)
        j = last_json(out)
        self.assertFalse(j["ok"])
        self.assertEqual(j["code"], code, j)
        self.assertNotIn("Traceback", err)
        return j

    def test_bulletin_worked_example_passes(self):
        rc, out, err = self.check(self.AC["record"])
        self.assertEqual(rc, 0, out + err)
        rec = json.loads(out)
        self.assertEqual(rec["affected"][1]["ranges"], [{"introduced": None, "fixed": "1.22.3", "last_affected": None}])
        self.assertIs(rec["workaround"], False)

    def test_user_saved_html_page_passes(self):
        rc, out, err = self.check(self.AC["record"], source_text=self.AC["html_page"])
        self.assertEqual(rc, 0, out + err)

    def test_quote_inside_script_tag_does_not_count(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["affected"] = [{"component": "image:aws-node/aws-network-policy-agent", "ranges": ["< 9.9.9"],
                            "quote": "aws-network-policy-agent < 9.9.9"}]
        self.refused(rec, "quote_not_found", source_text=self.AC["html_page"])

    def test_quote_not_found(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["affected"][0] = {"component": "image:aws-node/aws-network-policy-agent", "ranges": ["< 1.3.8"],
                              "quote": "aws-network-policy-agent < 1.3.8"}
        j = self.refused(rec, "quote_not_found")
        self.assertIn("1.3.8", j["error"])

    def test_one_bad_entry_refuses_whole_record(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["affected"].append({"component": "addon:coredns", "ranges": ["< 1.11.5"], "quote": "CoreDNS < 1.11.5"})
        rc, out, _ = self.check(rec)
        self.assertEqual(rc, 2)
        self.assertNotIn('"affected"', out, "a refused record must not be printed as normalized output")

    def test_unknown_component(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["affected"][0]["component"] = "addon:not-in-catalog"
        self.refused(rec, "unknown_component")

    def test_bad_range_unparseable(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["affected"][0]["ranges"] = ["> 1.3.7"]
        self.refused(rec, "bad_range")

    def test_bad_range_bound_not_in_quote(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["affected"][0]["ranges"] = ["< 1.3.9"]
        self.refused(rec, "bad_range")

    def test_schema_unknown_key(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["run_this"] = "kubectl delete ns kube-system"
        self.refused(rec, "schema")

    def test_schema_bad_severity(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["severity"] = "urgent"
        self.refused(rec, "schema")

    def test_source_unreadable_missing_file(self):
        self.refused(self.AC["record"], "source_unreadable", source_path=os.path.join(self.tmp, "missing.txt"))

    def test_source_url_mismatch(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["source_url"] = "https://aws.amazon.com/security/security-bulletins/2026-171-aws/"
        self.refused(rec, "source_unreadable")

    def test_live_origin_host_not_allowed(self):
        rec = copy.deepcopy(self.AC["record"])
        rec["origin"] = "live"
        rec["source_url"] = "https://example.com/bulletin"
        self.refused(rec, "schema", source_text="\n".join(self.AC["saved_page"].splitlines()[1:]))


# ------------------------------------------------------------------ advisory_fetch --input

class AdvisoryFetch(TmpCase):
    F = CASES["feeds"]

    def fetch(self, args, data, mode="w"):
        p = self.write("feed.in", data, mode)
        rc, out, err = run_py("advisory_fetch.py", list(args) + ["--input", p, "--catalog", CATALOG])
        return rc, out, err

    def ok(self, args, data, mode="w"):
        rc, out, err = self.fetch(args, data, mode)
        self.assertEqual(rc, 0, out + err)
        recs = json.loads(out)
        for r in recs:
            self.assertEqual(r["schema"], "eks-security/advisory@1")
            self.assertEqual(r["origin"], "file")
            self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", r["read_at"]), r["read_at"])
            self.assertIsNone(r["workaround"], "feeds do not state a workaround")
        return recs

    def test_ghsa_repo_advisory_maps_both_components(self):
        recs = self.ok(["--ghsa", "aws/aws-network-policy-agent/GHSA-mm5f-ggvx-hmvw"], json.dumps(self.F["ghsa_repo"]))
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["severity"], "high")
        self.assertEqual(r["severity_source"], "ghsa")
        aff = {e["component"]: e for e in r["affected"]}
        self.assertEqual(set(aff), {"addon:vpc-cni", "image:aws-node/aws-network-policy-agent"})
        self.assertEqual(aff["addon:vpc-cni"]["ranges"], [{"introduced": None, "fixed": "1.22.3", "last_affected": None}])
        self.assertEqual(aff["image:aws-node/aws-network-policy-agent"]["ranges"],
                         [{"introduced": None, "fixed": "1.3.7", "last_affected": None}])
        self.assertEqual(aff["addon:vpc-cni"]["quote"], "< 1.22.3")
        self.assertEqual(r["unmapped"], [])

    def test_ghsa_record_matches_inventory(self):
        recs = self.ok(["--ghsa", "aws/aws-network-policy-agent/GHSA-mm5f-ggvx-hmvw"], json.dumps(self.F["ghsa_repo"]))
        inv = copy.deepcopy(CASES["match"]["inventory_base"])
        inv["components"] = [
            {"id": "addon:vpc-cni", "kind": "eks-addon", "name": "vpc-cni", "version": "v1.22.3-eksbuild.1",
             "managed_by": "customer", "where": ["cluster"], "readable": True, "reason": None},
            {"id": "image:aws-node/aws-network-policy-agent", "kind": "container-image", "name": "aws-network-policy-agent",
             "version": "v1.3.6-eksbuild.1", "managed_by": "customer", "where": ["kube-system/daemonset/aws-node"],
             "readable": True, "reason": None}]
        doc = match.run(inv, recs, CAT, 0.5)
        v = {f["component"]: f["verdict"] for f in doc["findings"]}
        self.assertEqual(v, {"addon:vpc-cni": "not_exposed", "image:aws-node/aws-network-policy-agent": "exposed"})
        self.assertEqual(doc["overall"], "exposed")

    def test_ghsa_not_found(self):
        rc, out, _ = self.fetch(["--ghsa", "aws/aws-network-policy-agent/GHSA-mm5f-ggvx-hmvw"],
                                json.dumps(self.F["ghsa_not_found"]))
        self.assertEqual(rc, 2)
        self.assertEqual(last_json(out)["code"], "not_found")

    def test_ghsa_bad_id_refused(self):
        for bad in ("aws/aws-network-policy-agent/GHSA-zzzz", "aws/a b/GHSA-mm5f-ggvx-hmvw", "aws/GHSA-mm5f-ggvx-hmvw"):
            with self.subTest(ghsa=bad):
                rc, out, _ = self.fetch(["--ghsa", bad], json.dumps(self.F["ghsa_repo"]))
                self.assertEqual(rc, 2)
                self.assertEqual(last_json(out)["code"], "usage")

    def test_ghsa_dot_segment_refused(self):
        # "." and ".." are not GitHub owner or repo names; accepted, they change the API path that is fetched
        for bad in ("aws/../GHSA-mm5f-ggvx-hmvw", "../aws-network-policy-agent/GHSA-mm5f-ggvx-hmvw"):
            with self.subTest(ghsa=bad):
                rc, out, _ = self.fetch(["--ghsa", bad], json.dumps(self.F["ghsa_repo"]))
                self.assertEqual(rc, 2, "BUG advisory_fetch.py _REPO_PART accepts a dot segment %r as owner/repo "
                                        "(exit %d); expected usage refusal" % (bad, rc))

    def test_k8s_json_feed(self):
        recs = self.ok(["--k8s", "--since", "2000-01-01"], json.dumps(self.F["k8s"]))
        by = {r["id"]: r for r in recs}
        self.assertEqual(set(by), {"CVE-2026-76654", "CVE-2026-2270", "CVE-2099-0001"})
        self.assertEqual(by["CVE-2026-76654"]["severity"], "medium")  # published label "Medium (5.8)"
        self.assertEqual(by["CVE-2026-2270"]["severity"], "medium")   # computed from the CVSS 3.1 vector (5.9)
        self.assertIn("kubelet: <= v1.34.11", by["CVE-2026-76654"]["notes"])
        self.assertEqual(by["CVE-2026-76654"]["affected"], [])

    def test_injected_instruction_kept_as_data(self):
        inject = self.F["injected_text"]
        recs = self.ok(["--k8s", "--since", "2000-01-01"], json.dumps(self.F["k8s"]))
        r = next(x for x in recs if x["id"] == "CVE-2099-0001")
        self.assertEqual(r["title"], inject, "advisory text must be copied verbatim, not acted on")
        self.assertEqual(r["affected"], [])
        inv = copy.deepcopy(CASES["match"]["inventory_base"])
        inv["components"] = [{"id": "addon:vpc-cni", "kind": "eks-addon", "name": "vpc-cni", "version": "v1.23.0",
                              "managed_by": "customer", "where": ["cluster"], "readable": True, "reason": None}]
        doc = match.run(inv, [r], CAT, 0.5)
        self.assertNotEqual(doc["overall"], "not_exposed", "an instruction in advisory text must not set the verdict")
        self.assertEqual([x["title"] for x in doc["review"]], [inject])
        fp = self.write("findings.json", doc)
        ip = self.write("inventory.json", inv)
        md, ht = os.path.join(self.tmp, "r.md"), os.path.join(self.tmp, "r.html")
        rc, out, err = run_py("render_report.py", ["--findings", fp, "--inventory", ip, "--out-md", md, "--out-html", ht])
        self.assertEqual(rc, 0, out + err)
        with open(ht, encoding="utf-8") as f:
            h = f.read()
        self.assertNotIn("<script", h)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", h)
        self.assertIn("kubectl delete namespace kube-system", h)

    def test_alas_al2023_rss(self):
        recs = self.ok(["--alas", "al2023", "--since", "2000-01-01"], self.F["alas_al2023"])
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["id"], "ALAS2023-2026-3338")
        self.assertEqual(r["severity"], "important")
        self.assertEqual(r["packages"], [{"name": "emacs"}])
        self.assertEqual(r["affected"][0]["component"], "node-os:al2023")
        self.assertEqual(r["aliases"], ["CVE-2026-108976"])

    def test_alas_al2_rss_and_flavor_filter(self):
        recs = self.ok(["--alas", "al2", "--since", "2000-01-01"], self.F["alas_al2"])
        self.assertEqual([(r["id"], r["affected"][0]["component"], r["severity"]) for r in recs],
                         [("ALAS2DOCKER-2026-156", "node-os:al2", "medium")])
        self.assertEqual(self.ok(["--alas", "al2", "--since", "2000-01-01"], self.F["alas_al2023"]), [])

    def test_bottlerocket_updateinfo_gzip(self):
        recs = self.ok(["--bottlerocket", "--since", "2000-01-01"], base64.b64decode(self.F["bottlerocket_gz_b64"]), "wb")
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["id"], "GHSA-mgxf-pj6m-9494")
        self.assertEqual(r["severity"], "medium")
        self.assertEqual(r["aliases"], ["CVE-2020-10711"])
        self.assertEqual(r["packages"], [{"name": "kernel", "fixed": "0.3.3-b7d91846"}])
        self.assertEqual(r["affected"][0]["component"], "node-os:bottlerocket")
        self.assertTrue(r["source_url"].startswith("https://github.com/bottlerocket-os/"))

    def test_xml_doctype_entity_refused(self):
        for key in ("doctype_xml", "entity_only_xml"):
            with self.subTest(fixture=key):
                rc, out, err = self.fetch(["--alas", "al2023", "--since", "2000-01-01"], self.F[key])
                self.assertEqual(rc, 2, out)
                j = last_json(out)
                self.assertEqual(j["code"], "parse_error")
                self.assertIn("DOCTYPE", j["error"])
                self.assertNotIn("boom", out)


# ------------------------------------------------------------------ render_report

class RenderReport(TmpCase):
    RD = CASES["render"]

    def render(self, fd, inv=None):
        fp = self.write("findings.json", fd)
        args = ["--findings", fp]
        if inv is not None:
            args += ["--inventory", self.write("inventory.json", inv)]
        md, ht = os.path.join(self.tmp, "report.md"), os.path.join(self.tmp, "report.html")
        rc, out, err = run_py("render_report.py", args + ["--out-md", md, "--out-html", ht])
        texts = []
        for p in (md, ht):
            with open(p, encoding="utf-8") as f:
                texts.append(f.read())
        return rc, texts[0], texts[1], out + err

    def fixture(self):
        fd = copy.deepcopy(self.RD["findings"])
        fd["sources"][0]["title"] = self.RD["xss_title"]
        fd["sources"][1]["title"] = self.RD["pipe_title"]
        fd["findings"][1]["reason"] = self.RD["xss_title"]
        inv = copy.deepcopy(CASES["match"]["inventory_base"])
        inv["components"] = [{"id": "addon:vpc-cni", "kind": "eks-addon", "name": "vpc-cni", "version": "v1.21.1-eksbuild.3",
                              "managed_by": "customer", "where": ["cluster"], "readable": True, "reason": None}]
        return fd, inv

    def test_html_escaped_once(self):
        fd, inv = self.fixture()
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("<script", ht)
        self.assertNotIn("<img", ht)
        self.assertNotIn("onerror=1>", ht)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; and &quot;&gt;&lt;img src=x onerror=1&gt;", ht)
        for double in ("&amp;lt;", "&amp;gt;", "&amp;quot;", "&amp;amp;"):
            self.assertNotIn(double, ht, "double escape %s" % double)

    def test_markdown_escaped(self):
        fd, inv = self.fixture()
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("<script", md)
        self.assertNotIn("<img", md)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", md)
        self.assertIn("left\\|right", md)
        row = next(ln for ln in md.splitlines() if "left\\|right" in ln)
        cells = re.split(r"(?<!\\)\|", row.strip())[1:-1]
        self.assertEqual(len(cells), 5, "pipe in a cell must not add a column: %r" % row)

    def test_footer_and_origin(self):
        fd, inv = self.fixture()
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        footer = "The scripts that produced this report are read-only; they changed nothing."
        self.assertIn(footer, md)
        self.assertIn("<footer><p>" + footer + "</p></footer>", ht)
        self.assertIn("from file, not live", md)
        self.assertIn("from file, not live", ht)

    def test_no_active_content_in_html(self):
        fd, inv = self.fixture()
        rc, md, ht, log = self.render(fd, inv)
        self.assertNotRegex(ht, r"(?i)<script|javascript:|<iframe|<object|<embed|<img|<[a-z][^>]*\son[a-z]+\s*=")
        self.assertIn("default-src 'none'", ht)

    def test_rotation_pending_overall(self):
        fd, inv = self.fixture()
        fd["findings"] = [dict(fd["findings"][0], component="addon:vpc-cni@auto-mode", verdict="aws_managed_rotation_pending",
                               nodes_pending=["i-old"], priority="P2")]
        fd["overall"] = "rotation_pending"
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertIn("Overall verdict: Rotation pending", md)
        self.assertIn("Auto Mode nodes pending rotation", md)

    def test_incomplete_exit_3(self):
        fd, inv = self.fixture()
        fd["coverage"].update({"read": 0, "ratio": 0.0, "complete": False})
        fd["overall"] = "incomplete"
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 3, log)
        self.assertIn("Incomplete", md)

    def test_unsafe_value_not_placed_in_command(self):
        fd, inv = self.fixture()
        fd["cluster"] = "demo; rm -rf ~"
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        cmds = [ln for ln in md.splitlines() if ln.startswith("aws ")]
        self.assertTrue(cmds, "expected proposed commands for an exposed add-on")
        for ln in cmds:
            self.assertNotIn("rm -rf", ln)
        self.assertTrue(any("<CLUSTER>" in ln for ln in cmds))

    def test_not_exposed_wording_introduced_and_last_affected(self):
        # M1: a version below `introduced`, and a `last_affected`-only range, are outside the ranges, not "at or above"
        inv = copy.deepcopy(CASES["match"]["inventory_base"])
        inv["components"] = [{"id": "addon:vpc-cni", "kind": "eks-addon", "name": "vpc-cni", "version": "v1.22.3-eksbuild.1",
                              "managed_by": "customer", "where": ["cluster"], "readable": True, "reason": None}]
        base = CASES["match"]["advisory_base"]
        recs = [dict(base, id=i, affected=[{"component": "addon:vpc-cni", "ranges": [r], "quote": "vpc-cni " + r}])
                for i, r in (("CVE-TEST-0001", ">= 1.23.0, < 1.23.4"), ("CVE-TEST-0003", "<= 1.20.0"))]
        fd = match.run(inv, recs, CAT, 0.5)
        self.assertEqual({f["verdict"] for f in fd["findings"]}, {"not_exposed"}, fd["findings"])
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertIn("Not exposed: addon:vpc-cni v1.22.3-eksbuild.1 is outside every affected range of CVE-TEST-0001 "
                      "(fixed in: 1.23.4)", md)
        self.assertIn("Not exposed: addon:vpc-cni v1.22.3-eksbuild.1 is outside every affected range of CVE-TEST-0003 "
                      "(fixed in: none stated)", md)
        self.assertNotIn("at or above the fixed version", md)

    def test_patched_with_exposed_one_overall_line(self):
        # M8: an AWS-patched Auto Mode finding beside an exposed one prints one "Overall verdict:" line
        fd, inv = self.fixture()
        fd["findings"].append(dict(fd["findings"][0], component="addon:vpc-cni@auto-mode", verdict="aws_managed_patched",
                                   fixed_at="2026-11-01", priority="P4"))
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertEqual(len([ln for ln in md.splitlines() if ln.startswith("Overall verdict:")]), 1, md)
        self.assertIn("Overall verdict: Exposed", md)
        self.assertIn("Auto Mode components: AWS-patched (inferred, not read): every Auto Mode node it was judged on "
                      "was created at or after the fix time", md)

    def patched_fixture(self):
        fd, inv = self.fixture()
        fd["findings"].append(dict(fd["findings"][0], component="addon:vpc-cni@auto-mode", verdict="aws_managed_patched",
                                   fixed_at="2026-11-01", priority="P4"))
        node = {"kind": "node-os", "kernel": "6.1.0", "kubelet": "v1.33.1", "runtime": "containerd://1.7.27",
                "readable": True, "reason": None}
        inv["components"] += [
            dict(node, id="node-os:general-purpose", os_image="Bottlerocket OS 1.40.0 (aws-k8s-1.33)",
                 ami="ami-0aaa1111bbbb2222c", nodes=["i-a", "i-b"], managed_by="aws-auto-mode", where=["general-purpose"],
                 node_created={"i-a": "2026-11-02T01:00:00Z", "i-b": "2026-11-03T01:00:00Z"},
                 oldest_node_created="2026-11-02T01:00:00Z"),
            dict(node, id="node-os:system", os_image="Bottlerocket OS 1.40.0 (aws-k8s-1.33)", ami=None, nodes=["i-c"],
                 managed_by="aws-auto-mode", where=["system"], node_created={"i-c": "2026-11-04T01:00:00Z"},
                 oldest_node_created="2026-11-04T01:00:00Z"),
            dict(node, id="node-os:workers", os_image="Amazon Linux 2023", ami="ami-0ccc3333dddd4444e", nodes=["i-d"],
                 managed_by="customer", where=["workers"], node_created={"i-d": "2026-10-01T01:00:00Z"},
                 oldest_node_created="2026-10-01T01:00:00Z")]
        return fd, inv

    def test_patched_lists_auto_mode_groups(self):
        # A1: the AWS-patched line lists each Auto Mode NodePool's OS image and AMI, so the reader need not look them up
        fd, inv = self.patched_fixture()
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertIn("so a node created after the fix time can still run an older AMI.\n", md)
        self.assertIn("| NodePool | OS image | AMI | AMI built | Nodes | Oldest node created |", md)
        self.assertIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | ami-0aaa1111bbbb2222c | not read | 2 | "
                      "2026-11-02T01:00:00Z |", md)
        self.assertIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | not read | not read | 1 | 2026-11-04T01:00:00Z |",
                      md)
        self.assertNotIn("ami-0ccc3333dddd4444e", md)
        for cell in ("<th>NodePool</th>", "<td>general-purpose</td>", "<td>ami-0aaa1111bbbb2222c</td>",
                     "<td>not read</td>"):
            self.assertIn(cell, ht)
        self.assertNotIn("ami-0ccc3333dddd4444e", ht)

    def test_patched_flags_ami_built_before_fix(self):
        # a NodePool whose AMI was built before the fix time is likely unpatched, per advisory; after it, no flag
        fd, inv = self.patched_fixture()
        comps = {c["id"]: c for c in inv["components"]}
        comps["node-os:general-purpose"]["ami_created"] = "2026-10-20T11:06:51.000Z"
        comps["node-os:system"].update(ami="ami-0bbb2222cccc3333d", ami_created="2026-11-02T00:00:00.000Z")
        fd["findings"][-1].update(ami_before_fix=["node-os:general-purpose"])
        fd["findings"].append(dict(fd["findings"][-1], advisory="CVE-TEST-0009", fixed_at="2026-10-01", ami_before_fix=[]))
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertIn("Likely unpatched for CVE-TEST-0001 (fix time 2026-11-01): general-purpose. These nodes were created "
                      "after the fix time but run an older AMI", md)
        self.assertIn("Replace these NodePools' nodes and run the review again.", md)
        self.assertNotIn("Likely unpatched for CVE-TEST-0009", md + ht)
        self.assertIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | ami-0aaa1111bbbb2222c | "
                      "2026-10-20T11:06:51.000Z | 2 |", md)
        self.assertIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | ami-0bbb2222cccc3333d | 2026-11-02T00:00:00.000Z | 1 |",
                      md)
        self.assertIn("<td>2026-10-20T11:06:51.000Z</td>", ht)
        # no AMI built before the fix: no line; an unread date reads "not read" and the pool stays listed
        comps["node-os:general-purpose"]["ami_created"] = None
        for f in fd["findings"]:
            f["ami_before_fix"] = []
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("Likely unpatched", md + ht)
        self.assertIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | ami-0aaa1111bbbb2222c | not read | 2 |", md)

    def test_patched_table_skips_pending_pool(self):
        # M1: a node-os finding is judged on its own pool, so a pending pool is not listed under AWS-patched
        fd, inv = self.patched_fixture()
        base = fd["findings"][-1]
        fd["findings"][-1] = dict(base, component="node-os:general-purpose")
        fd["findings"].append(dict(base, component="node-os:system", verdict="aws_managed_rotation_pending",
                                   nodes_pending=["i-c"]))
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | ami-0aaa1111bbbb2222c | not read | 2 |", md)
        self.assertNotIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | not read |", md)
        # R2-1: an add-on patched on every Auto Mode node does not bring back a pool another advisory holds as pending
        fd, inv = self.patched_fixture()
        addon = fd["findings"][-1]
        fd["findings"] += [dict(addon, advisory="CVE-TEST-0009", component="node-os:general-purpose"),
                           dict(addon, advisory="CVE-TEST-0009", component="node-os:system",
                                verdict="aws_managed_rotation_pending", nodes_pending=["i-c"])]
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | ami-0aaa1111bbbb2222c | not read | 2 |", md)
        self.assertNotIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | not read |", md)
        # R2-1 residual: a pool whose node an add-on advisory holds as pending is not listed under AWS-patched;
        # pending is every node created before the fix time, so it holds i-a and i-b, not i-c
        fd, inv = self.patched_fixture()
        addon = fd["findings"][-1]
        fd["findings"].append(dict(addon, advisory="CVE-TEST-0009", verdict="aws_managed_rotation_pending",
                                   nodes_pending=["i-a", "i-b"]))
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) |", md)
        self.assertIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | not read | not read | 1 |", md)

    def split_patched_fixture(self):
        # general-purpose split into two node groups mid-rotation: i-b on the new AMI, i-a still on the old one
        fd, inv = self.patched_fixture()
        gp = next(c for c in inv["components"] if c["id"] == "node-os:general-purpose")
        gp.update(nodes=["i-b"], node_created={"i-b": "2026-11-03T01:00:00Z"}, oldest_node_created="2026-11-03T01:00:00Z")
        inv["components"].append(dict(gp, id="node-os:general-purpose/2", ami="ami-0eee5555ffff6666a", nodes=["i-a"],
                                      node_created={"i-a": "2026-11-02T01:00:00Z"},
                                      oldest_node_created="2026-11-02T01:00:00Z"))
        return fd, inv

    def test_patched_table_skips_split_pending_pool(self):
        # M2: a NodePool split into two node groups mid-rotation is left out when any of its nodes is pending
        fd, inv = self.split_patched_fixture()
        addon = fd["findings"][-1]
        fd["findings"].append(dict(addon, advisory="CVE-TEST-0009", verdict="aws_managed_rotation_pending",
                                   nodes_pending=["i-a"]))
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) |", md)
        self.assertNotIn("ami-0aaa1111bbbb2222c", md + ht)
        self.assertNotIn("ami-0eee5555ffff6666a", md + ht)
        self.assertIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | not read | not read | 1 |", md)

    def test_patched_table_skips_split_pool_node_os_pending(self):
        # a node-os finding pending on the split pool's second node group, with no nodes_pending, leaves out the pool
        fd, inv = self.split_patched_fixture()
        fd["findings"].append(dict(fd["findings"][-1], component="node-os:general-purpose/2",
                                   verdict="aws_managed_rotation_pending"))
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("| general-purpose | Bottlerocket OS 1.40.0 (aws-k8s-1.33) |", md)
        self.assertIn("| system | Bottlerocket OS 1.40.0 (aws-k8s-1.33) | not read | not read | 1 |", md)

    def test_unknown_actions_for_nodes_build_and_minor(self):
        # S2: no_nodes_read, eks_build and minor_only each get their own action, not the generic one
        fd, inv = self.fixture()
        fd["findings"] = [dict(fd["findings"][1], component="c%d" % i, reason=r + ": x")
                          for i, r in enumerate(("no_nodes_read", "eks_build", "minor_only"))]
        fd["overall"] = "unknown"
        rc, md, ht, log = self.render(fd, inv)
        self.assertEqual(rc, 0, log)
        for text in ("No Auto Mode node was read; check the nodes read in the preflight (read-only-access.md) and that "
                     "the NodePools have nodes, then re-run collect",
                     "To resolve: Compare the build with the advisory by hand.",
                     "The installed version names no patch release; find the patch release (for the control plane, "
                     "from its platform version) and compare by hand"):
            self.assertIn(text, md)
        self.assertNotIn("Read the advisory and the installed version by hand", md)


# ------------------------------------------------------------------ collectors: read-only guard

RULES = CASES["collect"]["rules"]
COMMANDS = CASES["collect"]["commands"]
_KW_END = re.compile(r"(?:^|[\s;&|({])(then|do|else|elif|if|while|until|time)$")
_SEP_END = re.compile(r"(;|\||&&|\$\(|\(|\{|!|`)$")
_WRAP_END = re.compile(r"(?:^|[\s;&|({])(call\s+\S+\s+\S+|probe_aws\s+\S+)$")
_PREFIX_TAIL = re.compile(r"(?:^|\s)(?:\w+=\S*|timeout\s+\d+)$")
_VAR = re.compile(r"^\$\{?(\w+|@|\*)\}?$")


def command_position(before):
    b = before.rstrip()
    while True:  # drop trailing VAR=value assignments and `timeout N` prefixes
        nb = _PREFIX_TAIL.sub("", b).rstrip()
        if nb == b:
            break
        b = nb
    return b == "" or bool(_SEP_END.search(b) or _KW_END.search(b) or _WRAP_END.search(b))


def logical_lines(src):
    """(first line number, text) with backslash continuations joined and comments removed."""
    out, buf, start = [], "", None
    for n, line in enumerate(src.splitlines(), 1):
        code = re.sub(r"(^|\s)#.*$", "", line)
        if start is None:
            start = n
        if code.rstrip().endswith("\\"):
            buf += code.rstrip()[:-1] + " "
            continue
        out.append((start, buf + code))
        buf, start = "", None
    return out


def for_values(src):
    """{var: set of words} from every `for VAR in w1 w2 ...;` loop with literal words."""
    vals = {}
    for _, code in logical_lines(src):
        for m in re.finditer(r"\bfor\s+(\w+)\s+in\s+([^;]+);", code):
            words = m.group(2).split()
            if all(re.match(r"^[A-Za-z0-9._:/-]+$", w) for w in words):
                vals.setdefault(m.group(1), set()).update(words)
    return vals


def scan_invocations(src, commands):
    """[(line, tool, args, function)] for every command-table name in command position.

    args are the command's own arguments: a wrapper's leading skip arguments are dropped and its
    fixed prefix is prepended. Shell variables stay as `$NAME` tokens.
    """
    names = sorted(commands, key=len, reverse=True)
    rx = re.compile(r"(?<![\w./$:@-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w.:-])")
    found, func = [], None
    for n, code in logical_lines(src):
        fm = re.match(r"^\s*(\w+)\(\)\s*\{", code)
        if fm:
            func = fm.group(1)
        elif re.match(r"^\}", code):
            func = None
            continue
        for m in rx.finditer(code):
            if not command_position(code[:m.start()]):
                continue
            rest = code[m.end():]
            if rest.lstrip().startswith("()"):
                continue  # a function definition, not a call
            rest = re.split(r"[;|)<>]|&&", rest)[0]
            try:
                toks = shlex.split(rest)
            except ValueError:
                toks = rest.split()
            spec = commands[m.group(1)]
            toks = list(spec.get("prefix", [])) + toks[spec.get("skip", 0):]
            found.append((n, spec["tool"], toks, func))
        if fm and code.rstrip().endswith("}"):
            func = None  # one-line function
    return found


def strip_globals(tool, args):
    a = list(args)
    while a:
        if tool == "kubectl" and a[0] in RULES["kubectl_global_flags"]:
            a = a[2:]
        elif a[0].startswith("$"):
            a = a[1:]  # ${KCFG:+--kubeconfig "$KCFG"} and similar optional flag groups
        else:
            break
    return a


def invocation_problem(tool, args):
    """None if the call is read-only by the rule, else a description. args hold no shell variables."""
    for a in args:
        low = a.lower()
        bad = (set(re.split(r"[,/.=:]", low)) | {low}) & set(RULES["forbidden_words"])
        if bad:
            return "forbidden word %s in %r" % (sorted(bad), a)
    a = strip_globals(tool, args)
    if tool == "aws":
        if not a:
            return "bare aws"
        if a[0].startswith("-"):
            return None if a[0] in RULES["aws_flag_only"] else "aws flag form %s" % a[0]
        if len(a) < 2:
            return "aws without an operation"
        svc, op = a[0], a[1]
        if any(op.startswith(p) for p in RULES["aws_op_prefixes"]) or "%s %s" % (svc, op) in RULES["aws_extra"]:
            return None
        return "aws %s %s is not a read call" % (svc, op)
    if not a:
        return "kubectl with no subcommand"
    if a[0] in RULES["kubectl_verbs"]:
        return None
    if len(a) > 1 and "%s %s" % (a[0], a[1]) in RULES["kubectl_pairs"]:
        return None
    return "kubectl %s is not a read call" % a[0]


def static_problems(src, commands):
    """Check every invocation; resolve `$VAR` from literal for-loops; allow pass-through only in wrappers."""
    loops = for_values(src)
    wrappers = set(commands) - {"aws", "kubectl"}
    problems, checked = [], []
    for n, tool, args, func in scan_invocations(src, commands):
        a = strip_globals(tool, args)
        verb_n = 2 if tool == "aws" else (2 if a[:1] in (["auth"], ["config"]) else 1)
        unresolved = [t for t in a[:verb_n] if _VAR.match(t)] + [t for t in args if _VAR.match(t) and _VAR.match(t).group(1) in ("@", "*")]
        if unresolved:
            if func in wrappers:
                continue  # the wrapper's own body: its call sites are checked instead
            var = _VAR.match(unresolved[0]).group(1)
            if var not in loops:
                problems.append((n, tool, args, "unresolved pass-through %s outside a known wrapper" % unresolved[0]))
                continue
        variants = [[]]
        for t in args:
            m = _VAR.match(t)
            if m and m.group(1) in loops:
                variants = [v + [w] for v in variants for w in sorted(loops[m.group(1)])]
            elif m:
                continue  # a value we cannot know; verbs were resolved above
            else:
                variants = [v + [t] for v in variants]
        for v in variants:
            checked.append((tool, v))
            p = invocation_problem(tool, v)
            if p:
                problems.append((n, tool, v, p))
    return problems, checked


def write_stubs(bindir):
    os.mkdir(bindir)
    for tool in ("aws", "kubectl"):
        p = os.path.join(bindir, tool)
        with open(p, "w", encoding="utf-8") as f:
            f.write(STUB.replace("{python}", sys.executable))
        os.chmod(p, 0o700)


STUB = r'''#!{python} -B
import json, os, sys
tool = os.path.basename(sys.argv[0])
args = sys.argv[1:]
cfg = json.load(open(os.environ["STUB_RESP"]))
resp = cfg[tool]
a = list(args)
while a and a[0] in ("--context", "--kubeconfig", "--cache-dir"):
    a = a[2:]
if tool == "aws" and a and a[0].startswith("--"):
    keys = [a[0]]
else:
    keys = [" ".join(a[:3]), " ".join(a[:2]), a[0] if a else ""]
    if "--addon-name" in a:
        keys.insert(0, " ".join(a[:2]) + " " + a[a.index("--addon-name") + 1])
r = next((resp[k] for k in keys if k in resp), None)
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps({"tool": tool, "args": args, "known": r is not None}) + "\n")
if r is None and cfg.get("lenient"):
    r = {"json": {} if tool == "aws" else {"apiVersion": "v1", "kind": "List", "items": []}}
if r is None:
    sys.stderr.write("An error occurred (ResourceNotFoundException): stub has no response for %s\n" % keys)
    sys.exit(254)
for flag, alt in (r.get("if_arg") or {}).items():
    if flag in args:
        r = alt
if "--query" in args and args[args.index("--query") + 1] in (r.get("query") or {}):
    print(r["query"][args[args.index("--query") + 1]])
    sys.exit(0)
if "rc" in r:
    sys.stderr.write(r.get("stderr", "") + "\n")
    sys.exit(r["rc"])
if "file" in r:
    r = {"json": cfg["files"][r["file"]]}
if "text" in r and ("json" not in r or ("--output" in args and args[args.index("--output") + 1] == "text")):
    print(r["text"])
else:
    print(json.dumps(r["json"]))
'''


def run_collector(test, script, args, responses):
    """Run a collector with fake aws/kubectl first on PATH; return (process, recorded calls)."""
    bindir = os.path.join(test.tmp, "bin")
    write_stubs(bindir)
    resp = test.write("responses.json", responses)
    log = os.path.join(test.tmp, "calls.jsonl")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "KUBECONFIG"))}
    env.update({"PATH": bindir + os.pathsep + env.get("PATH", "/usr/bin:/bin"), "STUB_RESP": resp, "STUB_LOG": log,
                "HOME": test.tmp})
    p = subprocess.run(["bash", os.path.join(ASSETS, script)] + list(args), capture_output=True, text=True,
                       timeout=300, env=env, cwd=test.tmp)
    calls = []
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            calls = [json.loads(ln) for ln in f if ln.strip()]
    return p, calls


def assert_private_tree(test, top):
    test.assertEqual(stat.S_IMODE(os.stat(top).st_mode), 0o700, "%s must be 0700" % top)
    for name in os.listdir(top):
        p = os.path.join(top, name)
        if os.path.isdir(p):
            test.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o700, p)
        else:
            test.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600, p)


NEEDS_JQ = unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "needs bash and jq")


class CollectReadOnly(TmpCase):
    def src(self, script):
        with open(os.path.join(ASSETS, script), encoding="utf-8") as f:
            return f.read()

    def test_scanner_negative_control(self):
        sample = "\n".join([
            "for t in aws kubectl jq; do command -v \"$t\"; done",
            "x=oldest_node_created; y=--output",
            "fail usage \"aws eks update-addon is never run\"",
            "# kubectl delete ns kube-system",
            "kubectl exec -it pod -- sh",
            "aws eks update-addon --cluster-name c",
            "kc get secrets -A",
            "v=\"$(kubectl get nodes -o json)\"",
            "call \"$OUT/x.json\" step aws eks describe-cluster --name c",
            "for op in describe-volumes delete-volume; do timeout 9 aws ec2 \"$op\"; done",
            "kubectl \"$@\"",
            "kubectl port-forward svc/x 8080:80",
        ])
        problems, checked = static_problems(sample, COMMANDS["collect.sh"])
        lines = sorted({p[0] for p in problems})
        self.assertEqual(lines, [5, 6, 7, 10, 11, 12], problems)
        self.assertIn(("kubectl", ["get", "nodes", "-o", "json"]), checked)
        self.assertIn(("aws", ["ec2", "describe-volumes"]), checked)

    def check_static(self, script, min_aws, min_kube, must_see):
        src = self.src(script)
        problems, checked = static_problems(src, COMMANDS[script])
        aws = [a for t, a in checked if t == "aws"]
        kube = [a for t, a in checked if t == "kubectl"]
        self.assertGreaterEqual(len(aws), min_aws, "scanner found too few aws calls in %s: %s" % (script, aws))
        self.assertGreaterEqual(len(kube), min_kube, "scanner found too few kubectl calls in %s: %s" % (script, kube))
        seen = {" ".join(strip_globals(t, a)[:2]) for t, a in checked}
        for s in must_see:
            self.assertIn(s, seen, "%s: expected to see %s" % (script, s))
        self.assertEqual(problems, [], "%s has a command that is not read-only" % script)

    def test_collect_static_commands_read_only(self):
        self.check_static("collect.sh", 15, 4, ["eks describe-cluster", "get nodes", "auth can-i", "inspector2 list-findings"])

    def test_posture_collect_static_commands_read_only(self):
        self.check_static("posture_collect.sh", 15, 15, ["eks describe-cluster", "get nodes", "auth can-i", "config view",
                                                          "ec2 describe-instances", "guardduty get-detector"])

    def test_no_forbidden_words_in_code(self):
        for script in ("collect.sh", "posture_collect.sh"):
            code = "\n".join(c for _, c in logical_lines(self.src(script)))
            for w in ("exec", "port-forward", "secret", "secrets"):
                with self.subTest(script=script, word=w):
                    self.assertIsNone(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(w), code), w)

    @NEEDS_JQ
    def test_collect_run_with_stubs(self):
        cc = CASES["collect"]
        work = os.path.join(self.tmp, "work")
        p, calls = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2", "--out", work],
                                 {"aws": cc["aws"], "kubectl": cc["kubectl"], "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(last_json(p.stdout)["ok"])
        assert_private_tree(self, work)
        self.assertTrue(calls)
        self.assertEqual([c for c in calls if not c["known"]], [], "collect.sh made a call the stub has no response for")
        bad = [(c["tool"], c["args"], invocation_problem(c["tool"], c["args"])) for c in calls
               if invocation_problem(c["tool"], c["args"])]
        self.assertEqual(bad, [], "a recorded call is not read-only")
        with open(os.path.join(work, "inventory.json"), encoding="utf-8") as f:
            inv = json.load(f)
        comps = {c["id"]: c for c in inv["components"]}
        self.assertFalse(comps["addon:vpc-cni"]["readable"])
        self.assertEqual(comps["addon:vpc-cni"]["reason"], "denied")
        self.assertTrue(comps["addon:coredns"]["readable"])
        npa = comps["image:aws-node/aws-network-policy-agent"]
        self.assertEqual((npa["version"], npa["readable"]), ("v1.2.0-eksbuild.1", True))
        with open(os.path.join(work, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertIn({"step": "describe-addon:vpc-cni", "code": "denied"},
                      [{"step": e["step"], "code": e["code"]} for e in meta["errors"]])
        # end to end: the worked example record against this inventory
        ap = self.write("adv.json", [CASES["advisory_check"]["record"]])
        fp = os.path.join(self.tmp, "findings.json")
        rc, out, err = run_py("match.py", ["--inventory", os.path.join(work, "inventory.json"), "--advisories", ap,
                                           "--catalog", CATALOG, "--out", fp])
        self.assertEqual(rc, 0, out + err)
        with open(fp, encoding="utf-8") as f:
            doc = json.load(f)
        v = {f["component"]: (f["verdict"], f["priority"]) for f in doc["findings"]}
        self.assertEqual(v["image:aws-node/aws-network-policy-agent"], ("exposed", "P1"))
        self.assertEqual(v["addon:vpc-cni"][0], "unknown")
        self.assertEqual(doc["overall"], "exposed")

    @NEEDS_JQ
    def test_collect_hidden_instance_found_by_id(self):
        # M2: an Auto Mode instance hidden from the filter call is looked up by its instance id
        cc = CASES["collect"]
        aws = dict(cc["aws"], **{"ec2 describe-instances": {"json": {"Reservations": []},
                                                            "if_arg": {"--instance-ids": cc["aws"]["ec2 describe-instances"]}}})
        work = os.path.join(self.tmp, "work")
        p, calls = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2", "--out", work],
                                 {"aws": aws, "kubectl": cc["kubectl"], "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        by_id = [c["args"] for c in calls if c["args"][:2] == ["ec2", "describe-instances"] and "--instance-ids" in c["args"]]
        self.assertEqual(len(by_id), 1, by_id)
        self.assertIn("i-0abc123", by_id[0])
        with open(os.path.join(work, "inventory.json"), encoding="utf-8") as f:
            amis = {c.get("ami") for c in json.load(f)["components"] if c.get("kind") == "node-os"}
        self.assertIn("ami-0123456789abcdef0", amis)
        # the AMI build date is kept per node group, and deprecated AMIs (past their owner-set deprecation time) are asked for
        img = [c["args"] for c in calls if c["args"][:2] == ["ec2", "describe-images"] and "--dry-run" not in c["args"]]
        self.assertEqual(len(img), 1, img)
        self.assertIn("--include-deprecated", img[0])
        with open(os.path.join(work, "inventory.json"), encoding="utf-8") as f:
            built = {c.get("ami"): c.get("ami_created") for c in json.load(f)["components"] if c.get("kind") == "node-os"}
        self.assertEqual(built.get("ami-0123456789abcdef0"), "2025-10-20T11:06:51.000Z")

    @NEEDS_JQ
    def test_collect_hybrid_node_not_looked_up(self):
        # LC-1: an SSM hybrid node (name mi-<hex>) is not an EC2 instance, so its providerID yields no instance id
        cc = CASES["collect"]
        aws = dict(cc["aws"], **{"ec2 describe-instances": {"json": {"Reservations": []},
                                                            "if_arg": {"--instance-ids": cc["aws"]["ec2 describe-instances"]}}})
        kubectl = copy.deepcopy(cc["kubectl"])
        hyb = copy.deepcopy(kubectl["get nodes"]["json"]["items"][0])
        hyb["metadata"] = {"name": "mi-0ccc123", "creationTimestamp": "2026-10-20T00:00:00Z", "labels": {}}
        hyb["spec"]["providerID"] = "eks-hybrid:///us-west-2/demo/mi-0ccc123"
        kubectl["get nodes"]["json"]["items"].append(hyb)
        work = os.path.join(self.tmp, "work")
        p, calls = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2", "--out", work],
                                 {"aws": aws, "kubectl": kubectl, "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        ec2 = [c["args"] for c in calls if c["args"][:2] == ["ec2", "describe-instances"]]
        self.assertFalse([a for a in ec2 if any("i-0ccc123" in x for x in a)], ec2)
        self.assertEqual(len([a for a in ec2 if "--instance-ids" in a]), 1, ec2)

    @NEEDS_JQ
    def test_collect_preflight_partial_k8s_not_ok(self):
        cc = CASES["collect"]
        kubectl = dict(cc["kubectl"], **{"auth can-i": {"text": "yes", "if_arg": {"--all-namespaces": {"text": "no"}}}})
        p, _ = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2", "--preflight-only",
                                                  "--out", os.path.join(self.tmp, "work")],
                             {"aws": cc["aws"], "kubectl": kubectl, "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = last_json(p.stdout)
        self.assertEqual(out["preflight"]["k8s:list nodes"], "ok")
        self.assertEqual(out["preflight"]["k8s:list pods"], "denied")
        self.assertFalse(out["ok"])

    def collect_inspector(self):
        """Full collect run with Inspector enabled: one running ECR image, one pod with no containerStatuses."""
        cc = CASES["collect"]
        ie = cc["inspector_enabled"]
        kubectl = copy.deepcopy(cc["kubectl"])
        kubectl["get pods,daemonsets,deployments,statefulsets"]["json"]["items"] += copy.deepcopy(ie["pods"])
        work = os.path.join(self.tmp, "work")
        p, _ = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2", "--out", work],
                             {"aws": dict(cc["aws"], **ie["aws"]), "kubectl": kubectl, "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(work, "inventory.json"), encoding="utf-8") as f:
            return {i["image"].rsplit("/", 1)[-1]: i["inspector"] for i in json.load(f)["images"]}

    @NEEDS_JQ
    def test_collect_zero_findings_carry_not_scanned_note(self):
        # M3: 0 findings is not proof of a scan; the image says so
        insp = self.collect_inspector()["app:v1"]
        self.assertEqual((insp["critical"], insp["high"], insp["findings"]), (0, 0, []), insp)
        self.assertEqual(insp["note"], "0 ACTIVE findings returned; whether Inspector scanned this image was not read "
                                       "(coverage is not collected)")

    @NEEDS_JQ
    def test_collect_pod_without_container_status_skipped(self):
        # M5: an image no running container reports was never queried, so it reads skipped, not 0 critical / 0 high
        insp = self.collect_inspector()["pending:v9"]
        self.assertEqual(insp, {"skipped": "image not queried: no running container reports it (pod has no "
                                           "containerStatuses)"})

    @NEEDS_JQ
    def test_collect_kubectl_not_logged_in_is_denied(self):
        # S8: kubectl's "must be logged in" (an unmapped principal) is denied, and not retried
        cc = CASES["collect"]
        kubectl = dict(cc["kubectl"], **{"get nodes": {"rc": 1, "stderr": "error: You must be logged in to the server "
                                                                         "(Unauthorized)"}})
        work = os.path.join(self.tmp, "work")
        p, calls = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2", "--out", work],
                                 {"aws": cc["aws"], "kubectl": kubectl, "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(work, "meta.json"), encoding="utf-8") as f:
            errs = {e["step"]: e["code"] for e in json.load(f)["errors"]}
        self.assertEqual(errs.get("kubectl-get-nodes"), "denied", errs)
        self.assertEqual(len([c for c in calls if c["tool"] == "kubectl" and c["args"][:2] == ["get", "nodes"]]), 1)

    @NEEDS_JQ
    def test_collect_result_names_preflight_not_ok(self):
        # S9: the result line lists every probe that is not ok under preflight_not_ok
        cc = CASES["collect"]
        kubectl = dict(cc["kubectl"], **{"auth can-i": {"text": "yes", "if_arg": {"--all-namespaces": {"text": "no"}}}})
        p, _ = run_collector(self, "collect.sh", ["--cluster", "demo", "--region", "us-west-2",
                                                  "--out", os.path.join(self.tmp, "work")],
                             {"aws": cc["aws"], "kubectl": kubectl, "files": {}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = last_json(p.stdout)
        self.assertNotIn("preflight_denied", out)
        self.assertIn("k8s:list pods", out["preflight_not_ok"])
        self.assertNotIn("k8s:list nodes", out["preflight_not_ok"])

    @NEEDS_JQ
    def test_posture_collect_run_with_stubs(self):
        pc = CASES["posture"]
        work = os.path.join(self.tmp, "work")
        p, calls = run_collector(self, "posture_collect.sh",
                                 ["--cluster", "demo", "--region", "us-west-2", "--context", "demo-ctx", "--work", work],
                                 {"aws": pc["stub_aws"], "kubectl": pc["stub_kubectl"], "files": pc["files"], "lenient": True})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(last_json(p.stdout)["ok"])
        assert_private_tree(self, os.path.join(work, "posture"))
        self.assertTrue(calls)
        bad = [(c["tool"], c["args"], invocation_problem(c["tool"], c["args"])) for c in calls
               if invocation_problem(c["tool"], c["args"])]
        self.assertEqual(bad, [], "a recorded call is not read-only")
        seen = {" ".join(strip_globals(c["tool"], c["args"])[:2]) for c in calls}
        for s in ("eks describe-cluster", "get nodes", "get pods", "ec2 describe-instances", "guardduty list-detectors"):
            self.assertIn(s, seen)
        P = os.path.join(work, "posture")
        self.assertFalse(os.path.exists(os.path.join(P, "guardduty.json")), "a denied read must not leave a file")
        with open(os.path.join(P, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["preflight"].get("guardduty:ListDetectors"), "denied")
        self.assertTrue(any(e["code"] == "denied" for e in meta["errors"]), meta["errors"])
        with open(os.path.join(P, "nodes.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), pc["files"]["nodes"])
        for script in ("posture_score.sh", "posture_extra.sh"):
            q = subprocess.run(["bash", os.path.join(ASSETS, script), work], capture_output=True, text=True, timeout=300)
            self.assertEqual(q.returncode, 0, q.stderr)
        q = subprocess.run(["bash", os.path.join(ASSETS, "posture_reduce.sh"), work], capture_output=True, text=True, timeout=120)
        self.assertIn(q.returncode, (0, 3), q.stdout + q.stderr)
        with open(os.path.join(work, "posture.json"), encoding="utf-8") as f:
            checks = {c["id"]: c for c in json.load(f)["checks"]}
        for cid in pc["expect"]["unknown_denied"]:
            self.assertEqual(checks[cid]["result"], "unknown", cid)


# ------------------------------------------------------------------ posture scorers and reducer

POSTURE_CHECK_KEYS = {"id", "war_id", "title", "result", "severity", "evidence", "source_file", "recommendation", "layer", "state"}
POSTURE_LAYERS = ["node-credential", "lateral-movement", "privilege", "identity", "detection", "api-exposure", "supply-chain"]


@NEEDS_JQ
class PostureScoring(TmpCase):
    PC = CASES["posture"]

    def build(self, names):
        work = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(work, "posture"), mode=0o700)
        for name in names:
            self.write(os.path.join("work", "posture", name + ".json"), self.PC["files"][name])
        return work

    def pipeline(self, work):
        for script in ("posture_score.sh", "posture_extra.sh"):
            q = subprocess.run(["bash", os.path.join(ASSETS, script), work], capture_output=True, text=True, timeout=300)
            self.assertEqual(q.returncode, 0, "%s: %s" % (script, q.stderr))
        for name in ("results.jsonl", "results-extra.jsonl"):
            with open(os.path.join(work, "posture", name), encoding="utf-8") as f:
                for ln in f:
                    t = json.loads(ln)
                    self.assertTrue({"pillar", "id", "track", "state", "detail"} <= set(t), t)
                    self.assertIn(t["state"], ("all", "most", "some", "none", "na", "unknown"))
                    self.assertIn(t["track"], ("measured", "governance"))
        q = subprocess.run(["bash", os.path.join(ASSETS, "posture_reduce.sh"), work], capture_output=True, text=True, timeout=120)
        with open(os.path.join(work, "posture.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(work, "posture.json")).st_mode), 0o600)
        return q, doc

    def check_shape(self, doc):
        self.assertEqual(doc["schema"], "eks-security/posture@1")
        self.assertEqual([x["layer"] for x in doc["layers"]], POSTURE_LAYERS)
        for x in doc["layers"]:
            self.assertIn(x["verdict"], ("contained", "partly", "not-contained", "unknown"))
        cov = doc["coverage"]
        self.assertEqual(cov["complete"], cov["checks_answered"] * 2 >= cov["checks_total"] > 0)
        for c in doc["checks"]:
            self.assertTrue(POSTURE_CHECK_KEYS <= set(c), c)
            self.assertIn(c["result"], ("pass", "fail", "na", "unknown"))
            if c["state"] in ("all",):
                self.assertEqual(c["result"], "pass")
            if c["state"] in ("most", "some", "none"):
                self.assertEqual(c["result"], "fail")

    def test_full_workdir(self):
        names = [n for n in self.PC["files"] if n != self.PC["denied_file"]]
        q, doc = self.pipeline(self.build(names))
        self.assertEqual(q.returncode, 0, q.stdout + q.stderr)
        self.check_shape(doc)
        checks = {c["id"]: c for c in doc["checks"]}
        layers = {x["layer"]: x["verdict"] for x in doc["layers"]}
        self.assertTrue(doc["coverage"]["complete"])
        self.assertIsInstance(doc["score"], int)
        self.assertTrue(0 <= doc["score"] <= 100)
        for cid in self.PC["expect"]["pass"]:
            self.assertEqual(checks[cid]["result"], "pass", checks[cid])
        hi = checks[self.PC["expect"]["fail_high"]]
        self.assertEqual((hi["result"], hi["severity"]), ("fail", "high"), hi)
        self.assertEqual(layers[self.PC["expect"]["fail_layer"]], "not-contained")
        for cid in self.PC["expect"]["unknown_denied"]:
            self.assertEqual(checks[cid]["result"], "unknown", checks[cid])
            self.assertIn("not collected", checks[cid]["evidence"])
        self.assertIn(self.PC["xss_tag"], hi["evidence"], "evidence names the failing node type, verbatim")
        # render: escaped evidence, posture section present
        md, ht = os.path.join(self.tmp, "p.md"), os.path.join(self.tmp, "p.html")
        rc, out, err = run_py("render_report.py", ["--posture", os.path.join(self.tmp, "work", "posture.json"),
                                                   "--out-md", md, "--out-html", ht])
        self.assertEqual(rc, 0, out + err)
        with open(ht, encoding="utf-8") as f:
            h = f.read()
        with open(md, encoding="utf-8") as f:
            m = f.read()
        self.assertNotIn("<script", h)
        self.assertNotIn("<script", m)
        self.assertIn("ng1&lt;script&gt;alert(1)&lt;/script&gt;", h)
        self.assertNotIn("&amp;lt;", h)
        self.assertIn("Score: %d of 100" % doc["score"], m)
        self.assertIn("not-contained", h)
        self.assertIn("The scripts that produced this report are read-only; they changed nothing.", m)

    def test_pass_with_failing_node_listed_as_exception(self):
        # M2: 9 of 10 nodes block IMDS, so the check passes, but the report still names the failing node
        names = [n for n in self.PC["files"] if n != self.PC["denied_file"]]
        work = self.build(names)
        node0 = self.PC["files"]["nodes"]["items"][0]
        inst0 = self.PC["files"]["instances"]["Reservations"][0]["Instances"][0]
        nodes, insts = [], []
        for i in range(10):
            iid = "i-0bad" if i == 9 else "i-0good%d" % i
            n = copy.deepcopy(node0)
            n["metadata"]["name"] = "node-%d" % i
            n["metadata"]["labels"]["eks.amazonaws.com/nodegroup"] = "general"
            n["spec"]["providerID"] = "aws:///us-west-2a/" + iid
            nodes.append(n)
            x = copy.deepcopy(inst0)
            x["InstanceId"] = iid
            x["Tags"] = [{"Key": "eks:nodegroup-name", "Value": "general"}, {"Key": "kubernetes.io/cluster/demo", "Value": "owned"}]
            x["MetadataOptions"] = {"HttpTokens": "required", "HttpPutResponseHopLimit": 2 if i == 9 else 1,
                                    "HttpEndpoint": "enabled"}
            insts.append(x)
        self.write(os.path.join("work", "posture", "nodes.json"), dict(self.PC["files"]["nodes"], items=nodes))
        self.write(os.path.join("work", "posture", "instances.json"), {"Reservations": [{"Instances": insts}]})
        q, doc = self.pipeline(work)
        c55 = next(c for c in doc["checks"] if c["id"] == "SEC-POSTURE-55")
        self.assertEqual(c55["result"], "pass", c55)
        self.assertIn("; failing: i-0bad", c55["evidence"])
        md, ht = os.path.join(self.tmp, "p.md"), os.path.join(self.tmp, "p.html")
        rc, out, err = run_py("render_report.py", ["--posture", os.path.join(work, "posture.json"), "--out-md", md,
                                                   "--out-html", ht])
        with open(md, encoding="utf-8") as f:
            m = f.read()
        self.assertIn("## Failed, unknown and passed-with-exceptions checks", m)
        row = next((ln for ln in m.splitlines() if "SEC-POSTURE-55" in ln), "")
        self.assertTrue(row.startswith("| pass (exceptions) |"), row)
        self.assertIn("i-0bad", row)

    def imds_nodes(self, read, optional=(), ids=("i-0aaa1111", "i-0bbb2222", "i-0ccc3333"), no_provider=False):
        # Linux EC2 nodes `ids`; instances.json holds only the ids in `read` (a failed by-id read leaves the
        # file in place); ids in `optional` allow IMDSv1; `no_provider` adds a node with no providerID.
        # Returns the IMDS checks of posture.json by id.
        work = self.build([n for n in self.PC["files"] if n != self.PC["denied_file"]])
        node0 = self.PC["files"]["nodes"]["items"][0]
        inst0 = self.PC["files"]["instances"]["Reservations"][0]["Instances"][0]
        nodes, insts = [], []
        for iid in ids:
            n = copy.deepcopy(node0)
            n["metadata"]["name"] = "node-" + iid
            n["spec"]["providerID"] = "aws:///us-west-2a/" + iid
            nodes.append(n)
            if iid in read:
                x = copy.deepcopy(inst0)
                x["InstanceId"] = iid
                x["MetadataOptions"] = {"HttpTokens": "optional" if iid in optional else "required",
                                        "HttpPutResponseHopLimit": 1, "HttpEndpoint": "enabled"}
                insts.append(x)
        if no_provider:
            n = copy.deepcopy(node0)
            n["metadata"]["name"] = "node-registering"
            del n["spec"]["providerID"]
            nodes.append(n)
        self.write(os.path.join("work", "posture", "nodes.json"), dict(self.PC["files"]["nodes"], items=nodes))
        self.write(os.path.join("work", "posture", "instances.json"), {"Reservations": [{"Instances": insts}]})
        q, doc = self.pipeline(work)
        return {c["id"]: c for c in doc["checks"] if c["id"] in ("SEC-POSTURE-46", "SEC-POSTURE-55")}

    def test_imds_unread_node_is_unknown_not_pass(self):
        # A1: every instance read passes, but one node's instance was not read
        for cid, c in self.imds_nodes(read=("i-0aaa1111", "i-0bbb2222")).items():
            self.assertEqual(c["result"], "unknown", c)
            self.assertIn("NOT READ", c["evidence"], cid)
            self.assertIn("i-0ccc3333", c["evidence"], cid)

    def test_imds_unread_node_named_when_a_read_node_fails(self):
        for cid, c in self.imds_nodes(read=("i-0aaa1111", "i-0bbb2222"), optional=("i-0bbb2222",)).items():
            self.assertEqual(c["result"], "fail", c)
            self.assertIn("i-0ccc3333", c["evidence"], cid)
            self.assertIn("failing: i-0bbb2222", c["evidence"], cid)

    def test_imds_every_node_read_scores_as_before(self):
        # negative control: no node unread, so nothing is named and the checks pass
        for cid, c in self.imds_nodes(read=("i-0aaa1111", "i-0bbb2222", "i-0ccc3333")).items():
            self.assertEqual(c["result"], "pass", c)
            self.assertNotIn("NOT READ", c["evidence"], cid)

    def test_imds_bucket_pass_with_unread_node_is_unknown(self):
        # 10 read, 1 of them failing (90%, the `all` bucket), 1 unread: still no pass
        ids = tuple("i-0%07d" % k for k in range(11))
        for cid, c in self.imds_nodes(read=ids[:10], optional=ids[:1], ids=ids).items():
            self.assertEqual(c["result"], "unknown", c)
            self.assertIn(ids[10], c["evidence"], cid)

    def test_imds_no_instance_read_names_the_nodes(self):
        for cid, c in self.imds_nodes(read=()).items():
            self.assertEqual(c["result"], "unknown", c)
            self.assertIn("NOT READ", c["evidence"], cid)
            self.assertIn("i-0ccc3333", c["evidence"], cid)
            self.assertNotIn("0/0", c["evidence"], cid)
            if cid == "SEC-POSTURE-55":
                self.assertIn("no Linux EC2 instance was read", c["evidence"])

    def test_imds_node_without_provider_id_scores(self):
        # a node registers before the cloud controller sets providerID; every token is still emitted
        checks = self.imds_nodes(read=("i-0aaa1111", "i-0bbb2222", "i-0ccc3333"), no_provider=True)
        self.assertEqual({c["result"] for c in checks.values()}, {"pass"}, checks)

    def test_sparse_workdir_score_null(self):
        q, doc = self.pipeline(self.build(self.PC["sparse_files"]))
        self.assertEqual(q.returncode, 3, q.stdout + q.stderr)
        self.check_shape(doc)
        self.assertFalse(doc["coverage"]["complete"])
        self.assertIsNone(doc["score"])
        md, ht = os.path.join(self.tmp, "p.md"), os.path.join(self.tmp, "p.html")
        rc, out, err = run_py("render_report.py", ["--posture", os.path.join(self.tmp, "work", "posture.json"),
                                                   "--out-md", md, "--out-html", ht])
        self.assertEqual(rc, 3, out + err)
        with open(md, encoding="utf-8") as f:
            self.assertIn("incomplete, no score", f.read())

    def test_reducer_refuses_unknown_and_duplicate_tokens(self):
        work = self.build(["cluster"])
        tok = {"pillar": "security", "id": "SEC-POSTURE-59", "track": "measured", "state": "all", "detail": "x"}
        for name, lines, code in (("dup", [tok, tok], "duplicate_id"),
                                  ("unk", [dict(tok, id="SEC-POSTURE-999")], "unknown_check"),
                                  ("bad", [dict(tok, state="great")], "bad_token")):
            with self.subTest(case=name):
                with open(os.path.join(work, "posture", "results-extra.jsonl"), "w", encoding="utf-8") as f:
                    f.write("".join(json.dumps(x) + "\n" for x in lines))
                q = subprocess.run(["bash", os.path.join(ASSETS, "posture_reduce.sh"), work], capture_output=True,
                                   text=True, timeout=60)
                self.assertEqual(q.returncode, 2, q.stdout + q.stderr)
                self.assertEqual(last_json(q.stdout)["code"], code)
                self.assertFalse(os.path.exists(os.path.join(work, "posture.json")))

    def test_score_refuses_bad_arguments(self):
        work = self.build(["cluster"])
        cases = (("posture_score.sh", "mistyped flag", [work, "--chek"]), ("posture_score.sh", "no workdir", []),
                 ("posture_score.sh", "empty workdir", [""]), ("posture_extra.sh", "no workdir", []),
                 ("posture_extra.sh", "empty workdir", [""]))
        for script, name, args in cases:
            with self.subTest(script=script, case=name):
                q = subprocess.run(["bash", os.path.join(ASSETS, script)] + args, capture_output=True,
                                   text=True, timeout=60, cwd=self.tmp)
                self.assertEqual(q.returncode, 2, q.stdout + q.stderr)
                self.assertIn("usage: %s <workdir>" % script, q.stderr)
                self.assertEqual(sorted(os.listdir(os.path.join(work, "posture"))), ["cluster.json"])
                self.assertEqual(os.listdir(self.tmp), ["work"])


# Partial reads: each case runs the real scorer, extra and reducer on the posture fixture with one read
# missing. A failed read gives unknown and names what was not read; a measured fail on what was read stands.
A, B = "i-0aaa1111", "i-0bbb2222"
ACCT = "111122223333"


@NEEDS_JQ
class PosturePartialRead(TmpCase):
    PC = CASES["posture"]
    build = PostureScoring.build
    pipeline = PostureScoring.pipeline

    def run_case(self, nodes_read, vols_read=None, sg_extra=False, addons=None, details=None,
                 webhooks=None, images=None, repos=None, open_on=B, unenc=(), auto_mode=False):
        work = self.build([n for n in self.PC["files"] if n != self.PC["denied_file"]])
        F = self.PC["files"]
        if auto_mode:
            cl = copy.deepcopy(F["cluster"])
            cl["cluster"]["computeConfig"] = {"enabled": True}
            self.write(os.path.join("work", "posture", "cluster.json"), cl)
        node0, inst0 = F["nodes"]["items"][0], F["instances"]["Reservations"][0]["Instances"][0]
        nodes, insts, vols = [], [], []
        for iid in (A, B):
            n = copy.deepcopy(node0)
            n["metadata"]["name"] = "node-" + iid
            n["spec"]["providerID"] = "aws:///us-west-2a/" + iid
            nodes.append(n)
            vid = "vol-0" + iid[3:] + "00000"
            if iid in nodes_read:
                x = copy.deepcopy(inst0)
                x["InstanceId"] = iid
                x["MetadataOptions"] = {"HttpTokens": "required", "HttpPutResponseHopLimit": 1, "HttpEndpoint": "enabled"}
                x["SecurityGroups"] = [{"GroupId": "sg-0open22" if iid == open_on else "sg-0node1"}]
                x["BlockDeviceMappings"] = [{"Ebs": {"VolumeId": vid}}]
                insts.append(x)
            if vols_read is None or iid in vols_read:
                vols.append({"VolumeId": vid, "Encrypted": iid not in unenc, "Attachments": [{"InstanceId": iid}]})
        self.write(os.path.join("work", "posture", "nodes.json"), dict(F["nodes"], items=nodes))
        self.write(os.path.join("work", "posture", "instances.json"), {"Reservations": [{"Instances": insts}]})
        self.write(os.path.join("work", "posture", "volumes.json"), {"Volumes": vols})
        sg = copy.deepcopy(F["sg"])
        if sg_extra:  # the open_on node's own launch-template SG: untagged, port 22 and 0.0.0.0/0
            sg["SecurityGroups"].append({"GroupId": "sg-0open22", "IpPermissions": [
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
                "IpPermissionsEgress": []})
        self.write(os.path.join("work", "posture", "sg.json"), sg)
        if addons is not None:
            self.write(os.path.join("work", "posture", "addons.json"), {"addons": addons, "addonDetails": details})
        if webhooks is not None:
            self.write(os.path.join("work", "posture", "validatingwebhooks.json"),
                       {"apiVersion": "v1", "kind": "List", "items": webhooks})
        if images is not None:
            pods = copy.deepcopy(F["pods"])
            p0 = pods["items"][0]
            pods["items"] = []
            for k, img in enumerate(images):
                p = copy.deepcopy(p0)
                p["metadata"]["name"] = "p%d" % k
                p["spec"]["containers"][0]["image"] = img
                pods["items"].append(p)
            self.write(os.path.join("work", "posture", "pods.json"), pods)
            self.write(os.path.join("work", "posture", "ecr.json"), {"repositories": repos})
        q, doc = self.pipeline(work)
        return {c["id"]: c for c in doc["checks"]}

    # sec-21 / SEC-POSTURE-18, a named volume not read: the by-id volume read failed (throttle, denial, volume deleted)
    def test_sec21_volume_unread_is_unknown(self):
        c = self.run_case(nodes_read=(A, B), vols_read=(A,))["SEC-POSTURE-18"]
        self.assertEqual(c["result"], "unknown", c)
        self.assertIn("vol-0bbb222200000", c["evidence"])

    # sec-21, a node's instance not read: its block devices are never asked for
    def test_sec21_instance_unread_is_unknown(self):
        c = self.run_case(nodes_read=(A,), vols_read=(A,))["SEC-POSTURE-18"]
        self.assertEqual(c["result"], "unknown", c)
        self.assertIn(B, c["evidence"])

    # A read node's volume is measurably unencrypted while node B is unread: the fail stands, B is named
    def test_sec21_measured_fail_with_unread_stays_fail(self):
        c = self.run_case(nodes_read=(A,), vols_read=(A,), unenc=(A,))["SEC-POSTURE-18"]
        self.assertEqual(c["result"], "fail", c)
        self.assertIn(B, c["evidence"])

    def test_sec21_full_read_passes(self):
        c = self.run_case(nodes_read=(A, B))["SEC-POSTURE-18"]
        self.assertEqual(c["result"], "pass", c)
        self.assertNotIn("NOT READ", c["evidence"])
        self.assertNotIn(self.SEC21_AUTO, c["evidence"])

    # sec-21, a volume nothing names: on an Auto Mode cluster EC2 can hide it from the volume list; the clause says so
    SEC21_AUTO = "not counted: a volume that EC2 hides from the volume list for this Region (managed resource visibility set to hidden) and that no PersistentVolume names and no node of this cluster has attached"

    def test_sec21_auto_mode_names_the_uncounted_volumes(self):
        c = self.run_case(nodes_read=(A, B), auto_mode=True)["SEC-POSTURE-18"]
        self.assertEqual(c["result"], "pass", c)
        self.assertIn(self.SEC21_AUTO, c["evidence"])

    # sec-30 / SEC-POSTURE-28 and net-2 / SEC-POSTURE-29: an unread node's untagged SG drops out of $lsg
    def test_sec30_net2_unread_node_is_unknown(self):
        cs = self.run_case(nodes_read=(A,), sg_extra=True)
        for cid in ("SEC-POSTURE-28", "SEC-POSTURE-29"):
            self.assertEqual(cs[cid]["result"], "unknown", cs[cid])
            self.assertIn(B, cs[cid]["evidence"], cid)

    # Read node A carries the open SG while node B is unread: the fail stands, B is named
    def test_sec30_net2_measured_fail_with_unread_stays_fail(self):
        cs = self.run_case(nodes_read=(A,), sg_extra=True, open_on=A)
        for cid in ("SEC-POSTURE-28", "SEC-POSTURE-29"):
            self.assertEqual(cs[cid]["result"], "fail", cs[cid])
            self.assertIn(B, cs[cid]["evidence"], cid)

    def test_sec30_net2_full_read_fails_on_the_open_sg(self):
        cs = self.run_case(nodes_read=(A, B), sg_extra=True)
        for cid in ("SEC-POSTURE-28", "SEC-POSTURE-29"):
            self.assertEqual(cs[cid]["result"], "fail", cs[cid])

    # sec-10 / SEC-POSTURE-33: a failed describe-addon leaves the add-on's own webhook counted as policy
    HOOK = [{"metadata": {"name": "acme-guard"}, "webhooks": [{"name": "v.acme.io",
             "clientConfig": {"service": {"namespace": "acme-system", "name": "acme"}},
             "rules": [{"apiGroups": [""], "resources": ["pods"], "operations": ["CREATE"], "scope": "*"}]}]}]

    def test_sec10_addon_unread_is_unknown(self):
        c = self.run_case(nodes_read=(A, B), addons=["vpc-cni", "acme-guard"],
                          details=[{"addonName": "vpc-cni"}], webhooks=self.HOOK)["SEC-POSTURE-33"]
        self.assertEqual(c["result"], "unknown", c)
        self.assertIn("acme-guard", c["evidence"])
        self.assertIn("NOT READ", c["evidence"])

    # An add-on name the collector does not describe (an AWS Marketplace name has an underscore) is not unread
    def test_sec10_marketplace_addon_name_is_not_unread(self):
        c = self.run_case(nodes_read=(A, B), addons=["vpc-cni", "acme_guard"],
                          details=[{"addonName": "vpc-cni"}], webhooks=self.HOOK)["SEC-POSTURE-33"]
        self.assertEqual(c["result"], "pass", c)
        self.assertNotIn("NOT READ", c["evidence"])

    def test_sec10_full_read_excludes_the_addon_webhook(self):
        c = self.run_case(nodes_read=(A, B), addons=["vpc-cni", "acme-guard"],
                          details=[{"addonName": "vpc-cni"},
                                   {"addonName": "acme-guard", "namespaceConfig": {"namespace": "acme-system"}}],
                          webhooks=self.HOOK)["SEC-POSTURE-33"]
        self.assertEqual(c["result"], "fail", c)

    # lens-13 / SEC-POSTURE-31: wording only; the result stays, the skipped count is named
    def test_lens13_names_the_skipped_images(self):
        c = self.run_case(nodes_read=(A, B), images=[
            ACCT + ".dkr.ecr.us-west-2.amazonaws.com/web:1",
            "602401143452.dkr.ecr.us-west-2.amazonaws.com/amazon-k8s-cni:v1",
            ACCT + ".dkr.ecr.eu-west-1.amazonaws.com/web:1"],
            repos=[{"repositoryName": "web", "imageTagMutability": "IMMUTABLE",
                    "repositoryUri": ACCT + ".dkr.ecr.us-west-2.amazonaws.com/web"}])["SEC-POSTURE-31"]
        self.assertEqual(c["result"], "pass", c)
        self.assertIn("not examined: 2 of the 3 distinct ECR repositories", c["evidence"])



if __name__ == "__main__":
    unittest.main()
