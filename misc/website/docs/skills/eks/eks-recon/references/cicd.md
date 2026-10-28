---
title: "Module: CI/CD"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/cicd.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/references/cicd.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/references/cicd.md). Edit the source, not this page.
:::

# Module: CI/CD

> **Part of:** [eks-recon](../)
> **Purpose:** Detect CI/CD pipelines and GitOps tools - GitHub Actions, GitLab CI, Jenkins, ArgoCD, Flux

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Workspace CI/CD](#workspace-cicd)
  - [In-Cluster GitOps](#in-cluster-gitops)
- [Spoke-side tracking and the GitOps outcome](#spoke-side-tracking-and-the-gitops-outcome)
- [Output Schema](#output-schema)
- [Integration Patterns](#integration-patterns)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Cluster name required:** Partial (only for in-cluster GitOps detection)
- **MCP tools used:** `list_k8s_resources` (for GitOps)
- **CLI fallback:** `find`, `kubectl`, Python 3

---

## Detection Strategy

CI/CD detection has two parts:

1. **Workspace scan** - Find CI/CD config files in local filesystem
2. **Cluster scan** - Inspect local controllers AND spoke-side workload tracking; report unconfirmed where evidence is insufficient

```
Workspace:
- GitHub Actions  -> .github/workflows/*.yml
- GitLab CI       -> .gitlab-ci.yml
- Jenkins         -> Jenkinsfile
- CircleCI        -> .circleci/config.yml
- AWS CodePipeline -> buildspec.yml, pipeline.json

In-Cluster:
- ArgoCD          -> Deployment in argocd namespace
- Flux            -> Deployment in flux-system namespace
```

---

## Detection Commands

### Workspace CI/CD

#### GitHub Actions

**Why detect GitHub Actions:** GitHub Actions is the most common CI/CD for projects hosted on GitHub. Finding EKS-related workflows reveals how deployments happen and what credentials/roles are used.

```bash
# Find GitHub Actions workflows
find . -path "./.github/workflows/*.yml" -o -path "./.github/workflows/*.yaml" 2>/dev/null | head -10
```

**Example output:**
```
./.github/workflows/ci.yml
./.github/workflows/deploy-staging.yml
./.github/workflows/deploy-prod.yml
```

**If found, check for EKS-related jobs** to identify deployment workflows:
```bash
grep -l "aws-actions/configure-aws-credentials\|kubectl\|helm\|eks" \
  .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null | head -5
```

**Example output:**
```
./.github/workflows/deploy-staging.yml
./.github/workflows/deploy-prod.yml
```

#### GitLab CI

**Why detect GitLab CI:** For projects on GitLab, this is the native CI/CD. Finding EKS references helps understand deployment pipelines and AWS integration.

```bash
# Find GitLab CI config
find . -name ".gitlab-ci.yml" -type f 2>/dev/null | head -3
```

**Example output:**
```
./.gitlab-ci.yml
```

**If found, check for EKS-related stages** to confirm Kubernetes deployments:
```bash
grep -l "kubectl\|helm\|aws eks\|eksctl" .gitlab-ci.yml 2>/dev/null
```

#### Jenkins

**Why detect Jenkins:** Jenkins remains common in enterprise environments. Pipeline libraries in `vars/` indicate shared deployment logic across teams.

```bash
# Find Jenkinsfile
find . -name "Jenkinsfile" -type f 2>/dev/null | head -5
```

**Example output:**
```
./Jenkinsfile
./pipelines/Jenkinsfile.deploy
```

**Check for pipeline libraries** that may contain shared EKS deployment steps:
```bash
find . -path "*/vars/*.groovy" -type f 2>/dev/null | head -5
```

**Example output:**
```
./vars/deployToEKS.groovy
./vars/helmDeploy.groovy
```

#### CircleCI

**Why detect CircleCI:** Popular cloud CI service with orbs for EKS deployments. Config structure differs from GitHub Actions.

```bash
# Find CircleCI config
find . -path "./.circleci/config.yml" -type f 2>/dev/null
```

**Example output:**
```
./.circleci/config.yml
```

#### AWS CodePipeline/CodeBuild

**Why detect CodePipeline/CodeBuild:** Native AWS CI/CD that integrates directly with IAM roles. Often used with EKS for seamless AWS permissions.

```bash
# Find buildspec files
find . -name "buildspec*.yml" -o -name "buildspec*.yaml" 2>/dev/null | head -5
```

**Example output:**
```
./buildspec.yml
./buildspec-deploy.yml
```

```bash
# Find pipeline definitions
find . -name "pipeline*.json" -o -name "codepipeline*.json" 2>/dev/null | head -3
```

**Example output:**
```
./infra/codepipeline.json
```

---

### In-Cluster GitOps

#### ArgoCD Detection

**Why detect ArgoCD:** ArgoCD is the most popular GitOps tool for Kubernetes. Understanding ArgoCD setup helps coordinate cluster upgrades with application deployments and reveals the GitOps repository structure.

**MCP (check for deployment):**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Deployment",
  api_version="apps/v1",
  namespace="argocd"
)
```

**MCP (Applications in the target cluster):**
Read independently of controller discovery. Counts require complete, successful
results; failed reads (including missing resource-type errors), incomplete or
unattempted reads remain `null`. Do not count
truncated examples or infer remote-hub counts from workload metadata.
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Application",
  api_version="argoproj.io/v1alpha1"
)
```

**CLI:**
```bash
# Presence-only shortcut; absence requires all-namespace Deployment/StatefulSet scans
kubectl get deploy -n argocd
```

**Example output:**
```
NAME                               READY   UP-TO-DATE   AVAILABLE   AGE
argocd-applicationset-controller   1/1     1            1           45d
argocd-dex-server                  1/1     1            1           45d
argocd-notifications-controller    1/1     1            1           45d
argocd-redis                       1/1     1            1           45d
argocd-repo-server                 1/1     1            1           45d
argocd-server                      1/1     1            1           45d
```

```bash
# Check for Applications
kubectl get applications.argoproj.io -A
```

**Example output:**
```
NAMESPACE   NAME              SYNC STATUS   HEALTH STATUS
argocd      platform-addons   Synced        Healthy
argocd      app-frontend      Synced        Healthy
argocd      app-backend       Synced        Progressing
```

```bash
# Get ArgoCD version
kubectl get deploy -n argocd argocd-server -o jsonpath='{.spec.template.spec.containers[0].image}'
```

**Example output:**
```
quay.io/argoproj/argocd:v2.10.5
```

**Local install management evidence:** inspect labels only when a local Argo
controller was observed. With no local controller, `eks_managed` is null. This
local check cannot rule out the AWS-managed capability; see `ListCapabilities`
in the outcome rules below.
```bash
# Check if ArgoCD is EKS-managed
kubectl get deploy -n argocd -o json | \
  jq -r '.items[].metadata.labels["eks.amazonaws.com/component"]'
```

**Example output (EKS-managed):**
```
argocd
```

#### Flux Detection

**Why detect Flux:** Flux is the CNCF GitOps tool, often preferred for multi-cluster setups. Understanding Flux configuration helps coordinate upgrades with GitRepository and Kustomization reconciliation cycles.

**MCP (check for deployment):**
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Deployment",
  api_version="apps/v1",
  namespace="flux-system"
)
```

**MCP (Kustomizations in the target cluster):**
Read GitRepositories and Kustomizations independently of controller discovery.
For each count, use a complete successful result (including zero); otherwise
retain `null` and the Coverage reason, as for Applications above.
```
list_k8s_resources(
  cluster_name="<cluster-name>",
  kind="Kustomization",
  api_version="kustomize.toolkit.fluxcd.io/v1"
)
```

**CLI:**
```bash
# Presence-only shortcut; absence requires all-namespace Deployment/StatefulSet scans
kubectl get deploy -n flux-system
```

**Example output:**
```
NAME                          READY   UP-TO-DATE   AVAILABLE   AGE
helm-controller               1/1     1            1           90d
kustomize-controller          1/1     1            1           90d
notification-controller       1/1     1            1           90d
source-controller             1/1     1            1           90d
```

```bash
# Check for GitRepositories
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
```

**Example output:**
```
NAMESPACE     NAME          URL                                       AGE    READY
flux-system   flux-system   ssh://git@github.com/org/gitops-repo      90d    True
flux-system   app-repo      ssh://git@github.com/org/app-manifests    45d    True
```

```bash
# Check for Kustomizations
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
```

**Example output:**
```
NAMESPACE     NAME          AGE   READY   STATUS
flux-system   flux-system   90d   True    Applied revision: main@sha1:abc123
flux-system   apps          90d   True    Applied revision: main@sha1:def456
```

```bash
# Read the observed controller image (a local flux CLI version is not this fact)
kubectl get deploy -n flux-system source-controller -o jsonpath='{.spec.template.spec.containers[0].image}'
```

**Example output:**
```
ghcr.io/fluxcd/source-controller:v1.2.4
```

---

### Spoke-side tracking and the GitOps outcome

**Always inspect workload metadata, even when local controller/CRD reads are empty.**
A hub can manage this cluster without installing Argo/Flux controllers or CRDs here.
Apply the controller component names and image checks above to readable
Deployments/StatefulSets across namespaces. An image match alone may be a CLI
workload; an ambiguous component role leaves the local flag null.
Metadata-only lists suffice for tracking, not controller
absence: obtain full Deployment/StatefulSet objects for image inspection. If that
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
| `app.kubernetes.io/instance` label | Weak alone: Helm charts (by convention) and Argo CD label tracking both use it. Keep the evidence as ambiguous and `unconfirmed` with reason "instance label seen, could be Helm or Argo CD label mode". Attribute it to Argo only with a valid tracking-id or another nonempty `argocd.argoproj.io/*` annotation on the same resource, or the user's target-specific statement that the hub uses this key for label tracking. A hub-side check of Applications whose destination is this cluster resolves the ambiguity. |
| Other `argocd.argoproj.io/*` annotations | Corroborate an instance label on the same resource only. Record one annotation key and its presence, never its value. An annotation alone is ambiguous (`unconfirmed` without other positive evidence), not a positive; malformed/non-self-referencing tracking-id cannot serve as this corroboration. |
| Custom instance label | Accept the key the user supplies as this target's `application.instanceLabelKey`, including an unprefixed key; mark it as user-supplied in Coverage. Never auto-discover unprefixed keys. A qualified key may also come from accessible target-linked Argo configuration/resource association; record that provenance. An unrelated hub or annotation-only configuration is insufficient. Do not infer ownership from the key's spelling. If the confirmed key is conventionally shared, record that collision caveat; configuration corroborates tracking, not exclusive ownership or live reconciliation. |
| `kustomize.toolkit.fluxcd.io/name` AND `kustomize.toolkit.fluxcd.io/namespace` labels | Tool-specific Flux Kustomization tracking evidence when both values are nonempty. One label alone is ambiguous. This is not exhaustive detection of all Flux/Helm deployment paths. |

Evaluate each signal independently. A configured custom instance label key
adds evidence when matched; it does not override other signal-table rules.

`argocd.argoproj.io/tracking-id` is the tracking **annotation**; do not invent an
`app.kubernetes.io/instance` tracking annotation. Tracking metadata can be stale or
manually copied: report observed tracking, not a verified active hub, sync health,
hub URL, controller namespace/version or remote application counts.

**Assembly rule (both runtimes):** combine readable local-controller evidence and
tool-specific tracking evidence. Set `gitops.tools_detected` to all supported tools
with that evidence, `tool` to the single name or `multiple`, `status: detected` and
`detected: true`. This means evidence observed, not live reconciliation verified.
Keep `gitops.evidence` for signal-table tracking observations; put controller facts
in their existing `argocd`/`flux` fields and supporting details in Markdown.
Keep `gitops.argocd.detected` / `gitops.flux.detected` scoped to **local controllers**:
`false` requires successful, complete all-namespace Deployment AND StatefulSet scans;
if either is unreadable and no controller was positively observed, use `null`. Do not set those local flags to true from spoke metadata.

For tracking evidence and its Coverage prose, use only signal-table values. Unknown
label/annotation keys may be named without quoting their values. Other Argo
annotations contribute key/presence only, never raw values. This does not prohibit
the separately documented local-controller image and management observations. In the
MCP path, exclude `kubectl.kubernetes.io/last-applied-configuration` values too:
even metadata-only responses can contain serialized ConfigMap data there.

A successful, complete equivalent CLI fallback can satisfy a selected logical read
after an MCP failure; retain the failed attempt in Coverage. Do not treat recovered
reads as incomplete, or accept a fallback with a narrower scope as equivalent.

Choose the overall outcome after combining the selected reads:
- `detected`: positive controller or specific tracking evidence exists. Preserve it
  despite unrelated denied reads and list the remaining gaps.
- `unconfirmed`: no positive evidence and at least one ambiguous signal, unknown
  required tracking key, denied/failed/malformed selected read, or missing/truncated
  page. Set `tool: unconfirmed`, `status: unconfirmed`, `detected: null`.
- `not_observed`: every selected read/page succeeded, resource identity is usable,
  and no known signal (including weak signals) matched. Set `tool: not_observed`,
  `status: not_observed`, `detected: false`, and list the checked signals, kinds and
  namespaces. This describes that scope, not absence of external GitOps. An optional
  ConfigMap inventory not selected is a disclosed exclusion, not a failed selected
  read; a selected ConfigMap inventory that fails instead requires `unconfirmed`.

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
`ListCapabilities` check (`aws eks list-capabilities --cluster-name <cluster>`) can
observe that capability when authorized. State its result or access gap separately;
do not reinterpret it as a local controller, or expand permissions automatically.

Sources: [Argo resource tracking](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_tracking/)
and [Flux remote-cluster Kustomizations](https://fluxcd.io/flux/components/kustomize/kustomizations/#kubeconfig-remote-clusters).
Argo permits the destination namespace on cluster-scoped tracking IDs; see its
[version-matched self-reference check](https://github.com/argoproj/argo-cd/blob/v3.5.6/controller/state.go).
For metadata-only API identity, see [Kubernetes metadata-only fetches](https://kubernetes.io/docs/reference/using-api/api-concepts/#metadata-only-fetches).

**Bounded evidence:** classify every item in each successful input, then retain
at most **3 examples per `(tool, signal, strength, key)` across the final report**.
For standalone wildcard Argo annotations, use one key family for this limit while
retaining the actual annotation key in each example.
Combine detected tools from all reads; never infer tool presence only from the first
examples or cut input off with `head`. Examples are not resource/application counts.
Shorten displayed strings to 256 characters with `...[truncated]`, preserving full
label keys up to Kubernetes' 317-character limit. Classify original values, never
shortened text. Ignore an oversized custom key with a warning; keep standard signals.
Keep at most 5 warning examples and note sampling, shortening, failed reads or missing
pages in Coverage. This applies when the helper samples or the final report drops
additional examples. Output is bounded; API response size and parser memory are not.

**CLI collection:** inspect full responses for controller identity/images; the
extractor retains tracking metadata only. Use the installed Python 3 executable (`python3`, or `python` /
`py -3` on Windows). For example, from the skill directory:

```bash
# Controller inspection: full objects, independent reads.
kubectl get deployments -A -o json
kubectl get statefulsets -A -o json

# Tracking extraction after successful collection:
set -o pipefail
kubectl get deployments -A -o json | python3 scripts/gitops_signals.py -
# Only with target-linked user/configuration provenance (including label mode):
kubectl get deployments -A -o json | python3 scripts/gitops_signals.py - \
  --argocd-instance-label-key '<confirmed-tracking-key>'
```

Repeat for StatefulSets and DaemonSets, then only the explicitly selected optional
kinds. Do not list all ConfigMaps by default. When the user confirms the hub uses
standard label tracking, pass `--argocd-instance-label-key app.kubernetes.io/instance`.
Pass an unprefixed key only when user-supplied; record that provenance in Coverage. A failed/invalid input exits nonzero;
do not replace it with `{items: []}`. The helper returns `resources_scanned`,
`tools_with_tracking` from the complete input, bounded `evidence` examples,
`evidence_sampled`, and `warning_count` / warning examples. `tools_with_tracking`
excludes ambiguous signals; combine tools and cap examples as above. A corroborated
label may include one `corroboration: {key: ..., value: present}` record. The helper
uses only signal-table keys and never emits unrelated annotation/label values.
For an extra single-kind inventory confirmed cluster-scoped by API discovery,
pass `--cluster-scoped` (e.g. when reading Namespaces); do not infer scope from a
missing namespace field or the tracking annotation. The default three-kind path
is namespaced. Input bytes are decoded as UTF-8, including a possible BOM.
Record scan scope/errors separately; this helper does not assess API coverage,
scan for controllers, or decide overall absence. For MCP, perform the same metadata
reads and bounded examples. Recover original group/kind AND scope for
PartialObjectMetadata from request/discovery context, never from the annotation;
obtain normal objects/context or leave evidence unconfirmed when unavailable.

## Output Schema

This is the **single canonical schema** for the cicd module — it carries every CI/CD and
GitOps fact. The `cicd-recon` agent emits exactly this shape (plus the shared `cluster:` block
from `references/cluster-basics.md`). Use `null` where a fact was not detected; never omit a key.

```yaml
cicd:
  workspace:
    tools:
      count: int              # number of workspace CI/CD tools detected
      list: list              # names of tools found in workspace (e.g. ["github_actions", "jenkins"])
    github_actions:
      detected: bool
      workflows:
        count: int
        list: list            # paths to workflow files
      eks_related: bool       # any workflow references EKS/kubectl/helm/eks
    gitlab_ci:
      detected: bool
      config_path: string     # path to .gitlab-ci.yml, null if absent
    jenkins:
      detected: bool
      jenkinsfile_path: string   # path to Jenkinsfile, null if absent
      pipeline_libraries: list   # */vars/*.groovy paths (shared library steps), null/empty if none
    circleci:
      detected: bool
      config_path: string     # path to .circleci/config.yml, null if absent
    codepipeline:
      detected: bool
      buildspec_paths: list   # buildspec*.yml / pipeline*.json paths
    atlantis:
      detected: bool
      config_path: string     # path to atlantis.yaml, null if absent

  gitops:
    tool: string              # argocd | flux | multiple | unconfirmed | not_observed
    status: string            # detected | unconfirmed | not_observed; evidence in the checked scope, not active management
    detected: bool | null     # true for evidence; false only for not_observed; null for unconfirmed
    tools_detected: list      # all tools evidenced by local controllers or specific tracking
    evidence: list            # representative signal-table observations; sampling and provenance in Coverage
    # Every nested field below is LOCAL ONLY; unavailable hub facts remain null.
    argocd:
      detected: bool | null   # false only after complete local controller scans
      namespace: string | null
      version: string | null # observed local server/controller image, never a client version
      eks_managed: bool | null # observed local install; not a substitute for AWS ListCapabilities
      applications: int | null # locally observable Applications only
    flux:
      detected: bool | null   # local controller, not remote management
      namespace: string | null
      version: string | null # observed local source-controller image only
      git_repositories: int | null # locally observable sources only
      kustomizations: int | null # locally observable Kustomizations only

  other_tools:                # additional CI/CD platforms detected in-cluster
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

If Terraform is detected and `gitops.argocd.detected: true`:
```bash
# Check for gitops-bridge pattern
grep -r "gitops_bridge\|argocd_bootstrap" --include="*.tf" . 2>/dev/null | head -3
```

**Example output:**
```
./main.tf:module "gitops_bridge" {
./main.tf:  source = "gitops-bridge-dev/gitops-bridge/helm"
```

### App of Apps

App of Apps is an ArgoCD pattern where one Application manages other Applications.

If `gitops.argocd.detected: true`:
```bash
# Check for App of Apps pattern
kubectl get applications.argoproj.io -A -o json 2>/dev/null | \
  jq -r '.items[] | select(.spec.source.path | contains("apps") or contains("applications")) | .metadata.name' | head -5
```

**Example output:**
```
root-apps
platform-apps
```

### ApplicationSets

ApplicationSets generate multiple Applications from templates.

```bash
# Check for ApplicationSets
kubectl get applicationsets.argoproj.io -A 2>/dev/null | head -10
```

**Example output:**
```
NAMESPACE   NAME               AGE
argocd      cluster-addons     45d
argocd      workload-apps      30d
```

---

## Edge Cases

### Multiple CI/CD Tools

Common to have multiple tools:
- GitHub Actions for CI (build/test)
- ArgoCD for CD (deploy to cluster)

Report all detected tools, note integration pattern.

### CI/CD in Different Repo

Application repo may be separate from infra repo:
- Note scan is workspace-limited
- GitOps tools in cluster indicate deployment mechanism

### Atlantis (Terraform CI/CD)

**Why detect Atlantis:** Atlantis automates Terraform via pull request comments. If found, infrastructure changes flow through PR approvals.

```bash
# Check for Atlantis config
find . -name "atlantis.yaml" -type f 2>/dev/null
```

**Example output:**
```
./atlantis.yaml
```

Record under `cicd.workspace.atlantis`: `detected` and `config_path`.

### Tekton Pipelines

**Why detect Tekton:** Tekton is a Kubernetes-native CI/CD framework. Pipelines run as pods in the cluster itself.

```bash
# Check for Tekton
kubectl get pipelines.tekton.dev -A 2>/dev/null | head -5
```

**Example output:**
```
NAMESPACE   NAME              AGE
tekton      build-pipeline    60d
tekton      deploy-pipeline   60d
```

```bash
kubectl get pipelineruns.tekton.dev -A 2>/dev/null | head -5
```

Record under `cicd.other_tools.tekton`: `detected`, `namespace`, and counts of
`pipelines`/`pipelineruns`.

### Spinnaker

**Why detect Spinnaker:** Enterprise deployment platform with advanced deployment strategies (canary, blue-green). Often used in large organizations.

```bash
# Check for Spinnaker
kubectl get deploy -n spinnaker 2>/dev/null
```

**Example output:**
```
NAME                READY   UP-TO-DATE   AVAILABLE   AGE
spin-clouddriver    1/1     1            1           120d
spin-deck           1/1     1            1           120d
spin-gate           1/1     1            1           120d
spin-orca           1/1     1            1           120d
```

Record under `cicd.other_tools.spinnaker`: `detected` and `namespace`.
