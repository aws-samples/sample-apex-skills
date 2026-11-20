"""P-307 groundwork: pass_k bounds, snapshot's pass_k, tokens, time and
harness. Every test builds its
own temp tree; none writes into misc/evals."""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "evals" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import skilleval_config  # noqa: E402
import snapshot  # noqa: E402


def _tmp(test):
    root = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, root, ignore_errors=True)
    return root


class PassKBounds(unittest.TestCase):
    def _load(self, pass_k_text):
        root = _tmp(self)
        (root / "demo").mkdir()
        (root / "demo" / ".skilleval.yaml").write_text(f"regression:\n  pass_k: {pass_k_text}\n")
        with mock.patch.object(skilleval_config, "EVALS_ROOT", root):
            return skilleval_config.load_config("demo")

    def test_pass_k_below_one_is_refused(self):
        for bad in ("0", "-2"):
            with self.subTest(bad=bad), self.assertRaisesRegex(RuntimeError, "pass_k"):
                self._load(bad)

    def test_non_integer_pass_k_is_refused(self):
        for bad in ("2.5", "three", "true"):
            with self.subTest(bad=bad), self.assertRaisesRegex(RuntimeError, "pass_k"):
                self._load(bad)

    def test_valid_pass_k_loads(self):
        self.assertEqual(self._load("1").pass_k, 1)
        self.assertEqual(self._load("5").pass_k, 5)


class SnapshotPassKAndCost(unittest.TestCase):
    def _tree(self, pass_k=5, cases=True):
        root = _tmp(self)
        skill = root / "demo"
        (skill / "workspace" / "runs" / "t1").mkdir(parents=True)
        (skill / "workspace" / "runs" / "t1" / "metrics.json").write_text(json.dumps({
            "overall": {"accuracy": 1.0, "ci_lo": 0.9, "ci_hi": 1.0},
            "positive": {"passed": 1, "total": 1}, "negative": {"passed": 1, "total": 1}}))
        latest = skill / "workspace" / "latest"
        latest.mkdir()
        arm = {"pass_rate": {"mean": 0.8, "stddev": 0.1}}
        (latest / "benchmark.json").write_text(json.dumps({
            "run_summary": {"with_skill": arm, "without_skill": arm},
            "metadata": {"runs_per_configuration": pass_k}}))
        if cases:
            (latest / "cases.json").write_text(json.dumps({
                "harness": "kiro", "base_arm": "without_skill", "pass_k": pass_k,
                "skill_summary": {"arms": {
                    "with_skill": {"tokens_per_run_mean": 1200.0, "wall_seconds_per_run_mean": 41.5},
                    "without_skill": {"tokens_per_run_mean": None, "wall_seconds_per_run_mean": 30.0}}}}))
        (skill / ".skilleval.yaml").write_text(f"regression:\n  pass_k: {pass_k}\n")
        return root

    def _run(self, root, *flags):
        argv = ["snapshot.py", "--skill", "demo", *flags]
        with mock.patch.object(snapshot, "EVALS_ROOT", root), \
                mock.patch.object(skilleval_config, "EVALS_ROOT", root), \
                mock.patch.object(snapshot, "get_git_head", return_value="abc1234"), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()):
            snapshot.main()
        return json.loads((root / "demo" / "baselines" / "baseline.json").read_text())

    def test_config_pass_k_5_gives_baseline_pass_k_5(self):
        self.assertEqual(self._run(self._tree(pass_k=5))["pass_k"], 5)

    def test_explicit_flag_wins_over_config(self):
        self.assertEqual(self._run(self._tree(pass_k=5), "--pass-k", "2")["pass_k"], 2)

    def test_tokens_time_and_harness_come_from_cases_json(self):
        task = self._run(self._tree())["task"]
        self.assertEqual(task["harness"], "kiro")
        self.assertEqual(task["with_skill_tokens_per_run_mean"], 1200.0)
        self.assertEqual(task["with_skill_wall_seconds_per_run_mean"], 41.5)
        self.assertIsNone(task["base_tokens_per_run_mean"])
        self.assertEqual(task["base_wall_seconds_per_run_mean"], 30.0)

    def test_no_cases_json_records_none(self):
        task = self._run(self._tree(cases=False))["task"]
        for key in ("harness", "with_skill_tokens_per_run_mean", "with_skill_wall_seconds_per_run_mean",
                    "base_tokens_per_run_mean", "base_wall_seconds_per_run_mean"):
            self.assertIn(key, task)
            self.assertIsNone(task[key])


if __name__ == "__main__":
    unittest.main()
