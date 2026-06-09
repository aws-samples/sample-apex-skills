---
name: eks-mcp-server
description: Install, configure, and troubleshoot the EKS MCP Server connection in your AI assistant (Claude Code, Amazon Q CLI, Cursor, Kiro). Use ONLY for MCP server setup problems — config file location (.mcp.json), IAM permissions for eks-mcp actions, uvx installation, choosing AWS-hosted vs self-hosted mode, or debugging why MCP tools fail to appear after config. Also activate if user mentions "eks mcp", "mcp server", "mcp.json", or "mcp tools not showing". Do NOT use for actual cluster operations once MCP is working — those go to eks-recon (discovery), eks-operation-review (audits), or eks-upgrade-check (upgrades).
---

# EKS MCP Server Setup

This skill guides you through configuring the EKS MCP Server to enable live EKS cluster operations through your AI assistant.

## When NOT to Use This Skill

- Operational cluster work (listing resources, troubleshooting pods, reading K8s state) — use the EKS MCP tools directly once configured
- EKS concept questions — use the other EKS skills

---

## Setup Workflow

### Step 0: Quick Check — Is EKS MCP Already Configured?

Before proceeding with setup, check if EKS MCP tools are already available:

1. Look for MCP tools in your current environment starting with `eks` or `mcp__eks`
2. Try a simple command: Ask to list EKS clusters — if it works, you're already set up

If MCP tools are available and working, **stop here** — skip this skill and proceed with your EKS task directly.

---

### Step 1: Hosting Mode

Ask the user:

> **Which hosting mode do you want?**
>
> 1. **AWS-Hosted (Managed)** — fully managed by AWS, zero local maintenance, requires AWS credentials and IAM permissions, CloudTrail audit logging included
> 2. **Self-Hosted (Open Source)** — runs locally via `uvx`, supports kubeconfig/OIDC auth, works in air-gapped environments, you manage updates
>
> *Choose AWS-Hosted if you have AWS credentials and want the simplest setup. Choose Self-Hosted if you need OIDC/kubeconfig auth, air-gapped support, or want to run without AWS IAM.*

Wait for the user's answer before proceeding.

---

### Step 2: Access Level

Ask the user:

> **What access level do you need?**
>
> 1. **Read-only** — list clusters, describe resources, view logs, read K8s state. Cannot create, modify, or delete anything. Recommended to start.
> 2. **Full access** — everything in read-only plus create/update/delete operations on K8s resources, CloudFormation stacks, and IAM policies.
>
> *Start with read-only if you're unsure. You can upgrade later by changing one flag.*

Wait for the user's answer before proceeding.

---

### Step 3: AI Assistant

Ask the user:

> **Which AI assistant are you configuring?**
>
> 1. **Claude Code** — `.mcp.json` (project-scope, shareable) or `~/.claude.json` (user-scope)
> 2. **Amazon Q Developer CLI** — `~/.aws/amazonq/mcp.json`
> 3. **Cursor IDE** — Settings → Cursor Settings → Tools & MCP → New MCP Server
> 4. **Kiro IDE** — `~/.kiro/settings/mcp.json` or `.kiro/settings/mcp.json`
> 5. **VS Code (Cline Extension)** — Cmd/Ctrl+Shift+P → "MCP" → Add Server → Open User Configuration

Wait for the user's answer before proceeding.

---

### Step 4: Region & Profile

Ask the user:

> **Which AWS region are your EKS clusters in?** (e.g., `us-west-2`, `eu-west-1`)
>
> **Optional:** Do you use a named AWS profile? If so, which one? (default: `default`)

Wait for the user's answer before proceeding.

---

### Step 5: Configure

Based on the answers from Steps 1–4, read the appropriate reference file and generate the exact configuration:

| Hosting mode | Reference file |
|---|---|
| AWS-Hosted | `${CLAUDE_SKILL_DIR}/references/aws-hosted-setup.md` |
| Self-Hosted | `${CLAUDE_SKILL_DIR}/references/self-hosted-setup.md` |

After reading the reference file:

1. Generate the complete JSON config block tailored to the user's choices (hosting mode, access level, region, profile, assistant)
2. Show the user exactly where to paste it (file path or UI location from Step 3)
3. Explain what each field does in one line each
4. Ask the user to confirm they've saved the config before proceeding

Do NOT proceed to Step 6 until the user confirms.

---

### Step 6: Verify Setup

Guide the user through verification:

1. **Restart** — Tell the user to restart their AI assistant (IDE, CLI, or extension) to load the new MCP config
2. **Test** — Ask the user to try: "List my EKS clusters" or "What EKS MCP tools are available?"
3. **Confirm** — Ask if the tools appeared and the command worked

If verification fails, read the Troubleshooting section from the reference file loaded in Step 5 and walk through the relevant fix.

---

## Interaction Rules

1. **Do NOT call any tools when this skill is first activated.** Start by checking Step 0, then ask questions.
2. **Do NOT assume hosting mode, access level, or assistant.** Always ask explicitly.
3. **Do NOT skip steps or combine multiple questions into one.** One decision per step.
4. **If the user provides choices up front** (e.g., "set up AWS-hosted read-only for Claude Code in us-west-2"), acknowledge each choice back to them for confirmation before generating the config. Do not silently accept — confirm.
5. **Do NOT generate config until all 4 choices are confirmed** (hosting mode, access level, assistant, region).
6. **Always read the relevant reference file** before generating config — do not rely on memory for exact args, env vars, or paths.

---

## After Setup

Once the MCP server is verified:
- This skill's job is done
- Hand off to the EKS MCP tools for actual cluster operations
- For operational work, use eks-recon (discovery), eks-operation-review (audits), or eks-upgrade-check (upgrades)
