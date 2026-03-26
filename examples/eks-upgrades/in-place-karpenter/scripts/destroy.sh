#!/usr/bin/env bash
set -euo pipefail

#######################################################################
# destroy.sh
#
# Cleanup script for the in-place EKS upgrade example.
#
# Auto-discovers deployments under tmp/terraform-aws-eks-blueprints/
# patterns/karpenter-*/ and asks which one to destroy.
#
# Destroy order:
#   1. Get cluster info (from Terraform state or AWS discovery)
#   2. Delete planted issue manifests
#   3. Terminate Karpenter EC2 instances via AWS API (fire and forget)
#   4. Delete Karpenter K8s resources (NodePools, NodeClaims, EC2NodeClasses)
#   5. Delete example workloads
#   6. Wait for EC2 instances to finish terminating
#   7. Terraform destroy
#   8. Clean up deployment directory (only after successful destroy)
#
# Safety:
#   - Ctrl+C will NOT delete tmp/ — Terraform state is preserved
#   - If tmp/ is missing but cluster exists, offers recovery options
#   - Deployment dir only deleted after terraform destroy succeeds
#
# Usage: ./scripts/destroy.sh
#######################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

INPLACE_DIR="$(pwd)"
PATTERNS_BASE="${INPLACE_DIR}/tmp/terraform-aws-eks-blueprints/patterns"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Timeouts
NODE_WAIT_TIMEOUT=300  # 5 minutes for instances to terminate

log_step() { echo -e "\n${BLUE}${BOLD}=== Step $1: $2 ===${NC}\n"; }
log_info() { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}"; }
log_debug() { echo -e "${CYAN}  → $1${NC}"; }

# Ctrl+C handler — preserve Terraform state
trap 'echo ""; echo -e "${YELLOW}⚠  Interrupted! Terraform state preserved in tmp/.${NC}"; echo -e "${YELLOW}   Re-run ./scripts/destroy.sh to continue cleanup.${NC}"; exit 130' INT TERM

echo -e "${RED}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       APEX EKS In-Place Upgrade — CLEANUP                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

#######################################################################
# Auto-discover deployments or fall back to AWS discovery
#######################################################################

TERRAFORM_DIR=""
CLUSTER_NAME=""
REGION=""
HAS_TERRAFORM=false

# Find all karpenter-* deployment directories with terraform state
declare -a DEPLOY_DIRS=()
if [ -d "$PATTERNS_BASE" ]; then
  for dir in "$PATTERNS_BASE"/karpenter-*/; do
    [ -d "$dir" ] || continue
    if [ -f "${dir}terraform.tfstate" ] || [ -d "${dir}.terraform" ]; then
      DEPLOY_DIRS+=("$dir")
    fi
  done
fi

