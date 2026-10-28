# ADR 0006: Skill content, supported installs and automatic triggering

- **Status**: Proposed
- **Date**: 2026-10-26

## Context

On every harness the body of a `SKILL.md` loads into the model's context when the skill runs, so every sentence in it is something the model reads and may act on. The draft router first proposed in aws-samples/sample-apex-skills#283, before this rework (commit f9eb213 on the PR's pre-squash branch; it may not resolve after the merge), mixes run-time instructions with other material: an audience note, a claim that it works when only the skills folder is copied, how it relates to AGENTS.md, research on what the harnesses document, release plans and contributor notes. A maintainer asked why that material is in the skill at all.

That claim about the skills folder raised a second question: which install setups a skill has to work in. A customer can get APEX through the installer, by cloning the whole repo, by copying the `skills/` folder, or by copying one skill folder alone. Each gives the agent a different set of files: one skill folder has no router, no runbooks and no `docs/`; the skills folder has the router and its runbooks but no `docs/`.

The third question is automatic triggering. With every skill installed together, the router's description competes with each sibling's description, and no harness documents which of two matching descriptions wins. The ways to stop a skill triggering on its own differ per harness. Claude Code's `disable-model-invocation: true` frontmatter key keeps the description out of context and blocks the model's own call to the skill. Codex reads `policy.allow_implicit_invocation: false` from the skill's `agents/openai.yaml`, not from SKILL.md; its docs say only that Codex then won't invoke the skill implicitly, while the skill-creator sample in the Codex source (openai/codex, codex-rs/skills/src/assets/samples/skill-creator/references/openai_yaml.md, read 2026-10-27) says the skill is then also not injected into the model's context by default. Kiro's frontmatter has no such switch; a Kiro custom agent loads only the skills listed in its `resources` field. The repo's frontmatter check rejects SKILL.md keys outside `name`, `description`, `license`, `metadata` and `allowed-tools`, and no repo check reads `agents/openai.yaml` (docs read 2026-10-26; versions installed for the local checks: Claude Code 2.1.310, Codex 0.163.0, Kiro CLI 1.27.0).

Options we did not take:

- **Skill content.** Instructions plus a one-line pointer to the rationale (the pointer dangles in a copy without `docs/`), or keeping the rationale in the skill as today (self-contained, but longer, with mixed audiences).
- **Installs.** Supporting one skill folder copied alone, so that a lone skill works for that shape and says plainly what it cannot do there. The maintainer chose the three installs below.
- **Automatic triggering.** Turning it off now, for APEX's own skills, on the harnesses that allow it. The maintainer chose to keep it on for now.

## Decision

**A SKILL.md holds instructions only.** It holds only what the model must do at run time. Design rationale goes to `docs/adr` and `docs/design`; notes about the repo and how to contribute go to CONTRIBUTING.

**Three supported installs.** APEX supports three setups: the installer (npx), a full repo clone, and the skills folder copied on its own. One skill folder copied alone is not a supported setup. What we earlier drafted as a router goal, that a skill copied alone still works and says its limits, moves here and is not adopted.

**Automatic triggering stays on for now.** The other skills keep triggering automatically. Switching it off is an option we may look at later, and if we do, only for APEX's own skills, never for every skill a customer has installed.

## Consequences

- The model reads only what it acts on, and the reasons for a decision are in one place, in the ADRs and design notes.
- A reader who has only a skill's folder does not see why it is written the way it is. Docs and skills have to stay in step.
- The router's other material, its packaging notes (the skills-folder claim among them), harness research, release plans and contributor notes, was dropped from SKILL.md; moving it is open (see Open). The same rule applies to every skill as it is rebuilt.
- The supported installs say what we build and test for; a lone skill folder is not one of them.
- With automatic triggering on, a sibling skill can fire before the router on a plain request. The routing eval in [ADR 0005](0005-router.md) measures that before any switch-off is weighed.
- No frontmatter key is added now, so the repo's frontmatter check stays as it is.

## Open

- What the three supported installs mean for one skill copied alone, which [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md) accepts as a weaker product: whether this record narrows that trade-off or only states what the router is built for (reading, to confirm).
- Where the material taken out of `skills/apex/SKILL.md` goes: the rework dropped the audience note, the skills-folder claim, the AGENTS.md comparison, the harness research, the retirement plan for steering-workflow-creator (removed in step 1) and the note on skills that read a `~/.claude/apex-steering/` path (replaced by a generic run-time rule on a missing file). None of it has moved to `docs/` or CONTRIBUTING yet. The EKS MCP fallback is decided (2026-10-28): when the EKS MCP tools are missing, `rules/AGENTS.md` and the router both ask the user whether they are willing and interested to install the EKS MCP Server, load `eks-mcp-server` on yes, and fall back to kubectl and the AWS CLI on no.
- A skill that reads a file outside `skills/`: before aws-samples/sample-apex-skills#286, `eks-operation-review` read its workflow from a `~/.claude/apex-steering/` path, which the skills-folder copy, one of the three supported installs, does not have (not decided). #286 moved that workflow to `skills/apex/runbooks/eks-operation-review/eks-operation-review.md`, which the vendored skill then reads as `../apex/runbooks/eks-operation-review/eks-operation-review.md`.
- If APEX's own skills are switched off later, `/apex` still loads and is the only automatic route left. On Claude Code the model then cannot call a switched-off skill, so the router hands over only if the user types its `/name` or the model reads its file (untested). On Codex the user's `$name` still runs it; whether the router's own mention counts is untested. Kiro has no frontmatter switch. Whether a skill copied on its own is still meant to trigger automatically, which waits until a switch-off is weighed again (reading, to confirm).
