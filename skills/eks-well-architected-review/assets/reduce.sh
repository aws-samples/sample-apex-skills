#!/usr/bin/env bash
# Severity-weighted reducer. Reads <workdir>/results.jsonl, writes scores.json to stdout.
#
# Usage:  ./reduce.sh "$WORK" > "$WORK/scores.json"
#
# This is a SHIPPED asset, not a copy of one. It is deliberately NOT a fenced jq block inside
# SKILL.md that prints to stdout: `render-report.py` reads `$WORK/scores.json` and hard-exits
# without it, and a block with no documented step writing that file leaves the agent to infer the redirect.
# An improvised step on the determinism spine is exactly where a silent divergence starts, so the
# reducer is a file the workflow invokes rather than a block the agent retypes.
#
# THE SEVERITY WEIGHTS ARE NOT WRITTEN DOWN IN THIS FILE. Do not add a copy: a literal jq map here, a
# second in SKILL.md's inline jq, a third in render-report.py's own severity sets -- beside the prose in
# references/severity.md's per-question tables, which is the only one a reader ever sees -- are copies
# nothing diffs. An id listed in severity.md's Reliability LOW table but absent from a code map would
# score at a `// 2` DEFAULT = Medium: the reader is told Low, the score uses Medium, at exit 0. Weight 1
# instead of 2 on a single question can move a published pillar score by a point, so such a
# disagreement is worth a score, not just a doc fix.
#
# references/severity.md IS THE SINGLE SOURCE. This file PARSES it (SEVERITY WEIGHTS section below)
# and render-report.py does not parse it at all -- it reads the parsed map back out of scores.json,
# where the block below publishes it under `severity`. So the weight the report LABELS a finding with is
# the same byte the published score was computed from, which is the one thing diffing two
# hand-maintained copies can never guarantee. It is also what this file's contract already says about
# every other number in the report: scores.json is the score contract and the renderer copies from it
# rather than recomputing.
#
# Same principle as the bucket rule b(): the state<->ratio gate below EXTRACTS b() from the reference
# files at run time instead of keeping a copy, and asserts the five committed copies are one distinct
# value. Prefer that shape for anything added here later. A markdown table is a poor machine interface,
# so every way the parse can go wrong -- unreadable file, unparsable ID cell, duplicate id, an id in
# results.jsonl with no row, a row for an id nothing emits -- REFUSES with a `reduce.sh:` diagnostic and
# exit 1. There is deliberately no fallback weight: a silent default is how a weight drifts unseen.
set -uo pipefail
umask 077
# -o writes scores.json HERE rather than relying on the caller's `> $WORK/scores.json` redirect. Two
# reasons. (1) Mode: a redirect is performed by the CALLING shell before this script starts, so no umask
# set in here can reach the file -- under a typical umask 022 scores.json lands 644 while everything collect.sh writes
# is 600, and scores.json is one of the two files most likely to be pasted into a ticket. Writing it
# ourselves puts it under this script's `umask 077`. (2) The redirect is not optional but is easy to
# omit, and omitting it leaves a 0-byte scores.json whose failure surfaces two steps later as a renderer
# complaint. Without -o the output still goes to stdout, so a redirect-based caller still works.
OUT=""
if [ "${1-}" = "-o" ]; then
  [ $# -ge 2 ] || { echo "reduce.sh: -o needs a path" >&2; exit 2; }
  OUT="$2"; shift 2
fi
W="${1:?usage: reduce.sh [-o scores.json] <workdir>   # reads <workdir>/results.jsonl, nodes.json, pods.json}"
[ -f "$W/results.jsonl" ] || { echo "reduce.sh: no results.jsonl in $W -- run the pillar scorers first" >&2; exit 1; }
[ -s "$W/results.jsonl" ] || { echo "reduce.sh: $W/results.jsonl is empty -- nothing was scored" >&2; exit 1; }

# ── COLLECTION FINGERPRINT -- this work dir must be the one that was collected ──────────────────────
# assets/collect.sh writes $W/.collection.json at the end of a successful collection: one UTC
# collection instant, the cluster and region as collected, and a sha256 over the content of every
# collected *.json. This gate proves the files its `files` map names -- on a collect.sh-written
# fingerprint, every collected *.json, including those this script and the scorers read -- are those
# same bytes.
#
# WHY THE SCORE CONTRACT IS WHERE THIS BELONGS. render-report.py is not relied on to re-derive questions'
# resource lists from the collected JSON -- that would be a second implementation of the checks -- so
# nothing downstream can be counted on to surface collected data that changed after collection. This gate
# checks that HERE, where every consumer of scores.json inherits it: the same argument the viability and
# liveness gates below make for living in the score contract rather than in three surfaces that can differ.
#
# WHAT IT CATCHES that nothing else does: a collected file hand-edited between collection and scoring, a
# collection that was interrupted and re-run half way, and a work dir whose collected files come from two
# collections. It does NOT catch a results.jsonl produced from other data -- one copied in from another
# work dir reduces and renders under this work dir's cluster; only assets/collect.sh's refusal of a work
# dir that already holds a non-empty results.jsonl stands in the way, and that blocks re-collecting in
# place, not copying. It is NOT a security boundary -- anyone who can edit pods.json can edit the
# fingerprint sitting beside it -- it is a provenance check on the collected input.
#
# WHAT IT COVERS. The collected INPUT, by content: the files the fingerprint's `files` map names. It does
# NOT cover results.jsonl -- the scorers append to that after collection ends, so no collection-time
# digest could describe it -- which means this gate says nothing about whether the emitted RECORDS are
# self-consistent. That is the state<->ratio gate's job further down. The two are complementary, not
# redundant: this one answers "is this the data that was collected, and when", that one answers "does
# each record's verdict follow from its own ratio". Neither substitutes for the other.
#
# The digest walks the `files` map rather than re-globbing $W, deliberately: a caller redirecting this
# script's stdout INTO the work dir (`reduce.sh "$W" > "$W/out.json"`) creates that file before this line
# runs, and a glob-based digest would refuse a correct run over it. assets/collect.sh carries the full
# argument for the allowlist, the digest definition, and the reason a collection TIMESTAMP does not break
# the byte-identical-across-two-runs requirement. Keep the two bash implementations and
# render-report.py's python one byte-compatible; the short version is:
#
#   for each name in the fingerprint's `files`, LC_ALL=C sorted:  "<name>  <sha256 hex>\n"
#     (a listed name that is no longer a readable file contributes no line, so the digest cannot match
#      and the mismatch is reported as "removed since collection")
#   digest = sha256 hex of that concatenation
#
# Nothing from this file reaches scores.json. It is compared, never copied -- which is what keeps two
# collections of the same data producing byte-identical scores.json while carrying two different
# collection instants.
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
FP="$W/.collection.json"
[ -f "$FP" ] || { echo "reduce.sh: no .collection.json in $W -- this work dir carries no record of" \
  "having been collected, so there is nothing to prove these files are the ones that were scored." \
  "assets/collect.sh writes it at the end of a successful collection; a work dir without it is either" \
  "from a collection that REFUSED (in which case do not score it -- read the collector's message) or" \
  "one assembled by hand. Re-run collection." >&2; exit 1; }
# `collected_at` is shape-checked, not merely non-empty, and this gate is deliberately no laxer than
# render-report.py's: the renderer prints that field as the report's "Data collected" line and refuses
# a value it cannot read as an instant, so a reducer that ACCEPTED one would hand the operator a
# published score and then a refused report -- two stages disagreeing about the same file, which is the
# split-gate failure the viability comment below describes. Same rule, same wording, both ends.
# TWO OUTCOMES, TWO MESSAGES, AND NO `2>&1`. Do not write this as `jq -e '...' "$FP" >/dev/null 2>&1 || {...}`:
# that collapses "the shape test is false" into "the shape test could not run" and then asserts the
# first about the second -- while the redirect throws away the only evidence of which happened,
# including bash's own `jq: command not found`. On a good work dir, with a PATH holding every binary
# EXCEPT jq, that form returns rc=1 and tells the operator the fingerprint is malformed and to
# "Re-run collection" -- a real AWS/kubectl round trip -- over data that is fine, with nothing on
# stderr naming jq. Plausible in an agentic session where each tool call can get a
# different PATH. So it takes the capture-and-check idiom this file's other "NOT checked" refusals use:
# a nonzero jq means the invariant was not checked, a `false` result means the file is malformed, and jq's
# stderr is not redirected anywhere. The others are named, not counted, because a count goes stale:
# `grep -n "was NOT checked"` lists them plus this gate's own message and this comment. All guard a
# `$(jq ...)` capture (FP_WANT, FP_LINES,
# ITEMS_SHAPE, BADJSON, MISSINGFIELDS, DUPIDS, BADENUM, BADSTATE, BADRATIO, SEV_UNSOURCED, SEV_STALE) except SEV_DUP,
# which guards a `$(printf ... | awk ... | sort)` pipeline and no jq at all.
FP_SHAPE=$(jq -r '(type=="object") and ((.digest|type)=="string") and ((.digest|test("^[0-9a-f]{64}$")))
       and ((.collected_at|type)=="string")
       and ((.collected_at|test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")))
       and ((.files|type)=="object") | tostring' "$FP") \
  || { echo "reduce.sh: the collection-fingerprint shape gate could not run -- jq exited nonzero over" \
    "$FP, so the invariant was NOT checked. Refusing rather than publishing a score whose provenance" \
    "gate was silently skipped. jq's own message above is the evidence for WHICH cause this is: a parse" \
    "error means $FP itself, and a \`command not found\` means jq is not on PATH while the collected" \
    "data is fine -- do not re-collect a cluster over that." >&2; exit 1; }
[ "$FP_SHAPE" = "true" ] \
  || { echo "reduce.sh: $FP is malformed -- it must be a JSON object carrying a 64-character lowercase" \
    "hex \`digest\`, a \`collected_at\` holding one UTC ISO-8601 instant of the form" \
    "2026-01-31T12:30:00Z, and a \`files\` object. A fingerprint that cannot be read is not a weaker" \
    "fingerprint, it is none: the report takes its \"Data collected\" line from it and will refuse the" \
    "same value. Re-run collection." >&2; exit 1; }
# THESE TWO CAPTURES ARE GUARDED; FOUR IN THIS FILE ARE NOT. Both read $FP, and a jq that dies at
# either leaves the variable EMPTY -- `set -u` does not object, because the assignment did happen -- after
# which the run refuses at the digest comparison below. What the operator is told then is NOT the same for
# the two, and that difference is the honest case for guarding them.
#   FOR FP_WANT THE REAL CAUSE WOULD BE NAMED, BUT SECOND. Unguarded, a shim jq that fails only for
# `jq -r '.digest'` gives rc=1, the prior scores.json intact, and a message headed "does not match its own
# collection fingerprint" whose body offers two disjuncts -- "either .collection.json has been altered
# rather than the collected data, or THE PER-FILE COMPARISON ITSELF COULD NOT RUN" -- closing with "check
# that $FP is well-formed JSON". So the truth would be in there. What would be wrong is the headline, and the first
# prescription under it: "Re-run collection and re-score all five pillars", a real AWS/kubectl round trip
# over data that is fine. Guarding this line is diagnostic polish and is not claimed as more than that.
#   FOR FP_LINES THERE IS NO SUCH LET-OUT, and that is why the pair is worth guarding at all. An empty
# FP_LINES leaves the per-file comparison with nothing to match any recorded name against, so every one is
# reported DELETED. Unguarded, a shim failing only `jq -r '.files|keys[]'`, with every name recorded in
# `.files` present on disk, would show the operator TEN of them as "<name>: removed since
# collection". The `head -10` on the printf below caps that list and prints no "and N more", so ten
# fabricated deletions read as the whole finding. That is a provably false claim about named files, and
# the capture is the only place it can be stopped.
#   jq's stderr is visible on both lines -- neither carries a `2>/dev/null` -- so neither failure is
# silent, whatever else its message gets wrong.
#   NEITHER FAILURE IS REACHABLE BY INPUT ALONE, and saying so is the reason to write it down rather than
# let the guards imply otherwise. The shape gate immediately above has already proven $FP is an object
# whose `.digest` is a 64-character hex STRING and whose `.files` is an object, so `jq -r '.digest'` and
# `jq -r '.files|keys[]'` cannot fail over a $FP that got this far. `collection_lines` cannot fail either:
# its last pipeline stage is `sort`, and a listed file it cannot hash yields a line with an EMPTY hash
# rather than an error -- measured, a collected file at mode 000 gives the capture rc=0 and a bare
# `b.json  ` with no digest, and it is the MISMATCH below that refuses, not this line. What these two
# guards cover is a jq that becomes unavailable or broken BETWEEN that gate and here -- the per-tool-call
# PATH the shape gate's own comment cites -- or a fork that fails.
#   THE FOUR THAT REMAIN UNGUARDED are NODES_TOTAL, NODES_READY, PODS_WL and PODS_RUN further down, and
# their residual is data loss rather than a wrong headline: the empty capture is not noticed until the
# final `--argjson` rejects it, and the write at the bottom of this file truncates its destination as that
# pipeline stage opens. With `{"items":[3]}` as nodes.json -- a shape every gate above
# legitimately accepts -- a good scores.json becomes 0 bytes at rc=2, and what the operator gets
# is four lines of jq with no `reduce.sh:` message at all. Do not read these two guards as closing that.
FP_WANT=$(jq -r '.digest' "$FP") || { echo "reduce.sh: could not read the recorded digest out of $FP --" \
  "jq exited nonzero over it (its own message, if it produced one, is above), so the collection" \
  "fingerprint was NOT checked. Refusing rather than publishing a score whose provenance gate was" \
  "silently skipped. This is not a claim that $FP is malformed -- the shape gate above already read it as" \
  "an object carrying a 64-character hex digest -- so check that jq still runs." >&2; exit 1; }
FP_LINES=$(jq -r '.files|keys[]' "$FP" | collection_lines "$W") \
  || { echo "reduce.sh: could not list the collected file names out of $FP -- jq exited nonzero over it" \
  "(its own message, if it produced one, is above), so the collection fingerprint was NOT checked." \
  "Refusing rather than publishing a score for data whose provenance was never compared. The re-hashing" \
  "half cannot be the cause: collection_lines ends in \`sort\` and reports 0 even for a file it could not" \
  "hash, which surfaces as a digest MISMATCH below and never here." >&2; exit 1; }
FP_HAVE=$(printf '%s\n' "$FP_LINES" | sha256_hex)
if [ "$FP_WANT" != "$FP_HAVE" ]; then
  # Name the files, not just the mismatch. A digest comparison tells the operator that SOMETHING moved;
  # the point of hashing per file is being able to say WHICH, so they can tell a re-collection apart from
  # one edited file. There is no "added" arm: the recomputation walks the recorded names, so a file that
  # merely appeared in the work dir is not part of this comparison at all -- by design, see above.
  CHANGED=$(printf '%s\n' "$FP_LINES" | jq -Rrs --slurpfile fp "$FP" '
    ($fp[0].files // {}) as $was
    | (split("\n") | map(select(length > 0) | split("  ") | {key: .[0], value: .[1]})
       | from_entries) as $now
    | ($was|keys)
    | map(. as $k
          | if   $now[$k] == null      then "\($k): removed since collection"
            elif $was[$k] != $now[$k]  then "\($k): modified since collection"
            else empty end)
    | .[]' 2>/dev/null)
  echo "reduce.sh: $W does not match its own collection fingerprint -- refusing to publish a score" \
    "for data whose provenance does not hold." >&2
  if [ -n "$CHANGED" ]; then
    printf '%s\n' "$CHANGED" | head -10 | sed 's/^/  /' >&2
  else
    # TWO THINGS REACH THIS ARM, SO THE MESSAGE NAMES BOTH. Either the per-file comparison found no difference
    # -- so the recorded digest disagrees with the files the fingerprint itself lists, which points at the
    # fingerprint -- or the jq that produces `$CHANGED` died, and its stderr went to /dev/null. Asserting the
    # first about the second is a diagnostic defect this file refuses throughout, in the
    # severity block and here outside it. The refusal itself is right either way: the outer digest
    # comparison already failed.
    echo "  No individual file differs from the digest recorded for it, so either $FP has been altered" >&2
    echo "  rather than the collected data, or the per-file comparison itself could not run. Re-run" >&2
    echo "  collection; if that does not clear it, check that $FP is well-formed JSON." >&2
  fi
  echo "  Every question was answered from the files as they were at collection time. Scoring the" >&2
  echo "  current ones would publish a number for one cluster state under the evidence of another," >&2
  echo "  which is the failure this gate exists to prevent. Re-run collection and re-score all five" >&2
  echo "  pillars." >&2
  exit 1
fi

# ── VIABILITY AND LIVENESS LIVE HERE, not in the report layer ──────────────────────────────────────
# These gates are not prose in SKILL.md or Python in render-report.py: split that way, the
# HTML could withhold a dead cluster's score while `reduce.sh` still emitted a number and the chat/markdown
# path printed it. A gate that only one of three surfaces honours is not a gate. Both resolve in
# the score contract, so every consumer of scores.json inherits them and none can recompute a
# different answer.
#
# Required, not optional: a work dir without nodes.json/pods.json cannot answer "is this cluster
# alive", and silently scoring as though it were is the exact failure this prevents.
for f in nodes pods; do
  [ -f "$W/$f.json" ] || { echo "reduce.sh: no $f.json in $W -- viability and liveness cannot be" \
    "evaluated without it, and a score that skips those gates is the defect this file exists to" \
    "prevent. Re-run collection." >&2; exit 1; }
  # NEITHER `2>&1` NOR "is not valid JSON". Both are wrong, and together: the redirect hides jq's own
  # reason and the message then asserts a cause this line holds no evidence for. With a jq that
  # fails only for `jq -e . <file>`, that form prints "nodes.json is not valid JSON" about a file real jq
  # validates at rc=0. A nonzero jq here is all that is observed -- the file could be malformed, jq
  # could be missing, the program could be uncompilable -- so that is what the message says, and jq's
  # stderr is left visible to say which.
  jq -e . "$W/$f.json" >/dev/null || { echo "reduce.sh: jq exited nonzero over $W/$f.json, so it could" \
    "not be confirmed as one readable JSON document -- jq's own message, if it produced one, is above." \
    "Refusing rather than scoring a file the reducer could not read." >&2; exit 1; }
  # `.items` must be PRESENT, not merely navigable. Counting with `.items[]?` would let safe
  # navigation make an ABSENT key indistinguishable from an empty list -- so a truncated or malformed
  # nodes.json (`{}`, or an error envelope that happens to be valid JSON) would count as zero nodes and
  # publish "NOT VIABLE — no data plane" for a cluster whose data plane was never looked at. That is
  # the worst possible verdict to get wrong: it is the one that suppresses the score entirely.
  # `kubectl get nodes -o json` returns {"items":[]} on a genuinely empty cluster, so a missing
  # `.items` is always a bad FILE and never a bad CLUSTER. render-report.py's need_list() already
  # refuses this exact input for the same reason; the gate's owner must not be the laxer of the two.
  # Split the same two ways as the fingerprint gate above, and for the same reason: with a jq
  # that fails only for this shape test, a swallowed-stderr form would print "has no `.items` array"
  # about a file whose `.items` is a perfectly good array. A nonzero jq is "NOT checked"; only a `false`
  # result is a claim about the file.
  #   THE COMPARISON ALSO CATCHES A MULTI-DOCUMENT FILE, WHICH IS WHY THE MESSAGE BELOW NAMES TWO CAUSES.
  # `jq -r '... | tostring'` applies its program ONCE PER DOCUMENT and prints one line per document, so a
  # nodes.json holding two concatenated documents makes this capture `true<newline>true`, which is not
  # `true` and is refused. That catch is worth having: a `jq -e` form of this test reports only the LAST
  # document's result, so it passes the file, which then dies inside the final scoring pipeline at rc=2 --
  # after `cat >` has already taken a good scores.json to 0 bytes. And a message reading "has no
  # `.items` array ... an absent or non-array .items" would be FALSE on that exact file: both documents
  # can carry a perfectly good `.items` array. Asserting a cause the test holds no evidence for is the
  # defect this gate is split to avoid, so the message states the two causes a single `true` rules out
  # and claims neither one.
  ITEMS_SHAPE=$(jq -r 'type=="object" and has("items") and (.items|type=="array") | tostring' \
    "$W/$f.json") || { echo "reduce.sh: the \`.items\` shape gate could not run -- jq exited nonzero" \
    "over $W/$f.json (its own message, if it produced one, is above), so the invariant was NOT checked." \
    "Refusing rather than publishing a score whose viability gate was silently skipped." >&2; exit 1; }
  [ "$ITEMS_SHAPE" = "true" ] || {
    echo "reduce.sh: $W/$f.json did not answer the \`.items\` shape test with a single \`true\` -- it is" \
      "MALFORMED, not a cluster with no ${f}, and it is ONE OF TWO things. Either \`.items\` is absent or" \
      "is not an array, which means the collection was truncated or returned something other than a ${f}" \
      "list; or the file holds MORE THAN ONE JSON document, because the test above runs once per document" \
      "and this comparison wants exactly one \`true\`. Tell them apart with \`jq -s 'length'" \
      "$W/$f.json\`, which counts the documents. \`kubectl get ${f} -o json\` returns exactly ONE" \
      "document, and an empty cluster still returns one document holding {\"items\":[]}, so both causes" \
      "are a bad FILE and neither is a bad cluster. Scoring it would report" \
      "NOT VIABLE for a bad file. Re-run collection." >&2; exit 1; }
done

# A "workload pod" is one outside the AWS/Kubernetes system namespaces whose phase is not `Succeeded`: a
# completed Job/CronJob pod has finished its work and is not a pod that failed to run. This is the ONE
# definition: excluding only kube-system/kube-node-lease/kube-public in one gate and every kube-*/amazon-* in
# another would let the viability gate and the liveness gate disagree about which pods count. It is the broader
# prefix match, which is the one that correctly ignores add-on namespaces such as amazon-guardduty.
#
# No `?` on `.items[]` below, deliberately: the guard above has already proven the key is an array, and
# the safe-navigation operator is what would let a malformed file masquerade as an empty one.
#
# Windows nodes are not counted (the scorers' `iswin`): this skill supports Linux nodes only, so a
# cluster whose only nodes -- or only Ready nodes -- are Windows has no data plane this review assesses.
NODES_TOTAL=$(jq '[.items[]|select(((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)!="windows")]|length' "$W/nodes.json")
NODES_READY=$(jq '[.items[]|select(((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)!="windows")|select([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0)]|length' "$W/nodes.json")
PODS_WL=$(jq '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")!="Succeeded")]|length' "$W/pods.json")
PODS_RUN=$(jq '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)")|not) and .status.phase=="Running")]|length' "$W/pods.json")

# ── results.jsonl STRUCTURE, validated before the scoring pipeline can see it ───────────────────────
# Every line must parse as JSON *and* be an object. Leaving that to the state-enum validator below,
# run with `2>/dev/null`, is not enough: a syntactically broken line would produce
# no hit there, sail through, and blow up inside the main `jq -s` pipeline as a bare
# "jq: parse error: Invalid literal at line 3, column 7" with exit 5: jq's code and jq's wording, not
# this file's exit-1 refusal convention, and with no indication of which file was at fault. A non-object
# line (`3`, `null`, `[...]`) would escape the same way, via "Cannot index number with state".
# Whitespace-only lines are tolerated because the scoring pipeline already ignores them.
#
# Line numbers come from an explicit `split("\n")` over the whole slurped file, NOT jq's
# `input_line_number` -- that builtin counts consumed NEWLINES, so a FINAL line with no trailing
# newline (a mid-write truncation -- this guard's stated primary use case) is attributed to the
# PREVIOUS line's number:
#   printf 'line1\nline2\nline3' | jq -R -r '"\(input_line_number): \(.)"'   # last line reports "2", not 3
# Splitting on "\n" ourselves and indexing gives the real line for every case, truncated or not. A
# split on a file that ends in "\n" leaves one trailing empty element that is not a real line, so it is
# excluded from the range; a file that does NOT end in "\n" has no such phantom element, so nothing is
# excluded and the true final (truncated) line is still checked.
BADJSON=$(jq -R -s -r '
  split("\n") as $lines
  | ($lines | length) as $n
  | (if $lines[$n-1]=="" then $n-1 else $n end) as $lastreal
  | range(0; $lastreal) as $i
  | $lines[$i] as $l
  | ($l | (try fromjson catch null)) as $r
  | if ($l|test("^[[:space:]]*$")) or (($r|type)=="object") then empty
    else "line \($i+1): \($l[0:60])" end
' "$W/results.jsonl") || {
  echo "reduce.sh: the JSONL well-formedness gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked. Refusing rather than publishing a score" \
    "whose only guard was silently skipped." >&2
  exit 1; }
if [ -n "$BADJSON" ]; then
  echo "reduce.sh: $W/results.jsonl is not valid JSONL -- every line must be one JSON object" >&2
  printf '%s\n' "$BADJSON" | head -5 | sed 's/^/  /' >&2
  echo "  A scorer block that was interrupted mid-write leaves a truncated last line. Truncate" >&2
  echo "  results.jsonl and re-score all five pillars, or re-run collection." >&2
  exit 1
fi

# ── REQUIRED FIELDS -- every record must carry pillar, id, track and state ──────────────────────────
# Checked here, before DUPIDS/BADSTATE and before any arithmetic, because two different failures
# follow a missing field and neither is the documented one:
#   - No `id`: reaches the grouping/lookup in the main `jq -s` pipeline below and dies with a bare
#     "jq: error ... Cannot index object with null", exit 5 -- jq's code and jq's wording, not this
#     file's exit-1 `reduce.sh:` convention SKILL.md promises fires "before a byte of output".
#   - No `track` (or no `pillar`): silently fails every `.track==`/`.pillar==` filter downstream, so
#     the record is dropped from BOTH the numerator and the denominator with exit 0 and no warning --
#     e.g. one measured + one trackless record reports "security total=1 applicable=1 coverage=100%"
#     while a question vanished. That is the exact failure the coverage gate exists to disclose.
# A field counts as missing if the key is absent, its value is null, or (for these four, all expected
# to be non-empty strings) it is the empty string -- an empty value fails the same downstream filters
# an absent key does, so treating it as present would reopen the same silent-drop.
#
# PRESENCE ONLY. This gate proves the four fields are there; it does not prove `pillar` and `track`
# hold legal values, and a present-but-misspelled one is dropped exactly as silently as an absent one.
# The enum gate below closes that half; `id` is instead constrained by DUPIDS and by the severity
# table's `// 2` default, and `state` by the state enum plus -- for MEASURED records whose `detail` leads
# with a ratio -- the state<->ratio gate, which is the only gate here that reads `detail` at all.
# `detail` itself is NOT required: a scorer arm may legitimately answer with no note.
MISSINGFIELDS=$(jq -r '
  . as $r
  | ["pillar","id","track","state"]
  | map(select(($r[.] == null) or (($r[.]|type)=="string" and ($r[.]|length)==0)))
  | select(length > 0)
  | "line \(input_line_number): missing/empty field(s) \(join(",")) -- \($r|tostring|.[0:80])"
' "$W/results.jsonl") || {
  echo "reduce.sh: the required-field gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked. Refusing rather than publishing a score" \
    "whose only guard was silently skipped." >&2
  exit 1; }
if [ -n "$MISSINGFIELDS" ]; then
  echo "reduce.sh: $W/results.jsonl has record(s) missing a required field -- every record must carry" \
    "pillar, id, track and state" >&2
  printf '%s\n' "$MISSINGFIELDS" | head -5 | sed 's/^/  /' >&2
  exit 1
fi

# ── ONE RECORD PER QUESTION ID ─────────────────────────────────────────────────────────────────────
# A repeated id silently double-counts and MOVES A PUBLISHED SCORE, with exit 0 and no warning. This is
# not a hand-editing hypothetical: the scorer helpers (`m`, `m2`, ...) `exit 1` with SCORER ABORT when a
# jq program fails, leaving results.jsonl partially written for that pillar, and SKILL.md Step 5 tells
# the agent to run the pillar block *verbatim* -- so the obvious retry re-emits every question the block
# already wrote. Every re-emitted question is then counted twice, which can move that pillar's score, and
# a re-emitted governance question is counted twice in the governance denominator.
# Appending is not idempotent, so the reducer refuses rather than average two answers to one question.
DUPIDS=$(jq -s -r 'map(.id // "(record with no id)") | group_by(.) | map(select(length>1))
  | map("\(.[0]|tostring) (\(length) records)") | .[]' "$W/results.jsonl") || {
  echo "reduce.sh: the duplicate-id gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked. Refusing rather than publishing a score" \
    "whose only guard was silently skipped." >&2
  exit 1; }
if [ -n "$DUPIDS" ]; then
  echo "reduce.sh: duplicate question id(s) in $W/results.jsonl -- each question must appear exactly once" >&2
  printf '%s\n' "$DUPIDS" | head -10 | sed 's/^/  /' >&2
  echo "  A duplicate double-counts its question: it moves the published pillar score and inflates the" >&2
  echo "  governance denominator, so it is refused here rather than merged or averaged." >&2
  echo "  Most likely cause: a pillar scorer block was re-run after a SCORER ABORT and appended a" >&2
  echo "  second copy of everything it had already written. Fix by re-collecting into a new work" >&2
  echo "  directory whose name starts with eks-war- (collect.sh --work with a new path), and re-score ALL five" >&2
  echo "  pillars." >&2
  exit 1
fi

# ── PILLAR AND TRACK ENUMS -- values, not merely presence ──────────────────────────────────────────
# The gate above proves `pillar` and `track` are non-empty. It does not prove they are spelled the way
# the pipeline below spells them, and both are matched by exact string EQUALITY
# (`select(.track=="measured")`, `select(.pillar==$p)`). So a wrong value is not a wrong answer, it is
# a MISSING one: the record falls out of BOTH the numerator and the denominator with exit 0 and no
# warning -- the identical silent-drop the presence gate exists to prevent, reached by typo instead of
# by omission. Reproducing on a collected work dir the arithmetic this gate refuses shows it:
# capitalising one measured record's `pillar` takes that pillar's question count down by one and can
# move both its score and the published headline; capitalising the `track` of a High-severity question
# does the same to its own pillar, and both are silent without this gate.
#   THE SCORE DOES NOT RELIABLY FALL, and the claim is that a typo MOVES the score, not that it
# lowers it: dropping a record scored below the pillar's average raises it, dropping one scored above
# lowers it, and a drop can also leave every rounded figure where it was. That last case is the worst
# one for a reader rather than the mildest: a question left the denominator and not one published
# figure changed. Reproduce it per record on your own work dir rather than trusting any one
# outcome: the direction and size depend on which record is dropped and on what the rest of
# the pillar scored, so no before/after figure written here would describe your cluster, and
# none is given.
#
# Both sets are CLOSED and are the scorers', not this file's taste:
#   - the five pillar strings are the literals hard-coded in the five `emit()` definitions. GREP for
#     them; do not trust a line number here. A line-number pointer goes stale on any edit to the
#     scorer file, and a stale one that lands on a blank line is
#     worse than no pointer at all because it reads as if it had been checked:
#         grep -n '{pillar:"' references/*.md references/*/*.md
#     That prints exactly five lines, one per pillar. Security's is in
#     references/security/identity-access.md because that one block scores the WHOLE Security pillar;
#     the other four files are named for their pillar. (Two glob terms, not `**`: stock macOS bash is
#     3.2 and has no `globstar`, so `references/**/*.md` would silently miss security/.) Those five
#     strings are also exactly the names `pillars` keys on below and exactly the names
#     assets/score.sh accepts;
#   - the two track strings are the only values any caller of `emit` passes: `governance` from `g()`
#     (`grep -n '^g(){' references/*.md references/*/*.md` -- five lines, one per pillar file),
#     `measured` from every `m`/`m2`/`m3`/`m4`/`m7` helper.
# Nothing shipped emits a third value of either, so anything else is a defect and is refused rather
# than dropped. Membership also rejects a non-string (`"pillar": 3`), which the presence gate admits.
#
# Ordered BEFORE the state check deliberately: that check exempts `unknown` only when
# `.track=="governance"`, so a mis-cased `track` on a governance record would be reported there as an
# illegal STATE -- loud, but blaming the wrong field.
BADENUM=$(jq -r 'select((.pillar|IN("operational-excellence","security","reliability",
                                    "performance-efficiency","cost-optimization")|not)
                        or (.track|IN("measured","governance")|not))
  | "\(.id // "?") pillar=\(.pillar|tostring) track=\(.track|tostring)"' "$W/results.jsonl") || {
  echo "reduce.sh: the pillar/track enum gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked. Refusing rather than publishing a score" \
    "whose only guard was silently skipped." >&2
  exit 1; }
if [ -n "$BADENUM" ]; then
  echo "reduce.sh: illegal pillar/track value(s) in $W/results.jsonl -- legal pillars:" \
    "operational-excellence security reliability performance-efficiency cost-optimization;" \
    "legal tracks: measured governance" >&2
  printf '%s\n' "$BADENUM" | head -5 | sed 's/^/  /' >&2
  echo "  Both are matched by exact string equality and are case-sensitive, so a record spelling" >&2
  echo "  either differently is dropped from the numerator AND the denominator and moves the" >&2
  echo "  published score. Fix the value, or re-run the pillar scorers, which emit both verbatim." >&2
  exit 1
fi

# Validate the state enum before scoring. A numeric or out-of-enum `state` would otherwise reach jq's lookup
# table and produce a bare interpreter error with exit 5 -- jq's code, not this file's exit-1
# convention. `unknown` is legal ONLY on the governance track, per the scoring model in references/workflow.md: the
# measured lookup table {all,most,some,none} has no `unknown` entry and the applicable pool filters
# only `na`, so a measured record with state "unknown" would reach the multiplication and die with
# "null (null) and number (3) cannot be multiplied", exit 5, no scores.json. Admitting `unknown` on
# every track would let that record through this gate.
BADSTATE=$(jq -r 'select(((.state|type)!="string")
  or (((.state|IN("all","most","some","none","na"))
       or (.state=="unknown" and .track=="governance"))|not))
  | "\(.id // "?") track=\(.track|tostring) state=\(.state|tostring)"' "$W/results.jsonl") || {
  echo "reduce.sh: the state enum gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked. Refusing rather than publishing a score" \
    "whose only guard was silently skipped." >&2
  exit 1; }
