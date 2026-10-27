# ADR 0004: One entry skill, and standalone knowledge and solution skills

- **Status**: Accepted
- **Date**: 2026-10-23

## Context

The new design has one skill that every engagement starts from, `apex`, and many skills that hold domain knowledge or do a piece of work. We needed names for that structure. The name is how contributors and customers talk about it, and it goes into the docs, so we wanted one that describes what the skills actually do.

We considered three pairs of names:

- **Hub and children.** "Hub" already appears in the repo (`steering/eks.md` calls itself the central hub). But it mixes two metaphors, a wheel and a family tree, and "children" suggests the skills belong to the hub.
- **Hub and spoke.** One consistent metaphor that many readers know. But spokes suggest a skill only connects through the hub, while a skill can be used on its own and one skill can call another. The term also already names a cluster topology in the EKS platform engineering skill.
- **Parent and child.** Familiar from software. But it suggests inheritance, that a child gets behavior or settings from its parent. Skills inherit nothing; `apex` routes and orchestrates. We rejected it.

None of the three fits: each implies a dependency the skills do not have.

## Decision

`apex` is the **entry skill**. Every other skill is a **standalone skill**, and each standalone skill is one of two kinds:

- a **knowledge skill** gives guidance and advice on a domain, for example `eks-best-practices`;
- a **solution skill** does a piece of work and hands back a result, for example `eks-design`, `eks-build` or `eks-cost-intelligence`.

## Consequences

- The names say what each skill is, not how it relates to another one, so they hold whether a skill is reached through `apex` or used on its own.
- "Standalone" matches the trade-off in [ADR 0003](0003-standalone-skills-are-a-weaker-tradeoff.md): a standalone skill works by itself, with less guidance than through `apex`.
- These terms are used in the docs. They do not rename any skill folder or `name` field (the Agent Skills spec requires `name` to match the folder name). "The EKS hub" named `steering/eks.md` when this record was written (removed in step 1).
- The wider reasoning is in the [skill design notes](../design/skill-design.md#the-entry-skill-and-standalone-skills).
