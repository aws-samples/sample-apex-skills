#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Run an Operator skill's declared artifact checks (operator class).

operator.artifact-checks: a skill that produces an artifact declares that
artifact's checks in its frontmatter, metadata.apex-artifact-checks (a list
of check ids), and the artifact must pass them before it is handed over.
CI runs this on fixture artifacts; at run time the skill runs it on its own
artifact, the same way it runs a schema check.

Check ids (the names misc/evals/<skill>/.skilleval.yaml uses today):
  structural          the artifact file validates against the skill's
                      declared output schema (metadata.apex-outputs)
  terraform-fmt       terraform fmt -check -recursive .
  terraform-validate  terraform init -backend=false -input=false, then
                      terraform validate -no-color
  checkov             checkov -d . --framework terraform --compact --quiet
The terraform and checkov checks run in the artifact folder (or the folder
holding the artifact file). An unknown id, or a check whose tool is not on
PATH, never passes.

Usage:
  run_artifact_checks.py [--skill-dir <skill>] [--checks id,id] <artifact>

--checks replaces the declared list (for CI fixtures). A skill that declares
no checks passes: it produces no artifact to check.
It imports the apex-base class tool schema_check (the class sync rewrites the
import to the flat copy's name). In this repo, run it with
PYTHONPATH=classes/apex-base/scripts.
Exit codes: 0 every check passed; 1 a check failed; 2 a check could not run.
"""
import argparse
import os
import shutil
import subprocess
import sys

import schema_check
from schema_check import CheckError

TIMEOUT = 300
COMMANDS = {
    "terraform-fmt": [["terraform", "fmt", "-check", "-recursive", "."]],
    "terraform-validate": [
        ["terraform", "init", "-backend=false", "-input=false"],
        ["terraform", "validate", "-no-color"],
    ],
    "checkov": [["checkov", "-d", ".", "--framework", "terraform", "--compact", "--quiet"]],
}
KNOWN = ["structural"] + sorted(COMMANDS)


def structural(skill_dir, artifact):
    if not os.path.isfile(artifact):
        raise CheckError(f"structural: {artifact} is not a file")
    schema = schema_check.load_schema(schema_check.declared_schema(skill_dir, "apex-outputs"))
    errors = schema_check.validate(schema_check.load(artifact), schema)
    return (1, "\n".join(errors)) if errors else (0, "validates against the declared output schema")


def run_commands(check, artifact):
    cwd = artifact if os.path.isdir(artifact) else os.path.dirname(os.path.abspath(artifact))
    for cmd in COMMANDS[check]:
        if not shutil.which(cmd[0]):
            raise CheckError(f"{check}: {cmd[0]} is not on PATH")
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise CheckError(f"{check}: {' '.join(cmd)} timed out after {TIMEOUT}s")
        if p.returncode != 0:
            detail = (p.stdout.strip() or p.stderr.strip())[:800]
            return 1, f"{' '.join(cmd)} exited {p.returncode}\n{detail}"
    return 0, "passed"


def declared_checks(skill_dir):
    checks = schema_check.skill_metadata(skill_dir).get("apex-artifact-checks", [])
    if not isinstance(checks, list) or not all(isinstance(c, str) and c for c in checks):
        raise CheckError(f"{skill_dir}/SKILL.md: metadata.apex-artifact-checks must be a list of check ids")
    return checks


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--skill-dir", help="skill folder (default: the folder this copied tool sits in)")
    p.add_argument("--checks", help="comma-separated check ids, instead of the declared list")
    p.add_argument("artifact")
    args = p.parse_args(argv)
    try:
        skill_dir = args.skill_dir or schema_check.default_skill_dir(__file__)
        if not skill_dir:
            raise CheckError("give --skill-dir")
        if args.checks is not None:
            checks = [c.strip() for c in args.checks.split(",") if c.strip()]
            if not checks:
                raise CheckError("--checks names no check")
        else:
            checks = declared_checks(skill_dir)
        unknown = [c for c in checks if c not in KNOWN]
        if unknown:
            raise CheckError(f"unknown check id(s) {', '.join(unknown)}; known: {', '.join(KNOWN)}")
        if not os.path.exists(args.artifact):
            raise CheckError(f"{args.artifact}: no such artifact")
    except CheckError as e:
        print(f"cannot check: {e}", file=sys.stderr)
        return 2
    if not checks:
        print("ok no artifact checks declared")
        return 0
    rc = 0
    for check in checks:
        try:
            code, detail = structural(skill_dir, args.artifact) if check == "structural" \
                else run_commands(check, args.artifact)
        except CheckError as e:
            print(f"cannot run {check}: {e}")
            rc = 2
            continue
        print(f"{'ok' if code == 0 else 'FAIL'} {check}")
        if code:
            rc = max(rc, 1)
            for line in detail.splitlines():
                print(f"  {line}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
