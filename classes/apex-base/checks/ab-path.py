#!/usr/bin/env python3
"""AB-PATH: no path from a skill into another skill's folder
(apex-base check no-path-into-another-skill, rule apex.no-path-into-another-skill).

Usage: ab-path.py <skill dir>

Reads every text file of the skill and resolves each relative path that
climbs with `../`, the whole path from the file's folder. A path
that lands inside another skill's folder (any skills/<name>/ or
devops-agent/<name>/ that holds a SKILL.md, such as `../../eks-genai/SKILL.md`
from skills/x/references/ or `../../../skills/eks-recon/x.md` from
devops-agent/eks-recon/references/) fails: a lone copy of the skill does not
have that folder. A climb to a folder that is not a skill (a Terraform
`../modules/` example) passes. Repo-rooted paths (`skills/<name>/...`) are
not checked: a lone copy loads none of them.

Exit 0 pass, 1 fail, 2 usage or internal error. Each output line is
`AB-PATH <PASS|FAIL> <path>[:<line>] <reason>`.
"""

import glob
import os
import re
import sys

CHECK = "AB-PATH"
CLIMB = re.compile(r"(?<![A-Za-z0-9_./-])((?:[A-Za-z0-9._-]+/)*\.\./[A-Za-z0-9._/-]*)")
SKILL_GLOBS = ("skills/*/SKILL.md", "devops-agent/*/SKILL.md")


def skill_files(skill_dir):
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            yield os.path.join(root, name)


def other_skills(skill_dir):
    own = os.path.realpath(skill_dir)
    root = os.path.dirname(os.path.dirname(own))
    found = (os.path.realpath(os.path.dirname(p)) for g in SKILL_GLOBS for p in glob.glob(os.path.join(root, g)))
    return sorted(d for d in found if d != own)


def hits(others, path):
    here = os.path.dirname(os.path.realpath(path))
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except UnicodeDecodeError:
        return
    for number, line in enumerate(lines, 1):
        for m in CLIMB.finditer(line):
            target = os.path.normpath(os.path.join(here, m.group(1)))
            for other in others:
                if target == other or target.startswith(other + os.sep):
                    yield number, os.path.relpath(other)
                    break


def main(argv):
    if len(argv) != 1:
        print(f"usage: {os.path.basename(__file__)} <skill dir>", file=sys.stderr)
        return 2
    skill_dir = os.path.relpath(argv[0])
    if not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        print(f"{CHECK}: no SKILL.md in {skill_dir}", file=sys.stderr)
        return 2
    others = other_skills(skill_dir)
    failed = 0
    try:
        for path in skill_files(skill_dir):
            for number, other in hits(others, path):
                failed += 1
                print(f"{CHECK} FAIL {os.path.relpath(path)}:{number} path into {other}")
    except OSError as e:
        print(f"{CHECK}: cannot read: {e}", file=sys.stderr)
        return 2
    if failed:
        return 1
    print(f"{CHECK} PASS {skill_dir} no path into another skill")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
