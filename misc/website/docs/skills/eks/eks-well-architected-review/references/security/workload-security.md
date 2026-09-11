---
title: "🔒 Security — Workload, Pod & Supply Chain Security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/workload-security.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/workload-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/workload-security.md). Edit the source, not this page.
:::

# 🔒 Security — Workload, Pod & Supply Chain Security

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**18 questions** — Admission control, Pod Security Standards, security contexts, image pull policy & signing, runtime monitoring, pod security baselines, IMDSv2.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `na`.

---

## Admission control & Pod Security Standards

### sec-10: Are admission webhooks (validating/mutating) deployed to enforce Pod security policies?

**Detection:** 🔬 AUTO-DETECTABLE

> Admission controllers enforce security policies at deployment time before Pods are created.

**Commands:**
```bash
kubectl get validatingwebhookconfigurations -o json
kubectl get mutatingwebhookconfigurations -o json
```

**Remediation:** Deploy OPA Gatekeeper or Kyverno to enforce Pod security policies. Start with a policy blocking privileged containers.

---

### sec-11: Are Pod Security Standards labels applied to namespaces to enforce security baselines?

**Detection:** 🔬 AUTO-DETECTABLE

> Pod Security Standards (baseline/restricted) prevent privileged containers and host access.

**Commands:**
```bash
kubectl get namespaces -o json
# Check labels starting with pod-security.kubernetes.io/
```

**Remediation:** `enforce=` is not advisory. The built-in Pod Security admission controller starts
rejecting pods that violate the level as soon as the label lands, and running pods are never evicted —
so the failure surfaces later, at the next rollout, reschedule or node replacement, which is the worst
moment to find out. Check what the level would reject, warn on it, then enforce, in that order:

```bash
# 1. What breaks? --dry-run=server returns one warning per EXISTING pod that violates the level.
kubectl label --dry-run=server --overwrite namespace <ns> \
  pod-security.kubernetes.io/enforce=baseline

# 2. Run it as a warning and an audit-log entry for real while the offenders get fixed.
kubectl label --overwrite namespace <ns> \
  pod-security.kubernetes.io/warn=baseline pod-security.kubernetes.io/audit=baseline

# 3. Only then enforce.
kubectl label --overwrite namespace <ns> pod-security.kubernetes.io/enforce=baseline
```

Node agents, CSI drivers and monitoring DaemonSets are the usual casualties: anything that needs
`hostPath`, `hostNetwork`, `hostPID` or `privileged` fails `baseline`, and `restricted` additionally
demands non-root, `seccompProfile` set and all capabilities dropped. Label each namespace at the level
its workloads can actually meet — `restricted` for your own applications, `baseline` or `privileged`
for the infrastructure namespaces — rather than enforcing one level everywhere and discovering it
during a node replacement.

---

### sec-16: Do you leverage Pod Security Standards, Pod Security Policies, or admission controllers to restrict Pod actions and enforce security controls?

**Detection:** 🔬 AUTO-DETECTABLE

> Assess the implementation of Pod-level security policies and admission control.

**Remediation:** Deploy admission controllers (Kyverno/Gatekeeper) to enforce Pod Security Standards and prevent privileged containers at deploy time.

---

### adm-1: Are admission controller policies (Gatekeeper/Kyverno) deployed with adequate coverage?

**Detection:** 🔬 AUTO-DETECTABLE

> Admission policies enforce security and compliance at deploy time.

**Commands:**
```bash
kubectl get constrainttemplates -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
```

**Remediation:** Deploy Gatekeeper or Kyverno with at least 5-10 policies covering common security baselines (privileged containers, host networking, resource limits).

---

### adm-2: Do admission policies block privileged container execution?

**Detection:** 🔬 AUTO-DETECTABLE

> Blocking privileged containers prevents container escape attacks.

**Commands:**
```bash
kubectl get constraints -A -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
# Look for privileged container blocking
```

**Remediation:** Add a policy to block privileged containers: Gatekeeper `K8sPSPPrivilegedContainer` constraint or Kyverno `disallow-privileged-containers` policy.

---

### adm-3: Are admission policies set to enforce mode (not audit-only)?

**Detection:** 🔬 AUTO-DETECTABLE

> Audit-only policies detect but do not prevent violations.

**Commands:**
```bash
kubectl get constraints -A -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
# Check enforcementAction / validationFailureAction
```

**Remediation:** Enforce mode starts rejecting admission requests the moment you switch it, and it
applies to existing workloads too: a Deployment that has run untouched for a year fails its next
rollout if it violates the policy. Read the audit results first and fix or exempt everything they name:

```bash
kubectl get constraints -A -o json | jq '.items[]|{name:.metadata.name,violations:.status.totalViolations}'
kubectl get policyreports,clusterpolicyreports -A          # Kyverno's equivalent
```

