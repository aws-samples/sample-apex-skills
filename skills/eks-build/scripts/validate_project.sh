#!/usr/bin/env bash
# validate_project.sh — Post-generation validation for eks-build skill
# Usage: ./validate_project.sh <project-directory>
#
# Validates that a generated EKS project is structurally correct and ready for
# terraform init/plan/apply. Does NOT require AWS credentials or a running cluster.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

pass() { echo -e "${GREEN}✓${NC} $1"; (( PASS++ )) || true; }
fail() { echo -e "${RED}✗${NC} $1"; (( FAIL++ )) || true; }
warn() { echo -e "${YELLOW}!${NC} $1"; (( WARN++ )) || true; }

PROJECT_DIR="${1:?Usage: $0 <project-directory>}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: $PROJECT_DIR is not a directory"
    exit 1
fi

echo "Validating project: $PROJECT_DIR"
echo "==========================================="

# --- 1. Required Terraform files ---
echo ""
echo "1. Required Terraform files"
echo "-------------------------------------------"

for f in main.tf variables.tf providers.tf versions.tf outputs.tf locals.tf data.tf; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        pass "$f exists"
    else
        fail "$f missing"
    fi
done

# --- 2. Config files ---
echo ""
echo "2. Configuration files"
echo "-------------------------------------------"

for f in configs/cluster.yaml configs/compute.yaml configs/addons.yaml configs/backend.hcl; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        pass "$f exists"
    else
        fail "$f missing"
    fi
done

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
    warn "terraform not found — skipping fmt check"
fi

# --- 4. before_compute check ---
echo ""
echo "4. before_compute configuration"
echo "-------------------------------------------"

ADDONS_YAML="$PROJECT_DIR/configs/addons.yaml"
if [ -f "$ADDONS_YAML" ]; then
    if grep -q "before_compute.*true" "$ADDONS_YAML" 2>/dev/null; then
        # Check vpc-cni
        if grep -A2 "vpc.cni\|vpc-cni" "$ADDONS_YAML" | grep -q "before_compute.*true"; then
            pass "vpc-cni has before_compute: true"
        else
            fail "vpc-cni missing before_compute: true — nodes will fail on fresh deploy"
        fi
        # Check eks-pod-identity-agent
        if grep -A2 "pod.identity\|eks-pod-identity" "$ADDONS_YAML" | grep -q "before_compute.*true"; then
            pass "eks-pod-identity-agent has before_compute: true"
        else
            warn "eks-pod-identity-agent missing before_compute: true — Pod Identity may not work"
        fi
    else
        fail "No before_compute: true found in addons.yaml"
    fi
else
    fail "addons.yaml not found"
fi

# --- 5. Two-phase module check (Pattern 1 only) ---
echo ""
echo "5. Two-phase module architecture"
echo "-------------------------------------------"

MAIN_TF="$PROJECT_DIR/main.tf"
if [ -f "$MAIN_TF" ]; then
    if grep -q 'eks-blueprints-addons' "$MAIN_TF"; then
        # Pattern 1 — check for two-phase split
        ADDON_MODULE_COUNT=$(grep -c 'source.*eks-blueprints-addons' "$MAIN_TF" || true)
        if [ "$ADDON_MODULE_COUNT" -ge 2 ]; then
            pass "Two-phase module architecture detected ($ADDON_MODULE_COUNT instances)"
            # Check for depends_on between phases
            if grep -q 'depends_on.*eks_addons_webhooks\|depends_on.*phase_1\|depends_on.*webhooks' "$MAIN_TF"; then
                pass "Phase 2 depends_on Phase 1 found"
            else
                warn "Could not verify depends_on between phases — check manually"
            fi
        else
            fail "Only $ADDON_MODULE_COUNT eks-blueprints-addons instance — need 2 for webhook ordering"
        fi
    elif grep -q 'argocd\|gitops' "$MAIN_TF"; then
        pass "Pattern 2 (ArgoCD) detected — two-phase not required"
    else
        warn "Could not determine pattern from main.tf"
    fi
else
    fail "main.tf not found"
fi

# --- 6. Module source paths ---
echo ""
echo "6. Module source paths"
echo "-------------------------------------------"

