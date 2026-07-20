# Report Generation

## Purpose
After all assessment checks are complete, calculate the readiness score and generate the upgrade assessment report.

## Step 1: Calculate Readiness Score

You MUST follow this algorithm exactly. Do NOT interpret loosely. Every rule below is deterministic.

### 1.1 — Scoring Algorithm (Pseudocode)

```
score = 100

# --- Category 1: Breaking Changes (max deduction: 25) ---
# COUNTING UNIT: each distinct breaking change TYPE that affects at least one resource.
# Example: "FlowSchema v1beta2 removed" = 1 item (even if 17 FlowSchema resources use it).
# Example: "PSP removed" = 1 item (even if 5 PSPs exist).
breaking_changes_deduction = 0
# EXCLUSION: skip breaking-change types with a scoring home in another category —
# containerd 1.x is scored under Category 3 (Node Readiness), not here. Parity with
# the Category 9 anonymous-auth exclusion below. Do NOT double-count.
for each breaking_change_type found in cluster:   # excluding types homed elsewhere (containerd -> Cat 3)
    if severity == HIGH:   breaking_changes_deduction += 10
    if severity == MEDIUM: breaking_changes_deduction += 4
    if severity == LOW:    breaking_changes_deduction += 2
breaking_changes_deduction = min(breaking_changes_deduction, 25)

# --- Category 2: Deprecated APIs (max deduction: 20) ---
# COUNTING UNIT: each distinct API path (e.g., flowschemas and prioritylevelconfigurations
# are 2 separate API paths even though they share the same API group).
# Count API paths, NOT individual resources using that path.
#
# An API path is "found in cluster" if surfaced by EITHER Step 2a (live object
# apiVersion) OR Step 2b (any entry in metadata.managedFields[].apiVersion) in
# references/deprecated-apis.md. A path is counted ONCE regardless of step.
#
# EXCLUSION (deprecated-apis.md Step 3b): a FlowSchema / PriorityLevelConfiguration
# counts ONLY if a user tool (kubectl/helm/argocd/flux/etc.) wrote a removed version
# in managedFields — writer identity is the only per-object signal. Objects whose
# only removed-version trace comes from internal APF controllers (managers named
# api-priority-and-fairness-config-* or eks-internal) are false positives and do NOT
# count. (eks-internal: exact manager string unverified vs public AWS docs as of
# 2026-07; AWS documents "manager: eks" — kept conservatively.) An API path is counted
# only if at least one object on it has a user-tool writer of a removed version;
# otherwise the path contributes 0 pts (report it under Informational Findings instead).
deprecated_apis_deduction = 0
deprecated_still_served_subtotal = 0
for each deprecated_api_path found in cluster:   # excluding system-written objects per Step 3b
    if removed_in_target_version:    deprecated_apis_deduction += 5
    if deprecated_but_still_served:  deprecated_still_served_subtotal += 1
# SUB-CAP: deprecated-but-still-served paths cap at 5 pts (the "(max 5)" in
# deprecated-apis.md Score Impact); removed-in-target paths have no sub-cap.
deprecated_apis_deduction += min(deprecated_still_served_subtotal, 5)
deprecated_apis_deduction = min(deprecated_apis_deduction, 20)

# --- Category 3: Node Readiness (max deduction: 20) ---
# Includes version skew, subnet IP capacity, containerd runtime, AND self-managed nodes.
# COUNTING UNIT: each distinct kubelet minor version (skew) + each subnet (IP check)
# + containerd runtime + self-managed-nodes presence (binary).
# SKEW ITERATION UNIT: distinct kubelet minor versions across ALL nodes — the union
# of managed node group versions AND every node's status.nodeInfo.kubeletVersion.
# Karpenter-provisioned and self-managed nodes have no node group; iterating node
# groups alone lets them escape both the deduction and hard blocker #1.
node_skew_deduction = 0
for each distinct_kubelet_minor_version across all nodes (MNG union nodeInfo):
    skew = target_minor_version - kubelet_minor_version
    if skew > 3:  node_skew_deduction += 20   # blocker — immediately caps (kubelet skew policy is N-3)
    if skew == 3: node_skew_deduction += 5    # warning — at max supported skew
# Composition rule: the +2 per-low-subnet warning ALWAYS applies (per subnet, below); the
# +5 collective hard blocker is ADDITIONAL and applies only when collective insufficiency holds.
for each subnet in cluster_subnets:
    if subnet.available_ips < 5:     node_skew_deduction += 2   # single low subnet — warning (always applies)
    elif subnet.available_ips <= 15: node_skew_deduction += 2   # warning
# Hard blocker ONLY when the cluster subnets COLLECTIVELY cannot place the control-plane
# ENIs (placement insufficiency) — a single low subnet among healthy subnets is a
# warning, not a blocker. Definition:
#   candidate_subnets_collectively_cannot_place_enis
#     = sum(AvailableIpAddressCount) across ALL cluster subnets < 5
# (e.g. subnets of 3 + 12 IPs → sum 15 ≥ 5 → NO blocker; the 3-IP subnet is a +2 warning only.)
if candidate_subnets_collectively_cannot_place_enis:
    node_skew_deduction += 5   # hard blocker (collective/placement insufficiency), in addition to any +2 warnings
# Self-managed nodes (node-readiness.md 5.4 — no automated upgrade path). SCORING
# HOME: Category 3. Binary: deduct once if any self-managed nodes are present.
if any self_managed_nodes_present:
    node_skew_deduction += 3
# Containerd 1.x runtime (see node-readiness.md 5.3 for node-type classification).
# SCORING HOME: containerd 1.x is scored HERE (Category 3), not under Breaking
# Changes (Category 1) — one home only, do not double-count:
if any node on containerd 1.x:
    if target >= 1.36 and any such node is self-managed/custom-AMI:
        node_skew_deduction += 5   # HIGH severity, NOT a score-cap blocker (outside containerd's tested matrix; managed nodes exempt)
    else:
        node_skew_deduction += 2   # warning (pre-1.36, or managed node that auto-upgrades)
node_skew_deduction = min(node_skew_deduction, 20)

# --- Category 4: Add-on Compatibility (max deduction: 15) ---
# COUNTING UNIT: each add-on (by name) + each unidentified workload.
# CLASSIFICATION RULES:
#   - "critical add-on" = vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver,
#     PLUS any non-AWS CNI installed in place of vpc-cni (Cilium, Calico) — an
#     INCOMPATIBLE cluster CNI must never score READY
#   - "optional add-on" = all other managed add-ons and identified OSS add-ons
#   - INCOMPATIBLE = installed version is NOT in the target's compatible set
#     (describe-addon-versions for the target returns no entry for it)
#   - Status DEGRADED or FAILED with correct version = treat as critical/optional
#     incompatible (same deduction as version incompatibility)
#   - Status ACTIVE but version behind = "update recommended"
#   - UNKNOWN_VERIFIABLE = identified but upstream compat source unreachable/ambiguous
#   - UNKNOWN_UNIDENTIFIED = workload looks like an add-on but couldn't be identified
#   - SKEW_WARNING = kube-proxy more than 3 minors behind the target (beyond the
#     version-skew policy) while still in the compatible set — a Category 4 warning,
#     NOT the same 2 pts as UNKNOWN_VERIFIABLE (they are separate rules that can
#     both apply to different add-ons)
#   - PRECEDENCE (most-specific-wins): a kube-proxy that is both "behind" and >3 minors
#     behind is assigned SKEW_WARNING (+2), which supersedes UPDATE_RECOMMENDED (+1);
#     INCOMPATIBLE supersedes both. One verdict per add-on.
#
# CRITICAL/OPTIONAL SPLIT (must match the bright-line table in
# addon-compatibility.md): a CRITICAL add-on INCOMPATIBLE = +5 AND hard blocker #3
# (caps score at 59); an OPTIONAL add-on INCOMPATIBLE = +3 with NO cap.
addon_deduction = 0
for each addon:
    if addon.verdict == "INCOMPATIBLE" or addon.status in [DEGRADED, FAILED]:
        if addon.name in [vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver, cilium, calico]:
            addon_deduction += 5   # critical add-on (incl. non-AWS CNIs) — also hard blocker #3/#4
        else:
            addon_deduction += 3   # optional add-on — points only, NO cap
    elif addon.verdict == "SKEW_WARNING":
        addon_deduction += 2       # kube-proxy >3 minors behind target (skew beyond policy)
    elif addon.verdict == "UNKNOWN_VERIFIABLE":
        addon_deduction += 2       # identified, compatibility unverified
    elif addon.verdict == "UPDATE_RECOMMENDED":
        addon_deduction += 1       # version behind but compatible
for each unidentified_workload:
    addon_deduction += 2           # UNKNOWN_UNIDENTIFIED
addon_deduction = min(addon_deduction, 15)

# --- Category 5: Karpenter (max deduction: 10) ---
# COUNTING UNIT: installed-and-incompatible (10), installed-but-version-unknown (2),
# or not-applicable (0). Karpenter is NOT an EKS managed add-on, so it is scored HERE,
# not in the Category 4 add-on loop. This is the ONE executable home for the
# unknown-version UNKNOWN_VERIFIABLE (2 pts) verdict — do not also score it in Cat 4.
karpenter_deduction = 0
if karpenter_installed:
    if karpenter_version_incompatible_with_target:
        karpenter_deduction = 10   # INCOMPATIBLE (hard blocker, see below)
    elif karpenter_version_unknown_or_unidentifiable:
        karpenter_deduction = 2    # UNKNOWN_VERIFIABLE — version could not be verified

# --- Category 6: Workload Risks (max deduction: 10) ---
# COUNTING UNIT: each individual Deployment/StatefulSet/DaemonSet affected.
# Only count workloads in non-system namespaces (exclude: kube-system, kube-public,
# kube-node-lease, karpenter, amazon-cloudwatch, amazon-guardduty, aws-observability).
# A single workload can trigger MULTIPLE risk types — count each risk separately.
#
# HIGH-severity risks (3 pts each, sub-cap 8 pts):
#   - Deployment with replicas == 1
#   - Deployment with strategy.type == Recreate
#
# MEDIUM-severity risks (1 pt each unless noted, sub-cap 4 pts):
#   - Deployment missing readinessProbe on ANY container (1 pt)
#   - Deployment missing resources.requests (cpu or memory) on ANY container (1 pt)
#   - Multi-replica Deployment without a matching PodDisruptionBudget (1 pt)
#   - Externally-facing workload missing lifecycle.preStop hook (1 pt)
#     (workload-risks.md 6.6 — SCORING HOME: Category 6 MEDIUM)
#   - Drain-blocking PDB (disruptionsAllowed == 0) (2 pts each)
#
# IMPORTANT: If one workload has BOTH single-replica AND missing probes,
# that is 1 HIGH (3 pts) + 1 MEDIUM (1 pt) = 4 pts for that workload.
# KIND GUARDS: DaemonSets have NO .spec.replicas — replica/PDB checks apply ONLY to
# Deployment/StatefulSet (workload-risks.md 6.1/6.2). DaemonSets are handled by their
# own kind-agnostic rules (missing probes / missing requests, which apply to all kinds).
# externally_facing = a workload backed by a LoadBalancer-type Service OR an Ingress
# (workload-risks.md 6.6 pinned definition); ClusterIP-only workloads are NOT.
workload_high = 0
workload_medium = 0
for each workload in non_system_namespaces:
    if workload.kind in [Deployment, StatefulSet]:
        if workload.replicas == 1:                workload_high += 3
        if workload.strategy == "Recreate":       workload_high += 3   # Deployment only; StatefulSet has no Recreate
        if workload.replicas > 1 and no_matching_pdb: workload_medium += 1
    # kind-agnostic checks (apply to Deployment, StatefulSet AND DaemonSet):
    if workload.missing_readiness_probe:      workload_medium += 1
    if workload.missing_resource_requests:    workload_medium += 1
    if workload.externally_facing and workload.missing_prestop_hook: workload_medium += 1
    # externally_facing = backed by a LoadBalancer-type Service OR an Ingress
for each pdb where disruptionsAllowed == 0:
    workload_medium += 2                      # drain-blocking PDB
workload_high = min(workload_high, 8)
workload_medium = min(workload_medium, 4)
workload_deduction = min(workload_high + workload_medium, 10)

# --- Category 7: AWS Upgrade Insights (max deduction: 10) ---
# COUNTING UNIT: each insight ID from the EKS Insights API.
# The insight status enum is PASSING / WARNING / ERROR / UNKNOWN — there is NO
# "FAILING" status. Map insight status to points:
#   ERROR   → 5 pts (worst real status — top tier)
#   WARNING → 2 pts
#   PASSING → 0 pts
#   UNKNOWN → LOW severity (0 pts — report under Informational Findings, no deduction).
#     This matches upgrade-insights.md Step 3, which classifies UNKNOWN as LOW: it is a
#     LOW-tier finding surfaced to the user, NOT silently dropped.
# SUPPRESSION (no double-count): if the insight's subject is already scored in another
# category (e.g. a deprecated-API WARNING already counted in Cat 2, or an add-on insight
# already counted in Cat 4), score it 0 here and keep it as confirmation evidence only.
insights_deduction = 0
for each insight:
    if insight.subject already scored in another category:  continue   # 0 pts — confirmation only
    if insight.status == "ERROR":    insights_deduction += 5
    if insight.status == "WARNING":  insights_deduction += 2
insights_deduction = min(insights_deduction, 10)

# --- Category 8: AL2 Nodes (max deduction: 5) ---
# COUNTING UNIT: count of individual AL2 nodes.
al2_deduction = 0
al2_node_count = count of nodes where osImage contains "Amazon Linux 2" (not "2023")
                 or kernelVersion contains "amzn2"
if al2_node_count > 0:
    al2_deduction = 2 + (al2_node_count // 3)   # integer division
al2_deduction = min(al2_deduction, 5)

# --- Category 9: Behavioral Changes (max deduction: 5) ---
# COUNTING UNIT: each distinct behavioral change TYPE that applies to the target version.
# EXCLUSION: The 1.32 "Anonymous Auth Restricted" change is scored under Category 1
# (Breaking Changes), NOT here. Do NOT count it in this category — that double-counts.
behavioral_deduction = 0
for each behavioral_change applicable to target:
    if severity == MEDIUM: behavioral_deduction += 2
    if severity == LOW:    behavioral_deduction += 1
behavioral_deduction = min(behavioral_deduction, 5)

# --- Category 10: Unsupported Version (max deduction: 15) ---
# TRIGGER: cluster's current version has passed its Extended Support Until date.
# This is a binary check — either the version is unsupported or it isn't.
# NOTE: If the target version does not exist on EKS, the assessment is ABORTED
# in Step 1.0 (version-validation.md) — no score is produced at all.
unsupported_deduction = 0
if cluster_version_extended_support_end_date < assessment_date:
    unsupported_deduction = 15

# --- Final Score ---
total_deductions = (breaking_changes_deduction + deprecated_apis_deduction
                    + node_skew_deduction + addon_deduction + karpenter_deduction
                    + workload_deduction + insights_deduction + al2_deduction
                    + behavioral_deduction + unsupported_deduction)
score = max(0, 100 - total_deductions)

# --- Hard Blocker Override (apply AFTER arithmetic) ---
# If ANY hard blocker is present, the upgrade CANNOT proceed safely.
# Cap score at 59 (NOT READY) regardless of the arithmetic result.
#
# Hard blockers (exhaustive list):
#   1. Node version skew > 3 (kubelet more than N-3 behind the target is outside the
#      Kubernetes version-skew policy — nodes may fail to register or the kubelet may be
#      incompatible; a support-policy limit, not an API-enforced rejection)
#   2. Karpenter version incompatible with target (node provisioning breaks)
#   3. Critical add-on INCOMPATIBLE with target version (networking/storage breaks)
#   4. Critical add-on DEGRADED or FAILED (node drain stalls — volumes, DNS, or
#      networking broken during reschedule)
#   5. API removed in target version AND actively used in cluster (workloads fail)
#   6. Cluster status != ACTIVE (EKS API rejects update-cluster-version)
#   7. AL2-only node groups AND target >= 1.33 (no AL2 AMI available for target)
#   8. Candidate control-plane subnets COLLECTIVELY cannot provide enough free IPs to
#      place control-plane ENIs (EKS API rejects update-cluster-version). A single low
#      subnet among otherwise-healthy subnets is a warning, not a blocker.
#
# NOTE: containerd 1.x on self-managed/custom-AMI nodes at target >= 1.36 is HIGH severity
# (+5 under Category 3) but is NOT a hard blocker — it does not cap the score.
# NOTE: "Critical add-on" = vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver, plus any
# non-AWS CNI installed in their place (cilium, calico)
has_hard_blocker = False
if any distinct_kubelet_minor_version skew > 3:       has_hard_blocker = True   # across ALL nodes (MNG union nodeInfo); kubelet skew policy is N-3
if karpenter_installed and karpenter_incompatible:    has_hard_blocker = True
if any critical_addon.verdict == "INCOMPATIBLE":      has_hard_blocker = True
if any critical_addon.status in [DEGRADED, FAILED]:   has_hard_blocker = True
if any api_removed_in_target_and_in_use:              has_hard_blocker = True
if cluster_status != "ACTIVE":                        has_hard_blocker = True
if al2_only_node_groups and target >= 1.33:           has_hard_blocker = True
if candidate_subnets_collectively_cannot_place_enis:  has_hard_blocker = True   # single low subnet among healthy = warning, not blocker
# containerd 1.x on self-managed nodes at target >= 1.36 is HIGH severity (+5 Cat 3) but is
# NOT a hard blocker — it does not cap the score.

if has_hard_blocker:
    score = min(score, 59)
```

