---
title: "eks-build"
description: "Use when building EKS clusters. Generates complete, production-ready Terraform projects with optional ArgoCD GitOps integration. Handles environment-specific constraints: air-gapped/VPC-endpoint-only networks, enterprise proxies, private container registries, compliance requirements. Supports 3 patterns: full Terraform, ArgoCD+Terraform, ArgoCD+ACK/KRO. Includes validated modules, two-phase webhook ordering, IRSA/Pod Identity, and 29+ addon configurations. Ask interactive questions or accept requirements YAML. Also use when (1) generating EKS Terraform code from scratch, (2) creating GitOps-managed EKS addons with ArgoCD, (3) scaffolding EKS projects with compliance constraints, (4) implementing two-phase webhook ordering for EKS addons, (5) configuring IRSA or Pod Identity for EKS workloads, (6) generating ArgoCD ApplicationSets for EKS addon management, or (7) comparing deployment patterns for implementation decisions. Skip for Amazon ECS (use ecs-build)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-build/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-build/SKILL.md). Edit the source, not this page.
:::


# EKS Build

Generate complete, production-ready EKS infrastructure projects. All generated code is `terraform apply`-ready with zero manual fixups.

All generated Terraform code MUST follow the conventions from these companion skills:

- **terraform-skill** -- resource block ordering, variable conventions, file organization, version constraints

## When to Use

- Generating EKS Terraform code from requirements (new project)
- Scaffolding EKS infrastructure with air-gapped, proxy, or compliance constraints
- Creating ArgoCD GitOps integration for EKS addon management
- Implementing two-phase webhook ordering for eks-blueprints-addons
- Configuring IRSA or Pod Identity for EKS workloads
- Generating ArgoCD ApplicationSets for addon lifecycle
- Creating Ralph loop validation configurations for EKS projects
- Adding custom addons (Kyverno, Prisma, New Relic) to an EKS project
- Choosing between or comparing deployment patterns (full Terraform vs ArgoCD+Terraform vs ArgoCD+ACK/KRO) for an actual build

## Don't Use

- Designing EKS architecture from requirements (use `eks-design`)
- General Terraform module development or testing (use `terraform-skill`)
- EKS cluster reconnaissance or discovery (use `eks-recon`)
- EKS operational best practices reference (use `eks-best-practices`)
- Amazon ECS builds of any kind (use `ecs-build`)

## Internet Search Requirements

This skill generates code from scratch every time. **Always search the internet** for:

- **Latest versions** of all addons, Helm charts, and Terraform modules before generating code -- never use hardcoded versions from cached knowledge
- **Latest EKS best practices** when requirements don't exactly match existing patterns
- **Addon-specific configuration** for addons not fully covered in existing patterns
- **Breaking changes** in new versions of addons or Terraform modules
- **Pattern 2b: KRO, ACK, and Crossplane** -- these evolve rapidly. Always search for latest RGD schema syntax, supported CRDs, ProviderConfig format, and known limitations

The references in this skill cover the most common scenarios. For anything beyond that, research first, then adapt.

## Pattern Decision Matrix

**Key distinction:** All patterns use Terraform for the EKS cluster and VPC infrastructure. The patterns differ in how K8s addons and AWS addon resources are managed after the cluster exists.

