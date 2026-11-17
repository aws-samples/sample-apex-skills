# Evals: apex-new-skill

## What these evals target

The `apex-new-skill` skill teaches a contributor how to add a skill, or a class change, to this repository end to end: name, classes and layout, front matter, the `SKILL_META` line, the eval set and sibling-map updates, regenerating the docs, the CI checks, the ADR, the design-doc note and the fact check, the blog question, and the fork, branch, explicit-path commit and pull request flow. `triggering.json` checks that it fires on contributor phrasings (add, contribute, submit, retrofit, pick classes, change a class, open a PR for a new skill) and does not fire on skill-content tuning, vendored-skill edits, doc sync, EKS design or usage, installing the skills, or PR help for another repo. `evals.json` exercises a greenfield add, a retrofit of a skill that landed without evals, the local pre-PR checks, and a class change with its ADR, design-doc note, fact check and blog question.

## Neighbour-skill disambiguation

The closest siblings are `skill-creator` (drafting and tuning a skill's content) and `update-docs` (syncing docs after any skill change). The rest of the negatives are vendored-skill edits, EKS service skills (`eks-design` also writes ADRs, for a customer's cluster) and generic catch-alls.

<!-- SIBLING_MAP_START -->
- **`skill-creator`** (create, edit, optimize and benchmark skill content), negatives 14, 15 ("tighten my skill's description", "benchmark my skill").
- **`terraform-skill`** (vendored skill; edits belong upstream), negative 16 ("Edit skills/terraform-skill/SKILL.md").
- **`eks-recon`** (discover what runs on a live EKS cluster), negative 17 ("What is running on my EKS cluster?").
- **`update-docs`** (sync marker blocks, wrappers and prose after a change), negative 18 ("I edited the description of eks-recon. Sync every README marker block").
- **`eks-design`** (EKS architecture documents and their ADRs), negative 19 ("Design the architecture for a new production EKS cluster").
- **Generic / other repositories and installs** (PR help outside this repo, installing the skills), negatives 20, 21 ("pull request on GitHub for a bug fix in my Django project", "install the APEX skills into Kiro").
- **`eks-best-practices`** (EKS architecture advice), negative 22 ("Karpenter or managed node groups").
<!-- SIBLING_MAP_END -->

The discriminator: getting a new or retrofitted skill into this repository (its files, evals, generated docs, checks and pull request) triggers `apex-new-skill`; writing or tuning what a skill says routes to `skill-creator`; a doc sync with no new skill or class change routes to `update-docs`; an ADR for a customer's cluster design routes to `eks-design`; using a skill on a workload routes to that skill.

## Live-MCP caveat

No `evals.json` task needs a live cluster, MCP server or AWS credentials. Every prompt carries enough context to be answered from the skill's own files; all are `"live_only": false` and runnable offline.

## How to run

From `misc/evals/`:
- `make validate-apex-new-skill`: frontmatter and 64/1024-char limits (deterministic)
- `make triggering-apex-new-skill`: triggering accuracy score (LIVE)
- `make task-apex-new-skill`: task evals with grader (LIVE)
- `make process-apex-new-skill`: process assertions against latest trajectory (deterministic)
- `make artifact-apex-new-skill`: artifact validation against outputs/ (deterministic)
- `make composite-apex-new-skill`: weighted composite score and letter grade (deterministic)

See `misc/evals/README.md` for the full capability catalogue and `.skilleval.yaml` for weight configuration.