### 1.2 — Score Interpretation

| Score | Rating | Meaning |
|-------|--------|---------|
| 90-100 | READY | Safe to proceed with upgrade |
| 80-89 | GOOD | Minor issues, can proceed with caution |
| 70-79 | FAIR | Several issues need attention before upgrade |
| 60-69 | RISKY | Significant issues, upgrade not recommended yet |
| 0-59 | NOT READY | Critical blockers, must resolve before upgrade |

### 1.3 — Worked Example

Cluster: `example-cluster`, upgrading 1.30 → 1.31

**Findings:**
- EBS CSI driver DEGRADED (IAM issue) → critical add-on, status DEGRADED → 5 pts
- 17 FlowSchema resources using `flowcontrol.apiserver.k8s.io/v1beta3` (2 API paths: flowschemas + prioritylevelconfigurations, deprecated but available in 1.31). Step 3b writer-identity scan shows the only v1beta3 writers are internal APF controllers (`api-priority-and-fairness-config-*`) — no user tool wrote them → **false positives, 0 pts (informational only)**
- 1 AWS Insight WARNING (deprecated APIs for v1.32) → 2 pts
- `legacy-app`: 1 replica (HIGH=3) + Recreate strategy (HIGH=3) + missing probes (MED=1) + missing requests (MED=1) = 8 pts
- `single-replica-app`: 1 replica (HIGH=3) + missing probes (MED=1) + missing requests (MED=1) = 5 pts
- `recreate-app`: Recreate strategy (HIGH=3) + missing probes (MED=1) = 4 pts
- `no-resources-app`: missing probes (MED=1) + missing requests (MED=1) = 2 pts
- `insufficient-replicas-app`: missing probes (MED=1) = 1 pt
- `karpenter-test-app`: missing probes (MED=1) = 1 pt

