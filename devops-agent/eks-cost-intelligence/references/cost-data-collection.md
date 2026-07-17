# Cost Data Collection

> **Part of:** [eks-cost-intelligence](../SKILL.md)
> **Purpose:** Exact API calls and queries to pull cost and utilization data from Cost Explorer, CloudWatch Container Insights, and the Kubernetes API

---

## Overview

This reference documents the exact API calls needed to collect cost and utilization data from three primary sources. Each section describes the API capability and includes reference pseudocode illustrating the usage pattern.

**Data sources and what they provide:**

| Source | Data | Required For |
|--------|------|--------------|
| AWS Cost Explorer | Dollar spend, namespace attribution, Savings Plan coverage | Dollar-accurate findings |
| CloudWatch Container Insights | CPU/memory P50/P95, node utilization | Utilization-based waste detection |
| Kubernetes API | Deployments, PVCs, Services, resource requests | Configuration-based analysis |

**API access chain:**
1. AWS APIs (Cost Explorer, CloudWatch, EC2, EKS) — always available
2. Kubernetes API — always available via Agent Space
3. CloudWatch Logs Insights — when Container Insights metrics unavailable

---

## 1. AWS Cost Explorer

### Prerequisites

- Cost Allocation Tags activated in Billing console (`eks:cluster-name`, `kubernetes-namespace`)
- Split Cost Allocation Data enabled for namespace-level attribution
- IAM permission: `ce:GetCostAndUsage`, `ce:GetSavingsPlansCoverage`
- Cost Explorer API is only available in `us-east-1` regardless of cluster region

### Time Window

All Cost Explorer queries in this reference use a **7-day lookback by default**, matching the 7-day window used for CloudWatch utilization metrics. If the request names a different window (e.g., "last 30 days"), apply the override consistently to every Cost Explorer query in the assessment and record the window used in the report metadata (`Analysis Window` field). The examples below show a 30-day window for illustration; substitute the active analysis window.

### 1.1 Total EKS Spend by Service

**Via Cost Explorer GetCostAndUsage API:**

Call the Cost Explorer GetCostAndUsage API with:
- TimePeriod: last 30 days
- Granularity: MONTHLY
- Metrics: BlendedCost, UnblendedCost, UsageQuantity
- Filter: Tag eks:cluster-name = <cluster-name>
- GroupBy: SERVICE dimension

Note: Cost Explorer API is only available in us-east-1 regardless of cluster region.

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
import boto3
from datetime import date, timedelta

ce = boto3.client("ce", region_name="us-east-1")
end = date.today()
start = end - timedelta(days=30)

response = ce.get_cost_and_usage(
    TimePeriod={"Start": str(start), "End": str(end)},
    Granularity="MONTHLY",
    Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"],
    Filter={
        "Tags": {
            "Key": "eks:cluster-name",
            "Values": ["<cluster-name>"]
        }
    },
    GroupBy=[
        {"Type": "DIMENSION", "Key": "SERVICE"}
    ]
)

# Parse results
for group in response["ResultsByTime"][0]["Groups"]:
    service = group["Keys"][0]
    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
    print(f"{service}: ${cost:.2f}")
```

**Expected services in results:**
- Amazon Elastic Kubernetes Service (control plane)
- Amazon Elastic Compute Cloud (EC2 nodes)
- Amazon Elastic Block Store (EBS volumes)
- Amazon Elastic Load Balancing (ALB/NLB)
- Amazon CloudWatch (monitoring)
- Amazon VPC (NAT Gateway, data transfer)

---

### 1.2 Namespace-Level Cost Attribution (Split Cost Allocation)

Split Cost Allocation Data distributes shared EC2 and EKS costs to individual pods/namespaces based on resource requests. Must be enabled in Cost Management console.

**Via Cost Explorer GetCostAndUsage API:**

Call the Cost Explorer GetCostAndUsage API with:
- TimePeriod: last 30 days
- Granularity: MONTHLY
- Metrics: BlendedCost
- Filter: AND condition — SERVICE = Amazon Elastic Kubernetes Service AND Tag eks:cluster-name = <cluster-name>
- GroupBy: TAG kubernetes-namespace, TAG kubernetes-deployment

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
response = ce.get_cost_and_usage(
    TimePeriod={"Start": str(start), "End": str(end)},
    Granularity="MONTHLY",
    Metrics=["BlendedCost"],
    Filter={
        "And": [
            {"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Elastic Kubernetes Service"]}},
            {"Tags": {"Key": "eks:cluster-name", "Values": ["<cluster-name>"]}}
        ]
    },
    GroupBy=[
        {"Type": "TAG", "Key": "kubernetes-namespace"},
        {"Type": "TAG", "Key": "kubernetes-deployment"}
    ]
)

# Build namespace cost map
namespace_costs = {}
for group in response["ResultsByTime"][0]["Groups"]:
    ns = group["Keys"][0].replace("kubernetes-namespace$", "")
    cost = float(group["Metrics"]["BlendedCost"]["Amount"])
    namespace_costs[ns] = namespace_costs.get(ns, 0) + cost
```

