#!/usr/bin/env bash
# Mock update-pages.sh for eval fixtures.
# Exits 1 with --check to simulate staleness detected.
# Exits 0 without --check to simulate successful regeneration.

if [[ "$1" == "--check" ]]; then
  echo "STALE: Docusaurus wrappers out of date"
  exit 1
fi

echo "Regenerated Docusaurus wrappers."
exit 0
