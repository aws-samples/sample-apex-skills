#!/usr/bin/env python3
"""Drive candidate C1 of the runner trial: the homegrown runner in
misc/evals/scripts/ on the claude harness, one case and one arm at a time.

It calls the runner's own functions (run_task_evals.run_subject,
run_task_evals.run_grader, run_task_evals._resolve_makefile_default,
artifact_validation.validate_run, run_triggering.run_single_query,
run_triggering.read_skill_meta, knowledge_assertions.evaluate,
skilleval_config.load_config, elicitation.ElicitationConfig.from_dict) for the
seven cases in cases.md. Each case is scored on its single pass condition
(cases.md); the source suites' other expectations are not.

Default: a dry run that prints the planned runs and makes no model call.
--paid starts the runs. It refuses to start without --out (empty or new),
--spend-limit-usd (finite, above 0) and --credential-note (recorded, not
enforced), and stops before the next run once the subjects' recorded cost
reaches the limit. The stop counts only the subjects' recorded cost: grader
calls, T6 query runs and a run that times out or crashes before its first
result event add nothing; on Claude Code older than 2.1.277, T5's earlier
turns add nothing; and the run that crosses the limit completes. The limit is
per invocation.

Do not run --paid on the trial host: every subject can reach the host's AWS
credentials (cases.md, Credentials and permissions).

Output (--out): runs.jsonl, one line per run (case, arm, run, status, pass,
tokens, duration_ms, wall_seconds, total_cost_usd, reason), summary.json
(pass count per case and arm, for score-sheet.md S1 and S2, plus a T6
"both_queries" cell counting runs k where both query arms passed at run k),
and each run's runner files under <case>/<arm>/run-<k>/. S2 reads `pass`
over `ran`, and n/a when `ran` is 0: "cannot run", "not run" (spend stop) and
"error" runs count in `runs` but not in `ran`.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "misc" / "evals" / "scripts"
PIN = "7efa0776"        # case text as it stands at this commit (cases.md)
OLD = "0678d921"        # tag v1.3.0, the old arm on T1 to T4 (cases.md)
RUNS = 3
TRIGGER_TIMEOUT = 90    # run_triggering.py --timeout default
GRADER_TIMEOUT = 600    # run_task_evals.py --grader-timeout default

T4_PASS = ("The headline rating field reads NOT READY (score 59 or lower, the "
           "hard-blocker cap), not a READY found by substring elsewhere in the "
           "report, and subnet-aaa (3 available IPs) is named as the blocker.")

# grade: (kind, value). Kinds: suite (run_grader on the suite expectations
# that contain each string), text (run_grader on this one expectation),
# artifact (validate_run on the one assertion named by key and value),
# multiturn (resumed at least once and the suite's first knowledge
# assertion holds), trigger (run_single_query on query index, should_trigger).
CASES = [
    {"id": "T1", "skill": "eks-security", "eval_id": 4,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("suite", ["Gives the verdict exposed for both"])},
    {"id": "T2", "skill": "eks-recon", "eval_id": 3,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("artifact", ("structural", "pattern", r"Changed[ \t]*\|[^|\n]*blue[^|\n]*desired_size"))},
    {"id": "T3", "skill": "eks-build", "eval_id": 1,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("artifact", ("validators", "path", "skills/eks-build/scripts/validate_project.sh"))},
    {"id": "T4", "skill": "eks-upgrade-check", "eval_id": 4,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("text", T4_PASS)},
    {"id": "T5", "skill": "eks-build", "eval_id": 3,
     "arms": ("with_skill", "without_skill"),
     "grade": ("multiturn", 0)},
    {"id": "T6", "skill": "eks-mcp-server", "eval_id": None,
     "arms": ("with_skill_q3", "with_skill_q18"),
     "grade": ("trigger", {"with_skill_q3": (3, True), "with_skill_q18": (18, False)})},
    {"id": "T7", "skill": "eks-recon", "eval_id": 1, "live": True,
     "arms": ("with_skill", "without_skill"),
     "grade": ("suite", ["cluster version and platform version",
                         "primary compute strategy",
                         "EKS-managed add-ons with their installed versions",
                         "IaC tool managing the cluster"])},
]
CASE_IDS = [c["id"] for c in CASES]


def load_runner() -> SimpleNamespace:
    """Import the runner's functions. No model call happens on import."""
    sys.path.insert(0, str(SCRIPTS))
    import artifact_validation
    import knowledge_assertions
    import run_task_evals
    import run_triggering
    import skilleval_config
    return SimpleNamespace(
        run_subject=run_task_evals.run_subject,
        run_grader=run_task_evals.run_grader,
        validate_run=artifact_validation.validate_run,
        evaluate_knowledge=knowledge_assertions.evaluate,
        run_single_query=run_triggering.run_single_query,
        read_skill_meta=run_triggering.read_skill_meta,
        subject_timeout=lambda skill: skilleval_config.load_config(skill).timeout,
        default_model=lambda: (run_task_evals._resolve_makefile_default("MODEL")
                               or "global.anthropic.claude-opus-4-6-v1"),  # run_task_evals.py:1025
    )


