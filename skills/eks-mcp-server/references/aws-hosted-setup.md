# AWS-Hosted EKS MCP Server Setup

> **Part of:** [eks-mcp-server](../SKILL.md)

> **Note:** The AWS-Hosted EKS MCP Server is currently in preview.

The fully managed EKS MCP Server is hosted by AWS, providing enterprise-grade capabilities with zero local maintenance.

## Prerequisites

- AWS account with EKS clusters
- AWS CLI installed and configured (`aws configure list`)
- Python 3.11 to 3.14 (`python3 --version`)
- `uv` package manager (`uv --version`) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Kubernetes access for the MCP caller.** For IAM-authenticated EKS reads, use an access entry with an appropriate policy or RBAC binding, or an existing `aws-auth` mapping where supported. The assessment skills do not change access. During setup a principal with effective `PowerUserAccess` can create its own entry.

`AmazonEKSViewPolicy` grants Kubernetes read permissions only, no IAM permissions, and covers most namespaced workload resources but not Secrets or most cluster-scoped and extension resources (for example nodes, persistentvolumes, storageclasses, ingressclasses, CRDs, admission webhook configurations, Gateway API resources and metrics.k8s.io); confirm each read through the MCP server (Step 3). Policy ARN: `arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy`.

## Step 1: Configure IAM Permissions

Attach the appropriate managed policy to your IAM role/user:

| Access Level | Managed Policy |
|--------------|----------------|
| **Read-only** (recommended to start) | `AmazonEKSMCPReadOnlyAccess` |
| **Full access** (includes write ops) | Create custom policy below |

For read-only, attach via IAM console or CLI:
```bash
aws iam attach-user-policy --user-name YOUR_USER --policy-arn arn:aws:iam::aws:policy/AmazonEKSMCPReadOnlyAccess
```

Required IAM actions for the MCP proxy:
- `eks-mcp:InvokeMcp` — initialization and tool discovery
- `eks-mcp:CallReadOnlyTool` — read operations
- `eks-mcp:CallPrivilegedTool` — write operations (optional)

## Step 2: Configure Your AI Assistant

Add the EKS MCP server to your assistant's MCP configuration. Replace `{region}` with your AWS region (e.g., `us-west-2`).

The same JSON below works for every supported assistant — only the config file path (or UI entry point) differs.

Pin a reviewed version and bump it on purpose after reading the release notes.

```json
{
  "mcpServers": {
    "eks-mcp": {
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@1.8.0",
        "https://eks-mcp.{region}.api.aws/mcp",
        "--service", "eks-mcp",
        "--region", "{region}"
      ]
    }
  }
}
```

### Config File Locations by Assistant

| Assistant | Config File / Entry Point | Notes |
|-----------|---------------------------|-------|
| Claude Code | `.mcp.json` (project) or `~/.claude.json` (user) | Prefer project-scope `.mcp.json` (checked in, shared with teammates). For user scope, run `claude mcp add -s user` — do not hand-edit `~/.claude.json`. |
| Cursor IDE | Settings → Cursor Settings → Tools & MCP → New MCP Server | — |
| Kiro IDE | `~/.kiro/settings/mcp.json` or `.kiro/settings/mcp.json` | — |
| VS Code (Cline Extension) | Cmd/Ctrl+Shift+P → "MCP" → Add Server → Open User Configuration | — |

## Optional: Read-Only Mode

Add `--read-only` to args to disable write operations:

```json
"args": [
  "mcp-proxy-for-aws@1.8.0",
  "https://eks-mcp.{region}.api.aws/mcp",
  "--service", "eks-mcp",
  "--region", "{region}",
  "--read-only"
]
```

## Optional: Multiple AWS Profiles

Specify a profile with `--profile`:

```json
"args": [
  "mcp-proxy-for-aws@1.8.0",
  "https://eks-mcp.{region}.api.aws/mcp",
  "--service", "eks-mcp",
  "--profile", "production",
  "--region", "{region}"
]
```

## Windows Users

Use this format for the args array:

```json
"args": [
  "--from", "mcp-proxy-for-aws@1.8.0",
  "mcp-proxy-for-aws.exe",
  "https://eks-mcp.{region}.api.aws/mcp",
  "--service", "eks-mcp",
  "--region", "{region}"
]
```

## Step 3: Verify Setup

1. Restart your AI assistant
2. Ask: "List my EKS clusters" or "What EKS MCP tools are available?"
3. For EKS, compare the MCP connection's cluster ARN or endpoint with `aws eks describe-cluster --name <cluster> --region <region>` before any Kubernetes request. Stop if the match cannot be verified. Through the verified connection, test a required read such as listing nodes for cost or ingressclasses for ingress. If it fails, report the missing read. Where entries are enabled, `aws eks list-access-entries --cluster-name <cluster> --region <region>` can help diagnose the failure. An empty or denied listing alone does not establish whether the read is authorized.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Access Denied" | Check IAM policy has `eks-mcp:*` actions |
| Tools not appearing | Restart IDE/CLI after config change |
| Connection timeout | Verify region matches your EKS clusters |
| Proxy issues | Set `HTTP_PROXY`/`HTTPS_PROXY` env vars |

## References

- [AWS EKS MCP Getting Started](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-getting-started.html)
- [MCP Proxy for AWS](https://github.com/aws/mcp-proxy-for-aws)
