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

```bash
kubectl get <kind> --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{"\t"}{range .metadata.managedFields[*]}{.manager}{"="}{.apiVersion}{","}{end}{"\n"}{end}'
```

Output is `namespace/name<TAB>manager1=apiVersion1,manager2=apiVersion2,...`.
The `manager` portion identifies which writer used each apiVersion (e.g.,
`kubectl-client-side-apply`, `argocd-application-controller`, controller
names) — this points to where the source manifest needs to be updated.

**Anti-pattern — do not pre-filter with naïve substring greps.**

```bash
# WRONG — `v1` is a prefix of `v1beta3`, so `grep -v` strips both lines.
... | grep -v "flowcontrol.apiserver.k8s.io/v1"
```

A single resource often has multiple `manager=apiVersion` entries on the
same line (e.g., a controller writing `v1` plus the user writing `v1beta3`).
Filter-then-decide pipelines drop the line entirely as soon as any benign
apiVersion matches. Walk the full output line by line and check each
`manager=apiVersion` pair against the deprecation table in Step 3 instead.

**Anti-pattern — do not substitute `-o yaml` or `-o json`.**

```bash
# WRONG — kubectl 1.21+ hides managedFields from -o yaml / -o json by default,
# so this scan returns false negatives.
kubectl get <kind> -A -o yaml | grep apiVersion
```

Use the `-o jsonpath` form above. It accesses `managedFields` directly and
is not affected by the default-hide behavior.

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
| 1.27 | `storage.k8s.io/v1beta1` CSIStorageCapacity | `storage.k8s.io/v1` |
| 1.26 | `flowcontrol.apiserver.k8s.io/v1beta1` | `flowcontrol.apiserver.k8s.io/v1beta2` |
| 1.29 | `flowcontrol.apiserver.k8s.io/v1beta2` | `flowcontrol.apiserver.k8s.io/v1` |
| 1.32 | `flowcontrol.apiserver.k8s.io/v1beta3` | `flowcontrol.apiserver.k8s.io/v1` |

### Step 3b: Filter Out Already-Migrated / System-Written Resources (deterministic rule)

A `v1beta3` (or other removed-version) string appearing in `metadata.managedFields[]`
does NOT by itself mean a resource needs migrating. The deciding question is **who
wrote the removed version** — a resource is a real finding only if a
**user-controlled writer** actually wrote it.

> **Why not compare served vs stored apiVersion?** Reading the object's live
> `apiVersion` (e.g. `kubectl get flowschema <name> -o jsonpath='{.apiVersion}'`)
> cannot distinguish a migrated object from an unmigrated one: the API server
> serves every object at the version you request, so the read-back value reflects
> the request, not the source manifest. On 1.30+ control planes a `v1` read-back
> can hide a manifest still applied as `v1beta3`. Do NOT use served/stored
> apiVersion as a per-object signal.

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
  `-producer-v1`) or is `eks-internal` → **EXCLUDE.** These are the API server's own
  bootstrap controllers; the user cannot and need not change them.
  (`eks-internal` — exact manager string is UNVERIFIED against public AWS docs as of
  2026-07; AWS documents `manager: eks`. Kept in the exclusion list conservatively.)
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
