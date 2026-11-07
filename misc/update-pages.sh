#!/usr/bin/env bash
# update-pages.sh
#
# Generates Docusaurus wrappers for every tracked *.md under skills/,
# examples/, and devops-agent/ into misc/website/docs/, plus the
# skills.json and examples.json manifests and llms.txt.
#
# Inputs (sources of truth):
#   skills/**/*.md        (except skills/README.md — marker-generated)
#   examples/**/*.md      (README.md → index.md wrappers)
#   examples/**/*.html    (copied to static/)
#   examples/**/*.png     (copied to static/)
#   devops-agent/**/*.md  (except devops-agent/README.md — marker-generated)
#   SKILL_META (below)    skill page titles and summaries
#
# Outputs (regenerated; tracked in git):
#   misc/website/docs/skills/<group>/<name>/index.md       wrapper for SKILL.md
#   misc/website/docs/skills/<group>/<name>/<sub>/<f>.md   wrapper for sub-files
#   misc/website/docs/skills/index.md              grouped skill list (overwritten)
#   misc/website/docs/skills/{eks,ecs}/index.md    EKS and ECS landing pages (overwritten)
#   misc/website/docs/skills/<group>/_category_.json  sidebar category (overwritten)
#   misc/website/docs/examples/<path>/index.md     wrapper for README.md
#   misc/website/docs/examples/index.md            card grid (overwritten)
#   misc/website/static/examples/                  .html + .png assets
#   misc/website/docs/devops-agent/<name>/index.md   wrapper for SKILL.md
#   misc/website/docs/devops-agent/<name>/<f>.md     wrapper for sub-files
#   misc/website/docs/devops-agent/index.md          listing page (overwritten)
#   misc/website/static/manifests/skills.json
#   misc/website/static/llms.txt                   agent-facing index (llmstxt.org)
#   misc/website/static/manifests/examples.json
#
# Usage:
#   ./misc/update-pages.sh              # regenerate in place
#   ./misc/update-pages.sh --check      # fail if generated artifacts are stale
#   ./misc/update-pages.sh --dry-run    # print what would be written; no edits
#
# --check is what the `docs-sync` CI job runs alongside
# update-all-references.sh: regenerate in place, then `git diff --exit-code`
# on the output paths. Non-zero exit means someone edited a wrapper by hand
# or added/edited a skill/workflow without running this script.
# Fix: `./misc/update-pages.sh && git add … && commit`.

set -euo pipefail
# Command substitutions must inherit errexit: parse_frontmatter exits 2 on
# invalid YAML, and most callers run inside $(...) (derive_title, the index
# builders). Without this, a broken SKILL.md would be swallowed and the
# wrapper written with an empty description.
shopt -s inherit_errexit

MODE="run"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
elif [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

python3 -c 'import yaml' 2>/dev/null || {
  echo "ERROR: PyYAML is required (pip install pyyaml)" >&2
  exit 1
}

SKILLS_OUT="$REPO_ROOT/misc/website/docs/skills"
EXAMPLES_OUT="$REPO_ROOT/misc/website/docs/examples"
MANIFEST="$REPO_ROOT/misc/website/static/manifests/skills.json"
LLMS_TXT="$REPO_ROOT/misc/website/static/llms.txt"
EXAMPLES_MANIFEST="$REPO_ROOT/misc/website/static/manifests/examples.json"
SKILLS_DIR="$REPO_ROOT/skills"
EXAMPLES_DIR="$REPO_ROOT/examples"
EXAMPLES_STATIC="$REPO_ROOT/misc/website/static/examples"
DEVOPS_OUT="$REPO_ROOT/misc/website/docs/devops-agent"
DEVOPS_DIR="$REPO_ROOT/devops-agent"

GH_BASE="https://github.com/aws-samples/sample-apex-skills/blob/main"

# Files this script may touch — the blast radius of --check.
TOUCHED_PATHS=(
  "misc/website/docs/skills"
  "misc/website/docs/examples"
  "misc/website/docs/devops-agent"
  "misc/website/static/manifests"
  "misc/website/static/llms.txt"
  "misc/website/static/examples"
)

# --- Parse one frontmatter key from a markdown file -----------------------
parse_frontmatter() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import os, sys, yaml
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
except (OSError, UnicodeDecodeError) as e:
    print(f"ERROR: {path}: {e}", file=sys.stderr)
    sys.exit(2)
if not lines or lines[0].rstrip() != "---":
    sys.exit(0)
fm = []
for line in lines[1:]:
    if line.rstrip() == "---":
        break
    fm.append(line)
else:
    print(f"ERROR: {path}: unclosed frontmatter block (missing closing '---')", file=sys.stderr)
    sys.exit(2)
if len("".join(fm).encode("utf-8")) > 64 * 1024:
    print(f"ERROR: {path}: frontmatter block too large to parse", file=sys.stderr)
    sys.exit(2)
try:
    data = yaml.safe_load("".join(fm))
except yaml.YAMLError as e:
    print(f"ERROR: {path}: {e}", file=sys.stderr)
    sys.exit(2)
if not isinstance(data, dict):
    sys.exit(0)
val = data.get(key)
if val is None:
    sys.exit(0)
print(" ".join(str(val).split()))
PY
}

# --- Extract first # heading from a markdown file -------------------------
first_heading() {
  local file="$1"
  awk '
    /^---$/ { block++; next }
    block == 1 { next }
    /^# / { sub(/^# */, ""); print; exit }
  ' "$file"
}

# --- Derive title from filename -------------------------------------------
# Replace hyphens with spaces and title-case each word. Uses awk rather than
# `sed 's/\b\(.\)/\u\1/g'` because the \b word boundary and \u uppercase escape
# are GNU-only; on BSD/macOS sed they silently no-op and leave titles lowercase.
title_from_filename() {
  local base="$1"
  base="${base%.md}"
  printf '%s\n' "$base" | awk '{
    gsub(/-/, " ")
    cap = 1; out = ""
    for (i = 1; i <= length($0); i++) {
      c = substr($0, i, 1)
      if (cap && c ~ /[a-z]/) { c = toupper(c); cap = 0 }
      else if (c ~ /[a-zA-Z0-9]/) { cap = 0 }
      else { cap = 1 }
      out = out c
    }
    print out
  }'
}

