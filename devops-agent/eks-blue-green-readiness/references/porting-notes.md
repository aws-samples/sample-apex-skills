# Porting Notes — eks-blue-green-readiness (maintainers only)

> **This file is for maintainers, not for the agent to read during execution.** It is excluded
> from the uploaded skill zip (add `-x './references/porting-notes.md'` to the zip command, as the
> README documents for the other skills). It captures design decisions and the live-verification
> record.

> **Staleness check:** Last verified 2026-07-20. The capability facts below (Pod Identity's
> cluster-independence, prefix-delegation IP math, AL2023/version cutoffs) have a release cadence —
> re-verify against the cited sources before each publish. This skill has **no Claude Code upstream
> original** — it is an original DevOps Agent skill; there is no "Differences from upstream" table.

## Design notes

### (a) Routing-collision design — why the name and triggers differ from the two neighbours

This skill was deliberately shaped to **not** collide with `eks-upgrade-check` or
`eks-upgrade-advisor` in the router (which matches on `name` + `description` + trigger phrases, not
body prose). The three occupy adjacent-but-distinct lanes:

| Skill | Lane | Would-collide trigger it must AVOID |
|-------|------|-------------------------------------|
| `eks-upgrade-check` | K8s-**version** readiness *score* (0–100), path-agnostic, **zero** blue-green content (correct) | "am I ready to upgrade", "readiness score", "deprecated APIs" |
| `eks-upgrade-advisor` | The phased **execution sequencer**; blue-green is one **mode** there | "upgrade my cluster", "plan my upgrade", "my upgrade is stuck", "upgrade runbook", "sequence an EKS upgrade" |
| `eks-blue-green-readiness` (this) | Standalone **pre-flight** for *standing up a green cluster* + cutover safety | — owns: "stand up a green cluster", "blue-green readiness", "is my green cluster ready for cutover", "second cluster pre-flight" |

Design rules applied:
- **Triggers are cluster-*standup*-centric**, never upgrade-centric. This skill's phrases are about
  a *green/second cluster* and *cutover*, not about "upgrading" or a "readiness score". A user who
  says "plan my upgrade" or "am I ready to upgrade" must route to advisor / upgrade-check, not here.
- **The description opens with "blue-green readiness pre-flight … GO/NO-GO gate for STANDING UP a
  green cluster"** and its "Route elsewhere" explicitly hands the *score* to eks-upgrade-check and
  the *phased execution sequencer where blue-green is a mode* to eks-upgrade-advisor. Both neighbours
  are named so the router has an explicit off-ramp.
- **Altitude, not duplication.** eks-upgrade-advisor's `blue-green-mode.md` already covers the
  cluster-shape identity change (OIDC/IRSA re-point, LB/DNS/cert, stateful split-brain) *as part of
  its execution overlay*. This skill lifts those same four concerns into a **standalone,
  pre-provisioning GO/NO-GO gate** with a deterministic roll-up — the thing you run *before* you
  decide to build green, whether or not the motivation is a version upgrade. The advisor sequences
  the *doing*; this skill gates the *should-we*. The overlap in subject matter is intentional and
  fine (mirrors the recon/upgrade-check "overlapping facts is fine" stance) — the *output shape*
  (a gated pre-flight verdict vs an ordered runbook) is what keeps them distinct.
- **When both are relevant** (a blue-green *upgrade*): run this pre-flight first for the GO/NO-GO on
  standing green up, then route the ordered execution to `eks-upgrade-advisor` (blue-green mode).
  This skill's "Route elsewhere" section points at `eks-upgrade-advisor`, but the **reverse pointer
  does not yet exist** — `eks-upgrade-advisor`'s SKILL.md / `blue-green-mode.md` do **not** name this
  skill. **REQUIRED cross-skill follow-up (not yet done):** add a pointer from `eks-upgrade-advisor`
  to `eks-blue-green-readiness` (e.g. "run the standalone pre-flight `eks-blue-green-readiness` for
  the GO/NO-GO on standing green up") so the two route reciprocally. Do **not** assume the pointer is
  in place; a maintainer must add it in the advisor skill (out of scope for edits to *this* skill).

### (b) Shared IP-capacity mechanics (cross-reference to the advisor and upgrade-check)

Gate 1's subnet free-IP thresholds are the **same skill-internal heuristic family** used by
`eks-upgrade-check` and `eks-upgrade-advisor` (Phase 1 Gate 5) — but **analogous, not identical**.
Two differences: (1) the quantity being checked — the advisor/upgrade-check check *node-surge*
headroom (old fleet + a bit); this skill checks a **whole second parallel fleet** (blue-live +
green-projected), a much larger `required` number; and (2) the **band shape** — the siblings use
**absolute** `<5 / 5–15 / >15` per-subnet bands, whereas Gate 1 uses a **15% *relative* margin** on
the aggregate `required_green`. These are **not the same rule** and can diverge on identical facts,
so Gate 1 is deliberately worded as "analogous but distinct (a relative margin, not the advisor's
absolute-count bands)" rather than claiming strict consistency. All of it is explicitly labelled
**skill-internal, NOT an AWS-published number** (AWS publishes only "up to 5 IPs" for control-plane
ENIs). If the siblings' bands change, revisit Gate 1. Secondary-CIDR and prefix-delegation escapes are shared vocabulary with the advisor's
blue-green-mode capacity section.

