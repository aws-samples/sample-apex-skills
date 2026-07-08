---
title: "Report Generation"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/report-generation.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-operation-review/references/report-generation.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-operation-review/references/report-generation.md). Edit the source, not this page.
:::

# Report Generation

## Purpose
After all section checks are complete, generate the ECS Operation Review report. Follow the consistency contract in `scoring-rubric.md`.

## Consistency Checks (MANDATORY before writing)

1. **Build a consolidated list** of all findings with their ratings from Sections 01-08.
2. **For each RED item:** confirm it appears in "Critical" or "Important" prioritized actions.
3. **For each AMBER item:** confirm it appears in "Important" or "Quick Wins".
4. **Executive Summary:** only mention ratings that match the consolidated list - never call an AMBER a "critical gap" or omit a RED.
5. **Prioritized Actions:** every entry references the finding ID (e.g., "04.1 - Deployment Circuit Breaker").

## Workflow

### Step 1: Build consolidated finding list
```
| Section | Item ID | Item Name | Rating |
```

### Step 2: Calculate Maturity Score
- Count GREEN, AMBER, RED, UNKNOWN.
- Calculate percentages (exclude UNKNOWN from the denominator).

### Step 3: Write Executive Summary
- **Top strengths** (GREEN items with highest operational impact).
- **Top gaps** (RED items, ordered by blast radius: security > availability > cost).
- 2-3 paragraphs. Every rating mentioned must match the consolidated list.

### Step 4: Write Findings Tables
One table per section. Every item from the consolidated list must appear.

### Step 5: Write Prioritized Actions
- **Critical (30 days):** all RED items. Columns: `# | Finding | Action | References`.
- **Important (90 days):** all AMBER items. Same columns.
- **Quick Wins:** items (RED or AMBER) fixable in < 1 hour. Columns: `# | Finding | Action | Effort | Impact | References`.

Every entry includes the finding ID and name (e.g., "04.1 - Deployment Circuit Breaker RED").

**One row per finding.** Never bundle multiple findings into a single row - each has its own context, action, and references.

**Ordering within Critical** (blast radius):
1. **Security first** - plaintext secrets, over-broad task roles, privileged containers, GuardDuty Runtime Monitoring off on Fargate, public ingress direct to tasks.
2. **Availability next** - no circuit breaker/rollback, single-AZ or single-replica critical services, AZ rebalancing off, missing health-check grace period, missing service autoscaling, managed termination protection off.
3. **Cost last** - no retention policy, resilience-only Spot flags (dollar work -> `ecs-cost-intelligence`).

Within each category, order estate/cluster-wide before single-service.

### Step 6: Write Investigate Manually
All UNKNOWN items with specific questions the user should answer (especially Section 08 process items).

### Step 7: Apply AWS Reference Links

Use the pre-verified reference map below. Do NOT call the AWS Documentation MCP server during report generation - it adds latency and token cost. Do NOT fabricate URLs beyond this list; if a finding has no specific match, use the fallback.

**Section 01 - Clusters & Capacity**
- Best practices index: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html`
- Auto scaling & capacity management: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability.html`
- Optimize cluster auto scaling: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html`
- Managed Instances (architect): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html`
- Managed Instances capacity providers: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-capacity-providers-concept.html`
- Managed instance draining: `https://aws.amazon.com/blogs/containers/amazon-ecs-enables-easier-ec2-capacity-management-with-managed-instance-draining/`
- Cluster auto scaling deep dive: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html`

**Section 02 - Networking**
- Network security best practices: `https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-network.html`
- Connect to AWS services from your VPC: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/networking-connecting-vpc.html`
- Service Connect: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect.html`
- Native ECS support in VPC Lattice: `https://aws.amazon.com/blogs/aws/streamline-container-application-networking-with-native-amazon-ecs-support-in-amazon-vpc-lattice/`

**Section 03 - Task Definitions**
- Task sizes: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-tasksize.html`
- Container images: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-considerations.html`
- Storage / volumes: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_data_volumes.html`
- Task IAM role: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html`

**Section 04 - Services & Deployment Safety**
- Deployment circuit breaker: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html`
- Configurable circuit breaker settings (Jul 2026): `https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-ecs-circuit-breaker-settings/`
- Blue/green deployments: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html`
- Linear/canary deployments (Oct 2025): `https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-built-in-linear-canary-deployments/`
- Pause/continue deployment controls (May 2026): `https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/`
- Service parameters: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-options.html`
- Automate rollbacks with CloudWatch alarms: `https://aws.amazon.com/blogs/containers/automate-rollbacks-for-amazon-ecs-rolling-deployments-with-cloudwatch-alarms/`

