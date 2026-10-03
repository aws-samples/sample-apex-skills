# 💰 Cost Optimization

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**11 questions** — Resource quotas, limit ranges, storage efficiency, idle resources, cost visibility,
chargeback tagging, VPC endpoints.

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` (Not
Assessed).

> ### What this pillar score measures — put this NEXT TO the number, every time the number appears
>
> **This score measures cost *hygiene*, not total cost efficiency.** The three largest levers on an EKS
> bill are **deliberately not scored here**, because each depends on intent the cluster cannot report:
>
> | Lever | Why not scored | Where it lives |
> |---|---|---|
> | **Spot vs On-Demand** | Spot under a stateful or latency-critical tier is *wrong*, not un-optimised. Keeping On-Demand can be the correct answer. | [cost-analysis.md](cost-analysis.md) Opportunity 2 |
> | **Graviton vs x86** | Blocked by container image architecture, which is not observable from `aws`/`kubectl`. | [cost-analysis.md](cost-analysis.md) Opportunity 1 |
> | **Extended Support surcharge** | Depends on today's date versus the EKS release calendar; scoring it would make the same cluster score differently on different days and break run-to-run determinism. | [cost-analysis.md](cost-analysis.md) Opportunity 7 |
>
> **Consequence you must disclose:** a cluster that has already taken every major lever — 100% Spot,
> 100% Graviton, on a current version — scores **exactly the same here** as one that has taken none.
> No scored question here reads the support policy or the version, so `EXTENDED` moves this pillar by **0**.
>
> **This is a placement requirement, not just a talking point.** "Mention cost hygiene somewhere in the
> conversation" does not satisfy this — the label and the three-lever posture line MUST sit immediately
> beside the Cost score **wherever that score is displayed**: in the chat response, in the written/Markdown
> report, and in the rendered HTML artifact that gets forwarded to the customer. A reader who sees only the
> number in the HTML — because the caveat landed in chat but not in the document, or landed once in an
> unrelated remediation bullet instead of next to the score — has been shown a "cost hygiene" score without
> being told it is one. Restate the cluster's actual Spot / Graviton / version posture (not just the word
> "hygiene") next to every rendering of the number, not once at the top of the report and not only in
> prose the reader has to go looking for. A bare number invites the reader to conclude "no cost levers
> taken", which the number does not say. Do **not** resolve this by folding the three levers into the
> scorer — that manufactures findings against clusters that are correct by design.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data.
> Use the prose for rationale and remediation wording only.

---

## Table of Contents

1. [Cost Optimization scorer — run by `assets/score.sh`, not by hand](#cost-optimization-scorer--run-by-assetsscoresh-not-by-hand)
2. [Cost Effective Resources](#cost-effective-resources)
   - [cost-1: Are ResourceQuotas configured for namespaces to prevent resource over-consumption?](#cost-1-are-resourcequotas-configured-for-namespaces-to-prevent-resource-over-consumption)
   - [cost-2: Are LimitRanges configured for namespaces to set default resource constraints?](#cost-2-are-limitranges-configured-for-namespaces-to-set-default-resource-constraints)
   - [cost-3: Do you proactively optimize Pod hours by scaling down or terminating unnecessary Pods during off-peak hours, nights, and weekends?](#cost-3-do-you-proactively-optimize-pod-hours-by-scaling-down-or-terminating-unnecessary-pods-during-off-peak-hours-nights-and-weekends)
   - [cost-4: Are you proactively monitoring and measuring data transfer costs between Availability Zones, regions, and to the internet?](#cost-4-are-you-proactively-monitoring-and-measuring-data-transfer-costs-between-availability-zones-regions-and-to-the-internet)
   - [cost-5: Is storage provisioning efficient (requested capacity vs provisioned capacity)?](#cost-5-is-storage-provisioning-efficient-requested-capacity-vs-provisioned-capacity)
3. [Expenditure and Usage Awareness](#expenditure-and-usage-awareness)
   - [cost-6: Are PersistentVolumes actively used (every PV Bound)?](#cost-6-are-persistentvolumes-actively-used-every-pv-bound)
   - [cost-7: Are cost allocation tags applied to the EKS cluster for chargeback?](#cost-7-are-cost-allocation-tags-applied-to-the-eks-cluster-for-chargeback)
   - [cost-8: Are the cluster's EBS volumes all attached (none idle and still billing)?](#cost-8-are-the-clusters-ebs-volumes-all-attached-none-idle-and-still-billing)
4. [StorageClass cost defaults](#storageclass-cost-defaults)
   - [cost-9: Are StorageClasses configured with cost-optimized volume types (gp3, Delete reclaim policy)?](#cost-9-are-storageclasses-configured-with-cost-optimized-volume-types-gp3-delete-reclaim-policy)
5. [EKS Best Practices](#eks-best-practices)
   - [lens-4: Is cost visibility tooling (Kubecost/OpenCost) deployed?](#lens-4-is-cost-visibility-tooling-kubecostopencost-deployed)
   - [lens-16: Are VPC endpoints for S3, ECR, and STS configured and available?](#lens-16-are-vpc-endpoints-for-s3-ecr-and-sts-configured-and-available)

---

## Cost Optimization scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh cost-optimization "$WORK"` extracts this block and runs it. Do not paste it
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
# Shape guard for every `rl` program, applied by `rl` itself: the result must be an object with `pass` and
# `fail` arrays of STRINGS plus an optional `context` array of strings, else `rl` records the failure.
# `{pass,fail}` rebuilds the object so a program returning extra keys cannot smuggle them through.
RQ='|if (type=="object") and ((.pass|type)=="array") and ((.fail|type)=="array") and (((.context//[])|type)=="array") and (([(.pass+.fail+(.context//[]))[]|select(type!="string")]|length)==0) and ((.kind==null) or (.kind=="field") or (.kind=="existence")) and ((.excluded==null) or (((.excluded|type)=="number") and (.excluded>=0) and ((.excluded|floor)==.excluded))) and ((.context_only==null) or ((.context_only|type)=="boolean")) then {pass,fail}+(if (.context|type)=="array" then {context} else {} end)+(if .kind!=null then {kind} else {} end)+(if .excluded!=null then {excluded} else {} end)+(if .context_only==true then {context_only:true} else {} end) else error("rl: the program did not return {pass:[string],fail:[string]} with optional context:[string], kind:field|existence, excluded:integer, context_only:boolean") end'
# BUILD THE RECORD WITH jq, NOT printf. `detail` is raw jq output and several questions interpolate
# cluster-controlled strings into it; with printf a `"` would forge a duplicate `state` key and a newline
# would forge whole extra records in other pillars. `--arg` escapes instead.
# Two details are load-bearing:
#   -c   without it results.jsonl stops being JSONL, and score.sh's already-scored refusal breaks: it greps
#        the literal `"pillar":"cost-optimization"`, which only compact output reproduces.
#   ||   this block runs under `bash` with NO `set -e`. Unguarded, one failed record gives rc=0 with a
#        question missing; guarded, the pillar aborts at rc=1 and the message names the failing question.
# Key order stays pillar,id,track,state,detail; `resources` is a sixth key appended only for questions that
# ran `rl`, so the first five fields read the same for every consumer.
# `--argjson` carries the whole evidence list as ONE argv entry, so a very large fleet can exceed ARG_MAX (on
# Linux the 128 KiB per-argument cap) and `execve` fails with "Argument list too long" before jq starts.
# Malformed content cannot reach this abort: `rl` admits exactly one valid line.
# THE ID IS RE-ASSERTED: a stale evidence list from the previous question is dropped, not attached to this
# one -- a list of the wrong objects under a verdict is worse than no list.
# Five files carry this helper; if you change one, change all five.
emit(){ local rs=false
  if [ "${RESID:-}" = "$1" ]; then rs="${RES:-null}"; fi
  RES= RESID=
  jq -cn --arg id "$1" --arg tr "$2" --arg st "$3" --arg de "$4" --argjson rs "$rs" \
  '{pillar:"cost-optimization",id:$id,track:$tr,state:$st,detail:$de}+(if $rs==false then {} else {resources:$rs} end)' >> "$W/results.jsonl" \
  || { printf 'SCORER ABORT [%s]: the record was not emitted -- the jq call failed, the OS refused to start it, or the append to results.jsonl failed; any message jq or the OS printed is above. On a large fleet suspect the evidence list rather than the record: the list reaches jq as ONE --argjson argument, so many thousand names can exceed the OS argument-size limit and execve fails with "Argument list too long" before jq runs.\n' "$1" >&2; exit 1; }; }
