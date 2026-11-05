# C3: posture check ("does my setup contain the next one?")

The question is not "is every setting perfect" but "if one pod is compromised tomorrow, does this cluster keep it contained?". Each check below reads live state, returns one of pass / fail / n.a. / unknown with the evidence it read, and carries a severity. A check that could not read its evidence is `unknown`, never pass.

## How it runs

C3 has two parts, both run by eks-security's own scripts on one collection:

1. **The scripted security pillar.** The checks are adapted from eks-well-architected-review's security pillar (identity and access, network, data protection, workload security, governance), copied into this skill so a posture check does not need a second skill installed. A full five-pillar Well-Architected review stays in eks-well-architected-review.
2. **The containment checks below**, which that pillar does not cover or covers only in part.

| Script | Role |
|---|---|
| `assets/posture_collect.sh` | Read-only collection for the pillar checks, with preflight probes |
| `assets/posture_score.sh` | Scores the pillar checks: one result per check |
| `assets/posture_extra.sh` | Runs the containment checks below, same result format |
| `assets/posture_reduce.sh` | Severity-weighted score with the coverage gate |
| `assets/render_report.py` | Markdown and HTML report |

Order: collect (`posture_collect.sh`), score, extra, reduce, render. C3 does not need the C1 inventory. Scoring: severity weights High 3, Medium 2, Low 1; pass counts full weight, fail zero, n.a. is left out; below 50% of applicable weight read, the score says "incomplete" and no number is given.

The access needed is in [read-only-access.md](read-only-access.md), C3 section.

"Workload namespaces" below means every namespace except `kube-system`, `kube-public`, `kube-node-lease` and namespaces the team names as system (for example the GuardDuty agent's and a policy engine's). The report prints the list it used.

## Containment checks

### A compromised pod can't reach the node role

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-1 | IMDSv2 required on every node | `aws ec2 describe-instances` for the node instance ids: `MetadataOptions.HttpTokens` | pass: every instance `required`; fail: any `optional`; unknown: instances not readable; Auto Mode nodes whose instances are not returned: n.a. with the note "AWS-managed" | High | adapted (lens-11) |
| PC-2 | IMDS hop limit 1 on nodes that run non-host-network pods | same call: `MetadataOptions.HttpPutResponseHopLimit` | pass: every instance `1`; fail: any `2` or more, listing the node groups; unknown as PC-1 | High | added |

Why: with IMDSv1 allowed, or IMDSv2 with a hop limit above 1, any pod can fetch the node role's credentials and act as the node. A workload that genuinely needs IMDS from a pod should get its own identity (PC-7) instead of a higher hop limit.

### A compromised pod can't move sideways

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-3 | NetworkPolicy is enforced | Standard cluster: `aws eks describe-addon --addon-name vpc-cni` `configurationValues` has `enableNetworkPolicy: "true"`, or another enforcing engine runs (Calico or Cilium pods). Auto Mode: ConfigMap `kube-system/amazon-vpc-cni` key `enable-network-policy-controller: "true"` ([Auto Mode network policies](https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html)) | pass: enforcement on; fail: off and no other engine; unknown: not readable | High | added |
| PC-4 | Default-deny ingress in every workload namespace | `kubectl get networkpolicies -A -o json`: a policy with `podSelector: {}`, `policyTypes` including `Ingress` and no `ingress` rules | pass: every workload namespace has one; fail: list the namespaces without; n.a.: no workload namespaces; unknown: networkpolicies not readable | High | extends sec-4 (policies exist) |
| PC-5 | Egress is controlled | same read: a default-deny `Egress` policy per workload namespace, or egress rules on the policies that select its pods | pass: every workload namespace; fail: list the rest | Medium | added |

Why: without enforcement, NetworkPolicy objects are text. Without a default deny, one compromised pod can reach every service in the cluster; without egress control it can reach the internet and the instance metadata of neighbours. PC-4 and PC-5 count only when PC-3 passes; with PC-3 failing they report fail with "not enforced".

### A compromised pod can't escalate

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-6a | Pod Security Admission enforce level per workload namespace | `kubectl get namespaces -o json`: label `pod-security.kubernetes.io/enforce` | pass: `baseline` or `restricted` on every workload namespace (report which; `restricted` is the target for workloads); fail: missing or `privileged`, listing them | High | extends sec-11 (labels exist) |
| PC-6b | No privileged or host-sharing pods outside system namespaces | `workloads.json` pod specs: `securityContext.privileged`, `hostPath` volumes, `hostNetwork`, `hostPID`, `hostIPC` | pass: none in workload namespaces; fail: list each pod and field | High | extends podsec-2, podsec-3 (privileged, hostPath) |

Why: a privileged or host-sharing pod is a node compromise waiting to happen; PSA is the admission gate that stops the next one being created.

