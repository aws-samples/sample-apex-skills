#!/usr/bin/env bash
# sync-eks-upgrade-skill.sh
#
# Syncs the eks-upgrade-check skill from the upstream sample-eks-upgrade-skill repo.
# Source: https://github.com/aws-samples/sample-eks-upgrade-skill
# License: MIT-0 (or whatever upstream declares — LICENSE is copied verbatim)
#
# This script treats the upstream repo as the source of truth.
# It clones the upstream repo into a temp directory, then replaces
# our local eks-upgrade-check folder with ONLY the core skill components:
#   - SKILL.md           (the skill itself)
#   - LICENSE            (license compliance)
#   - references/*.md    (8 progressive-disclosure docs — RENAMED from upstream's `steering/` for apex compatibility, see Apex-flavored deviations below)
#   - data/*.json        (OSS add-on registry)
#   - tools/*.py         (markdown-to-HTML converter)
#
# Excluded (deliberately NOT copied):
#   - .git/, .github/, .claude/, .mcp.json
#   - evals/, eks-upgrade-workspace/, docs/
#   - Generated *.html and *.md report artifacts at upstream root
#   - README.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
#
# Apex-flavored deviations (deterministic edits applied at sync time):
#
# 1. MCP Server Setup section — Upstream's section assumes a project-root
#    .mcp.json (which apex deliberately does not ship). After copy, this
#    script replaces that section with apex-flavored guidance pointing
#    users at the eks-mcp-server skill. The fallback note ("falls back
#    to AWS CLI and kubectl") is preserved.
#
# 2. steering/ -> references/ rename — Upstream's progressive-disclosure
#    docs live under steering/, but apex already uses a top-level steering/
#    directory at the repo root for workflow orchestration (different
#    concept). To avoid the collision and align with the Anthropic skill
#    spec's canonical name for "additional documentation agents read on
#    demand," we rename the directory on copy and rewrite all internal
#    cross-refs from `steering/` to `references/` inside SKILL.md and the
#    8 progressive-disclosure files.
#
# 3. Pushy description — Upstream's SKILL.md frontmatter description is a
#    keyword list ("EKS upgrade, cluster upgrade, upgrade readiness, ..."),
#    which under-triggers in the apex harness. After copy, this script
#    replaces the description with one that includes natural-question
#    phrasings ("can I upgrade my cluster?", "is my cluster ready for
#    1.32?", etc.) so the skill activates on casual user wording, not just
#    technical keywords. Matches the convention used by sibling skills
#    (eks-best-practices, eks-recon).
#
# Usage:
#   chmod +x misc/sync-eks-upgrade-skill.sh
#   ./misc/sync-eks-upgrade-skill.sh
#
# Run from the repo root (sample-apex-skills/).

set -euo pipefail

UPSTREAM_REPO="https://github.com/aws-samples/sample-eks-upgrade-skill.git"
UPSTREAM_SKILL_DIR=".claude/skills/eks-upgrade"
LOCAL_SKILL_PATH="skills/eks-upgrade-check"

# Resolve repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Sync eks-upgrade-check from upstream ==="
echo "Repo root: $REPO_ROOT"
echo ""

# --- Step 1: Clone upstream into a temp directory ---
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Cloning upstream: $UPSTREAM_REPO"
git clone --depth 1 "$UPSTREAM_REPO" "$TEMP_DIR/sample-eks-upgrade-skill" 2>&1
echo ""

UPSTREAM_ROOT="$TEMP_DIR/sample-eks-upgrade-skill"
UPSTREAM_DIR="$UPSTREAM_ROOT/$UPSTREAM_SKILL_DIR"

if [ ! -f "$UPSTREAM_DIR/SKILL.md" ]; then
    echo "ERROR: Upstream skill not found at $UPSTREAM_SKILL_DIR/SKILL.md"
    exit 1
fi

# --- Step 2: Wipe local eks-upgrade-check ---
LOCAL_DIR="$REPO_ROOT/$LOCAL_SKILL_PATH"

