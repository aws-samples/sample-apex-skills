---
title: "Module: IaC (Infrastructure as Code)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/iac.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/iac.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/iac.md). Edit the source, not this page.
:::

# Module: IaC (Infrastructure as Code)

> **Part of:** [eks-recon](../)
> **Purpose:** Detect IaC tooling - Terraform, CloudFormation, CDK, eksctl, Pulumi

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [1. Terraform Detection](#1-terraform-detection)
  - [2. CloudFormation Detection](#2-cloudformation-detection)
  - [3. CDK Detection](#3-cdk-detection)
  - [4. eksctl Detection](#4-eksctl-detection)
  - [5. Pulumi Detection](#5-pulumi-detection)
  - [6. Crossplane and ACK Detection](#6-crossplane-and-ack-detection)
  - [7. Tag-Based Detection (Fallback)](#7-tag-based-detection-fallback)
- [Output Schema](#output-schema)
- [Confidence Determination](#confidence-determination)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** No (workspace scan), Yes (for tag verification)
- **MCP tools used:** None (filesystem scan)
- **CLI fallback:** `find`, `grep`, `aws cloudformation`

---

## Detection Strategy

IaC detection is primarily workspace-based. Scan the local filesystem for IaC configuration files:

```
1. Terraform/OpenTofu -> .tf files with aws_eks_cluster or module "eks"
2. CloudFormation     -> .yaml/.json with AWS::EKS::
3. CDK                -> cdk.json + package.json with aws-cdk
4. eksctl             -> yaml files with kind: ClusterConfig
5. Pulumi             -> Pulumi.yaml + aws provider
6. Crossplane / ACK   -> in-cluster CRDs (compositions, services.k8s.aws)
```

**Confidence scoring:**
- **High**: IaC files found with cluster name matching target
- **Medium**: IaC files found but cluster name doesn't match
- **Low**: Only cluster tags suggest IaC tool
- **Unknown**: No evidence found

---

## Detection Commands

### 1. Terraform Detection

Start with Terraform detection because it is the most common IaC tool for EKS clusters in production environments.

`.tf` file detection covers both Terraform and OpenTofu (they share the `.tf` HCL
syntax and file layout); the two are distinguished by lockfile/lockfile usage below.

```bash
# Find Terraform/OpenTofu files with EKS resources
# No head cap on the file list — large monorepos have thousands of .tf files and a
# capped scan misses the ones defining the cluster. grep -rl walks all of them directly.
grep -rl "aws_eks_cluster\|module.*eks" --include="*.tf" . 2>/dev/null | head -20
```

**Example output:**
```
./infrastructure/eks/main.tf
./infrastructure/eks/cluster.tf
./modules/eks-cluster/main.tf
```

**If files found, extract details to determine which module or resource configuration is used:**
```bash
# Check for terraform-aws-modules/eks module source
grep -r "source.*terraform-aws-modules/eks" --include="*.tf" . 2>/dev/null | head -5

# Module version — the `version = "..."` line adjacent to the module block that sources
# terraform-aws-modules/eks (grep a few lines of context around the source line)
grep -rA3 "source.*terraform-aws-modules/eks" --include="*.tf" . 2>/dev/null | \
  grep "version\s*=" | head -5

# Check for cluster name in tf files
grep -r "cluster_name\s*=" --include="*.tf" . 2>/dev/null | head -5

# Check for tfvars
find . -name "*.tfvars" -type f 2>/dev/null | head -5
```

**Example output:**
```
./infrastructure/eks/main.tf:  source  = "terraform-aws-modules/eks/aws"
./infrastructure/eks/main.tf:  version = "20.8.4"
./infrastructure/eks/main.tf:  cluster_name    = "my-production-cluster"
./infrastructure/eks/terraform.tfvars
```

- `module_source` = the `source` value (e.g. `terraform-aws-modules/eks/aws`), null if the
  cluster is defined with raw `aws_eks_cluster` resources rather than a module.
- `module_version` = the `version` value on that module block, null if unpinned or raw resources.

**State backend detection — grep the backend block in *.tf and populate `state_backend`:**
```bash
# s3 | remote | local — matches the `backend "<type>"` line inside a terraform {} block
grep -rhoE 'backend "(s3|remote|local)"' --include="*.tf" . 2>/dev/null | head -3
```
Map the matched type to the `state_backend` enum (`s3` | `remote` | `local`). No `backend`
block present ⇒ implicit local state ⇒ record `state_backend: local`.

**Terraform state check (optional) - Use this to verify if Terraform has been applied:**
```bash
# Check if state exists
find . -name "terraform.tfstate" -o -name ".terraform" -type d 2>/dev/null | head -3
```

**OpenTofu vs Terraform:** both produce a `.terraform.lock.hcl` dependency lockfile. The
lockfile alone does not distinguish the two. Check for OpenTofu-specific usage:
```bash
# OpenTofu lockfile present (shared name with Terraform)
find . -name ".terraform.lock.hcl" -type f 2>/dev/null | head -3

# tofu CLI available / tofu-specific state or wrapper usage
command -v tofu 2>/dev/null
grep -rl "tofu" --include="*.tf" --include="*.hcl" . 2>/dev/null | head -3
```
Record `opentofu_detected: bool` when `tofu` usage is found; otherwise the `.tf` files are
attributed to Terraform.

### 2. CloudFormation Detection

Check for CloudFormation templates when Terraform is not found, or when the organization uses AWS-native tooling.

```bash
# Find CFN templates with EKS resources.
# Match AWS::EKS:: only — the old AWSTemplateFormatVersion OR-branch matched EVERY CFN
# template (any service), so it over-reported EKS IaC. No head cap on the file list.
grep -rlE "AWS::EKS::" --include="*.yaml" --include="*.yml" --include="*.json" . 2>/dev/null | head -10
```

**Example output:**
```
./cloudformation/eks-cluster.yaml
./templates/infrastructure.yaml
```

**Check for deployed stacks (if cluster name known) - This confirms the stack was actually deployed:**
```bash
# List stacks with EKS resources
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `eks`) || contains(StackName, `EKS`)].StackName'
```

**Example output:**
```json
[
    "eks-production-cluster",
    "eks-nodegroup-stack"
]
```

### 3. CDK Detection

Check for AWS CDK projects when the codebase uses TypeScript, Python, or other CDK-supported languages. CDK is common in organizations with strong development practices.

```bash
# Check for CDK project - cdk.json is the definitive marker
find . -name "cdk.json" -type f 2>/dev/null | head -3

# Check for CDK in package.json (TypeScript/JavaScript)
find . -name "package.json" -type f 2>/dev/null | head -10 | \
  xargs grep -l "aws-cdk\|@aws-cdk" 2>/dev/null | head -5

# Check for CDK in requirements.txt (Python)
find . -name "requirements.txt" -type f 2>/dev/null | head -5 | \
  xargs grep -l "aws-cdk" 2>/dev/null | head -3

# Check for cdk.out (synthesized templates) - indicates CDK has been synthesized
find . -name "cdk.out" -type d 2>/dev/null | head -3
```

**Example output:**
```
./infra/cdk.json
./infra/package.json
./infra/cdk.out
```

### 4. eksctl Detection

Check for eksctl when the cluster was created for development, testing, or quick deployments. eksctl is commonly used for simpler cluster setups.

```bash
# Find eksctl cluster configs
find . \( -name "eksctl*.yaml" -o -name "eksctl*.yml" -o -name "cluster*.yaml" -o -name "cluster*.yml" \) \
  -type f 2>/dev/null | head -10 | \
  xargs grep -l "kind:\s*ClusterConfig\|apiVersion:\s*eksctl.io" 2>/dev/null | head -5
```

**Example output:**
```
./eksctl-config.yaml
./clusters/dev-cluster.yaml
```

**Verify with eksctl CLI (if available) - Confirms eksctl can manage this cluster:**
```bash
# Check if eksctl recognizes the cluster
eksctl get cluster --name <cluster-name> --region <region> 2>/dev/null
```

**Example output:**
```
NAME                REGION          EKSCTL CREATED
my-dev-cluster      us-west-2       True
```

**Live tag check — eksctl stamps clusters with the `alpha.eksctl.io/cluster-name` tag:**
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.tags."alpha.eksctl.io/cluster-name"' --output text 2>/dev/null
```
Presence of `alpha.eksctl.io/cluster-name` (value equals the cluster name) ⇒ record
`eksctl_created: true`. Absence returns `None` ⇒ `eksctl_created: false`.

### 5. Pulumi Detection

Check for Pulumi when the organization uses infrastructure-as-real-code with TypeScript, Python, or Go. Pulumi is less common than Terraform but growing in adoption.

```bash
# Find Pulumi project files - Pulumi.yaml is the definitive marker
find . -name "Pulumi.yaml" -type f 2>/dev/null | head -3

# Check for AWS provider in Pulumi
find . -name "Pulumi.*.yaml" -type f 2>/dev/null | head -5 | \
  xargs grep -l "aws:" 2>/dev/null | head -3

# Check for EKS in Pulumi code
find . \( -name "*.ts" -o -name "*.py" -o -name "*.go" \) -type f 2>/dev/null | head -50 | \
  xargs grep -l "eks.Cluster\|pulumi_eks\|@pulumi/eks" 2>/dev/null | head -5
```

**Example output:**
```
./pulumi/Pulumi.yaml
./pulumi/Pulumi.production.yaml
./pulumi/index.ts
```

### 6. Crossplane and ACK Detection

Detect in-cluster IaC control planes. Crossplane and AWS Controllers for Kubernetes (ACK)
manage AWS infrastructure from inside the cluster via CRDs, often applied through GitOps.

**Crossplane — check for compositions / composite resource definitions:**
```bash
# Compositions present ⇒ Crossplane installed
kubectl get compositions 2>/dev/null

# Composite Resource Definitions (XRDs)
kubectl get compositeresourcedefinitions.apiextensions.crossplane.io 2>/dev/null

# Crossplane controller / core CRDs
kubectl get crds 2>/dev/null | grep crossplane.io
```

**ACK — check for the service-controller CRD group `services.k8s.aws`:**
```bash
# Any ACK controller registers CRDs under *.services.k8s.aws (e.g. eks.services.k8s.aws)
kubectl get crds 2>/dev/null | grep services.k8s.aws
```

Record `crossplane.detected: bool` (compositions or crossplane.io CRDs present) and
`ack.detected: bool` (any `services.k8s.aws` CRD present). For ACK, record the matched
CRD groups (e.g. `eks.services.k8s.aws`, `iam.services.k8s.aws`) in `ack.controllers`.

### 7. Tag-Based Detection (Fallback)

Use tag-based detection when workspace scan finds nothing. IaC tools often add identifying tags to the resources they create.

**MCP:**
```
describe_eks_resource(
  resource_type="cluster",
  cluster_name="<cluster-name>"
)
-> Check response for cluster.tags
```

**CLI:**
```bash
aws eks describe-cluster --name <cluster-name> \
  --query 'cluster.tags' --output json
```

**Example output (Terraform-managed cluster):**
```json
{
    "Environment": "production",
    "terraform": "true",
    "managed-by": "terraform"
}
```

**Example output (CloudFormation-managed cluster):**
```json
{
    "aws:cloudformation:stack-name": "eks-production-cluster",
    "aws:cloudformation:stack-id": "arn:aws:cloudformation:us-west-2:123456789012:stack/eks-production-cluster/abc123",
    "aws:cloudformation:logical-id": "EKSCluster"
}
```

**Common IaC tags:**
- Terraform: `terraform`, `tf-*`, `managed-by: terraform`
- CloudFormation: `aws:cloudformation:stack-name`
- CDK: `aws:cdk:*`
- Pulumi: `pulumi:*`

---

## Output Schema

This is the **single canonical schema** for the IaC module — it carries every IaC fact.
The `iac-recon` agent emits exactly this shape (plus the shared `cluster:` block from
`references/cluster-basics.md`). Use `null` where a fact was not detected; never omit a key.

```yaml
iac:
  tools_detected: list    # ALL IaC tools with evidence, flat — no "primary". e.g. ["terraform","cdk"]
                          # (Terraform | CloudFormation | CDK | eksctl | Pulumi | Crossplane | ACK | CLI | unknown)
  confidence: string      # high | medium | low — evidence-strength metadata (fact), not a verdict
  evidence:               # object form (canonical)
    type: string          # workspace_files | cluster_tags | cfn_stacks | in_cluster_crds
    details: string       # what was found (paths / reason for determination)

  workspace:
    # Terraform / OpenTofu
    terraform:
      detected: bool
      files: list             # paths to .tf files
      module_source: string   # e.g. "terraform-aws-modules/eks/aws", null if raw resources
      module_version: string  # version pinned on the module block, null if unpinned/raw
      state_backend: string   # s3 | remote | local
      opentofu_detected: bool # tofu CLI / tofu-specific usage found

    # CloudFormation
    cloudformation:
      detected: bool
      templates: list         # paths to CFN templates (matched AWS::EKS::)
      stack_name: string      # deployed stack name (if found)

    # CDK
    cdk:
      detected: bool
      language: string        # typescript | python | java | go
      cdk_json_path: string

    # eksctl
    eksctl:
      detected: bool
      config_files: list

    # Pulumi
    pulumi:
      detected: bool
      project_path: string
      language: string        # typescript | python | go

    # Crossplane (in-cluster control plane)
    crossplane:
      detected: bool

    # AWS Controllers for Kubernetes (ACK)
    ack:
      detected: bool
      controllers: list       # matched services.k8s.aws CRD groups, e.g. ["eks.services.k8s.aws"]

  tags:
    terraform_managed: bool
    eksctl_created: bool      # alpha.eksctl.io/cluster-name tag present
    cfn_stack_id: string      # aws:cloudformation:stack-id tag, null if absent
```

---

## Confidence Determination

| Scenario | Confidence | Reasoning |
|----------|------------|-----------|
| IaC files found with matching cluster name | High | Direct evidence |
| IaC files found, cluster name in tfvars/config | High | Indirect but strong |
| IaC files found, no cluster name match | Medium | Files exist but may be different cluster |
| Only cluster tags suggest IaC | Low | Tags can be manually added |
| No evidence found | Unknown | Might be CLI-created or IaC elsewhere |

---

## Edge Cases

### Multiple IaC Tools Detected

If multiple tools are found (e.g., Terraform + CDK):
- Report ALL detected tools flatly in `tools_detected` — do not pick a "primary" or rank
  them by likelihood, and do not ask the user to clarify. Presence of each tool is the fact.
- Each tool's per-tool `detected` flag and evidence appear in `workspace`.

### IaC in Different Directory

User may have IaC in a separate repo or directory:
- Note that scan is workspace-limited
- Suggest user point to IaC directory if known

### GitOps-Managed IaC

IaC may be applied via GitOps (ArgoCD/Flux deploying Crossplane or ACK). This is detected
by section 6 (Crossplane and ACK Detection): record `workspace.crossplane.detected` /
`workspace.ack.detected` and add `Crossplane` / `ACK` to `tools_detected` when present.

### No IaC (CLI-Created)

If no IaC evidence found:
- Cluster may have been created via `aws eks create-cluster` or console
- Record `tool: CLI/Console` as a fact (no IaC detected). State the fact only; draw no conclusion.
