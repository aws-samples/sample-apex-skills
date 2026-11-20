"""Compare committed baseline against current scores and gate CI on regressions.

--gate scores one run key's task result from run_task_evals.py instead
(--task-result, required with --gate): the new arm (with_skill) against the
base arm the runner names (baseline_arm: base_skill at --base-ref, or
without_skill), per case on Pass@k. It exits 2 on a regression and 1 when
there is no result to score; tokens and time are in the report and never
block: only pass rate blocks.
"""

import argparse
import json
import os
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
# The arms run_task_evals.py compares with_skill against (contract: baseline_arm).
BASE_ARMS = ("base_skill", "without_skill")
GATE_TOKENS_NOTE = "Tokens and time are reported and do not block: only pass rate blocks."


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


def workspace_base_arm(latest: Path, run_summary: dict[str, Any]) -> str:
    """The base arm a run compared with_skill against: base_arm in the run's
    cases.json (run_task_evals.py writes it), else base_skill when the
    benchmark holds that arm, else without_skill (older runs, from before the base_skill arm)."""
    cases = latest / "cases.json"
    if cases.exists():
        arm = json.loads(cases.read_text()).get("base_arm")
        if arm in BASE_ARMS:
            return arm
    return "base_skill" if "base_skill" in run_summary else "without_skill"


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
        rs = bench["run_summary"]
        base_arm = workspace_base_arm(latest, rs)
        ws = rs["with_skill"]["pass_rate"]
        bs = rs[base_arm]["pass_rate"]
        task = {"with_skill_mean": ws["mean"], "with_skill_stddev": ws["stddev"],
                "without_skill_mean": bs["mean"] if base_arm == "without_skill" else None,
                "baseline_arm": base_arm, "base_mean": bs["mean"]}
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
        try:
            row = json.loads(line)
        except ValueError:
            print(f"warning: {hp}: skipping a line that is not JSON", file=sys.stderr)
            continue
        if triggering is None and row.get("kind", "triggering") != "task":
            pos, neg = row.get("positive", {}), row.get("negative", {})
            triggering = {"accuracy": row.get("overall", {}).get("accuracy"),
                          "tpr": pos["passed"] / pos["total"] if pos.get("total", 0) > 0 else 0.0,
                          "tnr": neg["passed"] / neg["total"] if neg.get("total", 0) > 0 else 0.0,
                          "flake_count": row.get("flake_count", 0)}
        if task is None and row.get("kind") == "task":
            base_arm = row.get("baseline_arm") or "without_skill"
            task = {"with_skill_mean": row.get("with_skill_mean"),
                    "with_skill_stddev": row.get("with_skill_stddev"),
                    "without_skill_mean": row.get("without_skill_mean"),
                    "baseline_arm": base_arm,
                    "base_mean": row.get("base_skill_mean") if base_arm == "base_skill"
                    else row.get("without_skill_mean")}
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


# ---------- gate: new arm against the base arm, per case -------------------


class GateInputError(Exception):
    """The gate has no result it can score. It exits 1, never 0."""


def load_gate_entry(skill: str, task_result: Path) -> tuple[dict[str, Any], Optional[Path]]:
    """The run key's kind "task" entry and its runs dir, from task_result:
    the JSON list run_task_evals.py prints. The key's outcome must hold a
    history_entry (a runner error or a run with no case is refused)."""
    try:
        outcomes = json.loads(task_result.read_text())
    except (OSError, ValueError) as e:
        raise GateInputError(f"cannot read the runner result {task_result}: {e}")
    found = [o for o in outcomes if isinstance(o, dict) and o.get("skill") == skill] \
        if isinstance(outcomes, list) else []
    if not found:
        raise GateInputError(f"{task_result} holds no runner result for {skill}")
    outcome = found[-1]
    if "error" in outcome:
        raise GateInputError(f"the runner failed for {skill}: {outcome['error']}")
    if "skipped" in outcome:
        raise GateInputError(f"the runner ran no case for {skill} ({outcome['skipped']}), "
                             "so nothing passed")
    entry = outcome.get("history_entry")
    runs_dir = Path(outcome["runs_dir"]) if outcome.get("runs_dir") else None
    if not isinstance(entry, dict) or not isinstance(entry.get("cases"), list):
        raise GateInputError(f"no per-case task result for {skill}")
    if not entry["cases"]:
        raise GateInputError(f"the task result for {skill} holds no case")
    return entry, runs_dir


