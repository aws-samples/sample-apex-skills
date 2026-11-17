#!/usr/bin/env python3
"""Hook-test skeleton (piece 9): feed fixture events to each class hook script.

Usage: run_hook_tests.py [--root <repo root>]

Finds every fixture by the glob classes/*/hooks/*/tests/*.event.json. A
fixture `<harness>-<case>.event.json` (harness claude-code, codex or kiro)
has `<harness>-<case>.expected.json` beside it:

    {"exit": 2, "decision": "block", "stderr_contains": "Secret",
     "stdout_contains": "", "args": ["--mode", "block"], "timeout": 10}

`exit` is required; the rest are optional. The hook script is
classes/<c>/hooks/<hook>/<hook, with - as _>.py (secret-deny/secret_deny.py),
run with `args` and the event on stdin, from the repo root. Decisions:
`block` is exit 2 with non-empty stderr, `none` exit 0 with empty stdout,
`ask` exit 0 with a JSON stdout whose hookSpecificOutput.permissionDecision
is "ask" (Claude Code). A mismatch is FAIL; a run past the timeout is FAIL
with reason `timeout`.

Each line is `HOOK-TEST <PASS|FAIL|ERROR> <hook>/<fixture> <reason>`, then
`<n> hook tests, <f> failed, <e> errors`. Exit 0 when every test passed,
1 when any failed or errored, 2 on a usage error.
"""

import glob
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HARNESSES = ("claude-code", "codex", "kiro")
DEFAULT_TIMEOUT = 10


def decided(decision, rc, stdout, stderr):
    if decision == "block":
        return rc == 2 and stderr.strip() != ""
    if decision == "none":
        return rc == 0 and stdout.strip() == ""
    if decision == "ask":
        try:
            out = json.loads(stdout)
        except ValueError:
            return False
        spec = out.get("hookSpecificOutput") if isinstance(out, dict) else None
        return rc == 0 and isinstance(spec, dict) and spec.get("permissionDecision") == "ask"
    raise ValueError(f"unknown decision '{decision}'")


def run_one(event_path):
    """Return (status, reason) for one fixture."""
    tests_dir = os.path.dirname(event_path)
    hook_dir = os.path.dirname(tests_dir)
    case = os.path.basename(event_path)[: -len(".event.json")]
    if not case.startswith(tuple(h + "-" for h in HARNESSES)):
        return "ERROR", f"fixture name must start with one of {', '.join(HARNESSES)}"
    expected_path = os.path.join(tests_dir, case + ".expected.json")
    script = os.path.join(hook_dir, os.path.basename(hook_dir).replace("-", "_") + ".py")
    try:
        with open(expected_path, encoding="utf-8") as f:
            expected = json.load(f)
        with open(event_path, "rb") as f:
            event = f.read()
        json.loads(event)
    except (OSError, ValueError) as e:
        return "ERROR", f"cannot read fixture: {e}"
    if not isinstance(expected, dict) or not isinstance(expected.get("exit"), int):
        return "ERROR", "expected file needs an integer 'exit'"
    if not os.path.isfile(script):
        return "ERROR", f"no hook script {os.path.relpath(script)}"
    args = expected.get("args", [])
    try:
        r = subprocess.run([sys.executable, script, *args], input=event, capture_output=True,
                           timeout=expected.get("timeout", DEFAULT_TIMEOUT))
    except subprocess.TimeoutExpired:
        return "FAIL", "timeout"
    stdout = r.stdout.decode("utf-8", "replace")
    stderr = r.stderr.decode("utf-8", "replace")
    if r.returncode != expected["exit"]:
        return "FAIL", f"expected exit {expected['exit']}, got {r.returncode}"
    if "decision" in expected:
        try:
            ok = decided(expected["decision"], r.returncode, stdout, stderr)
        except ValueError as e:
            return "ERROR", str(e)
        if not ok:
            return "FAIL", f"expected decision {expected['decision']}"
    for key, stream in (("stdout_contains", stdout), ("stderr_contains", stderr)):
        want = expected.get(key)
        if want and want not in stream:
            return "FAIL", f"{key.split('_')[0]} lacks {want!r}"
    return "PASS", "ok"


def main(argv):
    root = REPO_ROOT
    if len(argv) == 2 and argv[0] == "--root":
        root = argv[1]
    elif argv:
        print(f"usage: {os.path.basename(__file__)} [--root <repo root>]", file=sys.stderr)
        return 2
    os.chdir(root)
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0}
    for event_path in sorted(glob.glob("classes/*/hooks/*/tests/*.event.json")):
        status, reason = run_one(event_path)
        counts[status] += 1
        hook = os.path.basename(os.path.dirname(os.path.dirname(event_path)))
        fixture = os.path.basename(event_path)[: -len(".event.json")]
        print(f"HOOK-TEST {status} {hook}/{fixture} {reason}")
    total = sum(counts.values())
    print(f"{total} hook tests, {counts['FAIL']} failed, {counts['ERROR']} errors")
    return 1 if counts["FAIL"] or counts["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
