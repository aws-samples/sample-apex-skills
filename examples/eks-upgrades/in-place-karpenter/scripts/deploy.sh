#!/usr/bin/env bash
set -euo pipefail

#######################################################################
# deploy.sh
#
# Deploy script for the in-place EKS upgrade example.
#
# What it does:
#   1. Setup APEX EKS (Claude Code or Kiro — user selects)
#   2. Clone terraform-aws-eks-blueprints into tmp/
#   3. Copy Karpenter pattern to a named directory (for parallel runs)
#   4. Deploy EKS 1.32 cluster with Karpenter pattern
#   5. Apply Karpenter resources and example workload
#   6. Plant upgrade issue manifests
#
# Parallel deployments:
#   The cluster name is derived from the directory name:
#     karpenter-cc   → cluster "ex-karpenter-cc"
#     karpenter-kiro → cluster "ex-karpenter-kiro"
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
echo "  Cluster will be named: ex-karpenter-<name>"
echo "  Default: ${DEFAULT_SUFFIX}"
echo ""
read -rp "Name [${DEFAULT_SUFFIX}]: " DEPLOY_SUFFIX
DEPLOY_SUFFIX="${DEPLOY_SUFFIX:-$DEFAULT_SUFFIX}"

# Validate: alphanumeric and hyphens only, reasonable length
if [[ ! "$DEPLOY_SUFFIX" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "ERROR: Name must be lowercase alphanumeric with optional hyphens (e.g. cc, kiro, test-1)"
  exit 1
fi

DEPLOY_DIR="karpenter-${DEPLOY_SUFFIX}"
TERRAFORM_DIR="${INPLACE_DIR}/tmp/terraform-aws-eks-blueprints/patterns/${DEPLOY_DIR}"

echo ""
echo "→ Cluster name will be: ex-${DEPLOY_DIR}"
echo "→ Terraform dir: tmp/terraform-aws-eks-blueprints/patterns/${DEPLOY_DIR}"
echo ""

# --- Step 1: Deploy Base Cluster (EKS 1.32) ---

# Safety check: don't overwrite existing Terraform state
if [ -f "${TERRAFORM_DIR}/terraform.tfstate" ] || [ -d "${TERRAFORM_DIR}/.terraform" ]; then
  echo "ERROR: Terraform state already exists for '${DEPLOY_SUFFIX}'. A cluster may be running."
  echo "       Run ./scripts/destroy.sh to clean up first."
  exit 1
fi

mkdir -p tmp

# Only clone if not already cloned (supports re-running and multiple deployments)
if [ ! -d "tmp/terraform-aws-eks-blueprints" ]; then
  git clone https://github.com/aws-ia/terraform-aws-eks-blueprints.git tmp/terraform-aws-eks-blueprints
fi

# Copy the pattern to the named directory
PATTERN_SRC="${INPLACE_DIR}/tmp/terraform-aws-eks-blueprints/patterns/karpenter"
if [ ! -d "$PATTERN_SRC" ]; then
  echo "ERROR: Karpenter pattern not found at ${PATTERN_SRC}"
  exit 1
fi
cp -r "$PATTERN_SRC" "$TERRAFORM_DIR"

cd "$TERRAFORM_DIR"

# Pin cluster version to 1.32
sed -i 's/cluster_version = "[0-9.]*"/cluster_version = "1.32"/' eks.tf
grep -q 'cluster_version = "1.32"' eks.tf || { echo "ERROR: Could not pin cluster version to 1.32 in eks.tf"; exit 1; }

terraform init
terraform apply --auto-approve
$(terraform output -raw configure_kubectl)

# Patch karpenter.yaml with actual cluster name
sed -i "s/ex-karpenter/ex-${DEPLOY_DIR}/g" karpenter.yaml

# Setup Karpenter and example workload
kubectl apply --server-side -f karpenter.yaml
kubectl apply --server-side -f example.yaml
kubectl scale deployment inflate --replicas=3

# --- Step 2: Plant Issues ---

cd "$INPLACE_DIR"
kubectl apply -f manifests/blocking-pdb.yaml
kubectl apply -f manifests/endpoints-watcher.yaml

echo ""
echo "✅ Deploy complete. Cluster 'ex-${DEPLOY_DIR}' is ready for upgrade exercise."
echo "   EKS version: 1.32 — upgrade target: 1.33"
echo ""
case "$TOOL_CHOICE" in
  1) echo "   Run: claude" ;;
  2) echo "   Run: kiro-cli chat" ;;
esac
echo ""
echo "   To destroy: ./scripts/destroy.sh"
