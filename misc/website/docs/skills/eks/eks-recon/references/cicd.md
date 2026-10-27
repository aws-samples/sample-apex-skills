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

**MCP (check for Applications CRD):**
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
set -o pipefail
kubectl get applications.argoproj.io -A -o json | python3 -c 'import json,sys; items=json.load(sys.stdin)["items"]; print("count:", len(items)); print("examples:", [(x["metadata"].get("namespace"), x["metadata"]["name"]) for x in items[:3]])'
```

**Example output:**
```
count: 3
examples: [('argocd', 'platform-addons'), ('argocd', 'app-frontend'), ('argocd', 'app-backend')]
```

```bash
# Get ArgoCD version
kubectl get deploy -n argocd argocd-server -o jsonpath='{.spec.template.spec.containers[0].image}'
```

**Example output:**
```
quay.io/argoproj/argocd:v2.10.5
```

**EKS Managed ArgoCD (Capability):** Check if using EKS ArgoCD Capability (AWS-managed) vs self-managed:
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

**MCP (check for Kustomizations):**
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
set -o pipefail
kubectl get gitrepositories.source.toolkit.fluxcd.io -A -o json | python3 -c 'import json,sys; items=json.load(sys.stdin)["items"]; print("count:", len(items)); print("examples:", [(x["metadata"].get("namespace"), x["metadata"]["name"]) for x in items[:3]])'
```

**Example output:**
```
count: 2
examples: [('flux-system', 'flux-system'), ('flux-system', 'app-repo')]
```

```bash
# Check for Kustomizations
set -o pipefail
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A -o json | python3 -c 'import json,sys; items=json.load(sys.stdin)["items"]; print("count:", len(items)); print("examples:", [(x["metadata"].get("namespace"), x["metadata"]["name"]) for x in items[:3]])'
```

**Example output:**
```
count: 2
examples: [('flux-system', 'flux-system'), ('flux-system', 'apps')]
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

**Bounded evidence contract (both runtimes):** classify/count the complete successful
input before sampling. Aggregate `evidence_counts` by `(tool, signal, strength, key)`;
counts are signal occurrences in the recorded scan scope, not applications, releases
or unique managed resources. One object can contribute more than one signal.
Keep at most **3 example identities per group across the final report**, not 3 for
every query. Default displayed string fields are capped at **256 characters** with
`truncated_fields` recording original lengths; never reclassify a shortened example.
Grouping keys retain their full valid Kubernetes label key (up to 317 characters),
because shortening a key would lose aggregation identity. An oversized configured
custom key is invalid: warn once and ignore that key, retaining standard signals.
Record total warnings and at most 5 warning examples in Coverage. Examples are the
first observations, not a statistical sample. Sampling limits output, not the memory
needed to parse an input or the scope/size of an API response.

Combine counts only across proven disjoint kind/namespace/page inventories. A retry
or namespaced scan overlapping an all-namespace scan must not be summed: select one
successful encompassing snapshot, note the overlap and keep the other observation
separate if needed. Do not cut the input off with `head` before counting. A truncated
API/tool response is a coverage gap, not a complete zero inventory. Preserve positive
groups alongside gaps. If every tracking read failed, counts are `null`, not zero.
Only when the user explicitly requests full evidence, export it to a separate file
and reference that file; keep the main report and model-visible output bounded.

**CLI metadata collection:** use the maintained evidence extractor after each
successful read. Use the installed Python 3 executable (`python3`, or `python` /
`py -3` on Windows). For example, from the skill directory:

```bash
set -o pipefail
kubectl get deployments -A -o json | python3 scripts/gitops_signals.py -
# If the custom key was independently supplied/confirmed:
kubectl get deployments -A -o json | python3 scripts/gitops_signals.py - \
  --argocd-instance-label-key '<confirmed-custom-key>'
```

Repeat for the other readable kinds above. A failed/invalid input exits nonzero;
do not replace it with `{items: []}`. The helper returns `resources_scanned`,
`tools_with_tracking`, scoped `evidence_count` / `evidence_counts`, bounded `evidence`
examples, and `warning_count` / warning examples. Copy counts and combine examples
under the bounded contract above. `tools_with_tracking` excludes ambiguous signals.
Do not infer missing positive tools from the first examples: counts/tool presence
use the entire supplied inventory. `--full-evidence` is only for an explicitly
requested separate export, never the default model-visible report.
For an extra single-kind inventory confirmed cluster-scoped by API discovery,
pass `--cluster-scoped` (e.g. when reading Namespaces); do not infer scope from a
missing namespace field or the tracking annotation. The default seven-kind path
is namespaced. Input bytes are decoded as UTF-8, including a possible BOM.
Record scan scope/errors separately; this helper does not assess API coverage,
scan for controllers, or decide overall absence. For MCP, perform the same metadata
reads and bounded aggregation. Recover original group/kind AND scope for
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
    tool: string              # argocd | flux | multiple | unconfirmed
    status: string            # detected | unconfirmed (evidence, not verified active management)
    detected: bool | null     # true when evidence observed; null when unconfirmed, never false from missing CRDs
    tools_detected: list      # all tools evidenced by local controllers or specific tracking
    evidence_count: int | null # scoped signal occurrences; null when every tracking read failed
    evidence_counts: list | null # tool/signal/strength/key/count groups; null if no successful inventory
    evidence: list            # <=3 examples/group globally; optional truncated_fields stores original lengths
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
      version: string         # observed source-controller image tag only, never a local client version
      git_repositories: int   # count of GitRepository resources
      kustomizations: int     # count of Kustomization resources

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

### GitOps Bridge (Terraform + ArgoCD)

The GitOps Bridge pattern uses Terraform to bootstrap ArgoCD, then ArgoCD manages applications.

If both Terraform and ArgoCD detected:
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

If ArgoCD detected:
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
set -o pipefail
kubectl get applicationsets.argoproj.io -A -o json | python3 -c 'import json,sys; items=json.load(sys.stdin)["items"]; print("count:", len(items)); print("examples:", [(x["metadata"].get("namespace"), x["metadata"]["name"]) for x in items[:3]])'
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
