# Autoscaling

## Purpose
Assess cluster-level autoscaling (nodes) and workload-level autoscaling (pods), plus AZ resilience.

## Checks to Execute

### 7.1 — Cluster Autoscaling Strategy

**What to check:**
- Karpenter NodePools and EC2NodeClasses
- Cluster Autoscaler deployment in kube-system
- EKS Auto Mode (cluster computeConfig)
- Node group scaling config (min/max/desired)
- Spot vs On-Demand nodes
- Currently pending pods

**How to check:**
1. List resources `nodepools.karpenter.sh` → check limits and consolidation policy. If 404/NotFound (CRD not installed) → Karpenter is not deployed, proceed to check for Cluster Autoscaler or Auto Mode. If 403/Forbidden → mark Karpenter status UNKNOWN.
2. List Deployments in kube-system → check for `cluster-autoscaler`
3. Describe cluster → `computeConfig` for Auto Mode
4. List node groups → describe each for scalingConfig and capacityType
5. List nodes → check labels for capacity type (`karpenter.sh/capacity-type` or `eks.amazonaws.com/capacityType`)
6. List pods with field selector `status.phase=Pending`

**Rating:**
- 🟢 GREEN: Karpenter or EKS Auto Mode with consolidation enabled (AWS-preferred path)
- 🟡 AMBER: Cluster Autoscaler present (legacy — consider migration to Karpenter), or Karpenter without consolidation
- 🔴 RED: No cluster autoscaling — manual node management
- ⬜ UNKNOWN: Cannot determine scale-up latency without testing

---

### 7.2 — Horizontal Pod Autoscaler (HPA)

**What to check:**
- HPAs across all namespaces (targets, min/max, current replicas)
- Multi-replica deployments without HPA
- HPAs with minReplicas=1 (single point of failure)
- KEDA ScaledObjects
- VPA resources

**How to check:**
1. List HPAs across all namespaces → check minReplicas, maxReplicas, current metrics
2. List Deployments with replicas > 1 → cross-reference with HPA targets
3. List HPAs where minReplicas == 1 (single point of failure for production workloads; acceptable for dev/staging)
4. List ScaledObjects (KEDA CRD). If 404/NotFound → KEDA not installed, skip. If 403/Forbidden → mark UNKNOWN.
5. List VPA resources. If 404/NotFound → VPA not installed, skip. If 403/Forbidden → mark UNKNOWN.

**Rating:**
- 🟢 GREEN: HPAs on stateless production workloads, min >= 2, tested under load
- 🟡 AMBER: HPAs exist but min=1, or some workloads missing HPA
- 🔴 RED: No HPAs — all workloads at fixed replica count
- ⬜ UNKNOWN: Cannot determine if HPAs have been load-tested

---

### 7.3 — Pod Topology Spread & AZ Resilience

**What to check:**
- Node distribution across AZs
- Deployments with topology spread constraints
- Deployments with pod anti-affinity
- Multi-replica deployments with neither (vulnerable to AZ failure)

**How to check:**
1. List nodes → group by label `topology.kubernetes.io/zone`
2. List Deployments → check `spec.template.spec.topologySpreadConstraints`
3. List Deployments → check `spec.template.spec.affinity.podAntiAffinity`
4. List multi-replica Deployments with neither topology spread nor anti-affinity

**Rating:**
- 🟢 GREEN: Nodes in 3 AZs, topology spread on production deployments
- 🟡 AMBER: Nodes in multiple AZs but no topology spread constraints
- 🔴 RED: Single-AZ deployment, or multi-replica services with no AZ spread
- ⬜ UNKNOWN: Cannot verify actual pod distribution without checking pod-to-node mapping

**Key talking point:** Having nodes in 3 AZs doesn't mean pods are spread. Without topology spread constraints, the scheduler may pack all pods into one AZ.
