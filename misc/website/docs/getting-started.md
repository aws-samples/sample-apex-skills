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
npx apex-skills@1.3.0
```

APEX v2 is in progress, so the commands here pin the installer to exactly version 1.3.0 until v2 ships, which also skips later 1.3.x installer releases. A fresh install with no earlier install record takes the newest v1.x.y release of the skills; `--version` picks a release, `--branch` follows a branch, and `--update` stays on the clone's major line or the branch it follows.

On a tree without steering/ (any v2 branch, and `main` once v2 merges), installer 1.3.0 still asks about steering, prints `No steering commands found in repo` and `No steering workflows found in repo`, and for Kiro CLI suggests `/eks-build`; ignore these, the skills, `apex` included, install correctly.

The installer's own messages show `npx apex-skills`; add `@1.3.0` when you run them.

Until v2 ships, a v1 release has the `/apex:*` commands and no `apex` skill or runbooks; for `/apex`, run `npx apex-skills@1.3.0 --branch main` or use the Manual Install below (both from `main`).

Detects Claude Code and/or Kiro CLI, clones the repo to `~/.apex-skills/`, and links the skills into place. Flags, exit codes, [installed paths](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md#installed-paths) and [uninstall](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md#uninstall): see the [installer README](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md).

Before upgrading from installer 1.2.0 or earlier, and before re-running after moving or renaming a home or project directory, copy out edited Kiro steering copies and remove or note links of your own into `~/.apex-skills`: with no install record the installer cannot tell them from its own.

```bash
npx apex-skills@1.3.0 --update              # Update an existing install
npx apex-skills@1.3.0 --version v1.2.0      # Installer 1.3.0, skills release v1.2.0
npx apex-skills@1.3.0 --branch feat/new-eks # Install from a branch
npx apex-skills@1.3.0 --help                # See all options
```

## Manual Install

If you prefer not to use npx, clone the repo and copy skills directly.

If you installed v1 with npx, run `npx apex-skills@1.3.0 --uninstall` first (or install with `npx apex-skills@1.3.0 --branch main` instead): `cp` cannot overwrite the links the npx install made and exits with an error.

**Upgrading a v1 manual install:** remove `~/.claude/commands/apex` and `~/.claude/apex-steering` (links into `steering/`, which v2 removes) and the eight APEX workflow files you copied into `~/.kiro/steering/` (design.md, eks-build.md, eks-genai.md, eks-operation-review.md, eks-platform-engineering.md, eks-security.md, eks-upgrade-check.md and new-skill.md; `grep -l 'APEX EKS Hub\|APEX Meta Hub' ~/.kiro/steering/*.md` lists them); the `/apex:<name>` commands are replaced by `/apex`, except `/apex:new-skill`, which is removed (for a new skill, follow [CONTRIBUTING.md](https://github.com/aws-samples/sample-apex-skills/blob/main/CONTRIBUTING.md#creating-a-new-skill), Creating a New Skill). `cp -r` does not remove the retired skill: also `rm -rf ~/.claude/skills/steering-workflow-creator ~/.kiro/skills/steering-workflow-creator`.

### Claude Code

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills

mkdir -p ~/.claude/skills
cp -r skills/* ~/.claude/skills/
```

Restart Claude Code; skills become available via `/<skill-name>`. With this manual install (from `main`), start with `/apex`: it routes your request to the right skill.

### Kiro CLI

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills

mkdir -p ~/.kiro/skills
cp -r skills/* ~/.kiro/skills/
```

**Usage:** in Kiro, type `/apex` with your request, or ask for apex by name, for example *"use apex to plan my EKS upgrade"*. Tested on Kiro CLI 2.35.1 (2026-10-28); Kiro CLI 1.27.0 rejected `/apex`.

### Codex

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
cd sample-apex-skills

mkdir -p ~/.agents/skills
cp -r skills/* ~/.agents/skills/
```

**Usage:** in Codex, type `$apex` with your request, for example *"$apex plan my EKS upgrade"*. Codex reads skills from `~/.agents/skills` (and a repository's `.agents/skills`); the installer does not set up Codex.

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

Claude Code (v2.1.277 or later; v2.1.281 or later in some sessions, such as on Amazon Bedrock or with telemetry disabled), Codex and Kiro also read a root `AGENTS.md`: you can append these rules there. Claude Code reads `AGENTS.md` only when no `CLAUDE.md` is in the working directory or above, so if you have a `CLAUDE.md`, append there or import with `@AGENTS.md`.

See [`rules/AGENTS.md`](https://github.com/aws-samples/sample-apex-skills/blob/main/rules/AGENTS.md) for the full content.

## Next steps

- Browse the [Skills](./skills) catalog.
- With a manual install from `main`, start with the [APEX router](./skills/general/apex) skill for a phased engagement: it routes to the right skill and its runbook.
