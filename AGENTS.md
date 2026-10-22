# AGENTS.md

This file is a short pointer for coding agents working in this repository.

## What this repo is

APEX: agent skills for platform engineering on Amazon EKS and Amazon ECS, plus the installer that puts them into Claude Code and Kiro (`npx apex-skills`).

## Where things are

- Skills live flat, one folder each: `skills/<name>/SKILL.md`. Most are named `eks-*` or `ecs-*`; a few are general (for example `terraform-skill`, `skill-creator`). Do not nest skill folders: Claude Code does not discover a skill under `skills/<group>/<name>/`.
- Router: `skills/apex/SKILL.md` will be the entry skill that routes a request to the right skill. It arrives with the apex router skill and is not in the repo yet; until then, pick the skill whose `description` matches the task.
- `steering/`, `examples/`, `devops-agent/` and `misc/` (installer, evals, website) are described in `CONTRIBUTING.md`.

## Rules for changes

- Contributor rules, the skill format and the release steps are in `CONTRIBUTING.md`. Read it before you add or change a skill.
- Some README sections and the website pages are generated. After changing a skill, run `./misc/update-all-references.sh` and `./misc/update-pages.sh` (see "Keeping docs in sync" in `CONTRIBUTING.md`).
