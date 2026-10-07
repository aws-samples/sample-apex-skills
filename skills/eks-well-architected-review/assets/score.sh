#!/usr/bin/env bash
# Run ONE pillar's scorer block against a collected work dir.
#
# Usage:
#   export CLUSTER=<name> REGION=<region>            # not read here; kept for symmetry with collect.sh
#   ${CLAUDE_SKILL_DIR}/assets/score.sh <pillar> <workdir>
#
#   <pillar> is one of: operational-excellence | security | reliability |
#                       performance-efficiency | cost-optimization
#
# WHY THIS IS A SCRIPT AND NOT "PASTE THE FENCED BLOCK".
# The detections live in the reference files -- this script does not copy them, it extracts and
# runs the same block a reader sees. What it removes is the paste.
#
#  1. A tool-permission allowlist cannot match the pasted form. Each pillar block defines shell
#     FUNCTIONS (`emit`, `g`, `rl`, `m`, `m2`, `m3`, `m4`, `m5`, `m6`, `m7` -- not every block defines
#     every one) and then calls them 198 times across the five blocks: 103 `m`-family, 29 `g`, 66 `rl`.
#     To count them, FROM THE SKILL ROOT (not from here -- these globs are relative to it):
#       grep -hE '^(m[0-9]*|g|rl) ' references/*.md references/*/*.md | wc -l
#     (`wc -l`, not `grep -c`: over a glob `grep -c` prints one count per file, never the total.) Called as
#     `m sec-1 cluster '...'`. A Bash permission rule matches literal command text, so no rule can ever
#     match a shell-function name: every one of those calls, and the bare `B='...'` / `W="$WORK"`
#     assignments, falls through to the normal permission flow -- prompting interactively and HARD-DENIED
#     under a no-prompt policy, which means an unattended run cannot reach a score at all. This is the
#     same wrapper-function problem that collect.sh solves for collection; this script solves it for the
#     scoring half. One grant per invocation of this script matches all of it.
#
#  2. One path for testing and for a real run. Extracting the fenced block with awk here is the only
#     way a review run executes it; a pasted copy would be a second path that testing never
#     exercises. Every run goes through here.
#
#  3. A pasted block cannot be re-run safely. It appends, so running a pillar twice double-appends every
#     id, and the failure surfaces two steps later as reduce.sh refusing a duplicate question id -- far
#     from the cause. This refuses up front.
#
# The block itself is not copied and stays in the markdown, which is the point of the design: the reader
# sees the exact jq that produced the score, and the prose and the detection cannot disagree.
set -uo pipefail

PILLAR="${1:?usage: score.sh <pillar> <workdir>   # pillar: operational-excellence|security|reliability|performance-efficiency|cost-optimization}"
WORK="${2:?usage: score.sh <pillar> <workdir>}"

# Resolved from this file's own location, not from an environment variable. A script HAS a file identity
# (${BASH_SOURCE[0]}); a pasted fenced block does not, which is why a pasted form would need an
# exported path and this does not. render-report.py locates references/ the same way.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REF="$HERE/../references"

# Closed allowlist, not a path argument. The caller names a pillar and this decides which file to read,
# so no input can make it extract and execute an arbitrary file.
case "$PILLAR" in
  operational-excellence)  SRC="$REF/operational-excellence.md" ;;
  security)                SRC="$REF/security/identity-access.md" ;;
  reliability)             SRC="$REF/reliability.md" ;;
  performance-efficiency)  SRC="$REF/performance-efficiency.md" ;;
  cost-optimization)       SRC="$REF/cost-optimization.md" ;;
  *) echo "score.sh: unknown pillar '$PILLAR'" >&2
     echo "score.sh: expected one of: operational-excellence security reliability performance-efficiency cost-optimization" >&2
     exit 1 ;;
esac

[ -f "$SRC" ] || { echo "score.sh: cannot find $SRC -- is the skill tree complete?" >&2; exit 1; }
[ -d "$WORK" ] || { echo "score.sh: work dir $WORK does not exist -- run assets/collect.sh first" >&2; exit 1; }
[ -f "$WORK/cluster.json" ] || { echo "score.sh: $WORK has no cluster.json -- run assets/collect.sh first, and do not hand-build a work dir" >&2; exit 1; }

