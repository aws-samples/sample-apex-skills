---
title: "Networking"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/references/networking.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-operation-review/references/networking.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/references/networking.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [eks-operation-review](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review), also maintained by the APEX team.
:::

# Networking

## Purpose
Assess VPC CNI configuration, IP capacity, DNS health, and network segmentation.

## Checks to Execute

### 6.1 — VPC and Subnet IP Capacity

**What to check:**
- Subnets used by the cluster and available IP count
- VPC CNI configuration: prefix delegation, custom networking, WARM_IP_TARGET
- Current pod count vs IP capacity
- VPC CNI add-on version

**How to check:**
1. Describe cluster → get subnet IDs from `resourcesVpcConfig.subnetIds`
2. Get VPC config for the cluster (available IPs per subnet)
3. List pods (Running) → count total
4. List nodes → count total
5. Describe addon `vpc-cni` → check version and configuration
6. Check DaemonSet `aws-node` in kube-system → inspect env vars for `ENABLE_PREFIX_DELEGATION`, `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG`. If 403/Forbidden when reading the aws-node DaemonSet → mark the prefix-delegation signal UNKNOWN (do not conclude it is disabled, and do not conclude it is enabled). Prefix delegation and custom networking are the two "good" signals feeding the GREEN precondition (see Rating): a >30%-headroom cluster is GREEN only when at least ONE of them is CONFIRMED present via a successful read. A 403 yields UNKNOWN, which can never satisfy that precondition — so a forbidden read here cannot earn GREEN (no unearned GREEN); a >30%-headroom cluster whose PD/custom-networking signals are not confirmed present caps at AMBER-with-note. Note the CNI-config uncertainty under Investigate Manually.
7. List ENIConfig resources (custom networking indicator). If ENIConfig listing returns 404/NotFound → custom networking CONFIRMED absent (a successful negative read); if 403/Forbidden → mark the custom-networking signal UNKNOWN rather than assuming absent or present (an UNKNOWN signal cannot satisfy the GREEN precondition — see step 6 and the evaluation-order note).

**Rating:**
- 🟢 GREEN: >30% IP headroom (skill-defined heuristic — not an AWS-published threshold) AND at least one of prefix delegation or custom networking CONFIRMED present via a successful read. GREEN needs the good signal confirmed — an UNKNOWN (403) PD/custom-networking signal can never satisfy this precondition (no unearned GREEN).
- 🟡 AMBER: 15-30% IP headroom (skill-defined heuristic — not an AWS-published threshold); OR >30% headroom but neither prefix delegation nor custom networking CONFIRMED present — this covers both (a) both signals confirmed absent via successful reads, and (b) the good signal could not be confirmed because a read returned 403/Forbidden (AMBER-with-note: "prefix delegation could not be verified; consider enabling it"). An unconfirmable good signal caps here, never GREEN.
- 🔴 RED: <15% IP headroom (skill-defined heuristic — not an AWS-published threshold)
- ⬜ UNKNOWN: the IP-capacity reads (subnet available-IP counts, pod/node counts) returned 403/Forbidden so headroom itself cannot be computed AND that 403 was the sole discriminator (nothing successfully read yields a color). A 403 on the PD or custom-networking read alone does NOT go here — headroom was computed, so the check resolves via the RED/AMBER/GREEN bands above (a confirmed RED or AMBER survives a 403 on the PD/custom-networking signal and is never downgraded to UNKNOWN).
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. The headroom percentage partitions exhaustively into RED (<15%), AMBER (15-30%), and >30%. Within the >30% band the PD/custom-networking overlay resolves the GREEN-vs-AMBER boundary: GREEN only when at least one of prefix delegation or custom networking is CONFIRMED present via a successful read; otherwise (both confirmed absent, OR the signal is UNKNOWN due to a 403) the >30% cluster caps at AMBER. The overlay only affects the >30% GREEN-vs-AMBER split — it never moves the RED (<15%) or AMBER (15-30%) headroom partitions.
- *Note: IP-exhaustion history and cluster growth trend are not gathered by the steps above (no event or trend data is collected), and subnet sharing with other workloads cannot be determined from cluster state. If capacity planning is a concern, investigate these manually.*

**Key talking point:** Prefix delegation assigns a /28 (16 IPs) per ENI slot instead of 1 IP — dramatically increases pod density.

---

### 6.2 — CoreDNS Health and Scaling

