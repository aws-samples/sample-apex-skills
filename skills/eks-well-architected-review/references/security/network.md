# 🔒 Security — Network Segmentation & Infrastructure

**8 questions** — Network policies, pod network separation, SSH access, security group separation, subnet IP capacity, prefix delegation.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access.md).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `not-applicable`.

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

**Detection:** ✋ ASK USER

> Disabling SSH reduces the attack surface on worker nodes.

**Remediation:** Remove SSH (port 22) from worker node security groups. Use AWS Systems Manager Session Manager for emergency node access instead.

---

### sec-31: Do you avoid sharing security groups between EKS worker nodes and the control plane?

**Detection:** ✋ ASK USER

> Separate security groups enforce network segmentation.

**Remediation:** Create separate security groups for worker nodes and the EKS control plane. Update node group launch templates to use the dedicated node SG.

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

### net-4: Are separate security groups used for the control plane and worker nodes?

**Detection:** 🔬 AUTO-DETECTABLE

> SG separation enforces network segmentation between control and data planes.

**Commands:**
```bash
aws ec2 describe-security-groups --filters Name=vpc-id,Values=<VPC_ID> --region <REGION>
# Compare cluster SG vs node SGs
```

**Remediation:** Create separate security groups for worker nodes and the EKS control plane. Do not reuse the cluster security group for node-to-node traffic.
