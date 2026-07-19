---
name: eks-al2-to-al2023
description: Amazon Linux 2 → AL2023 EKS node migration readiness checker — assesses the
  migration-relevant facts and risks of moving worker nodes off the deprecated AL2
  EKS-optimized AMI, then emits a guided, human-executed migration runbook with a canary
  node group. Detects AL2 vs AL2023 nodes/node groups, cgroup v2 workload risk (pre-8u372
  JDK 8, old .NET), IMDSv2 hop-limit-1 pod-metadata impact, bootstrap.sh → nodeadm/NodeConfig
  userData rewrite for custom launch templates and self-managed nodes, VPC CNI below 1.16.2,
  and DaemonSet/kernel-module/log-shipper agents. Triggers on "migrate to AL2023", "am I
  still on Amazon Linux 2", "AL2 end of support", "move nodes off AL2", "is my cluster
  AL2023 ready". Read-only — it reports facts and next steps and emits a runbook; it never
  modifies nodes or runs the migration. Route elsewhere for full upgrade-readiness scoring
  across all breaking changes (eks-upgrade-check), or raw cluster inventory (eks-recon).
---

# EKS AL2 → AL2023 Node Migration — DevOps Agent Port

## Overview

This skill assesses how ready an EKS cluster's worker nodes are to migrate from the
**Amazon Linux 2 (AL2)** EKS-optimized AMI — which AWS stopped publishing new EKS releases
for **on November 26, 2025** (as of 2026-07-19; source: [EKS AL2 deprecation FAQ](https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html)) — to **Amazon Linux 2023 (AL2023)**. It connects via AWS control-plane APIs and the Kubernetes API, detects which nodes are still on AL2, evaluates the known migration-breaking behaviors, and produces two artifacts: a **migration-readiness fact report** and a **guided, human-executed migration runbook** built around a canary node group.

It answers the question: *"What breaks if I move these nodes to AL2023, and how do I do it safely?"* It is **read-only** — it never cordons, drains, patches, or replaces a node, and it never creates or edits a node group. The runbook is a set of steps for a human (or a separate change-management pipeline) to execute; this skill only assesses and instructs.

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. It proceeds through discovery and detection without pausing
> for user input. When the target cluster is ambiguous (multiple clusters, none named),
> it assesses **all** discovered clusters. When a non-recoverable error occurs (API
> permission failure, no clusters found), it logs the error in the report and terminates
> per the Step 0 decision table.

## Prerequisites

### Required IAM Permissions (Agent Space Role)

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](references/iam-policy.json) — attach it directly to your Agent Space execution role. It grants **read-only AWS control-plane access** (EKS/EC2 `Describe`/`List`). It intentionally does **not** grant `eks:AccessKubernetesApi` — Kubernetes-API authentication is handled by the access entry below, not by IAM.

| Service | Actions (read-only) | Purpose |
|---------|--------------------|---------|
| **EKS** | `ListClusters`, `DescribeCluster`, `ListNodegroups`, `DescribeNodegroup`, `ListAddons`, `DescribeAddon`, `DescribeAddonVersions` | Cluster version, node-group AMI type / release version, VPC CNI add-on version |
| **EC2** | `DescribeInstances`, `DescribeLaunchTemplates`, `DescribeLaunchTemplateVersions`, `DescribeImages` | Node AMI IDs, launch-template userData + IMDS hop-limit settings, AMI name → AL2/AL2023 mapping |

### Kubernetes API Access (via Agent Space Access Entry)

Node-level facts (per-node `osImage`, `kernelVersion`, container runtime, DaemonSets, workload images) are read through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy at **cluster scope**. This is provisioned by `devops-agent/setup.sh` (or manually — see the project README "EKS Access Setup").

