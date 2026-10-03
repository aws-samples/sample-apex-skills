---
title: "🛡️ Reliability"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/reliability.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/reliability.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/reliability.md). Edit the source, not this page.
:::

# 🛡️ Reliability

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**28 questions** — Multi-AZ, autoscaling, resource limits, HPA, probes, PDBs, anti-affinity, topology spread, rolling updates, backups

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` (Not
Assessed). The per-question sections below give rationale and remediation.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** They agree today — every `🔬 AUTO-DETECTABLE` section is emitted
> `measured` and every `✋ ASK USER` section is emitted `governance` — and if an edit ever makes them
> disagree, the SCORER IS AUTHORITATIVE: answer the question from the collected data. Use the prose
> for rationale and remediation wording only.

---

## Reliability scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh reliability "$WORK"` extracts this block and runs it. Do not paste it
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
# Shape guard applied by `rl` to every program: the result must be an object with `pass` and `fail` arrays
# of STRINGS plus optional `context` (array of strings), `kind` (field|existence), `excluded` (non-negative
# integer) and `context_only` (boolean). Anything else is recorded as a failure, not written
# to results.jsonl; `{pass,fail}` rebuilds the object so extra keys cannot be smuggled through.
RQ='|if (type=="object") and ((.pass|type)=="array") and ((.fail|type)=="array") and (((.context//[])|type)=="array") and (([(.pass+.fail+(.context//[]))[]|select(type!="string")]|length)==0) and ((.kind==null) or (.kind=="field") or (.kind=="existence")) and ((.excluded==null) or (((.excluded|type)=="number") and (.excluded>=0) and ((.excluded|floor)==.excluded))) and ((.context_only==null) or ((.context_only|type)=="boolean")) then {pass,fail}+(if (.context|type)=="array" then {context} else {} end)+(if .kind!=null then {kind} else {} end)+(if .excluded!=null then {excluded} else {} end)+(if .context_only==true then {context_only:true} else {} end) else error("rl: the program did not return {pass:[string],fail:[string]} with optional context:[string], kind:field|existence, excluded:integer, context_only:boolean") end'
# BUILD THE RECORD WITH jq, NOT printf: `detail` carries cluster-controlled strings, and with printf a `"`
# would forge a duplicate `state` key and a newline would forge whole records in OTHER pillars. `--arg` escapes.
# TWO DETAILS ARE LOAD-BEARING:
#   -c   results.jsonl must stay JSONL (reduce.sh refuses otherwise), and score.sh's already-scored check
#        greps the literal `"pillar":"reliability"`, which only compact output reproduces.
#   ||   this block runs under `bash` with NO `set -e`; guarded, one failing record aborts rc=1 and names the
#        question, unguarded it leaves rc=0 with a record missing.
# Key order pillar,id,track,state,detail is documented in SKILL.md Step 5; `resources` is a SIXTH key,
# appended only for questions that ran `rl`.
# `--argjson` can fail on SIZE only: the list is ONE argv entry, so a huge fleet can exceed ARG_MAX (or the
# 128 KiB per-argument cap on Linux) and execve fails before jq starts. Malformed content cannot reach it: `rl`
# admits exactly one line of valid compact JSON. The abort message therefore names argument size.
# THE ID IS RE-ASSERTED: a stale evidence list from the previous question is dropped, never attached to this
# one. Five files carry this helper; if you change one, change all five.
emit(){ local rs=false
  if [ "${RESID:-}" = "$1" ]; then rs="${RES:-null}"; fi
  RES= RESID=
  jq -cn --arg id "$1" --arg tr "$2" --arg st "$3" --arg de "$4" --argjson rs "$rs" \
  '{pillar:"reliability",id:$id,track:$tr,state:$st,detail:$de}+(if $rs==false then {} else {resources:$rs} end)' >> "$W/results.jsonl" \
  || { printf 'SCORER ABORT [%s]: the record was not emitted -- the jq call failed, the OS refused to start it, or the append to results.jsonl failed; any message jq or the OS printed is above. On a large fleet suspect the evidence list rather than the record: the list reaches jq as ONE --argjson argument, so many thousand names can exceed the OS argument-size limit and execve fails with "Argument list too long" before jq runs.\n' "$1" >&2; exit 1; }; }
