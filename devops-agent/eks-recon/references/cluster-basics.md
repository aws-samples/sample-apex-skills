# Module: Cluster Basics

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect core cluster information - name, version, region, endpoint, platform version

## Table of Contents

- [Access Model](#access-model)
- [Detection Commands](#detection-commands)
- [Shared Cluster Block](#shared-cluster-block)
- [Cluster Detail (full recon)](#cluster-detail-full-recon)
- [Region Detection](#region-detection)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Access Model

This reference is **always loaded first** — it owns the shared `cluster:` block that every
other reference emits verbatim, so recon reads it before any module-specific reference.

It reads facts from two sources, both read-only:

- **AWS control-plane APIs** (EKS) — cluster identity, version, platform version, endpoint,
  status, tags, and the full-recon lifecycle facts (support type, zonal shift, CA presence,
  health, encryption config). Requires the read-only permissions in `references/iam-policy.json`.
- **Kubernetes API** (via the Agent Space EKS access entry) — not used by this reference.
  Every cluster-basics fact comes from a single `aws eks describe-cluster` call.

If a fact cannot be read (e.g. an AWS API failure), record it as `unconfirmed` in the report's
Coverage section rather than emitting a misleading `false`/`0`. If the Kubernetes API is
unreachable it does not affect this reference — cluster-basics is pure AWS-API.

> **Reference pseudocode note.** This reference has no Kubernetes-API reads, so it carries no
> reference pseudocode. Do not emit `kubectl ... | jq` pipelines anywhere in recon.

---

## Detection Commands

**Via AWS API** — call EKS DescribeCluster and read the core identity fields. This single
call populates both the shared `cluster:` block and the `cluster_detail` full-recon facts
below — no extra API calls are required.

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

**Extract from response:**
- `cluster.name` -> Cluster name
- `cluster.version` -> Kubernetes version (check for upgrade eligibility)
- `cluster.platformVersion` -> EKS platform version (indicates patch level)
- `cluster.endpoint` -> API server endpoint (the cluster API server endpoint URL)
- `cluster.arn` -> Cluster ARN (extract region from this)
- `cluster.status` -> Cluster status (verify ACTIVE before proceeding)
- `cluster.createdAt` -> Creation timestamp (useful for audit reports)

---

## Shared Cluster Block

This is the **canonical** `cluster:` block. Every module's report output includes it verbatim;
it is defined here once and never redefined per-module. Load this reference first so the shared
block is available to all other modules.

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

**Via AWS API:**
```bash
aws eks describe-cluster --name <cluster-name> --region <region> \
  --query 'cluster.{name:name,version:version,platformVersion:platformVersion,endpoint:endpoint,arn:arn,status:status,createdAt:createdAt,tags:tags}'
```

**Notes:**
- `tags` comes from `cluster.tags` (a map of key/value; emit `null` when the cluster has no tags).
- `region` is derived from the `--region` argument or parsed from `cluster.arn` (`arn:aws:eks:<region>:...`).

---

## Cluster Detail (full recon)

Additional control-plane identity/lifecycle facts owned by this reference. All come from the
same `aws eks describe-cluster` response — no extra API calls required. Report as facts only.

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

**Via AWS API:**
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

When the region is not specified, detect it using these methods in order:

1. **Extract from cluster ARN** (if already known): Parse `arn:aws:eks:<region>:<account>:cluster/<name>`
2. **From the discovered cluster listing**: the cluster was enumerated in a known region during Step 1 discovery
3. **Prompt is not available** (autonomous execution): fall back to the discovery region

---

## Output Schema

```yaml
cluster:
  name: string           # Cluster name - use for all subsequent API calls
  region: string         # AWS region - required for CLI commands
  version: string        # Kubernetes version (e.g., "1.31") - check EKS docs for EOL dates
  platform_version: string  # EKS platform version (e.g., "eks.5") - higher = more patches
  endpoint: string       # the cluster API server endpoint URL
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

1. The Agent Space reaches the Kubernetes API through the EKS access entry, which has VPC access where provisioned
2. The endpoint-access facts are captured by the **networking** reference as `networking.endpoint_access: {public, private, public_cidrs}` (see `references/networking.md` "## Output Schema") — recon reports them there, not as a separate cluster-basics scalar.
