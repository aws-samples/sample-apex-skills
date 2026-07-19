---
title: "eks-recon"
description: "EKS cluster reconnaissance and environment discovery — reports the raw FACTS of a cluster and its environment. Detects compute (Karpenter, MNG, Auto Mode, Fargate, nodes/AMI), networking (VPC/CNI, subnets, load balancers, DNS), security facts (auth mode, IRSA/Pod Identity, RBAC, encryption), add-ons/Helm, observability, workloads (Deployments, StatefulSets, PDBs, HPAs), storage (CSI, StorageClasses, PVs, backup tooling), IaC (Terraform, CDK, eksctl), CI/CD (Actions, ArgoCD, Flux), and cluster insights. Triggers on \"what am I running\", \"tell me about my setup\", \"what version am I on\", cluster inventory, or documenting current state before an upgrade/migration/design. Reports facts only; it does not score, rate, plan, or recommend, and overlapping facts with other skills is fine. Route elsewhere for a judgment or artifact — readiness scoring/deprecated-API checks (eks-upgrade-check), GREEN/AMBER/RED audits (eks-operation-review), design docs/diagrams (eks-design)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/SKILL.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-recon/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/SKILL.md). Edit the source, not this page.
:::


# EKS Reconnaissance — DevOps Agent Port

## Overview

This skill discovers and documents the current state of an EKS cluster and its environment. It connects via AWS control-plane APIs and the Kubernetes API, runs detection across up to 11 modules, and produces a **facts-only** report: a markdown fact report (primary) plus a machine-readable YAML artifact for hand-off to other skills.

Recon answers the question: *"What is this cluster, right now?"* It **reports facts only** — it never scores, rates, plans, or recommends. Reporting a fact that also matters to another skill (upgrade, security, cost, design) is expected and fine; the dividing line is discovery-of-facts (here) vs. verdict/score/artifact (route elsewhere).

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. It proceeds through discovery and detection without pausing
> for user input. When the target cluster is ambiguous (multiple clusters, none named),
> it assesses **all** discovered clusters. When a non-recoverable error occurs (API
> permission failure, no clusters found), it logs the error in the report and terminates
> per the Step 0 decision table.

## Prerequisites

### Required IAM Permissions (Agent Space Role)

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/iam-policy.json) — attach it directly to your Agent Space execution role. It grants **read-only AWS control-plane access** (EKS/EC2/ELB/IAM/Logs `Describe`/`List`/`Get`). It intentionally does **not** grant `eks:AccessKubernetesApi` — Kubernetes-API authentication is handled by the access entry below, not by IAM.

| Service | Actions (read-only) | Purpose |
|---------|--------------------|---------|
| **EKS** | `ListClusters`, `DescribeCluster`, `ListNodegroups`, `DescribeNodegroup`, `ListAddons`, `DescribeAddon`, `DescribeAddonVersions`, `ListFargateProfiles`, `DescribeFargateProfile`, `ListAccessEntries`, `ListPodIdentityAssociations`, `DescribePodIdentityAssociation`, `ListInsights`, `DescribeInsight`, `ListIdentityProviderConfigs` | Cluster config, compute inventory, add-ons, access model, EKS insights |
| **EC2** | `DescribeInstances`, `DescribeVpcs`, `DescribeSubnets`, `DescribeSecurityGroups`, `DescribeNetworkInterfaces`, `DescribeLaunchTemplates` | Nodes, VPC/subnet topology, security groups, ENIs |
| **ELB** | `elasticloadbalancing:Describe*` | Load balancer inventory (ALB/NLB), target groups |
| **IAM** | `ListRoles`, `GetRole`, `ListOpenIDConnectProviders`, `ListPolicies`, `GetPolicyVersion` | IRSA/Pod Identity roles, OIDC providers |
| **CloudWatch Logs** | `logs:DescribeLogGroups` | Control-plane log group presence (observability facts) |

### Kubernetes API Access (via Agent Space Access Entry)

Kubernetes-API facts (nodes, CRDs, workloads, RBAC, StorageClasses, etc.) are read through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy at **cluster scope**. This is provisioned by `devops-agent/setup.sh` (or manually — see the project README "EKS Access Setup").

