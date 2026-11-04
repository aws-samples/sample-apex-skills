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

This reference reads facts through read-only APIs:

- **Kubernetes API** (via the Agent Space EKS access entry) — in-cluster GitOps and CI/CD
  controllers: ArgoCD, Flux, Tekton, Spinnaker (Deployments and their CRDs). Requires
  `authenticationMode` to include `API` and the `AmazonAIOpsAssistantPolicy` access entry to
  be present. RBAC verbs needed: `get`, `list`.
- **AWS EKS API** (`ListCapabilities`, only when requested) — target-cluster hosted Argo capability
  observations, independent of Kubernetes access; requires `eks:ListCapabilities`.

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

If the Kubernetes API is unreachable (access entry absent), mark Kubernetes-derived
facts as `unconfirmed` in Coverage, never `false`; retain independent AWS observations.

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

For every workload read below, request the projected fields described in the
spoke-side collection section. Pseudocode describes collector-side processing;
unfiltered Kubernetes responses must not be returned to the model.

### 1. ArgoCD Detection

ArgoCD is the most popular GitOps tool for Kubernetes. Detecting it reveals the deployment
mechanism. A local installation is self-managed; AWS-hosted capabilities are separate.

**Via Kubernetes API** — detect the ArgoCD controller and version:

- **Resources:** `Deployment` AND `StatefulSet`, group/version `apps/v1`, all namespaces. A namespace-`argocd` query can confirm presence only.
- **Fields to extract:** presence of `argocd-server`; `argocd-server` →
  container images (parse the observed controller image tag for its version); also
  inspect the application-controller StatefulSet. Use the projected identities and
  executable hints described below; a name/image match alone is not controller proof.
- **RBAC verbs:** `get`, `list` on `deployments.apps` AND `statefulsets.apps` across all namespaces for absence checks.

**Via Kubernetes API** — count Applications in the target cluster independently
of controller discovery. Use complete, successful reads (including zero); failed
reads (including missing resource-type errors), incomplete or unattempted reads
remain null. Never infer remote-hub counts:

- **Resource:** `Application`, group/version `argoproj.io/v1alpha1`, all namespaces.
- **Fields to extract:** count of Application resources; `metadata.name`.
- **RBAC verbs:** `get`, `list` on `applications.argoproj.io`.