**When Split Cost Allocation is not enabled:**
Fall back to node-based estimation. See [cost-estimation-fallback.md](cost-estimation-fallback.md).

---

### 1.3 Savings Plan and Reserved Instance Coverage

**Via Cost Explorer APIs:**

Call GetSavingsPlansCoverage API with:
- TimePeriod: last 30 days
- Granularity: MONTHLY
- GroupBy: INSTANCE_TYPE_FAMILY dimension

Call GetSavingsPlansUtilization API with:
- TimePeriod: last 30 days
- Granularity: MONTHLY

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
# Savings Plans coverage by instance family
coverage_response = ce.get_savings_plans_coverage(
    TimePeriod={"Start": str(start), "End": str(end)},
    Granularity="MONTHLY",
    GroupBy=[{"Type": "DIMENSION", "Key": "INSTANCE_TYPE_FAMILY"}]
)

for period in coverage_response["SavingsPlansCoverages"]:
    coverage_pct = float(period["Coverage"]["CoveragePercentage"])
    on_demand_cost = float(period["Coverage"]["OnDemandCost"])
    sp_cost = float(period["Coverage"]["SpendCoveredBySavingsPlans"])
    print(f"Coverage: {coverage_pct:.1f}% | On-Demand: ${on_demand_cost:.2f} | SP: ${sp_cost:.2f}")

# Savings Plans utilization
utilization_response = ce.get_savings_plans_utilization(
    TimePeriod={"Start": str(start), "End": str(end)},
    Granularity="MONTHLY"
)

for period in utilization_response["SavingsPlansUtilizationsByTime"]:
    util = period["Utilization"]
    util_pct = float(util["UtilizationPercentage"])
    unused = float(util["UnusedCommitment"])
    print(f"Utilization: {util_pct:.1f}% | Unused commitment: ${unused:.2f}")
```

**Interpretation thresholds:**
- Coverage < 70% on stable workloads = Savings Plan opportunity (MEDIUM finding)
- Coverage < 40% on stable workloads = significant Savings Plan opportunity (HIGH finding)
- Utilization < 80% = over-committed Savings Plans (MEDIUM finding)

---


## 2. CloudWatch Container Insights

### Prerequisites

- Container Insights enabled on the cluster (via `amazon-cloudwatch-observability` add-on or CloudWatch agent DaemonSet)
- IAM permission: `cloudwatch:GetMetricData`, `cloudwatch:ListMetrics`
- Metrics namespace: `ContainerInsights`
- Metrics are available with ~5 minute delay

### 2.1 CPU Utilization per Pod (P50 and P95)

**Via CloudWatch GetMetricData API:**

Call GetMetricData with MetricDataQueries for:
- Metric: pod_cpu_utilization in ContainerInsights namespace
- Dimensions: ClusterName, Namespace (iterate per namespace)
- Period: 3600 (hourly)
- Stats: p50, p95
- StartTime: 7 days ago
- EndTime: now

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
import boto3
from datetime import datetime, timedelta

cw = boto3.client("cloudwatch", region_name="<region>")

response = cw.get_metric_data(
    MetricDataQueries=[
        {
            "Id": "cpu_p50",
            "MetricStat": {
                "Metric": {
                    "Namespace": "ContainerInsights",
                    "MetricName": "pod_cpu_utilization",
                    "Dimensions": [
                        {"Name": "ClusterName", "Value": "<cluster>"},
                        {"Name": "Namespace", "Value": "<namespace>"},
                        {"Name": "PodName", "Value": "<pod>"}
                    ]
                },
                "Period": 3600,
                "Stat": "p50"
            }
        },
        {
            "Id": "cpu_p95",
            "MetricStat": {
                "Metric": {
                    "Namespace": "ContainerInsights",
                    "MetricName": "pod_cpu_utilization",
                    "Dimensions": [
                        {"Name": "ClusterName", "Value": "<cluster>"},
                        {"Name": "Namespace", "Value": "<namespace>"},
                        {"Name": "PodName", "Value": "<pod>"}
                    ]
                },
                "Period": 3600,
                "Stat": "p95"
            }
        }
    ],
    StartTime=datetime.utcnow() - timedelta(days=7),
    EndTime=datetime.utcnow()
)

# Extract values
for result in response["MetricDataResults"]:
    metric_id = result["Id"]
    values = result["Values"]
    avg_value = sum(values) / len(values) if values else 0
    print(f"{metric_id}: {avg_value:.2f}%")
```

