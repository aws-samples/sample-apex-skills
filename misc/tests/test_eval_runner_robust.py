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
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Make misc/evals/scripts importable regardless of CWD.
MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(MISC_DIR, "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import artifact_validation  # noqa: E402
import process_assertions  # noqa: E402
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
import elicitation  # noqa: E402
from run_triggering import _handle_line  # noqa: E402


def tool_use(name, **extra):
    block = {"type": "tool_use", "name": name}
    block.update(extra)
    return block


def assistant(*blocks):
    return {"type": "assistant", "message": {"content": list(blocks)}}


def printer(lines):
    """A child process that prints `lines` and exits; never claude."""
    code = "import sys\nfor l in %r:\n    sys.stdout.write(l + '\\n')\n" % (lines,)
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)


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


if __name__ == "__main__":
    unittest.main()
