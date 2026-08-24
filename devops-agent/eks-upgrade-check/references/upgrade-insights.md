# AWS Upgrade Insights

## Purpose
Retrieve and interpret official AWS EKS Upgrade Insights — pre-upgrade checks that AWS runs against your cluster.

## How to Check

### Step 1: Get All Insights

1. Use the EKS ListInsights API with the cluster name
2. Filter for category `UPGRADE_READINESS`
3. Record each insight: ID, status, name, description

### Step 2: Get Details for Non-Passing Insights

For any insight with status other than `PASSING`:
1. Use the EKS DescribeInsight API with the specific insight ID
2. Record: detailed description, recommendation, affected resources

### CLI fallback (when the EKS APIs are not reachable through your tooling)

If those APIs are not reachable through your tooling, call them via the AWS CLI:

```bash
# Step 1 equivalent — list all upgrade-readiness insights
aws eks list-insights --cluster-name <cluster> --region <region> \
  --filter categories=UPGRADE_READINESS

# Step 2 equivalent — detail one non-PASSING insight
aws eks describe-insight --cluster-name <cluster> --region <region> --id <insight-id>
```

Requires `eks:ListInsights` and `eks:DescribeInsight`. If Insights cannot be reached by either
path, report Category 7 as UNKNOWN / not-scored — do NOT score it 0 (a denied read is not a
clean pass).

### Step 3: Classify Findings

| Insight Status | Severity |
|---------------|----------|
| PASSING | NONE |
| WARNING | MEDIUM |
| ERROR | HIGH |
| UNKNOWN | LOW |

### Step 4: Cross-Reference with Other Sections

AWS Upgrade Insights often overlap with findings from other sections (deprecated APIs, add-on compatibility). When reporting:
- Note if an insight confirms a finding from another section
- Do NOT double-count in the score. Match each insight to a category finding by **subject key**:
  the deprecated API group/version/resource (e.g. `flowcontrol.apiserver.k8s.io/v1beta3`) for
  Category 2, or the add-on name (e.g. `vpc-cni`) for Category 4. When an insight's subject key
  matches a finding **already scored in that category**, **suppress the insight's points** (score
  it 0) and keep the insight only as confirmation evidence in the report — do NOT add its
  WARNING/ERROR points on top of the category that already owns the finding.
- Only insights that reveal issues NOT caught by any other check contribute points under
  Category 7. Highlight those.

## Important Context for Users

AWS Upgrade Insights checks multiple versions ahead, not just the immediate target. For example, if upgrading from 1.30 → 1.31, AWS may flag deprecated APIs that are removed in 1.33. This is valuable forward-looking information but should not be confused with immediate blockers.

**Explain this distinction clearly in the report:**
- "Blocked for target version" = must fix before upgrading
- "Flagged by AWS for future version" = plan to fix, but not a blocker for this upgrade

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 7.**
> Quick reference: ERROR = 5 pts, WARNING = 2 pts, PASSING = 0 pts, UNKNOWN = 0 pts
> (LOW severity, informational only). Max category = 10 pts. The status enum is
> PASSING/WARNING/ERROR/UNKNOWN — there is no "FAILING" status.
