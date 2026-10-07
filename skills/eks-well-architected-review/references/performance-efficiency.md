# ⚡ Performance Efficiency

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**12 questions** — Resource requests, instance types, VPA, scheduling, DNS optimization, traffic routing

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` (Not
Assessed). The per-question sections below give rationale and remediation.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data.
> Use the prose for rationale and remediation wording only.

---

## Table of Contents

1. [Performance Efficiency scorer — run by `assets/score.sh`, not by hand](#performance-efficiency-scorer--run-by-assetsscoresh-not-by-hand)
2. [Workload sizing, scheduling and rollout](#workload-sizing-scheduling-and-rollout)
   - [perf-1: Do containers have CPU and memory requests set for accurate scheduling?](#perf-1-do-containers-have-cpu-and-memory-requests-set-for-accurate-scheduling)
   - [perf-2: Is Vertical Pod Autoscaler (VPA) deployed for right-sizing resource requests?](#perf-2-is-vertical-pod-autoscaler-vpa-deployed-for-right-sizing-resource-requests)
   - [perf-3: Are appropriate EC2 instance types selected for the workload requirements?](#perf-3-are-appropriate-ec2-instance-types-selected-for-the-workload-requirements)
   - [perf-4: Do deployments use RollingUpdate strategy for zero-downtime updates?](#perf-4-do-deployments-use-rollingupdate-strategy-for-zero-downtime-updates)
   - [perf-5: Are pod anti-affinity or topology spread constraints configured?](#perf-5-are-pod-anti-affinity-or-topology-spread-constraints-configured)
3. [Resource Optimization](#resource-optimization)
   - [perf-6: Is there diversity in EC2 instance types across node groups?](#perf-6-is-there-diversity-in-ec2-instance-types-across-node-groups)
4. [Node resource utilization](#node-resource-utilization)
   - [perf-7: Are node CPU and memory resources being utilized efficiently (requests vs capacity)?](#perf-7-are-node-cpu-and-memory-resources-being-utilized-efficiently-requests-vs-capacity)
5. [EKS Best Practices](#eks-best-practices)
   - [lens-5: Do pods use Kubernetes standard labels (app.kubernetes.io/name)?](#lens-5-do-pods-use-kubernetes-standard-labels-appkubernetesioname)
   - [lens-6: Do nodes use a SUPPORTED EKS-optimized AMI (Amazon Linux 2023 or Bottlerocket)?](#lens-6-do-nodes-use-a-supported-eks-optimized-ami-amazon-linux-2023-or-bottlerocket)
   - [lens-8: Do pods override CoreDNS ndots to ≤2 for faster DNS resolution?](#lens-8-do-pods-override-coredns-ndots-to-2-for-faster-dns-resolution)
   - [lens-9: Do LoadBalancer services use externalTrafficPolicy: Local?](#lens-9-do-loadbalancer-services-use-externaltrafficpolicy-local)
   - [lens-10: Are services configured with topology-aware routing?](#lens-10-are-services-configured-with-topology-aware-routing)

---

## Performance Efficiency scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh performance-efficiency "$WORK"` extracts this block and runs it. Do not paste it
into a shell: it defines shell functions (`emit`, `rl`, `g`, `m`…) and calls them once per question, and a Bash
permission rule matches literal command text — so no rule can match a function name and every call
prompts, or fails outright under a no-prompt policy. Appends one JSONL line per question to
`$WORK/results.jsonl`.

Every line carries `pillar`, `id`, `track`, `state` and `detail` — the shape SKILL.md Step 5 documents —
and, for the questions whose scorer runs an `rl` line, a **sixth `resources` key naming the objects the
check counted**, so the report can print `payments/api` instead of `7/9` without re-implementing the
detection in Python. `resources` is evidence, never verdict: it is built by a separate `jq` call that
cannot abort the question, so a broken name expression costs the list and nothing else. Three states are
distinguishable and the report says which: **no key** (this question publishes no list), **`null`** (the
list could not be built), **empty arrays** (the check looked and found nothing).

