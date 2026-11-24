#!/usr/bin/env python3
"""Offline tests for misc/evals/scripts/run_optimize.py. No model call: the
improve_description.py subprocess is stubbed.

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
             "trigger_rate": 0.0 if c["should_trigger"] else 1.0, "run_records": [{}]}
            for c in cases]
    return {"skill_name": skill, "description": "old", "results": rows,
            "summary": {"passed": 0, "failed": len(rows), "total": len(rows)}}


class TestRunOptimize(unittest.TestCase):
    def test_owned_negative_is_labelled(self):
        raw = {"description": "d", "results": [
            {"query": "q1", "should_trigger": False, "pass": False, "triggers": 2, "runs": 3},
            {"query": "q2", "should_trigger": True, "pass": False, "triggers": 0, "runs": 3},
            {"query": "q3", "should_trigger": False, "pass": True, "triggers": 0, "runs": 3}]}
        out = run_optimize.build_eval_results(raw, {"q1": "eks-design", "q3": "other"})
        self.assertEqual(out["results"][0]["query"], "q1 [owned by sibling `eks-design`]")
        self.assertEqual(out["results"][1]["query"], "q2")
        self.assertEqual(out["results"][2]["query"], "q3 [no sibling, out of scope]")
        self.assertEqual(out["summary"], {"passed": 1, "failed": 2, "total": 3})
        self.assertEqual(out["leakage"]["false_triggers"], ["q1 [owned by sibling `eks-design`]"])
        self.assertEqual(out["leakage"]["missed_triggers"], ["q2"])

    def test_sibling_map_attributes_real_negatives(self):
        owners = run_optimize.sibling_owners(SKILL)
        self.assertIn("eks-best-practices", owners.values())

    def test_build_only_writes_file_and_calls_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            res, out = Path(tmp, "r.json"), Path(tmp, "o.json")
            res.write_text(json.dumps(fake_results(SKILL)))
            with mock.patch.object(run_optimize.subprocess, "run") as run:
                rc = run_optimize.main(["--skill", SKILL, "--results", str(res),
                                        "--out", str(out), "--build-only"])
            self.assertEqual(rc, 0)
            run.assert_not_called()
            data = json.loads(out.read_text())
            self.assertTrue(any("owned by sibling" in q for q in data["leakage"]["false_triggers"]))
            self.assertNotIn("run_records", data["results"][0])

    def test_model_run_calls_vendored_improver(self):
        with tempfile.TemporaryDirectory() as tmp:
            res, out = Path(tmp, "r.json"), Path(tmp, "o.json")
            res.write_text(json.dumps(fake_results(SKILL)))
            with mock.patch.object(run_optimize.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)) as run:
                rc = run_optimize.main(["--skill", SKILL, "--results", str(res),
                                        "--out", str(out), "--model", "m"])
            self.assertEqual(rc, 0)
            cmd = run.call_args.args[0]
            self.assertIn("scripts.improve_description", cmd)
            self.assertEqual(cmd[cmd.index("--eval-results") + 1], str(out))
            self.assertEqual(run.call_args.kwargs["cwd"], run_optimize.SKILL_CREATOR)

    def test_missing_model_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = Path(tmp, "r.json")
            res.write_text(json.dumps(fake_results(SKILL)))
            self.assertEqual(run_optimize.main(["--skill", SKILL, "--results", str(res)]), 1)


if __name__ == "__main__":
    unittest.main()
