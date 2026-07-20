---
name: eks-blue-green-readiness
description: >-
  EKS blue-green readiness pre-flight — a read-only GO / GO-WITH-CAVEATS / NO-GO
  gate for STANDING UP a green cluster before a blue-green cutover. Answers "is it
  safe to stand green up and cut over?" across four gates — green node-fleet IP
  capacity (shared-subnet contention with live blue), IRSA/OIDC re-point (green's
  NEW OIDC issuer breaks blue-scoped role trust policies), LB/DNS/TLS-cert cutover
  wiring, and stateful-data ownership (split-brain if both clusters write). Per-gate
  RED/AMBER/GREEN/unconfirmed rolls up to GO, GO-WITH-CAVEATS, NO-GO, or NO-GO
  (unconfirmed); unreadable stays unconfirmed, never false GREEN. Triggers on "stand
  up a green cluster", "blue-green readiness", "green cluster ready for cutover",
  "second cluster pre-flight". Read-only assessment; never acts. Route for the
  upgrade readiness score (eks-upgrade-check), the phased sequencer where
  blue-green is a mode (eks-upgrade-advisor), backup posture (eks-backup), AL2 to
  AL2023 mechanics (eks-al2-to-al2023), or inventory (eks-recon).
---

# EKS Blue-Green Readiness — DevOps Agent Port

## Overview

This skill is a **read-only GO/NO-GO pre-flight** for **standing up a green cluster** in a
blue-green migration or upgrade. It answers one question: *"Is it safe to stand a second (green)
cluster up alongside blue and cut traffic over to it?"* It connects via read-only AWS
control-plane APIs and the Kubernetes API, runs **four cutover-readiness gates**, and emits a
single verdict — **GO** / **GO-WITH-CAVEATS** / **NO-GO** / **NO-GO (unconfirmed)** — backed by a
deterministic **RED / AMBER / GREEN / unconfirmed** per-gate roll-up and the per-gate evidence
behind it.

Its unique lane is the **cutover safety** of a *parallel-cluster* topology: the four things that
silently break when a whole second cluster is stood up next to a live one — **green node-fleet IP
capacity** in the shared subnets, the **new OIDC issuer** that invalidates every blue-scoped IRSA
trust policy, the **load-balancer / DNS / TLS-cert wiring** that does not span two clusters, and
**shared stateful data** that two clusters cannot both own. It does **not** score Kubernetes-
version upgrade readiness, sequence the upgrade, assess backup tooling, or re-inventory the
cluster — those belong to the sibling skills (see *When to Use*).

> **This is a pre-flight, not an execution plan.** It tells you whether green is *safe to stand
> up and cut over*, gate by gate. It does **not** emit the ordered "do X then Y" cutover runbook
> — that phased execution sequencer is `eks-upgrade-advisor` (where blue-green is one **mode**).
> And it does **not** produce the 0–100 version-readiness score — that is `eks-upgrade-check`.
> This skill sits **beside** both: the specific pre-flight for the *parallel-cluster* shape.

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. It proceeds through discovery and gating without pausing for
> user input. When the target cluster is ambiguous (multiple clusters, none named),
> it assesses **all** discovered clusters as candidate blue clusters. When a
> non-recoverable error occurs (API permission failure, no clusters found), it logs
> the error in the report and terminates per the Step 0 decision table.

## Prerequisites

### Required IAM Permissions (Agent Space Role)

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](references/iam-policy.json) — attach it directly to your Agent Space execution role. It grants **read-only AWS control-plane access** (EKS/EC2/ELB/Route 53/ACM `Describe`/`List`/`Get`). It intentionally does **not** grant `eks:AccessKubernetesApi` — Kubernetes-API authentication is handled by the access entry below, not by IAM.

