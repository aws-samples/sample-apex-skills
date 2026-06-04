---
title: Workshop
sidebar_position: 5
---

# Agentic Platform Engineering Experience

A hands-on workshop where participants use Claude Code with purpose-built agent skills to design, build, and operate Amazon EKS clusters. An adaptive AI tutor personalizes the experience — participants choose their own adventure across architecture design, Terraform generation, upgrade readiness checks, operational reviews, or building custom skills for their own use cases. No two participants follow the same path.

Everything is open source and reusable in your own AWS account.

| | |
|---|---|
| **Level** | 300 |
| **Duration** | 2 hours |
| **Topics** | Containers, Generative AI |
| **AWS Services** | Amazon Bedrock, Amazon EKS |
| **Engagement model** | Immersion Day |

**[Launch Workshop →](https://catalog.us-east-1.prod.workshops.aws/workshops/7ff87bbb-e472-4517-85f9-fb1d451acec1)**

## Three scenarios

### Day 0 — Architect

Design an EKS platform architecture with AI-guided decision making. Describe your requirements conversationally and receive architecture decision records, compute selection guidance, and security recommendations.

**Skills activated:** eks-best-practices, eks-design

### Day 1 — Build

Transform architecture decisions into Terraform modules. Deploy an EKS cluster with Karpenter, GitOps tooling, and platform add-ons — all generated and validated by the agent.

**Skills activated:** eks-build, terraform-skill, eks-best-practices

### Day 2 — Operate

Troubleshoot operational issues, perform cost optimization, and execute cluster upgrades with pre-flight validation. The agent acts as a senior SA co-pilot.

**Skills activated:** eks-upgrade-check, eks-operation-review, eks-recon

## Workshop flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        APEX Workshop                            │
├─────────────────┬─────────────────┬─────────────────────────────┤
│    Day 0        │    Day 1        │         Day 2               │
│   ARCHITECT     │    BUILD        │        OPERATE              │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ • Requirements  │ • IaC Gen       │ • Troubleshooting           │
│ • Decisions     │ • Deploy        │ • Cost Optimization         │
│ • ADR Output    │ • Validate      │ • Upgrade Planning          │
├─────────────────┴─────────────────┴─────────────────────────────┤
│           Skills: eks-best-practices + terraform-skill          │
├─────────────────────────────────────────────────────────────────┤
│        Agent Harness: Claude Code / Kiro CLI + Bedrock          │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- AWS account with EKS permissions (or Workshop Studio-provided account)
- Claude Code or Kiro CLI installed and configured
- Basic familiarity with Kubernetes concepts
- No prior Terraform experience required (agent-assisted)

## What you take home

- Hands-on experience deploying a real EKS platform with AI assistance
- Understanding of how curated skills encode best practices
- Direct experience with agentic AI workflows on Amazon Bedrock
- Reusable Terraform modules and operational runbooks