echo "Removing local eks-upgrade-check: $LOCAL_DIR"
rm -rf "$LOCAL_DIR"
echo ""

# --- Step 3: Copy only allowlisted skill components ---
echo "Copying core skill components to local..."
# NOTE: upstream's progressive-disclosure docs live under `steering/`;
# we rename to `references/` here (see Apex-flavored deviation #2 in
# the header). Cross-refs are rewritten in Step 5.
mkdir -p "$LOCAL_DIR/references" "$LOCAL_DIR/data" "$LOCAL_DIR/tools"

# Core skill file
cp "$UPSTREAM_DIR/SKILL.md" "$LOCAL_DIR/SKILL.md"

# License (copied from upstream repo root, since the skill dir doesn't carry one)
if [ -f "$UPSTREAM_ROOT/LICENSE" ]; then
    cp "$UPSTREAM_ROOT/LICENSE" "$LOCAL_DIR/LICENSE"
else
    echo "WARNING: Upstream LICENSE not found at repo root — skipping"
fi

# Progressive-disclosure files (upstream `steering/` -> local `references/`)
cp "$UPSTREAM_DIR/steering/"*.md "$LOCAL_DIR/references/"

# Data files
cp "$UPSTREAM_DIR/data/"*.json "$LOCAL_DIR/data/"

# Tools (Python helpers)
cp "$UPSTREAM_DIR/tools/"*.py "$LOCAL_DIR/tools/"

echo ""

# --- Step 4: Rewrite cross-refs `steering/` -> `references/` (apex-flavored) ---
echo "Rewriting 'steering/' cross-refs to 'references/' inside the vendored skill..."

# Files that may contain cross-refs: SKILL.md and every .md under references/.
# We rewrite all literal `steering/` substrings to `references/`. Scope is
# limited to files INSIDE the vendored skill dir, so it cannot affect any
# other apex content.
#
# Use `sed -i.bak` for portability across BSD (macOS) and GNU sed; remove
# the .bak files immediately after.
find "$LOCAL_DIR" -type f \( -name "SKILL.md" -o -path "$LOCAL_DIR/references/*.md" \) \
    -exec sed -i.bak 's|steering/|references/|g' {} +
find "$LOCAL_DIR" -name "*.bak" -delete

echo ""

# --- Step 5: Rewrite the MCP Server Setup section (apex-flavored) ---
echo "Rewriting 'MCP Server Setup' section to point at apex eks-mcp-server skill..."

SKILL_MD="$LOCAL_DIR/SKILL.md"
SKILL_MD_TMP="$LOCAL_DIR/SKILL.md.tmp"

# The upstream section runs from "### MCP Server Setup" up to (but not
# including) the next "###" or "##" heading. We replace it with a block
# that keeps the upstream's fallback semantics but redirects setup to
# the eks-mcp-server skill in this repo.
awk '
  BEGIN { in_block = 0 }
  /^### MCP Server Setup[[:space:]]*$/ {
    in_block = 1
    print "### MCP Server Setup"
    print ""
    print "This skill works without any MCP server — it falls back to AWS CLI and kubectl commands. That fallback path is the default in apex."
    print ""
    print "For richer EKS operations (live cluster reads, upgrade insights, K8s resource introspection), enable the EKS MCP server via the apex `eks-mcp-server` skill — it walks you through both AWS-hosted and self-hosted setup options. Once configured, this skill will prefer MCP tools over CLI for EKS operations."
    print ""
    print "Note: Apex does NOT ship a project-root `.mcp.json`. MCP setup is opt-in and user-driven through the `eks-mcp-server` skill."
    next
  }
  in_block && /^#{2,3}[[:space:]]/ {
    in_block = 0
    print ""
    print
    next
  }
  in_block { next }
  { print }
' "$SKILL_MD" > "$SKILL_MD_TMP"

mv "$SKILL_MD_TMP" "$SKILL_MD"

echo ""

# --- Step 6: Rewrite the SKILL.md description (apex-flavored, "pushy") ---
echo "Rewriting SKILL.md description with natural-question phrasings..."

