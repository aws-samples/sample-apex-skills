#!/usr/bin/env bash
# Severity-weighted reducer. Reads <workdir>/results.jsonl, writes scores.json to stdout.
#
# Usage:  ./reduce.sh "$WORK" > "$WORK/scores.json"
#
# This is a SHIPPED asset, not a copy of one. It used to exist only as a fenced jq block inside
# SKILL.md Step 7 that printed to stdout, while `render-report.py` reads `$WORK/scores.json` and
# hard-exits without it. No documented step wrote that file: the agent had to infer the redirect.
# An improvised step on the determinism spine is exactly where a silent divergence starts, so the
# reducer is a file the workflow invokes rather than a block the agent retypes.
#
# The severity weights below appeared three times -- here, in SKILL.md's inline jq, and in
# render-report.py's SEV sets. The SKILL.md copy is gone. render-report.py still keeps its own, because it
# needs the weights for the risk chips and the improvement-plan ordering without shelling out. Nothing
# enforces that the two agree -- no shipped check diffs them -- so this is the source of truth for
# SCORING, not the only copy -- edit both or neither.
set -uo pipefail
W="${1:?usage: reduce.sh <workdir>   # reads <workdir>/results.jsonl, nodes.json, pods.json}"
[ -f "$W/results.jsonl" ] || { echo "reduce.sh: no results.jsonl in $W -- run the pillar scorers first" >&2; exit 1; }
[ -s "$W/results.jsonl" ] || { echo "reduce.sh: $W/results.jsonl is empty -- nothing was scored" >&2; exit 1; }

# ── VIABILITY AND LIVENESS LIVE HERE, not in the report layer ──────────────────────────────────────
# These gates used to be prose in SKILL.md Step 4/4b plus Python in render-report.py, which meant the
# HTML withheld a dead cluster's score while `reduce.sh` still emitted a number and the chat/markdown
# path printed it. A gate that only one of three surfaces honours is not a gate. Both now resolve in
# the score contract, so every consumer of scores.json inherits them and none can recompute a
# different answer.
#
# Required, not optional: a work dir without nodes.json/pods.json cannot answer "is this cluster
# alive", and silently scoring as though it were is the exact failure this replaces.
for f in nodes pods; do
  [ -f "$W/$f.json" ] || { echo "reduce.sh: no $f.json in $W -- viability and liveness cannot be" \
    "evaluated without it, and a score that skips those gates is the defect this file exists to" \
    "prevent. Re-run collection." >&2; exit 1; }
  jq -e . "$W/$f.json" >/dev/null 2>&1 || { echo "reduce.sh: $W/$f.json is not valid JSON" >&2; exit 1; }
  # `.items` must be PRESENT, not merely navigable. The counts below used `.items[]?`, whose safe
  # navigation made an ABSENT key indistinguishable from an empty list -- so a truncated or malformed
  # nodes.json (`{}`, or an error envelope that happens to be valid JSON) counted as zero nodes and
  # published "NOT VIABLE — no data plane" for a cluster whose data plane was never looked at. That is
  # the worst possible verdict to get wrong: it is the one that suppresses the score entirely.
  # `kubectl get nodes -o json` returns {"items":[]} on a genuinely empty cluster, so a missing
  # `.items` is always a bad FILE and never a bad CLUSTER. render-report.py's need_list() already
  # refuses this exact input for the same reason; the gate's owner must not be the laxer of the two.
  jq -e 'type=="object" and has("items") and (.items|type=="array")' "$W/$f.json" >/dev/null 2>&1 || {
    echo "reduce.sh: $W/$f.json has no \`.items\` array -- this file is MALFORMED, not a cluster with" \
      "no ${f}. An empty cluster still returns {\"items\":[]}; an absent or non-array .items means the" \
      "collection was truncated or returned something other than a ${f} list. Scoring it would report" \
      "NOT VIABLE for a bad file. Re-run collection." >&2; exit 1; }
done

