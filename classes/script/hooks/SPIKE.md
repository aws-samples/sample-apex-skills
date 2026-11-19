# Spike: how the Stop gate finds which skill ran

The plan leaves this open: one plugin Stop hook must find which skill ran and
which schema to check, and the hook input names no skill. This note gives the
facts, the routes tried and the route the gate (stop-gate/stop_gate.py) takes.
It was done by reading the harness hook pages and local session files, and by
feeding fixture events to the gate; no model ran.

## What a Stop hook receives

| Harness | Stop input fields | Names the skill? |
|---|---|---|
| Claude Code | common fields `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`; Stop adds `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons` | no |
| Codex | common fields `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, `permission_mode`; Stop adds `turn_id`, `stop_hook_active`, `last_assistant_message` | no |
| Kiro CLI | `hook_event_name`, `cwd`, `session_id` | no |

Sources: the Claude Code hooks reference (code.claude.com/docs/en/hooks.md, Stop
input), the Codex hooks page (developers.openai.com/codex/hooks, Stop), and the
Kiro hook types page (kiro.dev/docs/hooks/types, Agent Stop, CLI tab).

## Routes

1. **Skill-scoped hooks** (Claude Code only). A skill's frontmatter `hooks`
   are registered when the skill is invoked, so such a hook knows its skill.
   Ruled out for this build: the repo's frontmatter check
   (misc/safe_frontmatter.py) allows only `name`, `description`, `license`,
   `metadata` and `allowed-tools`, Codex and Kiro have no such hooks, and the
   hook stays registered for the rest of the session.
2. **The transcript** (Claude Code and Codex; Kiro sends no path). A Claude
   Code session file records a skill run as an assistant `tool_use` named
   `Skill` with input `{"skill": "<name>", ...}` (checked in local Claude Code
   2.1.327 session files). A Codex session file lists the skills in a
   developer message and shows a run only as the model reading a SKILL.md
   through a shell call. Ruled out: Codex calls the transcript format "not a
   stable interface for hooks", Claude Code says the file may lag the
   conversation at Stop time, Kiro has none, and a transcript names the skill
   but not the output file to check.
3. **`last_assistant_message`** (Claude Code and Codex). It is the agent's own
   text, which the gate must not trust, and Kiro does not send it. Ruled out.
4. **A run record left by the class check tools** (all three harnesses).
   Taken. Every Script skill already runs its output validator before it hands
   the output on (`apex.validate-output`), and every Operator skill with an
   artifact runs its declared checks; those two class tools are the one place
   that knows the skill folder and the file. Each run leaves a small record;
   the gate reads the records for its working folder, and runs the same tool
   again itself on the same files. The record carries paths, never a verdict,
   so the gate never trusts the agent's or the tool's earlier result.

## The run record

One JSON file per tool run, `run-<ns>-<pid>.json`, in the state folder
`<temp>/apex-stop-gate-<uid>` (Python's `tempfile.gettempdir()`, so `TMPDIR`
moves it; created 0700, and the gate reads it only when this user owns it and
no one else can write to it):

```json
{"v": 1, "kind": "outputs", "tool": "/abs/skills/eks-recon/scripts/script_validate_output.py",
 "python": "/abs/python3", "pythonpath": null, "skill_dir": "/abs/skills/eks-recon",
 "files": ["/abs/EKS-Recon-demo.yaml"], "cwd": "/abs/work", "time": 1795000000.0}
```

`kind` is `outputs` (validate_output.py) or `artifact-checks`
(run_artifact_checks.py, one artifact). The gate takes the records whose `cwd`
is the Stop event's `cwd` or a folder under it, drops records older than 24
hours, and runs only the four tool names the class sync gives these tools
(validate_output.py, script_validate_output.py, run_artifact_checks.py,
operator_run_artifact_checks.py), with the interpreter the tool ran under, so
the gate needs no copy of the validator or its packages: the plugin's copy of
stop_gate.py is one file and imports nothing outside the standard library.
The gate sets `APEX_STOP_GATE_RUN=1` for its re-run, and a tool that sees it
writes no record, so the gate's own run does not leave a new one.

A pass deletes its record. A blocked fail keeps it, so the retry is checked
again. A warn, or a fail with the reentry guard spent, deletes it, so the
next turn starts clean.

## Who writes the record

The two class tools, classes/script/scripts/validate_output.py (with
classes/apex-base/scripts/schema_check.py) and
classes/operator/scripts/run_artifact_checks.py: a record each time they are
given files to check, before the check runs, unless `APEX_STOP_GATE_RUN` is
set. Until they write it, the gate finds no record and ends every turn with no
decision.

## Limits found

- A turn in which the skill never ran its check tool leaves no record, so the
  gate has nothing to check: the gate holds the skill to its own checks, it
  does not detect skills.
- Records are per working folder, not per session: two sessions in one folder
  see each other's records. That can cost a retry; the guard keeps it to one.
- Stop fires for the main agent only, so a skill run inside a subagent is
  checked only when the subagent's tool run leaves a record in the main
  agent's folder and the main agent then stops.
- The gate gives every check run 25 s in total, under Kiro's 30 s hook limit.
  One validator run on an eks-recon output took about 2.5 s here, and the
  gate with that one record about 2.5 s in all (most of it the jsonschema
  import). An Operator artifact check that runs terraform or
  checkov can take longer; past 25 s it is no verdict, which blocks once.
