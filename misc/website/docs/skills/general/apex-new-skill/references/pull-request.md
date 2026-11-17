---
title: "Fork, branch, commit, pull request"
description: "The flow is CONTRIBUTING.md's section \"Contributing via Pull Requests\"."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex-new-skill/references/pull-request.md
format: md
---

:::info[Source]
This page is generated from [skills/apex-new-skill/references/pull-request.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex-new-skill/references/pull-request.md). Edit the source, not this page.
:::

# Fork, branch, commit, pull request

The flow is CONTRIBUTING.md's section "Contributing via Pull Requests". Its words, quoted:

> Before sending us a pull request, please ensure that:
>
> 1. You are working against the latest source on the *main* branch.
> 2. You check existing open, and recently merged, pull requests to make sure someone else hasn't addressed the problem already.
> 3. You open an issue to discuss any significant work - we would hate for your time to be wasted.

> To send us a pull request, please:
>
> 1. Fork the repository.
> 2. Modify the source; please focus on the specific change you are contributing. If you also reformat all the code, it will be hard for us to focus on your change.
> 3. Ensure local tests pass.
> 4. Commit to your fork using clear commit messages.
> 5. Send us a pull request, answering any default questions in the pull request interface.
> 6. Pay attention to any automated CI failures reported in the pull request, and stay involved in the conversation.

Also from CONTRIBUTING.md: main "takes changes only through pull requests", and the section "Licensing": "We will ask you to confirm the licensing of your contribution."

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

Before a new skill, search open and recently merged pull requests and issues for the same idea (step 2 of the first list). For a new service prefix, open the issue first.

Commit by explicit path. Never `git add -A` or `git add .`:

```bash
git add skills/<name>/ misc/evals/<name>/ misc/update-pages.sh
git add docs/adr/<NNNN>-<slug>.md docs/adr/README.md docs/design/skill-design.md
git add misc/evals/<sibling>/README.md misc/evals/<sibling>/triggering.json   # one pair per sibling
git add README.md skills/README.md misc/website/docs/skills/index.md \
  misc/website/static/manifests/skills.json misc/website/docs/skills/<group>/<name>/
git status --porcelain        # only the paths you meant; nothing else staged
git commit -m "feat(skills): add <name> skill"
git push -u origin feat/<name>-skill
```

CONTRIBUTING.md asks only for "clear commit messages"; recent history on `main` uses conventional-commit titles such as `feat(<scope>): ...`, `fix: ...`, `chore(deps): ...`, so `feat(skills): add <name> skill` fits.

Keep the pull request to the new skill and its obligations: the skill folder, its eval set, sibling eval updates, its `SKILL_META` line and catalogue rows, regenerated docs, and the ADR and design-doc note from SKILL.md step 7. No reformatting of unrelated files (step 2 of the second list).

## The pull request

Open it from the fork's branch against `aws-samples/sample-apex-skills` `main`, in the GitHub web interface or with `gh pr create --repo aws-samples/sample-apex-skills --base main`. Answer the template in `.github/pull_request_template.md`: its "If this PR adds or changes a skill" checklist opens with "Walked the new-skill steps in `CONTRIBUTING.md`": tick it, since this skill walks them. The rest asks for valid front matter, the `triggering.json` set, the sibling-map updates, and that you ran the `update-docs` skill and committed the result.

In the body: what the skill does, who it is for, its classes, its siblings and how they differ, the check commands you ran with their results (and each planned check named as not run), and the `## Fact check` section from SKILL.md step 7. No internal or customer details: the body is public too.

After opening it, watch the `docs-sync` and `evals` jobs. A failure prints the diff or the warning; fix it locally, re-run the checks, commit by path, push.

Opening the pull request is the contributor's decision: prepare the commands, title and body, and hand them over.
