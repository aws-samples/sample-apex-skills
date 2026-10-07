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

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`.

---

## Table of Contents

1. [Pod & node network segmentation](#pod--node-network-segmentation)
   - [sec-4: Are Kubernetes Network Policies deployed to control Pod-to-Pod traffic?](#sec-4-are-kubernetes-network-policies-deployed-to-control-pod-to-pod-traffic)
   - [sec-14: Do you apply network separation to Pod networking using Kubernetes Network Policies or AWS security groups to control traffic between Pods and clusters?](#sec-14-do-you-apply-network-separation-to-pod-networking-using-kubernetes-network-policies-or-aws-security-groups-to-control-traffic-between-pods-and-clusters)
   - [sec-30: Is inbound SSH (port 22) closed to the internet on the cluster security groups?](#sec-30-is-inbound-ssh-port-22-closed-to-the-internet-on-the-cluster-security-groups)
   - [sec-31: Do you avoid sharing security groups between EKS worker nodes and the control plane? — RETIRED](#sec-31-do-you-avoid-sharing-security-groups-between-eks-worker-nodes-and-the-control-plane--retired)
2. [Network Infrastructure](#network-infrastructure)
   - [net-1: Do VPC subnets have sufficient available IP addresses (≥100 per subnet)?](#net-1-do-vpc-subnets-have-sufficient-available-ip-addresses-100-per-subnet)
   - [net-2: Do security groups follow least-privilege (no 0.0.0.0/0 on non-standard ports)?](#net-2-do-security-groups-follow-least-privilege-no-00000-on-non-standard-ports)
   - [net-3: Is VPC CNI prefix delegation enabled for improved IP capacity?](#net-3-is-vpc-cni-prefix-delegation-enabled-for-improved-ip-capacity)
   - [net-4: Has the cluster security group's default allow-all egress been narrowed?](#net-4-has-the-cluster-security-groups-default-allow-all-egress-been-narrowed)

---

## Pod & node network segmentation

### sec-4: Are Kubernetes Network Policies deployed to control Pod-to-Pod traffic?

**Detection:** 🔬 AUTO-DETECTABLE

> Network Policies enforce micro-segmentation between workloads — but only where something is
> enforcing them. Enforcement is opt-in on both EKS compute shapes, and a cluster full of
> NetworkPolicy objects with the enforcement switch off has exactly the same traffic flows as a
> cluster with no policies at all, while looking compliant to anyone counting objects. On a standard
> cluster the switch is the `--enable-network-policy` argument on the VPC CNI's network-policy agent
> (the `aws-eks-nodeagent` container of the `aws-node` DaemonSet), which is off when absent, together
> with `enable-network-policy-controller: "true"` in the `amazon-vpc-cni` ConfigMap — AWS: "When you first provision an
> EKS cluster, VPC CNI Network Policy functionality is not enabled by default"
> (`eks/latest/best-practices/network-security.html`). **The agent being present is not the switch**:
> it ships with every current VPC CNI and runs with `--enable-network-policy=false` until the add-on
> is reconfigured, which is the add-on's default configuration. On EKS Auto Mode it is a
> `ConfigMap`: "To use
> network policies with EKS Auto Mode, you first need to enable the Network Policy Controller by
> applying a ConfigMap to your cluster" (`eks/latest/userguide/auto-net-pol.html`). So this question
> reports coverage only once the policies can take effect — the switch is on, or a `calico-node` or
> `cilium` DaemonSet enforces beside the VPC CNI — and reports "not enforced" when they cannot.
> Only the exact value `"true"` of `enable-network-policy-controller` turns the controller on, and a
> repeated `--enable-network-policy` argument is read by its last occurrence. Where nothing collected
> shows enforcement — no `aws-node` DaemonSet in `kube-system`, no ready `calico-node` or `cilium`, and
> not every EC2 node an Auto Mode node with the ConfigMap on — this question never passes: a cluster
> with only Fargate nodes is "not enforced" (AWS: VPC CNI network policies apply "to Amazon EC2 Linux
> nodes only. You can't apply the policies to Fargate or Windows nodes", `eks/latest/userguide/cni-network-policy.html`;
> for the same reason a namespace whose running pods are all on Fargate nodes is never counted as enforced),
> Auto Mode nodes without the ConfigMap are "not enforced", and EC2 nodes whose CNI is not identified in
> the collected data are NOT ASSESSED. Where a ready `calico-node` or `cilium` does publish the coverage
> ratio but some EC2 nodes are Auto Mode nodes without the ConfigMap, a `most` or `all` is capped at
> `some`: those nodes enforce no policy for the pods that land on them. Beside EKS Hybrid Nodes, a
> ready `calico-node` or `cilium` is counted for the hybrid nodes only, unless its ready Pod count also
> covers every non-Auto-Mode EC2 node — AWS: "Cilium is not supported
> by AWS when running on nodes in AWS Cloud" (`eks/latest/userguide/hybrid-nodes-cni.html`), whose
> documented install pins the agent to hybrid nodes — so non-Auto-Mode EC2 nodes without both VPC CNI
> switches on cap a `most` or `all` at `some` the same way. Where EKS Hybrid Nodes run
> no ready `calico-node` or `cilium`, nothing collected shows enforcement on them, so a `most` or
> `all` is NOT ASSESSED, and a lower result says the hybrid nodes were not measured.
> **EKS Hybrid Nodes:** NOT ASSESSED on an EKS Hybrid Node, and deliberately counted as a collection gap rather than as inapplicable. NetworkPolicy really is enforced on hybrid nodes — Cilium and Calico are the CNIs AWS requires there and both enforce it — but this review collects neither, and the Amazon VPC CNI that this question measures is not compatible with a hybrid node.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get networkpolicies -A -o json
kubectl get namespaces -o json
# Compare: which namespaces have network policies
# Enforcement — standard cluster: the aws-eks-nodeagent container must be running AND must carry
# --enable-network-policy=true (absent means false), AND the amazon-vpc-cni ConfigMap must set
# enable-network-policy-controller: "true". Present-but-false is the shipped default and enforces nothing.
kubectl get daemonset aws-node -n kube-system -o json \
  | jq -r '.spec.template.spec.containers[]|select(.name=="aws-eks-nodeagent")|.args[]|select(startswith("--enable-network-policy"))'

# Enforcement — EKS Auto Mode (and the second half of the standard-cluster switch): the
# amazon-vpc-cni ConfigMap must turn the controller on.
kubectl get configmap amazon-vpc-cni -n kube-system -o json
```

