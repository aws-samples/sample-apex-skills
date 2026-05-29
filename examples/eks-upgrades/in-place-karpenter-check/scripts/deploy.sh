#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE_DIR="$SCRIPT_DIR/.."
REPO_ROOT="$(cd "$EXAMPLE_DIR/../../.." && pwd)"
TERRAFORM_DIR="$EXAMPLE_DIR/../../infrastructure/karpenter"

trap 'echo ""; echo "Interrupted! If terraform apply already started, infrastructure may exist."; echo "Run ./scripts/destroy.sh to clean up."; exit 130' INT TERM

echo ""
echo "Which tool are you using?"
echo "  [1] Claude Code"
echo "  [2] Kiro IDE / Kiro CLI"
echo ""
read -rp "> " TOOL_CHOICE

case "$TOOL_CHOICE" in
  1)
    DEFAULT_SUFFIX="check"
    echo ""
    echo "Setting up APEX EKS for Claude Code..."
    mkdir -p "$REPO_ROOT/.claude/skills"
    for skill in "$REPO_ROOT/skills"/*/; do
      name=$(basename "$skill")
      ln -sfn "../../skills/$name" "$REPO_ROOT/.claude/skills/$name"
    done
    mkdir -p "$REPO_ROOT/.claude/commands"
    ln -sfn ../../steering/commands/apex "$REPO_ROOT/.claude/commands/apex"
    echo "Done: Claude Code skills and commands configured"
    ;;
  2)
    DEFAULT_SUFFIX="check"
    echo ""
    echo "Setting up APEX EKS for Kiro..."
    mkdir -p "$REPO_ROOT/.kiro/skills"
    for skill in "$REPO_ROOT/skills"/*/; do
      name=$(basename "$skill")
      ln -sfn "../../skills/$name" "$REPO_ROOT/.kiro/skills/$name"
    done
    mkdir -p "$REPO_ROOT/.kiro/steering"
    cp "$REPO_ROOT/steering/eks.md" "$REPO_ROOT/.kiro/steering/eks.md"
    echo "Done: Kiro skills and steering configured"
    ;;
  *)
    echo "Invalid choice. Please enter 1 or 2."
    exit 1
    ;;
esac

echo ""
echo "Deployment name suffix (cluster will be: ex-karpenter-<suffix>)"
echo "  Default: ${DEFAULT_SUFFIX}"
echo ""
read -rp "Name [${DEFAULT_SUFFIX}]: " DEPLOY_SUFFIX
DEPLOY_SUFFIX="${DEPLOY_SUFFIX:-$DEFAULT_SUFFIX}"

if [[ ! "$DEPLOY_SUFFIX" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "ERROR: Name must be lowercase alphanumeric with optional hyphens"
  exit 1
fi

echo ""
echo "Cluster name: ex-karpenter-${DEPLOY_SUFFIX}"
echo "Terraform dir: $(cd "$TERRAFORM_DIR" && pwd)"
echo ""

cd "$TERRAFORM_DIR"
terraform init
terraform apply -var="name_suffix=${DEPLOY_SUFFIX}" --auto-approve

CLUSTER_NAME=$(terraform output -raw cluster_name)
REGION=$(terraform output -raw region)

echo ""
echo "Configuring kubectl..."
aws eks --region "$REGION" update-kubeconfig --name "$CLUSTER_NAME"

echo "Waiting for Fargate profile to activate..."
aws eks wait fargate-profile-active --cluster-name "$CLUSTER_NAME" --fargate-profile-name karpenter --region "$REGION" 2>/dev/null || true

echo "Bouncing system pods if stuck in Pending (Fargate race condition)..."
kubectl delete pods -n karpenter --field-selector=status.phase=Pending 2>/dev/null || true
kubectl delete pods -n kube-system -l k8s-app=kube-dns --field-selector=status.phase=Pending 2>/dev/null || true

echo "Waiting for Karpenter to become ready..."
kubectl wait -n karpenter deployment/karpenter --for=condition=Available --timeout=300s

echo "Applying Karpenter resources..."
KARPENTER_MANIFESTS=$(terraform output -raw karpenter_manifests_path)
kubectl apply --server-side -f "$KARPENTER_MANIFESTS"

echo "Applying example workload..."
kubectl apply --server-side -f example.yaml
kubectl scale deployment inflate --replicas=3

echo "Planting upgrade issues..."
kubectl apply -f "$EXAMPLE_DIR/manifests/blocking-pdb.yaml"
kubectl apply -f "$EXAMPLE_DIR/manifests/endpoints-watcher.yaml"

echo ""
echo "Deploy complete!"
echo "  Cluster: ${CLUSTER_NAME} (EKS 1.32)"
echo "  Target upgrade version: 1.33"
echo "  Karpenter: v1.0.2 (incompatible with 1.33 — requires >= 1.5)"
echo ""
echo "Run the upgrade readiness check:"
case "$TOOL_CHOICE" in
  1) echo "  cd $REPO_ROOT && claude"
     echo "  Then: /apex:eks-upgrade-check"
     echo "  Or ask: \"Is my cluster ready to upgrade to 1.33?\""
     ;;
  2) echo "  cd $REPO_ROOT && kiro-cli chat"
     echo "  Then ask: \"Is my cluster ready to upgrade to 1.33?\""
     ;;
esac
echo ""
echo "To destroy: ./scripts/destroy.sh"
