#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE_DIR="$SCRIPT_DIR/.."
TERRAFORM_DIR="$EXAMPLE_DIR/../../infrastructure/karpenter"

trap 'echo ""; echo "Interrupted! Terraform state preserved."; echo "Re-run ./scripts/destroy.sh to continue cleanup."; exit 130' INT TERM

cd "$TERRAFORM_DIR"

CLUSTER_NAME=$(terraform output -raw cluster_name 2>/dev/null || echo "")
REGION=$(terraform output -raw region 2>/dev/null || echo "us-west-2")

if [ -z "$CLUSTER_NAME" ]; then
  echo "No Terraform state found. Nothing to destroy."
  exit 0
fi

echo "Destroying cluster: ${CLUSTER_NAME} in ${REGION}"
echo ""

echo "==> Configuring kubectl..."
aws eks --region "$REGION" update-kubeconfig --name "$CLUSTER_NAME" 2>/dev/null || true

echo "==> Deleting planted manifests..."
kubectl delete -f "$EXAMPLE_DIR/manifests/blocking-pdb.yaml" --ignore-not-found 2>/dev/null || true
kubectl delete -f "$EXAMPLE_DIR/manifests/endpoints-watcher.yaml" --ignore-not-found 2>/dev/null || true

echo "==> Terminating Karpenter EC2 instances..."
INSTANCE_IDS=$(aws ec2 describe-instances \
  --region "$REGION" \
  --filters "Name=tag:karpenter.sh/discovery,Values=${CLUSTER_NAME}" \
            "Name=instance-state-name,Values=running,pending,stopping,stopped" \
  --query "Reservations[].Instances[].InstanceId" --output text 2>/dev/null || true)

if [ -n "$INSTANCE_IDS" ] && [ "$INSTANCE_IDS" != "None" ]; then
  INSTANCE_COUNT=$(echo "$INSTANCE_IDS" | wc -w)
  echo "    Terminating ${INSTANCE_COUNT} instance(s)..."
  aws ec2 terminate-instances --region "$REGION" --instance-ids $INSTANCE_IDS > /dev/null 2>&1 || true

  echo "    Waiting for instances to terminate..."
  ELAPSED=0
  while [ $ELAPSED -lt 300 ]; do
    RUNNING=$(aws ec2 describe-instances \
      --region "$REGION" \
      --filters "Name=tag:karpenter.sh/discovery,Values=${CLUSTER_NAME}" \
                "Name=instance-state-name,Values=running,pending,stopping,stopped,shutting-down" \
      --query "Reservations[].Instances[].InstanceId" --output text 2>/dev/null || true)
    if [ -z "$RUNNING" ] || [ "$RUNNING" = "None" ]; then
      echo "    All instances terminated"
      break
    fi
    sleep 15
    ELAPSED=$((ELAPSED + 15))
  done
else
  echo "    No Karpenter instances found"
fi

echo "==> Deleting Karpenter K8s resources..."
kubectl delete nodepools --all --ignore-not-found 2>/dev/null || true
kubectl delete nodeclaims --all --ignore-not-found 2>/dev/null || true
kubectl delete ec2nodeclasses --all --ignore-not-found 2>/dev/null || true

echo "==> Running terraform destroy..."
NAME_SUFFIX="${CLUSTER_NAME#ex-karpenter-}"
terraform destroy -var="name_suffix=${NAME_SUFFIX}" --auto-approve

echo ""
echo "Cleanup complete: ${CLUSTER_NAME} destroyed."
