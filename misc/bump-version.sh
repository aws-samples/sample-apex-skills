#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

VERSION="${1:-}"

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 <version>" >&2
  exit 2
fi

if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <version>" >&2
  echo "Example: $0 1.2.0" >&2
  exit 1
fi

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: '$VERSION' does not look like a valid semver (expected X.Y.Z)" >&2
  exit 1
fi

# Check every target before writing any, so a failed check leaves every file unchanged.
# The root README.md has no `--version vX.Y.Z` example since its rebuild, so it is not a target.
check() {
  if ! grep -qE -- "$2" "$1"; then
    echo "Error: $1 has no line matching '$2'; nothing was changed" >&2
    exit 1
  fi
}
check misc/installer/package.json '"version": "[^"]*"'
check misc/website/docs/getting-started.md '--version v[0-9]+\.[0-9]+\.[0-9]+'
check misc/installer/README.md 'e\.g\. `v[0-9]+\.[0-9]+\.[0-9]+'

# 1. misc/installer/package.json: update version field via jq (preserve 2-space indent)
jq --indent 2 --arg v "$VERSION" '.version = $v' misc/installer/package.json > tmp.$$.json && mv tmp.$$.json misc/installer/package.json
echo "Updated misc/installer/package.json -> version $VERSION"

# 2. misc/website/docs/getting-started.md: update --version vX.Y.Z
sed -i'' -E 's/(--version v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' misc/website/docs/getting-started.md
echo "Updated misc/website/docs/getting-started.md -> v$VERSION"

# 3. misc/installer/README.md: update e.g. `vX.Y.Z` in the options table
sed -i'' -E 's/(e\.g\. `v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' misc/installer/README.md
echo "Updated misc/installer/README.md -> v$VERSION"

echo ""
echo "Done. All files bumped to v$VERSION"
