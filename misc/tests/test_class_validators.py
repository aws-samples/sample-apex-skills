#!/usr/bin/env python3
"""Offline tests for the class validators (step 3.4a).

Covers classes/apex-base/scripts/schema_check.py and validate_input.py,
classes/script/scripts/validate_output.py and k_run_diff.py, and
classes/operator/scripts/run_artifact_checks.py, run as a skill runs them,
on the eks-recon schemas in skills/eks-recon/assets/. The done test: the
validators pass on eks-recon fixtures and fail on a broken one (V1).

Needs jsonschema and PyYAML (pip install 'jsonschema[format-nongpl]>=4.26,<5'
'pyyaml>=6,<7'); no network, no cluster. Cases come
from misc/tests/fixtures/class_validators_cases.json. Run from the repo root:
  python3 -B misc/tests/test_class_validators.py -v
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "classes", "apex-base", "scripts")
SCRIPT = os.path.join(ROOT, "classes", "script", "scripts")
OPERATOR = os.path.join(ROOT, "classes", "operator", "scripts")
RECON = os.path.join(ROOT, "skills", "eks-recon")
OUT_SCHEMA = os.path.join(RECON, "assets", "recon-output.schema.json")
with open(os.path.join(ROOT, "misc", "tests", "fixtures", "class_validators_cases.json"), encoding="utf-8") as _f:
    CASES = json.load(_f)
sys.path.insert(0, BASE)

import schema_check  # noqa: E402


def run(tool, args, path_env=None):
    """Run a class tool as a script; return (rc, stdout + stderr)."""
    env = dict(os.environ, PYTHONPATH=BASE)
    if path_env is not None:
        env["PATH"] = path_env
    p = subprocess.run([sys.executable, "-B", tool] + list(args), capture_output=True,
                       text=True, timeout=120, cwd=ROOT, env=env)
    return p.returncode, p.stdout + p.stderr


def mutate(doc, mutations):
    doc = copy.deepcopy(doc)
    for m in mutations:
        *parents, last = m["path"].split(".")
        node = doc
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        if isinstance(node, list):
            last = int(last)
        if m["op"] == "delete":
            del node[last]
        else:
            node[last] = m["value"]
    return doc


def output_case(case):
    """The YAML text of one output case."""
    doc = CASES["recon_report"]
    if "keep_only" in case:
        doc = {k: doc[k] for k in case["keep_only"]}
    text = yaml.safe_dump(mutate(doc, case.get("mutations", [])), sort_keys=False)
    if "yaml_replace" in case:
        old, new = case["yaml_replace"]
        assert old in text, old
        text = text.replace(old, new)
    return text


OUTPUTS = {c["id"]: c for c in CASES["output_cases"]}


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="class-validators-")
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def skill(self, name, front):
        """A minimal skill folder with the eks-recon schemas in assets/."""
        d = os.path.join(self.tmp, name)
        shutil.copytree(os.path.join(RECON, "assets"), os.path.join(d, "assets"))
        self.write(f"{name}/SKILL.md", "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n# x\n")
        return d

    def expect(self, case, rc, out):
        self.assertEqual(rc, case["expect"], f"{case['id']} ({case.get('what', '')}):\n{out}")
        if "message" in case:
            self.assertIn(case["message"], out, case["id"])


class OutputValidator(Tmp):
    """Piece 3: validate_output.py on eks-recon YAML, the schema found from SKILL.md."""

    def test_output_cases(self):
        for case in CASES["output_cases"]:
            with self.subTest(case["id"]):
                f = self.write(f"{case['id']}.yaml", output_case(case))
                rc, out = run(os.path.join(SCRIPT, "validate_output.py"), ["--skill-dir", RECON, f])
                self.expect(case, rc, out)

    def test_done_test_broken_fixture_fails(self):
        good = self.write("good.yaml", output_case(OUTPUTS["V0"]))
        bad = self.write("bad.yaml", output_case(OUTPUTS["V1"]))
        self.assertEqual(run(os.path.join(SCRIPT, "validate_output.py"), ["--skill-dir", RECON, good])[0], 0)
        self.assertEqual(run(os.path.join(SCRIPT, "validate_output.py"), ["--skill-dir", RECON, bad])[0], 1)

    def test_unreadable_outputs(self):
        for case in CASES["unreadable_outputs"]:
            with self.subTest(case["id"]):
                f = self.write(f"{case['id']}.yaml", case["text"])
                self.expect(case, *run(os.path.join(SCRIPT, "validate_output.py"), ["--skill-dir", RECON, f]))

    def test_handwritten_outputs(self):
        for case in CASES["handwritten_outputs"]:
            with self.subTest(case["id"]):
                f = self.write(f"{case['id']}.yaml", case["text"])
                self.expect(case, *run(os.path.join(SCRIPT, "validate_output.py"), ["--skill-dir", RECON, f]))

    def test_missing_inputs_never_pass(self):
        good = self.write("good.yaml", output_case(OUTPUTS["V0"]))
        cases = [
            ["--schema", os.path.join(self.tmp, "absent.schema.json"), good],
            ["--skill-dir", RECON, os.path.join(self.tmp, "absent.yaml")],
            ["--skill-dir", RECON],
            [good],  # no skill folder found next to the repo copy
        ]
        for args in cases:
            with self.subTest(args):
                self.assertEqual(run(os.path.join(SCRIPT, "validate_output.py"), args)[0], 2)

    def test_declared_path_must_stay_in_assets(self):
        d = self.skill("escape", {"name": "escape", "description": "x",
                                  "metadata": {"apex-outputs": "../eks-recon/assets/recon-output.schema.json"}})
        good = self.write("good.yaml", output_case(OUTPUTS["V0"]))
        rc, out = run(os.path.join(SCRIPT, "validate_output.py"), ["--skill-dir", d, good])
        self.assertEqual(rc, 2, out)
        self.assertIn("inside the skill's assets/", out)

    def test_copied_tool_finds_its_skill(self):
        """A copied tool in <skill>/scripts/, no --skill-dir: under source names; the flat names and the import rewrite are P-310's."""
        d = self.skill("copied", {"name": "copied", "description": "x",
                                  "metadata": {"apex-outputs": "assets/recon-output.schema.json"}})
        os.makedirs(os.path.join(d, "scripts"))
        for src in (os.path.join(BASE, "schema_check.py"), os.path.join(SCRIPT, "validate_output.py")):
            shutil.copy(src, os.path.join(d, "scripts"))
        good = self.write("good.yaml", output_case(OUTPUTS["V0"]))
        bad = self.write("bad.yaml", output_case(OUTPUTS["V1"]))
        tool = os.path.join(d, "scripts", "validate_output.py")
        self.assertEqual(run(tool, [good])[0], 0)
        self.assertEqual(run(tool, [bad])[0], 1)


