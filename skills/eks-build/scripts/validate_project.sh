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

# --- 11. Karpenter discovery tags ---
echo ""
echo "11. Karpenter discovery tags"
echo "-------------------------------------------"

# Karpenter launches nodes only into subnets and security groups whose tags
# match the EC2NodeClass selector terms; a mismatch fails silently at runtime.
# POSIX awk only (no gawk extensions, no grep -P), so this runs on macOS too.

# Shared parser: split a `key: value` (YAML) or `"key" = value` (HCL) line.
# Sets PK (key), PV (normalised value), PKIND (L = literal, E = expression).
KARP_PARSE_AWK=$(cat <<'AWK'
function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
function parse(line,   sep, hcl) {
    line = trim(line)
    sub(/^-[[:space:]]*/, "", line)
    sub(/^(merge\(|\{|\()[[:space:]]*/, "", line)
    if (!match(line, /^["']?[A-Za-z0-9._\/-]+["']?[[:space:]]*[:=]/)) return 0
    sep = substr(line, RLENGTH, 1)
    if (substr(line, RLENGTH + 1, 1) == "=") return 0
    hcl = (sep == "=")
    PK = substr(line, 1, RLENGTH - 1)
    gsub(/["'[:space:]]/, "", PK)
    PV = substr(line, RLENGTH + 1)
    sub(/[[:space:]]+#.*$/, "", PV)
    PV = trim(PV)
    if (PV == "" || PV ~ /^\{/) return 0
    if (index(PV, "${") > 0) PKIND = "E"
    else if (PV ~ /^["']/) PKIND = "L"
    else PKIND = (hcl ? "E" : "L")
    gsub(/\$\{/, "", PV)
    gsub(/[]}"',[:space:]]/, "", PV)
    if (PV == "") return 0
    return 1
}
AWK
)

# EC2NodeClass selectors: prints "<subnet|sg> <key> <value> <L|E>" per selector.
KARP_SEL_AWK="$KARP_PARSE_AWK"$(cat <<'AWK'

BEGIN { OFS = "\t" }
FNR == 1 { sel = ""; want = 0; nxt = 0 }
{
    line = $0
    if (match(line, /subnetSelectorTerms/)) {
        sel = "subnet"; want = 1; nxt = 0; line = substr(line, RSTART + RLENGTH)
    } else if (match(line, /securityGroupSelectorTerms/)) {
        sel = "sg"; want = 1; nxt = 0; line = substr(line, RSTART + RLENGTH)
    } else if (line ~ /SelectorTerms|^---|kind[[:space:]]*[:=]/) {
        want = 0; nxt = 0; next
    }
    if (!want) next
    if (nxt) {
        if (trim(line) == "") next
        if (parse(line)) print sel, PK, PV, PKIND
        want = 0; nxt = 0; next
    }
    if (line ~ /(^|[^A-Za-z0-9_])id[[:space:]]*[:=]/) { print sel, "__id__", "-", "L"; want = 0; next }
    if (match(line, /tags[[:space:]]*[:=]/)) {
        rest = trim(substr(line, RSTART + RLENGTH))
        sub(/^\{[[:space:]]*/, "", rest)
        if (rest == "") { nxt = 1; next }
        if (parse(rest)) print sel, PK, PV, PKIND
        want = 0
    }
}
AWK
)

# Tags the Terraform applies: prints "<subnet|sg|clustersg> <key> <value> <L|E>".
# Sources: aws_ec2_tag resources, the VPC module's private_subnet_tags and the
# EKS module's node_security_group_tags. A map passed by reference (for example
# `private_subnet_tags = local.subnet_tags`) prints key "__ref__".
KARP_TAG_AWK="$KARP_PARSE_AWK"$(cat <<'AWK'

BEGIN { OFS = "\t" }
FNR == 1 { mode = "" }
{
    line = $0
    if (line ~ /^[[:space:]]*#/) next
    if (mode == "") {
        if (line ~ /resource[[:space:]]+"aws_ec2_tag"/) {
            mode = "ec2tag"; depth = 0; seen = 0; blob = ""; tk = ""; tv = ""; tkind = ""
        } else if (match(line, /private_subnet_tags[[:space:]]*=/)) {
            mode = "subnet"; depth = 0; seen = 0; line = substr(line, RSTART + RLENGTH)
        } else if (match(line, /node_security_group_tags[[:space:]]*=/)) {
            mode = "sg"; depth = 0; seen = 0; line = substr(line, RSTART + RLENGTH)
        } else next
    }
    o = gsub(/\{/, "{", line); c = gsub(/\}/, "}", line)
    if (o > 0) seen = 1
    if (mode == "ec2tag") {
        blob = blob " " line
        if (parse(line)) {
            if (PK == "key") tk = PV
            else if (PK == "value") { tv = PV; tkind = PKIND }
        }
    } else if (!seen) {
        print mode, "__ref__", "-", "E"; mode = ""; next
    } else if (parse(line)) {
        print mode, PK, PV, PKIND
    }
    depth += o - c
    if (seen && depth <= 0) {
        if (mode == "ec2tag" && tk != "" && tv != "") {
            if (blob ~ /subnet/) print "subnet", tk, tv, tkind
            if (blob ~ /security_group/) print "sg", tk, tv, tkind
            if (blob ~ /cluster_primary_security_group|cluster_security_group/) print "clustersg", tk, tv, tkind
        }
        mode = ""
    }
}
AWK
)

# Compare one selector against the applied tags of its resource type.
karp_check() {
    local type="$1" key="$2" val="$3" kind="$4" label
    local matched=0 same_key=0 lit_diff=0 has_ref=0 seen_vals="" t k v vk
    [ "$type" = "subnet" ] && label="subnet" || label="security group"
    if [ "$key" = "__id__" ]; then
        pass "EC2NodeClass $label selector uses ids (no discovery tag to check)"
        return
    fi
    while IFS="$(printf '\t')" read -r t k v vk; do
        [ "$t" = "$type" ] || continue
        if [ "$k" = "__ref__" ]; then has_ref=1; continue; fi
        [ "$k" = "$key" ] || continue
        if [ "$v" = "$val" ]; then matched=1; break; fi
        same_key=1
        seen_vals="$seen_vals $v"
        if [ "$kind" = "L" ] && [ "$vk" = "L" ]; then lit_diff=1; fi
    done <<< "$KARP_APPLIED"
    if [ "$matched" -eq 1 ]; then
        pass "EC2NodeClass $label selector $key=$val matches a tag the project applies"
    elif [ "$lit_diff" -eq 1 ]; then
        fail "EC2NodeClass $label selector $key=$val does not match the applied value(s):$seen_vals -- Karpenter will find no $label"
    elif [ "$same_key" -eq 1 ]; then
        warn "EC2NodeClass $label selector $key=$val vs applied value(s):$seen_vals -- expressions differ, confirm they resolve to the same value"
    elif [ "$has_ref" -eq 1 ]; then
        warn "EC2NodeClass $label selector $key=$val: $label tags are passed by reference, check them manually"
    else
        fail "EC2NodeClass $label selector tag $key is not applied to any $label by this project (aws_ec2_tag, private_subnet_tags or node_security_group_tags)"
    fi
}

KARP_DIRS=("$PROJECT_DIR")
if [ -n "$GITOPS_DIR" ] && [ "$GITOPS_DIR" = "$PROJECT_DIR/../gitops" ]; then
    KARP_DIRS+=("$GITOPS_DIR")
fi
KARP_NC_LIST=$(find "${KARP_DIRS[@]}" -type f \( -name '*.tf' -o -name '*.yaml' -o -name '*.yml' -o -name '*.tftpl' -o -name '*.tpl' \) ! -path '*/.terraform/*' -exec grep -l 'EC2NodeClass' {} + 2>/dev/null || true)

if [ -z "$KARP_NC_LIST" ]; then
    pass "Karpenter not configured (no EC2NodeClass found)"
else
    KARP_NC_FILES=()
    while IFS= read -r f; do KARP_NC_FILES+=("$f"); done <<< "$KARP_NC_LIST"
    KARP_TF_FILES=()
    while IFS= read -r f; do
        [ -n "$f" ] && KARP_TF_FILES+=("$f")
    done <<< "$(find "$PROJECT_DIR" -type f -name '*.tf' ! -path '*/.terraform/*' 2>/dev/null || true)"

    KARP_SELECTORS=$(awk "$KARP_SEL_AWK" "${KARP_NC_FILES[@]}")
    KARP_APPLIED=""
    if [ "${#KARP_TF_FILES[@]}" -gt 0 ]; then
        KARP_APPLIED=$(awk "$KARP_TAG_AWK" "${KARP_TF_FILES[@]}")
    fi

    if [ -z "$KARP_SELECTORS" ]; then
        warn "EC2NodeClass found but its subnet/security group selector tags could not be read -- check manually"
    else
        while IFS="$(printf '\t')" read -r s_type s_key s_val s_kind; do
            karp_check "$s_type" "$s_key" "$s_val" "$s_kind"
        done <<< "$KARP_SELECTORS"
    fi

    # The baseline tags the cluster primary security group for discovery.
    KARP_SG_KEY=$(printf '%s\n' "$KARP_SELECTORS" | awk -F '\t' '$1 == "sg" && $2 != "__id__" { print $2; exit }')
    if [ -n "$KARP_SG_KEY" ]; then
        if printf '%s\n' "$KARP_APPLIED" | awk -F '\t' -v k="$KARP_SG_KEY" '$1 == "clustersg" && $2 == k { f = 1 } END { exit !f }'; then
            pass "Cluster security group carries the $KARP_SG_KEY tag"
        else
            warn "Cluster security group is not tagged $KARP_SG_KEY (no aws_ec2_tag on cluster_primary_security_group_id)"
        fi
    fi
fi

# --- 12. terraform validate (if credentials not required) ---
echo ""
echo "12. Terraform validate"
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
