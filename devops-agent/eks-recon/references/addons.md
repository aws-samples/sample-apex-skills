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
2. Helm releases        -> Installed via Helm, found from Helm's annotations on their resources (K8s API)
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

- `serviceAccountRoleArn` = the IRSA role bound to the add-on service account (null when no IRSA role). Per-add-on Pod Identity associations are separate and are not collected here.
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

> **No Secret reads.** Helm keeps each release record (chart, values, revision, status) in a
> Secret by default ([Helm storage backends](https://helm.sh/docs/topics/advanced/)). This
> skill never lists or gets Secrets. It reads the marks Helm puts on a release's own
> resources instead: on install, upgrade and rollback Helm sets the label
> `app.kubernetes.io/managed-by: Helm` and the annotations `meta.helm.sh/release-name` and
> `meta.helm.sh/release-namespace`. Helm v3.2.0 added the annotations, when it began adopting
> existing resources into a release ([Helm v3.2.0 release notes](https://github.com/helm/helm/releases/tag/v3.2.0)).

**Via Kubernetes API**: read the objects and keep only their metadata for Helm's marks:

- **Resource:** `Deployment`, `DaemonSet`, `StatefulSet` (group/version `apps/v1`) and `Service` (`v1`), all namespaces; `ConfigMap` (`v1`), all namespaces, label selector `app.kubernetes.io/managed-by=Helm` (so other ConfigMaps' data is not fetched).
- **Fields to extract:** annotation `meta.helm.sh/release-name` → release name; annotation `meta.helm.sh/release-namespace` → release namespace; label `helm.sh/chart` → `chart_labels` (verbatim, unique per release). Group objects by release namespace and name; one group is one release. An object labelled `app.kubernetes.io/managed-by: Helm` with no release annotations goes to `label_only` as `<kind>/<namespace>/<name>`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `daemonsets.apps`, `statefulsets.apps`, `services`, `configmaps`.

> **chart_labels note.** The chart's own templates set `helm.sh/chart`
> ([Helm label conventions](https://helm.sh/docs/chart_best_practices/labels/)), not Helm, so
> it can be absent. A release can show more than one value: its subcharts set their own, and
> an upgrade that fails part-way leaves some objects at the old chart, since Helm goes on
> updating a release's other objects when one update fails. It is not Helm's record of the
> chart version. `app.kubernetes.io/version`, where a chart sets it, is chart text in the same
> way, not Helm's record of the app version.

> **label_only note.** The `app.kubernetes.io/managed-by: Helm` label is chart text too: chart
> templates set it from `{{ .Release.Service }}`, which always renders `Helm`, also when Argo
> CD renders the chart with `helm template`
> ([Argo CD Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)) or someone runs
> `helm template | kubectl apply`. So `label_only` objects may belong to no Helm release.
> Never report them as releases; `count` leaves them out.

**What this does not report.** Chart version as Helm recorded it, app version, revision and
status are in Helm's release record, which this skill does not read. On a Flux-managed
release, the HelmRelease resource (`helm.toolkit.fluxcd.io`) carries status, chart version
and app version in its Ready condition and `status.history`
([Flux HelmRelease](https://fluxcd.io/flux/components/helm/helmreleases/)); this skill does
not read it, because the full object also holds `spec.values`, which can carry sensitive
values. A listed release is not known to be deployed: Helm applies a release's objects before
it marks the release failed, and `helm uninstall` leaves resources annotated
`helm.sh/resource-policy: keep` in place with their release annotations
([Helm chart tips](https://helm.sh/docs/howto/charts_tips_and_tricks/)), so a listed release
may be failed, pending or uninstalled. Helm does not annotate a chart's `crds/` CRDs or its
hooks, a release installed before Helm v3.2.0 and never upgraded since has no annotations,
and a chart that ships only kinds not read here (CRDs, Jobs, CronJobs, Ingresses, RBAC) is
not found. Report a release by name and namespace, and its `chart_labels` verbatim as
chart-set labels, never as the chart version Helm recorded. Scope an absence claim to the
kinds read: "no Helm-annotated Deployments, DaemonSets, StatefulSets, Services or
ConfigMaps", never "no Helm releases".

> **Coverage honesty:** report `helm_releases.count: 0` only when every read above ran and
> returned no Helm-annotated objects. If the Kubernetes API is unreachable or a read fails,
> emit `helm_releases: {unconfirmed: true, reason: "<kind> read failed: <error>"}` rather
> than a count of 0. Always add a Coverage line: `addons.helm_releases: found from Helm
> annotations on Deployments, DaemonSets, StatefulSets, Services and Helm-labelled
> ConfigMaps only; chart version, app version, revision and status not read (Helm release
> Secrets are not read); listed releases may be failed, pending or uninstalled`.

*Reference pseudocode (kubernetes client), not executable:*
```python
apps, core = client.AppsV1Api(), client.CoreV1Api()
# List items carry no kind, so pair each list with its kind.
objs = ([("Deployment", o) for o in apps.list_deployment_for_all_namespaces().items]
        + [("DaemonSet", o) for o in apps.list_daemon_set_for_all_namespaces().items]
        + [("StatefulSet", o) for o in apps.list_stateful_set_for_all_namespaces().items]
        + [("Service", o) for o in core.list_service_for_all_namespaces().items]
        + [("ConfigMap", o) for o in core.list_config_map_for_all_namespaces(
            label_selector="app.kubernetes.io/managed-by=Helm").items])
releases, label_only = {}, []
for kind, o in objs:
    ann, lab = o.metadata.annotations or {}, o.metadata.labels or {}
    name = ann.get("meta.helm.sh/release-name")
    if name:
        key = (ann.get("meta.helm.sh/release-namespace"), name)
        r = releases.setdefault(key, {"name": name, "namespace": key[0], "chart_labels": set()})
        if lab.get("helm.sh/chart"):
            r["chart_labels"].add(lab["helm.sh/chart"])
    elif lab.get("app.kubernetes.io/managed-by") == "Helm":
        label_only.append(f"{kind}/{o.metadata.namespace}/{o.metadata.name}")
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
        service_account_role: string  # serviceAccountRoleArn — IRSA role ARN; null = no IRSA role; per-add-on Pod Identity associations are not collected
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

  helm_releases:                    # from Helm's annotations on resources; no Secret is read
    count: int
    list:
      - name: string                # meta.helm.sh/release-name
        namespace: string           # meta.helm.sh/release-namespace
        chart_labels: list          # helm.sh/chart label values set by the chart, verbatim; [] if none
    label_only: list                # "<kind>/<namespace>/<name>": managed-by Helm, no release annotations
    # Chart version as Helm recorded it, app version, revision and status are in the
    # release Secret and are not read, so no field carries them.

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

Not reported: a release's status is in Helm's release record, which this skill does not
read. See "What this does not report" and the Coverage line in
[Helm Releases](#2-helm-releases); on Flux, the HelmRelease resource carries it.

### Orphaned Resources

Check for orphaned CRDs when an add-on uninstall may have been incomplete. Orphaned CRDs
can carry stale custom resources. Record CRDs whose group has no matching running
controller Deployment as a fact (cross-reference the CRD list from capability 4 against the
platform-component Deployments from capability 3); draw no conclusion.

**Via Kubernetes API** — the CRD list (capability 4, `customresourcedefinitions.apiextensions.k8s.io`) and the Deployment list (capability 3, `deployments.apps`) together provide the cross-reference. Group each CRD by its API group suffix and note groups with no controller Deployment. RBAC: `get`, `list` on both resources.
