# FedRAMP on EKS: Quick-Start

A per-regime quick-start for preparing an EKS-hosted system for a FedRAMP assessment. Read the cross-regime scope table and language-precision rules in [compliance-regimes.md](compliance-regimes.md) first; this file is the FedRAMP-specific depth. This is a starting-point quick-start, **not a complete FedRAMP readiness checklist**: it maps the EKS-relevant NIST SP 800-53 Rev. 5 control families, not the full baseline an assessment covers.

> **Compliance status changes over time: verify on the live [AWS Services in Scope by Compliance Program: FedRAMP](https://aws.amazon.com/compliance/services-in-scope/FedRAMP/) page before quoting coverage in any customer-facing document.**

## Scope & the language that gets graded

- **Pick the class first.** AWS US East/West is FedRAMP Certified **Class C (formerly Moderate baseline)**; AWS GovCloud (US) is **Class D (formerly High baseline)**. EKS is listed under both. FedRAMP 20x names **Class B** for Low. Promising Class D (High) in commercial regions is a guaranteed audit failure.
- **"Certified", not "Authorized".** Under the FedRAMP Consolidated Rules for 2026 (CR26), "FedRAMP Authorized" became "FedRAMP Certified". The agency still issues its own **Authority to Operate (ATO)**: AWS's FedRAMP Certification is the cloud provider's, and it **does not certify or authorize the customer's system**. Pull AWS's FedRAMP package from **AWS Artifact** for the controls the customer inherits.
- **The control catalog is NIST SP 800-53 Rev. 5** (current release 5.2.0), with 20 control families. The table below covers the families where EKS settings carry the evidence; the rest (for example Planning, Personnel Security, Program Management) are process controls the customer documents.

## The FedRAMP-specific mapping (on top of the 7-layer baseline)

| NIST SP 800-53 Rev. 5 family | EKS control |
|---|---|
| AC: Access Control | EKS Pod Identity + Access Entries (`API` mode); least-privilege RBAC; private cluster endpoint (Config rule `eks-endpoint-no-public-access`, mapped to AC-6(3) in the High Part 2 pack) |
| IA: Identification and Authentication | Federated human access mapped to Access Entries; Pod Identity instead of long-lived keys in pods |
| AU: Audit and Accountability | Control-plane `audit`+`authenticator` logs + CloudTrail, retained for the assessment's evidence window |
| CM: Configuration Management | PSA `restricted` + Kyverno admission; GitOps/CI for every change; ECR immutable tags; Bottlerocket or CIS-hardened AL2023 |
| SC: System and Communications Protection | Default-deny NetworkPolicy + Security Groups for Pods; VPC private endpoints; KMS CMK envelope encryption of Secrets and data layers; TLS in-cluster; Bottlerocket FIPS AMIs where FIPS crypto is required |
| SI: System and Information Integrity | ECR Enhanced Scanning; GuardDuty for EKS (audit-log and runtime monitoring); node patching through managed node groups or Auto Mode |
| IR: Incident Response | GuardDuty + Security Hub findings into the incident process; see [security-event-response.md](security-event-response.md) |
| CP: Contingency Planning | Multi-AZ node groups, PDBs, backup/restore of cluster state and data |
| RA: Risk Assessment | Image and node vulnerability scanning; `kube-bench`; [posture-check.md](posture-check.md) |
| SR: Supply Chain Risk Management | Image signing (Cosign or Notation) verified at admission; trusted registries only |

## Config conformance packs (Layer 7)

- One pack per class, names unchanged by the class rename: **"Operational Best Practices for FedRAMP(Low)"** (Class B), **"Operational Best Practices for FedRAMP(Moderate)"** (Class C), and Class D split across **"Operational Best Practices for FedRAMP (High Part 1)"** and **"Operational Best Practices for FedRAMP (High Part 2)"**. There is no bare "FedRAMP" pack among the console sample templates (the awslabs/aws-config-rules repo still holds an older bare template). "Operational Best Practices for NIST 800-53 rev 5" is a separate pack.
- **The packs are account-level evidence.** Across the four FedRAMP packs, the only EKS-specific rule is `eks-endpoint-no-public-access` (High Part 2). In-cluster controls (RBAC, PSA, NetworkPolicy, admission) need their own evidence: `kube-bench`, Kyverno policy reports, the posture check.
- AWS Audit Manager is in maintenance mode (existing setups only; see [compliance-accelerators.md](compliance-accelerators.md) for the dated status).

## 30 / 60 / 90 quick-start

- **Days 1-30, scope and evidence clock:** confirm the class (Class C commercial or Class D GovCloud) and the authorizing agency; enable control-plane `audit`+`authenticator` logging + CloudTrail + GuardDuty + Security Hub; deploy the matching FedRAMP conformance pack; pull AWS's FedRAMP package from Artifact.
- **Days 31-60:** Pod Identity + Access Entries + private endpoint (AC, IA); PSA `restricted` + Kyverno (CM); default-deny NetworkPolicy + SGP + CMK envelope encryption (SC); document the access-review and change-management processes.
- **Days 61-90:** Bottlerocket (FIPS AMIs where required) or CIS-hardened AL2023; image signing + admission verification (SR); ECR Enhanced Scanning + GuardDuty runtime monitoring (SI); collect evidence via Security Hub, the conformance pack and the in-cluster reports; plan continuous monitoring, which under CR26 follows the Collaborative Continuous Monitoring (CCM) framework.

## Escalate

Class D (High) or DoD Impact Level work in GovCloud; a first agency ATO for the customer's system; deciding which controls are inherited from AWS versus owned by the customer; or an assessor disputing AWS-inherited controls. See [engagement-and-response.md](engagement-and-response.md).

## Shared responsibility (FedRAMP)

| AWS manages | Customer manages |
|---|---|
| Control plane + etcd; AWS's own FedRAMP Certification (Class C East/West, Class D GovCloud) and its continuous monitoring; the FedRAMP package in Artifact | The customer system's own ATO with its agency; choosing the class and Region; the in-cluster controls above and their evidence; the process controls (planning, personnel, program management) |

## Sources
- [AWS FedRAMP](https://aws.amazon.com/compliance/fedramp/) · [AWS Services in Scope: FedRAMP](https://aws.amazon.com/compliance/services-in-scope/FedRAMP/) (**authoritative: verify here**) · [FedRAMP 20x](https://www.fedramp.gov/20x/)
- [NIST SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final) · [Config conformance pack sample templates](https://docs.aws.amazon.com/config/latest/developerguide/conformancepack-sample-templates.html) · [FedRAMP (High Part 2) pack](https://docs.aws.amazon.com/config/latest/developerguide/operational-best-practices-for-fedramp-high-part-2.html)
- [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html)
