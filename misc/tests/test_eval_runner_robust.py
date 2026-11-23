#!/usr/bin/env python3
"""Tests for eval runner input handling: event lines that are not JSON
objects, user messages with string content, tool calls with no input, the
tool-args-schema check, fixture files leaking into the graded outputs,
validators that pass with nothing to check, and the eval-role credentials
(no host ~/.aws in the subject's HOME, parent AWS_* dropped, refusal on a
wrong account, a missing expected-account file, a sign-in failure, no
Bedrock route for the model or a failed refresh mid-run).

No test calls a model, starts a `claude` process or reaches AWS. The two
stream readers are fed by a child Python process that only prints fixed
lines; the credential tests put a fake `aws` first on PATH.

Run directly with:

    python3 -B misc/tests/test_eval_runner_robust.py
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

# Make misc/evals/scripts importable regardless of CWD.
MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(MISC_DIR, "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import artifact_validation  # noqa: E402
import process_assertions  # noqa: E402
import parse_trajectory  # noqa: E402
import regression  # noqa: E402
import run_artifact_validation  # noqa: E402
from elicitation import drain_stream_for_events  # noqa: E402
from parse_trajectory import parse_events  # noqa: E402
from run_knowledge_assertions import extract_assistant_text  # noqa: E402
from run_task_evals import (  # noqa: E402
    compute_metrics,
    drain_stream,
    format_transcript,
    snapshot_sandbox_outputs,
    stage_fixture_files,
)
import run_task_evals  # noqa: E402
import run_triggering  # noqa: E402
import snapshot  # noqa: E402
import elicitation  # noqa: E402
from run_triggering import _handle_line  # noqa: E402

# The host's CLIs may differ from the runners' pinned versions, so the
# version check is off for every test but CliVersionCheck's.
REAL_CHECK_CLI_VERSIONS = run_triggering.check_cli_versions
_CLI_CHECK_OFF = [mock.patch.object(m, "check_cli_versions", return_value=None)
                  for m in (run_triggering, run_task_evals)]


def setUpModule():
    for p in _CLI_CHECK_OFF:
        p.start()


def tearDownModule():
    for p in _CLI_CHECK_OFF:
        p.stop()

REPO = Path(MISC_DIR).parent
HAS_BASE_TAG = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet",
     run_task_evals.DEFAULT_BASE_REF + "^{commit}"], capture_output=True).returncode == 0
NO_TAG = f"needs the {run_task_evals.DEFAULT_BASE_REF} tag (absent in a tagless archive)"


def tool_use(name, **extra):
    block = {"type": "tool_use", "name": name}
    block.update(extra)
    return block


def assistant(*blocks):
    return {"type": "assistant", "message": {"content": list(blocks)}}


REAL_POPEN = subprocess.Popen  # the adapter tests swap subprocess.Popen


def printer(lines, code=0, sleep=0.0):
    """A child process that prints `lines`, sleeps, exits `code`; never a harness."""
    src = ("import sys, time\nfor l in %r:\n    sys.stdout.write(l + '\\n')\n"
           "sys.stdout.flush()\ntime.sleep(%r)\nsys.exit(%d)\n") % (list(lines), sleep, code)
    return REAL_POPEN([sys.executable, "-c", src], stdout=subprocess.PIPE)


class NonObjectEventLines(unittest.TestCase):
    """A JSON Lines line that parses to a list, a string, a number or null
    is skipped, not a crash."""

    def test_parse_events_skips_and_counts_non_dict_events(self):
        events = [["a"], 3, "text", None, assistant(tool_use("Read", input={})),
                  {"type": "result", "duration_ms": 5}]
        traj = parse_events(events)
        self.assertEqual(traj.skipped_events, 4)
        self.assertEqual(traj.total_tool_calls, 1)
        self.assertEqual(traj.duration_ms, 5)
        self.assertEqual(traj.to_dict()["skipped_events"], 4)

    def test_parse_events_skips_non_dict_user_blocks(self):
        user = {"type": "user", "message": {"content": [
            "junk", {"type": "tool_result", "content": "ok"}]}}
        traj = parse_events([assistant(tool_use("Read", input={})), user])
        self.assertEqual(traj.total_tool_calls, 1)
        self.assertEqual(traj.steps[0].tool_calls[0].result, "ok")

    def test_user_string_content_in_transcript_and_metrics(self):
        events = [{"type": "user", "message": {"content": "hi"}}]
        self.assertIn("# Subject transcript", format_transcript(events, "p", None))
        with tempfile.TemporaryDirectory() as tmp:
            metrics = compute_metrics(events, "", Path(tmp))
        self.assertEqual(metrics["errors_encountered"], 0)

    def test_knowledge_text_reader_skips_non_object_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('[1]\n'
                            + json.dumps(assistant({"type": "text", "text": "hi"}))
                            + "\n")
            self.assertEqual(extract_assistant_text(path), "hi")

    def test_trigger_line_parser_skips_non_object_line(self):
        out = {"triggered": False}
        pending = _handle_line("[1, 2]", "eks-recon", out, lambda skills: None,
                               lambda *a: None, None)
        self.assertIsNone(pending)
        self.assertFalse(out["triggered"])

    def test_task_stream_reader_drops_non_object_lines(self):
        proc = printer(["[1]", "7", json.dumps({"type": "result"}), '"tail"'])
        events, timed_out = drain_stream(proc, timeout=30)
        proc.stdout.close()
        self.assertFalse(timed_out)
        self.assertEqual(events, [{"type": "result"}])

    def test_elicitation_stream_reader_drops_non_object_lines(self):
        proc = printer(["[1]", json.dumps({"type": "result"}), "null"])
        events, timed_out = drain_stream_for_events(proc, timeout=30)
        proc.stdout.close()
        self.assertFalse(timed_out)
        self.assertEqual(events, [{"type": "result"}])


class MissingToolInput(unittest.TestCase):
    """A tool call with no input stays distinguishable from an empty one."""

    def test_missing_and_null_input_read_as_none(self):
        traj = parse_events([assistant(tool_use("A"), tool_use("B", input=None),
                                       tool_use("C", input={}))])
        inputs = [tc.input for tc in traj.steps[0].tool_calls]
        self.assertEqual(inputs, [None, None, {}])



class ToolArgsSchemaCheck(unittest.TestCase):
    """The tool-args-schema check fails rather than guessing, and a tool that
    is never called passes only when every call must match."""

    def check(self, events, **extra):
        spec = {"type": "tool-args-schema", "tool": "T", "schema": {"type": "object"}}
        spec.update(extra)
        return process_assertions.evaluate(parse_events(events), [spec]).results[0]

    def test_missing_input_fails_naming_the_call(self):
        res = self.check([assistant(tool_use("T", input={}), tool_use("T"))])
        self.assertFalse(res.passed)
        self.assertIn("no input at indices [1]", res.evidence)

    def test_without_jsonschema_the_check_fails(self):
        with mock.patch.object(process_assertions, "_HAS_JSONSCHEMA", False):
            res = self.check([assistant(tool_use("T", input={}))])
        self.assertFalse(res.passed)
        self.assertIn("jsonschema package not installed", res.evidence)

    def test_never_called_passes_with_all_and_fails_without(self):
        res = self.check([assistant(tool_use("Other", input={}))], all=True)
        self.assertTrue(res.passed)
        self.assertIsNone(res.failure_class)
        self.assertFalse(self.check([assistant(tool_use("Other", input={}))]).passed)

    def test_never_called_fails_when_min_asks_for_a_call(self):
        res = self.check([assistant(tool_use("Other", input={}))], all=True, min=1)
        self.assertFalse(res.passed)
        self.assertEqual(res.failure_class, "invalid_tool_args")

    @unittest.skipUnless(process_assertions._HAS_JSONSCHEMA,
                         "needs the jsonschema package")
    def test_invalid_schema_fails_the_check_not_the_run(self):
        res = self.check([assistant(tool_use("T", input={}))],
                         schema={"type": "not-a-type"})
        self.assertFalse(res.passed)
        self.assertIn("calls match schema", res.evidence)


class StagedFixturesNotGraded(unittest.TestCase):
    """Only what the subject created or changed reaches the graded outputs."""

    def test_untouched_fixture_left_out_edited_and_new_files_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            eval_dir = tmp / "evals"
            (eval_dir / "files" / "shared" / "docs").mkdir(parents=True)
            (eval_dir / "files" / "shared" / "docs" / "guide.md").write_text("staged answer\n")
            (eval_dir / "files" / "shared" / "notes.md").write_text("staged notes\n")
            sandbox = tmp / "sandbox"
            sandbox.mkdir()
            staged = stage_fixture_files(sandbox, eval_dir, 1, ["docs/guide.md"])

            # The subject edits one staged file and writes a new one.
            (sandbox / "notes.md").write_text("subject edit\n")
            (sandbox / "docs" / "answer.md").write_text("subject answer\n")

            outputs = tmp / "outputs"
            snapshot_sandbox_outputs(sandbox, outputs, staged)
            got = sorted(p.relative_to(outputs).as_posix()
                         for p in outputs.rglob("*") if p.is_file())
        self.assertEqual(got, ["docs/answer.md", "notes.md"])

    def test_no_fixtures_copies_everything_but_dot_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sandbox = tmp / "sandbox"
            (sandbox / ".claude" / "skills").mkdir(parents=True)
            (sandbox / "out.md").write_text("x\n")
            (sandbox / "empty-dir").mkdir()
            outputs = tmp / "outputs"
            snapshot_sandbox_outputs(sandbox, outputs, {})
            self.assertTrue((outputs / "out.md").is_file())
            self.assertTrue((outputs / "empty-dir").is_dir())
            self.assertFalse((outputs / ".claude").exists())


class NothingToCheckIsNotAPass(unittest.TestCase):
    """A validator with no files of its kind reports skipped, never passed.
    The tool is stubbed as present and exiting 0, as terraform fmt and
    validate do in a directory with no .tf files."""

    def run_validator(self, fn, validator, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in files:
                (root / name).write_text("x\n")
            with mock.patch.object(artifact_validation.shutil, "which",
                                   return_value="/usr/bin/tool"), \
                    mock.patch.object(artifact_validation, "_run_command",
                                      return_value=(0, "", "")) as run:
                result = fn(root, validator)
            return result, run.call_count

    def test_terraform_fmt_with_no_tf_files(self):
        result, calls = self.run_validator(
            artifact_validation._validator_terraform_fmt,
            {"type": "terraform-fmt"}, ["README.md"])
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, 0)

    def test_terraform_validate_with_no_tf_files(self):
        result, calls = self.run_validator(
            artifact_validation._validator_terraform_validate,
            {"type": "terraform-validate"}, ["README.md"])
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, 0)

    def test_checkov_terraform_with_no_tf_files(self):
        result, calls = self.run_validator(
            artifact_validation._validator_checkov,
            {"type": "checkov"}, ["README.md"])
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, 0)

    def test_terraform_fmt_with_a_tf_file_still_runs(self):
        result, calls = self.run_validator(
            artifact_validation._validator_terraform_fmt,
            {"type": "terraform-fmt"}, ["main.tf"])
        self.assertEqual(result.status, "passed")
        self.assertEqual(calls, 1)

    def test_layer_with_every_check_skipped_scores_zero(self):
        skipped = artifact_validation.ValidatorResult(
            validator={"type": "terraform-fmt"}, status="skipped",
            detail="No .tf files found", exit_code=None, duration_ms=0)
        results = artifact_validation.ArtifactValidationResults(
            artifact_root=".", structural_results=[], validator_results=[skipped])
        self.assertEqual(results.overall_pass_rate, 0.0)

    def test_printed_total_rate_with_every_check_skipped(self):
        skipped = artifact_validation.ValidatorResult(
            validator={"type": "terraform-fmt"}, status="skipped",
            detail="No .tf files found", exit_code=None, duration_ms=0)
        results = artifact_validation.ArtifactValidationResults(
            artifact_root=".", structural_results=[], validator_results=[skipped])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sk").mkdir()
            (root / "sk" / "evals.json").write_text(json.dumps({"evals": [
                {"id": 1, "artifact_assertions": {"validators": [{"type": "terraform-fmt"}]}}]}))
            run_dir = root / "sk" / "workspace" / "latest" / "eval-1" / "with_skill" / "run-1"
            (run_dir / "outputs").mkdir(parents=True)
            (run_dir.parent.parent / "eval_metadata.json").write_text(json.dumps({"eval_id": 1}))
            argv = ["run_artifact_validation.py", "--skill", "sk",
                    "--workspace", str(root / "sk" / "workspace" / "latest")]
            err = io.StringIO()
            with mock.patch.object(run_artifact_validation, "EVALS_ROOT", root), \
                    mock.patch.object(run_artifact_validation, "validate_run",
                                      return_value=results), \
                    mock.patch.object(sys, "argv", argv), \
                    contextlib.redirect_stderr(err):
                rc = run_artifact_validation.main()
        # The rate reads 0%; the verdict and the exit code are unchanged.
        self.assertIn("TOTAL: 0/0 (0%) PASS", err.getvalue())
        self.assertEqual(rc, 0)


# A fake `aws` for the credential tests: it records each call (argv and the
# env names it was given) to $FAKE_AWS_LOG and answers by $FAKE_AWS_MODE.
FAKE_AWS = r"""#!PYTHON
import datetime, json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_AWS_LOG"], "a") as f:
    f.write(json.dumps({"args": args, "env": {k: v for k, v in os.environ.items()
                                              if k.startswith("AWS_")}}) + "\n")
mode = os.environ.get("FAKE_AWS_MODE", "ok")
with open(os.environ["FAKE_AWS_LOG"]) as f:
    assumes = sum('"assume-role"' in line for line in f) - (args[:2] == ["sts", "assume-role"])
if args[:2] == ["sts", "assume-role"] and (
        mode == "bad_utf8" or (mode == "bad_utf8_refresh" and assumes >= 1)):
    sys.stdout.buffer.write(b"\xff\xfe not utf-8\n")
    sys.exit(0)
if args[:2] == ["sts", "assume-role"]:
    if mode == "signin_fail":
        sys.stderr.write("Error when retrieving credentials from custom-process: "
                         "the sign-in has expired\n")
        sys.exit(255)
    if mode == "assume_silent_fail":
        sys.exit(3)
    exp = (datetime.datetime.now(datetime.timezone.utc)
           + datetime.timedelta(seconds=int(os.environ.get("FAKE_AWS_TTL", "3600"))))
    print(json.dumps({"Credentials": {
        "AccessKeyId": "ASIAROLEKEY", "SecretAccessKey": "role-secret",
        "SessionToken": "role-token", "Expiration": exp.strftime("%Y-%m-%dT%H:%M:%SZ")}}))
elif args[:2] == ["sts", "get-caller-identity"]:
    if mode == "gci_silent_fail":
        sys.exit(4)
    account = "999999999999" if mode == "wrong_account" else "123456789012"
    role = "Admin" if mode == "wrong_role" else "apex-eval-bedrock-invoke"
    print(json.dumps({"Account": account,
                      "Arn": "arn:aws:sts::%s:assumed-role/%s/s" % (account, role)}))
else:
    sys.exit(97)
