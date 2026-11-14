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
# Also copied: upstream's .claude/commands/eks-operation-review.md (the
# workflow) to skills/apex/runbooks/eks-operation-review/eks-operation-review.md,
# with steering/ rewritten to ../../../eks-operation-review/references/ (Step 8).
#
# Excluded (deliberately NOT copied):
#   - .git/, .github/, the rest of .claude/, .mcp.json
#   - evals/, docs/, reports/
#   - README.md, CHANGELOG.md, CLAUDE.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md, SECURITY.md
#   - .gitignore
#
# Apex-flavored deviations (deterministic edits applied at sync time):
# Edits before Step 8a are not anchor-checked: if upstream rewords an
# anchor, that edit silently does nothing.
#
# 1. steering/ -> references/ rename — Upstream's progressive-disclosure
#    docs live under steering/. Apex renames them to references/, the
#    Anthropic skill spec's canonical name for additional documentation
#    (this also avoided a clash with apex's former top-level steering/
#    directory, removed in v2). We rename the directory on copy and
#    rewrite all internal cross-refs from `steering/` to `references/`
#    inside SKILL.md and the 11 progressive-disclosure files.
#
# 2. SKILL.md body path fix — Upstream's body says "Read and follow
#    `.claude/commands/eks-operation-review.md`" — that path doesn't exist
#    in apex (Step 8 copies that file outside the vendored folder, to
#    skills/apex/runbooks/eks-operation-review/eks-operation-review.md).
#    We rewrite the line to that path, relative to this skill's folder.
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
# 5. Runbook fit (Steps 8 and 8a): the copied workflow is adapted to the
#    apex layout: `steering/` paths pointed at the eks-operation-review
#    skill's references/ folder, name/description frontmatter added, the
#    `.mcp.json` instructions and the fixed
#    `uvx awslabs.eks-mcp-server@<version>` test pointed at apex's
#    eks-mcp-server skill. The sync exits non-zero if an anchor is
#    missing; the runbook then has only its `steering/` paths rewritten
#    and UPSTREAM.md is not written until the script is fixed and re-run.
#
# 6. Report tool path (Step 7a): references/report-generation.md runs
#    `python3 tools/report_to_html.py`, upstream's repo-root layout. In apex
#    the tool sits in this skill's folder, so the command becomes
#    `python3 ${CLAUDE_SKILL_DIR}/tools/report_to_html.py`, as eks-upgrade-check
#    calls its tool. The sync exits non-zero if the anchor is missing.
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

# Upstream commit synced (the wipe above removed the old record)
git -C "$UPSTREAM_ROOT" rev-parse HEAD > "$LOCAL_DIR/.vendor-sha"

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
# to point at apex's workflow, which lives in the apex skill's
# runbooks/ folder (relative to this skill's folder, like references/).
sed -i.bak \
    's|`\.claude/commands/eks-operation-review\.md`|`../apex/runbooks/eks-operation-review/eks-operation-review.md` (relative to this skill'\''s folder)|g' \
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

# --- Step 7a: Point the report tool at this skill's folder (apex-flavored #6) ---
REPORT_GEN="$LOCAL_DIR/references/report-generation.md"
grep -q 'python3 tools/report_to_html\.py' "$REPORT_GEN" || { echo "ERROR: report tool anchor not found in $REPORT_GEN (upstream changed?)"; exit 1; }
sed -i.bak 's|python3 tools/report_to_html\.py|python3 ${CLAUDE_SKILL_DIR}/tools/report_to_html.py|g' "$REPORT_GEN"
rm -f "$REPORT_GEN.bak"