---

### 2.2 Memory Utilization per Pod (P50 and P95)

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
response = cw.get_metric_data(
    MetricDataQueries=[
        {
            "Id": "mem_p50",
            "MetricStat": {
                "Metric": {
                    "Namespace": "ContainerInsights",
                    "MetricName": "pod_memory_utilization",
                    "Dimensions": [
                        {"Name": "ClusterName", "Value": "<cluster>"},
                        {"Name": "Namespace", "Value": "<namespace>"},
                        {"Name": "PodName", "Value": "<pod>"}
                    ]
                },
                "Period": 3600,
                "Stat": "p50"
            }
        },
        {
            "Id": "mem_p95",
            "MetricStat": {
                "Metric": {
                    "Namespace": "ContainerInsights",
                    "MetricName": "pod_memory_utilization",
                    "Dimensions": [
                        {"Name": "ClusterName", "Value": "<cluster>"},
                        {"Name": "Namespace", "Value": "<namespace>"},
                        {"Name": "PodName", "Value": "<pod>"}
                    ]
                },
                "Period": 3600,
                "Stat": "p95"
            }
        }
    ],
    StartTime=datetime.utcnow() - timedelta(days=7),
    EndTime=datetime.utcnow()
)
```

---

### 2.3 Node Utilization Metrics (Idle Node Detection)

**Via CloudWatch GetMetricData API:**

Call GetMetricData with MetricDataQueries for:
- Metrics: node_cpu_utilization, node_memory_utilization, cluster_node_count in ContainerInsights namespace
- Dimensions: ClusterName
- Period: 86400 (daily)
- Stat: Average
- StartTime: 7 days ago
- EndTime: now

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
response = cw.get_metric_data(
    MetricDataQueries=[
        {
            "Id": "node_cpu",
            "MetricStat": {
                "Metric": {
                    "Namespace": "ContainerInsights",
                    "MetricName": "node_cpu_utilization",
                    "Dimensions": [{"Name": "ClusterName", "Value": "<cluster>"}]
                },
                "Period": 86400,
                "Stat": "Average"
            }
        },
        {
            "Id": "node_mem",
            "MetricStat": {
                "Metric": {
                    "Namespace": "ContainerInsights",
                    "MetricName": "node_memory_utilization",
                    "Dimensions": [{"Name": "ClusterName", "Value": "<cluster>"}]
                },
                "Period": 86400,
                "Stat": "Average"
            }
        }
    ],
    StartTime=datetime.utcnow() - timedelta(days=7),
    EndTime=datetime.utcnow()
)

# Idle node threshold: average CPU < 10% AND memory < 20% for 7 days
for result in response["MetricDataResults"]:
    values = result["Values"]
    if values:
        avg = sum(values) / len(values)
        if result["Id"] == "node_cpu" and avg < 10.0:
            print(f"IDLE NODE CANDIDATE: avg CPU {avg:.1f}% over 7 days")
```

**Idle node detection thresholds:**
- Average CPU < 10% for 7 days = idle node candidate
- Average memory < 20% for 7 days = under-utilized node
- Both CPU < 10% AND memory < 20% = strong consolidation signal

---

### 2.4 Fallback: CloudWatch Logs Insights

