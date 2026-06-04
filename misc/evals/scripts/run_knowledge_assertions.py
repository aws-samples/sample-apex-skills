#!/usr/bin/env python3
"""Standalone knowledge-assertion runner (deterministic, no LLM calls).

Replays existing events.jsonl files from a skill's workspace/latest/ directory,
extracts all assistant text output, and evaluates knowledge assertions against it.

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

from knowledge_assertions import evaluate

EVALS_ROOT = Path(__file__).resolve().parent.parent

# File extensions considered text-readable for output artifact scanning
_TEXT_EXTENSIONS = {
    ".tf", ".md", ".yaml", ".yml", ".json", ".hcl", ".toml",
    ".txt", ".mmd", ".py", ".sh", ".bash", ".zsh", ".ts", ".js",
    ".html", ".css", ".xml", ".csv", ".ini", ".cfg", ".conf",
    ".gitignore", ".env", ".tfvars",
}


def extract_assistant_text(events_path: Path) -> str:
    """Extract all assistant text content from an events.jsonl file."""
    texts: list[str] = []
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") != "assistant":
                continue
            msg = evt.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        texts.append(text)
    return "\n\n".join(texts)


def extract_output_files_text(outputs_dir: Path) -> str:
    """Read all text files from the outputs/ directory and return concatenated content.

    Skips binary files and handles encoding errors gracefully.
    """
    if not outputs_dir.is_dir():
        return ""

    texts: list[str] = []
    for filepath in sorted(outputs_dir.rglob("*")):
        if not filepath.is_file():
            continue
        # Skip files that are clearly binary based on extension
        suffix = filepath.suffix.lower()
        # Allow extensionless files (like .gitignore) if name starts with dot
        if suffix and suffix not in _TEXT_EXTENSIONS:
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore").strip()
            if content:
                texts.append(content)
        except (OSError, PermissionError):
            continue
    return "\n\n".join(texts)


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
        ka = p.get("knowledge_assertions")
        if ka:
            assertions_by_id[p["id"]] = ka

    if not assertions_by_id:
        print(f"[knowledge] {args.skill}: no knowledge_assertions defined in evals.json", file=sys.stderr)
        return 0

    workspace = Path(args.workspace) if args.workspace else None
    run_dirs = find_run_dirs(args.skill, workspace)
    if not run_dirs:
        print(f"[knowledge] {args.skill}: no run data found (run `make task-{args.skill}` first)", file=sys.stderr)
        return 2

    any_failed = False
    total_passed = 0
    total_failed = 0
    total_skipped = 0
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
        assistant_text = extract_assistant_text(events_file)
        outputs_text = extract_output_files_text(run_dir / "outputs")
        text = "\n\n".join(filter(None, [assistant_text, outputs_text]))
        if not text:
            print(f"[knowledge] {args.skill} {rel}: SKIP (no assistant text or output files)", file=sys.stderr)
            continue

        results = evaluate(text, assertions_by_id[eval_id])

        (run_dir / "knowledge-assertions.json").write_text(
            json.dumps(results.to_dict(), indent=2)
        )

        status = "PASS" if results.failed == 0 else "FAIL"
        if results.failed > 0:
            any_failed = True
        total_passed += results.passed
        total_failed += results.failed
        total_skipped += results.skipped
        total_assertions += results.total

        # Build summary line with score
        score_str = f"{results.pass_rate:.0%}" if results.pass_rate < 1.0 else "100%"
        skipped_str = f", {results.skipped} skipped" if results.skipped > 0 else ""
        print(
            f"[knowledge] {args.skill} {rel}: {status} "
            f"({results.passed}/{results.total - results.skipped} evaluated{skipped_str}, score={score_str})",
            file=sys.stderr,
        )

        # Report group-level results
        if results.groups:
            for gr in results.groups:
                gr_status = "PASS" if gr.failed == 0 else "FAIL"
                gr_skipped_str = f", {gr.skipped} skipped" if gr.skipped > 0 else ""
                print(
                    f"[knowledge]   group '{gr.name}': {gr_status} "
                    f"({gr.passed}/{gr.passed + gr.failed} evaluated{gr_skipped_str}, "
                    f"score={gr.score:.0%}, weight={gr.weight})",
                    file=sys.stderr,
                )

        if results.failure_classes:
            for fc, count in sorted(results.failure_classes.items()):
                print(f"[knowledge]   {fc}: {count}", file=sys.stderr)

    if total_assertions == 0:
        print(f"[knowledge] {args.skill}: no matching eval runs found for configured assertions", file=sys.stderr)
        return 2

    evaluated_total = total_assertions - total_skipped
    skipped_summary = f", {total_skipped} skipped" if total_skipped > 0 else ""
    print(
        f"[knowledge] {args.skill} TOTAL: {total_passed}/{evaluated_total} evaluated{skipped_summary} "
        f"({'PASS' if not any_failed else 'FAIL'})",
        file=sys.stderr,
    )
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