def _arm_view(arm: dict[str, Any]) -> dict[str, Any]:
    return {"runs": arm.get("runs", 0), "valid_runs": arm.get("valid_runs", 0),
            "passes": arm.get("passes", 0), "pass_at_k": arm.get("pass_at_k") is True,
            "pass_all_k": arm.get("pass_all_k") is True,
            "tokens_mean": arm.get("tokens_mean"), "wall_seconds_mean": arm.get("wall_seconds_mean"),
            "invalid_reasons": arm.get("invalid_reasons") or []}


def evaluate_gate(entry: dict[str, Any], threshold: float) -> dict[str, Any]:
    """Score one run key's task entry.

    A case fails when its with_skill arm fails Pass@k (no run of k passed;
    an invalid run never passes). A failed case blocks on its own when it
    is one of the key's own cases, or a shared class case on a target whose
    `blocking` is not False (CLASS_TARGETS: report-only targets list their
    shared-case fails without blocking). The pooled delta (with_skill mean
    less the base arm's mean, of the grader pass rate only, an invalid run
    counting as 0), rounded to 0.1 pp, also blocks below -threshold pp when
    the key has a blocking case. Tokens and time never block (GATE_TOKENS_NOTE)."""
    base_arm = entry.get("baseline_arm") or "without_skill"
    target_blocking = entry.get("blocking")
    cases = []
    for c in entry["cases"]:
        arms = c.get("arms") or {}
        cases.append({"eval_id": c.get("eval_id"), "source": c.get("source", "own"),
                      "blocks": c.get("source", "own") == "own" or target_blocking is not False,
                      "pass": c.get("pass") is True, "regressed": c.get("regressed") is True,
                      "new": _arm_view(arms.get("with_skill") or {}),
                      "base": _arm_view(arms.get(base_arm) or {})})
    k = entry.get("pass_k")
    reasons = [f"eval-{c['eval_id']} failed Pass@{k}"
               + (f" ({base_arm} passed it)" if c["regressed"] else "")
               for c in cases if not c["pass"] and c["blocks"]]
    delta = entry.get("delta")
    delta_pp = round(delta * 100, 1) if isinstance(delta, (int, float)) else None
    if delta_pp is not None and delta_pp < -threshold and any(c["blocks"] for c in cases):
        reasons.append(f"pooled pass rate {delta_pp:+.1f}pp against {base_arm}, "
                       f"threshold is {threshold:.1f}pp")
    report_only_fails = [c for c in cases if not c["pass"] and not c["blocks"]]
    if reasons:
        status = "REGRESSION"
    elif report_only_fails or (delta_pp is not None and delta_pp < 0):
        status = "WARNING"
    else:
        status = "PASS"
    summary_arms = (entry.get("skill_summary") or {}).get("arms") or {}
    return {"skill": entry.get("run_key"), "status": status, "reasons": reasons,
            "harness": entry.get("harness"), "pass_k": k, "baseline_arm": base_arm,
            "comparison": entry.get("comparison"), "base_ref": entry.get("base_ref"),
            "base_ref_sha": entry.get("base_ref_sha"), "target_blocking": target_blocking,
            "threshold_pp": threshold, "delta_pp": delta_pp,
            "with_skill_mean": entry.get("with_skill_mean"),
            "base_mean": entry.get("base_skill_mean") if base_arm == "base_skill"
            else entry.get("without_skill_mean"),
            "cases": cases,
            "report_only_failures": [c["eval_id"] for c in report_only_fails],
            "per_skill": {arm: summary_arms.get(arm) for arm in ("with_skill", base_arm)},
            "not_blocking": GATE_TOKENS_NOTE}


def _num(v: Any, fmt: str) -> str:
    return format(v, fmt) if isinstance(v, (int, float)) else "n/a"