When Container Insights metrics are not available (add-on not installed, metrics not publishing), query the performance log group directly. This requires Container Insights to be configured for log collection even if metric publishing is disabled.

**Log group:** `/aws/containerinsights/<cluster-name>/performance`

**Via CloudWatch Logs StartQuery API:**

Call StartQuery against log group /aws/containerinsights/<cluster-name>/performance with:
- Query: fields pod_cpu_utilization, pod_memory_utilization filtered by Type="Pod",
  stats percentile(95) grouped by namespace and pod name
- StartTime: 7 days ago
- EndTime: now

Then call GetQueryResults with the returned queryId (query is async, poll until Complete).

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
import time

logs = boto3.client("logs", region_name="<region>")

# Start the query
query_response = logs.start_query(
    logGroupName=f"/aws/containerinsights/{cluster_name}/performance",
    startTime=int((datetime.utcnow() - timedelta(days=7)).timestamp()),
    endTime=int(datetime.utcnow().timestamp()),
    queryString="""
        fields @timestamp, kubernetes.namespace_name, kubernetes.pod_name,
               pod_cpu_utilization, pod_memory_utilization
        | filter Type = "Pod"
        | stats avg(pod_cpu_utilization) as avg_cpu,
                percentile(pod_cpu_utilization, 50) as p50_cpu,
                percentile(pod_cpu_utilization, 95) as p95_cpu,
                avg(pod_memory_utilization) as avg_mem,
                percentile(pod_memory_utilization, 50) as p50_mem,
                percentile(pod_memory_utilization, 95) as p95_mem
          by kubernetes.namespace_name, kubernetes.pod_name
        | sort p95_cpu desc
        | limit 100
    """
)

query_id = query_response["queryId"]

# Poll for results (query is async)
while True:
    result = logs.get_query_results(queryId=query_id)
    if result["status"] == "Complete":
        break
    time.sleep(1)

# Parse results into usable format
pod_metrics = []
for row in result["results"]:
    fields = {f["field"]: f["value"] for f in row}
    pod_metrics.append({
        "namespace": fields.get("kubernetes.namespace_name"),
        "pod": fields.get("kubernetes.pod_name"),
        "p50_cpu": float(fields.get("p50_cpu", 0)),
        "p95_cpu": float(fields.get("p95_cpu", 0)),
        "p50_mem": float(fields.get("p50_mem", 0)),
        "p95_mem": float(fields.get("p95_mem", 0)),
    })
```

**Node-level utilization via Logs Insights:**

Call StartQuery with query filtering Type="Node", computing avg CPU/memory by NodeName,
filtering for avg_cpu < 10. Then poll GetQueryResults.

**When to use Logs Insights fallback:**
- Container Insights metrics not publishing to CloudWatch Metrics
- Need historical data beyond CloudWatch Metrics retention
- Need per-pod granularity not available in aggregated metrics

---


## 3. Kubernetes API

### Prerequisites

- Kubernetes API access available via Agent Space
- RBAC permissions: `get`, `list` on deployments, pods, services, persistentvolumeclaims, nodes, namespaces
- For full analysis: access to all namespaces (cluster-wide read)

### 3.1 Deployments with Resource Requests

**Via Kubernetes API:**

Use the Kubernetes API to:
1. List all Deployments across all namespaces (apps/v1 API group)
   - Extract spec.template.spec.containers[].resources.requests and limits for each
2. Identify Deployments where any container has null/empty CPU or memory requests
3. List all Pods across all namespaces
   - Aggregate total CPU requests (cores) and memory requests (GiB) per namespace

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
from kubernetes import client, config

config.load_kube_config()
apps_v1 = client.AppsV1Api()

# List all deployments
deployments = apps_v1.list_deployment_for_all_namespaces()

deployment_resources = []
for deploy in deployments.items:
    ns = deploy.metadata.namespace
    name = deploy.metadata.name
    replicas = deploy.spec.replicas or 0

    for container in deploy.spec.template.spec.containers:
        requests = container.resources.requests or {}
        limits = container.resources.limits or {}
        deployment_resources.append({
            "namespace": ns,
            "deployment": name,
            "container": container.name,
            "replicas": replicas,
            "cpu_request": requests.get("cpu", "NOT_SET"),
            "mem_request": requests.get("memory", "NOT_SET"),
            "cpu_limit": limits.get("cpu", "NOT_SET"),
            "mem_limit": limits.get("memory", "NOT_SET"),
        })
```

