#!/usr/bin/env python3
"""Deterministic hygiene pre-flight for misc/evals/<skill>/ entries.

Reuses the pre-flight logic already embedded in run_all_evals.py — runs
quick_validate, checks triggering.json positive/negative counts, checks
evals.json prompt/expectation counts, and confirms every `should_trigger=false`
entry in triggering.json is attributed to a sibling in README.md's
SIBLING_MAP block.

No model calls, no Makefile shell-outs, no live cluster. Safe for a
per-PR CI gate.

Usage:
  check_hygiene.py               — every skill under misc/evals/
  check_hygiene.py --skill NAME  — single skill (used by make init-evals-finalize)

Exit codes:
  0  every skill is clean
  1  one or more skills have hygiene warnings
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_run_all_evals():
    """Import run_all_evals.py without relying on a package __init__.py."""
    name = "_run_all_evals_for_hygiene"
    spec = importlib.util.spec_from_file_location(
        name,
        SCRIPTS_DIR / "run_all_evals.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--skill",
        help="Check only this skill (used by `make init-evals-finalize`). "
        "Default: every skill under misc/evals/.",
    )
    args = parser.parse_args()

    rae = _load_run_all_evals()

    skills = rae.discover_skills()
    if args.skill:
        if args.skill not in skills:
            print(
                f"unknown skill: {args.skill} (known: {', '.join(skills) or 'none'})",
                file=sys.stderr,
            )
            return 1
        skills = [args.skill]

    if not skills:
        print("no skills discovered under misc/evals/", file=sys.stderr)
        return 1

    any_fail = False
    for skill in skills:
        warnings: list[str] = []

        hygiene = rae.hygiene_check(skill)
        warnings.extend(hygiene.warnings)

        # Sibling-map attribution check — mirror the body of process_skill()
        # without shelling out to make.
        readme_path = rae.EVALS_ROOT / skill / "README.md"
        triggering_path = rae.EVALS_ROOT / skill / "triggering.json"
        try:
            import json

            triggering = json.loads(triggering_path.read_text())
        except FileNotFoundError:
            triggering = []
        except json.JSONDecodeError:
            triggering = []

        try:
            readme = readme_path.read_text()
        except FileNotFoundError:
            readme = ""
            warnings.append(f"missing README.md at {readme_path}")

        if readme and triggering:
            sibling_entries = rae.parse_sibling_map(readme)
            if not sibling_entries:
                warnings.append(
                    "sibling map empty — missing SIBLING_MAP markers or unparseable bullets"
                )
            _, _, unmatched = rae.build_index_to_sibling(sibling_entries, triggering)
            if unmatched:
                warnings.append(
                    f"sibling map does not attribute negative indices: {sorted(unmatched)}"
                )

        if warnings:
            any_fail = True
            print(f"✗ {skill}")
            for w in warnings:
                print(f"    - {w}")
        else:
            print(f"✓ {skill}")

    if any_fail:
        print("\nHygiene check failed. Fix the warnings above before merging.", file=sys.stderr)
        return 1

    print("\nAll skills pass hygiene.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