def case_source(case: dict) -> Path:
    name = "triggering.json" if case["grade"][0] == "trigger" else "evals.json"
    return REPO_ROOT / "misc" / "evals" / case["skill"] / name


def pinned_paths(case: dict) -> list[str]:
    """Repo paths whose text must equal PIN: the case file, its fixtures and the skill."""
    paths = [str(case_source(case).relative_to(REPO_ROOT)), f"skills/{case['skill']}"]
    if case["eval_id"] is not None:
        files = REPO_ROOT / "misc" / "evals" / case["skill"] / "files"
        paths += [str((files / d).relative_to(REPO_ROOT)) for d in ("shared", f"eval-{case['eval_id']}")
                  if (files / d).exists()]
    return paths


def check_pin(cases: list[dict]) -> list[str]:
    """Paths that differ from PIN or hold untracked or ignored files (git, no model call).

    An ignored file is staged into the subject's sandbox too, so it counts;
    __pycache__/ is Python's bytecode cache, holds no case text and is left out.
    """
    changed = []
    for case in cases:
        for p in pinned_paths(case):
            r = subprocess.run(["git", "-C", str(REPO_ROOT), "diff", "--quiet", PIN, "--", p])
            st = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--ignored", "--", p],
                                capture_output=True, text=True)
            extra = [l for l in st.stdout.splitlines() if "__pycache__/" not in l]
            if (r.returncode != 0 or st.returncode != 0 or extra) and p not in changed:
                changed.append(p)
    return changed


def load_case(case: dict) -> dict:
    data = json.loads(case_source(case).read_text())
    if case["grade"][0] == "trigger":
        return {"queries": data}
    matches = [e for e in data["evals"] if e["id"] == case["eval_id"]]
    if len(matches) != 1:
        raise ValueError(f"{case['id']}: {len(matches)} evals with id {case['eval_id']}")
    return matches[0]


def suite_expectations(case: dict, spec: dict) -> list[str]:
    value = case["grade"][1]
    picked = [e for e in spec["expectations"] if any(v in e for v in value)]
    if len(picked) != len(value):
        raise ValueError(f"{case['id']}: {len(picked)} suite expectations match, want {len(value)}")
    return picked


def artifact_pick(case: dict, spec: dict) -> dict:
    section, key, needle = case["grade"][1]
    cfg = spec["artifact_assertions"]
    picked = [a for a in cfg.get(section, []) if needle in str(a.get(key, ""))]
    if len(picked) != 1:
        raise ValueError(f"{case['id']}: {len(picked)} {section} entries match {needle!r}")
    return {"root_glob": cfg.get("root_glob"), section: picked}


def check_specs(cases: list[dict]) -> dict:
    """Load each case and resolve its pass-condition selector before any run."""
    specs = {}
    for case in cases:
        spec = specs[case["id"]] = load_case(case)
        kind, value = case["grade"]
        if kind == "suite":
            suite_expectations(case, spec)
        elif kind == "artifact":
            artifact_pick(case, spec)
        elif kind == "multiturn" and not (spec.get("elicitation") and len(spec.get("knowledge_assertions", [])) > value):
            raise ValueError(f"{case['id']}: no elicitation block or knowledge assertion {value}")
        elif kind == "trigger":
            for arm, (idx, should) in value.items():
                if spec["queries"][idx].get("should_trigger") is not should:
                    raise ValueError(f"{case['id']} {arm}: query {idx} should_trigger is not {should}")
    return specs


