---
title: "Severity Rationale (score weighting)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/severity.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/severity.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/severity.md). Edit the source, not this page.
:::

# Severity Rationale (score weighting)

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

Every measured question carries a WAF-style risk weight used by the reducer's `sev()` map:
**High = 3, Medium = 2, Low = 1**. These tiers are this skill's own editorial assignment, not an
AWS-published risk level — no Well-Architected Tool risk classification, CIS Benchmark severity or EKS
Best Practices Guide tiering backs them. They exist to order findings within a pillar, not to borrow
AWS's authority for that ordering. The pillar score is the severity-weighted average of applicable
answers, so a missing High-risk control moves the number three times as much as a missing Low-risk extra.

**What puts a question in each tier:**
- **High** — absence creates a *direct, exploitable exposure* or a *loss-of-availability / data-loss / cost-leak* that a reasonable operator must fix. These define whether a cluster is fundamentally sound.
- **Medium** — a real best practice that materially reduces risk or waste, but whose absence is survivable or context-dependent.
- **Low** — an optimization or advanced/aspirational practice. Valuable, but many well-run clusters legitimately skip it. One Low answer moves a pillar a third as far as one High answer.

**A Low tier is not a small share of the weight.** Weights are per question, so what a tier is worth
inside a pillar depends on how many questions that pillar puts in it. Performance Efficiency scores 11
measured questions — 1 High, 2 Medium, 8 Low (`perf-7` in its Medium table is interview-scored) — so its
Low tier carries **half** the applicable weight: 7 of 14 on the reference capture. Measured there,
fixing only that pillar's four Low failures (VPA, affinity refinement, `ndots`, topology-aware routing)
moved it **59 → 88**, flipping `Poor · High risk` to `Good · Low risk`, while `perf-1` — the pillar's
only High question — stayed at `some — 3 of 15 containers have resource requests`. So a pillar's band,
and the risk label derived from it, cannot tell you whether a High-severity control is met. Read the
High findings themselves.

**The discounts below are conditional.** Where a Medium rationale discounts a control because a more
specific check covers the same ground, the discount holds only while that other check passes. A cluster
missing the whole layer pays the discounted weight for every part of it, which is less than the gap
deserves — read those questions as a group, not one at a time.

Governance questions are unweighted here — they are interview-only and reported separately (Not Assessed in `auto` mode).

---

## Security

