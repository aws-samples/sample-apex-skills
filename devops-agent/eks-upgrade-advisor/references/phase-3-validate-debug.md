# Module: Phase 3 — Validate / Debug

> **Part of:** [eks-upgrade-advisor](../SKILL.md)
> **Purpose:** Confirm the upgraded cluster is healthy, and — when an upgrade stalls or a step
> fails — diagnose it deterministically by symptom. This is where a stuck upgrade gets a named
> cause and a next action, and where the tear-down / cut-back / rollback decision is made.
> Load [upgrade-model.md](upgrade-model.md) first. **This skill instructs; it does not act.**

## Table of Contents

- [Entry gate](#entry-gate)
- [Validation checklist (post-upgrade health)](#validation-checklist-post-upgrade-health)
- [Debug: failure-mode diagnosis table](#debug-failure-mode-diagnosis-table)
- [The rollback / cut-back decision](#the-rollback--cut-back-decision)
- [Tear-down gate (only after GREEN)](#tear-down-gate-only-after-green)
- [Post-upgrade housekeeping](#post-upgrade-housekeeping)
- [Post-upgrade health companion](#post-upgrade-health-companion)
- [Phase 3 exit contract](#phase-3-exit-contract)

---

## Entry gate

Phase 3 runs in two situations: (a) **normal** — after Phase 2 completed, to validate before
tear-down; (b) **debug** — a Phase 2 step hit a mid-flight hard-stop and jumped here. Both use
the tables below; the debug path enters at [the diagnosis table](#debug-failure-mode-diagnosis-table).

## Validation checklist (post-upgrade health)

Confirm each before declaring the upgrade healthy. Facts read via the AWS API + authorized
built-in K8s groups; anything CRD-backed that can't be read is `unconfirmed`, never `false`.

| Check | GREEN when | Source of fact |
|-------|-----------|----------------|
| Control-plane version | cluster status `ACTIVE` at the target minor | `DescribeCluster` |
| Node versions & skew | every node's `kubelet` at target (or within N-3), all `Ready` | K8s `nodes` (core) |
| Critical add-ons | vpc-cni, coredns, kube-proxy, ebs-csi all `ACTIVE` at the target-compatible version | `DescribeAddon` |
| Workloads rescheduled | Deployments/StatefulSets/DaemonSets at desired replicas, no stuck `Pending`/`CrashLoopBackOff` | K8s `apps` + `pods` (core) |
| No orphaned drain | zero nodes stuck `SchedulingDisabled` with live pods | K8s `nodes` + `pods` |
| Removed-API fallout | nothing failing on an API removed in the target version | K8s events; route deep scan to `eks-upgrade-check` |
| Karpenter (if present) | provisioning on v1, new nodes at target version | `unconfirmed` if CRD 403 — flag, don't pass |

## Debug: failure-mode diagnosis table

Deterministic symptom → cause → action. A second agent given the same symptom must reach the
same row. Every action is an operator instruction; the skill does not execute it. Diagnostic
commands are given in the same `Operator runs (this skill does not):` format as Phase 2.

| Symptom | Most likely cause | Operator action + diagnostic (this skill instructs) |
|---------|-------------------|----------------------------------------|
| Control-plane update `FAILED` / stuck in `UPDATING` | Pre-flight condition missed (insufficient subnet IPs for control-plane ENIs, or a removed-API dependency) | `aws eks describe-update --name <cluster> --update-id <id>` to read the errors; resolve the named cause. If a post-upgrade control-plane regression **and within 7 days** (in-place cluster, not Fargate), the one-minor version rollback is available (version-only). |
| Node group update stuck; nodes won't drain | Drain-blocking PDB (`disruptionsAllowed==0`) or long `terminationGracePeriodSeconds` | `kubectl get pdb -A` (find `ALLOWED DISRUPTIONS 0`); identify the PDB/workload (Gate 5 should have caught it); relax the PDB for the window; **do not** force-delete pods blindly. |
| Drain or pod creation blocked with a webhook error (`failed calling webhook`, `admission webhook denied`) | A **validating/mutating admission webhook** (policy engine, service mesh injector) rejecting eviction/creation — a classic silent stuck-drain/stuck-schedule cause | `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`; check the failing webhook's backing pod is healthy on the new nodes; fix/relax `failurePolicy` or the webhook service before continuing. |
| New nodes join then go / stay `NotReady` | Add-ons not updated (Step 2), or a node-OS crossing (cgroup v1 on 1.35, containerd 1.x past 1.35, AL2 AMI on 1.33+) | `kubectl describe node <n>` + `kubectl -n kube-system get pods` (CNI/kube-proxy healthy?); verify Step 2 add-ons ran after the control-plane bump; for node-OS causes route to `eks-al2-to-al2023`. Do not delete old nodes while new ones are `NotReady`. |
| Fargate pods still on the old kubelet version after the control-plane bump | Fargate pods don't roll automatically — they pick up the new kubelet only when **recycled** | Restart/roll the Fargate deployments: `kubectl rollout restart deployment/<name>` (per the AWS "Restart Fargate deployments after upgrading the control plane" guidance). |
| Pods stuck `Pending` after node roll | Insufficient capacity / subnet IP exhaustion / EC2 vCPU-quota limit; Karpenter not provisioning (half-migrated to v1); **or unsatisfiable scheduling constraints** — `topologySpreadConstraints` with `whenUnsatisfiable: DoNotSchedule`, node affinity, or taints with no matching new node | `kubectl describe pod <p>` (read the FailedScheduling reason — it names the exact constraint); check free subnet IPs, EC2 vCPU quota, and Karpenter reconcile state; for a topology/affinity/taint block, confirm the new nodes carry the labels/taints the pods require. |
| CoreDNS/service resolution breaks post-upgrade | CoreDNS add-on version incompatible with the new control plane, or skipped in Step 2 | `kubectl -n kube-system get deploy coredns -o wide` + check the `kube-dns` service endpoints; update CoreDNS to the new-control-plane-compatible version. |
| A critical add-on `DEGRADED` after the control-plane bump | Add-on left at a pre-upgrade version (Law 4 — add-ons don't ride along) | `aws eks describe-addon --cluster-name <c> --addon-name <a>`; update it to the new-CP-compatible version; roll back to the prior version if the new one misbehaves. |
| Workload throwing `no matches for kind ...` / `apiVersion` errors | A removed API the workload/controller still calls | Migrate the manifest/chart to the supported apiVersion; route the exhaustive removed-API scan to `eks-upgrade-check`. |
| Any of the above but the driving fact is CRD-backed and unreadable | `AmazonAIOpsAssistantPolicy` grants no CRD groups → `403` | Report the fact `unconfirmed` with the supplementary-ClusterRole fix; never diagnose from a guess. |

## The rollback / cut-back decision

| Situation | Recovery path |
|-----------|---------------|
| Control-plane-level regression, **within 7 days**, single minor, **AND rollback preconditions met** | **EKS version rollback** (one minor, version-only — does not undo data-plane/add-on/data changes). **Preconditions:** cluster was **upgraded in place** (not created-at-version), the **prior minor is still EKS-supported**, and it is **not a Fargate** cluster (Fargate pods must be deleted first; Auto Mode reverts nodes too). **Coupling:** if the nodes already rolled to the higher kubelet on this hop (managed node groups / Auto Mode / any rolled data plane), the CP rollback is **not** clean — leaving kubelet ahead of the API server violates the skew policy (kubelet never leads), so you must **also roll the nodes back** (`UpdateNodegroupVersion` to the prior release; Auto Mode does it automatically). Only a **held / unmoved** data plane (self-managed hold-nodes) backs out CP-only. If any precondition fails, rollback is **not** available — see [upgrade-model.md](upgrade-model.md) → Rollback reality. |
| Karpenter **0.x→1.x migration failed / half-migrated** (Phase 2 Step 0) | **Do not proceed to the cluster upgrade.** Restore Karpenter to a consistent state first: if manifests were already converted to v1, roll the Karpenter controller back to the last-good 0.33+/v1-capable version and re-run the conversion; if webhooks are erroring, check the conversion-webhook pod health. The cluster K8s version is untouched at this point (Step 0 precedes Step 1), so there is no cluster rollback to do — the fix is Karpenter-local. |
| Data-plane problem, **in-place** mode | Roll the node group back to the **prior AMI/release version**; control plane stays. |
| Data-plane problem, **blue-green** mode | **Cut back** to the untouched old fleet — the fastest fallback; see [blue-green-mode.md](blue-green-mode.md). |
| Data loss / corruption (not a version issue) | Restore from the Phase 1 backup via `eks-backup` (data/objects only — not a version change). |
| Outside all windows / multi-minor jump already crossed / rollback preconditions unmet | No downgrade — **roll forward**: fix the failing component at the target version. |

## Tear-down gate (only after GREEN)

Do **not** dismantle fallback capacity until validation is GREEN:

| Condition | Action |
|-----------|--------|
| Validation checklist all GREEN | **Proceed** — decommission old nodes (in-place) or the old blue fleet (blue-green); note the 7-day control-plane rollback window closes on its own. |
| Any check RED / `unconfirmed`-and-material | **Hold tear-down** — keep the fallback; resolve via the diagnosis table first. Tearing down fallback on an unvalidated upgrade removes the cheapest recovery. |

## Post-upgrade housekeeping

After the tear-down gate is GREEN, the plan reminds the operator of two easily-missed follow-ups:

- **Re-tighten anything relaxed for the window.** Any PDB relaxed in Phase 1 Gate 5 (or a
  `failurePolicy` softened to clear a webhook) must be **restored** — leaving `disruptionsAllowed`
  wide open removes the availability guarantee for normal operations.
- **Reconcile IaC drift.** A console/CLI-driven upgrade drifts from Terraform/CDK/eksctl state
  (`cluster_version`, add-on versions, node-group release versions). Update the IaC to match so
  the next `plan`/`apply` doesn't try to revert the upgrade. (Route IaC detection to `eks-recon`.)

## Post-upgrade health companion

For a **full post-upgrade operational health / maturity audit** (GREEN/AMBER/RED across
reliability, security, scalability, observability, cost), see **`eks-operation-review`** *(when
built out — it is currently a stub)*. This advisor validates that the **upgrade** succeeded; it
does not produce a maturity rating. The advisor stands alone today: Phase 3's checklist is
self-contained and does not depend on that skill existing.

## Phase 3 exit contract

Phase 3 exits **DONE** only when the validation checklist is GREEN (or an `unconfirmed` item is
named in Coverage with its ClusterRole fix and the operator has accepted it). A failing check
routes to the diagnosis table and the rollback/cut-back decision; the fallback capacity is
retained until GREEN. The advisor's final report states the end state (version, node skew,
add-on health), the mode used, any coverage gaps, and — if triggered — the recovery path taken.
