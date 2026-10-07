#!/usr/bin/env bash
# Collect every file the scorers read, once, into $WORK. Fails loud: a transient auth blip, throttle or
# permission error must never become empty data, because a plausible-looking wrong score is worse than a
# refusal. Ends with a validation gate that refuses to hand over an incomplete work dir.
#
# Usage (SKILL.md Step 2's form; a flag beats its env fallback CLUSTER/REGION/KCTX/WORK/AWS_PROFILE):
#   ${CLAUDE_SKILL_DIR}/assets/collect.sh --cluster <name> --region <region> --context <kubectl-context> \
#       [--work <dir, default ./eks-war-$CLUSTER>] [--profile <aws-profile>] \
#       [--kubeconfig <file, default: kubectl's own KUBECONFIG / ~/.kube/config>]  # no other defaults; see PARAMETERS
#
# $WORK may not exist yet, or may be a directory holding anything EXCEPT this review's own output. This
# script never deletes: it refuses rather than collect on top of a previous run. Emptiness is NOT the
# rule -- the skill, notes and unrelated files may sit beside it (any *.json inside $WORK must be valid JSON
# other than null/false: the validation gate checks every *.json in $WORK with `jq -e .`).
# See WORK DIRECTORY below.
#
# If you rely on the environment fallback instead of the flags, set the variables in the SAME command as
# the script: the Bash tool runs each command in a separate process, so an earlier export is already
# gone. SKILL_DIR is not read -- see the note further down on why there is no SKILL_DIR check.
#
# WHY THIS IS A SCRIPT AND NOT A FENCED BLOCK IN references/workflow.md.
# Fenced blocks the agent pastes into a shell have three problems, all real:
#
#  1. The tool-permission allowlist cannot match them. Every call goes through a retry wrapper --
#     `awsjson`, `kjson`, `kctl` -- so the command text a permission rule sees begins with the WRAPPER
#     name, not `aws` or `kubectl`. Bash rules are literal prefix matches ("everything before the first
#     `*` as written") and the built-in wrapper-strip list is fixed (timeout/time/nice/nohup/stdbuf/
#     command/builtin/noglob/xargs) -- shell functions are not on it. So a carefully narrowed allowlist
#     of `Bash(aws eks describe-cluster:*)`-style grants matches almost nothing that actually runs, every
#     collection line prompts, and the only way to stop the prompting is to re-grant `Bash(aws:*)` --
#     re-opening the destructive verbs the narrow list existed to withhold. One script is one grant, and
#     the grant names a file whose contents ship and can be read.
#  2. `bash -n` cannot check them. The blocks carry <PLACEHOLDER> tokens, which bash parses as
#     redirects, so a fenced collection path has no syntax gate at all.
#  3. They are duplicated. Blocks concatenated separately for testing can drift from the prose blocks,
#     and that drift is invisible.
#
# references/workflow.md documents what is collected and why. This file is what runs.
set -uo pipefail
umask 077   # belt-and-suspenders alongside the `chmod 700 "$WORK"` below: every file this script
            # creates (results.jsonl, every *.json, every *.json.tmp) lands owner-only from the
            # moment it exists, not just after the fact. Every write this script makes is under
            # $WORK, so this narrows nothing outside it.

# ── PARAMETERS: ARGUMENTS FIRST, ENVIRONMENT AS FALLBACK ───────────────────────────────────────────
# Arguments exist so the documented workflow needs NO `export` command at all, which is what lets
# SKILL.md leave `Bash(export CLUSTER=*)`/`Bash(export WORK=*)` out of allowed-tools. Such grants match
# on the prefix `export CLUSTER=` and therefore swallow every trailing assignment on the same line --
# `export CLUSTER=x PATH=/tmp/evil:$PATH` matches, and since this script resolves `aws`/`kubectl` through
# PATH, that is arbitrary code execution behind a grant that reads as narrow. An argument cannot set
# an environment variable, so the vector closes at the source rather than being validated after the fact.
# The environment fallback is kept so an existing caller that exports the three variables still works.
usage() {
  echo "usage: collect.sh [--cluster NAME] [--region REGION] [--context KUBECTL_CONTEXT]" >&2
  echo "                  [--work DIR] [--profile AWS_PROFILE] [--kubeconfig FILE]" >&2
  echo "  Each flag falls back to the matching environment variable" >&2
  echo "  (CLUSTER, REGION, KCTX, WORK, AWS_PROFILE) when omitted; --kubeconfig" >&2
  echo "  falls back to kubectl's own KUBECONFIG / ~/.kube/config." >&2
  exit 2
}
KCFG=""; _kcfg_given=0   # --kubeconfig only; its environment form is KUBECONFIG, which kubectl reads itself
while [ $# -gt 0 ]; do
  case "$1" in
    --cluster) [ $# -ge 2 ] || usage; CLUSTER="$2"; shift 2 ;;
    --region)  [ $# -ge 2 ] || usage; REGION="$2";  shift 2 ;;
    --context) [ $# -ge 2 ] || usage; KCTX="$2";    shift 2 ;;
    --work)    [ $# -ge 2 ] || usage; WORK="$2";    shift 2 ;;
    --profile) [ $# -ge 2 ] || usage; AWS_PROFILE="$2"; export AWS_PROFILE; unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_ROLE_ARN AWS_WEB_IDENTITY_TOKEN_FILE; shift 2 ;;
    --kubeconfig) [ $# -ge 2 ] || usage; KCFG="$2"; _kcfg_given=1; shift 2 ;;
    -h|--help) usage ;;
    *) echo "collect.sh: unknown argument '$1'" >&2; usage ;;
  esac
done
export CLUSTER="${CLUSTER-}" REGION="${REGION-}" KCTX="${KCTX-}"
[ -n "${WORK-}" ] && export WORK


# ── REQUIRED TOOLS -- checked before anything else, including argument validation ───────────────────
# The whole pipeline's tools: every external this script invokes, plus `python3` (render-report.py's)
# and one of `sha256sum`/`shasum`/`openssl` for the collection digest. Unchecked, a missing `jq` surfaces as
# silently-failing validation checks inside this run; a missing `python3` surfaces at Step 8, AFTER a full
# collection and all five scorers -- minutes of work lost to a binary whose absence is knowable in the first second.
#
# The base utilities are checked too, and that is not defensive padding: with `grep` off PATH this script
# would print "CLUSTER is not a valid EKS cluster name" for a perfectly valid name, because the validation
# below pipes into grep and a failed pipeline reads as a failed match. A missing tool must never be
# reported as bad input from the operator.
#
# `bash` is not checked: this script is already running, and score.sh invokes its scorer blocks with an
# explicit `bash`, so a system without it fails there with the interpreter's own message.
_missing=""; command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 || command -v openssl >/dev/null 2>&1 || _missing=" sha256sum|shasum|openssl"
for _t in aws kubectl jq python3 grep sed awk tr cut sort wc cat ls head tail date base64 mktemp mkdir chmod cp mv sleep dirname basename pkill; do
  command -v "$_t" >/dev/null 2>&1 || _missing="$_missing $_t"
done
if [ -n "$_missing" ]; then
  echo "collect.sh: required tool(s) not found on PATH:$_missing" >&2
  echo "  This review needs \`aws\` and \`kubectl\` to collect, \`jq\` for every detection and for" >&2
  echo "  reduce.sh, \`python3\` for render-report.py at the final step, the stock utilities (grep sed awk tr cut sort wc" >&2
  echo "  cat ls head tail date base64 mktemp mkdir chmod cp mv sleep dirname basename pkill) throughout, and one of \`sha256sum\`/\`shasum\`/\`openssl\` for the collection digest. Refusing now" >&2
  echo "  rather than after a collection that could not have been fingerprinted, scored or rendered. Nothing has been created." >&2
  exit 1
fi
unset _missing _t

# ── jq CAPABILITY, NOT jq VERSION ──────────────────────────────────────────────────────────────────
# Every detection and reduce.sh's gates assume jq 1.6 builtins. `IN/1` and `IN/2`
# arrived in 1.6 and are already used at FOUR sites in reduce.sh (the pillar-enum and track-enum gates, the
# ratio-exempt list and the state<->ratio gate itself);
# `walk/1` also arrived in 1.6 and is used by the policy-engine privileged reader.
# So 1.6 is this skill's real floor whether or not anything checks it -- this check makes the floor
# visible rather than raising it.
#
# WHY A CAPABILITY PROBE AND NOT A VERSION STRING. Distributions fork and backport: Amazon Linux 2 ships
# `jq-1.5` alongside 1.6, and a string like "jq-1.7.1-apple" or a vendor suffix parses badly. Running the
# builtin answers the only question that matters. `IN(` is the probe because it is the one used by
# reduce.sh, which every review must pass through.
#
# WHAT HAPPENS WITHOUT THIS, measured on a 1.5 library: jq resolves undefined functions lazily, so only the
# one question using the newer builtin aborts -- `SCORER ABORT [adm-2] ... walk/1 is not defined`, the
# security scorer exits rc=1 -- and reduce.sh then refuses on record count. A loud abort, never a silent wrong
# verdict. This turns two confusing failures several steps downstream into one refusal before any file is
# written. Defining the missing builtins inline in a scorer prelude would NOT fix it: reduce.sh's own `IN(`
# would still abort, in a file no prelude reaches.
if ! jq -n 'IN(1)' >/dev/null 2>&1 || ! jq -n '[1]|walk(.)' >/dev/null 2>&1; then
  echo "collect.sh: this jq is missing builtins the scorers require (\`IN\` and \`walk\`, both jq 1.6)." >&2
  echo "  Found: $(jq --version 2>/dev/null || echo unknown)" >&2
  echo "  jq >= 1.6 is required. The capability is tested rather than the version string, because" >&2
  echo "  distributions backport and rename -- Amazon Linux 2, for instance, ships jq-1.5 alongside 1.6." >&2
  echo "  Refusing now rather than aborting one scorer mid-review. Nothing has been created." >&2
  exit 1
fi

: "${CLUSTER:?pass --cluster <EKS cluster name>}"
# No apostrophe in this message: inside ${VAR:?word} an unescaped ' opens a quote context and swallows
# the closing brace, so `cluster's` would turn the whole file into a syntax error. `bash -n` catches it,
# which is a gate a fenced block pasted into a shell does not get.

# ── CLUSTER NAME VALIDATION -- runs BEFORE $WORK is derived or touched ──────────────────────────────
# $WORK defaults to $(pwd)/eks-war-$CLUSTER below, and it is derived before the first AWS call -- so EKS's
# own name validation (which would reject a bad name) never gets a chance to run first. Unvalidated,
# CLUSTER='./../../victim' would make $WORK resolve OUTSIDE any eks-war-* path. This script deletes
# nothing, so the consequence is a collection written to an unintended path rather than a file destroyed
# -- and that is still why this check exists: where the review writes must not be decidable by the
# cluster name. In an agentic context
# CLUSTER can arrive from a prompt or a document, so this is a confused-deputy, not a typo hazard --
# validated here against EKS's own constraint on `aws eks create-cluster --name`: "can contain only
# alphanumeric characters (case-sensitive), hyphens, and underscores... must start with an alphanumeric
# character... can not be longer than 100 characters."
# A NEWLINE IS REJECTED FIRST, BEFORE THE CHARSET CHECK, AND THAT ORDER IS THE POINT. `grep -Eq` matches
# LINE BY LINE, so `^...$` anchors to a line and not to the value: CLUSTER=$'good-name\n../../evil' passes
# a grep-only check with only its first line validated. No injection would follow -- every downstream use
# is a quoted argument -- but the guarantee the comment above claims would not hold, and a check that is
# weaker than it reads is worse than no check. POSIX `case` with a literal newline in the pattern tests
# the WHOLE string, with no subshell and no dependency on grep's line semantics.
case "$CLUSTER" in *"
"*) echo "collect.sh: CLUSTER contains a newline. Refusing before \$WORK is derived or touched." >&2
    exit 1 ;; esac
if ! printf '%s' "$CLUSTER" | grep -Eq '^[0-9A-Za-z][A-Za-z0-9_-]*$'; then
  echo "collect.sh: CLUSTER is not a valid EKS cluster name -- it must start with an alphanumeric" \
    "character and contain only alphanumeric characters, hyphens and underscores (the same rule" \
    "\`aws eks create-cluster --name\` enforces). Refusing before \$WORK is derived or touched." >&2
  exit 1
fi
if [ "${#CLUSTER}" -gt 100 ]; then
  echo "collect.sh: CLUSTER is ${#CLUSTER} characters -- EKS cluster names can not be longer than 100" \
    "characters. Refusing before \$WORK is derived or touched." >&2
  exit 1
fi

: "${REGION:?pass --region <AWS region of the cluster>}"
# REGION is never used to build a path or filename -- every use below is a quoted --region "$REGION"
# argument forwarded through awsjson's "$@" (never re-parsed by a shell), so it cannot cause the path
# traversal an unvalidated CLUSTER could. It is not the confused-deputy vector CLUSTER is, so it does
# not need CLUSTER's rule -- but a loose charset check still catches garbage (newlines, quotes, an
# accidentally-pasted ARN) before it burns three retries per AWS call for a single typo.
# Same line-anchoring hole as CLUSTER's, same fix, same reason -- see the note there.
case "$REGION" in *"
"*) echo "collect.sh: REGION contains a newline. Refusing." >&2; exit 1 ;; esac
if ! printf '%s' "$REGION" | grep -Eq '^[a-z0-9-]{1,20}$'; then
  echo "collect.sh: REGION does not look like an AWS region code (lowercase letters, digits and" \
    "hyphens only, e.g. us-east-1). Refusing." >&2
  exit 1
fi

# KCTX binds the Kubernetes half of this review to the same cluster as the AWS half; the reasoning is
# at the `kctl` helper below. It is validated HERE, with the other required parameters, because
# everything after this point is destructive: see the note there.
export KCTX="${KCTX:?pass --context <the kubectl context for this cluster> (do not take it from kubectl config current-context)}"
# --kubeconfig is optional (without it kubectl reads KUBECONFIG or ~/.kube/config, which it only reads),
# but a value given is checked here, before anything is created, for the same reason as KCTX: a path
# that names no readable file would otherwise surface only after $WORK and the preflight exist.
if [ "$_kcfg_given" -eq 1 ]; then
  case "$KCFG" in *[[:cntrl:]]*)
    echo "collect.sh: --kubeconfig contains a control character. Refusing." >&2; exit 1 ;; esac
  if [ ! -f "$KCFG" ] || [ ! -r "$KCFG" ]; then
    echo "collect.sh: --kubeconfig '$KCFG' is not a readable file. Refusing before anything is created." >&2
    echo "  Create it with: aws eks update-kubeconfig --name $CLUSTER --region $REGION --alias $KCTX --kubeconfig <file>" >&2
    exit 1
  fi
fi
unset _kcfg_given

# ── WORK DIRECTORY -- created fresh, never cleared ──────────────────────────────────────────────────
# THIS SCRIPT DELETES NOTHING. It collects into ONE directory and never clears it; every artefact of the
# review lands there (the collected JSON, results.jsonl, scores.json, report.html -- only the first of
# those is written by this script), and so does every scratch file it writes: the preflight's own
# `.eks-war-preflight.XXXXXX/` directory, kubectl's `.kube-cache/`, each call's `<name>.tmp`/
# `<name>.tmp.err`, the `.ng`/`.ad`/`.av`/`.fp` and `.<name>-add`/`-merged` merge scratch, and
# `.collection.json.tmp`. None of them is removed afterwards, and none can change a result: each is a dot-name or ends in `.tmp`/`.err`, so the
# `"$WORK"/*.json` globs below (the validation gate and the fingerprint) never match one, and reduce.sh
# and render-report.py open only files they name, never a listing of $WORK.
#
# Nor can one block a retry. The guard below refuses only this collector's three markers (.collection.json,
# cluster.json, a non-empty results.jsonl). Everything but the preflight directory, kubectl's `.kube-cache/`
# (which kubectl only ever reads back as its own cache) and the first call's `cluster.json.tmp`/`.tmp.err` is
# written only after cluster.json, so that marker refuses it anyway; each run makes a fresh preflight directory, and truncates those two before reading.
#
# That is a deliberate simplification. Accepting a caller-supplied $WORK and deleting every
# `$WORK/*.json` inside it BEFORE the first AWS call would need a three-arm ownership rule to make the
# delete safe -- and such a rule can still let through a directory holding an UNRELATED results.jsonl,
# clearing the .json files beside it. Having no delete removes the need for the rule: nothing is
# destroyed, so nothing has to be proven safe to destroy.
#
# The one invariant such a delete would provide is kept, by refusal instead of erasure. `awsjson`/`kjson` only
# write on success, so a stale file from an earlier run could otherwise satisfy a call that FAILS this
# time, and the validation gate -- whose whole purpose is to refuse un-collected data -- would pass on
# data that was never collected. So a run starts in a directory holding no output from an earlier run,
# or it does not start. NOT "an empty directory", which the rule further down explicitly
# disclaims: it refuses a PREVIOUS COLLECTION specifically, and deliberately
# tolerates a directory that is non-empty for any other reason.
export WORK="${WORK:-$(pwd)/eks-war-$CLUSTER}"
# ANY CONTROL CHARACTER IN $WORK IS REFUSED: none of the charset checks above covers $WORK, and it needs
# one. It is interpolated into refusal messages built one line per argument, so a control character forges
# text inside a message the operator is expected to read as this script's own words -- including the EKS
# CONNECTOR refusal, whose whole job is to be unambiguous.
#
# THE CLASS, NOT JUST NEWLINE. A test for `\n` only lets `--work $'/tmp/x\rFORGED: nothing
# is wrong, proceed'` walk straight through: CR returns the cursor to column 0, so on a terminal the
# forged text overwrites the line this script wrote. ESC (cursor and colour control) and BS do the same job
# by other means. A path has no legitimate use for any of them.
#
# THIS IS NOT PARITY WITH CLUSTER AND REGION, and it would be wrong to claim it: those two are newline-
# checked AND charset-validated (`^[0-9A-Za-z][A-Za-z0-9_-]*$`, `^[a-z0-9-]{1,20}$`), so no control character can
# reach them at all -- verified, both reject a CR. A filesystem path cannot be restricted to a charset that
# narrow, so this is the widest rule that is still safe for a path: everything `[[:cntrl:]]` matches. The
# derived default cannot contain one (CLUSTER is already validated and `pwd` cannot), so this only ever
# fires on a hand-passed `--work`.
case "$WORK" in *[[:cntrl:]]*)
    echo "collect.sh: WORK contains a control character (newline, carriage return, escape or similar)." >&2
    echo "  Refusing before it is created or written to: such a path forges lines inside this script's own" >&2
    echo "  messages. Pass a --work path made of printable characters." >&2
    exit 1 ;; esac
if [ -e "$WORK" ] && [ ! -d "$WORK" ]; then
  echo "collect.sh: refusing WORK='$WORK' -- it exists and is not a directory." >&2
  exit 1
