---
title: "Breaking Changes Detection"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-upgrade-check/references/breaking-changes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-upgrade-check/references/breaking-changes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-upgrade-check/references/breaking-changes.md). Edit the source, not this page.
:::

# Breaking Changes Detection

## Purpose
Identify version-specific breaking changes that affect ACTUAL resources in the cluster. Only flag a breaking change if the cluster has resources that will be impacted.

## Principle
Every breaking change entry must be written in consultant-advisory style:
- **What we found** in YOUR cluster and why it matters
- **Real-world impact** if not addressed before upgrade
- **Concrete remediation** with commands where applicable

Do NOT list generic Kubernetes release notes. Only report changes that affect resources actually present in the cluster.

## Version-Specific Breaking Changes

### Target >= 1.25: PodSecurityPolicy Removed (historical note — not an active check)

PodSecurityPolicy (PSP) was removed in Kubernetes 1.25. This skill's supported source-version
floor is 1.30, so PSP is already gone on every assessable cluster — there is nothing left to
scan for. This entry is retained as background context ONLY; it is NOT an active check and
produces no finding or deduction.
- Historical remediation (for reference only): workloads formerly governed by a PSP should use
  Pod Security Standards (PSS) — label namespaces with
  `kubectl label namespace <ns> pod-security.kubernetes.io/enforce=restricted`.
- **Scoring home:** n/a — nothing to detect on any assessable (>= 1.30) cluster.

### Target >= 1.29: FlowSchema API v1beta2 Removed

**Check:** Scan cluster resources for `apiVersion: flowcontrol.apiserver.k8s.io/v1beta2`
- Look at FlowSchema and PriorityLevelConfiguration resources
- Apply the writer-identity filter in `deprecated-apis.md` Step 3b FIRST. An object is a real
  finding only if a user tool (kubectl/helm/argocd/flux) wrote v1beta2 in `managedFields`.
  Objects whose only v1beta2 trace comes from internal APF controllers
  (`api-priority-and-fairness-config-*`, `eks-internal`) are false positives and do NOT count.
  (AWS-managed field writers are tagged `manager: eks`; both fully- and partially-managed
  fields carry this manager string — see AWS EKS docs "Determine fields you can customize for
  Amazon EKS add-ons" (kubernetes-field-management.html). Internal control-plane writers such
  as `eks-internal` are likewise not user tools. Neither counts as a user-managed writer.)
- If a real (user-managed) object is found → HIGH severity (removed API in use). Update to `flowcontrol.apiserver.k8s.io/v1`
- **Scoring home:** this is a removed API — scored under Deprecated APIs (Category 2), NOT
  here. Do NOT also deduct for it under Breaking Changes — that would double-count.

### Target >= 1.30: AppArmor Annotations Deprecated

**Check:** Scan pod templates in deployments/daemonsets/statefulsets for
`container.apparmor.security.beta.kubernetes.io/*` annotations
- If found → MEDIUM severity. AppArmor itself is GA and fully supported — only the
  annotation mechanism is deprecated, superseded by the native
  `securityContext.appArmorProfile` field (GA in K8s 1.31; the field was added as beta
  in 1.30 — see the Kubernetes v1.31 release blog / KEP-24 "AppArmor support").
- Remediation: Replace the annotations with the `appArmorProfile` field in
  `securityContext` (pod- or container-level). This annotation-to-field change is a
  mechanism swap, not a security-model change — for the deprecated *annotation* the
  field is the direct replacement, not seccomp. (Separately, AppArmor as a whole is
  deprecated in Kubernetes 1.34, where AWS recommends migrating to seccomp or Pod
  Security Standards — see the "Target >= 1.34: AppArmor Deprecated" section below.)

### Target >= 1.32: FlowSchema API v1beta3 Removed

**Check:** Scan for `apiVersion: flowcontrol.apiserver.k8s.io/v1beta3`
- Apply the writer-identity filter in `deprecated-apis.md` Step 3b FIRST. An object is
  a real finding only if a user tool (kubectl/helm/argocd/flux) wrote v1beta3 in
  `managedFields`. Objects whose only v1beta3 trace comes from internal APF controllers
  (`api-priority-and-fairness-config-*`, `eks-internal`) are false positives and do
  NOT count. (AWS-managed field writers are tagged `manager: eks`; both fully- and
  partially-managed fields carry this manager string — see AWS EKS docs "Determine fields
  you can customize for Amazon EKS add-ons" (kubernetes-field-management.html). Internal
  control-plane writers such as `eks-internal` are likewise not user tools. Neither counts
  as a user-managed writer.)
