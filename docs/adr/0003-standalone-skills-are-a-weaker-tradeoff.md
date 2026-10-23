# ADR 0003: A standalone skill is an accepted, weaker trade-off

- **Status**: Accepted
- **Date**: 2026-10-23

## Context

Skills follow the open [Agent Skills](https://agentskills.io/) format, so anyone can copy one skill folder into their agent and use it without the rest of APEX. Today that mostly works: almost every skill in `skills/` is self-contained (`eks-operation-review` still reads a steering workflow, and `ecs-modernize` reads `terraform-skill`'s files), and the steering workflows that run a full engagement sit outside the skills, in `steering/`.

[ADR 0001](0001-runbooks-live-in-apex.md) puts every runbook under the apex skill. That makes the full engagement depend on apex. A skill picked up on its own keeps its domain knowledge but loses the runbook that tells the agent how to run the engagement.

## Decision

We accept this as a design trade-off. Users who take a single skill without the full APEX setup get a weaker product: the knowledge is all there, the guided engagement is not. We do not duplicate runbooks into skills to close that gap.

## Consequences

- Standalone use keeps working: knowledge skills keep their advice, solution skills their references and scripts; how much runs without a runbook is decided per skill in steps 3 to 5.
- The best experience is the full setup: `/apex`, the apex skill and its runbooks.
- We say this plainly in the docs so nobody is surprised: the [skill design notes](../design/skill-design.md#standalone-skills) explain what a standalone skill does and does not give you.