fi
# Two refusals for paths nobody means to pass: the filesystem root, and the operator's home directory.
# The rule below does NOT cover either, and letting one through costs more than a chmod to 700.
# That rule is not an emptiness rule (read the next paragraph: it refuses a PREVIOUS COLLECTION, and
# deliberately NOT a non-empty directory), and `/` and `$HOME` always exist, so
# `_work_precreated` is 1
# and the `chmod 700` further down is skipped for exactly these two paths. The real consequence is the
# one worth naming: this script writes ~50 collected JSON files into $WORK -- and the rest of the
# pipeline later adds results.jsonl, scores.json and report.html beside them, none of which are written
# here -- so a single defeated compare puts that debris in `/` or in $HOME.
#
# COMPARED CANONICALLY, NOT AS STRINGS. A literal compare `[ "$WORK" = "${HOME:-}" ]` lets every
# other spelling of the same directory walk straight through it -- each checkable against a fake $HOME:
# `--work "$HOME/"`, `"$HOME/."`, `"$HOME//"`, `"$HOME/./."`, `"$HOME/../<user>"`, `"$HOME/x/.."`, a
# symlink pointing at $HOME, and a bare `--work .` run from $HOME would all reach `mkdir -p` and write
# cluster.json into the home directory this check exists to protect. `//`, `/.` and `/..` do the same
# for the filesystem root.
#
# $WORK NORMALLY DOES NOT EXIST YET -- that is the ordinary case, not an edge -- so a canonicaliser that
# requires existence is the wrong tool here. macOS is a first-class target and ships no GNU coreutils:
# its /bin/realpath is the BSD one, where `-m` is "illegal option -- m" and plain `realpath` errors
# outright on a path that does not exist, and `readlink -f` prints nothing for one. So `_canon` resolves
# the deepest ANCESTOR that IS A DIRECTORY using `cd -P` + `pwd -P` -- POSIX shell builtins, present in
# every shell this script can run under, and they follow symlinks -- then folds `.`, `..` and empty
# components out of the remaining tail.
#
# WHAT THE TAIL FOLD DOES AND DOES NOT GUARANTEE. Two plausible claims about it are FALSE, and the code
# has neither property: "none of the tail exists, so none of it can be a symlink" (wrong: the
# strip loop tests `! -d`, not `! -e`, so an existing file, a symlink to a file, or a dangling symlink
# lands in the tail), and "the residual error can only over-refuse, never under-refuse" (also wrong, see
# below). So this states the limit rather than asserting it away.
#
# What the loop DOES guarantee is narrow: no component of the tail is a directory *as far as this process
# can tell*. A symlink to a directory normally satisfies `-d` and so never reaches the tail -- it is
# resolved physically by `cd -P`, which is both the case that matters and the case that works.
#
# THE FOLD CAN ERR IN THE ACCEPTING DIRECTION. Executed counterexample: a symlink whose target directory
# this process cannot stat FAILS `[ -d ]`, so it lands in the tail and is folded lexically, and
# `<that symlink>/../..` is ACCEPTED while the kernel would resolve it somewhere else entirely -- possibly
# $HOME. What makes this a wart rather than a hole is a SEPARATE fact, and it is the one being relied on:
# the same permission bit that hid the target from `-d` also denies the write, so `mkdir -p` fails
# (measured: EACCES) and no collection is created there. The other foldable-but-invalid tails behave the
# same way -- ENOTDIR for `<file>/..` and `<symlink-to-file>/..`, ENOENT for a dangling symlink. So the
# guard is sound because these paths are unwritable, NOT because the fold is exact. Anything that makes
# one of them writable invalidates this reasoning and it has to be redone.
# $HOME is put through the SAME function, because both sides have to be normalised the same way: on
# macOS /tmp is a symlink to /private/tmp, so a $HOME underneath it resolves to /private/... and
# comparing a canonical $WORK against a raw $HOME would miss.
#
# THE ORDER IS LOAD-BEARING: $WORK is derived on the line above (it cannot be validated
# before it exists as a value), and every refusal here runs before the `mkdir -p "$WORK"` and
# `chmod 700` far below. Nothing is created by this block.
_canon() {
  _cp="$1"; _ct=""
  case "$_cp" in /*) ;; *) _cp="$(pwd)/$_cp" ;; esac
  while [ ! -d "$_cp" ] && [ "$_cp" != "/" ]; do
    _ct="/${_cp##*/}$_ct"; _cp="${_cp%/*}"; [ -n "$_cp" ] || _cp="/"
  done
  _cp="$(cd -P -- "$_cp" 2>/dev/null && pwd -P)" || return 1
  # POSIX leaves a pathname beginning with exactly two slashes implementation-defined, and `cd -P //`
  # reports `//` on macOS -- the root under another name, which must not survive the compare below.
  while :; do case "$_cp" in //*) _cp="${_cp#/}" ;; *) break ;; esac; done
  # One component at a time, parameter expansion only: no `IFS` word split (which would also glob a
  # tail containing a `*`) and no subshell. `..` pops the last component of a path that is already
  # physical, so popping it lexically is exact here too.
  while [ -n "$_ct" ]; do
    _ct="${_ct#/}"; _cc="${_ct%%/*}"
    case "$_ct" in *"/"*) _ct="/${_ct#*/}" ;; *) _ct="" ;; esac
    case "$_cc" in ""|".") ;; "..") _cp="${_cp%/*}" ;; *) _cp="$_cp/$_cc" ;; esac
  done
  printf '%s\n' "${_cp:-/}"
}
if ! _work_canon="$(_canon "$WORK")"; then
  echo "collect.sh: refusing WORK='$WORK' -- it can not be resolved: the deepest existing directory" \
    "above it is not traversable, so this script can not tell whether it is the filesystem root or your" \
    "home directory, and could not create or write \$WORK there either." >&2
  exit 1
fi
_home_canon=""
if [ -n "${HOME:-}" ]; then
  _home_canon="$(_canon "$HOME")" || _home_canon="$HOME"
fi
if [ "$_work_canon" = "/" ] || { [ -n "$_home_canon" ] && [ "$_work_canon" = "$_home_canon" ]; }; then
  echo "collect.sh: refusing WORK='$WORK' (resolves to '$_work_canon') -- it is the filesystem root or" \
    "your home directory. Pass --work with a subdirectory of it instead." >&2
  exit 1
fi
unset _work_canon _home_canon _cp _ct _cc
# Refused only for a PREVIOUS COLLECTION, not for a non-empty directory. $WORK may legitimately sit
# beside other files -- the skill itself, notes, whatever the operator keeps there -- and refusing on
# emptiness would block that. What cannot be tolerated is an earlier run's output: `awsjson`/`kjson` only
# write on success, so a stale collected file could satisfy a call that FAILS this time, and the
# validation gate -- whose whole purpose is to refuse un-collected data -- would pass on data that was
# never collected. `.collection.json` and `results.jsonl` are written only by this skill, so their
# presence is the unambiguous marker of a previous run.
# `cluster.json` is the marker for collected data, and it is the right one because it is the FIRST file
# any run writes (the identity binding below is the first collecting step) -- so if it is absent, this
# directory holds nothing from an earlier run that could shadow a failed call this time. `.collection.json`
# is written only at the END, so it distinguishes a finished collection from an abandoned one, which is
# the difference the message needs to state. `results.jsonl` is tested with `-s`, not `-f`: it is scored
# output, and an empty one is not scored output.
_prev=""
[ -f "$WORK/.collection.json" ] && _prev="a COMPLETED collection (.collection.json)"
[ -z "$_prev" ] && [ -f "$WORK/cluster.json" ] && _prev="an UNFINISHED collection (cluster.json, but no .collection.json)"
[ -z "$_prev" ] && [ -s "$WORK/results.jsonl" ] && _prev="scored output from an earlier run (results.jsonl)"
if [ -n "$_prev" ]; then
  echo "collect.sh: refusing WORK='$WORK' -- it already holds $_prev." >&2
  echo "  This script never deletes, and it will not collect on top of an earlier run: \`awsjson\`/" >&2
  echo "  \`kjson\` write only on success, so a stale file from that run can silently satisfy a call" >&2
  echo "  that FAILS this time, and the validation gate -- whose whole purpose is to refuse" >&2
  echo "  un-collected data -- would then pass on data that was never collected." >&2
  echo "  Pass --work with a new path whose name starts with eks-war- (or move or rename that directory yourself), then re-run. Other files are" >&2
  echo "  fine to keep there (any *.json inside it must be valid JSON other than null/false): only" >&2
  echo "  this collector's own output is refused, not a non-empty directory." >&2
  exit 1
fi
unset _prev
# ── PERMISSION PREFLIGHT -- runs BEFORE anything is collected, in a scratch dir inside $WORK ─────────
# Do not assume the operator holds cluster-admin or an unrestricted AWS role. Without this, a role
# missing one action discovers it partway through collection: every required call retries 3x with
# backoff, so an under-permissioned run would burn minutes before the validation gate refused. This
# script deletes nothing, so such a run destroys no previous collection; the wasted minutes are the
# cost, and a refusal in the first seconds is cheaper -- which is why both halves, AWS and Kubernetes,
# are probed here, before anything is collected.
#
# HOW EACH HALF IS PROBED, and why not `iam:SimulatePrincipalPolicy`: it needs a permission a restricted
# role is unlikely to hold, it omits resource control policies (RCPs), and it SIMULATES rather than
# performs -- AWS advises checking policies against the live environment afterwards regardless. Note it
# DOES evaluate SCPs including their condition keys, so "it ignores SCPs" would be wrong. This probes
# EFFECTIVE permission instead, which is what the collection will actually hit.
#   * EC2: `--dry-run`, which returns DryRunOperation (authorized) or UnauthorizedOperation (denied)
#     without performing the operation -- exact verdict, zero work, no data returned.
#   * eks/iam/ecr/cloudtrail/sts: no --dry-run, so one cheap real call each, page-capped where possible.
#   * Kubernetes: `kubectl auth can-i`, a SelfSubjectAccessReview -- always permitted and authoritative.
#     `auth can-i --list` is deliberately NOT used: its wildcard/apiGroup rows cannot be parsed into a
#     per-resource verdict. This half is what actually surprises people, because the built-in `view`
#     ClusterRole does NOT cover clusterroles, clusterrolebindings, either webhook configuration kind,
#     persistentvolumes or storageclasses -- all of which are collected.
#
# EVERY PROBE RUNS IN PARALLEL, under one hard ceiling for the whole preflight (PF_TIMEOUT). Serially it
# would cost enough that an operator would look for a way to skip it; a preflight people disable protects
# nobody. No figure is quoted here on purpose -- it depends on the account, the region and the endpoint.
#
# REFUSES ON A PROVEN DENIAL, on expired credentials, and on a half or a whole that settled NOWHERE.
# A single inconclusive probe (throttle, network, an error that is not an authorization failure) is
# reported and allowed through, so a transient fault cannot block a run that would otherwise succeed --
# collection's own fail-loud gate still catches it downstream. But "nothing settled" is not a transient
# fault, and neither is "one entire half settled nowhere": see the two arms below the watchdog.
if [ -d "$WORK" ]; then _work_precreated=1; else _work_precreated=0; fi
mkdir -p "$WORK"
[ "$_work_precreated" -eq 1 ] || chmod 700 "$WORK"   # why conditional: see the note after the preflight
unset _work_precreated
PF_DIR="$(mktemp -d "$WORK/.eks-war-preflight.XXXXXX")" || PF_DIR=""
# $WORK IS CREATED FIRST AND THE PREFLIGHT'S SCRATCH GOES INSIDE IT: this script writes nothing outside $WORK. It
# is a fresh `.eks-war-preflight.XXXXXX/` that
# nothing deletes, and it cannot block a retry or reach a result -- see WORK DIRECTORY above. CHECKED, and
# fatal: an unchecked `mktemp -d` would leave $PF_DIR EMPTY, so up to 50 verdict writes and `mkdir /response` go at the
# FILESYSTEM ROOT, which as root in a container all SUCCEED. No private directory, no preflight: refuse.
if [ -z "$PF_DIR" ] || [ ! -d "$PF_DIR" ]; then
  echo "collect.sh: could not create the preflight's private directory inside WORK='$WORK', so the" >&2
  echo "  permission preflight cannot run. Is WORK (or the directory above it) full, read-only or not" >&2
  echo "  writable by you? Fix that, or pass another --work, and re-run. Nothing has been collected or deleted." >&2
  exit 1
fi
trap 'pkill -P $$ 2>/dev/null' EXIT INT TERM
PF_TIMEOUT="${PF_TIMEOUT:-45}"   # hard ceiling for the WHOLE preflight, overridable for testing
PF_EXPECTED=""
PF_PIDS=""
PF_SKIPPED=""
# CLEARED, never inherited -- both of them, for two different reasons. `_pf_aws` reads BOTH from the
# environment (`${PF_CAPTURE:-/dev/null}` and `${PF_PREFIX:-a-}`), so an exported value reaches every probe
# that goes through it: 9 `pf` + 3 `pfg` + 1 `pfc` + up to 2 conditional per-object probes, so 15 at most
# and 13 on a cluster with no add-ons or Fargate profiles. `_pf_ec2` (8 probes) and `_pf_k8s`
# (27) read neither and are immune -- this is NOT about all 50 (15 + 8 + 27).
#   * $PF_CAPTURE: an exported one makes each of those probes write its response body to a path the CALLER
#     chose, overwriting one another. `umask 077` still lands that file 0600, so this is not an exposure --
#     it is a write outside $WORK, the one directory this script writes into and sets the mode of, made
#     before the refusals that promise nothing was collected. `pfc` sets it per-call, which is the only
#     supported way to keep a body.
#   * $PF_PREFIX: an exported one would MOVE EVERY VERDICT FILE that relies on the default into another
#     namespace, and the EKS CONNECTOR check below reads one verdict BY NAME. Were `pfc` unpinned, with
#     `PF_PREFIX=g-` exported against a connector cluster the verdict would land in
#     `g-eks-DescribeCluster`, the watchdog fill the `a-` name with UNKNOWN, THE PREFLIGHT REFUSAL NOT
#     FIRE, $WORK be created and `cluster.json` written, and only the backstop catch it -- the two defects
#     that check exists to prevent. All three wrappers (`pf`, `pfg`, `pfc`) state their own namespace at
#     the call site, so this clearing is belt-and-braces rather than the only thing holding it.
# PF_TIMEOUT above is deliberately the other way round, and it exists to be overridden for testing. Note
# what it is NOT: it is the watchdog's DEADLINE (`_pf_end=now+PF_TIMEOUT`), so RAISING IT IS MORE PERMISSIVE,
# not less -- measured, a probe that hangs 6s is UNKNOWN at 3 and settles at 20, and a large enough value
# removes the hard bound the watchdog exists to provide. What it cannot do is the thing that matters here:
# it cannot suppress a denial, an expired credential or the scope refusal, and it can neither redirect a
# write nor rename a file. Those are the properties that decide which of these three is safe to inherit.
PF_CAPTURE=
PF_PREFIX=