if [ ${#DEPLOY_DIRS[@]} -gt 1 ]; then
  # Multiple deployments — ask which one
  echo -e "${BOLD}Found ${#DEPLOY_DIRS[@]} active deployments:${NC}"
  echo ""
  IDX=0
  for dir in "${DEPLOY_DIRS[@]}"; do
    IDX=$((IDX + 1))
    dirname=$(basename "$dir")
    echo "  [$IDX] ${dirname}  (cluster: ex-${dirname})"
  done
  echo "  [a] Destroy ALL"
  echo "  [q] Quit"
  echo ""
  read -rp "> " CHOICE

  if [ "$CHOICE" = "q" ] || [ "$CHOICE" = "Q" ]; then
    echo "Aborted."
    exit 0
  fi

  if [ "$CHOICE" = "a" ] || [ "$CHOICE" = "A" ]; then
    echo ""
    echo -e "${YELLOW}Destroying all ${#DEPLOY_DIRS[@]} deployments sequentially...${NC}"
    for dir in "${DEPLOY_DIRS[@]}"; do
      dirname=$(basename "$dir")
      echo ""
      echo -e "${BOLD}━━━ Destroying ${dirname} ━━━${NC}"
      "$SCRIPT_DIR/destroy.sh" <<< "$(echo "$dirname" | grep -oP '(?<=karpenter-).*')" || true
    done
    exit 0
  fi

  CHOICE_IDX=$((CHOICE - 1))
  if [ "$CHOICE_IDX" -ge 0 ] && [ "$CHOICE_IDX" -lt "${#DEPLOY_DIRS[@]}" ]; then
    TERRAFORM_DIR="${DEPLOY_DIRS[$CHOICE_IDX]}"
    HAS_TERRAFORM=true
  else
    log_error "Invalid selection."
    exit 1
  fi

elif [ ${#DEPLOY_DIRS[@]} -eq 1 ]; then
  # Single deployment — use it
  TERRAFORM_DIR="${DEPLOY_DIRS[0]}"
  HAS_TERRAFORM=true
  dirname=$(basename "$TERRAFORM_DIR")
  log_info "Found deployment: ${dirname} (cluster: ex-${dirname})"

else
  # No deployment directories found — fall back to AWS discovery
  log_step 1 "No deployment directories found — searching for orphaned clusters"

  echo -e "${YELLOW}No karpenter-* directories with Terraform state found in tmp/.${NC}"
  echo -e "${YELLOW}This can happen if deploy.sh was interrupted or tmp/ was deleted.${NC}"
  echo ""

  CLUSTERS=$(aws eks list-clusters --query "clusters" --output text 2>/dev/null || echo "")

  if [ -n "$CLUSTERS" ] && [ "$CLUSTERS" != "None" ]; then
    echo -e "${BOLD}Found EKS clusters in your account:${NC}"
    echo ""
    IDX=0
    declare -a FOUND_CLUSTERS=()
    for c in $CLUSTERS; do
      IDX=$((IDX + 1))
      echo "  [$IDX] $c"
      FOUND_CLUSTERS+=("$c")
    done
    echo ""
    echo -n "Enter the number of the cluster to destroy (or 'q' to quit): "
    read -r CHOICE

    if [ "$CHOICE" = "q" ] || [ "$CHOICE" = "Q" ]; then
      echo "Aborted."
      exit 0
    fi

    CHOICE_IDX=$((CHOICE - 1))
    if [ "$CHOICE_IDX" -ge 0 ] && [ "$CHOICE_IDX" -lt "${#FOUND_CLUSTERS[@]}" ]; then
      CLUSTER_NAME="${FOUND_CLUSTERS[$CHOICE_IDX]}"
      REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")
      log_info "Selected: ${CLUSTER_NAME} in ${REGION}"

      # Offer to re-clone for terraform destroy
      echo ""
      echo -e "${BOLD}Recovery options:${NC}"
      echo "  [1] Re-clone terraform-aws-eks-blueprints and run terraform destroy (recommended)"
      echo "  [2] Delete cluster via AWS CLI (last resort — may leave orphaned resources)"
      echo "  [q] Quit"
      echo ""
      echo -n "> "
      read -r RECOVERY_CHOICE

      case "$RECOVERY_CHOICE" in
        1)
          echo ""
          log_info "Re-cloning terraform-aws-eks-blueprints..."
          mkdir -p "${INPLACE_DIR}/tmp"
          git clone https://github.com/aws-ia/terraform-aws-eks-blueprints.git \
            "${INPLACE_DIR}/tmp/terraform-aws-eks-blueprints"

          # Try to derive the suffix from the cluster name (ex-karpenter-<suffix>)
          SUFFIX=$(echo "$CLUSTER_NAME" | sed -n 's/^ex-karpenter-//p')
          if [ -z "$SUFFIX" ]; then
            SUFFIX="recovery"
          fi
          DEPLOY_DIR="karpenter-${SUFFIX}"
          TERRAFORM_DIR="${PATTERNS_BASE}/${DEPLOY_DIR}"
          cp -r "${PATTERNS_BASE}/karpenter" "$TERRAFORM_DIR"
          HAS_TERRAFORM=true

          cd "$TERRAFORM_DIR"
          terraform init

          echo ""
          log_warn "You need to import the existing cluster into Terraform state."
          log_warn "This is complex — it may be easier to use option 2 (AWS CLI delete)."
          log_warn "Alternatively, run: terraform destroy --auto-approve"
          log_warn "(Terraform will attempt to destroy even without full state)"
          echo ""
          echo -n "Try terraform destroy anyway? [y/N]: "
          read -r TRY_DESTROY
          if [ "$TRY_DESTROY" = "y" ] || [ "$TRY_DESTROY" = "Y" ]; then
            # Continue to the normal destroy flow below
            :
          else
            echo "Aborted. The repo is cloned in tmp/ for manual recovery."
            exit 0
          fi
          ;;
        2)
          echo ""
          log_warn "Deleting ALL resources via AWS CLI..."
          echo ""

          # Get VPC ID from cluster
          VPC_ID=$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$REGION" \
            --query "cluster.resourcesVpcConfig.vpcId" --output text 2>/dev/null || echo "")

          # 1. Terminate Karpenter EC2 instances
          log_step 1 "Terminating Karpenter EC2 instances"
          INSTANCE_IDS=$(aws ec2 describe-instances \
            --region "$REGION" \
            --filters "Name=tag:karpenter.sh/discovery,Values=${CLUSTER_NAME}" \
                      "Name=instance-state-name,Values=running,pending,stopping,stopped" \
            --query "Reservations[].Instances[].InstanceId" \
            --output text 2>/dev/null || true)

          if [ -n "$INSTANCE_IDS" ] && [ "$INSTANCE_IDS" != "None" ]; then
            # shellcheck disable=SC2086
            aws ec2 terminate-instances --region "$REGION" --instance-ids $INSTANCE_IDS > /dev/null 2>&1 || true
            log_info "Karpenter instances terminating"
          else
            log_info "No Karpenter instances found"
          fi

          # 2. Delete Fargate profiles (must be deleted before cluster)
          log_step 2 "Deleting Fargate profiles"
          PROFILES=$(aws eks list-fargate-profiles --cluster-name "$CLUSTER_NAME" --region "$REGION" \
            --query "fargateProfileNames" --output text 2>/dev/null || true)
          for fp in $PROFILES; do
            if [ -n "$fp" ] && [ "$fp" != "None" ]; then
              log_debug "Deleting Fargate profile: $fp"
              aws eks delete-fargate-profile --cluster-name "$CLUSTER_NAME" --fargate-profile-name "$fp" \
                --region "$REGION" 2>/dev/null || true
            fi
          done

          # 3. Delete EKS add-ons
          log_step 3 "Deleting EKS add-ons"
          ADDONS=$(aws eks list-addons --cluster-name "$CLUSTER_NAME" --region "$REGION" \
            --query "addons" --output text 2>/dev/null || true)
          for addon in $ADDONS; do
            if [ -n "$addon" ] && [ "$addon" != "None" ]; then
              log_debug "Deleting add-on: $addon"
              aws eks delete-addon --cluster-name "$CLUSTER_NAME" --addon-name "$addon" \
                --region "$REGION" 2>/dev/null || true
            fi
          done

          # 4. Wait for Fargate profiles to delete (required before cluster delete)
          log_step 4 "Waiting for Fargate profiles to delete"
          ELAPSED=0
          while [ $ELAPSED -lt 300 ]; do
            REMAINING=$(aws eks list-fargate-profiles --cluster-name "$CLUSTER_NAME" --region "$REGION" \
              --query "fargateProfileNames" --output text 2>/dev/null || echo "")
            if [ -z "$REMAINING" ] || [ "$REMAINING" = "None" ]; then
              log_info "All Fargate profiles deleted"
              break
            fi
            log_debug "Fargate profiles still deleting... (${ELAPSED}s)"
            sleep 15
            ELAPSED=$((ELAPSED + 15))
          done

          # 5. Delete EKS cluster
          log_step 5 "Deleting EKS cluster"
          aws eks delete-cluster --name "$CLUSTER_NAME" --region "$REGION" 2>/dev/null || true
          log_info "Cluster deletion initiated"

          # 6. Delete Karpenter SQS queue
          log_step 6 "Deleting Karpenter SQS queue"
          QUEUE_URL=$(aws sqs get-queue-url --queue-name "$CLUSTER_NAME" --region "$REGION" \
            --query "QueueUrl" --output text 2>/dev/null || echo "")
          if [ -n "$QUEUE_URL" ] && [ "$QUEUE_URL" != "None" ]; then
            aws sqs delete-queue --queue-url "$QUEUE_URL" --region "$REGION" 2>/dev/null || true
            log_info "SQS queue deleted"
          else
            log_info "No SQS queue found"
          fi

          # 7. Delete Karpenter EventBridge rules
          log_step 7 "Deleting Karpenter EventBridge rules"
          RULES=$(aws events list-rules --region "$REGION" --name-prefix "$CLUSTER_NAME" \
            --query "Rules[].Name" --output text 2>/dev/null || true)
          for rule in $RULES; do
            if [ -n "$rule" ] && [ "$rule" != "None" ]; then
              TARGETS=$(aws events list-targets-by-rule --rule "$rule" --region "$REGION" \
                --query "Targets[].Id" --output text 2>/dev/null || true)
              for target in $TARGETS; do
                aws events remove-targets --rule "$rule" --ids "$target" --region "$REGION" 2>/dev/null || true
              done
              aws events delete-rule --name "$rule" --region "$REGION" 2>/dev/null || true
              log_debug "Deleted EventBridge rule: $rule"
            fi
          done

          # 8. Delete Karpenter IAM roles
          log_step 8 "Deleting Karpenter IAM roles"
          for role_name in "$CLUSTER_NAME" "${CLUSTER_NAME}-karpenter"; do
            POLICIES=$(aws iam list-attached-role-policies --role-name "$role_name" \
              --query "AttachedPolicies[].PolicyArn" --output text 2>/dev/null || true)
            for policy in $POLICIES; do
              aws iam detach-role-policy --role-name "$role_name" --policy-arn "$policy" 2>/dev/null || true
            done
            INLINE=$(aws iam list-role-policies --role-name "$role_name" \
              --query "PolicyNames" --output text 2>/dev/null || true)
            for ip in $INLINE; do
              aws iam delete-role-policy --role-name "$role_name" --policy-name "$ip" 2>/dev/null || true
            done
            IPS=$(aws iam list-instance-profiles-for-role --role-name "$role_name" \
              --query "InstanceProfiles[].InstanceProfileName" --output text 2>/dev/null || true)
            for ip_name in $IPS; do
              aws iam remove-role-from-instance-profile --role-name "$role_name" \
                --instance-profile-name "$ip_name" 2>/dev/null || true
              aws iam delete-instance-profile --instance-profile-name "$ip_name" 2>/dev/null || true
            done
            aws iam delete-role --role-name "$role_name" 2>/dev/null && \
              log_debug "Deleted IAM role: $role_name" || true
          done

          # 9. Delete OIDC provider
          log_step 9 "Deleting OIDC provider"
          OIDC_ISSUERS=$(aws iam list-open-id-connect-providers \
            --query "OpenIDConnectProviderList[].Arn" --output text 2>/dev/null || true)
          for oidc_arn in $OIDC_ISSUERS; do
            OIDC_TAGS=$(aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$oidc_arn" \
              --query "Tags[?Key=='eks:cluster-name'&&Value=='${CLUSTER_NAME}']" --output text 2>/dev/null || true)
            if [ -n "$OIDC_TAGS" ]; then
              aws iam delete-open-id-connect-provider --open-id-connect-provider-arn "$oidc_arn" 2>/dev/null || true
              log_debug "Deleted OIDC provider: $oidc_arn"
            fi
          done

          # 10. Delete CloudWatch Log Group
          log_step 10 "Deleting CloudWatch Log Group"
          aws logs delete-log-group --log-group-name "/aws/eks/${CLUSTER_NAME}/cluster" \
            --region "$REGION" 2>/dev/null && log_info "Log group deleted" || log_info "No log group found"

          # 11. Delete KMS key alias and schedule key deletion
          log_step 11 "Deleting KMS key (alias/eks/${CLUSTER_NAME})"
          KMS_ALIAS="alias/eks/${CLUSTER_NAME}"
          KMS_KEY_ID=$(aws kms describe-key --key-id "$KMS_ALIAS" --region "$REGION" \
            --query "KeyMetadata.KeyId" --output text 2>/dev/null || echo "")
          if [ -n "$KMS_KEY_ID" ] && [ "$KMS_KEY_ID" != "None" ]; then
            aws kms delete-alias --alias-name "$KMS_ALIAS" --region "$REGION" 2>/dev/null || true
            aws kms schedule-key-deletion --key-id "$KMS_KEY_ID" --pending-window-in-days 7 \
              --region "$REGION" 2>/dev/null || true
            log_info "KMS alias deleted, key scheduled for deletion in 7 days"
          else
            log_info "No KMS key found"
          fi

          # 12. Wait for cluster to delete before VPC cleanup
          log_step 12 "Waiting for EKS cluster to delete"
          ELAPSED=0
          while [ $ELAPSED -lt 600 ]; do
            STATUS=$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$REGION" \
              --query "cluster.status" --output text 2>/dev/null || echo "DELETED")
            if [ "$STATUS" = "DELETED" ]; then
              log_info "Cluster deleted"
              break
            fi
            log_debug "Cluster status: ${STATUS} (${ELAPSED}s)"
            sleep 20
            ELAPSED=$((ELAPSED + 20))
          done

          # 13. Delete VPC and all its resources
          if [ -n "$VPC_ID" ] && [ "$VPC_ID" != "None" ]; then
            log_step 13 "Deleting VPC ${VPC_ID} and all resources"

            NAT_GWS=$(aws ec2 describe-nat-gateways --region "$REGION" \
              --filter "Name=vpc-id,Values=${VPC_ID}" "Name=state,Values=available,pending" \
              --query "NatGateways[].NatGatewayId" --output text 2>/dev/null || true)
            for nat in $NAT_GWS; do
              log_debug "Deleting NAT gateway: $nat"
              aws ec2 delete-nat-gateway --nat-gateway-id "$nat" --region "$REGION" 2>/dev/null || true
            done

            if [ -n "$NAT_GWS" ] && [ "$NAT_GWS" != "None" ]; then
              log_debug "Waiting for NAT gateways to delete..."
              sleep 60
            fi

            EIPS=$(aws ec2 describe-addresses --region "$REGION" \
              --filters "Name=tag:Blueprint,Values=${CLUSTER_NAME}" \
              --query "Addresses[].AllocationId" --output text 2>/dev/null || true)
            for eip in $EIPS; do
              log_debug "Releasing EIP: $eip"
              aws ec2 release-address --allocation-id "$eip" --region "$REGION" 2>/dev/null || true
            done

            SUBNETS=$(aws ec2 describe-subnets --region "$REGION" \
              --filters "Name=vpc-id,Values=${VPC_ID}" \
              --query "Subnets[].SubnetId" --output text 2>/dev/null || true)
            for subnet in $SUBNETS; do
              log_debug "Deleting subnet: $subnet"
              aws ec2 delete-subnet --subnet-id "$subnet" --region "$REGION" 2>/dev/null || true
            done

            IGWS=$(aws ec2 describe-internet-gateways --region "$REGION" \
              --filters "Name=attachment.vpc-id,Values=${VPC_ID}" \
              --query "InternetGateways[].InternetGatewayId" --output text 2>/dev/null || true)
            for igw in $IGWS; do
              log_debug "Detaching and deleting IGW: $igw"
              aws ec2 detach-internet-gateway --internet-gateway-id "$igw" --vpc-id "$VPC_ID" \
                --region "$REGION" 2>/dev/null || true
              aws ec2 delete-internet-gateway --internet-gateway-id "$igw" \
                --region "$REGION" 2>/dev/null || true
            done

            RTS=$(aws ec2 describe-route-tables --region "$REGION" \
              --filters "Name=vpc-id,Values=${VPC_ID}" \
              --query "RouteTables[?Associations[0].Main!=\`true\`].RouteTableId" \
              --output text 2>/dev/null || true)
            for rt in $RTS; do
              ASSOCS=$(aws ec2 describe-route-tables --region "$REGION" \
                --route-table-ids "$rt" \
                --query "RouteTables[].Associations[?!Main].RouteTableAssociationId" \
                --output text 2>/dev/null || true)
              for assoc in $ASSOCS; do
                aws ec2 disassociate-route-table --association-id "$assoc" --region "$REGION" 2>/dev/null || true
              done
              log_debug "Deleting route table: $rt"
              aws ec2 delete-route-table --route-table-id "$rt" --region "$REGION" 2>/dev/null || true
            done

            SGS=$(aws ec2 describe-security-groups --region "$REGION" \
              --filters "Name=vpc-id,Values=${VPC_ID}" \
              --query "SecurityGroups[?GroupName!='default'].GroupId" \
              --output text 2>/dev/null || true)
            for sg in $SGS; do
              log_debug "Deleting security group: $sg"
              aws ec2 delete-security-group --group-id "$sg" --region "$REGION" 2>/dev/null || true
            done

            log_debug "Deleting VPC: $VPC_ID"
            aws ec2 delete-vpc --vpc-id "$VPC_ID" --region "$REGION" 2>/dev/null || true
            log_info "VPC cleanup complete"
          fi

          echo ""
          echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
          echo -e "${GREEN}${BOLD}║          AWS CLI cleanup completed!                          ║${NC}"
          echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
          echo ""
          echo -e "${CYAN}Destroyed: ${CLUSTER_NAME} in ${REGION}${NC}"
          echo -e "${YELLOW}Verify in AWS Console that all resources are gone.${NC}"
          exit 0
          ;;
        q|Q)
          echo "Aborted."
          exit 0
          ;;
        *)
          echo "Invalid choice. Aborted."
          exit 1
          ;;
      esac
    else
      log_error "Invalid selection."
      exit 1
    fi
  else
    log_error "No EKS clusters found and no Terraform state. Nothing to destroy."
    exit 0
  fi
fi

#######################################################################
# We have a TERRAFORM_DIR — extract cluster info from Terraform state
#######################################################################

if [ "$HAS_TERRAFORM" = true ] && [ -n "$TERRAFORM_DIR" ] && [ -z "$CLUSTER_NAME" ]; then
  log_step 1 "Getting cluster info from Terraform state"
  cd "$TERRAFORM_DIR"

  TF_OUTPUT=$(terraform output -raw configure_kubectl 2>&1 || echo "")
  CONFIGURE_CMD=$(echo "$TF_OUTPUT" | grep -E '^aws eks' || echo "")

  if [ -n "$CONFIGURE_CMD" ]; then
    CLUSTER_NAME=$(echo "$CONFIGURE_CMD" | grep -oP '(?<=--name )\S+' || echo "")
    REGION=$(echo "$CONFIGURE_CMD" | grep -oP '(?<=--region )\S+' || echo "")
  fi

  if [ -n "$CLUSTER_NAME" ] && [ -n "$REGION" ]; then
    log_info "Cluster: ${CLUSTER_NAME} in ${REGION}"
  else
    log_warn "No outputs in Terraform state (state may be empty after re-clone)."
  fi
fi

# If we still don't have cluster info, bail
if [ -z "$CLUSTER_NAME" ] || [ -z "$REGION" ]; then
  log_warn "Could not determine cluster info."
  if [ "$HAS_TERRAFORM" = true ] && [ -n "$TERRAFORM_DIR" ]; then
    log_warn "Attempting terraform destroy without cluster info..."
    cd "$TERRAFORM_DIR"
    terraform destroy --auto-approve || true
    rm -rf "$TERRAFORM_DIR"
    log_info "Cleanup complete."
  fi
  exit 0
fi

#######################################################################
# Set kubectl context
#######################################################################

aws --region "$REGION" eks update-kubeconfig \
  --name "$CLUSTER_NAME" \
  --alias "${CLUSTER_NAME}" 2>/dev/null || true

KUBECTL_OK=true
kubectl config use-context "${CLUSTER_NAME}" 2>/dev/null || {
  log_warn "Could not set kubectl context. Cluster may already be deleted."
  KUBECTL_OK=false
}

#######################################################################
# Step 2: Delete planted issue manifests
#######################################################################

if [ "$KUBECTL_OK" = true ]; then
  log_step 2 "Deleting planted issue manifests"

  cd "$INPLACE_DIR"

  kubectl delete -f manifests/blocking-pdb.yaml --ignore-not-found 2>/dev/null || true
  kubectl delete -f manifests/endpoints-watcher.yaml --ignore-not-found 2>/dev/null || true

  log_info "Planted issue manifests deleted"
fi

#######################################################################
# Step 3: Terminate Karpenter EC2 instances via AWS API (fire and forget)
#######################################################################

log_step 3 "Terminating Karpenter-managed EC2 instances"

INSTANCE_IDS=$(aws ec2 describe-instances \
  --region "$REGION" \
  --filters "Name=tag:karpenter.sh/discovery,Values=${CLUSTER_NAME}" \
            "Name=instance-state-name,Values=running,pending,stopping,stopped" \
  --query "Reservations[].Instances[].InstanceId" \
  --output text 2>/dev/null || true)

if [ -n "$INSTANCE_IDS" ] && [ "$INSTANCE_IDS" != "None" ]; then
  INSTANCE_COUNT=$(echo "$INSTANCE_IDS" | wc -w)
  log_debug "Terminating ${INSTANCE_COUNT} Karpenter-managed instance(s)..."
  # shellcheck disable=SC2086
  aws ec2 terminate-instances --region "$REGION" --instance-ids $INSTANCE_IDS > /dev/null 2>&1 || true
  log_info "EC2 terminate initiated (continuing in parallel)"
else
  log_info "No Karpenter-managed instances found"
fi

#######################################################################
# Step 4: Delete Karpenter K8s resources + example workloads
#######################################################################

if [ "$KUBECTL_OK" = true ]; then
  log_step 4 "Deleting Karpenter K8s resources"

  log_debug "Deleting NodePools..."
  kubectl delete nodepools --all --ignore-not-found 2>/dev/null || true

  log_debug "Deleting NodeClaims..."
  kubectl delete nodeclaims --all --ignore-not-found 2>/dev/null || true

  log_debug "Deleting EC2NodeClasses..."
  kubectl delete ec2nodeclasses --all --ignore-not-found 2>/dev/null || true

  log_info "Karpenter K8s resources deleted"

  log_step 5 "Deleting example workloads"

  if [ -d "$TERRAFORM_DIR" ]; then
    cd "$TERRAFORM_DIR"
    kubectl delete -f example.yaml --ignore-not-found 2>/dev/null || true
    kubectl delete -f karpenter.yaml --ignore-not-found 2>/dev/null || true
  fi

  log_info "Example workloads deleted"
fi

#######################################################################
# Step 6: Wait for Karpenter instances to finish terminating
#######################################################################

log_step 6 "Waiting for Karpenter instances to finish terminating"

ELAPSED=0
while [ $ELAPSED -lt $NODE_WAIT_TIMEOUT ]; do
  RUNNING=$(aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=tag:karpenter.sh/discovery,Values=${CLUSTER_NAME}" \
              "Name=instance-state-name,Values=running,pending,stopping,stopped,shutting-down" \
    --query "Reservations[].Instances[].InstanceId" \
    --output text 2>/dev/null || true)

  if [ -z "$RUNNING" ] || [ "$RUNNING" = "None" ]; then
    log_info "All Karpenter instances terminated"
    break
  fi

  NODE_COUNT=$(echo "$RUNNING" | wc -w)
  log_debug "Still ${NODE_COUNT} instance(s) terminating... (${ELAPSED}s/${NODE_WAIT_TIMEOUT}s)"
  sleep 15
  ELAPSED=$((ELAPSED + 15))
done

if [ $ELAPSED -ge $NODE_WAIT_TIMEOUT ]; then
  log_warn "Timed out waiting for instances to terminate. Proceeding anyway..."
fi

#######################################################################
# Step 7: Terraform destroy
#######################################################################

TERRAFORM_DESTROY_OK=false

if [ "$HAS_TERRAFORM" = true ] && [ -d "$TERRAFORM_DIR" ]; then
  log_step 7 "Running terraform destroy"

  cd "$TERRAFORM_DIR"
  terraform destroy --auto-approve

  TERRAFORM_DESTROY_OK=true
  log_info "Terraform destroy completed"
else
  log_warn "No Terraform directory — skipping terraform destroy"
fi

#######################################################################
# Step 8: Clean up deployment directory (ONLY after successful destroy)
#######################################################################

if [ "$TERRAFORM_DESTROY_OK" = true ]; then
  log_step 8 "Cleaning up deployment directory"
  rm -rf "$TERRAFORM_DIR"
  log_info "Deployment directory cleaned up"

  # If no other deployments remain, clean up the clone too
  REMAINING_DEPLOYS=0
  if [ -d "$PATTERNS_BASE" ]; then
    for dir in "$PATTERNS_BASE"/karpenter-*/; do
      [ -d "$dir" ] && REMAINING_DEPLOYS=$((REMAINING_DEPLOYS + 1))
    done
  fi
  if [ "$REMAINING_DEPLOYS" -eq 0 ] && [ -d "${INPLACE_DIR}/tmp/terraform-aws-eks-blueprints" ]; then
    log_debug "No other deployments remain — cleaning up cloned repo"
    rm -rf "${INPLACE_DIR}/tmp/terraform-aws-eks-blueprints"
  fi
else
  log_warn "Skipping cleanup — Terraform state may still be needed"
  log_warn "Once you've confirmed all AWS resources are deleted, run:"
  log_warn "  rm -rf ${TERRAFORM_DIR}"
fi

#######################################################################
# Done
#######################################################################

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║          Cleanup completed successfully!                     ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Destroyed: ${CLUSTER_NAME} in ${REGION}${NC}"