if [ -n "$BADSTATE" ]; then
  echo "reduce.sh: illegal state value(s) in $W/results.jsonl -- legal: all most some none na;" \
    "unknown is legal on the governance track ONLY" >&2
  printf '%s\n' "$BADSTATE" | head -5 | sed 's/^/  /' >&2
  exit 1
fi

# ── STATE <-> RATIO -- a detail that leads with `n/m` must be the state's own bucket ────────────────
# Every measuring scorer emits `b($ok;$t)+"~\($ok)/\($t) ..."`, so `state` and the leading `n/m` of
# `detail` are two projections of ONE measurement. Nothing else checks that they still are. A record can
# therefore publish `"state":"all"` beside `"detail":"0/8 ..."` and move the headline at exit 0 -- the
# arithmetic below uses the state, the reader uses the ratio, and the disagreement is invisible. This is
# not only a hand-editing hypothesis: `emit()` builds records from cluster-controlled strings, and a
# partially-rewritten results.jsonl is a documented failure mode two gates above.
#
# WHY HERE AND NOT IN THE RENDERER. render-report.py's resource_agreement() looks like the obvious home
# and structurally cannot do this job: it returns early for any question whose scorer publishes no `rl`
# list of its own -- it keeps no private resource table to fall back on -- and seven ratio-bearing
# questions publish none -- rbac-2, rbac-3, ope-2, rel-20, rel-21, lens-8,
# lens-10. Forging the state of any of those can move the published overall at exit 0 with no message
# there. That placement reaches only the questions that publish an `rl` list; this invariant
# needs only `state` and `detail`, and reduce.sh is already where the score contract refuses malformed
# input -- the same argument the viability and liveness comments above make for themselves. Every
# measured question is in scope here whether or not it publishes an `rl` list, which is the bound that
# ruled the renderer out.
#
# BUT THE BOUND THAT REPLACES IT IS THE RATIO'S POSITION, NOT THE QUESTION'S: "in scope" above means
# eligible, not inspected. The `capture`
# below is anchored with `^`, so this gate inspects only measured records whose `detail` LEADS with `n/m`
# and whose id is not in RATIO_STATE_EXEMPT below, and skips every other one in silence. How many
# records lead with a ratio depends on the scorers' wording and on the cluster, and moves when either
# does, so rely on the BOUND, never a count.
# THE ANCHOR ITSELF IS RIGHT, AND THE SKIPPED RECORDS SHOW WHY. Measured details that carry an `n/m`-
# shaped token anywhere but the front -- `sec-2`, `sec-30` and `net-4` can -- carry a CIDR
# prefix, not a ratio. An UNanchored capture reads `0/0` out of `0.0.0.0/0` in sec-2's detail
# and would then demand `state == b(0;0) == "na"` against a correctly published `none` -- a false
# refusal on a good record. What is genuinely out of reach is a count written as prose: `sec-4` publishes
# "0 of 4 workload namespace(s) carry a NetworkPolicy", exactly the kind of number this gate exists to
# cross-check and the one shape it cannot read. Covering that would have to tell it from a CIDR first.
# AND THIS IS A SELF-CONSISTENCY CHECK, NOT AN EFFICACY ONE. When a scorer measures the wrong population,
# its `state` and its ratio are both computed from that same wrong population, so the two agree perfectly
# while both are wrong and this gate stays quiet. Widening it would not change that. Do not read a clean
# run here as evidence that the detections themselves are right.
#
# MEASURED TRACK ONLY, and that is a correctness bound rather than a convenience. The invariant is a
# property of the `m` .. `m7` helpers, each of which splits ONE `$B $p` result into `state~detail`:
# both halves come from the same b() call, so they cannot legitimately disagree. A GOVERNANCE record's
# fields have no such relationship. `g()` emits `governance unknown ""` -- b() never ran, and
# `unknown` is not in b()'s range at all -- so there is no second projection of a governance record
# to cross-check.
#
# ORDERED AFTER THE STATE ENUM, deliberately: an out-of-enum or non-string `state` would be reported
# here as a ratio disagreement -- loud, but blaming the wrong field, the way BADENUM sits before
# BADSTATE for the same reason. The `.track` filter below is likewise safe only because the enum gate
# has already proven `track` is one of the two legal spellings; a mis-cased `measured` would otherwise
# skip this gate silently rather than being refused there.
#
# THE BUCKET RULE IS NOT RE-IMPLEMENTED HERE. It is extracted from the committed `B='def b(...)'` line
# that the scorer blocks themselves run, so this gate cannot drift from the thing it validates: a
# second hand-typed copy of b() would turn every mismatch into "the two copies disagree" rather than
# "the record is wrong". The two globs are exactly score.sh's closed allowlist of scorer files (four at
# the top level plus security/identity-access.md), and no `2>/dev/null` hides a glob that fails to
# expand -- sed's nonzero exit is caught below, because a silently partial extraction that still yields
# one value would pass this gate while having read fewer files than it claims.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # score.sh and render-report.py resolve references/ the same way
REF="$HERE/../references"
[ -d "$REF" ] || { echo "reduce.sh: cannot find $REF -- this reducer reads two things out of that" \
  "directory and keeps a private copy of neither: the scorers' own bucket rule b() for the" \
  "state<->ratio gate, and every question's severity weight from severity.md, without which there is no" \
  "weighted score to compute at all. Is the skill tree complete?" >&2
  exit 1; }
# `LC_ALL=C` IS LOAD-BEARING ON THIS LINE. BSD sed exits 1 with "RE error: illegal byte sequence" on a single
# invalid UTF-8 byte anywhere under $REF, and the refusal below would then blame a wrong file mode, a broken
# symlink or a partial checkout -- three causes a mode-644, complete, readable file does not have, sending the
# maintainer to look for something that is not there. One `\200` in severity.md is enough. With LC_ALL=C
# the byte is just a byte, the glob is read, and the parse reaches viz(), which reports it as "1 character(s)
# that a terminal does not display, the first at byte 6 (invalid UTF-8 byte \200)".
#   THE SAME HOLDS FOR EVERY TOOL THAT READS THESE FILES, not just this sed. A `cut`, `tr` or
# `sed` assembling the carriage-return figures outside the C locale fails on a file holding both an
# interior carriage return and one invalid byte, and the refusal then prints "The INTERIOR one(s)
# are on line(s): ." -- an empty list -- and tells the maintainer to fix "the line(s) named
# above". So the carriage-return gate produces its own line numbers inside a single LC_ALL=C awk,
# and nothing on that path runs in the caller's locale.
#   Do not write "this is the only X" about a tool in this file: that is a census claim, and a
# census claim is only as good as the last count. Count again whenever a tool is added rather
# than trusting one.
B_DEF=$(LC_ALL=C sed -n "s/^B='\(.*\)'$/\1/p" "$REF"/*.md "$REF"/*/*.md | sort -u) || {
  echo "reduce.sh: could not read the reference files under $REF. This glob covers severity.md as well" \
    "as the scorer files, and it is the FIRST thing to touch them, so an unreadable file (wrong mode," \
    "broken symlink, partial checkout) surfaces here whichever file it is: named below is the bucket" \
    "rule for the state<->ratio gate, but severity.md carries every question's severity weight and is" \
    "read a few gates further down. Check the modes of $REF/*.md and $REF/*/*.md before assuming this" \
    "is only about b(). Refusing rather than skipping either." >&2
  exit 1; }
# Exactly ONE distinct definition, asserted rather than assumed. Those five copies are kept in step by
# hand and nothing else diffs them, so this assertion is worth having on its own: if they ever drift,
# two pillars are bucketing the same ratio differently and there is no single b() to validate against.
B_N=$(printf '%s\n' "$B_DEF" | grep -c .)
if [ "$B_N" -ne 1 ]; then
  echo "reduce.sh: expected exactly ONE distinct \`B='def b(...)'\` bucket rule across $REF --" \
    "found $B_N. Every pillar scorer must bucket a ratio identically, and the state<->ratio gate" \
    "below has no single rule to validate against until they agree." >&2
  if [ "$B_N" -eq 0 ]; then
    echo "  No reference file carries a line matching ^B='...' -- the scorer preamble was renamed or" >&2
    echo "  reformatted. An empty rule would make the gate below accept every record, so it refuses." >&2
  else
    printf '%s\n' "$B_DEF" | head -5 | sed 's/^/  /' >&2
    echo "  Reconcile the copies (grep -n \"^B='\" in references/) so all five read identically." >&2
  fi
  exit 1
fi

