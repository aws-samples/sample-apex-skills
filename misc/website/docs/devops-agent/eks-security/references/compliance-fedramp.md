---
title: "FedRAMP on EKS: Quick-Start"
description: "A per-regime quick-start for preparing an EKS-hosted system for a FedRAMP assessment."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/compliance-fedramp.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-security/references/compliance-fedramp.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/compliance-fedramp.md). Edit the source, not this page.
:::

# FedRAMP on EKS: Quick-Start

A per-regime quick-start for preparing an EKS-hosted system for a FedRAMP assessment. Read the cross-regime scope table and language-precision rules in [compliance-regimes.md](compliance-regimes.md) first; this file is the FedRAMP-specific depth. This is a starting-point quick-start, **not a complete FedRAMP readiness checklist**: it maps the EKS-relevant NIST SP 800-53 Rev. 5 control families, not the full baseline an assessment covers.

> **Compliance status changes over time: verify on the live [AWS Services in Scope by Compliance Program: FedRAMP](https://aws.amazon.com/compliance/services-in-scope/FedRAMP/) page before quoting coverage for EKS and every other AWS service in the boundary in any customer-facing document.**

## Scope & the language that gets graded

- **Scope from the system's FIPS 199 impact level; classes only loosely align with it.** AWS US East/West is FedRAMP Certified **Class C (formerly Moderate baseline)**; AWS GovCloud (US) is **Class D (formerly High baseline)**. EKS is listed under both. Promising Class D (High) in commercial regions is a guaranteed audit failure.
- **"Certified", not "Authorized".** Under the FedRAMP Consolidated Rules for 2026 (CR26), "FedRAMP Authorized" is renamed "FedRAMP Certified" (CR26: optional from July 4, 2026, mandatory from January 1, 2027). The agency still issues its own **Authority to Operate (ATO)**: AWS's FedRAMP Certification is the cloud provider's, and it **does not certify or authorize the customer's system**. U.S. Government employees and contractors request AWS's FedRAMP Certification Package from the FedRAMP PMO (Package Access Request Form); commercial customers and partners get the FedRAMP Partner Package, and customers the Security Artifacts, from **AWS Artifact**.
- **The control catalog is NIST SP 800-53 Rev. 5**, with 20 control families. The table below covers the families where EKS settings carry the evidence; the rest (for example Planning, Personnel Security, Program Management) are process controls the customer documents.

## The FedRAMP-specific mapping (on top of the 7-layer baseline)

| NIST SP 800-53 Rev. 5 family | EKS control |
|---|---|
| AC: Access Control | EKS Pod Identity + Access Entries (`API` mode); least-privilege RBAC; private cluster endpoint (Config rule `eks-endpoint-no-public-access`, mapped to AC-6(3) in the High Part 2 pack) |
| IA: Identification and Authentication | Federated human access mapped to Access Entries; Pod Identity instead of long-lived keys in pods |
| AU: Audit and Accountability | Control-plane `audit`+`authenticator` logs + CloudTrail, retained per AU-11 (agencies apply M-21-31: 12 months active plus 18 months cold storage for most required logs) |
| CM: Configuration Management | PSA `restricted` + Kyverno admission; GitOps/CI for every change; ECR immutable tags; Bottlerocket or CIS-hardened AL2023 |
| SC: System and Communications Protection | Default-deny NetworkPolicy + Security Groups for Pods; VPC private endpoints; KMS CMK envelope encryption of Secrets and data layers; TLS in-cluster; SC-13 follows the CR26 Cryptographic Module Use rules: document every module that protects federal customer data; validated (FIPS 140) modules are a MUST at Class D and a SHOULD at Class C. FIPS nodes: Bottlerocket FIPS AMIs, AL2023 with FIPS mode enabled, or an Auto Mode NodeClass with `advancedSecurity.fips: true` (US Regions). FIPS endpoints, for example: EKS service API `fips.eks.<region>.amazonaws.com` (US East/West; in GovCloud the FIPS endpoint is the standard `eks.<region>.amazonaws.com`), ECR `api.ecr-fips.<region>.amazonaws.com` and `dkr.ecr-fips.<region>.amazonaws.com`, and an ALB FIPS TLS policy such as `ELBSecurityPolicy-TLS13-1-2-FIPS-2023-04` (in GovCloud, confirm FIPS TLS termination with the account team); every other service the build calls: the [AWS FIPS](https://aws.amazon.com/compliance/fips/) page |
| SI: System and Information Integrity | ECR Enhanced Scanning; GuardDuty for EKS (audit-log and runtime monitoring); node patching through managed node groups or Auto Mode |
| IR: Incident Response | GuardDuty + Security Hub findings into the incident process; see [security-event-response.md](security-event-response.md) |
| CP: Contingency Planning | Multi-AZ node groups, PDBs, backup/restore of cluster state and data |
| RA: Risk Assessment | Image and node vulnerability scanning; `kube-bench`; [posture-check.md](posture-check.md) |
| SR: Supply Chain Risk Management | Image signing (Cosign or Notation) verified at admission; trusted registries only |

## Config conformance packs (Layer 7)

- One pack per Rev5 baseline, names unchanged by the class rename: **"Operational Best Practices for FedRAMP(Low)"** (Class B), **"Operational Best Practices for FedRAMP(Moderate)"** (Class C), and Class D split across **"Operational Best Practices for FedRAMP (High Part 1)"** and **"Operational Best Practices for FedRAMP (High Part 2)"**. There is no bare "FedRAMP" pack among the console sample templates (the awslabs/aws-config-rules repo still holds an older bare template). "Operational Best Practices for NIST 800-53 rev 5" is a separate pack.
- **The packs are account-level evidence.** Across the four FedRAMP packs, the only EKS-specific rule is `eks-endpoint-no-public-access` (High Part 2). In-cluster controls (RBAC, PSA, NetworkPolicy, admission) need their own evidence: `kube-bench`, Kyverno policy reports, the posture check.
- AWS Audit Manager is in maintenance mode (existing setups only; see [compliance-accelerators.md](compliance-accelerators.md) for the dated status).

## 30 / 60 / 90 quick-start

- **Days 1-30, scope and evidence clock:** confirm the impact level and the class (Class C commercial or Class D GovCloud) and the authorization route (an agency's own system is authorized by the agency's ATO; a cloud service sold to agencies needs its own FedRAMP Certification); enable control-plane `audit`+`authenticator` logging + CloudTrail + GuardDuty + Security Hub; deploy the matching FedRAMP conformance pack; request AWS's FedRAMP Certification Package from the FedRAMP PMO, or get the Partner Package from Artifact.
- **Days 31-60:** Pod Identity + Access Entries + private endpoint (AC, IA); PSA `restricted` + Kyverno (CM); default-deny NetworkPolicy + SGP + CMK envelope encryption + FIPS nodes per the SC row (SC); document the access-review and change-management processes.
- **Days 61-90:** image signing + admission verification (SR); ECR Enhanced Scanning + GuardDuty runtime monitoring (SI; in GovCloud, a manually created Runtime Monitoring VPC endpoint uses `com.amazonaws.<region>.guardduty-data-fips`, and 8 EKS audit-log AnomalousBehavior finding types are not available); collect evidence via Security Hub, the conformance pack and the in-cluster reports; plan continuous monitoring, which under CR26 follows the Collaborative Continuous Monitoring (CCM) framework.

## Escalate

Class D (High) or DoD Impact Level work in GovCloud; a first agency ATO for the customer's system; deciding which controls are inherited from AWS versus owned by the customer; or an assessor disputing AWS-inherited controls. See [engagement-and-response.md](engagement-and-response.md).

## Shared responsibility (FedRAMP)

| AWS manages | Customer manages |
|---|---|
| Control plane + etcd; AWS's own FedRAMP Certification (Class C East/West, Class D GovCloud) and its continuous monitoring; the FedRAMP Partner Package and Security Artifacts in Artifact (the Certification Package through the FedRAMP PMO) | The customer system's own authorization (an agency ATO for an agency system, or the service's own FedRAMP Certification for a cloud service offered to agencies: see Days 1-30); choosing the class and Region; the in-cluster controls above and their evidence; the process controls (planning, personnel, program management) |

## Sources
- [AWS FedRAMP](https://aws.amazon.com/compliance/fedramp/) · [AWS Services in Scope: FedRAMP](https://aws.amazon.com/compliance/services-in-scope/FedRAMP/) (**authoritative: verify here**) · [FedRAMP 20x](https://www.fedramp.gov/20x/) · [AWS FIPS](https://aws.amazon.com/compliance/fips/)
- [NIST SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final) · [Config conformance pack sample templates](https://docs.aws.amazon.com/config/latest/developerguide/conformancepack-sample-templates.html) · [FedRAMP (High Part 2) pack](https://docs.aws.amazon.com/config/latest/developerguide/operational-best-practices-for-fedramp-high-part-2.html)
- [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html)
