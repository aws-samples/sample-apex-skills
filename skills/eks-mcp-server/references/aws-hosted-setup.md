# AWS-Hosted EKS MCP Server Setup

> **Part of:** [eks-mcp-server](../SKILL.md)

> **Note:** The AWS-Hosted EKS MCP Server is currently in preview.

The fully managed EKS MCP Server is hosted by AWS, providing enterprise-grade capabilities with zero local maintenance.

## Prerequisites

- AWS account with EKS clusters
- AWS CLI installed and configured (`aws configure list`)
- Python 3.10+ (`python3 --version`)
- `uv` package manager (`uv --version`) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Kubernetes authorization for the MCP caller** — separate from the IAM permissions that allow MCP invocation and AWS discovery. With authentication mode `API`, the caller needs an EKS access entry plus an associated access policy and/or Kubernetes RBAC grants. `API_AND_CONFIG_MAP` also accepts existing `aws-auth` mappings; `CONFIG_MAP` uses that legacy path.

### Verify the target and access prerequisites

Use the same AWS profile/role and region as the proxy, including any assumed role:

```bash
aws sts get-caller-identity
aws eks describe-cluster --name <cluster> --region <region> --query 'cluster.{arn:arn,endpoint:endpoint,authenticationMode:accessConfig.authenticationMode}'
# Only for API or API_AND_CONFIG_MAP authentication modes:
aws eks list-access-entries --cluster-name <cluster> --region <region>
```

Match entries to the caller's IAM user/role ARN, not an STS session ARN. Listing needs `eks:ListAccessEntries`; denial means entry verification is unavailable, not an absent entry. In mixed mode, no entry does not exclude valid `aws-auth` access. Verify associated policy scopes/RBAC grants and actual Kubernetes reads in Step 3; an entry alone is insufficient.

`AmazonEKSViewPolicy` (`arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy`) grants Kubernetes permissions, **no IAM permissions**, and omits nodes and ingressclasses. Keep the IAM permissions for MCP invocation and the AWS APIs used (including EKS Describe/List actions and `eks:AccessKubernetesApi` for AWS-hosted Kubernetes reads), and grant supplementary RBAC for required reads the access policy omits. Entry creation and policy association require `eks:CreateAccessEntry` and `eks:AssociateAccessPolicy`: an authorized administrator with effective `PowerUserAccess` can perform them unless constrained by other policies, but that IAM policy alone gives no Kubernetes access. Do not change access during a read-only assessment.

Bind MCP reads to the cluster ARN/account/region verified by DescribeCluster and the intended Kubernetes endpoint. A local kubectl current-context neither selects nor verifies the AWS-hosted server's target. If using kubectl as a diagnostic fallback, compare `kubectl --context <context> config view --minify -o jsonpath='{.clusters[0].cluster.server}'` with that endpoint before any read, then pass `--context <verified-context>` explicitly; aliases are valid, matching names alone are insufficient. Complete this comparison before issuing Kubernetes requests: inspect the metadata result first, or guard subsequent reads with a fail-closed comparison in the same command. Printing the endpoint alongside unguarded reads is not verification. Stop if the target cannot be verified. Preserve current-context; if local setup changes it, tell the user first and restore the original value on completion or failure (unset it again if originally unset).

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

```json
{
  "mcpServers": {
    "eks-mcp": {
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
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
  "mcp-proxy-for-aws@latest",
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
  "mcp-proxy-for-aws@latest",
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
  "--from", "mcp-proxy-for-aws@latest",
  "mcp-proxy-for-aws.exe",
  "https://eks-mcp.{region}.api.aws/mcp",
  "--service", "eks-mcp",
  "--region", "{region}"
]
```

## Step 3: Verify Setup

1. Restart your AI assistant
2. Ask: "List my EKS clusters" or "What EKS MCP tools are available?"
3. For live cluster access, request a required Kubernetes read through MCP against the verified target, such as listing Deployments in a known namespace. For cost/ingress assessments also test Node reads, and for ingress test IngressClass and Ingress reads. A working cluster list verifies discovery only; entry existence or a successful read using a different CLI principal does not verify the MCP caller's Kubernetes access. Report denied reads with the required permission, never as an empty inventory.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Access Denied" | Check IAM policy has `eks-mcp:*` actions |
| Kubernetes read denied | Check the actual caller's access entry or legacy mapping, policy scope and RBAC for that resource; MCP invocation permission alone is insufficient |
| Tools not appearing | Restart IDE/CLI after config change |
| Connection timeout | Verify region matches your EKS clusters |
| Proxy issues | Set `HTTP_PROXY`/`HTTPS_PROXY` env vars |

## References

- [AWS EKS MCP Getting Started](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-getting-started.html)
- [MCP Proxy for AWS](https://github.com/aws/mcp-proxy-for-aws)
