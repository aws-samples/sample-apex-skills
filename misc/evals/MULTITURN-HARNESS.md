# `misc/evals/MULTITURN-HARNESS.md`: multi-turn eval harness

Code cites name a sha: `@ 2133c43d` is `origin/main` (2133c43dd693e0337987443270a60efdd3ac4ecd). `@ e368d68f` is branch `fix/p308-elicitation-eval-hygiene`, not yet on main, based on 2133c43d.

## 1. Purpose and scope

Issue 98, axis 2 ("Multi-turn / integration harness") asks for a "Multi-turn harness design doc". This is that doc. It describes the harness that exists and marks what is planned.

Some skills (eks-build, eks-design) ask clarifying questions before they produce output. In `claude -p` a question ends the run, so a single-shot eval grades an incomplete run. The multi-turn harness answers those questions from canned answers declared in `evals.json` and resumes the session, so the run is reproducible (`misc/evals/scripts/elicitation.py:4-7 @ 2133c43d`).

Scope today: task evals (`run_task_evals.py`) on the `claude` harness only. Kiro and codex run a multi-turn case as one turn (section 2.7).

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

`run_multiturn_subject` makes the session id itself with `uuid.uuid4()` and passes it on the first turn as `--session-id` (`elicitation.py:171`, `:176 @ 2133c43d`). `extract_session_id` (`elicitation.py:90 @ 2133c43d`) reads it from a `result` or `system/init` event, but nothing under `misc/` calls it. The runner discards the returned id (`run_task_evals.py:686 @ 2133c43d`, `raw_events, timed_out, _ = ...`).

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
- On a harness other than `claude` the runner turns multi-turn off and sets the note `single turn: <harness> has no AskUserQuestion tool non-interactively` (`run_task_evals.py:643-648 @ 2133c43d`). The note is returned as the subject's `elicitation` field (`run_task_evals.py:763 @ 2133c43d`).
- `_PopenRecorder` stands in for `elicitation.subprocess` during the run so every turn's exit code is kept (`run_task_evals.py:831-856 @ 2133c43d`; codes read at `:694`). A non-zero code on any turn makes the run invalid (`run_task_evals.py:752-753 @ 2133c43d`).
- On claude the events pass through `normalize_events` unchanged (`misc/evals/scripts/parse_trajectory.py:544-545 @ 2133c43d`) and are written to `events.jsonl` (`run_task_evals.py:724 @ 2133c43d`); `format_transcript` writes `transcript.md` (`run_task_evals.py:719`, `:212 @ 2133c43d`).
- stderr: on the multi-turn path the runner's `stderr` stays empty (`run_task_evals.py:651 @ 2133c43d`); `elicitation.py` pipes each turn's stderr and never reads it (`elicitation.py:178`, `:200 @ 2133c43d`).

## 3. What the first-half branch adds @ e368d68f

On branch `fix/p308-elicitation-eval-hygiene`, not yet on main.

### 3.1 Plain-text question heuristic

eks-build, eks-design and eks-mcp-server ask in plain text, not with `AskUserQuestion` (`elicitation.py:63-66 @ e368d68f`). With no `AskUserQuestion` in the final assistant message, `detect_pending_question` takes that message's last non-empty text block, splits it on blank lines, and returns the last paragraph if it holds a `?`, else None (`elicitation.py:84-87 @ e368d68f`). `AskUserQuestion` still wins when present (`elicitation.py:75-83 @ e368d68f`).

Stated limits (`elicitation.py:67-69 @ e368d68f`):

- False negative: a question followed by an options paragraph is missed.
- False positive: a closing offer that ends in `?` counts as a question, such as "Want me to confirm?" (the "confirm" false catch). It is then sent to `match_answer`, so a canned turn whose regex matches the offer answers it.

### 3.2 `elicitation_answer` record

Each resumed turn's first event gets `"elicitation_answer": "<answer>"`, the canned answer sent (`elicitation.py:216-219 @ e368d68f`; docstring `:179-181`). A grader reading `events.jsonl` can see what each turn answers. Stated limit: a resumed turn that emits no event loses the record (`elicitation.py:181 @ e368d68f`).

The branch also sends each turn's stderr to `DEVNULL`, since only stdout is read and an unread pipe can stall the subject until the timeout (`elicitation.py:187-191`, `:213 @ e368d68f`).

## 4. Open and planned (not built)

None of this is built.

- Kiro and codex multi-turn. Planned for the P-308 second half. The resume form differs from the claude `--resume` form at `elicitation.py:198 @ 2133c43d`, and the runner forces both to one turn today (`run_task_evals.py:643-648 @ 2133c43d`).
- `transcript.md` rendering of `elicitation_answer`. Planned for the P-308 second half. `format_transcript` (`run_task_evals.py:212 @ 2133c43d`) does not read the field, so the answer is in `events.jsonl` only, not in the transcript the grader reads.
- The runner's stderr pipes at `run_task_evals.py:701` and `:923 @ 2133c43d` (single-turn subject and grader, read only after the stream is drained). Owned by team B's P-307 follow-up, not this harness.
- Issue 98's other axis 2 items, quoted: "Workflow-level evals (does `/apex:eks-design` produce good end-to-end output?)", "Ambient triggering across turns" and "Skill interop when multiple loaded". No plan row holds them yet.