# A "workload pod" is one outside the AWS/Kubernetes system namespaces. SKILL.md previously carried
# TWO definitions of this -- Step 4 excluded only kube-system/kube-node-lease/kube-public, Step 4b
# excluded every kube-*/amazon-* -- so the viability gate and the liveness gate disagreed about which
# pods counted. Unified here on the broader prefix match, which is the one that correctly ignores
# add-on namespaces such as amazon-guardduty.
#
# No `?` on `.items[]` below, deliberately: the guard above has already proven the key is an array, and
# the safe-navigation operator is what let a malformed file masquerade as an empty one.
NODES_TOTAL=$(jq '[.items[]]|length' "$W/nodes.json")
NODES_READY=$(jq '[.items[]|select([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0)]|length' "$W/nodes.json")
PODS_WL=$(jq '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)]|length' "$W/pods.json")
PODS_RUN=$(jq '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)")|not) and .status.phase=="Running")]|length' "$W/pods.json")

# ── results.jsonl STRUCTURE, validated before the scoring pipeline can see it ───────────────────────
# Every line must parse as JSON *and* be an object. This used to be checked only implicitly by the
# state-enum validator below, which ran with `2>/dev/null` -- so a syntactically broken line produced
# no hit there, sailed through, and blew up inside the main `jq -s` pipeline as a bare
# "jq: parse error: Invalid literal at line 3, column 7" with exit 5: jq's code and jq's wording, not
# this file's exit-1 refusal convention, and with no indication of which file was at fault. A non-object
# line (`3`, `null`, `[...]`) escaped the same way, via "Cannot index number with state".
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
' "$W/results.jsonl")
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
MISSINGFIELDS=$(jq -r '
  . as $r
  | ["pillar","id","track","state"]
  | map(select(($r[.] == null) or (($r[.]|type)=="string" and ($r[.]|length)==0)))
  | select(length > 0)
  | "line \(input_line_number): missing/empty field(s) \(join(",")) -- \($r|tostring|.[0:80])"
' "$W/results.jsonl")
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
# already wrote. Observed: Performance Efficiency 59 -> 57 with total 11 -> 12. It also corrupts the
# governance denominator, because Step 6's interactive mode appends a second record per governance id
# with the answered state: 0 of 29 became 1 of 30, and a fully-answered interview would report 29 of 58.
# Appending is not idempotent, so the reducer refuses rather than average two answers to one question.
DUPIDS=$(jq -s -r 'map(.id // "(record with no id)") | group_by(.) | map(select(length>1))
  | map("\(.[0]|tostring) (\(length) records)") | .[]' "$W/results.jsonl")
if [ -n "$DUPIDS" ]; then
  echo "reduce.sh: duplicate question id(s) in $W/results.jsonl -- each question must appear exactly once" >&2
  printf '%s\n' "$DUPIDS" | head -10 | sed 's/^/  /' >&2
  echo "  A duplicate double-counts its question: it moves the published pillar score and inflates the" >&2
  echo "  governance denominator, so it is refused here rather than merged or averaged." >&2
  echo "  Most likely cause: a pillar scorer block was re-run after a SCORER ABORT and appended a" >&2
  echo "  second copy of everything it had already written. Fix by re-running collect.sh (it truncates" >&2
  echo "  results.jsonl), or truncate it yourself with ': > $W/results.jsonl' and re-score ALL five" >&2
  echo "  pillars." >&2
  echo "  If the duplicated ids are governance questions, an interview answer was APPENDED on top of" >&2
  echo "  the 'unknown' placeholder the pillar block already wrote. Rewrite that line in place instead" >&2
  echo "  of appending, so each governance question keeps exactly one record." >&2
  exit 1
fi

# Validate the state enum before scoring. A numeric or out-of-enum `state` used to reach jq's lookup
# table and produce a bare interpreter error with exit 5 -- jq's code, not this file's exit-1
# convention. `unknown` is legal ONLY on the governance track, per SKILL.md's scoring model: the
# measured lookup table {all,most,some,none} has no `unknown` entry and the applicable pool filters
# only `na`, so a measured record with state "unknown" reached the multiplication and died with
# "null (null) and number (3) cannot be multiplied", exit 5, no scores.json. Admitting `unknown` on
# every track is what let that record through this gate.
BADSTATE=$(jq -r 'select(((.state|type)!="string")
  or (((.state|IN("all","most","some","none","na"))
       or (.state=="unknown" and .track=="governance"))|not))
  | "\(.id // "?") track=\(.track|tostring) state=\(.state|tostring)"' "$W/results.jsonl")
if [ -n "$BADSTATE" ]; then
  echo "reduce.sh: illegal state value(s) in $W/results.jsonl -- legal: all most some none na;" \
    "unknown is legal on the governance track ONLY" >&2
  printf '%s\n' "$BADSTATE" | head -5 | sed 's/^/  /' >&2
  exit 1
fi

jq -s -r \
  --argjson nodes_total "$NODES_TOTAL" --argjson nodes_ready "$NODES_READY" \
  --argjson pods_wl "$PODS_WL" --argjson pods_run "$PODS_RUN" '
  def sc: {all:100,most:75,some:50,none:0}[.];
  # WAF risk weight per question: High=3, Medium=2 (default), Low=1
  def sev($id): ({
    "sec-2":3,"sec-38":3,"sec-6":3,"sec-18":3,"rbac-1":3,"sec-21":3,"sec-29":3,"sec-4":3,"sec-30":3,
    "net-2":3,"sec-11":3,"podsec-2":3,"podsec-4":3,"lens-11":3,"sec-26":3,
    "ope-5":3,"ope-6":3,"ope-11":3,"ope-12":3,
    "rel-1":3,"rel-6":3,"rel-7":3,"rel-12":3,"rel-13":3,"lens-15":3,"perf-1":3,
    "cost-6":3,"cost-8":3,"cost-9":3,
    "sec-5":1,"sec-17":1,"sec-8":1,"sec-23":1,"sec-27":1,"sec-28":1,"net-1":1,"net-3":1,
    "sec-12":1,"sec-32":1,"sec-35":1,"sec-36":1,"sec-37":1,
    "ope-3":1,"ope-4":1,"ope-10":1,"ope-14":1,"ope-17":1,"ope-18":1,
    "fargate-1":1,"fargate-2":1,"fargate-3":1,"fargate-4":1,"lens-1":1,
    "rel-11":1,"rel-15":1,"rel-16":1,"rel-17":1,"rel-19":1,"rel-20":1,"rel-23":1,"lens-2":1,"lens-3":1,
    "perf-2":1,"perf-4":1,"perf-5":1,"perf-6":1,"lens-5":1,"lens-8":1,"lens-9":1,"lens-10":1,
    "cost-3":1,"cost-4":1,"lens-4":1,"lens-13":1,"lens-16":1
  }[$id]) // 2;
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
  # NOT VIABLE keys on nodes==0 ALONE. It used to require nodes==0 AND workload_pods==0, which left a
  # cluster with no nodes but declared pods escaping BOTH gates: viability needed zero pods, and the
  # liveness check needed at least one node to look at. Such a cluster published a full numeric score.
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
                        elif $not_healthy then "NOT HEALTHY — no node is Ready"
                        else $numeric end),
    # Every surface reads these rather than deriving them, so the chat headline, the markdown table and
    # the HTML hero cannot disagree about whether the cluster was alive when it was measured.
    liveness: { nodes_total: $nodes_total, nodes_ready: $nodes_ready,
                workload_pods: $pods_wl, pods_running: $pods_run,
                viable: ($not_viable|not), healthy: (($not_viable or $not_healthy)|not),
                withheld_reason: (if $not_viable then "no data plane: 0 nodes"
                                  elif $not_healthy then "no node is Ready (\($nodes_total) node(s) exist)"
                                  else null end),
                warning: (if ($not_viable|not) and ($not_healthy|not) and $pods_down
                          then "only \($pods_run) of \($pods_wl) workload pods are Running"
                          else null end),
                # What the number WOULD have been. Kept so a reader can see the configuration score a
                # withholding suppressed, without the report having to publish it as the verdict.
                suppressed_overall: (if $not_viable or $not_healthy then $numeric else null end) },
    pillars: $ps,
    governance: { answered: ($ga|length), total: ($g|length),
                  score: (if ($ga|length)==0 then "Not Assessed" else (($ga|map(.state|sc)|add)/($ga|length)|round) end) } }
' "$W/results.jsonl"
