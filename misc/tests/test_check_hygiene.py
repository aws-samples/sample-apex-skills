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

    def set_knowledge(self, assertions: list) -> None:
        def change(data):
            data["evals"][0]["knowledge_assertions"] = assertions
        self.edit_json("evals.json", change)

    def assert_knowledge_fails(self, text: str) -> None:
        res = self.run_check()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("knowledge_assertions[1]", res.stdout)
        self.assertIn(text, res.stdout)

    FLAT = {"type": "must-contain", "pattern": "docs", "source": "README.md"}

    def group(self, **over) -> dict:
        g = {
            "group": "depth",
            "weight": 0.5,
            "assertions": [
                {"type": "must-contain", "pattern": "mkdocs", "source": "README.md"},
                {"type": "must-contain", "pattern": "nav", "source": "README.md",
                 "when_parent_matches": "mkdocs", "weight": 2},
            ],
        }
        g.update(over)
        return g

    def test_valid_group_passes(self):
        self.set_knowledge([self.FLAT, self.group()])
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_group_with_unknown_nested_type_fails(self):
        g = self.group()
        g["assertions"][1]["type"] = "must-match"
        self.set_knowledge([self.FLAT, g])
        self.assert_knowledge_fails("child[1]: unknown assertion type 'must-match'")

    def test_group_with_empty_assertions_fails(self):
        self.set_knowledge([self.FLAT, self.group(assertions=[])])
        self.assert_knowledge_fails("must have a non-empty 'assertions' list")

    def test_group_weight_above_one_fails(self):
        self.set_knowledge([self.FLAT, self.group(weight=2)])
        self.assert_knowledge_fails("Group 'weight' must be a float between 0 and 1")

    def test_group_with_bad_when_parent_matches_fails(self):
        g = self.group()
        g["assertions"][1]["when_parent_matches"] = "("
        self.set_knowledge([self.FLAT, g])
        self.assert_knowledge_fails("invalid 'when_parent_matches' regex")

    def test_group_with_non_object_child_fails(self):
        self.set_knowledge([self.FLAT, self.group(assertions=["mkdocs"])])
        self.assert_knowledge_fails("every group 'assertions' entry must be an object")

    def test_flat_entry_unknown_type_still_fails(self):
        self.set_knowledge([self.FLAT, dict(self.FLAT, type="must-match")])
        self.assert_knowledge_fails("Unknown assertion type: 'must-match'")


if __name__ == "__main__":
    unittest.main()
