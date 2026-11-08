# C3: posture check ("does my setup contain the next one?")

The question is not "is every setting perfect" but "if one pod is compromised tomorrow, does this cluster keep it contained?". Each check below reads live state, returns a result with the evidence it read, and carries a severity. A check that could not read its evidence is `unknown`, never pass.

## How it runs

This port runs no scripts. The agent makes the reads named in each row through the Agent Space's read-only AWS and Kubernetes API access, applies the row's rule and scores the result. The Claude Code skill runs the same checks as scripts (`posture_collect.sh`, `posture_score.sh`, `posture_extra.sh`, `posture_reduce.sh`); each row here carries that skill's check id (`SEC-POSTURE-<n>`) and, for checks it copied from the Well-Architected review's security pillar, the pillar question id, so the two copies report the same check under the same id. Of that skill's 64 checks this port walks the containment subset below; the rest of the copied pillar is not ported and the report lists it under "not checked". Two rows are port-only (marked): they are reported but kept out of the score and the layer verdicts, so the score rule is the scripted one. The score and layer verdicts are computed over these 20 checks, so they are not comparable with the scripted skill's 49-check score.

The access needed is in [read-only-access.md](read-only-access.md), C3 section. Checks that read RBAC objects or policy engine objects need the supplementary ClusterRole named there; without it they are `unknown`, never pass.

## Results, score and coverage

These rules are the Claude Code skill's `posture_reduce.sh` rules.

- **Bucket.** For a check over many objects, count the objects it applies to and the share that passes: 90% or more is `all`, 70% or more `most`, more than 0 `some`, 0 `none`, nothing to count `na`. All-or-nothing checks give `all` or `none`. A bucketed check at 90% or more reads pass; the report still lists it, with its failing objects, as `pass (exceptions)` (for example one node open to IMDS under SEC-POSTURE-55, or one namespace without default-deny under SEC-POSTURE-56).
- **Result.** `all` is pass; `most`, `some` and `none` are fail; `na` is n.a.; a read that was refused or failed is `unknown`.
- **Coverage gate.** A check is answered when its state is `all`, `most`, `some` or `none` (`na` and `unknown` are not answered). With fewer than half of the scored checks answered the report says "incomplete" and gives no score.
- **Score.** Sum of points times weight over answered checks, divided by the sum of their weights, rounded: points `all` 100, `most` 75, `some` 50, `none` 0; weight high 3, medium 2, low 1.
- **Layer verdict** ("would this contain a compromised pod?"), over the scored checks of the layer: `unknown` when none is answered; `not-contained` when any high-severity check fails; `contained` when every answered check passes and none is `unknown`; `partly` otherwise.
- **Workload namespaces** are every namespace whose name does not start with `kube-` or `amazon-`. The report prints the list it used.

## Containment checks

### Node credentials (layer node-credential)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-46 (lens-11) | IMDSv2 required on every node | `aws ec2 describe-instances` for the cluster's node instances: `MetadataOptions.HttpTokens` | Per running instance: pass when `required`; bucketed over instances | high |
| SEC-POSTURE-55 | Pods cannot reach IMDS | same read: `HttpEndpoint`, `HttpTokens`, `HttpPutResponseHopLimit`; `kubectl get nodes -o json` to tell Auto Mode nodes (label `eks.amazonaws.com/compute-type: auto`) | Per running Linux instance: pass when the endpoint is `disabled`, or `HttpTokens` is `required` with hop limit 1; bucketed; list the failing instances by node type (managed node group, Karpenter node pool, Auto Mode, other); Windows not assessed; no Linux instance: na | high |
| Port only: node role | Node role carries only node permissions | `aws eks describe-nodegroup` `nodeRole` (Auto Mode: NodeClass `spec.role`); `aws iam list-attached-role-policies` and `list-role-policies` for that role | pass: only the EKS worker node, CNI and ECR pull managed policies; fail: any other attached or inline policy, named. Reported, not scored | high |

Why: with IMDSv1 allowed, or IMDSv2 with a hop limit above 1, any pod can fetch the node role's credentials and act as the node. A workload that needs AWS access from a pod should get its own identity (EKS Pod Identity or IRSA) instead of a higher hop limit.

