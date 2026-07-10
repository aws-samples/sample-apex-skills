#!/usr/bin/env bash
# validate_project.sh — Post-generation validation for ecs-build skill
# Usage: ./validate_project.sh <project-directory>
#
# Validates that a generated ECS Terraform project is structurally correct and
# ready for terraform init/plan/apply. Does NOT require AWS credentials.
# Domain checks map to the Critical Build Rules in SKILL.md (cited as CR n).
#
# Exit codes: 0 = passed, 1 = failed, 2 = passed but FAIL-grade checks were
# skipped (semantic validation did not run).

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0
SKIPPED=()          # names of checks that did not run
SKIP_FAILGRADE=0    # 1 if any skipped check is FAIL-grade (semantic validation)

pass() { echo -e "${GREEN}✓${NC} $1"; (( PASS++ )) || true; }
fail() { echo -e "${RED}✗${NC} $1"; (( FAIL++ )) || true; }
warn() { echo -e "${YELLOW}!${NC} $1"; (( WARN++ )) || true; }
# skip_check <name> <reason> <failgrade 0|1>
skip_check() {
    echo -e "${YELLOW}-${NC} $1 skipped — $2"
    SKIPPED+=("$1")
    if [ "${3:-0}" -eq 1 ]; then SKIP_FAILGRADE=1; fi
}

PROJECT_DIR="${1:?Usage: $0 <project-directory>}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: $PROJECT_DIR is not a directory"
    exit 1
fi

# Helper: grep across all .tf files in the project (recursive, skips .terraform)
tf_grep() { grep -rn --include='*.tf' --exclude-dir=.terraform -E "$1" "$PROJECT_DIR" 2>/dev/null || true; }
tf_grep_q() { grep -rq --include='*.tf' --exclude-dir=.terraform -E "$1" "$PROJECT_DIR" 2>/dev/null; }

# Code-only variants for presence-triggered FAIL checks: drop full-line
# comments (# or //) so commented-out HCL never trips a FAIL. Known limit:
# heredoc bodies and trailing inline comments are NOT filtered — acceptable
# for these line-oriented heuristics.
tf_grep_code() { tf_grep "$1" | grep -vE '^[^:]+:[0-9]+:[[:space:]]*(#|//)' || true; }
tf_grep_code_q() { [ -n "$(tf_grep_code "$1")" ]; }

# All .tf files, recursive, .terraform excluded — awk/per-file checks use this
# so their scope matches tf_grep (module subdirs included).
TF_FILES=()
while IFS= read -r -d '' f; do
    TF_FILES+=("$f")
done < <(find "$PROJECT_DIR" -name '*.tf' -not -path '*/.terraform/*' -print0 2>/dev/null)

# Express Mode projects delegate service-level concerns (deployment strategy,
# circuit breaker, load balancing) to the ECS-managed infrastructure role —
# those checks are N/A, not missing.
EXPRESS_ONLY=0
if tf_grep_q 'aws_ecs_express_gateway_service|express_gateway_service|modules/express-service' \
   && ! tf_grep_q 'resource "aws_ecs_service"' \
   && ! tf_grep_q '//modules/service"'; then
    EXPRESS_ONLY=1
fi

echo "Validating project: $PROJECT_DIR"
echo "==========================================="
if [ "$EXPRESS_ONLY" -eq 1 ]; then
    echo "i Express project detected — service-level checks (circuit breaker, strategy, LB) skipped as N/A"
fi

# --- 1. Required Terraform files ---
echo ""
echo "1. Required Terraform files"
echo "-------------------------------------------"

for f in main.tf variables.tf providers.tf versions.tf outputs.tf; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        pass "$f exists"
    else
        fail "$f missing"
    fi
done
for f in locals.tf data.tf; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        pass "$f exists"
    else
        warn "$f missing (acceptable if unused, but the scaffold normally emits it)"
    fi
done

# --- 2. Config files ---
echo ""
echo "2. Configuration files"
echo "-------------------------------------------"

if [ -f "$PROJECT_DIR/configs/backend.hcl" ]; then
    pass "configs/backend.hcl exists"