### (c) The access-entry mechanism (why no `eks:AccessKubernetesApi`)

Same mechanism as `eks-recon`, `eks-backup`, `eks-al2-to-al2023`, and `eks-upgrade-advisor`:
K8s-API **authentication** comes from an EKS **access entry** binding the Agent Space role to
`AmazonAIOpsAssistantPolicy` at cluster scope — not from an IAM action. So `iam-policy.json` grants
no `eks:AccessKubernetesApi`. The IAM policy is pure AWS-control-plane read (EKS/EC2/IAM-GetRole/
KMS/ELB/Route 53/ACM), all `Describe`/`List`/`Get`, no create/modify/delete anywhere.

### (d) The AmazonAIOpsAssistantPolicy CRD limitation (built-in groups only)

The managed `AmazonAIOpsAssistantPolicy` authorizes **built-in API groups only — NO CRD groups**
(and not `apiextensions.k8s.io`). Consequences per gate, and the rule everywhere: a CRD-sourced
fact is **`unconfirmed`, never a false "absent/GREEN"**:
- **Gate 1:** `ENIConfig` custom networking (`crd.k8s.amazonaws.com`) → unconfirmed if in use. (The
  `aws-node` DaemonSet env that carries prefix-delegation flags is on the `apps` group and **is**
  readable — that part is fine.)
- **Gate 2:** `serviceaccounts` is on the **core** group but is **NOT** in the
  `AmazonAIOpsAssistantPolicy` readable core set (that set is `pods`, `pods/log`, `services`,
  `nodes`, `namespaces`, `events`, `persistentvolumes`, `persistentvolumeclaims`, `configmaps` —
  `serviceaccounts` and `secrets` are absent; source
  https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/EKS-Integration.html, as of
  2026-07-20). So reading the IRSA ServiceAccount `eks.amazonaws.com/role-arn` annotation **`403`s
  under the plain policy**, exactly like a CRD-blocked fact — Gate 2 is `unconfirmed` until the
  supplementary ClusterRole below (which grants `serviceaccounts`, get/list) is bound. Pod Identity
  *associations* and any identity CRD are likewise not fully resolvable from the plain policy; where
  the IRSA-vs-Pod-Identity split for a workload can't be read, it is `unconfirmed`, never assumed
  either way.
- **Gate 3:** AWS Load Balancer Controller `TargetGroupBinding`/`IngressClassParams`
  (`elbv2.k8s.aws`) and external-dns CRDs → `403` → the shared-LB weighted-target shape and
  external-dns record ownership are `unconfirmed`. (Ingress/Service are built-in and readable.)
- **Gate 4:** database-operator CRDs and `VolumeSnapshot` (`snapshot.storage.k8s.io`) → `unconfirmed`
  where authoritative ownership depends on them. StatefulSets/PVC/PV/StorageClass are built-in and
  readable — the primary data-shape read works.

