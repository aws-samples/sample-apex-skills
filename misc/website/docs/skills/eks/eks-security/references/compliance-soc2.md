---
title: "SOC 2 on EKS — Quick-Start"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-security/references/compliance-soc2.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-security/references/compliance-soc2.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-security/references/compliance-soc2.md). Edit the source, not this page.
:::

# SOC 2 on EKS — Quick-Start

A per-regime quick-start for preparing an EKS-hosted service for a SOC 2 examination. Read the cross-regime scope table and language-precision rules in [compliance-regimes.md](compliance-regimes) first; this file is the SOC 2-specific depth. This is a starting-point quick-start, **not a complete SOC 2 readiness checklist** — it maps the EKS-relevant Trust Services Criteria, not the full control set an examination covers.

> **Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting coverage in any customer-facing document.**

## Scope & the language that gets graded

- **SOC 2 is an attestation, not a certification**, performed by an independent CPA firm against the AICPA **Trust Services Criteria (TSC)**. AWS is **in scope for SOC 1/2/3** and its report is downloaded from **AWS Artifact** — but **AWS's SOC 2 does not make the customer's service SOC 2**. The customer must undergo **its own** examination; AWS's report is used via the **carve-out** method (the customer's description excludes AWS's controls and relies on AWS's SOC report as evidence — the near-universal choice; the *inclusive* method is the rarely-used alternative).
- **Type I** = design of controls at a point in time. **Type II** = *operating effectiveness* over a defined observation period (**typically 3–12 months**; a 3–6 month window is common for a first Type II, 12 months once established) — Type II is what customers and auditors actually want, and it requires a continuous evidence window, so **instrument logging early**.
- Select the applicable **Trust Services Categories**: **Security (Common Criteria — always required)**, plus optionally Availability, Confidentiality, Processing Integrity, and Privacy.

## The SOC 2-specific mapping (on top of the 7-layer baseline)

| Trust Services Criteria | EKS control |
|---|---|
| CC6 — logical & physical access | EKS Pod Identity + Access Entries (`API` mode); PSA `restricted`; least-privilege RBAC; private endpoint |
| CC7 — system operations / monitoring | GuardDuty for EKS + Security Hub; control-plane `audit`+`authenticator` + CloudTrail; ECR Enhanced Scanning |
| CC8 — change management | GitOps/CI with image signing (Cosign) + Kyverno admission; ECR immutable tags |
| CC6.6 / CC6.7 — boundary & transmission | Default-deny NetworkPolicy + Security Groups for Pods; TLS in-cluster; encryption at rest (CMK) |
| Availability (A1) — *if selected* | Multi-AZ node groups, PDBs, cluster autoscaling, backup/restore |
| Confidentiality (C1) — *if selected* | CMK on data layers; Secrets Manager + CSI/ESO; namespace/tenant isolation |

## 30 / 60 / 90 quick-start (Type II readiness)

- **Days 1-30 — start the evidence clock:** enable control-plane `audit`+`authenticator` logging + CloudTrail + GuardDuty + Security Hub (**CIS AWS Foundations + AWS FSBP**); enable ECR Enhanced Scanning; run `kube-bench`. Type II grades a *period* — the sooner these run, the sooner the observation window is clean.
- **Days 31-60:** Pod Identity + Access Entries (CC6); PSA `restricted` + Kyverno (CC8); default-deny NetworkPolicy + SGP (CC6.6); document the change-management + access-review process (the *process* evidence auditors sample).
- **Days 61-90:** Bottlerocket / CIS-hardened AL2023; image signing + admission verification; deploy Audit Manager (the SOC 2 mapping accelerates evidence collection); pull the **AWS SOC 2 report from Artifact** for the subservice carve-out; run the readiness assessment before the CPA examination.

## Escalate

First SOC 2 Type II on a mission-critical service; scoping which Trust Services Categories apply; multi-tenant SaaS confidentiality boundaries; or an auditor disputing the AWS subservice-organization carve-out. See [engagement-and-response.md](engagement-and-response).

## Shared responsibility (SOC 2)

| AWS manages | Customer manages |
|---|---|
| Control-plane + etcd; AWS's own SOC 1/2/3 examination; the SOC report in Artifact (subservice-organization controls) | The customer's own SOC 2 examination; selecting the Trust Services Categories; operating-effectiveness evidence over the Type II period; the change-management + access-review processes auditors sample |

## Sources
- [SOC on AWS](https://aws.amazon.com/compliance/soc-faqs/) · [AWS Artifact](https://aws.amazon.com/artifact/) · [AICPA Trust Services Criteria](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) (**authoritative — verify here**) · [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html)
