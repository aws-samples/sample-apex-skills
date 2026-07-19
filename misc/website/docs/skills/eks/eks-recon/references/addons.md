---
title: "Module: Add-ons"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/addons.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/addons.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/addons.md). Edit the source, not this page.
:::

# Module: Add-ons

> **Part of:** [eks-recon](../)
> **Purpose:** Detect add-on inventory - EKS-managed add-ons, Helm releases, manifest-installed components

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [EKS-Managed Add-ons](#1-eks-managed-add-ons)
  - [Helm Releases](#2-helm-releases)
  - [Common Platform Components](#3-common-platform-components)
  - [Custom Resource Definitions](#4-custom-resource-definitions-crds)
- [Output Schema](#output-schema)
- [Add-on Status](#add-on-status)
- [Edge Cases](#edge-cases)
  - [Self-Managed vs EKS-Managed](#self-managed-vs-eks-managed)
  - [Add-on Update Availability](#add-on-update-availability-raw-fact)
  - [Helm Release in Pending State](#helm-release-in-pending-state)
  - [Orphaned Resources](#orphaned-resources)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `list_eks_resources`, `describe_eks_resource`, `list_k8s_resources`
- **CLI fallback:** `aws eks`, `kubectl`, `helm`

---

## Detection Strategy

Add-ons can be installed via multiple mechanisms:

```
1. EKS-managed add-ons  -> AWS manages lifecycle, uses EKS add-on API
2. Helm releases        -> Installed via Helm, tracked in secrets
3. Manifest-installed   -> Raw YAML applied, no tracking metadata
4. Operator-managed     -> CRDs and controllers (e.g., cert-manager)
```

---

## Detection Commands

### 1. EKS-Managed Add-ons

**MCP:**
```
list_eks_resources(
  resource_type="addon",
  cluster_name="<cluster-name>"
)
```

For each add-on:
```
describe_eks_resource(
  resource_type="addon",
  cluster_name="<cluster-name>",
  resource_name="<addon-name>"
)
```

**CLI:**
```bash
# List all EKS-managed add-ons
aws eks list-addons --cluster-name <cluster-name> --query 'addons'

# Get details for each add-on (includes serviceAccountRoleArn + health.issues)
aws eks describe-addon --cluster-name <cluster-name> --addon-name <addon-name> \
  --query 'addon.{
    name:addonName,
    version:addonVersion,
    status:status,
    serviceAccountRoleArn:serviceAccountRoleArn,
    configurationValues:configurationValues,
    healthIssues:health.issues
  }'
```

- `serviceAccountRoleArn` = the Pod Identity / IRSA role bound to the add-on (null when none).
- `health.issues` = AWS-reported add-on health issues, a list of `{code, message, resourceIds}`.
  Capture verbatim as a raw fact (empty list = no reported issues); draw no conclusion.

**Core EKS add-ons to check:**
- `vpc-cni` (Amazon VPC CNI)
- `coredns` (DNS resolution)
- `kube-proxy` (Service networking)
- `aws-ebs-csi-driver` (EBS volumes)
- `aws-efs-csi-driver` (EFS volumes)
- `eks-pod-identity-agent` (Pod Identity)
- `amazon-cloudwatch-observability` (Container Insights)
- `aws-mountpoint-s3-csi-driver` (S3 mounts)
- `snapshot-controller` (Volume snapshots)

### 2. Helm Releases

Use Helm detection when you need to inventory third-party components that were installed via Helm charts. Many platform teams use Helm for add-ons not available as EKS-managed add-ons.

**CLI (Helm required):**
```bash
# List all Helm releases across namespaces.
# `chart` carries the chart name+version (e.g. external-dns-1.13.1); `app_version` is the
# packaged app version (e.g. 0.13.6); `revision` is the release revision counter. Keep them distinct.
helm list -A --output json 2>/dev/null | jq -r '.[] | {name: .name, namespace: .namespace, chart: .chart, app_version: .app_version, revision: .revision, status: .status}'
```

**Example output:**
```json
{
  "name": "aws-load-balancer-controller",
  "namespace": "kube-system",
  "chart": "aws-load-balancer-controller-1.6.2",
  "app_version": "v2.6.2",
  "revision": "1",
  "status": "deployed"
}
{
  "name": "external-dns",
  "namespace": "external-dns",
  "chart": "external-dns-1.13.1",
  "app_version": "0.13.6",
  "revision": "1",
  "status": "deployed"
}
```

**Alternative (kubectl, no Helm CLI):**

Use this approach when Helm CLI is not installed but you still need to detect Helm-managed releases. Helm stores release metadata as Kubernetes secrets.

> **Coverage honesty:** if the Helm CLI is absent, you MUST run the kubectl secret-based fallback below before reporting Helm releases. Do NOT report `helm_releases.count: 0` when `helm` simply isn't installed and the fallback wasn't run — that reports "no releases" when the truth is "not checked". If neither `helm` nor the kubectl fallback can run, emit `helm_releases: {unconfirmed: true, reason: "helm CLI absent and secret fallback unavailable"}` rather than a count of 0.

```bash
# Helm stores releases as secrets with label owner=helm.
# NOTE: the "version" label is the RELEASE REVISION (a counter), NOT the chart or app version.
# Chart version and app_version are NOT available from labels alone — they live inside the
# gzipped release blob (.data.release). Use `helm list` above to get chart + app_version.
kubectl get secrets -A -l owner=helm,status=deployed -o json 2>/dev/null | \
  jq -r '.items[] | {
    name: .metadata.labels["name"],
    namespace: .metadata.namespace,
    revision: .metadata.labels["version"]
  }'
```

### 3. Common Platform Components

Check for common components that may be manifest-installed:

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Deployment",
  api_version="apps/v1",
  namespace="kube-system"
)
```

**CLI:**
```bash
# List deployments in kube-system
kubectl get deploy -n kube-system -o json | jq -r '.items[].metadata.name'

# List deployments across all namespaces with common labels
kubectl get deploy -A -o json | jq -r '
  .items[] | 
  select(.metadata.labels["app.kubernetes.io/name"] != null) |
  {
    name: .metadata.labels["app.kubernetes.io/name"],
    namespace: .metadata.namespace,
    component: .metadata.labels["app.kubernetes.io/component"]
  }'
```

**Common components to detect:**
- AWS Load Balancer Controller
- External DNS
- Cert-Manager
- Metrics Server
- Cluster Autoscaler
- Karpenter (covered in compute module)
- External Secrets Operator
- Secrets Store CSI Driver

### 4. Custom Resource Definitions (CRDs)

Check CRDs to identify operators and controllers that extend Kubernetes functionality. CRDs reveal what platform capabilities are available even when the component was installed via raw manifests without Helm tracking.

```bash
# List all CRDs (indicates operators/controllers)
kubectl get crds -o json | jq -r '.items[].metadata.name' | sort
```

**Example output:**
```
certificates.cert-manager.io
clusterissuers.cert-manager.io
externalsecrets.external-secrets.io
issuers.cert-manager.io
nodepools.karpenter.sh
provisioners.karpenter.sh
secretstores.external-secrets.io
```

**Common CRD patterns:**
- `*.cert-manager.io` -> cert-manager
- `*.argoproj.io` -> ArgoCD
- `*.karpenter.sh` -> Karpenter
- `*.external-secrets.io` -> External Secrets
- `*.kyverno.io` -> Kyverno
- `*.gatekeeper.sh` -> OPA Gatekeeper
- `*.istio.io` -> Istio

---

## Output Schema

This is the **single canonical schema** for the add-ons module — it carries every add-on
fact. The `addons-recon` agent emits exactly this shape (plus the shared `cluster:` block
from `references/cluster-basics.md`). Use `null` where a fact was not detected; never omit a
key. All fields are raw facts — no compatibility assessment, no upgrade verdicts.

```yaml
addons:
  eks_managed:
    count: int
    list:
      - name: string
        version: string             # addonVersion (installed)
        status: string              # AWS-reported: ACTIVE, CREATING, UPDATING, DEGRADED, DELETING (fact)
        service_account_role: string  # serviceAccountRoleArn — Pod Identity/IRSA role ARN, null if none
        configuration: object       # configurationValues, null if none
        health_issues: list         # health.issues: [{code, message, resource_ids}], [] if none (fact)
        latest_version: string      # first entry from describe-addon-versions at CURRENT k8s version (fact)
        update_available: bool      # latest_version != installed version (raw fact only; NOT an upgrade verdict)

  # Delivery mechanism for the core trio (vpc-cni, coredns, kube-proxy) so a self-managed
  # core component is not silently absent (it would not appear under eks_managed).
  core_components:
    vpc_cni:
      detected: bool
      version: string
      managed_by: string            # eks-addon | self-managed | auto-mode
    coredns:
      detected: bool
      version: string
      managed_by: string            # eks-addon | self-managed | auto-mode
    kube_proxy:
      detected: bool
      version: string
      managed_by: string            # eks-addon | self-managed | auto-mode

  helm_releases:
    count: int
    list:
      - name: string
        namespace: string
        chart: string               # chart name+version, e.g. external-dns-1.13.1
        app_version: string         # packaged app version (helm list .app_version), null if label-only extraction
        revision: string            # release revision counter (helm .revision / secret "version" label) — NOT chart/app version
        status: string              # deployed, failed, pending-*

  platform_components:
    aws_load_balancer_controller:
      detected: bool
      version: string
      namespace: string
    external_dns:
      detected: bool
      version: string
      namespace: string
    cert_manager:
      detected: bool
      version: string
      namespace: string
    metrics_server:
      detected: bool
      version: string
      namespace: string
    external_secrets:
      detected: bool
      version: string
      namespace: string
    secrets_store_csi:
      detected: bool
      version: string
      namespace: string
    cluster_autoscaler:
      detected: bool
      version: string
      namespace: string

  crds:
    count: int
    notable: list                   # CRDs that indicate specific tools
```

> **`auto_mode_features` resolved:** the old `auto_mode_features` block (elb/block_storage/compute
> booleans) was an unbacked orphan in the agent file — no detection command ever populated it, and
> those facts belong to compute (`auto_mode.node_pools`) and storage. It is DROPPED here rather than
> kept as an always-null field. Auto Mode delivery of vendored CNI/DNS is captured via
> `core_components[].managed_by: auto-mode`.

---

## Add-on Status

Capture add-on status as a raw fact. The AWS-reported add-on `status` field
(ACTIVE/DEGRADED/etc.) and `health.issues` are AWS's own fields — record them verbatim.
Draw no conclusion about whether action is needed.

For each EKS-managed add-on, capture status:

```bash
# Check if add-on pods are running
kubectl get pods -n kube-system -l "app.kubernetes.io/name=<addon-name>" \
  --field-selector status.phase!=Running 2>/dev/null
```

**Example output (healthy - no results):**
```
No resources found in kube-system namespace.
```

**Example output (unhealthy):**
```
NAME                       READY   STATUS             RESTARTS   AGE
coredns-7f89c5b6d8-abc12   0/1     CrashLoopBackOff   5          10m
```

**Status interpretation:**
- `ACTIVE` - Add-on is healthy
- `CREATING` - Add-on is being installed
- `UPDATING` - Add-on is being updated
- `DEGRADED` - Add-on has issues (check pod status)
- `DELETING` - Add-on is being removed

---

## Edge Cases

### Self-Managed vs EKS-Managed

Some add-ons can be installed both ways. The core trio (`vpc-cni`, `coredns`, `kube-proxy`)
can run as an EKS-managed add-on, self-managed (raw manifest/Helm), or be replaced by Auto
Mode. Record the delivery mechanism per core component as a `managed_by` fact so a
self-managed core component is not silently absent from the report (it would not appear in
`aws eks list-addons`).

- Check EKS add-on API first (`aws eks list-addons`). If the component appears → `managed_by: eks-addon`.
- If not in the add-on list but the workload exists in-cluster → `managed_by: self-managed`.
- On Auto Mode clusters the vendored CNI/DNS are EKS-operated; no `aws-node` DaemonSet and
  a `vpc-cni` ResourceNotFound from describe-addon is expected → `managed_by: auto-mode`.

```bash
# Example: VPC CNI might be self-managed
kubectl get daemonset -n kube-system aws-node -o jsonpath='{.metadata.labels}' 2>/dev/null
```

**Example output (EKS-managed):**
```json
{"app.kubernetes.io/managed-by":"eks","app.kubernetes.io/name":"aws-node"}
```

**Example output (self-managed - no eks label):**
```json
{"app":"aws-node","k8s-app":"aws-node"}
```

### Add-on Update Availability (raw fact)

Capture whether a newer add-on version exists as a RAW FACT ONLY. Query the versions
available for the add-on at the cluster's CURRENT Kubernetes version and compare the
installed version against the latest returned. Do NOT compute compatibility with any
target/upgrade Kubernetes version, and do NOT state whether an upgrade should happen —
that assessment belongs to the eks-upgrade-check skill.

```bash
# List versions available for the add-on at the cluster's CURRENT k8s version.
# The first entry is the latest available version for that k8s version.
aws eks describe-addon-versions \
  --addon-name vpc-cni \
  --kubernetes-version <cluster-current-version> \
  --query 'addons[0].addonVersions[].addonVersion'
```

**Example output:**
```json
[
    "v1.15.1-eksbuild.1",
    "v1.15.0-eksbuild.2",
    "v1.14.1-eksbuild.1"
]
```

Record `latest_version` = the first element, and `update_available` = (`latest_version`
!= the installed `addonVersion`). These are facts about version strings only.

### Helm Release in Pending State

Detect stuck Helm releases before upgrades. Pending releases indicate failed or interrupted installations that can block subsequent operations on the same release.

```bash
# Check for stuck Helm releases
helm list -A --pending --output json 2>/dev/null
```

**Example output (stuck release):**
```json
[{
  "name": "failed-release",
  "namespace": "default",
  "status": "pending-install",
  "chart": "my-chart-1.0.0"
}]
```

### Orphaned Resources

Check for orphaned CRDs when you suspect incomplete add-on uninstalls. Orphaned CRDs can cause confusion during reinstallation and may contain stale custom resources.

```bash
# Check for CRDs without controller
kubectl get crds -o json | jq -r '
  .items[] | 
  select(.status.conditions[].type == "NamesAccepted" and .status.conditions[].status == "True") |
  .metadata.name'
```

Cross-reference with running deployments to identify orphans:
```bash
# List CRDs and check if their controller exists
kubectl get crds -o name | while read crd; do
  group=$(echo $crd | sed 's/.*\.//')
  echo "CRD: $crd"
done
```
