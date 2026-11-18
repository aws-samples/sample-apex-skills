---
sidebar_position: 1
title: What is APEX
description: "What APEX is: curated AWS platform engineering skills for AI coding agents, written by AWS experts, and what this repo holds."
---

# What is APEX

**APEX** — *Agentic Platform Engineering eXperience* — is how we teach platform engineering through AI coding agents. It's a curated set of skills authored by AWS Solutions Architects, Technical Account Managers, and ProServe consultants, delivered through any agentic harness compatible with the [Agent Skills](https://agentskills.io/) open standard (Claude Code, Kiro CLI, and others).

Each skill is a self-contained folder of instructions, scripts, and references that a frontier LLM can discover and load on demand. Together they compress onboarding from months to weeks by giving engineers expert-grade output for the decisions they're already making.

## What's in this repo

| Directory   | Purpose                                                              |
| ----------- | -------------------------------------------------------------------- |
| `skills/`   | Reusable domain knowledge (the agent's brain)                        |
| `skills/apex/` | The APEX router skill, its per-skill runbooks until each skill's rebuild, and your runbooks: your own procedures that chain skills |
| `classes/`  | The shared rules; the class sync copies them into each member skill |
| `examples/` | Hands-on labs to try APEX against real workloads                     |
| `misc/`     | Maintenance scripts, evaluations, and this docs site                 |

> **Key principle:** Skills provide the knowledge. Runbooks chain skills into your own procedures. Classes provide the guardrails.

## Where to go next

- [Getting Started](./getting-started.md) — install APEX in Claude Code or Kiro CLI.
- [Skills](./skills/index.md) — browse the catalog.
- [APEX router](./skills/general/apex/index.md): routes a request to the right skill and follows your runbooks, your own procedures that chain skills.
- [Contributing](./contributing/index.md) — add or improve a skill.
