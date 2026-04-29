#!/usr/bin/env python3
"""Task-axis runner for misc/evals/ (PLAN §2).

For each prompt in <skill>/evals.json (skipping "live_only": true entries
unless --include-live-only), for each config in {with_skill, without_skill},
for k in 1..--runs:

  1. Stage a sandbox (stage_skill_sandbox or stage_empty_sandbox) with a
     clean HOME, plus optional KUBECONFIG and read-only AWS session creds
     exported into the subprocess env so skills that touch real clusters
     can do so *safely* (reads only, API-server- and IAM-enforced).
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
  2  invalid inputs (missing evals.json, no fixture-free prompts, etc.)
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from run_triggering import (
    build_subprocess_env,
    stage_empty_sandbox,
    stage_skill_sandbox,
    read_skill_meta,
)

EVALS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_ROOT.parent.parent
HISTORY_DIR = EVALS_ROOT / "history"
HISTORY_CAP = 50
GRADER_MD = REPO_ROOT / "skills" / "skill-creator" / "agents" / "grader.md"


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
            msg = evt.get("message", {})
            for c in msg.get("content", []) or []:
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
            msg = evt.get("message", {})
            for c in msg.get("content", []) or []:
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
            msg = evt.get("message", {})
            had_tool = False
            for c in msg.get("content", []) or []:
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
            msg = evt.get("message", {})
            for c in msg.get("content", []) or []:
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
    """Pull the `result` event's tokens + duration if present."""
    for evt in reversed(events):
        if evt.get("type") == "result":
            return {
                "total_tokens": (
                    evt.get("usage", {}).get("input_tokens", 0)
                    + evt.get("usage", {}).get("output_tokens", 0)
                ) or evt.get("total_tokens", 0),
                "duration_ms": evt.get("duration_ms", 0),
                "num_turns": evt.get("num_turns", 0),
                "subtype": evt.get("subtype"),
            }
    return {"total_tokens": 0, "duration_ms": 0, "num_turns": 0, "subtype": None}


# ---------- sandbox snapshot --------------------------------------------------


