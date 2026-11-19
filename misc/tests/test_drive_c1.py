"""Tests for misc/runner-trial/drive_c1.py with the runner's functions mocked.

No model call, no claude process, no cluster or AWS access. The driver's git
reads are not mocked: the case text comes from git archive of drive_c1.PIN and
the old arm's skill from drive_c1.OLD, so the clone must hold both commits.
Run: python3 -B -m unittest misc.tests.test_drive_c1 -v
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("drive_c1", ROOT / "misc/runner-trial/drive_c1.py")
drive_c1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drive_c1)


def fake_runner(calls):
    """Runner functions that record their calls and write what run_subject writes."""
    def run_subject(**kw):
        calls.append(("run_subject", kw))
        run_dir = kw["run_dir"]
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (run_dir / "transcript.md").write_text("t")
        results = 2 if kw["elicitation"].turns else 1
        (run_dir / "events.jsonl").write_text("\n".join(
            json.dumps({"type": "result", "total_cost_usd": 0.25, "result": "Pattern 2a"}) for _ in range(results)) + "\n")
        (run_dir / "timing.json").write_text(json.dumps(
            {"total_tokens": 10, "input_tokens": 4, "output_tokens": 6, "token_source": "modelUsage",
             "duration_ms": 1500, "total_duration_seconds": 1.5}))
        return {"ok": True, "reason": None, "transcript_path": str(run_dir / "transcript.md"),
                "outputs_dir": str(run_dir / "outputs")}

    def run_grader(**kw):
        calls.append(("run_grader", kw))
        return {"expectations": [{"text": e, "passed": True} for e in kw["expectations"]]}

    def validate_run(**kw):
        calls.append(("validate_run", kw))
        return SimpleNamespace(structural_passed=1, validators_passed=0, structural_failed=0, validators_failed=0)

    def evaluate_knowledge(text, assertions):
        calls.append(("evaluate_knowledge", text))
        return SimpleNamespace(passed=1, failed=0)

    def run_single_query(query, name, skill_dir, model, timeout):
        calls.append(("run_single_query", query))
        return {"triggered": "eks-mcp config" in query, "invalid": False}

    return SimpleNamespace(run_subject=run_subject, run_grader=run_grader, validate_run=validate_run,
                           evaluate_knowledge=evaluate_knowledge, run_single_query=run_single_query,
                           read_skill_meta=lambda d: (Path(d).name, "desc"), subject_timeout=lambda s: 600,
                           default_model=lambda: "test-model", EvalCredentialError=EvalCredentialError,
                           start_eval_session=lambda timeout, source: calls.append(("session", timeout)))


class EvalCredentialError(RuntimeError):
    """Stands in for run_triggering.EvalCredentialError."""


def run_main(argv, runner=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = drive_c1.main(argv, runner=runner)
    return rc, out.getvalue(), err.getvalue()


class DryRunPlan(unittest.TestCase):
    def test_plan_for_the_seven_cases(self):
        calls = []
        rc, out, _ = run_main([], runner=fake_runner(calls))
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [], "a dry run calls no runner function")
        lines = [l for l in out.splitlines() if not l.startswith("dry run:")]
        counts = {}
        for line in lines:
            case, arm = line.split()[:2]
            counts[case] = counts.get(case, 0) + 1
        # cases.md, Run count: T1 to T4 9 each, T5 and T7 6 each, T6 6 query runs
        self.assertEqual(counts, {"T1": 9, "T2": 9, "T3": 9, "T4": 9, "T5": 6, "T6": 6, "T7": 6})
        self.assertIn("dry run: 54 runs planned, no model call made", out)
        self.assertTrue(all("old_skill" not in l for l in lines if l.split()[0] in ("T5", "T6", "T7")))
        self.assertIn(f"T1 old_skill run-1 OLD {drive_c1.OLD}\n", out)
        self.assertIn(f"T6 with_skill_q3 run-3 PIN {drive_c1.PIN}\n", out)

    def test_unknown_case_id_is_refused(self):
        rc, _, err = run_main(["--case", "T9"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown case id: T9", err)


class PaidRefusal(unittest.TestCase):
    def test_paid_without_inputs_is_refused(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            for argv, want in (
                (["--paid", "--out", d], "needs --spend-limit-usd"),
                (["--paid", "--spend-limit-usd", "50"], "needs --out"),
                (["--paid", "--out", d, "--spend-limit-usd", "0"], "above 0"),
                (["--paid", "--out", d, "--spend-limit-usd", "nan"], "finite"),
                (["--paid", "--out", d, "--spend-limit-usd", "inf"], "finite"),
            ):
                rc, _, err = run_main(argv, runner=fake_runner(calls))
                self.assertEqual(rc, 2, argv)
                self.assertIn(want, err)
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(calls, [])

    def test_help_names_the_eval_role_session(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            drive_c1.main(["--help"])
        self.assertIn("--paid needs the eval-role session", " ".join(out.getvalue().split()))

    def test_refused_eval_role_session_runs_nothing(self):
        calls = []
        runner = fake_runner(calls)

        def refuse(timeout, source):
            raise EvalCredentialError("no eval role")
        runner.start_eval_session = refuse
        with tempfile.TemporaryDirectory() as d:
            rc, _, err = run_main(["--paid", "--out", d, "--spend-limit-usd", "50", "--case", "T4"], runner=runner)
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(rc, 2)
        self.assertIn("eval-role session refused", err)
        self.assertEqual(calls, [])


class OutputShape(unittest.TestCase):
    KEYS = {"case", "arm", "run", "status", "pass", "tokens", "duration_ms", "wall_seconds", "total_cost_usd", "reason"}

    def test_runs_and_summary(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            argv = ["--paid", "--out", d, "--spend-limit-usd", "100"]
            for c in ("T1", "T3", "T5", "T6", "T7"):
                argv += ["--case", c]
            rc, _, _ = run_main(argv, runner=fake_runner(calls))
            self.assertEqual(rc, 0)
            recs = [json.loads(l) for l in (Path(d) / "runs.jsonl").read_text().splitlines()]
            summary = json.loads((Path(d) / "summary.json").read_text())
        self.assertEqual(len(recs), 9 + 9 + 6 + 6 + 6)
        self.assertTrue(all(set(r) == self.KEYS for r in recs))
        t1 = [r for r in recs if r["case"] == "T1"]
        self.assertTrue(all(r["status"] == "ran" and r["pass"] for r in t1))
        self.assertEqual(t1[0]["tokens"]["output_tokens"], 6)
        self.assertEqual(t1[0]["duration_ms"], 1500)
        self.assertEqual(t1[0]["total_cost_usd"], 0.25)
        t6 = {(r["arm"], r["pass"]) for r in recs if r["case"] == "T6"}
        self.assertEqual(t6, {("with_skill_q3", True), ("with_skill_q18", True)})
        self.assertTrue(all(r["status"] == "cannot run" for r in recs if r["case"] == "T7"))
        self.assertEqual(summary["cases"]["T1"]["old_skill"], {"pass": 3, "ran": 3, "runs": 3, "statuses": ["ran"] * 3})
        self.assertEqual(summary["cases"]["T5"]["with_skill"]["pass"], 3)
        self.assertEqual(calls[0], ("session", 600), "one eval-role session, minted first, for the longest timeout")
        self.assertEqual(sum(1 for name, _ in calls if name == "session"), 1)
        self.assertNotIn("grader_cost_usd", summary)
        graded = [kw["expectations"] for name, kw in calls if name == "run_grader"]
        self.assertTrue(all(len(e) == 1 and "verdict exposed for both" in e[0] for e in graded))
        picked = [kw["assertions_config"] for name, kw in calls if name == "validate_run"]
        self.assertTrue(all(len(c["validators"]) == 1 and "structural" not in c for c in picked))

    def test_spend_limit_stops_the_next_run(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            rc, _, _ = run_main(["--paid", "--out", d, "--spend-limit-usd", "0.5",
                                 "--case", "T4"], runner=fake_runner(calls))
            recs = [json.loads(l) for l in (Path(d) / "runs.jsonl").read_text().splitlines()]
            cells = json.loads((Path(d) / "summary.json").read_text())["cases"]["T4"]
        self.assertEqual(rc, 0)
        self.assertEqual([r["status"] for r in recs], ["ran", "ran"] + ["not run"] * 7)
        self.assertEqual(sum(1 for name, _ in calls if name == "run_subject"), 2)
        # S2 leaves the spend stop's 'not run' runs out: 2/2, not 2/3; an arm with none left is n/a
        self.assertEqual((cells["with_skill"]["pass"], cells["with_skill"]["runs"]), (2, 2))
        self.assertEqual([cells[a]["runs"] for a in ("without_skill", "old_skill")], [0, 0])


def paid(d, cases, runner, *extra):
    argv = ["--paid", "--out", d, "--spend-limit-usd", "100", *extra]
    for c in cases:
        argv += ["--case", c]
    rc, _, err = run_main(argv, runner=runner)
    recs = [json.loads(l) for l in (Path(d) / "runs.jsonl").read_text().splitlines()] if rc == 0 else []
    summary = json.loads((Path(d) / "summary.json").read_text()) if rc == 0 else None
    return rc, err, recs, summary


class FixedBranches(unittest.TestCase):
    def test_t6_both_queries_pairs_runs_by_index(self):
        runner, seen = fake_runner([]), {}
        passes = {3: {1, 2}, 18: {2, 3}}   # q3 passes runs 1, 2; q18 runs 2, 3: 2/3 each, both at run 2 only
        queries = json.loads((ROOT / "misc/evals/eks-mcp-server/triggering.json").read_text())

        def run_single_query(query, name, skill_dir, model, timeout):
            idx = next(i for i, q in enumerate(queries) if q["query"] == query)
            seen[idx] = seen.get(idx, 0) + 1
            return {"triggered": (seen[idx] in passes[idx]) == (idx == 3), "invalid": False}
        runner.run_single_query = run_single_query
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, summary = paid(d, ["T6"], runner)
        self.assertEqual(rc, 0)
        t6 = summary["cases"]["T6"]
        self.assertEqual((t6["with_skill_q3"]["pass"], t6["with_skill_q18"]["pass"]), (2, 2))
        self.assertEqual(t6["both_queries"], {"pass": 1, "ran": 3, "runs": 3})

    def test_kubeconfig_is_resolved_or_refused(self):
        calls = []
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            rc, err, _, _ = paid(out, ["T7"], fake_runner(calls), "--kubeconfig", str(Path(d) / "missing"))
            self.assertEqual(rc, 2)
            self.assertIn("kubeconfig not found", err)
            self.assertEqual(calls, [])
            kc = Path(d) / "kc"
            kc.write_text("k")
            cwd = os.getcwd()
            os.chdir(d)   # a relative path, as a maintainer would type it
            try:
                rc, _, _, _ = paid(out, ["T7"], fake_runner(calls), "--kubeconfig", "kc")
            finally:
                os.chdir(cwd)
        self.assertEqual(rc, 0)
        envs = [kw["extra_env"] for name, kw in calls if name == "run_subject"]
        self.assertEqual(len(envs), 6)
        self.assertTrue(all(e == {"KUBECONFIG": str(kc.resolve())} for e in envs))

    def test_grader_error_is_status_error(self):
        runner = fake_runner([])
        runner.run_grader = lambda **kw: {"error": "grader timeout"}
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, summary = paid(d, ["T4"], runner)
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "error" and r["pass"] is None for r in recs))
        self.assertEqual(summary["cases"]["T4"]["with_skill"]["ran"], 0)

    def test_grader_with_too_few_expectations_is_not_a_pass(self):
        runner = fake_runner([])
        runner.run_grader = lambda **kw: {"expectations": []}
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, summary = paid(d, ["T4"], runner)
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "error" for r in recs))
        self.assertEqual(summary["cases"]["T4"]["with_skill"]["pass"], 0)

    def test_grader_with_extra_expectations_is_not_a_pass(self):
        runner = fake_runner([])
        runner.run_grader = lambda **kw: {"expectations": [{"text": e, "passed": True}
                                                           for e in kw["expectations"] + ["extra"]]}
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, summary = paid(d, ["T4"], runner)
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "error" for r in recs))
        self.assertEqual(summary["cases"]["T4"]["with_skill"]["pass"], 0)

    def test_non_empty_out_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "runs.jsonl").write_text("{}\n")
            rc, err, _, _ = paid(d, ["T4"], fake_runner([]))
        self.assertEqual(rc, 2)
        self.assertIn("not an empty or new directory", err)

    def test_archived_extracts_the_tag(self):
        with drive_c1.archived(drive_c1.OLD, "skills/eks-security") as d:
            want = subprocess.run(["git", "-C", str(ROOT), "show", f"{drive_c1.OLD}:skills/eks-security/SKILL.md"],
                                  capture_output=True, check=True).stdout
            self.assertEqual((d / "skills/eks-security/SKILL.md").read_bytes(), want)
        self.assertFalse(d.exists())

    def test_git_failure_is_refused(self):
        err = io.StringIO()
        with mock.patch.object(drive_c1, "PIN", "0" * 40), contextlib.redirect_stderr(err):
            rc = drive_c1.main(["--case", "T1"])
        self.assertEqual(rc, 2)
        self.assertIn("git read failed: git archive", err.getvalue())


class FailingPaths(unittest.TestCase):
    """Each pass rule must be able to read False (or error), not only True."""

    def test_one_failed_grader_expectation_fails_the_run(self):
        runner = fake_runner([])
        runner.run_grader = lambda **kw: {"expectations": [{"text": e, "passed": i == 0}
                                                           for i, e in enumerate(kw["expectations"])]}
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as k:
            (Path(k) / "kc").write_text("k")
            rc, _, recs, summary = paid(d, ["T7"], runner, "--kubeconfig", str(Path(k) / "kc"))
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "ran" and r["pass"] is False for r in recs))
        self.assertTrue(all(r["reason"] == "grader 1/4" for r in recs))
        self.assertEqual(summary["cases"]["T7"]["with_skill"]["pass"], 0)

    def test_artifact_fail_is_not_a_pass(self):
        for res in ({"structural_passed": 1, "structural_failed": 1}, {"structural_passed": 0, "structural_failed": 0}):
            runner = fake_runner([])
            runner.validate_run = lambda res=res, **kw: SimpleNamespace(validators_passed=0, validators_failed=0, **res)
            with tempfile.TemporaryDirectory() as d:
                rc, _, recs, _ = paid(d, ["T2"], runner)
            self.assertEqual(rc, 0)
            self.assertTrue(all(r["status"] == "ran" and r["pass"] is False for r in recs), res)

    def test_knowledge_assertion_fail_is_not_a_pass(self):
        runner = fake_runner([])
        runner.evaluate_knowledge = lambda text, assertions: SimpleNamespace(passed=0, failed=1)
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, _ = paid(d, ["T5"], runner)
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "ran" and r["pass"] is False for r in recs))

    def test_multiturn_not_resumed_is_not_a_pass(self):
        runner = fake_runner([])
        real = runner.run_subject

        def one_turn(**kw):
            subj = real(**kw)
            (kw["run_dir"] / "events.jsonl").write_text(json.dumps({"type": "result", "result": "Pattern 2a"}) + "\n")
            return subj
        runner.run_subject = one_turn
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, _ = paid(d, ["T5"], runner)
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "ran" and r["pass"] is False for r in recs))

    def test_subject_failure_counts_in_runs(self):
        runner, n = fake_runner([]), []
        real = runner.run_subject

        def flaky(**kw):
            subj = real(**kw)
            n.append(1)
            return subj if len(n) % 3 == 1 else {**subj, "ok": False, "reason": "timeout"}
        runner.run_subject = flaky
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, summary = paid(d, ["T4"], runner)
        self.assertEqual(rc, 0)
        cell = summary["cases"]["T4"]["with_skill"]
        self.assertEqual(cell["statuses"], ["ran", "error", "error"])
        self.assertEqual([r["pass"] for r in recs[:3]], [True, None, None])
        self.assertEqual(recs[1]["reason"], "subject: timeout")
        # MF-1: S2 reads pass over runs, so an error run is a failed run: 1/3, not 1/1
        self.assertEqual((cell["pass"], cell["runs"]), (1, 3))

    def test_invalid_trigger_is_an_error(self):
        runner = fake_runner([])
        runner.run_single_query = lambda *a: {"triggered": True, "invalid": True, "invalid_reason": "no init"}
        with tempfile.TemporaryDirectory() as d:
            rc, _, recs, _ = paid(d, ["T6"], runner)
        self.assertEqual(rc, 0)
        self.assertTrue(all(r["status"] == "error" and r["pass"] is None and r["reason"] == "invalid: no init"
                            for r in recs))


class RunRecord(unittest.TestCase):
    def test_summary_records_runner_head(self):
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, summary = paid(d, ["T4"], fake_runner([]))
        self.assertEqual(rc, 0)
        self.assertEqual(summary["runner_head"], head)

    def test_missing_old_commit_is_refused_before_the_session(self):
        calls = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(drive_c1, "OLD", "0" * 40):
            rc, err, _, _ = paid(d, ["T1"], fake_runner(calls))
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(rc, 2)
        self.assertIn(f"--paid refused: OLD commit {'0' * 40} is not in this clone", err)
        self.assertEqual(calls, [])


EVENTS = [
    {"type": "system", "subtype": "init"},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Reading."},
        {"type": "tool_use", "id": "tu1", "name": "Read", "input": {"file_path": "a.tf"}},
        {"type": "tool_use", "id": "tu2", "name": "Bash", "input": {"command": "ls"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu2", "content": [{"type": "text", "text": "x"}], "is_error": True},
        {"type": "tool_result", "tool_use_id": "tu1", "content": "body"}]}},
    {"type": "result", "result": "Turn one done"},
    "not an object",
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu3", "name": "Skill", "input": None}]}},
    {"type": "result", "result": "Turn two done", "is_error": True},
]


class Spans(unittest.TestCase):
    def test_events_to_spans(self):
        spans = drive_c1.events_to_spans(EVENTS, ["first prompt", "second prompt"], "s1")
        sid = lambda *p, n=16: drive_c1._span_id("s1", *p, n=n)
        scope = {"name": "openinference.instrumentation.claude_agent_sdk"}
        t0, t1 = sid("trace", 0, n=32), sid("trace", 1, n=32)
        self.assertEqual(spans, [
            {"traceId": t0, "spanId": sid("agent", 0), "name": "ClaudeCode.turn", "kind": "INTERNAL", "scope": scope,
             "attributes": {"openinference.span.kind": "AGENT", "session.id": "s1", "input.value": "first prompt",
                            "output.value": "Turn one done"}, "status": {"code": "OK"}},
            {"traceId": t0, "spanId": sid("tool", 0, 0), "parentSpanId": sid("agent", 0), "name": "Read",
             "kind": "INTERNAL", "scope": scope,
             "attributes": {"openinference.span.kind": "TOOL", "tool.name": "Read", "session.id": "s1",
                            "input.value": '{"file_path": "a.tf"}', "tool.id": "tu1", "output.value": "body"},
             "status": {"code": "OK"}},
            {"traceId": t0, "spanId": sid("tool", 0, 1), "parentSpanId": sid("agent", 0), "name": "Bash",
             "kind": "INTERNAL", "scope": scope,
             "attributes": {"openinference.span.kind": "TOOL", "tool.name": "Bash", "session.id": "s1",
                            "input.value": '{"command": "ls"}', "tool.id": "tu2",
                            "output.value": '[{"type": "text", "text": "x"}]'}, "status": {"code": "ERROR"}},
            {"traceId": t1, "spanId": sid("agent", 1), "name": "ClaudeCode.turn", "kind": "INTERNAL", "scope": scope,
             "attributes": {"openinference.span.kind": "AGENT", "session.id": "s1", "input.value": "second prompt",
                            "output.value": "Turn two done"}, "status": {"code": "ERROR"}},
            {"traceId": t1, "spanId": sid("tool", 1, 0), "parentSpanId": sid("agent", 1), "name": "Skill",
             "kind": "INTERNAL", "scope": scope,
             "attributes": {"openinference.span.kind": "TOOL", "tool.name": "Skill", "session.id": "s1",
                            "input.value": "null", "tool.id": "tu3"}, "status": {"code": "OK"}},
        ])
        self.assertEqual(len({s["spanId"] for s in spans}), 5)
        self.assertEqual((len(t0), len(spans[0]["spanId"])), (32, 16))

    def test_empty_and_malformed_events(self):
        self.assertEqual(drive_c1.events_to_spans([], ["p"], "s"), [])
        junk = [None, 3, "x", [], {"type": "assistant", "message": "not a dict"},
                {"type": "assistant", "message": {"content": "text"}}, {"type": "user", "message": {"content": [1]}}]
        self.assertEqual(drive_c1.events_to_spans(junk, [], "s"), [])

    def test_unfinished_turn_reads_error(self):
        spans = drive_c1.events_to_spans(EVENTS[:3], [], "s")
        self.assertEqual([s["attributes"]["openinference.span.kind"] for s in spans], ["AGENT", "TOOL", "TOOL"])
        self.assertEqual(spans[0]["status"], {"code": "ERROR"})
        self.assertNotIn("output.value", spans[0]["attributes"])
        self.assertNotIn("input.value", spans[0]["attributes"])


if __name__ == "__main__":
    unittest.main()
