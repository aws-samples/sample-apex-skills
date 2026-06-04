"""Compare committed baseline against current scores and gate CI on regressions."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from composite_score import compute_from_baseline, compute_from_workspace
from skilleval_config import load_config
from snapshot import compute_eval_set_hash

EVALS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_ROOT.parent.parent
HISTORY_DIR = EVALS_ROOT / "history"

LAYERS = ["triggering", "task", "process_assertions", "artifact_validation", "knowledge_assertions"]
LAYER_LABELS = {"triggering": "Triggering", "task": "Task", "process_assertions": "Process",
                "artifact_validation": "Artifact", "knowledge_assertions": "Knowledge"}
PRIMARY_FIELD = {"triggering": "accuracy", "task": "with_skill_mean", "process_assertions": "pass_rate",
                 "artifact_validation": "pass_rate", "knowledge_assertions": "pass_rate"}
# Layers that support per-eval-case drill-down
DRILLDOWN_LAYERS = ["knowledge_assertions", "process_assertions", "artifact_validation"]
LAYER_FILENAME = {"knowledge_assertions": "knowledge-assertions.json",
                  "process_assertions": "process-assertions.json",
                  "artifact_validation": "artifact-validation.json"}


def get_git_head() -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT)
    return r.stdout.strip()


def compute_pass_k(latest: Path, k: int) -> Optional[float]:
    resolved = latest.resolve()
    eval_dirs: dict[str, list[Path]] = {}
    for grading in sorted(resolved.glob("eval-*/with_skill/run-*/grading.json")):
        eval_dirs.setdefault(grading.parent.parent.parent.name, []).append(grading)
    if not eval_dirs:
        return None
    passing = eligible = 0
    for gradings in eval_dirs.values():
        gs = sorted(gradings, key=lambda p: p.parent.name)[:k]
        if len(gs) < k:
            continue
        eligible += 1
        if all(json.loads(g.read_text())["summary"]["pass_rate"] == 1.0 for g in gs):
            passing += 1
    return passing / eligible if eligible else None


def load_baseline(skill: str) -> Optional[dict[str, Any]]:
    path = EVALS_ROOT / skill / "baselines" / "baseline.json"
    if not path.exists():
        return None
    baseline = json.loads(path.read_text())
    if baseline.get("version") not in (1, 2):
        sys.exit(f"Error: unsupported baseline version in {path}")
    return baseline


def _aggregate(latest: Path, pattern: str, extract_fn) -> Optional[dict[str, Any]]:
    files = list(latest.rglob(pattern))
    if not files:
        return None
    tp = tt = 0
    for f in files:
        p, t = extract_fn(json.loads(f.read_text()))
        tp += p
        tt += t
    return {"pass_rate": tp / tt if tt > 0 else 0.0, "passed": tp, "total": tt}


def _extract_knowledge(d: dict[str, Any]) -> tuple[int, int]:
    return d["passed"], d["total"]


def _extract_process(d: dict[str, Any]) -> tuple[int, int]:
    return d["passed"], d["total"]


def _extract_artifact(d: dict[str, Any]) -> tuple[int, int]:
    s = d["summary"]
    passed = s["structural_passed"] + s["validators_passed"]
    total = (s["structural_passed"] + s["structural_failed"]
             + s["validators_passed"] + s["validators_failed"])
    return passed, total


_LAYER_EXTRACT = {
    "knowledge_assertions": _extract_knowledge,
    "process_assertions": _extract_process,
    "artifact_validation": _extract_artifact,
}


def gather_per_eval_cases(latest: Path) -> dict[str, dict[str, Any]]:
    """Collect per-eval-case scores from workspace for drilldown layers.

    Returns: {"eval-1": {"knowledge_assertions": {"pass_rate": ..., "passed": ..., "total": ...}}, ...}
    """
    resolved = latest.resolve()
    cases: dict[str, dict[str, Any]] = {}

    eval_dirs = sorted(d for d in resolved.iterdir() if d.is_dir() and d.name.startswith("eval-"))

    for eval_dir in eval_dirs:
        case_name = eval_dir.name
        case_data: dict[str, Any] = {}

        for layer_key in DRILLDOWN_LAYERS:
            filename = LAYER_FILENAME[layer_key]
            extract_fn = _LAYER_EXTRACT[layer_key]
            files = list(eval_dir.rglob(f"with_skill/run-*/{filename}"))
            if not files:
                continue
            tp = tt = 0
            for f in files:
                data = json.loads(f.read_text())
                p, t = extract_fn(data)
                tp += p
                tt += t
            if tt > 0:
                case_data[layer_key] = {"pass_rate": tp / tt, "passed": tp, "total": tt}

        if case_data:
            cases[case_name] = case_data

    return cases


def gather_failed_assertions(latest: Path, layer: str, case_name: str) -> list[dict[str, Any]]:
    """Return failed assertion details for a specific eval case and layer.

    For traceability: reports which specific assertions failed.
    """
    resolved = latest.resolve()
    eval_dir = resolved / case_name
    if not eval_dir.is_dir():
        return []

    filename = LAYER_FILENAME.get(layer)
    if not filename:
        return []

    failed: list[dict[str, Any]] = []
    files = list(eval_dir.rglob(f"with_skill/run-*/{filename}"))

    for f in files:
        data = json.loads(f.read_text())
        run_name = f.parent.name  # e.g. "run-1"

        if layer == "knowledge_assertions":
            for r in data.get("results", []):
                if not r.get("passed", True):
                    assertion = r.get("assertion", {})
                    atype = assertion.get("type", "unknown")
                    pattern = assertion.get("pattern", assertion.get("patterns", ["?"])[0] if "patterns" in assertion else "?")
                    failed.append({
                        "run": run_name,
                        "type": atype,
                        "pattern": pattern,
                        "context": assertion.get("context", ""),
                    })
        elif layer == "process_assertions":
            for r in data.get("results", []):
                if not r.get("passed", True):
                    assertion = r.get("assertion", {})
                    failed.append({
                        "run": run_name,
                        "type": assertion.get("type", "unknown"),
                        "description": assertion.get("description", assertion.get("tool", "?")),
                        "failure_class": r.get("failure_class"),
                    })
        elif layer == "artifact_validation":
            for r in data.get("structural_results", []):
                if r.get("status") == "failed":
                    assertion = r.get("assertion", {})
                    failed.append({
                        "run": run_name,
                        "type": assertion.get("type", "unknown"),
                        "detail": assertion.get("path", assertion.get("pattern", "?")),
                        "failure_class": r.get("failure_class"),
                    })
            for r in data.get("validator_results", []):
                if r.get("status") == "failed":
                    validator = r.get("validator", {})
                    vtype = validator.get("type", "unknown") if isinstance(validator, dict) else str(validator)
                    # Use first line of detail for concise reporting
                    detail_raw = r.get("detail", r.get("error", "?"))
                    detail_line = detail_raw.split("\n")[0][:80] if detail_raw else "?"
                    failed.append({
                        "run": run_name,
                        "type": vtype,
                        "detail": detail_line,
                        "failure_class": r.get("failure_class"),
                    })

    return failed


def compute_case_deltas(baseline: dict[str, Any], current_cases: dict[str, dict[str, Any]],
                        layer: str, threshold: float) -> list[dict[str, Any]]:
    """Compare per-eval-case scores between baseline and current for a given layer.

    Returns list of regressed cases with delta info.
    """
    bl_cases = baseline.get("per_eval_cases") or {}
    regressed: list[dict[str, Any]] = []

    # Union of all case names from both baseline and current
    all_cases = sorted(set(list(bl_cases.keys()) + list(current_cases.keys())))

    for case_name in all_cases:
        bl_case = bl_cases.get(case_name, {})
        cur_case = current_cases.get(case_name, {})

        bl_layer = bl_case.get(layer)
        cur_layer = cur_case.get(layer)

        if bl_layer is None or cur_layer is None:
            continue

        bl_rate = bl_layer.get("pass_rate")
        cur_rate = cur_layer.get("pass_rate")
        if bl_rate is None or cur_rate is None:
            continue

        delta_pp = (cur_rate - bl_rate) * 100
        if delta_pp < -threshold:
            regressed.append({
                "case": case_name,
                "baseline_rate": bl_rate,
                "current_rate": cur_rate,
                "delta_pp": delta_pp,
            })

    return regressed


def gather_from_workspace(skill: str, pass_k: int) -> dict[str, Any]:
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    if not latest.exists():
        print(f"Error: workspace/latest not found for {skill}", file=sys.stderr)
        sys.exit(1)
    runs_dir = EVALS_ROOT / skill / "workspace" / "runs"
    triggering = None
    if runs_dir.is_dir():
        for d in sorted([d for d in runs_dir.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True):
            mp = d / "metrics.json"
            if mp.exists():
                m = json.loads(mp.read_text())
                pos, neg = m["positive"], m["negative"]
                triggering = {"accuracy": m["overall"]["accuracy"],
                              "tpr": pos["passed"] / pos["total"] if pos["total"] > 0 else 0.0,
                              "tnr": neg["passed"] / neg["total"] if neg["total"] > 0 else 0.0,
                              "flake_count": m.get("flake_count", 0)}
                break
    task = None
    bp = latest / "benchmark.json"
    if bp.exists():
        bench = json.loads(bp.read_text())
        ws = bench["run_summary"]["with_skill"]["pass_rate"]
        wos = bench["run_summary"]["without_skill"]["pass_rate"]
        task = {"with_skill_mean": ws["mean"], "with_skill_stddev": ws["stddev"], "without_skill_mean": wos["mean"]}
    extract_p = lambda d: (d["passed"], d["total"])
    extract_a = lambda d: (d["summary"]["structural_passed"] + d["summary"]["validators_passed"],
                           d["summary"]["structural_passed"] + d["summary"]["structural_failed"] +
                           d["summary"]["validators_passed"] + d["summary"]["validators_failed"])
    return {"triggering": triggering, "task": task,
            "process_assertions": _aggregate(latest, "process-assertions.json", extract_p),
            "artifact_validation": _aggregate(latest, "artifact-validation.json", extract_a),
            "knowledge_assertions": _aggregate(latest, "knowledge-assertions.json", extract_p),
            "pass_k_rate": compute_pass_k(latest, pass_k)}


def gather_from_history(skill: str) -> dict[str, Any]:
    hp = HISTORY_DIR / f"{skill}.jsonl"
    if not hp.exists():
        print(f"Error: no history file for {skill}", file=sys.stderr)
        sys.exit(1)
    lines = hp.read_text().strip().splitlines()
    if not lines:
        print(f"Error: history file is empty for {skill}", file=sys.stderr)
        sys.exit(1)
    triggering = task = None
    for line in reversed(lines):
        row = json.loads(line)
        if triggering is None and row.get("kind", "triggering") != "task":
            pos, neg = row.get("positive", {}), row.get("negative", {})
            triggering = {"accuracy": row.get("overall", {}).get("accuracy"),
                          "tpr": pos["passed"] / pos["total"] if pos.get("total", 0) > 0 else 0.0,
                          "tnr": neg["passed"] / neg["total"] if neg.get("total", 0) > 0 else 0.0,
                          "flake_count": row.get("flake_count", 0)}
        if task is None and row.get("kind") == "task":
            task = {"with_skill_mean": row.get("with_skill_mean"),
                    "with_skill_stddev": row.get("with_skill_stddev"),
                    "without_skill_mean": row.get("without_skill_mean")}
        if triggering is not None and task is not None:
            break
    return {"triggering": triggering, "task": task, "process_assertions": None,
            "artifact_validation": None, "knowledge_assertions": None, "pass_k_rate": None}


def get_primary(layer_data: Optional[dict[str, Any]], layer: str) -> Optional[float]:
    if layer_data is None:
        return None
    return layer_data.get(PRIMARY_FIELD[layer])


def fmt_pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def fmt_delta(d: Optional[float]) -> str:
    return "—" if d is None else f"{'+' if d >= 0 else ''}{d:.1f}pp"


def _format_failed_assertion(layer: str, assertion_info: dict[str, Any]) -> str:
    """Format a single failed assertion for human-readable output."""
    if layer == "knowledge_assertions":
        atype = assertion_info.get("type", "unknown")
        pattern = assertion_info.get("pattern", "?")
        return f'{atype} "{pattern}" FAILED'
    elif layer == "process_assertions":
        atype = assertion_info.get("type", "unknown")
        desc = assertion_info.get("description", "?")
        fc = assertion_info.get("failure_class")
        suffix = f" [{fc}]" if fc else ""
        return f'{atype} "{desc}" FAILED{suffix}'
    elif layer == "artifact_validation":
        atype = assertion_info.get("type", "unknown")
        detail = assertion_info.get("detail", "?")
        return f'{atype} "{detail}" FAILED'
    return "unknown assertion FAILED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    parser.add_argument("--threshold", type=float, default=5.0)
    parser.add_argument("--from-history", action="store_true")
    parser.add_argument("--pass-k", type=int, default=3)
    args = parser.parse_args()
    skill, threshold, pass_k = args.skill, args.threshold, args.pass_k

    baseline = load_baseline(skill)
    if baseline is None:
        print(f"No baseline for {skill} — skipping")
        sys.exit(0)

    baseline_hash = baseline.get("eval_set_hash")
    current_hash = compute_eval_set_hash(skill)
    if baseline_hash and current_hash and baseline_hash != current_hash:
        print(f"WARNING: eval set changed since baseline was frozen (baseline={baseline_hash[:12]}… current={current_hash[:12]}…)", file=sys.stderr)

    current = gather_from_history(skill) if args.from_history else gather_from_workspace(skill, pass_k)
    git_head = get_git_head()

    deltas: dict[str, Optional[float]] = {}
    for layer in LAYERS:
        br = get_primary(baseline.get(layer), layer)
        cr = get_primary(current.get(layer), layer)
        deltas[layer] = (cr - br) * 100 if (br is not None and cr is not None) else None

    bl_pk = (baseline.get("task") or {}).get("pass_k_rate")
    cur_pk = current.get("pass_k_rate")
    pk_delta = (cur_pk - bl_pk) * 100 if (bl_pk is not None and cur_pk is not None) else None

    non_null = [d for d in deltas.values() if d is not None]
    if pk_delta is not None:
        non_null.append(pk_delta)

    blocking: list[str] = [l for l in LAYERS if deltas[l] is not None and deltas[l] < -threshold]
    if pk_delta is not None and pk_delta < -threshold:
        blocking.append(f"pass_k_{pass_k}")

    if not non_null:
        status = "PASS"
    elif min(non_null) < -threshold:
        status = "REGRESSION"
    elif min(non_null) < 0:
        status = "WARNING"
    else:
        status = "PASS"

    # --- Per-eval-case drill-down for regressed layers ---
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    per_case_drilldown: dict[str, list[dict[str, Any]]] = {}
    current_cases: dict[str, dict[str, Any]] = {}

    if latest.exists() and not args.from_history:
        current_cases = gather_per_eval_cases(latest)
        for layer in blocking:
            if layer not in DRILLDOWN_LAYERS:
                continue
            regressed_cases = compute_case_deltas(baseline, current_cases, layer, threshold)
            if regressed_cases:
                # Enrich with failed assertion details
                for case_info in regressed_cases:
                    failed = gather_failed_assertions(latest, layer, case_info["case"])
                    case_info["failed_assertions"] = failed
                per_case_drilldown[layer] = regressed_cases

    # --- Composite score comparison ---
    config = load_config(skill)
    bl_composite = baseline.get("composite")
    bl_score = bl_composite["score"] if bl_composite else None
    bl_grade = bl_composite["grade"] if bl_composite else None

    cur_composite = compute_from_workspace(skill, config) if not args.from_history else None
    cur_score = cur_composite["score"] if cur_composite else None
    cur_grade = cur_composite["grade"] if cur_composite else None

    composite_delta = (cur_score - bl_score) if (cur_score is not None and bl_score is not None) else None

    result = {"skill": skill, "status": status, "threshold_pp": threshold,
              "deltas": deltas,
              "composite": {"baseline_score": bl_score, "baseline_grade": bl_grade,
                            "current_score": cur_score, "current_grade": cur_grade,
                            "delta": composite_delta},
              "pass_k": {"baseline": bl_pk, "current": cur_pk, "delta_pp": pk_delta},
              "blocking_layers": blocking,
              "per_case_regressions": per_case_drilldown if per_case_drilldown else None,
              "baseline_git_head": baseline.get("git_head", "unknown"),
              "current_git_head": git_head}
    print(json.dumps(result, indent=2))

    ws_dir = EVALS_ROOT / skill / "workspace"
    if ws_dir.is_dir():
        rows = []
        for layer in LAYERS:
            br = get_primary(baseline.get(layer), layer)
            cr = get_primary(current.get(layer), layer)
            d = deltas[layer]
            st = "⊘ skip" if d is None else ("❌ REGRESSION" if d < -threshold else "✅ PASS")
            rows.append(f"| {LAYER_LABELS[layer]} | {fmt_pct(br)} | {fmt_pct(cr)} | {fmt_delta(d)} | {st} |")
        pk_st = "⊘ skip" if pk_delta is None else ("❌ REGRESSION" if pk_delta < -threshold else "✅ PASS")
        rows.append(f"| Reliability (pass^{pass_k}) | {fmt_pct(bl_pk)} | {fmt_pct(cur_pk)} | {fmt_delta(pk_delta)} | {pk_st} |")

        reasons = [f"{LAYER_LABELS[l].lower()} dropped {abs(deltas[l]):.1f}pp" for l in LAYERS
                   if deltas[l] is not None and deltas[l] < -threshold]
        if pk_delta is not None and pk_delta < -threshold:
            reasons.append(f"pass^{pass_k} dropped {abs(pk_delta):.1f}pp")
        if status == "REGRESSION":
            verdict = f"REGRESSION ({', '.join(reasons)}, threshold is {threshold:.1f}pp)"
        elif status == "WARNING":
            verdict = "WARNING (minor regression below threshold)"
        else:
            verdict = "PASS"

        # Build per-eval-case drilldown section for the markdown report
        drilldown_lines: list[str] = []
        if per_case_drilldown:
            drilldown_lines.append("## Per-Eval-Case Drill-Down")
            drilldown_lines.append("")
            for layer, cases in per_case_drilldown.items():
                label = LAYER_LABELS[layer]
                br_layer = get_primary(baseline.get(layer), layer)
                cr_layer = get_primary(current.get(layer), layer)
                layer_delta = deltas[layer]
                drilldown_lines.append(
                    f"**REGRESSION: {label.lower()} score dropped "
                    f"{abs(layer_delta):.0f}pp ({fmt_pct(br_layer)} -> {fmt_pct(cr_layer)})**"
                )
                drilldown_lines.append("")
                drilldown_lines.append("Regressed cases:")
                for case_info in cases:
                    case_name = case_info["case"]
                    bl_r = case_info["baseline_rate"]
                    cur_r = case_info["current_rate"]
                    drilldown_lines.append(
                        f"- {case_name}: {fmt_pct(bl_r)} -> {fmt_pct(cur_r)}"
                    )
                    # Add failed assertion details for traceability
                    failed = case_info.get("failed_assertions", [])
                    if failed:
                        # Deduplicate by (type, pattern/detail) — multiple runs may repeat
                        seen: set[str] = set()
                        for fa in failed:
                            desc = _format_failed_assertion(layer, fa)
                            if desc not in seen:
                                seen.add(desc)
                                drilldown_lines.append(f"  - assertions: {desc}")
                drilldown_lines.append("")

        drilldown_section = ("\n" + "\n".join(drilldown_lines) + "\n") if drilldown_lines else ""
        composite_line = ""
        if bl_score is not None or cur_score is not None:
            bl_str = f"{bl_grade} ({bl_score})" if bl_score is not None else "—"
            cur_str = f"{cur_grade} ({cur_score})" if cur_score is not None else "—"
            delta_str = f"{composite_delta:+.1f}" if composite_delta is not None else "—"
            composite_line = f"\n**Composite:** {bl_str} → {cur_str} (Δ {delta_str})\n"

        report = (f"# Regression Report: {skill}\n\n"
                  f"**Status:** {status}\n"
                  f"**Threshold:** {threshold:.1f}pp\n"
                  f"**Baseline:** {baseline.get('git_head', 'unknown')} ({baseline.get('created_at', 'unknown')})\n"
                  f"**Current:** {git_head}\n"
                  + composite_line + "\n"
                  f"| Layer | Baseline | Current | Delta | Status |\n"
                  f"|-------|----------|---------|-------|--------|\n"
                  + "\n".join(rows) + "\n\n"
                  f"**Verdict:** {verdict}\n"
                  + drilldown_section)
        (ws_dir / "regression-report.md").write_text(report)

    sys.exit(2 if status == "REGRESSION" else 0)


if __name__ == "__main__":
    main()
