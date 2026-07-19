# Module: Cluster Insights

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect EKS Cluster Insights - AWS-generated upgrade-readiness and configuration findings for the cluster

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. List Insights](#1-list-insights)
  - [2. Describe Each Insight](#2-describe-each-insight)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

This reference reads facts from a single source, read-only:

- **AWS control-plane APIs** (EKS) — Cluster Insights are an AWS-managed feature surfaced
  entirely through the EKS API (`list-insights` / `describe-insight`). Requires the read-only
  permissions in `references/iam-policy.json`.

There is **no Kubernetes API read** in this reference — Cluster Insights is pure AWS-API. If
an insights call cannot be completed (e.g. an AWS API failure or a region/platform version
that does not support the feature), record the result as a fact per the Edge Cases below
(`count: 0` on an empty/unsupported result) or as `unconfirmed` in the report's Coverage
section on an outright API failure — never as a fabricated finding.

> **Reference pseudocode note.** This reference has no Kubernetes-API reads, so it carries no
> reference pseudocode. Do not emit `kubectl ... | jq` pipelines anywhere in recon.

---

## Detection Strategy

EKS Cluster Insights is an AWS-managed feature that surfaces findings against the cluster.
These are facts returned by the API — report them verbatim. This reference adds NO verdict,
score, or advice.

```
1. list-insights      -> Enumerate insight IDs + summary status
2. describe-insight   -> Pull per-insight detail (per id)
```

---

## Detection Capabilities

### 1. List Insights

Enumerate the insights AWS has generated for the cluster.

**Via AWS API:**
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

**Via AWS API:**
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
  - The `--categories` filter accepts all three values (`UPGRADE_READINESS`, `MISCONFIGURATION`, `ROLLBACK_READINESS`). `ROLLBACK_READINESS` may appear in returned results (surfaced during the post-upgrade rollback window).
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
