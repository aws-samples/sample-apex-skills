# Module: Upgrade Model (Foundation)

> **Part of:** [eks-upgrade-advisor](../SKILL.md)
> **Purpose:** The conceptual foundation every phase depends on — the laws of an EKS
> upgrade (version skew, the sequencing order, irreversibility), the two upgrade **modes**
> (in-place rolling vs blue-green cutover), and the vocabulary the phase files reuse. **Load
> this first**, before any phase file. It carries the rules; the phase files apply them.

## Table of Contents

- [What this skill is (and is not)](#what-this-skill-is-and-is-not)
- [The five laws of an EKS upgrade](#the-five-laws-of-an-eks-upgrade)
- [The canonical sequence](#the-canonical-sequence)
- [The AL2 node-OS fork (why the AL2 path depends on nodegroup type)](#the-al2-node-os-fork-why-the-al2-path-depends-on-nodegroup-type)
- [The two modes](#the-two-modes)
- [Rollback reality](#rollback-reality)
- [How the phases gate](#how-the-phases-gate)
- [Sources](#sources)

---

## What this skill is (and is not)

This skill is the **execution advisor** for an EKS Kubernetes-version upgrade. It assumes the
readiness *question* has already been answered by `eks-upgrade-check` (the 0–100 score and the
blocking-finding list) and turns a **GO** decision into a **safe, ordered, phased plan** the
operator executes: what to touch, in what order, where the hard-stops are, and how to diagnose
a stalled upgrade.

It does **not** re-score readiness, re-inventory the cluster, re-explain node-OS migration
mechanics, or assess backup tooling — those belong to the sibling skills (see the SKILL.md
routing table). Its unique lane is the **cross-domain order-of-operations**: the one place that
sequences control plane + add-ons + nodes into a single runbook with gates between phases.

## The five laws of an EKS upgrade

These are invariants. Every phase gate derives from one of them.

1. **One minor version at a time.** EKS upgrades the control plane exactly one minor version
   per upgrade (e.g. `1.30 → 1.31`, never `1.30 → 1.32` in a single step). Multi-version jumps
   are a sequence of single-minor upgrades, each fully validated before the next.
2. **A version upgrade is reversible only within a narrow window.** EKS supports a Kubernetes
   **version rollback of one minor version, within 7 days** of the upgrade (as of 2026-07-20;
   source: [EKS version rollback](https://aws.amazon.com/blogs/aws/upgrade-amazon-eks-clusters-with-confidence-using-kubernetes-version-rollbacks/)).
   Outside that window — or for a multi-minor jump — there is **no downgrade**. And a rollback
   reverts the *control-plane version only*; it does **not** undo data-plane changes, add-on
   updates, or any workload/PV-data mutation that happened after the bump. So the backup gate
   and the mode/rollback decision still live in *Prepare*: the version rollback is a
   time-boxed safety net, **not** a substitute for a backup or for a blue-green cut-back.
3. **The data plane follows the control plane, within skew, and never leads it.** Kubernetes'
   version-skew policy lets `kubelet` trail `kube-apiserver` but **never lead** it — and the
   same "not newer than the API server" rule binds `kube-proxy` and other control-plane-coupled
   components. On EKS, managed node groups / Fargate support **N-2** skew for **≤1.27** and
   **N-3** for **≥1.28** (as of 2026-07-20; sources:
   [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html),
   [Kubernetes version skew policy](https://kubernetes.io/releases/version-skew-policy/)).
   Nodes must be upgraded to stay inside that window; letting them fall outside it makes the API
   server reject them. The "never lead" half is why the control plane is upgraded **before**
   add-ons and nodes — bumping `kube-proxy`/CoreDNS to the target minor while the API server is
   still on the old minor would put a component *ahead* of the API server.

   > **Managed nodes carry an *additional* API gate, stronger than skew — and it is what forks
   > the AL2 path.** Skew (above) is what Kubernetes *tolerates*; separately, EKS's
   > `update-cluster-version` API **rejects** a control-plane upgrade until every **managed** node
   > group **and Fargate** already **equals the control plane's *current* minor** (as of
   > 2026-07-21; source: [EKS troubleshooting — "Node groups must match Kubernetes version before
   > upgrading control plane"](https://docs.aws.amazon.com/eks/latest/userguide/troubleshooting.html)).
   > **Self-managed** nodes are **not** API-gated — their `kubelet` version is not visible to the
   > EKS API — so a self-managed data plane may lawfully trail the control plane up to the **N-3**
   > skew limit while the control plane advances. That asymmetry is the hinge of the two AL2
   > execution paths (Phase 1 → *AL2 node-OS path*; Phase 2 → Step 3): once no matching AL2 AMI
   > exists, a **managed** AL2 group blocks the very next control-plane hop, whereas a
   > **self-managed** AL2 group can hold in place while the control plane moves.
4. **Add-ons do not ride along — upgrade them right *after* the control plane.** Upgrading the
   control plane does **not** auto-update managed add-ons (vpc-cni, coredns, kube-proxy,
   ebs-csi) or self-managed controllers (as of 2026-07-20; source:
   [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)).
   AWS's documented order is **control plane → add-ons → data plane**: add-on target versions
   are the ones compatible with the *new* control plane, and version-coupled add-ons
   (`kube-proxy`, CoreDNS) must not be raised ahead of the API server (Law 3). A version-
   incompatible critical add-on (especially CNI or CoreDNS) *left un-updated after* the
   control-plane bump is a top cause of a stuck or degraded upgrade. *(Exception: EKS **Auto
   Mode** manages the core add-ons and node rotation itself.)*
5. **Removed APIs break workloads silently.** APIs removed in the target version stop serving
   the moment the control plane crosses that version. Anything still calling them (workloads,
   controllers, GitOps, Helm) fails **after** the bump, not before — so it must be remediated
   in Prepare.

## The canonical sequence

The single most load-bearing fact in this skill. Upgrade in this order; each step is a phase
gate before the next:

```
0. Karpenter 0.x → 1.x FIRST   (v1beta1 → v1 CRD API migration; do this before the cluster
                                 upgrade, not during it — it is its own lifecycle change)
1. Control plane                (the one-minor EKS upgrade itself)
2. Add-ons / controllers        (update to versions compatible with the NEW control plane)
3. Node groups / data plane      (roll nodes to the target version, within skew)
4. Verify                        (Phase 3 — post-upgrade health + debug)
```

This is AWS's documented control-plane → add-ons → data-plane order (as of 2026-07-20; source:
[EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html),
"Upgrade your control plane and data plane in sequence"). Rationale: Karpenter's 0.x→1.x is a
CRD API migration independent of the cluster version and must not be entangled with it. The
control plane goes **first** so version-coupled add-ons (`kube-proxy`, CoreDNS) and nodes are
never raised *ahead* of the API server (Law 3 — nothing leads the API server). Add-ons go
**right after** the control plane (they don't ride along — Law 4) and are qualified against the
*new* control-plane version. Nodes go **last**, within skew.

> **Pre-control-plane remediation still happens in Prepare.** Removed-API fixes, backups, and
> readiness are resolved *before* step 1 (Phase 1) — they are pre-conditions, not part of the
> touch-order above. VPC CNI is the one add-on that may need raising *before* the control plane
> **only if** it is below the target's minimum floor; even then, to a version that supports both
> the old and new control plane. All other add-ons follow the control plane.

## The AL2 node-OS fork (why the AL2 path depends on nodegroup type)

A cluster still running **Amazon Linux 2 (AL2)** nodes hits a hard wall the plan must fork on
**before** touching the control plane, because **no AL2 EKS-optimized AMI exists for 1.33 or
1.34 — 1.32 was the last** (as of 2026-07-21; source:
[EKS AL2 AMI deprecation FAQ](https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html)).
Combined with Law 3's managed-node API gate, this splits into **two execution paths that fork on
the AL2 nodegroup type** — the advisor selects the path in Phase 1 and sequences it in Phase 2
Step 3; the node-OS mechanics themselves route to `eks-al2-to-al2023`:

1. **Managed node group on AL2 → migrate to AL2023 *first*, before any control-plane hop.**
   The `update-cluster-version` API is rejected until the managed group equals the control
   plane's *current* minor (Law 3 callout), and **no AL2 AMI exists past 1.32** — so a managed
   AL2 group can never be raised past 1.32. The control plane can complete **exactly one hop**
   (1.32 → 1.33) but **cannot advance beyond 1.33** — the 1.33 → 1.34 hop is rejected because the
   managed group cannot reach 1.33 (no AL2 AMI). So a **target beyond 1.33 is unreachable while an
   AL2 managed group exists**, and you would only get one hop before getting stuck. The migration
   to AL2023 is the unblock and it goes first. Route the migration itself to `eks-al2-to-al2023`.

2. **Self-managed AL2 → "control-plane-first / hold-nodes".** Self-managed `kubelet` is **not**
   API-gated (Law 3 callout), so advance the **control plane one minor at a time**
   (1.32 → 1.33 → 1.34) while **holding** the self-managed AL2 nodes at **kubelet 1.32** — this
   stays inside the **N-3** skew window the API does not gate for self-managed nodes. Then
   migrate the nodes to AL2023 **once**, before the **1.35** hop (below). That is **one** node
   migration for the whole run, **not** an AL2→AL2023 migration per hop.

> **N-3 is the skew *limit*, not slack — migrate before the CP would force a 4th minor.** A
> `kubelet` held at **1.32** under a **1.35** control plane is **exactly 3 minors behind — the
> N-3 boundary, with zero headroom** (as of 2026-07-21; source:
> [Kubernetes version skew policy](https://kubernetes.io/releases/version-skew-policy/); N-3 for
> EKS ≥1.28). The hold is therefore good only through a **1.34** control plane. The self-managed
> nodes **must** migrate to AL2023 **before** the control plane advances to **1.35** — the next
> hop would make the 1.32 kubelet a 4th minor behind and the API server rejects it. This is a
> *ceiling*, not a cushion; the skill must never imply the nodes can sit longer.

> **The 1.35 hop is also a cgroup wall.** Independently of skew, **cgroup v1 hard-fails kubelet
> start at 1.35** (1.33 and 1.34 are fine; AL2023 already uses cgroup v2) (as of 2026-07-21;
> source: [EKS standard-support versions](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html)).
> So for the self-managed path the single AL2→AL2023 node migration must land **before 1.35** on
> **two** counts at once — skew (N-3 exhausted) *and* cgroup v2 — which is why it is scheduled
> at exactly that boundary.

### Rollback-safety rationale — the self-managed hold-nodes path *only*

This "clean per-hop backout" advantage is **specific to the self-managed hold-nodes path** (Path 2
above), where the nodes genuinely do **not move** while the control plane advances. It does **not**
generalize to the in-place path as a whole, and in particular it does **not** apply to the managed
node-group path — see the managed-path contrast below. On the self-managed hold-nodes path,
control-plane-first is not merely **necessary** (no AL2 AMI for the 1.33/1.34 hops, per above) but
also **safer**:

- **Each control-plane hop is independently rollback-eligible.** Because the self-managed nodes
  **stay put** (held at kubelet 1.32) while the control plane advances, every single-minor hop is
  covered on its own by the EKS **7-day, one-minor, version-only, in-place** control-plane rollback
  (see *Rollback reality* below). A hop that regresses backs out cleanly to the prior minor.
- **No coupled node-rollback problem — on this path.** The data plane is **not changing during the
  hops**, so a bad hop has **nothing to un-migrate** on the nodes: the kubelet was already trailing
  the API server and stays trailing after a control-plane rollback, so no node action is coupled to
  the undo. There is no simultaneous "roll the control plane back *and* roll the nodes back" to
  coordinate — the control-plane rollback is the whole undo.
- The **single** node migration is deferred to the one boundary where it is forced (before 1.35 —
  skew + cgroup), keeping the risky data-plane change to **one** well-isolated event instead of
  smearing it across every hop.

> **Managed path: rollback IS coupled — the opposite property.** On the **managed node-group** path
> the AL2→AL2023 migration runs up front, and thereafter the managed nodes are rolled to the new
> kubelet **in lockstep with each control-plane hop** (nodes go last within each hop, but they *do*
> move every hop). So the nodes **do change each hop**, and a control-plane rollback is **not** a
> clean CP-only backout: rolling the control plane down to a lower minor while the nodes sit at the
> higher kubelet would leave **kubelet ahead of kube-apiserver**, which the Kubernetes version-skew
> policy **forbids** (kubelet may trail the API server but **never lead** it — as of 2026-07-21;
> source: [Kubernetes version skew policy](https://kubernetes.io/releases/version-skew-policy/)).
> A managed-path control-plane rollback therefore **forces a coupled node-group rollback** too
> (`UpdateNodegroupVersion` back to the prior release) — the two reversals must be coordinated, and
> the node roll-back is a real, separate data-plane action, not a free side effect. This is why the
> self-managed hold-nodes property above does **not** carry over to the managed path.

## The two modes

Selected in Phase 1, applied in Phases 2–3. **Blue-green is a MODE, not a phase** — see
[blue-green-mode.md](blue-green-mode.md) for the full overlay.

| | **In-place rolling** (default) | **Blue-green cutover** (mode) |
|---|---|---|
| Control plane | upgraded in place (one minor; 7-day rollback net) | still one minor per hop — blue-green is about the **data plane / cutover**, not a second control plane; a parallel *cluster* variant gets a target-version control plane of its own |
| Data plane | new nodes surge in, old cordon/drain out, same cluster | a **parallel target-version node fleet** (or a parallel cluster) is stood up; traffic shifts to it |
| Rollback of nodes | roll the node group back to the prior AMI/version | **cut back** to the untouched old fleet (fast) |
| Cost / complexity | lower; brief capacity overlap | higher; full parallel capacity during cutover |
| When | most clusters; sufficient surge headroom + subnet IPs | strict cutover control, instant node-level fallback, or validating a big jump on a parallel fleet |

> **Altitude note.** This is the **cluster-upgrade cutover** mode. The *node-group-level*
> canary blue-green for an AL2→AL2023 AMI change is owned by `eks-al2-to-al2023`; this skill
> routes there for node-OS mechanics and does not re-explain them.

## Rollback reality

- **Control plane: one-minor rollback within 7 days, else no downgrade.** EKS can revert the
  control plane one minor version within 7 days of the upgrade (source above). This is a
  time-boxed net, not a general undo: it reverts the *version only* — not data-plane changes,
  add-on updates, or post-upgrade data mutation — and it is unavailable outside the window or
  for multi-minor jumps. The pre-upgrade **backup gate** (Phase 1, routed to `eks-backup`)
  therefore still stands: a backup restores workloads + PV data into a *new or existing*
  cluster — it does **not** restore etcd or roll back the version. Backup = data insurance;
  version rollback = a narrow, version-only escape hatch. Neither replaces the other.
- **Add-ons: revertible.** A managed add-on can be updated back to a prior compatible version
  if the new one misbehaves — within the range the target control plane supports.
- **Nodes:** in-place → roll the node group back to the prior release; blue-green → cut back to
  the old fleet. This node-level reversibility is the main reason to choose blue-green for a
  high-stakes upgrade.

> **Version-rollback fine print (as of 2026-07-20; source:
> [Announcing EKS rollback](https://aws.amazon.com/blogs/containers/announcing-amazon-eks-rollback-for-safe-and-reliable-management-of-cluster-upgrades/)).**
> The 7-day one-minor rollback applies only to a cluster that was **upgraded in place** (not one
> created at the current version), the **prior version must still be EKS-supported**, and it is
> **not supported for Fargate**. For **Auto Mode** clusters the rollback also reverts the managed
> worker nodes (not control-plane-only); for managed node groups the operator rolls nodes back
> via `UpdateNodegroupVersion`. A cluster already on the oldest supported minor may have **no
> valid rollback target** — do not present rollback as universally available.

## How the phases gate

Each phase has an **entry-gate table** (in its file). The rule: **do not enter a phase until
the prior phase's gates are GREEN.** A `RED` gate is a hard-stop — the advisor states the
condition and what the operator must resolve, and does not emit the next phase's steps as
"ready to run." Gates that depend on CRD-backed facts the agent cannot read (e.g. PDBs on the
`policy` group, Karpenter CRDs) are reported `unconfirmed`, never `false` — an unconfirmed gate
is treated as **not-yet-GREEN** and flagged in Coverage, never silently passed.

## Sources

All version/timeline/skew claims below carry a source URL and an "as of 2026-07-20" stamp in
the phase files where they are applied. Canonical sources:

- Amazon EKS Kubernetes versions & the upgrade process — https://docs.aws.amazon.com/eks/latest/userguide/update-cluster.html
- EKS version lifecycle / standard vs extended support — https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html
- Kubernetes version skew policy — https://kubernetes.io/releases/version-skew-policy/
- Karpenter v1 migration — https://karpenter.sh/docs/upgrading/v1-migration/
- EKS AL2 AMI deprecation FAQ — https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html
- EKS troubleshooting — "Node groups must match Kubernetes version before upgrading control plane" (managed-node API gate) — https://docs.aws.amazon.com/eks/latest/userguide/troubleshooting.html
- EKS standard-support Kubernetes versions (cgroup v1 / containerd notes) — https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html

> **Do not assert a version, date, or skew number from memory.** Every such claim in the phase
> files is live-verifiable against these sources; carry the URL + "as of 2026-07-20".
