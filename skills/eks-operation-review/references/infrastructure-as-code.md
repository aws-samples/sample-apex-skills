# Infrastructure as Code & GitOps

## Purpose
Assess whether cluster infrastructure and workload deployments are reproducible, auditable, and version-controlled.

## Automation Note
This section is only partially automatable. The skill can detect tool presence (ArgoCD, Flux, CloudFormation stacks, cluster tags) but cannot assess process maturity (PR reviews, pipeline enforcement). Process-dependent items are marked UNKNOWN.

## Checks to Execute

### 2.1 — Cluster Provisioned via IaC

**What to check:**
- Cluster tags for IaC provenance (terraform, eksctl, cdk, aws:cloudformation:stack-name)
- CloudFormation stacks with "eks" or "EKS" in the name

**How to check:**
1. Describe cluster → inspect `tags` for IaC indicators (tags were already retrieved in Step 0 pre-flight — reuse that data, do NOT call `manage_eks_stacks`)
2. Look for tags: `terraform`, `managed-by`, `aws:cloudformation:stack-name`, `eksctl.cluster.k8s.io/*`, `aws:cdk:*`

**Rating:**
- 🟢 GREEN: Clear IaC provenance in tags (CloudFormation stack, Terraform tags, eksctl tags)
- 🟡 AMBER: IaC tags present but unclear if current, or eksctl-created (basic IaC)
- 🔴 RED: No IaC tags — cluster appears console/CLI-created
- ⬜ UNKNOWN: Tags alone cannot confirm if IaC is pipeline-driven or manually applied — suggest user verify

**Investigate manually:** Is IaC applied via CI/CD pipeline or manually? Could you recreate this cluster from code?

---

### 2.2 — Workload Deployment via GitOps or CI/CD

**What to check:**
- ArgoCD namespace and Application resources
- Flux namespace and Kustomization resources
- Other CD tools (Spinnaker, Tekton namespaces)

**How to check:**
1. List namespaces → check for `argocd`, `flux-system`, `spinnaker`, `tekton-pipelines`
2. If argocd namespace exists → list `applications.argoproj.io` resources, check sync status
3. If flux-system exists → list `kustomizations.kustomize.toolkit.fluxcd.io` resources

**Rating:**
- 🟢 GREEN: GitOps tool active with apps in-sync
- 🟡 AMBER: GitOps tool installed but apps out-of-sync, or CI/CD present but no GitOps
- 🔴 RED: No GitOps or CI/CD tools detected
- ⬜ UNKNOWN: No GitOps tools found — could still have external CI/CD. Suggest user verify: how do teams deploy workloads?

---

### 2.3 — Configuration Drift Detection & Remediation

**What to check:**
- ArgoCD auto-sync and self-heal settings
- Flux reconciliation status

**How to check:**
1. If ArgoCD present → read Application resources, check `spec.syncPolicy.automated` for `selfHeal: true`
2. If Flux present → check kustomization ready status

**Rating:**
- 🟢 GREEN: GitOps with self-heal enabled, all apps in-sync
- 🟡 AMBER: GitOps present but no self-heal, or some apps out-of-sync
- 🔴 RED: No drift detection mechanism
- ⬜ UNKNOWN: No GitOps tools found

---

### 2.4 — Access Control & RBAC Defined in Code

**What to check:**
- Authentication mode (API, CONFIG_MAP, API_AND_CONFIG_MAP)
- EKS Access Entries
- ClusterRoleBindings to cluster-admin
- Whether RBAC resources have GitOps labels

**How to check:**
1. Describe cluster → `accessConfig.authenticationMode`
2. List access entries
3. List ClusterRoleBindings → filter for `roleRef.name == "cluster-admin"`
4. Check ClusterRoles/ClusterRoleBindings for labels indicating Helm/ArgoCD management

**Rating:**
- 🟢 GREEN: API mode with Access Entries, RBAC managed by GitOps, cluster-admin limited
- 🟡 AMBER: API_AND_CONFIG_MAP (transitional), or RBAC partially in code
- 🔴 RED: CONFIG_MAP only with manual edits, broad cluster-admin access
- ⬜ UNKNOWN: Cannot determine if RBAC changes go through PR review — suggest user verify
