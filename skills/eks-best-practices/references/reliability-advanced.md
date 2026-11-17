# Reliability & Resiliency — Advanced / Operational

> **Part of:** [eks-best-practices](../SKILL.md)
> **Purpose:** Disaster recovery, deployment strategies, cluster-level enforcement, zonal shift, large-cluster guidance, and chaos engineering for Amazon EKS.

---

## Table of Contents

1. [Disaster Recovery](#disaster-recovery)
2. [EKS Zonal Shift (ARC Integration)](#eks-zonal-shift-arc-integration)
3. [Enforcing Default Topology Spread via Admission Controller](#enforcing-default-topology-spread-via-admission-controller)
4. [Velero Backup Tiers](#velero-backup-tiers)
5. [Recovery Scenarios](#recovery-scenarios)
6. [Deployment Strategies](#deployment-strategies)
7. [Large Cluster Guidance](#large-cluster-guidance)
8. [Chaos Engineering with AWS FIS](#chaos-engineering-with-aws-fis)

---

## Disaster Recovery

### Backup Strategy with Velero

```bash
# Install Velero with AWS plugin
velero install \
  --provider aws \
  --bucket my-velero-bucket \
  --backup-location-config region=us-east-1 \
  --snapshot-location-config region=us-east-1 \
  --plugins velero/velero-plugin-for-aws:v1.8.0  # illustrative pin — check the current release (e.g. v1.14.2) and match it to your Velero version

# Schedule daily backups
velero schedule create daily-backup \
  --schedule "0 2 * * *" \
  --ttl 720h \
  --include-namespaces production,staging
```

### DR Patterns

| Pattern | RPO | RTO | Cost |
|---------|-----|-----|------|
| **Backup/Restore** | Hours | Hours | Low |
| **Pilot Light** | Minutes | 30-60 min | Medium |
| **Warm Standby** | Seconds | Minutes | High |
| **Active-Active** | Near-zero | Near-zero | Highest |

**EKS-specific DR considerations:**
- Back up cluster configuration (add-ons, RBAC, CRDs) separately from workloads
- Use GitOps (ArgoCD/Flux) for declarative cluster state — simplifies recovery
- Test restore procedures regularly
- Cross-region ECR replication for image availability

---

## EKS Zonal Shift (ARC Integration)

Amazon Application Recovery Controller (ARC) zonal shift allows you to shift away from an impaired Availability Zone for EKS workloads. With the EKS-integrated ARC zonal shift enabled on the cluster, a shift does far more than reroute load balancer traffic — it acts across both the data plane and Kubernetes' own service routing:

- **Nodes in the impaired AZ are cordoned** so no new pods schedule there.
- **The EndpointSlice controller strips pod endpoints in the impaired AZ**, so east-west (in-cluster `ClusterIP`) traffic is shifted away too — not just external ALB/NLB traffic.
- **Managed Node Group AZRebalance is suspended** so the ASG does not fight the shift by rebalancing capacity back into the impaired AZ.
- **EKS Auto Mode stops provisioning** new capacity in the impaired AZ for the duration of the shift.

| Aspect | Detail |
|---|---|
| **What it does** | Cordons impaired-AZ nodes, strips impaired-AZ pod endpoints (ClusterIP + ALB/NLB), suspends MNG AZRebalance, and stops Auto Mode provisioning in that AZ |
| **Trigger** | Manual via console/API, or automated via zonal autoshift |
| **Duration** | Up to 72 hours per shift, extendable |
| **EKS impact** | Impaired-AZ pods are removed from Service endpoints (external and in-cluster); nodes are cordoned so nothing new lands there |
| **Pod scheduling** | Impaired-AZ nodes are cordoned — new pods do not schedule into the AZ for the shift's duration |
| **Prerequisites** | EKS-integrated ARC zonal shift enabled, multi-AZ deployment, topology spread constraints, sufficient capacity in remaining AZs |

**Karpenter and Auto Mode integration:** Karpenter (as of 2026-05) and EKS Auto Mode (as of 2026-07) integrate with ARC zonal shift, so provisioning honors an active shift and stops adding capacity in the impaired AZ. This integration is what makes the older "traffic-only" characterization of zonal shift stale — with it enabled, the shift reaches scheduling and in-cluster routing, not just the load balancer.

**When to use zonal shift:**
- AZ-level impairment (network, storage, compute degradation)
- Elevated error rates from a specific AZ
- Proactive shift during planned AZ maintenance

**Limitations:**
- Does not evict or reschedule already-running pods — it cordons nodes and removes endpoints, but existing pods in the impaired AZ keep running until they terminate on their own
- Requires sufficient capacity in remaining AZs to handle full load
- Requires the EKS-integrated ARC zonal shift to be enabled on the cluster; without it, only the load-balancer traffic path shifts

DO:
- Ensure topology spread constraints distribute pods across all AZs before relying on zonal shift
- Size capacity for N-1 AZ operation (if 3 AZs, each AZ should handle 50% of peak load)
- Test zonal shift in non-production before relying on it in production

DON'T:
- Use zonal shift as a substitute for proper multi-AZ pod distribution
- Assume already-running pods will be evicted or moved — the shift cordons nodes and strips endpoints, but does not reschedule pods that are already running

---

## Enforcing Default Topology Spread via Admission Controller

The default `KubeSchedulerConfiguration` cannot be changed in Amazon EKS. The built-in defaults use high `maxSkew` values (3 for hostname, 5 for zone) which are too permissive for small deployments. To enforce stricter topology spread, use a mutating admission controller.

**Approach with Kyverno:** Create a mutating policy that injects `topologySpreadConstraints` into Deployments that don't already specify them. The policy matches Deployments with `replicas >= 2` and adds zone-based and node-based spread constraints with `maxSkew: 1`.

**Approach with Gatekeeper:** Create a `ConstraintTemplate` that validates Deployments have `topologySpreadConstraints` defined, and rejects those without. Optionally scope to namespaces with a specific label (e.g., `ha=true`).

| Approach | Type | Behavior |
|---|---|---|
| Kyverno mutate | Inject defaults | Adds constraints if missing; doesn't override explicit ones |
| Gatekeeper validate | Reject non-compliant | Blocks Deployments without constraints; teams must add their own |
| Kyverno validate + mutate | Both | Injects defaults AND validates minimum requirements |

**Recommendation:** Use Kyverno mutate to inject sensible defaults, so teams get topology spread automatically without needing to know the details. Add a validate policy for critical namespaces that require explicit constraints.

---

## Velero Backup Tiers

| Tier | Scope | Frequency | Retention | What to Back Up |
|---|---|---|---|---|
| **Production** | K8s resources | Hourly | 30 days | Namespaces, Deployments, Services, ConfigMaps, Secrets, CRDs |
| **Production** | Persistent volumes | Every 4 hours | 30 days | EBS snapshots for stateful workloads |
| **Non-production** | K8s resources + PVs | Daily | 7 days | Same as production but less frequent |

**What NOT to back up:**
- Resources managed by GitOps (ArgoCD/Flux will reconcile from Git)
- Node-level state (Karpenter will reprovision)
- Cached data (Redis, Memcached — ephemeral by design)

> **Ephemeral ≠ unsized.** "Don't back up the cache" is a *backup-scope* decision and it is correct — a cache is reconstructible, so it does not belong in your recovery set. It is **not** a statement that an in-cluster cache can be left unsized. An in-cluster cache whose memory ceiling is not sized for real peak demand is a reliability risk regardless of backup policy: it can OOM under load and take dependent services down with it. Backup scope and capacity sizing are orthogonal — see [reliability-core.md — In-Cluster Stateful Cache: Sizing & Blast Radius](reliability-core.md#in-cluster-stateful-cache-sizing--blast-radius).

**What to ALWAYS back up:**
- Custom resources and CRDs not in Git
- Persistent volume data (databases, file storage)
- Secrets not managed by external secrets store
- Namespace-level RBAC and resource quotas (if not in Git)

DO:
- Encrypt backups with KMS CMK
- Store backups in a separate AWS account or region
- Test restore quarterly in an isolated environment
- Use Velero schedules (not manual backups) for consistency

DON'T:
- Back up everything — exclude GitOps-managed resources to avoid conflicts on restore
- Skip PV backups for stateful workloads
- Store backups in the same account as the cluster (blast radius)

---

## Recovery Scenarios

| Scenario | Impact | Recovery Mechanism | Estimated Recovery Time |
|---|---|---|---|
| **Single pod failure** | One pod down | Kubernetes self-healing (ReplicaSet recreates pod) | 10-30 seconds |
| **Node failure** | All pods on node down | Karpenter provisions replacement node, pods rescheduled | 1-3 minutes |
| **AZ impairment** | Pods in one AZ degraded | Zonal shift (traffic) + topology spread (pods already distributed) | 1-5 minutes (traffic shift) |
| **Add-on failure** | Cluster functionality degraded | Helm rollback or GitOps revert | 5-15 minutes |
| **Control plane issue** | API server unavailable | AWS-managed recovery (automatic) | 5-15 minutes (AWS SLA) |
| **Full cluster loss** | Everything down | Velero restore + GitOps reconciliation + DNS switch | 1-4 hours |
| **Region failure** | All AZs down | Multi-region failover (if configured) | 15-60 minutes |

### Full Cluster Recovery Steps (High Level)

1. Provision new EKS cluster (Terraform apply)
2. Install core add-ons (VPC CNI, CoreDNS, Karpenter)
3. Restore Velero backup (K8s resources + PV snapshots)
4. Reconcile GitOps repository (ArgoCD sync)
5. Validate workloads are running and healthy
6. Switch DNS/traffic to new cluster
7. Verify end-to-end functionality

---

## Deployment Strategies

### Rolling Updates (Default)

Control update behavior with `maxUnavailable` and `maxSurge`:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0     # No downtime — new pods created before old ones removed
    maxSurge: 1           # One extra pod during rollout
```

The default `maxUnavailable: 25%` means if you have 100 pods, only 75 may be active during rollout. If your app needs 80+, set `maxUnavailable: 20%` or lower.

Always use `kubectl rollout undo deployment <name>` for quick rollbacks.

### Blue/Green Deployments

Create a new Deployment identical to the current version, verify pods are healthy, then switch the Service `selector` to point to the new Deployment. Automate with Flux, Jenkins, Spinnaker, or AWS Load Balancer Controller.

### Canary Deployments

Deploy the new version with fewer replicas alongside the existing Deployment, divert a small percentage of traffic, and progressively increase if metrics are healthy. Use [Flagger](https://github.com/fluxcd/flagger) with Istio for automated canary progression. (AWS App Mesh reaches end of support on 2026-09-30 — do not adopt it for new canary/mesh work; prefer Istio or Cilium-based service mesh instead.)

---

## Large Cluster Guidance

For clusters approaching scale limits:

| Issue | Threshold | Solution |
|-------|-----------|----------|
| **kube-proxy latency** | >1000 Services | Switch to `ipvs` mode |
| **EC2 API throttling** | Frequent node scaling | Configure CNI to cache IPs, use larger instance types |
| **etcd size** | Approaching 8GB | Monitor `apiserver_storage_size_bytes`, reduce CRD churn |
| **DNS pressure** | >500 nodes | Deploy NodeLocal DNSCache, enable CoreDNS auto-scaling |

---

## Chaos Engineering with AWS FIS

AWS Fault Injection Service (FIS) provides managed chaos engineering experiments for EKS. FIS integrates with EKS to inject faults at the pod, node, and AZ level, validating that your resilience mechanisms (PDBs, topology spread, autoscaling) work as expected.

### Common EKS Experiments

| Experiment | What It Tests | Target |
|---|---|---|
| **Pod delete** | Self-healing, PDB behavior | Specific pods by label |
| **Node terminate** | Node replacement, pod rescheduling | EC2 instances in node group |
| **AZ failure** | Multi-AZ resilience, zonal shift | Subnet/AZ disruption |
| **CPU stress** | HPA scaling, resource limits | Pods or nodes |
| **Network disruption** | Timeout handling, circuit breakers | Pod network |
| **DNS failure** | DNS caching, fallback behavior | CoreDNS disruption |

### Experiment Progression

| Phase | Experiments | Scope |
|---|---|---|
| **1. Start small** | Delete single pod, verify PDB | One namespace, non-production |
| **2. Node level** | Terminate one node, verify rescheduling | One node group |
| **3. Multi-pod** | Delete multiple pods simultaneously | Multiple namespaces |
| **4. AZ level** | Simulate AZ failure, verify topology spread | One AZ |
| **5. Steady state** | Run experiments continuously in production | Automated, with guardrails |

DO:
- Start with non-production environments
- Define steady-state hypothesis before each experiment (what "healthy" looks like)
- Set stop conditions (abort if error rate exceeds threshold)
- Run experiments during business hours with the team available

DON'T:
- Run AZ-level experiments without verifying multi-AZ pod distribution first
- Skip PDB validation before running node-terminate experiments
- Run chaos experiments without monitoring and alerting in place

---

Prerequisite reading: [reliability-core.md](reliability-core.md).

---

**Sources:**
- [AWS EKS Best Practices Guide — Reliability](https://docs.aws.amazon.com/eks/latest/best-practices/reliability.html)
- [AWS EKS Best Practices Guide — High Availability](https://aws.github.io/aws-eks-best-practices/reliability/docs/)
- [AWS Prescriptive Guidance — HA and Resiliency for EKS](https://docs.aws.amazon.com/prescriptive-guidance/latest/ha-resiliency-amazon-eks-apps/introduction.html)
- [AWS FIS for EKS](https://docs.aws.amazon.com/fis/latest/userguide/fis-actions-reference.html)
- [EKS Zonal Shift (ARC integration)](https://docs.aws.amazon.com/eks/latest/userguide/zone-shift.html)
