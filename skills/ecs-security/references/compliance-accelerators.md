# Layer 7b — Compliance Accelerators

Tools that turn a hardened ECS estate into **continuous, auditor-ready evidence** — so an audit is a report-pull, not a fire drill.

| Service | Function for ECS | Reference |
|---|---|---|
| **AWS Config** | Resource-configuration compliance; rules that evaluate ECS task definitions/services — e.g. **`ecs-containers-nonprivileged`** (no privileged containers), read-only-rootfs, no plaintext secrets, `awsvpc` mode, no host networking. Flags drift continuously. | [AWS Config](https://aws.amazon.com/config/) |
| **AWS Security Hub** | CSPM; aggregates GuardDuty + Inspector + Config findings; runs the **ECS controls pack** (ECS.4, ECS.5, plaintext-secret and host-mode checks) and standards (AWS FSBP, CIS, NIST 800-53, PCI-DSS). | [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html) |
| **AWS Audit Manager** | Continuous evidence collection mapped to framework controls (HIPAA, PCI-DSS, FedRAMP, NIST 800-53) — makes audit prep continuous rather than point-in-time. | [AWS Audit Manager](https://aws.amazon.com/audit-manager/) |
| **AWS Artifact** | Self-service download of SOC 2, ISO 27001, PCI-DSS AOC, FedRAMP packages, HIPAA AOC, and the AWS Data Processing Addendum (DPA) — the documents you hand an auditor. | [AWS Artifact](https://aws.amazon.com/artifact/) |
| **AWS Services in Scope / Compliance Programs** | The authoritative, **live** source for which programs ECS and Fargate are in scope for. | [Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [ECS compliance validation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html) |

## How they fit together

1. **Baseline** — turn on Security Hub standards + the ECS controls; enable Config rules for ECS; enable ECR Enhanced Scanning + GuardDuty (Layers 4/6).
2. **Continuous evidence** — Audit Manager collects evidence against the chosen framework; Config flags drift; Security Hub scores posture.
3. **Audit time** — validate Security Hub against the compliance pack, remediate findings, download the attestation (AOC / package) from Artifact for the auditor.

> **Disclaimer (always include in customer-facing output):** "Compliance status changes over time — verify on the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page before quoting program coverage." Audit Manager / Security Hub frameworks *accelerate evidence*; they do **not** themselves constitute certification.

## Shared responsibility (Layer 7b)

| AWS manages | Customer manages |
|---|---|
| Service availability; pre-built ECS Config rules, Security Hub ECS controls, and Audit Manager framework definitions; attestation packages in Artifact | Selecting the right framework; remediating findings; mapping evidence to the auditor's requirements; downloading + presenting attestations; the workload-level controls AWS attestations don't cover |

## Sources
- [AWS Config](https://aws.amazon.com/config/) · [Security Hub ECS controls](https://docs.aws.amazon.com/securityhub/latest/userguide/ecs-controls.html) · [AWS Audit Manager](https://aws.amazon.com/audit-manager/) · [AWS Artifact](https://aws.amazon.com/artifact/)
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html)
