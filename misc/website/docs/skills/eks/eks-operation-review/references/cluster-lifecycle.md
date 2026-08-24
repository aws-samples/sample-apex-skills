---
title: "Cluster Lifecycle & Upgrades"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/references/cluster-lifecycle.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-operation-review/references/cluster-lifecycle.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/references/cluster-lifecycle.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [eks-operation-review](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review), also maintained by the APEX team.
:::

# Cluster Lifecycle & Upgrades

## Purpose
Assess EKS cluster version currency, data plane alignment, upgrade readiness, add-on compatibility, and upgrade process maturity.

## EKS Version Support Status

> **Last verified:** 2026-08-09. Support status is determined primarily from the **live EKS API**; the dated table below is a fallback used only when the API is unavailable.

Determine support status from the live API first; fall back to the dated table only when the API cannot be reached. Do NOT guess or use training data.

**Primary (live) method — preferred:**
Run `aws eks describe-cluster-versions` to get the authoritative real-time list of EKS versions and each version's `versionStatus` (falling back to the deprecated `status` field) — one of STANDARD_SUPPORT / EXTENDED_SUPPORT / UNSUPPORTED. Define **latest** = the highest version whose status is `STANDARD_SUPPORT` in the API response.

**Fallback method — only when the live API is unavailable:**
Use the dated table below. In fallback mode, **latest** = the highest `STANDARD_SUPPORT` version *in this table* (not the true current latest), so ratings are relative to the table and may lag reality — note fallback mode in the finding.

