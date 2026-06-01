---
title: "Addon Catalog"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/addon-catalog.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-build/references/addon-catalog.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/addon-catalog.md). Edit the source, not this page.
:::

# Addon Catalog

All addons supported by this framework, organized by category. Each addon is toggled via YAML configuration -- no Terraform code changes required.

## Addon Summary Table

| Category | Addon | Config Key | Pattern 1 | Pattern 2 | Default | Auth |
|---|---|---|---|---|---|---|
| **EKS Managed** | VPC CNI | `eks_addons.vpc-cni` | Terraform | Terraform | On | Node role |
| | CoreDNS | `eks_addons.coredns` | Terraform | Terraform | On | Node role |
| | kube-proxy | `eks_addons.kube-proxy` | Terraform | Terraform | On | Node role |
| | EBS CSI Driver | `eks_addons.aws-ebs-csi-driver` | Terraform | Terraform | On | Pod Identity |
| | EFS CSI Driver | `eks_addons.aws-efs-csi-driver` | Terraform | Terraform | Off | Pod Identity |
| | Pod Identity Agent | `eks_addons.eks-pod-identity-agent` | Terraform | Terraform | On | Node role |
| **Networking** | AWS LB Controller | `aws_load_balancer_controller` | Terraform | ArgoCD | On | IRSA |
| | ingress-nginx | `ingress_nginx` | Terraform | ArgoCD | Off | -- |
| | External DNS | `external_dns` | Terraform | ArgoCD | Off | IRSA |
| | Gateway API Controller | `aws_gateway_api_controller` | Terraform | ArgoCD | Off | IRSA |
| **Autoscaling** | Cluster Autoscaler | `cluster_autoscaler` | Terraform | ArgoCD | On | IRSA |
| | Karpenter | `karpenter` (dedicated submodule) | Terraform | ArgoCD | Off | Pod Identity |
| | Metrics Server | `metrics_server` | Terraform | ArgoCD | On | -- |
| **Security** | cert-manager | `cert_manager` | Terraform | ArgoCD | Off | -- |
| | External Secrets | `external_secrets` | Terraform | ArgoCD | Off | IRSA |
| | Gatekeeper | `gatekeeper` | Terraform | ArgoCD | Off | -- |
| | Kyverno | `kyverno` | Terraform | ArgoCD | Off | -- |
| **Observability** | CloudWatch Metrics | `cloudwatch_metrics` | Terraform | -- | Off | IRSA |
| | Fluent Bit | `fluentbit` | Terraform | -- | Off | IRSA |
| | Prometheus | `prometheus` | Terraform | -- | Off | -- |
| **Storage** | FSx CSI Driver | `fsx_csi` | Terraform | -- | Off | Pod Identity |
| **Backup** | Velero | `velero` | Terraform | ArgoCD | Off | IRSA/PodId |
| **Capabilities** | ACK | `capabilities.ack` | Terraform | Terraform | Off | IAM role |
| | KRO | `capabilities.kro` | Terraform | Terraform | Off | -- |
| **Custom** | Prisma Cloud | `custom_addons.prisma_defender` | Terraform | ArgoCD* | Off | -- |
| | New Relic | `custom_addons.new_relic` | Terraform | ArgoCD* | Off | -- |
| | Flux CD | `custom_addons.flux` | Terraform | ArgoCD* | Off | -- |
| | Multus CNI | `custom_addons.multus` | Terraform | ArgoCD* | Off | -- |
| | AWS PCA Issuer | `custom_addons.pca_issuer` | Terraform | ArgoCD* | Off | IRSA |

\* In Pattern 2, custom addons deploy via `gitops/custom-addons/` directory-based ApplicationSet.

## EKS Managed Addons

Deployed through the EKS API (not Helm), managed identically in both patterns. Configure under `eks_addons` in `addons.yaml`:

