"""Offline tests for misc/evals/scripts/elicitation.py.

Run from the repo root: python3 -m pytest misc/tests/test_elicitation.py
(or python3 -m unittest misc.tests.test_elicitation). No model calls: the
subject is a small Python script standing in for the harness CLI.
"""

from __future__ import annotations

import json
import os
import shutil
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

        # The real shape (elicitation.py run_multiturn_subject): the resumed
        # turn's first event is its system/init, and it carries the answer.
        events = [
            {"type": "system", "subtype": "init", "skills": ["eks-build"]},
            _assistant({"type": "text", "text": "Which region?"}),
            {"type": "result"},
            {"type": "system", "subtype": "init", "skills": ["eks-build"],
             "elicitation_answer": "us-west-2"},
            _assistant({"type": "text", "text": "Using us-west-2."}),
            {"type": "result"},
        ]
        out = run_task_evals.format_transcript(events, "build it", "eks-build")
        line = "**Eval harness reply (canned user answer):** us-west-2"
        self.assertEqual(out.count(line), 1)
        self.assertLess(out.index("Which region?"), out.index(line))
        second_init = out.index("_system/init", out.index("Which region?"))
        self.assertLess(out.index(line), second_init)
        self.assertLess(second_init, out.index("Using us-west-2."))

    def test_format_transcript_no_answer_no_line(self):
        import run_task_evals

        events = [_assistant({"type": "text", "text": "Which region?"}), {"type": "result"}]
        out = run_task_evals.format_transcript(events, "build it", "eks-build")
        self.assertNotIn("Eval harness reply", out)

    def test_detect_pending_question_keeps_its_signature(self):
        # misc/runner-trial/drive_c1.py imports it by name with one argument.
        self.assertTrue(callable(elicitation.detect_pending_question))
        self.assertIsNone(elicitation.detect_pending_question([]))


# Stand-ins for kiro-cli and codex: each logs its argv, then prints its
# harness's raw JSON Lines (parse_trajectory.py, harness shapes). Turn 1 asks
# in plain text; a resumed turn echoes the answer, its last argument.
KIRO_SUBJECT = textwrap.dedent(
    """
    import json, sys
    args = sys.argv[1:]
    with open(sys.argv[0] + ".argv", "a") as f:
        f.write(json.dumps(args) + "\\n")
    text = args[-1]
    if "--resume" in args:
        reply = "Building in " + text + "."
    else:
        reply = "I can build this.\\n\\nWhich AWS region should it run in?"
    upd = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": reply}}
    for evt in ({"type": "runStarted"}, {"update": upd}, {"type": "runFinished"}):
        print(json.dumps(evt), flush=True)
    """
)

CODEX_SUBJECT = textwrap.dedent(
    """
    import json, sys
    args = sys.argv[1:]
    with open(sys.argv[0] + ".argv", "a") as f:
        f.write(json.dumps(args) + "\\n")
    text = args[-1]
    resume = args[:2] == ["exec", "resume"]
    if resume:
        reply, usage = "Building in " + text + ".", {"input_tokens": 20, "output_tokens": 3}
    else:
        reply, usage = "I can build this.\\n\\nWhich AWS region should it run in?", {"input_tokens": 10, "output_tokens": 2}
    item = {"type": "agent_message", "text": reply}
    for evt in ({"type": "thread.started", "thread_id": THREAD},
                {"type": "item.completed", "item": item},
                {"type": "turn.completed", "usage": usage}):
        print(json.dumps(evt), flush=True)
    """
)

CANNED_REGION = {
    "strategy": "canned-multiturn",
    "turns": [{"question_match": "region", "answer": "us-west-2"}],
    "max_turns": 3,
}


