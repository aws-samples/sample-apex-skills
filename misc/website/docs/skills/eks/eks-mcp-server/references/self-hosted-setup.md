---
title: "Self-Hosted EKS MCP Server Setup"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-mcp-server/references/self-hosted-setup.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-mcp-server/references/self-hosted-setup.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-mcp-server/references/self-hosted-setup.md). Edit the source, not this page.
:::

# Self-Hosted EKS MCP Server Setup

> **Part of:** [eks-mcp-server](../)

The open-source EKS MCP server from [awslabs/mcp](https://github.com/awslabs/mcp) runs locally on your machine, providing full control over authentication and configuration.

## Prerequisites

- Python 3.10+ (`python3 --version`)
- `uv` package manager (`uv --version`) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **For IAM mode**: AWS CLI configured (`aws configure list`)
- **For kubeconfig mode**: Valid kubeconfig with cluster access
- **Kubernetes access for the MCP caller.** For IAM-authenticated EKS reads, use an access entry with an appropriate policy or RBAC binding, or an existing `aws-auth` mapping where supported. The assessment skills do not change access. During setup a principal with effective `PowerUserAccess` can create its own entry.

`AmazonEKSViewPolicy` grants Kubernetes read permissions only, no IAM permissions, and covers most namespaced workload resources but not Secrets or most cluster-scoped and extension resources (for example nodes, persistentvolumes, storageclasses, ingressclasses, CRDs, admission webhook configurations, Gateway API resources and metrics.k8s.io); confirm each read through the MCP server (Step 3). Policy ARN: `arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy`.

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

The examples pin `awslabs.eks-mcp-server@0.2.1`. Pin a reviewed version and bump it on purpose after reading the release notes.

```json
{
  "mcpServers": {
    "awslabs.eks-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.eks-mcp-server@0.2.1",
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
        "awslabs.eks-mcp-server@0.2.1",
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
"args": ["awslabs.eks-mcp-server@0.2.1"]
```

## Config File Locations by Assistant

| Assistant | Config File |
|-----------|-------------|
| Claude Code | `.mcp.json` (project) or `~/.claude.json` (user, via `claude mcp add -s user`) |
| Cursor | Settings → Tools & MCP |
| Kiro | `~/.kiro/settings/mcp.json` |
| VS Code (Cline) | Cmd+Shift+P → MCP → User Config |

## Windows Users

Use this format for the args array:

```json
"args": [
  "--from", "awslabs.eks-mcp-server@0.2.1",
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
3. For EKS, compare the MCP connection's target endpoint (including the server's selected kubeconfig context) with `aws eks describe-cluster --name <cluster> --region <region>` before any Kubernetes request. For kubeconfig setups without AWS discovery, compare the selected endpoint with the operator-confirmed target. Stop if the match cannot be verified. Through the verified connection, test a required read such as listing nodes for cost or ingressclasses for ingress. If it fails, report the missing read. Where entries are enabled, `aws eks list-access-entries --cluster-name <cluster> --region <region>` can help diagnose the failure. An empty or denied listing alone does not establish whether the read is authorized.

## Available Tools

### Always Available
- `list_k8s_resources`, `manage_k8s_resource` (supports `create`, `read`, `update`, `delete` operations — `read` replaces the older standalone `read_k8s_resource` tool)
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
| K8s API errors | Verify the MCP caller and failed read as described in Step 3 |
| kubeconfig not found | Set `KUBECONFIG` env var to correct path |

## References

- [awslabs/mcp EKS Server](https://github.com/awslabs/mcp/tree/main/src/eks-mcp-server)
- [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
