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
# The detections still live in the reference files -- this script does not copy them, it extracts and
# runs the same block a reader sees. What it removes is the paste.
#
#  1. The tool-permission allowlist could not match the pasted form. Each pillar block defines shell
#     FUNCTIONS (`emit`, `g`, `m`, `m2`, `m3`, `m4`) and then calls them ~130 times as
#     `m sec-1 cluster '...'`. A Bash permission rule matches literal command text, so no rule can ever
#     match a shell-function name: every one of those calls, and the bare `B='...'` / `W="$WORK"`
#     assignments, fell through to the normal permission flow -- prompting interactively and HARD-DENIED
#     under a no-prompt policy, which meant an unattended run could not reach a score at all. This is the
#     same wrapper-function problem that moved collection into collect.sh; it was still sitting in the
#     scoring half. One grant per invocation of this script matches all of it.
#
#  2. The tested path and the shipped path were different paths. test-harness/run-skill.sh already
#     extracts the fenced block with awk and runs it; SKILL.md told the agent to paste it. So the harness
#     never exercised what shipped. Now both go through here.
#
#  3. A pasted block cannot be re-run safely. It appends, so running a pillar twice double-appends every
#     id, and the failure surfaced two steps later as reduce.sh refusing a duplicate question id -- far
#     from the cause. This refuses up front.
#
# The block itself is unchanged and stays in the markdown, which is the point of the design: the reader
# sees the exact jq that produced the score, and the prose and the detection cannot disagree.
set -uo pipefail

PILLAR="${1:?usage: score.sh <pillar> <workdir>   # pillar: operational-excellence|security|reliability|performance-efficiency|cost-optimization}"
WORK="${2:?usage: score.sh <pillar> <workdir>}"

# Resolved from this file's own location, not from an environment variable. A script HAS a file identity
# (${BASH_SOURCE[0]}); the fenced block this replaces did not, which is why the pasted form needed an
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
  echo "score.sh: to re-score from scratch, delete $WORK/results.jsonl and run all five pillars again." >&2
  exit 1
fi

# First fenced ```bash block only. Every pillar file has exactly one scorer block and it is the first;
# the later blocks are per-question `**Commands:**` illustrations and `**Remediation:**` snippets, which
# must never execute -- some of them delete PersistentVolumes.
BLK="$(mktemp "${TMPDIR:-/tmp}/eks-war-scorer.XXXXXX")"
trap 'rm -f "$BLK"' EXIT
awk '/^```bash$/{fl=1;next} /^```$/{if(fl)exit} fl' "$SRC" > "$BLK"

[ -s "$BLK" ] || { echo "score.sh: found no fenced bash block in $SRC" >&2; exit 1; }
grep -q '^emit()' "$BLK" || {
  echo "score.sh: the first fenced bash block in $SRC does not define emit() -- it is not the pillar scorer." >&2
  echo "score.sh: refusing to run it. A '**Commands:**' or '**Remediation:**' block must never be executed." >&2
  exit 1; }

# interactive mode: substitute the interview answers into the block instead of asking the agent to
# hand-edit `g <id>` calls into `emit <id> governance <state> "<note>"`. Optional -- absent means auto
# mode, where every `g` call emits state "unknown" and the question is reported Not Assessed.
#
# Format, one per line, TAB-separated:   <id>\t<state>\t<note>
# <state> must be one of: all most some none na unknown   (reduce.sh validates it either way)
ANS="$WORK/governance.tsv"
if [ -f "$ANS" ]; then
  n=0
  while IFS=$'\t' read -r gid gstate gnote; do
    [ -n "${gid:-}" ] || continue
    case "$gid" in \#*) continue ;; esac
    case "${gstate:-}" in
      all|most|some|none|na|unknown) ;;
      *) echo "score.sh: $ANS: illegal state '${gstate:-}' for $gid (legal: all most some none na unknown)" >&2; exit 1 ;;
    esac
    grep -q "^g $gid\$" "$BLK" || continue   # not a governance id in THIS pillar; another block owns it
    # Rewrite in place. gnote is placed inside double quotes in the emitted call, so a double quote or a
    # backslash in it would break the block -- strip both rather than emit something unparseable.
    safe_note="$(printf '%s' "${gnote:-}" | tr -d '"\\')"
    awk -v id="$gid" -v st="$gstate" -v nt="$safe_note" \
      '$0 == "g " id { print "emit " id " governance " st " \"" nt "\""; next } { print }' \
      "$BLK" > "$BLK.new" && mv "$BLK.new" "$BLK"
    n=$((n+1))
  done < "$ANS"
  [ "$n" -gt 0 ] && echo "score.sh: $PILLAR: applied $n interview answer(s) from $ANS" >&2
fi

# The block opens with W="$WORK", so WORK must be in this script's environment, not inherited from an
# earlier shell -- the Bash tool runs each command in its own process and an export does not survive.
WORK="$WORK" bash "$BLK"
rc=$?
[ "$rc" -eq 0 ] || echo "score.sh: $PILLAR scorer exited $rc -- do NOT score from a partial results.jsonl" >&2
exit "$rc"