# Every probe records a verdict FILE unconditionally -- OK, DENIED or UNKNOWN. A probe that records
# nothing was therefore killed by the watchdog below, and is reported as UNKNOWN rather than silently
# counting as a pass. Measured: one `kubectl auth can-i` against an unroutable endpoint (real CA + exec
# auth, so kubectl actually dials) takes 92s, and `kubectl --request-timeout=8s` still took 24s -- the
# CLI flags do not give a hard bound, so the ceiling has to be enforced here.
_pf_rec() { printf '%s %s\n' "$1" "$2" > "$PF_DIR/$3"; }
# aws stderr opens with a BLANK line, so `head -1` returns an empty reason and every probe reads as
# unexplained. The script has a `firstline` helper for exactly this, but it is defined below the
# preflight, so the same rule is inlined here: first NON-EMPTY line.
_pf_first() { awk 'NF{print;exit}'; }
_pf_expect() { PF_EXPECTED="$PF_EXPECTED
$1|$2"; }

# Authorization failures that do NOT use the IAM error shape. Without these an EXPIRED SSO/session token
# -- the commonest real failure -- is classified UNKNOWN and passes straight through, defeating the
# preflight entirely. SCP and permissions-boundary denials render as `...(AccessDenied)...` so
# they are caught anyway; these are the credential-shaped ones that are not.
# Denial is tested FIRST, before `_pf_is_ok_err`: both are bare substring matches, so in the other order a
# message carrying an authorization failure AND a not-found token would be classified OK -- a denial recorded
# as a pass, the one direction this preflight must never get wrong.
#
# `ClientException` is here because AWS documents it, for the per-object EKS Describe* calls, as covering
# "using an action or resource on behalf of an IAM principal that doesn't have permissions ... or
# specifying an identifier that is not valid" -- and `AccessDeniedException` is NOT in those operations'
# documented error list at all. Those probes pass an identifier taken from the matching List call, so
# the "invalid identifier" half is ruled out by construction and a ClientException can only be the
# permissions half. That is the whole reason the probes never use a made-up name.
_pf_is_denied() {
  case "$1" in
    *UnauthorizedOperation*|*AccessDenied*|*not\ authorized*|*explicit\ deny*) return 0 ;;
    *ClientException*) return 0 ;;
    *) return 1 ;;
  esac
}
# Credential failures are their own verdict: they are not a permissions problem and the remedy is
# different. Every string below was captured live from this CLI, including the credential-process
# traceback; left unmatched, each would fall to UNKNOWN and be passed through, for
# what is the commonest misconfiguration there is.
_pf_is_credfail() {
  case "$1" in
    *ExpiredToken*|*ExpiredTokenException*|*InvalidClientTokenId*|*AuthFailure*|*security\ token*) return 0 ;;
    *SSO\ Token*|*sso\ session*|*Token\ has\ expired*) return 0 ;;
    *NoCredentials*|*Unable\ to\ locate\ credentials*|*retrieving\ credentials*) return 0 ;;
    *) return 1 ;;
  esac
}
# Retained only as a backstop. With real identifiers these should not occur; if one does, the call was
# authorised far enough to look the object up, so it is not a denial.
_pf_is_ok_err() {
  case "$1" in
    *ResourceNotFoundException*|*InvalidParameterException*) return 0 ;;
    *) return 1 ;;
  esac
}
_pf_ec2() {
  _act="ec2:$(printf '%s' "$1" | awk -F- '{for(i=1;i<=NF;i++) printf toupper(substr($i,1,1)) substr($i,2)}')"
  _e="$(aws ec2 "$1" --dry-run --region "$REGION" 2>&1)"
  case "$_e" in *DryRunOperation*) _pf_rec OK "$_act" "p-$1"; return ;; esac
  if _pf_is_denied "$_e"; then _pf_rec DENIED "$_act" "p-$1"
  elif _pf_is_credfail "$_e"; then _pf_rec EXPIRED "$_act" "p-$1"
  elif _pf_is_ok_err "$_e"; then _pf_rec OK "$_act" "p-$1"
  else _pf_rec UNKNOWN "$_act -- $(printf '%s' "$_e" | _pf_first | cut -c1-70)" "p-$1"; fi
}
# $PF_PREFIX selects the verdict-file namespace: `a-` for a probe that talks to $REGION, `g-` for one
# that does not. The AWS-half refusal is judged on the REGIONAL probes alone, and it could not fire at
# all if the two were mixed: three probes never touch $REGION -- sts:GetCallerIdentity and
# iam:ListOpenIDConnectProviders are global endpoints, and pricing:GetProducts is pinned to us-east-1 --
# so with every regional endpoint dead but credentials valid, `_a_ok + _p_ok` would still be >= 3 and the run
# would proceed into ~20 regional calls, each retried 3x, to discover one at a time what the preflight
# already knows. The global probes are reported and counted in PF_OKN/PF_TOTAL; they just
# cannot vouch for a region.
#
# $PF_CAPTURE keeps the RESPONSE BODY as well as the verdict. Every probe but one wants only the verdict,
# which is why stdout goes to /dev/null by default -- the probes exist to answer "is this permitted", and
# a response nobody reads is a response nobody has to reason about. The exception is eks:DescribeCluster,
# whose response is the single call that can prove a cluster is out of scope entirely: see EKS CONNECTOR
# CLUSTERS below. Capturing it here costs nothing -- the call is already being made, and discarding a
# response the script then has to make a second call to obtain is the waste this avoids.
_pf_aws() {
  _lbl="$1"; _slug="$(printf '%s' "$1" | tr ':' '-')"; _px="${PF_PREFIX:-a-}"; _cap="${PF_CAPTURE:-/dev/null}"; shift
  if _e="$("$@" 2>&1 >"$_cap")"; then _pf_rec OK "$_lbl" "$_px$_slug"; return; fi
  if _pf_is_denied "$_e"; then _pf_rec DENIED "$_lbl" "$_px$_slug"
  elif _pf_is_credfail "$_e"; then _pf_rec EXPIRED "$_lbl" "$_px$_slug"
  elif _pf_is_ok_err "$_e"; then _pf_rec OK "$_lbl" "$_px$_slug"
  else _pf_rec UNKNOWN "$_lbl -- $(printf '%s' "$_e" | _pf_first | cut -c1-70)" "$_px$_slug"; fi
}
# _pf_k8s <slug> <verb> <resource> [extra kubectl args...]
# THE VERB AND THE SCOPE MUST BOTH MATCH WHAT THE COLLECTOR ACTUALLY DOES.
#
# VERB: `list` and `get` are separate verbs in Kubernetes RBAC (`kubectl auth can-i` accepts each
# independently), and `configmaps` is collected ONLY as single-object gets -- `kjson_optional ...
# configmap aws-auth -n kube-system` and two others, never as a list. Probing `list configmaps` would
# therefore demand a verb no collection call needs, so a role scoped to exactly what this review reads
# would be REFUSED for a permission it correctly lacks.
#
# SCOPE: `kubectl auth can-i list pods` with no `-n`/`-A` is
# evaluated against the CONTEXT'S DEFAULT NAMESPACE, while the collector runs `get pods -A`. A role
# holding a RoleBinding in `default` but no ClusterRole would pass such a probe and then be denied the
# real call; a role holding a cluster-wide ClusterRole but nothing in `default` would be refused for a
# permission it has. So every namespaced probe carries `--all-namespaces`, and the three named ConfigMaps
# are probed in the namespaces they actually live in (`kube-system`, `aws-observability`). Cluster-
# scoped resources take no namespace and must not be given one. "The preflight probes what the
# collection calls" is the property that makes a pass mean anything, for verb and scope alike.
#
# The slug is explicit rather than derived from the resource, because `configmap/aws-auth` and
# `configmap/amazon-vpc-cni` are two probes that would otherwise collide on one verdict file.
_pf_k8s() {
  _sl="$1"; _vb="$2"; _rs="$3"; shift 3
  _v="$(kubectl auth can-i "$_vb" "$_rs" "$@" --context "$KCTX" ${KCFG:+--kubeconfig "$KCFG"} --cache-dir "$WORK/.kube-cache" 2>&1 | tail -1)"
  _lb="kubernetes: $_vb $_rs${*:+ $*}"
  case "$_v" in
    yes) _pf_rec OK "$_lb" "k-$_sl" ;;
    no) _pf_rec DENIED "$_lb" "k-$_sl" ;;
    *)   _pf_rec UNKNOWN "$_lb -- $(printf '%s' "$_v" | cut -c1-60)" "k-$_sl" ;;
  esac
}

for _op in describe-instances describe-volumes describe-security-groups describe-subnets \
           describe-nat-gateways describe-route-tables describe-vpc-endpoints \
           describe-instance-type-offerings; do
  _pf_expect "ec2:$(printf '%s' "$_op" | awk -F- '{for(i=1;i<=NF;i++) printf toupper(substr($i,1,1)) substr($i,2)}')" "p-$_op"
  _pf_ec2 "$_op" & PF_PIDS="$PF_PIDS $!"
done
# Per-object Describe* and pricing are probed too: a role holding List* but not the matching Describe*
# would otherwise pass preflight and then fail mid-collection. simulate-custom-policy confirms that such
# a role is denied all five while the List* calls succeed, so the gap is reachable.
# Each of the three wrappers below STATES ITS OWN NAMESPACE on both halves: the name it registers with
# `_pf_expect` and the name `_pf_aws` will write. A wrapper that hardcoded `a-` on the register side and left
# the write side to `_pf_aws`'s `${PF_PREFIX:-a-}` default would be one wrapper, two halves, disagreeing about
# where the filename comes from. That is the exact shape that disarms the connector check: an
# exported PF_PREFIX moves the file that is written while the registered name stays put, so the watchdog
# fills the registered name with UNKNOWN and every reader sees the placeholder. It is unreachable
# because PF_PREFIX is cleared above, but "unreachable because of a line in another block" is not a property
# worth relying on -- all three pin it, and the clearing is the belt.
pf() { _pf_expect "$1" "a-$(printf '%s' "$1" | tr ':' '-')"; PF_PREFIX=a- _pf_aws "$@" & PF_PIDS="$PF_PIDS $!"; }
# pfg: an AWS probe that does NOT talk to $REGION. Same reporting, different verdict-file prefix, so a
# region that is entirely unreachable cannot be vouched for by a global endpoint. See _pf_aws above.
pfg() { _pf_expect "$1" "g-$(printf '%s' "$1" | tr ':' '-')"; PF_PREFIX=g- _pf_aws "$@" & PF_PIDS="$PF_PIDS $!"; }
# pfc <file> <label> <cmd...>: a regional probe that KEEPS its response body in <file> -- or keeps nothing,
# if <file> is empty. Exactly one probe uses it; see $PF_CLUSTER_JSON and EKS CONNECTOR CLUSTERS below. The
# body goes in a SUBDIRECTORY of $PF_DIR so that the verdict aggregation's `cat "$PF_DIR"/*` cannot read a
# response as a verdict. It is not removed afterwards: it stays in this run's own preflight directory,
# which nothing opens once the connector check below has read it (see WORK DIRECTORY above).
#
# It sets $PF_PREFIX EXPLICITLY, as `pf` and `pfg` also do, because the connector check below finds this
# probe's verdict by the filename that prefix produces. Pinning it here is what stops an exported PF_PREFIX
# from moving that one file and silently disarming the check; the clearing further up is the belt.
#
# CREATION AND WRITABILITY ARE BOTH CHECKED, and a failure is NOT fatal. Each check covers a case the
# other misses:
#   * Unchecked, a `mkdir` failure falls through to the redirect in `_pf_aws`: the probe records UNKNOWN
#     and bash's own "line NNN: ...: No such file or directory" goes into the operator's did-not-settle
#     list, truncated at 70 characters so it names no cause at all.
#   * Checking only the `mkdir` is not enough either. `mkdir -p` RETURNS 0 FOR A DIRECTORY THAT ALREADY
#     EXISTS, whatever its mode -- try one at 0500 -- so the `else` never runs, the redirect
#     fails on its own, and that same truncated artefact comes back. A FULL filesystem, one of the two
#     causes the note below names, may fail at the write rather than at the `mkdir`. So the writability test is the
#     one that actually covers the documented causes; `: >` creates the file the probe will truncate anyway.
#   * The writability test's own redirections are ORDERED `2>/dev/null` FIRST. Written the natural way
#     round, `: > "$f" 2>/dev/null`, bash performs `> "$f"` BEFORE stderr is redirected, so a failing open
#     prints the very "line NNN: ...: Permission denied" this check exists to replace -- measured, and it
#     is the same left-to-right rule as `2>&1 >"$_cap"` in `_pf_aws`.
# Being unable to KEEP a response is no reason to fail a PERMISSION probe -- the probe still answers the
# question it was asked. What is lost is the connector check running this early, so that is what the note
# says, and the BACKSTOP after `describe-cluster` is collected still refuses a connector cluster.
if mkdir -p "$PF_DIR/response" 2>/dev/null && : 2>/dev/null > "$PF_DIR/response/describe-cluster.json"; then
  PF_CLUSTER_JSON="$PF_DIR/response/describe-cluster.json"
else
  PF_CLUSTER_JSON=""      # empty -> pfc keeps no body -> the connector check below cannot run
  echo "NOTE: the preflight could not create, or could not write into, the directory it keeps one" >&2
  echo "  response in, so the EKS Connector check cannot run this early:" >&2
  echo "    $PF_DIR/response" >&2
  echo "  Is the work directory full or read-only? Every permission probe still runs and none of their" >&2
  echo "  verdicts are affected. A connector cluster is refused after describe-cluster is collected" >&2
  echo "  instead, which leaves a cluster.json in the work directory; that refusal says so and says" >&2
  echo "  what to do about it." >&2
fi
pfc() { _pfc_f="$1"; shift; _pf_expect "$1" "a-$(printf '%s' "$1" | tr ':' '-')"; PF_PREFIX=a- PF_CAPTURE="$_pfc_f" _pf_aws "$@" & PF_PIDS="$PF_PIDS $!"; }
pfg "sts:GetCallerIdentity"             aws sts get-caller-identity
pf "eks:ListClusters"                  aws eks list-clusters --region "$REGION"
pfc "$PF_CLUSTER_JSON" \
    "eks:DescribeCluster"              aws eks describe-cluster --name "$CLUSTER" --region "$REGION"
pf "eks:ListNodegroups"                aws eks list-nodegroups --cluster-name "$CLUSTER" --region "$REGION"
pf "eks:ListAddons"                    aws eks list-addons --cluster-name "$CLUSTER" --region "$REGION"
pf "eks:ListFargateProfiles"           aws eks list-fargate-profiles --cluster-name "$CLUSTER" --region "$REGION"
pf "eks:ListPodIdentityAssociations"   aws eks list-pod-identity-associations --cluster-name "$CLUSTER" --region "$REGION"
pf "eks:ListInsights"                  aws eks list-insights --cluster-name "$CLUSTER" --region "$REGION"
pf "eks:DescribeAddonVersions"         aws eks describe-addon-versions --max-results 1 --region "$REGION"
pfg "iam:ListOpenIDConnectProviders"    aws iam list-open-id-connect-providers
pf "ecr:DescribeRepositories"          aws ecr describe-repositories --max-items 1 --region "$REGION"
pf "cloudtrail:DescribeTrails"         aws cloudtrail describe-trails --region "$REGION"
pfg "pricing:GetProducts"               aws pricing get-products --service-code AmazonEC2 --max-items 1 --region us-east-1
# These two need an object id. They are probed with a REAL id taken from the matching List call, and
# SKIPPED when that list is empty -- because collection only calls them per listed name, so there is
# nothing to authorise when the list is empty.
#
# They are NOT probed with a name engineered never to exist, treating ResourceNotFoundException as
# proof of the permission. AWS documents `ClientException` for these operations as covering BOTH "an IAM
# principal that doesn't have permissions" AND "specifying an identifier that is not valid" -- so a
# made-up name makes a denial and the probe's own bogus input indistinguishable, and the probe cannot
# answer the question it was asked. A real id removes the ambiguity: success proves the permission, and
# any ClientException can only be the permissions half.
# _pf_first_of <jmespath> <aws args...>
#   rc 0 -> prints the id it found
#   rc 1 -> the call SUCCEEDED and the list is genuinely empty
#   rc 2 -> the call FAILED; prints the first line of its error instead of an id
#
# Stderr and the exit status are both kept: discarding them reads "the List call failed" as
# "the cluster has none". A throttle, a denial or an endpoint timeout produces empty stdout, the caller
# would report "cluster has no addons, so collection never calls it", and the matching Describe* probe
# would be SKIPPED -- reopening the very List-without-Describe gap these two probes exist to close.
# With ListAddons throttled, a cluster with a dozen add-ons would be reported as having none.
# An empty list is only an empty list when the call succeeded.
_pf_first_of() {
  _q="$1"; shift
  if ! _v="$(aws "$@" --query "$_q" --output text 2>&1)"; then
    printf '%s' "$(printf '%s' "$_v" | _pf_first | cut -c1-70)"; return 2
  fi
  case "$_v" in ""|None) return 1 ;; *) printf '%s' "$_v" ;; esac
}
# _pf_of_dispatch <action> <slug> <captured-output> <rc> -- the two callers below differ only in the
# Describe* they probe, so the three-way outcome is decided in one place. rc 2 records an UNKNOWN verdict
# through the normal machinery rather than silently skipping: it counts in PF_TOTAL, never as an OK, and
# appears in the "did not settle" list the operator already reads.
_pf_of_unknown() {  # $1 action label  $2 slug  $3 list-call error  $4 the List call's own action
  _pf_expect "$1" "a-$2"
  _pf_rec UNKNOWN "$1 -- NOT PROBED: $4 itself failed ($3), so whether this permission is held is unknown" "a-$2"
}
_ad="$(_pf_first_of 'addons[0]' eks list-addons --cluster-name "$CLUSTER" --region "$REGION")"; _rc=$?
if [ "$_rc" -eq 0 ]; then
  pf "eks:DescribeAddon" aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$_ad" --region "$REGION"
elif [ "$_rc" -eq 1 ]; then PF_SKIPPED="$PF_SKIPPED
  eks:DescribeAddon (cluster has no addons, so collection never calls it)"
else _pf_of_unknown "eks:DescribeAddon" "eks-DescribeAddon" "$_ad" "eks:ListAddons"; fi
_fp="$(_pf_first_of 'fargateProfileNames[0]' eks list-fargate-profiles --cluster-name "$CLUSTER" --region "$REGION")"; _rc=$?
if [ "$_rc" -eq 0 ]; then
  pf "eks:DescribeFargateProfile" aws eks describe-fargate-profile --cluster-name "$CLUSTER" --fargate-profile-name "$_fp" --region "$REGION"
elif [ "$_rc" -eq 1 ]; then PF_SKIPPED="$PF_SKIPPED
  eks:DescribeFargateProfile (cluster has no Fargate profiles, so collection never calls it)"
else _pf_of_unknown "eks:DescribeFargateProfile" "eks-DescribeFargateProfile" "$_fp" "eks:ListFargateProfiles"; fi
unset _ad _fp _rc
# CLUSTER-SCOPED. The collector calls `get <r> -o json` with no namespace, so neither does the probe.
for _r in nodes namespaces persistentvolumes storageclasses clusterroles clusterrolebindings \
          validatingwebhookconfigurations mutatingwebhookconfigurations; do
  _pf_expect "kubernetes: list $_r" "k-$_r"; _pf_k8s "$_r" list "$_r" & PF_PIDS="$PF_PIDS $!"
done
# NAMESPACED. Every one of these is collected with `-A`, so the probe is `--all-namespaces`. Without it
# the probe answers for the context's default namespace, which is not the question being asked.
for _r in pods deployments statefulsets daemonsets services ingresses networkpolicies \
          horizontalpodautoscalers poddisruptionbudgets serviceaccounts persistentvolumeclaims \
          resourcequotas limitranges cronjobs jobs rolebindings; do
  _pf_expect "kubernetes: list $_r --all-namespaces" "k-$_r"
  _pf_k8s "$_r" list "$_r" --all-namespaces & PF_PIDS="$PF_PIDS $!"
done
# configmaps is `get`, not `list` -- see the note on _pf_k8s -- and each of the three is a NAMED object in
# a SPECIFIC namespace, which is what the collector asks for and therefore what is probed. The namespaces
# are the collection call sites' own: aws-auth and amazon-vpc-cni in kube-system, aws-logging in
# aws-observability. Keep these three in step with those three `kjson_optional*` calls.
for _cm in "kube-system aws-auth" "aws-observability aws-logging" "kube-system amazon-vpc-cni"; do
  set -- $_cm; _cns="$1"; _cnm="$2"
  _pf_expect "kubernetes: get configmap/$_cnm -n $_cns" "k-configmap-$_cnm"
  _pf_k8s "configmap-$_cnm" get "configmap/$_cnm" -n "$_cns" & PF_PIDS="$PF_PIDS $!"
done
unset _op _r _cm _cns _cnm _pfc_f

# WATCHDOG: wait for the probes, but never past PF_TIMEOUT. kubectl/aws do not offer a hard bound.
# Poll the tracked PIDs, not `jobs`: in a non-interactive shell job control is off, so `jobs -pr` is
# empty, so a loop over it would exit immediately and the blocking move into `wait`, where the ceiling
# is ignored. Each probe's own child (the actual aws/kubectl) is killed too,
# since killing only the subshell leaves the CLI running and re-parented.
_pf_end=$(( $(date +%s) + PF_TIMEOUT ))
while :; do
  _alive=0
  for _p in $PF_PIDS; do kill -0 "$_p" 2>/dev/null && { _alive=1; break; }; done
  [ "$_alive" -eq 0 ] && break
  if [ "$(date +%s)" -ge "$_pf_end" ]; then
    for _p in $PF_PIDS; do pkill -9 -P "$_p" 2>/dev/null; kill -9 "$_p" 2>/dev/null; done
    break
  fi
  sleep 1
done
for _p in $PF_PIDS; do wait "$_p" 2>/dev/null || true; done
unset _p _alive

PF_DENIED=""; PF_EXPIRED=""; PF_UNKNOWN=""
printf '%s\n' "$PF_EXPECTED" | while IFS='|' read -r _lbl _f; do
  [ -n "${_f:-}" ] || continue
  [ -f "$PF_DIR/$_f" ] || printf 'UNKNOWN %s -- probe did not complete within %ss\n' "$_lbl" "$PF_TIMEOUT" > "$PF_DIR/$_f"
