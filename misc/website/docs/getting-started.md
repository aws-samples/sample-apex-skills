---
sidebar_position: 2
title: Getting Started
---

# Getting Started

APEX skills are plain folders of markdown + scripts. Any agent harness that supports the [Agent Skills](https://agentskills.io/) standard can load them.

## Quick Install (recommended)

> **Prerequisites:** [Node.js 18+](https://nodejs.org/) and [git](https://git-scm.com/) must be installed.

```bash
npx apex-skills
```

The installer detects which tools you have (Claude Code, Kiro CLI, or both), clones the repo to `~/.apex-skills/`, and symlinks all skills + steering workflows into the right locations. Run `npx apex-skills --update` later to pull the latest skills.

## Manual Install

### Claude Code

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills
mkdir -p ~/.claude/skills
cp -r skills/* ~/.claude/skills/
```

Restart Claude Code; the skills become available via `/<skill-name>`.

### Kiro CLI

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills
mkdir -p ~/.kiro/skills
cp -r skills/* ~/.kiro/skills/
```

## Verify

In your harness, run:

```
/eks-recon
```

You should see the EKS reconnaissance skill prompt for cluster context.

## Next steps

- Browse the [Skills](./skills) catalog.
- Try a [Steering](./steering) workflow for a phased engagement.
