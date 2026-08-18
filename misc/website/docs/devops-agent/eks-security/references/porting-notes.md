---
title: "Porting Notes — eks-security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/porting-notes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-security/references/porting-notes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/porting-notes.md). Edit the source, not this page.
:::

# Porting Notes — eks-security

This file documents the differences between the Claude Code version and the DevOps Agent port. It is for maintainers, not for the agent to read during execution.

> **Staleness check:** the table below describes the upstream skill at a point in time and can drift as `skills/eks-security/` evolves. Re-verify each row against upstream when materially changing either copy, and update the date here. Last verified: 2026-08-18 (compliance references re-verified; other rows carried forward unchanged from 2026-07-17).

## Differences from Claude Code Version

| Aspect | Claude Code version | DevOps Agent version |
|--------|--------------------|--------------------|
| **Execution model** | Interactive — asks 8 discovery questions conversationally | Autonomous with HARD STOP gates — proceeds if context is sufficient, stops only for critical missing items |
| **Discovery** | 8 interactive questions before any recommendation | 3 mandatory context gates (compliance regime, workload sensitivity, OS/AMI preference); 5 additional context items gathered opportunistically |
| **Tool access** | Uses Bash, kubectl, AWS CLI via MCP server for live cluster inspection | Uses AWS APIs and Kubernetes APIs available in the Agent Space (read-only) |
| **Escalation** | References internal SpecReq / Specialist processes | Recommends engaging AWS Professional Services or Solutions Architects |
| **Skill routing** | Routes to sibling skills (`eks-genai`, `eks-build`, `eks-design`) | Self-contained; notes alternative guidance domains without routing |
| **Script execution** | Can run kube-bench, generate shell commands | Advisory only — recommends commands for the user to execute |
| **MCP dependencies** | References eks-mcp-server for live data | No MCP dependencies; uses Agent Space APIs directly |
| **Auto Mode security reference** | `references/auto-mode-security.md` — security facts (node OS, IMDSv2, shared-responsibility split) | Identical / in sync; security facts are launch-agnostic, only execution-model framing differs — edit both copies together. |
| **Compliance references** | 3 per-regime deep files (`compliance-hipaa/pci/soc2.md`), each with a control-mapping table + 30/60/90 + shared-responsibility table, **plus** router bullets + worked scenarios in `compliance-regimes.md` | **Only `compliance-regimes.md`** — the same compact per-regime bullets + worked scenarios, **no deep files** (and no per-regime control-mapping / 30-60-90 / shared-responsibility tables). The per-regime *bullets* are at parity with the skill's (same facts, incl. PCI Req 3/4 + segmentation 11.4.5/11.4.6); the port simply carries **less depth**. Keep the compliance *facts* in sync with the skill; the port intentionally omits the deep files (self-contained, no deep-dive links). |