# Upstream's description is a keyword list ("EKS upgrade, cluster upgrade,
# upgrade readiness, ..."). The apex review feedback (#36) calls for a
# pushier wording that mirrors how sibling skills like eks-best-practices
# and eks-recon advertise themselves — listing literal natural-question
# phrasings ("can I upgrade my cluster?", "is my cluster ready for
# 1.32?", etc.) so the skill triggers on casual user wording instead of
# only matching technical keywords.
#
# We replace the entire `description:` line in the YAML frontmatter. Awk
# matches the first `^description:` line and substitutes; the rest of the
# file passes through untouched.
awk -v new_desc='description: Assess EKS cluster upgrade readiness — run automated checks across 8 areas (version, breaking changes, deprecated APIs, add-on compatibility, node readiness, workload risks, AWS Insights, upgrade plan), calculate a 0-100 readiness score with a hard-blocker override, and generate a markdown/HTML report with prioritized remediation. Use this skill whenever someone asks "can I upgrade my cluster?", "is my cluster ready for 1.32?", "are we good to go to 1.33?", "what is blocking my upgrade?", or "should we move to the next version?" — even if they do not say "readiness" or "score". Falls back to AWS CLI and kubectl when the EKS MCP server is unavailable.' '
  BEGIN { replaced = 0 }
  /^description:/ && !replaced {
    print new_desc
    replaced = 1
    next
  }
  { print }
' "$SKILL_MD" > "$SKILL_MD_TMP"

mv "$SKILL_MD_TMP" "$SKILL_MD"

echo ""

# --- Step 7: Write UPSTREAM.md provenance file ---
echo "Writing UPSTREAM.md provenance..."
cat > "$LOCAL_DIR/UPSTREAM.md" <<EOF
# Upstream Provenance

This skill is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | $UPSTREAM_REPO |
| Source path | \`$UPSTREAM_SKILL_DIR/\` |
| Refresh command | \`./misc/sync-eks-upgrade-skill.sh\` |
| License | See \`LICENSE\` (copied verbatim from upstream) |

## Local modifications applied at sync time

The sync script applies three deterministic edits to upstream content:

1. **\`### MCP Server Setup\` section is replaced.** Apex does not ship a project-root \`.mcp.json\`; MCP setup is delegated to the \`eks-mcp-server\` skill in this repo. The upstream's fallback note ("falls back to AWS CLI and kubectl") is preserved.
2. **\`steering/\` -> \`references/\` rename.** Upstream's progressive-disclosure docs live under \`steering/\`, but apex already uses a top-level \`steering/\` directory at the repo root for workflow orchestration (different concept). The sync script renames the directory on copy and rewrites all internal cross-refs from \`steering/\` to \`references/\` inside \`SKILL.md\` and the 8 progressive-disclosure files. This aligns the layout with the Anthropic skill spec's canonical name for "additional documentation agents read on demand."
3. **\`description:\` frontmatter is replaced with a "pushy" wording.** Upstream's description is a keyword list. Apex review feedback (#36) calls for natural-question phrasings ("can I upgrade my cluster?", "is my cluster ready for 1.32?", etc.) that mirror sibling skills like \`eks-best-practices\` and \`eks-recon\`. The sync script replaces the whole \`description:\` line on every run.

Everything else is byte-for-byte from upstream.

## To propose changes

Open a PR against the upstream repo:
$UPSTREAM_REPO

Then re-run the sync script here.
EOF

echo ""

# --- Step 7: Show what we got ---
echo "=== Synced files ==="
find "$LOCAL_DIR" -type f | sort | while read -r f; do
    echo "  ${f#$REPO_ROOT/}"
done
echo ""

echo "=== Done ==="
echo "eks-upgrade-check synced from upstream successfully."
echo ""
echo "Next steps:"
echo "  1. Review the synced files (git diff)"
echo "  2. Ensure .claude/skills/eks-upgrade-check/ symlink exists:"
echo "       ln -sfn ../../skills/eks-upgrade-check .claude/skills/eks-upgrade-check"
echo "  3. Run ./misc/update-skills-references.sh to update skills/README.md"