""".replace("#!PYTHON", "#!" + sys.executable)

ACCOUNT = "123456789012"  # an account id AWS docs use in examples
ROLE_KEYS = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
             "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_EC2_METADATA_DISABLED"}


class EvalRoleCredentials(unittest.TestCase):
    """The subject's AWS access is the eval-role session only."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-cred-test-"))
        self.home = self.tmp / "home"
        (self.home / ".aws").mkdir(parents=True)
        (self.home / ".aws" / "credentials").write_text("[default]\nhost-key\n")
        self.cfg = self.home / ".apex-eval"
        self.cfg.mkdir()
        (self.cfg / "aws-config").write_text(
            "[profile apex-eval-admin]\ncredential_process = sign-in-helper print\n"
            "region = us-west-2\n")
        (self.cfg / "expected-account").write_text(ACCOUNT + "\n")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "aws").write_text(FAKE_AWS)
        (bin_dir / "aws").chmod(0o755)
        self.claude_log = self.tmp / "claude.log"
        (bin_dir / "claude").write_text(
            f"#!/bin/sh\necho \"$@\" >> {self.claude_log}\nexit 97\n")
        (bin_dir / "claude").chmod(0o755)
        self.log = self.tmp / "aws.log"
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "FAKE_AWS_LOG": str(self.log),
            "AWS_ACCESS_KEY_ID": "AKIAHOSTKEY",
            "AWS_SECRET_ACCESS_KEY": "host-secret",
            "AWS_PROFILE": "default",
            "AWS_BEARER_TOKEN_BEDROCK": "host-bedrock-key",
            "CLAUDE_CODE_USE_BEDROCK": "1",
        })
        self.env.start()
        run_triggering._eval_credentials = None

    def tearDown(self):
        run_triggering._eval_credentials = None
        self.env.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_clean_home_has_no_host_aws_link(self):
        skill = self.tmp / "skill"
        skill.mkdir()
        for ctx in (run_triggering.stage_skill_sandbox("s", skill),
                    run_triggering.stage_empty_sandbox()):
            with ctx as (_sandbox, home):
                self.assertFalse(os.path.lexists(home / ".aws"))
                self.assertEqual(list(home.iterdir()), [])

    def test_parent_aws_variables_never_reach_the_subject(self):
        role = {"AWS_ACCESS_KEY_ID": "ASIAROLEKEY", "AWS_SECRET_ACCESS_KEY": "role-secret",
                "AWS_SESSION_TOKEN": "role-token", "AWS_REGION": "us-west-2"}
        env = run_triggering.build_subprocess_env(
            self.tmp, extra={"KUBECONFIG": "/k"}, aws_env=role)
        self.assertEqual({k: v for k, v in env.items() if k.startswith("AWS_")}, role)
        self.assertEqual(env["KUBECONFIG"], "/k")
        self.assertEqual(env["HOME"], str(self.tmp))

    def test_aws_variables_in_extra_are_refused(self):
        with self.assertRaises(ValueError):
            run_triggering.build_subprocess_env(
                self.tmp, extra={"AWS_ACCESS_KEY_ID": "x"}, aws_env={})

    def test_session_is_the_eval_role_and_checked(self):
        creds = run_triggering.mint_eval_role_credentials(timeout=600)
        self.assertEqual(set(creds.env), ROLE_KEYS)
        self.assertEqual(creds.env["AWS_ACCESS_KEY_ID"], "ASIAROLEKEY")
        self.assertEqual(creds.env["AWS_REGION"], "us-west-2")
        self.assertNotIn("role-secret", repr(creds))
        assume, ident = self.calls()
        self.assertEqual(assume["args"][:2], ["sts", "assume-role"])
        args = assume["args"]
        self.assertEqual(args[args.index("--profile") + 1], "apex-eval-admin")
        self.assertEqual(args[args.index("--role-arn") + 1],
                         f"arn:aws:iam::{ACCOUNT}:role/apex-eval-bedrock-invoke")
        self.assertLessEqual(int(args[args.index("--duration-seconds") + 1]), 3600)
        self.assertEqual(assume["env"], {
            "AWS_CONFIG_FILE": str(self.cfg / "aws-config"),
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AWS_EC2_METADATA_DISABLED": "true"})
        self.assertEqual(ident["args"][:2], ["sts", "get-caller-identity"])
        self.assertEqual(ident["env"]["AWS_ACCESS_KEY_ID"], "ASIAROLEKEY")
        self.assertEqual(ident["env"]["AWS_CONFIG_FILE"], os.devnull)

    def test_wrong_account_is_refused(self):
        os.environ["FAKE_AWS_MODE"] = "wrong_account"
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "expected-account"):
            run_triggering.mint_eval_role_credentials()

    def test_wrong_role_is_refused(self):
        os.environ["FAKE_AWS_MODE"] = "wrong_role"
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "refusing"):
            run_triggering.mint_eval_role_credentials()

    def test_missing_expected_account_is_refused_before_any_aws_call(self):
        (self.cfg / "expected-account").unlink()
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "expected-account"):
            run_triggering.mint_eval_role_credentials()
        self.assertEqual(self.calls(), [])

    def test_sign_in_failure_says_sign_in_again(self):
        os.environ["FAKE_AWS_MODE"] = "signin_fail"
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "sign in again"):
            run_triggering.mint_eval_role_credentials()
        self.assertEqual(len(self.calls()), 1)

    def test_aws_failure_with_no_stderr_names_the_exit_code(self):
        for mode, code in (("assume_silent_fail", 3), ("gci_silent_fail", 4)):
            with self.subTest(mode=mode):
                os.environ["FAKE_AWS_MODE"] = mode
                with self.assertRaisesRegex(run_triggering.EvalCredentialError,
                                            rf"aws exited {code}\)?: no error text"):
                    run_triggering.mint_eval_role_credentials()

    def test_config_file_refusals_point_at_the_setup_section(self):
        cases = {
            "expected-account": ("expected-account", "not-an-id\n"),
            "expected-account missing": ("expected-account", None),
            "aws-config no section": ("aws-config", "[default]\nregion = us-west-2\n"),
            "aws-config no region": ("aws-config", "[profile apex-eval-admin]\n"),
            "aws-config unparsable": ("aws-config", "region = us-west-2\n"),
            "aws-config missing": ("aws-config", None),
        }
        for name, (fname, text) in cases.items():
            with self.subTest(name):
                saved = {f: (self.cfg / f).read_text()
                         for f in ("expected-account", "aws-config")}
                try:
                    if text is None:
                        (self.cfg / fname).unlink()
                    else:
                        (self.cfg / fname).write_text(text)
                    with self.assertRaisesRegex(run_triggering.EvalCredentialError,
                                                r"Eval-role setup \(`~/\.apex-eval`\)"):
                        run_triggering.mint_eval_role_credentials()
                finally:
                    for f, t in saved.items():
                        (self.cfg / f).write_text(t)
        self.assertEqual(self.calls(), [])

    def test_no_session_means_no_subject_env(self):
        with self.assertRaises(run_triggering.EvalCredentialError):
            run_triggering.eval_aws_env(600)

    def test_session_refreshed_before_it_would_expire(self):
        os.environ["FAKE_AWS_TTL"] = "300"
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "too soon"):
            run_triggering.mint_eval_role_credentials(timeout=600)
        run_triggering.set_eval_credentials(run_triggering.mint_eval_role_credentials())
        os.environ["FAKE_AWS_TTL"] = "3600"
        before = len(self.calls())
        env = run_triggering.eval_aws_env(600)
        self.assertEqual(set(env), ROLE_KEYS)
        self.assertEqual(len(self.calls()), before + 2)

    def runner_argvs(self, should_trigger=True):
        repo = Path(MISC_DIR).parent
        eval_set = self.tmp / "triggering.json"
        eval_set.write_text(json.dumps([{"query": "q", "should_trigger": should_trigger}]))
        return [
            (run_task_evals, ["run_task_evals.py", "--skill", "eks-recon"]),
            (run_triggering, ["run_triggering.py", "--eval-set", str(eval_set),
                              "--skill-path", str(repo / "skills" / "eks-recon")]),
        ]

    def test_runners_refuse_to_start_without_a_session(self):
        os.environ["FAKE_AWS_MODE"] = "signin_fail"
        for module, argv in self.runner_argvs():
            err = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(err):
                self.assertEqual(module.main(), 2)
            self.assertIn("sign in again", err.getvalue())
        self.assertFalse(self.claude_log.exists())

    def test_runners_refuse_to_start_without_bedrock(self):
        for value in (None, "0", "true"):
            if value is None:
                os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
            else:
                os.environ["CLAUDE_CODE_USE_BEDROCK"] = value
            for module, argv in self.runner_argvs():
                err = io.StringIO()
                with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(err):
                    self.assertEqual(module.main(), 2)
                self.assertIn("CLAUDE_CODE_USE_BEDROCK=1", err.getvalue())
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.claude_log.exists())

    def test_model_routing_variables_never_reach_the_subject(self):
        dropped = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                   "ANTHROPIC_BEDROCK_BASE_URL", "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                   "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, {k: "host-value" for k in dropped}):
            env = run_triggering.build_subprocess_env(self.tmp, aws_env={})
        self.assertEqual(dropped & set(env), set())
        self.assertEqual(env["CLAUDE_CODE_USE_BEDROCK"], "1")

    def test_mid_run_credential_failure_stops_the_triggering_run(self):
        from concurrent.futures import ThreadPoolExecutor
        (module, argv), = [a for a in self.runner_argvs(should_trigger=False)
                           if a[0] is run_triggering]
        out, err = io.StringIO(), io.StringIO()
        fail = run_triggering.EvalCredentialError("refresh failed")
        with mock.patch.object(sys, "argv", argv + ["--runs-per-query", "2"]), \
                mock.patch.object(run_triggering, "ProcessPoolExecutor", ThreadPoolExecutor), \
                mock.patch.object(run_triggering, "run_single_query", side_effect=fail), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(module.main(), 2)
        self.assertIn("refresh failed", err.getvalue())
        self.assertNotIn("passed", out.getvalue())

    def test_each_turn_gets_a_fresh_env(self):
        ask = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "AskUserQuestion",
             "input": {"questions": [{"question": "which region?"}]}}]}})
        cmd_base = [sys.executable, "-c", f"print({ask!r})"]
        calls = []

        def env_for_turn():
            calls.append(1)
            return dict(os.environ)

        config = elicitation.ElicitationConfig.from_dict({
            "strategy": "canned-multiturn", "max_turns": 3,
            "turns": [{"question_match": "region", "answer": "us-west-2"}]})
        events, timed_out, _ = elicitation.run_multiturn_subject(
            initial_prompt="p", elicitation=config, cmd_base=cmd_base, cwd=str(self.tmp),
            env_for_turn=env_for_turn, timeout_per_turn=30)
        self.assertFalse(timed_out)
        self.assertEqual(len(events), 3)
        self.assertEqual(len(calls), 3)

    def test_other_provider_switches_are_refused_at_start(self):
        os.environ["CLAUDE_CODE_USE_VERTEX"] = "1"
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "CLAUDE_CODE_USE_VERTEX"):
            run_triggering.mint_eval_role_credentials()
        self.assertEqual(self.calls(), [])

    def test_non_utf8_aws_output_is_a_refusal(self):
        os.environ["FAKE_AWS_MODE"] = "bad_utf8"
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "not UTF-8"):
            run_triggering.mint_eval_role_credentials()
        self.log.unlink()
        os.environ["FAKE_AWS_MODE"] = "bad_utf8_refresh"
        os.environ["FAKE_AWS_TTL"] = "300"
        run_triggering.set_eval_credentials(run_triggering.mint_eval_role_credentials())
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "not UTF-8"):
            run_triggering.eval_aws_env(600)

    def test_timeout_at_the_cap_is_refused_at_start_naming_its_source(self):
        (_, argv), = [a for a in self.runner_argvs() if a[0] is run_triggering]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv + ["--timeout", "3480"]), \
                contextlib.redirect_stderr(err):
            self.assertEqual(run_triggering.main(), 2)
        self.assertIn("--timeout is 3480s", err.getvalue())
        self.assertEqual(self.calls(), [])
        os.environ["FAKE_AWS_TTL"] = "3610"
        run_triggering.mint_eval_role_credentials(timeout=3479, source="--timeout")
        self.assertEqual(len(self.calls()), 2)

    def test_skilleval_timeout_counts_in_the_task_runner_start_check(self):
        import types
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_task_evals.py", "--skill", "eks-recon"]), \
                mock.patch.object(run_task_evals, "load_skilleval_config",
                                  return_value=types.SimpleNamespace(timeout=3500)), \
                contextlib.redirect_stderr(err):
            self.assertEqual(run_task_evals.main(), 2)
        self.assertIn("eks-recon/.skilleval.yaml is 3500s", err.getvalue())
        self.assertEqual(self.calls(), [])

    def test_run_subject_gives_each_turn_the_eval_role_env(self):
        claude_log = self.tmp / "claude-env.log"
        (self.tmp / "bin" / "claude").write_text(
            "#!" + sys.executable + "\nimport json, os\n"
            "open(os.environ['FAKE_CLAUDE_LOG'], 'a').write("
            "os.environ.get('AWS_ACCESS_KEY_ID', '-') + '\\n')\n"
            "print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'tool_use', "
            "'name': 'AskUserQuestion', 'input': {'questions': [{'question': 'which region?'}]}}]}}))\n")
        os.environ["FAKE_CLAUDE_LOG"] = str(claude_log)
        role = {"AWS_ACCESS_KEY_ID": "ASIAROLEKEY"}
        multi = elicitation.ElicitationConfig.from_dict({
            "strategy": "canned-multiturn", "max_turns": 3,
            "turns": [{"question_match": "region", "answer": "us-west-2"}]})
        for config, turns in ((multi, 3), (None, 1)):
            claude_log.unlink(missing_ok=True)
            with mock.patch.object(run_task_evals, "eval_aws_env", return_value=role) as aws_env:
                run_task_evals.run_subject(
                    prompt="p", skill_name="s", repo_skill_dir=self.tmp, with_skill=False,
                    model="m", timeout=30, run_dir=self.tmp / f"run-{turns}", extra_env=None,
                    elicitation=config)
            self.assertEqual(aws_env.call_count, turns)
            self.assertEqual(claude_log.read_text().split(), ["ASIAROLEKEY"] * turns)

    def test_missing_aws_cli_and_config_are_refusals(self):
        os.environ["PATH"] = str(self.tmp / "no-such-dir")
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "cannot run aws"):
            run_triggering.mint_eval_role_credentials()
        (self.cfg / "aws-config").unlink()
        with self.assertRaisesRegex(run_triggering.EvalCredentialError, "cannot read"):
            run_triggering.mint_eval_role_credentials()

    def test_runner_scripts_hold_no_account_id(self):
        for name in ("run_triggering.py", "run_task_evals.py"):
            text = Path(SCRIPTS_DIR, name).read_text()
            self.assertEqual(re.findall(r"(?<!\d)\d{12}(?!\d)", text), [], name)


# ---------- triggering runner: invalid runs, adapters, class cases ----


def j(obj):
    return json.dumps(obj)


SKILL = "eks-recon"

