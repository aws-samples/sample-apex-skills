"""Gather eval layer scores and write baselines/baseline.json for a skill."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from composite_score import compute_from_baseline
from skilleval_config import load_config

EVALS_ROOT = Path(__file__).resolve().parent.parent  # misc/evals/
REPO_ROOT = EVALS_ROOT.parent.parent


def find_latest_metrics(skill: str) -> dict[str, Any]:
    runs_dir = EVALS_ROOT / skill / "workspace" / "runs"
    if not runs_dir.is_dir():
        sys.exit(f"Error: runs directory not found: {runs_dir}")
    run_dirs = sorted([d for d in runs_dir.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True)
    for d in run_dirs:
        metrics_path = d / "metrics.json"
        if metrics_path.exists():
            return json.loads(metrics_path.read_text())
    sys.exit(f"Error: no metrics.json found in {runs_dir}")


def extract_triggering(metrics: dict[str, Any]) -> dict[str, Any]:
    overall = metrics["overall"]
    positive = metrics["positive"]
    negative = metrics["negative"]
    tpr = positive["passed"] / positive["total"] if positive["total"] > 0 else 0.0
    tnr = negative["passed"] / negative["total"] if negative["total"] > 0 else 0.0
    return {
        "accuracy": overall["accuracy"],
        "ci_lo": overall["ci_lo"],
        "ci_hi": overall["ci_hi"],
        "tpr": tpr,
        "tnr": tnr,
        "flake_count": metrics.get("flake_count", 0),
    }


def read_task_benchmark(skill: str, pass_k: int) -> Optional[dict[str, Any]]:
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    bench_path = latest / "benchmark.json"
    if not bench_path.exists():
        return None
    bench = json.loads(bench_path.read_text())
    run_summary = bench["run_summary"]
    with_skill = run_summary["with_skill"]["pass_rate"]
    without_skill = run_summary["without_skill"]["pass_rate"]
    runs_per = bench["metadata"]["runs_per_configuration"]
    pass_k_rate = compute_pass_k(latest, pass_k)
    return {
        "with_skill_mean": with_skill["mean"],
        "with_skill_stddev": with_skill["stddev"],
        "without_skill_mean": without_skill["mean"],
        "pass_k_rate": pass_k_rate,
        "runs_per_prompt": runs_per,
    }


def compute_pass_k(latest: Path, k: int) -> Optional[float]:
    resolved = latest.resolve()
    eval_dirs: dict[str, list[Path]] = {}
    for grading in sorted(resolved.glob("eval-*/with_skill/run-*/grading.json")):
        eval_name = grading.parent.parent.parent.name
        eval_dirs.setdefault(eval_name, []).append(grading)
    if not eval_dirs:
        return None
    passing = 0
    eligible = 0
    for eval_name, gradings in eval_dirs.items():
        gradings_sorted = sorted(gradings, key=lambda p: p.parent.name)[:k]
        if len(gradings_sorted) < k:
            continue
        eligible += 1
        all_pass = all(json.loads(g.read_text())["summary"]["pass_rate"] == 1.0 for g in gradings_sorted)
        if all_pass:
            passing += 1
    if eligible == 0:
        print(f"Warning: no evals have >= {k} runs for pass^k", file=sys.stderr)
        return None
    return passing / eligible


def aggregate_json_files(skill: str, pattern: str, extract_fn) -> Optional[dict[str, Any]]:
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    files = list(latest.rglob(f"with_skill/run-*/{pattern}"))
    if not files:
        return None
    total_passed = 0
    total_total = 0
    for f in files:
        data = json.loads(f.read_text())
        passed, total = extract_fn(data)
        total_passed += passed
        total_total += total
    pass_rate = total_passed / total_total if total_total > 0 else 0.0
    return {"pass_rate": pass_rate, "passed": total_passed, "total": total_total}


def extract_process_assertions(data: dict[str, Any]) -> tuple[int, int]:
    return data["passed"], data["total"]


def extract_artifact_validation(data: dict[str, Any]) -> tuple[int, int]:
    s = data["summary"]
    passed = s["structural_passed"] + s["validators_passed"]
    total = s["structural_passed"] + s["structural_failed"] + s["validators_passed"] + s["validators_failed"]
    return passed, total


def extract_knowledge_assertions(data: dict[str, Any]) -> tuple[int, int]:
    return data["passed"], data["total"]


def gather_per_eval_cases(skill: str) -> dict[str, dict[str, Any]]:
    """Collect per-eval-case scores for each assertion layer.

    Returns a dict keyed by eval case name (e.g. "eval-1") with per-layer scores:
    {
      "eval-1": {
        "knowledge_assertions": {"pass_rate": 1.0, "passed": 8, "total": 8},
        "process_assertions": {"pass_rate": 0.8, "passed": 4, "total": 5},
        "artifact_validation": {"pass_rate": 0.85, "passed": 11, "total": 13},
      },
      ...
    }
    """
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    if not latest.exists():
        return {}

    resolved = latest.resolve()
    cases: dict[str, dict[str, Any]] = {}

    # Find all eval-* directories
    eval_dirs = sorted(d for d in resolved.iterdir() if d.is_dir() and d.name.startswith("eval-"))

    layer_configs = [
        ("knowledge_assertions", "knowledge-assertions.json", extract_knowledge_assertions),
        ("process_assertions", "process-assertions.json", extract_process_assertions),
        ("artifact_validation", "artifact-validation.json", extract_artifact_validation),
    ]

    for eval_dir in eval_dirs:
        case_name = eval_dir.name
        case_data: dict[str, Any] = {}

        for layer_key, filename, extract_fn in layer_configs:
            # Aggregate across all runs within with_skill for this eval case
            files = list(eval_dir.rglob(f"with_skill/run-*/{filename}"))
            if not files:
                continue
            total_passed = 0
            total_total = 0
            for f in files:
                data = json.loads(f.read_text())
                passed, total = extract_fn(data)
                total_passed += passed
                total_total += total
            if total_total > 0:
                case_data[layer_key] = {
                    "pass_rate": total_passed / total_total,
                    "passed": total_passed,
                    "total": total_total,
                }

        if case_data:
            cases[case_name] = case_data

    return cases


def compute_eval_set_hash(skill: str) -> Optional[str]:
    """SHA-256 of the skill's evals.json (normalized with sorted keys)."""
    evals_path = EVALS_ROOT / skill / "evals.json"
    if not evals_path.exists():
        return None
    data = json.loads(evals_path.read_text())
    normalized = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(normalized).hexdigest()


