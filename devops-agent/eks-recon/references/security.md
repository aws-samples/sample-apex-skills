# Module: Security

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect security posture — IAM model, Pod Security, policy engines, secrets management

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
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

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS/IAM/KMS/GuardDuty) — authentication mode, access entries, OIDC
  issuer and matching IAM OIDC providers, envelope-encryption/KMS config, Pod Identity
  associations (via `eks:ListPodIdentityAssociations` + `eks:DescribePodIdentityAssociation`,
  covered by `eks:Describe*`), and GuardDuty EKS Runtime Monitoring status (via
  `guardduty:ListDetectors` + `guardduty:GetDetector`, in `references/iam-policy.json`).
  Container-image registries are ultimately observed from
  workload pod images (Kubernetes API); the AWS side only tells you whether ECR repositories
  exist, not whether workloads pull from them. Requires the read-only permissions in
  `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — the `aws-auth` ConfigMap;
  RBAC (ClusterRoles/ClusterRoleBindings, namespaced Roles/RoleBindings, wildcard roles,
  cluster-admin bindings); admission webhooks; PSA namespace labels; policy engines
  (Kyverno, OPA Gatekeeper); and secrets tooling (External Secrets Operator, Secrets Store
  CSI). Requires `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy`
  access entry to be present. RBAC verbs needed: `get`, `list`.

If the Kubernetes API is unreachable (access entry absent), report the AWS-API facts and
mark every K8s-dependent sub-fact (`aws_auth_configmap`, `rbac.*`, `admission_webhooks`,
`pod_security`, `policy_engines`, `secrets.external_secrets_operator`,
`secrets.secrets_store_csi`, `image_security.*`, `iam_for_pods.irsa`) as `unconfirmed` in
the report's Coverage section — never as `false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes
> client)* below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They
> are **not executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its Kubernetes-API
> capability.

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

## Detection Capabilities

### 1. Authentication & Access Detection

Detect how the cluster authenticates and authorizes API principals. These are facts about
the cluster's access model.

**Via AWS API** — authentication mode (`API` | `API_AND_CONFIG_MAP` | `CONFIG_MAP`):

```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.accessConfig.authenticationMode' --output text
```

**Via AWS API** — access entries (count + principal ARNs):

```bash
aws eks list-access-entries --cluster-name <cluster-name> --region <region> \
  --query 'accessEntries' --output json
```

**Via AWS API** — OIDC provider (cluster issuer + whether a matching IAM OIDC provider exists):

```bash
# Cluster OIDC issuer URL
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.identity.oidc.issuer' --output text

# IAM OIDC providers in the account; correlate by the issuer id substring
# (the trailing path segment of the issuer URL) to set iam_provider_present
aws iam list-open-id-connect-providers --query 'OpenIDConnectProviderList[].Arn' --output json
```

**Via Kubernetes API** — the `aws-auth` ConfigMap (presence is a fact):

- **Resource:** `ConfigMap`, group/version `v1` (core), name `aws-auth`, namespace `kube-system`.
- **Fields to extract:** presence only. A `NotFound` result sets `aws_auth_configmap.present: false`.
- **RBAC verbs:** `get` on `configmaps` in `kube-system`.

**Example facts:**
```
# authenticationMode: API_AND_CONFIG_MAP
# access entries: 3 (arn:aws:iam::123456789012:role/AdminRole, ...)
# aws-auth cm: not found  => present: false
# oidc issuer: https://oidc.eks.us-west-2.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE
# iam providers: [".../oidc.eks.us-west-2.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE"] => iam_provider_present: true
```

### 2. IAM for Pods Detection

Detect which IAM model the cluster uses for pods to obtain AWS credentials. This is how pods
access AWS services:
- **Pod Identity**: AWS-native, uses the EKS Pod Identity Agent addon and pod identity associations
- **IRSA**: uses an OIDC provider and service accounts annotated with `eks.amazonaws.com/role-arn`
- **Node role**: pods use the node's IAM role (no per-pod credential mechanism detected)

**Via AWS API** — Pod Identity (addon + associations):

