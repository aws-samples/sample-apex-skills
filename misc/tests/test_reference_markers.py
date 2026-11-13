#!/usr/bin/env python3
"""Tests that the README reference scripts refuse a damaged block marker.

Each script replaces the lines between a start and an end marker. A marker
line with extra whitespace, a marker pair present twice or a reversed pair
must make the script fail and leave the file alone, and a script that
rewrites two files must not rewrite the first when the second's markers
are bad.

Run directly with:

    python3 misc/tests/test_reference_markers.py
"""

import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (script, directories and files it reads, file holding the markers, start, end)
CASES = [
    (
        "update-skills-references.sh",
        ["README.md", "skills", "misc/update-pages.sh"],
        "skills/README.md",
        "<!-- SKILLS_DETAIL_START -->",
        "<!-- SKILLS_DETAIL_END -->",
    ),
    (
        "update-examples-references.sh",
        ["README.md", "examples"],
        "README.md",
        "<!-- EXAMPLES_REFERENCE_START -->",
        "<!-- EXAMPLES_REFERENCE_END -->",
    ),
    (
        "update-devops-agent-references.sh",
        ["devops-agent"],
        "devops-agent/README.md",
        "<!-- DEVOPS_AGENT_REFERENCE_START -->",
        "<!-- DEVOPS_AGENT_REFERENCE_END -->",
    ),
]


def _copy_tree(root, paths, script):
    os.makedirs(os.path.join(root, "misc"))
    shutil.copy2(os.path.join(REPO_ROOT, "misc", script), os.path.join(root, "misc", script))
    for rel in paths:
        src = os.path.join(REPO_ROOT, rel)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(root, rel))
        else:
            shutil.copy2(src, os.path.join(root, rel))


def _damage(path, marker, replacement):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    hits = [i for i, line in enumerate(lines) if line == marker]
    assert len(hits) == 1, f"{marker} is not one whole line in {path}"
    lines[hits[0]] = replacement
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


class DamagedMarkerTests(unittest.TestCase):
    def _run(self, script, paths, target, marker=None, replacement=None):
        with tempfile.TemporaryDirectory() as root:
            _copy_tree(root, paths, script)
            path = os.path.join(root, target)
            if marker is not None:
                _damage(path, marker, replacement)
            with open(path, "rb") as f:
                before = f.read()
            proc = subprocess.run(
                ["bash", os.path.join(root, "misc", script)],
                capture_output=True,
                text=True,
            )
            with open(path, "rb") as f:
                after = f.read()
        return proc, before, after

    def _run_and_read(self, root, script, path):
        with open(path, "rb") as f:
            before = f.read()
        proc = subprocess.run(
            ["bash", os.path.join(root, "misc", script)], capture_output=True, text=True
        )
        with open(path, "rb") as f:
            after = f.read()
        return proc, before, after

    def _assert_refused(self, script, paths, target, marker, replacement):
        proc, before, after = self._run(script, paths, target, marker, replacement)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ERROR: Could not find", proc.stderr)
        self.assertEqual(before, after)

    def test_undamaged_copy_runs(self):
        # Guards the copy itself: a missing input would also exit non-zero.
        for script, paths, target, start, end in CASES:
            with self.subTest(script=script):
                proc, _, _ = self._run(script, paths, target)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_indented_end_marker_fails_and_keeps_file(self):
        for script, paths, target, start, end in CASES:
            with self.subTest(script=script):
                self._assert_refused(script, paths, target, end, " " + end)

    def test_trailing_space_on_start_marker_fails_and_keeps_file(self):
        for script, paths, target, start, end in CASES:
            with self.subTest(script=script):
                self._assert_refused(script, paths, target, start, start + " ")

    def test_duplicated_marker_pair_fails_and_keeps_file(self):
        for script, paths, target, start, end in CASES:
            with self.subTest(script=script):
                with tempfile.TemporaryDirectory() as root:
                    _copy_tree(root, paths, script)
                    path = os.path.join(root, target)
                    with open(path, "a", encoding="utf-8") as f:
                        f.write("\n" + start + "\npasted copy\n" + end + "\n")
                    proc, before, after = self._run_and_read(root, script, path)
                self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("exactly once", proc.stderr)
                self.assertEqual(before, after)

    def test_reversed_marker_pair_fails_and_keeps_file(self):
        for script, paths, target, start, end in CASES:
            with self.subTest(script=script):
                with tempfile.TemporaryDirectory() as root:
                    _copy_tree(root, paths, script)
                    path = os.path.join(root, target)
                    _damage(path, start, "swap placeholder")
                    _damage(path, end, start)
                    _damage(path, "swap placeholder", end)
                    proc, before, after = self._run_and_read(root, script, path)
                self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("must come before", proc.stderr)
                self.assertEqual(before, after)

    def test_failed_second_file_leaves_first_file_alone(self):
        # Only the skills script can hit this today: the examples script writes
        # examples/README.md second only when that file exists, and the repo has none.
        script = "update-skills-references.sh"
        with tempfile.TemporaryDirectory() as root:
            _copy_tree(root, ["README.md", "skills", "misc/update-pages.sh"], script)
            first_path = os.path.join(root, "README.md")
            # A stale first block, so a write would change the file.
            _damage(first_path, "<!-- SKILLS_REFERENCE_START -->", "<!-- SKILLS_REFERENCE_START -->\nstale line")
            _damage(os.path.join(root, "skills/README.md"), "<!-- SKILLS_DETAIL_END -->", " <!-- SKILLS_DETAIL_END -->")
            proc, before, after = self._run_and_read(root, script, first_path)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
