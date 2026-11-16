# Module: Add-ons

> **Part of:** [eks-recon](../SKILL.md)
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
- **CLI fallback:** `aws eks`, `kubectl`

---

## Detection Strategy

Add-ons can be installed via multiple mechanisms:

```
1. EKS-managed add-ons  -> AWS manages lifecycle, uses EKS add-on API
2. Helm releases        -> Installed via Helm, found from Helm's annotations on their resources
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

Use Helm detection when you need to inventory third-party components that were installed via Helm charts. Many platform teams use Helm for add-ons not available as EKS-managed add-ons.

> **No Secret reads.** Helm keeps each release record (chart, values, revision, status) in a
> Secret by default ([Helm storage backends](https://helm.sh/docs/topics/advanced/)).
> `helm list`, `helm get`, `helm status` and `helm history` read those records, so
> this skill runs none of them and never lists Secrets. It reads the marks Helm puts on a
> release's own resources instead: on install, upgrade and rollback Helm sets the label
> `app.kubernetes.io/managed-by: Helm` and the annotations `meta.helm.sh/release-name` and
> `meta.helm.sh/release-namespace`. Helm v3.2.0 added the annotations, when it began adopting
> existing resources into a release ([Helm v3.2.0 release notes](https://github.com/helm/helm/releases/tag/v3.2.0)).

**MCP:** Helm releases: CLI only. The MCP tool returns annotations whole ([eks-mcp-server k8s_handler.py](https://github.com/awslabs/mcp/blob/c3d28b016ac5fec02a8f8954b86ab273a5a0ba5d/src/eks-mcp-server/awslabs/eks_mcp_server/k8s_handler.py#L613)), and `last-applied-configuration` can hold the full object ([Kubernetes declarative configuration](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/)).

**CLI:**
```bash
# kubectl returns full objects (pod-template env values, Helm-managed ConfigMap data). They
# go to a private temp dir, removed on success and on failure; only metadata reaches the
# output. ConfigMaps are filtered server-side to Helm-managed ones, so other ConfigMaps'
# data is not fetched. jq runs only when both reads succeed, and the exit code is kept.
d=$(mktemp -d) \
  && kubectl get deployments,daemonsets,statefulsets,services -A -o json > "$d/objects.json" \
  && kubectl get configmaps -A -l app.kubernetes.io/managed-by=Helm -o json > "$d/configmaps.json" \
  && jq -s '
  [.[].items[]
   | {kind, namespace: .metadata.namespace, name: .metadata.name,
      release: .metadata.annotations["meta.helm.sh/release-name"],
      release_namespace: .metadata.annotations["meta.helm.sh/release-namespace"],
      managed_by: .metadata.labels["app.kubernetes.io/managed-by"],
      chart_label: (.metadata.labels["helm.sh/chart"] // .metadata.labels.chart)}
   | select(.release != null or .managed_by == "Helm")]
  | {count: ([.[] | select(.release != null)] | group_by([.release_namespace, .release]) | length),
     list: ([.[] | select(.release != null)] | group_by([.release_namespace, .release])
            | map({name: .[0].release, namespace: .[0].release_namespace,
                   chart_labels: ([.[].chart_label | select(. != null)] | unique)})),
     label_only: [.[] | select(.release == null) | "\(.kind)/\(.namespace)/\(.name)"]}' \
  "$d/objects.json" "$d/configmaps.json"; rc=$?; rm -rf "$d"; (exit "$rc")
```

**Example output:**
```json
{
  "count": 1,
  "list": [
    {
      "name": "external-dns",
      "namespace": "external-dns",
      "chart_labels": ["external-dns-1.13.1"]
    }
  ],
  "label_only": ["DaemonSet/monitoring/node-agent"]
}
```

- `chart_labels` holds the `helm.sh/chart` label values on the release's objects, else the legacy `chart` label's (kube-prometheus-stack sets only `chart:`), verbatim.
  The chart's own templates set that label ([Helm label conventions](https://helm.sh/docs/chart_best_practices/labels/)),
  not Helm, so it can be absent. A release can show more than one value: its subcharts set
  their own, and an upgrade that fails part-way leaves some objects at the old chart, since
  Helm goes on updating a release's other objects when one update fails. It is not Helm's
  record of the chart version. `app.kubernetes.io/version`, where a chart sets it, is chart
  text in the same way, not Helm's record of the app version.
- `label_only` lists objects labelled `app.kubernetes.io/managed-by: Helm` that carry no
  release annotations. That label is chart text too: chart templates set it from
  `{{ .Release.Service }}`, which always renders `Helm`, also when Argo CD renders the chart
  with `helm template` ([Argo CD Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/))
  or someone runs `helm template | kubectl apply`. So these objects may belong to no Helm
  release. Never report them as releases; `count` leaves them out.

**What this does not report.** Chart version as Helm recorded it, app version, revision and
status are in Helm's release record, which this skill does not read. On a Flux-managed
release, the HelmRelease resource (`helm.toolkit.fluxcd.io`) carries status and chart
version in its Ready condition, and app version in `status.history`
([Flux HelmRelease](https://fluxcd.io/flux/components/helm/helmreleases/)); this skill does
not read it. A listed release is not known to be deployed: Helm applies a release's objects before
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

> **Coverage honesty:** report `helm_releases.count: 0` only when both reads ran and
> returned no Helm-annotated objects. If either read fails, emit
> `helm_releases: {unconfirmed: true, reason: "<kind> read failed: <error>"}` rather than a
> count of 0. Always add a Coverage line: `addons.helm_releases: found from Helm annotations
> on Deployments, DaemonSets, StatefulSets, Services and Helm-labelled ConfigMaps only; chart
> version, app version, revision and status not read (Helm release Secrets are not read);
> listed releases may be failed, pending or uninstalled`.

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
        chart_labels: list          # helm.sh/chart (else legacy chart) label values set by the chart, verbatim; [] if none
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

Not reported: a release's status is in Helm's release record, which this skill does not
read. See "What this does not report" and the Coverage line in
[Helm Releases](#2-helm-releases); on Flux, the HelmRelease resource carries it.

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
