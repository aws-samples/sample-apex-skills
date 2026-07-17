---
title: "eks-cost-intelligence"
description: "EKS cost efficiency assessment — 6-dimension analysis, weighted 0-100 Cost Score, and dollar-quantified remediation report. Analyzes compute efficiency, Spot/Graviton adoption, networking, storage, observability, and idle resources. Triggers on cost audit, cost review, cost driver analysis, FinOps assessment, spending efficiency, waste identification, over-provisioned workloads, or cost attribution by namespace. Combines live Cost Explorer data, CloudWatch utilization metrics, and Kubernetes resource analysis."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/SKILL.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-cost-intelligence/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/SKILL.md). Edit the source, not this page.
:::


# EKS Cost Intelligence — DevOps Agent Port

## Overview

This skill performs a live cost efficiency assessment of an EKS cluster. It connects via AWS APIs and the Kubernetes API, analyzes cost signals across 6 dimensions, calculates a weighted Cost Score (0-100), and produces a detailed report with dollar-quantified findings, prioritized recommendations, and pre-filled remediation snippets.

This skill is focused on **live cost assessment** — answering the question: "Where is this cluster wasting money, and how much can I save?"

## Prerequisites

### Required IAM Permissions (Agent Space Role)

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-cost-intelligence/references/iam-policy.json) — attach it directly to your Agent Space execution role.

The following permissions are included:

**EKS (required):**
- `eks:ListClusters`
- `eks:DescribeCluster`
- `eks:ListNodegroups`
- `eks:DescribeNodegroup`
- `eks:ListAddons`
- `eks:ListFargateProfiles`
- `eks:DescribeFargateProfile`

**EC2 (required):**
- `ec2:DescribeInstances`
- `ec2:DescribeVolumes`
- `ec2:DescribeSubnets`
- `ec2:DescribeVpcEndpoints`

**Elastic Load Balancing (required):**
- `elasticloadbalancing:DescribeLoadBalancers`
- `elasticloadbalancing:DescribeTargetGroups`
- `elasticloadbalancing:DescribeTargetHealth`

