---
title: "Fork, branch, commit, pull request"
description: "The flow is CONTRIBUTING.md's section Contributing via Pull Requests: read it first."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex-new-skill/references/pull-request.md
format: md
---

:::info[Source]
This page is generated from [skills/apex-new-skill/references/pull-request.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex-new-skill/references/pull-request.md). Edit the source, not this page.
:::

# Fork, branch, commit, pull request

The flow is CONTRIBUTING.md's section [Contributing via Pull Requests](https://github.com/aws-samples/sample-apex-skills/blob/main/CONTRIBUTING.md#contributing-via-pull-requests): read it first.

Also from CONTRIBUTING.md: main "takes changes only through pull requests" (section "Releasing to npm"), and the section "Licensing": "We will ask you to confirm the licensing of your contribution."

## Commands

Ask the contributor before each push. Never push to `main`.

```bash
# once: fork aws-samples/sample-apex-skills on GitHub, then
git clone https://github.com/<you>/sample-apex-skills.git
cd sample-apex-skills
git remote add upstream https://github.com/aws-samples/sample-apex-skills.git

# per skill: branch off the latest upstream main
git fetch upstream
git switch -c feat/<name>-skill upstream/main
```

Before a new skill, search open and recently merged pull requests and issues for the same idea (the first list in that section). For a new service prefix, the issue comes first: draft its title and body, hand them to the contributor to open, and stop until a maintainer answers.

Commit by explicit path. Never `git add -A` or `git add .`: stage each file `git status --porcelain` lists, by name, once you know why it changed (SKILL.md, step 5).

```bash
git status --porcelain        # only the paths you meant; nothing else staged
git commit -m "feat(skills): add <name> skill"
git push -u origin feat/<name>-skill   # only after the contributor says yes
```

CONTRIBUTING.md asks only for "clear commit messages"; recent history on `main` uses conventional-commit titles such as `feat(<scope>): ...`, `fix: ...`, `chore(deps): ...`, so `feat(skills): add <name> skill` fits.

Keep the pull request to the new skill and its obligations: the skill folder, its eval set, sibling eval updates, its `SKILL_META` line and catalogue rows, regenerated docs, and the ADR and design-doc note from SKILL.md step 7. No reformatting of unrelated files (the second list in that section).

## The pull request

The contributor opens it from the fork's branch against `aws-samples/sample-apex-skills` `main`, in the GitHub web interface or with `gh pr create --repo aws-samples/sample-apex-skills --base main`. Answer the template in `.github/pull_request_template.md`: its "If this PR adds or changes a skill" checklist opens with "Walked the new-skill steps in `CONTRIBUTING.md`": tick it, since this skill walks them. The rest asks for valid front matter, the `triggering.json` set, the sibling-map updates, and that you ran the `update-docs` skill and committed the result.

In the body: what the skill does, who it is for, its classes, its siblings and how they differ, the check commands you ran with their results (and each planned check named as not run), and the `## Fact check` section from SKILL.md step 7. No internal or customer details: the body is public too.

After opening it, watch the `docs-sync` and `evals` jobs. A failure prints the diff or the warning; fix it locally, re-run the checks, commit by path, push.

Opening the pull request is the contributor's decision: prepare the commands, title and body, and hand them over.
