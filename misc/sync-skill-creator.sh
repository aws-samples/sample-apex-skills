#!/usr/bin/env bash
# sync-skill-creator.sh
#
# Syncs the skill-creator skill from the upstream Anthropic skills repo.
# Source: https://github.com/anthropics/skills
#
# This script treats Anthropic's skill-creator as the source of truth.
# It clones (or pulls) the upstream repo into a temp directory, then
# replaces our local skill-creator folder entirely with the upstream version.
#
# Usage:
#   chmod +x misc/sync-skill-creator.sh
#   ./misc/sync-skill-creator.sh
#
# Run from the repo root (sample-apex-skills/).

set -euo pipefail

UPSTREAM_REPO="https://github.com/anthropics/skills.git"
UPSTREAM_SKILL_PATH="skills/skill-creator"
LOCAL_SKILL_PATH="skills/skill-creator"

# Resolve repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Sync skill-creator from upstream ==="
echo "Repo root: $REPO_ROOT"
echo ""

# --- Step 1: Clone or pull upstream into a temp directory ---
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Cloning upstream: $UPSTREAM_REPO"
git clone --depth 1 "$UPSTREAM_REPO" "$TEMP_DIR/skills" 2>&1
echo ""

UPSTREAM_DIR="$TEMP_DIR/skills/$UPSTREAM_SKILL_PATH"

if [ ! -d "$UPSTREAM_DIR" ]; then
    echo "ERROR: Upstream skill-creator not found at $UPSTREAM_SKILL_PATH"
    exit 1
fi

# --- Step 2: Wipe local skill-creator ---
LOCAL_DIR="$REPO_ROOT/$LOCAL_SKILL_PATH"

echo "Removing local skill-creator: $LOCAL_DIR"
rm -rf "$LOCAL_DIR"
echo ""

# --- Step 3: Copy upstream skill-creator ---
echo "Copying upstream skill-creator to local..."
cp -r "$UPSTREAM_DIR" "$LOCAL_DIR"
echo ""

# --- Step 4: Show what we got ---
echo "=== Synced files ==="
find "$LOCAL_DIR" -type f | sort | while read -r f; do
    echo "  $(realpath --relative-to="$REPO_ROOT" "$f")"
done
echo ""

echo "=== Done ==="
echo "skill-creator synced from upstream successfully."
echo ""
echo "Next steps:"
echo "  1. Review the synced files"
echo "  2. Run ./misc/update-skills-references.sh to update skills/README.md"
