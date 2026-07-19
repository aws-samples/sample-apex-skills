---
title: "Module: Security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/security.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/security.md). Edit the source, not this page.
:::

# Module: Security

> **Part of:** [eks-recon](../)
> **Purpose:** Detect security posture - IAM model, Pod Security, policy engines, secrets management

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [1. Authentication & Access Detection](#1-authentication--access-detection)
  - [2. IAM for Pods Detection](#2-iam-for-pods-detection)
  - [3. Pod Security Standards (PSS)](#3-pod-security-standards-pss)
  - [4. Policy Engine Detection](#4-policy-engine-detection)
  - [5. Secrets Management](#5-secrets-management)
  - [6. Image Security](#6-image-security)
  - [7. RBAC Summary](#7-rbac-summary)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `describe_eks_resource`, `list_k8s_resources`, `list_eks_resources`
- **CLI fallback:** `aws eks`, `kubectl`

---

## Detection Strategy

Security posture covers multiple dimensions:

```
1. Authentication    -> access authentication mode, access entries, aws-auth cm, OIDC provider
2. IAM for Pods      -> Pod Identity vs IRSA vs node role
3. Pod Security      -> PSA labels, PSS enforcement
4. Policy Engines    -> Kyverno, OPA Gatekeeper, or none
5. Secrets           -> ESO, Secrets Store CSI, native secrets, KMS
6. Image Security    -> ECR usage, private registries, admission policies
7. RBAC              -> Role/ClusterRole/namespaced Role analysis
```

---

## Detection Commands

### 1. Authentication & Access Detection

Detect how the cluster authenticates and authorizes API principals. These are facts about the cluster's access model.

**Authentication mode** (`API` | `API_AND_CONFIG_MAP` | `CONFIG_MAP`):
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.accessConfig.authenticationMode' --output text
```

**Access entries** (count + principal ARNs):
```bash
aws eks list-access-entries --cluster-name <cluster-name> --region <region> \
  --query 'accessEntries' --output json
```

**aws-auth ConfigMap** (presence is a fact; `NotFound` = `present: false`):
```bash
kubectl get cm aws-auth -n kube-system 2>/dev/null
# Exit non-zero / NotFound => aws_auth_configmap.present: false
```

**OIDC provider** (cluster issuer + whether a matching IAM OIDC provider exists):
```bash
# Cluster OIDC issuer URL
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.identity.oidc.issuer' --output text

# IAM OIDC providers in the account; correlate by the issuer id substring
# (the trailing path segment of the issuer URL) to set iam_provider_present
aws iam list-open-id-connect-providers --query 'OpenIDConnectProviderList[].Arn' --output json
```

**Example output:**
```
# authenticationMode: API_AND_CONFIG_MAP
# access entries: 3 (arn:aws:iam::123456789012:role/AdminRole, ...)
# aws-auth cm: Error from server (NotFound)  => present: false
# oidc issuer: https://oidc.eks.us-west-2.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE
# iam providers: [".../oidc.eks.us-west-2.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE"] => iam_provider_present: true
```

### 2. IAM for Pods Detection

Detect which IAM model the cluster uses for pods to obtain AWS credentials. This is how pods access AWS services:
- **Pod Identity**: AWS-native, uses the EKS Pod Identity Agent addon and pod identity associations
- **IRSA**: uses an OIDC provider and service accounts annotated with `eks.amazonaws.com/role-arn`
- **Node role**: pods use the node's IAM role (no per-pod credential mechanism detected)

**Pod Identity:**

**MCP:**
```
describe_eks_resource(
  resource_type="addon",
  cluster_name="<cluster-name>",
  resource_name="eks-pod-identity-agent"
)
```

**CLI:**
```bash
# Check if Pod Identity agent is installed as an addon
# NOTE: On EKS Auto Mode the Pod Identity Agent is BUILT INTO the cluster, not an installable
# addon, so describe-addon returns ResourceNotFound. That is expected — it does NOT mean Pod
# Identity is absent. Set pod_identity.detected = (addon present) OR (associations.count > 0).
aws eks describe-addon --cluster-name <cluster-name> --addon-name eks-pod-identity-agent 2>/dev/null

# List Pod Identity associations (report each {namespace, serviceAccount, roleArn} triple, not just a count)
# NOTE: list-pod-identity-associations does NOT return roleArn — its association objects only carry
# clusterName/namespace/serviceAccount/associationArn/associationId. roleArn requires the describe call.
# Two-step: enumerate association IDs, then describe each to obtain roleArn.
for id in $(aws eks list-pod-identity-associations --cluster-name <cluster-name> --region <region> \
    --query 'associations[].associationId' --output text); do
  aws eks describe-pod-identity-association --cluster-name <cluster-name> --association-id "$id" --region <region> \
    --query 'association.{namespace:namespace,serviceAccount:serviceAccount,roleArn:roleArn}'
done
# IAM: no new permissions needed — describe-pod-identity-association is covered by eks:Describe*.
```

**Example output (Pod Identity enabled):**
```json
{
  "addon": {
    "addonName": "eks-pod-identity-agent",
    "status": "ACTIVE",
    "addonVersion": "v1.3.4-eksbuild.1"
  }
}
```

**IRSA (IAM Roles for Service Accounts):**

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="ServiceAccount",
  api_version="v1"
)
```

**CLI:**
```bash
# Find service accounts with IRSA annotation
kubectl get sa -A -o json | jq -r '
  .items[] | 
  select(.metadata.annotations["eks.amazonaws.com/role-arn"] != null) |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    role: .metadata.annotations["eks.amazonaws.com/role-arn"]
  }'
```

**Example output (IRSA configured):**
```json
{
  "namespace": "kube-system",
  "name": "aws-load-balancer-controller",
  "role": "arn:aws:iam::123456789012:role/AWSLoadBalancerControllerRole"
}
{
  "namespace": "external-secrets",
  "name": "external-secrets",
  "role": "arn:aws:iam::123456789012:role/ExternalSecretsRole"
}
```

**Determine IAM Model:**
```
if pod_identity_associations > 0:
    if irsa_service_accounts > 0:
        model = "mixed"
    else:
        model = "Pod Identity"
elif irsa_service_accounts > 0:
    model = "IRSA"
else:
    model = "node-role"  # No per-pod credential mechanism detected; pods use the node IAM role
```

### 3. Pod Security Standards (PSS)

Check Pod Security Admission (PSA) enforcement. PSA replaced PodSecurityPolicy in Kubernetes 1.25+. Report which namespaces set which enforcement level:
- **restricted**: most constrained level
- **baseline**: minimally restrictive level
- **privileged**: unrestricted level (the default when no label is set)

**CLI:**
```bash
# Check PSA labels on namespaces
kubectl get ns -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.name,
    enforce: .metadata.labels["pod-security.kubernetes.io/enforce"],
    warn: .metadata.labels["pod-security.kubernetes.io/warn"],
    audit: .metadata.labels["pod-security.kubernetes.io/audit"]
  } |
  select(.enforce != null or .warn != null or .audit != null)'
```

**Example output (PSA configured):**
```json
{
  "namespace": "production",
  "enforce": "restricted",
  "warn": "restricted",
  "audit": "restricted"
}
{
  "namespace": "monitoring",
  "enforce": "baseline",
  "warn": "restricted",
  "audit": null
}
```

**Summary:**
```bash
# Count namespaces by enforcement level; the "none" bucket = namespaces with no PSA enforce label
kubectl get ns -o json | jq -r '
  .items | 
  group_by(.metadata.labels["pod-security.kubernetes.io/enforce"]) |
  map({level: (.[0].metadata.labels["pod-security.kubernetes.io/enforce"] // "none"), count: length})'
```

### 4. Policy Engine Detection

Identify which policy engines (if any) are installed. Policy engines enforce admission control beyond PSA:
- **Kyverno**: policies written in YAML
- **OPA Gatekeeper**: constraints written in Rego
Both may be present simultaneously — report each independently.

**Kyverno:**
```bash
# Check for Kyverno admission-controller deployment
kubectl get deploy -n kyverno kyverno-admission-controller 2>/dev/null

# Get Kyverno version from the admission-controller deployment (target by name, not items[0])
kubectl get deploy kyverno-admission-controller -n kyverno -o json 2>/dev/null | \
  jq -r '.spec.template.spec.containers[0].image'

# Count policies (-o name avoids the header-row off-by-one)
kubectl get clusterpolicies.kyverno.io -o name 2>/dev/null | wc -l
kubectl get policies.kyverno.io -A -o name 2>/dev/null | wc -l
```

**Example output (Kyverno detected):**
```
NAME                            READY   AGE
kyverno-admission-controller    1/1     45d

# Version: ghcr.io/kyverno/kyverno:v1.11.4
# ClusterPolicies: 12
# Policies: 3
```

**OPA Gatekeeper:**
```bash
# Check for Gatekeeper controller-manager deployment
kubectl get deploy -n gatekeeper-system gatekeeper-controller-manager 2>/dev/null

# Get Gatekeeper version from the controller-manager deployment (target by name, not items[0])
kubectl get deploy gatekeeper-controller-manager -n gatekeeper-system -o json 2>/dev/null | \
  jq -r '.spec.template.spec.containers[0].image'

# Count constraints (-o name avoids the header-row off-by-one)
kubectl get constraints -o name 2>/dev/null | wc -l
kubectl get constrainttemplates -o name 2>/dev/null | wc -l
```

**Example output (Gatekeeper detected):**
```
NAME                                READY   AGE
gatekeeper-controller-manager       1/1     90d

# Version: openpolicyagent/gatekeeper:v3.15.0
# ConstraintTemplates: 8
# Constraints: 15
```

### 5. Secrets Management

Detect how the cluster manages sensitive data:
- **External Secrets Operator (ESO)**: syncs secrets from AWS Secrets Manager/Parameter Store into K8s secrets
- **Secrets Store CSI Driver**: mounts secrets as volumes
- **KMS envelope encryption**: `cluster.encryptionConfig` scope for etcd secrets

**External Secrets Operator (ESO):**
```bash
# Check for ESO deployment
kubectl get deploy -n external-secrets external-secrets 2>/dev/null

# Count ExternalSecrets (-o name avoids the header-row off-by-one)
kubectl get externalsecrets.external-secrets.io -A -o name 2>/dev/null | wc -l

# Check SecretStores
kubectl get secretstores.external-secrets.io -A 2>/dev/null | head -5
kubectl get clustersecretstores.external-secrets.io 2>/dev/null | head -5
```

**Example output (ESO detected):**
```
NAME               READY   AGE
external-secrets   1/1     60d

# ExternalSecrets: 24
# SecretStores (namespaced): 4
# ClusterSecretStores: 1
```

**Secrets Store CSI Driver:**
```bash
# Check for Secrets Store CSI
kubectl get daemonset -n kube-system secrets-store-csi-driver 2>/dev/null

# Check for AWS provider
kubectl get daemonset -n kube-system secrets-store-csi-driver-provider-aws 2>/dev/null

# Count SecretProviderClasses (-o name avoids the header-row off-by-one)
kubectl get secretproviderclasses -A -o name 2>/dev/null | wc -l
```

**Example output (Secrets Store CSI detected):**
```
NAME                                      DESIRED   CURRENT   READY   AGE
secrets-store-csi-driver                  3         3         3       45d
secrets-store-csi-driver-provider-aws     3         3         3       45d

# SecretProviderClasses: 8
```

**KMS Encryption:**
```bash
# Report whether envelope encryption is configured and the key arn
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.encryptionConfig[*].{resources:resources,keyArn:provider.keyArn}'
```

**Example output (KMS encryption enabled):**
```json
[
  {
    "resources": ["secrets"],
    "keyArn": "arn:aws:kms:us-west-2:123456789012:key/a1b2c3d4-5678-90ab-cdef-EXAMPLE11111"
  }
]
```

> **Scope note:** `cluster.encryptionConfig` is fully owned by cluster-basics
> (`encryption_config.detected` / `.kms_key_arn` / `.resources` — see
> [`references/cluster-basics.md`](cluster-basics) "## Cluster Detail (full recon)").
> Security reports only the secrets-management view: `secrets.kms_encryption.{enabled,kms_key_arn}`.
> The resources-scope list (e.g. `["secrets"]`) is not re-owned here — defer to cluster-basics.

### 6. Image Security

Inventory container image sourcing facts:
- **ECR usage**: whether images pull from ECR (private `*.dkr.ecr.*` or `public.ecr.aws`)
- **Private registries**: the distinct registry hosts in use
- **Admission policies**: whether Kyverno/Gatekeeper rules target Pods (image-related admission control exists)

**ECR usage:**
```bash
# Check if ECR is used (look for ECR URLs in pods)
kubectl get pods -A -o json | jq -r '
  .items[].spec.containers[].image | 
  select(contains(".ecr.") or contains("ecr.aws"))' | sort -u | head -10
```

**Private registries in use** (distinct registry hosts across all pods):
```bash
kubectl get pods -A -o json | jq -r '
  .items[].spec.containers[].image
  | split("/")[0]
  | select(contains(".") or contains(":"))' | sort -u
```

**Example output (ECR images found):**
```
123456789012.dkr.ecr.us-west-2.amazonaws.com/my-app:v1.2.3
123456789012.dkr.ecr.us-west-2.amazonaws.com/api-service:latest
public.ecr.aws/aws-observability/aws-otel-collector:v0.35.0
```

**Image Policy Enforcement:**
```bash
# Check for image policies in Kyverno
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null | \
  jq -r '.items[] | select(.spec.rules[].match.resources.kinds[] == "Pod") | .metadata.name'

# Check for Gatekeeper image constraints
kubectl get constraints -o json 2>/dev/null | \
  jq -r '.items[] | select(.spec.match.kinds[].kinds[] == "Pod") | .metadata.name'
```

### 7. RBAC Summary

Inventory RBAC objects and report these facts:
- **Cluster-scoped**: ClusterRole / ClusterRoleBinding counts
- **Namespaced**: Role / RoleBinding counts
- **Wildcard roles**: roles whose rules contain `resources: ["*"]` AND `verbs: ["*"]` (report the names — a fact, no judgment)
- **cluster-admin bindings**: ClusterRoleBindings whose `roleRef.name == cluster-admin` (report names + subjects)

```bash
# Cluster-scoped counts (-o name avoids the header-row off-by-one)
kubectl get clusterroles -o name | wc -l
kubectl get clusterrolebindings -o name | wc -l

# Namespaced counts (-o name avoids the header-row off-by-one)
kubectl get roles -A -o name | wc -l
kubectl get rolebindings -A -o name | wc -l

# Find ClusterRoles with wildcard resources AND wildcard verbs (a fact)
kubectl get clusterroles -o json | jq -r '
  .items[] |
  select(any(.rules[]?; (.resources[]? == "*") and (.verbs[]? == "*"))) |
  .metadata.name'

# Find namespaced Roles with wildcard resources AND wildcard verbs (a fact)
kubectl get roles -A -o json | jq -r '
  .items[] |
  select(any(.rules[]?; (.resources[]? == "*") and (.verbs[]? == "*"))) |
  "\(.metadata.namespace)/\(.metadata.name)"'

# cluster-admin bindings (report names + subjects)
kubectl get clusterrolebindings -o json | jq -r '
  .items[] |
  select(.roleRef.name == "cluster-admin") |
  {name: .metadata.name, subjects: .subjects}'
```

**Example output (RBAC findings):**
```
# ClusterRoles: 87
# ClusterRoleBindings: 52
# Roles (all namespaces): 41
# RoleBindings (all namespaces): 63

# Wildcard roles (resources:* AND verbs:*):
super-admin-role
kube-system/local-operator-role

# cluster-admin bindings:
{
  "name": "cluster-admin-binding",
  "subjects": [
    {"kind": "User", "name": "admin@example.com"}
  ]
}
{
  "name": "eks-console-dashboard-full-access-binding",
  "subjects": [
    {"kind": "Group", "name": "eks-console-dashboard-full-access-group"}
  ]
}
```

---

## Output Schema

This is the **single canonical schema** for the security module — it carries every security
fact. The `security-recon` agent emits exactly this shape (plus the shared `cluster:` block
from `references/cluster-basics.md`). Use `null` where a fact was not detected; never omit a key.
This module reports only security-relevant facts that EXIST; it draws no verdicts.

```yaml
security:
  authentication:
    mode: string                    # cluster.accessConfig.authenticationMode: API | API_AND_CONFIG_MAP | CONFIG_MAP
    access_entries:
      count: int                    # number of access entries
      principal_arns: list          # principalArn per access entry
    aws_auth_configmap:
      present: bool                 # kubectl get cm aws-auth -n kube-system (NotFound => false)
    oidc:
      issuer: string                # cluster.identity.oidc.issuer, null if absent
      iam_provider_present: bool    # an IAM OIDC provider whose arn contains the issuer id substring exists

  iam_for_pods:
    model: string                   # Pod Identity | IRSA | mixed | node-role
    pod_identity:
      detected: bool                  # (eks-pod-identity-agent addon present) OR (associations.count > 0).
                                      # On EKS Auto Mode the agent is built-in, so describe-addon returns
                                      # ResourceNotFound (expected, not "absent") — associations.count > 0 sets detected: true.
      associations:
        count: int
        list:                       # one entry per pod identity association
          - namespace: string
            service_account: string
            role_arn: string
    irsa:
      detected: bool
      service_accounts_with_irsa: int   # count of SAs annotated with eks.amazonaws.com/role-arn

  pod_security:
    psa_enabled: bool
    enforcement:
      restricted: int               # namespaces enforcing restricted
      baseline: int                 # namespaces enforcing baseline
      privileged: int               # namespaces enforcing privileged
      none: int                     # namespaces with no PSA enforce label

  policy_engines:
    kyverno:
      detected: bool
      version: string
      cluster_policies: int
      policies: int
    opa_gatekeeper:
      detected: bool
      version: string
      constraint_templates: int
      constraints: int

  secrets:
    kms_encryption:
      enabled: bool                 # cluster.encryptionConfig present (secrets-management view)
      kms_key_arn: string           # provider.keyArn, null if absent
    external_secrets_operator:
      detected: bool
      version: string
      external_secrets_count: int
      secret_stores: int
    secrets_store_csi:
      detected: bool
      aws_provider: bool
      secret_provider_classes: int

  image_security:
    ecr_used: bool                  # any pod image pulls from ECR (private or public)
    private_registries: list        # distinct registry hosts across all pod images
    admission_policies: bool        # Kyverno/Gatekeeper rules targeting Pods exist

  admission_webhooks:
    validating:
      count: int                    # total ValidatingWebhookConfigurations
      webhooks:                     # non-system entries only
        - name: string
          webhook_names: list
          failure_policy: string    # Fail | Ignore (webhooks[0].failurePolicy)
    mutating:
      count: int                    # total MutatingWebhookConfigurations
      webhooks:                     # non-system entries only
        - name: string
          webhook_names: list
          failure_policy: string

  rbac:
    cluster_roles: int
    cluster_role_bindings: int
    roles: int                      # namespaced Roles across all namespaces
    role_bindings: int              # namespaced RoleBindings across all namespaces
    wildcard_roles: list            # roles whose rules contain resources:* AND verbs:* (cluster + namespaced)
    cluster_admin_bindings:         # ClusterRoleBindings with roleRef.name == cluster-admin
      - name: string
        subjects: list
```

---

## Edge Cases

### Mixed IAM for Pods

Some clusters use both IRSA and Pod Identity:
- `iam_for_pods.model: mixed`
- Both `pod_identity.detected` and `irsa.detected` are true; report both counts.

### Namespaces with no PSA labels

Namespaces without a PSA enforce label are counted in `pod_security.enforcement.none` (a fact; report the count).

### Multiple Policy Engines

A cluster may run both Kyverno and Gatekeeper. Report each under `policy_engines` independently (`detected: true` for both).

### GuardDuty Integration

```bash
# Check if GuardDuty EKS Runtime Monitoring is enabled
aws guardduty list-detectors --query 'DetectorIds'
# Then check features for each detector
aws guardduty get-detector --detector-id <id> \
  --query 'Features[?Name==`EKS_RUNTIME_MONITORING`]'
```

### Admission Webhooks

Identify validating and mutating admission webhooks to understand what policies are enforced at admission time. Webhooks can block or modify resources before they're persisted.

**CLI:**
```bash
# List validating webhooks (exclude system webhooks)
kubectl get validatingwebhookconfigurations -o json | jq '[
  .items[] | 
  select(.metadata.name | test("^(eks|vpc-resource|aws-)") | not) |
  {name: .metadata.name, webhooks: [.webhooks[].name], failurePolicy: .webhooks[0].failurePolicy}
]'

# List mutating webhooks (exclude system webhooks)
kubectl get mutatingwebhookconfigurations -o json | jq '[
  .items[] | 
  select(.metadata.name | test("^(eks|vpc-resource|aws-)") | not) |
  {name: .metadata.name, webhooks: [.webhooks[].name], failurePolicy: .webhooks[0].failurePolicy}
]'

# Count all webhooks
kubectl get validatingwebhookconfigurations --no-headers | wc -l
kubectl get mutatingwebhookconfigurations --no-headers | wc -l
```

**Example output (validating webhooks):**
```json
[
  {
    "name": "kyverno-resource-validating-webhook-cfg",
    "webhooks": ["validate.kyverno.svc"],
    "failurePolicy": "Fail"
  },
  {
    "name": "cert-manager-webhook",
    "webhooks": ["webhook.cert-manager.io"],
    "failurePolicy": "Fail"
  }
]
```

**Notable webhook names (reported verbatim as facts):**
- `kyverno-*` - Kyverno policy enforcement
- `gatekeeper-*` - OPA Gatekeeper constraints
- `cert-manager-webhook` - cert-manager
- `aws-load-balancer-webhook` - ALB controller

Admission webhooks are part of the canonical schema under `security.admission_webhooks`
(validating + mutating, each with `count` and per-webhook `{name, webhook_names, failure_policy}`).
Report `failurePolicy` verbatim (`Fail` | `Ignore`) as a fact; draw no conclusion.
