# Security Event Response

What to do when a security event touches an EKS cluster: a new CVE or advisory, a compromised image or package, a leaked credential, or a suspicious runtime finding. One generic workflow covers every event type, in seven steps: **scope, quick record, contain at once (proposed only), snapshot and investigate after isolation, remediate, verify, record.** Detection (Layer 5, [runtime-security.md](runtime-security.md)) and audit logging (Layer 6, [audit-logging.md](audit-logging.md)) produce the signals; this reference is how you respond.

**Read and propose only.** The agent does every read below through the Agent Space's read-only AWS and Kubernetes API access; the commands show the equivalent read so the team can repeat it. A read the Agent Space is not granted (for example pod logs or IAM) is printed as a command for the team to run, and the record says it was not read by the agent. Every change (NetworkPolicy, cordon, identity revocation, admission block, patch) is printed as a command or manifest for the team to review and run. The agent never applies, patches, scales, deletes, cordons, execs into a pod or reads a Secret's data.

## Before an event (prerequisites)

- **Detective signal:** GuardDuty EKS Protection and Runtime Monitoring, findings to Security Hub ([runtime-security.md](runtime-security.md)).
- **Forensic trail:** control-plane `audit` and `authenticator` logs, CloudTrail, VPC Flow Logs, with retention that meets the regime ([audit-logging.md](audit-logging.md)).
- **A rehearsed runbook** that maps common detections (container breakout, reverse shell, crypto-mining, anomalous API call, leaked credential) to these steps and to owners. Practice it in game days; the [AWS Security Incident Response Guide](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/welcome.html) covers the account-level process.
- **Design choices that make response possible:** immutable, minimal nodes (Bottlerocket, Auto Mode) make "replace the node" the clean default; least-privilege workload IAM (Pod Identity or IRSA) limits blast radius; default-deny NetworkPolicy per namespace makes an isolation policy a small delta; signed images with admission control make "redeploy from known-good" trustworthy.

## Event types

| Event | Step 1 scopes by | Step 2 records | Typical containment proposal | Typical remediation |
|---|---|---|---|---|
| **New CVE or advisory** | Component and installed version (run [cve-advisory-review.md](cve-advisory-review.md) first) | Specs, digests and logs of the affected pods, if the team will contain them | Usually none beyond the advisory's workaround, if it has one | Patched add-on, AMI or image on the emergency path |
| **Compromised image** (malware, known-bad, exploited CVE) | Image digest: every pod running it | Specs, logs and nodes of every pod running the digest | Pod-scoped isolation of those pods; block the digest at admission | Rebuild on a clean, patched base; redeploy by digest |
| **Compromised package** (a dependency in an image) | Images whose lockfile or SBOM contains the package version; then their pods | Same as compromised image, plus the lockfile or SBOM that names the package | Pod-scoped isolation; block the affected digests | Rebuild from a lockfile pinned to a clean version, in an isolated build step |
| **Leaked credential** (access key, role session, service account token) | The principal: which roles, Pod Identity associations, IRSA service accounts and pods use it | The principal's attached policies and the pods and service accounts that use it | Revoke or rotate the credential; revoke the role's active sessions | Rotate secrets the principal could read; narrow the role's policy |
| **Suspicious runtime finding** (GuardDuty, Falco, a CNAPP) | The finding's pod, node, namespace, service account and image | The finding as exported, plus the pod, node and identity records | Pod-scoped isolation; cordon the node; revoke the pod's identity | Close the entry vector (patch, permission, misconfiguration); replace the node |

## Step 1: Scope

Answer: which clusters, namespaces, workloads, images (by digest), packages and identities are involved. Start from the inventory [cve-advisory-review.md](cve-advisory-review.md) reads when a C1 run exists; otherwise read live.