**Workload risk calculation:**
- HIGH sub-total: 3+3+3+3 = 12 → capped at 8
- MEDIUM sub-total: 1+1+1+1+1+1+1+1+1 = 9 → capped at 4
- Workload total: 8+4 = 12 → capped at 10

**Score (arithmetic):**
```
100 - 0 (breaking) - 0 (deprecated: v1beta3 is APF-controller-written, 0 under Step 3b)
    - 0 (skew) - 5 (addon) - 0 (karpenter)
    - 10 (workload) - 2 (insights) - 0 (AL2) - 0 (behavioral) - 0 (unsupported)
= 100 - 17 = 83%
```

**Hard blocker override:**
```
EBS CSI driver DEGRADED → critical add-on DEGRADED → has_hard_blocker = True
score = min(83, 59) = 59% → NOT READY
```

**Final score: 59% — NOT READY** (hard blocker: critical add-on DEGRADED)

## Step 2: Build Master Finding List (MANDATORY — do this BEFORE calculating the score)

Before calculating the score, you MUST compile a complete finding table. This table is the single source of truth for scoring. Every row must map to exactly one line in the pseudocode above.

```
| # | Category | Finding | Counting Unit | Severity | Pts | Rule Applied |
|---|----------|---------|---------------|----------|-----|--------------|
| 1 | Deprecated APIs | flowschemas v1beta3 (APF-controller-written) | API path | INFO | 0 | Step 3b exclusion — internal writer, not counted |
| 2 | Deprecated APIs | prioritylevelconfigurations v1beta3 (APF-controller-written) | API path | INFO | 0 | Step 3b exclusion — internal writer, not counted |
| 3 | Add-on | aws-ebs-csi-driver DEGRADED | add-on | HIGH | 5 | critical addon DEGRADED |
| ... | ... | ... | ... | ... | ... | ... |
```