**Cost Explorer (optional — enables dollar-accurate spend):**
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`

**CloudWatch (optional — enables utilization-based analysis):**
- `cloudwatch:GetMetricData`
- `cloudwatch:ListMetrics`
- `logs:StartQuery`
- `logs:GetQueryResults`

**Amazon EFS (optional — enables EFS Intelligent-Tiering/lifecycle checks in the storage dimension):**
- `elasticfilesystem:DescribeFileSystems`
- `elasticfilesystem:DescribeLifecycleConfiguration`

**Kubernetes API access (required):**
- The Agent Space must have Kubernetes API access to the target cluster (via EKS Access Entry or aws-auth ConfigMap)
- Required RBAC: `get`, `list` on pods, nodes, deployments, services, persistentvolumeclaims, configmaps, secrets, namespaces, events, endpointslices

---

## When to Use

**Activate when the goal involves:**
- Identifying waste — "what's the biggest cost driver?" or "where am I over-provisioned?"
- Running a cost audit, cost review, or spending assessment against a live cluster
- Producing dollar-denominated findings to justify optimization work
- Cost attribution by namespace, team, or workload
- Preparing a FinOps review or cost reduction initiative
- Measuring a cluster's cost efficiency score (0-100)

**Out of scope (do not assess):**
- General cost optimization best practices without a live cluster — advisory guidance, not a live assessment
- Cluster design for cost efficiency — architecture decisions, not point-in-time measurement
- Operational health reviews — configuration quality, not cost posture
- Cluster discovery or reconnaissance — topology mapping, not cost analysis
- Upgrade readiness — version compatibility, not spending efficiency

---

## Assessment Workflow

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. It proceeds through discovery and assessment without pausing
> for user input. When the target cluster is ambiguous, it assesses all discovered
> clusters. When a non-recoverable error occurs (API permission failure, no clusters
> found, cluster in failed state), it logs the error in the report and terminates.

**Error output format:**

```
## Assessment Error — <one-line reason>
**Condition:** <which check failed>
**What was found:** <observed state>
**Recommendation:** <remediation guidance for next run>
```

### Step 0: Pre-flight — Cluster Discovery and Validation

**Action 1 — Discover clusters**

Use the EKS ListClusters API to discover available clusters in the current region.

**Decision table:**

| Condition | Action |
|-----------|--------|
| API call fails (auth/permission error) | **Abort with error** — log "Cannot access EKS. The agent role requires `eks:ListClusters` permission for the configured region." in the report and terminate this assessment. |
| Zero clusters returned | **Abort with error** — log "No EKS clusters found in this region." in the report and terminate this assessment. |
| Exactly one cluster found, none named in request | **Proceed** — state which cluster was auto-selected |
| Multiple clusters found, one named in request | **Proceed** — use the named cluster |
| Multiple clusters found, none named in request | **Proceed** — assess **all** discovered clusters. Note in the report that no specific cluster was targeted, so all clusters in the region are included. |

**Action 2 — Describe the selected cluster**

Use the EKS DescribeCluster API for the target cluster. Extract: cluster name, Kubernetes version, platform version, region, status, account ID.

**Action 3 — Validate cluster status**

| Cluster Status | Action |
|----------------|--------|
| `ACTIVE` | **Proceed** |
| `CREATING` / `UPDATING` / `DELETING` | **Skip cluster** — log "Cluster `<name>` is in `<status>` state; skipping until operation completes." If this is the only cluster, terminate with error report. |
| `FAILED` | **Skip cluster** — log "Cluster `<name>` is in FAILED state; recovery required before cost assessment." If this is the only cluster, terminate with error report. |

**Action 4 — Gather cluster context**

Collect the following using AWS and Kubernetes APIs:
- Kubernetes version and platform version (from DescribeCluster response)
- Node groups: use EKS ListNodegroups and DescribeNodegroup APIs for instance types, scaling config, capacity type (ON_DEMAND/SPOT)
- Add-ons: use EKS ListAddons API
- Fargate profiles: use EKS ListFargateProfiles API — if any profiles exist, use DescribeFargateProfile for each, note which namespaces/label selectors are Fargate-scheduled, and read `references/fargate-costs.md`. Fargate pods are billed on rounded-up pod requests (not node capacity), so exclude them from node-based checks and add the Fargate-specific checks to Steps 1–2.
- Node inventory: use Kubernetes API to list nodes with labels and capacity info
- Namespace list: use Kubernetes API to list namespaces

**Action 5 — Proceed to assessment**

Emit cluster summary (name, version, node count, region, account) and immediately begin Step 1. No confirmation required.

### Step 1: Compute Efficiency Assessment

Read `references/compute-efficiency.md` before executing checks.

Checks:
- CPU and memory request-to-utilization ratios across non-system namespaces
- Over-provisioned workloads (requests exceed utilization by threshold)
- Low-utilization nodes indicating consolidation opportunities
- Karpenter consolidation effectiveness (where installed)
- Workloads without resource requests or limits
- Fargate pod request right-sizing against Fargate's vCPU/memory combinations — only when Step 0 found Fargate profiles (read `references/fargate-costs.md`, Check F1)

Data collection uses:
- Kubernetes API to list pods with resource requests/limits per namespace
- CloudWatch Container Insights metrics (pod CPU/memory utilization) via CloudWatch GetMetricData API
- Kubernetes API to list nodes with allocatable resources and current allocations

If metrics-server or Container Insights is unavailable, mark utilization checks as SKIPPED and proceed with request-only analysis.

### Step 2: Spot/Graviton Adoption Assessment

Read `references/spot-graviton-adoption.md` before executing checks.

Checks:
- Graviton (arm64) adoption percentage vs x86 (amd64)
- Node groups/NodePools without arm64 in allowed architectures
- Workloads with explicit amd64 affinity that could run on arm64
- Spot vs On-Demand capacity percentage
- Stateless multi-replica workloads on On-Demand only
- Instance type diversity for Spot availability
- Node Termination Handler or Karpenter interruption handling
- Interruption-tolerant workloads running on Fargate (EKS has no Fargate Spot) — only when Step 0 found Fargate profiles (read `references/fargate-costs.md`, Check F2)

Data collection uses:
- Kubernetes API to list nodes (labels: `kubernetes.io/arch`, `karpenter.sh/capacity-type`, `eks.amazonaws.com/capacityType`)
- EKS DescribeNodegroup API for capacity type and instance types
- Kubernetes API to list deployments/statefulsets for affinity rules and replica counts

### Step 3: Networking Cost Assessment

Read `references/networking-costs.md` before executing checks.

Checks:
- Topology-aware routing configuration on cross-AZ services
- Instance mode vs IP mode on load balancers
- VPC endpoints for ECR, S3, STS
- Cross-AZ traffic potential based on pod distribution
- NAT Gateway cost estimation

Data collection uses:
- Kubernetes API to list services (annotations for topology hints, target-type)
- Kubernetes API to list EndpointSlices (zone distribution)
- EC2 DescribeVpcEndpoints API for existing endpoints
- CloudWatch GetMetricData API for NAT Gateway bytes processed

### Step 4: Storage Cost Assessment

Read `references/storage-costs.md` before executing checks.

Checks:
- PersistentVolumes using gp2 (flag for gp3 migration)
- PVCs bound but not mounted by any running pod
- Over-provisioned volumes (used vs provisioned capacity)
- EFS Intelligent-Tiering and lifecycle policies

Data collection uses:
- Kubernetes API to list PersistentVolumes and PersistentVolumeClaims
- Kubernetes API to list pods (volumeMounts cross-reference)
- EC2 DescribeVolumes API for volume type, size, and state
- EFS DescribeFileSystems and DescribeLifecycleConfiguration APIs

### Step 5: Observability Cost Assessment

Read `references/observability-costs.md` before executing checks.

Checks:
- EKS control plane logging configuration (all log types enabled unnecessarily)
- High-cardinality metric sources (Prometheus scrape configs, CloudWatch agent)
- DEBUG/TRACE log levels in production namespaces
- Log filtering/sampling configurations (FluentBit, CloudWatch agent)

Data collection uses:
- EKS DescribeCluster API (logging configuration)
- CloudWatch GetMetricData API (log group ingestion bytes)
- Kubernetes API to list ConfigMaps (FluentBit, CloudWatch agent, ADOT configs)
- Kubernetes API to list pods (environment variables for log levels)

### Step 6: Idle Resource Detection

Read `references/idle-resources.md` before executing checks.

Checks:
- Deployments scaled to zero replicas for extended periods
- LoadBalancer Services with no healthy backend endpoints
- Namespaces with no running workloads but allocated quotas
- Orphaned ConfigMaps and Secrets not referenced by running workloads

Data collection uses:
- Kubernetes API to list deployments (replicas=0, last-update timestamps)
- Kubernetes API to list services of type LoadBalancer and their endpoints
- ELB DescribeTargetHealth API for backend health status
- Kubernetes API to list namespaces, resource quotas, and running pods per namespace

### Step 7: Score Calculation

Read `references/report-generation.md` for the scoring algorithm.

Apply the scoring model:
- Start at 100 points
- Apply severity-weighted deductions per dimension (capped at dimension maximum)
- Skipped dimensions contribute zero deduction
- Classify final score: OPTIMIZED (90-100), GOOD (75-89), FAIR (60-74), NEEDS_WORK (40-59), CRITICAL (0-39)

### Step 8: Report Generation

Read `references/report-generation.md` for the report template.

Generate the report directly in markdown:
1. Build master finding list sorted by severity then savings
2. Generate markdown report using the template from `references/report-generation.md`
3. Use filename pattern: `EKS-Cost-Intelligence-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

