---
title: "🔒 Security — Workload, Pod & Supply Chain Security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/workload-security.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/workload-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/workload-security.md). Edit the source, not this page.
:::

# 🔒 Security — Workload, Pod & Supply Chain Security

**16 questions** — Admission control, Pod Security Standards, security contexts, image pull policy & signing, runtime monitoring, pod security baselines, IMDSv2.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `not-applicable`.

---

## Admission control & Pod Security Standards

### sec-10: Are admission webhooks (validating/mutating) deployed to enforce Pod security policies?

**Detection:** 🔬 AUTO-DETECTABLE

> Admission controllers enforce security policies at deployment time before Pods are created.

**Commands:**
```bash
kubectl get validatingwebhookconfigurations -o json
kubectl get mutatingwebhookconfigurations -o json
```

**Remediation:** Deploy OPA Gatekeeper or Kyverno to enforce Pod security policies. Start with a policy blocking privileged containers.

---

### sec-11: Are Pod Security Standards labels applied to namespaces to enforce security baselines?

**Detection:** 🔬 AUTO-DETECTABLE

> Pod Security Standards (baseline/restricted) prevent privileged containers and host access.

**Commands:**
```bash
kubectl get namespaces -o json
# Check labels starting with pod-security.kubernetes.io/
```

**Remediation:** Apply Pod Security Standards: `kubectl label namespace <ns> pod-security.kubernetes.io/enforce=baseline`.

---

### sec-16: Do you leverage Pod Security Standards, Pod Security Policies, or admission controllers to restrict Pod actions and enforce security controls?

**Detection:** ✋ ASK USER

> Assess the implementation of Pod-level security policies and admission control.

**Remediation:** Deploy admission controllers (Kyverno/Gatekeeper) to enforce Pod Security Standards and prevent privileged containers at deploy time.

---

### adm-1: Are admission controller policies (Gatekeeper/Kyverno) deployed with adequate coverage?

**Detection:** 🔬 AUTO-DETECTABLE

> Admission policies enforce security and compliance at deploy time.

**Commands:**
```bash
kubectl get constrainttemplates -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
```

**Remediation:** Deploy Gatekeeper or Kyverno with at least 5-10 policies covering common security baselines (privileged containers, host networking, resource limits).

---

### adm-2: Do admission policies block privileged container execution?

**Detection:** 🔬 AUTO-DETECTABLE

> Blocking privileged containers prevents container escape attacks.

**Commands:**
```bash
kubectl get constraints -A -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
# Look for privileged container blocking
```

**Remediation:** Add a policy to block privileged containers: Gatekeeper `K8sPSPPrivilegedContainer` constraint or Kyverno `disallow-privileged-containers` policy.

---

### adm-3: Are admission policies set to enforce mode (not audit-only)?

**Detection:** 🔬 AUTO-DETECTABLE

> Audit-only policies detect but do not prevent violations.

**Commands:**
```bash
kubectl get constraints -A -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
# Check enforcementAction / validationFailureAction
```

**Remediation:** Switch admission policies from audit/dryrun to enforce mode. Gatekeeper: set `enforcementAction: deny`. Kyverno: set `validationFailureAction: enforce`.

---

## Container & pod hardening

### sec-12: Do containers use explicit image pull policies (Always or IfNotPresent)?

**Detection:** 🔬 AUTO-DETECTABLE

> Explicit pull policies ensure containers use verified, up-to-date images.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].imagePullPolicy
```

**Remediation:** Set `imagePullPolicy: Always` or `IfNotPresent` on all containers. Avoid using `latest` tag without `Always` pull policy to ensure image integrity.

---

### sec-15: Do containers have security contexts configured (runAsNonRoot, readOnlyRootFilesystem, or allowPrivilegeEscalation=false)?

**Detection:** 🔬 AUTO-DETECTABLE

> Security contexts reduce the blast radius of a compromised container.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].securityContext
```

**Remediation:** Add `securityContext` to all containers: set `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, and `allowPrivilegeEscalation: false`.

---

### podsec-1: Do containers run as non-root users?

**Detection:** 🔬 AUTO-DETECTABLE

> Root containers can escape to the host and compromise the node.

**Commands:**
```bash
kubectl get pods -A -o json
# Check securityContext.runAsNonRoot == true
```

**Remediation:** Set `securityContext.runAsNonRoot: true` and `runAsUser: 1000` on all containers. Use Pod Security Standards `restricted` profile on namespaces.

---

### podsec-2: Are containers running without privileged mode?

**Detection:** 🔬 AUTO-DETECTABLE

> Privileged containers have full host access and bypass all security boundaries.

**Commands:**
```bash
kubectl get pods -A -o json
# Check securityContext.privileged != true
```

**Remediation:** Remove `securityContext.privileged: true` from all containers. Use specific capabilities instead of privileged mode for required host access.

---

### podsec-3: Are pods free of host path volume mounts?

**Detection:** 🔬 AUTO-DETECTABLE

> Host path mounts expose the node filesystem to containers.

**Commands:**
```bash
kubectl get pods -A -o json
# Check volumes[].hostPath is not used
```

**Remediation:** Replace hostPath volume mounts with PersistentVolumeClaims, ConfigMaps, or Secrets. hostPath mounts expose the node filesystem to containers.

---

### podsec-4: Are containers free of dangerous Linux capabilities (NET_ADMIN, SYS_ADMIN, ALL)?

**Detection:** 🔬 AUTO-DETECTABLE

> Dangerous capabilities enable container escape and network manipulation.

**Commands:**
```bash
kubectl get pods -A -o json
# Check capabilities.add does not include NET_ADMIN, SYS_ADMIN, ALL
```

**Remediation:** Remove dangerous capabilities (NET_ADMIN, SYS_ADMIN, ALL) from container security contexts. Add back only the specific capabilities needed.

---

### podsec-5: Do containers drop ALL Linux capabilities?

**Detection:** 🔬 AUTO-DETECTABLE

> Dropping ALL capabilities and adding back only needed ones is a security best practice.

**Commands:**
```bash
kubectl get pods -A -o json
# Check capabilities.drop includes "ALL"
```

**Remediation:** Add `securityContext.capabilities.drop: ["ALL"]` to all containers, then add back only required capabilities with `capabilities.add`.

---

### lens-11: Do EC2 worker nodes enforce IMDSv2 (HttpTokens=required)?

**Detection:** 🔬 AUTO-DETECTABLE

> IMDSv2 prevents SSRF attacks from stealing instance credentials.

**Commands:**
```bash
aws ec2 describe-instances --filters "Name=tag:kubernetes.io/cluster/<CLUSTER>,Values=owned,shared" --region <REGION>
# Check MetadataOptions.HttpTokens == required
```

**Remediation:** Enforce IMDSv2 on all EC2 instances: update launch templates with `MetadataOptions.HttpTokens=required` to prevent SSRF credential theft.

---

## Supply chain & runtime security

### sec-32: Do you implement container image signing and verification (Sigstore/Cosign, AWS Signer, Notary)?

**Detection:** ✋ ASK USER

> Image signing ensures only trusted images are deployed.

**Remediation:** Deploy Cosign webhook for image verification: `helm install cosign-webhook sigstore/cosign-webhook`. Configure policies to reject unsigned images.

---

### sec-33: Do you implement runtime security monitoring (Falco, GuardDuty for EKS, Sysdig)?

**Detection:** ✋ ASK USER

> Runtime monitoring detects suspicious container behavior.

**Remediation:** Deploy GuardDuty for EKS: enable in the GuardDuty console under EKS Protection. Alternatively, deploy Falco: `helm install falco falcosecurity/falco`.