# THE $PE PRELUDE MUST BE ONE LINE, asserted here because the failure is silent everywhere else.
# `PE='def gkenf: ...;def kyenf: ...;'` in references/security/identity-access.md carries the policy-engine
# predicates that four security questions call. It is consumed by TWO readers that both require a single
# line -- this file's sibling `sed -n "s/^PE='\(.*\)'$/\1/p"` idiom, and render-report.py's
# `_PRELUDE_RE = ^([A-Z][A-Z0-9_]*)='(def .*)'$` -- while the thing that RUNS it, bash, accepts a
# multi-line single-quoted assignment happily. So a `PE=` accidentally wrapped across two lines still
# scores every cluster correctly and still passes `bash -n`, and the only visible symptom is that the
# report's "Exact command used" panel quietly stops printing the definitions a reader needs to audit a
# SECURITY verdict. That combination -- correct scores, valid shell, silently degraded disclosure -- is
# why it is asserted rather than trusted. Measured: this gate fires on a deliberately split `PE=`.
# Counted across $REF rather than in one file so a second pillar adding a prelude is covered too.
# EVERY SINGLE-QUOTED UPPERCASE ASSIGNMENT IN A SCORER BLOCK, NOT JUST `PE`.
# A gate hardcoded to the literal name `PE` would cover "a second pillar adding a prelude" only
# when the new prelude was also called PE. Moving `B='`'s body to the next line in
# reliability.md would leave such a gate silent, leave render-report.py silent, leave all five pillar
# scores identical, and cut the definitions printed in the report by a quarter. `B` decides EVERY
# ratio verdict in the report, and `B_N`'s distinct-count cannot see it either: losing one of five
# identical copies still leaves one distinct definition, so only a count over every assignment
# catches the split.
#
# So the population is every column-zero `^NAME='` a reader would call an assignment, plus any INDENTED
# one whose body opens `def ` -- see "THE INDENTED HALF" below for why the indented side is bounded to
# preludes rather than taken wholesale -- and there are two requirements, because two different
# breakages matter:
#   1. it must open and close on ONE line with no leading whitespace -- `^NAME='.*'$`. The extractors are
#      all line-anchored seds and a line-anchored Python regex; bash is not, which is why a split or
#      indented assignment scores correctly and silently stops being extractable.
#   2. if its body defines anything, `def ` must come immediately after the opening quote -- one space
#      there also defeats render-report.py's `_PRELUDE_RE`.
# What this gate deliberately does NOT cover is a body that is extractable but wrong; prelude_shadow() in
# render-report.py covers that, by naming the questions whose panel would print a call with no definition.
# SCOPED TO THE SCORER BLOCK, with the same awk score.sh uses to extract it. Counting across whole files
# would pick up a remediation sample -- `REGION='<REGION>'; CLUSTER='<CLUSTER>'   # edit this line FIRST` in
# operational-excellence.md -- which is prose for a human to paste, not a scorer assignment, and which no
# extractor reads, and a whole-file count fails on a HEALTHY tree, which is the one thing a gate
# must never do. The population is exactly the text score.sh runs.
# ALL THREE READERS SHARE ONE POPULATION: the first fenced bash block. This gate, the per-file bound
# below and score.sh:109 read it, and so does render-report.py's prelude reader. A mismatch would be a hole,
# not a design, and prelude_shadow() would not cover it: it
# keys on MALFORMED assignments, not on location, so a WELL-FORMED prelude in a second fenced
# block would be in the printer's population and in no validator's. A second block containing
# `XX='def kyenf: false;'` would leave this gate at rc=0 and prelude_shadow() empty, while the panel
# would print `def kyenf: false` -- and re-running the printed program would flip all four admission questions.
# So _preludes() is scoped the same way (see _scorer_block in render-report.py), and what the report prints
# and what these gates validate are the same text.
SCORER_BLOCKS=$(awk 'FNR==1{fl=0;seen=0} /^```bash$/{if(!seen){fl=1;next}} /^```$/{if(fl){fl=0;seen=1}} fl' \
  "$REF"/*.md "$REF"/*/*.md 2>/dev/null)
# THE INDENTED HALF OF REQUIREMENT 1, AND WHY IT IS BOUNDED TO PRELUDES. Counting
# `^[[:space:]]*[A-Z][A-Z0-9_]*='` is not counting "an assignment a reader would call a prelude" -- it is
# any indented uppercase single-quoted assignment, including an ordinary shell local inside a helper.
# Inserting `  LOCALSEP='|'` into `emit()` would make such a gate exit 1 with a prelude error on a tree
# whose scores are identical. Counting column zero only is no answer either: SEEN and OK would then
# both be computed from the SAME column-zero pattern, so indenting an assignment would drop it out of
# BOTH counts and they would stay equal. That gate can only ever catch a SPLIT assignment, never an
# INDENTED one.
# It matters most on references/security/identity-access.md, the
# only file with three column-zero assignments and therefore the only one where the per-file `_n >= 2`
# bound below does not catch it anyway: one space before `PE='def gkenf...'`, or before `B='def b(...'`,
# would leave such a gate at rc=0 with 0 bytes of stderr, the published score unmoved and scores.json
# byte-identical to an unedited tree, while the report stops printing the definition it needed.
# So the indented side is counted in, bounded to PRELUDES -- a body opening `def ` -- which is the
# axis `DEF_SEEN`/`DEF_OK` already keys on 12 lines below, and which excludes `  LOCALSEP='|'` by
# construction rather than by luck about what the tree happens to contain. The message below names
# exactly these two patterns and claims nothing wider. What is deliberately NOT covered is an
# indented assignment whose body is not a definition (`  RQ='|if ...'`): render-report.py's `_PRELUDE_RE`
# reads only `def `-bodied assignments, so indenting one changes no byte of the report -- measured, reduce
# rc=0, render rc=0 and out.html byte-identical to pristine. A split `RQ='` is still caught, here and per
# file, because an orphan `RQ='` matches `^NAME='` and not `^NAME='.*'$`.
ASSIGN_SEEN=$(printf '%s\n' "$SCORER_BLOCKS" \
  | grep -c -e "^[A-Z][A-Z0-9_]*='" -e "^[[:space:]]\{1,\}[A-Z][A-Z0-9_]*='def " || true)
ASSIGN_OK=$(printf '%s\n' "$SCORER_BLOCKS" | grep -c "^[A-Z][A-Z0-9_]*='.*'$" || true)
# A LOWER BOUND, not merely an equality: every comparison below is between two counts, and two zeroes are
# equal, so an empty population would satisfy all of them. `SCORER_BLOCKS` is awk-scoped to the first
# ```bash fence per file, so renaming that fence to ```sh empties it and every assertion here would pass
# vacuously, together with a split `B='`, at rc=0. render-report.py still refuses that tree, so
# this is defence in depth rather than the only guard, but a gate that cannot tell "nothing wrong" from
# "nothing looked at" is not one.
# PER FILE, OVER THE FIVE PATHS score.sh NAMES -- not over whatever the directory happens to contain, and
# not discriminated on file content. Keying on `W=` is wrong in both directions:
# inside the extracted block it is circular (a renamed fence empties the block, the key vanishes and the file
# skips itself), and in the RAW file it false-positives on `severity.md` the moment a line
# beginning `W=` appears in prose, and can still be evaded by indenting `W="$WORK"` by one space while
# renaming that file's fence. The list below is the same closed set score.sh's `case` accepts, so the check
# governs exactly the five files that are executed and nothing else can enter or leave the population.
# The counted assignments are `B='` and `RQ='`: `W="$WORK"` is DOUBLE-quoted and is not in this population,
# so do not describe the floor as "at least `W=` and `B='...'`".
for _ref in operational-excellence.md security/identity-access.md reliability.md \
            performance-efficiency.md cost-optimization.md; do
  if [ ! -f "$REF/$_ref" ]; then
    echo "reduce.sh: $REF/$_ref is missing -- score.sh names it as a pillar scorer, so a review cannot" \
      "complete without it and the gates below would pass on four fifths of the detections." >&2
    exit 1
  fi
  _blk=$(awk '/^```bash$/{fl=1;next} /^```$/{if(fl)exit} fl' "$REF/$_ref")
  _n=$(printf '%s\n' "$_blk" | grep -c "^[A-Z][A-Z0-9_]*='" || true)
  if [ "${_n:-0}" -lt 2 ]; then
    echo "reduce.sh: $REF/$_ref yields only ${_n:-0} column-zero single-quoted assignment(s) from its first" \
      "fenced bash block -- every pillar file assigns at least \`B='...'\` and \`RQ='...'\` there. Either" \
      "the fence was renamed or reformatted, or an assignment was indented or split; either way this file's" \
      "detections were not read as score.sh will read them. Refusing rather than passing on a partial read." >&2
    exit 1
  fi
done
unset _ref _blk _n
# ORDERING NOTE: this arm is a backstop, not the thing that catches a renamed fence. The per-file
# loop above refuses unless
# EVERY one of the five pillar files yields at least 2 column-zero assignments, and those five `_blk`
# slices are disjoint subsets of `$SCORER_BLOCKS` counted by one of the same two patterns `ASSIGN_SEEN`
# uses -- so once the loop passes, ASSIGN_SEEN is at least 10 and neither half of the condition below can
# be true. Each of these hostile trees -- all five ```bash fences renamed to ```sh, one
# renamed, CRLF endings, a deleted pillar file, every `B=`/`RQ=`/`PE=` line deleted, every assignment
# indented -- is refused earlier, by the `B_N` distinct-count gate or by the loop. Keep it -- it
# costs nothing and the ordering above it is not guaranteed forever -- but do not read it as the guard
# that makes a vacuous pass impossible. That is the loop.
if [ -z "$SCORER_BLOCKS" ] || [ "$ASSIGN_SEEN" -lt 5 ]; then
  echo "reduce.sh: extracted $ASSIGN_SEEN scorer assignment(s) -- lines matching \`^NAME='\` or" \
    "\`^<space>NAME='def \` -- from the fenced blocks in $REF, which cannot be right: each of the five" \
    "pillar files assigns at least \`B='...'\` and \`RQ='...'\` at column zero. (NOT \`W=\`, which" \
    "is never counted: every copy of it is written \`W=\"\$WORK\"\` with DOUBLE quotes, so" \
    "no pattern here counts it.)" \
    "The extraction broke (a renamed or reformatted \`\`\`bash fence is the usual cause), so NOTHING" \
    "below was checked. Refusing rather than reporting a vacuous pass." >&2
  exit 1
fi
if [ "$ASSIGN_SEEN" -ne "$ASSIGN_OK" ]; then
  echo "reduce.sh: a scorer assignment in $REF does not open and close on ONE line with no leading" \
    "whitespace -- found $ASSIGN_SEEN line(s) matching \`^NAME='\` or \`^<space>NAME='def \` but only" \
    "$ASSIGN_OK matching \`^NAME='...'\$\`." >&2
  echo "  bash accepts a multi-line or indented single-quoted assignment, so every score stays correct" >&2
  echo "  and \`bash -n\` stays quiet. What breaks is the extraction: this file's sed, score.sh's, and" >&2
  echo "  render-report.py's _PRELUDE_RE are all line-anchored, so the report prints the \`b(...)\`," >&2
  echo "  \`gkenf\` or \`kyenf\` CALL with no definition and a reader cannot re-run the verdict." >&2
  echo "  Inspect with: grep -rn \"^[[:space:]]*[A-Z][A-Z0-9_]*='\" $REF" >&2
  exit 1
fi
DEF_SEEN=$(printf '%s\n' "$SCORER_BLOCKS" | grep -c "^[A-Z][A-Z0-9_]*='.*def " || true)
DEF_OK=$(printf '%s\n' "$SCORER_BLOCKS" | grep -c "^[A-Z][A-Z0-9_]*='def " || true)
if [ "$DEF_SEEN" -ne "$DEF_OK" ]; then
  echo "reduce.sh: a scorer prelude in $REF does not put \`def\` immediately after its opening quote --" \
    "found $DEF_SEEN prelude assignment(s) but only $DEF_OK starting \`'def \`." >&2
  echo "  render-report.py's _PRELUDE_RE requires \`'(def .*)'\`, so one space between the quote and" >&2
  echo "  \`def\` silently stops the report printing the definitions its scorers call." >&2
  exit 1
fi

# The ids below legitimately publish a state their leading ratio does not imply. Each reason was
# read out of the scorer itself, and each shape below reproduces it; none is a placeholder for
# a question someone could not make pass.
#   podsec-2   The ratio counts unprivileged workload containers; the state is not banded, because any
#              privileged container fails the question. A shape with one privileged container among 18
#              publishes `none` beside "17/18 nonpriv (workloads) — 1 container(s) run privileged", where
#              b(17;18) is `all`. (A shape with no privileged container publishes `all` beside 18/18,
#              which agrees with b() and needs no exemption.)
#   podsec-1, podsec-3, podsec-4, podsec-5  Not banded either, for the same reason as podsec-2: one
#              offender fails the question -- a container not set to run as non-root (podsec-1), a pod
#              with a hostPath volume (podsec-3), a container adding a capability outside the Pod
#              Security Standards Baseline allowlist (podsec-4), a container not dropping ALL
#              (podsec-5). A shape with one root container among 18 publishes `none` beside "17/18
#              nonroot (workloads) — 1 container(s) not set to run as non-root", where b(17;18) is
#              `all`; with no offender each publishes `all` beside m/m, which agrees with b().
RATIO_STATE_EXEMPT="podsec-2 podsec-1 podsec-3 podsec-4 podsec-5"

# `|| exit 1` on the jq itself, not just on its output. A jq that dies leaves BADRATIO empty, which is
# indistinguishable from "nothing was wrong" -- a gate whose jq carries a syntax error would
# report every run clean while never running. A check that cannot run must not report a pass.
BADRATIO=$(jq -r --arg exempt "$RATIO_STATE_EXEMPT" "$B_DEF"'
  ($exempt|split(" ")) as $ex
  | select(.track=="measured" and ((.detail|type)=="string") and ((.id|IN($ex[]))|not))
  | (.detail|capture("^(?<n>[0-9]+)/(?<t>[0-9]+)")) as $c
  | ($c.n|tonumber) as $n | ($c.t|tonumber) as $t
  | select(.state != b($n;$t))
  | "\(.id) state=\(.state) but detail leads \($n)/\($t), which b() buckets as \(b($n;$t))" +
    " -- \(.detail[0:60])"
' "$W/results.jsonl") || {
  echo "reduce.sh: the state<->ratio gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked. Refusing rather than publishing a score" \
    "whose only guard was silently skipped." >&2
  exit 1; }
if [ -n "$BADRATIO" ]; then
  echo "reduce.sh: record(s) in $W/results.jsonl whose state contradicts the ratio in their own" \
    "detail -- when detail leads with n/m, state must be b(n;m)" >&2
  printf '%s\n' "$BADRATIO" | head -5 | sed 's/^/  /' >&2
  echo "  b() is the scorers' own bucket rule, read from references/ rather than restated here:" >&2
  echo "  >=90% all, >=70% most, any pass some, none at zero passes, na at a zero denominator." >&2
  echo "  A record answering one way in its state and another in its detail moves the published score" >&2
  echo "  while the evidence printed beside it says otherwise, so it is refused rather than resolved" >&2
  echo "  in either direction. Re-run the pillar scorers, which derive both from one measurement." >&2
  echo "  If a scorer LEGITIMATELY publishes a state its leading ratio does not imply -- a capped band," >&2
  echo "  a second axis, or a rule that is not banded -- add its id to RATIO_STATE_EXEMPT in this file" >&2
  echo "  with a sentence saying why. Do not widen the rule to make one question quiet." >&2
  exit 1
fi