# rl <id> <collection-file>... '<jq program>'  -- NAME the objects the next `emit` counted, so the report
# prints `payments/api` rather than `7/9` (a correct count over the wrong set is the bug a bare count hides).
# The names come from jq, next to the verdict, so truthiness matches (jq `select(.x)` keeps `{}`, `[]`, `""`,
# `0`; Python's `bool()` rejects all four); render-report.py derives no names of its own. A question without
# an `rl` line publishes no list. Count the converted ones with
#     grep -h '^rl ' references/*.md references/*/*.md | wc -l
# (`-h` plus `wc -l`, not `grep -c`, which counts per file; two globs, not `**`: macOS bash 3.2 has no globstar.)
# It is a SEPARATE jq call because one SCORER ABORT costs the whole pillar its score. `rl` swallows its own
# failure and records `resources: null`; the `m` line then scores as usual. No `resources` key = no list
# published; `null` = the list could not be built; `[]` = the check looked and found nothing.
# The selection test appears in both `rl` and `m`; the report cross-checks the list against the ratio in
# `detail`. Write `fail` as the complement (`$all - $pass`) so the test appears once inside `rl`. `rl` emits
# unadorned arrays of strings; sorting, truncation and labels are the renderer's.
# The jq call's stderr goes to $RLERR, `rl.stderr` in the per-run `.eks-war-scorer.<pillar>.<pid>/` directory
# score.sh made, never a fixed name in $W (a planted entry is not written through); `2>` truncates it. The
# query is NOT re-run to recover the text (a second execution can fail differently). With RLERR unset stderr
# goes to /dev/null; `[ ! -f ] || [ ! -w ]` reports a capture failure instead of stale text.
rl(){ local id="$1"; shift; local fs=(); while [ "$#" -gt 1 ]; do fs+=("$W/$1.json"); shift; done; local r n q e= ef="${RLERR:-/dev/null}"; r=$(jq -c "$B $1 $RQ" "${fs[@]}" 2>"$ef"); q=$?; if [ "$q" = 0 ] && [ -n "$r" ] && n=$(printf '%s' "$r" | wc -l | tr -d ' ') && [ "$n" = 0 ]; then RES="$r" RESID="$id"; else RES=null RESID="$id"; if [ ! -f "$ef" ] || [ ! -w "$ef" ]; then e="jq's stderr could not be captured to $ef, so any OS message is on the line above"; else [ -s "$ef" ] && e=$(tr -s '[:space:]' ' ' < "$ef"); e="${e# }"; e="${e% }"; [ -n "$e" ] && e="; jq said: $e"; if [ "$q" != 0 ]; then e="jq exited $q$e"; elif [ -z "$r" ]; then e="jq exited 0 and produced no output at all$e"; else e="jq exited 0 but produced $((n+1)) results, and an evidence list is exactly one$e"; fi; fi; printf 'RESOURCE LIST SKIPPED [%s]: the evidence list could not be built -- %s. THE VERDICT IS UNAFFECTED -- this is not a finding and not a scoring error; the report will say that this step failed and that there is no list for this question.\n' "$id" "$e" >&2; fi; return 0; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Three inputs, for the questions below that need a third collection file.
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Four inputs, for `rel-4` and `lens-3` (rel-4 reads cluster.json for the EKS Auto Mode capability);
# `m5` is `m4` plus one input, for `lens-14` and `lens-15`. `m4` is identical in operational-excellence.md, cost-optimization.md
# and identity-access.md (which differs only by `$PE` in the jq call), `m5` in operational-excellence.md; change every copy.
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m5(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" f5="$6" p="$7" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" "$W/$f5.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# rel-1 ON A FARGATE-ONLY CLUSTER READS THE FARGATE PROFILE SUBNETS, NOT NODE ZONE LABELS. Fargate runs one
# Pod per node (docs.aws.amazon.com/eks/latest/best-practices/cost-opt-compute.html), so a node's zone label
# records where a Pod happened to land and the verdict would be a coin flip. The durable fact is the profile:
# docs.aws.amazon.com/eks/latest/userguide/fargate-profile.html -- "Amazon EKS and Fargate spread Pods across
# each of the subnets that is defined in the Fargate profile." Subnet-to-AZ comes from subnets.json. The arm
# fires ONLY when there are no EC2 nodes; otherwise EC2 nodes are the measurement, Fargate nodes excluded.
# If the profiles resolve to no AZ (no `subnets` in the profile detail, or ids not in subnets.json) this
# answers `na~NOT ASSESSED` and says which; it does NOT fall back to node labels, because a missing collection
# is not a finding. THAT DETAIL MUST NOT CONTAIN THE WORD "FARGATE": render-report.py's `NA_STRUCTURAL` regex
# (incl. `fargate|impossible|serverless compute|no EC2 nodes`) treats such an `na` as structural and subtracts it
# from the thin-evidence denominator, but this is a COLLECTION GAP and must keep counting against coverage.
# rel-1's `rl` NAMES AZs, NOT NODES, on the same two paths as the verdict. SUBNET IDS ARE NEVER EMITTED (they
# identify another tenant's network to anyone the report is forwarded to); unresolved ids are a COUNT in
# `context`, not `excluded`, because they were looked at and are a collection gap. ONE `pass_label` covers
# both arms because SCORER_LIST_UI holds text only.
# WINDOWS NODES ARE NOT ASSESSED (Linux nodes only). rel-1, rel-4, lens-2, lens-3 and lens-14 count nodes over
# B's `islinux`; lens-15 counts instances whose `.Platform` is not `windows`; rel-3 and rel-6 drop the pods
# `iswinpod` matches. Each states the Windows count in its detail, and each `rl` except lens-14's names the
# Windows nodes or pods in `context`, so a reduced population never reads as the whole fleet. The Windows-only
# `na` is answered only where nothing else can grade, and sits before any `na` whose reason (Fargate, hybrid,
# no nodes) would be false with Windows nodes present. Dropping Windows can remove a whole AZ (lens-14) or
# subnet (lens-15) and raise the band, so both details say how many left. lens-15 answers `na` when all
# instances are Windows, or nodes exist and none is `isec2`, rather than falling back to registered subnets:
# that stands in for missing data, and there the data exists (fargate-profile.html: private subnets only).
# rel-1 COUNTS A NODE'S ZONE ONLY WHERE THE SCHEDULER CAN PLACE A NEW WORKLOAD POD: Ready `True` and
# `spec.unschedulable` not true (`_rs`). The Ready test is copied from reduce.sh's `NODES_READY` so the two
# cannot disagree. The arms are still chosen on the whole population (all-NotReady EC2 nodes do not make a
# cluster Fargate-only or hybrid-only). lens-14 asks which AZs need egress, so a NotReady or cordoned node
# earns its AZ no credit but keeps its need: an AZ with only such nodes is left out when it is credited with
# NAT egress and stays in, failed, when it is not; when no other AZ is left, the count is taken over
# the AZs left out.
# The Deployment questions (rel-2, rel-5, rel-7, rel-8, rel-9, rel-18 here; perf-4, perf-5 in
# performance-efficiency.md) drop a Deployment whose pod template is Windows (`iswinspec`) from the `rl` list
# and the verdict, state the count in the detail, and answer `na` opening `NOT ASSESSED` when every
# Deployment they would judge is Windows. rel-19 to rel-22 use ope-7's `_lxds`, copied inline: `iswinspec` on
# `.spec.template.spec`, which also reads a required node affinity admitting Windows and no Linux node on
# `kubernetes.io/os`, `beta.kubernetes.io/os` or `node.kubernetes.io/windows-build`.
rl rel-1 nodes fargateprofiles subnets 'def _rs: ([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0) and ((.spec.unschedulable//false)!=true);def _why: [(if ([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0) then empty else "NotReady" end),(if (.spec.unschedulable//false)==true then "cordoned" else empty end)]|join(", ");input as $fp|input as $sn|[.items[]?] as $all|[$all[]|select(islinux)] as $ec2|[$ec2[]|select(_rs)] as $ec2r|[$ec2[]|select(_rs|not)] as $ec2x|(if ($ec2x|length)>0 then ["\($ec2x|length) Linux EC2 node(s) not counted as an AZ: NotReady or cordoned (spec.unschedulable), so the scheduler places no new workload Pod on them (DaemonSet Pods excepted)"]+[$ec2x[]|(.metadata.name//"?")+" ("+_why+", "+(.metadata.labels["topology.kubernetes.io/zone"]//"no zone label")+")"] else [] end) as $xctx|[$all[]|select(iswin and isec2)] as $wn|($wn|length) as $w|(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+[$wn[]|.metadata.name//"?"] else [] end) as $wctx|[$all[]|select(ishy)] as $hyn|($hyn|length) as $hy|[$hyn[]|select(_rs)] as $hyr|[$hyn[]|select(_rs|not)] as $hyxn|(if ($hyxn|length)>0 then ["\($hyxn|length) EKS Hybrid Node(s) not counted as a fault domain: NotReady or cordoned (spec.unschedulable), so the scheduler places no new workload Pod on them (DaemonSet Pods excepted)"]+[$hyxn[]|(.metadata.name//"?")+" ("+_why+", "+(.metadata.labels["topology.kubernetes.io/zone"]//"no zone label")+")"] else [] end) as $hyxctx|(($fp.profiles)//[]) as $profs|[$sn.Subnets[]?] as $subs|([$subs[]|.AvailabilityZone//"?"]|unique) as $vpcaz|([$profs[]?|(.subnets//[])[]]|unique) as $want|([$want[]|. as $id|$subs[]|select(.SubnetId==$id)|.AvailabilityZone//"?"]|unique) as $found|([$want[]|. as $id|select([$subs[]|select(.SubnetId==$id)]|length==0)]|length) as $missing|if (($ec2|length)==0 and ($profs|length)>0 and $hy==0) then {pass:$found,fail:[],context:(["\($profs|length) Fargate profile(s), naming \($want|length) distinct subnet(s)"]+(if $missing>0 then ["\($missing) of those subnet(s) are not in the collected VPC subnet data, so their AZ could not be resolved"] else [] end)+$wctx+$vpcaz)} elif (($ec2|length)==0 and $hy>0) then {pass:([$hyr[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique),fail:[],context:(["\($hy) EKS Hybrid Node(s) and no EC2 node: a hybrid node has no AWS Availability Zone, so any topology.kubernetes.io/zone on one is a fault domain the operator declared from the kubelet"]+(([$hyn[]|select((.metadata.labels["topology.kubernetes.io/zone"]//"")=="")]|length) as $hyu|if $hyu>0 then ["\($hyu) of those hybrid node(s) carry no topology.kubernetes.io/zone label and are not counted as a fault domain"] else [] end)+$hyxctx+$wctx+$vpcaz)} elif (($ec2|length)==0 and $w>0) then {pass:[],fail:[],context:($wctx+$vpcaz),context_only:true} else ([$ec2r[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique) as $zones|([$ec2r[]|select((.metadata.labels["topology.kubernetes.io/zone"]//"")=="")]|length) as $unlab|{pass:$zones,fail:[],context:((if $unlab>0 then ["\($unlab) EC2 node(s) carry no topology.kubernetes.io/zone label and are not counted as an AZ"] else [] end)+$xctx+$wctx+$vpcaz)} end'
m3 rel-1 nodes fargateprofiles subnets 'def _rs: ([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0) and ((.spec.unschedulable//false)!=true);input as $fp|input as $sn|[.items[]?] as $all|[$all[]|select(islinux)] as $ec2|[$ec2[]|select(_rs)] as $ec2r|(($ec2|length)-($ec2r|length)) as $x|(if $x>0 then " — \($x) of the \($ec2|length) Linux EC2 node(s) not counted: NotReady or cordoned (spec.unschedulable), so the scheduler places no new workload Pod on them (DaemonSet Pods excepted)" else "" end) as $xs|([$all[]|select(iswin and isec2)]|length) as $w|[$all[]|select(ishy)] as $hyn|($hyn|length) as $hy|[$hyn[]|select(_rs)] as $hyr|($hy-($hyr|length)) as $hyx|([$hyr[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique) as $hyz|([$hyr[]|select((.metadata.labels["topology.kubernetes.io/zone"]//"")!="")]|length) as $hyl|(if $hyx>0 then " — \($hyx) of the \($hy) hybrid node(s) not counted: NotReady or cordoned (spec.unschedulable), so the scheduler places no new workload Pod on them (DaemonSet Pods excepted)" else "" end) as $hyxs|([$hyn[]|select((.metadata.labels["topology.kubernetes.io/zone"]//"")=="")]|length) as $hyu|(if $hyu>0 then " — \($hyu) of the \($hy) hybrid node(s) carry no topology.kubernetes.io/zone label at all, so their fault domain is not declared and is not in that count" else "" end) as $hyus|(($fp.profiles)//[]) as $profs|([$profs[]?|(.subnets//[])[]]|unique) as $fpsub|([$sn.Subnets[]?|select(.SubnetId as $id|$fpsub|index($id))|.AvailabilityZone]|unique) as $fpaz|(if ($profs|length)>0 then " — \($profs|length) Fargate profile(s) reach \($fpaz|length) AZ(s), which is a separate population this verdict does not cover" else "" end) as $fpnote|([$ec2r[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique) as $ec2az| if (($ec2|length)==0 and ($profs|length)>0 and $hy==0) then ((if ($fpaz|length)>=3 then "all~\($fpaz|length) AZs across the subnets the \($profs|length) Fargate profile(s) launch Pods into" elif ($fpaz|length)==2 then "most~2 AZs across the subnets the \($profs|length) Fargate profile(s) launch Pods into" elif ($fpaz|length)==1 then "none~1 AZ across the subnets the \($profs|length) Fargate profile(s) launch Pods into" else "na~NOT ASSESSED: every worker node here is created per Pod, so its zone label records where one Pod happened to land rather than where the cluster is able to place Pods; the durable answer is the subnet list of the compute profiles, and \(if ($fpsub|length)==0 then "the collected profile detail carries none" else "none of the \($fpsub|length) subnet(s) it carries appears in the collected VPC subnet data" end) — collect the per-profile detail and re-run" end)+winx($w)) elif (($ec2|length)==0 and $hy>0) then ((if ($hyz|length)>=3 then "all~\($hyz|length) fault domains declared across \($hy) EKS Hybrid Node(s) by topology.kubernetes.io/zone"+$hyus+$hyxs+$fpnote elif ($hyz|length)==2 then "most~2 fault domains declared across \($hy) EKS Hybrid Node(s) by topology.kubernetes.io/zone"+$hyus+$hyxs+$fpnote elif ($hyz|length)==1 then "none~1 fault domain declared by topology.kubernetes.io/zone across \($hyl) of \($hy) EKS Hybrid Node(s), so those all share it"+$hyus+$hyxs+$fpnote elif $hyu<$hy then "none~0 fault domains declared by a Ready, schedulable EKS Hybrid Node: all \($hy - $hyu) of the \($hy) hybrid node(s) that carry a topology.kubernetes.io/zone label are NotReady or cordoned (spec.unschedulable), so the scheduler places no new workload Pod (DaemonSet Pods excepted) in any declared fault domain"+$hyus+$fpnote else "none~0 fault domains declared across \($hy) EKS Hybrid Node(s): an AWS Availability Zone is not something an on-premises node has, and not one hybrid node here carries a topology.kubernetes.io/zone label, so as far as the cluster can tell the whole fleet is a single failure domain. AWS documents setting the label from the kubelet (--node-labels=topology.kubernetes.io/zone=...) so that topology-aware scheduling and Pod topology spread constraints can spread Pods across the fault domains the operator controls — this is a gap to close, not a question that cannot apply"+$hyxs+$fpnote end)+winx($w)) elif (($ec2|length)==0 and $w>0) then winna($w) elif ($all|length)==0 then "na~no nodes" elif ($ec2az|length)>=3 then "all~\($ec2az|length) AZs"+$xs+hyx($hy)+winx($w) elif ($ec2az|length)==2 then "most~2 AZs"+$xs+hyx($hy)+winx($w) elif ($ec2az|length)>=1 then "none~1 AZ"+$xs+hyx($hy)+winx($w) else "none~0"+$xs+(if ($ec2r|length)==0 then $fpnote else "" end)+hyx($hy)+winx($w) end'
# rel-2 honours matchExpressions as well as matchLabels, ANDed: "All of the requirements, from both matchLabels
# and matchExpressions are ANDed together" (kubernetes.io, Labels and Selectors). All four operators are
# handled. A PRESENT-BUT-EMPTY SELECTOR (`{}`) IS THE BROADEST MATCH, covering every Deployment in the PDB's
# namespace -- policy/v1 PodDisruptionBudgetSpec.selector: "A null selector will match no pods, while an empty
# ({}) selector will select all pods within the namespace." A null or absent selector matches nothing.
# rel-2's `rl` REPRODUCES THE FULL SELECTOR TEST (matchLabels AND matchExpressions, all four operators): a
# list reading matchLabels only would name a matchExpressions-covered Deployment as uncovered beneath a
# verdict that counts it. Covered rows carry the name of the one PDB covering them (`  <- <pdb>`).
# A PDB COUNTS ONLY IF IT ALLOWS AT LEAST ONE VOLUNTARY DISRUPTION (`dis`). kubernetes.io, "Specifying a
# Disruption Budget": maxUnavailable 0/0%, or minAvailable 100%/the replica count, requires zero voluntary
# evictions, so `kubectl drain`, node-group upgrades and Karpenter consolidation never complete -- a blocker,
# not coverage. `np` is the replicas of every Deployment in the PDB's namespace that it selects; a percentage
# rounds up, as the disruption controller rounds it. A value that is neither a number nor `<digits>%` allows
# no eviction. A PDB WITH NEITHER FIELD IS NOT COUNTED (kubernetes/kubernetes pkg/controller/disruption/
# disruption.go sets `disruptionsAllowed` to 0). It must ALSO keep at least one pod: minAvailable 0/0%, or
# maxUnavailable 100%/at least `np`, lets every pod be evicted at once. `why` is "ok", "none" or "all";
# `dis` is `why=="ok"`. A Deployment counts only when EXACTLY ONE PDB selects it and that PDB passes `dis`:
# the eviction subresource refuses a pod matched by several PDBs (pkg/registry/core/pod/storage/eviction.go:
# "This pod has more than one PodDisruptionBudget, which the eviction subresource does not support").
rl rel-2 pdb deployments 'input as $d|[$d.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $deps0|([$deps0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$deps0[]|select(.spec.template.spec|iswinspec|not)] as $deps|[.items[]?] as $pdbs|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def sm($L): (.spec.selector) as $sel0|($sel0//{}) as $sel|(($sel0|type)=="object") and (($sel.matchLabels//{})|to_entries|all(.value==($L[.key]//null))) and (($sel.matchExpressions//[])|all(. as $e|($e.key) as $k|($L[$k]//null) as $v| if $e.operator=="In" then (($e.values//[])|index($v))!=null elif $e.operator=="NotIn" then (($e.values//[])|index($v))==null elif $e.operator=="Exists" then $v!=null elif $e.operator=="DoesNotExist" then $v==null else false end));def np: . as $pb|[$deps0[]|select((.metadata.namespace//"")==($pb.metadata.namespace//""))|((.spec.template.metadata.labels)//{}) as $L2|select($pb|sm($L2))|(.spec.replicas//1)]|add//0;def pct($v): ($v|rtrimstr("%")|tonumber);def why: np as $n|(.spec.maxUnavailable) as $mu|(.spec.minAvailable) as $ma|if $mu!=null then (if ($mu|type)=="number" then (if $mu<1 then "none" elif $n>0 and $mu>=$n then "all" else "ok" end) elif (($mu|type)=="string") and ($mu|test("^[0-9]+%$")) then (if pct($mu)<=0 then "none" elif $n>0 and (pct($mu)*$n/100)>($n-1) then "all" else "ok" end) else "none" end) elif $ma!=null then (if ($ma|type)=="number" then (if $ma>=$n then "none" elif $ma<1 then "all" else "ok" end) elif (($ma|type)=="string") and ($ma|test("^[0-9]+%$")) then (if (pct($ma)*$n/100)>($n-1) then "none" elif pct($ma)<=0 then "all" else "ok" end) else "none" end) else "none" end;def dis: why=="ok";[$deps[]|. as $dep|(($dep.spec.template.metadata.labels)//{}) as $L|[$pdbs[]|select((.metadata.namespace//"")==($dep.metadata.namespace//""))|select(sm($L))] as $m|($m|length) as $k|([$m[]|why as $w|select($w!="ok")|{p:(.metadata.name//"?"),w:$w}]|first) as $zero|(if $k==1 and $zero==null then ($m[0].metadata.name//"?") else null end) as $hit|{n:(($dep|qn)+(if $hit!=null then "  <- "+$hit elif $k>1 then "  <- "+([$m[]|(.metadata.name//"?")]|join(", "))+" (selected by \($k) PDBs — eviction refuses a pod with more than one)" elif $zero!=null then "  <- "+$zero.p+(if $zero.w=="all" then " (allows every replica to be evicted at once)" else " (allows no voluntary disruption)" end) else "" end)),ok:($hit!=null)}] as $r|{pass:[$r[]|select(.ok)|.n],fail:[$r[]|select(.ok|not)|.n],context:[$pdbs[]|qn]}'
m2 rel-2 pdb deployments 'input as $d|[$d.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $deps0|([$deps0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$deps0[]|select(.spec.template.spec|iswinspec|not)] as $deps|[.items[]?] as $pdbs|($deps|length) as $t|def sm($L): (.spec.selector) as $sel0|($sel0//{}) as $sel|(($sel0|type)=="object") and (($sel.matchLabels//{})|to_entries|all(.value==($L[.key]//null))) and (($sel.matchExpressions//[])|all(. as $e|($e.key) as $k|($L[$k]//null) as $v| if $e.operator=="In" then (($e.values//[])|index($v))!=null elif $e.operator=="NotIn" then (($e.values//[])|index($v))==null elif $e.operator=="Exists" then $v!=null elif $e.operator=="DoesNotExist" then $v==null else false end));def np: . as $pb|[$deps0[]|select((.metadata.namespace//"")==($pb.metadata.namespace//""))|((.spec.template.metadata.labels)//{}) as $L2|select($pb|sm($L2))|(.spec.replicas//1)]|add//0;def pct($v): ($v|rtrimstr("%")|tonumber);def why: np as $n|(.spec.maxUnavailable) as $mu|(.spec.minAvailable) as $ma|if $mu!=null then (if ($mu|type)=="number" then (if $mu<1 then "none" elif $n>0 and $mu>=$n then "all" else "ok" end) elif (($mu|type)=="string") and ($mu|test("^[0-9]+%$")) then (if pct($mu)<=0 then "none" elif $n>0 and (pct($mu)*$n/100)>($n-1) then "all" else "ok" end) else "none" end) elif $ma!=null then (if ($ma|type)=="number" then (if $ma>=$n then "none" elif $ma<1 then "all" else "ok" end) elif (($ma|type)=="string") and ($ma|test("^[0-9]+%$")) then (if (pct($ma)*$n/100)>($n-1) then "none" elif pct($ma)<=0 then "all" else "ok" end) else "none" end) else "none" end;def dis: why=="ok";([$deps[]|. as $dep|($dep.spec.template.metadata.labels//{}) as $L|select([$pdbs[]|select((.metadata.namespace//"")==($dep.metadata.namespace//""))|select(sm($L))] as $mm|($mm|length)==1 and ($mm|all(dis)))]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" elif $t==0 then "na~no workload Deployments" else b($ok;$t)+"~\($ok)/\($t) deploys covered by exactly one PDB, which allows a disruption"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# rel-3 AND rel-6 COUNT CONTAINERS, and their `m` programs flatten `.spec.containers[]?` with no pod or
# namespace attached, so the `rl` carries the POD through the flatten and names `ns/pod / container`, the only
# actionable form. `select(.c.resources.limits.cpu and .c.resources.limits.memory)` IS the verdict's own test,
# evaluated by jq, so list and verdict agree on truthiness (`limits.cpu: ""` and `readinessProbe: {}` are true
# to both sides).
rl rel-3 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $pods|[$pods[]|select(iswinpod($wds))] as $wpods|[$pods[]|select(iswinpod($wds)|not)|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pod|.spec.containers[]?|{n:($pod+" / "+(.name//"?")),c:.}] as $c|[$c[]|select(.c.resources.limits.cpu and .c.resources.limits.memory)] as $p|{pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if ($wpods|length)>0 then {context:(["\($wpods|length) Windows pod(s) not assessed — this skill supports Linux nodes only"]+[$wpods[]|(.metadata.namespace//"")+"/"+(.metadata.name//"?")])} else {} end)+(if ($c|length)==0 and ($wpods|length)>0 then {context_only:true} else {} end)'
m2 rel-3 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $pods|([$pods[]|select(iswinpod($wds))]|length) as $wp|[$pods[]|select(iswinpod($wds)|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.limits.cpu and .resources.limits.memory)]|length) as $ok| if ($t==0 and $wp>0) then winpna($wp) elif $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) limits (workloads)"+winpx($wp) end'
# rel-4 identifies the autoscaler by container IMAGE REPOSITORY and Karpenter's node label, not Deployment
# name: a Deployment NAMED `cluster-autoscaler` can run the `karpenter/controller` image, and a Helm release can
# use a non-default name. THE IMAGE PATTERN NAMES THE UPSTREAM REPOSITORIES as whole path components, so a
# registry prefix, an ECR pull-through cache or a tag/digest still match: `karpenter/controller` (the chart's
# controller.image.repository is public.ecr.aws/karpenter/controller, github.com/aws/karpenter-provider-aws
# charts/karpenter/values.yaml) and `cluster-autoscaler` with an optional -amd64/-arm64/-s390x suffix
# (registry.k8s.io/autoscaling/cluster-autoscaler; github.com/kubernetes/autoscaler cluster-autoscaler/Makefile
# builds IMAGE=$(REGISTRY)/cluster-autoscaler and per-arch `-$(ARCH)` images). A substring would let any image
# whose path contains `karpenter` count, and a bare `autoscaler` matches `cluster-proportional-autoscaler`.
# THE IMAGE ARM READS ONLY Running PODS AND REQUIRES THE CONTAINER TO BE READY: kubernetes.io/docs/concepts/
# workloads/pods/pod-lifecycle/ defines Running as "...At least one container is still running, or is in the
# process of starting or restarting", so a CrashLoopBackOff controller keeps phase Running. A container is
# credited only when the same-`name` `status.containerStatuses[]` entry has `ready == true` AND the Pod is
# ready (`$pok`: Ready condition `True`, no `deletionTimestamp`). The Deployment-name arm credits only
# `status.readyReplicas` above 0. A match failing readiness is never credited and `rl` lists it as a failing
# row, as it does a Deployment whose POD TEMPLATE runs a matching image under a non-matching name with no
# ready replica (`$tdn`/`$ntpl`); when such matches are all the evidence the answer is `none`.
# THE `karpenter.sh/nodepool` LABEL IS CREDITED ONLY BESIDE A READY CONTROLLER (`$kok`): Karpenter writes it
# on the nodes it launches and nothing removes it when the controller goes, so on its own it records past
# provisioning. With a controller-image container seen and none ready, or only a Deployment whose template runs
# it with no ready replica, the label is withheld (`$kbroken`, `none`). With no controller seen at all it caps
# at `most`, never `none`: a controller mirrored under another repository name is not recognised. Auto Mode's
# compute-type=auto nodes are excluded before this test. A not-ready Cluster Autoscaler is a failing match: beside the label, `none`.
# rel-4 DECIDES AUTO MODE ON THE CLUSTER FIELD. A bare `karpenter.sh/nodepool` test would credit Auto Mode for
# the wrong reason: Auto Mode applies that label to every node it provisions (docs.aws.amazon.com/eks/latest/
# userguide/associate-workload.html), and the detail would imply an in-cluster controller that does not
# exist. The capability: docs.aws.amazon.com/eks/latest/userguide/automode.html -- "Auto scaling: Relying on
# Karpenter auto scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to
# be deployed to run those Pods." The computeConfig.enabled branch lives only in the `rl` and `m4` lines below
# (the pair reads the same field); do not add a copy elsewhere.
# THE AUTO MODE ARM ALSO REQUIRES `computeConfig.nodePools` TO BE A NON-EMPTY LIST: `enabled` is not proof
# anything may be provisioned, and `all` from one boolean is a Pass without evidence. The empty-list arm caps
# at `most` and states only what was read (no BUILT-IN Auto Mode node pool is enabled). It must NOT say the
# cluster cannot provision -- NodePool objects are collected nowhere, so an operator-created pool is neither
# confirmed nor excluded -- and must not answer `none`, a false FAIL on evidence not held.
# ABSENT OR `null` IS NOT `[]`: the arm tests the TYPE and says "not reported" for absent/null, as `rel-24`
# does for `deletionProtection`. `arrays` rather than a bare `//[]`: `//` defaults on null, it does not defend
# a type, and `("general-purpose"//[])|length` is 15 (a string's length is its character count), so a STRING
# `nodePools` would be credited as a populated list and the later `join` would die with `Cannot iterate over string`, costing the whole pillar its score.
# THE OSS ARMS STILL WIN: the empty-list arm carries `($img+$karpnodes)==0`, so self-managed Karpenter beside
# Auto Mode (a READY image match; the label on a node NOT labelled compute-type=auto counts only beside one) still answers `all`.
# With Auto Mode enabled `$karpnodes`/`$karp` skip compute-type=auto nodes, which carry the label by AWS's
# hand. (`$name` is NOT in that guard: a NAME-only match is the weakest signal and is capped at `most` too.)
# rel-4's FARGATE ARM is deliberately LAST of the positive arms. A Fargate-only cluster has no EC2 node
# population to grow or shrink (docs.aws.amazon.com/eks/latest/best-practices/cost-opt-compute.html: "no EC2
# instance or operating system management"), so `none~no autoscaler` would invent a gap the operator cannot
# close. But the Karpenter controller can run on Fargate while provisioning EC2 nodes, so a ready image match
# must win. Only a cluster with nodes, none of them EC2, no CREDITED autoscaler evidence AND no broken
# autoscaler evidence reaches the `na`; a not-ready or Pending match, or a Deployment whose template runs such
# an image with no ready replica, sends it to `none`. A Deployment matched by NAME only, with no ready replica,
# does not block the `na`; `rl` names it in `context`.
# rel-4's `rl` FOLLOWS THE VERDICT'S ARMS:
#   computeConfig.enabled==true AND (nodePools non-empty OR no ready image match and no credited nodepool-label
#     node) -> `kind:"field"`: `pass` holds the enabled row plus the nodePools row when the list is non-empty;
#     with an empty list the nodePools row goes to `fail` instead (with any not-credited nodepool-label rows)
#     and only the enabled row passes. Enabled with an empty list AND such a match takes the arms below.
#   Windows-only, or hybrid-only, cluster -> `context` ONLY with `context_only:true`.
#   nodes exist, none of them EC2, no credited signal and no broken image/template evidence -> `context` ONLY,
#     `pass` and `fail` empty (nothing was counted, so nothing is named as passed). This Fargate arm sets no
#     `context_only`: its detail has no `n/m` to cross-check.
#   otherwise -> every match FROM ALL THREE SIGNALS (container image, `karpenter.sh/nodepool` node label,
#     Deployment name), each row saying which; naming Deployments only would print "found none" beneath a
#     green Pass won by an image. Credited matches are `pass`; a match that failed readiness (including a
#     labelled node not credited, or a template-only Deployment with no ready replica) is a `fail` row.
# All three patterns are matched case-insensitively, as the verdict does.
rl rel-4 deployments pods nodes cluster 'input as $p|input as $n|input as $cl|"(^|/)(karpenter/controller|cluster-autoscaler(-(amd64|arm64|s390x))?)(:|@|$)" as $pimg|"(^|/)karpenter/controller(:|@|$)" as $kimg|"karpenter|cluster-autoscaler" as $pnm|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");[$p.items[]?|select((.status.phase//"")=="Running")|qn as $pod|(.metadata.deletionTimestamp==null and any((.status.conditions//[])[]?;.type=="Ready" and .status=="True")) as $pok|[(.status.containerStatuses//[])[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(.image|test($pimg;"i"))|{r:($pok and ((.name//"") as $cn|any($rdy[];.==$cn))),s:($pod+" / "+(.name//"?")+" = "+(.image//"?"))}] as $ic|[$ic[]|select(.r)|"container image: "+.s] as $img|[$ic[]|select(.r|not)|"container image, NOT READY (not credited): "+.s] as $nimg|[$n.items[]?|select(islinux and ((.metadata.labels["karpenter.sh/nodepool"]//"")!="") and (($cl.cluster.computeConfig.enabled==true and (.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")|not))|(.metadata.name//"?")+" = "+(.metadata.labels["karpenter.sh/nodepool"]//"")] as $kl|([$p.items[]?|select((.status.phase//"")|IN("Running","Pending"))|(.status.phase) as $ph|(.metadata.deletionTimestamp==null and any((.status.conditions//[])[]?;.type=="Ready" and .status=="True")) as $pok|[(.status.containerStatuses//[])[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(.image|test($kimg;"i"))|($ph=="Running" and ($pok and ((.name//"") as $cn|any($rdy[];.==$cn))))]) as $kc|([.items[]?|select([.spec.template.spec.containers[]?.image|strings]|any(test($kimg;"i")))|(((.status.readyReplicas|numbers)//0)>0)]) as $kd|(if ($kc|length)>0 then ([$kc[]|select(.)]|length)==0 else (($kd|length)>0 and ([$kd[]|select(.)]|length)==0) end) as $kbroken|(if ($kc|length)>0 then "\($kc|length) container(s) running the Karpenter controller image are seen in Running or Pending Pods and none is ready" else "\($kd|length) Deployment(s) whose Pod template runs the Karpenter controller image are seen and none has a ready replica, and no container running it is in a Running or Pending Pod" end) as $kwhy|([$kc[]|select(.)]|length>0) as $kok|(if $kok then [$kl[]|"node label karpenter.sh/nodepool: "+.] else [] end) as $karp|(if $kbroken then [$kl[]|"node label karpenter.sh/nodepool, NOT CREDITED ("+$kwhy+"): "+.] elif $kok then [] else [$kl[]|"node label karpenter.sh/nodepool, NO CONTROLLER SEEN (no container running the Karpenter controller image (karpenter/controller) is in a Running or Pending Pod; the label stays on a node after the controller that set it is removed, so it is not proof of a working autoscaler): "+.] end) as $nkarp|[.items[]?|select((.metadata.name|test("karpenter|cluster-autoscaler";"i"))|not)|select([.spec.template.spec.containers[]?.image|strings]|any(test($pimg;"i")))|select((((.status.readyReplicas|numbers)//0)>0)|not)|"Deployment Pod template image, NO READY REPLICA (not credited): "+qn+" = "+([.spec.template.spec.containers[]?.image|strings|select(test($pimg;"i"))]|join(", "))] as $ntpl|[$p.items[]?|select((.status.phase//"")=="Pending")|qn as $pod|.spec.containers[]?|select(.image|test($pimg;"i"))|"container image, Pod PENDING (not credited): "+$pod+" / "+(.name//"?")+" = "+(.image//"?")] as $pnd|[.items[]?|select(.metadata.name|test($pnm;"i"))|{r:(((.status.readyReplicas|numbers)//0)>0),s:qn}] as $dc|[$dc[]|select(.r)|"Deployment name: "+.s] as $name|[$dc[]|select(.r|not)|"Deployment name, NO READY REPLICA (not credited): "+.s] as $nname|(([$n.items[]?]|length)>0) as $any|(([$n.items[]?|select(islinux)]|length)==0) as $noec2|[$n.items[]?|select(iswin and isec2)] as $wn|($wn|length) as $w|(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+[$wn[]|.metadata.name//"?"] else [] end) as $wctx|([$n.items[]?|select(ishy)]|length) as $hy|($cl.cluster.computeConfig) as $cc|(($cc.nodePools|arrays)//[]) as $np|(if (($cc.nodePools|type)=="array") then "[] (an empty list: no built-in Auto Mode node pool is enabled)" elif ($cc.nodePools==null) then "not reported by this API response" else "reported as a \($cc.nodePools|type) rather than a list, so it could not be read" end) as $npv|if ($cc.enabled==true and (($np|length)>0)) then {kind:"field",pass:["computeConfig.enabled = true (EKS Auto Mode provisions nodes; no in-cluster autoscaler is expected)","computeConfig.nodePools = "+($np|join(", "))],fail:[]}+(if $w>0 then {context:$wctx} else {} end) elif ($cc.enabled==true and ((($img+$karp)|length)==0)) then {kind:"field",pass:["computeConfig.enabled = true (EKS Auto Mode provisions nodes; no in-cluster autoscaler is expected)"],fail:(["computeConfig.nodePools = "+$npv+" -- this review does not collect NodePool objects, so a NodePool you created yourself was not read and is neither confirmed nor excluded here"]+$nkarp)}+(if $w>0 then {context:$wctx} else {} end) elif ($noec2 and $w>0) then {pass:[],fail:[],context:$wctx,context_only:true} elif ($any and $noec2 and $hy>0) then {pass:[],fail:[],context:["\($hy) EKS Hybrid Node(s) and no EC2 node: Cluster Autoscaler scales EC2 Auto Scaling groups and Karpenter provisions EC2 instances, and neither can create or remove a hybrid node, so there is no node population here for either to act on"],context_only:true} elif ($any and $noec2 and (($img+$karp+$name)|length)==0 and (($nimg+$pnd)|length)==0 and ([.items[]?|select([.spec.template.spec.containers[]?.image|strings]|any(test($pimg;"i")))|select((((.status.readyReplicas|numbers)//0)>0)|not)]|length)==0) then {pass:[],fail:[],context:(["every node carries eks.amazonaws.com/compute-type=fargate (Fargate schedules one Pod per node and provisions that node itself, so there is no EC2 node population for an autoscaler to grow or shrink)","no READY container in a Running Pod has an image matching "+$pimg,"no node carries a karpenter.sh/nodepool label","no Deployment with a ready replica has a name matching "+$pnm]+$nimg+$pnd+$nname)} else {kind:"existence",pass:($img+$karp+$name),fail:($nimg+$pnd+$nname+$ntpl+$nkarp),context:(["container images (credited only for a ready container in a Running Pod that is Ready and not being deleted): "+$pimg,"node label: karpenter.sh/nodepool (credited only beside a READY container running the Karpenter controller image "+$kimg+" in a Running Pod; with no such container seen it is listed as not credited)"+(if $cc.enabled==true then " (on a node NOT labelled eks.amazonaws.com/compute-type=auto: Auto Mode applies this label to every node it provisions)" else "" end),"Deployment names (credited only with status.readyReplicas > 0): "+$pnm]+$wctx)} end'
m4 rel-4 deployments pods nodes cluster 'input as $p|input as $n|input as $cl|"(^|/)(karpenter/controller|cluster-autoscaler(-(amd64|arm64|s390x))?)(:|@|$)" as $aimg|"(^|/)karpenter/controller(:|@|$)" as $kimg|($cl.cluster.computeConfig) as $cc|(($cc.nodePools|arrays)//[]) as $np|(if (($cc.nodePools|type)=="array") then "computeConfig.nodePools is an EMPTY list, so no BUILT-IN Auto Mode node pool is enabled" elif ($cc.nodePools==null) then "this API response does not report computeConfig.nodePools at all, so which node pools are enabled was not read" else "this API response reports computeConfig.nodePools as a \($cc.nodePools|type) rather than a list, so which node pools are enabled could not be read" end) as $npstate|([$p.items[]?|select((.status.phase//"")=="Running")|(.metadata.deletionTimestamp==null and any((.status.conditions//[])[]?;.type=="Ready" and .status=="True")) as $pok|[(.status.containerStatuses//[])[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(.image|test($aimg;"i"))|($pok and ((.name//"") as $cn|any($rdy[];.==$cn)))]) as $ic|([$ic[]|select(.)]|length) as $img|([$ic[]|select(.|not)]|length) as $nimg|([.items[]?|select(.metadata.name|test("karpenter|cluster-autoscaler";"i"))|(((.status.readyReplicas|numbers)//0)>0)]) as $dc|([$dc[]|select(.)]|length) as $name|([$dc[]|select(.|not)]|length) as $nname|([$n.items[]?|select(islinux and ((.metadata.labels["karpenter.sh/nodepool"]//"")!="") and (($cc.enabled==true and (.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")|not))]|length) as $karpraw|([$p.items[]?|select((.status.phase//"")|IN("Running","Pending"))|(.status.phase) as $ph|(.metadata.deletionTimestamp==null and any((.status.conditions//[])[]?;.type=="Ready" and .status=="True")) as $pok|[(.status.containerStatuses//[])[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(.image|test($kimg;"i"))|($ph=="Running" and ($pok and ((.name//"") as $cn|any($rdy[];.==$cn))))]) as $kc|([.items[]?|select([.spec.template.spec.containers[]?.image|strings]|any(test($kimg;"i")))|(((.status.readyReplicas|numbers)//0)>0)]) as $kd|(if ($kc|length)>0 then ([$kc[]|select(.)]|length)==0 else (($kd|length)>0 and ([$kd[]|select(.)]|length)==0) end) as $kbroken|(if ($kc|length)>0 then "\($kc|length) container(s) running the Karpenter controller image are seen in Running or Pending Pods and none is ready" else "\($kd|length) Deployment(s) whose Pod template runs the Karpenter controller image are seen and none has a ready replica, and no container running it is in a Running or Pending Pod" end) as $kwhy|([$kc[]|select(.)]|length>0) as $kok|(if $kok then $karpraw else 0 end) as $karpnodes|([.items[]?|select((.metadata.name|test("karpenter|cluster-autoscaler";"i"))|not)|select([.spec.template.spec.containers[]?.image|strings]|any(test($aimg;"i")))|select((((.status.readyReplicas|numbers)//0)>0)|not)]|length) as $tdn|(if $kbroken and $karpraw>0 then " — \($karpraw) node(s) carry the karpenter.sh/nodepool label, but it is not credited: \($kwhy)" else "" end) as $kbx|([$p.items[]?|select((.status.phase//"")=="Pending")|.spec.containers[]?|select(.image|test($aimg;"i"))]|length) as $pend|([$n.items[]?|select(islinux)]|length) as $t|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|(([$n.items[]?]|length)>0) as $any| if ($cc.enabled==true and (($np|length)>0)) then "all~EKS Auto Mode provides node autoscaling as a service capability (computeConfig.enabled=true, computeConfig.nodePools=\(($np|join(", ")))): it watches for unschedulable Pods, provisions nodes to run them and terminates nodes it no longer needs, so no in-cluster autoscaler Deployment is expected or found"+winx($w) elif ($cc.enabled==true and (($img+$karpnodes)==0)) then "most~EKS Auto Mode compute is enabled (computeConfig.enabled=true) but \($npstate); this review does not collect NodePool objects, so a NodePool you created yourself was NOT READ and is neither confirmed nor excluded here -- check it with kubectl get nodepools.karpenter.sh"+$kbx+winx($w) elif ($t==0 and $w>0) then winna($w)+hyx($hy) elif ($t==0 and $hy>0) then hyna($hy;"Cluster Autoscaler grows and shrinks EC2 Auto Scaling groups and Karpenter provisions EC2 instances; a hybrid node is a machine the operator joins with nodeadm through a HYBRID_LINUX access entry, and neither controller can create or remove one, so there is no node population here for either to scale") elif ($img+$karpnodes)>0 then "all~autoscaler present (by image/nodepool label)"+winx($w) elif ($karpraw>0 and ($kbroken|not) and ($nimg+$nname+$pend+$tdn)==0) then "most~\($karpraw) node(s) carry the karpenter.sh/nodepool label, which Karpenter writes on the nodes it launches, but no container running the Karpenter controller image (karpenter/controller) is in a Running or Pending Pod: the label stays on a node after the controller that set it is removed, so it shows Karpenter provisioned these nodes, not that anything scales this cluster now -- confirm which controller runs with kubectl get deployments -A -o wide (a controller image mirrored under another repository name is not recognised)"+winx($w) elif $name>0 then "most~a Deployment NAMED like an autoscaler has a ready replica, but no ready container running a matching image was found"+(if $nimg>0 then " (\($nimg) container(s) in Running Pods run a matching image and are not ready)" else "" end)+" — confirm which controller is actually running"+$kbx+winx($w) elif ($any and $t==0 and ($nimg+$pend)==0 and ([.items[]?|select([.spec.template.spec.containers[]?.image|strings]|any(test($aimg;"i")))|select((((.status.readyReplicas|numbers)//0)>0)|not)]|length)==0) then "na~every node is a Fargate node: Fargate schedules one Pod per node and provisions that node itself, so there is no EC2 node population for a cluster autoscaler to grow or shrink" elif (($nimg+$nname+$pend+$tdn)>0 or ($kbroken and $karpraw>0)) then "none~no READY autoscaler found: "+([(if $nimg>0 then "\($nimg) container(s) in Running Pods run a Karpenter controller or Cluster Autoscaler image but are not ready" else empty end),(if $pend>0 then "\($pend) container(s) in Pending Pods run a Karpenter controller or Cluster Autoscaler image and have not started" else empty end),(if $nname>0 then "\($nname) Deployment(s) named like an autoscaler have no ready replica (status.readyReplicas)" else empty end),(if $tdn>0 then "\($tdn) Deployment(s) not named like an autoscaler run a Karpenter controller or Cluster Autoscaler image in their Pod template and have no ready replica (status.readyReplicas)" else empty end),(if ($kbroken and $karpraw>0) then "\($karpraw) node(s) carry the karpenter.sh/nodepool label, but it is not credited: \($kwhy)" else empty end)]|join(", and "))+" -- a controller that is not ready is not credited as autoscaling this cluster; find out why with kubectl describe deployment, kubectl describe pod and kubectl logs --previous"+winx($w) else "none~no autoscaler"+winx($w) end'
# rel-5/7/8/9/18 and perf-4/5 (performance-efficiency.md) SHARE ONE `rl` SHAPE, copied because each `rl` is
# its own jq process: CHANGE ONE, CHANGE ALL SEVEN. The denominator is Deployments OUTSIDE `kube-*`/`amazon-*`
# whose pod template is not Windows (`iswinspec`); every Deployment the namespace rule EXCLUDED is named in
# `context` with the AWS-owner label it declares on itself, or the fact that it declares none. The rule is a
# namespace-NAME prefix only, so without that annotation the heading would certify an operator-installed
# `kube-system` Karpenter controller as somebody else's. The owner label only annotates; it never decides.
# `own` IS AN ORDERED PROBE: four labels in the order written, the third accepted only when its value STARTS
# WITH eks/amazon/aws (case-insensitively), first hit wins, else "no AWS owner label (may be yours)".
# `managed-by: Helm` falls THROUGH to `k8s-app`, `managed-by: prefix-aws` does NOT match, and an empty value
# reads as no label. Registry is not a signal: `public.ecr.aws/karpenter/controller` is AWS-published but
# operator-installed. No object changes sides: each list names what the `m` line under it counted.
rl rel-5 hpa deployments 'input as $dp|[.items[]?] as $hpas|[$dp.items[]?] as $all|[$all[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|. as $dep|select([$hpas[]|select(.metadata.namespace==$dep.metadata.namespace)|select((((.spec.scaleTargetRef.kind)//"")=="Deployment") and (((.spec.scaleTargetRef.name)//"")==$dep.metadata.name))]|length>0)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m2 rel-5 hpa deployments 'input as $d|[.items[]?] as $hpas|[$d.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $deps0|([$deps0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$deps0[]|select(.spec.template.spec|iswinspec|not)] as $deps|($deps|length) as $t|([$deps[]|. as $dep|select([$hpas[]|select(.metadata.namespace==$dep.metadata.namespace)|select((((.spec.scaleTargetRef.kind)//"")=="Deployment") and (((.spec.scaleTargetRef.name)//"")==$dep.metadata.name))]|length>0)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" elif $t==0 then "na~no deploys" else b($ok;$t)+"~\($ok)/\($t) deploys with HPA"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# Same shape as rel-3: the pod comes through the flatten so the row has an owner.
rl rel-6 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $pods|[$pods[]|select(iswinpod($wds))] as $wpods|[$pods[]|select(iswinpod($wds)|not)|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pod|.spec.containers[]?|{n:($pod+" / "+(.name//"?")),c:.}] as $c|[$c[]|select(.c.readinessProbe)] as $p|{pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if ($wpods|length)>0 then {context:(["\($wpods|length) Windows pod(s) not assessed — this skill supports Linux nodes only"]+[$wpods[]|(.metadata.namespace//"")+"/"+(.metadata.name//"?")])} else {} end)+(if ($c|length)==0 and ($wpods|length)>0 then {context_only:true} else {} end)'
m2 rel-6 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $pods|([$pods[]|select(iswinpod($wds))]|length) as $wp|[$pods[]|select(iswinpod($wds)|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.readinessProbe)]|length) as $ok| if ($t==0 and $wp>0) then winpna($wp) elif $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) readiness (workloads)"+winpx($wp) end'
rl rel-7 deployments '[.items[]?] as $all|[$all[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|select((.spec.replicas//1)>1)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m rel-7 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|([$d0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|($d|length) as $t|([$d[]|select((.spec.replicas//1)>1)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) multi-replica"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# rel-8 counts a `podAntiAffinity` only when a required entry, or a preferred entry's `podAffinityTerm`,
# carries a `labelSelector` object (`paterm`, byte-identical to perf-5's). `{}`, `null` and empty term lists
# do not count; any `topologyKey` does.
rl rel-8 deployments 'def paterm: (.spec.template.spec.affinity.podAntiAffinity) as $a|if ($a|type)=="object" then ([(($a.requiredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects]+[(($a.preferredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects|.podAffinityTerm|objects]|map(select((.labelSelector|type)=="object"))|length)>0 else false end;[.items[]?] as $all|[$all[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|select(paterm)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m rel-8 deployments 'def paterm: (.spec.template.spec.affinity.podAntiAffinity) as $a|if ($a|type)=="object" then ([(($a.requiredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects]+[(($a.preferredDuringSchedulingIgnoredDuringExecution|arrays)//[])[]|objects|.podAffinityTerm|objects]|map(select((.labelSelector|type)=="object"))|length)>0 else false end;[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|([$d0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|($d|length) as $t|([$d[]|select(paterm)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) anti-affinity"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# rel-9 COUNTS A ZONE-KEYED TOPOLOGY SPREAD CONSTRAINT ONLY WHEN IT CARRIES A `labelSelector`: "A null label
# selector matches no objects" (API reference, topologySpreadConstraints.labelSelector), so it spreads
# nothing. perf-5 in references/performance-efficiency.md applies the same test.
rl rel-9 deployments '[.items[]?] as $all|[$all[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|select([(.spec.template.spec.topologySpreadConstraints//[])[]|select(((.topologyKey//"")|IN("topology.kubernetes.io/zone","topology.k8s.aws/zone-id","failure-domain.beta.kubernetes.io/zone")) and ((.labelSelector|type)=="object"))]|length>0)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m rel-9 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|([$d0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|($d|length) as $t|([$d[]|select([(.spec.template.spec.topologySpreadConstraints//[])[]|select(((.topologyKey//"")|IN("topology.kubernetes.io/zone","topology.k8s.aws/zone-id","failure-domain.beta.kubernetes.io/zone")) and ((.labelSelector|type)=="object"))]|length>0)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) topo-spread"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
g rel-10
rl rel-11 pvc storageclasses pods 'input as $sc|input as $po|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");[$sc.items[]?|select(((.volumeBindingMode//"")=="WaitForFirstConsumer"))|(.metadata.name//"")] as $wf|[$po.items[]?|(.metadata.namespace//"") as $ns|(.metadata.name//"") as $pn|(.spec.volumes[]?|((.persistentVolumeClaim.claimName|strings),(select(.ephemeral!=null)|.name|strings|$pn+"-"+.)))|$ns+"/"+.] as $used|[.items[]] as $all|[$all[]|select(((.status.phase//"")=="Pending") and (((.spec.storageClassName//"") as $s|$wf|index($s))!=null) and ((n as $k|$used|index($k))==null) and (([.metadata.ownerReferences[]?|objects|select(.kind=="Pod")]|length)==0))] as $dl|($all-$dl) as $c|[$c[]|select(.status.phase=="Bound")] as $p|{pass:[$p[]|n],fail:[($c-$p)[]|n]}+(if ($dl|length)>0 then {context:[$dl[]|n+" \u2014 Pending on a WaitForFirstConsumer StorageClass with no consumer Pod, so it is not counted: such a claim binds only once a Pod that uses it is scheduled"]} else {} end)'
m3 rel-11 pvc storageclasses pods 'input as $sc|input as $po|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");[$sc.items[]?|select(((.volumeBindingMode//"")=="WaitForFirstConsumer"))|(.metadata.name//"")] as $wf|[$po.items[]?|(.metadata.namespace//"") as $ns|(.metadata.name//"") as $pn|(.spec.volumes[]?|((.persistentVolumeClaim.claimName|strings),(select(.ephemeral!=null)|.name|strings|$pn+"-"+.)))|$ns+"/"+.] as $used|[.items[]] as $all|[$all[]|select(((.status.phase//"")=="Pending") and (((.spec.storageClassName//"") as $s|$wf|index($s))!=null) and ((n as $k|$used|index($k))==null) and (([.metadata.ownerReferences[]?|objects|select(.kind=="Pod")]|length)==0))] as $dl|($all-$dl) as $c|($c|length) as $t|([$c[]|select(.status.phase=="Bound")]|length) as $ok|($dl|length) as $x| b($ok;$t)+"~\($ok)/\($t) bound"+(if $x>0 then " (\($x) Pending PVC(s) on a WaitForFirstConsumer StorageClass with no consumer Pod not counted: such a claim binds only once a Pod that uses it is scheduled)" else "" end)'
g rel-12
# rel-13 -- a running COLLECTOR found by Deployment name, DaemonSet name or container image is real
# monitoring (Container Insights' agent is a DaemonSet; Amazon Managed Prometheus is scraped by an ADOT collector).
# DUPLICATED PROGRAM -- EDIT BOTH OR NEITHER: the `rl` and `m3` lines are byte-identical to ope-5's in
# references/operational-excellence.md. Nothing enforces the match; if they drift, one cluster fact gets two
# verdicts (monitored in Operational Excellence, unmonitored here) and two evidence lists. Given up to hold
# the match, to be added in BOTH at once: an image row does not name the CONTAINER (two matching containers in
# one Pod emit two identical rows; the count still agrees), and the patterns are not published as `context`.
# The `rl` NAMES ALL THREE SOURCES THE VERDICT SUMS and says which each row came from; the detail has no
# `n/m`, so the cross-check cannot catch a shorter list. `kind:"existence"`: a name/image match, not a ratio.
# AN OPERATOR IS NOT A COLLECTOR (rel-23's rule): a name or image containing `operator` is not credited, nor
# is a Deployment or DaemonSet whose pod template runs such an image -- the CloudWatch add-on's controller-
# manager runs `cloudwatch-agent-operator`, and the `prometheus-config-reloader` sidecar's image sits under
# `prometheus-operator/`. The add-on's `cloudwatch-agent` DaemonSet and an OpenTelemetry `<cr>-collector` count.
# ALL THREE ARMS REQUIRE THE THING TO BE RUNNING: Deployment `readyReplicas`, DaemonSet `numberReady`, or Pod
# phase `Running` AND the matching container `ready: true`. `|numbers`, not `//0`: jq orders strings above numbers.
# THE POD ARM TESTS `phase=="Running"` EXACTLY, NOT rel-3/rel-6's predicate: a `Pending` pod belongs in their
# denominators, but a `Pending` collector watches nothing. Windows pins are skipped (`iswinspec`/`iswinpod`).
rl rel-13 deployments daemonsets pods 'input as $ds|input as $p|($ds|winds) as $w|def q: ((.metadata.namespace)//"")+"/"+((.metadata.name)//"?");([.items[]?|select(.spec.template.spec|iswinspec|not)|select(((.metadata.name)//"?")|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((((.metadata.name)//"?")|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.readyReplicas|numbers)>0)|"Deployment "+q]+[$ds.items[]?|select(.spec.template.spec|iswinspec|not)|select(((.metadata.name)//"?")|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((((.metadata.name)//"?")|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.numberReady|numbers)>0)|"DaemonSet "+q]+[$p.items[]?|select(iswinpod($w)|not)|select((.status.phase//"")=="Running")|q as $pod|[.status.containerStatuses[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(((.image)//"")|test("prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel";"i"))|select((((.image)//"")|test("node-exporter|operator";"i"))|not)|select(.name as $cn|$rdy|any(.==$cn))|"Pod "+$pod+" image "+((.image)//"?")]) as $hits|{pass:$hits,fail:[],kind:"existence"}'
m3 rel-13 deployments daemonsets pods 'input as $ds|input as $p|($ds|winds) as $w|(([.items[]?|select(.spec.template.spec|iswinspec|not)|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((.metadata.name|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.readyReplicas|numbers)>0)]|length) + ([$ds.items[]?|select(.spec.template.spec|iswinspec|not)|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((.metadata.name|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.numberReady|numbers)>0)]|length) + ([$p.items[]?|select(iswinpod($w)|not)|select((.status.phase//"")=="Running")|[.status.containerStatuses[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(((.image)//"")|test("prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel";"i"))|select((((.image)//"")|test("node-exporter|operator";"i"))|not)|select(.name as $cn|$rdy|any(.==$cn))]|length)) as $n| if $n>0 then "all~\($n) monitoring workload(s)/image(s)" else "none~none" end'
g rel-14
g rel-15
# rel-16 caps at `most`: a mesh control plane provides the CAPABILITY, but retries, circuit breaking and
# traffic shifting come from DestinationRule/VirtualService objects that are not collected. `all` would imply
# a resilience policy that may not exist.
# The mesh pattern is NOT the one Security uses (sec-27 in references/security/identity-access.md also tests
# Deployment NAMESPACES, exactly `istio-system|linkerd|consul` or a Linkerd extension namespace, and its name
# arm is the looser `linkerd`); this tests control-plane Deployment NAMES only. Everything this matches
# sec-27 matches too, so "mesh in Reliability, no mesh in Security" cannot happen, only the reverse. Do not align the two: a Deployment in a namespace named
# `consul` is not evidence of a control plane that can carry traffic policy.
m rel-16 deployments '([.items[]?|select(.metadata.name|test("istiod|linkerd-(destination|controller)|consul-connect";"i"))|select((.status.readyReplicas|numbers)>0)]|length) as $mesh| if $mesh>0 then "most~mesh control plane present; retries/circuit-breaking depend on DestinationRule/VirtualService policy, which this review does not collect" else "none~no mesh" end'
g rel-17
# rel-18's `rl` is the fifth copy in this file of the shared Deployment shape (see rel-5's note above for the owner probe).
# BOTH LINES BELOW ARE BYTE-IDENTICAL TO perf-4's in references/performance-efficiency.md, `rl` and `m`
# alike: one Deployment fact scored in two pillars. Do not "align" one side; if the test changes, change both.
rl rel-18 deployments '[.items[]?] as $all|[$all[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|[$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)] as $p|def qn: (.metadata.namespace//"")+"/"+(.metadata.name//"?");def own: (.metadata.labels//{}) as $L|[["eks.amazonaws.com/component",""],["addonmanager.kubernetes.io/mode",""],["app.kubernetes.io/managed-by","^(eks|amazon|aws)"],["k8s-app",""]]|map(. as [$k,$re]|(($L[$k]//"")|tostring) as $v|select($v!="" and ($re=="" or ($v|test($re;"i"))))|$k+"="+$v)|(.[0]//"no AWS owner label (may be yours)");{pass:[$p[]|qn],fail:[($d-$p)[]|qn],context:[$all[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)"))|qn+"  <- "+own]}'
m rel-18 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|([$d0[]|select(.spec.template.spec|iswinspec)]|length) as $wd|[$d0[]|select(.spec.template.spec|iswinspec|not)] as $d|($d|length) as $t|([$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only Deployments this question would judge are \($wd) Windows Deployment(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) rolling"+(if $wd>0 then " (\($wd) Windows Deployment(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
rl rel-19 daemonsets 'def _lxds: (.spec.template.spec//{})|iswinspec|not;[.items[]|select(_lxds)] as $d|[$d[]|select(.spec.updateStrategy.type=="RollingUpdate")] as $p|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");{pass:[$p[]|n],fail:[($d-$p)[]|n]}'
m rel-19 daemonsets 'def _lxds: (.spec.template.spec//{})|iswinspec|not;[.items[]] as $d0|([$d0[]|select(_lxds|not)]|length) as $wd|[$d0[]|select(_lxds)] as $d|($d|length) as $t|([$d[]|select(.spec.updateStrategy.type=="RollingUpdate")]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only DaemonSets this question would judge are \($wd) Windows DaemonSet(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) rolling DS"+(if $wd>0 then " (\($wd) Windows DaemonSet(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
m rel-20 daemonsets 'def _lxds: (.spec.template.spec//{})|iswinspec|not;[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d0|([$d0[]|select(_lxds|not)]|length) as $wd|[$d0[]|select(_lxds)|.spec.template.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory and .resources.limits.memory)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only workload DaemonSets this question would judge are \($wd) Windows DaemonSet(s); this skill supports Linux nodes only" elif $t==0 then "na~no workload DaemonSets (AWS-managed ones are not the operator'"'"'s to size)" else b($ok;$t)+"~\($ok)/\($t) DS containers with cpu+mem requests and a memory limit"+(if $wd>0 then " (\($wd) Windows DaemonSet(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# rel-21 HONOURS ITS TITLE -- "volumeClaimTemplates OR PVCs". `volumeClaimTemplates` gives each replica its
# own volume, but a StatefulSet mounting a PRE-PROVISIONED PersistentVolumeClaim from its pod template has
# persistent storage too; counting only the template arm would be a false FAIL against the question as
# worded. An `emptyDir` is still not storage and still fails.
# BOTH ARMS ARE TYPE-GATED WITH `arrays`: `//` defaults on `null` but hands a WRONG-TYPED value through, and
# `length` accepts a string. With `volumeClaimTemplates` set to the string "data", `(.//[])|length` reads 4 and
# credits persistent storage, and iterating a string `volumes` raises `Cannot iterate over string`, a SCORER
# ABORT that costs the whole pillar. `arrays` emits nothing for a non-array, so the answer is `none`.
m rel-21 statefulsets 'def _lxds: (.spec.template.spec//{})|iswinspec|not;[.items[]] as $s0|([$s0[]|select(_lxds|not)]|length) as $wd|[$s0[]|select(_lxds)] as $s|($s|length) as $t|([$s[]|select(((((.spec.volumeClaimTemplates|arrays)//[])|length)>0) or (([((.spec.template.spec.volumes|arrays)//[])[]|select(.persistentVolumeClaim)]|length)>0))]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only StatefulSets this question would judge are \($wd) Windows StatefulSet(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) STS storage"+(if $wd>0 then " (\($wd) Windows StatefulSet(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# THE DENOMINATOR IS EVERY StatefulSet whose pod template is not Windows, `kube-system` included, because
# that is what the scorer counts (no namespace filter). A list that filtered namespaces would read 0/2 against
# the scorer's 0/3 and the renderer would exit non-zero on a correct verdict.
rl rel-22 statefulsets 'def _lxds: (.spec.template.spec//{})|iswinspec|not;[.items[]|select(_lxds)] as $s|[$s[]|select((.spec.replicas//1)>1)] as $p|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");{pass:[$p[]|n],fail:[($s-$p)[]|n]}'
m rel-22 statefulsets 'def _lxds: (.spec.template.spec//{})|iswinspec|not;[.items[]] as $s0|([$s0[]|select(_lxds|not)]|length) as $wd|[$s0[]|select(_lxds)] as $s|($s|length) as $t|([$s[]|select((.spec.replicas//1)>1)]|length) as $ok| if $t==0 and $wd>0 then "na~NOT ASSESSED — the only StatefulSets this question would judge are \($wd) Windows StatefulSet(s); this skill supports Linux nodes only" else b($ok;$t)+"~\($ok)/\($t) STS multi-replica"+(if $wd>0 then " (\($wd) Windows StatefulSet(s) not assessed — this skill supports Linux nodes only)" else "" end) end'
# rel-23 ANCHORS ITS PATTERN AT A NAME-COMPONENT BOUNDARY. Unanchored, `otel` matches inside `hotel` and
# `tempo` inside `contemporary-api`, answering `all~tracing` on a cluster with no tracing. `(^|[^a-z])` makes
# the match start the name or follow a non-letter. `tempo` is also right-anchored (`tempo($|[^a-z])`) because
# Temporal's `temporal-frontend` starts with it; the rest are not, because `otelcol` and `otelcontribcol` are
# real collector names. rel-23 has NO `rl` line, so the reader cannot see what matched.
# A NAME CONTAINING `operator` IS NOT CREDITED: the OpenTelemetry/ADOT operator (the EKS `adot` add-on
# installs `opentelemetry-operator`) collects nothing until an `OpenTelemetryCollector` exists. DaemonSets are
# read too (trace collectors and the X-Ray daemon are commonly DaemonSets): `numberReady` above 0, as a
# Deployment needs `readyReplicas`. A ready Linux DaemonSet declaring the port `cwa-appsig-xray` also counts:
# the CloudWatch agent operator adds it only when the agent collects Application Signals traces, which go to
# X-Ray, and the CloudWatch Observability add-on enables that by default. Both arms skip Windows (`iswinspec`).
m2 rel-23 deployments daemonsets 'input as $ds|def tr: select(.spec.template.spec|iswinspec|not)|select(.metadata.name|test("(^|[^a-z])(jaeger|tempo($|[^a-z])|x-ray|xray|zipkin|otel|opentelemetry)"))|select((.metadata.name|test("operator"))|not);def xr: select(.spec.template.spec|iswinspec|not)|select(any(.spec.template.spec.containers[]?.ports[]?;(.name//"")=="cwa-appsig-xray"));if (([.items[]?|tr|select((.status.readyReplicas|numbers)>0)]|length)+([$ds.items[]?|tr|select((.status.numberReady|numbers)>0)]|length)+([$ds.items[]?|xr|select((.status.numberReady|numbers)>0)]|length))>0 then "all~tracing" else "none~none" end'
rl rel-24 cluster '{pass:["deletionProtection = " + (if (.cluster|has("deletionProtection")) then (.cluster.deletionProtection|tojson) else "not reported by this API version" end)],fail:[],kind:"field"}'
m rel-24 cluster 'if ((.cluster|has("deletionProtection"))|not) then "na~this API version does not report deletionProtection" elif .cluster.deletionProtection==true then "all~cluster deletion protection enabled" else "none~cluster deletion protection disabled -- DeleteCluster would succeed" end'
# lens-2's Auto Mode gate is EVERY EC2 NODE, not the cluster flag. `computeConfig.enabled` alone credits a
# node-level DNS cache to managed-node-group nodes on a MIXED-MODE cluster that lack one.
# docs.aws.amazon.com/eks/latest/userguide/auto-networking.html -- "EKS Auto Mode does not use the traditional
# CoreDNS deployment ... Auto Mode nodes utilize CoreDNS running as a system service directly on each node",
# and "If you plan to maintain a cluster with both Auto Mode and non-Auto Mode nodes, you must retain the
# CoreDNS deployment. Non-Auto Mode nodes ... cannot access the node-level DNS service that Auto Mode
# provides." The membership test is the documented label `eks.amazonaws.com/compute-type` = `auto`
# (docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html supported-label table;
# docs.aws.amazon.com/eks/latest/userguide/associate-workload.html).
# Fargate nodes are excluded from the denominator as everywhere else here. An empty EC2 set does NOT satisfy
# the gate ($t>0 is required): "all nodes are Auto Mode" must never be vacuously true. A mixed-mode or
# not-yet-migrated cluster falls through to MEASURING the nodelocaldns DaemonSet, and the final arm names the
# mix rather than printing a bare "none".
# ONE GATE, SPELLED BY 11 QUESTIONS: `($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t`. Find
# every copy with the command below (`-F` is REQUIRED: without it BSD grep, the macOS default, reads the
# mid-pattern `$` as an anchor and matches nothing):
#   grep -rnF '($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t' references/
# The 11 are lens-2 and lens-3 here; ope-10, ope-15, ope-16, lens-1 and lens-7 in
# references/operational-excellence.md; perf-6 in references/performance-efficiency.md; and sec-21, sec-30 and
# net-3 in references/security/identity-access.md. Some spell the gate on an `rl` line as well as an `m` line,
# so grep hits outnumber questions, and a comment quoting the pattern is matched by it too.
# CHANGE ONE, CHANGE ALL 11. Exceptions: rel-4 reads the cluster flag alone; sec-4 tests nodes. Each credits a
# capability Auto Mode delivers ON THE NODE, so each must ask about nodes, not `cluster.computeConfig.enabled`.
# DIFF THE CONDITION, NOT THE SURROUNDING BINDINGS: the quoted condition is byte-identical (some copies add
# conjuncts after it, e.g. `and $hy==0`); bindings differ by input (perf-6 reads `.`). Do not "align" them.
# Add-on half of the argument, quoted at ope-10: docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html.
# lens-2's FARGATE arm tests the NODE POPULATION, not the length of the DaemonSet list. The DaemonSet OBJECTS
# still exist on Fargate (kube-proxy, aws-node, CSI node DaemonSets with `desiredNumberScheduled: 0`), and
# docs.aws.amazon.com/eks/latest/userguide/fargate.html says "Daemonsets aren't supported on Fargate", so a
# list-length test would fail a missing nodelocaldns DaemonSet where deploying one is impossible. The
# `($any and $t==0 and $hy==0)` test and its detail `na~no DaemonSets possible on Fargate compute` match lens-1
# and ope-7 (which uses `$ec2==0`) in operational-excellence.md. `($any|not)` (no nodes at
# all) is a separate `na`. An EC2 cluster with no DaemonSets at all falls through to `none`: it HAS nodes that
# could carry a cache and does not.
m3 lens-2 daemonsets nodes cluster 'input as $n|input as $cl|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then "all~every \(if $w>0 then "Linux " else "" end)EC2 node is an EKS Auto Mode node (eks.amazonaws.com/compute-type=auto) and Auto Mode runs CoreDNS as a system service on each node, caching DNS queries on the node itself"+winx($w) elif ($any and $t==0 and $hy==0) then (if $w>0 then winna($w) else "na~no DaemonSets possible on Fargate compute" end) elif ($any|not) then "na~no nodes" elif ([.items[]|select(.metadata.name|test("nodelocaldns|node-local-dns"))|select((.status.numberReady|numbers)>0)]|length)>0 then "all~nodelocal dns"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy>0) then "none~Auto Mode caches DNS on each of the \($t) EC2 node(s) it runs, but the \($hy) EKS Hybrid Node(s) resolve through the cluster CoreDNS Deployment that AWS installs when a hybrid node joins, and no nodelocaldns DaemonSet caches for them"+winx($w) elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or $hy==0)) then "none~Auto Mode compute is enabled but \($auto) of \($t) EC2 nodes carry eks.amazonaws.com/compute-type=auto; the rest resolve through the CoreDNS Deployment, which they must keep, and no nodelocaldns DaemonSet caches for them"+winx($w) else "none~none"+winx($w) end'
# lens-3 ANSWERS `all` ON THE SAME ALL-NODES-AUTO GATE: on Auto Mode there is no CoreDNS Deployment to
# autoscale (auto-networking.html, quoted at lens-2), so DNS capacity tracks the node count, which Auto Mode
# itself autoscales (automode.html, quoted at rel-4). lens-2 already answers `all` on this fact; `none` here
# would contradict it, and the CoreDNS-autoscaler remediation is inapplicable. A mixed-mode cluster keeps a
# real CoreDNS Deployment, so it falls through to measuring the autoscaler.
# The `all` arm ALSO REQUIRES NO HYBRID AND NO FARGATE NODE (`$hy==0`, `$fg==0`): the gate counts EC2 nodes
# only. A hybrid node resolves through the cluster CoreDNS Deployment, and so does a Fargate Pod
# (managing-coredns.html -- "The CoreDNS Pods can be deployed to Fargate nodes if your cluster includes a
# Fargate Profile with a namespace that matches the namespace for the CoreDNS deployment"). So an all-Auto EC2
# fleet beside hybrid or Fargate nodes still measures the autoscaler, and its `none` arm names those nodes.
# The mixed-mode arm (`$auto` of `$t`) needs `($t>0 or ($hy==0 and $w==0))` so that a cluster whose zero EC2
# nodes are really Windows or hybrid nodes is not told "0 of 0 EC2 nodes are Auto Mode nodes".
m4 lens-3 deployments nodes addons cluster 'input as $n|input as $a|input as $cl|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|([$n.items[]?|select((ishy|not) and (isec2|not))]|length) as $fg|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0 and $fg==0) then "all~there is no CoreDNS Deployment to autoscale: Auto Mode runs CoreDNS as a node system service, so DNS capacity follows the node count, which Auto Mode scales itself"+winx($w) elif (([.items[]?|select((.metadata.namespace//"")=="kube-system" and (.metadata.name//"")=="coredns")]|length)>0) and ((($a.addonDetails)//[])|any((.addonName=="coredns") and (([(((.configurationValues//"")|tostring|fromjson?)//null)|objects|.autoScaling|objects|.enabled==true]|any)))) then "all~the EKS managed CoreDNS add-on autoscales itself: its configurationValues set autoScaling.enabled = true, so EKS adapts the replica count of the CoreDNS Deployment to the cluster\u2019s node and CPU count"+winx($w) elif ([.items[]|select(.metadata.name|test("dns-autoscaler|proportional-autoscaler"))|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~coredns autoscaler"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy>0) then "none~the \($t) EC2 node(s) resolve from Auto Mode\u2019s per-node CoreDNS, but the \($hy) EKS Hybrid Node(s) resolve through the cluster CoreDNS Deployment that AWS installs when a hybrid node joins, so that Deployment is still load-bearing and it has no autoscaler"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $fg>0) then "none~the \($t) EC2 node(s) resolve from Auto Mode\u2019s per-node CoreDNS, but Pods on the \($fg) Fargate node(s) get no node-local CoreDNS and need a cluster CoreDNS Deployment to resolve names"+(if ([.items[]?|select((.metadata.namespace//"")=="kube-system" and (.metadata.name//"")=="coredns")]|length)>0 then ", so that Deployment is still load-bearing and it has no autoscaler" else "; none (kube-system/coredns) is in the collected Deployments, so there is no Deployment here to autoscale and nothing those Pods can resolve through" end)+winx($w) elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or ($hy==0 and $w==0))) then "none~Auto Mode compute is enabled but \($auto) of \($t) EC2 nodes are Auto Mode nodes, so the CoreDNS Deployment the others depend on is still load-bearing and has no autoscaler"+winx($w) else "none~none"+winx($w) end'
# lens-14 SCORES NODE AZs, NOT A TOTAL: two gateways in ONE subnet beside nodes in two OTHER AZs are a single-AZ egress SPOF. AN AZ IS CREDITED ONLY WHEN
# EVERY NODE SUBNET IN IT HAS AN `active` 0.0.0.0/0 ROUTE (`NatGatewayId`) TO AN AVAILABLE PUBLIC GATEWAY SERVING THAT AZ; the table is the explicit
# association in state `associated`, else the main table. A NODE SUBNET is the one whose CIDR holds a Linux EC2 node's InternalIP, plus, with Fargate nodes,
# the AZ's Fargate profile subnets; a node in no collected subnet leaves its AZ uncredited (crediting ANY one would let a sibling subnet credit nodes that
# egress cross-AZ: a false Pass). A ZONAL gateway serves its subnet's AZ. A REGIONAL gateway (`AvailabilityMode` `regional`, or no `SubnetId`) spans AZs and
# is CREDITED FOR EXACTLY THE AZs WHERE `NatGatewayAddresses[]` holds an address in `Status` `succeeded` (an address giving only
# `AvailabilityZoneId` is mapped to its AZ through the collected subnets; an ID no subnet carries credits
# nothing). Crediting any other AZ would be a false Pass. A regional gateway whose addresses name no AZ may
# serve any AZ and cannot be credited: when it is available and a node AZ is left uncovered, the answer is
# `na` opening `NOT ASSESSED`.
# A PRIVATE NAT GATEWAY (`ConnectivityType` `private`) IS CREDITED FOR NO AZ: it gives no internet egress. It
# is left out of the available count, the detail says how many, and `context` names each one. A GATEWAY WHOSE
# SUBNET IS NOT IN THE COLLECTED VPC DATA COVERS NOTHING and is named as unresolved in `context`.
# The `rl` SPLITS ON THE NODE AZs THE VERDICT COUNTS, because the detail leads with `n/m` and the report
# cross-checks the list against it. Every gateway is named in `context` with its state AND AZ, so a
# `deleting`, `failed` or `pending` gateway never looks like egress capacity. The AZs carry the verdict's
# `//empty` (an unlabelled node is not an extra AZ) and its AZ set `$azs` (see rel-1's ready/cordoned note).
# A FARGATE NODE'S ZONE LABEL IS NOT COUNTED, for rel-1's reason: when any Fargate node exists the AZ
# population takes the AZs of the Fargate profiles' subnets (same join as rel-1) plus the Linux EC2 node AZs;
# Fargate accepts only private subnets, so their egress goes through a NAT gateway. When profiles resolve to
# no AZ and no EC2 node AZ remains, the answer is `na` opening `NOT ASSESSED`, worded without the words
# `NA_STRUCTURAL` treats as structural, because it is a collection gap.
rl lens-14 nat nodes subnets fargateprofiles routetables 'def _rs: ([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0) and ((.spec.unschedulable//false)!=true);input as $n|input as $sn|input as $fp|input as $rt|[$sn.Subnets[]?] as $subs|[.NatGateways[]?] as $g|def isreg: ((.AvailabilityMode//"")=="regional" or ((.SubnetId//"")==""));def ispriv: ((.ConnectivityType//"")=="private");def regaz: [.NatGatewayAddresses[]?|select(.Status=="succeeded")|(if ((.AvailabilityZone|type)=="string" and .AvailabilityZone!="") then .AvailabilityZone else (.AvailabilityZoneId//"") as $zid|([$subs[]|select($zid!="" and .AvailabilityZoneId==$zid)|.AvailabilityZone//empty]|first) end)|strings]|unique;[$g[]|select(.State=="available" and (ispriv|not))] as $up|([$g[]|select(.State=="available" and ispriv)]|length) as $pv|[$up[]|select(isreg)] as $reg|[$reg[]|select((regaz|length)==0)] as $regx|def gaz: . as $gw|if ($gw|isreg) then ($gw|regaz) else [$subs[]|select(.SubnetId==($gw.SubnetId//""))|.AvailabilityZone//empty] end;def dnat: .SubnetId as $sid|(([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid and (.AssociationState.State//"associated")=="associated")]|length>0)]|first)//([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true and (.AssociationState.State//"associated")=="associated")]|length>0)]|first)) as $tbl|[$tbl.Routes[]?|select(.DestinationCidrBlock=="0.0.0.0/0" and .State=="active")|.NatGatewayId//empty];def ip4: (split(".")|map(tonumber? // -1)) as $o|if ($o|length)==4 and ([$o[]|select(.>=0 and .<256)]|length)==4 then $o[0]*16777216+$o[1]*65536+$o[2]*256+$o[3] else empty end;def inc($i): ((.CidrBlock//"")|split("/")) as $c|(($c[1]//"")|tonumber? // 99) as $p|if $p<0 or $p>32 then false else (($c[0]//"")|ip4) as $s|(reduce range(32-$p) as $k (1;.*2)) as $q|(($i/$q)|floor)==(($s/$q)|floor) end;def nsn: [.status.addresses[]?|select(.type=="InternalIP")|.address|strings|ip4] as $ips|[$subs[]|select(. as $s|any($ips[];. as $i|$s|inc($i)))];[$n.items[]|select(isec2)] as $nh|([$n.items[]|select((ishy|not) and (isec2|not))]|length) as $fgn|(($fp.profiles)//[]) as $profs|([$profs[]?|(.subnets//[])[]]|unique) as $fpsub|(if $fgn>0 then ([$subs[]|select(.SubnetId as $id|$fpsub|index($id))|.AvailabilityZone//empty]|unique) else [] end) as $fz|[$nh[]|select(iswin|not)] as $le|def zs($z): [$le[]|select((.metadata.labels["topology.kubernetes.io/zone"]//"")==$z)|nsn|if length==0 then null else .[] end]+(if ($fz|index($z))!=null then [$subs[]|select((.AvailabilityZone//"")==$z and (.SubnetId as $id|$fpsub|index($id)))] else [] end);def zok($z): zs($z) as $ss|($ss|length)>0 and all($ss[];(.!=null) and (dnat as $d|any($up[];(.NatGatewayId//"?") as $gi|(($d|index($gi))!=null) and ((gaz|index($z))!=null))));([$le[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]+$fz|unique|map(select(. as $z|zok($z)))) as $natz|[$nh[]|select(iswin)] as $wn|($wn|length) as $w|[$nh[]|select((iswin|not) and (_rs|not))] as $lx|($lx|length) as $x|([$nh[]|select((iswin|not) and _rs)|.metadata.labels["topology.kubernetes.io/zone"]//empty]+$fz|unique) as $rz|([$lx[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique|map(select(. as $z|($rz|index($z))==null))) as $lxz|[$lxz[]|select(. as $z|($natz|index($z))!=null)] as $xz|[$lxz[]|select(. as $z|($natz|index($z))==null)] as $xk|((($rz+$xk)|length)==0 and ($xz|length)>0) as $xg|(if $xg then $xz else ($rz+$xk|unique) end) as $azs|([$wn[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique|map(select(. as $z|(($azs+$xz)|index($z))==null))) as $wz|def rnote: . as $gw|[$natz[] as $z|select((($gw|gaz|index($z))!=null) and any(zs($z)[];(.!=null) and ((dnat|index($gw.NatGatewayId//"?"))!=null)))|$z] as $c|if ($c|length)>0 then "credited for "+($c|join(", "))+", where node subnets route 0.0.0.0/0 to it" else "credited for no node AZ: an AZ is credited only when every node subnet in it routes 0.0.0.0/0 to an available gateway serving it" end;def ctx: . as $gw|($gw.NatGatewayId//"?")+" ("+($gw.State//"?")+", "+(if ($gw|ispriv) then (if ($gw|isreg) then "regional" else (([$subs[]|select(.SubnetId==($gw.SubnetId//""))|.AvailabilityZone//"?"]|first)//"AZ not resolved from the collected VPC subnet data") end)+", private: no internet egress, so credited for no AZ" elif ($gw|isreg) then ($gw|regaz) as $ra|(if ($gw.State//"")!="available" then "regional: not available, so credited for no AZ" elif ($ra|length)>0 then "regional: holds an egress address in status succeeded in "+($ra|join(", "))+"; "+($gw|rnote) else "regional: no egress address in status succeeded names an AZ, so credited for no AZ" end) else (([$subs[]|select(.SubnetId==($gw.SubnetId//""))|.AvailabilityZone//"?"]|first)//"AZ not resolved from the collected VPC subnet data")+(if ($gw.State//"")=="available" then "; "+($gw|rnote) else "" end) end)+")";if (($nh|length)>0 and ($nh|length)==$w and $fgn==0) or (($regx|length)>0 and ([$azs[]|select(. as $z|($natz|index($z))==null)]|length)>0) then {pass:[],fail:[],context:[$g[]|ctx],context_only:true} else {pass:[$azs[]|select(. as $z|($natz|index($z))!=null)|.+" (every node subnet in this AZ routes 0.0.0.0/0, by an active route, to an available NAT gateway serving this AZ)"],fail:[$azs[]|select(. as $z|($natz|index($z))==null)|.+(if $pv>0 then " (not every node subnet in this AZ routes 0.0.0.0/0, by an active route, to an available public NAT gateway serving this AZ, or a node here is in no collected subnet)" else " (not every node subnet in this AZ routes 0.0.0.0/0, by an active route, to an available NAT gateway serving this AZ, or a node here is in no collected subnet)" end)],context:[$g[]|ctx]} end'
m5 lens-14 nat nodes subnets fargateprofiles routetables 'def _rs: ([.status.conditions[]?|select(.type=="Ready" and .status=="True")]|length>0) and ((.spec.unschedulable//false)!=true);input as $n|input as $sn|input as $fp|input as $rt|[$sn.Subnets[]?] as $subs|[.NatGateways[]?] as $g|def isreg: ((.AvailabilityMode//"")=="regional" or ((.SubnetId//"")==""));def ispriv: ((.ConnectivityType//"")=="private");def regaz: [.NatGatewayAddresses[]?|select(.Status=="succeeded")|(if ((.AvailabilityZone|type)=="string" and .AvailabilityZone!="") then .AvailabilityZone else (.AvailabilityZoneId//"") as $zid|([$subs[]|select($zid!="" and .AvailabilityZoneId==$zid)|.AvailabilityZone//empty]|first) end)|strings]|unique;[$g[]|select(.State=="available" and (ispriv|not))] as $up|([$g[]|select(.State=="available" and ispriv)]|length) as $pv|[$up[]|select(isreg)] as $reg|[$reg[]|select((regaz|length)==0)] as $regx|def gaz: . as $gw|if ($gw|isreg) then ($gw|regaz) else [$subs[]|select(.SubnetId==($gw.SubnetId//""))|.AvailabilityZone//empty] end;def dnat: .SubnetId as $sid|(([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid and (.AssociationState.State//"associated")=="associated")]|length>0)]|first)//([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true and (.AssociationState.State//"associated")=="associated")]|length>0)]|first)) as $tbl|[$tbl.Routes[]?|select(.DestinationCidrBlock=="0.0.0.0/0" and .State=="active")|.NatGatewayId//empty];def ip4: (split(".")|map(tonumber? // -1)) as $o|if ($o|length)==4 and ([$o[]|select(.>=0 and .<256)]|length)==4 then $o[0]*16777216+$o[1]*65536+$o[2]*256+$o[3] else empty end;def inc($i): ((.CidrBlock//"")|split("/")) as $c|(($c[1]//"")|tonumber? // 99) as $p|if $p<0 or $p>32 then false else (($c[0]//"")|ip4) as $s|(reduce range(32-$p) as $k (1;.*2)) as $q|(($i/$q)|floor)==(($s/$q)|floor) end;def nsn: [.status.addresses[]?|select(.type=="InternalIP")|.address|strings|ip4] as $ips|[$subs[]|select(. as $s|any($ips[];. as $i|$s|inc($i)))];[$n.items[]|select(isec2)] as $nh|([$n.items[]|select((ishy|not) and (isec2|not))]|length) as $fgn|(($fp.profiles)//[]) as $profs|([$profs[]?|(.subnets//[])[]]|unique) as $fpsub|(if $fgn>0 then ([$subs[]|select(.SubnetId as $id|$fpsub|index($id))|.AvailabilityZone//empty]|unique) else [] end) as $fz|[$nh[]|select(iswin|not)] as $le|def zs($z): [$le[]|select((.metadata.labels["topology.kubernetes.io/zone"]//"")==$z)|nsn|if length==0 then null else .[] end]+(if ($fz|index($z))!=null then [$subs[]|select((.AvailabilityZone//"")==$z and (.SubnetId as $id|$fpsub|index($id)))] else [] end);def zok($z): zs($z) as $ss|($ss|length)>0 and all($ss[];(.!=null) and (dnat as $d|any($up[];(.NatGatewayId//"?") as $gi|(($d|index($gi))!=null) and ((gaz|index($z))!=null))));([$le[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]+$fz|unique|map(select(. as $z|zok($z)))) as $natz|[$nh[]|select(iswin)] as $wn|($wn|length) as $w|[$nh[]|select((iswin|not) and (_rs|not))] as $lx|($lx|length) as $x|([$nh[]|select((iswin|not) and _rs)|.metadata.labels["topology.kubernetes.io/zone"]//empty]+$fz|unique) as $rz|([$lx[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique|map(select(. as $z|($rz|index($z))==null))) as $lxz|[$lxz[]|select(. as $z|($natz|index($z))!=null)] as $xz|[$lxz[]|select(. as $z|($natz|index($z))==null)] as $xk|((($rz+$xk)|length)==0 and ($xz|length)>0) as $xg|(if $xg then $xz else ($rz+$xk|unique) end) as $azs|([$wn[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique|map(select(. as $z|(($azs+$xz)|index($z))==null))) as $wz|(if $fgn>0 and ($fz|length)>0 then " — the AZ count takes the \($fz|length) AZ(s) of the subnets the \($profs|length) Fargate profile(s) launch Pods into, not the zone labels of the \($fgn) Fargate node(s), which record only where a Pod happened to land" elif $fgn>0 then " — the \($fgn) Fargate node(s) are not in that count: their zone labels record only where a Pod happened to land, and their profiles\u2019 subnets did not resolve to an AZ in the collected data" else "" end) as $fgx|(if ($wz|length)>0 then " — \($wz|length) AZ(s) where only Windows nodes run are not in that count: \($wz|join(", "))" else "" end) as $wzx|(if $x>0 then " — \($x) Linux EC2 node(s) are NotReady or cordoned (spec.unschedulable), so the scheduler places no new workload Pod on them (DaemonSet Pods excepted)"+(if $xg then "; no other node AZ is left, so the count is taken over the \($xz|length) AZ(s) where they run, each of which is credited with NAT egress (every node subnet there routes 0.0.0.0/0 to an available public NAT gateway serving it) for the Pods already on those nodes: \($xz|join(", "))" elif ($xz|length)>0 then ", and earn their AZ no credit; \($xz|length) AZ(s) with such nodes but no Ready, uncordoned Linux EC2 node, and credited with NAT egress, are left out of that count: \($xz|join(", "))" else "" end)+(if ($xk|length)>0 then "; \($xk|length) AZ(s) with such nodes but no Ready, uncordoned Linux EC2 node, and not credited with NAT egress, stay in that count, because the Pods already on those nodes, and DaemonSet Pods, may still need egress: \($xk|join(", "))" else "" end) else "" end) as $xzx|($up|length) as $nat|($azs|length) as $az|([$azs[]|select(. as $z|($natz|index($z))!=null)]|length) as $ok|([$n.items[]|select(ishy)]|length) as $hy| if (($nh|length)>0 and ($nh|length)==$w and $fgn==0) then winna($w)+hyx($hy) elif (($az==0) and ([$n.items[]|select(ishy|not)]|length)==0 and $hy>0) then hyna($hy;"a NAT gateway gives nodes inside a VPC subnet egress to the internet, and a hybrid node egresses through the network the operator runs rather than through this VPC, so per-AZ NAT redundancy does not describe it") elif ($az==0 and $x>0) then "na~NOT ASSESSED — no Linux EC2 node names an AZ: none of them carries a topology.kubernetes.io/zone label, so there is no node AZ to compare the NAT gateways against; NotReady or cordoned (spec.unschedulable): \($x) of the \([$nh[]|select(iswin|not)]|length), so the scheduler places no new workload Pod on them (DaemonSet Pods excepted)"+$fgx+hyx($hy)+winx($w)+$wzx elif ($az==0 and $fgn>0) then "na~NOT ASSESSED: the only Linux VPC nodes here are created per Pod, so their zone labels record where one Pod happened to land rather than where the cluster is able to place Pods; the AZs this check scores for them are those of the subnets their compute profiles name, and \(if ($fpsub|length)==0 then "the collected profile detail carries none" else "none of the \($fpsub|length) subnet(s) it carries appears in the collected VPC subnet data" end) — collect the per-profile detail and re-run"+hyx($hy)+winx($w) elif $az==0 then "na~no nodes"+winx($w) elif ($regx|length)>0 and $ok<$az then "na~NOT ASSESSED — \($az - $ok) of \($az) node AZ(s) have no available NAT gateway credited to them, and \($regx|length) available regional NAT gateway(s) may serve them: a regional NAT gateway is credited for an AZ only where it holds an egress address in status succeeded, and none of their collected addresses in status succeeded names an AZ, so their egress redundancy cannot be judged here"+$fgx+$xzx+hyx($hy)+winx($w)+$wzx else b($ok;$az)+"~\($ok)/\($az) node AZ(s) where every node subnet routes 0.0.0.0/0, by an active route, to an available \(if $pv>0 then "public " else "" end)NAT gateway serving that AZ (a node subnet is the collected subnet whose CIDR holds a Linux EC2 node\u2019s InternalIP\(if ($fz|length)>0 then ", or a Fargate profile subnet in an AZ the profiles name" else "" end); an AZ with a node in no collected subnet is not credited; \($nat) available \(if $pv>0 then "public " else "" end)gateway(s)"+(if ($reg|length)>0 then "; \($reg|length) of them regional, each credited only for the AZs where it holds an egress address in status succeeded" else "" end)+(if $pv>0 then "; \($pv) available private gateway(s) not counted: a private NAT gateway gives no internet egress" else "" end)+")"+$fgx+$xzx+hyx($hy)+winx($w)+$wzx end'
# lens-15 -- a subnet is PRIVATE when its route table has no route to an internet gateway. AWS: "You can explicitly associate a subnet
# with a particular route table. Otherwise, the subnet is implicitly associated with the main route table." So the MAIN-TABLE FALLBACK
# is required: an implicitly-associated subnet returns an EMPTY association list, and a lookup without the fallback calls every such
# subnet not-private (wrong wherever the main table is private). This tests the route table, not MapPublicIpOnLaunch, which is only a
# proxy: a subnet can have it false and still route 0.0.0.0/0 to an IGW, a false PASS on a weight-3 question. A subnet whose table
# cannot be resolved counts as NOT private: never claim private without evidence. An association counts only in state `associated` (a
# `disassociated` one no longer routes the subnet, which falls back to the main table).
# lens-15 EMITS `excluded`, AND IT HAS TO: the subnets it drops are registered to something else, and the
# report does not publish their identifiers, so the disclosure is a COUNT. NEVER put a subnet id in that key.
# lens-15 SCORES WHERE THE NODES ACTUALLY ARE. Reading `resourcesVpcConfig.subnetIds` alone would never
# examine a node launched elsewhere (a managed node group with other `--subnets`, or a Karpenter `EC2NodeClass`
# selecting public subnets by tag), so `instances.json` is an input.
# THE DENOMINATOR IS THE NODE SUBNETS, NOT THEIR UNION WITH THE REGISTERED ONES: registered-but-node-free
# subnets would land in the NUMERATOR, so nine private registered subnets with every node in one public subnet
# would publish `all~9/10 private`, a PASS, with the public subnet in `fail` underneath.
# THE REGISTERED SUBNETS ARE A FALLBACK, NOT A SECOND POPULATION: with no node instance collected the
# denominator would be zero and the question vacuously `na`, and a missing collection is not a finding. Score
# the node subnets when there are any, else the registered ones, else every subnet in the file; the detail
# NAMES which. TERMINATED AND SHUTTING-DOWN INSTANCES ARE NOT NODES (no ENI in any subnet).
# A SCORED SUBNET NOT IN THE COLLECTED VPC DATA IS DISCLOSED, NOT DROPPED: counted and named in `context`.
# When NONE resolves the question answers `na` and says so, avoiding the words `fargate`, `impossible`,
# `serverless compute` and `no EC2 nodes`: render-report.py's `NA_STRUCTURAL` would subtract it from the
# thin-evidence denominator, but this is a COLLECTION GAP and must keep counting against coverage.
# THE LIST MUST FOLLOW THE SAME THREE POPULATIONS AS THE VERDICT.
rl lens-15 subnets cluster routetables instances nodes 'input as $cl|input as $rt|input as $inst|input as $nd|[$nd.items[]?] as $nds|([$nds[]|select(isec2)]|length) as $ne|(($cl.cluster.resourcesVpcConfig.subnetIds|arrays)//[]) as $own|[$inst.Reservations[]?.Instances[]?|select((((.State.Name)//"")|IN("terminated","shutting-down"))|not)] as $live|[$live[]|select(((.Platform//"")|ascii_downcase)=="windows")] as $wi|($wi|length) as $w|([$live[]|select(((.Platform//"")|ascii_downcase)!="windows")|.SubnetId//empty]|unique) as $nodesn|([$wi[]|.SubnetId//empty]|unique|map(select(. as $x|($nodesn|index($x))==null))) as $wsub|(if ($nodesn|length)>0 then $nodesn else $own end) as $scope|[.Subnets[]?] as $subs|([$scope[]|select(. as $id|([$subs[]|select(.SubnetId==$id)]|length)==0)]|length) as $unres|[$subs[]|select(($scope|length)==0 or (.SubnetId as $id|$scope|index($id)))] as $s|([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true and (.AssociationState.State//"associated")=="associated")]|length>0)]|first) as $main|[$s[]|select(.SubnetId as $sid|((([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid and (.AssociationState.State//"associated")=="associated")]|length>0)]|first)) // $main) as $tbl|($tbl!=null) and (([$tbl.Routes[]?|select((.GatewayId//"")|startswith("igw-"))]|length)==0))] as $p|def n: (.SubnetId//"?")+" ("+(.AvailabilityZone//"?")+", "+((.AvailableIpAddressCount//"?")|tostring)+" free IPs)";if ($nodesn|length)==0 and $w>0 then {pass:[],fail:[],context:(["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+[$wi[]|.InstanceId//"?"]),context_only:true} elif ($nodesn|length)==0 and ($nds|length)>0 and $ne==0 then {pass:[],fail:[],context:(["\($nds|length) node(s) and none an EC2 node, so no subnet is scored"]+[$nds[]|.metadata.name//"?"]),context_only:true} else {pass:[$p[]|n],fail:[($s-$p)[]|n],context:((if $unres>0 then ["\($unres) subnet(s) in this check'"'"'s population are not in the collected VPC subnet data, so no route table could be read for them and they are NOT in the ratio above (identifiers omitted)"] else [] end)+(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+[$wi[]|.InstanceId//"?"] else [] end)+(if ($wsub|length)>0 then ["\($wsub|length) subnet(s) are used only by those Windows node(s), so they left this check'"'"'s population and are among the excluded subnet(s) (identifiers omitted)"] else [] end)),excluded:(($subs|length)-($s|length))} end'
m5 lens-15 subnets cluster routetables instances nodes 'input as $cl|input as $rt|input as $inst|input as $nd|[$nd.items[]?] as $nds|([$nds[]|select(isec2)]|length) as $ne|([$nds[]|select(ishy)]|length) as $nh|(($cl.cluster.resourcesVpcConfig.subnetIds|arrays)//[]) as $own|[$inst.Reservations[]?.Instances[]?|select((((.State.Name)//"")|IN("terminated","shutting-down"))|not)] as $live|[$live[]|select(((.Platform//"")|ascii_downcase)=="windows")] as $wi|($wi|length) as $w|([$live[]|select(((.Platform//"")|ascii_downcase)!="windows")|.SubnetId//empty]|unique) as $nodesn|([$wi[]|.SubnetId//empty]|unique|map(select(. as $x|($nodesn|index($x))==null))) as $wsub|(if ($nodesn|length)>0 then $nodesn else $own end) as $scope|[.Subnets[]?] as $subs|([$scope[]|select(. as $id|([$subs[]|select(.SubnetId==$id)]|length)==0)]|length) as $unres|(if ($scope|length)==0 then "every subnet in the collected VPC data: the cluster registers none and no node instance was collected" elif ($nodesn|length)>0 then "the \($nodesn|length) subnet(s) the collected \(if $w>0 then "Linux " else "" end)node instances are actually in" else "the \($own|length) subnet(s) the cluster registers, no node instance having been collected" end) as $pop|[$subs[]|select(($scope|length)==0 or (.SubnetId as $id|$scope|index($id)))] as $s|([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true and (.AssociationState.State//"associated")=="associated")]|length>0)]|first) as $main|($s|length) as $t|([$s[]|.SubnetId as $sid|select(((([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid and (.AssociationState.State//"associated")=="associated")]|length>0)]|first)) // $main) as $tbl|($tbl!=null) and (([$tbl.Routes[]?|select((.GatewayId//"")|startswith("igw-"))]|length)==0))]|length) as $ok| if (($nodesn|length)==0 and $w>0) then winna($w) elif ($nodesn|length)==0 and ($nds|length)>0 and $ne==0 then "na~no EC2 nodes — the \($nds|length) node(s) here are "+([(if ($nds|length)>$nh then "\(($nds|length)-$nh) Fargate node(s), which run only in the subnets of a Fargate profile, and a Fargate profile accepts only private subnets with no direct route to an Internet Gateway" else empty end),(if $nh>0 then "\($nh) EKS Hybrid Node(s), which run on-premises, outside the VPC" else empty end)]|join("; and "))+". No worker node can sit in a public subnet, so the subnets the cluster registers are not scored in its place" elif $t==0 then (if $unres>0 then "na~NOT ASSESSED: none of the \($unres) subnet(s) this check would have scored is in the collected VPC subnet data, so no route table could be read for any of them — collect the VPC subnets and re-run" else "na~no node or cluster subnets to score" end) else b($ok;$t)+"~\($ok)/\($t) private (no IGW route, scored over \($pop))"+(if $unres>0 then " — \($unres) further subnet(s) in that population are not in the collected VPC subnet data and could not be scored" else "" end)+winx($w)+(if ($wsub|length)>0 then " — \($wsub|length) subnet(s) used only by Windows nodes are not in that population" else "" end) end'
```

**Governance (not assessed):** rel-10/rel-12 (volume snapshot/backup policy), rel-14
(HA ingress controller), rel-15 (LoadBalancer usage), rel-17 (CoreDNS/External DNS strategy).

---

## Stop guessing capacity

### rel-1: Are worker nodes deployed across multiple Availability Zones?

**Detection:** 🔬 AUTO-DETECTABLE

> Multi-AZ deployment ensures the cluster survives an AZ failure. A node counts toward an AZ, or toward a
> hybrid fault domain, only when its `Ready` condition is `True` and it is not cordoned (`spec.unschedulable`):
> the scheduler places no new workload Pod on a NotReady or cordoned node (DaemonSet Pods excepted), so an AZ
> that only such a node occupies gives the cluster no place to reschedule into when another AZ fails. The detail says how many nodes were left out,
> and the resource list names each one with its reason and zone.
> **On a cluster with no EC2 nodes, this is answered from the Fargate profiles, not from node labels.**
> A Fargate node is not a machine anyone placed: AWS documents that Fargate "provides pod isolation by
> scheduling one pod per node in a Kubernetes cluster", so `kubectl get nodes` lists one throwaway node per
> running Pod and its zone label records where that Pod happened to land. The durable fact is the profile —
> "Amazon EKS and Fargate spread Pods across each of the subnets that's defined in the Fargate profile" —
> so the scorer maps the profiles' subnet ids to AZs through the already-collected VPC subnet list.
> **EKS Hybrid Nodes:** An EKS Hybrid Node has no AWS Availability Zone. AWS documents setting `topology.kubernetes.io/zone` from the kubelet on a hybrid node (`--node-labels=topology.kubernetes.io/zone=dc1`) so that topology-aware scheduling and Pod topology spread constraints work, so on a hybrid fleet this question grades the fault domains the operator has declared — and answers `none` when not one node declares any, because that is a gap to close rather than a question that cannot apply.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get nodes -L eks.amazonaws.com/compute-type -o json
# EC2 nodes (compute-type != fargate): count unique topology.kubernetes.io/zone labels; 3+ -> all.
# Fargate nodes are excluded from that count, and so is any node that is not Ready
# (.status.conditions[] type Ready, status True) or is cordoned (.spec.unschedulable true).

# If there are NO EC2 nodes, read the profiles instead — one call per profile:
aws eks describe-fargate-profile --cluster-name <CLUSTER> --fargate-profile-name <PROFILE> \
  --region <REGION> --query 'fargateProfile.subnets'
aws ec2 describe-subnets --subnet-ids <ID_1> <ID_2> <ID_3> --region <REGION> \
  --query 'Subnets[].{Subnet:SubnetId,AZ:AvailabilityZone}'
# 3+ distinct AZs across the union of every profile's subnets -> all.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- no EC2 nodes but at least one Fargate profile → count the AZs of the profiles' subnets, not the nodes' zone labels
- no EC2 nodes and the profiles resolve to no AZ (no `subnets` collected, or ids absent from `subnets.json`) → `na~NOT ASSESSED`; the scorer does not fall back to node labels, because that is the measurement this rule exists to distrust

**Remediation:** If the detail says nodes were not counted, the AZ they sit in may already be the one you
are missing: a cordoned node takes Pods again after `kubectl uncordon <NODE>`, and a NotReady node needs
its kubelet, network or instance fixed, or the node replaced. The rest of this section is for an AZ that has
no node at all.

Which fix is correct depends on the compute the cluster runs, and on an Auto Mode cluster
the node-group answer is the wrong one. On an **EKS Hybrid Nodes** cluster none of the node-group answers
applies at all — a hybrid node cannot be in a node group and has no AWS Availability Zone to add capacity
in — so read that subsection first if the verdict named hybrid nodes.

**EKS Hybrid Nodes** — declare the fault domain, do not create a node group. There is no AZ to spread
across; what the cluster is missing is the operator's own topology, which nothing populates automatically
because a hybrid node runs no cloud-controller-manager. Set it from the kubelet when `nodeadm` joins the
node, using whatever your real failure boundary is — rack, room, building, site:

```yaml
# nodeadm config (nodeConfig), per node or per group of nodes sharing a failure domain
apiVersion: node.eks.aws/v1alpha1
kind: NodeConfig
spec:
  kubelet:
    flags:
      - --node-labels=topology.kubernetes.io/zone=dc1
```

Then spread the workload across those domains — the label alone changes nothing until something schedules
on it (`topologySpreadConstraints` with `topologyKey: topology.kubernetes.io/zone`, which is `rel-9`).
**Three or more distinct values across nodes that really are in separate failure domains** score `all`; two
score `most` and one scores `none`. Inventing distinct values for nodes that share one failure domain earns
the same credit while leaving the cluster exactly as fragile, and nothing in this review can detect that.

**Managed or self-managed node groups** — add capacity in the missing zones. `--cluster` is mandatory; without it
the command fails with
`Error: couldn't create node group filter from command line options: --cluster must be set`:

```bash
# --subnet-ids takes SUBNET IDS — one private subnet per AZ — not AZ names.
# (--node-zones is the flag that takes zone names; it is inherited from the cluster when omitted.)
eksctl create nodegroup --cluster <CLUSTER> --region <REGION> --name <NEW_NODEGROUP> \
  --subnet-ids <subnet-in-az-a>,<subnet-in-az-b>,<subnet-in-az-c>
```

**This only ADDS capacity — it does not move the nodes you already have.** A node group's subnets cannot be
changed in place, so the single-AZ group stays exactly where it is and the cluster is simply larger until
you finish the cutover: create the new group, confirm workloads can actually schedule onto it (zonal spread
is `rel-9`'s job — replicas do not redistribute themselves), then drain and delete the old group.

**EKS Auto Mode — do NOT add node-group capacity for this.** What withdraws the every-EC2-node-is-Auto-Mode
credit is **the first node-group node that REGISTERS, not the node group object**: every question gated on
it tests the NODE POPULATION — `computeConfig.enabled==true and $t>0 and $auto==$t`, "every EC2 node is an
Auto Mode node" — so a node group created with `desiredSize 0`, or any moment before its first node joins,
costs nothing whatever: no record and no pillar score changes while the group has no node. The price
arrives with the node.
Once one node-group node joins, the questions Auto Mode was answering through its platform-provided
checks are measured on the node population instead, and the Operational Excellence and Reliability
scores drop wherever those measurements fail, because those two pillars hold most of the questions the gate credits.
Performance Efficiency can move either way (`perf-6`, below). **Security can move wherever one of its measured questions
changes answer once the node joins**, `na` included, as an `na` leaves the weighted mean: an IMDSv2-optional node group
lowers `lens-11`; `sec-6`, if only Pod Identity credited it, goes `na` with no ready `eks-pod-identity-agent` DaemonSet. Losing the credit is
not the same as losing the question. The gated questions change like this: `ope-10`, `ope-16`, `lens-1`, `lens-2`, `lens-3`
and `lens-7` are measured instead, and fail on a cluster that left those jobs to Auto Mode, and `perf-6` — which answers `na` for as long as every EC2 node is an Auto
Mode node, because then AWS chose every instance type and there is no operator decision to grade, not
because a node group object is missing — becomes measurable. `net-3` loses its Auto Mode clause and keeps its own
measurement, as `sec-30` does once it loses the credit.
`ope-15` stays `all` (a node-group node is AWS-managed too) and `sec-21` stays measured; neither turns on
a credit being withdrawn: `ope-15`'s mixed-mode arm still counts as a platform credit, and `sec-21` never
counted as one, because its detail opens with a measured ratio and the report's credit rule excludes those.

**`perf-6` is the one question here that can pay OR cost, and one number decides which: how many DISTINCT
instance types the cluster ends up running.** `perf-6` collects `node.kubernetes.io/instance-type` from
every EC2 node, Auto Mode nodes included, and counts the values with `unique` — so what it sees is the
**union** of the types the fleet already runs and the types the node group adds. A node group that repeats a
type already running contributes nothing to that union, and neither does a node with no instance type to
read — the label absent, or present and empty, is dropped either way, so such a node added to a one-type
fleet still leaves `perf-6` at `1 type`. Three or more distinct types is a Pass, two is
Mostly, one is Partial. **That is the whole rule, and it is the rule rather than a list of cases on
purpose: state it any other way and it acquires an exception.** Read your own two numbers into it —
the types already running, and the types the new group would add that are not among them.

On a fleet that runs a single type the arithmetic usually comes out as a cost: one added
node of that same type keeps the union at one and adds a Partial `perf-6` answer to Performance
Efficiency where there was an `na`; one added node of a type not already running takes the union to two
and reaches Mostly. **Whenever the union reaches three, `perf-6` PASSES.** The near misses stop short
of that — a two-type fleet plus a node-group node repeating one of its types,
and a one-type fleet plus a two-type node group one of whose types was already running, both stop at two,
which is Mostly.

**`perf-6` passing is NOT the same as the pillar rising.** Whether Performance Efficiency rises depends on the added types being
CURRENT-generation. **`perf-3` scores the very same node population** — the same `isec2` set — and fails any
node whose instance family is on the dated previous-generation and retired list its own detection carries,
which this report prints verbatim with `perf-3` rather than restating here, so reaching three types with a
family on that list can cost more on `perf-3` than it gains on `perf-6`. On a one-type fleet running none of the listed families,
each of these two-node groups takes `perf-6` to Pass at `3 types`, and `perf-3` goes three
different ways:

- `m7i.large` + `r7i.large` — neither family is on `perf-3`'s list, so both new nodes pass `perf-3`.
- `p3.2xlarge` + `g4dn.xlarge` — `p3` is on the list and `g4dn` is not, so `perf-3` gains one failing node.
- `p3.2xlarge` + `g3.4xlarge` — both families are on the list, so `perf-3` gains two failing nodes.
- `m4.large` + `c4.large` — the same: both families are on the list, two failing nodes on `perf-3`.

A GPU node group is the ordinary case here rather than an exotic one — it is what gets added for ML, and
`perf-6`'s own advice is what prompts the node group in the first place. So diversify with
current-generation families if you diversify at all, and do not read `perf-6` as an argument in either
direction: it is neither a reason to add the capacity nor a reason not to.

So the price is concentrated in Operational Excellence and Reliability, and you would pay it for a fix that
was not needed. How much it is depends on the rest of your cluster's answers.
Adjust the NodePool and NodeClass instead:

```bash
kubectl get nodepool -o custom-columns=NAME:.metadata.name,CLASS:.spec.template.spec.nodeClassRef.name
kubectl get nodepool <NAME> -o jsonpath='{.spec.template.spec.requirements}' | jq .
kubectl get nodeclass <NAME> -o jsonpath='{.spec.subnetSelectorTerms}' | jq .
```

Then, in order of what is actually wrong:

1. **A NodePool pinned to too few zones** — a `topology.kubernetes.io/zone` requirement with `operator: In`
   and two values can only ever produce two AZs. Widen the `values` list.
2. **A NodeClass whose `subnetSelectorTerms` resolve inside fewer than 3 AZs** — tag one private subnet per
   AZ (or list the ids) so the selector reaches all three. AWS: "If there are multiple subnets that match
   the `subnetSelectorTerms` conditions or that you provide by ID, EKS Auto Mode creates nodes distributed
   across the subnets." Note that the built-in class cannot be edited — "In EKS Auto Mode, the bundled
   `default` NodeClass is read-only, so create a custom NodeClass ... then update the NodePool to point at
   the NodeClass" — and do not name your own class `default`.
3. **Both already span 3 AZs and the nodes still do not** — then the node configuration is not the gap and
   changing it will not help. karpenter.sh/docs/concepts/scheduling: "NodePools do not attempt to balance or
   rebalance the availability zones for their nodes. Availability zone balancing may be achieved by defining
   zonal Topology Spread Constraints for Pods that require multi-zone durability, and NodePools will respect
   these constraints while optimizing for compute costs." So the fix is on the workloads — see `rel-9` — and
   Auto Mode will provision the nodes the constraint requires.

**Fargate** — the answer is the profiles' subnets, so that is what changes. Two constraints make this more
than an edit: only private subnets are accepted ("only private subnets with no direct route to an Internet
Gateway are accepted for this parameter"), and **profiles are immutable** — "Fargate profiles can't be
changed. However, you can create a new updated profile to replace an existing profile, and then delete the
original." Create the replacement first, because "any Pods that are running using a Fargate profile are
stopped and put into a pending state when the profile is deleted" — deleting first takes the workload down.
For even placement AWS recommends one subnet per profile rather than three in one: "If you must have an even
spread, use two Fargate profiles. ... We recommend that each profile has only one subnet." `rel-9` cannot
help here — "Fargate does not currently support Kubernetes topologySpreadConstraints."

Sources: docs.aws.amazon.com/eks/latest/best-practices/cost-opt-compute.html,
docs.aws.amazon.com/eks/latest/userguide/fargate-profile.html,
docs.aws.amazon.com/eks/latest/userguide/create-node-class.html,
docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html,
docs.aws.amazon.com/eks/latest/userguide/ml-cluster-setup-cli.html.

---

### rel-2: Are PodDisruptionBudgets configured for critical deployments?

**Detection:** 🔬 AUTO-DETECTABLE

> PDBs prevent all replicas from being evicted simultaneously during node maintenance.

**Commands:**
```bash
kubectl get pdb -A -o json
kubectl get deployments -A -o json
# A Deployment counts when exactly one PDB selects it and that PDB allows at least one eviction but not
# all: minAvailable >= 1 and below the replicas it selects, or maxUnavailable >= 1 and below them
# (percentages rounded up); a PDB with neither field set does not count
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** `--min-available` must be set **strictly below** the Deployment's current replica
count. On a single-replica Deployment, `--min-available=1` requires that one pod never be evicted —
`kubectl drain`, managed node group upgrades and Karpenter consolidation all block indefinitely waiting
for a voluntary disruption the PDB will never allow. Give each workload exactly one PDB: when more than one
PDB selects the same pod, the eviction API refuses to evict it at all, so a second PDB blocks the drain
rather than adding protection — check for an existing PDB before creating one. Check the replica count,
create the PDB below it, then confirm the result is actually satisfiable:

```bash
kubectl get deployment <name> -n <ns> -o jsonpath='{.spec.replicas}'
kubectl create pdb <name> --selector=app=<label> --min-available=<replicas - 1> -n <ns>
kubectl get pdb <name> -n <ns> -o jsonpath='{.status.disruptionsAllowed}'   # must be >=1
```

If replicas is 1, fix that first — see `rel-7`. A PDB cannot make a single replica safe to evict.

---

### rel-3: Do containers have CPU and memory limits set?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource limits prevent a single container from consuming all node resources.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].resources.limits for cpu and memory
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set CPU and memory limits on all containers: `resources: { limits: { cpu: "500m", memory: "512Mi" } }`. Use VPA recommendations as a starting point.

---

### rel-4: Is a cluster autoscaler (Cluster Autoscaler or Karpenter) deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> Autoscalers add nodes when pods are pending and remove underutilized nodes.
> **An in-cluster autoscaler is credited only when it is ready.** A container whose image repository is
> `karpenter/controller` or `cluster-autoscaler` counts only in a Running Pod whose `status.containerStatuses`
> entry for that same container reports `ready: true`, whose `Ready` condition is `True` and which is not
> being deleted; a Deployment named like an autoscaler counts only with `status.readyReplicas` above 0.
> A controller in CrashLoopBackOff keeps its Pod in phase `Running` but is not ready, so it is not
> credited; when not-ready matches are all that is found the answer is `none`, and the detail counts
> them. That holds on a Fargate-only cluster too, where an autoscaler hosted on Fargate is what would add
> EC2 nodes: a not-ready or Pending matching container, or a Deployment whose Pod template runs a
> karpenter or cluster-autoscaler image and has no ready replica, makes it `none`, and only a Deployment
> matched by name alone, running neither image, leaves such a cluster `na`. The `karpenter.sh/nodepool` node label shows that
> Karpenter once provisioned a node, not that it still runs: the label stays after the controller is removed. It
> is credited only beside a ready Karpenter controller container. With such containers seen and none ready, or
> only Deployments whose Pod template runs the controller and none with a ready replica, the answer is `none`.
> With no controller seen at all it is `most`, not `none`, as a controller mirrored under another repository
> name is not recognised; the detail counts the labelled nodes and says why, and the list names them.
> **EKS Auto Mode satisfies this question with no autoscaler workload in the cluster** when it permits a
> node pool to provision into, and the verdict is read from `computeConfig.enabled` together with
> `computeConfig.nodePools`, not from a Deployment. AWS: "Auto scaling: Relying on Karpenter
> auto scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to be
> deployed to run those Pods. As workloads are terminated, EKS Auto Mode dynamically disrupts and
> terminates nodes when they are no longer needed, optimizing resource usage." Enabled with an EMPTY
> `computeConfig.nodePools` and no in-cluster autoscaler found reads as `most`, not `all`: the capability
> alone does not make nodes appear, and because this review does not collect NodePool objects, a NodePool
> the operator created themselves is not read and cannot be confirmed either way. Do not read an `all` on
> such a cluster as "a controller was found" — nothing runs in the cluster to find. AWS also applies
> `karpenter.sh/nodepool` to every node it provisions, so a label-based search **appears** to find OSS
> Karpenter on an Auto Mode cluster; the cluster fields are the answer, the label is a coincidence.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. Cluster Autoscaler grows and shrinks EC2 Auto Scaling groups and Karpenter provisions EC2 instances; a hybrid node is joined by the operator with `nodeadm` and neither controller can create or remove one.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -n karpenter -o json 2>/dev/null
kubectl get deployments -A -o json
# Look for karpenter or cluster-autoscaler, and check it is ready: the Pod's Ready condition is True, its
# status.containerStatuses[].ready is true, and the Deployment's status.readyReplicas is above 0
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig"
# enabled=true AND a non-empty nodePools -> autoscaling is a service capability, and an empty result
# from the two commands above is expected. enabled=true with nodePools [] is NOT that: no BUILT-IN node
# pool is enabled, which reads as `most`; a NodePool you created is not read here -- check for one
# with: kubectl get nodepools.karpenter.sh
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Karpenter or Cluster Autoscaler: `helm install karpenter oci://public.ecr.aws/karpenter/karpenter --version <VERSION> --namespace kube-system --set settings.clusterName=<CLUSTER>`, after creating the IAM roles its guide lists (https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/). Configure NodePools for automatic scaling.
If one is deployed but not ready, this check does not credit it: find out why with `kubectl describe deployment <name> -n <namespace>`, `kubectl describe pod <pod> -n <namespace>` and `kubectl logs <pod> -n <namespace> --previous`, and fix that rather than installing a second one.

**Not applicable to an EKS Hybrid Node** — neither Cluster Autoscaler nor Karpenter can create or remove one. Hybrid capacity is provisioned by you and joined with `nodeadm`.

**On an Auto Mode cluster, do not install either** — AWS suggests "running either EKS Auto Mode or
self-managed Karpenter", and if both are present the node pools have to be partitioned so each workload
belongs to exactly one of them. What is worth checking there instead is that your NodePool limits and
disruption settings are not blocking consolidation, and that PDBs (`rel-2`) do not stall the 21-day node
replacement Auto Mode enforces.

---

### rel-5: Are Horizontal Pod Autoscalers configured for deployments?

**Detection:** 🔬 AUTO-DETECTABLE

> HPAs scale pod replicas based on CPU/memory or custom metrics.

**Commands:**
```bash
kubectl get hpa -A -o json
kubectl get deployments -A -o json
# Count HPAs vs deployments
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add HPAs to stateless deployments: `kubectl autoscale deployment <name> --cpu=70% --min=2 --max=10` (kubectl 1.34 or newer; older kubectl spells it `--cpu-percent=70`).

---

### rel-6: Do containers have readiness probes configured?

**Detection:** 🔬 AUTO-DETECTABLE

> Readiness probes prevent traffic from being sent to pods that are not ready.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].readinessProbe is defined
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add readiness probes to all containers: `readinessProbe: { httpGet: { path: /healthz, port: 8080 }, initialDelaySeconds: 5, periodSeconds: 10 }`.

---

## Self-Healing Architecture

### rel-7: Do deployments run with more than one replica?

**Detection:** 🔬 AUTO-DETECTABLE

> Multiple replicas ensure availability during pod failures or rolling updates.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.replicas > 1
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `spec.replicas: 2` or higher for all production deployments. Single-replica deployments have zero availability during pod restarts.

---

### rel-8: Are pod anti-affinity rules configured to spread replicas across nodes?

**Detection:** 🔬 AUTO-DETECTABLE

> Anti-affinity prevents all replicas from landing on the same node. A `podAntiAffinity` counts only when
> it holds at least one required or preferred term with a `labelSelector`, on any `topologyKey`; an empty
> `podAntiAffinity: {}`, empty term lists, or a term without a `labelSelector` keep no replica apart and do
> not count.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.template.spec.affinity.podAntiAffinity for a required term, or a preferred
# entry's podAffinityTerm, that carries a labelSelector
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add pod anti-affinity rules: `affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution` with a `podAffinityTerm` whose `labelSelector` matches the workload's own Pods and `topologyKey: kubernetes.io/hostname`.

---

### rel-9: Are topology spread constraints configured to distribute pods across zones?

**Detection:** 🔬 AUTO-DETECTABLE

> Topology spread ensures pods are distributed across AZs for zone-level resilience.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.template.spec.topologySpreadConstraints for a zone topologyKey: topology.kubernetes.io/zone,
# topology.k8s.aws/zone-id or failure-domain.beta.kubernetes.io/zone (a hostname-only constraint does not count)
# and a labelSelector: a constraint without one matches no Pods and spreads nothing, so it does not count
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add a zone topology spread constraint whose `labelSelector` matches the Deployment's own Pod labels: `topologySpreadConstraints: [{ maxSkew: 1, topologyKey: topology.kubernetes.io/zone, whenUnsatisfiable: ScheduleAnyway, labelSelector: { matchLabels: { app: <your-app> } } }]`. Without a `labelSelector` the constraint matches no Pods and spreads nothing. Setting any constraint also replaces the scheduler's built-in default spreading (zone and hostname) for that Pod, so list every spread you want ([Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)).

---

### rel-10: Are VolumeSnapshot classes and snapshots configured for persistent volume backup?

**Detection:** ✋ ASK USER

> Volume snapshots enable point-in-time recovery for stateful workloads.

**Remediation:** Install the CSI **snapshot controller** — a separate component from the EBS CSI driver, and
one EKS Auto Mode does not include — then create a `VolumeSnapshotClass` naming the driver this cluster
actually provisions through. **Follow `rel-12`'s numbered prerequisites rather than repeating them here**:
the driver name differs between Auto Mode (`ebs.csi.eks.amazonaws.com`) and the standard EBS CSI driver
(`ebs.csi.aws.com`), and a class naming the wrong one matches no volume.

---

### rel-11: Are PersistentVolumeClaims in a Bound state?

**Detection:** 🔬 AUTO-DETECTABLE

> An unbound PVC blocks every Pod that mounts it, and usually means provisioning failed. A claim on a
> `WaitForFirstConsumer` StorageClass is the exception: it stays `Pending` by design until a Pod that
> uses it is scheduled, so such a claim with no consumer Pod yet is not a provisioning failure.

**Remediation:** Investigate unbound PVCs. Note that `--field-selector status.phase!=Bound` does
**not** work on PersistentVolumeClaims — Kubernetes registers only `metadata.name` and
`metadata.namespace` as selectable fields for PVCs, so that form fails with
`field label not supported: status.phase`. Filter client-side instead:

```bash
kubectl get pvc -A -o json \
  | jq -r '.items[]|select(.status.phase!="Bound")
           |"\(.metadata.namespace)/\(.metadata.name)\t\(.status.phase)\t\(.spec.storageClassName//"-")"'
```

Then for each, check that the StorageClass provisioner exists, that its zone matches where the pod
is scheduled (a `WaitForFirstConsumer` class binds only once a pod is placed), and that the
requested capacity is available.

---

### rel-12: Are VolumeSnapshot policies configured for automated backup?

**Detection:** ✋ ASK USER

> Automated snapshot policies ensure regular backups without manual intervention.

**Remediation:** A high Reliability score is not evidence a backup exists — nor is a snapshot that
has never been restored a tested backup. Prerequisites, in order:

**First establish which storage driver this cluster runs, because every step below differs by driver and
step 1 does not apply at all on EKS Auto Mode:**

```bash
kubectl get storageclass -o custom-columns=NAME:.metadata.name,PROVISIONER:.provisioner
aws eks describe-cluster --name <CLUSTER> --region <REGION> \
  --query 'cluster.storageConfig.blockStorage.enabled'
# true, or a StorageClass on ebs.csi.eks.amazonaws.com -> EKS Auto Mode block storage.
# A StorageClass on ebs.csi.aws.com -> the self-installed/add-on Amazon EBS CSI driver.
```

AWS: "EKS Auto Mode requires storage classes to use `ebs.csi.eks.amazonaws.com` as the provisioner. The
standard Amazon EBS CSI Driver (`ebs.csi.aws.com`) manages its own volumes separately." The two are not
interchangeable — a `VolumeSnapshotClass` naming the wrong one matches nothing and silently snapshots
nothing.

1. **A CSI driver with snapshot support.** On the **standard EBS CSI driver**, the `csi-snapshotter` sidecar
   must be running on the controller:
   `kubectl get pods -n kube-system -l app=ebs-csi-controller -o jsonpath='{.items[*].spec.containers[*].name}'`.
   **On EKS Auto Mode this command returns nothing, and that is correct, not a finding** — "You do not need
   to install the Amazon EBS CSI controller on EKS Auto Mode clusters", so there is no `ebs-csi-controller`
   Deployment and no sidecar to look for. Skip to step 2.
2. **The snapshot controller and the external-snapshotter CRDs** — `VolumeSnapshotClass`,
   `VolumeSnapshotContent`, `VolumeSnapshot` (`kubectl get crd | grep snapshot.storage.k8s.io`); without the
   controller reconciling them, a `VolumeSnapshot` object is created and never becomes `readyToUse`.
   **Neither ships with EKS Auto Mode** and this is the prerequisite most often missed on it: "Amazon EKS
   Auto Mode does not include the snapshot controller. The storage capability of EKS Auto Mode is compatible
   with the snapshot controller", and on the Auto Mode storage walkthrough, "You are responsible for
   installing and configuring the snapshot controller." Install it as the EKS managed add-on, which is also
   how you get the CRDs — AWS: "We recommend that you install the CSI snapshot controller through the Amazon
   EKS managed add-on. This add-on includes the custom resource definitions (CRDs) that are needed to create
   and manage snapshots on Amazon EKS."

The add-on name is not guessable, so it is quoted: "The Amazon EKS add-on name is `snapshot-controller`."

```bash
aws eks create-addon --cluster-name <CLUSTER> --addon-name snapshot-controller --region <REGION>
kubectl get crd | grep snapshot.storage.k8s.io   # 3 CRDs after the add-on becomes ACTIVE
```

On **EKS Auto Mode**, place it deliberately — "AWS suggests you configure this add-on to run on the built-in
`system` node pool", via the add-on's configuration values (`{"nodeSelector":{"karpenter.sh/nodepool":"system"}}`);
the snapshot controller already tolerates the `CriticalAddonsOnly` taint. A controller that cannot be
scheduled fails the same way a missing one does, and looks different in the logs than in the report.

3. **A `VolumeSnapshotClass` naming the driver this cluster actually uses.** On **EKS Auto Mode** — this is
   the class AWS publishes for it, driver included:

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: auto-ebs-vsclass
driver: ebs.csi.eks.amazonaws.com
deletionPolicy: Delete
```

On a cluster running the **standard Amazon EBS CSI driver**, the same object with
`driver: ebs.csi.aws.com`. Use the driver that matches the StorageClass the PVCs were provisioned
through — a snapshot class on the other driver will never match a volume. (Note the corollary AWS states
for migration: "To use existing volumes with EKS Auto Mode, migrate them using volume snapshots to a storage
class that uses the Auto Mode provisioner.")

4. **A schedule** — either a CronJob that creates a `VolumeSnapshot` referencing the target PVC on a
   recurring basis, or a managed path that replaces steps 3-4 outright: **AWS Backup** (native EBS/EFS
   backup plans with retention and cross-region copy) or **Velero with the AWS plugin** (namespace-aware —
   restores the Kubernetes objects, not just the volume). Either is less to operate than hand-rolled
   CronJob YAML.

**Verify a snapshot actually completes, then verify it actually restores** — a CronJob existing proves
neither:

```bash
kubectl get volumesnapshot -n <ns> <name> -o jsonpath='{.status.readyToUse}'   # must be true
# Then, on a schedule you repeat, prove restore works — a throwaway PVC/pod from the snapshot,
# not just a green snapshot job.
```

A snapshot that has never been restored is not a tested backup.

Sources for the Auto Mode statements above:
docs.aws.amazon.com/eks/latest/userguide/csi-snapshot-controller.html,
docs.aws.amazon.com/eks/latest/userguide/sample-storage-workload.html,
docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html,
docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html,
docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html.

---

## Failure Management

### rel-13: Are monitoring tools (Prometheus, CloudWatch, Datadog) deployed for alerting?

**Detection:** 🔬 AUTO-DETECTABLE

> Monitoring and alerting enable proactive detection of reliability issues.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for prometheus, grafana, datadog, cloudwatch
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Prometheus + Grafana for monitoring: `helm install prometheus oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack`. Configure alerting rules for critical metrics.

---

### rel-14: Are ingress controllers deployed with multiple replicas for high availability?

**Detection:** ✋ ASK USER

> HA ingress controllers prevent a single point of failure for inbound traffic.

**Remediation:** Scale ingress controllers to 2+ replicas: `kubectl scale deployment <ingress-controller> --replicas=3`. Add PDB with minAvailable=1.

---

### rel-15: Are LoadBalancer services used for external traffic exposure?

**Detection:** ✋ ASK USER

> LoadBalancer services distribute traffic across healthy pods.

**Remediation:** Use Service type LoadBalancer for external traffic. Deploy AWS Load Balancer Controller for ALB/NLB integration.

---

### rel-16: Is a service mesh deployed for traffic management and circuit breaking?

**Detection:** 🔬 AUTO-DETECTABLE

> Service meshes provide retry logic, circuit breaking, and traffic shifting.

**Remediation:** Deploy Istio, Linkerd or Consul Connect for traffic management with circuit breaking, retries, and traffic shifting capabilities.

**This question and Security's `sec-27` can disagree about the same cluster.** `rel-16` credits a Deployment named `istiod`,
`linkerd-destination`/`linkerd-controller` or `consul-connect`. `sec-27` (in
`security/identity-access.md`) credits `istiod`/`linkerd`/`consul-connect` by name **or** any Deployment
sitting in a namespace named exactly `istio-system`, `linkerd` (or a Linkerd extension namespace such as
`linkerd-viz`) or `consul`. Every Deployment `rel-16` matches, `sec-27` matches too, so the divergence runs one way only — `sec-27` "mesh present" against `rel-16`
"no mesh" — and it means one of two things. Either the mesh is real but not conventionally named (a
Consul control plane in namespace `consul` with no `consul-connect` Deployment, or `linkerd-viz` with no
`linkerd-destination`), and `sec-27` is the one to believe; or some Deployment merely sits in a namespace
*named* for a mesh that has no control plane in it — an app namespace called `consul`, an `istio-system`
left over from an uninstall — and `rel-16` is right. `sec-28` (mesh sidecars) counts workload pods, not the
mesh's own control-plane, gateway or ztunnel pods, carrying an Istio, Linkerd or Consul sidecar (`istio-proxy`, `linkerd-proxy`, `envoy-sidecar`,
`consul-dataplane`) and reads no mesh configuration, so no question here judges a mesh's mTLS mode.
Nothing in the report reconciles the questions; read them together.

---

### rel-17: Are CoreDNS and External DNS configured for service discovery?

**Detection:** ✋ ASK USER

> Reliable DNS is critical for service-to-service communication.

**Remediation:** Verify CoreDNS is running: `kubectl get pods -n kube-system -l k8s-app=kube-dns`. Deploy External DNS for automatic Route53 management.

---

### rel-18: Do deployments use RollingUpdate strategy?

**Detection:** 🔬 AUTO-DETECTABLE

> Rolling updates ensure zero-downtime deployments by gradually replacing pods.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.strategy.type == "RollingUpdate"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `strategy.type: RollingUpdate` with `maxUnavailable: 25%` and `maxSurge: 25%` on all Deployments for zero-downtime updates.

---

### rel-19: Do DaemonSets use RollingUpdate strategy?

**Detection:** 🔬 AUTO-DETECTABLE

> Rolling updates for DaemonSets prevent all node agents from restarting simultaneously.
> **Windows nodes:** not assessed — this skill supports Linux nodes only. A DaemonSet whose Pod template targets Windows (`os.name: windows`, a `kubernetes.io/os: windows` or `beta.kubernetes.io/os: windows` node selector, any `node.kubernetes.io/windows-build` node selector, or a required node affinity that, on those labels, admits Windows nodes and no Linux node) is left out of the count and disclosed in the detail.

**Remediation:** Set `updateStrategy.type: RollingUpdate` on DaemonSets with `maxUnavailable: 1` to prevent all node agents from restarting simultaneously.

---

## StatefulSet and DaemonSet workload shape

<!-- Do not file these three questions under "Disaster Recovery", "Resilience Testing" or
     "Dependency Management" -- not one of them is about any of those areas, and an
     operator scanning the headings to find the backup or the chaos-testing questions would find a DaemonSet
     resource-limits check instead. Nothing parses these `##` lines (the renderer keys on `###
     <id>: <title>` only), so the heading's only job is to tell a reader what is under it. -->

### rel-20: Do DaemonSet containers have resource requests and limits set?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource constraints on DaemonSets prevent them from starving workload pods.
> **Windows nodes:** not assessed — this skill supports Linux nodes only. A DaemonSet whose Pod template targets Windows (`os.name: windows`, a `kubernetes.io/os: windows` or `beta.kubernetes.io/os: windows` node selector, any `node.kubernetes.io/windows-build` node selector, or a required node affinity that, on those labels, admits Windows nodes and no Linux node) is left out of the count and disclosed in the detail.

**Remediation:** Add resource requests and limits to all DaemonSet containers to prevent them from starving workload pods on the same node.

---

### rel-21: Do StatefulSets use persistent storage (volumeClaimTemplates or PVCs)?

**Detection:** 🔬 AUTO-DETECTABLE

> Persistent storage ensures StatefulSet data survives pod restarts.
> **Windows nodes:** not assessed — this skill supports Linux nodes only. A StatefulSet whose Pod template targets Windows (`os.name: windows`, a `kubernetes.io/os: windows` or `beta.kubernetes.io/os: windows` node selector, any `node.kubernetes.io/windows-build` node selector, or a required node affinity that, on those labels, admits Windows nodes and no Linux node) is left out of the count and disclosed in the detail.

**Remediation:** Use `volumeClaimTemplates` in StatefulSet specs for persistent storage. This ensures each replica gets its own dedicated PVC.

---

### rel-22: Do StatefulSets run more than one replica?

**Detection:** 🔬 AUTO-DETECTABLE — the scorer checks `.spec.replicas > 1` on each StatefulSet.
**It does NOT check PodDisruptionBudgets**:
PDB coverage is measured separately by `rel-2`, which matches PDB selectors against workload labels.
Do not report an `all` here as evidence that StatefulSets are PDB-protected — that is a different
question with a different answer.

> A single-replica StatefulSet has no availability during a node drain, an AZ event, or its own
> rolling update: the one pod terminates before its replacement can attach the volume. Note that
> `replicas > 1` alone is not sufficient for a quorum-based system — a 2-replica etcd or ZooKeeper
> cannot form a majority — so read this as "not obviously single-pointed", not as "HA".
> **Windows nodes:** not assessed — this skill supports Linux nodes only. A StatefulSet whose Pod template targets Windows (`os.name: windows`, a `kubernetes.io/os: windows` or `beta.kubernetes.io/os: windows` node selector, any `node.kubernetes.io/windows-build` node selector, or a required node affinity that, on those labels, admits Windows nodes and no Linux node) is left out of the count and disclosed in the detail.

**Remediation:** Scale to the replica count the workload's own consensus model requires (3 for
quorum systems, 2+ for active/passive), and verify the volume claim template provisions per-replica
storage rather than sharing one volume:

```bash
kubectl scale statefulset/<name> -n <ns> --replicas=3
kubectl get statefulset <name> -n <ns> -o jsonpath='{.spec.volumeClaimTemplates[*].metadata.name}'
```

Then confirm a PDB actually selects those pods — see `rel-2`.

---

## Protection against accidental deletion

### rel-24: Is cluster deletion protection enabled?

**Detection:** 🔬 AUTO-DETECTABLE

> `DeleteCluster` is irreversible and takes the control plane, its CA and every access entry with it.
> Deletion protection makes EKS refuse the call outright, so an accidental `delete-cluster` — a wrong
> `--name`, a stale Terraform target, a misapplied script — fails instead of succeeding. It is a
> cluster-level flag, reported by `describe-cluster`, and costs nothing to hold.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.deletionProtection"
```

**Analysis:** boolean. `true` → `all`; `false` → `none`; field absent (older API surface) → `na`.

**Remediation:** Enable it in place — no restart, no rebuild:
```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> --deletion-protection
```
Then confirm the flag reads `true`. To delete such a cluster deliberately you disable protection first,
which is the point: the extra step is what stops the accident. Note this protects the **cluster**, not the
node groups, Fargate profiles or PersistentVolumes beneath it — those have their own lifecycles.

---

## Observability

### rel-23: Do you implement distributed tracing (AWS X-Ray, Jaeger, Zipkin) for request flow visibility?

**Detection:** 🔬 AUTO-DETECTABLE

> Distributed tracing enables root cause analysis across microservices.
>
> A ready Linux tracing collector counts — a Jaeger, Tempo, Zipkin, X-Ray or OpenTelemetry Deployment or DaemonSet,
> or a CloudWatch agent DaemonSet whose Application Signals X-Ray port (`cwa-appsig-xray`) is configured. An
> OpenTelemetry/ADOT operator on its own does not: it collects nothing until a collector resource exists.

**Remediation:** Deploy distributed tracing: `helm repo add jaegertracing https://jaegertracing.github.io/helm-charts && helm repo update && helm install jaeger jaegertracing/jaeger`. Or enable AWS X-Ray with the ADOT collector for request flow visibility.

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-2: Is NodeLocal DNSCache deployed for DNS performance?

**Detection:** 🔬 AUTO-DETECTABLE

> NodeLocal DNSCache reduces DNS latency and CoreDNS load.
> **EKS Auto Mode already caches DNS on the node — but only on nodes that are Auto Mode nodes.** AWS:
> "EKS Auto Mode does not use the traditional CoreDNS deployment to provide DNS resolution within the
> cluster. Instead, Auto Mode nodes utilize CoreDNS running as a system service directly on each node."
> On a **mixed-mode** cluster that credit does not transfer: "If you plan to maintain a cluster with both
> Auto Mode and non-Auto Mode nodes, you must retain the CoreDNS deployment. Non-Auto Mode nodes rely on
> the traditional CoreDNS pods for DNS resolution, as they cannot access the node-level DNS service that
> Auto Mode provides." So this question scores `all` only when **every** EC2 node carries
> `eks.amazonaws.com/compute-type: auto` — the label AWS documents as identifying Auto Mode managed
> nodes. Otherwise it measures the `nodelocaldns` DaemonSet as it always has.
> **EKS Hybrid Nodes:** EKS Hybrid Nodes are judged here: a nodelocaldns DaemonSet schedules onto a hybrid node, and a hybrid node resolves through the CoreDNS Deployment rather than through any node-local service, so the cache is exactly as relevant.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get daemonsets -A -o json
# Look for nodelocaldns or node-local-dns
kubectl get nodes -L eks.amazonaws.com/compute-type
# Every EC2 node "auto" -> node-level DNS everywhere. A mix -> the CoreDNS Deployment is still serving
# the non-Auto-Mode nodes, and a cache for them has to be deployed or done without.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all` (Fargate nodes excluded from that test, and a cluster with no EC2 node never satisfies it)

**Remediation:** Deploy NodeLocal DNSCache to reduce DNS latency: follow the EKS documentation for nodelocaldns DaemonSet deployment.

**On a mixed-mode cluster, deploy it for the non-Auto-Mode nodes only** (a `nodeAffinity` with
`eks.amazonaws.com/compute-type NotIn [auto]` keeps it off the Auto Mode nodes, which do not need it and
where a DaemonSet cannot replace the node's own DNS service). On an all-Auto-Mode cluster there is
nothing to deploy.

---

### lens-3: Is a CoreDNS autoscaler deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> CoreDNS autoscaler prevents DNS bottlenecks as the cluster grows.
> **On an all-Auto-Mode cluster there is no CoreDNS Deployment to autoscale**, so this scores `all` on
> the same gate as `lens-2`: AWS runs CoreDNS "as a system service directly on each node", which puts DNS
> capacity in step with the node count, and the node count is the thing Auto Mode autoscales — "EKS Auto
> Mode monitors for unschedulable Pods and makes it possible for new nodes to be deployed to run those
> Pods." Scoring this `none` while `lens-2` scores `all` would have the report contradict itself about one
> cluster fact. On a **mixed-mode** cluster, or an Auto Mode cluster that also runs Fargate nodes, the CoreDNS
> Deployment is retained and load-bearing for the non-Auto-Mode nodes and for Pods on Fargate, so the question
> measures the autoscaler as before.
> **EKS Hybrid Nodes:** Unaffected by EKS Hybrid Nodes — this question is about the CoreDNS Deployment, not about any node population. A hybrid node in fact depends on that Deployment, so the autoscaler matters more, not less.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for dns-autoscaler or proportional-autoscaler
aws eks describe-addon --cluster-name <name> --addon-name coredns --query addon.configurationValues --output text
# Or for `autoScaling` with `enabled: true` there: the EKS managed CoreDNS add-on then autoscales itself
kubectl get deployment coredns -n kube-system
# On an all-Auto-Mode cluster this returns NotFound, which is the expected shape, not a finding.
kubectl get nodes -L eks.amazonaws.com/compute-type
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster, and no hybrid or Fargate node → `all`

**Remediation:** Where CoreDNS runs as the EKS managed add-on, the add-on autoscales itself and a
second autoscaler is the wrong answer — turn its own autoscaling on instead, and EKS adapts the replica
count of the CoreDNS Deployment to the cluster's node and CPU count:

```bash
aws eks describe-addon --cluster-name <name> --addon-name coredns --query addon.configurationValues --output text
aws eks update-addon --cluster-name <name> --addon-name coredns \
  --resolve-conflicts PRESERVE --configuration-values '{"autoScaling":{"enabled":true}}'
```

`--configuration-values` is the add-on's whole configuration, not a patch: if the first command prints
existing values (a custom `corefile`, `replicaCount`, tolerations), merge the `autoScaling` object into them
and pass the merged document, or the values you leave out are dropped. `PRESERVE` only decides what happens to
fields that were changed on the cluster outside EKS; it does not keep configuration values left out of this call.
Autoscaling also needs the EKS add-on type of CoreDNS rather than a self-managed Deployment (`aws eks describe-addon
--cluster-name <name> --addon-name coredns` returns a version for it), and CoreDNS `v1.9` or later. The
optional `minReplicas`, `maxReplicas`, `nodesPerReplica` and `cpuCoresPerReplica` settings go in the same
`autoScaling` object, and the last two require a minimum add-on version for the cluster's Kubernetes
version (AWS publishes the table in "Scale CoreDNS Pods for high DNS traffic"). Only where CoreDNS is
self-managed, deploy a CoreDNS autoscaler (dns-autoscaler or proportional-autoscaler) to scale CoreDNS
replicas based on cluster size.

**This remediation does not apply to an all-Auto-Mode cluster** — there is no CoreDNS Deployment there to
give an autoscaler a scale target, and deploying one would be a no-op at best. On a mixed-mode cluster it does
apply, and it applies to the CoreDNS Deployment that AWS says you must retain for the non-Auto-Mode nodes, and that Pods on Fargate also resolve through;
size it against those nodes, not against the whole fleet.

---

### lens-14: Are NAT Gateways deployed per-AZ for redundancy?

**Detection:** 🔬 AUTO-DETECTABLE

> Per-AZ NAT Gateways prevent single-AZ failures from breaking outbound traffic.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. A NAT gateway gives nodes inside a VPC subnet egress to the internet, and a hybrid node egresses through the network the operator runs. The AZ population is the zone labels of the Linux EC2 nodes that are Ready and not cordoned (`spec.unschedulable`) plus, when any Fargate node is present, the AZs of the subnets the Fargate profiles launch Pods into, plus any AZ where only NotReady or cordoned Linux EC2 nodes run that is not credited with NAT egress (or, when no other AZ is left, every AZ where they run); a Fargate node's own zone label is not counted, because Fargate creates one node per Pod and the label records only where that Pod landed. Hybrid and Windows nodes are excluded. A NotReady or cordoned Linux EC2 node earns its AZ no credit, because the scheduler places no new workload Pod on it (DaemonSet Pods excepted): an AZ where only such nodes run is left out when it is credited with NAT egress, and stays in, failed, when it is not, because the Pods already on those nodes, and DaemonSet Pods, may still need egress. When no other AZ is left, the AZs where those nodes run are counted, so the filter never changes the verdict there. The detail says how many nodes that covers and which AZs were left out or kept.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws ec2 describe-nat-gateways --filter Name=vpc-id,Values=<VPC_ID> --region <REGION>
aws ec2 describe-route-tables --filters Name=vpc-id,Values=<VPC_ID> --region <REGION>  # each node subnet routes 0.0.0.0/0 to a NAT GW serving its AZ
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Give every AZ used by the cluster its own egress: either a regional NAT Gateway with automatic AZ expansion (`AutoProvisionZones` enabled), which expands to each AZ where it detects a workload network interface (AWS: up to 60 minutes after a resource first launches there), or one zonal NAT Gateway in a public subnet of each AZ, with each AZ's private route table pointing at the gateway in the same AZ. A regional gateway in manual mode serves only the AZs you have added to it, so add every node AZ. An AZ counts here only when every subnet its nodes are in (the subnet holding each Linux EC2 node's InternalIP, and with Fargate the profile subnets in that AZ) has an `active` `0.0.0.0/0` route to an available gateway serving that AZ, and a regional gateway serves only the AZs where it holds an egress address in status `succeeded`; an AZ it has no address in is not shown to have egress of its own. A private NAT gateway (`ConnectivityType` `private`) gives no internet egress and counts for no AZ; the gateway each AZ needs is a public one. When a node AZ is otherwise uncovered and an available regional gateway has no collected address in status `succeeded` that names an AZ, this question answers `NOT ASSESSED`; confirm the gateway's AZs in the VPC console.

**Not applicable to an EKS Hybrid Node** — it egresses through your own network, not through this VPC, so NAT gateway placement does not affect it.

---

### lens-15: Are worker nodes deployed in private subnets?

**Detection:** 🔬 AUTO-DETECTABLE

> Private subnets prevent direct internet access to worker nodes.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws ec2 describe-route-tables --filters Name=vpc-id,Values=<VPC_ID> --region <REGION>
# A subnet is PRIVATE when its route table has NO route whose GatewayId starts with "igw-".
# Use the subnet's explicitly-associated table (association state "associated"); fall back to the VPC's main table if it has none.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Remove the internet gateway route from the route tables serving the node subnets, and
route `0.0.0.0/0` to a NAT gateway in a public subnet instead.

> **Read this before running anything.** You are editing the default route of a live subnet. `replace-route`
> is used rather than delete-then-create because a failed `create-route` after a successful `delete-route`
> leaves the subnet with **no default route at all** — every node in it loses outbound connectivity,
> including image pulls and the kubelet's path to the control plane. Confirm the NAT gateway exists and is
> `available` in a public subnet that is **not associated with the route table you are about to change**, and
> do one route table at a time. A public route table is often shared: if the table is also associated with the
> NAT gateway's own subnet, repointing its default route at the NAT gateway cuts the NAT gateway off from the
> internet gateway, and with it the egress of every private subnet that routes through it; public load
> balancer subnets on the table lose their internet gateway route too. Do **not** run step 2 on such a table.
> Give the node subnets their own route table instead: `create-route-table`, `create-route` 0.0.0.0/0 to the
> NAT gateway on it, then move each node subnet onto it with `replace-route-table-association` (or
> `associate-route-table` for a subnet that has no explicit association), leaving the shared table and its
> internet gateway route untouched.

```bash
# 1. confirm the NAT gateway is usable before touching any route
aws ec2 describe-nat-gateways --nat-gateway-ids <NAT_ID> --region <REGION> \
  --query 'NatGateways[].{State:State,Subnet:SubnetId}'
# ...and list every subnet on the table: the NAT gateway's subnet must NOT be among them. Main=true means
# every subnet with no explicit association uses this table too, so check those as well
aws ec2 describe-route-tables --route-table-ids <RTB_ID> --region <REGION> \
  --query 'RouteTables[].Associations[].{Subnet:SubnetId,Main:Main,Assoc:RouteTableAssociationId}'

# 2. atomically repoint the default route — no window with the subnet unrouted
aws ec2 replace-route --route-table-id <RTB_ID> --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id <NAT_ID> --region <REGION>
```

Existing nodes keep their public IPs until replaced, so cycle the node group afterwards. Note that
setting `MapPublicIpOnLaunch=false` alone will **not** satisfy this check: it stops new instances
getting a public IP, but a subnet whose route table still reaches an internet gateway is still a public
subnet, and nodes already running in it keep the addresses they were given.

---
