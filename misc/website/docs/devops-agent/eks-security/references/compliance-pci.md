---
title: "PCI DSS on EKS — Quick-Start"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/compliance-pci.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-security/references/compliance-pci.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/compliance-pci.md). Edit the source, not this page.
:::

# PCI DSS on EKS — Quick-Start

A per-regime quick-start for running cardholder-data (CHD) workloads on Amazon EKS under PCI DSS. Read the cross-regime scope table and language-precision rules in [compliance-regimes.md](compliance-regimes) first; this file is the PCI-specific depth. This is a starting-point quick-start, **not a full PCI DSS checklist** — it maps the EKS-relevant requirements, not all 12 (Req 5/9/12 and the rest still apply to the cardholder-data environment).

> **Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting coverage in any customer-facing document. Requirement numbers and cadences below are as of PCI DSS v4.0.1 (June 2024) — re-verify against the current standard if it is renumbered.**

## Scope & the language that gets graded

- EKS is **natively in scope for PCI DSS Level 1** — AWS attests the infrastructure; **the customer owns the workload-level controls** (segmentation, access, logging, vuln management) and its own PCI assessment.
- The **PCI DSS Attestation of Compliance (AOC)** is downloaded from **AWS Artifact**; it covers AWS's responsibility, not the customer's cardholder-data environment (CDE).
- **Scope minimization is the highest-leverage move** — isolate the CDE into dedicated namespaces (or a dedicated cluster/account) so PCI controls apply to the smallest possible footprint.

## The PCI-specific controls (on top of the 7-layer baseline)

| PCI DSS requirement | EKS control |
|---|---|
| Req 1 — install & maintain network security controls (segmentation) | **Default-deny NetworkPolicy + Security Groups for Pods** isolating CDE namespaces; private endpoint |
| Req 2 — secure config | Bottlerocket / CIS-hardened AL2023; `kube-bench`; PSA `restricted` + Kyverno |
| Req 3 — protect stored account data | Render stored PAN unreadable via truncation, tokenization, keyed cryptographic hash of the entire PAN (Req 3.5.1.1; the keyed-hash condition — with key management per Reqs 3.6/3.7 — is a best practice that became mandatory 31 Mar 2025, replacing the older one-way-hash option of Req 3.5.1), or field-level strong crypto — CMK (KMS) disk/volume encryption on EBS/S3/EFS is **not** sufficient alone on non-removable media (Req 3.5.1.2); envelope-encryption CMK for the K8s API; mask PAN on display to BIN + last 4 (Req 3.4.1); no PAN in logs; minimize stored CHD |
| Req 4 — encrypt CHD in transit over open/public networks | TLS to clients; **mTLS** via service mesh for CHD-carrying paths that cross untrusted networks |
| Req 6 — secure development / patch | **ECR Enhanced Scanning** (Inspector); image signing; Auto Mode's ≤21-day node lifecycle (or managed-node patching) keeps replacement well inside the PCI one-month critical-patch window (Req 6.3.3) |
| Req 7 / 8 — access control | EKS Pod Identity + Access Entries (`API` mode); least-privilege RBAC; no static keys |
| Req 10 — logging & monitoring | Control-plane `audit`+`authenticator` + CloudTrail + GuardDuty; **1-year audit-log retention minimum, 3 months immediately available** (PCI DSS Req 10.5.1) |
| Req 11 — testing | ECR/Inspector continuous scanning; **quarterly ASV external scan** (Req 11.3.2) + **annual internal + external penetration tests** (Req 11.4.2 internal, 11.4.3 external); **segmentation testing** — at least once every 12 months, **every 6 months for service providers** (Req 11.4.5 / 11.4.6) — to prove the NetworkPolicy/SGP CDE isolation actually holds |

## Phased hardening quick-start — ~16 weeks (existing-cluster, audit-driven)

- **Weeks 1-2 (non-disruptive):** enable control-plane logging with **1-year** retention + GuardDuty + ECR Enhanced Scanning + the **Security Hub PCI DSS** standard + `kube-bench` baseline.
- **Weeks 3-6:** `aws-auth` → Access Entries (change window); audit IRSA/Pod Identity least-privilege (Req 7/8).
- **Weeks 7-10:** PSA `restricted` (`audit`→`enforce`); Kyverno PCI policies; **default-deny NetworkPolicy + Security Groups for Pods on the CDE namespace** (Req 1); render stored PAN unreadable — tokenize / keyed cryptographic hash of the entire PAN (Req 3.5.1.1) / field-level crypto (Req 3); mTLS for CHD in transit over open/public networks (Req 4).
- **Weeks 11-14:** migrate AL2 → AL2023 / Bottlerocket (AL2 OS reached EOL **2026-06-30** — already unsupported; prioritize).
- **Weeks 15-16:** AWS Config conformance packs **"Operational Best Practices for PCI DSS 4.0 (Excluding global resource types)" / "...(Including global resource types)"** (deploy the *Including* variant only in the global resources' home Region (us-east-1 in the commercial partition) — the only Region where its CloudFront/WAF/Shield rules find recorded configuration items — and the *Excluding* variant in every other Region (both variants also keep the global-IAM periodic rules, which evaluate in every Region regardless); see [recording global resource types in their home Region](https://docs.aws.amazon.com/config/latest/developerguide/select-resources.html)) + Security Hub PCI pack → remediate → pull the PCI AOC; schedule the quarterly ASV scan and segmentation testing (every 6 months as a service provider). Map controls to **Requirements 1/2/3/4/6/7/8/10/11**. (AWS Audit Manager's PCI framework works for existing accounts only — maintenance mode; see [compliance-accelerators.md](compliance-accelerators) for the dated status.)

## Escalate

First-time PCI Level 1 assessment; multi-tenant SaaS with cross-tenant CHD isolation; a CDE that cannot be network-segmented; or a QSA disputing an AWS-managed-control boundary. See [engagement-and-response.md](engagement-and-response).

## Shared responsibility (PCI DSS)

| AWS manages | Customer manages |
|---|---|
| Control-plane + etcd; PCI DSS L1 attestation of the infrastructure; the AOC in Artifact | CDE scoping + segmentation; the workload controls for Req 1/2/3/4/6/7/8/10/11; 1-year log retention; the quarterly ASV scan + annual pentest + segmentation testing (every 6 months as a service provider); the customer's own PCI assessment |

## Sources
- [PCI DSS on AWS](https://aws.amazon.com/compliance/pci-dss-level-1-faqs/) · [AWS Artifact](https://aws.amazon.com/artifact/) · [Security Hub PCI DSS standard](https://docs.aws.amazon.com/securityhub/latest/userguide/pci-standard.html)
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) (**authoritative — verify here**) · [EKS Best Practices: Compliance](https://docs.aws.amazon.com/eks/latest/best-practices/compliance.html)
