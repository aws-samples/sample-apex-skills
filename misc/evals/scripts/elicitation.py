#!/usr/bin/env python3
"""Elicitation strategies for multi-turn eval runs.

Skills like eks-build and eks-design ask clarifying questions before producing
output. In single-shot mode (`claude -p`), those questions get auto-skipped,
producing incomplete runs. Elicitation strategies provide pre-scripted answers
so evals are reproducible and deterministic.

Strategies:
  single-shot       — default, one prompt, no follow-up
  canned-multiturn  — pre-scripted answers matched by regex on question text
"""

from __future__ import annotations

import re
import uuid
import json
import os
import select
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CannedTurn:
    question_match: str  # regex pattern to match against question text
    answer: str

    @classmethod
    def from_dict(cls, d: dict) -> CannedTurn:
        return cls(
            question_match=d["question_match"],
            answer=d["answer"],
        )


@dataclass
class ElicitationConfig:
    strategy: str  # "single-shot" or "canned-multiturn"
    turns: list[CannedTurn]
    max_turns: int  # safety cap to prevent infinite loops

    @classmethod
    def from_dict(cls, d: dict | None) -> ElicitationConfig:
        if d is None:
            return cls(strategy="single-shot", turns=[], max_turns=1)
        return cls(
            strategy=d.get("strategy", "single-shot"),
            turns=[CannedTurn.from_dict(t) for t in d.get("turns", [])],
            max_turns=d.get("max_turns", 10),
        )


def detect_pending_question(events: list[dict]) -> str | None:
    """Scan events for an AskUserQuestion tool call that ended the session.

    Returns the concatenated question text if found, None otherwise.
    The question is the last AskUserQuestion tool_use in the final assistant
    message — this is what triggered the session end in -p mode.
    """
    for evt in reversed(events):
        if evt.get("type") != "assistant":
            continue
        msg = evt.get("message") or {}
        for content in reversed(msg.get("content") or []):
            if content.get("type") == "tool_use" and content.get("name") == "AskUserQuestion":
                inp = content.get("input") or {}
                questions = inp.get("questions") or []
                parts = []
                for q in questions:
                    if isinstance(q, dict):
                        parts.append(q.get("question", ""))
                return " ".join(parts).strip() or None
        break
    return None


def match_answer(question_text: str, turns: list[CannedTurn]) -> str | None:
    """Find the first canned turn whose pattern matches the question."""
    for turn in turns:
        if re.search(turn.question_match, question_text, re.IGNORECASE):
            return turn.answer
    return None


def extract_session_id(events: list[dict]) -> str | None:
    """Extract session ID from the result event."""
    for evt in reversed(events):
        if evt.get("type") == "result":
            return evt.get("session_id")
        if evt.get("type") == "system" and evt.get("subtype") == "init":
            return evt.get("session_id")
    return None


def drain_stream_for_events(
    process: subprocess.Popen,
    timeout: float,
) -> tuple[list[dict], bool]:
    """Read stream-json events until process exits or timeout. Same logic as
    run_task_evals.drain_stream but duplicated here to avoid circular imports
    when used standalone.
    """
    events: list[dict] = []
    buffer = ""
    start = time.time()
    timed_out = False

    while True:
        if time.time() - start > timeout:
            timed_out = True
            process.kill()
            process.wait()
            break
        if process.poll() is not None:
            rest = process.stdout.read() if process.stdout else b""
            if rest:
                buffer += rest.decode("utf-8", errors="replace")
            break

        ready, _, _ = select.select([process.stdout], [], [], 1.0)
        if not ready:
            continue
        chunk = os.read(process.stdout.fileno(), 65536)
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if buffer.strip():
        try:
            events.append(json.loads(buffer))
        except json.JSONDecodeError:
            pass
    return events, timed_out


def run_multiturn_subject(
    *,
    initial_prompt: str,
    elicitation: ElicitationConfig,
    cmd_base: list[str],
    cwd: str,
    env: dict[str, str],
    timeout_per_turn: int,
) -> tuple[list[dict], bool, str | None]:
    """Run a canned-multiturn session.

    Runs the initial prompt, detects questions, matches canned answers,
    and resumes the session until no more questions match or max_turns is hit.

    Returns (all_events, timed_out, session_id).
    """
    session_id = str(uuid.uuid4())
    all_events: list[dict] = []
    timed_out = False

    # First turn
    cmd = cmd_base + ["-p", initial_prompt, "--session-id", session_id]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env
    )
    events, timed_out = drain_stream_for_events(process, timeout_per_turn)
    all_events.extend(events)

    if timed_out:
        return all_events, True, session_id

    # Follow-up turns
    turns_used = 1
    while turns_used < elicitation.max_turns:
        question = detect_pending_question(events)
        if not question:
            break

        answer = match_answer(question, elicitation.turns)
        if not answer:
            break

        turns_used += 1
        cmd = cmd_base + ["-p", answer, "--resume", session_id]
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env
        )
        events, timed_out = drain_stream_for_events(process, timeout_per_turn)
        all_events.extend(events)

        if timed_out:
            return all_events, True, session_id

    return all_events, False, session_id
