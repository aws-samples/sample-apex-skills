#!/usr/bin/env bash
set -euo pipefail
trap 'rm -f /tmp/*-skill.zip /tmp/*-payload.json 2>/dev/null' EXIT

# DevOps Agent Setup Script
# Automates: IAM roles, Agent Space creation, AWS association, EKS access, skill upload
# Usage: bash devops-agent/setup.sh --space-name "my-space" --region us-west-2 --cluster-name my-cluster --cluster-region us-west-2
# Teardown: bash devops-agent/setup.sh --teardown --space-id <id> --region us-west-2

SPACE_NAME=""
REGION="us-west-2"
ACCOUNT_ID=""
CLUSTER_NAME=""
CLUSTER_REGION=""
TEARDOWN=false
SPACE_ID=""
AGENT_ROLE="DevOpsAgentRole-AgentSpace"
OPERATOR_ROLE="DevOpsAgentRole-WebappAdmin"

usage() {
  echo "Usage: bash devops-agent/setup.sh [OPTIONS]"
  echo ""
  echo "Setup:"
  echo "  --space-name NAME       Agent Space name (required)"
  echo "  --region REGION          Agent Space region (default: us-west-2)"
  echo "  --cluster-name NAME     EKS cluster to grant access to (optional)"
  echo "  --cluster-region REGION  Region of the EKS cluster (defaults to --region)"
  echo ""
  echo "Teardown:"
  echo "  --teardown              Delete all resources created by this script"
  echo "  --space-id ID           Agent Space ID to tear down (required with --teardown)"
  echo "  --region REGION          Region of the Agent Space"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --space-name) SPACE_NAME="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --cluster-name) CLUSTER_NAME="$2"; shift 2 ;;
    --cluster-region) CLUSTER_REGION="$2"; shift 2 ;;
    --teardown) TEARDOWN=true; shift ;;
    --space-id) SPACE_ID="$2"; shift 2 ;;
    --help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CLUSTER_REGION="${CLUSTER_REGION:-$REGION}"

if $TEARDOWN; then
  if [[ -z "$SPACE_ID" ]]; then echo "Error: --space-id required for teardown"; exit 1; fi
  echo "=== Tearing down Agent Space $SPACE_ID ==="

  if [[ -n "$CLUSTER_NAME" ]]; then
    echo "Removing EKS access entry..."
    aws eks delete-access-entry --cluster-name "$CLUSTER_NAME" --principal-arn "arn:aws:iam::${ACCOUNT_ID}:role/${AGENT_ROLE}" --region "$CLUSTER_REGION" 2>/dev/null || true
  fi

  echo "Deleting agent space..."
  aws devops-agent delete-agent-space --agent-space-id "$SPACE_ID" --region "$REGION" 2>/dev/null || true
  echo "  Waiting for space deletion to propagate..."
  sleep 10

  echo "Detaching policies and deleting IAM roles..."
  aws iam detach-role-policy --role-name "$AGENT_ROLE" --policy-arn "arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy" 2>/dev/null || true
  aws iam delete-role --role-name "$AGENT_ROLE" 2>/dev/null || true
  aws iam detach-role-policy --role-name "$OPERATOR_ROLE" --policy-arn "arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy" 2>/dev/null || true
  aws iam delete-role --role-name "$OPERATOR_ROLE" 2>/dev/null || true

  echo "=== Teardown complete ==="
  exit 0
fi

if [[ -z "$SPACE_NAME" ]]; then echo "Error: --space-name required"; usage; fi

echo "=== DevOps Agent Setup ==="
echo "Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Space: $SPACE_NAME"
[[ -n "$CLUSTER_NAME" ]] && echo "Cluster: $CLUSTER_NAME ($CLUSTER_REGION)"
echo ""

# Step 1: Create Agent Space IAM role
echo "[1/7] Creating IAM role: $AGENT_ROLE"
if aws iam get-role --role-name "$AGENT_ROLE" &>/dev/null; then
  echo "  Role already exists, skipping"