# claude -p --output-format stream-json --verbose (shape as parsed by _handle_line)
CLAUDE_INIT = j({"type": "system", "subtype": "init", "skills": ["update-config", SKILL]})
CLAUDE_SKILL_USE = j({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Skill", "input": {"skill": SKILL}}]}})
CLAUDE_TEXT = j({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}})
CLAUDE_RESULT = j({"type": "result", "subtype": "success", "is_error": False,
                   "usage": {"input_tokens": 10, "output_tokens": 5,
                             "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0}})

# kiro-cli chat --output-format stream-json (record names from kiro-cli 3.4.0)
KIRO_START = j({"type": "runStarted", "data": {"sessionId": "s1", "acpProtocolVersion": 1}})
KIRO_TEXT = j({"type": "sessionUpdate", "data": {"sessionId": "s1", "update": {
    "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "ok"}}}})
KIRO_READ = j({"type": "sessionUpdate", "data": {"sessionId": "s1", "update": {
    "sessionUpdate": "tool_call", "toolCallId": "t1", "title": "Reading file", "kind": "read",
    "rawInput": {"operations": [{"mode": "Line",
                                 "path": f"/tmp/h/.kiro/skills/{SKILL}/SKILL.md"}]}}}})
KIRO_OTHER_READ = j({"type": "sessionUpdate", "data": {"sessionId": "s1", "update": {
    "sessionUpdate": "tool_call", "toolCallId": "t2", "kind": "read",
    "rawInput": {"operations": [{"path": "/tmp/notes.md"}]}}}})
KIRO_DONE = j({"type": "runFinished", "data": {"sessionId": "s1", "finalText": "ok",
                                                "usage": {"inputTokens": 40, "outputTokens": 2}}})
KIRO_ERROR = j({"type": "runError", "data": {"sessionId": "s1", "stage": "turn",
                                              "message": "x", "errorType": "y"}})

# codex exec --json (openai/codex codex-rs/exec/src/exec_events.rs)
CODEX_START = j({"type": "thread.started", "thread_id": "0199a213-81c0-7800-8aa1-bbab2a035a53"})
CODEX_TURN = j({"type": "turn.started"})
CODEX_READ = j({"type": "item.started", "item": {
    "id": "item_1", "type": "command_execution",
    "command": f"bash -lc 'cat /tmp/h/.agents/skills/{SKILL}/SKILL.md'", "status": "in_progress"}})
CODEX_LS = j({"type": "item.started", "item": {
    "id": "item_1", "type": "command_execution", "command": "bash -lc ls", "status": "in_progress"}})
CODEX_MSG = j({"type": "item.completed", "item": {
    "id": "item_3", "type": "agent_message", "text": "Repo contains docs."}})
CODEX_DONE = j({"type": "turn.completed", "usage": {
    "input_tokens": 24763, "cached_input_tokens": 24448, "output_tokens": 122,
    "reasoning_output_tokens": 0}})
CODEX_FAILED = j({"type": "turn.failed", "error": {"message": "x"}})


def claude_parse(lines, code=0, sleep=0.0, timeout=30):
    return run_triggering.parse_stream_for_trigger(printer(lines, code, sleep), SKILL, timeout)


def kiro_parse(lines, code=0, sleep=0.0, timeout=30):
    return run_triggering.parse_kiro_stream(printer(lines, code, sleep), SKILL,
                                            Path("/nowhere/eks-recon"), timeout)


def codex_parse(lines, code=0, sleep=0.0, timeout=30):
    return run_triggering.parse_codex_stream(printer(lines, code, sleep), SKILL,
                                             Path("/nowhere/eks-recon"), timeout)


def rec(triggered=False, invalid=False, reason=None, tokens=None):
    r = run_triggering.new_run_record("claude")
    r.update(triggered=triggered and not invalid, trigger_seen=triggered, invalid=invalid,
             invalid_reason=reason, tokens=tokens)
    return r


class InvalidClaudeRuns(unittest.TestCase):
    """Invalid runs on the claude stream reader."""

    def test_broken_claude_no_init_nonzero_is_invalid(self):
        out = claude_parse([], code=1)
        self.assertTrue(out["invalid"])
        self.assertEqual(out["invalid_reason"], "no system/init event")
        self.assertFalse(out["triggered"])
        self.assertEqual(out["returncode"], 1)

    def test_broken_claude_cannot_pass_a_negative(self):
        records = [claude_parse(["not json"], code=1) for _ in range(3)]
        row = run_triggering.score_case({"query": "q", "should_trigger": False}, records, 0.5)
        self.assertFalse(row["pass"])
        self.assertEqual(row["fail_reason"], "no valid run")
        self.assertEqual((row["runs"], row["attempted_runs"], row["invalid_count"]), (0, 3, 3))

    def test_nonzero_exit_after_init_is_invalid(self):
        out = claude_parse([CLAUDE_INIT, CLAUDE_TEXT], code=1)
        self.assertEqual(out["invalid_reason"], "exited 1")

    def test_timeout_run_is_invalid(self):
        t0 = time.time()
        out = claude_parse([CLAUDE_INIT], sleep=30, timeout=1)
        self.assertLess(time.time() - t0, 15)
        self.assertTrue(out["invalid"])
        self.assertTrue(out["timed_out"])
        self.assertIn("timed out after 1s", out["invalid_reason"])

    def test_exit_zero_with_no_result_event_is_invalid(self):
        out = claude_parse([CLAUDE_INIT, CLAUDE_TEXT])
        self.assertEqual(out["invalid_reason"], "no result event")

    def test_clean_negative_run_is_valid_with_tokens(self):
        out = claude_parse([CLAUDE_INIT, CLAUDE_TEXT, CLAUDE_RESULT])
        self.assertFalse(out["invalid"])
        self.assertFalse(out["triggered"])
        self.assertEqual(out["tokens"]["total_tokens"], 115)

    def test_result_is_error_is_invalid(self):
        bad = j({"type": "result", "is_error": True})
        self.assertEqual(claude_parse([CLAUDE_INIT, bad])["invalid_reason"],
                         "result event reports is_error")

    def test_trigger_kills_and_stays_valid(self):
        out = claude_parse([CLAUDE_INIT, CLAUDE_SKILL_USE], sleep=30)
        self.assertTrue(out["triggered"])
        self.assertFalse(out["invalid"])
        self.assertLess(out["returncode"], 0)

    def test_init_invalid_run_never_reads_triggered(self):
        init = j({"type": "system", "subtype": "init", "skills": [SKILL, "leaked-plugin"]})
        out = claude_parse([init, CLAUDE_SKILL_USE], sleep=30)
        self.assertTrue(out["invalid"])
        self.assertTrue(out["trigger_seen"])
        self.assertFalse(out["triggered"])
        row = run_triggering.score_case({"query": "q", "should_trigger": True},
                                        [out, rec(), rec()], 0.5)
        self.assertEqual((row["triggers"], row["runs"]), (0, 2))
        self.assertFalse(row["pass"])

    def test_trigger_before_init_is_invalid(self):
        out = claude_parse([CLAUDE_SKILL_USE, CLAUDE_INIT], sleep=30)
        self.assertEqual(out["invalid_reason"], "no system/init event")
        self.assertFalse(out["triggered"])


class ScoringOnValidRunsOnly(unittest.TestCase):

    def test_all_invalid_fails_both_sides(self):
        bad = [rec(invalid=True, reason="no system/init event")] * 3
        for should in (True, False):
            for source in ("member", "class:apex-base"):
                row = run_triggering.score_case(
                    {"query": "q", "should_trigger": should, "source": source}, bad, 0.5)
                self.assertFalse(row["pass"], (should, source))
                self.assertEqual(row["trigger_rate"], 0.0)

    def test_invalid_runs_leave_the_rate(self):
        records = [rec(invalid=True, reason="x"), rec(invalid=True, reason="x"), rec(triggered=True)]
        row = run_triggering.score_case({"query": "q", "should_trigger": True}, records, 0.5)
        self.assertEqual((row["triggers"], row["runs"], row["trigger_rate"]), (1, 1, 1.0))
        self.assertTrue(row["pass"])
        self.assertEqual(len(row["invalid_runs"]), 2)

    def test_member_negative_with_some_invalid_runs_scores_valid_runs(self):
        records = [rec(invalid=True, reason="x"), rec(), rec()]
        row = run_triggering.score_case({"query": "q", "should_trigger": False}, records, 0.5)
        self.assertTrue(row["pass"])

    def test_shared_negative_with_an_invalid_run_fails(self):
        records = [rec(invalid=True, reason="x"), rec(), rec()]
        row = run_triggering.score_case(
            {"query": "q", "should_trigger": False, "source": "class:apex-base", "id": 9001},
            records, 0.01)
        self.assertFalse(row["pass"])
        self.assertEqual(row["fail_reason"], "shared negative with invalid runs")
        self.assertEqual(row["id"], 9001)


class KiroAdapterParsing(unittest.TestCase):

    def test_skill_md_read_is_a_trigger(self):
        out = kiro_parse([KIRO_START, KIRO_TEXT, KIRO_READ], sleep=30)
        self.assertTrue(out["triggered"])
        self.assertFalse(out["invalid"])
        self.assertEqual(out["harness"], "kiro")

    def test_other_reads_and_text_are_a_valid_negative(self):
        out = kiro_parse([KIRO_START, KIRO_TEXT, KIRO_OTHER_READ, KIRO_DONE])
        self.assertFalse(out["invalid"])
        self.assertFalse(out["triggered"])
        self.assertEqual(out["tokens"], {"input_tokens": 40, "output_tokens": 2,
                                         "cache_read_input_tokens": 0,
                                         "cache_creation_input_tokens": 0, "total_tokens": 42})

    def test_run_error_is_invalid(self):
        out = kiro_parse([KIRO_START, KIRO_TEXT, KIRO_ERROR, KIRO_DONE])
        self.assertEqual(out["invalid_reason"], "runError record")

    def test_no_session_updates_is_invalid_not_a_negative(self):
        out = kiro_parse([KIRO_START, KIRO_DONE])
        self.assertTrue(out["invalid"])
        self.assertIn("cannot show whether the skill loaded", out["invalid_reason"])

    def test_no_start_record_or_bad_exit_is_invalid(self):
        self.assertEqual(kiro_parse([KIRO_TEXT, KIRO_DONE])["invalid_reason"], "no runStarted event")
        self.assertEqual(kiro_parse([KIRO_START, KIRO_TEXT], code=3)["invalid_reason"], "exited 3")


class CodexAdapterParsing(unittest.TestCase):

    def test_skill_md_read_is_a_trigger(self):
        out = codex_parse([CODEX_START, CODEX_TURN, CODEX_READ], sleep=30)
        self.assertTrue(out["triggered"])
        self.assertFalse(out["invalid"])
        self.assertEqual(out["harness"], "codex")

    def test_other_commands_are_a_valid_negative_with_tokens(self):
        out = codex_parse([CODEX_START, CODEX_TURN, CODEX_LS, CODEX_MSG, CODEX_DONE])
        self.assertFalse(out["invalid"])
        self.assertFalse(out["triggered"])
        self.assertEqual(out["tokens"]["total_tokens"], 24763 + 122)
        self.assertEqual(out["tokens"]["cache_read_input_tokens"], 24448)

    def test_turn_failed_is_invalid(self):
        out = codex_parse([CODEX_START, CODEX_TURN, CODEX_FAILED], code=1)
        self.assertEqual(out["invalid_reason"], "turn.failed event")

    def test_no_items_is_invalid_not_a_negative(self):
        out = codex_parse([CODEX_START, CODEX_TURN, CODEX_DONE])
        self.assertIn("cannot show whether the skill loaded", out["invalid_reason"])

    def test_nonzero_with_no_start_is_invalid(self):
        self.assertEqual(codex_parse([], code=1)["invalid_reason"], "no thread.started event")


class AdaptersGetTheEvalRoleEnv(unittest.TestCase):
    """Every adapter's subprocess gets the eval-role session, a clean HOME
    and no host AWS key."""

    ROLE = {"AWS_ACCESS_KEY_ID": "ASIAROLEKEY", "AWS_SECRET_ACCESS_KEY": "role-secret",
            "AWS_SESSION_TOKEN": "role-token", "AWS_REGION": "us-west-2",
            "AWS_DEFAULT_REGION": "us-west-2", "AWS_EC2_METADATA_DISABLED": "true"}
    SAMPLES = {
        "claude": [CLAUDE_INIT, CLAUDE_TEXT, CLAUDE_RESULT],
        "kiro": [KIRO_START, KIRO_TEXT, KIRO_DONE],
        "codex": [CODEX_START, CODEX_TURN, CODEX_MSG, CODEX_DONE],
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-adapter-test-"))
        self.skill = self.tmp / SKILL
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text("---\nname: eks-recon\n---\n")
        self.kube = self.tmp / "shared-kubeconfig"
        self.kube.write_text("apiVersion: v1\nkind: Config\n")
        self.env = mock.patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "AKIAHOSTKEY", "AWS_SECRET_ACCESS_KEY": "host-secret",
            "AWS_PROFILE": "default", "OPENAI_API_KEY": "host-openai", "CODEX_HOME": "/host/codex",
            "KUBECONFIG": str(self.kube), "CLAUDE_CODE_USE_BEDROCK": "1"})
        self.env.start()
        run_triggering._eval_credentials = None
        run_triggering.set_eval_credentials(
            run_triggering.EvalCredentials(env=dict(self.ROLE), expires_at=time.time() + 3000))

    def tearDown(self):
        run_triggering._eval_credentials = None
        self.env.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_harness(self, harness):
        seen = {}

        def fake_popen(cmd, **kw):
            env, home = kw["env"], Path(kw["env"]["HOME"])
            seen.update(cmd=cmd, env=dict(env), cwd=kw.get("cwd"), stdin=kw.get("stdin"))
            seen["links"] = {p: os.path.islink(home / p) for p in
                             (f".kiro/skills/{SKILL}", f".agents/skills/{SKILL}")}
            kc = env.get("KUBECONFIG")
            seen["kube_text"] = Path(kc).read_text() if kc else None
            if kc:
                Path(kc).write_text("rewritten by the run\n")
            return printer(self.SAMPLES[harness])

        with mock.patch.object(run_triggering.subprocess, "Popen", side_effect=fake_popen):
            out = run_triggering.run_single_query("q", SKILL, self.skill, "m1", 30, harness=harness)
        return out, seen

    def test_role_env_reaches_every_adapter(self):
        for harness in run_triggering.HARNESSES:
            with self.subTest(harness=harness):
                out, seen = self.run_harness(harness)
                self.assertFalse(out["invalid"], out["invalid_reason"])
                env = seen["env"]
                self.assertEqual({k: v for k, v in env.items() if k.startswith("AWS_")}, self.ROLE)
                self.assertTrue(env["HOME"].startswith(tempfile.gettempdir()))
                self.assertNotEqual(env["HOME"], os.environ.get("HOME"))
                self.assertEqual(seen["cmd"][0], {"claude": "claude", "kiro": "kiro-cli",
                                                  "codex": "codex"}[harness])
                self.assertIn("m1", seen["cmd"])

    def test_harness_skill_staging_and_codex_routing(self):
        _out, seen = self.run_harness("kiro")
        self.assertTrue(seen["links"][f".kiro/skills/{SKILL}"])
        self.assertIn("stream-json", seen["cmd"])
        self.assertIn("--no-interactive", seen["cmd"])
        _out, seen = self.run_harness("codex")
        self.assertTrue(seen["links"][f".agents/skills/{SKILL}"])
        self.assertIn("--json", seen["cmd"])
        self.assertIn('model_provider="amazon-bedrock-runtime"', seen["cmd"])
        self.assertIn('model_providers.amazon-bedrock-runtime.aws.region="us-west-2"', seen["cmd"])
        self.assertNotIn("OPENAI_API_KEY", seen["env"])
        self.assertTrue(seen["env"]["CODEX_HOME"].startswith(seen["env"]["HOME"]))
        self.assertEqual(seen["stdin"], subprocess.DEVNULL)


class ClassSharedTriggerEvals(unittest.TestCase):
    """A class's shared cases merged with each target's own."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-class-test-"))
        self.classes = self.tmp / "classes"
        for name, parents in (("apex-base", "[]"), ("service", "[apex-base]")):
            d = self.classes / name
            d.mkdir(parents=True)
            (d / "class.yaml").write_text(f"name: {name}\nparents: {parents}\n")
        trig = self.classes / "apex-base" / "evals" / "trigger"
        trig.mkdir(parents=True)
        (trig / "triggering.json").write_text(json.dumps([
            {"id": 9001, "query": "shared negative", "should_trigger": False}]))
        self.member = self.tmp / "triggering.json"
        self.member.write_text(json.dumps([
            {"query": "own positive", "should_trigger": True},
            {"query": "shared negative", "should_trigger": False}]))
        self.copy = run_triggering.REPO_ROOT / "devops-agent" / SKILL
        self.targets = {"apex-base": {"devops-agent/eks-recon": True},
                        "service": {"devops-agent/eks-recon": False}}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, classes, member=True, targets=None):
        return run_triggering.build_eval_set(self.member if member else None, classes, self.copy,
                                             self.classes, targets or self.targets)

    def test_shared_cases_merge_after_the_members_own(self):
        cases, meta = self.build(["apex-base"])
        self.assertEqual([(c["query"], c["source"]) for c in cases], [
            ("own positive", "member"), ("shared negative", "member"),
            ("shared negative", "class:apex-base")])
        self.assertEqual(meta, {"run_key": "devops-agent-eks-recon", "target": "devops-agent/eks-recon",
                                "classes": ["apex-base"], "blocking": True})

    def test_parents_cases_come_through_a_child_class(self):
        cases, meta = self.build(["service"], member=False)
        self.assertEqual(meta["classes"], ["apex-base", "service"])
        self.assertEqual([c["id"] for c in cases], [9001])
        self.assertFalse(meta["blocking"])

    def test_non_target_and_missing_list_are_refused(self):
        with self.assertRaisesRegex(run_triggering.EvalSetError, "not a target"):
            self.build(["apex-base"], targets={"apex-base": {"skills/other": True}})
        with self.assertRaisesRegex(run_triggering.EvalSetError, "no target list"):
            self.build(["router"])

    def test_repeated_ids_are_refused(self):
        self.member.write_text(json.dumps([{"id": 9001, "query": "q", "should_trigger": True}]))
        with self.assertRaisesRegex(run_triggering.EvalSetError, r"repeat.*9001"):
            self.build(["apex-base"])

    def test_chain_with_no_shared_file_is_refused(self):
        (self.classes / "apex-base" / "evals" / "trigger" / "triggering.json").unlink()
        with self.assertRaisesRegex(run_triggering.EvalSetError, "no shared trigger evals"):
            self.build(["apex-base"])

    def test_same_query_twice_scores_as_two_rows(self):
        from concurrent.futures import ThreadPoolExecutor
        cases, _ = self.build(["apex-base"])
        calls = []

        def fake(query, *a, **kw):
            calls.append(kw["harness"])
            return rec(tokens={"total_tokens": 10})

        with mock.patch.object(run_triggering, "ProcessPoolExecutor", ThreadPoolExecutor), \
                mock.patch.object(run_triggering, "run_single_query", side_effect=fake):
            out = run_triggering.run_eval(cases, SKILL, "", self.copy, 2, 30, 3, 0.5, None,
                                          creds=None, harness="codex")
        self.assertEqual(len(out["results"]), 3)
        self.assertEqual([r["attempted_runs"] for r in out["results"]], [3, 3, 3])
        self.assertEqual(set(calls), {"codex"})
        self.assertEqual(out["summary"]["tokens_per_run"], 10)
        self.assertEqual(out["harness"], "codex")

    def test_real_target_list_names_existing_skills(self):
        listed = run_triggering.CLASS_TARGETS["apex-base"]
        self.assertEqual(len(listed), 32)
        self.assertEqual(sorted(t for t, b in listed.items() if b), [
            "devops-agent/eks-cost-intelligence", "devops-agent/eks-recon",
            "devops-agent/eks-security"])
        for t in listed:
            self.assertTrue((run_triggering.REPO_ROOT / t / "SKILL.md").is_file(), t)
        self.assertNotIn("skills/dotnet-aws-ecs", listed)
        keys = [run_triggering.run_key_for(run_triggering.REPO_ROOT / t) for t in listed]
        self.assertEqual(len(keys), len(set(keys)))


class TriggeringCli(unittest.TestCase):

    def main(self, argv, **patches):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["run_triggering.py"] + argv), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_triggering.main()
        return code, out.getvalue(), err.getvalue()

    def test_three_runs_by_default_and_harness_passed(self):
        skill = str(run_triggering.REPO_ROOT / "skills" / SKILL)
        eval_set = str(run_triggering.REPO_ROOT / "misc" / "evals" / SKILL / "triggering.json")
        seen = {}

        def fake_run_eval(**kw):
            seen.update(kw)
            return {"results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}

        with mock.patch.object(run_triggering, "mint_eval_role_credentials", return_value=None), \
                mock.patch.object(run_triggering, "run_eval", side_effect=fake_run_eval):
            code, out, _ = self.main(["--eval-set", eval_set, "--skill-path", skill,
                                      "--harness", "codex"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["runs_per_query"], 3)
        self.assertEqual(seen["harness"], "codex")
        self.assertEqual(json.loads(out)["run_key"], SKILL)

    def test_kiro_without_its_key_is_refused_before_any_call(self):
        skill = str(run_triggering.REPO_ROOT / "skills" / SKILL)
        eval_set = str(run_triggering.REPO_ROOT / "misc" / "evals" / SKILL / "triggering.json")
        env = {k: v for k, v in os.environ.items() if k != "KIRO_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(run_triggering, "mint_eval_role_credentials") as mint:
            code, _, err = self.main(["--eval-set", eval_set, "--skill-path", skill,
                                      "--harness", "kiro"])
        self.assertEqual(code, 2)
        self.assertIn("KIRO_API_KEY", err)
        mint.assert_not_called()

    def test_unknown_harness_is_a_usage_error(self):
        with self.assertRaises(SystemExit):
            self.main(["--skill-path", "x", "--harness", "gemini"])


# ---------- task runner: arms, Pass@k, adapters, class cases ---------


ROLE = {"AWS_ACCESS_KEY_ID": "ASIAROLEKEY", "AWS_SECRET_ACCESS_KEY": "role-secret",
        "AWS_SESSION_TOKEN": "role-token", "AWS_REGION": "us-west-2"}
INIT = {"type": "system", "subtype": "init", "skills": []}
RESULT = {"type": "result", "subtype": "success", "duration_ms": 5,
          "usage": {"input_tokens": 10, "output_tokens": 4}}


def fake_exe(bin_dir, name, lines, exit_code=0, extra=""):
    """A fake harness binary that prints `lines` and exits `exit_code`."""
    path = Path(bin_dir) / name
    path.write_text(
        "#!" + sys.executable + "\nimport json, os, sys\n" + extra
        + "for l in %r:\n    print(l)\nsys.exit(%d)\n" % ([json.dumps(x) if not isinstance(x, str) else x
                                                         for x in lines], exit_code))
    path.chmod(0o755)
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-tests-R-"))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.env = mock.patch.dict(os.environ, {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"})
        self.env.start()
        self.aws = mock.patch.object(run_task_evals, "eval_aws_env", return_value=dict(ROLE))
        self.aws_env = self.aws.start()

    def tearDown(self):
        self.aws.stop()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def subject(self, harness="claude", **kw):
        args = dict(prompt="p", skill_name="s", repo_skill_dir=self.tmp, with_skill=False,
                    model="m", timeout=30, run_dir=self.tmp / "run", extra_env=None)
        args.update(kw)
        if harness != "claude":
            args["harness"] = harness
        return run_task_evals.run_subject(**args)


# ---------- invalid runs --------------------------------------------------------


class InvalidRuns(Tmp):
    """Check fixes: each test below fails on the scripts at HEAD, where
    run_subject returned ok True for these runs."""

    def test_no_events_is_invalid(self):
        fake_exe(self.bin, "claude", [], 0)
        out = self.subject()
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no events")

    def test_no_init_event_is_invalid(self):
        fake_exe(self.bin, "claude", [RESULT], 0)
        out = self.subject()
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no init event")

    def test_canned_multiturn_nonzero_exit_is_invalid(self):
        ask = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "AskUserQuestion",
               "input": {"questions": [{"question": "which region?"}]}}]}}
        fake_exe(self.bin, "claude", [INIT, ask, RESULT], 3)
        multi = elicitation.ElicitationConfig.from_dict({
            "strategy": "canned-multiturn", "max_turns": 2,
            "turns": [{"question_match": "region", "answer": "us-west-2"}]})
        out = self.subject(elicitation=multi)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "subject exited 3")

    def test_canned_multiturn_reads_every_turns_exit_code(self):
        ask = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "AskUserQuestion",
               "input": {"questions": [{"question": "which region?"}]}}]}}
        counter = self.tmp / "turns"
        # Turn 1 exits 0, turn 2 exits 5.
        fake_exe(self.bin, "claude", [INIT, ask, RESULT], 0, extra=(
            "p = %r\nn = int(open(p).read()) + 1 if os.path.exists(p) else 1\n"
            "open(p, 'w').write(str(n))\n"
            "if n == 2:\n    print(json.dumps(%r)); sys.exit(5)\n") % (str(counter), INIT))
        multi = elicitation.ElicitationConfig.from_dict({
            "strategy": "canned-multiturn", "max_turns": 2,
            "turns": [{"question_match": "region", "answer": "us-west-2"}]})
        out = self.subject(elicitation=multi)
        self.assertEqual(out["exit_codes"], [0, 5])
        self.assertEqual(out["reason"], "subject exited 5")
        self.assertIs(elicitation.subprocess, subprocess)

    def test_valid_run_is_ok(self):
        fake_exe(self.bin, "claude", [INIT, RESULT], 0)
        out = self.subject()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["exit_codes"], [0])


# ---------- links in the snapshot and in fixtures ----------------------------


class Links(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-links-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_skips_a_dangling_nested_link(self):
        """Check fix: at HEAD copytree raised shutil.Error."""
        sandbox, out = self.tmp / "sb", self.tmp / "out"
        (sandbox / "sub").mkdir(parents=True)
        (sandbox / "sub" / "kept.txt").write_text("x")
        os.symlink(self.tmp / "nowhere", sandbox / "sub" / "dangling")
        run_task_evals.snapshot_sandbox_outputs(sandbox, out)
        self.assertTrue((out / "sub" / "kept.txt").is_file())
        self.assertFalse(os.path.lexists(out / "sub" / "dangling"))

    def test_snapshot_never_copies_what_a_link_points_at(self):
        """Check fix: at HEAD a top-level link to a file and a nested link to
        a directory copied the outside content."""
        outside = self.tmp / "outside"
        (outside / "d").mkdir(parents=True)
        (outside / "secret.txt").write_text("outside")
        (outside / "d" / "f.txt").write_text("outside")
        sandbox, out = self.tmp / "sb", self.tmp / "out"
        (sandbox / "sub").mkdir(parents=True)
        os.symlink(outside / "secret.txt", sandbox / "top-link")
        os.symlink(outside / "d", sandbox / "sub" / "dir-link")
        run_task_evals.snapshot_sandbox_outputs(sandbox, out)
        self.assertFalse(os.path.lexists(out / "top-link"))
        self.assertFalse(os.path.lexists(out / "sub" / "dir-link"))

    def test_fixture_in_repo_link_is_followed(self):
        """Eval 18's tracked link must still stage."""
        sandbox = self.tmp / "sb"
        sandbox.mkdir()
        run_task_evals.stage_fixture_files(
            sandbox, REPO / "misc" / "evals" / "ecs-modernize", 18, ["x"])
        staged = sandbox / ".claude" / "skills" / "terraform-skill" / "SKILL.md"
        self.assertTrue(staged.is_file())
        self.assertFalse(staged.parent.is_symlink())

    def test_fixture_link_out_of_the_repo_is_refused(self):
        """Check fix: at HEAD the outside file was copied in."""
        root = self.tmp / "evals"
        (root / "files" / "eval-1").mkdir(parents=True)
        os.symlink("/etc/hostname", root / "files" / "eval-1" / "leak")
        sandbox = self.tmp / "sb"
        sandbox.mkdir()
        with self.assertRaises(run_task_evals.FixtureLinkError):
            run_task_evals.stage_fixture_files(sandbox, root, 1, ["leak"])
        self.assertFalse(os.path.lexists(sandbox / "leak"))

    def test_dangling_fixture_link_is_refused(self):
        repo = self.tmp / "repo"
        (repo / "f").mkdir(parents=True)
        os.symlink(repo / "gone", repo / "f" / "dead")
        with self.assertRaisesRegex(run_task_evals.FixtureLinkError, "leads nowhere"):
            run_task_evals.check_fixture_links(repo / "f", repo_root=repo)

    def test_fixture_link_to_its_own_folder_or_above_is_refused(self):
        for name, link_dir in (("self", ("f",)), ("up", ("f", "sub"))):
            repo = self.tmp / name
            (repo / "f" / "sub").mkdir(parents=True)
            os.symlink(repo / "f", repo.joinpath(*link_dir) / "loop")
            with self.assertRaisesRegex(run_task_evals.FixtureLinkError, "own folder"):
                run_task_evals.check_fixture_links(repo / "f", repo_root=repo)


class RefusedFixtureIsAnInvalidRun(Tmp):
    def test_refused_fixture_runs_no_subject(self):
        root = self.tmp / "evals"
        (root / "files" / "eval-1").mkdir(parents=True)
        os.symlink("/etc/hostname", root / "files" / "eval-1" / "leak")
        log = self.tmp / "ran"
        fake_exe(self.bin, "claude", [INIT, RESULT], 0, extra="open(%r, 'w').write('x')\n" % str(log))
        out = self.subject(skill_eval_dir=root, eval_id=1, fixture_files=["leak"])
        self.assertFalse(out["ok"])
        self.assertIn("fixture staging refused", out["reason"])
        self.assertFalse(log.exists())


# ---------- per-assertion limit -------------------------------------------


class PerAssertionTimeout(unittest.TestCase):
    def test_slow_assertion_scores_failed_timeout_and_others_still_score(self):
        real = run_task_evals.evaluate

        def slow(trajectory, assertions):
            if assertions[0].get("slow"):
                time.sleep(30)
            return real(trajectory, assertions)

        traj = parse_events([INIT, {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {}}]}}, RESULT])
        defs = [{"type": "tool-called", "tool": "Read", "slow": True},
                {"type": "tool-called", "tool": "Read"}]
        with mock.patch.object(run_task_evals, "evaluate", slow):
            t0 = time.time()
            res = run_task_evals.evaluate_with_timeouts(traj, defs, timeout=1)
        self.assertLess(time.time() - t0, 10)
        self.assertEqual([r.passed for r in res.results], [False, True])
        self.assertEqual(res.results[0].evidence, "timeout")
        self.assertEqual(res.failure_classes, {"timeout": 1})
        self.assertEqual((res.passed, res.failed, res.total), (1, 1, 2))
        self.assertEqual(res.to_dict()["pass_rate"], 0.5)

    def test_result_matches_evaluate_on_fast_assertions(self):
        traj = parse_events([INIT, RESULT])
        defs = [{"type": "tool-called", "tool": "Bash"}, {"type": "no-such-type"}]
        a = run_task_evals.evaluate(traj, defs).to_dict()
        b = run_task_evals.evaluate_with_timeouts(traj, defs).to_dict()
        self.assertEqual(a, b)


# ---------- harness shapes and adapters -------------------------------------

CODEX_STREAM = [
    {"type": "thread.started", "thread_id": "0199a213-81c0-7800-8aa1-bbab2a035a53"},
    {"type": "turn.started"},
    {"type": "item.started", "item": {"id": "item_1", "type": "command_execution",
                                      "command": "bash -lc ls", "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution",
                                        "command": "bash -lc ls", "aggregated_output": "docs\n",
                                        "exit_code": 0, "status": "completed"}},
    {"type": "item.completed", "item": {"id": "item_2", "type": "mcp_tool_call", "server": "eks",
                                        "tool": "list_clusters", "arguments": {"region": "us-west-2"},
                                        "result": {"content": [{"type": "text", "text": "[]"}]},
                                        "error": None, "status": "completed"}},
    {"type": "item.completed", "item": {"id": "item_3", "type": "file_change", "status": "completed",
                                        "changes": [{"path": "main.tf", "kind": "add"},
                                                    {"path": "README.md", "kind": "update"}]}},
    {"type": "item.completed", "item": {"id": "item_4", "type": "agent_message",
                                        "text": "Repo contains docs, sdk, and examples directories."}},
    {"type": "turn.completed", "usage": {"input_tokens": 24763, "cached_input_tokens": 24448,
                                         "output_tokens": 122, "reasoning_output_tokens": 0}},
]

KIRO_RPC = [
    {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "sess_abc123def456", "update": {
        "sessionUpdate": "tool_call", "toolCallId": "call_001", "title": "Reading configuration file",
        "name": "read_file", "kind": "read", "status": "pending", "rawInput": {"path": "a.yaml"}}}},
    {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "sess_abc123def456", "update": {
        "sessionUpdate": "tool_call_update", "toolCallId": "call_001", "status": "completed",
        "content": [{"type": "content", "content": {"type": "text", "text": "Found 3 files"}}]}}},
    {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "s", "update": {
        "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Done."}}}},
]

