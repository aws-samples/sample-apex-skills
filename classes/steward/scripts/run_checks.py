#!/usr/bin/env python3
"""Admission-check runner: run every class.yaml check on every member skill.

Usage:
    run_checks.py [--root <repo root>] [--no-hook-tests]
    run_checks.py --self-test

A skill is a member of the classes its SKILL.md frontmatter names in
`metadata.apex-classes` (a space-separated list). For each member the runner
walks the class chain, parents first and each class once, and runs each
`checks:` entry of each classes/<c>/class.yaml:

  - status `exists`: its `run` command, from the repo root, with the skill
    folder as the last argument. Exit 0 is a pass, 1 a fail, anything else
    (or a run past the timeout) an error.
  - status `planned`: not built yet, so never counted as a pass; named in a
    PLANNED line.

The runner never stops at the first fail. A check prints its own
`<CHECK-ID> <PASS|FAIL> <path>[:<line>] <reason>` lines, which the runner
passes through; the runner adds `<id> ERROR <skill> <reason>` lines for
errors. Then it prints `<n> checks on <m> skills, <f> failed, <e> errors`
(plus `, <p> planned` when any are), runs the hook unit tests
(run_hook_tests.py) unless --no-hook-tests, and exits 1 when any check or hook test failed or errored, else 0.

--self-test runs the cases in tests/cases.json beside this script: each one
builds a temp tree (a git repo when it has commits), runs a command there and
asserts its exit code and literal output lines (present, absent, in order).
"""

import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO_ROOT, "misc"))

import yaml  # noqa: E402
from safe_frontmatter import FrontmatterError, load_frontmatter  # noqa: E402

CHECK_TIMEOUT = 120
SKILL_GLOBS = ("skills/*/SKILL.md", "devops-agent/*/SKILL.md")


class ClassError(Exception):
    pass


