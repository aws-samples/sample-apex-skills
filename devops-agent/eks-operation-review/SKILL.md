---
name: eks-operation-review
description: >-
  Perform a structured EKS operational excellence assessment against a live cluster.
  Covers 10 areas: cluster lifecycle, infrastructure as code, access and identity,
  observability, workload configuration, networking, autoscaling, deployment practices,
  operational processes, and add-on management. Produces a GREEN/AMBER/RED rated report
  with prioritized recommendations. Activate for any request to audit, review,
  health-check, or score an EKS cluster operational posture, including section-scoped
  reviews and version currency / current-state add-on and deprecated-API review with no target version. Not for upgrade readiness assessment against a target version, cluster discovery, or architectural design advice.
---

# EKS Operation Review

This skill performs a structured 10-section operational assessment of a live EKS cluster, producing a rated report with prioritized recommendations.

## When to Activate

Activate for any request to:
- Audit, review, health-check, or score an EKS cluster's operational posture
- Assess a specific operational area (e.g., "check my EKS networking", "review RBAC on my cluster", "EKS observability assessment")
- Generate an EKS operational review report

**Do NOT activate for:** upgrade readiness assessments, cluster discovery, architectural design advice, general Kubernetes questions, AWS troubleshooting, cluster creation, or one-off kubectl commands.

## Execution Model

This skill runs **autonomously** — it does NOT pause for user input mid-execution. It performs a **HARD STOP** on ambiguity instead of guessing.

### HARD STOP Conditions

If any of these conditions are met, produce a HARD STOP output and no report:

```
## HARD STOP
- **Reason:** [why execution cannot proceed]
- **What was found:** [clusters/resources discovered]
- **What is needed:** [specific input required to proceed]
```

HARD STOP triggers:
1. Multiple EKS clusters found and none specified by the user — list them and stop
2. No EKS clusters found in the configured region
3. Cluster access denied AT PRE-FLIGHT — the agent's role cannot describe the cluster or reach the Kubernetes API during the Step 0 pre-flight gate (IAM permissions or Kubernetes RBAC). This whole-run HARD STOP fires only at pre-flight; a 403 encountered later, during Steps 1–10, is handled per-signal (see the access-denied rule) and must NOT re-trigger this global HARD STOP
4. EKS or Kubernetes API access is not available or does not respond AT PRE-FLIGHT — the EKS or Kubernetes API cannot be reached during the Step 0 pre-flight gate. This whole-run HARD STOP fires only at pre-flight; a mid-run/transient K8s-API failure during Steps 1–10 is handled per-signal (section/signal marked UNKNOWN with recovery, see the access-denied rule and Error recovery) and must NOT re-trigger this global HARD STOP
5. A user-named cluster does not exist — if the user specified a cluster and DescribeCluster returns not-found (or it is absent from ListClusters), STOP immediately and report the error; do not fall back to a different cluster

### Passing Inputs

For a clean single-pass run, specify: cluster name, region (if not default), and optionally which sections to assess. Example: "Run EKS operation review for cluster `prod-app` in `us-west-2`"

## Prerequisites

