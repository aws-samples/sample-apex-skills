#!/usr/bin/env bash
# sync-eks-operation-review-skill.sh
#
# Syncs the eks-operation-review skill from the upstream sample-eks-operation-review-skill repo.
# Source: https://github.com/aws-samples/sample-eks-operation-review-skill
# License: MIT-0 (LICENSE is copied verbatim)
#
# This script treats the upstream repo as the source of truth.
# It clones the upstream repo into a temp directory, then replaces
# our local eks-operation-review folder with ONLY the core skill components:
#   - SKILL.md           (the skill itself, with frontmatter description)
#   - LICENSE            (license compliance)
#   - references/*.md    (11 progressive-disclosure docs — RENAMED from upstream's `steering/` for apex compatibility, see Apex-flavored deviations below)
#   - tools/*.py         (markdown-to-HTML report converter)
#
# Excluded (deliberately NOT copied):
#   - .git/, .github/, .claude/, .mcp.json
#   - evals/, docs/, reports/
#   - README.md, CHANGELOG.md, CLAUDE.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md, SECURITY.md
#   - .gitignore
#
# Apex-flavored deviations (deterministic edits applied at sync time):
#
# 1. steering/ -> references/ rename — Upstream's progressive-disclosure
#    docs live under steering/, but apex already uses a top-level steering/
#    directory at the repo root for workflow orchestration (different
#    concept). To avoid the collision and align with the Anthropic skill
#    spec's canonical name for "additional documentation agents read on
#    demand," we rename the directory on copy and rewrite all internal
#    cross-refs from `steering/` to `references/` inside SKILL.md and the
#    11 progressive-disclosure files.
#
# 2. SKILL.md body path fix — Upstream's body says "Read and follow
#    `.claude/commands/eks-operation-review.md`" — that path doesn't exist
#    in apex (the slash-command content is baked into apex's
#    steering/workflows/eks-operation-review.md instead). We rewrite the
#    line to point at the apex workflow location via the apex-steering
#    symlink convention used by other apex slash commands.
#
# 3. SKILL.md Prerequisites MCP line — Upstream lists "MCP servers
#    configured in .mcp.json" as a prereq. Apex doesn't ship .mcp.json;
#    MCP setup is handled by the eks-mcp-server skill. We rewrite the
#    line to point users at that skill instead.
#
# 4. SKILL.md description block-scalar flattening — Upstream uses YAML
#    folded-scalar form (description: > followed by indented lines).
#    Apex's catalog generator (misc/update-skills-references.sh) reads
#    everything after `description:` on the same line and would render
#    just `>` for this skill's catalog row. We flatten the block scalar
#    into a single-line `description: <one line>` so the catalog renders
#    the actual text. The wording is byte-for-byte identical — only the
#    YAML representation changes (newlines folded into spaces, leading
#    indentation stripped).
#
# NOTE: Unlike sync-eks-upgrade-skill.sh, this script does NOT need a
# pushy-description rewrite — skill-creator's restrained-style description
# in upstream is already apex-compatible (explicit-trigger phrasing, no
# over-triggering risk).
#
# Usage:
#   chmod +x misc/sync-eks-operation-review-skill.sh
#   ./misc/sync-eks-operation-review-skill.sh
#
# Run from the repo root (sample-apex-skills/).

set -euo pipefail

UPSTREAM_REPO="https://github.com/aws-samples/sample-eks-operation-review-skill.git"
LOCAL_SKILL_PATH="skills/eks-operation-review"

# Resolve repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Sync eks-operation-review from upstream ==="
echo "Repo root: $REPO_ROOT"
echo ""

# --- Step 1: Clone upstream into a temp directory ---
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Cloning upstream: $UPSTREAM_REPO"
git clone --depth 1 "$UPSTREAM_REPO" "$TEMP_DIR/sample-eks-operation-review-skill" 2>&1
echo ""

UPSTREAM_ROOT="$TEMP_DIR/sample-eks-operation-review-skill"

if [ ! -f "$UPSTREAM_ROOT/SKILL.md" ]; then
    echo "ERROR: Upstream SKILL.md not found at repo root"
    exit 1
fi

