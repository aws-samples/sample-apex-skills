#!/usr/bin/env python3
"""Standalone process-assertion runner (deterministic, no LLM calls).

Replays existing events.jsonl files from a skill's workspace/latest/ directory
through the assertion engine. Useful for re-evaluating after changing assertions
without re-running the subject.

Exit codes:
  0  all assertions across all runs passed
  1  at least one assertion failed
  2  invalid inputs or no run data found
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parse_trajectory import parse_events_file
from process_assertions import evaluate

EVALS_ROOT = Path(__file__).resolve().parent.parent


def find_run_dirs(skill: str, workspace: Path | None = None) -> list[Path]:
    """Find all run directories under the skill's workspace/latest/."""
    if workspace:
        base = workspace
    else:
        latest = EVALS_ROOT / skill / "workspace" / "latest"
        if latest.is_symlink() or latest.exists():
            base = latest.resolve()
        else:
            return []

    run_dirs: list[Path] = []
    for events_file in sorted(base.rglob("events.jsonl")):
        run_dirs.append(events_file.parent)
    return run_dirs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skill", required=True, help="Skill name")
    parser.add_argument("--workspace", default=None,
                        help="Override workspace path (default: <skill>/workspace/latest/)")
    args = parser.parse_args()

    evals_json_path = EVALS_ROOT / args.skill / "evals.json"
    if not evals_json_path.exists():
        print(f"missing: {evals_json_path}", file=sys.stderr)
        return 2

    evals_data = json.loads(evals_json_path.read_text())
    prompts = evals_data.get("evals") or []

    assertions_by_id: dict[int, list[dict]] = {}
    for p in prompts:
        pa = p.get("process_assertions")
        if pa:
            assertions_by_id[p["id"]] = pa

    if not assertions_by_id:
        print(f"[process] {args.skill}: no process_assertions defined in evals.json", file=sys.stderr)
        return 0

    workspace = Path(args.workspace) if args.workspace else None
    run_dirs = find_run_dirs(args.skill, workspace)
    if not run_dirs:
        print(f"[process] {args.skill}: no run data found (run `make task-{args.skill}` first)", file=sys.stderr)
        return 2

    any_failed = False
    total_passed = 0
    total_assertions = 0

    for run_dir in run_dirs:
        events_file = run_dir / "events.jsonl"
        metadata_file = run_dir.parent.parent / "eval_metadata.json"
        if not metadata_file.exists():
            continue

        metadata = json.loads(metadata_file.read_text())
        eval_id = metadata.get("eval_id")
        if eval_id not in assertions_by_id:
            continue

        rel = run_dir.relative_to(EVALS_ROOT / args.skill / "workspace")
        trajectory = parse_events_file(events_file)
        results = evaluate(trajectory, assertions_by_id[eval_id])

        (run_dir / "process-assertions.json").write_text(
            json.dumps(results.to_dict(), indent=2)
        )

        status = "PASS" if results.failed == 0 else "FAIL"
        if results.failed > 0:
            any_failed = True
        total_passed += results.passed
        total_assertions += results.total

        print(
            f"[process] {args.skill} {rel}: {status} "
            f"({results.passed}/{results.total})",
            file=sys.stderr,
        )
        if results.failure_classes:
            for fc, count in sorted(results.failure_classes.items()):
                print(f"[process]   {fc}: {count}", file=sys.stderr)

    if total_assertions == 0:
        print(f"[process] {args.skill}: no matching eval runs found for configured assertions", file=sys.stderr)
        return 2

    print(
        f"[process] {args.skill} TOTAL: {total_passed}/{total_assertions} "
        f"({'PASS' if not any_failed else 'FAIL'})",
        file=sys.stderr,
    )
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
