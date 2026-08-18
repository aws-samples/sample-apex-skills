#!/usr/bin/env bash
# sync-dotnet-aws-ecs-skill.sh
#
# Syncs the dotnet-aws-ecs skill from the upstream sample-appmod-skills repo.
# Source: https://github.com/adisimon217/sample-appmod-skills
# License: MIT (LICENSE is copied verbatim from the upstream repo root)
#
# This script treats the upstream repo as the source of truth.
# It clones the upstream repo into a temp directory, then replaces
# our local skills/dotnet-aws-ecs folder with ONLY the allowlisted
# skill components:
#   - SKILL.md           (the skill itself, from upstream dotnet-aws-ecs/)
#   - LICENSE            (license compliance — copied from the upstream
#                         REPO ROOT, since the skill dir doesn't carry one;
#                         if missing upstream, a WARNING is emitted and the
#                         sync continues)
#   - references/*.md    (progressive-disclosure docs — upstream already
#                         uses the references/ naming, no rename needed)
#   - data/**            (only if upstream provides dotnet-aws-ecs/data/)
#   - tools/**           (only if upstream provides dotnet-aws-ecs/tools/)
#
# Excluded (deliberately NOT copied):
#   - .git/, .github/
#   - Upstream repo-root README.md
#   - Anything outside dotnet-aws-ecs/ (other skill directories, docs, etc.)
#
# Apex-flavored deviations (deterministic edits applied at sync time):
#
#   1. SKILL.md — the `version:` top-level frontmatter line is removed.
#      Reason: the APEX frontmatter validator (misc/validate-frontmatter.py)
#      allows only name/description/license/metadata/allowed-tools as
#      top-level frontmatter keys.
#
#   Every other vendored file is byte-for-byte identical to upstream
#   (UPSTREAM.md and .vendor-sha are apex-side metadata, not upstream
#   content). This list MUST stay identical to the "Local modifications
#   applied at sync time" section of the generated UPSTREAM.md. See Step 5
#   below for the rules that apply to every edit.
#
# BSD/GNU portability conventions (mandatory for any future edit):
#   - Use `sed -i.bak` and delete the .bak files immediately afterwards
#     (works on both BSD/macOS and GNU sed).
#   - No GNU-only flags (the script must run on ubuntu-latest AND macOS).
#
# Usage:
#   chmod +x misc/sync-dotnet-aws-ecs-skill.sh
#   ./misc/sync-dotnet-aws-ecs-skill.sh
#
# Run from the repo root (sample-apex-skills/).

set -euo pipefail

UPSTREAM_REPO="https://github.com/adisimon217/sample-appmod-skills.git"
UPSTREAM_SKILL_DIR="dotnet-aws-ecs"
LOCAL_SKILL_PATH="skills/dotnet-aws-ecs"

# Resolve repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Sync dotnet-aws-ecs from upstream ==="
echo "Repo root: $REPO_ROOT"
echo ""

# --- Step 1: Clone upstream into a temp directory ---
TEMP_DIR=$(mktemp -d)
# Single-quote the trap so $TEMP_DIR expands when the trap fires, not now (SC2064).
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Cloning upstream: $UPSTREAM_REPO"
git clone --depth 1 "$UPSTREAM_REPO" "$TEMP_DIR/sample-appmod-skills" 2>&1
echo ""

UPSTREAM_ROOT="$TEMP_DIR/sample-appmod-skills"
UPSTREAM_DIR="$UPSTREAM_ROOT/$UPSTREAM_SKILL_DIR"

# --- Step 2: Guard — verify upstream layout BEFORE wiping anything ---
# This check MUST stay ahead of the `rm -rf` in Step 3: if the upstream
# layout changes, we fail here with the local skill dir untouched.
if [ ! -f "$UPSTREAM_DIR/SKILL.md" ]; then
    echo "ERROR: Upstream skill not found at $UPSTREAM_SKILL_DIR/SKILL.md" >&2
    echo "The upstream repo layout may have changed. Local $LOCAL_SKILL_PATH is untouched." >&2
    exit 1