# rl <id> <collection-file>... '<jq program>'  -- NAME the objects the next `emit` counted, so the report can
# print `payments/api` rather than `7/9`: a correct count over the wrong set is the scoping bug a bare count
# hides. The list is built in jq next to the verdict, not re-derived in Python (jq's `select(.x)` keeps `{}`,
# `[]`, `""` and `0`; Python's `bool()` rejects all four).
# A question without an `rl` line publishes no list. Some stay unconverted because the `m` program has
# already flattened away the identity a name needs (`rel-20`'s container list). Count converted questions with
#     grep -h '^rl ' references/*.md references/*/*.md | wc -l
# (`-h` plus `wc -l`, not `grep -c`, which counts per file; two globs, not `**`, because stock macOS bash 3.2
# has no `globstar`).
# It is a SEPARATE jq call from `m` so a failing name expression cannot abort the pillar: `rl` swallows its
# own failure, records `resources: null`, and the `m` line scores the question as usual. Three states, and the
# report says which: no `resources` key = no list published; `null` = the list could not be built; `[]` = the
# check looked and found nothing.
# The selection test appears twice (`rl` and `m`), so the report checks the list's counts against the ratio in
# `detail`. Write `fail` as the complement (`$all - $pass`) so the test appears once inside `rl`.
# `rl` emits unadorned arrays of strings; sorting, "showing 12 of N" truncation and labels are the renderer's.
# The failure reason: jq's stderr goes to $RLERR (`rl.stderr` in the `.eks-war-scorer.<pillar>.<pid>/`
# directory score.sh made for THIS run, never a fixed name in $W) and is read back into the message; the query
# is not re-run, since a second execution could fail differently. `2>` truncates, so only this call's stderr is
# read. With RLERR unset (block run outside score.sh) stderr goes to /dev/null, and jq's words are quoted only
# when the target is a writable regular file.
rl(){ local id="$1"; shift; local fs=(); while [ "$#" -gt 1 ]; do fs+=("$W/$1.json"); shift; done; local r n q e= ef="${RLERR:-/dev/null}"; r=$(jq -c "$B $1 $RQ" "${fs[@]}" 2>"$ef"); q=$?; if [ "$q" = 0 ] && [ -n "$r" ] && n=$(printf '%s' "$r" | wc -l | tr -d ' ') && [ "$n" = 0 ]; then RES="$r" RESID="$id"; else RES=null RESID="$id"; if [ ! -f "$ef" ] || [ ! -w "$ef" ]; then e="jq's stderr could not be captured to $ef, so any OS message is on the line above"; else [ -s "$ef" ] && e=$(tr -s '[:space:]' ' ' < "$ef"); e="${e# }"; e="${e% }"; [ -n "$e" ] && e="; jq said: $e"; if [ "$q" != 0 ]; then e="jq exited $q$e"; elif [ -z "$r" ]; then e="jq exited 0 and produced no output at all$e"; else e="jq exited 0 but produced $((n+1)) results, and an evidence list is exactly one$e"; fi; fi; printf 'RESOURCE LIST SKIPPED [%s]: the evidence list could not be built -- %s. THE VERDICT IS UNAFFECTED -- this is not a finding and not a scoring error; the report will say that this step failed and that there is no list for this question.\n' "$id" "$e" >&2; fi; return 0; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

# lens-12 / lens-13 (ECR scan-on-push, immutable image tags) are scored by the Security scorer in
# security/identity-access.md, not here: the EKS Best Practices Guides place both under Security, Image Security.
# cost-1 and cost-2 COUNT WHAT THE OBJECT SAYS, not that it exists: a quota holding only `count/configmaps` or a
# LimitRange constraining only PVCs must not score `all` on COMPUTE over-consumption. Keys (literal comparisons,
# not a regex): for a quota `cpu`/`memory` plus the `requests.`/`limits.` spellings; for a LimitRange a `Container`
# or `Pod` item naming cpu or memory in `default`, `defaultRequest`, `min` or `max` (not `maxLimitRequestRatio`
# alone, not `spec.limits: []`). A quota counts only with no scope (`spec.scopes` and `scopeSelector` scopeNames)
# or `NotTerminating` alone: scopes intersect, so `Terminating`, `BestEffort`, `NotBestEffort` or `PriorityClass`
# can leave long-running Pods unlimited; the detail says how many such scoped quotas were set aside. It says
# `cpu/memory quota` / `cpu/memory limitrange` so `0/4 ns quota` beside visible quotas is not a false statement.
rl cost-1 resourcequotas namespaces 'def cm: [(.spec.hard//{})|keys[]|select(.=="cpu" or .=="memory" or .=="requests.cpu" or .=="requests.memory" or .=="limits.cpu" or .=="limits.memory")]|length>0; def us: ([(.spec.scopes//[])[],((.spec.scopeSelector.matchExpressions//[])[]|(.scopeName//"?"))]-["NotTerminating"])==[]; input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|(.metadata.name//"?")] as $n|([.items[]|select(cm)|select(us)|.metadata.namespace]|unique) as $cov|[$n[]|select(. as $x|$cov|index($x))] as $p|{pass:$p,fail:($n-$p)}'
m2 cost-1 resourcequotas namespaces 'def cm: [(.spec.hard//{})|keys[]|select(.=="cpu" or .=="memory" or .=="requests.cpu" or .=="requests.memory" or .=="limits.cpu" or .=="limits.memory")]|length>0; def us: ([(.spec.scopes//[])[],((.spec.scopeSelector.matchExpressions//[])[]|(.scopeName//"?"))]-["NotTerminating"])==[]; input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|[.items[]|select(cm)|select((.metadata.namespace//"") as $x|$n|index($x))] as $q|([$q[]|select(us)|.metadata.namespace]|unique) as $cov|([$q[]|select(us|not)]|length) as $sq|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns cpu/memory quota"+(if $sq>0 then " (\($sq) scoped cpu/memory quota(s) not counted: a scope other than NotTerminating can leave long-running Pods outside the quota)" else "" end)'
rl cost-2 limitranges namespaces 'input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|(.metadata.name//"?")] as $n|([.items[]|select([.spec.limits[]?|select(.type=="Container" or .type=="Pod")|((.default//{})+(.defaultRequest//{})+(.min//{})+(.max//{}))|keys[]|select(.=="cpu" or .=="memory")]|length>0)|.metadata.namespace]|unique) as $cov|[$n[]|select(. as $x|$cov|index($x))] as $p|{pass:$p,fail:($n-$p)}'
m2 cost-2 limitranges namespaces 'input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[]|select([.spec.limits[]?|select(.type=="Container" or .type=="Pod")|((.default//{})+(.defaultRequest//{})+(.min//{})+(.max//{}))|keys[]|select(.=="cpu" or .=="memory")]|length>0)|.metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns cpu/memory limitrange"'
# cost-3 asks about OFF-PEAK scale-down (nights, weekends). Load-based autoscaling does not do that: an HPA at
# minReplicas still runs those replicas all night, so neither "KEDA present" nor "any HPA active" scores `all`.
# A scheduled scale-down shows up as a CronJob; KEDA's cron scaler lives in a ScaledObject, which is not
# collected, so KEDA alone is `some` with the reason stated.
# The `rl` line names all three evidence classes, including the CronJob that decides an `all` verdict (cost-3's
# detail has no `n/m`, so no count cross-check would catch an omission). KEDA Deployments print as `ns/name`,
# HPAs with an `HPA: ` prefix. The KEDA match is case-insensitive, as in the `m3` line.
# `nightly` IS NOT A CronJob NAME TOKEN and must not become one, nor `offpeak`/`off-peak`: they name WHEN, not
# what, so a lone `ops/nightly-db-backup` or `ops/offpeak-db-backup` would score `all`. The tokens name the ACTION, so
# `nightly-scale-down` still matches on its verb. A bare `scale` is not a token (`payments-scale-up-0800`
# would score as a scale-down), nor a bare `to-?0` (`upgrade-to-0-9`).
# A SUSPENDED CronJob (`spec.suspend: true`) does not count: it starts no runs, so it scales nothing down.
rl cost-3 deployments hpa cronjobs 'input as $h|input as $cj|[.items[]?|select(.metadata.name|test("keda";"i"))|select((.status.readyReplicas|numbers)>0)|(.metadata.namespace//"")+"/"+(.metadata.name//"?")] as $keda|[$h.items[]?|"HPA: "+(.metadata.namespace//"")+"/"+(.metadata.name//"?")] as $hpa|[$cj.items[]?|select(.spec.suspend!=true)|select(.metadata.name|test("scale-?down|down-?scal|scale-?in($|-)|to-?zero|scale-?to-?0($|-)|shutdown";"i"))|"scheduled scale-down CronJob: "+(.metadata.namespace//"")+"/"+(.metadata.name//"?")] as $sched|{kind:"existence",pass:($sched+$keda+$hpa),fail:[]}'
m3 cost-3 deployments hpa cronjobs 'input as $h|input as $cj|(([.items[]|select(.metadata.name|test("keda";"i"))|select((.status.readyReplicas|numbers)>0)]|length)>0) as $keda|([$h.items[]?]|length>0) as $hpa|([$cj.items[]?|select(.spec.suspend!=true)|select((.metadata.name|test("scale-?down|down-?scal|scale-?in($|-)|to-?zero|scale-?to-?0($|-)|shutdown";"i")))]|length) as $sched| if $sched>0 then "all~\($sched) scheduled scale-down CronJob(s)" + (if $keda then " + KEDA" else "" end) elif $keda then "some~KEDA installed, but no schedule-driven scale-down found (KEDA cron scalers are configured in ScaledObjects, which this review does not collect)" elif $hpa then "some~HPA only: scales on load, not on a clock, so idle nights and weekends still run at minimum replicas" else "none~no autoscaling" end'
g cost-4
g cost-5
# cost-6 TESTS IN-USE POSITIVELY -- `phase == "Bound"` -- not by exclusion (`!= "Released" and != "Available"`).
# `Failed` and `Pending` are neither, so an exclusion test would count an orphaned PV whose reclamation FAILED
# (its EBS volume still bills) as passing. `Bound` is the only phase serving a claim, as `rel-11` also uses, and
# cannot be widened by a phase name this scorer has never heard of.
rl cost-6 pv '[.items[]] as $v|[$v[]|select(.status.phase=="Bound")] as $p|def n: (.metadata.name//"?")+" ("+(.status.phase//"?")+")";{pass:[$p[]|n],fail:[($v-$p)[]|n]}'
m cost-6 pv '[.items[]] as $p|($p|length) as $t|([$p[]|select(.status.phase=="Bound")]|length) as $ok| if $t==0 then "na~no PV" else b($ok;$t)+"~\($ok)/\($t) in-use" end'
# cost-7's members are the four TAG CLASSES, not the tags: the denominator is 4 whatever the cluster carries,
# and a class passes when a tag key matching its pattern has a non-blank value (`project=""` attributes nothing).
# `keys_unsorted`, not `keys`, so the panel lists keys in the order the cluster reported them.
rl cost-7 cluster '(.cluster.tags//{}) as $t|($t|keys_unsorted) as $a|[$a[]|select($t[.]|strings|test("\\S"))] as $k|[(["project","project"],["environment","environment|^env$"],["cost-centre","cost|billing"],["team","team|owner"])|.[0] as $lab|.[1] as $pat|{l:$lab,h:[$k[]|select(test($pat;"i"))],e:[$a[]|select(test($pat;"i"))]}] as $r|{pass:[$r[]|select((.h|length)>0)|.l+": "+(.h|join(", "))],fail:[$r[]|select((.h|length)==0)|.l+": "+(if (.e|length)>0 then (.e|join(", "))+" (blank value)" else "absent" end)],context:[($t|to_entries)[]|.key+"="+(.value|tostring)]}'
m cost-7 cluster '(.cluster.tags//{}) as $t|(["project","environment|^env$","cost|billing","team|owner"]|map(select(. as $k|$t|to_entries|map(select(.value|strings|test("\\S")))|any(.key|test($k;"i"))))|length) as $ok| b($ok;4)+"~\($ok)/4 chargeback tag classes (project/environment/cost-centre/team)"'
# cost-8 emits PASSES/total like every sibling, and both lines count passes (`State == "in-use"`). The
# renderer cross-checks each list against the ratio in the detail, so failures/total would give a false
# DISAGREEMENT whenever $idle != $t-$idle and a false AGREEMENT at the midpoint (2 idle of 4). There is no
# `$idle==0` special case: prose with no ratio would skip the cross-check on exactly the clusters where a
# scoping bug would be invisible.
# Volume scoping is a cluster TAG OR A PersistentVolume's volume id (`$pvid`, verbatim from `sec-21`): without
# `--k8s-tag-cluster-id` the EBS CSI driver tags a volume only `ebs.csi.aws.com/cluster=true`, and a detached PV
# volume is exactly the idle case. NOT `sec-21`'s third clause, an attachment to one of this cluster's nodes: an
# attached volume passes by definition, so admitting it cannot surface a leak and only dilutes the ratio toward a
# pass (one idle tagged volume plus five untagged attached ones would read `most~5/6`, not `none~0/1`).
# `describe-volumes` is account- and region-wide with no filter, so this predicate alone keeps another
# cluster's disks out. A bare `.Value==$cn` is not enough: an unrelated volume tagged `Name=<cluster>` would
# count, turning `all` (1/1) into `some` (1/2) on a High-severity question. Both clauses bind the cluster
# NAME to a cluster-ish key.
# ATTACHED IS `in-use`, NOT "anything but available": `error`, `creating` and `deleting` would count toward
# the pass numerator and the "Attached, doing work" heading on a question about a pure billing leak.
# `error` and `deleted` leave the denominator: `error` means the hardware failed and the data is
# unrecoverable (https://docs.aws.amazon.com/ebs/latest/userguide/ebs-describing-volumes.html) and "AWS
# doesn't bill for volumes that have the error status" (https://repost.aws/knowledge-center/ebs-error-status),
# so neither label is true of it. `creating` and `deleting` are races, not leaks, but count as failures while
# they last: a one-run finding that disappears beats a false pass.
rl cost-8 volumes cluster pv 'input as $cl|input as $pvs|($cl.cluster.name//"") as $cn|([$pvs.items[]?|(.spec.csi.volumeHandle?,.spec.awsElasticBlockStore.volumeID?)]|map(select((type=="string") and .!="")|split("/")|last)|unique) as $pvid|[.Volumes[]?|select(([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0) or ((.VolumeId//"")|IN($pvid[])))] as $all|[$all[]|select((.State!="error") and (.State!="deleted"))] as $v|[$v[]|select(.State=="in-use")] as $p|def n: (.VolumeId//"?")+" ("+(.State//"?")+")";{pass:[$p[]|n],fail:[($v-$p)[]|n]}'
m3 cost-8 volumes cluster pv 'input as $cl|input as $pvs|($cl.cluster.name//"") as $cn|([$pvs.items[]?|(.spec.csi.volumeHandle?,.spec.awsElasticBlockStore.volumeID?)]|map(select((type=="string") and .!="")|split("/")|last)|unique) as $pvid|[.Volumes[]?|select(([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0) or ((.VolumeId//"")|IN($pvid[])))] as $all|[$all[]|select((.State!="error") and (.State!="deleted"))] as $v|(($all|length)-($v|length)) as $x|($v|length) as $t|([$v[]|select(.State=="in-use")]|length) as $ok| if $t==0 then (if $x>0 then "na~no cluster volumes (tagged or named by a PV) other than \($x) in state error or deleted, which EBS does not bill" else "na~no cluster volumes (tagged or named by a PV)" end) else b($ok;$t)+"~\($ok)/\($t) attached (cluster or PV vols)" end'
# cost-9 tests BOTH halves of its title, "gp3, Delete reclaim policy". Reading only `.parameters.type` would let
# a gp3 class with `reclaimPolicy: Retain` -- which leaves EBS volumes behind on every PVC delete, the leak
# cost-8 reports -- score like a correct one. `reclaimPolicy` defaults to Delete when unset
# (https://kubernetes.io/docs/concepts/storage/storage-classes/).
# The provisioner set is CANONICAL on FOUR scorer lines: cost-9's `rl` and `m` here, and `sec-25`'s `rl` and
# `m` in references/security/identity-access.md. EDIT ALL FOUR OR NONE. All three must stay listed:
# `ebs.csi.aws.com` (self-managed EBS CSI driver), `ebs.csi.eks.amazonaws.com` (EKS Auto Mode, which has its
# own provisioner: https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html) and
# `kubernetes.io/aws-ebs` (in-tree legacy).
# DO NOT REPLACE THE SET WITH A BARE `test("ebs|aws-ebs")`: it matches Auto Mode only by accident, would match
# an unrelated `example.com/ebs-fake`, and hides divergence between the lists instead of fixing it.
# The in-scope test (provisioner OR EBS volume type) appears on both the `rl` and `m` line. `sec-25` scopes by
# provisioner alone and grades an untyped class (it reads `parameters.encrypted`, never the type), so an editor
# changing what counts as GRADED here must not assume the two questions agree. `pass` (gp3 AND Delete, Delete
# the default) is spelled as the `m` line spells it and `fail` is the complement. Out-of-scope classes stay
# `context`, NAMED not counted.
# A THIRD BUCKET: AN EBS CLASS WITH NO `parameters.type` THAT RECLAIMS WITH Delete IS NOT GRADED. An absent
# `type` comes from the CSI driver's default, which this scorer (it reads `storageclasses` only) cannot
# resolve, and grading it a FAIL would put it in `resources.fail` on a High question while admitting it did
# not know. It leaves numerator AND denominator and is named in `context`. Only the TYPE half is unknown: an
# untyped class whose reclaim is NOT Delete fails "gp3 AND Delete" whatever its type, so it stays graded, in
# `fail`, labelled `type=unset, reclaimPolicy=<policy>`. Leaving it ungraded would turn
# [gp3/Delete, untyped/Retain] into a false all~1/1. When every in-scope class is ungraded the question
# publishes `na` and says why, not `0/0`.
rl cost-9 storageclasses '[.items[]?] as $all|def inscope: ((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|ebs\\.csi\\.eks\\.amazonaws\\.com|kubernetes\\.io/aws-ebs")) or ((.parameters.type//"")|test("^(gp2|gp3|io1|io2|st1|sc1)$"));def ty: ((.parameters.type//"")|tostring);[$all[]|select(inscope and (((ty|length)>0) or ((.reclaimPolicy//"Delete")!="Delete")))] as $sc|[$sc[]|select((ty=="gp3") and ((.reclaimPolicy//"Delete")=="Delete"))] as $p|def n: (.metadata.name//"?")+" (type="+(if (ty|length)>0 then ty else "unset, reclaimPolicy="+((.reclaimPolicy//"Delete")|tostring) end)+", encrypted="+((.parameters.encrypted//"unset")|tostring)+")";{pass:[$p[]|n],fail:[($sc-$p)[]|n],context:([$all[]|select(inscope and ((ty|length)==0) and ((.reclaimPolicy//"Delete")=="Delete"))|(.metadata.name//"?")+" (provisioner "+((.provisioner//"?")|tostring)+", reclaimPolicy Delete, no parameters.type — the volume type comes from the driver default, which this review does not collect, so this class was NOT graded)"]+[$all[]|select(inscope|not)|(.metadata.name//"?")+" ("+((.provisioner//"?")|tostring)+")"])}'
m cost-9 storageclasses '[.items[]?] as $all|def inscope: ((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|ebs\\.csi\\.eks\\.amazonaws\\.com|kubernetes\\.io/aws-ebs")) or ((.parameters.type//"")|test("^(gp2|gp3|io1|io2|st1|sc1)$"));def ty: ((.parameters.type//"")|tostring);[$all[]|select(inscope and (((ty|length)>0) or ((.reclaimPolicy//"Delete")!="Delete")))] as $sc|([$all[]|select(inscope and ((ty|length)==0) and ((.reclaimPolicy//"Delete")=="Delete"))]|length) as $u|($sc|length) as $t|([$sc[]|select((ty=="gp3") and ((.reclaimPolicy//"Delete")=="Delete"))]|length) as $ok| if $t==0 then (if $u>0 then "na~\($u) EBS StorageClass(es) have a Delete reclaim policy but set no parameters.type, so the volume type comes from the CSI driver default, which this review does not collect — this question was not answered here" else "na~no EBS StorageClasses" end) else b($ok;$t)+"~\($ok)/\($t) gp3 with Delete reclaim"+(if $u>0 then " (\($u) further EBS StorageClass(es) with a Delete reclaim policy set no parameters.type and were NOT graded: the volume type comes from the CSI driver default, which this review does not collect)" else "" end) end'
m lens-4 deployments 'if ([.items[]|select(.metadata.name|test("kubecost|opencost|cost-analyzer"))|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~cost tooling" else "none~none" end'
# lens-16 uses endswith(), not a regex (`test("ecr.api$")` treats `.` as any character). The suffix test is
# `endswith("."+$x)`, WITH the dot, so a service name that merely ends in `s3` or `sts` cannot match.
# The members are the four SERVICES asked for (denominator 4); each endpoint is `context` WITH ITS STATE, so
# `fail: s3` under a context line naming an s3 endpoint is not a contradiction (the cost-6/cost-8 form).
# ONLY AN `available` ENDPOINT COUNTS (not even a transient `pending`): ignoring `.State` would let `failed`,
# `rejected`, `deleted` and `pendingAcceptance` endpoints score `all~4/4` on traffic NOT leaving through the NAT gateway.
# A `Gateway` ENDPOINT COUNTS ONLY ON THE ROUTE TABLE OF EVERY NODE SUBNET: a subnet whose table lacks its
# route still reaches S3 through the NAT gateway. Node subnets: live instances' (every ENI, this VPC) and Fargate
# profiles'; a subnet's table is its explicit association, else the VPC main table. The union of the service's
# available Gateway endpoints must hold every such table; with none known, or one unresolved, NOT credited.
# A NON-Gateway ENDPOINT COUNTS ONLY WITHOUT `PrivateDnsEnabled: false` (default hostnames, `api.ecr.<region>...`,
# then resolve to public IPs: NAT gateway) and WITHOUT `DnsOptions.PrivateDnsOnlyForInboundResolverEndpoint: true`
# (S3's default: in-VPC S3 names stay public and use the Gateway endpoint judged above, or NAT). Missing = not set.
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
rl lens-16 vpcendpoints routetables instances fargateprofiles 'input as $rt|input as $inst|input as $fp|([$rt.RouteTables[]?|.VpcId//empty]|first) as $vpc|([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true)]|length>0)|.RouteTableId]|first) as $main|([$inst.Reservations[]?.Instances[]?|select((((.State.Name)//"")|IN("terminated","shutting-down"))|not)|if (.VpcId//"")==$vpc then ([.SubnetId]+[.NetworkInterfaces[]?.SubnetId]|.[]) else null end]+[($fp.profiles//[])[]?|(.subnets//[])[]]|unique) as $nsub|[$nsub[]|. as $sid|if $sid==null then null else (([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid)]|length>0)|.RouteTableId]|first)//$main) end] as $need|[.VpcEndpoints[]?] as $v|def gwok: .ServiceName as $s|([$v[]|select(.State=="available" and .VpcEndpointType=="Gateway" and .ServiceName==$s)|(.RouteTableIds//[])[]]) as $u|($need|length)>0 and (($need-$u)|length)==0;[$v[]|select(.State=="available")|select(.VpcEndpointType!="Gateway" or gwok)|select(.VpcEndpointType=="Gateway" or (.PrivateDnsEnabled!=false and .DnsOptions.PrivateDnsOnlyForInboundResolverEndpoint!=true))|(.ServiceName//"")] as $sn|["s3","ecr.api","ecr.dkr","sts"] as $want|[$want[]|select(. as $x|$sn|any(endswith("."+$x)))] as $p|{pass:$p,fail:($want-$p),context:[$v[]|(.ServiceName//"?")+" ("+((.State//"?")|tostring)+(if .VpcEndpointType=="Gateway" and ((.RouteTableIds//[])|length)==0 then ", Gateway, no route tables" elif .VpcEndpointType=="Gateway" and .State=="available" and (gwok|not) then (if ($need|length)==0 then ", Gateway, not credited: no node or Fargate profile subnet collected" else ", Gateway, not credited: not on the route table of every node subnet" end) elif .VpcEndpointType!="Gateway" and .PrivateDnsEnabled==false then ", private DNS disabled" elif .VpcEndpointType!="Gateway" and .DnsOptions.PrivateDnsOnlyForInboundResolverEndpoint==true then ", private DNS for inbound resolver endpoints only" else "" end)+")"]}'
m4 lens-16 vpcendpoints routetables instances fargateprofiles 'input as $rt|input as $inst|input as $fp|([$rt.RouteTables[]?|.VpcId//empty]|first) as $vpc|([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true)]|length>0)|.RouteTableId]|first) as $main|([$inst.Reservations[]?.Instances[]?|select((((.State.Name)//"")|IN("terminated","shutting-down"))|not)|if (.VpcId//"")==$vpc then ([.SubnetId]+[.NetworkInterfaces[]?.SubnetId]|.[]) else null end]+[($fp.profiles//[])[]?|(.subnets//[])[]]|unique) as $nsub|[$nsub[]|. as $sid|if $sid==null then null else (([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid)]|length>0)|.RouteTableId]|first)//$main) end] as $need|[.VpcEndpoints[]?] as $v|def gwok: .ServiceName as $s|([$v[]|select(.State=="available" and .VpcEndpointType=="Gateway" and .ServiceName==$s)|(.RouteTableIds//[])[]]) as $u|($need|length)>0 and (($need-$u)|length)==0;[$v[]|select(.State=="available")|select(.VpcEndpointType!="Gateway" or gwok)|select(.VpcEndpointType=="Gateway" or (.PrivateDnsEnabled!=false and .DnsOptions.PrivateDnsOnlyForInboundResolverEndpoint!=true))|.ServiceName] as $sn|([ "s3","ecr.api","ecr.dkr","sts"]|map(select(. as $x|$sn|any(endswith("."+$x))))|length) as $ok| b($ok;4)+"~\($ok)/4 endpoints available"'
```

**Governance (not assessed):** cost-4 (cross-AZ/region data-transfer monitoring),
cost-5 (storage requested-vs-used efficiency — needs in-pod usage).

---

## Cost Effective Resources

### cost-1: Are ResourceQuotas configured for namespaces to prevent resource over-consumption?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource quotas enforce cost governance by limiting what each team can consume.

**Commands:**
```bash
kubectl get resourcequotas -A -o json
kubectl get namespaces -o json
# Count namespaces with an unscoped (or NotTerminating-only) quota naming cpu or memory (cpu, memory,
# requests.cpu/.memory, limits.cpu/.memory), vs namespaces
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** A ResourceQuota that names `cpu` or `memory` changes what the namespace will **accept**,
not just how much it will hold. Upstream Kubernetes: "If you enforce a resource quota in a namespace for
either `cpu` or `memory`, you and other clients, must specify either `requests` or `limits` for that
resource, for every new Pod you submit. If you don't, the control plane may reject admission for that
Pod." The same page defines the short `cpu` and `memory` quota keys as "Same as `requests.cpu`" and "Same
as `requests.memory`", so `--hard=cpu=4,memory=8Gi` is what makes those declarations mandatory for every
container in the namespace. It is the **presence** of those two keys that does it, not the numbers —
raising the values does not soften it. ([Resource
Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/))

Nothing appears to break when you apply it: "Neither contention nor changes to quota will affect already
created resources." Running pods keep running, so the first rejection is the next pod something tries to
create — a rollout, a restart, a node replacement, hours or days later and looking unrelated to the
quota. A Deployment or ReplicaSet still applies cleanly, too; the 403 hits the controller's pod create,
so it shows up in `kubectl describe replicaset` and the namespace events rather than in the output of
`kubectl apply`. Find out who would be rejected first, then stage it:

```bash
# 1. Who would be rejected? A quota has no warn mode, and --dry-run=server on the quota object
#    validates only the quota -- it says nothing about existing pods -- so this is a manual check.
#    Lists every container and init container declaring neither a request nor a limit for cpu/memory:
kubectl get pods -n <ns> -o json | jq -r '.items[] | .metadata.name as $p
  | (.spec.initContainers[]?, .spec.containers[])
  | select((.resources.requests.cpu // .resources.limits.cpu) == null
        or (.resources.requests.memory // .resources.limits.memory) == null)
  | "\($p)\t\(.name)"'

# 2. If that printed anything, fix those specs -- or apply cost-2's LimitRange FIRST, which is
#    upstream's own answer: "You can define a LimitRange to force defaults on pods that make no
#    compute resource requirements (so that users don't have to remember to do that)."

# 3. A quota on object counts alone carries no such prerequisite, so it is safe on any namespace today.
kubectl create quota <name> -n <ns> --hard=pods=20

# 4. Size cpu/memory, then add them to the quota you already created.
kubectl top pods -n <ns> --containers   # needs metrics-server; the quota counts declared REQUESTS,
                                        # so treat live usage as a sanity check, not as the basis
kubectl patch resourcequota <name> -n <ns> --type=merge \
  -p '{"spec":{"hard":{"cpu":"4","memory":"8Gi","pods":"20"}}}'
```

`cpu=4,memory=8Gi,pods=20` are placeholders, not a recommendation. A quota set below what the namespace
already requests is accepted without complaint — existing pods are never evicted — and then blocks the
next deployment, so set the numbers from the namespace's real requests with headroom for a rolling
update's extra replica. Step 3 on its own does **not** satisfy this question: the detection counts a
namespace only once one of its unscoped (or NotTerminating-only) ResourceQuotas names `cpu` or `memory` (as `cpu`, `memory`,
`requests.cpu`, `requests.memory`, `limits.cpu` or `limits.memory` — a storage or object-count
quota does not count), because an object-count quota caps no compute and this question
is about compute over-consumption. Step 3 is still the safe first move — it is the step with no
prerequisite — but the namespace does not count until step 4 lands.

---

### cost-2: Are LimitRanges configured for namespaces to set default resource constraints?

**Detection:** 🔬 AUTO-DETECTABLE

> LimitRanges ensure containers without explicit requests/limits get sensible defaults.

**Commands:**
```bash
kubectl get limitranges -A -o json
kubectl get namespaces -o json
# Count namespaces with a Container or Pod limit naming cpu or memory, vs namespaces
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Apply LimitRanges per namespace: `kubectl apply -f` a LimitRange with default CPU/memory
requests and limits for containers without explicit values. Start with `defaultRequest` and `default`
only — those two mutate an incoming pod and reject nothing, which is what makes a LimitRange the safe way
to satisfy `cost-1`'s prerequisite. `min`, `max` and `maxLimitRequestRatio` are the parts that reject:
"if you attempt to create or update an object (Pod or PersistentVolumeClaim) that violates a LimitRange
constraint, your request to the API server will fail with an HTTP status code 403 Forbidden", and as with
a quota the failure is delayed — "LimitRange validations occur only at Pod admission stage, not on running
Pods. If you add or modify a LimitRange, the Pods that already exist in that namespace continue
unchanged." Two more traps from the same page: a `default` limit lower than a request a container already
declares leaves the pod unschedulable, because "a LimitRange does not check the consistency of the default
values it applies"; and "if two or more LimitRange objects exist in the namespace, it is not deterministic
which default value will be applied", so keep one per namespace. A `default` limit also caps a container
that previously had none, so a workload quietly bursting above it starts being CPU-throttled or OOM-killed
at its next restart — size the defaults from observed usage rather than round numbers.
([LimitRange](https://kubernetes.io/docs/concepts/policy/limit-range/))

---

### cost-3: Do you proactively optimize Pod hours by scaling down or terminating unnecessary Pods during off-peak hours, nights, and weekends?

**Detection:** 🔬 AUTO-DETECTABLE

> Evaluate cost optimization through workload scheduling and scaling.

**Remediation:** Implement pod scaling schedules using KEDA or CronJobs to scale down non-critical workloads during off-peak hours, nights, and weekends.

---

### cost-4: Are you proactively monitoring and measuring data transfer costs between Availability Zones, regions, and to the internet?

**Detection:** ✋ ASK USER

> Assess monitoring and optimization of network data transfer costs.

**Remediation:** Monitor cross-AZ data transfer using VPC Flow Logs and Cost Explorer. Use topology-aware routing to keep traffic within the same AZ where possible.

---

### cost-5: Is storage provisioning efficient (requested capacity vs provisioned capacity)?

**Detection:** ✋ ASK USER

> Over-provisioned storage wastes money on unused EBS capacity.

**Remediation:** Right-size storage PVC requests to match actual usage. Use `kubectl exec` to check filesystem usage inside pods and adjust PVC sizes accordingly.

---

## Expenditure and Usage Awareness

### cost-6: Are PersistentVolumes actively used (every PV Bound)?

**Detection:** 🔬 AUTO-DETECTABLE

> Unused PVs continue to incur EBS costs even when no workload is using them.

**Commands:**
```bash
kubectl get pv -o json
# Check status.phase: Bound is the only phase in which a PV is serving a claim. Released and
# Available are the common idle phases; Failed (reclamation failed) also leaves the backing EBS
# volume in place and billing, and Pending serves no claim either: the detection counts Bound only.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Snapshot anything you are not certain about first — `cost-8` and
[cost-analysis.md](cost-analysis.md) both require this before a volume delete, and a PV delete usually
implies one. Then remove the PV and its backing volume:

```bash
kubectl get pv <name> -o jsonpath='{.spec.claimRef}{"\n"}{.spec.csi.volumeHandle}{"\n"}'
aws ec2 create-snapshot --volume-id <vol-id> --description "pre-delete <name>" --region <REGION>
kubectl delete pv <name>
aws ec2 delete-volume --volume-id <vol-id> --region <REGION>   # only after the snapshot completes
```

> **If `kubectl delete pv` hangs in `Terminating`**, the PV carries the
> `kubernetes.io/pv-protection` finalizer and Kubernetes is waiting for the controller to clear it.
> That normally means the PV is still bound, or the CSI driver is unavailable. Fix the cause — delete
> the PVC that still references it, or restore the driver — rather than reaching for
> `kubectl patch pv <name> -p '{"metadata":{"finalizers":null}}'`. Stripping the finalizer removes the
> Kubernetes object while leaving the EBS volume behind, which converts a tidy-up into exactly the
> orphaned-and-billing volume `cost-8` reports.

---

### cost-7: Are cost allocation tags applied to the EKS cluster for chargeback?

**Detection:** 🔬 AUTO-DETECTABLE

> Cost tags enable attribution of EKS spend to teams, projects, or environments.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.tags"
# Look for cost/project/environment tags
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Apply cost allocation tags to the EKS cluster: `aws eks tag-resource --resource-arn <arn> --tags Team=<team>,Project=<project>,CostCenter=<cc>`.

---

### cost-8: Are the cluster's EBS volumes all attached (none idle and still billing)?

**Detection:** 🔬 AUTO-DETECTABLE — the scorer reads `volumes.json` (EC2); `pv.json` only names volume ids.

> An EBS volume in `State: available` is attached to nothing and still bills at full rate. These
> usually outlive a deleted PVC whose StorageClass had `reclaimPolicy: Retain`, or a node that was
> replaced without cleanup. `available` is not the only such state, which is why the detection counts
> `in-use` rather than counting everything that is not `available`: a `creating` or `deleting` volume
> is not attached either, and counts as a finding for as long as it lasts (normally minutes). `error`
> and `deleted` are left out of the count: `error` means the volume's underlying hardware failed and
> its data is unrecoverable, and AWS does not bill it; a `deleted` volume no longer bills.
>
> **Scope matters.** `describe-volumes` is collected region-wide with no filter, so the scorer
> narrows to volumes tagged for THIS cluster (`kubernetes.io/cluster/<name>`, or a tag whose key
> contains `cluster`, in any case, and whose value is the cluster name) or named by one of its PersistentVolumes,
> since the EBS CSI driver adds a cluster-name tag only when run with `--k8s-tag-cluster-id`. In a region that holds
> any volume that is not this cluster's, an unscoped read would bill this cluster for any of them left idle, and name them by VolumeId in the report.

**Remediation:** List the cluster's unattached volumes, confirm each is genuinely orphaned (check
`Tags` for a `kubernetes.io/created-for/pvc/name`), snapshot anything you are unsure about, then
delete:

