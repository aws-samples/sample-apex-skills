---
title: "Storage Costs"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/references/storage-costs.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-cost-intelligence/references/storage-costs.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/references/storage-costs.md). Edit the source, not this page.
:::

# Storage Costs

> **Part of:** [eks-cost-intelligence](../)
> **Purpose:** Checks for gp2 PersistentVolumes (flag for gp3 migration with 20% cost reduction), unbound/unmounted PVCs, over-provisioned volumes (used vs provisioned capacity), and EFS Intelligent-Tiering/lifecycle policies

---

## Overview

Storage costs is a mid-weight dimension (15 points max deduction). It evaluates whether the cluster's persistent storage is cost-efficient by detecting outdated storage classes, unused volumes, over-provisioned capacity, and missing lifecycle optimizations.

Storage waste is often overlooked because volumes persist independently of workloads. A deleted Deployment leaves its PVC behind, and EBS volumes continue billing even when no pod mounts them. The gp2-to-gp3 migration alone offers a guaranteed 20% cost reduction with zero performance trade-offs for most workloads.

### Checks Summary

| # | Check | Default Threshold | Severity Logic |
|---|-------|-------------------|----------------|
| 1 | gp2 PersistentVolumes (gp3 migration) | Any gp2 volume | MEDIUM (per Req 8.5) |
| 2 | Unbound/unmounted PVCs | Bound but not mounted by any running pod | By waste $ |
| 3 | Over-provisioned volumes | Used < 50% of provisioned AND > 20 GiB | By waste $ |
| 4 | EFS Intelligent-Tiering / lifecycle policies | EFS without lifecycle config | MEDIUM |

---

## Pre-requisites

These checks require:
- **kubectl access** to the cluster (for PVC/PV specs, pod volume mounts, StorageClass definitions)
- **AWS CLI access** for `ec2:DescribeVolumes` (EBS volume details and metrics)
- **Optional:** CloudWatch metrics for `VolumeReadBytes`, `VolumeWriteBytes`, and kubelet volume stats (improves utilization accuracy for Check 3)
- **Optional:** `elasticfilesystem:DescribeFileSystems`, `elasticfilesystem:DescribeLifecycleConfiguration` (for EFS checks)

Checks 1 and 2 require only Kubernetes API access. Check 3 benefits from CloudWatch metrics. Check 4 requires EFS API access.

---


## Check 1: gp2 PersistentVolumes — Flag for gp3 Migration

### What it detects

PersistentVolumes (PVs) and PersistentVolumeClaims (PVCs) using the `gp2` storage class, where migrating to `gp3` provides an immediate 20% cost reduction with equal or better performance (gp3 includes 3,000 IOPS and 125 MiB/s baseline at no extra cost).

### Cost comparison

| Storage Class | Cost per GiB/month | Baseline IOPS | Baseline Throughput |
|---------------|-------------------|---------------|---------------------|
| gp2 | $0.10 | 3 IOPS/GiB (min 100) | 128–250 MiB/s |
| gp3 | $0.08 | 3,000 IOPS (included) | 125 MiB/s (included) |
| **Savings** | **$0.02/GiB/month (20%)** | Better for < 1TB | Comparable |

### Data collection

