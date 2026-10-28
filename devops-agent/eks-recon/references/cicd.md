# Module: CI/CD

> **Part of:** [eks-recon](../SKILL.md)
> **Purpose:** Detect CI/CD pipelines and GitOps tools - GitHub Actions, GitLab CI, Jenkins, ArgoCD, Flux

## Table of Contents

- [Access Model](#access-model)
- [Detection Strategy](#detection-strategy)
- [Detection Capabilities](#detection-capabilities)
  - [1. ArgoCD Detection](#1-argocd-detection)
  - [2. Flux Detection](#2-flux-detection)
  - [3. Tekton Detection](#3-tekton-detection)
  - [4. Spinnaker Detection](#4-spinnaker-detection)
- [Spoke-side tracking and the GitOps outcome](#spoke-side-tracking-and-the-gitops-outcome)
- [Output Schema](#output-schema)
- [Integration Patterns](#integration-patterns)
- [Edge Cases](#edge-cases)

---

## Access Model

This reference reads facts from one source, read-only:

- **Kubernetes API** (via the Agent Space EKS access entry) — in-cluster GitOps and CI/CD
  controllers: ArgoCD, Flux, Tekton, Spinnaker (Deployments and their CRDs). Requires
  `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry to
  be present. RBAC verbs needed: `get`, `list`.

**Honest limitation — workspace CI detection is NOT available in the Agent Space.** The Claude
Code version scans a local repository filesystem for CI config files (GitHub Actions
`.github/workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml`,
`buildspec*.yml`/CodePipeline definitions, `atlantis.yaml`). The DevOps Agent has **no shell
and no filesystem access** — there is no repo to scan, so **workspace CI/CD detection is
unavailable**. Those `workspace.*` sub-facts are recorded as `unconfirmed` in the report's
Coverage section — never as `false`. State this in the report so a null workspace result is not
misread as "no CI/CD exists".

**In-cluster GitOps detection IS available via the Kubernetes API** — ArgoCD, Flux, Tekton, and
Spinnaker run as controllers inside the cluster and are read through the access entry.

If the Kubernetes API is unreachable (access entry absent), mark every GitOps sub-fact as
`unconfirmed` in the Coverage section — never as `false`.

> **Reference pseudocode note.** Code blocks labeled *reference pseudocode (kubernetes client)*
> below illustrate the resource, fields, and RBAC verbs for each K8s-API read. They are **not
> executable** in the Agent Space and are not an operational path — do not emit
> `kubectl ... | jq` pipelines. The agent reads these resources through its
> Kubernetes-API capability.

---

## Detection Strategy

Workspace CI config files cannot be scanned (no filesystem). Detection runs against in-cluster
GitOps/CI controllers plus spoke-side workload tracking:

```
Kubernetes API (controllers AND workload metadata):
- ArgoCD    -> Deployment in argocd namespace + Application CRDs
- Flux      -> Deployment in flux-system namespace + GitRepository/Kustomization CRDs
- Tekton    -> pipelines/pipelineruns.tekton.dev
- Spinnaker -> spin-* Deployments
```

---

## Detection Capabilities

### 1. ArgoCD Detection

ArgoCD is the most popular GitOps tool for Kubernetes. Detecting it reveals the deployment
mechanism and, where labeled, whether the install is the EKS-managed ArgoCD Capability.

**Via Kubernetes API** — detect the ArgoCD controller and version:

- **Resources:** `Deployment` AND `StatefulSet`, group/version `apps/v1`, all namespaces. A namespace-`argocd` query can confirm presence only.
- **Fields to extract:** presence of `argocd-server`; `argocd-server` →
  `spec.template.spec.containers[0].image` (parse the tag for the ArgoCD version); also inspect the application-controller StatefulSet image; label
  `eks.amazonaws.com/component` on the ArgoCD Deployments (present ⇒ EKS-managed ArgoCD
  Capability, else self-managed).
- **RBAC verbs:** `get`, `list` on `deployments.apps` AND `statefulsets.apps` across all namespaces for absence checks.

**Via Kubernetes API** — count ArgoCD Applications:

- **Resource:** `Application`, group/version `argoproj.io/v1alpha1`, all namespaces.
- **Fields to extract:** count of Application resources; `metadata.name`.
- **RBAC verbs:** `get`, `list` on `applications.argoproj.io`.

*Reference pseudocode (kubernetes client), not executable:*
```python
apps = client.AppsV1Api()
custom = client.CustomObjectsApi()

# Presence-only shortcut. This cannot establish local absence.
deploys = apps.list_namespaced_deployment("argocd").items
server = next((d for d in deploys if d.metadata.name == "argocd-server"), None)
version = server.spec.template.spec.containers[0].image.split(":")[-1] if server else None
eks_managed = any(
    (d.metadata.labels or {}).get("eks.amazonaws.com/component") == "argocd"
    for d in deploys)

applications = custom.list_cluster_custom_object(
    "argoproj.io", "v1alpha1", "applications")["items"]
app_count = len(applications)
```

Record `gitops.argocd`: `detected`, `namespace`, `version`, `eks_managed`, and `applications`
(count).

### 2. Flux Detection

Flux is the CNCF GitOps tool, often preferred for multi-cluster setups. Detecting it reveals
GitRepository and Kustomization reconciliation.

**Via Kubernetes API** — detect the Flux controllers and version:

- **Resources:** `Deployment` AND `StatefulSet`, group/version `apps/v1`, all namespaces (e.g.
  `source-controller`, `kustomize-controller`, `helm-controller`, `notification-controller`).
- **Fields to extract:** presence of the controllers; `source-controller` →
  `spec.template.spec.containers[0].image` (parse the tag for the Flux version).
- **RBAC verbs:** `get`, `list` on `deployments.apps` AND `statefulsets.apps` across all namespaces for absence checks.

**Via Kubernetes API** — count Flux sources and Kustomizations:

- **Resource:** `GitRepository`, group/version `source.toolkit.fluxcd.io/v1`; and
  `Kustomization`, group/version `kustomize.toolkit.fluxcd.io/v1`, all namespaces.
- **Fields to extract:** count of GitRepository resources; count of Kustomization resources.
- **RBAC verbs:** `get`, `list` on `gitrepositories.source.toolkit.fluxcd.io` and
  `kustomizations.kustomize.toolkit.fluxcd.io`.

*Reference pseudocode (kubernetes client), not executable:*
```python
apps = client.AppsV1Api()
custom = client.CustomObjectsApi()

# Presence-only shortcut. This cannot establish local absence.
deploys = apps.list_namespaced_deployment("flux-system").items
sc = next((d for d in deploys if d.metadata.name == "source-controller"), None)
version = sc.spec.template.spec.containers[0].image.split(":")[-1] if sc else None

git_repos = custom.list_cluster_custom_object(
    "source.toolkit.fluxcd.io", "v1", "gitrepositories")["items"]
kustomizations = custom.list_cluster_custom_object(
    "kustomize.toolkit.fluxcd.io", "v1", "kustomizations")["items"]
```

Record `gitops.flux`: `detected`, `namespace`, `version`, `git_repositories` (count), and
`kustomizations` (count).

### 3. Tekton Detection

Tekton is a Kubernetes-native CI/CD framework; pipelines run as pods in the cluster itself.

**Via Kubernetes API** — count Tekton pipelines:

- **Resource:** `Pipeline`, group/version `tekton.dev/v1` (`pipelines.tekton.dev`); and
  `PipelineRun` (`pipelineruns.tekton.dev`), all namespaces.
- **Fields to extract:** count of Pipeline resources; count of PipelineRun resources; the
  namespace(s) they run in.
- **RBAC verbs:** `get`, `list` on `pipelines.tekton.dev` and `pipelineruns.tekton.dev`.

Record `other_tools.tekton`: `detected`, `namespace`, and counts of `pipelines`/`pipelineruns`.

### 4. Spinnaker Detection

Spinnaker is an enterprise deployment platform with advanced strategies (canary, blue-green),
often used in large organizations.

**Via Kubernetes API** — detect Spinnaker microservices:

- **Resource:** `Deployment`, group/version `apps/v1`, namespace `spinnaker` (or wherever
  `spin-*` deployments run, e.g. `spin-clouddriver`, `spin-deck`, `spin-gate`, `spin-orca`).
- **Fields to extract:** presence of any `spin-*` Deployment; the namespace.
- **RBAC verbs:** `get`, `list` on `deployments.apps`.

Record `other_tools.spinnaker`: `detected` and `namespace`.

---

### Spoke-side tracking and the GitOps outcome

**Always inspect workload metadata, even when local controller/CRD reads are empty.**
A hub can manage this cluster without installing Argo/Flux controllers or CRDs here.
Discover controllers in readable Deployments/StatefulSets across namespaces and inspect
their container images. Establish local absence only from successful, complete
Deployment AND StatefulSet lists across **all namespaces**. Namespaced examples
are shortcuts for confirming presence and cannot establish absence. A namespace, CRD definition, or client CLI version alone does not
prove a running controller.

Read top-level `metadata.labels` and `metadata.annotations` on accessible Deployments,
StatefulSets, DaemonSets, Jobs, CronJobs, Services and ConfigMaps. Read each resource
kind separately so one denied kind does not discard successful reads of another.
Include other relevant kinds when discovery/permissions allow; this bounded inventory
does not cover every custom resource. Do not read Secrets for tracking detection.
Retain each API error and the namespaces/kinds actually scanned in Coverage. Missing
CRDs, an empty list, a failed list and incomplete permissions are different observations.

| Signal | Interpretation |
|--------|----------------|
| `argocd.argoproj.io/tracking-id` annotation | Tool-specific tracking evidence only when `<application>:<group>/<kind>:<namespace>/<name>` names the resource it is on. Core resources have an empty group (e.g. `app:/ConfigMap:ns/name`). For a resource confirmed cluster-scoped by API discovery/request context, match group/kind/name; the tracking namespace may be the application destination namespace. Missing namespace/scope context is unconfirmed. Malformed or non-self-referencing/copied annotations are ambiguous. |
| `app.kubernetes.io/instance` label | Ambiguous by itself: Helm and other tools also use it. Keep the observed value; do not attribute it to Argo without corroboration. This also covers Argo's `label` mode when the hub is inaccessible. |
| Custom instance label | Use a dedicated key explicitly linked to this target by the user or accessible Argo tracking configuration/resource association. Record that provenance; a setting from an unrelated hub or annotation-only configuration is insufficient. Only qualified custom keys (`prefix/key`) are sufficient under this rule. Shared `app.kubernetes.io/*`, `helm.sh/*`, Flux tracking keys, unqualified keys and known collisions remain ambiguous even when supplied. Qualification alone does not establish dedicated use; do not guess a key or attribute ordinary labels to Argo. |
| `kustomize.toolkit.fluxcd.io/name` AND `kustomize.toolkit.fluxcd.io/namespace` labels | Tool-specific Flux Kustomization tracking evidence when both values are nonempty. One label alone is ambiguous. This is not exhaustive detection of all Flux/Helm deployment paths. |

`argocd.argoproj.io/tracking-id` is the tracking **annotation**; do not invent an
`app.kubernetes.io/instance` tracking annotation. Tracking metadata can be stale or
manually copied: report observed tracking, not a verified active hub, sync health,
hub URL, controller namespace/version or remote application counts.

**Assembly rule (both runtimes):** combine readable local-controller evidence and
tool-specific tracking evidence. Set `gitops.tools_detected` to all supported tools
with that evidence, `tool` to the single name or `multiple`, `status: detected` and
`detected: true`. This means evidence observed, not live reconciliation verified.
Keep `gitops.argocd.detected` / `gitops.flux.detected` scoped to **local controllers**:
`false` requires successful, complete all-namespace Deployment AND StatefulSet scans;
if either is unreadable and no controller was positively observed, use `null`. Do not set those local flags to true from spoke metadata.

With only ambiguous signals, no signals, partial/denied reads or an unknown custom
tracking key, emit `tool: unconfirmed`, `status: unconfirmed`, `detected: null`,
`tools_detected: []`, and explain the evidence/coverage limit. Never turn absent
local CRDs into `tool: none` / `detected: false` for overall GitOps management.
Positive evidence survives unrelated denied reads: retain detected tools and list
the remaining gaps rather than replacing a positive result with unknown.
Use `null` for unobserved hub facts and inaccessible counts; do not infer a remote
application count from the number of labeled resources. An empty evidence list is
not a claim that no external GitOps exists.

Sources: [Argo resource tracking](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_tracking/)
and [Flux remote-cluster Kustomizations](https://fluxcd.io/flux/components/kustomize/kustomizations/#kubeconfig-remote-clusters).
Argo permits the destination namespace on cluster-scoped tracking IDs; see its
[version-matched self-reference check](https://github.com/argoproj/argo-cd/blob/v3.5.6/controller/state.go).
For metadata-only API identity, see [Kubernetes metadata-only fetches](https://kubernetes.io/docs/reference/using-api/api-concepts/#metadata-only-fetches).

**Bounded evidence:** classify every item in each successful input, then retain
at most **3 examples per `(tool, signal, strength, key)` across the final report**.
Combine detected tools from all reads; never infer tool presence only from the first
examples or cut input off with `head`. Examples are not resource/application counts.
Shorten displayed strings to 256 characters with `...[truncated]`, preserving full
label keys up to Kubernetes' 317-character limit. Classify original values, never
shortened text. Ignore an oversized custom key with a warning; keep standard signals.
Keep at most 5 warning examples and note sampling, shortening, failed reads or missing
pages in Coverage, including when examples were sampled during collection or
further limited in the final report. Output is bounded; API response size and parser memory are not.

**Via Kubernetes API:** list each readable resource above with `get`/`list`
permission on its API group (`apps`, `batch`, or core). Inspect the top-level metadata
fields in the signal table. Prefer metadata-only fetches when the capability supports
them and request/discovery context is retained, particularly for ConfigMaps. Process
every API page or namespace batch and retain bounded examples without copying full
ConfigMap bodies into the report. Record truncation or missing pages as gaps.
PartialObjectMetadata returns `meta.k8s.io/v1` /
`PartialObjectMetadata`: recover the original group/kind from the request/discovery
context, including whether the kind is namespaced, before checking self-reference. Never derive that identity from the tracking
annotation. If request context is unavailable, obtain normal objects or leave the
evidence unconfirmed. Metadata cannot establish controller versions/health. Use the
original group/kind and the returned namespace/name for self-reference. Record each observation as an evidence
example with `tool`, `signal`, `kind`, `namespace`, `name`, `key`, `value`, and `strength`
(`specific` or `ambiguous`). For the shared instance label, `tool` is `null` until
corroborated; for the Flux pair, `value` contains both `name` and `namespace`.
Apply the example limits above. No shell or executable helper is needed in Agent Space.

## Output Schema

This is the **single canonical schema** for the cicd module — it carries every CI/CD and
GitOps fact (plus the shared `cluster:` block from `references/cluster-basics.md`). Use `null`
where a fact was not detected; never omit a key. Where a fact could not be checked (workspace
CI files in Agent Space, or Kubernetes API unreachable), record it as `unconfirmed` in the
report's Coverage section rather than emitting a misleading `false`.

```yaml
cicd:
  workspace:
    # NOTE: workspace CI/CD detection is UNAVAILABLE in the Agent Space (no filesystem).
    # Every sub-fact below requires reading repository config files and is recorded as
    # `unconfirmed` in the report's Coverage section — never as false.
    tools:
      count: int              # unconfirmed — no filesystem in Agent Space
      list: list              # unconfirmed — no filesystem in Agent Space
    github_actions:
      detected: bool          # unconfirmed — requires repository access
      workflows:
        count: int            # unconfirmed
        list: list            # unconfirmed
      eks_related: bool       # unconfirmed
    gitlab_ci:
      detected: bool          # unconfirmed — requires repository access
      config_path: string     # unconfirmed
    jenkins:
      detected: bool          # unconfirmed — requires repository access
      jenkinsfile_path: string   # unconfirmed
      pipeline_libraries: list   # unconfirmed
    circleci:
      detected: bool          # unconfirmed — requires repository access
      config_path: string     # unconfirmed
    codepipeline:
      detected: bool          # unconfirmed — requires repository access
      buildspec_paths: list   # unconfirmed
    atlantis:
      detected: bool          # unconfirmed — requires repository access
      config_path: string     # unconfirmed

  gitops:                     # detectable via Kubernetes API
    tool: string              # argocd | flux | multiple | unconfirmed
    status: string            # detected | unconfirmed (evidence, not verified active management)
    detected: bool | null     # true when evidence observed; null when unconfirmed, never false from missing CRDs
    tools_detected: list      # all tools evidenced by local controllers or specific tracking
    evidence: list            # <=3 examples per tool/signal/strength/key; scan gaps in Coverage
    # Configured custom-label provenance and scan gaps belong in Coverage.
    # Each nested detected flag below describes LOCAL controllers only.
    argocd:
      detected: bool | null   # local controller: false only after successful scan; null if unreadable
      namespace: string
      version: string         # from argocd-server container image tag
      eks_managed: bool       # EKS ArgoCD Capability (AWS-managed) vs self-managed
      applications: int       # count of Application resources
    flux:
      detected: bool | null   # local controller, not remote management
      namespace: string
      version: string         # from source-controller image tag
      git_repositories: int   # count of GitRepository resources
      kustomizations: int     # count of Kustomization resources

  other_tools:                # additional CI/CD platforms detected in-cluster (Kubernetes API)
    spinnaker:
      detected: bool
      namespace: string       # namespace where spin-* deployments run, null if absent
    tekton:
      detected: bool
      namespace: string
      pipelines: int          # count of pipelines.tekton.dev resources
      pipelineruns: int       # count of pipelineruns.tekton.dev resources
```

---

## Integration Patterns

### GitOps Bridge (Terraform + ArgoCD)

The GitOps Bridge pattern uses Terraform to bootstrap ArgoCD, then ArgoCD manages applications.
The Terraform half is a workspace-file signal and is **unavailable** in the Agent Space; only
the ArgoCD half is observable (via the Kubernetes API). When ArgoCD is detected, note that a
GitOps Bridge may be present but the Terraform bootstrap cannot be confirmed here.

### App of Apps

App of Apps is an ArgoCD pattern where one root Application manages other Applications.

**Via Kubernetes API:** list `Application` (`argoproj.io/v1alpha1`) resources and identify roots
whose `spec.source.path` references `apps`/`applications`. Record the root Application name(s).
RBAC: `get`, `list` on `applications.argoproj.io`.

### ApplicationSets

ApplicationSets generate multiple Applications from templates.

**Via Kubernetes API:** list `ApplicationSet` (`argoproj.io/v1alpha1`) resources, all namespaces.
Record presence and names. RBAC: `get`, `list` on `applicationsets.argoproj.io`.

---

## Edge Cases

### Multiple CI/CD Tools

Common to have multiple tools (e.g. GitHub Actions for CI + ArgoCD for CD). Report all
detectable in-cluster tools; note that workspace CI tools cannot be observed in the Agent Space,
so the CI half of such a split is `unconfirmed`.

### Workspace CI Not Observable

The Agent Space has no filesystem, so repository-based CI config (GitHub Actions, GitLab CI,
Jenkins, CircleCI, CodePipeline, Atlantis) cannot be scanned. A null `workspace.*` fact means
"not observable here", not "no CI/CD". Record these as `unconfirmed` in the Coverage section and
state the limitation in the report. In-cluster GitOps controllers indicate the deployment
mechanism regardless.

### Tekton Pipelines

Tekton runs as pods in the cluster. Detected via capability 3 — record under
`cicd.other_tools.tekton`.

### Spinnaker

Spinnaker runs as `spin-*` microservices in the cluster. Detected via capability 4 — record
under `cicd.other_tools.spinnaker`.
