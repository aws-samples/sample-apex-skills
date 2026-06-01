# Lessons Learned: EKS Deployment Patterns

## Table of Contents

- [1. before_compute Is Mandatory](#1-before_compute-is-mandatory)
- [2. Two-Phase Module Architecture](#2-two-phase-module-architecture)
- [3. Addon Version Pinning](#3-addon-version-pinning)
- [4. Multus CNI Is BROKEN](#4-multus-cni-is-broken)
- [5. Kyverno Gotchas](#5-kyverno-gotchas)
- [6. ArgoCD EKS Capability](#6-argocd-eks-capability)
- [7. GitOps Bridge Pattern](#7-gitops-bridge-pattern)
- [8. IRSA vs Pod Identity](#8-irsa-vs-pod-identity)
- [9. Velero Configuration](#9-velero-configuration)
- [10. ACK and KRO](#10-ack-and-kro)
- [11. Deployment Order](#11-deployment-order)
- [12. Use HashiCorp Terraform, NOT OpenTofu](#12-use-hashicorp-terraform-not-opentofu)
- [13. Terraform Operational Notes](#13-terraform-operational-notes)
- [14. Automated Validation Findings](#14-automated-validation-findings)
- [15. Pod Identity Destroy Ordering](#15-pod-identity-destroy-ordering)
- [16. EFS CSI Driver Operational Notes](#16-efs-csi-driver-operational-notes)
- [17. Karpenter Dedicated Submodule](#17-karpenter-dedicated-submodule)
- [18. Pod Identity IAM Policy Name Collision](#18-pod-identity-iam-policy-name-collision)
- [19. ArgoCD Namespace Race Condition](#19-argocd-namespace-race-condition)
- [20. EKS Capability Destroy Hangs Terraform](#20-eks-capability-destroy-hangs-terraform)
- [21. CIS Policies Cannot Be Deployed as Helm Chart](#21-cis-policies-cannot-be-deployed-as-helm-chart)
- [22. Pattern 2a Custom-Addons Require Real Git Repo](#22-pattern-2a-custom-addons-require-real-git-repo)

Consolidated findings from two EKS deployment patterns:
- **Pattern 1 (terraform-eks)**: Full Terraform with eks-blueprints-addons, two-phase module architecture
- **Pattern 2 (argocd-eks)**: ArgoCD EKS Capability + ACK + GitOps Bridge

---

## 1. before_compute Is Mandatory

**Patterns:** Both

vpc-cni and eks-pod-identity-agent MUST have `before_compute: true`. Without it, EKS managed addons and node groups are created in parallel. Nodes finish before the CNI installs, fail health checks with `NodeCreationFailure: NetworkPluginNotReady`, and stay `NotReady`.

```yaml
eks_addons:
  vpc-cni:
    most_recent: true
    before_compute: true
  eks-pod-identity-agent:
    most_recent: true
    before_compute: true
```

**State migration note:** Adding `before_compute: true` to an existing addon moves the Terraform resource key. Use `terraform import` for in-place migration, or do a clean destroy+apply cycle.

---

## 2. Two-Phase Module Architecture

**Patterns:** Pattern 1 only

### Problem

LBC and Gatekeeper register webhooks with `failurePolicy: Fail` before their pods have ready endpoints. The single `eks-blueprints-addons` module deploys all Helm releases in parallel. Other addons hit these webhooks and get rejected.

### Why wait: true alone fails

`wait: true` only blocks when Terraform marks *that resource* as done. It does NOT prevent sibling `helm_release` resources in the same module from starting simultaneously.

### Fix

Split into two module calls:
1. **Phase 1** (`module.eks_addons_webhooks`): LBC + Gatekeeper only, with `wait: true`
2. **Phase 2** (`module.eks_addons`): Everything else, with `depends_on = [module.eks_addons_webhooks]`

Phase 1 also needs `depends_on = [module.eks_cluster]` so all EKS managed addons are ACTIVE before any Helm release starts.

### Trade-off

The module graph is instantiated twice, but with HashiCorp Terraform v1.14.5, plan still completes in under 2 minutes. **Do NOT use OpenTofu** -- see Section 12.

---

## 3. Addon Version Pinning

**Patterns:** Both

### Module defaults are stale

The `eks-blueprints-addons` module ships chart defaults that lag significantly behind current releases. Always look up the latest versions from authoritative sources (see [version-matrix.md](version-matrix.md)).

### Rules

- ALWAYS override chart versions from config YAML; never rely on module defaults
- Versions pinned at plan time go stale by deployment day. Re-verify before every apply.
- **cluster-autoscaler image.tag MUST match EKS K8s minor version**
- **LBC requires explicit vpcId** -- IMDS fallback fails with hop-limit restrictions

---

## 4. Multus CNI Is BROKEN

**Patterns:** Both (currently DISABLED)

- **Thick-plugin pod-lookup race:** Multus queries the K8s API for pod metadata before the pod is registered. ALL new pod creation fails.
- **Impact:** Existing pods survive, but no new pods can start anywhere in the cluster.

### Recovery (if accidentally enabled)

1. SSM to all nodes: `rm -f /etc/cni/net.d/00-multus.conf`
2. Delete DaemonSet: `kubectl delete ds kube-multus-ds -n kube-system`
3. Restart stuck pods, disable in config, re-apply

**Do not enable until upstream fixes the thick-plugin race.**

---

## 5. Kyverno Gotchas

**Patterns:** Both

### Webhook blocks other addons

During install/upgrade, Kyverno's validating webhook has no endpoints while pods start. This blocks pod creation for other addons. If a deployment gets stuck, wait for Kyverno to stabilize, then `kubectl rollout restart` the stuck deployment.

### TLS cert incompatibility on major version upgrades

Fix: delete ALL secrets AND all pods in the kyverno namespace simultaneously:

```bash
kubectl delete secrets --all -n kyverno && kubectl delete pods --all -n kyverno
```

### ArgoCD sync strategy (Pattern 2)

Use `Replace=true` syncOption, NOT `ServerSideApply=true`. SSA conflicts with `selfHeal: true` + `--force`.

---

## 6. ArgoCD EKS Capability

**Patterns:** Pattern 2 only

- Fully managed external service -- no pods in the cluster.
- ArgoCD CRDs are installed automatically; ApplicationSets are applied via `kubectl apply`.
- Use **cluster ARN** as the destination server (not `https://kubernetes.default.svc`).
- AppProjects need `sourceNamespaces: [argocd]`.

### Go templates

- `missingkey=zero` is essential. Without it, any missing annotation fails the entire ApplicationSet.
- Use `index .metadata.annotations "key-name"` for keys with dots or hyphens.

---

## 7. GitOps Bridge Pattern

**Patterns:** Pattern 2 only

Terraform writes cluster metadata to a K8s Secret annotated with `argocd.argoproj.io/secret-type: cluster`. ArgoCD's `clusters` generator reads these annotations and exposes them as template variables in ApplicationSets.

- `eks-blueprints-addons` provides `gitops_metadata` output with all IRSA ARNs, SA names, and namespaces.
- Annotation keys use module-specific names (e.g., `cluster_autoscaler_iam_role_arn`). Always check the module's `gitops_metadata` output for exact key names.

---

## 8. IRSA vs Pod Identity

**Patterns:** Both

| Feature | IRSA | Pod Identity |
|---------|------|-------------|
| Trust policy | OIDC provider URL required | `Service: pods.eks.amazonaws.com` |
| SA annotation | `eks.amazonaws.com/role-arn` required | Not needed |
| Session tagging | Not supported | Auto-tags (cluster, namespace, SA) |
| Prerequisites | OIDC provider | eks-pod-identity-agent addon |

- **Pod Identity is preferred** for new workloads (simpler, better auditing).
- EKS managed addons: use Pod Identity with separate `aws_eks_pod_identity_association` resources -- see Section 15.
- Helm-based addons (LBC, External DNS, Velero): IRSA via eks-blueprints-addons.
- Karpenter: Pod Identity via dedicated submodule -- see Section 17.
- When both are configured for the same SA, **Pod Identity takes precedence**.

---

## 9. Velero Configuration

**Patterns:** Both

Three-part config: S3 bucket + auth (IRSA or Pod Identity) + Helm chart.

| Setting | Value | Reason |
|---------|-------|--------|
| `upgradeCRDs` | `false` | bitnami/kubectl image for latest K8s may not exist |
| `kubectl.image.tag` | Look up latest available | Search Docker Hub for `bitnami/kubectl` tags |
| `credentials.useSecret` | `false` | When using Pod Identity |
| `s3_backup_location` | S3 bucket ARN | Required for IRSA policy |

### CRD name collision

ACK DynamoDB controller installs a `Backup` CRD that conflicts with Velero's. Always use the full API group: `backup.velero.io`.

---

## 10. ACK and KRO

**Patterns:** Both

### ACK

- EKS Capability: no pods in cluster. Creates and reconciles AWS resources from K8s CRs.
- Field naming follows AWS SDK Go convention: `blockPublicACLs` (not `blockPublicAcls`). Always verify against the installed CRD schema.
- Use `services.k8s.aws/deletion-policy=retain` when migrating from ACK-managed to Terraform-managed resources.

### KRO

- EKS Capability available but the controller may not reconcile new `ResourceGraphDefinition` resources in all cases. RGDs may stay `Inactive`.
- **Workaround:** Use ACK resources directly instead of KRO orchestration if RGDs are not activating.

---

## 11. Deployment Order

**Patterns:** Pattern 2

```
1. terraform apply          (cluster, IAM, capabilities, GitOps Bridge secret)
2. kubectl apply            argocd-projects.yaml
3. kubectl apply            addons applicationset.yaml
4. kubectl apply            custom-addons applicationset.yaml
5. kubectl apply            tenants applicationset.yaml
```

For Pattern 1, a single `terraform apply` handles everything (two-phase module architecture manages internal ordering).

---

## 12. Use HashiCorp Terraform, NOT OpenTofu

**Patterns:** Both

### Problem

OpenTofu v1.10.6 has a severe performance regression with `depends_on` module graphs. The two-phase module architecture causes `tofu plan` to take **30+ minutes** (vs < 2 min with Terraform v1.14.5).

### Evidence

| Binary | Version | Plan time (113 resources) | CPU |
|--------|---------|--------------------------|-----|
| OpenTofu | v1.10.6 | 30+ min | 145-177% |
| Terraform | v1.14.5 | < 2 min | Normal |

### Fix

- Use **HashiCorp Terraform v1.14.5+**
- Verify: `terraform --version` must show `Terraform v1.x.x`, NOT `OpenTofu`
- Common gotcha: macOS Homebrew aliases `terraform` to `tofu`. Fix with `brew install hashicorp/tap/terraform && brew link --overwrite terraform`
- After switching: run `terraform init -reconfigure -upgrade` to re-register providers

---

## 13. Terraform Operational Notes

**Patterns:** Both

### depends_on vs implicit references

```
module.eks_cluster.cluster_name    -> waits only for the cluster resource
depends_on = [module.eks_cluster]  -> waits for ALL resources in the module
```

### wait: true scope

Within a single module, `wait: true` on one `helm_release` does NOT delay sibling `helm_release` resources. Ordering requires separate module calls with `depends_on`.

### Deployment Timing (HashiCorp Terraform v1.14.5)

#### Pattern 1: Full Terraform

| Phase | Duration |
|-------|----------|
| `terraform plan` | < 2 min |
| `terraform apply` (total) | ~18 min |
| -- EKS cluster creation | ~9 min |
| -- Node group creation | ~2 min |
| -- Phase 1 (LBC + Gatekeeper) | ~3 min |
| -- Phase 2 (all other addons) | ~4 min |
| `terraform destroy` | ~10 min |

#### Pattern 2: ArgoCD + Terraform

| Phase | Duration |
|-------|----------|
| `terraform apply` (total) | ~16 min |
| -- EKS cluster creation | ~10 min |
| -- ArgoCD EKS Capability | ~5 min |
| -- Remaining (IAM, GitOps Bridge) | ~1 min |
| ArgoCD auto-sync | ~5 min |
| `terraform destroy` | ~15 min |

---

## 14. Automated Validation Findings

**Patterns:** Both

### GuardDuty addon auto-installed

AWS auto-installs `aws-guardduty-agent` when GuardDuty EKS Runtime Monitoring is enabled. Not managed by Terraform. Expect 5 or 6 managed addons depending on GuardDuty config.

### ACK S3 bucket re-deploy handling (Pattern 2)

When running destroy/apply cycles, ACK S3 buckets may persist. On re-deploy, ACK enters `ACK.Terminal` with `Resource already exists`.

**Fix:** Delete the pre-existing bucket before re-deploy:
```bash
aws s3 rb s3://<CLUSTER_NAME>-velero-backups-<ACCOUNT_ID> --force
```

### LBC webhook TLS CA mismatch (Pattern 2) -- ~20% recurrence rate

The LBC Helm chart uses `genCA`/`genSignedCert`. ArgoCD's partial sync can regenerate CA and cert independently, causing `caBundle` mismatch.

**Fix:** Delete stuck ArgoCD apps -- ApplicationSet recreates them:
```bash
kubectl delete application aws-load-balancer-controller gatekeeper -n argocd
```

### external-secrets startup latency

The cert-controller and webhook pods show `0/1 Ready` for ~90 seconds. This is normal startup behavior during initial certificate generation.

---

## 15. Pod Identity Destroy Ordering

**Patterns:** Pattern 1

### Problem

When Pod Identity IAM roles are created by separate modules and role ARNs are passed to the EKS addon config, `terraform destroy` may delete IAM roles before the addons that reference them.

### Fix

Create Pod Identity associations as **separate `aws_eks_pod_identity_association` resources**:

```hcl
resource "aws_eks_pod_identity_association" "ebs_csi" {
  cluster_name    = module.eks_cluster.cluster_name
  namespace       = "kube-system"
  service_account = "ebs-csi-controller-sa"
  role_arn        = module.ebs_csi_pod_identity[0].iam_role_arn
}
```

This creates correct dependency graph: Create (role -> addon -> association), Destroy (association first -> role and addon in parallel).

---

## 16. EFS CSI Driver Operational Notes

**Patterns:** Both

### DNS propagation delay

After creating EFS mount targets, DNS resolution takes ~5 minutes to propagate. Pods mounting EFS immediately will fail with `Failed to resolve`.

### Security groups

EFS mount targets must allow NFS (TCP 2049) inbound from the node security group.

### TLS on arm64

The `efs-proxy` binary does not work reliably on arm64 Karpenter-provisioned nodes. **Workaround:** use `nodeSelector: kubernetes.io/arch: amd64` for pods that require EFS TLS.

### EFS access points

Non-root containers cannot write to root-owned EFS directories. Create an EFS access point with `PosixUser` and `CreationInfo` set to the container's uid/gid.

---

## 17. Karpenter Dedicated Submodule

**Patterns:** Both (validated)

### Why not eks-blueprints-addons

The `eks-blueprints-addons` Karpenter integration has issues: stale chart default, missing CRDs, deprecated settings keys.

### Recommended approach

Use `terraform-aws-modules/eks/aws//modules/karpenter`:

```hcl
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "<LOOK_UP>"  # Look up latest from Terraform Registry
  cluster_name                    = module.eks_cluster.cluster_name
  create_pod_identity_association = true
  node_iam_role_use_name_prefix   = false
  node_iam_role_name              = "${local.cluster_config.name}-karpenter-node"
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
  tags = local.tags
}
```

Then deploy the Helm chart via `helm_release` and NodePool/EC2NodeClass via `kubectl_manifest`. Tag private subnets and cluster primary SG with `karpenter.sh/discovery: <cluster-name>`.

### EC2 Spot Service-Linked Role

Karpenter needs `AWSServiceRoleForEC2Spot`. Create before deploying:
```bash
aws iam create-service-linked-role --aws-service-name spot.amazonaws.com
```

---

## 18. Pod Identity IAM Policy Name Collision

**Patterns:** Both

### Problem

The `terraform-aws-modules/eks-pod-identity/aws` module creates IAM policies with hardcoded default names. Multiple projects in the same account collide.

### Fix

Always set a cluster-prefixed policy name:

```hcl
module "ebs_csi_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.7"
  name            = "${local.cluster_config.name}-ebs-csi"
  use_name_prefix = false
  attach_aws_ebs_csi_policy  = true
  aws_ebs_csi_policy_name    = "${local.cluster_config.name}-EBS_CSI"
  tags = local.tags
}
```

| Addon | Parameter | Example |
|-------|-----------|---------|
| EBS CSI | `aws_ebs_csi_policy_name` | `"${local.cluster_config.name}-EBS_CSI"` |
| EFS CSI | `aws_efs_csi_policy_name` | `"${local.cluster_config.name}-EFS_CSI"` |
| FSx CSI | `aws_fsx_lustre_csi_policy_name` | `"${local.cluster_config.name}-FSx_Lustre_CSI"` |

---

## 19. ArgoCD Namespace Race Condition

**Patterns:** Pattern 2a

### Problem

The ArgoCD EKS Capability creates the `argocd` namespace asynchronously. If the GitOps Bridge secret creation races it, the apply fails.

### Fix

Make the namespace resource conditional -- only create when ArgoCD capability is disabled:

```hcl
resource "kubernetes_namespace_v1" "argocd" {
  count = local.argocd_idc_enabled ? 0 : 1
  metadata { name = local.argocd_namespace }
  depends_on = [module.eks_cluster]
}
```

---

## 20. EKS Capability Destroy Hangs Terraform

**Patterns:** All patterns using EKS Capabilities

**Problem:** The provider's delete operation for capabilities hangs indefinitely during `terraform destroy`.

**Fix:** Add a `null_resource` with destroy-time provisioner that deletes capabilities via the EKS API before Terraform attempts deletion. Include `sleep 180` for ArgoCD capability deletion time.

**Workaround:** Manually delete capabilities via API, remove from state, then destroy:
```bash
terraform state list | grep capability | xargs -I{} terraform state rm {}
terraform destroy -auto-approve
```

---

## 21. CIS Policies Cannot Be Deployed as Helm Chart

**Patterns:** Pattern 2a, 2b

**Problem:** Kyverno CIS policies use JMESPath `{{ }}` delimiters that Helm interprets as Go templates.

**Fix:** Deploy via `kubectl_manifest` resources in the custom-addons Terraform module.

---

## 22. Pattern 2a Custom-Addons Require Real Git Repo

**Patterns:** Pattern 2a

**Problem:** Custom-addons ApplicationSets use ArgoCD's git directory generator, which requires a real, accessible git repository URL.

**Fix:** For resources needed at deploy time (Velero S3, CIS policies), create them in Terraform rather than relying on ArgoCD custom-addons.
