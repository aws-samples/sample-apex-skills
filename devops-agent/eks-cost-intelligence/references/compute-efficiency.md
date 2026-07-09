# Compute Efficiency

> **Part of:** [eks-cost-intelligence](../SKILL.md)
> **Purpose:** Checks for CPU/memory request-to-utilization ratios, over-provisioned workload detection, low-utilization node detection, Karpenter consolidation effectiveness, and missing resource requests/limits

---

## Overview

Compute efficiency is the highest-weighted dimension (25 points max deduction). It evaluates whether the cluster's CPU and memory capacity is being used effectively or wasted through over-provisioning, idle nodes, or missing resource governance.

### Checks Summary

| # | Check | Default Threshold | Severity Logic |
|---|-------|-------------------|----------------|
| 1 | CPU/memory request-to-utilization ratios | requests > 2× P95 usage | By waste $ |
| 2 | Over-provisioned workload detection | configurable (default: 2×) | By waste $ |
| 3 | Low-utilization node detection | <10% CPU, <20% memory over 7d | By idle node cost |
| 4 | Karpenter consolidation effectiveness | consolidation disabled or ineffective | MEDIUM–HIGH |
| 5 | Workloads without resource requests/limits | any pod missing requests | MEDIUM |
| 6 | Graceful degradation (metrics unavailable) | N/A | Mark SKIPPED |

---

## Pre-requisites

These checks require at least one of:
- **metrics-server** installed and responding (`kubectl top` works)
- **Container Insights** enabled (CloudWatch metrics available)
- **Prometheus** with kube-state-metrics and node-exporter

If none are available, the entire compute efficiency dimension is marked **SKIPPED**.

---

## Check 1: CPU/Memory Request-to-Utilization Ratios

### What it detects

Namespaces where aggregate CPU or memory requests significantly exceed actual P95 utilization, indicating systematic over-provisioning.

### Data collection

**Via Kubernetes Metrics API:**

```
Use the Kubernetes Metrics API to retrieve current pod resource usage per namespace.
Aggregate CPU (millicores) and memory (MiB) usage by namespace, excluding system namespaces.
```

**Via Kubernetes API (resource requests):**

```
Use the Kubernetes API to list all pods across non-system namespaces.
For each pod, extract spec.containers[].resources.requests.cpu and memory.
Aggregate total CPU requests (millicores) and memory requests (MiB) per namespace.
```

**Via CloudWatch GetMetricData API (preferred for P95):**

```
Use the CloudWatch GetMetricData API to retrieve P95 CPU utilization per namespace over 7 days.
Metric: pod_cpu_utilization in ContainerInsights namespace.
Dimensions: ClusterName, Namespace. Period: 604800. Stat: p95.
```

### Analysis logic

```
For each non-system namespace:
  cpu_ratio = cpu_requests / cpu_p95_actual
  mem_ratio = mem_requests / mem_p95_actual

  If cpu_ratio > 2.0 OR mem_ratio > 2.0:
    → Flag as over-provisioned (see Check 2 for per-workload detail)
```

### Namespaces to exclude

Always exclude system namespaces from this analysis:
- `kube-system`, `kube-public`, `kube-node-lease`
- `amazon-cloudwatch`, `amazon-guardduty`
- `aws-observability`, `aws-privateca-issuer`
- Any namespace matching `^kube-`, `^amazon-`, or `^aws-`

---

## Check 2: Over-Provisioned Workload Detection

### What it detects

Individual workloads (Deployments, StatefulSets, DaemonSets) where resource requests exceed P95 actual utilization by more than a configurable threshold.

### Configurable threshold

| Parameter | Default | Description |
|-----------|---------|-------------|
| `over_provision_ratio` | 2.0 | Flag when requests exceed P95 usage by this factor |
| `min_waste_dollars` | 10 | Minimum monthly waste to report (filters noise) |
| `lookback_days` | 7 | Period for utilization measurement |

### Data collection

**Via Kubernetes Metrics API:**

```
Use the Kubernetes Metrics API to get per-pod current usage in the target namespace.
Use the Kubernetes API to list deployments with their container resource requests and limits.
```

**Via CloudWatch Logs StartQuery API (per-pod P95):**

```
Use the CloudWatch Logs StartQuery API against the Container Insights performance log group
(/aws/containerinsights/<cluster>/performance) to query per-pod P95 CPU and memory
utilization over the lookback period. Filter to non-system namespaces.
```

### Analysis logic

