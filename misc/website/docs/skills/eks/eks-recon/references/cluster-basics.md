---
title: "Module: Cluster Basics"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/cluster-basics.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/cluster-basics.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/cluster-basics.md). Edit the source, not this page.
:::

# Module: Cluster Basics

> **Part of:** [eks-recon](../)
> **Purpose:** Detect core cluster information - name, version, region, endpoint, platform version

## Prerequisites

- **Cluster name required:** Yes (auto-discover if not provided — see SKILL.md Step 1)
- **MCP tools used:** `describe_eks_resource`
- **CLI fallback:** `aws eks describe-cluster`

---

## Detection Commands

### MCP (Preferred)

Use MCP when available because it handles authentication automatically and returns structured data that requires no parsing.

```
describe_eks_resource(
  resource_type="cluster",
  cluster_name="my-production-cluster"
)
```

**Example response:**

```json
{
  "cluster": {
    "name": "my-production-cluster",
    "version": "1.31",
    "platformVersion": "eks.5",
    "endpoint": "https://ABC123DEF456.gr7.us-west-2.eks.amazonaws.com",
    "arn": "arn:aws:eks:us-west-2:123456789012:cluster/my-production-cluster",
    "status": "ACTIVE",
    "createdAt": "2024-06-15T10:30:00Z"
  }
}
```

**Extract from response:**
- `cluster.name` -> Cluster name
- `cluster.version` -> Kubernetes version (check for upgrade eligibility)
- `cluster.platformVersion` -> EKS platform version (indicates patch level)
- `cluster.endpoint` -> API server endpoint (needed for kubectl config)
- `cluster.arn` -> Cluster ARN (extract region from this)
- `cluster.status` -> Cluster status (verify ACTIVE before proceeding)
- `cluster.createdAt` -> Creation timestamp (useful for audit reports)

### CLI Fallback

Use CLI when MCP tools are unavailable or when running from a bastion host with AWS credentials configured.

```bash
aws eks describe-cluster \
  --name my-production-cluster \
  --region us-west-2 \
  --query 'cluster.{
    name:name,
    version:version,
    platformVersion:platformVersion,
    endpoint:endpoint,
    arn:arn,
    status:status,
    createdAt:createdAt
  }'
```

**Example output:**

```json
{
    "name": "my-production-cluster",
    "version": "1.31",
    "platformVersion": "eks.5",
    "endpoint": "https://ABC123DEF456.gr7.us-west-2.eks.amazonaws.com",
    "arn": "arn:aws:eks:us-west-2:123456789012:cluster/my-production-cluster",
    "status": "ACTIVE",
    "createdAt": "2024-06-15T10:30:00.000000+00:00"
}
```

---

## Shared Cluster Block

This is the **canonical** `cluster:` block. Every module agent emits it verbatim via the pointer in its Output Format (see BUILD-SPEC Decision 1); it is defined here once and never redefined per-module.

```yaml
cluster:
  name: <string>              # Cluster name
  region: <string>            # AWS region (from arn or --region)
  version: <string>           # Kubernetes version (e.g., "1.31")
  platform_version: <string>  # EKS platform version (e.g., "eks.5")
  endpoint: <string>          # API server endpoint URL
  arn: <string>               # Full cluster ARN
  status: <string>            # ACTIVE, CREATING, UPDATING, DELETING
  created_at: <string>        # ISO timestamp
  tags: <map or null>         # from cluster.tags (null if none)
```

**Detection command that populates this block:**

