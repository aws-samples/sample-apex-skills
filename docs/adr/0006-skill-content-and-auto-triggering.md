# ADR 0006: Skill content, supported installs and automatic triggering

- **Status**: Proposed
- **Date**: 2026-10-26

## Context

On every harness the body of a `SKILL.md` loads into the model's context when the skill runs, so every sentence in it is something the model reads and may act on. The first version of the apex router mixes run-time instructions with other material: an audience note, a claim that it works when only the skills folder is copied, how it relates to AGENTS.md, research on what the harnesses document, release plans and contributor notes. A maintainer asked why that material is in the skill at all.

That claim about the skills folder raised a second question: which install setups a skill has to work in. A customer can get APEX through the installer, by cloning the whole repo, by copying the `skills/` folder, or by copying one skill folder alone. Each gives the agent a different set of files: one skill folder has no router, no runbooks and no `docs/`; the skills folder has the router and its runbooks but no `docs/`.

The third question is automatic triggering. With every skill installed together, the router's description competes with each sibling's description, and no harness documents which of two matching descriptions wins. The documented ways to stop a skill triggering on its own differ per harness. On Claude Code (`disable-model-invocation`) and Codex (`allow_implicit_invocation: false`) they also hide the skill's description from the model, and on Claude Code they block the model's own call to the skill. We found no per-skill switch on Kiro. The repo's frontmatter check also rejects keys outside `name`, `description`, `license`, `metadata` and `allowed-tools` today.

Options we did not take:

- **Skill content.** Instructions plus a one-line pointer to the rationale (the pointer dangles in a copy without `docs/`), or keeping the rationale in the skill as today (self-contained, but longer, with mixed audiences).
- **Installs.** Supporting one skill folder copied alone, so that a lone skill works for that shape and says plainly what it cannot do there.
- **Automatic triggering.** Turning it off now, for APEX's own skills, on the harnesses that allow it.

## Decision

**A SKILL.md holds instructions only.** It holds only what the model must do at run time. Design rationale goes to `docs/adr` and `docs/design`; notes about the repo and how to contribute go to CONTRIBUTING.

**Three supported installs.** APEX supports three setups: the installer (npx), a full repo clone, and the skills folder copied on its own. One skill folder copied alone is not a supported setup. What we earlier drafted as a router goal, that a skill copied alone still works and says its limits, moves here and is not adopted.

**Automatic triggering stays on for now.** The other skills keep triggering automatically. Switching it off is an option we may look at later, and if we do, only for APEX's own skills, never for every skill a customer has installed.

## Consequences

- The model reads only what it acts on, and the reasons for a decision are in one place, in the ADRs and design notes.
- A reader who has only a skill's folder does not see why it is written the way it is. Docs and skills have to stay in step.
- The router has to change: its packaging notes (the skills-folder claim among them), harness research, release plans and contributor notes move out of `skills/apex/SKILL.md` into `docs/` and CONTRIBUTING. The same rule applies to every skill as it is rebuilt.
- The supported installs say what we build and test for; a lone skill folder is not one of them.
- With automatic triggering on, a sibling skill can fire before the router on a plain request. The routing eval in [ADR 0005](0005-router.md) measures that before any switch-off is weighed.
- No frontmatter key is added now, so the repo's frontmatter check stays as it is.

## Open

- What the three supported installs mean for one skill copied alone, which [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md) accepts as a weaker product: whether this record narrows that trade-off or only states what the router is built for (reading, to confirm).
- Where the material taken out of `skills/apex/SKILL.md` goes: the rework dropped the audience note, the skills-folder claim, the AGENTS.md comparison, the harness research, the retirement plan for steering-workflow-creator and the note on skills that read a `~/.claude/apex-steering/` path (replaced by a generic run-time rule on a missing file). None of it has moved to `docs/` or CONTRIBUTING yet. The one fact a later doc needs: APEX's `rules/AGENTS.md` says to fall back to kubectl and the AWS CLI when the EKS MCP Server is unavailable, while the router sends missing EKS MCP tools to `eks-mcp-server` (not decided).
- A skill that reads a file outside `skills/`: `eks-operation-review` reads its workflow from a `~/.claude/apex-steering/` path, which the skills-folder copy, one of the three supported installs, does not have (not decided).
- If APEX's own skills are switched off later: whether `/apex` then takes over and works, which a maintainer asked and is not yet answered; and whether a skill copied on its own is still meant to trigger automatically, which waits until a switch-off is weighed again (reading, to confirm).
