#!/usr/bin/env python3
"""Tests for misc/sync-classes.py, the class sync and its --check.

Every case lives in misc/tests/fixtures/sync_classes_cases.json. Each one
builds its own classes/ folder and member skills in a temp tree, so no case
reads or writes the real skills/. The failure cases follow the P-310 fixture
table (F1 to F17); F0, F5b and F11 are the passing controls.

Needs PyYAML (pip install 'pyyaml>=6,<7'). Run from the repo root:

    python3 -B misc/tests/test_sync_classes.py -v
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
SCRIPT = os.path.join(ROOT, "misc", "sync-classes.py")
UPDATE_PAGES = os.path.join(ROOT, "misc", "update-pages.sh")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "class-sync.yml")
FIXTURES = os.path.join(ROOT, "misc", "tests", "fixtures", "sync_classes_cases.json")

with open(FIXTURES, encoding="utf-8") as _fh:
    DATA = json.load(_fh)

# The sketch's fixture ids; each must have at least one case.
SKETCH_IDS = ["F0", "F1", "F2", "F3a", "F3b", "F4", "F5", "F5b", "F6", "F7", "F8",
              "F9", "F10", "F11", "F15", "F16", "F17"]


def write_file(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def remove(root, rel):
    path = os.path.join(root, rel)
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def snapshot(root):
    out = {}
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, root)] = (fh.read(), os.stat(full).st_mode)
    return out


def run_sync(root, mode):
    args = [sys.executable, "-B", SCRIPT, "--root", root]
    if mode == "check":
        args.append("--check")
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


class SyncCase(unittest.TestCase):
    maxDiff = None

    def build(self, case):
        tmp = tempfile.mkdtemp(prefix="sync-classes-test-")
        self.addCleanup(shutil.rmtree, tmp)
        base = DATA["bases"][case["base"]]
        for rel, text in base["files"].items():
            write_file(tmp, rel, text)
        for rel in base.get("executable", []):
            os.chmod(os.path.join(tmp, rel), 0o755)
        for rel, text in case.get("files", {}).items():
            if text is None:
                remove(tmp, rel)
            else:
                write_file(tmp, rel, text)
        return tmp, base

    def mutate(self, tmp, steps):
        for step in steps:
            path = os.path.join(tmp, step["path"])
            if step.get("delete"):
                remove(tmp, step["path"])
            elif "write" in step:
                write_file(tmp, step["path"], step["write"])
            elif "append" in step:
                with open(path, "a", encoding="utf-8", newline="") as fh:
                    fh.write(step["append"])
            elif "replace" in step:
                old, new = step["replace"]
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                self.assertIn(old, text, f"fixture mutation target not found in {step['path']}")
                write_file(tmp, step["path"], text.replace(old, new, 1))
            elif "chmod" in step:
                os.chmod(path, int(step["chmod"], 8))
            else:
                self.fail(f"unknown mutation {step}")

    def run_case(self, case):
        tmp, base = self.build(case)
        if case.get("presync"):
            rc, out = run_sync(tmp, "write")
            self.assertEqual(rc, 0, f"presync failed:\n{out}")
        self.mutate(tmp, case.get("mutate", []))
        before = snapshot(tmp)
        exp = case["expect"]
        for mode in case["run"]:
            rc, out = run_sync(tmp, mode)
            self.assertEqual(rc, exp["rc"], f"{mode} run exit code; output:\n{out}")
            for want in exp.get("output", []):
                self.assertIn(want, out, f"{mode} run output")
        if exp.get("unchanged"):
            self.assertEqual(snapshot(tmp), before, "the tree changed")
        for rel, wants in exp.get("files", {}).items():
            with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                text = fh.read()
            for want in wants:
                self.assertIn(want, text, rel)
        for rel in exp.get("absent", []):
            self.assertFalse(os.path.exists(os.path.join(tmp, rel)), f"{rel} should not exist")
        for rel in exp.get("same_as_base", []):
            with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), base["files"][rel], rel)
        for rel in exp.get("executable", []):
            self.assertTrue(os.stat(os.path.join(tmp, rel)).st_mode & 0o100, f"{rel} not executable")
        if "order" in exp:
            with open(os.path.join(tmp, exp["order"]["path"]), encoding="utf-8") as fh:
                text = fh.read()
            at = [text.find(item) for item in exp["order"]["items"]]
            self.assertNotIn(-1, at, f"an ordered item is missing: {exp['order']['items']}")
            self.assertEqual(at, sorted(at), "items out of order")
        if "count" in exp:
            with open(os.path.join(tmp, exp["count"]["path"]), encoding="utf-8") as fh:
                self.assertEqual(fh.read().count(exp["count"]["text"]), exp["count"]["n"])

    def run_update_pages(self, case):
        # A tiny git tree holding only update-pages.sh and one skill that has
        # no SKILL_META line: --check must stop on it.
        tmp = tempfile.mkdtemp(prefix="sync-classes-pages-")
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, "misc"))
        shutil.copy2(UPDATE_PAGES, os.path.join(tmp, "misc", "update-pages.sh"))
        skill = case["skill"]
        write_file(tmp, f"skills/{skill}/SKILL.md",
                   f"---\nname: {skill}\ndescription: \"A skill with no SKILL_META line.\"\n---\n\n# New\n")
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        for cmd in (["git", "init", "-q"],
                    ["git", "add", "misc/update-pages.sh", f"skills/{skill}/SKILL.md"]):
            subprocess.run(cmd, cwd=tmp, check=True, env=env)
        p = subprocess.run(["bash", "misc/update-pages.sh", "--check"], cwd=tmp,
                           capture_output=True, text=True, timeout=120, env=env)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, case["expect"]["rc"], out)
        for want in case["expect"]["output"]:
            self.assertIn(want, out)


def _make(case):
    def test(self):
        if case.get("kind") == "update-pages":
            self.run_update_pages(case)
        else:
            self.run_case(case)
    test.__doc__ = f"{case['id']}: {case['about']}"
    return test


for _case in DATA["cases"]:
    setattr(SyncCase, "test_" + _case["id"].replace("-", "_"), _make(_case))


class Coverage(unittest.TestCase):
    def test_every_sketch_fixture_has_a_case(self):
        ids = [c["id"] for c in DATA["cases"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate case id")
        for want in SKETCH_IDS:
            self.assertTrue(any(i == want or i.startswith(want + "-") for i in ids), want)

    def test_workflow_runs_the_three_checks(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            text = fh.read()
        for line in ("python3 -B misc/tests/test_sync_classes.py -v",
                     "python3 misc/sync-classes.py --check",
                     "./misc/update-pages.sh --check"):
            self.assertIn(line, text)


if __name__ == "__main__":
    unittest.main()
