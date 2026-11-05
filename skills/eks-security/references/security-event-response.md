# Security Event Response

What to do when a security event touches an EKS cluster: a new CVE or advisory, a compromised image or package, a leaked credential, or a suspicious runtime finding. One generic workflow covers every event type, in six steps: **scope, assess and preserve, contain (proposed only), remediate, verify, record.** Detection (Layer 5, [runtime-security.md](runtime-security.md)) and audit logging (Layer 6, [audit-logging.md](audit-logging.md)) produce the signals; this reference is how you respond.

**Read and propose only.** Every command below that the skill runs is a read (`aws ... describe-*`, `list-*`, `get-*`, `lookup-events`, a Logs Insights query; `kubectl get`). Every change (NetworkPolicy, cordon, identity revocation, admission block, patch) is printed as a command or manifest for the team to review and run. The skill never applies, patches, scales, deletes, cordons, execs into a pod or reads a Secret's data.

## Before an event (prerequisites)

- **Detective signal:** GuardDuty EKS Protection and Runtime Monitoring, findings to Security Hub ([runtime-security.md](runtime-security.md)).
- **Forensic trail:** control-plane `audit` and `authenticator` logs, CloudTrail, VPC Flow Logs, with retention that meets the regime ([audit-logging.md](audit-logging.md)).
- **A rehearsed runbook** that maps common detections (container breakout, reverse shell, crypto-mining, anomalous API call, leaked credential) to these steps and to owners. Practice it in game days; the [AWS Security Incident Response Guide](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/welcome.html) covers the account-level process.
- **Design choices that make response possible:** immutable, minimal nodes (Bottlerocket, Auto Mode) make "replace the node" the clean default; least-privilege workload IAM (Pod Identity or IRSA) limits blast radius; default-deny NetworkPolicy per namespace makes an isolation policy a small delta; signed images with admission control make "redeploy from known-good" trustworthy.

## Event types

| Event | Step 1 scopes by | Step 2 asks | Typical containment proposal | Typical remediation |
|---|---|---|---|---|
| **New CVE or advisory** | Component and installed version (run [cve-advisory-review.md](cve-advisory-review.md) first) | Is there a public exploit; any finding or audit-log sign of use? | Usually none beyond the advisory's workaround, if it has one | Patched add-on, AMI or image on the emergency path |
| **Compromised image** (malware, known-bad, exploited CVE) | Image digest: every pod running it | Did any pod running it make unexpected API or network calls? | Pod-scoped isolation of those pods; block the digest at admission | Rebuild on a clean, patched base; redeploy by digest |
| **Compromised package** (a dependency in an image) | Images whose lockfile or SBOM contains the package version; then their pods | Same as compromised image, plus build-system access in the window | Pod-scoped isolation; block the affected digests | Rebuild from a lockfile pinned to a clean version, in an isolated build step |
| **Leaked credential** (access key, role session, service account token) | The principal: which roles, Pod Identity associations, IRSA service accounts and pods use it | CloudTrail calls by that key or role in the exposure window | Revoke or rotate the credential; revoke the role's active sessions | Rotate secrets the principal could read; narrow the role's policy |
| **Suspicious runtime finding** (GuardDuty, Falco, a CNAPP) | The finding's pod, node, namespace, service account and image | Is it a true positive; what did the pod and its identity touch? | Pod-scoped isolation; cordon the node; revoke the pod's identity | Close the entry vector (patch, permission, misconfiguration); replace the node |

## Step 1: Scope

Answer: which clusters, namespaces, workloads, images (by digest), packages and identities are involved. Start from the inventory the [cve-advisory-review.md](cve-advisory-review.md) collector writes when one exists; otherwise read live.

| Question | Read-only command | Field that answers it |
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

**Not exposed path:** when step 1 finds nothing in scope, write the record (step 6) with what was read and when, and stop.

## Step 2: Assess and preserve

Two questions come before any containment: **was it used**, and **is the evidence safe**. Scaling down, deleting or restarting a pod destroys its process state and local filesystem.

### Assess: was it used? (optional block)

These reads need the IAM actions listed in [read-only-access.md](read-only-access.md) (GuardDuty `ListDetectors`, `ListFindings`, `GetFindings`; CloudTrail `LookupEvents`; CloudWatch Logs `StartQuery`, `GetQueryResults`). When a source cannot be read (no access, the service not enabled, the log type not on), the record says **`not checked: no access`** (or `not checked: <source> not enabled`) for that source. It never says "no evidence" for a source that was not read.

**GuardDuty EKS findings for the cluster** ([filter attributes](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_filter-findings.html)):

```bash
DET=$(aws guardduty list-detectors --query 'DetectorIds[0]' --output text)
aws guardduty list-findings --detector-id "$DET" \
  --finding-criteria '{"Criterion":{"resource.eksClusterDetails.name":{"Equals":["<cluster>"]}}}'
aws guardduty get-findings --detector-id "$DET" --finding-ids <id> [<id> ...]
```