def snapshot_sandbox_outputs(sandbox: Path, outputs_dir: Path) -> None:
    """Copy any files the subject created inside the sandbox (excluding the
    staged .claude/ dir) into outputs_dir so the grader can inspect them.
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)
    for item in sandbox.iterdir():
        if item.name == ".claude":
            continue
        dest = outputs_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, symlinks=False, dirs_exist_ok=True)
        elif item.is_file():
            shutil.copy2(item, dest)


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
) -> dict:
    """Execute the subject and persist transcript/outputs/metrics/timing.

    Returns {"transcript_path": ..., "outputs_dir": ..., "ok": bool, "reason": ...}.
    """
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

    with ctx as (sandbox, home):
        env = build_subprocess_env(home, extra=extra_env)
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
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

        snapshot_sandbox_outputs(sandbox, outputs_dir)

    end_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    wall = time.time() - t0

    transcript_text = format_transcript(
        events, prompt, skill_name=(skill_name if with_skill else None)
    )
    transcript_path = run_dir / "transcript.md"
    transcript_path.write_text(transcript_text)
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e, separators=(",", ":")) for e in events) + "\n"
    )

    summary = extract_result_summary(events)
    metrics = compute_metrics(events, transcript_text, outputs_dir)
    (outputs_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    timing = {
        "total_tokens": summary["total_tokens"],
        "duration_ms": summary["duration_ms"],
        "total_duration_seconds": round(wall, 2),
        "executor_start": start_iso,
        "executor_end": end_iso,
        "executor_duration_seconds": round(wall, 2),
    }
    (run_dir / "timing.json").write_text(json.dumps(timing, indent=2))

    if timed_out:
        return {
            "transcript_path": str(transcript_path),
            "outputs_dir": str(outputs_dir),
            "ok": False,
            "reason": f"subject timed out after {timeout}s",
            "stderr": stderr.decode("utf-8", errors="replace")[-400:],
        }
    if process.returncode != 0:
        return {
            "transcript_path": str(transcript_path),
            "outputs_dir": str(outputs_dir),
            "ok": False,
            "reason": f"subject exited {process.returncode}",
            "stderr": stderr.decode("utf-8", errors="replace")[-400:],
        }
    return {
        "transcript_path": str(transcript_path),
        "outputs_dir": str(outputs_dir),
        "ok": True,
        "reason": None,
    }


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
        env = build_subprocess_env(home)
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
                for c in (evt.get("message", {}).get("content") or []):
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

    expectations_raw = grading.get("expectations")
    if not isinstance(expectations_raw, list):
        return {"error": "grading.json missing `expectations` array"}
    for exp in expectations_raw:
        if not isinstance(exp, dict) or "text" not in exp or "passed" not in exp:
            return {"error": f"grading.json expectation missing required fields: {exp}"}

    # Ensure summary is present — aggregate_benchmark reads it.
    if "summary" not in grading or "pass_rate" not in grading.get("summary", {}):
        passed = sum(1 for e in expectations_raw if e.get("passed"))
        total = len(expectations_raw)
        grading["summary"] = {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": (passed / total) if total else 0.0,
        }
        grading_path.write_text(json.dumps(grading, indent=2))

    return grading


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


# ---------- AWS read-only session --------------------------------------------


def mint_federation_token(policy_file: Path, name: str, duration: int) -> dict:
    """Run `aws sts get-federation-token` with a session policy."""
    r = subprocess.run(
        [
            "aws", "sts", "get-federation-token",
            "--name", name,
            "--policy", f"file://{policy_file}",
            "--duration-seconds", str(duration),
            "--output", "json",
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"get-federation-token failed: {r.stderr.strip()}")
    return json.loads(r.stdout)["Credentials"]


# ---------- benchmark --------------------------------------------------------


def run_benchmark(skill: str, benchmark_dir: Path) -> None:
    """Shell out to `make benchmark-<skill>`."""
    cmd = ["make", "-C", str(EVALS_ROOT), f"benchmark-{skill}", f"BENCHMARK_DIR={benchmark_dir}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise RuntimeError(f"benchmark-{skill} failed")


def update_latest_symlink(skill: str, runs_dir: Path) -> None:
    latest = EVALS_ROOT / skill / "workspace" / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    # Symlink relative so it survives a repo move.
    latest.symlink_to(runs_dir.relative_to(latest.parent))


# ---------- main --------------------------------------------------------------


def run_skill(
    skill: str,
    *,
    model: str,
    runs: int,
    include_live_only: bool,
    subject_timeout: int,
    grader_timeout: int,
    extra_env: dict[str, str] | None,
) -> dict:
    skill_eval_dir = EVALS_ROOT / skill
    skill_repo_dir = REPO_ROOT / "skills" / skill
    evals_json = skill_eval_dir / "evals.json"
    if not evals_json.exists():
        return {"skill": skill, "error": f"missing {evals_json}"}

    evals_data = json.loads(evals_json.read_text())
    prompts = evals_data.get("evals", [])
    if not include_live_only:
        prompts = [p for p in prompts if not p.get("live_only")]
    if not prompts:
        return {"skill": skill, "skipped": "no fixture-free prompts (all are live_only)"}

    skill_name, _description = read_skill_meta(skill_repo_dir)

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    runs_dir = skill_eval_dir / "workspace" / "runs" / ts
    runs_dir.mkdir(parents=True, exist_ok=True)

    per_prompt: list[dict] = []
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
                },
                indent=2,
            )
        )

        for config in ("with_skill", "without_skill"):
            config_dir = eval_dir / config
            config_dir.mkdir(exist_ok=True)
            for k in range(1, runs + 1):
                run_dir = config_dir / f"run-{k}"
                print(
                    f"[task] {skill} eval-{eval_id} {config} run-{k} (subject)",
                    file=sys.stderr,
                )
                subj = run_subject(
                    prompt=p["prompt"],
                    skill_name=skill_name,
                    repo_skill_dir=skill_repo_dir,
                    with_skill=(config == "with_skill"),
                    model=model,
                    timeout=subject_timeout,
                    run_dir=run_dir,
                    extra_env=extra_env,
                )
                if not subj["ok"]:
                    print(
                        f"[task]   subject failed: {subj.get('reason')}",
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
                            },
                            indent=2,
                        )
                    )
                    continue

                print(
                    f"[task] {skill} eval-{eval_id} {config} run-{k} (grader)",
                    file=sys.stderr,
                )
                grading = run_grader(
                    expectations=p["expectations"],
                    transcript_path=Path(subj["transcript_path"]),
                    outputs_dir=Path(subj["outputs_dir"]),
                    run_dir=run_dir,
                    model=model,
                    timeout=grader_timeout,
                )
                if "error" in grading:
                    print(f"[task]   grader failed: {grading['error']}", file=sys.stderr)
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
        per_prompt.append({"eval_id": eval_id, "prompt": p["prompt"][:80]})

    run_benchmark(skill, runs_dir)
    update_latest_symlink(skill, runs_dir)

    benchmark = json.loads((runs_dir / "benchmark.json").read_text())
    rs = benchmark.get("run_summary", {})
    with_pr = rs.get("with_skill", {}).get("pass_rate", {})
    wo_pr = rs.get("without_skill", {}).get("pass_rate", {})
    delta = with_pr.get("mean", 0) - wo_pr.get("mean", 0)

    entry = {
        "kind": "task",
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "runs_per_prompt": runs,
        "with_skill_mean": with_pr.get("mean", 0),
        "with_skill_stddev": with_pr.get("stddev", 0),
        "without_skill_mean": wo_pr.get("mean", 0),
        "without_skill_stddev": wo_pr.get("stddev", 0),
        "delta": round(delta, 4),
        "eval_ids": [p["id"] for p in prompts],
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
    parser.add_argument("--runs", type=int, default=1, help="Runs per (prompt × config). Default 1 for dev; use 3 for stddev.")
    parser.add_argument("--include-live-only", action="store_true",
                        help="Include prompts marked live_only=true")
    parser.add_argument("--model", default=None,
                        help="Model ID. Default comes from the Makefile.")
    parser.add_argument("--subject-timeout", type=int, default=600)
    parser.add_argument("--grader-timeout", type=int, default=600)
    parser.add_argument("--kubeconfig", default=None,
                        help="KUBECONFIG path exported into the subject subprocess")
    parser.add_argument("--aws-session-policy", default=None,
                        help="Path to an IAM session policy JSON. When set, mints an STS "
                             "federation token scoped by the policy and exports its creds "
                             "into the subject subprocess.")
    parser.add_argument("--aws-duration", type=int, default=7200,
                        help="STS federation-token lifetime in seconds (default 2h). "
                             "Long enough for a full task-axis run across 2 prompts × 2 configs.")
    parser.add_argument("--aws-region", default="us-west-2")
    args = parser.parse_args()

    skills = discover_skills()
    if args.skill:
        if args.skill not in skills:
            print(f"unknown skill: {args.skill}", file=sys.stderr)
            return 2
        skills = [args.skill]

    model = args.model or _resolve_makefile_default("MODEL") or "global.anthropic.claude-opus-4-7"

    extra_env: dict[str, str] = {}
    if args.kubeconfig:
        kcp = Path(args.kubeconfig).resolve()
        if not kcp.exists():
            print(f"kubeconfig not found: {kcp}", file=sys.stderr)
            return 2
        extra_env["KUBECONFIG"] = str(kcp)
    if args.aws_session_policy:
        policy = Path(args.aws_session_policy).resolve()
        if not policy.exists():
            print(f"aws session policy not found: {policy}", file=sys.stderr)
            return 2
        creds = mint_federation_token(
            policy, name=f"evals-readonly-{os.getpid()}", duration=args.aws_duration
        )
        extra_env["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
        extra_env["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
        extra_env["AWS_SESSION_TOKEN"] = creds["SessionToken"]
        extra_env["AWS_DEFAULT_REGION"] = args.aws_region
        print(
            f"[task] minted read-only AWS session (exp {creds['Expiration']})",
            file=sys.stderr,
        )

    outcomes = []
    for skill in skills:
        print(f"[task] === {skill} ===", file=sys.stderr)
        result = run_skill(
            skill,
            model=model,
            runs=args.runs,
            include_live_only=args.include_live_only,
            subject_timeout=args.subject_timeout,
            grader_timeout=args.grader_timeout,
            extra_env=extra_env or None,
        )
        outcomes.append(result)
        if "error" in result:
            print(f"[task] {skill}: ERROR {result['error']}", file=sys.stderr)
        elif "skipped" in result:
            print(f"[task] {skill}: skipped ({result['skipped']})", file=sys.stderr)
        else:
            e = result["history_entry"]
            print(
                f"[task] {skill}: with={e['with_skill_mean']:.2f} "
                f"without={e['without_skill_mean']:.2f} "
                f"Δ={e['delta']:+.2f}",
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
