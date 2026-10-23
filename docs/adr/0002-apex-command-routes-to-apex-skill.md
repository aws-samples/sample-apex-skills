# ADR 0002: `/apex` routes directly into the apex skill

- **Status**: Accepted (target design for the next major version; not built yet)
- **Date**: 2026-10-23

## Context

Today `apex` is a command namespace, not a command. The folder `steering/commands/apex/` holds the slash commands `/apex:eks`, `/apex:eks-design`, `/apex:eks-build`, `/apex:new-skill` and the others, and the installer links that folder into `~/.claude/commands/apex`. Each command loads one steering file: `/apex:eks` loads the EKS hub `steering/eks.md`, and `/apex:new-skill` loads `steering/workflows/new-skill.md`.

There is no bare `/apex` command. The APEX meta hub, `steering/apex.md`, is a steering file that no slash command loads. There is also no apex skill in `skills/` yet. So by design there is a gap: a user has no single, direct way to reach the apex entry point.

In the new design, apex becomes the hub skill that every engagement starts from, and it holds the runbooks ([ADR 0001](0001-runbooks-live-in-apex.md)). That hub needs a front door.

## Decision

Keep `/apex`, and make it route directly into the apex skill. `/apex` is the one entry point; the apex skill then routes to the right runbook and child skill.

## Consequences

- Users have one command to remember, and it lands them on the hub that knows every runbook.
- The gap between the slash commands and the apex entry point closes.
- The repo has to change: a bare `/apex` command has to be added and wired to the apex skill, and the place of today's `/apex:<name>` commands has to be settled (kept as shortcuts, or folded into the hub). That is part of the next major version.
