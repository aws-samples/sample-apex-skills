#!/usr/bin/env python3
"""AB-LINK: relative Markdown links resolve (apex-base check relative-links-resolve).

Usage: ab-link.py <skill dir>

Reads every Markdown file of the skill and checks each relative link target,
inline (`[text](target)`, images included) and reference-style
(`[label]: target`), with any `#anchor` or `?query` dropped. The target must
exist inside the skill's own folder, since a skill is installed alone.
Absolute URLs (a scheme such as https: or mailto:), absolute paths and
same-file anchors are out of scope. Links inside fenced code blocks and
inline code spans are skipped: they are examples, not links.

Exit 0 pass, 1 fail, 2 usage or internal error. Each output line is
`AB-LINK <PASS|FAIL> <path>[:<line>] <reason>`.
"""

import os
import re
import sys
from urllib.parse import unquote

CHECK = "AB-LINK"
INLINE = re.compile(r"!?\[(?:[^\]\\]|\\.)*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(][^)]*)?\)")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def markdown_files(skill_dir):
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            if name.endswith(".md"):
                yield os.path.join(root, name)


def link_targets(lines):
    fence = None
    for number, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if m:
            mark = m.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        text = CODE_SPAN.sub("", line)
        for target in INLINE.findall(text):
            yield number, target
        m = REFERENCE.match(text)
        if m:
            yield number, m.group(1)


def broken(skill_dir, path):
    own = os.path.realpath(skill_dir)
    here = os.path.dirname(os.path.realpath(path))
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for number, target in link_targets(lines):
        if SCHEME.match(target) or target.startswith(("#", "/")):
            continue
        bare = unquote(re.split(r"[#?]", target, maxsplit=1)[0])
        if not bare:
            continue
        resolved = os.path.normpath(os.path.join(here, bare))
        if resolved != own and not resolved.startswith(own + os.sep):
            yield number, target, "leaves the skill folder"
        elif not os.path.exists(resolved):
            yield number, target, "broken link"


def main(argv):
    if len(argv) != 1:
        print(f"usage: {os.path.basename(__file__)} <skill dir>", file=sys.stderr)
        return 2
    skill_dir = os.path.relpath(argv[0])
    if not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        print(f"{CHECK}: no SKILL.md in {skill_dir}", file=sys.stderr)
        return 2
    failed = 0
    try:
        for path in markdown_files(skill_dir):
            for number, target, reason in broken(skill_dir, path):
                failed += 1
                print(f"{CHECK} FAIL {os.path.relpath(path)}:{number} {reason} {target}")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{CHECK}: cannot read: {e}", file=sys.stderr)
        return 2
    if failed:
        return 1
    print(f"{CHECK} PASS {skill_dir} relative links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
