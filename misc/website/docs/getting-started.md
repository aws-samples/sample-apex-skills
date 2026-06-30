---
sidebar_position: 2
title: Getting Started
---

# Getting Started

:::warning Disclaimer
This project provides sample code for **educational and demonstration purposes only**. It is not intended for direct production use without proper review, testing, and validation. Always test generated infrastructure artifacts (Terraform, Helm charts, kubectl commands) in non-production environments first. Use at your own risk — the authors are not responsible for any issues, damages, or losses that may result from using this code in production.
:::

APEX skills are plain folders of markdown + scripts. Any agent harness that supports the [Agent Skills](https://agentskills.io/) standard can load them.

## NPX Installer (recommended)

> **Prerequisites:** [Node.js 18+](https://nodejs.org/) and [git](https://git-scm.com/) must be installed.

```bash
npx apex-skills
```

The installer detects which tools you have (Claude Code, Kiro CLI, or both), clones the repo to `~/.apex-skills/`, and symlinks all skills + steering workflows into the right locations.

```bash
npx apex-skills --update              # Pull latest skills
npx apex-skills --version v1.2.0      # Pin to a specific release
npx apex-skills --branch feat/new-eks # Install from a branch
npx apex-skills --help                # See all options
```

## Manual Install

If you prefer not to use npx, clone the repo and copy skills directly.

### Claude Code

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills

mkdir -p ~/.claude/skills ~/.claude/commands
cp -r skills/* ~/.claude/skills/
ln -sfn "$(pwd)/steering/commands/apex" ~/.claude/commands/apex
ln -sfn "$(pwd)/steering" ~/.claude/apex-steering
```

Restart Claude Code; skills become available via `/<skill-name>` and steering via `/apex:*`.

### Kiro CLI

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills

mkdir -p ~/.kiro/skills ~/.kiro/steering
cp -r skills/* ~/.kiro/skills/
cp steering/workflows/*.md ~/.kiro/steering/
```

### Other Agent Harnesses

Skills follow the [Agent Skills](https://agentskills.io/) standard. Clone and point your tool at `skills/{skill-name}/` — each contains a `SKILL.md` and optional `references/` directory.

## Verify

In your harness, run:

```
/eks-recon
```

You should see the EKS reconnaissance skill prompt for cluster context.

## Add Agent Rules (recommended)

We provide a [`rules/AGENTS.md`](https://github.com/aws-samples/sample-apex-skills/tree/main/rules) file with recommended rules for agents using APEX skills — skill discovery, upstream source verification, and safety guardrails.

Add the contents to your project's existing agent configuration:

| Tool | Where to add |
|------|-------------|
| Claude Code | Append to your project's `CLAUDE.md` |
| Cursor | Add to `.cursor/rules/apex.mdc` |
| Codex | Append to your project's `AGENTS.md` |
| Kiro | Add to `.kiro/steering/apex-rules.md` |
| Gemini CLI | Append to your project's `GEMINI.md` |

See [`rules/AGENTS.md`](https://github.com/aws-samples/sample-apex-skills/blob/main/rules/AGENTS.md) for the full content.

## Next steps

- Browse the [Skills](./skills) catalog.
- Try a [Steering](./steering) workflow for a phased engagement.