CLI:
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.{name:name,version:version,platformVersion:platformVersion,endpoint:endpoint,arn:arn,status:status,createdAt:createdAt,tags:tags}'
```

MCP:
```
describe_eks_resource(resource_type="cluster", cluster_name="<cluster-name>")
```

**Notes:**
- `tags` comes from `cluster.tags` (a map of key/value; emit `null` when the cluster has no tags).
- `region` is derived from the `--region` argument or parsed from `cluster.arn` (`arn:aws:eks:<region>:...`).

---

## Cluster Detail (full recon)

Additional control-plane identity/lifecycle facts owned by this module. All come from the same `aws eks describe-cluster` / `describe_eks_resource(resource_type="cluster")` response — no extra API calls required. Report as facts only.

| Fact | Detection (schema field) | Notes |
|------|--------------------------|-------|
| `upgrade_policy.support_type` | `cluster.upgradePolicy.supportType` | `STANDARD` or `EXTENDED` |
| `zonal_shift.enabled` | `cluster.zonalShiftConfig.enabled` | bool |
| `certificate_authority.present` | `cluster.certificateAuthority.data` present | emit `true`/`false` only — do NOT emit the CA data itself |
| `health.issues` | `cluster.health.issues` | raw list of issue objects, verbatim; `[]` when none |
| `encryption_config.detected` | `cluster.encryptionConfig` present | bool |
| `encryption_config.kms_key_arn` | `cluster.encryptionConfig[].provider.keyArn` | KMS key arn; `null` if not present |
| `encryption_config.resources` | `cluster.encryptionConfig[].resources` | scope list, e.g. `["secrets"]` |

**Detection command (fields not in the shared-block query):**
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.{support_type:upgradePolicy.supportType,zonal_shift:zonalShiftConfig.enabled,ca_present:certificateAuthority.data,health_issues:health.issues,encryption:encryptionConfig}'
```

**Output Schema (Cluster Detail):**
```yaml
cluster_detail:
  upgrade_policy:
    support_type: <string>       # STANDARD | EXTENDED
  zonal_shift:
    enabled: <bool>
  certificate_authority:
    present: <bool>              # presence only; never the CA data
  health:
    issues: <list>               # cluster.health.issues verbatim; [] when none
  encryption_config:
    detected: <bool>
    kms_key_arn: <string or null>
    resources: <list or null>    # e.g., ["secrets"]
```

**Not owned here (one-line pointers — do not duplicate):**
- Network identifiers (vpcId, subnetIds, cluster SG, endpoint access) → see `references/networking.md`.
- Auth mode + OIDC issuer/providers → see `references/security.md`.
- Control-plane logging → see `references/observability.md`.
- EKS Cluster Insights → see `references/cluster-insights.md`.

---

## Region Detection

When the user does not specify a region, detect it using these methods in order:

1. **Extract from cluster ARN** (if already known): Parse `arn:aws:eks:<region>:<account>:cluster/<name>`
2. **Check kubeconfig context**: Run `kubectl config current-context` and parse the region
3. **Query AWS config**: Run `aws configure get region`
4. **Prompt the user**: Ask explicitly as a last resort

---

## Output Schema

```yaml
cluster:
  name: string           # Cluster name - use for all subsequent API calls
  region: string         # AWS region - required for CLI commands
  version: string        # Kubernetes version (e.g., "1.31") - check EKS docs for EOL dates
  platform_version: string  # EKS platform version (e.g., "eks.5") - higher = more patches
  endpoint: string       # API server endpoint URL - needed for kubectl configuration
  arn: string           # Full cluster ARN - use for IAM policies and cross-account access
  status: string        # ACTIVE, CREATING, UPDATING, DELETING - proceed only if ACTIVE
  created_at: string    # ISO timestamp - useful for compliance and audit reports
  tags: map or null     # from cluster.tags (null if none)
```

> This block is the canonical **[## Shared Cluster Block](#shared-cluster-block)**. See that section for the detection command and the full-recon **[## Cluster Detail (full recon)](#cluster-detail-full-recon)** facts.

---

## Edge Cases

### Handle Cluster Not Found

When `describe-cluster` returns `ResourceNotFoundException`, troubleshoot in this order:

1. Verify the cluster name spelling matches exactly (case-sensitive)
2. Confirm the region is correct by listing clusters: `aws eks list-clusters --region <region>`
3. Check IAM permissions - the caller needs `eks:DescribeCluster` permission

### Handle Transitional States

When the cluster status is not `ACTIVE`, take these actions:

| Status | Action |
|--------|--------|
| `CREATING` | Wait for creation to complete before running recon |
| `UPDATING` | Proceed with caution - some data may be incomplete during upgrades |
| `DELETING` | Abort recon immediately - cluster is being terminated |

### Handle Private Clusters

When endpoint access is private-only:

1. Verify MCP tool connectivity first - the MCP server may have VPC access
2. For CLI access, connect through a VPN or bastion host within the VPC
3. The endpoint-access facts are captured by the **networking** module as `networking.endpoint_access: {public, private, public_cidrs}` (see `references/networking.md` "## Output Schema") — recon reports them there, not as a separate cluster-basics scalar.
