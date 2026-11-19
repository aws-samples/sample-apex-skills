#!/usr/bin/env python3
"""Parse events.jsonl into a structured trajectory of tool-call steps."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Token categories recorded per run, named as in the result event's `usage`.
# The counts come from the result event's `modelUsage` (one entry per model,
# summed), which includes subagent requests; `usage` counts only the
# top-level agent loop and leaves subagent tokens out. `usage` is read only
# when no `modelUsage` entry is a dict carrying one of MODEL_USAGE_KEYS
# (absent, empty or unreadable `modelUsage`). `token_source`
# records which object was read: "modelUsage", "usage" or None.
# `total_tokens` keeps its meaning (input + output) and its source, `usage`,
# so it stays comparable with earlier runs.
USAGE_TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

# The same categories as named inside each `modelUsage` entry.
MODEL_USAGE_KEYS = {
    "input_tokens": "inputTokens",
    "output_tokens": "outputTokens",
    "cache_read_input_tokens": "cacheReadInputTokens",
    "cache_creation_input_tokens": "cacheCreationInputTokens",
}


def token_count(value: Any) -> int:
    """Return `value` if it is an int count, else 0 (a string or float too)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def model_usage_entries(model_usage: Any) -> list[dict]:
    """The `modelUsage` entries that are dicts carrying a known key."""
    if not isinstance(model_usage, dict):
        return []
    return [
        per_model
        for per_model in model_usage.values()
        if isinstance(per_model, dict)
        and any(camel in per_model for camel in MODEL_USAGE_KEYS.values())
    ]


@dataclass
class ToolCall:
    name: str
    # The tool_use block's `input` as sent. None when the block has no
    # `input` key or it is null, so "no input" stays apart from `{}`.
    input: Any
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
    # Per-category counts (see USAGE_TOKEN_KEYS for the source). They come
    # from the last result event that carries a non-empty `modelUsage` or a
    # `usage` object, so a multi-turn run records its last result's counts.
    # On Claude Code v2.1.277 or later the last result's `modelUsage`
    # includes earlier turns' spend (when every earlier process exited
    # normally); before that it covers only the last turn. The docs name
    # only `total_cost_usd` and `modelUsage` as carrying restored spend.
    # None when no result event carried either; a missing key inside one is 0,
    # and so is a count that is not an int.
    # total_tokens is set from the last result whose `usage` input + output
    # is non-zero, so it can come from an earlier result than the categories.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    token_source: str | None = None
    # Events that were not a JSON object (a list, string, number or null
    # line in events.jsonl); they are skipped.
    skipped_events: int = 0

    def to_dict(self) -> dict:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "total_tool_calls": self.total_tool_calls,
            "total_steps": self.total_steps,
            "tool_sequence": self.tool_sequence,
            "tools_used": sorted(self.tools_used),
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "token_source": self.token_source,
            "skipped_events": self.skipped_events,
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
    token_counts: dict[str, int | None] = dict.fromkeys(USAGE_TOKEN_KEYS)
    token_source: str | None = None

    pending_calls: list[ToolCall] = []
    pending_text: list[str] = []
    skipped_events = 0

    i = 0
    while i < len(events):
        evt = events[i]
        if not isinstance(evt, dict):
            skipped_events += 1
            i += 1
            continue
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
                        input=c.get("input"),
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
                    if isinstance(next_evt, dict) and next_evt.get("type") == "user":
                        results_content = (next_evt.get("message") or {}).get("content") or []
                        result_idx = 0
                        for rc in results_content:
                            if isinstance(rc, dict) and rc.get("type") == "tool_result" and result_idx < len(turn_calls):
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
            entries = model_usage_entries(evt.get("modelUsage"))
            if entries:
                token_counts = dict.fromkeys(USAGE_TOKEN_KEYS, 0)
                for per_model in entries:
                    for key, camel in MODEL_USAGE_KEYS.items():
                        token_counts[key] += token_count(per_model.get(camel))
                token_source = "modelUsage"
            elif isinstance(evt.get("usage"), dict):
                for key in USAGE_TOKEN_KEYS:
                    token_counts[key] = usage.get(key, 0)
                token_source = "usage"

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
        **token_counts,
        token_source=token_source,
        skipped_events=skipped_events,
    )