KIRO_TYPED = [
    {"type": "runStarted", "data": {"sessionId": "s1"}},
    {"type": "sessionUpdate", "data": {"sessionUpdate": "tool_call", "toolCallId": "t1",
                                        "title": "execute_bash", "kind": "execute", "status": "pending",
                                        "rawInput": {"command": "kubectl get pods"}}},
    {"type": "sessionUpdate", "data": {"sessionUpdate": "tool_call_update", "toolCallId": "t1",
                                        "status": "failed", "rawOutput": "forbidden"}},
    {"type": "runFinished", "data": {"usage": {"inputTokens": 7, "outputTokens": 3}}},
]


class HarnessShapes(unittest.TestCase):
    def test_codex_reads_into_the_same_trajectory_form(self):
        traj = parse_events(parse_trajectory.normalize_events(CODEX_STREAM, "codex"))
        self.assertEqual(traj.tool_sequence, ["Bash", "mcp__eks__list_clusters", "Write", "Edit"])
        self.assertEqual(traj.steps[0].tool_calls[0].input, {"command": "bash -lc ls"})
        self.assertEqual(traj.steps[0].tool_calls[0].result, "docs\n")
        self.assertEqual(traj.steps[1].tool_calls[0].result, "[]")
        self.assertEqual((traj.input_tokens, traj.output_tokens, traj.cache_read_input_tokens),
                         (24763, 122, 24448))
        self.assertEqual(traj.total_tokens, 24885)
        self.assertIsNone(parse_trajectory.stream_invalid_reason(CODEX_STREAM, "codex"))

    def test_codex_failed_command_is_an_error_result(self):
        stream = [CODEX_STREAM[0], {"type": "item.completed", "item": {
            "type": "command_execution", "command": "false", "aggregated_output": "",
            "exit_code": 1, "status": "failed"}}, CODEX_STREAM[-1]]
        traj = parse_events(parse_trajectory.normalize_events(stream, "codex"))
        self.assertTrue(traj.steps[0].tool_calls[0].is_error)

    def test_codex_streams_that_cannot_be_scored_are_invalid(self):
        sri = parse_trajectory.stream_invalid_reason
        self.assertEqual(sri(CODEX_STREAM[1:], "codex"), "no init event")
        self.assertEqual(sri(CODEX_STREAM[:-1], "codex"), "codex stream ended with no turn.completed")
        failed = CODEX_STREAM[:2] + [{"type": "turn.failed", "error": {"message": "throttled"}}]
        self.assertEqual(sri(failed, "codex"), "codex reported an error: throttled")
        self.assertEqual(sri([], "codex"), "no events")

    def test_codex_error_only_stream_records_no_tokens(self):
        failed = CODEX_STREAM[:1] + [{"type": "turn.failed", "error": {"message": "throttled"}}]
        events = parse_trajectory.normalize_events(failed, "codex")
        traj = parse_events(events)
        self.assertIsNone(traj.input_tokens)
        self.assertIsNone(traj.token_source)
        self.assertIsNone(run_task_evals.extract_result_summary(events)["token_source"])

    def test_kiro_acp_updates_in_either_envelope(self):
        traj = parse_events(parse_trajectory.normalize_events(KIRO_RPC, "kiro"))
        self.assertEqual(traj.tool_sequence, ["read_file"])
        self.assertEqual(traj.steps[0].tool_calls[0].input, {"path": "a.yaml"})
        self.assertEqual(traj.steps[0].tool_calls[0].result, "Found 3 files")
        traj = parse_events(parse_trajectory.normalize_events(KIRO_TYPED, "kiro"))
        self.assertEqual(traj.tool_sequence, ["execute_bash"])
        self.assertTrue(traj.steps[0].tool_calls[0].is_error)
        self.assertEqual((traj.input_tokens, traj.output_tokens), (7, 3))
        self.assertIsNone(parse_trajectory.stream_invalid_reason(KIRO_TYPED, "kiro"))

    def test_kiro_without_tokens_reads_none(self):
        traj = parse_events(parse_trajectory.normalize_events(KIRO_RPC, "kiro"))
        self.assertIsNone(traj.input_tokens)
        self.assertIsNone(traj.token_source)

    def test_kiro_shape_with_no_tool_view_is_invalid(self):
        sri = parse_trajectory.stream_invalid_reason
        self.assertEqual(sri([{"type": "text", "text": "hi"}], "kiro"), "no runStarted event")
        self.assertIn("tool calls cannot be read",
                      sri([{"type": "runStarted"}, {"type": "runFinished"}], "kiro"))
        err = [{"type": "runStarted"}] + KIRO_RPC + [
            {"type": "runError", "data": {"sessionId": None, "stage": "x", "message": "boom"}}]
        self.assertEqual(sri(err, "kiro"), "kiro reported an error: boom")

    def test_claude_stream_is_unchanged(self):
        events = [INIT, RESULT, ["not", "an", "object"]]
        self.assertEqual(parse_trajectory.normalize_events(events, "claude"), [INIT, RESULT])

    def test_unknown_harness_is_refused(self):
        with self.assertRaises(ValueError):
            parse_trajectory.normalize_events([], "gemini")


