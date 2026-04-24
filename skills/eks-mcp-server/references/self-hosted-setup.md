# Self-Hosted EKS MCP Server Setup

> **Part of:** [eks-mcp-server](../SKILL.md)

The open-source EKS MCP server from [awslabs/mcp](https://github.com/awslabs/mcp) runs locally on your machine, providing full control over authentication and configuration.

## Prerequisites

- Python 3.10+ (`python3 --version`)
- `uv` package manager (`uv --version`) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **For IAM mode**: AWS CLI configured (`aws configure list`)
- **For kubeconfig mode**: Valid kubeconfig with cluster access

## Authentication Modes

| Mode | Use When | AWS Credentials |
|------|----------|-----------------|
| **IAM** (default) | Standard AWS/EKS setup | Required |
| **kubeconfig** | OIDC auth, air-gapped, non-AWS K8s | Not required |

## Step 1: Configure IAM (IAM Mode Only)

For IAM authentication, attach these permissions to your IAM role/user:

### Read-Only Policy
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "eks:DescribeCluster",
      "eks:DescribeInsight",
      "eks:ListInsights",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeRouteTables",
      "cloudformation:DescribeStacks",
      "cloudwatch:GetMetricData",
      "logs:StartQuery",
      "logs:GetQueryResults",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "eks-mcpserver:QueryKnowledgeBase"
    ],
    "Resource": "*"
  }]
}
```

### Write Operations
For write access (cluster creation, deployments), also attach:
- `IAMFullAccess`
- `AmazonVPCFullAccess`
- `AWSCloudFormationFullAccess`
- EKS Full Access: `"Action": "eks:*"`

## Step 2: Configure Your AI Assistant

### Basic Configuration (IAM Mode)

```json
{
  "mcpServers": {
    "awslabs.eks-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.eks-mcp-server@latest",
        "--allow-write",
        "--allow-sensitive-data-access"
      ],
      "env": {
        "AWS_PROFILE": "default",
        "AWS_REGION": "us-west-2",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

### Kubeconfig Mode (OIDC/Non-IAM)

```json
{
  "mcpServers": {
    "awslabs.eks-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.eks-mcp-server@latest",
        "--allow-write",
        "--allow-sensitive-data-access"
      ],
      "env": {
        "EKS_AUTH_MODE": "kubeconfig",
        "KUBECONFIG": "~/.kube/config",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

**Note**: In kubeconfig mode, AWS-specific tools are disabled:
- `manage_eks_stacks` (CloudFormation)
- `get_cloudwatch_logs`, `get_cloudwatch_metrics`
- `get_eks_vpc_config`, `get_eks_insights`
- `get_policies_for_role`, `add_inline_policy`

### Read-Only Mode

Remove `--allow-write` and `--allow-sensitive-data-access` for safer operation:

```json
"args": ["awslabs.eks-mcp-server@latest"]
```

## Config File Locations by Assistant

| Assistant | Config File |
|-----------|-------------|
| Amazon Q CLI | `~/.aws/amazonq/mcp.json` |
| Claude Code | `.mcp.json` (project) or `~/.claude.json` (user, via `claude mcp add -s user`) |
| Cursor | Settings → Tools & MCP |
| Kiro | `~/.kiro/settings/mcp.json` |
| VS Code (Cline) | Cmd+Shift+P → MCP → User Config |

## Windows Users

Use this format for the args array:

```json
"args": [
  "--from", "awslabs.eks-mcp-server@latest",
  "awslabs.eks-mcp-server.exe",
  "--allow-write",
  "--allow-sensitive-data-access"
]
```

## Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `--allow-write` | Enable create/update/delete operations |
| `--allow-sensitive-data-access` | Enable logs, events, secrets access |
| `--auth-mode kubeconfig` | Use kubeconfig instead of IAM |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_PROFILE` | AWS credentials profile | default |
| `AWS_REGION` | AWS region for EKS | us-east-1 |
| `EKS_AUTH_MODE` | `iam` or `kubeconfig` | iam |
| `KUBECONFIG` | Path to kubeconfig file | ~/.kube/config |
| `FASTMCP_LOG_LEVEL` | Log verbosity | WARNING |
| `HTTP_PROXY` / `HTTPS_PROXY` | Proxy settings | none |

## Step 3: Verify Setup

1. Restart your AI assistant
2. Ask: "List my EKS clusters" or "What tools are available?"

## Available Tools

### Always Available
- `list_k8s_resources`, `read_k8s_resource`, `manage_k8s_resource`
- `apply_yaml`, `generate_app_manifest`
- `get_pod_logs`, `get_k8s_events`
- `list_api_versions`

### IAM Mode Only
- `manage_eks_stacks` — CloudFormation cluster management
- `get_cloudwatch_logs`, `get_cloudwatch_metrics` — observability
- `get_eks_vpc_config` — VPC configuration
- `get_eks_insights` — upgrade readiness
- `get_policies_for_role`, `add_inline_policy` — IAM management
- `search_eks_troubleshoot_guide` — troubleshooting KB

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Permission errors | Verify IAM policy or kubeconfig RBAC |
| Tools not appearing | Restart IDE/CLI; check `FASTMCP_LOG_LEVEL=DEBUG` |
| K8s API errors | Ensure EKS access entry exists for your principal |
| kubeconfig not found | Set `KUBECONFIG` env var to correct path |

## References

- [awslabs/mcp EKS Server](https://github.com/awslabs/mcp/tree/main/src/eks-mcp-server)
- [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
