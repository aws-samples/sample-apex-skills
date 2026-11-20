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
| Kiro CLI V3 | `hook_event_name` (`Stop`), `cwd`, `session_id` | no |

Sources: the Claude Code hooks reference (code.claude.com/docs/en/hooks.md, Stop
input), the Codex hooks page (developers.openai.com/codex/hooks, Stop), and the
Kiro hook types page (kiro.dev/docs/hooks/types, Agent Stop, CLI tab). Kiro
CLI 2.x names the trigger `stop`, which the gate does not take: it reads only
V3's `Stop`.

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
skill_dir, files), drops any whose skill folder has no SKILL.md or whose tool,
named like one of the four check tools, is gone, and runs a tool only when its
real path is the skill's own synced copy
(`<skill_dir>/scripts/script_validate_output.py` or
`operator_run_artifact_checks.py`) and the skill folder's real path is a folder
directly in the skills root. A gone tool with any other name, or a record with
no tool, is not dropped: it is no verdict and blocks once. The gate never
takes the skills root from the record or the event: it is the repo's `skills/`
for the classes/ copy (from the gate's own location), and for an installed
copy (the Claude Code plugin cache, Kiro's `.kiro/apex-hooks`) the real path of
`~/.apex-skills/skills`, the clone the installer links Claude Code's and
Kiro's `.claude/skills` and `.kiro/skills` entries to
(misc/installer/bin/cli.mjs, `INSTALL_DIR` and `symlinkSkills`). So a record
may name a skill by its link or by its real path, and a skill folder the
agent makes in the project (a real folder in a project `.claude/skills` or
`.kiro/skills` included) is never run. With no `~/.apex-skills` clone (a
marketplace-only plugin install, and Codex, which the installer does not set
up) every record is no verdict and blocks once. With no sandbox (Claude
Code's default), or with the agent working in the home folder, the root is not
a boundary: the agent can make or relink `~/.apex-skills` and add a check the
gate runs; the root keeps out a skill planted in the project. A
`--project --kiro-hooks` install copies the gate itself into the project,
where the agent can edit it. With an empty or relative HOME (which
the installer refuses) an installed copy runs no check. Neither copy runs
this repo's `classes/script/scripts/validate_output.py` or
`classes/operator/scripts/run_artifact_checks.py`: an installed copy drops a
record that names one, with one stderr line, as it drops a stale record, and
the classes/ copy gives it no verdict. The gate runs a tool with its own
interpreter and `-B` (the skill copies import their flat copy of
`schema_check`), so stop_gate.py is one file that imports nothing outside the
standard library, a record cannot choose the interpreter or the import path,
and the re-run writes no `__pycache__` into the skill folder. Both copies run,
unsandboxed and with the hook's full environment, the checks a record names on
the files and folder the record names, and the record is agent-written (a
cloned repo can ship one). Turning the switch on lets a sandboxed agent choose
what runs outside its sandbox. The gate sets `APEX_STOP_GATE_RUN=1` for its
re-run, and a tool that sees it writes no record, so the gate's own run does
not leave a new one.

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
  each other's records. That can cost a retry; the guard keeps it to one. A
  warn, or a Stop with the guard spent, deletes every record under the root,
  another session's included, so that session's failed check is no longer
  checked at its own Stop.
- The writer walks from the check's working folder and the gate from the Stop
  event's `cwd`. A check run whose folder resolves to another root (a nested
  repo, a submodule, another worktree, a folder outside the project) leaves a
  record this Stop never reads.
- Stop fires for the main agent only, so a skill run inside a subagent is
  checked only when its tool run leaves a record in the main agent's project
  and the main agent then stops.
- The state is under the project root (the nearest folder holding .git)
  because Claude Code's sandbox gives
  sandboxed commands their own `$TMPDIR` while hooks run unsandboxed, so a
  record in the temp folder would land where the gate does not read. The
  sandbox by default writes the working folder and below, the per-user temp
  folder and added directories, so a session started in a subfolder of a repo
  cannot write the record at the repo root, and that run is not checked.
- The gate's switch variable does not reach the agent's commands, where the
  writer runs (Claude Code exports
  `CLAUDE_PLUGIN_OPTION_<KEY>` to hook processes, not to the agent's commands),
  so the state folder stands in for it: the first turn after the switch goes on
  leaves no record until a Stop has made the folder, and a folder left after
  the switch goes off keeps taking records until removed.
- Every record left is run again at the next Stop, and all runs share one
  budget; the newest-per-key rule keeps a fix-and-revalidate loop to one run,
  but many distinct files can still run past it, and a run past it is no
  verdict, which blocks once. The budget is set by the `--id`: with one,
  570 s (Claude Code and Codex, under their 600 s command-hook default:
  code.claude.com/docs/en/hooks.md, `timeout`; developers.openai.com/codex/hooks,
  `timeout`; both read 2026-11-19); with none (Kiro), the `--kiro-timeout`
  value less 5 s, or 25 s when it is not passed (under the 30 s default of a
  Kiro agent-config hook: kiro.dev/docs/hooks/actions, CLI tab, "Default
  timeout is 30 seconds (30,000ms). Configure with the `timeout_ms` field";
  the IDE tab says 60 s; read 2026-11-19). The output shape is set by the
  event (no `stop_hook_active`: Kiro's), so a hand run with no `--id` and a
  Claude Code event gets Claude Code's output and Kiro's budget. Kiro
  documents `hooks[].timeout` for the `.kiro/hooks` file the installer copies
  (kiro.dev/docs/hooks/, "Hook file schema": "Timeout in seconds for command
  actions (default: 60). 0 disables the timeout.", read 2026-11-20), and the
  hook file schema in a Kiro CLI 3.4.0 binary's v3 engine takes it as a whole
  number of seconds, 0 or more (read from its program text, not run; that
  engine drops a whole hook file that fails its schema). The class sync
  writes a `class.yaml` hooks entry's `kiro_timeout` (whole seconds, at least
  30) as the Kiro hook's `timeout` and as its command's `--kiro-timeout`, so
  Kiro's limit and the gate's budget come from one value. No Kiro Stop entry
  exists yet: once one lands with a `kiro_timeout` longer than a check runs,
  that check gets a verdict on Kiro too, so the gate can back
  operator.artifact-checks for eks-build there; with none set, a check slower
  than 25 s gets no verdict on Kiro. One validator run on an eks-recon output took about
  2.5 s on the build host, and the gate with that one record about 2.5 s in
  all (most of it the jsonschema import). An Operator artifact check that
  runs terraform or checkov can take longer (a one-resource project took
  about 18.6 s warm). Each check runs in its own process group (a new
  session). A timeout of the gate's budget kills the whole group, so no
  terraform or provider it started keeps running, and so does a SIGTERM or
  SIGINT to the gate or an error while a check runs; the gate holds both
  signals off while it starts the check, so one that lands then waits until
  the gate can kill it. Any other signal (SIGKILL, SIGHUP, SIGQUIT) leaves
  the check and what it started running. A process that leaves the group
  itself is not killed, a check that exits leaves what it started running,
  and a tool that exits but leaves a child holding its output open waits out
  the budget, which is no verdict.
- Skipped without a message, with exit 0: a record that is not valid JSON, is
  not a JSON object, cannot be read or is not a regular file; a record whose
  `time` is missing, not a number, not finite or later than now; and a state
  folder that is a link, not a folder, not this user's or writable by others.
  Skipped records stay until removed; a Kiro guard left behind spends the next
  block in that folder.
- A `stop_hook_active` that is not the boolean true (such as the string
  `"true"`) does not spend the guard, so the gate blocks again at that Stop.
- An installed copy drops a record by its tool's file name only: a tool named
  `validate_output.py` or `run_artifact_checks.py` is dropped wherever it is.
- The newest-per-key rule reads `files` in the order the record lists them, so
  the same files in another order are two keys.
- Records given in `APEX_STOP_GATE_RECORDS` get the current time at every read
  and are never deleted, so they are checked at every Stop while the variable
  is set. A value that is not valid JSON is the gate's own error: exit 3 at
  each Stop.
- Under a read-only project root the gate cannot make the state folder, so each
  Stop with the switch on is the gate's own error (exit 3).
- Kiro's Agent Stop page documents no surface for a hook's stderr, so a Kiro
  user may see no warning and no bad-switch line. Not yet run on Kiro, as of
  2026-11-19; that run uses Kiro's own login and needs no eval account.
- The hook-test runner's three run-record fixtures
  (`claude-code-g-block-record`, `claude-code-g-warn-record` and
  `claude-code-g-guard-spent-record`) give their record through
  `APEX_STOP_GATE_RECORDS`. The runner runs every fixture from the repo root
  with no `cwd`, so these three are the fixtures that make the state folder
  `.apex-stop-gate` in the checkout, and they check any record left there and
  delete the developer's passing, stale and old records in it (the warn and
  spent ones delete every record there). The other switch-on fixtures name a
  `cwd` that does not exist and stop before the state folder. The fixtures'
  record names this repo's `classes/` validator, which the classes/ copy does
  not run, so it is no verdict whether or not jsonschema is installed.
- This change ships no plugin copy of the gate. The class sync writes
  plugins/apex/hooks/script/stop-gate/stop_gate.py once a class.yaml `hooks:`
  entry names the gate, in the change that lands that entry.
