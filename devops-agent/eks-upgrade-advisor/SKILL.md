---
name: eks-upgrade-advisor
description: EKS Kubernetes-version upgrade execution advisor — turns a GO decision into a
  safe, ordered, phased plan (prepare → execute → validate/debug) and emits an operator
  runbook. Sequences the whole upgrade — Karpenter 0.x→1.x, control plane, add-ons, then node
  groups — with entry-gate hard-stops per phase, a backup + readiness gate before anything is
  touched, mode selection (in-place rolling by default, or blue-green cutover as a mode), and a
  symptom-based debug table for a stalled upgrade. Triggers on "how do I upgrade my EKS
  cluster", "plan my EKS upgrade", "upgrade runbook", "blue-green EKS upgrade", "my upgrade is
  stuck", "sequence an EKS upgrade". Read-only — it assesses and instructs via a runbook; it
  never upgrades, drains, or modifies anything. Route elsewhere for the readiness score
  (eks-upgrade-check), backup posture (eks-backup), AL2→AL2023 node-OS mechanics
  (eks-al2-to-al2023), or raw inventory (eks-recon).
---

# EKS Upgrade Advisor — DevOps Agent Port

## Overview

This skill is the **execution advisor** for an Amazon EKS Kubernetes-version upgrade. It assumes
the *readiness question* has already been answered by `eks-upgrade-check` (the 0–100 score and
the blocking-finding list) and turns a **GO** into a **safe, ordered, phased plan** the operator
executes: what to touch, in what order, where the hard-stops are, which **mode** to use, and how
to diagnose a stalled upgrade. It connects via read-only AWS control-plane APIs and the
Kubernetes API, and produces two artifacts: a **phased upgrade plan** (with per-phase gates) and
a **guided, human-executed runbook**.

It answers the question: *"I'm ready to upgrade — now walk me through actually doing it safely,
phase by phase, and help me debug it if it stalls."* It is **read-only**: it never triggers a
cluster update, updates an add-on, cordons or drains a node, or cuts over traffic. The runbook is
a set of steps for a human (or a change-management pipeline) to execute.

Its unique lane is the **cross-domain order-of-operations** — the one place that sequences
control plane + add-ons + nodes into a single gated runbook. It does **not** re-score readiness,
re-inventory the cluster, assess backup tooling, or re-explain node-OS migration mechanics; those
belong to the sibling skills (see the routing in *When to Use*).

