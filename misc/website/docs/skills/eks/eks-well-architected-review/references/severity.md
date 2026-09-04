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

Every measured question carries a WAF-style risk weight used by the reducer's `sev()` map:
**High = 3, Medium = 2, Low = 1**. The pillar score is the severity-weighted average of applicable
answers, so a missing High-risk control moves the number three times as much as a missing Low-risk extra.

**What puts a question in each tier:**
- **High** — absence creates a *direct, exploitable exposure* or a *loss-of-availability / data-loss / cost-leak* that a reasonable operator must fix. These define whether a cluster is fundamentally sound.
- **Medium** — a real best practice that materially reduces risk or waste, but whose absence is survivable or context-dependent.
- **Low** — an optimization or advanced/aspirational practice. Valuable, but many well-run clusters legitimately skip it. Its absence should barely move the score.

Governance questions are unweighted here — they are interview-only and reported separately (Not Assessed in `auto` mode).

---

## Security

### High
| ID | Check | Why High |
|----|-------|----------|
| sec-2 | API server not open to `0.0.0.0/0` | An internet-reachable control plane is the single biggest EKS attack vector. |
| sec-4 | NetworkPolicies present per namespace | Flat pod networking lets one compromised pod reach everything; isolation is baseline containment. |
| sec-6 | IRSA (pod-level IAM via OIDC) | Falling back to node-role credentials gives every pod broad AWS access — huge blast radius. |
| sec-11 | Pod Security Standards enforced | Without PSS, privileged/root pods deploy unchecked — the entry point for most container escapes. |
| sec-18 | OIDC provider associated | Prerequisite for IRSA; without it fine-grained pod IAM is impossible. |
| sec-21 | Cluster EBS volumes encrypted at rest | Unencrypted data at rest is a direct compliance and confidentiality failure. |
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
| sec-10 | Admission webhooks present | Enforcement point for policy; medium because PSS (sec-11) already covers the baseline. |
| sec-15 | Containers set a security context | Good hygiene; overlaps the more specific podsec checks. |
| sec-16 | Admission/policy engine deployed | Enables enforcement; value depends on the policies actually loaded. |
| sec-25 | StorageClasses set `encrypted: true` | Ensures new volumes are encrypted; sec-21 already covers existing ones. |
| sec-31 / net-4 | Separate control-plane vs node security groups | Limits lateral movement; defense-in-depth rather than a direct hole. |
| sec-33 | Runtime threat monitoring (GuardDuty/Falco) | Detection layer; valuable but not a preventive control. |
| adm-1 | ≥5 admission policies loaded | Depth of policy coverage; incremental over having an engine. |
| adm-2 | A policy blocks privileged pods | Reinforces podsec-2; medium as a policy-level backstop. |
| adm-3 | Policies run in enforce (not audit) mode | Audit-only still surfaces issues, so enforce is an upgrade not a baseline. |
| podsec-1 | Containers run as non-root | Important, but readOnlyRoot/no-priv-escalation (in sec-15) blunt the risk. |
| podsec-3 | Pods avoid hostPath mounts | hostPath is a common escape vector but often needed by legit tooling. |
| podsec-5 | Containers drop ALL capabilities | Best practice; partial hardening (podsec-2/4) covers the worst cases. |
| rbac-2 | ServiceAccounts use namespace-scoped RoleBindings | Scoping reduces blast radius; medium because cluster roles may be legitimate. |
| rbac-3 | No stale/dangling role bindings | Hygiene; low exploitability on its own. |
| rbac-4 | Default ServiceAccounts don't auto-mount tokens | Reduces token theft surface for workloads that don't need API access. |
| sec-3 / sec-7 / sec-13 / sec-14 / sec-19 / sec-20 / sec-22 / sec-24 / sec-34 | Governance/process (IAM mapping, kube-system access, env separation, CIS, change mgmt, EFS, secrets strategy, rotation) | Real risk-reduction practices, interview-scored. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| sec-5 | Dedicated cluster-creation role | Process nicety; minimal runtime risk. |
| sec-8 | External Secrets Operator | KMS envelope encryption already covers the baseline; ESO is an enhancement. |
| sec-12 | Explicit `imagePullPolicy` | Reproducibility detail, not a security exposure. |
| sec-17 | Access-entry (API) auth mode | Modern default; low direct risk either way. |
| sec-23 | EFS encryption in transit | Applies only if EFS is used; niche. |
| sec-27 / sec-28 | Service mesh / mTLS | Strong for zero-trust, but most clusters run fine without a mesh. |
| sec-32 | Image signing | Supply-chain enhancement; adoption still uncommon. |
| sec-35 / sec-36 / sec-37 | Rotation cadence, compliance scanning extras | Maturity practices. |
| net-1 | Subnets have ≥100 free IPs | Capacity planning; only bites at scale. |
| net-3 | VPC CNI prefix delegation | IP-density optimization, not a security control. |