fi

# The copy step below globs references/*.md, which fails after the rm if the
# directory is empty or absent — wiping local then aborting. Guard it here too,
# while local is still untouched, so every path the copy needs is verified before
# anything is removed.
if ! ls "$UPSTREAM_DIR/references/"*.md > /dev/null 2>&1; then
    echo "ERROR: Upstream has no references/*.md at $UPSTREAM_SKILL_DIR/references/" >&2
    echo "The upstream repo layout may have changed. Local $LOCAL_SKILL_PATH is untouched." >&2
    exit 1
fi

# --- Step 2b: Detect a DevOps Agent port (informational only) ---
# Upstream currently ships no DevOpsAgent/ port. If one appears, we only
# announce it here and keep going — nothing is created under devops-agent/.
if [ -d "$UPSTREAM_ROOT/DevOpsAgent" ]; then
    echo "NOTE: Upstream now provides a DevOpsAgent/ directory."
    echo "      This script does NOT vendor it — nothing is created under devops-agent/."
    echo "      Consider extending the vendoring setup if a port is wanted."
    echo ""
fi

# --- Step 3: Wipe local dotnet-aws-ecs ---
LOCAL_DIR="$REPO_ROOT/$LOCAL_SKILL_PATH"

echo "Removing local dotnet-aws-ecs: $LOCAL_DIR"
rm -rf "$LOCAL_DIR"
echo ""

# --- Step 4: Copy only allowlisted skill components ---
echo "Copying core skill components to local..."
mkdir -p "$LOCAL_DIR/references"

# Core skill file (existence guaranteed by the Step 2 guard)
cp "$UPSTREAM_DIR/SKILL.md" "$LOCAL_DIR/SKILL.md"

# License (copied from upstream repo root, since the skill dir doesn't carry one)
if [ -f "$UPSTREAM_ROOT/LICENSE" ]; then
    cp "$UPSTREAM_ROOT/LICENSE" "$LOCAL_DIR/LICENSE"
else
    echo "WARNING: Upstream LICENSE not found at repo root — skipping (initial-sync verification will catch a missing vendored LICENSE)" >&2
fi

# Progressive-disclosure files (upstream already uses references/ naming)
cp "$UPSTREAM_DIR/references/"*.md "$LOCAL_DIR/references/"

# Optional components (copied only if upstream provides them)
if [ -d "$UPSTREAM_DIR/data" ]; then
    cp -R "$UPSTREAM_DIR/data" "$LOCAL_DIR/data"
fi
if [ -d "$UPSTREAM_DIR/tools" ]; then
    cp -R "$UPSTREAM_DIR/tools" "$LOCAL_DIR/tools"
fi

echo ""

# --- Step 5: Deterministic edits (apex-flavored deviations) ---
#
# Upstream already uses references/ naming, has no .mcp.json assumption,
# and the description is vendored as-is (distinguishability vs ecs-modernize
# is verified at initial sync — see UPSTREAM.md / spec vendor-dotnet-aws-ecs).
#
# For every edit in this section, you MUST:
#   1. Fail with a non-zero exit if the edit target (file/line/pattern) is
#      not found in the copied content (do NOT silently no-op).
#   2. List the edit in BOTH this header comment and UPSTREAM.md below,
#      keeping the two lists identical.
#   3. Keep the edit deterministic (same output for the same upstream
#      commit, regardless of run time or environment).
#   4. Use `sed -i.bak` + rm *.bak (BSD/GNU portable), no GNU-only flags.

