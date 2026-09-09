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
# It is also the single source of the severity weights. They previously appeared three times --
# here, in SKILL.md's inline jq, and in render-report.py's SEV sets -- kept in sync by a comment.
set -uo pipefail
W="${1:?usage: reduce.sh <workdir>   # reads <workdir>/results.jsonl}"
[ -f "$W/results.jsonl" ] || { echo "reduce.sh: no results.jsonl in $W -- run the pillar scorers first" >&2; exit 1; }
[ -s "$W/results.jsonl" ] || { echo "reduce.sh: $W/results.jsonl is empty -- nothing was scored" >&2; exit 1; }
jq -s -r '
  def sc: {all:100,most:75,some:50,none:0}[.];
  # WAF risk weight per question: High=3, Medium=2 (default), Low=1
  def sev($id): ({
    "sec-2":3,"sec-6":3,"sec-18":3,"rbac-1":3,"sec-21":3,"sec-29":3,"sec-4":3,"sec-30":3,
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
  { technical_overall: (if ($scored|length) >= 4 then ($scored|map(.score)|add)/($scored|length)|round else "WITHHELD (insufficient pillar coverage)" end),
    pillars: $ps,
    governance: { answered: ($ga|length), total: ($g|length),
                  score: (if ($ga|length)==0 then "Not Assessed" else (($ga|map(.state|sc)|add)/($ga|length)|round) end) } }
' "$W/results.jsonl"
