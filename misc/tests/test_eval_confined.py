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
import run_triggering  # noqa: E402

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

    def __init__(self, active_units="", mint_rc=0, mint_err=""):
        self.calls = []
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
        proc.returncode = 0
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
        # dir and ~/.aws into the subject's sandbox and HOME.
        fake = FakeHost()
        with self.patched(fake):
            with run_triggering.stage_skill_sandbox("demo", self.make_skill()) as run:
                staged = run.home / ".claude" / "skills" / "demo"
                self.assertTrue(staged.is_dir())
                self.assertFalse(staged.is_symlink())
                self.assertFalse((run.home / ".aws").exists())
                self.assertFalse((run.home / ".aws").is_symlink())
                for p in [staged, *staged.rglob("*")]:
                    self.assertFalse(p.stat().st_mode & stat.S_IWGRP, p)
                    self.assertFalse(p.stat().st_mode & stat.S_IWOTH, p)
                self.assertTrue((staged / "scripts" / "run.sh").stat().st_mode & stat.S_IXGRP)
                self.assertTrue(run.sandbox.stat().st_mode & stat.S_IWGRP)
                root = run.root
        self.assertFalse(root.exists())
        cleanup = [c for c in fake.calls if c[:1] == ["sudo"]]
        self.assertTrue(cleanup, "cleanup unit was not started")

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
