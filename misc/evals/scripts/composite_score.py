"""Compute composite score from 5 eval layers and assign letter grade.

Layer scores are normalized to 0.0–1.0 before weighting:
  - Triggering: TPR × TNR (existing formula)
  - Process: assertions_passed / assertions_total
  - Artifact: validators_passed / validators_total
  - Knowledge: assertions_passed / assertions_total
  - Quality: grader_pass_rate (existing)

Composite = weighted sum × 100 → letter grade.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from skilleval_config import DEFAULT_WEIGHTS, SkillEvalConfig, load_config, score_to_grade

EVALS_ROOT = Path(__file__).resolve().parent.parent


def extract_layer_score(layer: str, data: Optional[dict[str, Any]]) -> Optional[float]:
    """Extract a 0.0–1.0 score from a layer's data dict.

    Returns None if the layer has no data (skipped).
    """
    if data is None:
        return None

    if layer == "triggering":
        tpr = data.get("tpr")
        tnr = data.get("tnr")
        if tpr is None or tnr is None:
            return data.get("accuracy")
        return tpr * tnr

    if layer == "quality":
        return data.get("pass_rate", data.get("grader_pass_rate"))

    return data.get("pass_rate")


def compute_composite(
    layer_scores: dict[str, Optional[float]],
    config: SkillEvalConfig,
) -> Optional[dict[str, Any]]:
    """Compute weighted composite score with redistribution.

    Returns dict with: score (0-100), grade, per-layer contributions, effective weights.
    Returns None if no layers have scores.
    """
    effective_weights = config.effective_weights()

    available = {k: v for k, v in layer_scores.items() if v is not None and k in effective_weights}
    if not available:
        return None

    missing_in_available = {k for k in effective_weights if k not in available}
    if missing_in_available:
        available_total = sum(effective_weights[k] for k in available)
        if available_total == 0:
            return None
        scale = 1.0 / available_total
        weights_final = {k: effective_weights[k] * scale for k in available}
    else:
        weights_final = effective_weights

    weighted_sum = sum(layer_scores[k] * weights_final[k] for k in available)
    score = weighted_sum * 100

    contributions = {}
    for k in available:
        contributions[k] = {
            "raw_score": layer_scores[k],
            "weight": weights_final[k],
            "contribution": layer_scores[k] * weights_final[k] * 100,
        }

    return {
        "score": round(score, 1),
        "grade": score_to_grade(score),
        "contributions": contributions,
        "effective_weights": weights_final,
        "layers_available": list(available.keys()),
        "layers_missing": list(missing_in_available),
    }


def compute_from_workspace(skill: str, config: Optional[SkillEvalConfig] = None) -> Optional[dict[str, Any]]:
    """Compute composite score from workspace data for a skill."""
    if config is None:
        config = load_config(skill)

    latest = EVALS_ROOT / skill / "workspace" / "latest"
    runs_dir = EVALS_ROOT / skill / "workspace" / "runs"

    layer_scores: dict[str, Optional[float]] = {}

    triggering_data = None
    if runs_dir.is_dir():
        for d in sorted([d for d in runs_dir.iterdir() if d.is_dir()], key=lambda x: x.name, reverse=True):
            mp = d / "metrics.json"
            if mp.exists():
                m = json.loads(mp.read_text())
                pos, neg = m["positive"], m["negative"]
                triggering_data = {
                    "tpr": pos["passed"] / pos["total"] if pos["total"] > 0 else 0.0,
                    "tnr": neg["passed"] / neg["total"] if neg["total"] > 0 else 0.0,
                }
                break
    layer_scores["triggering"] = extract_layer_score("triggering", triggering_data)

    if latest.exists():
        resolved = latest.resolve()

        process_files = list(resolved.rglob("with_skill/run-*/process-assertions.json"))
        if process_files:
            tp = tt = 0
            for f in process_files:
                d = json.loads(f.read_text())
                tp += d["passed"]
                tt += d["total"]
            layer_scores["process"] = tp / tt if tt > 0 else None
        else:
            layer_scores["process"] = None

        artifact_files = list(resolved.rglob("with_skill/run-*/artifact-validation.json"))
        if artifact_files:
            tp = tt = 0
            for f in artifact_files:
                s = json.loads(f.read_text())["summary"]
                tp += s["structural_passed"] + s["validators_passed"]
                tt += s["structural_passed"] + s["structural_failed"] + s["validators_passed"] + s["validators_failed"]
            layer_scores["artifact"] = tp / tt if tt > 0 else None
        else:
            layer_scores["artifact"] = None

        knowledge_files = list(resolved.rglob("with_skill/run-*/knowledge-assertions.json"))
        if knowledge_files:
            tp = tt = 0
            for f in knowledge_files:
                d = json.loads(f.read_text())
                tp += d["passed"]
                tt += d["total"]
            layer_scores["knowledge"] = tp / tt if tt > 0 else None
        else:
            layer_scores["knowledge"] = None

        bench_path = resolved / "benchmark.json"
        if bench_path.exists():
            bench = json.loads(bench_path.read_text())
            ws_rate = bench["run_summary"]["with_skill"]["pass_rate"]["mean"]
            layer_scores["quality"] = ws_rate
        else:
            layer_scores["quality"] = None
    else:
        layer_scores["process"] = None
        layer_scores["artifact"] = None
        layer_scores["knowledge"] = None
        layer_scores["quality"] = None

    return compute_composite(layer_scores, config)


def compute_from_baseline(baseline: dict[str, Any], config: Optional[SkillEvalConfig] = None) -> Optional[dict[str, Any]]:
    """Compute composite score from a baseline.json dict."""
    skill = baseline.get("skill", "unknown")
    if config is None:
        config = load_config(skill)

    layer_scores: dict[str, Optional[float]] = {}
    layer_scores["triggering"] = extract_layer_score("triggering", baseline.get("triggering"))
    layer_scores["process"] = extract_layer_score("process", baseline.get("process_assertions"))
    layer_scores["artifact"] = extract_layer_score("artifact", baseline.get("artifact_validation"))
    layer_scores["knowledge"] = extract_layer_score("knowledge", baseline.get("knowledge_assertions"))

    task_data = baseline.get("task")
    if task_data and "with_skill_mean" in task_data:
        layer_scores["quality"] = task_data["with_skill_mean"]
    else:
        layer_scores["quality"] = None

    return compute_composite(layer_scores, config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute composite score for a skill")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--from-baseline", action="store_true", help="Compute from baseline.json instead of workspace")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    config = load_config(args.skill)

    if args.from_baseline:
        baseline_path = EVALS_ROOT / args.skill / "baselines" / "baseline.json"
        if not baseline_path.exists():
            sys.exit(f"Error: no baseline for {args.skill}")
        baseline = json.loads(baseline_path.read_text())
        result = compute_from_baseline(baseline, config)
    else:
        result = compute_from_workspace(args.skill, config)

    if result is None:
        print(f"No layer scores available for {args.skill}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"  {args.skill}: {result['grade']} ({result['score']})")
        print(f"{'='*50}")
        print(f"\n  Layer breakdown:")
        for layer, contrib in result["contributions"].items():
            bar_len = int(contrib["raw_score"] * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"    {layer:<12} {bar} {contrib['raw_score']*100:5.1f}% (w={contrib['weight']:.2f}, +{contrib['contribution']:.1f})")
        if result["layers_missing"]:
            print(f"\n  Skipped (no data): {', '.join(result['layers_missing'])}")
        print()


if __name__ == "__main__":
    main()
