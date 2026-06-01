# Baseline Defaults

## Table of Contents

- [Cluster](#cluster)
- [Compute](#compute)
- [Networking](#networking)
- [Namespace Security](#namespace-security)
- [Addon Resilience](#addon-resilience)
- [IAM](#iam)
- [Observability](#observability)
- [Upgrade Path](#upgrade-path)
- [Cost Optimization](#cost-optimization)

Apply these to ALL generated projects regardless of environment (production, staging, development) unless explicitly overridden. Sourced from validated deployments and EKS best practices.

---

## Cluster

- **Authentication mode**: `API_AND_CONFIG_MAP` (not legacy `CONFIG_MAP`)
- **Endpoint access**: Private-only for production, private+public for dev/staging
- **Encryption**: KMS envelope encryption for etcd secrets (mandatory for production)
- **Logging**: Enable all 5 log types: api, audit, authenticator, controllerManager, scheduler
- **Log retention**: Audit 365 days, control plane 90 days, application 30 days
- **Access entries**: Use EKS access entries with scoped AWS-managed policies (`AmazonEKSClusterAdminPolicy`, `AmazonEKSAdminPolicy`, `AmazonEKSEditPolicy`, `AmazonEKSViewPolicy`)

## Compute

### Node Groups (MNG)

- **EBS volume**: gp3, encrypted, 100Gi, iops 3000, throughput 125 (never gp2)
- **Graviton**: Suggest arm64 (m7g, c7g, r7g) when workloads support it -- 20-40% savings. Default to x86 (m6i, m7i) when uncertain
- **Spot**: Recommend for dev/staging. Never for production stateful workloads
- **Multiple instance types**: Always 3+ per node group for AZ availability
- **IMDSv2**: Enforce hop limit 1 in launch template -- prevents pods from accessing node IMDS credentials

```hcl
# Launch template metadata options
metadata_options = {
  http_endpoint               = "enabled"
  http_tokens                 = "required"
  http_put_response_hop_limit = 1
}

# EBS block device
block_device_mappings = {
  xvda = {
    device_name = "/dev/xvda"
    ebs = {
      volume_size = 100
      volume_type = "gp3"
      iops        = 3000
      throughput  = 125
      encrypted   = true
    }
  }
}
```

### Node IAM Role

Only attach these policies -- never application permissions:
- `AmazonEKSWorkerNodePolicy`
- `AmazonEKS_CNI_Policy` (move to IRSA/Pod Identity when possible)
- `AmazonEC2ContainerRegistryReadOnly`
- `AmazonSSMManagedInstanceCore` (for SSM access, replaces SSH)

### Karpenter (When Selected)

**Architecture:** Use the dedicated `terraform-aws-modules/eks/aws//modules/karpenter` submodule (NOT eks-blueprints-addons). This submodule creates the controller IAM role with Pod Identity and the node IAM role. In Pattern 1, deploy the Helm chart via `helm_release`. In Pattern 2, deploy via ArgoCD Application (validated).

**Prerequisites:** The account must have the `AWSServiceRoleForEC2Spot` service-linked role for Spot instances. Create with `aws iam create-service-linked-role --aws-service-name spot.amazonaws.com` or via Terraform `aws_iam_service_linked_role`.

**Key components:**
1. `module "karpenter"` -- controller IAM role (Pod Identity) + node IAM role
2. `helm_release "karpenter"` -- Karpenter controller (chart: `oci://public.ecr.aws/karpenter/karpenter`)
3. `kubectl_manifest` -- NodePool + EC2NodeClass CRDs
4. `aws_ec2_tag` -- discovery tags on private subnets and cluster primary security group

**Discovery tags:** Karpenter finds subnets and security groups via `karpenter.sh/discovery: <cluster-name>` tags. Tag ALL private subnets and the cluster primary security group.

NodePool defaults:

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
spec:
  template:
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      requirements:
      - key: kubernetes.io/arch
        operator: In
        values: ["amd64", "arm64"]       # Multi-arch for cost savings
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["on-demand", "spot"]     # Karpenter handles fallback
      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["c", "m", "r"]           # Diverse instance families
      - key: karpenter.k8s.aws/instance-generation
        operator: Gt
        values: ["5"]                     # Gen 6+ only
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m
    budgets:
    - nodes: "10%"                        # Max 10% replaced at once
  limits:
    cpu: "1000"
    memory: 2000Gi
  weight: 50
```

EC2NodeClass defaults:

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
spec:
  role: <CLUSTER_NAME>-karpenter-node    # Must match node_iam_role_name in module
  amiSelectorTerms:
  - alias: al2023@latest
  subnetSelectorTerms:
  - tags:
      karpenter.sh/discovery: <CLUSTER_NAME>
  securityGroupSelectorTerms:
  - tags:
      karpenter.sh/discovery: <CLUSTER_NAME>
  blockDeviceMappings:
  - deviceName: /dev/xvda
    ebs:
      volumeSize: 100Gi
      volumeType: gp3
      encrypted: true
      iops: 3000
      throughput: 125
```

## Networking

### VPC CNI

```hcl
# vpc-cni addon configuration_values
configuration_values = jsonencode({
  env = {
    ENABLE_PREFIX_DELEGATION = "true"    # 4-16x more pods/node
    WARM_PREFIX_TARGET       = "1"
  }
  enableNetworkPolicy = "true"           # Native network policy (v1.14+)
})
```

| Setting | Default | When to Change |
|---------|---------|----------------|
| Prefix delegation | On | Disable only if subnet IPs are abundant and pod count <30/node |
| Network policy | On | Always on for production |
| Custom networking | Off | Enable for separate pod CIDR (IP-constrained VPCs) |

### Subnet Design

- **Private subnets**: Worker nodes, tagged `kubernetes.io/role/internal-elb = 1`
- **Public subnets**: ALB only (internet-facing), tagged `kubernetes.io/role/elb = 1`
- **Intra subnets**: EKS control plane ENIs (when available)
- **All subnets**: Tagged `kubernetes.io/cluster/<cluster-name> = shared`
- **NAT Gateway**: One per AZ for production (eliminates inter-AZ NAT traversal)

### kube-proxy

| Cluster Size | Mode | Why |
|-------------|------|-----|
| <500 services | iptables (default) | Simpler, well-tested |
| 500+ services | IPVS | O(1) vs O(n) lookup, better performance |

Set via kube-proxy ConfigMap: `mode: "ipvs"`, `ipvs.scheduler: "lc"`

### CoreDNS Tuning

- **ndots**: Set to `2` in pod dnsConfig (default 5 causes 4 extra lookups per external DNS query)
- **Proportional autoscaler**: `coresPerReplica: 256`, `nodesPerReplica: 16`, `min: 2`, `max: 20`
- **Lameduck duration**: 30s (critical for Karpenter -- delays shutdown for iptables propagation)
- **NodeLocal DNSCache**: Deploy for clusters >100 nodes (reduces CoreDNS load 80%+)

### Ingress

- **ALB target type**: `target-type: ip` (eliminates cross-AZ LB-to-pod charges)
- **SSL policy**: `ELBSecurityPolicy-TLS13-1-2-2021-06`
- **Health check alignment**: ALB health check path = readiness probe path, interval >= readiness probe period

## Namespace Security

### Pod Security Admission Labels

Apply to ALL generated namespaces (addon namespaces, tenant namespaces):

```yaml
metadata:
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
```

For hardened workloads, use `enforce: restricted`.

### Default-Deny NetworkPolicy

Generate for each namespace:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

Then add explicit allow rules for required traffic (DNS on port 53/UDP, HTTPS on 443/TCP).

### Resource Quotas (Tenants)

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-quota
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "50"
    persistentvolumeclaims: "10"
```

## Addon Resilience

### Replica Count and Topology

For production environments:

| Addon | Replicas | Topology Spread | PDB |
|-------|----------|-----------------|-----|
| LBC | 2 | AZ: DoNotSchedule | maxUnavailable: 1 |
| CoreDNS | 2+ (autoscaled) | AZ: DoNotSchedule | minAvailable: 50% |
| external-dns | 2 | AZ: DoNotSchedule | maxUnavailable: 1 |
| cert-manager | 2 | AZ: DoNotSchedule | maxUnavailable: 1 |
| external-secrets | 2 | AZ: DoNotSchedule | maxUnavailable: 1 |
| Kyverno | 3 | AZ: DoNotSchedule | minAvailable: 2 |
| Gatekeeper | 3 | AZ: DoNotSchedule | minAvailable: 2 |
| metrics-server | 2 | AZ: DoNotSchedule | maxUnavailable: 1 |

### Topology Spread Template

```yaml
topologySpreadConstraints:
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: DoNotSchedule
- maxSkew: 1
  topologyKey: kubernetes.io/hostname
  whenUnsatisfiable: ScheduleAnyway
```

### Graceful Shutdown

For addons behind ALB:
- `terminationGracePeriodSeconds: 60`
- `preStop: sleep 15` (allows kube-proxy and LB to deregister before SIGTERM)

### HPA Defaults (When Applicable)

- `minReplicas: 3` (production)
- `averageUtilization: 70` (30% headroom for bursts)
- `scaleUp.stabilizationWindowSeconds: 60`
- `scaleDown.stabilizationWindowSeconds: 300` (5 min cooldown, prevent flapping)
- Never run VPA and HPA on the same metric (VPA cpu + HPA cpu = conflict)

### Health Probes

| Probe | Purpose | Defaults |
|-------|---------|----------|
| Startup | Wait for slow init | `periodSeconds: 5`, `failureThreshold: 30` |
| Readiness | Traffic routing | `periodSeconds: 10`, `failureThreshold: 3` |
| Liveness | Deadlock detection | `periodSeconds: 15`, `failureThreshold: 3` |

**Liveness probes must NOT check external dependencies** -- if the DB goes down and liveness checks it, all pods restart, causing cascading failure.

### Resource Requests

- **Requests**: Always set for CPU and memory (scheduling guarantee)
- **Limits**: Always set memory (OOM protection). Usually omit CPU limits (avoid throttling)
- **Memory limit** = 1.5-2x memory requests

## IAM

| Approach | Use When |
|----------|----------|
| **Pod Identity** | EKS managed addons (EBS/EFS/FSx CSI, CloudWatch) and Karpenter -- default for all new workloads |
| **IRSA** | Helm-based addons via eks-blueprints-addons (LBC, External DNS, Velero, etc.) or Fargate workloads |

- Pod Identity is default. IRSA as fallback only
- Pod Identity associations for EKS managed addons: use **separate `aws_eks_pod_identity_association` resources** (not inline in addon config) for correct destroy ordering
- Node role: Only `AmazonEKSWorkerNodePolicy`, `AmazonEKS_CNI_Policy`, `AmazonEC2ContainerRegistryReadOnly`
- Access entries: Use scoped AWS-managed policies, not aws-auth ConfigMap

## Observability

### Container Insights

Enable via EKS addon: `amazon-cloudwatch-observability`

### Fluent Bit

- Log group: `/eks/<cluster-name>/application`
- Stream prefix: `pod-`
- Auto-create groups: true

### Alert Thresholds

| Metric | Threshold | Severity |
|--------|-----------|----------|
| Node CPU utilization | >80% sustained | Warning |
| Node memory utilization | >85% sustained | Warning |
| Pod memory utilization | >85% of limit | Warning |
| Pod container restarts | >3 in 5 min | Critical |
| Failed node count | >0 | Critical |

### GuardDuty

EKS Runtime Monitoring is auto-enabled at account level when GuardDuty is active. Not managed by Terraform. Key finding types: CryptocurrencyMining, PrivilegeEscalation, ReverseShell.

## Upgrade Path

Strict sequence:
```
1. Control Plane -> 2. EKS Managed Add-ons -> 3. Data Plane (nodes) -> 4. Custom Add-ons (Helm)
```

### Pre-Upgrade Checklist

1. Check EKS Cluster Insights: `aws eks list-insights --cluster-name <name>`
2. Scan deprecated APIs: Pluto or kube-no-trouble
3. Verify addon compatibility: `aws eks describe-addon-versions --kubernetes-version <target>`
4. Ensure PDBs configured (won't block node drains)
5. Back up via Velero or GitOps repo
6. Test in non-prod first

### Key API Removals

| Version | Removed |
|---------|---------|
| 1.25 | PodSecurityPolicy, batch/v1beta1 CronJob |
| 1.26 | flowcontrol.apiserver.k8s.io/v1beta1 |
| 1.27 | storage.k8s.io/v1beta1 CSIStorageCapacity |

### Version Support

- 14 months standard support
- +12 months extended support (additional fees)
- After: Auto-upgrade to oldest supported version

## Cost Optimization

| Action | Savings | When |
|--------|---------|------|
| Graviton (arm64) | 20-40% | Multi-arch workloads |
| Spot instances | 60-90% | Non-critical, stateless |
| Karpenter consolidation | 20-30% | Default on |
| gp3 over gp2 | 20% EBS | Always |
| VPC endpoints | NAT Gateway costs | Private clusters |
| target-type: ip | Cross-AZ charges | ALB/NLB |
| Topology-aware routing | 50-80% cross-AZ | High-traffic services |

### Tagging Strategy

All generated resources should include:

```hcl
tags = {
  Project     = var.project_name
  Environment = var.environment
  ManagedBy   = "terraform"
  Cluster     = var.cluster_name
}
```

Karpenter propagates tags to EC2 instances, EBS volumes automatically.
