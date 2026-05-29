---
sidebar_position: 6
title: Contributing
---

# Contributing

APEX skills are authored using the [`skill-creator`](./skills) skill, which encodes the [Agent Skills](https://agentskills.io/) spec — frontmatter constraints, the `scripts/` / `references/` / `assets/` layout, and the iterate-with-evals loop.

See [`CONTRIBUTING.md`](https://github.com/aws-samples/sample-apex-skills/blob/main/CONTRIBUTING.md) in the repo for the full contribution flow.

## Running `update-docs`

Adding, renaming, or removing a skill — or editing a `SKILL.md` frontmatter description — should be followed by running the [`update-docs`](./skills/update-docs) skill so wrappers, marker blocks, and prose references stay in sync.
