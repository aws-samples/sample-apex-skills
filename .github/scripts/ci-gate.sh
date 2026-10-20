#!/usr/bin/env bash
# Shared gate logic for CI checks that must report a status on every pull
# request. A workflow that is skipped by an `on.pull_request.paths` filter
# reports no status at all, so a required check with that name stays Pending
# and blocks the merge. Instead, each gated workflow runs on every pull
# request, asks this script whether the change touches its paths, and either
# does its real work or prints a no-op line and succeeds.
#
# Two idioms use it. In a single-job workflow each real-work step carries
# `if: steps.changes.outputs.relevant != 'false'`; a new step needs the same
# `if:` or it also runs on no-op pull requests. A workflow whose real work runs
# in other jobs (installer-test) uses `needs` plus an always() aggregate job
# that calls `verdict` instead.
#
# Usage:
#   ci-gate.sh changed <pattern>...
#     Decides whether the checked-out change touches any pattern. Writes
#     relevant=true or relevant=false to $GITHUB_OUTPUT (when set) and to
#     stdout. Patterns are bash globs: `*` and `**` both match across `/`, so a
#     pattern can match more paths than the GitHub paths filter it replaces,
#     never fewer. It fails safe: any event other than pull_request, or any
#     error while computing the changed files, gives relevant=true.
#
#   ci-gate.sh verdict <relevant> <changes-result> [<job-result>...]
#     Aggregate verdict for a workflow whose real work runs in other jobs.
#     Exits 0 only when the change-detection job succeeded and either
#     relevant is false (no-op) or every job result is success. Any other
#     combination, including an empty or unknown value, exits 1.

set -uo pipefail

emit() {
  local value=$1 reason=$2
  echo "ci-gate: relevant=${value} (${reason})"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "relevant=${value}" >> "$GITHUB_OUTPUT"
  fi
}

cmd_changed() {
  if [ "$#" -eq 0 ]; then
    echo "ci-gate: changed needs at least one pattern" >&2
    exit 2
  fi

  local event=${GITHUB_EVENT_NAME:-}
  if [ "$event" != "pull_request" ]; then
    emit true "event '${event:-unset}' is not pull_request, so the full check runs"
    return 0
  fi

  # On pull_request, actions/checkout checks out the test merge commit, whose
  # first parent is the base branch tip. Its diff against that parent is what
  # the merge would change. Without a merge commit, fall back to the merge
  # base with the pull request's base sha.
  local base
  if git rev-parse -q --verify 'HEAD^2' > /dev/null 2>&1; then
    base=$(git rev-parse 'HEAD^1' 2> /dev/null) || base=""
  else
    base=$(git merge-base "${PR_BASE_SHA:-}" HEAD 2> /dev/null) || base=""
  fi
  if [ -z "$base" ]; then
    emit true "could not find the base commit, so the full check runs"
    return 0
  fi

  local list
  list=$(mktemp)
  # --no-renames lists both sides of a move, so a file moved out of a watched
  # path still counts as a change to that path.
  if ! git diff --no-renames --name-only -z "$base" HEAD > "$list" 2> /dev/null; then
    rm -f "$list"
    emit true "git diff failed, so the full check runs"
    return 0
  fi

  local file pat hit=""
  while IFS= read -r -d '' file; do
    for pat in "$@"; do
      # shellcheck disable=SC2053 # the pattern is a glob on purpose
      if [[ "$file" == $pat ]]; then
        hit="'${file}' matches '${pat}'"
        break 2
      fi
    done
  done < "$list"
  rm -f "$list"
  if [ -n "$hit" ]; then
    emit true "$hit"
  else
    emit false "no changed file matches: $*"
  fi
  return 0
}

cmd_verdict() {
  if [ "$#" -lt 2 ]; then
    echo "ci-gate: verdict needs <relevant> <changes-result> [<job-result>...]" >&2
    exit 2
  fi
  local relevant=$1 changes=$2
  shift 2

  if [ "$changes" != "success" ]; then
    echo "ci-gate: FAIL: change detection result is '${changes:-empty}'"
    exit 1
  fi
  case "$relevant" in
    false)
      echo "ci-gate: no-op: this change touches none of the watched paths; nothing to test"
      exit 0
      ;;
    true)
      local r failed=0
      for r in "$@"; do
        if [ "$r" != "success" ]; then
          echo "ci-gate: FAIL: a required job result is '${r:-empty}'"
          failed=1
        fi
      done
      if [ "$#" -eq 0 ]; then
        echo "ci-gate: FAIL: no job results were given"
        failed=1
      fi
      if [ "$failed" -ne 0 ]; then
        exit 1
      fi
      echo "ci-gate: PASS: every job result is success"
      exit 0
      ;;
    *)
      echo "ci-gate: FAIL: relevant is '${relevant:-empty}', expected true or false"
      exit 1
      ;;
  esac
}

case "${1:-}" in
  changed) shift; cmd_changed "$@" ;;
  verdict) shift; cmd_verdict "$@" ;;
  *)
    echo "usage: ci-gate.sh changed <pattern>... | verdict <relevant> <changes-result> [<job-result>...]" >&2
    exit 2
    ;;
esac
