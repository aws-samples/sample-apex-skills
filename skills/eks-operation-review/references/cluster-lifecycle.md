# Cluster Lifecycle & Upgrades

## Purpose
Assess EKS cluster version currency, data plane alignment, upgrade readiness, add-on compatibility, and upgrade process maturity.

## EKS Version Support Calendar

> **Last verified:** 2026-04-24. This table can become stale. Before rating version currency, cross-check against the [official EKS version calendar](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html).

Use this table to determine the ACTUAL support status. Do NOT guess or use training data.

| Version | Standard Support Until | Extended Support Until | Current Status |
|---------|----------------------|----------------------|----------------|
| 1.35 | March 27, 2027 | March 27, 2028 | ✅ STANDARD (latest) |
| 1.34 | December 2, 2026 | December 2, 2027 | ✅ STANDARD |
| 1.33 | July 29, 2026 | July 29, 2027 | ✅ STANDARD |
| 1.32 | March 23, 2026 | March 23, 2027 | ✅ STANDARD |
| 1.31 | November 26, 2025 | November 26, 2026 | ⚠️ EXTENDED (standard ended) |
| 1.30 | July 23, 2025 | July 23, 2026 | ⚠️ EXTENDED (standard ended) |
| 1.29 | March 23, 2025 | March 23, 2026 | 🔴 EXTENDED (ending soon) |

**CRITICAL:** The `upgradePolicy.supportType` field from the API is a CONFIGURATION PREFERENCE, not the current billing status. A cluster on v1.35 with `supportType: EXTENDED` is still on standard support and NOT paying the extended premium. Always determine actual support status from the calendar above based on the cluster version.

## Checks to Execute

### 1.1 — Control Plane Version Currency

**What to check:**
- Describe the cluster to get the current Kubernetes version and platform version
- Look up the version in the calendar above to determine actual support status
- Report the actual support status, NOT the `supportType` API field

**How to check:**
1. Describe the cluster → get `version` and `platformVersion`
2. Match the version against the calendar table above
3. Report: version, standard/extended status, and when current support period ends

**Version out-of-range guard:** If the cluster version is higher than the highest version in this table (currently 1.35), rate GREEN — a newer version is by definition on standard support. Add a note: "Version 1.X is newer than the reference table (last verified YYYY-MM-DD). Rated GREEN as latest. Update the table when convenient."

**Rating:**
- 🟢 GREEN: On v1.35 or v1.34 (latest or N-1, standard support), OR version newer than table
- 🟡 AMBER: On v1.33 or v1.32 (standard support but older)
- 🔴 RED: On v1.31 or below (extended support — paying $0.60/hr vs $0.10/hr, 6x premium)
- ⬜ UNKNOWN: Cannot determine (should not happen with live access)

**Key talking point:** Extended support costs $0.60/hr vs $0.10/hr — that's ~$4,300/month extra per cluster.

---

### 1.2 — Data Plane Version Alignment

**What to check:**
- List all node groups and their Kubernetes versions
- Compare each node group version against the control plane version
- Check AMI type (AL2 vs AL2023 vs Bottlerocket)
- Check for Karpenter NodePools or EKS Auto Mode

**How to check:**
1. List node groups → describe each for version, AMI type, capacity type
2. List nodes via Kubernetes API → get kubelet versions
3. Check for Karpenter NodePools (`nodepools.karpenter.sh`). If 404/NotFound (CRD not installed) → Karpenter is not deployed, rate based on other node management. If 403/Forbidden → mark Karpenter status UNKNOWN.
4. Describe cluster → check `computeConfig` for Auto Mode

**Rating:**
- 🟢 GREEN: All nodes within N-1 of control plane, using managed node groups/Karpenter/Auto Mode
- 🟡 AMBER: Within skew policy but mixed versions, or self-managed nodes
- 🔴 RED: Any node beyond N-2 skew, or no visibility into node versions
- ⬜ UNKNOWN: No nodes found (possible if cluster is new or uses Fargate only)

**Red flags:** AL2 AMIs (approaching EOL), self-managed nodes with no automated upgrade path.

---

### 1.3 — Upgrade Readiness & Deprecated API Detection

**What to check:**
- EKS Cluster Insights for upgrade blockers
- Presence of deprecated API usage
- PodSecurityPolicy resources (removed in K8s 1.25)

**How to check:**
1. Get EKS Insights → filter for UPGRADE_READINESS category
2. List any PodSecurityPolicy resources via Kubernetes API
3. Check for Helm releases in kube-system (may use deprecated APIs)

**Rating:**
- 🟢 GREEN: No critical insights, no deprecated API usage detected
- 🟡 AMBER: WARNING-level insights, or no automated detection tooling
- �� RED: CRITICAL/ERROR insights, deprecated APIs actively in use
- ⬜ UNKNOWN: Insights API not accessible

---

### 1.4 — Add-on Version Compatibility

**What to check:**
- List all EKS managed add-ons with versions and health
- Compare installed versions against latest compatible for the cluster version
- Check for self-managed add-ons in kube-system (Helm releases)

**How to check:**
1. List addons → describe each for version, status, health
2. For each core add-on (vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver), compare installed vs latest compatible

**Rating:**
- 🟢 GREEN: All core add-ons are EKS Managed and on latest or N-1 compatible version
- 🟡 AMBER: Managed but behind, or mix of managed and self-managed
- 🔴 RED: Core add-ons self-managed with no version tracking, or health issues present
- ⬜ UNKNOWN: Cannot list add-ons

**Key talking point:** EKS does NOT auto-update add-ons when you upgrade the control plane. This is the #1 thing customers forget.

---

### 1.5 — Upgrade Process Maturity

**What to check (target cluster only):**
- Cluster tags for environment classification (dev, staging, prod)
- Evidence of IaC-managed upgrades (eksctl, CloudFormation, Terraform tags)

**How to check:**
1. Describe the target cluster → check tags for environment indicators

**Do NOT** list or describe other clusters in the account. Stay within the scope of the target cluster.

**Rating:**
- 🟢 GREEN: Cluster has environment tags, evidence of IaC management
- 🟡 AMBER: No environment tags, or unclear upgrade process
- 🔴 RED: No evidence of structured upgrade process
- ⬜ UNKNOWN: Cannot determine upgrade history from API alone — suggest user investigate

**Investigate manually:** Do you have a documented upgrade runbook? Do you test upgrades on a non-prod cluster first? Can more than one person execute an upgrade?
