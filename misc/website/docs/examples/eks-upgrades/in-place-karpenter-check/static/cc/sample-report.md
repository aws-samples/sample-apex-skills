---
title: "EKS Upgrade Readiness Assessment"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/examples/eks-upgrades/in-place-karpenter-check/static/cc/sample-report.md
format: md
---

:::info[Source]
This page is generated from [examples/eks-upgrades/in-place-karpenter-check/static/cc/sample-report.md](https://github.com/aws-samples/sample-apex-skills/blob/main/examples/eks-upgrades/in-place-karpenter-check/static/cc/sample-report.md). Edit the source, not this page.
:::

# EKS Upgrade Readiness Assessment

| Field | Value |
|-------|-------|
| Cluster | ex-karpenter-test |
| Region | us-west-2 |
| Account | 123456789012 |
| Current Version | 1.32 (Extended Support) |
| Target Version | 1.33 |
| Assessment Date | 2026-05-25 |

---

## Readiness Score: 59% — NOT READY

**Karpenter 1.0.2 is incompatible with Kubernetes 1.33 (requires >= 1.5).** This is a hard blocker — node provisioning will break after the control plane upgrade. You must upgrade Karpenter to >= 1.5 before upgrading the control plane. All other checks pass cleanly; once Karpenter is resolved, this cluster is in good shape.

### Score Breakdown

| Category | Status | Deduction | Details |
|----------|--------|-----------|---------|
| Breaking Changes | ✅ | -0 pts | None detected for 1.33 target |
| Deprecated APIs | ✅ | -0 pts | All resources on current API versions |
| Node Readiness | ✅ | -0 pts | All nodes on 1.32, subnets have 4000+ IPs |
| Add-on Compatibility | ✅ | -0 pts | vpc-cni, kube-proxy, pod-identity-agent all healthy |
| Karpenter | ❌ | -10 pts | v1.0.2 installed, requires >= 1.5 for K8s 1.33 |
| Workload Risks | ⚠️ | -7 pts | 1 single-replica, missing probes, missing PDB |
| AWS Upgrade Insights | ✅ | -0 pts | All 5 insights PASSING |
| AL2 / AMI | ✅ | -0 pts | No AL2 nodes (Fargate + Bottlerocket) |
| Behavioral Changes | ✅ | -0 pts | Endpoints deprecation is informational only |
| **Total** | | **-17 pts** | **Arithmetic: 83%, capped to 59% (hard blocker)** |

**Hard Blocker:** Karpenter 1.0.2 incompatible with target → score capped at 59%

---

## Blockers & Critical Actions

### Karpenter 1.0.2 Incompatible with Kubernetes 1.33

- **Severity:** CRITICAL (Hard Blocker)
- **What we found:** Karpenter v1.0.2 is deployed in the `karpenter` namespace. The official compatibility matrix requires Karpenter >= 1.5 for Kubernetes 1.33.
- **Impact if not addressed:** After the control plane upgrades to 1.33, Karpenter will fail to provision new nodes. Existing nodes continue running but new capacity requests (scale-up, spot interruption replacements, consolidation) will fail. The cluster will effectively lose autoscaling.
- **Remediation:**

  Upgrade Karpenter **before** the control plane upgrade. The 1.0.x → 1.5+ jump crosses the v1 API boundary — verify your NodePool and EC2NodeClass CRDs are on v1 APIs (not v1beta1):

  ```bash
  # 1. Check current Karpenter version
  kubectl get deployment karpenter -n karpenter -o jsonpath='{.spec.template.spec.containers[0].image}'

  # 2. Verify NodePool CRDs are v1 (not v1beta1)
  kubectl get nodepools.karpenter.sh -o yaml | grep apiVersion

  # 3. Upgrade Karpenter via Helm (adjust version to latest >= 1.5)
  helm upgrade karpenter oci://public.ecr.aws/karpenter/karpenter \
    --namespace karpenter \
    --version 1.5.0 \
    --set clusterName=ex-karpenter-test \
    --set clusterEndpoint=$(aws eks describe-cluster --name ex-karpenter-test --query cluster.endpoint --output text --region us-west-2) \
    --wait

  # 4. Verify Karpenter is healthy after upgrade
  kubectl get pods -n karpenter
  kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=20
  ```

- **Reference:** https://karpenter.sh/docs/upgrading/compatibility/

### Extended Support Cost Impact

- **Severity:** HIGH
- **What we found:** Cluster is on v1.32 which entered Extended Support on March 23, 2026. You are currently paying the extended support rate.
- **Impact:** Extended support costs $0.60/hr vs $0.10/hr for standard support. Monthly cost: $0.60 x 730 = $438/month (vs $73/month on standard). Extra cost: $0.50 x 730 = $365/month.
- **Remediation:** Upgrading to 1.33 (standard support until July 29, 2026) returns you to standard pricing.

---

## Recommended Actions

### Single-Replica Deployment: singleton-app

- **Severity:** MEDIUM
- **What we found:** `default/singleton-app` runs with 1 replica. During node drain (Karpenter consolidation or upgrade), this workload will experience downtime.
- **Remediation:** Scale to 2+ replicas if the workload requires availability, or accept brief downtime during upgrades.

### Missing Readiness Probes

- **Severity:** MEDIUM
- **What we found:** 2 workloads lack readiness probes:
  - `default/inflate` (3 replicas)
  - `default/singleton-app` (1 replica)
- **Remediation:** Add readiness probes so Kubernetes knows when pods are ready to receive traffic. Without probes, traffic may be sent to pods that aren't ready after rescheduling.

### Missing PDB for Multi-Replica Deployment: inflate

- **Severity:** MEDIUM
- **What we found:** `default/inflate` has 3 replicas but no PodDisruptionBudget. During node drain, all 3 pods could be evicted simultaneously.
- **Remediation:**
  ```bash
  kubectl create pdb inflate-pdb --namespace default \
    --selector app=inflate --min-available 2
  ```

### Missing Memory Request: inflate

- **Severity:** MEDIUM
- **What we found:** The `inflate` container in `default/inflate` has a CPU request but no memory request. Without memory requests, the scheduler cannot make optimal placement decisions during rescheduling.
- **Remediation:** Add `resources.requests.memory` to the container spec.

---

## Informational Findings

- **Endpoints API deprecated in 1.33:** The Endpoints API is deprecated in favor of EndpointSlices (`discovery.k8s.io/v1`). The 3 endpoints found (`karpenter/karpenter`, `kube-system/eks-extension-metrics-api`, `kube-system/kube-dns`) are auto-managed by their Services — no user action needed.
- **Containerd 1.7.x on Bottlerocket node:** Node `ip-10-0-x-x` runs containerd 1.7.31. This is fine for 1.33 but containerd 1.x support ends in Kubernetes 1.35. Plan to update before targeting 1.35.
- **Extended Support:** Cluster is on Extended Support ($365/month premium). Upgrading to 1.33 returns to standard pricing.

---

## Evidence

### Add-on Inventory

| Add-on | Type | Version | Status | Verdict | Source |
|--------|------|---------|--------|---------|--------|
| vpc-cni | Managed | v1.20.5-eksbuild.1 | ACTIVE | COMPATIBLE | EKS managed |
| kube-proxy | Managed | v1.32.13-eksbuild.5 | ACTIVE | COMPATIBLE | EKS managed |
| eks-pod-identity-agent | Managed | v1.3.10-eksbuild.3 | ACTIVE | COMPATIBLE | EKS managed |
| Karpenter | OSS (Helm) | 1.0.2 | Running | INCOMPATIBLE | karpenter.sh/docs/upgrading/compatibility |

### Node Group Summary

| Node | Type | Version | OS | Runtime | Skew vs 1.33 | Status |
|------|------|---------|-----|---------|------|--------|
| fargate-ip-10-0-x-x | Fargate | v1.32.13 | Minimal | containerd 2.2.3 | 1 | ✅ |
| fargate-ip-10-0-x-x | Fargate | v1.32.13 | Minimal | containerd 2.2.3 | 1 | ✅ |
| ip-10-0-x-x | Karpenter (c8g.xlarge) | v1.32.12 | Bottlerocket 1.61.0 | containerd 1.7.31 | 1 | ✅ |

**Karpenter NodePools:**

| NodePool | CPU Limit | Disruption | NodeClass |
|----------|-----------|------------|-----------|
| default | 1000 | WhenEmpty, 30s | EC2NodeClass/default |
| graviton-nodepool | 1000 | WhenEmptyOrUnderutilized, 60s | NodeClass/graviton-nodeclass |
| spot-nodepool | 1000 | WhenEmptyOrUnderutilized, 60s | NodeClass/spot-nodeclass |

**Subnet Capacity:**

| Subnet | AZ | CIDR | Available IPs | Status |
|--------|-----|------|---------------|--------|
| subnet-0aaaaaaaaaaaaaaaa | us-west-2a | 10.0.0.0/20 | 4090 | ✅ |
| subnet-0bbbbbbbbbbbbbbbb | us-west-2c | 10.0.32.0/20 | 4089 | ✅ |
| subnet-0cccccccccccccccc | us-west-2b | 10.0.16.0/20 | 4060 | ✅ |

### Workload Risk Summary

**Master Workload Table (non-system namespaces):**

| # | Name | Kind | NS | Replicas | Strategy | Probes | Requests | Findings |
|---|------|------|----|----------|----------|--------|----------|----------|
| 1 | inflate | Deployment | default | 3 | RollingUpdate | ❌ none | cpu only | Missing probes, missing memory request, no PDB |
| 2 | singleton-app | Deployment | default | 1 | RollingUpdate | ❌ none | ✅ cpu+mem | Single replica, missing probes |

**Risk Findings:**

| Finding | Severity | Workloads (by row #) | Count | Pts |
|---------|----------|---------------------|-------|-----|
| Single replica | HIGH | #2 | 1 | 3 |
| Missing readiness probes | MEDIUM | #1, #2 | 2 | 1 |
| Missing memory request | MEDIUM | #1 | 1 | 1 |
| Missing PDB (multi-replica) | MEDIUM | #1 | 1 | 1 |
| Drain-blocking PDB (singleton-pdb) | MEDIUM | #2 | 1 | 2 |
| **HIGH sub-total** | | | | 3 (cap 8) |
| **MEDIUM sub-total** | | | | 6 → capped 4 |
| **Category total** | | | | **7** (cap 10) |

### AWS Upgrade Insights

| Insight | Status | Description |
|---------|--------|-------------|
| EKS add-on version compatibility | ✅ PASSING | All add-on versions compatible with 1.33 |
| Cluster health issues | ✅ PASSING | No cluster health issues detected |
| Amazon Linux 2 compatibility | ✅ PASSING | No AL2 nodes detected |
| kube-proxy version skew | ✅ PASSING | kube-proxy versions match control plane |
| Kubelet version skew | ✅ PASSING | Node kubelet versions match control plane |

---

## Upgrade Plan

> **Do NOT proceed until the Karpenter blocker is resolved.**

### Pre-Upgrade Checklist

- [ ] **Upgrade Karpenter to >= 1.5** (hard blocker)
- [ ] Verify NodePool/EC2NodeClass CRDs are on v1 APIs after Karpenter upgrade
- [ ] Add readiness probes to inflate and singleton-app
- [ ] Add PDB for inflate deployment
- [ ] Consider scaling singleton-app to 2+ replicas
- [ ] Take etcd snapshot / backup

### Step 1: Upgrade Karpenter (MUST DO FIRST)

```bash
# Check current CRD API versions
kubectl get nodepools.karpenter.sh -o yaml | grep apiVersion
kubectl get ec2nodeclasses.karpenter.k8s.aws -o yaml | grep apiVersion

# Upgrade Karpenter (adjust to latest stable >= 1.5)
helm upgrade karpenter oci://public.ecr.aws/karpenter/karpenter \
  --namespace karpenter \
  --version 1.5.0 \
  --set clusterName=ex-karpenter-test \
  --set clusterEndpoint=$(aws eks describe-cluster --name ex-karpenter-test --query cluster.endpoint --output text --region us-west-2) \
  --wait

# Verify Karpenter is healthy
kubectl get pods -n karpenter
kubectl get nodepools.karpenter.sh
```

### Step 2: Update EKS Managed Add-ons (optional, already compatible)

```bash
# Check for latest compatible versions
aws eks describe-addon-versions --addon-name vpc-cni --kubernetes-version 1.33 --query 'addons[0].addonVersions[0].addonVersion' --region us-west-2
aws eks describe-addon-versions --addon-name kube-proxy --kubernetes-version 1.33 --query 'addons[0].addonVersions[0].addonVersion' --region us-west-2
aws eks describe-addon-versions --addon-name eks-pod-identity-agent --kubernetes-version 1.33 --query 'addons[0].addonVersions[0].addonVersion' --region us-west-2
```

### Step 3: Upgrade Control Plane

```bash
aws eks update-cluster-version \
  --name ex-karpenter-test \
  --kubernetes-version 1.33 \
  --region us-west-2
```

### Step 4: Monitor Upgrade Progress

```bash
# Get the update ID from the output of Step 3, then:
aws eks describe-update \
  --name ex-karpenter-test \
  --update-id <UPDATE_ID> \
  --region us-west-2

# Or watch cluster status
watch -n 30 'aws eks describe-cluster --name ex-karpenter-test --query "cluster.{status:status,version:version}" --output table --region us-west-2'
```

### Step 5: Update Node Groups (Karpenter-managed)

Karpenter nodes will be replaced automatically based on your NodePool `expireAfter` (720h) and disruption settings. To force immediate rotation:

```bash
# Option A: Trigger drift detection (Karpenter detects version mismatch and replaces nodes)
# This happens automatically after control plane upgrade

# Option B: Force immediate replacement
kubectl delete node <node-name>
```

### Step 6: Update Fargate Pods

Fargate pods must be recycled to pick up the new platform version:

```bash
# Delete and let the controller recreate them
kubectl rollout restart deployment -n <namespace> <deployment-name>
```

### Step 7: Verify

```bash
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running | grep -v Completed
aws eks describe-cluster --name ex-karpenter-test --query "cluster.version" --region us-west-2
```

---

## AWS Reference Links

- EKS Kubernetes Versions: https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html
- EKS Add-on Versions: https://docs.aws.amazon.com/eks/latest/userguide/managing-add-ons.html
- Karpenter Compatibility: https://karpenter.sh/docs/upgrading/compatibility/
- Karpenter Upgrade Guide: https://karpenter.sh/docs/upgrading/upgrade-guide/
- EKS Best Practices — Upgrades: https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html
- EKS Platform Versions: https://docs.aws.amazon.com/eks/latest/userguide/platform-versions.html
