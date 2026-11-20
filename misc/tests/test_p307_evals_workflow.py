"""P-307: the eval-gate job in .github/workflows/evals.yml gates a pull
request on the run keys it changed (`make -C misc/evals gate-changed
BASE=<the PR base sha>`), uploads each gate-report.md and the history rows
the run appended as an artifact, and stays dispatch-only with no Kiro leg
(going live and Kiro in CI are the user's questions Q4 and Q5, design.md
section 11).

The gate step's shell runs here with a fake `make` first on PATH that only
prints its arguments, and the collect step runs in a temporary git repo, so
no test reaches a model, AWS or the network.
"""

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "evals.yml"
SHA = "0123456789abcdef0123456789abcdef01234567"


def _bash(script: str, env: dict, cwd: str) -> subprocess.CompletedProcess:
    # GitHub runs a `run:` block as `bash -e {0}` (shell: bash is the default on ubuntu).
    return subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=60)


class EvalGateOnPullRequests(unittest.TestCase):

    def setUp(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        self.job = yaml.safe_load(WORKFLOW.read_text())["jobs"]["eval-gate"]
        self.steps = {s.get("name"): s for s in self.job["steps"]}
        self.tmp = tempfile.mkdtemp(prefix="p307-wf-")
        self.addCleanup(subprocess.run, ["rm", "-rf", self.tmp])
        fake = Path(self.tmp) / "bin" / "make"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\necho \"make $*\"\n")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    def gate(self, **env):
        step = self.steps["Run the gate"]
        full = {"PATH": f"{self.tmp}/bin:{os.environ['PATH']}", "HARNESS": "claude", "GATE_SKILL": "",
                "EVENT_NAME": "", "PR_BASE_SHA": ""}
        full.update(env)
        return _bash(step["run"], full, self.tmp)

    def test_still_dispatch_only_with_no_kiro_leg(self):
        self.assertEqual(self.job["if"], "github.event_name == 'workflow_dispatch'")
        self.assertEqual(self.job["strategy"]["matrix"]["harness"], ["claude", "codex"])

    def test_gate_step_reads_the_pr_base_sha(self):
        env = self.steps["Run the gate"]["env"]
        self.assertEqual(env["PR_BASE_SHA"], "${{ github.event.pull_request.base.sha }}")
        self.assertEqual(env["EVENT_NAME"], "${{ github.event_name }}")

    def test_pull_request_gates_the_changed_keys_against_its_base(self):
        r = self.gate(EVENT_NAME="pull_request", PR_BASE_SHA=SHA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(),
                         f"make -C misc/evals gate-changed BASE={SHA} HARNESS=claude")

    def test_pull_request_with_a_bad_base_runs_no_make(self):
        for base in ("", "main; echo INJECTED", "$(id)"):
            r = self.gate(EVENT_NAME="pull_request", PR_BASE_SHA=base)
            self.assertNotEqual(r.returncode, 0, base)
            self.assertNotIn("make ", r.stdout, base)

    def test_dispatch_keeps_gate_all_and_one_skill(self):
        r = self.gate(EVENT_NAME="workflow_dispatch", HARNESS="codex")
        self.assertEqual(r.stdout.strip(), "make -C misc/evals gate-all HARNESS=codex")
        r = self.gate(EVENT_NAME="workflow_dispatch", GATE_SKILL="eks-recon")
        self.assertEqual(r.stdout.strip(), "make -C misc/evals gate SKILL=eks-recon HARNESS=claude")

    def test_report_and_new_history_rows_are_collected_then_uploaded(self):
        names = [s.get("name") for s in self.job["steps"]]
        collect, upload = (self.steps["Collect the gate reports and new history rows"],
                           self.steps["Upload the gate reports and new history rows"])
        self.assertEqual(names.index(collect["name"]), names.index("Run the gate") + 1)
        self.assertEqual(names.index(upload["name"]), names.index(collect["name"]) + 1)
        for s in (collect, upload):
            self.assertEqual(s["if"], "always()", s["name"])  # a failed gate still uploads
        self.assertRegex(upload["uses"], r"^actions/upload-artifact@[0-9a-f]{40}$")
        self.assertEqual(upload["with"]["name"], "eval-gate-${{ matrix.harness }}")
        self.assertEqual(upload["with"]["path"], "${{ runner.temp }}/eval-gate")
        self.assertNotIn("secrets.", str(collect) + str(upload))

    def test_collect_keeps_only_the_rows_the_run_appended(self):
        repo = Path(self.tmp) / "repo"
        hist = repo / "misc" / "evals" / "history"
        hist.mkdir(parents=True)
        (hist / "eks-recon.jsonl").write_text('{"old": 1}\n')
        (hist / "eks-build.jsonl").write_text('{"old": 2}\n')
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "misc"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "base"], check=True)
        with open(hist / "eks-recon.jsonl", "a") as fh:
            fh.write('{"new": 1}\n')
        (hist / "devops-agent-eks-recon.jsonl").write_text('{"new": 2}\n')
        for ws in ("misc/evals/eks-recon/workspace",
                   "misc/evals/workspace/devops-agent-eks-recon/workspace"):
            (repo / ws).mkdir(parents=True)
            (repo / ws / "gate-report.md").write_text(f"# report {ws}\n")
        out = Path(self.tmp) / "runner-temp"
        r = _bash(self.steps["Collect the gate reports and new history rows"]["run"],
                  {"PATH": os.environ["PATH"], "RUNNER_TEMP": str(out)}, str(repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        got = {p.relative_to(out / "eval-gate").as_posix(): p.read_text()
               for p in (out / "eval-gate").rglob("*") if p.is_file()}
        self.assertEqual(got, {
            "history/eks-recon.jsonl": '{"new": 1}\n',
            "history/devops-agent-eks-recon.jsonl": '{"new": 2}\n',
            "eks-recon/gate-report.md": "# report misc/evals/eks-recon/workspace\n",
            "devops-agent-eks-recon/gate-report.md":
                "# report misc/evals/workspace/devops-agent-eks-recon/workspace\n",
        })

    def test_actions_are_pinned_by_sha_with_a_version_comment(self):
        text = WORKFLOW.read_text()
        for line in re.findall(r"uses: \S+.*", text):
            self.assertRegex(line, r"uses: [\w./-]+@[0-9a-f]{40} # v\d", line)


if __name__ == "__main__":
    unittest.main()
