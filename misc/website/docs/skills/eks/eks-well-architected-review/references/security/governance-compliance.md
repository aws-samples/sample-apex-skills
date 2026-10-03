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

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**6 questions** — Environment separation, CIS benchmarking, change management, audit logging, compliance scanning.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`.

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

**Remediation:** Run kube-bench as a Job: `kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-eks.yaml`. A pinned release tag in this URL keeps resolving — git tags do not expire — and that is the problem: it keeps applying the manifest that tag shipped, so the job goes on running the CIS EKS benchmark revision and the target list of the day it was pinned, and no 404 ever tells you it has stopped tracking new checks. Verified live 2026-09-12 with a plain HTTPS GET of each raw URL: `main`, `v0.16.0` (the latest release) and `v0.10.4` all return HTTP 200 and are byte-identical today, running `--targets node,policies,managedservices,controlplane --benchmark eks-1.5.0`; the 2021-era `v0.6.0` also returns HTTP 200, and its manifest runs the `node` target alone against `--benchmark eks-1.0`. So `main` is what tracks the current benchmark; pin a specific tag yourself only if you also own re-checking it. Review CIS Benchmark results regularly.

---

### sec-20: Do you manage configuration changes through version control with pull request reviews and approvals before applying to clusters?

**Detection:** ✋ ASK USER

> Assess the use of version control and change management processes for cluster configurations.

**Remediation:** Manage configuration changes through Git with PR reviews. Use ArgoCD or Flux to apply changes only after approval.

---

## Audit logging

### sec-26: Is Kubernetes audit logging enabled in the EKS control plane?

**Detection:** 🔬 AUTO-DETECTABLE

> Audit logs record all API server requests for security investigation and compliance. **Enabled is not
> monitored.** This reads `cluster.logging.clusterLogging` for an enabled `audit` type and nothing else:
> it does not check that a CloudWatch log group is receiving events, that a retention policy is set, or
> that any metric filter or alarm reads them. A pass means the control plane is emitting an audit trail,
> not that anyone would find out when something in it matters: turning the log types on is only the first
> half, and a metric filter plus an alarm over the audit stream is what turns a stored log into
> detection. Neither is checked here, on a pass or a fail.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.logging.clusterLogging"
# Check audit type is enabled
```

<!-- MAINTAINER NOTE — not report content, placed before **Remediation:** for the reason documented at
     lens-11 in workload-security.md: question_prose() in assets/render-report.py captures everything
     after "**Remediation:**" verbatim and html-escapes it, so a comment inside that span would reach
     the customer as literal text. This remediation gives the actual CLI because it is High severity
     and lower-severity questions in this same file (sec-19, sec-36) carry one. It flags that
     update-cluster-config is asynchronous the same way sec-38's KMS remediation in
     data-protection.md documents for its own async update, and it includes the retention-policy step
     because enabling `api`/`audit` logging is an open-ended CloudWatch Logs cost,
     not a one-time toggle. -->

**Remediation:** Enabling the log types is not the whole control — without a metric filter and an alarm,
the events sit in CloudWatch Logs and nobody finds out when one matters. Turn on logging first,
`audit` and `api` most importantly:

```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'
# Asynchronous, the same as sec-38's KMS update — poll until Successful before relying on it:
aws eks describe-update --name <CLUSTER> --region <REGION> --update-id <UPDATE_ID>
```

**Before you turn this on:** `api` and `audit` log every control-plane request, so on a busy cluster
this is a continuous, open-ended stream into CloudWatch Logs — ingestion and storage cost scale with API
server traffic, not with a one-time setting. Set a retention policy as part of enabling it, not as an
afterthought:

```bash
aws logs put-retention-policy --log-group-name /aws/eks/<CLUSTER>/cluster --retention-in-days 90 --region <REGION>
```

Then add a CloudWatch Logs metric filter on the `audit` log group for unauthorized calls (a filter
pattern like `{ ($.responseStatus.code = 401) || ($.responseStatus.code = 403) }` is the usual start)
and an alarm on the resulting metric — logging without an alarm answers this question but not the
threat it exists for.

---

## Compliance scanning

### sec-36: Do you regularly scan your EKS cluster against compliance frameworks (CIS Benchmark, kube-bench)?

**Detection:** ✋ ASK USER

> Compliance scanning identifies configuration drift.

**Remediation:** Run kube-bench as a Job: `kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-eks.yaml`. Review results regularly.

---

### sec-37: Do you regularly scan your EKS cluster configuration against compliance frameworks (CIS Kubernetes Benchmark, PCI-DSS, HIPAA, SOC 2) using automated tools like kube-bench, Prowler, or AWS Security Hub?

**Detection:** ✋ ASK USER

> Assess the implementation of automated compliance scanning to identify configuration drift and maintain adherence to security standards.

**Remediation:** Schedule regular compliance scans using kube-bench, Prowler, or AWS Security Hub. Integrate findings into your incident response workflow.

---
