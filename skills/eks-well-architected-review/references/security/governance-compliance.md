# 🔒 Security — Governance, Audit & Compliance

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**6 questions** — Environment separation, CIS benchmarking, change management, audit logging, compliance scanning.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access.md).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`. ASK USER responses: "Yes, fully" → `all`, "Mostly" → `most`, "Partially" → `some`, "No" → `none`, "Doesn't apply" → `na`.

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

**Remediation:** Run kube-bench as a CronJob: `kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-eks.yaml`. A pinned release tag in this URL eventually 404s as kube-bench cuts new releases (verified live, 2026-09-11: the latest tag is `v0.16.0`, well past the `v0.10.4` this used to point at) — `main` always resolves; pin a specific tag yourself only if you also own re-checking it. Review CIS Benchmark results regularly.

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

<!-- MAINTAINER NOTE — not report content, placed before **Remediation:** for the reason documented at
     lens-11 in workload-security.md: question_prose() in assets/render-report.py captures everything
     after "**Remediation:**" verbatim and html-escapes it, so a comment inside that span would reach
     the customer as literal text. This remediation used to be one sentence with no command, High
     severity, while lower-severity questions in this same file (sec-19, sec-36) already had one. It
     now gives the actual CLI, flags that update-cluster-config is asynchronous the same way sec-38's
     KMS remediation in data-protection.md already documents for its own async update, and adds the
     retention-policy step because enabling `api`/`audit` logging is an open-ended CloudWatch Logs cost,
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

**Remediation:** Run kube-bench as a CronJob: `kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-eks.yaml`. Review results regularly.

---

### sec-37: Do you regularly scan your EKS cluster configuration against compliance frameworks (CIS Kubernetes Benchmark, PCI-DSS, HIPAA, SOC 2) using automated tools like kube-bench, Prowler, or AWS Security Hub?

**Detection:** ✋ ASK USER

> Assess the implementation of automated compliance scanning to identify configuration drift and maintain adherence to security standards.

**Remediation:** Schedule regular compliance scans using kube-bench, Prowler, or AWS Security Hub. Integrate findings into your incident response workflow.
