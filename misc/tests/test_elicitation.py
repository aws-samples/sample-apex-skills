"""Offline tests for misc/evals/scripts/elicitation.py.

Run from the repo root: python3 -m pytest misc/tests/test_elicitation.py
(or python3 -m unittest misc.tests.test_elicitation). No model calls: the
subject is a small Python script standing in for the harness CLI.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "evals" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import elicitation  # noqa: E402
from elicitation import (  # noqa: E402
    ElicitationConfig,
    detect_pending_question,
    run_multiturn_subject,
)


def _assistant(*content: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(content)}}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


class DetectPendingQuestion(unittest.TestCase):
    def test_ask_user_question_tool_call(self):
        events = [
            _assistant(
                _text("Before I start:"),
                {
                    "type": "tool_use",
                    "name": "AskUserQuestion",
                    "input": {"questions": [{"question": "Which region?"}]},
                },
            )
        ]
        self.assertEqual(detect_pending_question(events), "Which region?")

    def test_plain_text_question_ends_the_run(self):
        # eks-build, eks-design and eks-mcp-server ask in plain text.
        events = [
            _assistant(_text("I can build this cluster.\n\nWhich AWS region should it run in?")),
            {"type": "result", "session_id": "s"},
        ]
        self.assertEqual(
            detect_pending_question(events), "Which AWS region should it run in?"
        )

    def test_plain_text_without_question_is_not_a_question(self):
        events = [_assistant(_text("Here is the design.\n\nIt is complete."))]
        self.assertIsNone(detect_pending_question(events))

    def test_question_in_an_earlier_paragraph_only_is_not_pending(self):
        events = [_assistant(_text("Why Karpenter? It scales fast.\n\nThe plan is done."))]
        self.assertIsNone(detect_pending_question(events))

    def test_question_ending_on_a_url_is_detected(self):
        text = "Plan ready.\n\nShould I pin it to https://example.com/v2?"
        self.assertEqual(
            detect_pending_question([_assistant(_text(text))]),
            "Should I pin it to https://example.com/v2?",
        )

    def test_question_mark_in_a_fenced_block_is_not_a_question(self):
        text = (
            "Here is the node group module:\n\n```hcl\n"
            '  instance_types = ["m5.xlarge"]\n\n'
            '  desired_size = var.environment == "prod" ? 3 : 1\n```'
        )
        self.assertIsNone(detect_pending_question([_assistant(_text(text))]))

    def test_question_mark_in_a_url_is_not_a_question(self):
        text = (
            "Done. Apply with terraform apply.\n\nReference: "
            "https://docs.aws.amazon.com/eks/latest/userguide/network-reqs.html?icmpid=docs"
        )
        self.assertIsNone(detect_pending_question([_assistant(_text(text))]))

    def test_question_mark_in_inline_code_is_not_a_question(self):
        text = (
            "Pattern used for the check:\n\n"
            "`(?<![a-z_])permissions_boundary_arn` matches the node module input."
        )
        self.assertIsNone(detect_pending_question([_assistant(_text(text))]))

    def test_only_the_final_assistant_message_counts(self):
        events = [
            _assistant(_text("Which region?")),
            _assistant({"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}),
        ]
        self.assertIsNone(detect_pending_question(events))


STDERR_FLOOD_SUBJECT = textwrap.dedent(
    """
    import json, sys
    # More than a pipe buffer holds (64 KiB on Linux), written before any
    # stdout line, as a chatty CLI can on stderr.
    sys.stderr.write("x" * (1024 * 1024))
    sys.stderr.flush()
    print(json.dumps({"type": "result", "session_id": "s", "result": "ok"}), flush=True)
    """
)


ASK_THEN_ANSWER_SUBJECT = textwrap.dedent(
    """
    import json, sys
    # Turn 1 (-p <prompt> --session-id <id>) asks in plain text; a resumed turn
    # (-p <answer> --resume <id>) echoes the answer it was given.
    args = sys.argv[1:]
    text = args[args.index("-p") + 1]
    if "--resume" in args:
        reply = "Building in " + text + "."
    else:
        reply = "I can build this.\\n\\nWhich AWS region should it run in?"
    msg = {"content": [{"type": "text", "text": reply}]}
    print(json.dumps({"type": "assistant", "message": msg}), flush=True)
    print(json.dumps({"type": "result", "session_id": "s"}), flush=True)
    """
)


class MultiturnSubjectProcess(unittest.TestCase):
    def test_stderr_flood_does_not_stall_the_turn(self):
        # The runner reads only stdout. An unread stderr pipe fills and blocks
        # the subject until the turn times out.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "subject.py"
            script.write_text(STDERR_FLOOD_SUBJECT)
            start = time.time()
            events, timed_out, _ = run_multiturn_subject(
                initial_prompt="hello",
                elicitation=ElicitationConfig.from_dict(None),
                cmd_base=[sys.executable, str(script)],
                cwd=tmp,
                env_for_turn=lambda: dict(os.environ),
                timeout_per_turn=5,
            )
            self.assertFalse(timed_out, "the subject stalled on a full stderr pipe")
            self.assertLess(time.time() - start, 5)
            self.assertEqual([e.get("type") for e in events], ["result"])

    def test_injected_answer_is_recorded_in_the_events(self):
        # The runner records the canned answer on the resumed turn's first event; no grader reads it yet.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "subject.py"
            script.write_text(ASK_THEN_ANSWER_SUBJECT)
            events, timed_out, _ = run_multiturn_subject(
                initial_prompt="build me a cluster",
                elicitation=ElicitationConfig.from_dict({
                    "strategy": "canned-multiturn",
                    "turns": [{"question_match": "region", "answer": "us-west-2"}],
                    "max_turns": 3,
                }),
                cmd_base=[sys.executable, str(script)],
                cwd=tmp,
                env_for_turn=lambda: dict(os.environ),
                timeout_per_turn=5,
            )
            self.assertFalse(timed_out)
            self.assertEqual(
                [e.get("type") for e in events],
                ["assistant", "result", "assistant", "result"],
            )
            self.assertEqual(
                [e.get("elicitation_answer") for e in events],
                [None, None, "us-west-2", None],
            )
            self.assertIn("us-west-2", events[2]["message"]["content"][0]["text"])

    def test_format_transcript_shows_canned_answer(self):
        import run_task_evals

        events = [
            _assistant({"type": "text", "text": "Which region?"}),
            {"type": "result"},
            {**_assistant({"type": "text", "text": "Using us-west-2."}),
             "elicitation_answer": "us-west-2"},
            {"type": "result"},
        ]
        out = run_task_evals.format_transcript(events, "build it", "eks-build")
        line = "**Canned answer sent:** us-west-2"
        self.assertEqual(out.count(line), 1)
        self.assertLess(out.index("Which region?"), out.index(line))
        self.assertLess(out.index(line), out.index("Using us-west-2."))

    def test_format_transcript_no_answer_no_line(self):
        import run_task_evals

        events = [_assistant({"type": "text", "text": "Which region?"}), {"type": "result"}]
        out = run_task_evals.format_transcript(events, "build it", "eks-build")
        self.assertNotIn("Canned answer sent", out)

    def test_detect_pending_question_keeps_its_signature(self):
        # misc/runner-trial/drive_c1.py imports it by name with one argument.
        self.assertTrue(callable(elicitation.detect_pending_question))
        self.assertIsNone(elicitation.detect_pending_question([]))


if __name__ == "__main__":
    unittest.main()
