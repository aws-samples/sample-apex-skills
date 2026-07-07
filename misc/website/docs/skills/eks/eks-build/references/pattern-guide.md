---
title: "EKS Infrastructure Pattern Comparison and Selection Guide"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/pattern-guide.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-build/references/pattern-guide.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/pattern-guide.md). Edit the source, not this page.
:::

# EKS Infrastructure Pattern Comparison and Selection Guide

## Table of Contents

- [Pattern Overview](#pattern-overview)
- [Decision Matrix](#decision-matrix)
- [Pattern 1: Full Terraform](#pattern-1-full-terraform)
- [Pattern 2a: ArgoCD + Terraform AWS](#pattern-2a-argocd--terraform-aws)
- [Pattern 2b: ArgoCD + ACK/KRO](#pattern-2b-argocd--ackkro)
- [Pattern 3: ArgoCD Cluster Creation (Placeholder)](#pattern-3-argocd-cluster-creation-placeholder)
- [Trade-offs](#trade-offs)
- [Migration Paths](#migration-paths)
- [Shared Infrastructure](#shared-infrastructure)

## Pattern Overview

| Pattern | Name | Addon Deployment | AWS Resource Addons | Status |
|---------|------|-----------------|---------------------|--------|
| 1 | Full Terraform | Terraform Helm releases via `eks-blueprints-addons` | Terraform resources (S3, IAM) | Validated |
| 2a | ArgoCD + Terraform AWS | ArgoCD ApplicationSets | Terraform via `eks-blueprints-addons` (IRSA only) | Validated |
| 2b | ArgoCD + ACK/KRO | ArgoCD ApplicationSets | ACK CRDs + KRO | Validated |
| 3 | ArgoCD Cluster Creation | ArgoCD manages everything | ArgoCD + ACK for cluster lifecycle | Placeholder |

## Decision Matrix

| Criteria | Pattern 1 | Pattern 2a | Pattern 2b | Pattern 3 |
|----------|-----------|------------|------------|-----------|
| GitOps maturity required | None | Moderate | High | Very High |
| AWS resource management | Terraform only | Terraform (IRSA) + ArgoCD (Helm) | ACK CRDs in-cluster | ACK for everything |
| Operational complexity | Low | Medium | Medium-High | High |
| Air-gapped support | Best | Good | Good | Unvalidated |
| Multi-cluster scale | Per-cluster Terraform | Single ArgoCD hub | Same as 2a | Full fleet |
| Drift detection | `terraform plan` only | ArgoCD self-heal + `terraform plan` | ArgoCD self-heal + ACK reconciliation | ArgoCD self-heal |
| Day-2 addon upgrades | Terraform PR + apply | Git commit to chart version | Git commit to chart version | Git commit |
| Team skill requirement | Terraform | Terraform + ArgoCD + Helm | Terraform + ArgoCD + ACK + KRO | ArgoCD + ACK |

**Use Pattern 1** when the team is Terraform-native, needs deterministic `plan`/`apply` cycles, or operates in strict change-management environments.

**Use Pattern 2a** when the team wants GitOps for addon lifecycle but prefers Terraform for AWS IAM resources (IRSA roles).

**Use Pattern 2b** when the team wants Kubernetes-native AWS resource management via ACK CRDs, reducing Terraform surface area.

**Use Pattern 3** (future) when full cluster lifecycle management through ArgoCD and ACK is desired.

## Pattern 1: Full Terraform

### Architecture

Terraform manages the entire stack: VPC, EKS cluster, EKS managed addons, Helm-based addons (via `eks-blueprints-addons`), IRSA roles, and AWS resources like S3 buckets.

### Two-Phase Module Architecture

Addons that register webhooks with `failurePolicy: Fail` must be fully running before other addons attempt to create Services or Namespaces:

- **Phase 1 (`eks_addons_webhooks`)**: Deploys only AWS Load Balancer Controller and Gatekeeper with `wait: true`.
- **Phase 2 (`eks_addons`)**: Deploys all remaining addons with `depends_on` on Phase 1. LBC and Gatekeeper set to `enabled = false` in Phase 2.

Both phases use `aws-ia/eks-blueprints-addons/aws` (look up latest version from Terraform Registry).

### before_compute for Critical Addons

EKS managed addons `vpc-cni` and `eks-pod-identity-agent` set `before_compute: true` to ensure they are active before node groups launch.

### Karpenter (When Selected)

Uses dedicated `terraform-aws-modules/eks/aws//modules/karpenter` submodule. See [baseline-defaults.md](baseline-defaults) for NodePool/EC2NodeClass defaults and [lessons-learned.md](lessons-learned) Section 17.

### AWS Resource Management

Terraform directly creates AWS resources (Velero S3 bucket, etc.). The `eks-blueprints-addons` module handles IRSA role creation. EKS managed addons use **Pod Identity** with separate `aws_eks_pod_identity_association` resources -- see [lessons-learned.md](lessons-learned) Section 15.

## Pattern 2a: ArgoCD + Terraform AWS

### Architecture

Terraform creates the EKS cluster, EKS managed addons, IRSA roles, and the ArgoCD EKS Capability. ArgoCD deploys all Helm-based addons via ApplicationSets.

### ArgoCD EKS Capability

ArgoCD is deployed as a fully managed AWS EKS Capability (`type = "ARGOCD"`), rather than a self-managed Helm release. Authentication uses AWS Identity Center (SSO) with group-based RBAC mapping.

### GitOps Bridge Pattern

Terraform creates a Kubernetes secret in the `argocd` namespace with label `argocd.argoproj.io/secret-type: cluster`. This secret carries:

- Cluster identity: `cluster_name`, `aws_region`, `aws_account_id`, `vpc_id`
- IRSA role ARNs from `module.eks_blueprints_addons.gitops_metadata`
- Addon enable flags: `enable_aws_load_balancer_controller`, `enable_velero`, etc.
- GitOps repo coordinates: `gitops_repo_url`, `gitops_repo_path`, `gitops_repo_revision`

The secret `server` field is set to the cluster ARN (not `https://kubernetes.default.svc`).

### IRSA via eks-blueprints-addons

The module is called with `create_kubernetes_resources = false` -- creates only IAM roles without deploying Helm charts. The `gitops_metadata` output provides all IRSA ARNs for the GitOps Bridge secret.

### ApplicationSets with Go Templates

The `cluster-addons` ApplicationSet uses a matrix generator combining the cluster secret selector with a static addon list. Go templates with `missingkey=zero` inject per-addon Helm values from cluster secret annotations.

## Pattern 2b: ArgoCD + ACK/KRO

### Architecture

Same base as Pattern 2a, but AWS resources that would normally be Terraform-managed are instead created by ACK controllers running as EKS Capabilities. KRO provides custom resource composition.

### ACK for AWS Resources

The ACK EKS Capability provisions AWS resources via Kubernetes CRDs. For example, the `velero-infra` custom addon chart contains an ACK `Bucket` resource that creates the Velero S3 backup bucket.

### Pod Identity for Velero

Pattern 2b uses Pod Identity for Velero (not IRSA). Terraform creates the IAM role with `pods.eks.amazonaws.com` as trusted principal and a `aws_eks_pod_identity_association`.

### KRO Capability

KRO provides Kubernetes Resource Orchestration for composing higher-level abstractions from ACK and native resources. KRO needs no IAM permissions; it operates through Kubernetes RBAC.

## Pattern 3: ArgoCD Cluster Creation (Placeholder)

This pattern extends Pattern 2b so that ArgoCD manages the full cluster lifecycle through ACK. Not yet validated.

### Conceptual Architecture

- A management cluster runs ArgoCD and ACK controllers
- Workload clusters are defined as ACK `Cluster` CRDs in the GitOps repository
- ArgoCD syncs cluster definitions, ACK provisions them
- Terraform scope is reduced to the management cluster and foundational networking only

## Trade-offs

| Dimension | Pattern 1 | Pattern 2a/2b | Pattern 3 |
|-----------|-----------|---------------|-----------|
| State management | Terraform state only | Terraform + ArgoCD desired state | ArgoCD only |
| Blast radius of bad merge | Full cluster | Addons only (ArgoCD); infra separate | Everything |
| Rollback speed | `terraform apply` from previous state | ArgoCD auto-revert via self-heal | ArgoCD auto-revert |
| Secret handling | Terraform variables/Vault | GitOps Bridge annotations (no secrets in Git) | Annotations + ACK |
| Testing | `terraform plan` | `terraform plan` + ArgoCD diff preview | ArgoCD diff preview |

## Migration Paths

### Pattern 1 to Pattern 2a

1. Add ArgoCD EKS Capability module and GitOps Bridge secret to Terraform config
2. Re-run `eks-blueprints-addons` with `create_kubernetes_resources = false`
3. Create the `cluster-addons` ApplicationSet matching current chart versions
4. Apply Terraform to create ArgoCD capability and GitOps Bridge
5. Remove Phase 1/Phase 2 Helm deployment blocks from Terraform

### Pattern 2a to Pattern 2b

1. Enable ACK and KRO EKS Capabilities
2. Create custom addon charts containing ACK CRD manifests
3. Switch from IRSA to Pod Identity for addons interacting with ACK-managed resources
4. Add custom-addons ApplicationSet to GitOps repository
5. Remove equivalent Terraform resources after ACK resources are healthy

### Pattern 2b to Pattern 3 (Future)

1. Provision a management cluster with ArgoCD and ACK capabilities
2. Define EKS cluster configuration as ACK CRDs in GitOps repository
3. Create ArgoCD Application managing the cluster CRD
4. Validate cluster creation, upgrade, and deletion workflows
5. Gradually move workload clusters from Terraform-managed to ACK-managed

## Shared Infrastructure

All patterns share:

- **EKS cluster module**: `terraform-aws-modules/eks/aws` with API-based access, KMS encryption, private endpoint
- **EKS managed addons**: vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver, eks-pod-identity-agent with `before_compute` ordering. Pod Identity via separate association resources.
- **Platform namespaces**: Pod Security Standards labels + default-deny NetworkPolicy
- **EKS Capabilities**: ACK and KRO available in all patterns via capability submodule
