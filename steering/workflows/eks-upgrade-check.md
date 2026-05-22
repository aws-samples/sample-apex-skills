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

The output is an assessment report — the user decides what to do with the findings.

Why: Readiness assessment is a discovery activity. Mutations belong to whatever upgrade-execution path the user chooses, where they review and approve a specific plan.

---

## Routing

There is one mode for this workflow: **run the full assessment**.

1. Activate the `eks-upgrade-check` skill
2. The skill discovers clusters, asks which to assess and what target version, and runs the 8-step assessment
3. The skill produces a markdown report and (optionally) converts it to HTML
4. Present the report and a one-paragraph summary highlighting blockers (if any) and the overall readiness rating

Do **not** re-implement the assessment in this workflow — the skill owns the procedure.

---

## After the Assessment

When the report is complete:

- **Score ≥ 80 (READY / GOOD):** Summarize the cluster as ready to proceed. Forward the cluster name, current version, target version, and any noted findings as shared context for whatever upgrade-execution path the user chooses next.
- **Score 60–79 (FAIR / RISKY):** Present the prioritized remediation list. Recommend resolving the top blockers and re-running the assessment.
- **Score < 60 (NOT READY):** Hard blockers exist. Walk the user through the blocker section. Recommend not proceeding with an upgrade until the blockers are resolved.

For full scoring rules and the hard-blocker list, see [eks-upgrade-check SKILL.md](../../skills/eks-upgrade-check/SKILL.md#readiness-score).

---

## EKS MCP Server (optional)

This skill works without MCP — it falls back to AWS CLI and `kubectl` for all checks. If the user wants richer EKS reads (e.g., `get_eks_insights`, `list_k8s_resources`), point them at the `eks-mcp-server` skill for setup. Apex does not ship a project-root `.mcp.json`; MCP is opt-in.

---

## Skills Reference

- **Primary:** `eks-upgrade-check` — owns the 8-step assessment, scoring, and report generation
- **Optional:** `eks-mcp-server` — guides MCP setup if the user wants richer cluster reads