**Remediation:** Two things are required, and a NetworkPolicy without the second does nothing.

**On an EKS Hybrid Node the enforcement point is not the VPC CNI** — it is the Cilium or Calico installation hybrid nodes require. The NetworkPolicy objects themselves are portable, but the ConfigMap step below has no effect on a hybrid node; enable policy enforcement in your CNI instead.

1. **Turn on enforcement.** Which switch depends on what runs your nodes. Every NetworkPolicy that
   already exists takes effect on the pods it selects as soon as enforcement is on, so review them
   first — especially any default-deny, and whether it allows DNS — preferably on a non-production
   cluster.

   *Standard nodes (managed node groups, self-managed EC2) — with the Amazon VPC CNI this is off by default:*

```bash
aws eks update-addon --cluster-name <CLUSTER> --addon-name vpc-cni --region <REGION> \
  --configuration-values '{"enableNetworkPolicy":"true"}'
```

   *EKS Auto Mode nodes — apply the `ConfigMap` AWS documents, which is the whole opt-in:*

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: amazon-vpc-cni
  namespace: kube-system
data:
  enable-network-policy-controller: "true"
```

   Once that is applied, policies are enforced on the node itself — AWS: "Enforcement of Kubernetes
   `NetworkPolicy` objects is implemented using the Extended Berkeley Packet Filter (eBPF)"
   (`eks/latest/userguide/cni-network-policy-configure.html`). A `NodeClass` step exists as well, and
   AWS describes it as **optional**: "Step 3: Adjust Network Policy Agent configuration in Node Class
   (Optional)" (`eks/latest/userguide/auto-net-pol.html`), where `spec.networkPolicy` (`DefaultAllow`
   or `DefaultDeny`) *adjusts* the agent the
   ConfigMap has already started and `spec.networkPolicyEventLogs: Enabled` turns on event logging.
   This review therefore reports whatever `spec.networkPolicy` you have set without scoring it —
   neither value switches enforcement off, and no AWS page states which one applies when the field is
   absent, so nothing is inferred from its absence. Calico or Cilium enforce natively and need neither
   switch on the nodes they run on.

   **On a mixed cluster you need both.** Auto Mode capabilities do not reach non-Auto-Mode nodes —
   AWS: "if your cluster combines Auto mode with other compute options like self-managed EC2
   instances, Managed Node Groups, or AWS Fargate, these add-ons remain necessary" — so a cluster with
   both node kinds and only one switch on leaves the other half of its pods unpoliced.

2. **Then write the policies.** Start with a default-deny per namespace and allow specific traffic —
   remembering to allow DNS, or every pod loses name resolution. On Auto Mode, CoreDNS runs on the
   node and its address comes from the cluster's service CIDR, not from a `kube-dns` Service endpoint.

> Consider `NETWORK_POLICY_ENFORCING_MODE=strict` only deliberately: pods then start default-deny before
> their policies are programmed, which breaks anything that talks during startup unless every path is
> already allowed.

---

### sec-14: Do you apply network separation to Pod networking using Kubernetes Network Policies or AWS security groups to control traffic between Pods and clusters?

**Detection:** ✋ ASK USER

> Assess the implementation of network segmentation and micro-segmentation for Pod communications.

**Remediation:** Apply NetworkPolicies or security groups per pod to enforce network segmentation between namespaces and workloads.

---

### sec-30: Is inbound SSH (port 22) closed to the internet on the cluster security groups?

**Detection:** 🔬 AUTO-DETECTABLE

> Disabling SSH reduces the attack surface on worker nodes. On EKS Auto Mode nodes AWS has already
> disabled it, and the security group is not the evidence that settles it: AWS states of Auto Mode
> managed instances that "SSH access is not available" and "AWS Systems Manager Session Manager (SSM)
> access is not available", and its security whitepaper that "remote access services like SSH and the
> AWS Systems Manager agent are not available on Auto Mode nodes". An open port 22 cannot reach a
> listener that does not exist, so on a cluster where every Linux EC2 node is an Auto Mode node this control
> is met by the platform and the security-group rule is not applied. That is a statement about port 22
> only — **net-4** covers the cluster security group's egress and **net-2** still measures `0.0.0.0/0`
> on every other port, so a permissive group is still reported, just not here. On a cluster that also
> runs a managed or self-managed node group, those nodes do run `sshd` and this question measures the
> security groups attached to their instances, tagged for the cluster or not.
> **EKS Hybrid Nodes:** This question still applies, and EKS Hybrid Nodes are reported NOT ASSESSED inside it. A hybrid node is not an EC2 instance and has no EC2 security group, so no rule in this measurement governs SSH to it: its sshd is the operator to reach and restrict, and the cluster security group carries only the control-plane ingress AWS adds for the remote node and pod CIDRs.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

> **Scope of the security-group half.** Where it does read security groups, it reads inbound `IpRanges`
> for `0.0.0.0/0` and `Ipv6Ranges` for `::/0` on the cluster's own groups, the cluster-tagged groups and
> every group attached to a Linux node instance (instance or network-interface level). It does not
> resolve `PrefixListIds`, peered-VPC CIDRs or `UserIdGroupPairs`, so port 22 reachable from a broad
> prefix list or from another security group is not reported here. And it reads the group, never the
> node: a pass means no internet-facing port-22 rule, not that `sshd` is stopped or that key material has
> been removed. **Systems Manager access is not measured either** — this
> review collects no SSM data, so whether a replacement break-glass path exists is guidance in the
> remediation, never a finding. The title names only the half that is measured. `net-2` applies the
> same `0.0.0.0/0`/`::/0` test to every other inbound port on the same groups. A group attached only to
> Windows node instances is left out of this measurement and counted in the detail (the cluster's own
> groups are always measured); a cluster whose only nodes are Windows nodes answers Not Applicable.

**Remediation:** **On an all-Auto-Mode cluster there is nothing to revoke and nothing to install** —
no `sshd` and no SSM agent are present, so the four preconditions below do not apply and step 4 cannot
succeed even on a correctly configured cluster. Break-glass access is the Kubernetes-native path AWS
provides instead: the `NodeDiagnostic` custom resource, which "is a Kubernetes-native method of
fetching system logs and information from an EKS Auto Mode node" and uploads them to S3 through a
pre-signed URL, plus EC2 console output and standard debug containers. Control who can use it with RBAC
on the `NodeDiagnostic` resource, and note that a Pod you deploy yourself *can* run an SSH or SSM
service — that session terminates in the container, not on the host.

For managed and self-managed node groups the path below applies. Revoking port 22 before the
replacement path is proven leaves a node with no
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
aws ec2 revoke-security-group-ingress --group-id <NODE_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=22,ToPort=22,Ipv6Ranges=[{CidrIpv6=::/0}]'
```