---

### 3.2 PersistentVolumeClaims with Status

**Via Kubernetes API:**

Use the Kubernetes API to:
1. List all PersistentVolumeClaims across all namespaces
   - Extract storageClassName, status.capacity.storage, status.phase, spec.volumeName
2. Filter PVCs using storageClassName "gp2" or null (migration candidates)
3. Cross-reference: List all Pods and extract spec.volumes[].persistentVolumeClaim.claimName
   - Identify Bound PVCs not referenced by any running pod (unmounted)

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
v1 = client.CoreV1Api()

# Get all PVCs
pvcs = v1.list_persistent_volume_claim_for_all_namespaces()

# Get all pods to check which PVCs are mounted
pods = v1.list_pod_for_all_namespaces()
mounted_pvcs = set()
for pod in pods.items:
    if pod.spec.volumes:
        for vol in pod.spec.volumes:
            if vol.persistent_volume_claim:
                mounted_pvcs.add(
                    f"{pod.metadata.namespace}/{vol.persistent_volume_claim.claim_name}"
                )

pvc_analysis = []
for pvc in pvcs.items:
    pvc_key = f"{pvc.metadata.namespace}/{pvc.metadata.name}"
    pvc_analysis.append({
        "namespace": pvc.metadata.namespace,
        "name": pvc.metadata.name,
        "storage_class": pvc.spec.storage_class_name or "default",
        "capacity": pvc.status.capacity.get("storage") if pvc.status.capacity else "unknown",
        "phase": pvc.status.phase,
        "is_mounted": pvc_key in mounted_pvcs,
        "is_gp2": pvc.spec.storage_class_name in (None, "gp2"),
    })
```

---

### 3.3 Services with Type (Load Balancer Detection)

**Via Kubernetes API:**

Use the Kubernetes API to:
1. List all Services across all namespaces — filter for spec.type == "LoadBalancer"
   - Extract external hostname/IP, ports, externalTrafficPolicy, annotations
2. List all Endpoints across all namespaces
   - Identify Endpoints with null/empty subsets (no healthy backends)
3. List Services missing topology-aware routing annotations
   (service.kubernetes.io/topology-mode or service.kubernetes.io/topology-aware-hints)

**Via ELB API (cross-reference for orphaned LB detection):**

Use the ELBv2 DescribeLoadBalancers API to list all load balancers.
For each, use DescribeTargetHealth to check for target groups with 0 healthy targets.

**API pattern (reference pseudocode):**

> Note: These are reference pseudocode for the API patterns, not executable code.

```python
elbv2 = boto3.client("elbv2", region_name="<region>")

# List all target groups
tgs = elbv2.describe_target_groups()

orphaned_lbs = []
for tg in tgs["TargetGroups"]:
    health = elbv2.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])
    healthy_count = sum(
        1 for t in health["TargetHealthDescriptions"]
        if t["TargetHealth"]["State"] == "healthy"
    )
    if healthy_count == 0:
        orphaned_lbs.append({
            "target_group": tg["TargetGroupName"],
            "arn": tg["TargetGroupArn"],
            "lb_arns": tg.get("LoadBalancerArns", []),
            "healthy_targets": 0
        })
```

---

### 3.4 Node Information (Instance Types, Architecture, Capacity Type)

**Via Kubernetes API:**

Use the Kubernetes API to list all Nodes and extract:
- metadata.labels: node.kubernetes.io/instance-type, kubernetes.io/arch,
  karpenter.sh/capacity-type or eks.amazonaws.com/capacityType, topology.kubernetes.io/zone
- status.allocatable: cpu, memory
- status.conditions: Ready status

Aggregate by instance type to produce a summary (count, architecture, capacity type per type).

---


## 4. Data Correlation Logic

Once data is collected from all three sources, correlate them to produce dollar-denominated waste findings.

### 4.1 Correlation Strategy

```mermaid
flowchart TD
    CE[Cost Explorer: namespace costs] --> CORR[Correlation Engine]
    CW[Container Insights: P95 utilization] --> CORR
    K8s[Kubernetes API: resource requests] --> CORR
    CORR --> WASTE[Dollar waste per namespace/workload]
    CORR --> IDLE[Idle resource costs]
    CORR --> OPP[Optimization opportunities]
