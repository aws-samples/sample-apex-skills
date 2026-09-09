# 🔒 Security — Network Segmentation & Infrastructure

**8 questions** — Network policies, pod network separation, SSH access, cluster security group egress, subnet IP capacity, prefix delegation.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access.md).**
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

**Remediation:** Deploy NetworkPolicies in every namespace: start with a default-deny policy, then allow specific traffic. Use Calico or Cilium CNI for enforcement.

---

### sec-14: Do you apply network separation to Pod networking using Kubernetes Network Policies or AWS security groups to control traffic between Pods and clusters?

**Detection:** ✋ ASK USER

> Assess the implementation of network segmentation and micro-segmentation for Pod communications.

**Remediation:** Apply NetworkPolicies or security groups per pod to enforce network segmentation between namespaces and workloads.

---

### sec-30: Do you disable SSH access to worker nodes, using Systems Manager or similar for emergency access?

**Detection:** 🔬 AUTO-DETECTABLE

> Disabling SSH reduces the attack surface on worker nodes.

**Remediation:** Remove SSH (port 22) from worker node security groups. Use AWS Systems Manager Session Manager for emergency node access instead.

---

### sec-31: Do you avoid sharing security groups between EKS worker nodes and the control plane? — RETIRED

**Detection:** ⊘ NOT ASSESSED (always `na`)

> **This question is no longer scored.** AWS applies the cluster security group to the control plane
> and to managed compute by design, and states that the older practice of maintaining separate
> control-plane and worker-node security groups is "no longer required and can be removed". Answering
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

**Remediation:** Remove overly permissive security group rules (0.0.0.0/0 on non-443/80 ports). Use specific CIDR ranges and restrict to required ports only.

---

### net-3: Is VPC CNI prefix delegation enabled for improved IP capacity?

**Detection:** 🔬 AUTO-DETECTABLE

> Prefix delegation increases available IPs per node from ~15 to ~110.

**Commands:**
```bash
kubectl get daemonset aws-node -n kube-system -o json
# Check env ENABLE_PREFIX_DELEGATION
```

**Remediation:** Enable VPC CNI prefix delegation: set `ENABLE_PREFIX_DELEGATION=true` on the aws-node DaemonSet to increase IP capacity from ~15 to ~110 per node.

---

### net-4: Has the cluster security group's default allow-all egress been narrowed?

**Detection:** 🔬 AUTO-DETECTABLE

> EKS creates the cluster security group with a single egress rule permitting all protocols to
> `0.0.0.0/0`. Every node and every pod using the cluster SG inherits it, so a compromised pod can
> reach any internet endpoint — the outbound path used for data exfiltration and for pulling a second
> stage. Narrowing egress to the destinations the workload actually needs removes that path.

**Commands:**
```bash
aws ec2 describe-security-groups --group-ids <CLUSTER_SG_ID> --region <REGION> \
  --query 'SecurityGroups[].IpPermissionsEgress'
# Passes when no egress rule allows all protocols ("-1") to 0.0.0.0/0.
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

> **Not what this used to ask.** This question previously asked whether *separate* security groups
> were used for the control plane and worker nodes, testing whether `securityGroupIds` contained
> `clusterSecurityGroupId`. That premise was wrong: AWS applies the cluster security group to the
> control plane *and* to managed compute by design, and it is never a member of the additional-groups
> list — so the check reported a separation that does not exist on essentially every cluster. AWS
> further states the old control-plane/node split is "no longer required and can be removed", so the
> previous remediation advised the opposite of current guidance.
