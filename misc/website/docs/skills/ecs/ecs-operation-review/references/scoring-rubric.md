---
title: "Scoring Rubric & Rating Rules"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/scoring-rubric.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/scoring-rubric.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/scoring-rubric.md). Edit the source, not this page.
:::

# Scoring Rubric & Rating Rules

## Ratings

| Rating | Emoji | Meaning |
|--------|-------|---------|
| GREEN | 🟢 | Fully implemented — matches Amazon ECS best practices |
| AMBER | 🟡 | Partial or inconsistent — improvement opportunity |
| RED | 🔴 | Not implemented or significant gap — action needed |
| UNKNOWN | ⬜ | Cannot be determined from estate data — investigate manually |

## Rules

- **Rate only on observed evidence.** If a check returns no data, times out, or is denied by permissions, mark UNKNOWN — never assume a GREEN or a RED.
- **One item, one rating.** Each check produces exactly one rating; do not average a section into a single score.
- **Blast-radius priority.** When ordering findings, rank by category: **security > availability > cost**. Within a category, cluster-wide/estate-wide issues rank above single-service issues.
- **Every RED needs an action.** A RED finding must have a specific, actionable recommendation with a cited AWS doc URL from `report-generation.md`.
- **Estate scope.** When assessing multiple clusters/services, rate per-resource and roll up: if any production service in a domain is RED, the domain's headline for that cluster is RED. Note which resource drives the rating.
- **Production vs non-production.** If tags (`Environment`, `env`) or naming indicate non-production, an item that would be RED in production may be AMBER — state the assumption explicitly and list it under "Investigate manually" if the environment class is uncertain.

## Maturity score

- Count GREEN, AMBER, RED, UNKNOWN across all rated items.
- Percentages exclude UNKNOWN from the denominator.
- Report the distribution in the Maturity Score table (see `report-generation.md`).

## Consistency contract (MANDATORY)

1. **Ratings are consistent everywhere.** If 04.1 is RED in the findings table, it is RED in the executive summary, prioritized actions, and quick wins — no drift.
2. **Prioritized Actions reference the finding ID.** Write "04.1 — Deployment Circuit Breaker 🔴", not just "Enable circuit breaker".
3. **Every RED appears in Critical or Important. Every AMBER appears in Important or Quick Wins.** Nothing rated RED/AMBER is missing from Prioritized Actions.
4. **Executive Summary matches the findings tables.** Do not call an AMBER a "critical gap", and do not omit a RED.
5. **One row per finding.** Never bundle two findings into one row — each has its own context, action, and references.

## Section index

| # | Section | Reference file |
|---|---------|----------------|
| 01 | Clusters & Capacity | `cluster-capacity.md` |
| 02 | Networking | `networking.md` |
| 03 | Task Definitions | `task-definitions.md` |
| 04 | Services & Deployment Safety | `services-deployment.md` |
| 05 | Service Health & Autoscaling | `service-health-scaling.md` |
| 06 | Observability | `observability.md` |
| 07 | Security Posture | `security-posture.md` |
| 08 | Operational Processes | `operational-processes.md` |
| — | Report generation | `report-generation.md` |
