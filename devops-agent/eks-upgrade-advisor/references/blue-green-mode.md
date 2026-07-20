# Module: Blue-Green Mode (Overlay)

> **Part of:** [eks-upgrade-advisor](../SKILL.md)
> **Purpose:** The **blue-green cutover mode** — an overlay on Phases 2–3, not a phase of its
> own. It replaces the in-place node roll (Phase 2 Step 3) with a parallel target-version fleet
> and a traffic cutover, and it changes the Phase 3 recovery path to a **cut-back**. Selected in
> Phase 1. Load [upgrade-model.md](upgrade-model.md) and [phase-2-execute.md](phase-2-execute.md)
> first — this file only describes what changes under the mode.

## Table of Contents

- [What "blue-green" means here (altitude)](#what-blue-green-means-here-altitude)
- [When to choose it](#when-to-choose-it)
- [The two blue-green shapes](#the-two-blue-green-shapes)
- [How it overlays each phase](#how-it-overlays-each-phase)
- [Cutover gate](#cutover-gate)
- [Cut-back (the payoff)](#cut-back-the-payoff)
- [Cost & capacity note](#cost--capacity-note)

---

## What "blue-green" means here (altitude)

This is the **cluster-upgrade cutover** strategy: the target-version data plane (or an entire
target-version cluster) is stood up **in parallel** to the old one, workloads/traffic are
shifted to it, and the old ("blue") capacity is kept intact as an instant fallback until the
new ("green") side is validated.

> **Not to be confused with:** the **node-group-level canary blue-green** for an AL2→AL2023 AMI
> change, which is owned by `eks-al2-to-al2023`. That is a data-plane-only AMI swap within one
> cluster/version; this is an *upgrade cutover* across a version change. When a blue-green
> upgrade also crosses AL2→AL2023 (target 1.33+), route the node-OS mechanics to
> `eks-al2-to-al2023` and keep the cutover orchestration here.

## When to choose it

Deterministic selection (mirrors Phase 1's decision table):

| Prefer blue-green when | Prefer in-place (default) when |
|------------------------|-------------------------------|
| Instant node-level fallback required (regulated / high-stakes workload) | Standard risk tolerance, maintenance window available |
| Validating a large or multi-hop upgrade on isolated parallel capacity before committing | Simple single-minor hop |
| Wanting to test the target version under real traffic with a fast escape | Surge headroom is available but full parallel capacity is not |
| Subnet IPs / quota can accommodate a **full parallel fleet** | IPs only support a modest surge |

If subnet IPs/quota cannot support a parallel fleet, blue-green is **not** available — Phase 1
Gate 5 flags this; fall back to in-place or resolve capacity first.

## The two blue-green shapes

| Shape | What is parallel | Cutover mechanism | Use when |
|-------|------------------|-------------------|----------|
| **In-cluster (node-fleet) blue-green** | A new target-version node group / Karpenter pool alongside the old, **same cluster & (already-upgraded) control plane** | Cordon blue nodes, shift pods to green via reschedule, keep blue cordoned-not-deleted as fallback | Most upgrades wanting fast node fallback; control plane already upgraded in place (one minor) |
| **Cluster blue-green** | An entire new cluster at the target version | Shift traffic at the ingress/DNS/load-balancer layer from old cluster to new | Big multi-minor jumps, or when you want the target control plane validated in full isolation before any production traffic |

For the **in-cluster** shape the control plane is still upgraded in place in Phase 2 Step 1
(one minor, 7-day rollback net). For the **cluster** shape the new cluster is provisioned at the
target version directly (no in-place control-plane hop on the old cluster).

## How it overlays each phase

- **Phase 1 (Prepare):** same gates, plus confirm **parallel-fleet capacity** (subnet IPs **and**
  EC2 vCPU quota) and — for the cluster shape — a **traffic-shift mechanism** (ingress/DNS/LB
  weighting), a **consumer re-point plan** (below), and a **state/data strategy** (below).

> **Cluster-shape blue-green changes the cluster's identity — plan the consumer re-point.** A new
> cluster has a **new API endpoint and a new OIDC issuer URL**. That breaks two things silently:
> (1) **IRSA** — every IAM role trust policy scoped to the old cluster's OIDC provider must be
> updated (or re-created) for green's issuer, or pods lose their AWS credentials; Pod Identity
> associations must likewise be re-created on green. (2) **Every consumer of the endpoint** —
> `kubectl` configs, CI/CD deploy targets, GitOps controllers — must be re-pointed. Also,
> **load balancers and external-DNS do not span two clusters**, so ingress/cert wiring is
> re-created on green (target-group registration, connection draining, external-dns records, cert
> re-issue/validation). None of this exists in the in-cluster shape (same endpoint/OIDC). State it
> in the plan; it is the most common cluster-blue-green surprise (as of 2026-07-20; source:
> [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
> → "Evaluate Blue/Green Clusters").

> **Stateful workloads are the hard part of cluster blue-green — do not hand-wave this.** For the
> **cluster shape**, persistent data does **not** move for free: an EBS volume is bound to one AZ
> and one cluster's PV/PVC objects, so a green cluster cannot simply reuse it; and cutting a
> stateful service over at the DNS/LB layer while both clusters can write risks **split-brain /
> data divergence**. Cluster-shape blue-green generally cannot cover a stateful service **without
> either downtime** (quiesce writes on blue, snapshot/restore or re-mount to green, then cut over)
> **or app-level replication** (e.g. a database's own replica + failover). Route the actual
> data-movement/restore mechanics to `eks-backup`, but state this constraint plainly in the plan.
> When stateful cluster-blue-green isn't feasible, prefer the **in-cluster (node-fleet) shape**
> (same cluster, same PVs — no data migration) or in-place rolling.
- **Phase 2 (Execute):** Steps 0–2 unchanged (Karpenter, then control plane, then add-ons).
  **Step 3 is replaced** by: stand up green at the target version → bring green
  add-ons/controllers to new-control-plane-compatible versions → shift workloads/traffic to green
  → **keep blue intact**.
- **Phase 3 (Validate/Debug):** validate on **green** using the standard checklist; the recovery
  path becomes **cut-back to blue** (below) instead of a node-group version rollback. Blue is
  torn down only at the Phase 3 tear-down gate, after green is GREEN.

## Cutover gate

| Condition | Action |
|-----------|--------|
| Green fully provisioned, add-ons `ACTIVE` at target-compatible versions, canary workloads healthy on green | **Proceed** — shift the remaining traffic/workloads to green. |
| Green unhealthy before cutover | **Hold on blue** — do not shift traffic; blue is still serving. Diagnose green via Phase 3. |
| Stateful data not yet replicated/consistent on green | **Hard-stop** — do not cut over stateful traffic until data is consistent on green (route to `eks-backup` for the data strategy); a premature cutover risks split or lost state. |

## Cut-back (the payoff)

The reason to pay for blue-green: recovery is a **traffic/scheduling shift back to blue**, which
is untouched and already at the known-good prior version — far faster than a version rollback or
a node-group AMI revert, and it covers data-plane *and* (cluster-shape) control-plane regressions.

| Situation | Cut-back |
|-----------|----------|
| Green misbehaves after partial cutover | Shift traffic/workloads back to blue; blue never changed. |
| Green misbehaves after full cutover, blue not yet torn down | Re-point ingress/DNS/LB (cluster shape) or un-cordon blue + reschedule (node-fleet shape) back to blue. |
| Blue already torn down | Cut-back is gone — this is why the tear-down gate (Phase 3) holds until green is GREEN. |

## Cost & capacity note

Blue-green runs **two fleets (or two clusters) concurrently** for the overlap window — roughly
double the compute cost during cutover, plus enough subnet IPs / instance quota for both sides.
State this in the plan so the operator accepts the cost trade for the faster, safer fallback.
The advisor never silently assumes the capacity exists — Phase 1 Gate 5 must confirm it.
