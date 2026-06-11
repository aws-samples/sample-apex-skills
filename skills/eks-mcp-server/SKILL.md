---
name: eks-mcp-server
description: Install, configure, and troubleshoot the EKS MCP Server connection in your AI assistant (Claude Code, Cursor, Kiro). Use ONLY for MCP server setup problems — config file location (.mcp.json), IAM permissions for eks-mcp actions, uvx installation, choosing AWS-hosted vs self-hosted mode, or debugging why MCP tools fail to appear after config. Also activate if user mentions "eks mcp", "mcp server", "mcp.json", or "mcp tools not showing". Do NOT use for actual cluster operations once MCP is working — those go to eks-recon (discovery), eks-operation-review (audits), or eks-upgrade-check (upgrades).
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

Ask which hosting mode: **AWS-Hosted** (managed by AWS, requires IAM, CloudTrail audit logging) or **Self-Hosted** (local via `uvx`, supports kubeconfig/OIDC, works air-gapped). Explain the trade-off: AWS-Hosted is simplest if you have credentials; Self-Hosted if you need OIDC/kubeconfig auth or air-gapped support.

Wait for the user's answer before proceeding.

---

### Step 2: Access Level

Ask what access level: **Read-only** (list, describe, view — cannot modify anything) or **Full access** (read-only plus create/update/delete on K8s resources, CloudFormation, IAM). Recommend read-only to start — can upgrade later by changing one flag.

Wait for the user's answer before proceeding.

---

### Step 3: AI Assistant

Ask which AI assistant they're configuring. Supported options and their config locations:

| Assistant | Config location |
|-----------|----------------|
| Claude Code | `.mcp.json` (project-scope) or `~/.claude.json` (user-scope) |
| Cursor IDE | Settings → Cursor Settings → Tools & MCP → New MCP Server |
| Kiro IDE | `~/.kiro/settings/mcp.json` or `.kiro/settings/mcp.json` |
| VS Code (Cline) | Cmd/Ctrl+Shift+P → "MCP" → Add Server → Open User Configuration |

Wait for the user's answer before proceeding.

---

### Step 4: Region & Profile

Ask which AWS region their EKS clusters are in (e.g., `us-west-2`, `eu-west-1`). Also ask if they use a named AWS profile (default: `default`). Region and profile can be asked together — they're a single decision point.

Wait for the user's answer before proceeding.

---

### Step 5: Configure

**Action 1 — Load reference file**

| Hosting mode | Reference file |
|---|---|
| AWS-Hosted | `${CLAUDE_SKILL_DIR}/references/aws-hosted-setup.md` |
| Self-Hosted | `${CLAUDE_SKILL_DIR}/references/self-hosted-setup.md` |

- Success → Proceed to Action 2.
- Failure (file not found) → STOP. Show: "Cannot read reference file at `<path>`. Verify the skill is installed correctly (`npx apex-skills` or check `skills/eks-mcp-server/references/`)." Wait for the user to resolve.

**Action 2 — Generate config**

Based on the answers from Steps 1–4 and the reference file content:

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

**If verification fails**, diagnose in this order:

1. **Config location** — Is the JSON file in the correct path for the chosen assistant (Step 3 table)? Ask the user to confirm.
2. **JSON validity** — Ask the user to check for syntax errors (trailing commas, missing braces). Provide a quick validation command: `python3 -c "import json; json.load(open('<path>'))"`.
3. **Credentials** — Ask the user to run `aws sts get-caller-identity` to confirm AWS credentials are working.
4. **Permissions** — If credentials work but MCP tools fail, check IAM permissions per the Troubleshooting section of the reference file loaded in Step 5.

If none of the above resolve it, read the full Troubleshooting section from the reference file and walk through remaining scenarios.

---

## Interaction Rules

1. **Do NOT call any tools when this skill is first activated.** Start by checking Step 0, then ask questions.
2. **Do NOT assume hosting mode, access level, or assistant.** Always ask explicitly.
3. **One decision per step.** If the user has already provided an answer (explicitly in their message or from prior context), confirm it instead of re-asking — but never silently skip.
4. **If the user provides all choices up front** (e.g., "set up AWS-hosted read-only for Claude Code in us-west-2"), summarize the choices back and ask for a single confirmation before generating config.
5. **Do NOT generate config until all 4 choices are confirmed** (hosting mode, access level, assistant, region).
6. **Always read the relevant reference file** before generating config — do not rely on memory for exact args, env vars, or paths.
7. **Do NOT retry a failed file read or command more than once.** STOP and surface the error to the user.

---

## After Setup

Once the MCP server is verified:
- This skill's job is done
- Hand off to the EKS MCP tools for actual cluster operations
- For operational work, use eks-recon (discovery), eks-operation-review (audits), or eks-upgrade-check (upgrades)
