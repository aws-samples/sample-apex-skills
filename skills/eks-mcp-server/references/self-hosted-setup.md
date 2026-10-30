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

`logs:StartQuery` and `logs:GetQueryResults` serve only `get_cloudwatch_logs`, which needs `--allow-sensitive-data-access`; drop them for a strict read-only profile.

### Write Operations
For write access (cluster creation, deployments), also attach:
- `IAMFullAccess`
- `AmazonVPCFullAccess`
- `AWSCloudFormationFullAccess`
- EKS Full Access: `"Action": "eks:*"`

These are broad grants. Attach them only with the opt-in write profile below, and where you can, replace them with policies scoped to the clusters, stacks and roles the server manages (least privilege).

## Step 2: Configure Your AI Assistant

### Basic Configuration (IAM Mode, read-only)

```json
{
  "mcpServers": {
    "awslabs.eks-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.eks-mcp-server@latest"
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

### Kubeconfig Mode (OIDC/Non-IAM, read-only)

```json
{
  "mcpServers": {
    "awslabs.eks-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.eks-mcp-server@latest"
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

### Opt-in: Write Access and Sensitive-Data Reads

The examples above are read-only with the sensitive-data flag off, the recommended start. Add only the flag you need; the example shows both (see Command-Line Arguments below): `--allow-write` for mutations (IAM mode: attach the write IAM permissions above; kubeconfig mode: grant write RBAC), `--allow-sensitive-data-access` for logs, events and Secret reads through `manage_k8s_resource`.

```json
"args": [
  "awslabs.eks-mcp-server@latest",
  "--allow-write",
  "--allow-sensitive-data-access"
]
```

`--allow-sensitive-data-access` puts pod logs, events, CloudWatch logs and Kubernetes Secrets (via `manage_k8s_resource`) into the model's context; `--allow-write` lets it change K8s resources, CloudFormation stacks and IAM inline policies. Upstream: "Only enable these flags when necessary and in trusted environments" (EKS MCP Server README, Important Security Note).

## Config File Locations by Assistant

| Assistant | Config File |
|-----------|-------------|
| Claude Code | `.mcp.json` (project) or `~/.claude.json` (user, via `claude mcp add -s user`) |
| Cursor | Settings → Tools & MCP |
| Kiro | `~/.kiro/settings/mcp.json` (user) or `.kiro/settings/mcp.json` (project) |
| VS Code (Cline) | Cmd+Shift+P → MCP → User Config |

## Windows Users

Use this format for the args array (read-only):

```json
"args": [
  "--from", "awslabs.eks-mcp-server@latest",
  "awslabs.eks-mcp-server.exe"
]
```

For the opt-in profile, append only the flag(s) you need (`"--allow-write"`, `"--allow-sensitive-data-access"`) after the `.exe` entry.

## Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `--allow-write` | Opt-in: enable create/update/delete operations (omit for read-only) |
| `--allow-sensitive-data-access` | Opt-in: enable logs, events and Kubernetes Secrets reads (still read-only). Omitting it does not hide Secrets from `list_k8s_resources` (see Available Tools); keep `list` on secrets out of the principal's RBAC |

To switch between IAM and kubeconfig auth, set the `EKS_AUTH_MODE` env var (see Environment Variables below) — the JSON examples above use this approach.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_PROFILE` | AWS credentials profile | default |
| `AWS_REGION` | AWS region for EKS | None (uses default AWS region) |
| `EKS_AUTH_MODE` | `iam` or `kubeconfig` | iam |
| `KUBECONFIG` | Path to kubeconfig file | ~/.kube/config |
| `FASTMCP_LOG_LEVEL` | Log verbosity | WARNING |
| `HTTP_PROXY` / `HTTPS_PROXY` | Proxy settings | none |

> **Region pitfall:** When used with the AWS-hosted proxy, `mcp-proxy-for-aws` signs SigV4 against `us-west-2` by default while the proxy's `--region` flag falls back to `us-east-1` when unset — always set `--region` (and `AWS_REGION`) explicitly to the region of your clusters to avoid a region-mismatch failure.

## Step 3: Verify Setup

1. Restart your AI assistant
2. Ask: "List my EKS clusters" or "What tools are available?"

## Available Tools

With no flags (the read-only examples above), `manage_k8s_resource` allows only `read` and `manage_eks_stacks` only `describe`; `apply_yaml`, `generate_app_manifest`, `add_inline_policy` and the other operations need `--allow-write`; `get_pod_logs`, `get_k8s_events`, `get_cloudwatch_logs` and `manage_k8s_resource` reads of a Secret need `--allow-sensitive-data-access`. Without the flag, these calls return an error. `list_k8s_resources` is not gated: for kind Secret it returns names, labels and annotations, and a Secret created with client-side `kubectl apply` carries its applied manifest, data included, in the `kubectl.kubernetes.io/last-applied-configuration` annotation. The upstream README marks `get_eks_vpc_config` and `get_eks_insights` as needing `--allow-sensitive-data-access`; the server code at 79267c6 does not enforce it.

### Both auth modes
- `list_k8s_resources`, `manage_k8s_resource` (supports `create`, `read`, `replace`, `patch`, `delete` operations)
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
