# Porting Notes — eks-upgrade-advisor (maintainers only)

> **This file is for maintainers, not for the agent to read during execution.** It is excluded
> from the uploaded skill zip (see the `-x './references/porting-notes.md'` flag in the README's
> zip instructions). It captures design decisions and the live-verification record.

> **Staleness check:** Last verified 2026-07-20. The version/timeline/skew facts below have a
> release cadence — re-verify against the cited sources before each publish. This skill has **no
> Claude Code upstream original** (the CC `skills/eks-upgrade-check` is a *readiness checker*,
> not an *execution advisor*), so there is no "Differences from upstream" table — these are
> original design decisions.

## Design notes

### (a) Relationship to sibling skills — why this is a separate skill

The advisor deliberately owns only the **cross-domain order-of-operations** of an upgrade. The
readiness *question* ("am I ready?") is `eks-upgrade-check`; backup posture is `eks-backup`;
node-OS migration mechanics are `eks-al2-to-al2023`; raw inventory is `eks-recon`. The advisor
*consumes* those verdicts and sequences the work — it never re-scores, re-assesses, or
re-explains them. This keeps each skill single-purpose (the project's standing scope decision:
skills stay permanently separate; no combined migrate+upgrade playbook). The advisor's value is
the one thing none of the others own: the gated prepare → execute → validate/debug sequence
across control plane + add-ons + nodes.