class HarnessAdapters(Tmp):
    def test_one_adapter_per_harness(self):
        self.assertEqual(set(run_task_evals.HARNESS_ADAPTERS), {"claude", "kiro", "codex"})
        env = dict(ROLE)
        claude = run_task_evals.adapter_claude(prompt="P", model="M", sandbox=self.tmp, env=env)
        self.assertEqual(claude[:3], ["claude", "-p", "P"])
        self.assertIn("bypassPermissions", claude)
        kiro = run_task_evals.adapter_kiro(prompt="P", model="M", sandbox=self.tmp, env=env)
        for flag in ("--no-interactive", "stream-json", "--trust-all-tools"):
            self.assertIn(flag, kiro)
        self.assertEqual(kiro[-1], "P")
        codex = run_task_evals.adapter_codex(prompt="P", model="M", sandbox=self.tmp, env=env)
        for flag in ("--json", "--skip-git-repo-check", "--ephemeral"):
            self.assertIn(flag, codex)
        self.assertIn('model_providers.amazon-bedrock-runtime.aws.region="us-west-2"', codex)
        self.assertEqual(codex[-1], "P")

    def test_kiro_run_stages_the_skill_and_keeps_the_eval_role_env(self):
        skill = self.tmp / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: s\n---\n")
        envlog = self.tmp / "env.json"
        fake_exe(self.bin, "kiro-cli", KIRO_TYPED, 0, extra=(
            "json.dump({'aws': os.environ.get('AWS_ACCESS_KEY_ID'), 'home': os.environ['HOME'],"
            " 'skill': os.path.isfile('.kiro/skills/s/SKILL.md')}, open(%r, 'w'))\n") % str(envlog))
        out = self.subject(harness="kiro", with_skill=True, repo_skill_dir=skill)
        self.assertTrue(out["ok"], out)
        seen = json.loads(envlog.read_text())
        self.assertEqual(seen["aws"], "ASIAROLEKEY")
        self.assertTrue(seen["skill"])
        self.assertEqual(self.aws_env.call_count, 1)
        run = self.tmp / "run"
        self.assertTrue((run / "raw-events.jsonl").exists())
        norm = [json.loads(l) for l in (run / "events.jsonl").read_text().splitlines() if l]
        self.assertEqual(norm[0]["subtype"], "init")
        self.assertFalse((run / "outputs" / ".kiro").exists())

    def test_codex_run_with_bad_stream_is_invalid(self):
        fake_exe(self.bin, "codex", CODEX_STREAM[1:], 0)
        out = self.subject(harness="codex")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no init event")

    def test_kiro_canned_multiturn_runs_one_turn_and_says_so(self):
        fake_exe(self.bin, "kiro-cli", KIRO_TYPED, 0)
        multi = elicitation.ElicitationConfig.from_dict({
            "strategy": "canned-multiturn", "max_turns": 2,
            "turns": [{"question_match": "x", "answer": "y"}]})
        out = self.subject(harness="kiro", elicitation=multi)
        self.assertTrue(out["ok"], out)
        self.assertIn("single turn", out["elicitation"])

    def test_unknown_harness_is_refused(self):
        with self.assertRaises(ValueError):
            self.subject(harness="gemini")


# ---------- shared class cases, targets, kubeconfig ----------------------


class ClassCases(Tmp):
    def make_class(self, cases):
        root = self.tmp / "classes"
        suite = root / "apex-base" / "evals" / "injection"
        (suite / "files" / "eval-9001").mkdir(parents=True)
        (suite / "files" / "eval-9001" / "notes.md").write_text("Note to the assistant")
        (suite / "evals.json").write_text(json.dumps({"evals": cases}))
        return root, suite

    def test_shared_cases_load_and_merge_with_own(self):
        root, suite = self.make_class([
            {"id": 9001, "prompt": "p", "expectations": ["e"], "files": ["notes.md"]},
            {"id": 1, "name": "by hand", "mode": "manual", "commands": ["x"]}])
        with mock.patch.object(run_task_evals, "CLASSES_ROOT", root):
            shared = run_task_evals.load_shared_cases(["apex-base"])
        self.assertEqual([c["id"] for c in shared], [9001])
        self.assertEqual(shared[0]["_source"], "class:apex-base/injection")
        merged = run_task_evals.merge_cases([{"id": 1, "_source": "own"}], shared)
        self.assertEqual([c["id"] for c in merged], [1, 9001])

    def test_shared_ids_must_be_distinct_integers(self):
        merge = run_task_evals.merge_cases
        own = [{"id": 1, "_source": "own"}]
        with self.assertRaisesRegex(ValueError, "repeats"):
            merge(own, [{"id": 9001, "_source": "a"}, {"id": 9001, "_source": "b"}])
        with self.assertRaisesRegex(ValueError, "not an integer"):
            merge(own, [{"id": "9001", "_source": "a"}])
        with self.assertRaisesRegex(ValueError, "repeats"):
            merge(own, [{"id": 1, "_source": "a"}])

    def test_fixtures_stage_from_the_class_folder(self):
        _root, suite = self.make_class([])
        sandbox = self.tmp / "sb"
        sandbox.mkdir()
        staged = run_task_evals.stage_fixture_files(sandbox, suite, 9001, ["notes.md"])
        self.assertEqual(list(staged), ["notes.md"])
        self.assertTrue((sandbox / "notes.md").is_file())

    def test_explicit_target_list(self):
        targets = run_task_evals.CLASS_TARGETS
        keys = [t["run_key"] for t in targets]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(sorted(t["run_key"] for t in targets if t["blocking"]),
                         ["devops-agent-eks-cost-intelligence", "devops-agent-eks-recon",
                          "devops-agent-eks-security"])
        self.assertEqual(len(targets), 22 + 4 + 6)
        self.assertNotIn("dotnet-aws-ecs", keys)
        for t in targets:
            self.assertTrue((REPO / t["skill_dir"] / "SKILL.md").is_file(), t)

    def test_devops_copy_has_its_own_run_key(self):
        copy = run_task_evals.resolve_target("devops-agent-eks-recon")
        twin = run_task_evals.resolve_target("eks-recon")
        self.assertEqual(copy["skill_rel"], "devops-agent/eks-recon")
        self.assertIsNone(copy["own_eval_dir"])
        self.assertEqual(copy["workspace"],
                         run_task_evals.TARGETS_WORKSPACE / "devops-agent-eks-recon" / "workspace")
        self.assertNotEqual(copy["workspace"], twin["workspace"])
        self.assertNotEqual(run_task_evals.history_path("devops-agent-eks-recon"),
                            run_task_evals.history_path("eks-recon"))

    def test_list_targets_prints_runnable_keys_and_runs_nothing(self):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_task_evals.py", "--list-targets"]), \
                mock.patch.object(run_task_evals, "mint_eval_role_credentials") as mint, \
                contextlib.redirect_stdout(out):
            self.assertEqual(run_task_evals.main(), 0)
        mint.assert_not_called()
        rows = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertIn("eks-recon", [r["run_key"] for r in rows])
        copy = [r for r in rows if r["run_key"] == "devops-agent-eks-security"]
        self.assertEqual([r["classes"] for r in copy], [["apex-base"]])

    def test_kubeconfig_is_copied_per_run(self):
        shared = self.tmp / "kubeconfig.readonly"
        shared.write_text("shared\n")
        fake_exe(self.bin, "claude", [INIT, RESULT], 0, extra=(
            "open(os.environ['KUBECONFIG'], 'a').write('rewritten\\n')\n"
            "open(%r, 'w').write(os.environ['KUBECONFIG'])\n") % str(self.tmp / "kc-path"))
        out = self.subject(extra_env={"KUBECONFIG": str(shared)})
        self.assertTrue(out["ok"], out)
        self.assertEqual(shared.read_text(), "shared\n")
        self.assertNotEqual((self.tmp / "kc-path").read_text(), str(shared))


# ---------- run_skill with fakes ---------------------------------


