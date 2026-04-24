---
name: eks-mcp-server
description: Setup and configure the EKS MCP Server for live cluster operations. Use this skill when the user wants to interact with real EKS clusters (list clusters, read K8s resources, troubleshoot pods, deploy workloads, check upgrade insights) but MCP tools are not available or not working. Also activate if user mentions "eks mcp", "mcp server", or asks how to connect their AI assistant to EKS.
license: Apache-2.0
---

# EKS MCP Server Setup

This skill helps you configure the EKS MCP Server to enable live EKS cluster operations through your AI assistant.

**Don't use this skill for:**
- Operational cluster work (listing resources, troubleshooting pods, reading K8s state) — use the EKS MCP tools directly once configured, or the `eks-recon` skill for discovery context
- EKS concept questions (architecture, best practices, upgrade planning) — use `eks-best-practices`, `eks-upgrader`, or `eks-recon`

## Quick Check: Is EKS MCP Already Configured?

Before proceeding with setup, check if EKS MCP tools are already available:

1. **Look for MCP tools** in your current environment starting with `eks` or `mcp__eks`
2. **Try a simple command**: Ask to list EKS clusters — if it works, you're already set up

If MCP tools are available and working, **skip this skill** and proceed with your EKS task directly.

## Choose Your Setup Option

| Option | Best For | Maintenance | AWS Account Required |
|--------|----------|-------------|---------------------|
| **AWS-Hosted (Managed)** | Production, teams, minimal ops | AWS manages everything | Yes |
| **Self-Hosted (Open Source)** | Air-gapped, custom auth, OIDC | You manage updates | Optional (kubeconfig mode) |

### Decision Guide

- **Choose AWS-Hosted if:** You have AWS credentials, want zero maintenance, need CloudTrail audit logging
- **Choose Self-Hosted if:** You need OIDC/kubeconfig auth, air-gapped environment, or want to run locally without AWS IAM

## Setup Instructions

Setup instructions are in separate reference files to avoid loading unnecessary content:

- **AWS-Hosted setup**: See [references/aws-hosted-setup.md](references/aws-hosted-setup.md)
- **Self-Hosted setup**: See [references/self-hosted-setup.md](references/self-hosted-setup.md)

Read the appropriate reference file based on the user's chosen option, then guide them through configuration.

## After Setup

Once the MCP server is configured:

1. **Restart your AI assistant** (IDE, CLI, or extension) to load the new MCP tools
2. **Verify connection**: Ask to list EKS clusters or available MCP tools
3. **Start using EKS tools**: The MCP server provides tools for cluster management, K8s resources, troubleshooting, and observability

This skill's job is done once setup is complete. Hand off to the EKS MCP tools for actual cluster operations.
