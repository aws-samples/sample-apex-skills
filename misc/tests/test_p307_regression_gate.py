"""P-307: `regression.py --gate` refuses a task result run below three runs
per case (STEP3-PLAN R:248, "Three runs per case"): exit 1, a config error,
distinct from exit 2, a regression."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import regression  # noqa: E402

KEY = "eks-recon"
_ABSENT = object()


def _entry(pass_k=3):
    arm = {"runs": 3, "valid_runs": 3, "passes": 3, "pass_at_k": True, "pass_all_k": True}
    entry = {"kind": "task", "run_key": KEY, "harness": "claude", "baseline_arm": "base_skill",
             "delta": 0.0, "cases": [{"eval_id": 1, "source": "own", "pass": True,
                                      "arms": {"with_skill": arm, "base_skill": arm}}]}
    if pass_k is not _ABSENT:
        entry["pass_k"] = pass_k
    return entry


class ThreeRunFloor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p307-gate-"))
        self._summary = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._summary is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._summary
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gate(self, entry):
        runs = self.tmp / "ws" / "runs" / "20261120T000000Z"
        runs.mkdir(parents=True, exist_ok=True)
        path = self.tmp / "task.json"
        path.write_text(json.dumps([{"skill": KEY, "runs_dir": str(runs), "history_entry": entry}]))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = regression.run_gate(KEY, path, 5.0)
        return rc, out.getvalue(), err.getvalue()

    def assert_refused(self, entry):
        rc, out, err = self.gate(entry)
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("three runs per case", err)

    def test_pass_k_one_exits_1(self):
        self.assert_refused(_entry(1))

    def test_pass_k_two_exits_1(self):
        self.assert_refused(_entry(2))

    def test_pass_k_missing_exits_1(self):
        self.assert_refused(_entry(_ABSENT))

    def test_pass_k_not_an_int_exits_1(self):
        for bad in ("3", 3.0, True, None):
            with self.subTest(pass_k=bad):
                self.assert_refused(_entry(bad))

    def test_pass_k_three_passes_as_today(self):
        rc, out, _ = self.gate(_entry(3))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