# ---------- harness output shapes ---------------------------------------------
#
# The task runner drives three harnesses. Each prints JSON Lines on stdout,
# in its own shape. normalize_events() turns each shape into Claude Code's
# stream-json form (system/init, assistant tool_use and text, user
# tool_result, result with usage), so parse_events, the transcript, the
# metrics and every assertion runner read all three the same way.
#
# claude: `claude -p --output-format stream-json`, read as it is.
# codex:  `codex exec --json` (codex-cli 0.163.0). Events, from
#   https://learn.chatgpt.com/docs/non-interactive-mode and
#   codex-rs/exec/src/exec_events.rs (read 2026-11-19): thread.started
#   {thread_id}, turn.started, turn.completed {usage: input_tokens,
#   cached_input_tokens, cache_write_input_tokens, output_tokens,
#   reasoning_output_tokens}, turn.failed {error: {message}}, item.started,
#   item.updated, item.completed {item}, error {message}. Item types:
#   agent_message {text}, reasoning, command_execution {command,
#   aggregated_output, exit_code, status}, file_change {changes: [{path,
#   kind}], status}, mcp_tool_call {server, tool, arguments, result
#   {content}, error {message}, status}, web_search {query}, todo_list.
#   Only item.completed is read, so a call is counted once. Tool names:
#   command_execution reads as Bash {command}, file_change as Write
#   (kind "add") or Edit {file_path}, one call per changed path,
#   mcp_tool_call as mcp__<server>__<tool> {arguments}, web_search as
#   WebSearch {query}. Codex's input_tokens counts cached input too (the
#   documented sample has 24448 cached of 24763 input); it is recorded as
#   given, with cached_input_tokens as cache_read_input_tokens and
#   cache_write_input_tokens as cache_creation_input_tokens.
# kiro:   `kiro-cli chat --no-interactive --output-format stream-json`
#   (kiro-cli 3.4.0). Its help says: "The run's ACP events as JSON Lines on
#   stdout, one self-describing event per line"; https://kiro.dev/docs/cli/
#   headless/ (read 2026-11-19) documents only the error record
#   {"type":"runError","data":{sessionId, stage, message, ...}}. The ACP
#   update objects follow https://agentclientprotocol.com/protocol/tool-calls
#   (sessionUpdate "tool_call" {toolCallId, title, kind, status, rawInput},
#   "tool_call_update" {toolCallId, status, content, rawOutput},
#   "agent_message_chunk" {content}). Kiro's docs do not show how an update
#   is wrapped on a line, so an update is read where it is found: the line
#   itself, its "update", its "data", "data.update" or "params.update". A
#   tool's name is its "name", else its "title", else its "kind"; a call
#   with no toolCallId is keyed by its line's position, so two such calls
#   stay two. Token counts are read only from the runFinished record's
#   "usage" or "data.usage" (input_tokens/inputTokens,
#   output_tokens/outputTokens); Kiro's docs name no token fields, so a
#   Kiro run's tokens read None until a recorded stream shows them. A Kiro
#   stream with no runStarted, no runFinished or no ACP update is invalid
#   (stream_invalid_reason), never scored as an empty trajectory.
#
# run_triggering.py reads kiro and codex streams line by line with the same
# helpers (START_EVENTS, END_EVENTS, acp_update, kiro_usage, codex_usage),
# so both runners apply one set of rules.

HARNESSES = ("claude", "kiro", "codex")
# Each harness's start and end event. A kiro or codex run needs both.
START_EVENTS = {"claude": "system/init", "kiro": "runStarted", "codex": "thread.started"}
END_EVENTS = {"claude": "result", "kiro": "runFinished", "codex": "turn.completed"}