Fields that answer it: `Type`, `Severity` (7 to 8 high, 9 to 10 critical), `Service.EventFirstSeen` and `EventLastSeen`, `Resource.KubernetesDetails.KubernetesWorkloadDetails` (`Name`, `Namespace`, `Containers[].Image`, `ServiceAccountName`) and `Resource.KubernetesDetails.KubernetesUserDetails.Username`. Narrow to a namespace or image with the criteria `resource.kubernetesDetails.kubernetesWorkloadDetails.namespace` or `resource.kubernetesDetails.kubernetesWorkloadDetails.containers.image`. An attack-sequence finding (Extended Threat Detection) carries the correlated timeline.

**CloudTrail for an involved role or access key** ([LookupAttribute keys](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupAttribute.html): `EventId`, `EventName`, `ReadOnly`, `Username`, `ResourceType`, `ResourceName`, `EventSource`, `AccessKeyId`):

```bash
aws cloudtrail lookup-events --start-time <ISO8601> --end-time <ISO8601> \
  --lookup-attributes AttributeKey=AccessKeyId,AttributeValue=<AKIA...|ASIA...>
aws cloudtrail lookup-events --start-time <ISO8601> --end-time <ISO8601> \
  --lookup-attributes AttributeKey=Username,AttributeValue=<role-session-name>
```

Fields: `Events[].EventName`, `EventSource`, `EventTime`, and inside `CloudTrailEvent` (a JSON string): `sourceIPAddress`, `userAgent`, `userIdentity.arn`, `errorCode`. `lookup-events` reads management events in the current Region only, one attribute per call; data events (for example S3 object reads) need a trail or CloudTrail Lake. IAM and STS events land in us-east-1. For a Pod Identity or IRSA role, the session name differs per pod, so search by `ResourceName` with the role ARN or filter `userIdentity.sessionContext.sessionIssuer.arn` in the returned events.