```
For each workload in non-system namespaces:
  cpu_request = sum of container CPU requests × replicas
  mem_request = sum of container memory requests × replicas
  cpu_p95     = measured P95 CPU usage over lookback_days
  mem_p95     = measured P95 memory usage over lookback_days

  cpu_over_ratio = cpu_request / cpu_p95
  mem_over_ratio = mem_request / mem_p95

  If cpu_over_ratio > over_provision_ratio OR mem_over_ratio > over_provision_ratio:
    waste_ratio = max(0, (requests - p95_actual)) / requests
    monthly_waste = waste_ratio × workload_monthly_cost
    
    If monthly_waste >= min_waste_dollars:
      → Generate finding
```

### Severity classification

| Monthly Waste | Severity |
|---------------|----------|
| > $500 | CRITICAL |
| $200–$500 | HIGH |
| $50–$200 | MEDIUM |
| < $50 | LOW |

### Remediation

```yaml
# Install VPA in recommendation mode
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: <deployment>-vpa
  namespace: <namespace>
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: <deployment>
  updatePolicy:
    updateMode: "Off"  # Recommendation-only — review before applying
```

```bash
# Quick right-sizing: patch requests to match P95 + 20% buffer
kubectl patch deployment <deployment> -n <namespace> --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "<p95_cpu * 1.2>m"},
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/memory", "value": "<p95_mem * 1.2>Mi"}
]'
```

---

## Check 3: Low-Utilization Node Detection

### What it detects

Nodes that have been running with consistently low CPU (<10%) and memory (<20%) utilization over a 7-day period, indicating they could be consolidated or removed.

### Thresholds

| Metric | Threshold | Period |
|--------|-----------|--------|
| CPU utilization | < 10% average | 7 days |
| Memory utilization | < 20% average | 7 days |

A node must be below **both** thresholds to be flagged as idle.

### Data collection

**Via Kubernetes Metrics API (point-in-time only):**

```
Use the Kubernetes Metrics API to get current node utilization (point-in-time snapshot).
Flag nodes where CPU < 10% AND memory < 20%.
```

> **Note:** `kubectl top` provides only a point-in-time snapshot. For 7-day averages, use CloudWatch or Prometheus.

**Via CloudWatch GetMetricData API (7-day average per node):**

```
Use the CloudWatch GetMetricData API to retrieve 7-day average node CPU and memory utilization.
Metrics: node_cpu_utilization, node_memory_utilization in ContainerInsights namespace.
Dimensions: ClusterName, NodeName. Period: 86400. Stat: Average.
```

### Node inventory (for cost calculation)

```
Use the Kubernetes API to list all nodes with their labels.
Extract: node.kubernetes.io/instance-type, karpenter.sh/capacity-type or
eks.amazonaws.com/capacityType, topology.kubernetes.io/zone,
eks.amazonaws.com/nodegroup or karpenter.sh/nodepool.
```

### Analysis logic

```
For each node NOT in a system-only role:
  avg_cpu_7d = average CPU utilization over 7 days
  avg_mem_7d = average memory utilization over 7 days

  If avg_cpu_7d < 10% AND avg_mem_7d < 20%:
    instance_type = node label "node.kubernetes.io/instance-type"
    hourly_cost = lookup(instance_type, region, capacity_type)
    monthly_waste = hourly_cost × 730
    → Generate finding with monthly_waste
```

### Severity classification

| Monthly Waste (per node) | Severity |
|--------------------------|----------|
| > $500 | CRITICAL |
| $200–$500 | HIGH |
| $50–$200 | MEDIUM |
| < $50 | LOW |

Multiple idle nodes compound: total idle waste = sum of all idle node costs.

### Remediation

```yaml
# If using Karpenter — enable consolidation (see Check 4)
# If using Managed Node Groups — reduce desired capacity
aws eks update-nodegroup-config \
  --cluster-name <cluster> \
  --nodegroup-name <nodegroup> \
  --scaling-config desiredSize=<current - idle_count>,minSize=<new_min>
```