*Reference pseudocode (kubernetes client), not executable:*
```python
apps = client.AppsV1Api()
custom = client.CustomObjectsApi()

# Use the controller observation established from projected fields below.
version = controller_image.split(":")[-1] if controller_image else None
eks_managed = False if local_argocd_controller_observed else None

# For a complete successful read; otherwise retain null and the Coverage reason.
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

**Via Kubernetes API** — count sources and Kustomizations in the target cluster
independently of controller discovery, using the same read-completeness rules:

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

# Count each complete successful list independently; failed/incomplete reads stay null.
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
Inspect projected Deployment/StatefulSet identities, container images and executable
hints across namespaces. Correlate the component and image with the executable;
a shared Argo image alone can be a CLI workload. An unrecognized command override
or ambiguous role leaves the local flag null. With no override, a dedicated Flux
controller image/component can support detection, but its entrypoint was not inspected.
Metadata-only lists do not establish controller absence. If safe controller
inspection is unavailable, local flags remain null and, without positive evidence,
the overall result is unconfirmed. Establish local absence only from successful, complete
Deployment AND StatefulSet lists across **all namespaces**. Namespaced examples
are shortcuts for confirming presence and cannot establish absence. A namespace, CRD definition, or client CLI version alone does not
prove a running controller.

Read top-level `metadata.labels` and `metadata.annotations` on Deployments,
StatefulSets and DaemonSets across all namespaces by default. ConfigMaps are an
optional extension, not a default cluster-wide list; fetching their full objects
can transfer application data even if the report later filters it. Jobs, CronJobs,
Services and other relevant kinds may extend the selected scope. Declare the scope
and record skipped kinds (including ConfigMaps) as Coverage exclusions for each reported target. Read each
selected kind separately; a denied/truncated selected read is a coverage failure,
not permission to silently shrink the scope. Do not read Helm release Secrets to
resolve tracking ambiguity. This inventory does not cover arbitrary custom resources
or Flux HelmRelease-only tracking.
Retain each API error and the namespaces/kinds actually scanned in Coverage. Missing
CRDs, an empty list, a failed list and incomplete permissions are different observations.

| Signal | Interpretation |
|--------|----------------|
| `argocd.argoproj.io/tracking-id` annotation | Tool-specific tracking evidence only when `<application>:<group>/<kind>:<namespace>/<name>` names the resource it is on. Core resources have an empty group (e.g. `app:/ConfigMap:ns/name`). For a resource confirmed cluster-scoped by API discovery/request context, match group/kind/name; the tracking namespace may be the application destination namespace. Missing namespace/scope context is unconfirmed. Malformed or non-self-referencing/copied annotations are ambiguous. |
| `app.kubernetes.io/instance` label | Specific Argo evidence when a valid tracking-id names the same resource (no label-mode confirmation needed), or when the user confirms that the managing Argo instance uses this key in `label` mode (not `annotation+label`) for this target. Otherwise keep it ambiguous and `unconfirmed`: "instance label seen, could be Helm or Argo CD label mode". Check hub Applications targeting this cluster and their resource/tracking associations to resolve the ambiguity. |
| Other `argocd.argoproj.io/*` annotations | Chart-authored keys such as `sync-wave` do not corroborate tracking. Record representative key/presence only, never values; these hints remain ambiguous, including when an instance label is present. `installation-id` alone is not a substitute for valid self-reference or confirmed label mode. |
| Custom instance label | Accept the key the user supplies as this target's `application.instanceLabelKey`, including an unprefixed key; mark it as user-supplied in Coverage. Never auto-discover unprefixed keys. A qualified custom key may also come from accessible target-linked Argo configuration/resource association; record that provenance. For the standard `app.kubernetes.io/instance` key, configuration discovery alone is insufficient: require the user's target-specific confirmation of `label` mode. An unrelated hub or annotation-only configuration is insufficient. Do not infer ownership from the key's spelling. If the confirmed key is conventionally shared, record that collision caveat; configuration corroborates tracking, not exclusive ownership or live reconciliation. |
| `kustomize.toolkit.fluxcd.io/name` AND `kustomize.toolkit.fluxcd.io/namespace` labels | Tool-specific Flux Kustomization tracking evidence when both values are nonempty. One label alone is ambiguous. This is not exhaustive detection of all Flux/Helm deployment paths. |

Evaluate each signal independently. A configured custom instance label key
adds evidence when matched; it does not override other signal-table rules.

`argocd.argoproj.io/tracking-id` is the tracking **annotation**; do not invent an
`app.kubernetes.io/instance` tracking annotation. Tracking metadata can be stale or
manually copied: report observed tracking, not a verified active hub, sync health,
hub URL, controller namespace/version or remote application counts.

**Assembly rule (both runtimes):** combine local-controller, specific tracking and
observed target-cluster Argo capability evidence. Set `gitops.tools_detected` to all supported tools
with that evidence, `tool` to the single name or `multiple`, `status: detected` and
`detected: true`. This means evidence observed, not live reconciliation verified.
Keep `gitops.evidence` for signal-table tracking observations; put controller facts
in their existing `argocd`/`flux` fields and supporting details in Markdown.
Keep `gitops.argocd.detected` / `gitops.flux.detected` scoped to **local controllers**:
`false` requires successful, complete all-namespace Deployment AND StatefulSet scans;
if either is unreadable and no controller was positively observed, use `null`. Do not set those local flags to true from spoke metadata.

A successful, complete equivalent retry through an available API capability can
satisfy a selected logical read; retain the failed attempt in Coverage. Do not treat
recovered reads as incomplete, or accept a narrower scope as equivalent. Agent Space
has no CLI fallback; if no equivalent API read is available, the gap remains.

Choose the overall outcome after combining the selected reads:
- `detected`: controller, specific tracking or target Argo capability evidence exists. Preserve it
  despite unrelated denied reads and list the remaining gaps.
- `unconfirmed`: no positive evidence and at least one ambiguous signal, unknown
  required tracking key, denied/failed/malformed selected read, or missing/truncated
  page. Set `tool: unconfirmed`, `status: unconfirmed`, `detected: null`. For shared-label
  ambiguity, Coverage must suggest checking hub Applications targeting this cluster
  and their resource/tracking associations. Access failures still need their own reasons.
- `not_observed`: every selected read/page succeeded, resource identity is usable,
  and no known signal (including weak signals) matched. Set `tool: not_observed`,
  `status: not_observed`, `detected: false`, and list the checked signals, kinds and
  namespaces. This describes that scope, not absence of external GitOps. An optional
  ConfigMap inventory not selected is a disclosed exclusion, not a failed selected
  read; a selected ConfigMap inventory that fails instead requires `unconfirmed`.
  Coverage must name the uninspected Flux Helm label pair
  `helm.toolkit.fluxcd.io/name` + `/namespace`; this is not exhaustive Flux detection.

For either nonpositive outcome use `tools_detected: []`. Missing local CRDs alone
never determine the overall outcome. Sampling displayed examples does not mean
input was truncated if all original items were classified. Incomplete input or
helper warnings prevent `not_observed` unless positive evidence already establishes
`detected`. Record the actual checked signals and limitations in Coverage.

Every field under `argocd` and `flux` describes LOCAL observations only and allows
`null`. On a spoke, do not fill hub namespace/version/management type/counts from
workload metadata or turn unavailable hub facts into `false`/`0`. Keep those fields
null; preserve counts from complete successful target-cluster reads independently
of controller flags. Local `detected` can be false after the complete controller
scans above.
A local false does not rule out AWS-managed Argo CD capability; the separate AWS
`ListCapabilities` API check (requiring `eks:ListCapabilities`) for this cluster can
observe capabilities created on this target only, not on a remote hub. Report the
result or access gap separately; an empty result does not exclude hub management.
An observed `type: ARGOCD` capability adds Argo to the overall detected tools; retain
its lifecycle status in Coverage, not the tracking evidence list or local fields.
This is configuration evidence, not readiness or successful reconciliation, and can
coexist with a local install. Keep pagination/access failures visible; without positive
evidence, a failed selected capability read requires `unconfirmed`. Run this optional
check only when requested; otherwise disclose it as uninspected. The supplied
`iam-policy.json` does not grant `eks:ListCapabilities`; do not expand permissions automatically.

Sources: [Argo resource tracking](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_tracking/)
and [Flux remote-cluster Kustomizations](https://fluxcd.io/flux/components/kustomize/kustomizations/#kubeconfig-remote-clusters).
Argo permits the destination namespace on cluster-scoped tracking IDs; see its
[version-matched self-reference check](https://github.com/argoproj/argo-cd/blob/v3.5.6/controller/state.go).
For metadata-only API identity, see [Kubernetes metadata-only fetches](https://kubernetes.io/docs/reference/using-api/api-concepts/#metadata-only-fetches).

**Bounded evidence:** inspect every selected API page before choosing a small set
of representative examples covering each observed tool and ambiguity. Keep the
report concise, shorten long displayed values, and disclose sampling or shortening
in Coverage. Do not calculate per-group totals or infer tool presence from only the
examples displayed. Classify original values, not shortened text. Output limits do
not limit API response size.

**Via Kubernetes API** — project selected workload observations before tool output
enters the model context (filtering the final report is insufficient):

- **Resources:** selected kinds from the scope above; ConfigMaps remain optional.
- **Fields to extract:** original resource identity, signal-table label/tracking-id
  values, and other Argo annotation keys/presence only. For controller discovery,
  also select container images and a derived executable hint: inspect `command[0]`,
  or `args[0]` only when no command override exists. Emit only an exact basename match
  for `argocd-server`, `argocd-application-controller`, `argocd-repo-server`,
  `argocd-applicationset-controller`, `source-controller`, `kustomize-controller`,
  `helm-controller` or `notification-controller`; otherwise `other` for an override,
  or `image-default` without one. Never return raw command paths, args, env or full workload bodies.
  If the capability cannot project safely, record which reads are unavailable;
  for metadata reads state "workload projection unavailable: spoke-side signals not inspected".
  Retain
  request identity, failed reads and continuation tokens; never turn a projection
  error into an empty successful list. Preserve malformed/missing field warnings;
  key/presence conversion must not turn invalid values into valid evidence.
- **RBAC verbs:** `get`, `list` on each selected kind in its API group.

Metadata-only fetches still need annotation-value filtering before tool output.
Prefer them when the capability supports
them and request/discovery context is retained, particularly for ConfigMaps. Process
every API page or namespace batch and retain bounded examples without copying full
ConfigMap bodies into the report. Record truncation or missing pages as gaps.
PartialObjectMetadata returns `meta.k8s.io/v1` /
`PartialObjectMetadata`: recover the original group/kind from the request/discovery
context, including whether the kind is namespaced, before checking self-reference. Never derive that identity from the tracking
annotation. If request context is unavailable, obtain projected identity or leave the
evidence unconfirmed. Metadata cannot establish controller versions/health. Use the
original group/kind and the returned namespace/name for self-reference. Record each observation as an evidence
example with `tool`, `signal`, `kind`, `namespace`, `name`, `key`, `value`, and `strength`
(`specific` or `ambiguous`). For the shared instance label, `tool` is `null` until
corroborated; for the Flux pair, `value` contains both `name` and `namespace`.
Only signal-table values may appear in tracking evidence or its Coverage prose;
unknown keys may be named without their values. Never record or quote other
label/annotation values, including `kubectl.kubernetes.io/last-applied-configuration`:
metadata-only responses still include that annotation and it can contain ConfigMap
data. For wildcard Argo annotations retain representative key/presence examples,
never values. They remain ambiguous hints and cannot corroborate an instance label. Treat wildcard names
as one evidence family so distinct keys do not create unbounded examples. These
privacy limits do not prohibit projected controller images and executable hints.
No shell or executable helper is needed in Agent Space.

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

  gitops:
    tool: string              # argocd | flux | multiple | unconfirmed | not_observed
    status: string            # detected | unconfirmed | not_observed; evidence in the checked scope, not active management
    detected: bool | null     # true for evidence; false only for not_observed; null for unconfirmed
    tools_detected: list      # all tools evidenced by controllers, tracking or target Argo capability
    evidence: list            # representative signal-table observations; sampling and provenance in Coverage
    # Every nested field below is LOCAL ONLY; unavailable hub facts remain null.
    argocd:
      detected: bool | null   # false only after complete local controller scans
      namespace: string | null
      version: string | null # observed local server/controller image, never a client version
      eks_managed: bool | null # false for observed local self-managed install; otherwise null; hosted capabilities separate
      applications: int | null # locally observable Applications only
    flux:
      detected: bool | null   # local controller, not remote management
      namespace: string | null
      version: string | null # observed local source-controller image only
      git_repositories: int | null # locally observable sources only
      kustomizations: int | null # locally observable Kustomizations only

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

These local Argo pattern checks require `gitops.argocd.detected: true`.
Tracking evidence alone on a spoke does not enable them: hub-only Applications
and ApplicationSets are not observable there; record that in Coverage.

### GitOps Bridge (Terraform + ArgoCD)

The GitOps Bridge pattern uses Terraform to bootstrap ArgoCD, then ArgoCD manages applications.
The Terraform half is a workspace-file signal and is **unavailable** in the Agent Space; only
the ArgoCD half is observable (via the Kubernetes API). When `gitops.argocd.detected: true`, note that a
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