# --- Step 8: Copy upstream's workflow to the apex runbook ---
RUNBOOK="$REPO_ROOT/skills/apex/runbooks/eks-operation-review/eks-operation-review.md"
echo "Copying upstream .claude/commands/eks-operation-review.md to the apex runbook..."
mkdir -p "$(dirname "$RUNBOOK")"
cp "$UPSTREAM_ROOT/.claude/commands/eks-operation-review.md" "$RUNBOOK"
sed -i.bak 's|steering/|../../../eks-operation-review/references/|g' "$RUNBOOK"
rm -f "$RUNBOOK.bak"
echo 'This runbook is written by `misc/sync-eks-operation-review-skill.sh` from upstream (see `skills/eks-operation-review/UPSTREAM.md`); change it there, not here.' > "$(dirname "$RUNBOOK")/UPSTREAM.md"

# --- Step 8a: Fit the runbook to the apex layout (apex-flavored #5) ---
echo "Adapting the runbook to the apex layout (frontmatter, MCP setup)..."
python3 - "$RUNBOOK" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    text = f.read()

edits = [
    # apex ships no project-root .mcp.json; MCP setup is the eks-mcp-server skill
    ("update the EKS MCP server config in `.mcp.json`:",
     "set them in the EKS MCP server's `env` config through apex's `eks-mcp-server` skill "
     "(apex does not ship a project-root `.mcp.json`):"),
    ("Verify AWS_PROFILE and AWS_REGION in `.mcp.json`",
     "Verify AWS_PROFILE and AWS_REGION in the EKS MCP server config (run apex's `eks-mcp-server` skill)"),
]
for old, new in edits:
    if old not in text:
        sys.exit("ERROR: runbook edit anchor not found (upstream changed?): " + old.splitlines()[0])
    text = text.replace(old, new)

# No fixed server version: the eks-mcp-server skill owns how the server is run
lines = text.split("\n")
hits = [i for i, ln in enumerate(lines) if ln.startswith("> 2. Test the MCP server: `uvx awslabs.eks-mcp-server@")]
if not hits:
    sys.exit("ERROR: runbook edit anchor not found (upstream changed?): Test the MCP server line")
for i in hits:
    lines[i] = "> 2. Re-run apex's `eks-mcp-server` skill to check the server is installed and starts"
text = "\n".join(lines)

# Frontmatter the apex router reads (upstream's command file has none)
if not text.startswith("---\n"):
    text = ("---\nname: eks-operation-review\n"
            "description: Day 2 operational-review workflow. Runs the eks-operation-review skill end-to-end, a "
            "10-section structured assessment of a live cluster's operational excellence, with GREEN/AMBER/RED "
            "ratings and a markdown/HTML report including prioritized actions and AWS reference links.\n---\n\n"
            + text)

with open(path, "w") as f:
    f.write(text)
PYEOF

echo ""

# --- Step 8b: Write UPSTREAM.md provenance file ---
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

The sync script applies six deterministic edits to upstream content:

