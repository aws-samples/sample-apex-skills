#!/usr/bin/env python3
"""AB-VER: a required metadata.version, bumped on every change to a skill's
instructions, scripts or references (apex-base check metadata-version-bumped).
Watched paths: SKILL.md, agents/ (loaded as instructions), scripts/ and tools/
(run as scripts), and references/.

Usage: ab-ver.py <skill dir>

Environment: BASE_SHA and HEAD_SHA, the commits to compare (HEAD_SHA
defaults to HEAD). With no BASE_SHA, or one git cannot read (the first push
of a branch), only presence and format are checked.

Fails when `metadata.version` is missing or is not X.Y.Z (the form
misc/bump-version.sh checks). With a base, also fails when a path under the
skill's watched paths changed between BASE_SHA and
HEAD_SHA and the version is not greater than at the base, compared as
numbers. A skill with no SKILL.md, or no version, at the base is new to the
check, so presence and format are enough.

Exit 0 pass, 1 fail, 2 usage or internal error. Each output line is
`AB-VER <PASS|FAIL> <path> <reason>`.
"""

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO_ROOT, "misc"))

from safe_frontmatter import FrontmatterError, load_frontmatter  # noqa: E402

CHECK = "AB-VER"
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
WATCHED = ("SKILL.md", "scripts/", "references/", "agents/", "tools/")


def frontmatter(text):
    """Return the text between the opening and closing `---` lines, or None.

    Splits on "\\n" only, so U+2028 and the other Unicode line breaks never
    end a line. The same function is in classes/steward/scripts/run_checks.py and ab-fm.py.
    """
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "".join(line + "\n" for line in lines[1:i])
    return None


def version_of(text):
    """Return metadata.version as a string, None when absent."""
    raw = frontmatter(text)
    if raw is None:
        raise FrontmatterError("no YAML frontmatter block found")
    data = load_frontmatter(raw)
    meta = data.get("metadata")
    if not isinstance(meta, dict) or meta.get("version") is None:
        return None
    return str(meta["version"])


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def show(sha, path):
    r = git("show", f"{sha}:{path}")
    return r.stdout if r.returncode == 0 else None


def main(argv):
    if len(argv) != 1:
        print(f"usage: {os.path.basename(__file__)} <skill dir>", file=sys.stderr)
        return 2
    skill_dir = os.path.relpath(argv[0])
    skill_md = os.path.join(skill_dir, "SKILL.md")
    base = os.environ.get("BASE_SHA", "")
    head = os.environ.get("HEAD_SHA", "") or "HEAD"
    if base and git("cat-file", "-e", f"{base}^{{commit}}").returncode != 0:
        base = ""
    try:
        head_text = show(head, skill_md)
        if head_text is None:
            print(f"{CHECK}: cannot read {skill_md} at {head}", file=sys.stderr)
            return 2
        version = version_of(head_text)
    except FrontmatterError as e:
        print(f"{CHECK} FAIL {skill_md} {e}")
        return 1
    if version is None:
        print(f"{CHECK} FAIL {skill_md} metadata.version missing")
        return 1
    if not SEMVER.match(version):
        print(f"{CHECK} FAIL {skill_md} metadata.version '{version}' is not X.Y.Z")
        return 1
    if not base:
        print(f"{CHECK} PASS {skill_md} version {version} (no base: presence and format only)")
        return 0
    r = git("diff", "-z", "--name-only", "--no-renames", f"{base}...{head}", "--", skill_dir)
    if r.returncode != 0:
        print(f"{CHECK}: git diff failed: {r.stderr.strip()}", file=sys.stderr)
        return 2
    prefix = skill_dir.replace(os.sep, "/") + "/"
    changed = sorted(p[len(prefix):] for p in r.stdout.split("\0")
                     if p.startswith(prefix) and p[len(prefix):].startswith(WATCHED))
    if not changed:
        print(f"{CHECK} PASS {skill_md} version {version}, no watched path changed")
        return 0
    base_text = show(base, skill_md)
    try:
        old = version_of(base_text) if base_text is not None else None
    except FrontmatterError:
        old = None
    if old is None or not SEMVER.match(old):
        print(f"{CHECK} PASS {skill_md} version {version}, new to the check")
        return 0
    if tuple(map(int, version.split("."))) > tuple(map(int, old.split("."))):
        print(f"{CHECK} PASS {skill_md} version {old} to {version}")
        return 0
    state = "unchanged" if version == old else f"not greater than {old}"
    print(f"{CHECK} FAIL {skill_md} version {version} {state}; changed: {', '.join(changed)}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except UnicodeDecodeError as e:
        print(f"{CHECK}: git output is not UTF-8: {e}", file=sys.stderr)
        sys.exit(2)
