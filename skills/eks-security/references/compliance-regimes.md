# Compliance Regimes — Scope, Nuance & Worked Scenarios

The cross-cutting view over the 7-layer stack. **Compliance status changes over time — every claim here must be re-verified against the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before it goes into a customer-facing document.** The table below is a *map to verify against*, not a substitute for the live page.

## EKS compliance-scope table

| Program | Status | Notes |
|---|---|---|
| **PCI DSS Level 1** | ✅ Natively in scope | Customer owns workload-level controls (segmentation, access, logging, vuln mgmt) |
| **HIPAA** | ✅ Eligible | **Requires a signed BAA with AWS** before processing PHI |
| **SOC 1 / 2 / 3** | ✅ In scope | Reports in AWS Artifact |
| **ISO 27001 / 27017 / 27018 / 9001** | ✅ In scope | Reports in AWS Artifact |
| **FedRAMP Moderate** | ✅ In scope | **Commercial regions** |
| **FedRAMP High** | ✅ In scope | **GovCloud only** (us-gov-east-1, us-gov-west-1) |
| **HITRUST CSF** | ✅ In scope | Healthcare-focused |
| **IRAP / C5 / K-ISMS / ENS High / OSPAR** | ✅ In scope | Regional government programs (AU / DE / KR / ES / SG) |
| **DISA IL4 / IL5** | ✅ In scope — **GovCloud only** | DoD Impact Levels 4 & 5 are GovCloud-only; **commercial regions reach IL2 only**. Don't imply IL5 works in commercial. |
| **GDPR / data residency** | Alignment / framework | AWS provides DPA + enablers; **no independent GDPR certification**; customer owns workload controls |
| **NIST SP 800-53 / 800-171** | Alignment / framework | Audit Manager framework support |
| **CJIS** | Alignment / framework | Architectural enablers |

> **Language precision (these are graded by auditors):**
> - EKS is **"HIPAA-eligible"**, never "HIPAA-compliant" — the customer signs a BAA and owns workload-level controls. "HIPAA-compliant" implies an attestation AWS does not provide.
> - **FedRAMP Moderate ≠ High.** Moderate = commercial regions; High = GovCloud only. Promising High in commercial regions is a guaranteed audit failure.
> - For **alignment/framework** regimes (GDPR, NIST, CJIS), AWS provides enablers but **no independent attestation** — say so explicitly.

## Per-regime quick guidance

> **The three most common regimes have dedicated quick-starts** (control-mapping tables + 30/60/90 + shared responsibility): **HIPAA** → [compliance-hipaa.md](compliance-hipaa.md) · **PCI DSS** → [compliance-pci.md](compliance-pci.md) · **SOC 2** → [compliance-soc2.md](compliance-soc2.md). The bullets below are the at-a-glance version for these plus FedRAMP/GDPR.

- **HIPAA** ([deep-dive](compliance-hipaa.md)) — confirm an active BAA first; enable all 5 control-plane log types for forensic depth; 6-year documentation retention (§164.316(b)(2)); CMK for EBS/S3/EFS holding PHI; Audit Manager HIPAA framework; accept the BAA in AWS Artifact (Agreements) and pull supporting SOC 2/ISO reports for evidence — there is no HIPAA AOC to download.
- **PCI-DSS** ([deep-dive](compliance-pci.md)) — 1-year audit-log retention minimum; **CMK on EBS/S3/EFS holding cardholder data + no PAN in logs (Req 3)** and **mTLS for CHD over untrusted networks (Req 4)**; default-deny NetworkPolicy + Security Groups for Pods to segment cardholder-data namespaces (Req 1); ECR Enhanced Scanning (Req 6 + 11) + quarterly ASV external scan + annual penetration test + segmentation testing (Req 11.4.5, ≥12 months; 11.4.6, every 6 months for service providers); Security Hub PCI-DSS pack; PCI AOC from Artifact.
- **SOC 2** ([deep-dive](compliance-soc2.md)) — an attestation, not a certification; AWS's SOC report (Artifact) is a subservice carve-out, not the customer's own SOC 2; select Trust Services Categories (Security/Common Criteria always); Type II grades operating effectiveness over a defined 3–12 month observation period (3–6 common for a first Type II), so instrument logging early.
- **FedRAMP** — Moderate (commercial) vs High (GovCloud) is the first question; CMK for all data layers; VPC private endpoints to keep traffic on the AWS backbone; Audit Manager FedRAMP framework; confirm the authorizing agency for the customer's account.
- **GDPR** — EU-region-only clusters + all data layers in EU; no cross-region replication outside the EU; EU-region CloudWatch/CloudTrail; download the DPA from Artifact; the customer owns Article-17 erasure, DPIAs, and breach notification (Articles 33-34).

