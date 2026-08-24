# Layer 7 — Compliance Accelerators

Tools that continuously **evaluate the hardened cluster's technical controls and flag drift** — narrowing, not eliminating, the audit-prep gap. They **record only Configuration Items as control evidence** — not a general solution to capture, organize, and share evidence for the full control set, and no AM-equivalent report assembly; assembling, organizing, and mapping the full evidence set remains the customer's job, for every regime.

| Service | Function | Reference |
|---|---|---|
| **AWS Config conformance packs** | Managed rule packs that continuously **evaluate technical controls and flag drift** (e.g. "Operational Best Practices for HIPAA Security"; "Operational Best Practices for PCI DSS 4.0 (Excluding global resource types)" / "...(Including global resource types)"; "Operational Best Practices for NIST 800-53 rev 5"; "Operational Best Practices for FedRAMP(Low)" / "...FedRAMP(Moderate)" — plus "...FedRAMP (High Part 1)" / "...FedRAMP (High Part 2)"; there is no bare "FedRAMP" pack). They are **not equivalent to Audit Manager Frameworks (which remain available in maintenance mode)**: they record only Configuration Items as control evidence — not a general solution to capture, organize, and share evidence for the full control set, and no AM-equivalent report assembly — this applies to **all** regimes (HIPAA/PCI included, not just SOC 2/GDPR), where the evidence layer is the customer's via Security Hub + partner/GRC tooling. No AWS-native pack exists for SOC 2 or GDPR. **Canonical dated status (referenced elsewhere): AWS Audit Manager, the prior evidence engine, is closed to new accounts / maintenance mode as of 2026-04-30 (existing setups continue).** | [AWS Config conformance packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html) |
| **AWS Config** | Resource-configuration compliance; rules evaluating EKS cluster settings (logging enabled, endpoint privacy, encryption). | [AWS Config](https://aws.amazon.com/config/) |
| **AWS Security Hub** | CSPM; aggregates GuardDuty + Inspector + Config findings; evaluates compliance-pack standards (CIS AWS Foundations, AWS FSBP, NIST SP 800-53, PCI-DSS). | [Security Hub](https://aws.amazon.com/security-hub/) |
| **AWS Artifact** | Self-service download of SOC 2, ISO 27001, PCI-DSS AOC, FedRAMP packages, and the AWS Data Processing Addendum (DPA) — the documents you hand an auditor; also where you accept agreements like the **HIPAA BAA** (there is **no "HIPAA AOC"** — no HIPAA certification exists for a CSP, so the HIPAA artifact is the signed BAA, per [AWS HIPAA compliance](https://aws.amazon.com/compliance/hipaa-compliance/)). | [AWS Artifact](https://aws.amazon.com/artifact/) |
| **AWS Compliance Programs / Services in Scope** | The authoritative, live source for which programs EKS is in scope for. | [Compliance Programs](https://aws.amazon.com/compliance/programs/) · [Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) |
| **kube-bench** | OSS CIS Kubernetes Benchmark scanner; run it to baseline current CIS posture and re-validate after hardening. | [kube-bench (Aqua)](https://github.com/aquasecurity/kube-bench) |

## How they fit together

1. **Baseline** — run `kube-bench` for current CIS posture; turn on Security Hub standards.
2. **Continuous evaluation** — AWS Config conformance packs continuously evaluate the chosen framework's technical controls and flag drift; they record only Configuration Items as control evidence — not a general solution to capture, organize, and share evidence for the full control set, and no AM-equivalent report assembly (that stays with the customer — see the Layer-7 table). (Audit Manager, the prior evidence engine, is in maintenance mode — see the canonical dated note in the table above.)
3. **Audit time** — validate Security Hub against the compliance pack, remediate findings, download the attestation (AOC / package) from Artifact for the auditor — AWS's attestation of the AWS-managed layer (subservice evidence); the customer still undergoes its own assessment/examination.

> **Disclaimer (always include in customer-facing output):** "Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage." Config conformance packs / Security Hub frameworks accelerate evidence; they do **not** themselves constitute certification.

## Shared responsibility (Layer 7)

| AWS manages | Customer manages |
|---|---|
| Service availability; pre-built framework definitions + compliance packs; attestation packages in Artifact | Selecting the right framework; remediating findings; mapping evidence to the auditor's requirements; downloading + presenting attestations; the workload-level controls AWS attestations don't cover |

## Sources
- [AWS Config conformance packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html) · [AWS Config](https://aws.amazon.com/config/) · [AWS Security Hub](https://aws.amazon.com/security-hub/) · [AWS Artifact](https://aws.amazon.com/artifact/) · [AWS Audit Manager — maintenance mode](https://aws.amazon.com/audit-manager/)
- [AWS Compliance Programs](https://aws.amazon.com/compliance/programs/) · [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [kube-bench](https://github.com/aquasecurity/kube-bench)
