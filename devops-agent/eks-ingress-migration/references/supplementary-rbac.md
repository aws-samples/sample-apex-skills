# Supplementary read-only ClusterRole (optional)

Ask the cluster owner to apply this if you want the webhook-exposure and Gateway API checks to resolve **definitively** instead of degrading to Unverified/unconfirmed. The assessment completes without it — it just reports less.

**This is an operator action.** The assessment never applies it; hand it to the cluster owner to run under their change-management process.

## Why it may be needed

Cluster reads come from an **EKS access entry** binding the Agent Space role to a cluster-access policy (`devops-agent/setup.sh` associates `AmazonAIOpsAssistantPolicy`).

> **Do not assume that policy's coverage — verify it.** As of 2026-08-30, `AmazonAIOpsAssistantPolicy` is listed among the available cluster-access policies in [Review access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html) but, unlike most policies on that page (`AmazonARCRegionSwitchScalingPolicy` is likewise unenumerated), **its rules are not enumerated there**. So the exact API groups it grants are **not** confirmable from an authoritative AWS source. This skill therefore treats **every** Kubernetes read as possibly denied and fails closed, rather than relying on assumed coverage.

Binding the ClusterRole below removes the guesswork: it grants exactly the reads this skill needs. Confirm the result with `kubectl auth can-i --as-group eks-ingress-migration ...` rather than assuming.

## Manifest

```yaml
# eks-ingress-migration-rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-ingress-migration
rules:
  # Gateway API adoption state (Option 1 readiness, topology gatewayApi block)
  - apiGroups: ["gateway.networking.k8s.io"]
    resources: ["gatewayclasses", "gateways", "httproutes", "grpcroutes", "referencegrants"]
    verbs: ["get", "list"]
  # Whether the Gateway API CRDs are installed, and at which version
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
  # ingress-nginx admission-webhook exposure (CVE-2025-1974 tri-state)
  - apiGroups: ["admissionregistration.k8s.io"]
    resources: ["validatingwebhookconfigurations"]
    verbs: ["get", "list"]
  # AWS LB Controller route ownership / IngressClassParams (self-managed LBC)
  - apiGroups: ["elbv2.k8s.aws"]
    resources: ["targetgroupbindings", "ingressclassparams"]
    verbs: ["get", "list"]
  # EKS Auto Mode managed load balancing (IngressClassParams in the managed group)
  - apiGroups: ["eks.amazonaws.com"]
    resources: ["ingressclassparams"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: eks-ingress-migration
subjects:
  - kind: Group
    name: eks-ingress-migration
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: eks-ingress-migration
  apiGroup: rbac.authorization.k8s.io
```

## Binding the group

Bind the group on the access entry (`--kubernetes-groups eks-ingress-migration`).

> `aws eks update-access-entry --kubernetes-groups` **replaces** the entry's group list rather than appending. If the role already carries groups from other tooling, pass them all in one comma-separated list.

**No Secret access is requested at any point.** TLS posture comes from the `secretName` references in `Ingress.spec.tls[]` plus the ACM inventory, never from key material.

## What stays degraded without it

| Read | Denied-path behaviour (fails closed) |
|------|--------------------------------------|
| `ValidatingWebhookConfiguration` | Webhook exposure is **Unverified → treated as exposed**, keeping the 🔴 5 CVE-2025-1974 band. Never reported "not exposed". |
| Gateway API objects / CRDs | Gateway API reported **unconfirmed** (`"gatewayApi": {"readStatus": "unconfirmed"}`). Never `crdsInstalled: false`, and never an "install the CRDs" recommendation on the strength of a `403`. |
