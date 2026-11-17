# ADR 0006: The five stages are the router's journey, not a rule in each skill

- **Status**: Accepted
- **Date**: 2026-11-16

## Context

An earlier design gave every skill that does work the same five stages: recon, analyse, map, build and validate. A skill would use only the stages it needs, each stage would produce its own artifact, and a shared helper would refuse a stage until the one before it was done. The stages were to be written once and copied into every skill.

Since then the design has moved. [ADR 0004](0004-naming.md) made every skill other than `apex` a standalone knowledge or solution skill. [ADR 0005](0005-skill-classes.md) shares rules through classes, and every sentence in a class is copied into every member, so a class rule has to hold for every member. The per-skill runbooks under `skills/apex/runbooks/` are being absorbed: their shared parts into the classes, the rest into the skills, and the runbook folder keeps only examples of how to chain skills.

Very few skills have all five stages. eks-recon and ecs-recon are recon. eks-operation-review, eks-upgrade-check and eks-cost-intelligence analyse. eks-design maps a target. eks-build and ecs-build build. A rule in every skill would leave most skills carrying stages they do not have.

We weighed three options:

- **Keep** the five stages as a rule every skill follows. Dropped: most skills would carry empty stages, and the rule would not hold for every member of the base class.
- **Reshape** them into the journey the router walks a customer through.
- **Drop** them. Kept as the fallback if reshaping does not hold up. Not taken, because the order still describes how our skills hand off: discovery comes before a review, a design before a build.

## Decision

**Reshape.** The five stages are the journey the `apex` router walks a customer through and the order skills hand off in. They are not a rule inside each skill, and the base class gets no stage rule.

- **Recon**: find what is running (eks-recon, ecs-recon).
- **Analyse**: assess it (for example eks-operation-review, eks-upgrade-check, eks-cost-intelligence, eks-security).
- **Map**: plan the target (for example eks-design, ecs-architect).
- **Build**: produce the code or the change (for example eks-build, ecs-build, eks-platform-engineering).
- **Validate**: check the result against the plan, by running an analysing skill again or the design's own validation.

A customer may start at any stage. The router's Day 0, Day 1 and Day 2 families stay as they are: they say where a customer is, and the stages say what comes next.

**How it reads to a customer once runbooks are absorbed.** The customer asks `apex`. The router works out where they are, sends them to the first skill that fits, and at each hand-off offers the next skill in stage order, carrying the context forward so nothing is asked twice (the router's hand-off table). Each skill does its own job fully on its own. A customer who wants a fixed engagement, such as recon, then an operations review, then an upgrade check, writes it as their own runbook, using the example runbooks as a model.

## Consequences

- Skills do not change for this decision; the base class gets no stage rule.
- The stage order lives in one place, the router's hand-off table, and moves with the router into its class.
- A skill copied out alone loses the journey but keeps its own job, which [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md) already accepts for hand-offs.
- Nothing refuses a later stage before an earlier one: a customer can ask for a build without a recon, and the build skill gathers what it needs.

## Open

- Whether the router writes an artifact per stage, and where it keeps them, is not decided here.
