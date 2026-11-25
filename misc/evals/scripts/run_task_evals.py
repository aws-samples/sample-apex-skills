#!/usr/bin/env python3
"""Task-axis runner for misc/evals/ (PLAN §2).

For each case in <skill>/evals.json and in the shared evals of the run key's
classes (CLASS_TARGETS), skipping "live_only": true entries unless
--include-live-only, for each
arm in {with_skill, base arm}, for k in 1..--runs (default
regression.pass_k). The base arm is base_skill, the skill as it was at
--base-ref (default DEFAULT_BASE_REF), or without_skill when the skill is
absent there or --base-ref is none. Step 2's subject is the --harness
(claude, kiro or codex; one adapter function each) on --subject-model
(run_triggering.subject_model), and every run's valid, pass, tokens and
wall time go to run-result.json, cases.json and the history row. An
invalid run scores grader pass rate 0 and counts in the pooled grader pass
rate (the history row's means and delta); a run with no token count
records tokens None, and token means cover only the runs that have one
(the scorecard reads the history row's
skill_summary.arms.with_skill.tokens_per_run_mean; its token_usage has no
reader):

  1. Stage a sandbox (stage_skill_sandbox or stage_empty_sandbox) with a
     clean HOME, plus an optional KUBECONFIG. The only AWS credentials the
     subject and the grader get are the eval-role session that
     run_triggering.mint_eval_role_credentials mints and checks before the
     first run; the host's ~/.aws and AWS_* variables are no longer handed
     to them in their environment or HOME. The subject runs inside
     run_triggering.wall_off_host and the grader outside it; what the wall
     hides and what stays open is in misc/evals/README.md, "Eval-role setup
     (`~/.apex-eval`)". The
     --aws-session-policy, --aws-region and --aws-duration flags are removed.
  2. Run `claude -p <prompt>` streaming stream-json. Write
       transcript.md, events.jsonl, outputs/, timing.json, metrics.json
     under:
       <skill>/workspace/runs/<UTC>/eval-<id>/<config>/run-<k>/
  3. Invoke a grader `claude -p` with grader.md as the role spec, the
     expectations, and the transcript/outputs paths. Grader writes
     grading.json at the run-dir (sibling of outputs/).
  4. After the whole matrix completes: shell out to
     `make benchmark-<skill> BENCHMARK_DIR=<runs-dir>` to aggregate into
     benchmark.json/benchmark.md; update <skill>/workspace/latest ->
     runs/<UTC>/; append a kind="task" row to history/<skill>.jsonl.

Grader caching is *intentional*-not-supported — every invocation pays the
grader call so we can detect grader drift.

Exit codes:
  0  all runs completed, benchmark generated
  1  subject or grader subprocess failure we couldn't recover from
  2  invalid inputs (missing evals.json, no fixture-free prompts, etc.), or
     the eval-role session refused at start or failed to refresh mid-run
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import multiprocessing
import os
import re
import select
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from run_triggering import (
    CLASS_TARGETS as CLASS_TARGET_PATHS,
    CLASS_TARGETS_REFUSED,
    EvalCredentialError,
    HARNESS_SUBJECT_MODELS,
    build_subprocess_env,
    check_cli_versions,
    eval_aws_env,
    harness_env,
    kiro_data_dir,
    mint_eval_role_credentials,
    run_key_for,
    set_eval_credentials,
    stage_empty_sandbox,
    stage_skill_sandbox,
    read_skill_meta,
    subject_model,
    wall_off_host,
)
from parse_trajectory import (
    HARNESSES,
    MODEL_USAGE_KEYS,
    USAGE_TOKEN_KEYS,
    model_usage_entries,
    normalize_events,
    parse_events,
    stream_invalid_reason,
    token_count,
)
from process_assertions import AssertionResult, ProcessAssertionResults, evaluate
from artifact_validation import validate_run as validate_artifacts
import elicitation
from elicitation import ElicitationConfig, _append_event, run_multiturn_subject
from skilleval_config import load_config as load_skilleval_config

EVALS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_ROOT.parent.parent
HISTORY_DIR = EVALS_ROOT / "history"
HISTORY_CAP = 50
GRADER_MD = REPO_ROOT / "skills" / "skill-creator" / "agents" / "grader.md"
SC_DIR = REPO_ROOT / "skills" / "skill-creator"
CLASSES_ROOT = REPO_ROOT / "classes"
# Run folders for a target with no misc/evals/<run key>/ folder of its own.
# misc/evals/workspace is left out of discover_skills and the Makefile's
# SKILLS list, so a run there adds no skill.
TARGETS_WORKSPACE = EVALS_ROOT / "workspace"

# The "old" arm is the skill as it was at this git ref (v1.3.0 is the
# first base). "none" runs with against without, as before.
DEFAULT_BASE_REF = "v1.3.0"
NEW_ARM = "with_skill"
BASE_ARM = "base_skill"
WITHOUT_ARM = "without_skill"

# Each process assertion runs in its own worker under this limit; one
# that does not finish scores failed with the reason "timeout".
ASSERTION_TIMEOUT_SECONDS = 10

# Where each harness finds a project skill in the sandbox.
# kiro: ".kiro/skills/" workspace scope (https://kiro.dev/docs/skills/,
# read 2026-11-19). codex: "$CWD/.agents/skills" (https://learn.chatgpt.com/
# docs/build-skills, read 2026-11-19).
HARNESS_SKILL_DIRS = {
    "claude": Path(".claude") / "skills",
    "kiro": Path(".kiro") / "skills",
    "codex": Path(".agents") / "skills",
}
# Top-level sandbox folders the runner stages; never copied into outputs/.
STAGED_TOP_DIRS = frozenset({".claude", ".kiro", ".agents"})

# Shared class cases run against each target of their class. The targets
# and which of them block are run_triggering.CLASS_TARGETS, the one list
# both runners read (its comment gives the reasons). A shared case lives in
# classes/<class>/evals/<suite>/evals.json and its fixtures in
# <suite>/files/shared/ and <suite>/files/eval-<id>/; only cases with a
# "prompt" run here (a "mode": "manual" case is run by hand).
def targets_by_folder(class_targets: dict[str, dict[str, bool]]) -> tuple[dict, ...]:
    """One target per skill folder: a folder on several classes' lists (a
    member and its class's parents) runs each class's shared cases, and
    blocks when any of those lists makes it blocking."""
    folders: dict[str, dict[str, bool]] = {}
    for cls, listed in class_targets.items():
        for path, blocking in listed.items():
            folders.setdefault(path, {})[cls] = blocking
    return tuple(
        {"run_key": run_key_for(REPO_ROOT / path), "skill_dir": path, "classes": list(by_class),
         "blocking": any(by_class.values())}
        for path, by_class in folders.items())


CLASS_TARGETS: tuple[dict, ...] = targets_by_folder(CLASS_TARGET_PATHS)
# Run key -> folder of each SKILL.md whose classes could not be read: listed
# and run like any key, so its run fails with the reason (run_skill).
REFUSED_TARGETS: dict[str, str] = {run_key_for(REPO_ROOT / p): p for p in CLASS_TARGETS_REFUSED}


# ---------- stream consumption ------------------------------------------------


def drain_stream(
    process: subprocess.Popen,
    timeout: float,
) -> tuple[list[dict], bool]:
    """Read all JSON lines from a stream-json subprocess until it exits or
    times out. Returns (events, timed_out).

    Uses select() with a short poll so the timeout check is actually reached
    while the subprocess is idle waiting for an API response. A naive blocking
    read can sit in recv() past the timeout and never surface.
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
            # EOF with the process still flagged as alive — loop back to poll().
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip():
                _append_event(events, line)

    if buffer.strip():
        _append_event(events, buffer)
    return events, timed_out


# ---------- transcript / metrics extraction -----------------------------------


def _truncate(s: str, limit: int = 2000) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n\n[… {len(s) - limit} chars elided]"


def format_transcript(events: list[dict], prompt: str, skill_name: str | None) -> str:
    """Human-readable markdown of the run — the grader reads this."""
    lines: list[str] = []
    lines.append(f"# Subject transcript")
    lines.append("")
    lines.append(f"**Skill staged:** `{skill_name or '(none — without_skill config)'}`")
    lines.append("")
    lines.append("## Prompt")
    lines.append("")
    lines.append(prompt)
    lines.append("")
    lines.append("## Session")
    lines.append("")

    for evt in events:
        etype = evt.get("type")
        if etype == "system" and evt.get("subtype") == "init":
            skills = evt.get("skills") or []
            lines.append(f"_system/init: skills available → {', '.join(skills) or '(none)'}_")
            lines.append("")
            continue
        if etype == "assistant":
            msg = evt.get("message") or {}
            for c in msg.get("content") or []:
                ctype = c.get("type")
                if ctype == "text":
                    text = (c.get("text") or "").strip()
                    if text:
                        lines.append(text)
                        lines.append("")
                elif ctype == "tool_use":
                    name = c.get("name", "?")
                    inp = c.get("input") or {}
                    inp_s = json.dumps(inp, indent=2, sort_keys=True)
                    lines.append(f"**Tool call: `{name}`**")
                    lines.append("")
                    lines.append("```json")
                    lines.append(_truncate(inp_s))
                    lines.append("```")
                    lines.append("")
                elif ctype == "thinking":
                    # Redact interior reasoning by default — keep transcripts
                    # focused on what the grader can verify.
                    lines.append(f"_(thinking: {len(c.get('thinking') or '')} chars elided)_")
                    lines.append("")
        elif etype == "user":
            msg = evt.get("message") or {}
            blocks = msg.get("content")
            for c in blocks if isinstance(blocks, list) else []:
                if c.get("type") == "tool_result":
                    content = c.get("content")
                    if isinstance(content, list):
                        parts = []
                        for p in content:
                            if isinstance(p, dict) and p.get("type") == "text":
                                parts.append(p.get("text") or "")
                        text = "\n".join(parts)
                    else:
                        text = str(content) if content is not None else ""
                    is_err = c.get("is_error") is True
                    prefix = "Tool result (ERROR)" if is_err else "Tool result"
                    lines.append(f"**{prefix}:**")
                    lines.append("")
                    lines.append("```")
                    lines.append(_truncate(text))
                    lines.append("```")
                    lines.append("")
        elif etype == "result":
            # Final summary event — skip in transcript, we capture it in timing.
            pass

    return "\n".join(lines).strip() + "\n"