- The cluster's `authenticationMode` **must include `API`** (i.e. `API` or `API_AND_CONFIG_MAP`). A `CONFIG_MAP`-only cluster cannot be reached via the access entry.
- The access entry (not an IAM action) provides the K8s-API **authentication**; the `AmazonAIOpsAssistantPolicy` provides the **authorization** (RBAC).
- **What `AmazonAIOpsAssistantPolicy` actually authorizes (read-only get/list):** built-in API groups only — core (`nodes`, `pods`, `namespaces`, `configmaps`), `apps` (deployments/daemonsets/statefulsets), `batch`, `events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. **It grants NO CustomResourceDefinition groups** (and not `apiextensions.k8s.io`).
- **Consequence for CRD-based facts:** Karpenter `EC2NodeClass`/`NodePool` (`karpenter.k8s.aws`, `karpenter.sh`) and Auto Mode `NodeClass` (`eks.amazonaws.com`) drive AMI selection for those compute types, but under a plain `AmazonAIOpsAssistantPolicy`-only association those CRD reads return `403 Forbidden`. To read the AMI family a Karpenter `EC2NodeClass` requests, bind the Agent Space role to a **supplementary read-only ClusterRole** granting `get`/`list` on `karpenter.k8s.aws`/`karpenter.sh`/`eks.amazonaws.com` (or associate a broader access policy). Absent that, Karpenter/Auto-Mode AMI facts are reported as `unconfirmed` — never as "AL2" or "AL2023" guessed, and never as `false`.

> **Availability hedge.** When the access entry is absent (or `authenticationMode` excludes `API`), the skill **degrades gracefully to AWS-control-plane-only facts** — it still reports node-group AMI type (`eks:DescribeNodegroup`), launch-template userData/IMDS settings, and the VPC CNI add-on version, all of which are readable via the AWS API alone. Each K8s-API-dependent fact that cannot be read (per-node `osImage`/`kernelVersion`, workload images for cgroup/IMDS risk, DaemonSets) is recorded as `unavailable`/`unconfirmed` in the report's Coverage section, **never** as a false negative.

## When to Use

**Activate when the goal involves:**
- Checking whether a cluster's nodes are still on Amazon Linux 2 and what a move to AL2023 entails — "am I still on AL2?", "migrate to AL2023", "AL2 end of support"
- Assessing the migration-specific risks (cgroup v2, IMDSv2 hop limit, nodeadm/NodeConfig, VPC CNI floor) before changing an AMI type
- Producing a guided migration runbook with a canary/blue-green validation approach

**Out of scope — route elsewhere:**
- **Full upgrade-readiness scoring across ALL breaking changes** (deprecated APIs, add-on compatibility matrix, version skew, a 0–100 score) → `eks-upgrade-check`. This skill is scoped to the AL2→AL2023 *node OS* migration; it does not score the whole upgrade.
- **Raw cluster inventory / "what am I running"** → `eks-recon`. Recon reports AMI facts without the migration risk analysis or runbook.
- Actually performing the migration — creating node groups, cordoning, draining, or replacing nodes (this skill is strictly read-only).

> **Overlap note (for maintainers).** The upstream `skills/eks-upgrade-check` skill carries AL2→AL2023 material as one module of a broader readiness check, and an effort is underway to improve it. This standalone skill goes deeper on the node-OS migration specifically. If the improved `eks-upgrade-check` subsumes this depth, these two may later merge — see `references/porting-notes.md`.

---

## Migration Assessment Workflow

**Error output format** (used by the Step 0 hard-stops):

```
## AL2023 Migration Check Error — <one-line reason>
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
| Multiple clusters found, none named in request | **Proceed** — assess **all** discovered clusters. Note in the report that no specific cluster was targeted. |

**Action 2 — Describe the selected cluster.** Use DescribeCluster. Extract name, Kubernetes version, region, status, `authenticationMode`. Record the cluster's Kubernetes version — it drives the AL2-availability facts in `references/migration-risks.md` (K8s 1.32 was the last EKS version to ship AL2 AMIs; 1.33+ ships AL2023/Bottlerocket only, as of 2026-07-19).

| Cluster Status | Action |
|----------------|--------|
| `ACTIVE` | **Proceed** |
| `CREATING` / `UPDATING` / `DELETING` | **Skip cluster** — log the state. If it is the only cluster, terminate with error report. |
| `FAILED` | **Skip cluster** — log FAILED state. If it is the only cluster, terminate with error report. |

**Action 3 — Probe Kubernetes API reachability.** Attempt one lightweight K8s-API read (list nodes). If it fails (access entry absent, `authenticationMode` excludes `API`, or 401/403), **do not abort** — set `k8s_api_available: false`, continue with AWS-control-plane-only detection, and record every K8s-dependent fact as `unavailable`/`unconfirmed` in Coverage.

### Step 1: Detect AL2 Footprint

Load `references/node-inventory.md`. Identify which nodes and node groups are on AL2 vs AL2023, by compute type (managed node groups, self-managed, Karpenter, Auto Mode, Fargate — Fargate has no AL2 concern). This produces the migration scope: the set of node groups that need action.

### Step 2: Evaluate Migration Risks

Load `references/migration-risks.md`. For the AL2 footprint from Step 1, assess each known migration-breaking behavior against what is actually running: cgroup v2 workload risk, IMDSv2 hop-limit-1, bootstrap.sh → nodeadm/NodeConfig rewrite, VPC CNI version floor, and DaemonSet/kernel-module/log-shipper agents. Each risk is reported with its status (applies / does-not-apply / unconfirmed) and the evidence behind it.