### High
| ID | Check | Why High |
|----|-------|----------|
| sec-2 | API server not open to `0.0.0.0/0` | An internet-reachable control plane is the single biggest EKS attack vector. |
| sec-4 | NetworkPolicies present per namespace | Flat pod networking lets one compromised pod reach everything; isolation is baseline containment. |
| sec-6 | Pod-level AWS identity (EKS Pod Identity **or** IRSA) | Falling back to node-role credentials gives every pod on the node broad AWS access — huge blast radius. The detection accepts either mechanism: Pod Identity is what AWS now recommends and it uses no ServiceAccount annotation, so an IRSA-only rationale described a check narrower than the one that runs. |
| sec-11 | Pod Security Standards enforced | Without PSS, privileged/root pods deploy unchecked — the entry point for most container escapes. |
| sec-18 | OIDC provider associated | Prerequisite for IRSA; without it fine-grained pod IAM is impossible. |
| sec-21 | Cluster EBS volumes encrypted at rest | Unencrypted data at rest is a direct compliance and confidentiality failure. |
| sec-38 | Secrets envelope encryption with a customer-managed KMS key | Without it, Secrets are protected by an AWS-owned key the customer cannot audit, scope or revoke. Distinct from sec-21, which covers the disks rather than the Secret objects. |
| sec-26 | Kubernetes audit logging enabled | No audit trail means breaches can't be detected or investigated. |
| sec-29 | Ingress terminates TLS | Plaintext ingress exposes credentials and data in transit. |
| sec-30 | No SSH (port 22) open to the internet | Open SSH is a direct node-takeover path. |
| net-2 | Security groups have no `0.0.0.0/0` on non-web ports | Wide-open SGs are direct network exposure. |
| podsec-2 | Workload containers not privileged | A privileged container is effectively root on the node. |
| podsec-4 | No dangerous capabilities (NET_ADMIN/SYS_ADMIN/ALL) | These capabilities enable container-to-host escape. |
| rbac-1 | `cluster-admin` bound only to system subjects | A stray cluster-admin binding is full cluster takeover. |
| lens-11 | IMDSv2 enforced (`HttpTokens=required`) | IMDSv1 enables SSRF-based theft of node credentials. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| sec-1 | Private API endpoint enabled | Strong control, but sec-2 (restricting public) is the harder gate; often paired. |
| sec-9 | Custom ClusterRoles avoid wildcard verbs/resources | Least-privilege matters, but built-in roles are excluded and impact is bounded. |
| sec-10 | Admission webhooks present | Enforcement point for policy — discounted only while sec-11 (PSS) is enforcing the baseline. With both absent, nothing inspects a pod spec before it runs, which is worse than either weight suggests. |
| sec-15 | Containers set a security context | The umbrella check: discounted only because podsec-1..5 measure the same properties directly and are scored separately. If those are failing too, this weight understates a cluster that sets no securityContext anywhere. |
| sec-16 | Admission/policy engine deployed | Enables enforcement; value depends on the policies actually loaded. |
| sec-25 | StorageClasses set `encrypted: true` | Sets the default for every volume created from here on; discounted only because sec-21 covers the volumes that exist today. Both failing means unencrypted disks now *and* unencrypted disks later. |
| net-4 | Cluster SG default allow-all egress narrowed | Removes the outbound path used for exfiltration and second-stage pulls; not itself an inbound hole. (sec-31, which asked about control-plane/node SG separation, is retired — AWS says that split is no longer required.) |
| sec-33 | Runtime threat monitoring (GuardDuty/Falco) | Detection layer; valuable but not a preventive control. |
| adm-1 | ≥5 admission policies loaded | Depth of policy coverage; incremental over having an engine. |
| adm-2 | A policy blocks privileged pods | Policy-level backstop for podsec-2 — discounted only while podsec-2 itself passes. Privileged pods present *and* no policy blocking them means nothing stops the next one either. |
| adm-3 | Policies run in enforce (not audit) mode | Audit-only still surfaces issues, so enforce is an upgrade not a baseline. |
| podsec-1 | Containers run as non-root | Root in the container is the starting position for every escape: a hostPath mount, a writable host socket or a runtime CVE turns it into root on the node. Medium rather than High because a root container that is *not* privileged is still bounded by the runtime's default capability set. |
| podsec-3 | Pods avoid hostPath mounts | hostPath is a common escape vector but often needed by legit tooling. |
| podsec-5 | Containers drop ALL capabilities | Best practice; discounted only while podsec-2/4 pass. A container that is neither privileged nor holding NET_ADMIN/SYS_ADMIN still keeps the runtime's default set (CHOWN, SETUID, NET_RAW…), so with those failing too this weight understates the gap. |
| rbac-2 | ServiceAccounts use namespace-scoped RoleBindings | Scoping reduces blast radius; medium because cluster roles may be legitimate. |
| rbac-3 | No stale/dangling role bindings | Hygiene; low exploitability on its own. |
| rbac-4 | Default ServiceAccounts don't auto-mount tokens | Reduces token theft surface for workloads that don't need API access. |
| lens-12 | ECR scan-on-push (cluster repos) | Surfaces known CVEs in the images this cluster actually pulls. Medium because scanning *reports* — on its own it does not stop a vulnerable image from being deployed. |
| sec-3 / sec-7 / sec-13 / sec-14 / sec-19 / sec-20 / sec-22 / sec-24 / sec-34 | Governance/process (IAM mapping, kube-system access, env separation, CIS, change mgmt, EFS, secrets strategy, rotation) | Real risk-reduction practices, interview-scored. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| sec-5 | Dedicated cluster-creation role | Process nicety; minimal runtime risk. Interview-scored. |
| sec-8 | External Secrets Operator | KMS envelope encryption already covers the baseline; ESO is an enhancement. |
| sec-12 | Explicit `imagePullPolicy` | Reproducibility detail, not a security exposure. |
| sec-17 | Access-entry (API) auth mode | Modern default; low direct risk either way. |
| sec-23 | EFS encryption in transit | Applies only if EFS is used; niche. Interview-scored. |
| sec-27 / sec-28 | Service mesh / mTLS | Strong for zero-trust, but most clusters run fine without a mesh. |
| sec-32 | Image signing | Supply-chain enhancement; adoption still uncommon. Interview-scored. |
| sec-35 / sec-36 / sec-37 | Rotation cadence, compliance scanning extras | Maturity practices; interview-scored. |
| net-1 | Subnets have ≥100 free IPs | Capacity planning; only bites at scale. |
| net-3 | VPC CNI prefix delegation | IP-density optimization, not a security control. |
| lens-13 | ECR immutable tags | Stops a reviewed tag being re-pointed at different content. Low because it hardens the registry rather than anything already running in the cluster. |

