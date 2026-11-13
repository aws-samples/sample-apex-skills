#!/usr/bin/env bash
# Adapted from skills/eks-well-architected-review/assets/reduce.sh at commit 7965ae3 (security pillar only). Keep in step by hand.
#
# Severity-weighted posture reducer with a coverage gate.
#
# Usage:  posture_reduce.sh <workdir>
#   Reads <workdir>/posture/results.jsonl (posture_score.sh) and <workdir>/posture/results-extra.jsonl
#   (posture_extra.sh); either may be absent, and every check without a token is reported `unknown`.
#   Writes <workdir>/posture.json (0600) and prints one JSON summary line on stdout.
#
# Exit codes: 0 posture.json written, coverage at or above the gate; 3 posture.json written but
# incomplete (coverage below the gate, score null); 2 usage or validation error, nothing written
# (one line on stdout: {"ok":false,"code":"<code>","error":"..."}; codes: usage, no_workdir, no_tokens,
# bad_token, duplicate_id, unknown_check, internal).
#
# ── OUTPUT SHAPE: <workdir>/posture.json, schema "eks-security/posture@1" (render_report.py reads it) ──
# {
#   "schema": "eks-security/posture@1",
#   "cluster": "<name>",                   from posture/cluster.json
#   "generated_at": "<ISO8601Z>",
#   "coverage": {
#     "checks_total": <int>,               measured checks in the catalog (governance checks excluded)
#     "checks_answered": <int>,            measured checks whose result is pass or fail
#     "ratio": <0..1, 3 decimals>,         checks_answered / checks_total
#     "gate": 0.5,
#     "complete": <bool>                   ratio >= gate (WAR's rule: applicable*2 >= total)
#   },
#   "score": <0-100 int> | null,           null when coverage.complete is false
#   "layers": [ {"layer": "<layer>", "verdict": "contained|partly|not-contained|unknown"} ],  all seven, fixed order
#   "checks": [ {
#     "id": "SEC-POSTURE-<n>",
#     "war_id": "<eks-well-architected-review question id>" | null,   null for the containment checks WAR lacks
#     "title": "<question>",
#     "result": "pass|fail|na|unknown",
#     "severity": "high|medium|low",
#     "evidence": "<the scorer's detail, plus up to 10 failing objects>",
#     "source_file": "posture/<file>.json[, ...]" | null,             null for governance checks
#     "recommendation": "<printed advice for the team to review; nothing is changed>",
#     "layer": "<layer>",                  extra key: the containment layer this check counts toward
#                                          (for SEC-POSTURE-18, 19, 21 and 25 the catalog grouping only)
#     "state": "all|most|some|none|na|unknown"   extra key: the scorer's bucket, which the score uses
#   } ]
# }
# Layers: node-credential, lateral-movement, privilege, identity, detection, api-exposure, supply-chain.
#
# RULES (copied from WAR reduce.sh unless marked):
#  - result: state all -> pass; most, some, none -> fail; na -> na; unknown -> unknown. Governance
#    questions are process questions with no cluster evidence: always `unknown`, never in coverage, score
#    or layer verdicts (WAR scores them separately as Not Assessed).
#  - score: sum(points(state) * weight) / sum(weight) over answered checks, rounded; points all 100,
#    most 75, some 50, none 0; weight high 3, medium 2, low 1 (WAR's High/Medium/Low). na and unknown are
#    left out of both sums. Below the coverage gate the score is null (WAR: INSUFFICIENT).
#  - layer verdict (new): over the measured checks of the layer, unknown when none is answered;
#    not-contained when any high-severity check fails; contained when every answered check passes and
#    none is unknown; partly otherwise. SEC-POSTURE-18, 19, 21 and 25 (encryption at rest and TLS
#    settings, which a compromised pod does not depend on) are scored and listed but count toward no
#    layer verdict.
#  - refusals (WAR's): a token that is not an object with a string id and a legal state and track, a
#    duplicate id, or an id the catalog does not know is refused with exit 2 and nothing is written.
#    Unlike WAR, a catalog check with no token is not refused; it is `unknown`, so the gate counts it.
#
# The catalog below carries each check's id, WAR id, title, layer, severity (WAR references/severity.md
# Security tables at 7965ae3 for the copied questions), source files and recommendation.
set -uo pipefail
umask 077

die() { printf 'posture_reduce.sh: %s\n' "$2" >&2; jq -cn --arg c "$1" --arg e "$2" '{ok:false,code:$c,error:$e}' 2>/dev/null \
  || printf '{"ok":false,"code":"%s","error":"see stderr"}\n' "$1"; exit 2; }