if [ ! -d "$UPSTREAM_ROOT/steering" ]; then
    echo "ERROR: Upstream steering/ directory not found at repo root"
    exit 1
fi

# --- Step 2: Wipe local eks-operation-review ---
LOCAL_DIR="$REPO_ROOT/$LOCAL_SKILL_PATH"

echo "Removing local eks-operation-review: $LOCAL_DIR"
rm -rf "$LOCAL_DIR"
echo ""

# --- Step 3: Copy only allowlisted skill components ---
echo "Copying core skill components to local..."
# NOTE: upstream's progressive-disclosure docs live under `steering/`;
# we rename to `references/` here (see Apex-flavored deviation #1 in
# the header). Cross-refs are rewritten in Step 4.
mkdir -p "$LOCAL_DIR/references" "$LOCAL_DIR/tools"

# Core skill file
cp "$UPSTREAM_ROOT/SKILL.md" "$LOCAL_DIR/SKILL.md"

# License
if [ -f "$UPSTREAM_ROOT/LICENSE" ]; then
    cp "$UPSTREAM_ROOT/LICENSE" "$LOCAL_DIR/LICENSE"
else
    echo "WARNING: Upstream LICENSE not found at repo root — skipping"
fi

# Progressive-disclosure files (upstream `steering/` -> local `references/`)
cp "$UPSTREAM_ROOT/steering/"*.md "$LOCAL_DIR/references/"

# Tools (Python helpers)
cp "$UPSTREAM_ROOT/tools/"*.py "$LOCAL_DIR/tools/"

echo ""

# --- Step 4: Rewrite cross-refs `steering/` -> `references/` (apex-flavored #1) ---
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

# --- Step 5: Flatten YAML block-scalar description (apex-flavored #4) ---
echo "Flattening YAML block-scalar description into a single line..."

SKILL_MD="$LOCAL_DIR/SKILL.md"

# Upstream uses YAML folded-scalar form:
#   description: >
#     line one of the description
#     line two of the description
#     ...
#
# Apex's catalog generator (misc/update-skills-references.sh) reads
# everything after `description:` on the same line. With the block
# scalar, that's just `>`. Result: catalog renders `>` instead of the
# actual description.
#
# Fix: detect `description: >` (or `description: >-`), collect the
# indented continuation lines until a non-indented line, join them
# with spaces, and replace the whole block with a single
# `description: <one-line text>` entry.
#
# The wording is preserved byte-for-byte (modulo whitespace folding,
# which is what the YAML > scalar means anyway).
python3 - "$SKILL_MD" <<'PYEOF'
import sys, re
path = sys.argv[1]
with open(path) as f:
    text = f.read()

# Match `description: >` (or `>-`), then capture continuation lines that
# are indented (start with whitespace), stopping at the first non-indented
# line (next frontmatter key or `---` terminator).
pattern = re.compile(
    r'^description:[ \t]*>-?[ \t]*\n((?:[ \t]+\S.*\n)+)',
    re.MULTILINE,
)

def fold(match):
    block = match.group(1)
    # Strip leading whitespace from each line, join with single spaces.
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    return f"description: {' '.join(lines)}\n"

new_text, n = pattern.subn(fold, text, count=1)
if n == 0:
    # Already flattened (e.g., upstream switched to single-line, or
    # this is a re-run on already-flattened content). No-op is safe.
    sys.exit(0)

with open(path, 'w') as f:
    f.write(new_text)
PYEOF

echo ""

# --- Step 6: Rewrite SKILL.md body path (apex-flavored #2) ---
echo "Rewriting SKILL.md body path (.claude/commands/... -> apex workflow)..."

SKILL_MD="$LOCAL_DIR/SKILL.md"

# Upstream line:
#   Read and follow `.claude/commands/eks-operation-review.md` — it
#   contains the full workflow, tool usage rules, and steering file
#   map. Load each steering file from `steering/` before running its
#   corresponding section.
#
# After the Step 4 rename, "steering/" inside that line has already
# become "references/". Now we need to fix the .claude/commands/ path
# to point at apex's workflow location. Apex slash commands use the
# `~/.claude/apex-steering/workflows/<name>.md` symlink convention.
sed -i.bak \
    's|`\.claude/commands/eks-operation-review\.md`|`~/.claude/apex-steering/workflows/eks-operation-review.md`|g' \
    "$SKILL_MD"
