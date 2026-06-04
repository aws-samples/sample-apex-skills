#!/usr/bin/env python3
"""Generate misc/website/static/manifests/evals.json from all baseline.json files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_ROOT.parent.parent
OUTPUT_PATH = REPO_ROOT / "misc" / "website" / "static" / "manifests" / "evals.json"

ALL_LAYERS = ("triggering", "process", "artifact", "knowledge", "quality")
EXCLUDED_SKILLS = {"update-docs", "steering-workflow-creator"}


def round1(val: float | None) -> float | None:
    """Round to 1 decimal place, or return None."""
    if val is None:
        return None
    return round(val, 1)


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
        "effective_weights": composite.get("effective_weights", {}),
        "layers": layers,
    }


def main() -> None:
    baselines = sorted(EVALS_ROOT.glob("*/baselines/baseline.json"))

    if not baselines:
        print("No baseline.json files found", file=sys.stderr)
        sys.exit(1)

    entries = [extract_entry(p) for p in baselines if p.parent.parent.name not in EXCLUDED_SKILLS]
    entries.sort(key=lambda e: e["score"] or 0, reverse=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(entries, indent=2) + "\n")

    print(f"Generated evals.json: {len(entries)} skills", file=sys.stderr)


if __name__ == "__main__":
    main()
