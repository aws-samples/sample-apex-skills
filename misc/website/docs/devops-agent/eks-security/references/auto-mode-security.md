---
title: "Securing an EKS Auto Mode Cluster"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/auto-mode-security.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-security/references/auto-mode-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/auto-mode-security.md). Edit the source, not this page.
:::

# Securing an EKS Auto Mode Cluster

EKS Auto Mode shifts a large slice of data-plane security responsibility to AWS — but it is not "security handled." The 7-layer stack still applies; what changes is *who owns each control*. This reference splits the responsibilities precisely, then lists the cases where Auto Mode is the wrong answer for security reasons.

> **Facts verified 2026-07-17 against** [EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/automode.html), [Security considerations for EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html), [Auto Mode managed instances](https://docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html), and [Alternate CNI plugins](https://docs.aws.amazon.com/eks/latest/userguide/alternate-cni-plugins.html). Auto Mode capabilities change frequently — re-check the [Auto Mode release notes](https://docs.aws.amazon.com/eks/latest/userguide/auto-change.html) before repeating any "not supported" claim below.

## What Auto Mode handles automatically

- **Node lifecycle and patching** — AWS creates, patches, and terminates the EC2 managed instances; nodes have a **maximum lifetime of 21 days** (reducible) and are then replaced, preventing configuration drift. AWS generally releases a new Auto Mode AMI **each week** with CVE and security fixes.
- **Node OS hardening** — nodes run AWS-selected Bottlerocket-variant AMIs treated as immutable: locked-down software, **SELinux enforcing**, **read-only root filesystem**. Direct access is blocked — **no SSH, no SSM**; management goes through the EKS and Kubernetes APIs only.
- **IMDS posture** — **IMDSv2 enforced with hop limit 1** by default.
- **Managed core components** — pod networking (VPC CNI function), the **NetworkPolicy enforcement engine**, load-balancing controller, EBS CSI, cluster DNS, Karpenter-based autoscaling, and GPU drivers run as service-owned components AWS configures and patches (not customer-managed add-ons).
- **Pod Identity agent** — pre-installed; you do not deploy the EKS Pod Identity Agent add-on on Auto Mode clusters.
- **Ephemeral node storage** — instance storage is encrypted; Auto Mode manages the volumes it attaches at node creation (root/data).

## What the customer still owns

Everything above the node, plus all account-level enablement:

- **Pod Security Admission** — PSA `restricted` on production namespaces, plus Kyverno/OPA admission policy. AWS explicitly leaves pod security standards to you.
- **NetworkPolicy authoring** — Auto Mode ships the enforcement engine, but *you* write the policies; default-deny on production namespaces is still your job.
- **GuardDuty enablement** — EKS Protection and Runtime Monitoring are not enabled by Auto Mode; enable them (Runtime Monitoring supports EKS on EC2 including Auto Mode) and validate any third-party runtime agent against Auto Mode before committing.
- **Secrets management** — Secrets Manager + Secrets Store CSI/ASCP (or ESO); the envelope-encryption CMK decision is yours.
- **IAM and cluster access** — Access Entries, least-privilege IAM, break-glass principals; review access entries regularly.
- **Audit evidence** — control-plane logging (`audit` + `authenticator` minimum), CloudTrail, Security Hub — none are auto-enabled.
- **Image supply chain and workloads** — ECR Enhanced Scanning, signing/verification, and the security of the containers themselves ("customers retain responsibility for securing and updating workloads running on these instances").
- **Persistent storage and VPC** — EBS volumes created via Kubernetes persistent storage are *not* fully managed by Auto Mode — enforce encryption via StorageClass (or account-level EBS encryption-by-default); VPC/subnet/SG design remains yours, as does ELB configuration.

## When to avoid Auto Mode for security reasons (as of 2026-07-17)

- **Custom AMI / baked-in hardening mandate** — Auto Mode does not support custom AMIs; AWS chooses the OS and image. If the auditor requires specific controls baked into the AMI, use Bottlerocket on self-managed Karpenter NodePools.
- **Alternate CNI requirement (Cilium, Calico, …)** — Auto Mode does not support alternate CNI or network-policy plugins.
- **Per-Pod Security Groups (classic SGPP) requirement** — a blocker only if *true per-Pod* SG assignment is mandated: the VPC CNI `SecurityGroupPolicy` CRD is [not supported on Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/auto-networking.html) (or Windows) nodes. Separate security groups for Pod traffic *are* available on Auto Mode via NodeClass [`podSecurityGroupSelectorTerms`](https://docs.aws.amazon.com/eks/latest/userguide/create-node-class.html), but only at NodeClass granularity (all Pods on that NodeClass share the same Pod security groups).
- **Host-level agent or forensic access requirement** — no SSH/SSM means no interactive node access; node-level tooling must run as a DaemonSet, and node forensic capture is constrained to what the APIs expose.
- **Windows workloads** — Auto Mode nodes are Linux-only.

**Not a blocker (a stale claim to avoid):** FIPS. Auto Mode offers **FIPS-compatible AMIs** in US regions via the NodeClass `advancedSecurity.fips` setting (released Oct 23, 2025) — do not cite FIPS as a reason to avoid Auto Mode. See the [Auto Mode release notes](https://docs.aws.amazon.com/eks/latest/userguide/auto-change.html).

## Bottom line

On Auto Mode, Layers 1 and parts of 3 (enforcement engine) shift to AWS; **Layers 2, 4, 5, 6, 7 and all policy content remain fully yours.** A "we're on Auto Mode so we're secure" posture fails an audit on GuardDuty, logging, PSA, NetworkPolicy content, and secrets handling — check each explicitly.

## Sources
- [Automate cluster infrastructure with EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/automode.html) (features, automated components, shared responsibility)
- [Security considerations for Amazon EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html)
- [Learn about Amazon EKS Auto Mode managed instances](https://docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html)
- [Alternate CNI plugins for Amazon EKS clusters](https://docs.aws.amazon.com/eks/latest/userguide/alternate-cni-plugins.html) (Auto Mode considerations)
- [EKS Auto Mode networking](https://docs.aws.amazon.com/eks/latest/userguide/auto-networking.html) · [Create a NodeClass](https://docs.aws.amazon.com/eks/latest/userguide/create-node-class.html) (SGPP unsupported; `podSecurityGroupSelectorTerms`) — verified 2026-07-21
- [EKS Auto Mode Best Practices: Security](https://docs.aws.amazon.com/eks/latest/best-practices/autosecure.html) (read-only root filesystem, SELinux enabled by default)
- [EKS Auto Mode release notes](https://docs.aws.amazon.com/eks/latest/userguide/auto-change.html) (FIPS AMIs; capability changes)
