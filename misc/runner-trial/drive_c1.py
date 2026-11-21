#!/usr/bin/env python3
"""Drive candidate C1 of the runner trial: the homegrown runner in
misc/evals/scripts/ on the claude harness, one case and one arm at a time.

It calls the runner's own functions (run_task_evals.run_subject,
run_task_evals.run_grader, run_task_evals._resolve_makefile_default,
artifact_validation.validate_run, run_triggering.run_single_query,
run_triggering.read_skill_meta, run_triggering.mint_eval_role_credentials,
run_triggering.set_eval_credentials, knowledge_assertions.evaluate,
skilleval_config.load_config, elicitation.ElicitationConfig.from_dict) for the
seven cases in cases.md. Each case is scored on its single pass condition
(cases.md); the source suites' other expectations are not.

Default: a dry run that prints the planned runs and makes no model call.
--paid starts the runs. It refuses to start without --out (empty or new)
and --spend-limit-usd (finite, above 0), or when the eval-role session the
runner mints (run_triggering.mint_eval_role_credentials) is refused, and
stops before the next run once the subjects' recorded cost reaches the limit. The stop counts only the subjects' recorded cost: grader
calls, T6 query runs and a run that times out or crashes before its first
result event add nothing; on Claude Code older than 2.1.277, or after an
earlier turn that exited abnormally, T5's earlier turns add nothing; and the
run that crosses the limit completes. The limit is per invocation.

Paid runs use a separate eval account through the eval role
apex-eval-bedrock-invoke (misc/evals/README.md, Eval-role setup); see
cases.md, Credentials and permissions, for the eval role's status. The
subject runs as your OS user with bypassPermissions, so it can read, write
and run anything your user can, the runner's environment included (and on
an EC2 host, the instance role through the metadata endpoint unless that is
blocked); run it as another OS user or in a container for a hard fence
(misc/evals/README.md, Eval-role setup).

Output (--out): runs.jsonl, one line per run (case, arm, run, status, pass,
tokens, duration_ms, wall_seconds, total_cost_usd, reason), summary.json
(pass count per case and arm, for score-sheet.md S1 and S2, plus a T6
"both_queries" cell counting runs k where both query arms passed at run k,
and runner_head, the git HEAD of the checkout whose runner ran), and each
run's runner files under <case>/<arm>/run-<k>/. runner_head is HEAD only;
uncommitted changes are not recorded. S2 reads `pass` over the runs
whose status is 'ran' or 'error' (an 'error' run counts as a failed run, as
the shipped runner does); 'cannot run' and 'not run' runs are left out, and
S2 is n/a when none is left. Any error during the runs ends the invocation:
runs.jsonl holds the runs that finished and summary.json is not written. A
subject that times out or exits nonzero (a canned multi-turn subject only
when it times out), a grader that returns an error or the wrong number of
expectations, or an invalid trigger query is recorded as an 'error' run.

events_to_spans converts one run's events.jsonl into the span input of the
AgentCore Evaluations Evaluate API, for C3; it is a pure function and no
paid path calls it.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "misc" / "evals" / "scripts"
PIN = "7efa0776"        # case text, fixtures and skills are read from this commit (cases.md)
OLD = "0678d921"        # tag v1.3.0, the old arm on T1 to T4 (cases.md)
RUNS = 3
TRIGGER_TIMEOUT = 90    # run_triggering.py --timeout default
GRADER_TIMEOUT = 600    # run_task_evals.py --grader-timeout default

T4_PASS = ("The headline rating field reads NOT READY (score 59 or lower, the "
           "hard-blocker cap), not a READY found by substring elsewhere in the "
           "report, and subnet-aaa (3 available IPs) is named as the blocker.")

# grade: (kind, value). Kinds: suite (run_grader on the suite expectations
# that contain each string), text (run_grader on this one expectation),
# artifact (validate_run on the one assertion named by key and value),
# multiturn (resumed at least once and the suite's first knowledge
# assertion holds), trigger (run_single_query on query index, should_trigger).
CASES = [
    {"id": "T1", "skill": "eks-security", "eval_id": 4,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("suite", ["Gives the verdict exposed for both"])},
    {"id": "T2", "skill": "eks-recon", "eval_id": 3,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("artifact", ("structural", "pattern", r"Changed[ \t]*\|[^|\n]*blue[^|\n]*desired_size"))},
    {"id": "T3", "skill": "eks-build", "eval_id": 1,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("artifact", ("validators", "path", "skills/eks-build/scripts/validate_project.sh"))},
    {"id": "T4", "skill": "eks-upgrade-check", "eval_id": 4,
     "arms": ("with_skill", "without_skill", "old_skill"),
     "grade": ("text", T4_PASS)},
    {"id": "T5", "skill": "eks-build", "eval_id": 3,
     "arms": ("with_skill", "without_skill"),
     "grade": ("multiturn", 0)},
    {"id": "T6", "skill": "eks-mcp-server", "eval_id": None,
     "arms": ("with_skill_q3", "with_skill_q18"),
     "grade": ("trigger", {"with_skill_q3": (3, True), "with_skill_q18": (18, False)})},
    {"id": "T7", "skill": "eks-recon", "eval_id": 1, "live": True,
     "arms": ("with_skill", "without_skill"),
     "grade": ("suite", ["cluster version and platform version",
                         "primary compute strategy",
                         "EKS-managed add-ons with their installed versions",
                         "IaC tool managing the cluster"])},
]
CASE_IDS = [c["id"] for c in CASES]


def load_runner() -> SimpleNamespace:
    """Import the runner's functions. No model call happens on import."""
    sys.path.insert(0, str(SCRIPTS))
    import artifact_validation
    import knowledge_assertions
    import run_task_evals
    import run_triggering
    import skilleval_config
    return SimpleNamespace(
        run_subject=run_task_evals.run_subject,
        run_grader=run_task_evals.run_grader,
        validate_run=artifact_validation.validate_run,
        evaluate_knowledge=knowledge_assertions.evaluate,
        run_single_query=run_triggering.run_single_query,
        read_skill_meta=run_triggering.read_skill_meta,
        start_eval_session=lambda timeout, source: run_triggering.set_eval_credentials(
            run_triggering.mint_eval_role_credentials(timeout=timeout, source=source)),
        EvalCredentialError=run_triggering.EvalCredentialError,
        subject_timeout=lambda skill: skilleval_config.load_config(skill).timeout,
        default_model=lambda: (run_task_evals._resolve_makefile_default("MODEL")
                               or "global.anthropic.claude-opus-4-6-v1"),  # run_task_evals.py:1032 @528dde41
    )