| Factor | Pattern 1: Full Terraform | Pattern 2a: ArgoCD + TF AWS | Pattern 2b: ArgoCD + K8s-native AWS |
|--------|--------------------------|----------------------------|--------------------------|
| **K8s addon management** | Terraform (Helm releases) | K8s-native (ArgoCD ApplicationSets) | K8s-native (ArgoCD ApplicationSets) |
| **AWS resources for addons** | Terraform (IRSA roles, S3 buckets) | **Terraform** for AWS IaC (IRSA roles, S3) | **K8s-native controller** (ACK, Crossplane) |
| **Deployment workflow** | CI/CD runs `terraform apply` | Full GitOps -- ArgoCD reconciles from Git | Full GitOps -- ArgoCD reconciles from Git |
| **Drift detection** | `terraform plan` (manual/scheduled) | ArgoCD self-heal + `terraform plan` for AWS | ArgoCD self-heal + controller reconciliation |
| **Terraform surface area** | Everything (cluster + addons + AWS) | Cluster + **AWS resources** (addons in ArgoCD) | **Cluster only** (addons + AWS both in K8s) |
| **Air-gapped support** | Best (Terraform controls all images) | Good (ECR mirrors + ArgoCD) | Good (same as 2a) |
| **Status** | **Validated** | **Validated** | **Validated** |

For detailed architecture, trade-offs, and selection criteria see [references/pattern-guide.md](references/pattern-guide).

### Pattern 2a vs 2b -- The Defining Difference

The ONLY difference between 2a and 2b is WHO creates the AWS resources that addons need (S3 buckets, IAM roles, policies, Route53 zones):

| | Pattern 2a | Pattern 2b |
|---|---|---|
| **Who creates AWS resources?** | **Terraform** (`module "eks_blueprints_addons"`, `aws_iam_role`) | **K8s-native controller** (ACK CRDs, Crossplane MRs) |
| **Terraform surface area** | Cluster + IAM + S3 + policies | **Cluster + controller bootstrap ONLY** |

**Self-check:** If generated code still uses Terraform for IRSA roles or S3 buckets for addons, that is Pattern 2a, NOT 2b.

Pattern 2b does NOT prescribe which controller. The choice is: ACK, Crossplane, or any K8s-native AWS controller. KRO provides orchestration on top (composing multiple resources into RGDs). Always search the internet for latest KRO docs before generating Pattern 2b code.

## Workflow

### Step 1: Gather Requirements

Accept requirements via interactive questionnaire or a requirements YAML file. If YAML is supplied, validate coverage (cluster, compute, networking, addons, auth, compliance, multi-tenancy) and prompt for gaps.

### Step 2: Select Pattern

Based on requirements, select Pattern 1, 2a, or 2b from the decision matrix.

### Step 3: Create Project Structure

```
projects/<project-name>/
├── design/        # Architecture docs (eks-design skill)
└── code/          # Terraform code (this skill)
```

### Step 4: Generate Pattern Scaffold

Generate root Terraform files under `projects/<project-name>/code/` following `terraform-skill` conventions.

- **Pattern 1** -- `main.tf` implements two-phase module architecture (Critical Rule 1). Phase 1: LBC + Gatekeeper with `wait = true`. Phase 2: all remaining addons with `depends_on = [module.eks_addons_webhooks]`.
- **Pattern 2a/2b** -- `main.tf` provisions EKS cluster and GitOps Bridge. For 2a include IRSA roles. For 2b include only controller bootstrap IAM.

Before generating, search the internet for latest stable versions of `terraform-aws-modules/eks`, `terraform-aws-modules/vpc`, `aws-ia/eks-blueprints-addons`, and all Helm charts. Pin exact versions. See [references/version-matrix.md](references/version-matrix).

### Step 5: Generate Required Modules

Under `projects/<project-name>/code/modules/`:
- `eks-cluster/` -- always. Wraps `terraform-aws-modules/eks` with opinionated defaults from [references/baseline-defaults.md](references/baseline-defaults).
- `custom-addons/` -- if custom addons enabled. See [references/addon-catalog.md](references/addon-catalog).
- `kyverno-policies/` -- if Kyverno CIS benchmark enabled.
- `eks-tenants/` -- if multi-tenancy enabled.
- `eks-gitops-bridge/` -- Pattern 2 only.

### Step 6-7: Configure and Customize

Edit `configs/*.yaml` based on requirements and apply customization patches per [references/customization-guide.md](references/customization-guide):
- Air-gapped, Enterprise proxy, Private registry, Compliance-strict

