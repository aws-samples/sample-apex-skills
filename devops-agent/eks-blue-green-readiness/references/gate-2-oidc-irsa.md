# Module: Gate 2 — OIDC / IRSA Re-point

> **Part of:** [eks-blue-green-readiness](../SKILL.md)
> **Purpose:** A **new (green) cluster has a NEW OIDC issuer URL**. Every IAM role trust policy
> scoped to the **old (blue)** issuer will **not** work for green — green's pods will fail to
> assume their roles. This gate enumerates the IRSA-consuming workloads and flags the
> trust-policy re-point required before cutover. Load [readiness-model.md](readiness-model.md)
> first for the gate vocabulary and roll-up.

## Table of Contents

- [The mechanic: a new cluster = a new OIDC issuer](#the-mechanic-a-new-cluster--a-new-oidc-issuer)
- [Why blue-scoped trust policies break on green](#why-blue-scoped-trust-policies-break-on-green)
- [Pod Identity: the alternative that sidesteps OIDC re-point](#pod-identity-the-alternative-that-sidesteps-oidc-re-point)
- [What to read](#what-to-read)
- [The gate table](#the-gate-table)
- [Worked example](#worked-example)

---

## The mechanic: a new cluster = a new OIDC issuer

IAM Roles for Service Accounts (IRSA) works by federating the cluster's **OIDC provider** into
IAM: a pod's ServiceAccount is annotated with a role ARN, the pod receives a projected OIDC token,
and IAM's `AssumeRoleWithWebIdentity` trusts that token **only if** the role's trust policy names
the cluster's OIDC provider ARN and issuer URL, and matches the `sub`
(`system:serviceaccount:<ns>:<sa>`) and `aud` (`sts.amazonaws.com`) conditions (as of 2026-07-20;
source: [IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)).

The OIDC issuer URL is **per-cluster** — it is minted when the cluster is created
(`https://oidc.eks.<region>.amazonaws.com/id/<UNIQUE-ID>`). A brand-new green cluster gets a
**brand-new `<UNIQUE-ID>`**, hence a **new issuer URL and a new IAM OIDC provider ARN**. This is
the single most common "green pods are broken and no one knows why" surprise in cluster-shape
blue-green (as of 2026-07-20; source: [EKS blue/green upgrade guidance](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
→ "Evaluate Blue/Green Clusters").

## Why blue-scoped trust policies break on green

Every IRSA role's trust policy on blue reads (paraphrased):

```
Principal:  Federated = arn:aws:iam::<acct>:oidc-provider/oidc.eks.<region>.amazonaws.com/id/<BLUE-ID>
Condition:  oidc.eks.<region>.amazonaws.com/id/<BLUE-ID>:sub = system:serviceaccount:<ns>:<sa>
            oidc.eks.<region>.amazonaws.com/id/<BLUE-ID>:aud = sts.amazonaws.com
```

Green's pods present tokens from `<GREEN-ID>`. The blue-scoped trust policy does **not** match, so
`AssumeRoleWithWebIdentity` is **denied** — the pod gets no AWS credentials and every AWS API call
it makes fails. Before green can serve, for **each** IRSA-consuming ServiceAccount the operator
must either:
1. **Create green's IAM OIDC provider** (from green's issuer) and **add green's issuer** to each
   role's trust policy (a second `StringEquals` condition, or a re-created policy), or
2. **Re-create the roles** scoped to green's provider (common in IaC where roles are per-cluster).

This gate does not perform the re-point — it **enumerates what needs re-pointing** so the operator
sizes and sequences the work before cutover, and so cutover is not attempted with broken pod
identity.

## Pod Identity: the alternative that sidesteps OIDC re-point

**EKS Pod Identity** associates an IAM role with a ServiceAccount through an **EKS API
association** (managed by the Pod Identity Agent), **not** through the cluster's OIDC provider — so
it does **not** depend on the per-cluster issuer URL (as of 2026-07-20; source:
[EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html);
verify against the live doc). The role's trust policy trusts the `pods.eks.amazonaws.com` service
principal, which is **cluster-independent** — the same role definition works on blue and green.

Practical consequence for this gate:
- Workloads using **Pod Identity** need only a **new association created on green** (an EKS API
  call), **not** a trust-policy rewrite — a materially smaller, less error-prone cutover step.
- Workloads using **IRSA** need the **full trust-policy re-point** above.
- Migrating IRSA → Pod Identity *before* the cutover is a documented way to make future
  blue-green (and DR) cluster swaps trivial — surface it as advice when a lot of IRSA roles are
  found, but it is out of this skill's scope to perform.

> **Verify live.** Pod Identity's cluster-independence and its exact trust-principal
> (`pods.eks.amazonaws.com`) should be re-confirmed against the live AWS doc above at publish time
> — carry "as of 2026-07-20" on the claim.

> **API-endpoint consumer re-point (operator-asserted → unconfirmed if unverified).** Green is a
> **separate cluster with a NEW API-server endpoint** — the cluster endpoint does not span blue and
> green any more than the OIDC issuer does. **Every consumer of blue's cluster endpoint must be
> re-pointed at green at cutover**: kubectl/kubeconfig contexts, CI/CD deploy targets, and GitOps
> controllers (Argo CD / Flux) that are still syncing to blue — a GitOps controller left pointed at
> blue will keep reconciling blue (or fight a half-cut-over green). AWS names this among the top
> blue-green surprises (as of 2026-07-20; source: [EKS blue/green upgrade guidance](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
> → "Evaluate Blue/Green Clusters"). This skill cannot read the external consumers of a cluster
> endpoint (CI/CD systems, workstation kubeconfigs, GitOps controller targets are outside the AWS +
> K8s read scope), so **endpoint-consumer re-point is operator-asserted**: if the operator confirms
> the consumer inventory is identified and will be re-pointed, note it; if it is **unverified** it is
> surfaced as an **`unconfirmed`** caveat on Gate 2 (not-GREEN, never assumed handled) — never a
> silent GREEN.

## What to read

**Via Kubernetes API — `serviceaccounts` is NOT in the `AmazonAIOpsAssistantPolicy` readable core
set; a supplementary read-only ClusterRole is REQUIRED for this enumeration:**
- List `ServiceAccounts` across namespaces and read the **`eks.amazonaws.com/role-arn`**
  annotation → the set of IRSA-consuming ServiceAccounts and the roles they map to. **Caveat:
  `serviceaccounts` is NOT authorized by the plain `AmazonAIOpsAssistantPolicy`** (the readable
  core set is `pods`, `pods/log`, `services`, `nodes`, `namespaces`, `events`,
  `persistentvolumes`, `persistentvolumeclaims`, `configmaps` — `serviceaccounts` and `secrets`
  are absent; see SKILL.md → *Kubernetes API Access*, source
  [CloudWatch/EKS integration](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/EKS-Integration.html),
  as of 2026-07-20). So under the plain policy these reads **`403`** — exactly like a CRD-blocked
  fact. The fix is the **supplementary read-only ClusterRole in `references/porting-notes.md`,
  which grants `serviceaccounts` (core group, get/list)**; with it this SA-annotation enumeration
  works, and it is then the primary enumeration source. **Without it, the SA read `403`s and Gate 2
  is `unconfirmed`** (never a false "no IRSA" / GREEN).
- Correlate to workloads (Deployments/StatefulSets/DaemonSets — `apps` group, authorized) that
  mount those ServiceAccounts, so the report names the affected workloads, not just SAs.

**Via AWS API (readable under `iam-policy.json`):**
- `eks:DescribeCluster` on blue → `identity.oidc.issuer` (blue's issuer URL — the string that
  green's will differ from).
- `eks:ListAccessEntries` / add-on listing → whether the **EKS Pod Identity Agent** add-on is
  present (a signal that some workloads may already use Pod Identity).
- `eks:ListPodIdentityAssociations` on blue → the **actual Pod Identity associations**
  (ServiceAccount ↔ role). This is the definitive read that **confirms** a workload uses Pod
  Identity (and therefore needs no OIDC re-point). It is in `iam-policy.json`
  (`EKSReadAccess`). **Row 1 GREEN requires this read to succeed;** if it is blocked or unreadable,
  the Pod-Identity-vs-IRSA split is `unconfirmed` (never assumed Pod Identity, never GREEN).
- `iam:GetRole` on each discovered role ARN → read the **trust policy** (`AssumeRolePolicyDocument`)
  to confirm it is scoped to blue's issuer / provider (IRSA) vs `pods.eks.amazonaws.com` (Pod
  Identity). This is the definitive per-role classification.

> **Trust policies unreadable = unconfirmed (never "GREEN / no IRSA").** If `iam:GetRole` is
> blocked (role omitted from the policy scope), **or** the ServiceAccount annotations are
> unreadable — either because `serviceaccounts` is not authorized under the plain
> `AmazonAIOpsAssistantPolicy` (the supplementary ClusterRole granting `serviceaccounts` has not
> been bound → `403`) or because the K8s API is down — the IRSA inventory is **`unconfirmed`** —
> report it with the failed read + fix (bind the supplementary read-only ClusterRole from
> `references/porting-notes.md`), and hold the gate at not-GREEN. Do **not** report "no IRSA workloads" or GREEN from
> a blocked read; that is the false negative this skill must never produce. Pod Identity
> *associations* are confirmed via `eks:ListPodIdentityAssociations` (see above); where that read
> is blocked/unreadable, treat the Pod-Identity-vs-IRSA split for that workload as `unconfirmed`
> rather than assuming IRSA or assuming Pod Identity.

## The gate table

**Evaluation order: rows are evaluated top-down; the first matching row wins.** Rows are ordered
**worst-first** — RED, then the not-GREEN graded rows (the `unconfirmed` and AMBER conditions,
which are mutually exclusive), with GREEN last — so that when inputs could match more than one row,
the safe (not-GREEN) outcome wins.

| # | Condition (first match wins, top-down) | Outcome |
|---|----------------------------------------|---------|
| 1 | IRSA-consuming ServiceAccounts found (read succeeded), each mapping to a role whose trust policy is scoped to **blue's** issuer (with or without a Pod Identity subset alongside) | **RED** — every such role's trust policy must be re-pointed to green's new issuer (or the role re-created) before cutover, or green's pods lose AWS credentials. List the SAs + roles + workloads; if a Pod Identity subset also exists, enumerate it (it needs only new associations on green — the RED driver is the IRSA subset). |
| 2 | `iam:GetRole` blocked, **or** ServiceAccount annotations unreadable — because `serviceaccounts` is not authorized under the plain `AmazonAIOpsAssistantPolicy` (supplementary ClusterRole not bound → `403`) **or** the K8s API is down — **or** `eks:ListPodIdentityAssociations` blocked/unreadable so the Pod-Identity-vs-IRSA split is unresolvable, **or** the "IaC re-creates the roles / uses a parameterized issuer" claim cannot be verified from AWS/K8s reads | **unconfirmed** — cannot enumerate (or safely dismiss) the re-point work from readable facts; report the failed read / unverifiable claim + fix (bind the supplementary read-only ClusterRole granting `serviceaccounts` — see `references/porting-notes.md`). Treated as not-GREEN. Never "no IRSA" / GREEN, and never AMBER off an unverifiable IaC assertion. |
| 3 | A **small IRSA set** whose trust policies already include a wildcard/parameterized issuer condition that is **confirmed by `iam:GetRole`** to already match green's issuer pattern | **AMBER** — re-point is genuinely handled by the parameterized trust policy (confirmed read), but the operator must confirm the green OIDC provider is created and the green apply ran before cutover. Record it. |
| 4 | An IRSA-consuming ServiceAccount whose role trust policy (read by `iam:GetRole`) is scoped to **neither** blue's issuer **nor** a green-matching parameterized pattern — e.g. a **stale** issuer from a prior cluster, a **cross-account** provider, or an otherwise unrecognized federation | **unconfirmed** — the role's cutover behaviour cannot be classified from the trust policy alone (it will not work for green as-is, but the correct fix is not derivable here). Report the SA + role + the mismatching condition and require the operator to verify/re-point it. Not-GREEN; never assumed handled. |
| 5 | **Zero** IRSA-consuming ServiceAccounts found (confirmed read), and every workload needing AWS uses **Pod Identity** — **confirmed via `eks:ListPodIdentityAssociations`** (or needs no AWS access) | **GREEN** — no trust-policy **re-point** is needed (the `pods.eks.amazonaws.com` principal is cluster-independent). **GREEN ≠ nothing to do:** the Pod Identity **associations must be created on the green cluster before cutover** — they are per-cluster EKS API associations and do **not** carry over from blue; omit them and green's pods lose credentials exactly like the IRSA-RED case. Carry this as an explicit pre-cutover action on the report. Requires the Pod Identity read to have succeeded; if it did not, row 2 applies. |

## Worked example

**Facts:** blue cluster `prod-blue`, issuer `oidc.eks.us-east-1.amazonaws.com/id/BLUE123`. K8s API
reachable. ServiceAccount scan finds 6 SAs annotated with `eks.amazonaws.com/role-arn` (external-dns,
aws-load-balancer-controller, cluster-autoscaler, and 3 app SAs). `iam:GetRole` on all 6 roles
succeeds: each trust policy names `oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/BLUE123` with a
`:sub` condition — all IRSA, none on Pod Identity. Pod Identity Agent add-on **not** installed.

**Evaluation:** 6 IRSA-consuming SAs, all scoped to blue's issuer → **RED**. Report enumerates the
6 SAs, their roles, and the workloads, and states: green's new issuer (minted at green creation)
means all 6 trust policies must be re-pointed (add green's provider condition or re-create the
roles) before cutover; advises evaluating a migration to Pod Identity to make this and future
cluster swaps trivial. Because a controller like external-dns and the LB controller are in the
list, the report notes these interact with Gate 3 (their green instances need working credentials
before green's ingress/DNS wiring can function).
</content>
