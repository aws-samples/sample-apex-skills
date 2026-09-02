---
title: "Layer 7b — Compliance Accelerators"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/compliance-accelerators.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/compliance-accelerators.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/compliance-accelerators.md). Edit the source, not this page.
:::

# Layer 7b — Compliance Accelerators

Tools that continuously **evaluate the hardened ECS estate's technical controls and flag drift** — narrowing, not eliminating, the audit-prep gap. They **record only Configuration Items as control evidence** — not a general solution to capture, organize, and share evidence for the full control set, and no AM-equivalent report assembly; assembling, organizing, and mapping the full evidence set remains the customer's job, for every regime.

| Service | Function for ECS | Reference |
|---|---|---|
| **AWS Config** | Resource-configuration compliance; rules that evaluate ECS task definitions/services — e.g. **`ecs-containers-nonprivileged`** (no privileged containers), read-only-rootfs, no plaintext secrets, `awsvpc` mode, no host networking. Flags drift continuously. | [AWS Config](https://aws.amazon.com/config/) |
| **AWS Security Hub** | CSPM; aggregates GuardDuty + Inspector + Config findings; runs the **ECS controls pack** (ECS.4, ECS.5, plaintext-secret and host-mode checks) and standards (AWS FSBP, CIS, NIST 800-53, PCI-DSS). | [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html) |
| **AWS Config conformance packs** | Managed rule packs that continuously **evaluate technical controls and flag drift** (e.g. "Operational Best Practices for HIPAA Security"; "Operational Best Practices for PCI DSS 4.0 (Excluding global resource types)" / "...(Including global resource types)"; "Operational Best Practices for NIST 800-53 rev 5"; "Operational Best Practices for FedRAMP(Low)" / "...FedRAMP(Moderate)" — plus "...FedRAMP (High Part 1)" / "...FedRAMP (High Part 2)"; there is no bare "FedRAMP" pack — exact display names per the [conformance pack sample templates](https://docs.aws.amazon.com/config/latest/developerguide/conformancepack-sample-templates.html)). They are **not equivalent to Audit Manager Frameworks (which remain available in maintenance mode)**: they record only Configuration Items as control evidence — not a general solution to capture, organize, and share evidence for the full control set, and no AM-equivalent report assembly — this applies to **all** regimes (HIPAA/PCI included, not just SOC 2/GDPR), where the evidence layer is the customer's via Security Hub + partner/GRC tooling. No AWS-native pack exists for SOC 2 or GDPR. **Canonical dated status (referenced elsewhere): AWS Audit Manager, the prior evidence engine, is closed to new accounts / maintenance mode as of 2026-04-30 (existing setups continue) ([availability change](https://docs.aws.amazon.com/audit-manager/latest/userguide/audit-manager-availability-change.html)).** | [AWS Config conformance packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html) |
| **AWS Artifact** | Self-service download of SOC 2, ISO 27001, PCI-DSS AOC, FedRAMP packages, and the AWS Data Processing Addendum (DPA) — the documents you hand an auditor; also where you accept agreements like the **HIPAA BAA** (there is **no "HIPAA AOC"** — no HIPAA certification exists for a CSP and the HIPAA artifact is the signed BAA, per [AWS HIPAA compliance](https://aws.amazon.com/compliance/hipaa-compliance/); auditors commonly also ask for supporting reports such as SOC 2, downloadable from Artifact). | [AWS Artifact](https://aws.amazon.com/artifact/) |
| **AWS Services in Scope / Compliance Programs** | The authoritative, **live** source for which programs ECS and Fargate are in scope for. | [Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [ECS compliance validation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html) |

## How they fit together

1. **Baseline** — turn on Security Hub standards + the ECS controls; enable Config rules for ECS; enable ECR Enhanced Scanning + GuardDuty (Layers 4/6).
2. **Continuous evaluation** — AWS Config conformance packs continuously evaluate the chosen framework's technical controls and flag drift; they record only Configuration Items as control evidence — not a general solution to capture, organize, and share evidence for the full control set, and no AM-equivalent report assembly (that stays with the customer — see the Layer-7b table). (Audit Manager, the prior evidence engine, is in maintenance mode — see the canonical dated note in the table above.)
3. **Audit time** — validate Security Hub against the compliance pack, remediate findings, download the attestation (AOC / package) from Artifact for the auditor — AWS's attestation of the AWS-managed layer (subservice evidence); the customer still undergoes its own assessment/examination.

> **Disclaimer (always include in customer-facing output):** "Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage." Config conformance packs / Security Hub frameworks *accelerate evidence*; they do **not** themselves constitute certification.

## Shared responsibility (Layer 7b)

| AWS manages | Customer manages |
|---|---|
| Service availability; pre-built ECS Config rules + Config conformance-pack templates, Security Hub ECS controls + standards; attestation packages in Artifact | Selecting the right framework; remediating findings; mapping evidence to the auditor's requirements; downloading + presenting attestations; the workload-level controls AWS attestations don't cover |

## Sources
- [AWS Config conformance packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html) · [AWS Config](https://aws.amazon.com/config/) · [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html) · [AWS Artifact](https://aws.amazon.com/artifact/) · [AWS Audit Manager — maintenance mode (availability change)](https://docs.aws.amazon.com/audit-manager/latest/userguide/audit-manager-availability-change.html)
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html)
