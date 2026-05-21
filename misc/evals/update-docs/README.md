# Evals — update-docs

## What these evals target

The `update-docs` skill audits and updates every documentation surface in the APEX repo after skill/steering changes — marker blocks, Docusaurus wrappers, and prose references. `triggering.json` checks that the skill fires on doc-sync/audit phrasings and does NOT fire on adjacent meta requests (creating skills, authoring workflows) or service-scoped questions. `evals.json` exercises two end-to-end scenarios: a skill rename ripple and a new-skill addition in chat-only mode.

## Neighbour-skill disambiguation

The only true sibling is `skill-creator` — both are meta-skills that operate on the `skills/` directory, but `update-docs` audits existing documentation while `skill-creator` drafts new skill content. Negatives bucket into skill-creator (authoring/optimizing SKILL.md), steering-workflow-creator (authoring workflows), and service-scoped catchalls (EKS, Terraform).

<!-- SIBLING_MAP_START -->
- **`skill-creator`** (create, edit, optimize, and benchmark skills) — negatives 9–12 phrase requests as drafting or optimizing a SKILL.md, which routes to skill-creator, not here.
- **`steering-workflow-creator`** (author steering workflows with convention and lint) — negative 14 asks for a new steering workflow with H2 sections and STOP gates.
- **Generic / service-scoped** — negatives 13, 15, 16 target EKS architecture, EKS MCP setup, and Terraform modules respectively. Sanity checks that docs-audit intent doesn't bleed into service skills.
<!-- SIBLING_MAP_END -->

The discriminator: "audit / sync / check / update the docs" triggers `update-docs`; "create / draft / optimize a skill" triggers `skill-creator`; "author a workflow" triggers `steering-workflow-creator`; service-scoped questions route to their respective service skills.

## Live-MCP caveat

Neither `evals.json` task needs a live cluster, MCP server, or AWS credentials. Both scenarios can be graded from response text alone — the skill reads repo state via filesystem and git, not via MCP tools. No `"live_only": true` markers; runnable offline.

## How to run

From `misc/evals/`:
- `make validate-update-docs` — frontmatter + 64/1024-char limits
- `make triggering-update-docs` — triggering accuracy score
- `make benchmark-update-docs` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