### Step 8: Generate GitOps Artifacts (Pattern 2 only)

Generate the `gitops/` tree with ArgoCD ApplicationSets. Use cluster ARN as destination server (Critical Rule 10). For OCI Helm charts, omit `oci://` prefix in `repoURL` (Critical Rule 10b).

### Step 9-10: README and Validate

Generate README and run `scripts/validate_project.sh` to verify structure, formatting, and critical configuration.

## Critical Build Rules

Non-negotiable lessons from production deployments. Violating any causes deployment failures. See [references/lessons-learned.md](references/lessons-learned) for full context.

### 1. Two-Phase Module Architecture (Pattern 1)

Split `eks-blueprints-addons` into TWO module calls:
- **Phase 1**: LBC + Gatekeeper only, `wait: true`
- **Phase 2**: All other addons, `depends_on = [module.eks_addons_webhooks]`

LBC and Gatekeeper register webhooks (`failurePolicy: Fail`) before pods are ready. Without two-phase, these webhooks block all other addon deployments.

### 2. before_compute: true

**MANDATORY** for vpc-cni and eks-pod-identity-agent. Without this, nodes fail with `NodeCreationFailure: NetworkPluginNotReady`.

### 3. Cluster-Autoscaler Version Match

Image tag MUST match EKS K8s minor version (e.g., v1.x.y for EKS 1.x).

### 4. LBC Requires Explicit vpcId

IMDS fallback fails with hop-limit restrictions. Always set `vpcId` in LBC Helm values.

### 5. Multus DISABLED

Thick-plugin pod-lookup race blocks ALL new pod creation. Never enable.

### 6. Version Pinning -- Always Search Internet

Never rely on module defaults or hardcoded versions. Search for every addon and module version before generating. See [references/version-matrix.md](references/version-matrix).

### 7. Kyverno syncOptions (Pattern 2)

Use `Replace=true`, NOT `ServerSideApply=true`. SSA conflicts with ArgoCD `selfHeal: true` + `--force`.

### 8. Velero Configuration

Three-part config: S3 bucket (encrypted) + Auth (Pod Identity or IRSA) + Helm values (`upgradeCRDs: false`, pin `kubectl.image.tag`).

### 9. ACK/KRO Are Capabilities, Crossplane Is Not

ACK and KRO run as EKS Capabilities (no pods). Validate via CRDs, not kubectl pods. Crossplane runs as pods via Helm chart.

### 10. ArgoCD Destination Server (Pattern 2)

Use cluster ARN as destination server, NOT `https://kubernetes.default.svc`. AppProjects require `sourceNamespaces: [argocd]`.

### 10b. ArgoCD OCI Helm Chart repoURL

Do NOT include `oci://` prefix in `repoURL`. Use `public.ecr.aws/karpenter` with `chart: karpenter`.

### 10c. S3 Bucket Persistence in Destroy/Apply Cycles (Pattern 2b)

S3 buckets persist after `terraform destroy` because the controller is deleted first. Add `aws s3 rb s3://<bucket> --force || true` as pre-destroy step.

### 11. Use HashiCorp Terraform, NOT OpenTofu

OpenTofu v1.10.6 has severe `depends_on` performance regression (30+ min plan vs < 2 min with Terraform v1.14.5). Require HashiCorp Terraform v1.14.5+.

### 12. ArgoCD EKS Capability Requires IAM Identity Center

The AWS-managed ArgoCD EKS Capability requires an existing IAM Identity Center instance. Self-managed ArgoCD can use any auth method.

## Customization Rules

| Constraint | Trigger | Guide |
|-----------|---------|-------|
| Air-gapped | `network.air_gapped = true` | [customization-guide.md S1](references/customization-guide) |
| Enterprise proxy | `network.proxy.enabled = true` | [customization-guide.md S2](references/customization-guide) |
| Private registry | `registry.type = "private"` | [customization-guide.md S3](references/customization-guide) |
| Compliance-strict | Security posture requirement | [customization-guide.md S4](references/customization-guide) |