| Service | Actions (read-only) | Purpose |
|---------|--------------------|---------|
| **EKS** | `ListClusters`, `DescribeCluster`, `ListNodegroups`, `DescribeNodegroup`, `ListAddons`, `DescribeAddon`, `ListAccessEntries`, `ListAssociatedAccessPolicies`, `ListPodIdentityAssociations` | Blue cluster config, `authenticationMode`, current OIDC issuer, node groups, VPC CNI add-on, the access model, and **Pod Identity associations** (to confirm a workload really uses Pod Identity vs IRSA — Gate 2) |
| **EC2** | `DescribeInstances`, `DescribeSubnets`, `DescribeVpcs`, `DescribeLaunchTemplates`, `DescribeLaunchTemplateVersions`, `DescribeImages` | Green node-fleet **subnet free-IP capacity**, **VPC secondary-CIDR association** (`DescribeVpcs` `CidrBlockAssociationSet`), CNI/ENI prefix-delegation facts, launch-template/AMI facts (Gate 1) |
| **IAM** | `iam:GetRole` | Read IRSA role **trust policies** to see which are scoped to blue's OIDC issuer and need re-pointing for green (Gate 2) |
| **KMS** | `kms:DescribeKey`, `kms:GetKeyPolicy` | Envelope-encryption key facts when green must reuse or re-grant a CMK (Gate 2/Gate 4 support) |
| **Elastic Load Balancing** | `elasticloadbalancing:Describe*` | Target groups / listeners / target health — blue's LB targets point at blue's nodes; green needs its own (Gate 3) |
| **Route 53** | `route53:ListHostedZones`, `route53:ListResourceRecordSets`, `route53:GetHostedZone` | Cutover DNS records + TTL (bleed window) for the cutover hostname (Gate 3) |
| **ACM** | `acm:ListCertificates`, `acm:DescribeCertificate` | Whether an ACM cert covers the cutover hostname for green's new endpoint (Gate 3) |

### Kubernetes API Access (via Agent Space Access Entry)

Kubernetes-API facts (IRSA-consuming ServiceAccounts, StatefulSets + bound PVs, workload health) are read through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy at **cluster scope**. This is provisioned by `devops-agent/setup.sh` (or manually — see the project README "EKS Access Setup").

- The cluster's `authenticationMode` **must include `API`** (i.e. `API` or `API_AND_CONFIG_MAP`). A `CONFIG_MAP`-only cluster cannot be reached via the access entry.
- The access entry (not an IAM action) provides the K8s-API **authentication**; the `AmazonAIOpsAssistantPolicy` provides the **authorization** (RBAC).
- **What `AmazonAIOpsAssistantPolicy` actually authorizes (read-only get/list):** built-in API groups only — core (`pods`, `pods/log`, `services`, `nodes`, `namespaces`, `events`, `persistentvolumes`, `persistentvolumeclaims`, `configmaps`), `apps` (deployments/replicasets/statefulsets/daemonsets), `batch` (jobs/cronjobs), `events.k8s.io`, `networking.k8s.io` (Ingress), `storage.k8s.io`, and `metrics.k8s.io`. **It grants NO CustomResourceDefinition groups** (and not `apiextensions.k8s.io`). **`serviceaccounts` and `secrets` are NOT in the readable core set** (verify against the authoritative RBAC list: [CloudWatch/EKS integration](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/EKS-Integration.html), as of 2026-07-20) — reads of either return `403 Forbidden` under the plain policy.
- **Consequence for CRD-based facts.** Anything on a CRD group is **not** authorized: an `IngressClassParams`/`TargetGroupBinding` (`elbv2.k8s.aws`) from the AWS Load Balancer Controller, an `external-dns` CRD, a `karpenter.sh`/`karpenter.k8s.aws` NodePool, or a storage-operator CRD all return `403 Forbidden`. Any such CRD-sourced fact is reported **`unconfirmed`** with the reason (and the supplementary-ClusterRole fix in `references/porting-notes.md`), **never** as "absent" / "GREEN" / `false`. An `unconfirmed` gate input is treated as **not-GREEN**.
- **Consequence for Gate 2 (ServiceAccount enumeration).** Because `serviceaccounts` is **not** in the readable core set (above), Gate 2's IRSA enumeration by reading the ServiceAccount `eks.amazonaws.com/role-arn` annotation **cannot** be performed under the plain policy — those reads `403`, exactly like a CRD-blocked fact. Under the plain policy alone Gate 2 is therefore **`unconfirmed`** (never a false "no IRSA" / GREEN). The documented fix is the same supplementary read-only ClusterRole used for the CRD facts, which **adds `serviceaccounts` (core group, get/list)** — see `references/porting-notes.md`. With it, the SA-annotation enumeration resolves; without it, Gate 2 stays `unconfirmed`.