def frontmatter(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    for i, line in enumerate(lines[1:], 1):
        if line.rstrip() == "---":
            return "".join(lines[1:i])
    return None


def declared_classes(skill_md):
    """Return the skill's metadata.apex-classes as a list ([] when absent)."""
    raw = frontmatter(skill_md)
    if raw is None:
        return []
    meta = load_frontmatter(raw).get("metadata")
    value = meta.get("apex-classes") if isinstance(meta, dict) else None
    if value is None:
        return []
    if not isinstance(value, str):
        raise ClassError("metadata.apex-classes must be a space-separated string")
    return value.split()


def load_class(name, cache):
    if name not in cache:
        path = os.path.join("classes", name, "class.yaml")
        if not os.path.isfile(path):
            raise ClassError(f"unknown class '{name}' (no {path})")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ClassError(f"{path} is not a mapping")
        cache[name] = data
    return cache[name]


def chain(names, cache):
    """Resolve classes parents first, each class once."""
    order, visiting = [], set()

    def visit(name):
        if name in order:
            return
        if name in visiting:
            raise ClassError(f"class cycle at '{name}'")
        visiting.add(name)
        for parent in load_class(name, cache).get("parents") or []:
            visit(parent)
        visiting.discard(name)
        order.append(name)

    for name in names:
        visit(name)
    return order


def run_member(skill_dir, classes, cache, counts):
    for cls in classes:
        for entry in load_class(cls, cache).get("checks") or []:
            check_id = entry.get("id", "?") if isinstance(entry, dict) else "?"
            status = entry.get("status") if isinstance(entry, dict) else None
            if status == "planned":
                counts["planned"] += 1
                print(f"{check_id} PLANNED {skill_dir} class {cls}, not built yet")
                continue
            counts["checks"] += 1
            if status != "exists" or not entry.get("run"):
                counts["errors"] += 1
                print(f"{check_id} ERROR {skill_dir} class {cls}: status '{status}' with no run command")
                continue
            try:
                r = subprocess.run([*shlex.split(entry["run"]), skill_dir], capture_output=True,
                                   text=True, timeout=CHECK_TIMEOUT)
            except subprocess.TimeoutExpired:
                counts["errors"] += 1
                print(f"{check_id} ERROR {skill_dir} timeout after {CHECK_TIMEOUT}s")
                continue
            except OSError as e:
                counts["errors"] += 1
                print(f"{check_id} ERROR {skill_dir} cannot run: {e}")
                continue
            if r.stdout:
                print(r.stdout, end="" if r.stdout.endswith("\n") else "\n")
            if r.returncode == 1:
                counts["failed"] += 1
            elif r.returncode != 0:
                counts["errors"] += 1
                last = (r.stderr.strip().splitlines() or [""])[-1]
                print(f"{check_id} ERROR {skill_dir} exit {r.returncode}: {last}")


def run_all(root, hook_tests):
    os.chdir(root)
    cache = {}
    counts = {"checks": 0, "failed": 0, "errors": 0, "planned": 0}
    members = 0
    for skill_md in sorted(p for g in SKILL_GLOBS for p in glob.glob(g)):
        skill_dir = os.path.dirname(skill_md)
        try:
            names = declared_classes(skill_md)
            if not names:
                continue
            members += 1
            run_member(skill_dir, chain(names, cache), cache, counts)
        except (ClassError, FrontmatterError, yaml.YAMLError, OSError, UnicodeDecodeError) as e:
            counts["errors"] += 1
            print(f"runner ERROR {skill_dir} {e}")
    summary = (f"{counts['checks']} checks on {members} skills, "
               f"{counts['failed']} failed, {counts['errors']} errors")
    if counts["planned"]:
        summary += f", {counts['planned']} planned"
    print(summary)
    rc = 1 if counts["failed"] or counts["errors"] else 0
    if hook_tests:
        sys.stdout.flush()
        r = subprocess.run([sys.executable, os.path.join(HERE, "run_hook_tests.py"), "--root", "."])
        if r.returncode != 0:
            rc = 1
    return rc


def write_files(root, files):
    for rel, content in files.items():
        path = os.path.join(root, rel)
        if content is None:
            if os.path.exists(path):
                os.remove(path)
            continue
        if isinstance(content, dict):
            content = content.get("text", "") + content["line"] * content["times"]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if rel.endswith((".py", ".sh")):
            os.chmod(path, 0o755)


def run_case(case):
    """Return a list of problems; empty when the case passed."""
    tmp = tempfile.mkdtemp(prefix="class-checks-")
    try:
        write_files(tmp, case.get("files", {}))
        env = dict(os.environ)
        env.pop("BASE_SHA", None)
        env.pop("HEAD_SHA", None)
        git_env = {**env, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        commits = case.get("commits", [])
        if commits:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True, env=git_env)
        for commit in commits:
            write_files(tmp, commit.get("files", {}))
            subprocess.run(["git", "add", "-A"], cwd=tmp, check=True, env=git_env)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "c"], cwd=tmp, check=True, env=git_env)
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp, check=True, env=git_env,
                                 capture_output=True, text=True).stdout.strip()
            if commit.get("as"):
                env[commit["as"]] = sha
        cmd = [sys.executable if a == "{python}" else a.replace("{repo}", REPO_ROOT) for a in case["cmd"]]
        r = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=300)
        out = r.stdout.splitlines()
        problems = []
        if r.returncode != case["exit"]:
            problems.append(f"exit {r.returncode}, expected {case['exit']}")
        for line in case.get("stdout_has", []):
            if line not in out:
                problems.append(f"missing line {line!r}")
        order = [out.index(line) for line in case.get("stdout_in_order", []) if line in out]
        if order != sorted(order):
            problems.append(f"lines out of order: {case['stdout_in_order']}")
        for line in case.get("stdout_lacks", []):
            if line in out:
                problems.append(f"unexpected line {line!r}")
        if problems and (r.stdout or r.stderr):
            problems.append("output:\n" + r.stdout + r.stderr)
        return problems
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def self_test():
    with open(os.path.join(HERE, "tests", "cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    failed = 0
    for case in cases:
        problems = run_case(case)
        print(f"SELF-TEST {'FAIL' if problems else 'PASS'} {case['name']}")
        for p in problems:
            print("  " + p.replace("\n", "\n  "))
        failed += bool(problems)
    print(f"{len(cases)} cases, {failed} failed")
    return 1 if failed else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    root, hook_tests = REPO_ROOT, True
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = args.pop(0)
        elif arg == "--no-hook-tests":
            hook_tests = False
        else:
            print(__doc__.split("\n\n")[1], file=sys.stderr)
            return 2
    return run_all(root, hook_tests)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
