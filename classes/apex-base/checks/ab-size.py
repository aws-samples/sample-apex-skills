#!/usr/bin/env python3
"""AB-SIZE: SKILL.md under 500 lines (apex-base check skill-md-under-500-lines).

Usage: ab-size.py <skill dir>

Counts lines, a last line with no final newline included; 500 or more fails.

Exit 0 pass, 1 fail, 2 usage or internal error. Each output line is
`AB-SIZE <PASS|FAIL> <path> <reason>`.
"""

import os
import sys

CHECK = "AB-SIZE"
MAX_LINES = 499


def main(argv):
    if len(argv) != 1:
        print(f"usage: {os.path.basename(__file__)} <skill dir>", file=sys.stderr)
        return 2
    skill_md = os.path.relpath(os.path.join(argv[0], "SKILL.md"))
    try:
        with open(skill_md, "rb") as f:
            count = len(f.read().splitlines())
    except OSError as e:
        print(f"{CHECK}: cannot read {skill_md}: {e}", file=sys.stderr)
        return 2
    if count > MAX_LINES:
        print(f"{CHECK} FAIL {skill_md} {count} lines (max {MAX_LINES})")
        return 1
    print(f"{CHECK} PASS {skill_md} {count} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
