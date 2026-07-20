---
title: "eks-upgrade-check"
description: "Assess EKS cluster upgrade readiness by running automated checks across 8 areas (version validation, breaking changes, deprecated APIs, add-on compatibility, node readiness, workload risks, AWS Upgrade Insights, upgrade plan), calculate a readiness score (0-100%), and generate a detailed report with remediation steps and pre-filled AWS CLI commands. Use this skill when investigating EKS upgrade safety, or, in the context of a version upgrade, Kubernetes version skew, deprecated API usage, addon compatibility, or Karpenter version; also node upgrade readiness or control plane upgrade planning."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-upgrade-check/SKILL.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-upgrade-check/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-upgrade-check/SKILL.md). Edit the source, not this page.
:::


# EKS Upgrade Readiness Skill

## Overview

This skill assesses a live EKS cluster's readiness for a Kubernetes version upgrade. It connects to the cluster via AWS APIs, runs automated checks across 8 assessment areas, calculates a readiness score (0-100%), and produces a detailed report with prioritized remediation steps and pre-filled AWS CLI commands.

This skill is laser-focused on **upgrade safety** — answering the question: "Is it safe to upgrade this cluster to the next version?"

All operations are **read-only** — this skill does not modify your cluster.

## What Gets Assessed

| # | Section | Key Checks |
|---|---------|------------|
| 01 | Version Validation | Upgrade path validity, version skew policy, support status & cost |
| 02 | Breaking Changes | Version-specific API removals, behavioral changes, resource impact |
| 03 | Deprecated API Detection | Live scan of cluster resources for deprecated/removed APIs |
| 04 | Add-on Compatibility | Core add-on versions, OSS add-on matrix, Karpenter compatibility |
| 05 | Node Readiness | Node version skew, AL2→AL2023 migration, AMI compatibility |
| 06 | Workload Risks | Single replicas, missing PDBs, health probes, resource requests |
| 07 | AWS Upgrade Insights | Official EKS pre-upgrade checks and recommendations |
| 08 | Upgrade Plan | Pre-filled CLI commands, step-by-step upgrade sequence |

## Readiness Score

The skill calculates a weighted readiness score:

| Category | Max Deduction | Rationale |
|----------|--------------|-----------|
| Breaking Changes | 25 pts | Highest risk — can break apps |
| Deprecated APIs | 20 pts | Actionable, fixable pre-upgrade |
| Node Readiness (skew + subnet IPs) | 20 pts | Can block upgrade entirely |
| Unsupported Version | 15 pts | No security patches, urgent upgrade needed |
| Add-on Compatibility | 15 pts | Critical > optional add-ons |
| Karpenter | 10 pts | Only if installed |
| Workload Risks | 10 pts | Best-practice, not blockers |
| AWS Upgrade Insights | 10 pts | Official AWS checks |
| AL2 Nodes / Behavioral | 10 pts | Informational |

**Hard Blocker Override:** If any hard blocker is detected (e.g., incompatible Karpenter,
critical add-on DEGRADED, cluster subnets collectively cannot place control-plane ENIs,
cluster not ACTIVE), the score is capped at ≤ 59% (NOT READY) regardless of other findings.
See `references/report-generation.md` for the full list.

**Score Interpretation:**

| Score | Level | Meaning |
|-------|-------|---------|
| 90-100 | READY | Safe to proceed |
| 80-89 | GOOD | Minor issues, can proceed with caution |
| 70-79 | FAIR | Several issues need attention first |
| 60-69 | RISKY | Significant issues, not recommended yet |
| 0-59 | NOT READY | Critical blockers, must resolve first |

## Assessment Workflow

### Step 0: Pre-flight

> **Execution model — autonomous with hard stops.** This skill runs autonomously
> and does NOT pause for interactive input. It proceeds only when the target cluster
> and version are unambiguous. If any gating criterion below is not met, it performs
> a **HARD STOP**: it does NOT guess, auto-select, or partially assess — it emits a
> structured stop message and ends. Never assess a cluster or target the user did not
> unambiguously specify or that cannot be uniquely determined.

**HARD STOP output format** — whenever a criterion below triggers a hard stop, output
exactly this and end the run (produce no readiness score):

```
## Assessment Halted — <one-line reason>

**Criterion not met:** <which check failed>
**What was found:** <observed state>
**To proceed:** <the specific input needed, e.g., re-run naming the cluster + region + target>
```

**Action 1 — Discover clusters**

