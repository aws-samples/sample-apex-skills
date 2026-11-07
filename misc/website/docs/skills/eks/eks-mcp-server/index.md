---
title: "EKS MCP Server: connect your AI assistant to Amazon EKS"
sidebar_label: "eks-mcp-server"
description: "Install, configure and troubleshoot the EKS MCP Server connection in your AI assistant (Claude Code, Cursor, Kiro)"
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-mcp-server/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-mcp-server/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-mcp-server/SKILL.md). Edit the source, not this page.
:::


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
2. Try a simple command: ask to list EKS clusters. If it works, discovery is configured.

If the request was only about discovery and the tools work, stop here. A working cluster list proves discovery only; for live Kubernetes reads, verify the target and the MCP caller's access per the loaded setup reference (Step 6).

---

### Step 1: Hosting Mode

Ask which hosting mode: **AWS-Hosted** (managed by AWS, requires IAM, CloudTrail audit logging) or **Self-Hosted** (local via `uvx`, supports kubeconfig/OIDC, works air-gapped). Explain the trade-off: AWS-Hosted is simplest if you have credentials; Self-Hosted if you need OIDC/kubeconfig auth or air-gapped support.

Wait for the user's answer before proceeding.

---

### Step 1b: Server Version

The package follows the hosting mode: Self-Hosted runs `awslabs.eks-mcp-server`, AWS-Hosted runs `mcp-proxy-for-aws-cli`. Ask how to handle its version:

- **Latest** (`@latest`): uvx resolves the newest release at every launch. Newest fixes, but releases you have not reviewed run with your cluster and AWS access.
- **Pinned to today's latest**: the exact current version goes into the config, and you bump it on purpose later. This pins that package only: `awslabs.eks-mcp-server` declares its dependencies as ranges, so they still resolve to their newest matching releases at first install, while each `mcp-proxy-for-aws-cli` release pins its whole dependency tree.
- **Pinned to a version you name**: that exact version goes into the config.

For AWS-Hosted this pins only the local proxy; AWS runs and updates the server.

Wait for the user's answer, then look the version up live with your web-fetch tool (WebFetch in Claude Code), or curl if shell access is allowed. Fetch `https://pypi.org/pypi/<package>/json` and read `info.version` and `info.requires_python` (the current release). For a named version, fetch `https://pypi.org/pypi/<package>/<version>/json` instead: a 404 means that version is not published, otherwise read its `info.requires_python`.

- Latest: tell the user the current version, and use `latest`.
- Pinned to today's latest: use `info.version`.
- Named version: if it is not published, say so and ask again (`mcp-proxy-for-aws-cli` releases start at 1.6.5). If it is older than the current release, name both and ask the user to confirm. Use the named version.
- In every case, give the Python range from the chosen release's `requires_python` as the Python prerequisite.

If the lookup fails (no network, blocked, or an error), say so plainly. Latest: use `@latest`. Named version: use it once the user confirms it could not be checked. Pinned to today's latest: ask whether to use `@latest` or the known version below. Never guess a newer version. If this machine cannot reach PyPI or a mirror at all, uvx cannot install either choice until an index mirror is set or the package is cached.

Known versions when this skill was last updated (2026-11-07, read from PyPI): awslabs.eks-mcp-server 0.2.1 (Python >=3.10), mcp-proxy-for-aws-cli 1.8.0 (Python >=3.11,<3.15). These may be out of date; never present them as the current release.

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
- Failure (file not found) → STOP. Show: "Cannot read reference file at `<path>`. Verify the skill is installed correctly (`npx apex-skills@1.3.0` or check `skills/eks-mcp-server/references/`)." Wait for the user to resolve.

**Action 2 — Generate config**

Based on the answers from Steps 1–4 and the reference file content:

1. Generate the complete JSON config block tailored to the user's choices (hosting mode, server version, access level, region, profile, assistant), with `<version>` in the reference's launch line replaced by the Step 1b result
2. Show the user exactly where to paste it (file path or UI location from Step 3)
3. Explain what each field does in one line each
4. Ask the user to confirm they've saved the config before proceeding

Do NOT proceed to Step 6 until the user confirms.

---

### Step 6: Verify Setup

Guide the user through verification:

1. **Restart** — Tell the user to restart their AI assistant (IDE, CLI, or extension) to load the new MCP config
2. **Test** — Ask the user to try: "List my EKS clusters" or "What EKS MCP tools are available?"
3. **Confirm** — Go to Step 3 of the [self-hosted](references/self-hosted-setup.md) or [AWS-hosted](references/aws-hosted-setup.md) reference and confirm a required read through that server.

**If verification fails**, diagnose in this order:

1. **Config location** — Is the JSON file in the correct path for the chosen assistant (Step 3 table)? Ask the user to confirm.
2. **JSON validity** — Ask the user to check for syntax errors (trailing commas, missing braces). Provide a quick validation command: `python3 -c "import json; json.load(open('<path>'))"`.
3. **Credentials** — Ask the user to run `aws sts get-caller-identity` to confirm AWS credentials are working.
4. **Permissions** — If credentials work but MCP tools fail, check IAM permissions per the Troubleshooting section of the reference file loaded in Step 5.

If none of the above resolve it, read the full Troubleshooting section from the reference file and walk through remaining scenarios.

---

## Interaction Rules

1. **Do NOT call any tools when this skill is first activated.** Start by checking Step 0, then ask questions.
2. **Do NOT assume hosting mode, server version, access level, or assistant.** Always ask explicitly.
3. **One decision per step.** If the user has already provided an answer (explicitly in their message or from prior context), confirm it instead of re-asking — but never silently skip.
4. **If the user provides all choices up front** (e.g., "set up AWS-hosted read-only for Claude Code in us-west-2, at @latest"), summarize the choices back and ask for a single confirmation before generating config.
5. **Do NOT generate config until all 5 choices are confirmed** (hosting mode, server version, access level, assistant, region).
6. **Always read the relevant reference file** before generating config — do not rely on memory for exact args, env vars, or paths.
7. **Do NOT retry a failed file read or command more than once.** STOP and surface the error to the user.

---

## After Setup

Once the MCP server is verified:
- This skill's job is done
- Hand off to the EKS MCP tools for actual cluster operations
- For operational work, use eks-recon (discovery), eks-operation-review (audits), or eks-upgrade-check (upgrades)
