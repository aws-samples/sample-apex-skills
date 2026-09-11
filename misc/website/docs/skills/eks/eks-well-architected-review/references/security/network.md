---
title: "🔒 Security — Network Segmentation & Infrastructure"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/network.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/network.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/network.md). Edit the source, not this page.
:::

# 🔒 Security — Network Segmentation & Infrastructure

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**8 questions** — Network policies, pod network separation, SSH access, cluster security group egress, subnet IP capacity, prefix delegation.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `na`.

---

## Pod & node network segmentation

### sec-4: Are Kubernetes Network Policies deployed to control Pod-to-Pod traffic?

**Detection:** 🔬 AUTO-DETECTABLE

> Network Policies enforce micro-segmentation between workloads.

**Commands:**
```bash
kubectl get networkpolicies -A -o json
kubectl get namespaces -o json
# Compare: which namespaces have network policies
```

**Remediation:** Two things are required, and a NetworkPolicy without the second does nothing.

1. **Turn on enforcement.** With the Amazon VPC CNI this is off by default:

```bash
aws eks update-addon --cluster-name <CLUSTER> --addon-name vpc-cni --region <REGION> \
  --configuration-values '{"enableNetworkPolicy":"true"}'
```

   On EKS Auto Mode, apply a `ConfigMap` named `amazon-vpc-cni` in `kube-system` with
   `enable-network-policy-controller: "true"`. Calico or Cilium enforce natively and need neither.

2. **Then write the policies.** Start with a default-deny per namespace and allow specific traffic —
   remembering to allow DNS, or every pod loses name resolution.

> Consider `NETWORK_POLICY_ENFORCING_MODE=strict` only deliberately: pods then start default-deny before
> their policies are programmed, which breaks anything that talks during startup unless every path is
> already allowed.

---

### sec-14: Do you apply network separation to Pod networking using Kubernetes Network Policies or AWS security groups to control traffic between Pods and clusters?

**Detection:** ✋ ASK USER

> Assess the implementation of network segmentation and micro-segmentation for Pod communications.

**Remediation:** Apply NetworkPolicies or security groups per pod to enforce network segmentation between namespaces and workloads.

---

### sec-30: Do you disable SSH access to worker nodes, using Systems Manager or similar for emergency access?

**Detection:** 🔬 AUTO-DETECTABLE

> Disabling SSH reduces the attack surface on worker nodes.

**Remediation:** Revoking port 22 before the replacement path is proven leaves a node with no
interactive access at all if any one of the following isn't true yet — check them, in order, before
touching the security group:

1. **The SSM Agent is running on every node.** `aws ssm describe-instance-information --region <REGION>`
   must list them; AL2023, AL2 and Bottlerocket ship the agent preinstalled, but a custom AMI or a
   bootstrap script that disables it will not.
2. **The node instance role carries `AmazonSSMManagedInstanceCore`** (or an equivalent least-privilege
   policy): `aws iam list-attached-role-policies --role-name <NODE_ROLE> --region <REGION>`.
3. **On a private cluster with narrowed egress (see net-4), the SSM VPC endpoints exist:**
   `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<VPC_ID> --region <REGION> --query "VpcEndpoints[].ServiceName"`
   must include `ssm`, `ssmmessages` and `ec2messages` — without them, narrowed egress blocks the agent
   from reaching the service and revoking SSH leaves nothing.
4. **A session actually opens:** `aws ssm start-session --target <INSTANCE_ID>` against at least one
   node in every node group, before revoking anything.

Only once all four hold, remove SSH from the worker node security groups:

```bash
aws ec2 revoke-security-group-ingress --group-id <NODE_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=0.0.0.0/0}]'
```

A node that fails any of the four checks and then has SSH revoked has no path back except replacing the instance.

---

### sec-31: Do you avoid sharing security groups between EKS worker nodes and the control plane? — RETIRED

**Detection:** ⊘ NOT ASSESSED (always `na`)

> **This question is no longer scored.** AWS applies the cluster security group to the control plane
> and to managed compute by design, and states, of clusters originally deployed on
> Kubernetes 1.14 / platform version `eks.3` or earlier, that their separate control-plane and
> worker-node security groups are "no longer required and can be removed". The narrower point holds
> generally: today the cluster security group spans both planes by design. Answering
> it would penalise the configuration AWS now ships by default. The remediation this question used to
> give — create a dedicated node security group — is the opposite of current guidance, which is why
> the text was removed rather than reworded.
>
> The measurable control that remains in this area is **net-4**: whether the cluster security group's
> default allow-all egress to `0.0.0.0/0` has been narrowed.

---

## Network Infrastructure

### net-1: Do VPC subnets have sufficient available IP addresses (≥100 per subnet)?

**Detection:** 🔬 AUTO-DETECTABLE

> Low IP capacity causes pod scheduling failures.

**Commands:**
```bash
aws ec2 describe-subnets --filters Name=vpc-id,Values=<VPC_ID> --region <REGION> --query "Subnets[].{Id:SubnetId,AZ:AvailabilityZone,Available:AvailableIpAddressCount}"
```

**Remediation:** Expand subnets with low IP capacity or enable VPC CNI prefix delegation (`ENABLE_PREFIX_DELEGATION=true`) to increase available IPs per node.

---

### net-2: Do security groups follow least-privilege (no 0.0.0.0/0 on non-standard ports)?

**Detection:** 🔬 AUTO-DETECTABLE