class RunSkill(Tmp):
    def setUp(self):
        super().setUp()
        self.evals = self.tmp / "evals"
        self.history = self.tmp / "history"
        self.calls = []
        for p in [
            mock.patch.object(run_task_evals, "EVALS_ROOT", self.evals),
            mock.patch.object(run_task_evals, "TARGETS_WORKSPACE", self.evals / "workspace"),
            mock.patch.object(run_task_evals, "HISTORY_DIR", self.history),
            mock.patch.object(run_task_evals, "CLASSES_ROOT", self.tmp / "classes"),
            mock.patch.object(run_task_evals, "load_skilleval_config",
                              return_value=types.SimpleNamespace(timeout=60, pass_k=3)),
            mock.patch.object(run_task_evals, "run_subject", side_effect=self.fake_subject),
            mock.patch.object(run_task_evals, "run_grader", side_effect=self.fake_grader),
            mock.patch.object(run_task_evals, "run_benchmark", side_effect=self.fake_benchmark),
        ]:
            p.start()
            self.addCleanup(p.stop)
        self.fail_case = set()
        self.subject_fails = set()

    def write_own(self, skill, cases):
        d = self.evals / skill
        d.mkdir(parents=True)
        (d / "evals.json").write_text(json.dumps({"evals": cases}))

    def fake_subject(self, **kw):
        self.calls.append(kw)
        run_dir = kw["run_dir"]
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "outputs").mkdir(exist_ok=True)
        tokens = 100 if kw["with_skill"] else 50
        (run_dir / "timing.json").write_text(json.dumps({
            "total_tokens": tokens, "input_tokens": tokens - 10, "output_tokens": 10,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            "token_source": "usage", "total_duration_seconds": 2.5}))
        key = (kw["eval_id"], run_dir.parent.name, run_dir.name)
        if key in self.subject_fails:
            return {"transcript_path": "t", "outputs_dir": str(run_dir / "outputs"), "ok": False,
                    "reason": "subject exited 1", "invalid": True, "exit_codes": [1],
                    "elicitation": None}
        if kw["eval_id"] != 99:
            (run_dir / "events.jsonl").write_text(json.dumps(INIT) + "\n" + json.dumps(RESULT) + "\n")
        return {"transcript_path": "t", "outputs_dir": str(run_dir / "outputs"), "ok": True,
                "reason": None, "invalid": False, "exit_codes": [0], "elicitation": None}

    def fake_grader(self, **kw):
        run_dir = kw["run_dir"]
        eval_id = json.loads((run_dir.parent.parent / "eval_metadata.json").read_text())["eval_id"]
        ok = (eval_id, run_dir.parent.name) not in self.fail_case
        grading = {"expectations": [{"text": "e", "passed": ok, "evidence": ""}],
                   "summary": {"passed": int(ok), "failed": int(not ok), "total": 1,
                               "pass_rate": float(ok)}}
        (run_dir / "grading.json").write_text(json.dumps(grading))
        return grading

    def fake_benchmark(self, skill, runs_dir, skill_path=None):
        self.bench_skill_path = skill_path
        summary = {}
        for config_dir in sorted(runs_dir.glob("eval-*/*")):
            summary.setdefault(config_dir.name, {"pass_rate": {"mean": 0.5, "stddev": 0.1}})
        (runs_dir / "benchmark.json").write_text(json.dumps({"run_summary": summary}))

    def run_it(self, skill, **kw):
        args = dict(model="m", runs=None, include_live_only=False, subject_timeout=None,
                    grader_timeout=60, extra_env=None)
        args.update(kw)
        with contextlib.redirect_stderr(io.StringIO()):
            return run_task_evals.run_skill(skill, **args)

    @unittest.skipUnless(HAS_BASE_TAG, NO_TAG)
    def test_old_arm_is_the_skill_at_the_base_ref(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"]}])
        sha = run_task_evals.resolve_base_ref("v1.3.0")
        out = self.run_it("eks-recon", base_ref="v1.3.0", base_sha=sha)
        entry = out["history_entry"]
        self.assertEqual(entry["baseline_arm"], "base_skill")
        self.assertEqual(entry["comparison"], "new_vs_base")
        self.assertEqual(entry["base_ref_sha"], sha)
        self.assertIsNone(entry["without_skill_mean"])
        self.assertEqual(entry["base_skill_mean"], 0.5)
        arms = {c["run_dir"].parent.name for c in self.calls}
        self.assertEqual(arms, {"with_skill", "base_skill"})
        base_dirs = {c["repo_skill_dir"] for c in self.calls if c["run_dir"].parent.name == "base_skill"}
        self.assertEqual(len(base_dirs), 1)
        base_dir = base_dirs.pop()
        self.assertFalse(str(base_dir).startswith(str(REPO)))
        self.assertFalse(base_dir.exists(), "the materialised ref is removed after the run")

    @unittest.skipUnless(HAS_BASE_TAG, NO_TAG)
    def test_skill_absent_at_the_ref_runs_against_without(self):
        self.write_own("apex-new-skill", [{"id": 1, "prompt": "p", "expectations": ["e"]}])
        sha = run_task_evals.resolve_base_ref("v1.3.0")
        entry = self.run_it("apex-new-skill", base_ref="v1.3.0", base_sha=sha)["history_entry"]
        self.assertEqual(entry["baseline_arm"], "without_skill")
        self.assertEqual(entry["comparison"], "new_vs_without")
        self.assertEqual(entry["without_skill_mean"], 0.5)
        self.assertEqual({c["with_skill"] for c in self.calls if c["run_dir"].parent.name == "without_skill"},
                         {False})

    def test_runs_default_to_pass_k(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"]}])
        entry = self.run_it("eks-recon")["history_entry"]
        self.assertEqual(entry["runs_per_prompt"], 3)
        self.assertEqual(entry["pass_k"], 3)
        self.assertEqual(len(self.calls), 6)

    def test_one_case_fails_on_its_own_with_tokens_and_time(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"]},
                                     {"id": 2, "prompt": "q", "expectations": ["e"]}])
        self.fail_case = {(2, "with_skill")}
        out = self.run_it("eks-recon", runs=3)
        entry = out["history_entry"]
        by_id = {c["eval_id"]: c for c in entry["cases"]}
        self.assertTrue(by_id[1]["pass"])
        self.assertFalse(by_id[2]["pass"])
        self.assertTrue(by_id[2]["regressed"])
        new = by_id[1]["arms"]["with_skill"]
        self.assertEqual(new["tokens_per_run"], [100, 100, 100])
        self.assertEqual(new["wall_seconds_per_run"], [2.5, 2.5, 2.5])
        self.assertTrue(new["pass_all_k"])
        self.assertEqual(by_id[1]["arms"]["without_skill"]["tokens_mean"], 50)
        s = entry["skill_summary"]
        self.assertEqual((s["cases"], s["cases_passed"], s["cases_regressed"]), (2, 1, 1))
        self.assertEqual(s["arms"]["with_skill"]["tokens_per_run_mean"], 100)
        for field in ("kind", "ts", "model", "with_skill_mean", "with_skill_stddev", "without_skill_mean",
                      "without_skill_stddev", "delta", "eval_ids", "token_usage", "runs_per_prompt"):
            self.assertIn(field, entry)
        self.assertEqual(entry["token_usage"]["with_skill"]["runs"], 6)
        hist = [json.loads(l) for l in (self.history / "eks-recon.jsonl").read_text().splitlines()]
        self.assertEqual(hist[-1]["cases"], json.loads(json.dumps(entry["cases"])))
        cases_file = json.loads((Path(out["runs_dir"]) / "cases.json").read_text())
        self.assertEqual(len(cases_file["cases"]), 2)
        rec = json.loads((Path(out["runs_dir"]) / "eval-1" / "with_skill" / "run-1" / "run-result.json").read_text())
        self.assertEqual((rec["valid"], rec["pass"], rec["tokens"]), (True, True, 100))

    def test_invalid_runs_are_recorded_and_never_pass(self):
        """Check fix: at HEAD a failed subject `continue`d with no
        process-assertions.json and no record of the run."""
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"],
                                      "process_assertions": [{"type": "no-tool-called", "tool": "Bash"}]}])
        self.subject_fails = {(1, "with_skill", f"run-{k}") for k in (1, 2, 3)}
        out = self.run_it("eks-recon", runs=3)
        case = out["history_entry"]["cases"][0]
        new = case["arms"]["with_skill"]
        self.assertEqual((new["runs"], new["valid_runs"], new["passes"]), (3, 0, 0))
        self.assertFalse(case["pass"])
        self.assertEqual(new["invalid_reasons"], ["subject exited 1"] * 3)
        pa = json.loads((Path(out["runs_dir"]) / "eval-1" / "with_skill" / "run-1"
                         / "process-assertions.json").read_text())
        self.assertEqual((pa["passed"], pa["failed"]), (0, 1))
        self.assertEqual(pa["failure_classes"], {"invalid_run": 1})
        self.assertEqual(out["history_entry"]["skill_summary"]["arms"]["with_skill"]["invalid_runs"], 3)

    def test_missing_events_file_is_an_invalid_run(self):
        """Check fix: at HEAD a missing events.jsonl was skipped silently."""
        self.write_own("eks-recon", [{"id": 99, "prompt": "p", "expectations": ["e"],
                                      "process_assertions": [{"type": "no-tool-called", "tool": "Bash"}]}])
        out = self.run_it("eks-recon", runs=1)
        new = out["history_entry"]["cases"][0]["arms"]["with_skill"]
        self.assertEqual(new["invalid_reasons"], ["events.jsonl missing"])
        self.assertFalse(out["history_entry"]["cases"][0]["pass"])

    def test_process_assertions_run_under_the_limit(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"],
                                      "process_assertions": [{"type": "no-tool-called", "tool": "Bash"}]}])
        with mock.patch.object(run_task_evals, "evaluate_with_timeouts",
                               wraps=run_task_evals.evaluate_with_timeouts) as ewt:
            self.run_it("eks-recon", runs=1)
        self.assertEqual(ewt.call_count, 2)

    def test_class_target_runs_shared_cases_in_its_own_workspace(self):
        suite = self.tmp / "classes" / "apex-base" / "evals" / "read-only"
        suite.mkdir(parents=True)
        (suite / "evals.json").write_text(json.dumps({"evals": [
            {"id": 9004, "prompt": "p", "expectations": ["e"]}]}))
        out = self.run_it("devops-agent-eks-recon", runs=1)
        entry = out["history_entry"]
        self.assertEqual(entry["run_key"], "devops-agent-eks-recon")
        self.assertEqual(entry["skill_dir"], "devops-agent/eks-recon")
        self.assertTrue(entry["blocking"])
        self.assertEqual(entry["cases"][0]["source"], "class:apex-base/read-only")
        self.assertEqual(self.calls[0]["skill_eval_dir"], suite)
        self.assertEqual(self.calls[0]["repo_skill_dir"], REPO / "devops-agent" / "eks-recon")
        self.assertTrue(out["runs_dir"].startswith(str(self.evals / "workspace" / "devops-agent-eks-recon")))
        self.assertEqual(self.bench_skill_path, REPO / "devops-agent" / "eks-recon")
        self.assertTrue((self.history / "devops-agent-eks-recon.jsonl").exists())

    def test_member_runs_own_and_shared_cases(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"]}])
        suite = self.tmp / "classes" / "apex-base" / "evals" / "injection"
        suite.mkdir(parents=True)
        (suite / "evals.json").write_text(json.dumps({"evals": [
            {"id": 9001, "prompt": "p", "expectations": ["e"]}]}))
        entry = self.run_it("eks-recon", runs=1)["history_entry"]
        self.assertEqual(entry["eval_ids"], [1, 9001])

    def test_harness_passes_through(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"]}])
        entry = self.run_it("eks-recon", runs=1, harness="codex")["history_entry"]
        self.assertEqual({c["harness"] for c in self.calls}, {"codex"})
        self.assertEqual(entry["harness"], "codex")

    def test_history_row_records_the_subject_model(self):
        self.write_own("eks-recon", [{"id": 1, "prompt": "p", "expectations": ["e"]}])
        for harness in ("codex", "kiro"):
            entry = self.run_it("eks-recon", runs=1, harness=harness,
                                subject_model_id="s-id")["history_entry"]
            self.assertEqual((entry["model"], entry["subject_model"]), ("m", "s-id"))


class BaseRef(unittest.TestCase):
    @unittest.skipUnless(HAS_BASE_TAG, NO_TAG)
    def test_materialise_reads_git_objects_only(self):
        sha = run_task_evals.resolve_base_ref("v1.3.0")
        with tempfile.TemporaryDirectory() as d:
            got = run_task_evals.materialise_skill_at_ref(sha, "skills/eks-recon", Path(d))
            self.assertTrue((got / "SKILL.md").is_file())
            want = subprocess.run(["git", "-C", str(REPO), "show", f"{sha}:skills/eks-recon/SKILL.md"],
                                  capture_output=True).stdout
            self.assertEqual((got / "SKILL.md").read_bytes(), want)
            self.assertIsNone(run_task_evals.materialise_skill_at_ref(sha, "skills/apex-new-skill", Path(d)))

    def test_unknown_ref_is_an_error(self):
        with self.assertRaises(run_task_evals.BaseRefError):
            run_task_evals.resolve_base_ref("no-such-ref-evals")

    @unittest.skipUnless(HAS_BASE_TAG, NO_TAG)
    def test_cli_defaults(self):
        captured = {}

        def fake_run_skill(skill, **kw):
            captured.update(kw)
            return {"skill": skill, "skipped": "fake"}

        with mock.patch.object(sys, "argv", ["run_task_evals.py", "--skill", "eks-recon"]), \
                mock.patch.object(run_task_evals, "mint_eval_role_credentials"), \
                mock.patch.object(run_task_evals, "set_eval_credentials"), \
                mock.patch.object(run_task_evals, "run_skill", side_effect=fake_run_skill), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_task_evals.main(), 0)
        self.assertIsNone(captured["runs"])
        self.assertEqual(captured["harness"], "claude")
        self.assertEqual(captured["base_ref"], "v1.3.0")
        self.assertEqual(captured["base_sha"], run_task_evals.resolve_base_ref("v1.3.0"))

    def test_base_ref_none_and_bad_ref(self):
        captured = {}
        argv = ["run_task_evals.py", "--skill", "eks-recon"]
        common = [mock.patch.object(run_task_evals, "mint_eval_role_credentials"),
                  mock.patch.object(run_task_evals, "set_eval_credentials"),
                  mock.patch.object(run_task_evals, "run_skill",
                                    side_effect=lambda s, **kw: captured.update(kw) or {"skill": s, "skipped": "f"})]
        with contextlib.ExitStack() as stack:
            for p in common:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            err = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            with mock.patch.object(sys, "argv", argv + ["--base-ref", "none"]):
                self.assertEqual(run_task_evals.main(), 0)
            self.assertIsNone(captured["base_sha"])
            with mock.patch.object(sys, "argv", argv + ["--base-ref", "no-such-ref-evals"]):
                self.assertEqual(run_task_evals.main(), 2)
            self.assertIn("names no commit", err.getvalue())


# ---------- fix round: one parse, one env, models, targets, fixtures ----


class KiroOneParse(unittest.TestCase):
    """The task and triggering runners read a kiro stream by one set of rules."""

    def test_task_kiro_needs_start_and_finish(self):
        sri = parse_trajectory.stream_invalid_reason
        self.assertIsNone(sri(KIRO_TYPED, "kiro"))
        self.assertEqual(sri(KIRO_TYPED[1:], "kiro"), "no runStarted event")
        self.assertEqual(sri(KIRO_TYPED[:-1], "kiro"), "kiro stream ended with no runFinished")
        self.assertIn("tool calls cannot be read", sri([KIRO_TYPED[0], KIRO_TYPED[-1]], "kiro"))

    def test_task_kiro_tokens_come_from_run_finished(self):
        traj = parse_events(parse_trajectory.normalize_events(KIRO_TYPED, "kiro"))
        self.assertEqual((traj.input_tokens, traj.output_tokens), (7, 3))
        self.assertEqual(traj.token_source, "usage")
        usage_update = {"type": "sessionUpdate", "data": {"sessionUpdate": "usage_update",
                                                          "inputTokens": 9, "outputTokens": 9}}
        stream = KIRO_TYPED[:-1] + [usage_update, {"type": "runFinished", "data": {}}]
        traj = parse_events(parse_trajectory.normalize_events(stream, "kiro"))
        self.assertIsNone(traj.input_tokens)

    def test_non_integer_kiro_count_reads_as_missing(self):
        done = {"type": "runFinished", "data": {"usage": {"inputTokens": "7", "outputTokens": 3}}}
        self.assertIsNone(parse_trajectory.kiro_usage(done))
        traj = parse_events(parse_trajectory.normalize_events(KIRO_TYPED[:-1] + [done], "kiro"))
        self.assertIsNone(traj.input_tokens)

    def test_calls_with_no_id_are_kept_apart(self):
        calls = [{"type": "sessionUpdate", "data": {"sessionUpdate": "tool_call", "title": "read",
                                                     "rawInput": {"path": p}}} for p in "abc"]
        stream = [KIRO_TYPED[0]] + calls + [KIRO_TYPED[-1]]
        traj = parse_events(parse_trajectory.normalize_events(stream, "kiro"))
        self.assertEqual([s.tool_calls[0].input for s in traj.steps],
                         [{"path": "a"}, {"path": "b"}, {"path": "c"}])

    def test_triggering_reads_the_same_tokens_and_envelopes(self):
        rpc_read = j({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {
            "sessionUpdate": "tool_call", "toolCallId": "t9", "kind": "read",
            "rawInput": {"path": f"/tmp/h/.kiro/skills/{SKILL}/SKILL.md"}}}})
        out = kiro_parse([KIRO_START, rpc_read], sleep=30)
        self.assertTrue(out["triggered"])
        out = kiro_parse([KIRO_START, KIRO_TEXT, KIRO_DONE])
        self.assertEqual(out["tokens"], {"input_tokens": 40, "output_tokens": 2,
                                         "cache_read_input_tokens": 0,
                                         "cache_creation_input_tokens": 0, "total_tokens": 42})

    def test_codex_tokens_share_one_reading(self):
        out = codex_parse([CODEX_START, CODEX_TURN, CODEX_LS, CODEX_MSG, CODEX_DONE])
        traj = parse_events(parse_trajectory.normalize_events(
            [json.loads(x) for x in (CODEX_START, CODEX_LS, CODEX_DONE)], "codex"))
        self.assertEqual(out["tokens"]["cache_read_input_tokens"], traj.cache_read_input_tokens)
        self.assertEqual(out["tokens"]["input_tokens"], traj.input_tokens)

    def test_harnesses_defined_once(self):
        self.assertIs(run_triggering.HARNESSES, parse_trajectory.HARNESSES)
        self.assertIs(run_task_evals.HARNESSES, parse_trajectory.HARNESSES)


class SubjectEnv(Tmp):
    """One env builder for every subject: codex loses its host routing on the
    task runner too, CI secrets never reach a subject, Kiro's key reaches
    only kiro."""

    def setUp(self):
        super().setUp()
        self.envlog = self.tmp / "env.json"
        self.host = mock.patch.dict(os.environ, {
            "CODEX_HOME": "/host/codex", "OPENAI_BASE_URL": "http://evil", "OPENAI_API_KEY": "k",
            "CODEX_API_KEY": "k", "APEX_EVAL_AWS_CONFIG": "cfg", "APEX_EVAL_EXPECTED_ACCOUNT": "1",
            "KIRO_API_KEY": "kiro-key"})
        self.host.start()

    def tearDown(self):
        self.host.stop()
        super().tearDown()

    def record_env(self):
        return ("json.dump({k: os.environ.get(k) for k in ('CODEX_HOME', 'OPENAI_BASE_URL',"
                " 'OPENAI_API_KEY', 'CODEX_API_KEY', 'APEX_EVAL_AWS_CONFIG',"
                " 'APEX_EVAL_EXPECTED_ACCOUNT', 'KIRO_API_KEY', 'HOME')}, open(%r, 'w'))\n"
                % str(self.envlog))

    def test_task_codex_subject_env(self):
        fake_exe(self.bin, "codex", CODEX_STREAM, 0, extra=self.record_env())
        out = self.subject(harness="codex")
        self.assertTrue(out["ok"], out)
        seen = json.loads(self.envlog.read_text())
        for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "CODEX_API_KEY", "APEX_EVAL_AWS_CONFIG",
                  "APEX_EVAL_EXPECTED_ACCOUNT", "KIRO_API_KEY"):
            self.assertIsNone(seen[k], k)
        self.assertEqual(seen["CODEX_HOME"], str(Path(seen["HOME"]) / ".codex"))

    def test_task_kiro_subject_gets_only_its_key(self):
        fake_exe(self.bin, "kiro-cli", KIRO_TYPED, 0, extra=self.record_env())
        out = self.subject(harness="kiro")
        self.assertTrue(out["ok"], out)
        seen = json.loads(self.envlog.read_text())
        self.assertEqual(seen["KIRO_API_KEY"], "kiro-key")
        self.assertIsNone(seen["APEX_EVAL_AWS_CONFIG"])

    def test_claude_subject_and_grader_env_drop_ci_secrets(self):
        env = run_triggering.build_subprocess_env(self.tmp, aws_env=dict(ROLE))
        for k in ("APEX_EVAL_AWS_CONFIG", "APEX_EVAL_EXPECTED_ACCOUNT", "KIRO_API_KEY"):
            self.assertNotIn(k, env)
        self.assertEqual(run_triggering.harness_env(env, self.tmp, "kiro")["KIRO_API_KEY"],
                         "kiro-key")
        self.assertNotIn("KIRO_API_KEY", run_triggering.harness_env(env, self.tmp, "claude"))
        fake_exe(self.bin, "claude", [RESULT], 0, extra=self.record_env())
        (self.tmp / "g").mkdir()
        run_task_evals.run_grader(expectations=["e"], transcript_path=self.tmp / "t.md",
                                  outputs_dir=self.tmp / "o", run_dir=self.tmp / "g",
                                  model="m", timeout=30)
        seen = json.loads(self.envlog.read_text())
        for k in ("APEX_EVAL_AWS_CONFIG", "APEX_EVAL_EXPECTED_ACCOUNT", "KIRO_API_KEY"):
            self.assertIsNone(seen[k], k)