---

## Reliability

### High
| ID | Check | Why High |
|----|-------|----------|
| rel-1 | Nodes span multiple AZs | Single-AZ means an AZ outage takes the whole cluster down. |
| rel-6 | Containers have readiness probes | Without them, traffic routes to unready pods → user-facing outages. |
| rel-7 | Deployments run >1 replica | Single-replica workloads have no failover; any pod loss is downtime. |
| rel-12 | Backup/snapshot policy exists | No backups = permanent data loss on failure. **Interview-scored**, and the only High-weighted question that is: the scorer emits it on the governance track, so in `auto` mode it reports Not Assessed and never enters the Reliability number. A high Reliability score is not evidence that backups exist — ask. |
| rel-13 | Monitoring & alerting deployed | Without it, failures go unnoticed until users complain. |
| lens-15 | Worker nodes in private subnets | Public-subnet nodes are directly reachable and a resilience/security risk. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| rel-2 | PodDisruptionBudgets cover deployments | Prevents mass eviction during drains; matters mostly during maintenance. |
| rel-3 | Containers set CPU/memory limits | Prevents noisy-neighbor starvation; some teams intentionally omit CPU limits. |
| rel-4 | Cluster autoscaler / Karpenter present | Handles capacity; static clusters can still be reliable. |
| rel-5 | HPAs on deployments | Absorbs load spikes; not every workload needs autoscaling. |
| rel-8 | Pod anti-affinity | Spreads replicas off single nodes; incremental over multi-replica. |
| rel-9 | Topology spread constraints | Spreads across zones; refinement of anti-affinity. |
| rel-14 | HA ingress controller | Matters only when ingress is on the critical path; interview-scored. |
| rel-18 | Deployments use RollingUpdate | Enables zero-downtime deploys; default for most. |
| rel-21 | StatefulSets use persistent volume templates | Prevents data loss on reschedule for stateful apps. |
| rel-22 | StatefulSets run HA (>1 replica) | HA for stateful apps; many are single-instance by design. |
| lens-14 | NAT gateway per AZ | Avoids a cross-AZ egress SPOF; cost/resilience tradeoff. |
| rel-10 | Volume snapshot class configured | Enables backups; interview-scored. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| rel-11 | PVCs are Bound | A symptom check, not a design control. |
| rel-15 | LoadBalancer services used appropriately | Architecture choice, not a reliability gate; interview-scored. |
| rel-16 | Service mesh | Adds resilience features but optional. |
| rel-17 | DNS / service discovery setup | CoreDNS is present by default; interview-scored. |
| rel-19 | DaemonSets use RollingUpdate | Minor operational detail. |
| rel-20 | DaemonSets set requests+limits | Hygiene for node agents. |
| rel-23 | Distributed tracing | Observability enhancement, not availability. |
| lens-2 | NodeLocal DNSCache | Latency/reliability optimization at scale. |
| lens-3 | CoreDNS autoscaler | Only matters at high DNS QPS. |

---

## Operational Excellence

### High
| ID | Check | Why High |
|----|-------|----------|
| ope-5 | Control-plane metrics collected | You can't operate what you can't see; core observability. |
| ope-6 | Control-plane logging enabled (all types) | Without logs, incident response and audit are blind. |
| ope-11 | CloudTrail enabled | The record of who did what in the account; essential for forensics. |
| ope-12 | Kubernetes audit logging on | API-level audit trail for the cluster. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| ope-1 | Infrastructure as Code | Reproducibility/drift control; interview-scored. |
| ope-2 | AWS integration controllers (LB/ExternalDNS/EBS-CSI) | Operational glue; partial adoption is common. |
| ope-7 | Node-level metrics (node-exporter) | Complements control-plane metrics. |
| ope-8 | Centralized log forwarding | Aggregation aids ops; apps can log without it short-term. |
| ope-9 | Alarms on API 401/403 spikes | Early breach signal; interview-scored. |
| ope-13 | Documented upgrade plan | Avoids falling out of support; process. Interview-scored. |
| ope-15 | EKS-managed node groups (or Auto Mode) | Managed lifecycle/patching; self-managed is viable but heavier. |
| ope-16 | Core addons EKS-managed | Keeps CNI/CoreDNS/kube-proxy patched. |
| ope-19 | Capacity planning process | Prevents saturation; process. Interview-scored. |
| lens-7 | VPC CNI addon healthy/current | Networking foundation health. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| ope-3 | GitOps (ArgoCD/Flux) | Great practice, but not required for a sound cluster. |
| ope-4 | Templating (Helm/Kustomize) | Packaging preference. Interview-scored. |
| ope-10 | CNI metrics helper | Niche observability add-on. |
| ope-14 | Non-prod test environment | Org practice, interview-scored. |
| ope-17 / ope-18 | Job/CronJob config hygiene | Only relevant if batch workloads exist. |
| fargate-1..4 | Fargate profile/logging specifics | Apply only to Fargate clusters. |
| lens-1 | Node Problem Detector | Useful signal, easily lived without. |