**What to check:**
- CoreDNS deployment: replica count, resource requests, pod placement
- Node count (to assess CoreDNS ratio — ~1 replica per 16 nodes or 256 cores, minimum 2)
- NodeLocal DNSCache DaemonSet
- CoreDNS HPA
- CoreDNS topology spread constraints

**How to check:**
1. Read Deployment `coredns` in kube-system → replicas, resources, topologySpreadConstraints. If 403/Forbidden when reading the coredns Deployment → mark the replica-adequacy signal UNKNOWN (do not infer a replica count, or AZ spread from topologySpreadConstraints, from an unreadable Deployment); apps/v1 Deployment is a core API so 404 is not expected. Replica adequacy is the PRIMARY signal for this check, so a forbidden coredns read means the RED/AMBER under-provisioning preconditions cannot be evaluated and GREEN cannot be awarded — apply the 403 replica-adequacy-signal rule in the Rating block below.
2. List pods with label `k8s-app=kube-dns` → check node placement
3. Count nodes. If 403/Forbidden when listing nodes → mark the replica-adequacy signal UNKNOWN (the ~1-per-16-nodes / 256-cores formula cannot be computed without a node count); Node is a core API so 404 is not expected, and an empty successful list means zero nodes. The node count is a component of the primary replica-adequacy signal — apply the 403 replica-adequacy-signal rule in the Rating block below.
4. List DaemonSets → check for `node-local-dns` or `nodelocaldns` (recommended for clusters with 50+ nodes). If 403/Forbidden when listing DaemonSets → mark the NodeLocal DNSCache signal UNKNOWN (do not conclude it is absent); apps/v1 DaemonSet is a core API so 404 is not expected. NodeLocal DNSCache on large clusters is a GREEN precondition, so a forbidden DaemonSet read caps GREEN at AMBER-with-note ("NodeLocal DNSCache presence could not be verified"), never a silent GREEN pass.
5. Check for CoreDNS autoscaling before flagging "no HPA": the EKS-managed CoreDNS add-on has a built-in `autoScaling` feature (enabled via the add-on `configurationValues`) that scales replicas WITHOUT creating an HPA object. Also list HPAs in kube-system with label `k8s-app=kube-dns`. If either the add-on built-in autoScaling is enabled OR an HPA is present, CoreDNS can auto-scale, so fewer static replicas is acceptable. If 403/Forbidden when listing HPAs → treat the HPA presence as UNKNOWN (do not conclude 'no HPA'); if the add-on built-in autoScaling cannot be confirmed either, mark the CoreDNS-autoscaling signal UNKNOWN rather than rating RED. (autoscaling/v2 HPA is a core API, so 404 is not expected; an empty successful list means no HPA.)

