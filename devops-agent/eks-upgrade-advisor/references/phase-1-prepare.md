# Module: Phase 1 — Prepare

> **Part of:** [eks-upgrade-advisor](../SKILL.md)
> **Purpose:** The pre-upgrade gate battery. Confirm readiness (route to `eks-upgrade-check`),
> confirm a backup exists (route to `eks-backup`), verify the mechanical pre-conditions
> (version hop, skew headroom, add-on target versions, drain-safety, capacity), then select the
> **mode** and **rollback strategy**. Nothing in Phase 2 is emitted as "ready to run" until
> every Phase 1 gate below is **GREEN**. Load [upgrade-model.md](upgrade-model.md) first.
>
> **Gate outcome vocabulary (deterministic).** Every gate row resolves to exactly one of:
> **GREEN** (satisfied — proceed), **AMBER** (a caveat that does not block — proceed with it
> recorded), **RED** (hard-stop — does not proceed), **unconfirmed** (a required fact could not
> be read — treated as *not-GREEN*, i.e. it blocks like RED until confirmed, and is named in
> Coverage). The exit contract below keys only on these four words — no gate emits a bare verb.

## Table of Contents

- [Entry gate (from Step 0)](#entry-gate-from-step-0)
- [Gate 1 — Readiness confirmed](#gate-1--readiness-confirmed)
- [Gate 2 — Backup taken (recovery gate)](#gate-2--backup-taken-recovery-gate)
- [Gate 3 — Version hop & skew](#gate-3--version-hop--skew)
- [Gate 4 — Add-on target versions resolved](#gate-4--add-on-target-versions-resolved)
- [Gate 5 — Drain safety (PDBs, single-replica, capacity)](#gate-5--drain-safety-pdbs-single-replica-capacity)
- [Gate 6 — Karpenter migration state](#gate-6--karpenter-migration-state)
- [Gate 7 — Control-plane upgrade prerequisites (IAM role, KMS, logging)](#gate-7--control-plane-upgrade-prerequisites-iam-role-kms-logging)
- [Decision — mode & rollback strategy](#decision--mode--rollback-strategy)
- [Phase 1 exit contract](#phase-1-exit-contract)
- [Worked example (facts → gates → mode → outcome)](#worked-example-facts--gates--mode--outcome)

---

## Entry gate (from Step 0)

Phase 1 begins only after SKILL.md Step 0 has selected an `ACTIVE` cluster and probed K8s-API
reachability. If `k8s_api_available: false`, every K8s-dependent gate below degrades to
`unconfirmed` (never `false`) and Phase 1 exits `NOT-READY` with the reachability gap named in
Coverage — the advisor does not green-light an upgrade it could not inspect.

> **Non-prod first (standing discipline, not a per-run gate).** The emitted plan states, once, up
> front: AWS recommends rehearsing the upgrade in a **non-production** cluster before production
> (as of 2026-07-20; source: [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
> → "Before Upgrading"). The advisor's plan is per-cluster; it does not assume the target is prod
> or non-prod, but the runbook header carries this reminder so it is never skipped.

## Gate 1 — Readiness confirmed

This skill does **not** re-score readiness. Route to `eks-upgrade-check` and consume its verdict.
Only **hard blockers** gate this skill; the 0–100 score / band is **surfaced, not gating** — a
low-but-blocker-free score proceeds with the score recorded and its risks noted. **EKS Upgrade
Insights** (`ListInsights`/`DescribeInsight`) are owned by `eks-upgrade-check`'s readiness area
and reach this gate *through* that verdict — the advisor reads them directly only as a fallback
when a readiness verdict is unavailable (so it can still surface AWS's own UPGRADE_READINESS
findings), never to re-derive a score.

| Condition | Outcome |
|-----------|---------|
| `eks-upgrade-check` verdict available, **zero hard blockers** (any band) | **GREEN** — record the score + band + target version; continue to Gate 2. |
| Verdict available, **hard blocker(s)** present (removed-API in use, DEGRADED critical add-on, subnet IPs below floor, etc.) | **RED** — do not emit Phase 2. Restate each blocker and route back to `eks-upgrade-check` remediation. |
| Verdict available, no hard blocker but a **low/RISKY band** | **AMBER** — proceed with the band + its risk drivers recorded; the band informs mode choice (a risky cluster leans blue-green), it does not block. |
| Readiness **not yet run** | **unconfirmed** — instruct the operator to run `eks-upgrade-check` first; the advisor consumes its output, it does not substitute for it. Treated as not-GREEN. |

## Gate 2 — Backup taken (recovery gate)

EKS offers only a **narrow version rollback** (one minor, within 7 days, version-only — Law 2),
so a current backup remains mandatory insurance before touching the control plane: it is the
only thing that recovers *data and objects* if something worse than a version regression occurs.
Route to `eks-backup` for the posture verdict.

The stateful-vs-stateless branches below consume the **data shape** from `eks-backup` (it detects
StatefulSets + bound PVs). If the data shape is itself `unconfirmed` (K8s API unreadable), **never
assume stateless** — default to the stateful branch (mirrors `eks-backup`'s "unconfirmed shape
never downgrades urgency").

| `eks-backup` posture | Outcome |
|----------------------|--------|
| `READY` (recent recovery point / current Velero schedule) | **GREEN** — proceed. |
| `PARTIAL`, cluster stateful (or shape unconfirmed) | **RED until closed** — do not proceed until the operator closes the gap for stateful workloads; state the gap. |
| `PARTIAL`, cluster confirmed stateless | **AMBER** — may proceed with the risk noted. |
| `UNPROTECTED`, cluster stateful (or shape unconfirmed) | **RED** — hard-stop. Emit the `eks-backup` runbook first. Never green-light an upgrade of an unprotected stateful cluster. |
| `UNPROTECTED`, cluster confirmed stateless | **AMBER** — may proceed with the risk explicitly recorded. |
| posture `unconfirmed` (backup CRDs / K8s API unreadable) | **unconfirmed** — treat as not-GREEN; name the coverage gap; do not silently pass. |

> **A backup is not a version undo, and the version rollback is not a backup.** State this
> wherever recovery is discussed: the backup protects *data and objects*, restored into a
> running/new cluster — it does **not** restore etcd or change the Kubernetes version. The EKS
> 7-day version rollback reverts the *control-plane version only* — it does **not** recover
> data or undo post-upgrade mutations. They cover different failure modes; keep both (see
> [upgrade-model.md](upgrade-model.md) → Rollback reality, and the `eks-backup` limitation
> callout).

## Gate 3 — Version hop & skew

Facts from `DescribeCluster` (current version) + the requested target. The rows are exhaustive
over the target-vs-current relation (equal / +1 / >1 / lower / unreleased) and the skew state.

| Condition | Outcome |
|-----------|---------|
| Target **==** current version | **RED** — nothing to upgrade; report already-at-target and stop (no plan emitted). |
| Target is **lower** than current (downgrade request) | **RED** — this skill does not plan downgrades; the only supported reversal is the EKS 7-day version rollback (see [upgrade-model.md](upgrade-model.md)). State that and stop. |
| Target is exactly current **+1 minor** | **GREEN** — a single valid hop. |
| Target is **>1 minor** ahead | **AMBER (sequence)** — split into single-minor hops (Law 1); this skill's plan covers ONE hop; state that the operator repeats the full cycle per minor. Do not emit a multi-minor jump as one upgrade. (For big jumps, note blue-green cluster-shape as an alternative.) |
| Target minor **not yet released** on EKS | **RED** — abort target; instruct to pick a released version (verify against the EKS versions page, as of 2026-07-20). |
| Current `kubelet`/node skew **already beyond** the EKS limit vs the API server | **RED** — nodes outside the supported window (N-2 for ≤1.27, N-3 for ≥1.28) must be rolled into policy *before* another control-plane hop; a further hop would push them further out and the API server rejects them. |
| Existing `kubelet` skew **near** the limit vs current API server | **AMBER** — record the headroom; nodes must be rolled promptly after the control-plane hop (Phase 2 Step 3) to stay in-policy (as of 2026-07-20; source: [Kubernetes version skew policy](https://kubernetes.io/releases/version-skew-policy/)). |
| Current version already in **extended support** | **AMBER (note, non-blocking)** — surface cost/timeline urgency: EKS gives **14 months standard + 12 months extended** per minor (26 total); extended bills **$0.60/cluster-hour vs $0.10 standard** (as of 2026-07-20; source: [EKS version lifecycle](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)). Proceed. |

## Gate 4 — Add-on target versions resolved

Add-ons do not ride along (Law 4). For each managed add-on (vpc-cni, coredns, kube-proxy,
ebs-csi, plus any others detected), resolve the version compatible with the **target** control
plane via `DescribeAddonVersions`. This is a Phase 1 *resolution* step; the actual update runs in
**Phase 2 Step 2 — right *after* the control-plane upgrade** (AWS's control-plane → add-ons
order). The one exception: VPC CNI below the target's minimum floor may be raised *before* the
control plane, to a version supporting both (Phase 2 Step 1). *(EKS **Auto Mode** manages the
core add-ons itself — mark N/A and skip.)*

| Condition | Outcome |
|-----------|---------|
| Compatible target version resolvable for every critical add-on | **GREEN** — record the target version per add-on for Phase 2 Step 2. |
| A critical add-on currently `DEGRADED` / `FAILED` **pre-upgrade** | **RED** — resolve health before upgrading; a broken CNI/CoreDNS stalls the later node rotation (drain can't reschedule). |
| No compatible version exists for a critical add-on at the target | **RED** — the add-on gates the upgrade; resolve (or replace) it first. |
| Add-on is self-managed (Helm/manifest, not an EKS managed add-on) | **AMBER** — the operator owns its compatibility; name it and require an explicit new-control-plane-compatible-version confirmation. |
| **cluster-autoscaler** present (if used instead of Karpenter) | **AMBER** — its version is tightly coupled to the Kubernetes minor; a mismatch breaks scaling mid node-roll. Call it out explicitly (like CNI/CoreDNS) and require the target-minor-matched version. |

## Gate 5 — Drain safety (PDBs, single-replica, capacity)

Node rotation (Phase 2 step 3, and blue-green cutover) drains nodes. Drain-blockers must be
cleared in Prepare.

Subnet free-IP thresholds below are a **skill-internal heuristic** for *node-subnet surge*, shared
with `eks-upgrade-check` for consistency — they are **not** an AWS-published node-surge number.
(AWS publishes only a control-plane-subnet requirement of "up to 5 available IPs" for the cluster
ENIs, which is a different thing; source: [EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
→ "Verify available IP addresses", as of 2026-07-20.) Applied per node-subnet: **< 5** free = RED,
**5–15** = AMBER, **> 15** = GREEN.

| Condition | Outcome |
|-----------|---------|
| A PodDisruptionBudget with `disruptionsAllowed == 0` (or `maxUnavailable: 0`) | **RED** — the #1 "upgrade stuck" cause: drain blocks forever. Name the PDB + workload; require it relaxed for the maintenance window. |
| PDBs live on the `policy` API group; if that read is **blocked/unreadable** (403) | **unconfirmed** — report `unconfirmed`, never "no blocking PDBs"; flag in Coverage. Treated as not-GREEN until confirmed (supplementary ClusterRole needed). |
| No blocking PDB found (read succeeded) | **GREEN** — record. |
| Single-replica Deployments / un-replicated StatefulSets present | **AMBER** — these incur downtime on drain; list them so the operator accepts or scales out first. |
| Workloads with `topologySpreadConstraints` set to `whenUnsatisfiable: DoNotSchedule` (readable — core/`apps` groups) | **AMBER** — like a strict PDB, this can both reduce availability during the roll and block reschedule if the surviving/new topology can't satisfy the spread. List them so the operator confirms the spread is satisfiable across the rolled fleet. |
| Any node-subnet with **< 5** free IPs | **RED** — in-place surge and blue-green both need free IPs; too few blocks the node surge/rotation. Report per-subnet free IPs. |
| Any node-subnet with **5–15** free IPs (none below 5) | **AMBER** — tight; node rotation may stall under surge. Report per-subnet free IPs (route capacity facts to `eks-recon` if needed). |
| All node-subnets **> 15** free IPs | **GREEN** — sufficient *in-place surge* headroom. (Blue-green needs a **full parallel fleet** ≈2× — that capacity is checked separately in the BG sub-block below, not settled by this GREEN.) |

> **Gate 5 records the worst of all rows that match.** The four dimensions above (blocking PDB,
> single-replica / un-replicated StatefulSet, strict `topologySpread`, subnet free-IPs) are
> independent and can co-occur — e.g. a RED PDB alongside an AMBER subnet, or an AMBER subnet
> alongside an `unconfirmed` PDB read. When more than one row matches, the recorded outcome is the
> most restrictive of them (RED < unconfirmed < AMBER < GREEN).

> **Blue-green overlap — aggregate against the WHOLE pool, do not evaluate per-fleet.** The
> per-subnet heuristic above assumes a *single* fleet's surge. When the selected mode is
> **blue-green**, blue and green are alive at once and (in the common shared-subnet case) draw IPs
> from the **same pool**. The authoritative check compares green's projected demand against the
> pool's current **free** IP count:
>
> > **GREEN-projected demand  ≤  current FREE IPs in the pool**
> > (`free` already nets out **every** other consumer — BLUE-live *and* any third tenant sharing the
> > subnet — so this form holds no matter how many fleets/clusters share the CIDR).
>
> Use the free-IP form as primary. The total-pool form `BLUE-live + GREEN-projected ≤ total usable`
> (usable = subnet size minus the 5 AWS-reserved addresses; e.g. a `/25` = 128 − 5 = 123 usable) is
> **equal to it only when blue and green are the pool's SOLE consumers.** In a genuinely shared
> subnet a third consumer X exists, so `free = total usable − BLUE-live − X`; the total-usable form
> drops the −X term and **over-states capacity → false GREEN**. Only use the total-usable form for a
> single-consumer (blue-only) pool, or subtract the others explicitly (`… ≤ total usable −
> other-consumers`). [blue-green-mode.md](blue-green-mode.md) and the mode-decision definition below
> use this **same** free-IP-primary comparison. Estimate green's side from CNI/ENI facts (projected
> node count × per-node demand, warm-target pre-allocation, prefix vs secondary-IP mode); the
> mechanics and mitigations live in [blue-green-mode.md](blue-green-mode.md) → "Capacity strategies
> under blue-green". The rows below extend Gate 5 **only when mode == blue-green**. The same
> skill-internal band heuristic (still **NOT** an AWS-published node-surge number) applies to the
> **residual headroom** left after the aggregate: `headroom = current free IPs − GREEN-projected`
> (equal to `total usable − (BLUE-live + GREEN-projected)` only when blue+green are the sole
> consumers), banded **< 5** = RED, **5–15** = AMBER (tight), **> 15** = GREEN.

| Condition (blue-green mode only) | Outcome |
|----------------------------------|---------|
| **GREEN-projected ≤ current free IPs** with residual headroom **> 15**, and pool consumption is **readable** | **GREEN** — green fits comfortably; blue (and any third consumer, already netted out of free) coexist with green in the shared pool for the overlap window. Record GREEN-projected vs current free IPs. (Mirrors [blue-green-mode.md](blue-green-mode.md) decision aid — the minimum model holds; record and proceed.) |
| **GREEN-projected ≤ current free IPs** but leaves residual headroom of only **5–15** IPs | **AMBER** — fits but tight; the overlap has little slack (a late-scaling green pod or blue not draining on schedule can tip it to exhaustion). Report GREEN-projected vs current free IPs; consider secondary-CIDR or rolling-drain-down before cutover. |
| **GREEN-projected exceeds current free IPs** (or residual headroom **< 5**) | **RED** — cutover would stall: green cannot get pod/node IPs while blue (and any third consumer) still hold their share. Report GREEN-projected vs current free IPs; resolve capacity (secondary-CIDR / rolling-drain-down) or fall back to in-place. |
| Green node/pod subnets carved from a **separate secondary VPC CIDR** (green does not share blue's pool), green's own pool is sized for GREEN-projected demand + warm targets, **and** custom networking / `ENIConfig` is **confirmed** to target the secondary-CIDR subnets | **GREEN** — contention escaped; blue keeps its pool. **Note:** confirming that targeting requires reading the `ENIConfig` CRD (unreadable under `AmazonAIOpsAssistantPolicy`) and at Phase 1 no green nodes exist to observe instead — so absent a supplementary ClusterRole this GREEN is **not routinely reachable** and normally resolves to `unconfirmed` (next row). It is a real GREEN only once the CRD read is granted or green nodes are up. |
| Secondary CIDR present for green but green's pool **not** sized for its projected demand (or CNI not yet pointed at it) | **AMBER** — mitigation started but unproven; size/verify green's pool before cutover. |
| Green's secondary-CIDR targeting depends on `ENIConfig`, but that **CRD read is blocked** (`ENIConfig` lives on `crd.k8s.amazonaws.com`, a **custom** resource — **not** authorized by `AmazonAIOpsAssistantPolicy`, which grants built-in API groups only; and at Phase 1 no green nodes exist yet to observe the effective CNI config instead) | **unconfirmed** — the secondary-CIDR GREEN above **cannot** be recorded: green's targeting is unproven, treated as not-GREEN, **never GREEN**. Report the supplementary-ClusterRole fix (mirrors Gate 6's Karpenter-CRD gap); route the read to `eks-recon`. |
| Pool consumption **unreadable** (CNI config / ENI / IPAM facts blocked, e.g. `aws-node` env or EC2 describe unavailable) | **unconfirmed** — report the gap; treated as not-GREEN, **never GREEN/"fits"**. Route the read to `eks-recon`; blue-green is not confirmed-available until the aggregate is measurable. |

> **Within the blue-green sub-block, take the worst matching row.** The BG rows above are not
> mutually exclusive: when green's pool is sized but the `ENIConfig` CRD is unreadable, the
> "secondary-CIDR present but CNI not yet pointed at it" (AMBER) row and the "`ENIConfig` read
> blocked" (unconfirmed) row **both** match — the two are indistinguishable from the readable facts
> (a sized-but-unverified pool and an unreadable targeting CRD look the same). **When more than one
> BG row matches, the sub-block's outcome is the most restrictive of them (RED < unconfirmed <
> AMBER < GREEN).** So the overlap resolves to **unconfirmed**, never GREEN/AMBER off an unreadable
> CRD — an unreadable `ENIConfig` can never yield a confirmed reading.
>
> **Under blue-green, Gate 5's outcome is the WORSE of the two readings.** The main per-subnet
> table above is a *single-fleet* surge reading; a single-fleet **GREEN** (every node-subnet > 15
> free) does **not** settle Gate 5 when mode == blue-green — a contended *shared* subnet can pass
> the single-fleet row yet fail the aggregate sub-block. **When mode == blue-green, Gate 5's
> recorded outcome is the worse (more restrictive) of (a) the single-fleet main-table row and (b)
> this blue-green aggregate sub-block** (RED < unconfirmed < AMBER < GREEN), where the sub-block's
> own value is itself the worst of its matching rows per the note just above. The exit contract must
> never record Gate 5 = GREEN off the single-fleet row alone under blue-green mode.

## Gate 6 — Karpenter migration state

If Karpenter is present, its 0.x→1.x migration (v1beta1→v1) is a **separate change that goes
first** (sequence step 0), before the cluster upgrade.

| Condition | Outcome |
|-----------|---------|
| Karpenter absent (MNG / Auto Mode / Fargate only) | **N/A (GREEN)** — skip; note compute type. |
| Karpenter already on 1.x | **GREEN** — proceed to the cluster upgrade sequence. |
| Karpenter on 0.x | **GREEN (sequenced)** — not a blocker, but the plan must emit Karpenter 0.x→1.x as **Phase 2 Step 0** (migrate to 1.x, validate, THEN upgrade the cluster); do not interleave. |
| Karpenter version **unconfirmed** (CRD read `403` under `AmazonAIOpsAssistantPolicy`) | **unconfirmed** — Karpenter CRDs (`karpenter.sh`, `karpenter.k8s.aws`) are not authorized by the managed policy; report `unconfirmed` with the supplementary-ClusterRole fix, never a guessed version. Treated as not-GREEN. |

## Gate 7 — Control-plane upgrade prerequisites (IAM role, KMS, logging)

AWS requires specific account resources for the control-plane upgrade itself; **if they are not
present, the cluster cannot be upgraded** and EKS reverts the attempt (as of 2026-07-20; source:
[EKS cluster upgrade best practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
→ "Verify basic EKS requirements before upgrading"). These are all **read-only verifiable** ahead
of time — subnet free-IP capacity is already covered by Gate 5; this gate covers the rest.

| Condition | Outcome |
|-----------|---------|
| Cluster IAM role (`cluster.roleArn` from `DescribeCluster`) present, resolvable via `iam:GetRole` | **GREEN** — record. |
| Cluster IAM role **missing or not resolvable** | **RED** — the control-plane update will fail; the role must be restored before upgrading. |
| Secret/envelope encryption **enabled** (`DescribeCluster` `encryptionConfig` present) **and** the cluster IAM role can use the KMS key (`kms:GetKeyPolicy`/`DescribeKey` shows the grant) | **GREEN** — record. |
| Encryption enabled but the cluster role **lacks** KMS-key permission | **RED** — the update fails; grant the role `kms:Decrypt`/`DescribeKey` on the CMK first. |
| Encryption **not** enabled | **N/A (GREEN)** — no KMS dependency. |
| KMS-key policy read **blocked** (no `kms:GetKeyPolicy`) | **unconfirmed** — report the gap; treated as not-GREEN until confirmed. |
| Control-plane logging (api/audit) **enabled** before the upgrade | **GREEN** — record. |
| Control-plane logging **disabled** | **AMBER** — recommend enabling api/audit logging *before* Step 1 so upgrade-time errors are captured (AWS "Before Upgrading" guidance); non-blocking but strongly advised — a Phase 3 debug of a stuck update is far harder without it. |

> **IAM note:** verifying this gate needs read-only `iam:GetRole` and (for the KMS branch)
> `kms:DescribeKey`/`kms:GetKeyPolicy`. These are included in `references/iam-policy.json` under the
> `UpgradePrereqReadAccess` Sid. If your Agent Space role is scoped tighter and omits them, this
> gate degrades to `unconfirmed` (not-GREEN) rather than failing — the plan names the gap.

## Decision — mode & rollback strategy

Mode selection is **deterministic and fact-based** — the autonomous default is **in-place
rolling** unless a concrete trigger below forces (or the user's request explicitly names)
blue-green. The rows are ordered; apply the **first** that matches (no overlap):

| # | Trigger (evaluated in order) | Mode |
|---|------------------------------|------|
| 1 | Any node-subnet **< 5** free IPs (Gate 5 RED) | **neither — RED**; resolve capacity first. |
| 2 | User's request explicitly asks for blue-green / a cutover | **Blue-green** (if capacity allows a parallel fleet; else RED). |
| 3 | Target is **>1 minor** ahead (multi-hop, Gate 3 AMBER) **and** a full parallel fleet fits the subnet/quota | **Blue-green** (cluster shape) — validate the jump on isolated capacity. |
| 4 | Gate 1 band is **RISKY/low** (blocker-free) **and** a parallel fleet fits | **Blue-green** — instant fallback for a high-risk upgrade. |
| 5 | Otherwise | **In-place rolling** (default). |

"A parallel fleet fits" is a fact with **two** halves, both required — using the **same aggregate
comparison** as Gate 5's blue-green sub-block above:
- **IPs:** `GREEN-projected demand ≤ current free IPs in the pool` — the authoritative form, because
  `free` nets out **all** other consumers (BLUE-live *and* any third tenant sharing the subnet). Use
  the total-pool form `BLUE-live + GREEN-projected ≤ total usable` **only** when blue+green are the
  pool's sole consumers (otherwise it drops the third consumer and false-GREENs); *not* GREEN-projected
  vs a subnet's isolated headroom. See the Gate 5 BG rows and
  [blue-green-mode.md](blue-green-mode.md) → "Shared-subnet aggregate contention".
- **Quota:** **EC2 On-Demand vCPU / instance-limit quota headroom** for green's real instances
  (blue-green consumes ~2× for the overlap; secondary-CIDR fixes IPs but **not** this half).

If a blue-green trigger fires but either half does **not** fit, the outcome depends on **which
trigger fired** — the advisor never silently overrides an explicit user path:
- **Advisor-initiated triggers (rows 3–4)** — where the advisor merely *suggested* blue-green (a
  multi-hop jump or a RISKY band): record **AMBER** and fall back to **in-place** with the reason
  noted. Blue-green was the advisor's optimization, not a requirement; in-place is a safe default.
- **User-requested blue-green (row 2)** — where the user *explicitly asked* for blue-green / a
  cutover but it does **not** fit: the outcome is **RED** (NOT-READY). The user's chosen path is
  blocked; do **not** silently downgrade their explicit request to in-place. Report the capacity
  gap and the fix (secondary-CIDR / rolling-drain-down / quota increase) so the user can decide
  whether to resolve capacity or consciously switch to in-place — the advisor does not make that
  switch for them.

(The Gate 5 BG sub-block gates the IP half explicitly; the vCPU half is verified here and applies
equally under blue-green — a green fleet that fits on IPs can still stall on a vCPU-quota ceiling.)

> **Capacity is two facts, not one.** Even in-place *surge* consumes extra instances briefly;
> blue-green consumes ~2× for the overlap. Subnet free-IPs (Gate 5) is one constraint; **EC2
> On-Demand vCPU service-quota** is the other. Hitting a vCPU limit mid-surge stalls the node roll
> exactly like IP exhaustion — surface both. (Quota facts are readable via Service Quotas; route
> raw capacity inventory to `eks-recon` if needed.)

Record the chosen mode and the rollback strategy (in-place: node-group rollback to prior
release; blue-green: cut back to old fleet). This choice is an **input to Phase 2**.

## Phase 1 exit contract

Because the skill is **fully autonomous (no interactive prompt)**, there is no live "operator
accepts" channel — so the exit is resolved deterministically from the gate outcomes:

- **READY** — every gate is **GREEN**, and a mode + rollback strategy are chosen.
- **READY-WITH-CAVEATS** — gates are GREEN or **AMBER** (no RED, no material `unconfirmed`). The
  advisor emits Phase 2 **and** lists every AMBER as an explicit "operator must accept before
  running" caveat at the top of the plan. It does not assume acceptance; it makes the caveats
  impossible to miss and leaves the go/no-go with the human.
- **NOT-READY** — any **RED**, or any **`unconfirmed`** gate that materially affects safety
  (backup, PDBs, Karpenter version, cluster IAM role / KMS, K8s-API reachability). The blocking
  condition is named, the relevant sibling runbook is routed, and **no** Phase 2 steps are
  emitted as runnable.

(Gates 1–7 all feed this contract; a RED in any — including the Gate 7 control-plane
prerequisites — holds the exit at NOT-READY.)

The advisor never emits Phase 2 as runnable from a NOT-READY state, and never silently upgrades
an AMBER to accepted.

## Worked example (facts → gates → mode → outcome)

Deterministic walk-through; a second agent given the same facts must reach the same result.

**Facts (from Step 0 + siblings):** cluster `prod-1`, current **1.30**, target **1.31**,
`authenticationMode: API_AND_CONFIG_MAP`, K8s API reachable. `eks-upgrade-check`: score 82, band
READY, **zero hard blockers**. `eks-backup`: **READY** (recovery point 12h old), data shape
stateful (3 StatefulSets on gp3). Add-ons vpc-cni/coredns/kube-proxy/ebs-csi all `ACTIVE`, target
1.31-compatible versions resolve. PDB read succeeds: **no** `disruptionsAllowed==0`; no strict
topologySpread. Node-subnets: two at 40+ free IPs, one at **9**. Karpenter **absent** (2 managed
node groups). Cluster IAM role present; **no** envelope encryption; api/audit logging **on**.

**Gate evaluation:**

| Gate | Facts → | Outcome |
|------|---------|---------|
| 1 Readiness | score 82, 0 blockers | **GREEN** |
| 2 Backup | READY, stateful | **GREEN** |
| 3 Version/skew | 1.30→1.31 = +1; nodes at 1.30 (in-skew) | **GREEN** |
| 4 Add-ons | all compatible target versions resolve | **GREEN** |
| 5 Drain safety | no blocking PDB / topologySpread; **one subnet at 9 free IPs (5–15)** | **AMBER** |
| 6 Karpenter | absent | **N/A (GREEN)** |
| 7 CP prereqs | IAM role present; no encryption (KMS N/A); logging on | **GREEN** |

**Mode:** apply the ordered triggers — no subnet <5 (row 1 no), request didn't ask blue-green
(row 2 no), single-minor not >1 (row 3 no), band READY not RISKY (row 4 no) → **row 5: in-place
rolling**. Rollback strategy: node-group revert to the 1.30 release.

**Exit:** one AMBER (Gate 5), no RED, no material unconfirmed → **READY-WITH-CAVEATS**. Phase 2 is
emitted, topped with the caveat: *"Subnet `subnet-x` has 9 free IPs (5–15 band) — node rotation
may stall under surge; free IPs or reduce surge before running Step 3."* The go/no-go stays with
the operator.