Then switch one policy at a time, starting with the ones already reporting zero violations:

- Gatekeeper: `enforcementAction: deny` on the constraint (`warn` is the useful intermediate step for a constraint you have just written).
- Kyverno: `validationFailureAction: Enforce` — renamed to `failureAction` on the rule in Kyverno 1.13
  and later (`spec.validationFailureAction` migrated to `spec.rules.validate.failureAction`, per the
  v1.13.0 release notes: https://github.com/kyverno/kyverno/releases/tag/v1.13.0), where the old field
  still works but is deprecated.

Exclude the namespaces that run the cluster's own infrastructure — `kube-system` plus wherever the CNI,
CSI drivers, node agents and monitoring DaemonSets live — before enforcing anything that blocks
privileged or host access, or the policy will block the add-ons the cluster needs to bring up nodes.

---

## Container & pod hardening

### sec-12: Do containers use explicit image pull policies (Always or IfNotPresent)?

**Detection:** 🔬 AUTO-DETECTABLE

> Explicit pull policies ensure containers use verified, up-to-date images.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].imagePullPolicy
```

**Remediation:** Set `imagePullPolicy: Always` or `IfNotPresent` on all containers. Avoid using `latest` tag without `Always` pull policy to ensure image integrity.

---

### sec-15: Do containers have security contexts configured (runAsNonRoot, readOnlyRootFilesystem, or allowPrivilegeEscalation=false)?

**Detection:** 🔬 AUTO-DETECTABLE

> Security contexts reduce the blast radius of a compromised container.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].securityContext
```

**Remediation:** Add `securityContext` to all containers: set `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, and `allowPrivilegeEscalation: false`.

---

### podsec-1: Do containers run as non-root users?

**Detection:** 🔬 AUTO-DETECTABLE

> Root containers can escape to the host and compromise the node.

**Commands:**
```bash
kubectl get pods -A -o json
# Check securityContext.runAsNonRoot == true
```

**Remediation:** Set `securityContext.runAsNonRoot: true` and `runAsUser: 1000` on all containers. Use Pod Security Standards `restricted` profile on namespaces.

---

### podsec-2: Are containers running without privileged mode?

**Detection:** 🔬 AUTO-DETECTABLE

> Privileged containers have full host access and bypass all security boundaries.

**Commands:**
```bash
kubectl get pods -A -o json
# Check securityContext.privileged != true
```

**Remediation:** `privileged: true` grants root-equivalent access to the host — device nodes, kernel
modules, the ability to remount the host filesystem — so removing it fleet-wide in one edit is exactly
how you take down whatever depends on it. CNI plugins, CSI node-driver DaemonSets and security-agent
DaemonSets (Falco, GuardDuty's EKS agent, most service meshes' init containers) commonly need it to
function. Find out who actually needs it before touching anything:

```bash
kubectl get pods -A -o json | jq -r \
  '.items[] | select([.spec.containers[]?,.spec.initContainers[]?][]?.securityContext.privileged==true)
  | "\(.metadata.namespace)/\(.metadata.name)"'