The DevOps Agent must have:
- **EKS cluster access** via its IAM role — see [EKS access setup](https://docs.aws.amazon.com/devopsagent/latest/userguide/configuring-integrations-and-knowledge-aws-eks-access-setup.html)
- **AWS API permissions** for: `eks:Describe*`, `eks:List*`, `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroupRules`, `ecr:DescribeRepositories`, `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies`, `iam:GetRolePolicy`, `logs:DescribeLogGroups`, `cloudwatch:DescribeAlarms`, `backup:ListBackupPlans` (optional)
- **Kubernetes RBAC access** to list/get Nodes, Pods, Deployments, Services, DaemonSets, Namespaces, and related resources
- **CRD read access** for the GitOps, progressive delivery, backup/DR, autoscaler, and policy-engine checks — the supplementary read-only ClusterRole in the README's Step 2b (Argo CD, Flux (Kustomization-based), Argo Rollouts, Velero, Karpenter, KEDA, VPA, Kyverno, Gatekeeper, volume snapshots); without it those checks report UNKNOWN

## Reference File Map

Before executing checks for any section, load the corresponding reference file from `references/`.

| User Request | Reference File(s) to Load |
|---|---|
| Full review / assess / audit / health check | ALL files in order: cluster-lifecycle → addon-management, then report-generation |
| Version currency / lifecycle / deprecated APIs (current state) | `references/cluster-lifecycle.md` |
| IRSA / RBAC / access / pod identity / endpoint | `references/access-identity.md` |
| Logging / metrics / alerting / observability | `references/observability.md` |
| Resource requests / probes / PDB / image tags / storage | `references/workload-configuration.md` |
| IP / subnet / DNS / CoreDNS / network policy | `references/networking.md` |
| Autoscaling / Karpenter / HPA / topology spread | `references/autoscaling.md` |
| Deployment / rollout / CI/CD / graceful shutdown | `references/deployment-practices.md` |
| Runbook / on-call / post-incident / backup / DR / Velero | `references/operational-processes.md` |
| Add-on / node monitoring / cluster insights | `references/addon-management.md` |
| Deliver report | `references/report-generation.md` |
| IaC / GitOps / ArgoCD / Flux / drift | `references/infrastructure-as-code.md` |

## Assessment Overview

| # | Section | Key Checks |
|---|---------|------------|
| 01 | Cluster Lifecycle & Upgrades | Version currency, data plane alignment, deprecated APIs, add-on compatibility, upgrade process |
| 02 | Infrastructure as Code & GitOps | IaC provenance, GitOps tools, drift detection, RBAC in code |
| 03 | Access & Identity | IRSA/Pod Identity, least privilege RBAC, API server endpoint security, Pod Security Admission |
| 04 | Observability | Control plane logging, metrics stack, log aggregation, alerting |
| 05 | Workload Configuration | Resource requests/limits, health probes, PDBs, image tags, storage |
| 06 | Networking | IP capacity, CoreDNS health, network policies |
| 07 | Autoscaling | Cluster autoscaler/Karpenter, HPA, topology spread |
| 08 | Deployment Practices | Rollout strategy, CI/CD, graceful shutdown |
| 09 | Operational Processes | Runbooks, on-call, post-incident review, backup/DR (Velero, AWS Backup) |
| 10 | Add-on Management | Managed add-ons, node health monitoring, cluster insights |

Of the 36 ratable checks (of 38 numbered), 33 are auto-ratable (~92%, 33/36); the 3 exceptions are the human-knowledge/process items (9.1 runbooks, 9.2 on-call, 9.3 post-incident review), which have no observable cluster signal, require human input, and are marked UNKNOWN by design with suggestions for investigation. Separately, the 2 evidence-only checks are excluded from rating (not from automation) — they feed evidence into their owning checks rather than receiving a rating of their own.

## Assessment Workflow

### Step 0: Pre-flight

Verify access before starting the assessment:

1. **List clusters** — use EKS ListClusters API. If multiple found and none specified → HARD STOP with list. If one found → proceed with that cluster.
2. **Describe cluster** — use EKS DescribeCluster API. Report: cluster name, Kubernetes version, platform version, region, status, authentication mode. If the cluster status is not ACTIVE (e.g., UPDATING, CREATING), note the status in the report and proceed with the data available — do NOT HARD STOP on a non-ACTIVE status. Do not surface the AWS account ID in the report — mask or omit it.
3. **Verify Kubernetes access** — list Nodes via Kubernetes API.
   - Success → proceed
   - Failure → HARD STOP with access error details

### Steps 1-10: Run Assessment

Load each reference file in section order. For each section:
1. Load the reference file from `references/`
2. Execute the checks described in it using available EKS and Kubernetes APIs
3. Rate each item using the rubric below

**Error recovery:** If a section fails entirely (API unreachable, permissions denied for all checks), mark all items as UNKNOWN with failure reason, then proceed to next section. Do not let one failed section block the entire assessment. Exception: the evidence-only checks 10.1 and 10.3 never receive a rating (including UNKNOWN); if their evidence is unavailable, keep their Evidence-only status and note the missing evidence under their owning checks (1.4 / 5.5 / 1.3).

### Step 11: Generate Report

Load `references/report-generation.md` and produce the report following its structure and consistency rules.

## Rating Rubric

| Rating | Meaning |
|--------|---------|
| GREEN | Fully implemented — matches EKS best practices |
| AMBER | Partial or inconsistent — improvement opportunity |
| RED | Not implemented or significant gap — action needed |
| N/A | Check does not apply to this cluster (e.g. no stateful workloads) — excluded from scoring |
| UNKNOWN | Cannot be determined from cluster data — investigate manually — excluded from scoring |

### Rules

- Only rate based on what was actually observed — never assume
- If a check fails or returns no data, mark the affected signal UNKNOWN per the access-denied (403) handling rule below (a total failure of the whole section still maps to all-UNKNOWN per the Error recovery paragraph above; a single forbidden read follows the floor-preserving logic). Exception: the evidence-only checks 10.1 and 10.3 are never rated (including UNKNOWN) even if they individually fail or return no data; keep their Evidence-only status and note the missing evidence under their owning checks (1.4 / 5.5 / 1.3).
- **Access-denied (403) handling (floor-preserving):** When a check's data-gathering read returns 403/Forbidden: (1) mark only that specific signal UNKNOWN — never treat a forbidden read as "resource absent" or zero. (2) Still evaluate every signal that was read successfully, RED-first then AMBER. (3) Confirmed floor: if a successfully-read signal independently triggers RED or AMBER, the check keeps that rating — a forbidden read of a different signal can only make the true state worse, never better, so it never downgrades a confirmed RED/AMBER to UNKNOWN. (4) No unearned GREEN: GREEN requires all of its preconditions confirmed by successful reads; an unconfirmable "good" signal caps the check at AMBER (with a "could not verify X" note) when the other signals are GREEN-worthy, or UNKNOWN when nothing is confirmed — never GREEN. (5) Rate the whole check UNKNOWN only when no successfully-read signal yields RED or AMBER AND the forbidden read was the sole remaining discriminator.
- If a check fails with a permissions error, decide its rating via the access-denied (403) handling rule above; in the report, direct the user to the "Resource Access (Prerequisites)" section of the skill README to grant the review read permissions (see the AWS EKS access setup guide at https://docs.aws.amazon.com/devopsagent/latest/userguide/configuring-integrations-and-knowledge-aws-eks-access-setup.html for the full procedure)
- **Pre-flight gate takes precedence over per-signal 403 handling.** The Step 0 pre-flight DescribeCluster / Kubernetes-node access check is a whole-run gate: a 403/Forbidden there is HARD STOP trigger 3 (cluster access denied) — stop and emit no report. The per-signal, floor-preserving 403 handling above applies ONLY after pre-flight has succeeded (i.e. to individual check reads during Steps 1–10). A DescribeCluster 403 is therefore a HARD STOP at pre-flight, not a per-signal UNKNOWN; the per-signal UNKNOWN fallbacks (e.g. for the 3.1/3.3 DescribeCluster-derived signals) come into play once the pre-flight DescribeCluster has already succeeded and a read issued during Steps 1–10 (including a re-issued DescribeCluster) is the one denied — that read is treated as per-signal and never re-triggers the global HARD STOP.
- **UNKNOWN-band discipline:** A check may be rated UNKNOWN only via a decidable trigger (a specific read returned 403, or a specific signal is genuinely unavailable from the API). For a check that HAS an observable partition, permanently-true unobservable questions ("was it tested?", "did issues occur historically?", "is it reviewed periodically?") are never UNKNOWN-band triggers — they belong under "Items to Investigate Manually", and an always-true UNKNOWN clause must not compete with that check's observable GREEN/AMBER/RED bands (a check with real observable bands cannot ALSO carry an always-true UNKNOWN escape). **Carve-out for signal-less process checks:** a small set of checks — 9.1 (runbooks), 9.2 (on-call), 9.3 (post-incident) — are inherently process/human-knowledge checks with no observable cluster signal at all; these are legitimately rated UNKNOWN as their normal, by-design outcome and routed to Items to Investigate Manually. The no-always-true-clause prohibition above bites only where a check has an observable partition; it does NOT invalidate these signal-less process checks, which have no observable band to compete with.
- Prioritize by blast radius: security > availability > cost
- Every RED finding must have a specific, actionable recommendation

## Report Output

Deliver the report **inline in your response** (see report-generation Step 9). The filename below applies only if a workspace is available and you additionally save a copy — inline delivery is primary and always required.

### Filename (for an optional workspace copy)

`EKS-Operation-Review-<cluster-name>-<YYYY-MM-DD>-<HHMM>.md`

### Report Template

```markdown
# EKS Operation Review Report
Cluster: [name] | Region: [region] | Version: [version]
Date: [YYYY-MM-DD HH:MM]

## Executive Summary
[2-3 paragraphs. Strengths first, then gaps. Every rating mentioned must match findings.]

## Maturity Score
**Maturity Score: X% (computed over N of M applicable checks; K UNKNOWN excluded)**
<!-- MANDATORY: never present the score without this coverage annotation. M = applicable checks (GREEN+AMBER+RED+UNKNOWN); N = M − K = rated checks; K = UNKNOWN count; X% = GREEN ÷ N × 100. See references/report-generation.md for the computation. -->

| Rating | Count | Percentage |
|--------|-------|------------|
| GREEN | X | X% |
| AMBER | X | X% |
| RED | X | X% |
| N/A | X | -- |
| UNKNOWN | X | -- |

## Findings
[One table per section with columns: Item | Status | Current State | Recommendation | References]
[For the evidence-only checks 10.1 and 10.3, use the Status value `Evidence-only (see 1.4, 5.5)` and `Evidence-only (see 1.3)` respectively — they contribute no count to the Maturity Score.]

## Prioritized Actions

### Critical (Address within 30 days)
[All RED items except those fixable in < 1 hour (which may instead go in Quick Wins), ordered: security > availability > cost]

### Important (Address within 90 days)
[All AMBER items except those fixable in < 1 hour (which may instead go in Quick Wins)]

### Quick Wins
[Items (RED or AMBER) fixable in < 1 hour — one row per finding, each led by its finding ID and rating token]
| # | Finding | Action | Effort | Impact | References |
|---|---------|--------|--------|--------|------------|
| 1 | [X.X — Item Name] RED/AMBER | [action] | [estimate] | [what improves] | [links] |

## Items to Investigate Manually
[All UNKNOWN items with specific questions, PLUS any "could-not-verify" caveats from checks capped at AMBER-with-note under the access-denied (403) rule, PLUS manual-review questions surfaced by any check regardless of its rating]

## AWS Reference Links
[Grouped by topic — use pre-verified URLs from references/report-generation.md]
```

### Consistency Rules (MANDATORY)

1. Ratings must be consistent across the entire report
2. Prioritized Actions must reference the finding ID (e.g., "4.1 — Control Plane Logging RED")
3. Every RED must appear in Critical (or Quick Wins if fixable in < 1 hour); every AMBER in Important (or Quick Wins if fixable in < 1 hour)
4. Executive Summary must match the findings — do not call something "critical" if it's AMBER
5. One row per finding in Prioritized Actions — never bundle multiple findings

### Report Footer

Append at the end:

```markdown
---

*This report was generated by an AWS DevOps Agent skill provided as sample code for educational and demonstration purposes only. Findings should be reviewed and validated before acting on them. See the project's README for full terms and licensing information.*

*Before sharing this report outside your organization, mask or omit the AWS account ID and any cluster ARNs.*
```

## Live Data Caveat

This skill determines version support status primarily from the live EKS **DescribeClusterVersions** API. It also includes embedded reference tables (a fallback EKS version table, compatibility data, pre-verified AWS documentation URLs) that may become stale over time; these are used only when the live API is unavailable.

If the live API is not available, flag results as: "⚠️ Version data based on embedded fallback table (last verified 2026-08-09). Verify against official docs."