> **A version upgrade is (mostly) one-way.** EKS supports a Kubernetes **version rollback of one
> minor version, within 7 days** of the upgrade — and that reverts the *control-plane version
> only* (as of 2026-07-20; source: [EKS version rollback](https://aws.amazon.com/blogs/aws/upgrade-amazon-eks-clusters-with-confidence-using-kubernetes-version-rollbacks/)).
> Outside that window, for a multi-minor jump, or for data-plane / add-on / data changes, there
> is **no undo**. This is why the **backup gate** and the **mode + rollback decision** live in
> *Prepare*, before anything is touched. A version rollback is a narrow safety net; it is **not**
> a backup, and a backup is **not** a version undo. See `references/upgrade-model.md`.

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. It proceeds through assessment and planning without pausing
> for user input. When the target cluster is ambiguous (multiple clusters, none named),
> it advises on **all** discovered clusters. When a non-recoverable error occurs (API
> permission failure, no clusters found), it logs the error in the report and terminates
> per the Step 0 decision table.

## Prerequisites

### Required IAM Permissions (Agent Space Role)

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](references/iam-policy.json) — attach it directly to your Agent Space execution role. It grants **read-only AWS control-plane access** (EKS/EC2/Auto Scaling `Describe`/`List`). It intentionally does **not** grant `eks:AccessKubernetesApi` — Kubernetes-API authentication is handled by the access entry below, not by IAM.

| Service | Actions (read-only) | Purpose |
|---------|--------------------|---------|
| **EKS** | `ListClusters`, `DescribeCluster`, `ListNodegroups`, `DescribeNodegroup`, `ListAddons`, `DescribeAddon`, `DescribeAddonVersions`, `ListUpdates`, `DescribeUpdate`, `ListInsights`, `DescribeInsight`, `ListFargateProfiles`, `DescribeFargateProfile`, `ListAccessEntries`, `ListAssociatedAccessPolicies` | Cluster version/status, node-group versions, add-on current + target-compatible versions, in-progress/failed update status, EKS upgrade insights, Fargate profiles (compute-model detection on the AWS-only path), the access model |
| **EC2** | `DescribeInstances`, `DescribeSubnets`, `DescribeLaunchTemplates`, `DescribeLaunchTemplateVersions`, `DescribeImages` | Node inventory, **subnet free-IP capacity** (surge/blue-green gate), launch-template userData/AMI facts |
| **Auto Scaling** | `DescribeAutoScalingGroups` | Node-group ASG capacity headroom for surge / parallel-fleet sizing |
| **IAM / KMS** | `iam:GetRole`, `kms:DescribeKey`, `kms:GetKeyPolicy` | Control-plane upgrade prerequisites (Phase 1 Gate 7): cluster IAM role present, and — if envelope encryption is on — the role can use the KMS key. Missing either **fails the upgrade** |

### Kubernetes API Access (via Agent Space Access Entry)

Kubernetes-API facts (node versions/skew, workload health, PDBs, add-on pods, drain-safety) are read through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy at **cluster scope**. This is provisioned by `devops-agent/setup.sh` (or manually — see the project README "EKS Access Setup").

- The cluster's `authenticationMode` **must include `API`** (i.e. `API` or `API_AND_CONFIG_MAP`). A `CONFIG_MAP`-only cluster cannot be reached via the access entry.
- The access entry (not an IAM action) provides the K8s-API **authentication**; the `AmazonAIOpsAssistantPolicy` provides the **authorization** (RBAC).
- **What `AmazonAIOpsAssistantPolicy` actually authorizes (read-only get/list):** built-in API groups only — core (`pods`, `services`, `nodes`, `namespaces`, `events`, `configmaps`, `persistentvolumes`, `persistentvolumeclaims`), `apps` (deployments/replicasets/statefulsets/daemonsets), `batch` (jobs/cronjobs), `events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. **It grants NO CustomResourceDefinition groups** (and not `apiextensions.k8s.io`).
- **Consequence for CRD-based and `policy`-group facts:** two gate inputs this skill wants are **not** authorized by the managed policy alone. **PodDisruptionBudgets** live on the `policy` API group, and **Karpenter** config lives on `karpenter.sh` / `karpenter.k8s.aws` — under a plain `AmazonAIOpsAssistantPolicy`-only association these reads return `403 Forbidden`. The drain-safety gate (Phase 1 Gate 5) and the Karpenter-state gate (Gate 6) therefore report `unconfirmed` in that case — **never** "no blocking PDBs" or a guessed Karpenter version. To confirm them, bind the Agent Space role to a **supplementary read-only ClusterRole** granting `get`/`list` on `poddisruptionbudgets.policy`, `karpenter.sh`, `karpenter.k8s.aws`, and (if used) `eks.amazonaws.com` — or associate a broader access policy. See `references/porting-notes.md` for the exact ClusterRole. An `unconfirmed` safety gate is treated as **not-GREEN**, never silently passed.

> **Availability hedge.** When the access entry is absent (or `authenticationMode` excludes `API`), the skill **degrades gracefully to AWS-control-plane-only facts** — it still advises from cluster version/status, node-group versions, add-on versions, update status, subnet capacity, and EKS insights (all readable via the AWS API alone). Each K8s-API-dependent gate input that cannot be read (node skew, workload health, PDBs) is recorded as `unavailable`/`unconfirmed` in the report's Coverage section, **never** as a false negative — and a phase is never green-lit on an upgrade the skill could not inspect.

## When to Use

**Activate when the goal involves:**
- Planning and sequencing an EKS Kubernetes-version upgrade — "how do I upgrade my cluster?", "plan my EKS upgrade", "give me an upgrade runbook"
- Choosing an upgrade approach — in-place rolling vs **blue-green cutover** — and getting the phased, gated plan for it
- Debugging a stalled or failed upgrade — "my upgrade is stuck", "nodes won't drain", "add-on degraded after upgrade"

**Out of scope — route elsewhere:**
- **Upgrade readiness scoring / the 0–100 score / deprecated-API blocking** → `eks-upgrade-check`. This skill *consumes* that verdict as its entry gate; it does not produce it.
- **Backup / recovery posture and the backup runbook** → `eks-backup`. The advisor *routes to it* for the Phase 1 backup gate; it does not assess backup tooling.
- **AL2 → AL2023 node-OS migration mechanics** (nodeadm/NodeConfig, cgroup v2, IMDS hop limit, VPC CNI floor) → `eks-al2-to-al2023`. The advisor flags the version triggers and routes there; it does not re-explain node-OS internals.
- **Raw cluster inventory / "what am I running"** → `eks-recon`.
- **Full post-upgrade operational health / maturity audit** (GREEN/AMBER/RED) → `eks-operation-review` *(when built out — currently a stub)*. The advisor validates that the *upgrade* succeeded; it does not rate operational maturity.
- Actually performing the upgrade — triggering updates, updating add-ons, draining nodes, cutting over traffic (this skill is strictly read-only).

---

## Upgrade Advisory Workflow

**Error output format** (used by the Step 0 hard-stops):

```
## Upgrade Advisory Error — <one-line reason>
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
| Multiple clusters found, none named in request | **Proceed** — advise on **all** discovered clusters. Note in the report that no specific cluster was targeted. |

**Action 2 — Describe the selected cluster.** Use DescribeCluster. Extract name, Kubernetes version, platform version, region, status, `authenticationMode`. The current Kubernetes version + the requested target drive the version-hop gate (`references/phase-1-prepare.md` → Gate 3).

| Cluster Status | Action |
|----------------|--------|
| `ACTIVE` | **Proceed** |
| `UPDATING` | **Enter debug mode** — an upgrade is already in flight (possibly the "my upgrade is stuck" trigger). Do **not** skip: load `references/phase-3-validate-debug.md` and enter its diagnosis path for the in-progress/stuck update (inspect it via `ListUpdates`/`DescribeUpdate`). Do not emit a fresh Phase 1/2 plan over a running update. |
| `CREATING` / `DELETING` | **Skip cluster** — log the state. If it is the only cluster, terminate with error report. |
| `FAILED` | **Skip cluster** — log FAILED state. If it is the only cluster, terminate with error report. |

**Action 3 — Probe Kubernetes API reachability.** Attempt one lightweight K8s-API read (list nodes). If it fails (access entry absent, `authenticationMode` excludes `API`, or 401/403), **do not abort** — set `k8s_api_available: false`, advise from AWS-control-plane facts, and record every K8s-dependent gate input as `unavailable`/`unconfirmed` in Coverage. The advisor does not green-light a phase on a cluster it could not inspect.

### Phase 1 — Prepare

Load `references/phase-1-prepare.md`. Run the seven gates — readiness (route to `eks-upgrade-check`), backup (route to `eks-backup`), version hop & skew, add-on target versions, drain safety (PDBs/topology/capacity), Karpenter migration state, and control-plane upgrade prerequisites (cluster IAM role / KMS key / logging) — then select the **mode** and **rollback strategy**. Because the skill is autonomous (no interactive prompt), the exit is deterministic: **READY** (all gates GREEN), **READY-WITH-CAVEATS** (GREEN/AMBER, no RED — Phase 2 emitted with every AMBER listed as an explicit "operator must accept before running" caveat), or **NOT-READY** (any RED, or a material `unconfirmed` — no Phase 2 steps emitted as runnable). The advisor never assumes an AMBER is accepted.

### Phase 2 — Execute

Load `references/phase-2-execute.md`. Emit the ordered runbook: **Karpenter 0.x→1.x (first, if applicable) → control plane → add-ons → data plane** (AWS's documented control-plane → add-ons → data-plane order), branching at the data-plane step by the chosen mode (in-place rolling, or blue-green — `references/blue-green-mode.md`) and by compute model (MNG / self-managed / Karpenter / Fargate / Auto Mode). Each step carries a mid-flight hard-stop. Only emitted when Phase 1 exited READY or READY-WITH-CAVEATS (never from NOT-READY).

### Phase 3 — Validate / Debug

Load `references/phase-3-validate-debug.md`. Provide the post-upgrade validation checklist, the symptom-based debug table for a stalled upgrade, and the rollback / cut-back decision. Fallback capacity (old nodes / blue fleet) is retained until validation is GREEN.

---

## How to Use the References

Load `references/upgrade-model.md` **first** — it carries the laws (version skew, the sequence,
rollback reality) and the mode definitions every phase depends on. Then load the phase file(s)
the request needs.

| Intent / when to use | Reference file |
|----------------------|----------------|
| Always first — the upgrade laws, the canonical sequence, the two modes, rollback reality | [upgrade-model.md](references/upgrade-model.md) |
| Pre-upgrade gates: readiness, backup, version hop/skew, add-ons, drain safety, Karpenter, mode selection | [phase-1-prepare.md](references/phase-1-prepare.md) |
| The ordered execution runbook (Karpenter → control plane → add-ons → nodes) + mid-flight hard-stops | [phase-2-execute.md](references/phase-2-execute.md) |
| Post-upgrade validation checklist, symptom-based debug table, rollback/cut-back decision | [phase-3-validate-debug.md](references/phase-3-validate-debug.md) |
| The blue-green cutover **mode** overlay (when the mode is chosen in Phase 1) | [blue-green-mode.md](references/blue-green-mode.md) |

For a **targeted question** ("my upgrade is stuck, nodes won't drain"), load `upgrade-model.md` +
`phase-3-validate-debug.md`. For a **full upgrade plan**, load `upgrade-model.md` + all three
phase files (+ `blue-green-mode.md` if that mode is chosen). Each reference describes assessment
**declaratively** as capability blocks (AWS API calls, and "**Via Kubernetes API**" blocks for
K8s resources). There is no Agent tool and no subagents in this environment — analysis isolation
is achieved by loading one reference at a time, not by spawning subagents.

---

## Report Output

Produce **two** artifacts. The agent generates both directly — no external conversion tools or scripts.

The report structure below is a **contract**: emit these sections in this order, and include a section even if empty (write "none detected" / "unconfirmed" rather than omitting it) so a reader can trust that a missing item means "assessed and absent," not "skipped."

### 1. Phased upgrade plan (primary)

- **Filename:** `EKS-Upgrade-Plan-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

```markdown
# EKS Upgrade Plan — <cluster> (<region>)
_generated <timestamp> · source: AWS API + K8s API · <current version> → <target version>_

## Decision: READY | READY-WITH-CAVEATS | NOT-READY
<one-line rationale tied to the Phase 1 gates; if READY-WITH-CAVEATS, list the AMBER caveats the operator must accept; if NOT-READY, the blocking gate>

## Mode & rollback strategy
<in-place rolling | blue-green cutover; rollback path: node-group revert / cut-back to blue;
7-day control-plane version-rollback window noted>

## Phase 1 — Prepare (gate results)
| Gate | Result | Evidence / routed-to |
|------|--------|----------------------|
| Readiness (eks-upgrade-check) | GREEN | score 88, no hard blockers |
| Backup (eks-backup) | AMBER | PARTIAL — stateful gap named |
| Version hop & skew | GREEN | 1.31 → 1.32, single minor; skew OK |
| Add-on target versions | GREEN | vpc-cni/coredns/kube-proxy/ebs-csi resolved |
| Drain safety (PDBs/capacity) | unconfirmed | PDB read 403 — supplementary ClusterRole needed |
| Karpenter migration state | N/A | MNG only |
| CP upgrade prereqs (IAM role/KMS/logging) | GREEN | role present; no encryption; api/audit logs on |

## Phase 2 — Execute (the ordered runbook)
<the sequenced steps for the chosen mode; every command prefixed "Operator runs (this skill does not):">

## Phase 3 — Validate / Debug
<the post-upgrade checklist + the debug table pointer>

## Notable facts
<flat neutral bullets>

## Coverage
<facts that could not be confirmed + reason — never a false negative>
- phase1.drain_safety.pdbs: unconfirmed (policy-group read 403 under AmazonAIOpsAssistantPolicy)
```

### 2. Guided upgrade runbook

- **Filename:** `EKS-Upgrade-Runbook-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

A step-by-step runbook a human executes, assembled from the phase files and tailored to the
chosen mode and the detected compute types. Every command is presented as an instruction for the
operator, prefixed with a clear note that **this skill does not run it**.

---

## Read-Only Guardrails

1. **Assess and instruct — never act.** This skill reads facts and emits a phased plan + runbook. It never triggers a cluster update, updates an add-on, drains a node, or cuts over traffic. Runbook commands are for a human to run.
2. **Consume sibling verdicts; do not re-derive them.** Readiness comes from `eks-upgrade-check`, backup posture from `eks-backup`, node-OS mechanics from `eks-al2-to-al2023`. The advisor sequences and gates; it does not re-score, re-assess, or re-explain them.
3. **Cite the source and date for every version/timeline/skew claim.** The one-minor rule, the 7-day rollback window, the N-3 skew policy, AL2/cgroup/containerd version triggers, and extended-support cost all carry a source URL and "as of 2026-07-20" — see the phase files and `references/upgrade-model.md`. Do not assert from memory.
4. **Distinguish absence from unconfirmed.** A PDB (`policy` group) or Karpenter (CRD) read that returns `403` is `unconfirmed` (with the reason + the ClusterRole fix), never "no blocking PDBs" or a guessed version. A material `unconfirmed` gate is treated as **not-GREEN**, never silently passed.
5. **Never green-light a phase you could not inspect.** If the K8s API is unreachable, or a safety gate is `unconfirmed`, the phase exits NOT-READY with the gap named in Coverage.
6. **Do NOT hardcode or guess cluster names.** Discover via ListClusters first (Step 0).
7. **Do NOT retry a failed API call more than once.** If it fails twice, record the gap in Coverage and continue.
8. **A version upgrade is (mostly) one-way; gates run before action.** The 7-day version rollback is narrow (one minor, version-only). Never present it as a general undo, and never emit Phase 2 as runnable from a NOT-READY Phase 1.

---

*This skill is provided as sample code for educational and demonstration purposes only. Findings are point-in-time and should be validated before acting on them. Upgrade procedures must be reviewed and tested in a non-production environment first. See the project's README and LICENSE for full terms.*
