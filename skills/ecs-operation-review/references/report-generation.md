# Report Generation

## Purpose
After all section checks are complete, generate the ECS Operation Review report. Follow the consistency contract in `scoring-rubric.md`.

## Consistency Checks (MANDATORY before writing)

> The **canonical** consistency contract lives in `scoring-rubric.md` ("Consistency contract (MANDATORY — canonical)"). The list below is the operational checklist that implements it; if they ever differ, `scoring-rubric.md` wins.

1. **Build a consolidated list** of all findings with their ratings from Sections 01-08. Include each **cross-domain duplicate control once**, under its scoring section only (see the "Cross-domain duplicate checks" table in `scoring-rubric.md`: log driver → 6.2, task-role least privilege → 7.1, deployment-failure alerting → 4.5, `RESOURCE:ENI` / ENI density → 2.6, Fargate retirement exposure → 8.4). **Exclude N/A items** from the list (they are neither scored nor investigated).
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
- Count GREEN, AMBER, RED, UNKNOWN. **Do not count N/A items** (see `scoring-rubric.md`).
- Calculate percentages (exclude UNKNOWN and N/A from the denominator).
- **Report coverage next to every percentage:** "N of M items assessable (X% coverage)", where N = GREEN+AMBER+RED and M = all items except N/A. Put this line directly under the Maturity Score table.
- **If UNKNOWN exceeds ~25% of assessable-plus-unknown items, do NOT lead with a headline maturity percentage.** Lead with the coverage figure and a one-line caveat naming the **actual observed cause(s)** of the UNKNOWNs — denied permissions, sections not run, or evidence the APIs cannot expose — do not default to blaming permissions/credentials. First confirm no not-applicable checks were mistakenly booked as UNKNOWN (they belong under N/A and never count toward this threshold; see `scoring-rubric.md`, "N/A vs UNKNOWN"). (Recall 8.5 is UNKNOWN by design and always counts toward UNKNOWN.)

### Step 3: Write Executive Summary
- **Top strengths** (GREEN items with highest operational impact).
- **Top gaps** (RED items, ordered by blast radius: security > availability > cost).
- **One-line coverage statement** ("N of M items assessable, X% coverage") so an exec reading only the summary still sees the coverage signal — mandatory when UNKNOWN exceeds ~25%.
- 2-3 paragraphs. Every rating mentioned must match the consolidated list.

### Step 4: Write Findings Tables
One table per section. Every item from the consolidated list must appear.

### Step 5: Write Prioritized Actions
- **Critical (30 days):** RED items with real availability/security blast radius. Columns: `# | Finding | Impact | Action | References`.
- **Important (90 days):** all AMBER items **plus process/hygiene findings capped there** (see below — capped items may be RED-rated in the findings tables). Same columns.
- **Quick Wins:** items (RED or AMBER) fixable in < 1 hour. Columns: `# | Finding | Action | Effort | Impact | References`.

**Severity capping (avoid false urgency).** A missing `Environment` tag (8.2) and a single-AZ production service must not both land in "Critical — 30 days" — that flattens genuinely different blast radii. **Process- and hygiene-only findings — 8.1 (IaC provenance), 8.2 (tagging), and 8.6 (revision hygiene / quota tracking) — are capped at AMBER and belong in "Important", never "Critical",** even if a strict reading would rate them RED (exception: 8.6 *quota already blocking launches* is a genuine availability issue and may be Critical). If you prefer tiers over capping, split Critical into "Critical — availability/security impact" and "Important — process/hygiene" and place these there. Availability/security REDs (single-AZ prod, no circuit breaker, plaintext secrets, GuardDuty off on Fargate) always stay Critical.

Every entry includes the finding ID and name (e.g., "04.1 - Deployment Circuit Breaker RED").