def get_git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    parser.add_argument("--pass-k", type=int, default=3)
    args = parser.parse_args()

    skill = args.skill
    pass_k = args.pass_k

    metrics = find_latest_metrics(skill)
    triggering = extract_triggering(metrics)

    snapshot_meta = metrics.get("snapshot", {})
    model = snapshot_meta.get("model", "unknown")

    task = read_task_benchmark(skill, pass_k)
    process = aggregate_json_files(skill, "process-assertions.json", extract_process_assertions)
    artifact = aggregate_json_files(skill, "artifact-validation.json", extract_artifact_validation)
    knowledge = aggregate_json_files(skill, "knowledge-assertions.json", extract_knowledge_assertions)

    git_head = get_git_head()
    eval_set_hash = compute_eval_set_hash(skill)
    per_eval_cases = gather_per_eval_cases(skill)

    baseline = {
        "version": 2,
        "skill": skill,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head,
        "eval_set_hash": eval_set_hash,
        "model": model,
        "pass_k": pass_k,
        "triggering": triggering,
        "task": task,
        "process_assertions": process,
        "artifact_validation": artifact,
        "knowledge_assertions": knowledge,
        "per_eval_cases": per_eval_cases if per_eval_cases else None,
        "composite": None,
    }

    config = load_config(skill)
    composite_result = compute_from_baseline(baseline, config)
    if composite_result:
        baseline["composite"] = {
            "score": composite_result["score"],
            "grade": composite_result["grade"],
            "contributions": composite_result["contributions"],
            "effective_weights": composite_result["effective_weights"],
        }

    baselines_dir = EVALS_ROOT / skill / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    out_path = baselines_dir / "baseline.json"
    out_path.write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"Baseline written: {out_path}")


if __name__ == "__main__":
    main()