```

### 4.2 Namespace-Level Waste Calculation

```python
def correlate_namespace_waste(namespace_costs, namespace_metrics, namespace_requests):
    """
    Correlate Cost Explorer spend with utilization metrics and resource requests
    to calculate per-namespace waste.

    Args:
        namespace_costs: dict[str, float] - from Cost Explorer (Section 1.2)
        namespace_metrics: dict[str, dict] - from Container Insights (Section 2.1/2.2)
            Format: {"ns": {"p95_cpu": float, "p95_mem": float}}
        namespace_requests: dict[str, dict] - from Kubernetes API (Section 3.1)
            Format: {"ns": {"total_cpu_cores": float, "total_mem_gi": float}}

    Returns:
        list[dict] - waste findings per namespace
    """
    findings = []

    for ns, cost in namespace_costs.items():
        if ns in ("kube-system", "kube-public", "kube-node-lease"):
            continue  # Skip system namespaces

        metrics = namespace_metrics.get(ns, {})
        requests = namespace_requests.get(ns, {})

        if not metrics or not requests:
            continue  # Cannot calculate waste without both data points

        # CPU waste ratio
        cpu_request = requests.get("total_cpu_cores", 0)
        cpu_p95 = metrics.get("p95_cpu", 0)
        if cpu_request > 0:
            cpu_waste_ratio = max(0, (cpu_request - cpu_p95) / cpu_request)
        else:
            cpu_waste_ratio = 0

        # Memory waste ratio
        mem_request = requests.get("total_mem_gi", 0)
        mem_p95 = metrics.get("p95_mem", 0)
        if mem_request > 0:
            mem_waste_ratio = max(0, (mem_request - mem_p95) / mem_request)
        else:
            mem_waste_ratio = 0

        # Use conservative (lower) ratio
        waste_ratio = min(cpu_waste_ratio, mem_waste_ratio)

        # Calculate dollar waste (with 15% headroom buffer)
        headroom_factor = 0.85
        monthly_waste = waste_ratio * cost * headroom_factor

        if monthly_waste > 50:  # Only report if above LOW threshold
            findings.append({
                "namespace": ns,
                "monthly_cost": cost,
                "waste_ratio": waste_ratio,
                "monthly_waste": monthly_waste,
                "cpu_waste_ratio": cpu_waste_ratio,
                "mem_waste_ratio": mem_waste_ratio,
                "confidence": "high" if cost > 0 and metrics else "medium"
            })

    return sorted(findings, key=lambda f: f["monthly_waste"], reverse=True)
```

### 4.3 Idle Resource Cost Correlation

```python
def correlate_idle_resources(services, endpoints, elb_costs):
    """
    Cross-reference Kubernetes Services with endpoint health and ELB costs
    to identify orphaned load balancers.

    Args:
        services: list[dict] - LoadBalancer services from Section 3.3
        endpoints: list[dict] - endpoint status from Section 3.3
        elb_costs: dict[str, float] - per-LB monthly cost from Cost Explorer

    Returns:
        list[dict] - idle LB findings with cost
    """
    # Build set of services with no healthy endpoints
    empty_endpoints = {
        f"{ep['namespace']}/{ep['name']}"
        for ep in endpoints
        if ep.get("reason") == "no_endpoints"
    }

    findings = []
    for svc in services:
        svc_key = f"{svc['namespace']}/{svc['name']}"
        if svc_key in empty_endpoints:
            # Estimate LB cost: ~$16.43/month (NLB) or ~$22.27/month (ALB) base
            lb_hostname = svc.get("external_ip", "")
            monthly_cost = elb_costs.get(lb_hostname, 16.43)  # default NLB base cost

            findings.append({
                "dimension": "idle",
                "severity": "HIGH" if monthly_cost > 200 else "MEDIUM",
                "affected_resource": svc_key,
                "current_state": f"LoadBalancer with 0 healthy targets",
                "monthly_cost": monthly_cost,
                "monthly_waste": monthly_cost,  # 100% waste if no targets
                "monthly_savings": monthly_cost,
                "effort": "Low",
                "fix_summary": f"Delete unused Service {svc['name']} or fix backend pods",
                "confidence": "high"
            })

    return findings