```bash
# The set cost-8 fails, tag half: the scorer's own tag predicate, then every state except in-use, error
# (failed hardware, not billed) and deleted -- available, creating and deleting. No --filters form selects
# it: the predicate accepts any tag key containing "cluster" in any case. It also counts an untagged volume a
# PV names (`kubectl get pv`, .spec.csi.volumeHandle). Only an available volume can be deleted.
# On EKS Auto Mode, volumes it created after April 22, 2026 are hidden from this list call;
# the report names the idle ones the review recovered by ID.
aws ec2 describe-volumes --region <REGION> --output json \
  | jq --arg cn '<CLUSTER>' '[.Volumes[]|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0)|select((.State!="in-use") and (.State!="error") and (.State!="deleted"))|{Id:.VolumeId,State:.State,Size:.Size,Created:.CreateTime,Tags:.Tags}]'
```

Related but distinct: **PersistentVolumes** that are not `Bound` — `Released`, `Available`, `Failed`
or `Pending` — are a Kubernetes-object concern covered by `cost-6`. A Released or Failed PV leaves its
EBS volume in place, normally `available` (a failed reclaim does not put it in `error`, which is an EBS
hardware failure), so the two findings often appear together — report them as one root cause, not two.

---

## StorageClass cost defaults

<!-- This heading names what `cost-9` checks rather than "FinOps" -- one question, and not a FinOps practice
     question: it inspects the cluster's StorageClasses for gp3 and a `Delete` reclaim policy. Under
     "FinOps", an operator looking for chargeback, showback or cost tooling would find a StorageClass
     check instead; the nearest this pillar has are `cost-7` (cost allocation tags for chargeback) and
     `lens-4` (Kubecost/OpenCost). Nothing parses these `##` lines (the renderer keys on `### <id>: <title>`
     only), so the heading's only job is to tell a reader what is under it. -->