> Open security group rules expose the cluster to unauthorized access.

**Commands:**
```bash
aws ec2 describe-security-groups --filters Name=vpc-id,Values=<VPC_ID> --region <REGION> --output json
# Check IpPermissions for 0.0.0.0/0 on non-443/80 ports
```

**Remediation:** A wide-open rule on a port that looks unused can still be load-bearing — an NLB
health-check range or a partner's fixed IP that nobody documented — so revoking it blind can cut either
off with no warning. Find who is actually using the port before narrowing it:

```bash
aws ec2 describe-network-interfaces --filters Name=group-id,Values=<SG_ID> --region <REGION> \
  --query 'NetworkInterfaces[].{Id:NetworkInterfaceId,Desc:Description,Attachment:Attachment.InstanceId}'
# Cross-check against VPC Flow Logs for the source IPs actually hitting this port, and any
# documented partner/office CIDR or load balancer health-check range before revoking.
```

Then add the specific replacement before revoking the wide rule, the same order as net-4:

```bash
aws ec2 authorize-security-group-ingress --group-id <SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=<PORT>,ToPort=<PORT>,IpRanges=[{CidrIp=<SPECIFIC_CIDR>}]'
aws ec2 revoke-security-group-ingress --group-id <SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=<PORT>,ToPort=<PORT>,IpRanges=[{CidrIp=0.0.0.0/0}]'
```

---

### net-3: Is VPC CNI prefix delegation enabled for improved IP capacity?

**Detection:** 🔬 AUTO-DETECTABLE

> Prefix delegation raises the IP ceiling per node by assigning /28 prefixes (16 IPs each) to a node's ENIs instead of individual secondary IPs. The gain is instance-type dependent — IPs per ENI × ENIs attached, both of which vary by instance size — not a flat number.

**Commands:**
```bash
kubectl get daemonset aws-node -n kube-system -o json
# Check env ENABLE_PREFIX_DELEGATION
```

<!-- MAINTAINER NOTE — not report content, placed before **Remediation:** for the same reason as the
     lens-11 note in workload-security.md: question_prose() in assets/render-report.py captures
     everything after "**Remediation:**" verbatim and html-escapes it for display, so a comment inside
     that span would reach the customer as literal text. "~15 to ~110" was a plausible worked example
     for one instance size stated as a general fact, and 110 is not a prefix-delegation output at all —
     it is Kubernetes' own default --max-pods-per-node cap, which AWS states plainly: "By default, the
     maximum number of Pods that you can run on a node is 110, but you can change that number."
     (https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses.html, fetched
     2026-09-11). Low severity, so this fix stays a mechanism statement, not a worked example. -->

**Remediation:** Enable VPC CNI prefix delegation (`ENABLE_PREFIX_DELEGATION=true` on the aws-node
DaemonSet) on node groups running short on IPs. It raises the ceiling by IPs-per-ENI × ENIs, both
instance-type dependent, so the gain varies by instance size rather than following one before/after
number — and the 110-pods-per-node figure some instance types hit first is Kubernetes' own `--max-pods`
default, a separate, changeable ceiling on top of whatever IPs prefix delegation makes available.

---

### net-4: Has the cluster security group's default allow-all egress been narrowed?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately outside the blockquote and the Remediation
     block so the renderer does not extract it (see question_prose() in assets/render-report.py, which
     takes the first `>` blockquote and the Remediation text only). Report readers scanning for what to
     type were skimming past the real warning because this changelog sat next to it.
     Not what this question used to ask: it previously asked whether *separate* security groups were
     used for the control plane and worker nodes, testing whether securityGroupIds contained
     clusterSecurityGroupId. That premise was wrong — AWS applies the cluster security group to the
     control plane *and* to managed compute by design, and it is never a member of the
     additional-groups list, so the check reported a separation that does not exist on essentially
     every cluster. AWS further states the old control-plane/node split is "no longer required and can
     be removed", so the previous remediation advised the opposite of current guidance.
     The blockquote below is one physical line on purpose: question_prose() keeps the `>` marker of
     every continuation line, so a wrapped blockquote ships stray `>` characters into the report. -->

> EKS creates the cluster security group with a default egress rule permitting all protocols to `0.0.0.0/0` (alongside a self-referencing rule for node-to-node traffic, which is not the concern here). Every node and every pod using the cluster SG inherits it, so a compromised pod can reach any internet endpoint — the outbound path used for data exfiltration and for pulling a second stage. Narrowing egress to the destinations the workload actually needs removes that path.

**Commands:**
```bash
aws ec2 describe-security-groups --group-ids <CLUSTER_SG_ID> --region <REGION> \
  --query 'SecurityGroups[].IpPermissionsEgress'
# Fails on ANY rule opening every port to 0.0.0.0/0 — `IpProtocol: "-1"`, or tcp/udp 0-65535, which
# grants identical egress and used to be read as "narrowed".
```

**Remediation:** Replace the default egress rule on the cluster security group with specific
destinations. Most clusters need 443 to the VPC endpoints they use (`ecr.api`, `ecr.dkr`, `s3`, `sts`,
`logs`), plus 443 to the control plane and any external service the workload calls. Removing all
egress will break image pulls and add-on updates, so add the replacements before revoking:

```bash
aws ec2 authorize-security-group-egress --group-id <CLUSTER_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=<VPC_CIDR>}]'
aws ec2 revoke-security-group-egress --group-id <CLUSTER_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]'
```

---
