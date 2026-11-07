---
title: "EKS Operation Review"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/runbooks/eks-operation-review/eks-operation-review.md
format: md
---

:::info[Source]
This page is generated from [skills/apex/runbooks/eks-operation-review/eks-operation-review.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/runbooks/eks-operation-review/eks-operation-review.md). Edit the source, not this page.
:::

# EKS Operation Review

## Tool Usage Rules

1. **Do NOT call any tools when this skill is first activated.** Wait for the user to explicitly ask for a review.
2. **Do NOT read mcp.json or config files as a "check".** The only way to verify the MCP server works is to call an actual tool.
3. **Do NOT hardcode or guess cluster names.** Always discover clusters by listing them first.
4. **Do NOT retry a failed MCP tool call more than once.** If it fails twice, stop and show troubleshooting steps.
5. **Always load the relevant steering file before executing checks for that section.**
6. **Do NOT use the `manage_eks_stacks` MCP tool for cluster discovery or description.** That tool manages CloudFormation stacks, not EKS clusters. Use `aws eks list-clusters` and `aws eks describe-cluster` via Bash for pre-flight, and `list_k8s_resources` for Kubernetes checks. **Carve-out:** check 3.1's credential-name scan intentionally uses raw `kubectl` with name-only projection (`go-template`/`jsonpath`) because it must enumerate Secret key names and env-var names without those values ever reaching the agent context or the report — an MCP `list_k8s_resources` call returns only resource summaries (name, namespace, timestamps, labels, annotations) and omits the Secret `.data` block, so it is not a dependable way to enumerate Secret key names — and worse, because its `annotations` passthrough is unfiltered, a `kubectl.kubernetes.io/last-applied-configuration` annotation on a Secret can surface both the key names AND their values into the agent context via that summary. The raw `kubectl` name-only projection sidesteps both problems, which is exactly why the carve-out uses it. The Step 0 pre-flight `aws eks update-kubeconfig` action enables that `kubectl` access.

## Steering File Loading

Before executing checks for any section, read the corresponding steering file from the `references/` directory using the Read tool.

### Scenario to Steering File Map

| User Request | Steering File(s) to Load |
|---|---|
| Full review / assess / audit / health check | ALL files in order: cluster-lifecycle -> addon-management, then report-generation |
| Version currency / lifecycle / deprecated APIs (current state) | `references/cluster-lifecycle.md` |
| IRSA / RBAC / access / pod identity / endpoint | `references/access-identity.md` |
| Logging / metrics / alerting / observability | `references/observability.md` |
| Resource requests / probes / PDB / image tags / storage | `references/workload-configuration.md` |
| IP / subnet / DNS / CoreDNS / network policy | `references/networking.md` |
| Autoscaling / Karpenter / HPA / topology spread | `references/autoscaling.md` |
| Deployment / rollout / CI/CD / graceful shutdown | `references/deployment-practices.md` |
| Runbook / on-call / post-incident / backup / DR / Velero | `references/operational-processes.md` |
| Add-on / node monitoring / cluster insights | `references/addon-management.md` |
| Generate / write report | `references/report-generation.md` |
| IaC / GitOps / ArgoCD / Flux / drift | `references/infrastructure-as-code.md` |

---

## Overview

This skill assesses your live EKS cluster against 10 areas of operational best practice. It connects to your cluster via the EKS MCP server, runs automated checks, rates each item as GREEN/AMBER/RED, and produces a report with prioritized recommendations and AWS documentation links.

## What Gets Assessed

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

Of the 36 ratable checks (of 38 numbered), 33 are auto-ratable (~92%, 33/36); the 3 exceptions are the human-knowledge/process items (9.1 runbooks, 9.2 on-call, 9.3 post-incident review), which have no observable cluster signal and are marked UNKNOWN by design with suggestions for what to investigate. (The 2 evidence-only checks are excluded from the rating entirely, not counted against automation.)

## Prerequisites

