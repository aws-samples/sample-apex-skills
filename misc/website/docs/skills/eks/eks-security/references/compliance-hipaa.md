---
title: "HIPAA on EKS — Quick-Start"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-security/references/compliance-hipaa.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-security/references/compliance-hipaa.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-security/references/compliance-hipaa.md). Edit the source, not this page.
:::

# HIPAA on EKS — Quick-Start

A per-regime quick-start for running Protected Health Information (PHI) workloads on Amazon EKS. Read the cross-regime scope table and language-precision rules in [compliance-regimes.md](compliance-regimes) first; this file is the HIPAA-specific depth. This is a starting-point quick-start, **not a complete HIPAA Security Rule checklist** — it focuses on the EKS-relevant technical safeguards (§164.312/.316), not the full administrative (§164.308) and physical (§164.310) safeguards a HIPAA program also requires.

> **Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting coverage in any customer-facing document.**

## Scope & the language that gets graded

- EKS is **HIPAA-*eligible*** — **never "HIPAA-compliant."** "Compliant" implies an attestation AWS does not issue; the customer signs a BAA and owns workload-level controls.
- **A signed AWS Business Associate Addendum (BAA) is the first gate** — no PHI may be processed until it is active. Confirm the BAA covers **every service** in the data path (EKS, EBS, S3, EFS, CloudWatch Logs, etc.) via the [HIPAA Eligible Services reference](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/).
- **There is no HIPAA AOC or certification** — AWS states plainly that "there is no HIPAA certification for a cloud service provider." ("AOC / Attestation of Compliance" is PCI-DSS terminology, not HIPAA.) The HIPAA artifact you obtain from AWS is the **signed BAA**, accepted via **AWS Artifact → Agreements**; for supporting evidence you download AWS's SOC 2 / ISO reports (Artifact → Reports) and consult the "Architecting for HIPAA Security and Compliance on AWS" whitepaper. The customer proves its own Security Rule controls.

## The HIPAA-specific controls (on top of the 7-layer baseline)

| HIPAA Security Rule area | EKS control |
|---|---|
| Access control §164.312(a) | EKS Pod Identity + Access Entries (`API` auth mode); PSA `restricted`; least-privilege RBAC/IRSA |
| Audit controls §164.312(b) | **All 5 control-plane log types** for forensic depth (not just `audit`+`authenticator`); CloudTrail; GuardDuty for EKS |
| Integrity §164.312(c) | ECR Enhanced Scanning + Cosign/Notation image signing + Kyverno `verifyImages` |
| Transmission security §164.312(e) | TLS in-cluster; mTLS via service mesh for PHI-carrying paths |
| Encryption/decryption §164.312(a)(2)(iv) — *addressable*, applied at rest | **CMK** for EBS/S3/EFS holding PHI + envelope-encryption CMK for the K8s API |
| Documentation retention §164.316(b)(2) | **6-year** minimum retention of required documentation (commonly applied to audit-log/evidence retention as well) |

## 30 / 60 / 90 quick-start

- **Confirm the BAA is active — before anything else.** Then Days 1-30: enable all 5 control-plane logs (retain per your evidence policy — §164.316(b)(2)'s **6-year** rule governs *documentation*, commonly extended to logs), GuardDuty for EKS, ECR Enhanced Scanning, Security Hub; run `kube-bench`; deploy the Audit Manager **HIPAA Security Rule** framework.
- **Days 31-60:** Pod Identity + Access Entries; PSA `restricted` (`audit`→`enforce`); Kyverno; default-deny NetworkPolicy + Security Groups for Pods on PHI namespaces; CMK on every PHI data layer.
- **Days 61-90:** Bottlerocket (or CIS-hardened AL2023); image signing + admission verification; HIPAA mock audit → remediate → confirm the BAA is accepted in Artifact and pull supporting SOC 2 / ISO reports for the auditor (there is no HIPAA AOC to download).

## Escalate

First-time HIPAA audit/assessment on a mission-critical workload; multi-tenant SaaS with cross-tenant PHI isolation; PHI in a service not on the HIPAA-eligible list; or any control the customer cannot ground in an AWS-published source. See [engagement-and-response.md](engagement-and-response).

## Shared responsibility (HIPAA)

| AWS manages | Customer manages |
|---|---|
| Control-plane + etcd security; BAA coverage of eligible services; the SOC/ISO attestation reports + the accepted BAA in Artifact | The BAA signature; all workload-level Security Rule controls (access, audit, integrity, transmission, encryption); documentation retention (§164.316(b)(2) — 6-year); the risk assessment |

## Sources
- [HIPAA on AWS](https://aws.amazon.com/compliance/hipaa-compliance/) · [HIPAA Eligible Services](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/) · [AWS Artifact](https://aws.amazon.com/artifact/)
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) (**authoritative — verify here**) · [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html)
