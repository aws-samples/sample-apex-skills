#!/usr/bin/env bash
# sync-terraform-skill.sh
#
# Syncs the terraform-skill from the upstream repo by Anton Babenko.
# Source: https://github.com/antonbabenko/terraform-skill
# License: Apache License 2.0
#
# This script treats the upstream repo as the source of truth.
# It clones the upstream repo into a temp directory, then replaces
# our local terraform-skill folder with ONLY the core skill components:
#   - SKILL.md       (the skill itself)
#   - LICENSE         (required for Apache 2.0 compliance)
#   - references/*.md (progressive disclosure content referenced by SKILL.md)
#
# Everything else (README, CLAUDE.md, CONTRIBUTING.md, CHANGELOG.md,
# tests/, .github/, .claude-plugin/) is left behind — those are repo
# management files, not skill components.
#
# Usage:
#   chmod +x misc/sync-terraform-skill.sh
#   ./misc/sync-terraform-skill.sh
#
# Run from the repo root (sample-apex-skills/).

set -euo pipefail

UPSTREAM_REPO="https://github.com/antonbabenko/terraform-skill.git"
LOCAL_SKILL_PATH="skills/terraform-skill"

# Resolve repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Sync terraform-skill from upstream ==="
echo "Repo root: $REPO_ROOT"
echo ""

# --- Step 1: Clone upstream into a temp directory ---
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Cloning upstream: $UPSTREAM_REPO"
git clone --depth 1 "$UPSTREAM_REPO" "$TEMP_DIR/terraform-skill" 2>&1
echo ""

UPSTREAM_DIR="$TEMP_DIR/terraform-skill"

if [ ! -f "$UPSTREAM_DIR/SKILL.md" ]; then
    echo "ERROR: Upstream terraform-skill not found (no SKILL.md)"
    exit 1
fi

# --- Step 2: Wipe local terraform-skill ---
LOCAL_DIR="$REPO_ROOT/$LOCAL_SKILL_PATH"

echo "Removing local terraform-skill: $LOCAL_DIR"
rm -rf "$LOCAL_DIR"
echo ""

# --- Step 3: Copy only core skill components ---
echo "Copying core skill components to local..."
mkdir -p "$LOCAL_DIR/references"

# Core skill file
cp "$UPSTREAM_DIR/SKILL.md" "$LOCAL_DIR/SKILL.md"

# License (required for Apache 2.0 compliance)
cp "$UPSTREAM_DIR/LICENSE" "$LOCAL_DIR/LICENSE"

# Progressive disclosure reference files
cp "$UPSTREAM_DIR/references/"*.md "$LOCAL_DIR/references/"

echo ""

# --- Step 4: Show what we got ---
echo "=== Synced files ==="
find "$LOCAL_DIR" -type f | sort | while read -r f; do
    echo "  $(realpath --relative-to="$REPO_ROOT" "$f")"
done
echo ""

echo "=== Done ==="
echo "terraform-skill synced from upstream successfully."
echo ""
echo "Next steps:"
echo "  1. Review the synced files"
echo "  2. Run ./misc/update-skills-references.sh to update skills/README.md"