# ── SEVERITY WEIGHTS -- PARSED FROM references/severity.md ─────────────────────────────────────────
# The header note at the top of this file carries the argument for why the map is not written here. This
# is the parse. THE GRAMMAR IS CLOSED AND NARROW, because it is the price of using a document written
# for humans as a machine interface:
#
#   `### High` / `### Medium` / `### Low`   opens a tier (3 / 2 / 1) and must own EXACTLY ONE
#                                           well-formed table: an `| ID | ... |` header row, a `|----|`
#                                           separator, then one or more data rows. The tier closes at the
#                                           next heading of any kind, or at the first non-table line once
#                                           any table line has been read under it -- header and separator
#                                           included, so the closer is armed before the first data row.
#                                           The CLOSED ATX spelling (`### Medium ###`, space before the
#                                           closing run) is the same heading in GFM and is accepted; four
#                                           or more columns of indentation makes it a code block in GFM
#                                           and is refused. See HEADING SYNTAX below for the exact
#                                           boundary and why it sits where it does.
#   | <ID cell> | ... |                     a data row. The FIRST cell is the only one read, so an id
#                                           mentioned in the prose of the third cell (net-4's row names
#                                           sec-31) is not a row and does not become a weight.
#   ID cell                                 `sec-12`, or a ` / `-separated list of ids sharing one
#                                           rationale (`sec-27 / sec-28`), or a contiguous range
#                                           (`fargate-1..2`). Anything else in that cell is a REFUSAL,
#                                           not a skipped row -- silently skipping is how a question
#                                           loses its documented weight and falls back to a default.
#
# THE RULE THAT DECIDES A WEIGHT, stated once so the gaps can be reasoned about instead of enumerated:
#
#     a data row's tier is the tier of the NEAREST PRECEDING `### High|Medium|Low` heading, provided the
#     tier is still open when the row is read.
#
# ANY edit that changes which heading that is -- retyping one, deleting one, INSERTING one, or moving the
# row -- changes the weight. That is the whole mechanism, and it is why this parse is gated in three
# structural ways rather than one. Each gate answers an edit whose ungated effect can be reproduced, not one
# imagined:
#
#   TIER CLOSES AT THE END OF ITS TABLE. Closing a tier only at the next heading does
#   not catch a table drifting out from under its tier: DELETING a `### Medium` line
#   would leave its table under the still-open `### High` above it. To reproduce the
#   effect, build a STAND-ALONE PERMISSIVE PARSER, stated here so it can be rebuilt:
#   the nearest-preceding-heading rule and nothing else -- a tier is opened by
#   `### High|Medium|Low`, closed only by the NEXT heading of any kind, and every
#   `|`-leading line under an open tier contributes its first id-shaped cell; no
#   table-end closer, no header-row requirement, no owns-a-row requirement, no
#   indentation rule, no refusals. What makes it a valid stand-in is that on the
#   shipped severity.md it produces a map byte-identical to this parser's (compare the
#   `.severity` sha256 of both), so the two differ only in what they refuse. Run over
#   any collected work dir, deleting the one `### Medium` line of Security re-weights
#   every row of that table (`adm-1`, for one, goes from weight 2 to 3) and can move
#   the Security and overall scores; deleting all five (one per pillar) re-weights far
#   more and can move a pillar score UP as well as down, which is the direction nobody
#   audits. Both happen at EXIT 0 with no diagnostic under the permissive parser.
#   Under this one the orphaned table's first data row is read under no tier and
#   refused.
#
#   A TIER'S TABLE MUST START WITH ITS HEADER ROW. Closing the tier at the table end still misses the
#   mirror-image edit: INSERTING `### Low` into the middle of an existing table re-tiers every row below the
#   insertion point. Under a parser without this rule, one `### Low` inserted above `| sec-9 |` drops every
#   row below it from weight 2 to weight 1 and moves the Security score, at EXIT 0 with no diagnostic. The
#   document is visibly broken -- the rows below have lost their header row, so markdown renders them as
#   literal pipes -- while the published score would move quietly. So a tier's table must begin with the
#   `| ID | ...` header; a heading whose table starts at a data row is refused and names the insertion.
#
#   A TIER MUST OWN AT LEAST ONE DATA ROW. That closes the last placement of the same edit: inserting a
#   heading directly ABOVE another table's header row passes the header check (the new tier gets a
#   well-formed table) but leaves the heading above owning nothing. A tier with no data rows is refused.
#
# SOME OF THESE REQUIREMENTS ARE GFM, SOME ARE THIS PROJECT'S. Worth separating, because the argument
# above leans on "the document is visibly broken" for its authority and that is only true of the GFM
# ones. GFM-aligned: a header row must be followed by a delimiter row WHOSE CELL COUNT MATCHES IT, and
# the rows below a mid-table insertion stop being table rows. (The cell-count half is checked -- see the
# `want == 2` branch -- because without it one edit could remove a whole severity table from the
# rendered document in silence.) PROJECT INVARIANTS, stricter than GFM, are THREE: the header's first
# cell must be literally `ID`; a tier heading must own at least one data row; and EVERY TABLE LINE MUST
# BEGIN WITH `|`. Keep that third one on this list: a refusal it causes must name it, not three causes
# the edit does not have. GFM lets a row omit its outer pipes, so `sec-21 | ... | ... |` renders
# IDENTICALLY to the piped form -- 15 tables / 134 rows in both renderers, byte-identical to the
# unedited file -- and this parser refuses it anyway, because the leading `|` is the only thing that
# tells a table line from prose here. Refusing is the choice; naming the true reason for the refusal is
# not optional. GFM is perfectly happy with a `| Question | ... |` header, with two consecutive
# `### Low` headings, and with a heading as the last line of the file; this parser refuses all three
# even though a looser parse would still produce a correct map. They are refused because in THIS file
# each one is a documentation defect.
#
# WHAT TELLS A HEADER ROW FROM A DATA ROW IS THE DELIMITER ROW IN POSITION 2, not the `ID` cell.
# GFM mandates that delimiter row and no data row in this file is shaped like one, so position
# alone decides: first table line under a tier is the header, second is the delimiter, the rest
# are data. The `ID` literal is not what makes the distinction possible, and the counterfactual
# is one line: delete the `if (cell == "ID")` test so `want == 1` accepts any first table line,
# and every structural accident above is STILL refused -- insertions at six positions, both
# heading deletions, a blank line inside a table, a preamble foreign table, a header-only foreign
# table and a mid-table insertion, twelve for twelve, three of them merely refused by a different
# rule and message. The inputs the `ID` test adds are at least FIVE classes; read FIVE as a count
# of what is known and not as a closed set. The variant is one substitution, so this is
# reproducible:
#     sed 's/if (cell == "ID") { want = 2;/if (1) { want = 2;/' reduce.sh
# Run against that variant, these five flip REFUSED -> ACCEPTED: a RENAMED but correct header
# (`| Question | Check | ... |`); a header whose COLUMNS WERE REORDERED (`| Check | ID | ... |`); a header
# whose cells were EDITED INTO DELIMITER SHAPE; a header whose first cell is EMPTY (`|  | Check | ... |`);
# and a header whose first cell is BACKTICKED (`` | `ID` | Check | ... | ``). All five then map
# IDENTICALLY to the unedited file, so the conclusion does not depend on the count. So the `ID` cell buys
# naming consistency in this
# file and a better diagnostic, which is reason enough to keep it. It does not buy the header/data
# distinction, and a necessity claim that survives deleting the thing it is about is not a necessity
# claim.
#
# HEADING SYNTAX IS GFM'S, IN BOTH DIRECTIONS. The tier-heading match accepts a CLOSED ATX heading --
# `### Medium ###`, `### Medium #`, `### Medium ######`, `###  Medium  ###`, trailing whitespace after the
# closing run -- because CommonMark and GFM define each of those as the same heading as `### Medium`.
# Refusing them would produce a diagnostic telling the editor that a visibly present, visibly correct
# heading had been "DELETED or RETYPED".
#   It refuses `### Medium###`: CommonMark requires the closing run to be preceded by whitespace, and
# without it the heading TEXT is literally `Medium###`. Accepting that would be a SILENT MISPARSE, which is
# the worse direction, so the group is `([ \t]* +#+)?` and deliberately not `[ \t]*#*[ \t]*$`.
# `### Medium #x`, `### Medium ### #` and `### Medium ### x` are refused for the same reason: their heading
# text is `Medium #x`, `Medium ###` and `Medium ### x`, not `Medium`.
#   THE WHITESPACE RUN BEFORE THE CLOSING `#` RUN MUST END IN A SPACE. It may contain tabs; it may not end
# in one. CommonMark 0.31 allows spaces or tabs before the closing run; the earlier rule allowed spaces
# only, and renderers still implement both. A run that ends in a tab (`### Medium<TAB>###`) therefore has
# no single correct reading -- the heading text is `Medium` under one rule and `Medium<TAB>###` under the
# other -- and a spelling with no single correct reading is exactly the case the "no silent misparse" rule
# exists for. A run that contains tabs but ends in a space is the same heading under both rules, so it is
# accepted. `([ \t]* +#+)?` is the exact expression of that rule. The two nearby expressions each err in a
# different direction: `([ \t]+#+)?` accepts the tab-ending run, and `( +#+)?` falsely refuses every
# tab-bearing run that ends in a space (`### Medium<TAB> ###`, `###<TAB>High<TAB> #`, ...). A NBSP, a
# vertical tab or a form feed before the run is not GFM whitespace, so it is refused.
#   NOT overstated: the tab form is not a silent re-tiering vector. `### Low<TAB>###` does move the map to
# Low, but every renderer shows a reader the word `Low`, so the rendered view still discloses the tier.
# The case for refusing a run that ends in a tab is the absence of a single correct reading, not score risk.
#   AND IT REFUSES A TIER HEADING INDENTED FOUR OR MORE COLUMNS, tabs counted to a stop of 4. That is the
# one place a parser that trims before matching would be LAXER than GFM rather than stricter:
# `    ### Medium` and a tab-indented one would both open a tier, while GFM makes four columns an
# indented CODE BLOCK -- verified, `    ### Medium` renders `<pre><code>### Medium</code></pre>` and
# three spaces still render `<h3>Medium</h3>`, so three are still accepted here. Indentation alone never
# moves the map, so this is not a third silent re-tiering mechanism; it COMPOUNDS the two that exist.
# Retyping `### Medium` to `    ### Low` would file those rows as Low while the rendered document emits
# no heading at all, so a reader sees them continuing under the `### High` above while the Security and
# overall scores move. That defeats the second prong of the residual-risk mitigation below: reading a
# severity.md DIFF still works, but "a reader of the RENDERED severity.md can see which tier each
# question is filed under" does not, because the indentation hides the retyped heading from the rendered
# view.
#   REFUSING THE INDENTATION NARROWS THAT PRONG; IT DOES NOT RESTORE IT, and the difference is worth being
# exact about because the rest of this comment leans on the prong. Two counts are easy to conflate. The
# SILENT RE-TIERINGS are two (heading retype into another valid tier heading, row moved between tables). The
# edits that make the RENDERED file disagree with the parsed tier -- or drop rows out of it -- are a
# DIFFERENT set, and TWENTY-NINE of them are recorded below (22 accepted + 7 refused; add the lists up
# rather than trusting this number).
#   THAT NUMBER IS A COUNT OF WHAT IS KNOWN AND NOTHING MORE. Any new kind
# of input can add to it without a single change to the code, so treat the
# true number as larger. The set is NOT closed and nothing here should imply
# it is. Do not RANK them either: a ranking of this set is falsified by the
# next input nobody thought of. And ADD THE LISTS UP rather than writing a
# total from memory: a total written from memory drifts from its own
# enumeration.
#   RENDERER OPTIONS MATTER HERE. Whether a renderer passes raw HTML through, escapes it, or lets a
# container absorb the lines that follow it changes what several of the edits below do to the rendered
# file, so each is recorded by its mechanism and the ways renderers differ on it. The unedited file is
# 15 tables / 134 rows.
#   SEVEN ARE REFUSED: an UNTERMINATED code fence (the fence-state gate
# above, which tracks fence state because a parity test misses three
# two-keystroke forms); a tier heading indented four or more columns; a
# delimiter row whose cell count stops matching its header; and the four
# table-line indentations -- a data row at 4 spaces or 1 tab (that row and
# every row below it in its table -- as many as 20, the largest table here),
# a header row or a delimiter row at 4 spaces (14 tables / 118 rows, the
# whole table gone).
#   WHAT REMAINS ACCEPTED IS BEST STATED AS A RULE, NOT A RANKED LIST.
# Any ranking of this census is falsified by the next input nobody
# thought of, so none is given. The rule, which every known case is
# consistent with:
#
#     ANY single line inserted between a tier heading and its table is accepted in silence, and the damage it
#     does to the rendered document depends on the renderer and its options rather than on how exotic the line
#     is. ANY fence is accepted in silence unless the fence-state gate above catches it.
#
# TWENTY-TWO instances are recorded, and the count is derived by adding up the
# list: 8 container + 8 raw HTML + 2 no-markup + 1 retype + 1 entity + 2
# fence-inside-another-construct = 22. If you edit the list, re-add it. They
# are recorded for their MECHANISMS, not as an ordering, and the set is not
# closed:
#     CONTAINER MARKUP, plain markdown -- `> Low`, `- Low`, `* Low`, `+ Low`, `1. Low`, `> - Low`,
#       `>> Low`, `> > > Low`. A renderer that lets the container absorb the table after it swallows
#       the whole Security `### High` table into it -- all 15 High-severity questions gone from the
#       reader -- while another keeps the table. Renderers DISAGREE on all eight.
#     RAW HTML -- `<h3>Low</h3>`, `<div>`, `<p>Low</p>`, `<details>`, `<br>`, `<hr>`: harmless where raw
#       HTML is escaped; where it is passed through, the Security High table can be absorbed into the HTML
#       block. `<table><tr><td>Low</td></tr></table>` passed through REPLACES the Security High table with a
#       one-row fake. `<!-- x` unterminated, passed through, hides every table after it.
#     NO MARKUP AT ALL -- a SETEXT underline (`Low` then `---`) and a bare paragraph `Low`: every table
#       still renders; the document shows a tier word above a table filed at a different tier.
#     NOT AN INSERTION -- retyping `Why High` to `Why Low` in a HEADER row: every table still renders, and
#       the rendered table then names one tier while the published weight is another.
#     A FENCE INSIDE ANOTHER CONSTRUCT, which the fence-state gate refuses while the document may be
#       unharmed -- a fence between `<!--` and `-->` (a commented-out example) is inert in a renderer that
#       passes raw HTML through and opens a code block in one that escapes it; a fence inside a multi-line
#       link-reference-definition title is absorbed into the title by some renderers and opens a code
#       block in others. Place the construct at a block start: mid-paragraph, `[ref]:` is not a
#       link-reference definition at all, and the fence is then a bare unterminated fence. These are in
#       the ACCEPTED column for the renderers that ignore them and in the REFUSED column for this parser,
#       which is the one place those two columns overlap. The gate models neither construct and its
#       damage clause says so.
#     AN HTML ENTITY, WHICH DEFEATS THE RESIDUAL-RISK ARGUMENT ITSELF -- `| ID | Check | Why &#76;ow |` is
#       accepted, and a renderer that decodes the entity shows `<th>Why Low</th>` under `<h3>High</h3>`.
#       The mitigation this whole comment leans on is "read a severity.md DIFF as a score change" -- and
#       `Why &#76;ow` is not text a human reads as "Low". The rendered view and the diff can disagree in
#       BOTH directions at once.
# None of the twenty-two moves a score, which is why no gate here sees them -- and it is also why they are more
# dangerous to a READER than to a score.
#   ONE CASE IS NOT A WORDING PROBLEM AND IS DISCLOSED RATHER THAN GUARDED: a bare ZERO WIDTH SPACE
# (U+200B) on a line of its own between two data rows. This parser reads it as a non-table line, closes the
# tier and refuses the nine rows below it as belonging to no tier -- while a GFM renderer keeps every one of
# the 134 original rows inside the table and adds the ZWSP line as a 135th (15 tables / 135 rows). So the
# parser and the renderer DISAGREE ABOUT THE STRUCTURE
# OF THE DOCUMENT, not merely about how to describe it, and the rows the parser calls orphaned are visibly
# under `### High` to any reader.
#   THE DECISION IS DISCLOSURE, NOT A GUARD, and the reasoning is worth keeping because the opposite
# choice is tempting. A guard could go two ways and both are worse. ACCEPTING the line would mean
# treating an invisible character as though it were not there, which is the silent-misparse direction
# this file refuses everywhere else -- and it would have to decide which invisible characters are
# ignorable, an unbounded question. Giving it a DEDICATED refusal changes nothing about the outcome: it
# is already refused, by the correct rule (a line in a table that does not begin with `|`), at exit 1,
# with the rows named. What matters is that the quoted evidence is not INVISIBLE, or the reader sees a
# complaint about an apparently empty line, so viz() names the character and its byte offset. viz() also
# names variation selectors and three classes of invalid UTF-8 beyond the ZWSP, but not every invisible
# character is enumerated, so no completeness claim is made here; see viz() itself for what it does and
# does not claim.
# What remains true and is recorded rather than fixed: on this input the rendered document does not disclose
# the problem, so it is a member of the accepted-but-invisible class above in every respect except that the
# parser happens to refuse it. A form feed, a vertical tab and a NBSP on a bare line behave the same way in
# this parser and differ between renderers (some drop the rows, some keep them).
# So: READING THE severity.md DIFF IS THE PRONG THAT HOLDS. The rendered view is a convenience that two
# known single edits still defeat; do not treat it as the check.
#
# WHAT REMAINS UNCAUGHT, by construction and not by omission: any edit that leaves EVERY tier heading
# owning a structurally complete table while changing which heading is nearest to a row. Retyping
# `### Medium` as `### Low` and moving a row from one table to another are two instances; the set is
# defined by that property, not by that list. Those are honoured silently and must be -- they are
# indistinguishable from a deliberate re-tiering, which is the entire point of this file being the source
# of truth. No gate can separate them from intent; only reading the severity.md diff can. READ A
# severity.md DIFF AS A SCORE CHANGE.
#
# FENCED CODE BLOCKS AND HTML COMMENTS are not understood, and that has a consequence: a ``` fence or an
# <!-- --> line is a non-table line, so it TERMINATES the tier whose table it interrupts, and any
# `|`-leading line inside it is read as a table row. A fence or comment placed INSIDE a severity table
# therefore refuses -- but WHICH gate refuses it depends on whether the fence is closed. A CLOSED pair inside
# a table refuses via the no-tier rule, because the interruption closed the tier and orphaned the rows below
# it. An UNTERMINATED fence is caught earlier, by the fence-state gate above, with a fence message and the
# count of table lines it swallows; the parse never runs. Either way it is refused rather than skipped.
#   THE OTHER PLACEMENT BEHAVES THE OPPOSITE WAY and the difference is worth stating, because it is easy
# to assume the first mechanism for both. A fence carrying its OWN `### Low` heading and its own table
# raises NOTHING here: the fenced heading opens a tier and the fenced id becomes a real weight (measured,
# 133 rows parsed instead of 132, zero complaints from this parse), while the renderer shows the whole
# block as code and 15 tables / 134 rows. It is still refused, but two gates later and by a different one
# -- the staleness gate, because the fenced id documents a question nothing emits. An id that HAPPENS to
# be a live question is NOT silent as a single edit: the real row is still there, so the fenced row is a
# SECOND row for that id and the duplicate-id gate refuses it BY NAME -- measured, "sec-21 has 2 rows,
# weight(s) 1 3". It goes silent only when the real row is deleted TOO, and then it moves the score: a
# fenced `### Low` table carrying `| sec-21 |` with the real High row removed gives EXIT 0, a changed map
# and a moved score, with the whole edit invisible inside a code fence. That is a two-part edit, not one
# keystroke, but it is the reason to keep tables and tier headings out of code fences. The file has none
# today.
#
# Weights can only ever be 1, 2 or 3 because they come from the tier heading, never from the row, so
# there is no numeric validation to do here. NOTE that this is the one thing severity.md does NOT own:
# the tier -> number mapping lives in `tier = 3/2/1` below, in render-report.py's `(1, 2, 3)` validator,
# and in prose in severity.md and SKILL.md. severity.md is the single source of WHICH TIER a question is
# in, not of what a tier is worth. Those four are constants, not per-question data, and nothing enforces
# that they agree.
SEV_MD="$REF/severity.md"
[ -f "$SEV_MD" ] || { echo "reduce.sh: cannot find $SEV_MD -- the severity weight of every question is" \
  "read from that file and this reducer keeps no copy of it, so there is no weighted score to compute" \
  "without it. Restore it from the skill tree; do not proceed with a default weight." >&2; exit 1; }
# CARRIAGE RETURNS GET THEIR OWN NAME, BEFORE THE PARSE -- AND THE MESSAGE BRANCHES, because the two ways a
# `\r` gets into this file have OPPOSITE consequences and one message would assert the first for both.
#   LINE ENDINGS (every line ends with `\r`). A CRLF copy renders IDENTICALLY to pristine in both renderers
# (measured: 15 tables / 134 rows), so nothing a reader sees is wrong -- but the trailing `\r` defeats the
# `[ \t]*$` anchor of the tier-heading match, so NO tier opens. Without this gate the result is exit 1 with
# one complaint per table line (149 on the shipped file), every one about a missing tier heading, zero rows
# parsed, and not one containing the string "CRLF". A maintainer who saved the file from a Windows editor
# would have no path from that output to the cause.
#   A STRAY `\r` INSIDE ONE CELL. The headings are INTACT and every one of them still parses -- measured, 15
# `<h3>` elements, all reading High/Medium/Low -- and the rendered document is NOT normal: the `\r` splits
# the row, so it renders 135 rows instead of 134. Telling that editor their headings are unrecognisable and
# their document looks fine is false on both halves, so this arm names the line numbers and says what
# actually happens. Both arms exist because the fix differs: one is an editor setting, the other is one
# character in one cell.
#   Either way, each complaint that QUOTED a line would have quoted its `\r` too, which returns the terminal
# cursor to column 0 and lets the rest of the message overwrite the evidence -- which is why this runs before
# the parse rather than being left to it.
# ── AN UNTERMINATED CODE FENCE DESTROYS THE RENDERED FILE ──────────────────────────────────────────
# ONE `` ``` `` LINE, anywhere, at exit 0 with the weight map byte-identical: measured, a single fence
# inserted between `### High` and its header row -- or in the preamble -- renders the file as ZERO TABLES AND
# ZERO ROWS -- a CommonMark renderer reads everything after an unclosed fence as code -- against pristine
# 15 tables / 134 `<tr>`. Every severity weight disappears from the only view a reader ever gets, while this
# parser reports perfect health, because a fence is just a non-table line to it.
#   A PARITY TEST WOULD HAVE THE SAME HOLE, reachable in two keystrokes. An EVEN count of fence lines proves
# nothing, because CommonMark closes a fence only with THE SAME CHARACTER, a run AT LEAST AS LONG, and NO
# INFO STRING on the closer. Measured, all three at exit 0 with the map unchanged and the document at 0
# tables / 0 rows: `` ``` `` followed by `~~~`; ```` ```` ```` followed by `` ``` ``; and
# `` ```bash `` followed by `` ```bash ``. A count cannot express the invariant. The invariant is IS THE
# FENCE STACK EMPTY AT EOF, so the gate below tracks fence STATE.
#   WHAT IT IMPLEMENTS, from CommonMark: an OPENER is a line indented at most 3 columns whose first
# non-whitespace run is 3 or more backticks or 3 or more tildes; a backtick opener may not carry a backtick in
# its info string. A CLOSER is a line indented at most 3 columns, of the SAME character, with a run AT LEAST
# AS LONG as the opener, and NOTHING but whitespace after that run. Fences do not nest, so one piece of state
# is enough. If an opener is still open at EOF the gate refuses and NAMES THE OPENER LINE.
#   THE DAMAGE CLAUSE IS DERIVED, NOT ASSERTED. Asserting 0 tables / 0 rows for every unterminated fence
# would be false whenever the fence sits at or after the last table -- a fence at EOF renders 15 / 134 and
# changes nothing. So the gate counts the `|`-leading lines that FOLLOW the opener and reports that count:
# those are the table lines the code block swallows, and it is a fact about this file rather than a figure
# carried over from a different one.
#   Safe by measurement: pristine severity.md contains ZERO fence lines of any kind.
FENCE_OPEN=$(LC_ALL=C awk '
  {
    fl = $0; sub(/\r$/, "", fl)
    find = 0
    for (fi = 1; fi <= length(fl); fi++) {
      fc = substr(fl, fi, 1)
      if (fc == " ") find++; else if (fc == "\t") find += 4 - (find % 4); else break
    }
    ft = fl; sub(/^[ \t]+/, "", ft)
    fch = substr(ft, 1, 1)
    if (find <= 3 && (fch == "`" || fch == "~")) {
      frun = 0
      while (substr(ft, frun + 1, 1) == fch) frun++
      if (frun >= 3) {
        frest = substr(ft, frun + 1)
        if (opench == "") {
          # A backtick opener may not have a backtick in its info string (CommonMark); a tilde one may.
          if (fch == "`" && index(frest, "`") > 0) next
          opench = fch; openrun = frun; openline = NR; openpipes = 0
          next
        }
        sub(/[ \t]+$/, "", frest)
        if (fch == opench && frun >= openrun && frest == "") { opench = ""; next }
        next
      }
    }
    if (opench != "" && ft ~ /^\|/) openpipes++
  }
  END { if (opench != "") print openline "\t" opench "\t" openrun "\t" openpipes }
' "$SEV_MD") || {
  echo "reduce.sh: could not scan $SEV_MD for code fences -- awk exited nonzero, so the unterminated-fence" \
    "check did NOT run. Its stderr is not sent to /dev/null, because a dead awk would then look exactly" \
    "like a file with no open fence: the gate keys on FENCE_OPEN being non-empty, so it would be" \
    "skipped in SILENCE. Any message awk printed is above; the carriage-return scan below is guarded" \
    "the same way." >&2
  exit 1; }
if [ -n "$FENCE_OPEN" ]; then
  F_LINE=$(printf '%s' "$FENCE_OPEN" | cut -f1)
  F_CH=$(printf '%s'   "$FENCE_OPEN" | cut -f2)
  F_RUN=$(printf '%s'  "$FENCE_OPEN" | cut -f3)
  F_PIPES=$(printf '%s' "$FENCE_OPEN" | cut -f4)
  # THE DAMAGE CLAUSE IS DERIVED FROM WHERE THE FENCE IS. A fence at or after the last table swallows
  # nothing and the document renders unchanged -- measured, a fence appended at EOF gives 15 tables / 134
  # `<tr>`, identical to pristine -- so asserting lost tables there would be a false clause in a refusal
  # whose whole purpose is to be true. With table lines after it the count is exact and reported as a count.
  if [ "${F_PIPES:-0}" -eq 0 ]; then
    FENCE_DAMAGE="No table line follows it, so the rendered document is unaffected TODAY and this is refused\
 as a latent defect: the next row or table added below line $F_LINE disappears from the rendered file with no\
 other sign, because this reducer would still read it."
  else
    FENCE_DAMAGE="On the reading this scan implements it swallows $F_PIPES table line(s) that follow it,\
 and the rendered document then loses them while this reducer reads them anyway and publishes a full, correct\
 weight map -- which is why it is refused here. THAT IS A CEILING, NOT A CERTAINTY: this scan does not model\
 HTML blocks or link-reference definitions, and a fence INSIDE one of those is inert in some renderers: a\
 renderer that passes raw HTML through ignores a fence between an <!-- and a -->, and some renderers absorb a\
 fence inside a multi-line link-reference-definition title into the title. If either is your case the fence\
 is inert to those renderers, and the fix is to take it out of the construct rather than\
 to close it."
  fi
  echo "reduce.sh: $SEV_MD opens a CODE FENCE at line $F_LINE ($F_RUN x \`$F_CH\`) that is never closed." \
    "A fence closes only with the SAME character, a run at least as long, and nothing after it -- so" \
    "\`\`\` does not close \`~~~\`, \`\`\` does not close \`\`\`\`, and a closer carrying an info string" \
    "(\`\`\`bash) does not close anything. Everything after line $F_LINE is inside that code block." \
    "$FENCE_DAMAGE Close the fence, or delete it." >&2
  exit 1