done
# $PF_DIR also holds the `response/` subdirectory (see `pfc`), so this glob always includes a directory
# and `cat` therefore always exits 1 in these four lines. That is inert TODAY -- nothing reads their status
# and there is no `set -e` -- but it is a tripwire for whoever adds one: narrow the glob to the verdict
# files, which are all `a-`/`g-`/`p-`/`k-` prefixed, rather than move the response body in here, where
# it would be read by four greps that are looking for verdicts.
PF_DENIED="$(cat "$PF_DIR"/* 2>/dev/null  | grep '^DENIED '  | sed 's/^DENIED /  /'  | sort)"
PF_EXPIRED="$(cat "$PF_DIR"/* 2>/dev/null | grep '^EXPIRED ' | sed 's/^EXPIRED /  /' | sort)"
PF_UNKNOWN="$(cat "$PF_DIR"/* 2>/dev/null | grep '^UNKNOWN ' | sed 's/^UNKNOWN /  /' | sort)"
PF_OKN="$(cat "$PF_DIR"/* 2>/dev/null | grep -c '^OK ')"
PF_TOTAL="$(printf '%s\n' "$PF_EXPECTED" | grep -c '|')"

# ── EKS CONNECTOR CLUSTERS ARE REFUSED HERE, BY NAME, BEFORE ANYTHING IS COLLECTED ─────────────────
# A cluster REGISTERED with EKS via the Connector is not an EKS cluster: it is someone else's conformant
# Kubernetes cluster made visible in the EKS console, and AWS documents the Connector as read-only
# visibility that "does not enable management or mutating operations". `describe-cluster` on one returns
# `name`, `arn`, `createdAt`, `status`, `tags` and `connectorConfig` -- and NOT `version`,
# `resourcesVpcConfig`, `logging`, `encryptionConfig`, `computeConfig` or `accessConfig` (AWS's own
# GKE-connector walkthrough shows exactly this response shape). Without this the run would still have
# failed -- the validation gate requires `cluster.version` -- but it would have failed after a full
# collection, with "cluster.version is not set": a symptom, not the cause. Worse, the absent fields are the
# ones a dozen Security and Operational Excellence questions grade, and an absent `logging` block is
# indistinguishable from logging switched off. A connector cluster would have scored as a badly-configured
# EKS cluster rather than as the wrong kind of input.
#
# WHY IT IS CHECKED HERE AND NOT (ONLY) AFTER `describe-cluster` IS COLLECTED:
#  1. THERE IT WOULD NEVER FIRE ON THE DOCUMENTED WORKFLOW. `aws eks update-kubeconfig` SUCCEEDS on a connector
#     cluster, writing `certificate-authority-data: ""` and `server: null`; `kubectl` then falls back to
#     localhost:8080, all 27 Kubernetes probes go UNKNOWN, and the Kubernetes-half refusal below exits
#     first -- handing the operator three "likely causes" that are all false, one of them telling them to
#     run the `update-kubeconfig` they just ran successfully. Measured with a shimmed `aws`/`kubectl`.
#  2. THERE IT WOULD WEDGE ITS OWN WORK DIRECTORY. Firing after `cluster.json` is written leaves behind the
#     "UNFINISHED collection" marker the WORK DIRECTORY guard refuses on, so run 2 of the identical
#     command would lose this message and report an interrupted collection instead; following that advice
#     re-hits this refusal, which writes the marker again. The one reason the run can never succeed would
#     be printed once and then permanently replaced.
# The preflight makes this call anyway and would otherwise throw the response away, so checking here costs no
# extra API call. Refusing before `cluster.json` is written makes the message reachable, repeatable, and true.
#
# IT IS CHECKED BEFORE THE PERMISSION ARMS BELOW on purpose: scope beats permissions. If describe-cluster
# answered at all then the credentials are neither expired nor denied for it, and no amount of re-authing
# or policy-attaching can make this cluster in scope -- so "out of scope" is the message that helps.
# BOTH conditions are required, and the LOAD-BEARING one is the verdict: `_pf_aws` records `OK` only on a
# zero exit, so a probe that failed or was killed by the watchdog cannot reach this refusal no matter what
# its capture file holds -- a killed `aws` can leave a PARTIAL body behind, and `[ -s ]` only rules out the
# empty case. The verdict is found by FILENAME, which is why `pfc` pins `PF_PREFIX=a-` at the call site
# instead of inheriting it: an exported prefix would file that verdict elsewhere and this `grep` would read
# the watchdog's UNKNOWN placeholder instead. `jq` reading the body is the third condition and it is
# deliberately silent on failure: unreadable JSON is not evidence of a connector cluster, so the run
# continues and the BACKSTOP further down catches the connector case from the collected `cluster.json`.
#
# refuse_connector <note line>... -- ONE message, TWO call sites: here, and the backstop after
# `describe-cluster` is collected. The note is the only part that differs between them; pass one argument
# per line and this function indents each, the same way `_pf_refuse_half` below takes its diagnosis lines.
# Do not pass embedded newlines: only the first line would be indented, so the layout would depend on the
# caller's own source indentation.
refuse_connector() {
  echo "collect.sh: '$CLUSTER' is an EKS CONNECTOR cluster (describe-cluster returned connectorConfig)," >&2
  echo "  so this review does not apply to it. The Connector registers a conformant Kubernetes cluster" >&2
  echo "  running elsewhere -- on-premises, another cloud, another distribution -- for VISIBILITY in the" >&2
  echo "  EKS console. AWS does not run its control plane, and describe-cluster returns none of the" >&2
  echo "  fields this review grades: no version, no resourcesVpcConfig, no logging, no encryptionConfig," >&2
  echo "  no computeConfig. Scoring it would report those absences as misconfiguration." >&2
  echo "  This skill judges Amazon EKS on AWS only, Linux nodes only -- EKS Auto Mode and EC2 compute" >&2
  echo "  (managed node groups, self-managed nodes, Fargate), in any mix, with EKS Hybrid Nodes judged" >&2
  echo "  apart from the EC2 nodes. Windows nodes are not assessed. EKS Anywhere and EKS Connector" >&2
  echo "  clusters are out of scope." >&2
  for _rc_line in "$@"; do echo "  $_rc_line" >&2; done
  echo "  ACTION: nothing here is fixable and no retry helps -- this refusal is about what the cluster IS," >&2
  echo "  not about credentials, network or permissions. Re-run against an EKS cluster whose control plane" >&2
  echo "  AWS runs. Connector clusters appear in \`aws eks list-clusters --region $REGION\` alongside real" >&2
  echo "  ones; the difference is visible in one call --" >&2
  echo "    aws eks describe-cluster --name <NAME> --region $REGION --query 'cluster.version'" >&2
  echo "  returns a Kubernetes version for an EKS cluster and null for a connected one. Exit status 3 is" >&2
  echo "  reserved for this refusal (out of scope, permanently); every other refusal exits 1." >&2
  exit 3
}
if [ -s "$PF_CLUSTER_JSON" ] && grep -q '^OK ' "$PF_DIR/a-eks-DescribeCluster" 2>/dev/null && \
   [ "$(jq -r 'if (.cluster.connectorConfig // null) != null then "yes" else "no" end' "$PF_CLUSTER_JSON" 2>/dev/null)" = "yes" ]; then
  refuse_connector "Nothing has been collected or deleted." \
                   "WORK='$WORK' holds only this preflight's own scratch directory and kubectl's .kube-cache/."
fi

if [ -n "$PF_EXPIRED" ]; then
  echo "PREFLIGHT FAILED -- the credentials in use are expired or invalid, not merely under-permissioned." >&2
  echo "  Nothing has been collected or deleted. Re-authenticate and re-run. Reported by:" >&2
  printf '%s\n' "$PF_EXPIRED" >&2
  exit 1
fi
if [ -n "$PF_DENIED" ]; then
  echo "PREFLIGHT FAILED -- the credentials in use are missing permissions this review requires." >&2
  echo "  Nothing has been collected or deleted. Denied:" >&2
  printf '%s\n' "$PF_DENIED" >&2
  echo "" >&2
  echo "  AWS: every action this review needs is read-only (Describe*/List*/Get*). references/workflow.md's" >&2
  echo "  section 'Permission preflight and the read-only IAM policy' carries a ready-to-attach policy." >&2
  echo "  Kubernetes: the built-in 'view' ClusterRole is NOT sufficient -- it does not cover" >&2
  echo "  clusterroles, clusterrolebindings, rolebindings, either webhook configuration kind," >&2
  echo "  persistentvolumes or storageclasses. 'AmazonEKSAdminViewPolicy' covers them (it also grants" >&2
  echo "  read on Secrets, which this skill never collects)." >&2
  echo "  If you cannot attach these yourself, send this list and that policy to whoever administers" >&2
  echo "  this account's IAM and the cluster's access entries." >&2
  exit 1
fi
# NOTHING verified is not a pass. If no probe settled, the cluster or the credentials are unreachable, and
# proceeding walks into every collection call blocking for as long as the probe just did (measured: 92s per
# kubectl call against an unroutable endpoint). Refuse fast instead of hanging. The per-half arms below
# catch the far more common one-sided version of the same outage.
if [ "$PF_OKN" -eq 0 ] && [ -n "$PF_UNKNOWN" ]; then
  echo "PREFLIGHT FAILED -- not one of the $PF_TOTAL checks could be completed, so nothing about these" >&2
  echo "  credentials or this cluster has been established. That normally means the cluster endpoint is" >&2
  echo "  unreachable from here (private endpoint without a tunnel, wrong context, network path down) or" >&2
  echo "  the credentials are unusable. Nothing has been collected or deleted." >&2
  echo "  First few:" >&2
  printf '%s\n' "$PF_UNKNOWN" | head -5 >&2
  exit 1
fi
# HALF a preflight is not a preflight. The arm above only fires when NOTHING settled, and the outage
# that actually happens is one-sided: every AWS probe answers (those endpoints are public) while every
# Kubernetes probe hangs, because the cluster endpoint is private with no tunnel from here, or $KCTX
# points at a different cluster. PF_OKN is then ~23, the all-or-nothing arm stays quiet, and the run
# walks into 26 kubectl calls that each block as long as the probe just did -- measured at 92s against an
# unroutable endpoint -- before the REQUIRED gate refuses anyway. Half an hour to reach a refusal the
# preflight already held the evidence for. Each half is judged on its own verdict files, so neither can
# be carried by the other's passes.
_pf_half() {  # $1: verdict-file prefix -> "<settled> <total>" on stdout
  _hs=0; _ht=0
  for _vf in "$PF_DIR/$1"*; do
    [ -f "$_vf" ] || continue
    _ht=$((_ht+1))
    grep -q '^OK ' "$_vf" && _hs=$((_hs+1))
  done
  printf '%s %s' "$_hs" "$_ht"
}
_pf_refuse_half() {  # $1: settled  $2: total  $3: half name  $4..: diagnosis lines
  # Every positional is captured BEFORE the shift. Reading "$2" after `shift 3` printed the first
  # diagnosis line where the check count belonged, mid-sentence.
  _hn="$3"; _htot="$2"; shift 3
  echo "PREFLIGHT FAILED -- not one of the $_htot $_hn checks could be completed, so nothing about the" >&2
  echo "  $_hn half of this review has been established. The other half answered, which is why this is" >&2
  echo "  reported separately: a review built from one half only would publish scores for questions it" >&2
  echo "  never measured. Nothing has been collected or deleted." >&2
  for _d in "$@"; do echo "  $_d" >&2; done
}
set -- $(_pf_half "k-"); _k_ok="$1"; _k_tot="$2"
set -- $(_pf_half "a-"); _a_ok="$1"; _a_tot="$2"
set -- $(_pf_half "p-"); _p_ok="$1"; _p_tot="$2"
set -- $(_pf_half "g-"); _g_ok="$1"; _g_tot="$2"   # global/out-of-region: reported, never counted as region proof
if [ "$_k_tot" -gt 0 ] && [ "$_k_ok" -eq 0 ]; then
  _pf_refuse_half "$_k_ok" "$_k_tot" "Kubernetes" \
    "Likely causes, in the order they occur:" \
    "  * the cluster's API endpoint is private and there is no network path from here" \
    "  * --context/\$KCTX names a context for another cluster, or one whose token has expired" \
    "  * \`aws eks update-kubeconfig --name $CLUSTER --region $REGION${KCFG:+ --kubeconfig \"$KCFG\"}\` has not been run for this cluster" \
    "Check with: kubectl auth can-i list nodes --context \"\$KCTX\"${KCFG:+ --kubeconfig \"$KCFG\"}"
  printf '%s\n' "$PF_UNKNOWN" | grep 'kubernetes:' | head -5 >&2
  exit 1
fi
if [ $(( _a_ok + _p_ok )) -eq 0 ] && [ $(( _a_tot + _p_tot )) -gt 0 ]; then
  _pf_refuse_half "$(( _a_ok + _p_ok ))" "$(( _a_tot + _p_tot ))" "AWS (in $REGION)" \
    "Likely causes: no credentials for this account in this shell, the wrong --profile, or no network" \
    "path to the AWS endpoints in $REGION. Check with: aws sts get-caller-identity --region $REGION" \
    "$_g_ok of $_g_tot probes to endpoints OUTSIDE $REGION did answer (sts, iam, pricing). Credentials" \
    "  working globally while nothing in $REGION answers points at the region or its endpoints, not at" \
    "  the credentials -- which is why those three do not count towards this half."
  printf '%s\n' "$PF_UNKNOWN" | grep -v 'kubernetes:' | head -5 >&2
  exit 1
fi
unset _k_ok _k_tot _a_ok _a_tot _p_ok _p_tot _g_ok _g_tot _hs _ht _vf _hn _htot _d

# Report what was actually established -- never "all permitted" when something did not settle.
if [ -n "$PF_UNKNOWN" ]; then
  echo "OK: preflight -- $PF_OKN of $PF_TOTAL checks passed; none denied. These did not settle and are NOT" >&2
  echo "    confirmed; collection fails loud if they matter:" >&2
  printf '%s\n' "$PF_UNKNOWN" >&2
else
  echo "OK: preflight -- all $PF_TOTAL applicable AWS actions and Kubernetes reads are permitted."
fi
if [ -n "$PF_SKIPPED" ]; then
  echo "NOTE: not applicable to this cluster, so not probed:$PF_SKIPPED" >&2
fi

# $WORK IS CREATED ABOVE, BEFORE THE PERMISSION PREFLIGHT, whose scratch lives inside it (see PF_DIR),
# and not here after it. The `_work_precreated` test runs before `mkdir -p`.
# Restrictive from the moment it exists: the collected JSON contains the account id, IAM role and
# OIDC ARNs, security-group and subnet ids, and cluster tags. `chmod`, not just an early `umask`, so a
# directory a caller pre-created is left at the mode they chose -- this script will not change the mode
# of a directory it did not make. `umask 077` above already lands every file it writes owner-only.
# A preflight refusal therefore leaves $WORK behind holding only `.eks-war-preflight.XXXXXX/`, which the
# WORK DIRECTORY guard does not refuse: re-running into the same --work path is not blocked by it.
# results.jsonl is NOT created here. It is one of the three markers the WORK DIRECTORY guard above refuses
# on, and a script that plants its own guard's marker would wedge, once non-empty, the directory against
# the commonest case there is: a run that fails partway and is retried, then refused as "already holds a
# previous run" over a file it wrote itself. (The guard also tests results.jsonl with `-s`, so an EMPTY
# one, which holds no scored output, is not refused.) The guard is the right behaviour, and creating the
# very marker it refuses on would work against it. Nothing needs the file
# to pre-exist: score.sh's every `emit` appends with `>>`, and its already-scored check is written
# `[ -f ... ] && grep -q ...` precisely so an absent file is not an error.
# There is deliberately no SKILL_DIR check here, and nothing in this script needs one.
#
# Steps 7 and 8 invoke assets/reduce.sh and assets/render-report.py, and must work from any working
# directory -- a bare `assets/...` form resolves only when the shell happens to be sitting in the skill
# root, which is not where $WORK is. This script invokes neither of them, so demanding an exported
# SKILL_DIR on their behalf would only be a way to fail early over a path this script never uses --
# and, as below, there is no such path left to fail over.
#
# SKILL.md writes those invocations as `${CLAUDE_SKILL_DIR}/assets/...`, which Claude Code
# substitutes in both the skill body and the Bash rules in `allowed-tools` -- so the path arrives
# already absolute and there is nothing to export or to check. Requiring the export would
# refuse every run that follows the current instructions, which do not tell anyone to
# export it. reduce.sh reads no SKILL_DIR at all, and render-report.py finds references/ from its own
# __file__, so neither downstream step depends on it either.
# Nothing is cleared here. The guard above proved the work directory holds none of THIS review's output
# (see WORK DIRECTORY), so there is no previous collection to remove and no stale file to shadow a failed
# call. It may well hold other files, and those are none of this script's business.
# The fingerprint is written only at the END of a successful collection, so an unfinished run leaves
# none at all -- which is the message that is actually true.

export AWS_PAGER=""            # never page
# AWS_PROFILE is honoured if exported; `--profile` also unsets the env credentials that outrank AWS_PROFILE.

COLLECT_ERRORS=0              # incremented on any hard failure; checked by the validation gate

# ── CLUSTER IDENTITY BINDING (REQUIRED) ────────────────────────────────────────────────────────────
# The AWS half of this review comes from `aws eks describe-cluster --name $CLUSTER`, and the
# Kubernetes half from whatever `kubectl` happens to point at. Unbound, NOTHING ties those together.
# An operator with several clusters in their kubeconfig could collect the control-plane facts from
# cluster A and every pod, node and RBAC object from cluster B, and the validation gate would pass:
# every REQUIRED file present, all valid JSON, `cluster.version` set, `namespaces.json` non-empty. The
# resulting report names cluster A and grades cluster B's workloads.
#
# KCTX is mandatory and has no default. `kubectl config current-context` is deliberately NOT used as a
# fallback: an unattended run would then silently inherit whatever context was last selected, which is
# the failure this binding exists to prevent.
#
# THE CHECK ITSELF RUNS FURTHER UP, beside the other required-parameter validation and BEFORE $WORK
# is created or chmod-ed. Here would be after both, so a run that is going to be refused for a missing
# KCTX would first create the work dir and the preflight's scratch inside it, and only then decline to
# collect. A refusal over a missing variable should leave nothing behind, and nothing about validating
# a variable needs to happen after that point.

# kctl : every kubectl call after this point goes through here, and the one before it (_pf_k8s's `auth can-i`) passes the
# same flags itself -- a binding enforced on some calls is not a binding. --cache-dir keeps kubectl's cache out of ~/.kube;
# --kubeconfig, when given, is passed the same way, so the kubeconfig SKILL.md Step 1 writes into $WORK is the one read.
kctl() { kubectl --context "$KCTX" ${KCFG:+--kubeconfig "$KCFG"} --cache-dir "$WORK/.kube-cache" "$@"; }

# firstline <file> : the first NON-EMPTY line of a captured stderr.
# `head -1` loses the reason whenever stderr opens with a blank line or a deprecation warning,
# leaving the operator with "ERROR: failed to collect volumes.json:" and no cause — which is
# nearly as unhelpful as no message at all. Observed for real on a denied ec2:DescribeVolumes.
firstline() { grep -m1 -v '^[[:space:]]*$' "$1" 2>/dev/null; }