### Lateral movement (layer lateral-movement)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-26 (sec-4) | NetworkPolicy is enforced, and policies exist | `kubectl get daemonsets -A -o json`: the `kube-system/aws-node` DaemonSet's `aws-eks-nodeagent` container runs with `--enable-network-policy=true`, or a ready `calico-node` or `cilium` DaemonSet runs. Auto Mode: ConfigMap `kube-system/amazon-vpc-cni` key `enable-network-policy-controller: "true"` ([Auto Mode network policies](https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html)); `kubectl get networkpolicies -A -o json` | Enforcement off and no other engine: fail. Enforcement on: bucket the workload namespaces that have any NetworkPolicy | high |
| SEC-POSTURE-56 | Default-deny ingress per workload namespace | `kubectl get networkpolicies -A -o json` and `kubectl get namespaces -o json` | A namespace passes when it has a policy with an empty `podSelector`, `Ingress` in `policyTypes` (implied when absent) and no ingress rule; bucketed; list the namespaces without one | high |
| SEC-POSTURE-57 | Egress limited per workload namespace | same reads | A namespace passes when a policy with an empty `podSelector` lists `Egress` in `policyTypes`; bucketed. Allowed destinations are not judged | medium |

Why: without enforcement, NetworkPolicy objects are text. Without a default deny, one compromised pod can reach every service in the cluster; without egress control it can reach the internet.

