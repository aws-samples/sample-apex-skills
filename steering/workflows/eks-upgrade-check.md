---
name: eks-upgrade-check
description: Day 2 upgrade-readiness assessment workflow. Runs the eks-upgrade-check skill end-to-end — 8 automated checks, 0-100 readiness score, markdown/HTML report with remediation steps.
---

# Upgrade-Readiness Assessment Workflow

> **Part of:** [APEX EKS Hub](../eks.md)
> **Lifecycle:** Day 2 — Operate (pre-upgrade)
> **Skill:** `eks-upgrade-check` — [SKILL.md](../../skills/eks-upgrade-check/SKILL.md)

---

## Access Model

This workflow is **read-only**:

- **CAN** run read-only commands (`aws eks describe-*`, `kubectl get`, `helm list`) to discover cluster state
- **CAN** generate a markdown/HTML readiness report
- **CANNOT** mutate cluster state (no upgrades, applies, deletes, annotations)

The output is an assessment report — the user decides what to do with it. They typically pair this with `/apex:eks-upgrade` to plan and execute the actual upgrade.

Why: Readiness assessment is a discovery activity. Mutations belong in the upgrade workflow itself, where the user has reviewed and approved a specific plan.

---

## How This Differs From `/apex:eks-upgrade`

| | `/apex:eks-upgrade-check` | `/apex:eks-upgrade` |
|---|---|---|
| **Goal** | Decide *whether* to upgrade | Plan and guide *how* to upgrade |
| **Output** | Readiness report (0-100 score, blockers, remediation) | Upgrade plan + step-by-step companion |
| **Scope** | One assessment, one report | Full lifecycle — pre-flight, plan, execute, validate |
| **Mutations** | None | None during planning; user runs the upgrade |
| **Typical sequence** | Run first to surface blockers | Run after blockers resolved |

If a user asks *"is my cluster ready to upgrade?"* — route here. If they ask *"upgrade my cluster"* or *"give me an upgrade plan"* — route to `/apex:eks-upgrade`.

---

## Routing

There is one mode for this workflow: **run the full assessment**.

1. Activate the `eks-upgrade-check` skill
2. The skill discovers clusters, asks which to assess and what target version, and runs the 8-step assessment
3. The skill produces a markdown report and (optionally) converts it to HTML
4. Present the report and a one-paragraph summary; suggest `/apex:eks-upgrade` as the next step if blockers are clear

Do **not** re-implement the assessment in this workflow — the skill owns the procedure.

---

## After the Assessment

When the report is complete:

- **Score ≥ 80 (READY / GOOD):** Suggest the user proceed to `/apex:eks-upgrade` to plan the upgrade. Forward the cluster name, current version, target version, and any noted findings as shared context.
- **Score 60–79 (FAIR / RISKY):** Present the prioritized remediation list. Recommend resolving the top blockers and re-running the assessment.
- **Score < 60 (NOT READY):** Hard blockers exist. Walk the user through the blocker section. Do not route to `/apex:eks-upgrade` until the blockers are resolved.

For full scoring rules and the hard-blocker list, see [eks-upgrade-check SKILL.md](../../skills/eks-upgrade-check/SKILL.md#readiness-score).

---

## EKS MCP Server (optional)

This skill works without MCP — it falls back to AWS CLI and `kubectl` for all checks. If the user wants richer EKS reads (e.g., `get_eks_insights`, `list_k8s_resources`), point them at the `eks-mcp-server` skill for setup. Apex does not ship a project-root `.mcp.json`; MCP is opt-in.

---

## Skills Reference

- **Primary:** `eks-upgrade-check` — owns the 8-step assessment, scoring, and report generation
- **Optional:** `eks-mcp-server` — guides MCP setup if the user wants richer cluster reads
- **Adjacent:** `eks-upgrader` — used by `/apex:eks-upgrade` to plan and execute the actual upgrade after assessment
