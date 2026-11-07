---
title: "EKS Operation Review (eks-operation-review): rated audit of a live EKS cluster"
sidebar_label: "eks-operation-review"
description: "Structured EKS operational excellence assessment across 10 areas, GREEN/AMBER/RED rated, including deprecated-API review with no target version"
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-operation-review/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/SKILL.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [sample-eks-operation-review-skill](https://github.com/aws-samples/sample-eks-operation-review-skill), also maintained by the APEX team.
:::


# EKS Operation Review

This skill performs a structured 10-section operational assessment of a live EKS cluster, producing a rated report with prioritized recommendations.

## When to use

Activate for any request to audit, review, health-check, or score an EKS cluster's operational posture — including section-scoped reviews of individual areas (e.g., "check my EKS networking", "review RBAC on my cluster").

Not for: upgrade readiness assessment against a target version, cluster discovery, or architectural design advice (current-state add-on and deprecated-API review with no target belongs here, not with the upgrade skill). General Kubernetes questions, AWS troubleshooting, cluster creation, and one-off kubectl commands should be handled directly without this skill.

## Instructions

Read and follow `../apex/runbooks/eks-operation-review/eks-operation-review.md` (relative to this skill's folder) — it contains the full workflow, tool usage rules, and steering file map. Load each steering file from `references/` before running its corresponding section.

## Prerequisites

- AWS credentials with EKS read access
- Python 3.10+ and uv installed
- kubectl installed — required for check 3.1's name-only credential scan; pre-flight configures its kubeconfig via `aws eks update-kubeconfig`
- EKS MCP server configured (see the `eks-mcp-server` skill for setup); apex does not ship a project-root `.mcp.json`