fi
# ── CARRIAGE RETURNS ───────────────────────────────────────────────────────────────────────────────
# A PREDICATE CANNOT BE TRUSTED TO PICK THE REPAIR HERE. A predicate chosen to separate "carriage returns
# acting as line terminators" from "carriage returns inside a cell" tends to be right about the inputs it
# was built on and wrong about their mirror, and the wrong side then gets a repair that DESTROYS THE FILE:
# `CR_N > NL`, `CR_IN > NL` and `CR_MAX > 1 && CR_NONROW > 0` each fail that way. So THE REPAIR MUST NOT
# DEPEND ON GETTING THE PREDICATE RIGHT.
#   SO THE REPAIR IS ONE COMMAND, MEASURED ON EVERY SHAPE. Strip the carriage return that terminates a line,
# then convert any that remain:
#       awk '{sub(/\r$/,"")} 1' severity.md | tr '\r' '\n' > fixed
# Measured against a copy of severity.md (15 tables / 134 `<tr>` rendered), on every carriage-return
# shape built for this gate. The two single-step commands each destroy the
# document on some shape; strip-then-convert destroys none of them:
#     input                          `tr -d '\r'`        `tr '\r' '\n'`      strip-then-convert
#     21 bare-CR-terminated ROWS     14 tables / 116     restores pristine   restores pristine
#     one bare CR between two rows   15 / 133            restores pristine   restores pristine
#     all-CRLF + 5 bare-CR lines     restores pristine   0 tables / 0 rows   restores pristine
#     all-CRLF + 1 bare CR           restores pristine   0 tables / 0 rows   restores pristine
# `tr -d` deletes line boundaries, which cannot be recovered; `tr '\r' '\n'` turns every CRLF into a blank line
# and breaks every table. Neither failure mode is in strip-then-convert, because it removes the CR that is
# PAIRED with a newline and converts only the ones that are not.
#   THE FOUR CELLS ABOVE ARE DELTAS AGAINST THE UNEDITED 134, NOT CONSTANTS. How big each delta is
# depends on WHICH rows are marked: a row merged into the row after it costs one `<tr>`, and one merged
# across a table boundary can cost the whole table, so marking a different set of 21 rows gives a
# different delta (15 tables / 114 `<tr>` rather than 14 / 116 is one such). The DIRECTIONAL claims are
# what to rely on: `tr -d` loses boundaries on every bare-CR shape, `tr '\r' '\n'` renders any all-CRLF
# file at 0 tables, and strip-then-convert restores both bare-CR shapes byte-for-byte to the unedited
# file.
#   THE ONE SHAPE IT DOES NOT REPAIR is a carriage return genuinely INSIDE a cell, where the editor wants
# the text rejoined rather than split: there strip-then-convert splits the row (the file gains one line;
# 15 tables / 135 `<tr>` when the carriage return sits immediately before a `|`, so the fragment is still
# a row, and 15 / 134 when it sits mid-cell, where the table simply ends -- measured both) and deleting
# that one carriage return is what restores the file. That is a per-line judgement, the message names the
# lines, and NO OPERATION IS ASSERTED SAFE FOR THE WHOLE FILE. `tr '\r' '\n'` is "never loses TEXT", not
# "never destructive": it destroys every table in three measured cases while preserving every byte of
# text.
#
# EVERYTHING THIS GATE NEEDS IS COUNTED IN ONE awk, INSIDE THE C LOCALE, because figures assembled
# with `tr`, `grep`, `cut` and `sed` in the ambient locale break on a file holding both an interior
# carriage return and one invalid UTF-8 byte: `cut` fails and the refusal prints "The INTERIOR one(s)
# are on line(s): ." -- an empty list -- then tells the maintainer to fix "the line(s) named above".
# The only text re-parsed outside that awk is the awk's OWN output, read back with the nine `cut -f`
# calls just below: ASCII digits and spaces in fixed tab-separated fields, which no locale can
# reinterpret.
#   FIELDS: records; total CRs; records ending in CR; interior CRs; the most in any one record; how many
# interior-CR records do NOT begin with `|`; how many DO; how many interior CRs are followed by text that
# BEGINS A TABLE ROW (the terminator signal -- a bare CR between two rows looks like an in-cell CR to every
# count, and only this test separates them); how many affected lines are DATA rows, i.e. begin with `|` and are
# neither the `| ID |` header nor a `|---|` delimiter; the first ten interior-CR line numbers; and the first ten
# CR-terminated line numbers.
CR_FACTS=$(LC_ALL=C awk '
  {
    crn = gsub(/\r/, "\r")
    crtail = (substr($0, length($0), 1) == "\r") ? 1 : 0
    crin = crn - crtail
    tot += crn; eol += crtail
    if (crin > 0) {
      inall += crin
      if (crin > maxin) maxin = crin
      if (listn < 10) { list = list (listn++ ? " " : "") NR }
      if ($0 ~ /^\|/) rowl++; else nonrowl++
      if ($0 ~ /^[ \t]*\|/ && $0 !~ /^[ \t]*\|[ \t]*ID[ \t]*\|/ \
                           && $0 !~ /^[ \t]*\|[-: |]+\|[ \t]*$/) datarowl++
      # IS THIS CARRIAGE RETURN A LINE TERMINATOR? Two conditions, and BOTH are needed -- each alone is
      # wrong on a real input:
      #   the text BEFORE it must end with `|`, i.e. look like a COMPLETE table row. Testing only what
      #     follows fires on a carriage return sitting immediately before a `|` INSIDE a row -- an in-cell
      #     carriage return -- so arm 1 would assert the file "uses BARE CARRIAGE RETURNS AS LINE ENDINGS"
      #     about a single split cell, and its repair would split the row instead of restoring it.
      #   the text AFTER it must begin a BLOCK CONSTRUCT: `|`, `#`, or nothing (a blank line). Testing only
      #     for `|` misses the last data row of a tier, a bare carriage return, then `### Medium` with no
      #     blank line. That would route to arm 2, which would call it an in-cell carriage return and
      #     prescribe DELETION, and deletion produces `| lens-11 ... |### Medium`, DESTROYING THE HEADING,
      #     while the file still refuses. The invariant command fixes that same input at exit 0 -- measured
      #     both ways.
      nseg = split($0, seg, "\r")
      for (si = 2; si <= nseg; si++) {
        sbefore = seg[si - 1]; sub(/[ \t]+$/, "", sbefore)
        if (sbefore ~ /\|$/ && seg[si] ~ /^[ \t]*($|\||#)/) splitrow++
      }
    }
    if (crtail && elistn < 10) { elist = elist (elistn++ ? " " : "") NR }
  }
  END { printf "%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\n", \
               NR, tot, eol, inall, maxin, nonrowl, rowl, splitrow, datarowl, list, elist }
' "$SEV_MD") || {
  echo "reduce.sh: could not scan $SEV_MD for carriage returns -- awk exited nonzero, so the line-ending" \
    "checks did NOT run. Its stderr is not sent to /dev/null: that would leave every field" \
    "empty, make the \`-gt 0\` test below false and skip the whole gate in silence. Refusing instead." >&2
  exit 1; }
NL=$(printf '%s' "$CR_FACTS"        | cut -f1)
CR_N=$(printf '%s' "$CR_FACTS"      | cut -f2)
CR_EOL=$(printf '%s' "$CR_FACTS"    | cut -f3)
CR_IN=$(printf '%s' "$CR_FACTS"     | cut -f4)
CR_MAX=$(printf '%s' "$CR_FACTS"    | cut -f5)
CR_NONROW=$(printf '%s' "$CR_FACTS" | cut -f6)
CR_ROW=$(printf '%s' "$CR_FACTS"    | cut -f7)
CR_SPLITROW=$(printf '%s' "$CR_FACTS" | cut -f8)
CR_DATAROW=$(printf '%s' "$CR_FACTS" | cut -f9)
CR_LINES=$(printf '%s' "$CR_FACTS"  | cut -f10)
CR_LINES_EOL=$(printf '%s' "$CR_FACTS" | cut -f11)
if [ "${CR_N:-0}" -gt 0 ]; then
  # `LC_ALL=C` ON BOTH STAGES, AND IT IS LOAD-BEARING. All four arms emit this command, and in the ambient
  # locale it DESTROYS THE FILE it is prescribed for. Measured on the shipped file re-saved CRLF with one
  # Windows-1252 smart quote (byte 0x92) put in place of the space after a row's first `|` -- a Word paste
  # into a latin-1 editor, the same provenance this file already cites for U+202F/U+FEFF:
  #     before                  the 405-line severity.md re-saved CRLF, 0x92 at :205 (its first data row)
  #     as prescribed (ambient) 204 lines survive, 56% of the bytes lost   awk: towc: multibyte conversion failure
  #     with LC_ALL=C           405 lines, pristine's size to the byte; the 0x92 is the one byte that differs
  # WHAT SURVIVES IS THE FILE UP TO THE OFFENDING LINE -- awk dies there, and the `> fixed` the
  # message itself names has already captured everything before it -- SO THE LOSS IS
  # PLACEMENT-DEPENDENT and the figure above is one placement rather than the number. Measured, one
  # 0x92 at four positions in the same 405-line file: first data row (line 205) leaves 204 lines, 56%
  # of the file destroyed; that table's header row two lines above leaves 202, also 56%; data row 232
  # leaves 231, 41% lost; data row 300 leaves 299, 15% lost. No byte counts: each edit above a
  # placement moves them, and any figure here goes stale when the file grows, which is why the
  # mechanism is stated and every number names its file. `tr -d '\r'` dies the same way at every
  # placement ("tr: Illegal byte sequence"), so the `tr -d` alternative the two hygiene arms offer
  # carries `LC_ALL=C` too.
  #   AN INVARIANT COMMAND IS NOT ENOUGH ON ITS OWN. Having both arms prescribe one command means
  # mis-routing cannot produce destructive advice -- but only if the command is also right ABOUT ITS
  # ENVIRONMENT. The gate's own awk (CR_FACTS, above) is `LC_ALL=C` for exactly this class, and the
  # comment above it describes `cut` failing on precisely "an interior carriage return and one invalid
  # UTF-8 byte"; the repair the gate prescribes needs the same pin. A command is not invariant because it
  # has no branches. It is invariant when its environment is pinned, and pinning it is one token per
  # stage.
  CR_FIX="LC_ALL=C awk '{sub(/\\r\$/,\"\")} 1' $SEV_MD | LC_ALL=C tr '\\r' '\\n' > fixed"
  #     arm 1  CR_SPLITROW > 0, or several interior CRs in a non-row record: they are terminating lines
  #     arm 2  CR_IN > 0                                                     interior carriage returns
  #     arm 3  CR_EOL == NL                                                  uniformly CRLF (hygiene)
  #     arm 4  otherwise                                                     mixed endings (hygiene)
  # Arm 1 and arm 2 PRESCRIBE THE SAME COMMAND, which is the point: mis-routing between them cannot produce
  # destructive advice. They differ only in what they tell the maintainer to expect afterwards.
  if [ "${CR_SPLITROW:-0}" -gt 0 ] || { [ "${CR_MAX:-0}" -gt 1 ] && [ "${CR_NONROW:-0}" -gt 0 ]; }; then
    echo "reduce.sh: $SEV_MD uses BARE CARRIAGE RETURNS AS LINE ENDINGS, at least in part -- $CR_IN of its" \
      "$CR_N carriage return(s) sit inside a record as awk splits records, the most in any one record is" \
      "$CR_MAX, and $CR_SPLITROW of them are directly followed by text that begins a table row. That last" \
      "count is the evidence: a carriage return followed by \`|\` is separating two table rows, so it is" \
      "doing a line terminator's work and awk never split there. Across the whole file awk sees only $NL" \
      "record(s) where the text has more lines than that. Table lines and tier headings inside such a run" \
      "cannot be parsed, because they are not separate records." \
      "REPAIR: $CR_FIX -- this strips the carriage return of any CRLF pair and converts the rest to" \
      "newlines. It restored a correct file byte-for-byte on most carriage-return shapes measured, and did" \
      "NOT on all of them: where a carriage return sits immediately before a \`|\` INSIDE a row this branch" \
      "can still be the one that fires, and there the command splits that row instead of restoring it, which" \
      "this parser then refuses -- visibly, and without losing text. THE \`LC_ALL=C\` ON BOTH STAGES IS NOT" \
      "OPTIONAL: without it, on a file that also holds one invalid byte, awk aborts mid-stream and the" \
      "redirection keeps only the newline-ended lines before the one holding that byte (on the 405-line severity.md, 15% to" \
      "56% lost at the four placements measured on the CRLF file; all of it when every line ends in a bare CR, since awk then sees one line). Do NOT use \`tr -d '\\r'\` alone (it deletes these line boundaries irrecoverably) and do NOT" \
      "use \`tr '\\r' '\\n'\` alone (on a file that also has CRLF endings it turns every one into a blank" \
      "line and every table disappears -- measured, 0 tables)." >&2
  elif [ "${CR_IN:-0}" -gt 0 ]; then
    if [ "${CR_DATAROW:-0}" -gt 0 ] && [ "${CR_NONROW:-0}" -eq 0 ] && [ "${CR_DATAROW:-0}" -eq "${CR_ROW:-0}" ]; then
      # THE `<tr>` ARITHMETIC IS FOR DATA ROWS ONLY. Applied to anything beginning with `|`, which
      # includes the header and delimiter rows, it points the WRONG WAY there: measured, a carriage
      # return inside a header row renders 14 tables / 118 `<tr>` -- a table LOST -- and one inside a
      # delimiter row renders 15 / 134, completely UNCHANGED, against the one row GAINED it would claim.
      CR_WHAT="Every affected line is a DATA row, so each carriage return is inside a table cell. A renderer"
      CR_WHAT="$CR_WHAT splits that row there, so the document renders one extra row per such carriage return"
      CR_WHAT="$CR_WHAT -- measured, 135 \`<tr>\` for one and 136 for two against 134 for a correct file --"
      CR_WHAT="$CR_WHAT while this parser reads the row as a single line, so the table a reader would see does"
      CR_WHAT="$CR_WHAT not match the weights this file documents."
    else
      CR_WHAT="The affected lines are not all data rows ($CR_DATAROW data row(s), $CR_ROW line(s) beginning"
      CR_WHAT="$CR_WHAT with \`|\` in total, $CR_NONROW not beginning with one), so NO single claim is made"
      CR_WHAT="$CR_WHAT here about the rendered row count: measured against 134 for a correct file, a carriage"
      CR_WHAT="$CR_WHAT return inside a DATA row gives 135, inside a HEADER row gives 14 tables / 118 (a table"
      CR_WHAT="$CR_WHAT lost), inside a DELIMITER row gives 15 / 134 (unchanged), and inside a tier heading or"
      CR_WHAT="$CR_WHAT the preamble gives 134. The figures point in three different directions, which is why"
      CR_WHAT="$CR_WHAT the count is not asserted."
    fi
    echo "reduce.sh: $SEV_MD contains $CR_N carriage return(s), of which $CR_IN sit INSIDE a line rather than" \
      "terminating one; $CR_EOL terminate lines, out of $NL lines in total. The interior one(s) are on" \
      "line(s), UP TO TEN SHOWN of $CR_IN: $CR_LINES. $CR_WHAT" \
      "REPAIR, and it is a per-line judgement rather than one command: where the carriage return is inside a" \
      "cell and you want the text rejoined, DELETE that carriage return from that line. Where you are not" \
      "sure, \`$CR_FIX\` loses no text WHEN RUN EXACTLY AS WRITTEN, \`LC_ALL=C\` on both stages included" \
      "-- drop either one and awk or tr can abort on an invalid byte and the redirection keeps only what had" \
      "been written, measured at half the file. It converts the carriage return to a newline, so an" \
      "in-cell one leaves a visibly split row for you to rejoin by hand rather than silently joining two" \
      "lines. Nothing here is asserted safe for the whole file: after the repair, re-run reduce.sh and" \
      "check by hand every line that held a carriage return." >&2
  elif [ "$CR_EOL" -eq "$NL" ]; then
    echo "reduce.sh: $SEV_MD has CRLF (Windows) LINE ENDINGS -- all $NL of its lines end with a carriage" \
      "return and none has one inside it. This file is required to use LF endings: it is a reference" \
      "document whose diff is read as a score change, and a whole-file line-ending change buries that diff." \
      "CLASSIFIED AS HYGIENE on the evidence of this reference document, not as a guarantee about any file:" \
      "an all-CRLF copy of a WELL-FORMED severity.md was measured to parse to the identical weight map (the" \
      "reducer strips carriage returns before matching) and to render identically. A file that is malformed" \
      "for other reasons lands here too and those measurements say nothing about it -- a file whose only" \
      "content is one carriage return reaches this arm and parses no rows at all. REPAIR: \`$CR_FIX\`, or" \
      "\`LC_ALL=C tr -d '\\r'\`, which is equivalent here because every carriage return in this file" \
      "terminates a line -- but only with \`LC_ALL=C\`, without which tr aborts on an invalid byte and the" \
      "redirection keeps a truncated file." >&2
  else
    echo "reduce.sh: $SEV_MD has MIXED LINE ENDINGS -- $CR_EOL of its $NL lines are terminated by a" \
      "carriage return and the rest are not. Every carriage return in this file terminates a line; none is" \
      "inside one. Line(s) ending in one, up to ten shown of $CR_EOL: $CR_LINES_EOL. This is a line-ending" \
      "problem and not a problem with the text, so it is the line-ending setting of your editor that wants" \
      "changing: a file edited by two tools, or one line re-saved by a tool configured for CRLF, looks" \
      "exactly like this. Neither the parse nor the rendered document is affected on a file that is" \
      "otherwise well-formed -- both were measured identical to a correct file -- so this is a hygiene" \
      "refusal. REPAIR: \`$CR_FIX\`, or \`LC_ALL=C tr -d '\\r'\`, which is equivalent here because every" \
      "carriage return in this file terminates a line -- but only with \`LC_ALL=C\`, without which tr aborts" \
      "on an invalid byte and the redirection keeps a truncated file." >&2
  fi
  exit 1
fi
SEV_RAW=$(LC_ALL=C awk '
  # endtier() ends the open tier and records HOW it ended, so an orphaned row downstream can be told the
  # actual cause instead of being handed a guess. It also enforces "a tier owns at least one data row".
  # `closed_by` is written ONLY when a tier was actually open: this function is also reached with tier==0
  # (every `##` heading in the file, and every non-table line after a foreign table); recording those
  # too would tell a foreign table in the PREAMBLE "the non-tier heading at
  # line 1 closed the tier above it", naming the document title as the closer of a tier that had never
  # been opened. A machine whose stated job is to name the true cause must not invent one.
  function endtier(why) {
    if (tier > 0) {
      if (rows == 0)
        print "!! line " open_line ": the `### " tname[tier] "` heading here owns no table with data rows" \
              " (" why "). REQUIRED: a tier must own exactly one table -- an `| ID | ... |` header row, a" \
              " `|----|` delimiter row, then at least one data row. The parenthesis above is the observed" \
              " reason the tier ended and is the fact to read. The edits KNOWN to reach here are listed" \
              " below, unranked and EXPLICITLY NOT AS A CLOSED SET -- two constructible inputs reach here" \
              " without being one of the four below, an indented data row and a data row that lost" \
              " its leading `|`. The four: a tier heading" \
              " INSERTED directly above the header or delimiter row of another table (which hands that" \
              " table to the new tier and re-tiers every row in it), a duplicated consecutive tier heading," \
              " a tier heading left as the last line of the file, and an interruption between the header" \
              " and delimiter rows of this tier. The parenthesis above is derived from parser state and is" \
              " the fact to trust; this list is not."
      closed_by = why; closed_at = NR
    }
    tier = 0; intable = 0; want = 0; rows = 0; hdr_nf = 0
  }
  # Does this ID cell look like data rather than a header? Used only to tell the two shapes of
  # "first table line is not a header" apart, so each gets its own cause. Locals are named apart from the
  # data loop below (n/tok/t/i) on purpose -- awk has no scoped variables.
  function idish(c) {
    n2 = split(c, tk, "/"); t2 = tk[1]; sub(/^[ \t]+/, "", t2); sub(/[ \t]+$/, "", t2)
    return (t2 ~ /^[a-z]+-[0-9]+$/ || t2 ~ /^[a-z]+-[0-9]+\.\.[0-9]+$/)
  }
  # DOES THIS NON-TABLE LINE LOOK LIKE A TABLE ROW THAT LOST ITS LEADING `|`? GFM permits omitting the
  # outer pipes, so `sec-21 | ... |` renders IDENTICALLY to `| sec-21 | ... |` -- measured, 15 tables and
  # 134 rows in both renderers, byte-identical to pristine. This parser requires the leading `|` anyway
  # (see PROJECT INVARIANTS above), which makes that one keystroke a refusal -- so the refusal has to be
  # able to say which line it is about. Without this, removing the leading `|` from the LAST data row of a
  # tier would produce NO complaint here at all: the row would stop being read and `lens-11` would vanish from
  # the map, leaving the downstream completeness gate to say "add one row per id" about a row that is
  # present and rendering, with no line number.
  #   DELIBERATELY NARROW. It is not "contains a `|`": prose after a table legitimately contains pipes
  # (`use `a | b` here`), and accusing that of being a broken row would be a false refusal. The text
  # BEFORE the first `|` must itself be an id cell or the literal `ID`, which is the shape only a row or
  # a header row has. A line this returns 0 for ends the tier as any non-table line does.
  #   IT RETURNS WHICH SHAPE, NOT JUST WHETHER. 1 = the pre-pipe text is literally `ID`, so the line is a
  # HEADER row that lost its pipe. 2 = the pre-pipe text is id-shaped, so it is a DATA row that lost its
  # pipe. A boolean would make the delimiter-first branch describe the `ID` case for
  # both -- so replacing a header row with `sec-9 | Custom ClusterRoles | why |` would be told the line "has the
  # shape of the `| ID | ... |` header row of this table, with its LEADING `|` MISSING" and "Nothing was
  # deleted", and would be prescribed "RESTORE THE PIPE". All three are false: the line is data-shaped, the
  # header row HAS been deleted, and following that repair produces a SECOND, different refusal ("it starts
  # at the data row |sec-9|"). A repair that makes the input worse is the one failure this
  # parser must never commit, so the two shapes are reported apart and only shape 1 gets a
  # repair prescribed.
  function unpiped(s) {
    if (index(s, "|") == 0) return 0
    u = substr(s, 1, index(s, "|") - 1); sub(/^[ \t]+/, "", u); sub(/[ \t]+$/, "", u)
    if (u == "ID") return 1
    if (idish(u)) return 2
    return 0
  }
  # NAMES WHAT A TERMINAL DOES NOT SHOW -- AND, WHERE IT CANNOT NAME IT, SAYS SO WITH THE BYTE. Quoting a
  # line back is only evidence if the reader can SEE what is wrong with it. Three inputs show quoting alone
  # is not enough: `### High<TAB>#` prints as `### High #`, which satisfies the stated requirement verbatim;
  # `| sec-21<NBSP> |` prints as `sec-21 `, visually identical to `sec-21`; and a bare form feed or
  # zero-width space prints as an apparently EMPTY quoted line. In each case the parser is right and the
  # evidence it offers looks like proof it is wrong.
  #   FIVE NAMED CHARACTERS ARE NOT THE WHOLE OF WHAT A TERMINAL HIDES.
  # At least nineteen more reproduce the failure exactly: U+2000 to U+200A, U+202F,
  # U+3000 and U+1680 all print as a space, and U+FEFF, U+200E, U+200F, U+2060 and U+00AD print as NOTHING --
  # for example `| sec-2<U+FEFF> |` would print `ID cell token "sec-2" is not a question id`, a quoted token that
  # is character-for-character the required shape. U+202F and U+FEFF arrive routinely from word processors
  # and from web paste.
  #   SO THE CHECK IS INVERTED RATHER THAN EXTENDED. Enumerating Unicode is not possible here; enumerating
  # what is SAFE is. After the five named checks -- kept because a name is more useful than a byte -- it
  # decodes each UTF-8 sequence and reports the first character it cannot show, by code point where it has
  # one and by lead byte where the sequence is invalid.
  # THIS IS NOT A COMPLETENESS CLAIM: a byte-level catch-all cannot say
  # which character a multibyte sequence encodes, and a reader who sees `\357` still has to look it up. What
  # it guarantees is only that no invisible character can be quoted back with NOTHING said about it.
  #   COUNTS, NOT JUST FIRST OCCURRENCES, because reporting only the first would mean repairing byte N produces a
  # second identical-looking refusal with no hint that more remained.
  # IS THIS CODE POINT ONE A READER CANNOT SEE? Ranges rather than an enumeration, and deliberately not
  # claimed to be exhaustive -- the point is that anything it misses which is genuinely invisible would have
  # to be a code point that is neither a C0 control, nor in the Unicode space/format blocks below, nor an
  # invalid sequence. Sources are the Unicode general categories Cf (format) and Zs/Zl/Zp (separators) plus
  # the well-known invisible-but-not-space characters. U+00A0 and U+200B are handled by name above and would
  # also match here; that is harmless because they are blanked out of `sc` before this runs.
  #   DECIMAL LITERALS, NOT HEX. BWK awk does not support `0x` literals: `0xFEFF` evaluates to
  # ZERO, so a hex version of this function would return false for every code point and viz() would lose its
  # entire invisible class while still reporting legitimate text. Each constant carries its code point in the
  # comment beside it instead.
  function invisible(c) {
    # Decimal, with the code point beside each in a `#` comment ABOVE the expression -- awk has no /* */.
    #   160 U+00A0 no-break space          173 U+00AD soft hyphen
    #   847 U+034F combining grapheme joiner  1564 U+061C arabic letter mark
    #  5760 U+1680 ogham space mark        6158 U+180E mongolian vowel separator
    #  4447-4448 U+115F..U+1160 hangul fillers     6068-6069 U+17B4..U+17B5 khmer inherent vowels
    #  8192-8207 U+2000..U+200F spaces, zero-width joiners, bidi marks
    #  8232-8239 U+2028..U+202F line/paragraph separators, bidi overrides, narrow no-break space
    #  8287-8303 U+205F..U+206F medium mathematical space, invisible operators, U+2065 (unassigned and
    #            therefore not displayable text either), bidi isolates, deprecated format characters
    # 10240 U+2800 braille pattern blank  12288 U+3000 ideographic space  12644 U+3164 hangul filler
    # 65279 U+FEFF zero width no-break space (BOM)   65440 U+FFA0 halfwidth hangul filler
    # 65529-65531 U+FFF9..U+FFFB interlinear annotation
    # 119155-119162 U+1D173..U+1D17A musical formatting
    #  1536-1541 U+0600..U+0605 arabic number signs (Cf)   1757 U+06DD arabic end of ayah (Cf)
    #  1807 U+070F syriac abbreviation mark (Cf)             2274 U+08E2 arabic disputed end of ayah (Cf)
    # 69821 U+110BD kaithi number sign (Cf)                 69837 U+110CD kaithi number sign above (Cf)
    # 78896-78904 U+13430..U+13438 egyptian hieroglyph format controls (Cf)
    # 113824-113827 U+1BCA0..U+1BCA3 shorthand format controls (Cf)
    #            Those 24 were missing, and missing them was worse than a silent miss: the ELSE branch below
    #            told the reader they "DO display" and that em dashes are legitimate -- a positive
    #            reassurance, and the opposite of the truth for a format character. The exhaustiveness
    #            disclaimer covers failing to NAME a character; it never licensed asserting the miss displays.
    # 917504-917999 U+E0000..U+E03E7 tag characters AND the variation selectors supplement, as ONE range.
    #            Two ranges (U+E0000..U+E007F and U+E0100..U+E01EF) would leave U+E0080..U+E00FF --
    #            128 code points, unassigned and so not displayable text either -- classified as text that
    #            displays: a gap between two ranges that
    #            each looked complete. Prefer one wide range over two exact ones here.
    # 65024-65039 U+FE00..U+FE0F VARIATION SELECTORS, like the U+E0100..U+E01EF variation
    # selectors supplement, each on its own make a quoted token
    # character-for-character identical to the required shape with no caution at all. Nothing in the
    # other ranges covers them; they are not spaces and not in the format block.
    return (c == 160 || c == 173 || c == 847 || c == 1564 || c == 5760 || c == 6158 \
         || (c >= 1536 && c <= 1541) || c == 1757 || c == 1807 || c == 2274 \
         || c == 69821 || c == 69837 || (c >= 78896 && c <= 78904) \
         || (c >= 113824 && c <= 113827) \
         || (c >= 4447 && c <= 4448) || (c >= 6068 && c <= 6069) \
         || (c >= 8192 && c <= 8207) || (c >= 8232 && c <= 8239) \
         || (c >= 8287 && c <= 8303) \
         || c == 10240 || c == 12288 || c == 12644 || c == 65279 || c == 65440 \
         || (c >= 65024 && c <= 65039) \
         || (c >= 65529 && c <= 65531) || (c >= 119155 && c <= 119162) \
         || (c >= 917504 && c <= 917999))
  }

  # COUNTS occurrences of `needle` in `hay` and leaves in the global BLANKED a copy with each occurrence
  # replaced by an equal number of SPACES, so byte offsets are preserved. index()-based on purpose: BWK awk
  # REGEXES DO NOT HONOUR OCTAL ESCAPES FOR BYTES >= \200 -- measured, `gsub(/\342\200\213/, ...)` matches
  # nothing on a string that plainly contains U+200B while `index(s, "\342\200\213")` finds it at byte 2.
  # A regex-based version of this counts zero for both multibyte names, so viz() would fall through to its
  # catch-all and report "3 byte(s) outside printable ASCII" for a character it had a name for.
  function blank(hay, needle) {
    bc = 0; bout = ""; brest = hay; bpad = ""
    for (bj = 1; bj <= length(needle); bj++) bpad = bpad " "
    while ((bk = index(brest, needle)) > 0) {
      bout = bout substr(brest, 1, bk - 1) bpad
      brest = substr(brest, bk + length(needle))
      bc++
    }
    BLANKED = bout brest
    return bc
  }
  function viz(s) {
    vz = ""
    # `sc` is a scratch copy in which each NAMED sequence is replaced by the SAME NUMBER OF SPACES, so the
    # catch-all below does not report a character that has just been named by name, while byte offsets into
    # `sc` still map 1:1 onto `s`. Without the length-preserving substitution a tab would be reported twice, once
    # as a TAB and once as an unnameable byte.
    sc = s
    vn = gsub(/\t/, " ", sc);            if (vn) vz = vz ", " vn " TAB(s), first at byte " index(s, "\t")
    vn = blank(sc, "\302\240"); sc = BLANKED
                                         if (vn) vz = vz ", " vn " NO-BREAK SPACE(s) (U+00A0), first at byte " index(s, "\302\240")
    vn = blank(sc, "\342\200\213"); sc = BLANKED
                                         if (vn) vz = vz ", " vn " ZERO WIDTH SPACE(s) (U+200B), first at byte " index(s, "\342\200\213")
    vn = gsub(/\014/, " ", sc);          if (vn) vz = vz ", " vn " FORM FEED(s), first at byte " index(s, "\014")
    vn = gsub(/\013/, " ", sc);          if (vn) vz = vz ", " vn " VERTICAL TAB(s), first at byte " index(s, "\013")
    # THE CATCH-ALL DECODES UTF-8 INSTEAD OF JUDGING BYTES, because judging bytes produces a FALSE CAUTION on
    # text that is perfectly legitimate here. severity.md contains EM DASHES (U+2014) in 12 of its data rows,
    # and a byte-level "outside printable ASCII" test reports every one of them as something "a terminal does
    # not display", with "retype the cell by hand" attached -- advice that would silently replace correct
    # punctuation. The byte count and offset are exact but the CLASSIFICATION is wrong, and a caution that
    # fires on correct input is the same defect as a diagnostic naming a cause the input does not have.
    #   So: walk the string, decode each well-formed UTF-8 sequence to a code point, and sort what is found
    # into three kinds. INVISIBLE / FORMAT code points get the caution. INVALID sequences get the caution.
    # Everything else is legitimate non-ASCII text and gets a SEPARATE, non-alarming mention -- and only when
    # the caution is already firing for something else, so the reader can tell which character is the problem.
    # On its own, legitimate non-ASCII says nothing at all.
    #   THIS IS STILL NOT A COMPLETENESS CLAIM in either direction. A character that DISPLAYS but displays as
    # something else -- a Cyrillic `а` in place of a Latin `a` -- is legitimate by this test and is not named
    # here; what catches it is the grammar check that rejected the cell in the first place.
    vo = 0; voc = 0; vcp = ""; vlegit = 0; vlegat = 0; vlegcp = ""
    vi = 1
    while (vi <= length(sc)) {
      b1 = BYTE[substr(sc, vi, 1)]
      if (b1 < 32 || b1 == 127) {          # a C0 control or DEL: never displayable
        voc++; if (vo == 0) { vo = vi; vcp = sprintf("control byte \\%o", b1) }
        vi++; continue
      }
      if (b1 < 128) { vi++; continue }     # printable ASCII
      if (b1 >= 240)      vlen = 4
      else if (b1 >= 224) vlen = 3
      else if (b1 >= 192) vlen = 2
      else                vlen = 0         # a continuation byte with no lead: invalid
      if (vlen == 0 || vi + vlen - 1 > length(sc)) {
        voc++; if (vo == 0) { vo = vi; vcp = sprintf("invalid UTF-8 byte \\%o", b1) }
        vi++; continue
      }
      vok = 1; vc = 0
      b2 = BYTE[substr(sc, vi + 1, 1)]
      if (b2 < 128 || b2 > 191) vok = 0
      else if (vlen == 2) vc = (b1 - 192) * 64 + (b2 - 128)
      else {
        b3 = BYTE[substr(sc, vi + 2, 1)]
        if (b3 < 128 || b3 > 191) vok = 0
        else if (vlen == 3) vc = (b1 - 224) * 4096 + (b2 - 128) * 64 + (b3 - 128)
        else {
          b4 = BYTE[substr(sc, vi + 3, 1)]
          if (b4 < 128 || b4 > 191) vok = 0
          else vc = (b1 - 240) * 262144 + (b2 - 128) * 4096 + (b3 - 128) * 64 + (b4 - 128)
        }
      }
      # A WELL-FORMED LEAD AND CONTINUATION BYTES ARE NOT ENOUGH. A decoder checking only those accepts three classes of
      # invalid UTF-8 as valid and then classifies them as LEGITIMATE non-ASCII, which is the worst of the
      # three possible answers: an OVERLONG encoding (`\300\255` for U+002D), a LONE SURROGATE
      # (`\355\240\200` for D800), and an OUT-OF-RANGE sequence (`\364\220\200\200` for 110000).
      # Each would be silent. RFC 3629 excludes all three, so each is rejected on the decoded value.
      if (vok) {
        if (vlen == 2 && vc < 128)        vok = 0      # overlong 2-byte form
        else if (vlen == 3 && vc < 2048)  vok = 0      # overlong 3-byte form
        else if (vlen == 4 && vc < 65536) vok = 0      # overlong 4-byte form
        else if (vc >= 55296 && vc <= 57343) vok = 0   # UTF-16 surrogate half, never valid in UTF-8
        else if (vc > 1114111) vok = 0                 # beyond U+10FFFF
        if (!vok) vinvreason = "an invalid UTF-8 sequence -- overlong, a surrogate half, or beyond U+10FFFF"
      } else vinvreason = "an invalid UTF-8 byte"
      if (!vok) {
        voc++
        if (vo == 0) { vo = vi; vcp = sprintf("%s, lead byte \\%o", vinvreason, b1) }
        vi += (vlen > 1 ? vlen : 1); continue
      }
      if (invisible(vc)) {
        voc++; if (vo == 0) { vo = vi; vcp = sprintf("U+%04X, an invisible or formatting character", vc) }
      } else {
        vlegit++; if (vlegat == 0) { vlegat = vi; vlegcp = sprintf("U+%04X", vc) }
      }
      vi += vlen
    }
    if (vo > 0)
      vz = vz ", " voc " character(s) that a terminal does not display, the first at byte " vo " (" vcp ")." \
           " This message cannot always name what such a character is for -- look the code point up, or" \
           " retype the cell by hand"
    # THE NON-ASCII MENTION FIRES EVEN WHEN NOTHING ELSE DOES. Gating it on `vz != ""` would mean a cell whose
    # ONLY anomaly was a non-ASCII character -- a Cyrillic `а` standing in for a Latin `a`, a stray combining
    # mark -- is quoted back with ZERO disclosure, which is precisely the residual case the comment above
    # disclaims and relies on this clause to cover. It is safe to fire unconditionally because viz() is
    # only ever called from a message that has ALREADY refused something, and because the wording is
    # non-alarming: it cannot raise the em-dash false caution, since on a row that merely contains an em
    # dash there is no message for it to appear in.
    vlegtail = ""
    if (vlegit > 0)
      # WORDED AS "PROBABLY DISPLAYS", NOT "DOES DISPLAY". This branch is the ELSE of a range test, so it is
      # where every code point the ranges miss lands -- and any format character the ranges miss lands here and is
      # told it displays. A branch that is by construction the residue of an incomplete test must not make a
      # positive claim about its contents.
      vlegtail = "(The same text holds " vlegit " non-ASCII character(s) that this check did not recognise as" \
                 " invisible, the first " vlegcp " at byte " vlegat ". Most such characters DO display -- em" \
                 " dashes are used throughout this file and are legitimate -- but this is a residual category" \
                 " rather than a verdict: a formatting character the ranges above do not list would also land" \
                 " here, and so would a letter from another script that merely LOOKS like an ASCII one. Check" \
                 " the code point if the quoted text looks correct and was still refused.)"
    if (vz == "" && vlegtail == "") return ""
    if (vz == "") return " -- NOTE: " vlegtail
    sub(/^, /, "", vz)
    # The closing sentence goes BEFORE the legitimate-text parenthetical, so "those" cannot be read as
    # referring to the characters the parenthetical has just called fine.
    return " -- CAUTION, that quoted text contains " vz ". A terminal does not show those, so the quote above" \
           " may look correct when it is not" (vlegtail == "" ? "" : ". " vlegtail)
  }
  # THE NEAREST PRECEDING `#` LINE, QUOTED BACK AS AN OBSERVATION. Every diagnostic about a missing
  # tier heading calls this rather than ranking guesses. It reports a line number and the literal text
  # of a line the parser actually read, so the editor compares that against the required shape themselves
  # rather than being handed a likelihood ordering, which is wrong on ordinary edits:
  # a blank line inside a table would be told a heading had been DELETED; a renamed header cell would be told a
  # heading had been INSERTED; a deleted header row would be told its cell had been RENAMED; and a heading
  # reading `### Medium ###` -- present, correct and rendering as `<h3>Medium</h3>` -- would be told it had been
  # "DELETED or RETYPED". In each case the parser holds the text that answers the question, so it prints that and not a
  # guess. Modelled on `closed_by`, which is the one attribution here derived from parser state.
  # Indentation is called out explicitly because a heading indented into a code block reads as correct once
  # trimmed, and trimmed is how it would otherwise be quoted back.
  function nearest() {
    if (hash_at == 0) return "No `#` line precedes it anywhere in the file."
    if (hash_ind >= 4) return "The nearest preceding `#` line is line " hash_at ", reads `" hash_txt \
      "`" viz(hash_txt) ", and is indented " hash_ind " columns -- GFM makes four or more columns an" \
      " indented code block, not a heading, so it opens no tier here and renders no heading in the" \
      " document either."
    return "The nearest preceding `#` line is line " hash_at " and reads `" hash_txt "`" viz(hash_txt) "."
  }
  # GFM measures leading whitespace in COLUMNS, with tab stops of four: a tab advances to the next
  # multiple of 4, so a lone leading tab is four columns and so is `space tab`. Four or more columns makes
  # the line an indented code block, never a heading. Returning the column count rather than a boolean
  # keeps the "3 spaces is still a heading" boundary readable at the two call sites.
  function indent_cols(s) {
    ic = 0
    for (ip = 1; ip <= length(s); ip++) {
      ch = substr(s, ip, 1)
      if (ch == " ") ic++
      else if (ch == "\t") ic += 4 - (ic % 4)
      else break
    }
    return ic
  }
  BEGIN { FS = "|"; tier = 0; intable = 0; want = 0; rows = 0; open_line = 0
          # BYTE maps a one-byte string to its numeric value (awk has no ord()); SAFE is every
          # printable ASCII byte, which is what viz() treats as displayable. Built once.
          for (bi = 1; bi < 256; bi++) BYTE[sprintf("%c", bi)] = bi
          SAFE = ""; for (bi = 32; bi < 127; bi++) SAFE = SAFE sprintf("%c", bi)
          tname[3] = "High"; tname[2] = "Medium"; tname[1] = "Low"
          closed_by = "no `### High|Medium|Low` heading had appeared before it"
          hash_at = 0 }
  # SHIFT THE ONE-LINE LOOKBEHIND FIRST, before any rule can set it for the CURRENT line. `cand_*` holds
  # a line that is NOT a table line but contains a `|`, which is what a table row looks like once its
  # leading `|` is removed; `prev_*` is that line only when it is the line IMMEDIATELY above this one.
  # The delimiter-first branch below uses it to derive the un-piped-header case instead of guessing.
  { prev_plain_at = cand_at; prev_plain_txt = cand_txt; cand_at = 0; cand_txt = "" }
  # `\r` is removed from every line, not just the end of it: a CRLF file is refused by a named gate in
  # the shell above, but if any `\r` ever reaches a QUOTED line in a diagnostic it returns the terminal
  # cursor to column 0 and the evidence is overwritten by whatever the message prints next. Evidence that
  # the terminal erases is worse than no evidence, because it reads as if the parser printed nothing.
  { line = $0; gsub(/\r/, "", line)
    indent = indent_cols(line); sub(/^[ \t]+/, "", line); sub(/[ \t]+$/, "", line) }
  # REMEMBER THE NEAREST PRECEDING `#` LINE, verbatim, whether or not it parsed as a tier heading. This is
  # the one piece of state that lets the "no tier owns this table" branch below report WHAT IT SAW instead
  # of ranking guesses about what someone might have done. Deliberately set for tier headings too: when the
  # table of a valid tier heading is orphaned by an interruption, naming that heading tells the editor the
  # heading is fine and the interruption is the problem. No `next` here -- this rule falls through.
  line ~ /^#/ { hash_at = NR; hash_txt = line; hash_ind = indent }
  indent < 4 && line ~ /^###[ \t]+(High|Medium|Low)([ \t]* +#+)?[ \t]*$/ {
    # CAPTURED BEFORE endtier() RESETS THE STATE, because it is the only evidence that distinguishes a
    # DELETED header row from a heading INSERTED between a header row and its delimiter row. `want == 2`
    # on the tier being closed means that tier had already read its `| ID | ... |` header row and was
    # waiting for the delimiter row of that header when this heading arrived -- so the header row EXISTS, at
    # `hdr_at`, and the delimiter row this heading now owns is the one that belongs to it. Read the
    # delimiter-first branch below for what this is used for and why a guess is not good enough.
    split_hdr = (tier > 0 && want == 2); split_hdr_at = hdr_at
    endtier("the `### " tname[tier] "` tier was closed by the heading at line " NR)
    if (line ~ /High/) tier = 3; else if (line ~ /Medium/) tier = 2; else tier = 1
    intable = 0; want = 1; rows = 0; open_line = NR; next
  }
  # BRANCHED ON `indent`, because unbranched it would call one line both a heading and not a heading in
  # a single message: this reason would say "the non-tier heading at line N", while nearest() -- quoted in the
  # very same complaint -- says that line is indented four or more columns and GFM therefore makes it an
  # indented code block, NOT a heading. Both cannot be true of one line.
  line ~ /^#/ {
    # A REJECTED TIER-HEADING CANDIDATE IS RECORDED UNCONDITIONALLY, unlike `closed_by`, because otherwise
    # a diagnostic would name the wrong line: pristine severity.md puts a BLANK LINE above all 15
    # tier headings, so when a malformed heading arrives the blank line has ALREADY closed the tier and
    # `tier == 0`. endtier() writes `closed_by` only when `tier > 0` -- rightly, or a foreign table in the
    # preamble gets told the document title closed a tier that never opened -- so the blank line`s reason
    # would survive and the orphaned rows below would be told "the table above was ended by the non-table line at
    # line 141 which is blank or holds only whitespace", AN UNMODIFIED BLANK LINE, for inputs such as
    # `## Medium`, `### Medium<TAB>#` and `### Medium<NBSP>`. A STALE true-sounding cause is strictly worse
    # than none, and it would also make the indent branch below unreachable as a cause for every heading in this
    # file. So the rejection is remembered here with its own line number, and the `tier == 0` branch prefers
    # whichever event is LATER.
    #   THE TEST IS NARROW so it cannot resurrect the preamble defect: a `###` line (measured -- every
    # `###` line in pristine severity.md is a tier heading, so one this rule sees was meant to be one), or
    # a heading at any depth whose text is exactly High/Medium/Low (measured -- no `#`/`##` line in
    # pristine has that text, so `## Security` is untouched and still reports as a non-tier heading).
    if (line ~ /^###/ || line ~ /^#+[ \t]*(High|Medium|Low)[ \t]*$/) {
      rej_head_at = NR; rej_head_txt = line; rej_head_ind = indent
    }
    endtier(indent >= 4 \
      ? "the line at line " NR " begins with `#` but is indented " indent " columns, which GFM makes an" \
        " indented code block rather than a heading -- either way it is not a table line, so it ended the" \
        " table above it" \
      : "the non-tier heading at line " NR " closed the tier above it")
    next }
  # End of the table closes the tier. `intable` is what allows a heading to be separated from its table by
  # a blank line or a sentence of prose (neither exists today, both are legitimate markdown) while still
  # ending the tier at the first non-table line that FOLLOWS any of its table lines.
  # A TABLE LINE INDENTED FOUR OR MORE COLUMNS IS NOT A TABLE LINE, for the same GFM reason the tier-heading
  # rule already applies four lines up: four columns makes it an indented code block. Applied
  # only to headings, with the table rules trimming leading whitespace unconditionally, FOUR separate
  # one-line edits would each remove rows or a whole table from the RENDERED document at exit 0 with the map
  # UNCHANGED and not one complaint (pristine 15 tables / 134 rows):
  # a data row indented 4 spaces or 1 tab, 15 tables / 124 rows -- 10 rows gone; a header row or a
  # delimiter row indented 4 spaces, 14 tables / 118 rows -- an entire Security `### High` table gone.
  # That is the same consequence as the mismatched delimiter width the `want == 2` branch refuses by name,
  # so refusing one and not these four would be a distinction with nothing behind it. SAFE BY MEASUREMENT:
  # pristine severity.md has ZERO lines indented 4 or more columns (its deepest indent is the 3-space
  # continuation lines of the numbered list in the prose), so 1-3 space indents are read
  # exactly as unindented lines are. This sits BELOW the non-tier-heading rule on purpose: an indented `###` line must keep
  # reaching that rule, where nearest() already explains the code-block reading for headings.
  # `line != ""` IS LOAD-BEARING, NOT DEFENSIVE. `line` is already trimmed here, so `line == ""` is exactly
  # "this line holds nothing but whitespace" -- and a whitespace-only line is a BLANK LINE in GFM, never an
  # indented code block: measured, four spaces or one tab on an otherwise empty line renders
  # byte-identically to a bare newline in both renderers (15 tables / 124 rows, zero `<pre>`) when inserted
  # between two data rows. Without this guard the amount of INVISIBLE whitespace on an empty line would flip a
  # true diagnostic into a false one -- ten complaints reading "the line at line N is indented 4 columns --
  # GFM makes four or more an indented code block" about a line GFM treats as blank, while the same input
  # with zero spaces correctly says "which is blank or holds only whitespace". Editors that preserve
  # indentation on empty lines produce exactly this input. Falling through to the `line !~ /^\|/` rule below
  # is deliberate: that rule reports it correctly.
  indent >= 4 && line != "" {
    # NAMED AT ITS OWN LINE, not left to be inferred downstream. endtier() below only fires when a table
    # was already open, so the two edits that indent a HEADER or DELIMITER row -- the two that cost the
    # whole table, 14 tables / 118 rows -- would otherwise reach only the delimiter-first branch, which
    # holds no evidence and correctly names no cause. The evidence is right here, so it is printed here.
    if (line ~ /^\|/)
      # THE MECHANISM CLAUSE IS BRANCHED, because "GFM makes this an indented code block" is FALSE for one
      # of the four targets. Measured `<pre>` counts on the rendered file: 1 for an indented header row,
      # data row or tier heading -- and ZERO for an indented DELIMITER row, because the header row above it
      # has already opened a paragraph and the indented delimiter is absorbed as a LAZY CONTINUATION of it,
      # turning the table into one paragraph of literal pipes.
      # The verdict (not a table line here) is true for all four; only the reason
      # differs, so only the reason branches.
      print "!! line " NR ": this line is indented " indent " columns and reads `" line "`" viz(line) \
            " -- so this parser does not read it as a table line" \
            (want == 2 \
               ? ", and the document does not render it as one either: the header row above has already" \
                 " opened a paragraph, so an indented delimiter row is absorbed into it as a lazy" \
                 " continuation and the whole table becomes one paragraph of literal `|` characters" \
                 " (measured: no `<pre>` block at all, and the table gone)" \
               : ". GFM makes four or more columns an INDENTED CODE BLOCK, so the document renders it as" \
                 " preformatted text rather than as part of any table") \
            ". Measured against pristine (15" \
            " tables / 134 rows, both renderers): a DATA row indented this far drops ITSELF AND EVERY ROW" \
            " BELOW IT IN THE SAME TABLE. That is the rule; the number is whatever that table has left below" \
            " the row, so no single figure is quoted here." \
            " The largest table in this file has 20 data rows, so 20" \
            " is the most a single indented data row has been measured to remove (134 down to 114). A HEADER" \
            " or DELIMITER row indented this far drops its whole table instead. Any of these passes at exit 0 with the" \
            " weight map UNCHANGED unless refused here. Remove the indentation; up to 3 columns is" \
            " still a table line."
    if (intable) endtier("the line at line " NR " is indented " indent " columns -- GFM makes four or" \
                       " more an indented code block, so it is not a table line and the rows are not" \
                       " rendering as part of this table either")
    next
  }
  line !~ /^\|/ {
    if (line ~ /\|/) { cand_at = NR; cand_txt = line }
    # QUOTE THE LINE, do not enumerate causes. A list such as "a blank line, an HTML
    # comment or a code fence" names a cause the input may not have: for example,
    # removing the leading `|` from one data row makes that row a
    # non-table line, and nine downstream rows would each be told the table had been ended by a blank
    # line, an HTML comment or a code fence, about a line that is a table row in every renderer. The line
    # itself is in hand, so it is printed -- the principle nearest() implements for headings.
    #   Printed only when `intable` -- i.e. only when this line BROKE an open table. With `intable == 0` the
    # line sits between a tier heading and its table, and the
    # `want == 1` branches below do NOT report it, except for one shape: of the
    # single-line insertions tried in that position, only the UN-PIPED HEADER ROW is reported (the
    # delimiter-first branch derives it from the lookbehind); fifteen others -- a setext underline, a bare
    # paragraph, `<h3>Low</h3>`, `<div>`, `<p>Low</p>`, an unterminated `<!-- x`, `> Low`, `- Low`,
    # `>> Low` among them -- are ACCEPTED in silence (the weight map unchanged), and several of them delete whole
    # tables from the rendered document. That class is accepted and invisible;
    # it is NOT covered here, and is recorded as a gap rather than
    # claimed as covered. Complaining here as well would be wrong for the one shape that IS reported --
    # it would earn that edit two complaints -- which is why the guard stays.
    up = (intable ? unpiped(line) : 0)
    # THE TWO SHAPES GET DIFFERENT MESSAGES HERE TOO, and for the same reason the delimiter-first branch
    # below needs them: a claim true of one is false of the other.
    #   `up == 2`, a DATA row that lost its leading `|`: "nothing in the rendered document looks wrong" is
    # MEASURED CORRECT -- un-piping the first, sixth, fifteenth and last data rows of the file each render
    # 15 tables / 134 rows, byte-identical to pristine, in both renderers. The repair is real and it works.
    #   `up == 1`, an `ID`-first row: the same sentence would be FALSE OVER THE WHOLE REACHABLE DOMAIN of this
    # arm. `up` is computed only when `intable`, so this fires only where a header row is never legal --
    # inside an open table -- and there the document GAINS a visible row reading `ID | Check | Why High`:
    # measured 15 tables / 135 rows against pristine 15 / 134. Worse, prescribing "RESTORE THE LEADING
    # `|`" would not work: with the pipe added the line refuses again as `ID cell token "ID" is not a
    # question id`. That is the same defect the delimiter-first branch is written to avoid
    # -- a repair that makes the input worse -- so this arm states the observation, says the
    # render DOES change, and prescribes nothing.
    if (up == 2)
      print "!! line " NR ": this line reads `" line "` -- it does NOT begin with `|`, so this parser does" \
            " not read it as a table line, and the question id in its first cell therefore gets no weight." \
            " GFM lets a table line omit its outer pipes and renders it identically to a piped one, so the" \
            " rendered document is byte-identical to a correct one and discloses nothing; this file" \
            " requires the leading `|` anyway. RESTORE THE LEADING `|` on line " NR "." viz(line)
    else if (up == 1)
      print "!! line " NR ": this line reads `" line "` -- its first cell is `ID`, so it has the shape of a" \
            " HEADER row, and it sits inside a table that is already open. A second header row is not legal" \
            " here in any form: this parser does not read the line as a table line at all (it does not" \
            " begin with `|`), and adding the leading `|` would NOT fix it -- the line would then be read" \
            " as a data row whose id cell is `ID`, and refused again with a different message. So no repair" \
            " is prescribed. The rendered document is NOT unchanged either: GFM reads this as a row with" \
            " its outer pipes omitted, so the table gains a visible row reading `ID | Check | ...`" \
            " (measured, 135 rows against 134). Decide what this line was meant to be and remove or replace" \
            " it." viz(line)
    if (intable) endtier("the table above was ended by the non-table line at line " NR \
                       (line == "" ? " which is blank or holds only whitespace" \
                                   : " which reads `" line "` -- every table line in this file must" \
                                     " begin with `|`, and that one does not" viz(line)))
    next
  }
  {
    intable = 1
    cell = $2; sub(/^[ \t]+/, "", cell); sub(/[ \t]+$/, "", cell)
    if (tier == 0) {
      what = ((cell == "ID" || cell ~ /^[-: ]+$/) \
             ? "a table starts here (at |" cell "|) but no tier owns it" \
             : "the severity row |" cell "| belongs to no tier") viz(cell)
      # WHICHEVER STRUCTURAL EVENT IS LATER IS THE CAUSE. Two can leave a table with no tier: the tier
      # closing (`closed_by`, at `closed_at`) and a heading candidate being REJECTED (`rej_head_*`). Reporting
      # only the first would mean a rejected heading standing between the closer and this
      # line is silently replaced by the closer -- and in pristine layout the closer is always the blank
      # line above the heading. `>=` rather than `>` because a rejected heading on the same line as the
      # closer IS the closer, and the rejection is the more informative half of it.
      #   IT ALSO TAKES PRECEDENCE OVER THE `BEGIN` DEFAULT, which for the FIRST tier heading would assert "no
      # `### High|Medium|Low` heading had appeared before it" in the same sentence that nearest() quotes
      # one. That default is reached only when no heading candidate precedes the table at all, which is
      # the foreign-table-in-the-preamble case it is for.
      #   nearest() IS SUPPRESSED when the rejected heading IS the nearest `#` line, which is the common
      # case: it would quote the same text a second time and repeat the invisible-character caution with it.
      why = closed_by; near = " " nearest()
      if (rej_head_at > 0 && rej_head_at >= closed_at) {
        why = "the line at line " rej_head_at " reads `" rej_head_txt "`, and this parser did NOT accept it" \
              " as a tier heading, so it opened no tier" \
              (rej_head_ind >= 4 \
                 ? " -- it is indented " rej_head_ind " columns, which GFM makes an indented code block" \
                   " rather than a heading" \
                 : "") \
              viz(rej_head_txt)
        if (rej_head_at == hash_at) near = ""
      }
      print "!! line " NR ": " what " -- " why "." near " REQUIRED: every table in this file" \
            " sits under a heading that is exactly `### High`, `### Medium` or `### Low` -- indented at" \
            " most 3 columns, optionally closed by a space and a run of `#` -- and this file may" \
            " contain no table that is not a severity table." \
            (rej_head_at > 0 && rej_head_at >= closed_at \
               ? " Reading these rows at the tier above would silently re-tier the whole table, which is" \
                 " why they are refused rather than defaulted." \
               : " These rows are refused rather than read at the tier above because this parser cannot" \
                 " tell an interruption from a deliberate move; the tier above may well be the tier they" \
                 " belong to, and if it is, repair the interruption rather than moving the rows.")
      next
    }
    # `want == 3` IS THE DELIMITER-OPTIONAL STATE, set by the data-row branch below. It is tested BEFORE
    # `want == 1` so that the line which SETS it is not also consumed by it. See that branch for why the
    # delimiter has to be optional there.
    if (want == 3) {
      want = 0
      if (cell ~ /^[-: ]+$/) next    # the delimiter row survived -- consume it and say nothing
    }                                # otherwise fall through and read this line as data
    # A tier table must open with its header row, then its delimiter row. This is what catches a heading
    # INSERTED mid-table: the rows below the insertion have no header of their own. THREE SHAPES OF FIRST
    # TABLE LINE reach this -- a delimiter row, a data row, or a header row whose first cell is not `ID` --
    # and they have different repairs, so they are reported apart. The SHAPE is observed; the EDIT behind it
    # is named only where the parser holds evidence for it (`split_hdr` in the delimiter branch), and is
    # otherwise listed by what is known to reach the branch, explicitly not as a closed set. Two branches
    # would collapse the delimiter-first case into the last one, so a DELETED
    # header row would be reported as a RENAMED cell -- and then, because that branch expects the delimiter next
    # and would just have eaten it, complain a second time that the header row was not followed by one. Each
    # branch leaves `want` in the state that stops the SAME edit earning a second complaint; that is
    # measured per branch below, not asserted for all of them.
    if (want == 1) {
      if (cell == "ID") { want = 2; hdr_at = NR; hdr_nf = NF; next }
      if (cell ~ /^[-: ]+$/) {
        # The first table line is the `|----|` DELIMITER row. Deleting the header row is NOT the only
        # single edit that puts one there, so this branch does not name DELETION as the cause.
        # Naming it outright would name a cause the input may not
        # have. Inserting a tier heading
        # between a header row and its delimiter row reaches here with the header row PRESENT and nothing
        # deleted, and "restore the header row" is then the WRONG repair: the fix is to remove the inserted
        # heading. endtier() two branches up already enumerates that very edit, so naming deletion here would assert an
        # edit in one message and deny its existence in another. The rule is not about wording: a
        # UNIVERSAL CLAIM OVER AN UNBOUNDED INPUT SPACE, asserted from imagination rather than enumerated
        # by construction, is the error shape of a stale census. So the insertion
        # case is DERIVED from state -- `split_hdr`, captured in the heading rule -- and what remains
        # is listed by shape without any claim to be exhaustive.
        if (split_hdr) {
          print "!! line " NR ": the `### " tname[tier] "` heading at line " open_line " sits between the" \
                " `| ID | ... |` header row at line " split_hdr_at " and this `|----|` delimiter row," \
                " which belongs to that header. The header row is PRESENT; nothing was deleted. REMOVE THE" \
                " HEADING at line " open_line " -- do not add a header row here. The tier above is" \
                " reported separately as owning no data rows, which is the other half of the same edit." \
                " GFM needs the header and delimiter rows adjacent, so this table is not rendering as a" \
                " table in the document either."
        } else if (prev_plain_at == NR - 1 && unpiped(prev_plain_txt) == 1) {
          # THE SECOND CAUSE DERIVED FROM STATE RATHER THAN GUESSED. Naming the repair
          # "the header row was DELETED (restore it)" here would be wrong -- for the input
          # that reaches THIS arm the header row is present one line above, so that repair produces a
          # DUPLICATED header row. The evidence is one line away: `prev_plain_*` is the
          # immediately preceding line when it is a non-table line shaped like a row, which is exactly
          # what a header row looks like once its leading `|` is gone. Measured on `| ID | Check | Why
          # High |` with the pipe removed: both renderers still render the file identically to pristine,
          # 15 tables / 134 rows, so nothing in the document discloses the edit.
          print "!! line " NR ": the table under the `### " tname[tier] "` heading at line " open_line \
                " starts at this `|----|` delimiter row, and the line at line " prev_plain_at " reads `" \
                prev_plain_txt "`" viz(prev_plain_txt) " -- that has the shape of the `| ID | ... |`" \
                " header row of this table, with" \
                " its LEADING `|` MISSING, which is why this parser did not read it as one. RESTORE THE" \
                " PIPE on line " prev_plain_at "; do NOT add a header row, which would leave the table" \
                " with two. Nothing was deleted, and GFM renders an outer-pipe-less header row as a" \
                " normal header row, so the document looks correct and only this parser objects."
        } else if (prev_plain_at == NR - 1 && unpiped(prev_plain_txt) == 2) {
          # SHAPE 2: the line above is DATA-shaped, not header-shaped. It is reported apart from shape 1
          # because everything shape 1 says would be false here -- the header row IS absent, and "restore
          # the pipe" makes the input worse rather than better: with the pipe restored that line becomes a
          # data row sitting where the header row belongs, and the parser refuses it again with a different
          # message. Measured on `sec-9 | Custom ClusterRoles | why |` replacing the header row. So this arm
          # names the shape, names the wrong repair as wrong, and prescribes nothing.
          print "!! line " NR ": the table under the `### " tname[tier] "` heading at line " open_line \
                " starts at this `|----|` delimiter row, and the line at line " prev_plain_at " reads `" \
                prev_plain_txt "`" viz(prev_plain_txt) " -- the text before its first `|` is a question" \
                " id, so that line has the" \
                " shape of a DATA row, not of the `| ID | ... |` header row this table needs. This parser read no" \
                " header row between the heading at line " open_line " and this delimiter row. THAT IS THE" \
                " OBSERVATION; the parser holds no evidence for which edit produced it and prescribes no" \
                " repair. In particular, adding a leading `|` to line " prev_plain_at " would NOT fix it:" \
                " that line would then be read as a data row standing where the header row belongs, and" \
                " refused again with a different message. The shape required is a header row whose first" \
                " cell is `ID`, beginning with `|`, on the line immediately above this delimiter row."
        } else {
          print "!! line " NR ": the table under the `### " tname[tier] "` heading at line " open_line \
                " starts at a `|----|` delimiter row: this parser read no `| ID | ... |` header row" \
                " between the heading and this line. THAT IS THE OBSERVATION and it is all this branch" \
                " claims -- it holds no evidence for WHICH edit produced it, so it names none and" \
                " prescribes no repair. Compare the lines between " open_line " and " NR " against the" \
                " required shape yourself: a header row whose first cell is `ID`, beginning with `|`," \
                " on the line immediately above this delimiter row. (The three shapes the parser CAN" \
                " recognise are reported by name instead of reaching here -- a tier heading inserted" \
                " between a header row and its delimiter row, a header row whose leading `|` was removed," \
                " and a data-shaped line standing where the header row belongs.) GFM needs a header row" \
                " above that delimiter to render a table at all, so the" \
                " rows below are not rendering as a table in the document either."
        }
        want = 3; next      # the delimiter row has been read, so `want == 2` must not run again and
                            # consume the first DATA row as a missing delimiter. want == 3 rather than 0
                            # because the header-cells-edited-into-delimiter-shape input leaves the REAL
                            # delimiter row on the next line, and want == 0 would read it as data and earn a
                            # second complaint ("`----` is not a question id") for that one edit --
                            # measured: want = 0 gives 2 complaints there and 1 on the deleted-header
                            # input, want = 3 gives 1 on both.
      }
      if (idish(cell)) {
        # The first table line is a DATA row: neither a header row nor a delimiter row is above it.
        print "!! line " NR ": the table under the `### " tname[tier] "` heading at line " open_line \
              " has no `| ID | ... |` header row and no `|----|` delimiter row -- it starts at the data" \
              " row |" cell "|" viz(cell) ". THREE edits are KNOWN to reach this and the parser cannot" \
              " separate them, so" \
              " they are listed by what reaches here rather than by likelihood, and not as a closed set" \
              " -- the cell quoted above is what tells them apart: a tier heading INSERTED into the middle of an existing table, which leaves the" \
              " rows below it with no header and silently re-tiers them (remove it, or give the new tier a" \
              " header row of its own); the header and delimiter rows of this table both deleted (restore" \
              " both); or the header cell edited to something SHAPED LIKE a question id, which leaves a" \
              " header row this parser cannot tell from a data row (restore `| ID | ... |`)."
        want = 3            # fall through and read this line as data: the rows are intact, the header is
                            # not, so re-reading them as a broken header would add noise and no signal.
                            # want == 3, not 0 and not 2, because WHICH edit happened decides whether a
                            # delimiter row follows and the parser cannot know which. All three were
                            # measured, complaints per single edit, on the header-and-delimiter-deleted
                            # input and on the header-cell-renamed-to-an-id-shape input:
                            #   want = 0 (require nothing): 1 and 2 -- the surviving delimiter is read as
                            #     data and earns "`----` is not a question id"
                            #   want = 2 (require one):     2 and 1 -- the absent delimiter earns "header
                            #     row at line N is not followed by a separator", naming a header row that
                            #     is not there
                            #   want = 3 (accept either):   1 and 1
                            # One edit, one complaint, on both inputs, is the property being bought here.
      } else {
        # The first table line looks like a header row whose first cell is neither `ID` nor a delimiter.
        print "!! line " NR ": the `### " tname[tier] "` table at line " open_line " has a header row" \
              " whose first cell is |" cell "|" viz(cell) ", not `ID`. Either that cell was edited -- restore" \
              " `| ID | ... |` -- or a tier heading was inserted just above a table that is not a severity" \
              " table, which this file may not contain. It was NOT deleted: deleting a header row leaves" \
              " its delimiter row as the first table line, which is reported separately and by name."
        want = 2; hdr_at = NR; hdr_nf = NF
        next                # the delimiter row is still expected next, so consuming it here keeps one
                            # edit to one complaint. `hdr_at`/`hdr_nf` are recorded even though this row
                            # is malformed: it IS the header row positionally, so it is what the
                            # cell-count check below must compare against. Leaving them unset would let that
                            # check reach back to a PREVIOUS tier whose delimiter was never consumed and
                            # report "the header row at line 93" about a delimiter row 21 lines later --
                            # a wrong-line diagnostic, which this parser must not print.
      }
    }
    if (want == 2) {
      if (cell ~ /^[-: ]+$/) {
        # GFM REQUIRES THE DELIMITER ROW TO HAVE THE SAME CELL COUNT AS ITS HEADER ROW; if it does not,
        # there is no table at all. Checking only that
        # "a header row must be followed by a delimiter row" is half the GFM rule -- and the
        # other half has a consequence, not just an inaccuracy: shortening one delimiter row to `|---|--|` under a
        # 3-column header leaves the map UNCHANGED and silent while a GFM renderer shows that entire severity
        # table as a paragraph of literal pipes, dropping it from 15 rendered tables to 14. ONE EDIT
        # REMOVING A WHOLE SEVERITY TABLE FROM THE VIEW A READER GETS is exactly what the rendered-view
        # of the residual-risk mitigation depends on not happening. `hdr_nf` is only set where a real
        # `| ID | ... |` header row was read, so this cannot fire in the branches that already refused.
        if (hdr_nf > 0 && NF != hdr_nf) {
          print "!! line " NR ": the `|----|` delimiter row here has " (NF - 2) " cell(s) but the" \
                " `| ID | ... |` header row at line " hdr_at " has " (hdr_nf - 2) ". GFM requires the two" \
                " counts to MATCH or the block is not a table at all -- measured, this renders as a" \
                " paragraph of literal `|` characters and the whole table disappears from the document," \
                " while the weights parse unchanged. Give the delimiter row one cell per header cell."
          want = 0; hdr_nf = 0; next
        }
        want = 0; hdr_nf = 0; next
      }
      # `hdr_at`, not `(NR - 1)`. The two agree in every reachable state -- `want == 2` is only ever
      # set on the line before this one. `hdr_at` is used because the
      # line number of the header row is HELD, and recomputing it is how a wrong-line diagnostic
      # arises (see `hdr_at`/`hdr_nf` in the branch above): computing a line number that is
      # already known invites exactly that defect.
      # viz(cell) IS LOAD-BEARING HERE, not decorative. A zero-width space inside the delimiter row
      # (`|--<U+200B>--|-------|----------|`) reaches this branch, and without disclosure the message reads
      # "is not followed by a `|----|` separator row -- found |----|" -- it displays `|----|` and says that
      # is not a `|----|`, which reads as proof the parser is broken rather than as evidence about the file.
      # Measured: that input renders 14 tables / 118 rows, the whole table gone.
      print "!! line " NR ": the `### " tname[tier] "` header row at line " hdr_at " is not followed by" \
            " a `|----|` separator row -- found |" cell "|" viz(cell) ". GFM requires that delimiter row," \
            " so what follows is not being rendered as a table either."
      want = 0; next
    }
    # AN EMPTY FIRST CELL IS A REFUSAL, NOT A SKIPPED ROW, which is what the grammar at the top of this
    # section already promises ("anything else in that cell is a REFUSAL, not a skipped row") and what the
    # code must do. `split("", tok, "/")` returns 0, so the loop below never runs, nothing is emitted
    # and without this rule NO complaint would be printed. Unrefused,
    # blanking the ID cell of `sec-21` would leave this parser at exit 0 with zero complaints and the id gone
    # from the map; the only sign would be the completeness gate downstream saying "Add one row per id" about a
    # row that is present and rendering (15 tables / 134 rows, unchanged), with no line number.
    if (cell == "") {
      print "!! line " NR ": the FIRST cell of this data row is empty. The first cell is the only one" \
            " read, so this row documents no question and the row renders in the document while" \
            " contributing no weight. Put the question id back, or delete the row."
      next
    }
    emitted = 0
    n = split(cell, tok, "/")
    for (i = 1; i <= n; i++) {
      t = tok[i]; sub(/^[ \t]+/, "", t); sub(/[ \t]+$/, "", t)
      if (t ~ /^[a-z]+-[0-9]+$/) { print t " " tier; emitted++; continue }
      if (t ~ /^[a-z]+-[0-9]+\.\.[0-9]+$/) {
        p = index(t, "-"); pre = substr(t, 1, p - 1); rest = substr(t, p + 1)
        d = index(rest, ".."); lo = substr(rest, 1, d - 1) + 0; hi = substr(rest, d + 2) + 0
        if (lo > hi) { print "!! line " NR ": range \"" t "\" counts backwards"; continue }
        for (k = lo; k <= hi; k++) { print pre "-" k " " tier; emitted++ }
        continue
      }
      print "!! line " NR ": ID cell token \"" t "\" is not a question id -- expected `sec-12`, a" \
            " ` / `-separated list of them, or a range like `fargate-1..2`" viz(t)
    }
    # `rows` IS SET ONLY BY A ROW THAT ACTUALLY YIELDED AN ID. Set before the loop, a row
    # whose ID cell produced nothing would still tell endtier() the tier owned a data row. The owns-a-row gate
    # exists to catch a tier whose table contributes no weights; a row that contributes none must not
    # satisfy it.
    if (emitted > 0) rows = 1
  }
  # A tier left open at EOF gets the same at-least-one-row check as one closed mid-file.
  END { endtier("the file ended") }
' "$SEV_MD") || {
  echo "reduce.sh: could not parse $SEV_MD -- awk exited nonzero, so the severity weights were NOT" \
    "read. Refusing rather than publishing a weighted score with weights nothing supplied." >&2
  exit 1; }