# --- Strip leading YAML frontmatter from a markdown file ------------------
strip_frontmatter() {
  local file="$1"
  awk '
    BEGIN { mode = "preamble" }
    mode == "preamble" && NR == 1 && /^---[[:space:]]*$/ { mode = "in_fm"; next }
    mode == "preamble" { mode = "body"; print; next }
    mode == "in_fm" && /^---[[:space:]]*$/ { mode = "body"; next }
    mode == "in_fm" { next }
    mode == "body" { print }
  ' "$file"
}

# --- Classify a skill into a service group ---
classify_skill() {
  local name="$1"
  case "$name" in
    eks-*) echo "eks" ;;
    ecs-*) echo "ecs" ;;
    *)     echo "general" ;;
  esac
}

# --- YAML-safe scalar via JSON encoding -----------------------------------
yaml_scalar() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1], ensure_ascii=False))' "$1"
}

# First-sentence extraction that skips mid-sentence abbreviations ("e.g. ",
# "i.e. ", "vs. ") so the ". " inside them is not treated as a sentence
# boundary. Abbreviation patterns are anchored to a word boundary (start of
# string, space, or open paren) so words merely ending in the same letters
# (e.g. "devs.") still count as sentence ends. Prints the first real sentence
# (with trailing period); prints the input unchanged if no real sentence
# boundary exists.
first_sentence() {
  local text="$1" head="" rest="$1"
  while [[ "$rest" == *". "* ]]; do
    head="${head}${rest%%". "*}."
    rest="${rest#*". "}"
    case "$head" in
      [eE].g.|*[\ \(][eE].g.|[iI].e.|*[\ \(][iI].e.|[vV]s.|*[\ \(][vV]s.) head="$head " ;;
      *) printf '%s' "$head"; return ;;
    esac
  done
  printf '%s' "$text"
}

# --- Skill page titles and summaries --------------------------------------
# One line per skill: <folder><TAB><page title><TAB><summary>. The title is the
# skill page's <title>, with the folder name added after its first part
# (Docusaurus appends " | APEX Skills"). The summary is the
# page's meta description, the manifest `summary` field, the landing-page line
# and the llms.txt line: keep it under 160 characters, in words taken from the
# skill's own SKILL.md. SKILL.md descriptions are routing text for agents and
# run to 1,000 characters, which is why the pages do not use them directly.
# A skill missing here falls back to its name and its description's first
# sentence, and the generator warns.
SKILL_META="$(cat <<'META'
apex	APEX Router: pick the right EKS or ECS skill	Router for EKS and ECS requests: picks the skill that fits, infers the stage (Day 0 Design, Day 1 Build, Day 2 Operate) and suggests next skills
dotnet-aws-ecs	.NET on Amazon ECS Fargate with CloudFormation or CDK	Deploy a .NET workload to Amazon ECS Fargate behind an Application Load Balancer, with CloudFormation or CDK and a deployment guide
ecs-architect	ECS Architect: choose your Amazon ECS deployment model	Choose the ECS deployment model for a new workload: Fargate, EC2, Managed Instances, Express Mode or ECS Anywhere, capacity providers and task sizing
ecs-build	ECS Build: apply-ready Terraform for Amazon ECS	Generate apply-ready Terraform for ECS clusters, services and task definitions on Fargate, EC2 Auto Scaling or Managed Instances
ecs-devops	ECS DevOps: deployments and CI/CD for Amazon ECS	Deploy and release to ECS: blue/green and canary deployments, CI/CD pipelines and rollbacks
ecs-genai	ECS GenAI: GPU, ML and LLM workloads on Amazon ECS	GPU, ML and GenAI workloads on ECS: GPU instances, Inferentia, Trainium and Neuron, launch type choice, training and model inference
ecs-modernize	ECS Modernize: migrate VMware or EC2 apps to ECS	Assess an existing VMware or EC2 app from its source code, decide replatform or rearchitect, and migrate it onto ECS
ecs-observability	ECS Observability: logs, metrics and traces for ECS	ECS observability architecture: logs, metrics and traces with CloudWatch, Container Insights, X-Ray, ADOT, Managed Prometheus and Grafana, or FireLens
ecs-operation-review	ECS Operation Review: rated audit of a live ECS estate	Structured ECS operational excellence assessment of a live estate across 8 domains with GREEN/AMBER/RED ratings
ecs-recon	ECS Recon: discover what your Amazon ECS estate runs	ECS environment discovery: compute and capacity providers, task definitions, deployments, scaling, networking, security, observability and IaC/CI-CD
ecs-security	ECS Security: hardening and compliance for Amazon ECS	ECS security and compliance: task and execution roles, iam:PassRole, trust policies, secrets injection and shared responsibility on Fargate and EC2
eks-best-practices	EKS Best Practices: architecture advice for Amazon EKS	EKS architecture advice: compute, networking, security, reliability, cost, scaling, observability, multi-tenancy, upgrades, hybrid and surge readiness
eks-build	EKS Build: production-ready Terraform for Amazon EKS	Generate production-ready EKS Terraform projects with optional ArgoCD GitOps, air-gapped support and 29+ addon configurations
eks-cost-intelligence	EKS Cost Intelligence: cost score for Amazon EKS	Live EKS cost efficiency assessment across 6 dimensions with a 0-100 Cost Score and dollar-quantified findings
eks-design	EKS Design: architecture documents for Amazon EKS	Generate EKS architecture design documents with Mermaid diagrams, ADRs, security architecture and validation reports, guided by Well-Architected practices
eks-genai	EKS GenAI: GPU, Neuron and LLM serving on Amazon EKS	GenAI and LLM workloads on EKS: GPU vs Trainium/Inferentia, vLLM and Ray serving, distributed training, ML storage and AI gateways
eks-ingress-migration	EKS Ingress Migration: plan the move off NGINX Ingress	Assess a live cluster's NGINX/Ingress estate and plan migration to Gateway API, the AWS Load Balancer Controller or AWS Transform
eks-mcp-server	EKS MCP Server: connect your AI assistant to Amazon EKS	Set up and troubleshoot the EKS MCP Server in your AI assistant; for cluster work once MCP works, use eks-recon, eks-operation-review or eks-upgrade-check
eks-operation-review	EKS Operation Review: rated audit of a live EKS cluster	Structured EKS operational excellence assessment across 10 areas, GREEN/AMBER/RED rated, including deprecated-API review with no target version
eks-platform-engineering	EKS Platform Engineering: build an IDP on Amazon EKS	Internal Developer Platform design on EKS: Backstage, ArgoCD, Kargo, progressive delivery, golden paths and DORA metrics
eks-recon	EKS Recon: discover what your Amazon EKS cluster runs	EKS cluster discovery: compute, networking, security facts, add-ons, workloads, storage, IaC and CI/CD, reported as facts with no scoring
eks-security	EKS Security: CVE review, posture and compliance for EKS	Read-only scripted security reviews of a live EKS cluster (CVE exposure, security event response, posture check) plus hardening: CIS, HIPAA, PCI-DSS, FedRAMP
eks-upgrade-check	EKS Upgrade Check: upgrade readiness score for Amazon EKS	Assess EKS cluster upgrade readiness with a 0-100 score across 8 areas including deprecated APIs, add-on compatibility and workload risks
eks-well-architected-review	EKS Well-Architected Review: unofficial pillar scores	Unofficial Well-Architected style review of a live EKS cluster (Linux nodes only), scored across five pillars; run only on an explicit WAFR request
graviton-migration	Graviton Migration: move workloads from x86 to arm64	Migrate a workload from x86 to AWS Graviton (arm64): arm64 readiness scanning with the Arm migration MCP server, then the Karpenter node cutover on EKS
skill-creator	Skill Creator: create, test and tune agent skills	Create new skills, modify existing skills, run evals, benchmark performance and optimize triggering accuracy
terraform-skill	Terraform Skill: modules, tests and CI for Terraform	Terraform and OpenTofu: modules, native tests, Terratest, CI/CD pipelines, state debugging and security scanning
update-docs	Update Docs: sync the APEX docs after a skill change	Audit and sync all documentation surfaces after skill changes: README markers, Docusaurus site and prose references
META
)"