After building this table:
1. Sum each category column
2. Apply the per-category cap from the pseudocode
3. Sum all capped category totals
4. Subtract from 100

Include this table in the report under "Score Breakdown" so users can audit the math.

## Step 3: Consistency Checks (MANDATORY)

### 3.1 Structural contract (check FIRST, before content checks)

Before returning the report, verify it contains exactly these top-level sections
in this order:

1. `# EKS Upgrade Readiness Assessment`
2. `## Readiness Score: ...`
3. `## Blockers`
4. `## Critical Actions`
5. `## Recommended Actions`
6. `## Informational Findings`
7. `## Evidence`
8. `## Upgrade Plan`
9. `## AWS Reference Links`

`## Blockers` lists ONLY hard-blocker findings (the ones that cap the score at ≤59 —
the exhaustive list in the Hard Blocker Override pseudocode). All other HIGH-severity
findings go under `## Critical Actions`. Do NOT lump them together.

If ANY of sections 3, 4, 5, 6, 8, or 9 is missing, the report is invalid — add the
missing section (with "No blockers identified." / "No critical actions." /
"No recommended actions." / "None." placeholder text if empty) before returning it
to the user.

Sections 3, 4, 5, and 6 MUST appear before section 7 (Evidence). If they appear
after Evidence, the report is invalid — reorder before returning.