**Section 05 - Service Health & Autoscaling**
- Health-check grace period: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-healthcheck.html`
- Connection draining: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-connection-draining.html`
- Service auto scaling: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html`
- Optimizing service auto scaling: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-autoscaling-best-practice.html`
- AZ rebalancing: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-rebalancing.html`

**Section 06 - Observability**
- Container Insights (enhanced observability): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html`
- Enhanced-observability metrics: `https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html`
- FireLens: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html`
- CloudWatch Application Signals on ECS: `https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-ECSMain.html`
- Monitor ECS events with EventBridge filtering: `https://aws.amazon.com/blogs/containers/monitor-amazon-ecs-events-with-amazon-eventbridge-filtering/`

**Section 07 - Security Posture**
- Security best practices: `https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html`
- Task & container security: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-tasks-containers.html`
- Secrets (Secrets Manager): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data-tutorial.html`
- Secrets (SSM Parameter Store): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-app-ssm-paramstore.html`
- Compliance & security (GuardDuty): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-compliance.html`
- GuardDuty Runtime Monitoring for Fargate (ECS): `https://docs.aws.amazon.com/guardduty/latest/ug/how-runtime-monitoring-works-ecs-fargate.html`
- Security Hub CSPM controls for ECS: `https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html`

**Section 08 - Operational Processes**
- Fargate task retirement/maintenance: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-maintenance.html`
- Deregister a task-definition revision: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deregister-task-definition-v2.html`
- Best practices index: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html`

**Fallback (any topic):**
- ECS Best Practices Guide: `https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/`
- ECS Developer Guide: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/`

### Step 8: Final Consistency Validation
Before outputting, scan for:
- Any RED item missing from Prioritized Actions -> add it.
- Any item mentioned in the Executive Summary with the wrong rating -> fix it.
- Any Prioritized Action without a finding ID -> add the ID.

### Step 8b: Append Sample-Code Disclaimer
Add this footer at the very end, after the AWS Reference Links section, separated by a horizontal rule:

    ---

    *This report was generated by a Claude Code skill provided as sample code for educational and demonstration purposes only. Findings should be reviewed and validated before acting on them. See the project's README and LICENSE for full terms.*

### Step 9: Write the Report File
Write the report to the **workspace directory** (workspace root or a `reports/` subfolder). Do NOT use absolute paths outside the workspace.

**Filename format:** `ECS-Operation-Review-<cluster-name>-<YYYY-MM-DD>-<HHMM>.md`
**Example:** `ECS-Operation-Review-prod-cluster-2026-07-08-1830.md`

### Step 10: Offer HTML Conversion
Ask: "Would you like me to convert the report to HTML?" If yes, run the script - do NOT generate HTML by hand:
```bash
python3 report_to_html.py <report-filename>.md
```
Run from the workspace root where `report_to_html.py` is located; if not found there, use `tools/report_to_html.py`.

## Report Template

The generated report should follow this structure (headings, Maturity Score table, one findings table per section, Prioritized Actions split into Critical/Important/Quick Wins, Investigate Manually, AWS Reference Links, then the sample-code disclaimer footer):

- Title line: `# ECS Operation Review Report`
- Header lines: Cluster / Region / Account; Capacity mix; Services count; Date.
- `## Executive Summary` - 2-3 paragraphs, strengths first then gaps; every rating matches findings.
- `## Maturity Score` - table with columns Rating | Count | Percentage for GREEN/AMBER/RED/UNKNOWN.
- `## Findings` - one subsection per section (01-08), each a table: Item | Status | Current State | Recommendation | References.
- `## Prioritized Actions` - three tables:
  - `### Critical (Address within 30 days)` - columns: # | Finding | Action | References (all RED).
  - `### Important (Address within 90 days)` - columns: # | Finding | Action | References (all AMBER).
  - `### Quick Wins` - columns: # | Finding | Action | Effort | Impact | References.
- `## Items to Investigate Manually` - UNKNOWN items with specific questions.
- `## AWS Reference Links` - links grouped by section (from the Step 7 map).
- Sample-code disclaimer footer (Step 8b).
