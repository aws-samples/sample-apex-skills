#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <version>" >&2
  echo "Example: $0 1.2.0" >&2
  exit 1
fi

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: '$VERSION' does not look like a valid semver (expected X.Y.Z)" >&2
  exit 1
fi

# 1. misc/installer/package.json — update version field via jq (preserve 2-space indent)
jq --indent 2 --arg v "$VERSION" '.version = $v' misc/installer/package.json > tmp.$$.json && mv tmp.$$.json misc/installer/package.json
echo "Updated misc/installer/package.json -> version $VERSION"

# 2. README.md — update --version vX.Y.Z (pattern match, not line number)
sed -i'' -E 's/(--version v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' README.md
if ! grep -qE -- "--version v${VERSION}" README.md; then
  echo "Error: failed to update version in README.md" >&2
  exit 1
fi
echo "Updated README.md -> v$VERSION"

# 3. misc/website/docs/getting-started.md — update --version vX.Y.Z
sed -i'' -E 's/(--version v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' misc/website/docs/getting-started.md
if ! grep -qE -- "--version v${VERSION}" misc/website/docs/getting-started.md; then
  echo "Error: failed to update version in misc/website/docs/getting-started.md" >&2
  exit 1
fi
echo "Updated misc/website/docs/getting-started.md -> v$VERSION"

# 4. misc/installer/README.md line 32 — update e.g. `vX.Y.Z` in options table
sed -i'' -E 's/(e\.g\. `v)[0-9]+\.[0-9]+\.[0-9]+/\1'"$VERSION"'/' misc/installer/README.md
if ! grep -qE "e\.g\. \`v${VERSION}\`" misc/installer/README.md; then
  echo "Error: failed to update version in misc/installer/README.md" >&2
  exit 1
fi
echo "Updated misc/installer/README.md -> v$VERSION"

echo ""
echo "Done. All files bumped to v$VERSION"
