---
name: eks-security
description: EKS security and compliance assessment — 7-layer hardening stack, CIS/HIPAA/PCI/FedRAMP/SOC2/GDPR audit prep, and 30/60/90 roadmap.
  Covers OS/AMI selection (Bottlerocket, AL2023, RHEL, Ubuntu), identity (EKS Pod Identity
  vs IRSA, Access Entries vs aws-auth), workload security (Pod Security Admission,
  Kyverno/OPA, NetworkPolicy, Security Groups for Pods), image supply chain (ECR scanning,
  Cosign/Notation signing), runtime detection (GuardDuty, Falco), audit logging, etcd /
  secrets encryption, and compliance accelerators (Audit Manager, Config, Security Hub).
  Triggers on CIS Benchmark, HIPAA, PCI-DSS, FedRAMP, SOC 2, GDPR compliance, cluster
  hardening, audit-prep, or any regulated-workload assessment. Does not cover non-EKS
  platforms (ECS/ROSA), account-level security with no EKS angle, or GenAI-workload
  security.
---

# EKS Security & Compliance

> **Execution model — fully autonomous.** This skill runs autonomously with no
> interactive prompts. If the request provides sufficient context (compliance regime,
> workload sensitivity, cluster topology), proceed through the full 7-layer analysis.
> If critical context is missing, infer from cluster state or apply documented defaults,
> noting all assumptions in the report output.

End-to-end, opinionated security and compliance guidance for Amazon EKS, structured as a **7-layer stack** plus a **compliance-regime cross-cutting view**. This skill is **discovery-driven** — the right hardening stack is a function of *(compliance regime x OS-standardization mandate x team skill x audit timeline x workload sensitivity x air-gap requirement x scale x operational-overhead tolerance)*. Skipping the discovery context makes the recommendation wrong about half the time.

