"""Tests for misc/runner-trial/drive_c1.py with the runner's functions mocked.

No model call, no claude process, no cluster or AWS access. The git reads
(the case-text pin and the old skill extract) are mocked too, so a shallow
clone runs these tests; PinCheck runs check_pin on a throwaway git repo.
Run: python3 -B -m unittest misc.tests.test_drive_c1 -v
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
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
                           default_model=lambda: "test-model")


@contextlib.contextmanager
def no_git():
    """Mock the two git reads: the pin check and the old skill extract."""
    with mock.patch.object(drive_c1, "check_pin", return_value=[]), \
         mock.patch.object(drive_c1, "old_skill_dir", lambda s: contextlib.nullcontext(ROOT / "skills" / s)):
        yield


def run_main(argv, runner=None):
    out, err = io.StringIO(), io.StringIO()
    with no_git(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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
        self.assertIn("run_task_evals.run_subject(", out)
        self.assertIn("run_triggering.run_single_query(", out)

    def test_unknown_case_id_is_refused(self):
        rc, _, err = run_main(["--case", "T9"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown case id: T9", err)


class PaidRefusal(unittest.TestCase):
    def test_paid_without_inputs_is_refused(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            for argv, want in (
                (["--paid", "--out", d], "needs --spend-limit-usd, --credential-note"),
                (["--paid", "--out", d, "--spend-limit-usd", "50"], "needs --credential-note"),
                (["--paid", "--spend-limit-usd", "50", "--credential-note", "c"], "needs --out"),
                (["--paid", "--out", d, "--spend-limit-usd", "0", "--credential-note", "c"], "above 0"),
                (["--paid", "--out", d, "--spend-limit-usd", "nan", "--credential-note", "c"], "finite"),
                (["--paid", "--out", d, "--spend-limit-usd", "inf", "--credential-note", "c"], "finite"),
                (["--paid", "--out", d, "--spend-limit-usd", "50", "--credential-note", "  "], "needs --credential-note"),
            ):
                rc, _, err = run_main(argv, runner=fake_runner(calls))
                self.assertEqual(rc, 2, argv)
                self.assertIn(want, err)
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(calls, [])

    def test_help_says_not_on_this_host(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            drive_c1.main(["--help"])
        self.assertIn("Do not run --paid on the trial host", " ".join(out.getvalue().split()))


class OutputShape(unittest.TestCase):
    KEYS = {"case", "arm", "run", "status", "pass", "tokens", "duration_ms", "wall_seconds", "total_cost_usd", "reason"}

    def test_runs_and_summary(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            argv = ["--paid", "--out", d, "--spend-limit-usd", "100", "--credential-note", "model-only test credential"]
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
        self.assertEqual(summary["credential_note"], "model-only test credential")
        self.assertNotIn("grader_cost_usd", summary)
        graded = [kw["expectations"] for name, kw in calls if name == "run_grader"]
        self.assertTrue(all(len(e) == 1 and "verdict exposed for both" in e[0] for e in graded))
        picked = [kw["assertions_config"] for name, kw in calls if name == "validate_run"]
        self.assertTrue(all(len(c["validators"]) == 1 and "structural" not in c for c in picked))

    def test_spend_limit_stops_the_next_run(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            rc, _, _ = run_main(["--paid", "--out", d, "--spend-limit-usd", "0.5", "--credential-note", "c",
                                 "--case", "T4"], runner=fake_runner(calls))
            recs = [json.loads(l) for l in (Path(d) / "runs.jsonl").read_text().splitlines()]
        self.assertEqual(rc, 0)
        self.assertEqual([r["status"] for r in recs], ["ran", "ran"] + ["not run"] * 7)
        self.assertEqual(sum(1 for name, _ in calls if name == "run_subject"), 2)


def paid(d, cases, runner, *extra):
    argv = ["--paid", "--out", d, "--spend-limit-usd", "100", "--credential-note", "c", *extra]
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

    @unittest.skipUnless(subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{drive_c1.OLD}^{{commit}}"],
                                        capture_output=True).returncode == 0, "old tag not in this clone")
    def test_old_skill_dir_extracts_the_tag(self):
        with drive_c1.old_skill_dir("eks-security") as d:
            self.assertEqual(d.name, "eks-security")
            want = subprocess.run(["git", "-C", str(ROOT), "show", f"{drive_c1.OLD}:skills/eks-security/SKILL.md"],
                                  capture_output=True, check=True).stdout
            self.assertEqual((d / "SKILL.md").read_bytes(), want)
        self.assertFalse(d.exists())


class PinCheck(unittest.TestCase):
    """check_pin, unmocked, on a throwaway repo holding T1's case file and skill."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git = lambda *a: subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t",
                                              *a], capture_output=True, text=True, check=True).stdout.strip()
        (self.root / "misc/evals/eks-security").mkdir(parents=True)
        (self.root / "misc/evals/eks-security/evals.json").write_text("{}")
        (self.root / "skills/eks-security/references").mkdir(parents=True)
        (self.root / "skills/eks-security/SKILL.md").write_text("s")
        (self.root / ".gitignore").write_text("*.log\n__pycache__/\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "pin")
        patches = [mock.patch.object(drive_c1, "REPO_ROOT", self.root),
                   mock.patch.object(drive_c1, "PIN", self.git("rev-parse", "HEAD"))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.t1 = [c for c in drive_c1.CASES if c["id"] == "T1"]

    def test_clean_tree_passes(self):
        self.assertEqual(drive_c1.check_pin(self.t1), [])

    def test_untracked_file_in_the_skill_refuses(self):
        (self.root / "skills/eks-security/references/new.md").write_text("n")
        self.assertEqual(drive_c1.check_pin(self.t1), ["skills/eks-security"])

    def test_ignored_file_in_the_skill_refuses(self):
        (self.root / "skills/eks-security/references/cheat.log").write_text("c")
        self.assertEqual(drive_c1.check_pin(self.t1), ["skills/eks-security"])

    def test_pycache_in_the_skill_passes(self):
        (self.root / "skills/eks-security/__pycache__").mkdir()
        (self.root / "skills/eks-security/__pycache__/x.pyc").write_bytes(b"c")
        self.assertEqual(drive_c1.check_pin(self.t1), [])

    def test_near_miss_pycache_names_refuse(self):
        for rel in ("skills/eks-security/references/my__pycache__/c.md", "skills/eks-security/__pycache__/answer.md"):
            with self.subTest(rel=rel):
                f = self.root / rel
                f.parent.mkdir(parents=True)
                f.write_text("c")
                self.assertEqual(drive_c1.check_pin(self.t1), ["skills/eks-security"])
                shutil.rmtree(f.parent)


if __name__ == "__main__":
    unittest.main()
