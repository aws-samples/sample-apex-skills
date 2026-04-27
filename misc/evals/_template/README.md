# Evals — <REPLACE>

## What these evals target

<REPLACE: 1-3 sentence scope description — which slice of the skill's declared scope these inputs exercise, and what `triggering.json` vs `evals.json` each check.>

## Neighbor-skill disambiguation

<REPLACE: table or bullet-list mapping each negative prompt in `triggering.json` to the sibling skill it targets, plus the key discriminator that keeps this skill from firing on it. Example shape:

- **`sibling-skill-a`** (one-line scope) — negatives N, M ("short quoted near-miss phrase").
- **`sibling-skill-b`** (one-line scope) — negative K ("short quoted near-miss phrase").

Close with a sentence naming the discriminator that separates this skill from its neighbors.>

## Live-MCP caveat

<REPLACE: note whether the `evals.json` tasks need a live cluster / MCP server, or whether the prompts carry enough context to be answered from fixtures alone. State explicitly whether running these evals requires MCP availability.>

## How to run

From `misc/evals/`:
- `make validate-<REPLACE>` — frontmatter + 64/1024-char limits
- `make triggering-<REPLACE>` — triggering accuracy score
- `make benchmark-<REPLACE>` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
