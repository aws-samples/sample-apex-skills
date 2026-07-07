---
title: "Report Generation"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/references/report-generation.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-operation-review/references/report-generation.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/references/report-generation.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [eks-operation-review](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review), also maintained by the APEX team.
:::

# Report Generation

## Purpose
After all section checks are complete, generate the EKS Operation Review report.

## Consistency Checks (MANDATORY before writing)

Before writing the report, validate consistency:

1. **Build a master list** of all findings with their ratings from sections 01-10
2. **For each RED item:** confirm it appears in "Critical" or "Important" prioritized actions
3. **For each AMBER item:** confirm it appears in "Important" or "Quick Wins"
4. **For the Executive Summary:** only mention ratings that match the master list — do not call something a "critical gap" if it's AMBER, or omit a RED from the summary
5. **For Prioritized Actions:** every entry must reference the finding ID (e.g., "4.1 — Control Plane Logging")

## Workflow

### Step 1: Build Master Finding List

```
| Section | Item ID | Item Name | Rating |
```

### Step 2: Calculate Maturity Score

- Count GREEN, AMBER, RED, UNKNOWN
- Calculate percentages (exclude UNKNOWN from denominator)

### Step 3: Write Executive Summary

From the master list, identify:
- **Top strengths** (GREEN items with highest operational impact)
- **Top gaps** (RED items, ordered by blast radius: security > availability > cost)
- Write 2-3 paragraphs. Every rating mentioned must match the master list.

### Step 4: Write Findings Tables

One table per section. Every item from the master list must appear.

### Step 5: Write Prioritized Actions

Cross-reference against the master list:
- **Critical (30 days):** All RED items. Column: `Finding | Action | References`
- **Important (90 days):** All AMBER items. Column: `Finding | Action | References`
- **Quick Wins:** Items (RED or AMBER) fixable in < 1 hour. Column: `Finding | Action | Effort | Impact | References`

Every entry must include the finding ID and name (e.g., "4.1 — Control Plane Logging 🔴").

**One row per finding.** Never bundle multiple findings into a single row (e.g., "2.2/2.3 — GitOps & Drift Detection"). Each finding has its own context, action, and references — collapsing them hides information and breaks the "every RED must appear in Critical" consistency rule. If two findings genuinely share an action, list them on separate rows that point to the same action.

**Ordering within Critical:** List RED items by blast radius category:
1. Security first — public API endpoint, hardcoded credentials, no PSA/network policies, overly broad RBAC
2. Availability next — no PDBs, single-replica critical workloads, missing health probes, no alerting
3. Cost last — extended support billing, deprecated storage classes

Within each category, order by scope (cluster-wide before namespace-scoped).

### Step 6: Write Investigate Manually

All UNKNOWN items with specific questions the user should answer.

### Step 7: Apply AWS Reference Links

Use the pre-verified reference map below. Do NOT call the AWS Documentation MCP server — it adds latency and token cost with minimal benefit.

**Section 01 — Cluster Lifecycle & Upgrades**
- Version calendar: `https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html`
- Upgrade cluster: `https://docs.aws.amazon.com/eks/latest/userguide/update-cluster.html`
- Best practices for upgrades: `https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html`
- Platform versions: `https://docs.aws.amazon.com/eks/latest/userguide/platform-versions.html`
- Managed node groups: `https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html`
- EKS Auto Mode: `https://docs.aws.amazon.com/eks/latest/userguide/automode.html`

**Section 02 — Infrastructure as Code & GitOps**
- EKS User Guide (general): `https://docs.aws.amazon.com/eks/latest/userguide/`
- Best practices (general): `https://docs.aws.amazon.com/eks/latest/best-practices/`

**Section 03 — Access & Identity**
- IRSA: `https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html`
- EKS Pod Identity: `https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html`
- Access entries: `https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html`
- Grant K8s access: `https://docs.aws.amazon.com/eks/latest/userguide/grant-k8s-access.html`
- RBAC hardening: `https://docs.aws.amazon.com/eks/latest/userguide/rbac-hardening.html`
- API server endpoint: `https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html`
- Security best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/security.html`
- Pod Security Standards: `https://docs.aws.amazon.com/eks/latest/best-practices/pod-security.html`

**Section 04 — Observability**
- Control plane logging: `https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html`
- Observability overview: `https://docs.aws.amazon.com/eks/latest/userguide/eks-observe.html`

**Section 05 — Workload Configuration**
- EBS CSI driver: `https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html`
- Reliability best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/reliability.html`

**Section 06 — Networking**
- VPC CNI: `https://docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html`
- Prefix delegation: `https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses.html`
- Custom networking: `https://docs.aws.amazon.com/eks/latest/userguide/cni-custom-network.html`
- CoreDNS: `https://docs.aws.amazon.com/eks/latest/userguide/managing-coredns.html`
- Networking best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/networking.html`

**Section 07 — Autoscaling**
- Karpenter best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/karpenter.html`
- Scalability best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/scalability.html`
- Cost optimization: `https://docs.aws.amazon.com/eks/latest/best-practices/cost-opt.html`

**Section 08 — Deployment Practices**
- Reliability best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/reliability.html`

**Section 09 — Operational Processes**
- Reliability best practices: `https://docs.aws.amazon.com/eks/latest/best-practices/reliability.html`

**Section 10 — Add-on Management**
- Managed add-ons: `https://docs.aws.amazon.com/eks/latest/userguide/managing-add-ons.html`
- Node health & auto-repair: `https://docs.aws.amazon.com/eks/latest/userguide/node-health.html`

**Fallback (any topic):**
- EKS Best Practices Guide: `https://docs.aws.amazon.com/eks/latest/best-practices/`
- EKS User Guide: `https://docs.aws.amazon.com/eks/latest/userguide/`

Do NOT fabricate URLs beyond this list. If a finding doesn't match a specific URL above, use the fallback section-level page.

### Step 8: Final Consistency Validation

Before outputting, scan the report for:
- Any RED item missing from Prioritized Actions → add it
- Any item mentioned in Executive Summary with wrong rating → fix it
- Any Prioritized Action without a finding ID → add the ID

### Step 8b: Append Sample-Code Disclaimer

Add the following footer at the very end of the report, after the AWS Reference Links section, separated by a horizontal rule:

```markdown
---

*This report was generated by a Claude Code skill provided as sample code for educational and demonstration purposes only. Findings should be reviewed and validated before acting on them. See the project's README and LICENSE for full terms.*
```

### Step 9: Write the Report File

Write the report to the **workspace directory**. The file must be created inside the current workspace.

**Filename format:** `EKS-Operation-Review-<cluster-name>-<YYYY-MM-DD>-<HHMM>.md`

**Example:** `EKS-Operation-Review-demo-cluster-2026-03-22-1830.md`

The file should be written to the workspace root or a `reports/` subfolder within the workspace. Do NOT use absolute paths outside the workspace.

### Step 10: Offer HTML Conversion

Ask: "Would you like me to convert the report to HTML?"

If yes, run the conversion script — do NOT generate HTML manually. Execute this command:

```bash
python3 report_to_html.py <report-filename>.md
```

Run this from the workspace root where `report_to_html.py` is located. If the script is not found in the workspace root, check `tools/report_to_html.py`.

Do NOT create HTML by hand. Always use the script.
