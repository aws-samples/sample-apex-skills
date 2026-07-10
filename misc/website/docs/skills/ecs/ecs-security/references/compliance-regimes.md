---
title: "Compliance Regimes — Scope, Discipline & Worked Scenarios"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/compliance-regimes.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/compliance-regimes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/compliance-regimes.md). Edit the source, not this page.
:::

# Compliance Regimes — Scope, Discipline & Worked Scenarios

The cross-cutting view over the 7-layer stack. **Compliance status changes over time — every scope claim must be re-verified against the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page (and the ECS-specific [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html)) before it goes into a customer-facing document.**

## The scope discipline (why there is no fixed table here)

Amazon ECS and AWS Fargate are broadly covered by AWS's major compliance programs, but **program scope is per-service, per-Region, and changes over time** — quoting a memorized ECS scope table is exactly the kind of claim an auditor rejects. So this skill deliberately does **not** reproduce a fixed "ECS is in scope for X/Y/Z" table. The correct move every time:

1. Open the **live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page**, filter to the customer's program(s) and Region(s), and confirm ECS / Fargate / ECR are listed. **Note:** program tables treat Fargate inconsistently (verified 2026-07-10): **PCI** covers it via the ECS row's bracketed note ("Amazon Elastic Container Service (ECS) [both Fargate and EC2 launch types]"); the **SOC and FedRAMP** tables list Amazon ECS with **no Fargate mention at all** (no bracketed note); the **HIPAA Eligible Services Reference** lists **AWS Fargate as its own line item**. Don't fail an ECS engagement just because "Fargate" isn't its own line item — but for programs whose table is silent on Fargate, confirm coverage with the AWS account team rather than asserting it.
2. Cross-check the ECS-specific [Compliance validation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html) page.
3. Pull the attestation (SOC 2 / ISO / PCI AOC / FedRAMP package) from **AWS Artifact** for the auditor. For HIPAA there is **no AOC or certification** and the HIPAA artifact is the **signed BAA** (accepted via AWS Artifact Agreements) ([AWS HIPAA compliance](https://aws.amazon.com/compliance/hipaa-compliance/)); auditors commonly also ask for supporting reports such as SOC 2 from Artifact.
4. State the customer-owned workload controls explicitly — AWS's scope covers the service, not the customer's configuration.

## Language precision (these are graded by auditors)

- **ECS/Fargate are "HIPAA-*eligible*"**, never "HIPAA-compliant" — a signed **BAA** with AWS is required before processing PHI, and the customer owns workload-level controls.
- **FedRAMP Moderate ≠ High.** Moderate is generally commercial-Region; High is generally GovCloud. Confirm on the live page for the customer's Region — don't promise High in commercial.
- **Fargate FIPS 140-3 is GovCloud (US) only**, off by default, LINUX + X86_64 + PV 1.4.0+ (verified — [Fargate FIPS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-fips-compliance.html)). Don't conflate 140-3 with 140-2.
- For **alignment/framework** regimes (GDPR, NIST 800-53/171, CJIS), AWS provides enablers/DPA rather than a traditional certification. For **GDPR specifically**, name the concrete enabler: the **CISPE Data Protection Code of Conduct** — the first pan-European Article 40 code of conduct for cloud infrastructure providers (approved by the EDPB and adopted by CNIL in 2021, independently verified by EY CertifyPoint). 100+ AWS services are listed on the **CISPE public register** as adherent; check whether ECS/Fargate/ECR are on it for the customer's assurance ([CISPE Code](https://aws.amazon.com/compliance/cispe/)).
- **ECS Anywhere** places the on-prem host, OS, and network entirely on the customer — it sits **outside** the AWS-managed compliance boundary for those hosts. Escalate for any regulated ECS Anywhere workload.

## Per-regime quick guidance (map controls to the 7 layers)

- **HIPAA** — confirm an active BAA first; prefer **Fargate** for per-task isolation of PHI workloads (no shared kernel); CMK on ECR/EBS/EFS/logs holding PHI; Secrets Manager injection (no plaintext); GuardDuty Runtime Monitoring; ~6-year log retention; Audit Manager HIPAA framework; hand the auditor the **signed BAA + SOC 2 report** (there is no "HIPAA AOC" — AWS: *"There is no HIPAA certification for a cloud service provider"*, [AWS HIPAA compliance](https://aws.amazon.com/compliance/hipaa-compliance/)).
- **PCI-DSS** — SG-per-service + private subnets + VPC endpoints to segment the cardholder-data environment (Req 1); ECR Enhanced Scanning + image hardening (Req 6/11); least-privilege task/execution roles + scoped `iam:PassRole` (Req 7); CloudTrail + Container Insights, ~1-year retention (Req 10); Security Hub PCI pack; PCI AOC from Artifact.
- **FedRAMP** — Moderate (commercial) vs High (GovCloud) is the first question; CMK for all data layers; VPC endpoints to keep traffic on the AWS backbone; Fargate FIPS if in GovCloud; Audit Manager FedRAMP framework; confirm the authorizing agency.
- **GDPR** — alignment/framework backed by the CISPE Code (above); DPA from Artifact (the AWS DPA + Standard Contractual Clauses apply automatically); customer owns erasure/DPIA/breach-notification. **EU-only residency is a customer *policy* choice, not a GDPR mandate** — the GDPR permits transfers outside the EU under an adequacy decision or appropriate safeguards (SCCs), and AWS applies the SCCs automatically for transfers to non-adequate countries ([AWS DPA / SCCs](https://docs.aws.amazon.com/whitepapers/latest/navigating-gdpr-compliance/aws-data-processing-addendum-dpa.html)). So keep ECS + data + logs EU-resident **if the customer's data-residency policy requires it** (and CISPE's EEA-only option supports that), but don't state EU-only as a GDPR requirement.

## Worked scenarios (decision shape, not copy-paste)

### 1 — HIPAA greenfield, open to AWS defaults, Fargate
Fargate (per-task isolation for PHI) + separate least-privileged task & execution roles with confused-deputy trust + `readonlyRootFilesystem`/non-root/`privileged:false`/dropped-caps/distroless + ECR Enhanced Scanning + AWS Signer signing + `awsvpc` SG-per-service in private subnets + VPC endpoints (ECR/S3/Secrets Manager/Logs) + Secrets Manager injection + CMK on data layers + GuardDuty Runtime Monitoring + Extended Threat Detection + CloudTrail + Audit Manager HIPAA framework. **Confirm the BAA is active before anything else.** 30/60/90: baseline detection → identity + secrets → workload/network/image + mock audit + assemble the HIPAA evidence pack (signed BAA + SOC 2 report from Artifact — no HIPAA AOC exists).

### 2 — PCI-DSS existing ECS-on-EC2 cluster, audit in 4 months
Priority-ordered (not big-bang): Weeks 1-2 enable CloudTrail + GuardDuty Runtime Monitoring (EC2 agent) + ECR Enhanced Scanning + Security Hub PCI pack + Config ECS rules (non-disruptive). Weeks 3-6 split over-broad roles → least-privileged task + execution roles, add confused-deputy conditions, scope `iam:PassRole`, migrate plaintext env-var secrets → Secrets Manager injection, **lock down IMDS from tasks** (no task isolation on EC2). Weeks 7-10 `readonlyRootFilesystem`/non-root/`privileged:false`/dropped-caps (test first), SG-per-service + private subnets + VPC endpoints on the CDE. Weeks 11-14 immutable tags + image signing; consider migrating the CDE to **Fargate** for per-task isolation. Weeks 15-16 Audit Manager PCI framework + remediate Security Hub + pull PCI AOC. Map to PCI Requirements 1/2/6/7/8/10/11.

### 3 — FedRAMP Moderate, federal, needs FIPS
FIPS-140 crypto is required. **Fargate FIPS is GovCloud-only** — if the workload must be FIPS on Fargate, it must run in GovCloud (escalate for the federal partner engagement + confirm the authorizing agency). Otherwise use FIPS endpoints and CMK across all data layers, VPC endpoints to keep traffic on the backbone, Audit Manager FedRAMP framework. Escalate if the customer needs FedRAMP **High**.

## Escalate (compliance-specific)

First-time certification on a mission-critical regulated workload; XXL+ segment; FedRAMP High / GovCloud; IL4/IL5; regulated **ECS Anywhere** (customer owns the host); multi-tenant SaaS with cross-tenant PHI/cardholder/federal isolation **on shared EC2 container instances** (no task isolation — recommend Fargate or account-per-tenant); customer-vs-auditor disagreement on AWS-managed-control acceptability; written legal commitments beyond Artifact; or any claim you cannot ground in an AWS-published source.

## Sources
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) (**authoritative — verify here**) · [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html) · [Compliance Programs](https://aws.amazon.com/compliance/programs/)
- [AWS Fargate FIPS-140](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-fips-compliance.html) · [HIPAA Eligible Services](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/) · [AWS Artifact](https://aws.amazon.com/artifact/)
- [CISPE Data Protection Code of Conduct](https://aws.amazon.com/compliance/cispe/) · [AWS Data Processing Addendum + SCCs (GDPR transfers)](https://docs.aws.amazon.com/whitepapers/latest/navigating-gdpr-compliance/aws-data-processing-addendum-dpa.html) · [GDPR Center](https://aws.amazon.com/compliance/gdpr-center/)
