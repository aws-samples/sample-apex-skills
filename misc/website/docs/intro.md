---
sidebar_position: 1
title: What is APEX
---

# What is APEX

**APEX** — *Agentic Platform Engineering eXperience* — is a curated set of EKS platform-engineering skills, authored by senior AWS Solutions Architects and delivered through agentic AI coding agents (Claude Code, Kiro CLI, and any harness compatible with the [Agent Skills](https://agentskills.io/) open standard).

Each skill is a self-contained folder of instructions, scripts, and references that an LLM can discover and load on demand. Together they compress EKS onboarding from months to weeks by giving engineers SSA-grade output for the decisions they're already making.

## What's in this repo

| Directory   | Purpose                                                              |
| ----------- | -------------------------------------------------------------------- |
| `skills/`   | Reusable domain knowledge (the agent's brain)                        |
| `steering/` | Phased engagement playbooks that combine skills (the SA's playbook)  |
| `examples/` | Hands-on labs to try APEX against real workloads                     |
| `misc/`     | Maintenance scripts, evaluations, and this docs site                 |

> **Key principle:** Skills provide the knowledge. Steering provides the structure.

## Where to go next

- [Getting Started](./getting-started.md) — install APEX in Claude Code or Kiro CLI.
- [Skills](./skills) — browse the catalog.
- [Steering](./steering) — phased workflows that combine multiple skills.
- [Contributing](./contributing.md) — add or improve a skill.