- The cluster's `authenticationMode` **must include `API`** (i.e. `API` or `API_AND_CONFIG_MAP`). A `CONFIG_MAP`-only cluster cannot be reached via the access entry.
- The access entry (not an IAM action) provides the K8s-API **authentication**; the `AmazonAIOpsAssistantPolicy` provides the **authorization** (RBAC).
- **What `AmazonAIOpsAssistantPolicy` actually authorizes (read-only get/list):** built-in API groups only — core (`pods`, `services`, `nodes`, `namespaces`, `events`, `persistentvolumes`, `persistentvolumeclaims`, `configmaps`), `apps` (deployments/replicasets/statefulsets/daemonsets), `batch` (jobs/cronjobs), `events.k8s.io`, `networking.k8s.io` (ingresses/ingressclasses), `storage.k8s.io` (storageclasses), and `metrics.k8s.io`. **It grants NO CustomResourceDefinition groups** (and not `apiextensions.k8s.io`).
- **Consequence for CRD-based facts:** the managed policy alone does **not** authorize reading Karpenter (`karpenter.sh`, `karpenter.k8s.aws`), Auto Mode `NodeClass` (`eks.amazonaws.com`), `TargetGroupBinding` (`elbv2.k8s.aws`/`eks.amazonaws.com`), `VolumeSnapshotClass` (`snapshot.storage.k8s.io`), `VerticalPodAutoscaler` (`autoscaling.k8s.io`), Kyverno/Gatekeeper, Calico/Cilium, service-mesh, ArgoCD/Flux, Crossplane/ACK, or Velero CRDs. Under a plain `AmazonAIOpsAssistantPolicy`-only association those reads return `403 Forbidden`. To capture CRD-based facts, bind the Agent Space role to a **supplementary read-only ClusterRole** granting `get`/`list` on the relevant CRD groups (or associate a broader access policy). Absent that, the CRD-dependent sub-facts are reported as `unconfirmed` per the hedge below — never as `false`/`count: 0`.

> **Availability hedge.** When the access entry is absent (or `authenticationMode` excludes `API`), the skill **degrades gracefully to AWS-control-plane-only facts** — it still reports everything reachable via the EKS/EC2/ELB/IAM APIs. Each K8s-API-dependent module or sub-fact that cannot be read — whether because the access entry is missing, `authenticationMode` excludes `API`, or the RBAC (see above) does not authorize that resource (e.g. a CRD group) — is recorded as `unavailable` / `unconfirmed` in the report's Coverage section, **never** as `false` / `count: 0`.

## When to Use

**Activate when the goal involves:**
- Discovering or documenting an EKS cluster's current state — "what am I running?", "tell me about my setup"
- Inventory before an upgrade, migration, or architecture change
- Targeted current-state questions — "what version am I on?", "am I using Karpenter?"
- Supplying raw cluster facts as input to another workflow

**Out of scope — route elsewhere (these produce judgments/artifacts, not facts):**
- **Upgrade readiness scoring / deprecated-API blocking** → `eks-upgrade-check`. Recon discovers *what version you're on*; it does not assess whether you are *ready* to move.
- **Operational audits with GREEN/AMBER/RED maturity ratings** → `eks-operation-review`. Recon inventories what exists; it does not rate maturity.
- **Architecture design documents or Mermaid diagrams** → `eks-design`. Recon discovers current state; it does not produce design artifacts.
- Creating or modifying cluster resources (this skill is strictly read-only).

---

## Reconnaissance Workflow

**Error output format** (used by the Step 0 hard-stops):

```
## Recon Error — <one-line reason>
**Condition:** <which check failed>
**What was found:** <observed state>
**Recommendation:** <remediation guidance for next run>
```

### Step 0: Pre-flight — Cluster Discovery and Validation

**Action 1 — Discover clusters.** Use the EKS ListClusters API to discover available clusters in the target region.