## Worked scenarios (decision shape, not copy-paste)

### 1 — HIPAA greenfield, open to AWS defaults
Bottlerocket + Pod Identity + Access Entries + PSA `restricted` + Kyverno + VPC CNI NetworkPolicy + Security Groups for Pods + ECR Enhanced Scanning + Cosign + GuardDuty for EKS + all 5 control-plane logs + CMK on PHI data layers + Audit Manager HIPAA framework. **Confirm the BAA is active before anything else.** 30/60/90: provision + enable logging/Audit Manager → onboard first PHI workload + validate Pod Identity/Access Entries/Kyverno/NetworkPolicy → HIPAA mock audit + remediate + confirm the signed BAA (Artifact Agreements) + supporting SOC 2 report (no HIPAA AOC exists).

### 2 — Vendor-OS mandate (RHEL), FedRAMP Moderate, federal
Layer 1 = custom CIS-hardened RHEL AMI on self-managed nodes via Image Builder (customer owns RHEL hardening + patch cycle), **or** ROSA if they want Red-Hat-managed OpenShift (separate product — defer to ROSA + Red Hat partner). Layers 2-7 identical to the canonical stack. FedRAMP nuance: Moderate = commercial regions; CMK for all data layers; VPC private endpoints. Surface Bottlerocket as the AWS-canonical alternative *if* the mandate is a support contract rather than specific RHEL features — without pushing past the mandate. Escalate if the customer needs FedRAMP **High** (GovCloud + partner).

### 3 — PCI-DSS existing-cluster hardening, audit in 4 months
Priority-ordered (not big-bang): Weeks 1-2 enable logging + GuardDuty + ECR scanning + Security Hub PCI pack + `kube-bench` baseline (non-disruptive). Weeks 3-6 `aws-auth` → Access Entries (change window), audit IRSA least-privilege. Weeks 7-10 PSA `restricted` (`audit`→`enforce`), Kyverno PCI policies, default-deny NetworkPolicy + SGP on the cardholder-data namespace. Weeks 11-14 migrate AL2→AL2023/Bottlerocket (AL2 OS EOL **June 30 2026**). Weeks 15-16 Audit Manager PCI framework + remediate + pull PCI AOC. Map controls to PCI Requirements 1/2/3/4/6/7/8/10/11.

### 4 — GDPR / EU data residency
GDPR is **alignment/framework** — no AWS certification. Architecture: EKS + all data layers in EU regions only; no non-EU replication; EU-region logs; VPC endpoints to avoid egress via non-EU edges; AWS European Sovereign Cloud for highest assurance (escalate for availability). Standard 7-layer baseline otherwise. Customer owns Article-17 erasure, DPIAs, breach notification; AWS provides the DPA (Artifact).

### 5 — EKS Auto Mode for a compliance-sensitive workload
The crux: is a CIS-hardened **custom** AMI a **hard regulatory requirement** or an **organizational preference**? Auto Mode doesn't support custom AMIs (or Cilium) as of 2026-07-17.
- **Hard requirement → Auto Mode not viable** → Bottlerocket on self-managed Karpenter NodePools.
- **Preference → Auto Mode viable** → lead with its reduced-permission node IAM (`AmazonEKSWorkerNodeMinimalPolicy`) as a HIPAA differentiator.
- Most compliance-sensitive customers land on **Bottlerocket + Karpenter** as the compromise (immutable OS + custom-AMI control + consolidation). Layers 2-7 are identical regardless of the Layer-1 choice.

## Escalate (compliance-specific)

First-time certification on a mission-critical regulated workload; XXL+ segment; FedRAMP High/GovCloud; Top Secret/Secret (out of scope); EKS Anywhere/Hybrid Nodes inside a FedRAMP boundary; multi-tenant SaaS with cross-tenant PHI/cardholder/federal isolation; customer-vs-auditor disagreement on AWS-managed-control acceptability; written legal commitments beyond Artifact; or any claim you cannot ground in an AWS-published source.

## Sources
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) (**authoritative — verify here**) · [Compliance Programs](https://aws.amazon.com/compliance/programs/)
- [HIPAA Eligible Services](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/) · [FedRAMP Services](https://aws.amazon.com/compliance/services-in-scope/FedRAMP/) · [ISO Certified](https://aws.amazon.com/compliance/iso-certified/) · [PCI DSS Level 1 FAQ](https://aws.amazon.com/compliance/pci-dss-level-1-faqs/) · [GDPR Center](https://aws.amazon.com/compliance/gdpr-center/)
- [AWS Artifact](https://aws.amazon.com/artifact/) · [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html)