- If a real (user-managed, not-yet-migrated) v1beta3 object is found → HIGH severity.
  Update to `flowcontrol.apiserver.k8s.io/v1`.
- **Scoring home:** this finding is scored under Deprecated APIs (Category 2), NOT
  here. Do NOT also deduct for it under Breaking Changes — that would double-count.

### Target >= 1.32: Anonymous Auth Restricted

**Flag** (MEDIUM severity) only when `current <= 1.31 AND target >= 1.32` — i.e. the upgrade crosses INTO the anonymous-auth restriction. A cluster already on 1.32+ has the restriction in effect; do NOT flag it again.
- Anonymous requests only allowed to /healthz, /livez, /readyz
- Check: List ClusterRoleBindings via the Kubernetes API and identify any whose `subjects[]`
  include `system:unauthenticated`
- **Flag MEDIUM only if** that listing shows a `system:unauthenticated` subject bound to something **beyond the API-server health-endpoint defaults** — access to `/healthz`, `/livez`, `/readyz` (via the default `system:public-info-viewer` binding) is the expected default and is NOT a finding. If the only bindings surfaced are those health-endpoint defaults, do NOT write the finding.
- Impact: Monitoring tools or LB health checks hitting non-health endpoints will get 401
- **Scoring home:** scored under Breaking Changes (Category 1, MEDIUM = 4 pts). Do
  NOT also count it under Behavioral Changes (Category 9) — it has exactly one home.

### Target >= 1.33: Endpoints API Deprecated

**Check:** List Endpoints resources, then apply the `deprecated-apis.md` Step 3b
writer-identity filter — a finding counts ONLY if a user tool
(`kubectl-*`, `helm`, `argocd-application-controller`, `flux`, etc.) wrote the
Endpoints object in `managedFields`.
- Do NOT flag by mere presence and do NOT simply "exclude the default `kubernetes`
  endpoint": the endpoints controller still auto-creates an Endpoints object for
  EVERY selector Service in 1.33+ (that behavior is unchanged), so a presence check
  false-positives on essentially every Service. The deprecation targets code/tooling
  that reads or writes the Endpoints API directly, which the writer test isolates.
- If a user-tool-written Endpoints object exists → MEDIUM severity
- Remediation: Migrate the tooling/consumers to the EndpointSlices API (`discovery.k8s.io/v1`)

### Target >= 1.33: AL2 AMI Not Available

**Check:** List nodes → inspect `status.nodeInfo.kernelVersion` for `amzn2` or `osImage` for `Amazon Linux 2`
- If AL2 nodes found → HIGH severity. Cannot create new AL2 node groups for 1.33+
- Remediation: Migrate to AL2023 or Bottlerocket BEFORE upgrading control plane

### Target >= 1.34: AppArmor Deprecated

**Check:** Detect AppArmor use on workloads — either the legacy
`container.apparmor.security.beta.kubernetes.io/*` annotations OR the
`securityContext.appArmorProfile` field set to `Localhost`/`RuntimeDefault`.
- If AppArmor is in use → MEDIUM severity. AppArmor (as a whole, not just the
  annotation form) is deprecated in Kubernetes 1.34. Source: AWS EKS "Review release
  notes for Kubernetes versions on standard support" — "AppArmor is deprecated in
  Kubernetes 1.34. We recommend migrating to alternative container security solutions
  like seccomp or Pod Security Standards"
  (`https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html`,
  as of 2026-08-05).
- **Clarifier:** this "deprecated in 1.34" wording is AWS EKS guidance, NOT an upstream
  Kubernetes removal. Upstream, the `securityContext.appArmorProfile` field is GA since
  Kubernetes 1.31 and is NOT deprecated; only the legacy
  `container.apparmor.security.beta.kubernetes.io/*` annotation form is deprecated
  upstream. Treat the AWS note as EKS-recommended migration guidance, not as a signal
  that the field API is going away.
- Remediation: Plan migration to seccomp profiles or Pod Security Standards per the AWS
  guidance above. (This SUPERSEDES the narrower annotation-only advice under
  "Target >= 1.30" — for a 1.34+ target, migrating off AppArmor entirely is the AWS
  recommendation, whereas below 1.34 the annotation-to-field swap is the only change.)

### Target >= 1.34: Freshness / Coverage Gate