class GraderNullObjects(Tmp):

    def grade(self, run_dir, grading):
        run_dir.mkdir(parents=True)
        fake_exe(self.bin, "claude", [RESULT], 0, extra="open(%r, 'w').write(%r)\n" % (
            str(run_dir / "grading.json"), json.dumps(grading)))
        with contextlib.redirect_stderr(io.StringIO()):
            return run_task_evals.run_grader(expectations=["e"], transcript_path=self.tmp / "t.md",
                                             outputs_dir=self.tmp / "o", run_dir=run_dir,
                                             model="m", timeout=30)

    def test_null_grader_objects_reach_the_benchmark_as_empty(self):
        bench = self.tmp / "bench"
        base = {"expectations": [{"text": "e", "passed": True, "evidence": "x"}],
                "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0}}
        out = self.grade(bench / "eval-1" / "with_skill" / "run-1",
                         dict(base, timing=None, execution_metrics=None, user_notes_summary=None))
        self.assertNotIn("error", out)
        for k in ("timing", "execution_metrics", "user_notes_summary"):
            self.assertEqual(out[k], {}, k)
        out = self.grade(bench / "eval-1" / "with_skill" / "run-2",
                         dict(base, user_notes_summary={"uncertainties": None, "needs_review": ["n"]}))
        self.assertEqual(out["user_notes_summary"], {"uncertainties": [], "needs_review": ["n"]})
        saved = json.loads((bench / "eval-1" / "with_skill" / "run-2" / "grading.json").read_text())
        self.assertEqual(saved["user_notes_summary"], out["user_notes_summary"])
        with contextlib.redirect_stderr(io.StringIO()):
            run_task_evals.run_benchmark("apex", bench, skill_path=REPO / "skills" / "apex")
        self.assertTrue((bench / "benchmark.json").is_file())


class SubjectModelPerHarness(unittest.TestCase):

    def test_defaults(self):
        sm = run_triggering.subject_model
        self.assertEqual(sm("claude", "bedrock-id", None), "bedrock-id")
        self.assertEqual(sm("codex", "bedrock-id", None), "global.openai.gpt-5.6-terra")
        self.assertEqual(sm("kiro", "bedrock-id", None), "claude-opus-4.8")
        self.assertEqual(sm("codex", "bedrock-id", "x"), "x")

    def test_task_cli_runs_the_subject_on_its_harness_model_and_the_grader_on_model(self):
        captured = {}

        def fake_run_skill(skill, **kw):
            captured.update(kw)
            return {"skill": skill, "skipped": "fake"}

        argv = ["run_task_evals.py", "--skill", "eks-recon", "--harness", "codex",
                "--model", "grader-id", "--base-ref", "none"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(run_task_evals, "mint_eval_role_credentials"), \
                mock.patch.object(run_task_evals, "set_eval_credentials"), \
                mock.patch.object(run_task_evals, "run_skill", side_effect=fake_run_skill), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_task_evals.main(), 0)
        self.assertEqual(captured["model"], "grader-id")
        self.assertEqual(captured["subject_model_id"], "global.openai.gpt-5.6-terra")

    def test_kiro_pins_the_v3_engine_on_both_runners(self):
        cmd = run_task_evals.adapter_kiro(prompt="P", model="M", sandbox=Path("/tmp"), env={})
        self.assertEqual(cmd[cmd.index("--agent-engine") + 1], "v3")
        seen = {}

        def fake_popen(c, **kw):
            seen["cmd"] = c
            return printer([KIRO_START, KIRO_TEXT, KIRO_DONE])

        home = Path(tempfile.mkdtemp(prefix="evals-kiro-cmd-"))
        try:
            with mock.patch.object(run_triggering.subprocess, "Popen", side_effect=fake_popen):
                run_triggering.run_kiro("q", SKILL, home, "m", 30, home, home, {})
        finally:
            shutil.rmtree(home, ignore_errors=True)
        self.assertEqual(seen["cmd"][seen["cmd"].index("--agent-engine") + 1], "v3")


class TokensNotRecorded(unittest.TestCase):
    """A run with no token count reads None, never 0, up to the scorecard mean."""

    def test_run_record_and_means(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "timing.json").write_text(json.dumps({
                "total_tokens": 0, "input_tokens": 0, "token_source": None,
                "total_duration_seconds": 1.0}))
            rec = run_task_evals.run_record(run_dir, arm="with_skill", k=1, harness="kiro",
                                            subj={"ok": True, "reason": None})
        self.assertIsNone(rec["tokens"])
        self.assertIsNone(rec["token_usage"]["input_tokens"])
        arm = run_task_evals.summarize_arm([rec], 1)
        self.assertIsNone(arm["tokens_mean"])
        mixed = run_task_evals.summarize_arm([rec, dict(rec, tokens=90)], 2)
        self.assertEqual(mixed["tokens_mean"], 90)
        case = run_task_evals.summarize_case(1, "own", {"with_skill": [rec]}, "without_skill", 1)
        skill = run_task_evals.summarize_skill([case], "without_skill")
        self.assertIsNone(skill["arms"]["with_skill"]["tokens_per_run_mean"])

    def test_aggregate_token_usage_skips_a_run_with_no_count(self):
        with tempfile.TemporaryDirectory() as d:
            for run, source, total in (("run-1", None, 0), ("run-2", "usage", 100)):
                run_dir = Path(d) / "eval-1" / "with_skill" / run
                run_dir.mkdir(parents=True)
                (run_dir / "timing.json").write_text(json.dumps(
                    {"total_tokens": total, "token_source": source}))
            usage = run_task_evals.aggregate_token_usage(Path(d), configs=("with_skill",))
        self.assertEqual(usage["with_skill"]["runs"], 1)
        self.assertEqual(usage["with_skill"]["mean"]["total_tokens"], 100)


class TargetsAndCases(Tmp):

    def list_targets(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["run_task_evals.py", "--list-targets", *flags]), \
                mock.patch.object(run_task_evals, "mint_eval_role_credentials") as mint, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(run_task_evals.main(), 0)
        mint.assert_not_called()
        return [json.loads(l)["run_key"] for l in out.getvalue().splitlines()], err.getvalue()

    def test_list_targets_keeps_only_keys_with_a_runnable_case(self):
        keys, err = self.list_targets()
        self.assertIn("devops-agent-eks-security", keys)
        self.assertNotIn("setup", keys)
        self.assertIn("setup: no runnable case", err)
        # With no shared class cases, a copy with no suite of its own has no
        # case, and a key whose own cases are all live-only lists only with
        # --include-live-only.
        with mock.patch.object(run_task_evals, "CLASSES_ROOT", self.tmp / "no-classes"):
            keys, err = self.list_targets()
            self.assertIn("eks-recon", keys)
            self.assertNotIn("devops-agent-eks-security", keys)
            self.assertIn("devops-agent-eks-security: no runnable case", err)
            self.assertNotIn("eks-operation-review", keys)
            keys, _ = self.list_targets("--include-live-only")
            self.assertIn("eks-operation-review", keys)
            self.assertNotIn("setup", keys)

    def test_subject_model_flag_overrides_the_harness_default(self):
        captured = {}

        def fake_run_skill(skill, **kw):
            captured.update(kw)
            return {"skill": skill, "skipped": "fake"}

        argv = ["run_task_evals.py", "--skill", "eks-recon", "--harness", "kiro", "--model", "g",
                "--subject-model", "s-id", "--base-ref", "none"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(run_task_evals, "mint_eval_role_credentials"), \
                mock.patch.object(run_task_evals, "set_eval_credentials"), \
                mock.patch.object(run_task_evals, "run_skill", side_effect=fake_run_skill), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_task_evals.main(), 0)
        self.assertEqual((captured["model"], captured["subject_model_id"]), ("g", "s-id"))

    def test_runs_below_one_is_refused(self):
        with mock.patch.object(sys, "argv", ["run_task_evals.py", "--runs", "0"]), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            run_task_evals.main()
        self.assertEqual(e.exception.code, 2)

    def test_shared_ids_need_no_range(self):
        merged = run_task_evals.merge_cases([{"id": 1, "_source": "own"}],
                                            [{"id": 8, "_source": "class:x/y"}])
        self.assertEqual([c["id"] for c in merged], [1, 8])

    def test_removed_triggering_flags(self):
        for argv in (["--list-class-targets", "apex-base"], ["--skill-path", "x", "--kubeconfig", "k"]):
            with mock.patch.object(sys, "argv", ["run_triggering.py"] + argv), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_triggering.main()


class FixtureAndOutputEdges(Tmp):
    """Fixture links to the repo root or .git and special files are refused;
    a linked fixture folder's files are hashed, so they leave outputs/."""

    def fixture(self):
        src = self.tmp / "suite" / "files" / "shared"
        src.mkdir(parents=True)
        return src

    def test_link_to_repo_root_or_git_is_refused(self):
        for target in (REPO, REPO / ".git"):
            src = self.fixture()
            (src / "link").symlink_to(target)
            with self.assertRaisesRegex(run_task_evals.FixtureLinkError, "repo root or .git"):
                run_task_evals.check_fixture_links(src)
            shutil.rmtree(self.tmp / "suite")

    def test_fifo_in_fixture_is_refused(self):
        src = self.fixture()
        os.mkfifo(src / "pipe")
        with self.assertRaisesRegex(run_task_evals.FixtureLinkError, "not a regular file"):
            run_task_evals.check_fixture_links(src)

    def test_fifo_in_sandbox_is_not_copied(self):
        sandbox = self.tmp / "sb"
        (sandbox / "d").mkdir(parents=True)
        os.mkfifo(sandbox / "d" / "pipe")
        (sandbox / "d" / "ok.txt").write_text("x")
        out = self.tmp / "out"
        run_task_evals.snapshot_sandbox_outputs(sandbox, out)
        self.assertTrue((out / "d" / "ok.txt").is_file())
        self.assertFalse((out / "d" / "pipe").exists())

    def test_files_under_a_linked_fixture_folder_are_hashed(self):
        src = self.fixture()
        (src / "link").symlink_to(REPO / "skills" / SKILL)
        sandbox = self.tmp / "sb"
        sandbox.mkdir()
        staged = run_task_evals.stage_fixture_files(sandbox, self.tmp / "suite", 1, ["x"])
        self.assertIn("link/SKILL.md", staged)


# ---------- the gate: regression.py --gate, manifest, Makefile -------


def run_rec(arm, passed, *, valid=True, tokens=100, wall=2.0):
    return {"arm": arm, "valid": valid, "pass": passed and valid, "grader_pass_rate": 1.0 if passed else 0.0,
            "tokens": tokens, "token_usage": {k: 0 for k in parse_trajectory.USAGE_TOKEN_KEYS},
            "wall_seconds": wall, "invalid_reason": None if valid else "no init event"}


def gate_case(eval_id, new_passes, base_passes, *, source="own", k=3, base_arm="base_skill"):
    """A case built by the runner's own summarize_case from k runs per arm."""
    by_arm = {"with_skill": [run_rec("with_skill", i < new_passes, tokens=200) for i in range(k)],
              base_arm: [run_rec(base_arm, i < base_passes, tokens=150) for i in range(k)]}
    return run_task_evals.summarize_case(eval_id, source, by_arm, base_arm, k)


def gate_entry(cases, *, base_arm="base_skill", blocking=None, delta=0.0, key="eks-recon"):
    return {"kind": "task", "run_key": key, "harness": "claude", "pass_k": 3,
            "baseline_arm": base_arm, "base_ref": "v1.3.0", "base_ref_sha": "a" * 40,
            "comparison": "new_vs_base" if base_arm == "base_skill" else "new_vs_without",
            "blocking": blocking, "delta": delta, "with_skill_mean": 0.9,
            "base_skill_mean": 0.9 if base_arm == "base_skill" else None,
            "without_skill_mean": 0.9 if base_arm == "without_skill" else None,
            "cases": cases, "skill_summary": run_task_evals.summarize_skill(cases, base_arm)}


class GateTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-gate-"))
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gate(self, outcome_or_text, key="eks-recon", threshold=5.0):
        path = self.tmp / "task.json"
        path.write_text(outcome_or_text if isinstance(outcome_or_text, str)
                        else json.dumps(outcome_or_text))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = regression.run_gate(key, path, threshold)
        return rc, out.getvalue(), err.getvalue()

    def outcome(self, entry, key="eks-recon"):
        runs = self.tmp / "ws" / "runs" / "20261119T000000Z"
        runs.mkdir(parents=True, exist_ok=True)
        return [{"skill": key, "runs_dir": str(runs), "history_entry": entry}]


class GatePerCase(GateTmp):
    """One case failing Pass@k fails the gate on its own; the base arm is
    the one the runner names; tokens and time are in the report and never
    block."""

    def test_one_failed_case_blocks_with_no_pooled_drop(self):
        entry = gate_entry([gate_case(1, 3, 3), gate_case(2, 0, 3)], delta=0.0)
        rc, out, err = self.gate(self.outcome(entry))
        self.assertEqual(rc, 2)
        result = json.loads(out)
        self.assertEqual(result["status"], "REGRESSION")
        self.assertEqual(result["reasons"], ["eval-2 failed Pass@3 (base_skill passed it)"])
        self.assertIn("| eval-2 | own | yes | 0/3 | 3/3 | no | no | 200 | 150 |", err)

    def test_a_case_failing_on_both_arms_still_blocks(self):
        rc, out, _ = self.gate(self.outcome(gate_entry([gate_case(1, 0, 0)])))
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out)["reasons"], ["eval-1 failed Pass@3"])

    def test_invalid_runs_never_pass(self):
        k = 3
        by_arm = {"with_skill": [run_rec("with_skill", True, valid=False) for _ in range(k)],
                  "base_skill": [run_rec("base_skill", True) for _ in range(k)]}
        case = run_task_evals.summarize_case(5, "own", by_arm, "base_skill", k)
        rc, _, _ = self.gate(self.outcome(gate_entry([case])))
        self.assertEqual(rc, 2)

    def test_all_pass_is_exit_0_with_tokens_time_and_the_note(self):
        entry = gate_entry([gate_case(1, 1, 3), gate_case(2, 3, 3)])
        rc, out, err = self.gate(self.outcome(entry))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["status"], "PASS")
        self.assertIn("Tokens/run new | Tokens/run base | Time/run new (s)", err)
        self.assertIn("| with_skill | 2 | 1 | 6 | 0 | 200 | 2.0 |", err)
        self.assertIn("only pass rate blocks", err)
        report = (self.tmp / "ws" / "gate-report.md").read_text()
        self.assertIn("**Status:** PASS", report)

    def test_tokens_and_time_never_block(self):
        cases = [gate_case(1, 3, 3)]
        cases[0]["arms"]["with_skill"]["tokens_mean"] = 10 ** 9
        cases[0]["arms"]["with_skill"]["wall_seconds_mean"] = 10 ** 6
        rc, _, _ = self.gate(self.outcome(gate_entry(cases)))
        self.assertEqual(rc, 0)

    def test_pooled_drop_past_threshold_blocks(self):
        rc, out, _ = self.gate(self.outcome(gate_entry([gate_case(1, 3, 3)], delta=-0.2)))
        self.assertEqual(rc, 2)
        self.assertIn("pooled pass rate -20.0pp against base_skill", json.loads(out)["reasons"][0])
        rc, out, _ = self.gate(self.outcome(gate_entry([gate_case(1, 3, 3)], delta=-0.02)))
        self.assertEqual((rc, json.loads(out)["status"]), (0, "WARNING"))

    def test_without_skill_base_arm_is_read_from_the_entry(self):
        entry = gate_entry([gate_case(1, 0, 3, base_arm="without_skill")], base_arm="without_skill")
        rc, out, err = self.gate(self.outcome(entry))
        self.assertEqual(rc, 2)
        result = json.loads(out)
        self.assertEqual(result["baseline_arm"], "without_skill")
        self.assertEqual(result["cases"][0]["base"]["passes"], 3)
        self.assertIn("with_skill against without_skill", err)

    def test_report_only_target_lists_shared_fails_without_blocking(self):
        shared = gate_case(9001, 0, 3, source="class:apex-base/read-only")
        rc, out, _ = self.gate(self.outcome(gate_entry([shared], blocking=False,
                                                       key="devops-agent-eks-ingress-migration"),
                                            key="devops-agent-eks-ingress-migration"),
                               key="devops-agent-eks-ingress-migration")
        self.assertEqual((rc, json.loads(out)["status"]), (0, "WARNING"))
        self.assertEqual(json.loads(out)["report_only_failures"], [9001])
        # The same target's own case still blocks, and a blocking target's shared case blocks.
        own_fail = gate_entry([gate_case(1, 0, 0), shared], blocking=False)
        self.assertEqual(self.gate(self.outcome(own_fail))[0], 2)
        self.assertEqual(self.gate(self.outcome(gate_entry([shared], blocking=True)))[0], 2)

    def test_nothing_to_score_is_exit_1_never_0(self):
        good = gate_entry([gate_case(1, 3, 3)])
        for bad in ("", "not json", json.dumps([{"skill": "eks-recon", "error": "missing evals.json"}]),
                    json.dumps([{"skill": "eks-recon", "skipped": "no fixture-free prompts"}]),
                    json.dumps([{"skill": "other", "history_entry": good}]),
                    json.dumps([{"skill": "eks-recon", "history_entry": dict(good, cases=[])}]),
                    json.dumps([{"skill": "eks-recon", "history_entry": {"kind": "task"}}])):
            rc, out, err = self.gate(bad)
            self.assertEqual(rc, 1, bad)
            self.assertEqual(out, "", bad)
            self.assertIn("FAIL", err)

    def test_only_a_true_pass_passes(self):
        case = gate_case(1, 3, 3)
        case["pass"] = "false"
        rc, out, _ = self.gate(self.outcome(gate_entry([case])))
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out)["cases"][0]["pass"], False)

    def test_pooled_delta_is_rounded_before_the_threshold(self):
        rc, out, _ = self.gate(self.outcome(gate_entry([gate_case(1, 3, 3)], delta=-0.07000000001)),
                               threshold=7.0)
        self.assertEqual((rc, json.loads(out)["delta_pp"]), (0, -7.0))
        rc, _, _ = self.gate(self.outcome(gate_entry([gate_case(1, 3, 3)], delta=-0.072)), threshold=7.0)
        self.assertEqual(rc, 2)

    def test_gate_needs_task_result(self):
        with mock.patch.object(sys, "argv", ["regression.py", "--gate", "--skill", "eks-recon"]), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                regression.main()
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--gate needs --task-result", err.getvalue())
        self.assertFalse(hasattr(regression, "gate_keys"))

    def test_step_summary_gets_the_report(self):
        summary = self.tmp / "summary.md"
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
        self.gate(self.outcome(gate_entry([gate_case(1, 3, 3)])))
        self.assertIn("# Eval Gate Report: eks-recon", summary.read_text())