**Rating:**
- 🟢 GREEN: CoreDNS scaled to cluster size (~1 replica per 16 nodes or 256 cores, min 2) or add-on built-in autoScaling / HPA enabled, spread across AZs, NodeLocal DNSCache on large clusters. GREEN is not awardable without a SUCCESSFUL coredns Deployment read AND a successful node count — replica adequacy is the primary signal and must be confirmed via successful reads (a 403 on either the coredns Deployment or the node count makes replica adequacy UNKNOWN → see the 403 replica-adequacy-signal rule). A forbidden DaemonSet read (step 4) caps GREEN at AMBER-with-note rather than awarding the "NodeLocal DNSCache on large clusters" precondition unearned.
- 🟡 AMBER: Adequate replicas but no topology spread, or no NodeLocal DNSCache on 50+ node clusters, **or** the add-on-autoScaling-disabled-plus-HPA-403 edge arm (replica count confirmed below the ~1-per-16-nodes / 256-cores, min-2 formula AND add-on built-in autoScaling confirmed disabled by a successful read, but the HPA list returned 403) — AMBER-with-note "CoreDNS replicas below the recommended formula and add-on built-in autoScaling confirmed disabled, but HPA presence could not be verified (403) — confirm no HPA is compensating and enable autoscaling if absent" (detailed under UNKNOWN → edge clause below)
- 🔴 RED: CoreDNS under-provisioned — replica count below the ~1-per-16-nodes (or 256-cores, minimum 2) formula with no autoscaling (neither add-on built-in autoScaling nor HPA) on ANY cluster. The minimum-2-replica floor applies regardless of cluster size, so a small cluster with a single static CoreDNS replica and no autoscaling is RED; only the NodeLocal DNSCache expectation carries the "50+ nodes" qualifier
- ⬜ UNKNOWN: the CoreDNS-autoscaling / replica-adequacy signal is undeterminable AND that 403 was the sole discriminator. Two sole-discriminator entries: (a) the HPA list (step 5) returned 403/Forbidden AND the add-on built-in autoScaling could not be confirmed either, so the CoreDNS-autoscaling signal is undeterminable — do NOT rate RED on that unconfirmed absence (a forbidden HPA list is not "no HPA"). **Edge — add-on autoScaling CONFIRMED DISABLED (successful read) + HPA list 403:** clause (a) does NOT fire here (the add-on autoScaling signal WAS confirmed, as disabled, so the autoscaling signal is not wholly undeterminable), and this state is NOT UNKNOWN. Resolve it on the replica-adequacy signal instead: the HPA 403 cannot earn GREEN's "autoscaling enabled" alternative (no unearned GREEN), so GREEN requires a confirmed-adequate replica count (≥ the ~1-per-16-nodes / 256-cores, min-2 formula) plus AZ spread and NodeLocal-on-large; a confirmed below-formula replica count is NOT a confirmed "under-provisioned" RED (RED's "no autoscaling" precondition needs the HPA confirmed absent, which the 403 blocks), so it caps at 🟡 AMBER-with-note ("CoreDNS replicas below the recommended formula and add-on built-in autoScaling confirmed disabled, but HPA presence could not be verified (403) — confirm no HPA is compensating and enable autoscaling if absent"), never RED and never UNKNOWN. (b) the coredns Deployment read (step 1) OR the node count (step 3) returned 403/Forbidden, so replica adequacy cannot be computed and the RED/AMBER under-provisioning preconditions cannot be evaluated — the check is UNKNOWN when that forbidden replica-adequacy read is the sole discriminator (nothing else successfully read yields a color). A CONFIRMED RED or AMBER survives this: if the replica count read succeeded and shows replicas below the ~1-per-16-nodes (or 256-cores, min 2) formula AND autoscaling is confirmed absent via successful reads, that RED stands even if a different read (e.g. the DaemonSet list for NodeLocal DNSCache, or the HPA list) returned 403 — a confirmed color is never downgraded to UNKNOWN.
- **403 replica-adequacy-signal rule:** the coredns Deployment replica count (step 1) and the node count (step 3) together form the PRIMARY replica-adequacy signal (the ~1-per-16-nodes / 256-cores, min-2 formula). When either read returns 403/Forbidden the formula cannot be evaluated: (a) GREEN is NOT awardable — a forbidden coredns read means replica adequacy and AZ spread are unconfirmed; (b) do NOT rate RED "under-provisioned" on an unreadable replica count or node count (that unconfirmed under-provisioning is not a confirmed RED); (c) when the forbidden replica-adequacy read is the SOLE discriminator, the check is UNKNOWN. This never *raises* a band: a confirmed RED/AMBER from successful reads stands as a floor and is not downgraded by a 403 on a different signal. A forbidden DaemonSet read (step 4) is NOT a replica-adequacy failure — it only caps GREEN at AMBER-with-note on the NodeLocal DNSCache precondition. Record any forbidden read under Investigate Manually.
- *Note: the ~1-replica-per-16-nodes (or 256-cores) ratio is the AWS-published CoreDNS autoscaler formula, not a skill-defined value. The "50+ nodes" NodeLocal DNSCache trigger and the >30%/<15% IP-headroom bands, by contrast, are skill-defined heuristics with no AWS-published source.*
- *Investigate Manually: whether DNS resolution issues have occurred historically is not observable from cluster state (no query-latency or error-rate data is collected by the steps above); confirm with the operator if DNS reliability is a concern.*
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping — the edge arm named in the UNKNOWN clause (add-on autoScaling confirmed disabled + HPA 403) resolves to the AMBER band above, so it does not create a state outside the RED/AMBER/GREEN/UNKNOWN partition. **Precedence — this per-check edge does NOT override the global 403 rules; it is an application of them.** The edge is exactly global rule 4 ("no unearned GREEN": the HPA 403 leaves GREEN's autoscaling alternative unconfirmable, and the below-formula replica count blocks the confirmed-adequate GREEN precondition) combined with global rule 5 not firing (the whole check is not UNKNOWN because the successfully-read replica-adequacy + confirmed-disabled add-on autoScaling signals still yield a color — AMBER — so the 403 is not the sole discriminator). Where this per-check text and the global rules both speak, they agree; the global rules govern and nothing here is a silent local override.

---

### 6.3 — Network Policies & Segmentation

**What to check:**
- VPC CNI Network Policy Controller enabled (the `aws-network-policy-agent` container runs with `--enable-network-policy=true`, or the vpc-cni add-on `configurationValues` sets `enableNetworkPolicy: "true"`)
- Calico pods (alternative enforcement engine)
- NetworkPolicy resources across namespaces
- Default-deny policies (podSelector: {})
- Namespaces without any NetworkPolicy

**How to check:**
1. Read DaemonSet `aws-node` in kube-system → inspect the `aws-network-policy-agent` container for the `--enable-network-policy=true` arg (or check the vpc-cni add-on `configurationValues` for `enableNetworkPolicy: true`). A self-managed Helm install instead sets the `amazon-vpc-cni` ConfigMap key `enable-network-policy-controller: "true"`. **Routing note:** a 403/Forbidden on THIS enforcement read (aws-node DaemonSet / add-on config), WHEN the NetworkPolicy list in step 3 succeeded and policies are present, does NOT go to UNKNOWN — policy presence WAS determined; only enforcement was not verified, so route it to the AMBER "policies defined but enforcement not verified" arm.
2. List pods with label `k8s-app=calico-node`
3. List NetworkPolicies across all namespaces. If 403/Forbidden when listing NetworkPolicies → mark the network-policy signal UNKNOWN; do not rate RED on a forbidden list. (NetworkPolicy is a core `networking.k8s.io` API, so 404 is not expected; an empty successful list means no NetworkPolicies.) **Routing note:** a 403 on THIS NetworkPolicy list is the only 403 that routes to the UNKNOWN band (policy presence genuinely undeterminable); a 403 on the step-1 enforcement read while this list succeeded routes to AMBER instead (see step 1).
4. Inspect NetworkPolicies for default-deny (empty podSelector)
5. Compare namespaces with policies vs namespaces without

**Rating:**
- 🟢 GREEN: Enforcement enabled (VPC CNI controller or Calico), default-deny in production namespaces
- 🟡 AMBER: Policies defined but enforcement not verified, or policies in some but not all *application* namespaces (the production/application-namespace set — exclude `kube-system`, `kube-public`, `kube-node-lease`, and `default`; a bare kube-system/kube-public with no NetworkPolicy is the norm and does NOT trigger this arm), or enforcement enabled and policies present but NO default-deny in production namespaces
- 🔴 RED: No network policies, or policies defined but enforcement not enabled (false security)
- ⬜ UNKNOWN: the NetworkPolicy list (step 3) returned 403 so policy presence cannot be determined AND that 403 was the sole discriminator. (A 403 on the enforcement read alone — step 1 — while the NetworkPolicy list succeeded does NOT belong here; policy presence was determined, so that state is the AMBER "policies defined but enforcement not verified" arm.) CONFIRMED FLOOR: a color established from successful reads survives a 403 elsewhere — but "no enforcement" is a two-engine claim (GREEN's enforcement = VPC CNI controller **OR** Calico), so the "false security" RED is CONFIRMED only when BOTH engines are confirmed absent via successful reads: the step-1 VPC-CNI read confirms enforcement disabled AND the step-2 Calico pod list *succeeded and found no Calico*. In that both-confirmed-absent state, with the NetworkPolicy list showing policies present, the confirmed RED ("policies defined but enforcement not enabled — false security") is NOT downgraded to UNKNOWN even if some other unrelated read returned 403. If instead the step-1 VPC-CNI read confirms enforcement disabled but the step-2 Calico pod list returned 403 (Calico may be installed and enforcing), the enforcement signal is UNKNOWN — not confirmed-absent — so do NOT rate the "false security" RED; route per the 403 rules (the NetworkPolicy list determined policy presence, so this is the AMBER "policies defined but enforcement not verified" arm; if the NetworkPolicy list itself also 403'd, UNKNOWN).
- *Investigate Manually: whether the defined NetworkPolicies have actually been tested (i.e. verified to allow intended traffic and block the rest) is not observable from cluster state; confirm enforcement behavior with the operator.*
- **Production-namespace decision rule:** "production namespaces" is not directly observable from cluster state. When namespace criticality cannot be determined, treat application namespaces (exclude `kube-system`, `kube-public`, `kube-node-lease`, and `default`) as production for the default-deny assessment, apply the GREEN/AMBER default-deny expectation to those assumed-production namespaces, and record the assumption under Investigate Manually.
- **Evaluation order:** assess RED first; if not RED, assess AMBER; otherwise GREEN. Keeps the bands exhaustive and non-overlapping.

**Critical gotcha:** VPC CNI requires explicitly enabling the Network Policy Controller. Without it, NetworkPolicy resources are just YAML that does nothing.
