---
title: "Generated docs and repo checks"
description: "All commands run from the repo root."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex-new-skill/references/repo-checks.md
format: md
---

:::info[Source]
This page is generated from [skills/apex-new-skill/references/repo-checks.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex-new-skill/references/repo-checks.md). Edit the source, not this page.
:::

# Generated docs and repo checks

All commands run from the repo root. The generators and the validator parse front matter with PyYAML: CONTRIBUTING.md says "running them locally requires it: `pip install pyyaml`". None of them needs network access.

## What a new skill reaches

`misc/installer/bin/cli.mjs` (`getSkills`) links the directories under `skills/` into a user's skills folder, so a merged content skill reaches every `npx apex-skills` install at the next release tag (installer 1.3.0 and later install the newest `v1.x.y` tag, per CONTRIBUTING.md, "Releasing to npm"). Write for that audience, and keep the public-repo rule: no internal or customer content.

## Generators

The list to run is the Steward class's `generators` in `classes/steward/class.yaml` (each `run`, then each `check`; a `status: planned` entry is not built yet: name it as not run). The table below describes generators that entry lists; run each entry whose status is `exists`. Never edit their output by hand. CONTRIBUTING.md: "The regenerator owns everything between the markers".

| Command | Rebuilds | Reads sources from |
|---|---|---|
| `./misc/update-all-references.sh` | Marker blocks in `README.md` (Skills and Examples reference), the detail block in `skills/README.md`, `devops-agent/README.md`. It runs `misc/update-skills-references.sh` and its siblings; that script fails (exit 1) on a skill with no `SKILL_META` line, no summary or a group not in `README_GROUPS`. | The filesystem (`skills/*/SKILL.md` front matter) and the `SKILL_META` table in `misc/update-pages.sh` |
| `./misc/update-pages.sh` | Website wrappers `misc/website/docs/skills/<group>/<name>/index.md` (and one per `.md` under the skill), the group page `misc/website/docs/skills/<group>/index.md` for `eks` and `ecs`, the card grid `misc/website/docs/skills/index.md`, `misc/website/static/manifests/skills.json` and `misc/website/static/llms.txt` | `git ls-files`, so only staged or committed files |

`<group>` is `eks` for `eks-*` names, `ecs` for `ecs-*`, else `general`.

Order matters. Run the generators only after the skill's files are staged, each by name (SKILL.md, step 5). If `update-pages.sh` runs first it writes manifest and card entries but no wrapper page, and CI fails later. Confirm:

```bash
ls misc/website/docs/skills/*/<name>/index.md
```

Then stage what they produced, by path: list it with `git status --porcelain -uall` and add each line you expect. Anything in that list you did not expect (a file outside the generator outputs, a stray report) stays unstaged: find out why it changed first.

## Checks

Run each; each must exit 0. The first three and the two test commands are among what `.github/workflows/docs-sync.yml` runs; the hygiene check is what `.github/workflows/evals.yml` runs. The `vendored-guard` job also fails a pull request that edits a vendored folder (rule 5 in SKILL.md).

| Command | Checks |
|---|---|
| `python3 misc/validate-frontmatter.py` | Every `skills/*/SKILL.md` and `devops-agent/*/SKILL.md`: front matter is a YAML mapping; `name` and `description` present; `description` at most 1024 characters; only `name`, `description`, `license`, `metadata`, `allowed-tools` keys; no anchors or aliases; block under 64KB; nesting depth at most 8; description equals the `skills.json` entry (a missing entry is only a warning, so run `update-pages.sh` to add it). |
| `./misc/update-all-references.sh --check` | Regenerates the marker blocks, then fails on any `git diff` in `README.md`, `skills/README.md`, `devops-agent/README.md`. |
| `./misc/update-pages.sh --check` | Regenerates wrappers and manifests, then fails on any diff or any untracked generated file under `misc/website/docs/` or `misc/website/static/manifests/`. Unstaged new wrappers count as untracked: stage them first. It also fails on a skill with no `SKILL_META` line. |
| `python3 -B misc/tests/test_reference_markers.py -v` | The reference marker blocks. |
| `node --experimental-strip-types --test misc/website/src/components/skillSearch.test.ts` | The skill finder's search, which reads the catalogue entry step 5 adds. |
| `python3 misc/evals/scripts/check_hygiene.py` | Every eval set under `misc/evals/`: front matter via `quick_validate.py`, 8+ positives and 8+ negatives in `triggering.json`, 2+ prompts with 3+ expectations each in `evals.json`, every negative attributed in SIBLING_MAP. Per skill: `cd misc/evals && make init-evals-finalize SKILL=<name>`. It passes a skill with no eval set (the per-skill form fails it): see [evals.md](evals.md), section 6. |
| `python3 skills/skill-creator/scripts/quick_validate.py skills/<name>` | Name is kebab-case, at most 64 characters; description at most 1024 characters with no `<` or `>`; allowed keys. |
| Each class check with status `exists` in the `checks` of the skill's classes and their parents | What the class says it checks. |

`--check` compares the working tree with the git index, so it passes once regenerated output is staged; CI runs it on the committed tree.

## Optional: package the skill

CONTRIBUTING.md's manual path ends with packaging the skill. Run `package_skill.py` as a module from `skills/skill-creator` (it imports `scripts.quick_validate`, so run by file path it exits 1 with `ModuleNotFoundError`), with an output directory outside the repo (with none, it writes the `.skill` into `skills/skill-creator/`, a vendored folder), and never commit the `.skill` file:

```bash
(cd skills/skill-creator && python3 -m scripts.package_skill ../<name> "$(mktemp -d)")
```

## Prose that the generators do not cover

After the scripts pass, look for hand-written skill lists, counts and links that the new skill makes stale (CONTRIBUTING.md, "Keeping skill docs in sync after changes", asks you to run the `update-docs` skill, which walks them). Propose prose edits to the contributor; do not rewrite other skills' content.