> This fallback table was sourced from the EKS upgrade skill's version data on the "as of" date shown in the table header; it goes stale as new EKS versions ship and support windows advance — refresh it periodically against the [official EKS version calendar](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html). Prefer `aws eks describe-cluster-versions --include-all` (the `--include-all` flag also surfaces `UNSUPPORTED` versions) whenever the live API is reachable. If the API is unavailable and the cluster runs a version **not present** in this fallback table, do not guess from training data — classify by the table's bounds instead (this applies in fallback mode only; if the live API is reachable, the API's own support status governs and this fallback logic does not apply). A version **below the lowest table entry** (older than 1.30, the lowest version in this fallback table — note that 1.30 is itself now UNSUPPORTED, its extended support having ended July 23, 2026, so 1.31 is the oldest version still in extended support) is past extended-support end — rate 🔴 RED, since it is out of support, and note that it is below the fallback table and out of support. A version **newer than the highest table entry** (1.36) may be a brand-new release that the stale fallback table simply predates — do not rate it out of support. Rate it 🟢 GREEN via the out-of-range guard in check 1.1 and note that the version is newer than the fallback table (last verified 2026-08-09).

| Version | Standard Support Until | Extended Support Until | Status (as of 2026-08-09) |
|---------|----------------------|----------------------|----------------|
| 1.36 | August 2, 2027 | August 2, 2028 | ✅ STANDARD_SUPPORT (latest in table) |
| 1.35 | March 27, 2027 | March 27, 2028 | ✅ STANDARD_SUPPORT |
| 1.34 | December 2, 2026 | December 2, 2027 | ✅ STANDARD_SUPPORT |
| 1.33 | July 29, 2026 | July 29, 2027 | ⚠️ EXTENDED_SUPPORT (standard ended) |
| 1.32 | March 23, 2026 | March 23, 2027 | ⚠️ EXTENDED_SUPPORT (standard ended) |
| 1.31 | November 26, 2025 | November 26, 2026 | ⚠️ EXTENDED_SUPPORT (standard ended) |
| 1.30 | July 23, 2025 | July 23, 2026 | ⛔ UNSUPPORTED (extended support ended July 23, 2026) |

**CRITICAL:** The `upgradePolicy.supportType` field from the API is a CONFIGURATION PREFERENCE, not the current billing status. A cluster on a standard-support version with `supportType: EXTENDED` is still on standard support and NOT paying the extended premium. Always determine actual support status from `describe-cluster-versions` (or the fallback table), never from `supportType`.

## Checks to Execute

### 1.1 — Control Plane Version Currency

**What to check:**
- The cluster's current Kubernetes version and platform version
- The version's actual support status (STANDARD_SUPPORT / EXTENDED_SUPPORT / UNSUPPORTED)
- Report the actual support status, NOT the `supportType` API field

**How to check:**
1. Describe the cluster → get `version` and `platformVersion`
2. Run `aws eks describe-cluster-versions` → find the cluster's version and its `versionStatus` (falling back to the deprecated `status` field), and identify **latest** = the highest `STANDARD_SUPPORT` version. If the live API is unavailable, fall back to the dated table above and note fallback mode in the finding.
3. Report: version, standard/extended/unsupported status, and when the current support period ends

**Rating (evaluate RED first, then AMBER, then GREEN):**
- 🔴 RED: Version is on **extended support**, or **unsupported** (past its extended-support end date) — extended support incurs the cost premium below; unsupported means running with no support
- 🟡 AMBER: Version is on **standard support but older** — a standard version more than one minor behind the latest standard version
- 🟢 GREEN: Version is the **latest** standard-support version or **N-1** (one minor behind the latest standard version)
- ⬜ UNKNOWN: Cannot determine the version (should not happen with live access); OR the `describe-cluster-versions` call **succeeded but returned no versions (an empty list)** — this is NOT a 403 (do not treat an empty-but-successful response as access-denied, and do not read empty data as "version unsupported"). Prefer falling back to the dated table above (treat empty-but-successful as "live version data unavailable") and note fallback mode; if the table is also unavailable, rate this dimension UNKNOWN with the note "version support data unexpectedly empty from a successful describe-cluster-versions response." Floor-preserving: an empty-but-successful response never yields GREEN on its own.

**Version out-of-range guard (fallback mode only):** If using the fallback table and the cluster version is higher than the highest version in the table, rate GREEN and note: "Version 1.X is newer than the fallback table (last verified 2026-08-09); the live API was unavailable. Rated GREEN as latest. Refresh the table when convenient."

**Extended-support cost impact:** Extended support has historically cost ~$0.60/hr vs ~$0.10/hr for standard support. These rates are indicative and subject to change — verify against the current [Amazon EKS pricing page](https://aws.amazon.com/eks/pricing/) before quoting figures. Compute, do not estimate:
```
extra_cost_per_month = (extended_rate - standard_rate) × 730
total_extended_cost  = extended_rate × 730
# With the indicative rates above: extra = (0.60 - 0.10) × 730 = ~$365/month per cluster
# 730 = average hours per month (365 days × 24 hours ÷ 12 months)
```

**Key talking point:** At indicative rates, extended support adds roughly $365/month per cluster — verify against the EKS pricing page before quoting a figure.

---

### 1.2 — Data Plane Version Alignment

**What to check:**
- List all node groups and their Kubernetes versions
- Compare each node group version against the control plane version
- Check AMI type (AL2 vs AL2023 vs Bottlerocket)
- Check for Karpenter NodePools or EKS Auto Mode

**How to check:**
1. List node groups → describe each for version, AMI type, capacity type. **403 guard:** if listing or describing node groups returns 403/Forbidden → mark the node-group and AMI-type signals UNKNOWN; do NOT read a forbidden result as "no managed node groups" or "not AL2." An unconfirmed AMI type must not be assumed non-AL2, so the AL2 end-of-life AMBER cap cannot be silently skipped — report AMI type UNKNOWN rather than granting GREEN on the AMI dimension.
2. List nodes via Kubernetes API → get kubelet versions. **403 guard:** if this read returns 403/Forbidden → mark the version-skew signal UNKNOWN (a forbidden read is the auditor identity's own permission restriction, not a cluster state); do NOT route it to RED. A forbidden node-list marks ONLY the version-skew signal UNKNOWN — it does NOT by itself force the whole check UNKNOWN: a confirmed end-of-life AMI type from a successful describe-nodegroup (step 1) still forces at-least-AMBER (confirmed-floor), and the whole check goes UNKNOWN only when BOTH the version-skew signal AND the AMI-type signal are unavailable (see UNKNOWN band and the combo map). The RED "no visibility into node versions" arm applies ONLY when the node-list read SUCCEEDS but returns no parseable/usable version data (a genuine no-visibility state) — never when the read was forbidden.
3. Check for Karpenter NodePools (`nodepools.karpenter.sh`). If 404/NotFound (CRD not installed) → Karpenter is not deployed, rate based on other node management. If 403/Forbidden → mark Karpenter status UNKNOWN. **Note:** EKS Auto Mode is built on Karpenter and serves the `karpenter.sh` CRDs too, so the `nodepools.karpenter.sh` CRD being present does NOT by itself mean self-managed (open-source) Karpenter is deployed — distinguish Auto Mode via step 4.
4. Describe cluster → check `computeConfig.enabled` for Auto Mode (cluster-level signal). Auto Mode nodes also carry the label `eks.amazonaws.com/compute-type=auto`; use these to tell Auto Mode apart from self-managed Karpenter even though both serve the `nodepools.karpenter.sh` CRD.

**Rating:**
- 🟢 GREEN: All nodes within N-1 of control plane, using managed node groups/Karpenter/Auto Mode, AND the AMI-type signal was SUCCESSFULLY read and confirms no node runs an end-of-life AMI type (see AMBER). GREEN requires BOTH preconditions confirmed — an unconfirmable good signal never earns GREEN (see the AMI-UNKNOWN cap and the combo map)
- 🟡 AMBER: Nodes within two minors of the control plane but mixed versions, or self-managed nodes (exactly 2 minors behind lands here — still within the upstream kubelet N-3 skew policy); OR nodes running an end-of-life AMI type — AL2, whose EKS-optimized AMIs ended at Kubernetes 1.32 and whose OS support ended 2026-06-30 — which caps the rating at AMBER regardless of version skew (migrate to AL2023 or Bottlerocket), so an otherwise-GREEN cluster on AL2 AMIs lands here; OR the version-skew signal is GREEN-worthy (nodes successfully read, all within N-1) but the AMI-type signal is UNKNOWN because describe-nodegroup returned 403 — GREEN's AMI precondition is unconfirmed, so cap at **AMBER-with-note** ("versions current but AMI type could not be verified") and record the AMI uncertainty under Investigate Manually; this never *raises* a band (a confirmed >N-2 RED still requires a successful version read), it only caps an otherwise-GREEN down to AMBER
- 🔴 RED: Any node more than 2 minors behind the control plane, or a successful node-list read that returns no parseable version data for the nodes it lists (a genuine no-visibility state) (this >N-2 bound is a skill-defined operational standard — stricter than the upstream kubelet version-skew policy, which permits up to N-3). A 403/Forbidden on the node-list read does NOT satisfy this arm — that is UNKNOWN, not RED.
- ⬜ UNKNOWN: No nodes found (possible if cluster is new or uses Fargate only); OR **both** the version-skew signal AND the AMI-type signal are unavailable — i.e. the node-list read was forbidden (403) AND the AMI type could not be confirmed from a successful describe-nodegroup. A forbidden node-list alone does NOT force whole-check UNKNOWN when a successful describe-nodegroup confirmed the AMI type (that path caps at AMBER-with-note if AMI is clean, or AMBER if AMI is AL2/EOL — confirmed-floor). A permission restriction is never a RED. (The node-list-403 arm is retained as defense-in-depth even though pre-flight typically hard-stops on a failed node list; when it does fire it marks only the version-skew signal UNKNOWN, not the whole check.)
- **Evaluation order:** assess RED first, then AMBER, otherwise GREEN. Version-skew RED (any node >N-2, or a successful read that yields no parseable node versions) dominates and is evaluated before the AMI-type check, so an AL2 node that is also >N-2 behind stays RED; the AL2 end-of-life signal only caps at AMBER a cluster that would otherwise be GREEN. A forbidden (403) node-list read is not a RED — it marks only the version-skew signal UNKNOWN per the 403 guard in step 2. Keeps the bands exhaustive and non-overlapping.
- **Signal-combination map (version-skew × AMI-type → exactly one band; confirmed RED/AMBER survives a 403 on the other signal):**
  - version >N-2 (confirmed RED), AMI = *any* (AL2 / AL2023 / unreadable) → **RED** (version-skew RED dominates and survives an AMI-read 403 — confirmed-floor)
  - version N-1/current (confirmed), AMI = AL2/EOL (confirmed) → **AMBER** (AL2 end-of-life cap)
  - version N-1/current (confirmed), AMI = AL2023/Bottlerocket (confirmed clean) → **GREEN** (both preconditions confirmed)
  - version N-1/current (confirmed), AMI = unreadable (describe-nodegroup 403) → **AMBER-with-note** ("versions current but AMI type could not be verified"; GREEN's AMI precondition unconfirmed)
  - version unreadable (node-list 403), AMI = AL2/EOL (confirmed) → **AMBER** (confirmed EOL AMI forces at-least-AMBER even though version-skew is UNKNOWN — confirmed-floor)
  - version unreadable (node-list 403), AMI = AL2023/Bottlerocket (confirmed clean) → **AMBER-with-note** ("AMI type verified clean but node version skew could not be verified"; no unearned GREEN)
  - version unreadable (node-list 403), AMI = unreadable (describe-nodegroup 403) → **UNKNOWN** (both discriminators unavailable, nothing confirmed yields a color)

**Red flags:** AL2 OS is past EOL (2026-06-30) and EKS AL2 AMIs ended with Kubernetes 1.32 — migrate to AL2023 or Bottlerocket; self-managed nodes with no automated upgrade path.

---

### 1.3 — Upgrade Readiness & Deprecated API Detection

**What to check:**
- EKS Cluster Insights for upgrade blockers
- Presence of deprecated API usage
- PodSecurityPolicy resources (removed in K8s 1.25)

**How to check:**
1. Get EKS Insights → filter for UPGRADE_READINESS category
2. List any PodSecurityPolicy resources via Kubernetes API. If 404/NotFound or the API group is not served (expected on Kubernetes ≥1.25, where PSP was removed) → no PSPs present, not a finding; if 403/Forbidden → mark the PSP signal UNKNOWN rather than assuming absence.
3. Check for Helm releases in kube-system as supporting evidence for deprecated-API risk — Helm-managed workloads there may ship manifests targeting deprecated/removed API versions; treat any found as supporting evidence feeding the deprecated-API RED determination above (evidence only; the insight/deprecated-API signals in the bands govern the rating)

**Rating:**
- 🟢 GREEN: No critical insights AND the deprecated-API/PSP signals were CONFIRMED via successful reads (Insights read succeeded clean AND the PSP list was successfully read — an empty/404 result confirming no PSPs). GREEN requires the GREEN-precondition signals confirmed — if the PSP list returned 403/Forbidden (PSP signal UNKNOWN), GREEN is not awardable even when insights read clean (see the AMBER-with-note cap)
- 🟡 AMBER: WARNING-level insights present, OR **AMBER-with-note**: insights read clean but the PSP list returned 403/Forbidden so deprecated-API/PSP usage could not be fully verified — cap at AMBER with the note "no critical insights, but deprecated-API/PSP usage could not be fully verified" (GREEN's PSP precondition is unconfirmed) and record the uncertainty under Investigate Manually. This never *raises* a band — a confirmed ERROR-insight / deprecated-API RED still stands; it only caps an otherwise-GREEN down to AMBER
- 🔴 RED: ERROR insights, deprecated APIs actively in use. **Confirmed-floor:** a confirmed ERROR insight (or confirmed deprecated-API usage) keeps this RED even if a *different* signal read is forbidden — e.g. a 403 on the PSP list marks only the PSP signal UNKNOWN and never downgrades a confirmed ERROR-insight RED to UNKNOWN.
- ⬜ UNKNOWN: Insights API not accessible (the Insights read is the sole discriminator and it returned 403/Forbidden or is otherwise unreachable), and no other successfully-read signal (e.g. confirmed deprecated-API usage) already yields a color
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.
- **Scoring authority:** this check owns the EKS Cluster Insights / upgrade-readiness signal; check 10.3 defers here and is evidence-only. Note: step 1 filters to the UPGRADE_READINESS category, but 10.3 may defer insight evidence spanning ALL categories (PASSING/WARNING/ERROR); score any such deferred evidence with this check's generic bands (ERROR insight → RED, WARNING insight → AMBER) regardless of category, so no ERROR insight is dropped.

---

### 1.4 — Add-on Version Compatibility

**What to check:**
- List all EKS managed add-ons with versions and health
- Compare installed versions against latest compatible for the cluster version
- Check for self-managed add-ons in kube-system (Helm releases)

**How to check:**
1. List addons → describe each for version, status, health. **403 guard:** if listing add-ons returns 403/Forbidden → UNKNOWN (see band). If a per-add-on describe-addon returns 403/Forbidden → mark that add-on's health signal UNKNOWN and do NOT assume healthy — a forbidden health read must not silently skip the **health-issue** RED.
2. For each core add-on (vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver), compare installed vs latest compatible
3. Determine EBS usage (required before aws-ebs-csi-driver can be classified): list PersistentVolumes and PersistentVolumeClaims via the Kubernetes API and check for EBS-backed volumes — CSI provisioner `ebs.csi.aws.com`, in-tree provisioner `kubernetes.io/aws-ebs`, in-tree volume source `awsElasticBlockStore`, or a `gp2`/`gp3` StorageClass. **403 guard:** if this PV/PVC read returns 403/Forbidden (or otherwise cannot complete) → mark the EBS-usage signal UNKNOWN; do NOT read a forbidden/failed list as "no EBS PVs found." The favorable **absent-and-not-needed → N/A** classification for aws-ebs-csi-driver requires a SUCCESSFUL, empty PV/PVC read confirming no EBS-backed volumes exist. When EBS usage is UNKNOWN, an absent aws-ebs-csi-driver may NOT be classified absent-and-not-needed — treat it as **absent-and-needed** (→ AMBER) or report the aws-ebs-csi-driver state UNKNOWN, never N/A.

**Core add-on set:** vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver. The first three (vpc-cni, coredns, kube-proxy) are REQUIRED for normal cluster function; aws-ebs-csi-driver is CONDITIONALLY required — needed only when EBS-backed PersistentVolumes/PersistentVolumeClaims are in use. For each core add-on, classify its state as one of: **managed-current** (EKS Managed, latest or N-1 compatible), **managed-behind** (EKS Managed but older than N-1), **self-managed** (present as a Helm/self-managed release rather than an EKS Managed add-on), **absent-and-needed** (neither managed nor self-managed and the add-on is required — any of the three required add-ons, or aws-ebs-csi-driver when EBS PVs/PVCs exist), **absent-and-not-needed** (aws-ebs-csi-driver only, when a SUCCESSFUL PV/PVC read confirms no EBS-backed PVs/PVCs exist → N/A, not a finding; if the EBS-usage read was forbidden/failed and is therefore UNKNOWN, this favorable state does NOT apply), **health-issue** (DEGRADED/failed add-on status via describe-addon), or **health-unknown** (the add-on is present per ListAddons but its per-add-on describe-addon returned 403/Forbidden, so its version/health could not be read — the add-on's contribution is UNKNOWN; do NOT assume healthy).

**Rating:**
- 🟢 GREEN: Every core add-on is either **managed-current** or **absent-and-not-needed** (the latter applies only to aws-ebs-csi-driver with no EBS PVs/PVCs) AND every core add-on's health was CONFIRMED via a successful describe-addon (no **health-unknown** add-on). Equivalently: all required core add-ons are EKS Managed and on latest or N-1 with health confirmed, and any not-needed conditional add-on is legitimately absent. A **health-unknown** add-on (describe-addon 403) blocks overall GREEN — see the AMBER-with-note cap and the aggregation rule.
- 🟡 AMBER: At least one core add-on is **managed-behind**, **self-managed**, or **absent-and-needed** (a required add-on — vpc-cni/coredns/kube-proxy, or aws-ebs-csi-driver while EBS volumes are in use — is genuinely not installed), and no add-on has a health issue. A genuinely-absent required CNI add-on (vpc-cni) may also indicate a non-standard/third-party CNI — note that possibility rather than assuming misconfiguration. OR **AMBER-with-note (describe-addon 403)**: every determinable core add-on is **managed-current**/**absent-and-not-needed** (would otherwise be GREEN) but at least one core add-on is **health-unknown** (its per-add-on describe-addon returned 403) so its version/health could not be verified — cap at AMBER with the note "core add-ons look current but <add-on>'s version/health could not be verified" (can't award overall GREEN with an unverified core add-on) and record the uncertainty under Investigate Manually. This never *raises* a band — a confirmed health-issue RED, or a confirmed managed-behind/self-managed/absent-and-needed AMBER, on another add-on still sets the band via worst-of; the cap only lowers an otherwise-GREEN to AMBER.
- 🔴 RED: Any core add-on is in the **health-issue** state (DEGRADED/failed add-on status via describe-addon). RED is reserved for health issues. **Confirmed-floor:** a confirmed health-issue RED on one add-on is not downgraded by a 403 on a *different* add-on's describe/health read (that 403 marks only the other add-on's signal UNKNOWN) — the confirmed RED stands.
- ⬜ UNKNOWN: The ListAddons call itself returned 403/Forbidden (cannot enumerate add-ons at all), OR every core add-on resolved to **health-unknown** (each present add-on's describe-addon returned 403) with no determinable add-on left — i.e. the forbidden read is the sole discriminator and no successfully-read add-on already yields a color. A single add-on's describe-addon 403 does NOT force whole-check UNKNOWN when other add-ons are determinable (that path caps at AMBER-with-note per the health-unknown rule — confirmed floor).
- **State→band map (each state → exactly one outcome):** managed-current → GREEN · managed-behind → AMBER · self-managed → AMBER · absent-and-needed → AMBER · absent-and-not-needed → N/A for that add-on (no finding; does not block GREEN — requires a successful empty PV/PVC read) · health-issue → RED · **health-unknown → per-add-on UNKNOWN** (describe-addon 403; contribution undetermined — blocks overall GREEN, does not itself set a worse band). **EBS-usage UNKNOWN** (forbidden/failed PV/PVC read) with aws-ebs-csi-driver absent → NOT N/A: treat as absent-and-needed (AMBER) or mark that add-on UNKNOWN, so a forbidden read can never silently grant GREEN.
- **Aggregation rule (worst-of over DETERMINABLE add-ons, mirrors 10.2's UNKNOWN-dimension-blocks-GREEN):** rank per-add-on bands RED > AMBER > GREEN; managed-current/managed-behind/self-managed/absent-and-needed/health-issue are **determinable**, absent-and-not-needed is **N/A** (excluded), and **health-unknown is UNKNOWN** (a scored add-on whose 403-hidden health could be anything, including RED). (1) If at least one add-on is determinable, the overall band = the **worst determinable band**, with one guard: **a health-unknown add-on blocks overall GREEN** — so if the worst determinable band is GREEN but any core add-on is health-unknown, cap overall at **AMBER-with-note** (name the unverified add-on under Investigate Manually); a confirmed RED (health-issue) or AMBER (managed-behind/self-managed/absent-and-needed) determinable add-on still sets the overall via worst-of (a health-unknown never *lowers* an already-worse band — confirmed floor). Overall GREEN therefore requires every core add-on determinable AND (managed-current or absent-and-not-needed). (2) If NO add-on is determinable (every present add-on is health-unknown, others N/A), the overall check is **UNKNOWN**. This yields exactly one overall result for every {ListAddons-outcome × per-add-on-describe-outcome} combination.
- **Evaluation order:** assess RED first (any health issue); if not RED, assess AMBER (any managed-behind / self-managed / absent-and-needed); otherwise GREEN. Keeps the bands exhaustive and non-overlapping.
- **Scoring authority:** this check owns add-on version compatibility scoring; check 10.1 defers here and is evidence-only.

**Key talking point:** EKS does NOT auto-update add-ons when you upgrade the control plane. This is the #1 thing customers forget.

---

### 1.5 — Upgrade Process Maturity

**What to check (target cluster only):**
- Cluster tags for environment classification (dev, staging, prod)
- Evidence of IaC-managed upgrades (eksctl, CloudFormation, Terraform tags)

**How to check:**
1. Describe the target cluster → check tags for environment indicators (dev/staging/prod) AND IaC-provenance tags (same set as check 2.1: `terraform` / `managed-by` / `aws:cloudformation:stack-name` / `eksctl.cluster.k8s.io/*` / `aws:cdk:*`). **403 guard:** if the describe/tags read returns 403/Forbidden → UNKNOWN; do NOT treat a forbidden tag read as "no environment tag" (that would be a false AMBER). The "no environment tag" AMBER requires a SUCCESSFUL tags read that returns no environment-classification tag.

**Do NOT** list or describe other clusters in the account. Stay within the scope of the target cluster.

**Rating:**
- 🟢 GREEN: Cluster has an environment tag whose value is a clear dev/staging/prod classification
- 🟡 AMBER: An environment tag is present but its value is not a clear dev/staging/prod classification (ambiguous or non-standard value), OR environment intent is split across conflicting tag keys, OR no environment-classification tag is present at all. An absent environment tag is a governance/hygiene improvement opportunity — not a critical availability or security gap — so it rates AMBER, not RED.
- ⬜ UNKNOWN: The cluster tags cannot be read (describe/tags returns 403/Forbidden) — this is the sole decidable UNKNOWN trigger for 1.5
- **Evaluation order:** assess AMBER first (any of: ambiguous/non-standard environment value, conflicting environment tag keys, or no environment tag at all); otherwise GREEN. (1.5 has no RED band — no environment-tagging state rises to Critical; a forbidden tags read is UNKNOWN.)
- **Scoring authority:** this check owns environment-classification and upgrade-process-maturity scoring; the IaC-provenance tag signal (terraform/CloudFormation/eksctl/CDK) is owned by check 2.1 — 1.5 gathers those tags as evidence but defers their scoring there, so an untagged cluster is not double-penalized.

**Investigate manually:** Upgrade history cannot be determined from the API alone — confirm with the user. Do you have a documented upgrade runbook? Do you test upgrades on a non-prod cluster first? Can more than one person execute an upgrade?
