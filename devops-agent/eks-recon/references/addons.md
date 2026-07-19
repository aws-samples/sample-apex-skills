# Module: Add-ons

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect add-on inventory — EKS-managed add-ons, Helm releases, manifest-installed components

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. EKS-Managed Add-ons](#1-eks-managed-add-ons)
  - [2. Helm Releases](#2-helm-releases)
  - [3. Common Platform Components](#3-common-platform-components)
  - [4. Custom Resource Definitions (CRDs)](#4-custom-resource-definitions-crds)
- [Output Schema](#output-schema)
- [Add-on Status](#add-on-status)
- [Edge Cases](#edge-cases)
  - [Self-Managed vs EKS-Managed](#self-managed-vs-eks-managed)
  - [Add-on Update Availability](#add-on-update-availability-raw-fact)
  - [Helm Release in Pending State](#helm-release-in-pending-state)
  - [Orphaned Resources](#orphaned-resources)

---

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS) — the EKS-managed add-on inventory and per-add-on
  detail: `eks:ListAddons`, `eks:DescribeAddon` (installed version, status,
  `serviceAccountRoleArn`, `health.issues`, `configurationValues`) and
  `eks:DescribeAddonVersions` (latest version at the current Kubernetes version →
  `update_available`). Requires the read-only permissions in `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — `platform_components`,
  `core_components` in-cluster delivery/`managed_by`, `helm_releases`, and CRDs. Requires
  `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry
  to be present. RBAC verbs needed: `get`, `list`.

If the Kubernetes API is unreachable (access entry absent), report the AWS-API facts
(`eks_managed`, and `core_components` entries confirmed via the add-on API) and mark every
K8s-dependent sub-fact (`platform_components.*`, `helm_releases`, self-managed
`core_components`, `crds`) as `unconfirmed` in the report's Coverage section — never as
`false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes client)*
> below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They are
> **not executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its Kubernetes-API
> capability.

---

## Detection Strategy

Add-ons can be installed via multiple mechanisms:

```
1. EKS-managed add-ons  -> AWS manages lifecycle, uses EKS add-on API (AWS API)
2. Helm releases        -> Installed via Helm, tracked in Kubernetes secrets (K8s API)
3. Manifest-installed   -> Raw YAML applied, no tracking metadata (K8s API)
4. Operator-managed     -> CRDs and controllers, e.g. cert-manager (K8s API)
```

---

## Detection Capabilities

### 1. EKS-Managed Add-ons

**Via AWS API** — list EKS-managed add-ons, then describe each one:

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

Inventory third-party components installed via Helm charts. Many platform teams use Helm
for add-ons not available as EKS-managed add-ons.

Helm stores each release's metadata as a Kubernetes `Secret` labeled `owner=helm`. In the
Agent Space there is no `helm` CLI, so **the Kubernetes-API read of these secrets IS the
primary Helm-detection path** (not a fallback).

**Via Kubernetes API** — list Helm release secrets:

- **Resource:** `Secret`, group/version `v1` (core), label selector `owner=helm,status=deployed`, all namespaces.
- **Fields to extract:** label `name` → release name; `metadata.namespace` → namespace; label `version` → release **revision** (a counter, NOT the chart or app version).
- **RBAC verbs:** `get`, `list` on `secrets`.

> **Chart / app_version note.** The `version` label is the RELEASE REVISION only. Chart
> version and `app_version` are NOT available from labels alone — they live inside the
> gzipped release blob (`.data.release`). When only the secret labels are read, populate
> `revision` and leave `chart`/`app_version` null rather than guessing. Keep `chart`
> (chart name+version, e.g. `external-dns-1.13.1`), `app_version` (packaged app version,
> e.g. `0.13.6`), and `revision` (release revision counter) distinct.

> **Coverage honesty:** report `helm_releases.count: 0` ONLY when the secret read ran and
> returned no `owner=helm` secrets. If the Kubernetes API is unreachable and the secret
> read could not run, emit `helm_releases: {unconfirmed: true, reason: "Kubernetes API
> unreachable; helm release secrets not read"}` rather than a count of 0 — that would
> report "no releases" when the truth is "not checked".

*Reference pseudocode (kubernetes client), not executable:*
```python
v1 = client.CoreV1Api()
secrets = v1.list_secret_for_all_namespaces(
    label_selector="owner=helm,status=deployed")
releases = [{
    "name": s.metadata.labels.get("name"),
    "namespace": s.metadata.namespace,
    "revision": s.metadata.labels.get("version"),  # release revision counter, NOT chart/app version
} for s in secrets.items]
```

### 3. Common Platform Components

Detect common components that may be manifest-installed (they would not appear under the
EKS add-on API).

**Via Kubernetes API** — list Deployments and read their identifying labels:

- **Resource:** `Deployment`, group/version `apps/v1`, all namespaces.
- **Fields to extract:** `metadata.labels["app.kubernetes.io/name"]` → component name; `metadata.namespace`; `metadata.labels["app.kubernetes.io/component"]`; the container image tag → version.
- **RBAC verbs:** `get`, `list` on `deployments.apps` (cluster-wide).

**Common components to detect:**
- AWS Load Balancer Controller
- External DNS
- Cert-Manager
- Metrics Server
- Cluster Autoscaler
- Karpenter (covered in compute module)
- External Secrets Operator
- Secrets Store CSI Driver

*Reference pseudocode (kubernetes client), not executable:*
```python
apps = client.AppsV1Api()
components = []
for d in apps.list_deployment_for_all_namespaces().items:
    labels = d.metadata.labels or {}
    name = labels.get("app.kubernetes.io/name")
    if not name:
        continue
    components.append({
        "name": name,
        "namespace": d.metadata.namespace,
        "component": labels.get("app.kubernetes.io/component"),
    })
```

### 4. Custom Resource Definitions (CRDs)

CRDs identify operators and controllers that extend Kubernetes. They reveal what platform
capabilities are present even when the component was installed via raw manifests without
Helm tracking.

**Via Kubernetes API** — list CRDs:

- **Resource:** `CustomResourceDefinition`, group/version `apiextensions.k8s.io/v1`.
- **Fields to extract:** `metadata.name` for each CRD.
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io`.

**Example CRD names observed:**
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
        app_version: string         # packaged app version, null if only the release-secret label is available
        revision: string            # release revision counter (from the release-secret "version" label) — NOT chart/app version
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

Per-add-on pod health can be corroborated via the Kubernetes API:

**Via Kubernetes API** — list the add-on's pods and read their phase:

- **Resource:** `Pod`, group/version `v1` (core), namespace `kube-system`, label selector `app.kubernetes.io/name=<addon-name>`.
- **Fields to extract:** `status.phase` per pod (a pod not in `Running` indicates the add-on is degraded — a fact, not a verdict).
- **RBAC verbs:** `get`, `list` on `pods`.

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

- Check the EKS add-on API first (`aws eks list-addons`). If the component appears → `managed_by: eks-addon`.
- If not in the add-on list but the workload exists in-cluster → `managed_by: self-managed`.
- On Auto Mode clusters the vendored CNI/DNS are EKS-operated; no `aws-node` DaemonSet and
  a `vpc-cni` ResourceNotFound from describe-addon is expected → `managed_by: auto-mode`.

**Via Kubernetes API** — distinguish self-managed from EKS-managed for a core component:

- **Resource:** `DaemonSet`, group/version `apps/v1`, namespace `kube-system`, name `aws-node` (VPC CNI example).
- **Fields to extract:** `metadata.labels` — the label `app.kubernetes.io/managed-by=eks` indicates EKS-managed; its absence with a bare `app`/`k8s-app` label indicates self-managed.
- **RBAC verbs:** `get`, `list` on `daemonsets.apps`.

**Example (EKS-managed labels):**
```json
{"app.kubernetes.io/managed-by":"eks","app.kubernetes.io/name":"aws-node"}
```

**Example (self-managed — no eks label):**
```json
{"app":"aws-node","k8s-app":"aws-node"}
```

### Add-on Update Availability (raw fact)

Capture whether a newer add-on version exists as a RAW FACT ONLY. Query the versions
available for the add-on at the cluster's CURRENT Kubernetes version and compare the
installed version against the latest returned. Do NOT compute compatibility with any
target/upgrade Kubernetes version, and do NOT state whether an upgrade should happen —
that assessment belongs to the eks-upgrade-check skill.

**Via AWS API** — list add-on versions at the current Kubernetes version:

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
!= the installed `addonVersion`). These are facts about version strings only — NOT an
"should upgrade" verdict.

### Helm Release in Pending State

Detect stuck Helm releases as a fact. Pending releases indicate failed or interrupted
installations. A release secret with a `status` label other than `deployed` (e.g.
`pending-install`, `pending-upgrade`, `failed`) surfaces this.

**Via Kubernetes API** — list Helm release secrets in a non-deployed state:

- **Resource:** `Secret`, group/version `v1` (core), label selector `owner=helm`, all namespaces.
- **Fields to extract:** label `status` (values other than `deployed` — e.g. `pending-install`, `pending-upgrade`, `failed`); label `name`; `metadata.namespace`; label `version` (revision).
- **RBAC verbs:** `get`, `list` on `secrets`.

Record the release name, namespace, and status verbatim; draw no conclusion.

### Orphaned Resources

Check for orphaned CRDs when an add-on uninstall may have been incomplete. Orphaned CRDs
can carry stale custom resources. Record CRDs whose group has no matching running
controller Deployment as a fact (cross-reference the CRD list from capability 4 against the
platform-component Deployments from capability 3); draw no conclusion.

**Via Kubernetes API** — the CRD list (capability 4, `customresourcedefinitions.apiextensions.k8s.io`) and the Deployment list (capability 3, `deployments.apps`) together provide the cross-reference. Group each CRD by its API group suffix and note groups with no controller Deployment. RBAC: `get`, `list` on both resources.