> **Availability hedge.** When the access entry is absent (or `authenticationMode` excludes `API`), the skill **degrades gracefully to AWS-control-plane-only facts** — it still gates from subnet free-IP capacity, the OIDC issuer URL, IAM trust policies, ELB/Route 53/ACM facts, and node-group config, all readable via the AWS API alone. Each K8s-API-dependent input that cannot be read (IRSA ServiceAccount enumeration, StatefulSet/PV data shape) is recorded as `unavailable`/`unconfirmed` in the report's Coverage section, **never** as a false negative — and no gate is green-lit on a fact the skill could not inspect.

## When to Use

**Activate when the goal involves:**
- Standing up a **green (second) cluster** and deciding whether it is safe to cut over — "stand up a green cluster", "is my green cluster ready for cutover", "second cluster pre-flight", "blue-green readiness"
- Pre-flighting the **parallel-cluster** cutover surface: green IP capacity, OIDC/IRSA re-point, LB/DNS/cert cutover, shared stateful data
- Getting a **GO / GO-WITH-CAVEATS / NO-GO / NO-GO (unconfirmed)** verdict (from a RED/AMBER/GREEN/unconfirmed per-gate roll-up) before provisioning green

**Out of scope — route elsewhere:**
- **Kubernetes-version upgrade readiness scoring / the 0–100 score / deprecated-API blocking** → `eks-upgrade-check`. That is path-agnostic version readiness; it has no blue-green content, and that is correct. This skill does not re-score it.
- **The phased upgrade *execution* plan / ordered cutover runbook** — where **blue-green is one mode** among in-place rolling → `eks-upgrade-advisor`. That skill *sequences* the work (Karpenter → control plane → add-ons → nodes) and owns the cutover/cut-back runbook. This skill is the **pre-flight** that decides whether green is safe to stand up; it does not sequence the execution.
- **Backup / recovery posture** and the data-movement mechanics for a stateful cutover → `eks-backup`. Gate 4 *routes to it* for the restore/replication mechanics; it does not assess backup tooling.
- **AL2 → AL2023 node-OS migration mechanics** (nodeadm/NodeConfig, cgroup v2, IMDS hop limit, VPC CNI floor) → `eks-al2-to-al2023`.
- **Raw cluster inventory / "what am I running"** → `eks-recon`.
- Actually standing green up, registering targets, cutting over DNS, or moving data (this skill is strictly read-only).

---

## Readiness Workflow

**Error output format** (used by the Step 0 hard-stops):

```
## Blue-Green Readiness Error — <one-line reason>
**Condition:** <which check failed>
**What was found:** <observed state>
**Recommendation:** <remediation guidance for next run>
```

### Step 0: Pre-flight — Topology Intent, Cluster Discovery, and Validation

**Action 0 — Confirm this is a blue-green topology (runtime decline gate).** This skill gates the
safety of **standing up a green (second) cluster** and cutting over to it. Before any discovery or
gating, confirm there is a **green-standup intent**: the request is to stand up / cut over to a
*second* cluster (green), not to upgrade a cluster **in place**.

| Condition | Action |
|-----------|--------|
| Request is an **in-place** upgrade (rolling nodes / control-plane bump on the *same* cluster), or no second/green cluster is being stood up, or the intent is "upgrade my cluster" / "am I ready to upgrade" with no parallel-cluster signal | **Decline — emit "N/A — not a blue-green topology"** and **SKIP all four gates.** Do not score. State: "This is not a green-standup / cutover pre-flight. Route to `eks-upgrade-check` for the version-readiness score, or `eks-upgrade-advisor` for in-place upgrade execution." Terminate without a GO/NO-GO. |
| Request is (or is ambiguous but consistent with) **standing up a green/second cluster** and cutting over to it | **Proceed** to Action 1. |

This is a genuine runtime path, not just router prose: when pointed at an in-place cluster, the
skill must **decline and skip gating** rather than emit a meaningless green-standup GO/NO-GO.

**Action 1 — Discover clusters.** Use the EKS ListClusters API to discover available clusters in the target region. The discovered cluster(s) are the candidate **blue** (source) cluster.