class InputValidator(Tmp):
    """Piece 5, apex-base half: validate_input.py on eks-recon inputs."""

    def test_input_cases_inline(self):
        for case in CASES["input_cases"]:
            with self.subTest(case["id"]):
                rc, out = run(os.path.join(BASE, "validate_input.py"),
                              ["--skill-dir", RECON, "--json", json.dumps(case["input"])])
                self.expect(case, rc, out)

    def test_input_cases_from_file(self):
        for case in CASES["input_cases"]:
            with self.subTest(case["id"]):
                f = self.write(f"{case['id']}.json", json.dumps(case["input"]))
                self.expect(case, *run(os.path.join(BASE, "validate_input.py"), ["--skill-dir", RECON, f]))

    def test_bad_inline_json_cannot_check(self):
        rc, out = run(os.path.join(BASE, "validate_input.py"), ["--skill-dir", RECON, "--json", "{cluster"])
        self.assertEqual(rc, 2, out)
        self.assertIn("not valid JSON", out)

    def test_undeclared_input_schema_cannot_check(self):
        d = self.skill("noinputs", {"name": "noinputs", "description": "x"})
        rc, out = run(os.path.join(BASE, "validate_input.py"), ["--skill-dir", d, "--json", "{}"])
        self.assertEqual(rc, 2, out)
        self.assertIn("metadata.apex-inputs is not declared", out)