1. **\`steering/\` -> \`references/\` rename.** Upstream's progressive-disclosure docs live under \`steering/\`. Apex renames them to \`references/\`, the Anthropic skill spec's canonical name for additional documentation. The sync script renames the directory on copy and rewrites all internal cross-refs from \`steering/\` to \`references/\` inside \`SKILL.md\` and the 11 progressive-disclosure files.

2. **\`SKILL.md\` description block-scalar flattening.** Upstream uses YAML folded-scalar form (\`description: >\` followed by indented lines). Apex's catalog generator reads the same line as the key, so the catalog row would render just \`>\`. The sync flattens the block scalar to a single \`description: <one line>\` entry. Wording is preserved byte-for-byte; only the YAML representation changes.

3. **\`SKILL.md\` body path fix.** Upstream's body says "Read and follow \`.claude/commands/eks-operation-review.md\`": that path doesn't exist in apex. The sync copies that file, with its \`steering/\` paths rewritten to \`../../../eks-operation-review/references/\`, outside this folder to \`skills/apex/runbooks/eks-operation-review/eks-operation-review.md\`. The sync rewrites the reference to that file, relative to this skill's folder (\`../apex/runbooks/eks-operation-review/eks-operation-review.md\`).

4. **\`SKILL.md\` Prerequisites MCP line.** Upstream lists "MCP servers configured in \`.mcp.json\`" as a prerequisite. Apex doesn't ship \`.mcp.json\`; MCP setup is handled by the \`eks-mcp-server\` skill. The sync rewrites the line to point users at that skill instead.

5. **Runbook fit.** The copied workflow at \`skills/apex/runbooks/eks-operation-review/eks-operation-review.md\` gets its \`steering/\` paths pointed at this skill's folder (\`../../../eks-operation-review/references/\` from the runbook), apex's \`name\`/\`description\` frontmatter, and its \`.mcp.json\` instructions and fixed \`uvx awslabs.eks-mcp-server@<version>\` test pointed at the \`eks-mcp-server\` skill. The sync exits non-zero if an anchor is missing; the runbook then has only its \`steering/\` paths rewritten and UPSTREAM.md is not written until the script is fixed and re-run.

6. **Report tool path.** \`references/report-generation.md\` runs \`python3 tools/report_to_html.py\` (upstream's repo-root layout); the sync points it at this skill's folder, \`python3 \${CLAUDE_SKILL_DIR}/tools/report_to_html.py\`. The sync exits non-zero if the anchor is missing.

The upstream description **wording** is NOT rewritten — skill-creator's restrained-style content is already apex-compatible. Only the YAML representation is flattened (Edit #2).

Everything else is byte-for-byte from upstream.

## To propose changes

Open a PR against the upstream repo:
$UPSTREAM_REPO

Then re-run the sync script here.
EOF

echo ""

# --- Step 9: Sync DevOps Agent port ---
# Mirrors sync-eks-upgrade-skill.sh's port-sync steps, ADAPTED to
# op-review's upstream DevOpsAgent/ structure:
#   - upstream references/ already uses `references/` naming (no rename)
#   - upstream ships NO assets/ folder and NO iam-policy.json, so those
#     copy/extract steps are guarded and skipped cleanly (never error).
DEVOPS_DIR="$REPO_ROOT/devops-agent/eks-operation-review"
UPSTREAM_DEVOPS="$UPSTREAM_ROOT/DevOpsAgent"

echo "Syncing DevOps Agent port..."

# Guard: only run the port sync if upstream ships DevOpsAgent/SKILL.md.
# If upstream ever lacks it, leave the local port directory untouched and
# continue (do NOT error) — keeps the skill sync usable on its own.
if [ ! -f "$UPSTREAM_DEVOPS/SKILL.md" ]; then
    echo "  NOTE: upstream DevOpsAgent/SKILL.md not found — skipping DevOps Agent port sync (local port left untouched)"
else
    # Guard passed — wipe and replace the (previously placeholder) port dir
    echo "Removing local DevOps Agent port: $DEVOPS_DIR"
    rm -rf "$DEVOPS_DIR"
    echo ""

    # --- Step 10: Copy DevOps Agent port components ---
    echo "Copying DevOps Agent port to local..."

    mkdir -p "$DEVOPS_DIR/references"

    # SKILL.md (verbatim — port target is the DevOps Agent, not apex Claude
    # Code, so the apex-flavored SKILL.md deviations do NOT apply here;
    # matches the eks-upgrade-check port's verbatim-copy convention)
    cp "$UPSTREAM_DEVOPS/SKILL.md" "$DEVOPS_DIR/SKILL.md"

    # README.md → references/porting-notes.md (Differences section = porting
    # notes; excluded from upload zip by setup.sh; serves as docs page via
    # generators). Mirrors the upgrade port's convention.
    cp "$UPSTREAM_DEVOPS/README.md" "$DEVOPS_DIR/references/porting-notes.md"

    # Fix relative links broken by relocation (SKILL.md is now one dir up;
    # LICENSE is this repo's root one)
    sed -i.bak -e 's|(SKILL\.md)|(../SKILL.md)|g' -e 's|(\.\./LICENSE)|(../../../LICENSE)|g' "$DEVOPS_DIR/references/porting-notes.md"
    rm -f "$DEVOPS_DIR/references/porting-notes.md.bak"

    # References (upstream knowledge files — verbatim, already `references/`)
    cp "$UPSTREAM_DEVOPS/references/"*.md "$DEVOPS_DIR/references/"

    # Assets — GUARDED. Op-review's upstream DevOpsAgent/ ships no assets/.
    # Only copy if upstream actually provides a non-empty assets/ dir.
    if [ -d "$UPSTREAM_DEVOPS/assets" ] && [ -n "$(ls -A "$UPSTREAM_DEVOPS/assets" 2>/dev/null)" ]; then
        mkdir -p "$DEVOPS_DIR/assets"
        cp "$UPSTREAM_DEVOPS/assets/"* "$DEVOPS_DIR/assets/"
        echo "  Copied SKILL.md, references/ (+ porting-notes.md), assets/"
    else
        echo "  Copied SKILL.md, references/ (+ porting-notes.md); no upstream assets/ — skipped"
    fi

    echo ""

    # --- Step 11: IAM policy — GUARDED (skipped for op-review) ---
    # Unlike eks-upgrade-check, op-review's upstream ships NO iam-policy.json
    # and its root README has no IAM policy block to extract. Skip cleanly.
    echo "  No iam-policy.json for op-review port (upstream ships none) — skipped"
    echo ""

    # --- Step 12: Write DevOps Agent port UPSTREAM.md provenance ---
    echo "Writing DevOps Agent port UPSTREAM.md..."
    cat > "$DEVOPS_DIR/UPSTREAM.md" <<EOF
# Upstream Provenance

This DevOps Agent port is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | $UPSTREAM_REPO |
| Source path | \`DevOpsAgent/\` |
| Refresh command | \`./misc/sync-eks-operation-review-skill.sh\` |
| License | See \`skills/eks-operation-review/LICENSE\` (shared with the CC skill) |

## Local modifications applied at sync time

1. **\`DevOpsAgent/README.md\` → \`references/porting-notes.md\`** — the README's "Differences" section serves as porting documentation. Renamed so setup.sh excludes it from the upload zip (matching the eks-upgrade-check/eks-recon/eks-security pattern).

Unlike the eks-upgrade-check port, op-review's upstream \`DevOpsAgent/\` ships **no \`assets/\` directory and no \`iam-policy.json\`**, so those steps are skipped. Everything else is byte-for-byte from upstream's \`DevOpsAgent/\` directory.

## To propose changes

Open a PR against the upstream repo:
$UPSTREAM_REPO

Then re-run the sync script here.
EOF

    echo ""
fi

# --- Step 13: Stage synced files for generator visibility (git ls-files) ---
# update-pages.sh / update-all-references.sh enumerate tracked files via
# `git ls-files`, so newly-synced port files must be staged or the generators
# miss them on the next run (mirrors sync-eks-upgrade-skill.sh:321).
echo "Staging synced files for generator visibility (git ls-files)..."
git -C "$REPO_ROOT" add "$LOCAL_DIR" "$DEVOPS_DIR" "$(dirname "$RUNBOOK")" 2>/dev/null || true

echo ""

# --- Step 14: Show what we got ---
echo "=== Synced files (CC skill) ==="
find "$LOCAL_DIR" -type f | sort | while read -r f; do
    echo "  ${f#$REPO_ROOT/}"
done
echo ""

if [ -d "$DEVOPS_DIR" ]; then
    echo "=== Synced files (DevOps Agent port) ==="
    find "$DEVOPS_DIR" -type f | sort | while read -r f; do
        echo "  ${f#$REPO_ROOT/}"
    done
    echo ""
fi

echo "=== Done ==="
echo "eks-operation-review synced from upstream successfully."
echo ""
echo "Next steps:"
echo "  1. Review the synced files (git diff)"
echo "  2. Ensure .claude/skills/eks-operation-review/ symlink exists:"
echo "       ln -sfn ../../skills/eks-operation-review .claude/skills/eks-operation-review"
echo "  3. Run ./misc/update-all-references.sh && ./misc/update-pages.sh to update README.md, skills/README.md, and the docs site pages"
