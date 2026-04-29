#!/usr/bin/env python3
"""Phase 1 of misc/evals/PLAN.md — the triggering-axis scorecard runner.

Orchestrates `make triggering-<skill>` for every in-scope skill, enriches the
raw `run_eval` output with stratified metrics (TPR / TNR / flakes / per-sibling
leakage / threshold sweep / delta-vs-prev), persists per-run artefacts under
`<skill>/workspace/runs/<UTC>/` (gitignored) and a compact one-line summary to
`misc/evals/history/<skill>.jsonl` (committed, 50-entry cap), then splices a
freshly rendered scorecard into `misc/evals/README.md` between the
`<!-- SCORECARD_START/END -->` markers.

Task-axis columns stay `—` until Phase 2 drops `<skill>/workspace/latest/benchmark.json`.

See misc/evals/PLAN.md §1 for design intent; this file is the only new runtime
code Phase 1 ships. The Python CLI never duplicates Makefile defaults —
user-supplied flags (`--model`, `--runs-per-query`, `--num-workers`) are only
forwarded as `KEY=VALUE` pairs to `make triggering-<skill>` when explicitly
passed, so the Makefile remains the single source of truth for defaults.

Exit codes:
  0  success, no regressions
  1  one or more `make triggering-<skill>` invocations errored
  2  --fail-on-regression threshold breached (exit 1 is reserved for make failure)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EVALS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_ROOT.parent.parent
HISTORY_DIR = EVALS_ROOT / "history"
HISTORY_CAP = 50
TRIGGER_THRESHOLD = 0.5
THRESHOLD_SWEEP = (0.33, 0.5, 0.67)

SCORECARD_START = "<!-- SCORECARD_START -->"
SCORECARD_END = "<!-- SCORECARD_END -->"
SIBLING_MAP_START = "<!-- SIBLING_MAP_START -->"
SIBLING_MAP_END = "<!-- SIBLING_MAP_END -->"


# ---------- discovery ---------------------------------------------------------


def discover_skills() -> list[str]:
    """Mirror the Makefile's SKILLS derivation exactly."""
    skills = []
    for child in sorted(EVALS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if child.name in {"_template", "workspace", "scripts", "history"}:
            continue
        if child.name.startswith("."):
            continue
        skills.append(child.name)
    return skills


# ---------- hygiene pre-flight ------------------------------------------------


@dataclass
class Hygiene:
    ok: bool
    warnings: list[str] = field(default_factory=list)


def hygiene_check(skill: str) -> Hygiene:
    """Returns a bag of warnings — never raises, never exits.

    Warnings exist to flag drift quickly; they do not block a run.
    """
    warnings: list[str] = []
    skill_path = REPO_ROOT / "skills" / skill
    triggering_path = EVALS_ROOT / skill / "triggering.json"
    evals_path = EVALS_ROOT / skill / "evals.json"
    sc_scripts = REPO_ROOT / "skills" / "skill-creator" / "scripts"

    # A — quick_validate for frontmatter / 64-char name / 1024-char description.
    res = subprocess.run(
        ["python3", str(sc_scripts / "quick_validate.py"), str(skill_path)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        warnings.append(f"quick_validate failed: {res.stdout.strip() or res.stderr.strip()}")

    # triggering.json shape.
    try:
        triggering = json.loads(triggering_path.read_text())
    except FileNotFoundError:
        warnings.append(f"missing triggering.json at {triggering_path}")
        triggering = []
    except json.JSONDecodeError as e:
        warnings.append(f"triggering.json is not valid JSON: {e}")
        triggering = []

    pos = sum(1 for e in triggering if e.get("should_trigger") is True)
    neg = sum(1 for e in triggering if e.get("should_trigger") is False)
    if pos < 8:
        warnings.append(f"triggering.json has {pos} positives (<8)")
    if neg < 8:
        warnings.append(f"triggering.json has {neg} negatives (<8)")

    # evals.json shape.
    try:
        evals = json.loads(evals_path.read_text())
    except FileNotFoundError:
        warnings.append(f"missing evals.json at {evals_path}")
        evals = {"evals": []}
    except json.JSONDecodeError as e:
        warnings.append(f"evals.json is not valid JSON: {e}")
        evals = {"evals": []}

    prompts = evals.get("evals", [])
    if len(prompts) < 2:
        warnings.append(f"evals.json has {len(prompts)} prompts (<2)")
    for p in prompts:
        exp = p.get("expectations", [])
        if len(exp) < 3:
            warnings.append(
                f"evals.json prompt id={p.get('id', '?')} has {len(exp)} expectations (<3)"
            )

    return Hygiene(ok=(not warnings), warnings=warnings)


# ---------- sibling-map parser ------------------------------------------------


_BULLET_RE = re.compile(r"^-\s+\*\*(.+?)\*\*", re.DOTALL)
# "negatives 9, 10, 11" / "Negatives at items 9–11" / "negative cases 1–4" /
# "Negative 7 enforces". Up to three filler words between "negative" and the
# first digit keep the match specific while tolerating the prose variations
# in the live READMEs.
_NEGATIVES_RE = re.compile(
    r"\bnegatives?\b(?:\s+\w+){0,3}?\s+(\d[\d,\s\-–]*)",
    re.IGNORECASE,
)
# A real skill slug is lowercase kebab-case with at least one hyphen. This
# excludes catchall buckets like "Generic / non-EKS" or "Unrelated" so their
# negatives fall through to the `other` bucket rather than getting mapped
# to a bogus sibling.
_SKILL_SLUG_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")


def _extract_sibling_name(bold_content: str) -> str | None:
    """Grab the sibling slug from `**...**`. Tolerates both
    ``**`eks-recon`**`` and ``**eks-recon (…):**`` shapes by taking the first
    kebab-case-with-hyphen token inside the bolded run. Returns None for
    catchall bullets like ``**Generic / non-EKS**``; the caller buckets those
    indices under `other`.
    """
    stripped = bold_content.replace("`", "")
    m = _SKILL_SLUG_RE.search(stripped)
    return m.group(0) if m else None


def _expand_indices(raw: str) -> list[int]:
    """Parse "9, 10, 11" / "9-11" / "9–11" into [9, 10, 11].

    Accepts both ASCII hyphen and en-dash as range separators, plus
    comma-separated lists.
    """
    out: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        # Try range first (covers both `-` and `–`).
        m = re.match(r"^(\d+)\s*[\-–]\s*(\d+)$", token)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= hi:
                out.extend(range(lo, hi + 1))
            continue
        if token.isdigit():
            out.append(int(token))
    return out


def parse_sibling_map(readme_text: str) -> list[tuple[str, list[int]]]:
    """Return [(sibling_name, [indices_as_written]), ...] from the region
    between SIBLING_MAP_START/END. Empty list if the markers are missing or
    the section is empty — callers treat that as "all negatives unattributed".
    """
    start = readme_text.find(SIBLING_MAP_START)
    end = readme_text.find(SIBLING_MAP_END)
    if start == -1 or end == -1 or end < start:
        return []
    block = readme_text[start + len(SIBLING_MAP_START) : end]

    entries: list[tuple[str, list[int]]] = []
    # Bullets may span lines; normalise whitespace per-bullet.
    for raw_bullet in re.split(r"\n(?=-\s)", block.strip()):
        bullet = raw_bullet.strip()
        if not bullet.startswith("- "):
            continue
        m_bold = _BULLET_RE.match(bullet)
        if not m_bold:
            continue
        sibling = _extract_sibling_name(m_bold.group(1))
        # None sibling = catchall bullet ("Generic / non-EKS", "Unrelated").
        # The negatives it claims are documented as intentionally non-sibling,
        # so we assign them to the `other` bucket instead of dropping them —
        # the scorecard still needs to show their count.
        sibling_key = sibling or "other"
        m_neg = _NEGATIVES_RE.search(bullet)
        if not m_neg:
            continue
        indices = _expand_indices(m_neg.group(1))
        if indices:
            entries.append((sibling_key, indices))
    return entries


def build_index_to_sibling(
    sibling_entries: list[tuple[str, list[int]]],
    triggering: list[dict],
) -> tuple[dict[int, str], list[int], list[int]]:
    """Map *absolute 0-indexed* negative positions → sibling name.

    The plan's canonical convention is 1-indexed into the full triggering list.
    One live README (eks-mcp-server) uses relative-to-negatives numbering
    instead. To keep the parser robust without touching bullet text, try
    absolute first; if every cited index points to a *positive* entry, retry
    with a relative-to-negatives offset. Anything still misaligned bucks to
    `other`.

    Returns (map, matched_indices, unmatched_indices_in_triggering).
    """
    num_positives = sum(1 for e in triggering if e.get("should_trigger") is True)
    neg_indices_zero = {i for i, e in enumerate(triggering) if e.get("should_trigger") is False}

    def _try(shift: int) -> dict[int, str] | None:
        mapping: dict[int, str] = {}
        for sibling, raw in sibling_entries:
            for one_indexed in raw:
                zero_idx = one_indexed - 1 + shift
                if zero_idx in neg_indices_zero:
                    mapping[zero_idx] = sibling
                else:
                    return None
        return mapping

    mapping = _try(0)
    if mapping is None:
        # Relative-to-negatives: bullet cites "1" for the first negative, etc.
        mapping = _try(num_positives) or {}

    matched = sorted(mapping.keys())
    unmatched = sorted(neg_indices_zero - set(matched))
    return mapping, matched, unmatched


# ---------- Wilson CI ---------------------------------------------------------


def wilson_ci(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. Honest bounds with ~16 samples."""
    if total == 0:
        return (0.0, 0.0)
    phat = passed / total
    denom = 1 + (z * z) / total
    center = phat + (z * z) / (2 * total)
    span = z * math.sqrt((phat * (1 - phat) + (z * z) / (4 * total)) / total)
    lo = (center - span) / denom
    hi = (center + span) / denom
    return (max(0.0, lo), min(1.0, hi))


# ---------- metric enrichment -------------------------------------------------


def _pass_at_threshold(result: dict, threshold: float) -> bool:
    rate = result["trigger_rate"]
    if result["should_trigger"]:
        return rate >= threshold
    return rate < threshold


def enrich_metrics(
    run_eval_json: dict,
    triggering: list[dict],
    sibling_map: dict[int, str],
    unmatched_indices: list[int],
    snapshot: dict,
) -> dict:
    """Compute everything the scorecard and history need from the raw
    `run_eval` output.
    """
    results = run_eval_json.get("results", [])

    # Map query text -> index in triggering.json (stable; ProcessPoolExecutor
    # can return results in any order).
    query_to_idx = {item["query"]: idx for idx, item in enumerate(triggering)}

    # Overall.
    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    ci_lo, ci_hi = wilson_ci(passed, total)

    # Stratified.
    pos = [r for r in results if r["should_trigger"]]
    neg = [r for r in results if not r["should_trigger"]]
    pos_passed = sum(1 for r in pos if r["pass"])
    neg_passed = sum(1 for r in neg if r["pass"])

    # Flakes.
    flakes = [r for r in results if 0 < r["trigger_rate"] < 1]

    # Mean trigger rates.
    mean_pos = (sum(r["trigger_rate"] for r in pos) / len(pos)) if pos else 0.0
    mean_neg = (sum(r["trigger_rate"] for r in neg) / len(neg)) if neg else 0.0

    # Per-sibling leakage. Denominator = number of negatives assigned to that
    # sibling; numerator = number of those that incorrectly triggered (pass==False).
    leakage: dict[str, dict[str, int]] = {}
    sibling_per_result: list[tuple[dict, str]] = []
    for r in results:
        if r["should_trigger"]:
            continue
        idx = query_to_idx.get(r["query"])
        sibling = sibling_map.get(idx, "other") if idx is not None else "other"
        leakage.setdefault(sibling, {"total": 0, "leaked": 0})
        leakage[sibling]["total"] += 1
        if not r["pass"]:
            leakage[sibling]["leaked"] += 1
        sibling_per_result.append((r, sibling))

    # Threshold sweep.
    sweep: dict[str, dict[str, int]] = {}
    for t in THRESHOLD_SWEEP:
        t_pos = sum(1 for r in pos if _pass_at_threshold(r, t))
        t_neg = sum(1 for r in neg if _pass_at_threshold(r, t))
        sweep[f"{t:.2f}"] = {
            "passed": t_pos + t_neg,
            "total": total,
            "positive_passed": t_pos,
            "positive_total": len(pos),
            "negative_passed": t_neg,
            "negative_total": len(neg),
        }

    return {
        "skill": run_eval_json.get("skill_name"),
        "snapshot": snapshot,
        "overall": {
            "passed": passed,
            "total": total,
            "accuracy": (passed / total) if total else 0.0,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
        },
        "positive": {"passed": pos_passed, "total": len(pos)},
        "negative": {"passed": neg_passed, "total": len(neg)},
        "flake_count": len(flakes),
        "flakes": [
            {
                "query": r["query"],
                "trigger_rate": r["trigger_rate"],
                "should_trigger": r["should_trigger"],
                "pass": r["pass"],
            }
            for r in flakes
        ],
        "mean_trigger_rate_positive": mean_pos,
        "mean_trigger_rate_negative": mean_neg,
        "leakage": leakage,
        "threshold_sweep": sweep,
        "matched_indices": sorted(sibling_map.keys()),
        "unmatched_indices": unmatched_indices,
        "results": results,
    }


# ---------- history -----------------------------------------------------------


def history_path(skill: str) -> Path:
    return HISTORY_DIR / f"{skill}.jsonl"


def read_history(skill: str) -> list[dict]:
    path = history_path(skill)
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_history(skill: str, entry: dict) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_history(skill)
    rows.append(entry)
    rows = rows[-HISTORY_CAP:]
    path = history_path(skill)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            f.write("\n")


def history_compact_entry(metrics: dict) -> dict:
    """Distilled one-liner: what we need for `∆ vs prev` and trend plots."""
    return {
        "ts": metrics["snapshot"]["started_at"],
        "model": metrics["snapshot"]["model"],
        "provider": metrics["snapshot"].get("provider", "unknown"),
        "git_head": metrics["snapshot"]["git_head"],
        "skill_sha": metrics["snapshot"]["skill_sha"],
        "triggering_sha": metrics["snapshot"]["triggering_sha"],
        "evals_sha": metrics["snapshot"]["evals_sha"],
        "runs_per_query": metrics["snapshot"]["runs_per_query"],
        "overall": metrics["overall"],
        "positive": metrics["positive"],
        "negative": metrics["negative"],
        "flake_count": metrics["flake_count"],
        "mean_trigger_rate_positive": metrics["mean_trigger_rate_positive"],
        "mean_trigger_rate_negative": metrics["mean_trigger_rate_negative"],
        "leakage": metrics["leakage"],
        "matched_indices": metrics["matched_indices"],
        "unmatched_indices": metrics["unmatched_indices"],
    }


# ---------- snapshot ----------------------------------------------------------


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha1_bytes(path.read_bytes())


def git_head_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_snapshot(
    skill: str,
    model: str,
    provider: str,
    runs_per_query: int,
    num_workers: int,
) -> dict:
    skill_md = REPO_ROOT / "skills" / skill / "SKILL.md"
    return {
        "skill": skill,
        "model": model,
        "provider": provider,
        "runs_per_query": runs_per_query,
        "num_workers": num_workers,
        "skill_sha": file_sha(skill_md) or "missing",
        "triggering_sha": file_sha(EVALS_ROOT / skill / "triggering.json") or "missing",
        "evals_sha": file_sha(EVALS_ROOT / skill / "evals.json") or "missing",
        "git_head": git_head_short(),
        "started_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------- triggering invocation --------------------------------------------


def run_triggering(
    skill: str,
    model: str | None,
    runs_per_query: int | None,
    num_workers: int | None,
) -> tuple[int, str, str]:
    """Shell out to `make triggering-<skill>` with only user-set overrides.

    Returns (returncode, stdout, stderr). The Makefile prints the full
    `run_eval` JSON on stdout; `make`'s own recipe echoes appear in stderr.
    """
    cmd = ["make", "-C", str(EVALS_ROOT), f"triggering-{skill}"]
    if model is not None:
        cmd.append(f"MODEL={model}")
    if runs_per_query is not None:
        cmd.append(f"RUNS_PER_QUERY={runs_per_query}")
    if num_workers is not None:
        cmd.append(f"NUM_WORKERS={num_workers}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_run_eval_json(stdout: str) -> dict:
    """`make` prints the recipe echo, then the script's indented JSON, then
    `make: Leaving directory '…'` after. Use `raw_decode` so a trailing
    non-JSON line doesn't make `json.loads` raise `Extra data`."""
    lines = stdout.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("{"):
            start = i
            break
    if start is None:
        raise RuntimeError("no JSON object found in `make triggering-…` stdout")
    blob = "\n".join(lines[start:])
    obj, _end = json.JSONDecoder().raw_decode(blob)
    return obj


# ---------- resolved model (for the scorecard metadata) -----------------------


def resolve_makefile_default(var: str) -> str | None:
    """Ask the Makefile what its default value for VAR is, so scorecard
    metadata shows the model that was actually used when the user didn't
    override it. Avoids hard-coding a copy of the default in Python."""
    try:
        r = subprocess.run(
            ["make", "-C", str(EVALS_ROOT), "--no-print-directory", "-pn"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if r.returncode not in (0, 2):
        return None
    pattern = re.compile(rf"^{re.escape(var)}\s*:?\??=\s*(.+)$", re.MULTILINE)
    matches = pattern.findall(r.stdout)
    # Last definition wins for a `?=` that's redefined elsewhere; for our
    # simple Makefile the first match is the actual default.
    return matches[0].strip() if matches else None


# ---------- scorecard rendering -----------------------------------------------


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def fmt_delta_pp(current: float, previous: float | None) -> str:
    if previous is None:
        return "—"
    delta = (current - previous) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.0f}pp"


def load_task_benchmark(skill: str) -> dict | None:
    """Read <skill>/workspace/latest/benchmark.json if present."""
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    if not latest.exists():
        return None
    bench = latest / "benchmark.json"
    if not bench.exists():
        return None
    try:
        return json.loads(bench.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def previous_task_mean(skill: str) -> float | None:
    """Latest prior 'task' entry from history/<skill>.jsonl, excluding the
    row we just appended (if any). Used for the Task regression column.
    """
    rows = read_history(skill)
    task_rows = [r for r in rows if r.get("kind") == "task"]
    if len(task_rows) < 2:
        return None
    return task_rows[-2].get("with_skill_mean")


def format_task_cell(benchmark: dict | None) -> str:
    if not benchmark:
        return "—"
    rs = benchmark.get("run_summary", {})
    w = rs.get("with_skill", {}).get("pass_rate", {})
    wo = rs.get("without_skill", {}).get("pass_rate", {})
    if not w or not wo:
        return "—"
    delta = w.get("mean", 0) - wo.get("mean", 0)
    return (
        f"{w.get('mean', 0)*100:.0f}% ± {w.get('stddev', 0)*100:.0f}% / "
        f"{wo.get('mean', 0)*100:.0f}% ± {wo.get('stddev', 0)*100:.0f}% / "
        f"{delta*100:+.0f}pp"
    )


def format_task_regression(benchmark: dict | None, previous: float | None) -> str:
    if not benchmark:
        return "—"
    if previous is None:
        return "—"
    current = (
        benchmark.get("run_summary", {})
        .get("with_skill", {})
        .get("pass_rate", {})
        .get("mean", 0)
    )
    delta = (current - previous) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.0f}pp"


def aggregate_expectations(benchmark: dict) -> list[dict]:
    """Per-expectation pass rate across runs of a benchmark."""
    by_text: dict[str, dict[str, int]] = {}
    for run in benchmark.get("runs", []):
        for exp in run.get("expectations", []) or []:
            text = exp.get("text", "")
            if not text:
                continue
            slot = by_text.setdefault(
                text, {"total": 0, "passed": 0, "with_passed": 0, "with_total": 0}
            )
            slot["total"] += 1
            if exp.get("passed"):
                slot["passed"] += 1
            if run.get("configuration") == "with_skill":
                slot["with_total"] += 1
                if exp.get("passed"):
                    slot["with_passed"] += 1
    out = []
    for text, slot in by_text.items():
        out.append(
            {
                "text": text,
                "passed": slot["passed"],
                "total": slot["total"],
                "with_passed": slot["with_passed"],
                "with_total": slot["with_total"],
            }
        )
    return out


def collect_eval_feedback(benchmark_dir: Path) -> list[dict]:
    """Walk eval-*/<config>/run-*/grading.json; collect eval_feedback.suggestions."""
    out: list[dict] = []
    seen: set[str] = set()
    for grading in benchmark_dir.glob("eval-*/*/run-*/grading.json"):
        try:
            data = json.loads(grading.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        fb = data.get("eval_feedback") or {}
        for s in fb.get("suggestions", []) or []:
            key = json.dumps(s, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
    return out


def render_scorecard(
    per_skill: list[dict],
    *,
    run_model: str,
    run_provider: str,
    run_runs_per_query: int,
    run_ts: str,
    run_git_head: str,
) -> str:
    lines: list[str] = []
    lines.append(SCORECARD_START)
    lines.append(
        "<!-- Auto-generated by scripts/run_all_evals.py. Do not edit between these markers. -->"
    )
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    lines.append(
        f"*Last updated: {run_ts} · provider: {run_provider} · model: {run_model} · "
        f"runs_per_query: {run_runs_per_query} · git HEAD: {run_git_head}*"
    )
    lines.append("")
    lines.append(
        "| Skill | Overall | Positive (TPR) | Negative (TNR) | Flakes | ∆ vs prev | Task pass rate (with / without / Δ) | Task Δ vs prev | Hygiene |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")

    for s in per_skill:
        if s.get("error"):
            lines.append(
                f"| {s['skill']} | ERROR | — | — | — | — | — | — | ⚠ |"
            )
            continue
        m = s["metrics"]
        ov = m["overall"]
        overall_cell = (
            f"{ov['passed']}/{ov['total']} ({pct(ov['accuracy'])}, "
            f"CI {pct(ov['ci_lo'])}–{pct(ov['ci_hi'])})"
        )
        tpr = f"{m['positive']['passed']}/{m['positive']['total']}"
        tnr = f"{m['negative']['passed']}/{m['negative']['total']}"
        delta_cell = fmt_delta_pp(ov["accuracy"], s.get("previous_accuracy"))
        task_cell = format_task_cell(s.get("task_benchmark"))
        task_delta_cell = format_task_regression(
            s.get("task_benchmark"), s.get("previous_task_mean")
        )
        hygiene_cell = "✓" if s["hygiene"].ok else "⚠"
        lines.append(
            f"| {s['skill']} | {overall_cell} | {tpr} | {tnr} | {m['flake_count']} | {delta_cell} | {task_cell} | {task_delta_cell} | {hygiene_cell} |"
        )

    lines.append("")
    lines.append(
        "> Hygiene warnings (`⚠`) render only when `quick_validate` fails, "
        "`triggering.json` has fewer than 8 positives/negatives, `evals.json` "
        "has fewer than 2 prompts or <3 expectations on any prompt, or the "
        "sibling-map parser reports unattributed negatives. When a row is "
        "`⚠`, the detail block surfaces the specific warnings."
    )
    lines.append("")

    for s in per_skill:
        if s.get("error"):
            lines.append(f"<details><summary>{s['skill']} detail</summary>")
            lines.append("")
            lines.append(f"**Error:** {s['error']}")
            lines.append("")
            lines.append("</details>")
            lines.append("")
            continue
        lines.extend(_render_skill_detail(s))
        lines.append("")

    lines.append(SCORECARD_END)
    return "\n".join(lines)


def _render_skill_detail(s: dict) -> list[str]:
    m = s["metrics"]
    out: list[str] = []
    out.append(f"<details><summary>{s['skill']} detail</summary>")
    out.append("")

    if s["hygiene"].warnings:
        out.append("**Hygiene warnings:**")
        out.append("")
        for w in s["hygiene"].warnings:
            out.append(f"- {w}")
        out.append("")

    if m["unmatched_indices"]:
        out.append(
            "**Unattributed negatives** (not found in sibling map — bucketed as `other`): "
            + ", ".join(str(i) for i in m["unmatched_indices"])
        )
        out.append("")

    if m["flakes"]:
        out.append("**Flaky queries** (trigger rate strictly between 0 and 1):")
        out.append("")
        for f in m["flakes"]:
            kind = "pos" if f["should_trigger"] else "neg"
            mark = "✅" if f["pass"] else "❌"
            rate = f"{f['trigger_rate']:.2f}"
            q = f["query"]
            if len(q) > 100:
                q = q[:97] + "…"
            out.append(f"- `{rate}`  {mark} {kind} `\"{q}\"`")
        out.append("")

    if m["leakage"]:
        out.append("**Per-sibling leakage** (negatives where we triggered when we shouldn't):")
        out.append("")
        out.append("| Decoy sibling | Leak rate |")
        out.append("|---|---|")
        for sibling, counts in sorted(m["leakage"].items()):
            out.append(f"| {sibling} | {counts['leaked']}/{counts['total']} |")
        out.append("")

    sweep = m.get("threshold_sweep") or {}
    if sweep:
        out.append("**Threshold sweep:**")
        out.append("")
        out.append("| Threshold | Overall | Positive | Negative |")
        out.append("|---|---|---|---|")
        for t in sorted(sweep.keys(), key=float):
            row = sweep[t]
            out.append(
                f"| {t} | {row['passed']}/{row['total']} | "
                f"{row['positive_passed']}/{row['positive_total']} | "
                f"{row['negative_passed']}/{row['negative_total']} |"
            )
        out.append("")

    history = s.get("history_recent") or []
    # Triggering-only rows (kind absent or not "task") for the trigger history table.
    trig_history = [r for r in history if r.get("kind") != "task"]
    if trig_history:
        out.append(f"**Run history** (last {len(trig_history)}, sourced from `misc/evals/history/{s['skill']}.jsonl`):")
        out.append("")
        out.append("| UTC | Overall | TPR | TNR | Model |")
        out.append("|---|---|---|---|---|")
        for row in trig_history:
            o = row.get("overall", {})
            p = row.get("positive", {})
            n = row.get("negative", {})
            out.append(
                f"| {row.get('ts', '—')} | {o.get('passed', '—')}/{o.get('total', '—')} | "
                f"{p.get('passed', '—')}/{p.get('total', '—')} | "
                f"{n.get('passed', '—')}/{n.get('total', '—')} | {row.get('model', '—')} |"
            )
        out.append("")

    bench = s.get("task_benchmark")
    if bench:
        rs = bench.get("run_summary", {})
        w = rs.get("with_skill", {}).get("pass_rate", {})
        wo = rs.get("without_skill", {}).get("pass_rate", {})
        out.append("**Task axis** (per-prompt averages from `workspace/latest/benchmark.json`):")
        out.append("")
        out.append(
            f"- with_skill: {w.get('mean', 0)*100:.0f}% ± {w.get('stddev', 0)*100:.0f}% "
            f"(min {w.get('min', 0)*100:.0f}%, max {w.get('max', 0)*100:.0f}%)"
        )
        out.append(
            f"- without_skill: {wo.get('mean', 0)*100:.0f}% ± {wo.get('stddev', 0)*100:.0f}% "
            f"(min {wo.get('min', 0)*100:.0f}%, max {wo.get('max', 0)*100:.0f}%)"
        )
        out.append(
            f"- lift: {(w.get('mean', 0) - wo.get('mean', 0))*100:+.0f}pp"
        )
        runs_per_prompt = bench.get("metadata", {}).get("runs_per_configuration", "?")
        out.append(f"- runs per (prompt × config): {runs_per_prompt}")
        out.append("")

        exp_rows = aggregate_expectations(bench)
        if exp_rows:
            out.append("**Per-expectation pass rate** (with_skill only):")
            out.append("")
            out.append("| Pass rate | Expectation |")
            out.append("|---|---|")
            for row in sorted(exp_rows, key=lambda r: (r["with_passed"] / r["with_total"]) if r["with_total"] else 0):
                wt = row["with_total"]
                wp = row["with_passed"]
                rate_s = f"{wp}/{wt}" if wt else "—"
                text = row["text"]
                if len(text) > 120:
                    text = text[:117] + "…"
                out.append(f"| {rate_s} | {text} |")
            out.append("")

        # Grader feedback aggregated from this run.
        latest = EVALS_ROOT / s["skill"] / "workspace" / "latest"
        if latest.exists():
            suggestions = collect_eval_feedback(latest.resolve())
            if suggestions:
                out.append("**Grader suggestions** (deduplicated across runs):")
                out.append("")
                for sug in suggestions[:10]:
                    assertion = sug.get("assertion")
                    reason = sug.get("reason", "")
                    if assertion:
                        out.append(f"- on `\"{assertion[:90]}…\"`: {reason}")
                    else:
                        out.append(f"- {reason}")
                out.append("")

    out.append("</details>")
    return out


def splice_readme(readme_path: Path, rendered: str) -> None:
    """Replace the SCORECARD_START…SCORECARD_END block in place. Raises if
    the markers are missing — the README edit is not auto-self-healing.
    """
    text = readme_path.read_text()
    pattern = re.compile(
        re.escape(SCORECARD_START) + r".*?" + re.escape(SCORECARD_END),
        re.DOTALL,
    )
    if not pattern.search(text):
        raise RuntimeError(
            f"SCORECARD markers missing in {readme_path}; add both "
            f"{SCORECARD_START} and {SCORECARD_END} before running score."
        )
    # Use a lambda so regex-metacharacters in `rendered` (e.g. \d coming from
    # a grader-produced regex in a suggestion) don't get interpreted as
    # replacement-string backreferences.
    new_text = pattern.sub(lambda _m: rendered, text, count=1)
    readme_path.write_text(new_text)


# ---------- workspace persistence --------------------------------------------


def workspace_run_dir(skill: str, ts: str) -> Path:
    return EVALS_ROOT / skill / "workspace" / "runs" / ts


def persist_artifacts(skill: str, ts: str, raw: dict, metrics: dict) -> Path:
    run_dir = workspace_run_dir(skill, ts)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "triggering.json").write_text(json.dumps(raw, indent=2))
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return run_dir


def latest_workspace_metrics(skill: str) -> dict | None:
    """For --skip-triggering. Returns the most recent metrics.json under
    <skill>/workspace/runs/ or None.
    """
    runs_dir = EVALS_ROOT / skill / "workspace" / "runs"
    if not runs_dir.exists():
        return None
    candidates = sorted(
        (p for p in runs_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for c in candidates:
        m = c / "metrics.json"
        if m.exists():
            return json.loads(m.read_text())
    return None


# ---------- per-skill driver --------------------------------------------------


def process_skill(
    skill: str,
    *,
    model_flag: str | None,
    runs_flag: int | None,
    workers_flag: int | None,
    skip_triggering: bool,
    resolved_model: str,
    resolved_provider: str,
    resolved_runs: int,
) -> dict:
    """Returns a dict shaped as the scorecard row needs."""
    hygiene = hygiene_check(skill)

    # Read triggering.json and sibling map up front (needed even when skipping).
    triggering = json.loads((EVALS_ROOT / skill / "triggering.json").read_text())
    readme = (EVALS_ROOT / skill / "README.md").read_text()
    sibling_entries = parse_sibling_map(readme)
    if not sibling_entries:
        hygiene.ok = False
        hygiene.warnings.append(
            "sibling map empty — missing SIBLING_MAP markers or unparseable bullets"
        )
    sibling_map, matched, unmatched = build_index_to_sibling(sibling_entries, triggering)
    if unmatched:
        hygiene.ok = False
        hygiene.warnings.append(
            f"sibling map does not attribute negative indices: {unmatched}"
        )

    history = read_history(skill)
    # Find the last triggering row — task rows don't have overall/positive/negative.
    trig_rows = [r for r in history if r.get("kind") != "task"]
    prev_accuracy: float | None = None
    if trig_rows:
        prev_accuracy = trig_rows[-1].get("overall", {}).get("accuracy")

    task_benchmark = load_task_benchmark(skill)
    prev_task_mean = previous_task_mean(skill)

    if skip_triggering:
        metrics = latest_workspace_metrics(skill)
        if metrics is None:
            return {
                "skill": skill,
                "hygiene": hygiene,
                "error": "--skip-triggering but no prior workspace/runs/ artefacts",
            }
        return {
            "skill": skill,
            "hygiene": hygiene,
            "metrics": metrics,
            "previous_accuracy": prev_accuracy,
            "history_recent": list(reversed(history[-5:])),
            "task_benchmark": task_benchmark,
            "previous_task_mean": prev_task_mean,
        }

    snapshot = build_snapshot(
        skill,
        model=model_flag or resolved_model,
        provider=resolved_provider,
        runs_per_query=runs_flag if runs_flag is not None else resolved_runs,
        num_workers=workers_flag if workers_flag is not None else 10,
    )
    rc, stdout, stderr = run_triggering(
        skill,
        model=model_flag,
        runs_per_query=runs_flag,
        num_workers=workers_flag,
    )
    if rc != 0:
        return {
            "skill": skill,
            "hygiene": hygiene,
            "error": (stderr.strip() or stdout.strip() or f"make exited {rc}")[-400:],
            "make_failure": True,
        }
    try:
        raw = extract_run_eval_json(stdout)
    except Exception as e:
        return {
            "skill": skill,
            "hygiene": hygiene,
            "error": f"could not parse run_eval JSON: {e}",
            "make_failure": True,
        }

    metrics = enrich_metrics(raw, triggering, sibling_map, unmatched, snapshot)
    run_dir = persist_artifacts(skill, snapshot["started_at"], raw, metrics)

    append_history(skill, history_compact_entry(metrics))

    # Re-read history after append so the detail block reflects the row we just wrote.
    history_after = read_history(skill)

    return {
        "skill": skill,
        "hygiene": hygiene,
        "metrics": metrics,
        "previous_accuracy": prev_accuracy,
        "history_recent": list(reversed(history_after[-5:])),
        "run_dir": str(run_dir),
        "task_benchmark": task_benchmark,
        "previous_task_mean": prev_task_mean,
    }


# ---------- main --------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skill", help="Run only this skill (iteration mode)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered scorecard to stdout; do not rewrite README",
    )
    # No defaults — see module docstring.
    parser.add_argument("--model", default=None)
    parser.add_argument("--runs-per-query", type=int, default=None, dest="runs_per_query")
    parser.add_argument("--num-workers", type=int, default=None, dest="num_workers")
    parser.add_argument(
        "--threshold-sweep",
        action="store_true",
        help="Reserved: the sweep is always computed; this flag is accepted for forward-compat",
    )
    parser.add_argument(
        "--skip-triggering",
        action="store_true",
        help="Skip `make triggering-<skill>`; rebuild scorecard from latest workspace/runs/",
    )
    parser.add_argument(
        "--fail-on-regression",
        type=float,
        default=None,
        help="Exit 2 if any skill's overall accuracy dropped by > N percentage points vs its previous run",
    )
    args = parser.parse_args()

    skills = discover_skills()
    if args.skill:
        if args.skill not in skills:
            print(
                f"unknown skill: {args.skill} (known: {', '.join(skills)})",
                file=sys.stderr,
            )
            sys.exit(1)
        skills = [args.skill]

    if not skills:
        print("no skills discovered under misc/evals/", file=sys.stderr)
        return 1

    # Resolve Makefile defaults once so the scorecard metadata is accurate.
    resolved_provider = resolve_makefile_default("PROVIDER") or "bedrock"
    default_model = "global.anthropic.claude-opus-4-7" if resolved_provider == "bedrock" else "claude-opus-4-7"
    resolved_model = args.model or resolve_makefile_default("MODEL") or default_model
    resolved_runs = (
        args.runs_per_query
        if args.runs_per_query is not None
        else int(resolve_makefile_default("RUNS_PER_QUERY") or 3)
    )

    per_skill: list[dict] = []
    make_failed = False
    regression_breach = False

    for skill in skills:
        print(f"[run_all_evals] {skill}", file=sys.stderr)
        row = process_skill(
            skill,
            model_flag=args.model,
            runs_flag=args.runs_per_query,
            workers_flag=args.num_workers,
            skip_triggering=args.skip_triggering,
            resolved_model=resolved_model,
            resolved_provider=resolved_provider,
            resolved_runs=resolved_runs,
        )
        per_skill.append(row)
        if row.get("make_failure"):
            make_failed = True

        # Regression check — trigger axis.
        if args.fail_on_regression is not None and row.get("metrics") and row.get("previous_accuracy") is not None:
            current = row["metrics"]["overall"]["accuracy"]
            delta_pp = (current - row["previous_accuracy"]) * 100
            if delta_pp < -abs(args.fail_on_regression):
                regression_breach = True
                print(
                    f"[run_all_evals] triggering regression on {skill}: "
                    f"{delta_pp:.1f}pp (threshold {-abs(args.fail_on_regression)}pp)",
                    file=sys.stderr,
                )

        # Regression check — task axis.
        if args.fail_on_regression is not None and row.get("task_benchmark") and row.get("previous_task_mean") is not None:
            current_task = (
                row["task_benchmark"].get("run_summary", {})
                .get("with_skill", {}).get("pass_rate", {}).get("mean", 0)
            )
            task_delta_pp = (current_task - row["previous_task_mean"]) * 100
            if task_delta_pp < -abs(args.fail_on_regression):
                regression_breach = True
                print(
                    f"[run_all_evals] task regression on {skill}: "
                    f"{task_delta_pp:.1f}pp (threshold {-abs(args.fail_on_regression)}pp)",
                    file=sys.stderr,
                )

    run_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    rendered = render_scorecard(
        per_skill,
        run_model=args.model or resolved_model,
        run_provider=resolved_provider,
        run_runs_per_query=resolved_runs,
        run_ts=run_ts,
        run_git_head=git_head_short(),
    )

    if args.dry_run:
        print(rendered)
    else:
        readme = EVALS_ROOT / "README.md"
        splice_readme(readme, rendered)
        print(f"[run_all_evals] rewrote {readme}", file=sys.stderr)

    if make_failed:
        return 1
    if regression_breach:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
