---
name: eks-operation-review
description: Day 2 operational-review workflow. Runs the eks-operation-review skill end-to-end — 10-section structured assessment of a live cluster's operational excellence, with GREEN/AMBER/RED ratings and a markdown/HTML report including prioritized actions and AWS reference links.
---

# Operational Review Workflow

> **Part of:** [APEX EKS Hub](../eks.md)
> **Lifecycle:** Day 2 — Operate
> **Skill:** `eks-operation-review` — [SKILL.md](../../skills/eks-operation-review/SKILL.md)

---

## Access Model

This workflow is **read-only**:

- **CAN** issue read-only commands via the EKS MCP server, AWS CLI, and `kubectl get` to discover cluster state
- **CAN** generate a markdown/HTML operational-review report
- **CANNOT** mutate cluster state (no apply, delete, annotate, or scale operations)

The output is an assessment report — the user decides what to do with the findings. Mutations belong to whatever remediation path the user chooses.

Why: Operational reviews are discovery activities. The skill audits ten areas of operational practice and rates each. Acting on the recommendations is a separate, deliberate step.

---

## MCP Server Setup

This skill **requires** the EKS MCP server (`awslabs.eks-mcp-server`) for live cluster reads. Pre-flight Action 3 calls one MCP tool to verify connectivity; if it fails, the skill stops and surfaces troubleshooting steps.

**Setup path**: invoke the apex `eks-mcp-server` skill before running this workflow. Apex does not ship a project-root `.mcp.json`; MCP setup is opt-in and user-driven.

**Optional second MCP server** (`awslabs.aws-documentation-mcp-server`): used by some reference files for live AWS-doc lookups, but the skill's `references/report-generation.md` already ships a pre-verified URL reference map and explicitly deprioritizes the doc-MCP server during report generation. The skill works correctly with only the EKS MCP server configured. If the doc-MCP server is also available, individual reference files may use it for ad-hoc lookups; otherwise they fall back to `WebFetch` and the hardcoded reference map.

---

## Routing

There is one mode for this workflow with two scopes:

1. **Full review** — *"run an operational review on my cluster"*, *"audit my EKS posture"*, *"EKS health check"*. Activates the skill end-to-end across all 10 sections.
2. **Section-scoped review** — *"check my EKS networking"*, *"review RBAC on my cluster"*, *"audit observability on my cluster"*. The skill loads only the relevant reference file(s) and produces a focused report.

**Steps**:

1. Activate the `eks-operation-review` skill
2. The skill discovers clusters (`aws eks list-clusters`), confirms which to assess, then verifies MCP connectivity
3. The skill loads each reference file in section order (or only the matching ones for a scoped request) from `skills/eks-operation-review/references/`
4. The skill produces a markdown report in `reports/` (or workspace root) and optionally converts it to HTML via `tools/report_to_html.py`
5. Present the report and a one-paragraph summary highlighting RED findings and the maturity score

Do **not** re-implement the assessment in this workflow — the skill owns the procedure.

---

## After the Assessment

Read the maturity score and use the rating distribution to set tone:

