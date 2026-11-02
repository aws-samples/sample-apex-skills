---
title: "eks-mcp-server"
description: "Install, configure, and troubleshoot the EKS MCP Server connection in your AI assistant (Claude Code, Cursor, Kiro). Use ONLY for MCP server setup problems — config file location (.mcp.json), IAM permissions for eks-mcp actions, uvx installation, choosing AWS-hosted vs self-hosted mode, or debugging why MCP tools fail to appear after config. Also activate if user mentions \"eks mcp\", \"mcp server\", \"mcp.json\", or \"mcp tools not showing\". Do NOT use for actual cluster operations once MCP is working — those go to eks-recon (discovery), eks-operation-review (audits), or eks-upgrade-check (upgrades). For setting up the Arm migration MCP server used for arm64 readiness scanning, use graviton-migration, not this skill."
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

First inspect whether EKS MCP tools are available. Tool discovery and AWS cluster discovery do not query Kubernetes. For a discovery-only request, successful AWS discovery is enough to stop here; describe that limited result.

Inspect only the selected EKS connection's non-secret routing and credential-provider settings. Parse JSON/TOML locally **before displaying its contents**, then print an explicit allowlist of non-secret scalar fields. Do not emit whole files, argument arrays, environment/header maps, raw lines or grep context; these can expose adjacent secrets, URL credentials or inline provider credentials. If parsing fails, report the file path and error category and leave the binding unverified rather than falling back to a raw dump. Authentication tools may consume credentials without displaying them.

For a connection check or live Kubernetes work, complete these gates **in order**, inspecting each result before the next call. Record the connection, target and caller evidence; an unknown field stays unknown rather than being filled from a likely match.

| Gate | Evidence required | When evidence is missing |
|------|-------------------|--------------------------|
| **1. Target** | The active MCP connection's account/region/cluster binding tied to the intended DescribeCluster ARN or endpoint. For kubeconfig/OIDC, inspect the connection's selected context and endpoint; when AWS discovery is unavailable for external OIDC or a non-AWS cluster, use the operator-confirmed endpoint. | Stop before **any Kubernetes request**, including `list_api_versions` and identity checks. Report **Target unverified; Kubernetes access not tested**, naming the missing connection metadata. Continue only configuration or AWS metadata diagnostics. |
| **2. Caller** | The actual connection's active credential/provider configuration or identity evidence from that verified connection. Resolve IAM credentials with the same effective configuration; for OIDC use its configured provider/subject or an identity check against the verified target. | Only an identity check through the verified connection or the same verified active credential configuration is permitted. If that cannot establish the caller, stop before inventory and report **Caller unverified; Kubernetes access not tested**. |
| **3. Read access** | A successful required resource read through that verified connection, scoped to the intended cluster. | Report the observed failure or unverified coverage; do not claim the connection is ready for live work. |

A VPC, subnet, cluster display name or profile name is not cluster-unique binding evidence. Two clusters can share them. DescribeCluster through an unrelated CLI connection does not establish where the MCP server will send requests; a likely shared CLI role is not proof of the MCP caller. Do not use a Kubernetes request to fill a missing target binding, even if the tool advertises itself as a quick connection check.

`list_api_versions` is Kubernetes API discovery, so it is subject to the target gate. Its success does not prove resource-read authorization. Do not batch inventory calls with unresolved verification calls. Skip setup only when these gates pass; otherwise retain the diagnostic-only result and request the missing connection configuration without changing credentials or permissions.

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
- Failure (file not found) → STOP. Show: "Cannot read reference file at `<path>`. Verify the skill is installed correctly (`npx apex-skills@1.3.0` or check `skills/eks-mcp-server/references/`)." Wait for the user to resolve.

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
3. **Cluster access** — For live cluster reads, follow the loaded setup reference's target and Kubernetes authorization checks. A working cluster list does not prove access to the Kubernetes API; use the actual MCP principal/connection. When explaining verification, give complete diagnostic commands/tool calls scoped to the selected cluster and region, including `aws eks list-access-entries --cluster-name <cluster> --region <region>` when the authentication mode enables entries.
4. **Confirm** — Ask if the tools appeared and the required read against the intended cluster worked (or explicitly record that only tool discovery was tested)

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