# Edit 1: SKILL.md — remove the `version:` top-level frontmatter line.
# Reason: the APEX frontmatter validator (misc/validate-frontmatter.py)
# allows only name/description/license/metadata/allowed-tools top-level keys.
echo "Applying deterministic edit 1: remove 'version:' frontmatter line from SKILL.md..."
# Guard (Req 5.7): fail loudly if the edit target is gone from upstream.
# The frontmatter block is bounded by '---' on line 1 and the next '---'
# line, so both the guard and the deletion are restricted to lines
# 2..closing-'---' — a 'version:' line in the markdown body is never touched.
if ! sed -n '2,/^---$/p' "$LOCAL_DIR/SKILL.md" | grep -q '^version:'; then
    echo "ERROR: deterministic edit 1 target not found: expected a 'version:' top-level line in the YAML frontmatter of $LOCAL_SKILL_PATH/SKILL.md" >&2
    echo "Upstream may have dropped the key — update Step 5 and both edit lists (script header + UPSTREAM.md) accordingly." >&2
    exit 1
fi
sed -i.bak '2,/^---$/{/^version:/d;}' "$LOCAL_DIR/SKILL.md"
rm -f "$LOCAL_DIR/SKILL.md.bak"

echo ""

# --- Step 6: Write UPSTREAM.md provenance file ---
echo "Writing UPSTREAM.md provenance..."
# Content is deliberately static — no timestamps or other run-time values —
# so repeated syncs of the same upstream commit are byte-identical. The
# quoted heredoc delimiter keeps everything literal (no expansion).
cat > "$LOCAL_DIR/UPSTREAM.md" <<'EOF'
# Upstream Provenance

This skill is **vendored** from an upstream repo. Do not edit files here
directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | https://github.com/adisimon217/sample-appmod-skills.git |
| Source path | `dotnet-aws-ecs/` |
| Refresh command | `./misc/sync-dotnet-aws-ecs-skill.sh` |
| License | See `LICENSE` (copied verbatim from upstream repo root) |
| Last synced commit | See `.vendor-sha` in this directory |

## Local modifications applied at sync time

- `SKILL.md`: the `version:` top-level frontmatter line is removed at
  sync time (the APEX frontmatter policy allows only the
  name/description/license/metadata/allowed-tools top-level keys).

Everything else is byte-for-byte from upstream (`LICENSE` is copied
from the upstream repo root; `UPSTREAM.md` and `.vendor-sha` are
apex-side metadata, not upstream content).

## To propose changes

Open a PR against the upstream repo:
https://github.com/adisimon217/sample-appmod-skills.git

Then re-run the sync script here.
EOF

echo ""

# --- Step 7: Stage new files for generators ---
echo "Staging synced files for generator visibility (git ls-files)..."
# NOTE: no `|| true` here (intentional deviation from sync-eks-upgrade-skill.sh):
# a failed `git add` must fail the sync via set -e.
git -C "$REPO_ROOT" add "$LOCAL_DIR"

echo ""

# --- Step 8: Show what we got ---
echo "=== Synced files ==="
find "$LOCAL_DIR" -type f | sort | while read -r f; do
    echo "  ${f#"$REPO_ROOT"/}"
done
echo ""

UPSTREAM_SHA="$(git -C "$UPSTREAM_ROOT" rev-parse HEAD)"
echo "Upstream HEAD SHA: $UPSTREAM_SHA"
echo ""

echo "=== Done ==="
echo "dotnet-aws-ecs synced from upstream successfully."
echo ""
echo "Next steps:"
echo "  1. Review the synced files (git diff --cached)"
echo "  2. Record the upstream SHA (initial sync only — the weekly vendor-update"
echo "     workflow maintains it afterwards):"
echo "       echo '$UPSTREAM_SHA' > skills/dotnet-aws-ecs/.vendor-sha"
echo "  3. Ensure .claude/skills/dotnet-aws-ecs symlink exists:"
echo "       ln -sfn ../../skills/dotnet-aws-ecs .claude/skills/dotnet-aws-ecs"
echo "  4. Run ./misc/update-all-references.sh && ./misc/update-pages.sh"
echo "  5. Run python3 misc/validate-frontmatter.py"