## Output Structure

### Pattern 1

```
projects/<project-name>/code/
├── main.tf                    # Two-phase module architecture
├── locals.tf, data.tf, providers.tf, variables.tf, outputs.tf, versions.tf
├── modules/
│   ├── eks-cluster/
│   ├── custom-addons/
│   └── kyverno-policies/
├── configs/
│   ├── cluster.yaml, compute.yaml, addons.yaml, backend.hcl
└── validation-checklist.md
```

### Pattern 2

```
projects/<project-name>/code/
├── main.tf                    # Cluster + GitOps Bridge
├── locals.tf, data.tf, providers.tf, variables.tf, outputs.tf, versions.tf
├── modules/
│   ├── eks-cluster/
│   ├── eks-gitops-bridge/
│   └── custom-addons/
├── configs/
│   ├── cluster.yaml, compute.yaml, addons.yaml, backend.hcl
├── gitops/
│   ├── addons/applicationset.yaml
│   ├── custom-addons/applicationset.yaml
│   ├── bootstrap/argocd-projects.yaml
│   └── tenants/applicationset.yaml
└── validation-checklist.md
```

### Deployment

**Pattern 1:**
```bash
cd projects/<project-name>/code
terraform init -backend-config=configs/backend.hcl
terraform plan && terraform apply
```

**Pattern 2:**
```bash
cd projects/<project-name>/code
terraform init -backend-config=configs/backend.hcl
terraform plan && terraform apply
aws eks update-kubeconfig --name <CLUSTER_NAME> --region <REGION>
kubectl apply -f gitops/bootstrap/argocd-projects.yaml
kubectl apply -f gitops/addons/applicationset.yaml
kubectl apply -f gitops/custom-addons/applicationset.yaml
```

### Expected Timing (HashiCorp Terraform v1.14.5+)

| Step | Pattern 1 | Pattern 2 |
|------|-----------|-----------|
| `terraform plan` | < 2 min | < 1 min |
| `terraform apply` | ~18 min | ~16 min |
| ArgoCD sync | N/A | ~5 min |
| `terraform destroy` | ~10 min | ~15 min |

## Completion Checklist

Every item must be done before handoff:

- [ ] Internet search for latest versions (not from cached knowledge)
- [ ] Pattern selected and confirmed
- [ ] Project structure created with pattern scaffold
- [ ] Required modules generated
- [ ] Configuration customized with project-specific values
- [ ] Customization patches applied (if applicable)
- [ ] GitOps artifacts generated (Pattern 2 only)
- [ ] `terraform fmt -check` passes
- [ ] `before_compute: true` set for vpc-cni and eks-pod-identity-agent
- [ ] Two-phase module architecture present (Pattern 1)
- [ ] All versions explicitly pinned
- [ ] Multus NOT enabled
- [ ] `validation-checklist.md` generated

## References

Read these as needed based on the task at hand:

- [Baseline Defaults](references/baseline-defaults) -- Read when generating cluster, compute, networking, or security configuration. Covers all default values applied to every project.
- [Pattern Guide](references/pattern-guide) -- Read when selecting between patterns or implementing pattern-specific architecture.
- [Customization Guide](references/customization-guide) -- Read when applying air-gapped, proxy, private registry, or compliance constraints.
- [Addon Catalog](references/addon-catalog) -- Read when configuring specific addons or adding custom addons. Covers all 29+ supported addons.
- [Lessons Learned](references/lessons-learned) -- Read when troubleshooting deployment failures or understanding why a Critical Build Rule exists.
- [Version Matrix](references/version-matrix) -- Read when looking up authoritative version sources for addons and Terraform modules.
- [Checkov Config](references/checkov-config) -- Read when setting up security scanning for generated Terraform code.
