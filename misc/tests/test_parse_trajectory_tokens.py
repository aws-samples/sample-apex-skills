#!/usr/bin/env python3
"""Tests for the per-category token counts parsed from eval trajectories.

Run directly with:

    python3 misc/tests/test_parse_trajectory_tokens.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make misc/evals/scripts importable regardless of CWD.
MISC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(MISC_DIR, "evals", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from parse_trajectory import USAGE_TOKEN_KEYS, parse_events  # noqa: E402
from run_task_evals import (  # noqa: E402
    aggregate_token_usage,
    extract_result_summary,
)

# Shape of a Claude Code stream-json `result` event's usage object.
FULL_USAGE = {
    "input_tokens": 7,
    "cache_creation_input_tokens": 10262,
    "cache_read_input_tokens": 33441,
    "output_tokens": 917,
    "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
    "service_tier": "standard",
    "cache_creation": {
        "ephemeral_1h_input_tokens": 0,
        "ephemeral_5m_input_tokens": 10262,
    },
}

# An older usage object with no cache keys.
LEGACY_USAGE = {"input_tokens": 120, "output_tokens": 30}

# A run that spawned a subagent: `usage` counts only the top-level loop,
# `modelUsage` counts the whole tree, one entry per model.
SUBAGENT_USAGE = {
    "input_tokens": 20,
    "cache_creation_input_tokens": 133484,
    "cache_read_input_tokens": 79001,
    "output_tokens": 12345,
}
SUBAGENT_MODEL_USAGE = {
    "model-small": {
        "inputTokens": 400,
        "outputTokens": 16,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "costUSD": 0.0005,
    },
    "model-large": {
        "inputTokens": 13929,
        "outputTokens": 48757,
        "cacheReadInputTokens": 938453,
        "cacheCreationInputTokens": 322780,
        "costUSD": 3.78,
    },
}

# `modelUsage` with no readable entry: a non-dict entry and one with
# snake_case keys. The counts should come from `usage` instead.
UNREADABLE_MODEL_USAGE = {
    "model-a": 5,
    "model-b": {"input_tokens": 99, "output_tokens": 99},
}

# A string count, which should read as 0 rather than raise.
STRING_MODEL_USAGE = {
    "model-a": {
        "inputTokens": "56",
        "outputTokens": 10,
        "cacheReadInputTokens": 100,
        "cacheCreationInputTokens": 0,
    },
}


def _events(usage, model_usage=None):
    result = {
        "type": "result",
        "subtype": "success",
        "duration_ms": 1234,
        "num_turns": 1,
        "usage": usage,
    }
    if model_usage is not None:
        result["modelUsage"] = model_usage
    return [
        {"type": "system", "subtype": "init"},
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "done"}]},
        },
        result,
    ]


class ParseEventsTokenTests(unittest.TestCase):
    def test_full_usage_reports_each_category(self):
        t = parse_events(_events(FULL_USAGE))
        self.assertEqual(t.input_tokens, 7)
        self.assertEqual(t.output_tokens, 917)
        self.assertEqual(t.cache_read_input_tokens, 33441)
        self.assertEqual(t.cache_creation_input_tokens, 10262)
        # total_tokens keeps its meaning: input + output only.
        self.assertEqual(t.total_tokens, 7 + 917)
        d = t.to_dict()
        for key in USAGE_TOKEN_KEYS:
            self.assertIn(key, d)
        self.assertEqual(d["cache_read_input_tokens"], 33441)

    def test_usage_without_cache_keys_reads_zero(self):
        t = parse_events(_events(LEGACY_USAGE))
        self.assertEqual(t.input_tokens, 120)
        self.assertEqual(t.output_tokens, 30)
        self.assertEqual(t.cache_read_input_tokens, 0)
        self.assertEqual(t.cache_creation_input_tokens, 0)
        self.assertEqual(t.total_tokens, 150)

    def test_no_result_event_leaves_counts_none(self):
        t = parse_events(_events(FULL_USAGE)[:2])
        self.assertIsNone(t.total_tokens)
        for key in USAGE_TOKEN_KEYS:
            self.assertIsNone(getattr(t, key))
        self.assertIsNone(t.token_source)

    def test_model_usage_preferred_over_usage(self):
        t = parse_events(_events(SUBAGENT_USAGE, SUBAGENT_MODEL_USAGE))
        self.assertEqual(t.token_source, "modelUsage")
        self.assertEqual(t.input_tokens, 400 + 13929)
        self.assertEqual(t.output_tokens, 16 + 48757)
        self.assertEqual(t.cache_read_input_tokens, 938453)
        self.assertEqual(t.cache_creation_input_tokens, 322780)
        # modelUsage exceeds the top-level usage object.
        self.assertGreater(
            t.cache_read_input_tokens, SUBAGENT_USAGE["cache_read_input_tokens"]
        )
        # total_tokens keeps its source: usage input + output.
        self.assertEqual(t.total_tokens, 20 + 12345)
        self.assertEqual(t.to_dict()["token_source"], "modelUsage")

    def test_no_model_usage_falls_back_to_usage(self):
        t = parse_events(_events(FULL_USAGE))
        self.assertEqual(t.token_source, "usage")
        self.assertEqual(t.cache_read_input_tokens, 33441)

    def test_empty_model_usage_falls_back_to_usage(self):
        t = parse_events(_events(FULL_USAGE, {}))
        self.assertEqual(t.token_source, "usage")
        self.assertEqual(t.input_tokens, 7)

    def test_unreadable_model_usage_falls_back_to_usage(self):
        t = parse_events(_events(FULL_USAGE, UNREADABLE_MODEL_USAGE))
        self.assertEqual(t.token_source, "usage")
        self.assertEqual(t.input_tokens, 7)
        self.assertEqual(t.cache_read_input_tokens, 33441)

    def test_string_count_reads_zero(self):
        t = parse_events(_events(FULL_USAGE, STRING_MODEL_USAGE))
        self.assertEqual(t.token_source, "modelUsage")
        self.assertEqual(t.input_tokens, 0)
        self.assertEqual(t.output_tokens, 10)
        self.assertEqual(t.cache_read_input_tokens, 100)


class ExtractResultSummaryTests(unittest.TestCase):
    def test_full_usage(self):
        s = extract_result_summary(_events(FULL_USAGE))
        self.assertEqual(s["total_tokens"], 7 + 917)
        self.assertEqual(s["input_tokens"], 7)
        self.assertEqual(s["output_tokens"], 917)
        self.assertEqual(s["cache_read_input_tokens"], 33441)
        self.assertEqual(s["cache_creation_input_tokens"], 10262)
        self.assertEqual(s["duration_ms"], 1234)

    def test_usage_without_cache_keys(self):
        s = extract_result_summary(_events(LEGACY_USAGE))
        self.assertEqual(s["total_tokens"], 150)
        self.assertEqual(s["cache_read_input_tokens"], 0)
        self.assertEqual(s["cache_creation_input_tokens"], 0)

    def test_no_result_event(self):
        s = extract_result_summary([])
        self.assertEqual(s["total_tokens"], 0)
        for key in USAGE_TOKEN_KEYS:
            self.assertEqual(s[key], 0)
        self.assertIsNone(s["token_source"])

    def test_model_usage_preferred_over_usage(self):
        s = extract_result_summary(_events(SUBAGENT_USAGE, SUBAGENT_MODEL_USAGE))
        self.assertEqual(s["token_source"], "modelUsage")
        self.assertEqual(s["input_tokens"], 400 + 13929)
        self.assertEqual(s["output_tokens"], 16 + 48757)
        self.assertEqual(s["cache_read_input_tokens"], 938453)
        self.assertEqual(s["cache_creation_input_tokens"], 322780)
        self.assertEqual(s["total_tokens"], 20 + 12345)

    def test_no_model_usage_falls_back_to_usage(self):
        s = extract_result_summary(_events(FULL_USAGE))
        self.assertEqual(s["token_source"], "usage")
        self.assertEqual(s["cache_read_input_tokens"], 33441)
        self.assertEqual(s["cache_creation_input_tokens"], 10262)

    def test_unreadable_model_usage_falls_back_to_usage(self):
        s = extract_result_summary(_events(FULL_USAGE, UNREADABLE_MODEL_USAGE))
        self.assertEqual(s["token_source"], "usage")
        self.assertEqual(s["input_tokens"], 7)
        self.assertEqual(s["cache_read_input_tokens"], 33441)

    def test_string_count_reads_zero(self):
        s = extract_result_summary(_events(FULL_USAGE, STRING_MODEL_USAGE))
        self.assertEqual(s["token_source"], "modelUsage")
        self.assertEqual(s["input_tokens"], 0)
        self.assertEqual(s["output_tokens"], 10)
        self.assertEqual(s["cache_read_input_tokens"], 100)


class AggregateTokenUsageTests(unittest.TestCase):
    def _write_timing(self, root, config, eval_id, run, timing):
        run_dir = root / f"eval-{eval_id}" / config / f"run-{run}"
        run_dir.mkdir(parents=True)
        (run_dir / "timing.json").write_text(json.dumps(timing))

    def test_sums_and_means_per_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            full = extract_result_summary(_events(FULL_USAGE))
            legacy = extract_result_summary(_events(LEGACY_USAGE))
            self._write_timing(root, "with_skill", 1, 1, full)
            self._write_timing(root, "with_skill", 2, 1, legacy)
            # A timing.json written before the split: total_tokens only.
            self._write_timing(
                root, "without_skill", 1, 1, {"total_tokens": 40, "duration_ms": 5}
            )

            agg = aggregate_token_usage(root)

            ws = agg["with_skill"]
            self.assertEqual(ws["runs"], 2)
            self.assertEqual(ws["total"]["total_tokens"], 924 + 150)
            self.assertEqual(ws["total"]["input_tokens"], 127)
            self.assertEqual(ws["total"]["output_tokens"], 947)
            self.assertEqual(ws["total"]["cache_read_input_tokens"], 33441)
            self.assertEqual(ws["total"]["cache_creation_input_tokens"], 10262)
            self.assertEqual(ws["mean"]["cache_read_input_tokens"], 16720.5)

            wos = agg["without_skill"]
            self.assertEqual(wos["runs"], 1)
            self.assertEqual(wos["total"]["total_tokens"], 40)
            self.assertEqual(wos["total"]["cache_read_input_tokens"], 0)

    def test_skips_timing_that_is_not_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_timing(root, "with_skill", 1, 1, [1, 2])
            self._write_timing(root, "with_skill", 2, 1, "text")
            self._write_timing(root, "with_skill", 3, 1, {"total_tokens": 9})
            agg = aggregate_token_usage(root)
            self.assertEqual(agg["with_skill"]["runs"], 1)
            self.assertEqual(agg["with_skill"]["total"]["total_tokens"], 9)

    def test_string_count_in_timing_reads_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_timing(
                root, "with_skill", 1, 1, {"total_tokens": "56", "input_tokens": 4}
            )
            agg = aggregate_token_usage(root)
            self.assertEqual(agg["with_skill"]["runs"], 1)
            self.assertEqual(agg["with_skill"]["total"]["total_tokens"], 0)
            self.assertEqual(agg["with_skill"]["total"]["input_tokens"], 4)

    def test_empty_runs_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            agg = aggregate_token_usage(Path(tmp))
            self.assertEqual(agg["with_skill"]["runs"], 0)
            self.assertEqual(agg["with_skill"]["mean"]["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
