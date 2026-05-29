---
title: "apex:eks-operation-review"
description: "Run a structured EKS operational excellence assessment — 10-section review (cluster lifecycle, IaC/GitOps, access/identity, observability, workload config, networking, autoscaling, deployment practices, ops processes, add-on management) producing a rated report with GREEN/AMBER/RED findings and prioritized actions. Use when someone asks \"run an EKS operational review\", \"audit my cluster\", \"EKS health check\", \"review my EKS posture\", or asks for a section-scoped review (networking, RBAC, observability, etc.)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/steering/commands/apex/eks-operation-review.md
format: md
---

:::info[Source]
This page is generated from [steering/commands/apex/eks-operation-review.md](https://github.com/aws-samples/sample-apex-skills/blob/main/steering/commands/apex/eks-operation-review.md). Edit the source, not this page.
:::

<objective>
Run the APEX EKS operational-review workflow — a structured, MCP-backed evaluation of a live cluster's operational excellence across 10 areas, producing a markdown/HTML report with consistent ratings and prioritized recommendations.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/eks-operation-review.md
</execution_context>

<process>
Follow the eks-operation-review workflow. Hand off to the `eks-operation-review` skill for the 10-section assessment, rating logic, and report generation. The skill is self-contained — the workflow's job is to set the access model, route to the skill, and document the MCP setup story.
</process>