class RegressionBaseArm(unittest.TestCase):
    """regression.py reads the base arm the runner names, so a
    base_skill run's benchmark (no without_skill arm) is not a KeyError."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-regr-"))
        self.latest = self.tmp / "eks-recon" / "workspace" / "latest"
        self.latest.mkdir(parents=True)
        self.root = mock.patch.object(regression, "EVALS_ROOT", self.tmp)
        self.root.start()

    def tearDown(self):
        self.root.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bench(self, arms):
        rs = {a: {"pass_rate": {"mean": m, "stddev": 0.1}} for a, m in arms.items()}
        (self.latest / "benchmark.json").write_text(json.dumps({"run_summary": rs}))

    def test_base_skill_benchmark(self):
        self.bench({"with_skill": 0.9, "base_skill": 0.7})
        task = regression.gather_from_workspace("eks-recon", 3)["task"]
        self.assertEqual(task["baseline_arm"], "base_skill")
        self.assertEqual(task["base_mean"], 0.7)
        self.assertIsNone(task["without_skill_mean"])

    def test_cases_json_names_the_arm(self):
        self.bench({"with_skill": 0.9, "base_skill": 0.7, "without_skill": 0.2})
        (self.latest / "cases.json").write_text(json.dumps({"base_arm": "without_skill"}))
        task = regression.gather_from_workspace("eks-recon", 3)["task"]
        self.assertEqual((task["baseline_arm"], task["base_mean"]), ("without_skill", 0.2))

    def test_old_without_skill_benchmark_unchanged(self):
        self.bench({"with_skill": 0.9, "without_skill": 0.5})
        task = regression.gather_from_workspace("eks-recon", 3)["task"]
        self.assertEqual((task["with_skill_mean"], task["without_skill_mean"]), (0.9, 0.5))

    def test_history_base_arm(self):
        hist = self.tmp / "history"
        hist.mkdir()
        row = {"kind": "task", "with_skill_mean": 0.9, "without_skill_mean": None,
               "baseline_arm": "base_skill", "base_skill_mean": 0.6}
        (hist / "eks-recon.jsonl").write_text(json.dumps(row) + "\n")
        with mock.patch.object(regression, "HISTORY_DIR", hist):
            task = regression.gather_from_history("eks-recon")["task"]
        self.assertEqual((task["baseline_arm"], task["base_mean"]), ("base_skill", 0.6))

    def test_history_skips_a_line_that_is_not_json(self):
        hist = self.tmp / "history"
        hist.mkdir()
        row = {"kind": "task", "with_skill_mean": 0.9, "baseline_arm": "base_skill",
               "base_skill_mean": 0.6}
        (hist / "eks-recon.jsonl").write_text(json.dumps(row) + "\n" + '{"kind": "tas')
        with mock.patch.object(regression, "HISTORY_DIR", hist), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            task = regression.gather_from_history("eks-recon")["task"]
        self.assertEqual(task["base_mean"], 0.6)
        self.assertIn("skipping a line that is not JSON", err.getvalue())


def snap_arm(mean):
    return {"pass_rate": {"mean": mean, "stddev": 0.1}}


class SnapshotBaseArm(unittest.TestCase):
    """snapshot.py reads the base arm the runner names (with_skill against
    base_skill or without_skill), as regression.py does."""

    def _bench(self, arms, cases_base_arm=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        latest = root / "demo" / "workspace" / "latest"
        latest.mkdir(parents=True)
        (latest / "benchmark.json").write_text(json.dumps({
            "run_summary": arms,
            "metadata": {"runs_per_configuration": 3}}))
        if cases_base_arm:
            (latest / "cases.json").write_text(json.dumps({"base_arm": cases_base_arm}))
        return root

    def _read(self, root):
        with mock.patch.object(snapshot, "EVALS_ROOT", root):
            return snapshot.read_task_benchmark("demo", 3)

    def test_base_skill_benchmark_snapshots_with_the_base_arm(self):
        root = self._bench({"with_skill": snap_arm(0.9), "base_skill": snap_arm(0.6)})
        task = self._read(root)
        self.assertEqual(task["with_skill_mean"], 0.9)
        self.assertEqual(task["baseline_arm"], "base_skill")
        self.assertEqual(task["base_mean"], 0.6)
        self.assertIsNone(task["without_skill_mean"])

    def test_cases_json_base_arm_names_the_arm(self):
        root = self._bench({"with_skill": snap_arm(0.9), "base_skill": snap_arm(0.6)},
                           cases_base_arm="base_skill")
        self.assertEqual(self._read(root)["baseline_arm"], "base_skill")

    def test_without_skill_benchmark_works_as_before(self):
        root = self._bench({"with_skill": snap_arm(0.8), "without_skill": snap_arm(0.4)})
        task = self._read(root)
        self.assertEqual(task["with_skill_mean"], 0.8)
        self.assertEqual(task["with_skill_stddev"], 0.1)
        self.assertEqual(task["without_skill_mean"], 0.4)
        self.assertEqual(task["baseline_arm"], "without_skill")
        self.assertEqual(task["base_mean"], 0.4)
        self.assertEqual(task["runs_per_prompt"], 3)


class EvalManifest(unittest.TestCase):
    """--check compares and writes nothing; each entry carries
    tokens_per_run from the latest task history row."""

    def setUp(self):
        import generate_eval_manifest as gem
        self.gem = gem
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-manifest-"))
        (self.tmp / "eks-recon" / "baselines").mkdir(parents=True)
        (self.tmp / "eks-recon" / "baselines" / "baseline.json").write_text(json.dumps(
            {"skill": "eks-recon", "composite": {"score": 80.0, "grade": "B"}, "task": {}}))
        (self.tmp / "history").mkdir()
        self.out = self.tmp / "evals.json"
        self.patches = [mock.patch.object(gem, "EVALS_ROOT", self.tmp),
                        mock.patch.object(gem, "HISTORY_DIR", self.tmp / "history"),
                        mock.patch.object(gem, "OUTPUT_PATH", self.out)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def main(self, *argv):
        with mock.patch.object(sys, "argv", ["generate_eval_manifest.py", *argv]), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                self.gem.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, err.getvalue()

    def test_tokens_per_run_from_history(self):
        hist = self.tmp / "history" / "eks-recon.jsonl"
        hist.write_text(json.dumps({"kind": "task", "with_skill_mean": 1.0}) + "\n")
        self.assertIsNone(self.gem.tokens_per_run("eks-recon"))
        entry = gate_entry([gate_case(1, 3, 3)])
        hist.write_text(hist.read_text() + json.dumps(entry) + "\n"
                        + json.dumps({"kind": "triggering"}) + "\n")
        self.assertEqual(self.gem.tokens_per_run("eks-recon"), 200)
        self.assertIsNone(self.gem.tokens_per_run("no-such-skill"))

    def test_bad_trailing_line_is_skipped_and_null_mean_stays_null(self):
        entry = gate_entry([gate_case(1, 3, 3)])
        (self.tmp / "history" / "eks-recon.jsonl").write_text(json.dumps(entry) + "\n" + '{"kind": "ta')
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.gem.tokens_per_run("eks-recon"), 200)
        self.assertIn("skipping a line that is not JSON", err.getvalue())
        entry["skill_summary"]["arms"]["with_skill"]["tokens_per_run_mean"] = None
        (self.tmp / "history" / "eks-recon.jsonl").write_text(json.dumps(entry) + "\n")
        self.assertIsNone(self.gem.tokens_per_run("eks-recon"))

    def test_check_both_ways_and_writes_nothing(self):
        code, err = self.main("--check")
        self.assertEqual(code, 1)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.main()[0], 0)
        self.assertIn('"tokens_per_run": null', self.out.read_text())
        self.assertEqual(self.main("--check")[0], 0)
        before = self.out.read_text()
        self.out.write_text(before.replace('"grade": "B"', '"grade": "A"'))
        stale = self.out.read_text()
        code, err = self.main("--check")
        self.assertEqual(code, 1)
        self.assertIn("eks-recon: differs in grade", err)
        self.assertEqual(self.out.read_text(), stale)


@unittest.skipUnless(shutil.which("make"), "make not installed")
class GateMakefile(unittest.TestCase):
    """The gate and task Makefile targets, by `make -n` (prints the commands, runs none)."""

    def make(self, *args, dry_run=True):
        return subprocess.run(["make"] + (["-n"] if dry_run else []) + ["--no-print-directory", "-C",
                               os.path.join(MISC_DIR, "evals"), *args],
                              capture_output=True, text=True, timeout=60)

    def test_gate_runs_stages_then_runner_then_gate(self):
        r = self.make("gate", "SKILL=eks-recon", "GATE_STAGES=echo stage-one; echo stage-two")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        marks = ["set -e; echo stage-one; echo stage-two",
                 "run_task_evals.py --skill eks-recon --harness claude",
                 "regression.py --gate --skill eks-recon --task-result"]
        self.assertEqual([out.index(m) for m in marks], sorted(out.index(m) for m in marks))
        self.assertNotIn("--runs", out)
        self.assertNotIn("--base-ref", out)  # empty BASE_REF: the runner's own default
        self.assertIn("no stage wired", self.make("gate-stages").stdout)

    def test_overrides_and_subject_model_per_harness(self):
        r = self.make("gate", "SKILL=eks-recon", "RUNS_PER_PROMPT=3", "HARNESS=codex", "BASE_REF=v1.2.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--harness codex --base-ref v1.2.0 --runs 3", r.stdout)
        self.assertIn("--model global.anthropic.claude-opus-4-6-v1", r.stdout)  # the grader
        self.assertNotIn("--subject-model", r.stdout)  # the runner's per-harness default
        r = self.make("gate", "SKILL=x", "SUBJECT_MODEL=m2")
        self.assertIn("--subject-model m2", r.stdout)

    def test_gate_needs_a_plain_skill(self):
        # Real runs: each check exits before any stage or runner line.
        r = self.make("gate", dry_run=False)
        self.assertEqual(r.returncode, 2)  # make's own exit for a failed recipe
        self.assertEqual(r.stdout.strip().splitlines(),
                         ["usage: make gate SKILL=<run key> [HARNESS=claude|kiro|codex] "
                          "[BASE_REF=<ref>] [RUNS_PER_PROMPT=<n>]"])
        for target in ("gate", "snapshot", "regression", "composite", "init-evals-finalize"):
            r = self.make(target, "SKILL=x; echo INJECTED; #", dry_run=False)
            self.assertEqual(r.returncode, 2, target)
            self.assertNotIn("INJECTED", r.stdout.replace("echo INJECTED", ""), target)
            self.assertIn("SKILL must match", r.stdout, target)

    def test_task_and_triggering_take_base_ref_and_harness(self):
        r = self.make("task-eks-recon", "BASE_REF=v1.2.0")
        self.assertIn("--base-ref v1.2.0", r.stdout)
        self.assertNotIn("--runs", r.stdout)
        r = self.make("triggering-eks-recon", "HARNESS=codex")
        self.assertIn("--harness codex", r.stdout)
        self.assertIn("--subject-model m2", self.make("triggering-eks-recon", "SUBJECT_MODEL=m2").stdout)

    def test_gate_all_lists_runnable_targets_and_gates_each(self):
        r = self.make("gate-all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"run_task_evals\.py --list-targets +\| python3 -c")
        self.assertNotIn("--gate-keys", r.stdout)
        self.assertIn("run_task_evals.py --list-targets --include-live-only",
                      self.make("gate-all", "INCLUDE_LIVE_ONLY=1").stdout)
        self.assertIn("regression.py --gate --skill $k", r.stdout)

    def test_only_bedrock_provider(self):
        r = self.make("help", "PROVIDER=anthropic")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PROVIDER must be 'bedrock', got 'anthropic'", r.stderr)


class EvalGateWorkflow(unittest.TestCase):
    """The eval-gate job: dispatch-only, claude and codex, secrets only on
    the steps that read them, no Kiro key, pinned CLIs."""

    def setUp(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        self.text = (REPO / ".github" / "workflows" / "evals.yml").read_text()
        self.wf = yaml.safe_load(self.text)
        self.job = self.wf["jobs"]["eval-gate"]

    def test_dispatch_only_matrix_without_kiro(self):
        self.assertEqual(self.job["if"], "github.event_name == 'workflow_dispatch'")
        self.assertEqual(self.job["strategy"]["matrix"]["harness"], ["claude", "codex"])
        self.assertNotIn("KIRO_API_KEY", self.text)
        self.assertNotIn("harness", self.wf[True]["workflow_dispatch"]["inputs"])  # `on:` loads as True

    def test_secrets_only_on_the_steps_that_read_them(self):
        self.assertNotIn("env", self.job)
        with_secret = [s.get("name") for s in self.job["steps"] if "secrets." in json.dumps(s)]
        self.assertEqual(with_secret, ["Require the eval secrets", "Write the eval-role config"])
        checkout = self.job["steps"][0]
        self.assertIs(checkout["with"]["persist-credentials"], False)

    def test_pinned_clis(self):
        install = next(s for s in self.job["steps"] if s.get("name") == "Install the eval tools")
        self.assertIn("@anthropic-ai/claude-code@2.1.121", install["run"])
        self.assertIn("@openai/codex@0.163.0", install["run"])

    def test_a_dispatched_run_is_not_cancelled(self):
        c = self.wf["concurrency"]
        self.assertIn("github.event_name", c["group"])
        self.assertEqual(c["cancel-in-progress"], "${{ github.event_name != 'workflow_dispatch' }}")


class CliVersionCheck(unittest.TestCase):
    """Both runners read `<cli> --version` and stop on a version other than
    the one the adapter was written against, or on a missing CLI."""

    def setUp(self):
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.dict(os.environ, {"PATH": self.bin}))
        for m in (run_triggering, run_task_evals):
            stack.enter_context(mock.patch.object(m, "check_cli_versions", REAL_CHECK_CLI_VERSIONS))
        self.runs = stack.enter_context(
            mock.patch.object(subprocess, "run", wraps=subprocess.run))

    def cli(self, name, version_line):
        fake_exe(self.bin, name, [version_line])

    def assert_only_version_reads(self):
        self.assertTrue(self.runs.call_args_list)
        for call in self.runs.call_args_list:
            self.assertEqual(call.args[0][1:], ["--version"])

    def test_matching_versions_pass(self):
        self.cli("claude", "2.1.121 (Claude Code)")
        self.cli("codex", "codex-cli 0.163.0")
        self.cli("kiro-cli", "kiro-cli 3.4.0")
        self.assertIsNone(REAL_CHECK_CLI_VERSIONS(["claude", "codex", "kiro"]))

    def test_a_missing_cli_stops(self):
        err = REAL_CHECK_CLI_VERSIONS(["kiro"])
        self.assertIn("kiro-cli --version", err)
        self.assertIn("3.4.0", err)

    def test_a_different_version_stops_triggering_before_any_run(self):
        self.cli("claude", "2.1.328 (Claude Code)")
        skill = str(run_triggering.REPO_ROOT / "skills" / SKILL)
        eval_set = str(run_triggering.REPO_ROOT / "misc" / "evals" / SKILL / "triggering.json")
        argv = ["run_triggering.py", "--eval-set", eval_set, "--skill-path", skill]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(run_triggering, "mint_eval_role_credentials") as mint, \
                mock.patch.object(run_triggering, "run_eval") as run_eval, \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_triggering.main(), 2)
        self.assertIn("claude 2.1.328 is installed", err.getvalue())
        self.assertIn("claude 2.1.121", err.getvalue())
        mint.assert_not_called()
        run_eval.assert_not_called()
        self.assert_only_version_reads()

    def test_a_different_version_stops_task_evals_before_any_run(self):
        self.cli("claude", "2.1.121 (Claude Code)")
        self.cli("codex", "codex-cli 0.170.0")
        argv = ["run_task_evals.py", "--skill", "eks-recon", "--harness", "codex",
                "--model", "grader-id", "--base-ref", "none"]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(run_task_evals, "mint_eval_role_credentials") as mint, \
                mock.patch.object(run_task_evals, "run_skill") as run_skill, \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_task_evals.main(), 2)
        self.assertIn("codex 0.170.0 is installed", err.getvalue())
        mint.assert_not_called()
        run_skill.assert_not_called()
        self.assert_only_version_reads()

    def test_expected_versions_match_the_ci_pins(self):
        text = (REPO / ".github" / "workflows" / "evals.yml").read_text()
        versions = run_triggering.HARNESS_CLI_VERSIONS
        self.assertIn(f"@anthropic-ai/claude-code@{versions['claude'][1]}", text)
        self.assertIn(f"@openai/codex@{versions['codex'][1]}", text)


if __name__ == "__main__":
    unittest.main()
