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
| N/A | ⬜ | Check does not apply to this estate's compute model / architecture — see below |

### N/A vs UNKNOWN (distinct states)

**N/A** and **UNKNOWN** are different and must not be conflated:

- **UNKNOWN** = the check *applies* but the data could not be obtained (permission denied, timeout, ambiguous evidence). UNKNOWN items **go on the "Investigate Manually" list**.
- **N/A** = the check *does not apply* to this estate by design — e.g., an EC2-ASG-only check on a Fargate-only estate, GuardDuty Runtime Monitoring on a Managed-Instances-only estate (7.4), or a Windows/ECS-Anywhere/Express-Mode workload where a Linux/Fargate assumption doesn't hold. State the reason inline.

**N/A items are excluded from BOTH the maturity-score table AND the "Investigate Manually" list** — there is nothing to investigate and nothing to score. They may be listed in a short "Not applicable (with reason)" note if useful, but they never affect counts or percentages. Reference files that already use N/A branches: 1.2, 1.4, 1.6, 2.5, 5.1, 6.5, 7.4, 8.3.

## Rules

- **Rate only on observed evidence.** If a check returns no data, times out, or is denied by permissions, mark UNKNOWN — never assume a GREEN or a RED.
- **One item, one rating.** Each check produces exactly one rating; do not average a section into a single score.
- **Blast-radius priority.** When ordering findings, rank by category: **security > availability > cost**. Within a category, cluster-wide/estate-wide issues rank above single-service issues.
- **Every RED needs an action.** A RED finding must have a specific, actionable recommendation with a cited AWS doc URL from `report-generation.md`.
- **Estate scope.** When assessing multiple clusters/services, rate per-resource and roll up: if any production service in a domain is RED, the domain's headline for that cluster is RED. Note which resource drives the rating.
- **Production vs non-production.** If tags (`Environment`, `env`) or naming indicate non-production, an item that would be RED in production may be AMBER — state the assumption explicitly and list it under "Investigate manually" if the environment class is uncertain.

## Maturity score

- Count GREEN, AMBER, RED, UNKNOWN across all rated items. **N/A items are not counted at all** (see the N/A vs UNKNOWN section).
- Percentages exclude UNKNOWN (and N/A) from the denominator.
- **Always report coverage alongside every percentage.** A percentage computed over a handful of assessable items while most are UNKNOWN is misleading (e.g., "5 GREEN + 30 UNKNOWN" is **not** "100% GREEN"). Next to each maturity percentage, state **"N of M items assessable (X% coverage)"**, where N = GREEN+AMBER+RED and M = all items except N/A.
- **Do NOT quote a headline maturity percentage when UNKNOWN exceeds ~25% of assessable-plus-unknown items.** Instead lead with the coverage figure and explain that the estate could not be sufficiently observed (permissions/scope), and that the percentage is not representative. This prevents a low-coverage run from reporting a flattering score. (Note: check 8.5 — runbooks/on-call/PIR — is UNKNOWN *by design*, so it always contributes to the UNKNOWN count; factor that in when judging the 25% threshold.)

## Cross-domain duplicate checks (score once)

Some best practices are visible from two domains. To avoid inflating the maturity denominator by counting one control twice, each is scored in **exactly one** section and cross-referenced (not re-rated) from the other:

| Control | Scored in | Referenced (not scored) from |
|---|---|---|
| Container has no log driver / log routing / stream-prefix / delivery mode | **6.2** | 3.3 |
| Task-role least privilege, over-broad policy, execution-role-reused-as-task-role | **7.1** | 3.4 |
| Deployment-failure alerting (`SERVICE_DEPLOYMENT_FAILED`) | **4.5** | 6.4 |
| Fargate multi-AZ / replica resilience for task retirement | **8.4** | 04 / 05 |

When building the consolidated finding list, include each of these once, under its scoring section only.

## Consistency contract (MANDATORY — canonical)

**This section is the canonical statement of the consistency contract.** The "Consistency Checks" block in `report-generation.md` is an operational checklist that implements these rules; if the two ever appear to differ, this section wins.

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
