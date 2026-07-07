---
title: "Version Management"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/version-matrix.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-build/references/version-matrix.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/references/version-matrix.md). Edit the source, not this page.
:::

# Version Management

**Do NOT use hardcoded versions.** Always look up current versions from the authoritative sources below before generating code. Pin the verified version in the generated `addons.yaml` or ApplicationSet.

## Version Lookup Process

Before generating a project, look up **every** addon and module version. Never reuse versions from a previous generation -- they go stale.

### How to Look Up Versions

Use these methods in order of preference:

1. **Web search** (recommended) -- Search the internet for the addon name + "latest version" or "helm chart version". Examples:
   - Search: `aws-load-balancer-controller helm chart latest version`
   - Search: `cert-manager latest stable release`
   - Search: `terraform-aws-modules/eks latest version`

2. **ArtifactHub pages** -- Fetch the ArtifactHub URL from the table below for current chart version, app version, and changelog.

3. **GitHub releases** -- For addons not on ArtifactHub (e.g., cluster-autoscaler), check the GitHub releases page.

4. **Terraform Registry** -- For Terraform modules, fetch the registry page.

5. **Helm CLI** (if available) -- Run `helm search repo <chart>` after adding the repo.

### Lookup Rules

- **EKS managed addons**: Use `most_recent: true` in Terraform -- EKS auto-selects compatible versions. No manual lookup needed.
- **Helm chart addons**: Look up each enabled addon's latest stable chart version.
- **cluster-autoscaler**: Image tag MUST match the EKS K8s minor version (e.g., `v1.x.y` for EKS 1.x).
- **Terraform modules**: Check registry for latest compatible version. Use `~>` constraint for minor version flexibility.

## Authoritative Version Sources

Look up current versions here before every project generation:

| Addon | Helm Repo / Source |
|-------|-------------------|
| karpenter | https://github.com/aws/karpenter-provider-aws/releases |
| aws-load-balancer-controller | https://artifacthub.io/packages/helm/aws/aws-load-balancer-controller |
| cluster-autoscaler | https://github.com/kubernetes/autoscaler/releases |
| metrics-server | https://artifacthub.io/packages/helm/metrics-server/metrics-server |
| cert-manager | https://artifacthub.io/packages/helm/cert-manager/cert-manager |
| external-dns | https://artifacthub.io/packages/helm/external-dns/external-dns |
| external-secrets | https://artifacthub.io/packages/helm/external-secrets/external-secrets |
| kyverno | https://artifacthub.io/packages/helm/kyverno/kyverno |
| kyverno-policies | https://artifacthub.io/packages/helm/kyverno/kyverno-policies |
| gatekeeper | https://artifacthub.io/packages/helm/gatekeeper/gatekeeper |
| velero | https://artifacthub.io/packages/helm/vmware-tanzu/velero |
| ingress-nginx | https://artifacthub.io/packages/helm/ingress-nginx/ingress-nginx |
| aws-privateca-issuer | https://artifacthub.io/packages/helm/cert-manager/aws-privateca-issuer |

| Terraform Module | Registry |
|-----------------|----------|
| eks | https://registry.terraform.io/modules/terraform-aws-modules/eks/aws |
| eks-blueprints-addons | https://registry.terraform.io/modules/aws-ia/eks-blueprints-addons/aws |
| eks-blueprints-addon | https://registry.terraform.io/modules/aws-ia/eks-blueprints-addon/aws |
| eks-pod-identity | https://registry.terraform.io/modules/terraform-aws-modules/eks-pod-identity/aws |

## Known Stale Defaults (eks-blueprints-addons Module)

The `eks-blueprints-addons` module ships chart defaults that lag behind. These addons MUST be overridden:

| Addon | Problem with Module Default | Override Required? |
|-------|---------------------------|-------------------|
| aws-load-balancer-controller | Module default is many versions behind; old versions CrashLoop on IMDS hop-limit | **Yes -- always override** |
| external-secrets | Module default lags significantly | Recommended |
| gatekeeper | Module default lags | Recommended |
| velero | Module default uses old chart major version | Recommended for Pattern 2 |
| kyverno (custom-addons) | Custom-addons module default is behind stable | Always override |

## Addon-Specific Version Rules

### cluster-autoscaler
- Image tag **MUST match** EKS K8s minor version (e.g., `v1.x.0` for EKS 1.x)
- The eks-blueprints-addons module auto-selects correct tag for Pattern 1
- For Pattern 2, set `image.tag` explicitly in the ApplicationSet
- Verify via: `kubectl get deploy -n kube-system cluster-autoscaler-aws-cluster-autoscaler -o jsonpath='{.spec.template.spec.containers[0].image}'`

### aws-load-balancer-controller
- Requires explicit `vpcId` in Helm values -- IMDS fallback fails with hop-limit
- Watch for major chart version bumps that change value schemas

### velero
- Set `upgradeCRDs: false` -- bitnami/kubectl image for latest K8s may not exist
- Pin `kubectl.image.tag` to the latest available -- search Docker Hub for `bitnami/kubectl`
- Set `credentials.useSecret: false` when using Pod Identity

### kyverno
- Override custom-addons module chart version to latest stable
- Major version upgrades may need TLS secret + pod deletion

## Terraform Module Versioning

| Module | Version Strategy | Notes |
|--------|-----------------|-------|
| eks | `~> <MAJOR>.0` | Look up latest major; pin with `~>` for minor flexibility |
| eks-blueprints-addons | Exact pin | Chart defaults are stale -- always override chart versions |
| eks-blueprints-addon | Exact pin | Single addon wrapper for custom addons |
| eks capability | Same as eks module | Submodule -- version tied to eks module |
| eks-pod-identity | `~> <MAJOR>.0` | Used for EKS managed addon Pod Identity IAM roles |

## EKS Capabilities

| Capability | Notes |
|-----------|-------|
| ArgoCD | GA -- fully managed, runs externally, no pods in cluster |
| ACK | GA -- S3 + IAM controllers; field names follow SDK Go convention |
| KRO | Early release -- controller may not yet reconcile RGDs; use ACK directly |
