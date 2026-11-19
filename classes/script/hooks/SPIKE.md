# Spike: how the Stop gate finds which skill ran

The plan leaves this open: one plugin Stop hook must find which skill ran and
which schema to check, and the hook input names no skill. This note gives the
facts, the routes tried and the route the gate (stop-gate/stop_gate.py) takes.
It was done by reading the harness hook pages and local session files, and by
feeding fixture events to the gate; no model ran.

## What a Stop hook receives

| Harness | Stop input fields | Names the skill? |
|---|---|---|
| Claude Code | common fields include `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`; Stop adds `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons` | no |
| Codex | common fields include `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, `permission_mode`; Stop adds `turn_id`, `stop_hook_active`, `last_assistant_message` | no |
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
   hook stays registered for the rest of the session unless `once: true`.
2. **The transcript** (Claude Code and Codex; Kiro sends no path). A Claude
   Code session file records a skill run as an assistant `tool_use` named
   `Skill` with input `{"skill": "<name>", ...}` (checked in local Claude Code
   2.1.327 session files). A Codex session file lists the skills in a
   developer message and shows a run only as the model reading a SKILL.md
   through a shell call. Ruled out: Codex says "the transcript format isn't a
   stable interface for hooks and may change over time", Claude Code says the
   file may lag the conversation at Stop time, Kiro has none, and a transcript
   names the skill but not the output file to check.
3. **`last_assistant_message`** (Claude Code and Codex). It is the agent's own
   text, which the gate must not trust, and Kiro does not send it. Ruled out.
4. **A run record left by the class check tools** (all three harnesses).
   Taken. A Script skill is to run its output validator before it hands the
   output on (`apex.validate-output`), and an Operator skill with an artifact
   its declared checks; those two class tools are the one place that knows the
   skill folder and the file. Once they write it, each run leaves a small
   record; the gate reads the records for its project and runs the same tool
   again itself on the same files. The record carries paths, never a verdict,
   so the gate never trusts the agent's or the tool's earlier result.

## The run record

One JSON file per tool run, `run-<ns>-<pid>.json`, in the state folder
`<root>/.apex-stop-gate`, root the nearest folder at or above the working
folder that holds `.git`, else the working folder (the writer walks from its
own working folder, the gate from the Stop event's `cwd`). The gate makes the
folder (0700, with a `.gitignore` of `*`) at each Stop it runs with its switch
on, the writer writes only into a folder that exists, and the gate reads it
only when this user owns it and no one else can write to it:

```json
{"tool": "/abs/skills/eks-recon/scripts/script_validate_output.py",
 "skill_dir": "/abs/skills/eks-recon", "files": ["/abs/EKS-Recon-demo.yaml"],
 "cwd": "/abs/work", "time": 1795000000.0}
```

The gate deletes records older than 24 hours, keeps the newest per (tool,
skill_dir, files), drops any whose skill folder has no SKILL.md or whose tool
is gone, and runs a tool only when its real path is the skill's own synced copy
(`<skill_dir>/scripts/script_validate_output.py` or
`operator_run_artifact_checks.py`) and the skill folder's real path is a folder
directly in the skills root. The gate takes that root from its own file's
location, never from the record or the event: `<plugin>/skills` for the
plugin's copy, the repo's `skills/` for the classes/ copy. The classes/ copy
also runs this repo's `classes/script/scripts/validate_output.py` and
`classes/operator/scripts/run_artifact_checks.py`; the plugin's copy never runs
those two, and drops a record that names one, with one stderr line, as it drops
a stale record. It runs a tool with its own interpreter (for the repo's two it
sets `PYTHONPATH` to `classes/apex-base/scripts`; the skill copies import their
flat copy), so the plugin's copy of stop_gate.py is one file and imports
nothing outside the standard library, and a record cannot choose the
interpreter or the import path. The record, like the output, is within the
agent's reach and can name any skill in the skills root and any files, and the
classes/ copy's skills root is in the checkout, which the agent can write, so
the gate stops an honest agent skipping a failed check, not a hostile one. The gate sets `APEX_STOP_GATE_RUN=1` for its re-run,
and a tool that sees it writes no record, so the gate's own run does not leave
a new one.

A pass deletes its record. A blocked fail keeps it, so the retry is checked
again. A warn, or a fail with the reentry guard spent, deletes it, so the
next turn starts clean.

## Who writes the record

The two class tools, classes/script/scripts/validate_output.py (with
classes/apex-base/scripts/schema_check.py) and
classes/operator/scripts/run_artifact_checks.py, are to write a record each
time a check starts on files, unless `APEX_STOP_GATE_RUN` is set, in a
separate change to those tools. Until they write it, the gate finds no record and ends every
turn with no decision.

## Limits found

- A turn in which the skill never ran its check tool leaves no record, so the
  gate has nothing to check: the gate holds the skill to its own checks, it
  does not detect skills.
- The tools write no record when they exit 2 before checking (a bad skill
  folder, an undeclared schema, a missing artifact), so such a run is not
  checked at Stop.
- Records are per project, not per session: two sessions in one project see
  each other's records. That can cost a retry; the guard keeps it to one.
- Stop fires for the main agent only, so a skill run inside a subagent is
  checked only when its tool run leaves a record in the main agent's project
  and the main agent then stops.
- The state is under the working folder because Claude Code's sandbox gives
  sandboxed commands their own `$TMPDIR` while hooks run unsandboxed, so a
  record in the temp folder would land where the gate does not read. Under the
  sandbox a command can write only in the working folder and below, so a
  session started in a subfolder of a repo cannot write the record at the repo
  root, and that run is not checked.
- The writer cannot read the gate's switch (Claude Code exports
  `CLAUDE_PLUGIN_OPTION_<KEY>` to hook processes, not to the agent's commands),
  so the state folder stands in for it: the first turn after the switch goes on
  leaves no record until a Stop has made the folder, and a folder left after
  the switch goes off keeps taking records until removed.
- Every record left is run again at the next Stop, and all runs share one 25 s
  budget; the newest-per-key rule keeps a fix-and-revalidate loop to one run,
  but many distinct files can still run past it, and a run past it is no
  verdict, which blocks once. 25 s is under the lower of Kiro's two documented
  defaults (60 s for a hook file's `timeout`, 30 s on the CLI actions page).
  One validator run on an eks-recon output took about 2.5 s on the build host,
  and the gate with that one record about 2.5 s in all (most of it the
  jsonschema import). An Operator artifact check that runs terraform or
  checkov can take longer (a one-resource project took about 18.6 s warm).
- A record it cannot read, and a state folder others can write, are skipped
  without a message; skipped records stay until removed; a Kiro guard left
  behind spends the next block in that folder.
- Kiro's Agent Stop page documents no surface for a hook's stderr, so a Kiro
  user may see no warning and no bad-switch line. Not run on Kiro, as of
  2026-11-19: no model runs on the build host until DECISION R-20261116-B-39
  is answered.
- The hook-test runner's run-record fixture (`claude-code-g-block-record`)
  gives its record through `APEX_STOP_GATE_RECORDS`. The runner runs every
  fixture from the repo root, so each fixture with the switch on makes the
  state folder `.apex-stop-gate` in the checkout and checks any record left
  there. The fixture's record names an output file that does not exist, so the
  check gives no verdict whether or not jsonschema is installed.
- The plugin's copy, plugins/apex/hooks/script/stop-gate/stop_gate.py, carries
  the class sync's header line, but the sync checks it only once a class.yaml
  hooks entry names the gate; until then a test checks that it is the class
  copy plus that line.