### Step 3: Emit the Guided Runbook

Load `references/runbook.md`. Assemble a migration runbook tailored to the detected compute types, centered on a **canary node group** validation approach. The runbook is instructions for a human to execute — this skill does not run it.

---

## How to Use the References

Load `references/node-inventory.md` first (it establishes the AL2 footprint every later step scopes to), then the others as the request needs.

| Intent / when to use | Reference file |
|----------------------|----------------|
| Always first — detect AL2 vs AL2023 nodes, node groups, compute types, launch templates | [node-inventory.md](references/node-inventory.md) |
| Assess the migration-breaking behaviors (cgroup v2, IMDSv2, nodeadm, VPC CNI, agents) | [migration-risks.md](references/migration-risks.md) |
| Build the guided, human-executed migration runbook (canary node group, blue/green, validation, rollback) | [runbook.md](references/runbook.md) |

For a **targeted question** ("am I still on AL2?"), load only `node-inventory.md`. For a **full migration assessment**, load all three in order.

Each reference describes detection **declaratively** as capability blocks (AWS API calls, and "**Via Kubernetes API**" blocks for K8s resources). There is no Agent tool and no subagents in this environment — analysis isolation is achieved by loading one reference at a time, not by spawning subagents.

---

## Report Output

Produce **two** artifacts. The agent generates both directly — no external conversion tools or scripts.

### 1. Migration-readiness fact report (primary)

- **Filename:** `EKS-AL2023-Migration-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

```markdown
# AL2 → AL2023 Migration Check — <cluster> (<region>)
_generated <timestamp> · source: AWS API + K8s API · K8s version: <version>_

## AL2 footprint
| Compute | On AL2 | On AL2023 | Unconfirmed |
|---------|--------|-----------|-------------|
| Managed node groups | 2 (ng-a, ng-b) | 0 | 0 |
| Self-managed | 0 | 0 | 0 |
| Karpenter | — | — | 1 EC2NodeClass (CRD read blocked) |

## Migration risks
| Risk | Status | Evidence |
|------|--------|----------|
| cgroup v2 (JDK 8 < 8u372 / old .NET) | applies | 1 workload image tagged openjdk:8u312 |
| IMDSv2 hop limit → 1 | applies | ng-a has no launch template (default hop limit 1) |
| bootstrap.sh → nodeadm/NodeConfig | applies | ng-b uses a custom launch template with bootstrap.sh userData |
| VPC CNI < 1.16.2 | applies | add-on version v1.15.4-eksbuild.1 (floor is 1.16.2) |
| DaemonSet / kernel-module / log-shipper agents | review | 3 DaemonSets mount host paths — listed below |

## Notable facts
<flat neutral bullets>

## Coverage
<facts that could not be confirmed + reason — never a false negative>
```

### 2. Guided migration runbook

- **Filename:** `EKS-AL2023-Migration-Runbook-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

A step-by-step runbook a human executes, assembled per `references/runbook.md` and tailored to the detected compute types (managed node group blue/green vs custom-AMI in-place vs Karpenter drift). Every command in it is presented as an instruction for the operator, prefixed with a clear note that **this skill does not run it**.

---

## Read-Only Guardrails

1. **Assess and instruct — never act.** This skill reads facts and emits a runbook. It never creates/edits node groups, cordons, drains, patches, or replaces nodes. Runbook commands are for a human to run.
2. **Cite the source and date for every version/timeline claim.** AL2 end-of-support dates, VPC CNI floors, and cgroup facts carry a source URL and "as of <date>" — see `references/migration-risks.md`. Do not assert a version or date from memory.
3. **Do NOT hardcode or guess cluster names.** Discover via ListClusters first (Step 0).
4. **Distinguish absence from unconfirmed.** A node OS or workload image that could not be read is `unconfirmed` (with a reason), never assumed AL2023-ready and never a false negative. Karpenter/Auto-Mode AMI facts behind blocked CRD reads are `unconfirmed`.
5. **Do NOT retry a failed API call more than once.** If it fails twice, record the gap in Coverage and continue.
6. **The runbook is guidance, not a guarantee.** Node migration replaces nodes and reschedules pods; the human validates on a canary before rolling fleet-wide.

---

*This skill is provided as sample code for educational and demonstration purposes only. Findings are point-in-time facts and should be validated before acting on them. Migration steps must be reviewed and tested in a non-production environment first. See the project's README and LICENSE for full terms.*