The report includes:
- Executive summary with total estimated spend and projected savings
- Cost Score with classification and per-dimension breakdown
- Prioritized recommendations sorted by savings impact
- Per-dimension findings with remediation snippets
- Methodology and confidence notes
- Disclaimer footer

---

## Cost Score

The skill calculates a weighted cost efficiency score:

| Dimension | Max Deduction | What It Measures |
|-----------|--------------|-----------------|
| Compute Efficiency | 25 pts | CPU/memory waste, over-provisioning, missing requests |
| Spot/Graviton Adoption | 20 pts | Spot percentage, Graviton eligibility, instance diversity |
| Networking Costs | 15 pts | Cross-AZ traffic, VPC endpoints, topology routing |
| Storage Costs | 15 pts | gp2->gp3, unused PVCs, oversized volumes |
| Observability Costs | 10 pts | Control plane logging, metric cardinality, log levels |
| Idle Resources | 15 pts | Zero-scale deploys, orphaned LBs, empty namespaces |

**Score Classification:**
- 90-100: **OPTIMIZED** — Excellent cost efficiency
- 75-89: **GOOD** — Minor optimization opportunities
- 60-74: **FAIR** — Several areas need attention
- 40-59: **NEEDS_WORK** — Significant waste detected
- 0-39: **CRITICAL** — Major cost inefficiencies across multiple dimensions

