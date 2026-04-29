#!/usr/bin/env bash
# update-all-references.sh
#
# Thin orchestrator: runs every auto-gen script that rebuilds marker-delimited
# blocks in the repo's docs (Skills/Steering/Examples reference tables in
# README.md + skills/README.md). One entry point so contributors and CI don't
# have to remember which script owns which block.
#
# Usage:
#   ./misc/update-all-references.sh              # regenerate in place
#   ./misc/update-all-references.sh --check      # fail if any block is stale
#   ./misc/update-all-references.sh --dry-run    # preview; forwards to each script
#
# --check is what the `docs-sync` CI job runs: regenerate, then `git diff
# --exit-code` on the docs paths. Non-zero exit means someone edited a
# marker block by hand or added a skill/workflow/example without running
# the scripts — fix is `./misc/update-all-references.sh && git add … && commit`.

set -euo pipefail

MODE="run"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
elif [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SCRIPTS=(
  "misc/update-skills-references.sh"
  "misc/update-steering-references.sh"
  "misc/update-examples-references.sh"
)

# Files any script above may touch — the blast radius of --check.
TOUCHED_PATHS=(
  "README.md"
  "skills/README.md"
)

run_script() {
  local script="$1"
  case "$MODE" in
    dry-run) bash "$script" --dry-run ;;
    *)       bash "$script" ;;
  esac
}

for s in "${SCRIPTS[@]}"; do
  echo "▸ $s"
  run_script "$s"
done

if [[ "$MODE" == "check" ]]; then
  if ! git diff --quiet -- "${TOUCHED_PATHS[@]}"; then
    echo ""
    echo "ERROR: auto-generated blocks are stale. Diff:"
    git --no-pager diff -- "${TOUCHED_PATHS[@]}"
    echo ""
    echo "Fix: run ./misc/update-all-references.sh locally, commit the result."
    exit 1
  fi
  echo "✓ docs are in sync with skills/, steering/, examples/"
fi