# awsjson <outfile> -- <aws ...> : required AWS call. Retries (3x, backoff), writes only on
# success + valid JSON, otherwise records a hard error. Never fabricates data.
awsjson() {
  local out="$1"; shift; [ "${1:-}" = "--" ] && shift
  local tmp="$out.tmp" n=0
  while :; do
    if "$@" >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "$out"; return 0
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then
      echo "ERROR: failed to collect $(basename "$out"): $(firstline "$tmp.err")" >&2
      COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1   # $tmp, $tmp.err stay: no `*.json` glob matches them
    fi
    sleep $((n*2))
  done
}

# awsjson_detail <outfile> -- <aws ...> : DETAIL AWS call whose absence DEGRADES a verdict rather than
# invalidating the file it merges into. A failure is a warning here and never fatal -- but it must also
# leave NO ARTIFACT, and it must be caught somewhere.
#
# A SCORER DOES READ WHAT THIS HELPER MERGES, so "no scorer reads these, so a failure is harmless" is
# false: `lens-7` reads `.addonDetails[]` and `.addonTargets[]`. The two
# are not equally load-bearing, and they are covered differently:
#   * `.addonDetails` (describe-addon) decides `lens-7`'s version, status and health. A dropped entry
#     would make `lens-7` award `most` (75%) for vpc-cni off an API it never saw, while the run still
#     printed "Safe to score" -- an `addons: N / addonDetails: N-1` shape. The ADD-ON GAP CANARY further
#     down refuses that shape.
#   * `.addonTargets` (describe-addon-versions) decides only currency, and `lens-7` has an explicit
#     "its currency was not assessed" arm for the absent case. That degrades honestly, so it stays a
#     warning with no canary.
# It retries 3x, as the REQUIRED `awsjson` beside it does: a single attempt makes a transient throttle
# indistinguishable from a denial.
# A bare `aws ... > "$WORK/addon-$A.json" || echo WARN` leaves an artifact: bash creates the redirect target BEFORE
# running the command, so a denied call leaves a 0-byte addon-*.json behind, and the blanket
# `jq -e .` scan in the validation gate then throws away a collection in which every REQUIRED file is
# present and valid. A read-only role holding eks:List* but not
# eks:DescribeAddon -- that is commonly scoped out separately from the List
# calls -- would get a "(non-fatal)" warning per add-on and then "COLLECTION FAILED". A best-effort
# call whose failure discards the whole run is not best-effort. Writes via a `.tmp` path (which the
# gate's `*.json` glob does not match) and promotes it only on success + valid JSON.
awsjson_detail() {
  local out="$1"; shift; [ "${1:-}" = "--" ] && shift
  local tmp="$out.tmp" n=0
  while :; do
    if "$@" >"$tmp" 2>/dev/null && jq -e . "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "$out" && return 0
      # A FAILED RENAME MUST NOT REPORT SUCCESS HERE, and this helper is the only one where that
      # matters. The other write helpers name a FIXED output file: a failed rename there leaves the file
      # absent, and the REQUIRED gate at the bottom of this script already refuses the run with
      # "cluster.json(NOT COLLECTED)" -- measured. This helper's two callers instead reuse ONE scratch
      # path ($WORK/.ad.json, $WORK/.av.json) across loop iterations and do not clear it between them,
      # so `mv … ; return 0` would hand the merge the PREVIOUS add-on's response to fold in under the
      # CURRENT add-on's name. On a three-add-on cluster with the rename failing on vpc-cni, addonDetails
      # would come out [coredns, coredns, kube-proxy] -- coredns recorded twice, vpc-cni missing -- and
      # the name/detail COUNTS would still match 3=3, so the add-on gap canary below could not see it
      # either. `lens-7` would report vpc-cni unassessed, or worse, another add-on's version as its own.
      # `return 1` prevents that, and nothing is deleted: both callers merge $out only on a 0, so a stale
      return 1   # body left there (and the unrenamed $tmp) is never read; the next success overwrites it.
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then
      return 1         # the partial stays at $tmp, a `.tmp` name the validation gate's `*.json` never matches
    fi
    sleep $((n*2))
  done
}

# kjson <outfile> <kubectl get-args...> : required kubectl call. A cluster with no objects of a
# type returns exit 0 with {"items":[]} — that is a valid empty, kept as-is. A non-zero exit
# (auth/throttle/RBAC) is retried, then recorded as a hard error. Never fabricates data.
kjson() {
  local out="$1"; shift
  local tmp="$out.tmp" n=0
  while :; do
    if kctl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "$out"; return 0
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then
      echo "ERROR: kubectl --context $KCTX get $* failed: $(firstline "$tmp.err")" >&2
      COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1   # $tmp, $tmp.err stay: no `*.json` glob matches them
    fi
    sleep $((n*2))
  done
}

# kjson_optional_doc <outfile> <empty-doc> <kubectl get-args...> : for maybe-absent CRDs and objects.
# Falls back to <empty-doc> ONLY when the resource genuinely does not exist. Any other error is hard.
#
# <empty-doc> is a parameter because the two absent shapes are not the same shape. A LIST get returns
# `{"items":[]}`, so that is what its absence must look like; a SINGLE-OBJECT get (`get configmap
# amazon-vpc-cni`) returns one ConfigMap object, and normalising its absence to `{"items":[]}` hands the
# scorer a document of a type it never sees on a cluster where the object exists. `{}` keeps
# `.data["enable-network-policy-controller"]` reading null either way, which is the point.
kjson_optional_doc() {
  local out="$1" empty="$2"; shift 2
  local tmp="$out.tmp"
  if kctl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
    mv "$tmp" "$out"; return 0
  fi
  if grep -qiE "the server doesn't have a resource type|could not find (the )?requested resource|Unknown resource|NotFound" "$tmp.err" 2>/dev/null; then
    printf '%s\n' "$empty" >"$out"; return 0   # genuinely absent → empty is correct
  fi
  echo "ERROR: kubectl --context $KCTX get $* failed (not a missing-resource error): $(firstline "$tmp.err")" >&2
  COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1
}

# kjson_optional <outfile> <kubectl get-args...> : the list-shaped case, unchanged for its six callers.
kjson_optional() {
  local out="$1"; shift
  kjson_optional_doc "$out" '{"items":[]}' "$@"
}
awsjson "$WORK/cluster.json"    -- aws eks describe-cluster       --name "$CLUSTER" --region "$REGION" --output json

# ── EKS CONNECTOR BACKSTOP ─────────────────────────────────────────────────────────────────────────
# The refusal itself, and the reasoning behind it, live in the PREFLIGHT (see EKS CONNECTOR CLUSTERS
# above), which is where it belongs: there it runs before `cluster.json` is written, so it leaves no marker
# and stays reachable and repeatable. This is the same check on the same condition, kept because the preflight
# copy can be defeated. No claim is made here about how many ways -- an exhaustive count is exactly the
# sort of assertion that rots -- but these are the known ones, and each was reproduced:
#   * the probe DID NOT SETTLE -- watchdog kill, throttle, transient fault -- which the preflight reports
#     and deliberately allows through, since one inconclusive probe must not block a viable run;
#   * the RESPONSE COULD NOT BE KEPT: `$PF_DIR/response` could not be created, so `$PF_CLUSTER_JSON` is
#     empty and the preflight check has nothing to read. The preflight says so in a NOTE naming the path;
#   * the probe settled `OK` and the body WAS kept, but it is not JSON this check can read -- a warning or
#     banner printed ahead of the document, a response shape `jq` cannot match, a truncation the CLI did
#     not report. Then the preflight prints a clean "all N permitted" and this is the only thing between
#     that and a scored connector cluster. (An unchecked `mkdir` is NOT a cause of this arm: a failed
#     redirect makes the probe record UNKNOWN -- fault injection shows it -- so it lands in the FIRST
#     arm, which is why the `mkdir` is checked and has its own arm above.)
# Without any of them, such a cluster would be refused three checks later by the CLUSTER IDENTITY BINDING
# for "describe-cluster CA present: no", which is a symptom of the same cause and reads like a kubeconfig
# problem.
#
# This call site HAS already written `cluster.json`, and that file is unambiguously this run's own -- the
# WORK DIRECTORY guard refuses at startup if it pre-exists -- so the message says so and says what to do
# about it. It does NOT tell the operator which arm fired, because from here they are indistinguishable and
# the remedy is identical either way. The script still deletes nothing.
if [ -s "$WORK/cluster.json" ] && \
   [ "$(jq -r 'if (.cluster.connectorConfig // null) != null then "yes" else "no" end' "$WORK/cluster.json" 2>/dev/null)" = "yes" ]; then
  refuse_connector \
    "This was caught after collection STARTED, because the preflight's own copy of this check could" \
    "not run: its eks:DescribeCluster probe did not settle, or that probe's response could not be" \
    "kept or could not be read. The work directory" \
    "  WORK='$WORK'" \
    "now holds this run's cluster.json and its scratch, nothing more. Move it before you re-run ANY" \
    "cluster with that --work path: while that file is there, the work-directory guard reports an" \
    "unfinished collection instead of this message."
fi
awsjson "$WORK/nodegroups.json" -- aws eks list-nodegroups        --cluster-name "$CLUSTER" --region "$REGION" --output json
awsjson "$WORK/addons.json"     -- aws eks list-addons            --cluster-name "$CLUSTER" --region "$REGION" --output json
# EKS recomputes these once a day from the control-plane audit logs, at no charge, so reading them
# costs the review one call and nothing else. `ope-20` grades the UPGRADE_READINESS category.
awsjson "$WORK/insights.json"   -- aws eks list-insights          --cluster-name "$CLUSTER" --region "$REGION" --output json
awsjson "$WORK/fargate.json"    -- aws eks list-fargate-profiles  --cluster-name "$CLUSTER" --region "$REGION" --output json

# EKS Pod Identity associations. REQUIRED, not optional: Pod Identity is the mechanism AWS now
# recommends over IRSA, and it uses NO ServiceAccount annotation — associations live only in the
# EKS API. Without this call, `sec-6` (High) sees a correctly-built Pod Identity cluster as having
# no workload identity at all and reports a false High-severity finding.
awsjson "$WORK/podidentity.json" -- aws eks list-pod-identity-associations --cluster-name "$CLUSTER" --region "$REGION" --output json

# The IAM OIDC identity provider. REQUIRED, and deliberately NOT treated as optional.
# `cluster.identity.oidc.issuer` is populated on EVERY EKS cluster — it is the *input* to
# `aws iam create-open-id-connect-provider`, not evidence that the provider exists. The provider is
# a separate IAM resource, so scoring OIDC/IRSA off the issuer alone is a pass that cannot fail.
# Note this is an ACCOUNT-scoped call (iam:ListOpenIDConnectProviders), unlike everything else here.
# It must still fail loud: if a denial were substituted with an empty list, `sec-18` (High) would
# report "no IAM OIDC provider" on a cluster that has one — a false finding is worse than a refusal.
awsjson "$WORK/oidcproviders.json" -- aws iam list-open-id-connect-providers --output json

export VPC=$(jq -r '.cluster.resourcesVpcConfig.vpcId // empty' "$WORK/cluster.json")

# ── IDENTITY CROSS-CHECK: does $KCTX actually point at $CLUSTER? ────────────────────────────────────
# Runs HERE — after cluster.json exists, before the first `kubectl get` — so a mismatch costs one AWS
# call rather than a full collection and a wrong report.
#
# Compare the cluster CA CERTIFICATE, not the endpoint URL. Both sides publish it -- describe-cluster
# as `.cluster.certificateAuthority.data`, the kubeconfig as `certificate-authority-data` -- it is issued
# per cluster, and it identifies the cluster rather than the route taken to reach it.
#
# WHY NOT THE ENDPOINT URL: a URL is a network address, so any
# legitimate indirection makes the two sides differ and a URL check refuses a cluster it should
# accept. A private-endpoint cluster reached over an SSM/SSH tunnel presents `https://127.0.0.1:6443`
# in the kubeconfig while describe-cluster reports the real hostname. kubectl proxy, an /etc/hosts
# override and an egress proxy all break it the
# same way. A URL check would leave the skill unable to review exactly the posture its own `sec-2`
# rewards: turn the public endpoint off, as the Security pillar asks, and the review would stop working.
#
# The CA comparison keeps the teeth a URL check would have. The hazard is a kubeconfig pointing at a
# DIFFERENT cluster, and EKS provisions each cluster's control plane with its own CA at creation, so a CA
# match identifies the cluster. Pairing one cluster's describe-cluster CA with another cluster's
# kubeconfig CA fails the match, which any two clusters of your own will show.
# Context names are not compared: a context name is user-renameable and often not the cluster ARN.
# ca_canon: reduce a PEM certificate bundle to a canonical string -- the base64 payload of every
# CERTIFICATE block, whitespace stripped, in order. Compare THAT, never the raw bytes.
#
# WHY: the two sides publish the same certificate in cosmetically different files. describe-cluster
# returns base64-of-PEM; a kubeconfig may embed the same base64 or point at a PEM file on disk. Comparing
# raw bytes would make a single TRAILING NEWLINE -- what every editor, `echo >>` and mounted ConfigMap adds --
# report `CLUSTER MISMATCH ... two different clusters` for a byte-identical certificate: the pristine
# file accepted, the same file plus "\n" refused. That is worse than the false refusal the CA-file
# fallback below exists to prevent, because it is a confident wrong verdict rather than a cautious
# one. Canonicalising also handles CRLF, a different PEM wrap column, and a multi-certificate bundle.
ca_canon() {  # stdin: PEM text -> stdout: ONE canonical payload PER CERTIFICATE, one per line
  # One line per certificate, NOT one blob for the whole file. Concatenating every certificate into
  # a single string would make a two-certificate trust bundle unable to equal a
  # one-certificate describe-cluster response no matter which cluster it belonged to.
  awk '/-----BEGIN CERTIFICATE-----/{i=1;b="";next}
       /-----END CERTIFICATE-----/{if(i){gsub(/[ \t\r]/,"",b); if(b!="") print b} i=0; next}
       i{b=b $0}'
}
ca_shares_cert() {  # $1,$2: newline-separated canonical cert lists -> 0 when they share at least one
  # Parameter expansion only, no here-document: bash < 5.1 always, and any bash for a large bundle,
  # backs one with a temp file outside $WORK. Each line of $1 is matched as a whole line of $2.
  local _a _rest _nl='
'
  _rest="$1$_nl"
  while [ -n "$_rest" ]; do
    _a="${_rest%%"$_nl"*}"; _rest="${_rest#*"$_nl"}"
    [ -n "$_a" ] || continue
    case "$_nl$2$_nl" in *"$_nl$_a$_nl"*) return 0 ;; esac
  done
  return 1
}
ca_count() { printf '%s\n' "$1" | grep -c '[^[:space:]]'; }

