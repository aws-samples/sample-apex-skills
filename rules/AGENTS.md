# AWS & EKS Guidance

- For EKS or ECS requests, load the `apex` skill first if it is installed:
  it routes to the matching skill and holds the shared APEX rules. If it
  is not installed, use the matching skill directly.
- Before any task, check for a relevant AWS or APEX skill.
  APEX skills are installed at `~/.claude/skills/` (Claude Code) or
  `~/.kiro/skills/` (Kiro), or under `.claude/skills/` or `.kiro/skills/`
  in the project for a `--project` install. Prefer skill guidance over
  general knowledge.
- Prefer the AWS MCP Server for AWS interactions: it provides scoped
  IAM access and CloudTrail-compatible audit logging. If unavailable,
  use the AWS CLI directly.
- Prefer the EKS MCP Server for live cluster interactions: it provides
  Kubernetes API access (read by default, write if configured), upgrade
  insights, and cluster discovery. If unavailable, use kubectl and AWS
  CLI directly.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When uncertain about specific EKS details (add-on versions, API parameters,
  Karpenter behavior, VPC CNI settings), verify against upstream source repos
  rather than guessing. Cross-reference the upstream repo to confirm the
  behavior still holds in the current release:
  - Karpenter: `github.com/aws/karpenter-provider-aws`
  - VPC CNI: `github.com/aws/amazon-vpc-cni-k8s`
  - AWS Load Balancer Controller: `github.com/kubernetes-sigs/aws-load-balancer-controller`
  - CoreDNS: `github.com/coredns/coredns`
  - EKS AMI: `github.com/awslabs/amazon-eks-ami`
  - EKS Terraform module: `github.com/terraform-aws-modules/terraform-aws-eks`
- When creating infrastructure, prefer infrastructure-as-code (Terraform with
  `terraform-aws-modules/terraform-aws-eks`, AWS CDK, or CloudFormation) over
  direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Never execute destructive operations (node drain, cluster delete, force
  eviction) without explicit user confirmation.
- Never output secrets, credentials, or kubeconfig contents in responses.
- Avoid non-ASCII characters (including em dashes) in AWS resource names
  and descriptions. Use hyphens instead.