[ $# -eq 1 ] || die usage "usage: posture_reduce.sh <workdir>"
command -v jq >/dev/null 2>&1 || die internal "jq not found on PATH"
WORK="$1"; P="$WORK/posture"
[ -d "$P" ] && [ -f "$P/cluster.json" ] || die no_workdir "$P/cluster.json not found; run posture_collect.sh, posture_score.sh and posture_extra.sh first"

CATALOG=$(cat <<'CATALOG_EOF'
[
{"id":"SEC-POSTURE-1","token":"sec-1","war_id":"sec-1","title":"Is the EKS cluster API server endpoint configured with private access enabled?","layer":"api-exposure","severity":"medium","source_file":"posture/cluster.json","governance":false,"recommendation":"Enable the private API endpoint (endpointPrivateAccess=true) so in-VPC clients and nodes do not leave the VPC."},
{"id":"SEC-POSTURE-2","token":"sec-2","war_id":"sec-2","title":"Is public API server access restricted to specific CIDR ranges rather than reachable from the whole internet?","layer":"api-exposure","severity":"high","source_file":"posture/cluster.json","governance":false,"recommendation":"Restrict publicAccessCidrs to known operator ranges, or turn the public endpoint off."},
{"id":"SEC-POSTURE-3","token":"sec-3","war_id":"sec-3","title":"Do you allow users to assume an IAM Role and map that role to a Kubernetes RBAC group, rather than creating individual user mappings in the aws-auth ConfigMap?","layer":"identity","severity":"medium","source_file":null,"governance":true,"recommendation":"Map IAM roles (not users) to Kubernetes groups, through access entries where possible."},
{"id":"SEC-POSTURE-4","token":"sec-5","war_id":"sec-5","title":"Do you use a dedicated IAM role to create EKS clusters that is not used for routine cluster operations or day-to-day management tasks?","layer":"identity","severity":"low","source_file":null,"governance":true,"recommendation":"Create clusters with a dedicated role that is not used for daily operations."},
{"id":"SEC-POSTURE-5","token":"sec-6","war_id":"sec-6","title":"Is pod-level workload identity (EKS Pod Identity or IRSA) configured for workloads that need AWS access?","layer":"identity","severity":"high","source_file":"posture/serviceaccounts.json, posture/cluster.json, posture/oidcproviders.json, posture/podidentity.json, posture/nodes.json, posture/daemonsets.json, posture/pods.json","governance":false,"recommendation":"Give workloads that call AWS their own role with EKS Pod Identity or IRSA instead of the node role."},
{"id":"SEC-POSTURE-6","token":"sec-7","war_id":"sec-7","title":"Do you restrict access to the kube-system namespace to super administrators only, preventing regular users from modifying critical cluster components?","layer":"privilege","severity":"medium","source_file":null,"governance":true,"recommendation":"Limit write access to kube-system to cluster administrators."},
{"id":"SEC-POSTURE-7","token":"sec-9","war_id":"sec-9","title":"Do non-system ClusterRoles avoid wildcard (star) resource and verb permissions?","layer":"privilege","severity":"medium","source_file":"posture/clusterroles.json","governance":false,"recommendation":"Replace wildcard verbs and resources in custom ClusterRoles with the specific ones needed."},
{"id":"SEC-POSTURE-8","token":"sec-17","war_id":"sec-17","title":"Is cluster access granted through EKS access entries (API authentication mode) rather than the legacy aws-auth ConfigMap?","layer":"identity","severity":"low","source_file":"posture/cluster.json","governance":false,"recommendation":"Move authenticationMode to API and grant access through EKS access entries."},
{"id":"SEC-POSTURE-9","token":"sec-18","war_id":"sec-18","title":"Is an OIDC provider configured for the EKS cluster to enable IRSA?","layer":"identity","severity":"high","source_file":"posture/cluster.json, posture/oidcproviders.json, posture/serviceaccounts.json","governance":false,"recommendation":"Register the IAM OIDC provider for the cluster issuer before relying on IRSA."},
{"id":"SEC-POSTURE-10","token":"rbac-1","war_id":"rbac-1","title":"Is cluster-admin restricted to the two built-in subjects expected to hold it?","layer":"privilege","severity":"high","source_file":"posture/clusterrolebindings.json, posture/awsauth.json, posture/cluster.json","governance":false,"recommendation":"Remove cluster-admin bindings other than Group system:masters and User eks:addon-manager, and any system:masters mapping in aws-auth."},
{"id":"SEC-POSTURE-11","token":"rbac-2","war_id":"rbac-2","title":"Do service accounts use namespace-scoped permissions (not cluster-wide)?","layer":"privilege","severity":"medium","source_file":"posture/rolebindings.json, posture/clusterrolebindings.json, posture/serviceaccounts.json","governance":false,"recommendation":"Bind workload service accounts with namespaced RoleBindings instead of ClusterRoleBindings."},
{"id":"SEC-POSTURE-12","token":"rbac-3","war_id":"rbac-3","title":"Are role bindings free of stale references to non-existent subjects?","layer":"privilege","severity":"medium","source_file":"posture/rolebindings.json, posture/serviceaccounts.json, posture/clusterrolebindings.json","governance":false,"recommendation":"Remove role binding subjects that no longer exist."},
{"id":"SEC-POSTURE-13","token":"rbac-4","war_id":"rbac-4","title":"Do default service accounts in non-system namespaces have automountServiceAccountToken disabled?","layer":"identity","severity":"medium","source_file":"posture/serviceaccounts.json, posture/pods.json","governance":false,"recommendation":"Set automountServiceAccountToken: false on each namespace default service account."},
{"id":"SEC-POSTURE-14","token":"sec-8","war_id":"sec-8","title":"Is an external secrets manager operator (e.g. External Secrets Operator) deployed on the cluster?","layer":"identity","severity":"low","source_file":"posture/deployments.json","governance":false,"recommendation":"Consider an external secrets operator so application credentials live in a managed store."},
{"id":"SEC-POSTURE-15","token":"sec-24","war_id":"sec-24","title":"Do you leverage AWS Secrets Manager and Config Provider (ASCP), EKS secrets encryption, or third-party solutions like HashiCorp Vault to manage secrets in EKS?","layer":"identity","severity":"medium","source_file":null,"governance":true,"recommendation":"Keep application credentials in AWS Secrets Manager (ASCP or an external secrets operator) rather than in manifests."},
{"id":"SEC-POSTURE-16","token":"sec-34","war_id":"sec-34","title":"Do you implement automatic rotation of secrets, credentials, and TLS certificates?","layer":"identity","severity":"medium","source_file":null,"governance":true,"recommendation":"Rotate credentials and TLS certificates automatically."},
{"id":"SEC-POSTURE-17","token":"sec-35","war_id":"sec-35","title":"Do you implement automatic rotation of secrets, credentials, database passwords, and TLS certificates used by your EKS workloads, using tools like AWS Secrets Manager, External Secrets Operator, or cert-manager?","layer":"identity","severity":"low","source_file":null,"governance":true,"recommendation":"Automate rotation for workload credentials, database passwords and certificates."},
{"id":"SEC-POSTURE-18","token":"sec-21","war_id":"sec-21","title":"Are EBS volumes used by the cluster encrypted at rest?","layer":"node-credential","severity":"high","source_file":"posture/volumes.json, posture/cluster.json, posture/pv.json, posture/nodes.json, posture/instances.json","governance":false,"recommendation":"Encrypt the EBS volumes this cluster uses (enable EBS encryption by default for the account and Region)."},
{"id":"SEC-POSTURE-19","token":"sec-38","war_id":"sec-38","title":"Is the cluster configured to envelope-encrypt Kubernetes Secrets with a customer-managed KMS key?","layer":"identity","severity":"high","source_file":"posture/cluster.json","governance":false,"recommendation":"Configure envelope encryption of Kubernetes Secrets with a customer-managed KMS key."},
{"id":"SEC-POSTURE-20","token":"sec-22","war_id":"sec-22","title":"Do you enable encryption at rest for Amazon EFS file systems used by Pods?","layer":"node-credential","severity":"medium","source_file":null,"governance":true,"recommendation":"Create EFS file systems used by pods with encryption at rest."},
{"id":"SEC-POSTURE-21","token":"sec-25","war_id":"sec-25","title":"Are StorageClasses configured with encryption enabled for new volumes?","layer":"node-credential","severity":"medium","source_file":"posture/storageclasses.json","governance":false,"recommendation":"Set encrypted: \"true\" on every EBS StorageClass."},
{"id":"SEC-POSTURE-22","token":"sec-23","war_id":"sec-23","title":"Do you enable encryption in transit for Amazon EFS when using the EFS CSI driver?","layer":"node-credential","severity":"low","source_file":null,"governance":true,"recommendation":"Mount EFS with encryption in transit (the EFS CSI driver tls mount option)."},
{"id":"SEC-POSTURE-23","token":"sec-27","war_id":"sec-27","title":"Is a service mesh control plane (Istio, Linkerd or Consul) deployed?","layer":"lateral-movement","severity":"low","source_file":"posture/deployments.json","governance":false,"recommendation":"Where zero-trust service-to-service traffic is required, deploy a service mesh control plane."},
{"id":"SEC-POSTURE-24","token":"sec-28","war_id":"sec-28","title":"Do workload pods carry a service-mesh sidecar (the data path for service-to-service mTLS)?","layer":"lateral-movement","severity":"low","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Inject mesh sidecars into workload pods where mTLS between services is required."},
{"id":"SEC-POSTURE-25","token":"sec-29","war_id":"sec-29","title":"Are Ingress resources configured with TLS termination?","layer":"api-exposure","severity":"high","source_file":"posture/ingresses.json","governance":false,"recommendation":"Terminate TLS on every Ingress (spec.tls, or an ALB certificate-arn with an HTTPS listener)."},
{"id":"SEC-POSTURE-26","token":"sec-4","war_id":"sec-4","title":"Are Kubernetes Network Policies deployed to control Pod-to-Pod traffic?","layer":"lateral-movement","severity":"high","source_file":"posture/networkpolicies.json, posture/namespaces.json, posture/daemonsets.json, posture/pods.json, posture/vpccniconfig.json, posture/nodeclasses.json, posture/nodes.json","governance":false,"recommendation":"Turn on NetworkPolicy enforcement (VPC CNI network policy agent, or the Auto Mode Network Policy Controller) and add policies to every workload namespace."},
{"id":"SEC-POSTURE-27","token":"sec-14","war_id":"sec-14","title":"Do you apply network separation to Pod networking using Kubernetes Network Policies or AWS security groups to control traffic between Pods and clusters?","layer":"lateral-movement","severity":"medium","source_file":null,"governance":true,"recommendation":"Separate pod traffic with NetworkPolicies or security groups for pods."},
{"id":"SEC-POSTURE-28","token":"sec-30","war_id":"sec-30","title":"Is inbound SSH (port 22) closed to the internet on the cluster security groups?","layer":"api-exposure","severity":"high","source_file":"posture/sg.json, posture/cluster.json, posture/nodes.json, posture/instances.json","governance":false,"recommendation":"Remove inbound port 22 from 0.0.0.0/0 and ::/0; use SSM Session Manager for node access."},
{"id":"SEC-POSTURE-29","token":"net-2","war_id":"net-2","title":"Do security groups follow least-privilege (no 0.0.0.0/0 on non-standard ports)?","layer":"api-exposure","severity":"high","source_file":"posture/sg.json, posture/cluster.json, posture/nodes.json, posture/instances.json","governance":false,"recommendation":"Remove world-open inbound rules outside TCP 80/443 from cluster and node security groups."},
{"id":"SEC-POSTURE-30","token":"lens-12","war_id":"lens-12","title":"Do ECR repositories have scan-on-push enabled?","layer":"supply-chain","severity":"medium","source_file":"posture/ecr.json, posture/pods.json","governance":false,"recommendation":"Scan the images this cluster pulls; configure registry-level scanning (see SEC-POSTURE-62)."},
{"id":"SEC-POSTURE-31","token":"lens-13","war_id":"lens-13","title":"Do ECR repositories use immutable image tags?","layer":"supply-chain","severity":"low","source_file":"posture/ecr.json, posture/pods.json","governance":false,"recommendation":"Set image tag mutability to IMMUTABLE on the repositories this cluster pulls from."},
{"id":"SEC-POSTURE-32","token":"net-4","war_id":"net-4","title":"Has the cluster security group's default allow-all egress been narrowed?","layer":"lateral-movement","severity":"medium","source_file":"posture/sg.json, posture/cluster.json","governance":false,"recommendation":"Narrow the cluster security group egress from all traffic to 0.0.0.0/0 to what the cluster needs."},
{"id":"SEC-POSTURE-33","token":"sec-10","war_id":"sec-10","title":"Is any non-AWS validating admission webhook deployed whose rules match Pod creation?","layer":"privilege","severity":"medium","source_file":"posture/validatingwebhooks.json, posture/mutatingwebhooks.json, posture/addons.json","governance":false,"recommendation":"Run a validating admission webhook (policy engine) that inspects pod creation."},
{"id":"SEC-POSTURE-34","token":"sec-11","war_id":"sec-11","title":"Are Pod Security Standards labels applied to namespaces to enforce security baselines?","layer":"privilege","severity":"high","source_file":"posture/namespaces.json, posture/pods.json","governance":false,"recommendation":"Label every workload namespace pod-security.kubernetes.io/enforce=baseline or restricted."},
{"id":"SEC-POSTURE-35","token":"sec-16","war_id":"sec-16","title":"Is a policy engine (Kyverno or Gatekeeper) deployed with at least one policy loaded?","layer":"privilege","severity":"medium","source_file":"posture/kyverno.json, posture/constraints.json, posture/constrainttemplates.json","governance":false,"recommendation":"Deploy a policy engine (Kyverno or Gatekeeper) with enforcing policies loaded."},
{"id":"SEC-POSTURE-36","token":"adm-1","war_id":"adm-1","title":"Are admission controller policies (Gatekeeper/Kyverno) deployed on the cluster?","layer":"privilege","severity":"medium","source_file":"posture/kyverno.json, posture/constraints.json, posture/constrainttemplates.json","governance":false,"recommendation":"Load admission policies covering the baseline Pod Security controls."},
{"id":"SEC-POSTURE-37","token":"adm-2","war_id":"adm-2","title":"Is an admission policy engine deployed with at least one policy loaded, which is where a privileged-container restriction would live (whether any loaded policy restricts privileged is reported, not scored)?","layer":"privilege","severity":"medium","source_file":"posture/kyverno.json, posture/constraints.json, posture/constrainttemplates.json","governance":false,"recommendation":"Load an enforcing policy that rejects privileged containers."},
{"id":"SEC-POSTURE-38","token":"adm-3","war_id":"adm-3","title":"Is an admission policy engine deployed with at least one policy loaded?","layer":"privilege","severity":"medium","source_file":"posture/kyverno.json, posture/constraints.json, posture/constrainttemplates.json","governance":false,"recommendation":"Run admission policies in enforce mode once audit results are clean."},
{"id":"SEC-POSTURE-39","token":"sec-12","war_id":"sec-12","title":"Are workload container images pinned to a digest or an explicit tag rather than :latest?","layer":"supply-chain","severity":"low","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Pin workload images to a digest or an explicit version tag, never :latest."},
{"id":"SEC-POSTURE-40","token":"sec-15","war_id":"sec-15","title":"Do containers have security contexts configured (runAsNonRoot, readOnlyRootFilesystem, or allowPrivilegeEscalation=false)?","layer":"privilege","severity":"medium","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Set a securityContext on every container (runAsNonRoot, readOnlyRootFilesystem, allowPrivilegeEscalation: false)."},
{"id":"SEC-POSTURE-41","token":"podsec-1","war_id":"podsec-1","title":"Do containers run as non-root users?","layer":"privilege","severity":"medium","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Run containers as non-root (runAsNonRoot: true and a non-zero runAsUser)."},
{"id":"SEC-POSTURE-42","token":"podsec-2","war_id":"podsec-2","title":"Are containers running without privileged mode?","layer":"privilege","severity":"high","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Remove privileged: true from workload containers."},
{"id":"SEC-POSTURE-43","token":"podsec-3","war_id":"podsec-3","title":"Are pods free of host path volume mounts?","layer":"privilege","severity":"medium","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Replace hostPath volumes with CSI or emptyDir volumes outside the system namespaces."},
{"id":"SEC-POSTURE-44","token":"podsec-4","war_id":"podsec-4","title":"Do containers add only the Linux capabilities the Pod Security Standards Baseline profile allows (no NET_ADMIN, SYS_ADMIN, SYS_MODULE, ALL)?","layer":"privilege","severity":"high","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Add only Baseline-allowed capabilities; drop NET_ADMIN, SYS_ADMIN and similar."},
{"id":"SEC-POSTURE-45","token":"podsec-5","war_id":"podsec-5","title":"Do containers drop ALL Linux capabilities?","layer":"privilege","severity":"medium","source_file":"posture/pods.json, posture/daemonsets.json","governance":false,"recommendation":"Drop ALL capabilities and add back only what each container needs."},
{"id":"SEC-POSTURE-46","token":"lens-11","war_id":"lens-11","title":"Do EC2 worker nodes enforce IMDSv2 (HttpTokens=required)?","layer":"node-credential","severity":"high","source_file":"posture/instances.json, posture/nodes.json","governance":false,"recommendation":"Require IMDSv2 (HttpTokens=required) on every node launch template or NodeClass."},
{"id":"SEC-POSTURE-47","token":"sec-32","war_id":"sec-32","title":"Do you implement container image signing and verification (Sigstore/Cosign, AWS Signer, Notary)?","layer":"supply-chain","severity":"low","source_file":null,"governance":true,"recommendation":"Sign images and verify signatures at admission."},
{"id":"SEC-POSTURE-48","token":"sec-33","war_id":"sec-33","title":"Is a runtime security monitoring agent present (GuardDuty Runtime Monitoring, Falco, Sysdig or Tetragon)?","layer":"detection","severity":"medium","source_file":"posture/addons.json, posture/pods.json","governance":false,"recommendation":"Run a runtime threat detection agent on every node (GuardDuty Runtime Monitoring or an equivalent)."},
{"id":"SEC-POSTURE-49","token":"sec-13","war_id":"sec-13","title":"Do you use separate EKS clusters for production and non-production environments, ideally in different AWS accounts?","layer":"identity","severity":"medium","source_file":null,"governance":true,"recommendation":"Run production and non-production on separate clusters, ideally in separate accounts."},
{"id":"SEC-POSTURE-50","token":"sec-19","war_id":"sec-19","title":"Do you leverage tools like kube-bench to automatically check whether EKS is deployed securely by running checks documented in the CIS Kubernetes Benchmark?","layer":"detection","severity":"medium","source_file":null,"governance":true,"recommendation":"Run CIS benchmark checks (for example kube-bench) on a schedule."},
{"id":"SEC-POSTURE-51","token":"sec-20","war_id":"sec-20","title":"Do you manage configuration changes through version control with pull request reviews and approvals before applying to clusters?","layer":"supply-chain","severity":"medium","source_file":null,"governance":true,"recommendation":"Change cluster configuration only through reviewed pull requests."},
{"id":"SEC-POSTURE-52","token":"sec-26","war_id":"sec-26","title":"Is Kubernetes audit logging enabled in the EKS control plane?","layer":"detection","severity":"high","source_file":"posture/cluster.json","governance":false,"recommendation":"Enable the audit control plane log type."},
{"id":"SEC-POSTURE-53","token":"sec-36","war_id":"sec-36","title":"Do you regularly scan your EKS cluster against compliance frameworks (CIS Benchmark, kube-bench)?","layer":"detection","severity":"low","source_file":null,"governance":true,"recommendation":"Scan the cluster against a compliance framework on a schedule."},
{"id":"SEC-POSTURE-54","token":"sec-37","war_id":"sec-37","title":"Do you regularly scan your EKS cluster configuration against compliance frameworks (CIS Kubernetes Benchmark, PCI-DSS, HIPAA, SOC 2) using automated tools like kube-bench, Prowler, or AWS Security Hub?","layer":"detection","severity":"low","source_file":null,"governance":true,"recommendation":"Automate configuration compliance scanning (kube-bench, Prowler or Security Hub)."},
{"id":"SEC-POSTURE-55","token":"SEC-POSTURE-55","war_id":null,"title":"Do node instances block pod access to the instance metadata service (IMDSv2 required with hop limit 1, per node type)?","layer":"node-credential","severity":"high","source_file":"posture/instances.json, posture/nodes.json","governance":false,"recommendation":"Set HttpTokens=required and HttpPutResponseHopLimit=1 in each launch template, managed node group template or Karpenter EC2NodeClass; give pods that need AWS access Pod Identity or IRSA."},
{"id":"SEC-POSTURE-56","token":"SEC-POSTURE-56","war_id":null,"title":"Does every workload namespace carry a default-deny ingress NetworkPolicy?","layer":"lateral-movement","severity":"high","source_file":"posture/networkpolicies.json, posture/namespaces.json","governance":false,"recommendation":"Add a NetworkPolicy with podSelector: {} and policyTypes: [Ingress] to every workload namespace, then allow the flows each service needs."},
{"id":"SEC-POSTURE-57","token":"SEC-POSTURE-57","war_id":null,"title":"Is pod egress limited by a NetworkPolicy in every workload namespace?","layer":"lateral-movement","severity":"medium","source_file":"posture/networkpolicies.json, posture/namespaces.json","governance":false,"recommendation":"Add a NetworkPolicy with podSelector: {} and policyTypes: [Egress] that allows DNS and the destinations each namespace needs."},
{"id":"SEC-POSTURE-58","token":"SEC-POSTURE-58","war_id":null,"title":"Are workload pods free of hostNetwork, hostPID and hostIPC outside the system namespaces?","layer":"privilege","severity":"high","source_file":"posture/pods.json","governance":false,"recommendation":"Remove hostNetwork, hostPID and hostIPC from workload pods; the Baseline Pod Security level rejects them."},
{"id":"SEC-POSTURE-59","token":"SEC-POSTURE-59","war_id":null,"title":"Is the control plane authenticator log enabled?","layer":"detection","severity":"medium","source_file":"posture/cluster.json","governance":false,"recommendation":"Enable the authenticator control plane log type alongside audit (re-state every type already enabled)."},
{"id":"SEC-POSTURE-60","token":"SEC-POSTURE-60","war_id":null,"title":"Is GuardDuty EKS Audit Log Monitoring enabled in this Region?","layer":"detection","severity":"medium","source_file":"posture/guardduty.json","governance":false,"recommendation":"Enable GuardDuty and its EKS Audit Log Monitoring feature (EKS_AUDIT_LOGS) in this account and Region."},
{"id":"SEC-POSTURE-61","token":"SEC-POSTURE-61","war_id":null,"title":"Is GuardDuty Runtime Monitoring enabled for EKS in this Region?","layer":"detection","severity":"medium","source_file":"posture/guardduty.json","governance":false,"recommendation":"Enable GuardDuty Runtime Monitoring with automated agent management for EKS (EKS_ADDON_MANAGEMENT)."},
{"id":"SEC-POSTURE-62","token":"SEC-POSTURE-62","war_id":null,"title":"Is ECR registry scanning enhanced, with continuous rescan of every repository?","layer":"supply-chain","severity":"medium","source_file":"posture/ecr-scanning.json","governance":false,"recommendation":"Set registry scanning to ENHANCED with a CONTINUOUS_SCAN rule whose filter covers the repositories this cluster pulls (for example *)."},
{"id":"SEC-POSTURE-63","token":"SEC-POSTURE-63","war_id":null,"title":"Are workload images referenced by immutable digest?","layer":"supply-chain","severity":"low","source_file":"posture/pods.json","governance":false,"recommendation":"Reference images as repo@sha256:<digest> (CI can resolve tags to digests at deploy time)."},
{"id":"SEC-POSTURE-64","token":"SEC-POSTURE-64","war_id":null,"title":"Is cluster-wide admin through an access policy held only by the expected principals (the roles named with --admin-allow)?","layer":"identity","severity":"high","source_file":"posture/accessentries.json, posture/cluster.json","governance":false,"recommendation":"For each failing principal, grant what it needs at a narrower scope (AmazonEKSAdminPolicy with a namespace access scope, or a Kubernetes group bound to a narrower RBAC role), then remove the cluster-wide grant: aws eks disassociate-access-policy --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN> --policy-arn arn:aws:eks::aws:cluster-access-policy/<the listed policy, AmazonEKSClusterAdminPolicy or AmazonEKSAdminPolicy>. Keep one break-glass admin role whose use is logged. Printed for review; nothing is changed."}
]
CATALOG_EOF
)

# Tokens: both files, one JSON value per line. A line that is not JSON is a broken scorer run.
TOK="$P/.reduce-tokens.$$"
: > "$TOK" || die internal "cannot write $TOK"
trap 'rm -f -- "$TOK" "$P/.posture.json.$$"' EXIT
for f in "$P/results.jsonl" "$P/results-extra.jsonl"; do
  [ -f "$f" ] || continue
  jq -c . "$f" >> "$TOK" 2>/dev/null || die bad_token "$(basename "$f") holds a line that is not JSON (an interrupted scorer run?); re-collect into a new work dir"
done
[ -s "$TOK" ] || die no_tokens "no tokens in $P/results.jsonl or $P/results-extra.jsonl; run posture_score.sh and posture_extra.sh"

CHECK=$(jq -rs --argjson cat "$CATALOG" '
  ([$cat[].token]) as $known
  | if any(.[]; (type!="object") or ((.id|type)!="string") or ((.state//"")|IN("all","most","some","none","na","unknown")|not) or ((.track//"")|IN("measured","governance")|not))
      then "bad_token\tA token is not an object with a string id, a legal state (all most some none na unknown) and a legal track (measured governance)"
    elif ((map(.id)|length) != (map(.id)|unique|length))
      then "duplicate_id\tDuplicate token id(s): \([group_by(.id)[]|select(length>1)|.[0].id]|join(", ")). A scorer was run twice into one work dir; re-collect into a new work dir"
    elif any(.[]; .id as $i|($known|index($i))==null)
      then "unknown_check\tToken id(s) the catalog does not know: \([.[]|.id as $i|select(($known|index($i))==null)|.id]|join(", "))"
    else "ok\t" end' "$TOK") || die internal "the token validation could not run"
case "$CHECK" in ok*) ;; *) die "${CHECK%%	*}" "${CHECK#*	}" ;; esac

CLUSTER_NAME=$(jq -r '.cluster.name // ""' "$P/cluster.json" 2>/dev/null)
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OUT="$WORK/posture.json"
jq -s --argjson cat "$CATALOG" --arg cl "$CLUSTER_NAME" --arg now "$NOW" '
  (map({key:.id,value:.})|from_entries) as $t
  | def res: {all:"pass",most:"fail",some:"fail",none:"fail",na:"na",unknown:"unknown"}[.];
    def pts: {all:100,most:75,some:50,none:0}[.];
    def wt: {high:3,medium:2,low:1}[.];
    def failing: (.resources.fail? // []) as $f | if ($f|length)==0 then "" else "; failing: "+($f[0:10]|join(", "))+(if ($f|length)>10 then " (+\(($f|length)-10) more)" else "" end) end;
  [ $cat[] | . as $c | ($t[$c.token] // null) as $k
    | (if $c.governance then "unknown" elif $k==null then "unknown" else $k.state end) as $st
    | {id:$c.id, war_id:$c.war_id, title:$c.title, result:($st|res), severity:$c.severity,
       evidence:(if $c.governance then "governance question: process only, not assessed from cluster data; confirm with the team"
                 elif $k==null then "no token: posture_score.sh or posture_extra.sh was not run for this check, so it was NOT measured"
                 else (($k.detail//"")+($k|failing)) end),
       source_file:$c.source_file, recommendation:$c.recommendation, layer:$c.layer, state:$st, gov:$c.governance} ] as $rows
  | [$rows[]|select(.gov|not)] as $m
  | [$m[]|select(.state|IN("all","most","some","none"))] as $ans
  | ($m|length) as $tot | ($ans|length) as $ac
  | (($ac*2) >= $tot and $tot>0) as $complete
  | {schema:"eks-security/posture@1", cluster:$cl, generated_at:$now,
     coverage:{checks_total:$tot, checks_answered:$ac, ratio:(if $tot==0 then 0 else ((($ac/$tot)*1000)|round/1000) end), gate:0.5, complete:$complete},
     score:(if $complete and $ac>0 then (($ans|map((.state|pts)*(.severity|wt))|add) / ($ans|map(.severity|wt)|add) | round) else null end),
     layers:[ ["node-credential","lateral-movement","privilege","identity","detection","api-exposure","supply-chain"][] as $l
       | [$m[]|select(.layer==$l and (.id|IN("SEC-POSTURE-18","SEC-POSTURE-19","SEC-POSTURE-21","SEC-POSTURE-25")|not))] as $q | [$q[]|select(.result=="pass" or .result=="fail")] as $a
       | {layer:$l, verdict:(if ($a|length)==0 then "unknown"
                             elif any($a[]; .result=="fail" and .severity=="high") then "not-contained"
                             elif all($a[]; .result=="pass") and (any($q[]; .result=="unknown")|not) then "contained"
                             else "partly" end)} ],
     checks:[$rows[]|del(.gov)] }' "$TOK" > "$P/.posture.json.$$" || die internal "the reduction failed (jq error above)"
mv -- "$P/.posture.json.$$" "$OUT" || die internal "could not write $OUT"
chmod 600 -- "$OUT" 2>/dev/null
jq -c --arg o "$OUT" '{ok:true,out:$o,complete:.coverage.complete,ratio:.coverage.ratio,score,layers:(.layers|map({(.layer):.verdict})|add)}' "$OUT"
if [ "$(jq -r '.coverage.complete' "$OUT")" = true ]; then exit 0; fi
echo "posture_reduce.sh: coverage $(jq -r '"\(.coverage.checks_answered)/\(.coverage.checks_total)"' "$OUT") is below the 0.5 gate; the score is withheld (null)" >&2
exit 3
