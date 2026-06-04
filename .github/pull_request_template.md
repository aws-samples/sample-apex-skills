## Summary

<!-- Brief description of what this PR changes. -->

## If this PR adds or changes a skill

- [ ] Ran `/apex:new-skill` (or walked the equivalent manual steps in `CONTRIBUTING.md`)
- [ ] `skills/<skill>/SKILL.md` present with valid frontmatter
- [ ] `misc/evals/<skill>/triggering.json` authored (≥16 prompts; balanced positives and near-miss negatives)
- [ ] For each neighbour: `misc/evals/<neighbour>/SIBLING_MAP` gained a bullet and its `triggering.json` gained the matching negatives (via `update_sibling_map.py` or hand-edit)
- [ ] Ran the `update-docs` skill and committed any resulting changes (regenerated wrappers/manifest, marker-block updates, prose edits)

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the full new-skill workflow.