This question fails on `::/0` as well as `0.0.0.0/0`, and on any rule whose ports include 22, so run one
revoke per open rule and repeat that rule's protocol and ports exactly (an all-traffic rule is
`IpProtocol=-1` with no ports). A command that matches no rule revokes nothing (outside a default VPC it
returns `InvalidPermission.NotFound`), so leave out the `::/0` line on a group with no IPv6 rule.

A node that fails any of the four checks and then has SSH revoked has no path back except replacing the instance.

---

### sec-31: Do you avoid sharing security groups between EKS worker nodes and the control plane? — RETIRED

**Detection:** ⊘ NOT ASSESSED (always `na`)

> **This question is not scored.** AWS applies the cluster security group to the control plane
> and to managed compute by design, and states, of clusters originally deployed on
> Kubernetes 1.14 / platform version `eks.3` or earlier, that their separate control-plane and
> worker-node security groups are "no longer required and can be removed". The narrower point holds
> generally: today the cluster security group spans both planes by design. Answering
> it would penalise the configuration AWS now ships by default.
>
> The measurable control that remains in this area is **net-4**: whether the cluster security group's
> default allow-all egress to `0.0.0.0/0` has been narrowed.

---

## Network Infrastructure

### net-1: Do VPC subnets have sufficient available IP addresses (≥100 per subnet)?

