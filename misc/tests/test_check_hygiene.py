"""Offline tests for misc/evals/scripts/check_hygiene.py (issue 399 item 140).

Run from the repo root: python3 -m pytest misc/tests/test_check_hygiene.py
Each test copies the scripts, one passing eval set and its skill into a
temporary tree laid out like the repo, so the real tree is never touched.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = "update-docs"


class CheckHygienePlaceholders(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        shutil.copytree(REPO / "misc" / "evals" / "scripts", root / "misc" / "evals" / "scripts")
        shutil.copytree(REPO / "misc" / "evals" / SKILL, root / "misc" / "evals" / SKILL)
        for skill in (SKILL, "skill-creator"):
            shutil.copytree(REPO / "skills" / skill, root / "skills" / skill)
        self.root = root
        self.evals = root / "misc" / "evals" / SKILL

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.root / "misc" / "evals" / "scripts" / "check_hygiene.py"),
             "--skill", SKILL],
            capture_output=True, text=True, timeout=120,
        )

    def edit_json(self, name: str, change) -> None:
        path = self.evals / name
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def assert_fails_on_placeholder(self, name: str) -> None:
        res = self.run_check()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn(f"{name} still has", res.stdout)

    def test_control_copy_passes(self):
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_placeholder_in_triggering_query_fails(self):
        def change(data):
            first = next(e for e in data if e["should_trigger"] is True)
            first["query"] = "<REPLACE: positive prompt that should trigger this skill>"
        self.edit_json("triggering.json", change)
        self.assert_fails_on_placeholder("triggering.json")

    def test_placeholder_in_evals_prompt_fails(self):
        def change(data):
            data["evals"][0]["prompt"] = "<REPLACE: realistic task prompt>"
        self.edit_json("evals.json", change)
        self.assert_fails_on_placeholder("evals.json")

    def test_placeholder_in_evals_expectation_fails(self):
        def change(data):
            data["evals"][0]["expectations"][0] = "<REPLACE: grader-checkable assertion>"
        self.edit_json("evals.json", change)
        self.assert_fails_on_placeholder("evals.json")

    def test_placeholder_in_readme_fails(self):
        readme = self.evals / "README.md"
        readme.write_text(readme.read_text() + "\n<REPLACE: 1-3 sentence scope description>\n")
        self.assert_fails_on_placeholder("README.md")


if __name__ == "__main__":
    unittest.main()