### 3.2 Content checks

1. Every hard-blocker finding (caps score ≤59) must appear in "Blockers"; every other
   HIGH/CRITICAL finding must appear in "Critical Actions"
2. Every MEDIUM finding must appear in "Recommended Actions"
3. Every LOW finding must appear in "Informational Findings"
4. The executive summary must match the findings — don't call something critical if it's medium
5. Score components must add up correctly
6. **CROSS-CHECK RULE:** Before writing any count (e.g., "5 deployments missing probes"),
   go back to the raw data and list the names. If the count of names doesn't match the number
   in your heading, fix it. Never write a count from memory.
7. **NO HALLUCINATED NUMBERS:** For any dollar amount, percentage, or numeric claim, show the
   arithmetic inline or in a comment. If you can't show the math, don't state the number.
8. **WORKLOAD TABLE REQUIRED:** The master workload table from `workload-risks.md` Step A
   MUST be produced before any workload risk findings are written. All workload counts in the
   report must be traceable to rows in that table.
9. **SCORE RECONCILIATION (hard gate):** Sum the Pts column of the Master Finding List
   table. The arithmetic check is: the headline score in `## Readiness Score:` MUST equal
   100 minus that sum (after per-category caps). **EXCEPTION — hard-blocker override:** when
   any hard blocker is present, the score is intentionally capped at 59 (which will NOT equal
   100 − sum whenever the arithmetic result exceeds 59). In that case the capped score of 59
   is correct and MUST be accepted — do NOT flag the report INVALID for the arithmetic
   mismatch. Apply the strict "score == 100 − sum" equality check ONLY on the non-capped path
   (no hard blocker). Also confirm each row's Deduction in the Score Breakdown table equals
   the corresponding category subtotal in the Master Finding List. If the header, the Score
   Breakdown, and the Master Finding List do not all agree (accounting for the hard-blocker
   cap), the report is INVALID — recompute and fix before returning it. Never publish a score
   that differs from the table it is derived from (except the documented ≤59 blocker cap).
