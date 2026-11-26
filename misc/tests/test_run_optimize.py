#!/usr/bin/env python3
"""Offline tests for misc/evals/scripts/run_optimize.py. No model call: the
improve_description.py and run_triggering.py subprocesses are stubbed.

Run directly with:

    python3 -B misc/tests/test_run_optimize.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MISC_DIR, "evals", "scripts"))

import run_optimize  # noqa: E402

SKILL = "eks-recon"


def fake_results(skill: str) -> dict:
    """A run_triggering.py-shaped output where every case fails."""
    cases = json.loads((run_optimize.EVALS_ROOT / skill / "triggering.json").read_text())
    rows = [{"query": c["query"], "should_trigger": c["should_trigger"], "pass": False,
             "triggers": 0 if c["should_trigger"] else 3, "runs": 3,
             "trigger_rate": 0.0 if c["should_trigger"] else 1.0, "run_records": [{}],
             "fail_reason": "trigger rate below threshold" if c["should_trigger"]
             else "trigger rate at or above threshold"}
            for c in cases]
    return {"skill_name": skill, "description": "old", "results": rows,
            "summary": {"passed": 0, "failed": len(rows), "total": len(rows)}}


def run_main(tmp: str, raw: dict, *extra: str) -> tuple[int, Path]:
    res, out = Path(tmp, "r.json"), Path(tmp, "o.json")
    res.write_text(json.dumps(raw))
    return run_optimize.main(["--skill", SKILL, "--results", str(res), "--out", str(out), *extra]), out


class TestRunOptimize(unittest.TestCase):
    def test_owned_negative_is_labelled(self):
        rows = [{"query": "q1", "should_trigger": False, "pass": False, "triggers": 2, "runs": 3},
                {"query": "q2", "should_trigger": True, "pass": False, "triggers": 0, "runs": 3},
                {"query": "q3", "should_trigger": False, "pass": True, "triggers": 0, "runs": 3}]
        out = run_optimize.build_eval_results(rows, "d", {"q1": "eks-design", "q3": "other"})
        self.assertEqual(out["results"][0]["query"], "q1 [owned by sibling `eks-design`]")
        self.assertEqual(out["results"][1]["query"], "q2")
        self.assertEqual(out["results"][2]["query"], "q3 [no sibling, out of scope]")
        self.assertEqual(out["summary"], {"passed": 1, "failed": 2, "total": 3})
        self.assertEqual(set(out), {"description", "results", "summary"})

    def test_rows_with_no_valid_run_are_dropped(self):
        raw = {"results": [
            {"query": "a", "runs": 0, "fail_reason": "no valid run"},
            {"query": "b", "runs": 3, "fail_reason": "shared negative with invalid runs"},
            {"query": "c", "runs": 3, "fail_reason": None},
            {"query": "d", "runs": 3, "fail_reason": "trigger rate below threshold"}]}
        rows, dropped = run_optimize.valid_rows(raw)
        self.assertEqual([r["query"] for r in rows], ["c", "d"])
        self.assertEqual(dropped, 2)

    def test_sibling_map_attributes_real_negatives(self):
        owners = run_optimize.sibling_owners(SKILL)
        self.assertIn("eks-best-practices", owners.values())

    def test_build_only_writes_file_and_calls_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run_optimize.subprocess, "run") as run:
            rc, out = run_main(tmp, fake_results(SKILL), "--build-only")
            self.assertEqual(rc, 0)
            run.assert_not_called()
            data = json.loads(out.read_text())
            self.assertTrue(any("owned by sibling" in r["query"] for r in data["results"]))
            self.assertEqual(set(data["results"][0]), set(run_optimize.ROW_KEYS))

    def test_other_skills_results_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _ = run_main(tmp, dict(fake_results(SKILL), skill_name="eks-design"), "--build-only")
            self.assertEqual(rc, 1)

    def test_proposal_is_validated_on_a_staged_copy(self):
        seen = {}

        def fake_run(cmd, **kw):
            if "scripts.improve_description" in cmd:
                seen["improve"] = (cmd, kw)
                return mock.Mock(returncode=0, stdout=json.dumps({"description": "NEW: desc"}))
            skill_path = Path(cmd[cmd.index("--skill-path") + 1])
            seen["staged_md"] = (skill_path / "SKILL.md").read_text()
            seen["staged_parent"] = skill_path.parent.name
            return mock.Mock(returncode=0, stdout=json.dumps({"summary": {"passed": 5, "total": 9}}))

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run_optimize.subprocess, "run", side_effect=fake_run), \
                mock.patch("sys.stdout") as stdout:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                res = Path("r.json")
                res.write_text(json.dumps(fake_results(SKILL)))
                rc = run_optimize.main(["--skill", SKILL, "--results", "r.json",
                                        "--out", "rel.json", "--model", "m"])
            finally:
                os.chdir(old)
            printed = "".join(c.args[0] for c in stdout.write.call_args_list)
            cmd, kw = seen["improve"]
            self.assertEqual(rc, 0)
            self.assertTrue(Path(cmd[cmd.index("--eval-results") + 1]).is_absolute())
            self.assertEqual(kw["cwd"], run_optimize.SKILL_CREATOR)
            self.assertIn('description: "NEW: desc"', seen["staged_md"])
            self.assertEqual(seen["staged_parent"], "skills")
            self.assertEqual(json.loads(printed)["validation"], {"passed": 5, "total": 9})
            self.assertTrue(Path(tmp, "rel.validation.json").exists())

    def test_description_rewrite_keeps_the_rest(self):
        md = "---\nname: x\ndescription: old\n  more\nmetadata: {}\n---\n\n# Body\n"
        self.assertEqual(run_optimize.with_description(md, 'a "b"'),
                         '---\nname: x\ndescription: "a \\"b\\""\nmetadata: {}\n---\n\n# Body\n')

    def test_row_with_no_valid_run_never_reaches_the_improver(self):
        raw = fake_results(SKILL)
        raw["results"][0].update(query="ZERO RUN ROW", runs=0, triggers=0, fail_reason="no valid run")
        seen = {}

        def fake_run(cmd, **kw):
            if "scripts.improve_description" in cmd:
                data = json.loads(Path(cmd[cmd.index("--eval-results") + 1]).read_text())
                seen["queries"] = [r["query"] for r in data["results"]]
                return mock.Mock(returncode=0, stdout=json.dumps({"description": "new"}))
            return mock.Mock(returncode=0, stdout=json.dumps({"summary": {}}))

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run_optimize.subprocess, "run", side_effect=fake_run), \
                mock.patch("sys.stdout"):
            rc, _ = run_main(tmp, raw, "--model", "m")
        self.assertEqual(rc, 0)
        self.assertEqual(len(seen["queries"]), len(raw["results"]) - 1)
        self.assertFalse(any("ZERO RUN ROW" in q for q in seen["queries"]))

    def test_validate_removes_its_staged_copy(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen["staged"] = Path(cmd[cmd.index("--skill-path") + 1])
            seen["existed"] = (seen["staged"] / "SKILL.md").exists()
            return mock.Mock(returncode=0, stdout="{}")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(tempfile, "tempdir", tmp), \
                mock.patch.object(run_optimize.subprocess, "run", side_effect=fake_run):
            run_optimize.validate(SKILL, run_optimize.REPO_ROOT / "skills" / SKILL, "new", "m")
            self.assertTrue(seen["existed"])
            self.assertTrue(str(seen["staged"]).startswith(tmp))
            self.assertEqual(list(Path(tmp).glob("optimize-*")), [])

    def test_proposal_is_kept_when_validation_fails(self):
        def fake_run(cmd, **kw):
            if "scripts.improve_description" in cmd:
                return mock.Mock(returncode=0, stdout=json.dumps({"description": "KEPT PROPOSAL"}))
            return mock.Mock(returncode=2, stdout="")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run_optimize.subprocess, "run", side_effect=fake_run):
            rc, out = run_main(tmp, fake_results(SKILL), "--model", "m")
            proposal = out.with_name(out.stem + ".proposal.json")
            self.assertEqual(rc, 2)
            self.assertTrue(proposal.exists())
            self.assertEqual(json.loads(proposal.read_text())["description"], "KEPT PROPOSAL")

    def test_no_valid_rows_left_is_refused_before_the_improver(self):
        raw = fake_results(SKILL)
        for r in raw["results"]:
            r.update(runs=0, triggers=0, fail_reason="no valid run")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run_optimize.subprocess, "run") as run:
            rc, out = run_main(tmp, raw, "--model", "m")
            self.assertEqual(rc, 1)
            run.assert_not_called()
            self.assertFalse(out.exists())

    def test_missing_model_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _ = run_main(tmp, fake_results(SKILL))
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