This file enumerates specific 1.34 changes above, but the Kubernetes 1.34 and EKS 1.34
release notes may carry additional breaking changes not captured here. For any target
>= 1.34, before reporting "no further breaking changes," perform the same live lookup
described under "Target > 1.36: Live Lookup Required" below:
1. A documentation search for "EKS Kubernetes <target> breaking changes"
2. A documentation search for "Kubernetes <target> removed APIs"
3. Fetch the K8s CHANGELOG for the target minor version
4. A documentation search for "EKS <target> release notes"

**If live sources are unreachable:** note "Breaking changes for <target> could not be
fully verified — AWS/K8s documentation unavailable; re-check before upgrading" rather
than asserting the list is complete.

### Target >= 1.35: Cgroup v1 Support Removed from Default Config (conditional; overridable)

**Conditional** — flag (HIGH severity) ONLY if cgroup v1 nodes are detected. Applies
to any target >= 1.35. Note this is not an absolute block: the kubelet
`failCgroupV1=false` override keeps cgroup v1 nodes running. EKS-managed AL2023 and
Bottlerocket nodes are cgroup v2 and unaffected (Bottlerocket additionally sets
`failCgroupV1=false`). Fargate continues to use cgroup **v1**, but AWS manages the Fargate
runtime, so there is no customer remediation for Fargate (source: AWS EKS Kubernetes 1.35
release notes, "Fargate continues to use cgroup v1").
- kubelet refuses to start on cgroup v1 nodes unless `failCgroupV1=false`
- AL2 uses cgroup v1 by default; AL2023 and Bottlerocket use cgroup v2
- **Check:** inspect node OS images — AL2 nodes (osImage contains "Amazon Linux 2",
  not "2023") imply cgroup v1; AL2023/Bottlerocket nodes are cgroup v2. If NO cgroup
  v1 nodes are present, do NOT flag and do NOT deduct — record under Informational
  Findings only.
- **Detection caveat:** this keys on the osImage "Amazon Linux 2" string as a
  conservative proxy for cgroup v1 — the actual cgroup version is not read from the
  node. An AL2 node pinned to cgroup v2 over-flags; a non-AL distro pinned to v1 is missed.

### Target >= 1.35: Containerd 1.x Outside Tested Matrix (managed AMIs unaffected)

**Check:** List nodes → inspect `status.nodeInfo.containerRuntimeVersion`
- If any node shows containerd 1.x → MEDIUM severity (HIGH for self-managed / custom-AMI nodes at target >= 1.36 — see Node Readiness 5.3)
- containerd 1.x is outside the tested matrix for 1.36, which is validated against containerd 2.x. EKS-managed AL2023 AMIs ship containerd 2.x, so they are unaffected.
- **Scoring home:** containerd 1.x is scored under Node Readiness (Category 3), NOT
  here. It is HIGH severity for the self-managed/1.36 case but is NOT a hard blocker (no score cap). Do NOT also deduct for it under Breaking Changes — that would double-count.

### Any target: Ingress NGINX Retired (calendar event, version-independent)

