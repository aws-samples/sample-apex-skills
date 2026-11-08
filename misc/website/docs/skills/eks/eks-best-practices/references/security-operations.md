---
title: "EKS Security Operations"
description: "How a platform team runs EKS security over time: staying informed, patch cadence and the emergency path, build hygiene, and the shape of a security event..."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-best-practices/references/security-operations.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-best-practices/references/security-operations.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-best-practices/references/security-operations.md). Edit the source, not this page.
:::

# EKS Security Operations

> **Part of:** [eks-best-practices](../index.md)
> **Purpose:** How a platform team runs EKS security over time: staying informed, patch cadence and the emergency path, build hygiene, and the shape of a security event response

This file is knowledge only. Live checks (am I exposed, would my setup contain it) belong to eks-security: see "Live checks: eks-security" in [SKILL.md: Security Operations](../index.md#security-operations).

**For hardening controls, see:** [Security](security.md) | [Runtime & Network](security-runtime-network.md) | [Supply Chain & Compliance](security-supply-chain.md) | [Container Registry](container-registry.md)

---

## Table of Contents

1. [Staying Informed](#staying-informed)
2. [Patch Cadence and the Emergency Path](#patch-cadence-and-the-emergency-path)
3. [Build Hygiene](#build-hygiene)
4. [Responding to a Security Event](#responding-to-a-security-event)

---

## Staying Informed

A team that learns about a fix at its next quarterly review has been exposed for the whole gap. Decide which sources cover each layer you run, route them into the channel your on-call already watches, and name an owner who triages each item within a working day.

### Sources per layer

| Layer | Source | Format |
|---|---|---|
| AWS services, EKS add-ons, AWS-published components | [AWS security bulletins](https://aws.amazon.com/security/security-bulletins/) | Web page plus an RSS feed (`https://aws.amazon.com/security/security-bulletins/rss/feed/`) |
| Account-specific notices (end of support, required actions) | AWS Health | Events to EventBridge |
| Kubernetes itself | [Kubernetes official CVE feed](https://kubernetes.io/docs/reference/issues-security/official-cve-feed/) | JSON and RSS |
| Node OS: Amazon Linux | [Amazon Linux Security Center](https://alas.aws.amazon.com/) | RSS per release (AL2023; AL2 reached end of support 2026-06-30) |
| Node OS: Bottlerocket | [Bottlerocket security advisories](https://advisories.bottlerocket.aws/updateinfo.xml.gz) | `updateinfo.xml.gz` (follow redirects) |
| EKS optimized AMIs (Amazon Linux 2023) | [amazon-eks-ami releases](https://github.com/awslabs/amazon-eks-ami/releases) | GitHub releases |
| Add-ons and controllers you install (VPC CNI, CSI drivers, load balancer controller, Karpenter, metrics-server, and so on) | Each project's GitHub releases and repository security advisories | Watch the repository for releases |
| Your images and their packages | Amazon Inspector enhanced scanning on ECR, which rescans images when new CVEs are published, while they are within the configured re-scan duration (push date and last-in-use date; 7 days by default for new activations); set it to cover every image you still run (multi-architecture images: use the pull date, since last-in-use is not tracked) | Findings to EventBridge and Security Hub |
| Your application dependencies | Your language ecosystem's advisory database through a dependency bot or software composition analysis in CI | Pull requests or CI findings |

Read available add-on versions live (see [Cluster Upgrades](cluster-upgrades.md#add-on-compatibility-matrix-check)).

### Get alerted, do not go looking

- Route Amazon Inspector findings through EventBridge (or Security Hub) to the on-call channel, filtered to `CRITICAL` and `HIGH` for paging and the rest for a daily digest. Inspector can map an ECR image to the EKS pods running it, so a finding can name the affected workloads (the mapping refreshes about daily).
- Feed the bulletin and OS advisory RSS feeds into the team's chat or ticketing tool, so a new item opens a ticket with an owner rather than waiting to be read.
- Keep an inventory of what runs where (add-on versions, self-managed controller images, node AMIs, application images by digest). A bulletin is only useful if you can answer "do we run that" in minutes. eks-security C1 collects this inventory (images by digest included) and compares it with an advisory.
- Run a standing sweep (for example weekly) of every source since the last sweep against that inventory. eks-security C1's sweep mode does this on a cluster for the AWS bulletin, Kubernetes, Amazon Linux and Bottlerocket feeds and Inspector findings; watch the other sources in the table yourself.

### Triage each item the same way

1. Does the affected component run in any of our clusters, at an affected version? (eks-security C1; "we cannot tell" is a finding, not a "no".)
2. What is the published severity, and is there a workaround?
3. Which path does the fix take: the normal cadence or the emergency path (below)?

Keep the published severity as the starting point. Context such as "we do not rely on that feature" belongs in the ticket as a note; it does not quietly lower the priority.

---

## Patch Cadence and the Emergency Path

Two paths, written down before you need them: a **normal cadence** that keeps everything current between Kubernetes upgrades, and an **emergency path** for a security fix that cannot wait for the next window.

### Normal cadence

| Component | How it updates | Cadence to set |
|---|---|---|
| EKS managed add-ons | `aws eks update-addon` to a newer patch version | A fixed interval (for example every 2 to 4 weeks), plus at every Kubernetes minor upgrade |
| Self-managed controllers (Helm or GitOps) | Chart or image version bump through your pipeline | Same interval as managed add-ons |
| Node images: managed node groups | `aws eks update-nodegroup-version` to the latest AMI release for the cluster version | A fixed interval |
| Node images: Karpenter | Drift: a new AMI matching `amiSelectorTerms` (for example an `@latest` alias) replaces nodes; a pinned AMI needs a bump | Bounded by `expireAfter` (see [Karpenter](karpenter.md)) |
| Node images: EKS Auto Mode | AWS publishes a patched node AMI at most weekly; NodePools replace nodes through drift once it is available, within PDBs and NodePool disruption budgets. Built-in NodePools also expire nodes after 14 days; 21 days is the enforced maximum | Lower `expireAfter` on your own NodePools if you need faster rotation |
| Node OS: Bottlerocket | In-place OS update through the Bottlerocket update operator, or node replacement | A fixed interval |
| Base images | Rebuild and rescan (see [Container Registry](container-registry.md)) | Weekly is a common choice |
| Application images | Rebuild on the refreshed base image, even with no code change | Each time the base image moves |

Cadence rules:

- Every change goes through non-production first, with the same tests each time, so a routine update stays routine.
- PodDisruptionBudgets and topology spread let node rotation run during working hours without an outage (see [Reliability & Resiliency: Core](reliability-core.md)).
- Track the time from "fix released" to "fix running in production" per component. That number, not the cadence on paper, is your real exposure window.

### The emergency path

Use it when a fix addresses a published critical or high issue in a component you run at an affected version, and especially when there is no workaround.

1. **Confirm exposure** on each cluster (eks-security C1). Record the clusters, node groups and workloads in scope.
2. **Apply any published workaround** first if one exists, as a stopgap while the fix is tested.
3. **Test the fix in non-production** with a shortened soak: the same smoke and health checks as the normal cadence, measured in hours, not weeks.
4. **Roll out to production** outside the normal window, one cluster or node group at a time, with PDBs respected:
   - Managed add-on: `aws eks update-addon --cluster-name <c> --addon-name <a> --addon-version <fixed> --resolve-conflicts PRESERVE` (`PRESERVE` keeps your configuration changes; review the diff first).
   - Managed node group: update to the AMI release that carries the fix.
   - Karpenter or Auto Mode: confirm the fixed AMI is the one selected, then let drift or a planned rotation replace the older nodes. On Auto Mode, list nodes created before the fix was released; they run the old build until replaced.
   - Application image: rebuild on a patched base or a fixed package version, then deploy through the pipeline.
5. **Verify** with the same check that confirmed exposure (eks-security C1), not by reading the version you meant to deploy.
6. **Record** the dates (published, triaged, fixed in non-production, fixed in production) and what slowed it down, and feed that back into the normal cadence.

The emergency path is a shortened version of the normal one, not a bypass. Skipping non-production entirely trades a known risk for an unknown one.

---

## Build Hygiene

Build practices decide how far one bad dependency or base image can spread, and how fast you can replace it.

### Pin, then move the pin on purpose

- Reference base images by digest (`FROM <registry>/<image>@sha256:<digest>`) and deploy application images by digest or immutable tag (see [Container Registry](container-registry.md)). A tag can be moved under you; a digest cannot.
- Move a pinned digest through a reviewed change (a dependency bot pull request or a pipeline step), so every base image change is visible, tested and reversible.

### Install dependencies from a lockfile, in an isolated step

- Commit the lockfile and install from it in the package manager's locked or frozen mode, so a build cannot pick up a version nobody reviewed.
- Installing a package can run code from that package. Turn off package install scripts by default where the package manager allows it, and allow them only for the packages that need them. Run dependency installation in an isolated build stage with no cloud credentials, no access to secrets and only the network it needs to reach your package mirror; copy only the built output into the runtime image (multi-stage build).

### Scanners have limits: rebuild on a cadence anyway

- Image scanners match installed packages against CVE-indexed advisories. Content that is not tracked as a package, such as a certificate trust store bundled inside a language runtime, configuration files, or binaries and data copied into the image, may change in a security-relevant way without any CVE or scan finding.
- So "no findings" is not "up to date". Rebuild application images on refreshed base images and runtime releases on a fixed cadence, whatever the scan says.
- For SBOMs and image signing, see [Supply Chain & Compliance](security-supply-chain.md).

---

## Responding to a Security Event

One shape for any event (prepare, scope, record, contain, investigate, remediate, verify, report): a vulnerable component in use, a compromised image or package, a leaked credential, or suspicious behaviour in a pod. Write the runbook around this shape before you need it. eks-security C2 runs scope, evidence capture and containment proposals on a live cluster; checking whether an exposure was used (step 4's GuardDuty, CloudTrail and audit-log reads) is the team's own step for now ([issue 351](https://github.com/aws-samples/sample-apex-skills/issues/351)).

| Step | Question | Practice |
|---|---|---|
| 0. Prepare | Before any event | Turn on audit logging and GuardDuty EKS Protection and Runtime Monitoring beforehand (see [Runtime & Network](security-runtime-network.md)). For a compromised host and the order to redeploy in, follow the [AWS incident response guide](https://docs.aws.amazon.com/eks/latest/best-practices/incident-response-and-forensics.html). |
| 1. Scope | What is involved? | Clusters, namespaces, workloads, images by digest, packages, and the identities those workloads use (Pod Identity associations, IRSA roles, the node role). Start from the inventory, not from memory. |
| 2. Record | What must we keep before acting? | Record the pod spec, node, image digest and logs (seconds, read through the API server), then contain at once. |
| 3. Contain | How do we stop it spreading without taking down neighbours? | Isolate the affected pods, not the namespace (below). Limit egress, cordon the node, and cut off the identity the workload used. Protect the node where the platform allows it (EC2 termination protection, not on Spot, plus ASG scale-in protection; neither stops Cluster Autoscaler, which removes nodes through `TerminateInstanceInAutoScalingGroup`, so with Cluster Autoscaler also annotate the node (`kubectl annotate node <node> cluster-autoscaler.kubernetes.io/scale-down-disabled=true`) before Cluster Autoscaler marks it for deletion (it then carries the `ToBeDeletedByClusterAutoscaler` taint); on Karpenter, annotate the node (`kubectl annotate node <node> karpenter.sh/do-not-disrupt=true`), which also blocks drift; on Auto Mode, the pod annotation (`kubectl annotate pod <pod> -n <namespace> karpenter.sh/do-not-disrupt=true`), which does not stop expiry, Spot interruption, node auto repair (on by default in Auto Mode) or drift (Auto Mode gives each NodeClaim a 24h `terminationGracePeriod` by default ([create-node-pool](https://docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html))); see [Karpenter](karpenter.md#do-not-disrupt-does-not-block-forceful-disruption)). |
| 4. Investigate | Was it used? | After isolation: capture volatile state (see [Incident Response in Supply Chain & Compliance](security-supply-chain.md#incident-response)), snapshot the node's EBS volumes where the platform allows it, then check GuardDuty EKS findings, CloudTrail for the involved roles or keys, and the cluster audit log. Deleting, scaling down or draining destroys evidence; isolating does not, unless a liveness probe then fails and restarts the container. |
| 5. Remediate | What removes the cause? | The patched add-on, node image, base image or package version, through the emergency path above. |
| 6. Verify | Is it gone, and would it be contained next time? | Re-run the exposure check (eks-security C1) and the posture checks for the affected controls (eks-security C3). |
| 7. Report | What happened and what changes? | What, when, exposure, evidence found (or "no evidence in sources X for window Y"), actions taken, open items, and the changes to cadence, alerting or controls. |

### Containment that stays pod-scoped

A deny-all policy on the whole namespace cuts off healthy pods too. Select the affected pods by label instead:

```yaml
# Quarantine: denies traffic to and from selected pods only if no other NetworkPolicy also selects them and allows it (policies are additive); open connections may survive, depending on the engine
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: quarantine
  namespace: <namespace>
spec:
  podSelector:
    matchLabels:
      quarantine: "true"
  policyTypes:
  - Ingress
  - Egress
```

Then label the affected pod: `kubectl label pod <pod> -n <namespace> quarantine=true`. To make it hold whatever other policies allow, use an Admin-tier ClusterNetworkPolicy Deny where the VPC CNI enforces policy (v1.22.3+, the fixed release in [AWS security bulletin 2026-170](https://aws.amazon.com/security/security-bulletins/2026-170-aws/), or Auto Mode; see [Runtime & Network](security-runtime-network.md)); under Calico or Cilium use that engine's cluster-wide deny. The pod still counts toward its ReplicaSet: pause Deployment rollouts (`kubectl rollout pause`) and hold HPA or manual scale-downs until evidence is taken; do not change its app labels. Notes:

- NetworkPolicy works only where a policy engine enforces it (VPC CNI with network policy enabled; EKS Auto Mode once the Network Policy Controller ConfigMap is applied; or, outside Auto Mode, another engine such as Calico or Cilium). VPC CNI policies do not apply to Fargate or Windows pods. Confirm enforcement before relying on it; Security Groups for Pods are the alternative where they are in use (see [Runtime & Network](security-runtime-network.md)).
- VPC CNI network policy enforcement might not work reliably for standalone pods (created without a controller, so no `metadata.ownerReferences`); do not rely on the quarantine policy alone for them ([Limit Pod traffic with Kubernetes network policies](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html)).
- Cutting off a workload identity has two parts: stop new credentials (remove the Pod Identity association or tighten the role's trust policy), and invalidate credentials already issued, which stay valid until they expire, by [revoking the role's active sessions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html). Revoking denies every session of the role, healthy pods included, until they fetch new credentials; check who shares the role first. For the node role this hits every node that uses it; follow the AWS guide (remove the role from the instance) instead.
- Automate only the first containment step (for example a GuardDuty finding through EventBridge to a function that applies the quarantine label) and keep the rest a human decision; the label isolates only where the quarantine policy already exists in that pod's namespace: create it in every namespace beforehand (step 0) or use the Admin-tier ClusterNetworkPolicy.

---

**Sources:**
- [AWS security bulletins](https://aws.amazon.com/security/security-bulletins/)
- [Kubernetes official CVE feed](https://kubernetes.io/docs/reference/issues-security/official-cve-feed/)
- [Amazon ECR: EventBridge events for enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-events.html)
- [EKS Auto Mode: instance lifecycle and patching](https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html)
- [Amazon Inspector: Configuring the Amazon ECR re-scan duration](https://docs.aws.amazon.com/inspector/latest/user/scanning_resources_configure_duration_setting_ecr.html)
- [Security Overview of Amazon EKS Auto Mode: data plane](https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html)
- [Revoke IAM role temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html)
- [AWS EKS Best Practices Guide: Incident Response](https://docs.aws.amazon.com/eks/latest/best-practices/incident-response-and-forensics.html)
