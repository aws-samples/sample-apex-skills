# Engagement & Response Framework

How to run an ECS security/compliance conversation: the full discovery question set, the adoption-challenge archetypes, the response structure, and escalation criteria.

## Discovery — Required questions (the minimum for a defensible recommendation)

Do NOT proceed to a recommendation without these. The first four determine ~80% of the answer, and **launch type is first** because it moves the shared-responsibility line.

1. **Launch type(s)?** AWS Fargate / ECS on EC2 / ECS Managed Instances / ECS Anywhere (external) / mixed.
2. **Compliance regime(s)?** None / SOC 2 / HIPAA / PCI-DSS / FedRAMP Moderate / FedRAMP High / GDPR / ISO 27001 / NIST 800-53/171 / IL4-IL5 — rank primary/secondary if multiple.
3. **Workload sensitivity?** Public / internal-confidential / PII / PHI (HIPAA) / cardholder data (PCI) / federal / mixed.
4. **Audit timeline?** None (greenfield posture) / <3 mo (urgent) / 3-6 mo / 6-12 mo / continuous (e.g., FedRAMP ConMon).
5. **Network topology?** Public subnets + IGW / private subnets + NAT / fully private + VPC endpoints; single vs multi-account; multi-region; GovCloud.
6. **Secrets & config posture?** Plaintext env vars / Secrets Manager / SSM Parameter Store / hybrid; rotation requirement; VPC-endpoint access to the secret store.
7. **Team ECS/security skill?** Low / moderate / high / mixed.
8. **Current security tooling baseline?** None / AWS-native / third-party CNAPP / OSS / hybrid.

## Discovery — Recommended questions (sharpen the answer when depth allows)

Cross-account resource access (drives confused-deputy + `iam:PassRole` scoping) · CI/CD system that registers task definitions and passes roles · image build pipeline + registry (drives signing/scanning) · ingress pattern (ALB/NLB/public IP) · egress requirements (NAT vs VPC-endpoint-only) · data-at-rest CMK requirement · log retention requirement · SIEM in use · existing pentest findings · customer segment (XS–XXL+, drives escalation).

> **The #1 mistake:** prescribing controls without confirming the **launch type**. A Fargate answer (AWS owns the OS/kernel; per-task isolation; no IMDS-from-task concern) and an ECS-on-EC2 answer (customer owns AMI patching + IMDS lockdown; no task isolation) diverge at Layers 1, 3, 5, and 6. The right stack is a function of *(launch type × compliance regime × workload sensitivity × audit timeline × network topology × team skill × ops tolerance)*.

## The 5 adoption-challenge archetypes

Identify the customer's #1 concern early — it shapes every subsequent step:
1. **Role-trust firefight** — "ECS was unable to assume the role" blocking task launch → lead with the [identity-and-access](identity-and-access.md) trust-policy diagnosis, then least-privilege the role split.
2. **Compliance audit panic** — audit imminent, posture gap unclear → lead with the 30/60/90 non-disruptive baseline (CloudTrail + GuardDuty + ECR scanning + Security Hub ECS controls) and defer scope to the live Services-in-Scope page.
3. **Secrets sprawl** — credentials in plaintext env vars → lead with Secrets Manager/SSM injection + execution-role permission + VPC endpoint.
4. **Shared-responsibility confusion** — unclear what AWS vs customer secures across Fargate/EC2/MI → lead with the per-launch-type [shared-responsibility](shared-responsibility.md) split.
5. **Tooling sprawl** — many tools, no unified posture → lead with Security Hub aggregation + the ECS controls pack.

## Response framework (8 steps)

Skip a step only if the question is narrow enough that it doesn't apply.
1. **Acknowledgment + context summary** — restate launch type(s), regime(s), sensitivity, timeline, network topology, secrets posture, skill, baseline; name the #1 adoption challenge.
2. **Compliance-regime position** — which programs apply; **defer to the live [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) page** and [ECS compliance validation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html); call out workload-level ownership. **Always add the live-page disclaimer.**
3. **Top-level stack recommendation** — one paragraph naming the choice at each of the 7 layers, each justified against the discovery answers; note the launch-type substitutions (EC2 adds OS + IMDS; MI loses GuardDuty Runtime Monitoring).
4. **Layer-by-layer detail** — walk the 7 layers; cite the specific AWS doc for each; give the **shared-responsibility split** per layer (critical for audit conversations).
5. **30/60/90 hardening roadmap** — baseline (non-disruptive) → identity + secrets → workload + network + image; greenfield deploys the full stack at creation.
6. **Security baseline (non-negotiable)** — include the full baseline from SKILL.md regardless of regime.
7. **Known gotchas (surface 3-5 relevant ones)** — task role vs execution role confusion; the "unable to assume the role" trust error; the trailing-colon secret-ARN syntax; env-var secrets not auto-rotating; GuardDuty Runtime Monitoring excludes Managed Instances; containers-are-not-a-boundary on EC2; HIPAA-eligible not compliant; Fargate FIPS = GovCloud only; read-only rootfs breaks write-expecting apps.
8. **Cite sources** — every recommendation cites an AWS-published reference. If you can't ground a claim, **say so and recommend escalation — do not synthesize.** Customers validate every claim against an auditor.

## Escalation criteria

Escalate (SpecReq / Specialist / Security review) when any holds:
- First-time certification on a **mission-critical regulated workload** (highest stakes).
- **XXL+ segment** (all security/compliance recommendations require human review).
- **FedRAMP High / GovCloud** → federal partner engagement (also the boundary for Fargate FIPS).
- **IL4 / IL5** → GovCloud + DoD partner.
- **ECS Anywhere inside a compliance boundary** → the customer owns the entire on-prem host, OS, and network; shared-responsibility boundary mapping required.
- **Multi-tenant SaaS** with cross-tenant PHI / cardholder / federal isolation, especially on **shared EC2 container instances** (no task isolation) → recommend Fargate or account-per-tenant.
- **Customer vs auditor disagreement** on AWS-managed-control acceptability → joint review with the auditor.
- **Written legal commitment** beyond Artifact (custom DPA, FedRAMP ConMon SLA, sovereignty).
- **Cannot ground the response** → do not synthesize; escalate.

## Sources
- [ECS Best Practices: Security](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security.html) · [ECS security documentation set](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security.html)
- [AWS Services in Scope](https://aws.amazon.com/compliance/services-in-scope/) · [Compliance validation for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-compliance.html)