```

### 4.4 Storage Waste Correlation

```python
def correlate_storage_waste(pvcs, ebs_volumes):
    """
    Cross-reference PVCs with EBS volume data to identify storage waste.

    Args:
        pvcs: list[dict] - from Section 3.2
        ebs_volumes: list[dict] - from EC2 DescribeVolumes

    Returns:
        list[dict] - storage waste findings
    """
    findings = []

    for pvc in pvcs:
        # gp2 to gp3 migration opportunity
        if pvc.get("is_gp2") and pvc.get("phase") == "Bound":
            capacity_gb = parse_storage_size(pvc.get("capacity", "0"))
            # gp2: $0.10/GB/month, gp3: $0.08/GB/month = 20% savings
            monthly_cost = capacity_gb * 0.10
            monthly_savings = capacity_gb * 0.02  # $0.02/GB savings

            findings.append({
                "dimension": "storage",
                "severity": classify_severity(monthly_savings),
                "affected_resource": f"{pvc['namespace']}/{pvc['name']}",
                "current_state": f"Using gp2 StorageClass ({capacity_gb}Gi)",
                "monthly_cost": monthly_cost,
                "monthly_waste": monthly_savings,
                "monthly_savings": monthly_savings,
                "effort": "Medium",
                "fix_summary": "Migrate to gp3 StorageClass (20% cost reduction)",
                "confidence": "high"
            })

        # Unmounted PVC waste
        if pvc.get("phase") == "Bound" and not pvc.get("is_mounted"):
            capacity_gb = parse_storage_size(pvc.get("capacity", "0"))
            monthly_cost = capacity_gb * 0.10  # assume gp2/gp3 pricing
            findings.append({
                "dimension": "storage",
                "severity": classify_severity(monthly_cost),
                "affected_resource": f"{pvc['namespace']}/{pvc['name']}",
                "current_state": f"Bound PVC ({capacity_gb}Gi) not mounted by any pod",
                "monthly_cost": monthly_cost,
                "monthly_waste": monthly_cost,
                "monthly_savings": monthly_cost,
                "effort": "Low",
                "fix_summary": "Delete unused PVC or attach to workload",
                "confidence": "high"
            })

    return findings


def parse_storage_size(size_str):
    """Parse Kubernetes storage size string to GB."""
    if size_str.endswith("Ti"):
        return float(size_str[:-2]) * 1024
    elif size_str.endswith("Gi"):
        return float(size_str[:-2])
    elif size_str.endswith("Mi"):
        return float(size_str[:-2]) / 1024
    else:
        return float(size_str) / (1024**3)  # assume bytes


def classify_severity(monthly_amount):
    """Classify finding severity based on monthly dollar impact."""
    if monthly_amount > 500:
        return "CRITICAL"
    elif monthly_amount > 200:
        return "HIGH"
    elif monthly_amount > 50:
        return "MEDIUM"
    else:
        return "LOW"
