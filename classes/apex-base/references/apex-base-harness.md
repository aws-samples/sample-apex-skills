# Harness notes

APEX skills run in several harnesses. They differ in four places: how the user asks for a skill, the ask tool, path variables, and what to do without subagents. This file holds those differences, so a skill's own text stays the same in every harness (rule `apex.harness-notes`).

## How a skill is invoked

| Harness | How the user reaches a skill |
|---|---|
| Claude Code | `/<skill> <request>`, for example `/apex <request>`; the text typed after the command follows the skill as `ARGUMENTS:`. A skill can also load on its own when its description matches. |
| Codex | `$<skill> <request>`, once the skills are copied into a Codex skills folder (the APEX installer does not set this up). |
| Kiro | `/<skill> <request>` in Kiro CLI (tested on 2.35.1, checked on 2026-10-28; 1.27.0 rejected it), or by asking for the skill by name in the chat. |
| AWS DevOps Agent | Through its own skill ports. A zip upload with a `scripts/` folder is rejected; a repository import keeps all files. With Sandbox (preview) enabled, a skill can include executable code the agent runs in the sandbox. |

## Asking the user

Ask with the harness's ask tool where it has one; else ask in plain text (rule `apex.one-way-to-ask`).

| Harness | Ask tool |
|---|---|
| Claude Code | `AskUserQuestion` |
| Codex | `request_user_input` (one to three short questions), in Plan mode only; in Default mode ask in plain text. Source: openai/codex `codex-rs/core/src/tools/handlers/request_user_input_spec.rs` ("This tool is only available in {allowed_modes}") and `codex-rs/protocol/src/config_types.rs` (`allows_request_user_input`: Plan only), checked on 2026-11-16. |
| Kiro | None: Kiro's built-in tools (https://kiro.dev/docs/tools/, checked on 2026-11-16) include no ask tool, so ask in plain text in the chat. |
| AWS DevOps Agent | None a skill can call: ask in plain text in the chat; the agent shows its own clarification options there ("Disambiguation cards in chat", May 13, 2026, https://docs.aws.amazon.com/devopsagent/latest/userguide/whats-new.html, checked on 2026-11-16). A scheduled or event-triggered run has no chat to ask in, so it states what it assumed. |

## Path variables

- Claude Code: `${CLAUDE_SKILL_DIR}` is the installed skill's own folder, for example `${CLAUDE_SKILL_DIR}/references/<file>.md`. It points only at this skill's folder, never at another skill.
- Other harnesses: give paths relative to the skill root, one level deep (`references/<file>.md`), as the Agent Skills format defines file references.
- A hook command runs in the current directory, so a relative path in a hook resolves from there, not from the skill folder.

## Without subagents

When the harness has no subagent (Agent) tool, run the steps inline, one after another, in the same session. A skill that offers a subagent mode names its inline fallback.
