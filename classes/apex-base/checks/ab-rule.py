#!/usr/bin/env python3
"""AB-RULE: apex-base rule ids present in the SKILL.md marker block
(apex-base check rule-ids-in-marker-block).

Usage, from the repo root: ab-rule.py <skill dir>

Reads every rule id apex-base declares (`- **<id>**:` lines in
classes/apex-base/rules.md, read from the current directory) and requires
each one inside the skill's class marker block, `<!-- APEX_CLASSES_START -->` to
`<!-- APEX_CLASSES_END -->`, the block the class sync writes. This proves the
copy landed, not behaviour. Marker integrity (a block present twice, a block
edited by hand) is the class sync's --check, not this check.

Exit 0 pass, 1 fail, 2 usage or internal error. Each output line is
`AB-RULE <PASS|FAIL> <path> <reason>`.
"""

import os
import re
import sys

CHECK = "AB-RULE"
START = "<!-- APEX_CLASSES_START -->"
END = "<!-- APEX_CLASSES_END -->"
RULES = os.path.join("classes", "apex-base", "rules.md")
RULE_LINE = re.compile(r"^- \*\*([a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*)\*\*:")


def rule_ids(rules_path):
    with open(rules_path, encoding="utf-8") as f:
        return [m.group(1) for m in (RULE_LINE.match(line) for line in f) if m]


def marker_block(text):
    """Return the text between the first start marker and the next end marker."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == START]
    if not starts:
        return None
    for j in range(starts[0] + 1, len(lines)):
        if lines[j].strip() == END:
            return "\n".join(lines[starts[0] + 1:j])
    return None


def main(argv):
    rules_path = RULES
    if len(argv) != 1:
        print(f"usage: {os.path.basename(__file__)} <skill dir>", file=sys.stderr)
        return 2
    skill_md = os.path.relpath(os.path.join(argv[0], "SKILL.md"))
    try:
        ids = rule_ids(rules_path)
        with open(skill_md, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"{CHECK}: cannot read: {e}", file=sys.stderr)
        return 2
    if not ids:
        print(f"{CHECK}: no rule ids found in {rules_path}", file=sys.stderr)
        return 2
    block = marker_block(text)
    if block is None:
        print(f"{CHECK} FAIL {skill_md} no marker block")
        return 1
    missing = [i for i in ids if not re.search(r"(?<![A-Za-z0-9.-])" + re.escape(i) + r"(?![A-Za-z0-9-])", block)]
    for rule in missing:
        print(f"{CHECK} FAIL {skill_md} missing {rule}")
    if missing:
        return 1
    print(f"{CHECK} PASS {skill_md} {len(ids)} rule ids in the marker block")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
