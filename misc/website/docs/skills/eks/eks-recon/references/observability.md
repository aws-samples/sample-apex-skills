---
title: "Module: Observability"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/observability.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/observability.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/observability.md). Edit the source, not this page.
:::

# Module: Observability

> **Part of:** [eks-recon](../)
> **Purpose:** Detect observability stack - metrics, logging, tracing configuration

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [1. Metrics Collection](#1-metrics-collection)
  - [2. Logging Configuration](#2-logging-configuration)
  - [3. Tracing](#3-tracing)
  - [4. Application Signals (APM)](#4-application-signals-apm)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

> **Shared cluster block:** every module agent also emits the shared `cluster:` block defined
> under "## Shared Cluster Block" in [`cluster-basics.md`](cluster-basics). It is not redefined here.
>
> **Module ownership:** this module OWNS control-plane logging. `cluster-basics` defers to the
> `logging.control_plane` block below for which control-plane log types are enabled/disabled.

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `describe_eks_resource`, `list_k8s_resources`
- **CLI fallback:** `aws eks`, `kubectl`, `aws logs`

---

## Detection Strategy

Observability has three pillars (plus control plane logging):

```
1. Metrics          -> Container Insights, Prometheus, Datadog, etc.
2. Logging          -> CloudWatch, FluentBit, OpenSearch, etc.
3. Tracing          -> X-Ray, ADOT, Jaeger, etc.
4. Control Plane    -> API server, audit, authenticator logs
```

**Why detect each pillar:**

| Pillar | Why It Matters |
|--------|----------------|
| Metrics | Understand resource utilization, HPA scaling decisions, capacity planning |
| Logging | Debug application issues, audit security events, compliance requirements |
| Tracing | Diagnose latency in distributed systems, identify service dependencies |
| Control Plane | Investigate API failures, audit access, debug networking issues |

---

## Detection Commands

### 1. Metrics Collection

Start with metrics detection to understand how the cluster tracks resource usage and supports autoscaling. Most clusters have at least one metrics solution.

**Container Insights (CloudWatch):**

Use Container Insights when you need AWS-native monitoring with automatic CloudWatch integration. This is the simplest option for teams already using AWS observability tools.

**MCP:**
```
describe_eks_resource(
  resource_type="addon",
  cluster_name="<cluster-name>",
  resource_name="amazon-cloudwatch-observability"
)
```

**CLI:**
```bash
# Check for CloudWatch add-on
aws eks describe-addon --cluster-name <cluster-name> \
  --addon-name amazon-cloudwatch-observability 2>/dev/null

# Alternative: Check for CloudWatch agent DaemonSet
kubectl get daemonset -n amazon-cloudwatch cloudwatch-agent 2>/dev/null

# Check for Fluent Bit (CloudWatch integration)
kubectl get daemonset -n amazon-cloudwatch fluent-bit 2>/dev/null
```

**Example output (add-on installed):**
```json
{
  "addon": {
    "addonName": "amazon-cloudwatch-observability",
    "clusterName": "prod-cluster",
    "status": "ACTIVE",
    "addonVersion": "v1.5.0-eksbuild.1"
  }
}
```

**Example output (not installed):**
```
An error occurred (ResourceNotFoundException) when calling the DescribeAddon operation
```

**Prometheus (Self-Managed):**

Use Prometheus when you need flexible metrics collection with PromQL queries, custom recording rules, or Grafana dashboards. Common in teams with existing Prometheus expertise.

```bash
# Check for Prometheus deployment
kubectl get deploy -n prometheus prometheus-server 2>/dev/null || \
kubectl get deploy -n monitoring prometheus-server 2>/dev/null || \
kubectl get statefulset -n prometheus prometheus-server 2>/dev/null

# Check for kube-prometheus-stack (Helm)
helm list -A --filter "prometheus\|kube-prometheus" 2>/dev/null

# Check for Prometheus Operator
kubectl get deploy -A -l "app.kubernetes.io/name=prometheus-operator" 2>/dev/null
```

**Example output (Prometheus detected):**
```
NAME                READY   UP-TO-DATE   AVAILABLE   AGE
prometheus-server   1/1     1            1           45d
```

**Amazon Managed Prometheus (AMP):**

Check for AMP when you need managed Prometheus with automatic scaling and AWS integration. Look for `aps-workspaces` URLs in remote write configurations.

```bash
# Check for ADOT or Prometheus remote write config
kubectl get configmap -A -o json | jq -r '
  .items[] |
  select(.data | to_entries | .[] | .value | contains("aps-workspaces")) |
  {namespace: .metadata.namespace, name: .metadata.name}'
```

**Example output (AMP configured):**
```json
{
  "namespace": "prometheus",
  "name": "prometheus-config"
}
```

**Grafana:**
```bash
# Check for Grafana deployment
kubectl get deploy -A -l "app.kubernetes.io/name=grafana" 2>/dev/null

# Check for Amazon Managed Grafana (external, check workspace)
# Note: AMG workspaces are external to cluster
```

**Grafana type + version:** classify how Grafana runs and record its version.
- `self-managed` — a `grafana` Deployment in-cluster; version comes from the deployment image tag.
- `amg` — Amazon Managed Grafana; workspace is external to the cluster, so there is no in-cluster
  version (record `version: null`).
```bash
# Version from the grafana image tag (self-managed)
kubectl get deploy -A -l "app.kubernetes.io/name=grafana" -o json 2>/dev/null | \
  jq -r '.items[].spec.template.spec.containers[] | select(.name|test("grafana")) | .image'
```

**Other Metrics Tools:**

Third-party tools like Datadog and New Relic provide unified observability platforms. Check for these when the team uses a commercial APM solution.

```bash
# Datadog
kubectl get daemonset -n datadog datadog-agent 2>/dev/null

# New Relic
kubectl get daemonset -A -l "app.kubernetes.io/name=nri-bundle" 2>/dev/null
```

> **metrics-server defer:** metrics-server is reported by the addons module
> (`addons.platform_components.metrics_server`) — see addons. This module does not detect or
> emit it.

**Prometheus type + version:** classify how Prometheus runs and record its version.
- `self-managed` — a `prometheus-server` Deployment/StatefulSet (e.g. Helm `prometheus`).
- `operator` — the Prometheus Operator is present (label `app.kubernetes.io/name=prometheus-operator`), managing `Prometheus` CRs.
- `amp` — Amazon Managed Prometheus; an `aps-workspaces` remote_write target with no in-cluster server.
```bash
# Version from the prometheus image tag (self-managed / operator)
kubectl get deploy,statefulset -A -l "app.kubernetes.io/name=prometheus" -o json 2>/dev/null | \
  jq -r '.items[].spec.template.spec.containers[] | select(.name|test("prometheus")) | .image'
```

**Container Insights addon_version:** take the exact `addonVersion` from the describe-addon
call in the Container Insights step above (`.addon.addonVersion`, e.g. `v1.5.0-eksbuild.1`).

**Alertmanager:** detect presence as a component (not a feature).
```bash
kubectl get deploy,statefulset -A -l "app.kubernetes.io/name=alertmanager" -o json 2>/dev/null | \
  jq -r '.items[].metadata.name'
# kube-prometheus-stack also ships the Alertmanager CR
kubectl get alertmanagers.monitoring.coreos.com -A 2>/dev/null
```

**Prometheus scrape_configs / remote_write targets (raw fact):** capture the configured
scrape job names and remote_write URLs verbatim — do not interpret them.
```bash
# Self-managed / operator: the prometheus config secret or configmap
kubectl get secret -A -o json 2>/dev/null | jq -r '
  .items[] | select(.metadata.name|test("prometheus")) | .metadata.namespace + "/" + .metadata.name'
# Extract remote_write targets (e.g. aps-workspaces AMP URLs) and scrape job names from the rendered config
kubectl get cm -A -o json 2>/dev/null | jq -r '
  .items[] | .data // {} | to_entries[] | .value
  | capture("remote_write:[\\s\\S]*?url:\\s*(?<url>\\S+)") // empty | .url' 2>/dev/null
```
Record `scrape_configs` (count + list of job names) and `remote_write_targets` (list of URLs)
exactly as found; report `null`/empty where the config is not readable.

### 2. Logging Configuration

Detect logging configuration to understand how application and cluster logs are collected and where they are sent.

**Control Plane Logging (this module owns it):**

Check control plane logging first. This module is the single owner of the control-plane
logging fact; `cluster-basics` defers here.

```bash
# Check which control plane logs are enabled
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
log type is enabled the group exists and can optionally be confirmed:
```bash
aws logs describe-log-groups \
  --log-group-name-prefix /aws/eks/<cluster-name>/cluster \
  --query 'logGroups[].logGroupName'
```

**Fluent Bit / Fluentd:**

Fluent Bit (lightweight) and Fluentd (feature-rich) are the most common log forwarders. Check their ConfigMaps to determine where logs are being sent.

```bash
# Fluent Bit DaemonSet
kubectl get daemonset -A -l "app.kubernetes.io/name=fluent-bit" 2>/dev/null

# Fluentd DaemonSet
kubectl get daemonset -A -l "app=fluentd" 2>/dev/null

# Check Fluent Bit ConfigMap for destinations
kubectl get configmap -n amazon-cloudwatch fluent-bit-config -o yaml 2>/dev/null | \
  grep -E "cloudwatch|opensearch|s3|kinesis" || true
```

**Example output (Fluent Bit detected):**
```
NAMESPACE          NAME         DESIRED   CURRENT   READY   AGE
amazon-cloudwatch  fluent-bit   3         3         3       60d
```

**OpenSearch / Elasticsearch:**
```bash
# Check for OpenSearch endpoint in configs
kubectl get configmap -A -o json | jq -r '
  .items[] |
  select(.data | to_entries | .[] | .value | contains("opensearch") or contains("elasticsearch")) |
  {namespace: .metadata.namespace, name: .metadata.name}'
```

**Loki:**
```bash
# Check for Loki deployment
kubectl get deploy -A -l "app.kubernetes.io/name=loki" 2>/dev/null
kubectl get statefulset -A -l "app.kubernetes.io/name=loki" 2>/dev/null
```

### 3. Tracing

Tracing is essential for debugging latency in microservices architectures. Without tracing, diagnosing cross-service issues requires correlating logs manually.

**AWS X-Ray / OpenTelemetry (otel):**

The OpenTelemetry collector (shipped by AWS as ADOT — AWS Distro for OpenTelemetry, addon name
`adot`) can send traces to X-Ray, Jaeger, or other backends. Record it under the `otel` key and
capture its version.

```bash
# Check for OTel / ADOT collector
kubectl get deploy -A -l "app.kubernetes.io/name=aws-otel-collector" 2>/dev/null
kubectl get deploy -A -l "app=opentelemetry-collector" 2>/dev/null

# Check for X-Ray daemon
kubectl get daemonset -A -l "app=xray-daemon" 2>/dev/null

# Check ADOT add-on (addon name is 'adot'; version → otel.version)
aws eks describe-addon --cluster-name <cluster-name> --addon-name adot 2>/dev/null
```

**Example output (ADOT/otel add-on installed):**
```json
{
  "addon": {
    "addonName": "adot",
    "clusterName": "prod-cluster",
    "status": "ACTIVE",
    "addonVersion": "v0.88.0-eksbuild.1"
  }
}
```

**Jaeger:**

Jaeger is a popular open-source tracing backend. Check for it when the team uses a self-managed tracing solution.

```bash
# Check for Jaeger
kubectl get deploy -A -l "app.kubernetes.io/name=jaeger" 2>/dev/null
kubectl get deploy -A -l "app=jaeger" 2>/dev/null
```

**Tempo:**

Grafana Tempo is often used with Grafana and Loki for a unified observability stack.

```bash
# Check for Grafana Tempo
kubectl get deploy -A -l "app.kubernetes.io/name=tempo" 2>/dev/null
kubectl get statefulset -A -l "app.kubernetes.io/name=tempo" 2>/dev/null
```

### 4. Application Signals (APM)

Application Signals provides automatic instrumentation for common frameworks. Check for this when the team wants APM without modifying application code.

```bash
# Check for CloudWatch Application Signals
kubectl get deploy -n amazon-cloudwatch cloudwatch-agent-operator 2>/dev/null

# Check for auto-instrumentation (record which namespaces have Instrumentation CRs)
kubectl get instrumentations.opentelemetry.io -A 2>/dev/null
```

- `application_signals.enabled` — a toggled feature; `true` when the CloudWatch agent operator
  / Application Signals is active.
- `auto_instrumentation.enabled` + `auto_instrumentation.namespaces` — `true` when any
  `Instrumentation` CR exists; record the list of namespaces containing them.

**Example output (auto-instrumentation configured):**
```
NAMESPACE   NAME       AGE   ENDPOINT
default     java-app   30d   http://adot-collector:4317
```

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
- Metrics Server (for HPA)
- Prometheus (for detailed metrics)
- Container Insights (for AWS integration)

Note all and their purposes.

### Log Aggregation Outside Cluster

Logs may go to:
- External CloudWatch in different account
- Third-party SaaS (Datadog, Splunk)
- Self-managed OpenSearch/ELK

Check Fluent Bit/Fluentd configs for destinations.

### Control Plane Logging Not Enabled

```bash
# Check which log types are enabled
aws eks describe-cluster --name <cluster-name> \
  --query 'cluster.logging.clusterLogging[?enabled==`true`].types'
```

If empty, record `enabled_types: []` and `disabled_types: [api, audit, authenticator,
controllerManager, scheduler]`. Report this as a neutral fact.

### ADOT vs Self-Managed OTel Collectors

```bash
# Check if using ADOT add-on or self-managed
aws eks describe-addon --cluster-name <cluster-name> --addon-name adot 2>/dev/null
# vs
kubectl get deploy -A -l "app=opentelemetry-collector" 2>/dev/null
```

Both surface under the `otel` key; the addon name is `adot`.
