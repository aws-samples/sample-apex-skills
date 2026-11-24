"""Offline tests for misc/evals/scripts/update_sibling_map.py (issue 399 item 140).

Run from the repo root: python3 -m pytest misc/tests/test_update_sibling_map.py
Each test copies the script into a temporary tree laid out like the repo
(misc/evals/scripts/ plus one sibling eval dir), so the real tree is never
touched.
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
SCRIPT = REPO / "misc" / "evals" / "scripts" / "update_sibling_map.py"
SIBLING = "sib"

README_WITH_MARKERS = (
    "# Evals\n\n"
    "<!-- SIBLING_MAP_START -->\n"
    "- **`other`** (other scope): negative 2 (\"something else\").\n"
    "<!-- SIBLING_MAP_END -->\n"
)
README_NO_MARKERS = "# Evals\n\nNo sibling map here.\n"

# One entry per line, with a non-ASCII character (U+2014, built from its code
# point here), as misc/evals/update-docs/triggering.json is laid out.
DASH = chr(0x2014)
COMPACT = (
    "[\n"
    '  { "query": "Run update-docs ' + DASH + ' sync the references.", "should_trigger": true },\n'
    '  { "query": "something else", "should_trigger": false }\n'
    "]\n"
)
INDENTED = json.dumps(
    [{"query": "one", "should_trigger": True}, {"query": "two", "should_trigger": False}],
    indent=2,
) + "\n"


class UpdateSiblingMap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "misc" / "evals" / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, root / "misc" / "evals" / "scripts" / SCRIPT.name)
        self.script = root / "misc" / "evals" / "scripts" / SCRIPT.name
        self.dir = root / "misc" / "evals" / SIBLING
        self.dir.mkdir()
        self.triggering = self.dir / "triggering.json"
        self.readme = self.dir / "README.md"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, triggering: str, readme: str) -> None:
        self.triggering.write_text(triggering, encoding="utf-8")
        self.readme.write_text(readme, encoding="utf-8")

    def run_helper(self, *prompts: str) -> subprocess.CompletedProcess:
        args = [sys.executable, str(self.script), "--new-skill", "zz-new",
                "--target-sibling", SIBLING, "--scope", "a new scope"]
        for p in prompts:
            args += ["--negative-prompt", p]
        return subprocess.run(args, capture_output=True, text=True, timeout=60)

    def test_missing_markers_writes_nothing(self):
        self.write(COMPACT, README_NO_MARKERS)
        res = self.run_helper("route this to zz-new")
        self.assertEqual(res.returncode, 1)
        self.assertIn("SIBLING_MAP markers not found", res.stderr)
        self.assertEqual(self.triggering.read_text(encoding="utf-8"), COMPACT)

    def test_rerun_after_missing_markers_appends_nothing(self):
        self.write(COMPACT, README_NO_MARKERS)
        self.run_helper("route this to zz-new")
        self.run_helper("route this to zz-new")
        self.assertEqual(len(json.loads(self.triggering.read_text())), 2)

    def test_prompt_already_in_triggering_is_refused(self):
        self.write(COMPACT, README_WITH_MARKERS)
        res = self.run_helper("something else")
        self.assertEqual(res.returncode, 1)
        self.assertIn("already in", res.stderr)
        self.assertEqual(self.triggering.read_text(encoding="utf-8"), COMPACT)
        self.assertEqual(self.readme.read_text(), README_WITH_MARKERS)

    def test_compact_layout_and_non_ascii_are_kept(self):
        self.write(COMPACT, README_WITH_MARKERS)
        res = self.run_helper("route this to zz-new")
        self.assertEqual(res.returncode, 0, res.stderr)
        after = self.triggering.read_text(encoding="utf-8")
        old_lines = COMPACT.splitlines()
        new_lines = after.splitlines()
        # The existing entries stay byte for byte; only the last one gains a comma.
        self.assertEqual(new_lines[:2], old_lines[:2])
        self.assertEqual(new_lines[2], old_lines[2] + ",")
        self.assertEqual(new_lines[3], '  { "query": "route this to zz-new", "should_trigger": false }')
        self.assertEqual(new_lines[4:], ["]"])
        self.assertIn(DASH, after)
        self.assertNotIn("\\u2014", after)
        data = json.loads(after)
        self.assertEqual(data[-1], {"query": "route this to zz-new", "should_trigger": False})
        self.assertIn("negative 3 (", self.readme.read_text())

    def test_indented_layout_is_kept(self):
        self.write(INDENTED, README_WITH_MARKERS)
        res = self.run_helper("p1", "p2")
        self.assertEqual(res.returncode, 0, res.stderr)
        after = self.triggering.read_text()
        self.assertEqual(
            after,
            json.dumps(
                json.loads(INDENTED)
                + [{"query": "p1", "should_trigger": False},
                   {"query": "p2", "should_trigger": False}],
                indent=2,
            ) + "\n",
        )
        self.assertIn("negatives 3, 4 (", self.readme.read_text())


if __name__ == "__main__":
    unittest.main()
