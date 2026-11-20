# Eval set for a new skill

Every new first-party skill needs an eval set under `misc/evals/<name>/`; some existing first-party skills do not have one yet (`make check-evals-coverage`, run from `misc/evals/`, lists them). Vendored skills (`skill-creator`, `terraform-skill`) and the `apex` router do not: CONTRIBUTING.md, Creating a New Skill, step 5, excludes them.

What CONTRIBUTING.md asks for (section "Pre-PR checklist for new skills"):

- "`misc/evals/<name>/triggering.json` has ≥16 prompts (≥8 positives, ≥8 negatives)"
- "Every neighbour's `SIBLING_MAP` block in `misc/evals/<neighbour>/README.md` lists this new skill, and the corresponding negatives are in `misc/evals/<neighbour>/triggering.json`"

The CI hygiene check asks for more (see "evals.json" below); `misc/evals/scripts/check_hygiene.py` holds the full list of what it fails on.

## 1. Scaffold

From `misc/evals/`:

```bash
cd misc/evals
make init-evals SKILL=<name>                      # no siblings
make init-evals SKILL=<name> SIBLINGS="a,b,c"     # with the siblings confirmed in step 2
cd ../..
```

This copies `misc/evals/_template/` to `misc/evals/<name>/` (`README.md`, `triggering.json`, `evals.json`, `.skilleval.yaml`, `files/`) and replaces `<REPLACE>` with the skill name. With `SIBLINGS=` it also writes one placeholder bullet per sibling into the README's SIBLING_MAP block.

## 2. triggering.json

A JSON list of `{"query": "...", "should_trigger": true|false}` objects.

- At least 8 positives: the five prompts from step 1 plus near paraphrases, in the words a user would really type.
- At least 8 near-miss negatives: prompts that sound close but belong to each confirmed sibling. With no siblings, use catch-all negatives (another service, an unrelated domain) and attribute them to one bold non-skill bullet in the sibling map.
- Replace every `<REPLACE: ...>` placeholder entry; leave none behind.

## 3. evals.json

`misc/evals/scripts/check_hygiene.py` (run by the `evals` CI job on every pull request that touches `skills/**` or `misc/evals/**`) warns, and so exits 1, when `evals.json` is missing, has fewer than 2 prompts, or has a prompt with fewer than 3 expectations, among other failures (a missing `.skilleval.yaml` or `README.md`, for example; the script holds the full list). The template ships 1 prompt with 1 expectation, so fill it in: at least 2 realistic task prompts, each with at least 3 grader-checkable expectations.

## 4. README.md and the sibling map

Fill in every `<REPLACE>` marker: the scope, the boundary with siblings, and the live-MCP note ("no live dependencies" for a pure knowledge skill).

Inside `<!-- SIBLING_MAP_START -->` and `<!-- SIBLING_MAP_END -->`, each bullet must keep the shape the parser reads:

```
- **`sibling-name`** (one-line scope), negatives 9, 10 ("short quoted near-miss phrase").
```

Every `should_trigger: false` entry in `triggering.json` must be attributed to a bullet by its index (1-based position in the list, as `update_sibling_map.py` counts), or the hygiene check fails.

## 5. Update each sibling's eval set

For each confirmed sibling, run the helper once. It appends the negatives to the sibling's `triggering.json` and inserts a bullet for the new skill in the sibling's SIBLING_MAP block with the new indices:

```bash
python3 misc/evals/scripts/update_sibling_map.py \
  --new-skill <name> --target-sibling <sibling> \
  --scope "<one-line scope of the new skill>" \
  --negative-prompt "<prompt that should route to the new skill, not the sibling>" \
  --negative-prompt "<a second one>"
```

You write the scope and the prompts; the helper only does the insertion. It writes the sibling's whole `triggering.json` back with two-space indents, so a file in another layout shows a diff on most lines, and it writes the negatives before it checks the README's SIBLING_MAP markers: if it exits 1, read both files before you run it again, or the negatives land twice. These sibling updates go in the same pull request as the new skill.

A sibling with no eval set (the helper exits 1 with "sibling eval dir not found"; `make check-evals-coverage` lists such skills): scaffold one for it first (`make init-evals SKILL=<sibling>` from `misc/evals/`), fill it to the hygiene floor in sections 2 to 4, then run the helper. That widens the pull request to the sibling's folder: say so in the body.

## 6. Check

```bash
cd misc/evals
make init-evals-finalize SKILL=<name>   # same hygiene checks CI runs, for one skill
make hygiene                            # every skill; run after updating siblings
grep -rn '<REPLACE' <name>/             # leftover placeholders; must print nothing
cd ../..
```

Both `make` targets must exit 0. `make hygiene`, the form CI runs, passes a skill that has no eval set at all, which `make init-evals-finalize` fails; neither fails on a `<REPLACE: ...>` placeholder left in a filled file, which the grep finds. Live evals (`make triggering-<name>`, `make task-<name>`) call a model and are not required from a contributor: `misc/evals/README.md` says "Contributors only need to author `triggering.json`. Maintainers run the full eval suite after merge." The hygiene floor above still applies in CI.