### cost-9: Are StorageClasses configured with cost-optimized volume types (gp3, Delete reclaim policy)?

**Detection:** 🔬 AUTO-DETECTABLE

> gp3 storage is about 20% cheaper than gp2 per GiB, and below ~1,000 GiB it is at or above gp2's baseline
> IOPS, though gp2 volumes of 334 GiB and larger sustain 250 MiB/s against gp3's default 125 MiB/s, so
> set `throughput: 250` for those volumes. Between 170 and 334 GiB gp2 reaches 250 MiB/s only by burst,
> and gp3 throughput above 125 MiB/s costs about $0.04 per MiB/s-month (N. Virginia list price; region-dependent),
> so there it can cost more than gp2 below about 250 GiB — add it only where the workload needs it.
> **Above ~1,000 GiB it is a performance downgrade unless you provision IOPS.** gp2's baseline scales at
> 3 IOPS/GiB, so it passes gp3's flat 3,000 IOPS at 1,000 GiB and keeps climbing to 16,000 — a 4 TiB gp2
> volume gets 12,000 baseline IOPS that a default gp3 volume would cut to 3,000.

**Remediation:** A StorageClass's `provisioner`, `parameters` and `reclaimPolicy` cannot be changed once it exists (the API server rejects the update), so do not edit the gp2 classes:
create a gp3 class (`provisioner: ebs.csi.aws.com`, or `ebs.csi.eks.amazonaws.com` on EKS Auto Mode; `parameters.type: gp3`; `reclaimPolicy: Delete` unless the volumes are meant to outlive their claims), move the `storageclass.kubernetes.io/is-default-class: "true"` annotation to it, and name it in new claims.

