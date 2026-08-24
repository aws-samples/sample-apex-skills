# Add-on & Component Management

## Purpose
Assess add-on management maturity, node health monitoring, and cluster insights usage.

## Checks to Execute

### 10.1 — Core Add-ons Managed via EKS Managed Add-ons

**What to check:**
- All EKS managed add-ons: name, version, status, health
- Compare installed versions against latest compatible for the cluster version
- Self-managed add-ons in kube-system (Helm releases)
- Deprecated in-tree EBS plugin usage

**How to check:**
1. List addons → describe each for version, status, health issues
2. For each of the 4 core add-ons (vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver):
   - Check if installed as managed add-on
   - Compare installed version vs latest compatible
3. List PersistentVolumes → check for `spec.awsElasticBlockStore` (deprecated in-tree)

**Rating:**
- **Evidence-only — no independent GREEN/AMBER/RED here.** Collect add-on inventory, versions, managed-vs-self-managed status, health, and deprecated in-tree plugin usage as supporting evidence, then route each signal to the check that owns and scores it:
  - Add-on inventory, version currency, managed-vs-self-managed status, and add-on **health status** → rated under check **1.4 (Add-on Version Compatibility)**, which owns add-on version compatibility scoring and whose RED band is health-driven.
  - Deprecated in-tree storage plugin usage (`spec.awsElasticBlockStore` on PersistentVolumes) → rated under check **5.5 (Persistent Volume & Stateful Workload Configuration)**, which owns the deprecated-in-tree-storage signal and has the RED band that scores it.

**Key talking point:** EKS does NOT auto-update add-ons when you upgrade the control plane. Clusters upgraded to 1.31 still running vpc-cni from 1.27 is a ticking time bomb.

---

### 10.2 — Node Health Monitoring & Auto-Repair

**What to check:**
- EKS Auto Mode (cluster `computeConfig`) — node health monitoring and auto-repair are built in for Auto-Mode-managed nodes; enabled by default.
- Node auto-repair — available on THREE compute types, each with its own control surface:
  - **EKS managed node groups** — `nodeRepairConfig` on the node group (`describe-nodegroup`; enable via `update-nodegroup-config --node-repair-config enabled=true`).
  - **Karpenter-managed nodes** — the Karpenter `NodeRepair=true` feature gate, set on the Karpenter controller Deployment via the `--feature-gates` CLI arg or the `FEATURE_GATES` env var (alpha in open-source Karpenter v1.1+). This is inspectable, so auto-repair IS assessable for Karpenter — the same way `nodeRepairConfig` is for managed node groups.
  - **EKS Auto Mode** — native, always on.
  - **Self-managed node groups (plain ASGs)** are the ONLY compute type with no auto-repair mechanism, so its absence is not held against them.
- EKS Node Monitoring Agent add-on (`eks-node-monitoring-agent`, NMA) — a DaemonSet that runs on any EKS **Linux** compute EXCEPT AWS Fargate: managed node groups, self-managed node groups, and Karpenter-managed nodes. (Not needed on Auto-Mode-managed nodes, which are covered natively; not available on Windows nodes — NMA and auto-repair are Linux-only.) NMA + auto-repair together react to extra node conditions (AcceleratedHardwareReady / ContainerRuntimeReady / KernelReady / NetworkingReady / StorageReady).
- Compute topology — which compute types the cluster actually uses (Auto Mode, managed node groups, self-managed node groups, Karpenter, Fargate), so the health-coverage expectation is keyed to what each type supports.
- Fargate — NMA and auto-repair are NOT applicable to AWS Fargate; Fargate compute is **N/A** for this check.
- Windows — the node monitoring agent and node auto-repair are **Linux-only**; AWS does not offer them on Windows (node-health.html Important callout: "The node monitoring agent and node auto repair are only available on Linux. These features aren't available on Windows."). Windows nodes (managed, self-managed, or Karpenter) are therefore **N/A** for this check — their lack of NMA/auto-repair is a capability AWS does not provide, never a finding.
- GPU nodes (need NMA for GPU/accelerator failure detection, which auto-repair alone does not catch).