def _text_of(content: Any) -> str:
    """Text out of an ACP or MCP content value (a block, a list or a str)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(t for t in (_text_of(c) for c in content) if t)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if "content" in content:
            return _text_of(content.get("content"))
    return ""


def _tool_pair(name: str, tool_input: Any, result: str | None, is_error: bool) -> list[dict]:
    """One tool call in stream-json form: the assistant tool_use event and
    the user tool_result event parse_events pairs with it."""
    return [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": name, "input": tool_input}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": result, "is_error": is_error}]}},
    ]


def _assistant_text(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def codex_usage(evt: dict) -> dict | None:
    """A codex turn.completed's token counts in USAGE_TOKEN_KEYS names
    (cached_input_tokens as cache_read_input_tokens, cache_write_input_tokens
    as cache_creation_input_tokens), or None when it has no usage object."""
    u = evt.get("usage")
    if not isinstance(u, dict):
        return None
    return {"input_tokens": token_count(u.get("input_tokens")),
            "output_tokens": token_count(u.get("output_tokens")),
            "cache_read_input_tokens": token_count(u.get("cached_input_tokens")),
            "cache_creation_input_tokens": token_count(u.get("cache_write_input_tokens"))}


def _normalize_codex(events: list) -> list[dict]:
    out: list[dict] = []
    usage: dict | None = None
    turns = 0
    error: str | None = None
    for evt in events:
        if not isinstance(evt, dict):
            continue
        etype = evt.get("type")
        if etype == "thread.started":
            out.append({"type": "system", "subtype": "init", "harness": "codex",
                        "session_id": evt.get("thread_id")})
        elif etype == "turn.completed":
            turns += 1
            counts = codex_usage(evt)
            if counts is not None:
                usage = usage or dict.fromkeys(USAGE_TOKEN_KEYS, 0)
                for key, value in counts.items():
                    usage[key] += value
        elif etype == "turn.failed":
            turns += 1
            err = evt.get("error") if isinstance(evt.get("error"), dict) else {}
            error = str(err.get("message") or "turn.failed")
        elif etype == "error":
            error = str(evt.get("message") or "error")
        elif etype == "item.completed":
            item = evt.get("item") if isinstance(evt.get("item"), dict) else {}
            itype = item.get("type")
            if itype == "agent_message":
                text = (item.get("text") or "").strip()
                if text:
                    out.append(_assistant_text(text))
            elif itype == "command_execution":
                code = item.get("exit_code")
                failed = item.get("status") in ("failed", "declined") or (
                    isinstance(code, int) and code != 0)
                out.extend(_tool_pair("Bash", {"command": item.get("command")},
                                      item.get("aggregated_output"), failed))
            elif itype == "file_change":
                failed = item.get("status") == "failed"
                for change in item.get("changes") or []:
                    if not isinstance(change, dict):
                        continue
                    name = "Write" if change.get("kind") == "add" else "Edit"
                    out.extend(_tool_pair(name, {"file_path": change.get("path")},
                                          None, failed))
            elif itype == "mcp_tool_call":
                err = item.get("error") if isinstance(item.get("error"), dict) else None
                res = item.get("result") if isinstance(item.get("result"), dict) else {}
                result = err.get("message") if err else _text_of(res.get("content"))
                out.extend(_tool_pair(f"mcp__{item.get('server')}__{item.get('tool')}",
                                      item.get("arguments"), result or None,
                                      err is not None or item.get("status") == "failed"))
            elif itype == "web_search":
                out.extend(_tool_pair("WebSearch", {"query": item.get("query")}, None, False))
    if turns or error:
        result_evt = {"type": "result", "harness": "codex",
                      "subtype": "error" if error else "success",
                      "is_error": error is not None, "error": error,
                      "num_turns": turns}
        if usage is not None:
            result_evt["usage"] = usage
        out.append(result_evt)
    return out


def acp_update(evt: dict) -> dict | None:
    """The ACP session update an event line carries, wherever it sits."""
    candidates = [evt, evt.get("update"), evt.get("data")]
    data = evt.get("data")
    if isinstance(data, dict):
        candidates.append(data.get("update"))
    params = evt.get("params")
    if isinstance(params, dict):
        candidates.append(params.get("update"))
    for c in candidates:
        if isinstance(c, dict) and isinstance(c.get("sessionUpdate"), str):
            return c
    return None


def kiro_usage(evt: dict) -> dict | None:
    """A kiro runFinished record's token counts in USAGE_TOKEN_KEYS names,
    from its "usage" or "data.usage", or None when neither carries
    input_tokens/inputTokens or output_tokens/outputTokens, or when a count
    it carries is not an int (read as missing, never as 0)."""
    pairs = {"input_tokens": ("input_tokens", "inputTokens"),
             "output_tokens": ("output_tokens", "outputTokens")}
    data = evt.get("data") if isinstance(evt.get("data"), dict) else {}
    for obj in (evt.get("usage"), data.get("usage")):
        if not isinstance(obj, dict) or not any(n in obj for ns in pairs.values() for n in ns):
            continue
        out = dict.fromkeys(USAGE_TOKEN_KEYS, 0)
        for key, names in pairs.items():
            for n in names:
                if n in obj:
                    value = obj.get(n)
                    if not isinstance(value, int) or isinstance(value, bool):
                        return None
                    out[key] = value
        return out
    return None


def _normalize_kiro(events: list) -> list[dict]:
    out: list[dict] = []
    calls: dict[str, dict] = {}
    order: list[str] = []
    text: list[str] = []
    usage: dict | None = None
    error: str | None = None
    finished = False
    started = False
    updates = 0

    def flush_text() -> None:
        if text:
            joined = "".join(text).strip()
            if joined:
                out.append(_assistant_text(joined))
            text.clear()

    def emit(call_id: str) -> None:
        call = calls.pop(call_id, None)
        if call is None:
            return
        order.remove(call_id)
        flush_text()
        out.extend(_tool_pair(call["name"], call["input"], call["result"], call["error"]))

    for pos, evt in enumerate(events):
        if not isinstance(evt, dict):
            continue
        etype = evt.get("type")
        if etype == "runError":
            data = evt.get("data") if isinstance(evt.get("data"), dict) else {}
            error = str(data.get("message") or "runError")
            continue
        if etype == "runStarted":
            if not started:
                started = True
                out.append({"type": "system", "subtype": "init", "harness": "kiro"})
            continue
        if etype == "runFinished":
            finished = True
            usage = kiro_usage(evt) or usage
            continue
        upd = acp_update(evt)
        if upd is None:
            continue
        updates += 1
        kind = upd.get("sessionUpdate")
        if kind == "agent_message_chunk":
            text.append(_text_of(upd.get("content")))
        elif kind in ("tool_call", "tool_call_update"):
            raw_id = upd.get("toolCallId")
            call_id = f"id:{raw_id}" if raw_id is not None else f"pos:{pos}"
            call = calls.get(call_id)
            if call is None:
                call = {"name": upd.get("name") or upd.get("title") or upd.get("kind") or "",
                        "input": None, "result": None, "error": False}
                calls[call_id] = call
                order.append(call_id)
            if "rawInput" in upd:
                call["input"] = upd.get("rawInput")
            result = _text_of(upd.get("rawOutput")) or _text_of(upd.get("content"))
            if result:
                call["result"] = result
            status = upd.get("status")
            if status == "failed":
                call["error"] = True
            if status in ("completed", "failed"):
                emit(call_id)
    for call_id in list(order):
        emit(call_id)
    flush_text()
    if started or error or updates:
        result_evt = {"type": "result", "harness": "kiro",
                      "subtype": "error" if error else "success",
                      "is_error": error is not None, "error": error,
                      "finished": finished, "acp_updates": updates}
        if usage is not None:
            result_evt["usage"] = usage
        out.append(result_evt)
    return out


def normalize_events(events: list, harness: str) -> list[dict]:
    """A harness's raw events in Claude Code stream-json form (see above)."""
    if harness == "claude":
        return [e for e in events if isinstance(e, dict)]
    if harness == "codex":
        return _normalize_codex(events)
    if harness == "kiro":
        return _normalize_kiro(events)
    raise ValueError(f"unknown harness: {harness!r} (expected one of {HARNESSES})")