**Two things to know before you book the saving:**

1. **A StorageClass governs only volumes created from it.** Existing gp2 volumes keep their
   type, so this change saves nothing on current storage until each volume is migrated (in place and
   online with `aws ec2 modify-volume --volume-type gp3`, adding `--throughput 250` for a volume of
   334 GiB or larger and `--iops` where item 2 applies).
   Nothing in this review counts those existing volumes, so treat the saving as applying to future
   growth.
2. **For any volume at or above ~1,000 GiB, provision `iops: min(size × 3, 16000)`** (and matching
   `throughput`) on the gp3 class, or you trade a 20% storage saving for a baseline IOPS cut. Cap it:
   gp2's baseline stops climbing at 16,000 IOPS, reached at 5,334 GiB, and every larger gp2 volume gets
   the same 16,000 ([EBS User Guide](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html),
   verified 2026-09-11) — provisioning `size × 3` uncapped past that point asks gp3 for more IOPS than
   gp2 ever delivered, and you pay for IOPS gp2 never had. Provisioned IOPS above the free 3,000 carry
   their own charge, which erodes part of that 20% — so on large volumes this is a deliberate trade, not
   a free win.

See the gp2/gp3 crossover detail in [cost-analysis.md](cost-analysis.md).

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-4: Is cost visibility tooling (Kubecost/OpenCost) deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> Cost visibility enables chargeback and optimization decisions.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for kubecost or opencost
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Kubecost or OpenCost for cost visibility: `helm repo add kubecost https://kubecost.github.io/kubecost/ && helm repo update && helm install kubecost kubecost/kubecost --namespace kubecost --create-namespace --set global.clusterId=<cluster-name>` or deploy OpenCost via Helm.

