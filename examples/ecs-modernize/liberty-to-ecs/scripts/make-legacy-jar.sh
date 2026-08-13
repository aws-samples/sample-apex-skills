#!/usr/bin/env bash
# =============================================================================
# Generates the unmanaged JAR that app-before's build depends on.
#
#   ./scripts/make-legacy-jar.sh
#
# Why this exists: app-before/pom.xml declares a `system`-scoped dependency on
# app-before/lib/legacy-tax-rules-1.2.jar. A system-scoped dependency resolves
# from a path in the working copy rather than from a repository, which is the
# `build_reproducibility` blocker the assessment reports.
#
# The JAR is generated rather than committed so this repository stays
# source-only, while the assessment still sees a genuine
# repository-unresolvable dependency declaration.
#
# This is the ONLY script in the exercise. Everything else — Maven, Docker,
# Terraform, the AWS CLI — you run yourself, per the README, because seeing the
# commands is the point of the exercise.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="${HERE}/app-before/lib/legacy-tax-rules-1.2.jar"

if [[ -f "$JAR" ]]; then
  echo "already present: ${JAR#"$HERE"/}"
  exit 0
fi

command -v javac >/dev/null 2>&1 || { echo "ERROR: javac not found on PATH" >&2; exit 1; }
command -v jar   >/dev/null 2>&1 || { echo "ERROR: jar not found on PATH" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "${WORK}/src/com/example/tax" "${WORK}/out"
cat >"${WORK}/src/com/example/tax/TaxRules.java" <<'JAVA'
package com.example.tax;

/** Stand-in for a third-party tax-rules library shipped as a bare JAR. */
public final class TaxRules {
    private TaxRules() { }

    public static double rateFor(String region) {
        return "JP".equals(region) ? 0.10 : 0.0;
    }
}
JAVA

# --release 8 keeps the class file loadable by the legacy build's Java 8 target.
javac --release 8 -nowarn -d "${WORK}/out" "${WORK}/src/com/example/tax/TaxRules.java"

mkdir -p "$(dirname "$JAR")"
(cd "${WORK}/out" && jar cf "$JAR" .)

echo "generated: ${JAR#"$HERE"/}"
echo
echo "Note it is NOT packaged into the WAR — a system-scoped dependency never is."
echo "That is why GET /orders/orders reports taxRate \"unavailable\" at runtime."
