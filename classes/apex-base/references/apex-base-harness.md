# Harness notes

APEX skills run in several harnesses. They differ in four places: how the user asks for a skill, the ask tool, path variables, and what to do without subagents. This file holds those differences, so a skill's own text stays the same in every harness (rule `apex.harness-notes`).

## How a skill is invoked

| Harness | How the user reaches a skill |
|---|---|
| Claude Code | `/<skill> <request>`, for example `/apex <request>`; the text typed after the command follows the skill as `ARGUMENTS:`. A skill can also load on its own when its description matches. |
| Codex | `$<skill> <request>`, once the skills are copied into a Codex skills folder (the APEX installer does not set this up). |
| Kiro | `/<skill> <request>` in Kiro CLI (tested on 2.35.1, checked on 2026-10-28; 1.27.0 rejected it), or by asking for the skill by name in the chat. |
| AWS DevOps Agent | Through its own skill ports, which take the rules only, with no hook. A zip upload that holds scripts is rejected; a repository import keeps all files. |

## Asking the user

Ask with the harness's ask tool where it has one; else ask in plain text (rule `apex.one-way-to-ask`).

| Harness | Ask tool |
|---|---|
| Claude Code | `AskUserQuestion` |
| Codex | UNVERIFIED: not checked against a live source; ask in plain text until it is |
| Kiro | UNVERIFIED: not checked against a live source; ask in plain text until it is |
| AWS DevOps Agent | UNVERIFIED: not checked against a live source; ask in plain text until it is |

## Path variables

- Claude Code: `${CLAUDE_SKILL_DIR}` is the installed skill's own folder, for example `${CLAUDE_SKILL_DIR}/references/<file>.md`. It points only at this skill's folder, never at another skill.
- Other harnesses: give paths relative to the skill root, one level deep (`references/<file>.md`), as the Agent Skills format defines file references.
- A hook command runs in the current directory, so a relative path in a hook resolves from there, not from the skill folder.

## Without subagents

When the harness has no subagent (Agent) tool, run the steps inline, one after another, in the same session. A skill that offers a subagent mode names its inline fallback.
