#!/usr/bin/env bash
# Mock update-all-references.sh for eval fixtures.
# Exits 1 with --check to simulate staleness detected.
# Exits 0 without --check to simulate successful regeneration.

if [[ "$1" == "--check" ]]; then
  echo "STALE: marker blocks out of date"
  exit 1
fi

echo "Regenerated marker blocks."
exit 0