K_ENDPOINT=$(kctl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)
K_CA=$(kctl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null | tr -d '\n\r ' | { b=$(cat); [ -n "$b" ] && printf '%s' "$b" | base64 -d 2>/dev/null | ca_canon; })
# A kubeconfig may reference its CA as a FILE (`certificate-authority: /path`) instead of embedding it as
# base64 (`certificate-authority-data`). `aws eks update-kubeconfig` always embeds, but a hand-built or
# tool-converted kubeconfig, and some CI setups that mount the CA, use the file form -- and reading only
# the embedded field would refuse those, a false refusal that comparing CAs instead of endpoints
# would otherwise introduce. Fall back to the file and encode it the same way AWS publishes it.
if [ -z "$K_CA" ]; then
  K_CAFILE=$(kctl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority}' 2>/dev/null)
  # A relative CA path is resolved by kubectl against the KUBECONFIG FILE's directory, not $PWD --
  # `kubectl config set-cluster --certificate-authority=/tmp/ca.crt` with KUBECONFIG=/tmp/cfg stores the
  # bare name `ca.crt`. Testing it as-is would therefore fail from any other working directory.
  case "$K_CAFILE" in
    /*) : ;;
    ?*) _kcfg="${KUBECONFIG:-}"; _kcfg="${KCFG:-${_kcfg%%:*}}"; [ -n "$_kcfg" ] || _kcfg="$HOME/.kube/config"
        K_CAFILE="$(dirname "$_kcfg")/$K_CAFILE"; unset _kcfg ;;
  esac
  if [ -n "$K_CAFILE" ] && [ -r "$K_CAFILE" ]; then
    K_CA=$(ca_canon < "$K_CAFILE" 2>/dev/null)
  fi
  unset K_CAFILE
fi
A_ENDPOINT=$(jq -r '.cluster.endpoint // empty' "$WORK/cluster.json")
A_CA=$(jq -r '.cluster.certificateAuthority.data // empty' "$WORK/cluster.json" | tr -d '\n\r ' | { b=$(cat); [ -n "$b" ] && printf '%s' "$b" | base64 -d 2>/dev/null | ca_canon; })
if [ -z "$K_CA" ] || [ -z "$A_CA" ]; then
  echo "ERROR: cannot verify cluster identity — kubeconfig CA present: $([ -n "$K_CA" ] && echo yes || echo no)," >&2
  echo "       describe-cluster CA present: $([ -n "$A_CA" ] && echo yes || echo no)." >&2
  echo "       Refusing to collect: an unverified binding is how the AWS half and the kubectl half end up" >&2
  echo "       describing different clusters. A kubeconfig with no embedded CA (for example one using" >&2
  echo "       insecure-skip-tls-verify) cannot be identity-checked; re-create it with" >&2
  echo "       'aws eks update-kubeconfig --name $CLUSTER --region $REGION --alias $CLUSTER${KCFG:+ --kubeconfig \"$KCFG\"}'." >&2
  COLLECT_ERRORS=$((COLLECT_ERRORS+1))
elif ! ca_shares_cert "$A_CA" "$K_CA"; then
  echo "ERROR: CLUSTER MISMATCH — refusing to collect." >&2
  echo "       kubectl context '$KCTX' presents a different cluster CA than aws describe-cluster" >&2
  echo "       '$CLUSTER' does, so they are two different clusters." >&2
  echo "       kubectl context endpoint  : $K_ENDPOINT" >&2
  echo "       describe-cluster endpoint : $A_ENDPOINT" >&2
  echo "       The report would name '$CLUSTER' while grading a different cluster's workloads." >&2
  echo "       Fix with: aws eks update-kubeconfig --name $CLUSTER --region $REGION --alias $CLUSTER${KCFG:+ --kubeconfig \"$KCFG\"}" >&2
  COLLECT_ERRORS=$((COLLECT_ERRORS+1))
elif [ "${K_ENDPOINT%/}" != "${A_ENDPOINT%/}" ]; then
  # Same cluster, different route. Legitimate (tunnel/bastion/proxy) -- disclose it, do not refuse. It
  # is reported because it tells the reader the data came through an indirect path.
  echo "OK: kubectl context '$KCTX' and cluster '$CLUSTER' present the SAME cluster CA."
  echo "NOTE: reached indirectly — kubeconfig points at $K_ENDPOINT while the cluster endpoint is" >&2
  echo "      $A_ENDPOINT (tunnel, port-forward or proxy). Identity is verified by CA, so this is" >&2
  echo "      accepted; the collected data is this cluster's." >&2
else
  _kn=$(ca_count "$K_CA")
  echo "OK: kubectl context '$KCTX' and cluster '$CLUSTER' both resolve to $A_ENDPOINT (CA verified)"
  # A trust bundle carrying more than one CA is EXPECTED during an EKS CA rotation's dual trust period.
  # AWS: "clients should be configured to trust a CA bundle rather than pin to a single CA certificate".
  [ "$_kn" -gt 1 ] && echo "NOTE: the kubeconfig trusts $_kn CAs (an EKS CA rotation's dual trust period looks" >&2
  [ "$_kn" -gt 1 ] && echo "      exactly like this). The cluster's in-use CA is among them, so identity is verified." >&2
  unset _kn
fi
# Abort now rather than at the validation gate: every kubectl call after this point would collect the
# wrong cluster's data, and the gate cannot tell whose data it is looking at.
[ "$COLLECT_ERRORS" -eq 0 ] || { echo "Aborting collection." >&2; exit 1; }
[ -n "$VPC" ] || { echo "ERROR: could not read VPC id from cluster.json — aborting (cluster describe failed?)" >&2; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); }

# ADDON DETAIL, MERGED INTO THE ONE FIXED FILE A SCORER CAN NAME.
# A scorer can only read a FIXED filename, and `addon-<NAME>.json` is variable: it exists only for the
# addons a cluster happens to install. So `lens-7` -- titled "Is the VPC CNI addon version current and
# healthy?" -- could not name it, and answering from the bare NAME list would report `all` ("vpc-cni
# managed") on a cluster whose vpc-cni is two versions behind the default. `addonVersion`, `status` and
# `health.issues` come from one DescribeAddon per addon.
# Merged as `.addonDetails[]` they are addressable, and `[]` on an addon-less cluster needs no guard.
# No per-addon files are written: their content would be byte-identical to the merged entry.
if [ -f "$WORK/addons.json" ]; then
  jq '. + {addonDetails: (.addonDetails // [])}' "$WORK/addons.json" > "$WORK/.adm.json" \
    && mv "$WORK/.adm.json" "$WORK/addons.json"
  for A in $(jq -r '.addons[]?' "$WORK/addons.json"); do
    if awsjson_detail "$WORK/.ad.json" -- aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$A" --region "$REGION" --output json; then
      jq -s '.[0] + {addonDetails: ((.[0].addonDetails // []) + [.[1].addon | objects])}' \
        "$WORK/addons.json" "$WORK/.ad.json" > "$WORK/.adm.json" \
        && mv "$WORK/.adm.json" "$WORK/addons.json"
    else
      echo "collect.sh: WARN addon detail '$A' not collected; lens-7 reports it unassessed" >&2
    fi
  done
  # What "current" means requires the versions AWS offers for THIS cluster's Kubernetes version, which
  # is a second call per addon. THIS SCRIPT MAKES NO CLAIM ABOUT THE ORDER OF `versions`, and `lens-7`
  # depends on none. It is tempting to assume the list is NEWEST FIRST and read the installed version's
  # index as "exactly how many releases behind it is -- no semver parsing, and no ordering assumption
  # of our own". Both halves are wrong: the index IS the ordering assumption, nothing verifies it, and
  # reversing the list would flip `lens-7` from `most` to `all`, claiming a version two minor releases
  # old was "at or newer than the EKS default". Nor is the index a release count -- the list
  # interleaves `-eksbuild.N` rebuilds, so an index distance of 13 can span just 3 distinct minor
  # versions. So `lens-7` parses
  # vMAJOR.MINOR.PATCH[-eksbuild.N] and compares tuples, so the order this call returns is irrelevant.
  # `defaultVersion` is what EKS would install today.
  _K8S=$(jq -r '.cluster.version // empty' "$WORK/cluster.json" 2>/dev/null)
  if [ -n "$_K8S" ]; then
    for A in $(jq -r '.addons[]?' "$WORK/addons.json"); do
      if awsjson_detail "$WORK/.av.json" -- aws eks describe-addon-versions --addon-name "$A" --kubernetes-version "$_K8S" --region "$REGION" --output json; then
        jq -s --arg a "$A" '.[0] + {addonTargets: ((.[0].addonTargets // []) + [{
              addonName: $a,
              versions: [.[1].addons[0].addonVersions[]?.addonVersion],
              defaultVersion: ([.[1].addons[0].addonVersions[]? | select(any(.compatibilities[]?; .defaultVersion)) | .addonVersion] | first)
            }])}' "$WORK/addons.json" "$WORK/.av.json" > "$WORK/.adm.json" \
          && mv "$WORK/.adm.json" "$WORK/addons.json"
      else
        echo "collect.sh: WARN available versions for addon '$A' not collected; lens-7 reports its currency unassessed" >&2
      fi
    done
  else
    echo "collect.sh: WARN cluster version unreadable, so addon currency was not looked up" >&2
  fi
  unset _K8S
  # .ad/.adm/.av.json are left in place: dot-names, read only right after these loops rewrite them.
fi
# Fargate profile detail, merged into ONE file the scorers read. fargate-1 (selector specificity)
# needs this call: without it it could only answer `na~NOT ASSESSED` --
# claiming "not applicable" for something the review simply had not looked at, which is excluded from
# scoring and so silently inflates coverage. Required, not best-effort: if there are profiles, their
# detail is the only way to answer a question that would otherwise pretend to be inapplicable.
echo '{"profiles":[]}' > "$WORK/fargateprofiles.json"
for FP in $(jq -r '.fargateProfileNames[]?' "$WORK/fargate.json"); do
  if awsjson "$WORK/.fp.json" -- aws eks describe-fargate-profile --cluster-name "$CLUSTER" --fargate-profile-name "$FP" --region "$REGION" --output json; then
    jq -s '{profiles: (.[0].profiles + [.[1].fargateProfile])}' "$WORK/fargateprofiles.json" "$WORK/.fp.json" > "$WORK/.fpm.json" \
      && mv "$WORK/.fpm.json" "$WORK/fargateprofiles.json"
  fi
done
# .fp.json/.fpm.json are left in place: dot-names, read only right after this loop rewrites them.
for R in nodes namespaces storageclasses pv clusterroles clusterrolebindings \
         validatingwebhookconfigurations mutatingwebhookconfigurations; do
  kjson "$WORK/$R.json" "$R"; done
for R in pods deployments statefulsets daemonsets services ingresses networkpolicies hpa pdb \
         serviceaccounts pvc resourcequotas limitranges cronjobs jobs rolebindings; do
  kjson "$WORK/$R.json" "$R" -A; done
# cp, not `ln -sf`: the scorers read these under both names, and a copy needs no symlink support and
# no `ln` in the tool allowlist, and it survives $WORK being moved or archived, which a symlink
# written relative to another directory may not.
# sec-10 reads the short names; the validation gate checks the long ones, so both have to exist. The copy
# is CONDITIONAL because an unconditional one would emit a raw `cp: ...: No such file or directory` whenever
# the source had not been collected -- the only unprefixed error text in an otherwise uniform report.
for _wh in validating mutating; do
  if [ -f "$WORK/${_wh}webhookconfigurations.json" ]; then
    cp "$WORK/${_wh}webhookconfigurations.json" "$WORK/${_wh}webhooks.json"
  else
    echo "collect.sh: ${_wh}webhookconfigurations.json was not collected, so ${_wh}webhooks.json cannot be written" >&2
  fi
done
unset _wh
# Kyverno / Gatekeeper policies — optional CRDs; empty only when the CRD is not installed
# EKS Fargate's documented log router is NOT a sidecar. AWS: "you don't explicitly run a Fluent Bit
# container as a sidecar, but Amazon runs it for you. All that you have to do is configure the log
# router" — via a ConfigMap named `aws-logging` in the namespace `aws-observability`. Without collecting
# it, `fargate-4` can never credit a correctly-configured Fargate cluster. Optional-style because its
# absence is a legitimate finding, not a collection failure.
kjson_optional "$WORK/awslogging.json" configmap aws-logging -n aws-observability
# aws-auth maps IAM principals to Kubernetes RBAC groups. An entry granting system:masters is a
# full-cluster takeover path via IAM, and it is invisible to a ClusterRoleBinding check: the binding
# names the GROUP system:masters, which is a legitimate built-in, while the aws-auth ConfigMap decides
# who is IN that group. rbac-1 therefore reads this file as its second input, alongside
# clusterrolebindings.json -- sec-17 still only reads accessConfig.authenticationMode.
#
# Collecting this file and letting nothing read it would be worse than not collecting it: this comment
# describes the exact attack path as the reason for collecting it, so the gap would read as
# coverage. Optional because a cluster on API-only auth legitimately has no aws-auth ConfigMap, and its
# absence must leave rbac-1 exactly as it was rather than manufacture a finding.
kjson_optional "$WORK/awsauth.json" configmap aws-auth -n kube-system

kjson_optional "$WORK/kyverno.json"           clusterpolicies.kyverno.io
kjson_optional "$WORK/constraints.json"       constraints -A
kjson_optional "$WORK/constrainttemplates.json" constrainttemplates

# ── TWO AUTO MODE OBJECTS WHERE ABSENCE *IS* THE ANSWER ─────────────────────────────────────────────
# Both go through the optional helper, and the contrast with the two EC2 calls further down is the
# crux of this whole block -- they look like the same situation and are opposites:
#
#   * An EC2 list call that comes back empty on an Auto Mode cluster is a BLIND INSTRUMENT. Nothing
#     about the cluster changed; the API stopped reporting. Scoring that as "no instances, no volumes"
#     invents three findings, so it is repaired below and, if it cannot be repaired, REFUSED.
#   * A ConfigMap or a CRD that is not there IS the measurement. No `amazon-vpc-cni` ConfigMap means
#     the Network Policy Controller was never enabled; no NodeClass means no Auto Mode NodeClass was
#     ever created. Both are exactly what the operator wants to be told. Turning either into a
#     collection error would refuse an entire review over a correct answer.
#
# So these two exit 0 with a normalised empty document and never touch the not-collected machinery --
# while a Forbidden or a connection failure still fails loud, because the helper only accepts
# "resource does not exist" as grounds for an empty.

# The amazon-vpc-cni ConfigMap. https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html,
# "Step 1: Enable Network Policy Controller", verbatim:
#   "To use network policies with EKS Auto Mode, you first need to enable the Network Policy Controller
#    by applying a ConfigMap to your cluster."
# and the manifest it then shows is `metadata.name: amazon-vpc-cni`, `namespace: kube-system`,
# `data.enable-network-policy-controller: "true"`.
# https://docs.aws.amazon.com/eks/latest/best-practices/autosecure.html shows a different key in the
# same ConfigMap -- `enable-network-policy: "true"`, which the controller does not read -- and adds:
#   "It's also required to define the Network Policy support is configured in the Node Class, as
#    illustrated here:"
# followed by a NodeClass carrying `networkPolicy`/`networkPolicyEventLogs`. A second object to
# correlate is why what gets collected is the whole ConfigMap rather than a pre-digested boolean:
# `sec-4` reads `enable-network-policy-controller` out of this one file, and the NodeClass out of the next.
kjson_optional_doc "$WORK/vpccniconfig.json" '{}' configmap amazon-vpc-cni -n kube-system

# Auto Mode NodeClasses. https://docs.aws.amazon.com/eks/latest/userguide/create-node-class.html
# documents `spec.networkPolicy` ("networkPolicy: DefaultAllow  # or DefaultDeny") and, under
# `spec.advancedNetworking`:
#   "ipv4PrefixSize is default to Auto which is prefix and fallback to secondary IP. \"32\" is the
#    secondary IP mode."
# Both are defaults an operator may have overridden, and `sec-4` and `net-3` must read the value rather
# than assert the default. Cluster-scoped, so no `-A`. `{"items":[]}` when the CRD is absent, which is
# every cluster that is not in Auto Mode.
kjson_optional "$WORK/nodeclasses.json" nodeclasses.eks.amazonaws.com
awsjson "$WORK/sg.json"           -- aws ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/subnets.json"      -- aws ec2 describe-subnets         --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/nat.json"          -- aws ec2 describe-nat-gateways     --filter Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/routetables.json"  -- aws ec2 describe-route-tables    --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/vpcendpoints.json" -- aws ec2 describe-vpc-endpoints   --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
# ── EC2 INSTANCES AND VOLUMES: THE LIST APIs WENT BLIND ON EKS AUTO MODE ────────────────────────────
# One list-form call each is not enough. On an EKS Auto Mode cluster both return an empty set, and an
# empty-but-valid document passes every generic check this script makes -- so `lens-11` (IMDSv2), `sec-21`
# (EBS encryption) and `cost-8` (idle volumes), all weight 3, would silently become `na` with no error and no
# note in the report. `b()` renders a zero denominator as `na~0/0 IMDSv2`, which reads like a
# measurement rather than an absence, and `na` removes a question from the DENOMINATOR -- so the cluster
# nobody could see would score BETTER than one that was fully audited.
#
# https://docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html, "Managed resource
# visibility", verbatim:
#   "Beginning April 22, 2026, new Amazon EC2 managed instances and associated resources (for example,
#    EC2 launch templates, EBS volumes, and network interfaces (ENIs)) created by EKS Auto Mode are
#    hidden from EC2 console views and `describe` API list operations by default. Managed resources that
#    already existed in your account before that date remain visible."
# That date is past, so a review run today hits this by default on any Auto Mode cluster whose nodes
# were launched after it. The same page, verbatim, gives the ways through:
#   "Even when managed resources are hidden from EC2 console views and list APIs, you can still view EKS
#    Auto Mode instances through:" ... "Kubernetes APIs (for example, `kubectl get nodes`)." ...
#   "Direct EC2 API queries by instance ID (for example, `describe-instances --instance-ids
#    i-0123456789abcdef0`)." ... "The `DescribeInstances` API with the `include-managed-resources`
#    parameter."
# It also documents the account-wide setting that would restore the list APIs -- deliberately NOT used
# or suggested here: changing it is a write to an account setting, and this skill only ever looks.
#
# WHY NOT `--include-managed-resources`. The API parameter is real; the EC2 API Reference documents it
# on both operations, e.g.
# https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
#   "IncludeManagedResources: Indicates whether to include managed resources in the output. If this
#    parameter is set to `true`, the output includes resources that are managed by AWS services, even if
#    managed resource visibility is set to hidden."
# The CLI does not expose it yet. Tested 2026-09-11 against
# `aws-cli/2.34.30 Python/3.14.7 Darwin/25.6.0 source/arm64`:
#   $ aws ec2 describe-instances --include-managed-resources --max-items 1
#   aws: [ERROR]: Unknown options: --include-managed-resources
# A skill cannot dictate the operator's CLI version, so everything below is built on the instance-ID
# path, which works on every version. The negative result is recorded here rather than left as folklore:
# when a CLI ships the flag, this block can collapse to two calls, and a maintainer should be able to
# see why it is built the complicated way.
#
# HOW THE ID PATH WORKS.
#  - Instance IDs come from `nodes.json`, already collected above. `.spec.providerID` on an EC2-backed
#    node ends in the instance id, and on an Auto Mode node the node NAME is the instance id --
#    https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
#    "Lastly, Auto Mode nodes use the EC2 instance ID as the Kubernetes node name." Both are read and
#    only strings matching `^i-<hex>$` survive. That filter is load-bearing twice over: a Fargate
#    providerID is a different shape (`aws:///<az>/fargate-ip-<a>-<b>-<c>-<d>...`) and ONE unusable id fails
#    the whole `describe-instances` call, taking every good id down with it; and node objects are
#    cluster data rather than local input, so the anchored hex-only pattern is also what makes the
#    deliberately-unquoted `$batch` expansion below safe -- no surviving id can hold a space, a quote,
#    a semicolon or a glob character.
#  - Volume IDs come from the instances just collected (`BlockDeviceMappings[].Ebs.VolumeId`) and from
#    `pv.json` (`spec.csi.volumeHandle`, plus the legacy `spec.awsElasticBlockStore.volumeID`), keeping
#    only `^vol-<hex>$` -- an EFS volumeHandle (`fs-0123::fsap-4567`) must not reach `describe-volumes`
#    for the same all-or-nothing reason.
#  - The list call is KEPT and merged with, never replaced: it still finds cluster instances that are
#    not currently nodes -- a stopped instance, one that never joined, a leftover from a scaled-in
#    nodegroup -- which the id path cannot see because they are in nobody's `nodes.json`. Merging
#    dedupes by `InstanceId`/`VolumeId` and preserves `{"Reservations":[...]}` and `{"Volumes":[...]}`
#    exactly, because that is the shape the scorers read.
#
# THE RESIDUAL GAP, DISCLOSED RATHER THAN CLOSED. An Auto Mode EBS volume that is attached to nothing
# and backs no PersistentVolume has no id discoverable from `nodes.json` or `pv.json`, so it stays
# invisible and `cost-8` cannot count it. For NODE volumes that should not arise --
# https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
# says "On EKS Auto Mode nodes, the root and data Amazon EBS volumes are encrypted and configured to be
# deleted upon termination of the instance" -- but a volume created by something else and left behind
# can still hide. references/workflow.md tells the reader the same thing, because `cost-8` reporting no
# idle volumes on an Auto Mode cluster must not be read as proof that there are none.
# Second-order limit worth knowing: `cost-8` then scopes volumes by cluster TAG or PV volume id, so an
# ID-recovered volume that only a node attachment ties to the cluster is collected but not counted there
# (`sec-21` also counts one on an EC2 node of the cluster). Collection makes it visible; scorers scope.
#
# CHUNKING. The id form cannot be page-sized:
# https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html says of MaxResults
# "You cannot specify this parameter and the instance IDs parameter in the same request", while the same
# page warns "We strongly recommend using only paginated requests. Unpaginated requests are susceptible
# to throttling and timeouts." The only lever left is the length of the id list itself, so it is chunked
# -- which also keeps a several-hundred-node cluster's argv well clear of the OS argument limit.
EC2_ID_CHUNK=100

# ids_gone <id> : after an id-form call for <id> ALONE has failed, record <id> in $IDS_GONE when EC2's
# error says the id does not exist (a Node or PersistentVolume briefly outliving its instance or volume
# during a scale-in or a delete). The completeness canaries in the validation gate exempt exactly these
# ids and refuse on every other id that is missing from the merged file.
IDS_GONE=""
ids_gone() {
  printf '%s' "$IDS_CALL_ERR" | grep -qE 'Invalid(InstanceID|Volume)\.NotFound' && IDS_GONE="$IDS_GONE $1"
  return 0
}

# merge_instances / merge_volumes <base> <add> : <base> plus everything in <add> it does not already
# have, first occurrence winning. The list call's copy of an instance is therefore the one kept, and the
# output order is a pure function of the input order, which is what keeps two runs byte-identical.
# Each new instance stays inside its own reservation so `OwnerId`/`ReservationId` survive; a reservation
# left with no instances is dropped rather than emitted empty.
# The `.InstanceId as $id | ($have | index($id))` dance is not stylistic: inside `A | index(B)`, `B` is
# evaluated with `.` rebound to `A`, so the obvious `$have | index(.InstanceId)` reads `.InstanceId` off
# the ARRAY and dies with "Cannot index array with string". Bind the id before the pipe.
merge_instances() {
  jq -s '.[0] as $a | .[1] as $b
    | ([$a.Reservations[]?.Instances[]?.InstanceId] | map(select(. != null))) as $have
    | {Reservations: (($a.Reservations // [])
        + [ $b.Reservations[]?
            | .Instances = [ .Instances[]?
                             | select(.InstanceId as $id | ($have | index($id)) == null) ]
            | select((.Instances | length) > 0) ])}' "$1" "$2"
}
merge_volumes() {
  jq -s '.[0] as $a | .[1] as $b
    | ([$a.Volumes[]?.VolumeId] | map(select(. != null))) as $have
    | {Volumes: (($a.Volumes // [])
        + [ $b.Volumes[]? | select(.VolumeId as $id | ($have | index($id)) == null) ])}' "$1" "$2"
}

# augment_by_ids <target> <ec2-subcommand> <id-flag> <merge-fn> <count-jq> <id...> : top up <target>
# with id-form calls, in chunks, merging each chunk in as it arrives.
#
# BEST-EFFORT ON PURPOSE, and this is the one judgement call in the block. A hard error here would be
# indistinguishable from a denied list call -- which is already a refusal, since the list call above it
# uses `awsjson` -- and would make an id-path hiccup fatal on clusters that never needed the id path at
# all. What actually matters is whether every instance behind an EC2 node, and every volume id asked
# about, ended up in the MERGED file, and that is asserted per id by the canaries in the validation
# gate, which exempt only the ids EC2 reported as not existing (see ids_gone).
# So: warn here (with the reason, not just "failed"), refuse there.
#
# Writes through a dot-prefixed temp, like the Fargate merge above, because bash creates a redirect
# target before running the command: a plain `> "$WORK/x.json"` on a denied call leaves a 0-byte
# x.json that the gate's `*.json` scan then rejects, discarding an otherwise complete collection.
# A leading dot keeps the temp out of that glob, which is why it can be left in place either way.

# ids_call <target> <ec2-subcommand> <id-flag> <merge-fn> <id...> : one id-form call, merged on success.
# Returns 0 on merge, 1 on anything else, and leaves $IDS_CALL_ERR set to the first stderr line so the
# caller can decide whether the failure is worth splitting up.
ids_call() {
  local target="$1" sub="$2" flag="$3" mergefn="$4"; shift 4
  local base tmp merged rc=1
  base=$(basename "$target" .json); tmp="$WORK/.$base-add.json"; merged="$WORK/.$base-merged.json"
  IDS_CALL_ERR=""
  # "$@" is expanded unquoted-per-word by the caller; here each id is already its own parameter, so
  # "$@" is correct and no re-splitting happens.
  if aws ec2 "$sub" "$flag" "$@" --region "$REGION" --output json >"$tmp" 2>"$tmp.err" \
     && jq -e . "$tmp" >/dev/null 2>&1; then
    if "$mergefn" "$target" "$tmp" >"$merged" && jq -e . "$merged" >/dev/null 2>&1; then
      mv "$merged" "$target"; rc=0
    else
      IDS_CALL_ERR="could not merge the response into $base.json"
    fi
  else
    IDS_CALL_ERR="$(firstline "$tmp.err")"
  fi
  # $tmp, $tmp.err and $merged are left in place: dot-names, and each call truncates them before reading.
  return "$rc"
}

augment_by_ids() {
  local target="$1" sub="$2" flag="$3" mergefn="$4" cexpr="$5"; shift 5
  local base batch id one
  local n=0 i=0 calls=0 fails=0 total=$# before after
  base=$(basename "$target" .json)
  [ "$total" -gt 0 ] || return 0
  before=$(jq "$cexpr" "$target" 2>/dev/null || echo 0)
  batch=""
  for id in "$@"; do
    batch="$batch $id"; n=$((n+1)); i=$((i+1))
    if [ "$n" -ge "$EC2_ID_CHUNK" ] || [ "$i" -eq "$total" ]; then
      calls=$((calls+1))
      # $batch is intentionally unquoted: it must word-split into one argv element per id. Safe only
      # because every id was matched against an anchored hex-only pattern before it got here.
      if ! ids_call "$target" "$sub" "$flag" "$mergefn" $batch; then
        echo "WARN: aws ec2 $sub $flag (chunk $calls, $n id(s)) returned no usable data:" \
             "$IDS_CALL_ERR" >&2
        fails=$((fails+1))
        [ "$n" -eq 1 ] && ids_gone $batch
        # ONE unusable id fails the whole call and takes every good id with it. The realistic cause is
        # not a bug but a race: a Node object briefly outlives its instance during a scale-in, so its
        # id is gone by the time this runs -- and on an Auto Mode cluster, where the list call
        # contributes nothing, that single stale id would otherwise empty the file and make the
        # validation gate refuse a review of a perfectly healthy cluster. So when EC2 says an id is the
        # problem, retry the chunk one id at a time and keep the ones that resolve. Gated on the error
        # naming an id, deliberately: a throttle or a denial applies to every id equally and re-asking
        # per id would just multiply it.
        if [ "$n" -gt 1 ] && printf '%s' "$IDS_CALL_ERR" \
             | grep -qE 'Invalid(InstanceID|Volume|ParameterValue)'; then
          echo "      retrying those $n id(s) individually -- EC2 named an id, so the rest may be fine" >&2
          for one in $batch; do
            calls=$((calls+1))
            ids_call "$target" "$sub" "$flag" "$mergefn" "$one" || { fails=$((fails+1)); ids_gone "$one"; }
          done
        fi
      fi
      batch=""; n=0
    fi
  done
  after=$(jq "$cexpr" "$target" 2>/dev/null || echo 0)
  echo "OK: $base.json: $before from the list call, $((after - before)) added by $flag" \
       "($total id(s), $calls call(s), $fails of them failed)"
}

awsjson "$WORK/instances.json"    -- aws ec2 describe-instances       --filters Name=tag:kubernetes.io/cluster/"$CLUSTER",Values=owned,shared --region "$REGION" --output json
# Only augment a file the list call actually produced. If that call hard-failed, COLLECT_ERRORS is
# already set and the gate will refuse; writing this file from the id path alone would convert a
# refusal into a partial answer nobody asked for.
if [ -f "$WORK/instances.json" ]; then
  # `select(. != "")` before `split` is not defensive padding: `"" | split("/")` is `[]`, `last` on that
  # is null, and `test` on null aborts the whole program -- which would leave $NODE_IIDS empty and skip
  # the id path in silence, the exact failure mode this section exists to remove. A node with no
  # `providerID` at all reaches that path, which is why the filter stays.
  NODE_IIDS=$(jq -r '[ .items[]? | (.spec.providerID // ""), (.metadata.name // "") ]
                     | map(select(type == "string" and . != "") | split("/") | last)
                     | map(select(test("^i-[0-9a-f]{8,}$")))
                     | unique | .[]' "$WORK/nodes.json" 2>/dev/null)
  # Unquoted on purpose (word-splitting into separate ids); see augment_by_ids.
  augment_by_ids "$WORK/instances.json" describe-instances --instance-ids merge_instances \
                 '[.Reservations[]?.Instances[]?] | length' $NODE_IIDS
fi

awsjson "$WORK/volumes.json"      -- aws ec2 describe-volumes         --region "$REGION" --output json
if [ -f "$WORK/volumes.json" ]; then
  # Derived AFTER the instance merge above, so an Auto Mode node recovered by id also contributes its
  # root and data volume ids here. https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
  # on VolumeId.N: "The volume IDs. If not specified, then all volumes are included in the response."
  VOL_IDS=$(jq -rs '[ (.[0] | .Reservations[]?.Instances[]?.BlockDeviceMappings[]?.Ebs.VolumeId?),
                      (.[1] | .items[]? | (.spec.csi.volumeHandle?, .spec.awsElasticBlockStore.volumeID?)) ]
                    | map(select(type == "string" and . != "") | split("/") | last)
                    | map(select(test("^vol-[0-9a-f]{8,}$")))
                    | unique | .[]' "$WORK/instances.json" "$WORK/pv.json" 2>/dev/null)
  augment_by_ids "$WORK/volumes.json" describe-volumes --volume-ids merge_volumes \
                 '[.Volumes[]?] | length' $VOL_IDS
fi
awsjson "$WORK/ecr.json"          -- aws ecr describe-repositories    --region "$REGION" --output json
awsjson "$WORK/cloudtrail.json"   -- aws cloudtrail describe-trails   --region "$REGION" --output json
INVALID=""
for f in "$WORK"/*.json; do
  [ -L "$f" ] && continue                                   # skip the two symlink aliases
  jq -e . "$f" >/dev/null 2>&1 || INVALID="$INVALID $(basename "$f")"
done

# Every file a scorer reads MUST exist and parse. A file that was never collected
# is indistinguishable from "the cluster has none of these" once scoring starts,
# which silently pins the dependent questions to "none" and deflates the score.
# Listing them explicitly is what makes an un-run collection command a hard error.
REQUIRED="cluster nodegroups addons fargate podidentity oidcproviders nodes pods
deployments statefulsets daemonsets services ingresses networkpolicies hpa pdb
namespaces serviceaccounts clusterroles clusterrolebindings rolebindings
storageclasses pv pvc resourcequotas limitranges cronjobs jobs
validatingwebhookconfigurations mutatingwebhookconfigurations sg subnets nat
routetables vpcendpoints instances volumes ecr cloudtrail insights"
for r in $REQUIRED; do
  [ -f "$WORK/$r.json" ] || { INVALID="$INVALID $r.json(NOT COLLECTED)"; continue; }
  jq -e . "$WORK/$r.json" >/dev/null 2>&1 || INVALID="$INVALID $r.json(unparseable)"
done
# The Kyverno/Gatekeeper CRDs and the Fargate log-router ConfigMap are the only legitimately-EMPTY
# files, but each must still exist as valid JSON so the scorers can read it. awslogging is here and
# not in REQUIRED because the ConfigMap is genuinely absent on most clusters — but absent-as-an-object
# and absent-as-a-file are different things: fargate-4 reads it through m3, which ABORTS the whole
# Operational Excellence block on an unopenable input. score.sh fails loudly on that -- the block
# exits 1 and score.sh prints "do NOT score from a partial results.jsonl" -- so the danger is not a
# silent pipeline, it is an operator who reduces anyway. Do that and NOTHING PUBLISHED MOVES IN A
# DIRECTION THAT READS AS DAMAGE. The block dies at fargate-4, so every record from there on vanishes
# -- measured fargate-4, lens-1 and lens-7, and governance ope-19, which sits after them in the block
# -- and both the measured and the process denominators shrink by those records.
# The HEADLINE COVERAGE FIGURE (reduce.sh's `coverage` field, the
# one the chat summary prints from the `jq -r` block under SKILL.md's "Step 7 -- Reduce to scores",
# cited by NAME and not by line, because a line number in a comment is a fact about a file that
# keeps being edited --
# NOT the HTML coverage cell, which is a different
# number under the same word) moves only slightly, nowhere near the 50% gate. The
# Operational Excellence score can go UP, because the lost questions may include failures, and
# the overall headline can hold. The only reader-visible trace is a cell that SHRINKS -- its
# denominator drops, and so does the "N process question(s) not assessed" note beneath it -- and a
# reader with no baseline report to compare against cannot tell a shrunken denominator from a small
# cluster. That is the exact failure this gate exists to prevent, and it is reachable whenever
# a newly-collected file is added to neither list.
for r in kyverno constraints constrainttemplates awslogging awsauth fargateprofiles \
         vpccniconfig nodeclasses; do
  [ -f "$WORK/$r.json" ] && jq -e . "$WORK/$r.json" >/dev/null 2>&1 \
    || INVALID="$INVALID $r.json(missing/unparseable; write '{\"items\":[]}' if the CRD is absent)"
done

# ── COLLECTION-GAP CANARIES: instances.json and volumes.json may NOT be silently empty ──────────────
# Neither file is in the may-be-empty list above, and references/workflow.md says the same in prose, so
# the rule and the code cannot drift. An empty `instances.json` on a cluster whose nodes ARE EC2
# instances is not a finding, it is the blind list API described in the Auto Mode note further up: the
# id path above exists to repair it, and when the repair does not land, this refuses instead of
# publishing `na~0/0 IMDSv2`. Recorded through $INVALID -- the same not-collected mechanism the REQUIRED
# loop uses -- so this script still has exactly one way of refusing.
if [ -f "$WORK/nodes.json" ] && [ -f "$WORK/instances.json" ]; then
  # "EC2 node" = a node backed by an EC2 instance, i.e. neither Fargate NOR an EKS Hybrid node. Fargate
  # nodes carry `eks.amazonaws.com/compute-type=fargate`; EKS Hybrid nodes carry an `eks-hybrid:///`
  # providerID and `eks.amazonaws.com/compute-type=hybrid`. NEITHER is backed by an EC2 instance, so a
  # Fargate-only or hybrid-only cluster legitimately has zero instances and must not trip this. Counting
  # hybrid nodes as EC2 would make this canary fire on every hybrid-only cluster and refuse the run with
  # "EKS Auto Mode hides managed instances from list APIs" -- a cause that has nothing to do with the
  # cluster in front of it -- while the SCOPE-PLATFORMS block in references/workflow.md says such a cluster is "not
  # refused".
  #
  # THIS IS `isec2`, CHARACTER FOR CHARACTER, not a second expression that happens to agree today. The
  # scorers carry `ishy`/`isec2` in the shared `B='def b(...)'` prelude of all five reference blocks; if
  # this test and `isec2` disagree, a cluster whose collection is accepted here gets its node population
  # partitioned differently two steps later. A disagreement matters most in one direction:
  #
  #   * `ishy` is NOT the label OR the providerID. The providerID DECIDES and the label only breaks a
  #     tie -- an `aws:` providerID VETOES the label, because the providerID is written by nodeadm while
  #     the label is an ordinary label anyone with node-patch RBAC can set. OR-ing them here would make
  #     `providerID = aws:///...` plus `compute-type=hybrid` read as "not an EC2 node" HERE and as an
  #     EC2 node IN THE SCORERS. A fleet of real EC2 instances mislabelled hybrid would then pass
  #     collection with an empty instances.json and be scored as EC2 with no instance data --
  #     exactly the hole this canary exists to close. (Same evasion as the `lens-14 some -> all` one
  #     render-report.py documents.)
  #   * `test()` on a NON-STRING providerID is a jq error, not false, and a `2>/dev/null || echo 0`
  #     fallback would turn that into "no EC2 nodes" -- i.e. a malformed providerID would DISARM the
  #     canary. `| tostring` is why the prelude has it too.
  #
  # There is no `/fargate-` providerID signal here: keeping one would make this canary's EC2 set a strict
  # SUBSET of the scorers' on a Fargate node whose label was missing, and a canary whose population is
  # smaller than the one that gets scored is a canary that can be walked past. A label-less Fargate node
  # counts as EC2 here, which is exactly what the scorers do with it, so the refusal is correct.
  # `.items[]?` would make the could-not-run arm below unreachable: safe navigation turns "this file
  # is not a node list" into "the list is empty", CANARY_OK stays 1, and `{}`, `{"items":3}` and a
  # `{"kind":"Status","status":"Failure"}` RBAC envelope all print "Safe to score". Dropping the `?`
  # alone is NOT enough, which is why this is a type test and not `.items[]`: jq ITERATES AN OBJECT, so
  # `{"items":{}}` counts zero through a bare `.items[]` and slips past the same way.
  # reduce.sh gets away with a bare `.items[]` only because its own `has("items") and
  # (.items|type=="array")` gate has already proved the key is an array; there is no such gate here, so
  # the assertion has to live in the counting expression itself.
  # One entry per EC2 node: its instance id (from the providerID, else the node name, exactly as the id
  # path above derives them), or "" when neither yields one. The count of entries is EC2_NODES; the ids
  # are what the per-id completeness arm below checks against instances.json.
  EC2_NODE_IIDS=$(jq -c '[ (.items | if type=="array" then .[] else error("nodes.json has no .items array") end)
                    | ((.spec.providerID? // "") | tostring) as $p
                    | (if   ($p | test("^eks-hybrid:")) then true
                       elif ($p | test("^aws:"))        then false
                       else ((.metadata.labels["eks.amazonaws.com/compute-type"] // "") == "hybrid")
                       end) as $hy
                    | select((((.metadata.labels["eks.amazonaws.com/compute-type"] // "") != "fargate")
                              and ($hy | not)))
                    | ([$p, ((.metadata.name? // "") | tostring)]
                       | map(split("/") | last // "") | map(select(test("^i-[0-9a-f]{8,}$"))) | first // "") ]' \
                  "$WORK/nodes.json" 2>/dev/null) || EC2_NODE_IIDS=
  EC2_NODES=$(printf '%s' "$EC2_NODE_IIDS" | jq 'if type=="array" then length else error("not an array") end' 2>/dev/null) \
    || EC2_NODES=
  # Same shape, same reason: `.Reservations[]?` would let `{"Reservations":7}` count zero instances and
  # fire the WRONG arm -- the Auto Mode "zero EC2 instances" diagnosis, about a cluster fault that is not
  # there -- instead of the could-not-run one. `{"Reservations":{}}` needs the type test for the same
  # object-iteration reason as `.items` above. `.Instances` gets the SAME test and not a `?`, because
  # `{"Reservations":[{"Instances":3}]}` and `[{"Instances":{}}]` would count zero the
  # same way -- wrong Auto Mode cause on a cluster with EC2 nodes, silent "Safe to score" on one without.
  # A THIRD SPELLING HERE WOULD BE ITS OWN DEFECT: all three counts must fail the same way or the next
  # reader has to work out which of them refuses. `[]` and zero Reservations stay legal and are the only
  # legitimate empties there are -- merge_instances above ASSIGNS `.Instances = [ ... ]` on every
  # reservation it merges and drops any left empty, and describe-instances always returns the member, so
  # an absent or non-array `.Instances` is a malformed file and not a cluster with nothing running.
  INST_TOTAL=$(jq '[ (.Reservations | if type=="array" then .[] else error("instances.json has no .Reservations array") end)
                     | (.Instances   | if type=="array" then .[]
                                       else error("a Reservation in instances.json has no .Instances array") end)
                   ] | length' "$WORK/instances.json" 2>/dev/null) || INST_TOTAL=
  # A CANARY THAT CANNOT COUNT MUST REFUSE, NOT COUNT ZERO. Ending these with `|| echo 0` would turn any
  # jq failure -- a `.metadata` that is not an object, a `.Reservations` that is not an array, a truncated
  # file -- into "no EC2 nodes" and the canary would wave the collection through. That is the same
  # cannot-run-so-it-passed shape reduce.sh guards against, and it is the
  # only failure mode a canary must not have. The `case` is a numeric test written without `-gt`: `[ x
  # -gt 0 ]` on a non-numeric value is a shell error, not false, so the guard would need a guard.
  # `${VAR:-x}` and not `${VAR:-0}`: an EMPTY value is a failed count, not zero nodes, and substituting
  # `x` makes it fail the digit test alongside `null`, `jq: error ...` and a truncated number.
  CANARY_OK=1
  case "${EC2_NODES:-x}"  in *[!0-9]*) CANARY_OK=0 ;; esac
  case "${INST_TOTAL:-x}" in *[!0-9]*) CANARY_OK=0 ;; esac
  # A PARTIAL file passes a zero test: one throttled id chunk, or a mixed cluster whose list call returns
  # only the tagged node-group instances, leaves some EC2 nodes with no instance while the total is not
  # zero, and lens-11/sec-21/cost-8 would then grade the subset as if it were the fleet. So every EC2
  # node's instance id must be in the merged file, except the ids EC2 itself said do not exist.
  MISSING_IIDS=""
  if [ "$CANARY_OK" = 1 ]; then
    MISSING_IIDS=$(printf '%s' "$EC2_NODE_IIDS" | jq -r --arg gone "$IDS_GONE" \
                      --slurpfile inst "$WORK/instances.json" '
        . as $want
        | [ $inst[0].Reservations[].Instances[].InstanceId ] as $have
        | [ $gone | splits("[ ]+") | select(. != "") ] as $g
        | [ $want[] | select(. != "") ] | unique
        | map(select(. as $id | ($have | index($id)) == null and ($g | index($id)) == null))
        | join(" ")' 2>/dev/null) || CANARY_OK=0
  fi
  if [ "$CANARY_OK" = 0 ]; then
    INVALID="$INVALID nodes.json+instances.json(THE EC2-NODE CANARY COULD NOT RUN: counting EC2 nodes"
    INVALID="$INVALID or EC2 instances did not produce a number, so whether instances.json is complete"
    INVALID="$INVALID was NOT checked -- do not read this as a pass; re-collect both files)"
  elif [ "$EC2_NODES" -gt 0 ] && [ "$INST_TOTAL" -eq 0 ]; then
    INVALID="$INVALID instances.json(NOT COLLECTED: ${EC2_NODES} EC2 node(s) in nodes.json but"
    INVALID="$INVALID zero EC2 instances -- EKS Auto Mode hides managed instances from list APIs and the"
    INVALID="$INVALID instance-id fallback also came back empty; lens-11/sec-21/cost-8 would score 0/0)"
  elif [ -n "$MISSING_IIDS" ]; then
    _nm=0; for _i in $MISSING_IIDS; do _nm=$((_nm+1)); done
    INVALID="$INVALID instances.json(INCOMPLETE: ${_nm} of the ${EC2_NODES} EC2 node(s) in nodes.json have no"
    INVALID="$INVALID instance in instances.json -- the describe-instances --instance-ids lookup for them"
    INVALID="$INVALID failed (see the WARN line(s) above); lens-11/sec-21/cost-8 would grade a subset)"
  fi
fi
if [ -f "$WORK/volumes.json" ] && [ -f "$WORK/instances.json" ] && [ -f "$WORK/pv.json" ]; then
  # $VOL_IDS is exactly the set of ids the id path asked about -- block devices on the collected
  # instances plus PV volume handles -- so counting it needs no second, drifting expression. It is also
  # deliberately shape-based rather than driver-based: EKS Auto Mode's CSI driver is
  # `ebs.csi.eks.amazonaws.com`, not `ebs.csi.aws.com`, so a `.spec.csi.driver ==` test would be blind
  # to exactly the clusters this canary exists for, while a `vol-…` volumeHandle is an EBS volume under
  # any driver name.
  # Checked id by id against volumes.json, NOT against its length: the list call is unfiltered and
  # returns every volume in the account and region, so any unrelated volume would make a length test
  # pass while the cluster's own volumes are missing. Ids EC2 reported as not existing are exempt.
  EBS_EXPECTED=0
  for v in ${VOL_IDS:-}; do EBS_EXPECTED=$((EBS_EXPECTED+1)); done
  MISSING_VOLS=$(printf '%s\n' "${VOL_IDS:-}" | jq -Rrn --arg gone "$IDS_GONE" \
                    --slurpfile vols "$WORK/volumes.json" '
      [ inputs | splits("[ \t]+") | select(. != "") ] as $w
      | ($vols[0].Volumes | if type=="array" then [ .[].VolumeId ] else error("volumes.json has no .Volumes array") end) as $have
      | [ $gone | splits("[ ]+") | select(. != "") ] as $g
      | $w | unique
      | map(select(. as $id | ($have | index($id)) == null and ($g | index($id)) == null))
      | join(" ")' 2>/dev/null) || MISSING_VOLS="?"
  if [ "$MISSING_VOLS" = "?" ]; then
    INVALID="$INVALID volumes.json(THE VOLUME CANARY COULD NOT RUN: volumes.json could not be read as a"
    INVALID="$INVALID volume list, so whether it holds the cluster's volumes was NOT checked; re-collect it)"
  elif [ -n "$MISSING_VOLS" ]; then
    _nm=0; for _v in $MISSING_VOLS; do _nm=$((_nm+1)); done
    INVALID="$INVALID volumes.json(INCOMPLETE: ${_nm} of the ${EBS_EXPECTED} EBS volume id(s) referenced by the"
    INVALID="$INVALID collected instances or PersistentVolumes are not in it -- the describe-volumes"
    INVALID="$INVALID --volume-ids lookup for them failed (see the WARN line(s) above; EKS Auto Mode hides"
    INVALID="$INVALID its volumes from the list call); sec-21/cost-8 would grade a subset)"
  fi
fi

# ── COLLECTION-GAP CANARY: one merged detail per ADD-ON NAME ─────────────────────────────────────────
# `lens-7` reads `.addonDetails[]` to get
# vpc-cni's version, status and health, so a name in `.addons` with no matching detail leaves
# `addons.json` valid and complete-looking while `lens-7` answers `most` ("its detail was not collected")
# for a High-visibility add-on nobody looked at. Without this check `addons: N / addonDetails: N-1` passes
# under an "OK ... Safe to score." Covers a denial, a throttle and a failed merge alike. Zero names and zero
# details is the legitimate empty and passes.
# `.addonTargets` is deliberately NOT checked here -- see the awsjson_detail header: `lens-7` has an
# honest "currency was not assessed" arm for that one, so a gap degrades the verdict instead of faking it.
if [ -f "$WORK/addons.json" ]; then
  AD_NAMES=$(jq '(.addons//[])|length' "$WORK/addons.json" 2>/dev/null || echo 0)
  AD_DETAIL=$(jq '(.addonDetails//[])|length' "$WORK/addons.json" 2>/dev/null || echo -1)
  if [ "${AD_NAMES:-0}" -ne "${AD_DETAIL:--1}" ]; then
    INVALID="$INVALID addons.json(NOT COLLECTED: ${AD_NAMES} add-on name(s) but ${AD_DETAIL} merged"
    INVALID="$INVALID describe-addon detail(s) -- lens-7 would report vpc-cni's version, status and"
    INVALID="$INVALID health as not collected, or score it off a blind API)"
  fi
fi

# semantic canaries that catch a silent auth/throttle failure the per-call checks might miss
[ -n "$(jq -r '.cluster.version // empty' "$WORK/cluster.json" 2>/dev/null)" ] \
  || INVALID="$INVALID cluster.json(no .cluster.version)"
[ "$(jq '.items|length' "$WORK/namespaces.json" 2>/dev/null || echo 0)" -gt 0 ] \
  || INVALID="$INVALID namespaces.json(empty→cluster unreachable?)"

if [ "$COLLECT_ERRORS" -gt 0 ] || [ -n "$INVALID" ]; then
  echo "COLLECTION FAILED — do NOT score this data." >&2
  [ "$COLLECT_ERRORS" -gt 0 ] && echo "  $COLLECT_ERRORS hard collection error(s) reported above (auth / throttle / permission)." >&2
  [ -n "$INVALID" ] && echo "  invalid or empty:$INVALID" >&2
  [ "$COLLECT_ERRORS" -gt 0 ] && echo "  For the errors: fix credentials/connectivity/permissions (e.g. re-run 'aws eks update-kubeconfig'," >&2
  [ "$COLLECT_ERRORS" -gt 0 ] && echo "  check the profile/region), or wait out a throttle." >&2
  [ -n "$INVALID" ] && echo "  Every *.json in the work directory must be valid JSON (not null/false), so a listed name this" >&2
  [ -n "$INVALID" ] && echo "  collector does not write is a file that was already there, not a collection failure: keep it" >&2
  [ -n "$INVALID" ] && echo "  out of the work directory." >&2
  [ -n "$INVALID" ] && echo "  Every other listed file failed to collect completely." >&2
  if [ -f "$WORK/cluster.json" ]; then
    echo "  Then re-run collect.sh with a NEW --work directory (or move this one aside): this one now holds" >&2
    echo "  cluster.json, and collect.sh refuses to collect on top of an earlier run." >&2
  else
    echo "  Then re-run collect.sh." >&2
  fi
  echo "  Scoring against this data would be incorrect." >&2
  exit 1
fi

# ── COLLECTION FINGERPRINT: the provenance record the scorer and the renderer both assert ────────────
# Written ONLY here, ONLY after the gate above passed, and read by assets/reduce.sh and
# assets/render-report.py before either publishes a number. It carries three things:
#
#   collected_at  ONE UTC ISO-8601 instant: the wall clock AT COLLECTION. This is the report's
#                 "Data collected" line, and it is DATA -- a fact about when the cluster was read --
#                 not a clock the report layer looks at later. It is deliberately not the results.jsonl
#                 MTIME, which is a fact about a filesystem and not about a cluster: `cp -r`, `tar -x`, `git
#                 checkout`, a re-score, or a bare `touch` all rewrite it, so a work dir moved between
#                 machines would publish a collection date nobody had collected on. `touch -t 209901011230
#                 results.jsonl` would be enough to make the report claim a 2099 collection, under a
#                 masthead that says "Scores describe configuration at collection time".
#   cluster/region  As COLLECTED. A cluster NAME and a region are already printed in the report, so
#                 this adds no identifier that was not customer-visible -- and no account id, ARN,
#                 endpoint, subnet, security-group, instance or volume id appears here at all.
#   files/digest  the NAMES of the files this collection wrote, each with the sha256 of its content,
#                 plus one digest over that whole list -- so a later stage can prove it is reading the
#                 same bytes that were scored, rather than a work dir that has moved on.
#
# WHAT IT COVERS, AND WHAT IT DOES NOT. It covers the COLLECTED INPUT: the files listed in `files`, by
# content. It does NOT cover `results.jsonl`, and must not -- the scorers append to that file after this
# line runs, so any digest over it would be stale the moment scoring began. So the fingerprint says
# nothing about whether the emitted RECORDS are consistent with the data; that is the state<->ratio
# gate's job in reduce.sh. The two are complementary, not redundant: this one answers "is this the data
# that was collected, and when", that one answers "does each record's verdict follow from its own
# ratio". Neither substitutes for the other, and a reader who assumes "fingerprint" means "everything in
# the work dir is vouched for" is wrong in both directions.
#
# WHY A COLLECTION TIMESTAMP DOES NOT BREAK DETERMINISM -- two collections of the same fixture must
# produce BYTE-IDENTICAL results.jsonl and scores.json. Nothing asserts that
# automatically, so the property below is maintained BY HAND and
# the argument is written out in full precisely so it can be re-checked by reading.
# The instant lives in THIS FILE and nowhere else. It is not an input to the digest (which is over file
# bytes only), no scorer reads it, and reduce.sh copies no field of this file into scores.json -- it
# only compares. So two collections a minute apart differ in `.collection.json`'s `collected_at`, which
# is the one place a collection instant belongs, and in nothing determinism is asserted on. A digest
# with the timestamp folded in, or a timestamp copied into scores.json, is what would break
# that property; the fingerprint file is deliberately not one of the artifacts compared across runs.
#
# The digest is a hash OF HASHES with the file NAMES included, not one hash over a concatenation: that
# way a collected file disappearing or being renamed is caught as well as one being edited, and the
# asserting stage can name WHICH file moved instead of only reporting that something did.
#
# AN ALLOWLIST OF WHAT WAS COLLECTED, NOT A DENYLIST OF WHAT IS IN THE DIRECTORY. The verifiers walk the
# `files` map -- the names THIS collection wrote -- and hash exactly those. They do not re-glob the work
# dir. Two reasons:
#   * A caller may legitimately create a file in $WORK. `reduce.sh "$WORK" > "$WORK/out.json"` is the
#     obvious one, and the shell creates that redirect target BEFORE reduce.sh runs, so a glob-based
#     digest would see `out.json: added since collection` and refuse a completely correct run. Requiring
#     callers to know that `scores.json` is the one blessed output filename is not a contract, it is a
#     trap; the same trap catches anyone dropping a debug dump beside the data.
#   * An allowlist cannot be silently widened. A denylist grows an exemption every time a new output
#     file appears next to the data, and each exemption is a name whose content nothing then checks.
# What an allowlist gives up is noticing an UNEXPECTED extra file, and that costs nothing here: every
# file any scorer or the renderer reads is one this collector wrote (that is what the REQUIRED gate
# above enforces), so a name outside the map is a name nothing scored from.
#
# THREE IMPLEMENTATIONS, ONE DEFINITION -- KEEP THEM BYTE-COMPATIBLE. This file (bash) computes the
# digest below at collection time; assets/reduce.sh (bash) and assets/render-report.py (python) both
# recompute exactly this:
#
#   for each name in the fingerprint's `files`, LC_ALL=C sorted:  "<name>  <sha256 hex>\n"
#     (a listed name that is no longer a readable file contributes NO line, which both fails the
#      digest and lets the verifier report it as "removed since collection")
#   digest = sha256 hex of that concatenation
#
# At collection time the list is every `*.json` in $WORK. That is not quite "everything this script
# wrote", and the difference is worth stating rather than glossing: the work-directory guard refuses any
# EARLIER COLLECTION, but it deliberately does not refuse a non-empty directory, so an operator's own
# unrelated `something.json` sitting beside the collection WILL be fingerprinted. The error that causes
# is one-directional and safe -- editing that file makes the render refuse ("changed since collection")
# rather than letting a changed collection through -- so the fingerprint is over-inclusive, never
# under-inclusive, which is the direction a provenance check must fail in. `scores.json` does not exist
# yet (the reducer that asserts this writes it), `results.jsonl` is not matched by the glob, and neither
# is any dot-file -- this one or `.not-collected` -- because a bash `*` glob does not match a leading dot.
# NOTE for the python side: `pathlib.glob("*.json")` DOES match dot-files, so anywhere it globs the work
# dir it must exclude this file by name; verified on 3.9, not assumed.
sha256_hex() {   # sha256_hex [file] -- hex digest of <file>, or of stdin when called with no argument
  if command -v sha256sum >/dev/null 2>&1;  then sha256sum   ${1+"$1"} | cut -d' ' -f1
  elif command -v shasum   >/dev/null 2>&1; then shasum -a 256 ${1+"$1"} | cut -d' ' -f1
  else openssl dgst -sha256 ${1+"$1"} | sed 's/^.*= *//'; fi
}
collection_lines() {   # <workdir> < <names, one per line>  ->  "<name>  <hex>", LC_ALL=C sorted
  local d="$1" n
  while IFS= read -r n; do
    [ -n "$n" ] || continue
    [ -f "$d/$n" ] || continue          # listed but gone: no line, so the digest cannot match
    printf '%s  %s\n' "$n" "$(sha256_hex < "$d/$n")"   # stdin: a named FILE with a \ in its path gets a \-prefixed hash line
  done | LC_ALL=C sort
}
collected_names() {    # <workdir> -> the names this collection wrote, one per line
  local d="$1" f b
  for f in "$d"/*.json; do
    [ -f "$f" ] || continue
    b=$(basename "$f")
    # NOT belt-and-braces: nothing at the top removes a stray scores.json, because this script
    # deletes nothing at all. scores.json is
    # written later by reduce.sh and never by this script, so a stray one (an earlier run's, left in a
    # directory the previous-collection guard did not refuse) must not be fingerprinted as collected data.
    [ "$b" = "scores.json" ] && continue
    printf '%s\n' "$b"
  done
}
FP_LINES=$(collected_names "$WORK" | collection_lines "$WORK")
[ -n "$FP_LINES" ] || { echo "collect.sh: no collected *.json in $WORK to fingerprint -- refusing." >&2; exit 1; }
FP_DIGEST=$(printf '%s\n' "$FP_LINES" | sha256_hex)
FP_STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# Built with jq rather than printf, for the same reason the scorers' emit() is: a hand-built JSON
# string is one unescaped character away from a document that parses as something else. Every value
# here arrives through --arg, and the files map is derived from the same lines the digest was taken
# over, so the file cannot describe a different set than the digest covers.
printf '%s\n' "$FP_LINES" | jq -Rs \
    --arg at "$FP_STAMP" --arg cluster "$CLUSTER" --arg region "$REGION" --arg digest "$FP_DIGEST" '
    { fingerprint: 1, collected_at: $at, cluster: $cluster, region: $region, digest: $digest,
      files: (split("\n") | map(select(length > 0) | split("  ") | {key: .[0], value: .[1]})
              | from_entries) }' > "$WORK/.collection.json.tmp" \
  && jq -e '(.digest|length)==64 and (.collected_at|length)>0 and (.files|length)>0' \
       "$WORK/.collection.json.tmp" >/dev/null 2>&1 \
  && mv "$WORK/.collection.json.tmp" "$WORK/.collection.json" \
  || { # .collection.json.tmp is left in place: every reader opens `.collection.json` by that exact name.
       echo "ERROR: could not write the collection fingerprint $WORK/.collection.json." >&2
       echo "  assets/reduce.sh and assets/render-report.py both REFUSE without it, so a collection" >&2
       echo "  that cannot record its own provenance is a failed collection, not a warning." >&2
       exit 1; }
echo "OK: fingerprint $WORK/.collection.json — $(printf '%s\n' "$FP_LINES" | wc -l | tr -d ' ') file(s), collected_at $FP_STAMP"
echo "OK: $(ls "$WORK"/*.json | wc -l | tr -d ' ') files collected and validated. Safe to score."
