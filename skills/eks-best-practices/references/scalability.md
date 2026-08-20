# EKS Scalability

> **Part of:** [eks-best-practices](../SKILL.md)
> **Purpose:** Scaling theory, control plane and data plane scaling, cluster services, workload patterns, node efficiency, and large-cluster guidance for Amazon EKS

---

## Table of Contents

1. [Scaling Theory](#scaling-theory)
2. [Control Plane Scaling](#control-plane-scaling)
3. [Data Plane Scaling](#data-plane-scaling)
4. [Cluster Services Scaling](#cluster-services-scaling)
5. [Workload Scaling](#workload-scaling)
6. [Node & Workload Efficiency](#node--workload-efficiency)
7. [Large Cluster Guidance](#large-cluster-guidance)

---

## Scaling Theory

### Think in Churn Rate, Not Node Count

A 5,000-node cluster with stable, long-running pods puts little stress on the control plane. A 1,000-node cluster creating 10,000 short-lived jobs per minute puts enormous pressure on it. **Churn rate** -- the rate of change over a 5-minute window -- is a better indicator of scaling stress than cluster size alone.

### Think in QPS

Kubernetes components have rate-limiting mechanisms (Kubelet QPS to API server, scheduler throughput, controller manager work queues). Removing one bottleneck shifts pressure downstream. Change QPS settings with care -- monitor each component in the chain before and after adjustments.

### Scale by Metrics, Not Fixed Numbers

Don't rely on fixed limits like "110 pods per node." Instead, monitor metrics that reveal whether each component is keeping up. The Pod Lifecycle Event Generator (PLEG) duration is a key signal for node saturation:

```promql
# Detect if kubelet can't keep up with container runtime
increase(kubelet_pleg_relist_duration_seconds_bucket{instance="$instance"}[$__rate_interval])

# Find the most saturated nodes cluster-wide
topk(3, increase(kubelet_pleg_discard_events{}[$__rate_interval]))
```

If PLEG durations hit the timeout, the node is over its limit. Fix the cause (reduce pods per node, fix error-induced retries) before scaling further.

### Split Bottlenecks in Half

When investigating scaling issues, check metrics in both upstream and downstream directions from the suspected bottleneck. Start at the API server -- it sits between clients and the control plane, so you can quickly determine which side has the problem. Avoid chasing the first suspicious metric; look at the full picture downstream first.

---

## Control Plane Scaling

EKS automatically scales the control plane (API servers across 2+ AZs, etcd across 3 AZs), but there are limits on how fast it scales.

For large clusters that hit these auto-scaling limits, **EKS Provisioned Control Plane (PCP)** directly addresses the API-scaling concern: it offers a 99.99% SLA, an 8XL control-plane tier (added 2026-03), and faster pod autoscaling (added 2026-07). See [Amazon EKS Provisioned Control Plane](https://docs.aws.amazon.com/eks/latest/userguide/eks-provisioned-control-plane.html). Consider it before relying solely on the Terraform-level burst knobs below.

### Control Plane Configuration Parameters

**As of 2026-08-12**, EKS lets you customize selected managed control-plane component settings directly on the cluster ([Advanced Kubernetes control plane configuration](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-configuration.html)), via new fields on the existing `CreateCluster` / `UpdateClusterConfig` APIs — `kubeSchedulerConfig`, `kubeControllerManagerConfig`, and `kubeApiServerConfig`. Settings are **cluster-wide** (they apply to every workload — you can't scope them to a namespace); EKS validates each change, records it in CloudTrail, and there's **no additional charge for the configuration itself**. A change is **not instant** — EKS applies it as a rolling control-plane update that takes several minutes (block on `aws eks wait cluster-active`, or track `DescribeUpdate`), and the cluster keeps the same availability and performance throughout. Requires **Kubernetes 1.31+** and is available in all AWS commercial, GovCloud (US), and China Regions where EKS is available. Configure it via the Console, **eksctl**, AWS CLI / EKS API (SDKs), CloudFormation, or **AWS CDK**; support for **ACK and Terraform is coming soon** (as of 2026-08-20).

| Component | Parameter | Supported values | Default | Requires PCP |
|---|---|---|---|---|
| kube-scheduler | `nodeResourcesFit.scoringStrategy` | `LeastAllocated`, `MostAllocated` | `LeastAllocated` (`cpu:1, memory:1`) | No |
| kube-controller-manager | `horizontalPodAutoscalerControllerConfig.horizontalPodAutoscalerSyncPeriod` | `10s`–`15s` | `15s` | **Yes** |
| kube-apiserver | `eventTtl` | `10m`–`60m` | `60m` | No |
| kube-apiserver | `serviceNodePortRange` (`minPort`/`maxPort`) | `10260`–`32767` | `30000`–`32767` | No |

The values above are as-published for K8s 1.31+; treat **`DescribeClusterVersions`** as the source of truth for the current default and supported range per version (`aws eks describe-cluster-versions --cluster-versions <ver>`), especially if you automate cluster config across versions. There is **no reset operation**, and omitting a field on update does not clear it (updates merge) — to revert *any* parameter, set it explicitly back to its default (look the default up via `DescribeClusterVersions`).

**Scheduler — `MostAllocated` (bin-packing).** `LeastAllocated` (default) spreads pods to leave headroom on every node; `MostAllocated` packs pods onto already-utilized nodes so the same workloads run on fewer nodes, and node pools that support consolidation can then reclaim the emptied ones. Before relying on it for cost:

- It only changes **scoring among nodes that can already run the pod** — it does **not** change how Karpenter or EKS Auto Mode provisions or removes nodes. Bin-packing happens onto *existing* capacity, so validate the combined behavior against your provisioner before trusting it for savings.
- **Running pods are never moved** — the strategy affects future placement only. To rebalance, evict/restart pods.
- Packing **concentrates blast radius** (more pods lost per node/AZ failure) and densely packed nodes fill faster, so pods can sit `Pending` while new capacity comes up. Watch the headroom trade-off.
- In **multi-tenant** clusters, packing concentrates **correlated-failure / blast-radius** risk (one dense node's *involuntary* loss — unhealthy node, instance retirement, AZ disruption — can take out a whole tenant or service). Spread replicas across failure domains with `topologySpreadConstraints` (the remedy for involuntary loss); PDBs only bound *voluntary* disruptions (the drains/evictions that `MostAllocated`-driven consolidation triggers), not a node failing. For the separate resource-isolation dimension (noisy neighbors on a packed node), rely on per-pod requests/limits and `ResourceQuota`/`LimitRange`.
- You can optionally weight resources (`cpu`, `memory`, `nvidia.com/gpu`, `aws.amazon.com/neuron`, `aws.amazon.com/neuroncore`; weights 1–100) — useful when an accelerator, not CPU/memory, is the scarce resource.

**Controller manager — HPA sync period (requires PCP).** Shortening `horizontalPodAutoscalerSyncPeriod` from the default `15s` toward `10s` makes HPA react sooner to load — a fit for many-HPA / bursty clusters. It **requires [Provisioned Control Plane](https://docs.aws.amazon.com/eks/latest/userguide/eks-provisioned-control-plane.html)** — the config itself is free, but this is the one parameter that forces a **paid PCP tier** (billed at the hourly rate for your chosen tier), which is sized to absorb the extra reconcile traffic and pairs with PCP's faster pod autoscaling (noted above). Trade-off: a shorter period gives the controller less time per cycle, so it **lowers the number of HPA objects the control plane can reconcile on schedule** (≈one-third fewer going `15s`→`10s`). EKS does **not** validate the period against your HPA count and won't alarm if it's exceeded — the symptom is *slower* autoscaling, the opposite of intent. Count your objects (`kubectl get hpa -A --no-headers | wc -l`) first, and revert to `15s` if scaling lags. **One-way lock:** while this parameter is set to any non-default value you cannot move the control plane from Provisioned back to Standard mode — reset it to `15s` first, then switch the tier to `standard`.

**API server — event retention (`eventTtl`).** High-churn clusters (batch, CI/CD, AI/ML, frequent CronJobs) accumulate thousands of events that consume etcd space and slow event LISTs. Shortening retention from `60m` toward `10m` sheds that pressure — but it applies to **new events only** (existing events age out on their original TTL), deleted events are unrecoverable, and it narrows the `kubectl get events` / `describe` window for incident investigation and debugging. (Kubernetes events are ephemeral diagnostics, **not** the audit record — the EKS control-plane Kubernetes audit log (CloudWatch Logs) and AWS API-level auditing (CloudTrail) are separate and unaffected by `eventTtl`.) Shorten only if you ship events to a durable store, so investigation doesn't depend on the in-cluster TTL.

**API server — service node port range.** Widen or shift `serviceNodePortRange` (bounded `10260`–`32767`) to align node-port allocation with existing firewall policy, or to support more services — especially useful when migrating apps that expect fixed ports outside the default `30000`–`32767`. The range covers `NodePort` services and, by default, `type=LoadBalancer` services too, so narrowing it can affect LoadBalancer services as well, not just NodePort. `minPort ≤ maxPort` is enforced, and existing services keep their ports (only recreating a service reallocates). Before changing the range, confirm your security groups and network ACLs allow it and that it doesn't collide with ports other node software uses — the `10260` floor exists to clear Kubernetes node health ports (kubelet `10248`, kube-proxy `10256`). What's actually exposed on node IPs is the set of *allocated* NodePorts plus your SG/NACL rules (not the configured range width itself), so keep those locked down.

> **Roll cluster-wide changes out carefully.** Every parameter here affects the entire cluster and all workloads. Test in a non-production cluster first, and change one parameter at a time so you can attribute any behavior change.

### etcd Database Size Limits

etcd database size is a hard ceiling, not a soft target — when it is exceeded, etcd emits a "no space" alarm and the cluster goes **read-only** (no new pods, no scaling, no deployments). Know your ceiling and watch the *trend* toward it. The following figures are per the [EKS Provisioned Control Plane docs](https://docs.aws.amazon.com/eks/latest/userguide/eks-provisioned-control-plane.html), verified for EKS v1.30–v1.34+ (re-check the page for your version, as tiers and caps evolve):

| Mode | etcd DB size ceiling |
|---|---|
| **Standard** (auto-scaling) control plane | **8 GB** |
| **Provisioned Control Plane** (all tiers) | **16 GB, flat** across every PCP tier (XL → 8XL) |

> **PCP exit restriction.** Once a cluster's etcd database exceeds **8 GB** while on Provisioned mode, you **cannot switch back to Standard** until you reduce it below 8 GB. Growing past the Standard ceiling is a one-way door until you shed data — plan capacity accordingly.

**Alert on the rate of growth toward the ceiling, not on a mid-range absolute.** A database sitting at a healthy fraction of its limit is not a problem — an absolute value in the middle of the range is normal and alarming on it causes fatigue and premature escalation. What matters is a *sustained upward trend* that will reach the ceiling. AWS documents pre-built alert rules for exactly this — `etcdBackendQuotaLowSpace` (near-quota) and `etcdExcessiveDatabaseGrowth` (trend) — in [Managing etcd database size on Amazon EKS clusters](https://aws.amazon.com/blogs/containers/managing-etcd-database-size-on-amazon-eks-clusters/). Track `apiserver_storage_size_bytes` and reduce CRD/object churn (event TTLs, finalizer hygiene) to hold headroom.

**Attribute latency correctly — don't alarm on LIST latency alone.** A high LIST/read latency during a surge is a *symptom* whose root cause may be etcd or the API server. The cluster-wide read SLO is generous (upstream targets **≤30 s** at p99 for cluster/namespace-scoped LISTs; ≤1 s for single-resource reads — see [Kubernetes SLOs](https://github.com/kubernetes/community/blob/master/sig-scalability/slos/slos.md)), so a LIST-latency number that looks alarming in isolation may be within SLO. Correlate LIST latency with `etcd_request_duration_seconds` before tuning — the skill already teaches this chain at [observability.md — API vs etcd Latency](observability.md#api-vs-etcd-latency).

### Burst Limits

Avoid scaling spikes that increase cluster size by more than ~10% at a time (e.g., 1,000 to 1,100 nodes, or 4,000 to 4,500 pods at once). The control plane auto-scales but needs time to adapt. New clusters will not immediately support hundreds of nodes.

Use custom metrics in HPA (requests/second, queue depth) rather than just CPU/memory to control scaling speed and match your application's actual constraints.

### API Priority and Fairness (APF)

APF controls how the API server divides its inflight request quota among different request types, preventing noisy clients from starving critical system requests.

The API server limits total inflight requests via `--max-requests-inflight` (400) + `--max-mutating-requests-inflight` (200) = 600 per API server. EKS increases this to ~2,000 as the control plane scales. With 2+ API servers, the cluster handles several thousand requests/second.

**PriorityLevelConfigurations** define priority buckets, **FlowSchemas** route requests to them. EKS uses Kubernetes defaults, which work for most clusters. Monitor for 429 (Too Many Requests) errors:

```promql
# Monitor API server rejections
apiserver_request_total{code="429"}
```

If you see 429s from your controllers, they're likely making excessive LIST calls. Switch to watches/informers where possible.

### Control Plane Monitoring

**API Server metrics:**

| Metric | What It Tells You |
|--------|-------------------|
| `apiserver_request_total` | Request volume by verb, resource, response code |
| `apiserver_request_duration_seconds` | Response latency by verb and resource |
| `apiserver_admission_controller_admission_duration_seconds` | Admission webhook latency |
| `apiserver_admission_webhook_rejection_count` | Webhook rejection rate |
| `rest_client_request_duration_seconds` | Outbound request latency |

**etcd metrics:**

| Metric | What It Tells You |
|--------|-------------------|
| `etcd_request_duration_seconds` | etcd latency per operation |
| `apiserver_storage_size_bytes` | etcd database size |

When etcd's database size exceeds its limit, it emits a "no space" alarm and the cluster becomes **read-only** -- no new pods, no scaling, no deployments.

Consider the [Kubernetes Monitoring Overview Dashboard](https://grafana.com/grafana/dashboards/14623) to visualize API server and etcd metrics.

### kubectl Optimization

| Tip | Why |
|-----|-----|
| Retain `--cache-dir` | Avoids redundant discovery API calls (default: 10-min cache) |
| Set `disable-compression: true` | Reduces CPU on client and server if bandwidth is adequate |
| Avoid kubectl in tight loops | Use watches/informers instead of repeated GET/LIST calls |

```yaml
# kubeconfig with compression disabled
apiVersion: v1
clusters:
- cluster:
    server: <server-url>
    disable-compression: true
  name: my-cluster
```

---

## Data Plane Scaling

### Use Automatic Node Autoscaling

**Karpenter** (recommended) provisions instances directly from EC2 based on workload requirements -- no pre-configured node groups needed. It avoids the 450-node-per-group quota and offers better instance diversity.

**Managed Node Groups + Cluster Autoscaler** is the alternative when you need ASG-based management or features not yet supported by Karpenter.

**See also:** [Autoscaling Reference](autoscaling.md) | [Karpenter Reference](karpenter.md)

### Use Diverse EC2 Instance Types

Each region has limited capacity per instance type. Restricting to a single type can cause "insufficient capacity" errors at scale. Let Karpenter choose from a broad set:

```yaml
spec:
  template:
    spec:
      requirements:
      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["c", "m", "r"]   # Multiple families
      - key: karpenter.k8s.aws/instance-generation
        operator: Gt
        values: ["5"]              # Current gen
```

For Cluster Autoscaler, create multiple node groups with similarly-sized instances. Use [ec2-instance-selector](https://github.com/aws/amazon-ec2-instance-selector) to find compatible types.

### Prefer Larger Nodes

Fewer, larger nodes reduce control plane load (fewer kubelets, fewer DaemonSet pods). A 4xlarge node has a much higher percentage of usable space than a 2xlarge because system overhead (DaemonSets, kubelet reserves) is proportionally smaller.

However, don't go to extremes -- very large nodes create availability risk (1 node failure = large blast radius) and can cause issues with dynamic runtimes spawning excessive OS threads due to CGROUPS exposing total vCPU count.

**Recommended range:** 4xlarge to 12xlarge for most workloads. Split workloads with different churn rates into different node groups/pools (e.g., small batch jobs on 4xlarge, large stateful apps on 12xlarge).

### Use Consistent Node Sizes

A workload requesting 500m CPU performs differently on a 4-core instance vs a 16-core instance. Avoid burstable T-series for production workloads. Use Karpenter labels or node selectors to target specific instance sizes:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        karpenter.k8s.aws/instance-size: 8xlarge
```

### Automate AMI Updates

Keep worker nodes up to date with the latest EKS-optimized AMIs:

- **Karpenter** (v1) selects AMIs via `amiSelectorTerms` on the EC2NodeClass -- it does not auto-track the latest AMI unless you use the `@latest` alias, which is discouraged in production (pin a specific AMI/alias instead)
- **MNG** requires updating the ASG launch template for patch releases; minor versions are available as managed upgrades
- Use Bottlerocket for automatic, minimal-downtime updates

---

## Cluster Services Scaling

Cluster services (kube-system namespace, DaemonSets) support your workloads and are critical during outages. Run them on **dedicated compute** (separate node group or Fargate) so workload scaling doesn't impact them.

### CoreDNS

CoreDNS is often the first bottleneck in scaling clusters. Two levers: reduce queries and increase replicas.

**Reduce queries -- lower ndots:**

By default, ndots=5 means a request to `api.example.com` (2 dots) triggers searches through multiple `.cluster.local` suffixes before going external. Set ndots=2 for workloads that primarily call external services:

```yaml
spec:
  dnsConfig:
    options:
      - name: ndots
        value: "2"
      - name: edns0
```

Or fully qualify domain names with a trailing dot: `api.example.com.`

**Scale horizontally:**

| Option | How It Works | Trade-off |
|--------|-------------|-----------|
| **CoreDNS add-on autoscaling** | 1 replica per 256 cores or 16 nodes | Recommended for EKS add-on |
| **Cluster proportional autoscaler** | Scales based on node/core count | For self-managed CoreDNS |
| **NodeLocal DNSCache** | DaemonSet -- one instance per node | Higher resource usage, best reliability |

**Set lameduck duration to 30 seconds** in CoreDNS configuration. This keeps CoreDNS responding to in-flight requests during shutdown, giving nodes time to update iptables rules before the pod terminates. Without this, DNS lookup failures occur during scale-down.

Use `/ready` instead of `/health` for the CoreDNS readiness probe to ensure pods are fully prepared before receiving traffic.

### Metrics Server

The Metrics Server stores collected data in memory. As the cluster grows, it needs more resources. Scale vertically using VPA or the Addon Resizer (scales proportionally with worker node count). Horizontal scaling adds HA but does not help with metrics volume -- only vertical scaling does.

### Logging & Monitoring Agents

Agents that query the API server for metadata enrichment can strain the control plane at scale. For FluentBit:

- Enable `Use_Kubelet` to fetch metadata from the local kubelet instead of the API server
- Set `Kube_Meta_Cache_TTL` to 60+ seconds to reduce repeated calls

If full metadata enrichment isn't needed, consider disabling API server integrations entirely or implementing sampling closer to the agent to reduce request volume.

---

## Workload Scaling

### Use IPv6

IPv6 avoids IP address exhaustion -- the most common scaling wall for pods and nodes. Pods get addresses faster with fewer ENI attachments per node. Enable IPv6 **before** creating your cluster (can't be added later).

IPv4 prefix mode offers similar per-node performance benefits if IPv6 isn't feasible.

### Limit Services per Namespace

| Limit | Recommended | Maximum |
|-------|-------------|---------|
| Services per namespace | 500 | 5,000 |
| Services per cluster | -- | 10,000 |

kube-proxy's iptables rules grow with total services, adding latency and CPU overhead on every node. Keeping namespaces under 500 services avoids performance degradation and naming collisions.

Use separate EKS clusters for different application environments (dev, test, prod) instead of namespaces.

### Understand ELB Quotas

| ELB Type | Default Target Quota | Per-AZ Limit |
|----------|---------------------|--------------|
| ALB | 1,000 targets | -- |
| NLB | 3,000 targets | 500 per AZ (500 per LB total with cross-zone load balancing enabled) |

If a service exceeds these targets, split across multiple LBs or use an in-cluster ingress controller. Use Route 53 (weighted DNS), Global Accelerator, or CloudFront to present multiple LBs as a single endpoint.

### Use EndpointSlices

EndpointSlices reduce API server load compared to Endpoints for large, frequently-scaling services. They include topology information for features like topology-aware routing.

Verify your controllers use them -- for older AWS Load Balancer Controller versions, enable `--enable-endpoint-slices`; it is on by default since LBC v2.7+ (and in v3), so no action is needed on current versions.

### Reduce Control Plane Watches

- Set `automountServiceAccountToken: false` for pods that don't need Kubernetes API access
- Mark static secrets as [immutable](https://kubernetes.io/docs/concepts/configuration/secret/#secret-immutable) -- the kubelet skips watches for immutable secrets
- Use external secret stores (Secrets Store CSI, External Secrets Operator) to reduce secrets stored in etcd

---

## Node & Workload Efficiency

Efficient workload sizing reduces cost and increases scale simultaneously.

### The "Sweet Spot" Concept

Every application has a saturation point where adding traffic degrades performance. Scale the application **before** it reaches saturation -- this is the "sweet spot." Test each application to find its sweet spot using application-level metrics (request latency, queue depth), not just CPU utilization.

### Why CPU Utilization Is Misleading

The Kubernetes scheduler uses the concept of CPU cores for scheduling. But once pods are placed, Linux's Completely Fair Scheduler (CFS) uses a share-based system where **only busy containers count**. A pod requesting 1 core can use all 4 cores on a node if nothing else is busy.

This means:
- Performance in dev (low contention) won't match production (high contention)
- HPA based on CPU utilization may under- or over-scale because CPU doesn't correlate with saturation for apps that offload work to databases, caches, or other services

For complex applications, scale on custom metrics (requests/second, p99 latency) rather than CPU.

### Avoid Pod Sprawl

Under-provisioned CPU requests combined with default 50% HPA threshold creates exponential pod multiplication:

| Scenario | Actual Need | Result |
|----------|------------|--------|
| Sweet spot = 2 vCPU, request = 2 vCPU | 1 pod | 1 pod |
| Sweet spot = 2 vCPU, request = 0.5 vCPU | 1 pod | 4 pods |
| + HPA at 50% CPU threshold | 1 pod | 8 pods |
| x 10 deployments | 10 pods | 80 pods |

Right-size the request to reflect the actual sweet spot, then set HPA thresholds accordingly.

### Setting Requests Wisely

Don't set requests exactly at the sweet spot -- that wastes capacity when pods aren't at peak. Instead, mix workloads with different profiles on the same nodes:

- Pair bursty CPU workloads with memory-heavy, low-CPU workloads
- This allows bursty pods to use spare CPU without over-taxing the node

For I/O-bound workloads on large nodes, consider [CPU pinning](https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/#static-policy) to avoid CFS complexity and get predictable performance.

---

## Large Cluster Guidance

### EKS Scalability Limits

| Dimension | Default / Practical Limit | Notes |
|-----------|--------------------------|-------|
| Nodes per cluster | Up to 100,000 (by arrangement) | Plan carefully beyond 1,000 |
| Pods per node | ~110 default, ENI-based max ~250 | Depends on instance type + CNI mode |
| Services per cluster | 10,000 | kube-proxy iptables limit ~5K, use IPVS |
| Pods per cluster | ~150,000 | Practical limit based on etcd/API server |
| ConfigMaps/Secrets | 10,000 each | Monitor etcd size |
| Namespaces | 10,000 | Performance degrades beyond ~5K |

### Switch to IPVS at 500+ Services

iptables rules are O(n) for n services -- IPVS uses hash tables for O(1) lookup:

```bash
aws eks update-addon --cluster-name $CLUSTER_NAME --addon-name kube-proxy \
  --configuration-values '{"ipvs": {"scheduler": "rr"}, "mode": "ipvs"}' \
  --resolve-conflicts OVERWRITE
```

**Prerequisites:**
- Install `ipvsadm` package on worker nodes
- Load IPVS kernel modules (`ip_vs`, `ip_vs_rr`, `ip_vs_wrr`, `ip_vs_lc`, etc.)
- Add modules to `/etc/modules-load.d/ipvs.conf` to persist across reboots

**Validate:** `sudo ipvsadm -L` should show entries for the Kubernetes API Server and CoreDNS services.

Available IPVS schedulers: `rr` (Round Robin), `lc` (Least Connections), `wrr` (Weighted Round Robin), and others. Round Robin and Least Connections are the most common choices.

### Shard Cluster Autoscaler at 1,000+ Nodes

The Cluster Autoscaler has been tested to 1,000 nodes. Beyond that, run multiple sharded instances, each managing a subset of node groups:

```yaml
# ClusterAutoscaler-1: manages groups 1-4
autoscalingGroups:
- name: eks-data_m1-...
  maxSize: 450
  minSize: 2
# ... (4 groups)

# ClusterAutoscaler-2: manages groups 5-8
autoscalingGroups:
- name: eks-data_m5-...
  maxSize: 450
  minSize: 2
# ... (4 groups)
```

Karpenter does not have this limitation -- it handles large clusters without sharding.

### Large Cluster Checklist

| Concern | Threshold | Action |
|---------|-----------|--------|
| Service routing | 500+ services | Switch to IPVS mode |
| DNS | Any large cluster | NodeLocal DNSCache, lower ndots, set lameduck=30s |
| API server load | 429 errors | Audit controllers, use watches, review APF config |
| Control plane scaling | >10% burst | Rate-limit scaling, use custom HPA metrics |
| Monitoring | Large cluster | Use Amazon Managed Prometheus (not in-cluster) |
| etcd | Growing DB size | Monitor `apiserver_storage_size_bytes`, enable event TTL |
| Node autoscaling | 1,000+ nodes | Use Karpenter or shard CAS |
| kubectl | Automation/scripts | Enable cache-dir, disable compression |
| Node efficiency | Any scale | Prefer 4xlarge-12xlarge, match churn to node size |
| Pod networking | IP exhaustion | Use prefix delegation; IPv6 (dual-stack) for larger address space |

**For clusters beyond 1,000 nodes or 50,000 pods**, AWS recommends engaging your support team or TAM for specialist guidance. EKS can support up to 100,000 nodes with appropriate planning.

---

**Sources:**
- [AWS EKS Best Practices Guide -- Scalability](https://docs.aws.amazon.com/eks/latest/best-practices/scalability.html)
- [Kubernetes Scalability Thresholds](https://github.com/kubernetes/community/blob/master/sig-scalability/configs-and-limits/thresholds.md)
