---
name: eks-security
description: Day 1/Day 2 EKS security workflow. Runs the eks-security skill's three read-only reviews of a live cluster (CVE and advisory review, security event response, security posture check, each with the verdict exposed / not exposed / unknown) and guides hardening and compliance-audit prep through the discovery-driven 7-layer stack (OS/AMI, identity and access, workload security, image supply chain, runtime security, audit logging, compliance accelerators), the compliance-regime scope view (HIPAA/PCI/FedRAMP/GDPR/SOC2/ISO), the security baseline and a 30/60/90 hardening roadmap.
---

# EKS Security Workflow

> **Lifecycle:** Day 1 (greenfield hardening) / Day 2 (CVE review, event response, posture check, audit prep for an existing cluster)
> **Skill:** eks-security | cve-advisory-review.md, security-event-response.md, posture-check.md, os-ami-hardening.md, identity-and-access.md, compliance-regimes.md
> **Access Model:** read-only (the three reviews) / advisory (hardening and compliance)

This workflow covers two kinds of work. The three reviews read a live cluster with read-only AWS and Kubernetes calls (the access the skill's `read-only-access.md` lists), compare by fixed rules, and print every change as a command or manifest for the team to review and run; they never apply, patch, scale, delete, cordon, exec into a pod or read Secret data. The hardening and compliance work produces an opinionated layer-by-layer recommendation and a 30/60/90 roadmap. All domain knowledge comes from the `eks-security` skill; this workflow supplies the engagement structure.

## How to Route Requests

| The user says… | Route to | Mode |
|---|---|---|
| "Am I exposed to CVE-..." / "check this security bulletin (or GHSA) against my cluster" / "CVE review for EKS" / "check what is current since a date" | C1 CVE and advisory review | Day 2 |
| "We have a compromised image / package" / "a credential leaked" / "suspicious pod" / "respond to CVE-... on our cluster" | C2 Security event response | Day 2 |
| "Check my EKS security posture" / "are we following security best practice" / "would my cluster contain a compromised pod" | C3 Posture check | Day 2 |
| "Harden my EKS cluster" / "EKS security baseline" | Full 7-layer hardening | Day 1/2 |
| "HIPAA / PCI-DSS / FedRAMP / GDPR / SOC 2 on EKS" / "audit in N months" | Compliance-regime + audit-prep roadmap | Day 2 |
| "Bottlerocket vs AL2023 vs RHEL/Ubuntu" / "CIS-hardened AMI" | Layer 1 (OS/AMI) deep-dive | Day 1 |
| "Pod Identity vs IRSA" / "Access Entries vs aws-auth" | Layer 2 (identity & access) | Day 1/2 |
| "Pod Security Admission / Kyverno / NetworkPolicy / SGP" | Layer 3 (workload security) | Day 1/2 |
| "ECR scanning / image signing / Cosign / Notation" | Layer 4 (image supply chain) | Day 1/2 |
| "GuardDuty for EKS / Falco / runtime threats" | Layer 5 (runtime security) | Day 1/2 |
| "audit logging / control-plane logs / SIEM / retention" | Layer 6 (audit logging) | Day 2 |
| "Audit Manager / Config / Security Hub / Artifact" | Layer 7 (compliance accelerators) | Day 2 |

A component that is only behind the latest release, with no advisory, is not a security finding: upgrade readiness against a target version goes to `eks-upgrade-check`, version currency with no target version to `eks-operation-review`.

## Review phases (C1, C2, C3)

### Phase R1: Scope and access
Confirm the cluster and Region and, for C1, the advisory (CVE id, bulletin URL, GHSA id, or a sweep date; default the last 30 days). Check read access first (the skill's preflight); a refused read becomes `unknown` for the parts it covers, never clean.

### Phase R2: Read and compare
- **C1:** read the cluster once, get the advisory as a record (structured feeds as published; a bulletin extracted with every version line quoted from the page and checked), and compare by the skill's verdict rules.
- **C2:** scope the event (workloads, images by digest, packages, identities), take a quick record (seconds, read through the API server), propose pod-scoped containment at once, propose snapshots after isolation, then the remediation on the emergency path, verification and the report.
- **C3:** run the posture checks (security pillar plus the containment checks) and score them.

### Phase R3: Report
Open with the coverage line; below 50% coverage the result is "incomplete" with no overall verdict. Give the three-state verdict per component or check, with its source and read time. On Auto Mode, report AWS-managed components with the nodes still pending replacement, not a patch. Print every fix for the team to review; run none.

## Hardening phases

### Phase 1: Discovery (STOP gate, do not skip)
Ask the **required** questions before any recommendation (full list in the skill's `engagement-and-response.md`):
1. Compliance regime(s)? 2. Workload sensitivity? 3. OS/AMI strategy? 4. Audit timeline? 5. Cluster topology? 6. Team K8s/security skill? 7. Operational-overhead tolerance? 8. Current security tooling baseline?

> **STOP:** Do not proceed to a recommendation until the required-8 are answered. The first four (regime, OS mandate, audit timeline, ops tolerance) determine ~80% of the answer. Reflexively recommending "Bottlerocket" or "AL2023 + CIS" without them is the #1 mistake. On an existing cluster, a C3 posture check answers much of question 8 from live data.

### Phase 2: Compliance-regime position
State which programs apply and whether EKS is natively in scope vs alignment/framework only. **Always include the disclaimer** ("verify on the live AWS Services in Scope page"). Precision: EKS is HIPAA-*eligible* (BAA required), not "HIPAA-compliant"; FedRAMP High = GovCloud only.

### Phase 3: Top-level stack recommendation
One paragraph naming the choice at each of the 7 layers, each one-sentence-justified against the discovery answers; surface the vendor-OS path and third-party CNAPP alternatives with the conditions that justify them.

### Phase 4: Layer-by-layer guidance
Walk all 7 layers, citing the AWS doc/blog/workshop for each and giving the **shared-responsibility split** per layer (what AWS manages vs what the customer manages, critical for audit conversations). Use the matching skill reference for each layer.

### Phase 5: 30/60/90 hardening roadmap
Baseline (non-disruptive: logging, GuardDuty, ECR scanning, Security Hub, a C3 posture check and kube-bench, the C1 sweep) → identity + workload (Access Entries, Pod Identity, PSA, Kyverno, NetworkPolicy) → OS + image + accelerators (Bottlerocket/CIS-AL2023, signing, Config conformance packs, Artifact). Greenfield deploys the full stack at creation.

### Phase 6: Security baseline, gotchas, escalation
Include the non-negotiable baseline regardless of regime; surface 3-5 relevant gotchas (Auto Mode no custom AMI, PSP removed 1.25+, Pod Identity 5,000-association limit, HIPAA-needs-BAA, FedRAMP Moderate≠High, FIPS 140-3≠140-2, CIS AL2≠AL2023, App Mesh EOS, AL2 EOL); escalate per the skill's criteria when stakes warrant it.

## Quality Checklist (before delivering)

- [ ] Reviews: coverage line present; no "not exposed" for a component that was not read; unknowns carry their reason and action; every fix printed, none run.
- [ ] Reviews: every version fact quotes its source URL and read time; context notes never lower a verdict or priority.
- [ ] Required-8 discovery questions answered before any hardening recommendation.
- [ ] Compliance-status disclaimer included; EKS framed as HIPAA-*eligible* (not "compliant"); FedRAMP Moderate vs High not conflated.
- [ ] IRSA framed as a fully supported alternative (Pod Identity recommended for new), **never** "legacy".
- [ ] Every recommendation cites an AWS-published source; no synthesized compliance claims.
- [ ] Non-negotiable security baseline included; 3-5 relevant gotchas surfaced; shared-responsibility split given per layer.
- [ ] Escalation flagged when first-time cert + mission-critical, FedRAMP High, or any ungroundable claim.