- **Mostly GREEN, few AMBER, no RED**: cluster is in good operational shape. Note any AMBER as improvement opportunities; no urgent action needed.
- **Several AMBER, some RED**: typical state for production clusters. Walk the user through the Critical (RED) and Important (AMBER) priorities tables in the report.
- **Many RED**: significant gaps. Recommend addressing the security-flagged RED findings first (per the report's blast-radius prioritization). Do not route to upgrade workflows until critical operational gaps are addressed.

For full rating rules and the consistency contract, see [eks-operation-review SKILL.md](../../skills/eks-operation-review/SKILL.md).

---

## Tool Usage Rules

Sourced from the upstream skill — preserved verbatim because they encode invariants the assessment relies on:

1. **Do NOT call any tools when this skill is first activated.** Wait for the user to explicitly ask for a review.
2. **Do NOT read mcp.json or config files as a "check".** The only way to verify the MCP server works is to call an actual tool.
3. **Do NOT hardcode or guess cluster names.** Always discover clusters by listing them first.
4. **Do NOT retry a failed MCP tool call more than once.** If it fails twice, stop and show troubleshooting steps.
5. **Always load the relevant reference file before executing checks for that section.**
6. **Do NOT use the `manage_eks_stacks` MCP tool for cluster discovery or description.** That tool manages CloudFormation stacks, not EKS clusters. Use `aws eks list-clusters` and `aws eks describe-cluster` via Bash for pre-flight, and `list_k8s_resources` for Kubernetes checks.

---

## Reference File Loading

Before executing checks for any section, read the corresponding reference file from `skills/eks-operation-review/references/` using the Read tool.

| User Request | Reference File(s) to Load |
|---|---|
| Full review / assess / audit / health check | ALL files in order: cluster-lifecycle -> addon-management, then report-generation |
| Upgrade / version / deprecated API | `references/cluster-lifecycle.md` |
| IRSA / RBAC / access / pod identity / endpoint | `references/access-identity.md` |
| Logging / metrics / alerting / observability | `references/observability.md` |
| Resource requests / probes / PDB / image tags / storage | `references/workload-configuration.md` |
| IP / subnet / DNS / CoreDNS / network policy | `references/networking.md` |
| Autoscaling / Karpenter / HPA / topology spread | `references/autoscaling.md` |
| Deployment / rollout / CI/CD / graceful shutdown | `references/deployment-practices.md` |
| Runbook / on-call / backup / DR / Velero | `references/operational-processes.md` |
| Add-on / node monitoring / cluster insights | `references/addon-management.md` |
| Generate / write report | `references/report-generation.md` |
| IaC / GitOps / ArgoCD / Flux / drift | `references/infrastructure-as-code.md` |

---

## Assessment Workflow

### Step 0: Pre-flight

This step verifies everything works before starting the assessment. Follow this exact sequence:

**Action 1 — List clusters (discovers clusters)**

Use the AWS CLI to list clusters. Do NOT use the `manage_eks_stacks` MCP tool — it manages CloudFormation stacks, not cluster discovery.

```
aws eks list-clusters --output json
```

- Success → show the cluster list. Ask the user which cluster to assess. If only one cluster, confirm: "I found one cluster: [name]. Shall I assess this one?"
- Failure → STOP. Do NOT retry more than once. Do NOT read config files. Show:

> **Cannot list EKS clusters.** Try these steps:
> 1. Check that AWS credentials work: `aws sts get-caller-identity`
> 2. Check the region: `aws configure get region`
> 3. Verify the EKS MCP server is configured (run apex's `eks-mcp-server` skill to set it up)

Wait for the user to resolve the issue.

**Action 2 — Describe the selected cluster**

Use the AWS CLI to describe the cluster. Do NOT use `manage_eks_stacks` — it looks for CloudFormation stacks, not EKS clusters.

```
aws eks describe-cluster --name <cluster-name> --output json
```

From the response, show:
- Cluster name, Kubernetes version, platform version, region, status
- AWS account ID
- Authentication mode

**Action 3 — Verify MCP connectivity**

Call one MCP tool to confirm the EKS MCP server works (e.g., list Nodes):

```
list_k8s_resources(cluster_name="<cluster-name>", kind="Node", api_version="v1")
```

- Success → MCP server is working. Proceed.
- Failure → STOP. Show:

> **The EKS MCP server isn't responding.** Try these steps:
> 1. Check that Python 3.10+ and uv are installed: `uv --version`
> 2. Test the MCP server: `uvx awslabs.eks-mcp-server@latest`
> 3. Re-run apex's `eks-mcp-server` skill to verify setup

Wait for the user to resolve the issue.

**Action 4 — Confirm**

Ask: *"Ready to start the assessment on [cluster-name] (v[version])?"*

Proceed only after the user confirms.

### Steps 1-10: Run Assessment

Read each reference file in section order using the Read tool. For each section:

1. Read the reference file from `skills/eks-operation-review/references/`
2. Execute the checks described in it
3. Rate each item using the rubric below

**Error recovery:** If a section fails entirely (MCP server unreachable, permissions denied for all checks in that section, or repeated timeouts), mark all items in that section as UNKNOWN with a note explaining the failure reason, then proceed to the next section. Do not let one failed section block the rest of the assessment.

### Step 11: Generate Report

Read `skills/eks-operation-review/references/report-generation.md` and produce the report.

---

## Rating Rubric

| Rating | Meaning |
|--------|---------|
| GREEN | Fully implemented — matches EKS best practices |
| AMBER | Partial or inconsistent — improvement opportunity |
| RED | Not implemented or significant gap — action needed |
| UNKNOWN | Cannot be determined from cluster data — investigate manually |

### Rules

- Only rate based on what was actually observed — never assume
- If a check fails or returns no data, mark UNKNOWN
- Prioritize by blast radius: security > availability > cost
- Every RED finding must have a specific, actionable recommendation

---

## Report Format

### Consistency Rules (MANDATORY)

1. **Ratings must be consistent across the entire report.** If 4.1 is RED in the findings table, it must appear as RED everywhere — executive summary, prioritized actions, quick wins.
2. **Prioritized Actions must reference the finding ID.** Write "4.1 — Control Plane Logging RED" not just "Enable logging".
3. **Every RED must appear in Critical or Important.** Every AMBER must appear in Important or Quick Wins. Nothing rated RED/AMBER can be missing from Prioritized Actions.
4. **Executive Summary must match the findings.** Do not call something a "critical gap" if it's AMBER, or skip a RED item.

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
| Rating | Count | Percentage |
|--------|-------|------------|
| GREEN | X | X% |
| AMBER | X | X% |
| RED | X | X% |
| UNKNOWN | X | -- |

## Findings

### Section 01 — Cluster Lifecycle & Upgrades
| Item | Status | Current State | Recommendation | References |
|------|--------|---------------|----------------|------------|

[Repeat for all 10 sections]

## Prioritized Actions

### Critical (Address within 30 days)
| # | Finding | Action | References |
|---|---------|--------|------------|
| 1 | [X.X — Item Name] RED | [specific action] | [links] |

### Important (Address within 90 days)
| # | Finding | Action | References |
|---|---------|--------|------------|
| 1 | [X.X — Item Name] AMBER | [specific action] | [links] |

### Quick Wins
| # | Finding | Action | Effort | Impact | References |
|---|---------|--------|--------|--------|------------|
| 1 | [X.X — Item Name] | [action] | [estimate] | [what improves] | [links] |

## Items to Investigate Manually
[UNKNOWN items with specific questions to answer]

## AWS Reference Links
[All links grouped by topic]

---

*This report was generated by a Claude Code skill provided as sample code for educational and demonstration purposes only. Findings should be reviewed and validated before acting on them. See the project's README and LICENSE for full terms.*
```

### AWS References

Use the pre-verified reference map in `references/report-generation.md` Step 7. Do NOT call the AWS Documentation MCP server during report generation — it adds latency and token cost. All URLs are pre-verified and mapped by section.

Do NOT fabricate URLs beyond the reference map. If a finding doesn't match a specific URL, use the fallback section-level page.

---

## Skills Reference

- **Primary:** `eks-operation-review` — owns the 10-section assessment, rating logic, and report generation
- **Optional:** `eks-mcp-server` — guides MCP setup; this workflow has a hard dependency on the EKS MCP server
- **Adjacent:** `eks-upgrade-check` — separately assesses upgrade readiness; if a review's RED finding is "version on extended support," route to `apex:eks-upgrade-check` for the upgrade-readiness workflow
