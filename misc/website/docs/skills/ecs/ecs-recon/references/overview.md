---
title: "Module: Overview and Inventory"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/overview.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-recon/references/overview.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-recon/references/overview.md). Edit the source, not this page.
:::

# Module: Overview and Inventory

> **Part of:** [ecs-recon](../)
> **Purpose:** Account/region-wide ECS inventory — discover all clusters, services, and task counts in a single pass

## Prerequisites

- **Region required:** Yes (resolve before scanning — see Region Resolution below)
- **AWS credentials:** Caller must have IAM permissions for the APIs listed below
- **APIs used:**
  - `ecs:ListClusters` — enumerate all cluster ARNs in the region
  - `ecs:ListServices` — enumerate all service ARNs within a cluster
  - `ecs:DescribeClusters` — retrieve cluster status, task counts, and capacity providers

---

## Detection Strategy

Run these steps in order. Each step feeds into the next.

| Step | Action | Why this order |
|------|--------|----------------|
| 1 | List all clusters (paginated) | Establishes the full inventory boundary |
| 2 | List services per cluster (paginated) | Associates services to their parent cluster |
| 3 | Describe clusters with STATISTICS | Retrieves running/stopped task counts and capacity providers in bulk |

**Why this order matters:**

1. `ListClusters` is the cheapest call and gives us the full scope. If it fails (access-denied), we abort early rather than making expensive per-cluster calls.
2. `ListServices` must run per-cluster because there is no account-wide list-services API.
3. `DescribeClusters` with `--include STATISTICS` returns task counts in a single batch call (up to 100 clusters), avoiding per-service DescribeServices calls for the overview.

---

## Region Resolution

When the user does not specify a region, resolve it using these methods in order:

1. **User-provided:** If the user explicitly states a region, use it directly.
2. **Environment variable:** Check `AWS_DEFAULT_REGION` or `AWS_REGION`.
3. **AWS config file:** Run `aws configure get region`.
4. **Ask the user:** If none of the above resolves, prompt the user before proceeding.

If region cannot be resolved, abort the overview scan with error type `region_unresolved`.

---

## Detection Commands

### Step 1: List All Clusters

```bash
aws ecs list-clusters --region us-east-1
```

**Example output:**

```json
{
    "clusterArns": [
        "arn:aws:ecs:us-east-1:123456789012:cluster/prod-api",
        "arn:aws:ecs:us-east-1:123456789012:cluster/staging-web",
        "arn:aws:ecs:us-east-1:123456789012:cluster/batch-processing"
    ]
}
```

**Pagination handling:** AWS CLI v2 auto-paginates by default — the command above returns all cluster ARNs across all pages in a single invocation, with no token handling needed. Only if you pass `--max-items` does the CLI truncate and emit a `NextToken` field (capital N); resume with `--starting-token <NextToken>` until `NextToken` is absent. Prefer the default (no `--max-items`) so no results are silently truncated.

**Interpretation:**
- Extract cluster names from the ARNs (the segment after `cluster/`).
- An empty `clusterArns` list means no ECS clusters exist in this account/region — report that fact and stop.

---

### Step 2: List Services Per Cluster

```bash
aws ecs list-services --cluster prod-api --region us-east-1
```

**Example output:**

```json
{
    "serviceArns": [
        "arn:aws:ecs:us-east-1:123456789012:service/prod-api/user-service",
        "arn:aws:ecs:us-east-1:123456789012:service/prod-api/order-service",
        "arn:aws:ecs:us-east-1:123456789012:service/prod-api/notification-service"
    ]
}
```

**Pagination handling:** AWS CLI v2 auto-paginates by default — services can number in the hundreds per cluster, and the command above collects all pages in a single invocation. Do not pass `--max-items`; if it is used, the CLI truncates and emits a `NextToken` field (capital N) that must be fed back via `--starting-token <NextToken>` until absent, or the service list is silently incomplete.

**Interpretation:**
- Extract service names from ARNs (the last segment after the final `/`).
- An empty `serviceArns` list means the cluster has no services — include the cluster in the report with an empty services list.
- Repeat this step for **every** cluster discovered in Step 1.

---

### Step 3: Describe Clusters (with Statistics)

```bash
aws ecs describe-clusters --clusters prod-api staging-web batch-processing --include STATISTICS --region us-east-1
```