def stream_invalid_reason(events: list, harness: str) -> str | None:
    """Why a run's raw event stream cannot be scored, or None.

    No events, no start event (START_EVENTS) or an error the harness
    reported (codex turn.failed or error, kiro runError) makes the run
    invalid. A codex run with no turn.completed or a kiro run with no
    runFinished did not finish, and a kiro run with no ACP update shows no
    tool view. These shapes would otherwise score as an empty trajectory,
    on which some assertions pass."""
    objs = [e for e in events if isinstance(e, dict)]
    if not objs:
        return "no events"
    norm = normalize_events(objs, harness)
    if not any(e.get("type") == "system" and e.get("subtype") == "init" for e in norm):
        return "no runStarted event" if harness == "kiro" else "no init event"
    result = next((e for e in reversed(norm) if e.get("type") == "result"), None)
    if harness in ("codex", "kiro") and result is not None and result.get("is_error"):
        return f"{harness} reported an error: {result.get('error')}"
    if harness == "codex" and result is None:
        return "codex stream ended with no turn.completed"
    if harness == "kiro" and not result.get("finished"):
        return "kiro stream ended with no runFinished"
    if harness == "kiro" and not result.get("acp_updates"):
        return "kiro stream: no ACP session update found, so tool calls cannot be read"
    return None


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
