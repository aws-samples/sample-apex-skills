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
from typing import Any, Callable


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


# A fenced block, whatever blank lines it holds, and an inline code span or a
# URL: a "?" in any of them is code or a query string, not a question.
_FENCED = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.MULTILINE | re.DOTALL)
_INLINE_OR_URL = re.compile(r"`[^`\n]*`|https?://\S*[^\s?.,)>]")


def detect_pending_question(events: list[dict]) -> str | None:
    """Scan the final assistant message for the question that ended the session.

    Returns the question text if found, None otherwise. The question is the
    last AskUserQuestion tool_use in the final assistant message: this is what
    ends the session in -p mode. A skill that asks in plain text (eks-build,
    eks-design, eks-mcp-server) ends on its question instead, so with no
    AskUserQuestion the question is the final text's last paragraph, when it
    holds a "?" outside code and URLs: a closed fenced block counts as one
    paragraph (so a reply that ends on code is not a question), and a "?" in a
    closed fenced block, an inline code span or a URL does not count (a URL
    stops before a trailing "?", ".", ",", ")" or ">"). Paragraphs are split
    on blank lines with LF line ends, so CRLF text reads as one paragraph.
    The plain-text form is a heuristic: it misses a question followed by
    another paragraph, such as an options paragraph or a sign-off ("Let me
    know and I'll generate the rest."), and counts a closing offer that ends
    in "?" (such as "Want me to confirm?", the "confirm" false catch). It
    also misses a question on a fence's closing line ("``` and which
    region?"), and a fence of 4 or more backticks is closed early by an
    inner ``` line, so a "?" in the rest of that block counts.
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
        for content in reversed(msg.get("content") or []):
            if content.get("type") == "text" and (content.get("text") or "").strip():
                text = _FENCED.sub("[code]", content["text"])
                last = text.strip().split("\n\n")[-1].strip()
                return last if "?" in _INLINE_OR_URL.sub("", last) else None
        break
    return None


def match_answer(question_text: str, turns: list[CannedTurn]) -> str | None:
    """Find the first canned turn whose pattern matches the question."""
    for turn in turns:
        if re.search(turn.question_match, question_text, re.IGNORECASE):
            return turn.answer
    return None


def extract_session_id(events: list[dict]) -> str | None:
    """The session ID of the last result or system/init event that has one
    (a normalized codex result has none; its init carries the thread_id)."""
    for evt in reversed(events):
        if evt.get("type") == "result" or (
                evt.get("type") == "system" and evt.get("subtype") == "init"):
            if evt.get("session_id"):
                return evt["session_id"]
    return None


def _append_event(events: list[dict], line: str) -> None:
    """Append one stream-json line if it parses to a JSON object; a line that
    is not JSON, or parses to a list, string, number or null, is dropped."""
    try:
        evt = json.loads(line)
    except json.JSONDecodeError:
        return
    if isinstance(evt, dict):
        events.append(evt)


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
                _append_event(events, line)

    if buffer.strip():
        _append_event(events, buffer)
    return events, timed_out


def run_multiturn_subject(
    *,
    initial_prompt: str,
    elicitation: ElicitationConfig,
    cmd_base: list[str] | None = None,
    cwd: str,
    env_for_turn: Callable[[], dict[str, str]],
    timeout_per_turn: int,
    turn_cmd: Callable[[str, bool, str | None], list[str] | None] | None = None,
    normalize: Callable[[list[dict]], list[dict]] | None = None,
) -> tuple[list[dict], bool, str | None]:
    """Run a canned-multiturn session.

    Runs the initial prompt, detects questions, matches canned answers,
    and resumes the session until no more questions match or max_turns is hit.
    `env_for_turn` is called before each turn, so each turn starts on an
    eval-role session that outlasts it.

    `turn_cmd(text, resume, session_id)` builds each turn's command. With
    none it is claude's form, `cmd_base + ["-p", text]` plus `--session-id`
    on the first turn and `--resume` after, the id made here. A harness
    that names its own session (codex) gets None on the first turn, then
    the id extract_session_id reads from that turn's events; a turn_cmd
    that returns None ends the loop. `normalize` puts a turn's raw events
    in Claude Code stream-json form before its question is read (as
    given when None).

    Returns (all_events, timed_out, session_id). Each canned answer sent is
    recorded as "elicitation_answer": "<answer>" on the first event of the
    turn it resumed (on a real claude run that is the system/init event); a
    resumed turn that emits no event loses that record.
    """
    if turn_cmd is None:
        session_id: str | None = str(uuid.uuid4())

        def turn_cmd(text: str, resume: bool, sid: str | None) -> list[str]:
            return (cmd_base or []) + ["-p", text, "--resume" if resume else "--session-id", sid]
    else:
        session_id = None
    norm = normalize or (lambda evts: evts)
    all_events: list[dict] = []
    timed_out = False

    # First turn. Only stdout is read (drain_stream_for_events), so stderr goes
    # to DEVNULL: an unread pipe fills and stalls the subject until the timeout.
    cmd = turn_cmd(initial_prompt, False, session_id)
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=cwd, env=env_for_turn()
    )
    events, timed_out = drain_stream_for_events(process, timeout_per_turn)
    all_events.extend(events)

    if timed_out:
        return all_events, True, session_id
    if session_id is None:
        session_id = extract_session_id(norm(events))

    # Follow-up turns
    turns_used = 1
    while turns_used < elicitation.max_turns:
        question = detect_pending_question(norm(events))
        if not question:
            break

        answer = match_answer(question, elicitation.turns)
        if not answer:
            break

        cmd = turn_cmd(answer, True, session_id)
        if cmd is None:
            break
        turns_used += 1
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=cwd, env=env_for_turn()
        )
        events, timed_out = drain_stream_for_events(process, timeout_per_turn)
        if events:
            # Record the injected answer in events.jsonl, on the resumed turn's
            # first event. transcript.md shows it
            # (run_task_evals.format_transcript); drive_c1's T5 check does
            # not use it.
            events[0]["elicitation_answer"] = answer
        all_events.extend(events)

        if timed_out:
            return all_events, True, session_id

    return all_events, False, session_id