| Condition | Action |
|-----------|--------|
| API call fails (auth/permission error) | **Abort with error** — log "Cannot access EKS. The agent role requires `eks:ListClusters` for the configured region." and terminate. |
| Zero clusters returned | **Abort with error** — log "No EKS clusters found in this region." and terminate. |
| Exactly one cluster found, none named in request | **Proceed** — state which cluster was auto-selected. |
| Multiple clusters found, one named in request | **Proceed** — use the named cluster. |
| Multiple clusters found, none named in request | **Proceed** — recon **all** discovered clusters. Note in the report that no specific cluster was targeted, so all clusters in the region are included. |

**Action 2 — Describe the selected cluster.** Use DescribeCluster. Extract name, Kubernetes version, platform version, region, status, account ID, `authenticationMode`. This populates the shared `cluster:` and `cluster_detail:` blocks (`references/cluster-basics.md`).

| Cluster Status | Action |
|----------------|--------|
| `ACTIVE` | **Proceed** |
| `CREATING` / `UPDATING` / `DELETING` | **Skip cluster** — log "Cluster `<name>` is in `<status>` state; skipping." If it is the only cluster, terminate with error report. |
| `FAILED` | **Skip cluster** — log "Cluster `<name>` is in FAILED state." If it is the only cluster, terminate with error report. |

**Action 3 — Probe Kubernetes API reachability.** Attempt one lightweight K8s-API read (e.g. list nodes). If it fails (access entry absent, `authenticationMode` excludes `API`, or 401/403), **do not abort** — set a `k8s_api_available: false` flag, continue with AWS-control-plane-only modules, and record every K8s-dependent module/sub-fact as `unavailable`/`unconfirmed` in Coverage.

**Action 4 — Load `references/cluster-basics.md` first**, then proceed to module selection. `cluster-basics` is **always loaded first by every module** — it provides the shared cluster context all other modules depend on.

### Step 1: Select and Run Modules

Determine which modules to run from user intent using the routing table below. For a **targeted query**, load only the matching reference(s). For **full recon**, load all 11 references. Before running a module, **read its reference file** — the references carry detection order, edge cases, and the canonical output schema; skipping them produces shallow results.

Each reference describes detection **declaratively** as capability blocks (AWS API calls, and "**Via Kubernetes API**" blocks for K8s resources). There is no Agent tool and no subagents in this environment — module isolation is achieved by loading one reference at a time, not by spawning subagents.

### Step 2: Generate the Report

Produce both artifacts (see Report Output below). The markdown fact report is the primary deliverable; the YAML is a machine artifact for hand-off.

---

## How to Use the References

`references/cluster-basics.md` is **always loaded first**. Load additional references only for the modules the request needs.

| Intent / when to use | Reference file |
|----------------------|----------------|
| Always first — name, region, version, platform version, endpoint, support type, zonal shift, encryption config, health | [cluster-basics.md](references/cluster-basics) |
| Karpenter, nodes, scaling, Auto Mode, node groups, Fargate, self-managed | [compute.md](references/compute) |
| VPC, ingress, CNI, service mesh, load balancer, connectivity | [networking.md](references/networking) |
| IAM, IRSA, Pod Identity, RBAC, policies, encryption, secrets, webhooks | [security.md](references/security) |
| EKS-managed add-ons, Helm releases, plugins, "what's installed?" | [addons.md](references/addons) |
| Logging, metrics, monitoring, Container Insights, Prometheus | [observability.md](references/observability) |
| Deployments, pods, services, ingresses, "what's running?" | [workloads.md](references/workloads) |
| PVCs, EBS, EFS, StorageClasses, CSI drivers, volumes, snapshots, backup tooling | [storage.md](references/storage) |
| Terraform, CloudFormation, CDK, eksctl, Pulumi, Crossplane, "how is it managed?" | [iac.md](references/iac) |
| GitHub Actions, GitLab CI, Jenkins, ArgoCD, Flux, GitOps, pipelines | [cicd.md](references/cicd) |
| EKS-reported upgrade-readiness & configuration insights (raw findings) | [cluster-insights.md](references/cluster-insights) |

For **full recon**, load all rows. For a **targeted query** (e.g. "am I using Karpenter?"), load only `cluster-basics.md` + the matching row (`compute.md`).

---

## Report Output

