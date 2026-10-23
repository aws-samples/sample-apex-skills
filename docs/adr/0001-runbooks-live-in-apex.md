# ADR 0001: Runbooks live in one place under the apex skill

- **Status**: Accepted (target design for the next major version; not built yet)
- **Date**: 2026-10-23

## Context

A runbook is the step-by-step part of an engagement: which questions to ask, in what order, which skill to load at each step, and what to hand back. Today the repo has no folder named `runbook` or `runbooks`. The closest thing is the set of steering workflows in `steering/workflows/` (for example `design.md`, `eks-build.md`, `eks-upgrade-check.md`), which the EKS hub `steering/eks.md` routes to. The domain knowledge sits in `skills/<name>/`.

We had to decide where runbooks live in the new design. There were two options.

**Option A: inside each skill**, for example `eks-design/runbook/`. This was our first choice. A user could pick up one skill folder and use it on its own, runbook included, with nothing else from the repo.

**Option B: in one place under the apex skill**, for example `apex/runbooks/`. One folder can serve several sibling skills. If we later have `eks-design` and `gke-design`, one runbook in apex can guide both instead of two near-copies in two skills.

A maintainer argued strongly for option B: customers get one entry point, and they can use, update and edit every runbook in one place. We agreed.

A second point shaped the decision. We strongly advise customers to customize runbooks to fit their own needs. The rest of a skill is domain knowledge that should stay close to upstream; the runbook is the part a customer is expected to adapt. Keeping all the adaptable parts in one folder makes that customization easier to find, review and keep across upgrades.

## Decision

All runbooks live under the apex skill, at `apex/runbooks/<name>`. Skills do not carry their own runbooks: the runbook content is removed from the other skills, which keep their domain knowledge, references and scripts.

## Consequences

- Customers have one place to read and adapt every runbook.
- One runbook can drive several sibling skills, so there is less duplication as the catalog grows.
- A skill used on its own, without apex, has no runbook. We accept that trade-off: see [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md).
- The repo has to change: an apex skill has to exist (there is no `skills/apex/` today), the steering workflows have to move or map into `apex/runbooks/`, and any skill that carries runbook-style steps has to hand them over. That work is part of the next major version, not this record.
- The design notes explain how customers adapt runbooks, so the guidance lives in the docs rather than in the folder layout: [skill design notes](../design/skill-design.md#runbooks).
