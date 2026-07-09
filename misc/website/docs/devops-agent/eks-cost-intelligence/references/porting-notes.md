---
title: "Porting Notes — eks-cost-intelligence"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/references/porting-notes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-cost-intelligence/references/porting-notes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/references/porting-notes.md). Edit the source, not this page.
:::

# Porting Notes — eks-cost-intelligence

This file documents the differences between the Claude Code version and the DevOps Agent port. It is for maintainers, not for the agent to read during execution.

## Differences from Claude Code Version

| Aspect | Claude Code (`skills/eks-cost-intelligence/`) | DevOps Agent (this skill) |
|--------|-----------------------------------------------|---------------------------|
| Execution model | Interactive — asks user to confirm cluster, waits for responses | Fully autonomous — hard-stop decision tables, no interactive prompts |
| Tool access | `aws` CLI, `kubectl`, optional MCP server | AWS APIs and Kubernetes APIs available in Agent Space |
| Report generation | Markdown + optional HTML via `tools/report_to_html.py` | Markdown only, generated directly |
| MCP configuration | Local `.mcp.json` with `eks-mcp-server` skill for setup | Configured at Agent Space level (no setup instructions needed) |
| Reference file paths | `skills/eks-cost-intelligence/references/` | `references/` (relative to skill root) |
| Script dependencies | Python script for HTML conversion | None — no scripts permitted |
| Cluster selection | Shows list, asks user to choose | Auto-selects single cluster; HARD STOP on ambiguity |