1. **AWS credentials configured** -- `aws configure` or `~/.aws/credentials` with a profile that has EKS access
2. **Python 3.10+** and **uv** installed ([Install uv](https://docs.astral.sh/uv/getting-started/installation/)) -- required to run the EKS MCP server
3. **kubectl** installed -- required for check 3.1's name-only credential scan; pre-flight configures its kubeconfig via `aws eks update-kubeconfig`
4. **Required AWS Permissions**:
   - `eks:Describe*`, `eks:List*`
   - `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroupRules`
   - `ecr:DescribeRepositories`
   - `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies`, `iam:GetRolePolicy`
   - `logs:DescribeLogGroups`
   - `cloudwatch:DescribeAlarms`
   - `backup:ListBackupPlans` (optional)

## MCP Server Configuration

The MCP servers use your existing AWS credentials from the environment (`~/.aws/credentials`, `AWS_PROFILE`, `AWS_REGION`). No additional configuration is needed if your AWS CLI already works.

If you need to use a specific profile or region, update the EKS MCP server config in `.mcp.json`:

```json
"env": {
  "AWS_PROFILE": "your-profile-name",
  "AWS_REGION": "your-region",
  "FASTMCP_LOG_LEVEL": "ERROR"
}
```

## Getting Started

Run: `/eks-operation-review`

The skill will automatically discover your clusters and walk you through the assessment.

---

## Assessment Workflow

### Step 0: Pre-flight

This step verifies everything works before starting the assessment. Follow this exact sequence:

**Action 1 -- List clusters (discovers clusters)**

Use the AWS CLI to list clusters. Do NOT use the `manage_eks_stacks` MCP tool — it manages CloudFormation stacks, not cluster discovery.

```
aws eks list-clusters --output json
```

- Success -> Show the cluster list. Ask the user which cluster to assess. If only one cluster, confirm: "I found one cluster: [name]. Shall I assess this one?"
- Failure -> STOP. Do NOT retry more than once. Do NOT read config files. Show:

> **Cannot list EKS clusters.** Try these steps:
> 1. Check that AWS credentials work: `aws sts get-caller-identity`
> 2. Check the region: `aws configure get region`
> 3. Verify AWS_PROFILE and AWS_REGION in `.mcp.json`

Wait for the user to resolve the issue.

**Action 2 -- Describe the selected cluster**

Use the AWS CLI to describe the cluster. Do NOT use `manage_eks_stacks` — it looks for CloudFormation stacks, not EKS clusters.

```
aws eks describe-cluster --name <cluster-name> --output json
```

From the response, show:
- Cluster name, Kubernetes version, platform version, region, status
- AWS account ID
- Authentication mode

- Success -> Show the details above. If the cluster status is not ACTIVE (e.g., UPDATING, CREATING), note the status and proceed with the data available. Proceed to Action 3.
- Failure -> STOP. Do NOT retry more than once. If the named cluster is not found, report that it does not exist and do NOT fall back to another cluster. If describe is denied (403/AccessDenied), this is a pre-flight access failure — show:

> **Cannot describe the cluster.** Try these steps:
> 1. Confirm the cluster name and region are correct.
> 2. Check that AWS credentials work: `aws sts get-caller-identity`
> 3. Confirm your identity has `eks:DescribeCluster` on this cluster.

Wait for the user to resolve the issue.

**Action 3 -- Configure kubectl access**

Configure a kubeconfig context for the selected cluster so check 3.1's name-only `kubectl` credential scan works. Use the region from Action 2's describe output.

```
aws eks update-kubeconfig --name <cluster-name> --region <region>
```

Then verify kubectl can reach the cluster:

```
kubectl auth can-i get pods -A
```

- Success -> kubectl is configured. Proceed.
- Failure -> STOP. Do NOT retry more than once. Show:

> **Cannot configure kubectl access.** Try these steps:
> 1. Check that kubectl is installed: `kubectl version --client`
> 2. Re-run: `aws eks update-kubeconfig --name <cluster-name> --region <region>`
> 3. Confirm your identity has an EKS access entry / RBAC binding on the cluster: `aws sts get-caller-identity`

Wait for the user to resolve the issue.

**Action 4 -- Verify MCP connectivity**

Call one MCP tool to confirm the EKS MCP server works (e.g., list Nodes):

```
list_k8s_resources(cluster_name="<cluster-name>", kind="Node", api_version="v1")
```

- Success -> MCP server is working. Proceed.
- Failure -> STOP. Show:

> **The EKS MCP server isn't responding.** Try these steps:
> 1. Check that Python 3.10+ and uv are installed: `uv --version`
> 2. Test the MCP server: `uvx awslabs.eks-mcp-server@0.1.28`
> 3. Verify AWS_PROFILE and AWS_REGION in `.mcp.json`

Wait for the user to resolve the issue.

**Action 5 -- Confirm**

Ask: *"Ready to start the assessment on [cluster-name] (v[version])?"*

Proceed only after the user confirms.

### Steps 1-10: Run Assessment

Read each steering file in section order using the Read tool. For each section:
1. Read the steering file from `references/` directory
2. Execute the checks described in it
3. Rate each item using the rubric below

**Error recovery:** If a section fails entirely (MCP server unreachable, permissions denied for all checks in that section, or repeated timeouts), mark all items in that section as UNKNOWN with a note explaining the failure reason, then proceed to the next section. Do not let one failed section block the rest of the assessment. Exception: the evidence-only checks 10.1 and 10.3 never receive a rating (including UNKNOWN); if their evidence is unavailable, keep their Evidence-only status and note the missing evidence under their owning checks (1.4 / 5.5 / 1.3).

### Step 11: Generate Report

Read `references/report-generation.md` and produce the report.

---

## Rating Rubric

| Rating | Meaning |
|--------|---------|
| GREEN | Fully implemented -- matches EKS best practices |
| AMBER | Partial or inconsistent -- improvement opportunity |
| RED | Not implemented or significant gap -- action needed |
| N/A | Check does not apply to this cluster (e.g. no stateful workloads) -- excluded from scoring |
| UNKNOWN | Cannot be determined from cluster data -- investigate manually -- excluded from scoring |

### Rules

- Only rate based on what was actually observed -- never assume
- If a check fails or returns no data, mark the affected signal UNKNOWN per the access-denied (403) handling rule below (a total failure of the whole section still maps to all-UNKNOWN per the Error recovery paragraph above; a single forbidden read follows the floor-preserving logic). Exception: the evidence-only checks 10.1 and 10.3 are never rated (including UNKNOWN) even if they individually fail or return no data; keep their Evidence-only status and note the missing evidence under their owning checks (1.4 / 5.5 / 1.3).
- **Access-denied (403) handling (floor-preserving):** When a check's data-gathering read returns 403/Forbidden: (1) mark only that specific signal UNKNOWN -- never treat a forbidden read as "resource absent" or zero. (2) Still evaluate every signal that was read successfully, RED-first then AMBER. (3) Confirmed floor: if a successfully-read signal independently triggers RED or AMBER, the check keeps that rating -- a forbidden read of a different signal can only make the true state worse, never better, so it never downgrades a confirmed RED/AMBER to UNKNOWN. (4) No unearned GREEN: GREEN requires all of its preconditions confirmed by successful reads; an unconfirmable "good" signal caps the check at AMBER (with a "could not verify X" note) when the other signals are GREEN-worthy, or UNKNOWN when nothing is confirmed -- never GREEN. (5) Rate the whole check UNKNOWN only when no successfully-read signal yields RED or AMBER AND the forbidden read was the sole remaining discriminator.
- **UNKNOWN-band discipline:** A check may be rated UNKNOWN only via a decidable trigger (a specific read returned 403, or a specific signal is genuinely unavailable from the API). For a check that HAS an observable partition, permanently-true unobservable questions ("was it tested?", "did issues occur historically?", "is it reviewed periodically?") are never UNKNOWN-band triggers -- they belong under "Items to Investigate Manually", and an always-true UNKNOWN clause must not compete with that check's observable GREEN/AMBER/RED bands (a check with real observable bands cannot ALSO carry an always-true UNKNOWN escape). **Carve-out for signal-less process checks:** a small set of checks -- 9.1 (runbooks), 9.2 (on-call), 9.3 (post-incident) -- are inherently process/human-knowledge checks with no observable cluster signal at all; these are legitimately rated UNKNOWN as their normal, by-design outcome and routed to Items to Investigate Manually. The no-always-true-clause prohibition above bites only where a check has an observable partition; it does NOT invalidate these signal-less process checks, which have no observable band to compete with.
- **Pre-flight gate takes precedence over per-signal 403 handling.** The Step 0 pre-flight cluster-access / node-list check is a whole-run gate: a 403/Forbidden there pauses the run and waits for the user to resolve access (cluster access denied) per the Step 0 Success/Failure branches — no report is produced until pre-flight passes. This whole-run gate fires only at pre-flight; a 403 encountered later, during Steps 1–10, must NOT re-trigger it. The per-signal, floor-preserving 403 handling above applies ONLY after pre-flight has succeeded (to individual check reads during Steps 1--10). A DescribeCluster 403 is therefore a pre-flight stop, not a per-signal UNKNOWN; the per-signal UNKNOWN fallbacks (e.g. for the 3.1/3.3 DescribeCluster-derived signals) apply once pre-flight DescribeCluster has already succeeded and a read issued during Steps 1–10 (including a re-issued DescribeCluster) is the one denied — such a read is treated as per-signal, never as the whole-run gate.
- Prioritize by blast radius: security > availability > cost
- Every RED finding must have a specific, actionable recommendation

---

## Report Format

### Consistency Rules (MANDATORY)

1. **Ratings must be consistent across the entire report.** If 4.1 is RED in the findings table, it must appear as RED everywhere -- executive summary, prioritized actions, quick wins.
2. **Prioritized Actions must reference the finding ID.** Write "4.1 -- Control Plane Logging RED" not just "Enable logging".
3. **Every RED must appear in Critical (or Quick Wins if <1hr). Every AMBER must appear in Important (or Quick Wins if <1hr).** Nothing rated RED/AMBER can be missing from Prioritized Actions.
4. **Executive Summary must match the findings.** Do not call something a "critical gap" if it's AMBER, or skip a RED item.
5. **One row per finding in Prioritized Actions -- never bundle multiple findings into one row.**

### File Output

- **Location:** Workspace root or `reports/` subfolder. Do NOT write outside the workspace.
- **Filename:** `EKS-Operation-Review-<cluster-name>-<YYYY-MM-DD>-<HHMM>.md`

### Template

```markdown
# EKS Operation Review Report
Cluster: [name] | Region: [region] | Version: [version]
Date: [YYYY-MM-DD HH:MM]

## Executive Summary
[2-3 paragraphs. Strengths first, then gaps. Every rating mentioned must match the findings tables.]

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

### Section 01 -- Cluster Lifecycle & Upgrades
| Item | Status | Current State | Recommendation | References |
|------|--------|---------------|----------------|------------|

[Repeat for all 10 sections. For the evidence-only checks 10.1 and 10.3, use the Status value `Evidence-only (see 1.4, 5.5)` and `Evidence-only (see 1.3)` respectively -- they contribute no count to the Maturity Score.]

## Prioritized Actions

### Critical (Address within 30 days)
<!-- All RED items except those fixable in < 1 hour, which may instead go in Quick Wins. -->
| # | Finding | Action | References |
|---|---------|--------|------------|
| 1 | [X.X -- Item Name] RED | [specific action] | [links] |

### Important (Address within 90 days)
<!-- All AMBER items except those fixable in < 1 hour, which may instead go in Quick Wins. -->
| # | Finding | Action | References |
|---|---------|--------|------------|
| 1 | [X.X -- Item Name] AMBER | [specific action] | [links] |

### Quick Wins
| # | Finding | Action | Effort | Impact | References |
|---|---------|--------|--------|--------|------------|
| 1 | [X.X -- Item Name] RED/AMBER | [action] | [estimate] | [what improves] | [links] |

## Items to Investigate Manually
[All UNKNOWN items with specific questions to answer, PLUS any "could-not-verify" caveats from checks capped at AMBER-with-note under the access-denied (403) rule, PLUS manual-review questions surfaced by any check regardless of its rating]

## AWS Reference Links
[All links grouped by topic]

---

*This report was generated by a Claude Code skill provided as sample code for educational and demonstration purposes only. Findings should be reviewed and validated before acting on them. See the project's README and LICENSE for full terms.*

*Before sharing this report outside your organization, mask or omit the AWS account ID and any cluster ARNs.*
```

### AWS References

Use the pre-verified reference map in `references/report-generation.md` Step 7. Do NOT call the AWS Documentation MCP server during report generation — it adds latency and token cost. All URLs are pre-verified and mapped by section.

Do NOT fabricate URLs beyond the reference map. If a finding doesn't match a specific URL, use the fallback section-level page.
