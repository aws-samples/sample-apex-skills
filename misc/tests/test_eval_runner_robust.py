#!/usr/bin/env python3
"""Tests for eval runner input handling: event lines that are not JSON
objects, tool calls with no input, fixture files leaking into the graded
outputs, and validators that pass with nothing to check.

No test calls a model or starts a `claude` process. The two stream readers
are fed by a child Python process that only prints fixed lines.

Run directly with:

    python3 -B misc/tests/test_eval_runner_robust.py
"""

import json
import os
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
from elicitation import drain_stream_for_events  # noqa: E402
from parse_trajectory import parse_events, parse_events_file  # noqa: E402
from run_knowledge_assertions import extract_assistant_text  # noqa: E402
from run_task_evals import (  # noqa: E402
    drain_stream,
    snapshot_sandbox_outputs,
    stage_fixture_files,
)
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

    def test_parse_events_skips_non_dict_content_blocks(self):
        user = {"type": "user", "message": {"content": [
            "junk", {"type": "tool_result", "content": "ok"}]}}
        traj = parse_events([assistant("junk", tool_use("Read", input={})), user])
        self.assertEqual(traj.total_tool_calls, 1)
        self.assertEqual(traj.steps[0].tool_calls[0].result, "ok")

    def test_parse_events_file_counts_non_object_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('[1, 2]\n"s"\n'
                            + json.dumps(assistant(tool_use("Read", input={}))) + "\n")
            traj = parse_events_file(path)
        self.assertEqual(traj.skipped_events, 2)
        self.assertEqual(traj.total_tool_calls, 1)

    def test_knowledge_text_reader_skips_non_object_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('[1]\n'
                            + json.dumps(assistant("junk", {"type": "text", "text": "hi"}))
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

    def test_args_match_skips_missing_input_and_matches_real_input(self):
        spec = [{"type": "tool-called", "tool": "Bash", "args_match": {"command": "ls"}}]
        traj = parse_events([assistant(tool_use("Bash"),
                                       tool_use("Bash", input={"command": "ls"}))])
        res = process_assertions.evaluate(traj, spec)
        self.assertTrue(res.results[0].passed)
        self.assertEqual(res.results[0].matching_calls, [1])
        missing = process_assertions.evaluate(parse_events([assistant(tool_use("Bash"))]), spec)
        self.assertFalse(missing.results[0].passed)
        self.assertEqual(missing.results[0].failure_class, "missed_tool")

    def test_schema_check_fails_missing_input_and_passes_empty_input(self):
        schema = {"type": "object", "required": []}
        with mock.patch.object(process_assertions, "_HAS_JSONSCHEMA", False):
            missing = process_assertions.evaluate(
                parse_events([assistant(tool_use("T"))]),
                [{"type": "tool-args-schema", "tool": "T", "schema": schema}])
            empty = process_assertions.evaluate(
                parse_events([assistant(tool_use("T", input={}))]),
                [{"type": "tool-args-schema", "tool": "T", "schema": schema}])
        self.assertFalse(missing.results[0].passed)
        self.assertTrue(empty.results[0].passed)

    def test_schema_fallback_with_required_key_and_missing_input(self):
        with mock.patch.object(process_assertions, "_HAS_JSONSCHEMA", False):
            self.assertFalse(process_assertions._validate_against_schema(
                None, {"required": ["path"]}))


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


if __name__ == "__main__":
    unittest.main()
