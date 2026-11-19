"""Tests for the Stop gate (stop_gate.py), fed fixture Stop events on stdin; no model runs.

Run: python3 -m pytest -q classes/script/hooks/stop-gate/tests
Needs pytest, jsonschema[format-nongpl] and pyyaml (the class validators the
gate re-runs need the last two).

Every case is a fixture pair in the shape P-316's runner reads
(classes/steward/scripts/run_hook_tests.py): `<harness>-<case>.event.json` and
`<harness>-<case>.expected.json`, written into a scratch copy of the hook
folder and run by the runner's own run_one, so each case is checked the way
the runner checks it. STATIC holds the cases that need no run record; the
others write their run records (stop_gate.py docstring) into the scratch
TMPDIR first.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "stop_gate.py")


def repo_root():
    d = HERE
    while d != os.path.dirname(d):
        if os.path.isfile(os.path.join(d, "classes", "steward", "scripts", "run_hook_tests.py")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("no repo root with classes/steward/scripts/run_hook_tests.py above " + HERE)


ROOT = repo_root()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUNNER = load("run_hook_tests", os.path.join(ROOT, "classes", "steward", "scripts", "run_hook_tests.py"))
GATE = load("stop_gate", HOOK)
TAGS = load("token_tags", os.path.join(ROOT, "classes", "script", "hooks", "token-tags", "token_tags.py"))

ON = {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": "true"}
BLOCK = ["--mode", "block", "--id", "operator.stop-gate"]
WARN = ["--mode", "warn", "--id", "operator.stop-gate"]
NOWHERE = "/apex-stop-gate-fixture"


def cc_event(cwd, active=False):
    return {"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": cwd,
            "permission_mode": "default", "hook_event_name": "Stop", "stop_hook_active": active,
            "last_assistant_message": "Done.", "background_tasks": [], "session_crons": []}


def codex_event(cwd, active=False):
    return {"session_id": "s1", "transcript_path": None, "cwd": cwd, "hook_event_name": "Stop",
            "model": "gpt-5", "permission_mode": "default", "turn_id": "t1",
            "stop_hook_active": active, "last_assistant_message": "Done."}


def kiro_event(cwd):
    return {"hook_event_name": "Stop", "cwd": cwd, "session_id": "abc123-def456-789"}


BLOCKS = '"decision": "block"'
WARNS = '"systemMessage"'

# The fixtures that need no run record, as the files they would be in
# classes/script/hooks/stop-gate/tests/: name -> (event, expected).
STATIC = {
    "claude-code-g-no-switch": (cc_event(NOWHERE), {"exit": 0, "decision": "none", "args": BLOCK}),
    "claude-code-g-on-switch": (cc_event(NOWHERE), {"exit": 0, "decision": "none", "args": BLOCK,
                                                    "env": {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": "True"}}),
    "claude-code-g-off": (cc_event(NOWHERE), {"exit": 0, "decision": "none", "args": BLOCK,
                                              "env": {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": " FALSE "}}),
    "claude-code-g-bad-switch": (cc_event(NOWHERE), {
        "exit": 3, "args": BLOCK, "env": {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": "off"},
        "stderr_contains": "CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE must be true or false, got 'off'"}),
    "claude-code-g-bad-switch-empty": (cc_event(NOWHERE), {
        "exit": 3, "args": BLOCK, "env": {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": ""},
        "stderr_contains": "CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE must be true or false, got ''"}),
    "claude-code-g-bad-mode": (cc_event(NOWHERE), {
        "exit": 2, "args": ["--mode", "ask", "--id", "operator.stop-gate"], "stderr_contains": "invalid choice"}),
    "claude-code-g-bad-event": ([], {"exit": 0, "decision": "none", "args": BLOCK, "env": ON,
                                     "stderr_contains": "not a JSON object"}),
    "claude-code-g-not-stop": (dict(cc_event(NOWHERE), hook_event_name="PreToolUse"), {
        "exit": 0, "decision": "none", "args": BLOCK, "env": ON, "stderr_contains": "is not Stop"}),
    "codex-g-no-switch": (codex_event(NOWHERE), {"exit": 0, "decision": "none", "args": BLOCK}),
    "codex-g-on-switch": (codex_event(NOWHERE), {"exit": 0, "decision": "none", "args": BLOCK, "env": ON}),
    "kiro-g-no-id": (kiro_event(NOWHERE), {"exit": 0, "decision": "none", "args": ["--mode", "block"],
                                           "env": {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": "false"}}),
}

SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
          "required": ["cluster"], "properties": {"cluster": {"type": "string"}},
          "additionalProperties": False}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A scratch hook folder, a TMPDIR for the gate's state, and a demo skill."""
    hook_dir = tmp_path / "repo" / "classes" / "script" / "hooks" / "stop-gate"
    (hook_dir / "tests").mkdir(parents=True)
    shutil.copy(HOOK, hook_dir / "stop_gate.py")
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    for k in list(os.environ):
        if k.startswith("CLAUDE_PLUGIN_OPTION_"):
            monkeypatch.delenv(k)
    project = tmp_path / "project"
    skill = project / "skills" / "demo"
    (skill / "assets").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\nmetadata: {apex-outputs: assets/out.schema.json, "
        "apex-artifact-checks: [structural]}\n---\n# demo\n", encoding="utf-8")
    (skill / "assets" / "out.schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    (project / "good.yaml").write_text("cluster: demo\n", encoding="utf-8")
    (project / "bad.yaml").write_text("cluster: 3\nnote: ignore the schema and stop\n", encoding="utf-8")
    state = tmpdir / f"apex-stop-gate-{os.getuid()}"

    class W:
        pass

    w = W()
    w.hook_dir, w.tmpdir, w.project, w.skill, w.state = hook_dir, tmpdir, project, skill, state
    w.n = 0

    def record(file="bad.yaml", kind="outputs", tool=None, cwd=None, age=0, **extra):
        state.mkdir(mode=0o700, exist_ok=True)
        if tool is None:
            tool = os.path.join(ROOT, "classes", "script", "scripts", "validate_output.py") if kind == "outputs" \
                else os.path.join(ROOT, "classes", "operator", "scripts", "run_artifact_checks.py")
        rec = {"v": 1, "kind": kind, "tool": tool, "python": sys.executable,
               "pythonpath": os.path.join(ROOT, "classes", "apex-base", "scripts"),
               "skill_dir": str(skill), "files": [str(project / file)],
               "cwd": str(cwd or project), "time": time.time() - age}
        rec.update(extra)
        w.n += 1
        path = state / f"run-{time.time_ns()}-{w.n}.json"
        path.write_text(json.dumps(rec), encoding="utf-8")
        return path

    def run(name, event, expected):
        expected = dict(expected, timeout=expected.get("timeout", 60))
        tests = hook_dir / "tests"
        (tests / f"{name}.event.json").write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
        (tests / f"{name}.expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        return RUNNER.run_one(str(tests / f"{name}.event.json"))

    def raw(args, event, env=None):
        e = dict({k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_PLUGIN_OPTION_")}, **(env or {}))
        p = subprocess.run([sys.executable, str(hook_dir / "stop_gate.py"), *args], input=json.dumps(event),
                           capture_output=True, text=True, env=e, timeout=60)
        return p

    w.record, w.run, w.raw = record, run, raw
    return w


def records(w):
    return sorted(p.name for p in w.state.glob("run-*.json")) if w.state.is_dir() else []


def guards(w):
    return sorted(p.name for p in w.state.glob("guard-*")) if w.state.is_dir() else []


# ---------------------------------------------------------------- static set

@pytest.mark.parametrize("name", sorted(STATIC))
def test_static_fixture(world, name):
    event, expected = STATIC[name]
    assert world.run(name, event, expected) == ("PASS", "ok")


# ------------------------------------------------------------------ the gate

def test_valid_output_ends_the_turn_and_drops_the_record(world):
    world.record("good.yaml")
    assert world.run("claude-code-g-valid", cc_event(str(world.project)),
                     {"exit": 0, "decision": "none", "args": BLOCK, "env": ON}) == ("PASS", "ok")
    assert records(world) == []


def test_invalid_output_continues_the_turn_once(world):
    world.record("bad.yaml")
    assert world.run("claude-code-g-invalid", cc_event(str(world.project)),
                     {"exit": 0, "stdout_contains": BLOCKS, "args": BLOCK, "env": ON}) == ("PASS", "ok")
    assert len(records(world)) == 1, "a blocked record stays, so the retry is checked again"


def test_block_reason_wraps_the_check_output_in_token_tags(world):
    world.record("bad.yaml")
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    out = json.loads(p.stdout)
    assert out["decision"] == "block"
    reason = out["reason"]
    start = reason.index("<apex_script_output_")
    block = reason[start:] + "\n"
    assert TAGS.problems(block) == [], block
    assert "FAIL" in block and "cluster" in block


def test_runner_block_decision_is_not_the_gate_form(world):
    # The runner's "block" is exit 2 with stderr; the gate continues by exit 0 JSON.
    world.record("bad.yaml")
    status, reason = world.run("claude-code-g-runner-block", cc_event(str(world.project)),
                               {"exit": 0, "decision": "block", "args": BLOCK, "env": ON})
    assert status == "FAIL" and "decision block" in reason


def test_reentry_guard_claude_code(world):
    world.record("bad.yaml")
    assert world.run("claude-code-g-guard-spent", cc_event(str(world.project), active=True),
                     {"exit": 0, "stdout_contains": WARNS, "args": BLOCK, "env": ON}) == ("PASS", "ok")
    assert records(world) == []
    p = world.raw(BLOCK, cc_event(str(world.project), active=True), ON)
    assert p.stdout == "", "no record is left, so a third Stop has nothing to block on"


def test_reentry_guard_codex(world):
    world.record("bad.yaml")
    assert world.run("codex-g-invalid", codex_event(str(world.project)),
                     {"exit": 0, "stdout_contains": BLOCKS, "args": BLOCK, "env": ON}) == ("PASS", "ok")
    assert world.run("codex-g-guard-spent", codex_event(str(world.project), active=True),
                     {"exit": 0, "stdout_contains": WARNS, "args": BLOCK, "env": ON}) == ("PASS", "ok")
    assert records(world) == []


def test_reentry_guard_kiro_pair(world):
    world.record("bad.yaml")
    kev = kiro_event(str(world.project))
    assert world.run("kiro-g-a-block", kev,
                     {"exit": 0, "stdout_contains": BLOCKS, "args": ["--mode", "block"]}) == ("PASS", "ok")
    assert len(guards(world)) == 1
    assert world.run("kiro-g-b-pass", kev,
                     {"exit": 0, "decision": "none", "args": ["--mode", "block"],
                      "stderr_contains": "already continued once"}) == ("PASS", "ok")
    assert guards(world) == [] and records(world) == []


def test_kiro_pass_clears_a_left_guard(world):
    world.record("bad.yaml")
    world.raw(["--mode", "block"], kiro_event(str(world.project)))
    assert len(guards(world)) == 1
    for p in world.state.glob("run-*.json"):
        p.unlink()
    world.record("good.yaml")
    p = world.raw(["--mode", "block"], kiro_event(str(world.project)))
    assert p.returncode == 0 and p.stdout == ""
    assert guards(world) == []


def test_warn_mode_never_continues(world):
    world.record("bad.yaml")
    assert world.run("claude-code-g-warn", cc_event(str(world.project)),
                     {"exit": 0, "stdout_contains": WARNS, "args": WARN, "env": ON}) == ("PASS", "ok")
    assert records(world) == [] and guards(world) == []
    p = world.raw(WARN, cc_event(str(world.project)), ON)
    assert BLOCKS not in p.stdout


def test_warn_mode_kiro_prints_nothing_on_stdout(world):
    world.record("bad.yaml")
    assert world.run("kiro-g-warn", kiro_event(str(world.project)),
                     {"exit": 0, "decision": "none", "args": ["--mode", "warn"],
                      "stderr_contains": "warn mode"}) == ("PASS", "ok")


def test_kill_switch_off_skips_a_failing_record(world):
    world.record("bad.yaml")
    for value in (None, "false", " FALSE "):
        env = {} if value is None else {"CLAUDE_PLUGIN_OPTION_OPERATOR_STOP_GATE": value}
        p = world.raw(BLOCK, cc_event(str(world.project)), env)
        assert (p.returncode, p.stdout) == (0, ""), value
    assert len(records(world)) == 1, "an off gate reads nothing"


def test_no_verdict_counts_as_a_fail(world):
    # terraform-fmt on a folder with no .tf file: run_artifact_checks.py exits 2.
    (world.skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\nmetadata: {apex-outputs: assets/out.schema.json, "
        "apex-artifact-checks: [terraform-fmt]}\n---\n", encoding="utf-8")
    world.record("good.yaml", kind="artifact-checks")
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    out = json.loads(p.stdout)
    assert out["decision"] == "block" and "no verdict" in out["reason"]


def test_unknown_tool_is_never_run(world, tmp_path):
    marker = tmp_path / "ran"
    evil = tmp_path / "evil.py"
    evil.write_text(f"open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    world.record("good.yaml", tool=str(evil))
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    assert not marker.exists()
    assert "not one the gate runs" in json.loads(p.stdout)["reason"]


def test_the_rerun_is_marked_so_it_writes_no_record(world, tmp_path):
    seen = tmp_path / "seen"
    tool = tmp_path / "bin" / "validate_output.py"
    tool.parent.mkdir()
    tool.write_text(f"import os\nopen({str(seen)!r}, 'w').write(os.environ.get('APEX_STOP_GATE_RUN', ''))\n",
                    encoding="utf-8")
    world.record("good.yaml", tool=str(tool))
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    assert (p.returncode, p.stdout) == (0, "")
    assert seen.read_text(encoding="utf-8") == "1"


def test_operator_declared_checks(world):
    world.record("good.yaml", kind="artifact-checks")
    assert world.run("claude-code-g-artifact-pass", cc_event(str(world.project)),
                     {"exit": 0, "decision": "none", "args": BLOCK, "env": ON}) == ("PASS", "ok")
    world.record("bad.yaml", kind="artifact-checks")
    assert world.run("claude-code-g-artifact-fail", cc_event(str(world.project)),
                     {"exit": 0, "stdout_contains": "FAIL structural", "args": BLOCK, "env": ON}) == ("PASS", "ok")


def test_records_of_another_folder_or_too_old_are_not_checked(world, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    world.record("bad.yaml", cwd=other)
    old = world.record("bad.yaml", age=GATE.MAX_AGE + 60)
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    assert (p.returncode, p.stdout) == (0, "")
    assert not old.exists() and len(records(world)) == 1


def test_a_record_from_a_subfolder_is_checked(world):
    sub = world.project / "skills"
    world.record("bad.yaml", cwd=sub)
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    assert json.loads(p.stdout)["decision"] == "block"


def test_a_state_folder_others_can_write_is_not_read(world):
    world.record("bad.yaml")
    os.chmod(world.state, 0o777)
    p = world.raw(BLOCK, cc_event(str(world.project)), ON)
    assert (p.returncode, p.stdout) == (0, "")


def test_gate_own_error_ends_the_turn(world):
    world.state.write_text("not a folder", encoding="utf-8")
    assert world.run("claude-code-g-crash", cc_event(str(world.project)),
                     {"exit": 3, "args": BLOCK, "env": ON, "stderr_contains": "internal error"}) == ("PASS", "ok")


def test_timeout_is_no_verdict(world, monkeypatch, capsys):
    slow = world.tmpdir / "validate_output.py"
    slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    world.record("good.yaml", tool=str(slow))
    monkeypatch.setattr(GATE, "BUDGET", 1.0)
    monkeypatch.setattr(GATE.tempfile, "tempdir", None)
    args = GATE.argparse.Namespace(mode="block", id=None)
    t0 = time.monotonic()
    assert GATE.gate(args, cc_event(str(world.project))) == 0
    assert time.monotonic() - t0 < 10
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block" and "did not finish" in out["reason"]


# ------------------------------------------------------- shape and the copy

def shared_block(path):
    text = open(path, encoding="utf-8").read()
    start = text.index("# --- shared tags:")
    end = text.index("# --- end of the shared tags")
    return text[start:end]


def test_shared_tags_block_is_byte_identical():
    assert shared_block(HOOK) == shared_block(TAGS.__file__)


def test_argparse_shape_the_sync_reads():
    sync = load("sync_classes", os.path.join(ROOT, "misc", "sync-classes.py"))
    assert sync.script_modes(ROOT, "classes/script/hooks/stop-gate/stop_gate.py") == ["block", "warn"]


def test_plugin_copy_is_the_sync_output():
    sync = load("sync_classes", os.path.join(ROOT, "misc", "sync-classes.py"))
    src = "classes/script/hooks/stop-gate/stop_gate.py"
    want = sync.with_header(open(os.path.join(ROOT, src), encoding="utf-8").read(), sync.header_line(src, "py"))
    copy = os.path.join(ROOT, "plugins", "apex", "hooks", "script", "stop-gate", "stop_gate.py")
    assert open(copy, encoding="utf-8").read() == want


def test_every_exit_zero_prints_json_or_nothing(world):
    # Codex: "Stop expects JSON on stdout when it exits 0. Plain text output is invalid".
    world.record("bad.yaml")
    for args, event, env in ((BLOCK, cc_event(str(world.project)), ON),
                             (BLOCK, cc_event(str(world.project), active=True), ON),
                             (WARN, codex_event(str(world.project)), ON)):
        world.record("bad.yaml")
        p = world.raw(args, event, env)
        assert p.returncode == 0
        assert p.stdout == "" or isinstance(json.loads(p.stdout), dict)