def compute_metrics(events: list[dict], transcript_text: str, outputs_dir: Path) -> dict:
    tool_calls: dict[str, int] = {}
    steps = 0
    errors = 0
    files_created: list[str] = []

    for evt in events:
        if evt.get("type") == "assistant":
            msg = evt.get("message") or {}
            had_tool = False
            for c in msg.get("content") or []:
                if c.get("type") == "tool_use":
                    had_tool = True
                    name = c.get("name", "?")
                    tool_calls[name] = tool_calls.get(name, 0) + 1
                    if name in ("Write", "Edit"):
                        p = (c.get("input") or {}).get("file_path")
                        if isinstance(p, str) and p not in files_created:
                            files_created.append(p)
            if had_tool:
                steps += 1
        elif evt.get("type") == "user":
            msg = evt.get("message") or {}
            blocks = msg.get("content")
            for c in blocks if isinstance(blocks, list) else []:
                if c.get("type") == "tool_result" and c.get("is_error"):
                    errors += 1

    output_chars = 0
    if outputs_dir.exists():
        for p in outputs_dir.rglob("*"):
            if p.is_file():
                try:
                    output_chars += p.stat().st_size
                except OSError:
                    pass

    return {
        "tool_calls": tool_calls,
        "total_tool_calls": sum(tool_calls.values()),
        "total_steps": steps,
        "files_created": files_created,
        "errors_encountered": errors,
        "output_chars": output_chars,
        "transcript_chars": len(transcript_text),
    }


def extract_result_summary(events: list[dict]) -> dict:
    """Pull the last `result` event's tokens + duration if present.

    Only the last result event is read, so a multi-turn run records its
    last result's counts. On Claude Code v2.1.277 or later the last
    result's `modelUsage` includes earlier turns' spend (when every earlier
    process exited normally); before that it covers only the last turn.
    The docs name only `total_cost_usd` and `modelUsage` as carrying
    restored spend.

    The per-category counts (USAGE_TOKEN_KEYS) are summed over the event's
    `modelUsage` entries, which include subagent requests; the event's
    `usage` counts only the top-level agent loop and is read only when no
    `modelUsage` entry is a dict carrying one of MODEL_USAGE_KEYS.
    `token_source` names the object read ("modelUsage", "usage", or None
    when the event has neither, in which case the categories read 0). A
    missing key reads as 0, and so does a `modelUsage` count that is not
    an int.

    `total_tokens` keeps its meaning and source: `usage` input + output,
    else a `total_tokens` key if present (none in stored result events),
    else 0, so it stays comparable with earlier runs. With `modelUsage` it
    can be below input_tokens + output_tokens.

    `total_tokens_with_cache` reads the same top-level `usage` (the agent
    loop only, no subagent request, while the per-category counts beside
    it come from `modelUsage`, subagents included) and adds cache reads
    and writes: input + cache read + cache write + output. Codex's
    input_tokens already counts its cached input (parse_trajectory.py,
    harness shapes), so a codex run's value is input + output.
    """
    for evt in reversed(events):
        if evt.get("type") == "result":
            usage = evt.get("usage") or {}
            with_cache = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            if evt.get("harness") != "codex":
                with_cache += (usage.get("cache_read_input_tokens", 0)
                               + usage.get("cache_creation_input_tokens", 0))
            entries = model_usage_entries(evt.get("modelUsage"))
            if entries:
                counts = dict.fromkeys(USAGE_TOKEN_KEYS, 0)
                for per_model in entries:
                    for key, camel in MODEL_USAGE_KEYS.items():
                        counts[key] += token_count(per_model.get(camel))
                token_source = "modelUsage"
            else:
                counts = {key: usage.get(key, 0) for key in USAGE_TOKEN_KEYS}
                token_source = "usage" if isinstance(evt.get("usage"), dict) else None
            return {
                "total_tokens": (
                    (evt.get("usage") or {}).get("input_tokens", 0)
                    + (evt.get("usage") or {}).get("output_tokens", 0)
                ) or evt.get("total_tokens", 0),
                "total_tokens_with_cache": with_cache,
                **counts,
                "token_source": token_source,
                "duration_ms": evt.get("duration_ms", 0),
                "num_turns": evt.get("num_turns", 0),
                "subtype": evt.get("subtype"),
            }
    return {
        "total_tokens": 0,
        "total_tokens_with_cache": 0,
        **dict.fromkeys(USAGE_TOKEN_KEYS, 0),
        "token_source": None,
        "duration_ms": 0,
        "num_turns": 0,
        "subtype": None,
    }


