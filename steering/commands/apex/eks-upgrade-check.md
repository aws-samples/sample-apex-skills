---
name: apex:eks-upgrade-check
description: Assess EKS cluster upgrade readiness — automated checks across 8 areas (version, breaking changes, deprecated APIs, add-on compatibility, node readiness, workload risks, AWS Insights, upgrade plan), a 0-100 readiness score, and a markdown/HTML report with prioritized remediation. Use for upgrade-readiness assessments before running an actual upgrade.
---
<objective>
Run the APEX EKS upgrade-readiness assessment — a structured, read-only evaluation of whether a live cluster is ready to upgrade to its next minor version.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/eks-upgrade-check.md
</execution_context>

<process>
Follow the eks-upgrade-check workflow. Hand off to the `eks-upgrade-check` skill for the 8-step assessment, scoring, and report generation. The skill is self-contained — the workflow's job is to set the access model and route to the skill.
</process>