class HarnessResume(unittest.TestCase):
    """The kiro and codex resume forms (run_task_evals.harness_turn_cmd),
    run against stand-in CLIs: the CLI name is swapped for the script and
    every other argument is the runner's own."""

    def _run(self, harness: str, source: str):
        import run_task_evals

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        script = Path(tmp) / "subject.py"
        script.write_text(source)
        turn_cmd = run_task_evals.harness_turn_cmd(
            harness, model="m", sandbox=Path(tmp), env={},
            wrap=lambda c: [sys.executable, str(script)] + c[1:])
        events, timed_out, sid = run_multiturn_subject(
            initial_prompt="build me a cluster",
            elicitation=ElicitationConfig.from_dict(CANNED_REGION),
            cwd=tmp,
            env_for_turn=lambda: dict(os.environ),
            timeout_per_turn=5,
            turn_cmd=turn_cmd,
            normalize=lambda evts: run_task_evals.normalize_events(evts, harness),
        )
        argv = [json.loads(line) for line in Path(str(script) + ".argv").read_text().splitlines()]
        return run_task_evals, events, timed_out, sid, argv

    def test_kiro_resumes_with_resume_flag(self):
        rte, events, timed_out, sid, argv = self._run("kiro", KIRO_SUBJECT)
        self.assertFalse(timed_out)
        self.assertEqual(len(argv), 2)
        self.assertEqual(argv[0][:1], ["chat"])
        self.assertNotIn("--resume", argv[0])
        self.assertEqual(argv[1][-2:], ["--resume", "us-west-2"])
        self.assertEqual(argv[0][:-1], argv[1][:-2])
        norm = rte.normalize_turns(events, "kiro")
        self.assertEqual([e.get("elicitation_answer") for e in norm if "elicitation_answer" in e],
                         ["us-west-2"])
        texts = [c["text"] for e in norm if e.get("type") == "assistant"
                 for c in e["message"]["content"] if c.get("type") == "text"]
        self.assertTrue(texts[-1].startswith("Building in us-west-2"))
        self.assertIsNone(rte.stream_invalid_reason(events, "kiro"))
        out = rte.format_transcript(norm, "build me a cluster", "eks-build")
        self.assertEqual(out.count("**Eval harness reply (canned user answer):** us-west-2"), 1)

    def test_codex_resumes_by_thread_id(self):
        rte, events, timed_out, sid, argv = self._run(
            "codex", CODEX_SUBJECT.replace("THREAD", repr("t-1")))
        self.assertFalse(timed_out)
        self.assertEqual(sid, "t-1")
        self.assertEqual(len(argv), 2)
        self.assertEqual(argv[0][0], "exec")
        self.assertNotIn("--ephemeral", argv[0])
        self.assertIn("-C", argv[0])
        self.assertEqual(argv[1][:2], ["exec", "resume"])
        self.assertNotIn("-C", argv[1])
        self.assertEqual(argv[1][-2:], ["t-1", "us-west-2"])
        norm = rte.normalize_turns(events, "codex")
        self.assertEqual([e.get("elicitation_answer") for e in norm if "elicitation_answer" in e],
                         ["us-west-2"])
        result = [e for e in norm if e.get("type") == "result"][-1]
        self.assertEqual(result["usage"]["input_tokens"], 30)
        self.assertEqual(result["usage"]["output_tokens"], 5)
        self.assertEqual(result["num_turns"], 2)

    def test_codex_with_no_thread_id_runs_one_turn(self):
        rte, events, timed_out, sid, argv = self._run(
            "codex", CODEX_SUBJECT.replace("THREAD", "None"))
        self.assertFalse(timed_out)
        self.assertIsNone(sid)
        self.assertEqual(len(argv), 1)

    def test_single_turn_normalize_matches_normalize_events(self):
        import run_task_evals as rte

        raw = [{"type": "thread.started", "thread_id": "t"},
               {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
               {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}]
        self.assertEqual(rte.normalize_turns(raw, "codex"), rte.normalize_events(raw, "codex"))


if __name__ == "__main__":
    unittest.main()
