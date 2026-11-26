# `misc/evals/MULTITURN-HARNESS.md`: multi-turn eval harness

Code cites name a sha: `@ 2133c43d` was `origin/main` when this doc was written (2133c43dd693e0337987443270a60efdd3ac4ecd). `@ 33a5bc2f` was `origin/main` after PR 571 merged (33a5bc2f9f3457c6aba43c2283f9fc207834b4c1). `@ e81a5ee4` is PR 578's code commit, rebased after PR 572 merged (e81a5ee497935fed471bbcb1b77e2fb50db7b96e; PR 578 merged as 5b15ec9a).

## 1. Purpose and scope

Issue 98's acceptance criteria ask for a "Multi-turn harness design doc written"; its axis 2 is the "Multi-turn / integration harness". This is that doc. It describes the harness that exists and marks what is planned.

Some skills (eks-build, eks-design) ask clarifying questions before they produce output. In `claude -p` a question ends the run, so a single-shot eval grades an incomplete run. The multi-turn harness answers those questions from canned answers declared in `evals.json` and resumes the session, so the run is reproducible (`misc/evals/scripts/elicitation.py:4-7 @ 2133c43d`).

Scope today: task evals (`run_task_evals.py`) on the `claude`, `kiro` and `codex` harnesses. Kiro and codex resume by their own CLI forms (section 2.7), tested only against stand-in CLIs so far.

## 2. How it works on main @ 2133c43d

All code is in `misc/evals/scripts/elicitation.py`, wired in by `misc/evals/scripts/run_task_evals.py`.

### 2.1 Config shape

A case opts in with an `elicitation` block in its `evals.json`:

```json
"elicitation": {
  "strategy": "canned-multiturn",
  "turns": [
    {"question_match": "region", "answer": "us-west-2"},
    ...
  ],
  "max_turns": 8
}
```

- `CannedTurn` holds `question_match` (a regex matched against the question text) and `answer` (`elicitation.py:28-38 @ 2133c43d`).
- `ElicitationConfig` holds `strategy` (`"single-shot"` or `"canned-multiturn"`), `turns` and `max_turns` (`elicitation.py:41-45 @ 2133c43d`).
- No block gives `strategy="single-shot"`, no turns, `max_turns=1` (`elicitation.py:49-50 @ 2133c43d`). A block with no `strategy` defaults to `"single-shot"`; a block with no `max_turns` defaults to 10 (`elicitation.py:52-54 @ 2133c43d`).
- The one case on main with canned answers is `eks-build` case 3 (`misc/evals/eks-build/evals.json:221 @ 2133c43d`, block at `:298-311`, `max_turns` 8 at `:310`). The README says the same (`misc/evals/README.md:224 @ 2133c43d`).

### 2.2 Question detection

`detect_pending_question(events)` (`elicitation.py:58 @ 2133c43d`) walks the events backwards to the last `assistant` event and stops there (`:65-67`, `:78`). In that event's content it looks, last first, for a `tool_use` named `AskUserQuestion` (`:69-70`). If found, it joins the `question` field of every entry in `input.questions` with spaces and returns it, or None when that is empty (`:71-77`). Any other final assistant message returns None: on main only an `AskUserQuestion` call counts as a question.

### 2.3 Answer matching

`match_answer(question_text, turns)` returns the `answer` of the first canned turn, in list order, whose `question_match` matches anywhere in the question text under `re.search(..., re.IGNORECASE)` (`elicitation.py:82-87 @ 2133c43d`). Turns are not consumed: the same turn can answer more than one question.

### 2.4 Session id

`run_multiturn_subject` makes the session id itself with `uuid.uuid4()` and passes it on the first turn as `--session-id` (`elicitation.py:171`, `:176 @ 2133c43d`). `extract_session_id` (`elicitation.py:90 @ 2133c43d`) reads it from a `result` or `system/init` event, but nothing under `misc/` calls it (at 2133c43d; PR 580's `elicitation.py` calls it for kiro's and codex's first turn; only codex's resume uses the id). The runner discards the returned id (`run_task_evals.py:686 @ 2133c43d`, `raw_events, timed_out, _ = ...`).

### 2.5 Resume loop and turn limit

1. Turn 1 runs `cmd_base + ["-p", initial_prompt, "--session-id", session_id]` (`elicitation.py:176 @ 2133c43d`). `cmd_base` is the claude stream-json command from `_claude_cmd_base` (`run_task_evals.py:780 @ 2133c43d`).
2. While `turns_used < max_turns` (`elicitation.py:187-188 @ 2133c43d`), it detects a question in the last turn's events, matches an answer, and runs `cmd_base + ["-p", answer, "--resume", session_id]` (`elicitation.py:198 @ 2133c43d`).
3. `max_turns` counts every subject call, the first included: `turns_used` starts at 1 (`elicitation.py:187 @ 2133c43d`).
4. Each turn gets the full per-run timeout (`timeout_per_turn=timeout`, `run_task_evals.py:692 @ 2133c43d`). A timeout on any turn returns at once with `timed_out` true (`elicitation.py:183-184`, `:205-206 @ 2133c43d`).
5. Events of every turn are appended to one list (`elicitation.py:181`, `:203 @ 2133c43d`).

### 2.6 No question, no match

If the last turn has no question, or no canned turn matches it, the loop stops (`elicitation.py:190-195 @ 2133c43d`) and the run ends with the events so far, `timed_out` false (`elicitation.py:208 @ 2133c43d`). The run is not marked invalid for this and no note is written: the grader sees a run that stopped at an unanswered question.