```yaml
eks_addons:
  vpc-cni:
    most_recent: true
    before_compute: true          # MANDATORY -- prevents NodeCreationFailure
  coredns:
    most_recent: true
  kube-proxy:
    most_recent: true
  aws-ebs-csi-driver:
    most_recent: true
  aws-efs-csi-driver:
    most_recent: true
  eks-pod-identity-agent:
    most_recent: true
    before_compute: true          # MANDATORY -- for Pod Identity workloads
```

### before_compute Requirements

| Addon | Needs before_compute | Reason |
|-------|---------------------|--------|
| vpc-cni | **Yes** | Nodes need CNI for Pod IPs and health checks |
| eks-pod-identity-agent | **Yes** | Pods need agent DaemonSet for Pod Identity |
| coredns | No | DNS runs as Deployment; nodes work without it initially |
| kube-proxy | No | Iptables rules set up on node join |
| aws-ebs-csi-driver | No | Storage driver only needed when PVCs are created |

### Pod Identity for EKS Managed Addons

EKS managed addons (EBS CSI, EFS CSI, FSx CSI, Mountpoint S3 CSI, CloudWatch) use **Pod Identity** instead of IRSA. IAM roles are created by `terraform-aws-modules/eks-pod-identity/aws` modules. Associations are **separate `aws_eks_pod_identity_association` resources** -- not inline in addon config.

**Why separate resources (not inline `pod_identity_association`):**
1. Terraform v1.14's strict `for_each` rejects unknown module outputs in the upstream EKS module's filter expression
2. Separate resources create correct destroy ordering -- associations destroyed before IAM roles

```hcl
# IAM role (no association -- created separately)
module "ebs_csi_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "<LOOK_UP>"  # Look up latest from Terraform Registry
  name            = "${local.cluster_config.name}-ebs-csi"
  use_name_prefix = false
  attach_aws_ebs_csi_policy  = true
  aws_ebs_csi_policy_name    = "${local.cluster_config.name}-EBS_CSI"  # Avoid cross-project collision
  tags = local.tags
}

# Separate association (depends on both cluster and IAM role)
resource "aws_eks_pod_identity_association" "ebs_csi" {
  cluster_name    = module.eks_cluster.cluster_name
  namespace       = "kube-system"
  service_account = "ebs-csi-controller-sa"
  role_arn        = module.ebs_csi_pod_identity[0].iam_role_arn
}
```

## Blueprints Addons (Pattern 1)

The `aws-ia/eks-blueprints-addons` module deploys these as Helm releases. Each addon has an `enabled` flag and optional `config` block:

```yaml
aws_load_balancer_controller:
  enabled: true
  config:
    wait: true                     # Required for Phase 1 webhook ordering
    chart_version: "<LOOK_UP>"     # Always override module default
    set:
      - name: vpcId
        value: "vpc-0abc123"       # Explicit -- IMDS fallback can fail
      - name: replicaCount
        value: "2"
```

### Critical: Two-Phase Module Architecture

LBC and Gatekeeper must deploy in Phase 1 (with `wait: true`) before all other addons in Phase 2. See [lessons-learned.md](lessons-learned) for details.

## ArgoCD-Managed Addons (Pattern 2)

Addon enable flags pass to ArgoCD via the GitOps Bridge metadata secret. ArgoCD reads `enable_<addon_name>` annotations and conditionally creates Helm Applications.

**Karpenter in Pattern 2 (validated):** Terraform creates the IAM roles and Pod Identity associations via the dedicated submodule. The Helm chart deploys via ArgoCD Application (OCI chart: `oci://public.ecr.aws/karpenter/karpenter`). NodePool/EC2NodeClass CRDs can be deployed via a custom-addons chart. Discovery tags must be applied by Terraform before ArgoCD syncs.

```yaml
addons:
  aws_load_balancer_controller:
    enabled: true
  metrics_server:
    enabled: true
  cluster_autoscaler:
    enabled: true
```

### Tenant Workloads (Pattern 2)