def aggregate_token_usage(
    runs_dir: Path,
    configs: tuple[str, ...] = ("with_skill", "without_skill"),
) -> dict:
    """Sum and average the per-run token counts in each config's timing.json.

    The skill-creator benchmark.json carries one `tokens` value per run (usually `output_chars`);
    this keeps the cache categories visible across a whole run directory.
    It fills the history row's token_usage, which nothing reads; the
    scorecard reads skill_summary.arms.with_skill.tokens_per_run_mean.

    A timing.json whose token_source is None (no token count recorded), or
    that is unreadable or not a JSON object, is skipped, so `runs` and the
    mean cover only runs with a count. One with no token_source key (written
    before the key existed) still counts.

    In a counted run, a missing key, or a value that is not an int, reads as 0. That
    fallback is defensive: run_skill calls
    this only on the fresh runs/<ts> directory it just created, so old and
    new timing.json files are not mixed here.
    """
    keys = ("total_tokens",) + USAGE_TOKEN_KEYS
    out: dict[str, dict] = {}
    for config in configs:
        totals = dict.fromkeys(keys, 0)
        n = 0
        for timing_file in sorted(runs_dir.glob(f"eval-*/{config}/run-*/timing.json")):
            try:
                timing = json.loads(timing_file.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(timing, dict) or timing.get("token_source", "") is None:
                continue
            n += 1
            for key in keys:
                totals[key] += token_count(timing.get(key))
        out[config] = {
            "runs": n,
            "total": totals,
            "mean": {key: (round(totals[key] / n, 1) if n else 0) for key in keys},
        }
    return out


# ---------- fixture staging ----------------------------------------------------


def stage_fixture_files(
    sandbox: Path,
    skill_eval_dir: Path,
    eval_id: int | str,
    files: list[str] | None,
) -> dict[str, str]:
    """Copy fixture files into the sandbox before the subject runs.

    Convention:
      <skill_eval_dir>/files/shared/   -> copied for ALL eval cases
      <skill_eval_dir>/files/eval-<id>/ -> copied only for this eval case

    Both are merged into the sandbox root (shared first, then eval-specific
    overlays so per-eval files can override shared ones).

    Only stages files if:
      1. The eval case declares a non-empty "files" array, AND
      2. The <skill_eval_dir>/files/ directory actually exists on disk.

    <skill_eval_dir> is misc/evals/<member>/ for a member's own case and
    classes/<class>/evals/<suite>/ for a shared class case.

    A link inside a fixture folder is followed (eval 18's tracked
    .claude/skills/terraform-skill link points into the repo) only when it
    resolves to a path that exists inside the repo; any other link raises
    FixtureLinkError before anything is copied.

    Returns each staged file's sandbox-relative POSIX path mapped to the
    sha256 of its staged bytes; empty when nothing was staged.
    snapshot_sandbox_outputs uses it to leave staged files out.
    """
    staged: dict[str, str] = {}
    if not files:
        return staged

    files_root = skill_eval_dir / "files"
    if not files_root.is_dir():
        return staged

    # Stage shared/ first (base layer), then the eval-specific overlay (can
    # override shared files).
    sources = [files_root / "shared", files_root / f"eval-{eval_id}"]
    for source in sources:
        if source.is_dir():
            check_fixture_links(source)
    for source in sources:
        if source.is_dir():
            shutil.copytree(source, sandbox, symlinks=False, dirs_exist_ok=True)

    for source in sources:
        if not source.is_dir():
            continue
        # Walk linked folders too: copytree copied what they hold.
        for dirpath, _dirs, filenames in os.walk(source, followlinks=True):
            for name in filenames:
                rel = Path(dirpath, name).relative_to(source).as_posix()
                staged[rel] = _sha256(sandbox / rel)
    return staged


class FixtureLinkError(RuntimeError):
    """A fixture folder holds a link that leaves the repo, leads nowhere or
    to the repo root or .git, or holds a file that is not a regular file."""


def check_fixture_links(source: Path, repo_root: Path | None = None) -> None:
    """Raise FixtureLinkError for a link under `source` (followed links
    included) that does not resolve to an existing path inside the repo, or
    that resolves to the repo root or into its .git, and for an entry that is
    neither a folder nor a regular file (a FIFO would hang the copy)."""
    root = os.path.realpath(repo_root or REPO_ROOT)
    git_dir = os.path.join(root, ".git")
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(source, followlinks=True):
        real_dir = os.path.realpath(dirpath)
        if real_dir in seen:
            dirnames[:] = []
            continue
        seen.add(real_dir)
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.exists(path) and not os.path.isfile(path):
                raise FixtureLinkError(f"fixture {path} is not a regular file")
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                continue
            target = os.path.realpath(path)
            inside = target.startswith(root + os.sep)
            if target == root or target == git_dir or target.startswith(git_dir + os.sep):
                raise FixtureLinkError(
                    f"fixture link {path} -> {os.readlink(path)} reaches the repo root or .git")
            if real_dir == target or real_dir.startswith(target + os.sep):
                raise FixtureLinkError(
                    f"fixture link {path} -> {os.readlink(path)} points to its own folder or above it")
            if not inside or not os.path.exists(target):
                raise FixtureLinkError(
                    f"fixture link {path} -> {os.readlink(path)} "
                    + ("leaves the repo" if not inside else "leads nowhere"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ignore_links(directory: str, names: list[str]) -> list[str]:
    """copytree ignore callable: leave out every link and every entry that
    is neither a folder nor a regular file (a FIFO the subject made)."""
    out = []
    for n in names:
        path = os.path.join(directory, n)
        if os.path.islink(path) or not (os.path.isdir(path) or os.path.isfile(path)):
            out.append(n)
    return out


# ---------- sandbox snapshot --------------------------------------------------


def snapshot_sandbox_outputs(
    sandbox: Path,
    outputs_dir: Path,
    staged: dict[str, str] | None = None,
) -> None:
    """Copy any files the subject created inside the sandbox (excluding the
    staged .claude/ dir) into outputs_dir so the grader can inspect them.

    `staged` is stage_fixture_files' return. A staged file still byte-identical
    to what was staged is then removed from outputs_dir, so a check on outputs
    cannot pass on fixture text alone. A staged file the subject edited is kept.

    Links are never copied, at the top level or below it: a dangling one
    would crash copytree, and a live one would copy what lies outside the
    sandbox. Nor is an entry that is neither a folder nor a regular file
    (a FIFO). The staged skill folders (STAGED_TOP_DIRS) are left out.
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)
    for item in sandbox.iterdir():
        if item.name in STAGED_TOP_DIRS or item.is_symlink():
            continue
        dest = outputs_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, symlinks=False, dirs_exist_ok=True,
                            ignore=_ignore_links)
        elif item.is_file():
            shutil.copy2(item, dest)
    for rel, digest in (staged or {}).items():
        out = outputs_dir / rel
        if out.is_file() and _sha256(out) == digest:
            out.unlink()


# ---------- subject run -------------------------------------------------------


def run_subject(
    *,
    prompt: str,
    skill_name: str,
    repo_skill_dir: Path,
    with_skill: bool,
    model: str,
    timeout: int,
    run_dir: Path,
    extra_env: dict[str, str] | None,
    elicitation: ElicitationConfig | None = None,
    skill_eval_dir: Path | None = None,
    eval_id: int | str | None = None,
    fixture_files: list[str] | None = None,
    harness: str = "claude",
) -> dict:
    """Execute the subject and persist transcript/outputs/metrics/timing.

    Returns {"transcript_path": ..., "outputs_dir": ..., "ok": bool,
    "reason": ..., "invalid": bool, "exit_codes": [...], "elicitation": ...}.
    A run that is not ok is an invalid run: it timed out, a subject
    process exited non-zero (every turn of a canned multi-turn run is
    read), the stream holds no events or no start event, the harness
    reported an error (stream_invalid_reason), or its fixtures were refused
    (FixtureLinkError). events.jsonl holds the stream in Claude Code
    stream-json form (normalize_events); a kiro or codex run also writes
    its raw stream to raw-events.jsonl.

    A KUBECONFIG in `extra_env` is copied into the run's clean HOME and the
    subject gets the copy, so a live run that writes its kubeconfig (such
    as `aws eks update-kubeconfig`) cannot rewrite the shared file. A PATH
    in `extra_env` reaches the subject, and its dirs that are not on the
    runner's own PATH are bound back read-only inside the wall
    (wall_off_host `ro_dirs`; it skips HOME, ~/.local, a walled folder and
    a folder above one, and checks nothing else), so a caller adds only a
    private dir it created.
    """
    if harness not in HARNESS_ADAPTERS:
        raise ValueError(f"unknown harness: {harness!r} (expected one of {HARNESSES})")
    run_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    ctx = (
        stage_skill_sandbox(skill_name, repo_skill_dir)
        if with_skill
        else stage_empty_sandbox()
    )
    start_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = time.time()

    elicitation = elicitation or ElicitationConfig.from_dict(None)
    multiturn = bool(elicitation.strategy == "canned-multiturn" and elicitation.turns)
    elicitation_note = None
    if multiturn and harness != "claude":
        # Canned answers resume the session after an AskUserQuestion call
        # (elicitation.py); kiro and codex run non-interactive with no such
        # tool, so the case runs as one turn and the run says so.
        multiturn = False
        elicitation_note = f"single turn: {harness} has no AskUserQuestion tool non-interactively"
    raw_events: list[dict] = []
    exit_codes: list[int | None] = []
    stderr: bytes = b""
    timed_out = False
    refused: str | None = None

    with ctx as (sandbox, home):
        if with_skill and harness != "claude":
            link = sandbox / HARNESS_SKILL_DIRS[harness] / skill_name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(repo_skill_dir.resolve())
        # Stage fixture files into the sandbox before running the subject.
        staged: dict[str, str] = {}
        if skill_eval_dir and eval_id is not None and fixture_files:
            try:
                staged = stage_fixture_files(sandbox, skill_eval_dir, eval_id, fixture_files)
            except FixtureLinkError as e:
                refused = f"fixture staging refused: {e}"

        run_extra = dict(extra_env or {})
        if run_extra.get("KUBECONFIG"):
            kube_copy = home / ".kube" / "config"
            kube_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run_extra["KUBECONFIG"], kube_copy)
            kube_copy.chmod(0o600)
            run_extra["KUBECONFIG"] = str(kube_copy)
        # PATH dirs in extra_env that are not on the runner's own PATH (the C1
        # driver's T7 aws shim dir, in a temp dir the wall hides) are bound
        # back read-only; the runner's own entries, spelled exactly as on its
        # PATH, get no extra bind. wall_off_host skips HOME, ~/.local, a walled
        # folder and a folder above one and checks nothing else, so a caller
        # adds only a private dir it created.
        host_path = os.environ.get("PATH", "").split(os.pathsep)
        path_dirs = tuple(d for d in run_extra.get("PATH", "").split(os.pathsep)
                          if d and d not in host_path)

        def subject_env() -> dict[str, str]:
            return harness_env(build_subprocess_env(home, extra=run_extra or None,
                                                    aws_env=_eval_env(timeout)),
                               home, harness)

        staged_skill = repo_skill_dir if with_skill else None
        if refused:
            pass
        elif multiturn:
            cmd_base = wall_off_host(_claude_cmd_base(model), sandbox, home, staged_skill, path_dirs)
            with _recording_popen() as procs:
                raw_events, timed_out, _ = run_multiturn_subject(
                    initial_prompt=prompt,
                    elicitation=elicitation,
                    cmd_base=cmd_base,
                    cwd=str(sandbox),
                    env_for_turn=subject_env,
                    timeout_per_turn=timeout,
                )
            exit_codes = [p.returncode for p in procs]
        else:
            env = subject_env()
            cmd = HARNESS_ADAPTERS[harness](prompt=prompt, model=model, sandbox=sandbox, env=env)
            process = subprocess.Popen(
                wall_off_host(cmd, sandbox, home, staged_skill, path_dirs,
                              rw_dirs=(kiro_data_dir(env),) if harness == "kiro" else ()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(sandbox),
                env=env,
            )
            raw_events, timed_out = drain_stream(process, timeout=timeout)
            exit_codes = [process.returncode]
            if process.stderr:
                try:
                    stderr = process.stderr.read() or b""
                except Exception:
                    stderr = b""

        snapshot_sandbox_outputs(sandbox, outputs_dir, staged)

    end_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    wall = time.time() - t0

    events = normalize_events(raw_events, harness)
    transcript_text = format_transcript(
        events, prompt, skill_name=(skill_name if with_skill else None)
    )
    transcript_path = run_dir / "transcript.md"
    transcript_path.write_text(transcript_text)
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e, separators=(",", ":")) for e in events) + "\n"
    )
    if harness != "claude":
        (run_dir / "raw-events.jsonl").write_text(
            "\n".join(json.dumps(e, separators=(",", ":")) for e in raw_events) + "\n"
        )

    summary = extract_result_summary(events)
    metrics = compute_metrics(events, transcript_text, outputs_dir)
    (outputs_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    timing = {
        "total_tokens": summary["total_tokens"],
        "total_tokens_with_cache": summary["total_tokens_with_cache"],
        **{key: summary[key] for key in USAGE_TOKEN_KEYS},
        "token_source": summary["token_source"],
        "duration_ms": summary["duration_ms"],
        "total_duration_seconds": round(wall, 2),
        "executor_start": start_iso,
        "executor_end": end_iso,
        "executor_duration_seconds": round(wall, 2),
    }
    (run_dir / "timing.json").write_text(json.dumps(timing, indent=2))

    if refused:
        reason = refused
    elif timed_out:
        reason = f"subject timed out after {timeout}s"
    elif any(code != 0 for code in exit_codes):
        reason = f"subject exited {next(c for c in exit_codes if c != 0)}"
    else:
        reason = stream_invalid_reason(raw_events, harness)
    out = {
        "transcript_path": str(transcript_path),
        "outputs_dir": str(outputs_dir),
        "ok": reason is None,
        "reason": reason,
        "invalid": reason is not None,
        "exit_codes": exit_codes,
        "elicitation": elicitation_note,
    }
    if reason is not None:
        out["stderr"] = stderr.decode("utf-8", errors="replace")[-400:]
    return out


# ---------- harness adapters --------------------------------------------------
#
# One function per harness, each returning the subject command for one
# non-interactive run whose stdout is JSON Lines. Every adapter runs under
# the triggering runner's env: build_subprocess_env with the eval-role
# session (eval_aws_env), a clean HOME and no host AWS_* variables, then
# harness_env (codex: no CODEX_DROPPED_VARS, CODEX_HOME in the clean HOME;
# kiro: the parent's XDG data dir, and KIRO_API_KEY when set).


def _claude_cmd_base(model: str) -> list[str]:
    return [
        "claude",
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--permission-mode", "bypassPermissions",
        "--model", model,
    ]


def adapter_claude(*, prompt: str, model: str, sandbox: Path, env: dict[str, str]) -> list[str]:
    """`claude -p` stream-json, as the runner has always run it."""
    base = _claude_cmd_base(model)
    return base[:1] + ["-p", prompt] + base[1:]


def adapter_kiro(*, prompt: str, model: str, sandbox: Path, env: dict[str, str]) -> list[str]:
    """`kiro-cli chat` (kiro-cli 3.5.0 `chat --help`): --output-format
    stream-json gives "The run's ACP events as JSON Lines on stdout" and
    "implies --no-interactive"; --trust-all-tools lets it run tools without
    asking, the counterpart of claude's bypassPermissions; --agent-engine
    v3 pins the engine the stream is read for."""
    return ["kiro-cli", "chat", "--agent-engine", "v3", "--no-interactive",
            "--output-format", "stream-json", "--trust-all-tools", "--model", model, prompt]


def adapter_codex(*, prompt: str, model: str, sandbox: Path, env: dict[str, str]) -> list[str]:
    """`codex exec --json` (codex-cli 0.163.0 `exec --help`): "Print events
    to stdout as JSONL". The sandbox is not a git repo
    (--skip-git-repo-check), no session files are kept (--ephemeral), and
    approvals and Codex's own sandbox are off, the counterpart of claude's
    bypassPermissions (the runner's temp sandbox is the outer fence). The
    model goes to the amazon-bedrock-runtime provider in the eval-role
    session's region."""
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "--ephemeral",
           "--dangerously-bypass-approvals-and-sandbox", "-C", str(sandbox),
           "-c", 'model_provider="amazon-bedrock-runtime"', "-m", model]
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    if region:
        cmd += ["-c", f'model_providers.amazon-bedrock-runtime.aws.region="{region}"']
    return cmd + [prompt]


HARNESS_ADAPTERS = {
    "claude": adapter_claude,
    "kiro": adapter_kiro,
    "codex": adapter_codex,
}


_EVAL_ENV_LOCK = threading.Lock()


def _eval_env(timeout: int) -> dict[str, str]:
    """eval_aws_env under a lock: runs side by side share one eval-role
    session, and one refresh at a time keeps two runs from each minting
    a new one."""
    with _EVAL_ENV_LOCK:
        return eval_aws_env(timeout)


class _PopenRecorder:
    """Stands in for the subprocess module inside elicitation.py while any
    multi-turn run is live, keeping each thread's Popen calls in that
    thread's own list, so each run reads only its own turns' exit codes
    (elicitation.run_multiturn_subject does not return them)."""

    def __init__(self) -> None:
        self.local = threading.local()
        self.lock = threading.Lock()
        self.users = 0
        self.saved: Any = None

    def __getattr__(self, name: str) -> Any:
        return getattr(subprocess, name)

    def Popen(self, *args: Any, **kwargs: Any) -> subprocess.Popen:  # noqa: N802
        proc = subprocess.Popen(*args, **kwargs)
        procs = getattr(self.local, "procs", None)
        if procs is not None:
            procs.append(proc)
        return proc


_RECORDER = _PopenRecorder()


@contextlib.contextmanager
def _recording_popen():
    """The recorder is in place from the first live multi-turn run until
    the last one ends; elicitation.subprocess is then restored."""
    with _RECORDER.lock:
        if _RECORDER.users == 0:
            _RECORDER.saved = elicitation.subprocess
            elicitation.subprocess = _RECORDER
        _RECORDER.users += 1
    _RECORDER.local.procs = procs = []
    try:
        yield procs
    finally:
        _RECORDER.local.procs = None
        with _RECORDER.lock:
            _RECORDER.users -= 1
            if _RECORDER.users == 0:
                elicitation.subprocess = _RECORDER.saved


def _side_by_side(fn: Any, items: list) -> list:
    """fn(item) for every item at the same time, one thread each, the
    results in the items' order whatever order they finish in. It waits
    for every call; then the first call that raised, in item order,
    raises here, as it would have in a serial loop."""
    if len(items) <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        futures = [pool.submit(fn, item) for item in items]
    return [f.result() for f in futures]


# ---------- grader run --------------------------------------------------------


def _build_grader_prompt(
    grader_spec: str,
    expectations: list[str],
    transcript_path: Path,
    outputs_dir: Path,
    run_dir: Path,
) -> str:
    expectations_json = json.dumps(expectations, indent=2)
    return (
        "You are acting as the Grader agent. Follow the spec exactly, then write "
        f"the grading JSON to {run_dir}/grading.json.\n\n"
        "<GRADER_SPEC>\n"
        f"{grader_spec}\n"
        "</GRADER_SPEC>\n\n"
        "<INPUTS>\n"
        f"expectations: {expectations_json}\n"
        f"transcript_path: {transcript_path}\n"
        f"outputs_dir: {outputs_dir}\n"
        "</INPUTS>\n\n"
        "Read the transcript, examine the outputs directory, evaluate each expectation "
        "with evidence, and write the full JSON object per the spec to "
        f"{run_dir}/grading.json. After writing, stop."
    )


def run_grader(
    *,
    expectations: list[str],
    transcript_path: Path,
    outputs_dir: Path,
    run_dir: Path,
    model: str,
    timeout: int,
) -> dict:
    """Invoke the grader as a separate `claude -p` subprocess. The grader
    writes grading.json to run_dir. Returns the parsed grading dict on
    success, else {"error": ...}.
    """
    grader_spec = GRADER_MD.read_text()
    prompt = _build_grader_prompt(
        grader_spec, expectations, transcript_path, outputs_dir, run_dir
    )

    grading_path = run_dir / "grading.json"
    # Fresh slate — the grader must write it this run.
    if grading_path.exists():
        grading_path.unlink()

    with stage_empty_sandbox() as (sandbox, home):
        env = build_subprocess_env(home, aws_env=_eval_env(timeout))
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", "bypassPermissions",
            "--model", model,
        ]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(sandbox),
            env=env,
        )
        events, timed_out = drain_stream(process, timeout=timeout)
        stderr = b""
        if process.stderr:
            try:
                stderr = process.stderr.read() or b""
            except Exception:
                stderr = b""

    if not grading_path.exists():
        # Fallback: maybe the grader emitted the JSON inline. Sweep the
        # final assistant message for a JSON blob.
        for evt in reversed(events):
            if evt.get("type") == "assistant":
                for c in ((evt.get("message") or {}).get("content") or []):
                    if c.get("type") == "text":
                        text = c.get("text") or ""
                        m = re.search(r"\{.*\}", text, re.DOTALL)
                        if m:
                            try:
                                obj = json.loads(m.group(0))
                                if "expectations" in obj:
                                    grading_path.write_text(json.dumps(obj, indent=2))
                                    break
                            except json.JSONDecodeError:
                                continue
                if grading_path.exists():
                    break

    if not grading_path.exists():
        return {
            "error": "grader produced no grading.json",
            "timed_out": timed_out,
            "stderr": stderr.decode("utf-8", errors="replace")[-400:],
        }

    try:
        grading = json.loads(grading_path.read_text())
    except json.JSONDecodeError as e:
        return {"error": f"grading.json invalid JSON: {e}"}
    if not isinstance(grading, dict):
        return {"error": "grading.json is not an object"}

    expectations_raw = grading.get("expectations")
    if not isinstance(expectations_raw, list):
        return {"error": "grading.json missing `expectations` array"}
    for exp in expectations_raw:
        if not isinstance(exp, dict) or "text" not in exp or "passed" not in exp:
            return {"error": f"grading.json expectation missing required fields: {exp}"}

    # Ensure summary is an object with a numeric pass_rate: aggregate_benchmark
    # reads it, and a null pass_rate crashes its stats.
    changed = False
    summary = grading.get("summary")
    if not (isinstance(summary, dict) and isinstance(summary.get("pass_rate"), (int, float))):
        passed = sum(1 for e in expectations_raw if e.get("passed"))
        total = len(expectations_raw)
        grading["summary"] = {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": (passed / total) if total else 0.0,
        }
        changed = True
    # aggregate_benchmark (vendored) calls .get on each of these objects and
    # extends its notes from the three lists, so a grader that writes null
    # (as one does when it has no notes) would crash the benchmark after the
    # run. Each non-object reads as {} and each non-list note as [].
    for key in ("timing", "execution_metrics", "user_notes_summary"):
        if key in grading and not isinstance(grading[key], dict):
            grading[key] = {}
            changed = True
    notes = grading.get("user_notes_summary", {})
    for key in ("uncertainties", "needs_review", "workarounds"):
        if key in notes and not isinstance(notes[key], list):
            notes[key] = []
            changed = True
    if changed:
        grading_path.write_text(json.dumps(grading, indent=2))

    return grading


# ---------- process assertions under a per-assertion limit ------------------


def _assertion_worker(conn: Any, trajectory: Any, assertion: dict) -> None:
    try:
        result = evaluate(trajectory, [assertion]).results[0]
        conn.send(("ok", result.to_dict()))
    except Exception as e:  # reported as that assertion's failure
        conn.send(("error", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def _mp_context() -> Any:
    methods = multiprocessing.get_all_start_methods()
    return multiprocessing.get_context("fork" if "fork" in methods else "spawn")


def evaluate_with_timeouts(
    trajectory: Any,
    assertions: list[dict],
    timeout: float | None = None,
) -> ProcessAssertionResults:
    """evaluate(trajectory, [a]) once per assertion, each in its own worker
    process under `timeout` seconds (default ASSERTION_TIMEOUT_SECONDS),
    merged into one result in the shape evaluate() returns. A worker that
    does not answer in time is killed and its assertion scores failed with
    the evidence and failure_class "timeout"; a worker that raises scores
    failed with the error."""
    timeout = ASSERTION_TIMEOUT_SECONDS if timeout is None else timeout
    ctx = _mp_context()
    results: list[AssertionResult] = []
    for assertion in assertions:
        recv, send = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=_assertion_worker, args=(send, trajectory, assertion))
        proc.start()
        send.close()
        msg = None
        try:
            if recv.poll(timeout):
                msg = recv.recv()
        except EOFError:
            msg = ("error", "worker exited with no result")
        finally:
            recv.close()
            proc.join(1)
            if proc.is_alive():
                proc.kill()
                proc.join()
        if msg is None:
            results.append(AssertionResult(assertion=assertion, passed=False, evidence="timeout",
                                           failure_class="timeout", matching_calls=None))
        elif msg[0] == "ok":
            results.append(AssertionResult(**msg[1]))
        else:
            results.append(AssertionResult(assertion=assertion, passed=False,
                                           evidence=f"assertion raised {msg[1]}",
                                           failure_class="error", matching_calls=None))
    return _merge_assertion_results(results)


def _merge_assertion_results(results: list[AssertionResult]) -> ProcessAssertionResults:
    passed = sum(1 for r in results if r.passed)
    failure_classes: dict[str, int] = {}
    for r in results:
        if r.failure_class:
            failure_classes[r.failure_class] = failure_classes.get(r.failure_class, 0) + 1
    return ProcessAssertionResults(
        results=results, passed=passed, failed=len(results) - passed, total=len(results),
        pass_rate=passed / len(results) if results else 0.0, failure_classes=failure_classes,
    )


def invalid_run_assertions(assertions: list[dict], reason: str) -> ProcessAssertionResults:
    """Every assertion failed for an invalid run, so the process layer
    counts the run instead of dropping it (as the grader layer does: an
    invalid run's grader pass rate is 0 in the pooled rate)."""
    return _merge_assertion_results([
        AssertionResult(assertion=a, passed=False, evidence=f"invalid run: {reason}",
                        failure_class="invalid_run", matching_calls=None)
        for a in assertions
    ])


# ---------- old against new ---------------------------------------------------


class BaseRefError(RuntimeError):
    """The --base-ref cannot be read or a skill cannot be taken from it."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True)


def resolve_base_ref(ref: str) -> str:
    """The commit sha `ref` names, else BaseRefError."""
    r = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if r.returncode != 0:
        raise BaseRefError(f"--base-ref {ref!r} names no commit in {REPO_ROOT}")
    return r.stdout.decode().strip()


def changed_paths(base: str) -> list[str]:
    """The repo paths that differ between commit `base` and HEAD (a rename
    lists both names), else BaseRefError."""
    if base.startswith("-"):
        raise BaseRefError(f"--changed-since {base!r} is not a ref")
    r = _git("diff", "--name-only", "--no-renames", "-z", base, "HEAD", "--")
    if r.returncode != 0:
        raise BaseRefError(f"--changed-since {base!r}: git diff failed: "
                           f"{r.stderr.decode('utf-8', 'replace').strip()}")
    return [p for p in r.stdout.decode().split("\0") if p]


# The gate's own files (its scripts, the Makefile, the grader spec, the
# skill-creator scripts it runs, and the class-membership readers its target
# list is built with): a change to one can change any run key's result, so it
# gates every run key.
GATE_PATHS = ("misc/evals/scripts", "misc/evals/Makefile",
              "skills/skill-creator/agents/grader.md", "skills/skill-creator/scripts",
              "classes/steward/scripts/run_checks.py", "misc/safe_frontmatter.py")


def target_changed(target: dict, paths: list[str]) -> bool:
    """True when a path is under the target's skill folder, its
    misc/evals/<run key>/ folder, the evals/ folder or class.yaml of one of
    its classes or one of GATE_PATHS."""
    roots = ([target["skill_rel"], (EVALS_ROOT / target["run_key"]).relative_to(REPO_ROOT).as_posix()]
             + [f"classes/{c}/{leaf}" for c in target["classes"] for leaf in ("evals", "class.yaml")]
             + list(GATE_PATHS))
    return any(p == r or p.startswith(r + "/") for p in paths for r in roots)


def materialise_skill_at_ref(sha: str, rel_path: str, dest: Path) -> Path | None:
    """Write the folder `rel_path` as it is at commit `sha` under `dest`,
    read from git objects only (git archive; the worktree is not touched).
    Returns the folder, or None when `rel_path` does not exist at `sha`.
    A link, or a member whose name leaves `rel_path`, raises BaseRefError
    (no skill or devops-agent folder holds a link at v1.3.0)."""
    if _git("cat-file", "-e", f"{sha}:{rel_path}").returncode != 0:
        return None
    r = _git("archive", "--format=tar", sha, "--", rel_path)
    if r.returncode != 0:
        raise BaseRefError(f"git archive {sha} {rel_path} failed: "
                           f"{r.stderr.decode('utf-8', 'replace').strip()}")
    prefix = rel_path.rstrip("/") + "/"
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        for member in tar.getmembers():
            name = member.name.rstrip("/")
            parent_dir = member.isdir() and prefix.startswith(name + "/")
            if (name.startswith("/") or ".." in Path(name).parts
                    or not (parent_dir or name == prefix.rstrip("/") or name.startswith(prefix))):
                raise BaseRefError(f"unexpected path in archive: {name}")
            if not (member.isfile() or member.isdir()):
                raise BaseRefError(f"{name} at {sha[:12]} is a link or special file")
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)
    return dest / rel_path


# ---------- targets and shared class cases ------------------------------------


def class_target(run_key: str) -> dict | None:
    return next((t for t in CLASS_TARGETS if t["run_key"] == run_key), None)


def resolve_target(run_key: str) -> dict:
    """Where a run key's skill, own cases, runs and history live.

    A key with a misc/evals/<key>/ folder keeps today's layout. A class
    target with none (a planned member with no suite yet) runs under
    misc/evals/workspace/<key>/."""
    target = class_target(run_key) or {}
    own = EVALS_ROOT / run_key
    own_dir = own if (own / "evals.json").exists() else None
    skill_dir = target.get("skill_dir") or REFUSED_TARGETS.get(run_key, f"skills/{run_key}")
    workspace = (own if own_dir else TARGETS_WORKSPACE / run_key) / "workspace"
    return {
        "run_key": run_key,
        "skill_rel": skill_dir,
        "skill_repo_dir": REPO_ROOT / skill_dir,
        "own_eval_dir": own_dir,
        "classes": list(target.get("classes", [])),
        "blocking": target.get("blocking"),
        "workspace": workspace,
        "refused": CLASS_TARGETS_REFUSED.get(skill_dir),
    }


def load_shared_cases(classes: list[str]) -> list[dict]:
    """The runnable shared cases of each class: every case with a "prompt"
    in classes/<class>/evals/<suite>/evals.json, tagged with its source and
    fixture folder."""
    cases: list[dict] = []
    for cls in classes:
        for suite_json in sorted((CLASSES_ROOT / cls / "evals").glob("*/evals.json")):
            data = json.loads(suite_json.read_text())
            for case in data.get("evals") or []:
                if not isinstance(case, dict) or not case.get("prompt"):
                    continue
                case = dict(case)
                case["_source"] = f"class:{cls}/{suite_json.parent.name}"
                case["_fixture_root"] = suite_json.parent
                cases.append(case)
    return cases


def merge_cases(own: list[dict], shared: list[dict]) -> list[dict]:
    """A member's own cases followed by the shared ones. Shared ids must be
    integers and differ from the member's ids and from each other: run
    folders, the benchmark and the assertion runners key on the id, so a
    repeat would overwrite a run."""
    seen: dict[Any, str] = {}
    for case in own:
        seen[case["id"]] = "own"
    for case in shared:
        cid = case.get("id")
        if not isinstance(cid, int) or isinstance(cid, bool):
            raise ValueError(f"{case['_source']}: shared case id {cid!r} is not an integer")
        if cid in seen:
            raise ValueError(f"{case['_source']}: case id {cid} repeats an id from {seen[cid]}")
        seen[cid] = case["_source"]
    return list(own) + list(shared)


def target_cases(target: dict, include_live_only: bool) -> list[dict]:
    """The cases a run of `target` (resolve_target) runs: its own and its
    classes' shared ones (merge_cases; raises ValueError), without
    live_only cases unless `include_live_only`."""
    own: list[dict] = []
    if target["own_eval_dir"] is not None:
        for case in json.loads((target["own_eval_dir"] / "evals.json").read_text()).get("evals") or []:
            own.append(dict(case, _source="own", _fixture_root=target["own_eval_dir"]))
    cases = merge_cases(own, load_shared_cases(target["classes"]))
    return cases if include_live_only else [c for c in cases if not c.get("live_only")]


# ---------- per-run and per-case results --------------------------------------


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def run_record(run_dir: Path, *, arm: str, k: int, subj: dict, harness: str) -> dict:
    """One run's result, written to run-result.json: valid, pass, tokens and
    wall time. A run passes only when it is valid, every grader expectation
    passed, and its process assertions and artifact validation (when the
    case has them) passed."""
    timing = _read_json(run_dir / "timing.json") or {}
    grading = _read_json(run_dir / "grading.json") or {}
    summary = grading.get("summary") or {}
    total = summary.get("total") or 0
    grader_ok = bool(total) and summary.get("passed") == total
    pa = _read_json(run_dir / "process-assertions.json")
    av = _read_json(run_dir / "artifact-validation.json")
    process_ok = None if pa is None else pa.get("failed") == 0
    artifact_ok = None
    if av is not None:
        s = av.get("summary") or {}
        artifact_ok = (s.get("structural_failed", 0) + s.get("validators_failed", 0)) == 0
    valid = bool(subj.get("ok"))
    recorded = timing.get("token_source") is not None
    record = {
        "arm": arm,
        "run": k,
        "harness": harness,
        "valid": valid,
        "invalid_reason": subj.get("reason"),
        "exit_codes": subj.get("exit_codes"),
        "elicitation": subj.get("elicitation"),
        "grader_pass_rate": summary.get("pass_rate", 0.0),
        "grader_error": grading.get("grader_error"),
        "process_passed": process_ok,
        "artifact_passed": artifact_ok,
        "pass": valid and grader_ok and process_ok is not False and artifact_ok is not False,
        # None when the run recorded no token count (timing.json token_source
        # None), never 0.
        "tokens": token_count(timing.get("total_tokens")) if recorded else None,
        "token_usage": {key: token_count(timing.get(key)) if recorded else None
                        for key in USAGE_TOKEN_KEYS},
        "token_source": timing.get("token_source"),
        # None when the run wrote no timing.json time, never 0.
        "wall_seconds": timing.get("total_duration_seconds"),
    }
    (run_dir / "run-result.json").write_text(json.dumps(record, indent=2))
    return record


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _mean_recorded(values: list) -> float | None:
    """Mean of the values that are not None; None when every one is."""
    got = [v for v in values if v is not None]
    return _mean(got) if got else None


def summarize_arm(records: list[dict], k: int) -> dict:
    """Pass@k for one case and arm: pass_at_k when any of the k runs passed,
    pass_all_k when all k ran valid and passed (pass^k). Invalid runs never
    pass; a case with no valid run fails."""
    passes = sum(1 for r in records if r["pass"])
    valid = [r for r in records if r["valid"]]
    return {
        "runs": len(records),
        "valid_runs": len(valid),
        "passes": passes,
        "pass_at_k": passes > 0,
        "pass_all_k": len(records) == k and passes == k,
        "pass_rate_mean": _mean([r["grader_pass_rate"] for r in records]),
        "tokens_per_run": [r["tokens"] for r in records],
        "tokens_mean": _mean_recorded([r["tokens"] for r in records]),
        "token_usage_mean": {key: _mean_recorded([r["token_usage"][key] for r in records])
                             for key in USAGE_TOKEN_KEYS},
        "wall_seconds_per_run": [r["wall_seconds"] for r in records],
        "wall_seconds_mean": _mean_recorded([r["wall_seconds"] for r in records]),
        "invalid_reasons": [r["invalid_reason"] for r in records if not r["valid"]],
    }


def summarize_case(eval_id: Any, source: str, by_arm: dict[str, list[dict]],
                   base_arm: str, k: int) -> dict:
    """One case's result across both arms. `pass` is the new arm's
    pass_at_k; `regressed` is True when the base arm passed and the new one
    did not."""
    arms = {arm: summarize_arm(recs, k) for arm, recs in by_arm.items()}
    new = arms.get(NEW_ARM) or summarize_arm([], k)
    base = arms.get(base_arm) or summarize_arm([], k)
    return {
        "eval_id": eval_id,
        "source": source,
        "arms": arms,
        "pass": new["pass_at_k"],
        "regressed": base["pass_at_k"] and not new["pass_at_k"],
    }


def summarize_skill(cases: list[dict], base_arm: str) -> dict:
    out: dict[str, Any] = {"cases": len(cases),
                           "cases_passed": sum(1 for c in cases if c["pass"]),
                           "cases_regressed": sum(1 for c in cases if c["regressed"]),
                           "arms": {}}
    for arm in (NEW_ARM, base_arm):
        arm_cases = [c["arms"][arm] for c in cases if arm in c["arms"]]
        tokens = [t for a in arm_cases for t in a["tokens_per_run"]]
        walls = [w for a in arm_cases for w in a["wall_seconds_per_run"]]
        out["arms"][arm] = {
            "cases_pass_at_k": sum(1 for a in arm_cases if a["pass_at_k"]),
            "cases_pass_all_k": sum(1 for a in arm_cases if a["pass_all_k"]),
            "runs": sum(a["runs"] for a in arm_cases),
            "invalid_runs": sum(a["runs"] - a["valid_runs"] for a in arm_cases),
            "tokens_per_run_mean": _mean_recorded(tokens),
            "wall_seconds_per_run_mean": _mean_recorded(walls),
        }
    return out


# ---------- history -----------------------------------------------------------


def history_path(skill: str) -> Path:
    return HISTORY_DIR / f"{skill}.jsonl"


def read_history(skill: str) -> list[dict]:
    path = history_path(skill)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_history(skill: str, entry: dict) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_history(skill)
    rows.append(entry)
    rows = rows[-HISTORY_CAP:]
    path = history_path(skill)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            f.write("\n")


# ---------- benchmark --------------------------------------------------------


def run_benchmark(skill: str, benchmark_dir: Path, skill_path: Path | None = None) -> None:
    """Shell out to `make benchmark-<skill>`. A target with no
    misc/evals/<skill>/ folder has no make target, so its benchmark runs
    aggregate_benchmark directly with the same arguments."""
    if skill_path is None:
        cmd = ["make", "-C", str(EVALS_ROOT), f"benchmark-{skill}", f"BENCHMARK_DIR={benchmark_dir}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
    else:
        cmd = [sys.executable, "-m", "scripts.aggregate_benchmark", str(benchmark_dir),
               "--skill-name", skill, "--skill-path", str(skill_path)]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SC_DIR))
    if r.returncode != 0:
        sys.stderr.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise RuntimeError(f"benchmark-{skill} failed")


def update_latest_symlink(skill: str, runs_dir: Path, workspace: Path | None = None) -> None:
    latest = (workspace or EVALS_ROOT / skill / "workspace") / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    # Symlink relative so it survives a repo move.
    latest.symlink_to(runs_dir.relative_to(latest.parent))


# ---------- main --------------------------------------------------------------


def run_skill(
    skill: str,
    *,
    model: str,
    runs: int | None,
    include_live_only: bool,
    subject_timeout: int | None,
    grader_timeout: int,
    extra_env: dict[str, str] | None,
    harness: str = "claude",
    base_ref: str | None = None,
    base_sha: str | None = None,
    subject_model_id: str | None = None,
) -> dict:
    """Run one run key's cases: its own misc/evals/<key>/evals.json cases
    and the shared cases of its classes, on two arms: with_skill (the
    skill as it is now) against the base arm, which is the skill as it was
    at `base_sha` (base_skill), or without_skill when `base_sha` is None or
    the skill does not exist there. Each case runs `runs` times per
    arm, default regression.pass_k from .skilleval.yaml. The subject runs
    on `subject_model_id` (default `model`), the grader on `model`."""
    target = resolve_target(skill)
    if target["refused"]:
        return {"skill": skill, "error": target["refused"]}
    skill_repo_dir = target["skill_repo_dir"]
    skill_eval_dir = target["own_eval_dir"]
    if skill_eval_dir is None and class_target(skill) is None:
        return {"skill": skill, "error": f"missing {EVALS_ROOT / skill / 'evals.json'}"}

    # Resolve effective subject timeout: CLI override > .skilleval.yaml > 600
    skill_config = load_skilleval_config(skill)
    if subject_timeout is not None:
        effective_timeout = subject_timeout
    else:
        effective_timeout = skill_config.timeout
    runs = runs if runs is not None else skill_config.pass_k

    try:
        prompts = target_cases(target, include_live_only)
    except ValueError as e:
        return {"skill": skill, "error": str(e)}
    if not prompts:
        return {"skill": skill, "skipped": "no fixture-free prompts (all are live_only)"}

    skill_name, _description = read_skill_meta(skill_repo_dir)

    base_tmp = Path(tempfile.mkdtemp(prefix="evals-base-ref-"))
    try:
        base_dir = (materialise_skill_at_ref(base_sha, target["skill_rel"], base_tmp)
                    if base_sha else None)
        base_arm = BASE_ARM if base_dir is not None else WITHOUT_ARM
        base_name = read_skill_meta(base_dir)[0] if base_dir is not None else None
        return _run_cases(
            skill, target, prompts, skill_name=skill_name, base_arm=base_arm,
            base_dir=base_dir, base_name=base_name, base_ref=base_ref, base_sha=base_sha,
            model=model, runs=runs, timeout=effective_timeout, grader_timeout=grader_timeout,
            extra_env=extra_env, harness=harness, subject_model_id=subject_model_id or model,
        )
    finally:
        shutil.rmtree(base_tmp, ignore_errors=True)


def _run_cases(
    skill: str,
    target: dict,
    prompts: list[dict],
    *,
    skill_name: str,
    base_arm: str,
    base_dir: Path | None,
    base_name: str | None,
    base_ref: str | None,
    base_sha: str | None,
    model: str,
    runs: int,
    timeout: int,
    grader_timeout: int,
    extra_env: dict[str, str] | None,
    harness: str,
    subject_model_id: str | None = None,
) -> dict:
    """Run every case on both arms, one arm after the other. On each arm
    the case's `runs` subjects run side by side, one thread each; the
    process assertions and artifact checks then run in this thread once
    every subject has ended (no thread is live when they fork); then the
    graders of the runs left valid run side by side. Each run keeps its own
    sandbox, clean HOME and bwrap wall (fresh temp dirs per run), its own
    run-<k> folder and its own timing.json (its own wall time and tokens),
    and records are kept in run order, so the report is the one a serial
    run of the same results gives. A run that fails or times out is an
    invalid run and the others go on; a throttle the harness does not
    recover from fails that run alone. An exception in one run (such as a
    refused eval-role refresh) is raised once the others have ended."""
    skill_repo_dir = target["skill_repo_dir"]
    effective_timeout = timeout
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    runs_dir = target["workspace"] / "runs" / ts
    runs_dir.mkdir(parents=True, exist_ok=True)

    per_prompt: list[dict] = []
    cases: list[dict] = []
    for p in prompts:
        eval_id = p["id"]
        eval_dir = runs_dir / f"eval-{eval_id}"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "eval_metadata.json").write_text(
            json.dumps(
                {
                    "eval_id": eval_id,
                    "eval_name": p.get("prompt", "")[:60],
                    "prompt": p["prompt"],
                    "expectations": p["expectations"],
                    "source": p["_source"],
                },
                indent=2,
            )
        )

        by_arm: dict[str, list[dict]] = {}
        for config in (NEW_ARM, base_arm):
            config_dir = eval_dir / config
            config_dir.mkdir(exist_ok=True)
            run_dirs = [config_dir / f"run-{k}" for k in range(1, runs + 1)]
            for k in range(1, runs + 1):
                print(
                    f"[task] {skill} eval-{eval_id} {config} run-{k} (subject)",
                    file=sys.stderr,
                )

            def subject(run_dir: Path) -> dict:
                return run_subject(
                    prompt=p["prompt"],
                    skill_name=(base_name if config == BASE_ARM else skill_name),
                    repo_skill_dir=(base_dir if config == BASE_ARM else skill_repo_dir),
                    with_skill=(config != WITHOUT_ARM),
                    model=subject_model_id or model,
                    timeout=effective_timeout,
                    run_dir=run_dir,
                    extra_env=extra_env,
                    elicitation=ElicitationConfig.from_dict(p.get("elicitation")),
                    skill_eval_dir=p["_fixture_root"],
                    eval_id=eval_id,
                    fixture_files=p.get("files"),
                    harness=harness,
                )

            # The case's k runs on this arm run side by side; the checks
            # below run in this thread once all have ended, then the
            # graders run side by side (see the docstring of _run_cases).
            subjects = _side_by_side(subject, run_dirs)
            to_grade: list[int] = []
            for k, (run_dir, subj) in enumerate(zip(run_dirs, subjects), 1):
                process_assertion_defs = p.get("process_assertions")
                events_file = run_dir / "events.jsonl"
                if subj["ok"] and process_assertion_defs and not events_file.exists():
                    subj = subjects[k - 1] = dict(subj, ok=False, invalid=True,
                                                  reason="events.jsonl missing")
                if not subj["ok"]:
                    print(
                        f"[task]   {skill} eval-{eval_id} {config} run-{k} subject failed: "
                        f"{subj.get('reason')}",
                        file=sys.stderr,
                    )
                    (run_dir / "grading.json").write_text(
                        json.dumps(
                            {
                                "expectations": [
                                    {
                                        "text": e,
                                        "passed": False,
                                        "evidence": f"subject failed: {subj.get('reason')}",
                                    }
                                    for e in p["expectations"]
                                ],
                                "summary": {
                                    "passed": 0,
                                    "failed": len(p["expectations"]),
                                    "total": len(p["expectations"]),
                                    "pass_rate": 0.0,
                                },
                                "subject_error": subj.get("reason"),
                                "invalid_run": True,
                            },
                            indent=2,
                        )
                    )
                    if process_assertion_defs:
                        (run_dir / "process-assertions.json").write_text(json.dumps(
                            invalid_run_assertions(process_assertion_defs,
                                                   subj.get("reason") or "").to_dict(),
                            indent=2))
                    continue

                # --- Layer 1: Process assertions (deterministic, no LLM) ---
                if process_assertion_defs:
                    run_events = []
                    for line in events_file.read_text().splitlines():
                        if line.strip():
                            try:
                                run_events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                    trajectory = parse_events(run_events)
                    pa_results = evaluate_with_timeouts(trajectory, process_assertion_defs)
                    (run_dir / "process-assertions.json").write_text(
                        json.dumps(pa_results.to_dict(), indent=2)
                    )
                    print(
                        f"[task]   {skill} eval-{eval_id} {config} run-{k} process assertions: "
                        f"{pa_results.passed}/{pa_results.total} passed",
                        file=sys.stderr,
                    )

                # --- Layer 2: Artifact validation (deterministic, no LLM) ---
                artifact_assertion_defs = p.get("artifact_assertions")
                if artifact_assertion_defs:
                    outputs_path = Path(subj["outputs_dir"])
                    if outputs_path.exists():
                        repo_root = Path(__file__).resolve().parent.parent.parent
                        av_results = validate_artifacts(
                            outputs_dir=outputs_path,
                            assertions_config=artifact_assertion_defs,
                            repo_root=repo_root,
                        )
                        (run_dir / "artifact-validation.json").write_text(
                            json.dumps(av_results.to_dict(), indent=2)
                        )
                        av_passed = av_results.structural_passed + av_results.validators_passed
                        av_failed = av_results.structural_failed + av_results.validators_failed
                        print(
                            f"[task]   {skill} eval-{eval_id} {config} run-{k} artifact validation: "
                            f"{av_passed}/{av_passed + av_failed} passed"
                            f" ({av_results.overall_pass_rate:.0%})",
                            file=sys.stderr,
                        )

                print(
                    f"[task] {skill} eval-{eval_id} {config} run-{k} (grader)",
                    file=sys.stderr,
                )
                to_grade.append(k)

            def grade(k: int) -> dict:
                return run_grader(
                    expectations=p["expectations"],
                    transcript_path=Path(subjects[k - 1]["transcript_path"]),
                    outputs_dir=Path(subjects[k - 1]["outputs_dir"]),
                    run_dir=run_dirs[k - 1],
                    model=model,
                    timeout=grader_timeout,
                )

            for k, grading in zip(to_grade, _side_by_side(grade, to_grade)):
                run_dir = run_dirs[k - 1]
                if "error" in grading:
                    print(f"[task]   {skill} eval-{eval_id} {config} run-{k} grader failed: "
                          f"{grading['error']}", file=sys.stderr)
                    (run_dir / "grading.json").write_text(
                        json.dumps(
                            {
                                "expectations": [
                                    {
                                        "text": e,
                                        "passed": False,
                                        "evidence": f"grader failed: {grading['error']}",
                                    }
                                    for e in p["expectations"]
                                ],
                                "summary": {
                                    "passed": 0,
                                    "failed": len(p["expectations"]),
                                    "total": len(p["expectations"]),
                                    "pass_rate": 0.0,
                                },
                                "grader_error": grading["error"],
                            },
                            indent=2,
                        )
                    )
            by_arm[config] = [run_record(run_dir, arm=config, k=k, subj=subj, harness=harness)
                              for k, (run_dir, subj) in enumerate(zip(run_dirs, subjects), 1)]
        per_prompt.append({"eval_id": eval_id, "prompt": p["prompt"][:80]})
        cases.append(summarize_case(eval_id, p["_source"], by_arm, base_arm, runs))

    skill_summary = summarize_skill(cases, base_arm)
    (runs_dir / "cases.json").write_text(json.dumps(
        {"run_key": skill, "harness": harness, "base_arm": base_arm, "pass_k": runs,
         "cases": cases, "skill_summary": skill_summary}, indent=2))

    run_benchmark(skill, runs_dir,
                  skill_path=None if target["own_eval_dir"] else skill_repo_dir)
    update_latest_symlink(skill, runs_dir, target["workspace"])

    benchmark = json.loads((runs_dir / "benchmark.json").read_text())
    rs = benchmark.get("run_summary") or {}
    # Pooled grader pass rate per arm; an invalid run counts in it as 0.
    with_pr = (rs.get(NEW_ARM) or {}).get("pass_rate") or {}
    base_pr = (rs.get(base_arm) or {}).get("pass_rate") or {}
    delta = with_pr.get("mean", 0) - base_pr.get("mean", 0)
    ran_without = base_arm == WITHOUT_ARM

    entry = {
        "kind": "task",
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "subject_model": subject_model_id or model,
        "runs_per_prompt": runs,
        "with_skill_mean": with_pr.get("mean", 0),
        "with_skill_stddev": with_pr.get("stddev", 0),
        # None when this run's base arm was base_skill (no without arm ran).
        "without_skill_mean": base_pr.get("mean", 0) if ran_without else None,
        "without_skill_stddev": base_pr.get("stddev", 0) if ran_without else None,
        # with_skill mean less the base arm's mean (without_skill or base_skill).
        "delta": round(delta, 4),
        "eval_ids": [p["id"] for p in prompts],
        "token_usage": aggregate_token_usage(runs_dir, configs=(NEW_ARM, base_arm)),
        "run_key": skill,
        "skill_dir": target["skill_rel"],
        "blocking": target["blocking"],
        "harness": harness,
        "pass_k": runs,
        "base_ref": base_ref,
        "base_ref_sha": base_sha,
        "baseline_arm": base_arm,
        "comparison": "new_vs_base" if base_arm == BASE_ARM else "new_vs_without",
        "base_skill_mean": None if ran_without else base_pr.get("mean", 0),
        "base_skill_stddev": None if ran_without else base_pr.get("stddev", 0),
        "cases": cases,
        "skill_summary": skill_summary,
    }
    append_history(skill, entry)

    return {
        "skill": skill,
        "runs_dir": str(runs_dir),
        "benchmark": benchmark.get("run_summary"),
        "history_entry": entry,
    }


def discover_skills() -> list[str]:
    return sorted(
        child.name
        for child in EVALS_ROOT.iterdir()
        if child.is_dir()
        and child.name not in {"_template", "workspace", "scripts", "history", ".secrets"}
        and not child.name.startswith(".")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skill", help="Run only this skill")
    parser.add_argument("--runs", type=int, default=None,
                        help="Runs per (case x arm). Default: the skill's regression.pass_k "
                             "in .skilleval.yaml (3 when unset).")
    parser.add_argument("--harness", choices=HARNESSES, default="claude",
                        help="Subject harness: claude (claude -p), kiro (kiro-cli chat) "
                             "or codex (codex exec). The grader is claude -p on every harness.")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF,
                        help=f"Git ref the base arm takes the skill from (default {DEFAULT_BASE_REF}). "
                             "A skill absent there runs against without_skill; "
                             "'none' runs with_skill against without_skill.")
    parser.add_argument("--list-targets", action="store_true",
                        help="Print each run key (misc/evals skills and class targets) that has "
                             "a case to run (live_only cases count only with "
                             "--include-live-only) as JSON lines and exit; the others are named "
                             "on stderr. Runs nothing.")
    parser.add_argument("--changed-since", default=None, metavar="REF",
                        help="With --list-targets: only the run keys with a file changed between "
                             "REF and HEAD under the skill folder, misc/evals/<run key>/ or a "
                             "class's evals/ folder; a change to the gate's own scripts, the "
                             "Makefile or the grader spec lists every run key.")
    parser.add_argument("--include-live-only", action="store_true",
                        help="Include prompts marked live_only=true")
    parser.add_argument("--gate", action="store_true",
                        help="The merge gate's run: refuse before any model call unless each "
                             "case runs three times (--runs, else regression.pass_k).")
    parser.add_argument("--model", default=None,
                        help="The grader's model, and the claude subject's (a Bedrock id). "
                             "Default comes from the Makefile.")
    parser.add_argument("--subject-model", default=None,
                        help="The subject's model on any harness; default --model on claude, "
                             f"else codex {HARNESS_SUBJECT_MODELS['codex']}, "
                             f"kiro {HARNESS_SUBJECT_MODELS['kiro']}.")
    parser.add_argument("--subject-timeout", type=int, default=None,
                        help="Subject timeout in seconds. Overrides per-skill .skilleval.yaml timeout. "
                             "If not set, uses .skilleval.yaml timeout (default 600).")
    parser.add_argument("--grader-timeout", type=int, default=600)
    parser.add_argument("--kubeconfig", default=None,
                        help="KUBECONFIG path exported into the subject subprocess")
    args = parser.parse_args()
    if args.runs is not None and args.runs < 1:
        parser.error("--runs must be 1 or more")

    skills = discover_skills()
    if args.changed_since is not None and not args.list_targets:
        parser.error("--changed-since needs --list-targets")
    if args.list_targets:
        paths = None
        if args.changed_since is not None:
            try:
                paths = changed_paths(args.changed_since)
            except BaseRefError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
        keyed: set[str] = set()
        for key in sorted(set(skills) | {t["run_key"] for t in CLASS_TARGETS} | set(REFUSED_TARGETS)):
            t = resolve_target(key)
            keyed.add(t["skill_rel"])
            if paths is not None and not target_changed(t, paths):
                continue
            try:
                runnable = bool(t["refused"]) or bool(target_cases(t, args.include_live_only))
            except ValueError:
                runnable = True  # listed, so a run reports the error
            if not runnable:
                print(f"[gate] {key} changed but has no runnable case: not gated" if paths is not None
                      else f"[task] {key}: no runnable case", file=sys.stderr)
                continue
            print(json.dumps({"run_key": key, "skill_dir": t["skill_rel"],
                              "own_cases": t["own_eval_dir"] is not None,
                              "classes": t["classes"], "blocking": t["blocking"]}))
        # A changed skill folder no run key covers is named too, so
        # gate-changed never reads it as gated.
        for rel in sorted({"/".join(p.split("/")[:2]) for p in paths or []
                           if p.startswith("skills/") and p.count("/") >= 2} - keyed):
            print(f"[gate] {rel} changed but has no run key: not gated", file=sys.stderr)
        return 0
    if args.skill:
        if (args.skill not in skills and class_target(args.skill) is None
                and args.skill not in REFUSED_TARGETS):
            print(f"unknown skill: {args.skill}", file=sys.stderr)
            return 2
        skills = [args.skill]
    if args.gate:
        for s in skills:
            k = args.runs if args.runs is not None else load_skilleval_config(s).pass_k
            if k != 3:
                print(f"error: the gate scores three runs per case; {s} would run {k} "
                      "(set regression.pass_k to 3, or leave RUNS_PER_PROMPT empty)",
                      file=sys.stderr)
                return 2

    model = args.model or _resolve_makefile_default("MODEL") or "global.anthropic.claude-opus-4-6-v1"
    subject = subject_model(args.harness, model, args.subject_model)

    extra_env: dict[str, str] = {}
    if args.kubeconfig:
        kcp = Path(args.kubeconfig).resolve()
        if not kcp.exists():
            print(f"kubeconfig not found: {kcp}", file=sys.stderr)
            return 2
        extra_env["KUBECONFIG"] = str(kcp)
    timeouts = [(args.grader_timeout, "--grader-timeout")] + (
        [(args.subject_timeout, "--subject-timeout")] if args.subject_timeout is not None
        else [(load_skilleval_config(s).timeout, f"{s}/.skilleval.yaml") for s in skills]
    )
    longest, source = max(timeouts, key=lambda t: t[0])
    version_error = check_cli_versions(["claude", args.harness])  # the grader is claude -p
    if version_error:
        print(f"error: {version_error}", file=sys.stderr)
        return 2
    try:
        set_eval_credentials(mint_eval_role_credentials(timeout=longest, source=source))
    except EvalCredentialError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print("[task] eval-role session checked against ~/.apex-eval/expected-account", file=sys.stderr)

    base_ref = None if args.base_ref.lower() in ("", "none") else args.base_ref
    base_sha = None
    if base_ref:
        try:
            base_sha = resolve_base_ref(base_ref)
        except BaseRefError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    outcomes = []
    for skill in skills:
        print(f"[task] === {skill} ===", file=sys.stderr)
        try:
            result = run_skill(
                skill,
                model=model,
                runs=args.runs,
                include_live_only=args.include_live_only,
                subject_timeout=args.subject_timeout,
                grader_timeout=args.grader_timeout,
                extra_env=extra_env or None,
                harness=args.harness,
                base_ref=base_ref,
                base_sha=base_sha,
                subject_model_id=subject,
            )
        except EvalCredentialError as e:
            print(f"error: {skill}: eval-role session refresh failed, stopping: {e}", file=sys.stderr)
            return 2
        except BaseRefError as e:
            result = {"skill": skill, "error": str(e)}
        outcomes.append(result)
        if "error" in result:
            print(f"[task] {skill}: ERROR {result['error']}", file=sys.stderr)
        elif "skipped" in result:
            print(f"[task] {skill}: skipped ({result['skipped']})", file=sys.stderr)
        else:
            e = result["history_entry"]
            base_mean = (e["without_skill_mean"] if e["without_skill_mean"] is not None
                         else e["base_skill_mean"])
            s = e["skill_summary"]
            print(
                f"[task] {skill}: with={e['with_skill_mean']:.2f} "
                f"{e['baseline_arm']}={base_mean:.2f} "
                f"delta={e['delta']:+.2f} cases passed {s['cases_passed']}/{s['cases']}, "
                f"regressed {s['cases_regressed']}",
                file=sys.stderr,
            )

    print(json.dumps(outcomes, indent=2, default=str))
    return 0 if all("error" not in o for o in outcomes) else 1


def _resolve_makefile_default(var: str) -> str | None:
    try:
        r = subprocess.run(
            ["make", "-C", str(EVALS_ROOT), "--no-print-directory", "-pn"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    if r.returncode not in (0, 2):
        return None
    m = re.search(rf"^{re.escape(var)}\s*\??=\s*(.+)$", r.stdout, re.MULTILINE)
    return m.group(1).strip() if m else None


if __name__ == "__main__":
    sys.exit(main())