The `m`/`m2`/`m3`/`m4` thresholds are the determinism guarantee and are not yours to edit. Do not
hand-edit a `g` call.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end; def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end; def isec2: ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not); def hyx($h): if $h>0 then " (\($h) EKS Hybrid Node(s) excluded: they run on infrastructure outside AWS and this question does not judge them)" else "" end; def hyna($h;$why): "na~no EC2 nodes — this cluster runs \($h) EKS Hybrid Node(s), which run on infrastructure outside AWS: \($why)"; def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows"; def islinux: isec2 and (iswin|not); def iswinspec: ((.os.name // "")=="windows") or ((.nodeSelector["kubernetes.io/os"] // "")=="windows") or ((.nodeSelector["beta.kubernetes.io/os"] // "")=="windows") or (.nodeSelector["node.kubernetes.io/windows-build"] != null) or (((.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms)//[]) as $ts|(($ts|length)>0) and ($ts|any(.[]; any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|any(.[]; .=="windows")) and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux")) and ($v|all(.[]; . != "windows"))))) or (($k=="node.kubernetes.io/windows-build") and ((($o=="In") and (($v|length)>0)) or ($o=="Exists"))))))) and ($ts|all(.[]; ((((.matchExpressions//[])|length)==0) and (((.matchFields//[])|length)==0)) or any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux"))) or ($o=="DoesNotExist"))) or (($k=="node.kubernetes.io/windows-build") and (($o=="In") or ($o=="Exists")))))))); def winds: [.items[]?|select((.spec.template.spec//{})|iswinspec)|{key:((.metadata.namespace//"")+"/"+(.metadata.name//"")),value:true}]|from_entries; def iswinpod($w): (.spec|iswinspec) or ((.metadata.namespace//"") as $ns|any(.metadata.ownerReferences[]?; ((.kind//"")=="DaemonSet") and ($w[$ns+"/"+(.name//"")]//false))); def winx($w): if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end; def winpx($w): if $w>0 then " (\($w) Windows pod(s) not assessed — this skill supports Linux nodes only)" else "" end; def winna($w): "na~NOT ASSESSED — the only nodes this question would judge are \($w) Windows node(s); this skill supports Linux nodes only"; def winpna($w): "na~NOT ASSESSED — the only pods this question would judge are \($w) Windows pod(s); this skill supports Linux nodes only";'
# Shape guard `rl` applies to every program: the result must be an object with `pass` and `fail` string
# arrays (optional `context`, `kind`, `excluded`, `context_only`); anything else is recorded as an `rl`
# failure. `{pass,fail}` rebuilds the object so extra keys cannot be smuggled through.
RQ='|if (type=="object") and ((.pass|type)=="array") and ((.fail|type)=="array") and (((.context//[])|type)=="array") and (([(.pass+.fail+(.context//[]))[]|select(type!="string")]|length)==0) and ((.kind==null) or (.kind=="field") or (.kind=="existence")) and ((.excluded==null) or (((.excluded|type)=="number") and (.excluded>=0) and ((.excluded|floor)==.excluded))) and ((.context_only==null) or ((.context_only|type)=="boolean")) then {pass,fail}+(if (.context|type)=="array" then {context} else {} end)+(if .kind!=null then {kind} else {} end)+(if .excluded!=null then {excluded} else {} end)+(if .context_only==true then {context_only:true} else {} end) else error("rl: the program did not return {pass:[string],fail:[string]} with optional context:[string], kind:field|existence, excluded:integer, context_only:boolean") end'
# Build the record with jq --arg, not printf: `detail` carries cluster-controlled strings, and with printf
# a `"` could forge a duplicate `state` key and a newline could forge records in other pillars.
# Two details are load-bearing:
#   -c   without it results.jsonl stops being JSONL, and score.sh's already-scored refusal greps the
#        compact literal `"pillar":"performance-efficiency"`.
#   ||   this block runs with NO `set -e`; without the guard one failing record leaves the file a record
#        short and only reduce.sh's severity staleness gate notices, naming the wrong cause.
# Key order stays pillar,id,track,state,detail (SKILL.md Step 5 documents it); `resources` is a sixth key
# appended only for questions that ran `rl`.
# `--argjson` can fail on an oversized evidence list: it is ONE argv entry, and on Linux a single argument
# is capped at 128 KiB (`execve`: "Argument list too long"). The abort below also covers that case.
# The ID is re-asserted, not assumed: a stale evidence list from the previous question is dropped rather
# than attached to this one.
# Five files carry this helper; if you change one, change all five.
emit(){ local rs=false
  if [ "${RESID:-}" = "$1" ]; then rs="${RES:-null}"; fi
  RES= RESID=
  jq -cn --arg id "$1" --arg tr "$2" --arg st "$3" --arg de "$4" --argjson rs "$rs" \
  '{pillar:"performance-efficiency",id:$id,track:$tr,state:$st,detail:$de}+(if $rs==false then {} else {resources:$rs} end)' >> "$W/results.jsonl" \
  || { printf 'SCORER ABORT [%s]: the record was not emitted -- the jq call failed, the OS refused to start it, or the append to results.jsonl failed; any message jq or the OS printed is above. On a large fleet suspect the evidence list rather than the record: the list reaches jq as ONE --argjson argument, so many thousand names can exceed the OS argument-size limit and execve fails with "Argument list too long" before jq runs.\n' "$1" >&2; exit 1; }; }
# rl <id> <collection-file>... '<jq program>'  -- NAME the objects the next `emit` counted.
#
# Why: the report must print `payments/api` rather than `7/9`; a correct count over the wrong set is the
# scoping bug a bare count hides. The names are built in jq, next to the verdict, because re-deriving the
# detection in Python would mismatch on truthiness (jq's `select(.x)` keeps `{}`, `[]`, `""` and `0`;
# Python's `bool()` rejects all four). render-report.py only prints what the scorer emits.
# It is a separate jq call because one SCORER ABORT costs the whole pillar its score and evidence must
# not be able to do that. `rl` swallows its own failure, records `resources: null`, and the `m` line
# scores as usual. Three states: no `resources` key = no list is published; `null` = the list could not
# be built; `[]` = the check looked and found nothing.
# The selection test appears twice (in `rl` and in `m`); the report checks the list's counts against the
# ratio in `detail`. Write `fail` as the complement (`$all - $pass`) so the test appears once in `rl`.
# Failure text: jq's stderr goes to $RLERR (`rl.stderr` in the per-run scorer directory score.sh made,
# never a fixed name in $W) and is read back into the message; the query is not re-run, because a second
# execution could fail differently. jq's words are quoted only when that path is a writable regular file.
rl(){ local id="$1"; shift; local fs=(); while [ "$#" -gt 1 ]; do fs+=("$W/$1.json"); shift; done; local r n q e= ef="${RLERR:-/dev/null}"; r=$(jq -c "$B $1 $RQ" "${fs[@]}" 2>"$ef"); q=$?; if [ "$q" = 0 ] && [ -n "$r" ] && n=$(printf '%s' "$r" | wc -l | tr -d ' ') && [ "$n" = 0 ]; then RES="$r" RESID="$id"; else RES=null RESID="$id"; if [ ! -f "$ef" ] || [ ! -w "$ef" ]; then e="jq's stderr could not be captured to $ef, so any OS message is on the line above"; else [ -s "$ef" ] && e=$(tr -s '[:space:]' ' ' < "$ef"); e="${e# }"; e="${e% }"; [ -n "$e" ] && e="; jq said: $e"; if [ "$q" != 0 ]; then e="jq exited $q$e"; elif [ -z "$r" ]; then e="jq exited 0 and produced no output at all$e"; else e="jq exited 0 but produced $((n+1)) results, and an evidence list is exactly one$e"; fi; fi; printf 'RESOURCE LIST SKIPPED [%s]: the evidence list could not be built -- %s. THE VERDICT IS UNAFFECTED -- this is not a finding and not a scoring error; the report will say that this step failed and that there is no list for this question.\n' "$id" "$e" >&2; fi; return 0; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# m2 reads two files (perf-6 uses it for the cluster.json Auto Mode gate); the digit is the input count, from
# which render-report.py derives arity. Byte-identical in reliability.md, operational-excellence.md and
# cost-optimization.md.
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

# perf-1 is a flattener: the `m` program binds `.spec.containers[]?` and keeps nothing of the pod, so a
# plain copy would list bare container names (`app`, twice, from two pods). The `rl` line binds `$pod`
# BEFORE descending and names entries `<namespace>/<pod> / <container>`.
# Its test is the `m` line's own `select(.resources.requests.cpu and .resources.requests.memory)` with
# `.c.` in front: BOTH keys, so a cpu-only container is a fail on both sides.
# The list is built in jq to keep jq's truthiness: `requests: {cpu: "", memory: "100Mi"}` and
# `{cpu: 0, memory: 0}` pass here and would fail a Python `bool()` re-derivation. The
# `na~no workload containers` arm has two empty arrays and no `n/m`.
# TERMINATED PODS ARE OUT OF THE DENOMINATOR on both lines: collect.sh runs `kubectl get pods -A` with no
# phase filter, so unreaped `Succeeded`/`Failed` pods (most of the file on a CronJob cluster) are in
# pods.json, and a request cannot be set on an exited pod, so counting one is a fail nobody can clear.
# `//""` is safe on `.status.phase`: it is a STRING, so `//` only swallows an absent/null phase (an
# unscheduled pod, which belongs in the denominator). Do NOT copy it onto a boolean field: jq treats
# `false` as absent.
# Every copy of the predicate must agree byte for byte; this must print 1:
#     grep -ho 'select((\.status\.phase//"")|IN("Succeeded","Failed")|not)' references/*.md references/*/*.md | sort -u | wc -l
# WINDOWS PODS ARE OUT OF THE DENOMINATOR (Linux nodes only): `iswinpod($wds)` (B), applied after the
# namespace and phase filters; `winpx` discloses the count, `rl` names them in `context`, and if they are the
# only workload pods the answer is `winpna` (`na`), not a Pass.
rl perf-1 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wpn|($wpn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pod|.spec.containers[]?|{n:($pod+" / "+(.name//"?")),c:.}] as $c|[$c[]|select(.c.resources.requests.cpu and .c.resources.requests.memory)] as $p|(if $wp>0 then ["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wpn else [] end) as $cx|if ($c|length)==0 and $wp>0 then {pass:[],fail:[],context:$cx,context_only:true} else {pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if $wp>0 then {context:$cx} else {} end) end'
m2 perf-1 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory)]|length) as $ok| if $t==0 and $wp>0 then winpna($wp) elif $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) requests (workloads)"+winpx($wp) end'
m perf-2 deployments 'if ([.items[]|select(.metadata.name|test("vertical-pod-autoscaler|(^|-)vpa-(recommender|updater|admission-controller)$"))|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~VPA" else "none~none" end'
# perf-3 -- previous-generation instance share, pinned to AWS's published list.
# AWS, ec2/latest/instancetypes/instance-types.html "Previous generation instances":
#   General purpose  A1 | M1 | M2 | M3 | M4 | T1
#   Compute          C1 | C3 | C4
#   Memory           R3 | R4
#   Storage          I2
#   Accelerated      G3 | P3 | P3dn
# `[a-z]*` before the dot keeps suffixed members of a previous-gen family (p3dn); the generation ranges
# exclude m5, c5 and t2.
# THE TEST IS A DENYLIST: a family it does not name is a family it did NOT JUDGE, not one AWS confirmed
# current. So the detail says "not on this dated previous-generation or retired family list", exactly
# coextensive with the alternation. Three grounds put a node on the FAILING side:
#   1. the family is on the AWS bullets above (a1, m1-m4, t1, c1/c3/c4, r3/r4, i2, g3, p3/p3dn);
#   2. it is an earlier generation of a prefix those bullets name (g2, p2);
#   3. it is one of five retired families AWS no longer offers -- cc2, cr1, cg1, hi1, hs1.
# The passing side is "none of those three" and nothing stronger; do not read it as AWS listing the
# family as current.
# g2 and p2 are NOT current although the page does not name them: it lists G3/P3 as previous generation,
# AWS also drops fully retired families from it, and g2/p2 are older members of families whose successors
# are already retired. Inferring "current" from absence is a fail-open that puts a retired family in the
# passing numerator.
# m5, c5, r5, t2, i3, d2, h1, x1 and x1e pass on POSITIVE evidence: the same page's "Current generation
# instances" section names them. A family on NEITHER section (f1 today) counts as a pass; do not widen
# the pattern to cover it from memory.
# The generation ranges encode an ordering argument: within a prefix the bullets name, every generation at
# or below the newest previous-generation member is at least as old (`g[1-3]`, `c[1-4]`, `r[1-4]`, ...).
# Only g2 and p2 ever shipped among the generations the ranges add; cc2, cr1, cg1, hi1 and hs1 are spelled out
# because the ranges cannot reach them. `[a-z]*` sits AFTER the alternation and can only extend a match it
# already anchored.
# THE LIST IS A DATED SNAPSHOT OF AN AWS PAGE, NOT A FIXED FACT. Verified against
# https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html ("Previous generation
# instances") on 2026-09-12 and re-read 2026-09-25: the five bullets above are that section verbatim.
# The pattern `a1|m[1-4]|t1|c[1-4]|r[1-4]|i[1-2]|g[1-3]|p[1-3]|cc2|cr1|cg1|hi1|hs1` is DERIVED from them by
# grounds 2 and 3. A stale list does NOT fail safe: a family AWS adds later lands in the PASSING
# NUMERATOR and raises the band. Re-check that section (and
# https://docs.aws.amazon.com/ec2/latest/instancetypes/pg.html, which enumerates each family's types)
# before trusting the pattern on a later run, and re-date this stamp when you do.
# THE DENOMINATOR IS `//empty`, NOT "the label is a non-empty string": `//empty` drops a node only when
# the label is absent (or `false`), so a node labelled with the EMPTY STRING stays in `$t` and, matching
# no previous-generation family, counts on the passing side. `rl` binds `$t` the same way. DO NOT MIRROR
# THIS WITH Python's `or ""`: it drops the empty-string node and yields a list that contradicts the verdict.
# The `na~no instance types (serverless compute)` arm has empty `pass`/`fail` and the set-aside nodes in
# `context`; no `kind`.
# WINDOWS NODES ARE OUT (`islinux`, not `isec2`, on both lines); `winx` discloses them, `rl` names them in
# `context`, and if they are the only EC2 nodes the answer is `winna` (`na`), checked before the hybrid and
# serverless arms.
rl perf-3 nodes '[.items[]] as $all|def nn: (.metadata.labels//{}) as $l|(.metadata.name//"?")+" ("+([($l["node.kubernetes.io/instance-type"]//"?"),($l["topology.kubernetes.io/zone"]//"?")]|map(select(.!=""))|join(", "))+")";([$all[]|select(ishy)]|length) as $hy|[$all[]|select(iswin and isec2)|nn] as $wn|($wn|length) as $w|(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn else [] end) as $wcx|([$all[]|select(islinux)]|length) as $lxn|[$all[]|select(islinux)|(.metadata.labels["node.kubernetes.io/instance-type"]//empty) as $t|{t:$t,n:nn}] as $it|[$it[]|select(.t|test("^(a1|m[1-4]|t1|c[1-4]|r[1-4]|i[1-2]|g[1-3]|p[1-3]|cc2|cr1|cg1|hi1|hs1)[a-z]*\\."))] as $old|if ($lxn==0 and $w>0) then {pass:[],fail:[],context:$wcx,context_only:true} elif (($it|length)==0 and ($all|length)>0) then {pass:[],fail:[],context:($wcx+[(if $hy>0 then "no EC2 node carries a node.kubernetes.io/instance-type label; the \($hy) EKS Hybrid Node(s) below are not EC2 instances and have no instance type" else "no node carries a node.kubernetes.io/instance-type label, so there is no instance generation to judge — a Fargate node has no instance type" end)]+[$all[]|select(iswin and isec2|not)|nn])} else {pass:[($it-$old)[]|.n],fail:[$old[]|.n]}+(if $w>0 then {context:$wcx} else {} end) end'
m perf-3 nodes '([.items[]|select(ishy)]|length) as $hy|([.items[]|select(iswin and isec2)]|length) as $w|([.items[]|select(isec2)]|length) as $ec2n|[.items[]|select(islinux)|.metadata.labels["node.kubernetes.io/instance-type"]//empty] as $it|($it|length) as $t|([$it[]|select(test("^(a1|m[1-4]|t1|c[1-4]|r[1-4]|i[1-2]|g[1-3]|p[1-3]|cc2|cr1|cg1|hi1|hs1)[a-z]*\\."))]|length) as $old|($t-$old) as $ok| if ([.items[]]|length)==0 then "na~no nodes" elif ($ec2n==$w and $w>0) then winna($w)+hyx($hy) elif ($ec2n==0 and $hy>0) then hyna($hy;"instance generation is a property of an EC2 instance type: a hybrid node runs on hardware the operator owns and carries no node.kubernetes.io/instance-type label to read a generation from") elif $t==0 then "na~no instance types (serverless compute)"+winx($w) else b($ok;$t)+"~\($ok)/\($t) not on this dated previous-generation or retired family list"+hyx($hy)+winx($w) end'
# perf-4's `m` program is byte-identical to `rel-18`'s in references/reliability.md: the same Deployments
# and RollingUpdate test scored twice at two weights, because a rolling update is both a performance and a
# reliability property. Deliberate; do not "fix" it. The two `rl` programs are kept byte-identical too
# (the id apart), so CHANGING ONE MEANS CHANGING BOTH; this must print 1:
#     grep -h "^rl \(perf-4\|rel-18\) deployments " references/*.md | sed "s/^rl [a-z0-9-]* //" | sort -u | wc -l
# The excluded list carries the owner label each excluded Deployment declares (`own` on the `rl` line: four
# labels in fixed order, first set-and-matching wins, else a fallback sentence). A WEAK signal and says so:
# labels annotate the list and never decide who is excluded; the kube-*/amazon-* namespace-NAME prefix does
# (and, on both lines, a Windows pod spec). No count of excluded kube-*/amazon-* Deployments is quoted;
# `context` names them.
rl perf-4 deployments '[.items[]?] as $all|[$all[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m perf-4 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|([$d0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|($d|length) as $t|([$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) rolling"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# perf-5 distinguishes SPREADING from PINNING. Any `affinity` does NOT satisfy it: a nodeAffinity pinning
# every replica to one AZ or instance type must not score `all` on a placement question. Only
# topologySpreadConstraints and podAntiAffinity spread; nodeAffinity alone is reported as pinning.
# A topology spread constraint counts ONLY WITH a `labelSelector`. API reference: "An empty label selector
# matches all objects. A null label selector matches no objects." Without one it counts no Pods in any
# domain, and because the scheduler applies its default constraints only to a Pod that defines none, it
# also switches those defaults off. rel-9 (references/reliability.md) applies the same test.
# perf-5's pass set is rel-8's (podAntiAffinity) plus every Deployment with such a constraint on any key,
# a superset of rel-9's (zone-keyed only), so unlike perf-4/rel-18 these are not the same question.
# A podAntiAffinity counts ONLY WITH at least one term that selects pods (`paterm`, byte-identical to
# rel-8's): a `requiredDuringSchedulingIgnoredDuringExecution` entry, or the `podAffinityTerm` of a
# `preferred...` entry, carrying a `labelSelector` object. API reference: "If it's null, this
# PodAffinityTerm matches with no Pods". `podAntiAffinity: {}` (a Helm chart whose block templated out),
# `null`, `false`, empty term lists and a preferred entry with no `podAffinityTerm` do not count. Any
# `topologyKey` counts, hostname included. A `{}` podAntiAffinity beside a nodeAffinity is counted as
# pinned.
rl perf-5 deployments 'def paterm: (.spec.template.spec.affinity.podAntiAffinity) as $a|if ($a|type)=="object" then ([(($a.requiredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects]+[(($a.preferredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects|.podAffinityTerm|objects]|map(select((.labelSelector|type)=="object"))|length)>0 else false end;[.items[]?] as $all|[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|select(([((.spec.template.spec.topologySpreadConstraints|arrays)//[])[]|objects|select((.labelSelector|type)=="object")]|length)>0 or paterm)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m perf-5 deployments 'def paterm: (.spec.template.spec.affinity.podAntiAffinity) as $a|if ($a|type)=="object" then ([(($a.requiredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects]+[(($a.preferredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects|.podAffinityTerm|objects]|map(select((.labelSelector|type)=="object"))|length)>0 else false end;[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $d0|([$d0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|($d|length) as $t|([$d[]|select(([((.spec.template.spec.topologySpreadConstraints|arrays)//[])[]|objects|select((.labelSelector|type)=="object")]|length)>0 or paterm)]|length) as $spread|([$d[]|select(([((.spec.template.spec.topologySpreadConstraints|arrays)//[])[]|objects|select((.labelSelector|type)=="object")]|length)==0 and (paterm|not) and ((.spec.template.spec.affinity.nodeAffinity//null)!=null))]|length) as $pinned| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" elif $t==0 then "na~no workload Deployments" elif $pinned>0 and $spread==0 then "none~0/\($t) spread; \($pinned) deploy(s) use nodeAffinity only, which PINS placement rather than spreading it"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) else b($spread;$t)+"~\($spread)/\($t) deploys set a topologySpreadConstraint with a labelSelector, or podAntiAffinity, on any topologyKey, hostname included" + (if $pinned>0 then " (\($pinned) pinned by nodeAffinity only)" else "" end)+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# perf-6 asks about diversity ACROSS NODE GROUPS, and EKS Auto Mode has none. Banding the realized type
# count there would put a 3-node one-type Auto Mode cluster in the worst band and print "use multiple
# instance types across node groups", an instruction with no object on that platform: AWS picks each
# node's type from the NodePool requirements, and one type on a small cluster is healthy consolidation.
# "Relax the NodePool requirements" is not a valid fix either (the built-in general-purpose NodePool
# already permits C, M and R at generation 5+). The permitted set is the lever and is NOT collected
# (NodePools are not in assets/collect.sh; an EKS NodeClass carries no instance-type requirements), so the
# Auto Mode arm answers `na` with the reason: unanswered, not passed and not failed. Its text is
# deliberately not worded to match render-report.py's NA_STRUCTURAL pattern; `na_reason` files it as
# `unobserved`, which is what it is.
# SIBLING GATE of the other Auto Mode gates: the same all-nodes-auto test. Change one, change all; the census
# recipe is the ONE GATE note at ope-10 in references/operational-excellence.md. The cluster flag alone is not
# enough: on a mixed-mode cluster the managed node groups are real and the question applies to them. The `rl`
# line repeats the condition byte for byte, so this file holds two copies (here and in `m2`).
# EVIDENCE LIST: on the counting arm `pass` is the DISTINCT INSTANCE TYPES (not node names), `fail` is empty,
# and `context` states the banding; no `kind`, since the count is reported in prose, not `n/m`. The two `na`
# arms emit empty `pass`/`fail` with the reason and objects in `context`; they never claim anything PASSED.
# `//empty|select(.!="")` ON BOTH LINES, AND THE `select` IS NOT REDUNDANT: `//empty` drops `null` and
# `false` but NOT the empty string:
#   `[null,"",false,"m7i.large"] | [.[]|.//empty] | unique`  ->  ["","m7i.large"], length 2.
# Without the `select`, a node labelled `node.kubernetes.io/instance-type: ""` counts as a DISTINCT TYPE,
# can lift the band to a false Pass, and prints an empty string to the customer as an instance type.
# THE ASYMMETRY WITH perf-3 IS DELIBERATE, do not "fix" it: perf-3 counts NODES and keeps the
# empty-string node in its denominator; perf-6 counts TYPES, and "" is not a type.
# WINDOWS NODES ARE NOT IN THE POPULATION (Linux nodes only): `$ec2` is `islinux` (B) on both lines; `winx`
# discloses them and `rl` names them in `context`. When they are the only EC2 nodes the answer is `winna`
# (`na`, `rl` sets `context_only`), checked first. The gate deliberately carries no `$w==0` conjunct: it reads
# the Linux population, so a cluster whose only non-Auto nodes are Windows reaches the Auto Mode arm (`na`,
# never a Pass).
rl perf-6 nodes cluster 'input as $cl|([.items[]|select(ishy)]|length) as $hy|[.items[]] as $all|[$all[]|select(iswin and isec2)|.metadata.name//"?"] as $wn|($wn|length) as $w|(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn else [] end) as $wcx|[$all[]|select(islinux)] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|([$ec2[]|.metadata.labels["node.kubernetes.io/instance-type"]//empty|select(.!="")]|unique) as $types|if ($t==0 and $w>0) then {pass:[],fail:[],context:$wcx,context_only:true} elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then {pass:[],fail:[],context:(["computeConfig.enabled = true, and every "+(if $w>0 then "Linux " else "" end)+"EC2 node carries eks.amazonaws.com/compute-type=auto"]+$types+$wcx)} elif ($types|length)==0 then {pass:[],fail:[],context:($wcx+[(if ($all|length)==0 then "the cluster returned no nodes" elif $hy>0 then "no EC2 node carries a node.kubernetes.io/instance-type label; the \($hy) EKS Hybrid Node(s) below are not EC2 instances and have no instance type to diversify" else "no node carries a node.kubernetes.io/instance-type label — a Fargate node has none" end)]+[$all[]|select(iswin and isec2|not)|.metadata.name//"?"])} else {pass:$types,fail:[],context:(["\($t) EC2 node(s); 3 or more distinct types reads as Pass, 2 as Mostly, 1 as Partial"]+$wcx)} end'
m2 perf-6 nodes cluster 'input as $cl|[.items[]] as $all|([$all[]|select(iswin and isec2)]|length) as $w|[$all[]|select(islinux)] as $ec2|([$all[]|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|([$ec2[]|.metadata.labels["node.kubernetes.io/instance-type"]//empty|select(.!="")]|unique|length) as $d| if ($t==0 and $w>0) then winna($w)+hyx($hy) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "na~EKS Auto Mode has no node groups to diversify: AWS selects the instance type of every node from the permitted set in the NodePool requirements, so the \($d) distinct type(s) now running across \($t) Auto Mode node(s) is a placement AWS made and not a setting the operator chose. The permitted set is the only lever here, it lives in the NodePool spec (kubectl get nodepools -o yaml), and this review does not collect it — so this question is unanswered on Auto Mode rather than failed"+hyx($hy)+winx($w) elif ($all|length)==0 then "na~no nodes" elif ($t==0 and $hy>0) then hyna($hy;"instance-type diversification is an EC2 lever: a hybrid node is a machine the operator already owns, it carries no node.kubernetes.io/instance-type label, and there is no instance type to spread risk across") elif $d==0 then "na~no instance types (serverless compute)"+winx($w) elif $d>=3 then "all~\($d) types"+hyx($hy)+winx($w) elif $d==2 then "most~2 types"+hyx($hy)+winx($w) else "some~1 type"+hyx($hy)+winx($w) end'
g perf-7
# lens-5 EXCLUDES TERMINATED PODS on both lines with the same predicate, spelled identically, as perf-1
# (see there for why, for the `//""` safety note and for the byte-identity count recipe).
# WINDOWS PODS ARE OUT OF THE DENOMINATOR on both lines (`iswinpod`, B), after the namespace and phase
# filters; `winpx` discloses the count, `rl` names them in `context`, and if they are the only workload
# pods the answer is `winpna` (`na`) rather than `b()`'s bare `na~0/0`.
rl lens-5 pods daemonsets '(input|winds) as $wds|[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $all|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");[$all[]|select(iswinpod($wds))|n] as $wpn|($wpn|length) as $wp|(if $wp>0 then ["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wpn else [] end) as $cx|[$all[]|select(iswinpod($wds)|not)] as $w|[$w[]|select(.metadata.labels["app.kubernetes.io/name"])] as $p|if ($w|length)==0 and $wp>0 then {pass:[],fail:[],context:$cx,context_only:true} else {pass:[$p[]|n],fail:[($w-$p)[]|n]}+(if $wp>0 then {context:$cx} else {} end) end'
m2 lens-5 pods daemonsets '(input|winds) as $wds|[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $all|([$all[]|select(iswinpod($wds))]|length) as $wp|[$all[]|select(iswinpod($wds)|not)] as $p|($p|length) as $t|([$p[]|select(.metadata.labels["app.kubernetes.io/name"])]|length) as $ok| if $t==0 and $wp>0 then winpna($wp) else b($ok;$t)+"~\($ok)/\($t) std labels"+winpx($wp) end'
# lens-6 -- the pass set must EXCLUDE Amazon Linux 2. A bare `test("Bottlerocket|Amazon Linux")` matches
# "Amazon Linux 2" and would score it `all`, full marks for an AMI family that reached end of support on
# 2025-11-26 (last Kubernetes version 1.32) and gets no security patches. `Amazon Linux 20[0-9][0-9]`
# accepts AL2023 and any future year-numbered release, rejects bare "Amazon Linux 2", and avoids a version
# list that goes stale. AL2 is called out in the detail because it is a security finding, not merely a
# non-pass. The question reads `nodes.json` alone, from each node's own `osImage`.
# FARGATE NODES ARE EXCLUDED, as in perf-3, perf-6, ope-15 and lens-1: AWS owns and patches the Fargate
# image and there is no `amiType` or EC2NodeClass to change, so the operator cannot act. A Fargate node's
# `osImage` is not in the pass set, so without the exclusion a Fargate-only cluster would score a hard
# `none~0/N supported EKS AMI`. A Fargate node reports `osImage: "Minimal"`; the EKS User Guide's
# `kubectl get nodes -o wide` example (getting-started-eksctl.html) shows `Amazon Linux 2` for
# `fargate-ip-...` nodes, which is a stale example: do not re-derive the exclusion from it. The AL2
# end-of-support date above concerns the EKS-optimized AL2 AMI for EC2 nodes, not the Fargate image. A
# synthetic Fargate node copied from an EC2 node inherits that node's `osImage`, so test against a real one.
# WINDOWS NODES ARE NOT IN THE POPULATION (Linux nodes only): both lines take `islinux` (B) as the
# denominator (not Fargate, not an EKS Hybrid Node, not Windows). `winx` discloses them on the graded arm;
# when they are the only nodes left the answer is `winna` (`na`, never `all`), checked before the hybrid
# and Fargate arms. `winna` opens with `NOT ASSESSED`, so render-report.py's `na_reason()` classifies it
# `unobserved` (NA_NOT_ASSESSED is tested before NA_STRUCTURAL).
# Windows and Fargate nodes are DISCLOSED in `context`, not dropped (a partial pass listing only passing nodes
# reads as a whole-fleet pass); NOT `excluded`, a bare count for objects whose identifiers must not be
# published. The hybrid, Fargate and Windows-only `na` arms emit empty `pass`/`fail`; the Windows-only arm
# sets `context_only`. No `kind`: the counting arm's detail leads with `\($ok)/\($t)`, which `resource_agreement()` checks.
rl lens-6 nodes '[.items[]] as $all|([$all[]|select(ishy)]|length) as $hy|def fgn: (.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate";def okn: (.status.nodeInfo.osImage//"")|test("Bottlerocket|Amazon Linux 20[0-9][0-9]");def nn: (.metadata.labels//{}) as $l|(.metadata.name//"?")+" ("+([($l["node.kubernetes.io/instance-type"]//"?"),($l["topology.kubernetes.io/zone"]//"?"),(.status.nodeInfo.osImage//"?")]|map(select(.!=""))|join(", "))+")";[$all[]|select(fgn)] as $fg|[$all[]|select(iswin and isec2)] as $wall|($wall|length) as $w|[$all[]|select(islinux)] as $den|if (($den|length)==0 and ($all|length)>0) then (if $w>0 then {pass:[],fail:[],context:(["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+[$wall[]|nn]+(if ($fg|length)>0 then ["\($fg|length) Fargate node(s) excluded: AWS owns the image there"] else [] end)),context_only:true} else {pass:[],fail:[],context:([(if $hy>0 then "\($hy) EKS Hybrid Node(s) and no EC2 node to assess: AWS publishes no EKS-optimized AMI for a hybrid node, so the AMI-family test does not describe one" else "all \($fg|length) node(s) run on Fargate compute, where AWS owns and patches the node image: there is no AMI family for the operator to select and nothing here to migrate" end)]+[$all[]|nn])} end) else ([$den[]|select(okn)] as $p|((if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+[$wall[]|nn] else [] end)+(if ($fg|length)>0 then ["\($fg|length) Fargate node(s) excluded: AWS owns the image there"] else [] end)) as $ctx|{pass:[$p[]|nn],fail:[($den-$p)[]|nn]}+(if ($ctx|length)>0 then {context:$ctx} else {} end)) end'
m lens-6 nodes '[.items[]] as $all|($all|length) as $n|([$all[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate")]|length) as $fg|[$all[]|select(isec2)] as $ec2|([$all[]|select(ishy)]|length) as $hy|([$ec2[]|select(iswin)]|length) as $w|[$all[]|select(islinux)] as $lx|([$lx[]|.status.nodeInfo.osImage//""]) as $os|([$os[]|select(test("Bottlerocket|Amazon Linux 20[0-9][0-9]"))]|length) as $ok|([$os[]|select(test("Amazon Linux") and (test("Amazon Linux 20[0-9][0-9]")|not))]|length) as $al2|($lx|length) as $t| if $n==0 then "na~no nodes" elif ($t==0 and $w>0) then winna($w)+hyx($hy) elif (($ec2|length)==0 and $hy>0) then hyna($hy;"AWS publishes no EKS-optimized AMI for a hybrid node: the operator installs and patches the node operating system themselves, and Bottlerocket, Amazon Linux 2023, Ubuntu and RHEL are all validated for hybrid nodes, so the AMI-family test this question applies to EC2 nodes does not describe them") elif $t==0 then "na~all \($fg) node(s) run on Fargate compute, where AWS owns and patches the node image: there is no AMI family for the operator to select and nothing here to migrate" else b($ok;$t)+"~\($ok)/\($t) supported EKS AMI"+(if $al2>0 then ", \($al2) on Amazon Linux 2 (end of support 2025-11-26 — no security patches)" else "" end)+winx($w)+(if $fg>0 then " (\($fg) Fargate node(s) excluded: AWS owns the image there)" else "" end)+hyx($hy) end'
# lens-8 EXCLUDES TERMINATED PODS with the same predicate as perf-1 and lens-5 (a `dnsConfig` cannot be
# changed on an exited pod), and Windows pods (`iswinpod`, B; `winpx`, `winpna` as in perf-1).
m2 lens-8 pods daemonsets '(input|winds) as $wds|[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $all|([$all[]|select(iswinpod($wds))]|length) as $wp|[$all[]|select(iswinpod($wds)|not)] as $p|($p|length) as $t|([$p[]|select([.spec.dnsConfig.options[]?|select(.name=="ndots" and ((.value|tonumber?)//9)<=2)]|length>0)]|length) as $ok| if $t==0 and $wp>0 then winpna($wp) else b($ok;$t)+"~\($ok)/\($t) ndots<=2"+winpx($wp) end'
# lens-9 credits `aws-load-balancer-nlb-target-type: ip` as well as `externalTrafficPolicy: Local`: both
# avoid the extra kube-proxy hop (IP mode sends traffic straight to the pod), so failing an IP-mode NLB for
# a flag irrelevant to its path would be a false finding.
# The target type is `nlbtt`: the annotation when set (an explicit `instance` is never credited), else `ip`
# for `spec.loadBalancerClass: eks.amazonaws.com/nlb` (EKS Auto Mode NLB: "default targeting mode is IP
# Mode, not Instance Mode", EKS User Guide, auto-networking), else empty, which is not credited: the AWS
# Load Balancer Controller's own default is `instance`.
# `[.items[]` AND NOT `[.items[]?`: a `?` would swallow the iteration error on `services.json` =
# `{"items":null}` or `{}` and emit `na~no LoadBalancer services`, a confident "none" about a file it could
# not read, instead of the `m` helper's abort ("a missing or malformed collection file is NOT a finding").
# The refusal must not depend on a neighbour question aborting. It does not over-refuse: a cluster with
# zero Services collects `{"items":[]}`, which reaches the honest `na` arm.
m lens-9 services 'def nlbtt: ((.metadata.annotations//{})["service.beta.kubernetes.io/aws-load-balancer-nlb-target-type"] // (if (.spec.loadBalancerClass//"")=="eks.amazonaws.com/nlb" then "ip" else "" end));[.items[]|select(.spec.type=="LoadBalancer")] as $lb|($lb|length) as $t|([$lb[]|select(nlbtt=="ip")]|length) as $iptarget|([$lb[]|select(.spec.externalTrafficPolicy=="Local" or nlbtt=="ip")]|length) as $ok| if $t==0 then "na~no LoadBalancer services" else b($ok;$t)+"~\($ok)/\($t) avoid the extra hop" + (if $iptarget>0 then " (\($iptarget) via IP-mode targets, where externalTrafficPolicy is moot)" else "" end) end'
# lens-10 SCOPES ITS DENOMINATOR like every other counting question here, rather than counting every
# Service. Three kinds of Service cannot satisfy it, so counting them would make a fully configured
# cluster report a Partial:
#   - `kube-*`/`amazon-*` namespaces -- the pillar-wide operator-scope filter, same test as perf-1/perf-4;
#   - HEADLESS (`clusterIP: None`) or `type: ExternalName` (a DNS alias, even with a selector) -- kube-proxy
#     is not in the path, so `topology-mode` hints are not consulted;
#   - SELECTOR-LESS (`default/kubernetes`, hand-managed endpoints) -- the EndpointSlice controller does not
#     manage their slices, so nothing writes `hints.forZones`.
# `[.items[]` AND NOT `[.items[]?`, DELIBERATELY: on `services.json` = `{"items":null}` the `?` turns a
# refusal (`SCORER ABORT [lens-10]: ...`) into a published `na "0/0 topo routing"`, and because `na` drops
# the question from the applicable pool a malformed input could RAISE the score. It buys nothing on any
# real shape. Do not add it.
m lens-10 services '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|select((.spec.type//"")!="ExternalName" and (.spec.clusterIP//"")!="None")|select(.spec.selector!=null)] as $s|($s|length) as $t|([$s[]|select((.metadata.annotations["service.kubernetes.io/topology-aware-hints"] // .metadata.annotations["service.kubernetes.io/topology-mode"] // "")|IN("Auto","auto"))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) topo routing"'
```

**Governance (not assessed):** perf-7 (node utilization — needs live metrics not in the
snapshot).

---

## Workload sizing, scheduling and rollout

<!-- These five questions are not filed under "Monitoring" because not one of them measures
     monitoring: they are container resource requests, VPA, instance-type selection, the Deployment update
     strategy and pod anti-affinity/topology spread. An operator scanning the headings for the metrics or
     dashboard questions would find none here, and this pillar has none -- monitoring is graded in Operational
     Excellence (`ope-5`, `ope-7`, `ope-10`) and Reliability (`rel-13`). Nothing parses these `##` lines
     (the renderer keys on `### <id>: <title>` only), so the heading's only job is to tell a reader what
     is under it. -->

### perf-1: Do containers have CPU and memory requests set for accurate scheduling?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource requests enable the scheduler to place pods on nodes with sufficient capacity.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].resources.requests for cpu and memory
# Skip pods in status.phase Succeeded or Failed -- an exited pod's requests cannot be changed
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set CPU and memory requests on all containers based on actual usage. Use VPA recommendations: `kubectl get vpa -A -o jsonpath="{.items[*].status.recommendation}"` as a guide.

---

### perf-2: Is Vertical Pod Autoscaler (VPA) deployed for right-sizing resource requests?

**Detection:** 🔬 AUTO-DETECTABLE

> VPA recommends or automatically adjusts resource requests based on actual usage.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for vertical-pod-autoscaler deployment
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy VPA in recommendation mode to right-size resource requests without auto-applying changes.

---

### perf-3: Are appropriate EC2 instance types selected for the workload requirements?

**Detection:** 🔬 AUTO-DETECTABLE

> Instance type selection impacts performance, cost, and workload compatibility.
> **What the count means:** the passing side is the nodes whose instance family is **not on** a list of previous-generation and fully retired families, built from AWS's own published previous-generation page as it read on 2026-09-12 (re-read unchanged 2026-09-25) — which is weaker than AWS confirming the family is current. A family the list does not name is counted as a pass and raises the score even though nothing tested it, so read a pass here as "nothing this list knows about was found", not as "every node is current-generation". For `x1`, `x1e`, `d2` and `h1` that pass is right: the same AWS page lists them as current generation. A family on neither of that page's two lists (`f1` as of 2026-09-25) is the known case it cannot decide.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node: instance generation is a property of an EC2 instance type, and a hybrid node runs on hardware the operator owns and carries no `node.kubernetes.io/instance-type` label to read one from.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get nodes -o json
# Check node.kubernetes.io/instance-type labels for type diversity
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- **This question counts previous-generation families against a dated snapshot of an AWS page, not
  against a fixed fact.** The list and its verification stamp live in the scorer comment above the
  `perf-3` line; it was verified against
  [Previous generation instances](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html)
  on **2026-09-12**, re-read unchanged on **2026-09-25**, and needs re-checking there before it is trusted on a later run.
- **The test is a denylist, so it is one-sided and the emitted `detail` says only what it tested** —
  `n/m not on this dated previous-generation or retired family list`. It does **not** say
  "current-generation". Three grounds put a node on the failing side: the family is on AWS's dated
  previous-generation bullets; or it is an **earlier generation** of a prefix those bullets name (`g2`,
  `p2` — the bullets name `g3` and `p3`, and a lower generation of the same family cannot be current
  while its successor is already retired); or it is one of five **fully retired** families AWS no longer
  offers (`cc2`, `cr1`, `cg1`, `hi1`, `hs1`). The generation ranges — `c[1-4]`, `r[1-4]`, `i[1-2]`,
  `g[1-3]`, `p[1-3]` — carry only that ordering fact, so they assert nothing the snapshot does not
  already say.
- **A pass here is not a clean bill of health, and a stale list does not fail safe.** A family named
  nowhere in the three grounds above is **counted in the passing numerator and raises the band** — it is
  not set aside. For `x1`, `x1e`, `d2` and `h1` that is right: the same AWS page's "Current generation
  instances" section names them (re-read 2026-09-25), so a fleet of them scoring `all` is correct.
  The known case is a family on **neither** of that page's two lists — `f1` today (`F2` is listed current,
  `F1` is not) — which no AWS page read here classifies, and this list does not classify it either. Read a pass as "nothing this list knows about was
  found", and re-date the snapshot before relying on it.

**Remediation:** Review instance types for workload fit. Use Graviton (m7g, c7g) for better price-performance. Match instance family to workload profile (compute, memory, general).

**Not applicable to an EKS Hybrid Node** — it has no EC2 instance type, so there is no generation to move.

---

### perf-4: Do deployments use RollingUpdate strategy for zero-downtime updates?

**Detection:** 🔬 AUTO-DETECTABLE

> Rolling updates maintain performance during deployments by keeping pods available.

**Remediation:** Set `strategy.type: RollingUpdate` on all Deployments with appropriate `maxUnavailable` and `maxSurge` values for zero-downtime updates.

---

### perf-5: Are pod anti-affinity or topology spread constraints configured?

**Detection:** 🔬 AUTO-DETECTABLE

> Scheduling constraints optimize pod placement for performance and availability. A `podAntiAffinity`
> counts only when it holds at least one required or preferred term with a `labelSelector`, on any
> `topologyKey`; an empty `podAntiAffinity: {}`, empty term lists, or a term without a `labelSelector`
> spread nothing and do not count.

**Remediation:** Configure pod anti-affinity and/or topology spread constraints to spread pod placement across nodes and zones; give each topology spread constraint and each pod anti-affinity term a `labelSelector` that matches the workload's own Pods, since one without a `labelSelector` matches no Pods and spreads nothing. Pod affinity alone co-locates pods rather than spreading them, so it does not count here.

---

## Resource Optimization

### perf-6: Is there diversity in EC2 instance types across node groups?

**Detection:** 🔬 AUTO-DETECTABLE

> Instance type diversity reduces Spot interruption risk and improves bin-packing.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node: instance-type diversification is an EC2 lever, and a hybrid node is a machine the operator already owns with no instance type to spread risk across.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**On EKS Auto Mode this question is `na`, and the remediation below must not be quoted there.** Auto
Mode has no node groups, so "use multiple instance types across node groups" names something the
cluster does not have. AWS selects each node's instance type itself, from the permitted set in the
NodePool `requirements`, and on a small cluster settling on a single type is normal consolidation
rather than a diversity defect — banding on the running type count would put a 3-node Auto Mode cluster
running one type in the worst band and tell it to change a construct it does not have. **Do not tell an Auto Mode operator to
"relax the NodePool requirements" either**: the built-in NodePools already permit the C, M and R
families at generation 5 and newer, so on a cluster like that there is nothing to relax and the
instruction is just as unfollowable. The only actionable lever is the permitted set, and
this review does not collect NodePools (`assets/collect.sh` collects `nodeclasses.json`; an EKS
NodeClass carries subnets, security groups, ephemeral storage and network policy, no instance-type
requirements). So the scorer answers `na` and says why. To answer it yourself, read the permitted set
and widen it only if it is genuinely narrow:

```bash
kubectl get nodepools -o yaml   # spec.template.spec.requirements: the families/generations AWS may pick from
```

**Remediation:** **EC2 node groups and self-managed/Karpenter fleets only — on EKS Auto Mode this
question is `na` and none of the following applies, per the note above.** Use multiple instance types
across node groups to improve bin-packing and reduce Spot interruption risk. Mix instance families
of one architecture (m5, m6i, m7i are all x86_64; m7g is arm64 and belongs in an arm64 group, for
images built for arm64). On Karpenter, widen the `NodePool` `requirements` rather than adding node groups.

**Not applicable to an EKS Hybrid Node** — there is no instance type to diversify. Spread hybrid capacity across your own failure domains instead (`rel-1`).

---

## Node resource utilization

<!-- `perf-7` is not filed under "Network Performance". It is a CPU-and-memory question and
     measures nothing about the network; the network-performance questions in this pillar are `lens-8`
     (CoreDNS ndots), `lens-9` (externalTrafficPolicy) and `lens-10` (topology-aware routing), and they sit
     under "EKS Best Practices" below. Nothing parses these `##` lines; the heading's only job is to tell
     a reader what is under it. -->

### perf-7: Are node CPU and memory resources being utilized efficiently (requests vs capacity)?

**Detection:** ✋ ASK USER

> Low utilization indicates over-provisioning; high utilization risks resource contention.

**Remediation:** Right-size nodes based on actual utilization. Target 60-80% CPU and memory utilization. Use Karpenter for automatic instance type selection.

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-5: Do pods use Kubernetes standard labels (app.kubernetes.io/name)?

**Detection:** 🔬 AUTO-DETECTABLE

> Standard labels enable consistent service discovery and monitoring.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check for app.kubernetes.io/name label
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add Kubernetes standard labels to all pods: `app.kubernetes.io/name`, `app.kubernetes.io/version`, `app.kubernetes.io/component`.

---

### lens-6: Do nodes use a SUPPORTED EKS-optimized AMI (Amazon Linux 2023 or Bottlerocket)?

**Detection:** 🔬 AUTO-DETECTABLE

> EKS-optimized AMIs are tuned for Kubernetes performance and security — but only while AWS still
> publishes them. An AMI family past end of support is a security finding, not a performance one.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. AWS publishes no EKS-optimized AMI for one: the operator installs and patches the node operating system, and Bottlerocket, Amazon Linux 2023, Ubuntu and RHEL are all validated for hybrid nodes, so the AMI-family test this question applies to EC2 nodes does not describe them.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get nodes -o json
# status.nodeInfo.osImage — "Bottlerocket OS ..." / "Amazon Linux 2023..." pass; "Amazon Linux 2" does NOT
```

**Amazon Linux 2 is NOT a pass.** AWS *"ended support for Amazon EKS optimized Amazon Linux 2 AMIs on
November 26, 2025"*; Kubernetes **1.32 was the last version** for which EKS released them, and they
*"no longer receive software updates, security patches, or bug fixes from AWS"*. They are also
unavailable on 1.33+. A bare substring match on `Amazon Linux` would be satisfied by "Amazon
Linux 2", so a fleet of unpatched AL2 nodes would score `all` — rewarding an end-of-life OS; this
question accepts Amazon Linux only as `Amazon Linux 20xx`. Read that as: if you see AL2, it is the finding, and it outranks anything
else in this pillar.

**Analysis:** percentage of Linux EC2 nodes on an AMI AWS still publishes:
- ≥90% → `all` · ≥70% → `most` · >0% → `some` · 0% → `none` · no nodes → `na`
- Linux pass set: `Bottlerocket OS *`, `Amazon Linux 20xx` (AL2023 and later), read from
  `status.nodeInfo.osImage`. The year match deliberately avoids a hard-coded version list that goes
  stale the next time AWS ships a release.
- The detail names the AL2 node count separately, because an unsupported node OS is materially
  different from Ubuntu or a deliberate custom AMI.
- **Windows nodes are excluded from the denominator, and the exclusion is stated in the detail.** This
  skill supports Linux nodes only: a Windows node is named in the evidence list as not assessed and
  counted in the detail, and a cluster whose only EC2 nodes are Windows answers `na`, never
  `all`.
- **Fargate nodes are excluded from the denominator, and an all-Fargate cluster is `na`.** AWS owns and
  patches the Fargate node image; there is no `amiType` and no `EC2NodeClass` to point at a different
  family, so nothing in the remediation below can be carried out. Without the exclusion a
  Fargate-only cluster would score a hard `none — 0/N supported EKS AMI` on a platform where there is
  nothing to migrate. **A live Fargate node's `osImage` is `Minimal`** (measured 2026-09-12 on a
  Fargate-backed cluster). The EKS User Guide's own `kubectl get nodes -o wide` example
  shows `OS-IMAGE` = `Amazon Linux 2` for every `fargate-ip-…` node
  ([Get started with Amazon EKS – eksctl](https://docs.aws.amazon.com/eks/latest/userguide/getting-started-eksctl.html));
  that is a stale doc example, not the string a Fargate node reports today; check your own with
  `kubectl get nodes -o wide`. Either way the node is excluded — but do not re-derive the
  exclusion from the AL2 string, and **the AL2 end-of-support date above is about the EKS-optimized AL2
  AMI for EC2 nodes, not about the platform image AWS runs Fargate pods on.**

**Remediation:** **EC2 nodes only — do not quote any of this to a Fargate or Auto Mode operator.** On
Fargate there is no worker node to move and no AMI to select (it scores `na`, and the reason the scorer
prints is the whole finding there); an Auto Mode node runs AWS's own Bottlerocket variant and passes. For EC2 nodes:
move worker nodes to **Bottlerocket** (minimal, image-based, and the lowest-effort option under
Karpenter) or **Amazon Linux 2023**. Both are current EKS-optimized families.
- Managed node groups: set `amiType` to `BOTTLEROCKET_x86_64` / `BOTTLEROCKET_ARM_64` or
  `AL2023_x86_64_STANDARD` / `AL2023_ARM_64_STANDARD`, then roll the group.
- Karpenter v1 (`karpenter.k8s.aws/v1` EC2NodeClass): replace `amiSelectorTerms` with the single term
  `- alias: al2023@latest` or `- alias: bottlerocket@latest`, then drop `amiFamily` or set it to the same
  family. `amiFamily` alone "does not impact which AMI is discovered, only the UserData generation" — the AL2
  image stays selected. Pin a tested release tag (`al2023@vYYYYMMDD`, `bottlerocket@v1.20.4`) for production:
  `@latest` drifts every node on each new AMI ([karpenter.sh NodeClasses](https://karpenter.sh/docs/concepts/nodeclasses/)). `AL2` is deprecated.
- AL2 → AL2023 is **not** a drop-in swap: AL2023 bootstraps with `nodeadm` and a YAML config schema
    instead of `/etc/eks/bootstrap.sh`, requires VPC CNI ≥ 1.16.2, and enforces IMDSv2. Both AL2023 and
    Bottlerocket EKS-optimized AMIs carry the `imds-support: v2.0` AMI attribute (`aws ec2
    describe-images`, verified live 2026-09-11), which on its own launches instances at `HttpTokens:
    required` and `HttpPutResponseHopLimit: 2` — one hop further than the plain EC2 default of 1, and
    enough for a pod off the host network to still reach IMDS. **Karpenter is not the permissive path
    here.** Its `EC2NodeClass` explicitly defaults `httpPutResponseHopLimit` back down to **1**, to block
    IMDS access from containers not on the host network (karpenter.sh NodeClasses reference, verified
    live 2026-09-11) — so an AL2 → AL2023 move under Karpenter does not loosen the hop limit unless the
    operator's `EC2NodeClass` overrides that default. **A managed node group is the case that actually
    needs checking.** AWS documents AL2023 managed node groups as defaulting to hop 1 with no launch
    template and hop 2 once a launch template names a custom AMI (EKS User Guide, "Upgrade from Amazon
    Linux 2 to Amazon Linux 2023," verified live 2026-09-11) — but that split does not hold uniformly
    across AMI families: verified live against a Bottlerocket-based managed node group on one real
    cluster, which has **no** user-specified launch
    template, yet the launch template EKS generated for it carries `HttpPutResponseHopLimit: 2`, and
    every resulting instance reports `HttpTokens: required`, hop 2. Don't infer the hop limit from AMI
    family or provisioning mechanism — read `MetadataOptions.HttpPutResponseHopLimit` off the actual
    instances. Say this in the report; a migration presented as trivial will fail.
- EKS Auto Mode manages the node OS itself, so this question is not an action item there.
- AWS Fargate is not an action item either, for a stronger reason: AWS owns the node image outright, so
  neither `amiType` nor an `EC2NodeClass` exists to change. Report the platform, not a migration.

**Not applicable to an EKS Hybrid Node** — there is no EKS-optimized AMI for one. Patch the node OS you installed (Bottlerocket, AL2023, Ubuntu or RHEL are the validated choices) on your own cadence.

---

### lens-8: Do pods override CoreDNS ndots to ≤2 for faster DNS resolution?

**Detection:** 🔬 AUTO-DETECTABLE

> Default ndots=5 causes unnecessary DNS lookups for external domains.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.dnsConfig.options for ndots <= 2
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Override CoreDNS ndots in pod specs: add `dnsConfig.options: [{name: ndots, value: "2"}]` to reduce unnecessary DNS search domain lookups.

---

### lens-9: Do LoadBalancer services use externalTrafficPolicy: Local?

**Detection:** 🔬 AUTO-DETECTABLE

> Local policy preserves client IPs and avoids extra network hops.

**Commands:**
```bash
kubectl get services -A -o json
# Check LoadBalancer services for externalTrafficPolicy: Local
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `externalTrafficPolicy: Local` on LoadBalancer services to preserve client IPs and
avoid extra network hops across nodes. **This question credits either of two paths** — a service fronted
by an AWS Load Balancer Controller NLB in IP-target mode
(`service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip`) already routes straight to the pod
IP, so it satisfies this check with no traffic-policy change. An EKS Auto Mode NLB
(`spec.loadBalancerClass: eks.amazonaws.com/nlb`) defaults to IP targets, so it is credited without the
annotation unless the annotation sets another target type. Prefer that path where you already run the controller:
`externalTrafficPolicy: Local` also drops traffic on nodes carrying no local endpoint, and skews load
distribution toward nodes running more replicas.

---

### lens-10: Are services configured with topology-aware routing?

**Detection:** 🔬 AUTO-DETECTABLE

> Topology routing keeps traffic in-zone to reduce latency and cross-AZ costs.

**Commands:**
```bash
kubectl get services -A -o json
# Check annotation service.kubernetes.io/topology-aware-hints (deprecated; takes precedence whenever present),
# else service.kubernetes.io/topology-mode; routing is enabled only by the value Auto/auto
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable topology-aware routing: add annotation `service.kubernetes.io/topology-mode: Auto` to services for in-zone traffic routing, and remove any deprecated `service.kubernetes.io/topology-aware-hints` annotation, which takes precedence over `topology-mode` whenever it is present, whatever its value. **The count covers the services this annotation can act on** — those in your own namespaces (not `kube-*`/`amazon-*`) that have a cluster IP and a pod selector. A headless service (`clusterIP: None`) bypasses kube-proxy entirely and a selector-less service has no controller-managed EndpointSlices, so neither can be routed by topology and neither is counted against you.

---