| Condition | Action |
|-----------|--------|
| API call fails (auth/permission error) | **Abort with error** — log "Cannot access EKS. The agent role requires `eks:ListClusters` for the configured region." and terminate. |
| Zero clusters returned | **Abort with error** — log "No EKS clusters found in this region." and terminate. |
| Exactly one cluster found, none named in request | **Proceed** — treat it as blue; state which cluster was auto-selected. |
| Multiple clusters found, one named in request | **Proceed** — use the named cluster as blue. |
| Multiple clusters found, none named in request | **Proceed** — pre-flight **all** discovered clusters as candidate blue. Note in the report that no specific cluster was targeted. |

**Action 2 — Describe the selected (blue) cluster.** Use DescribeCluster. Extract name, Kubernetes version, region, status, `authenticationMode`, the **OIDC issuer URL** (`identity.oidc.issuer`), subnet IDs, and `encryptionConfig`. The OIDC issuer is the anchor for Gate 2.

| Cluster Status | Action |
|----------------|--------|
| `ACTIVE` | **Proceed** |
| `CREATING` / `UPDATING` | **Note and proceed with a caveat** — blue is mid-change; facts are point-in-time. Record it in Coverage. |
| `DELETING` / `FAILED` | **Skip cluster** — log the state. If it is the only cluster, terminate with error report. |
| `PENDING` / any other non-`ACTIVE` status | **Do not gate** — the cluster is not in a readable steady state; record the observed status in Coverage and treat every gate input for it as `unconfirmed` (not-GREEN, never a false GREEN). If it is the only cluster, terminate with an error report noting the non-ACTIVE status. |

**Action 3 — Probe Kubernetes API reachability.** Attempt one lightweight K8s-API read (list nodes). If it fails (access entry absent, `authenticationMode` excludes `API`, or 401/403), **do not abort** — set `k8s_api_available: false`, gate from AWS-control-plane facts, and record every K8s-dependent gate input as `unavailable`/`unconfirmed` in Coverage. No gate is green-lit on a cluster it could not inspect.

### The four gates

Load `references/readiness-model.md` **first** — it defines the gate vocabulary and the roll-up
combinator. Then run the four gates, each in its own reference:

| Gate | Question | Reference |
|------|----------|-----------|
| **Gate 1 — Green IP capacity** | Do the shared subnets hold a *whole second* node fleet while blue is still live? | [gate-1-green-ip-capacity.md](references/gate-1-green-ip-capacity.md) |
| **Gate 2 — OIDC / IRSA re-point** | Green has a NEW OIDC issuer — which IRSA trust policies break? | [gate-2-oidc-irsa.md](references/gate-2-oidc-irsa.md) |
| **Gate 3 — LB / DNS / cert cutover** | Are LB targets, DNS records + TTL, and the TLS cert ready for green's endpoint? | [gate-3-lb-dns-cert-cutover.md](references/gate-3-lb-dns-cert-cutover.md) |
| **Gate 4 — Stateful data** | Can both clusters run without split-brain? Who owns the datastore? | [gate-4-stateful-data.md](references/gate-4-stateful-data.md) |

Each gate resolves to exactly one of **GREEN** / **AMBER** / **RED** / **unconfirmed** (defined in
`readiness-model.md`). The overall verdict is the **deterministic roll-up** of the four (any RED →
NO-GO; any unconfirmed → not-GREEN; see the combinator in `readiness-model.md`).

---

## How to Use the References

Load `references/readiness-model.md` **first** — it carries the gate vocabulary and the roll-up
combinator every gate feeds. Then load the gate file(s) the request needs.

| Intent / when to use | Reference file |
|----------------------|----------------|
| Always first — what green-readiness means, the 4 gates at a glance, the RED/AMBER/GREEN/unconfirmed roll-up combinator | [readiness-model.md](references/readiness-model.md) |
| Green node-fleet IP capacity: shared-subnet aggregate contention, secondary CIDR, prefix delegation | [gate-1-green-ip-capacity.md](references/gate-1-green-ip-capacity.md) |
| OIDC/IRSA: new issuer, trust-policy re-point, Pod Identity alternative | [gate-2-oidc-irsa.md](references/gate-2-oidc-irsa.md) |
| Cutover wiring: LB target (de)registration, DNS + TTL bleed, TLS cert coverage | [gate-3-lb-dns-cert-cutover.md](references/gate-3-lb-dns-cert-cutover.md) |
| Shared stateful data: ownership, split-brain, external vs in-cluster store | [gate-4-stateful-data.md](references/gate-4-stateful-data.md) |

