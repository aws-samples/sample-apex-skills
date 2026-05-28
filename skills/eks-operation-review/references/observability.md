# Observability

## Purpose
Assess observability across three layers: control plane, data plane (nodes), and workloads — covering metrics, logs, and alerting.

## Checks to Execute

### 4.1 — EKS Control Plane Logging

**What to check:**
- Which of the 5 log types are enabled (api, audit, authenticator, controllerManager, scheduler)
- CloudWatch log group existence and retention policy

**How to check:**
1. Describe cluster → `logging.clusterLogging` → check each entry for `enabled: true` and which `types`
2. Use CloudWatch tools to check log group `/aws/eks/{cluster-name}/cluster` retention (recommend >= 30 days for audit logs; no retention policy = logs kept forever at cost)

**Rating:**
- 🟢 GREEN: All 5 log types enabled with defined retention policy
- 🟡 AMBER: Some log types enabled (especially if audit is on), or no retention policy
- 🔴 RED: Control plane logging completely disabled, or audit logs specifically disabled
- ⬜ UNKNOWN: Should not happen with live access

**Key talking point:** EKS control plane logging is OFF by default. The audit log is your security camera for every API call.

---

### 4.2 — Metrics Collection & Dashboards

**What to check:**
- CloudWatch Container Insights add-on (`amazon-cloudwatch-observability`)
- Prometheus pods (labels: `app.kubernetes.io/name=prometheus` or `app=prometheus`)
- Grafana pods
- kube-state-metrics deployment (critical for cluster state visibility)
- node-exporter DaemonSet
- ADOT add-on
- Third-party monitoring DaemonSets (Datadog, New Relic, Dynatrace)

**How to check:**
1. Describe addon `amazon-cloudwatch-observability`
2. List pods with label `app.kubernetes.io/name=prometheus` across all namespaces
3. List pods with label `app.kubernetes.io/name=grafana`
4. List pods with label `app.kubernetes.io/name=kube-state-metrics`
5. List DaemonSets across all namespaces (catches node-exporter and third-party agents)

**Rating:**
- 🟢 GREEN: Metrics collection + kube-state-metrics + dashboards (Container Insights or Prometheus+Grafana or third-party)
- 🟡 AMBER: Partial stack (e.g., Container Insights but no kube-state-metrics, or Prometheus without Grafana)
- 🔴 RED: No metrics collection at all
- ⬜ UNKNOWN: Cannot determine if dashboards are actively used

---

### 4.3 — Centralized Log Aggregation for Workloads

**What to check:**
- Fluent Bit DaemonSet (labels: `app.kubernetes.io/name=fluent-bit` or `k8s-app=fluent-bit`)
- Fluentd DaemonSet
- CloudWatch agent DaemonSet in `amazon-cloudwatch` namespace
- Application log groups in CloudWatch

**How to check:**
1. List DaemonSets with Fluent Bit labels across all namespaces
2. List DaemonSets in `amazon-cloudwatch` namespace
3. Use CloudWatch tools to check for log groups with prefix `/aws/eks/{cluster-name}`

**Rating:**
- 🟢 GREEN: Log shipper deployed, logs centralized with retention policy, structured logging
- 🟡 AMBER: Log shipper exists but no retention policy, or unstructured logging
- 🔴 RED: No centralized log collection — teams rely on kubectl logs
- ⬜ UNKNOWN: Cannot determine log format (structured vs unstructured) without sampling

---

### 4.4 — Alerting Defined and Actionable

**What to check:**
- CloudWatch Alarms related to EKS/ContainerInsights
- Prometheus Alertmanager pods
- PrometheusRule resources (alert definitions)

**How to check:**
1. List pods with label `app.kubernetes.io/name=alertmanager`
2. List PrometheusRule resources. If 404/NotFound (CRD not installed) → Prometheus Operator not deployed, rate alerting based on CloudWatch only. If 403/Forbidden → mark UNKNOWN.
3. Use CloudWatch tools to list alarms with ContainerInsights namespace

**Rating:**
- 🟢 GREEN: Alerts cover critical scenarios (node, pod, capacity), routed to on-call
- 🟡 AMBER: Some alerts exist but incomplete coverage, or no runbooks linked
- 🔴 RED: No alerting configured
- ⬜ UNKNOWN: Cannot determine if alerts have runbooks or if on-call monitors them — suggest user investigate

**Minimum viable alert set:** NodeNotReady, PodCrashLooping, PodPendingTooLong, HighAPIServerLatency, IPExhaustion.