10. **MANDATORY-FINDING PRESENCE:** Every "always flag" item from the steering files
   MUST appear as a row in the Master Finding List when its target condition is met.
   When the upgrade crosses INTO the restriction (current <= 1.31 AND target >= 1.32) this
   includes "Anonymous Auth Restricted" (Category 1, 4 pts). A cluster already on 1.32+ is
   past this crossing — do NOT add it.
   If an always-flag item is absent from the table, the assessment is incomplete —
   add it before scoring.

## Step 4: Write the Report

### Filename Format
`EKS-Upgrade-Assessment-<cluster>-<current>-to-<target>-<YYYY-MM-DD>-<HHMM>.md`

Example: `EKS-Upgrade-Assessment-my-cluster-1.30-to-1.31-2026-03-26-1430.md`

### Report Template

**The report structure is a contract, not a suggestion.** Every report MUST contain
the sections below, in exactly this order, with exactly these headings. Do not
reorder, rename, or omit required sections. Sections marked OPTIONAL are included
only when their condition is met; if the condition isn't met, omit the section
entirely (do not leave it as "N/A" or "None found").

**Required section order (every report, every time):**

1. `# EKS Upgrade Readiness Assessment` — title + metadata table
2. `## Readiness Score: XX% — [LEVEL]` — summary sentence + Score Breakdown table
3. `## Blockers` — hard-blocker findings ONLY (caps score ≤59); MUST appear even if empty (write "No blockers identified.")
4. `## Critical Actions` — other HIGH/CRITICAL findings; MUST appear even if empty (write "No critical actions.")
5. `## Recommended Actions` — MUST appear even if empty (write "No recommended actions.")
6. `## Informational Findings` — MUST appear even if empty (write "None.")
7. `## Evidence` — container for the detailed tables below
   - `### Add-on Inventory`
   - `### Unknown & Unidentified Add-ons` — OPTIONAL (only if any UNKNOWN_* verdicts exist)
   - `### Node Group Summary`
   - `### Workload Risk Summary`
