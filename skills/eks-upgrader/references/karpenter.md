# Karpenter Upgrade Guide

> **Part of:** [eks-upgrader](../SKILL.md)
> **Purpose:** Karpenter <-> K8s version compatibility, Helm upgrade procedure, CRD management, API migration boundaries, drift-based node replacement, and version-specific breaking changes

---

## Table of Contents

1. [Compatibility Matrix](#compatibility-matrix)
2. [Pre-Upgrade Validation](#pre-upgrade-validation)
3. [Upgrade Procedure](#upgrade-procedure)
4. [CRD Management](#crd-management)
5. [API Migration Boundaries](#api-migration-boundaries)
6. [Drift-Based Node Replacement](#drift-based-node-replacement)
7. [Karpenter Hosting](#karpenter-hosting)
8. [Disruption Budgets](#disruption-budgets)
9. [Version-Specific Breaking Changes](#version-specific-breaking-changes)
10. [Rollback](#rollback)
11. [Common Issues](#common-issues)

---

## Compatibility Matrix

| Kubernetes | Minimum Karpenter Version |
|-----------|--------------------------|
| **1.29** | >= 0.34 |
| **1.30** | >= 0.37 |
| **1.31** | >= 1.0.5 |
| **1.32** | >= 1.2 |
| **1.33** | >= 1.5 |
| **1.34** | >= 1.6 |
| **1.35** | >= 1.9 |

Karpenter is not tied to a specific K8s version like Cluster Autoscaler. However, each Karpenter release has a minimum supported K8s version. Always check this matrix before upgrading either component.

### Upgrade ordering with EKS

When upgrading both EKS and Karpenter:

1. **Check if your current Karpenter version supports the target K8s version** using the matrix above
2. If yes -- upgrade EKS control plane first, then upgrade Karpenter at your convenience
3. If no -- upgrade Karpenter first to a version that supports both your current and target K8s versions, then upgrade EKS

---

## Pre-Upgrade Validation

```bash
# 1. Document current version
helm list -n kube-system | grep karpenter

# 2. Back up NodePool and EC2NodeClass configurations
kubectl get nodepools -o yaml > nodepools-backup.yaml
kubectl get ec2nodeclasses -o yaml > ec2nodeclasses-backup.yaml

# 3. Check current node state
kubectl get nodes -l karpenter.sh/nodepool --show-labels

# 4. Verify webhook configurations
kubectl get mutatingwebhookconfigurations | grep karpenter
kubectl get validatingwebhookconfigurations | grep karpenter

# 5. Check IAM permissions (controller role and node role)
# Verify the controller role has permissions required by the target version

# 6. Review pending pods and disruption state
kubectl get nodeclaims
kubectl get pods --field-selector=status.phase=Pending -A
```

Before any Karpenter upgrade, review the [version-specific breaking changes](#version-specific-breaking-changes) for every minor version between your current and target version.

---

## Upgrade Procedure

### Upgrade Checklist

Before generating an upgrade plan, confirm all applicable items are included:

- [ ] CRD upgrade step (BEFORE controller -- bundled chart does not auto-upgrade CRDs)
- [ ] Controller upgrade step
- [ ] Karpenter hosting compute refresh -- Karpenter pods run on Fargate or MNG, which don't auto-drift. Handle them like any other Fargate/MNG workload in the data plane step
- [ ] Disruption budget review -- if budget may block node replacement (e.g., 10% of 1 node = 0), ask user:
  - **Wait:** Let nodes replace naturally as workloads scale and budget allows
  - **Expedite:** Temporarily adjust budget or `kubectl delete nodeclaim <name>`, then revert budget after
- [ ] Post-upgrade validation

Do not proceed with plan generation until all applicable items are addressed.

### Overview

Karpenter is installed via Helm. The upgrade follows a two-step process: CRDs first, then the controller.

### Standard Helm upgrade

```bash
KARPENTER_NAMESPACE=kube-system
KARPENTER_VERSION=1.10.0

# Step 1: Upgrade CRDs (using the independent CRD chart -- recommended)
helm upgrade --install karpenter-crd \
    oci://public.ecr.aws/karpenter/karpenter-crd \
    --version "${KARPENTER_VERSION}" \
    --namespace "${KARPENTER_NAMESPACE}"

# Step 2: Upgrade the controller
helm upgrade karpenter \
    oci://public.ecr.aws/karpenter/karpenter \
    --version "${KARPENTER_VERSION}" \
    --namespace "${KARPENTER_NAMESPACE}" \
    --reuse-values
```

When using `--reuse-values`, verify that your existing values are compatible with the new version. Some Helm values are renamed or removed between versions.

### Post-upgrade verification

```bash
# Verify controller is running
kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter

# Check controller logs for errors
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter --tail=50

# Verify CRD versions
kubectl get crd nodepools.karpenter.sh -o jsonpath='{.spec.versions[*].name}'
kubectl get crd ec2nodeclasses.karpenter.k8s.aws -o jsonpath='{.spec.versions[*].name}'

# Verify NodePools are healthy
kubectl get nodepools
kubectl get ec2nodeclasses
```

---

## CRD Management

Karpenter CRDs are tightly coupled to the Karpenter version and must be updated alongside the controller. There are two approaches:

| Method | Lifecycle Management | Recommended |
|--------|---------------------|-------------|
| **Independent `karpenter-crd` chart** | Helm manages CRD upgrades and deletions | Yes |
| **Bundled in `karpenter` chart** | Helm only installs CRDs on first install; never upgrades them | No |

The independent chart ensures CRDs stay in sync with the controller. If you're currently using the bundled approach, switch to the independent chart:

```bash
helm install karpenter-crd \
    oci://public.ecr.aws/karpenter/karpenter-crd \
    --version "${KARPENTER_VERSION}" \
    --namespace kube-system
```

If you get `invalid ownership metadata; label validation error` when installing the `karpenter-crd` chart, see the [CRD ownership fix](#crd-ownership-errors) in Common Issues.

---

## API Migration Boundaries

Karpenter has gone through three API generations. Understanding these boundaries is critical for planning multi-version upgrades.

```
v1alpha5 (Provisioner, AWSNodeTemplate, Machine)
    |
    v--- 0.32: introduced v1beta1 alongside v1alpha5
    |
v1beta1 (NodePool, EC2NodeClass, NodeClaim)
    |
    v--- 0.33+: v1alpha5 dropped, v1beta1 only
    |
    v--- 1.0: introduced v1 with conversion webhooks for v1beta1
    |
v1 (NodePool, EC2NodeClass, NodeClaim)
    |
    v--- 1.1+: v1beta1 dropped, v1 only
```

### Migration rules

| Current Version | Target Version | Migration Path |
|----------------|---------------|----------------|
| < 0.32 | 0.33+ | Must upgrade to 0.32.x first (supports both alpha + beta), migrate resources, then upgrade |
| 0.32 - 0.37 | 1.0+ | Follow the [v1 Migration Guide](https://karpenter.sh/docs/upgrading/v1-migration/) |
| 0.32 - 1.0 | 1.1+ | Must complete v1beta1 -> v1 migration first. 1.1+ drops v1beta1 entirely |
| >= 1.1 | Latest | Standard Helm upgrade, check breaking changes per version |

**The most common pitfall:** upgrading directly to 1.1+ without completing the v1 migration. Karpenter 1.1+ will not recognize v1beta1 resources, causing provisioning failures.

### Verify migration status

```bash
# Check if any v1beta1 resources still exist
kubectl get nodepools.v1beta1.karpenter.sh 2>/dev/null
kubectl get ec2nodeclasses.v1beta1.karpenter.k8s.aws 2>/dev/null
kubectl get nodeclaims.v1beta1.karpenter.sh 2>/dev/null

# If these return results, complete the v1 migration before upgrading to 1.1+
```

---

## Drift-Based Node Replacement

After an EKS control plane upgrade, Karpenter automatically detects that existing nodes are running an outdated AMI and replaces them. This is the primary mechanism for data plane upgrades in Karpenter-managed clusters.

### How it works

1. EKS control plane is upgraded (e.g., 1.30 -> 1.31)
2. AWS publishes a new EKS-optimized AMI for 1.31
3. Karpenter detects that existing nodes' AMIs don't match the latest for their K8s version
4. Karpenter marks nodes as `Drifted`
5. Karpenter provisions replacement nodes with the new AMI
6. Karpenter cordons, drains (respecting PDBs), and terminates old nodes

### Monitor drift replacement

```bash
# Check for drifted nodes
kubectl get nodeclaims -o custom-columns=\
NAME:.metadata.name,\
NODEPOOL:.metadata.labels.karpenter\.sh/nodepool,\
READY:.status.conditions[?(@.type=='Ready')].status,\
DRIFTED:.status.conditions[?(@.type=='Drifted')].status

# Watch node replacement in real-time
kubectl get nodes -l karpenter.sh/nodepool -w
```

### Force immediate replacement

If drift detection hasn't triggered or you want to force a rollout:

```bash
# Annotate all Karpenter nodes to trigger drift
kubectl annotate nodeclaims --all karpenter.sh/voluntary-disruption=drifted --overwrite
```

### Control drift with EC2NodeClass

Karpenter discovers AMIs based on the `amiFamily` or `amiSelectorTerms` in your EC2NodeClass. If you pin specific AMI IDs, Karpenter won't automatically drift to newer AMIs -- you must update the EC2NodeClass to reference the new AMI:

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  # Auto-discovery (drift happens automatically when AWS publishes new AMIs):
  amiFamily: AL2023

  # Pinned AMI (drift only happens when you update this list):
  # amiSelectorTerms:
  # - id: ami-0123456789abcdef0
```

---

## Karpenter Hosting

Karpenter itself runs on compute that must be upgraded alongside the control plane.

| Karpenter Runs On | Upgrade Method |
|-------------------|----------------|
| **Fargate** | `kubectl rollout restart deployment karpenter -n <namespace>` |
| **MNG** | Include Karpenter nodes in MNG rotation (update launch template, refresh node group) |

Fargate and MNG nodes are not managed by Karpenter, so they don't auto-drift. Refresh them **after** upgrading the Karpenter controller but **before** relying on Karpenter to replace data plane nodes.

```bash
# Fargate: restart to get new Fargate nodes at control plane version
kubectl rollout restart deployment karpenter -n karpenter
kubectl rollout status deployment karpenter -n karpenter

# Verify Karpenter pods are running on upgraded nodes
kubectl get pods -n karpenter -o wide
```

---

## Disruption Budgets

Disruption budgets control how aggressively Karpenter replaces nodes during drift, consolidation, and expiration. This is critical during EKS upgrades to prevent replacing too many nodes simultaneously.

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    budgets:
    # Normal operations: replace at most 10% of nodes at a time
    - nodes: "10%"
    # Business hours: no disruptions
    - nodes: "0"
      schedule: "0 9 * * 1-5"    # Mon-Fri 9 AM UTC
      duration: 8h
```

### Budget behavior during upgrades

| Scenario | Budget Applies? | Notes |
|----------|----------------|-------|
| **Drift replacement** | Yes | Nodes are replaced within budget limits |
| **Consolidation** | Yes | Empty/underutilized node removal respects budgets |
| **Expiration** (`expireAfter`) | Yes | Expired nodes replaced within budget |
| **Manual node deletion** | No | `kubectl delete node` bypasses budgets |
| **Spot interruption** | No | Involuntary disruption, no budget |

### Recommended budget for upgrades

During an EKS upgrade, you may want a dedicated budget that allows faster node replacement than your normal operating budget:

```yaml
budgets:
- nodes: "20%"    # Allow faster replacement during upgrades
```

After the upgrade completes and all nodes are on the new version, revert to your normal budget.

### Node expiry as alternative to drift

Instead of relying on drift detection, you can set `expireAfter` to force periodic node replacement, ensuring nodes always run recent AMIs:

```yaml
spec:
  template:
    spec:
      expireAfter: 720h    # 30 days
```

Karpenter does not add jitter to expiry -- if many nodes were created at the same time, they'll all expire together. Use PDBs and disruption budgets to prevent mass simultaneous replacement.

---

## Version-Specific Breaking Changes

This section covers breaking changes for Karpenter 1.x releases. For changes in 0.x versions, see the [full upgrade guide](https://karpenter.sh/docs/upgrading/upgrade-guide/).

### 1.10.0+

- New EventBridge detail-type for Capacity Reservation Instance Interruption warnings. Update EventBridge rules if using interruptible ODCRs.

### 1.9.0+

- IAM policy from the getting-started CloudFormation template is now split into 5 separate policies. If you depend on this template, update your IAM role to attach all 5.

### 1.8.0+

- Adds Static Capacity support. Upgrade CRDs to use this feature.
- **Avoid v1.8.4** -- contains a regression with TopologySpreadConstraint scheduling.

### 1.7.0+

- Instance profiles now created with path `/karpenter/{region}/{cluster-name}/{nodeclass-uid}/` instead of root `/`.
- **New IAM permission required:** `iam:ListInstanceProfiles` on the controller role.
- Metric renames: `karpenter_pods_pods_drained_total` -> `karpenter_pods_drained_total`, reason `liveness` -> `registration_timeout`.

### 1.6.0+

- Native ODCR support graduates to beta (enabled by default). Review the [ODCR guide](https://karpenter.sh/docs/concepts/nodepools/#on-demand-capacity-reservations) if using open ODCRs.
- New config options: `MinValuesPolicy` (Strict/BestEffort) and `DisableDryRun`.

### 1.3.0+

- New `reserved` capacity type for ODCRs. Workloads with `nodeSelector: karpenter.sh/capacity-type: on-demand` won't match reserved capacity -- use nodeAffinity to allow both.
- Metric rename: `karpenter_ignored_pod_count` -> `karpenter_scheduler_ignored_pod_count`.

### 1.2.0+

- Metric reason labels changed from camelCase to snake_case (e.g., `Drifted` -> `drifted`).
- NodeClass status and termination controllers merged into single `nodeclass` controller.

### 1.1.0+ (Major migration boundary)

- **v1beta1 API support dropped.** Complete the v1 migration before upgrading.
- `nodeClassRef.group` and `nodeClassRef.kind` are strictly required on all NodePools/NodeClaims.
- Neuron accelerator label values corrected: all were `inferentia`, now correctly `trainium`, `inferentia`, `inferentia2`.
- Internal `karpenter.k8s.aws/cluster` tag replaced by `eks:eks-cluster-name`.

### 1.0.0+ (Major migration boundary)

- Introduces v1 APIs with conversion webhooks for v1beta1. Follow the [v1 Migration Guide](https://karpenter.sh/docs/upgrading/v1-migration/).

### 0.37.0+

- Readiness status condition added to EC2NodeClass. **CRDs must be updated before the controller**, or Karpenter cannot provision nodes.
- Webhooks re-enabled by default. If network policies block ingress, allowlist ports 8000, 8001, 8081, 8443.

### 0.34.0+

- Introduces disruption budgets. Default is 10% of nodes per NodePool. This is a significant behavior change from pre-0.34 hard-coded parallelism limits.
- Controller may use more CPU/memory due to multi-batch disruption processing. Increase resource limits if needed.
- DNS policy changed back to `ClusterFirst`. If running Karpenter on Fargate/MNG managing your DNS service, set `--set dnsPolicy=Default`.

### 0.33.0+

- **v1alpha5 API dropped.** Must upgrade to 0.32.x first and migrate all Provisioner/AWSNodeTemplate/Machine resources to NodePool/EC2NodeClass/NodeClaim.
- Drift enabled by default via `FEATURE_GATES`.
- Settings via `karpenter-global-settings` ConfigMap dropped. Use container environment variables instead.
- Recommended namespace changed to `kube-system` for API Priority and Fairness benefits. If using IRSA, update the trust policy namespace.

---

## Rollback

### Standard rollback (within same API generation)

```bash
PREVIOUS_VERSION=1.9.0

# Rollback CRDs
helm upgrade --install karpenter-crd \
    oci://public.ecr.aws/karpenter/karpenter-crd \
    --version "${PREVIOUS_VERSION}" \
    --namespace kube-system

# Rollback controller
helm upgrade karpenter \
    oci://public.ecr.aws/karpenter/karpenter \
    --version "${PREVIOUS_VERSION}" \
    --namespace kube-system \
    --reuse-values
```

### Rollback across API boundaries

Rolling back across a major API boundary (e.g., from 1.1+ back to 0.3x) is risky and may require manual cleanup:

- **1.1+ -> 1.0.x:** Possible if v1 resources are still present. The 1.0 conversion webhooks will serve v1beta1 requests.
- **1.0+ -> 0.3x:** Requires removing Machine CRs and the `karpenter.sh/managed-by` tags from EC2 instances, or Karpenter may garbage-collect the instances.
- **0.33+ -> 0.32.x:** Only 0.32.x supports handling rollback after v1beta1 APIs are deployed.
- **0.36+ -> older:** Only specific patch versions support rollback (0.32.9+, 0.33.4+, 0.34.5+, 0.35.4+). Older patches may drift all nodes.

---

## Common Issues

### CRD ownership errors

**Symptom:** `invalid ownership metadata; label validation error` when upgrading the `karpenter-crd` chart.

**Cause:** CRDs were originally installed by the bundled `karpenter` chart and don't have the ownership labels expected by the `karpenter-crd` chart.

```bash
# Transfer CRD ownership to the karpenter-crd release
for crd in $(kubectl get crds | grep karpenter | awk '{print $1}'); do
    kubectl label crd "$crd" "app.kubernetes.io/managed-by=Helm" --overwrite
    kubectl annotate crd "$crd" "meta.helm.sh/release-name=karpenter-crd" --overwrite
    kubectl annotate crd "$crd" "meta.helm.sh/release-namespace=kube-system" --overwrite
done
```

### Nodes not replacing after EKS upgrade

**Symptom:** EKS control plane upgraded but Karpenter nodes still running old AMI.

**Possible causes:**

1. **AMIs are pinned** in EC2NodeClass `amiSelectorTerms` -- Karpenter won't detect drift. Update the AMI IDs manually.
2. **Disruption budgets set to `nodes: "0"`** -- check if a budget window is blocking disruption.
3. **PDBs blocking drain** -- a pod's PDB may prevent node drain. Check `kubectl get pdb -A`.

```bash
# Check if drift is detected
kubectl get nodeclaims -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Drifted")].status}{"\n"}{end}'

# Check disruption budget status
kubectl describe nodepool default | grep -A5 "Disruption"
```

### Webhook connection failures

**Symptom:** Pod scheduling fails with errors referencing Karpenter webhooks.

**Cause:** Network policies blocking ingress to Karpenter webhook ports (8000, 8001, 8081, 8443), or webhook configurations referencing a non-existent service after upgrade.

```bash
# Check webhook configurations
kubectl get validatingwebhookconfigurations | grep karpenter
kubectl get mutatingwebhookconfigurations | grep karpenter

# Verify webhook service has endpoints
kubectl get endpoints -n kube-system | grep karpenter

# If stale webhooks exist from a previous version, delete them
kubectl delete validatingwebhookconfiguration <stale-webhook-name>
kubectl delete mutatingwebhookconfiguration <stale-webhook-name>
```

### Controller resource exhaustion after upgrade

**Symptom:** Karpenter pod OOMKilled or high CPU after upgrading to 0.34+.

**Cause:** Multi-batch disruption processing (introduced in 0.34) uses more resources than the single-batch approach in earlier versions.

```bash
# Increase controller resources
helm upgrade karpenter oci://public.ecr.aws/karpenter/karpenter \
    --version "${KARPENTER_VERSION}" \
    --namespace kube-system \
    --set controller.resources.requests.cpu=1 \
    --set controller.resources.requests.memory=1Gi \
    --set controller.resources.limits.memory=2Gi \
    --reuse-values
```

### Coordinating Karpenter and EKS upgrades

When upgrading both in the same maintenance window:

1. **Upgrade Karpenter first** (if needed for K8s compatibility)
2. **Upgrade EKS control plane** -- Karpenter continues running, nodes unchanged
3. **Let drift handle node replacement** -- Karpenter detects AMI drift and replaces nodes within disruption budgets
4. **Verify all nodes on new version:**

```bash
kubectl get nodes -l karpenter.sh/nodepool \
    -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,AGE:.metadata.creationTimestamp
```

If nodes are stuck on the old version, check drift detection, disruption budgets, and PDBs as described above.

---

**Sources:**
- [Karpenter Upgrade Guide](https://karpenter.sh/docs/upgrading/upgrade-guide/)
- [Karpenter Compatibility](https://karpenter.sh/docs/upgrading/compatibility/)
- [v1 Migration Guide](https://karpenter.sh/docs/upgrading/v1-migration/)
- [Disruption Budgets](https://karpenter.sh/docs/concepts/disruption/)