Two AWS-published guides are the canonical foundation and every recommendation must align with one or both: the [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html) guide and the [EKS Best Practices: Runtime Security](https://docs.aws.amazon.com/eks/latest/best-practices/runtime-security.html) guide.

> **The accuracy bar (non-negotiable for this skill).** Compliance is the one domain where customers validate *every* claim against an auditor. **Compliance status changes over time — always defer to the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage** in any customer-facing document. Never state a cryptographic-module status, FedRAMP boundary, or certification you cannot cite to an AWS-published source. When you can't ground a claim, say so — do not synthesize.

## Prerequisites — Agent Space IAM Permissions

A ready-to-use IAM policy document is available at [`references/iam-policy.json`](references/iam-policy.json) — attach it directly to your Agent Space execution role.

The following read-only permissions are included:

| Service | Required Actions | Purpose |
|---------|-----------------|---------|
| **EKS** | `eks:DescribeCluster`, `eks:ListClusters`, `eks:ListAddons`, `eks:DescribeAddon`, `eks:ListAccessEntries`, `eks:ListPodIdentityAssociations` | Cluster configuration, add-on inventory, access model |
| **EC2** | `ec2:DescribeInstances`, `ec2:DescribeLaunchTemplates`, `ec2:DescribeSecurityGroups`, `ec2:DescribeImages` | Node groups, AMI identification, security group posture |
| **IAM** | `iam:ListRoles`, `iam:GetRole`, `iam:ListPolicies`, `iam:GetPolicyVersion`, `iam:ListOpenIDConnectProviders` | IRSA/Pod Identity roles, OIDC providers |
| **GuardDuty** | `guardduty:ListDetectors`, `guardduty:GetDetector`, `guardduty:ListFindings` | Runtime monitoring status, active findings |
| **Security Hub** | `securityhub:GetEnabledStandards`, `securityhub:GetFindings` | Compliance standards enabled, security findings |
| **Config** | `config:DescribeConfigRules`, `config:GetComplianceDetailsByConfigRule` | Configuration compliance posture |
| **CloudTrail** | `cloudtrail:DescribeTrails`, `cloudtrail:GetTrailStatus` | Audit logging verification |
| **Kubernetes API** | Read access to namespaces, pods, networkpolicies, podsecuritypolicies, clusterroles, clusterrolebindings | Workload security posture assessment |

> **Note:** This skill operates primarily as advisory guidance. When API access is available, it enriches recommendations with live cluster state. When API access is unavailable, it provides full guidance based on the context provided in the request.

## When to Use This Skill

**Activate when the goal involves:**
- Harden an EKS cluster or prepare for a first-time compliance audit (HIPAA, PCI-DSS, FedRAMP, SOC 2, ISO 27001, GDPR, HITRUST, NIST 800-53/171)
- Choose an OS / AMI strategy for security (Bottlerocket vs AL2023-with-CIS vs Ubuntu Pro vs RHEL vs Auto Mode)
- Decide identity & access (EKS Pod Identity vs IRSA; Access Entries vs `aws-auth`)
- Apply workload security (Pod Security Admission, Kyverno/OPA, NetworkPolicy, Security Groups for Pods)
- Secure the image supply chain (ECR Enhanced Scanning, Cosign/Notation signing, admission verification)
- Add runtime security (GuardDuty for EKS, Falco) and audit logging (control-plane logs, CloudTrail, SIEM)
- Wire compliance accelerators (Audit Manager, Config, Security Hub, Artifact)

**Don't use this skill for:**
- Non-EKS container platforms — **ECS/Fargate-without-EKS** (defer to ECS security guidance) or **ROSA** (Red Hat manages the stack differently)
- **AWS account-level / org-wide security** with no EKS-specific angle (IAM org policy, SCPs, SSO, multi-service GuardDuty)
- **GenAI/GPU workload security** specifically (model-artifact provenance, training-data confidentiality, GPU-node compliance) — use EKS GenAI guidance
- Generic EKS architecture/cost/upgrade decisions with no security driver
- Generating Terraform/Helm or auditing a live cluster's operational posture

## Discovery First — Context Gates

**Do NOT recommend a hardening stack without the following context.** The single most common mistake is reflexively saying "use Bottlerocket" or "use AL2023 with CIS hardening" without confirming the customer's context. The first four items alone determine ~80% of the recommendation.

### Autonomous Context Resolution

If the request does not specify the following three items, infer from cluster context (tags, labels, namespace naming, existing policies) or apply the stated defaults. Note all assumptions in the report output.

1. **Compliance regime(s)** — If not determinable from cluster context (e.g., tags like `compliance:hipaa`, namespace names, existing admission policies), assume **SOC 2** as the baseline and note the assumption. Available regimes: None / SOC 2 / HIPAA / PCI-DSS / FedRAMP Moderate / FedRAMP High / GDPR / ISO 27001 / HITRUST / NIST 800-53/171 / CJIS / DISA IL5
2. **Workload sensitivity** — If not determinable from cluster context (e.g., namespace labels, network policies, encryption settings), assume **internal** and note the assumption. Levels: Public / internal / PII / PHI (HIPAA) / cardholder data (PCI) / federal
3. **OS / AMI preference** — If not determinable from node AMI IDs or launch templates, assume **Open to AWS defaults** and note the assumption. Options: Open to AWS defaults / Bottlerocket-first / AL2023+CIS / Ubuntu mandate / RHEL mandate / EKS Auto Mode

### Context Already Provided When

The request already provides sufficient context — for example:
- "Harden my HIPAA cluster running Bottlerocket on EKS 1.31 in us-east-1"
- "What's the FedRAMP Moderate security stack for EKS with AL2023?"
- "We need SOC 2 compliance for our PII workloads on EKS Auto Mode"

### Additional Context (gather when depth allows, use defaults if unavailable)

4. **Audit timeline?** None / <3 mo (urgent) / 3-6 mo / 6-12 mo / continuous.
5. **Cluster topology?** Single vs multi-cluster, single vs multi-account, multi-region, EKS Anywhere, Hybrid Nodes, GovCloud.
6. **Team K8s/security skill?** Low / moderate / high / mixed.
7. **Operational-overhead tolerance?** Zero (managed-only) / low / moderate / high.
8. **Current security tooling baseline?** None / AWS-native / third-party CNAPP / OSS / hybrid.

Full required + recommended question set, the 5 adoption-challenge archetypes, and the 8-step response framework: [references/engagement-and-response.md](references/engagement-and-response.md).

## The 7-Layer Security & Compliance Stack

Walk the layers bottom-up on a first engagement; each layer's controls compound on the previous.

| Layer | Focus | AWS-canonical default | Reference |
|-------|-------|----------------------|-----------|
| **1 — Compute / OS / AMI** | Node hardening | **Bottlerocket** (immutable, SELinux-enforcing, minimal); else CIS-hardened AL2023 via Image Builder; respect vendor-OS mandates (Ubuntu Pro / RHEL) | [os-ami-hardening.md](references/os-ami-hardening.md) |
| **2 — Identity & Access** | Who can do what | **EKS Pod Identity** (workloads) + **EKS Access Entries** (cluster access) | [identity-and-access.md](references/identity-and-access.md) |
| **3 — Workload Security** | Pod + network posture | **PSA `restricted`** + **Kyverno** (or OPA) + **VPC CNI NetworkPolicy** (default-deny) + **Security Groups for Pods** | [workload-security.md](references/workload-security.md) |
| **4 — Image Supply Chain** | Trust what you run | **ECR Enhanced Scanning** (Inspector) + **Cosign/Notation signing** + Kyverno `verifyImages` admission | [image-supply-chain.md](references/image-supply-chain.md) |
| **5 — Runtime Security** | Detect at runtime | **GuardDuty for EKS** (EKS Protection + Runtime Monitoring); Falco for OSS/custom rules; findings → Security Hub | [runtime-security.md](references/runtime-security.md) |
| **6 — Audit Logging & Forensics** | Prove what happened | EKS control-plane logs (**`audit` + `authenticator` minimum**) + CloudTrail + VPC Flow Logs + SIEM forwarding | [audit-logging.md](references/audit-logging.md) |
| **7 — Compliance Accelerators** | Continuous evidence | **Audit Manager** + **Config** + **Security Hub** + **Artifact** (download attestations) | [compliance-accelerators.md](references/compliance-accelerators.md) |

> **The AWS-canonical reference stack for a new commercial cluster:** Bottlerocket (L1) + Pod Identity + Access Entries (L2) + PSA `restricted` + Kyverno + VPC CNI NetworkPolicy + Security Groups for Pods (L3) + ECR Enhanced Scanning + Cosign signing (L4) + GuardDuty for EKS (L5) + control-plane `audit`+`authenticator` logging + CloudTrail (L6) + Audit Manager + Config + Security Hub (L7). The **vendor-OS path** applies the same stack with a Layer-1 substitution only.

**Cross-cutting concerns** (span every layer, aligned to the AWS Best Practices security areas): **data encryption & secrets management** (default envelope encryption on K8s 1.28+, CMK, Secrets Manager/CSI/ESO) → [encryption-and-secrets.md](references/encryption-and-secrets.md); **multi-tenancy & multi-account isolation** (soft vs hard, namespaces→cluster-/account-per-tenant) → [multi-tenancy.md](references/multi-tenancy.md); **incident response & forensics** (the runbook when a detection fires) → [incident-response-and-forensics.md](references/incident-response-and-forensics.md); and the **shared-responsibility model** — AWS secures the control plane (control-plane nodes + etcd) and assumes more as you move self-managed → MNG → Fargate; you secure the data plane, node OS, workloads, and the controls in this skill. Each reference includes its per-layer shared-responsibility split.

## Compliance-Regime Scope (cross-cutting)

EKS is **natively in scope** for PCI-DSS L1, HIPAA-eligible (BAA required), SOC 1/2/3, ISO 27001/27017/27018/9001, FedRAMP Moderate (commercial) and High (GovCloud only), HITRUST CSF, IRAP, C5, K-ISMS, ENS High, OSPAR, DISA IL4/IL5 (GovCloud only — commercial reaches IL2). AWS provides **alignment / framework support** (not independent attestation) for GDPR, NIST SP 800-53/800-171, and CJIS — the customer owns workload-level controls. Per-regime nuance, the scope table, and the worked HIPAA/PCI/FedRAMP/GDPR/Auto-Mode scenarios: [references/compliance-regimes.md](references/compliance-regimes.md).

> **Always include the disclaimer in customer-facing output:** "Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage." And precision matters: EKS is **HIPAA-*eligible*** (with a signed BAA), not "HIPAA-compliant"; FedRAMP **High = GovCloud only**, Moderate = commercial regions.

## Security Baseline (non-negotiable — every recommendation includes this)

Regardless of regime, every hardening recommendation MUST include:
- **EKS Pod Identity** (recommended for new workloads; IRSA is a fully supported alternative — see note) — never static AWS keys
- **EKS Access Entries** for cluster access — never the `aws-auth` ConfigMap on new clusters
- **EKS control-plane logging** — `audit` + `authenticator` at minimum
- **GuardDuty for EKS** — EKS Protection (audit-log) + Runtime Monitoring (agent)
- **ECR Enhanced Scanning** on all production repositories
- **Pod Security Admission `restricted`** on production namespaces
- **NetworkPolicy default-deny** on production namespaces (VPC CNI native, or Calico/Cilium on self-managed)
- **Encryption at rest** — EKS provides **default envelope encryption of all Kubernetes API data** (KMS provider v2, AWS-owned key) on **K8s 1.28+ with no action required**; bring a **customer-managed KMS key (CMK)** for control over rotation/audit, and use CMKs for EBS/S3/EFS under compliance regimes (etcd EBS volumes are also EBS-encrypted independently)
- **Encryption in transit** — TLS in-cluster; mTLS via service mesh for high-sensitivity workloads
- **Secrets via Secrets Manager + Secrets Store CSI Driver + ASCP** (or External Secrets Operator) — never plain Kubernetes Secrets in production; never baked into images
- **CloudTrail** for EKS API audit; **private API endpoint** (or restricted public CIDR allowlist) for production
- **Preventive governance (multi-account):** enforce the above with **EKS IAM condition keys** in SCPs/IAM (private endpoint, CMK encryption, approved K8s version, deletion protection) so non-compliant clusters can't be created — see [identity-and-access.md](references/identity-and-access.md)

## Hardening Roadmap (30 / 60 / 90)

- **Days 1-30 (baseline, non-disruptive):** enable control-plane `audit`+`authenticator` logging; enable GuardDuty for EKS; enable Security Hub (CIS AWS Foundations + AWS FSBP); enable ECR Enhanced Scanning; run `kube-bench` for the current CIS posture. *Change nothing yet — establish the baseline.*
- **Days 31-60 (identity + workload):** migrate `aws-auth` → Access Entries (planned change window, `kubectl` access pre-validated); migrate/justify IRSA → Pod Identity; enable PSA `restricted` (start `audit` mode → `enforce`); deploy Kyverno/OPA; enforce NetworkPolicy default-deny.
- **Days 61-90 (OS + image + accelerators):** migrate to Bottlerocket (or build CIS-hardened AL2023 via Image Builder); enable ECR image signing; deploy Audit Manager with the applicable framework; validate Security Hub against the compliance pack; download attestations from AWS Artifact.
- **Greenfield:** deploy the full 7-layer stack at cluster creation, not retrofitted.

## Top Guardrails (the high-cost mistakes)

- **Don't recommend a stack before the discovery context is confirmed** — the #1 mistake.
- **Don't call IRSA "legacy"** — AWS docs say Pod Identity is *recommended for new workloads* while **IRSA remains a fully supported alternative** (and is the right choice on Fargate, Windows nodes, unsupported SDKs, or cross-account OIDC federation). "Legacy" applies to the `aws-auth` ConfigMap, not IRSA.
- **Don't use `aws-auth` ConfigMap on new clusters** — it's deprecated; use Access Entries (auditable in CloudTrail).
- **Don't recommend PodSecurityPolicy (PSP)** — removed in Kubernetes 1.25+; use PSA + Kyverno/OPA.
- **Don't recommend AWS App Mesh for new work** — end of support **Sept 30, 2026**; use Istio/Linkerd/Cilium mesh or VPC Lattice.
- **Don't recommend EKS Auto Mode when a hard CIS-hardened-*custom*-AMI requirement exists** — Auto Mode doesn't support custom AMIs (as of June 2026); use Bottlerocket on self-managed Karpenter NodePools. Cilium CNI is also not supported on Auto Mode.
- **Don't promise "HIPAA-compliant"** — EKS is HIPAA-*eligible*; a signed BAA is required and the customer owns workload-level controls.
- **Don't conflate** FedRAMP Moderate (commercial) with High (GovCloud); FIPS 140-3 (Bottlerocket FIPS AMIs) with 140-2; or CIS AL2 with CIS AL2023 benchmarks (distinct documents).
- **Don't treat a CMK as free of operational risk** — once a CMK is the envelope-encryption key, **disabling it degrades the cluster** (the API server can't boot on restart; ~30-day window to re-enable before forced auto-upgrade) and **deleting it makes the cluster unrecoverable**. Guard the CMK with least-privilege IAM + a CloudWatch alarm.
- **Don't synthesize compliance claims** — cite an AWS-published source or recommend escalation.

