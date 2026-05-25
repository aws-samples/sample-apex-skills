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

echo "==> Step 1: Configuring kubectl..."
aws eks --region "$REGION" update-kubeconfig --name "$CLUSTER_NAME" 2>/dev/null || true

KUBECTL_OK=true
kubectl cluster-info 2>/dev/null || KUBECTL_OK=false

if [ "$KUBECTL_OK" = true ]; then
  echo "==> Step 2: Draining workloads (prevents orphaned AWS resources)..."

  echo "    Deleting planted manifests..."
  kubectl delete -f "$EXAMPLE_DIR/manifests/blocking-pdb.yaml" --ignore-not-found 2>/dev/null || true
  kubectl delete -f "$EXAMPLE_DIR/manifests/endpoints-watcher.yaml" --ignore-not-found 2>/dev/null || true

  echo "    Deleting all Ingresses (triggers ALB cleanup)..."
  kubectl delete ingress --all --all-namespaces --ignore-not-found 2>/dev/null || true

  echo "    Deleting all LoadBalancer Services (triggers NLB/CLB cleanup)..."
  kubectl delete svc --field-selector spec.type=LoadBalancer --all-namespaces --ignore-not-found 2>/dev/null || true

  echo "    Deleting all PVCs (triggers EBS/EFS cleanup)..."
  kubectl delete pvc --all --all-namespaces --ignore-not-found 2>/dev/null || true

  echo "    Waiting 30s for AWS resource cleanup (ALB Controller, CSI drivers)..."
  sleep 30

  echo "==> Step 3: Removing Karpenter K8s resources (triggers node termination)..."
  kubectl delete nodepools --all --ignore-not-found 2>/dev/null || true
  kubectl delete nodeclaims --all --ignore-not-found 2>/dev/null || true
  kubectl delete ec2nodeclasses --all --ignore-not-found 2>/dev/null || true
else
  echo "    kubectl unavailable — cluster may already be partially destroyed"
  echo "    Proceeding with AWS-side cleanup..."
fi

echo "==> Step 4: Terminating Karpenter EC2 instances via AWS API..."
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
  if [ $ELAPSED -ge 300 ]; then
    echo "    Timed out waiting — proceeding anyway"
  fi
else
  echo "    No Karpenter instances found"
fi

echo "==> Step 5: Running terraform destroy..."
NAME_SUFFIX="${CLUSTER_NAME#ex-karpenter-}"
terraform destroy -var="name_suffix=${NAME_SUFFIX}" --auto-approve

echo "==> Step 6: Post-destroy orphan check..."
echo "    Checking for orphaned resources tagged with ${CLUSTER_NAME}..."

ORPHAN_LBS=$(aws elbv2 describe-load-balancers --region "$REGION" \
  --query "LoadBalancers[].LoadBalancerArn" --output text 2>/dev/null || true)
TAGGED_LBS=""
if [ -n "$ORPHAN_LBS" ] && [ "$ORPHAN_LBS" != "None" ]; then
  for lb_arn in $ORPHAN_LBS; do
    TAGS=$(aws elbv2 describe-tags --region "$REGION" --resource-arns "$lb_arn" \
      --query "TagDescriptions[].Tags[?Key=='kubernetes.io/cluster/${CLUSTER_NAME}'].Value" \
      --output text 2>/dev/null || true)
    if [ -n "$TAGS" ] && [ "$TAGS" != "None" ]; then
      TAGGED_LBS="$TAGGED_LBS $lb_arn"
    fi
  done
fi

ORPHAN_VOLS=$(aws ec2 describe-volumes --region "$REGION" \
  --filters "Name=tag:kubernetes.io/cluster/${CLUSTER_NAME},Values=owned" \
            "Name=status,Values=available" \
  --query "Volumes[].VolumeId" --output text 2>/dev/null || true)

ORPHAN_SGS=$(aws ec2 describe-security-groups --region "$REGION" \
  --filters "Name=tag:kubernetes.io/cluster/${CLUSTER_NAME},Values=owned" \
  --query "SecurityGroups[].GroupId" --output text 2>/dev/null || true)

HAS_ORPHANS=false
if [ -n "$TAGGED_LBS" ] && [ "$TAGGED_LBS" != " " ]; then
  echo "    WARNING: Orphaned Load Balancers:${TAGGED_LBS}"
  HAS_ORPHANS=true
fi
if [ -n "$ORPHAN_VOLS" ] && [ "$ORPHAN_VOLS" != "None" ]; then
  echo "    WARNING: Orphaned EBS Volumes: ${ORPHAN_VOLS}"
  HAS_ORPHANS=true
fi
if [ -n "$ORPHAN_SGS" ] && [ "$ORPHAN_SGS" != "None" ]; then
  echo "    WARNING: Orphaned Security Groups: ${ORPHAN_SGS}"
  HAS_ORPHANS=true
fi

if [ "$HAS_ORPHANS" = false ]; then
  echo "    No orphaned resources detected"
fi

echo ""
echo "Cleanup complete: ${CLUSTER_NAME} destroyed."