else
  TRUST=$(cat <<POLICY
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole","Condition":{"StringEquals":{"aws:SourceAccount":"${ACCOUNT_ID}"},"ArnLike":{"aws:SourceArn":"arn:aws:aidevops:${REGION}:${ACCOUNT_ID}:agentspace/*"}}}]}
POLICY
  )
  aws iam create-role --role-name "$AGENT_ROLE" --assume-role-policy-document "$TRUST" --output text --query 'Role.Arn'
  aws iam attach-role-policy --role-name "$AGENT_ROLE" --policy-arn "arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy"
  echo "  Created and policy attached"
fi

# Step 2: Create Operator Web App IAM role
echo "[2/7] Creating IAM role: $OPERATOR_ROLE"
if aws iam get-role --role-name "$OPERATOR_ROLE" &>/dev/null; then
  echo "  Role already exists, skipping"
else
  TRUST=$(cat <<POLICY
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":["sts:AssumeRole","sts:TagSession"],"Condition":{"StringEquals":{"aws:SourceAccount":"${ACCOUNT_ID}"},"ArnLike":{"aws:SourceArn":"arn:aws:aidevops:${REGION}:${ACCOUNT_ID}:agentspace/*"}}}]}
POLICY
  )
  aws iam create-role --role-name "$OPERATOR_ROLE" --assume-role-policy-document "$TRUST" --output text --query 'Role.Arn'
  aws iam attach-role-policy --role-name "$OPERATOR_ROLE" --policy-arn "arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy"
  echo "  Created and policy attached"
fi

# Step 3: Create Agent Space (check for existing first)
echo "[3/7] Creating Agent Space: $SPACE_NAME"
EXISTING_SPACE=$(aws devops-agent list-agent-spaces --region "$REGION" --query "agentSpaces[?name=='${SPACE_NAME}'].agentSpaceId" --output text 2>/dev/null || true)
if [[ -n "$EXISTING_SPACE" ]]; then
  SPACE_ID="$EXISTING_SPACE"
  echo "  Space already exists: $SPACE_ID"
else
  SPACE_ID=$(aws devops-agent create-agent-space --name "$SPACE_NAME" --description "APEX skills testing" --region "$REGION" --query 'agentSpace.agentSpaceId' --output text)
  echo "  Created: $SPACE_ID"
fi

# Step 4: Associate AWS account
echo "[4/7] Associating AWS account"
aws devops-agent associate-service --agent-space-id "$SPACE_ID" --service-id "aws" --configuration "{\"aws\":{\"assumableRoleArn\":\"arn:aws:iam::${ACCOUNT_ID}:role/${AGENT_ROLE}\",\"accountId\":\"${ACCOUNT_ID}\",\"accountType\":\"monitor\"}}" --region "$REGION" --output text --query 'association.status'

# Step 5: Enable Operator Web App
echo "[5/7] Enabling Operator Web App"
OPERATOR_URL=$(aws devops-agent enable-operator-app --agent-space-id "$SPACE_ID" --auth-flow iam --operator-app-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/${OPERATOR_ROLE}" --region "$REGION" --query 'operatorAppUrl' --output text)
echo "  URL: $OPERATOR_URL"

# Step 6: EKS access entry (if cluster specified)
if [[ -n "$CLUSTER_NAME" ]]; then
  echo "[6/7] Creating EKS access entry on $CLUSTER_NAME"
  AUTH_MODE=$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$CLUSTER_REGION" --query 'cluster.accessConfig.authenticationMode' --output text)
  if [[ "$AUTH_MODE" != *"API"* ]]; then
    echo "  WARNING: Cluster auth mode is '$AUTH_MODE' — must include API. Skipping access entry."
  else
    aws eks create-access-entry --cluster-name "$CLUSTER_NAME" --principal-arn "arn:aws:iam::${ACCOUNT_ID}:role/${AGENT_ROLE}" --type STANDARD --region "$CLUSTER_REGION" --output text --query 'accessEntry.principalArn' 2>/dev/null || echo "  Access entry already exists"
    aws eks associate-access-policy --cluster-name "$CLUSTER_NAME" --principal-arn "arn:aws:iam::${ACCOUNT_ID}:role/${AGENT_ROLE}" --policy-arn "arn:aws:eks::aws:cluster-access-policy/AmazonAIOpsAssistantPolicy" --access-scope type=cluster --region "$CLUSTER_REGION" --output text --query 'associatedAccessPolicy.policyArn' 2>/dev/null || echo "  Policy already associated"
    echo "  EKS access configured"
  fi
else
  echo "[6/7] No cluster specified, skipping EKS access entry"
fi

# Step 7: Upload skills
echo "[7/7] Uploading skills"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPLOADED=0
for skill_dir in "$SCRIPT_DIR"/*/; do
  [[ -f "$skill_dir/SKILL.md" ]] || continue
  skill_name=$(basename "$skill_dir")
  if [[ ! -d "$skill_dir/references" ]]; then
    echo "  Skipping $skill_name (placeholder — no references/)"
    continue
  fi
  echo "  Packaging $skill_name..."
  ZIP_FILE="/tmp/${skill_name}-skill.zip"
  rm -f "$ZIP_FILE"
  (cd "$skill_dir" && zip -qr "$ZIP_FILE" . -x './references/porting-notes.md')
  JSON_FILE="/tmp/${skill_name}-payload.json"
  python3 -c "import base64,json,sys; zf=sys.argv[1]; sid=sys.argv[2]; z=open(zf,'rb').read(); open(sys.argv[3],'w').write(json.dumps({'agentSpaceId':sid,'assetType':'skill','metadata':{'agent_types':['CHAT']},'content':{'zip':{'zipFile':base64.b64encode(z).decode()}}}))" "$ZIP_FILE" "$SPACE_ID" "$JSON_FILE"
  ASSET_ID=$(aws devops-agent create-asset --cli-input-json "file://$JSON_FILE" --region "$REGION" --query 'asset.assetId' --output text)
  echo "  Uploaded: $skill_name ($ASSET_ID)"
  rm -f "$ZIP_FILE"
  rm -f "$JSON_FILE"
  UPLOADED=$((UPLOADED + 1))
done

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Agent Space ID: $SPACE_ID"
echo "Operator App:   $OPERATOR_URL"
echo "Skills uploaded: $UPLOADED"
echo "Region:         $REGION"
[[ -n "$CLUSTER_NAME" ]] && echo "EKS access:     $CLUSTER_NAME ($CLUSTER_REGION)"
echo ""
echo "Next steps:"
echo "  1. Open the Operator Web App: $OPERATOR_URL"
echo "  2. Start a chat and ask: 'Run a cost efficiency assessment on my EKS cluster'"
echo ""
echo "To tear down:"
echo "  bash devops-agent/setup.sh --teardown --space-id $SPACE_ID --region $REGION${CLUSTER_NAME:+ --cluster-name $CLUSTER_NAME --cluster-region $CLUSTER_REGION}"
