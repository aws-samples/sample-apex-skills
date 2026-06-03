#!/usr/bin/env python3
"""Standalone artifact-validation runner (deterministic, no LLM calls).

Validates files in existing outputs/ directories from a skill's workspace/latest/
against artifact_assertions declared in evals.json.

Exit codes:
  0  all assertions and validators passed (or skipped)
  1  at least one assertion or validator failed
  2  invalid inputs or no run data found
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from artifact_validation import validate_run, ArtifactValidationResults

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
    for outputs_dir in sorted(base.rglob("outputs")):
        if outputs_dir.is_dir():
            run_dirs.append(outputs_dir.parent)
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

    assertions_by_id: dict[int, dict] = {}
    for p in prompts:
        aa = p.get("artifact_assertions")
        if aa:
            assertions_by_id[p["id"]] = aa

    if not assertions_by_id:
        print(f"[artifact] {args.skill}: no artifact_assertions defined in evals.json", file=sys.stderr)
        return 0

    workspace = Path(args.workspace) if args.workspace else None
    run_dirs = find_run_dirs(args.skill, workspace)
    if not run_dirs:
        print(f"[artifact] {args.skill}: no run data found (run `make task-{args.skill}` first)", file=sys.stderr)
        return 2

    repo_root = EVALS_ROOT.parent.parent
    any_failed = False
    total_passed = 0
    total_failed = 0
    runs_validated = 0

    for run_dir in run_dirs:
        outputs_dir = run_dir / "outputs"
        if not outputs_dir.exists():
            continue

        metadata_file = run_dir.parent.parent / "eval_metadata.json"
        if not metadata_file.exists():
            continue

        metadata = json.loads(metadata_file.read_text())
        eval_id = metadata.get("eval_id")
        if eval_id not in assertions_by_id:
            continue

        rel = run_dir.relative_to(EVALS_ROOT / args.skill / "workspace")

        results = validate_run(
            outputs_dir=outputs_dir,
            assertions_config=assertions_by_id[eval_id],
            repo_root=repo_root,
        )

        (run_dir / "artifact-validation.json").write_text(
            json.dumps(results.to_dict(), indent=2)
        )

        runs_validated += 1
        run_passed = results.structural_passed + results.validators_passed
        run_failed = results.structural_failed + results.validators_failed
        total_passed += run_passed
        total_failed += run_failed

        status = "PASS" if run_failed == 0 else "FAIL"
        if run_failed > 0:
            any_failed = True

        print(
            f"[artifact] {args.skill} {rel}: {status} "
            f"(structural: {results.structural_passed}/{results.structural_passed + results.structural_failed}, "
            f"validators: {results.validators_passed}/{results.validators_passed + results.validators_failed}) "
            f"root={results.artifact_root}",
            file=sys.stderr,
        )

        for r in results.structural_results:
            if r.status == "failed":
                print(f"[artifact]   FAIL: {r.assertion.get('type')}: {r.evidence}", file=sys.stderr)
        for r in results.validator_results:
            if r.status == "failed":
                print(f"[artifact]   FAIL: {r.validator.get('type')}: {r.detail[:120]}", file=sys.stderr)

    if runs_validated == 0:
        print(f"[artifact] {args.skill}: no matching eval runs found for configured assertions", file=sys.stderr)
        return 2

    total = total_passed + total_failed
    rate = total_passed / total if total else 1.0
    print(
        f"[artifact] {args.skill} TOTAL: {total_passed}/{total} "
        f"({rate:.0%}) {'PASS' if not any_failed else 'FAIL'}",
        file=sys.stderr,
    )
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