| Question | Equivalent read-only command | Field that answers it |
|---|---|---|
| Which node runs a known pod? | `kubectl get pod <pod> -n <ns> -o jsonpath='{.spec.nodeName}{"\n"}'` | `.spec.nodeName` |
| Which pods belong to a compromised workload? | `kubectl get deploy <name> -n <ns> -o jsonpath='{.spec.selector.matchLabels}'` then `kubectl get pods -n <ns> -l <key>=<value> -o wide` | label selector; `NODE` column |
| Which pods run a given image, by digest? | `kubectl get pods -A -o json \| jq -r '.items[] \| . as $p \| .status.containerStatuses[]? \| select(.imageID \| contains("<sha256:digest>")) \| "\($p.metadata.namespace) \($p.metadata.name) \($p.spec.nodeName)"'` | `.status.containerStatuses[].imageID` (the digest actually running; `.spec.containers[].image` is only the reference asked for) |
| Which pods use a compromised service account? | `kubectl get pods -n <ns> -o json \| jq -r '.items[] \| select(.spec.serviceAccountName=="<sa>") \| "\(.metadata.name) \(.spec.nodeName)"'` | `.spec.serviceAccountName` |
| Which IAM role does that service account get (Pod Identity)? | `aws eks list-pod-identity-associations --cluster-name <c> --namespace <ns> --service-account <sa>` then `aws eks describe-pod-identity-association --cluster-name <c> --association-id <id>` | `association.roleArn` (and `targetRoleArn` for cross-account chaining) |
| Which IAM role does it get (IRSA)? | `kubectl get sa <sa> -n <ns> -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'` | the `eks.amazonaws.com/role-arn` annotation |
| What can that role do? | `aws iam get-role --role-name <r>`, `aws iam list-attached-role-policies --role-name <r>`, `aws iam list-role-policies --role-name <r>` | `AssumeRolePolicyDocument` (who can assume it), attached and inline policy names |
| Which Kubernetes rights does the identity hold? | `kubectl get rolebindings,clusterrolebindings -A -o json \| jq -r '.items[] \| select(any(.subjects[]?; .name=="<sa-or-user>")) \| "\(.metadata.namespace // "cluster") \(.metadata.name) \(.roleRef.name)"'` | `.roleRef.name` per binding |
| Which IAM principals have cluster access? | `aws eks list-access-entries --cluster-name <c>` | `accessEntries[]` |
| Which node group or NodePool, and is it Auto Mode? | `kubectl get node <node> --show-labels`; `aws eks describe-cluster --name <c> --query cluster.computeConfig.enabled` | label `eks.amazonaws.com/compute-type=auto`; `computeConfig.enabled` |

For a compromised package, the cluster cannot see lockfiles: ask for the repository path, find the lockfiles that pin the affected version, map them to image repositories, then to digests and pods with the image query above.

**Not exposed path:** when step 1 finds nothing in scope, write the record (step 7) with what was read and when, and stop.

## Step 2: Quick record (seconds)

AWS's guide puts isolation first: "Your first course of action should be to isolate the damage" ([EKS Best Practices: Incident response and forensics](https://docs.aws.amazon.com/eks/latest/best-practices/incident-response-and-forensics.html)). So take only the record that costs seconds, read through the API server, then contain at once. Deleting, scaling down or draining destroys evidence; isolating does not.

Record, and keep with the event record:

- `kubectl get pod <pod> -n <ns> -o yaml` (full spec and status, including `status.containerStatuses[].imageID`, the running digest).
- `kubectl get node <node> -o yaml` (node, `nodeInfo`, labels, provider ID with the instance id).
- `kubectl logs <pod> -n <ns> --all-containers --timestamps` and `--previous` where a container restarted.
- `kubectl get events -n <ns> --field-selector involvedObject.name=<pod>`.

Checking whether an exposure was exploited (GuardDuty findings, CloudTrail and audit log queries) is not covered yet: https://github.com/aws-samples/sample-apex-skills/issues/351

## Step 3: Contain at once (proposed only)

