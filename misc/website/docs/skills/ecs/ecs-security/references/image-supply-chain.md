---
title: "Layer 4 — Image Supply Chain Security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/image-supply-chain.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/image-supply-chain.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/image-supply-chain.md). Edit the source, not this page.
:::

# Layer 4 — Image Supply Chain Security

The end-state is a chain: **scan → sign → run only signed, scanned images**, all from a repository you control (ECR) rather than an unvetted public registry.

## ECR image scanning — Enhanced (Inspector) vs basic

ECR offers two scanning modes; know which is which (verified against current docs):

| Mode | Engine | Coverage | Status |
|---|---|---|---|
| **Enhanced scanning** | **Amazon Inspector** | OS packages **AND** programming-language packages (Python, Node.js, Java, Ruby, Go, …); **continuous re-scan** on new CVE disclosure; CVSS scoring; findings → Security Hub | **Recommended** for production. Reference: [ECR enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html) |
| **Basic scanning (AWS native)** | AWS-native CVE engine | OS packages, on push / on-demand | GA and the default for new registries; broad OS coverage |
| **Basic scanning (Clair)** | OSS Clair | OS packages | **Deprecated** — verified 2026-07-09: *"Clair support is deprecated, Clair will not be supported in new regions as they are added and will no longer be supported in all regions as of October 1, 2025"*; also unsupported in Regions added after **September 2024**. Do not recommend. Source: [ECS task and container security best practices — scan images](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-tasks-containers.html). |

For a regulated workload, enable **Enhanced scanning** on all production repositories (PCI Req 6/11, similar for other regimes) — the continuous re-scan is the key differentiator, since a clean image on push develops CVEs over time. Images with `HIGH`/`CRITICAL` findings should be rebuilt or deleted. Reference: [Scanning ECR images with Amazon Inspector](https://docs.aws.amazon.com/inspector/latest/user/scanning-ecr.html).

## Image signing — AWS Signer + Notation

ECR supports container image signing so you can verify **provenance and integrity** before running an image. ECR integrates with **AWS Signer** and offers two ways to sign (verified against current docs):
- **Managed signing (automatic, AWS-recommended)** — ECR signs on push using a configured AWS Signer signing profile; both image and signature are stored in your private repository.
- **Manual signing (client-side)** — use the **Notation CLI + AWS Signer plugin** (Notary Project / CNCF, an OCI standard) to sign before push; signatures are stored as OCI artifacts alongside the image in ECR. Choose this for signing outside the push workflow or fine-grained control.
- Verify locally, in CI, or at deploy time. Reference: [Sign images in Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing.html) · [Manual signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing-manual.html) · [Sign container images in Signer](https://docs.aws.amazon.com/signer/latest/developerguide/container-workflow.html).

> **ECS vs EKS signing-enforcement nuance (state this precisely).** On **EKS**, admission controllers (e.g. Kyverno `verifyImages`) can *block unsigned images at admission*. **ECS has no admission-controller equivalent** — enforce signature verification in the **CI/CD pipeline** (fail the deploy if verification fails) and/or a pre-deploy gate, since ECS itself won't refuse an unsigned image at task launch. Don't imply ECS has cluster-side admission enforcement.

## Immutable tags + CMK-encrypted repositories

- **Immutable tags** — configure ECR repositories with tag immutability so an attacker (or an accidental re-push) can't overwrite a known-good tag with a compromised image under the same name. Deploy by digest (`@sha256:…`) for the strongest guarantee.
- **CMK encryption at rest** — ECR encrypts images at rest with an AWS-managed KMS key by default; use a **customer-managed key (CMK)** for rotation/audit control under compliance regimes. Reference: [ECR encryption at rest](https://docs.aws.amazon.com/AmazonECR/latest/userguide/encryption-at-rest.html).

## Third-party scanners (alternatives or complements)

| Scanner | Strengths | Available via |
|---|---|---|
| **Snyk** | Developer-focused, strong language scanning | AWS Marketplace |
| **Aqua / Prisma Cloud / Wiz / Sysdig** | Full CNAPP / container-security platforms | AWS Marketplace |
| **Trivy** | OSS, fast, broad CVE coverage | Self-hosted CI/CD |

Position AWS-native (ECR Enhanced Scanning + Inspector + Security Hub) as the default; third-party CNAPP suits customers with an existing enterprise contract or multi-cloud posture. When a customer already runs a CNAPP, the conversation is coexistence-vs-displacement — escalate to Security guidance rather than reflexively recommending replacement.

## Shared responsibility (Layer 4)

| AWS manages | Customer manages |
|---|---|
| ECR registry durability; Inspector scan engine + CVE feed; Signer signing service; signature storage | Enabling Enhanced Scanning per repo; setting tag immutability + CMK; signing pipeline + keys; **pipeline-side signature verification** (no ECS admission control); base-image hygiene; remediating findings |

## Sources
- [ECR enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html) · [ECR image scanning overview](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) · [Inspector ECR integration](https://docs.aws.amazon.com/inspector/latest/user/ecr-integration.html)
- [Sign images in Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing.html) · [Manual signing (Notation CLI)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing-manual.html) · [Sign container images in Signer](https://docs.aws.amazon.com/signer/latest/developerguide/container-workflow.html) · [ECR encryption at rest](https://docs.aws.amazon.com/AmazonECR/latest/userguide/encryption-at-rest.html)
