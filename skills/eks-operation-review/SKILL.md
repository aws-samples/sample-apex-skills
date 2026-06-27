---
name: eks-operation-review
description: Run a structured EKS operational excellence assessment against a live cluster. Covers 10 areas — networking, autoscaling, observability, access & identity, add-ons, workload config, deployments, cluster lifecycle, IaC, operational processes — and produces a GREEN/AMBER/RED rated report with prioritized recommendations. Activate for any request to audit, review, health-check, or score an EKS cluster's operational posture, including section-scoped reviews of individual areas. Not for upgrade readiness, cluster discovery, or architectural design advice.
---

# EKS Operation Review

This skill performs a structured 10-section operational assessment of a live EKS cluster, producing a rated report with prioritized recommendations.

## When to use

Activate for any request to audit, review, health-check, or score an EKS cluster's operational posture — including section-scoped reviews of individual areas (e.g., "check my EKS networking", "review RBAC on my cluster").

Not for: upgrade readiness assessments, cluster discovery, or architectural design advice. General Kubernetes questions, AWS troubleshooting, cluster creation, and one-off kubectl commands should be handled directly without this skill.

## Instructions

Read and follow `~/.claude/apex-steering/workflows/eks-operation-review.md` — it contains the full workflow, tool usage rules, and steering file map. Load each steering file from `references/` before running its corresponding section.

## Prerequisites

- AWS credentials with EKS read access
- Python 3.10+ and uv installed
- EKS MCP server configured (see the `eks-mcp-server` skill for setup); apex does not ship a project-root `.mcp.json`
