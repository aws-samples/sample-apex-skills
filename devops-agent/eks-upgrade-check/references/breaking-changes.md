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

### Target >= 1.25: PodSecurityPolicy Removed

**Check:** List PodSecurityPolicy resources via Kubernetes API
- Apply the writer-identity filter in `deprecated-apis.md` Step 3b FIRST. A PSP is a real
  finding only if a user tool (kubectl/helm/argocd/flux) wrote it in `managedFields`; objects
  whose only trace comes from internal controllers do NOT count.
- If a real (user-managed) PSP exists → HIGH severity. PSPs will cease to exist after upgrade.
- Remediation: Migrate to Pod Security Standards (PSS) by labeling namespaces: `kubectl label namespace <ns> pod-security.kubernetes.io/enforce=restricted`
- **Scoring home:** this is a removed API — scored under Deprecated APIs (Category 2), NOT
  here. Do NOT also deduct for it under Breaking Changes — that would double-count.

### Target >= 1.29: FlowSchema API v1beta2 Removed

**Check:** Scan cluster resources for `apiVersion: flowcontrol.apiserver.k8s.io/v1beta2`
- Look at FlowSchema and PriorityLevelConfiguration resources
- Apply the writer-identity filter in `deprecated-apis.md` Step 3b FIRST. An object is a real
  finding only if a user tool (kubectl/helm/argocd/flux) wrote v1beta2 in `managedFields`.
  Objects whose only v1beta2 trace comes from internal APF controllers
  (`api-priority-and-fairness-config-*`, `eks-internal`) are false positives and do NOT count.
  (`eks-internal` — exact manager string unverified against public AWS docs as of 2026-07;
  AWS documents `manager: eks`. Kept conservatively.)
- If a real (user-managed) object is found → HIGH severity (removed API in use). Update to `flowcontrol.apiserver.k8s.io/v1`
- **Scoring home:** this is a removed API — scored under Deprecated APIs (Category 2), NOT
  here. Do NOT also deduct for it under Breaking Changes — that would double-count.

### Target >= 1.30: AppArmor Annotations Deprecated

**Check:** Scan pod templates in deployments/daemonsets/statefulsets for
`container.apparmor.security.beta.kubernetes.io/*` annotations
- If found → MEDIUM severity. AppArmor itself is GA and fully supported — only the
  annotation mechanism is deprecated, superseded by the native
  `securityContext.appArmorProfile` field (GA in K8s 1.30).
- Remediation: Replace the annotations with the `appArmorProfile` field in
  `securityContext` (pod- or container-level). Do NOT migrate to seccomp — seccomp
  and AppArmor are complementary mechanisms, not replacements.

### Target >= 1.32: FlowSchema API v1beta3 Removed

**Check:** Scan for `apiVersion: flowcontrol.apiserver.k8s.io/v1beta3`
- Apply the writer-identity filter in `deprecated-apis.md` Step 3b FIRST. An object is
  a real finding only if a user tool (kubectl/helm/argocd/flux) wrote v1beta3 in
  `managedFields`. Objects whose only v1beta3 trace comes from internal APF controllers
  (`api-priority-and-fairness-config-*`, `eks-internal`) are false positives and do
  NOT count. (`eks-internal` — exact manager string unverified against public AWS docs
  as of 2026-07; AWS documents `manager: eks`. Kept conservatively.)
- If a real (user-managed, not-yet-migrated) v1beta3 object is found → HIGH severity.
  Update to `flowcontrol.apiserver.k8s.io/v1`.
- **Scoring home:** this finding is scored under Deprecated APIs (Category 2), NOT
  here. Do NOT also deduct for it under Breaking Changes — that would double-count.

### Target >= 1.32: Anonymous Auth Restricted

**Flag** (MEDIUM severity) only when `current <= 1.31 AND target >= 1.32` — i.e. the upgrade crosses INTO the anonymous-auth restriction. A cluster already on 1.32+ has the restriction in effect; do NOT flag it again.
- Anonymous requests only allowed to /healthz, /livez, /readyz
- Check: List ClusterRoleBindings via the Kubernetes API and flag any whose `subjects[]`
  include `system:unauthenticated`
- Impact: Monitoring tools or LB health checks hitting non-health endpoints will get 401
- **Scoring home:** scored under Breaking Changes (Category 1, MEDIUM = 4 pts). Do
  NOT also count it under Behavioral Changes (Category 9) — it has exactly one home.

### Target >= 1.33: Endpoints API Deprecated

**Check:** List Endpoints resources (exclude the default `kubernetes` endpoint)
- If custom Endpoints exist → MEDIUM severity
- Remediation: Migrate to EndpointSlices API (`discovery.k8s.io/v1`)

### Target >= 1.33: AL2 AMI Not Available

**Check:** List nodes → inspect `status.nodeInfo.kernelVersion` for `amzn2` or `osImage` for `Amazon Linux 2`
- If AL2 nodes found → HIGH severity. Cannot create new AL2 node groups for 1.33+
- Remediation: Migrate to AL2023 or Bottlerocket BEFORE upgrading control plane

### Target >= 1.35: Cgroup v1 Support Removed

**Conditional** — flag (HIGH severity) ONLY if cgroup v1 nodes are detected. Applies
to any target >= 1.35.
- kubelet refuses to start on cgroup v1 nodes unless `failCgroupV1=false`
- AL2 uses cgroup v1 by default; AL2023 and Bottlerocket use cgroup v2
- **Check:** inspect node OS images — AL2 nodes (osImage contains "Amazon Linux 2",
  not "2023") imply cgroup v1; AL2023/Bottlerocket nodes are cgroup v2. If NO cgroup
  v1 nodes are present, do NOT flag and do NOT deduct — record under Informational
  Findings only.
- **Detection caveat:** this keys on the osImage "Amazon Linux 2" string as a
  conservative proxy for cgroup v1 — the actual cgroup version is not read from the
  node. An AL2 node pinned to cgroup v2 over-flags; a non-AL distro pinned to v1 is missed.

### Target >= 1.35: Containerd 1.x End of Support

**Check:** List nodes → inspect `status.nodeInfo.containerRuntimeVersion`
- If any node shows containerd 1.x → MEDIUM severity (HIGH for self-managed / custom-AMI nodes at target >= 1.36 — see Node Readiness 5.3)
- containerd 1.x is outside the tested matrix for 1.36, which is validated against containerd 2.x. EKS-managed AL2023 AMIs ship containerd 2.x, so they are unaffected.
- **Scoring home:** containerd 1.x is scored under Node Readiness (Category 3), NOT
  here. It is HIGH severity for the self-managed/1.36 case but is NOT a hard blocker (no score cap). Do NOT also deduct for it under Breaking Changes — that would double-count.

### Target >= 1.35: Ingress NGINX Retired

**Check:** List deployments/daemonsets with `ingress-nginx` or `nginx-ingress` in name
- If found → HIGH severity. No more security patches.
- Remediation: Migrate to Gateway API or AWS Load Balancer Controller

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