**How to check:**
1. Describe cluster → check `computeConfig` for Auto Mode (`computeConfig.enabled == true`). Auto Mode manages node health monitoring and auto-repair for its own Auto-Mode-managed nodes natively. Auto Mode can coexist with other compute (mixed mode), so a cluster may be Auto Mode AND still have node-group / Karpenter / Fargate nodes — do not assume Auto Mode means nothing else is present.
2. Detect compute types by **per-node labels** — NOT by trying to enumerate self-managed groups from `list-nodegroups`, which returns ONLY EKS-managed node groups and therefore never surfaces self-managed ASGs. **If the node list / per-node label read returns 403 / Forbidden, the compute-topology dimension is UNKNOWN — report it as unconfirmed under Investigate Manually and do NOT let unread nodes fall through the else-branch (step f) to `self-managed`, which would manufacture a false RED out of a permissions failure.** Classify each successfully-read node with this decision tree, evaluated **in order** so every node lands in exactly one type. Two ordering rules: (i) the Windows OS gate (step a) is tested FIRST because the node monitoring agent and node auto-repair are **Linux-only** (see the Important callout in node-health.html) — a Windows node is N/A for this check regardless of which compute type provisioned it; (ii) EKS Auto Mode is built ON Karpenter and serves the same `karpenter.sh` API group, so Auto-Mode nodes ALSO carry `karpenter.sh/nodepool`, and the Auto-Mode compute-type label must be tested before the Karpenter label to keep Auto-Mode and self-managed-Karpenter nodes distinct:
   - a. Node carries `kubernetes.io/os=windows` (or the deprecated `beta.kubernetes.io/os=windows`; note `node.kubernetes.io/os` is NOT a well-known Kubernetes label) → **Windows** node → **N/A**. NMA and node auto-repair are Linux-only, so a Windows managed / self-managed / Karpenter node is excluded from NMA/auto-repair scoring, exactly as Fargate is. (Auto Mode and Fargate never run Windows, so this gate cannot mis-catch them.)
   - b. Else node carries `eks.amazonaws.com/compute-type=auto` → **Auto Mode** node (native health monitoring + auto-repair).
   - c. Else node carries `eks.amazonaws.com/nodegroup` → **EKS managed node group** node.
   - d. Else node carries `karpenter.sh/nodepool` (and did NOT match step b) → **open-source (self-managed) Karpenter** node.
   - e. Else the node name is prefixed `fargate-` (the authoritative Fargate discriminator; the observed node label `eks.amazonaws.com/compute-type=fargate` is not formally documented as a node label — AWS documents `eks.amazonaws.com/compute-type: fargate` as a node taint) → **Fargate** (N/A).
   - f. Else → **self-managed** node group (plain ASG).