**Cluster audit log for a service account or pod**, CloudWatch Logs Insights on the log group `/aws/eks/<cluster>/cluster` ([control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html), [query examples](https://docs.aws.amazon.com/eks/latest/best-practices/auditing-and-logging.html)); needs the `audit` log type enabled:

```bash
QID=$(aws logs start-query --log-group-name /aws/eks/<cluster>/cluster \
  --start-time <epoch-seconds> --end-time <epoch-seconds> \
  --query-string 'fields @timestamp, verb, objectRef.resource, objectRef.namespace, objectRef.name, responseStatus.code, sourceIPs.0
| filter @logStream like "kube-apiserver-audit"
| filter user.username = "system:serviceaccount:<ns>:<sa>"
| sort @timestamp desc | limit 500' --query queryId --output text)
aws logs get-query-results --query-id "$QID"
```

For a pod, filter `objectRef.name = "<pod>" and objectRef.namespace = "<ns>"` (with `objectRef.subresource` showing `exec`, `attach` or `portforward` attempts against it). Fields: `verb`, `objectRef.*`, `responseStatus.code` (403 means tried and refused), `sourceIPs`, `annotations.authorization.k8s.io/decision`. Watch for `get`/`list` on `secrets`, `create` on `pods/exec`, and new `rolebindings` or `clusterrolebindings`.

### Preserve before containing

Record, and keep with the event record:

- `kubectl get pod <pod> -n <ns> -o yaml` (full spec and status, including `status.containerStatuses[].imageID`, the running digest).
- `kubectl get node <node> -o yaml` (node, `nodeInfo`, labels, provider ID with the instance id).
- `kubectl logs <pod> -n <ns> --all-containers --timestamps` and `--previous` where a container restarted.
- `kubectl get events -n <ns> --field-selector involvedObject.name=<pod>`.
- `aws ec2 describe-instances --instance-ids <id>` (AMI, security groups, IAM instance profile, `MetadataOptions`).

**Propose, do not run:** a snapshot of the node's EBS volumes (`aws ec2 create-snapshot --volume-id <vol> --description "<event-id> <node>"`), a label marking the pod and node as under investigation, EC2 termination protection and scale-in protection on the node (not available on Spot), and volatile capture (memory, process and network state) by the team's forensic tooling before anything is terminated. On Auto Mode there is no SSH or SSM access to the node, so host-level capture is limited to what runs as a pod or through the APIs ([auto-mode-security.md](auto-mode-security.md)).

**Do not delete, scale down or restart the pod** until evidence is captured and the team decides. Source: [EKS Best Practices: Incident response and forensics](https://docs.aws.amazon.com/eks/latest/best-practices/incident-response-and-forensics.html).

## Step 3: Contain (proposed only)

Every item is printed for the team to review and apply.

**Pod-scoped network isolation, by label.** Select only the suspect pods. Do **not** propose a namespace-wide deny-all: it cuts every neighbour in the namespace, causing an outage that hides the event and loses evidence from healthy pods. First add a unique label to the suspect pods (proposed: `kubectl label pod <pod> -n <ns> quarantine=<event-id>`), so the policy cannot match healthy replicas that share the app label. Then:

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
  policyTypes: [Ingress, Egress]   # no ingress or egress rules: deny all to and from these pods
```

To keep only an investigation path, add a narrow ingress rule from the responders' namespace instead of leaving it empty. For **egress deny only** (stop exfiltration and callbacks, keep the pod serving), set `policyTypes: [Egress]` with no egress rules, or allow only DNS to the cluster DNS service (TCP and UDP 53). This needs NetworkPolicy enforcement on (VPC CNI network policy or Auto Mode, [workload-security.md](workload-security.md)). A NetworkPolicy does not help if the attacker has the host: then isolate the node with an EC2 security group, which affects every pod on that node. On Fargate, the NetworkPolicy is the isolation (no node to cordon).

**Node.** Propose `kubectl cordon <node>` (stop new scheduling). Avoid `drain` while evidence on the node matters: it evicts the compromised process. Detach the node from load balancer target groups if it serves traffic.

**Identity revocation.**
- Pod Identity: propose `aws eks delete-pod-identity-association --cluster-name <c> --association-id <id>`, or narrow the role's policy if other workloads share the role.
- IRSA: propose tightening the role's trust policy (`Condition` on `<oidc>:sub` to remove `system:serviceaccount:<ns>:<sa>`), or narrow its permissions.
- Credentials already issued stay valid until they expire. To cut them now, propose the IAM **Revoke active sessions** action on the role, which attaches the `AWSRevokeOlderSessions` deny policy for sessions issued before that time ([revoke role sessions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html)). It hits every current session of the role, so check which workloads share it first.
- Leaked access key: propose `aws iam update-access-key --status Inactive`, then rotate.
- Node role: if the node role is implicated (for example through IMDS from a pod), propose replacing the node rather than editing a role every node uses.

**Image digest block at admission**, only if a policy engine is installed (`kubectl get crd | grep -E 'kyverno|gatekeeper'`): propose a Kyverno or Gatekeeper rule that denies the compromised digest (and its tag) cluster-wide. Without a policy engine, say so; installing one is a step for after the event.

## Step 4: Remediate

Patched add-on or node AMI, an image rebuilt on a patched base and redeployed by digest, a package pinned to a clean version in the lockfile. A security fix takes the **emergency path** (see the eks-best-practices skill's patch cadence and emergency path guidance), not the next upgrade window. For a managed add-on, propose `aws eks update-addon --cluster-name <c> --addon-name <a> --addon-version <v> --resolve-conflicts PRESERVE` after a non-production test. Roll out the fix and start replacement pods first, then remove the compromised ones; if a Deployment or DaemonSet owns them, deleting the pods only reschedules the vulnerable version. Replace a compromised node rather than cleaning it (Karpenter, a managed node group or Auto Mode provision a fresh node). Rotate any secret the compromised identity could read.

## Step 5: Verify

Re-run [cve-advisory-review.md](cve-advisory-review.md) for the advisory (verdict "not exposed" for every component in scope) and the [posture-check.md](posture-check.md) checks that touch the affected control (for example IMDS hop limit, NetworkPolicy default-deny, PSA level, workload identity). Re-run the step 2 queries for the period after containment: no new findings, API calls or audit entries from the revoked identity.

## Step 6: Record

Write the record even on the not-exposed path. After the event, find the root cause and update admission policies, PSA levels and NetworkPolicies so the entry vector stays closed; the record (with its evidence) is itself audit evidence.

```markdown
# Security event record: <event-id>
- Event: <type> <identifier, e.g. CVE id, digest, access key id (last 4)>; source <URL or finding id>, read <UTC time>
- Clusters and scope: <clusters, namespaces, workloads, digests, identities>; read at <UTC time>
- Exposure: exposed | not exposed | unknown (<reason>)
- Evidence of use, per source and window:
  - GuardDuty: <findings ids> | no findings for <window> | not checked: no access
  - CloudTrail: <events> | no events for <principal> in <window> | not checked: no access
  - Audit log: <entries> | no entries in <window> | not checked: no access | not checked: audit log not enabled
- Preserved: <pod spec, node, digest, logs, snapshot ids (proposed or taken by the team)>
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
- [GuardDuty filter attributes](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_filter-findings.html) · [GuardDuty EKS integration](https://docs.aws.amazon.com/eks/latest/userguide/integration-guardduty.html)
- [CloudTrail LookupAttribute](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupAttribute.html) · [EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [Revoke IAM role temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html) · [AWS Security Incident Response Guide](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/welcome.html)
- All checked 2026-11-05.
