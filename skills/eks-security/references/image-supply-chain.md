# Layer 4: Image Supply Chain Security

The end-state is a complete chain: **scan → sign → verify-at-admission.** Each stage is independently valuable; together they ensure only scanned, signed images run.

## ECR Enhanced Scanning (powered by Amazon Inspector)

- CVE detection across **OS packages AND programming-language packages** (Python, Node.js, Java, Ruby, Go, …).
- CVSS severity scoring; **continuous re-scan** on new CVE disclosure.
- Findings flow to **AWS Security Hub** for unified posture.
- References: [Amazon ECR features](https://aws.amazon.com/ecr/features/) · [Amazon Inspector](https://aws.amazon.com/inspector/).
- To check running images and components against a specific CVE or advisory, use [cve-advisory-review.md](cve-advisory-review.md); for a compromised image or package, [security-event-response.md](security-event-response.md).

## ECR image signing

ECR stores image signatures as OCI artifacts via:
- **Cosign** (Sigstore project, CNCF): keyless or keyed signatures.
- **Notation** (CNCF, OCI standard): ECR is Notation-compatible.

## Image admission control: Kyverno image verification

Kyverno's image verification rule blocks unsigned or high-severity images **at admission time**. Combined with ECR Enhanced Scanning + image signing (Cosign or Notation, above), this closes the loop: an image that isn't scanned-clean and signed never schedules. (See Layer 3, this is policy-engine sub-rule 3c.) Write the rule as an `ImageValidatingPolicy` (`policies.kyverno.io/v1`, stable since Kyverno v1.18). The older `verifyImages` rule belongs to the legacy `ClusterPolicy` (`kyverno.io/v1`), which is deprecated in v1.19 with removal planned for v1.20 ([Kyverno v1.19 policy types](https://release-1-19-0.kyverno.io/docs/policy-types/overview/)).

As of Kyverno v1.19.2, Kyverno's built-in image verification (`verifyImages` and `ImageValidatingPolicy`) cannot verify AWS Signer signatures. For images signed with AWS Signer, use the [kyverno-notation-aws](https://github.com/nirmata/kyverno-notation-aws) extension service, or OPA Gatekeeper with Ratify and the AWS Signer plugin ([EKS user guide](https://docs.aws.amazon.com/eks/latest/userguide/image-verification.html)). The kyverno-notation-aws sample policy is a `ClusterPolicy` ([kyverno-policy.yaml](https://github.com/nirmata/kyverno-notation-aws/blob/58b210b446590eb079b1c84245cacd4a434e8a36/configs/samples/kyverno-policy.yaml)), and the Kyverno v1.20 release candidate stops enforcing legacy policies after the upgrade ([v1.20.0-rc.1 notes](https://github.com/kyverno/kyverno/releases/tag/v1.20.0-rc.1)), so that route needs Kyverno 1.19.x; on a newer Kyverno, use Gatekeeper with Ratify.

## Third-party scanners (alternatives or complements to ECR Enhanced Scanning)

| Scanner | Strengths | Available via |
|---|---|---|
| **Snyk** | Developer-focused, strong language scanning | AWS Marketplace |
| **Aqua** | Full container security platform | AWS Marketplace |
| **Wiz** | CNAPP, agentless | AWS Marketplace |
| **Prisma Cloud** (Palo Alto) | Comprehensive CSPM + workload protection | AWS Marketplace |
| **Trivy** | Open-source, fast, broad CVE coverage | Self-hosted (CI/CD) |

Position AWS-native (ECR Enhanced Scanning + Inspector + Security Hub) as the default; third-party CNAPP suits customers with an existing enterprise contract or multi-cloud posture. When a customer already runs a CNAPP, the conversation is coexistence-vs-displacement, escalate to Security guidance rather than reflexively recommending replacement.

## Hardening the images themselves

- Prefer **distroless / minimal base images** to shrink the CVE surface.
- Generate an **SBOM** and enforce build provenance where the regime requires it.
- DLC and ML images carry large dependency trees (PyTorch, CUDA), the CVE surface is far larger than typical microservices; scan on push **and** on a schedule for base-image drift.
- Keep **language runtimes** in images (Node.js, PHP and similar) on a release their project still patches. Inspector reports a runtime installed as an OS package; a runtime built from a release tarball, as the official `node` and `php` images do, may not show up, so check the runtime's own release and security pages (for example [Node.js releases](https://nodejs.org/en/about/previous-releases), [PHP supported versions](https://www.php.net/supported-versions.php)). Inspector's ECR coverage: [supported operating systems and programming languages](https://docs.aws.amazon.com/inspector/latest/user/supported.html).

## Shared responsibility (Layer 4)

| AWS manages | Customer manages |
|---|---|
| ECR registry; Inspector scanning engine + CVE feed; signature storage | Enabling Enhanced Scanning per repo; signing keys + signing pipeline; admission policies (`verifyImages`); base-image hygiene; SBOM/provenance |

## Sources
- [Amazon ECR features](https://aws.amazon.com/ecr/features/) · [Amazon Inspector](https://aws.amazon.com/inspector/)
- [Sigstore Cosign](https://docs.sigstore.dev/) · [Notation (CNCF Notary Project)](https://notaryproject.dev/) · [Kyverno ImageValidatingPolicy](https://release-1-19-0.kyverno.io/docs/policy-types/image-validating-policy/) · [Kyverno verifyImages (legacy)](https://release-1-19-0.kyverno.io/docs/policy-types/cluster-policy/verify-images/)
- [AWS Marketplace for Containers](https://aws.amazon.com/marketplace/) (Snyk, Aqua, Wiz, Prisma Cloud, Sysdig, …)
