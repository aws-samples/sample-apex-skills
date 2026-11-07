# README skill-list options (a) to (e)

Each file below is the whole README from PR 377 (head 9e5d484). Only the skill-list part (README lines 84 to 195) differs between them. Repo-relative links and the logo are repointed with `../../` so each page renders from this folder; nothing else is changed. This folder is for viewing only and will not be merged.

## (a) Both lists

[README-a-both-lists.md](README-a-both-lists.md)

- What you see: the hand-written "Pick a skill by what you are doing" list (seven groups, one "Use it to" line per skill), then the generated Skills Reference grid of skill names.
- To maintain when a skill is added: a hand-written row in the grouped list (group and "Use it to" line), plus a run of `misc/update-skills-references.sh` for the grid.

## (b) One generated grouped list

[README-b-generated-grouped.md](README-b-generated-grouped.md)

- What you see: the same grouped list as (a), shown as the generator would print it. No separate grid.
- To maintain when a skill is added: a group and a short "Use it to" field in the skill's own files, then the generator run. Needs a new per-skill field and a generator change; neither is built.

## (c) Generated only

[README-c-generated-only.md](README-c-generated-only.md)

- What you see: only the generated Skills Reference grid of skill names, no grouping by task and no line per skill.
- To maintain when a skill is added: the generator run only, as today.

## (d) Grouped only

[README-d-grouped-only.md](README-d-grouped-only.md)

- What you see: the hand-written grouped list from (a), no grid.
- To maintain when a skill is added: a hand-written row in the grouped list. The generator would stop writing the README block (`misc/update-skills-references.sh:473` errors today when the markers are missing, so the script needs a change); `skills/README.md` keeps its generated list.

## (e) Generated from each SKILL.md description

[README-e-generated-from-skill-description.md](README-e-generated-from-skill-description.md)

- What you see: the same seven groups and order as (a), but each skill's line is the first sentence of its SKILL.md `description:`, copied verbatim from `main`. No separate grid.
- To maintain when a skill is added: a group for the skill (the only new per-skill field) and the generator run. The text comes from the description the skill already has.
- Note: those descriptions are written for the agent to pick the skill, so several first sentences are long trigger lists ("Use whenever someone ...") rather than a short line for a person. Making them read well for people means editing the descriptions themselves, which also changes when agents pick the skill.

## Your question: does a shorter description become another thing to maintain?

Today each skill has one description: the `description:` field in its SKILL.md, written for the agent and up to 1024 characters. The "Use it to" lines in (a), (b) and (d) are a second, hand-kept description of each skill, so yes: each new or changed skill needs that line written and kept in step with its SKILL.md. (e) has no extra description, since it reuses the SKILL.md one. (c) has none at all, since it shows names only.