rm -f "$SKILL_MD.bak"

echo ""

# --- Step 7: Rewrite SKILL.md Prerequisites MCP line (apex-flavored #3) ---
echo "Rewriting SKILL.md Prerequisites MCP line (.mcp.json -> eks-mcp-server skill)..."

# Upstream prereq:
#   - MCP servers configured in `.mcp.json`
# Apex equivalent:
#   - EKS MCP server configured (see the `eks-mcp-server` skill for setup);
#     apex does not ship a project-root .mcp.json
sed -i.bak \
    's|- MCP servers configured in `\.mcp\.json`|- EKS MCP server configured (see the `eks-mcp-server` skill for setup); apex does not ship a project-root `.mcp.json`|g' \
    "$SKILL_MD"
rm -f "$SKILL_MD.bak"

echo ""

# --- Step 8: Write UPSTREAM.md provenance file ---
echo "Writing UPSTREAM.md provenance..."
cat > "$LOCAL_DIR/UPSTREAM.md" <<EOF
# Upstream Provenance

This skill is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | $UPSTREAM_REPO |
| Source path | repo root (\`SKILL.md\`, \`steering/\`, \`tools/\`, \`LICENSE\`) |
| Refresh command | \`./misc/sync-eks-operation-review-skill.sh\` |
| License | See \`LICENSE\` (copied verbatim from upstream — MIT-0) |

## Local modifications applied at sync time

The sync script applies four deterministic edits to upstream content:

1. **\`steering/\` -> \`references/\` rename.** Upstream's progressive-disclosure docs live under \`steering/\`, but apex already uses a top-level \`steering/\` directory at the repo root for workflow orchestration (different concept). The sync script renames the directory on copy and rewrites all internal cross-refs from \`steering/\` to \`references/\` inside \`SKILL.md\` and the 11 progressive-disclosure files. This aligns the layout with the Anthropic skill spec's canonical name for "additional documentation agents read on demand."

2. **\`SKILL.md\` description block-scalar flattening.** Upstream uses YAML folded-scalar form (\`description: >\` followed by indented lines). Apex's catalog generator reads the same line as the key, so the catalog row would render just \`>\`. The sync flattens the block scalar to a single \`description: <one line>\` entry. Wording is preserved byte-for-byte; only the YAML representation changes.

3. **\`SKILL.md\` body path fix.** Upstream's body says "Read and follow \`.claude/commands/eks-operation-review.md\`" — that path doesn't exist in apex (the slash-command content is baked into apex's \`steering/workflows/eks-operation-review.md\` instead). The sync rewrites the reference to point at the apex workflow via the \`~/.claude/apex-steering\` symlink convention used by other apex slash commands.

4. **\`SKILL.md\` Prerequisites MCP line.** Upstream lists "MCP servers configured in \`.mcp.json\`" as a prerequisite. Apex doesn't ship \`.mcp.json\`; MCP setup is handled by the \`eks-mcp-server\` skill. The sync rewrites the line to point users at that skill instead.

The upstream description **wording** is NOT rewritten — skill-creator's restrained-style content is already apex-compatible. Only the YAML representation is flattened (Edit #2).

Everything else is byte-for-byte from upstream.

## To propose changes

Open a PR against the upstream repo:
$UPSTREAM_REPO

Then re-run the sync script here.
EOF

echo ""

# --- Step 8: Show what we got ---
echo "=== Synced files ==="
find "$LOCAL_DIR" -type f | sort | while read -r f; do
    echo "  ${f#$REPO_ROOT/}"
done
echo ""

echo "=== Done ==="
echo "eks-operation-review synced from upstream successfully."
echo ""
echo "Next steps:"
echo "  1. Review the synced files (git diff)"
echo "  2. Ensure .claude/skills/eks-operation-review/ symlink exists:"
echo "       ln -sfn ../../skills/eks-operation-review .claude/skills/eks-operation-review"
echo "  3. Run ./misc/update-all-references.sh to update README.md and skills/README.md catalogs"
