#!/usr/bin/env python3
"""P-307: the eval manifest scores the claude harness only.

Run directly with:

    python3 misc/tests/test_p307_tokens_manifest.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MISC_DIR, "evals", "scripts"))

import generate_eval_manifest as gem  # noqa: E402

def task_row(harness, tokens, walls=12.5, cases_passed=2):
    row = {"kind": "task", "skill_summary": {
        "cases": 3, "cases_passed": cases_passed,
        "arms": {"with_skill": {"tokens_per_run_mean": tokens,
                                "wall_seconds_per_run_mean": walls}}}}
    if harness is not None:
        row["harness"] = harness
    return row


class ManifestClaudeRow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p307-manifest-"))
        (self.tmp / "eks-recon" / "baselines").mkdir(parents=True)
        (self.tmp / "eks-recon" / "baselines" / "baseline.json").write_text(json.dumps(
            {"skill": "eks-recon", "composite": {"score": 80.0, "grade": "B"}, "task": {}}))
        (self.tmp / "history").mkdir()
        self.hist = self.tmp / "history" / "eks-recon.jsonl"
        self.patches = [mock.patch.object(gem, "EVALS_ROOT", self.tmp),
                        mock.patch.object(gem, "HISTORY_DIR", self.tmp / "history")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, *rows):
        self.hist.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def entry(self):
        return gem.extract_entry(self.tmp / "eks-recon" / "baselines" / "baseline.json")

    def test_claude_row_then_codex_row_yields_the_claude_value(self):
        self.write(task_row("claude", 200.0, walls=12.5, cases_passed=2),
                   task_row("codex", 900.0, walls=99.0, cases_passed=0))
        e = self.entry()
        self.assertEqual(e["tokens_per_run"], 200)
        self.assertEqual(e["seconds_per_run"], 12.5)
        self.assertEqual(e["cases_passed"], 2)

    def test_row_with_no_harness_is_claude(self):
        self.write(task_row(None, 150.0), task_row("kiro", 900.0))
        self.assertEqual(self.entry()["tokens_per_run"], 150)

    def test_no_claude_row_or_no_summary_reads_none(self):
        self.write(task_row("codex", 900.0))
        e = self.entry()
        self.assertEqual((e["tokens_per_run"], e["seconds_per_run"], e["cases_passed"]),
                         (None, None, None))
        self.write({"kind": "task", "with_skill_mean": 1.0})
        e = self.entry()
        self.assertEqual((e["tokens_per_run"], e["seconds_per_run"], e["cases_passed"]),
                         (None, None, None))


if __name__ == "__main__":
    unittest.main()