# Refuse a second run for the same pillar rather than double-appending. reduce.sh would catch the
# duplicate ids and abort the whole review, but it would do so two steps away from the cause.
if [ -f "$WORK/results.jsonl" ] && grep -q "\"pillar\":\"$PILLAR\"" "$WORK/results.jsonl" 2>/dev/null; then
  echo "score.sh: $WORK/results.jsonl already holds $PILLAR records -- this pillar has already been scored." >&2
  echo "score.sh: appending again would emit every id twice and reduce.sh would refuse the duplicates." >&2
  echo "score.sh: to re-score from scratch, re-collect into a new work directory whose name starts with eks-war- (collect.sh --work with a new path), then run all five pillars there." >&2
  exit 1
fi

# First fenced ```bash block only. Every pillar file has exactly one scorer block and it is the first;
# the later blocks are per-question `**Commands:**` illustrations and `**Remediation:**` snippets, which
# must never execute -- some of them delete PersistentVolumes.
#
# THE SCRATCH FILE IS THE RUN'S OWN, IN $WORK, AND ITS CREATION IS CHECKED. An unchecked
# `mktemp "${TMPDIR:-/tmp}/..."` fails on a read-only or full $TMPDIR: $BLK is EMPTY, the awk redirect below
# dies on the empty target, and `[ -s "$BLK" ]` then blames the SHIPPED REFERENCE FILE -- "found no fenced
# bash block in .../operational-excellence.md", which is false: awk extracts the whole scorer block from it and it does
# define emit(). $WORK is already this run's own checked-to-exist directory, so no /tmp is needed.
#
# THE `mkdir` IS WHAT MAKES A NAME IN $WORK SAFE. The file sits in a directory THIS PROCESS just created,
# and mkdir fails on ANY entry already at its name -- a leftover, a symlink (dangling or not), a FIFO --
# without following it, so nothing planted there is written through, and "$BLK" is a fresh name no other
# run has used. `set -C` is NOT a substitute: bash's noclobber
# refuses only an existing REGULAR file, and opens a planted symlink to /dev/null (measured). $PILLAR
# (closed allowlist above, so it cannot escape $WORK) and $$ in the name keep concurrent runs off each
# other's scratch: two DIFFERENT pillars, and two of the SAME pillar -- which still both append, as they
# always could, because the refusal above is not a lock. What is left is a same-uid process creating
# something inside the new directory before a redirect into it (collect.sh chmod 700s only a $WORK it made).
#
# NOTHING DELETES IT. Every run that gets past this point LEAVES its `.eks-war-scorer.<pillar>.<pid>/`
# directory, holding `block` and the scorer's `rl.stderr` (RLERR below), IN THE WORK DIR, and no later
# step removes it. That cannot change a result: collect.sh's `"$WORK"/*.json` globs skip a dot-name, and
# reduce.sh and render-report.py open only files they name. It costs disk, and a run whose pid matches
# a same-pillar leftover: mkdir says "File exists" and the check below refuses, which is true; the next
# run has another pid. Both creates are checked, the directory and the file in it: each is an allocation
# a full filesystem can refuse, and either refusal lands on the message below instead of blaming $SRC.
SCR="$WORK/.eks-war-scorer.$PILLAR.$$"
BLK="$SCR/block"
mkdir "$SCR" && true > "$BLK" || {
  echo "score.sh: cannot create the scratch file $BLK -- the error on the line above, mkdir's or the" >&2
  echo "score.sh: shell's, carries the errno and is the authoritative cause. It is about the WORK DIR" >&2
  echo "score.sh: $WORK, not about the skill tree: NOTHING IS WRONG WITH $SRC. Fix that, then re-run." >&2
  exit 1; }
awk '/^```bash$/{fl=1;next} /^```$/{if(fl)exit} fl' "$SRC" > "$BLK"

[ -s "$BLK" ] || { echo "score.sh: found no fenced bash block in $SRC" >&2; exit 1; }
grep -q '^emit()' "$BLK" || {
  echo "score.sh: the first fenced bash block in $SRC does not define emit() -- it is not the pillar scorer." >&2
  echo "score.sh: refusing to run it. A '**Commands:**' or '**Remediation:**' block must never be executed." >&2
  exit 1; }

# The block opens with W="$WORK", so WORK must be in this script's environment, not inherited from an
# earlier shell -- the Bash tool runs each command in its own process. RLERR is rl's stderr file, in $SCR.
WORK="$WORK" RLERR="$SCR/rl.stderr" bash "$BLK"
rc=$?
[ "$rc" -eq 0 ] || echo "score.sh: $PILLAR scorer exited $rc -- do NOT score from a partial results.jsonl" >&2
exit "$rc"
