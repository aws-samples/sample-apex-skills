# Module: Workloads

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect running workloads - deployments, services, ingresses, jobs

**Note:** This is an optional module for migration assessments or workload inventory. Skip for basic infrastructure recon.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Understand the Detection Strategy](#understand-the-detection-strategy)
3. [List Workloads by Type](#list-workloads-by-type)
   - [List Deployments](#1-list-deployments)
   - [List StatefulSets](#2-list-statefulsets)
   - [List DaemonSets](#3-list-daemonsets)
   - [List CronJobs and Jobs](#4-list-cronjobs-and-jobs)
   - [List Services](#5-list-services)
   - [List Ingresses](#6-list-ingresses)
   - [List HPAs](#7-list-hpas)
   - [List Pod Disruption Budgets](#8-list-pod-disruption-budgets)
   - [List PriorityClasses](#9-list-priorityclasses)
   - [List Vertical Pod Autoscalers](#10-list-vertical-pod-autoscalers)
   - [Enumerate API Versions In Use](#11-enumerate-api-versions-in-use)
4. [Generate Summary Statistics](#generate-summary-statistics)
5. [Output Schema](#output-schema)
6. [Additional Fact Collection](#additional-fact-collection)
   - [Pod Phase and Replica Counts](#pod-phase-and-replica-counts)
   - [Resource Requests and Limits](#resource-requests-and-limits)
   - [Inventory Container Images](#inventory-container-images)
   - [PVCs (see storage module)](#pvcs-see-storage-module)
7. [Handle Edge Cases](#handle-edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `list_k8s_resources`, `read_k8s_resource`
- **CLI fallback:** `kubectl`

---

## Understand the Detection Strategy

Use this section to understand the scope of workload inventory before running commands. Workload inventory covers:

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

## List Workloads by Type

Use these commands to enumerate workloads across namespaces. Start with Deployments (most common), then expand to StatefulSets, DaemonSets, and Jobs based on what you find.

### 1. List Deployments

Run this first to identify the main application workloads. Deployments are the most common workload type and reveal the core services running in the cluster.

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Deployment",
  api_version="apps/v1"
)
```

**CLI:**
```bash
# List all deployments with replica counts, ALL container images, init containers, and labels
kubectl get deploy -A -o json | jq -r '
  .items[] |
  select(.metadata.namespace | startswith("kube-") | not) |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    replicas: .spec.replicas,
    ready: .status.readyReplicas,
    images: [.spec.template.spec.containers[].image],
    init_containers: [.spec.template.spec.initContainers[]?.name],
    labels: .metadata.labels
  }'
```

Iterate **all** `containers[].image` (a workload may run multiple containers — sidecars,
proxies), not just `containers[0]`. Record `init_containers` (names) per workload; empty
list when none.

**Example output:**
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

### 2. List StatefulSets

Check StatefulSets when you need to understand stateful applications like databases, message queues, or caches. These require special handling during migrations due to persistent storage.

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="StatefulSet",
  api_version="apps/v1"
)
```

**CLI:**
```bash
# List StatefulSets with volumeClaimTemplate -> storageClass linkage
kubectl get statefulsets -A -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    replicas: .spec.replicas,
    volume_claims: [.spec.volumeClaimTemplates[]?.metadata.name],
    storage_class: (.spec.volumeClaimTemplates[]?.spec.storageClassName)
  }'
```

Capture the `volumeClaimTemplate` -> `storageClassName` linkage: each StatefulSet
volume claim template names a storage class the pods provision volumes from. Record the
storage class per StatefulSet (`null` when the template omits it and the cluster default applies).

**Example output:**
```json
{
  "namespace": "production",
  "name": "redis-cluster",
  "replicas": 3,
  "volume_claims": ["data"],
  "storage_class": "gp3"
}
```

### 3. List DaemonSets

List DaemonSets to identify node-level agents (monitoring, logging, security). These run on every node and reveal operational tooling in use.

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="DaemonSet",
  api_version="apps/v1"
)
```

**CLI:**
```bash
# List DaemonSets
kubectl get daemonsets -A -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    desired: .status.desiredNumberScheduled,
    ready: .status.numberReady
  }'
```

**Example output:**
```json
{
  "namespace": "kube-system",
  "name": "aws-node",
  "desired": 5,
  "ready": 5
}
```

### 4. List CronJobs and Jobs

Check batch workloads to understand scheduled tasks (backups, reports) and one-time jobs. Important for understanding maintenance windows and resource usage patterns.

**CLI:**
```bash
# List CronJobs
kubectl get cronjobs -A -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    schedule: .spec.schedule,
    suspend: .spec.suspend,
    lastSchedule: .status.lastScheduleTime
  }'

# List active Jobs
kubectl get jobs -A --field-selector status.successful!=1 -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    active: .status.active,
    failed: .status.failed
  }'
```

**Example output (CronJob):**
```json
{
  "namespace": "production",
  "name": "db-backup",
  "schedule": "0 2 * * *",
  "suspend": false,
  "lastSchedule": "2026-04-22T02:00:00Z"
}
```

### 5. List Services

List Services to understand network exposure. Services reveal how applications communicate internally (ClusterIP) and externally (LoadBalancer, NodePort).

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Service",
  api_version="v1"
)
```

**CLI:**
```bash
# List services with type, ports, and selector
kubectl get svc -A -o json | jq -r '
  .items[] |
  select(.metadata.namespace | startswith("kube-") | not) |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    type: .spec.type,
    ports: [.spec.ports[]? | "\(.port)/\(.protocol)"],
    selector: .spec.selector
  }'
```

Record each service as a full entry (`name`, `type`, `ports`, `selector`), not only an
aggregate count by type.

> **Note:** The `services.by_type` field (counts per `ClusterIP`/`NodePort`/`LoadBalancer`)
> is aggregated by the agent from the enumerated services list above — no separate counting
> command is needed.

**Example output:**
```json
{
  "namespace": "production",
  "name": "api-gateway",
  "type": "LoadBalancer",
  "ports": ["443/TCP", "80/TCP"],
  "selector": {"app": "api-gateway"}
}
```

### 6. List Ingresses

Check Ingresses to identify external access points and routing rules. Ingresses show domain mappings, TLS configuration, and which services are publicly accessible.

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Ingress",
  api_version="networking.k8s.io/v1"
)
```

**CLI:**
```bash
# List Ingresses with TLS presence
kubectl get ingress -A -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    class: .spec.ingressClassName,
    hosts: [.spec.rules[]?.host],
    tls_enabled: ((.spec.tls // []) | length > 0)
  }'
```

`tls_enabled` = `true` when the ingress declares one or more `spec.tls` entries, else `false`.

**Example output:**
```json
{
  "namespace": "production",
  "name": "api-ingress",
  "class": "alb",
  "hosts": ["api.example.com", "api-internal.example.com"],
  "tls_enabled": true
}
```

### 7. List HPAs

List Horizontal Pod Autoscalers to understand autoscaling configuration. HPAs reveal which workloads scale automatically and their scaling thresholds.

**CLI:**
```bash
# List HPAs with current metrics
kubectl get hpa -A -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    target: .spec.scaleTargetRef.name,
    minReplicas: .spec.minReplicas,
    maxReplicas: .spec.maxReplicas,
    currentReplicas: .status.currentReplicas,
    metrics: [.spec.metrics[]?.type]
  }'
```

**Example output:**
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

### 8. List Pod Disruption Budgets

Enumerate PodDisruptionBudgets (PDBs) across namespaces. A PDB records the minimum
availability guarantee for the pods matched by its selector. Record existence, the
`minAvailable` / `maxUnavailable` value, and the label selector (the workloads it covers).

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="PodDisruptionBudget",
  api_version="policy/v1"
)
```

**CLI:**
```bash
# List PDBs (VERIFIED: kubectl get pdb -A exposes MIN AVAILABLE / MAX UNAVAILABLE cols)
kubectl get pdb -A -o json | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    min_available: .spec.minAvailable,
    max_unavailable: .spec.maxUnavailable,
    selector: .spec.selector.matchLabels
  }'
```

Exactly one of `min_available` / `max_unavailable` is set per PDB; the other is `null`.
The `selector` matchLabels identify the covered workloads.

**Example output:**
```json
{
  "namespace": "production",
  "name": "api-gateway-pdb",
  "min_available": "1",
  "max_unavailable": null,
  "selector": {"app": "api-gateway"}
}
```

### 9. List PriorityClasses

List PriorityClasses (cluster-scoped) to record scheduling priority definitions.

**MCP:**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="PriorityClass",
  api_version="scheduling.k8s.io/v1"
)
```

**CLI:**
```bash
kubectl get priorityclasses -o json | jq -r '
  .items[] |
  {
    name: .metadata.name,
    value: .value,
    global_default: .globalDefault
  }'
```

**Example output:**
```json
{
  "name": "high-priority",
  "value": 1000000,
  "global_default": false
}
```

### 10. List Vertical Pod Autoscalers

List VerticalPodAutoscalers only if the CRD is present. VPA is an add-on CRD
(`verticalpodautoscalers.autoscaling.k8s.io`); guard the query so its absence is a clean
fact, not an error.

**CLI:**
```bash
# Detect the CRD first (absence is a fact)
kubectl get crd verticalpodautoscalers.autoscaling.k8s.io 2>/dev/null

# If present, list VPAs
kubectl get verticalpodautoscalers.autoscaling.k8s.io -A -o json 2>/dev/null | jq -r '
  .items[] |
  {
    namespace: .metadata.namespace,
    name: .metadata.name,
    target: .spec.targetRef.name,
    update_mode: .spec.updatePolicy.updateMode
  }'
```

Record `detected: false` for the whole block when the CRD is absent.

**Example output:**
```json
{
  "namespace": "production",
  "name": "api-gateway-vpa",
  "target": "api-gateway",
  "update_mode": "Auto"
}
```

### 11. Enumerate API Versions In Use

Enumerate the distinct `apiVersion` values that live resources in the cluster use, as a
**raw fact list**. This is inventory only.

> **Scope note:** Report the apiVersions verbatim. Do **not** flag any as deprecated,
> removed, or upgrade-blocking, and do not cross-reference them against a target Kubernetes
> version — that deprecation math belongs to the `eks-upgrade-check` skill, not recon.

**CLI:**
```bash
# apiVersions used by common workload/config resources across all namespaces
kubectl get deploy,statefulset,daemonset,replicaset,cronjob,job,ingress,hpa,pdb,networkpolicy \
  -A -o json | jq -r '[.items[].apiVersion] | unique | sort[]'
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

## Generate Summary Statistics

Run this command to get a high-level view of workload distribution across namespaces. Use this for initial assessment before diving into details.

```bash
# Quick summary of workload counts by namespace
kubectl get deploy,statefulsets,daemonsets,jobs -A -o json | jq -r '
  .items |
  group_by(.metadata.namespace) |
  map({
    namespace: .[0].metadata.namespace,
    total: length,
    by_kind: group_by(.kind) | map({key: .[0].kind, value: length}) | from_entries
  })'
```

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

Commands for facts that feed the schema blocks above beyond the primary per-type listings.

### Pod Phase and Replica Counts

Enumerate pod phase and replica-vs-desired counts.

```bash
# Pods not in Running/Succeeded phase (phase per pod)
kubectl get pods -A --field-selector 'status.phase!=Running,status.phase!=Succeeded' \
  -o json | jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name): \(.status.phase)"'

# Deployments where ready != desired replicas
kubectl get deploy -A -o json | jq -r '
  .items[] |
  select(.spec.replicas != .status.readyReplicas) |
  "\(.metadata.namespace)/\(.metadata.name): \(.status.readyReplicas)/\(.spec.replicas)"'
```

**Example output:**
```
production/api-gateway: 2/3
staging/worker: 0/2
```

### Resource Requests and Limits

Inventory pods that declare no resource requests (count).

```bash
# Count of pods without resource requests
kubectl get pods -A -o json | jq -r '
  .items[] |
  select(.spec.containers[].resources.requests == null) |
  "\(.metadata.namespace)/\(.metadata.name)"' | sort -u | wc -l
```

**Example output:**
```
23
```

### Inventory Container Images

Enumerate unique images and image counts by registry.

```bash
# Unique images across cluster
kubectl get pods -A -o json | jq -r '
  [.items[].spec.containers[].image] | unique | sort[]'

# Images by registry — normalize bare "nginx" -> docker.io/library
kubectl get pods -A -o json | jq -r '
  def registry(i):
    (i | split("/")) as $p |
    if ($p | length) == 1 then "docker.io/library"        # bare "nginx"
    elif ($p | length) == 2 and ($p[0] | test("[.:]") | not) then "docker.io"  # "library/nginx", "bitnami/redis"
    else $p[0] end;                                        # registry host present
  [.items[].spec.containers[].image] |
  group_by(registry(.)) |
  map({registry: (.[0] | registry(.)), count: length})'
```

A bare image reference like `nginx` resolves to the Docker Hub library namespace, so bucket
it under `docker.io/library` (not under the literal first path segment). A two-segment
reference whose first segment has no `.` or `:` (e.g. `bitnami/redis`) is also a Docker Hub
reference → `docker.io`.

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

## Handle Edge Cases

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

Check for Services without matching pods to find potential cleanup opportunities or misconfiguration.

```bash
# Services without matching deployments
kubectl get svc -A -o json | jq -r '
  .items[] |
  select(.spec.selector != null and .spec.type != "ExternalName") |
  {namespace: .metadata.namespace, name: .metadata.name, selector: .spec.selector}'
```
