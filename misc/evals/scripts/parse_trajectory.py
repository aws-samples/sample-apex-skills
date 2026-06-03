#!/usr/bin/env python3
"""Parse events.jsonl into a structured trajectory of tool-call steps."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class ToolCall:
    name: str
    input: dict
    result: str | None
    is_error: bool
    index: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Step:
    tool_calls: list[ToolCall]
    step_index: int
    text_output: str | None

    def to_dict(self) -> dict:
        return {
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "step_index": self.step_index,
            "text_output": self.text_output,
        }


@dataclass
class Trajectory:
    steps: list[Step]
    total_tool_calls: int
    total_steps: int
    tool_sequence: list[str]
    tools_used: set[str]
    duration_ms: int | None
    total_tokens: int | None

    def to_dict(self) -> dict:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "total_tool_calls": self.total_tool_calls,
            "total_steps": self.total_steps,
            "tool_sequence": self.tool_sequence,
            "tools_used": sorted(self.tools_used),
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
        }


def _extract_text_from_result_content(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts) if parts else None
    return str(content)


def parse_events(events: list[dict]) -> Trajectory:
    steps: list[Step] = []
    tool_sequence: list[str] = []
    global_tool_index = 0
    duration_ms: int | None = None
    total_tokens: int | None = None

    pending_calls: list[ToolCall] = []
    pending_text: list[str] = []

    i = 0
    while i < len(events):
        evt = events[i]
        etype = evt.get("type")

        if etype == "assistant":
            msg = evt.get("message") or {}
            turn_calls: list[ToolCall] = []
            turn_text_parts: list[str] = []

            for c in msg.get("content") or []:
                ctype = c.get("type")
                if ctype == "tool_use":
                    tc = ToolCall(
                        name=c.get("name", ""),
                        input=c.get("input") or {},
                        result=None,
                        is_error=False,
                        index=global_tool_index,
                    )
                    turn_calls.append(tc)
                    tool_sequence.append(tc.name)
                    global_tool_index += 1
                elif ctype == "text":
                    text = (c.get("text") or "").strip()
                    if text:
                        turn_text_parts.append(text)

            if turn_calls:
                # Look ahead for the user event with tool_results
                if i + 1 < len(events):
                    next_evt = events[i + 1]
                    if next_evt.get("type") == "user":
                        results_content = (next_evt.get("message") or {}).get("content") or []
                        result_idx = 0
                        for rc in results_content:
                            if rc.get("type") == "tool_result" and result_idx < len(turn_calls):
                                turn_calls[result_idx].result = _extract_text_from_result_content(
                                    rc.get("content")
                                )
                                turn_calls[result_idx].is_error = rc.get("is_error") is True
                                result_idx += 1

                step = Step(
                    tool_calls=turn_calls,
                    step_index=len(steps),
                    text_output="\n".join(turn_text_parts) if turn_text_parts else None,
                )
                steps.append(step)

        elif etype == "result":
            usage = evt.get("usage") or {}
            d = evt.get("duration_ms")
            if d is not None:
                duration_ms = d
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            if input_t or output_t:
                total_tokens = input_t + output_t

        i += 1

    tools_used = set(tool_sequence)

    return Trajectory(
        steps=steps,
        total_tool_calls=global_tool_index,
        total_steps=len(steps),
        tool_sequence=tool_sequence,
        tools_used=tools_used,
        duration_ms=duration_ms,
        total_tokens=total_tokens,
    )


def parse_events_file(path: Path) -> Trajectory:
    events: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return parse_events(events)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <events.jsonl>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(2)

    trajectory = parse_events_file(path)
    print(json.dumps(trajectory.to_dict(), indent=2))