---

## Performance Efficiency

### High
| ID | Check | Why High |
|----|-------|----------|
| perf-1 | Containers set CPU/memory requests | Without requests the scheduler can't place or bin-pack correctly — the root of both waste and contention. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| perf-3 | Appropriate/modern instance types | Right-sizing the fleet; impacts perf and cost. |
| perf-7 | Node utilization in a healthy band | Efficiency signal; needs live metrics (interview). |
| lens-6 | EKS-optimized AMIs (Bottlerocket/AL2023) | Better boot/runtime characteristics. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| perf-2 | Vertical Pod Autoscaler | Right-sizing aid; recommendation-mode optional. |
| perf-4 | RollingUpdate strategy | Overlaps rel-18. |
| perf-5 | Scheduling constraints tuned | Refinement of affinity/spread. |
| perf-6 | Instance-type diversity | Helps Spot/availability; not core perf. |
| lens-5 | Standard `app.kubernetes.io/*` labels | Tooling/consistency nicety. |
| lens-8 | CoreDNS `ndots` tuned | Micro-optimization for DNS-heavy apps. |
| lens-9 | LB `externalTrafficPolicy: Local` | Preserves source IP / cuts a hop; situational. |
| lens-10 | Topology-aware routing | Cross-AZ traffic optimization. |

---

## Cost Optimization

### High
| ID | Check | Why High |
|----|-------|----------|
| cost-6 | No idle/unused PersistentVolumes | Idle EBS bills every hour for zero value — direct, ongoing waste. |
| cost-8 | No Released/Available (orphaned) volumes | Same as above from the orphaned-resource angle; pure leak. |
| cost-9 | Storage on gp3 (not gp2) | gp3 is ~20% cheaper on storage. Below ~1,000 GiB it is also faster at baseline, so migrating is a straight win. At or above ~1,000 GiB a gp2 volume already exceeds gp3's default 3,000 IOPS, and migrating without provisioning `iops: min(size × 3, 16000)` is a **performance downgrade** — gp2's baseline stops climbing at 16,000 IOPS, reached at 5,334 GiB, and every larger gp2 volume gets the same 16,000, so an uncapped `size × 3` formula overshoots gp2 parity (and overpays for IOPS never delivered) above that size. See [cost-analysis.md](cost-analysis) for the crossover. Still weighted High because the overspend is unforced, not because the migration is free. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| cost-1 | ResourceQuotas per namespace | Caps runaway consumption; governance guardrail. |
| cost-2 | LimitRanges per namespace | Sensible defaults prevent oversized pods. |
| cost-5 | Storage requested-vs-used efficiency | Right-sizing; needs usage data (interview). |
| cost-7 | Cost-allocation tags present | You can't optimize what you can't attribute. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| cost-3 | Off-peak / event-driven scaling (KEDA) | Savings for bursty workloads; not universal. |
| cost-4 | Data-transfer cost monitoring | Visibility practice; interview-scored. |
| lens-4 | Cost-visibility tooling (Kubecost/OpenCost) | Helpful, but chargeback is optional. |
| lens-16 | VPC endpoints for S3/ECR/STS | Trims NAT data-processing cost; modest savings. |

---

*Note: `lens-12` and `lens-13` (ECR scan-on-push, immutable tags) are scored under **Security**, not
here — they are supply-chain controls, and `cost-optimization.md` records the move. Do not look for them
in a low Cost score.*

*Note: the compute-cost heavyweights — Graviton, Spot, and Extended Support — are handled in
[cost-analysis.md](cost-analysis) as narrative savings opportunities, not scored pillar questions,
because they are recommendations rather than pass/fail controls.*