**Example output:**

```json
{
    "clusters": [
        {
            "clusterName": "prod-api",
            "clusterArn": "arn:aws:ecs:us-east-1:123456789012:cluster/prod-api",
            "status": "ACTIVE",
            "runningTasksCount": 12,
            "pendingTasksCount": 0,
            "activeServicesCount": 3,
            "registeredContainerInstancesCount": 0,
            "capacityProviders": [
                "FARGATE",
                "FARGATE_SPOT"
            ],
            "statistics": [
                {
                    "name": "runningEC2TasksCount",
                    "value": "0"
                },
                {
                    "name": "runningFargateTasksCount",
                    "value": "12"
                },
                {
                    "name": "pendingFargateTasksCount",
                    "value": "0"
                },
                {
                    "name": "activeFargateServiceCount",
                    "value": "3"
                }
            ]
        },
        {
            "clusterName": "staging-web",
            "clusterArn": "arn:aws:ecs:us-east-1:123456789012:cluster/staging-web",
            "status": "ACTIVE",
            "runningTasksCount": 4,
            "pendingTasksCount": 1,
            "activeServicesCount": 2,
            "registeredContainerInstancesCount": 3,
            "capacityProviders": [
                "my-ec2-asg-provider"
            ],
            "statistics": [
                {
                    "name": "runningEC2TasksCount",
                    "value": "4"
                },
                {
                    "name": "runningFargateTasksCount",
                    "value": "0"
                }
            ]
        },
        {
            "clusterName": "batch-processing",
            "clusterArn": "arn:aws:ecs:us-east-1:123456789012:cluster/batch-processing",
            "status": "ACTIVE",
            "runningTasksCount": 0,
            "pendingTasksCount": 0,
            "activeServicesCount": 0,
            "registeredContainerInstancesCount": 0,
            "capacityProviders": [],
            "statistics": []
        }
    ],
    "failures": []
}
```

**Batch limits:** `DescribeClusters` accepts up to 100 cluster names per call. If you have more than 100 clusters, batch them into groups of 100.

**Interpretation:**
- `runningTasksCount` — tasks currently in RUNNING state.
- The `statistics` list contains per-launch-type counts. Documented statistic names include `runningEC2TasksCount`, `runningFargateTasksCount`, `pendingEC2TasksCount`, `pendingFargateTasksCount`, `activeEC2ServiceCount`, `activeFargateServiceCount`, `drainingEC2ServiceCount`, and `drainingFargateServiceCount`.
- The API does not return a "stopped" task count in this response. For the overview, report `runningTasksCount` as `running_tasks` and report `stopped_tasks: null` (not collected). An accurate stopped count requires a separate `ListTasks` call with `--desired-status STOPPED` per cluster.
- `capacityProviders` — the capacity provider names associated with the cluster.
- `activeServicesCount` — use this as `services_count` (cross-reference with Step 2 results for accuracy).
- Check the `failures` array — any cluster that failed to describe will appear here with a reason.

---

## Output Schema

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Service.html (launchType enum: EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES) and https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Cluster.html (cluster status values, statistics names)

```yaml
overview:
  clusters:
    - name: string            # Cluster name (extracted from ARN)
      arn: string             # Full cluster ARN
      status: string          # ACTIVE | PROVISIONING | DEPROVISIONING | FAILED | INACTIVE
      services_count: int     # Number of services in cluster
      running_tasks: int      # Tasks in RUNNING state
      stopped_tasks: int | null  # Tasks in STOPPED state (null = not collected at overview level)
      capacity_providers: list[string]  # Associated capacity provider names (may be empty)
      error: string | null    # Failing API call + error code if this cluster could not be fully scanned; null otherwise
      services:
        - name: string        # Service name (extracted from ARN)
          status: string      # ACTIVE | DRAINING | INACTIVE
          desired_count: int  # Target task count for the service
          running_count: int  # Currently running task count
          launch_type: string | "not_applicable" | null  # FARGATE | EC2 | EXTERNAL | MANAGED_INSTANCES | not_applicable (capacity provider strategy in use) | null (not collected)
          error: string | null  # Failing API call + error code for this service; null otherwise
```

