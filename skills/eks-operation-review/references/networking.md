# Networking

## Purpose
Assess VPC CNI configuration, IP capacity, DNS health, and network segmentation.

## Checks to Execute

### 6.1 — VPC and Subnet IP Capacity

**What to check:**
- Subnets used by the cluster and available IP count
- VPC CNI configuration: prefix delegation, custom networking, WARM_IP_TARGET
- Current pod count vs IP capacity
- VPC CNI add-on version

**How to check:**
1. Describe cluster → get subnet IDs from `resourcesVpcConfig.subnetIds`
2. Get VPC config for the cluster (available IPs per subnet)
3. List pods (Running) → count total
4. List nodes → count total
5. Describe addon `vpc-cni` → check version and configuration
6. Check DaemonSet `aws-node` in kube-system → inspect env vars for `ENABLE_PREFIX_DELEGATION`, `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG`
7. List ENIConfig resources (custom networking indicator)

**Rating:**
- 🟢 GREEN: >30% IP headroom, prefix delegation or custom networking enabled
- 🟡 AMBER: Adequate IPs now but no prefix delegation and cluster is growing
- 🔴 RED: <15% IPs available, or past IP exhaustion incidents
- ⬜ UNKNOWN: Cannot determine subnet sharing with other workloads

**Key talking point:** Prefix delegation assigns a /28 (16 IPs) per ENI slot instead of 1 IP — dramatically increases pod density.

---

### 6.2 — CoreDNS Health and Scaling

**What to check:**
- CoreDNS deployment: replica count, resource requests, pod placement
- Node count (to assess CoreDNS ratio — ~1 replica per 8 nodes, minimum 2)
- NodeLocal DNSCache DaemonSet
- CoreDNS HPA
- CoreDNS topology spread constraints

**How to check:**
1. Read Deployment `coredns` in kube-system → replicas, resources, topologySpreadConstraints
2. List pods with label `k8s-app=kube-dns` → check node placement
3. Count nodes
4. List DaemonSets → check for `node-local-dns` or `nodelocaldns` (recommended for clusters with 50+ nodes)
5. List HPAs in kube-system with label `k8s-app=kube-dns` (if HPA present, CoreDNS can auto-scale so fewer static replicas is acceptable)

**Rating:**
- 🟢 GREEN: CoreDNS scaled to cluster size (~1 replica per 8 nodes, min 2), spread across AZs, NodeLocal DNSCache on clusters with 50+ nodes
- 🟡 AMBER: Adequate replicas but no topology spread, or no NodeLocal DNSCache on 50+ node clusters, or no HPA
- 🔴 RED: CoreDNS under-provisioned (2 replicas for 50+ nodes with no HPA), or past DNS incidents
- ⬜ UNKNOWN: Cannot determine if DNS issues have occurred historically

---

### 6.3 — Network Policies & Segmentation

**What to check:**
- VPC CNI Network Policy Controller enabled (`ENABLE_NETWORK_POLICY` env var on aws-node)
- Calico pods (alternative enforcement engine)
- NetworkPolicy resources across namespaces
- Default-deny policies (podSelector: {})
- Namespaces without any NetworkPolicy

**How to check:**
1. Read DaemonSet `aws-node` in kube-system → check env var `ENABLE_NETWORK_POLICY`
2. List pods with label `k8s-app=calico-node`
3. List NetworkPolicies across all namespaces
4. Inspect NetworkPolicies for default-deny (empty podSelector)
5. Compare namespaces with policies vs namespaces without

**Rating:**
- 🟢 GREEN: Enforcement enabled (VPC CNI controller or Calico), default-deny in production namespaces
- 🟡 AMBER: Policies defined but enforcement not verified, or policies in some namespaces only
- 🔴 RED: No network policies, or policies defined but enforcement not enabled (false security)
- ⬜ UNKNOWN: Cannot determine if policies have been tested

**Critical gotcha:** VPC CNI requires explicitly enabling the Network Policy Controller. Without it, NetworkPolicy resources are just YAML that does nothing.