Use the Kubernetes API to list PersistentVolumeClaims across all namespaces. Filter for storageClassName == "gp2" or null (which defaults to the cluster's default StorageClass). Also list StorageClasses to identify the default and check if a gp3 class exists. Extract capacity from spec.resources.requests.storage.

Use the EC2 DescribeVolumes API filtered by the cluster tag (`kubernetes.io/cluster/<cluster>=owned`) to verify volume types and get actual sizes. Count gp2 vs gp3 volumes for the cluster.

### Analysis logic

```
gp2_pvcs = []
total_gp2_gb = 0

For each PVC in all non-system namespaces:
  If storageClassName == "gp2" OR (storageClassName is null AND default SC is gp2):
    gp2_pvcs.append(pvc)
    total_gp2_gb += pvc.capacity_gb

If len(gp2_pvcs) > 0:
  monthly_waste = total_gp2_gb * 0.02  # $0.02/GiB savings
  monthly_savings = monthly_waste       # Full savings achievable
  → Generate finding with severity = MEDIUM (per Req 8.5)
```

### Severity classification

Per Requirement 8.5, gp2 volumes always generate a **MEDIUM** severity finding regardless of dollar amount. This is because:
- The migration is low-effort and low-risk
- gp3 is strictly better for most workloads (more baseline IOPS)
- The 20% savings is guaranteed

| Condition | Severity |
|-----------|----------|
| Any gp2 volumes detected | MEDIUM (per Req 8.5) |
| gp2 waste > $200/month | Escalate to HIGH |
| gp2 waste > $500/month | Escalate to CRITICAL |

### Remediation

```yaml
# Step 1: Create a gp3 StorageClass (if not already present)
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

```bash
# Step 2: Remove default annotation from gp2 StorageClass
kubectl annotate storageclass gp2 \
  storageclass.kubernetes.io/is-default-class-

# Step 3: For existing volumes — snapshot and restore approach
# (EBS volumes cannot be converted in-place from gp2 to gp3 via K8s)
aws ec2 create-snapshot --volume-id <vol-id> --description "gp2-to-gp3 migration"
aws ec2 create-volume --snapshot-id <snap-id> --volume-type gp3 \
  --availability-zone <az> --size <size>

# Step 4: For new PVCs — they will automatically use gp3 (new default)
```

---


## Check 2: Unbound/Unmounted PVCs

### What it detects

PersistentVolumeClaims that are in `Bound` state (an EBS volume exists and is being billed) but are not mounted by any running pod. This includes:
- PVCs left behind after a Deployment/StatefulSet was deleted
- PVCs from scaled-down StatefulSets (e.g., replicas reduced from 5 to 3, leaving 2 orphaned PVCs)
- PVCs in `Released` state (PV reclaim policy retained the volume)

### Data collection

Use the Kubernetes API to list all PersistentVolumeClaims and all running Pods. Cross-reference spec.volumes[].persistentVolumeClaim.claimName across all running pods to build a set of mounted PVCs. Identify PVCs in Bound state that are not in the mounted set.

### Analysis logic

```
mounted_pvcs = set()
For each running pod:
  For each volume in pod.spec.volumes:
    If volume.persistentVolumeClaim:
      mounted_pvcs.add(f"{pod.namespace}/{volume.persistentVolumeClaim.claimName}")

unmounted_pvcs = []
For each PVC where status.phase == "Bound":
  pvc_key = f"{pvc.namespace}/{pvc.name}"
  If pvc_key NOT in mounted_pvcs:
    unmounted_pvcs.append(pvc)

For each unmounted PVC:
  storage_rate = lookup_rate(pvc.storageClassName)  # $0.08 for gp3, $0.10 for gp2
  capacity_gb = parse_storage(pvc.spec.resources.requests.storage)
  monthly_waste = capacity_gb * storage_rate
  monthly_savings = monthly_waste  # Full cost recoverable by deleting PVC
  → Generate finding
```

### Severity classification

| Monthly Waste | Severity |
|---------------|----------|
| > $500 (aggregate unmounted) | CRITICAL |
| $200–$500 | HIGH |
| $50–$200 | MEDIUM |
| < $50 | LOW |

### Remediation

```bash
# Verify the PVC is truly unused (check for Jobs, CronJobs that may mount it periodically)
kubectl get jobs,cronjobs -n <namespace> -o json | \
  jq -r '.items[].spec.template.spec.volumes[]? | 
    select(.persistentVolumeClaim.claimName == "<pvc-name>") | 
    "Referenced by: \(.)"'

# If confirmed unused — delete the PVC (this also deletes the EBS volume if reclaimPolicy=Delete)
kubectl delete pvc <pvc-name> -n <namespace>

# If reclaimPolicy is Retain — also clean up the PV and EBS volume manually
kubectl get pv <pv-name> -o jsonpath='{.spec.csi.volumeHandle}'
# Returns vol-xxxxx — verify and delete via AWS CLI if appropriate
```

> **Caution:** Always verify that no CronJob, Job, or batch workload periodically mounts the PVC before deletion. Check events and recent pod history.

---


## Check 3: Over-Provisioned Volumes

### What it detects

PersistentVolumes where the actual used capacity is significantly below the provisioned capacity. Since EBS volumes are billed by provisioned size (not used space), over-provisioned volumes represent direct waste.

### Detection criteria

Flag a volume as over-provisioned if:
- `waste_ratio > 50%` (used capacity is less than half of provisioned)
- `provisioned_gb > 20 GiB` (ignore small volumes where absolute waste is minimal)

### Data collection

Use the Kubernetes API kubelet stats endpoint (`/api/v1/nodes/<node>/proxy/stats/summary`) to get volume usage statistics including capacityBytes, usedBytes, and availableBytes per PVC. Aggregate across all nodes to build a utilization map.

Alternatively, use the CloudWatch GetMetricData API for EBS VolumeReadBytes/VolumeWriteBytes to assess I/O activity. Map PVCs to EBS volume IDs via PersistentVolume spec.csi.volumeHandle.

> **Note:** CloudWatch does not directly expose "bytes used on filesystem" for EBS. The most reliable source for filesystem usage is kubelet volume stats (above) or a monitoring agent (Prometheus node-exporter with filesystem collector).

If Prometheus is available, query `kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes` to identify volumes with usage below 50% of provisioned capacity.

### Analysis logic

```
For each mounted PVC with available usage data:
  provisioned_gb = parse_storage(pvc.spec.resources.requests.storage)
  used_gb = volume_stats.used_bytes / (1024^3)
  
  waste_ratio = (provisioned_gb - used_gb) / provisioned_gb

  If waste_ratio > 0.50 AND provisioned_gb > 20:
    wasted_gb = provisioned_gb - used_gb
    storage_rate = lookup_rate(pvc.storageClassName)
    monthly_waste = wasted_gb * storage_rate

    # Right-size target: 2× actual usage (safety buffer) or minimum 20 GiB
    right_sized_gb = max(used_gb * 2, 20)
    monthly_savings = (provisioned_gb - right_sized_gb) * storage_rate
    → Generate finding
```

### Severity classification

| Monthly Waste | Severity |
|---------------|----------|
| > $500 | CRITICAL |
| $200–$500 | HIGH |
| $50–$200 | MEDIUM |
| < $50 | LOW |

### Graceful degradation

If kubelet volume stats and Prometheus are both unavailable:
- Mark Check 3 as **SKIPPED** with reason: "No volume utilization data available"
- Report: "Cannot assess volume utilization without kubelet stats or Prometheus. Install node-exporter or enable kubelet volume stats to enable this check."
- Checks 1, 2, and 4 still proceed (they don't require utilization data)

### Remediation

```bash
# EBS volumes cannot be shrunk in-place. Migration path:
# 1. Snapshot the volume
# 2. Create a smaller volume from snapshot (or new volume + data copy)
# 3. Update PV/PVC to point to new volume

# Step 1: Identify the EBS volume
kubectl get pv <pv-name> -o jsonpath='{.spec.csi.volumeHandle}'

# Step 2: Create snapshot
aws ec2 create-snapshot --volume-id <vol-id> \
  --description "Right-sizing: <namespace>/<pvc-name>"

# Step 3: Create smaller volume
aws ec2 create-volume \
  --snapshot-id <snap-id> \
  --volume-type gp3 \
  --size <right_sized_gb> \
  --availability-zone <az>

# Alternative: For workloads that can tolerate downtime, use volume expansion
# (only works for INCREASING size — not shrinking)
# For shrinking, consider application-level data migration (pg_dump, etc.)
```

> **Note:** EBS volumes can only be expanded, not shrunk. Right-sizing over-provisioned volumes requires a migration strategy (snapshot + restore to smaller volume, or application-level data migration). Report this as **Medium effort**.

---


## Check 4: EFS Intelligent-Tiering / Lifecycle Policies

### What it detects

Amazon EFS file systems used by the cluster that do not have Intelligent-Tiering or lifecycle policies configured. Without lifecycle policies, all data remains in the Standard storage class ($0.30/GiB/month) even if rarely accessed, when it could be automatically moved to Infrequent Access ($0.016/GiB/month) — a 94% cost reduction for cold data.

### EFS pricing reference

| Storage Class | Cost per GiB/month | Access Cost |
|---------------|-------------------|-------------|
| EFS Standard | $0.30 | None |
| EFS Infrequent Access (IA) | $0.016 | $0.01/GiB read |
| EFS Archive | $0.008 | $0.03/GiB read |

### Data collection

Use the Kubernetes API to list PersistentVolumes with CSI driver `efs.csi.aws.com`. Extract the filesystem ID from the volume handle (spec.csi.volumeHandle, split on "::" taking the first element).

Use the EFS DescribeFileSystems API to get filesystem details including size. Use the EFS DescribeLifecycleConfiguration API to check if Intelligent-Tiering lifecycle policies (TransitionToIA, TransitionToArchive, TransitionToPrimaryStorageClass) are configured.

### Analysis logic

```
efs_filesystems = set()

# Discover EFS file systems used by the cluster
For each PV with csi.driver == "efs.csi.aws.com":
  fs_id = pv.spec.csi.volumeHandle.split("::")[0]
  efs_filesystems.add(fs_id)

For each fs_id in efs_filesystems:
  lifecycle_config = aws efs describe-lifecycle-configuration(fs_id)
  
  If lifecycle_config.LifecyclePolicies is empty:
    # No lifecycle policy — all data stays in Standard tier
    fs_details = aws efs describe-file-systems(fs_id)
    total_gb = fs_details.SizeInBytes.Value / (1024^3)
    
    # Estimate savings: assume 60% of data is infrequently accessed
    ia_eligible_gb = total_gb * 0.60
    current_cost = ia_eligible_gb * 0.30  # Standard rate
    optimized_cost = ia_eligible_gb * 0.016  # IA rate
    monthly_savings = current_cost - optimized_cost
    
    → Generate finding (severity = MEDIUM)
  
  Elif "TransitionToIA" in lifecycle_config but "TransitionToArchive" not present:
    # Partial optimization — could add Archive tier
    → Generate LOW severity finding (informational)
  
  Else:
    # Lifecycle policies configured — no finding
    pass
```

### Severity classification

| Condition | Severity |
|-----------|----------|
| No lifecycle policy AND EFS > 100 GiB | MEDIUM |
| No lifecycle policy AND EFS > 500 GiB | HIGH |
| No lifecycle policy AND EFS > 2 TiB | CRITICAL |
| Lifecycle policy exists but no Archive tier | LOW |

### Remediation

```bash
# Enable Intelligent-Tiering lifecycle policy on EFS
aws efs put-lifecycle-configuration \
  --file-system-id <fs-id> \
  --lifecycle-policies \
    '[
      {"TransitionToIA": "AFTER_30_DAYS"},
      {"TransitionToArchive": "AFTER_90_DAYS"},
      {"TransitionToPrimaryStorageClass": "AFTER_1_ACCESS"}
    ]'