```

Exclude `kube-system` and wherever the CNI, CSI drivers and node agents live — those are the usual
load-bearing cases. For everything else, `privileged: true` nearly always stands in for one or two
specific capabilities: add exactly what the container calls via `securityContext.capabilities.add`,
confirm the workload still runs, then remove the flag — one Deployment at a time, not fleet-wide.

---

### podsec-3: Are pods free of host path volume mounts?

**Detection:** 🔬 AUTO-DETECTABLE

> Host path mounts expose the node filesystem to containers.

**Commands:**
```bash
kubectl get pods -A -o json
# Check volumes[].hostPath is not used
```

**Remediation:** Replace hostPath volume mounts with PersistentVolumeClaims, ConfigMaps, or Secrets. hostPath mounts expose the node filesystem to containers.

---

### podsec-4: Are containers free of dangerous Linux capabilities (NET_ADMIN, SYS_ADMIN, ALL)?

**Detection:** 🔬 AUTO-DETECTABLE

> Dangerous capabilities enable container escape and network manipulation.

**Commands:**
```bash
kubectl get pods -A -o json
# Check capabilities.add does not include NET_ADMIN, SYS_ADMIN, ALL
```

**Remediation:** `NET_ADMIN`, `SYS_ADMIN` and `ALL` are also what CNI plugins (route and interface
manipulation), CSI node drivers (mount-namespace operations) and some security-agent DaemonSets
legitimately need, so removing them from an infrastructure pod instead of an application one breaks
networking or storage cluster-wide, not just the one pod. List who carries them before removing anything:

```bash
kubectl get pods -A -o json | jq -r \
  '.items[] | .metadata.namespace as $ns | .metadata.name as $n | .spec.containers[]? |
  select((.securityContext.capabilities.add // []) | any(. == "NET_ADMIN" or . == "SYS_ADMIN" or . == "ALL"))
  | "\($ns)/\($n): \(.securityContext.capabilities.add)"'
```

Leave `kube-system` and the CNI/CSI/node-agent namespaces for last. For application workloads, drop the
capability, redeploy, and watch for the specific failure it was covering (a route-manipulation error, a
permission-denied on a raw socket) before calling it fixed — then add back only the exact capability the
error names, never `ALL`.

---

### podsec-5: Do containers drop ALL Linux capabilities?

**Detection:** 🔬 AUTO-DETECTABLE

> Dropping ALL capabilities and adding back only needed ones is a security best practice.

**Commands:**
```bash
kubectl get pods -A -o json
# Check capabilities.drop includes "ALL"
```

**Remediation:** Add `securityContext.capabilities.drop: ["ALL"]` to all containers, then add back only required capabilities with `capabilities.add`.

---

### lens-11: Do EC2 worker nodes enforce IMDSv2 (HttpTokens=required)?

**Detection:** 🔬 AUTO-DETECTABLE

> IMDSv2 prevents SSRF attacks from stealing instance credentials.

**Commands:**
```bash
aws ec2 describe-instances --filters "Name=tag:kubernetes.io/cluster/<CLUSTER>,Values=owned,shared" --region <REGION>
# Check MetadataOptions.HttpTokens == required
```

<!-- MAINTAINER NOTE — not report content, placed here (before **Remediation:**, after the Commands
     fence) rather than inside the Remediation body, because question_prose() in
     assets/render-report.py captures everything from "**Remediation:**" to the next `\n---`/`\n### `
     verbatim, then html-escapes it for display — a comment placed inside that span reaches the
     customer as literal "&lt;!--...--&gt;" text instead of being hidden, which is why it sits here.
     History: the hop-limit paragraph below previously stated a flat rule — "1 for a managed node group
     with no launch template, 2 when a launch template with a custom AMI is used" — with the values
     backwards. An earlier draft of this note then over-corrected: it treated the live cluster used to
     verify this (a maintainer's own test cluster, ap-southeast-5, Kubernetes 1.34) as AL2023 and
     read a contradiction into the AWS docs that isn't there. That nodegroup is actually
     amiType: BOTTLEROCKET_ARM_64 (releaseVersion 1.54.0-5043decc), confirmed via
     `aws eks describe-nodegroup`, not AL2023. Corrected picture, all three parts live-verified:
       (1) AL2023 managed node groups: the EKS User Guide states, and nothing here challenges it, "For
     IMDSv2 with AL2023, the default hop count for managed node groups can vary: When not using a launch
     template, the default is set to 1 ... When using a custom AMI in a launch template, the default
     HttpPutResponseHopLimit is set to 2." (https://docs.aws.amazon.com/eks/latest/userguide/al2023.html,
     fetched live 2026-09-11 via the AWS docs MCP).
       (2) The live cluster is a Bottlerocket managed node group with launchTemplate: null, and EKS's own
     AWSServiceRoleForAmazonEKSNodegroup generated a launch template setting HttpPutResponseHopLimit: 2
     — every instance reports Hop: 2, Tokens: required. This is a DIFFERENT AMI family than (1), not a
     counterexample to it, and it is consistent with ImdsSupport: v2.0 on that AMI (see below). Every
     fixture under test-harness/fixtures/**/aws_ec2_describe-instances_*.json agrees (all 2).
       (3) ImdsSupport is not a fixed AMI-family property, which is the genuinely new fact here and the
     reason the remediation still says "check the instance" rather than branch purely on AMI family:
     live-checked (`describe-images`, read-only, ap-southeast-5), the SAME Bottlerocket
     release (v1.64.0, built the same day) carries no ImdsSupport attribute (null) on its aws-k8s-1.31
     track and ImdsSupport: v2.0 on its aws-k8s-1.34 track. AL2's EKS-optimized AMI could not be checked
     the same way: AWS stopped publishing it entirely on 2025-11-26 (stated on the same al2023.html
     page), and its SSM parameter for 1.34 no longer resolves.
       Karpenter's httpPutResponseHopLimit:1 default is unaffected by any of the above and is documented
     at https://karpenter.sh/docs/concepts/nodeclasses/, corroborated by the "Announcing Karpenter 1.0"
     post on the AWS Containers Blog. -->

**Remediation:** Require IMDSv2 (`MetadataOptions.HttpTokens=required`) so node credentials cannot be
read with a bare `GET` to `169.254.169.254`, which is what makes a server-side request forgery
profitable. Two things make this less of a one-liner than it looks:

- **Anything that only speaks IMDSv1 breaks the moment tokens are required** — old AWS SDK versions, vendored third-party agents, and any `curl http://169.254.169.254/...` in a bootstrap script or container image. The `MetadataNoToken` CloudWatch metric (namespace `AWS/EC2`) counts IMDSv1 calls per instance; get it to zero before you require tokens, not after.
- **Editing a launch template does not change instances that are already running.** A new launch template version applies only to instances launched after it, so the node group has to be rolled (or the Karpenter nodes drifted) before the setting is real. Where a node cannot be replaced yet, set it on the running instance.

```bash
aws ec2 create-launch-template-version --launch-template-id <LT_ID> --source-version '$Latest' \
  --launch-template-data '{"MetadataOptions":{"HttpTokens":"required","HttpEndpoint":"enabled"}}' \
  --region <REGION>
aws ec2 modify-instance-metadata-options --instance-id <INSTANCE_ID> --http-tokens required \
  --http-endpoint enabled --region <REGION>     # already-running instance, no replacement
```

`HttpPutResponseHopLimit` is the other half of the setting and is not part of this finding: a hop limit
of **1** is what stops a pod on the pod network from reaching IMDS at all, because the extra hop
consumes it, while **2** lets pods through. The default depends on the AMI family and how the node was
created, and it is not the same for every AMI family, so **read the effective value off the instance
rather than infer it**:

```bash
aws ec2 describe-instances --instance-ids <INSTANCE_ID> --region <REGION> \
  --query 'Reservations[].Instances[].MetadataOptions.{HopLimit:HttpPutResponseHopLimit,Tokens:HttpTokens}'
```

- **AL2023 managed node groups:** the EKS User Guide documents no launch template → hop 1 (containers
  blocked from IMDS); a custom AMI in a launch template → hop 2.
- **Other AMI families can differ from that split.** A Bottlerocket managed node group with no
  user-supplied launch template can still land on hop **2** — EKS's own auto-generated launch template
  set it that way on a live cluster checked for this review — which is consistent with the AMI itself
  carrying `imds-support: v2.0`. That attribute is not fixed per AMI family either: the same Bottlerocket
  release carries it on the AMI built for one Kubernetes version track and not on the AMI built for an
  older one, so an AMI can gain it between node-group upgrades without anyone changing a setting.
- **Karpenter 1.0 and later is the one case that overrides both**: its `EC2NodeClass` defaults
  `httpPutResponseHopLimit` to **1** and `httpTokens` to `required`, specifically to block pods that
  aren't on the host network from reaching IMDS, regardless of AMI family.

Check the effective value rather than assuming a container that reads instance metadata needs it raised, and
prefer IRSA or EKS Pod Identity, which removes the reason for a pod to want node credentials at all.

---

## Supply chain & runtime security

### sec-32: Do you implement container image signing and verification (Sigstore/Cosign, AWS Signer, Notary)?

**Detection:** ✋ ASK USER

> Image signing ensures only trusted images are deployed.

**Remediation:** Deploy Cosign webhook for image verification: `helm install cosign-webhook sigstore/cosign-webhook`. Configure policies to reject unsigned images.

---

### sec-33: Do you implement runtime security monitoring (Falco, GuardDuty for EKS, Sysdig)?

**Detection:** 🔬 AUTO-DETECTABLE

> Runtime monitoring detects suspicious container behavior.

**Remediation:** Deploy GuardDuty for EKS: enable in the GuardDuty console under EKS Protection. Alternatively, deploy Falco: `helm install falco falcosecurity/falco`.

---

## Image supply chain

> Moved here from Cost Optimization. Both questions are ECR controls that limit what can enter
> the cluster, which the EKS Best Practices Guides cover under Security / Image Security. Scored
> in the consolidated Security scorer in [identity-access.md](identity-access).

### lens-12: Do ECR repositories have scan-on-push enabled?

**Detection:** 🔬 AUTO-DETECTABLE

> Image scanning detects vulnerabilities before deployment.

**Commands:**
```bash
aws ecr describe-repositories --region <REGION> --query "repositories[].imageScanningConfiguration.scanOnPush"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable scan-on-push for ECR repositories: `aws ecr put-image-scanning-configuration --repository-name <name> --image-scanning-configuration scanOnPush=true`.

---

---

### lens-13: Do ECR repositories use immutable image tags?

**Detection:** 🔬 AUTO-DETECTABLE

> Immutable tags prevent tag overwriting and ensure deployment reproducibility.

**Commands:**
```bash
aws ecr describe-repositories --region <REGION> --query "repositories[].imageTagMutability"
# Check for IMMUTABLE
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable immutable tags for ECR repositories: `aws ecr put-image-tag-mutability --repository-name <name> --image-tag-mutability IMMUTABLE`.

---
