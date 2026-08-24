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

Run **two scans in parallel** for each resource type. Both are required because
they catch different failure modes.

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

#### Step 2a: Object `apiVersion` scan

For each resource type, list resources and check the live `apiVersion` field
against the deprecation table in Step 3. This is a **detection** step only: it
surfaces candidate API paths from the live object `apiVersion`; it does not decide
whether a resource needs migrating. That decision is made in Step 3b by writer
identity — not by a served-vs-stored apiVersion comparison.

#### Step 2b: `managedFields` apiVersion scan

For each resource, inspect every entry in `metadata.managedFields[]` and check
its `apiVersion` against the deprecation table in Step 3. The API server may
auto-convert resources to the storage version, so Step 2a alone misses
manifests originally applied under a deprecated apiVersion. `managedFields`
preserves the apiVersion used by every writer (kubectl, controllers, Argo CD,
Flux, Helm), so this scan covers all configuration sources.

**How to scan:** List each resource kind across all namespaces via the Kubernetes
API and read `metadata.managedFields[]` from every returned object. Each entry
contains a `manager` (the writer) and an `apiVersion` (the version that writer
used). For each object, record `namespace/name` plus every `manager=apiVersion`
pair. The `manager` value identifies which writer used each apiVersion (e.g.,
`kubectl-client-side-apply`, `argocd-application-controller`, controller
names) — this points to where the source manifest needs to be updated.

**Anti-pattern — do not pre-filter with naïve substring matching.**

For example, excluding every object whose managedFields text contains
`flowcontrol.apiserver.k8s.io/v1` also excludes `v1beta3` entries, because `v1`
is a prefix of `v1beta3`. A single resource often has multiple
`manager=apiVersion` entries (e.g., a controller writing `v1` plus the user
writing `v1beta3`), and filter-then-decide logic drops the object entirely as
soon as any benign apiVersion matches. Walk every object and check each
`manager=apiVersion` pair individually against the deprecation table in Step 3.

**Anti-pattern — do not rely on client-rendered output that hides managedFields.**

The raw Kubernetes API response includes `metadata.managedFields`. Client tools
may strip it from rendered output (kubectl 1.21+ hides managedFields from
`-o yaml` / `-o json` by default — kubectl added `--show-managed-fields` in 1.21 and
omits managedFields unless that flag is set), producing false negatives. Always read
`managedFields` directly from the API object, not from rendered/summarized views.

### Step 3: Check for Removed APIs by Target Version

| Target | Removed API | Replacement |
|--------|------------|-------------|
| 1.22 | `networking.k8s.io/v1beta1` Ingress | `networking.k8s.io/v1` |
| 1.22 | `rbac.authorization.k8s.io/v1beta1` | `rbac.authorization.k8s.io/v1` |
| 1.25 | `policy/v1beta1` PodSecurityPolicy | Pod Security Standards |
| 1.25 | `policy/v1beta1` PodDisruptionBudget | `policy/v1` |
| 1.25 | `batch/v1beta1` CronJob | `batch/v1` |
| 1.25 | `discovery.k8s.io/v1beta1` EndpointSlice | `discovery.k8s.io/v1` |
| 1.25 | `autoscaling/v2beta1` HPA | `autoscaling/v2` |
| 1.26 | `autoscaling/v2beta2` HPA | `autoscaling/v2` |
| 1.26 | `flowcontrol.apiserver.k8s.io/v1beta1` | `flowcontrol.apiserver.k8s.io/v1beta2` |
| 1.27 | `storage.k8s.io/v1beta1` CSIStorageCapacity | `storage.k8s.io/v1` |
| 1.29 | `flowcontrol.apiserver.k8s.io/v1beta2` | `flowcontrol.apiserver.k8s.io/v1` |
| 1.32 | `flowcontrol.apiserver.k8s.io/v1beta3` | `flowcontrol.apiserver.k8s.io/v1` |

> **EndpointSlice (1.25) and CSIStorageCapacity (1.27)** are detected via the generic
> deprecated-API path — EKS Upgrade Insights (Step 1) plus the `managedFields` writer
> test (Step 2b / Step 3b) — not a dedicated per-kind resource read. A `list` on the
> `v1` API of either kind tells you nothing about `v1beta1` writers, so no separate
> `discovery.k8s.io` / `storage.k8s.io` scan or RBAC grant is required for them.

### Target >= 1.33: Live Lookup Required for Removed APIs

The removal table above is current through Kubernetes 1.32 (as of 2026-08-05). It does
NOT cover API removals in 1.33 or later. If the target version is >= 1.33 — and in
particular for **Target >= 1.34**, which this table does not cover at all — you MUST
perform a live lookup before reporting "no removed APIs found."

**How to check:**
1. Use your documentation-search capability to look up "EKS Kubernetes <target> removed APIs".
2. Use your documentation-search capability to look up "Kubernetes <target> deprecated API migration guide".
3. Retrieve the relevant AWS/Kubernetes documentation pages — the Kubernetes "Deprecated API
   Migration Guide" and the CHANGELOG for the target minor version (e.g., `CHANGELOG-1.34.md`).
4. Cross-check the EKS Upgrade Insights from Step 1 — AWS scans audit logs and flags
   removed-API usage per target version.