```bash
# Cordon and drain idle nodes before removal
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

---

## Check 4: Karpenter Consolidation Effectiveness

### What it detects

Whether Karpenter is installed, whether consolidation is enabled, and whether it is actively consolidating underutilized nodes.

### Data collection

**Step 1: Check if Karpenter is installed**

```
Use the Kubernetes API to list Deployments in kube-system and karpenter namespaces.
Look for a deployment named "karpenter". Alternatively, check if the NodePool CRD exists
via the API discovery endpoint.
```

**Step 2: Check consolidation configuration**

```
Use the Kubernetes API to list NodePool resources (karpenter.sh/v1).
Extract spec.disruption.consolidationPolicy, spec.disruption.consolidateAfter,
and spec.disruption.budgets for each NodePool.
For older Karpenter versions, list Provisioner resources and extract
spec.ttlSecondsAfterEmpty and spec.consolidation.
```

**Step 3: Check consolidation activity (recent events)**

```
Use the Kubernetes API to list Events with fieldSelector reason=DisruptionInitiated.
Filter for events containing "consolidat" in the message.
Also list NodeClaim resources and check status.conditions for type "Drifted"
or "Consolidatable".
```

### Analysis logic

```
If Karpenter NOT installed:
  → Skip this check (not applicable)

If Karpenter installed:
  For each NodePool:
    If consolidationPolicy is missing or "WhenEmpty":
      → Finding: consolidation not fully enabled
      severity = MEDIUM (missed optimization opportunity)
    
    If consolidationPolicy == "WhenEmptyOrUnderutilized":
      Check recent consolidation events (last 7 days):
        If zero consolidation events AND idle nodes exist (from Check 3):
          → Finding: consolidation enabled but not working
          severity = HIGH (something is blocking consolidation)
        
        If consolidation events present:
          → No finding (consolidation is working)
    
    If disruption budgets are overly restrictive (e.g., maxUnavailable: 0):
      → Finding: disruption budgets may prevent consolidation
      severity = LOW
```

### Severity classification

| Condition | Severity |
|-----------|----------|
| Consolidation disabled + idle nodes present | HIGH |
| Consolidation set to WhenEmpty only (not WhenEmptyOrUnderutilized) | MEDIUM |
| Consolidation enabled but no activity despite idle nodes | HIGH |
| Overly restrictive disruption budgets | LOW |

### Remediation

```yaml
# Enable full consolidation on NodePool
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 5m    # 30s for non-prod, 5m for prod
    budgets:
    - nodes: "10%"          # Allow disrupting up to 10% of nodes at a time
```

```bash
# Verify consolidation is working after enabling
kubectl get events --field-selector reason=DisruptionInitiated -A \
  --sort-by='.lastTimestamp' | grep -i consolidat
```

---

## Check 5: Workloads Without Resource Requests or Limits

### What it detects

Pods/containers that do not define CPU or memory requests (or limits). Without requests, the scheduler cannot make informed placement decisions, and without limits, a single pod can consume all node resources.

### Data collection

**Via Kubernetes API:**

```
Use the Kubernetes API to list all running pods across non-system namespaces.
For each pod, inspect each container's resources.requests and resources.limits.
Identify containers missing:
- CPU requests (resources.requests.cpu is null or empty)
- Memory requests (resources.requests.memory is null or empty)
- All limits (resources.limits is null or empty object)
Count affected containers per namespace.
```

**Summary count by namespace:**

```
Aggregate the missing-requests count per namespace for reporting.
```

### Analysis logic

```
For each running pod in non-system namespaces:
  For each container:
    missing_cpu_request = (resources.requests.cpu is null or empty)
    missing_mem_request = (resources.requests.memory is null or empty)
    missing_limits = (resources.limits is null or empty)

  Count total containers missing requests per namespace
  Count total containers missing limits per namespace

  If any containers missing requests:
    → Generate finding per namespace (grouped)
    severity = MEDIUM (governance gap, prevents accurate cost attribution)
  
  If > 50% of containers in a namespace missing requests:
    → Escalate to HIGH (significant governance gap)
```

### Severity classification

| Condition | Severity |
|-----------|----------|
| > 50% of containers in namespace missing requests | HIGH |
| Any containers missing requests (≤ 50%) | MEDIUM |
| Containers missing limits only (requests present) | LOW |

### Remediation

```yaml
# LimitRange to enforce defaults (apply per namespace)
apiVersion: v1
kind: LimitRange
metadata:
  name: default-resources
  namespace: <namespace>
spec:
  limits:
  - default:
      cpu: "500m"
      memory: "512Mi"
    defaultRequest:
      cpu: "100m"
      memory: "128Mi"
    type: Container
```

```yaml
# ResourceQuota to cap total namespace consumption
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute-quota
  namespace: <namespace>
spec:
  hard:
    requests.cpu: "10"
    requests.memory: "20Gi"
    limits.cpu: "20"
    limits.memory: "40Gi"