**Detection:** 🔬 AUTO-DETECTABLE

> Low IP capacity causes pod scheduling failures.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws ec2 describe-subnets --filters Name=vpc-id,Values=<VPC_ID> --region <REGION> --query "Subnets[].{Id:SubnetId,AZ:AvailabilityZone,Available:AvailableIpAddressCount}"
```

**Remediation:** Expand subnets with low IP capacity or enable VPC CNI prefix delegation (`ENABLE_PREFIX_DELEGATION=true`) to increase available IPs per node.

---

### net-2: Do security groups follow least-privilege (no 0.0.0.0/0 on non-standard ports)?

**Detection:** 🔬 AUTO-DETECTABLE

> Open security group rules expose the cluster to unauthorized access.
> **Windows nodes:** not assessed — this skill supports Linux nodes only. A security group attached only
> to Windows node instances is left out of this measurement and counted in the detail.

**Commands:**
```bash
aws ec2 describe-security-groups --filters Name=vpc-id,Values=<VPC_ID> --region <REGION> --output json
# Check IpPermissions for 0.0.0.0/0 or ::/0 on anything other than a single-port TCP 80, TCP 443 or UDP 443 rule
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
aws ec2 revoke-security-group-ingress --group-id <SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=<PORT>,ToPort=<PORT>,Ipv6Ranges=[{CidrIpv6=::/0}]'
```

The `::/0` line removes a rule open to all of IPv6, which this question fails as well. The protocol and
ports must repeat the open rule exactly (an all-traffic rule is `IpProtocol=-1` with no ports); a command
that matches no rule revokes nothing (outside a default VPC it returns `InvalidPermission.NotFound`).

---

### net-3: Is VPC CNI prefix delegation enabled for improved IP capacity?

**Detection:** 🔬 AUTO-DETECTABLE

> Prefix delegation raises the IP ceiling per node by assigning /28 prefixes (16 IPs each) to a node's ENIs instead of individual secondary IPs. The gain is instance-type dependent — IPs per ENI × ENIs attached, both of which vary by instance size — not a flat number. EKS Auto Mode already does this: AWS states that "EKS Auto Mode defaults to using prefix delegation (/28 prefixes) for pod networking and maintains a predefined warm pool of IP resources that scales based on the number of scheduled pods", and that when pod subnet fragmentation is detected it falls back to secondary IPs on its own. The default is overridable, so it is verified rather than assumed: a `NodeClass` can set `spec.advancedNetworking.ipv4PrefixSize` to `"32"`, which AWS documents as "the secondary IP mode" — prefix delegation off. On a cluster that mixes Auto Mode with a managed or self-managed node group, only the Auto Mode nodes get the default; the rest take their pod IP mode from the `aws-node` DaemonSet, so this question keeps measuring that DaemonSet.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. `ENABLE_PREFIX_DELEGATION` changes how the Amazon VPC CNI allocates Pod IPs from ENI prefixes, and AWS documents the VPC CNI as incompatible with hybrid nodes, so there is no prefix delegation to turn on.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get daemonset aws-node -n kube-system -o json
# Check env ENABLE_PREFIX_DELEGATION
# EKS Auto Mode: prefix delegation is the default, so what matters is whether a NodeClass opted out.
kubectl get nodeclasses.eks.amazonaws.com -o json
# Check spec.advancedNetworking.ipv4PrefixSize — "Auto" (or unset) is prefix delegation, "32" is not.
```