```bash
# Check if the Pod Identity agent is installed as an addon.
# NOTE: On EKS Auto Mode the Pod Identity Agent is BUILT INTO the cluster, not an installable
# addon, so describe-addon returns ResourceNotFound. That is expected — it does NOT mean Pod
# Identity is absent. Set pod_identity.detected = (addon present) OR (associations.count > 0).
aws eks describe-addon --cluster-name <cluster-name> --addon-name eks-pod-identity-agent 2>/dev/null

# List Pod Identity associations (report each {namespace, serviceAccount, roleArn} triple, not just a count).
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

**Example facts (Pod Identity enabled):**
```json
{
  "addon": {
    "addonName": "eks-pod-identity-agent",
    "status": "ACTIVE",
    "addonVersion": "v1.3.4-eksbuild.1"
  }
}
```

**Via Kubernetes API** — IRSA service accounts:

- **Resource:** `ServiceAccount`, group/version `v1` (core), all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, and the annotation
  `metadata.annotations["eks.amazonaws.com/role-arn"]`. Select only service accounts where
  that annotation is present; report `{namespace, name, role}` per match and the total count.
- **RBAC verbs:** `get`, `list` on `serviceaccounts` (all namespaces).

*Reference pseudocode (kubernetes client), not executable:*
```python
v1 = client.CoreV1Api()
irsa = [
    {"namespace": sa.metadata.namespace,
     "name": sa.metadata.name,
     "role": (sa.metadata.annotations or {}).get("eks.amazonaws.com/role-arn")}
    for sa in v1.list_service_account_for_all_namespaces().items
    if (sa.metadata.annotations or {}).get("eks.amazonaws.com/role-arn")
]
```

**Example facts (IRSA configured):**
```json
{"namespace": "kube-system", "name": "aws-load-balancer-controller", "role": "arn:aws:iam::123456789012:role/AWSLoadBalancerControllerRole"}
{"namespace": "external-secrets", "name": "external-secrets", "role": "arn:aws:iam::123456789012:role/ExternalSecretsRole"}
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

Check Pod Security Admission (PSA) enforcement. PSA replaced PodSecurityPolicy in Kubernetes
1.25+. Report which namespaces set which enforcement level:
- **restricted**: most constrained level
- **baseline**: minimally restrictive level
- **privileged**: unrestricted level (the default when no label is set)

**Via Kubernetes API** — PSA labels on namespaces:

- **Resource:** `Namespace`, group/version `v1` (core).
- **Fields to extract:** `metadata.name` and labels `pod-security.kubernetes.io/enforce`,
  `pod-security.kubernetes.io/warn`, `pod-security.kubernetes.io/audit`. A namespace is
  reported when any of the three labels is set.
- **Summary selection logic:** group namespaces by the value of the
  `pod-security.kubernetes.io/enforce` label; namespaces with no enforce label fall into the
  `none` bucket. Count namespaces per bucket (`restricted` / `baseline` / `privileged` / `none`).
- **RBAC verbs:** `get`, `list` on `namespaces`.

*Reference pseudocode (kubernetes client), not executable:*
```python
v1 = client.CoreV1Api()
buckets = {"restricted": 0, "baseline": 0, "privileged": 0, "none": 0}
detail = []
for ns in v1.list_namespace().items:
    labels = ns.metadata.labels or {}
    enforce = labels.get("pod-security.kubernetes.io/enforce")
    warn = labels.get("pod-security.kubernetes.io/warn")
    audit = labels.get("pod-security.kubernetes.io/audit")
    buckets[enforce if enforce in buckets else "none"] += 1
    if enforce or warn or audit:
        detail.append({"namespace": ns.metadata.name,
                       "enforce": enforce, "warn": warn, "audit": audit})
```

**Example facts (PSA configured):**
```json
{"namespace": "production", "enforce": "restricted", "warn": "restricted", "audit": "restricted"}
{"namespace": "monitoring", "enforce": "baseline", "warn": "restricted", "audit": null}
```

### 4. Policy Engine Detection

Identify which policy engines (if any) are installed. Policy engines enforce admission
control beyond PSA:
- **Kyverno**: policies written in YAML
- **OPA Gatekeeper**: constraints written in Rego

Both may be present simultaneously — report each independently.

**Via Kubernetes API** — Kyverno:

- **Deployment:** `Deployment`, group/version `apps/v1`, name `kyverno-admission-controller`,
  namespace `kyverno`. Presence = Kyverno installed. Read
  `spec.template.spec.containers[0].image` and parse the tag for the version (target the
  deployment by name, not `items[0]`).
- **Policy counts:** `ClusterPolicy` (`clusterpolicies.kyverno.io`) cluster-wide, and
  `Policy` (`policies.kyverno.io`) across all namespaces. Count resources directly (the
  resource count, not a header-inclusive line count).
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `clusterpolicies.kyverno.io`,
  `policies.kyverno.io`.

**Example facts (Kyverno detected):** deployment `kyverno-admission-controller` present;
version `ghcr.io/kyverno/kyverno:v1.11.4`; ClusterPolicies 12; Policies 3.

**Via Kubernetes API** — OPA Gatekeeper:

- **Deployment:** `Deployment`, group/version `apps/v1`, name `gatekeeper-controller-manager`,
  namespace `gatekeeper-system`. Presence = Gatekeeper installed. Read
  `spec.template.spec.containers[0].image` and parse the tag for the version (target by name).