def case_source(case: dict, root: Path) -> Path:
    name = "triggering.json" if case["grade"][0] == "trigger" else "evals.json"
    return root / "misc" / "evals" / case["skill"] / name


class GitError(RuntimeError):
    """git archive failed, so the pinned or old tree was not read."""


def load_case(case: dict, root: Path) -> dict:
    data = json.loads(case_source(case, root).read_text())
    if case["grade"][0] == "trigger":
        return {"queries": data}
    matches = [e for e in data["evals"] if e["id"] == case["eval_id"]]
    if len(matches) != 1:
        raise ValueError(f"{case['id']}: {len(matches)} evals with id {case['eval_id']}")
    return matches[0]


def suite_expectations(case: dict, spec: dict) -> list[str]:
    value = case["grade"][1]
    picked = [e for e in spec["expectations"] if any(v in e for v in value)]
    if len(picked) != len(value):
        raise ValueError(f"{case['id']}: {len(picked)} suite expectations match, want {len(value)}")
    return picked


def artifact_pick(case: dict, spec: dict) -> dict:
    section, key, needle = case["grade"][1]
    cfg = spec["artifact_assertions"]
    picked = [a for a in cfg.get(section, []) if needle in str(a.get(key, ""))]
    if len(picked) != 1:
        raise ValueError(f"{case['id']}: {len(picked)} {section} entries match {needle!r}")
    return {"root_glob": cfg.get("root_glob"), section: picked}


def check_specs(cases: list[dict], root: Path) -> dict:
    """Load each case and resolve its pass-condition selector before any run."""
    specs = {}
    for case in cases:
        spec = specs[case["id"]] = load_case(case, root)
        kind, value = case["grade"]
        if kind == "suite":
            suite_expectations(case, spec)
        elif kind == "artifact":
            artifact_pick(case, spec)
        elif kind == "multiturn" and not (spec.get("elicitation") and len(spec.get("knowledge_assertions", [])) > value):
            raise ValueError(f"{case['id']}: no elicitation block or knowledge assertion {value}")
        elif kind == "trigger":
            for arm, (idx, should) in value.items():
                if spec["queries"][idx].get("should_trigger") is not should:
                    raise ValueError(f"{case['id']} {arm}: query {idx} should_trigger is not {should}")
    return specs