class KRunDiff(Tmp):
    """The Script class's k-run diff with eks-recon's same-answer rule."""

    def test_krun_cases(self):
        rule = os.path.join(RECON, "assets", "same-answer.yaml")
        for case in CASES["krun_cases"]:
            with self.subTest(case["id"]):
                files = []
                for i, muts in enumerate(case["runs"]):
                    doc = mutate(CASES["recon_report"], muts)
                    files.append(self.write(f"{case['id']}/run{i}.yaml", yaml.safe_dump(doc)))
                args = ["--skill-dir", RECON] if case.get("use_skill_rule") else \
                    ["--same-answer", rule, "--k", str(case["k"])]
                self.expect(case, *run(os.path.join(SCRIPT, "k_run_diff.py"), args + files))

    def test_same_file_twice_cannot_check(self):
        f = self.write("run.yaml", yaml.safe_dump(CASES["recon_report"]))
        rc, out = run(os.path.join(SCRIPT, "k_run_diff.py"),
                      ["--skill-dir", RECON, "--k", "2", f, f])
        self.assertEqual(rc, 2, out)
        self.assertIn("given twice", out)

    def test_rule_file_shape(self):
        rule = schema_check.load(os.path.join(RECON, "assets", "same-answer.yaml"))
        self.assertEqual(rule["k"], 10)  # STEP3-PLAN: 10 runs on one cluster
        for path in rule["ignore"]:
            parts = path.replace("[]", "").split(".")
            self.assertIn(parts[0], schema_check.load(OUT_SCHEMA)["properties"], path)


class ArtifactChecks(Tmp):
    """The Operator class's declared artifact checks on fixture artifacts."""

    def fake_bin(self, tools):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir, exist_ok=True)
        for name, mode in tools.items():
            if mode == "validate":  # init passes, validate fails
                body = 'case "$1" in validate) echo "Error: bad block"; exit 1;; esac\nexit 0\n'
            else:
                body = f'echo "{name} $*"\nexit {mode}\n'
            path = self.write(f"bin/{name}", "#!/bin/sh\n" + body)
            os.chmod(path, 0o755)
        return bindir

    def test_artifact_cases(self):
        for case in CASES["artifact_cases"]:
            with self.subTest(case["id"]):
                front = {"name": case["id"], "description": "x",
                         "metadata": {"apex-outputs": "assets/recon-output.schema.json"}}
                if case.get("declared") is not None:
                    front["metadata"]["apex-artifact-checks"] = case["declared"]
                d = self.skill(case["id"], front)
                if case["artifact"] == "tf":
                    artifact = os.path.dirname(self.write(f"{case['id']}-tf/main.tf", 'terraform {}\n'))
                else:
                    artifact = self.write(f"{case['id']}.yaml", output_case(OUTPUTS[case["artifact"]]))
                args = ["--skill-dir", d, artifact]
                path_env = self.fake_bin(case["fake_tools"]) if "fake_tools" in case else None
                self.expect(case, *run(os.path.join(OPERATOR, "run_artifact_checks.py"), args, path_env))


class SchemaChecker(Tmp):
    """schema_check.py: every skill schema in the repo is valid Draft 2020-12."""

    def test_every_skill_schema_is_valid(self):
        found = []
        for name in sorted(os.listdir(os.path.join(ROOT, "skills"))):
            assets = os.path.join(ROOT, "skills", name, "assets")
            if os.path.isdir(assets):
                found += [os.path.join(assets, f) for f in sorted(os.listdir(assets)) if f.endswith(".schema.json")]
        self.assertTrue(found)
        rc, out = run(os.path.join(BASE, "schema_check.py"), ["--check-schema"] + found)
        self.assertEqual(rc, 0, out)


class ReconSchemaMatchesSkill(unittest.TestCase):
    """The hand-written schema stays in step with SKILL.md."""

    def setUp(self):
        with open(OUT_SCHEMA, encoding="utf-8") as f:
            self.schema = json.load(f)
        with open(os.path.join(RECON, "SKILL.md"), encoding="utf-8") as f:
            self.skill = f.read()

    def test_frontmatter_declares_the_schemas(self):
        meta = schema_check.skill_metadata(RECON)
        self.assertEqual(schema_check.declared_schema(RECON, "apex-outputs"), os.path.realpath(OUT_SCHEMA))
        self.assertTrue(os.path.isfile(schema_check.declared_schema(RECON, "apex-inputs")))
        self.assertNotIn("apex-classes", meta)  # class membership is P-310's sync, not this row

    def test_schema_revision_matches_skill_md(self):
        revs = set(re.findall(r'schema_revision: "([^"]+)"', self.skill))
        self.assertEqual(len(revs), 1, revs)
        want = self.schema["properties"]["report"]["properties"]["schema_revision"]["const"]
        self.assertEqual(revs, {want}, "bump the schema's schema_revision and $id with SKILL.md's")
        self.assertTrue(self.schema["$id"].endswith(want))


if __name__ == "__main__":
    unittest.main()
