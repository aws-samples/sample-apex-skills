#!/usr/bin/env python3
"""Tests for classes/apex-base/scripts/report.py, the shared report tool.

Every case lives in misc/tests/fixtures/report_tool_cases.json:
- normal: each skill's normal report is byte-identical to that skill's own
  report tool's output (the fixture's _about names where each came from);
- hostile: the hostile-input suite (markup in link text and in the href,
  javascript: and mixed-case schemes, C0 control characters except tab, LF
  and CR, DEL and C1 characters, placeholder-shaped strings), plus the
  masking line passing through as written;
- errors: each error exits 2 with one stderr line and no traceback, and
  writes nothing;
- gate: eks-security below its coverage gate writes both pages, exit 3;
- class copy: misc/sync-classes.py copies the tool into a member skill of
  a temp tree (needs PyYAML, skipped without it), and the copy writes the
  same page.

Every case runs the shared tool (or its class copy) only, in its own temp
dir. Stdlib only, apart from the class copy case. Run from the repo root:

    python3 -B misc/tests/test_report_tool.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, "classes", "apex-base", "scripts", "report.py")
FIXTURES = os.path.join(ROOT, "misc", "tests", "fixtures", "report_tool_cases.json")

with open(FIXTURES, encoding="utf-8") as _fh:
    DATA = json.load(_fh)
NORMAL = {c["id"]: c for c in DATA["normal"]}


def write_file(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def read_file(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def run_tool(args, cwd):
    return subprocess.run([sys.executable, "-B", "-I", TOOL] + args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def set_path(doc, path, value):
    for key in path[:-1]:
        doc = doc[key]
    doc[path[-1]] = value


class Normal(unittest.TestCase):
    def test_byte_identical(self):
        for case in DATA["normal"]:
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as d:
                inputs = []
                for name, text in case["inputs"].items():
                    write_file(os.path.join(d, name), text)
                    inputs.append(os.path.join(d, name))
                outs = []
                for name in case["outputs"]:
                    outs += ["--out", os.path.join(d, "out-" + name)]
                r = run_tool([case["template"]] + inputs + outs, d)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout + r.stderr, "")
                for name, want in case["outputs"].items():
                    path = os.path.join(d, "out-" + name)
                    with open(path, "rb") as fh:
                        got = fh.read()
                    self.assertEqual(got, want.encode("utf-8"), name)
                    self.assertEqual(os.stat(path).st_mode & 0o777, 0o600, name)


class Hostile(unittest.TestCase):
    def pages(self, case, template, d):
        if template == "eks-security":
            base = NORMAL["sec-1"]["inputs"]
            findings = json.loads(base["sec-1-findings.json"])
            for path in DATA["sec_fields"]:
                set_path(findings, path, case["value"])
            write_file(os.path.join(d, "f.json"), json.dumps(findings))
            write_file(os.path.join(d, "i.json"), base["sec-1-inventory.json"])
            args = [template, os.path.join(d, "f.json"), os.path.join(d, "i.json"),
                    "--out", os.path.join(d, "o.md"), "--out", os.path.join(d, "o.html")]
            names = {".md": "o.md", ".html": "o.html"}
        else:
            write_file(os.path.join(d, "in.md"), case["input"])
            args = [template, os.path.join(d, "in.md"), "--out", os.path.join(d, "o.html")]
            names = {".html": "o.html"}
        r = run_tool(args, d)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {suffix: read_file(os.path.join(d, name)) for suffix, name in names.items()}

    def test_cases(self):
        for case in DATA["hostile"]:
            for template in case["templates"]:
                with self.subTest(case=case["id"], template=template), tempfile.TemporaryDirectory() as d:
                    pages = self.pages(case, template, d)
                    contains = case["contains"]
                    if isinstance(contains, list):
                        contains = {".html": contains}
                    for suffix, wants in contains.items():
                        for want in wants:
                            self.assertIn(want, pages[suffix])
                    for page in pages.values():
                        for bad in case["absent"]:
                            self.assertNotIn(bad, page)


class Errors(unittest.TestCase):
    def test_cases(self):
        for case in DATA["errors"]:
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as d:
                for name, spec in case["files"].items():
                    path = os.path.join(d, name)
                    if spec.get("dir"):
                        os.mkdir(path)
                    elif "symlink" in spec:
                        os.symlink(spec["symlink"], path)
                    elif "hex" in spec:
                        with open(path, "wb") as fh:
                            fh.write(bytes.fromhex(spec["hex"]))
                    else:
                        write_file(path, spec["text"])
                before = {n: read_file(os.path.join(d, n)) for n, s in case["files"].items() if "text" in s}
                r = run_tool([a.replace("{d}", d) for a in case["args"]], d)
                self.assertEqual(r.returncode, case["rc"], r.stderr)
                self.assertEqual(r.stdout, "")
                lines = r.stderr.splitlines()
                self.assertEqual(len(lines), 1, r.stderr)
                self.assertIn(case["stderr"], lines[0])
                self.assertNotIn("Traceback", r.stderr)
                for name in case["absent"]:
                    self.assertFalse(os.path.lexists(os.path.join(d, name)), name)
                for name, text in before.items():
                    self.assertEqual(read_file(os.path.join(d, name)), text, name)


class Gate(unittest.TestCase):
    def test_below_gate_exits_3(self):
        gate = DATA["gate"]
        base = NORMAL[gate["base"]]["inputs"]
        findings = json.loads(base["sec-1-findings.json"])
        path, value = gate["set"]
        set_path(findings, path, value)
        with tempfile.TemporaryDirectory() as d:
            write_file(os.path.join(d, "f.json"), json.dumps(findings))
            write_file(os.path.join(d, "i.json"), base["sec-1-inventory.json"])
            r = run_tool(["eks-security", os.path.join(d, "f.json"), os.path.join(d, "i.json"),
                          "--out", os.path.join(d, "o.md"), "--out", os.path.join(d, "o.html")], d)
            self.assertEqual(r.returncode, gate["rc"], r.stderr)
            self.assertIn("Overall verdict: Incomplete.", read_file(os.path.join(d, "o.md")))
            self.assertTrue(os.path.exists(os.path.join(d, "o.html")))


class ClassCopy(unittest.TestCase):
    """The class sync copies the tool into a member skill, and the copy writes the same page."""

    def test_member_copy(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML is not installed (pip install 'pyyaml>=6,<7'); CI installs it")
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(os.path.join(ROOT, "classes", "apex-base"), os.path.join(d, "classes", "apex-base"))
            os.makedirs(os.path.join(d, "skills", "demo"))
            write_file(os.path.join(d, "skills", "demo", "SKILL.md"),
                       "---\nname: demo\ndescription: Demo member skill.\nmetadata:\n  apex-classes: \"apex-base\"\n---\n\n# Demo\n")
            sync = os.path.join(ROOT, "misc", "sync-classes.py")
            for mode in ([], ["--check"]):
                r = subprocess.run([sys.executable, "-B", sync, "--root", d] + mode, capture_output=True, text=True,
                                   timeout=120)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            copy = os.path.join(d, "skills", "demo", "scripts", "apex_base_report.py")
            case = NORMAL["ecs-1-full"]
            write_file(os.path.join(d, "in.md"), case["inputs"]["ecs-1-full.md"])
            r = subprocess.run([sys.executable, "-B", "-I", copy, case["template"], os.path.join(d, "in.md"),
                                "--out", os.path.join(d, "o.html")], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(read_file(os.path.join(d, "o.html")), case["outputs"]["ecs-1-full.html"])


if __name__ == "__main__":
    unittest.main()