def plan_runs(cases: list[dict]) -> list[dict]:
    """Every (case, arm, run) and the skill revision it reads (PIN or OLD)."""
    return [{"case": case["id"], "arm": arm, "run": k, "rev": "OLD" if arm == "old_skill" else "PIN"}
            for case in cases for arm in case["arms"] for k in range(1, RUNS + 1)]


def check_commits() -> str | None:
    """None when OLD is a commit in this clone, else the refusal text (git, no model call)."""
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{OLD}^{{commit}}"], capture_output=True)
    if r.returncode != 0:
        return f"--paid refused: OLD commit {OLD} is not in this clone (fetch it first)"
    return None


def runner_head() -> str:
    """git rev-parse HEAD of the checkout this driver and its runner run from.
    runner_head is HEAD only; uncommitted changes are not recorded."""
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    if r.returncode != 0:
        raise GitError(f"git rev-parse HEAD failed: {r.stderr.strip()}")
    return r.stdout.strip()


@contextlib.contextmanager
def archived(rev: str, *paths: str):
    """The repo paths as they stand at rev, extracted to a temp dir that is yielded as
    the tree's root (git, no model call). Raises GitError when git archive fails."""
    tmp = Path(tempfile.mkdtemp(prefix="drive-c1-"))
    try:
        r = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", rev, *paths], capture_output=True)
        if r.returncode != 0:
            raise GitError(f"git archive {rev} failed: {r.stderr.decode(errors='replace').strip()}")
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
            # filter= (PEP 706) is missing from older interpreters such as Python 3.9.16, so feature-detect it
            tar.extractall(tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def last_result(events_path: Path) -> tuple[dict, int]:
    """The last result event and the count of result events in events.jsonl."""
    results = []
    if events_path.exists():
        for line in events_path.read_text().splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                evt = json.loads(line)
                if evt.get("type") == "result":
                    results.append(evt)
    return (results[-1] if results else {}), len(results)


OI_SCOPE = "openinference.instrumentation.claude_agent_sdk"


def _span_id(session_id: str, *parts: object, n: int = 16) -> str:
    return hashlib.sha256("/".join(map(str, (session_id, *parts))).encode()).hexdigest()[:n]


def events_to_spans(events: list, prompts: list[str], session_id: str) -> list[dict]:
    """Convert one run's events.jsonl (Claude Code stream-json events, as
    misc/evals/scripts/parse_trajectory.py reads them) into the spans for the
    AgentCore Evaluations Evaluate API: evaluationInput={"sessionSpans": spans}.
    Pure function: no AWS call, no file read.

    The fields the page's extraction section names are converted (input.value
    and output.value on AGENT; tool.name, tool.id, input.value and output.value
    on TOOL), plus openinference.span.kind and session.id; the examples'
    llm.*, mime-type and tool.parameters attributes are not.
    Builtin.GoalSuccessRate (session) and Builtin.Correctness (trace) read the
    user prompt and agent response of each turn; Builtin.TrajectoryAnyOrderMatch
    reads the tool names. Each turn, the events up to and including a result
    event, is one trace: an AGENT span (input.value = prompts[i] when given,
    output.value = the result event's `result`) and one TOOL span per tool_use
    (tool.name, tool.id, input.value = the input as JSON, output.value = the
    matching tool_result content, paired by tool_use_id). Tool calls after the
    last result event are a turn that did not finish: its AGENT span has no
    output.value and status ERROR. A line that is not a JSON object is skipped.
    IDs are derived from session_id, so the output is deterministic. No start
    or end times are emitted (the examples omit them). Tool spans share the
    turn's trace with a parentSpanId (the unified example gives the tool span
    its own traceId). Whether Evaluate needs either is untested. A session
    with no result event and no tool call gives no spans, and a text-only turn
    after the last result event is dropped.

    Shape and attributes from the Claude Agent SDK page, unified telemetry
    (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/supported-frameworks-claude-agent-sdk.html,
    read 2026-11-19): scope `openinference.instrumentation.claude_agent_sdk`,
    "Invoke agent | `openinference.span.kind` = `AGENT`", "Execute tool |
    `openinference.span.kind` = `TOOL`", "User prompt and agent response: from
    `input.value` and `output.value` on the invoke agent span", "Tool call: the
    tool name from `tool.name`, the tool call ID from `tool.id`, the arguments
    from `input.value`, and the result from `output.value`". Whether Evaluate
    scores spans never ingested into CloudWatch is untested (score-sheet.md, C3).
    """
    turns, cur = [], {"tools": [], "result": None}
    for evt in events:
        if not isinstance(evt, dict):
            continue
        msg = evt.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
        if evt.get("type") == "assistant":
            cur["tools"] += [{"name": b.get("name", ""), "id": b.get("id"), "input": b.get("input"), "result": None,
                              "error": False} for b in blocks if b.get("type") == "tool_use"]
        elif evt.get("type") == "user":
            for b in blocks:
                if b.get("type") == "tool_result":
                    for t in cur["tools"]:
                        if t["id"] is not None and t["id"] == b.get("tool_use_id"):
                            c = b.get("content")
                            t["result"], t["error"] = (c if isinstance(c, str) else json.dumps(c)), b.get("is_error") is True
        elif evt.get("type") == "result":
            cur["result"] = evt
            turns.append(cur)
            cur = {"tools": [], "result": None}
    if cur["tools"]:
        turns.append(cur)
    spans = []
    for i, turn in enumerate(turns):
        trace_id, agent_id = _span_id(session_id, "trace", i, n=32), _span_id(session_id, "agent", i)
        attrs = {"openinference.span.kind": "AGENT", "session.id": session_id}
        if i < len(prompts):
            attrs["input.value"] = prompts[i]
        res = turn["result"]
        if res is not None and isinstance(res.get("result"), str):
            attrs["output.value"] = res["result"]
        ok = res is not None and not res.get("is_error")
        spans.append({"traceId": trace_id, "spanId": agent_id, "name": "ClaudeCode.turn", "kind": "INTERNAL",
                      "scope": {"name": OI_SCOPE}, "attributes": attrs, "status": {"code": "OK" if ok else "ERROR"}})
        for j, t in enumerate(turn["tools"]):
            tattrs = {"openinference.span.kind": "TOOL", "tool.name": t["name"], "session.id": session_id,
                      "input.value": json.dumps(t["input"])}
            if t["id"] is not None:
                tattrs["tool.id"] = t["id"]
            if t["result"] is not None:
                tattrs["output.value"] = t["result"]
            spans.append({"traceId": trace_id, "spanId": _span_id(session_id, "tool", i, j), "parentSpanId": agent_id,
                          "name": t["name"], "kind": "INTERNAL", "scope": {"name": OI_SCOPE}, "attributes": tattrs,
                          "status": {"code": "ERROR" if t["error"] else "OK"}})
    return spans


def grade_task(runner, case: dict, spec: dict, subj: dict, run_dir: Path, model: str,
               root: Path) -> tuple[bool | None, str]:
    kind, value = case["grade"]
    outputs, transcript = Path(subj["outputs_dir"]), Path(subj["transcript_path"])
    if kind in ("suite", "text"):
        expectations = [value] if kind == "text" else suite_expectations(case, spec)
        grading = runner.run_grader(expectations=expectations, transcript_path=transcript,
                                    outputs_dir=outputs, run_dir=run_dir, model=model, timeout=GRADER_TIMEOUT)
        if "error" in grading:
            return None, f"grader: {grading['error']}"
        if len(grading["expectations"]) != len(expectations):
            return None, f"grader returned {len(grading['expectations'])} expectations, want {len(expectations)}"
        ok = all(e.get("passed") for e in grading["expectations"])
        return ok, f"grader {sum(bool(e.get('passed')) for e in grading['expectations'])}/{len(expectations)}"
    if kind == "artifact":
        res = runner.validate_run(outputs_dir=outputs, assertions_config=artifact_pick(case, spec), repo_root=root)
        passed = res.structural_passed + res.validators_passed
        failed = res.structural_failed + res.validators_failed
        return (passed == 1 and failed == 0), f"artifact {passed} passed, {failed} failed"
    if kind == "multiturn":
        final, n_results = last_result(run_dir / "events.jsonl")
        ka = runner.evaluate_knowledge(final.get("result") or "", [spec["knowledge_assertions"][value]])
        return (n_results >= 2 and ka.failed == 0 and ka.passed == 1), f"result events {n_results}, pattern {ka.passed}/1"
    raise ValueError(f"{case['id']}: unknown grade kind {kind}")


# Spare seconds the minted cluster session must have left past a run's timeout.
LIVE_SESSION_MARGIN = 120
MINTED_KEYS = ("aws_access_key_id", "aws_secret_access_key", "aws_session_token", "expiration")


class LiveSessionError(RuntimeError):
    """The live run's cluster session is missing, malformed or too short."""


def read_minted_session(path: str, profile: str, timeout: int) -> dict:
    """Read the cluster session the operator minted before the run
    (--cluster-credentials): `profile`'s section of that file, holding only
    aws_access_key_id, aws_secret_access_key, aws_session_token and
    expiration (ISO 8601). The driver never signs in or assumes a role
    itself, so the sign-in that minted the session stays outside the runner.
    A section that names a credential_process, role_arn or source_profile is
    refused, and so is a session that would not outlast a `timeout`-second
    run by LIVE_SESSION_MARGIN. Read anew for each run, so a session minted
    again between runs is picked up. Returns the STS-shaped Credentials dict."""
    import configparser
    import datetime
    parser = configparser.ConfigParser(interpolation=None)
    try:
        if not parser.read(path):
            raise LiveSessionError(f"cannot read {path}")
    except (configparser.Error, UnicodeDecodeError) as e:
        raise LiveSessionError(f"cannot parse {path} ({e.__class__.__name__})") from None
    if not parser.has_section(profile):
        raise LiveSessionError(f"{path} has no [{profile}] section")
    sec = parser[profile]
    signin = [k for k in ("credential_process", "role_arn", "source_profile") if k in sec]
    if signin:
        raise LiveSessionError(f"[{profile}] in {path} names {', '.join(signin)}: give the minted session only")
    missing = [k for k in MINTED_KEYS if not sec.get(k, "").strip()]
    if missing:
        raise LiveSessionError(f"[{profile}] in {path} lacks {', '.join(missing)}")
    try:
        expires = datetime.datetime.fromisoformat(sec["expiration"].strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        raise LiveSessionError(f"[{profile}] in {path} has an expiration that is not ISO 8601") from None
    left = expires - time.time()
    if left < timeout + LIVE_SESSION_MARGIN:
        raise LiveSessionError(f"the minted session has {max(left, 0):.0f}s left, under this run's {timeout}s "
                               f"timeout plus {LIVE_SESSION_MARGIN}s: mint it again")
    return {"AccessKeyId": sec["aws_access_key_id"].strip(), "SecretAccessKey": sec["aws_secret_access_key"].strip(),
            "SessionToken": sec["aws_session_token"].strip()}


@contextlib.contextmanager
def live_env(kubeconfig: str, credentials: str | None, timeout: int):
    """Yield the extra env a live subject gets. A kubeconfig whose current
    user runs `aws` with AWS_PROFILE in its exec env needs a session the
    subject's empty HOME lacks: the driver reads that profile's minted
    session from `credentials` (--cluster-credentials; with none the run
    cannot run, with no fallback), and writes, into a private temp dir removed
    when the run ends, a kubeconfig whose exec carries only that session (no
    profile, no config file, no host path) and `bin/aws`, a shim that runs
    the real aws on the same session. PATH puts the shim first, so an `aws`
    the subject runs by name uses that session, while the subject's AWS_*
    env stays the eval-role session for its model calls. The role is the one
    the session was minted for and is not checked here: mint the read-only
    role. Any other kubeconfig (token, certificate, or one that does not
    parse) is passed as is, with no shim."""
    import yaml
    try:
        cfg = yaml.safe_load(Path(kubeconfig).read_text())
        ctx = next(c["context"] for c in cfg["contexts"] if c["name"] == cfg["current-context"])
        user = next(u for u in cfg["users"] if u["name"] == ctx["user"])
        cluster = next(c for c in cfg["clusters"] if c["name"] == ctx["cluster"])
        ex = user["user"]["exec"]
        exec_env = {e["name"]: e["value"] for e in ex.get("env") or []}
    except (yaml.YAMLError, OSError, KeyError, TypeError, StopIteration):
        yield {"KUBECONFIG": kubeconfig}
        return
    if ex.get("command") != "aws" or "AWS_PROFILE" not in exec_env:
        yield {"KUBECONFIG": kubeconfig}
        return
    if not credentials:
        raise LiveSessionError("no --cluster-credentials for the kubeconfig's aws profile")
    creds = read_minted_session(credentials, exec_env["AWS_PROFILE"], timeout)
    real_aws = shutil.which("aws")
    session = (("AWS_ACCESS_KEY_ID", creds["AccessKeyId"]), ("AWS_SECRET_ACCESS_KEY", creds["SecretAccessKey"]),
               ("AWS_SESSION_TOKEN", creds["SessionToken"]), ("AWS_CONFIG_FILE", os.devnull),
               ("AWS_SHARED_CREDENTIALS_FILE", os.devnull), ("AWS_EC2_METADATA_DISABLED", "true"))
    new_exec = {k: v for k, v in ex.items() if k != "env"}
    new_exec["env"] = [{"name": k, "value": v} for k, v in session]
    out = {"apiVersion": "v1", "kind": "Config", "current-context": cfg["current-context"],
           "clusters": [cluster], "contexts": [{"name": cfg["current-context"], "context": ctx}],
           "users": [{"name": user["name"], "user": {"exec": new_exec}}]}
    tmp = tempfile.mkdtemp(prefix="drive-c1-live-")   # mode 700
    try:
        path = Path(tmp) / "kubeconfig"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(out, f)
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir(mode=0o700)
        shim = " ".join(f"{k}={shlex.quote(v)}" for k, v in session)
        fd = os.open(bin_dir / "aws", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
        with os.fdopen(fd, "w") as f:
            f.write(f"#!/bin/sh\nexec env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE {shim} {shlex.quote(real_aws)} \"$@\"\n")
        yield {"KUBECONFIG": str(path), "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_one(runner, case: dict, spec: dict, item: dict, out_dir: Path, model: str, kubeconfig: str | None,
            root: Path, credentials: str | None) -> dict:
    rec = {"case": case["id"], "arm": item["arm"], "run": item["run"], "status": None, "pass": None,
           "tokens": None, "duration_ms": None, "wall_seconds": None, "total_cost_usd": None, "reason": None}
    kind, value = case["grade"]
    run_dir = out_dir / case["id"] / item["arm"] / f"run-{item['run']}"
    if case.get("live") and not kubeconfig:
        rec.update(status="cannot run", reason="no --kubeconfig for a live case")
        return rec
    t0 = time.time()
    if kind == "trigger":
        idx, should = value[item["arm"]]
        skill_dir = root / "skills" / case["skill"]
        name, _ = runner.read_skill_meta(skill_dir)
        res = runner.run_single_query(spec["queries"][idx]["query"], name, skill_dir, model, TRIGGER_TIMEOUT)
        rec["wall_seconds"] = round(time.time() - t0, 2)
        if res.get("invalid"):
            rec.update(status="error", reason=f"invalid: {res.get('invalid_reason')}")
        else:
            rec.update(status="ran", **{"pass": bool(res.get("triggered")) is should},
                       reason=f"triggered {bool(res.get('triggered'))}, want {should}")
        return rec
    sys.path.insert(0, str(SCRIPTS))
    from elicitation import ElicitationConfig
    timeout = runner.subject_timeout(case["skill"])
    try:
        # Only live_env raises LiveSessionError, before its yield.
        with (live_env(kubeconfig, credentials, timeout) if case.get("live") else contextlib.nullcontext()) as live, \
                (archived(OLD, f"skills/{case['skill']}") if item["arm"] == "old_skill"
                 else contextlib.nullcontext(root)) as tree:
            skill_dir = tree / "skills" / case["skill"]
            name, _ = runner.read_skill_meta(skill_dir)
            subj = runner.run_subject(
                prompt=spec["prompt"], skill_name=name, repo_skill_dir=skill_dir,
                with_skill=item["arm"] != "without_skill", model=model, timeout=timeout,
                run_dir=run_dir, extra_env=live,
                elicitation=ElicitationConfig.from_dict(spec.get("elicitation")),
                skill_eval_dir=root / "misc" / "evals" / case["skill"],
                eval_id=case["eval_id"], fixture_files=spec.get("files"))
    except LiveSessionError as e:
        rec.update(status="cannot run", reason=f"cluster session: {e}")
        return rec
    rec["wall_seconds"] = round(time.time() - t0, 2)
    timing_path = run_dir / "timing.json"
    if timing_path.exists():
        timing = json.loads(timing_path.read_text())
        rec["duration_ms"] = timing.get("duration_ms")
        rec["tokens"] = {k: v for k, v in timing.items() if k.endswith("_tokens") or k == "token_source"}
    rec["total_cost_usd"] = last_result(run_dir / "events.jsonl")[0].get("total_cost_usd")
    if not subj.get("ok"):
        rec.update(status="error", reason=f"subject: {subj.get('reason')}")
        return rec
    ok, why = grade_task(runner, case, spec, subj, run_dir, model, root)
    rec.update(status="error" if ok is None else "ran", reason=why, **{"pass": ok})
    return rec


def execute(runner, cases: list[dict], out_dir: Path, *, model: str, spend_limit: float,
            kubeconfig: str | None, root: Path, head: str, credentials: str | None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {c["id"]: c for c in cases}
    specs = check_specs(cases, root)
    spent, records = 0.0, []
    with (out_dir / "runs.jsonl").open("w") as log:
        for item in plan_runs(cases):
            case = by_id[item["case"]]
            if spent >= spend_limit:
                rec = {"case": case["id"], "arm": item["arm"], "run": item["run"], "status": "not run",
                       "pass": None, "tokens": None, "duration_ms": None, "wall_seconds": None,
                       "total_cost_usd": None, "reason": f"spend limit ${spend_limit} reached (${spent:.2f})"}
            else:
                rec = run_one(runner, case, specs[case["id"]], item, out_dir, model, kubeconfig, root, credentials)
                spent += rec["total_cost_usd"] or 0.0
            records.append(rec)
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(f"[c1] {rec['case']} {rec['arm']} run-{rec['run']}: {rec['status']} pass={rec['pass']} "
                  f"subject spend ${spent:.2f} of ${spend_limit} {rec.get('reason') or ''}", file=sys.stderr)
    summary = {"model": model, "pin": PIN, "old": OLD, "runner_head": head,
               "spend_limit_usd": spend_limit, "subject_cost_usd": round(spent, 4), "cases": {}}
    for rec in records:
        cell = summary["cases"].setdefault(rec["case"], {}).setdefault(
            rec["arm"], {"pass": 0, "ran": 0, "runs": 0, "statuses": []})
        cell["runs"] += rec["status"] in ("ran", "error")
        cell["ran"] += rec["status"] == "ran"
        cell["pass"] += bool(rec["pass"])
        cell["statuses"].append(rec["status"])
    t6 = {(r["arm"], r["run"]): r for r in records if r["case"] == "T6"}
    if t6:
        # cases.md T6: a run k passes only when both query arms passed at run k
        arms = next(c["arms"] for c in cases if c["id"] == "T6")
        ks = range(1, RUNS + 1)
        both = [[t6.get((a, k), {}) for a in arms] for k in ks]
        summary["cases"]["T6"]["both_queries"] = {
            "pass": sum(all(r.get("pass") for r in rs) for rs in both),
            "ran": sum(all(r.get("status") == "ran" for r in rs) for rs in both),
            "runs": sum(all(r.get("status") in ("ran", "error") for r in rs) for rs in both)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None, runner: SimpleNamespace | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Drive runner-trial candidate C1 (misc/runner-trial/cases.md). Dry run by default: "
                    "prints the planned runs and makes no model call. --paid needs the eval-role session the "
                    "runner mints (misc/evals/README.md, Eval-role setup); the subject runs as your OS user "
                    "with bypassPermissions, so it can read, write and run anything your user can, the "
                    "runner's environment included (and on an EC2 host, the instance role through the "
                    "metadata endpoint unless that is blocked); run it as another OS user or in a "
                    "container for a hard fence (misc/evals/README.md, Eval-role setup).")
    p.add_argument("--out", type=Path, help="output dir, empty or new (required with --paid)")
    p.add_argument("--case", action="append", help="case id, repeatable (default: T1 to T7)")
    p.add_argument("--paid", action="store_true", help="start the runs (model calls, billed)")
    p.add_argument("--spend-limit-usd", type=float, help="the maintainers' spend limit for C1, per invocation "
                                                         "(required with --paid)")
    p.add_argument("--kubeconfig", help="read-only kubeconfig for T7 (without it T7 reads 'cannot run')")
    p.add_argument("--cluster-credentials", help="file outside ~/.aws holding a session you minted before the run for "
                                                 "the kubeconfig's aws profile: a [<profile>] section with "
                                                 "aws_access_key_id, aws_secret_access_key, aws_session_token and "
                                                 "expiration (the only keys used); the driver reads it before each T7 run and "
                                                 "never signs in itself, though the subject runs as your user and can "
                                                 "still reach cluster-aws-config, ada and ~/.aws by path (without it, a "
                                                 "kubeconfig whose exec runs aws with AWS_PROFILE reads 'cannot run')")
    args = p.parse_args(argv)

    unknown = [c for c in (args.case or []) if c not in CASE_IDS]
    if unknown:
        print(f"unknown case id: {', '.join(unknown)} (known: {', '.join(CASE_IDS)})", file=sys.stderr)
        return 2
    cases = [c for c in CASES if not args.case or c["id"] in args.case]
    # The case files, fixtures and skills are read from PIN, never the working tree.
    paths = sorted({p for c in cases for p in (f"misc/evals/{c['skill']}", f"skills/{c['skill']}")})
    try:
        with archived(PIN, *paths) as root:
            return drive(args, cases, root, runner)
    except GitError as e:
        print(f"git read failed: {e}", file=sys.stderr)
        return 2


def drive(args: argparse.Namespace, cases: list[dict], root: Path, runner: SimpleNamespace | None) -> int:
    try:
        check_specs(cases, root)
    except (ValueError, KeyError, IndexError) as e:
        print(f"case set does not resolve: {e}", file=sys.stderr)
        return 2

    if not args.paid:
        plan = plan_runs(cases)
        for item in plan:
            print(f"{item['case']} {item['arm']} run-{item['run']} {item['rev']} {PIN if item['rev'] == 'PIN' else OLD}")
        print(f"dry run: {len(plan)} runs planned, no model call made")
        return 0

    missing = [f for f, v in (("--out", args.out), ("--spend-limit-usd", args.spend_limit_usd)) if v is None]
    limit = args.spend_limit_usd
    if missing or (limit is not None and not (math.isfinite(limit) and limit > 0)):
        print(f"--paid refused: needs {', '.join(missing) or 'a finite --spend-limit-usd above 0'}", file=sys.stderr)
        return 2
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        print(f"--paid refused: --out {args.out} is not an empty or new directory", file=sys.stderr)
        return 2
    kubeconfig = None
    if args.kubeconfig:
        kcp = Path(args.kubeconfig).resolve()   # as run_task_evals.py main does
        if not kcp.exists():
            print(f"kubeconfig not found: {kcp}", file=sys.stderr)
            return 2
        kubeconfig = str(kcp)
    credentials = None
    if args.cluster_credentials:
        ccp = Path(args.cluster_credentials).resolve()
        if not ccp.is_file():
            print(f"cluster credentials is not a file: {ccp}", file=sys.stderr)
            return 2
        credentials = str(ccp)
    refused = check_commits()
    if refused:
        print(refused, file=sys.stderr)
        return 2
    head = runner_head()
    runner = runner or load_runner()
    # The session must outlast the longest subprocess, as run_task_evals.py main checks.
    timeouts = [(GRADER_TIMEOUT, "the grader timeout"), (TRIGGER_TIMEOUT, "the triggering timeout")] + [
        (runner.subject_timeout(c["skill"]), f"{c['skill']}/.skilleval.yaml") for c in cases if c["grade"][0] != "trigger"]
    try:
        runner.start_eval_session(*max(timeouts, key=lambda t: t[0]))
        summary = execute(runner, cases, args.out, model=runner.default_model(),
                          spend_limit=limit, kubeconfig=kubeconfig, root=root, head=head, credentials=credentials)
    except runner.EvalCredentialError as e:
        print(f"eval-role session refused or failed to refresh, stopping: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