Produce **two** artifacts. The **markdown fact report is the primary deliverable** (rendered inline to the user); the YAML is a machine artifact for optional hand-off to other skills. The agent generates both directly — no external conversion tools or scripts.

> **Facts only.** Both artifacts report what the cluster *is*. Never emit a verdict, score, readiness rating, or recommendation. A "Notable facts" line states an observation ("2 subnets have < 16 free IPs"); it never says "you should" or "this is a risk".

### Markdown fact report (primary)

- **Filename:** `EKS-Recon-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

Render this structure, including **only modules that actually ran**:

```markdown
# EKS Recon — <cluster> (<region>)
_generated <timestamp> · source: AWS API + K8s API · modules: N/N_

## Cluster summary
| Fact | Value |
|------|-------|
| version / platform | 1.31 / eks.5 |
| support type | STANDARD |
| status / created | ACTIVE / 2024-09-10 |
| authentication mode | API_AND_CONFIG_MAP |
| compute strategy | Karpenter + 1 MNG |
| IaC | Terraform (high confidence) |
| CI/CD | GitHub Actions + ArgoCD |

## Per-module facts
### Compute
<small fact table per module — one H3 per RUN module>
### Networking
...

## Notable facts
<flat bullets: co-occurring or absent facts, stated neutrally, ZERO verdicts>
- authentication_mode = API_AND_CONFIG_MAP; aws-auth ConfigMap present
- compute.strategy = Karpenter; security.iam_for_pods.irsa.detected = false
- 2 of 4 cluster subnets report < 16 available IPs

## Coverage
<modules that could not run + reason, AND sub-facts that ran but could not be confirmed>
- storage: unavailable (reason: K8s API access entry absent — AWS-API-only mode)
- addons.helm_releases: unconfirmed (reason: Helm release Secrets not readable) — reported as `unconfirmed`, not `count: 0`
```

### Machine YAML artifact

- **Filename:** `EKS-Recon-{cluster}-{YYYY-MM-DD}-{HHMM}.yaml`

Assemble one top-level key per module, each emitted **verbatim in the canonical shape defined by that module's `references/<module>.md` "## Output Schema"**, plus the shared `cluster:` and `cluster_detail:` blocks (from `references/cluster-basics.md`). Unavailable modules become `<module>: {unavailable: true, reason: "<short reason>"}`.

> **The reference Output Schemas are the single source of truth for the YAML shape** — do not hand-copy a schema. The fragment below shows only the envelope; the authoritative per-module shape lives in each reference.

```yaml
# EKS Reconnaissance Report — illustrative envelope only.
# Canonical shape per module = references/<module>.md "## Output Schema".
cluster:              # shape: references/cluster-basics.md "## Shared Cluster Block"
  name: my-cluster
  region: us-west-2
  version: "1.31"
  platform_version: eks.5
  status: ACTIVE
cluster_detail:       # shape: references/cluster-basics.md "## Cluster Detail (full recon)"
  upgrade_policy: {support_type: STANDARD}
compute:              # shape: references/compute.md "## Output Schema"
  strategy: Karpenter
networking: { ... }   # shape: references/networking.md
storage:
  unavailable: true
  reason: "K8s API access entry absent — AWS-API-only mode"
```

---

## Facts-Only Guardrails

1. **Report facts, never judgments.** No scores, ratings, readiness verdicts, risk labels, or recommendations. "Notable facts" states observations; it never says "you should" or "this is a risk".
2. **Do NOT hardcode or guess cluster names.** Always discover clusters via ListClusters first (Step 0).
3. **Do NOT retry a failed API call more than once.** If it fails twice, record the gap in Coverage and continue.
4. **Always read the relevant reference before running a module.** References carry detection order, edge cases, and the canonical output schema.
5. **Distinguish absence from unconfirmed.** A fact that could not be checked is `unconfirmed`/`unavailable` (with a reason), never `count: 0` or `false`.
6. **Never omit a schema key.** Use `null` where a fact was not detected — preserve the full canonical shape from each reference.

---

*This skill is provided as sample code for educational and demonstration purposes only. Findings are point-in-time facts and should be validated before acting on them. See the project's README and LICENSE for full terms.*