```

```bash
# Identify which Deployments need requests added
kubectl get deployments -n <namespace> -o json | \
  jq '.items[] | select(.spec.template.spec.containers | 
    any(.resources.requests.cpu == null)) | .metadata.name'
```

---

## Check 6: Graceful Degradation — Metrics Unavailable

### What it detects

Whether the required metrics sources (metrics-server, Container Insights, or Prometheus) are available. If none are available, utilization-based checks (1, 2, 3) cannot run.

### Detection logic

**Step 1: Check metrics-server availability**

```
Use the Kubernetes Metrics API (nodes endpoint). If the API returns an error
or "Metrics API not available", metrics-server is unavailable.
```

**Step 2: Check Container Insights availability**

```
Use the EKS DescribeAddon API to check if amazon-cloudwatch-observability is installed and ACTIVE.
Alternatively, use the Kubernetes API to list pods in the amazon-cloudwatch namespace
with label app.kubernetes.io/name=cloudwatch-agent.
```

**Step 3: Check Prometheus availability**

```
Use the Kubernetes API to list pods across all namespaces with labels:
- app=prometheus
- app.kubernetes.io/name=prometheus
- app.kubernetes.io/name=adot-collector
If any matching pods are running, Prometheus/AMP is available.
```

### Degradation behavior

```
metrics_server_available = (kubectl top nodes succeeds)
container_insights_available = (CloudWatch add-on is ACTIVE)
prometheus_available = (Prometheus pods running)

If metrics_server_available OR container_insights_available OR prometheus_available:
  → Proceed with utilization-based checks (1, 2, 3)
  → Use best available source (prefer Container Insights for historical P95)

If NONE available:
  → Mark checks 1, 2, 3 as SKIPPED
  → Still run checks 4 and 5 (they don't require utilization metrics)
  → Report in findings:
      status: SKIPPED
      reason: "No metrics source available (metrics-server, Container Insights, or Prometheus)"
      impact: "Cannot assess CPU/memory utilization ratios or detect idle nodes"
      remediation: "Install metrics-server (kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml) or enable Container Insights add-on"
```

### SKIPPED output format

When metrics are unavailable, include this in the report:

```markdown
### Compute Efficiency — PARTIALLY SKIPPED

**Checks completed:** Karpenter consolidation, missing resource requests/limits
**Checks skipped:** CPU/memory utilization ratios, over-provisioned workloads, idle node detection

**Reason:** No metrics source available (metrics-server, Container Insights, or Prometheus not detected)

**Impact:** Cannot calculate utilization-based waste. Dollar waste estimates for compute over-provisioning are unavailable.

**Remediation:**
- Install metrics-server: `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`
- Or enable Container Insights: `aws eks create-addon --cluster-name <cluster> --addon-name amazon-cloudwatch-observability`
- Or deploy Prometheus with kube-state-metrics
```

---

## Scoring Contribution

The compute efficiency dimension has a **maximum deduction of 25 points**.

### Deduction calculation

```
deduction = 0

For each finding in this dimension:
  If severity == CRITICAL: deduction += 25 × 0.6 = 15
  If severity == HIGH:     deduction += 25 × 0.3 = 7.5
  If severity == MEDIUM:   deduction += 25 × 0.15 = 3.75
  If severity == LOW:      deduction += 25 × 0.05 = 1.25

actual_deduction = min(deduction, 25)  # Cap at maximum
```

### Dimension status

| Condition | Status |
|-----------|--------|
| All checks completed | ASSESSED |
| Some checks skipped (partial metrics) | ASSESSED (with note) |
| All utilization checks skipped (no metrics) | SKIPPED if checks 4+5 also produce no findings |

If the dimension is fully SKIPPED, it contributes **zero deduction** and is excluded from the score denominator.

---

## Decision Tree

```
START
  │
  ├─ Is Karpenter installed?
  │   ├─ YES → Run Check 4 (consolidation effectiveness)
  │   └─ NO  → Skip Check 4
  │
  ├─ Are metrics available? (metrics-server OR Container Insights OR Prometheus)
  │   ├─ YES → Run Checks 1, 2, 3
  │   │         ├─ Use Container Insights for P95 (preferred, 7-day history)
  │   │         ├─ Use Prometheus for P95 (alternative)
  │   │         └─ Use metrics-server for point-in-time (last resort, lower confidence)
  │   └─ NO  → Mark Checks 1, 2, 3 as SKIPPED
  │
  ├─ Run Check 5 (always — only needs Kubernetes API)
  │
  └─ Aggregate findings → Calculate dimension deduction
```