**Check:** List deployments/daemonsets with `ingress-nginx` or `nginx-ingress` in name
- This is NOT gated on the Kubernetes target version. The `ingress-nginx` project
  retired in March 2026 (Kubernetes Steering and Security Response Committees announcement) — a calendar event, not a
  version property. Flag `ingress-nginx` on ANY cluster regardless of current or target
  version, matching `oss_addon_registry.json` ("HIGH severity regardless of current
  version compatibility").
- If found → HIGH severity. The project is retired: no more releases or security patches.
- Remediation: Migrate to Gateway API (e.g. Envoy Gateway, AWS Gateway API Controller)
  or the AWS Load Balancer Controller.

### Target == 1.35: IPVS Proxy Mode Deprecated

**Check:** Read kube-proxy ConfigMap → check `mode` field
- If `mode: ipvs` AND target is exactly 1.35 → MEDIUM severity. IPVS proxy mode is deprecated as of 1.35; removal is slated for a future release (it is NOT removed in 1.36).
- Remediation: Plan a migration to iptables or nftables mode ahead of the eventual removal.

### Target >= 1.35: --pod-infra-container-image Flag Removed

**Conditional** — flag (LOW severity) ONLY if custom-AMI / self-managed nodes are
detected (reuse the classification from node-readiness.md check 5.4). Applies to any
target >= 1.35.
- Affects custom AMIs with this kubelet flag in bootstrap scripts
- EKS-managed AMIs are not affected — if the cluster has no self-managed/custom-AMI
  nodes, do NOT flag and do NOT deduct
- **Detection caveat:** this detects the *presence* of self-managed/custom-AMI nodes,
  not whether the `--pod-infra-container-image` flag is actually set — the kubelet flag
  is not readable via the API. Presence is a conservative proxy.

### Target >= 1.36: IPVS Proxy Mode Deprecated (removal in a future release)

**Check:** Read kube-proxy ConfigMap → check `mode` field
- If `mode: ipvs` → MEDIUM severity. IPVS proxy mode is deprecated (as of 1.35) and slated for
  removal in a future release; it is NOT removed in 1.36.
- Remediation: Plan a migration to iptables or nftables mode ahead of the eventual removal.

### Target >= 1.36: gitRepo Volume Removed

**Check:** Scan pod templates (Deployments, DaemonSets, StatefulSets, Jobs, CronJobs, bare Pods)
for `spec.volumes[].gitRepo`.
- If found → HIGH severity. The `gitRepo` volume type is permanently disabled in 1.36. The API
  still accepts the spec, but the kubelet refuses to run the pod and returns an error — so the
  workload will fail to start on 1.36 nodes.
- Remediation: Migrate to an initContainer that clones the repo, or a git-sync sidecar, before
  upgrading. See KEP-5040.

### Target >= 1.36: Strict IP/CIDR Validation

**Check:** Scan manifests/resources for IP or CIDR fields with non-canonical notation —
leading zeros (e.g., `010.000.000.005`) or ambiguous CIDR (e.g., `192.168.0.5/24` instead of
`192.168.0.0/24`). Common in Services, NetworkPolicies, and custom configs.
- If found → MEDIUM severity. The `StrictIPCIDRValidation` feature gate is on by default for
  built-in API kinds in 1.36. Existing stored objects are preserved (validation ratcheting),
  but new creates/updates with non-canonical values are rejected. Does NOT apply to custom
  resource kinds.
- Remediation: Update manifests, Helm charts, and automation to canonical IP/CIDR format before
  upgrading. See KEP-4858.

### Target >= 1.37: SELinux Volume Labeling GA

**Check:** Only relevant on SELinux-enforcing nodes. Look for pods sharing a single volume
between privileged and unprivileged containers.
- If SELinux is enforced AND shared volumes exist → MEDIUM severity. Faster SELinux volume
  labeling now defaults to all volumes (using `mount -o context` instead of recursive
  relabeling). Sharing a volume between privileged and unprivileged pods on the same node may
  break.
- Remediation: Audit clusters and set the `seLinuxChangePolicy` field and SELinux volume labels
  correctly on affected pods before upgrading.

### Target >= 1.36: Service externalIPs Deprecated

**Check:** Scan Services for a non-empty `spec.externalIPs` field.
- If found → LOW severity. `externalIPs` is deprecated in 1.36 (full removal planned for 1.43).
  Creating/updating such Services produces deprecation warnings but still works.
- Remediation: Plan migration to LoadBalancer Services, NodePort, or Gateway API. See KEP-5707.

### Target > 1.36: Live Lookup Required

This file does not cover breaking changes for versions beyond 1.36. If the target version
is > 1.36, you MUST perform a live lookup before reporting "no breaking changes found."

**How to check:**
1. Search AWS docs: a documentation search for "EKS Kubernetes <target> breaking changes"
2. Search AWS docs: a documentation search for "Kubernetes <target> removed APIs"
3. Fetch the Kubernetes changelog: the K8s CHANGELOG for the target
   minor version (e.g., CHANGELOG-1.37.md)
4. Check for EKS-specific changes: a documentation search for "EKS <target> release notes"

**If no breaking changes are found after live lookup:** Report "No breaking changes identified
for <target> based on available documentation" with a note that the user should re-check closer
to their upgrade date as documentation may be updated.

**If live sources are unreachable:** Report "Breaking changes for <target> could not be verified —
AWS documentation unavailable" with MEDIUM severity. Do NOT assume no breaking changes exist.

## Score Impact

> **Canonical scoring is defined in `references/report-generation.md` §Category 1 (Breaking Changes).**

| Severity | Per-item Deduction | Max Category |
|----------|-------------------|--------------|
| HIGH | 10 pts | 25 pts total |
| MEDIUM | 4 pts | |
| LOW | 2 pts | |