To confirm the CRD-dependent inputs, bind the Agent Space role to a **read-only** supplementary
ClusterRole (a runtime-visible copy is duplicated here because porting-notes ships excluded from
the zip — **keep in sync** if this ever moves to a runtime file):

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-blue-green-readiness-readonly
rules:
  - apiGroups: [""]                       # core group — serviceaccounts is NOT in the
    resources: ["serviceaccounts"]        # AmazonAIOpsAssistantPolicy readable core set,
    verbs: ["get", "list"]                # so Gate 2's IRSA SA-annotation enumeration needs this
  - apiGroups: ["elbv2.k8s.aws"]
    resources: ["targetgroupbindings", "ingressclassparams"]
    verbs: ["get", "list"]
  - apiGroups: ["externaldns.k8s.io"]
    resources: ["dnsendpoints"]
    verbs: ["get", "list"]
  - apiGroups: ["crd.k8s.amazonaws.com"]
    resources: ["eniconfigs"]
    verbs: ["get", "list"]
  - apiGroups: ["snapshot.storage.k8s.io"]
    resources: ["volumesnapshots", "volumesnapshotcontents"]
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.sh"]
    resources: ["nodepools", "nodeclaims"]
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.k8s.aws"]
    resources: ["ec2nodeclasses"]
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
```

Bind it with a `ClusterRoleBinding`. Absent this, the CRD-dependent gate inputs report
`unconfirmed` and are treated as not-GREEN — the skill degrades safe, never false.

### (e) IAM read-only note (Gate 1/Gate 2/Gate 3 AWS reads)

`iam:GetRole` (trust-policy read), `elasticloadbalancing:Describe*`, the three Route 53 read
actions, and the two ACM read actions are all in `iam-policy.json` (Sids `IdentityReadAccess`,
`CutoverReadAccess`). If a tighter Agent Space role omits any, the corresponding gate input
degrades to `unconfirmed` (not-GREEN) rather than being reported false — the report names the
missing permission. There are **no** write/create/modify/delete actions anywhere in the policy.

**Two reads were added to the policy (both strictly read-only) to close false-GREEN gaps:**
- **`ec2:DescribeVpcs`** (Sid `EC2ReadAccess`) — Gate 1 reads the VPC's **secondary-CIDR association**
  from `DescribeVpcs`' `CidrBlockAssociationSet` (it is **not** in `DescribeSubnets`). An earlier
  draft claimed the secondary-CIDR escape was "readable under iam-policy.json / nothing missing"
  while `EC2ReadAccess` did **not** grant `DescribeVpcs` — that gap is now fixed (the action is added
  and listed in the SKILL.md prereq table). This corrects the earlier "nothing missing" claim.
- **`eks:ListPodIdentityAssociations`** (Sid `EKSReadAccess`) — Gate 2 row 4 (GREEN) requires
  *confirming* a workload uses Pod Identity; without this read, "uses Pod Identity" was an assumption.
  The read confirms it; if blocked, Gate 2 is `unconfirmed`.
Both are read-only (`Describe`/`List`); the policy remains free of any write/create/modify/delete.

### (f) Deferred scope

- **Green-side live inspection.** This skill pre-flights from **blue** + the surrounding AWS
  environment; green typically does not exist yet. It does not (and cannot) read a green cluster's
  live state. If green is already partially stood up, inspecting it is out of scope here — route to
  `eks-recon` for green's inventory once it exists.
- **EC2 vCPU service-quota headroom** for the green fleet is a real second capacity constraint
  (the advisor's blue-green mode calls it out alongside subnet IPs). This skill does **not read**
  Service Quotas (a `servicequotas:GetServiceQuota` read is a possible future revision), so the
  quota is **operator-asserted**. It **does** gate on it: an unverified vCPU/instance quota is an
  unread hard standup blocker (`InsufficientInstanceCapacity`), so Gate 1 grades it **`unconfirmed`
  (not-GREEN)** unless the operator affirmatively confirms headroom — same discipline as gate-4's
  unverified RPO, **not** a silent AMBER caveat. (This corrects the earlier draft, which treated it
  as an operator-owned note that did not gate / surfaced it as AMBER.)
- **Datastore-specific describe APIs** (RDS/EFS/S3/DynamoDB) are intentionally **not** in the read
  scope — Gate 4 classifies ownership from K8s facts + endpoint references and routes the
  store-specific detail and data-movement mechanics to `eks-recon` / `eks-backup`.

## Verification note (sources live-verified 2026-07-20)

Every capability/limit claim was verified live against these sources on 2026-07-20:

- **OIDC issuer is per-cluster; IRSA trust policy binds the cluster's provider + `sub`/`aud`** —
  https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html . A new
  cluster mints a new issuer `<UNIQUE-ID>`, so blue-scoped trust policies do not match green's
  tokens. Confirmed.
- **EKS Pod Identity sidesteps the per-cluster OIDC provider** (association via EKS API + Pod
  Identity Agent; trust principal `pods.eks.amazonaws.com`, cluster-independent) —
  https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html . Framed as "verify live" in
  Gate 2 since the exact principal string / cluster-independence should be re-confirmed at publish.
- **Blue/green cluster identity + LB/DNS/cert + stateful split-brain** (a new cluster has a new
  endpoint/OIDC; LBs and external-dns do not span clusters; stateful cutover risks split-brain) —
  https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html ("Evaluate
  Blue/Green Clusters"). This is the same source the advisor's blue-green-mode.md cites; consistent.
- **Prefix delegation (/28 prefixes, denser pods-per-node) and increasing available IPs** —
  https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses.html . Confirmed
  prefix delegation changes IP-packing but does not create address space.
- **VPC secondary CIDR (e.g. 100.64.0.0/16 for green-only subnets) + CNI custom networking** —
  https://docs.aws.amazon.com/vpc/latest/userguide/configure-your-vpc.html and
  https://docs.aws.amazon.com/eks/latest/userguide/cni-custom-network.html . Confirmed.
- **Control-plane-subnet "up to 5 available IPs" is the only AWS-published EKS free-IP figure** —
  https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html ("Verify available
  IP addresses"). Gate 1's parallel-fleet thresholds are therefore labelled skill-internal, NOT
  AWS-published (same honesty stance as the advisor's Gate 5).

All claims returned TRUE or NUANCED-with-"verify-live"-caveat; zero refuted claims shipped. Negative
/ absence claims (e.g. "Pod Identity does not depend on OIDC") carry the live-doc pointer and
"as of 2026-07-20" phrasing per the negative-claims discipline.

## Follow-ups (post-merge advisories)

- If a future eks-upgrade-check vendoring tightens its description, re-confirm no new trigger
  overlap with this skill's "second cluster" phrases.
- Consider adding the EC2 vCPU-quota read to Gate 1 (deferred above).
- Consider a shared `capacity-model` fragment factored out of Gate 1 and the advisor's
  blue-green-mode to keep the IP heuristic single-sourced.
</content>
