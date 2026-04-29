# Evals — <REPLACE>

## What these evals target

<REPLACE: 1-3 sentence scope description — which slice of the skill's declared scope these inputs exercise, and what `triggering.json` vs `evals.json` each check.>

## Neighbour-skill disambiguation

<REPLACE: 1-2 sentences framing the boundary with sibling skills. Then fill in the sibling map below.>

<!-- SIBLING_MAP_START -->
- **`sibling-skill-a`** (one-line scope) — negatives N, M ("short quoted near-miss phrase").
- **`sibling-skill-b`** (one-line scope) — negative K ("short quoted near-miss phrase").
<!-- SIBLING_MAP_END -->

<REPLACE: close with a sentence naming the discriminator that separates this skill from its neighbours. The `make score` parser reads only what's between the SIBLING_MAP markers — keep each bullet shaped `- **`sibling-name`** ... negatives N, M ...` (ranges like `9-11` or `9–11` also work) so the sibling-leakage attribution matches every negative in `triggering.json`. Prose outside the markers is free.>

## Live-MCP caveat

<REPLACE: note whether the `evals.json` tasks need a live cluster / MCP server, or whether the prompts carry enough context to be answered from fixtures alone. State explicitly whether running these evals requires MCP availability.>

## How to run

From `misc/evals/`:
- `make validate-<REPLACE>` — frontmatter + 64/1024-char limits
- `make triggering-<REPLACE>` — triggering accuracy score
- `make benchmark-<REPLACE>` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