### Privilege (layer privilege)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-34 (sec-11) | Pod Security Admission enforce label per workload namespace | `kubectl get namespaces -o json`: label `pod-security.kubernetes.io/enforce` | A namespace passes with `baseline` or `restricted` (report which; `restricted` is the target for workloads); bucketed; list the rest | high |
| SEC-POSTURE-42 (podsec-2) | No privileged containers | `kubectl get pods -A -o json` (the agent's own read): `securityContext.privileged` per container | Per container, init and ephemeral container of unfinished workload pods: any privileged container fails the check (`none`); otherwise `all`; list each failing pod and container; Windows pods not assessed | high |
| SEC-POSTURE-43 (podsec-3) | No hostPath volumes | same read: `spec.volumes[].hostPath` | any workload pod with a hostPath volume fails the check (`none`); otherwise `all`; list each failing pod | medium |
| SEC-POSTURE-58 | No host namespaces | same read: `spec.hostNetwork`, `hostPID`, `hostIPC` on pods not finished (phase other than `Succeeded` or `Failed`) | Any workload pod with one of them true fails the check; otherwise pass; no workload pods: na | high |
| SEC-POSTURE-10 (rbac-1) | cluster-admin held only by the built-in subjects | `kubectl get clusterrolebindings -o json`; ConfigMap `kube-system/aws-auth` | Fail on any `cluster-admin` binding subject other than Group `system:masters` and User `eks:addon-manager`, and on any `system:masters` mapping in `aws-auth` (not read when the authentication mode is `API`); list them | high |

Why: a privileged or host-sharing pod is a node compromise waiting to happen; PSA is the admission gate that stops the next one being created. A workload with cluster-admin turns a pod compromise into a cluster compromise.

### Identity (layer identity)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-64 | Cluster admin through an access policy | `aws eks describe-cluster` `accessConfig`; `aws eks list-access-entries`; per entry `aws eks list-associated-access-policies --principal-arn <arn>` | Admin is `AmazonEKSClusterAdminPolicy` at any scope, or `AmazonEKSAdminPolicy` at cluster scope. The roles the team names as expected admins (the cluster creator, a break-glass role) are listed, not failed; any other holder fails the check, listed with its policy. An entry's `kubernetesGroups` are not read: a group binding to cluster admin shows under SEC-POSTURE-10. `CONFIG_MAP` authentication mode: na; on it the cluster creator holds `system:masters` in no visible configuration, and the evidence prints `bootstrapClusterCreatorAdminPermissions=<value>`. When `bootstrapClusterCreatorAdminPermissions` is true and the team named no creator role, say one holder is likely the creator (the EKS API does not name it) | high |

Fix for SEC-POSTURE-64, printed only: grant each listed principal what it needs at a narrower scope (`AmazonEKSAdminPolicy` with a namespace access scope, or a Kubernetes group bound to a narrower RBAC role), then `aws eks disassociate-access-policy --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN> --policy-arn arn:aws:eks::aws:cluster-access-policy/<the listed policy>`, keeping one break-glass admin role whose use is logged ([EKS best practices: identity and access](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html)).

### Detection (layer detection)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-52 (sec-26) | Audit log on | `aws eks describe-cluster` `cluster.logging.clusterLogging` | pass when type `audit` is enabled | high |
| SEC-POSTURE-59 | Authenticator log on | same read | pass when type `authenticator` is enabled | medium |
| SEC-POSTURE-60 | GuardDuty EKS Audit Log Monitoring | `aws guardduty list-detectors`, `get-detector` | pass when an `ENABLED` detector has feature `EKS_AUDIT_LOGS` `ENABLED`; no detector or the feature off: fail. Configuration only, findings are never read | medium |
| SEC-POSTURE-61 | GuardDuty Runtime Monitoring | same reads | pass when feature `RUNTIME_MONITORING` or `EKS_RUNTIME_MONITORING` is `ENABLED`; report the `EKS_ADDON_MANAGEMENT` setting | medium |
| SEC-POSTURE-48 (sec-33) | A runtime security agent is present | `aws eks list-addons` / `describe-addon`; `kubectl get pods -A -o json` | pass when a GuardDuty add-on is installed, or DaemonSet pods named for the GuardDuty agent, Falco, Sysdig or Tetragon run | medium |

Feature names as in the [GuardDuty API reference](https://docs.aws.amazon.com/guardduty/latest/APIReference/API_DetectorFeatureConfiguration.html), checked 2026-11-05. Why: containment is also about finding out. Audit history from before logging was turned on cannot be recovered.

### API exposure (layer api-exposure)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-1 (sec-1) | Private endpoint access on | `aws eks describe-cluster` `resourcesVpcConfig.endpointPrivateAccess` | pass when true | medium |
| SEC-POSTURE-2 (sec-2) | Public endpoint not open to the internet | same read: `endpointPublicAccess`, `publicAccessCidrs` | pass: public access off, or `publicAccessCidrs` restricted; fail: public with a `/0` prefix, or CIDRs that together cover the whole IPv4 range; a CIDR that cannot be parsed makes it `some` (fail, coverage not measured) | high |

### Supply chain (layer supply-chain)

| Id | Check | Reads the agent makes | Rule | Severity |
|---|---|---|---|---|
| SEC-POSTURE-62 | Registry scanning is enhanced with continuous rescan | `aws ecr get-registry-scanning-configuration` | `all` (pass): `ENHANCED` with a `CONTINUOUS_SCAN` rule whose filter is `*`; `some` (fail): `ENHANCED` with narrower or on-push rules only; `none`: `BASIC` or no rule | medium |
| SEC-POSTURE-63 | Workload images pinned by digest | `kubectl get pods -A -o json` (the agent's own read): `image` of every container and init container of unfinished workload pods | Per container: pass when the image ends in `@sha256:<64 hex>`; bucketed; list the rest | low |
| Port only: image admission | Admission policy for signed or allowed images, where an engine is installed | Kyverno `ImageValidatingPolicy` (`policies.kyverno.io/v1`) or legacy `ClusterPolicy` with a `verifyImages` rule, or a Gatekeeper constraint on image sources | pass: present and enforcing (`spec.validationActions` holds `Deny`; legacy: `failureAction: Enforce`); fail: engine installed, no such policy; n.a.: no engine. Reported, not scored (the scripted copy treats image signing, sec-32, as a governance question) | low |

Why: continuous rescan surfaces a new CVE on an image already running; digest pinning makes "what is running" a fact C1 can compare; admission policy stops an unknown image starting.

## Currency rule

No posture check judges component versions. Version exposure comes from a C1 sweep ([cve-advisory-review.md](cve-advisory-review.md)), reported beside the posture result. Only a gap to a published fixed version is a security finding. A component that is merely behind the latest release, with no advisory, is not: plain version lag goes to eks-upgrade-check against a target version, or to eks-operation-review with no target version. Issue 348's currency group (behind latest) is not checked in this version; add-on available versions are read in the C1 inventory (`eks:DescribeAddonVersions`) for a manual read.

## Repository checks (not in this port)

The Claude Code skill can walk a manual repository check list (lockfiles committed, base images pinned by digest, no `latest` tag) when the team names a local path; it is not scripted there either. The Agent Space has no file access to a team's repository, so this port does not run it; the report says so under "not checked".

## Output

- Per check: id (with the pillar question id where there is one), result (a pass with failing objects reads `pass (exceptions)`), evidence (the read and field, with the values read), severity, layer.
- Score: by the rules above, with its coverage line, or "incomplete".
- One verdict row per containment layer.
- Fixes as printed commands or manifests for the team to review (for example a default-deny NetworkPolicy per namespace, a launch template with hop limit 1, the PSA label, scoping an admin access entry). Nothing is applied. Hardening knowledge behind each fix is in the layer references of this skill.
