# Evals — steering-workflow-creator

## What these evals target

The `steering-workflow-creator` skill is a meta-skill for authoring new steering workflows (the phased playbooks under `steering/workflows/`) plus their matching `steering/commands/apex/<name>.md` slash-command shims. It teaches the convention (frontmatter keys, header block, five required H2 sections, STOP-gate syntax), the tool-routing tree (knowledge vs live MCP vs setup-bridge), and the lint pass before handoff. `triggering.json` checks that the skill fires on authoring-intent phrasings across several AWS services and does NOT fire on adjacent requests — adding a skill (a different meta workflow), running an engagement against EKS (service-scoped knowledge skills), or pure Kubernetes questions. `evals.json` exercises two end-to-end authoring tasks the skill should be able to answer from its `references/convention.md` and `references/tool-routing.md` alone.

## Neighbour-skill disambiguation

This skill has **no true siblings** in the eval sense. It is meta (about authoring workflows) rather than service-scoped, and the only other meta-skill in the repo, `skill-creator`, is upstream-synced and eval-excluded (see `misc/evals/Makefile`'s coverage exclusion). Negatives therefore bucket into three catchall groups by routing target: the `/apex:new-skill` meta workflow (different meta artefact), the service-scoped EKS skills (vocabulary overlap only in the generic "create" / "help me" verbs), and pure off-repo topics.

<!-- SIBLING_MAP_START -->
- **Meta workflow routing (not a sibling skill)** — the `/apex:new-skill` steering workflow onboards a new *skill*, while this skill authors new *workflows*. Negatives at items 9, 10 phrase the request as adding a skill and must route to the new-skill workflow, not here.
- **`eks-best-practices`** — Day 0/Day 1 EKS architecture + decision frameworks. Negatives at items 11, 14 ("design an EKS cluster", "Karpenter vs MNG") must route there.
- **`eks-upgrader`** — Day 2 EKS upgrade procedures. Negative at item 12 ("upgrade my EKS cluster") must route there.
- **`skill-creator`** — upstream-synced meta-skill for drafting SKILL.md frontmatter + references. Negative at item 13 is a pure frontmatter-review request that belongs to skill-creator, not to this workflow-authoring skill.
- **`eks-mcp-server`** — setup-bridge skill for the EKS MCP server. Negative at item 15 asks how to configure MCP tooling.
- **Generic / non-repo** — pure Kubernetes-internals questions with no authoring hook. Negative at item 16 ("Kubernetes PDB semantics") is a sanity check that this skill does not fire on off-topic K8s content.
<!-- SIBLING_MAP_END -->

The `make score` parser reads only what's between the SIBLING_MAP markers — keep each bullet shaped `- **...** ... negatives N, M ...` (ranges like `11-14` or `11–14` also work) so the sibling-leakage attribution matches every negative. Prose outside the markers is free.

The discriminator: "author a new *workflow*" (H2 sections, STOP gates, `Source:` annotations, shim pairing) triggers this skill; "author a new *skill*" (SKILL.md, frontmatter description optimization, references tree) triggers `skill-creator`; running an engagement against a deployed service triggers the relevant service-scoped skill.

## Live-MCP caveat

Neither `evals.json` task needs a live cluster, MCP server, or AWS credentials. Both are pure authoring tasks answered from `skills/steering-workflow-creator/references/convention.md` and `references/tool-routing.md`. The grader evaluates the response text alone — no `"live_only": true` markers, runnable offline.

## How to run

From `misc/evals/`:
- `make validate-steering-workflow-creator` — frontmatter + 64/1024-char limits
- `make triggering-steering-workflow-creator` — triggering accuracy score
- `make benchmark-steering-workflow-creator` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
