# Module: Observability

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect observability stack — metrics, logging, tracing configuration

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. Metrics Collection](#1-metrics-collection)
  - [2. Logging Configuration](#2-logging-configuration)
  - [3. Tracing](#3-tracing)
  - [4. Application Signals (APM)](#4-application-signals-apm)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

> **Shared cluster block:** every module agent also emits the shared `cluster:` block defined
> under "## Shared Cluster Block" in [`cluster-basics.md`](cluster-basics.md). It is not redefined here.
>
> **Module ownership:** this module OWNS control-plane logging. `cluster-basics` defers to the
> `logging.control_plane` block below for which control-plane log types are enabled/disabled.

---

## Access Model

This module reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS / CloudWatch Logs) — control-plane logging is AWS-only:
  `eks:DescribeCluster` (`cluster.logging.clusterLogging`) determines which control-plane
  log types are enabled/disabled; the control-plane log group name is deterministic
  (`/aws/eks/<cluster-name>/cluster`) and can optionally be confirmed via the CloudWatch
  Logs API (`logs:DescribeLogGroups`). Container Insights and ADOT (`otel`) add-on versions
  come from `eks:DescribeAddon`. Requires the read-only permissions in
  `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — everything else: Prometheus,
  Grafana, Alertmanager, scrape/remote-write config, Fluent Bit / Fluentd, log
  destinations, OTel/Jaeger/Tempo/X-Ray collectors, and APM (Application Signals /
  auto-instrumentation). Requires `authenticationMode` to include `API` and the
  `AmazonAIOpsAssistantPolicy` access entry to be present. RBAC verbs needed: `get`, `list`.

If the Kubernetes API is unreachable (access entry absent), report the AWS-API facts
(`logging.control_plane`, `container_insights.addon_version`, `tracing.otel.version` from
the ADOT add-on) and mark every K8s-dependent sub-fact (`prometheus`, `grafana`,
`alertmanager`, `scrape_configs`, `logging.application`, `log_destinations`, in-cluster
`tracing.*`, `apm.*`) as `unconfirmed` in the report's Coverage section — never as
`false`/`count: 0`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes client)*
> below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They are
> **not executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its Kubernetes-API
> capability.

---

## Detection Strategy

Observability has three pillars (plus control plane logging):

```
1. Metrics          -> Container Insights, Prometheus, Datadog, etc.
2. Logging          -> CloudWatch, FluentBit, OpenSearch, etc.
3. Tracing          -> X-Ray, OTel, Jaeger, etc.
4. Control Plane    -> API server, audit, authenticator logs (AWS API)
```

**Why detect each pillar:**

| Pillar | Why It Matters |
|--------|----------------|
| Metrics | Understand resource utilization, HPA scaling decisions, capacity planning |
| Logging | Debug application issues, audit security events, compliance requirements |
| Tracing | Diagnose latency in distributed systems, identify service dependencies |
| Control Plane | Investigate API failures, audit access, debug networking issues |

---

## Detection Capabilities

### 1. Metrics Collection

Detect how the cluster tracks resource usage and supports autoscaling. Most clusters have
at least one metrics solution.

**Container Insights (CloudWatch):**

AWS-native monitoring delivered as the `amazon-cloudwatch-observability` add-on.

**Via AWS API** — describe the Container Insights add-on:

```bash
aws eks describe-addon --cluster-name <cluster-name> \
  --addon-name amazon-cloudwatch-observability \
  --query 'addon.{status:status,addonVersion:addonVersion}'
```

**Example output (add-on installed):**
```json
{
  "status": "ACTIVE",
  "addonVersion": "v1.5.0-eksbuild.1"
}
```

A `ResourceNotFoundException` means the add-on is not installed → `container_insights.enabled: false`.

**Container Insights addon_version:** take the exact `addonVersion` from this describe-addon
call (`.addon.addonVersion`, e.g. `v1.5.0-eksbuild.1`).

The CloudWatch agent and Fluent Bit DaemonSets that the add-on ships surface via the
Kubernetes API (see Logging below); the add-on version above is the authoritative
Container Insights fact.

**Prometheus (self-managed / operator / AMP):**

Classify how Prometheus runs and record its version.
- `self-managed` — a `prometheus-server` Deployment/StatefulSet (e.g. Helm `prometheus`).
- `operator` — the Prometheus Operator is present (label `app.kubernetes.io/name=prometheus-operator`), managing `Prometheus` CRs.
- `amp` — Amazon Managed Prometheus; an `aps-workspaces` remote_write target with no in-cluster server (record `version: null`).

**Via Kubernetes API** — detect Prometheus and its version:

- **Resource:** `Deployment` and `StatefulSet`, group/version `apps/v1`, label selector `app.kubernetes.io/name=prometheus`, all namespaces. Also check `Deployment` with label `app.kubernetes.io/name=prometheus-operator` to set `type: operator`.
- **Fields to extract:** container image whose name matches `prometheus` → parse the image tag for the version; `metadata.namespace`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `statefulsets.apps`.

**Amazon Managed Prometheus (AMP):** AMP has no in-cluster server; it appears as an
`aps-workspaces` URL in a remote_write target. Detect it from the Prometheus config
(see scrape/remote_write below) → `type: amp`, `version: null`.

**Grafana:**

Classify how Grafana runs and record its version.
- `self-managed` — a `grafana` Deployment in-cluster; version comes from the deployment image tag.
- `amg` — Amazon Managed Grafana; the workspace is external to the cluster, so there is no in-cluster version (record `version: null`).

**Via Kubernetes API** — detect Grafana and its version:

- **Resource:** `Deployment`, group/version `apps/v1`, label selector `app.kubernetes.io/name=grafana`, all namespaces.
- **Fields to extract:** container image whose name matches `grafana` → parse the image tag for the version; `metadata.namespace`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

**Alertmanager:** detect presence as a component (not a feature).

**Via Kubernetes API** — detect Alertmanager:

- **Resource:** `Deployment` / `StatefulSet`, group/version `apps/v1`, label selector `app.kubernetes.io/name=alertmanager`, all namespaces; and the `Alertmanager` CR, group/version `monitoring.coreos.com/v1` (shipped by kube-prometheus-stack).
- **Fields to extract:** `metadata.name`, `metadata.namespace` (presence = detected).
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `statefulsets.apps`, `alertmanagers.monitoring.coreos.com`.

**Prometheus scrape_configs / remote_write targets (raw fact):** capture the configured
scrape job names and remote_write URLs verbatim — do not interpret them.

**Via Kubernetes API** — read the Prometheus config:

- **Resource:** `ConfigMap` and `Secret`, group/version `v1` (core), all namespaces, whose name matches `prometheus`.
- **Fields to extract:** from the rendered config body — `scrape_configs[].job_name` (scrape job names) and `remote_write[].url` (remote_write URLs, e.g. `aps-workspaces` AMP endpoints).
- **RBAC verbs:** `get`, `list` on `configmaps`, `secrets`.

Record `scrape_configs` (count + list of job names) and `remote_write_targets` (list of URLs)
exactly as found; report `null`/empty where the config is not readable.

**Other Metrics Tools:**

Commercial APM agents (Datadog, New Relic) provide unified observability platforms.

**Via Kubernetes API** — detect commercial agents:

- **Resource:** `DaemonSet`, group/version `apps/v1`, all namespaces — Datadog (label `app.kubernetes.io/name` / name `datadog-agent`), New Relic (label `app.kubernetes.io/name=nri-bundle`).
- **Fields to extract:** presence per tool → append to `other_tools.list`.
- **RBAC verbs:** `get`, `list` on `daemonsets.apps`.

> **metrics-server defer:** metrics-server is reported by the addons module
> (`addons.platform_components.metrics_server`) — see addons. This module does not detect or
> emit it.

*Reference pseudocode (kubernetes client), not executable:*
```python
apps = client.AppsV1Api()

# Prometheus (self-managed / operator) — version from image tag
prom = apps.list_deployment_for_all_namespaces(
    label_selector="app.kubernetes.io/name=prometheus")
prom_image = next((c.image for d in prom.items
                   for c in d.spec.template.spec.containers
                   if "prometheus" in c.name), None)

# Grafana — version from image tag
graf = apps.list_deployment_for_all_namespaces(
    label_selector="app.kubernetes.io/name=grafana")
graf_image = next((c.image for d in graf.items
                   for c in d.spec.template.spec.containers
                   if "grafana" in c.name), None)
```

### 2. Logging Configuration

Detect how application and cluster logs are collected and where they are sent.

**Control Plane Logging (this module owns it — AWS API):**

This module is the single owner of the control-plane logging fact; `cluster-basics` defers here.

**Via AWS API** — read the cluster logging config:

```bash
aws eks describe-cluster --name <cluster-name> \
  --query 'cluster.logging.clusterLogging[*].{types:types,enabled:enabled}'
```

**The `clusterLogging` array groups log types by state**, not by individual type. EKS returns
one entry per state — an `enabled: true` group listing the enabled types and/or an `enabled: false`
group listing the disabled types. A partially-enabled cluster therefore returns BOTH groups.
De-nest this into flat `enabled_types` and `disabled_types` lists for the schema. Any of the five
types (`api`, `audit`, `authenticator`, `controllerManager`, `scheduler`) not present in the
enabled group is disabled. Report which types are enabled as a neutral fact.

**Example output (partially enabled — api + audit on, rest off):**
```json
[
  {
    "types": ["api", "audit"],
    "enabled": true
  },
  {
    "types": ["authenticator", "controllerManager", "scheduler"],
    "enabled": false
  }
]
```
→ `enabled_types: [api, audit]`, `disabled_types: [authenticator, controllerManager, scheduler]`

**Example output (none enabled):**
```json
[
  {
    "types": ["api", "audit", "authenticator", "controllerManager", "scheduler"],
    "enabled": false
  }
]
```
→ `enabled_types: []`, `disabled_types: [api, audit, authenticator, controllerManager, scheduler]`

**Control-plane log group (deterministic):** the `clusterLogging` query returns only types/enabled,
not the log group. The EKS control-plane CloudWatch log group name is deterministic:
`/aws/eks/<cluster-name>/cluster`. Populate `log_group` from the cluster name. When any control-plane
log type is enabled the group exists and can optionally be confirmed via the CloudWatch Logs API:
```bash
aws logs describe-log-groups \
  --log-group-name-prefix /aws/eks/<cluster-name>/cluster \
  --query 'logGroups[].logGroupName'
```

**Fluent Bit / Fluentd (application log forwarders):**

Fluent Bit (lightweight) and Fluentd (feature-rich) are the most common log forwarders.
Their config identifies where logs are being sent.

**Via Kubernetes API** — detect the forwarder and its destination:

- **Resource:** `DaemonSet`, group/version `apps/v1`, all namespaces — Fluent Bit (label `app.kubernetes.io/name=fluent-bit`), Fluentd (label `app=fluentd`).
- **Resource:** `ConfigMap`, group/version `v1` (core), the forwarder's config (e.g. `fluent-bit-config` in `amazon-cloudwatch`).
- **Fields to extract:** presence → `application.tool`; the config body's output plugins/hosts (matching `cloudwatch`, `opensearch`, `elasticsearch`, `s3`, `kinesis`, `loki`) → `application.destination` and `log_destinations` booleans; `metadata.namespace`.
- **RBAC verbs:** `get`, `list` on `daemonsets.apps`, `configmaps`.

**OpenSearch / Elasticsearch, Loki (destinations):**

**Via Kubernetes API** — detect additional log backends:

- **Resource:** `ConfigMap` (core `v1`) whose data references `opensearch`/`elasticsearch`; `Deployment`/`StatefulSet` (`apps/v1`) with label `app.kubernetes.io/name=loki`.
- **Fields to extract:** presence → set the corresponding `log_destinations` boolean.
- **RBAC verbs:** `get`, `list` on `configmaps`, `deployments.apps`, `statefulsets.apps`.

### 3. Tracing

Tracing debugs latency in microservices architectures.

**AWS X-Ray / OpenTelemetry (otel):**

The OpenTelemetry collector (shipped by AWS as ADOT — AWS Distro for OpenTelemetry, add-on
name `adot`) can send traces to X-Ray, Jaeger, or other backends. Record it under the
`otel` key and capture its version. Both the ADOT add-on and a self-managed OTel collector
surface under `otel`.

**Via AWS API** — describe the ADOT add-on (add-on name is `adot`; version → `otel.version`):

```bash
aws eks describe-addon --cluster-name <cluster-name> --addon-name adot \
  --query 'addon.{status:status,addonVersion:addonVersion}'
```

**Example output (ADOT/otel add-on installed):**
```json
{
  "status": "ACTIVE",
  "addonVersion": "v0.88.0-eksbuild.1"
}
```

**Via Kubernetes API** — detect self-managed OTel collectors and the X-Ray daemon:

- **Resource:** `Deployment`, group/version `apps/v1`, all namespaces — ADOT collector (label `app.kubernetes.io/name=aws-otel-collector`), self-managed OTel (label `app=opentelemetry-collector`).
- **Resource:** `DaemonSet`, group/version `apps/v1`, label selector `app=xray-daemon` → `xray.detected`.
- **Fields to extract:** presence per tool; container image tag → `otel.version` when the add-on is not the source.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `daemonsets.apps`.

**Jaeger:**

**Via Kubernetes API** — detect Jaeger:

- **Resource:** `Deployment`, group/version `apps/v1`, all namespaces, label selector `app.kubernetes.io/name=jaeger` (or `app=jaeger`).
- **Fields to extract:** presence → `jaeger.detected`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

**Tempo:**

Grafana Tempo is often paired with Grafana and Loki.

**Via Kubernetes API** — detect Tempo:

- **Resource:** `Deployment` / `StatefulSet`, group/version `apps/v1`, all namespaces, label selector `app.kubernetes.io/name=tempo`.
- **Fields to extract:** presence → `tempo.detected`.
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `statefulsets.apps`.

### 4. Application Signals (APM)

Application Signals provides automatic instrumentation for common frameworks without
modifying application code.

**Via Kubernetes API** — detect Application Signals and auto-instrumentation:

- **Resource:** `Deployment`, group/version `apps/v1`, namespace `amazon-cloudwatch`, name `cloudwatch-agent-operator` → `application_signals.enabled`.
- **Resource:** `Instrumentation` CR, group/version `opentelemetry.io/v1alpha1`, all namespaces → `auto_instrumentation.enabled` (true when any CR exists) and `auto_instrumentation.namespaces` (namespaces containing them).
- **RBAC verbs:** `get`, `list` on `deployments.apps`, `instrumentations.opentelemetry.io`.

- `application_signals.enabled` — a toggled feature; `true` when the CloudWatch agent operator
  / Application Signals is active.
- `auto_instrumentation.enabled` + `auto_instrumentation.namespaces` — `true` when any
  `Instrumentation` CR exists; record the list of namespaces containing them.

---

## Output Schema

This is the **single canonical schema** for the observability module — it carries every
observability fact. The `observability-recon` agent emits exactly this shape (plus the shared
`cluster:` block from `references/cluster-basics.md`). Use `null` where a fact was not detected;
never omit a key. This module OWNS the control-plane logging fact (`logging.control_plane`);
`cluster-basics` defers here.

```yaml
observability:
  metrics:
    container_insights:
      enabled: bool               # feature toggle: amazon-cloudwatch-observability addon active
      addon_version: string       # describe-addon .addon.addonVersion, null if not installed

    prometheus:
      detected: bool
      type: string                # self-managed | amp | operator
      version: string             # from prometheus image tag, null for amp
      namespace: string

    grafana:
      detected: bool
      type: string                # self-managed | amg
      version: string             # from grafana image tag, null for amg (workspace external)
      namespace: string

    # metrics-server is reported by the addons module (platform_components.metrics_server) — see addons

    alertmanager:
      detected: bool              # component presence (deploy/statefulset or Alertmanager CR)
      namespace: string

    scrape_configs:               # raw fact — scrape jobs found in the prometheus config
      count: int
      list: list                  # scrape job names, verbatim
    remote_write_targets: list    # remote_write URLs verbatim (e.g. aps-workspaces AMP URLs)

    other_tools:                  # commercial APM agents detected in-cluster
      count: int
      list: list                  # e.g. ["datadog", "newrelic"]

  logging:
    control_plane:                # OWNED by this module — de-nested from clusterLogging groups
      enabled_types: list         # subset of [api, audit, authenticator, controllerManager, scheduler]
      disabled_types: list        # the remaining types not in enabled_types
      log_group: string           # deterministic: /aws/eks/<cluster-name>/cluster

    application:
      tool: string                # fluent-bit | fluentd | promtail | none
      destination: string         # cloudwatch | opensearch | loki | s3 | null
      namespace: string

    log_destinations:
      cloudwatch: bool
      opensearch: bool
      s3: bool
      loki: bool

  tracing:
    tool: string                  # xray | otel | jaeger | tempo | none
    otel:                         # OpenTelemetry / ADOT collector (addon name is 'adot')
      detected: bool
      version: string
    xray:
      detected: bool
    jaeger:
      detected: bool
    tempo:
      detected: bool

  apm:
    application_signals:
      enabled: bool               # feature toggle
    auto_instrumentation:
      enabled: bool               # feature toggle: any Instrumentation CR present
      namespaces: list            # namespaces containing Instrumentation CRs
```

---

## Edge Cases

### Multiple Metrics Solutions

Common to have:
- Metrics Server (for HPA — reported by the addons module)
- Prometheus (for detailed metrics)
- Container Insights (for AWS integration)

Note all as facts; draw no conclusion about maturity or gaps.

### Log Aggregation Outside Cluster

Logs may go to:
- External CloudWatch in a different account
- Third-party SaaS (Datadog, Splunk)
- Self-managed OpenSearch/ELK

The Fluent Bit/Fluentd config (capability 2) carries the destination. Record it as a fact.

### Control Plane Logging Not Enabled

If the `clusterLogging` groups show no enabled types, record `enabled_types: []` and
`disabled_types: [api, audit, authenticator, controllerManager, scheduler]`. Report this as
a neutral fact — no compliance-gap judgment.

### ADOT vs Self-Managed OTel Collectors

The ADOT add-on (AWS API, add-on name `adot`) and a self-managed OTel collector
(Kubernetes API, label `app=opentelemetry-collector`) both surface under the `otel` key.
Record whichever is present; when both, record the add-on version as `otel.version`.