Tenants use a Kustomize-based ApplicationSet with a Git Directory Generator that auto-discovers tenant overlay directories (`gitops/tenants/*/overlays/*`). Each tenant gets its own AppProject for RBAC isolation.

## Custom Addons

### Prisma Cloud Defender

Runtime container security agent from Palo Alto Networks.

```yaml
custom_addons:
  prisma_defender:
    enabled: true
    chart: twistlock-defender
    chart_version: "<LOOK_UP>"
    repository: "https://<REGISTRY_URL>"
    namespace: twistlock
```

### New Relic

Infrastructure monitoring bundle (K8s integration, Prometheus agent, logging).

```yaml
custom_addons:
  new_relic:
    enabled: true
    chart: nri-bundle
    chart_version: "<LOOK_UP>"     # Look up from https://artifacthub.io/packages/helm/newrelic/nri-bundle
    repository: https://helm-charts.newrelic.com
    namespace: newrelic
    set:
      - name: global.licenseKey
        value: "<YOUR_LICENSE_KEY>"
```

### Flux CD

GitOps toolkit. Installs Flux controllers; configure GitRepository and Kustomization CRDs separately.

```yaml
custom_addons:
  flux:
    enabled: true
    chart: flux2
    chart_version: "<LOOK_UP>"     # Look up from https://artifacthub.io/packages/helm/fluxcd-community/flux2
    repository: https://fluxcd-community.github.io/helm-charts
    namespace: flux-system
```

### Multus CNI -- BROKEN

**Do NOT enable.** Thick-plugin has a pod-lookup race condition that blocks ALL new pod creation.

```yaml
custom_addons:
  multus:
    enabled: false  # BROKEN: thick-plugin pod-lookup race
```

### AWS PCA Issuer

Bridges cert-manager with AWS Private Certificate Authority for org-trusted TLS.

```yaml
custom_addons:
  pca_issuer:
    enabled: true
    chart: aws-privateca-issuer
    chart_version: "<LOOK_UP>"     # Look up from https://artifacthub.io/packages/helm/cert-manager/aws-privateca-issuer
    repository: https://cert-manager.github.io/aws-privateca-issuer
    namespace: cert-manager
    service_account_role_arn: "arn:aws:iam::<ACCOUNT_ID>:role/pca-issuer-role"
    cluster_issuer_arn: "arn:aws:acm-pca:<REGION>:<ACCOUNT_ID>:certificate-authority/<CA_ID>"
    cluster_issuer_name: pca-cluster-issuer
```

## Adding a New Custom Addon

### Pattern 1 (Terraform)

1. Add a module block in `modules/custom-addons/main.tf`:

```hcl
module "my_addon" {
  count   = try(var.custom_addons_config.my_addon.enabled, false) ? 1 : 0
  source  = "aws-ia/eks-blueprints-addon/aws"
  version = "<LOOK_UP>"  # Look up from Terraform Registry

  chart            = try(var.custom_addons_config.my_addon.chart, "my-addon")
  chart_version    = try(var.custom_addons_config.my_addon.chart_version, "<LOOK_UP>")
  repository       = try(var.custom_addons_config.my_addon.repository, "https://charts.example.com")
  namespace        = try(var.custom_addons_config.my_addon.namespace, "my-addon")
  create_namespace = true

  values = try(var.custom_addons_config.my_addon.values, [])
  set    = try(var.custom_addons_config.my_addon.set, [])
  tags   = var.tags
}
```

2. Add config in `addons.yaml`:

```yaml
custom_addons:
  my_addon:
    enabled: true
    chart: my-addon
    chart_version: "<LOOK_UP>"
    repository: "https://charts.example.com"
    namespace: my-addon
```

### Pattern 2 (ArgoCD)

1. Create `gitops/custom-addons/charts/my-addon/` with `Chart.yaml` + `values.yaml`.
2. The directory-based ApplicationSet auto-discovers and deploys it.