def plan_runs(cases: list[dict]) -> list[dict]:
    """Every (case, arm, run) with the exact runner call it makes."""
    plan = []
    for case in cases:
        kind, value = case["grade"]
        for arm in case["arms"]:
            if kind == "trigger":
                idx, should = value[arm]
                call = (f"run_triggering.run_single_query(query=triggering.json[{idx}], "
                        f"skill_name='{case['skill']}', repo_skill_dir=skills/{case['skill']}, "
                        f"timeout={TRIGGER_TIMEOUT}); pass if triggered is {should}")
            else:
                skill_dir = (f"skills/{case['skill']} at {OLD}" if arm == "old_skill"
                             else f"skills/{case['skill']}")
                call = (f"run_task_evals.run_subject(prompt=evals.json id {case['eval_id']}, "
                        f"skill_name='{case['skill']}', repo_skill_dir={skill_dir}, "
                        f"with_skill={arm != 'without_skill'}"
                        f"{', extra_env KUBECONFIG' if case.get('live') else ''})")
                if kind == "suite":
                    call += f"; run_task_evals.run_grader(expectations=the suite's lines with {value})"
                elif kind == "text":
                    call += "; run_task_evals.run_grader(expectations=[the case's pass condition])"
                elif kind == "artifact":
                    call += f"; artifact_validation.validate_run(outputs, {{{value[0]}: [the {value[1]} {value[2]!r} entry]}})"
                else:
                    call += (f"; resumed (2+ result events) and knowledge_assertions.evaluate("
                             f"final text, [knowledge_assertions[{value}]])")
            for k in range(1, RUNS + 1):
                plan.append({"case": case["id"], "arm": arm, "run": k, "call": call})
    return plan