# NOT sorted here, deliberately: awk's output is in FILE order and the complaint lines below must stay
# that way. Sorting this pipeline would make the `head -10` of diagnostics show
# lexically-first line numbers -- "line 100" printed above "line 80" -- so the earliest and most
# diagnostic problem could be the one truncated away. The data lines get sorted separately, below.
# `LC_ALL=C` ON THESE TOO. SEV_RAW carries the awk complaints, and a complaint QUOTES the offending line --
# so on an invalid-UTF-8 input the bytes viz() is describing pass straight through this pipeline. Without it
# BSD sed exits 1 with "RE error: illegal byte sequence" here as well, and the diagnostic viz() worked to
# produce is lost one line before it is printed. The tools over FILE-DERIVED TEXT that a search could find
# all have it -- this pipeline, the B_DEF sed, the fence scan, the carriage-return awk and the main parse
# awk -- and the ones over ids and numbers are left alone deliberately. That is a statement about what was
# checked, not a guarantee: a new tool over file-derived text needs it too.
# ONE TOOL, SO A FAILURE IS DISTINGUISHABLE FROM AN EMPTY RESULT. `grep | sed` keyed on the result
# being non-empty could not be guarded, because `grep` exits 1 when it
# finds NOTHING, which is the normal clean-file case, and BSD `sed` also exits 1 on error. The two statuses are
# indistinguishable, so "no complaints" and "the extraction died" would look the same. awk exits 0 whether or not it
# printed anything, so a non-zero status here means a real failure and nothing else. It also keeps two
# locale-sensitive tools off a path that carries quoted file bytes.
SEV_BAD=$(printf '%s\n' "$SEV_RAW" | LC_ALL=C awk '/^!! /{ sub(/^!! /, ""); print }') || {
  echo "reduce.sh: could not extract the parse complaints for $SEV_MD -- awk exited nonzero. The complaints" \
    "exist (the parse produced them) but cannot be shown, and publishing a score while unable to display why" \
    "it should be refused is the worse of the two failures." >&2
  exit 1; }