**One row per finding, root causes annotated.** Do not merge multiple findings into a single row — each keeps its own context, action, and references. **But when several rows share one root cause** (e.g., one single-replica/single-AZ/no-autoscaling service producing rows at 4.4, 5.4, 5.5, and 8.4), annotate every affected row with the shared root cause and group size (e.g., "Related: 4 findings, 1 root cause — see 5.4") so a single fix is not read as four independent problems (see the consistency contract in `scoring-rubric.md`).

**Ordering within Critical AND Important** (blast radius — apply the same category order to both tables):
1. **Security first** - plaintext secrets, over-broad task roles, privileged containers, GuardDuty Runtime Monitoring off on Fargate, public ingress direct to tasks.
2. **Availability next** - no circuit breaker/rollback, single-AZ or single-replica critical services, AZ rebalancing off, missing health-check grace period, missing service autoscaling, managed termination protection off.
3. **Cost last** - no retention policy, resilience-only Spot flags (dollar work -> `ecs-cost-intelligence`).

Within each category, order estate/cluster-wide before single-service. In the **Important** table this ordering (plus the Impact column) keeps availability AMBERs (single-replica, AZ rebalancing off) visibly above capped hygiene items (missing tags, runbook gaps) — do not interleave them.

### Step 6: Write Investigate Manually
All **UNKNOWN** items with specific questions the user should answer (especially Section 08 process items). For check **8.5** (runbooks/on-call/PIR), state in the customer-visible entry that it is **UNKNOWN by design** — process maturity is not readable from the AWS APIs — so the tool limitation is not misread as a customer observability failure. **Do not list N/A items here** — N/A means the check doesn't apply, so there is nothing to investigate (see `scoring-rubric.md`, "N/A vs UNKNOWN"). If useful, N/A items may go in a separate short "Not applicable (with reason)" note that does not affect scoring.

### Step 7: Apply AWS Reference Links

Use the pre-verified reference map below (**all URLs verified live 2026-07-09**). Do NOT call the AWS Documentation MCP server during report generation - it adds latency and token cost. Do NOT fabricate URLs beyond this list; if a finding has no specific match, use the fallback. Re-verify this map whenever the skill is materially updated and bump the date.

**Section 01 - Clusters & Capacity**
- Best practices index: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html`
- Launch types & capacity providers (in-place migration): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-launch-type-comparison.html`
- Auto scaling & capacity management: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability.html`
- Optimize cluster auto scaling: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-speed-up-ec2.html`
- Managed Instances (architect): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html`
- Managed Instances patching / lifecycle: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html`
- Managed Instances capacity providers: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-capacity-providers-concept.html`
- Managed instance draining: `https://aws.amazon.com/blogs/containers/amazon-ecs-enables-easier-ec2-capacity-management-with-managed-instance-draining/`
- Cluster auto scaling deep dive: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html`
- EC2 container instances / agent versions: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-versions.html`
- describe-container-instances (CLI): `https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-container-instances.html`

**Section 02 - Networking**
- Network security best practices: `https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-network.html`
- Connect to AWS services from your VPC: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/networking-connecting-vpc.html`
- Interface VPC endpoints (PrivateLink) for ECS: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html`
- Service Connect: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect.html`
- Native ECS support in VPC Lattice: `https://aws.amazon.com/blogs/aws/streamline-container-application-networking-with-native-amazon-ecs-support-in-amazon-vpc-lattice/`
- ENI trunking (increase task density): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-instance-eni.html`

**Section 03 - Task Definitions**
- Task sizes: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-tasksize.html`
- Container images: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-considerations.html`
- Storage / volumes: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_data_volumes.html`
- Task IAM role: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html`

**Section 04 - Services & Deployment Safety**
- Deployment circuit breaker: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html`
- Configurable circuit breaker settings (Jul 2026): `https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-ecs-circuit-breaker-settings/`
- How CloudWatch alarms detect deployment failures: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html`
- Blue/green deployments: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html`
- Linear/canary deployments (Oct 2025): `https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-built-in-linear-canary-deployments/`
- NLB support for linear/canary (Feb 2026): `https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-ecs-nlb-linear-canary-deployments/`
- Pause/continue deployment controls (May 2026): `https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-ecs-pause-continue-deployments/`
- Service parameters: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-options.html`
- Automate rollbacks with CloudWatch alarms (blog): `https://aws.amazon.com/blogs/containers/automate-rollbacks-for-amazon-ecs-rolling-deployments-with-cloudwatch-alarms/`

