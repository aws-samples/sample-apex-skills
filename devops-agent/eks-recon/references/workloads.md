# Module: Workloads

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect running workloads — deployments, services, ingresses, jobs

**Note:** This is an optional module for migration assessments or workload inventory. Skip for basic infrastructure recon.

---

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [Deployments](#1-deployments)
  - [StatefulSets](#2-statefulsets)
  - [DaemonSets](#3-daemonsets)
  - [CronJobs and Jobs](#4-cronjobs-and-jobs)
  - [Services](#5-services)
  - [Ingresses](#6-ingresses)
  - [HPAs](#7-hpas)
  - [Pod Disruption Budgets](#8-pod-disruption-budgets)
  - [PriorityClasses](#9-priorityclasses)
  - [Vertical Pod Autoscalers](#10-vertical-pod-autoscalers)
  - [API Versions In Use](#11-api-versions-in-use)
- [Summary Statistics](#summary-statistics)
- [Output Schema](#output-schema)
- [Additional Fact Collection](#additional-fact-collection)
  - [Pod Phase and Replica Counts](#pod-phase-and-replica-counts)
  - [Resource Requests and Limits](#resource-requests-and-limits)
  - [Inventory Container Images](#inventory-container-images)
  - [PVCs (see storage module)](#pvcs-see-storage-module)
- [Edge Cases](#edge-cases)

---

## Access Model

This module reads facts almost entirely from the **Kubernetes API** — deployments,
statefulsets, daemonsets, cronjobs/jobs, services, ingresses, HPAs, PDBs, priority classes,
VPAs, and the live-resource apiVersion inventory are all in-cluster reads. Both sources are
read-only:

- **Kubernetes API** (via the Agent Space EKS access entry) — all workload, networking, and
  autoscaling resources below. Requires `authenticationMode` to include `API` and the
  `AmazonAIOpsAssistantPolicy` access entry to be present. RBAC verbs needed: `get`, `list`.
- **AWS control-plane APIs** — this module makes no AWS-API calls of its own; the shared
  `cluster:` block is sourced by `references/cluster-basics.md`.

If the Kubernetes API is unreachable (access entry absent), this module can produce almost
nothing — mark every workload sub-fact as `unconfirmed` in the report's Coverage section,
never as `false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes
> client)* below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They
> are **not executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its Kubernetes-API
> capability, then applies the described selection/aggregation logic.

---

## Detection Strategy

Workload inventory covers the following resource types. Start with Deployments (most common),
then expand based on what you find:

```
1.  Deployments        -> Long-running applications
2.  StatefulSets       -> Stateful applications
3.  DaemonSets         -> Node-level agents
4.  CronJobs/Jobs      -> Batch workloads
5.  Services           -> Network exposure
6.  Ingresses          -> External access
7.  HPAs               -> Horizontal autoscaling configuration
8.  PDBs               -> Pod disruption budgets
9.  PriorityClasses    -> Scheduling priority definitions
10. VPAs               -> Vertical autoscaling configuration (if CRD present)
11. API versions       -> apiVersions live resources use (raw fact list)
```

---

## Detection Capabilities

### 1. Deployments

Run this first to identify the main application workloads. Deployments are the most common
workload type and reveal the core services running in the cluster.

**Via Kubernetes API** — list Deployments across all namespaces:

- **Resource:** `Deployment`, group/version `apps/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.replicas`,
  `status.readyReplicas`, **all** `spec.template.spec.containers[].image` (not just
  `containers[0]` — a workload may run sidecars/proxies), `spec.template.spec.initContainers[].name`
  (empty list when none), `metadata.labels`.
- **Selection:** exclude namespaces beginning with `kube-`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

Iterate **all** `containers[].image` (a workload may run multiple containers — sidecars,
proxies), not just `containers[0]`. Record `init_containers` (names) per workload; empty
list when none.

**Example (one deployment):**
```json
{
  "namespace": "production",
  "name": "api-gateway",
  "replicas": 3,
  "ready": 3,
  "images": [
    "123456789012.dkr.ecr.us-west-2.amazonaws.com/api-gateway:v2.1.0",
    "docker.io/envoyproxy/envoy:v1.28.0"
  ],
  "init_containers": ["migrate-db"],
  "labels": {"app": "api-gateway", "team": "platform"}
}
```

### 2. StatefulSets

Check StatefulSets when you need to understand stateful applications like databases, message
queues, or caches. These require special handling during migrations due to persistent storage.

**Via Kubernetes API** — list StatefulSets across all namespaces:

- **Resource:** `StatefulSet`, group/version `apps/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.replicas`,
  `status.readyReplicas`, `spec.volumeClaimTemplates[].metadata.name` (→ `volume_claims`),
  `spec.volumeClaimTemplates[].spec.storageClassName` (→ `storage_class`),
  `spec.template.spec.initContainers[].name`.
- **RBAC verbs:** `get`, `list` on `statefulsets.apps`.

Capture the `volumeClaimTemplate` → `storageClassName` linkage: each StatefulSet volume
claim template names a storage class the pods provision volumes from. Record the storage
class per StatefulSet (`null` when the template omits it and the cluster default applies).

**Example (one statefulset):**
```json
{
  "namespace": "production",
  "name": "redis-cluster",
  "replicas": 3,
  "volume_claims": ["data"],
  "storage_class": "gp3"
}
```

### 3. DaemonSets

List DaemonSets to identify node-level agents (monitoring, logging, security). These run on
every node and reveal operational tooling in use.

**Via Kubernetes API** — list DaemonSets across all namespaces:

- **Resource:** `DaemonSet`, group/version `apps/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`,
  `status.desiredNumberScheduled` (→ `desired`), `status.numberReady` (→ `ready`).
- **RBAC verbs:** `get`, `list` on `daemonsets.apps`.

**Example (one daemonset):**
```json
{
  "namespace": "kube-system",
  "name": "aws-node",
  "desired": 5,
  "ready": 5
}
```

### 4. CronJobs and Jobs

Check batch workloads to understand scheduled tasks (backups, reports) and one-time jobs.
Important for understanding maintenance windows and resource usage patterns.

**Via Kubernetes API** — list CronJobs across all namespaces:

- **Resource:** `CronJob`, group/version `batch/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.schedule`,
  `spec.suspend`, `status.lastScheduleTime` (→ `last_schedule`, null if never run).
- **RBAC verbs:** `get`, `list` on `cronjobs.batch`.

**Via Kubernetes API** — list active/incomplete Jobs across all namespaces:

- **Resource:** `Job`, group/version `batch/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `status.active`,
  `status.failed`.
- **Selection:** count/list only jobs that have not completed successfully (i.e. not
  `status.succeeded == 1`).
- **RBAC verbs:** `get`, `list` on `jobs.batch`.

**Example (CronJob):**
```json
{
  "namespace": "production",
  "name": "db-backup",
  "schedule": "0 2 * * *",
  "suspend": false,
  "lastSchedule": "2026-04-22T02:00:00Z"
}
```

### 5. Services

List Services to understand network exposure. Services reveal how applications communicate
internally (ClusterIP) and externally (LoadBalancer, NodePort).

**Via Kubernetes API** — list Services across all namespaces:

- **Resource:** `Service`, group/version `v1` (core), all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.type`, `spec.ports[]`
  (format each as `"<port>/<protocol>"`), `spec.selector`.
- **Selection:** exclude namespaces beginning with `kube-`.
- **RBAC verbs:** `get`, `list` on `services`.

Record each service as a full entry (`name`, `type`, `ports`, `selector`), not only an
aggregate count by type.

> **Note:** The `services.by_type` field (counts per `ClusterIP`/`NodePort`/`LoadBalancer`)
> is aggregated by the agent from the enumerated services list above — no separate counting
> read is needed.

**Example (one service):**
```json
{
  "namespace": "production",
  "name": "api-gateway",
  "type": "LoadBalancer",
  "ports": ["443/TCP", "80/TCP"],
  "selector": {"app": "api-gateway"}
}
```

### 6. Ingresses

Check Ingresses to identify external access points and routing rules. Ingresses show domain
mappings, TLS configuration, and which services are publicly accessible.

**Via Kubernetes API** — list Ingresses across all namespaces:

- **Resource:** `Ingress`, group/version `networking.k8s.io/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.ingressClassName`
  (→ `class`), `spec.rules[].host` (→ `hosts`), and `tls_enabled` = `true` when
  `spec.tls` has one or more entries, else `false`.
- **RBAC verbs:** `get`, `list` on `ingresses.networking.k8s.io`.

`tls_enabled` = `true` when the ingress declares one or more `spec.tls` entries, else `false`.

**Example (one ingress):**
```json
{
  "namespace": "production",
  "name": "api-ingress",
  "class": "alb",
  "hosts": ["api.example.com", "api-internal.example.com"],
  "tls_enabled": true
}
```

### 7. HPAs

List Horizontal Pod Autoscalers to understand autoscaling configuration. HPAs reveal which
workloads scale automatically and their scaling thresholds.

**Via Kubernetes API** — list HPAs across all namespaces:

- **Resource:** `HorizontalPodAutoscaler`, group/version `autoscaling/v2`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.scaleTargetRef.name`
  (→ `target`), `spec.minReplicas`, `spec.maxReplicas`, `status.currentReplicas`,
  `spec.metrics[].type` (→ `metrics`).
- **RBAC verbs:** `get`, `list` on `horizontalpodautoscalers.autoscaling`.

**Example (one HPA):**
```json
{
  "namespace": "production",
  "name": "api-gateway-hpa",
  "target": "api-gateway",
  "minReplicas": 2,
  "maxReplicas": 10,
  "currentReplicas": 4,
  "metrics": ["Resource", "External"]
}
```

### 8. Pod Disruption Budgets

Enumerate PodDisruptionBudgets (PDBs) across namespaces. A PDB records the minimum
availability guarantee for the pods matched by its selector. Record existence, the
`minAvailable` / `maxUnavailable` value, and the label selector (the workloads it covers).

**Via Kubernetes API** — list PDBs across all namespaces (VERIFIED live: PDBs expose
MIN AVAILABLE / MAX UNAVAILABLE):

- **Resource:** `PodDisruptionBudget`, group/version `policy/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.minAvailable`,
  `spec.maxUnavailable`, `spec.selector.matchLabels` (→ `selector`).
- **RBAC verbs:** `get`, `list` on `poddisruptionbudgets.policy`.

Exactly one of `min_available` / `max_unavailable` is set per PDB; the other is `null`.
The `selector` matchLabels identify the covered workloads.

**Example (one PDB):**
```json
{
  "namespace": "production",
  "name": "api-gateway-pdb",
  "min_available": "1",
  "max_unavailable": null,
  "selector": {"app": "api-gateway"}
}
```

### 9. PriorityClasses

List PriorityClasses (cluster-scoped) to record scheduling priority definitions.

**Via Kubernetes API** — list PriorityClasses (cluster-scoped):

- **Resource:** `PriorityClass`, group/version `scheduling.k8s.io/v1`.
- **Fields to extract:** `metadata.name`, `value`, `globalDefault` (→ `global_default`).
- **RBAC verbs:** `get`, `list` on `priorityclasses.scheduling.k8s.io`.

**Example (one PriorityClass):**
```json
{
  "name": "high-priority",
  "value": 1000000,
  "global_default": false
}
```

### 10. Vertical Pod Autoscalers

List VerticalPodAutoscalers only if the CRD is present. VPA is an add-on CRD
(`verticalpodautoscalers.autoscaling.k8s.io`); guard the read so its absence is a clean
fact, not an error.

**Via Kubernetes API** — detect the CRD first, then list VPAs if present:

- **CRD check:** `CustomResourceDefinition`, group/version `apiextensions.k8s.io/v1`, name
  `verticalpodautoscalers.autoscaling.k8s.io`. Absence is a fact — record `detected: false`
  for the whole block and skip the list read.
- **Resource (if CRD present):** `VerticalPodAutoscaler`, group/version
  `autoscaling.k8s.io/v1`, all namespaces.
- **Fields to extract:** `metadata.namespace`, `metadata.name`, `spec.targetRef.name`
  (→ `target`), `spec.updatePolicy.updateMode` (→ `update_mode`).
- **RBAC verbs:** `get`, `list` on `customresourcedefinitions.apiextensions.k8s.io` and
  `verticalpodautoscalers.autoscaling.k8s.io`.

Record `detected: false` for the whole block when the CRD is absent.

**Example (one VPA):**
```json
{
  "namespace": "production",
  "name": "api-gateway-vpa",
  "target": "api-gateway",
  "update_mode": "Auto"
}
```

### 11. API Versions In Use

Enumerate the distinct `apiVersion` values that live resources in the cluster use, as a
**raw fact list**. This is inventory only.

> **Scope note:** Report the apiVersions verbatim. Do **not** flag any as deprecated,
> removed, or upgrade-blocking, and do not cross-reference them against a target Kubernetes
> version — that deprecation math belongs to the `eks-upgrade-check` skill, not recon.

**Via Kubernetes API** — read live resources across the common workload/config kinds and
collect their `apiVersion` values:

- **Resources:** `Deployment`, `StatefulSet`, `DaemonSet`, `ReplicaSet` (`apps/v1`);
  `CronJob`, `Job` (`batch/v1`); `Ingress`, `NetworkPolicy` (`networking.k8s.io/v1`);
  `HorizontalPodAutoscaler` (`autoscaling/v2`); `PodDisruptionBudget` (`policy/v1`) — all
  namespaces.
- **Aggregation:** collect `metadata`-level `apiVersion` (the served version each object was
  read as) across all items, then de-duplicate and sort into a distinct list. This is a
  raw union of the versions observed in use, nothing more.
- **RBAC verbs:** `get`, `list` on each resource above.

*Reference pseudocode (kubernetes client), not executable:*
```python
# Collect the served apiVersion of every live object across the common kinds,
# then de-duplicate. Raw inventory only — no deprecation classification.
versions = set()
for obj in live_workload_and_config_objects():   # deploy/sts/ds/rs/cronjob/job/ingress/hpa/pdb/netpol
    versions.add(obj["apiVersion"])
api_versions_in_use = sorted(versions)
```

**Example output:**
```
apps/v1
autoscaling/v2
batch/v1
networking.k8s.io/v1
policy/v1
```

---

## Summary Statistics

A high-level view of workload distribution across namespaces, for initial assessment before
diving into details. This is **aggregated by the agent** from the per-type Kubernetes-API
reads above (Deployments, StatefulSets, DaemonSets, Jobs) — no separate read is needed.
Group the collected objects by `metadata.namespace`, then within each namespace count total
objects and counts per `kind`.

**Example output:**
```json
[
  {
    "namespace": "production",
    "total": 12,
    "by_kind": {"Deployment": 8, "StatefulSet": 2, "DaemonSet": 2}
  },
  {
    "namespace": "staging",
    "total": 6,
    "by_kind": {"Deployment": 5, "Job": 1}
  }
]
```

---

## Output Schema

This is the **single canonical schema** for the workloads module — it carries every
workloads fact. The `workloads-recon` agent emits exactly this shape (plus the shared
`cluster:` block from `references/cluster-basics.md`). Use `null` where a fact was not
detected; never omit a key. Aggregate containers use the `{count, list}` wrapper.

> **PVCs are owned by the storage module.** This schema does not carry a `storage.pvcs`
> block — see the storage module for PVC inventory (status, storage class, capacity).

```yaml
workloads:
  summary:
    deployments: int
    statefulsets: int
    daemonsets: int
    cronjobs: int
    jobs: int
    services: int
    ingresses: int
    hpas: int
    pdbs: int
    namespaces_with_workloads: int

  by_namespace:
    - namespace: string
      deployments: int
      statefulsets: int
      services: int
      ingresses: int

  deployments:
    count: int
    list:
      - namespace: string
        name: string
        replicas: int
        ready: int                 # status.readyReplicas
        images: list               # ALL containers[].image
        init_containers: list      # initContainers[].name, [] when none
        labels: object

  statefulsets:
    count: int
    list:
      - namespace: string
        name: string
        replicas: int
        ready: int
        volume_claims: list        # volumeClaimTemplates[].metadata.name
        storage_class: string      # volumeClaimTemplates[].spec.storageClassName, null if unset
        init_containers: list

  daemonsets:
    count: int
    list:
      - namespace: string
        name: string
        desired: int               # status.desiredNumberScheduled
        ready: int                 # status.numberReady

  cronjobs:
    count: int
    list:
      - namespace: string
        name: string
        schedule: string
        suspend: bool
        last_schedule: string      # status.lastScheduleTime, null if never run

  jobs:
    count: int                     # active/incomplete jobs
    list:
      - namespace: string
        name: string
        active: int
        failed: int

  services:
    count: int
    by_type:
      cluster_ip: int
      load_balancer: int
      node_port: int
      external_name: int
    list:
      - namespace: string
        name: string
        type: string               # ClusterIP | NodePort | LoadBalancer | ExternalName
        ports: list                # ["443/TCP", ...]
        selector: object

  ingresses:
    count: int
    list:
      - namespace: string
        name: string
        class: string              # spec.ingressClassName
        hosts: list
        tls_enabled: bool          # true when spec.tls has >=1 entry

  hpas:
    count: int
    list:
      - namespace: string
        name: string
        target: string             # spec.scaleTargetRef.name
        min_replicas: int
        max_replicas: int
        current_replicas: int      # status.currentReplicas
        metrics: list              # spec.metrics[].type

  pdbs:
    count: int
    list:
      - namespace: string
        name: string
        min_available: string      # spec.minAvailable (one of min/max set, other null)
        max_unavailable: string    # spec.maxUnavailable
        selector: object           # spec.selector.matchLabels — covered workloads

  priority_classes:
    count: int
    list:
      - name: string
        value: int
        global_default: bool

  vpas:
    detected: bool                 # verticalpodautoscalers CRD present
    count: int
    list:
      - namespace: string
        name: string
        target: string             # spec.targetRef.name
        update_mode: string        # spec.updatePolicy.updateMode

  api_versions_in_use: list        # RAW distinct apiVersions used by live resources.
                                    # NOT flagged deprecated/removed — see Scope note in §11.

  images:
    unique:
      count: int
      list: list                   # unique image strings across pods
    by_registry:
      - registry: string           # normalized: bare "nginx" -> docker.io/library
        count: int
```

---

## Additional Fact Collection

Facts that feed the schema blocks above beyond the primary per-type listings. All are
Kubernetes-API reads with agent-side selection/aggregation.

### Pod Phase and Replica Counts

Enumerate pod phase and replica-vs-desired counts.

**Via Kubernetes API** — pods not in a healthy phase, and deployments not fully ready:

- **Resource:** `Pod`, group/version `v1` (core), all namespaces. Select pods whose
  `status.phase` is neither `Running` nor `Succeeded`; report `<namespace>/<name>: <phase>`.
- **Resource:** `Deployment`, group/version `apps/v1`, all namespaces. Select deployments
  where `status.readyReplicas != spec.replicas`; report `<namespace>/<name>: <ready>/<desired>`.
- **RBAC verbs:** `get`, `list` on `pods` and `deployments.apps`.

**Example output:**
```
production/api-gateway: 2/3
staging/worker: 0/2
```

### Resource Requests and Limits

Inventory pods that declare no resource requests (count).

**Via Kubernetes API** — count pods missing resource requests:

- **Resource:** `Pod`, group/version `v1` (core), all namespaces.
- **Selection:** a pod counts when any container has `resources.requests == null`;
  de-duplicate by `<namespace>/<name>` and count.
- **RBAC verbs:** `get`, `list` on `pods`.

**Example output:**
```
23
```

### Inventory Container Images

Enumerate unique images and image counts by registry.

**Via Kubernetes API** — read pod container images, then aggregate:

- **Resource:** `Pod`, group/version `v1` (core), all namespaces. Collect every
  `spec.containers[].image`.
- **Unique images:** de-duplicate and sort the collected image strings.
- **Images by registry:** bucket each image by its registry, applying Docker Hub
  normalization (below).
- **RBAC verbs:** `get`, `list` on `pods`.

**Registry normalization rule (agent-side selection logic):** a bare image reference like
`nginx` resolves to the Docker Hub library namespace, so bucket it under `docker.io/library`
(not under the literal first path segment). A two-segment reference whose first segment has
no `.` or `:` (e.g. `bitnami/redis`) is also a Docker Hub reference → `docker.io`. Otherwise
the first path segment is the registry host.

*Reference pseudocode (kubernetes client), not executable:*
```python
# Bucket collected pod container images by registry with Docker Hub normalization.
def registry(image):
    parts = image.split("/")
    if len(parts) == 1:                                   # bare "nginx"
        return "docker.io/library"
    if len(parts) == 2 and not any(c in parts[0] for c in ".:"):  # "bitnami/redis"
        return "docker.io"
    return parts[0]                                       # registry host present

images = [c.image for pod in pods for c in pod.spec.containers]
by_registry = Counter(registry(i) for i in images)
```

**Example output (images by registry):**
```json
[
  {"registry": "123456789012.dkr.ecr.us-west-2.amazonaws.com", "count": 15},
  {"registry": "docker.io", "count": 3},
  {"registry": "docker.io/library", "count": 2},
  {"registry": "quay.io", "count": 2}
]
```

### PVCs (see storage module)

PVC inventory (status, storage class, capacity) is owned by the **storage** module — see
`references/storage.md`. This module does not emit a `storage.pvcs` block. The StatefulSet
`volume_claims` / `storage_class` linkage above is the only volume fact workloads carries
(it records the volumeClaimTemplate → storage class wiring, not the bound PVCs).

---

## Edge Cases

### Exclude System Namespaces

Filter out system namespaces to focus on user workloads. Typically exclude:
- `kube-system`
- `kube-public`
- `kube-node-lease`
- `amazon-cloudwatch`
- `argocd` (unless specifically interested)

### Handle Large Clusters

For clusters with many workloads, avoid overwhelming output:
- Paginate results
- Focus on user namespaces
- Provide summary first, details on request

### Identify Orphaned Resources

Check for Services without matching pods to find potential cleanup opportunities or
misconfiguration.

**Via Kubernetes API** — list Services with a selector that may lack backing pods:

- **Resource:** `Service`, group/version `v1` (core), all namespaces.
- **Selection:** services where `spec.selector != null` and `spec.type != "ExternalName"`;
  report `namespace`, `name`, `selector`. Cross-reference against pods to find selectors
  with no matching pods.
- **RBAC verbs:** `get`, `list` on `services` and `pods`.