# Verify the configuration
aws efs describe-lifecycle-configuration --file-system-id <fs-id>
```

```terraform
# Terraform equivalent
resource "aws_efs_file_system" "example" {
  # ... existing config ...

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  lifecycle_policy {
    transition_to_archive = "AFTER_90_DAYS"
  }

  lifecycle_policy {
    transition_to_primary_storage_class = "AFTER_1_ACCESS"
  }
}
```

> **Note:** Enabling lifecycle policies is non-disruptive and takes effect immediately for new file access patterns. Data transitions happen automatically in the background. There is no performance impact for Standard-tier data; IA/Archive reads incur a small per-GiB access charge ($0.01/GiB for IA, $0.03/GiB for Archive).

---


## Scoring Contribution

The storage costs dimension has a **maximum deduction of 15 points**.

### Deduction calculation

```
deduction = 0

For each finding in this dimension:
  If severity == CRITICAL: deduction += 15 × 0.6 = 9.0
  If severity == HIGH:     deduction += 15 × 0.3 = 4.5
  If severity == MEDIUM:   deduction += 15 × 0.15 = 2.25
  If severity == LOW:      deduction += 15 × 0.05 = 0.75

actual_deduction = min(deduction, 15)  # Cap at maximum
```

### Dimension status

| Condition | Status |
|-----------|--------|
| All checks completed | ASSESSED |
| Check 3 skipped (no volume stats) | ASSESSED (with note) |
| Check 4 skipped (no EFS in cluster) | ASSESSED (EFS check not applicable) |
| All checks skipped (no kubectl access) | SKIPPED |

If the dimension is fully SKIPPED, it contributes **zero deduction** and is excluded from the score denominator.

---

## Decision Tree

```
START
  │
  ├─ Get all PVCs and StorageClasses
  │   │
  │   ├─ Any gp2 PVCs or gp2 default StorageClass?
  │   │   ├─ YES → Run Check 1 (gp2 migration)
  │   │   └─ NO  → Skip Check 1 (no gp2 detected)
  │   │
  │   ├─ Any bound PVCs?
  │   │   ├─ YES → Run Check 2 (unmounted PVC detection)
  │   │   └─ NO  → Skip Check 2 (no PVCs in cluster)
  │   │
  │   ├─ Volume utilization data available? (kubelet stats OR Prometheus)
  │   │   ├─ YES → Run Check 3 (over-provisioned volumes)
  │   │   └─ NO  → Mark Check 3 as SKIPPED
  │   │
  │   └─ Any EFS-backed PVs?
  │       ├─ YES → Run Check 4 (EFS lifecycle policies)
  │       └─ NO  → Skip Check 4 (no EFS in cluster)
  │
  └─ Aggregate findings → Calculate dimension deduction (capped at 15)