<!-- MAINTAINER NOTE — not report content, placed before **Remediation:** for the same reason as the
     lens-11 note in workload-security.md: question_prose() in assets/render-report.py captures
     everything after "**Remediation:**" verbatim and html-escapes it for display, so a comment inside
     that span would reach the customer as literal text. Do not state a figure like "~15 to ~110": it is
     a worked example for one instance size, not a general fact, and 110 is no prefix-delegation output —
     it is Kubernetes' own default --max-pods-per-node cap, which AWS states plainly: "By default, the
     maximum number of Pods that you can run on a node is 110, but you can change that number."
     (https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses.html, fetched
     2026-09-11). Low severity, so this remediation stays a mechanism statement, not a worked example. -->

**Remediation:** Enable VPC CNI prefix delegation (`ENABLE_PREFIX_DELEGATION=true` on the aws-node
DaemonSet) on node groups running short on IPs. It raises the ceiling by IPs-per-ENI × ENIs, both
instance-type dependent, so the gain varies by instance size rather than following one before/after
number — and the 110-pods-per-node figure some instance types hit first is Kubernetes' own `--max-pods`
default, a separate, changeable ceiling on top of whatever IPs prefix delegation makes available.

**Not applicable to an EKS Hybrid Node** — prefix delegation is an Amazon VPC CNI setting and the VPC CNI does not run on one. Pod IP density on hybrid nodes is set by your Cilium or Calico IPAM configuration.