if [ -n "$SEV_BAD" ]; then
  echo "reduce.sh: $SEV_MD is malformed -- the severity tables could not be read as data" >&2
  printf '%s\n' "$SEV_BAD" | head -10 | LC_ALL=C sed 's/^/  /' >&2
  echo "  The shape this file requires: every \`### High\`/\`### Medium\`/\`### Low\` heading owns exactly" >&2
  echo "  ONE table -- an \`| ID | ... |\` header row, a \`|----|\` separator, then at least one data" >&2
  echo "  row -- and each data row's FIRST cell is a question id (\`sec-12\`), a \` / \`-separated list of" >&2
  echo "  ids sharing one rationale, or a contiguous range (\`fargate-1..2\`). Nothing this parser cannot" >&2
  echo "  read is skipped, because a skipped row is a question whose documented weight stops applying" >&2
  echo "  with no sign that it did." >&2
  echo "  READ EACH COMPLAINT AS AN OBSERVATION, not as a diagnosis to be argued with. Each one says what" >&2
  echo "  the parser saw, at which line, and -- where a tier heading is what is missing -- quotes the" >&2
  echo "  nearest \`#\` line back to you verbatim with its line number, so you can compare that text against" >&2
  echo "  the required shape yourself. Likely causes are not ranked, because on ordinary edits" >&2
  echo "  the top-ranked cause can be other than the edit that was" >&2
  echo "  made: a heading reading \`### Medium ###\` would rank as DELETED or RETYPED, a renamed header" >&2
  echo "  cell as an INSERTED heading, a deleted header row as a RENAMED cell, and a blank line inside a" >&2
  echo "  table as a missing heading. Where a cause IS named above it is derived from state this parser" >&2
  echo "  holds -- which line ended the tier, which shape the first table line had -- and not guessed." >&2
  echo "  Do NOT resolve any of these by moving rows under a different heading. A tier reaches exactly" >&2
  echo "  one table, and re-tiering a table moves the published score." >&2
  exit 1