```

---

## Worked Example (Full Dimension)

```
Cluster: production-us-east-1 (45 PVCs total)

Check 1 — gp2 Migration:
  Found: 12 PVCs using gp2, totaling 850 GiB
  monthly_waste = 850 × $0.02 = $17.00/month
  severity = MEDIUM (per Req 8.5)
  effort = Low

Check 2 — Unmounted PVCs:
  Found: 3 PVCs bound but not mounted by any running pod
    - logging/elasticsearch-data-2 (200 GiB, gp3) → $16.00/month
    - staging/redis-backup (50 GiB, gp3) → $4.00/month
    - default/test-data (100 GiB, gp2) → $10.00/month
  total_monthly_waste = $30.00/month
  severity = LOW (< $50 aggregate)
  effort = Low

Check 3 — Over-Provisioned Volumes:
  Found: 2 volumes with > 50% waste ratio
    - analytics/clickstream-data (500 GiB provisioned, 45 GiB used) → $32.80/month savings
    - ml/training-cache (200 GiB provisioned, 30 GiB used) → $11.20/month savings
  total_monthly_savings = $44.00/month
  severity = LOW (< $50 aggregate)
  effort = Medium

Check 4 — EFS Lifecycle:
  Found: 1 EFS file system (fs-0abc123) without lifecycle policy
    - Total size: 250 GiB
    - Estimated IA-eligible: 150 GiB (60%)
    - Current cost for eligible data: 150 × $0.30 = $45.00/month
    - Optimized cost: 150 × $0.016 = $2.40/month
    - monthly_savings = $42.60/month
  severity = MEDIUM
  effort = Low

Summary:
  Total findings: 4
  Total monthly waste: $123.60
  Total monthly savings: $133.40
  Severities: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 2 LOW

Scoring:
  deduction = (2 × 2.25) + (2 × 0.75) = 4.5 + 1.5 = 6.0
  actual_deduction = min(6.0, 15) = 6.0

  Dimension score contribution: -6.0 points
```

---

## Notes

- gp2→gp3 migration is the single highest-ROI storage optimization (20% savings, zero risk, low effort)
- EBS volumes are billed by provisioned size, not used space — over-provisioning is direct waste
- EFS lifecycle policies are non-disruptive to enable and provide immediate cost benefits for cold data
- Always verify unmounted PVCs are not used by CronJobs or batch workloads before recommending deletion
- Volume shrinking (Check 3 remediation) requires snapshot + restore — cannot be done in-place for EBS
- All prices reference us-east-1 rates; adjust for region-specific pricing in the report
