---
title: "Module: Cluster Insights"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/cluster-insights.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/cluster-insights.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/cluster-insights.md). Edit the source, not this page.
:::

# Module: Cluster Insights

> **Part of:** [eks-recon](../)
> **Purpose:** Detect EKS Cluster Insights - AWS-generated upgrade-readiness and configuration findings for the cluster

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [1. List Insights](#1-list-insights)
  - [2. Describe Each Insight](#2-describe-each-insight)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Yes
- **MCP tools used:** `get_eks_insights` (if available)
- **CLI fallback:** `aws eks list-insights`, `aws eks describe-insight`

---

## Detection Strategy

EKS Cluster Insights is an AWS-managed feature that surfaces findings against the cluster. These are facts returned by the API — report them verbatim. This module adds NO verdict, score, or advice.

```
1. list-insights      -> Enumerate insight IDs + summary status
2. describe-insight   -> Pull per-insight detail (per id)
```

---

## Detection Commands

### 1. List Insights

Enumerate the insights AWS has generated for the cluster.

**MCP:**
```
get_eks_insights(
  cluster_name="<cluster-name>"
)
```

**CLI:**
```bash
aws eks list-insights --cluster-name <cluster-name> --region <region> \
  --query 'insights[].{id:id,name:name,category:category,status:insightStatus.status,version:kubernetesVersion,lastRefresh:lastRefreshTime}'
```

**Example output:**
```json
[
  {
    "id": "a1b2c3d4-0000-1111-2222-333344445555",
    "name": "Deprecated APIs removed in Kubernetes v1.32",
    "category": "UPGRADE_READINESS",
    "status": "PASSING",
    "version": "1.32",
    "lastRefresh": "2026-07-17T09:12:00.000000+00:00"
  }
]
```

### 2. Describe Each Insight

For each insight id from step 1, pull the detail (adds the `description` field).

**CLI:**
```bash
aws eks describe-insight --cluster-name <cluster-name> --id <insight-id> --region <region> \
  --query 'insight.{id:id,name:name,category:category,status:insightStatus.status,version:kubernetesVersion,lastRefresh:lastRefreshTime,description:description}'
```

**Example output:**
```json
{
  "id": "a1b2c3d4-0000-1111-2222-333344445555",
  "name": "Deprecated APIs removed in Kubernetes v1.32",
  "category": "UPGRADE_READINESS",
  "status": "PASSING",
  "version": "1.32",
  "lastRefresh": "2026-07-17T09:12:00.000000+00:00",
  "description": "Checks for usage of APIs removed in the target Kubernetes version."
}
```

**Field values (report verbatim, do not interpret):**
- `category`: `UPGRADE_READINESS` | `MISCONFIGURATION` | `ROLLBACK_READINESS`
  - `ROLLBACK_READINESS` may appear in returned results (surfaced during the post-upgrade rollback window), even though the `--categories` filter accepts only `UPGRADE_READINESS` / `MISCONFIGURATION`.
- `status`: `PASSING` | `WARNING` | `ERROR` | `UNKNOWN` (`UNKNOWN` = Amazon EKS is unable to determine if your cluster is impacted)

---

## Output Schema

```yaml
cluster_insights:
  count: int
  list:
    - id: string
      name: string
      category: string          # UPGRADE_READINESS | MISCONFIGURATION | ROLLBACK_READINESS
      status: string            # PASSING | WARNING | ERROR | UNKNOWN
      kubernetes_version: string  # target/checked version reported by the insight
      last_refresh_time: string   # ISO timestamp
      description: string
```

---

## Edge Cases

### No Insights / Unsupported

When `list-insights` returns an empty `insights` array, or the API/region does not support Cluster Insights (e.g., `ResourceNotFoundException` or an empty result on older platform versions):
- Emit `cluster_insights: {count: 0, list: []}`.
- This is a fact (no insights reported), not an error.

### Describe Failure for a Single ID

If `describe-insight` fails for one id but `list-insights` returned it, include the id/name/category/status from the list output and set `description: null`. Do not drop the entry.

### Facts Only

The API itself returns findings (PASSING/WARNING/ERROR/UNKNOWN). Report them exactly. Do NOT add readiness scoring, "you should upgrade/fix", or any verdict — that is a downstream skill's job, not recon's.
