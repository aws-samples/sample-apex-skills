#!/usr/bin/env bash
set -euo pipefail

#######################################################################
# deploy.sh
#
# Deploy script for the in-place EKS upgrade example (Istio).
#
# What it does:
#   1. Setup APEX EKS (Claude Code or Kiro — user selects)
#   2. Clone istio-on-eks into tmp/
#   3. Copy sidecar blueprint to a named directory (for parallel runs)
#   4. Pin EKS to 1.32 and Istio to 1.23.x
#   5. Deploy EKS cluster with Istio via Terraform
#   6. Enable sidecar injection and deploy sample workloads
#   7. Plant upgrade issue manifests
#
# Parallel deployments:
#   The cluster name is derived from the directory name:
#     istio-cc   → cluster "ex-istio-cc"
#     istio-kiro → cluster "ex-istio-kiro"
#   Each deployment has its own Terraform state and cluster.
#   Run deploy.sh twice (once per tool) for side-by-side testing.
#
# Safety:
#   - Will NOT overwrite if Terraform state already exists for the name
#   - Ctrl+C warns about partial state and how to clean up
#
# Usage: ./scripts/deploy.sh
#######################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

INPLACE_DIR="$(pwd)"

# Ctrl+C handler — warn about partial state
trap 'echo ""; echo "⚠  Interrupted! If terraform apply already started, infrastructure may exist in AWS."; echo "   Run ./scripts/destroy.sh to clean up."; echo "   DO NOT delete the tmp/ directory — it contains Terraform state needed for cleanup."; exit 130' INT TERM

# --- APEX EKS Setup ---

echo ""
echo "Which tool are you using?"
echo "  [1] Claude Code"
echo "  [2] Kiro IDE / Kiro CLI"
echo ""
read -rp "> " TOOL_CHOICE

case "$TOOL_CHOICE" in
  1)
    DEFAULT_SUFFIX="cc"
    echo ""
    echo "Setting up APEX EKS for Claude Code..."
    # Skills — symlink into .claude/skills/
    mkdir -p ../../../.claude/skills
    for skill in ../../../skills/*/; do
      name=$(basename "$skill")
      ln -sfn "../../skills/$name" "../../../.claude/skills/$name"
    done
    # Commands — symlink steering commands into .claude/commands/
    mkdir -p ../../../.claude/commands
    ln -sfn ../../steering/commands/apex ../../../.claude/commands/apex
    echo "✓ Claude Code skills and commands configured"
    ;;
  2)
    DEFAULT_SUFFIX="kiro"
    echo ""
    echo "Setting up APEX EKS for Kiro..."
    # Skills — symlink into .kiro/skills/
    mkdir -p ../../../.kiro/skills
    for skill in ../../../skills/*/; do
      name=$(basename "$skill")
      ln -sfn "../../skills/$name" "../../../.kiro/skills/$name"
    done
    # Steering — copy for Kiro IDE slash commands
    mkdir -p ../../../.kiro/steering
    cp ../../../steering/eks.md ../../../.kiro/steering/eks.md
    echo "✓ Kiro skills and steering configured"
    ;;
  *)
    echo "Invalid choice. Please enter 1 or 2."
    exit 1
    ;;
esac

# --- Deployment Name ---

echo ""
echo "Deployment name (used for cluster isolation)."
echo "  Cluster will be named: ex-istio-<name>"
echo "  Default: ${DEFAULT_SUFFIX}"
echo ""
read -rp "Name [${DEFAULT_SUFFIX}]: " DEPLOY_SUFFIX
DEPLOY_SUFFIX="${DEPLOY_SUFFIX:-$DEFAULT_SUFFIX}"