def render_gate_report(result: dict[str, Any]) -> str:
    base, k = result["baseline_arm"], result["pass_k"]
    if base == "base_skill":
        sha = (result.get("base_ref_sha") or "")[:12]
        against = f"base_skill (the skill at {result.get('base_ref')}, {sha})"
    else:
        against = "without_skill (no skill: the skill is new at the base ref, or --base-ref none)"
    lines = [f"# Eval Gate Report: {result['skill']}", "",
             f"**Status:** {result['status']}",
             f"**Harness:** {result.get('harness')}",
             f"**Comparison:** with_skill against {against}",
             f"**Pass@{k}:** a case passes when at least one of its {k} with_skill runs passes; "
             "an invalid run never passes",
             "**Blocks:** a failed own case; a failed shared class case only on a blocking target "
             f"(this target: {'report-only' if result['target_blocking'] is False else 'blocking'})",
             "",
             f"| Case | Source | Blocks | with_skill passes | {base} passes | Pass@{k} | pass^{k} "
             "| Tokens/run new | Tokens/run base | Time/run new (s) | Time/run base (s) | Result |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in result["cases"]:
        new, old = c["new"], c["base"]
        verdict = "pass" if c["pass"] else ("FAIL" if c["blocks"] else "fail (report-only)")
        if c["regressed"]:
            verdict += ", regressed"
        lines.append(
            f"| eval-{c['eval_id']} | {c['source']} | {'yes' if c['blocks'] else 'no'} "
            f"| {new['passes']}/{new['runs']} | {old['passes']}/{old['runs']} "
            f"| {'yes' if c['pass'] else 'no'} | {'yes' if new['pass_all_k'] else 'no'} "
            f"| {_num(new['tokens_mean'], '.0f')} | {_num(old['tokens_mean'], '.0f')} "
            f"| {_num(new['wall_seconds_mean'], '.1f')} | {_num(old['wall_seconds_mean'], '.1f')} "
            f"| {verdict} |")
    lines += ["", "## Per skill", "",
              f"| Arm | Cases Pass@{k} | Cases pass^{k} | Runs | Invalid runs | Tokens/run | Time/run (s) |",
              "|---|---|---|---|---|---|---|"]
    for arm, s in result["per_skill"].items():
        s = s or {}
        lines.append(f"| {arm} | {s.get('cases_pass_at_k', 'n/a')} | {s.get('cases_pass_all_k', 'n/a')} "
                     f"| {s.get('runs', 'n/a')} | {s.get('invalid_runs', 'n/a')} "
                     f"| {_num(s.get('tokens_per_run_mean'), '.0f')} "
                     f"| {_num(s.get('wall_seconds_per_run_mean'), '.1f')} |")
    lines += ["",
              f"**Pooled pass rate:** with_skill {_num(result['with_skill_mean'], '.3f')}, "
              f"{base} {_num(result['base_mean'], '.3f')}, delta {_num(result['delta_pp'], '+.1f')}pp "
              f"(threshold {result['threshold_pp']:.1f}pp)",
              "",
              "**Verdict:** " + (result["status"] if not result["reasons"]
                                 else f"{result['status']} ({'; '.join(result['reasons'])})"),
              "", result["not_blocking"], ""]
    return "\n".join(lines)


def gate_workspace(skill: str, runs_dir: Optional[Path]) -> Path:
    """Where gate-report.md goes: the run's workspace (runs/<UTC> is two
    levels under it), else the key's misc/evals workspace."""
    if runs_dir is not None:
        return runs_dir.parent.parent
    own = EVALS_ROOT / skill
    return (own if (own / "evals.json").exists() else EVALS_ROOT / "workspace" / skill) / "workspace"


def run_gate(skill: str, task_result: Path, threshold: float) -> int:
    try:
        entry, runs_dir = load_gate_entry(skill, task_result)
    except GateInputError as e:
        print(f"[gate] {skill}: FAIL, {e}", file=sys.stderr)
        return 1
    result = evaluate_gate(entry, threshold)
    result["skill"] = result["skill"] or skill
    report = render_gate_report(result)
    print(json.dumps(result, indent=2))
    print(report, file=sys.stderr)
    ws = gate_workspace(skill, runs_dir)
    if ws.is_dir():
        (ws / "gate-report.md").write_text(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(report + "\n")
    return 2 if result["status"] == "REGRESSION" else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    parser.add_argument("--threshold", type=float, default=5.0)
    parser.add_argument("--from-history", action="store_true")
    parser.add_argument("--pass-k", type=int, default=3,
                        help="Without --gate only; the gate takes k from the task result.")
    parser.add_argument("--gate", action="store_true",
                        help="Score the run key's per-case task result (with_skill against the "
                             "base arm the runner names); exit 2 on a regression, 1 when there is "
                             "no result to score. Needs --task-result.")
    parser.add_argument("--task-result", type=Path, default=None,
                        help="With --gate: the JSON run_task_evals.py printed.")
    args = parser.parse_args()
    if args.gate:
        if args.task_result is None:
            parser.error("--gate needs --task-result")
        sys.exit(run_gate(args.skill, args.task_result, args.threshold))
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
