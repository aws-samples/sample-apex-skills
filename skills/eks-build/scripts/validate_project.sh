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
# A relative path that starts with "-" would be read as an option by find, grep and terraform.
case "$PROJECT_DIR" in -*) PROJECT_DIR="./$PROJECT_DIR" ;; esac

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
if [ -f "$PROJECT_DIR/configs/backend.hcl" ] && ! grep -Eq '^[[:space:]]*use_lockfile[[:space:]]*=[[:space:]]*true([[:space:]#]|$)' "$PROJECT_DIR/configs/backend.hcl" 2>/dev/null; then
    warn "configs/backend.hcl: could not confirm use_lockfile = true (S3 state locking; DynamoDB locking is deprecated)"
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
    # Extract module source paths and check they exist.
    # sed -E (POSIX.1-2024; GNU and BSD sed); no grep -P, which BSD/macOS grep lacks.
    # The `source = "./modules/..."` attribute must start the line or follow a `{`
    # on it (a one-line module block), so a `#` or `//` commented line and a second
    # match in a trailing comment are not read; lines inside a /* */ block are.
    if ! MODULE_SOURCES=$(sed -n -E 's|^([^#/]*[{])?[[:space:]]*source[[:space:]]*=[[:space:]]*"(\./modules/[^"]+)".*|\2|p' "$MAIN_TF"); then
        # Unreadable main.tf: report once and skip the rest of this section.
        fail "Could not read module sources from main.tf"
    elif [ "$(grep -Ec '^([^#/]*[{])?[[:space:]]*source[[:space:]]*=[[:space:]]*"\./modules/' "$MAIN_TF")" -gt "$(printf '%s' "$MODULE_SOURCES" | grep -c .)" ]; then
        fail "main.tf references ./modules/ but not every module source could be parsed"
    elif [ -n "$MODULE_SOURCES" ]; then
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
# match the EC2NodeClass selector terms (terms are ORed, the tags inside one
# term are ANDed); a mismatch fails silently at runtime. Intended to run on
# macOS too (POSIX awk, no grep -P), but not run there.

# Shared helpers. strip() drops # and // comments; tok() splits a line into
# T[1..n]: { } [ ] ( ) , outside quotes and ${...}, and trimmed text between;
# parse() reads `key: value` (YAML) or `"key" = value` (HCL) into PK, PV and
# PKIND (L literal, E expression): 1 with a value, 2 for a bare key, else 0.
KARP_LIB_AWK=$(cat <<'AWK'
BEGIN { OFS = "\t" }
function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
function strip(s) { sub(/(^|[[:space:]])(#|\/\/).*$/, "", s); return s }
function tok(s,   n, i, c, q, b, ip) {
    n = 0; q = ""; b = ""; ip = 0
    for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (q != "") { b = b c; if (c == q) q = ""; continue }
        if (ip) { b = b c; if (c == "{") ip++; else if (c == "}") ip--; continue }
        if (c == "\"" || c == "'") { q = c; b = b c; continue }
        if (c == "$" && substr(s, i + 1, 1) == "{") { b = b "${"; i++; ip = 1; continue }
        if (index("{}[](),", c)) { if (trim(b) != "") T[++n] = trim(b); b = ""; T[++n] = c; continue }
        b = b c
    }
    if (trim(b) != "") T[++n] = trim(b)
    return n
}
function parse(s,   q, r, hcl) {
    s = trim(s); sub(/^-[[:space:]]*/, "", s)
    if (s ~ /^["']/) {
        q = substr(s, 1, 1); r = index(substr(s, 2), q)
        if (!r) return 0
        PK = substr(s, 2, r - 1); s = trim(substr(s, r + 2))
        if (s !~ /^[:=]/) return 0
        hcl = (substr(s, 1, 1) == "="); s = substr(s, 2)
    } else if (match(s, /^[A-Za-z0-9._\/:-]+[[:space:]]*=/)) {
        PK = trim(substr(s, 1, RLENGTH - 1)); hcl = 1; s = substr(s, RLENGTH + 1)
    } else if (match(s, /^[A-Za-z0-9._\/:-]*[A-Za-z0-9._\/-]:([[:space:]]|$)/)) {
        PK = substr(s, 1, RLENGTH); sub(/:[[:space:]]*$/, "", PK); hcl = 0; s = substr(s, RLENGTH + 1)
    } else return 0
    if (s ~ /^[=>]/) return 0
    PV = trim(s)
    if (PV == "") return 2
    if (index(PV, "${") > 0 || index(PV, "{{") > 0) PKIND = "E"
    else if (PV ~ /^["']/) PKIND = "L"
    else PKIND = (hcl ? "E" : "L")
    gsub(/\$\{/, "", PV); gsub(/[]}"'[:space:]]/, "", PV)
    return (PV == "") ? 0 : 1
}
AWK
)

# EC2NodeClass selectors: "<subnet|sg> <list> <term> <key> <value> <L|E> <file>"
# per tag of every term; key __id__ (id term), __ref__ (tags by reference),
# __bad__ (unreadable tag) or __other__ (no tags or id).
KARP_SEL_AWK="$KARP_LIB_AWK"$(cat <<'AWK'

function out(k, v, kd) { if (!tm) tm = 1; print sel, g, tm, k, v, kd, FILENAME; to++ }
function flush() { if (reg && tm && !to) print sel, g, tm, "__other__", "-", "L", FILENAME }
function newterm() { flush(); tm++; to = 0; tagd = -1; tagc = -1; pend = 0 }
FNR == 1 { flush(); reg = 0 }
END { flush() }
{
    line = strip($0)
    if (line !~ /[^[:space:]]/) next
    ind = match(line, /[^[:space:]]/) - 1
    if (match(line, /(subnet|securityGroup)SelectorTerms/)) {
        flush(); sel = (substr(line, RSTART, 2) == "su") ? "subnet" : "sg"
        g++; reg = 1; ri = ind; d = 0; ld = -1; tm = 0; to = 0; tagd = -1; tagc = -1; pend = 0
        line = substr(line, RSTART + RLENGTH); sub(/^["']?[[:space:]]*[:=]/, "", line); first = 1
    } else if (line ~ /SelectorTerms|^---|^[[:space:]]*["']?kind["']?[[:space:]]*[:=]/) { flush(); reg = 0; next }
    else if (!reg) next
    else first = 0
    if (!first && d == 0) {
        if (ind < ri || (ind == ri && line !~ /^[[:space:]]*-/)) { flush(); reg = 0; next }
        if (tagc >= 0 && ind <= tagc) tagc = -1
        if (match(line, /^[[:space:]]*-[[:space:]]*/)) { newterm(); ind = RLENGTH; line = substr(line, RLENGTH + 1) }
    }
    n = tok(line)
    for (i = 1; i <= n; i++) {
        t = T[i]
        if (t == "{" || t == "[") {
            d++
            if (t == "[" && ld < 0 && d == 1 && !tm) ld = 1
            else if (t == "{" && ld > 0 && d == ld + 1) newterm()
            if (pend) { tagd = d; pend = 0 }
            continue
        }
        if (t == "}" || t == "]") {
            if (d == tagd) tagd = -1
            d--; if (ld > 0 && d < ld) { flush(); reg = 0; break }
            continue
        }
        pend = 0
        if (t == "," || t == "(" || t == ")") continue
        r = parse(t)
        if ((tagd > 0 && d == tagd) || (tagc >= 0 && d == 0)) {
            if (r == 1) out(PK, PV, PKIND); else out("__bad__", "-", "L")
        } else if (r == 2 && PK == "tags") {
            if (i == n && d == 0) tagc = ind; else pend = 1
        } else if (r == 1 && PK == "tags") out("__ref__", "-", "E")
        else if (r == 1 && PK == "id") out("__id__", "-", "L")
    }
}
AWK
)

# Tags the Terraform applies: "<type> <key> <value> <L|E>", type subnet (private
# subnets), pubsubnet, subunk (a subnet target that is neither), sg, clustersg
# or unk (aws_ec2_tag target not identifiable). Inputs read: aws_ec2_tag
# resources and the private_subnet_tags, public_subnet_tags and
# node_security_group_tags maps; a map by reference prints key __ref__.
KARP_TAG_AWK="$KARP_LIB_AWK"$(cat <<'AWK'

function emit(k, v, kd,   x) {
    if (mode != "ec2tag") { print mode, k, v, kd; return }
    x = 0
    if (blob ~ /private_subnet/) { print "subnet", k, v, kd; x = 1 }
    if (blob ~ /public_subnet/) { print "pubsubnet", k, v, kd; x = 1 }
    if (!x && blob ~ /subnet/) { print "subunk", k, v, kd; x = 1 }
    if (blob ~ /cluster_primary_security_group|vpc_config/) print "clustersg", k, v, kd
    if (blob ~ /security_group/) { print "sg", k, v, kd; x = 1 }
    if (!x) print "unk", k, v, kd
}
FNR == 1 { mode = "" }
{
    line = strip($0)
    if (mode == "") {
        if (line ~ /resource[[:space:]]+"aws_ec2_tag"/) {
            mode = "ec2tag"; d = 0; p = 0; seen = 0; blob = ""; tk = ""; tv = ""; kk = ""; tkind = ""
        } else if (match(line, /(private_subnet|public_subnet|node_security_group)_tags[[:space:]]*=/)) {
            mode = substr(line, RSTART, 2)
            mode = (mode == "pr") ? "subnet" : (mode == "pu") ? "pubsubnet" : "sg"
            d = 0; p = 0; seen = 0; ref = 0; line = substr(line, RSTART + RLENGTH)
        } else next
    }
    n = tok(line)
    for (i = 1; i <= n; i++) {
        t = T[i]
        if (t == "{") { d++; seen = 1; continue }
        if (t == "}") { d--; continue }
        if (t == "(") { p++; continue }
        if (t == ")") { p--; continue }
        if (t ~ /^[],[]$/) continue
        r = parse(t)
        if (mode == "ec2tag") {
            if (r == 1 && PK == "key") { tk = PV; kk = PKIND }
            else if (r == 1 && PK == "value") { tv = PV; tkind = PKIND }
            else if (d >= 1) blob = blob " " t
        } else if (d >= 1) {
            if (r == 1) print mode, PK, PV, PKIND
        } else if (!(i < n && T[i + 1] == "(")) ref = 1
    }
    if (d > 0 || p > 0 || (mode == "ec2tag" && !seen)) next
    if (mode == "ec2tag") {
        if (tk != "" && kk == "L" && tv != "") emit(tk, tv, tkind)
        else emit("__ref__", "-", "E")
    } else if (ref || !seen) print mode, "__ref__", "-", "E"
    mode = ""
}
AWK
)

# Judge each selector term. Input: "A" + applied rows, then "S" + selector rows.
# Prints "<P|W|F> <message>" per term, then the cluster security group line.
KARP_EVAL_AWK=$(cat <<'AWK'
BEGIN { FS = OFS = "\t" }
$1 == "A" {
    if ($3 == "__ref__") { REF[$2] = 1; next }
    if (index(KV[$2, $3] " ", " " $4 " ") == 0) KV[$2, $3] = KV[$2, $3] " " $4
    HAS[$2, $3, $4] = 1
    if ($5 == "E") KE[$2, $3] = 1
    next
}
$1 == "S" {
    s = $2 SUBSEP $3
    if (!(s in GS)) { GS[s] = 1; GL[++ng] = s; GT[s] = $2 }
    tid = s SUBSEP $4
    if (!(tid in TS)) { TS[tid] = "P"; TN[s] = $4; f = $8; sub(/.*\//, "", f); TF[tid] = f; TT[tid] = "" }
    if ($5 != "__id__" && $5 != "__other__" && $5 != "__ref__" && $5 != "__bad__")
        TT[tid] = TT[tid] (TT[tid] == "" ? "" : ", ") $5 "=" $6
    judge($2, $5, $6, $7)
    if (res == "W" && TS[tid] == "P") TS[tid] = "W"
    if (res == "F") TS[tid] = "F"
    if (res == "I" && TS[tid] == "P") TS[tid] = "I"
    if (res != "P" && res != "I") TM[tid] = TM[tid] (TM[tid] == "" ? "" : "; ") msg
    if ($2 == "sg" && $5 ~ /discovery/ && SGK != "karpenter.sh/discovery") SGK = $5
}
function judge(ty, k, v, kd,   pub) {
    res = "W"; pub = (ty == "subnet")
    if (k == "__id__") { res = "I"; return }
    if (k == "__other__") { msg = "no tags or id selector, not checked"; return }
    if (k == "__ref__") { msg = "tags passed by reference, check them manually"; return }
    if (k == "__bad__") { msg = "a tag could not be read, check it manually"; return }
    if (index(v, "*")) { msg = k "=" v ": wildcard value, not compared, check manually"; return }
    if ((ty, k, v) in HAS) { res = "P"; return }
    if (pub && (("pubsubnet", k, v) in HAS)) { msg = k "=" v " is applied only to public subnets (public_subnet_tags or an aws_ec2_tag on them): Karpenter would launch nodes there"; return }
    if ((("unk", k, v) in HAS) || (pub && (("subunk", k, v) in HAS))) { msg = k "=" v ": tag target not identifiable, check manually"; return }
    if ((ty, k) in KV) {
        if (kd == "L" && !((ty, k) in KE)) { res = "F"; msg = k "=" v " does not match the applied value(s):" KV[ty, k]; return }
        msg = k "=" v " vs applied value(s):" KV[ty, k] " -- expressions differ (expected when GitOps YAML holds a literal name and Terraform an expression), confirm they resolve to the same value"; return
    }
    if ((("unk", k) in KV) || (pub && ((("subunk", k) in KV) || (("pubsubnet", k) in KV)))) { msg = k "=" v ": tag target not identifiable, check manually"; return }
    if (REF[ty] || REF["unk"] || (pub && REF["subunk"])) { msg = k "=" v ": tags are passed by reference, check them manually"; return }
    msg = "tag " k " not found in the inputs scanned (aws_ec2_tag, private_subnet_tags, public_subnet_tags, node_security_group_tags); module-level tags and other inputs are not read, check manually"
}
END {
    for (j = 1; j <= ng; j++) {
        s = GL[j]; ok = 0; allf = 1; lab = (GT[s] == "subnet") ? "subnet" : "security group"
        for (x = 1; x <= TN[s]; x++) { tid = s SUBSEP x; if (TS[tid] == "P" || TS[tid] == "I") ok = 1; if (TS[tid] != "F") allf = 0 }
        for (x = 1; x <= TN[s]; x++) {
            tid = s SUBSEP x; h = "EC2NodeClass " lab " selector term " x " (" TF[tid] ")"
            if (TS[tid] == "I") print "P", h " uses ids (no discovery tag to check)"
            else if (TS[tid] == "P") print "P", h " " TT[tid] ": every tag matches a tag the project applies to " (GT[s] == "subnet" ? "private subnets" : "security groups")
            else if (TS[tid] == "W" || ok) print "W", h ": " TM[tid] (ok ? " (another term matches)" : "")
            else print "F", h ": " TM[tid] (allf ? " -- no term matches and no scanned input carries this value, so Karpenter would find no " lab : "")
        }
    }
    if (SGK == "") exit
    for (z in HAS) { split(z, q, SUBSEP); if (q[1] == "clustersg" && q[2] == SGK) cs = 1; if (q[1] == "unk" && q[2] == SGK) cu = 1 }
    if (cs) print "P", "Cluster security group carries the " SGK " tag"
    else if (cu) print "W", "Cluster security group: an aws_ec2_tag with key " SGK " has a target that is not identifiable, check manually"
    else print "W", "Cluster security group: no aws_ec2_tag with key " SGK " on cluster_primary_security_group_id found (module-level tags are not read)"
}
AWK
)

KARP_DIRS=("$PROJECT_DIR")
if [ -n "$GITOPS_DIR" ] && [ "$GITOPS_DIR" = "$PROJECT_DIR/../gitops" ]; then
    KARP_DIRS+=("$GITOPS_DIR")
fi
KARP_NC_LIST=$(find -H "${KARP_DIRS[@]}" -type f \( -name '*.tf' -o -name '*.yaml' -o -name '*.yml' -o -name '*.tftpl' -o -name '*.tpl' \) ! -path '*/.terraform/*' -exec grep -l -E "kind[\"']?[[:space:]]*[:=][[:space:]]*[\"']?EC2NodeClass" {} + 2>/dev/null || true)

if [ -z "$KARP_NC_LIST" ]; then
    pass "Karpenter not configured (no EC2NodeClass found)"
else
    KARP_NC_FILES=()
    while IFS= read -r f; do KARP_NC_FILES+=("$f"); done <<< "$KARP_NC_LIST"
    KARP_TF_FILES=()
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        if [ -r "$f" ]; then KARP_TF_FILES+=("$f"); else warn "Cannot read $f -- skipped by the Karpenter tag check"; fi
    done <<< "$(find -H "$PROJECT_DIR" -type f -name '*.tf' ! -path '*/.terraform/*' 2>/dev/null || true)"

    KARP_SELECTORS=$(awk "$KARP_SEL_AWK" "${KARP_NC_FILES[@]}" || true)
    KARP_APPLIED=""
    if [ "${#KARP_TF_FILES[@]}" -gt 0 ]; then
        KARP_APPLIED=$(awk "$KARP_TAG_AWK" "${KARP_TF_FILES[@]}" || true)
    fi
    # The Pattern 2 shape applies local.cluster_config.name, decoded from
    # configs/cluster.yaml: judge it as that file's top-level name literal, only
    # when locals.tf decodes that file directly (any other shape stays an expression).
    KARP_CNAME=""
    if [ -r "$PROJECT_DIR/configs/cluster.yaml" ] && grep -Eq '^[[:space:]]*cluster_config[[:space:]]*=[[:space:]]*yamldecode\(file\("[^"]*configs/cluster\.yaml"\)\)[[:space:]]*$' "$PROJECT_DIR/locals.tf" 2>/dev/null; then
        KARP_CNAME=$(awk '/^name[[:space:]]*:/ { sub(/^name[[:space:]]*:[[:space:]]*/, ""); sub(/[[:space:]]+#.*$/, ""); gsub(/["'\''[:space:]]/, ""); if ($0 !~ /[${}]/) print; exit }' "$PROJECT_DIR/configs/cluster.yaml")
    fi
    if [ -n "$KARP_CNAME" ] && [ -n "$KARP_APPLIED" ]; then
        KARP_APPLIED=$(printf '%s\n' "$KARP_APPLIED" | awk -v n="$KARP_CNAME" 'BEGIN { FS = OFS = "\t" } $3 == "local.cluster_config.name" && $4 == "E" { $3 = n; $4 = "L" } { print }')
    fi

    if [ -z "$KARP_SELECTORS" ]; then
        warn "EC2NodeClass found but its subnet/security group selector tags could not be read -- check manually"
    else
        while IFS="$(printf '\t')" read -r k_lvl k_msg; do
            case "$k_lvl" in P) pass "$k_msg" ;; F) fail "$k_msg" ;; W) warn "$k_msg" ;; esac
        done <<< "$( { printf '%s\n' "$KARP_APPLIED" | awk 'NF { print "A\t" $0 }'; printf '%s\n' "$KARP_SELECTORS" | awk '{ print "S\t" $0 }'; } | awk "$KARP_EVAL_AWK")"
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

# --- 13. Permissions boundary (optional) ---
echo ""
echo "13. Permissions boundary"
echo "-------------------------------------------"

CLUSTER_YAML="$PROJECT_DIR/configs/cluster.yaml"
BOUNDARY=""
UNREADABLE=0
if [ -f "$CLUSTER_YAML" ] && [ ! -r "$CLUSTER_YAML" ]; then
    UNREADABLE=1
elif [ -f "$CLUSTER_YAML" ]; then
    # Top-level key only; strip CR so a CRLF file reads the same
    BOUNDARY=$(grep -E '^permissions_boundary[[:space:]]*:' "$CLUSTER_YAML" | head -1 | tr -d '\r' \
        | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]+#.*$//; s/^["'\'']//; s/["'\''][[:space:]]*$//' || true)
fi
if [ "$UNREADABLE" = 1 ]; then
    fail "configs/cluster.yaml is not readable: cannot check permissions_boundary"
elif [ -z "$BOUNDARY" ] || [ "$BOUNDARY" = "null" ] || [ "$BOUNDARY" = "~" ]; then
    pass "permissions_boundary not set: no boundary check needed"
else
    # A customer managed (account id) or AWS managed (`aws`) policy can be a boundary
    if [[ "$BOUNDARY" =~ ^arn:aws[a-z-]*:iam::([0-9]{12}|aws):policy/.+$ ]]; then
        pass "permissions_boundary is an IAM policy ARN"
    else
        fail "permissions_boundary is not an IAM policy ARN: $BOUNDARY"
    fi
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