**If no removed APIs are found after live lookup:** Report "No removed APIs identified for
<target> based on available documentation (as of the check date)" and advise re-checking
closer to the upgrade date, as documentation may be updated.

**If live sources are unreachable:** Report "Removed APIs for <target> could not be
verified — documentation unavailable" with MEDIUM severity. Do NOT assume none exist.

### Step 3b: Filter Out Already-Migrated / System-Written Resources (deterministic rule)

A `v1beta3` (or other removed-version) string appearing in `metadata.managedFields[]`
does NOT by itself mean a resource needs migrating. The deciding question is **who
wrote the removed version** — a resource is a real finding only if a
**user-controlled writer** actually wrote it.

> **Why not compare served vs stored apiVersion?** Reading an object's top-level
> `apiVersion` field back from the API cannot distinguish a migrated object from an
> unmigrated one: the API server serves every object at the version you request, so
> the read-back value reflects the request, not the source manifest. On 1.30+
> control planes a `v1` read-back can hide a manifest still applied as `v1beta3`.
> Do NOT use served/stored apiVersion as a per-object signal.

Apply this deterministic test to **every removed-API kind** surfaced via
`managedFields` in Step 2b (FlowSchema / PriorityLevelConfiguration and all other
kinds alike — Ingress, PodDisruptionBudget, CronJob, HPA, EndpointSlice, etc.).
The writer-identity filter is general: any kind can carry a stale removed-version
entry written by an internal/system manager, so the same false-positive risk
applies beyond APF. Objects surfaced only by Step 2a's live-object `apiVersion`
that have no `managedFields` writer signal are validated separately (see the
managedFields-absence caveat below):

**Writer identity (the only per-object signal).** For any
removed-version entry in `managedFields`, check the `manager` (writer):

- If the writer is a **Kubernetes/EKS-internal APF controller** — its name starts with
  `api-priority-and-fairness-config-` (e.g.
  `api-priority-and-fairness-config-consumer-v1`,
  `-producer-v1`) — or is the EKS-managed writer `eks`, or the internal control-plane
  writer `eks-internal` → **EXCLUDE.** These are the API server's own bootstrap
  controllers and EKS-managed/control-plane fields; the user cannot and need not
  change them. AWS documents the `eks` writer string: both server-side-apply and
  client-side managed fields on EKS "are tagged with `manager: eks`"
  (kubernetes-field-management.html, "Field Management"). Internal control-plane writers
  such as `eks-internal` are likewise not user tools and do not count as a user-managed
  writer.
- If the writer is a **user tool** — `kubectl-*`, `helm`, `argocd-application-controller`,
  `flux`, or any other non-APF manager → **COUNT it.** This points to a real source
  manifest that must be updated.

**Outcome:** A resource counts as a deprecated-API finding only if a user tool wrote a
removed version in `managedFields`. If the only removed-version trace comes from
internal APF controllers → it is a false positive; exclude it and record it under
Informational Findings as "system-written — no action required."

**Caveat — spoofability:** `managedFields.manager` is client-supplied and can be
spoofed or renamed; treat writer identity as strong evidence, not proof. When a
finding is surprising, confirm against the actual source manifests (GitOps repo,
Helm values) before acting on it.

**Caveat — managedFields absence:** this caveat covers spoofed or renamed managers; it
does NOT cover managedFields *absence*. Objects whose managedFields were stripped or
never recorded (e.g., after a Velero/OADP restore or a managedFields-clearing webhook)
carry no writer signal — exclude them from the Step 3b writer test and validate them
separately against source manifests. Treating absent managedFields as "no user-tool
writer" is a false-negative blind spot. If that separate check of the source manifests
(GitOps repo, Helm values) confirms a user tool authored the removed version, treat the
object as having a user-tool writer for counting purposes (count the path); if the
manifests show no such authorship, leave it excluded.

An API path (e.g., `flowschemas`) is counted only if **at least one object on that path
has a user-tool writer of a removed version**. If every object on the path is excluded,
the path contributes 0 points — do NOT deduct for it, and do NOT describe it as a blocker.

### Step 4: Classify Findings

For each deprecated API found, record the **source** (`object` from Step 2a /
`managedFields` from Step 2b) and severity:

- **Removed in target version** → HIGH severity, action required
- **Deprecated but still available in target** → LOW severity, plan migration
- **Removed in future version** → INFO, awareness only

If a single resource is flagged by both Step 2a and Step 2b, report it once
with `source: object+managedFields`. Counting at the API-path level (not the
resource level) is canonical — see `references/report-generation.md` Category 2.

## Output Format

For each finding, report:
- API version and kind
- Resource name and namespace
- **Source** (`object` / `managedFields` / `object+managedFields`)
- Whether it's removed in the target version or just deprecated
- Specific migration command (e.g., update apiVersion field, re-apply manifests
  with the new apiVersion)

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 2 (Deprecated APIs).**

| Finding | Deduction |
|---------|-----------|
| API removed in target version | 5 pts per API path (max 20) |
| API deprecated but available | 1 pt per API path (sub-cap: max 5 pts — enforced in report-generation.md Category 2 pseudocode) |