- **Constraint counts:** `constraints` (the aggregate constraint resources) and
  `constrainttemplates`. Count resources directly.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `constraints`, `constrainttemplates`.

**Example facts (Gatekeeper detected):** deployment `gatekeeper-controller-manager` present;
version `openpolicyagent/gatekeeper:v3.15.0`; ConstraintTemplates 8; Constraints 15.

### 5. Secrets Management

Detect how the cluster manages sensitive data:
- **External Secrets Operator (ESO)**: syncs secrets from AWS Secrets Manager/Parameter Store into K8s secrets
- **Secrets Store CSI Driver**: mounts secrets as volumes
- **KMS envelope encryption**: `cluster.encryptionConfig` scope for etcd secrets

**Via Kubernetes API** — External Secrets Operator (ESO):

- **Deployment:** `Deployment`, group/version `apps/v1`, name `external-secrets`, namespace
  `external-secrets`. Presence = ESO installed; read the image tag for the version.
- **Counts:** `ExternalSecret` (`externalsecrets.external-secrets.io`) across all namespaces;
  `SecretStore` (`secretstores.external-secrets.io`, namespaced) and `ClusterSecretStore`
  (`clustersecretstores.external-secrets.io`, cluster-scoped). Count resources directly.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `externalsecrets.external-secrets.io`,
  `secretstores.external-secrets.io`, `clustersecretstores.external-secrets.io`.

**Example facts (ESO detected):** deployment `external-secrets` present; ExternalSecrets 24;
SecretStores (namespaced) 4; ClusterSecretStores 1.

**Via Kubernetes API** — Secrets Store CSI Driver:

- **DaemonSet:** `DaemonSet`, group/version `apps/v1`, namespace `kube-system`, names
  `secrets-store-csi-driver` (driver) and `secrets-store-csi-driver-provider-aws` (AWS
  provider). Presence of each is a fact.
- **Counts:** `SecretProviderClass` (`secretproviderclasses`) across all namespaces. Count
  resources directly.
- **RBAC verbs:** `get`, `list` on `daemonsets.apps`, `secretproviderclasses`.

**Example facts (Secrets Store CSI detected):** daemonsets `secrets-store-csi-driver` and
`secrets-store-csi-driver-provider-aws` present; SecretProviderClasses 8.

**Via AWS API** — KMS envelope encryption (secrets-management view):

```bash
# Report whether envelope encryption is configured and the key arn
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.encryptionConfig[*].{resources:resources,keyArn:provider.keyArn}'
```

**Example facts (KMS encryption enabled):**
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
> [`references/cluster-basics.md`](cluster-basics.md) "## Cluster Detail (full recon)").
> Security reports only the secrets-management view: `secrets.kms_encryption.{enabled,kms_key_arn}`.
> The resources-scope list (e.g. `["secrets"]`) is not re-owned here — defer to cluster-basics.

### 6. Image Security

Inventory container image sourcing facts:
- **ECR usage**: whether images pull from ECR (private `*.dkr.ecr.*` or `public.ecr.aws`)
- **Private registries**: the distinct registry hosts in use
- **Admission policies**: whether Kyverno/Gatekeeper rules target Pods (image-related admission control exists)

ECR usage and registry hosts are observed from the images that workloads actually run — the
authoritative source is pod container images read via the Kubernetes API (the AWS side only
tells you ECR repositories exist, not that anything pulls from them).

**Via Kubernetes API** — ECR usage and private registries:

- **Resource:** `Pod`, group/version `v1` (core), all namespaces.
- **Fields to extract:** `spec.containers[].image` for every pod. `ecr_used` is true if any
  image string contains `.ecr.` or `ecr.aws`. `private_registries` is the distinct set of
  registry hosts — the first `/`-delimited segment of each image, kept only when it looks
  like a host (contains `.` or `:`).
- **RBAC verbs:** `get`, `list` on `pods` (all namespaces).

**Via Kubernetes API** — image policy enforcement:

- **Kyverno:** list `ClusterPolicy` (`clusterpolicies.kyverno.io`); a policy targets images
  when any rule's `match.resources.kinds` includes `Pod`. Report matching policy names.
- **Gatekeeper:** list `constraints`; a constraint targets images when any
  `spec.match.kinds[].kinds` includes `Pod`. Report matching constraint names.
- `admission_policies` is true if any such Pod-targeting policy/constraint exists.
- **RBAC verbs:** `get`, `list` on `clusterpolicies.kyverno.io`, `constraints`.

**Example facts (ECR images found):**
```
123456789012.dkr.ecr.us-west-2.amazonaws.com/my-app:v1.2.3
123456789012.dkr.ecr.us-west-2.amazonaws.com/api-service:latest
public.ecr.aws/aws-observability/aws-otel-collector:v0.35.0
```

### 7. RBAC Summary

