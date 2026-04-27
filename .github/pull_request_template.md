## Summary

<!-- Brief description of what this PR changes. -->

## If this PR adds a new skill

- [ ] `skills/<skill>/SKILL.md` present and passes `make validate-<skill>` (run from `misc/evals/`)
- [ ] `misc/evals/<skill>/triggering.json` authored (≥16 prompts; balanced positives and near-miss negatives)
- [ ] `misc/evals/<skill>/evals.json` authored (≥2 realistic task prompts; every assertion tagged `TODO: human review` until tuned)
- [ ] `misc/evals/<skill>/README.md` filled in (replaces `<REPLACE>` markers from the template)
- [ ] `make check-evals-coverage` exits 0

See [`misc/evals/README.md`](../misc/evals/README.md) for the capability catalogue and [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the full new-skill workflow.
