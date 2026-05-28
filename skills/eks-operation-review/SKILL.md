---
name: eks-operation-review
description: Run a structured EKS operational excellence assessment against a live cluster. Only activate when the user explicitly requests an EKS operational review, EKS health check, EKS audit, or EKS assessment. Do NOT activate for general Kubernetes questions, AWS troubleshooting, EKS setup/creation, or ad-hoc kubectl commands.
---

# EKS Operation Review

This skill performs a structured 10-section operational assessment of a live EKS cluster, producing a rated report with prioritized recommendations.

## When to use

Activate ONLY when the user explicitly asks for one of:
- An EKS operational review / assessment / audit / health check
- A specific section review (e.g., "check my EKS networking", "review RBAC on my cluster")

Do NOT activate for:
- General Kubernetes or EKS questions ("how do I create a node group?")
- AWS troubleshooting ("my pods can't pull images")
- Cluster creation or setup
- One-off kubectl commands or resource lookups

## Instructions

Read and follow `~/.claude/apex-steering/workflows/eks-operation-review.md` — it contains the full workflow, tool usage rules, and steering file map. Load each steering file from `references/` before running its corresponding section.

## Prerequisites

- AWS credentials with EKS read access
- Python 3.10+ and uv installed
- EKS MCP server configured (see the `eks-mcp-server` skill for setup); apex does not ship a project-root `.mcp.json`