## Escalation

Recommend engaging AWS Professional Services or an AWS Solutions Architect for:
- First-time certification on a **mission-critical regulated workload** (highest stakes).
- **FedRAMP High / GovCloud** → federal partner engagement.
- **Top Secret / Secret classified** → AWS Top Secret/Secret region partner (out of scope here — commercial + GovCloud only).
- **EKS Anywhere (air-gapped) or Hybrid Nodes inside a FedRAMP boundary** → shared-responsibility boundary mapping (AWS manages no control plane in air-gapped EKS Anywhere; Hybrid on-prem nodes are outside the FedRAMP boundary).
- **Multi-tenant SaaS** with cross-tenant PHI / cardholder / federal isolation.
- **Customer vs auditor disagreement** on AWS-managed-control acceptability (e.g., AWS-managed AMI patching vs documented patch cycle) → joint review with the auditor.
- **Written legal commitment** beyond Artifact (custom DPA, FedRAMP ConMon SLA, sovereignty-plus).
- **AI/ML workloads with PHI/cardholder/federal data** → joint AI/ML + Security review.
- **Cannot ground the response** → do not synthesize; escalate. Rejected compliance guidance leads to audit findings and erodes trust.

Full criteria: [references/engagement-and-response.md](references/engagement-and-response.md).