Note: on this branch `devops-agent/eks-upgrade-check` is currently a placeholder stub pending the
upstream vendoring (PR #3). The advisor references it as the readiness entry gate on the
assumption it lands built-out; if it is still a stub at publish time, the advisor still stands —
its Phase 1 Gate 1 simply instructs the operator to run the readiness check, whatever form it
takes.

**Routing follow-up for the eks-upgrade-check vendoring (tracked here, not fixable unilaterally):**
the stub's inherited upstream description lists "upgrade plan" as one of its 8 check areas, which
can **collide** with this advisor's triggers ("plan my EKS upgrade", "sequence an EKS upgrade") —
the router matches descriptions, not body prose. When eks-upgrade-check is vendored, disambiguate:
its "upgrade plan" = the *remediation steps to reach GO* (pre-readiness); the advisor's plan = the
*ordered execution sequence after GO*. Add a bidirectional pointer (upgrade-check GO → advisor)
and tighten upgrade-check's description so it doesn't claim execution sequencing. Until then the
advisor's "When to Use" cleanly disclaims readiness scoring, so the one-directional exclusion holds.

### (b) The access-entry mechanism (why no `eks:AccessKubernetesApi`)

Same mechanism as `eks-recon`, `eks-backup`, and `eks-al2-to-al2023`: K8s-API **authentication**
comes from an EKS **access entry** binding the Agent Space role to `AmazonAIOpsAssistantPolicy`
at cluster scope — not from an IAM action. So `iam-policy.json` grants no
`eks:AccessKubernetesApi`. The IAM policy is pure AWS-control-plane read (EKS/EC2/Auto Scaling).

### (c) The supplementary read-only ClusterRole (two gate inputs need it)

This skill has **two** gate inputs the managed policy does not authorize, both load-bearing for
safety:
- **PodDisruptionBudgets** live on the `policy` API group — `AmazonAIOpsAssistantPolicy` does
  **not** grant it. The drain-safety gate (Phase 1 Gate 5) is the single most important
  pre-upgrade check (a `disruptionsAllowed==0` PDB is the #1 "upgrade stuck" cause), so a blocked
  PDB read must surface as `unconfirmed` and hold the gate at not-GREEN — never "no blocking
  PDBs".
- **Karpenter** config (`karpenter.sh`, `karpenter.k8s.aws`) and Auto Mode `NodeClass`
  (`eks.amazonaws.com`) are CRDs — also unauthorized, so Gate 6 reports `unconfirmed`.

To confirm both, bind the Agent Space role to this **read-only** ClusterRole (a runtime-visible
copy of this YAML is intentionally duplicated into this reference file because porting-notes ships
excluded from the zip — **keep the two copies in sync** if this ever moves to a runtime file):

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-upgrade-advisor-readonly
rules:
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.sh"]
    resources: ["nodepools", "nodeclaims"]
    verbs: ["get", "list"]
  - apiGroups: ["karpenter.k8s.aws"]
    resources: ["ec2nodeclasses"]
    verbs: ["get", "list"]
  - apiGroups: ["eks.amazonaws.com"]
    resources: ["nodeclasses", "nodepools"]
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
```

Bind it to the Agent Space principal with a `ClusterRoleBinding`. Absent this, Gates 5 and 6
report `unconfirmed` and are treated as not-GREEN — the skill degrades safe, never false.

### (d) Blue-green as a MODE, and the altitude split vs eks-al2-to-al2023

Blue-green is modeled as a cross-phase **mode overlay** (`blue-green-mode.md`), not a phase and
not a separate skill — this was the explicit build spec. The subtle design point: `eks-al2-to-al2023`
already owns *node-group-level canary blue-green* for an AMI swap. To avoid collision, this
skill's blue-green is defined at a **higher altitude** — the *cluster-upgrade cutover* (parallel
target-version fleet or parallel cluster + traffic shift). The mode file states the distinction
explicitly and routes node-OS mechanics to the sibling.

### (e) Why the phase files carry the runbook (no separate runbook.md)

`eks-backup` and `eks-al2-to-al2023` have a standalone `runbook.md` because their assessment and
their runbook are distinct outputs. Here the *phases are the runbook* — the ordered, gated steps
ARE the operator procedure — so a separate runbook.md would duplicate the phase files. The
Report Output still emits a runbook artifact, assembled from the phase files.

## Verification note (sources live-verified 2026-07-20)

Every version/timeline/skew claim was verified live against these sources on 2026-07-20:

- One-minor-at-a-time upgrades — https://docs.aws.amazon.com/eks/latest/eksctl/cluster-upgrade.html
- **Version rollback (one minor, within 7 days, version-only)** — https://aws.amazon.com/blogs/aws/upgrade-amazon-eks-clusters-with-confidence-using-kubernetes-version-rollbacks/ *(this corrected an initial draft that called upgrades strictly irreversible — the rollback feature exists; framing updated throughout.)* Rollback fine print (in-place clusters only, prior version must still be supported, not Fargate, Auto Mode reverts nodes too) — https://aws.amazon.com/blogs/containers/announcing-amazon-eks-rollback-for-safe-and-reliable-management-of-cluster-upgrades/
- Kubernetes version skew (kubelet trails, **never leads**; kube-proxy/components not newer than apiserver) — https://kubernetes.io/releases/version-skew-policy/ — **EKS boundary: N-2 for ≤1.27, N-3 for ≥1.28** — https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html
- **Upgrade sequence: control plane → add-ons → data plane** (AWS's documented order; corrected a draft that put add-ons before the control plane — that would put kube-proxy/CoreDNS ahead of the API server, a skew violation and a self-contradiction with the skill's own "nothing leads the API server" law). Add-ons do not auto-update; Auto Mode manages core add-ons + node rotation; Fargate pods must be restarted after the control-plane bump — https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html
- Karpenter 0.x→1.0 (v1beta1→v1, needs 0.33+ first) — https://aws.amazon.com/blogs/containers/announcing-karpenter-1-0/
- AL2 AMIs: **1.32 last, 1.33+ AL2023/Bottlerocket only** (publishing ended 2025-11-26) — https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-extended.html
- PDBs block drain during node rotation — https://docs.aws.amazon.com/eks/latest/best-practices/application.html
- Extended support: **14 mo standard + 12 mo extended = 26 mo**; **$0.60 vs $0.10/cluster-hr** — https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html
- cgroup v1 deprecation at **1.35** (kubelet refuses to start by default; `failCgroupV1`) and containerd 1.x last supported at **1.35** (2.0+ for 1.36; AL2023 AMI bundles it) — https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html

- **Control-plane upgrade prerequisites (Phase 1 Gate 7)** — cluster IAM role must be present, and if envelope encryption is on the role must have KMS-key permission; **missing either means the cluster cannot be upgraded** (EKS reverts the attempt). Pre-upgrade **control-plane logging** is AWS "Before Upgrading" guidance. Both CONFIRMED against — https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html ("Verify basic EKS requirements before upgrading" + "Before Upgrading"). Read-only verifiable via `describe-cluster` (roleArn + encryptionConfig), `iam:GetRole`, `kms:GetKeyPolicy`/`DescribeKey`.
- **Cluster-shape blue-green identity change** — a new cluster has a new API endpoint + OIDC issuer, breaking IRSA/Pod Identity and requiring kubectl/CI-CD/external-dns/cert re-point; LBs/external-dns don't span clusters — https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html ("Evaluate Blue/Green Clusters").
- **Subnet free-IP thresholds (<5/5-15/>15)** are a skill-internal node-surge heuristic shared with eks-upgrade-check, **not** an AWS-published node-surge number (AWS publishes only "up to 5 IPs" for control-plane ENIs) — labeled as such in Gate 5 after the 9-lens review (L4/L7/L9 concurred).

All claims returned TRUE or NUANCED-with-correction-applied; zero refuted claims shipped.

## 9-lens PR review (2026-07-20)

Ran the full Find→Verify→Frame→Post pipeline (8 lenses + framing; Lens 3 eval-scaffold N/A for a DevOps Agent skill). Zero INCORRECT survived; L4 verified 11/12 claims TRUE. Folded to convergence: added Gate 7 (control-plane IAM/KMS/logging prereqs — the one new hard gate, verified as a real upgrade-failure cause); rollback-precondition caveat into the Phase 3 crisis table; READY-WITH-CAVEATS state threaded through Phase 2 entry gate + SKILL report line; IP-threshold source honesty; $-figure citation repoint; cluster-autoscaler + topologySpreadConstraints in gates; Fargate profile + IAM/KMS actions added to iam-policy.json; blue-green OIDC/IRSA re-point caveat; EC2 vCPU-quota + non-prod-first + control-plane-duration notes; Karpenter-migration-failure recovery row. Remaining post-merge advisories: slim the extended-support $-figures to a bare link; deepen cluster-blue-green LB/DNS/cert cutover mechanics.
