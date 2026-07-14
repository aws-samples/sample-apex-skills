# Module: Overview and Inventory

> **Part of:** [ecs-recon](../SKILL.md)
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

#### MCP (Future)

When an ECS MCP server becomes available, use it for structured, pre-authenticated access:

```
ecs_list_clusters(
  region="us-east-1"
)
```

**Expected response:**

```json
{
  "clusterArns": [
    "arn:aws:ecs:us-east-1:123456789012:cluster/prod-api",
    "arn:aws:ecs:us-east-1:123456789012:cluster/staging-web",
    "arn:aws:ecs:us-east-1:123456789012:cluster/batch-processing"
  ],
  "nextToken": null
}
```

#### CLI Fallback

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

**Pagination handling:** If `nextToken` is present in the response, repeat the call with `--starting-token <nextToken>` until `nextToken` is `null` or absent. Collect all cluster ARNs across all pages before proceeding.

```bash
aws ecs list-clusters --region us-east-1 --starting-token <nextToken>
```

**Interpretation:**
- Extract cluster names from the ARNs (the segment after `cluster/`).
- An empty `clusterArns` list means no ECS clusters exist in this account/region — report that fact and stop.

---

### Step 2: List Services Per Cluster

#### MCP (Future)

```
ecs_list_services(
  cluster="prod-api",
  region="us-east-1"
)
```

**Expected response:**

```json
{
  "serviceArns": [
    "arn:aws:ecs:us-east-1:123456789012:service/prod-api/user-service",
    "arn:aws:ecs:us-east-1:123456789012:service/prod-api/order-service",
    "arn:aws:ecs:us-east-1:123456789012:service/prod-api/notification-service"
  ],
  "nextToken": null
}
```

#### CLI Fallback

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

**Pagination handling:** If `nextToken` is present, repeat with `--starting-token <nextToken>`. Services can number in the hundreds per cluster — always paginate.

```bash
aws ecs list-services --cluster prod-api --region us-east-1 --starting-token <nextToken>
```

**Interpretation:**
- Extract service names from ARNs (the last segment after the final `/`).
- An empty `serviceArns` list means the cluster has no services — include the cluster in the report with an empty services list.
- Repeat this step for **every** cluster discovered in Step 1.

---

### Step 3: Describe Clusters (with Statistics)

#### MCP (Future)

```
ecs_describe_clusters(
  clusters=["prod-api", "staging-web", "batch-processing"],
  include=["STATISTICS"],
  region="us-east-1"
)
```

**Expected response:**

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
      "capacityProviders": ["FARGATE", "FARGATE_SPOT"],
      "statistics": [
        {"name": "runningEC2TasksCount", "value": "0"},
        {"name": "runningFargateTasksCount", "value": "12"},
        {"name": "drainedEC2TasksCount", "value": "0"},
        {"name": "activeFargateTasksCount", "value": "12"}
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
      "capacityProviders": ["my-ec2-asg-provider"],
      "statistics": [
        {"name": "runningEC2TasksCount", "value": "4"},
        {"name": "runningFargateTasksCount", "value": "0"}
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

#### CLI Fallback

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
- To calculate stopped tasks, note that the API does not directly return a "stopped" count in this response. For the overview, report `runningTasksCount` as `running_tasks`. The stopped count can be derived from the STATISTICS fields or from a separate `ListTasks` call with `--desired-status STOPPED` if needed. For the overview map, report 0 for stopped tasks when the STATISTICS data does not include a direct stopped count.
- `capacityProviders` — the capacity provider names associated with the cluster.
- `activeServicesCount` — use this as `services_count` (cross-reference with Step 2 results for accuracy).
- Check the `failures` array — any cluster that failed to describe will appear here with a reason.

---

## Output Schema

```yaml
overview:
  clusters:
    - name: string            # Cluster name (extracted from ARN)
      arn: string             # Full cluster ARN
      status: string          # ACTIVE | PROVISIONING | DEPROVISIONING | FAILED | INACTIVE
      services_count: int     # Number of services in cluster
      running_tasks: int      # Tasks in RUNNING state
      stopped_tasks: int      # Tasks in STOPPED state (0 if not retrievable from overview)
      capacity_providers: list[string]  # Associated capacity provider names (may be empty)
      services:
        - name: string        # Service name (extracted from ARN)
          status: string      # ACTIVE | DRAINING | INACTIVE
          desired_count: int  # Target task count for the service
          running_count: int  # Currently running task count
          launch_type: string | null  # FARGATE | EC2 | EXTERNAL | MANAGED_INSTANCES | null (if capacity provider strategy)
```

**Notes:**
- `services` list is populated from Step 2. The `status`, `desired_count`, `running_count`, and `launch_type` fields require an additional `DescribeServices` call per cluster during the overview. If skipped for performance, mark these fields as `null` and note that full service details are available in the drill-down phase.
- `stopped_tasks` may be reported as 0 at the overview level when only `DescribeClusters` is used (it does not return stopped count directly). Accurate stopped task counts require `ListTasks --desired-status STOPPED` per cluster.

---

## Edge Cases

### Empty Clusters

When a cluster has zero services and zero running tasks:
- Include the cluster in the output with `services_count: 0`, `running_tasks: 0`, `stopped_tasks: 0`, and an empty `services` list.
- Do not skip or hide empty clusters — they are part of the inventory.

### Paginated Results

Both `ListClusters` and `ListServices` return paginated results:
- Always check for `nextToken` in the response.
- Continue calling with `--starting-token` until `nextToken` is absent or `null`.
- Collect **all** results before proceeding to the next step.
- For `ListClusters`, default page size is 100 (maximum). For `ListServices`, default is 10 (maximum 100 with `--max-items`).

Use `--max-items 100` with `ListServices` to minimize pagination rounds:

```bash
aws ecs list-services --cluster prod-api --region us-east-1 --max-items 100
```

### Access-Denied Handling

If an API call returns `AccessDeniedException`:

| Failed Call | Action |
|-------------|--------|
| `ListClusters` | Abort the entire overview scan — cannot proceed without cluster list. Report error with reason. |
| `ListServices` for a specific cluster | Record the cluster with `services: unavailable`, retain data for other clusters, continue. |
| `DescribeClusters` | Record affected clusters with `status: unavailable`, retain service data from Step 2, continue. |

In all cases, include the specific error message and the IAM action that was denied.

### Partial Failure Retention

When a failure occurs mid-scan:
- **Retain all data collected before the failure.** Never discard already-collected inventory.
- Record which step failed and for which resource.
- Present the partial data alongside the error so the user sees what was discovered.
- Example: If 5 out of 8 clusters were successfully scanned before a throttle on the 6th, report the 5 complete clusters and mark clusters 6–8 as unavailable with reason `"API throttled on DescribeClusters"`.

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
- Record the affected step as unavailable with reason `"API throttled"`.
- Continue with remaining detections.

### Large Accounts (100+ Clusters)

For accounts with more than 100 clusters:
- `DescribeClusters` accepts a maximum of 100 clusters per call. Batch cluster names into groups of 100.
- `ListServices` must be called per-cluster regardless of account size.
- Consider advising the user to scope the scan to a subset of clusters for large accounts.