---

## Reliability

### High
| ID | Check | Why High |
|----|-------|----------|
| rel-1 | Nodes span multiple AZs | Single-AZ means an AZ outage takes the whole cluster down. |
| rel-6 | Containers have readiness probes | Without them, traffic routes to unready pods → user-facing outages. |
| rel-7 | Deployments run >1 replica | Single-replica workloads have no failover; any pod loss is downtime. |
| rel-12 | Backup/snapshot policy exists | No backups = permanent data loss on failure. |
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
| rel-14 | HA ingress controller | Matters only when ingress is on the critical path. |
| rel-18 | Deployments use RollingUpdate | Enables zero-downtime deploys; default for most. |
| rel-21 | StatefulSets use persistent volume templates | Prevents data loss on reschedule for stateful apps. |
| rel-22 | StatefulSets run HA (>1 replica) | HA for stateful apps; many are single-instance by design. |
| lens-14 | NAT gateway per AZ | Avoids a cross-AZ egress SPOF; cost/resilience tradeoff. |
| rel-10 | Volume snapshot class configured | Enables backups; interview-scored. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| rel-11 | PVCs are Bound | A symptom check, not a design control. |
| rel-15 | LoadBalancer services used appropriately | Architecture choice, not a reliability gate. |
| rel-16 | Service mesh | Adds resilience features but optional. |
| rel-17 | DNS / service discovery setup | CoreDNS is present by default. |
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
| ope-1 | Infrastructure as Code | Reproducibility/drift control; interview + tag signal. |
| ope-2 | AWS integration controllers (LB/ExternalDNS/EBS-CSI) | Operational glue; partial adoption is common. |
| ope-7 | Node-level metrics (node-exporter) | Complements control-plane metrics. |
| ope-8 | Centralized log forwarding | Aggregation aids ops; apps can log without it short-term. |
| ope-9 | Alarms on API 401/403 spikes | Early breach signal; interview-scored. |
| ope-13 | Documented upgrade plan | Avoids falling out of support; process. |
| ope-15 | EKS-managed node groups (or Auto Mode) | Managed lifecycle/patching; self-managed is viable but heavier. |
| ope-16 | Core addons EKS-managed | Keeps CNI/CoreDNS/kube-proxy patched. |
| ope-19 | Capacity planning process | Prevents saturation; process. |
| lens-7 | VPC CNI addon healthy/current | Networking foundation health. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| ope-3 | GitOps (ArgoCD/Flux) | Great practice, but not required for a sound cluster. |
| ope-4 | Templating (Helm/Kustomize) | Packaging preference. |
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
| cost-9 | Storage on gp3 (not gp2) | gp3 is ~20% cheaper with equal/better performance — an unforced overspend if not migrated. |

### Medium
| ID | Check | Why Medium |
|----|-------|-----------|
| cost-1 | ResourceQuotas per namespace | Caps runaway consumption; governance guardrail. |
| cost-2 | LimitRanges per namespace | Sensible defaults prevent oversized pods. |
| cost-5 | Storage requested-vs-used efficiency | Right-sizing; needs usage data (interview). |
| cost-7 | Cost-allocation tags present | You can't optimize what you can't attribute. |
| lens-12 | ECR scan-on-push (cluster repos) | Security-adjacent hygiene on images the cluster uses. |

### Low
| ID | Check | Why Low |
|----|-------|---------|
| cost-3 | Off-peak / event-driven scaling (KEDA) | Savings for bursty workloads; not universal. |
| cost-4 | Data-transfer cost monitoring | Visibility practice; interview-scored. |
| lens-4 | Cost-visibility tooling (Kubecost/OpenCost) | Helpful, but chargeback is optional. |
| lens-13 | ECR immutable tags | Supply-chain hygiene with minor cost impact. |
| lens-16 | VPC endpoints for S3/ECR/STS | Trims NAT data-processing cost; modest savings. |

---

*Note: the compute-cost heavyweights — Graviton, Spot, and Extended Support — are handled in
[cost-analysis.md](cost-analysis) as narrative savings opportunities, not scored pillar questions,
because they are recommendations rather than pass/fail controls.*
