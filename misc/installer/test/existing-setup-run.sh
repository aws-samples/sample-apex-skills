#!/usr/bin/env bash
# Run an installer over the existing-setup fixture and check that none of the
# user's existing paths changed, was removed or moved (step 12 groundwork).
# Paths the installer adds are listed, not judged, including ones inside a user
# directory.
#
# The first run with a given --work dir builds the fixture
# (existing-setup-fixture.sh) in <work>/home, with the project at
# <work>/home/work/app, and records <work>/before.snap as the baseline. Every
# run then executes the installer with HOME pointed at the fixture, snapshots
# the home again and compares it with the current baseline
# (existing-setup-check.mjs). Re-run with the same --work to chain steps
# (install, then --update, then --uninstall): each step is compared with the
# original fixture, unless --rebaseline was given on an earlier step.
#
# Usage: misc/installer/test/existing-setup-run.sh --work <dir> (--version <x.y.z> | --cli <file>)
#            [--repo-url <url>] [--offline] [--project] [--rebaseline] [--step <name>] -- [<installer args...>]
#   --work        sandbox dir; holds home/, npm-cache/, xdg-config/, xdg-cache/,
#                 the snapshots and each step's output
#   --version     run npx --yes apex-skills@<x.y.z> (an exact version: the run
#                 fails as invalid unless npx ran that version)
#   --cli         run node <file> instead (a local bin/cli.mjs, for example)
#   --repo-url    passed to the installer as APEX_SKILLS_REPO_URL; a file:// URL
#                 also sets GIT_ALLOW_PROTOCOL=file, as install-paths.sh does
#   --offline     the network fence install-paths.sh uses (every proxy variable
#                 set to http://127.0.0.1:9); only with --cli, since npx must
#                 fetch the package, and only with a file:// --repo-url
#   --project     run the installer from the fixture project dir, not from HOME
#   --rebaseline  before this step, re-read the current baseline's paths (for a
#                 user edit made between steps) and use that as the baseline
#                 for this and later steps; a path the user added between steps
#                 is not in it
#   --step        a label for this step's files (default: step<n>); a label
#                 that was used already in this --work is refused
# Example:
#   misc/installer/test/existing-setup-run.sh --work /tmp/es --version 1.3.0 --step install -- -y
#   misc/installer/test/existing-setup-run.sh --work /tmp/es --version 1.3.0 --step update -- --update
#
# The installer runs under env -i with only PATH, HOME, USERPROFILE, TERM,
# NO_COLOR, npm_config_cache, XDG_CONFIG_HOME, XDG_CACHE_HOME, hermetic git
# settings and the --repo-url and --offline variables, so the caller's
# XDG_STATE_HOME, npm cache and user npm config are not read or written (npm
# still reads its builtin and global config under the node prefix on PATH).
# The fixture's own ~/.gitconfig is part of the user's setup, so
# GIT_CONFIG_GLOBAL is not set to /dev/null. Without --offline, npx and the
# installer's clone use the network.
#
# After RUN_TIMEOUT seconds (a whole number, default 600; any other value is
# refused) the installer's process group gets SIGTERM, then SIGKILL 5 s later;
# a process that leaves the group (setsid) is not reached. The installer's own
# exit code is printed, not judged, except that 126, 127 (it could not run) and
# 142 (timed out) make the step invalid: exit 2, after the compare is printed.
#
# Exit codes: 0 no user path changed, removed or moved; 1 at least one was;
# 2 bad command line, setup failure or an invalid step.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$SCRIPT_DIR/existing-setup-check.mjs"
WORK=""
VERSION=""
CLI=""
REPO_URL=""
OFFLINE=0
PROJECT=0
REBASE=0
STEP=""
need() { [ $# -ge 2 ] && [ -n "$2" ] || { echo "$1 needs a value" >&2; exit 2; }; }
while [ $# -gt 0 ]; do
  case "$1" in
    --work) need "$@"; WORK="$2"; shift 2 ;;
    --version) need "$@"; VERSION="$2"; shift 2 ;;
    --cli) need "$@"; CLI="$2"; shift 2 ;;
    --repo-url) need "$@"; REPO_URL="$2"; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
    --project) PROJECT=1; shift ;;
    --rebaseline) REBASE=1; shift ;;
    --step) need "$@"; STEP="$2"; shift 2 ;;
    --) shift; break ;;
    -h|--help) sed -n '2,/^set -u$/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$WORK" ] || { echo "--work <dir> is required" >&2; exit 2; }
if [ -n "$VERSION" ] && [ -n "$CLI" ]; then echo "give --version or --cli, not both" >&2; exit 2; fi
if [ -n "$VERSION" ]; then
  [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || { echo "--version must be an exact version such as 1.3.0, not a tag: $VERSION" >&2; exit 2; }
  cmd=(npx --yes "apex-skills@$VERSION")
elif [ -n "$CLI" ]; then
  [ -f "$CLI" ] || { echo "--cli $CLI is not a file" >&2; exit 2; }
  CLI="$(cd "$(dirname "$CLI")" && pwd -P)/$(basename "$CLI")"
  cmd=(node "$CLI")
else
  echo "--version <x.y.z> or --cli <file> is required" >&2; exit 2
fi
case "$REPO_URL" in -*) echo "--repo-url must not start with -" >&2; exit 2 ;; esac
if [ "$OFFLINE" -eq 1 ]; then
  [ -n "$CLI" ] || { echo "--offline needs --cli (npx must fetch the package)" >&2; exit 2; }
  case "$REPO_URL" in file://*) ;; *) echo "--offline needs a file:// --repo-url" >&2; exit 2 ;; esac