if [ -f "$MAIN_TF" ]; then
    # Extract module source paths and check they exist
    MODULE_SOURCES=$(grep -oP 'source\s*=\s*"\./modules/[^"]+' "$MAIN_TF" | sed 's/source *= *"//g' || true)
    if [ -n "$MODULE_SOURCES" ]; then
        while IFS= read -r mod_path; do
            FULL_PATH="$PROJECT_DIR/$mod_path"
            if [ -d "$FULL_PATH" ]; then
                pass "Module $mod_path exists"
            else
                fail "Module $mod_path referenced but directory not found"
            fi
        done <<< "$MODULE_SOURCES"
    else
        pass "No local module sources found (using registry modules)"
    fi
fi

# --- 7. GitOps artifacts (Pattern 2 only) ---
echo ""
echo "7. GitOps artifacts"
echo "-------------------------------------------"

GITOPS_DIR=""
if [ -d "$PROJECT_DIR/gitops" ]; then
    GITOPS_DIR="$PROJECT_DIR/gitops"
elif [ -d "$PROJECT_DIR/../gitops" ]; then
    GITOPS_DIR="$PROJECT_DIR/../gitops"
fi

if [ -n "$GITOPS_DIR" ]; then
    for f in addons/applicationset.yaml bootstrap/argocd-projects.yaml; do
        if [ -f "$GITOPS_DIR/$f" ]; then
            pass "gitops/$f exists"
        else
            fail "gitops/$f missing"
        fi
    done
elif grep -q 'argocd\|gitops' "$MAIN_TF" 2>/dev/null; then
    fail "Pattern 2 detected but gitops/ directory not found"
else
    pass "Pattern 1 — gitops/ not required"
fi

# --- 8. Version pinning check ---
echo ""
echo "8. Version pinning"
echo "-------------------------------------------"

if [ -f "$ADDONS_YAML" ]; then
    # Check if chart_version is set for LBC
    if grep -A5 "load_balancer_controller\|aws_load_balancer" "$ADDONS_YAML" | grep -q "chart_version"; then
        pass "LBC chart_version is pinned"
    elif grep -q "load_balancer_controller\|aws_load_balancer" "$ADDONS_YAML"; then
        warn "LBC enabled but chart_version not pinned — module default will CrashLoop"
    fi

    # Check if vpcId is set for LBC
    if grep -A10 "load_balancer_controller\|aws_load_balancer" "$ADDONS_YAML" | grep -q "vpcId"; then
        pass "LBC vpcId is set"
    elif grep -q "load_balancer_controller\|aws_load_balancer" "$ADDONS_YAML"; then
        warn "LBC enabled but vpcId not set — IMDS fallback may fail"
    fi
fi

# --- 9. Velero configuration ---
echo ""
echo "9. Velero configuration"
echo "-------------------------------------------"

if [ -f "$ADDONS_YAML" ]; then
    if grep -q "velero" "$ADDONS_YAML"; then
        if grep -A10 "velero" "$ADDONS_YAML" | grep -q "upgradeCRDs.*false"; then
            pass "Velero upgradeCRDs set to false"
        else
            warn "Velero may need upgradeCRDs: false (bitnami/kubectl image may not exist)"
        fi
    else
        pass "Velero not configured"
    fi
fi

# --- 10. Multus check ---
echo ""
echo "10. Multus safety check"
echo "-------------------------------------------"

if [ -f "$ADDONS_YAML" ]; then
    if grep -A3 "multus" "$ADDONS_YAML" | grep -q "enabled.*true"; then
        fail "Multus is ENABLED — thick-plugin breaks ALL pod creation (see lessons-learned)"
    else
        pass "Multus is disabled or not configured"
    fi
fi

# --- 11. terraform validate (if credentials not required) ---
echo ""
echo "11. Terraform validate"
echo "-------------------------------------------"

if command -v terraform &>/dev/null; then
    # Only run if .terraform exists (already initialized)
    if [ -d "$PROJECT_DIR/.terraform" ]; then
        if terraform -chdir="$PROJECT_DIR" validate 2>&1 | grep -q "Success"; then
            pass "terraform validate passes"
        else
            warn "terraform validate had issues (may need init first)"
        fi
    else
        warn "Not initialized — run 'terraform init' first, then re-validate"
    fi
else
    warn "terraform not found — skipping validate"
fi

# --- Summary ---
echo ""
echo "==========================================="
echo "Validation Summary"
echo "==========================================="
echo -e "${GREEN}Passed:${NC}  $PASS"
echo -e "${RED}Failed:${NC}  $FAIL"
echo -e "${YELLOW}Warnings:${NC} $WARN"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VALIDATION FAILED${NC} — fix the issues above before deploying"
    exit 1
else
    echo -e "${GREEN}VALIDATION PASSED${NC}"
    exit 0
fi
