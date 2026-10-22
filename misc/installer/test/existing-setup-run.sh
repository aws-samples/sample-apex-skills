#!/usr/bin/env bash
# Run an installer over the existing-setup fixture and check that it changed
# nothing of the user's (step 12 groundwork: "install over an existing setup
# changes nothing of the user's").
#
# The first run with a given --work dir builds the fixture
# (existing-setup-fixture.sh) in <work>/home, with the project at
# <work>/home/work/app, and records <work>/before.snap. Every run then executes
# the installer command with HOME pointed at the fixture, snapshots the home
# again and compares it with before.snap (existing-setup-check.mjs). Re-run
# with the same --work to chain steps (install, then --update, then
# --uninstall): each step is compared with the original fixture.
#
# Usage: misc/installer/test/existing-setup-run.sh --work <dir> [--project] [--step <name>] -- <installer command...>
#   --work     sandbox dir; holds home/, npm-cache/, xdg-config/, the snapshots
#              and each step's output
#   --project  run the command from the fixture project dir, not from HOME
#   --step     a label for this step's files (default: step<n>)
# Example:
#   misc/installer/test/existing-setup-run.sh --work /tmp/es --step install -- npx --yes apex-skills@next -y
#   misc/installer/test/existing-setup-run.sh --work /tmp/es --step update -- npx --yes apex-skills@next --update
#
# The command runs under env -i with only PATH, HOME, USERPROFILE, TERM,
# NO_COLOR, npm_config_cache, XDG_CONFIG_HOME, XDG_CACHE_HOME and hermetic git
# settings, so nothing in the caller's environment (XDG_STATE_HOME, a real npm
# cache or config) is read or written. It is killed after RUN_TIMEOUT seconds
# (default 600: npx and the clone use the network). Its own exit code is
# printed, not judged: the check is the compare.
#
# Exit codes: 0 no user path changed, removed or moved; 1 at least one was;
# 2 bad command line or setup failure.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK=""
PROJECT=0
STEP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --work) WORK="$2"; shift 2 ;;
    --project) PROJECT=1; shift ;;
    --step) STEP="$2"; shift 2 ;;
    --) shift; break ;;
    -h|--help) sed -n '2,/^set -u$/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$WORK" ] || { echo "--work <dir> is required" >&2; exit 2; }
[ $# -gt 0 ] || { echo "no installer command after --" >&2; exit 2; }
mkdir -p "$WORK"
WORK="$(cd "$WORK" && pwd -P)"
H="$WORK/home"
PROJ="$H/work/app"

if [ ! -f "$WORK/before.snap" ]; then
  [ ! -e "$H" ] || { echo "$H exists but $WORK/before.snap does not; use a new --work dir" >&2; exit 2; }
  bash "$SCRIPT_DIR/existing-setup-fixture.sh" "$H" "$PROJ" || { echo "fixture build failed" >&2; exit 2; }
  node "$SCRIPT_DIR/existing-setup-check.mjs" snapshot "$H" "$WORK/before.snap" || exit 2
fi
n=1
while [ -e "$WORK/step$n.out" ] || [ -e "$WORK/step$n.after.snap" ]; do n=$((n + 1)); done
[ -n "$STEP" ] || STEP="step$n"
case "$STEP" in *[!A-Za-z0-9._-]*) echo "--step may hold only letters, digits, . _ -" >&2; exit 2 ;; esac
mkdir -p "$WORK/npm-cache" "$WORK/xdg-config" "$WORK/xdg-cache"
cwd="$H"; [ "$PROJECT" -eq 0 ] || cwd="$PROJ"

echo "== $STEP: (cd $cwd && $*)"
(
  cd "$cwd" || exit 2
  env -i PATH="$PATH" HOME="$H" USERPROFILE="$H" TERM=dumb NO_COLOR=1 \
    npm_config_cache="$WORK/npm-cache" XDG_CONFIG_HOME="$WORK/xdg-config" XDG_CACHE_HOME="$WORK/xdg-cache" \
    GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 \
    perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' "${RUN_TIMEOUT:-600}" "$@" </dev/null
) > "$WORK/$STEP.out" 2>&1
rc=$?
echo "installer exit code: $rc (output: $WORK/$STEP.out)"
node "$SCRIPT_DIR/existing-setup-check.mjs" snapshot "$H" "$WORK/$STEP.after.snap" || exit 2
node "$SCRIPT_DIR/existing-setup-check.mjs" compare "$WORK/before.snap" "$WORK/$STEP.after.snap" > "$WORK/$STEP.compare.txt"
crc=$?
grep -v '^unchanged ' "$WORK/$STEP.compare.txt"
case "$crc" in
  0) echo "PASS $STEP: no user path changed, removed or moved" ;;
  1) echo "FAIL $STEP: a user path changed, was removed or moved (see $WORK/$STEP.compare.txt)"; exit 1 ;;
  *) echo "compare failed" >&2; exit 2 ;;
esac
