#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema[format-nongpl]>=4.26,<5", "pyyaml>=6,<7"]
# ///
"""The Script class's k-run diff: the same input gives the same answer on every run.

script.same-output. Give it the outputs of k runs on one input. It drops the
fields the skill's "same answer" rule lists (assets/same-answer.yaml), then
compares the rest exactly: every count and every other value, lists in order.
File names never enter the comparison.

same-answer.yaml:
  k: 10                      # runs the check needs (--k overrides)
  ignore:                    # dot paths dropped before the comparison;
    - report.generated_at    # "[]" means every element of a list
    - cluster_insights.list[].last_refresh_time

Usage:
  k_run_diff.py [--skill-dir <skill>] [--k <n>] <run-output>...

It imports the apex-base class tool schema_check (the class sync (planned)
rewrites the import to the flat copy's name). In this repo, run it with
PYTHONPATH=classes/apex-base/scripts.
Exit codes: 0 the same answer in every run; 1 a run differs; 2 the check
could not run (fewer than k files, a file given twice, unreadable input, a
bad rule file, input nested too deep).
"""
import argparse
import copy
import json
import os
import sys

try:
    import schema_check
except ImportError:
    print("cannot check: the apex-base class tool schema_check is not installed beside this tool", file=sys.stderr)
    sys.exit(2)
from schema_check import CheckError  # noqa: E402


def load_rule(path):
    rule = schema_check.load(path)
    if not isinstance(rule, dict):
        raise CheckError(f"{path}: must be a mapping with k and ignore")
    k = rule.get("k")
    ignore = rule.get("ignore", [])
    if not isinstance(k, int) or isinstance(k, bool) or k < 2:
        raise CheckError(f"{path}: k must be an integer of at least 2")
    if not isinstance(ignore, list) or not all(isinstance(p, str) and p for p in ignore):
        raise CheckError(f"{path}: ignore must be a list of dot paths")
    return k, ignore


def drop(doc, path):
    """Remove one dot path ("a.b[].c") from doc in place; absent parts are skipped."""
    head, _, rest = path.partition(".")
    each = head.endswith("[]")
    key = head[:-2] if each else head
    if not isinstance(doc, dict) or key not in doc:
        return
    if not rest and not each:
        del doc[key]
        return
    targets = doc[key] if each else [doc[key]]
    if each and not isinstance(targets, list):
        return
    for t in targets:
        if rest:
            drop(t, rest)
    if each and not rest:
        del doc[key]


def diff(a, b, path="$", out=None):
    """List the paths where a and b differ."""
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            sub = f"{path}.{key}"
            if key not in a or key not in b:
                out.append(f"{sub}: present in only one run")
            else:
                diff(a[key], b[key], sub, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items against {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out)
    elif type(a) is not type(b) or a != b:
        out.append(f"{path}: {json.dumps(a, default=str)} against {json.dumps(b, default=str)}")
    return out


def compare(docs, ignore):
    """Return per-run differences against run 1 after dropping the ignored paths."""
    kept = []
    for d in docs:
        d = copy.deepcopy(d)
        for p in ignore:
            drop(d, p)
        kept.append(d)
    return [(i + 1, diff(kept[0], d)) for i, d in enumerate(kept) if i]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--skill-dir", help="skill folder holding assets/same-answer.yaml")
    p.add_argument("--k", type=int, help="runs required (default: the rule's k)")
    p.add_argument("files", nargs="*")
    args = p.parse_args(argv)
    try:
        skill_dir = args.skill_dir or schema_check.default_skill_dir(__file__)
        if not skill_dir:
            raise CheckError("give --skill-dir")
        k, ignore = load_rule(os.path.join(skill_dir, "assets", "same-answer.yaml"))
        k = args.k if args.k is not None else k
        if k < 2:
            raise CheckError("--k must be at least 2")
        if len(args.files) < k:
            raise CheckError(f"{len(args.files)} run outputs given, the check needs {k}")
        real = [os.path.realpath(f) for f in args.files]
        if len(set(real)) != len(real):
            raise CheckError("a run output is given twice")
        docs = [schema_check.load(f) for f in args.files]
        results = compare(docs, ignore)
    except CheckError as e:
        print(f"cannot check: {e}", file=sys.stderr)
        return 2
    except RecursionError:
        print("cannot check: a run output is nested too deep", file=sys.stderr)
        return 2
    rc = 0
    for run, found in results:
        if found:
            rc = 1
            print(f"FAIL run {run} ({args.files[run - 1]}) differs from run 1 ({args.files[0]}):")
            for line in found:
                print(f"  {line}")
    if rc == 0:
        print(f"ok the same answer in all {len(docs)} runs (ignoring {len(ignore)} listed paths)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
