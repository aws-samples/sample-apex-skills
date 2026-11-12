#!/usr/bin/env bash
# Bootstrap the read-only artefacts for misc/evals/ task-axis runs and the
# "Read-only operating profile" recipe (misc/website/docs/read-only-operating-profile.md).
#
# What this creates:
#   1. In the cluster pointed at by your current KUBECONFIG:
#        - ServiceAccount kube-system/evals-readonly
#        - ClusterRole / ClusterRoleBinding evals-readonly (get/list/watch, no Secrets)
#        - Secret kube-system/evals-readonly-token (SA-bound token)
#   2. In misc/evals/.secrets/ (gitignored):
#        - kubeconfig.readonly   — auths as the SA; read-only
#        - readonly-session-policy.json — IAM session policy the runner
#                                         uses when minting an STS federation
#                                         token for the subject subprocess
#
# Both outputs are generated from the checked-in declarative sources under
# misc/evals/setup/ — no secret material is ever committed.
#
# Idempotent: re-running leaves the SA, bindings and token unchanged and picks
# up a new cluster endpoint. To rotate the token:
# `kubectl -n kube-system delete secret evals-readonly-token`, then re-run this
# script. Exit non-zero on any step so CI wrappers can gate on it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVALS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SECRETS_DIR="${EVALS_ROOT}/.secrets"

RBAC_YAML="${SCRIPT_DIR}/readonly-rbac.yaml"
POLICY_JSON="${SCRIPT_DIR}/readonly-session-policy.json"

log() { printf '[bootstrap-readonly] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

command -v kubectl >/dev/null || die "kubectl not found in PATH"
command -v aws >/dev/null || die "aws CLI not found in PATH"

CURRENT_CTX="$(kubectl config current-context 2>/dev/null || true)"
[[ -n "${CURRENT_CTX}" ]] || die "no kubectl current-context; point KUBECONFIG at the target cluster first"

log "current kubectl context: ${CURRENT_CTX}"
log "applying RBAC (idempotent)..."
kubectl apply -f "${RBAC_YAML}" >&2

# Wait for the controller to populate the token field on the Secret.
# Practically this is <1s, but we shouldn't assume.
log "waiting for SA token to be populated..."
for i in {1..30}; do
  if kubectl get secret -n kube-system evals-readonly-token -o jsonpath='{.data.token}' 2>/dev/null | grep -q .; then
    break
  fi
  sleep 1
  [[ $i -eq 30 ]] && die "evals-readonly-token never got populated (is this cluster running a token controller?)"
done

TOKEN="$(kubectl get secret -n kube-system evals-readonly-token -o jsonpath='{.data.token}' | base64 -d)"
[[ -n "${TOKEN}" ]] || die "decoded SA token was empty"

# Cluster endpoint + CA — pulled from whatever cluster the current kubeconfig
# has as current-context. Works for EKS, GKE, AKS, or any other
# kubeconfig-accessible cluster; nothing here is EKS-specific.
CLUSTER_NAME="$(kubectl config view --minify -o jsonpath='{.contexts[0].context.cluster}')"
CLUSTER_API="$(kubectl config view --minify --flatten -o jsonpath='{.clusters[0].cluster.server}')"
CA_DATA="$(kubectl config view --minify --flatten -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"

[[ -n "${CLUSTER_API}" ]] || die "could not read cluster server endpoint from kubeconfig"
[[ -n "${CA_DATA}" ]] || die "could not read cluster CA data (inline CA required; path-based CA not supported)"

mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

KUBECONFIG_OUT="${SECRETS_DIR}/kubeconfig.readonly"
umask 077
cat > "${KUBECONFIG_OUT}" <<EOF
apiVersion: v1
kind: Config
clusters:
- name: eks-readonly
  cluster:
    server: ${CLUSTER_API}
    certificate-authority-data: ${CA_DATA}
contexts:
- name: evals-readonly
  context:
    cluster: eks-readonly
    user: evals-readonly
    namespace: default
current-context: evals-readonly
users:
- name: evals-readonly
  user:
    token: ${TOKEN}
EOF
chmod 600 "${KUBECONFIG_OUT}"
log "wrote ${KUBECONFIG_OUT}"

# The session policy is static — copy it into .secrets/ so the Makefile
# defaults find it in the same place as the kubeconfig. Copying instead of
# symlinking keeps the .secrets/ directory self-contained if someone moves
# the repo.
POLICY_OUT="${SECRETS_DIR}/readonly-session-policy.json"
cp "${POLICY_JSON}" "${POLICY_OUT}"
chmod 600 "${POLICY_OUT}"
log "wrote ${POLICY_OUT}"

# Sanity-check the kubeconfig actually works and actually denies writes.
log "verifying read access..."
KUBECONFIG="${KUBECONFIG_OUT}" kubectl get nodes --request-timeout=10s >/dev/null 2>&1 \
  || die "readonly kubeconfig cannot list nodes — check cluster reachability from this host"

log "verifying write denial..."
if KUBECONFIG="${KUBECONFIG_OUT}" kubectl auth can-i create pods --all-namespaces 2>&1 | grep -qx yes; then
  die "readonly kubeconfig is allowed to CREATE pods — RBAC binding is wrong"
fi

log "verifying Secret denial..."
if KUBECONFIG="${KUBECONFIG_OUT}" kubectl auth can-i list secrets --all-namespaces 2>&1 | grep -qx yes; then
  die "readonly kubeconfig is allowed to LIST secrets; another binding grants this ServiceAccount or its groups secrets"
fi

# The apex-run session tag labels the minted session in CloudTrail.
log "verifying AWS federation-token minting..."
if ! aws sts get-federation-token \
       --name "evals-readonly-bootstrap-check" \
       --policy "file://${POLICY_OUT}" \
       --duration-seconds 900 \
       --tags "Key=apex-run,Value=$(date -u +%Y%m%dT%H%M%SZ)-$$" \
       --output text --query Credentials.AccessKeyId >/dev/null 2>&1; then
  die "aws sts get-federation-token failed; it needs IAM-user long-term credentials with sts:GetFederationToken (a role or Identity Center session cannot call it) and sts:TagSession; the kubeconfig above is written and usable"
fi

log "done. both artefacts are in ${SECRETS_DIR}/ (gitignored)."
log "you can now run: make task-eks-recon INCLUDE_LIVE_ONLY=1 (or task-eks-operation-review)"