Every item is printed for the team to review and apply. The order and the controls follow [EKS Best Practices: Incident response and forensics](https://docs.aws.amazon.com/eks/latest/best-practices/incident-response-and-forensics.html). This step reads what applies to this cluster and prints the proposals for it.

**Keep the pod in place.** The pod stays in its ReplicaSet, so a rollout or scale-down can delete it with its evidence. Propose pausing rollouts (`kubectl rollout pause deploy/<name> -n <ns>`) and holding autoscaler and manual scale-downs until the evidence is taken. Do not change the pod's app labels: the ReplicaSet would replace it.

**Read whether NetworkPolicy is enforced here** before proposing one:

| Cluster | Read | Enforced when |
|---|---|---|
| VPC CNI (not Auto Mode) | `aws eks describe-addon --cluster-name <c> --addon-name vpc-cni --query addon.configurationValues` | network policy is enabled (`enableNetworkPolicy` is `"true"`) |
| Auto Mode | `kubectl get configmap amazon-vpc-cni -n kube-system -o jsonpath='{.data.enable-network-policy-controller}'` | `true`: the Network Policy Controller ConfigMap is applied ([Auto Mode network policies](https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html)). Auto Mode supports no alternate policy engine. |
| Fargate or Windows pods | `kubectl get pod <pod> -n <ns> -o wide` (node name and OS) | never by VPC CNI: its policies do not apply to Fargate or Windows pods. Say so, and propose the pod's security group (Security Groups for Pods) where it has one. |
| Admin tier available? | `kubectl get crd clusternetworkpolicies.networking.k8s.aws` | the CRD exists |

**Pod-scoped network isolation, by label.** Select only the suspect pods; do **not** propose a namespace-wide deny-all, which cuts every neighbour. Propose an added label (`kubectl label pod <pod> -n <ns> quarantine=<event-id>`; the app labels stay), then:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: quarantine-<event-id>
  namespace: <ns>
spec:
  podSelector:
    matchLabels:
      quarantine: <event-id>
  policyTypes: [Ingress, Egress]   # no rules: denies what no other policy selecting these pods allows
```

Print these limits with it:

- It holds only if no other NetworkPolicy selecting the pod allows the traffic. Policies are additive: the pod gets "the union of what the applicable policies allow" ([Kubernetes network policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)), so existing allows keep working.
- Open connections may survive, depending on the engine.
- Where the Admin tier is available, propose an Admin-tier `ClusterNetworkPolicy` with a Deny action selecting the quarantine label instead: the Admin tier is evaluated first and namespace policies cannot override it ([EKS network policies](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html)).
- If the attacker has the host, a NetworkPolicy does not help: propose isolating the node with an EC2 security group, which affects every pod on that node.

**Node.** Propose `kubectl cordon <node>` (stop new scheduling) and detaching the node from load balancer target groups if it serves traffic. Do not drain: it evicts the compromised process. Node protection, with what each does not cover:

- EC2 termination protection (`aws ec2 modify-instance-attribute --instance-id <id> --disable-api-termination`): not available on Spot, and it does not stop Auto Scaling scale-in, so on a node group also propose scale-in protection (`aws autoscaling set-instance-protection --instance-ids <id> --auto-scaling-group-name <asg> --protected-from-scale-in`).
- Karpenter: `kubectl annotate node <node> karpenter.sh/do-not-disrupt=true`, which does not stop expiry, Spot interruption or manual deletion.
- Auto Mode: do not promise termination protection or a snapshot; neither is confirmed to work on Auto Mode instances, and every node has a 21-day maximum lifetime ([auto-mode-security.md](auto-mode-security.md)).

**Identity.** Each proposal names what it breaks; use the step 1 reads to list who shares the identity first.

- Pod Identity: `aws eks delete-pod-identity-association --cluster-name <c> --association-id <id>` breaks every pod on that service account. Narrow the role's policy instead if healthy pods share it.
- IRSA: tighten the role's trust policy (`Condition` on `<oidc>:sub` to remove `system:serviceaccount:<ns>:<sa>`), or narrow its permissions.
- Credentials already issued stay valid until they expire. The IAM **Revoke active sessions** action on the role ([revoke role sessions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html)) denies every session of the role issued before that time, healthy pods included, until they fetch new credentials.
- Leaked access key: `aws iam update-access-key --status Inactive`, then rotate.
- Node role (for example reached through IMDS from a pod): propose replacing the node rather than editing a role every node uses.

**Image digest block at admission**, only if a policy engine is installed (`kubectl get crd | grep -E 'kyverno|gatekeeper'`): propose a Kyverno or Gatekeeper rule that denies the compromised digest (and its tag) cluster-wide. Without a policy engine, say so; installing one is a step for after the event.

## Step 4: Snapshot and investigate (after isolation)

Once the pod is isolated:

- Read `aws ec2 describe-instances --instance-ids <id>` (AMI, security groups, IAM instance profile, `MetadataOptions`, attached volumes).
- **Propose, do not run:** snapshots of the node's EBS volumes, root and data (`aws ec2 create-snapshot --volume-id <vol> --description "<event-id> <node>"`), not on Auto Mode (step 3); volatile capture (memory, process and network state) by the team's forensic tooling before anything is terminated. On Auto Mode there is no SSH or SSM access to the node, so host-level capture is limited to what runs as a pod or through the APIs ([auto-mode-security.md](auto-mode-security.md)).
- Investigation itself (was the exposure used, what the attacker reached) is the team's step; this skill does not run it yet (issue 351 above).

## Step 5: Remediate

Patched add-on or node AMI, an image rebuilt on a patched base and redeployed by digest, a package pinned to a clean version in the lockfile. A security fix takes the **emergency path**, not the next upgrade window. For a managed add-on, propose `aws eks update-addon --cluster-name <c> --addon-name <a> --addon-version <v> --resolve-conflicts PRESERVE` after a non-production test. Roll out the fix and start replacement pods first, then remove the compromised ones; if a Deployment or DaemonSet owns them, deleting the pods only reschedules the vulnerable version. Replace a compromised node rather than cleaning it (Karpenter, a managed node group or Auto Mode provision a fresh node). Rotate any secret the compromised identity could read. Resume a paused rollout (`kubectl rollout resume deploy/<name> -n <ns>`) only once the evidence is taken.

## Step 6: Verify

Re-run [cve-advisory-review.md](cve-advisory-review.md) for the advisory (verdict "not exposed" for every component in scope) and the [posture-check.md](posture-check.md) checks that touch the affected control (for example IMDS hop limit, NetworkPolicy default-deny, PSA level, workload identity).

## Step 7: Record

Write the record even on the not-exposed path. After the event, find the root cause and update admission policies, PSA levels and NetworkPolicies so the entry vector stays closed; the record (with its evidence) is itself audit evidence.

```markdown
# Security event record: <event-id>
- Event: <type> <identifier, e.g. CVE id, digest, access key id (last 4)>; source <URL or finding id>, read <UTC time>
- Clusters and scope: <clusters, namespaces, workloads, digests, identities>; read at <UTC time>
- Exposure: exposed | not exposed | unknown (<reason>)
- Evidence of use: not checked by this skill (exploitation checks are not covered yet)
- Read by the agent / printed for the team to run: <list>
- Recorded: <pod spec, node, digest, logs>; snapshots: <ids, proposed or taken by the team>
- Actions proposed: <list, with the printed command or manifest>
- Actions taken by the team: <list, who, when>
- Verification: <re-run results with times>
- Open items: <owner, due>
```

## Shared responsibility (event response)

| AWS manages | Customer manages |
|---|---|
| Control-plane integrity; GuardDuty detections; durable log and snapshot primitives; clean replacement AMIs; Auto Mode node patching | The runbook and its rehearsal; isolation and eradication decisions and actions; credential rotation; forensic capture and evidence retention; post-event hardening |

## Sources
- [EKS Best Practices: Incident response and forensics](https://docs.aws.amazon.com/eks/latest/best-practices/incident-response-and-forensics.html) · [EKS Best Practices: Auditing and logging](https://docs.aws.amazon.com/eks/latest/best-practices/auditing-and-logging.html) · [EKS Best Practices: Runtime security](https://docs.aws.amazon.com/eks/latest/best-practices/runtime-security.html)
- [GuardDuty EKS integration](https://docs.aws.amazon.com/eks/latest/userguide/integration-guardduty.html) · [EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [EKS network policies](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html) · [Auto Mode network policies](https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html) · [Kubernetes network policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Revoke IAM role temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html) · [AWS Security Incident Response Guide](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/welcome.html)
- All checked 2026-11-05.