**Notes:**
- `services` list is populated from Step 2. The `status`, `desired_count`, `running_count`, and `launch_type` fields require an additional `DescribeServices` call per cluster during the overview. If skipped for performance, mark these fields as `null` (not collected) and note that full service details are available in the drill-down phase.
- `launch_type` semantics match compute.md: `not_applicable` means the service uses a `capacityProviderStrategy` (no explicit launch type); `null` is reserved strictly for "not collected". Never use `null` to mean "capacity provider strategy in use".
- `stopped_tasks` is `null` at the overview level when only `DescribeClusters` is used (it does not return a stopped count). Accurate stopped task counts require `ListTasks --desired-status STOPPED` per cluster; report the integer only when that call was made.

---

## Edge Cases

### Empty Clusters

When a cluster has zero services and zero running tasks:
- Include the cluster in the output with `services_count: 0`, `running_tasks: 0`, `stopped_tasks: null` (not collected at overview level), and an empty `services` list.
- Do not skip or hide empty clusters — they are part of the inventory.

### Paginated Results

Both `ListClusters` and `ListServices` return paginated results, but AWS CLI v2 handles this automatically:
- Run the commands **without** `--max-items` — the CLI auto-paginates and returns the complete result set in one invocation.
- If `--max-items` is used anyway, the CLI truncates the output and emits a `NextToken` field (capital N). You must then resume with `--starting-token <NextToken>` until `NextToken` is absent, or results are silently truncated. There is no lowercase `nextToken` in truncated CLI v2 output.
- Collect **all** results before proceeding to the next step.

### Access-Denied Handling

If an API call returns `AccessDeniedException`:

| Failed Call | Action |
|-------------|--------|
| `ListClusters` | Total failure — the root call produced no data. Report the module as `unavailable: true` with reason. This is the ONLY case that marks the whole module unavailable. |
| `ListServices` for a specific cluster | Record the cluster entry with `error` set (failing API + error code), leave its `services` list empty, retain data for other clusters, continue. |
| `DescribeClusters` | Record affected clusters with `error` set, retain service data from Step 2, continue. |

In all cases, include the specific error message and the IAM action that was denied in the `error` field.

### Partial Failure Retention

When a failure occurs mid-scan:
- **Retain all data collected before the failure.** Never discard already-collected inventory.
- Record which step failed and for which resource, on that resource's `error` field.
- Present the partial data alongside the error so the user sees what was discovered.
- Reserve module-level `unavailable: true` for total failure only (the root `ListClusters` call failed and no data exists).
- Example: If 5 out of 8 clusters were successfully scanned before a throttle on the 6th, report the 5 complete clusters (`error: null`) and record clusters 6–8 with `error: "API throttled on DescribeClusters"`.

### DescribeClusters Failures Array

The `DescribeClusters` response includes a `failures` array for clusters that could not be described:

```json
{
  "clusters": [...],
  "failures": [
    {
      "arn": "arn:aws:ecs:us-east-1:123456789012:cluster/deleted-cluster",
      "reason": "MISSING"
    }
  ]
}
```

- `MISSING` — cluster does not exist (may have been deleted between ListClusters and DescribeClusters).
- Handle by recording the cluster with `status: "NOT_FOUND"` and continuing.

### Throttling

If a call is throttled (`ThrottlingException`):
- Do **not** retry (the skill is read-only and does not implement retry logic).
- Record the affected resource(s) with `error: "API throttled on <call>"`.
- Continue with remaining detections.

### Large Accounts (100+ Clusters)

For accounts with more than 100 clusters:
- `DescribeClusters` accepts a maximum of 100 clusters per call. Batch cluster names into groups of 100.
- `ListServices` must be called per-cluster regardless of account size.
- Consider advising the user to scope the scan to a subset of clusters for large accounts.

---

## Sources

- AWS CLI pagination behavior (auto-pagination by default; `--max-items` truncation emits `NextToken`, resume with `--starting-token`): https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-pagination.html
- Cluster API shape, status values, and documented `statistics` names (e.g., runningEC2TasksCount, runningFargateTasksCount, pendingEC2TasksCount, activeEC2ServiceCount, drainingEC2ServiceCount, activeFargateServiceCount): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Cluster.html
- Service API shape and `launchType` enum (EC2 | FARGATE | EXTERNAL | MANAGED_INSTANCES): https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Service.html
- DescribeClusters request limits and `failures` array: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeClusters.html
- ListServices API: https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ListServices.html