---



### lens-16: Are VPC endpoints for S3, ECR, and STS configured and available?

**Detection:** 🔬 AUTO-DETECTABLE

> Where nodes reach these services through a NAT gateway, VPC endpoints remove its per-GB data-processing charge on that traffic and keep it off the internet path. This question does not check for a NAT gateway: without one, the case for the Interface endpoints (ecr.api, ecr.dkr, sts), which bill hourly per Availability Zone plus per GB, is private connectivity, not cost; the S3 Gateway endpoint carries no charge.

**Commands:**
```bash
aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<VPC_ID> --region <REGION>
# Look for s3, ecr.api, ecr.dkr, sts service names, and check State on each: only available
# carries traffic, so a failed/rejected/deleted/pendingAcceptance endpoint still routes those
# API calls through the NAT gateway and still bills for them. A Gateway endpoint (s3) also needs
# each node subnet's route table in RouteTableIds: a subnet whose table lacks its route does not use it.
# An Interface endpoint also needs PrivateDnsEnabled true (for s3, also DnsOptions without
# PrivateDnsOnlyForInboundResolverEndpoint true), or in-VPC hostnames still resolve to public IPs via NAT.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Create a Gateway endpoint for S3 on every node subnet's route table, and Interface endpoints with private DNS for ECR (.api and .dkr) and STS. Where nodes egress through a NAT gateway this removes its data-processing charge on image pulls and AWS API calls; where they do not, weigh the Interface endpoints' hourly charges against the private-connectivity benefit.

---
