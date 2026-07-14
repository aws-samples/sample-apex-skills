#!/usr/bin/env python3
"""Tests for the safe frontmatter loader.

Run directly with:

    python3 misc/tests/test_safe_frontmatter.py
"""

import os
import sys
import unittest
from glob import glob

# Make the sibling misc/ directory importable regardless of CWD.
MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(MISC_DIR)
sys.path.insert(0, MISC_DIR)

from safe_frontmatter import (  # noqa: E402
    ALLOWED_TOP_LEVEL_KEYS,
    MAX_FRONTMATTER_BYTES,
    MAX_NESTING_DEPTH,
    FrontmatterError,
    load_frontmatter,
)


def _extract_frontmatter(path):
    """Return the frontmatter string between the first two --- delimiters."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    fm_lines = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            return "".join(fm_lines)
        fm_lines.append(line)
    return None


class PositiveCases(unittest.TestCase):
    def test_all_allowed_keys(self):
        raw = (
            "name: my-skill\n"
            "description: A helpful skill.\n"
            "license: Apache-2.0\n"
            "allowed-tools: Read, Bash\n"
            "metadata:\n"
            "  category: general\n"
            "  version: 1\n"
        )
        data = load_frontmatter(raw)
        self.assertEqual(data["name"], "my-skill")
        self.assertEqual(data["description"], "A helpful skill.")
        self.assertEqual(data["license"], "Apache-2.0")
        self.assertEqual(data["allowed-tools"], "Read, Bash")
        self.assertEqual(data["metadata"]["category"], "general")

    def test_nested_metadata_mapping(self):
        raw = "name: s\ndescription: d\nmetadata:\n  a:\n    b: c\n"
        data = load_frontmatter(raw)
        self.assertEqual(data["metadata"]["a"]["b"], "c")

    def test_minimal_name_description(self):
        raw = "name: s\ndescription: d\n"
        data = load_frontmatter(raw)
        self.assertEqual(data, {"name": "s", "description": "d"})

    def test_constants_match_spec(self):
        self.assertEqual(MAX_FRONTMATTER_BYTES, 64 * 1024)
        self.assertEqual(MAX_NESTING_DEPTH, 8)
        self.assertEqual(
            ALLOWED_TOP_LEVEL_KEYS,
            frozenset({"name", "description", "license", "metadata", "allowed-tools"}),
        )


class NegativeCases(unittest.TestCase):
    def test_oversized_input(self):
        raw = "name: s\ndescription: " + ("x" * (MAX_FRONTMATTER_BYTES + 1)) + "\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_anchor_alias(self):
        raw = "name: &a s\ndescription: *a\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_billion_laughs(self):
        raw = (
            "name: &a bomb\n"
            "description: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a]\n"
            "metadata: [*b, *b, *b, *b, *b, *b, *b, *b, *b]\n"
        )
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_duplicate_key(self):
        raw = "name: one\nname: two\ndescription: d\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_non_mapping_list(self):
        raw = "- a\n- b\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_non_mapping_scalar(self):
        raw = "just a string\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_unexpected_top_level_key(self):
        raw = "name: s\ndescription: d\nevil: x\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_excessive_nesting(self):
        # Build a mapping nested deeper than MAX_NESTING_DEPTH under metadata.
        lines = ["name: s", "description: d", "metadata:"]
        indent = "  "
        for i in range(MAX_NESTING_DEPTH + 3):
            lines.append(f"{indent * (i + 1)}k{i}:")
        lines.append(f"{indent * (MAX_NESTING_DEPTH + 4)}leaf: v")
        raw = "\n".join(lines) + "\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_deep_flow_nesting_bomb(self):
        # A deeply-nested flow sequence must be rejected cleanly, not crash
        # the recursive composer/loader with a RecursionError.
        raw = "description: " + ("[" * 600) + ("]" * 600) + "\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_python_object_tag(self):
        # SafeLoader refuses the tag; it must surface as FrontmatterError.
        raw = "description: !!python/object/apply:os.system ['echo hi']\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_complex_unhashable_key(self):
        raw = "? [a, b]\n: 1\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)

    def test_merge_key(self):
        raw = "name: s\ndescription: d\nmetadata:\n  <<: {a: 1}\n"
        with self.assertRaises(FrontmatterError):
            load_frontmatter(raw)


class RealSkillsRegression(unittest.TestCase):
    def test_all_repo_skills_parse(self):
        patterns = [
            os.path.join(REPO_ROOT, "skills", "*", "SKILL.md"),
            os.path.join(REPO_ROOT, "devops-agent", "*", "SKILL.md"),
        ]
        paths = []
        for pattern in patterns:
            paths.extend(sorted(glob(pattern)))
        self.assertTrue(paths, "expected to find at least one SKILL.md")
        for path in paths:
            raw = _extract_frontmatter(path)
            self.assertIsNotNone(raw, f"no frontmatter block in {path}")
            try:
                load_frontmatter(raw, source=path)
            except FrontmatterError as e:
                self.fail(f"{path} failed load_frontmatter: {e}")


if __name__ == "__main__":
    unittest.main()
