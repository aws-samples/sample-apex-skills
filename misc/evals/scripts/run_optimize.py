#!/usr/bin/env python3
"""Description optimizer grounded in leakage data (issue 98, eval signal axis 3).

Reads a skill's saved triggering results (run_triggering.py output), marks
each should-not prompt with the sibling that owns it per the skill's
SIBLING_MAP (misc/evals/<skill>/README.md), and hands the result to the
vendored skills/skill-creator/scripts/improve_description.py through its
`--eval-results` flag. That script asks `claude -p` for a tighter description.
This script then runs a validation of the proposal in a sandbox before
surfacing it (see Output for what it does and does not judge): it stages a temp copy of the skill with the proposed description and runs
run_triggering.py on it with `--skill-path`, against the skill's own
triggering.json.

Leakage counts, printed on stderr: false triggers are should-not prompts
that fired, owned by a sibling or out of scope; missed triggers are the
skill's own prompts that did not fire. Rows with no valid run (runs 0, or a
fail_reason that is not about the trigger rate) are dropped first and
counted on their own line, so infra failures do not reach the improver.
The triggering sandbox stages only the target skill, so a miss shows that
the target did not fire, not which sibling would have.

Why improve_description.py and not run_loop.py: run_loop.py scores each
iteration with the vendored run_eval.py, whose detector this repo replaced
with run_triggering.py (misc/evals/Makefile, section D: "invoking it here
would feed noise into the optimizer"). improve_description.py only reads a
results file in run_eval.py's output schema, which run_triggering.py keeps.

Inputs:
  --skill NAME        skill under misc/evals/ and skills/
  --results PATH      run_triggering.py output for that skill; default the
                      newest misc/evals/<skill>/workspace/runs/*/triggering.json
                      (written by run_all_evals.py)

Usage:
  run_optimize.py --skill eks-recon --build-only     # write the eval results, no model call
  run_optimize.py --skill eks-recon --model <id>     # propose, validate, surface

`--model` is used by both model calls. The improver runs `claude -p` with
the caller's environment, so run it only under the eval account's
Bedrock-only role, never with a host's admin credentials.
run_triggering.py mints the eval-role session itself.

Output: the proposal is written beside the eval results file
(<out>.proposal.json) before the validation run, so it is kept when that
run fails. On success stdout is JSON with the proposed description, the
baseline summary and the validation run's summary; the validation run's
full output is written beside the eval results file (<out>.validation.json).
The script reports both summaries and does not judge between them, and
they are not counted alike: the baseline counts the valid rate-based rows
of the saved run (after the drop above); the validation counts every row
of the current triggering.json, invalid runs as fails, at run_triggering.py's
defaults (harness claude, 3 runs per query), whatever the saved run used.

Exit codes: 0 ok, 1 bad input (no valid rows left included), else the
failing step's exit code.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
EVALS_ROOT = SCRIPTS_DIR.parent
REPO_ROOT = EVALS_ROOT.parent.parent
SKILL_CREATOR = REPO_ROOT / "skills" / "skill-creator"

sys.path.insert(0, str(SCRIPTS_DIR))
from run_all_evals import build_index_to_sibling, parse_sibling_map  # noqa: E402

# Fields improve_description.py reads from each results row.
ROW_KEYS = ("query", "should_trigger", "pass", "triggers", "runs")
# run_triggering.py fail_reason values that are about the trigger rate.
RATE_REASONS = (None, "trigger rate below threshold", "trigger rate at or above threshold")


def latest_results(skill: str) -> Path | None:
    """Newest saved triggering run for the skill, or None."""
    runs = sorted((EVALS_ROOT / skill / "workspace" / "runs").glob("*/triggering.json"))
    return runs[-1] if runs else None


def sibling_owners(skill: str) -> dict[str, str]:
    """Map each should-not query in triggering.json to its SIBLING_MAP owner."""
    triggering = json.loads((EVALS_ROOT / skill / "triggering.json").read_text())
    readme = EVALS_ROOT / skill / "README.md"
    entries = parse_sibling_map(readme.read_text()) if readme.exists() else []
    mapping, _, _ = build_index_to_sibling(entries, triggering)
    return {triggering[i]["query"]: owner for i, owner in mapping.items()}


def valid_rows(raw: dict) -> tuple[list[dict], int]:
    """Rows with at least one valid run and a rate-based verdict, and the
    count dropped."""
    keep = [r for r in raw["results"] if r.get("runs") and r.get("fail_reason") in RATE_REASONS]
    return keep, len(raw["results"]) - len(keep)


def build_eval_results(rows: list[dict], description: str, owners: dict[str, str]) -> dict:
    """Rows trimmed to what improve_description.py reads, with each owned
    negative's query suffixed by its owner so the leakage reaches the
    improvement prompt."""
    out = []
    for r in rows:
        row = {k: r[k] for k in ROW_KEYS if k in r}
        owner = owners.get(r["query"])
        if not r["should_trigger"] and owner:
            label = "no sibling, out of scope" if owner == "other" else f"owned by sibling `{owner}`"
            row["query"] = f"{r['query']} [{label}]"
        out.append(row)
    passed = sum(1 for r in out if r["pass"])
    return {"description": description, "results": out,
            "summary": {"passed": passed, "failed": len(out) - passed, "total": len(out)}}


def improve_cmd(eval_results: Path, skill_dir: Path, model: str) -> list[str]:
    """Command line for the vendored improver (run with cwd=skills/skill-creator,
    since it imports `scripts.utils`)."""
    return [sys.executable, "-B", "-m", "scripts.improve_description",
            "--eval-results", str(eval_results), "--skill-path", str(skill_dir), "--model", model]


def with_description(skill_md: str, description: str) -> str:
    """SKILL.md text with its frontmatter `description:` (and any indented
    continuation lines) replaced by the given one, as a quoted scalar."""
    m = re.match(r"---\n(.*?)\n---\n", skill_md, re.S)
    if not m:
        raise ValueError("SKILL.md has no frontmatter")
    fm, n = re.subn(r"^description:.*(?:\n[ \t]+.*)*", lambda _: "description: " + json.dumps(description),
                    m.group(1), flags=re.M)
    if n != 1:
        raise ValueError(f"SKILL.md frontmatter has {n} description keys")
    return f"---\n{fm}\n---\n" + skill_md[m.end():]


def validate(skill: str, skill_dir: Path, description: str, model: str) -> subprocess.CompletedProcess:
    """Run run_triggering.py on a temp copy of the skill carrying the
    proposed description; the copy is removed afterwards."""
    tmp = Path(tempfile.mkdtemp(prefix="optimize-"))
    try:
        staged = tmp / "skills" / skill
        shutil.copytree(skill_dir, staged)
        md = staged / "SKILL.md"
        md.write_text(with_description(md.read_text(), description))
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_DIR / "run_triggering.py"),
             "--eval-set", str(EVALS_ROOT / skill / "triggering.json"),
             "--skill-path", str(staged), "--model", model],
            stdout=subprocess.PIPE, text=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skill", required=True, help="Skill name (misc/evals/<skill>, skills/<skill>)")
    parser.add_argument("--results", default=None,
                        help="run_triggering.py output JSON (default: newest workspace run)")
    parser.add_argument("--out", default=None,
                        help="Where to write the eval results (default: misc/evals/<skill>/workspace/optimize/<UTC>.json)")
    parser.add_argument("--build-only", action="store_true",
                        help="Write the eval results and stop; no model call")
    parser.add_argument("--model", default=None,
                        help="Model for the improver and the validation run (required unless --build-only). "
                             "The improver runs `claude -p` with the caller's environment: run it only under "
                             "the eval account's Bedrock-only role, never with a host's admin credentials")
    args = parser.parse_args(argv)

    skill_dir = REPO_ROOT / "skills" / args.skill
    triggering = EVALS_ROOT / args.skill / "triggering.json"
    if not triggering.exists() or not (skill_dir / "SKILL.md").exists():
        print(f"error: need misc/evals/{args.skill}/triggering.json and skills/{args.skill}/SKILL.md",
              file=sys.stderr)
        return 1
    results = Path(args.results) if args.results else latest_results(args.skill)
    if results is None or not results.exists():
        print(f"error: no triggering results; run `make -s triggering-{args.skill} > <file>` and pass "
              "--results <file>, or run run_all_evals.py, whose saved run is the default input",
              file=sys.stderr)
        return 1
    if not args.build_only and not args.model:
        print("error: --model is required unless --build-only", file=sys.stderr)
        return 1

    raw = json.loads(results.read_text())
    if raw.get("skill_name") not in (None, args.skill):
        print(f"error: {results} is a run of {raw['skill_name']}, not {args.skill}", file=sys.stderr)
        return 1
    current = {c["query"] for c in json.loads(triggering.read_text())}
    stale = [r["query"] for r in raw["results"] if r["query"] not in current]
    if stale:
        print(f"warning: {len(stale)} queries are not in the current triggering.json", file=sys.stderr)

    rows, dropped = valid_rows(raw)
    if not rows:
        print(f"error: no rows with a valid run in {results} ({dropped} dropped)", file=sys.stderr)
        return 1
    eval_results = build_eval_results(rows, raw["description"], sibling_owners(args.skill))
    out = (Path(args.out) if args.out else (
        EVALS_ROOT / args.skill / "workspace" / "optimize" / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(eval_results, indent=2))
    fails = [r for r in eval_results["results"] if not r["pass"]]
    print(f"{out}: {sum(1 for r in fails if not r['should_trigger'])} false triggers, "
          f"{sum(1 for r in fails if r['should_trigger'])} missed triggers", file=sys.stderr)
    if dropped:
        print(f"{dropped} rows with no valid run dropped", file=sys.stderr)
    if args.build_only:
        return 0

    improved = subprocess.run(improve_cmd(out, skill_dir, args.model), cwd=SKILL_CREATOR,
                              stdout=subprocess.PIPE, text=True)
    if improved.returncode:
        return improved.returncode
    proposal = json.loads(improved.stdout)["description"]
    out.with_name(out.stem + ".proposal.json").write_text(json.dumps({"description": proposal}, indent=2))
    checked = validate(args.skill, skill_dir, proposal, args.model)
    if checked.returncode:
        return checked.returncode
    validation = out.with_name(out.stem + ".validation.json")
    validation.write_text(checked.stdout)
    print(json.dumps({"description": proposal, "baseline": eval_results["summary"],
                      "validation": json.loads(checked.stdout)["summary"],
                      "validation_results": str(validation)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
