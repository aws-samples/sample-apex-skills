# Module: Readiness Model (Foundation)

> **Part of:** [eks-blue-green-readiness](../SKILL.md)
> **Purpose:** The conceptual foundation every gate depends on — what "green readiness" means,
> the four gates at a glance, the shared gate-outcome vocabulary, and the **deterministic roll-up
> combinator** that turns four gate outcomes into one GO / NO-GO verdict. **Load this first**,
> before any gate file. It carries the rules; the gate files apply them.

## Table of Contents

- [What this skill is (and is not)](#what-this-skill-is-and-is-not)
- [What "green readiness" means](#what-green-readiness-means)
- [The four gates at a glance](#the-four-gates-at-a-glance)
- [Gate-outcome vocabulary (deterministic)](#gate-outcome-vocabulary-deterministic)
- [The roll-up combinator](#the-roll-up-combinator)
- [Why unconfirmed is never GREEN](#why-unconfirmed-is-never-green)
- [Sources](#sources)

---

## What this skill is (and is not)

This skill is a **read-only GO/NO-GO pre-flight** for **standing up a green cluster** in a
blue-green migration or upgrade. It answers exactly one question: *"Is it safe to stand a second
(green) cluster up alongside a live blue cluster and cut traffic over to it?"*

It does **not** score Kubernetes-version upgrade readiness (that is `eks-upgrade-check` — a
path-agnostic 0–100 readiness score with zero blue-green content, which is correct), it does
**not** emit the ordered upgrade *execution* runbook (that is `eks-upgrade-advisor`, where
blue-green is one **mode** among in-place rolling), and it does **not** assess backup tooling or
re-inventory the cluster. Its unique lane is the **cutover safety of a parallel-cluster
topology** — the four things that silently break when a whole second cluster is stood up beside a
live one.

> **Altitude split (read this).** `eks-upgrade-advisor` treats blue-green as a *mode* inside a
> version upgrade and owns the *sequenced execution* (Karpenter → control plane → add-ons →
> nodes → cutover → cut-back). This skill is the **standalone pre-flight** that runs *before* any
> of that: it does not care whether the motivation is a version upgrade, a VPC re-architecture,
> or a region move — it only asks "is green safe to stand up and cut over?" and returns a gated
> verdict. When the caller is mid-upgrade, run this pre-flight, then route the ordered execution
> to `eks-upgrade-advisor`.

## What "green readiness" means

"Green" is the **new, parallel cluster** you intend to stand up next to the existing "blue"
cluster and cut traffic over to. Green readiness is **not** about green's Kubernetes version or
its workload health (green may not even exist yet) — it is about whether the **surrounding
environment can support a second cluster and a clean cutover**:

1. **Capacity** — the shared subnets must hold blue's live fleet **and** green's projected fleet
   at the overlap, or green cannot even be scheduled.
2. **Identity** — green is a *different cluster* with a *new OIDC issuer*, so every IRSA trust
   policy scoped to blue's issuer must be re-pointed or green's pods lose AWS credentials.
3. **Traffic** — load balancers, DNS, and TLS certs do not span two clusters; green needs its
   own target registration, a DNS cutover plan (with TTL bleed), and cert coverage of the
   cutover hostname.
4. **Data** — two clusters cannot both own the same stateful datastore without split-brain risk;
   ownership and a cutover discipline must exist.

Each of these is a **gate**. The pre-flight passes only when all four clear (see the combinator).

## The four gates at a glance

| Gate | The failure it guards against | Reference |
|------|-------------------------------|-----------|
| **Gate 1 — Green IP capacity** | Green's node fleet cannot get pod/ENI IPs because blue is still consuming the shared subnet pool | [gate-1-green-ip-capacity.md](gate-1-green-ip-capacity.md) |
| **Gate 2 — OIDC / IRSA re-point** | Green's pods fail to assume their IAM roles because trust policies are scoped to blue's (now-wrong) OIDC issuer | [gate-2-oidc-irsa.md](gate-2-oidc-irsa.md) |
| **Gate 3 — LB / DNS / cert cutover** | Traffic can't reach green (no targets), lands on stale blue (DNS TTL bleed), or breaks on TLS (cert doesn't cover the hostname) | [gate-3-lb-dns-cert-cutover.md](gate-3-lb-dns-cert-cutover.md) |
| **Gate 4 — Stateful data** | Blue and green both write the same store → split-brain / data divergence | [gate-4-stateful-data.md](gate-4-stateful-data.md) |

## Gate-outcome vocabulary (deterministic)

Every gate row in every gate file resolves to **exactly one** of these four words. No gate emits
a bare verb, a score, or a percentage — the combinator keys only on these four:

- **GREEN** — satisfied. This gate does not block a GO.
- **AMBER** — a caveat that does not block, but the operator must **explicitly accept** it before
  cutover (e.g. a shared external datastore that is safe *only with cutover discipline*). Proceed
  with it recorded and surfaced.
- **RED** — a hard-stop. Standing up / cutting over to green is unsafe until this is resolved.
- **unconfirmed** — a required fact could not be read (K8s API unreachable, a CRD group `403`
  under `AmazonAIOpsAssistantPolicy`, or an IAM/ELB/Route 53/ACM read blocked). Treated as
  **not-GREEN** — it blocks a clean GO exactly like a RED would, and is named in Coverage. It is
  **never** silently converted to GREEN or to a false "absent".

> **Note — distinct from `eks-operation-review`'s roll-up.** This RED/AMBER/GREEN/unconfirmed
> vocabulary is shared in spirit with `eks-operation-review`, but this skill's roll-up is
> **cutover-scoped** (is green safe to stand up and cut over?), *not* a general cluster
> operational-health audit. Same words, different question — do not conflate the two verdicts.

## The roll-up combinator

**Within-gate roll-up (worst-input-wins) — apply this BEFORE the combinator.** Each gate has
multiple inputs (e.g. Gate 1: subnet free IPs, placement intent, projected size, prefix state, and
the EC2 vCPU/instance quota). A gate's single outcome is the **worst** of its inputs on the ordering
`unconfirmed / RED > AMBER > GREEN`: **if any input is `unconfirmed`, the gate's outcome is
`unconfirmed`** (and if any is RED, the gate is at least RED) — it is **never** rounded up to
GREEN/AMBER by ignoring a not-GREEN input. There is **no "materiality" test** that lets a gate drop
an `unconfirmed`/RED input and report a cleaner outcome: every `unconfirmed` input is material by
definition (it is an unread fact the verdict depends on). A gate that reports GREEN or AMBER is
asserting **all** of its inputs were read and none is `unconfirmed`. This is what prevents the
aggregate from ever reading "no unconfirmed" while a gate input is in fact unconfirmed.

The overall verdict is a **pure function** of the four gate outcomes — a second agent given the
same four outcomes must reach the same verdict. Evaluate in this order; the **first** matching
row wins:

| # | Condition across the four gates | Verdict |
|---|----------------------------------|---------|
| 1 | **Any** gate is **RED** | **NO-GO** — do not stand green up / do not cut over. Name every RED gate and its resolution. (unconfirmed gates, if any, are also listed — but RED alone already blocks.) |
| 2 | No RED, but **any** gate is **unconfirmed** | **NO-GO (unconfirmed)** — not safe to declare GO on facts that could not be read. Name every unconfirmed gate + the read that failed + the fix (supplementary ClusterRole / IAM permission). Never downgrade this to GO. |
| 3 | No RED, no unconfirmed, but **any** gate is **AMBER** | **GO-WITH-CAVEATS** — green may be stood up, but every AMBER is listed as an explicit "operator must accept before cutover" caveat at the top of the report. The go/no-go on the caveats stays with the human. |
| 4 | **All four** gates are **GREEN** | **GO** — safe to stand green up and cut over per the evidence. |

**Notes on the combinator:**
- The order matters: a RED **and** an unconfirmed together resolve to **NO-GO** (row 1), and both
  are reported — the combinator never lets an unconfirmed mask a RED or vice-versa.
- There is **no scoring / averaging**. Four GREENs is the only path to GO. This mirrors the
  sibling skills' "never green-light a phase you could not inspect" law.
- A gate marked **N/A** (e.g. Gate 4 on a confirmed-stateless cluster) counts as **GREEN** for
  the combinator — but "stateless" must be a *confirmed* read; an unreadable data shape is
  `unconfirmed`, not N/A (see Gate 4).

## Why unconfirmed is never GREEN

The `AmazonAIOpsAssistantPolicy` that authorizes this skill's K8s reads grants **built-in API
groups only — no CRD groups** (see SKILL.md → *Kubernetes API Access*). So several gate inputs
that live on CRD groups — an AWS Load Balancer Controller `TargetGroupBinding`
(`elbv2.k8s.aws`), an external-dns CRD, a Karpenter `NodePool` — return `403 Forbidden` under the
managed policy alone. Likewise an AWS-side read (`iam:GetRole` on a trust policy, an ELB / Route
53 / ACM describe) may be blocked by a tighter role.

In every such case the fact is **`unconfirmed`**, with the reason and the fix
(`references/porting-notes.md` carries the supplementary read-only ClusterRole; the IAM policy
carries the AWS-side permissions). An `unconfirmed` gate input is **never** reported as "absent",
"no IRSA", "no LB", "stateless", or GREEN — that would be a **false negative**, the one failure
mode this skill must never produce. It is treated as **not-GREEN** and holds the verdict at
NO-GO (combinator row 2) until confirmed.

## Sources

Every capability/limit claim in the gate files carries a source URL and an "as of 2026-07-20"
stamp where it is applied. Canonical sources:

- IAM roles for service accounts (IRSA) — the OIDC provider is per-cluster —
  https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html
- EKS Pod Identity (sidesteps the per-cluster OIDC provider) —
  https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html
- EKS blue/green cluster upgrade guidance (identity change, LB/DNS/cert, stateful) —
  https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html
- VPC CNI increase-available-IPs / prefix delegation —
  https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses.html
- Amazon VPC secondary CIDR blocks —
  https://docs.aws.amazon.com/vpc/latest/userguide/configure-your-vpc.html

> **Do not assert a capability, limit, or date from memory.** Every such claim in the gate files
> is live-verifiable against these sources; carry the URL + "as of 2026-07-20".
</content>
