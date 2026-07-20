# Module: Phase 2 — Execute

> **Part of:** [eks-upgrade-advisor](../SKILL.md)
> **Purpose:** The ordered upgrade sequence, emitted as an operator runbook. Applies the
> canonical sequence from [upgrade-model.md](upgrade-model.md), branches by the **mode** chosen
> in Phase 1, and carries mid-flight hard-stops so a stall is caught at the step that caused it.
> **This skill does not run any of these steps** — every command is for a human operator.
> Do not emit this phase until Phase 1 exited **READY** or **READY-WITH-CAVEATS** (never NOT-READY).

## Table of Contents

- [Entry gate](#entry-gate)
- [The sequence (both modes share the spine)](#the-sequence-both-modes-share-the-spine)
- [Step 0 — Karpenter 0.x → 1.x (only if applicable)](#step-0--karpenter-0x--1x-only-if-applicable)
- [Step 1 — Upgrade the control plane](#step-1--upgrade-the-control-plane)
- [Step 2 — Update add-ons to new-control-plane-compatible versions](#step-2--update-add-ons-to-new-control-plane-compatible-versions)
- [Step 3 — Roll the data plane (mode + compute-model dependent)](#step-3--roll-the-data-plane-mode--compute-model-dependent)
- [Mid-flight hard-stops](#mid-flight-hard-stops)
- [Phase 2 exit contract](#phase-2-exit-contract)

---

## Entry gate

| Condition | Action |
|-----------|--------|
| Phase 1 exited **READY**, mode + rollback strategy recorded | **Proceed.** |
| Phase 1 exited **READY-WITH-CAVEATS** (GREEN/AMBER, no RED, no material unconfirmed) | **Proceed** — emit the runbook, but surface every AMBER caveat as an explicit "operator must accept before running" block at the top; do not assume acceptance. |
| Phase 1 exited **NOT-READY**, or any RED / material `unconfirmed` gate open | **Do not emit runnable steps** — restate the blocking gate and return to Phase 1. |
| Mode not chosen | **Hold** — the data-plane step (Step 3) branches on mode; resolve the decision first. |

## The sequence (both modes share the spine)

Steps 0→2 are identical in both modes; only **Step 3 (data plane)** branches. The order is the
load-bearing invariant — AWS's documented control-plane → add-ons → data-plane sequence; see
[upgrade-model.md](upgrade-model.md) → The canonical sequence.

```
Step 0  Karpenter 0.x → 1.x        (separate lifecycle change, FIRST; skip if N/A)
Step 1  Control plane +1 minor      (the EKS upgrade)
Step 2  Add-ons → new-CP-compatible (RIGHT AFTER control plane; they don't ride along)
Step 3  Data plane                  (in-place rolling  OR  blue-green — see blue-green-mode.md;
                                      branches by compute model: MNG / self-managed / Karpenter
                                      / Fargate / Auto Mode)
        → then Phase 3 (validate/debug)
```

Every command below is prefixed for the operator:

```
Operator runs (this skill does not):
  <command>
```

## Step 0 — Karpenter 0.x → 1.x (only if applicable)

Only if Phase 1 Gate 6 found Karpenter on 0.x. This is a **Karpenter-lifecycle migration
(v1beta1 → v1), independent of the cluster upgrade**, done first and validated on its own.

- Karpenter must be on **0.33+** before the v1 migration (conversion webhooks handle in-place
  CRD conversion — no node roll required for the migration itself), then manifests updated to
  the v1 API before moving to 1.1+ (as of 2026-07-20; source:
  [Announcing Karpenter 1.0](https://aws.amazon.com/blogs/containers/announcing-karpenter-1-0/)).
- Validate that `NodePool`/`EC2NodeClass` resources reconcile on v1 and new nodes provision
  **before** starting the cluster upgrade.

| Condition | Action |
|-----------|--------|
| Karpenter migrated to 1.x and provisioning verified | **Proceed to Step 1.** |
| Migration incomplete / webhooks erroring | **Hard-stop** — do not upgrade the cluster with a half-migrated Karpenter; resolve first. |
| Karpenter version `unconfirmed` (CRD 403) | **Hold** — cannot confirm safe state; report `unconfirmed`, name the supplementary-ClusterRole fix, do not assume migrated. |

## Step 1 — Upgrade the control plane

The single-minor EKS control-plane upgrade (Law 1). One minor version only, and it goes
**first** — before add-ons and nodes — so nothing version-coupled is ever raised ahead of the
API server (Law 3).

- **One pre-control-plane exception:** if VPC CNI is **below the target's minimum floor**, raise
  it first (to a version supporting *both* the old and new control plane). Every other add-on
  waits for Step 2. Removed-API remediation and backups were already handled in Phase 1.
- Trigger the EKS cluster update to the target minor. EKS performs a rolling, in-place
  control-plane upgrade; it is **not** instantaneous — it commonly takes on the order of tens of
  minutes. Watch it via `aws eks describe-update`; treat it as **in progress, not stuck**, while
  the update status is `InProgress` — only escalate to Phase 3 debug on a `Failed` status or no
  status change over a sustained period, so a normally-slow upgrade isn't mistaken for a hang.
- **7-day rollback net:** note in the runbook that if a control-plane-level regression appears,
  EKS can revert one minor within 7 days (version-only, in-place clusters only, not Fargate —
  see [upgrade-model.md](upgrade-model.md) → Rollback reality). This is the escape hatch for the
  control-plane step specifically; it does not cover Step 2/3 changes.

| Condition | Action |
|-----------|--------|
| Control plane reaches target version, status `ACTIVE` | **Proceed to Step 2.** |
| Update `FAILED` / stuck (see Phase 3 diagnosis) | **Hard-stop** — go to Phase 3 debug; do not update add-ons or roll nodes onto a control plane that did not fully upgrade. |

## Step 2 — Update add-ons to new-control-plane-compatible versions

Add-ons do not ride along (Law 4) — update them **right after** the control-plane upgrade, to
the versions compatible with the **new** control plane (resolved in Phase 1 Gate 4, re-confirmed
against the now-current version).

- Order within the step: **CNI (vpc-cni) → CoreDNS → kube-proxy → ebs-csi / others.** The CNI
  is the highest-blast-radius add-on — pods can't get IPs if it breaks. Update one minor step
  at a time where the add-on requires it.
- Self-managed controllers (Helm/manifest) are the operator's responsibility; the runbook names
  them and requires an explicit new-control-plane-compatible-version confirmation.
- *(EKS **Auto Mode**: the core add-ons are EKS-managed — no manual update here; confirm health
  and move on.)*

| Condition | Action |
|-----------|--------|
| All critical add-ons updated and `ACTIVE` at new-CP-compatible versions | **Proceed to Step 3.** |
| An add-on update goes `DEGRADED` / `FAILED` | **Hard-stop** — do NOT roll nodes on a broken CNI/CoreDNS (drain can't reschedule); roll the add-on back to the prior compatible version and resolve. |

## Step 3 — Roll the data plane (mode + compute-model dependent)

Nodes go **last** so `kubelet` never leads `kube-apiserver` (skew is only defined for kubelet
*behind*). This step branches on **both** the mode (in-place vs blue-green) **and** the compute
model.

**By compute model** (route node-OS mechanics to `eks-al2-to-al2023`; this skill sequences):

| Compute model | Data-plane action |
|---------------|-------------------|
| **Managed node groups** | EKS-managed node-group version update (surge new nodes, cordon/drain old respecting PDBs, delete empties). |
| **Self-managed** | Operator rolls the ASG/launch-template to the target AMI; same cordon/drain/PDB discipline. |
| **Karpenter** | Roll via drift/expiry or node-pool update on v1; new nodes provision at the target version. |
| **Fargate** | **No node roll** — pods pick up the new kubelet only when **recycled**. After the control-plane bump, the operator **restarts/rolls the Fargate deployments** (as of 2026-07-20; source: [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html) → "Restart Fargate deployments after upgrading the control plane"). |
| **EKS Auto Mode** | **EKS rolls the managed nodes itself** after the control-plane upgrade, respecting PDBs — the operator monitors, does not manually roll. |

**In-place rolling (default):** surge new target-version nodes in, cordon + drain old nodes,
respect PDBs (cleared in Phase 1 Gate 5), delete old nodes once empty.

**Blue-green cutover (mode):** stand up the parallel target-version fleet and shift workloads —
**see [blue-green-mode.md](blue-green-mode.md)** for the full overlay. Do not duplicate it here.

**Node-OS crossings that land in this step** (route node-OS mechanics to `eks-al2-to-al2023`;
this skill only flags the version triggers):

| Trigger version | Concern | Action |
|-----------------|---------|--------|
| Target **1.33+** | No AL2 EKS AMI exists (1.32 was the last; AL2023/Bottlerocket only, as of 2026-07-20; source: [EKS AL2 deprecation FAQ](https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html)) | If any node group is still AL2, the node roll **is also an AL2→AL2023 migration** — route to `eks-al2-to-al2023` for nodeadm/cgroup/IMDS mechanics; do not re-explain them here. |
| Target **1.35** | cgroup v1 deprecated — kubelet refuses to start on a cgroup-v1 node by default (`failCgroupV1` defaults to fail; AL2023 already uses cgroup v2) (as of 2026-07-20; source: [EKS standard-support versions](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html)) | Confirm nodes are on cgroup v2 (AL2023/Bottlerocket) before rolling; a lingering cgroup-v1 self-managed AMI won't boot. |
| Crossing **1.35 → 1.36** | 1.35 is the last release supporting containerd 1.x; 2.0+ required beyond it (as of 2026-07-20; same source) | For EKS-optimized AL2023 AMIs the runtime is bundled (handled by the AMI); a **self-managed / custom AMI** must ship containerd 2.0+ — flag it. |

| Condition | Action |
|-----------|--------|
| All nodes on target version, workloads rescheduled, within skew | **Proceed to Phase 3.** |
| Drain stalls / nodes stuck `NotReady` / rescheduling fails | **Hard-stop** — go to Phase 3 debug; do not delete old nodes while workloads are unscheduled. |

## Mid-flight hard-stops

Applies across all steps — the advisor bakes these into the runbook so a stall is caught at its
cause, not three steps later:

| Symptom mid-upgrade | Hard-stop action |
|---------------------|------------------|
| Drain hangs on a pod | **Stop the roll** — a PDB (`disruptionsAllowed==0`) or a long terminationGracePeriod is blocking; do not force-delete blindly. → Phase 3. |
| Critical add-on flips `DEGRADED` after a step | **Stop** — resolve/roll back the add-on before continuing; a broken CNI cascades. |
| New nodes fail to join / stay `NotReady` | **Stop** — check node-OS crossing (cgroup/containerd/AMI), subnet IPs, or launch-template userData. → Phase 3. |
| Control-plane update `FAILED` | **Stop** — Phase 3 diagnosis; consider the 7-day version rollback if it is a control-plane regression. |

## Phase 2 exit contract

Phase 2 completes only when the control plane is at the target version **and** the data plane
is fully rolled to the target (all nodes, within skew, workloads rescheduled) under the chosen
mode. A stall at any step routes to **Phase 3 (validate/debug)** before any destructive
follow-up (deleting old nodes, dismantling a blue fleet). Never tear down the old/fallback
capacity until Phase 3 confirms the new state healthy.