Each reference describes assessment **declaratively** as capability blocks (AWS API calls, and
"**Via Kubernetes API**" blocks for K8s resources). There is no Agent tool and no subagents in
this environment — analysis isolation is achieved by loading one reference at a time, not by
spawning subagents.

---

## Report Output

Produce **one** artifact — the pre-flight report. The agent generates it directly, with no
external conversion tools or scripts.

The report structure below is a **contract**: emit these sections in this order, and include a
section even if empty (write "none detected" / "unconfirmed" rather than omitting it) so a reader
can trust that a missing item means "assessed and absent," not "skipped."

- **Filename:** `EKS-BlueGreen-Readiness-{cluster}-{YYYY-MM-DD}-{HHMM}.md`

```markdown
# EKS Blue-Green Readiness — <blue cluster> (<region>)
_generated <timestamp> · source: AWS API + K8s API · standing up a green cluster_

## Verdict: GO | GO-WITH-CAVEATS | NO-GO | NO-GO (unconfirmed)
<one-line rationale from the roll-up combinator; if GO-WITH-CAVEATS, list the AMBER caveats the
operator must accept; if NO-GO, the blocking gate(s); if any input is unconfirmed, say so — an
unconfirmed gate is never GREEN>

## Gate results (roll-up)
| Gate | Result | Evidence / routed-to |
|------|--------|----------------------|
| 1 Green IP capacity | AMBER | subnet-a 42 free, subnet-b 9 free (5–15 band); prefix delegation off |
| 2 OIDC / IRSA re-point | RED | 6 IRSA ServiceAccounts scoped to blue's issuer; all need green re-point |
| 3 LB / DNS / cert cutover | unconfirmed | TargetGroupBinding CRD read 403 — supplementary ClusterRole needed |
| 4 Stateful data | RED | in-cluster StatefulSet on gp3, no cross-cluster story — split-brain risk |

## Notable facts
<flat neutral bullets — blue OIDC issuer URL, node-subnet free IPs, IRSA SA count, cutover
hostname/TTL, stateful data shape>

## Coverage
<facts that could not be confirmed + reason — never a false negative>
- gate3.lb_targets: unconfirmed (elbv2.k8s.aws TargetGroupBinding CRD read 403 under AmazonAIOpsAssistantPolicy)
```

---

## Read-Only Guardrails

1. **Assess — never act.** This skill reads facts and emits a GO/NO-GO pre-flight. It never creates a cluster, registers a target, changes a DNS record, re-points a trust policy, or moves data.
2. **Pre-flight, not sequencer or scorer.** It decides whether green is *safe to stand up and cut over*. It does not sequence the upgrade execution (that is `eks-upgrade-advisor`, where blue-green is a mode) and does not produce the version-readiness score (that is `eks-upgrade-check`).
3. **Cite the source and date for every capability/limit claim.** The OIDC-issuer-is-new fact, Pod Identity as the OIDC-sidestep, prefix-delegation IP math, and the stateful-cutover constraint each carry a source URL and "as of 2026-07-20" in the gate files. Do not assert from memory.
4. **Distinguish absence from unconfirmed.** A CRD read (`elbv2.k8s.aws` TargetGroupBinding, external-dns, Karpenter) that returns `403`, or an unreadable IAM trust policy / ELB / Route 53 / ACM fact, is `unconfirmed` (with the reason + the fix), **never** "GREEN / no IRSA / no LB / stateless". A material `unconfirmed` gate is treated as **not-GREEN**.
5. **Never green-light a gate you could not inspect.** If the K8s API is unreachable, or a gate input is `unconfirmed`, the roll-up is **not GREEN** and the gap is named in Coverage.
6. **Never emit a false negative.** Blocked / unreadable = `unconfirmed` = not-GREEN. Absence is only reported when a successful read confirmed it.
7. **Do NOT hardcode or guess cluster names.** Discover via ListClusters first (Step 0).
8. **Do NOT retry a failed API call more than once.** If it fails twice, record the gap in Coverage and continue.

---

*This skill is provided as sample code for educational and demonstration purposes only. Findings are point-in-time and should be validated before acting on them. Blue-green cutover procedures must be reviewed and tested in a non-production environment first. See the project's README and LICENSE for full terms.*
</content>
</invoke>
