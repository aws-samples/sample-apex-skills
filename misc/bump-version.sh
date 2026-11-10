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
# The root README.md has no `--version vX.Y.Z` example, so it is not a target.
check() {
  if ! grep -qE -- "$2" "$1"; then
    echo "Error: $1 has no line matching '$2'; nothing was changed" >&2
    exit 1
  fi
}
check misc/installer/package.json '"version": "[^"]*"'
check misc/website/docs/getting-started.md '--version v[0-9]+\.[0-9]+\.[0-9]+'
check misc/website/docs/getting-started.md 'skills release v[0-9]+\.[0-9]+\.[0-9]+'
check misc/installer/README.md 'e\.g\. `v[0-9]+\.[0-9]+\.[0-9]+'

# 1. misc/installer/package.json: update version field via jq (preserve 2-space indent)
jq --indent 2 --arg v "$VERSION" '.version = $v' misc/installer/package.json > tmp.$$.json
mv tmp.$$.json misc/installer/package.json
echo "Updated misc/installer/package.json -> version $VERSION"

# 2. misc/website/docs/getting-started.md: update --version vX.Y.Z
sed -E -i.bak -e 's/(--version v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' -e 's/(skills release v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' misc/website/docs/getting-started.md && rm -f misc/website/docs/getting-started.md.bak
if ! grep -qE -- "--version v${VERSION}" misc/website/docs/getting-started.md; then
  echo "Error: failed to update version in misc/website/docs/getting-started.md" >&2
  exit 1
fi
if ! grep -qE -- "skills release v${VERSION}" misc/website/docs/getting-started.md; then
  echo "Error: failed to update version in misc/website/docs/getting-started.md" >&2
  exit 1
fi
echo "Updated misc/website/docs/getting-started.md -> v$VERSION"

# 3. misc/installer/README.md: update e.g. `vX.Y.Z` in the options table
sed -E -i.bak 's/(e\.g\. `v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' misc/installer/README.md && rm -f misc/installer/README.md.bak
if ! grep -qE "e\.g\. \`v${VERSION}\`" misc/installer/README.md; then
  echo "Error: failed to update version in misc/installer/README.md" >&2
  exit 1
fi
echo "Updated misc/installer/README.md -> v$VERSION"

echo ""
echo "Done. All files bumped to v$VERSION"