3. Confirm Karpenter API presence: query the `nodepools.karpenter.sh` CRD (`kubectl get nodepools.karpenter.sh`). 404 / NotFound → the karpenter.sh API is not served; a returned list → the API is served; 403 / Forbidden → the CRD read is undetermined, and whether that undetermined read is a *scored* dimension depends on the successful step-2 node-label sweep: **if the node-label sweep showed at least one Karpenter node** (`karpenter.sh/nodepool` and not Auto Mode), Karpenter is a compute type the cluster actually uses, so a 403 here makes the Karpenter auto-repair dimension UNKNOWN (report unconfirmed; caps GREEN per the aggregation rule); **if the node-label sweep showed ZERO Karpenter nodes**, the cluster does not use open-source Karpenter and a 403 on the Karpenter CRD is **NOT a scored dimension** — note it under Investigate Manually and do NOT let it block GREEN (a healthy MNG-only cluster must stay reachable to GREEN even when the Karpenter CRD read 403s, which is the default posture where the managed access policy grants no CRD groups). (Only if the node-label sweep *itself* 403'd is the whole compute topology UNKNOWN — step 2.) CRD presence alone only tells you the `karpenter.sh` API group is served — it does NOT prove open-source Karpenter, because EKS Auto Mode serves the same CRD. Whether a `karpenter.sh/nodepool` node is Auto Mode or self-managed Karpenter is decided by the per-node `eks.amazonaws.com/compute-type=auto` label (step 2b), not by CRD presence.
4. Determine NMA presence once for the cluster: describe addon `eks-node-monitoring-agent` (or check for its DaemonSet). NMA covers managed, self-managed, and Karpenter **Linux** nodes (not Fargate, not Windows, not needed on Auto Mode). If this read returns 403 / Forbidden, the NMA dimension is UNKNOWN (report unconfirmed under Investigate Manually; do NOT treat unreadable as absent → a false RED/AMBER).
5. Gather auto-repair evidence per compute type that supports it. **Any of these reads that returns 403 / Forbidden makes that compute type's auto-repair dimension UNKNOWN, not failing — surface as unconfirmed, never as RED/AMBER:**
   - **Managed node groups:** `describe-nodegroup` → `nodeRepairConfig` enabled?
   - **Karpenter:** inspect the Karpenter controller Deployment for the `NodeRepair=true` feature gate (`--feature-gates` arg or `FEATURE_GATES` env var). Present-and-true → auto-repair on.
   - **Self-managed node groups:** no auto-repair mechanism exists — nothing to gather.
   - **Auto Mode / Fargate:** not applicable (Auto Mode native; Fargate has no nodes to repair).
6. List nodes → check for `nvidia.com/gpu` (or other accelerator) in capacity (GPU nodes).

**Rating:**
Assess each compute type the cluster actually uses. A cluster may mix several types. Evaluate each present type RED-first → AMBER → GREEN using only the evidence that type supports. The overall band is the **worst of the determinable per-compute-type assessments** — see the aggregation rule below for how N/A and UNKNOWN dimensions are handled.
- 🟢 **Auto Mode nodes** — native health monitoring + auto-repair, no NMA add-on needed → GREEN for those nodes.
- **Managed node groups** — expect BOTH `nodeRepairConfig` (auto-repair) enabled AND NMA present (NMA also catches accelerator/GPU faults auto-repair misses):
  - 🔴 RED: neither present (especially with GPU workloads).
  - 🟡 AMBER: exactly one present — auto-repair without NMA, or NMA without auto-repair.
  - 🟢 GREEN: both auto-repair and NMA present.
- **Karpenter-managed nodes** — auto-repair IS available here via the `NodeRepair=true` feature gate, so assess it exactly like managed node groups: expect BOTH the `NodeRepair=true` feature gate AND NMA present:
  - 🔴 RED: neither present (especially with GPU workloads).
  - 🟡 AMBER: exactly one present — feature gate without NMA, or NMA without the feature gate.
  - 🟢 GREEN: both the `NodeRepair=true` feature gate and NMA present.
- **Self-managed node groups** — the ONLY compute type with no auto-repair mechanism, so its absence is NOT held against them; the expectation is the NMA DaemonSet alone:
  - 🔴 RED: NMA absent (especially with GPU workloads).
  - 🟢 GREEN: NMA present.
- ⬜ **Fargate compute — N/A.** NMA and auto-repair are not applicable to AWS Fargate; Fargate is excluded from scoring. A cluster that is ENTIRELY Fargate rates **N/A** for 10.2. In a mixed cluster, Fargate contributes nothing to the worst-of; only the non-Fargate compute types are assessed.
- ⬜ **Windows nodes — N/A.** The node monitoring agent and node auto-repair are **Linux-only** (node-health.html Important callout: "The node monitoring agent and node auto repair are only available on Linux. These features aren't available on Windows."), so Windows nodes — whether managed, self-managed, or Karpenter — are excluded from NMA/auto-repair scoring exactly like Fargate. A cluster whose only in-scope nodes are Windows (and/or Fargate) rates **N/A** for 10.2. In a mixed cluster, Windows nodes contribute nothing to the worst-of; only the Linux non-Fargate compute types are assessed. Do NOT rate a Windows node set RED/AMBER for lacking a capability AWS does not offer it.
- ⬜ **UNKNOWN (per dimension):** a dimension whose evidence could not be read with live access (e.g., the Karpenter feature-gate/CRD read returned 403). It is neither GREEN nor a failure — it is undetermined. Surface it under **Investigate Manually**.
- **Aggregation rule (decidable for every combination):** rank the per-compute-type bands RED > AMBER > GREEN.
  1. **A dimension is only SCORED for a compute type the cluster ACTUALLY USES** — presence is read from the successful step-2 node-label sweep. A 403 on evidence for a compute type that has ZERO nodes in that sweep (e.g. a Karpenter-CRD 403 on a cluster whose node labels show no Karpenter nodes) is NOT a scored dimension: note it under Investigate Manually and do not let it block GREEN. Only a compute type present on actual nodes contributes a dimension (and a 403 on *its* evidence → UNKNOWN → caps GREEN). (This gating presumes the node-label sweep itself SUCCEEDED; if that sweep 403'd, the whole compute topology is UNKNOWN per step 2.)
  2. **Determinable** dimensions are those that resolved to RED, AMBER, or GREEN. N/A (e.g., Fargate, Windows) and UNKNOWN dimensions are NOT determinable. **N/A and UNKNOWN are not equivalent for aggregation:** an N/A dimension is legitimately excluded (AWS offers the capability on no in-scope node of that type), whereas an UNKNOWN dimension is a scored dimension (a compute type the cluster uses) whose evidence a forbidden read (403) hid — its band could be anything, including RED.
  3. If at least one dimension is determinable, the **overall band = the worst determinable band** (RED beats AMBER beats GREEN), with one guard: **a UNKNOWN dimension blocks an overall GREEN.** So if the worst determinable band is GREEN but any scored dimension is UNKNOWN, the overall is capped at **AMBER** (with the unverified dimension named under Investigate Manually) — never GREEN, because a 403-hidden dimension may itself be RED. A confirmed RED or AMBER determinable dimension still sets the overall via worst-of as normal (an UNKNOWN never *lowers* an already-worse band). N/A dimensions — and 403s on compute types not present on any node (per sub-item 1) — are simply excluded and do NOT block GREEN; only a 403-driven UNKNOWN on a compute type the cluster actually uses does. Overall GREEN therefore requires that every scored dimension be determinable AND GREEN (N/A and not-present-compute-type dimensions aside).
  4. If NO dimension is determinable, then: if at least one dimension is UNKNOWN (all others N/A), the overall check is **UNKNOWN** (report unconfirmed under Investigate Manually). If every dimension is N/A (e.g., an entirely-Fargate cluster, an all-Windows cluster, or a mix of only Fargate + Windows), the overall check is **N/A**.
  This yields exactly one overall result for every combination of {GREEN / AMBER / RED / N/A / UNKNOWN} across dimensions.
- **Evaluation order:** first map the compute topology per node with the step-2 decision tree, evaluated in order — a. Windows via `kubernetes.io/os=windows` → N/A FIRST, since NMA/auto-repair are Linux-only; b. Auto Mode via `eks.amazonaws.com/compute-type=auto`; c. managed via `eks.amazonaws.com/nodegroup`; d. open-source Karpenter via `karpenter.sh/nodepool`; e. Fargate via the authoritative node-name prefix `fargate-` (the `eks.amazonaws.com/compute-type=fargate` label is NOT a documented node label — AWS documents it as a node taint — so it must not be used as the Fargate discriminator; a Fargate node lacking that label must still be caught as N/A via the name prefix, never fall through to self-managed); f. else self-managed — and note that `nodepools.karpenter.sh` CRD presence only confirms the `karpenter.sh` API is served (Auto Mode serves it too) — it does not by itself prove open-source Karpenter, and a Karpenter-CRD 403 is a scored UNKNOWN only when the node sweep actually found Karpenter nodes (else note under Investigate Manually, does not block GREEN). Then assess each present, in-scope compute type with RED-first → AMBER → GREEN precedence using only the evidence that type supports: Auto-Mode nodes are natively GREEN; managed node groups are scored on `nodeRepairConfig` AND NMA; open-source Karpenter nodes are scored on the `NodeRepair=true` feature gate AND NMA; self-managed nodes are scored on NMA alone; Fargate and Windows are N/A. Apply the aggregation rule above to reach the overall band. Never rate a mixed cluster GREEN on the strength of `computeConfig.enabled == true` alone, never require auto-repair on the one compute type (self-managed) that cannot provide it, and never rate Windows nodes RED/AMBER for lacking Linux-only NMA/auto-repair. Keeps the bands exhaustive and non-overlapping.

---

### 10.3 — EKS Cluster Insights Reviewed

**What to check:**
- All cluster insights with status
- Count by status (PASSING, WARNING, ERROR)
- Details on any ERROR or WARNING insights

**How to check:**
1. Get EKS Insights for the cluster
2. For any non-PASSING insights → get detailed description and recommendation

**Rating:**
- **Evidence-only — rated under check 1.3 (Upgrade Readiness & Deprecated API Detection).** Collect the cluster insights and their statuses as supporting evidence, but do not assign an independent GREEN/AMBER/RED here; the upgrade-readiness / insights rating is owned by check 1.3.