### 2.7 Runner wiring

- `run_task_evals.py` imports the module and `ElicitationConfig`, `_append_event`, `run_multiturn_subject` (`run_task_evals.py:102-103 @ 2133c43d`).
- Each case's block is read with `ElicitationConfig.from_dict(p.get("elicitation"))` and passed to `run_subject` (`run_task_evals.py:1524`, `:1534 @ 2133c43d`).
- A run is multi-turn only when `strategy == "canned-multiturn"` and `turns` is non-empty (`run_task_evals.py:641 @ 2133c43d`).
- PR 580, not main @ 2133c43d: kiro and codex run the same loop with their own turn commands (`run_task_evals.py` `harness_turn_cmd`), each resume form read from its CLI's `--help` on 2026-11-26: kiro-cli 3.5.0 adds `--resume` (its help's first sentence: "Resume the most recent conversation from this directory."; each run's sandbox is its own folder, so that conversation should be the run's, unverified until a live run), and codex-cli 0.163.0 runs `codex exec resume <thread_id> <answer>` ("Usage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]"), the id from the first turn's `thread.started`, whose turn drops `--ephemeral`. Each turn's events are normalized before its question is read, and `normalize_turns` keeps the canned answer on the resumed turn's first event. On kiro and codex each resumed turn that printed events is checked on its own by `stream_invalid_reason`: it needs its own start event (kiro `runStarted`, codex `thread.started`), on kiro an ACP update, and its finish event, or the run is invalid, named by turn. A resumed turn that prints no event is not checked (section 3.2). Whether a real `codex exec resume` emits `thread.started` is unverified until a live run; if it does not, every codex multi-turn run reads invalid as `turn 2: no init event`.
- `_PopenRecorder` stands in for `elicitation.subprocess` during the run so every turn's exit code is kept (`run_task_evals.py:831-856 @ 2133c43d`; codes read at `:694`). A non-zero code on any turn makes the run invalid (`run_task_evals.py:752-753 @ 2133c43d`).
- On claude the events pass through `normalize_events` unchanged (`misc/evals/scripts/parse_trajectory.py:544-545 @ 2133c43d`) and are written to `events.jsonl` (`run_task_evals.py:724 @ 2133c43d`); `format_transcript` writes `transcript.md` (`run_task_evals.py:719`, `:212 @ 2133c43d`).
- stderr: on the multi-turn path the runner's `stderr` stays empty (`run_task_evals.py:651 @ 2133c43d`); `elicitation.py` pipes each turn's stderr and never reads it (`elicitation.py:178`, `:200 @ 2133c43d`).

## 3. What PR 570 added @ 33a5bc2f

PR 570 merged into main as 4b34709f.

### 3.1 Plain-text question heuristic

eks-build, eks-design and eks-mcp-server ask in plain text, not with `AskUserQuestion` (`elicitation.py:69-72 @ 33a5bc2f`). With no `AskUserQuestion` in the final assistant message, `detect_pending_question` takes that message's last non-empty text block, reads a closed fenced block as one paragraph, splits it on blank lines, and returns the last paragraph if it holds a `?` outside an inline code span or a URL, else None (`elicitation.py:98-102 @ 33a5bc2f`). `AskUserQuestion` still wins when present (`elicitation.py:89-97 @ 33a5bc2f`).

Stated limits (`elicitation.py:77-83 @ 33a5bc2f`):

- False negative: a question followed by another paragraph, such as an options paragraph or a sign-off, is missed, and so is a question on a fence's closing line.
- False positive: a closing offer that ends in `?` counts as a question, such as "Want me to confirm?" (the "confirm" false catch). It is then sent to `match_answer`, so a canned turn whose regex matches the offer answers it.
- A fence of 4 or more backticks is closed early by an inner ```` ``` ```` line, so a `?` in the rest of that block counts.

### 3.2 `elicitation_answer` record

Each resumed turn's first event gets `"elicitation_answer": "<answer>"`, the canned answer sent (`elicitation.py:232-236 @ 33a5bc2f`; docstring `:194-197`). PR 578, not PR 570, adds its rendering: `format_transcript` shows it in transcript.md, the file the grader reads, as a `**Eval harness reply (canned user answer):**` line before that event (`run_task_evals.py:246-251 @ e81a5ee4`). Stated limit: a resumed turn that emits no event loses the record (`elicitation.py:196-197 @ 33a5bc2f`), and, in PR 580 on all three harnesses, when it exits 0 the run is still scored valid on the earlier turns' events.

PR 570 also sends each turn's stderr to `DEVNULL`, since only stdout is read and an unread pipe can stall the subject until the timeout (`elicitation.py:203-207`, `:229 @ 33a5bc2f`).

## 4. Open and planned (not built)

None of this is built.

- Kiro and codex multi-turn live proof. The resume forms (section 2.7) are tested only against stand-in CLIs; a live run waits on the eval credential.
- The runner's stderr pipes at `run_task_evals.py:701` and `:923 @ 2133c43d` (single-turn subject and grader, read only after the stream is drained). Outside this harness.
- Issue 98's other axis 2 items, quoted: "Workflow-level evals (does `/apex:eks-design` produce good end-to-end output?)", "Ambient triggering across turns" and "Skill interop when multiple loaded". They wait on a scoping decision about whether they get work of their own; nothing is built for them here.