**On EKS Auto Mode there is nothing to enable** — prefix delegation is the default and the `aws-node`
env var does not apply, since "Configuration options for the previous AWS VPC CNI will not apply to EKS
Auto Mode". What to check instead is that no `NodeClass` has opted out with
`spec.advancedNetworking.ipv4PrefixSize: "32"`. If one has, **first ask whether that was deliberate**:
AWS recommends secondary IP mode for exactly one shape of workload — "For pod-sparse workloads (a few
pods per node, common in ML or GPU workloads, or anti-affinity-heavy workloads) targeting more than a
few hundred nodes per Availability Zone, secondary IP mode (`"32"`) is a more optimized configuration.
It allocates one IP per pod rather than reserving 16 per node, which extends the effective capacity of
`/20` pod subnets." For a pod-dense workload, remove the field (or set it to `Auto`) to return to the
default; for a pod-sparse one at that scale, leaving it is the better configuration and this finding is
informational rather than something to fix.

---

### net-4: Has the cluster security group's default allow-all egress been narrowed?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately outside the blockquote and the Remediation
     block so the renderer does not extract it (see question_prose() in assets/render-report.py, which
     takes the first `>` blockquote and the Remediation text only). Report readers scanning for what to
     type skim past a real warning when maintainer notes sit next to it.
     This question does not ask whether *separate* security groups are used for the control plane and
     worker nodes (securityGroupIds containing clusterSecurityGroupId), and must not: AWS applies the
     cluster security group to the control plane *and* to managed compute by design, and it is never a
     member of the additional-groups list, so such a check reports a separation that does not exist on
     essentially every cluster. AWS further states the old control-plane/node split is "no longer
     required and can be removed", so a remediation asking for that split contradicts current guidance
     (see sec-31, not scored).
     The blockquote below is one physical line on purpose: question_prose() keeps the `>` marker of
     every continuation line, so a wrapped blockquote ships stray `>` characters into the report. -->

> EKS creates the cluster security group with a default egress rule permitting all protocols to `0.0.0.0/0` (alongside a self-referencing rule for node-to-node traffic, which is not the concern here). Every node and every pod using the cluster SG inherits it, so a compromised pod can reach any internet endpoint — the outbound path used for data exfiltration and for pulling a second stage. Narrowing egress to the destinations the workload actually needs removes that path.

**Commands:**
```bash
aws ec2 describe-security-groups --group-ids <CLUSTER_SG_ID> --region <REGION> \
  --query 'SecurityGroups[].IpPermissionsEgress'
# Fails on ANY rule opening every port to 0.0.0.0/0 or ::/0 — `IpProtocol: "-1"`, or tcp/udp 0-65535, which
# grants identical egress and is not "narrowed".
```

**Remediation:** Replace the default egress rule on the cluster security group with specific
destinations. Most clusters need 443 to the VPC endpoints they use (`ecr.api`, `ecr.dkr`, `s3`, `sts`,
`logs`; an `s3` *gateway* endpoint is reached through its prefix list, `PrefixListIds=[{PrefixListId=<S3_PL_ID>}]`,
not the VPC CIDR), plus 443 to the control plane and any external service the workload calls. The revokes
below remove only the `0.0.0.0/0` and `::/0` ranges: the outbound-to-self rule EKS creates beside it stays and carries the
minimum AWS lists under "Restricting cluster traffic" (TCP 443, TCP 10250 and TCP/UDP 53 to the cluster
security group, https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html); where nodes or pods
use a different security group, add those rules to the cluster security group with that group as the
destination. Removing all egress will break image pulls and add-on updates, so add the replacements before revoking:

```bash
aws ec2 authorize-security-group-egress --group-id <CLUSTER_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=<VPC_CIDR>}]'
aws ec2 revoke-security-group-egress --group-id <CLUSTER_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]'
aws ec2 revoke-security-group-egress --group-id <CLUSTER_SG_ID> --region <REGION> \
  --ip-permissions 'IpProtocol=-1,Ipv6Ranges=[{CidrIpv6=::/0}]'
```

The `::/0` line removes the IPv6 allow-all egress this question also fails on; a tcp or udp 0-65535 rule
fails it too and is revoked with its own protocol and ports. On an IPv6 cluster, first authorize the
equivalent `Ipv6Ranges` replacement, or the revoke removes its IPv6 egress; a revoke matching no rule removes nothing.

---
