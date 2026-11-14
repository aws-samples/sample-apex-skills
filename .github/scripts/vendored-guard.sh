#!/usr/bin/env bash
# Fails a pull request that edits a vendored folder, unless it is a vendor
# sync. A vendored folder is any directory that holds UPSTREAM.md or
# .vendor-sha on the pull request's base commit; its files come from an
# upstream repo and the next sync overwrites local edits.
#
# A pull request may change vendored files when either:
#   - the vendor-update workflow opened it: author github-actions[bot] and a
#     chore/vendor-update-* branch in this repository, or
#   - a maintainer added the vendor-sync label, for a sync script run by hand.
#
# Inputs (environment): BASE_SHA, HEAD_SHA, PR_AUTHOR, HEAD_REF, HEAD_REPO,
# BASE_REPO, HAS_SYNC_LABEL (true or false). Run from the repository root
# with both commits fetched.

set -euo pipefail

ISSUE_URL="https://github.com/aws-samples/sample-apex-skills/issues/189"

if [ "${PR_AUTHOR:-}" = "github-actions[bot]" ] &&
   [ "${HEAD_REPO:-}" = "${BASE_REPO:-}" ] &&
   [[ "${HEAD_REF:-}" == chore/vendor-update-* ]]; then
  echo "vendored-guard: allowed, vendor-update workflow pull request"
  exit 0
fi
if [ "${HAS_SYNC_LABEL:-}" = "true" ]; then
  echo "vendored-guard: allowed, vendor-sync label"
  exit 0
fi

markers=$(git ls-tree -r --name-only "$BASE_SHA" | grep -E '(^|/)(UPSTREAM\.md|\.vendor-sha)$' || true)
changed=$(git diff --name-only --no-renames "$BASE_SHA...$HEAD_SHA")

hits=0
while IFS= read -r path; do
  [ -n "$path" ] || continue
  while IFS= read -r marker; do
    [ -n "$marker" ] || continue
    dir=$(dirname "$marker")
    if [[ "$path" == "$dir"/* ]]; then
      # Point at UPSTREAM.md when the folder has one.
      if grep -qx "$dir/UPSTREAM.md" <<< "$markers"; then
        marker="$dir/UPSTREAM.md"
      fi
      echo "::error file=${path}::${path} is in a vendored folder (see ${marker}). Change it in the upstream repo and re-run the sync script. See ${ISSUE_URL}"
      hits=$((hits + 1))
      break
    fi
  done <<< "$markers"
done <<< "$changed"

if [ "$hits" -gt 0 ]; then
  echo "vendored-guard: ${hits} vendored file(s) changed outside a vendor sync"
  exit 1
fi
echo "vendored-guard: no vendored file changed"