fi
limit="${RUN_TIMEOUT:-600}"
[[ "$limit" =~ ^[1-9][0-9]*$ ]] || { echo "RUN_TIMEOUT must be a whole number of seconds: $limit" >&2; exit 2; }
mkdir -p "$WORK" || exit 2
WORK="$(cd "$WORK" && pwd -P)" || exit 2
H="$WORK/home"
PROJ="$H/work/app"

if [ ! -f "$WORK/before.snap" ]; then
  [ ! -e "$H" ] || { echo "$H exists but $WORK/before.snap does not; use a new --work dir" >&2; exit 2; }
  bash "$SCRIPT_DIR/existing-setup-fixture.sh" "$H" "$PROJ" || { echo "fixture build failed" >&2; exit 2; }
  node "$CHECK" snapshot "$H" "$WORK/before.snap" || exit 2
  echo "before.snap" > "$WORK/baseline"
fi
[ -f "$WORK/baseline" ] || echo "before.snap" > "$WORK/baseline"
BASE="$WORK/$(cat "$WORK/baseline")"
n=1
while [ -e "$WORK/step$n.out" ] || [ -e "$WORK/step$n.after.snap" ]; do n=$((n + 1)); done
[ -n "$STEP" ] || STEP="step$n"
case "$STEP" in *[!A-Za-z0-9._-]*) echo "--step may hold only letters, digits, . _ -" >&2; exit 2 ;; esac
[ ! -e "$WORK/$STEP.out" ] || { echo "step $STEP already ran in $WORK; use another --step" >&2; exit 2; }
if [ "$REBASE" -eq 1 ]; then
  node "$CHECK" rebase "$BASE" "$H" "$WORK/$STEP.before.snap" || exit 2
  echo "$STEP.before.snap" > "$WORK/baseline"
  BASE="$WORK/$STEP.before.snap"
fi
mkdir -p "$WORK/npm-cache" "$WORK/xdg-config" "$WORK/xdg-cache" || exit 2
cwd="$H"; [ "$PROJECT" -eq 0 ] || cwd="$PROJ"
extra=()
if [ -n "$REPO_URL" ]; then
  extra+=("APEX_SKILLS_REPO_URL=$REPO_URL")
  case "$REPO_URL" in file://*) extra+=(GIT_ALLOW_PROTOCOL=file) ;; esac
fi
if [ "$OFFLINE" -eq 1 ]; then
  fence=http://127.0.0.1:9
  extra+=("HTTPS_PROXY=$fence" "HTTP_PROXY=$fence" "ALL_PROXY=$fence" "https_proxy=$fence" "http_proxy=$fence" "all_proxy=$fence")
fi

echo "== $STEP: (cd $cwd && ${cmd[*]} $*) against baseline $(basename "$BASE")"
# The installer runs in its own process group; on timeout the whole group is
# signalled, so a node child under npx is stopped too. A Ctrl-C or SIGTERM to
# this script is passed on to that group (exit 130).
# shellcheck disable=SC2016 # the perl program is meant to be single-quoted
(
  cd "$cwd" || exit 2
  env -i PATH="$PATH" HOME="$H" USERPROFILE="$H" TERM=dumb NO_COLOR=1 \
    npm_config_cache="$WORK/npm-cache" XDG_CONFIG_HOME="$WORK/xdg-config" XDG_CACHE_HOME="$WORK/xdg-cache" \
    GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 ${extra[@]+"${extra[@]}"} \
    perl -e '
      my $limit = shift @ARGV;
      my $pid = fork;
      die "fork: $!\n" unless defined $pid;
      if ($pid == 0) { setpgrp(0, 0); exec @ARGV or exit 127; }
      setpgrp($pid, $pid);
      local $SIG{INT} = local $SIG{TERM} = sub { kill "TERM", -$pid; waitpid($pid, 0); exit 130; };
      local $SIG{ALRM} = sub { kill "TERM", -$pid; sleep 5; kill "KILL", -$pid; waitpid($pid, 0); exit 142; };
      alarm $limit;
      waitpid($pid, 0);
      exit(($? & 127) ? 128 + ($? & 127) : $? >> 8);
    ' "$limit" "${cmd[@]}" "$@" </dev/null
) > "$WORK/$STEP.out" 2>&1
rc=$?
echo "installer exit code: $rc (output: $WORK/$STEP.out)"
invalid=""
case "$rc" in
  126|127) invalid="the installer could not be run (exit $rc)" ;;
  142) invalid="the installer did not exit within ${limit}s and was stopped" ;;
esac
if [ -n "$VERSION" ] && [ -z "$invalid" ]; then
  ran=""
  for f in "$WORK"/npm-cache/_npx/*/node_modules/apex-skills/package.json; do
    [ -f "$f" ] || continue
    v="$(node -e 'process.stdout.write(String(JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")).version))' "$f" 2>/dev/null)"
    [ "$v" = "$VERSION" ] && ran="$v"
  done
  if [ -n "$ran" ]; then echo "installer version: apex-skills $ran (from the npx cache)"
  else invalid="no apex-skills $VERSION package found in the npx cache"; fi
fi
node "$CHECK" snapshot "$H" "$WORK/$STEP.after.snap" || exit 2
node "$CHECK" compare "$BASE" "$WORK/$STEP.after.snap" > "$WORK/$STEP.compare.txt"
crc=$?
grep -v '^unchanged ' "$WORK/$STEP.compare.txt"
if [ -n "$invalid" ]; then echo "INVALID $STEP: $invalid; the compare above is not a result" >&2; exit 2; fi
case "$crc" in
  0) echo "PASS $STEP: no user path changed, removed or moved" ;;
  1) echo "FAIL $STEP: a user path changed, was removed or moved (see $WORK/$STEP.compare.txt)"; exit 1 ;;
  *) echo "compare failed (exit $crc; the checker's message is above)" >&2; exit 2 ;;
esac
