## Summary

<!-- Brief description of what this PR changes. -->

## If this PR adds or changes a skill

- [ ] Ran `/apex:new-skill` (or walked the equivalent manual steps in `CONTRIBUTING.md`)
- [ ] `skills/<skill>/SKILL.md` present and passes `make validate-<skill>` (run from `misc/evals/`)
- [ ] `misc/evals/<skill>/triggering.json` authored (≥16 prompts; balanced positives and near-miss negatives)
- [ ] `misc/evals/<skill>/evals.json` authored (≥2 realistic task prompts with ≥3 expectations each; every assertion tagged `TODO: human review` until tuned)
- [ ] `misc/evals/<skill>/README.md` filled in — including the SIBLING_MAP block (or explicitly empty with rationale if the skill has no siblings)
- [ ] For each neighbour: `misc/evals/<neighbour>/SIBLING_MAP` gained a bullet and its `triggering.json` gained the matching negatives (via `update_sibling_map.py` or hand-edit)
- [ ] `make init-evals-finalize SKILL=<skill>` exits 0
- [ ] `make check-evals-coverage` exits 0

See [`misc/evals/README.md`](../misc/evals/README.md) for the capability catalogue and [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the full new-skill workflow.
