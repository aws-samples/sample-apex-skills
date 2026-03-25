# In-Place EKS Upgrade

> **Part of:** [eks-upgrader](../SKILL.md)
> **Purpose:** Step-by-step in-place upgrade procedure with validation checkpoints, add-on sequencing, data plane paths, and failure recovery

---

## Table of Contents

1. [Upgrade Sequence](#upgrade-sequence)
2. [Step 1: Upgrade Control Plane](#step-1-upgrade-control-plane)
3. [Step 2: Upgrade EKS Managed Add-ons](#step-2-upgrade-eks-managed-add-ons)
4. [Step 3: Upgrade Data Plane](#step-3-upgrade-data-plane)
5. [Step 4: Upgrade Custom Add-ons](#step-4-upgrade-custom-add-ons)
6. [Step 5: Post-Upgrade Validation](#step-5-post-upgrade-validation)
7. [Ensuring Availability During Upgrade](#ensuring-availability-during-upgrade)
8. [Version Skew Policy](#version-skew-policy)
9. [Bottlerocket-Specific Guidance](#bottlerocket-specific-guidance)
10. [Emergency Rollback](#emergency-rollback)
11. [Common Failure Modes](#common-failure-modes)

---

## Upgrade Sequence

In-place upgrades follow a strict order. Each step must complete and be validated before proceeding to the next.

```
1. Control Plane        (AWS-managed, ~15-30 min, irreversible)
     |
     v-- CHECKPOINT: API server healthy, version confirmed
     |
2. EKS Managed Add-ons  (VPC CNI, CoreDNS, kube-proxy, CSI drivers)
     |
     v-- CHECKPOINT: add-ons running, DNS resolving, networking functional
     |
3. Data Plane           (MNG, Karpenter drift, Auto Mode, Fargate restart)
     |
     v-- CHECKPOINT: all nodes on target version, pods healthy
     |
4. Custom Add-ons       (Karpenter, Istio, ingress controllers, cert-manager, etc.)
     |
     v-- CHECKPOINT: all components reporting healthy
     |
5. Client Tools         (kubectl, Helm, eksctl)
```

---

## Step 1: Upgrade Control Plane

```bash
CLUSTER=my-cluster
TARGET_VERSION=1.31

# Check current version
aws eks describe-cluster --name ${CLUSTER} \
  --query 'cluster.{Version:version,Status:status}'

# Initiate upgrade (one minor version at a time)
UPDATE_ID=$(aws eks update-cluster-version \
  --name ${CLUSTER} \
  --kubernetes-version ${TARGET_VERSION} \
  --query 'update.id' --output text)

# Monitor upgrade progress
watch -n 30 "aws eks describe-update \
  --name ${CLUSTER} \
  --update-id ${UPDATE_ID} \
  --query 'update.{Status:status,Errors:errors}'"
```

### Validation checkpoint

```bash
# Confirm version
aws eks describe-cluster --name ${CLUSTER} \
  --query 'cluster.version' --output text
# Should return: TARGET_VERSION

# Verify API server is healthy
kubectl get --raw /healthz

# Check that existing workloads are unaffected
kubectl get nodes
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### Key constraints

- One minor version at a time (1.30 -> 1.31, not 1.30 -> 1.32)
- Takes 15-30 minutes
- API server remains available during upgrade (brief intermittent errors possible)
- **Cannot be rolled back** -- this is the point of no return

---

## Step 2: Upgrade EKS Managed Add-ons

Add-ons are **not** automatically upgraded with the control plane. Upgrade them in priority order.

### Add-on priority and sequencing

| Priority | Add-On | Why this order |
|----------|--------|---------------|
| 1 | **vpc-cni** | Pod networking -- upgrade before data plane to ensure new nodes get compatible CNI |
| 2 | **kube-proxy** | Service networking -- should match control plane version |
| 3 | **coredns** | Cluster DNS -- should match control plane version |
| 4 | **ebs-csi-driver** | Storage -- upgrade after control plane, before data plane if possible |
| 5 | **efs-csi-driver** | Storage -- same as EBS CSI |
| 6 | **eks-pod-identity-agent** | Pod Identity -- upgrade after control plane |

### Find compatible versions

```bash
TARGET_VERSION=1.31

for ADDON in vpc-cni kube-proxy coredns aws-ebs-csi-driver aws-efs-csi-driver eks-pod-identity-agent; do
  echo "=== ${ADDON} ==="
  aws eks describe-addon-versions \
    --addon-name ${ADDON} \
    --kubernetes-version ${TARGET_VERSION} \
    --query 'addons[0].addonVersions[0:3].{Version:addonVersion,Default:compatibilities[0].defaultVersion}' \
    --output table 2>/dev/null || echo "  Not installed or not available"
done
```

### Upgrade each add-on

```bash
# Check current version first
aws eks describe-addon --cluster-name ${CLUSTER} --addon-name vpc-cni \
  --query 'addon.{Version:addonVersion,Status:status}'

# Upgrade
aws eks update-addon \
  --cluster-name ${CLUSTER} \
  --addon-name vpc-cni \
  --addon-version v1.19.2-eksbuild.1 \
  --resolve-conflicts OVERWRITE

# Monitor status
aws eks describe-addon --cluster-name ${CLUSTER} --addon-name vpc-cni \
  --query 'addon.status'
# Wait for: "ACTIVE"
```

**VPC CNI constraint:** When installed as an EKS managed add-on, VPC CNI can only be upgraded one minor version at a time.

**OVERWRITE vs PRESERVE:** Use `OVERWRITE` to accept the new default config. Use `PRESERVE` if you have custom configuration on the add-on that you want to keep. If `PRESERVE` causes a conflict, the update will fail -- you'll need to manually reconcile.

### Validation checkpoint

```bash
# Verify all add-ons are ACTIVE
aws eks list-addons --cluster-name ${CLUSTER} --output text | \
  xargs -I{} aws eks describe-addon --cluster-name ${CLUSTER} \
  --addon-name {} --query 'addon.{Name:addonName,Version:addonVersion,Status:status}'

# Test DNS resolution
kubectl run dns-test --image=busybox:1.36 --rm -it --restart=Never -- \
  nslookup kubernetes.default.svc.cluster.local

# Test pod networking (create a test pod if needed)
kubectl get pods -A -o wide | head -20
```

---

## Step 3: Upgrade Data Plane

### Managed Node Groups (MNG)

```bash
# List node groups
aws eks list-nodegroups --cluster-name ${CLUSTER} --output text

# Upgrade each node group
aws eks update-nodegroup-version \
  --cluster-name ${CLUSTER} \
  --nodegroup-name default \
  --kubernetes-version ${TARGET_VERSION}

# Monitor rolling update progress
watch -n 30 "aws eks describe-nodegroup \
  --cluster-name ${CLUSTER} \
  --nodegroup-name default \
  --query 'nodegroup.{Status:status,Version:version,DesiredSize:scalingConfig.desiredSize}'"
```

Control rolling update speed:

```bash
# Allow max 1 node unavailable at a time (safest)
aws eks update-nodegroup-config \
  --cluster-name ${CLUSTER} \
  --nodegroup-name default \
  --update-config '{"maxUnavailable": 1}'

# Or percentage-based for large groups
aws eks update-nodegroup-config \
  --cluster-name ${CLUSTER} \
  --nodegroup-name default \
  --update-config '{"maxUnavailablePercentage": 33}'
```

### Karpenter-Managed Nodes

Karpenter handles data plane upgrades automatically through drift detection. After the control plane upgrade, Karpenter detects that node AMIs no longer match the latest EKS-optimized AMI and replaces nodes within disruption budget limits.

```bash
# Check for drifted nodes
kubectl get nodeclaims -o custom-columns=\
NAME:.metadata.name,\
READY:.status.conditions[?(@.type=='Ready')].status,\
DRIFTED:.status.conditions[?(@.type=='Drifted')].status

# Monitor node replacement
kubectl get nodes -l karpenter.sh/nodepool -w

# Force immediate replacement if drift hasn't triggered
kubectl annotate nodeclaims --all karpenter.sh/voluntary-disruption=drifted --overwrite
```

For detailed Karpenter upgrade procedures (including upgrading Karpenter itself), see [karpenter.md](karpenter.md).

### EKS Auto Mode

No action needed. After the control plane upgrade, Auto Mode incrementally updates managed nodes while respecting PDBs. Monitor progress:

```bash
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
VERSION:.status.nodeInfo.kubeletVersion,\
AGE:.metadata.creationTimestamp
```

### Fargate

Fargate profiles don't have long-running nodes -- pods pick up the new version when they're recreated. Restart all Fargate workloads:

```bash
# Identify Fargate pods
kubectl get pods -A -o wide | grep fargate-

# Restart each deployment running on Fargate
kubectl get deployments -A -o json | \
  jq -r '.items[] | select(.spec.template.spec.schedulerName == "fargate-scheduler" or .metadata.annotations["eks.amazonaws.com/fargate-profile"] != null) | "\(.metadata.namespace) \(.metadata.name)"' | \
  while read ns name; do
    kubectl rollout restart deployment ${name} -n ${ns}
  done
```

### Validation checkpoint

```bash
# All nodes on target version
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
VERSION:.status.nodeInfo.kubeletVersion,\
STATUS:.status.conditions[?(@.type=='Ready')].status

# No pending pods
kubectl get pods -A --field-selector=status.phase=Pending

# All nodes Ready
kubectl get nodes | grep -v " Ready"
```

---

## Step 4: Upgrade Custom Add-ons

After the EKS core is upgraded, upgrade self-managed add-ons. Each has its own compatibility matrix with K8s versions.

| Add-on | Compatibility check | Upgrade tool |
|--------|-------------------|--------------|
| **Karpenter** | [Compatibility matrix](karpenter.md#compatibility-matrix) | Helm |
| **Istio** | [Istio support matrix](istio.md#version-compatibility) | istioctl / Helm |
| **AWS Load Balancer Controller** | [Release notes](https://github.com/kubernetes-sigs/aws-load-balancer-controller/releases) | Helm |
| **Cluster Autoscaler** | Must match K8s minor version | Helm |
| **cert-manager** | [Supported releases](https://cert-manager.io/docs/releases/) | Helm |
| **metrics-server** | [Compatibility](https://github.com/kubernetes-sigs/metrics-server#compatibility-matrix) | Helm |
| **Ingress NGINX** | [Changelog](https://github.com/kubernetes/ingress-nginx/blob/main/Changelog.md) | Helm |
| **ArgoCD / Flux** | Check release notes | Helm / CLI |

For Karpenter and Istio, load the dedicated reference files for step-by-step upgrade procedures.

### Validation checkpoint

```bash
# Verify all Helm releases are healthy
helm list -A

# Check all system pods are running
kubectl get pods -n kube-system
kubectl get pods -n istio-system 2>/dev/null
kubectl get pods -n cert-manager 2>/dev/null
kubectl get pods -n ingress-nginx 2>/dev/null
```

---

## Step 5: Post-Upgrade Validation

```bash
# 1. Cluster version confirmed
aws eks describe-cluster --name ${CLUSTER} --query 'cluster.version'

# 2. All nodes on target version
kubectl get nodes -o wide

# 3. All system pods healthy
kubectl get pods -A | grep -v Running | grep -v Completed

# 4. DNS working
kubectl run dns-test --image=busybox:1.36 --rm -it --restart=Never -- \
  nslookup kubernetes.default.svc.cluster.local

# 5. Application health checks passing
# (run your application-specific smoke tests here)

# 6. Verify no deprecated API usage on new version
pluto detect-helm --target-versions k8s=v${TARGET_VERSION}

# 7. Update kubectl client
kubectl version --client
```

---

## Ensuring Availability During Upgrade

### PodDisruptionBudgets

PDBs prevent too many pods from being evicted simultaneously during node drains. Set them on every critical workload before upgrading:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp
spec:
  minAvailable: "80%"    # or maxUnavailable: 1
  selector:
    matchLabels:
      app: myapp
```

### Topology spread constraints

Spreading pods across zones and hosts ensures that a single node replacement doesn't take down all replicas:

```yaml
spec:
  topologySpreadConstraints:
  - maxSkew: 2
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: myapp
  - maxSkew: 2
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: myapp
```

### Pre-upgrade PDB audit

```bash
# List all PDBs and their current status
kubectl get pdb -A

# Check for PDBs that might block drains (0 disruptions allowed)
kubectl get pdb -A -o json | \
  jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name) - allowed: \(.status.disruptionsAllowed)"'
```

Fix any PDBs showing 0 disruptions allowed before starting the upgrade, or node drains will block indefinitely.

---

## Version Skew Policy

| Control Plane Version | Supported kubelet Versions | Skew |
|----------------------|---------------------------|------|
| >= 1.28 | CP version minus 3 (e.g., 1.31 supports kubelet 1.28+) | n-3 |
| < 1.28 | CP version minus 2 (e.g., 1.27 supports kubelet 1.25+) | n-2 |

This gives you a window to upgrade the data plane after the control plane without rushing. However, keep AMI versions current for security patches.

---

## Bottlerocket-Specific Guidance

### Bottlerocket Update Operator (BUO)

BUO handles OS-level security patches via in-place reboot -- distinct from a K8s version upgrade which requires full node replacement.

| Scenario | Action | Tool | Disruption |
|----------|--------|------|------------|
| OS security patch | In-place update + reboot | BUO | Reboot only |
| New Bottlerocket AMI (same K8s) | Node replacement | Karpenter drift / MNG update | Pod eviction + reschedule |
| K8s version upgrade | Full upgrade sequence | EKS API + drift/MNG | Full data plane rollout |

### SSM access (no SSH)

Bottlerocket uses SSM for admin access. Verify connectivity before upgrading:

- Node IAM role has `AmazonSSMManagedInstanceCore` policy
- VPC endpoints for SSM configured (if private subnets without NAT)
- Control container enabled by default; admin container must be explicitly enabled

---

## Emergency Rollback

The control plane cannot be rolled back. Everything else can.

| Component | Method |
|-----------|--------|
| **Data plane nodes** | MNG: update launch template to previous AMI. Karpenter: update EC2NodeClass `amiSelectorTerms` to pin old AMI |
| **EKS managed add-ons** | `aws eks update-addon` to previous version |
| **Helm add-ons** | `helm rollback <release> <revision>` |
| **Applications** | `kubectl rollout undo deployment/<name>` or GitOps revert |
| **CRD changes** | Revert CRD spec, but data migration may not reverse -- test CRD rollback in non-prod first |
| **Network policies** | Revert via GitOps or `kubectl apply` -- takes effect immediately |
| **IAM changes** | Revert Terraform/CloudFormation -- may take minutes to propagate |

### Full cluster rebuild (last resort)

If the upgrade fails catastrophically and the cluster is unrecoverable:

| Step | Action | Time |
|------|--------|------|
| 1 | Provision new EKS cluster at previous version (Terraform) | 15-20 min |
| 2 | Install core add-ons | 5-10 min |
| 3 | Restore Velero backup (K8s resources) | 10-30 min |
| 4 | Restore PV snapshots | 10-30 min |
| 5 | Reconcile GitOps | 5-15 min |
| 6 | Validate + switch DNS/traffic | 10-15 min |
| **Total** | | **~1-2 hours** |

Velero backs up K8s resources and PV data but not AWS resources (IAM roles, security groups, VPC config) -- those must be recreated via IaC.

Test the full rebuild procedure quarterly in an isolated environment so it works when you actually need it.

---

## Common Failure Modes

### Control plane upgrade stuck

**Symptom:** Update status stays `InProgress` for over 45 minutes.

**Check:**
```bash
aws eks describe-update --name ${CLUSTER} --update-id ${UPDATE_ID} \
  --query 'update.errors'
```

**Common causes:**
- Insufficient free IPs in cluster subnets (need 5+)
- KMS key used for secret encryption is inaccessible
- EKS IAM role trust policy is misconfigured

### Add-on update fails with conflict

**Symptom:** Add-on status shows `DEGRADED` or update fails.

**Fix:** If you used `PRESERVE` and there's a config conflict, check what the conflict is:
```bash
aws eks describe-addon --cluster-name ${CLUSTER} --addon-name <addon> \
  --query 'addon.{Status:status,Health:health,ConfigConflicts:configurationConflicts}'
```

Resolve by either accepting defaults (`OVERWRITE`) or manually merging your custom config.

### Node drain blocked by PDB

**Symptom:** MNG update hangs, nodes stay in `NotReady` or cordon state.

**Diagnose:**
```bash
# Find pods blocking drain
kubectl get pdb -A -o json | \
  jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check for pods without controllers (naked pods)
kubectl get pods -A --field-selector=status.phase=Running -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences == null) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Adjust PDB `minAvailable`/`maxUnavailable`, scale up replicas, or delete naked pods blocking the drain.

### Pods crash after data plane upgrade

**Symptom:** Pods in CrashLoopBackOff after nodes are replaced.

**Common causes:**
- Application uses a deprecated API removed in the new version
- Init containers or sidecars incompatible with new kubelet
- Volume mounts fail due to CSI driver version mismatch

**Diagnose:**
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
```

---

**Sources:**
- [AWS EKS Best Practices Guide -- Cluster Upgrades](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
- [EKS Version Lifecycle](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)
- [Kubernetes Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)
