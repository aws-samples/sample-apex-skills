---
title: "eks-security"
description: "Day 1/Day 2 EKS security & compliance workflow. Guides hardening an Amazon EKS cluster and preparing it for a compliance audit through the discovery-driven 7-layer stack — OS/AMI hardening, identity & access, workload security, image supply chain, runtime security, audit logging, and compliance accelerators — with the compliance-regime scope view (HIPAA/PCI/FedRAMP/GDPR/SOC2/ISO), a non-negotiable security baseline, and a 30/60/90 hardening roadmap."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/steering/workflows/eks-security.md
format: md
---

:::info[Source]
This page is generated from [steering/workflows/eks-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/steering/workflows/eks-security.md). Edit the source, not this page.
:::


# EKS Security & Compliance Workflow

> **Part of:** [APEX EKS Hub](../eks)
> **Lifecycle:** Day 1 (greenfield hardening) / Day 2 (audit prep for an existing cluster)
> **Skill:** eks-security | os-ami-hardening.md, identity-and-access.md, compliance-regimes.md
> **Access Model:** advisory

This workflow guides a team through hardening an EKS cluster and preparing for a compliance audit. It produces an opinionated, layer-by-layer hardening recommendation and a 30/60/90 roadmap; it does not read or mutate a live cluster. All domain knowledge comes from the `eks-security` skill (the 7-layer stack, the compliance-regime scope view, the security baseline); this workflow supplies the engagement structure.

## How to Route Requests

| The user says… | Route to | Mode |
|---|---|---|
| "Harden my EKS cluster" / "EKS security baseline" / "is my cluster secure?" | Full 7-layer hardening | Day 1/2 |
| "HIPAA / PCI-DSS / FedRAMP / GDPR / SOC 2 on EKS" / "audit in N months" | Compliance-regime + audit-prep roadmap | Day 2 |
| "Bottlerocket vs AL2023 vs RHEL/Ubuntu" / "CIS-hardened AMI" | Layer 1 (OS/AMI) deep-dive | Day 1 |
| "Pod Identity vs IRSA" / "Access Entries vs aws-auth" | Layer 2 (identity & access) | Day 1/2 |
| "Pod Security Admission / Kyverno / NetworkPolicy / SGP" | Layer 3 (workload security) | Day 1/2 |
| "ECR scanning / image signing / Cosign / Notation" | Layer 4 (image supply chain) | Day 1/2 |
| "GuardDuty for EKS / Falco / runtime threats" | Layer 5 (runtime security) | Day 1/2 |
| "audit logging / control-plane logs / SIEM / retention" | Layer 6 (audit & forensics) | Day 2 |
| "Audit Manager / Config / Security Hub / Artifact" | Layer 7 (compliance accelerators) | Day 2 |

## Phases

### Phase 1 — Discovery (STOP gate — do not skip)
Ask the **required** questions before any recommendation (full list in the skill's `engagement-and-response.md`):
1. Compliance regime(s)? 2. Workload sensitivity? 3. OS/AMI strategy? 4. Audit timeline? 5. Cluster topology? 6. Team K8s/security skill? 7. Operational-overhead tolerance? 8. Current security tooling baseline?

> **STOP:** Do not proceed to a recommendation until the required-8 are answered. The first four (regime, OS mandate, audit timeline, ops tolerance) determine ~80% of the answer. Reflexively recommending "Bottlerocket" or "AL2023 + CIS" without them is the #1 mistake.

### Phase 2 — Compliance-regime position
State which programs apply and whether EKS is natively in scope vs alignment/framework only. **Always include the disclaimer** ("verify on the live AWS Services in Scope page"). Precision: EKS is HIPAA-*eligible* (BAA required), not "HIPAA-compliant"; FedRAMP High = GovCloud only.

### Phase 3 — Top-level stack recommendation
One paragraph naming the choice at each of the 7 layers, each one-sentence-justified against the discovery answers; surface the vendor-OS path and third-party CNAPP alternatives with the conditions that justify them.

### Phase 4 — Layer-by-layer guidance
Walk all 7 layers, citing the AWS doc/blog/workshop for each and giving the **shared-responsibility split** per layer (what AWS manages vs what the customer manages — critical for audit conversations). Use the matching skill reference for each layer.

### Phase 5 — 30/60/90 hardening roadmap
Baseline (non-disruptive: logging, GuardDuty, ECR scanning, Security Hub, kube-bench) → identity + workload (Access Entries, Pod Identity, PSA, Kyverno, NetworkPolicy) → OS + image + accelerators (Bottlerocket/CIS-AL2023, signing, Config conformance packs, Artifact). Greenfield deploys the full stack at creation.

### Phase 6 — Security baseline, gotchas, escalation
Include the non-negotiable baseline regardless of regime; surface 3-5 relevant gotchas (Auto Mode no custom AMI, PSP removed 1.25+, Pod Identity 5,000-association limit, HIPAA-needs-BAA, FedRAMP Moderate≠High, FIPS 140-3≠140-2, CIS AL2≠AL2023, App Mesh EOS, AL2 EOL); escalate per the skill's criteria when stakes warrant it.

## Quality Checklist (before delivering)

- [ ] Required-8 discovery questions answered before any recommendation.
- [ ] Compliance-status disclaimer included; EKS framed as HIPAA-*eligible* (not "compliant"); FedRAMP Moderate vs High not conflated.
- [ ] IRSA framed as a fully supported alternative (Pod Identity recommended for new) — **never** "legacy".
- [ ] Every recommendation cites an AWS-published source; no synthesized compliance claims.
- [ ] Non-negotiable security baseline included; 3-5 relevant gotchas surfaced; shared-responsibility split given per layer.
- [ ] Escalation flagged when first-time cert + mission-critical, XXL+, FedRAMP High, or any ungroundable claim.
