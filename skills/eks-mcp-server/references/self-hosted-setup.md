# Self-Hosted EKS MCP Server Setup

> **Part of:** [eks-mcp-server](../SKILL.md)

The open-source EKS MCP server from [awslabs/mcp](https://github.com/awslabs/mcp) runs locally on your machine, providing full control over authentication and configuration.

## Prerequisites

- Python 3.10+ (`python3 --version`)
- `uv` package manager (`uv --version`) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **For IAM mode**: AWS CLI configured (`aws configure list`)
- **For kubeconfig mode**: Valid kubeconfig with cluster access
- **For IAM-authenticated EKS Kubernetes reads**: The server's actual IAM principal needs Kubernetes authorization independently of its AWS permissions. In authentication mode `API`, create an access entry and associate an access policy and/or grant Kubernetes RBAC. `API_AND_CONFIG_MAP` also accepts existing `aws-auth` mappings; `CONFIG_MAP` uses that legacy path. Kubeconfig mode using OIDC or non-AWS Kubernetes does not require EKS access entries.

### Verify the target and access prerequisites

For IAM-authenticated EKS connections, use the same AWS profile/role and region as the server (including any assumed role). These IAM identity/entry checks do not apply to external OIDC identities; verify their Kubernetes RBAC and actual reads instead:

```bash
aws sts get-caller-identity
aws eks describe-cluster --name <cluster> --region <region> --query 'cluster.{arn:arn,endpoint:endpoint,authenticationMode:accessConfig.authenticationMode}'
# Only for API or API_AND_CONFIG_MAP authentication modes:
aws eks list-access-entries --cluster-name <cluster> --region <region>
```

Match entries to the IAM user/role ARN, not an STS session ARN. The last command needs `eks:ListAccessEntries`; if denied, entry verification is unavailable, not evidence that an entry is missing. An absent entry in mixed mode does not rule out valid `aws-auth` access. Entry existence alone does not establish authorization: inspect the associated access policies/scopes or RBAC grants and test required reads in Step 3.

`AmazonEKSViewPolicy` (`arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy`) grants Kubernetes permissions, **no IAM permissions**, and omits nodes and ingressclasses. In IAM mode, the server still needs the AWS permissions in Step 1, and supplementary RBAC for reads not covered by its access policy. An authorized administrator can create entries (`eks:CreateAccessEntry`) and associate policies (`eks:AssociateAccessPolicy`); `PowerUserAccess` allows those EKS actions unless constrained by other policies, but does not automatically grant Kubernetes access. Do not change permissions merely to run a read-only assessment.

For kubeconfig mode, record the original current-context and inspect the selected context's endpoint with `kubectl --context <context> config view --minify -o jsonpath='{.clusters[0].cluster.server}'`. For IAM-authenticated EKS, compare it with DescribeCluster above; for external OIDC or non-AWS setups, use the operator-confirmed target endpoint. Context aliases are valid; names alone are insufficient. Ensure the server uses that verified binding; changing the CLI's current-context does not prove a running server retargeted. Pin CLI verification reads with `--context <verified-context>`. Complete this comparison before issuing Kubernetes requests: inspect the metadata result first, or guard subsequent reads with a fail-closed comparison in the same command. Printing the endpoint alongside unguarded reads is not verification. Stop on an unverified target. If setup changes current-context, tell the user first and restore its original value on completion or failure (unset it again if originally unset).

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
3. For live cluster access, verify the server's target account/region/cluster (or selected kubeconfig binding), then request a required Kubernetes read such as listing Deployments in a known namespace. Discovery success alone does not prove Kubernetes access. For cost/ingress assessments also test Node reads, and for ingress test IngressClass and Ingress reads. Report a denied read with its required permission, never as an empty inventory; test through MCP itself, since another CLI principal's success does not verify the server.

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
| K8s API errors | Verify target endpoint/reachability, actual auth principal, authentication mode, access entry or legacy mapping, and policy/RBAC coverage; denied reads are not empty results |
| kubeconfig not found | Set `KUBECONFIG` env var to correct path |

## References

- [awslabs/mcp EKS Server](https://github.com/awslabs/mcp/tree/main/src/eks-mcp-server)
- [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
