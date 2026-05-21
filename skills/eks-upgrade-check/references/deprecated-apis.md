# Deprecated API Detection

## Purpose
Scan live cluster resources for usage of deprecated or removed Kubernetes APIs that will break during or after the upgrade.

## How to Check

### Step 1: Get EKS Upgrade Insights

Use the EKS Insights API with category `UPGRADE_READINESS` — this is the most reliable source for deprecated API detection as AWS scans the audit logs.

1. Get EKS Insights → filter for UPGRADE_READINESS
2. For any non-PASSING insights → get detailed description
3. Record: insight status, affected resources, recommended action

### Step 2: Scan Live Resources

For each resource type below, list resources and check their `apiVersion` field against the deprecation table.

**Resource types to scan:**
- Deployments, DaemonSets, StatefulSets, ReplicaSets
- CronJobs, Jobs
- Ingresses
- NetworkPolicies
- PodDisruptionBudgets
- HorizontalPodAutoscalers
- CustomResourceDefinitions
- ValidatingWebhookConfigurations, MutatingWebhookConfigurations
- FlowSchemas, PriorityLevelConfigurations

### Step 3: Check for Removed APIs by Target Version

| Target | Removed API | Replacement |
|--------|------------|-------------|
| 1.22 | `networking.k8s.io/v1beta1` Ingress | `networking.k8s.io/v1` |
| 1.22 | `rbac.authorization.k8s.io/v1beta1` | `rbac.authorization.k8s.io/v1` |
| 1.25 | `policy/v1beta1` PodSecurityPolicy | Pod Security Standards |
| 1.25 | `policy/v1beta1` PodDisruptionBudget | `policy/v1` |
| 1.25 | `batch/v1beta1` CronJob | `batch/v1` |
| 1.25 | `discovery.k8s.io/v1beta1` EndpointSlice | `discovery.k8s.io/v1` |
| 1.26 | `autoscaling/v2beta1` HPA | `autoscaling/v2` |
| 1.26 | `flowcontrol.apiserver.k8s.io/v1beta1` | `flowcontrol.apiserver.k8s.io/v1beta3` |
| 1.29 | `flowcontrol.apiserver.k8s.io/v1beta2` | `flowcontrol.apiserver.k8s.io/v1` |
| 1.32 | `flowcontrol.apiserver.k8s.io/v1beta3` | `flowcontrol.apiserver.k8s.io/v1` |

### Step 4: Classify Findings

For each deprecated API found:
- **Removed in target version** → HIGH severity, action required
- **Deprecated but still available in target** → LOW severity, plan migration
- **Removed in future version** → INFO, awareness only

## Output Format

For each finding, report:
- API version and kind
- Resource name and namespace
- Whether it's removed in the target version or just deprecated
- Specific migration command (e.g., update apiVersion field)

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 2 (Deprecated APIs).**

| Finding | Deduction |
|---------|-----------|
| API removed in target version | 5 pts per API path (max 20) |
| API deprecated but available | 1 pt per API path (max 5) |