skill_title() {
  local t
  t="$(awk -F'\t' -v n="$1" '$1 == n { print $2; exit }' <<<"$SKILL_META")"
  if [[ -z "$t" ]]; then
    echo "WARNING: skills/$1 has no SKILL_META line in misc/update-pages.sh" >&2
    t="$(derive_title "$SKILLS_DIR/$1/SKILL.md")"
  fi
  # The skill id goes in the title too, so a search for it matches.
  if [[ "$t" == "$1" ]]; then :
  elif [[ "$t" == *": "* ]]; then t="${t%%: *} ($1): ${t#*: }"
  else t="$t ($1)"
  fi
  printf '%s\n' "$t"
}

skill_summary() {
  local s
  s="$(awk -F'\t' -v n="$1" '$1 == n { print $3; exit }' <<<"$SKILL_META")"
  if [[ -z "$s" ]]; then
    s="$(first_sentence "$(parse_frontmatter "$SKILLS_DIR/$1/SKILL.md" "description")")"
    if [[ ${#s} -gt 160 ]]; then
      s="${s:0:157}"
      s="${s% *}..."
    fi
  fi
  printf '%s\n' "$s"
}

# --- Link rewriting filter (stdin → stdout) -------------------------------
# Rewrites:
#   - SKILL.md → index.md in relative .md links, kept as .md file paths
#   - non-.md relative targets → GitHub blob URL
#   - external URLs and anchors → pass through
rewrite_links() {
  local src="$1"
  python3 -c '
import re, sys, os, signal
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

src = sys.argv[1]
GH_BASE = sys.argv[2]
src_dir = os.path.dirname(src)
is_example = src.startswith("examples/")

def rewrite(m):
    prefix = m.group(1)  # "!" for images, "" for links
    text, target = m.group(2), m.group(3)
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return m.group(0)
    anchor = ""
    query = ""
    if "#" in target:
        target, anchor = target.rsplit("#", 1)
        anchor = "#" + anchor
    if "?" in target:
        target, query = target.split("?", 1)
        query = "?" + query
    if not target:
        return m.group(0)
    resolved = os.path.normpath(os.path.join(src_dir, target))

    # For examples/ sources: static assets (.png, .html) resolve to /sample-apex-skills/examples/...
    if is_example and resolved.startswith("examples/") and not target.endswith(".md"):
        examples_prefix = "examples/"
        static_url = "/sample-apex-skills/examples/" + resolved[len(examples_prefix):]
        if target.endswith(".png"):
            return f"![{text}](pathname://{static_url}{query}{anchor})"
        elif target.endswith(".html"):
            # Emit both a link and an iframe embed
            link = f"[{text}](pathname://{static_url}{query}{anchor})"
            iframe = (
                "\n\n<iframe src=\"" + static_url + query + "\" "
                "width=\"100%\" height=\"600px\" "
                "style={{border:\"1px solid var(--ifm-color-emphasis-300)\", borderRadius:\"8px\"}}>"
                "</iframe>\n"
            )
            return link + iframe
        else:
            return f"[{text}]({GH_BASE}/{resolved}{query}{anchor})"

    if resolved.startswith(".."):
        return f"[{text}]({GH_BASE}/{target}{query}{anchor})"
    if not resolved.startswith(("skills/", "examples/", "devops-agent/")):
        return f"[{text}]({GH_BASE}/{resolved}{query}{anchor})"
    if not target.endswith(".md"):
        return f"[{text}]({GH_BASE}/{resolved}{query}{anchor})"
    # .md links within skills/examples/devops-agent: rewrite for Docusaurus
    if os.path.basename(resolved) == "SKILL.md":
        resolved = os.path.join(os.path.dirname(resolved), "index.md")
    elif os.path.basename(resolved) == "README.md" and resolved.startswith("examples/"):
        resolved = os.path.join(os.path.dirname(resolved), "index.md")
    # Insert group prefix for skills (output is nested under group dirs)
    if resolved.startswith("skills/"):
        skill_rel = resolved[len("skills/"):]
        skill_name = skill_rel.split("/")[0]
        if skill_name.startswith("eks-"):
            group = "eks"
        elif skill_name.startswith("ecs-"):
            group = "ecs"
        else:
            group = "general"
        resolved = f"skills/{group}/{skill_rel}"
    # Compute relative path from source — for skills sources, also account for group nesting
    if src.startswith("skills/"):
        src_skill = src.split("/")[1]
        if src_skill.startswith("eks-"):
            src_group = "eks"
        elif src_skill.startswith("ecs-"):
            src_group = "ecs"
        else:
            src_group = "general"
        effective_src_dir = f"skills/{src_group}/{src_skill}/" + "/".join(src.split("/")[2:-1])
        effective_src_dir = effective_src_dir.rstrip("/")
        new_target = os.path.relpath(resolved, effective_src_dir)
    else:
        new_target = os.path.relpath(resolved, src_dir)
    # Keep the .md file path: Docusaurus resolves a file link to the URL of
    # the target page at build time, so it holds whatever the URL form
    # (trailing slash or not, index pages, <dir>/<dir>.md pages). A
    # URL-relative link such as "../eks-recon" resolves against the browser
    # URL and breaks when that form changes.
    return f"[{text}]({new_target}{query}{anchor})"

for line in sys.stdin:
    sys.stdout.write(re.sub(r"(!?)\[([^\]]*)\]\(([^)]+)\)", rewrite, line))
' "$src" "$GH_BASE"
}

# --- Detect vendored skill and emit appropriate admonition ----------------
# A vendored skill has a LICENSE* file in its directory.
# Team-owned (source URL matches aws-samples/aws/awslabs/amazon orgs) gets
# an info admonition. External third-party gets a caution admonition.
vendored_skill_admonition() {
  local src="$1"
  # Only applies to files under skills/<name>/
  [[ "$src" == skills/*/SKILL.md || "$src" == skills/*/* ]] || return 0
  local skill_name="${src#skills/}"
  skill_name="${skill_name%%/*}"
  local skill_dir="$REPO_ROOT/skills/$skill_name"

  # Check for LICENSE* file
  local license_file=""
  for f in "$skill_dir"/LICENSE*; do
    [[ -f "$f" ]] && license_file="$f" && break
  done
  [[ -n "$license_file" ]] || return 0

  # Extract metadata from THIRD_PARTY_NOTICES.md (authoritative source)
  local notices="$REPO_ROOT/THIRD_PARTY_NOTICES.md"
  local author license_id source_url license_from_notices
  if [[ -f "$notices" ]]; then
    # Pass skill_name via ENVIRON (not -v, which escape-processes the value)
    # and match with index()==1 (literal prefix) rather than a regex, so a
    # name containing regex metacharacters cannot match the wrong section.
    # `found && /^## / { exit }` stops each scan at the next section heading, so a
    # section missing the field yields empty rather than bleeding the NEXT
    # section's value in (which would flip a third-party skill's attribution).
    source_url="$(SKILL_NAME="$skill_name" awk '
      index($0, "## " ENVIRON["SKILL_NAME"]) == 1 { found=1; next }
      found && /^## / { exit }
      found && /Source:/ { sub(/.*Source:[* ]*/, ""); sub(/[* ]*$/, ""); print; exit }
    ' "$notices")"
    author="$(SKILL_NAME="$skill_name" awk '
      index($0, "## " ENVIRON["SKILL_NAME"]) == 1 { found=1; next }
      found && /^## / { exit }
      found && /Copyright:/ { sub(/.*Copyright:[* ]*/, ""); sub(/[* ]*$/, ""); print; exit }
    ' "$notices")"
    # License mirrors the Copyright block: take the THIRD_PARTY_NOTICES License
    # field (dropping the "(see ...)" file pointer) so a vendored skill without a
    # frontmatter `license:` key renders its actual license, not the default.
    license_from_notices="$(SKILL_NAME="$skill_name" awk '
      index($0, "## " ENVIRON["SKILL_NAME"]) == 1 { found=1; next }
      found && /^## / { exit }
      found && /License:/ { sub(/.*License:[* ]*/, ""); sub(/ *\(see.*$/, ""); sub(/[* ]*$/, ""); print; exit }
    ' "$notices")"
    # Normalize the long-form license name to its SPDX short id so the
    # admonition reads "under the MIT license", not "under the MIT License license".
    case "$license_from_notices" in
      "MIT License") license_from_notices="MIT" ;;
      "Apache License 2.0"|"Apache 2.0") license_from_notices="Apache-2.0" ;;
    esac
  fi
  # Fallback: frontmatter metadata
  if [[ -z "$author" ]]; then
    local skill_md="$skill_dir/SKILL.md"
    author="$(parse_frontmatter "$skill_md" "author")"
  fi
  # Precedence: frontmatter `license:` (e.g. terraform-skill) > THIRD_PARTY_NOTICES
  # License field > Apache-2.0 default.
  license_id="$(parse_frontmatter "$skill_dir/SKILL.md" "license")"
  [[ -z "$license_id" ]] && license_id="$license_from_notices"
  [[ -z "$license_id" ]] && license_id="Apache-2.0"
  # Next source: the "Source repo" row of the skill's UPSTREAM.md (the sync
  # scripts' provenance file), so a vendored skill with no notices entry
  # names its upstream repo rather than its own folder.
  if [[ -z "$source_url" && -f "$skill_dir/UPSTREAM.md" ]]; then
    source_url="$(awk -F'|' '$2 ~ /^ *Source repo *$/ { gsub(/ /, "", $3); print $3; exit }' "$skill_dir/UPSTREAM.md")"
    source_url="${source_url%.git}"
  fi
  [[ -z "$source_url" ]] && source_url="$GH_BASE/skills/$skill_name"
  [[ -z "$author" ]] && author="third party"
  # Strip a leading "Copyright (c) <year> " prefix so the admonition shows a bare
  # maintainer name (terraform-skill convention), not the raw copyright line.
  author="$(printf '%s' "$author" | sed -E 's/^Copyright( \([cC]\))?[[:space:]]+[0-9]{4}(-[0-9]{4})?[[:space:]]+//')"

  # Determine ownership: team-owned if source URL matches AWS orgs. A vendored
  # skill with a LICENSE file but no THIRD_PARTY_NOTICES entry is repo-native /
  # team-owned by convention (third-party skills always carry a notices entry),
  # so the fallback URL correctly resolves it to the team admonition.
  local is_team=false
  if [[ "$source_url" == *github.com/aws-samples/* || \
        "$source_url" == *github.com/aws/* || \
        "$source_url" == *github.com/awslabs/* || \
        "$source_url" == *github.com/amazon* ]]; then
    is_team=true
  fi

  if $is_team; then
    local repo_name="${source_url##*/}"
    cat <<EOF

:::info[Vendored skill]
This skill is sourced from [$repo_name]($source_url), also maintained by the APEX team.
:::

EOF
  else
    cat <<EOF

:::caution[Third-party skill]
This skill is maintained by **$author** under the $license_id license. Upstream: [$source_url]($source_url)
:::

EOF
  fi
}

# --- Build a generic wrapper to stdout ------------------------------------
build_wrapper() {
  local src="$1"
  local title="$2"
  local description="$3"
  local sidebar_label="${4:-}"
  local title_yaml desc_yaml label_line=""
  title_yaml="$(yaml_scalar "$title")"
  desc_yaml="$(yaml_scalar "$description")"
  [[ -n "$sidebar_label" ]] && label_line="sidebar_label: $(yaml_scalar "$sidebar_label")"$'\n'

  cat <<EOF
---
title: $title_yaml
${label_line}description: $desc_yaml
custom_edit_url: $GH_BASE/$src
format: md
---

:::info[Source]
This page is generated from [$src]($GH_BASE/$src). Edit the source, not this page.
:::

EOF
  vendored_skill_admonition "$src"
  strip_frontmatter "$REPO_ROOT/$src" | rewrite_links "$src"
}

# --- Compute output path for a source file --------------------------------
compute_out_path() {
  local src="$1"
  if [[ "$src" == skills/*/SKILL.md ]]; then
    local folder="${src#skills/}"
    folder="${folder%/SKILL.md}"
    local group
    group="$(classify_skill "$folder")"
    echo "$SKILLS_OUT/$group/$folder/index.md"
  elif [[ "$src" == skills/* ]]; then
    local rel="${src#skills/}"
    local skill_name="${rel%%/*}"
    local group
    group="$(classify_skill "$skill_name")"
    echo "$SKILLS_OUT/$group/$rel"
  elif [[ "$src" == examples/*/README.md ]]; then
    local rel="${src#examples/}"
    rel="${rel%/README.md}"
    echo "$EXAMPLES_OUT/$rel/index.md"
  elif [[ "$src" == examples/* ]]; then
    local rel="${src#examples/}"
    echo "$EXAMPLES_OUT/$rel"
  elif [[ "$src" == devops-agent/*/SKILL.md ]]; then
    local folder="${src#devops-agent/}"
    folder="${folder%/SKILL.md}"
    echo "$DEVOPS_OUT/$folder/index.md"
  elif [[ "$src" == devops-agent/* ]]; then
    local rel="${src#devops-agent/}"
    echo "$DEVOPS_OUT/$rel"
  fi
}

# --- Derive title for any source file -------------------------------------
derive_title() {
  local file="$1"
  local t
  t="$(parse_frontmatter "$file" "name")"
  if [[ -n "$t" ]]; then echo "$t"; return; fi
  t="$(first_heading "$file")"
  if [[ -n "$t" ]]; then echo "$t"; return; fi
  title_from_filename "$(basename "$file")"
}

# --- Skill folders of one group, sorted, one per line ----------------------
skills_in_group() {
  local d folder
  for d in "$SKILLS_DIR"/*/; do
    [[ -f "$d/SKILL.md" ]] || continue
    folder="$(basename "$d")"
    [[ -n "$(parse_frontmatter "$d/SKILL.md" "name")" ]] || continue
    [[ "$(classify_skill "$folder")" == "$1" ]] && printf '%s\n' "$folder"
  done | LC_ALL=C sort
}

# --- One "- [name](link): summary" line per skill of a group ---------------
# Links are .md file paths, relative to the page in $2's directory, so
# Docusaurus resolves them to page URLs.
emit_skill_list() {
  local group="$1" prefix="$2" skill
  while IFS= read -r skill; do
    printf -- '- [**%s**](%s%s/index.md): %s\n' "$skill" "$prefix" "$skill" "$(skill_summary "$skill")"
  done < <(skills_in_group "$group")
}

# --- Build skills/index.md to stdout ---------------------------------------
build_skills_index() {
  cat <<'EOF'
---
sidebar_position: 3
title: "Agent skills for Amazon EKS, Amazon ECS and platform engineering"
sidebar_label: Skills
description: "Browse every APEX skill: AWS skills for AI agents doing platform engineering on Amazon EKS and Amazon ECS, from design and Terraform to reviews and security."
---

# Skills

> _This page is auto-generated by [`misc/update-pages.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/update-pages.sh). Do not edit manually._

## [EKS skills](./eks/index.md)

EOF
  emit_skill_list eks "./eks/"
  echo ""
  echo "## [ECS skills](./ecs/index.md)"
  echo ""
  emit_skill_list ecs "./ecs/"
  echo ""
  echo "## General"
  echo ""
  emit_skill_list general "./general/"
}

# --- Build the EKS or ECS landing page (skills/<group>/index.md) -----------
build_group_index() {
  case "$1" in
    eks) cat <<'EOF'
---
sidebar_position: 1
title: "EKS Skills: AI agent skills for Amazon EKS"
sidebar_label: EKS skills
description: "APEX agent skills for Amazon EKS: design, Terraform builds, cluster discovery, operational, cost, security and upgrade reviews, ingress migration and GenAI."
---

# EKS skills

APEX skills for Amazon Elastic Kubernetes Service (EKS). They cover designing a cluster and generating its Terraform, finding out what a live cluster runs, reviewing its operations, cost, security and upgrade readiness, migrating off NGINX Ingress, and running GenAI workloads. See [Getting started](../../getting-started.md) to install them.

EOF
      ;;
    ecs) cat <<'EOF'
---
sidebar_position: 1
title: "ECS Skills: AI agent skills for Amazon ECS"
sidebar_label: ECS skills
description: "APEX agent skills for Amazon ECS: architecture and launch type choice, Terraform builds, deployments and CI/CD, security, operational reviews and GPU workloads."
---

# ECS skills

APEX skills for Amazon Elastic Container Service (ECS). They cover Day 0 architecture and compute-model selection (Fargate, EC2, Managed Instances, Express Mode, ECS Anywhere), Terraform builds, deployment strategies and CI/CD pipelines, security hardening and compliance, operational-excellence reviews, observability design, modernizing existing apps, and GPU, ML and GenAI workloads. The .NET on Fargate skill, dotnet-aws-ecs, is listed under General. See [Getting started](../../getting-started.md) to install them.

EOF
      ;;
  esac
  emit_skill_list "$1" "./"
}

# --- Build skills.json manifest to stdout ---------------------------------
build_manifest() {
  local summaries="" d
  for d in "$SKILLS_DIR"/*/; do
    [[ -f "$d/SKILL.md" ]] || continue
    summaries+="$(basename "$d")"$'\t'"$(skill_summary "$(basename "$d")")"$'\n'
  done
  SKILL_SUMMARIES="$summaries" python3 - "$SKILLS_DIR" <<'PY'
import json, os, sys
import yaml

skills_dir = sys.argv[1]
summaries = dict(
    line.split("\t", 1) for line in os.environ["SKILL_SUMMARIES"].splitlines() if line
)


def parse_fm(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or lines[0].rstrip() != "---":
        return {}
    fm_lines = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        fm_lines.append(line)
    else:
        print(f"ERROR: {path}: unclosed frontmatter block (missing closing '---')", file=sys.stderr)
        sys.exit(2)
    if len("".join(fm_lines).encode("utf-8")) > 64 * 1024:
        print(f"ERROR: {path}: frontmatter block too large to parse", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load("".join(fm_lines))
    if not isinstance(data, dict):
        return {}
    return {k: str(v) for k, v in data.items() if v is not None}


out = []
for entry in sorted(os.listdir(skills_dir)):
    sd = os.path.join(skills_dir, entry)
    sm = os.path.join(sd, "SKILL.md")
    if not os.path.isfile(sm):
        continue
    try:
        fm = parse_fm(sm)
    except Exception as e:
        print(f"ERROR: {sm}: {e}", file=sys.stderr)
        sys.exit(1)
    name = fm.get("name") or entry
    # Classify by prefix
    if entry.startswith("eks-"):
        group = "eks"
    elif entry.startswith("ecs-"):
        group = "ecs"
    else:
        group = "general"
    out.append({
        "name": name,
        "description": fm.get("description", ""),
        "summary": summaries.get(entry, ""),
        "path": f"/docs/skills/{group}/{entry}",
        "group": group,
    })

print(json.dumps(out, indent=2, ensure_ascii=False))
PY
}

# --- Build llms.txt (llmstxt.org) from the skills.json manifest on stdin ---
build_llms_txt() {
  python3 -c "$(cat <<'PY'
import json, sys

SITE = "https://aws-samples.github.io/sample-apex-skills"
# The landing pages' descriptions (build_group_index): keep them the same.
LANDING = {
    "eks": "APEX agent skills for Amazon EKS: design, Terraform builds, cluster discovery, operational, cost, security and upgrade reviews, ingress migration and GenAI.",
    "ecs": "APEX agent skills for Amazon ECS: architecture and launch type choice, Terraform builds, deployments and CI/CD, security, operational reviews and GPU workloads.",
}
skills = json.load(sys.stdin)
print(f"""# APEX Skills (Agentic Platform Engineering eXperience)

> Curated AWS skills for AI agents doing platform engineering on AWS, delivered through any coding agent

- Repository: https://github.com/aws-samples/sample-apex-skills
- Documentation: {SITE}/
- License: MIT-0
- Spec: https://agentskills.io

Install with the NPX installer (Claude Code and Kiro CLI):
```
npx apex-skills@1.3.0
```
For v2 and its `/apex` router, use the manual install from `main`.

See {SITE}/docs/getting-started/ for full installation instructions.

Skills on `main`, listed by misc/update-pages.sh; titles and summaries are kept in its SKILL_META table. The same list is on the Skills page ({SITE}/docs/skills/). As JSON: {SITE}/manifests/skills.json""")
for group, heading, landing in (
    ("eks", "EKS skills", "/docs/skills/eks/"),
    ("ecs", "ECS skills", "/docs/skills/ecs/"),
    ("general", "General skills", None),
):
    rows = [s for s in skills if s["group"] == group]
    print()
    print(f"## {heading}")
    print()
    if landing:
        print(f"- [{heading} overview]({SITE}{landing}): {LANDING[group]}")
    for s in rows:
        print(f"- [{s['name']}]({SITE}{s['path']}/): {s['summary']}")
PY
)"
}

# --- Write _category_.json files and group landing pages -----------------
# Every category starts collapsed; Docusaurus opens the one holding the page
# you are on. EKS and ECS get a landing page (the category's index doc).
write_category_files() {
  local group label position
  for group in eks ecs general; do
    case "$group" in
      eks) label="EKS"; position=1 ;;
      ecs) label="ECS"; position=2 ;;
      general) label="General"; position=3 ;;
    esac
    mkdir -p "$SKILLS_OUT/$group"
    cat > "$SKILLS_OUT/$group/_category_.json" <<CATEOF
{
  "label": "$label",
  "position": $position,
  "collapsible": true,
  "collapsed": true
}
CATEOF
  done
  build_group_index eks > "$SKILLS_OUT/eks/index.md"
  build_group_index ecs > "$SKILLS_OUT/ecs/index.md"
}

# --- Recursive cleanup: remove wrappers not in the expected set -----------
cleanup_stale_tree() {
  local base_dir="$1"
  shift
  local -A keep_set
  for p in "$@"; do keep_set["$p"]=1; done

  [[ -d "$base_dir" ]] || return 0
  while IFS= read -r -d '' f; do
    local rel="${f#"$base_dir"/}"
    if [[ -z "${keep_set[$rel]:-}" ]]; then
      rm "$f"
    fi
  done < <(find "$base_dir" -name '*.md' -print0)
  find "$base_dir" -type d -empty -delete 2>/dev/null || true
}

# --- Build examples/index.md card grid to stdout --------------------------
build_examples_index() {
  cat <<'EOF'
---
sidebar_position: 5
title: Examples
description: "Hands-on walkthroughs demonstrating APEX skills against real AWS infrastructure — deploy, run, and assess platform engineering workflows."
---

# Examples

> _This page is auto-generated by [`misc/update-pages.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/update-pages.sh). Do not edit manually._

Examples are self-contained walkthroughs demonstrating APEX skills against real infrastructure. Each example deploys resources, runs an APEX workflow, and shows expected results.

EOF
  while IFS= read -r -d '' readme; do
    local rel="${readme#"$EXAMPLES_DIR"/}"
    local dir_rel="${rel%/README.md}"
    local name description
    name="$(parse_frontmatter "$readme" "name")"
    description="$(parse_frontmatter "$readme" "description")"
    [[ -n "$name" ]] || continue
    [[ -n "$description" ]] || description="_(no description in frontmatter)_"
    echo "## [$name](./$dir_rel/)"
    echo ""
    echo "$description"
    echo ""
  done < <(find "$EXAMPLES_DIR" -type d -name '.terraform' -prune -o -type d -name '.*' -prune -o -name 'README.md' -print0 | sort -z)
}

# --- Build examples.json manifest to stdout --------------------------------
build_examples_manifest() {
  python3 - "$EXAMPLES_DIR" <<'PY'
import json, os, sys
import yaml

examples_dir = sys.argv[1]


def parse_fm(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or lines[0].rstrip() != "---":
        return {}
    fm_lines = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        fm_lines.append(line)
    else:
        print(f"ERROR: {path}: unclosed frontmatter block (missing closing '---')", file=sys.stderr)
        sys.exit(2)
    if len("".join(fm_lines).encode("utf-8")) > 64 * 1024:
        print(f"ERROR: {path}: frontmatter block too large to parse", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load("".join(fm_lines))
    if not isinstance(data, dict):
        return {}
    return {k: str(v) for k, v in data.items() if v is not None}


out = []
for root, dirs, files in sorted(os.walk(examples_dir)):
    # Prune gitignored/hidden trees (e.g. examples/**/.terraform) so a large
    # no-frontmatter README under them never aborts the generator.
    dirs[:] = [d for d in dirs if d != ".terraform" and not d.startswith(".")]
    dirs.sort()
    if "README.md" not in files:
        continue
    readme_path = os.path.join(root, "README.md")
    try:
        fm = parse_fm(readme_path)
    except Exception as e:
        print(f"ERROR: {readme_path}: {e}", file=sys.stderr)
        sys.exit(1)
    name = fm.get("name")
    if not name:
        continue
    rel_dir = os.path.relpath(root, examples_dir)
    out.append({
        "name": name,
        "description": fm.get("description", ""),
        "path": f"/docs/examples/{rel_dir}",
    })

print(json.dumps(out, indent=2, ensure_ascii=False))
PY
}

# --- Copy examples static assets (.html, .png) to website/static/examples/ -
copy_examples_static() {
  mapfile -t STATIC_FILES < <(git ls-files -- 'examples/**/*.html' 'examples/**/*.png')
  for asset in "${STATIC_FILES[@]}"; do
    local rel="${asset#examples/}"
    local dest="$EXAMPLES_STATIC/$rel"
    if [[ "$MODE" == "dry-run" ]]; then
      echo "COPY $asset → $dest"
    else
      mkdir -p "$(dirname "$dest")"
      cp "$REPO_ROOT/$asset" "$dest"
    fi
  done
}

# =========================================================================
# Generate
# =========================================================================

if [[ "$MODE" == "dry-run" ]]; then
  echo "=== DRY RUN — would write the following ==="
fi

# Collect all tracked .md under skills/, examples/ and devops-agent/
mapfile -t ALL_MD < <(git ls-files -- 'skills/**/*.md' 'examples/**/*.md' 'devops-agent/**/*.md')

declare -a EXPECTED_SKILL_FILES=("index.md" "eks/index.md" "ecs/index.md")
declare -a EXPECTED_EXAMPLES_FILES=("index.md")
declare -a EXPECTED_DEVOPS_FILES=("index.md")

# --- Per-file wrappers ---
for src in "${ALL_MD[@]}"; do
  # Skip skills/README.md and devops-agent/README.md (marker-generated, not docs pages)
  [[ "$src" == "skills/README.md" ]] && continue
  [[ "$src" == "devops-agent/README.md" ]] && continue

  out_file="$(compute_out_path "$src")"
  [[ -n "$out_file" ]] || continue

  # Track expected file for cleanup
  if [[ "$src" == skills/* ]]; then
    EXPECTED_SKILL_FILES+=("${out_file#"$SKILLS_OUT"/}")
  elif [[ "$src" == examples/* ]]; then
    EXPECTED_EXAMPLES_FILES+=("${out_file#"$EXAMPLES_OUT"/}")
  elif [[ "$src" == devops-agent/* ]]; then
    EXPECTED_DEVOPS_FILES+=("${out_file#"$DEVOPS_OUT"/}")
  fi

  sidebar_label=""
  if [[ "$src" == skills/*/SKILL.md ]]; then
    # Skill pages: a readable title and a short summary for search results;
    # the sidebar keeps the skill name, which is what users type.
    skill="${src#skills/}"
    skill="${skill%/SKILL.md}"
    title="$(skill_title "$skill")"
    description="$(skill_summary "$skill")"
    sidebar_label="$(derive_title "$REPO_ROOT/$src")"
  else
    title="$(derive_title "$REPO_ROOT/$src")"
    description="$(parse_frontmatter "$REPO_ROOT/$src" "description")"
  fi

  if [[ "$MODE" == "dry-run" ]]; then
    echo "--- $out_file ---"
    build_wrapper "$src" "$title" "${description:-}" "$sidebar_label" | head -10 || true
    echo "  [... body truncated ...]"
    echo ""
  else
    mkdir -p "$(dirname "$out_file")"
    build_wrapper "$src" "$title" "${description:-}" "$sidebar_label" > "$out_file.tmp"
    mv "$out_file.tmp" "$out_file"
  fi
done

# --- Skills index (grouped list) ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $SKILLS_OUT/index.md ---"
  build_skills_index | head -20 || true
  echo "  [... truncated ...]"
  echo ""
else
  mkdir -p "$SKILLS_OUT"
  build_skills_index > "$SKILLS_OUT/index.md.tmp"
  mv "$SKILLS_OUT/index.md.tmp" "$SKILLS_OUT/index.md"
fi

# --- Category files for sidebar grouping ---
if [[ "$MODE" != "dry-run" ]]; then
  write_category_files
fi

# --- Manifest ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $MANIFEST ---"
  build_manifest
  echo ""
else
  mkdir -p "$(dirname "$MANIFEST")"
  build_manifest > "$MANIFEST.tmp"
  mv "$MANIFEST.tmp" "$MANIFEST"
fi

# --- llms.txt (from the manifest) ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $LLMS_TXT ---"
  build_manifest | build_llms_txt | head -20 || true
  echo "  [... truncated ...]"
  echo ""
else
  build_manifest | build_llms_txt > "$LLMS_TXT.tmp"
  mv "$LLMS_TXT.tmp" "$LLMS_TXT"
fi

# --- Examples index (card grid) ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $EXAMPLES_OUT/index.md ---"
  examples_index_out="$(build_examples_index)"
  head -20 <<<"$examples_index_out"
  echo "  [... truncated ...]"
  echo ""
else
  mkdir -p "$EXAMPLES_OUT"
  build_examples_index > "$EXAMPLES_OUT/index.md.tmp"
  mv "$EXAMPLES_OUT/index.md.tmp" "$EXAMPLES_OUT/index.md"
fi

# --- DevOps Agent index ---

# Escape &, <, > so description text is safe to inject into HTML table cells.
# Uses sed (not ${var//}) — bash 5.2 patsub_replacement expands & in replacements.
html_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

build_devops_index() {
  cat <<'INDEXEOF'
---
sidebar_position: 3.5
title: DevOps Agent Skills
description: "Skills ported for fully autonomous execution on AWS DevOps Agent — read-only EKS cluster assessments without interactive prompts."
---

# DevOps Agent Skills

> _This page is auto-generated by [`misc/update-pages.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/update-pages.sh). Do not edit manually._

A subset of APEX skills ported for the [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/) runtime. These run fully autonomously — no interactive prompts, no scripts, no MCP server references.

<table>
<tr><th>Skill</th><th>Status</th><th>Description</th></tr>
INDEXEOF

  for skill_dir in "$DEVOPS_DIR"/*/; do
    local skill_md="$skill_dir/SKILL.md"
    [[ -f "$skill_md" ]] || continue
    local folder
    folder="$(basename "$skill_dir")"
    local title
    title="$(parse_frontmatter "$skill_md" "name")"
    [[ -z "$title" ]] && title="$(title_from_filename "$folder")"
    local desc
    desc="$(parse_frontmatter "$skill_md" "description")"
    [[ -z "$desc" ]] && desc="<em>(no description)</em>"
    # Truncate at first sentence boundary (". " only — avoids cutting "EKS 1.32";
    # first_sentence skips abbreviations like "e.g. " / "i.e. ").
    # Fall back to word boundary + ellipsis for descriptions without sentence ends
    local first
    first="$(first_sentence "$desc")"
    if [[ "$first" != "$desc" ]]; then
      desc="$first"
    elif [[ ${#desc} -gt 150 ]]; then
      desc="${desc:0:150}"
      desc="${desc% *}…"
    fi
    if [[ ${#desc} -gt 200 ]]; then
      desc="${desc:0:200}"
      desc="${desc% *}…"
    fi
    local status="Placeholder"
    [[ -d "$skill_dir/references" ]] && status="Active"
    [[ "$desc" != "<em>(no description)</em>" ]] && desc="$(html_escape "$desc")"
    echo "<tr><td><a href=\"./$folder/\"><b>$title</b></a></td><td>$status</td><td>$desc</td></tr>"
  done
  echo "</table>"
}

if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $DEVOPS_OUT/index.md ---"
  devops_index_out="$(build_devops_index)"
  head -20 <<<"$devops_index_out"
  echo "  [... truncated ...]"
  echo ""
else
  mkdir -p "$DEVOPS_OUT"
  build_devops_index > "$DEVOPS_OUT/index.md.tmp"
  mv "$DEVOPS_OUT/index.md.tmp" "$DEVOPS_OUT/index.md"
fi

# --- Examples manifest ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "--- $EXAMPLES_MANIFEST ---"
  build_examples_manifest
  echo ""
else
  mkdir -p "$(dirname "$EXAMPLES_MANIFEST")"
  build_examples_manifest > "$EXAMPLES_MANIFEST.tmp"
  mv "$EXAMPLES_MANIFEST.tmp" "$EXAMPLES_MANIFEST"
fi

# --- Examples static assets (.html, .png) ---
copy_examples_static

# --- Stale-wrapper cleanup (only in real-write mode, not --check) ---
if [[ "$MODE" == "run" ]]; then
  cleanup_stale_tree "$SKILLS_OUT" "${EXPECTED_SKILL_FILES[@]}"
  cleanup_stale_tree "$EXAMPLES_OUT" "${EXPECTED_EXAMPLES_FILES[@]}"
  cleanup_stale_tree "$DEVOPS_OUT" "${EXPECTED_DEVOPS_FILES[@]}"
fi

# --- Dry-run exits here ---
if [[ "$MODE" == "dry-run" ]]; then
  echo "=== No changes written ==="
  exit 0
fi

# --- --check: regen happened in place above; now diff against committed state
if [[ "$MODE" == "check" ]]; then
  diff_dirty=false
  if ! git diff --quiet -- "${TOUCHED_PATHS[@]}"; then
    diff_dirty=true
  fi
  untracked="$(git ls-files --others --exclude-standard -- "${TOUCHED_PATHS[@]}")"

  if $diff_dirty || [[ -n "$untracked" ]]; then
    echo ""
    echo "ERROR: Docusaurus wrappers / manifest are stale."
    if $diff_dirty; then
      echo ""
      echo "Diff:"
      git --no-pager diff -- "${TOUCHED_PATHS[@]}"
    fi
    if [[ -n "$untracked" ]]; then
      echo ""
      echo "Untracked (newly generated) files:"
      printf '  %s\n' "$untracked"
    fi
    echo ""
    echo "Fix: run ./misc/update-pages.sh locally, commit the result."
    exit 1
  fi
  echo "✓ Docusaurus wrappers + manifests are in sync with skills/, examples/, and devops-agent/"
  exit 0
fi

# --- Run mode summary ---
skill_count="$(find "$SKILLS_OUT" -name '*.md' | wc -l)"
examples_count="$(find "$EXAMPLES_OUT" -name '*.md' | wc -l)"
devops_count="$(find "$DEVOPS_OUT" -name '*.md' 2>/dev/null | wc -l)"
examples_static_count="$(find "$EXAMPLES_STATIC" -type f 2>/dev/null | wc -l)"
echo "✅ Generated Docusaurus wrappers and manifests:"
echo "   Skills:      $skill_count files in misc/website/docs/skills/"
echo "   Examples:    $examples_count files in misc/website/docs/examples/"
echo "   DevOps Agent: $devops_count files in misc/website/docs/devops-agent/"
echo "   Static:      $examples_static_count files in misc/website/static/examples/"
echo "   Manifests:   misc/website/static/manifests/{skills,examples}.json"
echo "   llms.txt:    misc/website/static/llms.txt"