# Validate: alphanumeric and hyphens only, reasonable length
if [[ ! "$DEPLOY_SUFFIX" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "ERROR: Name must be lowercase alphanumeric with optional hyphens (e.g. cc, kiro, test-1)"
  exit 1
fi

DEPLOY_DIR="istio-${DEPLOY_SUFFIX}"
TERRAFORM_DIR="${INPLACE_DIR}/tmp/istio-on-eks/terraform-blueprint/${DEPLOY_DIR}"

echo ""
echo "→ Cluster name will be: ex-${DEPLOY_DIR}"
echo "→ Terraform dir: tmp/istio-on-eks/terraform-blueprint/${DEPLOY_DIR}"
echo ""

# --- Step 1: Deploy Base Cluster (EKS 1.32 + Istio 1.25.x) ---

# Safety check: don't overwrite existing Terraform state
if [ -f "${TERRAFORM_DIR}/terraform.tfstate" ] || [ -d "${TERRAFORM_DIR}/.terraform" ]; then
  echo "ERROR: Terraform state already exists for '${DEPLOY_SUFFIX}'. A cluster may be running."
  echo "       Run ./scripts/destroy.sh to clean up first."
  exit 1
fi

mkdir -p tmp

# Only clone if not already cloned (supports re-running and multiple deployments)
if [ ! -d "tmp/istio-on-eks" ]; then
  git clone https://github.com/aws-samples/istio-on-eks.git tmp/istio-on-eks
fi

# Copy the sidecar blueprint to the named directory
BLUEPRINT_SRC="${INPLACE_DIR}/tmp/istio-on-eks/terraform-blueprint/sidecar"
if [ ! -d "$BLUEPRINT_SRC" ]; then
  echo "ERROR: Sidecar blueprint not found at ${BLUEPRINT_SRC}"
  exit 1
fi
cp -r "$BLUEPRINT_SRC" "$TERRAFORM_DIR"

cd "$TERRAFORM_DIR"

# Pin cluster version to 1.32
sed -i 's/cluster_version\s*=\s*"[0-9.]*"/cluster_version = "1.32"/' main.tf
grep -q 'cluster_version = "1.32"' main.tf || { echo "ERROR: Could not pin cluster version to 1.32 in main.tf"; exit 1; }

# Pin Istio chart version to 1.25.2 (supports K8s 1.29-1.32 but NOT 1.33 — forces Istio upgrade before EKS upgrade)
sed -i 's/istio_chart_version\s*=\s*"[0-9.]*"/istio_chart_version = "1.25.2"/' main.tf
grep -q 'istio_chart_version = "1.25.2"' main.tf || { echo "ERROR: Could not pin Istio chart version to 1.25.2 in main.tf"; exit 1; }

# Set cluster name to ex-istio-<suffix> instead of using the directory name
sed -i "s|name\s*=\s*basename(path.cwd)|name   = \"ex-${DEPLOY_DIR}\"|" main.tf

terraform init
terraform apply --auto-approve
$(terraform output -raw configure_kubectl)

# --- Step 2: Enable Sidecar Injection and Deploy Workloads ---

echo ""
echo "→ Enabling sidecar injection on default namespace..."
kubectl label namespace default istio-injection=enabled --overwrite

echo "→ Deploying sample workload with Istio sidecar..."
kubectl apply -f - <<'WORKLOAD'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sample-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sample-app
  template:
    metadata:
      labels:
        app: sample-app
    spec:
      containers:
      - name: app
        image: nginx:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: sample-app
  namespace: default
spec:
  selector:
    app: sample-app
  ports:
  - port: 80
    targetPort: 80
WORKLOAD

echo "→ Waiting for sample-app pods to be ready..."
kubectl rollout status deployment/sample-app -n default --timeout=120s

# Verify sidecars are injected
echo "→ Verifying Istio sidecar injection..."
SIDECAR_COUNT=$(kubectl get pods -n default -l app=sample-app -o jsonpath='{range .items[*]}{.spec.containers[*].name}{"\n"}{end}' | grep -c istio-proxy || true)
if [ "$SIDECAR_COUNT" -gt 0 ]; then
  echo "✓ Istio sidecars injected (${SIDECAR_COUNT} proxies running)"
else
  echo "⚠  Sidecars may not be injected yet. Pods may need a restart after Istio finishes initializing."
fi

# --- Step 3: Plant Issues ---

cd "$INPLACE_DIR"
echo ""
echo "→ Planting upgrade issues..."

kubectl apply -f manifests/envoyfilter-metrics.yaml
echo "  ✓ EnvoyFilter (deprecated metrics customization)"

# Scale the ingress gateway to 1 replica (simulates the common oversight)
kubectl scale deployment istio-ingress -n istio-ingress --replicas=1 2>/dev/null || true
# Delete any existing PDB on the ingress gateway
kubectl delete pdb -n istio-ingress --all --ignore-not-found 2>/dev/null || true
echo "  ✓ Single-replica ingress gateway (no PDB)"

kubectl apply -f manifests/label-conflict.yaml
echo "  ✓ Namespace with conflicting injection labels"

# Wait for the conflicting-labels workload to deploy
kubectl rollout status deployment/httpbin -n conflicting-labels --timeout=60s 2>/dev/null || true

echo ""
echo "✅ Deploy complete. Cluster 'ex-${DEPLOY_DIR}' is ready for upgrade exercise."
echo "   EKS version: 1.32 — upgrade target: 1.33"
echo "   Istio version: 1.25.2 — does NOT support K8s 1.33, must upgrade to 1.26.x first"
echo ""
echo "   Planted issues (4):"
echo "     1. Istio 1.25 does not support K8s 1.33 (must upgrade Istio first)"
echo "     2. EnvoyFilter with deprecated metrics customization"
echo "     3. Single-replica ingress gateway (no PDB)"
echo "     4. Namespace with conflicting Istio injection labels"
echo ""
case "$TOOL_CHOICE" in
  1) echo "   Run: claude" ;;
  2) echo "   Run: kiro-cli chat" ;;
esac
echo ""
echo "   To destroy: ./scripts/destroy.sh"
