#!/usr/bin/env python3
"""Generate misc/website/static/manifests/evals.json from all baseline.json files.

Each entry's tokens_per_run is the with_skill arm's mean tokens per run
(skill_summary.arms.with_skill.tokens_per_run_mean) in the latest kind
"task" row of misc/evals/history/<skill>.jsonl run on the claude harness
(a row with no harness field is claude), the only committed place the task
runner records tokens (baseline.json carries none); null when that row has no
per-skill summary (older rows), its mean is null (no run recorded a token
count) or there is no such row. A history line that is not a JSON object
is skipped with a warning.

--check builds the same content and compares it with the committed file:
exit 0 when they match, 1 when they differ or the file is missing. It
writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_ROOT.parent.parent
OUTPUT_PATH = REPO_ROOT / "misc" / "website" / "static" / "manifests" / "evals.json"
HISTORY_DIR = EVALS_ROOT / "history"

ALL_LAYERS = ("triggering", "process", "artifact", "knowledge", "quality")
EXCLUDED_SKILLS = {"update-docs"}


def round1(val: float | None) -> float | None:
    """Round to 1 decimal place, or return None."""
    if val is None:
        return None
    return round(val, 1)


def latest_task_row(skill: str) -> dict | None:
    """The skill's latest kind "task" history row run on the claude harness.
    A row with no harness field is claude: run_task_evals.py wrote rows
    before it had other harnesses without one."""
    path = HISTORY_DIR / f"{skill}.jsonl"
    if not path.exists():
        return None
    for line in reversed(path.read_text().splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        if not isinstance(row, dict):
            print(f"warning: {path}: skipping a line that is not a JSON object", file=sys.stderr)
            continue
        if row.get("kind") == "task" and row.get("harness", "claude") == "claude":
            return row
    return None


def tokens_per_run(skill: str) -> int | None:
    """Mean tokens per with_skill run from the skill's latest claude task row."""
    arms = ((latest_task_row(skill) or {}).get("skill_summary") or {}).get("arms") or {}
    value = (arms.get("with_skill") or {}).get("tokens_per_run_mean")
    return round(value) if isinstance(value, (int, float)) else None


def extract_entry(baseline_path: Path) -> dict:
    """Extract manifest entry from a single baseline.json."""
    data = json.loads(baseline_path.read_text())

    composite = data.get("composite", {})
    contributions = composite.get("contributions", {})

    layers = {}
    for layer in ALL_LAYERS:
        if layer in contributions:
            c = contributions[layer]
            layers[layer] = {
                "raw_score": round1(c.get("raw_score")),
                "weight": round1(c.get("weight", 0)),
                "contribution": round1(c.get("contribution", 0)),
            }
        else:
            layers[layer] = {"raw_score": None, "weight": 0, "contribution": 0}

    task = data.get("task") or {}

    return {
        "skill": data["skill"],
        "score": round1(composite.get("score", 0)),
        "grade": composite.get("grade", "F"),
        "created_at": data.get("created_at"),
        "model": data.get("model"),
        "git_head": data.get("git_head"),
        "pass_k_rate": task.get("pass_k_rate"),
        "tokens_per_run": tokens_per_run(data["skill"]),
        "effective_weights": composite.get("effective_weights", {}),
        "layers": layers,
    }


def build_manifest() -> list[dict]:
    baselines = sorted(EVALS_ROOT.glob("*/baselines/baseline.json"))
    if not baselines:
        print("No baseline.json files found", file=sys.stderr)
        sys.exit(1)
    entries = [extract_entry(p) for p in baselines if p.parent.parent.name not in EXCLUDED_SKILLS]
    entries.sort(key=lambda e: e["score"] or 0, reverse=True)
    return entries


def check(entries: list[dict]) -> int:
    """Compare with the committed file; name each entry that differs."""
    want = json.dumps(entries, indent=2) + "\n"
    try:
        have = OUTPUT_PATH.read_text()
    except OSError as e:
        print(f"evals.json check: cannot read {OUTPUT_PATH} ({e.strerror})", file=sys.stderr)
        return 1
    if have == want:
        print(f"evals.json check: up to date ({len(entries)} skills)", file=sys.stderr)
        return 0
    try:
        old = {e.get("skill"): e for e in json.loads(have) if isinstance(e, dict)}
    except ValueError:
        old = {}
    new = {e["skill"]: e for e in entries}
    for skill in sorted(set(old) | set(new)):
        o, n = old.get(skill), new.get(skill)
        if o is None or n is None:
            print(f"  {skill}: {'not in the committed file' if o is None else 'no longer generated'}",
                  file=sys.stderr)
        elif o != n:
            keys = sorted(k for k in set(o) | set(n) if o.get(k) != n.get(k) or (k in o) != (k in n))
            print(f"  {skill}: differs in {', '.join(keys)}", file=sys.stderr)
    print(f"evals.json check: {OUTPUT_PATH} is out of date; run "
          "`make -C misc/evals eval-manifest` and commit it", file=sys.stderr)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="Compare with the committed evals.json; exit 1 on a difference; write nothing.")
    args = parser.parse_args()

    entries = build_manifest()
    if args.check:
        sys.exit(check(entries))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(entries, indent=2) + "\n")

    print(f"Generated evals.json: {len(entries)} skills", file=sys.stderr)


if __name__ == "__main__":
    main()
