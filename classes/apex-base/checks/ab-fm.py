#!/usr/bin/env python3
"""AB-FM: frontmatter lint for one skill (apex-base check frontmatter-lint).

Usage: ab-fm.py <skill dir>

Parses SKILL.md frontmatter with misc/safe_frontmatter.py and requires
`name` (a string equal to the folder name) and `description` (a string of
1 to 1024 characters). The manifest match stays in
misc/validate-frontmatter.py, which is not a class check.

Exit 0 pass, 1 fail, 2 usage or internal error. Each output line is
`AB-FM <PASS|FAIL> <path> <reason>`.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO_ROOT, "misc"))

from safe_frontmatter import FrontmatterError, load_frontmatter  # noqa: E402

CHECK = "AB-FM"


def extract_frontmatter(path):
    """Return the text between the opening and closing `---`, or None."""
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


def problems(skill_dir, skill_md):
    raw = extract_frontmatter(skill_md)
    if raw is None:
        return ["no YAML frontmatter block found"]
    try:
        data = load_frontmatter(raw)
    except FrontmatterError as e:
        return [str(e)]
    found = []
    folder = os.path.basename(os.path.normpath(skill_dir))
    name = data.get("name")
    if not isinstance(name, str) or not name:
        found.append("missing or invalid 'name' key")
    elif name != folder:
        found.append(f"name '{name}' does not match folder '{folder}'")
    desc = data.get("description")
    if not isinstance(desc, str):
        found.append("missing or invalid 'description' key")
    elif not 1 <= len(desc) <= 1024:
        found.append(f"description is {len(desc)} chars (1 to 1024)")
    return found


def main(argv):
    if len(argv) != 1:
        print(f"usage: {os.path.basename(__file__)} <skill dir>", file=sys.stderr)
        return 2
    skill_dir = argv[0]
    skill_md = os.path.relpath(os.path.join(skill_dir, "SKILL.md"))
    if not os.path.isfile(skill_md):
        print(f"{CHECK}: no SKILL.md in {skill_dir}", file=sys.stderr)
        return 2
    try:
        found = problems(skill_dir, skill_md)
    except (OSError, UnicodeDecodeError) as e:
        print(f"{CHECK}: cannot read {skill_md}: {e}", file=sys.stderr)
        return 2
    for reason in found:
        print(f"{CHECK} FAIL {skill_md} {reason}")
    if found:
        return 1
    print(f"{CHECK} PASS {skill_md} frontmatter ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