@contextlib.contextmanager
def old_skill_dir(skill: str):
    """skills/<skill> as it stands at OLD, extracted to a temp dir (git, no model call)."""
    tmp = Path(tempfile.mkdtemp(prefix="drive-c1-old-"))
    try:
        archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", OLD, f"skills/{skill}"],
                                 capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            # filter= needs tarfile.data_filter; /usr/bin/python3 3.9.16 here has none
            tar.extractall(tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        yield tmp / "skills" / skill
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def last_result(events_path: Path) -> tuple[dict, int]:
    """The last result event and the count of result events in events.jsonl."""
    results = []
    if events_path.exists():
        for line in events_path.read_text().splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                evt = json.loads(line)
                if evt.get("type") == "result":
                    results.append(evt)
    return (results[-1] if results else {}), len(results)


def grade_task(runner, case: dict, spec: dict, subj: dict, run_dir: Path, model: str) -> tuple[bool | None, str]:
    kind, value = case["grade"]
    outputs, transcript = Path(subj["outputs_dir"]), Path(subj["transcript_path"])
    if kind in ("suite", "text"):
        expectations = [value] if kind == "text" else suite_expectations(case, spec)
        grading = runner.run_grader(expectations=expectations, transcript_path=transcript,
                                    outputs_dir=outputs, run_dir=run_dir, model=model, timeout=GRADER_TIMEOUT)
        if "error" in grading:
            return None, f"grader: {grading['error']}"
        if len(grading["expectations"]) != len(expectations):
            return None, f"grader returned {len(grading['expectations'])} expectations, want {len(expectations)}"
        ok = all(e.get("passed") for e in grading["expectations"])
        return ok, f"grader {sum(bool(e.get('passed')) for e in grading['expectations'])}/{len(expectations)}"
    if kind == "artifact":
        res = runner.validate_run(outputs_dir=outputs, assertions_config=artifact_pick(case, spec), repo_root=REPO_ROOT)
        passed = res.structural_passed + res.validators_passed
        failed = res.structural_failed + res.validators_failed
        return (passed == 1 and failed == 0), f"artifact {passed} passed, {failed} failed"
    if kind == "multiturn":
        final, n_results = last_result(run_dir / "events.jsonl")
        ka = runner.evaluate_knowledge(final.get("result") or "", [spec["knowledge_assertions"][value]])
        return (n_results >= 2 and ka.failed == 0 and ka.passed == 1), f"result events {n_results}, pattern {ka.passed}/1"
    raise ValueError(f"{case['id']}: unknown grade kind {kind}")


def run_one(runner, case: dict, spec: dict, item: dict, out_dir: Path, model: str, kubeconfig: str | None) -> dict:
    rec = {"case": case["id"], "arm": item["arm"], "run": item["run"], "status": None, "pass": None,
           "tokens": None, "duration_ms": None, "wall_seconds": None, "total_cost_usd": None, "reason": None}
    kind, value = case["grade"]
    run_dir = out_dir / case["id"] / item["arm"] / f"run-{item['run']}"
    if case.get("live") and not kubeconfig:
        rec.update(status="cannot run", reason="no --kubeconfig for a live case")
        return rec
    t0 = time.time()
    if kind == "trigger":
        idx, should = value[item["arm"]]
        skill_dir = REPO_ROOT / "skills" / case["skill"]
        name, _ = runner.read_skill_meta(skill_dir)
        res = runner.run_single_query(spec["queries"][idx]["query"], name, skill_dir, model, TRIGGER_TIMEOUT)
        rec["wall_seconds"] = round(time.time() - t0, 2)
        if res.get("invalid"):
            rec.update(status="error", reason=f"invalid: {res.get('invalid_reason')}")
        else:
            rec.update(status="ran", **{"pass": bool(res.get("triggered")) is should},
                       reason=f"triggered {bool(res.get('triggered'))}, want {should}")
        return rec
    sys.path.insert(0, str(SCRIPTS))
    from elicitation import ElicitationConfig
    with (old_skill_dir(case["skill"]) if item["arm"] == "old_skill"
          else contextlib.nullcontext(REPO_ROOT / "skills" / case["skill"])) as skill_dir:
        name, _ = runner.read_skill_meta(skill_dir)
        subj = runner.run_subject(
            prompt=spec["prompt"], skill_name=name, repo_skill_dir=skill_dir,
            with_skill=item["arm"] != "without_skill", model=model, timeout=runner.subject_timeout(case["skill"]),
            run_dir=run_dir, extra_env=({"KUBECONFIG": kubeconfig} if case.get("live") else None),
            elicitation=ElicitationConfig.from_dict(spec.get("elicitation")),
            skill_eval_dir=REPO_ROOT / "misc" / "evals" / case["skill"],
            eval_id=case["eval_id"], fixture_files=spec.get("files"))
    rec["wall_seconds"] = round(time.time() - t0, 2)
    timing_path = run_dir / "timing.json"
    if timing_path.exists():
        timing = json.loads(timing_path.read_text())
        rec["duration_ms"] = timing.get("duration_ms")
        rec["tokens"] = {k: v for k, v in timing.items() if k.endswith("_tokens") or k == "token_source"}
    rec["total_cost_usd"] = last_result(run_dir / "events.jsonl")[0].get("total_cost_usd")
    if not subj.get("ok"):
        rec.update(status="error", reason=f"subject: {subj.get('reason')}")
        return rec
    ok, why = grade_task(runner, case, spec, subj, run_dir, model)
    rec.update(status="error" if ok is None else "ran", reason=why, **{"pass": ok})
    return rec


def execute(runner, cases: list[dict], out_dir: Path, *, model: str, spend_limit: float,
            credential_note: str, kubeconfig: str | None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {c["id"]: c for c in cases}
    specs = check_specs(cases)
    spent, records = 0.0, []
    with (out_dir / "runs.jsonl").open("w") as log:
        for item in plan_runs(cases):
            case = by_id[item["case"]]
            if spent >= spend_limit:
                rec = {"case": case["id"], "arm": item["arm"], "run": item["run"], "status": "not run",
                       "pass": None, "tokens": None, "duration_ms": None, "wall_seconds": None,
                       "total_cost_usd": None, "reason": f"spend limit ${spend_limit} reached (${spent:.2f})"}
            else:
                rec = run_one(runner, case, specs[case["id"]], item, out_dir, model, kubeconfig)
                spent += rec["total_cost_usd"] or 0.0
            records.append(rec)
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(f"[c1] {rec['case']} {rec['arm']} run-{rec['run']}: {rec['status']} pass={rec['pass']} "
                  f"subject spend ${spent:.2f} of ${spend_limit}", file=sys.stderr)
    summary = {"model": model, "pin": PIN, "old": OLD, "credential_note": credential_note,
               "spend_limit_usd": spend_limit, "subject_cost_usd": round(spent, 4), "cases": {}}
    for rec in records:
        cell = summary["cases"].setdefault(rec["case"], {}).setdefault(
            rec["arm"], {"pass": 0, "ran": 0, "runs": 0, "statuses": []})
        cell["runs"] += 1
        cell["ran"] += rec["status"] == "ran"
        cell["pass"] += bool(rec["pass"])
        cell["statuses"].append(rec["status"])
    t6 = {(r["arm"], r["run"]): r for r in records if r["case"] == "T6"}
    if t6:
        # cases.md T6: a run k passes only when both query arms passed at run k
        arms = next(c["arms"] for c in cases if c["id"] == "T6")
        ks = range(1, RUNS + 1)
        both = [[t6.get((a, k), {}) for a in arms] for k in ks]
        summary["cases"]["T6"]["both_queries"] = {
            "pass": sum(all(r.get("pass") for r in rs) for rs in both),
            "ran": sum(all(r.get("status") == "ran" for r in rs) for rs in both),
            "runs": RUNS}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None, runner: SimpleNamespace | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Drive runner-trial candidate C1 (misc/runner-trial/cases.md). Dry run by default: "
                    "prints the planned runs and makes no model call. Do not run --paid on the trial host: "
                    "every subject can reach the host's AWS credentials (cases.md, Credentials and permissions).")
    p.add_argument("--out", type=Path, help="output dir, empty or new (required with --paid)")
    p.add_argument("--case", action="append", help="case id, repeatable (default: T1 to T7)")
    p.add_argument("--paid", action="store_true", help="start the runs (model calls, billed)")
    p.add_argument("--spend-limit-usd", type=float, help="the maintainers' spend limit for C1, per invocation "
                                                         "(required with --paid)")
    p.add_argument("--credential-note", help="which subject credential, limited to the model calls, "
                                             "the maintainers provided; recorded, not enforced (required with --paid)")
    p.add_argument("--kubeconfig", help="read-only kubeconfig for T7 (without it T7 reads 'cannot run')")
    p.add_argument("--model", help="subject and grader model (default: the runner's)")
    args = p.parse_args(argv)

    unknown = [c for c in (args.case or []) if c not in CASE_IDS]
    if unknown:
        print(f"unknown case id: {', '.join(unknown)} (known: {', '.join(CASE_IDS)})", file=sys.stderr)
        return 2
    cases = [c for c in CASES if not args.case or c["id"] in args.case]
    changed = check_pin(cases)
    if changed:
        print(f"case text differs from {PIN}: {', '.join(changed)}", file=sys.stderr)
        return 2

    try:
        check_specs(cases)
    except (ValueError, KeyError, IndexError) as e:
        print(f"case set does not resolve: {e}", file=sys.stderr)
        return 2

    if not args.paid:
        plan = plan_runs(cases)
        for item in plan:
            print(f"{item['case']} {item['arm']} run-{item['run']}: {item['call']}")
        print(f"dry run: {len(plan)} runs planned, no model call made")
        return 0

    note = (args.credential_note or "").strip()
    missing = [f for f, v in (("--out", args.out), ("--spend-limit-usd", args.spend_limit_usd),
                              ("--credential-note", note)) if v in (None, "")]
    limit = args.spend_limit_usd
    if missing or (limit is not None and not (math.isfinite(limit) and limit > 0)):
        print(f"--paid refused: needs {', '.join(missing) or 'a finite --spend-limit-usd above 0'}", file=sys.stderr)
        return 2
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        print(f"--paid refused: --out {args.out} is not an empty or new directory", file=sys.stderr)
        return 2
    kubeconfig = None
    if args.kubeconfig:
        kcp = Path(args.kubeconfig).resolve()   # as run_task_evals.py main does
        if not kcp.exists():
            print(f"kubeconfig not found: {kcp}", file=sys.stderr)
            return 2
        kubeconfig = str(kcp)
    runner = runner or load_runner()
    summary = execute(runner, cases, args.out, model=args.model or runner.default_model(),
                      spend_limit=limit, credential_note=note, kubeconfig=kubeconfig)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
