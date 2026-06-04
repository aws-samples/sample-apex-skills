#!/usr/bin/env python3
"""Assertion engine for eval trajectories.

Takes a parsed Trajectory and a list of assertion configs, evaluates each,
and returns structured results with failure classification.
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

from parse_trajectory import Trajectory, ToolCall, parse_events_file


@dataclass
class AssertionResult:
    assertion: dict
    passed: bool
    evidence: str
    failure_class: str | None
    matching_calls: list[int] | None

    def to_dict(self) -> dict:
        return {
            "assertion": self.assertion,
            "passed": self.passed,
            "evidence": self.evidence,
            "failure_class": self.failure_class,
            "matching_calls": self.matching_calls,
        }


@dataclass
class ProcessAssertionResults:
    results: list[AssertionResult]
    passed: int
    failed: int
    total: int
    pass_rate: float
    failure_classes: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "pass_rate": self.pass_rate,
            "failure_classes": self.failure_classes,
        }


def _args_match(tool_input: dict, args_match: dict) -> bool:
    """Partial match: every key in args_match must exist with the same value."""
    for key, expected in args_match.items():
        if key not in tool_input:
            return False
        if tool_input[key] != expected:
            return False
    return True


def _all_tool_calls(trajectory: Trajectory) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for step in trajectory.steps:
        calls.extend(step.tool_calls)
    return calls


def _eval_tool_called(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    tool = assertion["tool"]
    args_match_spec = assertion.get("args_match")
    min_count = assertion.get("min")
    max_count = assertion.get("max")

    all_calls = _all_tool_calls(trajectory)
    matching: list[int] = []
    for tc in all_calls:
        if tc.name != tool:
            continue
        if args_match_spec and not _args_match(tc.input, args_match_spec):
            continue
        matching.append(tc.index)

    count = len(matching)

    if count == 0:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}' was never called"
            + (f" with matching args {args_match_spec}" if args_match_spec else ""),
            failure_class="missed_tool",
            matching_calls=matching,
        )

    if min_count is not None and count < min_count:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}' called {count} times, expected min {min_count}",
            failure_class="missed_tool",
            matching_calls=matching,
        )

    if max_count is not None and count > max_count:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}' called {count} times, expected max {max_count}",
            failure_class="missed_tool",
            matching_calls=matching,
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Tool '{tool}' called {count} times (indices: {matching})",
        failure_class=None,
        matching_calls=matching,
    )


def _eval_tool_sequence(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    sequence = assertion["sequence"]
    tool_seq = trajectory.tool_sequence

    # Check subsequence: each element of `sequence` must appear in order
    seq_idx = 0
    matching: list[int] = []
    global_idx = 0

    for i, tool_name in enumerate(tool_seq):
        if seq_idx < len(sequence) and tool_name == sequence[seq_idx]:
            matching.append(i)
            seq_idx += 1

    if seq_idx == len(sequence):
        return AssertionResult(
            assertion=assertion,
            passed=True,
            evidence=f"Sequence {sequence} found at positions {matching}",
            failure_class=None,
            matching_calls=matching,
        )

    found_prefix = sequence[:seq_idx]
    missing_from = sequence[seq_idx:]
    return AssertionResult(
        assertion=assertion,
        passed=False,
        evidence=f"Sequence {sequence} not found. Matched {found_prefix}, missing {missing_from}. "
        f"Actual tool order: {tool_seq}",
        failure_class="wrong_sequence",
        matching_calls=matching if matching else None,
    )


def _eval_tool_call_count(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    tool = assertion["tool"]
    min_count = assertion.get("min")
    max_count = assertion.get("max")

    count = trajectory.tool_sequence.count(tool)
    matching = [tc.index for tc in _all_tool_calls(trajectory) if tc.name == tool]

    violations: list[str] = []
    if min_count is not None and count < min_count:
        violations.append(f"below min {min_count}")
    if max_count is not None and count > max_count:
        violations.append(f"above max {max_count}")

    if violations:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}' called {count} times ({', '.join(violations)})",
            failure_class="missed_tool",
            matching_calls=matching,
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Tool '{tool}' called {count} times (within [{min_count}, {max_count}])",
        failure_class=None,
        matching_calls=matching,
    )


def _eval_step_count(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    min_count = assertion.get("min")
    max_count = assertion.get("max")
    actual = trajectory.total_steps

    if max_count is not None and actual > max_count:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Step count {actual} exceeds max {max_count}",
            failure_class="excess_steps",
            matching_calls=None,
        )

    if min_count is not None and actual < min_count:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Step count {actual} below min {min_count}",
            failure_class="insufficient_steps",
            matching_calls=None,
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Step count {actual} within [{min_count}, {max_count}]",
        failure_class=None,
        matching_calls=None,
    )


def _eval_no_tool_called(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    tool = assertion["tool"]
    matching = [tc.index for tc in _all_tool_calls(trajectory) if tc.name == tool]

    if matching:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Forbidden tool '{tool}' was called {len(matching)} times at indices {matching}",
            failure_class="forbidden_tool",
            matching_calls=matching,
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Tool '{tool}' was never called (as required)",
        failure_class=None,
        matching_calls=None,
    )


def _eval_tool_effectiveness(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    max_no_progress = assertion["max_consecutive_no_progress"]

    all_calls = _all_tool_calls(trajectory)
    if not all_calls:
        return AssertionResult(
            assertion=assertion,
            passed=True,
            evidence="No tool calls to evaluate",
            failure_class=None,
            matching_calls=None,
        )

    consecutive_no_progress = 0
    worst_streak = 0
    worst_streak_indices: list[int] = []
    current_streak_indices: list[int] = []
    prev_result: str | None = None

    for tc in all_calls:
        has_progress = (not tc.is_error) and (tc.result != prev_result)

        if has_progress:
            consecutive_no_progress = 0
            current_streak_indices = []
        else:
            consecutive_no_progress += 1
            current_streak_indices.append(tc.index)
            if consecutive_no_progress > worst_streak:
                worst_streak = consecutive_no_progress
                worst_streak_indices = list(current_streak_indices)

        prev_result = tc.result

    if worst_streak > max_no_progress:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Found {worst_streak} consecutive calls without progress "
            f"(max allowed: {max_no_progress}) at indices {worst_streak_indices}",
            failure_class="no_progress_loop",
            matching_calls=worst_streak_indices,
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Worst no-progress streak: {worst_streak} (max allowed: {max_no_progress})",
        failure_class=None,
        matching_calls=None,
    )


def _validate_against_schema(instance: dict, schema: dict) -> bool:
    """Validate instance against JSON Schema. Falls back to basic checks if jsonschema unavailable."""
    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance, schema)
            return True
        except jsonschema.ValidationError:
            return False
    # Fallback: basic type + required checking
    warnings.warn("jsonschema package not installed; using basic type/required validation only")
    if schema.get("type") == "object" and not isinstance(instance, dict):
        return False
    for req in schema.get("required", []):
        if req not in instance:
            return False
    return True


def _eval_tool_args_schema(trajectory: Trajectory, assertion: dict) -> AssertionResult:
    tool = assertion["tool"]
    schema = assertion["schema"]
    require_all = assertion.get("all", False)
    min_matches = assertion.get("min")

    all_calls = _all_tool_calls(trajectory)
    tool_calls = [tc for tc in all_calls if tc.name == tool]

    if not tool_calls:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}' was never called",
            failure_class="invalid_tool_args",
            matching_calls=[],
        )

    matching: list[int] = []
    for tc in tool_calls:
        if _validate_against_schema(tc.input, schema):
            matching.append(tc.index)

    if require_all and len(matching) != len(tool_calls):
        non_matching = [tc.index for tc in tool_calls if tc.index not in matching]
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}': {len(matching)}/{len(tool_calls)} calls match schema; "
            f"non-matching indices: {non_matching}",
            failure_class="invalid_tool_args",
            matching_calls=matching,
        )

    if min_matches is not None and len(matching) < min_matches:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}': {len(matching)} calls match schema, expected min {min_matches}",
            failure_class="invalid_tool_args",
            matching_calls=matching,
        )

    if not matching:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            evidence=f"Tool '{tool}': 0/{len(tool_calls)} calls match schema",
            failure_class="invalid_tool_args",
            matching_calls=[],
        )

    return AssertionResult(
        assertion=assertion,
        passed=True,
        evidence=f"Tool '{tool}': {len(matching)}/{len(tool_calls)} calls match schema",
        failure_class=None,
        matching_calls=matching,
    )


_EVALUATORS = {
    "tool-called": _eval_tool_called,
    "tool-sequence": _eval_tool_sequence,
    "tool-call-count": _eval_tool_call_count,
    "step-count": _eval_step_count,
    "no-tool-called": _eval_no_tool_called,
    "tool-effectiveness": _eval_tool_effectiveness,
    "tool-args-schema": _eval_tool_args_schema,
}


def evaluate(trajectory: Trajectory, assertions: list[dict]) -> ProcessAssertionResults:
    results: list[AssertionResult] = []

    for assertion in assertions:
        atype = assertion.get("type", "")
        evaluator = _EVALUATORS.get(atype)
        if evaluator is None:
            results.append(AssertionResult(
                assertion=assertion,
                passed=False,
                evidence=f"Unknown assertion type: '{atype}'",
                failure_class=None,
                matching_calls=None,
            ))
            continue
        results.append(evaluator(trajectory, assertion))

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total = len(results)

    failure_classes: dict[str, int] = {}
    for r in results:
        if r.failure_class:
            failure_classes[r.failure_class] = failure_classes.get(r.failure_class, 0) + 1

    return ProcessAssertionResults(
        results=results,
        passed=passed,
        failed=failed,
        total=total,
        pass_rate=passed / total if total else 0.0,
        failure_classes=failure_classes,
    )


def evaluate_from_file(events_path: Path, assertions: list[dict]) -> ProcessAssertionResults:
    trajectory = parse_events_file(events_path)
    return evaluate(trajectory, assertions)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <events.jsonl> <assertions.json>",
            file=sys.stderr,
        )
        print(
            "  assertions.json: a JSON file containing a list of assertion objects,",
            file=sys.stderr,
        )
        print(
            '  or a JSON file with a "process_assertions" key.',
            file=sys.stderr,
        )
        sys.exit(2)

    events_path = Path(sys.argv[1])
    assertions_path = Path(sys.argv[2])

    if not events_path.exists():
        print(f"File not found: {events_path}", file=sys.stderr)
        sys.exit(2)
    if not assertions_path.exists():
        print(f"File not found: {assertions_path}", file=sys.stderr)
        sys.exit(2)

    raw = json.loads(assertions_path.read_text())
    if isinstance(raw, list):
        assertions = raw
    elif isinstance(raw, dict) and "process_assertions" in raw:
        assertions = raw["process_assertions"]
    else:
        print("assertions file must be a list or have a 'process_assertions' key", file=sys.stderr)
        sys.exit(2)

    results = evaluate_from_file(events_path, assertions)
    print(json.dumps(results.to_dict(), indent=2))
    sys.exit(0 if results.failed == 0 else 1)
