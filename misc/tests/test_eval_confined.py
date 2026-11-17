#!/usr/bin/env python3
"""Tests for the confined eval launches (misc/evals/scripts/confined.py).

systemd-run, systemctl, sudo and aws are mocked: nothing here starts a unit,
mints a session or calls a model.

Run directly with:

    python3 misc/tests/test_eval_confined.py
"""

import contextlib
import io
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(MISC_DIR, "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import confined  # noqa: E402
import elicitation  # noqa: E402
import run_task_evals  # noqa: E402
import run_triggering  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

_REAL_POPEN = subprocess.Popen

CREDS = {
    "AccessKeyId": "ASIATESTKEYID0000000",
    "SecretAccessKey": "test-secret-value",
    "SessionToken": "test-session-token",
    "Expiration": "2026-11-17T12:00:00Z",
}


class _Done:
    """Stands in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class FakeHost:
    """Records every subprocess call and answers like an idle host."""

    def __init__(self, active_units="", mint_rc=0, mint_err="", cleanup_rc=0):
        self.calls = []
        self.cleanup_rc = cleanup_rc
        self.popen_argv = None
        self.env_file_at_start = None
        self.active_units = active_units
        self.mint_rc, self.mint_err = mint_rc, mint_err

    def run(self, argv, **kw):
        self.calls.append(list(argv))
        if argv[:2] == ["systemctl", "list-units"]:
            return _Done(stdout=self.active_units)
        if argv[:2] == ["systemctl", "is-active"]:
            return _Done(returncode=3, stdout="inactive\n")
        if argv[:3] == ["aws", "sts", "assume-role"]:
            import json
            self.mint_env = kw.get("env")
            if self.mint_rc:
                return _Done(returncode=self.mint_rc, stderr=self.mint_err)
            return _Done(stdout=json.dumps({"Credentials": CREDS}))
        return _Done()

    def popen(self, argv, **kw):
        self.popen_argv = list(argv)
        env_arg = next(a for a in argv if a.startswith("EnvironmentFile="))
        path = Path(env_arg.split("=", 1)[1])
        self.env_file_at_start = (path.read_text(), stat.S_IMODE(path.stat().st_mode))
        inner = argv[argv.index("--") + 1:]
        if inner[:1] == ["/usr/bin/find"]:
            # The cleanup unit: run its find here, as the test user.
            if _REAL_POPEN(inner).wait() != 0:
                raise AssertionError(f"cleanup find failed: {inner}")
        proc = mock.Mock()
        proc.poll.return_value = 0
        proc.communicate.return_value = (b"", b"")
        proc.returncode = self.cleanup_rc if inner[:1] == ["/usr/bin/find"] else 0
        return proc


class ConfinedTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-confined-"))
        runs, env = self.tmp / "runs", self.tmp / "env"
        runs.mkdir()
        env.mkdir(mode=0o700)
        self.patches = [
            mock.patch.object(confined, "RUNS_ROOT", runs),
            mock.patch.object(confined, "ENV_DIR", env),
            mock.patch.object(confined, "LOCK_FILE", env / "launch.lock"),
            mock.patch.object(confined, "_public_ipv4", ["203.0.113.7"]),
            mock.patch.object(confined, "_resolver", "10.9.0.2"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        subprocess.run(["chmod", "-R", "u+rwx", str(self.tmp)])
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def patched(self, fake):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(confined.subprocess, "run", fake.run))
        stack.enter_context(mock.patch.object(confined.subprocess, "Popen", fake.popen))
        return stack


class StageTests(ConfinedTestCase):
    def make_skill(self):
        skill = self.tmp / "src" / "demo"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: demo\n---\n")
        (skill / "SKILL.md").chmod(0o664)
        (skill / "scripts" / "run.sh").write_text("#!/bin/sh\n")
        (skill / "scripts" / "run.sh").chmod(0o775)
        return skill

    def test_skill_is_a_readonly_copy_and_no_host_aws_link(self):
        # Must fail on the old stage_skill_sandbox, which symlinked the skill
        # dir and ~/.aws (when present) into the subject's sandbox and HOME,
        # so the host HOME here has a ~/.aws.
        host_home = self.tmp / "host-home"
        (host_home / ".aws").mkdir(parents=True)
        (host_home / ".aws" / "credentials").write_text("HOST-AWS-SECRET\n")
        fake = FakeHost()
        with self.patched(fake), mock.patch.dict(os.environ, {"HOME": str(host_home)}):
            with run_triggering.stage_skill_sandbox("demo", self.make_skill()) as run:
                staged = run.home / ".claude" / "skills" / "demo"
                self.assertTrue(staged.is_dir())
                self.assertFalse(staged.is_symlink())
                self.assertFalse((run.home / ".aws").exists())
                self.assertFalse((run.home / ".aws").is_symlink())
                for p in run.root.rglob("*"):
                    self.assertFalse(p.is_symlink(), p)
                    if p.is_file():
                        self.assertNotIn("HOST-AWS-SECRET", p.read_text(errors="replace"), p)
                for p in [staged, *staged.rglob("*")]:
                    self.assertFalse(p.stat().st_mode & stat.S_IWGRP, p)
                    self.assertFalse(p.stat().st_mode & stat.S_IWOTH, p)
                self.assertTrue((staged / "scripts" / "run.sh").stat().st_mode & stat.S_IXGRP)
                self.assertTrue(run.sandbox.stat().st_mode & stat.S_IWGRP)
                root = run.root
        self.assertFalse(root.exists())
        cleanup = [c for c in fake.calls if c[:1] == ["sudo"]]
        self.assertTrue(cleanup, "cleanup unit was not started")

    def test_symlink_in_staged_tree_is_refused(self):
        src = self.make_skill()
        secret = self.tmp / "outside-secret"
        secret.write_text("x")
        (src / "scripts" / "creds").symlink_to(secret)
        with self.assertRaisesRegex(confined.ConfinedError, "symlink"):
            confined.stage_readonly_copy(src, self.tmp / "dest-ro")
        self.assertFalse((self.tmp / "dest-ro").exists())
        with self.assertRaisesRegex(confined.ConfinedError, "symlink"):
            confined.stage_writable_copy(src / "scripts" / "creds", self.tmp / "dest-f")

    def test_unsafe_eval_id_is_refused_before_any_path(self):
        files = self.tmp / "skill-evals" / "files" / "shared"
        files.mkdir(parents=True)
        (files / "a.txt").write_text("a")
        sandbox = self.tmp / "sb"
        sandbox.mkdir()
        with self.assertRaisesRegex(confined.ConfinedError, "bad eval id"):
            run_task_evals.stage_fixture_files(sandbox, self.tmp / "skill-evals", "../up", ["a.txt"])
        self.assertEqual(list(sandbox.iterdir()), [])

    def test_cleanup_unit_failure_is_recorded(self):
        fake = FakeHost(cleanup_rc=2)
        with self.patched(fake):
            with run_triggering.stage_empty_sandbox() as run:
                pass
        self.assertIn("cleanup unit exited 2", run.left)

    def test_writable_copy_is_group_writable(self):
        src = self.make_skill()
        dest = self.tmp / "dest"
        dest.mkdir()
        confined.stage_writable_copy(src, dest)
        self.assertTrue((dest / "SKILL.md").stat().st_mode & stat.S_IWGRP)
        self.assertTrue((dest / "scripts").stat().st_mode & stat.S_IWGRP)


class LaunchTests(ConfinedTestCase):
    def test_launch_runs_systemd_unit_with_keys_only_in_env_file(self):
        fake = FakeHost()
        run = confined.Run("r1", confined.RUNS_ROOT / "r1")
        with self.patched(fake):
            with confined.launch_confined(run, confined.claude_argv(["-p", "x"]), "bedrock", 600) as proc:
                self.assertIs(proc.returncode, 0)
        argv = fake.popen_argv
        self.assertEqual(argv[:3], ["sudo", "-n", "systemd-run"])
        self.assertIn("--uid=apex-eval", argv)
        self.assertIn("--unit=apex-eval-r1", argv)
        self.assertEqual(argv[argv.index("--") + 1], str(confined.CLAUDE_BIN))
        props = [argv[i + 1] for i, a in enumerate(argv) if a == "-p" and i < argv.index("--")]
        for want in ("ProtectHome=tmpfs", "PrivateTmp=yes", "NoNewPrivileges=yes",
                     "ProtectSystem=strict", "RuntimeMaxSec=660"):
            self.assertIn(want, props)
        deny = next(p for p in props if p.startswith("IPAddressDeny="))
        for want in ("localhost", "link-local", "10.0.0.0/8", "203.0.113.7"):
            self.assertIn(want, deny)
        joined = " ".join(argv)
        for secret in CREDS.values():
            self.assertNotIn(secret, joined)
        text, mode = fake.env_file_at_start
        self.assertEqual(mode, 0o600)
        self.assertIn('AWS_ACCESS_KEY_ID="ASIATESTKEYID0000000"', text)
        self.assertIn(f'HOME="{run.home}"', text)
        self.assertNotIn("KUBECONFIG", text)
        self.assertNotIn("AWS_PROFILE", text)
        self.assertFalse(run.env_file.exists(), "env file left after the launch")
        kills = [c for c in fake.calls if c[:4] == ["sudo", "-n", "systemctl", "kill"]]
        self.assertEqual(kills, [["sudo", "-n", "systemctl", "kill", "--signal=SIGKILL",
                                  "apex-eval-r1.service"]])
        mint = next(c for c in fake.calls if c[:3] == ["aws", "sts", "assume-role"])
        self.assertIn(confined.ROLE_ARN, mint)
        self.assertEqual(mint[mint.index("--role-session-name") + 1], "evals-r1")
        self.assertEqual(mint[mint.index("--duration-seconds") + 1], "900")
        self.assertFalse(any(k.startswith("AWS_ACCESS") for k in fake.mint_env))
        self.assertEqual(fake.mint_env["AWS_SHARED_CREDENTIALS_FILE"], os.devnull)

    def test_policy_none_mints_nothing(self):
        fake = FakeHost()
        run = confined.Run("r2", confined.RUNS_ROOT / "r2")
        with self.patched(fake):
            with confined.launch_confined(run, ["/bin/true"], "none", 60):
                pass
        self.assertFalse(any(c[:2] == ["aws", "sts"] for c in fake.calls))
        self.assertNotIn("AWS_", fake.env_file_at_start[0])

    def test_refuses_while_a_unit_is_active(self):
        fake = FakeHost(active_units="apex-eval-old.service loaded active running x\n")
        run = confined.Run("r3", confined.RUNS_ROOT / "r3")
        with self.patched(fake):
            with self.assertRaises(confined.ConfinedError):
                with confined.launch_confined(run, ["/bin/true"], "none", 60):
                    pass
        self.assertIsNone(fake.popen_argv)

    def test_mint_failure_names_the_credential_process(self):
        fake = FakeHost(mint_rc=255, mint_err="Error when retrieving credentials from custom-process: sign-in expired")
        run = confined.Run("r4", confined.RUNS_ROOT / "r4")
        with self.patched(fake):
            with self.assertRaisesRegex(confined.ConfinedError, "credential_process failed"):
                with confined.launch_confined(run, ["/bin/true"], "bedrock", 60):
                    pass
        self.assertIsNone(fake.popen_argv)

    def test_timeout_over_session_cap_is_refused(self):
        confined.check_timeout(3300)
        with self.assertRaises(confined.ConfinedError):
            confined.check_timeout(3301)

    def test_include_live_only_is_refused(self):
        with self.assertRaisesRegex(confined.ConfinedError, "include-live-only"):
            confined.preflight(600, include_live_only=True)

    def test_unit_has_private_dev_shm(self):
        run = confined.Run("r5", confined.RUNS_ROOT / "r5")
        argv = confined.systemd_run_argv(run, "apex-eval-r5", ["/bin/true"], 60)
        self.assertIn("TemporaryFileSystem=/dev/shm", argv)
        self.assertIn("IPAddressAllow=10.9.0.2", argv)

    def test_triggering_query_goes_through_launch_confined(self):
        seen = {}

        @contextlib.contextmanager
        def fake_launch(run, argv, policy_kind, timeout, **kw):
            seen.update(argv=argv, policy_kind=policy_kind)
            yield mock.Mock()

        # A direct Popen (the old path) must fail here, never start claude.
        no_popen = mock.Mock(side_effect=AssertionError("direct Popen of claude"))
        with mock.patch.object(confined, "launch_confined", fake_launch), \
             mock.patch.object(run_triggering.subprocess, "Popen", no_popen), \
             mock.patch.object(confined, "cleanup_run", return_value=[]), \
             mock.patch.object(run_triggering, "parse_stream_for_trigger",
                               return_value={"triggered": True}):
            skill = self.tmp / "s"
            skill.mkdir()
            (skill / "SKILL.md").write_text("x")
            out = run_triggering.run_single_query("q", "s", skill, None, 90)
        self.assertEqual(out, {"triggered": True})
        self.assertEqual(seen["argv"][0], str(confined.CLAUDE_BIN))
        self.assertEqual(seen["policy_kind"], "bedrock")


def fake_proc(lines=(), returncode=0):
    """A finished systemd-run client whose stdout is `lines`. The stream
    readers read a finished client's output as one tail, so each fake
    stream that must parse is one line."""
    proc = mock.Mock()
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    proc.returncode = returncode
    proc.stdout = io.BytesIO("".join(line + "\n" for line in lines).encode())
    proc.stderr = io.BytesIO(b"")
    return proc


INIT = '{"type":"system","subtype":"init","skills":[]}'
ASK = ('{"type":"assistant","message":{"content":[{"type":"tool_use",'
       '"name":"AskUserQuestion","input":{"questions":[{"question":"Which region?"}]}}]}}')


class LaunchSiteTests(ConfinedTestCase):
    """Every claude launch goes through launch_confined. subprocess.Popen
    raises for the whole test, so no real claude can start."""

    def launches(self, *procs):
        seen = []
        queue = list(procs)

        @contextlib.contextmanager
        def fake_launch(run, argv, policy_kind, timeout, **kw):
            seen.append({"argv": argv, "policy_kind": policy_kind, **kw})
            yield queue.pop(0)

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("subprocess.Popen",
                                       side_effect=AssertionError("direct Popen")))
        stack.enter_context(mock.patch.object(confined, "launch_confined", fake_launch))
        stack.enter_context(mock.patch.object(confined, "cleanup_run", return_value=[]))
        stack.enter_context(mock.patch.object(confined, "read_back", return_value=[]))
        return seen, stack

    def subject(self, elicit=None):
        skill = self.tmp / "skill"
        skill.mkdir(exist_ok=True)
        (skill / "SKILL.md").write_text("---\nname: skill\n---\n")
        return run_task_evals.run_subject(
            prompt="p", skill_name="skill", repo_skill_dir=skill, with_skill=True,
            model="m", timeout=60, run_dir=self.tmp / "run",
            elicitation=elicitation.ElicitationConfig.from_dict(elicit),
        )

    def assert_confined(self, seen, n):
        self.assertEqual(len(seen), n)
        for call in seen:
            self.assertEqual(call["argv"][0], str(confined.CLAUDE_BIN))
            self.assertEqual(call["policy_kind"], "bedrock")

    def test_single_shot_subject(self):
        seen, stack = self.launches(fake_proc([INIT]))
        with stack:
            out = self.subject()
        self.assertTrue(out["ok"], out)
        self.assert_confined(seen, 1)

    def test_each_elicitation_turn(self):
        seen, stack = self.launches(fake_proc([ASK]), fake_proc([INIT]))
        elicit = {"strategy": "canned-multiturn", "max_turns": 3,
                  "turns": [{"question_match": "region", "answer": "us-west-2"}]}
        with stack:
            out = self.subject(elicit)
        self.assertTrue(out["ok"], out)
        self.assert_confined(seen, 2)
        self.assertEqual([c["unit_suffix"] for c in seen], ["t1", "t2"])

    def test_failed_turn_fails_the_subject(self):
        seen, stack = self.launches(fake_proc([ASK], returncode=1), fake_proc([INIT]))
        elicit = {"strategy": "canned-multiturn", "max_turns": 3,
                  "turns": [{"question_match": "region", "answer": "us-west-2"}]}
        with stack:
            out = self.subject(elicit)
        self.assertFalse(out["ok"])
        self.assertIn("turn 1 exited 1", out["reason"])
        self.assertEqual(len(seen), 1)

    def test_grader(self):
        transcript = self.tmp / "transcript.md"
        transcript.write_text("t")
        outputs = self.tmp / "outputs"
        outputs.mkdir()
        run_dir = self.tmp / "grader-run"
        run_dir.mkdir()
        seen, stack = self.launches(fake_proc([INIT]))
        with stack:
            out = run_task_evals.run_grader(
                expectations=["e"], transcript_path=transcript, outputs_dir=outputs,
                run_dir=run_dir, model="m", timeout=60,
            )
        self.assertIn("error", out)
        self.assertEqual(out["cleanup_left"], [])
        self.assert_confined(seen, 1)


class StreamTailTests(unittest.TestCase):
    """A client that has already exited leaves its last lines as one tail."""

    def test_task_and_turn_readers_keep_every_tail_line(self):
        for drain in (run_task_evals.drain_stream, elicitation.drain_stream_for_events):
            events, timed_out = drain(fake_proc([INIT, ASK, '{"type":"result"}']), 10)
            self.assertFalse(timed_out)
            self.assertEqual([e["type"] for e in events], ["system", "assistant", "result"], drain)


NOISY = ("import sys; sys.stderr.write('x' * 400000); sys.stderr.flush(); "
         "print('{\"type\":\"system\",\"subtype\":\"init\",\"skills\":[]}')")


class NoisyStderrTests(ConfinedTestCase):
    """A unit that writes more stderr than a pipe holds must not stall the
    run. The fake launch starts a Python child that writes 400 kB to stderr,
    then one stdout line; never claude."""

    def launches(self):
        seen = []

        @contextlib.contextmanager
        def fake_launch(run, argv, policy_kind, timeout, **kw):
            seen.append(argv)
            proc = _REAL_POPEN([sys.executable, "-c", NOISY], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,
                               stderr=kw.get("stderr", subprocess.PIPE))
            try:
                yield proc
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(confined, "launch_confined", fake_launch))
        stack.enter_context(mock.patch.object(confined, "cleanup_run", return_value=[]))
        stack.enter_context(mock.patch.object(confined, "read_back", return_value=[]))
        return seen, stack

    def test_subject_does_not_stall(self):
        skill = self.tmp / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: skill\n---\n")
        seen, stack = self.launches()
        with stack:
            out = run_task_evals.run_subject(
                prompt="p", skill_name="skill", repo_skill_dir=skill, with_skill=True,
                model="m", timeout=8, run_dir=self.tmp / "run",
            )
        self.assertTrue(out["ok"], out.get("reason"))
        self.assertEqual(len(seen), 1)

    def test_grader_does_not_stall(self):
        transcript = self.tmp / "transcript.md"
        transcript.write_text("t")
        outputs = self.tmp / "outputs"
        outputs.mkdir()
        run_dir = self.tmp / "grader-run"
        run_dir.mkdir()
        seen, stack = self.launches()
        with stack:
            out = run_task_evals.run_grader(
                expectations=["e"], transcript_path=transcript, outputs_dir=outputs,
                run_dir=run_dir, model="m", timeout=8,
            )
        self.assertFalse(out.get("timed_out"), out)
        self.assertTrue(out.get("stderr", "").endswith("x" * 100), out.get("stderr", "")[-20:])


class TriggeringFailureTests(ConfinedTestCase):
    def query(self, proc):
        @contextlib.contextmanager
        def fake_launch(run, argv, policy_kind, timeout, **kw):
            yield proc

        skill = self.tmp / "s"
        skill.mkdir(exist_ok=True)
        (skill / "SKILL.md").write_text("x")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
             mock.patch.object(confined, "launch_confined", fake_launch), \
             mock.patch.object(confined, "cleanup_run", return_value=[]):
            return run_triggering.run_single_query("q", "s", skill, None, 90)

    def test_unit_that_never_starts_is_invalid(self):
        out = self.query(fake_proc([], returncode=1))
        self.assertTrue(out["invalid"])
        self.assertIn("no stream", out["invalid_reason"])

    def test_unit_that_exits_non_zero_is_invalid(self):
        out = self.query(fake_proc([INIT], returncode=1))
        self.assertTrue(out["invalid"])
        self.assertIn("exited 1", out["invalid_reason"])

    def test_clean_negative_is_not_invalid(self):
        out = self.query(fake_proc([INIT]))
        self.assertFalse(out["invalid"])
        self.assertFalse(out["triggered"])

    def eval_with(self, single_query):
        with mock.patch.object(run_triggering, "ProcessPoolExecutor", ThreadPoolExecutor), \
             mock.patch.object(run_triggering, "run_single_query", single_query):
            return run_triggering.run_eval(
                [{"query": "q", "should_trigger": False}], "s", "", self.tmp, 1, 90, 1, 0.5, None,
            )

    def test_invalid_run_never_passes_a_negative(self):
        out = self.eval_with(mock.Mock(return_value={
            "triggered": False, "invalid": True, "invalid_reason": "no stream", "init_skills": None,
        }))
        self.assertFalse(out["results"][0]["pass"])
        self.assertEqual(out["results"][0]["runs"], 0)

    def test_failed_mint_stops_the_run(self):
        boom = mock.Mock(side_effect=confined.ConfinedError("role session mint failed"))
        with self.assertRaisesRegex(confined.ConfinedError, "mint failed"):
            self.eval_with(boom)


class ReadBackTests(unittest.TestCase):
    def tar_with(self, entries):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for name, kind in entries:
                ti = tarfile.TarInfo(name)
                if kind == "file":
                    data = b"ok"
                    ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
                elif kind == "dir":
                    ti.type = tarfile.DIRTYPE
                    tf.addfile(ti)
                elif kind == "symlink":
                    ti.type = tarfile.SYMTYPE
                    ti.linkname = "/home/ec2-user/.aws/credentials"
                    tf.addfile(ti)
                elif kind == "hardlink":
                    ti.type = tarfile.LNKTYPE
                    ti.linkname = "./a.txt"
                    tf.addfile(ti)
        return buf.getvalue()

    def test_links_and_unsafe_names_are_dropped(self):
        data = self.tar_with([
            (".", "dir"), ("./a.txt", "file"), ("./d", "dir"), ("./d/b.txt", "file"),
            ("./leak", "symlink"), ("./hard", "hardlink"), ("../up.txt", "file"),
            ("/abs.txt", "file"),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            dropped = confined.extract_safe(data, dest)
            self.assertEqual((dest / "a.txt").read_bytes(), b"ok")
            self.assertEqual((dest / "d" / "b.txt").read_bytes(), b"ok")
            self.assertFalse((dest / "leak").exists() or (dest / "leak").is_symlink())
            self.assertFalse((dest / "hard").exists())
            self.assertFalse((dest.parent / "up.txt").exists())
        self.assertEqual(len(dropped), 4)
        self.assertTrue(any("leak (link)" in d for d in dropped))


if __name__ == "__main__":
    unittest.main()
