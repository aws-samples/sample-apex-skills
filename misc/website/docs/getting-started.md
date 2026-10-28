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

Detects Claude Code and/or Kiro CLI, clones the repo to `~/.apex-skills/`, and links the skills into place. Flags, exit codes, [installed paths](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md#installed-paths) and [uninstall](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md#uninstall): see the [installer README](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md).

Before upgrading from installer 1.2.0 or earlier, and before re-running after moving or renaming a home or project directory, copy out edited Kiro steering copies and remove or note links of your own into `~/.apex-skills`: with no install record the installer cannot tell them from its own.

```bash
npx apex-skills --update              # Update an existing install
npx apex-skills --version v1.2.0      # Pin to a release
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

Files copied this way load into every Kiro interaction; add `inclusion: manual` frontmatter or use `npx apex-skills`.

### Other Agent Harnesses

Skills follow the [Agent Skills](https://agentskills.io/) standard. Clone and point your tool at `skills/{skill-name}/` — each contains a `SKILL.md` and optional `references/` directory.

### AWS DevOps Agent

A subset of skills are ported for fully autonomous execution on the [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/). These live in the `devops-agent/` directory and run without interactive prompts.

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills

# Automated setup (creates Agent Space, uploads skills, configures EKS access)
./devops-agent/setup.sh --space-name <your-space> --cluster-name <your-cluster> --region <region>

# Or upload a single skill manually
cd devops-agent/eks-cost-intelligence
zip -r /tmp/eks-cost-intelligence.zip . -x '*.zip' -x './references/porting-notes.md'
# Upload in the Agent Space Operator Web App: Knowledge > Skills > Add skill > Upload skill
```

See [`devops-agent/README.md`](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/README.md) for full setup instructions and constraints.

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

Claude Code (v2.1.277 or later), Codex and Kiro also read a root `AGENTS.md`: you can append these rules there. Claude Code reads `AGENTS.md` only when no `CLAUDE.md` is in the working directory or above, so if you have a `CLAUDE.md`, append there or import with `@AGENTS.md`.

See [`rules/AGENTS.md`](https://github.com/aws-samples/sample-apex-skills/blob/main/rules/AGENTS.md) for the full content.

## Next steps

- Browse the [Skills](./skills) catalog.
- Try a [Steering](./steering) workflow for a phased engagement.
