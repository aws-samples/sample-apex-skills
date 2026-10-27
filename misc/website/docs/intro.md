---
sidebar_position: 1
title: What is APEX
---

# What is APEX

**APEX** — *Agentic Platform Engineering eXperience* — is how we teach platform engineering through AI coding agents. It's a curated set of skills authored by AWS Solutions Architects, Technical Account Managers, and ProServe consultants, delivered through any agentic harness compatible with the [Agent Skills](https://agentskills.io/) open standard (Claude Code, Kiro CLI, and others).

Each skill is a self-contained folder of instructions, scripts, and references that a frontier LLM can discover and load on demand. Together they compress onboarding from months to weeks by giving engineers expert-grade output for the decisions they're already making.

## What's in this repo

| Directory   | Purpose                                                              |
| ----------- | -------------------------------------------------------------------- |
| `skills/`   | Reusable domain knowledge (the agent's brain)                        |
| `skills/apex/` | The APEX router skill and its runbooks: phased procedures that combine skills (the SA's playbook) |
| `rules/`    | Project-level agent rules — verification, source-checking, guardrails |
| `examples/` | Hands-on labs to try APEX against real workloads                     |
| `misc/`     | Maintenance scripts, evaluations, and this docs site                 |

> **Key principle:** Skills provide the knowledge. Runbooks provide the structure. Rules provide the guardrails.

## Where to go next

- [Getting Started](./getting-started) — install APEX in Claude Code or Kiro CLI.
- [Skills](./skills) — browse the catalog.
- [APEX router](./skills/general/apex): routes a request to the right skill and holds the runbooks, phased procedures that combine skills.
- [Contributing](./contributing) — add or improve a skill.
