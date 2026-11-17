#!/usr/bin/env python3
"""Tests for the confined eval launches (misc/evals/scripts/confined.py).

systemd-run, systemctl, sudo and aws are mocked: nothing here starts a unit,
mints a session or calls a model.

Run directly with:

    python3 misc/tests/test_eval_confined.py
"""

import contextlib
import functools
import io
import json
import multiprocessing
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(MISC_DIR, "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import confined  # noqa: E402
import elicitation  # noqa: E402
import run_all_evals  # noqa: E402
import run_task_evals  # noqa: E402
import run_triggering  # noqa: E402
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor  # noqa: E402

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
        resolv = self.tmp / "resolv.conf"
        resolv.write_text("nameserver 10.9.0.2\n")
        self.patches = [
            mock.patch.object(confined, "RUNS_ROOT", runs),
            mock.patch.object(confined, "ENV_DIR", env),
            mock.patch.object(confined, "LOCK_FILE", env / "launch.lock"),
            mock.patch.object(confined, "_public_ipv4", ["203.0.113.7"]),
            mock.patch.object(confined, "RESOLV_CONF", resolv),
            # The AWS documentation's example account id.
            mock.patch.object(confined, "_account", "123456789012"),
            mock.patch.object(confined, "HOST_HIDDEN_FILE", self.tmp / "inaccessible-paths"),
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

    def test_link_at_or_above_the_staged_root_is_refused(self):
        # Each shape git can check out: files itself, files/shared,
        # files/eval-<id> (stage_fixture_files) and skills/<name> (stage_run).
        outside = self.tmp / "outside"
        (outside / "shared").mkdir(parents=True)
        (outside / "shared" / "creds").write_text("HOST-SECRET")
        evals = self.tmp / "evals"
        shapes = {
            "files": (evals / "a", "files", outside),
            "shared": (evals / "b", "files/shared", outside / "shared"),
            "eval-id": (evals / "c", "files/eval-1", outside / "shared"),
        }
        for label, (skill_eval_dir, rel, target) in shapes.items():
            link = skill_eval_dir / rel
            link.parent.mkdir(parents=True)
            link.symlink_to(target)
            sandbox = self.tmp / f"sb-{label}"
            sandbox.mkdir()
            with self.assertRaisesRegex(confined.ConfinedError, "symlink", msg=label):
                run_task_evals.stage_fixture_files(sandbox, skill_eval_dir, 1, ["creds"])
            self.assertEqual(list(sandbox.iterdir()), [], label)
        skill_link = self.tmp / "skills" / "demo"
        skill_link.parent.mkdir()
        skill_link.symlink_to(self.make_skill())
        with self.assertRaisesRegex(confined.ConfinedError, "symlink"):
            confined.stage_run("demo", skill_link)
        self.assertEqual(list(confined.RUNS_ROOT.iterdir()), [])

    def test_unsafe_eval_id_is_refused_before_any_path(self):
        files = self.tmp / "skill-evals" / "files" / "shared"
        files.mkdir(parents=True)
        (files / "a.txt").write_text("a")
        sandbox = self.tmp / "sb"
        sandbox.mkdir()
        for bad in ("../up", "1\n"):
            with self.assertRaisesRegex(confined.ConfinedError, "bad eval id"):
                run_task_evals.stage_fixture_files(sandbox, self.tmp / "skill-evals", bad, ["a.txt"])
        self.assertEqual(list(sandbox.iterdir()), [])

    def test_run_skill_refuses_a_bad_eval_id_before_any_path(self):
        evals = self.tmp / "evals"
        (evals / "demo").mkdir(parents=True)
        (evals / "demo" / "evals.json").write_text(
            '{"evals": [{"id": "../../escape", "prompt": "p", "expectations": ["e"]}]}')
        (self.tmp / "skills").mkdir()
        shutil.copytree(self.make_skill(), self.tmp / "skills" / "demo")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
             mock.patch.object(run_task_evals, "EVALS_ROOT", evals), \
             mock.patch.object(run_task_evals, "REPO_ROOT", self.tmp), \
             mock.patch.object(confined, "launch_confined", side_effect=AssertionError("launch")):
            out = run_task_evals.run_skill("demo", model="m", runs=1, subject_timeout=60,
                                           grader_timeout=60)
        self.assertIn("bad eval ids", out.get("error", ""), out)
        self.assertFalse((evals / "demo" / "workspace").exists())

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
        self.assertEqual(mint[mint.index("--role-arn") + 1],
                         f"arn:aws:iam::123456789012:role/{confined.ROLE_NAME}")
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
        self.assertIn("TemporaryFileSystem=/dev/shm:mode=1777", argv)
        self.assertIn("IPAddressAllow=10.9.0.2", argv)

    def test_skill_copy_is_bound_read_only_for_the_subject(self):
        # Without the binds, the subject can rename .claude/skills (or
        # .claude) and put its own skill in its place.
        src = self.tmp / "src" / "demo"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("x")
        run = confined.stage_run("demo", src)
        home = run.home
        subject = confined.systemd_run_argv(run, "u", confined.claude_argv([]), 60)
        self.assertIn(f"BindPaths={home / '.claude'}", subject)
        self.assertIn(f"BindReadOnlyPaths={home / '.claude' / 'skills'}", subject)
        cleanup = confined.systemd_run_argv(run, "u", ["/usr/bin/find"], 60, lock_skills=False)
        self.assertFalse([a for a in cleanup if a.startswith("BindPaths=")], cleanup)
        empty = confined.stage_run()
        argv = confined.systemd_run_argv(empty, "u", confined.claude_argv([]), 60)
        self.assertFalse([a for a in argv if ".claude" in a], argv)
        fake = FakeHost()
        with self.patched(fake):
            confined.cleanup_run(run)
        self.assertNotIn(f"BindPaths={home / '.claude'}", fake.popen_argv)

    def test_host_hidden_paths_come_from_the_host_file(self):
        run = confined.Run("r6", confined.RUNS_ROOT / "r6")

        def hidden():
            argv = confined.systemd_run_argv(run, "u", ["/bin/true"], 60)
            return next(a for a in argv if a.startswith("InaccessiblePaths="))

        self.assertEqual(hidden(), "InaccessiblePaths=-/var/log")
        confined.HOST_HIDDEN_FILE.write_text("/var/lib/other\n\n")
        self.assertEqual(hidden(), "InaccessiblePaths=-/var/log -/var/lib/other")
        for bad in ("var/lib/x\n", "/var/lib/a b\n", "# x\n", "/\n", "/var/../etc\n",
                    "/var/x\0y\n"):
            confined.HOST_HIDDEN_FILE.write_text(bad)
            with self.assertRaisesRegex(confined.ConfinedError, "plain absolute path"):
                hidden()
        confined.HOST_HIDDEN_FILE.write_bytes(b"/var/\xff\n")
        with self.assertRaisesRegex(confined.ConfinedError, "cannot read"):
            hidden()

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
    """A finished systemd-run client whose stdout is `lines`."""
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

    def test_failed_later_turn_fails_the_subject(self):
        seen, stack = self.launches(fake_proc([ASK]), fake_proc([INIT], returncode=1))
        elicit = {"strategy": "canned-multiturn", "max_turns": 3,
                  "turns": [{"question_match": "region", "answer": "us-west-2"}]}
        with stack:
            out = self.subject(elicit)
        self.assertFalse(out["ok"])
        self.assertIn("turn 2 exited 1", out["reason"])

    def test_grader(self):
        transcript = self.tmp / "transcript.md"
        transcript.write_text("t")
        outputs = self.tmp / "outputs"
        outputs.mkdir()
        run_dir = self.tmp / "grader-run"
        run_dir.mkdir()
        seen, stack = self.launches(fake_proc([INIT]))
        left = []
        with stack:
            out = run_task_evals.run_grader(
                expectations=["e"], transcript_path=transcript, outputs_dir=outputs,
                run_dir=run_dir, model="m", timeout=60, left_out=left,
            )
        self.assertIn("error", out)
        self.assertEqual(left, [])
        self.assert_confined(seen, 1)

    def test_cleanup_left_reaches_the_subject_and_grader_results(self):
        def cleanup(run):
            run.left.append("left by cleanup")
            return run.left

        transcript = self.tmp / "transcript.md"
        transcript.write_text("t")
        outputs = self.tmp / "outputs"
        outputs.mkdir()
        run_dir = self.tmp / "grader-run"
        run_dir.mkdir()
        seen, stack = self.launches(fake_proc([INIT]), fake_proc([INIT]))
        left = []
        with stack, mock.patch.object(confined, "cleanup_run", side_effect=cleanup):
            out = self.subject()
            run_task_evals.run_grader(
                expectations=["e"], transcript_path=transcript, outputs_dir=outputs,
                run_dir=run_dir, model="m", timeout=60, left_out=left,
            )
        self.assertEqual(out["cleanup_left"], ["left by cleanup"])
        self.assertEqual(left, ["left by cleanup"])


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
    then one stdout line; subprocess.Popen raises, so never claude."""

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
        stack.enter_context(mock.patch("subprocess.Popen",
                                       side_effect=AssertionError("direct Popen")))
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
                run_dir=run_dir, model="m", timeout=8, left_out=[],
            )
        self.assertFalse(out.get("timed_out"), out)
        self.assertTrue(out.get("stderr", "").endswith("x" * 100), out.get("stderr", "")[-20:])

    def test_triggering_query_does_not_stall(self):
        skill = self.tmp / "s"
        skill.mkdir()
        (skill / "SKILL.md").write_text("x")
        seen, stack = self.launches()
        with stack:
            out = run_triggering.run_single_query("q", "s", skill, None, 8)
        self.assertFalse(out["invalid"], out)
        self.assertEqual(len(seen), 1)

    def test_multiturn_turn_does_not_stall(self):
        skill = self.tmp / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: skill\n---\n")
        seen, stack = self.launches()
        elicit = {"strategy": "canned-multiturn", "max_turns": 3,
                  "turns": [{"question_match": "region", "answer": "us-west-2"}]}
        with stack:
            out = run_task_evals.run_subject(
                prompt="p", skill_name="skill", repo_skill_dir=skill, with_skill=True,
                model="m", timeout=8, run_dir=self.tmp / "run",
                elicitation=elicitation.ElicitationConfig.from_dict(elicit),
            )
        self.assertTrue(out["ok"], out.get("reason"))
        self.assertEqual(len(seen), 1)


class TriggeringFailureTests(ConfinedTestCase):
    def query(self, proc, cleanup=lambda run: []):
        @contextlib.contextmanager
        def fake_launch(run, argv, policy_kind, timeout, **kw):
            yield proc

        skill = self.tmp / "s"
        skill.mkdir(exist_ok=True)
        (skill / "SKILL.md").write_text("x")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
             mock.patch.object(confined, "launch_confined", fake_launch), \
             mock.patch.object(confined, "cleanup_run", side_effect=cleanup):
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

    def test_cleanup_left_reaches_the_result_and_the_row(self):
        def cleanup(run):
            run.left.append("left by cleanup")
            return run.left

        out = self.query(fake_proc([INIT]), cleanup=cleanup)
        self.assertEqual(out["cleanup_left"], ["left by cleanup"])
        rows = self.eval_with(mock.Mock(return_value={
            "triggered": False, "invalid": False, "init_skills": [],
            "cleanup_left": ["left by cleanup"],
        }))
        self.assertEqual(rows["results"][0]["cleanup_left"], ["left by cleanup"])

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

    def test_failed_mint_starts_no_queued_job_on_the_real_pool(self):
        # The real ProcessPoolExecutor, forked so the fake query below (and
        # the Popen and launch guards) reach the workers: no launch, no Popen.
        started = self.tmp / "started"

        def fake_query(query, *a):
            with open(started, "a") as f:
                f.write(query + "\n")
            if query == "q0":
                raise confined.ConfinedError("role session mint failed")
            time.sleep(0.3)
            return {"triggered": False, "invalid": False, "init_skills": []}

        pool = functools.partial(ProcessPoolExecutor,
                                 mp_context=multiprocessing.get_context("fork"))
        queries = [{"query": f"q{i}", "should_trigger": False} for i in range(20)]
        with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
             mock.patch.object(confined, "launch_confined", side_effect=AssertionError("launch")), \
             mock.patch.object(run_triggering, "ProcessPoolExecutor", pool), \
             mock.patch.object(run_triggering, "run_single_query", fake_query):
            with self.assertRaisesRegex(confined.ConfinedError, "mint failed"):
                run_triggering.run_eval(queries, "s", "", self.tmp, 2, 90, 1, 0.5, None)
        # Only q0 and at most the one job running beside it start. The old
        # `with` exit started all 20.
        names = started.read_text().split()
        self.assertIn("q0", names)
        self.assertLessEqual(set(names), {"q0", "q1"}, names)


class RunErrorMetricsTests(unittest.TestCase):
    def test_run_errors_are_left_out_of_the_skill_scores(self):
        # q1 passes, q2 passes, q3 leaks; q4 and q5 never ran (invalid).
        answers = {"q1": True, "q2": False, "q3": True}

        def single_query(query, *a):
            if query in answers:
                return {"triggered": answers[query], "invalid": False, "init_skills": []}
            return {"triggered": False, "invalid": True, "invalid_reason": "no stream",
                    "init_skills": None}

        triggering = [{"query": "q1", "should_trigger": True}] + [
            {"query": q, "should_trigger": False} for q in ("q2", "q3", "q4", "q5")]
        with mock.patch.object(run_triggering, "ProcessPoolExecutor", ThreadPoolExecutor), \
             mock.patch.object(run_triggering, "run_single_query", single_query):
            raw = run_triggering.run_eval(triggering, "s", "", Path("."), 1, 90, 1, 0.5, None)
        m = run_all_evals.enrich_metrics(raw, triggering, {}, [], {})
        self.assertEqual((m["overall"]["passed"], m["overall"]["total"]), (2, 5))
        for t in m["threshold_sweep"].values():
            self.assertEqual((t["passed"], t["total"]), (2, 3))
        self.assertEqual(m["leakage"], {"other": {"total": 2, "leaked": 1}})
        self.assertEqual(m["mean_trigger_rate_negative"], 0.5)
        self.assertEqual(m["overall"]["run_errors"], 2)


class PublicIpTests(unittest.TestCase):
    """IMDS is mocked: urlopen never reaches the network."""

    def setUp(self):
        p = mock.patch.object(confined, "_public_ipv4", None)
        p.start()
        self.addCleanup(p.stop)

    def test_imds_failure_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(confined.ConfinedError):
                confined.public_ipv4()

    def test_404_is_no_public_ipv4(self):
        token = mock.Mock()
        token.read.return_value = b"tok"
        err = urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=[token, err]):
            self.assertEqual(confined.public_ipv4(), [])

    def test_other_http_error_raises(self):
        token = mock.Mock()
        token.read.return_value = b"tok"
        err = urllib.error.HTTPError("u", 500, "err", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=[token, err]):
            with self.assertRaises(confined.ConfinedError):
                confined.public_ipv4()


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
                    ti.linkname = "/home/someone/.aws/credentials"
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


class PreflightTests(ConfinedTestCase):
    """preflight reads the account, IMDS and the resolver before any mint."""

    def setUp(self):
        super().setUp()
        config = self.tmp / "aws-config"
        config.write_text("[profile apex-eval-admin]\n")
        claude = self.tmp / "claude"
        claude.write_text("")
        for p in (
            mock.patch.object(confined, "PARENT_AWS_CONFIG", config),
            mock.patch.object(confined, "CLAUDE_BIN", claude),
            mock.patch.object(confined.shutil, "which", return_value="/usr/bin/aws"),
        ):
            p.start()
            self.addCleanup(p.stop)
        # The base class's patch restores these when the test ends.
        confined._account = None

    def host(self, account="123456789012\n", rc=0, err="ExpiredToken"):
        fake = FakeHost()
        base = fake.run

        def run(argv, **kw):
            if argv[:3] == ["aws", "sts", "get-caller-identity"]:
                fake.calls.append(list(argv))
                fake.identity_env = kw.get("env")
                return _Done(returncode=rc, stdout=account, stderr=err if rc else "")
            return base(argv, **kw)

        fake.run = run
        return fake

    def test_reads_the_account_at_run_time(self):
        fake = self.host()
        caller = {"AWS_PROFILE": "caller", "AWS_ACCESS_KEY_ID": "caller-key"}
        with self.patched(fake), mock.patch.dict(os.environ, caller):
            confined.preflight(600)
        ident = next(c for c in fake.calls if c[:3] == ["aws", "sts", "get-caller-identity"])
        self.assertEqual(ident[ident.index("--profile") + 1], confined.PARENT_PROFILE)
        self.assertEqual(fake.identity_env["AWS_CONFIG_FILE"], str(confined.PARENT_AWS_CONFIG))
        self.assertEqual({k: v for k, v in fake.identity_env.items() if k.startswith("AWS_")},
                         {"AWS_CONFIG_FILE": str(confined.PARENT_AWS_CONFIG),
                          "AWS_SHARED_CREDENTIALS_FILE": os.devnull})
        self.assertEqual(confined.role_arn(),
                         f"arn:aws:iam::123456789012:role/{confined.ROLE_NAME}")
        self.assertFalse(any(c[:3] == ["aws", "sts", "assume-role"] for c in fake.calls))

    def test_unreadable_account_fails_closed(self):
        for kw in ({"rc": 255, "account": ""}, {"account": "None\n"}):
            confined._account = None
            fake = self.host(**kw)
            with self.patched(fake), \
                 self.assertRaisesRegex(confined.ConfinedError, "cannot read the account"):
                confined.preflight(600)
            self.assertFalse(any(c[:3] == ["aws", "sts", "assume-role"] for c in fake.calls))

    def test_failed_account_read_fails_closed_and_names_the_sign_in(self):
        # rc 1 with a 12-digit stdout still fails; an expired credential_process
        # gets the renew hint. (mint_role_session's session-name check at
        # fullmatch stays untested: its names are built here, evals-<run id>.)
        fake = self.host(rc=1, err="Error when retrieving credentials from custom-process")
        with self.patched(fake), \
             self.assertRaisesRegex(confined.ConfinedError, "renew its sign-in"):
            confined.preflight(600)
        self.assertFalse(any(c[:3] == ["aws", "sts", "assume-role"] for c in fake.calls))

    def test_bad_host_file_stops_preflight_before_any_mint(self):
        confined.HOST_HIDDEN_FILE.write_text("var/lib/x\n")
        fake = self.host()
        with self.patched(fake), \
             self.assertRaisesRegex(confined.ConfinedError, "plain absolute path"):
            confined.preflight(600)
        self.assertFalse(any(c[:3] == ["aws", "sts", "assume-role"] for c in fake.calls))

    def test_no_aws_cli_is_refused(self):
        with mock.patch.object(confined.shutil, "which", return_value=None), \
             self.patched(self.host()), \
             self.assertRaisesRegex(confined.ConfinedError, "AWS CLI"):
            confined.preflight(600)

    def test_imds_and_resolver_are_read_in_preflight(self):
        confined._public_ipv4 = None
        with self.patched(self.host()), \
             mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")), \
             self.assertRaisesRegex(confined.ConfinedError, "IMDSv2"):
            confined.preflight(600)
        confined._public_ipv4 = ["203.0.113.7"]
        confined.RESOLV_CONF.write_text("nameserver 127.0.0.53\n")
        with self.patched(self.host()), \
             self.assertRaisesRegex(confined.ConfinedError, "loopback"):
            confined.preflight(600)


class ActiveUnitTests(ConfinedTestCase):
    def test_deactivating_units_counted_and_rc_checked(self):
        fake = FakeHost()
        with self.patched(fake):
            confined._active_units()
        argv = next(c for c in fake.calls if c[:2] == ["systemctl", "list-units"])
        self.assertTrue(any("deactivating" in a for a in argv), argv)

        class Bad(FakeHost):
            def run(self, argv, **kw):
                if argv[:2] == ["systemctl", "list-units"]:
                    return _Done(returncode=1, stderr="dbus")
                return super().run(argv, **kw)

        with self.patched(Bad()):
            with self.assertRaises(confined.ConfinedError):
                confined._active_units()

    def test_cgnat_in_deny(self):
        self.assertIn("100.64.0.0/10", confined.IP_DENY)


class RealClientExitTests(ConfinedTestCase):
    def test_real_client_non_zero_exit_is_invalid(self):
        # A real child reaches EOF before poll() sees its exit (the EOF branch).
        code = f"import sys; print({INIT!r}, flush=True); sys.exit(1)"

        @contextlib.contextmanager
        def fake_launch(run, argv, policy_kind, timeout, **kw):
            p = _REAL_POPEN([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                yield p
            finally:
                p.wait()
                p.stdout.close()

        skill = self.tmp / "s"
        skill.mkdir()
        (skill / "SKILL.md").write_text("x")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
             mock.patch.object(confined, "launch_confined", fake_launch), \
             mock.patch.object(confined, "cleanup_run", return_value=[]):
            out = run_triggering.run_single_query("q", "s", skill, None, 30)
        self.assertTrue(out["invalid"], out)


class TriggerStreamTests(unittest.TestCase):
    def test_timeout_after_init_is_invalid(self):
        code = f"import time; print({INIT!r}, flush=True); time.sleep(30)"
        p = _REAL_POPEN([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out = run_triggering.parse_stream_for_trigger(p, "s", timeout=2)
        p.stdout.close()
        self.assertTrue(out["invalid"], out)
        self.assertIn("timed out", out["invalid_reason"])
        self.assertIsNotNone(p.poll())

    def test_client_alive_after_eof_is_invalid(self):
        # stdout closes, then the client lives past the 5 s wait and exits 1.
        code = (f"import os, time; print({INIT!r}, flush=True); os.close(1); "
                "time.sleep(7); os._exit(1)")
        p = _REAL_POPEN([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out = run_triggering.parse_stream_for_trigger(p, "s", timeout=30)
        p.stdout.close()
        self.assertTrue(out["invalid"], out)
        self.assertIn("no exit code", out["invalid_reason"])

    def test_every_tail_line_is_read_and_the_pending_block_carried(self):
        skill_use = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "s"}}]}})
        start = json.dumps({"type": "stream_event", "event": {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "name": "Skill", "input": {}}}})
        delta = json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": '{"skill":"s"}'}}})
        # A last line with no newline; a block split across tail lines.
        for tail in (f"{INIT}\n{skill_use}", f"{INIT}\n{start}\n{delta}\n"):
            proc = fake_proc()
            proc.stdout = io.BytesIO(tail.encode())
            out = run_triggering.parse_stream_for_trigger(proc, "s", timeout=10)
            self.assertTrue(out["triggered"], tail)


class TaskMainTests(unittest.TestCase):
    def test_failed_mint_stops_the_task_run(self):
        err = io.StringIO()
        boom = confined.ConfinedError("role session mint failed")
        with mock.patch.object(confined, "preflight", return_value="2.0.0"), \
             mock.patch.object(run_task_evals, "discover_skills", return_value=["a", "b"]), \
             mock.patch.object(run_task_evals, "run_skill", side_effect=boom) as run_skill, \
             mock.patch.object(sys, "argv", ["run_task_evals.py", "--model", "m"]), \
             contextlib.redirect_stderr(err):
            rc = run_task_evals.main()
        self.assertEqual(rc, 1)
        self.assertIn("run stopped: role session mint failed", err.getvalue())
        self.assertEqual(run_skill.call_count, 1)
        self.assertEqual(run_skill.call_args.kwargs["claude_version"], "2.0.0")


class RunSkillRecordTests(ConfinedTestCase):
    """run_skill with the subject, grader and benchmark mocked."""

    def test_live_only_dropped_and_version_and_cleanup_recorded(self):
        evals = self.tmp / "evals"
        (evals / "demo").mkdir(parents=True)
        (evals / "demo" / "evals.json").write_text(json.dumps({"evals": [
            {"id": 1, "prompt": "needs a cluster", "expectations": ["e"], "live_only": True},
            {"id": 2, "prompt": "offline", "expectations": ["e"]},
        ]}))
        (self.tmp / "skills" / "demo").mkdir(parents=True)
        (self.tmp / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\ndescription: d\n---\n")
        prompts = []

        def subject(**kw):
            prompts.append(kw["prompt"])
            kw["run_dir"].mkdir(parents=True)
            return {"ok": True, "transcript_path": str(self.tmp / "t"),
                    "outputs_dir": str(self.tmp / "o"), "cleanup_left": ["subject left"]}

        def grader(**kw):
            kw["left_out"].append("grader left")
            return {"summary": {}}

        def benchmark(skill, runs_dir):
            (runs_dir / "benchmark.json").write_text("{}")

        with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
             mock.patch.object(confined, "launch_confined", side_effect=AssertionError("launch")), \
             mock.patch.multiple(
                 run_task_evals, EVALS_ROOT=evals, REPO_ROOT=self.tmp,
                 HISTORY_DIR=self.tmp / "history", run_subject=subject, run_grader=grader,
                 run_benchmark=benchmark, update_latest_symlink=mock.Mock()):
            out = run_task_evals.run_skill("demo", model="m", runs=1, subject_timeout=60,
                                           grader_timeout=60, claude_version="2.0.0")
        self.assertEqual(prompts, ["offline", "offline"])
        infos = [json.loads(p.read_text()) for p in Path(out["runs_dir"]).rglob("confined.json")]
        self.assertEqual(len(infos), 2)
        for info in infos:
            self.assertEqual(info, {"claude_version": "2.0.0",
                                    "subject_cleanup_left": ["subject left"],
                                    "grader_cleanup_left": ["grader left"]})
        row = json.loads((self.tmp / "history" / "demo.jsonl").read_text())
        self.assertEqual(row["claude_version"], "2.0.0")


class AllEvalsHistoryTests(unittest.TestCase):
    def test_history_row_records_the_confined_claude_version(self):
        append = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "s").mkdir()
            (Path(tmp) / "s" / "triggering.json").write_text("[]")
            (Path(tmp) / "s" / "README.md").write_text("")
            with mock.patch("subprocess.Popen", side_effect=AssertionError("direct Popen")), \
                 mock.patch.multiple(
                     run_all_evals, EVALS_ROOT=Path(tmp), append_history=append,
                     hygiene_check=mock.Mock(return_value=mock.Mock(warnings=[])),
                     parse_sibling_map=mock.Mock(return_value=["x"]),
                     build_index_to_sibling=mock.Mock(return_value=({}, [], [])),
                     read_history=mock.Mock(return_value=[]),
                     load_task_benchmark=mock.Mock(return_value=None),
                     previous_task_mean=mock.Mock(return_value=None),
                     build_snapshot=mock.Mock(return_value={"started_at": "t"}),
                     run_triggering=mock.Mock(return_value=(0, "{}", "")),
                     extract_run_eval_json=mock.Mock(
                         return_value={"confined_claude_version": "2.0.0"}),
                     enrich_metrics=mock.Mock(return_value={}),
                     persist_artifacts=mock.Mock(return_value=Path(tmp)),
                     history_compact_entry=mock.Mock(return_value={}),
                     compute_from_workspace=mock.Mock(return_value=None),
                     load_config=mock.Mock()):
                run_all_evals.process_skill(
                    "s", model_flag=None, runs_flag=None, workers_flag=None,
                    skip_triggering=False, resolved_model="m", resolved_provider="bedrock",
                    resolved_runs=1)
        self.assertEqual(append.call_args.args[1]["claude_version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
