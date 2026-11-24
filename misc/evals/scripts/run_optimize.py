#!/usr/bin/env python3
"""Description optimizer grounded in leakage data (issue 98, eval signal axis 3).

Reads a skill's saved triggering results (run_triggering.py output), marks
each should-not prompt with the sibling that owns it per the skill's
SIBLING_MAP (misc/evals/<skill>/README.md), and hands the result to the
vendored skills/skill-creator/scripts/improve_description.py through its
`--eval-results` flag. That script asks `claude -p` for a tighter description
and prints JSON with the proposal; this script relays it.

Leakage here means a run where the target fired on a prompt a sibling owns
(a false trigger), or missed one of its own prompts. The triggering sandbox
stages only the target skill, so a miss shows that the target did not fire,
not which sibling would have.

Why improve_description.py and not run_loop.py: run_loop.py scores each
iteration with the vendored run_eval.py, whose detector this repo replaced
with run_triggering.py (misc/evals/Makefile, section D: "invoking it here
would feed noise into the optimizer"). improve_description.py only reads a
results file in run_eval.py's output schema, which run_triggering.py keeps.

Inputs:
  --skill NAME        skill under misc/evals/ and skills/
  --results PATH      run_triggering.py output; default the newest
                      misc/evals/<skill>/workspace/runs/*/triggering.json
                      (written by run_all_evals.py)

Usage:
  run_optimize.py --skill eks-recon --build-only     # write the eval results, no model call
  run_optimize.py --skill eks-recon --model <id>     # also propose a description

The proposal is not validated here: re-run `make triggering-<skill>` on the
proposed description before adopting it.

Exit codes: 0 ok, 1 bad input, else improve_description.py's exit code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
EVALS_ROOT = SCRIPTS_DIR.parent
REPO_ROOT = EVALS_ROOT.parent.parent
SKILL_CREATOR = REPO_ROOT / "skills" / "skill-creator"

sys.path.insert(0, str(SCRIPTS_DIR))
from run_all_evals import build_index_to_sibling, parse_sibling_map  # noqa: E402

# Fields improve_description.py reads from each results row.
ROW_KEYS = ("query", "should_trigger", "pass", "triggers", "runs", "trigger_rate")


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


def build_eval_results(raw: dict, owners: dict[str, str]) -> dict:
    """run_triggering.py output trimmed to what improve_description.py reads,
    with each owned negative's query suffixed by its owner so the leakage
    reaches the improvement prompt."""
    rows = []
    for r in raw["results"]:
        row = {k: r[k] for k in ROW_KEYS if k in r}
        owner = owners.get(r["query"])
        if not r["should_trigger"] and owner:
            label = "no sibling, out of scope" if owner == "other" else f"owned by sibling `{owner}`"
            row["query"] = f"{r['query']} [{label}]"
        rows.append(row)
    passed = sum(1 for r in rows if r["pass"])
    leaks = [r["query"] for r in rows if not r["should_trigger"] and not r["pass"]]
    misses = [r["query"] for r in rows if r["should_trigger"] and not r["pass"]]
    return {
        "skill_name": raw.get("skill_name"),
        "description": raw["description"],
        "results": rows,
        "summary": {"passed": passed, "failed": len(rows) - passed, "total": len(rows)},
        "leakage": {"false_triggers": leaks, "missed_triggers": misses},
    }


def improve_cmd(eval_results: Path, skill_dir: Path, model: str, history: str | None) -> list[str]:
    """Command line for the vendored improver (run with cwd=skills/skill-creator,
    since it imports `scripts.utils`)."""
    cmd = [sys.executable, "-B", "-m", "scripts.improve_description",
           "--eval-results", str(eval_results), "--skill-path", str(skill_dir),
           "--model", model]
    if history:
        cmd += ["--history", history]
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skill", required=True, help="Skill name (misc/evals/<skill>, skills/<skill>)")
    parser.add_argument("--results", default=None,
                        help="run_triggering.py output JSON (default: newest workspace run)")
    parser.add_argument("--out", default=None,
                        help="Where to write the eval results (default: misc/evals/<skill>/workspace/optimize/<UTC>.json)")
    parser.add_argument("--build-only", action="store_true",
                        help="Write the eval results and stop; no model call")
    parser.add_argument("--model", default=None, help="Model for improve_description.py (required unless --build-only)")
    parser.add_argument("--history", default=None, help="Passed through to improve_description.py --history")
    args = parser.parse_args(argv)

    skill_dir = REPO_ROOT / "skills" / args.skill
    if not (EVALS_ROOT / args.skill / "triggering.json").exists() or not (skill_dir / "SKILL.md").exists():
        print(f"error: need misc/evals/{args.skill}/triggering.json and skills/{args.skill}/SKILL.md",
              file=sys.stderr)
        return 1
    results = Path(args.results) if args.results else latest_results(args.skill)
    if results is None or not results.exists():
        print(f"error: no triggering results; run `make triggering-{args.skill}` and save its "
              "JSON, or pass --results", file=sys.stderr)
        return 1
    if not args.build_only and not args.model:
        print("error: --model is required unless --build-only", file=sys.stderr)
        return 1

    eval_results = build_eval_results(json.loads(results.read_text()), sibling_owners(args.skill))
    out = Path(args.out) if args.out else (
        EVALS_ROOT / args.skill / "workspace" / "optimize" / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(eval_results, indent=2))
    leak = eval_results["leakage"]
    print(f"{out}: {len(leak['false_triggers'])} false triggers, "
          f"{len(leak['missed_triggers'])} missed triggers", file=sys.stderr)
    if args.build_only:
        return 0
    return subprocess.run(improve_cmd(out, skill_dir, args.model, args.history),
                          cwd=SKILL_CREATOR).returncode


if __name__ == "__main__":
    sys.exit(main())