### A compromised pod can't use broad identity

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-7 | Node role carries only node permissions | `aws eks describe-nodegroup` `nodeRole` (Auto Mode: NodeClass `spec.role`); `aws iam list-attached-role-policies` and `list-role-policies` for that role | pass: only the EKS worker node, CNI and ECR pull managed policies; fail: any other attached or inline policy, named; unknown: IAM not readable | High | added |
| PC-8 | No workload holds cluster-admin | `kubectl get clusterrolebindings -o json`: bindings to `cluster-admin` whose subjects are service accounts outside `kube-system`; `aws eks list-associated-access-policies` per access entry for the cluster admin policy, reported as a count | pass: no workload service account bound; fail: list them; access entries with the admin policy are listed for review, not failed | High | extends rbac-1 |

Why: if workloads lean on the node role, every pod on the node holds those rights. A workload with cluster-admin turns a pod compromise into a cluster compromise.

### It is seen

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-9 | Audit and authenticator logs on | `aws eks describe-cluster` `cluster.logging.clusterLogging`: types `audit` and `authenticator` enabled | pass: both; fail: either missing | High | extends sec-26 (audit only) |
| PC-10 | GuardDuty EKS audit log monitoring on | `aws guardduty list-detectors`, `get-detector`: feature `EKS_AUDIT_LOGS` status `ENABLED` | pass: enabled; fail: no detector or disabled; unknown: not readable | High | added |
| PC-11 | GuardDuty runtime monitoring on, agent running | `get-detector`: feature `RUNTIME_MONITORING` or `EKS_RUNTIME_MONITORING` `ENABLED`; the GuardDuty agent DaemonSet is present and ready on every Linux node | pass: feature on and agent on all nodes; fail: feature off or agent missing on nodes (listed) | Medium | extends sec-33 (an agent is present) |

Feature names as in the [GuardDuty API reference](https://docs.aws.amazon.com/guardduty/latest/APIReference/API_DetectorFeatureConfiguration.html), checked 2026-11-05. Why: containment is also about finding out. Audit history from before logging was turned on cannot be recovered.

### The API is not open

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-12 | Public endpoint not open to the internet | `describe-cluster` `resourcesVpcConfig.endpointPublicAccess` and `publicAccessCidrs` | pass: public access off, or CIDRs that exclude `0.0.0.0/0`; fail: public with `0.0.0.0/0` | High | adapted (sec-1, sec-2) |

### Supply chain

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-13 | Registry scanning is enhanced with continuous rescan | `aws ecr get-registry-scanning-configuration`: `scanType` `ENHANCED` and a rule with `scanFrequency` `CONTINUOUS_SCAN` covering the cluster's repositories | pass: both; fail: basic scanning or scan on push only | Medium | extends lens-12 (scan on push) |
| PC-14 | Running images pinned by digest | `inventory.json` `images[].pinned_by_digest` | pass: every workload image; fail: list images pinned by tag; report the share | Medium | extends sec-12 (accepts an explicit tag) |
| PC-15 | Admission policy for signed or allowed images, where an engine is installed | Kyverno `ClusterPolicy` with a `verifyImages` rule, or a Gatekeeper constraint on image sources | pass: present and in enforce mode; fail: engine installed, no such policy; n.a.: no engine installed (reported, with eks-best-practices guidance on choosing one) | Medium | extends sec-32 |

Why: continuous rescan surfaces a new CVE on an image already running; digest pinning makes "what is running" a fact C1 can compare; admission policy stops an unknown image starting.

### Currency

| Id | Check | Live evidence | Pass / fail / n.a. / unknown | Severity | Relation to the pillar |
|---|---|---|---|---|---|
| PC-16 | No component below a fixed version | C1 `findings.json` from a sweep (see [cve-advisory-review.md](cve-advisory-review.md)) | pass: no `exposed`; fail: each exposed finding with its priority; unknown: no sweep run or coverage incomplete | per finding | added |

Only a gap to a published fixed version is a C3 finding. A component that is merely behind the latest release, with no advisory, is not: route it to eks-upgrade-check, which owns version lag.

## Repository checks (optional input)

When the team names a local repository path, three checks run on its files and are reported in their own section, never mixed into the cluster score:
- a lockfile is committed for each package manifest found (for example `package-lock.json`, `poetry.lock`, `go.sum`);
- every Dockerfile `FROM` line pins its base image by digest;
- no manifest, Helm values file or Dockerfile uses the tag `latest`.

These are read with file reads only; nothing is built or installed.

## Output

- Per check: id, result, evidence (the command and field, with the values read), severity.
- Score: from `posture_reduce.sh`, with its coverage line.
- One summary row per containment layer: "would this contain a compromised pod?" yes / partly / no / unknown, from that layer's checks.
- Fixes as printed commands or manifests for the team to review (for example a default-deny NetworkPolicy per namespace, a launch template with hop limit 1, the PSA label). Nothing is applied. Hardening knowledge behind each fix is in eks-best-practices and the layer references of this skill.
