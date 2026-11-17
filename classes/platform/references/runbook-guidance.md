# Runbook guidance

How a member skill runs a guided engagement with the user.

## Modes

Pick a mode from what the user asked for:

| User intent | Mode |
|---|---|
| A full engagement ("build", "design", "plan" the whole thing) | Full: every phase, in order |
| One part of it (one layer, one decision, one tool) | Scoped: an abbreviated first phase, then the phases that part needs; defaults for the rest |
| An overview ("what does a production setup look like?") | Summary: the phases condensed |

A single concept question is not an engagement: answer it directly and skip the phases.

## Phases

Run the phases in order. Each phase names its source: "Source: knowledge" means it uses the skill's knowledge only, with no live reads.

## Inputs

Ask the required inputs in one turn. Read what the user already gave first (a report, a requirements file, an earlier answer) and ask only what is still missing (`apex.one-way-to-ask`).

## Gates

Restate what you understood and wait for the user's confirmation before a recommendation, before generating an artifact, and before any change (`operator.confirm-before-change` already requires the last). When a gate fires, name the one decision you need.

## Recommend, do not enumerate

- Name the default and the trade-off. Show the full option matrix only when the user pushes back.
- Explain each key choice briefly. Do not emit code or a document silently.
- Say which mode you picked and why.

## Check before presenting

Self-grade the output against the skill's own declared checklist and pass threshold before you present it; for an Operator member these are its artifact checks, all of which must pass (`operator.artifact-checks`). The threshold is the skill's: there is no shared one. Below it, fix the gaps first.
