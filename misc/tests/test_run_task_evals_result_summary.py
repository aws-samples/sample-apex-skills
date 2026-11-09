#!/usr/bin/env python3
"""Tests that extract_result_summary reads the last `result` event.

A multi-turn eval run emits one `result` event per turn, and the last one
carries the counts the run records. Every case in
test_parse_trajectory_tokens.py feeds a single result event, so it cannot
tell the last event from the first.

Run directly with:

    python3 misc/tests/test_run_task_evals_result_summary.py
"""

import os
import sys
import unittest

# Make misc/evals/scripts importable regardless of CWD.
MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(MISC_DIR, "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from run_task_evals import extract_result_summary  # noqa: E402

FIRST_RESULT = {
    "type": "result",
    "subtype": "success",
    "duration_ms": 1000,
    "num_turns": 1,
    "usage": {"input_tokens": 10, "output_tokens": 5},
    "modelUsage": {"model-a": {"inputTokens": 100, "outputTokens": 50}},
}

LAST_RESULT = {
    "type": "result",
    "subtype": "error_max_turns",
    "duration_ms": 4000,
    "num_turns": 3,
    "usage": {"input_tokens": 30, "output_tokens": 12},
    "modelUsage": {"model-a": {"inputTokens": 900, "outputTokens": 400}},
}


class LastResultEventTests(unittest.TestCase):
    def test_last_result_event_wins(self):
        events = [
            {"type": "system", "subtype": "init"},
            FIRST_RESULT,
            {"type": "user"},
            {"type": "assistant"},
            LAST_RESULT,
        ]
        s = extract_result_summary(events)
        self.assertEqual(s["duration_ms"], 4000)
        self.assertEqual(s["num_turns"], 3)
        self.assertEqual(s["subtype"], "error_max_turns")
        self.assertEqual(s["total_tokens"], 42)
        self.assertEqual(s["token_source"], "modelUsage")
        self.assertEqual(s["input_tokens"], 900)
        self.assertEqual(s["output_tokens"], 400)

    def test_events_after_the_last_result_are_ignored(self):
        s = extract_result_summary([FIRST_RESULT, LAST_RESULT, {"type": "assistant"}])
        self.assertEqual(s["duration_ms"], 4000)
        self.assertEqual(s["input_tokens"], 900)


if __name__ == "__main__":
    unittest.main()