8. `## Upgrade Plan` — always required
9. `## AWS Reference Links` — always required

The four action sections (Blockers, Critical Actions, Recommended, Informational) come
BEFORE the Evidence tables. This is intentional — readers open the report to answer
"what do I need to do?", not "what did the tool find?". Evidence supports the action
items; it doesn't precede them.

```markdown
# EKS Upgrade Readiness Assessment

| Field | Value |
|-------|-------|
| Cluster | [name] |
| Region | [region] |
| Account | [account-id] |
| Current Version | [current] |
| Target Version | [target] |
| Assessment Date | [YYYY-MM-DD HH:MM] |

> Account ID hygiene: the account ID is sensitive. If this report will be shared outside the account, mask or omit the `[account-id]` value before sharing.

---

## Readiness Score: [XX]% — [READY/GOOD/FAIR/RISKY/NOT READY]

[2-3 sentence summary. What's the bottom line? Can they upgrade safely?]

### Score Breakdown

| Category | Status | Deduction | Details |
|----------|--------|-----------|---------|
| Breaking Changes | ✅/⚠️/❌ | -X pts | [summary] |
| Deprecated APIs | ✅/⚠️/❌ | -X pts | [summary] |
| Node Readiness | ✅/⚠️/❌ | -X pts | [summary] |
| Add-on Compatibility | ✅/⚠️/❌ | -X pts | [summary] |
| Karpenter | ✅/⚠️/❌/N/A | -X pts | [summary] |
| Workload Risks | ✅/⚠️/❌ | -X pts | [summary] |
| AWS Upgrade Insights | ✅/⚠️/❌ | -X pts | [summary] |
| AL2 / AMI | ✅/⚠️/❌ | -X pts | [summary] |
| Behavioral Changes | ✅/⚠️/❌ | -X pts | [summary] |
| Unsupported Version | ✅/❌/N/A | -X pts | [summary — omit row if version is supported] |
| **Total** | | **-X pts** | **Score: XX%** |

---

## Blockers

[Hard-blocker findings ONLY — the ones that cap the score at ≤59 (see the Hard Blocker
Override list). These MUST be resolved before upgrading. If none, write: "No blockers identified."]

### [Finding Title]
- **Severity:** CRITICAL (hard blocker)
- **What we found:** [specific to this cluster]
- **Impact if not addressed:** [real-world consequence]
- **Remediation:**
  ```bash
  [pre-filled command with actual cluster name and region]
  ```
- **Reference:** [AWS doc link]

---

## Critical Actions

[HIGH-severity findings that are NOT hard blockers — important to address but do not cap the
score. If none, write: "No critical actions."]

### [Finding Title]
- **Severity:** HIGH
- **What we found:** [specific to this cluster]
- **Impact if not addressed:** [real-world consequence]
- **Remediation:**
  ```bash
  [pre-filled command with actual cluster name and region]
  ```
- **Reference:** [AWS doc link]

---

## Recommended Actions

[Items that SHOULD be addressed but won't block the upgrade. If none, write: "No recommended actions."]

### [Finding Title]
- **Severity:** MEDIUM
- **What we found:** [details]
- **Remediation:** [steps]

---

## Informational Findings

[LOW severity items and behavioral changes — awareness only. If none, write: "None."]

---

## Evidence

### Add-on Inventory

| Add-on | Type | Version | Status | Verdict | Source |
|--------|------|---------|--------|---------|--------|
| [name] | Managed/Self-managed/OSS | [ver] | [health] | one of the addon-compatibility.md §4.3 verdict states | [URL or "managed"] |

### Unknown & Unidentified Add-ons

Include this subsection only if ANY add-on has verdict `UNKNOWN_VERIFIABLE` or
`UNKNOWN_UNIDENTIFIED`. Omit it entirely if everything was resolved.

#### Compatibility Unverified (UNKNOWN_VERIFIABLE)

Add-ons the skill identified but could not verify against the target Kubernetes
version. The user must check these manually before upgrading.

| Add-on | Version | URL(s) Consulted | Why Unverified |
|--------|---------|------------------|----------------|
| [name] | [ver] | [url] | [e.g., page 404, no compat matrix found, ambiguous wording] |

#### Unidentified Workloads (UNKNOWN_UNIDENTIFIED)

Workloads that appear to be add-ons (based on namespace or shape) but could not be
identified. The user likely knows what these are — please review and confirm
compatibility with the target version manually.

| Kind | Name | Namespace | Image | Labels |
|------|------|-----------|-------|--------|
| [Deployment/DaemonSet/StatefulSet] | [name] | [ns] | [full image:tag] | [key labels present] |

### Node Group Summary

| Node Group | Version | AMI Type | Instances | Skew | Status |
|------------|---------|----------|-----------|------|--------|
| [name] | [ver] | [ami] | [min/max] | [N] | ✅/⚠️/❌ |

### Workload Risk Summary

| Risk | Severity | Count | Details |
|------|----------|-------|---------|
| Single replica deployments | HIGH | [N] | [names] |
| Missing PDBs | MEDIUM | [N] | [names] |
| Missing readiness probes | MEDIUM | [N] | [names] |
| Missing resource requests | MEDIUM | [N] | [names] |

---

## Upgrade Plan

[Step-by-step upgrade sequence with pre-filled commands.]

### Pre-Upgrade Checklist
- [ ] All blockers resolved
- [ ] Add-ons updated to compatible versions
- [ ] Node groups ready (AL2023/Bottlerocket)
- [ ] PDBs in place for critical workloads
- [ ] Backup/snapshot taken

### Rollback Considerations (advisory — not scored)
EKS supports rolling the control plane back to the previous minor version within 7 days of an
in-place upgrade (single version, N→N-1), gated by `ROLLBACK_READINESS` cluster insights. Two
forward-decidable choices can foreclose that path, so decide them before/while upgrading:
- **New-version-only API/feature adoption during the 7-day bake window** must be removed before a
  rollback — limit adoption of target-only APIs until the upgrade is confirmed stable.
- **Add-on cross-compatibility** — for a clean rollback, EKS-managed add-ons should be compatible
  with BOTH the current and target versions, not target-only.
Boundaries: Fargate rollback is unsupported; add-ons, etcd, workloads, and PVs are NOT reverted;
only Auto Mode nodes auto-roll-back (managed / self-managed / hybrid node groups are the
operator's job); rolling back to a version in extended support requires setting the cluster upgrade
policy to `EXTENDED` first. Advisory only — it does not change the readiness score.

### Step 1: Update Add-ons (if needed)
```bash
aws eks update-addon --cluster-name [CLUSTER] --addon-name [ADDON] --addon-version [VERSION] --region [REGION]
```

### Step 2: Upgrade Control Plane
```bash
aws eks update-cluster-version --name [CLUSTER] --kubernetes-version [TARGET] --region [REGION]
```

### Step 3: Monitor Upgrade Progress
```bash
aws eks describe-update --name [CLUSTER] --update-id [UPDATE_ID] --region [REGION]
```

### Step 4: Upgrade Node Groups
```bash
aws eks update-nodegroup-version --cluster-name [CLUSTER] --nodegroup-name [NODEGROUP] --region [REGION]
```

### Step 5: Verify
```bash
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

---

## AWS Reference Links

[All links verified via web search or AWS documentation. Do NOT fabricate URLs.]
```

## Step 5: Look Up AWS References

Use web search or AWS documentation to find verified URLs. Prefer:
- `https://docs.aws.amazon.com/eks/latest/best-practices/`
- `https://docs.aws.amazon.com/eks/latest/userguide/`
- `https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html`

Do NOT fabricate deep-link URLs. When in doubt, link to the broad section page.

## Step 6: Write the Report File

Write to the workspace root.

## Step 7: Offer HTML Conversion

After writing the markdown report, ask:
*"Would you like me to convert the report to HTML? Run: `python3 ${CLAUDE_SKILL_DIR}/tools/md_to_html.py <report-filename>.md`"*

Do NOT generate HTML manually. Always use the conversion script.
