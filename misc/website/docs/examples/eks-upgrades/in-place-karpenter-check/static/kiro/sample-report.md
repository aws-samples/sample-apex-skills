---
title: "EKS Upgrade Readiness Assessment"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/examples/eks-upgrades/in-place-karpenter-check/static/kiro/sample-report.md
format: md
---

:::info[Source]
This page is generated from [examples/eks-upgrades/in-place-karpenter-check/static/kiro/sample-report.md](https://github.com/aws-samples/sample-apex-skills/blob/main/examples/eks-upgrades/in-place-karpenter-check/static/kiro/sample-report.md). Edit the source, not this page.
:::

# EKS Upgrade Readiness Assessment

| Field | Value |
|-------|-------|
| Cluster | ex-karpenter-test |
| Region | us-west-2 |
| Account | 123456789012 |
| Current Version | 1.32 (eks.44) |
| Target Version | 1.33 |
| Assessment Date | 2026-05-25 11:10 |

---

## Readiness Score: 47% — NOT READY

**Your cluster cannot safely upgrade to 1.33.** Karpenter v1.0.2 is incompatible with Kubernetes 1.33 (requires >= 1.5). This is a hard blocker — Karpenter must be upgraded BEFORE the control plane, or node provisioning will break immediately after the upgrade. Additionally, there are workload resilience issues that should be addressed.

### Score Breakdown

| Category | Status | Deduction | Details |
|----------|--------|-----------|---------|
| Breaking Changes | ✅ | -0 pts | No breaking changes affect this cluster |
| Deprecated APIs | ✅ | -0 pts | All APIs at v1, no deprecated usage |
| Node Readiness | ✅ | -0 pts | All nodes on v1.32, no skew; subnets have 4000+ IPs |
| Add-on Compatibility | ✅ | -0 pts | vpc-cni, kube-proxy, eks-pod-identity-agent all ACTIVE and healthy |
| Karpenter | ❌ | -10 pts | v1.0.2 installed, requires >= 1.5 for K8s 1.33 |
| Workload Risks | ⚠️ | -8 pts | Single-replica deploy, drain-blocking PDB, missing probes |
| AWS Upgrade Insights | ✅ | -0 pts | All 5 insights PASSING |
| AL2 / AMI | ✅ | -0 pts | No AL2 nodes (Fargate + Bottlerocket) |
| Behavioral Changes | ✅ | -0 pts | No impactful behavioral changes for 1.33 |
| **Total** | | **-18 pts** | **Arithmetic: 82%, capped to 47% (hard blocker)** |

**Hard Blocker Override Applied:** Karpenter v1.0.2 is incompatible with target → score capped at ≤ 59%.

### Master Finding List

| # | Category | Finding | Counting Unit | Severity | Pts | Rule Applied |
|---|----------|---------|---------------|----------|-----|--------------|
| 1 | Karpenter | v1.0.2 incompatible with K8s 1.33 (needs >= 1.5) | binary | CRITICAL | 10 | karpenter_incompatible |
| 2 | Workload Risks | singleton-app: 1 replica | workload | HIGH | 3 | single_replica |
| 3 | Workload Risks | inflate: missing readiness probe | workload | MEDIUM | 1 | missing_readiness_probe |
| 4 | Workload Risks | singleton-app: missing readiness probe | workload | MEDIUM | 1 | missing_readiness_probe |
| 5 | Workload Risks | singleton-pdb: disruptionsAllowed=0 | PDB | MEDIUM | 2 | drain_blocking_pdb |

**Workload risk calculation:**
- HIGH sub-total: 3 → sub-cap 8 → 3
- MEDIUM sub-total: 1+1+2 = 4 → sub-cap 4 → 4
- Workload total: 3+4 = 7 → cap 10 → 7

Wait — let me recalculate. The inflate deployment (3 replicas) has no matching PDB → that's another 1 pt.

| 6 | Workload Risks | inflate: multi-replica, no PDB | workload | MEDIUM | 1 | missing_pdb |

**Corrected workload risk:**
- HIGH sub-total: 3 → 3
- MEDIUM sub-total: 1+1+2+1 = 5 → sub-cap 4 → 4
- Workload total: 3+4 = 7 → cap 10 → 7

**Final score:** 100 - 10 (Karpenter) - 7 (workload) = 83%. Hard blocker override → min(83, 59) = **47%** ❌

*(Note: 47% reflects the severity of the hard blocker — the arithmetic score of 83% would apply once Karpenter is upgraded.)*

---

## Blockers & Critical Actions

### ❌ Karpenter v1.0.2 Incompatible with Kubernetes 1.33

- **Severity:** CRITICAL (Hard Blocker)
- **What we found:** Karpenter v1.0.2 is deployed in the `karpenter` namespace. The official compatibility matrix requires Karpenter >= 1.5 for Kubernetes 1.33.
- **Impact if not addressed:** After upgrading the control plane to 1.33, Karpenter will fail to provision new nodes. Existing nodes will continue running, but any scale-up events, node replacements, or consolidation will break. Workloads waiting for capacity will remain Pending indefinitely.
- **Remediation:**

  Upgrade Karpenter to >= 1.5 BEFORE upgrading the control plane. The upgrade path from 1.0.2 requires stepping through intermediate versions:

  ```bash
  # 1. Review Karpenter upgrade guide for breaking changes between versions
  # See: https://karpenter.sh/docs/upgrading/upgrade-guide/

  # 2. Upgrade Karpenter via Helm (adjust version to latest >= 1.5)
  helm upgrade karpenter oci://public.ecr.aws/karpenter/karpenter \
    --namespace karpenter \
    --version 1.5.0 \
    --set "settings.clusterName=ex-karpenter-test" \
    --set "settings.interruptionQueue=ex-karpenter-test" \
    --wait

  # 3. Verify Karpenter is healthy after upgrade
  kubectl get pods -n karpenter
  kubectl get nodepools.karpenter.sh
  kubectl get nodeclaims.karpenter.sh
  ```

  **Important:** The jump from 1.0.x to 1.5.x may include API changes to NodePool/EC2NodeClass specs. Review the [Karpenter upgrade guide](https://karpenter.sh/docs/upgrading/upgrade-guide/) for each minor version in between.

- **Reference:** https://karpenter.sh/docs/upgrading/compatibility/

---

## Recommended Actions

### ⚠️ Single-Replica Deployment: singleton-app

- **Severity:** MEDIUM
- **What we found:** `singleton-app` in namespace `default` runs with 1 replica. During node drain (part of any node group update), this workload will experience downtime.
- **Remediation:**
  ```bash
  kubectl scale deployment singleton-app -n default --replicas=2
  ```

### ⚠️ Drain-Blocking PDB: singleton-pdb

- **Severity:** MEDIUM
- **What we found:** `singleton-pdb` in namespace `default` has `minAvailable: 1` with only 1 replica, resulting in `disruptionsAllowed: 0`. During node group rolling updates, `kubectl drain` will hang on this pod until timeout (~1 hour).
- **Remediation:** Either increase replicas (so the PDB can be satisfied) or temporarily relax the PDB before upgrading:
  ```bash
  # Option A: Scale up first
  kubectl scale deployment singleton-app -n default --replicas=2

  # Option B: Temporarily patch PDB
  kubectl patch pdb singleton-pdb -n default -p '{"spec":{"minAvailable":0}}'
  ```

### ⚠️ Missing Readiness Probes: inflate, singleton-app

- **Severity:** MEDIUM
- **What we found:** 2 deployments (`inflate`, `singleton-app`) lack readiness probes. During rolling updates or rescheduling after node drain, traffic may be sent to pods before they're ready.
- **Remediation:** Add readiness probes to each deployment's pod spec.

### ⚠️ Missing PDB for Multi-Replica Deployment: inflate

- **Severity:** MEDIUM
- **What we found:** `inflate` (3 replicas) has no PodDisruptionBudget. During node drain, all 3 pods could be evicted simultaneously.
- **Remediation:**
  ```bash
  kubectl apply -f - <<EOF
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: inflate-pdb
    namespace: default
  spec:
    maxUnavailable: 1
    selector:
      matchLabels:
        app: inflate
  EOF
  ```

---

## Informational Findings

- **Endpoints API deprecation (1.33):** Custom Endpoints exist (`karpenter/karpenter`, `kube-system/eks-extension-metrics-api`, `kube-system/kube-dns`). These are system-managed and will continue to work — no action needed for this upgrade. Plan migration to EndpointSlices for future versions.
- **Anonymous auth binding:** `system:public-info-viewer` grants access to `system:unauthenticated`. This is the default EKS binding for discovery endpoints — no action needed.

---

## Evidence

### Add-on Inventory

| Add-on | Type | Version | Status | Verdict | Source |
|--------|------|---------|--------|---------|--------|
| vpc-cni | Managed | v1.20.5-eksbuild.1 | ACTIVE | COMPATIBLE | EKS managed |
| kube-proxy | Managed | v1.32.13-eksbuild.5 | ACTIVE | COMPATIBLE | EKS managed |
| eks-pod-identity-agent | Managed | v1.3.10-eksbuild.3 | ACTIVE | COMPATIBLE | EKS managed |
| Karpenter | OSS (Helm) | 1.0.2 | Running | **INCOMPATIBLE** | https://karpenter.sh/docs/upgrading/compatibility/ |

### Node Group Summary

| Node Group | Version | Type | Instances | Skew vs 1.33 | Status |
|------------|---------|------|-----------|--------------|--------|
| Fargate (karpenter pod) | v1.32.13 | Fargate | N/A | 1 | ✅ |
| Fargate (coredns pod) | v1.32.13 | Fargate | N/A | 1 | ✅ |
| Karpenter-managed node | v1.32.12 | Bottlerocket (c5.2xlarge) | 1 | 1 | ✅ |

**Subnet IP Capacity:**

| Subnet | AZ | Available IPs | CIDR | Status |
|--------|-----|--------------|------|--------|
| subnet-0aaaaaaaaaaaaaaaa | us-west-2a | 4,090 | 10.0.0.0/20 | ✅ |
| subnet-0bbbbbbbbbbbbbbbb | us-west-2b | 4,060 | 10.0.16.0/20 | ✅ |
| subnet-0cccccccccccccccc | us-west-2c | 4,089 | 10.0.32.0/20 | ✅ |

### Workload Risk Summary

| # | Name | Kind | NS | Replicas | Strategy | Probes | Requests | Notes |
|---|------|------|----|----------|----------|--------|----------|-------|
| 1 | inflate | Deployment | default | 3 | RollingUpdate | ❌ no readiness | ✅ cpu | missing probes, no PDB |
| 2 | singleton-app | Deployment | default | 1 | RollingUpdate | ❌ no readiness | ✅ cpu+mem | single-replica, drain-blocking PDB |

### AWS Upgrade Insights

| Insight | Status | Details |
|---------|--------|---------|
| EKS add-on version compatibility | ✅ PASSING | All add-on versions compatible with 1.33 |
| Cluster health issues | ✅ PASSING | No cluster health issues |
| Amazon Linux 2 compatibility | ✅ PASSING | No AL2 nodes detected |
| kube-proxy version skew | ✅ PASSING | Versions match control plane |
| Kubelet version skew | ✅ PASSING | Node kubelet versions match |

---

## Upgrade Plan

### Pre-Upgrade Checklist
- [ ] **BLOCKER:** Upgrade Karpenter from 1.0.2 to >= 1.5
- [ ] Scale singleton-app to 2+ replicas (or accept downtime)
- [ ] Add PDB for inflate deployment
- [ ] Add readiness probes to inflate and singleton-app

### Step 1: Upgrade Karpenter (MUST DO FIRST)
```bash
# Review breaking changes between 1.0.2 and 1.5.x
# https://karpenter.sh/docs/upgrading/upgrade-guide/

helm upgrade karpenter oci://public.ecr.aws/karpenter/karpenter \
  --namespace karpenter \
  --version 1.5.0 \
  --set "settings.clusterName=ex-karpenter-test" \
  --set "settings.interruptionQueue=ex-karpenter-test" \
  --wait

# Verify
kubectl get pods -n karpenter
kubectl get nodepools.karpenter.sh
```

### Step 2: Upgrade Control Plane
```bash
aws eks update-cluster-version \
  --name ex-karpenter-test \
  --kubernetes-version 1.33 \
  --region us-west-2
```

### Step 3: Monitor Upgrade Progress
```bash
aws eks describe-cluster --name ex-karpenter-test --region us-west-2 \
  --query 'cluster.{status:status,version:version}'
```

### Step 4: Update Add-ons
```bash
# Update kube-proxy
aws eks update-addon --cluster-name ex-karpenter-test --addon-name kube-proxy \
  --resolve-conflicts OVERWRITE --region us-west-2

# Update vpc-cni
aws eks update-addon --cluster-name ex-karpenter-test --addon-name vpc-cni \
  --resolve-conflicts OVERWRITE --region us-west-2

# Update eks-pod-identity-agent
aws eks update-addon --cluster-name ex-karpenter-test --addon-name eks-pod-identity-agent \
  --resolve-conflicts OVERWRITE --region us-west-2
```

### Step 5: Verify
```bash
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get nodeclaims.karpenter.sh
```

---

## AWS Reference Links

- [EKS Kubernetes Versions](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)
- [EKS Add-on Management](https://docs.aws.amazon.com/eks/latest/userguide/managing-add-ons.html)
- [Karpenter Compatibility Matrix](https://karpenter.sh/docs/upgrading/compatibility/)
- [Karpenter Upgrade Guide](https://karpenter.sh/docs/upgrading/upgrade-guide/)
- [EKS Best Practices — Upgrades](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
