# ADR 0001: Runbooks live in one place under the apex skill

- **Status**: Accepted
- **Date**: 2026-10-23

## Context

A runbook is the step-by-step part of an engagement: which questions to ask, in what order, which skill to load at each step, and what to hand back. Today (2026-10-23) the repo has no folder named `runbook` or `runbooks`. The closest thing is the set of steering workflows in `steering/workflows/` (for example `design.md`, `eks-build.md`, `eks-upgrade-check.md`), which the EKS hub `steering/eks.md` routes to. The domain knowledge sits in `skills/<name>/`.

We had to decide where runbooks live in the new design. There were two options.

**Option A: inside each skill**, for example `eks-design/runbook/`. This was our first choice. A user could pick up one skill folder and use it on its own, runbook included, with nothing else from the repo.

**Option B: in one place under the apex skill**, at `skills/apex/runbooks/`.

A maintainer argued strongly for option B: customers get one entry point, and they can use, update and edit every runbook in one place. We agreed.

A second point shaped the decision. We strongly advise customers to customize runbooks to fit their own needs. The rest of a skill is domain knowledge that should stay close to upstream; the runbook is the part a customer is expected to adapt. Keeping all the adaptable parts in one folder makes that customization easier to find, review and carry across upgrades in a fork.

Inside that folder we had to choose how to group runbooks: by task (`design/`, `build/`) or by skill (`eks-design/`, `eks-build/`). A task name blurs platforms: "design" for EKS and "design" for ECS are different work. A skill name does not.

## Decision

All runbooks live under the apex skill, at `skills/apex/runbooks/<skill>/`, one folder per skill for now. Skills do not carry their own runbooks: the runbook content is removed from the other skills, which keep their domain knowledge, references and scripts.

For now, only the apex skill points at runbooks. No other skill's SKILL.md loads a runbook from `apex/runbooks/`, with one recorded exception: the vendored `eks-operation-review`, whose sync script rewrites upstream's pointer to `../apex/runbooks/eks-operation-review/eks-operation-review.md`.

Set: a runbook is a procedure, not an information source; domain knowledge lives only in the skill, so there is one surface to maintain. Still open, decided in steps 3 to 5 of the plan (see the [skill design notes](../design/skill-design.md#plan)): how thin each runbook gets, whether runbooks stay grouped by skill, and where a runbook that spans several skills goes. Also left for steps 3 to 5: five of the seven moved runbooks still carry their own routing table ("How to Route Requests"), while the apex skill's tables route; step 1 does not edit them.

## Consequences

- Customers have one place to read and adapt every runbook.
- Each runbook sits next to the skill name it serves, so EKS and ECS work never share a folder by accident.
- A skill used on its own, without apex, has no runbook. We accept that trade-off: see [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md).
- The repo has to change: an apex skill has to exist (there is no `skills/apex/` today), the steering workflows have to move into `apex/runbooks/<skill>/`, and any skill that carries runbook-style steps has to hand them over. That work is part of the next major version, not this record.
- The design notes explain how customers adapt runbooks, so the guidance lives in the docs rather than in the folder layout: [skill design notes](../design/skill-design.md#runbooks).
- A runbook reaches its skill's files through `../../../<skill>/` or a repo-root path such as `skills/<skill>/references/` (three runbooks, eks-genai, eks-platform-engineering and eks-security, also name them with no path), a chain two levels deep, while the [Agent Skills specification](https://agentskills.io/specification) asks for file references one level deep from `SKILL.md`. Step 1 repoints those paths to the new depth and keeps the two-level chain; flattening it is for steps 3 to 5.