else
    warn "configs/backend.hcl missing — remote state config expected"
fi

# --- 3. terraform fmt check ---
echo ""
echo "3. Terraform format check"
echo "-------------------------------------------"

if command -v terraform &>/dev/null; then
    FMT_OUTPUT=$(terraform fmt -check -recursive "$PROJECT_DIR" 2>&1) || true
    if [ -z "$FMT_OUTPUT" ]; then
        pass "terraform fmt -check passes"
    else
        fail "terraform fmt -check found unformatted files:"
        echo "$FMT_OUTPUT" | head -10
    fi
else
    skip_check "terraform fmt" "terraform binary not found" 1
fi

# --- 4. Module source pins ---
echo ""
echo "4. Module and provider version pins"
echo "-------------------------------------------"

if tf_grep_q 'source\s*=\s*"terraform-aws-modules/ecs/aws"'; then
    # Every registry module block must carry a version pin (recursive scan)
    UNPINNED=""
    if [ ${#TF_FILES[@]} -gt 0 ]; then
        UNPINNED=$(awk 'FNR==1{inmod=0}
            /module "/{inmod=1; hasver=0; hasreg=0}
            inmod && /source[[:space:]]*=[[:space:]]*"terraform-aws-modules\//{hasreg=1}
            inmod && /version[[:space:]]*=/{hasver=1}
            inmod && /^}/{if (hasreg && !hasver) print FILENAME; inmod=0}' "${TF_FILES[@]}" 2>/dev/null || true)
    fi
    if [ -z "$UNPINNED" ]; then
        pass "terraform-aws-modules/ecs module blocks carry version pins"
    else
        fail "Registry module block without a version pin (CR 9): $UNPINNED"
    fi
else
    pass "No registry ECS module used (raw resources) — ensure provider pin below"
fi

if tf_grep_q 'required_providers' && tf_grep_q 'hashicorp/aws'; then
    pass "required_providers block pins hashicorp/aws"
else
    fail "No hashicorp/aws pin found in required_providers (CR 9)"
fi

# Local module source paths resolve (relative to the file that declares them)
while IFS= read -r -d '' tf; do
    tf_dir=$(dirname "$tf")
    while IFS= read -r mod_path; do
        [ -z "$mod_path" ] && continue
        if [ -d "$tf_dir/$mod_path" ]; then
            pass "Module $mod_path exists (referenced from ${tf#"$PROJECT_DIR"/})"
        else
            fail "Module $mod_path referenced from ${tf#"$PROJECT_DIR"/} but directory not found"
        fi
    done < <(grep -hoE 'source[[:space:]]*=[[:space:]]*"\./[^"]+' "$tf" 2>/dev/null | sed 's/.*"//' || true)
done < <(find "$PROJECT_DIR" -name '*.tf' -not -path '*/.terraform/*' -print0 2>/dev/null)

# --- 5. FARGATE_SPOT misuse / launch type checks (CR 1, CR 2) ---
echo ""
echo "5. FARGATE_SPOT / launch_type checks (CR 1)"
echo "-------------------------------------------"

if tf_grep_code_q 'launch_type\s*=\s*"FARGATE_SPOT"'; then
    fail "launch_type = \"FARGATE_SPOT\" found — FARGATE_SPOT is a capacity provider, not a launchType. Apply will fail."
    tf_grep_code 'launch_type\s*=\s*"FARGATE_SPOT"' | head -5
else
    pass "No launch_type = FARGATE_SPOT misuse"
fi

if tf_grep_code_q 'launch_type\s*=\s*"MANAGED_INSTANCES"'; then
    warn "launch_type = \"MANAGED_INSTANCES\" found — valid launchType, but this skill generates capacity provider strategies (Step 5) — confirm this is intentional."
    tf_grep_code 'launch_type\s*=\s*"MANAGED_INSTANCES"' | head -5
else
    pass "No launch_type = MANAGED_INSTANCES (skill default is capacity provider strategy)"
fi

# launch_type and capacity_provider_strategy on the same service resource
LT_CPS_CONFLICT=""
if [ ${#TF_FILES[@]} -gt 0 ]; then
    LT_CPS_CONFLICT=$(awk 'FNR==1{inres=0}
        /^[[:space:]]*(#|\/\/)/{next}
        /^resource "aws_ecs_service"/{inres=1; lt=0; cps=0; name=FILENAME": "$0}
        inres && /launch_type[[:space:]]*=/{lt=1}
        inres && /capacity_provider_strategy/{cps=1}
        inres && /^}/{if (lt && cps) print name; inres=0}' "${TF_FILES[@]}" 2>/dev/null || true)
fi
if [ -n "$LT_CPS_CONFLICT" ]; then
    fail "Service sets BOTH launch_type and capacity_provider_strategy (mutually exclusive, CR 1): $LT_CPS_CONFLICT"
else
    pass "No service mixes launch_type with capacity_provider_strategy"
fi

# A single capacity_provider_strategy must not mix Fargate and non-Fargate
# provider types (CR 2). Resource-block granular via awk. Only quoted
# literals are classified: an unquoted reference/interpolation (e.g.
# `capacity_provider = capacity_provider_strategy.value.name` inside a
# dynamic block) is indeterminate — reported separately, never a FAIL.
# Module blocks may hold a services = {...} map of MULTIPLE services this
# heuristic cannot separate, so module-block conflicts are warn-grade.
CPS_SCAN=""
if [ ${#TF_FILES[@]} -gt 0 ]; then
    CPS_SCAN=$(awk 'FNR==1{inres=0}
        /^[[:space:]]*(#|\/\/)/{next}
        /^(resource "aws_ecs_service"|resource "aws_ecs_cluster_capacity_providers")/{inres=1; ismod=0; farg=0; cust=0; dyn=0; name=FILENAME": "$0}
        /^module "/{inres=1; ismod=1; farg=0; cust=0; dyn=0; name=FILENAME": "$0}
        inres && /capacity_provider[[:space:]]*=/{
            if ($0 ~ /=[[:space:]]*"FARGATE(_SPOT)?"/) farg=1
            else if ($0 ~ /=[[:space:]]*"[^$]/) cust=1
            else dyn=1
        }
        inres && /^}/{
            if (farg && cust) print (ismod ? "MODMIX|" : "MIX|") name
            else if (dyn && (farg || cust)) print "DYN|" name
            inres=0
        }' "${TF_FILES[@]}" 2>/dev/null || true)
fi
CPS_MIXED=$(echo "$CPS_SCAN" | grep '^MIX|' | sed 's/^MIX|//' || true)
CPS_MODMIX=$(echo "$CPS_SCAN" | grep '^MODMIX|' | sed 's/^MODMIX|//' || true)
CPS_DYN=$(echo "$CPS_SCAN" | grep '^DYN|' | sed 's/^DYN|//' || true)
if [ -n "$CPS_MIXED" ]; then
    fail "capacity_provider_strategy mixes FARGATE/FARGATE_SPOT with a custom (ASG/MI) provider in the same strategy — a single strategy cannot mix provider types (CR 2): $CPS_MIXED"
else
    pass "No capacity provider strategy mixes Fargate and non-Fargate provider types"
fi
if [ -n "$CPS_MODMIX" ]; then
    warn "Fargate and custom providers both referenced in one module block — module services map: verify per-service; heuristic cannot separate entries (CR 2): $CPS_MODMIX"
fi
if [ -n "$CPS_DYN" ]; then
    warn "dynamic strategy block — cannot statically verify type mixing (unquoted capacity_provider reference, CR 2): $CPS_DYN"
fi

# --- 6. Managed Instances wiring (CR 3) ---
echo ""
echo "6. Managed Instances wiring (CR 3)"
echo "-------------------------------------------"

if tf_grep_q 'managed_instances_provider'; then
    if tf_grep_q 'infrastructure_role_arn'; then
        pass "MI provider sets infrastructure_role_arn"
    else
        fail "managed_instances_provider without infrastructure_role_arn — capacity provider create will fail"
    fi
    if tf_grep_q 'ec2_instance_profile_arn'; then
        pass "MI launch template sets ec2_instance_profile_arn"
    else
        fail "managed_instances_provider without ec2_instance_profile_arn — required"
    fi
    if tf_grep_q 'AmazonECSInfrastructureRolePolicyForManagedInstances' || tf_grep_q 'create_infrastructure_iam_role'; then
        pass "MI infrastructure role policy attachment (or module-managed role) present"
    else
        warn "AmazonECSInfrastructureRolePolicyForManagedInstances attachment not found — verify the infrastructure role carries it"
    fi
    if tf_grep_q 'MANAGED_INSTANCES'; then
        pass "MANAGED_INSTANCES appears in requires_compatibilities scope"
    else
        fail "MI capacity provider present but no task definition includes MANAGED_INSTANCES in requires_compatibilities"
    fi
    # MI + ASG provider in the same resource is invalid
    MI_ASG_MIX=""
    if [ ${#TF_FILES[@]} -gt 0 ]; then
        MI_ASG_MIX=$(awk 'FNR==1{inres=0}
            /^[[:space:]]*(#|\/\/)/{next}
            /^resource "aws_ecs_capacity_provider"/{inres=1; mi=0; asg=0; name=FILENAME": "$0}
            inres && /managed_instances_provider/{mi=1}
            inres && /auto_scaling_group_provider/{asg=1}
            inres && /^}/{if (mi && asg) print name; inres=0}' "${TF_FILES[@]}" 2>/dev/null || true)
    fi
    if [ -n "$MI_ASG_MIX" ]; then
        fail "Capacity provider declares BOTH managed_instances_provider and auto_scaling_group_provider (mutually exclusive): $MI_ASG_MIX"
    else
        pass "No capacity provider mixes MI and ASG blocks"
    fi
else
    pass "No Managed Instances provider — MI checks skipped"
fi

# --- 7. awslogs mode explicitness (CR 4) ---
echo ""
echo "7. awslogs mode (CR 4)"
echo "-------------------------------------------"

if tf_grep_q '"?awslogs"?' ; then
    # Any file that configures awslogs must also set mode explicitly
    MODE_MISSING=""
    while IFS= read -r -d '' f; do
        if ! grep -qE '"?mode"?\s*[:=]\s*"?(non-)?blocking"?' "$f"; then
            MODE_MISSING="$MODE_MISSING $f"
        fi
    done < <(grep -rlZ --include='*.tf' --exclude-dir=.terraform 'awslogs' "$PROJECT_DIR" 2>/dev/null || true)
    if [ -z "$MODE_MISSING" ]; then
        pass "Every file configuring awslogs sets an explicit mode"
        # Blocking mode needs a recorded justification (comment) nearby
        if grep -rqE '"?mode"?\s*[:=]\s*"blocking"' "$PROJECT_DIR" --include='*.tf' --exclude-dir=.terraform 2>/dev/null; then
            if grep -rqiE '(audit|guaranteed|justif|compliance).*' "$PROJECT_DIR" --include='*.tf' --exclude-dir=.terraform 2>/dev/null; then
                pass "blocking mode present with an inline justification comment"
            else
                warn "awslogs mode=blocking found without a justification comment — blocking stalls the app if CloudWatch is unreachable (default flipped to non-blocking 2025-06-25)"
            fi
        fi
    else
        fail "awslogs configured without explicit mode (account defaultLogDriverMode makes behavior non-deterministic):$MODE_MISSING"
    fi
else
    warn "No awslogs configuration found — confirm logging is configured (FireLens/splunk are also acceptable)"
fi

# --- 8. IAM trust scoping (CR 5) ---
echo ""
echo "8. IAM role checks (CR 5)"
echo "-------------------------------------------"

# Cluster-scoped SourceArn is documented-unsupported
if tf_grep_code_q 'aws:SourceArn.*:cluster/'; then
    fail "Cluster-scoped aws:SourceArn found in a trust policy — not supported for ecs-tasks trust; use arn:aws:ecs:<region>:<account>:* (CR 5)"
    tf_grep_code 'aws:SourceArn.*:cluster/' | head -5
else
    pass "No cluster-scoped aws:SourceArn in trust policies"
fi

if tf_grep_q 'execution_role_arn' && tf_grep_q 'task_role_arn'; then
    EXEC_ROLE=$(tf_grep 'execution_role_arn\s*=' | head -1 | sed -E 's/.*=[[:space:]]*//' || true)
    TASK_ROLE=$(tf_grep 'task_role_arn\s*=' | head -1 | sed -E 's/.*=[[:space:]]*//' || true)
    if [ -n "$EXEC_ROLE" ] && [ "$EXEC_ROLE" = "$TASK_ROLE" ]; then
        fail "execution_role_arn and task_role_arn reference the same role — separate them (CR 5)"
    else
        pass "execution_role_arn and task_role_arn are distinct references"
    fi
elif tf_grep_q 'terraform-aws-modules/ecs'; then
    pass "Roles delegated to the ecs module (creates separate roles by default)"
else
    warn "Could not verify execution/task role separation — check manually"
fi

# --- 9. Deployment strategy consistency (CR 6) ---
echo ""
echo "9. Deployment strategy checks (CR 6)"
echo "-------------------------------------------"

if [ "$EXPRESS_ONLY" -eq 1 ]; then
    skip_check "deployment strategy checks" "Express project — strategy/circuit-breaker/LB managed by the ECS infrastructure role (N/A)" 0
elif tf_grep_q 'strategy\s*=\s*"(BLUE_GREEN|LINEAR|CANARY)"'; then
    # Resource-block granular: circuit breaker is rolling-only, so it must
    # not sit on the SAME service block as a blue/green-family strategy.
    # (A rolling service and a BG service may legitimately share a file.)
    # Module blocks may hold a services = {...} map of multiple services this
    # heuristic cannot separate — those conflicts are warn-grade.
    CB_SCAN=""
    if [ ${#TF_FILES[@]} -gt 0 ]; then
        CB_SCAN=$(awk 'FNR==1{inres=0}
            /^[[:space:]]*(#|\/\/)/{next}
            /^resource "aws_ecs_service"/{inres=1; ismod=0; bg=0; cb=0; name=FILENAME": "$0}
            /^module "/{inres=1; ismod=1; bg=0; cb=0; name=FILENAME": "$0}
            inres && /strategy[[:space:]]*=[[:space:]]*"(BLUE_GREEN|LINEAR|CANARY)"/{bg=1}
            inres && /deployment_circuit_breaker/{cb=1}
            inres && /^}/{if (bg && cb) print (ismod ? "MOD|" : "RES|") name; inres=0}' "${TF_FILES[@]}" 2>/dev/null || true)
    fi
    CB_CONFLICTS=$(echo "$CB_SCAN" | grep '^RES|' | sed 's/^RES|//' || true)
    CB_MOD_CONFLICTS=$(echo "$CB_SCAN" | grep '^MOD|' | sed 's/^MOD|//' || true)
    if [ -n "$CB_CONFLICTS" ]; then
        fail "Circuit breaker configured on the same service block as a blue/green-family strategy — circuit breaker is rolling-only: $CB_CONFLICTS"
    else
        pass "No service block mixes a blue/green-family strategy with the deployment circuit breaker"
    fi
    if [ -n "$CB_MOD_CONFLICTS" ]; then
        warn "Blue/green-family strategy and circuit breaker both present in one module block — module services map: verify per-service; heuristic cannot separate entries: $CB_MOD_CONFLICTS"
    fi
    # LB requirement split: LINEAR/CANARY need managed traffic shifting;
    # BLUE_GREEN without an LB is documented-valid (headless) — warn only.
    if tf_grep_q 'load_balancer|service_connect_configuration'; then
        pass "Load balancer / Service Connect present for blue/green-family strategy"
    elif tf_grep_q 'strategy\s*=\s*"(LINEAR|CANARY)"'; then
        fail "LINEAR/CANARY requires ALB, NLB, or Service Connect for traffic shifting — none found"
    else
        warn "headless blue/green (no managed traffic shifting) — confirm intent"
    fi
else
    # Rolling services should have the circuit breaker
    if tf_grep_q 'aws_ecs_service' || tf_grep_q 'terraform-aws-modules/ecs'; then
        if tf_grep_q 'deployment_circuit_breaker|circuit_breaker'; then
            pass "Rolling services configure the deployment circuit breaker"
        else
            warn "No deployment_circuit_breaker found — rolling services should enable it with rollback"
        fi
    fi
fi

if tf_grep_code_q 'CODE_DEPLOY|aws_codedeploy'; then
    fail "CodeDeploy controller/resources found — generate native ECS strategies for new services (CR 6)"
else
    pass "No CodeDeploy deployment resources"
fi

# --- 10. App Mesh ban (CR 7) ---
echo ""
echo "10. Service mesh check (CR 7)"
echo "-------------------------------------------"

# Ignore comment lines (# or //) so prose mentions of App Mesh don't FAIL
APPMESH_HITS=$(tf_grep 'aws_appmesh_|appmesh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*(#|//)' || true)
if [ -n "$APPMESH_HITS" ]; then
    fail "App Mesh resources found — App Mesh end of support 2026-09-30; use Service Connect"
    echo "$APPMESH_HITS" | head -3
else
    pass "No App Mesh resources"
fi

# --- 11. Fargate exclusions (CR 10) ---
echo ""
echo "11. Fargate parameter exclusions (CR 10)"
echo "-------------------------------------------"

if tf_grep_q '"FARGATE"'; then
    FARGATE_VIOLATIONS=""
    for p in '"privileged"\s*:\s*true' 'privileged\s*=\s*true' '"gpu"' '"links"' '"placementConstraints"' '"dockerSecurityOptions"'; do
        if tf_grep_q "$p"; then
            FARGATE_VIOLATIONS="$FARGATE_VIOLATIONS $p"
        fi
    done
    if [ -n "$FARGATE_VIOLATIONS" ]; then
        warn "Possible Fargate-excluded parameters found ($FARGATE_VIOLATIONS) — verify they are only on EC2/MI task definitions"
    else
        pass "No Fargate-excluded parameters detected"
    fi
else
    pass "No FARGATE compatibility declared — exclusion checks skipped"
fi

# --- 12. Container hygiene (CR 12 + image/secret hygiene) ---
echo ""
echo "12. Container hygiene"
echo "-------------------------------------------"

# ECS Exec needs writable paths for the SSM agent; readonly root breaks it.
# Project-level co-occurrence heuristic (warn-grade).
if tf_grep_q 'enable_execute_command\s*=\s*true' && tf_grep_q '"?readonlyRootFilesystem"?\s*[:=]\s*true'; then
    warn "enable_execute_command = true and readonlyRootFilesystem: true both present in this project — ECS Exec needs writable paths for the SSM agent; verify they are not on the same service/task (file-level heuristic)"
else
    pass "No ECS Exec / readonlyRootFilesystem co-occurrence"
fi

# :latest image tags — non-deterministic deploys; pin a tag or digest
if tf_grep_q '"?image"?\s*[:=]\s*"[^"]*:latest"'; then
    warn "Image tag :latest found — pin an immutable tag or digest:"
    tf_grep '"?image"?\s*[:=]\s*"[^"]*:latest"' | head -5
else
    pass "No :latest image tags"
    if tf_grep_q '"?image"?\s*[:=]\s*(var\.|local\.|"\$\{)'; then
        echo "  note: image references use var/local interpolation — tag pinning cannot be checked statically"
    fi
fi

# Plaintext credential-looking names inside environment blocks — use
# secrets/valueFrom (SSM Parameter Store or Secrets Manager) instead.
ENV_SECRET_HITS=""
if [ ${#TF_FILES[@]} -gt 0 ]; then
    ENV_SECRET_HITS=$(awk 'FNR==1{env=0}
        /"?environment"?[[:space:]]*[:=][[:space:]]*\[/{env=1}
        env && /(PASSWORD|SECRET|TOKEN|API_KEY)/{print FILENAME":"FNR": "$0}
        env && /\]/{env=0}' "${TF_FILES[@]}" 2>/dev/null || true)
fi
if [ -n "$ENV_SECRET_HITS" ]; then
    warn "Suspicious plaintext credential names inside environment blocks — move to secrets/valueFrom (heuristic; verify):"
    echo "$ENV_SECRET_HITS" | head -5
else
    pass "No suspicious plaintext credential names in environment blocks"
fi

# --- 13. Private networking endpoints (CR 8) ---
echo ""
echo "13. VPC endpoint sanity (CR 8)"
echo "-------------------------------------------"

if tf_grep_q 'vpc_endpoint|aws_vpc_endpoint'; then
    if tf_grep_q 'ecr\.api' && tf_grep_q 'ecr\.dkr'; then
        pass "ECR api + dkr endpoints present"
    else
        warn "VPC endpoints configured but ecr.api/ecr.dkr pair not both found"
    fi
    # Require S3-endpoint context: service name ending .s3, an explicit
    # Gateway endpoint type, or an s3_gateway module key — a bare "Gateway"
    # word (e.g. "Internet Gateway" in a comment) must NOT satisfy this.
    if tf_grep_q 'com\.amazonaws\.[a-z0-9-]+\.s3|service_name\s*=\s*"[^"]*\.s3"|vpc_endpoint_type\s*=\s*"Gateway"|service_type\s*=\s*"Gateway"|s3_gateway'; then
        pass "S3 gateway endpoint present (ECR layers live in S3)"
    else
        fail "VPC endpoints configured without an S3 gateway endpoint — image pulls will hang (most-missed endpoint)"
    fi
    if tf_grep_q 'enable_execute_command\s*=\s*true'; then
        if tf_grep_q 'ssmmessages'; then
            pass "ECS Exec enabled and ssmmessages endpoint present"
        else
            fail "ECS Exec enabled in a VPC-endpoint project without an ssmmessages endpoint (it is ssmmessages, not ssm)"
        fi
    fi
else
    pass "No VPC endpoints generated (public/NAT networking assumed)"
fi

# --- 14. terraform validate ---
echo ""
echo "14. Terraform validate"
echo "-------------------------------------------"

if command -v terraform &>/dev/null; then
    if [ -d "$PROJECT_DIR/.terraform" ]; then
        if terraform -chdir="$PROJECT_DIR" validate 2>&1 | grep -q "Success"; then
            pass "terraform validate passes"
        else
            fail "terraform validate reported errors — inspect 'terraform -chdir=$PROJECT_DIR validate' output"
        fi
    else
        skip_check "terraform validate" "project not initialized (run 'terraform init' first, then re-validate)" 1
    fi
else
    skip_check "terraform validate" "terraform binary not found" 1
fi

# --- Summary ---
echo ""
echo "==========================================="
echo "Validation Summary"
echo "==========================================="
echo -e "${GREEN}Passed:${NC}  $PASS"
echo -e "${RED}Failed:${NC}  $FAIL"
echo -e "${YELLOW}Warnings:${NC} $WARN"
echo -e "${YELLOW}Skipped:${NC} ${#SKIPPED[@]}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VALIDATION FAILED${NC} — fix the issues above before deploying"
    exit 1
fi

if [ "${#SKIPPED[@]}" -gt 0 ]; then
    SKIPLIST=$(printf '%s, ' "${SKIPPED[@]}")
    SKIPLIST=${SKIPLIST%, }
    if [ "$SKIP_FAILGRADE" -eq 1 ]; then
        echo -e "${YELLOW}VALIDATION PASSED WITH SKIPS${NC} — semantic validation did not run (${#SKIPPED[@]} checks skipped: $SKIPLIST)"
        exit 2
    fi
    echo -e "${GREEN}VALIDATION PASSED${NC} (${#SKIPPED[@]} checks skipped: $SKIPLIST)"
    exit 0
fi

echo -e "${GREEN}VALIDATION PASSED${NC}"
exit 0