```

### 4.5 Complete Correlation Workflow

```python
def run_full_correlation(cluster_name, region):
    """
    Complete data collection and correlation workflow.
    Returns all findings ready for scoring.
    """
    findings = []
    data_sources_used = []
    skipped_dimensions = []

    # --- Step 1: Collect Cost Explorer data ---
    try:
        namespace_costs = get_namespace_costs(cluster_name)  # Section 1.2
        sp_coverage = get_savings_plan_coverage()             # Section 1.3
        data_sources_used.append("Cost Explorer")
    except Exception as e:
        print(f"Cost Explorer unavailable: {e}")
        print("Falling back to node-based estimation")
        namespace_costs = estimate_costs_from_nodes(cluster_name)  # See cost-estimation-fallback.md
        data_sources_used.append("Node-based estimation")

    # --- Step 2: Collect Container Insights metrics ---
    try:
        namespace_metrics = get_pod_metrics(cluster_name, region)  # Section 2.1/2.2
        node_metrics = get_node_metrics(cluster_name, region)      # Section 2.3
        data_sources_used.append("Container Insights")
    except Exception as e:
        print(f"Container Insights metrics unavailable: {e}")
        try:
            # Fallback to Logs Insights
            namespace_metrics = get_metrics_from_logs(cluster_name, region)  # Section 2.4
            node_metrics = get_node_metrics_from_logs(cluster_name, region)
            data_sources_used.append("CloudWatch Logs Insights")
        except Exception as e2:
            print(f"Logs Insights also unavailable: {e2}")
            namespace_metrics = {}
            node_metrics = {}
            skipped_dimensions.append("compute_efficiency")

    # --- Step 3: Collect Kubernetes resource data ---
    try:
        deployments = get_deployments_with_requests()   # Section 3.1
        pvcs = get_pvcs_with_status()                   # Section 3.2
        services = get_services_with_type()             # Section 3.3
        endpoints = get_endpoints_status()              # Section 3.3
        nodes = get_node_info()                         # Section 3.4
        data_sources_used.append("Kubernetes API")
    except Exception as e:
        print(f"FATAL: Cannot access Kubernetes API: {e}")
        raise  # Cannot proceed without K8s access

    # --- Step 4: Correlate and generate findings ---

    # Compute waste (requires metrics + requests + costs)
    if "compute_efficiency" not in skipped_dimensions:
        namespace_requests = aggregate_requests_by_namespace(deployments)
        compute_findings = correlate_namespace_waste(
            namespace_costs, namespace_metrics, namespace_requests
        )
        findings.extend(compute_findings)

    # Storage waste (requires PVCs)
    storage_findings = correlate_storage_waste(pvcs, [])
    findings.extend(storage_findings)

    # Idle resources (requires services + endpoints)
    idle_findings = correlate_idle_resources(services, endpoints, {})
    findings.extend(idle_findings)

    # Savings Plan opportunity (requires Cost Explorer)
    if sp_coverage and sp_coverage < 70:
        findings.append({
            "dimension": "compute",
            "severity": "MEDIUM" if sp_coverage > 40 else "HIGH",
            "affected_resource": "cluster-wide",
            "current_state": f"Savings Plan coverage at {sp_coverage:.0f}%",
            "monthly_waste": 0,  # Opportunity, not waste
            "monthly_savings": 0,  # Calculated separately
            "effort": "Medium",
            "fix_summary": "Evaluate Compute Savings Plans for stable workloads",
            "confidence": "medium"
        })

    return {
        "findings": findings,
        "data_sources": data_sources_used,
        "skipped_dimensions": skipped_dimensions,
        "namespace_costs": namespace_costs,
    }
```

---

## 5. Data Source Availability Matrix

| Check | Cost Explorer | Container Insights | Kubernetes API | Fallback |
|-------|:---:|:---:|:---:|---|
| Total cluster spend | Required | — | — | Node-based estimation |
| Namespace cost attribution | Required | — | — | Node-based estimation |
| Savings Plan coverage | Required | — | — | Skip (note in report) |
| CPU/memory P50/P95 | — | Required | — | Logs Insights or metrics-server |
| Node utilization | — | Required | — | Logs Insights |
| Resource requests | — | — | Required | Cannot skip |
| PVC storage class | — | — | Required | Cannot skip |
| Service type/endpoints | — | — | Required | Cannot skip |
| Node instance types | — | — | Required | EC2 DescribeInstances |

**Minimum viable assessment:** Kubernetes API alone enables configuration-based findings (missing requests, gp2 volumes, orphaned LBs). Adding Container Insights enables utilization-based findings. Adding Cost Explorer enables dollar-accurate attribution.

---

## 6. Rate Limits and Performance

| API | Rate Limit | Mitigation |
|-----|-----------|------------|
| Cost Explorer | 5 requests/second | Batch time periods, cache results |
| CloudWatch GetMetricData | 50 TPS, 100,800 datapoints/call | Use fewer queries with multiple metrics per call |
| CloudWatch Logs Insights | 30 concurrent queries | Run sequentially, poll with backoff |
| Kubernetes API | Varies by cluster | Use label selectors to reduce response size |
| EC2 DescribeInstances | 100 requests/second | Paginate with MaxResults |

**Best practices:**
- Cache Cost Explorer results (data updates daily, not real-time)
- Batch CloudWatch metric queries (up to 500 MetricDataQueries per call)
- Use label selectors with Kubernetes API list calls to reduce payload
- Run Logs Insights queries sequentially and poll with exponential backoff