**Key differences from eks-upgrade-check scoring:**
- No hard-blocker override (cost issues don't prevent cluster operation)
- Severity-weighted deductions within each dimension
- Skipped dimensions excluded entirely (not penalized)

---

## Data Sources

| Source | Access Method | What It Provides |
|--------|--------------|-----------------|
| **AWS Cost Explorer** | Cost Explorer GetCostAndUsage API | Actual spend by service/tag |
| **CloudWatch Container Insights** | CloudWatch GetMetricData API | CPU/memory utilization per pod/node |
| **Kubernetes API** | Kubernetes list/get operations | Resource requests, limits, replica counts, PVCs |
| **EC2 API** | EC2 DescribeInstances API | Instance types, pricing tier, Spot vs On-Demand |

If Cost Explorer is unavailable, the skill falls back to node-based cost estimation (see `references/cost-estimation-fallback.md`).

### Default Time Window

Cost Explorer queries use a **7-day lookback by default** (matching the 7-day window used for CloudWatch utilization checks). If the request names a different window (e.g., "last 30 days"), apply the requested window to all Cost Explorer queries. Whichever window is used, record it in the report metadata (`Analysis Window` field) so findings are reproducible and comparable across runs.

---

## Out of Scope (v1)

The following are intentionally excluded from the initial release and may be added in future versions:

| Area | Rationale |
|------|-----------|
| **Savings Plans / RI coverage scoring** | Data is collected (see `cost-data-collection.md`) but not scored as a dimension. SP/RI decisions are account-level purchasing decisions, not cluster-level configuration. Findings are surfaced as informational notes when coverage < 70%, but do not contribute to the Cost Score. |
| **Namespace/team cost attribution as a scored dimension** | The skill reports namespace cost allocation in the report's methodology section, but does not score attribution quality. Attribution is an observability concern, not a waste indicator. |
| **GPU utilization efficiency** | Only relevant for ML-heavy clusters. Deferred to a future enhancement. |
| **Non-prod time-based downscaling** | High-ROI quick win but requires time-series analysis beyond a point-in-time assessment. Planned for Idle Resources dimension enhancement. |
| **Internet egress optimization** | Covered partially by NAT Gateway analysis; full egress optimization is out of scope. |

---

## Operational Rules

1. **Do NOT hardcode or guess cluster names.** Always discover clusters by listing them first.
2. **Do NOT retry a failed API call more than once.** If it fails twice, log the failure, skip that check, and continue.
3. **Always read the relevant reference file before executing checks for that dimension.**
4. **Do NOT duplicate general advisory content.** Keep recommendations specific to cost findings with actionable remediation steps.
5. **Emit findings as structured output** following the schema in `references/findings-format.md`.

---

## Steering File Map

Before executing checks for any dimension, read the corresponding reference file from `references/`.

| User Request | Reference File(s) to Load |
|---|---|
| Full cost assessment / audit / review | ALL dimension files in order (Steps 1-6), then `report-generation.md` |
| Compute efficiency / over-provisioning / CPU waste | `references/compute-efficiency.md` |
| Spot / Graviton / instance types / arm64 | `references/spot-graviton-adoption.md` |
| Networking costs / cross-AZ / NAT / VPC endpoints | `references/networking-costs.md` |
| Storage costs / gp2 / PVC / EBS | `references/storage-costs.md` |
| Observability / logging / metrics / cardinality | `references/observability-costs.md` |
| Idle resources / unused / orphaned / zero-scale | `references/idle-resources.md` |
| Fargate profiles / Fargate pod pricing / request rounding | `references/fargate-costs.md` |
| Score calculation / scoring algorithm | `references/report-generation.md` |
| Generate report / produce report | `references/report-generation.md` |
| Cost data collection / API calls | `references/cost-data-collection.md` |
| Waste formulas / dollar calculation | `references/waste-calculation.md` |
| Fallback estimation / no Cost Explorer | `references/cost-estimation-fallback.md` |
| Finding format / output schema | `references/findings-format.md` |

---

## Report Output

- **Format:** Markdown
- **Filename:** `EKS-Cost-Intelligence-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

The agent generates the report directly — no external conversion tools required.

The report includes:
- Executive summary with total estimated spend and projected savings
- Cost Score with classification and per-dimension breakdown
- Prioritized recommendations sorted by savings impact
- Per-dimension findings with remediation snippets
- Methodology and confidence notes
- Disclaimer footer

---

*This skill is provided as sample code for educational and demonstration purposes only. Findings should be reviewed and validated before acting on them. See the project's README and LICENSE for full terms.*
