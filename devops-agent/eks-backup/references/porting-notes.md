# Porting Notes — eks-backup

This file documents design decisions for maintainers of the DevOps Agent `eks-backup` skill.
It is for maintainers, not for the agent to read during execution. **This file is excluded
from the uploaded skill zip** (see the `-x './references/porting-notes.md'` flag in the
README's zip instructions) — it ships in the repository for maintainers only.

> **Staleness check:** the notes below describe verified upstream facts and design intent at a
> point in time and can drift as AWS Backup for EKS, Velero, and the sibling `eks-recon` skill
> evolve. Re-verify each cited source and the RBAC breakdown when materially changing this
> skill, and update the date here. Last verified: 2026-07-19.

Unlike the other DevOps Agent ports, **this skill has no Claude Code upstream original** — it
is authored fresh for the DevOps Agent. So instead of a "Differences from Claude Code Version"
table, the notes below capture the design decisions.

## Design notes

### (a) The posture verdict is intentional (unlike eks-recon)

`eks-recon` is deliberately **facts-only**: its storage module (`storage.md`, section 6
"Backup Tooling") already performs raw backup-tool **DETECTION** — Velero / AWS Backup /
Kasten K10 presence as boolean facts, with **no** posture verdict or runbook. This skill does
**not** duplicate that detection philosophy; it **routes detection there conceptually** and
adds the two things `eks-recon` intentionally withholds: a **READY / PARTIAL / UNPROTECTED
posture verdict** and a **guided runbook**. Rating posture is the whole point of this skill, so
the "draw no conclusion" rule of `eks-recon` is deliberately relaxed here — but only for the
backup-recoverability question, and always subject to the "never UNPROTECTED on unread facts"
guardrail in `backup-approaches.md`.

### (b) Access-entry mechanism (why iam-policy.json has no `eks:AccessKubernetesApi`)

Same mechanism as `eks-recon`. The DevOps Agent reaches the Kubernetes API through an **EKS
Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy`
cluster-access policy (cluster scope), provisioned by `devops-agent/setup.sh`. The cluster's
`authenticationMode` must include `API` (i.e. `API` or `API_AND_CONFIG_MAP`). Because the
access entry — not an IAM action — grants K8s-API **authentication**, `iam-policy.json`
contains **only AWS control-plane reads** and deliberately omits `eks:AccessKubernetesApi`.

**Authorization is narrower than authentication, and the two must not be conflated.** The
access entry only authenticates the role; `AmazonAIOpsAssistantPolicy` supplies the RBAC, and
it authorizes read-only `get`/`list` on **built-in API groups only** — core, `apps`, `batch`,
`events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. It grants **no
CRD groups** (not even `apiextensions.k8s.io`). Consequently the `velero.io` CRDs
(`BackupStorageLocation`, `Schedule`, `Backup`, `Restore`, `VolumeSnapshotLocation`) are **not**
readable through the access entry alone — those reads return `403 Forbidden`. The Velero
**controller Deployment** IS readable because the `apps` group is authorized, which is why the
skill treats the Deployment as a presence signal and the CRDs as `unconfirmed`-on-403.

### (c) The supplementary read-only ClusterRole

To confirm full Velero posture, bind the Agent Space role's Kubernetes identity to this
read-only ClusterRole (or associate a broader access policy). Bind it via a
`ClusterRoleBinding` to the same subject the EKS access entry maps the Agent Space role to.

> **Note:** the runtime-visible copy lives in `references/velero-assessment.md` ("Lifting the
> limitation (supplementary ClusterRole)") — that is the copy the agent surfaces to the user
> during execution, since this porting-notes file is excluded from the uploaded zip. Keep the
> two YAML copies in sync.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-backup-velero-readonly
rules:
  - apiGroups: ["velero.io"]
    resources:
      - backups
      - restores
      - schedules
      - backupstoragelocations
      - volumesnapshotlocations
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources:
      - customresourcedefinitions
    verbs: ["get", "list"]
```

Without this binding (or a broader access policy), the Velero CRD sub-facts stay `unconfirmed`
and the skill reports the ClusterRole as the fix in the posture note and Coverage section.

### (d) The AWS Backup half needs NO cluster access at all

The entire AWS Backup for EKS assessment (`aws-backup-assessment.md`) is pure AWS control-plane
API — `backup:*` and `eks:*` read-only actions in `iam-policy.json`, all `Resource: "*"`. It
needs no EKS access entry, no `authenticationMode` requirement, and no supplementary
ClusterRole. It is unaffected by any Kubernetes-API degradation and always runs to completion.
This is why a cluster is never labeled UNPROTECTED on unread Velero facts: the AWS Backup half
always yields a confirmable answer on its own.

### (e) Verification note

The AWS Backup for EKS GA facts and the Velero CRD facts in this skill were **live-verified
against the AWS and Velero documentation on 2026-07-19**. Sources:

- AWS Backup for EKS GA (Nov 2025): https://aws.amazon.com/about-aws/whats-new/2025/11/aws-backup-supports-amazon-eks/
- AWS Backup EKS backups (what is / isn't covered + limitations): https://docs.aws.amazon.com/aws-backup/latest/devguide/eks-backups.html
- EKS integration with AWS Backup: https://docs.aws.amazon.com/eks/latest/userguide/integration-backup.html
- EKS access policy permissions (AWSBackupFullAccessPolicyForBackup): https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html
- Restoring EKS (non-destructive, will not overwrite K8s version): https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-eks.html
- EKS envelope encryption (AWS-managed etcd; Velero as self-managed alternative): https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html
- How Velero works: https://velero.io/docs/main/how-velero-works/
- Velero API types (velero.io/v1 CRDs): https://velero.io/docs/main/api-types/

The CNCF-maturity / "accepted March 2026" claim for Velero was **deliberately omitted** — it
is dubious and irrelevant to backup posture; do not reintroduce it.
