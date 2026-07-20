# Module: Gate 4 — Stateful Data

> **Part of:** [eks-blue-green-readiness](../SKILL.md)
> **Purpose:** Blue and green run **simultaneously** during the overlap window. If both point at
> the same stateful data and both can write, that is **split-brain / data divergence**. This gate
> classifies where the cluster's state lives (external managed store vs in-cluster PV/StatefulSet
> vs stateless) and decides whether green can be stood up and cut over safely. Load
> [readiness-model.md](readiness-model.md) first for the gate vocabulary and roll-up.

## Table of Contents

- [The failure: two clusters, one datastore](#the-failure-two-clusters-one-datastore)
- [Datastore ownership: the three shapes](#datastore-ownership-the-three-shapes)
- [What to read](#what-to-read)
- [The gate table](#the-gate-table)
- [Worked example](#worked-example)

---

## The failure: two clusters, one datastore

Blue-green's whole point is that blue keeps serving while green is validated. But **state does not
fork for free**. During the overlap, if a stateful service runs on **both** clusters against the
**same** backing store — or if the cutover shifts writes to green while blue can still write — you
get **split-brain**: two writers, divergent state, and no clean merge. Cutting a stateful service
over at the DNS/LB layer (Gate 3) while both sides can write is the classic way this happens (as
of 2026-07-20; source: [EKS blue/green upgrade guidance](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
→ "Evaluate Blue/Green Clusters" / stateful considerations).

The safe patterns all enforce **single-writer at any instant**:
- **Quiesce-and-cut** — stop writes on blue, ensure the store is consistent, then let green take
  over as the sole writer (brief write-downtime).
- **App-level replication + failover** — the datastore's own replication (e.g. a managed DB with a
  replica) promotes green's endpoint after blue is demoted; the datastore, not the cluster,
  guarantees single-writer.
Neither is something this skill performs — Gate 4 confirms that **an ownership + single-writer
story exists** before green is stood up, and routes the actual data-movement/restore mechanics to
`eks-backup`.

## Datastore ownership: the three shapes

The gate outcome is driven by **where the state lives and who owns write authority**:

1. **Any external read-write store, shared.** The data lives **outside** both clusters. This
   includes the AWS-managed stores (RDS / Aurora / DynamoDB / ElastiCache / EFS / S3) **and any
   non-AWS / on-prem / mainframe backend** — e.g. a z/OS **CICS/DB2** database, an **IBM MQ** queue
   manager, a self-managed database, or a third-party SaaS datastore. Green can reach the same store
   as blue — convenient *but* both clusters can write unless cutover discipline enforces
   single-writer. This is **AMBER**: safe **only with** a quiesce-and-cut or replica-failover
   discipline at cutover; the operator must accept and own that discipline. (EFS/S3 shared-read is
   lower-risk than a read-write primary, but the write-coordination requirement is the same for any
   read-write store, AWS or not.) A store that maps to none of the AWS names above (mainframe/non-AWS)
   is **still an external read-write store** — it must **not** be read as "stateless" just because it
   is not on the AWS list.

   > **Replication lag / RPO is an operator-asserted input.** When the cutover plan relies on
   > **replica promotion / failover** (rather than quiesce-and-cut), the **replication lag / RPO at
   > the cutover instant** determines whether green promotes a consistent copy or loses the last N
   > seconds of writes. This skill cannot read the store's replication lag (the datastore describe
   > APIs are out of scope — see *What to read*), so lag/RPO is **operator-asserted**; if unverified
   > it is `unconfirmed` (not-GREEN, and not silently AMBER) — see the gate table.
2. **In-cluster stateful (StatefulSet on a PV / EBS), no cross-cluster story.** The data lives
   **inside** blue — an EBS-backed PV is bound to one AZ and to **blue's** PV/PVC objects; green
   cannot simply reuse it, and there is no replication to green. Standing green up and cutting over
   would either lose the data or (if forced) risk split-brain. This is **RED** unless a concrete
   data-migration/replication plan exists (route to `eks-backup` for snapshot/restore or to the
   app's own replication).
3. **Stateless (confirmed).** No StatefulSets, no bound read-write PVs that hold authoritative
   state, **and no shared external read-write store** (shape 1) — either there is no state at all,
   or every external store green touches is green-connect-only / not a shared writer. This is
   **GREEN**: green can be stood up and cut over with no data-ownership constraint. **"Stateless"
   must be a confirmed read** — an unreadable data shape, or "no external endpoint found" when the
   endpoint could be hiding in an unreadable Secret/pod env, is `unconfirmed`, **never** assumed
   stateless (mirrors `eks-backup`'s "unconfirmed shape never downgrades urgency"). A shared external
   read-write store is shape 1 (**AMBER**), not stateless — the GREEN classification excludes it.

## What to read

**Via Kubernetes API (`AmazonAIOpsAssistantPolicy` — built-in groups only, all authorized):**
- `StatefulSets` (`apps` group) → in-cluster stateful workloads and their replica counts.
- `PersistentVolumeClaims` / `PersistentVolumes` (core group) → bound volumes, their
  `storageClassName`, access modes (`ReadWriteOnce` EBS vs `ReadWriteMany` EFS), and the CSI driver
  (`storage.k8s.io` StorageClasses) → distinguishes EBS-bound single-AZ single-cluster volumes from
  shared EFS.
- `Services`/`ConfigMaps` env (core) referencing external endpoints (RDS/DynamoDB hostnames) →
  signals an external managed store (shape 1) vs in-cluster (shape 2). **Note: `secrets` is NOT in
  the `AmazonAIOpsAssistantPolicy` core-readable set** (see SKILL.md → *Kubernetes API Access*), so
  a DB endpoint that lives **only** in a Secret (or in an unreadable env source) **cannot** be read
  here. Consequently, **"no external endpoint found" does NOT mean stateless** — the endpoint may be
  hiding in an unreadable Secret or pod env; that case resolves to **`unconfirmed`**, not GREEN (see
  the gate table).

**Via AWS API (readable under `iam-policy.json`):**
- `kms:DescribeKey` / `GetKeyPolicy` → for an encrypted external store or EBS CSI CMK, whether
  green's principals can be granted key access (a support fact for the migration story; the store's
  own describe APIs — RDS/EFS/S3 — are **not** in this skill's read scope and route to `eks-recon`
  / `eks-backup` for detail).

> **Unreadable = unconfirmed (never "stateless" / GREEN).** If the K8s API is unreachable, or the
> StatefulSet/PVC/PV reads fail, the **data shape is `unconfirmed`** — and per the safe-default
> rule the gate is **not-GREEN** (it does **not** assume stateless). Report the failed read + fix.
> **CRD caveat:** some data operators expose state through CRDs (e.g. a database operator's
> `Cluster`/`Backup` CRD, a `VolumeSnapshot` on `snapshot.storage.k8s.io`) that are **not**
> authorized by the managed policy (403). Where authoritative state ownership depends on such a
> CRD, that fact is `unconfirmed` — never inferred as stateless or as "has a replication story".

## The gate table

**Evaluation order: rows are evaluated top-down; the first matching row wins.** Rows are ordered
**worst-first** (RED, then unconfirmed, then AMBER, then GREEN) so that when inputs could match more
than one row, the safe (not-GREEN) outcome wins. In particular, a cutover that relies on an
**unverified replica promotion** matches the unconfirmed row (row 3) **before** the AMBER shared-store
row (row 4) — a managed store with a read replica matches **both**, and worst-first ensures the
unverified-RPO promotion resolves to `unconfirmed` (not-GREEN), never silently to AMBER. Likewise a
shared external read-write store matches row 4 (AMBER) **before** the stateless row (GREEN, row 5)
can apply — the GREEN row explicitly **excludes** any shared read-write store.

| # | Condition (first match wins, top-down) | Outcome |
|---|----------------------------------------|---------|
| 1 | **In-cluster stateful** (StatefulSet on an EBS-backed `ReadWriteOnce` PV or similar), **no** cross-cluster replication/migration story | **RED** — green cannot reuse blue's single-AZ single-cluster volume, and forcing a cutover risks data loss or split-brain. Require a concrete data-migration/replication plan (route to `eks-backup`) before standing green up; or prefer an in-cluster (node-fleet) blue-green that keeps the same PVs (route to `eks-upgrade-advisor` for that mode). |
| 2 | Data shape **unreadable** (K8s API down, or StatefulSet/PVC/PV reads fail); **or** authoritative ownership depends on an unreadable CRD; **or** **no external endpoint was found but state cannot be confirmed absent** (the DB endpoint may live only in an unreadable **Secret**/pod env — `secrets` is not core-readable) | **unconfirmed** — do **not** assume stateless; treated as not-GREEN. Report the failed read + fix in Coverage. |
| 3 | Cutover depends on **replica promotion / failover**, and the **replication lag / RPO at cutover is unverified** (operator-asserted and not confirmed) | **unconfirmed** — a stale replica promoted at cutover loses the last writes; lag/RPO is operator-asserted and cannot be read here. Not-GREEN, and not silently AMBER, until the operator confirms an acceptable RPO/lag. (If the operator confirms lag/RPO is acceptable, this reduces to the row-4 AMBER discipline.) Evaluated **before** the AMBER shared-store row so an unverified-RPO promotion cannot slip to AMBER. |
| 4 | **Any shared external read-write store** — AWS-managed (RDS/Aurora/DynamoDB/ElastiCache/EFS/S3) **or non-AWS / mainframe (DB2·CICS·IBM MQ)** — reachable by both clusters | **AMBER** — safe **only with** a cutover discipline (quiesce-and-cut, or replica promotion) that enforces single-writer. List the store(s); require the operator to accept the discipline before cutover. **If the cutover relies on unverified replica promotion, row 3 (unconfirmed) fires first — do not land here.** Route the failover/quiesce mechanics to `eks-backup` / the datastore's own tooling. |
| 5 | **Stateless** confirmed — no StatefulSets, no authoritative read-write in-cluster PVs, **and no shared external read-write store** (state is either fully absent, or external **and** each store is green-connect-only / not a shared writer per rows 3–4) | **GREEN** — green can be stood up and cut over with no data-ownership constraint. Requires a *confirmed* read (row 2 covers the unconfirmable case). |

## Worked example

**Facts:** blue `prod-blue`, K8s API reachable. Workload scan: 3 Deployments (stateless web/API),
**1 StatefulSet** `postgres` with 1 replica bound to a `ReadWriteOnce` **EBS gp3** PVC via the EBS
CSI driver; ConfigMaps reference no external DB host (the app talks to the in-cluster `postgres`
Service). No `VolumeSnapshot`/replication CRD readable (and none inferred). No external RDS
endpoint found.

**Evaluation:** authoritative state is **in-cluster** — an EBS-backed single-AZ, single-cluster PV
owned by blue's StatefulSet, with **no** cross-cluster replication story → **row 1 → RED** (first
match; the "no external endpoint found" fact does not reach the row-2 unconfirmed case because the
in-cluster StatefulSet already establishes the data shape as a confirmed read). Report: green
(a separate cluster) cannot reuse blue's EBS PV; cutting a DNS/LB shift over while `postgres` runs
on both sides risks split-brain, and standing green up without migrating the data loses it. Require
a concrete plan before green: snapshot/restore or logical replication to a green-side Postgres
(route mechanics to `eks-backup`), **or** use an in-cluster (node-fleet) blue-green that keeps the
same cluster and PVs (route to `eks-upgrade-advisor`'s blue-green mode). This RED, combined with
Gate 2's RED in the other example, would roll up to **NO-GO** (combinator row 1).
</content>