fi
# `LC_ALL=C sort` here is NOT what makes the output deterministic -- awk emits in file order, which is
# already deterministic, and removing this sort still produces byte-identical scores.json across repeated
# runs (measured). What it buys is that the PUBLISHED key order is id order rather than the order rows
# happen to sit in severity.md, so re-ordering two rows in the document does not churn scores.json, and
# the map is greppable and diffable by id. The sort on SEV_DUP below is a different matter and IS
# required for determinism -- awk's `for (i in n)` has no defined iteration order.
SEV_ROWS=$(printf '%s\n' "$SEV_RAW" | LC_ALL=C grep -v '^!! ' | LC_ALL=C grep -v '^[[:space:]]*$' \
           | LC_ALL=C sort)
[ -n "$SEV_ROWS" ] || { echo "reduce.sh: parsed ZERO severity rows out of $SEV_MD. The file exists but" \
  "carries no readable \`### High|Medium|Low\` table, so no question has a weight. An empty map would" \
  "make every question below unsourced; refusing here says why instead." >&2; exit 1; }
# WITHOUT ITS GUARD THIS GATE FAILS OPEN IN SILENCE. It keys on `$SEV_DUP` being non-empty, so with
# no `||` guard a dying awk leaves the variable empty, the test false, and
# a severity.md documenting one id TWICE at DIFFERENT WEIGHTS published at exit 0 with zero bytes of
# stderr. Its six sibling gates carry the same guard for the same reason.
# A gate of this shape is found by grepping the pattern across the file, not by trusting a list of
# known gates: a list misses instances that a grep of the pattern
# finds. `set -o pipefail` is on, so the guard catches a death in either stage of the pipeline.
SEV_DUP=$(printf '%s\n' "$SEV_ROWS" | LC_ALL=C awk '
  { n[$1]++; w[$1] = w[$1] " " $2 }
  END { for (i in n) if (n[i] > 1) print i " has " n[i] " rows, weight(s)" w[i] }' | LC_ALL=C sort) || {
  echo "reduce.sh: the duplicate-id check over $SEV_MD could not run -- awk or sort exited nonzero, so the" \
    "invariant 'each question has exactly one documented weight' was NOT checked. Refusing rather than" \
    "publishing a map in which one id could carry two different weights, where which one wins depends on" \
    "which row this parser read last." >&2
  exit 1; }
if [ -n "$SEV_DUP" ]; then
  echo "reduce.sh: question id(s) appear in more than one severity row in $SEV_MD -- each question must" \
    "have exactly one documented weight" >&2
  printf '%s\n' "$SEV_DUP" | head -10 | sed 's/^/  /' >&2
  echo "  Two rows for one id means the weight depends on which table the parser reads last, which is" >&2
  echo "  not a documented severity. Refused even when the two rows agree: an id filed under two" >&2
  echo "  tiers is a documentation defect either way. Delete the duplicate row." >&2
  exit 1
fi
SEVMAP=$(printf '%s\n' "$SEV_ROWS" | jq -Rn '
  [inputs | split(" ") | {key: .[0], value: (.[1]|tonumber)}] | from_entries') || {
  echo "reduce.sh: could not turn the parsed severity rows into a map -- jq exited nonzero." >&2
  exit 1; }
# COMPLETENESS, both directions. "Authoritative" means every scored question's weight has a source in
# that file and nothing in that file describes a question that does not exist. Neither direction is
# cosmetic: an id with no row would take a default weight that a reader could not check,
# and a row for a retired id is a reader being shown a weight nothing applies.
SEV_UNSOURCED=$(jq -r --argjson sev "$SEVMAP" 'select($sev[.id] == null) | .id' "$W/results.jsonl" \
  | LC_ALL=C sort -u) || {
  echo "reduce.sh: the severity completeness gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked." >&2; exit 1; }
if [ -n "$SEV_UNSOURCED" ]; then
  echo "reduce.sh: question(s) in $W/results.jsonl have no row in $SEV_MD, so their severity weight has" \
    "no source. Refusing rather than weighting them at a default nobody documented -- that default is" \
    "how a question ends up scored Medium while the tables say Low." >&2
  printf '%s\n' "$SEV_UNSOURCED" | head -20 | sed 's/^/  /' >&2
  echo "  Add one row per id to that pillar's \`### High\`, \`### Medium\` or \`### Low\` table, with the" >&2
  echo "  reasoning -- the tier you file it under IS the weight the score will use." >&2
  exit 1
fi
SEV_STALE=$(jq -s -r --argjson sev "$SEVMAP" '([.[].id] | unique) as $ids | ($sev|keys) - $ids | .[]' \
  "$W/results.jsonl") || {
  echo "reduce.sh: the severity staleness gate could not run -- jq exited nonzero over" \
    "$W/results.jsonl, so the invariant was NOT checked." >&2; exit 1; }
if [ -n "$SEV_STALE" ]; then
  echo "reduce.sh: $SEV_MD documents a severity for question id(s) that $W/results.jsonl does not" \
    "contain, so the tables describe questions this skill does not ask" >&2
  printf '%s\n' "$SEV_STALE" | head -20 | sed 's/^/  /' >&2
  echo "  If any pillar scorer did not exit 0, results.jsonl is incomplete: re-collect into a new" >&2
  echo "  eks-war-* work directory and re-score all five pillars there. Only if all five scorers" >&2
  echo "  exited 0: every scorer emits every one of its questions on every run (a question that does" >&2
  echo "  not apply is emitted as \`na\`), so a documented id that is absent is a row left behind by a" >&2
  echo "  question that was renamed or removed -- not a cluster-specific omission; delete the row." >&2
  exit 1
fi

jq -s -r \
  --argjson nodes_total "$NODES_TOTAL" --argjson nodes_ready "$NODES_READY" \
  --argjson pods_wl "$PODS_WL" --argjson pods_run "$PODS_RUN" \
  --argjson sevmap "$SEVMAP" '
  def sc: {all:100,most:75,some:50,none:0}[.];
  # WAF risk weight per question: High=3, Medium=2, Low=1 -- read from $sevmap, which the section above
  # parsed out of references/severity.md. NO `// 2` default: the completeness gate has already proved
  # every id in results.jsonl has a row, so a miss here is a broken invariant rather than a question
  # someone forgot, and error() says so instead of quietly weighting it Medium.
  def sev($id): ($sevmap[$id] // error("no severity row for \($id) in references/severity.md"));
  def pillars: ["operational-excellence","security","reliability","performance-efficiency","cost-optimization"];
  (map(select(.track=="measured"))) as $m |
  (map(select(.track=="governance"))) as $g |
  (pillars | map(. as $p |
     ($m|map(select(.pillar==$p))) as $q |
     ($q|map(select(.state!="na"))) as $appl |
     ($q|length) as $tot |
     ($appl|length) as $ac |
     ($q|map(select(.state=="na"))|length) as $na |
     { pillar:$p, total:$tot, applicable:$ac, na:$na,
       coverage: (if $tot==0 then 0 else (($ac*100/$tot)|floor) end),
       score: (if $tot==0 or ($ac*2 < $tot) then "INSUFFICIENT"
               else (($appl|map((.state|sc)*sev(.id))|add) / ($appl|map(sev(.id))|add) | round) end) }
  )) as $ps |
  ($ps|map(select(.score|type=="number"))) as $scored |
  ($g|map(select(.state!="unknown" and .state!="na"))) as $ga |
  # ---- viability and liveness, resolved before any number is published ----------------------------
  # Both counts are of Linux nodes: Windows nodes are excluded where NODES_TOTAL/NODES_READY are read.
  # NOT VIABLE keys on nodes==0 ALONE. Requiring nodes==0 AND workload_pods==0 would let a
  # cluster with no nodes but declared pods escape BOTH gates: viability would need zero pods, and the
  # liveness check needs at least one node to look at. Such a cluster would publish a full numeric score.
  # A cluster with no nodes has no data plane whatever its manifests declare, so pods are irrelevant.
  ($nodes_total == 0) as $not_viable |
  # NOT HEALTHY: nodes exist and none is Ready. Withholds the headline, keeps the pillar detail --
  # the configuration is real and worth reporting, it just does not describe a working system.
  ($nodes_total > 0 and $nodes_ready == 0) as $not_healthy |
  # Under half the workload pods Running: publish the score, carry a warning. Deliberately NOT a
  # refusal and deliberately NOT a filter -- a batch cluster legitimately idles at zero running pods,
  # and excluding non-Running pods from the ratios would make a cluster that cannot schedule its
  # workload score HIGHER. Judge what is declared; disclose what is running.
  ($pods_wl > 0 and ($pods_run * 2) < $pods_wl) as $pods_down |
  (if ($scored|length) >= 4 then (($scored|map(.score)|add)/($scored|length)|round)
   else "WITHHELD (insufficient pillar coverage)" end) as $numeric |
  { technical_overall: (if $not_viable then "NOT VIABLE — no data plane"
                        elif $not_healthy then "NOT HEALTHY — no Linux node is Ready"
                        else $numeric end),
    # Every surface reads these rather than deriving them, so the chat headline, the markdown table and
    # the HTML hero cannot disagree about whether the cluster was alive when it was measured.
    liveness: { nodes_total: $nodes_total, nodes_ready: $nodes_ready,
                workload_pods: $pods_wl, pods_running: $pods_run,
                viable: ($not_viable|not), healthy: (($not_viable or $not_healthy)|not),
                withheld_reason: (if $not_viable then "no data plane: 0 Linux nodes"
                                  elif $not_healthy then "no Linux node is Ready (\($nodes_total) Linux node(s) exist)"
                                  else null end),
                warning: (if ($not_viable|not) and ($not_healthy|not) and $pods_down
                          then "only \($pods_run) of \($pods_wl) workload pods are Running"
                          else null end),
                # What the number WOULD have been. Kept so a reader can see the configuration score a
                # withholding suppressed, without the report having to publish it as the verdict.
                suppressed_overall: (if $not_viable or $not_healthy then $numeric else null end) },
    pillars: $ps,
    governance: { answered: ($ga|length), total: ($g|length),
                  score: (if ($ga|length)==0 then "Not Assessed" else (($ga|map(.state|sc)|add)/($ga|length)|round) end) },
    # The weights this run scored with, id by id, exactly as references/severity.md documents them.
    # PUBLISHED, not merely used: render-report.py labels the Severity column and orders the
    # Immediate/Short-term/Strategic tiers from this map, so the report cannot rank a finding by a
    # weight the score was not computed from. It is also the audit trail -- a scores.json in a ticket
    # carries the weights behind its own numbers. Keyed in id order (see the sort above), so that
    # re-ordering rows in severity.md does not churn this file; determinism does not depend on it.
    severity: $sevmap }
' "$W/results.jsonl" \
  | { if [ -n "$OUT" ]; then cat > "$OUT"; else cat; fi; }
