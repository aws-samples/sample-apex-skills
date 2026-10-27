# ADR 0002: `/apex` routes directly into the apex skill

- **Status**: Accepted
- **Date**: 2026-10-23

## Context

Today `apex` is a command namespace, not a command. The folder `steering/commands/apex/` holds the slash commands `/apex:eks`, `/apex:eks-design`, `/apex:eks-build`, `/apex:new-skill` and the others, and the installer links that folder into `~/.claude/commands/apex`. Each command loads one steering file: `/apex:eks` loads the EKS hub `steering/eks.md`, and `/apex:new-skill` loads `steering/workflows/new-skill.md`.

There is no bare `/apex` command. The APEX meta hub, `steering/apex.md`, is a steering file that no slash command loads. There is also no apex skill in `skills/` yet. So by design there is a gap: a user has no single, direct way to reach the apex entry point.

In the new design, apex becomes the entry skill that every engagement starts from ([ADR 0004](0004-naming.md)), and it holds the runbooks ([ADR 0001](0001-runbooks-live-in-apex.md)). That entry skill needs a front door. We did not weigh another front door; the open part is today's `/apex:<name>` commands (see Consequences).

## Decision

Keep `/apex`, and make it route directly into the apex skill. `/apex` is the one entry point; the apex skill then routes to the right runbook and standalone skill.

## Consequences

- Users have one command to remember, and it lands them on the entry skill that knows every runbook.
- The gap between the slash commands and the apex entry point closes.
- The repo has to change: a bare `/apex` command has to be added and wired to the apex skill, and the place of today's `/apex:<name>` commands has to be settled (kept as shortcuts, or folded into the apex skill). That is part of the next major version.
- In step 1 of the plan, `/apex` is wired to the apex skill, which then takes over routing for now. `/apex:new-skill` is not moved into a runbook: it is removed with `steering/`, and the contributor skill that replaces it is built in step 7 of the plan, once we know what a skill is (see the [skill design notes](../design/skill-design.md#plan)).
