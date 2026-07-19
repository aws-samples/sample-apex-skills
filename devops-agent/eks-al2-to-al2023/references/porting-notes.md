# Porting Notes — eks-al2-to-al2023

This file documents design decisions for maintainers of the DevOps Agent `eks-al2-to-al2023`
skill. It is for maintainers, not for the agent to read during execution. **This file is
excluded from the uploaded skill zip** (see the `-x './references/porting-notes.md'` flag in
the README's zip instructions) — it ships in the repository for maintainers only.

> **Staleness check:** the notes below describe verified upstream facts and design intent at a
> point in time and can drift as the AL2→AL2023 deprecation timeline, the upstream
> `skills/eks-upgrade-check` skill, and the sibling `eks-recon` skill evolve. Re-verify each
> cited source and the RBAC breakdown when materially changing this skill, and update the date
> here. Last verified: 2026-07-19.

Unlike some DevOps Agent ports, **this skill has no Claude Code upstream original of this exact
skill** — it is authored fresh for the DevOps Agent. So instead of a "Differences from Claude
Code Version" table, the notes below capture the design decisions.

## Design notes

### (a) Relationship to upstream `eks-upgrade-check` (SPECULATIVE — may later merge)

This is a **standalone node-OS-migration skill** authored fresh for the DevOps Agent. It
**deepens** the AL2→AL2023 material that the upstream `skills/eks-upgrade-check` carries as one
module (`references/node-readiness.md`). An effort is underway to improve `eks-upgrade-check`,
so **this skill is speculative and may later merge / overlap** with the improved
`eks-upgrade-check`. State the boundary explicitly:

- **This skill = node-OS-migration depth** — cgroup v2 workload risk, IMDSv2 hop-limit-1
  pod-metadata impact, `nodeadm`/`NodeConfig` userData rewrite, VPC CNI 1.16.2 floor,
  host-agent (DaemonSet/kernel-module/log-shipper) review, and a **canary-node-group migration
  runbook**.
- **`eks-upgrade-check` = whole-cluster upgrade-readiness breadth** — deprecated APIs, add-on
  compatibility matrix, version skew, across **all** breaking changes, rolled into a **0–100
  readiness score**.

**Flag for maintainers:** if/when the improved `eks-upgrade-check` subsumes this node-OS depth,
reconcile the two — either fold this skill's depth into an `eks-upgrade-check` module or keep
this as the deep-dive it routes to. Do not let the two drift into contradicting facts (see (e)).

### (b) Access-entry mechanism (why iam-policy.json has no `eks:AccessKubernetesApi`)

Same mechanism as `eks-recon`. The DevOps Agent reaches the Kubernetes API through an **EKS
Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy`
cluster-access policy (cluster scope), provisioned by `devops-agent/setup.sh`. The cluster's
`authenticationMode` must include `API` (i.e. `API` or `API_AND_CONFIG_MAP`). Because the
access entry — not an IAM action — grants K8s-API **authentication**, `iam-policy.json`
contains **only AWS control-plane reads** and deliberately omits `eks:AccessKubernetesApi`.

**Authorization is narrower than authentication, and the two must not be conflated.** The
access entry only authenticates the role; `AmazonAIOpsAssistantPolicy` supplies the RBAC, and
it authorizes read-only `get`/`list` on **built-in API groups only** — core (`nodes`, `pods`,
`namespaces`, `configmaps`), `apps` (deployments/daemonsets/statefulsets), `batch`,
`events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. It grants **no
CRD groups** (not even `apiextensions.k8s.io`). Consequently the Karpenter `EC2NodeClass` /
`NodePool` (`karpenter.k8s.aws`, `karpenter.sh`) and Auto Mode `NodeClass` (`eks.amazonaws.com`)
CRDs that drive AMI selection are **not** readable through the access entry alone — those reads
return `403 Forbidden`. Node OS facts (`osImage`, `kernelVersion` on core `nodes`) and
node-group `amiType` (AWS API) ARE readable, which is why the skill classifies **running**
Karpenter/Auto-Mode node OS from the node facts while reporting the **desired** CRD AMI family
as `unconfirmed`-on-403. (See SKILL.md for the authoritative RBAC breakdown.)

### (c) The supplementary read-only ClusterRole

To confirm the desired Karpenter / Auto-Mode AMI family (the blocked CRD reads), bind the Agent
Space role's Kubernetes identity to this read-only ClusterRole (or associate a broader access
policy). Bind it via a `ClusterRoleBinding` to the same subject the EKS access entry maps the
Agent Space role to.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-al2023-migration-crd-readonly
rules:
  - apiGroups: ["karpenter.k8s.aws"]
    resources:
      - ec2nodeclasses
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.sh"]
    resources:
      - nodepools
      - nodeclaims
    verbs: ["get", "list"]
  - apiGroups: ["eks.amazonaws.com"]
    resources:
      - nodeclasses
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources:
      - customresourcedefinitions
    verbs: ["get", "list"]
```

Without this binding (or a broader access policy), the Karpenter/Auto-Mode desired-AMI
sub-facts stay `unconfirmed` and the skill reports the ClusterRole as the fix in the posture
note and Coverage section. **Because this porting-notes file is excluded from the uploaded skill
zip, a runtime-visible copy of this same YAML also lives in `references/node-inventory.md`**
(section "Lifting the limitation (supplementary ClusterRole)") so the Coverage note / runbook
can surface it at runtime.

### (d) Verification note

The AL2→AL2023 migration facts in this skill were **live-verified against the AWS
documentation on 2026-07-19**. Sources:

- EKS AL2 deprecation FAQ (end-of-support dates, cgroup v2, JDK 8u372):
  https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html
- AL2023 support / migration (IMDS hop limit, nodeadm/NodeConfig, VPC CNI 1.16.2 floor,
  migration paths): https://docs.aws.amazon.com/eks/latest/userguide/al2023.html
- Kubernetes standard-support versions (cgroup v1 removal at K8s 1.35):
  https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html
- SELinux modes (AL2023 permissive by default):
  https://docs.aws.amazon.com/linux/al2023/ug/selinux-modes.html
- AL2023 vs AL2 comparison (DNF/systemd-networkd/journald/etc.):
  https://docs.aws.amazon.com/linux/al2023/ug/compare-with-al2.html
- EKS-optimized AMI (kernel 6.1/6.12, containerd-only):
  https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami.html

### (e) Fact-precision decision (reconciling with upstream node-readiness.md)

This skill uses the **precise** deprecation dates rather than the looser upstream
`skills/eks-upgrade-check/references/node-readiness.md` wording:

- **EKS-optimized AL2 AMI end-of-support: 2025-11-26** (AWS stopped publishing new EKS releases
  of the AL2 AMIs).
- **Kubernetes 1.32 was the last EKS version to ship AL2 AMIs** — 1.33+ ships AL2023 /
  Bottlerocket only.
- **Base AL2 OS end-of-support: 2026-06-30** (custom AL2-base AMIs are a stopgap until then).

The upstream check states this more loosely as "AL2 standard support ended June 2025" and
"EKS 1.33+ does not publish AL2 AMIs". **This is NOT a contradiction** — it is the same
deprecation stated precisely. Documented here so a maintainer syncing the two skills does not
mistake the precise dates for a conflicting fact. Source (all three dates):
https://docs.aws.amazon.com/eks/latest/userguide/eks-ami-deprecation-faqs.html (as of
2026-07-19).