Use EKS ListClusters to discover available clusters, then apply this decision table:

| Condition | Action |
|-----------|--------|
| User named a cluster in the request | Confirm it exists in the list, then proceed. If it does not exist → HARD STOP. |
| Exactly one cluster found, none named | Proceed. State which cluster is being assessed. |
| More than one cluster found, none named | **HARD STOP.** List all clusters (name + region). Do NOT auto-select by first/newest/any heuristic. |
| Zero clusters found | **HARD STOP.** Report that no clusters were found in the region/account. |

**Action 2 — Describe the selected cluster**

Use EKS DescribeCluster and record: cluster name, Kubernetes version, platform version, region, status, account ID.

> **Account ID hygiene:** the account ID is sensitive. If the generated report will be shared outside the account, mask or omit the account ID before sharing.

**Action 2b — Validate cluster status**

If status is NOT `ACTIVE` → **HARD STOP**:
- **CREATING/UPDATING/DELETING** — cluster is in transition; the EKS API will reject an upgrade.
- **FAILED** — cluster must be recovered before an upgrade can be attempted.

**Action 3 — Validate permissions**

Verify access to: ListNodegroups, ListAddons, ListInsights. If any required permission
is missing → **HARD STOP** and report exactly which IAM action is denied. Do NOT proceed
with a partial assessment.

**Action 4 — Determine target version**

- **User specified a target version** → use it. Validate the upgrade path per
  `references/version-validation.md`; if the path is invalid (downgrade, same version,
  or the target does not exist on EKS) → **HARD STOP**.
- **No target specified** → default to the immediate next minor version (current + 1).
  This is deterministic (EKS upgrades one minor at a time), so it is a safe default, not
  a guess. State the assumed target explicitly in the report metadata.
- **User requested a multi-hop upgrade** (target > current + 1) → **HARD STOP**. Show the
  required one-hop-at-a-time path (e.g., 1.30 → 1.31 → 1.32) and state that this run
  assesses only a single hop; re-run naming the immediate next version.

**Action 5 — Proceed**

If all criteria above pass, proceed through Steps 1-8 without further pauses.

### Steps 1-8: Run Assessment

For each assessment area, read the corresponding reference file from `references/` and execute the checks described.

| Assessment Area | Reference File |
|---|---|
| Version / upgrade path | `references/version-validation.md` |
| Breaking changes / API removals | `references/breaking-changes.md` |
| Deprecated APIs | `references/deprecated-apis.md` |
| Add-on compatibility / Karpenter | `references/addon-compatibility.md` |
| Node readiness / AL2 / AMI | `references/node-readiness.md` |
| Workload risks / PDB / probes | `references/workload-risks.md` |
| AWS Insights | `references/upgrade-insights.md` |
| Generate report | `references/report-generation.md` |

### Step 9: Calculate Score & Generate Report

Follow the scoring algorithm in `references/report-generation.md` to calculate the final score and produce the report.

## Tool Usage Guidelines

1. **Do NOT hardcode or guess cluster names.** Always discover by listing first.
2. **Do NOT retry a failed API call more than once.**
3. **Always read the relevant reference file before executing checks for that section.**
4. **Use EKS APIs for cluster queries** — DescribeCluster, ListNodegroups, DescribeNodegroup, ListAddons, DescribeAddon, DescribeAddonVersions, ListInsights, DescribeInsight.
5. **Use Kubernetes APIs** for resource scanning — list Deployments, DaemonSets, StatefulSets, Pods, Nodes, PDBs, etc.
6. **Use EC2 DescribeSubnets** for subnet IP capacity checks.

## Data Files

- **OSS Add-on Registry:** `assets/oss_addon_registry.json` — identifiers and authoritative upstream URLs for common OSS add-ons. This file does NOT contain compatibility data. Compatibility is always verified live via the registry's `compatibility_url` and `releases_url` fields.

## Report Output Format

The report is rendered as Markdown **inline in your response** — the DevOps Agent
runtime cannot write files. Use the report-title pattern from
`references/report-generation.md` as the report's title/heading, not as a saved
filename. There is only one delivery path: render the full report inline.

Each report includes:
- Readiness score with breakdown
- Blockers (hard blockers only — these cap the score at ≤59)
- Critical Actions (other HIGH-severity findings, not score-capping)
- Recommended actions
- Informational findings
- Evidence tables (add-ons, nodes, workloads)
- Step-by-step upgrade plan with pre-filled commands
- AWS reference links