**Section 05 - Service Health & Autoscaling**
- Health-check grace period (CreateService API): `https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html`
- Load-balancer health-check tuning: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-healthcheck.html`
- Connection draining: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-connection-draining.html`
- Service auto scaling: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html`
- Optimizing service auto scaling: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-autoscaling-best-practice.html`
- AZ rebalancing: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-rebalancing.html`

**Section 06 - Observability**
- Container Insights (enhanced observability): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-container-insights.html`
- Enhanced-observability metrics: `https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html`
- Send ECS logs to CloudWatch (awslogs): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html`
- LogConfiguration API (stream prefix, delivery mode, max-buffer-size): `https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html`
- ECS account settings (default log driver mode, ENI trunking): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html`
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
- ECS Exec (debugging / interactive access): `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html`

**Section 08 - Operational Processes**
- Fargate task retirement/maintenance: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-maintenance.html`
- Deregister a task-definition revision: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deregister-task-definition-v2.html`
- Service Quotas for Amazon ECS: `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-quotas.html`
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
python3 tools/report_to_html.py <report-filename>.md
```
The converter ships in the skill's `tools/` directory (`tools/report_to_html.py`) — invoke it from there. If a copy has been placed at the workspace root, `python3 report_to_html.py <report-filename>.md` also works.

## Report Template

The generated report should follow this structure (headings, Maturity Score table, one findings table per section, Prioritized Actions split into Critical/Important/Quick Wins, Investigate Manually, AWS Reference Links, then the sample-code disclaimer footer):

- Title line: `# ECS Operation Review Report`
- Header lines: Cluster / Region / Account; Capacity mix; Services count; Date.
- **Confidentiality caution (immediately under the header):** a one-line note such as *"Treat this report as customer-confidential — it contains account IDs, ARNs, security-group findings, and other estate details. Share only with authorized parties."*
- `## Executive Summary` - 2-3 paragraphs, strengths first then gaps; every rating matches findings.
- `## Maturity Score` - table with columns Rating | Count | Percentage for GREEN/AMBER/RED/UNKNOWN (N/A items excluded from the table). The UNKNOWN row shows "—" in the Percentage column — UNKNOWN is excluded from the percentage denominator, so giving it a percentage would make the rows not sum to 100%. Immediately below the table:
  - the **coverage line**: "N of M items assessable (X% coverage)" (see Step 2), and
  - a mandatory **### Scope & limitations** block stating what was and wasn't assessed for this run — which sections ran, any UNKNOWN-heavy areas, and any of the standing blind spots from `SKILL.md` that apply (scheduled/standalone tasks not enumerated; Express Mode services N/A; Windows / ECS Anywhere workloads N/A for Linux/Fargate-assuming checks; API-throttling/partial-coverage caveats). If coverage is below ~75%, say so here and do not lead with a headline percentage.
- `## Findings` - one subsection per section (01-08), each a table: Item | Status | Current State | Recommendation | References.
- `## Prioritized Actions` - three tables (both Critical and Important ordered by blast radius: security > availability > cost — see Step 5):
  - `### Critical (Address within 30 days)` - columns: # | Finding | Impact | Action | References (REDs with availability/security blast radius).
  - `### Important (Address within 90 days)` - columns: # | Finding | Impact | Action | References (all AMBERs, plus severity-capped process/hygiene findings — which may be RED-rated in the findings tables).
  - `### Quick Wins` - columns: # | Finding | Action | Effort | Impact | References.
- `## Items to Investigate Manually` - UNKNOWN items with specific questions.
- `## AWS Reference Links` - links grouped by section (from the Step 7 map).
- Sample-code disclaimer footer (Step 8b).
