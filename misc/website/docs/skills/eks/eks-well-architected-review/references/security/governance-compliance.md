---
title: "🔒 Security — Governance, Audit & Compliance"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/governance-compliance.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/governance-compliance.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/governance-compliance.md). Edit the source, not this page.
:::

# 🔒 Security — Governance, Audit & Compliance

**6 questions** — Environment separation, CIS benchmarking, change management, audit logging, compliance scanning.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `not-applicable`.

---

## Environment separation

### sec-13: Do you use separate EKS clusters for production and non-production environments, ideally in different AWS accounts?

**Detection:** ✋ ASK USER

> Evaluate environment separation strategies to minimize risk and improve security posture.

**Remediation:** Use separate EKS clusters for production and non-production, ideally in different AWS accounts. Use AWS Organizations for account isolation.

---

## Change management

### sec-19: Do you leverage tools like kube-bench to automatically check whether EKS is deployed securely by running checks documented in the CIS Kubernetes Benchmark?

**Detection:** ✋ ASK USER

> Evaluate the use of automated security benchmarking tools for cluster configuration validation.

**Remediation:** Run kube-bench as a CronJob: `kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-eks.yaml`. Review CIS Benchmark results regularly.

---

### sec-20: Do you manage configuration changes through version control with pull request reviews and approvals before applying to clusters?

**Detection:** ✋ ASK USER

> Assess the use of version control and change management processes for cluster configurations.

**Remediation:** Manage configuration changes through Git with PR reviews. Use ArgoCD or Flux to apply changes only after approval.

---

## Audit logging

### sec-26: Is Kubernetes audit logging enabled in the EKS control plane?

**Detection:** 🔬 AUTO-DETECTABLE

> Audit logs record all API server requests for security investigation and compliance.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.logging.clusterLogging"
# Check audit type is enabled
```

**Remediation:** Enable EKS audit logging and set up CloudWatch metric filters for unauthorized API calls.

---

## Compliance scanning

### sec-36: Do you regularly scan your EKS cluster against compliance frameworks (CIS Benchmark, kube-bench)?

**Detection:** ✋ ASK USER

> Compliance scanning identifies configuration drift.

**Remediation:** Run kube-bench as a CronJob: `kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-eks.yaml`. Review results regularly.

---

### sec-37: Do you regularly scan your EKS cluster configuration against compliance frameworks (CIS Kubernetes Benchmark, PCI-DSS, HIPAA, SOC 2) using automated tools like kube-bench, Prowler, or AWS Security Hub?

**Detection:** ✋ ASK USER

> Assess the implementation of automated compliance scanning to identify configuration drift and maintain adherence to security standards.

**Remediation:** Schedule regular compliance scans using kube-bench, Prowler, or AWS Security Hub. Integrate findings into your incident response workflow.