Inventory RBAC objects and report these facts:
- **Cluster-scoped**: ClusterRole / ClusterRoleBinding counts
- **Namespaced**: Role / RoleBinding counts
- **Wildcard roles**: roles whose rules contain `resources: ["*"]` AND `verbs: ["*"]` (report the names — a fact, no judgment)
- **cluster-admin bindings**: ClusterRoleBindings whose `roleRef.name == cluster-admin` (report names + subjects)

**Via Kubernetes API** — RBAC inventory:

- **Resources:** `ClusterRole`, `ClusterRoleBinding`, `Role`, `RoleBinding`, all group/version
  `rbac.authorization.k8s.io/v1`. Roles/RoleBindings are counted across all namespaces.
- **Counts:** report the resource count for each of the four kinds (the count of objects, not
  a header-inclusive line count).
- **Wildcard role selection logic:** a role (ClusterRole or namespaced Role) qualifies when
  **any single rule** in `rules[]` has `resources` containing `*` **AND** `verbs` containing
  `*`. The per-rule (`any()`) test is deliberate: it must not match a role where one rule has
  `resources: ["*"]` and a *different* rule has `verbs: ["*"]`. Report qualifying cluster
  roles by name and namespaced roles as `namespace/name`. This is a fact (roles with
  `resources:*` and `verbs:*`), not a judgment about permissiveness.
- **cluster-admin bindings:** `ClusterRoleBinding` objects whose `roleRef.name == cluster-admin`;
  report `{name, subjects}`.
- **RBAC verbs:** `get`, `list` on `clusterroles`, `clusterrolebindings`, `roles`,
  `rolebindings` (all `rbac.authorization.k8s.io`).

*Reference pseudocode (kubernetes client), not executable:*
```python
rbac = client.RbacAuthorizationV1Api()

def is_wildcard(rules):
    return any(
        "*" in (r.resources or []) and "*" in (r.verbs or [])
        for r in (rules or [])
    )

wildcard = []
for cr in rbac.list_cluster_role().items:
    if is_wildcard(cr.rules):
        wildcard.append(cr.metadata.name)
for r in rbac.list_role_for_all_namespaces().items:
    if is_wildcard(r.rules):
        wildcard.append(f"{r.metadata.namespace}/{r.metadata.name}")

cluster_admin = [
    {"name": b.metadata.name, "subjects": b.subjects}
    for b in rbac.list_cluster_role_binding().items
    if b.role_ref.name == "cluster-admin"
]
```

**Example facts (RBAC findings):**
```
# ClusterRoles: 87
# ClusterRoleBindings: 52
# Roles (all namespaces): 41
# RoleBindings (all namespaces): 63

# Wildcard roles (resources:* AND verbs:*):
super-admin-role
kube-system/local-operator-role

# cluster-admin bindings:
{"name": "cluster-admin-binding", "subjects": [{"kind": "User", "name": "admin@example.com"}]}
{"name": "eks-console-dashboard-full-access-binding", "subjects": [{"kind": "Group", "name": "eks-console-dashboard-full-access-group"}]}
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
      present: bool                 # ConfigMap aws-auth in kube-system (NotFound => false)
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

**Via AWS API** — check whether GuardDuty EKS Runtime Monitoring is enabled:

```bash
# List detectors, then check features for each detector
aws guardduty list-detectors --query 'DetectorIds'
aws guardduty get-detector --detector-id <id> \
  --query 'Features[?Name==`EKS_RUNTIME_MONITORING`]'
```

### Admission Webhooks

Identify validating and mutating admission webhooks to understand what policies are enforced
at admission time. Webhooks can block or modify resources before they're persisted.

**Via Kubernetes API** — validating and mutating webhook configurations:

- **Resources:** `ValidatingWebhookConfiguration` and `MutatingWebhookConfiguration`,
  group/version `admissionregistration.k8s.io/v1`.
- **Fields to extract:** `metadata.name`, `webhooks[].name` (as `webhook_names`), and
  `webhooks[0].failurePolicy` (`Fail` | `Ignore`, reported verbatim).
- **Counts:** report the total count of each configuration kind.
- **Non-system filter:** for the per-webhook detail list, exclude system webhooks whose
  `metadata.name` matches `^(eks|vpc-resource|aws-)`; the total `count` still includes all.
- **RBAC verbs:** `get`, `list` on `validatingwebhookconfigurations`,
  `mutatingwebhookconfigurations`.

**Example facts (validating webhooks, non-system):**
```json
[
  {"name": "kyverno-resource-validating-webhook-cfg", "webhooks": ["validate.kyverno.svc"], "failurePolicy": "Fail"},
  {"name": "cert-manager-webhook", "webhooks": ["webhook.cert-manager.io"], "failurePolicy": "Fail"}
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