## How to Use the References

Progressive disclosure — the essentials are above; load a reference only when the task needs that depth:

| Reference | Load when the task is about... |
|-----------|------------------------------|
| [engagement-and-response.md](references/engagement-and-response.md) | Full discovery question set, adoption-challenge archetypes, the 8-step response framework, escalation criteria |
| [os-ami-hardening.md](references/os-ami-hardening.md) | Layer 1 — Bottlerocket vs AL2023 vs Ubuntu/RHEL, CIS benchmark hierarchy, Image Builder hardened-AMI pipeline, FIPS |
| [identity-and-access.md](references/identity-and-access.md) | Layer 2 — Pod Identity vs IRSA, Access Entries vs aws-auth, access policies |
| [workload-security.md](references/workload-security.md) | Layer 3 — PSA, Kyverno/OPA, NetworkPolicy, Security Groups for Pods, service-mesh mTLS |
| [image-supply-chain.md](references/image-supply-chain.md) | Layer 4 — ECR Enhanced Scanning, Cosign/Notation signing, admission control, third-party scanners |
| [runtime-security.md](references/runtime-security.md) | Layer 5 — GuardDuty for EKS, Falco, Security Hub aggregation |
| [audit-logging.md](references/audit-logging.md) | Layer 6 — control-plane log types, CloudTrail, VPC Flow Logs, SIEM forwarding, retention |
| [compliance-accelerators.md](references/compliance-accelerators.md) | Layer 7 — Audit Manager, Config, Security Hub, Artifact, kube-bench |
| [encryption-and-secrets.md](references/encryption-and-secrets.md) | Default envelope encryption (KMS v2), CMK + its operational risk, EBS/EFS/FSx encryption, Secrets Manager/CSI/ESO/Sealed Secrets, secret hygiene |
| [multi-tenancy.md](references/multi-tenancy.md) | Soft vs hard multi-tenancy, in-cluster isolation (namespaces/RBAC/NetworkPolicy/quotas/node isolation), cluster-/account-per-tenant |
| [incident-response-and-forensics.md](references/incident-response-and-forensics.md) | IR runbook for a compromised pod/node, isolation/eradication, credential revocation, forensic capture |
| [compliance-regimes.md](references/compliance-regimes.md) | Per-regime scope (HIPAA/PCI/FedRAMP/GDPR/ISO/...), the scope table, worked scenarios, regime-specific controls |

## Sources

- [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html) · [EKS Best Practices: Runtime Security](https://docs.aws.amazon.com/eks/latest/best-practices/runtime-security.html) · [EKS Best Practices: Cluster Access Management](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-access-management.html)
- [Meet compliance requirements with Bottlerocket](https://docs.aws.amazon.com/eks/latest/userguide/bottlerocket-compliance-support.html) · [Bottlerocket FIPS AMIs](https://docs.aws.amazon.com/eks/latest/userguide/bottlerocket-fips-amis.html)
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) · [IRSA](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) · [Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
- [GuardDuty EKS integration](https://docs.aws.amazon.com/eks/latest/userguide/integration-guardduty.html) · [Control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html) · [VPC CNI NetworkPolicy](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html)
- [AWS Compliance Programs](https://aws.amazon.com/compliance/programs/) · [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [AWS Artifact](https://aws.amazon.com/artifact/)
- [aws/aws-eks-best-practices](https://github.com/aws/aws-eks-best-practices) · [EKS Security Immersion Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/165b0729-2791-4452-8920-53b734419050) · [kube-bench](https://github.com/aquasecurity/kube-bench)

