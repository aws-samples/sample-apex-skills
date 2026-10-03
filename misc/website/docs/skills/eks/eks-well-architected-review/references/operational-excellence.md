---
title: "⚙️ Operational Excellence"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/operational-excellence.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/operational-excellence.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/operational-excellence.md). Edit the source, not this page.
:::

# ⚙️ Operational Excellence

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**24 questions** — IaC, GitOps, monitoring, logging, upgrade management, managed node groups, EKS addons

Scoring is **deterministic** — run the scorer block below; each measured question prints
`all`/`most`/`some`/`none`/`na` from `jq`. Governance questions (process-only) emit `unknown` (Not
Assessed). The per-question sections that follow give rationale and remediation for writing findings.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** They agree today — every `🔬 AUTO-DETECTABLE` section is emitted
> `measured` and every `✋ ASK USER` section is emitted `governance` — and if an edit ever makes them
> disagree, the SCORER IS AUTHORITATIVE: answer the question from the collected data. Use the prose
> for rationale and remediation wording only.

---

## Table of Contents

1. [Operational Excellence scorer — run by `assets/score.sh`, not by hand](#operational-excellence-scorer--run-by-assetsscoresh-not-by-hand)
2. [Infrastructure as Code](#infrastructure-as-code)
   - [ope-1: Do you provision your EKS cluster and worker nodes using Infrastructure as Code (IaC) tools such as Terraform, CloudFormation, or AWS CDK?](#ope-1-do-you-provision-your-eks-cluster-and-worker-nodes-using-infrastructure-as-code-iac-tools-such-as-terraform-cloudformation-or-aws-cdk)
   - [ope-2: Are AWS integrations (Load Balancer Controller, External DNS, EBS CSI Driver) deployed as EKS add-ons or controllers?](#ope-2-are-aws-integrations-load-balancer-controller-external-dns-ebs-csi-driver-deployed-as-eks-add-ons-or-controllers)
   - [ope-3: Do you use GitOps workflows (ArgoCD, Flux) to minimize direct kubectl access?](#ope-3-do-you-use-gitops-workflows-argocd-flux-to-minimize-direct-kubectl-access)
   - [ope-4: Are you using Helm charts or Kustomize for Kubernetes manifest templating?](#ope-4-are-you-using-helm-charts-or-kustomize-for-kubernetes-manifest-templating)
3. [Centralized monitoring and logging](#centralized-monitoring-and-logging)
   - [ope-5: Are control plane metrics monitored using CloudWatch Container Insights or Prometheus?](#ope-5-are-control-plane-metrics-monitored-using-cloudwatch-container-insights-or-prometheus)
   - [ope-6: Are EKS control plane logs (API server, audit, authenticator, controller manager, scheduler) enabled?](#ope-6-are-eks-control-plane-logs-api-server-audit-authenticator-controller-manager-scheduler-enabled)
   - [ope-7: Are worker node metrics (CPU, memory, disk) monitored using Node Exporter or CloudWatch?](#ope-7-are-worker-node-metrics-cpu-memory-disk-monitored-using-node-exporter-or-cloudwatch)
   - [ope-8: Are application logs forwarded to a centralized system (Fluent Bit, Fluentd, CloudWatch)?](#ope-8-are-application-logs-forwarded-to-a-centralized-system-fluent-bit-fluentd-cloudwatch)
   - [ope-9: Have you created CloudWatch alarms or alerts for API server 403/401 responses?](#ope-9-have-you-created-cloudwatch-alarms-or-alerts-for-api-server-403401-responses)
   - [ope-10: Is the CNI metrics helper deployed to monitor VPC CNI IP address allocation and ENI usage?](#ope-10-is-the-cni-metrics-helper-deployed-to-monitor-vpc-cni-ip-address-allocation-and-eni-usage)
   - [ope-11: Are you using AWS CloudTrail to audit EKS API calls and IRSA actions?](#ope-11-are-you-using-aws-cloudtrail-to-audit-eks-api-calls-and-irsa-actions)
   - [ope-12: Is Kubernetes audit logging enabled to track API authorization decisions?](#ope-12-is-kubernetes-audit-logging-enabled-to-track-api-authorization-decisions)
   - [ope-13: Do you have an ongoing upgrade plan aligned with the EKS Kubernetes version support lifecycle?](#ope-13-do-you-have-an-ongoing-upgrade-plan-aligned-with-the-eks-kubernetes-version-support-lifecycle)
   - [ope-14: Do you have a non-production test environment for validating EKS upgrades before production?](#ope-14-do-you-have-a-non-production-test-environment-for-validating-eks-upgrades-before-production)
   - [ope-15: Are worker nodes managed using EKS Managed Node Groups?](#ope-15-are-worker-nodes-managed-using-eks-managed-node-groups)
   - [ope-16: Are core EKS add-ons (VPC CNI, CoreDNS, kube-proxy) managed as EKS managed add-ons?](#ope-16-are-core-eks-add-ons-vpc-cni-coredns-kube-proxy-managed-as-eks-managed-add-ons)
4. [CronJob workload shape](#cronjob-workload-shape)
   - [ope-18: Do CronJobs set a concurrency policy other than the default Allow?](#ope-18-do-cronjobs-set-a-concurrency-policy-other-than-the-default-allow)
5. [EKS upgrade-readiness insights](#eks-upgrade-readiness-insights)
   - [ope-20: Do the EKS upgrade-readiness insights AWS computes for this cluster all pass?](#ope-20-do-the-eks-upgrade-readiness-insights-aws-computes-for-this-cluster-all-pass)
6. [Capacity Planning](#capacity-planning)
   - [ope-19: Do you perform regular capacity planning reviews to ensure your EKS cluster can handle projected growth, seasonal traffic spikes, and maintain adequate resource headroom for scaling?](#ope-19-do-you-perform-regular-capacity-planning-reviews-to-ensure-your-eks-cluster-can-handle-projected-growth-seasonal-traffic-spikes-and-maintain-adequate-resource-headroom-for-scaling)
7. [Fargate Profile Management](#fargate-profile-management)
   - [fargate-1: Are Fargate profile namespace selectors specific (not just default/kube-system)?](#fargate-1-are-fargate-profile-namespace-selectors-specific-not-just-defaultkube-system)
   - [fargate-2: Do Fargate pods have CPU and memory resource requests defined?](#fargate-2-do-fargate-pods-have-cpu-and-memory-resource-requests-defined)
   - [fargate-4: Is the Fargate built-in log router configured with a log destination?](#fargate-4-is-the-fargate-built-in-log-router-configured-with-a-log-destination)
8. [EKS Best Practices](#eks-best-practices)
   - [lens-1: Is Node Problem Detector deployed for node health monitoring?](#lens-1-is-node-problem-detector-deployed-for-node-health-monitoring)
   - [lens-7: Is the VPC CNI add-on managed, current, ACTIVE and free of reported health issues?](#lens-7-is-the-vpc-cni-add-on-managed-current-active-and-free-of-reported-health-issues)

---

## Operational Excellence scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh operational-excellence "$WORK"` extracts this block and runs it. Do
not paste it into a shell: it defines shell functions (`emit`, `rl`, `g`, `m`…) and calls them once per
question, and a Bash permission rule matches literal command text — so no rule can match a function name
and every call prompts, or fails outright under a no-prompt policy. Appends one JSONL line per question to
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
# Shape guard for every `rl` program below, applied by `rl` itself. The result must be an object with
# `pass` and `fail` arrays of STRINGS plus an optional `context` array of strings; anything else is
# recorded as a failure rather than written into results.jsonl. `{pass,fail}` rebuilds the object so
# extra keys cannot get through.
RQ='|if (type=="object") and ((.pass|type)=="array") and ((.fail|type)=="array") and (((.context//[])|type)=="array") and (([(.pass+.fail+(.context//[]))[]|select(type!="string")]|length)==0) and ((.kind==null) or (.kind=="field") or (.kind=="existence")) and ((.excluded==null) or (((.excluded|type)=="number") and (.excluded>=0) and ((.excluded|floor)==.excluded))) and ((.context_only==null) or ((.context_only|type)=="boolean")) then {pass,fail}+(if (.context|type)=="array" then {context} else {} end)+(if .kind!=null then {kind} else {} end)+(if .excluded!=null then {excluded} else {} end)+(if .context_only==true then {context_only:true} else {} end) else error("rl: the program did not return {pass:[string],fail:[string]} with optional context:[string], kind:field|existence, excluded:integer, context_only:boolean") end'
# BUILD THE RECORD WITH jq, NOT printf. `detail` is raw jq output and several questions interpolate
# cluster-controlled strings into it. With printf a `"` in a value would forge a duplicate `state` key
# and a newline would forge whole extra records in OTHER pillars. `--arg` escapes instead.
# Two details are load-bearing:
#   -c   without it results.jsonl stops being JSONL and score.sh's already-scored refusal breaks (it
#        greps the literal `"pillar":"operational-excellence"`, which only compact output reproduces).
#   ||   this block runs under `bash` with NO `set -e`. Guarded, one failing record aborts rc=1 and
#        names the question; unguarded, rc=0 with a record short.
# Key order stays pillar,id,track,state,detail (SKILL.md Step 5 documents the bytes); `resources` is a
# sixth key appended only for questions that ran `rl`.
# `--argjson` can fail on an oversized evidence list (`jq: Argument list too long`); the abort message names
# argument size as a likely cause.
# THE ID IS RE-ASSERTED, not assumed: a stale list from the previous question is dropped, never attached
# to this one.
# Five files carry this helper; if you change one, change all five.
emit(){ local rs=false
  if [ "${RESID:-}" = "$1" ]; then rs="${RES:-null}"; fi
  RES= RESID=
  jq -cn --arg id "$1" --arg tr "$2" --arg st "$3" --arg de "$4" --argjson rs "$rs" \
  '{pillar:"operational-excellence",id:$id,track:$tr,state:$st,detail:$de}+(if $rs==false then {} else {resources:$rs} end)' >> "$W/results.jsonl" \
  || { printf 'SCORER ABORT [%s]: the record was not emitted -- the jq call failed, the OS refused to start it, or the append to results.jsonl failed; any message jq or the OS printed is above. On a large fleet suspect the evidence list rather than the record: the list reaches jq as ONE --argjson argument, so many thousand names can exceed the OS argument-size limit and execve fails with "Argument list too long" before jq runs.\n' "$1" >&2; exit 1; }; }
# rl <id> <collection-file>... '<jq program>'  -- NAME the objects the next `emit` counted.
# The report prints `payments/api` rather than `7/9`: a correct count over the wrong set is the scoping bug a
# bare count hides. Names are built here, in jq, so no second language re-implements the detection (jq
# `select(.x)` keeps `{}`, `[]`, `""` and `0`; Python's `bool()` rejects them).
# A question with no `rl` line publishes no list; a question stays unconverted when its `m` program has already
# flattened away the identity a name needs, and restructuring a `select(...)` chain to recover it can silently
# change the verdict.
# It is a SEPARATE jq call so that evidence cannot cost the pillar its score: every scorer line aborts
# on failure, so `rl` swallows its own failure, records `resources: null`, and the `m` line scores the
# question as it would have. Three states: no `resources` key = no list published; `null` = the list
# could not be built; `[]` = the check looked and found nothing.
# The selection test appears twice (in `rl` and in `m`), so the report checks the list's counts against the ratio
# in `detail`. Write `fail` as the complement (`$all - $pass`) so the test appears once inside `rl`.
# `rl` emits unadorned arrays of strings only; sorting, "showing 12 of N" and labels are the renderer's.
# The failure reason: jq's stderr goes to $RLERR (`rl.stderr` inside the per-run `.eks-war-scorer.<pillar>.<pid>/`
# directory score.sh made, never a fixed name in $W). The query is NOT re-run to recover the text: a
# second execution can fail differently. With RLERR unset, stderr goes to /dev/null; jq's words are
# quoted only when the file is a writable regular file, so an earlier call's text is never shown.
rl(){ local id="$1"; shift; local fs=(); while [ "$#" -gt 1 ]; do fs+=("$W/$1.json"); shift; done; local r n q e= ef="${RLERR:-/dev/null}"; r=$(jq -c "$B $1 $RQ" "${fs[@]}" 2>"$ef"); q=$?; if [ "$q" = 0 ] && [ -n "$r" ] && n=$(printf '%s' "$r" | wc -l | tr -d ' ') && [ "$n" = 0 ]; then RES="$r" RESID="$id"; else RES=null RESID="$id"; if [ ! -f "$ef" ] || [ ! -w "$ef" ]; then e="jq's stderr could not be captured to $ef, so any OS message is on the line above"; else [ -s "$ef" ] && e=$(tr -s '[:space:]' ' ' < "$ef"); e="${e# }"; e="${e% }"; [ -n "$e" ] && e="; jq said: $e"; if [ "$q" != 0 ]; then e="jq exited $q$e"; elif [ -z "$r" ]; then e="jq exited 0 and produced no output at all$e"; else e="jq exited 0 but produced $((n+1)) results, and an evidence list is exactly one$e"; fi; fi; printf 'RESOURCE LIST SKIPPED [%s]: the evidence list could not be built -- %s. THE VERDICT IS UNAFFECTED -- this is not a finding and not a scoring error; the report will say that this step failed and that there is no list for this question.\n' "$id" "$e" >&2; fi; return 0; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Three inputs, for the questions that read three collection files. `input` yields f2 then f3.
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Four inputs. Byte-identical to the `m4` in reliability.md and cost-optimization.md; security/identity-access.md carries a
# variant that adds `$PE`. ope-2 and fargate-4 call `m5` below, not this.
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# `m5` IS `m4` PLUS ONE INPUT FILE. ope-2 needs a FARGATE signal (nodes.json) because its block-storage
# slot cannot be used on Fargate; leaving it in the denominator would mark a Fargate-only cluster down
# for lacking an EBS CSI driver that could serve nothing. Nothing tabulates helper names:
# render-report.py's `_helper_arity` reads the number out of the name (`^(m\d*)`).
m5(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" f5="$6" p="$7" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" "$W/$f5.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

g ope-1
# ope-2 credits each of its three integration slots SEPARATELY. On EKS Auto Mode two are cluster
# capabilities, not installed objects; matching names alone would score an Auto Mode cluster 0/3 for not
# installing what AWS already runs. Sources:
#   LOAD BALANCER -- credited when cluster.kubernetesNetworkConfig.elasticLoadBalancing.enabled is true
#   (docs.aws.amazon.com/eks/latest/userguide/auto-configure-nlb.html: no additional controller needed).
#   BLOCK STORAGE -- credited when cluster.storageConfig.blockStorage.enabled is true AND a StorageClass
#   with provisioner `ebs.csi.eks.amazonaws.com` exists. BOTH, because
#   docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html says Auto Mode does not create a
#   StorageClass; the flag alone would pass a cluster that can provision nothing. The controller is AWS's to run
#   (docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html).
#   EXTERNAL-DNS -- stays measured: it is not an Auto Mode capability, so a faithful Auto Mode cluster
#   with a StorageClass and no external-dns reads `some` 2/3, not `all`.
# ON FARGATE-ONLY COMPUTE THE DENOMINATOR IS 2: only block storage leaves (ebs-csi.html: "You can't mount Amazon
# EBS volumes to Fargate Pods."). The other two stay in (docs.aws.amazon.com/eks/latest/userguide/fargate.html:
# NLB/ALB work with IP targets only; external-dns is an ordinary Deployment). EFS is NOT substituted for EBS: the
# slot is dropped, not replaced. The `N/3` in the detail is safe because ope-2 publishes no `rl` line, so
# resource_agreement() has nothing to cross-check it against.
# AN ADD-ON CREDITS A SLOT ONLY WHEN WORKING: its `.addonDetails[]` entry is ACTIVE with no
# `health.issues` (the predicate ope-16 and lens-1 use). `.addons` is a list of NAMES, so membership
# alone would credit an add-on in CREATE_FAILED or DEGRADED. A broken add-on falls through to the
# ready-Deployment test. The load balancer slot has no add-on test (AWS publishes no EKS add-on for the
# AWS Load Balancer Controller). When a slot is not credited but its add-on is installed, the gap
# names the add-on's status (`_brk`).
m5 ope-2 deployments addons storageclasses cluster nodes 'input as $ad|def _brk($p;$l): ([(($ad.addonDetails)//[])[]|select((.addonName//"")|test($p))]|first) as $x|if $x==null then "no "+$l else "no working "+$l+" (the "+($x.addonName)+" add-on is installed, status "+(($x.status)//"unknown")+(if ([$x.health.issues[]?]|length)>0 then ", health issue(s): "+([$x.health.issues[]?|(.code//"unknown")]|join(", ")) else "" end)+")" end;input as $sc|input as $cl|input as $n|[.items[]?|select((.status.readyReplicas|numbers)>0)|.metadata.name] as $dn|[(($ad.addonDetails)//[])[]|select(((.status//"")=="ACTIVE") and (([.health.issues[]?]|length)==0))|(.addonName//"")] as $ao|($dn|any(test("aws-load-balancer-controller"))) as $lbdep|(($dn|any(test("ebs-csi"))) or ($ao|any(test("ebs-csi")))) as $stdep|(($dn|any(test("external-dns"))) or ($ao|any(test("external-dns")))) as $dnsdep|(($cl.cluster.kubernetesNetworkConfig.elasticLoadBalancing.enabled)==true) as $autolb|(($cl.cluster.storageConfig.blockStorage.enabled)==true) as $autobs|([$sc.items[]?|select((.provisioner//"")=="ebs.csi.eks.amazonaws.com")]|length>0) as $autosc|(([$n.items[]?]|length)>0) as $any|([$n.items[]?|select(isec2)]|length) as $ec2|([$n.items[]?|select(ishy)]|length) as $hy|($any and $ec2==0 and $hy>0) as $hyonly|($any and $ec2==0 and $hy==0) as $fgonly|($fgonly or $hyonly) as $nobs|($lbdep or $autolb) as $lbok|($stdep or ($autobs and $autosc)) as $stok|([$lbok,(if $nobs then empty else $stok end),$dnsdep]|map(select(.))|length) as $ok|(if $nobs then 2 else 3 end) as $den|[(if $lbdep then "aws-load-balancer-controller deployed" elif $autolb then "Auto Mode load balancing (kubernetesNetworkConfig.elasticLoadBalancing.enabled=true)" else empty end),(if $nobs then empty elif $stdep then "an EBS CSI driver is deployed" elif ($autobs and $autosc) then "Auto Mode block storage (storageConfig.blockStorage.enabled=true) plus a StorageClass on ebs.csi.eks.amazonaws.com" else empty end),(if $dnsdep then "external-dns deployed" else empty end)] as $cred|[(if $lbok then empty else "no load balancer controller" end),(if $nobs then empty elif $stok then empty else (if ($autobs and ($autosc|not)) then "Auto Mode block storage is enabled but no StorageClass references ebs.csi.eks.amazonaws.com, so nothing can be provisioned" else _brk("ebs-csi";"EBS CSI driver") end) end),(if $dnsdep then empty else _brk("external-dns";"external-dns") end)] as $gap| b($ok;$den)+"~\($ok)/\($den) integrations\(if $fgonly then " (block storage is out of the denominator on Fargate-only compute: EBS volumes cannot be mounted to Fargate pods, so an EBS CSI driver would have nothing to serve)" elif $hyonly then " (block storage is out of the denominator: there is no EC2 node here and \($hy) EKS Hybrid Node(s), and AWS documents that Amazon EBS volumes and the Amazon EBS CSI driver are not compatible with hybrid nodes, so an EBS CSI driver would have nothing to serve)" else "" end); credited: \(if ($cred|length)>0 then ($cred|join(", ")) else "none" end); gap: \(if ($gap|length)>0 then ($gap|join(", ")) else "none" end)"'
# ope-3 credits Argo CD by a ready Deployment named *argocd-repo-server -- a Deployment present in all three upstream
# install manifests (full, core, HA) and in the argo-helm chart's default names -- and Flux by its controllers in
# flux-system (an app placed there is no GitOps controller). A name that merely CONTAINS argocd is not credited.
m ope-3 deployments 'if ([.items[]|select(((.metadata.name//"")|test("argocd-repo-server$")) or ((.metadata.namespace//"")|test("fluxcd")) or ((.metadata.name//"")|test("fluxcd")) or (((.metadata.namespace//"")=="flux-system") and ((.metadata.name//"")|test("^(source|kustomize|helm|notification|image-reflector|image-automation)-controller$"))))|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~gitops present" else "none~no gitops" end'
g ope-4
# ope-5 searches DaemonSets and container IMAGES as well as Deployment names: CloudWatch Container
# Insights ships its agent as a DaemonSet and Amazon Managed Prometheus is scraped by an ADOT collector.
# DUPLICATED PROGRAM -- EDIT BOTH OR NEITHER. The jq below is byte-identical to rel-13's (find it with
# `grep -n "^rl rel-13 \|^m3 rel-13 " references/reliability.md`). Nothing enforces the match; if they
# drift, one cluster fact gets two verdicts (monitored here, unmonitored in Reliability).
# ope-5's `rl` names ALL THREE sets the `m` line counts (Deployments, DaemonSets, images), so the list
# has exactly `$n` members; the detail carries no leading `N/M`, so no cross-check would see a gap.
# AN OPERATOR IS NOT A COLLECTOR (rel-23's rule; rel-13's note gives the cases): a name or image containing
# `operator` is not credited, nor is a Deployment or DaemonSet whose pod template runs such an image, so the
# CloudWatch add-on's controller-manager and `opentelemetry-operator` alone do not pass; their collectors do.
# THE IMAGE ARM CARRIES POD IDENTITY: `q` is bound to the POD before the container loop, so the list prints pod
# and namespace instead of a bare image.
# A MONITORING WORKLOAD THAT RUNS NO REPLICA IS NOT MONITORING: the Deployment and DaemonSet arms require
# `.status.readyReplicas` / `.status.numberReady` (a `replicas: 0` grafana would otherwise publish `all`).
# `|numbers` RATHER THAN `//0`: `//0` fails open on a NON-NUMERIC value, as jq orders every string above every
# number (`("3"//0)>0` is true); `numbers` yields nothing for null, boolean or string.
# THE POD-IMAGE ARM TAKES TWO CLAUSES, EACH CATCHING WHAT THE OTHER MISSES: `.status.phase` must be
# `Running` AND the matching container's `containerStatuses` entry must be `ready`. Phase alone credits
# a CrashLoopBackOff pod (still `Running`, but the Deployment arm already drops it, so this arm would be
# a false Pass). Readiness alone credits a pod on an unreachable node (phase `Unknown` with the LAST
# reported `ready: true`).
# `Running`, not a terminal-phase exclusion: a Pending agent is not monitoring NOW.
# The readiness clause is PER CONTAINER, matched by NAME in the same pod's `containerStatuses` (a pod can
# run a ready monitoring container beside an unready sidecar). A container with no readiness probe is
# reported `ready: true` once started, so no correctly-configured agent loses credit.
# KNOWN AND BOUNDED: a pod in graceful termination still `ready` is credited for one snapshot; the other
# arms carry the same race, and testing `.metadata.deletionTimestamp` would drop pods of an ordinary
# rolling update that are still collecting metrics. Windows pins are skipped (`iswinspec`/`iswinpod`).
rl ope-5 deployments daemonsets pods 'input as $ds|input as $p|($ds|winds) as $w|def q: ((.metadata.namespace)//"")+"/"+((.metadata.name)//"?");([.items[]?|select(.spec.template.spec|iswinspec|not)|select(((.metadata.name)//"?")|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((((.metadata.name)//"?")|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.readyReplicas|numbers)>0)|"Deployment "+q]+[$ds.items[]?|select(.spec.template.spec|iswinspec|not)|select(((.metadata.name)//"?")|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((((.metadata.name)//"?")|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.numberReady|numbers)>0)|"DaemonSet "+q]+[$p.items[]?|select(iswinpod($w)|not)|select((.status.phase//"")=="Running")|q as $pod|[.status.containerStatuses[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(((.image)//"")|test("prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel";"i"))|select((((.image)//"")|test("node-exporter|operator";"i"))|not)|select(.name as $cn|$rdy|any(.==$cn))|"Pod "+$pod+" image "+((.image)//"?")]) as $hits|{pass:$hits,fail:[],kind:"existence"}'
m3 ope-5 deployments daemonsets pods 'input as $ds|input as $p|($ds|winds) as $w|(([.items[]?|select(.spec.template.spec|iswinspec|not)|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((.metadata.name|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.readyReplicas|numbers)>0)]|length) + ([$ds.items[]?|select(.spec.template.spec|iswinspec|not)|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))|select((.metadata.name|test("node-exporter|operator";"i"))|not)|select(any(.spec.template.spec.containers[]?;((.image|strings)//"")|test("operator"))|not)|select((.status.numberReady|numbers)>0)]|length) + ([$p.items[]?|select(iswinpod($w)|not)|select((.status.phase//"")=="Running")|[.status.containerStatuses[]?|select(.ready==true)|.name] as $rdy|.spec.containers[]?|select(((.image)//"")|test("prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel";"i"))|select((((.image)//"")|test("node-exporter|operator";"i"))|not)|select(.name as $cn|$rdy|any(.==$cn))]|length)) as $n| if $n>0 then "all~\($n) monitoring workload(s)/image(s)" else "none~none" end'
# `pass` is the scorer's OWN numerator set (`$on`, every enabled type) rather than the five wanted, so
# if EKS enables a sixth type the report's count check trips on the fixed denominator of 5. `fail` is
# the wanted types that are off.
rl ope-6 cluster '([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]]|unique) as $on|["api","audit","authenticator","controllerManager","scheduler"] as $want|{pass:$on,fail:[$want[]|select(. as $x|($on|index($x))|not)]}'
m ope-6 cluster '([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]]|unique|length) as $ok| b($ok;5)+"~\($ok)/5 log types"'
# ope-7 is an existence check -- `all` iff a DaemonSet named node-exporter or cloudwatch-agent has a
# ready pod (numberReady) -- so `fail` is empty by construction; Linux EC2 and hybrid nodes are CONTEXT.
# They make the question `na` on Fargate-only compute.
# WINDOWS NODES ARE NOT ASSESSED (Linux nodes only). `islinux` keeps them out of the node count; every
# graded detail carries `winx`; a cluster whose only non-Fargate nodes are Windows answers `winna`,
# ahead of the Fargate arm. `_lxds` drops a DaemonSet whose pod template can only schedule onto Windows
# (`iswinspec`), so it never credits Linux nodes. ope-8 and lens-1 carry the same `_lxds` clause.
rl ope-7 daemonsets nodes 'def _lxds: (.spec.template.spec//{})|iswinspec|not;input as $n|[$n.items[]?|select(iswin and isec2)] as $wn|([$n.items[]?|select(islinux)]|length) as $ec2|([$n.items[]?|select(ishy)]|length) as $hy|("\($wn|length) Windows node(s) not assessed — this skill supports Linux nodes only") as $wl|if (([$n.items[]?|select(islinux or ishy)]|length)==0 and ($wn|length)>0) then {pass:[],fail:[],context:([$wl]+[$wn[]|((.metadata.name)//"?")]),context_only:true} else ([.items[]?|select(((.metadata.name)//"?")|test("node-exporter|cloudwatch-agent"))|select(_lxds)|select((.status.numberReady|numbers)>0)] as $hit|{pass:[$hit[]|((.metadata.namespace)//"")+"/"+((.metadata.name)//"?")],fail:[],context:([$n.items[]?|select(islinux or ishy)|((.metadata.name)//"?")+(if ishy then " (EKS Hybrid Node)" else "" end)]+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end)),kind:"existence"}) end'
m2 ope-7 daemonsets nodes 'def _lxds: (.spec.template.spec//{})|iswinspec|not;input as $n|([$n.items[]?|select(islinux)]|length) as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0 and $hy==0) then (if $w>0 then winna($w) else "na~no DaemonSets possible on Fargate compute" end) elif ([.items[]|select(.metadata.name|test("node-exporter|cloudwatch-agent"))|select(_lxds)|select((.status.numberReady|numbers)>0)]|length)>0 then "all~"+([.items[]|select(.metadata.name|test("node-exporter|cloudwatch-agent"))|select(_lxds)|select((.status.numberReady|numbers)>0)|if (.metadata.name|test("node-exporter")) then "node-exporter" else "cloudwatch-agent" end]|unique|join(", "))+winx($w) else "none~none"+winx($w) end'
# A LOG FORWARDER THAT RUNS NO POD FORWARDS NO LOGS, so the DaemonSet must be UP (`.status.numberReady`,
# same `|numbers` form as ope-5) and not merely named. Other questions carry the same clause. Without
# it a zero-node cluster with a matching DaemonSet at desired 0 would publish `all~log forwarder`.
# NO `rl` TWIN AND NO RATIO: the detail is the bare token `log forwarder`.
# HYBRID NODES STILL COUNT: `numberReady` counts a pod wherever it is scheduled.
# WINDOWS NODES DO NOT: `test("fluent")` also matches `fluent-bit-windows`, so `_lxds` drops a forwarder
# that can only schedule onto Windows before the name test credits it.
m2 ope-8 daemonsets nodes 'def _lxds: (.spec.template.spec//{})|iswinspec|not;input as $n|([$n.items[]?|select(islinux)]|length) as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0 and $hy==0) then (if $w>0 then winna($w) else "na~DaemonSet log forwarding impossible on Fargate; fargate-4 scores the sidecar log router instead" end) elif ([.items[]|select(.metadata.name|test("fluent"))|select(_lxds)|select((.status.numberReady|numbers)>0)]|length)>0 then "all~log forwarder"+winx($w) else "none~none"+winx($w) end'
g ope-9
# ope-10 answers `na` ON AUTO MODE -- the ONE Auto Mode conversion in this file that is NOT a credit.
# The question asks whether the CNI metrics helper is deployed to monitor VPC CNI IP allocation and ENI usage. On
# Auto Mode the object is gone AND the outcome is not delivered by default, so `none` would print a remediation
# that cannot be followed and `all` would claim visibility the operator lacks.
#   docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html: Auto Mode needs no networking add-ons, so
#   there is no VPC CNI DaemonSet for a metrics helper to read.
#   docs.aws.amazon.com/eks/latest/userguide/auto-managed-component-logs.html: IPAM logs (AUTO_MODE_IPAM_LOGS)
#   need separate log delivery, off by default, so the visibility is ABSENT, not inapplicable.
# THIS COSTS THE OPERATOR SOMETHING REAL: Auto Mode "defaults to using prefix delegation (/28 prefixes)"
# (docs.aws.amazon.com/eks/latest/userguide/auto-networking.html), so subnet pressure is HIGHER. net-1 counts FREE
# ADDRESSES, not free /28 blocks.
# SCOPE OF THE GATE: EVERY EC2 NODE MUST BE AN AUTO MODE NODE, not merely the cluster flag. A flag-only
# gate would answer `na` on a MIXED-MODE cluster whose other nodes still run the VPC CNI DaemonSet.
#   docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html: "if your cluster combines Auto mode with other
#   compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate, these add-ons remain
#   necessary."
#   docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html: Auto Mode and self-managed Karpenter
#   may coexist.
# The membership test is the documented label `eks.amazonaws.com/compute-type: auto`
# (docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html,
# docs.aws.amazon.com/eks/latest/userguide/associate-workload.html). Fargate nodes are out of the denominator and
# $t>0 is required so an empty cluster is never vacuously credited.
# ONE GATE, SPELLED BY 11 QUESTIONS (ope-10, ope-15, ope-16, lens-1 and lens-7 here; lens-2 and lens-3
# in references/reliability.md; sec-21, sec-30 and net-3 in references/security/identity-access.md;
# perf-6 in references/performance-efficiency.md). CHANGE ONE, CHANGE ALL 11. The documented exceptions:
# rel-4 reads the cluster flag alone, and sec-4 tests nodes, not the flag. render-report.py holds no copy of
# the gate. Take the census rather than trusting any count in a comment, from the skill directory:
#   grep -rF '($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t' references/ | grep -v ':[[:space:]]*#' | cut -d: -f1 | sort | uniq -c
# (`-F` because BSD grep reads `$` as an anchor; the comment filter because a comment quoting the rule would
# otherwise be counted.) Five of them (lens-7, ope-15, ope-16, perf-6, sec-30) spell the gate on their `rl`
# line as well as their `m` line, so lines exceed questions.
# On a mixed-mode cluster the question FALLS THROUGH to measuring the helper: `aws-node` is on the
# non-Auto-Mode nodes, so its absence is a genuine gap; the detail also says Auto Mode nodes still need
# AUTO_MODE_IPAM_LOGS delivery.
# COVERAGE COUPLING: this `na` is coupled to ope-16 and lens-7's `all`. Narrowing ope-16 or lens-7 back to
# `na` on an all-Auto-Mode cluster while leaving this `na` is the edit to refuse: `na` for a subject
# only PARTLY absent is a silent free pass on the part that is present (reduce.sh withholds a pillar
# when applicable*2 < total). On a mixed-mode cluster all three measure.
# WINDOWS NODES ARE NOT ASSESSED in ope-10, ope-15, ope-16, lens-1 and lens-7 (Linux nodes only). `$t` counts
# `islinux` nodes; `$w` counts the Windows EC2 nodes left out; every graded arm carries `winx($w)`; `winna`
# answers only when nothing else can grade the cluster. `$fg` counts Fargate nodes. ope-10 answers `na` on
# Fargate-only compute: the helper instruments the aws-node DaemonSet and "Daemonsets aren't supported on
# Fargate" (docs.aws.amazon.com/eks/latest/userguide/fargate.html). ope-15's Fargate and hybrid arms only answer
# `na`; lens-1 grades hybrid nodes and answers `na` on Fargate, so its `winna` needs no hybrid node.
# NO VPC CNI, NO HELPER: on EC2 nodes running another CNI, kube-system/aws-node is absent or (Cilium's documented
# ENI-mode install) patched with a nodeSelector so it schedules onto no node. The helper reads the metrics aws-node's
# ipamd publishes, so there is nothing to instrument and ope-10 answers `na`, as on hybrid nodes.
m4 ope-10 deployments nodes cluster daemonsets 'input as $n|input as $cl|input as $ds|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))] as $an|(($an|length)==0) or ($an|all((.status.desiredNumberScheduled//-1)==0))) as $nocni|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|([$n.items[]?|select((isec2|not) and (ishy|not))]|length) as $fg|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto| if ($t==0 and $fg==0 and $w>0) then winna($w)+hyx($hy) elif ($t==0 and $hy==0 and $fg>0) then "na~Fargate compute: there is no Linux EC2 node, and a cni-metrics-helper reports what the aws-node DaemonSet allocates on worker nodes; DaemonSets are not supported on Fargate, where AWS deploys a version of the VPC CNI with each Fargate node, so there is nothing here for the helper to instrument"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "na~auto mode manages VPC CNI IP and ENI allocation itself: every \(if $w>0 then "Linux " else "" end)EC2 node is an Auto Mode node (eks.amazonaws.com/compute-type=auto), so there is no VPC CNI DaemonSet for a cni-metrics-helper to instrument and it cannot be deployed. The equivalent visibility is the AUTO_MODE_IPAM_LOGS log type, which stays off until you configure CloudWatch Vended Logs delivery for it"+hyx($hy)+winx($w) elif ($t==0 and $hy>0) then hyna($hy;"a cni-metrics-helper reports the IP and ENI allocation of the Amazon VPC CNI, and AWS documents that the VPC CNI is not compatible with hybrid nodes and configures its aws-node DaemonSet with anti-affinity for the eks.amazonaws.com/compute-type=hybrid label, so there is no VPC CNI here to instrument")+winx($w) elif ([.items[]|select(.metadata.name|test("cni-metrics-helper"))|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~cni metrics helper"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t==0) then "na~no EC2 nodes" elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or $hy==0)) then "none~Auto Mode compute is enabled but only \($auto) of \($t) EC2 nodes are Auto Mode nodes; the rest still run the VPC CNI DaemonSet, so a cni-metrics-helper is deployable for them and none is deployed — and the Auto Mode nodes need the AUTO_MODE_IPAM_LOGS delivery on top of that"+winx($w) elif ($t>0 and $nocni) then "na~no node runs the Amazon VPC CNI: the kube-system/aws-node DaemonSet is absent or schedules onto none of the \($t) Linux EC2 node(s), so this cluster uses another CNI, and a cni-metrics-helper reads the IP and ENI metrics that aws-node publishes"+hyx($hy)+winx($w) else "none~none"+winx($w) end'
# ope-11 IS BINARY: IS THE CLUSTER'S REGION COVERED BY A TRAIL? One multi-region trail, or one homed in
# the cluster region, is enough, so any covering trail answers `all`. Hardcoding `all` beside a `1/3`
# ratio would trip reduce.sh's state-vs-ratio gate (ope-11 is NOT in RATIO_STATE_EXEMPT) and abort the
# whole reduction; banding on the ratio would mark a covered region down for a trail covering some OTHER
# region. So the trail ratio LEADS the detail only when it is N/N; otherwise the detail leads with the
# region and says "2 of 3", and `rl` files non-covering trails as `context`. collect.sh calls
# describe-trails in the cluster's region, which returns trails homed there plus multi-region shadows.
rl ope-11 cloudtrail cluster 'input as $cl|((($cl.cluster.arn//"")|split(":"))[3]//"") as $rg|[(.trailList//[])[]] as $tr|[$tr[]|select((.IsMultiRegionTrail==true) or ((.HomeRegion//"")==$rg))] as $p|def n: (.Name//"?")+" ("+(if .IsMultiRegionTrail==true then "multi-region" else "home region "+(.HomeRegion//"") end)+")";if ($p|length)>0 then {pass:[$p[]|n],fail:[]}+(if ($tr-$p)==[] then {} else {context:[($tr-$p)[]|n]} end) else {pass:[],fail:[$tr[]|n]} end'
m2 ope-11 cloudtrail cluster 'input as $cl|((($cl.cluster.arn//"")|split(":"))[3]//"") as $rg|((.trailList//[])|length) as $t|[(.trailList//[])[]|select((.IsMultiRegionTrail==true) or ((.HomeRegion//"")==$rg))] as $cov| if $t==0 then "none~no trail" elif ($cov|length)==0 then "none~\($t) trail(s) exist but none is multi-region or homed in \($rg)" elif ($cov|length)==$t then "all~\($t)/\($t) trail(s) cover \($rg) (configuration only — IsLogging requires get-trail-status, which this review does not collect)" else "all~\($rg) is covered: \($cov|length) of \($t) trail(s) are multi-region or homed there, and one is enough (\($t-($cov|length)) other trail(s) are neither, listed as context; configuration only — IsLogging requires get-trail-status, which this review does not collect)" end'
m ope-12 cluster '"na~deduplicated: the audit on/off fact is scored as sec-26 (Security) and is 1 of the 5 log types in ope-6, where a disabled audit log lowers that ratio (e.g. 4/5 = most) rather than failing it"'
g ope-13
g ope-14
# ope-15 scores node COVERAGE: one managed node group must not read a mostly-Karpenter cluster as fully
# managed. Nodes in an MNG carry the eks.amazonaws.com/nodegroup label.
# AUTO MODE ANSWERS `all`, NOT `na`: `na` says the question does not apply, `all` says the control is
# met, and on Auto Mode it is, by a mechanism AWS recommends over managed node groups
# (docs.aws.amazon.com/eks/latest/userguide/automode.html: Karpenter-based scaling, 21-day maximum node lifetime,
# AWS-chosen AMI). The subject (nodes) exists and is managed. `na` would also drop OpEx below the 50% coverage
# gate. ope-16 and lens-7 answer `all` on Auto Mode for the same reason; `na` stays right where the outcome is not
# delivered: net-3 and ope-10.
# A MIXED-MODE CLUSTER IS NOT GIVEN THE ALL-AUTO-MODE ANSWER. Unlike ope-10/16, lens-1 and lens-7 (which credit a
# NODE-SCOPED capability), this asks whether nodes are MANAGED, and on a mixed cluster every node is, by different
# mechanisms. The band is ARITHMETIC: managed = (Auto Mode nodes UNION node-group nodes), a union so a node with
# both labels is not double-counted, over every EC2 node. A self-managed node is in neither and lowers the band.
# Flag on but nodes carrying neither label scores `none`. The mixed-mode arm names both populations with counts.
# NO LEADING `N/M` RATIO ON THE ARM WHERE `rl` TAKES THE `kind:"field"` BRANCH. `rl` short-circuits there when the
# flag is on and every EC2 node (at least one) is Auto Mode (`islinux` excludes hybrid and Windows), emitting 1
# pass, 0 fail; a detail beginning "3/3" would be compared to that 1/1 by resource_agreement() and the render
# would exit 1. Both `m3` arms behind that test lead with prose. With the flag on, EC2 nodes not all Auto Mode,
# plus hybrid nodes, `m3` leads with "$man/$t" but `rl` has left the field branch and lists the same EC2 nodes,
# so ratio and list agree. A change to either line's branch test has to be made to both. Without hybrid nodes the
# mixed-mode arm leads with prose. The standard-cluster arm keeps "\($mng)/\($t)"; it would disagree with `rl`
# only with the flag off and an EC2 node labelled compute-type=auto.
# ope-15's members are the EC2 NODES, not the node groups: a self-managed or Karpenter node belongs to
# no group, so a group list reads 1/1 exactly when coverage is worst. `pass` is the UNION `m` counts as
# `$man` and `fail` is its complement, so the test appears once.
# The Auto Mode arm is a field, not a count: it emits `kind:"field"` and the member IS that field, with
# the nodes in `context`. NO `context_only:true` there: the panel would then read "nothing above should
# be read as an object that passed or failed" beneath the `computeConfig.enabled = true` member that
# produced the `all` -- a false sentence in rendered prose. What keeps the renderer safe is the ABSENCE
# OF A RATIO on that arm (every EC2 node is Auto Mode and hybrid is out of the population, so N/N says
# nothing). DO NOT put a count back into that arm's detail, and do not put hybrid nodes back into any
# of these denominators without giving `rl` the same population.
# KNOWN: on the `$ng==0` arm (nodes carry a nodegroup label but `list-nodegroups` returned none -- a synthetic
# shape) the list shows those nodes as AWS-managed beneath a `none` verdict. The labels and the EKS API disagree
# there; picking a side would change what the panel claims.
# HYBRID NODES ARE NOT IN ope-15's POPULATION, neither `m3`'s nor `rl`'s. Counting them in `m3` alone gives a
# FALSE FAIL (hybridising the one self-managed node of a cluster whose other two EC2 nodes are in a node group
# turns `all~2/2` into `some~2/3`, a gap no remediation can close) and NO REPORT (`rl` names 2 of 2 against a
# detail leading 2/3, so render-report.py exits 1). `m3` follows `rl`'s population; `hyx()` discloses it.
# WINDOWS NODES ARE OUT OF BOTH POPULATIONS: `m3` and `rl` both count `islinux`; `rl` lists them as `context`
# after a "not assessed" line; a Windows-only cluster answers `winna` with a `context_only` list.
rl ope-15 nodegroups nodes cluster 'input as $n|input as $cl|((.nodegroups)//[]) as $ng|[$n.items[]?|select(islinux)] as $ec2|[$n.items[]?|select(iswin and isec2)] as $wn|("\($wn|length) Windows node(s) not assessed — this skill supports Linux nodes only") as $wl|($ec2|length) as $t|([$ec2[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"])//"")=="auto")]|length) as $auto|def how: ((.metadata.name)//"?") as $nn|((.metadata.labels)//{}) as $l|if (($l["eks.amazonaws.com/compute-type"])//"")=="auto" then $nn+" (EKS Auto Mode node)" else $nn+" (nodegroup="+(($l["eks.amazonaws.com/nodegroup"])//""|if .=="" then "none" else . end)+")" end; if ($t==0 and ($wn|length)>0) then {pass:[],fail:[],context:([$wl]+[$wn[]|((.metadata.name)//"?")]),context_only:true} elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then {pass:["computeConfig.enabled = true (EKS Auto Mode launches, patches, upgrades and replaces these nodes; a managed node group is not the mechanism)"],fail:[],context:([$n.items[]?|select((iswin and isec2)|not)|((.metadata.name)//"?")]+[$ng[]|"managed node group alongside Auto Mode: "+.]+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end)),kind:"field"} else ([$ec2[]|select(((((.metadata.labels)//{})["eks.amazonaws.com/nodegroup"])//"")!="" or ((((.metadata.labels)//{})["eks.amazonaws.com/compute-type"])//"")=="auto")] as $man|{pass:[$man[]|how],fail:[($ec2-$man)[]|how],context:($ng+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end))}) end'
m3 ope-15 nodegroups nodes cluster 'input as $n|input as $cl|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/nodegroup"]//"")!="")]|length) as $mng|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|([$ec2[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto") or ((.metadata.labels["eks.amazonaws.com/nodegroup"]//"")!=""))]|length) as $man|((.nodegroups//[])|length) as $ng| if ($t==0 and $w>0) then winna($w)+hyx($hy) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then "all~EKS Auto Mode manages the node lifecycle and every EC2 node is an Auto Mode node (eks.amazonaws.com/compute-type=auto): AWS launches, patches, upgrades and replaces them, so a managed node group is not the mechanism here (\($t) EC2 node(s), \($ng) managed node group(s) alongside Auto Mode)"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy>0) then "all~EKS Auto Mode manages all \($t) EC2 node(s) (eks.amazonaws.com/compute-type=auto) — AWS launches, patches, upgrades and replaces them, alongside \($ng) managed node group(s) — so every node this question judges has an AWS-managed lifecycle"+hyx($hy)+winx($w)+". A hybrid node cannot be placed in an EKS managed node group under any configuration, so its lifecycle stays with the operator whatever is done here and counting it as a failure would report a gap no remediation can close" elif ($t==0 and $hy>0) then hyna($hy;"a hybrid node joins the cluster through a HYBRID_LINUX access entry and nodeadm, on hardware the operator owns, and it cannot be placed in an EKS managed node group, so there is no node lifecycle here for AWS to take over") elif $t==0 then "na~no EC2 nodes" elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or $hy==0)) then ((if $hy==0 then b($man;$t)+"~Auto Mode is enabled on the cluster but not on every EC2 node: Auto Mode manages \($auto) of \($t), a managed node group manages \($mng) (\($ng) MNG), so \($man) of \($t) have an AWS-managed node lifecycle"+(if $man<$t then "; the other \($t-$man) carry neither the eks.amazonaws.com/nodegroup label nor eks.amazonaws.com/compute-type=auto and are what this question asks you to migrate" else "" end) else b($man;$t)+"~\($man)/\($t) node(s) have an AWS-managed node lifecycle: Auto Mode is enabled but manages only \($auto) of the \($t) EC2 node(s) and a managed node group manages \($mng) (\($ng) MNG)"+(if $man<$t then ", so \($t-$man) EC2 node(s) carry neither the eks.amazonaws.com/nodegroup label nor eks.amazonaws.com/compute-type=auto" else "" end)+"; the \($hy) EKS Hybrid Node(s) are excluded from that denominator rather than counted as failures, because they run on hardware the operator owns and cannot be placed in an EKS managed node group at all" end)+winx($w)) elif $ng==0 then "none~0 managed node groups returned by list-nodegroups (\($t) EC2 node(s))"+(if $hy>0 then ", and \($hy) EKS Hybrid Node(s), whose node lifecycle stays with the operator either way" else "" end)+winx($w) else (if $hy==0 then b($mng;$t)+"~\($mng)/\($t) EC2 nodes in a managed node group (\($ng) MNG)" else b($mng;$t)+"~\($mng)/\($t) EC2 nodes in a managed node group (\($ng) MNG); the \($hy) EKS Hybrid Node(s) are excluded from that denominator rather than counted as failures, because they cannot be placed in one at all" end)+winx($w) end'
# ope-16 ANSWERS `all` ON AUTO MODE, not `na`, by ope-15's argument: the OUTCOME (core add-ons EKS-managed) is met
# more strongly (docs.aws.amazon.com/eks/latest/userguide/auto-upgrade.html: "EKS Auto Mode replaces these
# components with service functionality"). The operator still owns add-ons they install themselves, so the
# standard-cluster arm is untouched.
# THE GATE IS EVERY EC2 NODE, NOT THE CLUSTER FLAG: the add-ons are replaced only on Auto Mode nodes,
# and docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html says they remain necessary on a mixed cluster. A
# flag-only gate would say "no add-on version left to manage" about a cluster whose coredns, kube-proxy and
# vpc-cni serve its node-group nodes. Sibling gate of the other 10 (see the census at ope-10); ope-16 and lens-3
# also require `$fg==0` in the all-Auto arm, because Fargate beside Auto Mode still needs the operator's
# CoreDNS. On a mixed-mode cluster it falls through to MEASURING the three add-ons.
# FARGATE-ONLY COMPUTE GETS ITS OWN ARM and it is NOT a blanket `na`: exactly ONE of the three applies.
#   kube-proxy -- docs.aws.amazon.com/eks/latest/userguide/managing-kube-proxy.html: "isn't deployed to Fargate
#   nodes". Nothing to manage.
#   vpc-cni -- docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html: deployed with each Fargate node,
#   "but you don't update it".
#   coredns -- STILL THE OPERATOR'S (docs.aws.amazon.com/eks/latest/userguide/fargate-getting-started.html:
#   CoreDNS runs on EC2 by default; on Fargate-only it needs a `coredns` Fargate profile plus a rollout restart,
#   or the managed add-on).
# So the Fargate denominator is 1 and the band comes from coredns alone. `na` here would be wrong (two thirds of
# the subject absent does not make the question inapplicable) and would spend band margin (reduce.sh withholds a
# pillar when applicable*2 < total).
# NO LEADING RATIO ON THE FARGATE OR ALL-AUTO-MODE ARMS. On the Fargate arm `rl` takes its `($any and $t==0)`
# branch and emits `kind:"existence"` with `coredns` as the single member (0/1 or 1/1). On the all-Auto-Mode arm
# `rl` short-circuits to a `kind:"field"` entry (1 pass, 0 fail) on that arm's own test (flag on, at least one
# EC2 node, all Auto Mode, no hybrid). An "N/3" on either would be reported as a DISAGREEMENT. The mixed-mode arm
# takes `rl`'s three-add-on path and leads with prose by choice. A change to the field branch's test has to be
# made on both lines.
# ope-16 has THREE list shapes, two of which are not counts:
#   AUTO MODE -- `kind:"field"`, the member IS the setting.
#   FARGATE-ONLY -- `kind:"existence"` (the verdict is the coredns membership test); with `kind` unset
#     the panel would label a yes/no answer "Counted as passing (1)".
#   OTHERWISE -- the three core add-ons, `pass`+`fail`==3, which the `N/3` cross-checks.
# A cluster with no Linux EC2, Fargate or hybrid node but with Windows nodes takes none of the three: its
# list is `context_only` beside the `winna` detail.
# THE THREE NAMES MUST BE WORKING ADD-ONS, not merely in `.addons` (a list of NAMES): otherwise
# `all~3/3 core addons` would publish on a cluster whose coredns is DEGRADED with
# InsufficientNumberOfReplicas. `$hz` is `.addons` intersected with `.addonDetails[]` entries that are
# ACTIVE with no `health.issues`. collect.sh's ADD-ON GAP CANARY refuses a collection whose `.addons` and
# `.addonDetails` lengths differ; on a hand-assembled work dir a name with no detail reads as
# not-credited and `_ast` says which.
# THE DETAIL WORDING NAMES BOTH CONDITIONS: "N/3 core addons" counts managed AND working; in `fail` a bare name is
# not a managed add-on, a decorated one is managed and broken.
# AUTO MODE PLUS FARGATE IS NOT THE ALL-AUTO ARM: the arm also requires `$fg==0` (eks-add-ons.html). Auto
# Mode covers its own nodes; on the Fargate nodes coredns is the only core add-on the operator manages,
# so that cluster takes the Fargate arm. That disjunct carries no `$hy==0`: the hybrid arm sits ahead of
# it and takes every all-Auto cluster with a hybrid node.
rl ope-16 addons nodes cluster 'def _ast($ad;$x): ($ad|map(select(.addonName==$x))|first) as $d|if $d==null then "its describe-addon detail was not collected" else "status "+(($d.status)//"unknown")+(if ([$d.health.issues[]?]|length)>0 then ", health issue(s): "+([$d.health.issues[]?|(.code//"unknown")]|join(", ")) else "" end) end;input as $n|input as $cl|((.addons)//[]) as $a|((.addonDetails)//[]) as $ad|[$ad[]|select(((.status//"")=="ACTIVE") and (([.health.issues[]?]|length)==0))|.addonName] as $hd|[$a[]|select(. as $x|$hd|any(.==$x))] as $hz|["vpc-cni","coredns","kube-proxy"] as $core|($hz|any(.=="coredns")) as $cdok|($a|any(.=="coredns")) as $cdmg|[$n.items[]?|select(islinux)] as $ec2|[$n.items[]?|select(iswin and isec2)] as $wn|("\($wn|length) Windows node(s) not assessed — this skill supports Linux nodes only") as $wl|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"])//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any|([$n.items[]?|select((isec2|not) and (ishy|not))]|length) as $fg| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0 and $fg==0) then {pass:["computeConfig.enabled = true (EKS Auto Mode runs the VPC CNI, CoreDNS and kube-proxy as service functionality, so there is no managed add-on to update)"],fail:[],context:($a+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end)),kind:"field"} elif ($hy>0 and ($t==0 or ($cl.cluster.computeConfig.enabled==true and $auto==$t))) then (["coredns","kube-proxy"] as $hcore|{pass:[$a[]|select(. as $x|($hcore|any(.==$x)) and ($hz|any(.==$x)))],fail:[$hcore[]|. as $x|select(($hz|any(.==$x))|not)|if ($a|any(.==$x)) then $x+" (an EKS managed add-on, but "+_ast($ad;$x)+")" else $x end],context:(["vpc-cni is out of scope on a hybrid node: AWS documents that the Amazon VPC CNI is not compatible with hybrid nodes and its aws-node DaemonSet carries anti-affinity for eks.amazonaws.com/compute-type=hybrid"]+[$a[]|select(. as $x|($hcore|any(.==$x))|not)]+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end)),kind:"existence"}) elif ($any and $t==0 and $fg==0 and ($wn|length)>0) then {pass:[],fail:[],context:([$wl]+[$wn[]|((.metadata.name)//"?")]),context_only:true} elif (($any and $t==0) or (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t)) then {pass:(if $cdok then ["coredns"] else [] end),fail:(if $cdok then [] elif $cdmg then ["coredns is an EKS managed add-on, but "+_ast($ad;"coredns")] elif $t>0 then ["coredns is not an EKS managed add-on"] else ["coredns is not an EKS managed add-on (it runs from the cluster CoreDNS Deployment, which on Fargate-only compute you also have to place on Fargate deliberately)"] end),context:([$a[]|select(.!="coredns")]+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end)),kind:"existence"} elif (($cl.cluster.computeConfig.enabled==true) and $t==0) then {pass:[],fail:[],context:(["no Linux EC2 node, Fargate node or hybrid node: there is nothing here for a core add-on to run on"]+$a),context_only:true} else {pass:[$a[]|select(. as $x|($core|any(.==$x)) and ($hz|any(.==$x)))],fail:[$core[]|. as $x|select(($hz|any(.==$x))|not)|if ($a|any(.==$x)) then $x+" (an EKS managed add-on, but "+_ast($ad;$x)+")" else $x end],context:[$a[]|select(. as $x|($core|any(.==$x))|not)]} end'
m3 ope-16 addons nodes cluster 'def _ast($ad;$x): ($ad|map(select(.addonName==$x))|first) as $d|if $d==null then "its describe-addon detail was not collected" else "status "+(($d.status)//"unknown")+(if ([$d.health.issues[]?]|length)>0 then ", health issue(s): "+([$d.health.issues[]?|(.code//"unknown")]|join(", ")) else "" end) end;input as $n|input as $cl|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any|([$n.items[]?|select((isec2|not) and (ishy|not))]|length) as $fg|((.addons//[]) as $a|((.addonDetails)//[]) as $ad|[$ad[]|select(((.status//"")=="ACTIVE") and (([.health.issues[]?]|length)==0))|.addonName] as $hd|[$a[]|select(. as $x|$hd|any(.==$x))] as $hz|(["vpc-cni","coredns","kube-proxy"]|map(select(. as $x|$hz|any(.==$x)))|length) as $ok|($hz|any(.=="coredns")) as $cdok|($a|any(.=="coredns")) as $cdmg| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0 and $fg==0) then "all~auto mode replaces the VPC CNI, CoreDNS and kube-proxy add-ons with service functionality that AWS updates, so these components are AWS-managed and there is no add-on version left for the operator to manage"+winx($w) elif ($hy>0 and ($t==0 or ($cl.cluster.computeConfig.enabled==true and $auto==$t))) then ((["coredns","kube-proxy"]|map(select(. as $x|$hz|any(.==$x)))|length) as $hok|b($hok;2)+"~\($hok)/2 core add-ons that apply to an EKS Hybrid Node are EKS managed add-ons that are ACTIVE with no reported health issues (coredns and kube-proxy). The third, vpc-cni, is not a gap you can close: AWS documents that the Amazon VPC CNI is not compatible with hybrid nodes and ships its aws-node DaemonSet with anti-affinity for eks.amazonaws.com/compute-type=hybrid, so pod networking here comes from Cilium or Calico, which is not an EKS managed add-on and whose version this review does not read"+winx($w)) elif ($any and $t==0 and $fg==0 and $w>0) then winna($w) elif (($any and $t==0) or (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t)) then (if $cdok then "all" else "none" end)+"~"+(if $t>0 then "Auto Mode covers all \($t) EC2 node(s), but this cluster also runs \($fg) Fargate node(s), and AWS documents that the core add-ons remain necessary when Auto Mode is combined with AWS Fargate. On the Fargate nodes " else "Fargate compute: " end)+"coredns is the only one of the three core add-ons that applies here, and it is \(if $cdok then "an EKS managed add-on that is ACTIVE with no reported health issues" elif $cdmg then "an EKS managed add-on, but not one this review credits as working: \(_ast($ad;"coredns"))" elif $t>0 then "not an EKS managed add-on" else "not an EKS managed add-on — it runs from the cluster CoreDNS Deployment, which on Fargate-only compute you also have to place on Fargate deliberately" end). The other two are not gaps you can close: kube-proxy is not deployed to Fargate nodes, and a version of the VPC CNI ships with each Fargate node on a schedule AWS owns"+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t==0) then "na~no EC2 nodes" elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or $hy==0)) then b($ok;3)+"~Auto Mode is enabled but only \($auto) of \($t) EC2 nodes are Auto Mode nodes, so vpc-cni, coredns and kube-proxy remain necessary for the rest: \($ok) of the 3 are EKS managed add-ons that are ACTIVE with no reported health issues"+winx($w) else b($ok;3)+"~\($ok)/3 core addons are EKS managed add-ons that are ACTIVE with no reported health issues"+winx($w) end)'
# ope-18 reads `concurrencyPolicy` alone. The API server stores `failedJobsHistoryLimit: 1` and
# `successfulJobsHistoryLimit: 3` on every CronJob that omits them (kubectl explain cronjob.spec), and
# collect.sh reads stored objects, so a test on either limit passes every CronJob. `concurrencyPolicy`
# defaults to `Allow`, which is the value that fails.
rl ope-18 cronjobs '[.items[]?] as $c|[$c[]|select((.spec.concurrencyPolicy//"Allow")!="Allow")] as $p|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");{pass:[$p[]|n],fail:[($c-$p)[]|n]}'
m ope-18 cronjobs '[.items[]?] as $c|($c|length) as $t|([$c[]|select((.spec.concurrencyPolicy//"Allow")!="Allow")]|length) as $ok| if $t==0 then "na~no CronJobs" else b($ok;$t)+"~\($ok)/\($t) CronJobs guarded (concurrencyPolicy is not Allow)" end'
rl ope-20 insights '[(.insights//[])[]|select(.category=="UPGRADE_READINESS")] as $u|{pass:[$u[]|select((.insightStatus.status//"")=="PASSING")|.name],fail:[$u[]|select((.insightStatus.status//"")!="PASSING")|(.name + " (" + ((.insightStatus.status)//"unknown") + ")")],context:[(.insights//[])[]|select(.category!="UPGRADE_READINESS")|(.name + " (" + ((.category)//"uncategorised") + ", not graded by this question)")]}'
m ope-20 insights '[(.insights//[])[]|select(.category=="UPGRADE_READINESS")] as $u|($u|length) as $t|([$u[]|select((.insightStatus.status//"")=="PASSING")]|length) as $ok| if $t==0 then "na~EKS reported no upgrade-readiness insights for this cluster" else b($ok;$t)+"~\($ok)/\($t) EKS upgrade-readiness insights passing" end'
# fargate-1 is MEASURED from describe-fargate-profile.
# THE TEST IS THE TITLE'S: a selector is broad when it has NO labels and its namespace pattern matches
# `default` or `kube-system`. Labels are optional per AWS (hp-nodes-fargate-pod-selection), so a
# namespace-only selector on an application namespace is the standard shape and passes; a labelled
# kube-system selector (`k8s-app=kube-dns`, CoreDNS on Fargate-only) passes too. Namespaces may carry
# the `*` and `?` wildcards; `_nsglob` turns one into an anchored regex (namespace names are [a-z0-9-],
# so nothing else needs escaping), so `*` or `kube-*` without labels counts as broad.
# EVERY SELECTOR OF A PROFILE IS TESTED: selectors are OR-ed, so one broad selector makes the profile
# broad. A profile with no selectors does not qualify.
m2 fargate-1 fargate fargateprofiles 'input as $fp|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$fp.profiles[]?] as $ps|($ps|length) as $t|def _nsglob: "^"+(gsub("\\?";".")|gsub("\\*";".*"))+"$";([$ps[]|select((((.selectors//[])|length)>0) and all((.selectors//[])[]; ((.namespace//"")!="") and ((((.labels//{})|length)>0) or (((.namespace//"")|_nsglob) as $re|(["default","kube-system"]|any(.[]; test($re)))|not))))]|length) as $ok| if $t==0 then "none~fargate profiles exist but none could be described" else b($ok;$t)+"~\($ok)/\($t) profiles have no selector that takes all of default or kube-system (every selector names another namespace or carries labels)" end) end'
# fargate-2 / fargate-4 -- pod selection resolves POD -> NODE, not a pod label. AWS documents
# `compute-type` on Fargate NODES; on a POD the only related label is `eks.amazonaws.com/fargate-profile`,
# which you ADD to disambiguate. A pod-label selector matches zero pods on a real Fargate cluster and
# silently no-ops to `na`. Joining on `.spec.nodeName` uses the documented node label.
m3 fargate-2 fargate pods nodes 'input as $p|input as $n|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")|.metadata.name]) as $fg|([$p.items[]?|select((.spec.nodeName//"") as $nn|$fg|index($nn))|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory)]|length) as $ok| if $t==0 then "na~no pods resolved to a Fargate node" else b($ok;$t)+"~\($ok)/\($t) fargate pod requests" end) end'
# fargate-4 -- the DOCUMENTED Fargate logging mechanism is the built-in log router: a ConfigMap `aws-logging` in
# namespace `aws-observability` (docs.aws.amazon.com/eks/latest/userguide/fargate-logging.html). A sidecar is
# accepted as an alternative path. It requires an [OUTPUT] section ("At least one supported Output plugin has to
# be provided"), not a non-empty ConfigMap: counting data keys would credit a ConfigMap holding only filters.conf
# or parsers.conf while Fargate ships no logs. THE `"i"` FLAG ON THE [OUTPUT] MATCH IS A DELIBERATE
# SUPERSET, NOT A DOCUMENTED EQUIVALENCE. Do not cite "The keys are case-insensitive" for it: that is
# about keys inside a section, not the header. AWS says nothing about header case. If Fargate rejects
# `[output]`, this could say `all` for a cluster with no logging; kept because a false `none` on a
# working cluster is the likelier error. If AWS documents header case-sensitivity, drop the flag.
# The [OUTPUT] header must open a line of the `output.conf` KEY: `# [OUTPUT]` is a Fluent Bit comment, and whether jq's `^` also matches after a newline differs between jq builds (jq 1.7.1: no), so `(^|\n)` is used, a line start on either; an [OUTPUT] under `filters.conf` is rejected by AWS.
# A ConfigMap Fargate REJECTS answers `some` first: a header other than [FILTER], [OUTPUT] or [PARSER] in any value, [SERVICE] and [INPUT] included (AWS: "If you provide any other sections, they will be rejected"; Fluent Bit compares section names case-insensitively, hence `"i"`), or values over 5,300 characters (AWS: "Can't exceed 5300 characters", not saying what is counted; the values alone are a floor under any count).
# It requires the NAMESPACE LABEL too ("the `aws-observability: enabled` label is required");
# `kubectl create namespace aws-observability` omits it, which answers `some` and the detail names the label.
# THE SIDECAR ARM COUNTS ONLY PODS ON FARGATE NODES, joined on `.spec.nodeName` as fargate-2 does: a
# fluent-bit DaemonSet pod on an EC2 node collects nothing from a Fargate pod ("Daemonsets aren't
# supported on Fargate"). Five inputs, hence `m5`: fargate, awslogging, pods, nodes, namespaces.
m5 fargate-4 fargate awslogging pods nodes namespaces 'input as $cm|input as $p|input as $n|input as $ns|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else (($cm.data//{}) as $d|(($d["output.conf"]//"")|test("(^|\n)[ \t]*\\[OUTPUT\\]";"i")) as $has_out|([$d[]|strings|select(test("(^|\n)[ \t]*\\[(?!(FILTER|OUTPUT|PARSER)\\])";"i"))]|length>0) as $bad_sec|([$d[]|strings|length]|add//0) as $chars|(($d|keys)|length) as $keys|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")|.metadata.name]) as $fg|([$p.items[]?|select((.spec.nodeName//"") as $nn|$fg|index($nn))|select([.spec.containers[]?.name]|any(test("fluent")))]|length) as $side|([$ns.items[]?|select((.metadata.name//"")=="aws-observability")|select(((.metadata.labels//{})["aws-observability"]//"")=="enabled")]|length>0) as $lab| if $bad_sec then "some~aws-logging carries a section other than [FILTER], [OUTPUT] or [PARSER] (such as [SERVICE] or [INPUT], which Fargate manages itself), so Fargate rejects it and ships no logs" elif $chars>5300 then "some~aws-logging data values total \($chars) characters, over the 5,300 a Fargate ConfigMap may hold, so Fargate rejects it and ships no logs" elif ($has_out and $lab) then "all~aws-observability/aws-logging log router with an [OUTPUT] destination, in a namespace labelled aws-observability: enabled" elif $has_out then "some~aws-logging declares an [OUTPUT] under output.conf, but namespace aws-observability does not carry the label aws-observability: enabled, which AWS requires, so the log router is not enabled" elif $keys>0 then "some~aws-logging ConfigMap exists but declares no [OUTPUT] under output.conf, so Fargate ships no logs" elif $side>0 then "most~\($side) pod(s) on Fargate nodes run a fluent sidecar; Fargate has a built-in log router and the documented path is the aws-logging ConfigMap" else "none~no aws-logging ConfigMap in aws-observability and no fluent sidecar" end) end'
# lens-1 asks whether node problems are DETECTED. On an Auto Mode cluster AWS does it, so this answers `all` for
# ope-15's reason. docs.aws.amazon.com/eks/latest/userguide/node-health.html: "EKS Auto Mode compute includes the
# node monitoring agent." Requiring a node-problem-detector DaemonSet there would ask the cluster to duplicate
# what it runs below the pod layer.
# THE GATE IS EVERY EC2 NODE, NOT THE CLUSTER FLAG: the agent is in the Auto Mode node's AMI, so a flag would hand
# a mixed-mode cluster's node-group nodes a mechanism they do not have. Sibling gate of the other 10. On a
# mixed-mode cluster the question falls through to the add-on and DaemonSet paths, both ordered ahead of the
# mixed-mode arm, so a cluster with either still scores `all`.
# THREE PATHS, NOT ONE. A DaemonSet-only test would score `none` on a STANDARD cluster that enabled node
# monitoring the documented way, as an EKS managed add-on, and tell it to install what it already runs.
#   node-health.html: the agent is enabled with Auto Mode and usable "with any EKS compute types except
#   for AWS Fargate", as an add-on or via Helm/Kubernetes tooling.
#   docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html: the add-on name is
#   `eks-node-monitoring-agent`, matched with `==` because an add-on name is an exact API value; no install needed
#   on Auto Mode.
#   docs.aws.amazon.com/eks/latest/userguide/node-health-nma.html: the agent is deployed as a DaemonSet, so the
#   add-on and the hand-managed DaemonSet are the same component by two routes, and both score `all`.
# ON A MIXED-MODE CLUSTER THE ADD-ON IS THE ARM THAT MATTERS: it covers the non-Auto-Mode nodes the node
# gate does not credit from the AMI.
# NEEDS THE ADD-ON LIST, hence m4: `daemonsets nodes addons cluster`; `.` is f1 and each `input` yields f2, f3, f4.
# Re-derive `m4` callers with `grep -rnE "^m4 [a-z]+-[0-9]+ " references/*.md references/*/*.md`.
# WINDOWS NODES ARE NOT ASSESSED (Linux nodes only): `$t` counts `islinux` nodes, hybrid stays judged,
# a Windows-only cluster answers `winna` ahead of the Fargate arm, and every other arm carries
# `winx($w)`. The NPD arm applies ope-7's `_lxds`, so a Windows-only node-problem-detector credits
# nothing.
# THE ADD-ON ARM READS THE ADD-ON STATUS IT CLAIMS: it requires the `.addonDetails[]` entry ACTIVE with no
# `health.issues` (ope-16's predicate), or it would assert the agent is enabled while the add-on sits in
# CREATE_FAILED. A broken add-on FALLS THROUGH, so a working node-problem-detector still wins and only a
# cluster with neither reaches `none~none`.
# THE ADD-ON ARM ALSO REQUIRES A NODE TO RUN ON (at least one Linux EC2 or hybrid node): with no nodes
# the add-on still reports ACTIVE while its DaemonSet sits at desired 0. That shape is answered by the
# no-node arm above (`na~no EC2 nodes`) when Auto Mode is enabled, and falls through to `none~none`
# otherwise.
# THE DAEMONSET ARM IS THE THIRD ROUTE AND CREDITS THE AGENT AS WELL AS NPD: a Helm install
# (github.com/aws/eks-node-monitoring-agent) creates the DaemonSet `eks-node-monitoring-agent` and no EKS
# add-on. When the add-on is listed, its DaemonSet is the add-on's and the add-on arm has already judged
# it. This arm REQUIRES A READY POD, as ope-5's does: a DaemonSet scaled to zero detects nothing.
m4 lens-1 daemonsets nodes addons cluster 'def _lxds: (.spec.template.spec//{})|iswinspec|not;input as $n|input as $a|input as $cl|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then "all~auto mode bakes the EKS node monitoring agent into the node AMI of every \(if $w>0 then "Linux " else "" end)EC2 node (eks.amazonaws.com/compute-type=auto) and enables automatic node repair by default, so node problem detection and node replacement are AWS-managed"+winx($w) elif ($t==0 and $hy==0 and ($any or ($cl.cluster.computeConfig.enabled==true))) then (if $w>0 then winna($w) elif $any then "na~no DaemonSets possible on Fargate compute" else "na~no EC2 nodes" end) elif ((($t+$hy)>0) and ((($a.addons)//[])|any(.=="eks-node-monitoring-agent")) and ((($a.addonDetails)//[])|any((.addonName=="eks-node-monitoring-agent") and ((.status//"")=="ACTIVE") and (([.health.issues[]?]|length)==0)))) then "all~the EKS node monitoring agent is enabled as the eks-node-monitoring-agent EKS managed add-on, which AWS deploys as a DaemonSet"+(if ($cl.cluster.computeConfig.enabled==true) then " across the \($t - $auto) EC2 node(s) that are not Auto Mode nodes"+(if $auto>0 then ", while the remaining \($auto) node(s) carry the agent in the node AMI" else "" end) else " on the Linux nodes in this cluster" end)+winx($w) elif ([.items[]|select(.metadata.name|test("node-problem-detector|npd|eks-node-monitoring-agent"))|select(((.metadata.name|test("eks-node-monitoring-agent")) and ((($a.addons)//[])|any(.=="eks-node-monitoring-agent")))|not)|select(_lxds)|select((.status.numberReady|numbers)>0)]|length)>0 then "all~"+([.items[]|select(.metadata.name|test("node-problem-detector|npd|eks-node-monitoring-agent"))|select(((.metadata.name|test("eks-node-monitoring-agent")) and ((($a.addons)//[])|any(.=="eks-node-monitoring-agent")))|not)|select(_lxds)|select((.status.numberReady|numbers)>0)|if (.metadata.name|test("eks-node-monitoring-agent")) then "a ready eks-node-monitoring-agent DaemonSet" else "NPD" end]|unique|join(", "))+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy>0) then "none~Auto Mode covers all \($t) \(if $w>0 then "Linux " else "" end)EC2 node(s) — the node monitoring agent is in their AMI and node auto repair is on by default — but Auto Mode does not reach infrastructure outside AWS, so the \($hy) EKS Hybrid Node(s) have no node-problem detection and no automatic node repair, and neither the eks-node-monitoring-agent add-on nor a node-problem-detector DaemonSet covers them"+winx($w) elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or $hy==0)) then "none~Auto Mode compute is enabled but only \($auto) of \($t) EC2 nodes carry the node monitoring agent in their AMI; the rest have no node-problem detection and no automatic node repair, and neither the eks-node-monitoring-agent add-on nor a node-problem-detector DaemonSet covers them"+winx($w) else "none~none"+winx($w) end'
g ope-19
# lens-7 ANSWERS `all` ON AUTO MODE, not `na`, on the same gate and for the same reason as ope-16. Both
# halves are AWS-managed: CURRENT (docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html: a new
# AMI weekly, "AWS determines" the image; the pod networking capability ships in it,
# docs.aws.amazon.com/eks/latest/userguide/auto-upgrade.html) and HEALTHY
# (docs.aws.amazon.com/eks/latest/userguide/node-health.html: `NetworkingReady` is set by the node monitoring
# agent, enabled with Auto Mode compute). Prose detail with no ratio, as ope-16: lens-7's extractor looks for
# `vpc-cni` in the add-on list and finds nothing on Auto Mode.
# THE GATE IS EVERY EC2 NODE, NOT THE CLUSTER FLAG: both credits are node-scoped (the AMI and the monitoring
# agent belong to Auto Mode compute); on a mixed cluster the `vpc-cni` add-on remains the mechanism for the other
# nodes (docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html), so it falls through to the `vpc-cni` add-on
# test. Sibling gate of the other 10.
# FARGATE-ONLY COMPUTE ANSWERS `all` TOO (docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html: a
# version is deployed with each Fargate node "but you don't update it"). `describe-addon` returning nothing is the
# expected shape; without this arm the cluster would read `none~not managed` and be told to update an add-on it is
# documented as not updating. `all` rather than `na` for ope-15's reason.
# THE HEALTH HALF IS DELIBERATELY NOT CLAIMED FROM `NetworkingReady` ON FARGATE: node-health.html scopes
# the agent to "any EKS compute types except for AWS Fargate". That arm rests on who owns the component,
# and its detail says so.
# Neither Auto-Mode-reachable arm carries a ratio and `rl` short-circuits on the same node gate, so
# resource_agreement() has nothing to compare. The Fargate arm COUNTS NOTHING: its single pass is a NODE FACT
# with an empty `fail` and no `kind`; on a mixed-mode cluster `rl` branches on the node population and does not
# print the Auto-Mode-only claim.
# lens-7 reads a different thing on each arm: Auto Mode a CLUSTER FIELD (`kind:"field"`), Fargate NODE LABELS
# (no `kind`: the node population itself is the verdict), the rest the add-on list.
# `\u0027` is jq's escape for an apostrophe inside the shell single quotes that wrap the jq program.
rl lens-7 addons nodes cluster 'input as $n|input as $cl|((.addons)//[]) as $a|[$n.items[]?|select(islinux)] as $ec2|[$n.items[]?|select(iswin and isec2)] as $wn|("\($wn|length) Windows node(s) not assessed — this skill supports Linux nodes only") as $wl|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"])//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any|([$n.items[]?|select((isec2|not) and (ishy|not))]|length) as $fg| if ($t==0 and $fg==0 and ($wn|length)>0) then {pass:[],fail:[],context:([$wl]+[$wn[]|((.metadata.name)//"?")]),context_only:true} elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then {pass:["computeConfig.enabled = true (AWS owns the VPC CNI\u0027s version and health; a new node AMI ships roughly weekly)"],fail:[],kind:"field"}+(if ($wn|length)>0 then {context:([$wl]+[$wn[]|((.metadata.name)//"?")])} else {} end) elif ($any and $hy>0 and ($t==0 or ($cl.cluster.computeConfig.enabled==true and $auto==$t))) then {pass:[],fail:[],context:([(if $t==0 then "\($hy) EKS Hybrid Node(s) and no EC2 node: the Amazon VPC CNI is not compatible with a hybrid node, so there is no vpc-cni add-on version to name here and the CNI actually in use (Cilium or Calico) is not collected" else "\($t) Auto Mode EC2 node(s) and \($hy) EKS Hybrid Node(s): the Auto Mode nodes take pod networking from their AMI and the Amazon VPC CNI is not compatible with a hybrid node, so no node here takes its pod networking from the vpc-cni add-on and the CNI actually in use on the hybrid nodes (Cilium or Calico) is not collected" end)]+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end)),context_only:true} elif ($any and $t==0) then {pass:[(if ($wn|length)>0 then "every node other than the Windows nodes" else "every node" end)+" carries eks.amazonaws.com/compute-type=fargate (AWS deploys a version of the VPC CNI with each Fargate node and you do not update it there, so there is no add-on version to read)"],fail:[],context:($a+(if ($wn|length)>0 then [$wl]+[$wn[]|((.metadata.name)//"?")] else [] end))} elif (($cl.cluster.computeConfig.enabled==true) and $t==0 and (($a|any(.=="vpc-cni"))|not)) then {pass:[],fail:[],context:(["no Linux EC2 node, Fargate node or hybrid node, and vpc-cni is not an EKS managed add-on here, so there is no add-on version, status or health to read"]+$a),context_only:true} else (((.addonDetails//[])|map(select(.addonName=="vpc-cni"))|first) as $d|((.addonTargets//[])|map(select(.addonName=="vpc-cni"))|first) as $tg|{pass:(if ($a|any(.=="vpc-cni")) then ["vpc-cni " + (($d.addonVersion)//"version not collected") + " (status " + (($d.status)//"unknown") + ", EKS default " + (($tg.defaultVersion)//"not collected") + ")"] else [] end),fail:(if ($a|any(.=="vpc-cni")) then [(($d.health.issues)//[])[]|(.code//"unknown") + ": " + ((.message)//"")] else ["vpc-cni not a managed add-on"] end),context:$a}) end'
m3 lens-7 addons nodes cluster 'def _vt: (capture("^v?(?<a>[0-9]+)\\.(?<b>[0-9]+)\\.(?<c>[0-9]+)(?:-eksbuild\\.(?<d>[0-9]+))?")|[(.a|tonumber),(.b|tonumber),(.c|tonumber),((.d//"0")|tonumber)])? // null;input as $n|input as $cl|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any|([$n.items[]?|select((isec2|not) and (ishy|not))]|length) as $fg| if ($t==0 and $fg==0 and $w>0) then winna($w)+hyx($hy) elif (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then "all~auto mode delivers pod networking as service functionality on every EC2 node\(if $w>0 then " that runs Linux" else "" end) (eks.amazonaws.com/compute-type=auto), on an AWS-managed AMI that EKS refreshes weekly with CVE and security fixes, and reports the node networking stack health as the NetworkingReady node condition"+winx($w) elif ($hy>0 and ($t==0 or ($cl.cluster.computeConfig.enabled==true and $auto==$t))) then ((if $t==0 then hyna($hy;"AWS documents that the Amazon VPC CNI is not compatible with hybrid nodes and ships its aws-node DaemonSet with anti-affinity for the eks.amazonaws.com/compute-type=hybrid label, so there is no VPC CNI add-on version, status or health to read here — pod networking comes from a Cilium or Calico installation this review does not collect") else "na~no node on this cluster takes its pod networking from the vpc-cni EKS managed add-on, so there is no add-on version, status or health to read: all \($t) \(if $w>0 then "Linux " else "" end)EC2 node(s) carry eks.amazonaws.com/compute-type=auto and get pod networking as Auto Mode service functionality from an AWS-managed AMI rather than from a versioned add-on, and AWS documents that the Amazon VPC CNI is not compatible with the \($hy) EKS Hybrid Node(s) and ships its aws-node DaemonSet with anti-affinity for the eks.amazonaws.com/compute-type=hybrid label, so pod networking there comes from a Cilium or Calico installation this review does not collect" end)+winx($w)) elif ($any and $t==0) then "all~Fargate compute: AWS deploys a version of the VPC CNI with each Fargate node and the operator does not update it on Fargate nodes, so there is no add-on version to read or raise here and an empty add-on list is the expected shape. Pod network health on Fargate is AWS-managed too — each Fargate pod gets its own network interface — and this skill does not read a node condition for it, because the EKS node monitoring agent that publishes one is documented for every compute type except Fargate"+winx($w) elif ((.addons//[])|any(.=="vpc-cni")) then (((.addonDetails//[])|map(select(.addonName=="vpc-cni"))|first) as $d|((.addonTargets//[])|map(select(.addonName=="vpc-cni"))|first) as $tg|(($tg.versions)//[]) as $vs|($d.addonVersion|_vt) as $bv|($tg.defaultVersion|_vt) as $dv|([$vs[]|_vt|select(.!=null)]) as $pv| if $d == null then "most~vpc-cni is a managed add-on, but its detail was not collected, so version, status and health were not read" elif (($d.status//"") != "ACTIVE") then "none~vpc-cni \($d.addonVersion//"version not reported") is a managed add-on but its status is \($d.status//"unknown"), not ACTIVE" elif ((($d.health.issues)//[])|length) > 0 then "some~vpc-cni \($d.addonVersion//"version not reported") is ACTIVE with \((($d.health.issues)//[])|length) health issue(s): \((($d.health.issues)//[])|map(.code//"unknown")|join(", "))" elif (($vs|length) == 0) then "most~vpc-cni \($d.addonVersion//"version not reported") is managed, ACTIVE and free of reported health issues, but the versions EKS offers for Kubernetes \($cl.cluster.version//"unknown") were not collected, so its currency was not assessed" elif ($bv == null or $dv == null) then "most~vpc-cni \($d.addonVersion//"version not reported") is managed, ACTIVE and free of reported health issues, but \(if $bv == null then "its own version string" else "the EKS default \($tg.defaultVersion)" end) does not parse as vMAJOR.MINOR.PATCH[-eksbuild.N], so its currency was not assessed" elif ($bv >= $dv) then "all~vpc-cni \($d.addonVersion) managed, ACTIVE, no health issues, and at or newer than the EKS default \($tg.defaultVersion)" elif (($vs|index($d.addonVersion)) == null) then "some~vpc-cni \($d.addonVersion) is managed, ACTIVE and healthy, but it is older than the EKS default \($tg.defaultVersion) and is not among the \($vs|length) versions EKS offers for Kubernetes \($cl.cluster.version//"unknown"), so it cannot be updated in place from where it is" else (([$pv[]|.[0:2]]|unique) as $minors|([$minors[]|select(. > ($bv[0:2]) and . <= ($dv[0:2]))]|length) as $mb|([$pv[]|select(. > $bv)]|length) as $nb|"most~vpc-cni \($d.addonVersion) is managed, ACTIVE and healthy, but behind the EKS default \($tg.defaultVersion) by \($mb) minor version(s) (\($bv[0:2]|map(tostring)|join(".")) to \($dv[0:2]|map(tostring)|join("."))); \($nb) of the \($vs|length) versions EKS offers for Kubernetes \($cl.cluster.version//"unknown") are newer than the installed one") end)+winx($w) elif (($cl.cluster.computeConfig.enabled==true) and $t==0) then "na~no EC2 nodes" elif ($cl.cluster.computeConfig.enabled==true and (($auto==$t and $t>0)|not) and ($t>0 or $hy==0)) then "none~Auto Mode compute is enabled but only \($auto) of \($t) EC2 nodes get pod networking from the Auto Mode AMI; the rest need the vpc-cni add-on, which is not installed as an EKS managed add-on"+winx($w) else "none~not managed"+winx($w) end'
```

**Governance (not assessed):** ope-1 (IaC), ope-4 (templating), ope-9 (auth-failure
alarms), ope-13 (upgrade plan), ope-14 (non-prod test env), ope-19 (capacity planning).

---

## Infrastructure as Code

### ope-1: Do you provision your EKS cluster and worker nodes using Infrastructure as Code (IaC) tools such as Terraform, CloudFormation, or AWS CDK?

**Detection:** ✋ ASK USER

> IaC ensures reproducible, version-controlled infrastructure.

**Remediation:** Adopt Terraform, CDK, or CloudFormation for cluster provisioning. Store all K8s manifests in Git and deploy via CI/CD pipelines.

---

### ope-2: Are AWS integrations (Load Balancer Controller, External DNS, EBS CSI Driver) deployed as EKS add-ons or controllers?

**Detection:** 🔬 AUTO-DETECTABLE

> AWS integrations enable Kubernetes-native management of AWS resources.
> **On EKS Auto Mode, two of these three are cluster capabilities rather than workloads**, and each is
> credited on its own flag — not as one blanket pass. Load balancing counts when
> `kubernetesNetworkConfig.elasticLoadBalancing.enabled` is true, because AWS: "EKS Auto Mode handles
> Network Load Balancer provisioning by default for all services of type LoadBalancer - no additional
> controller installation or configuration is required." Block storage counts when
> `storageConfig.blockStorage.enabled` is true **and** a `StorageClass` references
> `ebs.csi.eks.amazonaws.com`, because AWS: "EKS Auto Mode does not create a `StorageClass` for you" —
> the capability is on but provisions nothing without one. `external-dns` is not an Auto Mode
> capability, so it stays measured and its absence is a real gap on any cluster.
> **On a Fargate-only cluster the denominator is 2, not 3.** AWS: "You can't mount Amazon EBS volumes to
> Fargate Pods", and the EBS CSI node component "can only run on Amazon EC2 instances" — so on a cluster
> with no EC2 node the block storage slot cannot be satisfied by anything, and it is **dropped from the
> denominator** rather than counted as a gap. The other two slots stay: load balancers work with Fargate
> ("Network Load Balancers and Application Load Balancers (ALBs) can be used with Fargate with IP targets
> only") and `external-dns` is an ordinary Deployment with no node dependency. Note that this means a
> deployed EBS CSI controller earns no credit on such a cluster — there is nothing for it to serve.
> **EKS Hybrid Nodes:** An EKS Hybrid Node drops block storage from the denominator: AWS documents that Amazon EBS volumes and the EBS CSI driver are not compatible with hybrid nodes, so an EBS CSI driver would have nothing to serve them. The load balancer and DNS integrations are still judged.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for: aws-load-balancer-controller, external-dns, ebs-csi
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# The two Auto Mode capabilities, each its own field — a cluster can have either, both or neither:
aws eks describe-cluster --name <CLUSTER> --region <REGION> \
  --query 'cluster.{lb:kubernetesNetworkConfig.elasticLoadBalancing.enabled,storage:storageConfig.blockStorage.enabled}'
kubectl get storageclass -o json    # the storage slot also needs a class on ebs.csi.eks.amazonaws.com
kubectl get nodes -L eks.amazonaws.com/compute-type
# every node "fargate" (no EC2 node at all) -> the block storage slot is not assessable, denominator 2
```

**Analysis:** One point per slot, denominator 3 — or 2 on Fargate-only compute:
- load balancing: an `aws-load-balancer-controller` Deployment with a ready replica, **or** Auto Mode load balancing enabled (AWS publishes no EKS add-on for the controller)
- block storage: an `ebs-csi` controller Deployment with a ready replica, or an EBS CSI EKS add-on that is `ACTIVE` with no health issues, **or** Auto Mode block storage enabled **with** a `StorageClass` on `ebs.csi.eks.amazonaws.com`
- `external-dns`: a Deployment with a ready replica, or the EKS add-on `ACTIVE` with no health issues — no capability substitutes for it
- 3/3 → `all`, 2/3 → `some`, 1/3 → `some`, 0/3 → `none` (the `b()` bands: ≥90% `all`, ≥70% `most`, >0% `some`)
- Fargate-only (nodes exist and none is an EC2 node): block storage leaves the denominator, so 2/2 → `all`, 1/2 → `some`, 0/2 → `none`

**Remediation:** On a standard cluster, deploy the missing pieces as Helm charts or EKS add-ons —
`aws eks create-addon --cluster-name <CLUSTER> --region <REGION> --addon-name aws-ebs-csi-driver
--service-account-role-arn <EBS_CSI_ROLE_ARN>` for block storage, and the AWS Load Balancer Controller
chart for ingress/NLB provisioning. The EBS CSI add-on needs that IAM role, carrying an AWS managed EBS
CSI policy such as `AmazonEBSCSIDriverPolicyV2`, before it can create a volume: without one it falls back
to the node IAM role and can go `ACTIVE` while every claim fails with `could not create volume in EC2:
UnauthorizedOperation`. Create the role first, as AWS documents in "Step 1: Create an IAM role"
(https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html). Where the finding
says an add-on is installed but not working, repair that add-on rather than creating it again: `aws eks
describe-addon --cluster-name <CLUSTER> --region <REGION> --addon-name <ADDON> --query 'addon.[status,health]'`
shows the status and health issues it reported.

**On an Auto Mode cluster, do not install what AWS already runs** — the load balancer controller and the
EBS CSI controller are service functionality there, and adding your own is a migration problem, not a
fix. Two things are still yours:

```bash
# 1. If storageConfig.blockStorage.enabled is true but no StorageClass names the Auto Mode provisioner,
#    the capability provisions nothing. Create one (see also sec-25 for the encryption parameter):
kubectl apply -f - <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: auto-ebs-sc
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"   # drop this line if `kubectl get storageclass` already shows a (default)
provisioner: ebs.csi.eks.amazonaws.com
volumeBindingMode: WaitForFirstConsumer
parameters:
  type: gp3
  encrypted: "true"
EOF

# 2. external-dns is the one slot with no Auto Mode equivalent. Install it and give it a Route 53 role
#    (Pod Identity — see sec-6), or accept that DNS records are managed outside the cluster.
```

**On a Fargate-only cluster, ignore the `aws-ebs-csi-driver` half of the command above** — EBS volumes
cannot be mounted to Fargate pods, so installing the driver buys nothing and this question does not count
it. What remains worth doing is the AWS Load Balancer Controller (Fargate services need it, on IP targets)
and `external-dns`. If persistent storage is what you were after, the Fargate path is Amazon EFS, which is
a different question from this one.

---

### ope-3: Do you use GitOps workflows (ArgoCD, Flux) to minimize direct kubectl access?

**Detection:** 🔬 AUTO-DETECTABLE

> GitOps reduces human error and provides audit trails for all changes.

**Remediation:** Implement GitOps workflows (ArgoCD, Flux) to eliminate direct kubectl access. Restrict kubectl to break-glass scenarios only.

---

### ope-4: Are you using Helm charts or Kustomize for Kubernetes manifest templating?

**Detection:** ✋ ASK USER

> Templating enables consistent configuration across environments.

**Remediation:** Adopt Helm for application packaging: `helm create <chart>`. Use values files per environment and store charts in a Helm repository.

---

## Centralized monitoring and logging

### ope-5: Are control plane metrics monitored using CloudWatch Container Insights or Prometheus?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and
     the Remediation block so the renderer does not extract it. The remediation gives the
     full create-addon command with --cluster-name/--region (a bare `create-addon
     --addon-name amazon-cloudwatch-observability` fails if pasted as given), states that
     the add-on's pods need an IAM role before they can publish anything, and ends with a
     verification step: on a High-severity question a bare instruction with no working
     command, no prerequisite and no verification is not a fix. Verified 2026-09-11 against
     docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html
     (required IAM permissions). Cite no repost.aws knowledge-center article here: this
     skill's source hierarchy admits the service documentation, and repost articles -- like
     blog posts -- are neither versioned with the service nor authoritative for a default.
     -->

> Control plane monitoring enables early detection of API server and etcd issues.

**Remediation:** The addon's agent pods need permission to publish before they can do anything — AWS:
"The permissions in the AWSXrayWriteOnlyAccess and CloudWatchAgentServerPolicy AWS managed policies are
required." Without that role, the addon installs and its pods run, but they cannot write metrics or
logs, which fails silently rather than blocking the install. Grant it with Pod Identity (see sec-6)
before creating the addon:

```bash
aws eks create-addon --cluster-name <CLUSTER> --region <REGION> --addon-name eks-pod-identity-agent
aws iam create-role --role-name AmazonEKSObservabilityRole --assume-role-policy-document \
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"pods.eks.amazonaws.com"},"Action":["sts:AssumeRole","sts:TagSession"]}]}'
aws iam attach-role-policy --role-name AmazonEKSObservabilityRole --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
aws iam attach-role-policy --role-name AmazonEKSObservabilityRole --policy-arn arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess
aws eks create-pod-identity-association --cluster-name <CLUSTER> --region <REGION> \
  --namespace amazon-cloudwatch --service-account cloudwatch-agent --role-arn <ROLE_ARN>
aws eks create-addon --cluster-name <CLUSTER> --region <REGION> --addon-name amazon-cloudwatch-observability
```

Container Insights bills as ordinary CloudWatch usage — custom metrics plus log ingestion and
storage — on top of anything ope-6's control plane logs already cost, so it is not a free flip of a
switch either. Verify the addon is actually active and its pods are actually running before reporting
this fixed, since a permissions gap here fails quietly:

```bash
aws eks describe-addon --cluster-name <CLUSTER> --region <REGION> --addon-name amazon-cloudwatch-observability --query 'addon.status'
kubectl get pods -n amazon-cloudwatch
```

Alternatively, deploy Prometheus + Grafana instead of the AWS-managed path if that already fits your
stack; it carries the same practical requirement — the collector needs a place to write to and someone
watching the dashboards — without the CloudWatch billing model.

---

### ope-6: Are EKS control plane logs (API server, audit, authenticator, controller manager, scheduler) enabled?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote
     and the Remediation block so the renderer does not extract it. The remediation
     gives the exact update-cluster-config command, the describe-update poll because the
     update is asynchronous (same pattern sec-38 documents for its own async cluster
     update, in data-protection.md, so the skill teaches one pattern rather than two),
     and a put-retention-policy command so enabling `audit`/`api` on a busy control
     plane doesn't create open-ended CloudWatch Logs ingestion and storage cost.
     Verified 2026-09-11 against
     docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html (exact command and
     log group name `/aws/eks/<cluster-name>/cluster`) and the CLI reference for `logs
     put-retention-policy`. SOURCE NOTE: do not present "This log type usually has the
     highest volume of log events" to the reader as an AWS quote. That sentence is NOT
     on control-plane-logs.html or on any other page of the service documentation; it
     appears in the Containers blog post "Understanding and Cost Optimizing Amazon EKS
     Control Plane Logs", and blog posts sit at the bottom of this skill's source
     hierarchy — ope-5's note above rejects repost.aws articles for the same reason. The
     claim itself is sound, so it is made in our own words with no attribution, and the
     quoted sentence is the charging one, which IS verbatim on the cited page. Do not
     re-attribute it. -->

> Control plane logs are essential for troubleshooting and security auditing.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.logging.clusterLogging"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Turning these on has a running cost — AWS: "You are charged the standard CloudWatch Logs
data ingestion and storage costs for any logs sent to CloudWatch Logs from your clusters"
(docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html) — and there is no cap unless you set
one. Expect `audit` and `api` to dominate that bill: the audit log records every API request the cluster
serves, so its volume scales with cluster activity rather than with cluster size. Set retention as part of
turning logging on, not as a follow-up:

```bash
aws eks update-cluster-config --region <REGION> --name <CLUSTER> \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'
```

This is **asynchronous** — the call returns an update id immediately, and the change is not live until
you poll it to `Successful`:

```bash
aws eks describe-update --region <REGION> --name <CLUSTER> --update-id <UPDATE_ID>
```

EKS creates the log group automatically as `/aws/eks/<CLUSTER>/cluster`. Cap its retention so the two
highest-volume types don't accumulate indefinitely:

```bash
aws logs put-retention-policy --log-group-name /aws/eks/<CLUSTER>/cluster --retention-in-days 90
```

---

### ope-7: Are worker node metrics (CPU, memory, disk) monitored using Node Exporter or CloudWatch?

**Detection:** 🔬 AUTO-DETECTABLE

> Node monitoring enables capacity planning and early detection of resource exhaustion.
> **EKS Hybrid Nodes:** EKS Hybrid Nodes are judged here. A DaemonSet does schedule onto a hybrid node — the collected `node-exporter` DaemonSet excludes only `compute-type=fargate` — so this question is graded normally and the evidence list labels each hybrid node as such.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.
> **What is credited:** a Linux-schedulable DaemonSet whose name contains `node-exporter` or `cloudwatch-agent`, with at least one ready pod. The `cloudwatch-agent` DaemonSet is what the Amazon CloudWatch Observability add-on runs for Container Insights, which publishes node CPU, memory and filesystem utilization.

**Remediation:** Deploy Prometheus Node Exporter as a DaemonSet: `helm install node-exporter oci://ghcr.io/prometheus-community/charts/prometheus-node-exporter`. Create Grafana dashboards for CPU, memory, disk. Or enable Container Insights with the `amazon-cloudwatch-observability` EKS add-on (the ope-5 remediation), which runs the `cloudwatch-agent` DaemonSet.

---

### ope-8: Are application logs forwarded to a centralized system (Fluent Bit, Fluentd, CloudWatch)?

**Detection:** 🔬 AUTO-DETECTABLE

> Centralized logging enables cross-service troubleshooting and audit trails.
> **EKS Hybrid Nodes:** EKS Hybrid Nodes are judged here: a log-forwarding DaemonSet schedules onto a hybrid node like any other, so this question is graded normally.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Remediation:** Deploy Fluent Bit as a DaemonSet that sends container logs to CloudWatch Logs. The
`amazon-cloudwatch-observability` addon from ope-5 already does this by default: it runs a `fluent-bit`
DaemonSet in `amazon-cloudwatch` under the same `cloudwatch-agent` service account, so the IAM role granted
there covers it. To run your own Fluent Bit instead, follow AWS's "Set up Fluent Bit as a DaemonSet to send
logs to CloudWatch Logs" (docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-setup-logs-FluentBit.html),
including the node-role IAM permissions it requires. A forwarder whose output is not configured
still passes this question, so confirm log streams arrive in the destination before reporting this fixed.

---

### ope-9: Have you created CloudWatch alarms or alerts for API server 403/401 responses?

**Detection:** ✋ ASK USER

> Monitoring auth failures detects unauthorized access attempts.

**Remediation:** Create CloudWatch metric filters on EKS audit logs for 403/401 responses. Set alarms with SNS notifications for threshold breaches.

---

### ope-10: Is the CNI metrics helper deployed to monitor VPC CNI IP address allocation and ENI usage?

**Detection:** 🔬 AUTO-DETECTABLE

> CNI metrics prevent IP exhaustion which can cause pod scheduling failures.
> **On an all-Auto-Mode cluster this scores `na`, and that is not a pass.** There is no VPC CNI DaemonSet
> to instrument — AWS: "With Amazon EKS Auto Mode, you don't need to install or upgrade networking
> add-ons" — so the helper cannot be deployed. But the visibility it provides is not delivered either:
> AWS lists "Pod networking - VPC CNI IP Address Management" among its managed component log sources
> and then says "EKS Auto managed component logs (such as Compute, Block storage, Load balancing, and
> IPAM) require separate configuration through log delivery". **The operator loses something real
> here:** IP-exhaustion pressure is invisible until they configure that delivery, and Auto Mode
> "defaults to using prefix delegation (/28 prefixes)", so every node reserves a block of subnet
> addresses and subnet pressure is **higher** than on a standard cluster, not lower. Until the IPAM logs
> are on, the closest thing this report has is `net-1` — and it is worth being precise about what that is.
> `net-1` counts **free addresses** in the cluster subnets; prefix delegation allocates whole **/28
> blocks**. Those are different quantities, and on a subnet shared with other workloads they come apart
> quickly: hundreds of free addresses can be left with no fully-free /28 among them, at which point a node
> stops receiving prefixes and falls back to assigning single addresses — still working, but no longer at
> the density Auto Mode assumes. So read `net-1` as an upper bound on headroom rather than a measurement of
> it, unless its own detail says it counted blocks.
> **`na` requires that EVERY EC2 node is an Auto Mode node** — every one carrying
> `eks.amazonaws.com/compute-type: auto`, with Fargate nodes excluded and at least one EC2 node present.
> On a **mixed-mode** cluster the `na` would be a false statement about the cluster in front of you: the
> non-Auto-Mode nodes still run the `aws-node` VPC CNI DaemonSet, AWS says so ("if your cluster combines
> Auto mode with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS
> Fargate, these add-ons remain necessary"), and the helper is deployable for them. So a mixed-mode cluster is
> **measured**: no `cni-metrics-helper` Deployment is a real `none`, and the finding names how many nodes
> are Auto Mode nodes so the reader can see that both fixes below apply at once — the DaemonSet path for
> the non-Auto-Mode nodes, the log-delivery path for the Auto Mode ones.
> **Fargate-only compute:** `na`. The helper reads the `aws-node` DaemonSet on worker nodes, and AWS says "Daemonsets aren't supported on Fargate"; a version of the VPC CNI ships with each Fargate node. On a cluster with EC2 nodes beside Fargate the question is graded for the EC2 nodes.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. A cni-metrics-helper instruments the Amazon VPC CNI, and AWS documents that the VPC CNI is not compatible with hybrid nodes — its `aws-node` DaemonSet carries anti-affinity for `eks.amazonaws.com/compute-type=hybrid` — so there is no VPC CNI on one to instrument.
> **Another CNI on EC2 nodes:** `na`. When `kube-system/aws-node` is absent or schedules onto no node (Cilium's ENI-mode install patches it with a nodeSelector that no node carries), the nodes run another CNI. The helper reads only the metrics that `aws-node` publishes, so there is nothing for it to instrument; any equivalent visibility comes from that CNI.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Remediation:** Which fix applies depends on the compute mode — the two are not interchangeable, **and on
a mixed-mode cluster you need both**: the helper covers the nodes that still run the VPC CNI DaemonSet, and
`AUTO_MODE_IPAM_LOGS` covers the Auto Mode nodes. Neither one covers the whole fleet on its own.

**Not applicable to an EKS Hybrid Node** — there is no `aws-node` DaemonSet on one to instrument, so none of the steps below reaches a hybrid node. If the verdict named hybrid nodes, the equivalent visibility is whatever your Cilium or Calico installation exports.

**Standard cluster (VPC CNI runs as a DaemonSet).** Deploy the helper and read the metrics in CloudWatch.
The helper publishes with `cloudwatch:PutMetricData`, which the default EKS node-role policies do not
grant: add it to the node role or to an IRSA / Pod Identity role for the helper's service account. The
helper's pod goes Ready whether or not its publishes succeed, so confirm the metrics appear in CloudWatch:

```bash
kubectl apply -f https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.19.2/config/master/cni-metrics-helper.yaml
# then alarm on the published CloudWatch metrics, e.g. totalIPAddresses vs assignIPAddresses
```

**EKS Auto Mode.** The command above cannot work: there is no `aws-node` DaemonSet to scrape. Ask AWS
for the equivalent stream instead — the `AUTO_MODE_IPAM_LOGS` log type, delivered through CloudWatch
Vended Logs in three API calls:

```bash
# 0. the destination must exist first — this one is a log group; an S3 bucket or Firehose stream works too
aws logs create-log-group --region <REGION> --log-group-name /aws/eks/<CLUSTER>/ipam
aws logs put-retention-policy --region <REGION> --log-group-name /aws/eks/<CLUSTER>/ipam --retention-in-days 30

# 1. name the cluster capability as a delivery source
aws logs put-delivery-source --region <REGION> --name <CLUSTER>-ipam --log-type AUTO_MODE_IPAM_LOGS \
  --resource-arn arn:aws:eks:<REGION>:<ACCOUNT_ID>:cluster/<CLUSTER>

# 2. name where the logs go, and keep the ARN it returns
aws logs put-delivery-destination --region <REGION> --name <CLUSTER>-ipam-dest \
  --delivery-destination-configuration destinationResourceArn=arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:/aws/eks/<CLUSTER>/ipam \
  --query 'deliveryDestination.arn' --output text

# 3. pair the two — <DEST_ARN> is the ARN printed by step 2, not a name
aws logs create-delivery --region <REGION> --delivery-source-name <CLUSTER>-ipam \
  --delivery-destination-arn <DEST_ARN>
```

The other three Auto Mode log types — `AUTO_MODE_COMPUTE_LOGS`, `AUTO_MODE_BLOCK_STORAGE_LOGS`,
`AUTO_MODE_LOAD_BALANCING_LOGS` — are configured the same way, each as its own delivery source. This is
billed as CloudWatch Vended Logs delivery plus storage at the destination, and the destination may need
a resource policy allowing delivery, so treat it as a change with a cost and a permissions step, not a
switch. Control plane logging (`ope-6`) does **not** cover any of these.

---

### ope-11: Are you using AWS CloudTrail to audit EKS API calls and IRSA actions?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. EKS API calls and IRSA assume-role
     events are both management events, and every trail records management events by default,
     so the remediation asks for no event selectors: that would imply config work a default
     trail doesn't need. It gives the create-trail/start-logging commands, states the real cost
     model (first management-event copy per Region is free; data events are billed from the
     first event, with no free tier), and adds get-trail-status because the scorer's own
     comment says it checks configuration only and cannot see IsLogging. Verified 2026-09-11
     against
     docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-trail-manage-costs.html and
     the CLI reference for create-trail/get-trail-status. -->

> CloudTrail provides API-level audit logging for compliance.

**Remediation:** A multi-region trail's default **management events** already cover EKS control-plane
API calls and IRSA's `sts:AssumeRoleWithWebIdentity` — no custom event selector is needed for either.
**Cost:** AWS delivers the first copy of management events in each Region free of charge, so one
multi-region trail costs nothing extra for management events alone — "if you have one trail that is
logging management events, there are no CloudTrail charges to log management events on that trail."
Data events are different: "For data events, all deliveries incur CloudTrail costs, including the
first" — so only turn on data events (S3 object-level, Lambda invoke, etc.) if you specifically need
that granularity, and expect an ongoing per-event charge with no free tier
(https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-trail-manage-costs.html).
`<BUCKET>` must already exist with a bucket policy that lets the `cloudtrail.amazonaws.com` service
principal call `s3:GetBucketAcl` on the bucket and `s3:PutObject` under `AWSLogs/<ACCOUNT_ID>/`;
without it `create-trail` fails with `InsufficientS3BucketPolicyException`. Attach the policy AWS
publishes at https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-s3-bucket-policy-for-cloudtrail.html
first, then:

```bash
aws cloudtrail create-trail --name <NAME> --s3-bucket-name <BUCKET> --is-multi-region-trail
aws cloudtrail start-logging --name <NAME>
```

This question's detection reads trail **configuration** only — a multi-region trail can exist and still
not be logging. Confirm separately:

```bash
aws cloudtrail get-trail-status --name <NAME> --query 'IsLogging'
```

---

### ope-12: Is Kubernetes audit logging enabled to track API authorization decisions?

**Detection:** 🔬 AUTO-DETECTABLE — the scorer answers `na` unconditionally; see its comment.

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote
     and the Remediation block so the renderer does not extract it. The scorer for this
     id returns a flat `na~deduplicated: the audit on/off fact is scored as sec-26
     (Security) and is 1 of the 5 log types in ope-6, where a disabled audit log lowers
     that ratio (e.g. 4/5 = most) rather than failing it` — it reads the same
     cluster.logging.clusterLogging field ope-6 and sec-26 already score and never
     computes an independent verdict from it. So the remediation cross-references ope-6
     rather than restating its fix in different words, and carries no
     "Commands"/"Analysis: percentage-based scoring" boilerplate, which would describe
     a calculation this question never performs on a High-weighted question with no
     path to `all`/`none`. A THIRD hand-maintained copy of the same
     enable-audit-logging procedure would be a drift surface no test catches. Checked
     2026-09-11. -->

> This question asks specifically about Kubernetes audit logging, but that fact is already measured
> twice elsewhere from the same `cluster.logging.clusterLogging` field: sec-26 (Security pillar,
> governance-compliance) scores the on/off fact, and ope-6 counts `audit` as 1 of its 5 control plane
> log types, so in this pillar a disabled audit log lowers ope-6's ratio (e.g. 4/5, `most`) rather than
> failing a question. Rather than compute a third verdict from one field, this question always answers
> `na` and does not add to or subtract from the pillar score — it stays in the question set so the
> Well-Architected question text has a place in the report, not as an independent measurement.

**Remediation:** See **ope-6** — enabling Kubernetes audit logging is that remediation's
`update-cluster-config --logging` command with `"audit"` in the `types` array (it is included when you
enable all five, which is the common case). Follow the same asynchronous poll and the same
`put-retention-policy` step there: `audit` is typically the highest-volume of the five log types, so the
cost and async-completion guidance apply to it at least as much as to the other four. This section does
not repeat those commands — a procedure hand-copied into three questions drifts three ways when one of
them is updated and the other two are not.

---

### ope-13: Do you have an ongoing upgrade plan aligned with the EKS Kubernetes version support lifecycle?

**Detection:** ✋ ASK USER

> Regular upgrades ensure security patches and feature access.

**Remediation:** Create a documented upgrade schedule aligned with the EKS version calendar. Test upgrades in non-prod first. Use `eksctl upgrade cluster` or Terraform.

---

### ope-14: Do you have a non-production test environment for validating EKS upgrades before production?

**Detection:** ✋ ASK USER

> Test environments prevent upgrade-related outages in production.

**Remediation:** Create a dedicated staging EKS cluster in a separate AWS account. Test all upgrades and add-on updates there before applying to production.

---

### ope-15: Are worker nodes managed using EKS Managed Node Groups?

**Detection:** 🔬 AUTO-DETECTABLE

> Managed Node Groups automate node patching, updates, and replacement.
> **EKS Auto Mode satisfies this question without any node group.** It is one of the three EKS node
> types, and AWS launches, patches, upgrades and replaces its nodes for you — so a cluster whose EC2
> nodes are all Auto Mode nodes scores `all` here, not `none`, and has nothing to migrate.
> **On a mixed-mode cluster the answer comes from counting nodes, not from reading the cluster flag.** This
> question asks whether the worker nodes are **managed**, and both mechanisms manage: a node counts as
> managed if it carries `eks.amazonaws.com/compute-type: auto` **or** `eks.amazonaws.com/nodegroup`. So a
> cluster running Auto Mode alongside a managed node group can legitimately score `all` — every node has
> an AWS-owned lifecycle — and the finding names **both** populations with their counts rather than
> claiming "a managed node group is not the mechanism here" about nodes for which it plainly is. A
> genuinely **self-managed** node is in neither population, still lowers the ratio, and is what the
> remediation below is addressed to. A cluster with the Auto Mode flag on whose nodes carry neither label
> scores `none`: neither label says AWS manages them, whatever the flag says.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. A hybrid node joins through a `HYBRID_LINUX` access entry and `nodeadm`, on hardware the operator owns, and cannot be placed in an EKS managed node group at all.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws eks list-nodegroups --cluster-name <CLUSTER> --region <REGION>
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
# The flag above is not the answer on its own — count the nodes each mechanism owns:
kubectl get nodes -L eks.amazonaws.com/compute-type,eks.amazonaws.com/nodegroup
# "auto" in the first column or any value in the second = managed. Blank in both = counted as not managed.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- the denominator is EC2 nodes (Fargate excluded); a node passes if it is an Auto Mode node **or** in a
  managed node group, so an all-Auto-Mode cluster and a fully-node-grouped one both reach `all`, and a
  mixed-mode cluster's band is the union of the two populations over the whole EC2 node set

**Remediation:** Migrate self-managed nodes to EKS Managed Node Groups: `eksctl create nodegroup --cluster <name> --managed`. This automates patching and updates.

**Not applicable to an EKS Hybrid Node** — a hybrid node cannot be placed in a managed node group under any configuration, so do not run these steps against one. Its lifecycle is `nodeadm` on hardware you own.

**On a mixed-mode cluster, scope this to the nodes the finding names as carrying neither label** — the Auto Mode nodes
and the existing node-group nodes are already covered and are not what the command above is for. Whether
you migrate the remainder into a node group or into Auto Mode is a choice; AWS notes that running Auto Mode
next to self-managed Karpenter is a migration or advanced configuration rather than a steady state, so
converging on one mechanism is worth planning even when this question already reads `all`.

---

### ope-16: Are core EKS add-ons (VPC CNI, CoreDNS, kube-proxy) managed as EKS managed add-ons?

**Detection:** 🔬 AUTO-DETECTABLE

> EKS managed add-ons receive AWS-managed updates and configuration.
> **An all-Auto-Mode cluster satisfies this question with no add-ons at all**, the same way `ope-15`
> satisfies the managed-node-group question with no node group. AWS: "Additionally, you no longer need to
> update components like: Amazon VPC CNI / AWS Load Balancer Controller / CoreDNS / `kube-proxy` /
> Karpenter / AWS EBS CSI driver … EKS Auto Mode replaces these components with service functionality."
> The question asks whether these components are EKS-managed; AWS running them below the add-on layer is
> a stronger form of that outcome, so a cluster whose EC2 nodes all carry
> `eks.amazonaws.com/compute-type: auto`, with no Fargate or hybrid node beside them, scores `all` here
> and has nothing to migrate. Any add-on the
> operator installs **on top of** Auto Mode is still theirs to update — AWS lists "Amazon EKS Add-ons"
> under what you remain responsible for.
> **On a mixed-mode cluster the add-ons are not replaced and this question is measured normally.** AWS is
> explicit: "However, if your cluster combines Auto mode with other compute options like self-managed EC2
> instances, Managed Node Groups, or AWS Fargate, these add-ons remain necessary." So `vpc-cni`, `coredns`
> and `kube-proxy` are still load-bearing for the non-Auto-Mode nodes, and whether each is an EKS managed
> add-on is a real question with a real answer — counted out of three exactly as on a standard cluster,
> with the finding noting how many nodes are Auto Mode nodes. Reading `all` off the cluster flag here
> would print "there is no add-on version left for the operator to manage" about add-ons sitting in the
> cluster's own add-on list.
> **Being named in the add-on list is not enough — the add-on has to be working.** `list-addons` returns
> a NAME and nothing else, so counting membership alone reported all three patched on a cluster whose
> `coredns` add-on had no healthy replica. Each of the three counts here only when `describe-addon`
> reports it `ACTIVE` with no health issues, the same two fields `lens-7` reads for `vpc-cni`. A
> `CREATE_FAILED` or `DEGRADED` add-on is still the operator's to fix, and it is delivering neither the
> AWS-managed update this question is about nor the component itself, so the finding names it and says
> which status and which health issue codes it reported.
> **On a Fargate-only cluster exactly one of the three applies, so the answer comes from `coredns`
> alone.** `kube-proxy` is out because AWS says "The add-on isn't deployed to Fargate nodes in your
> cluster"; `vpc-cni` is out because "A version of the add-on is deployed with each Fargate node in your
> cluster, but you don't update it on Fargate nodes" — AWS owns that version, so its absence from the
> add-on list is not something the operator can act on. `coredns` is **not** excused: it runs as pods
> rather than on the node, it is installable as the `coredns` EKS add-on on any compute type, and on
> Fargate-only compute the operator has extra work to do rather than less — AWS: "By default, CoreDNS is
> configured to run on Amazon EC2 infrastructure on Amazon EKS clusters. If you want to only run your Pods
> on Fargate in your cluster, complete the following steps", i.e. give CoreDNS its own Fargate profile and
> restart it. So this question is measured on Fargate, not marked not-applicable; the two add-ons that
> cannot exist there simply leave the count. The same `coredns`-only answer applies when every EC2 node is
> an Auto Mode node and the cluster also runs Fargate nodes: Fargate is one of the compute options AWS names
> in "these add-ons remain necessary", Auto Mode covers its own nodes, and on the Fargate nodes `coredns` is
> the one of the three the operator manages.
> **EKS Hybrid Nodes:** On an EKS Hybrid Node the denominator is two, not three: `coredns` and `kube-proxy` both apply, and `vpc-cni` does not, because AWS documents the Amazon VPC CNI as incompatible with hybrid nodes. Pod networking there comes from Cilium or Calico, which is not an EKS managed add-on and whose version this review does not read.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# Check for: vpc-cni, coredns, kube-proxy
aws eks describe-addon --cluster-name <CLUSTER> --region <REGION> --addon-name coredns \
  --query "addon.{status:status,issues:health.issues[].code}"
# and the same for vpc-cni and kube-proxy: the name alone is not the answer, ACTIVE with no health
# issue is — a CREATE_FAILED add-on is in the list and is not managing anything
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
# true is NOT the whole answer — the add-ons are replaced only on nodes that are Auto Mode nodes:
kubectl get nodes -L eks.amazonaws.com/compute-type
# every EC2 node "auto" -> an empty add-on list is the expected shape, not a gap
# a mix -> the three add-ons remain necessary, and the count out of three is the answer
# every node "fargate" -> only coredns applies; kube-proxy and vpc-cni are AWS's on Fargate nodes
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all`, from the node population
  rather than the add-on count (Fargate nodes excluded from that test, and a cluster with no EC2 node never
  satisfies it); any non-Auto-Mode EC2 node → count the three add-ons as on a standard cluster
- an add-on counts only when `describe-addon` reports it `ACTIVE` with no `health.issues`; one that is in
  the add-on list and not working is counted as failing, and the finding names its status and issue codes
- nodes exist and none is an EC2 node (Fargate-only) → the band comes from `coredns` alone: it is an EKS
  managed add-on, `ACTIVE` and free of reported health issues → `all`, otherwise → `none`. `vpc-cni` and
  `kube-proxy` are neither counted nor required

**Remediation:** Migrate VPC CNI, CoreDNS, and kube-proxy to EKS managed add-ons: `aws eks create-addon --cluster-name <name> --addon-name vpc-cni --resolve-conflicts OVERWRITE`, and the same for `coredns` and `kube-proxy`.
Without the flag the migration can fail. With the default `NONE`, AWS says that if a self-managed
copy is installed "Amazon EKS doesn't change the value. Creation of the add-on might fail", and `PRESERVE`
behaves the same way at creation. `OVERWRITE` changes every field that differs to the EKS default, so
first record any setting you changed on the self-managed copy (for VPC CNI, `aws-node` environment
variables such as `WARM_IP_TARGET` or custom networking) and pass it back with `--configuration-values`
in the same command (https://repost.aws/knowledge-center/eks-prevent-conflicts-managed-addons).

**On an all-Auto-Mode cluster there is nothing to do here, and installing these add-ons is a regression** —
they would run alongside the service functionality that already provides them. If you are migrating a
standard cluster to Auto Mode, the add-ons come out as part of that move, not into it.

**On a mixed-mode cluster the command above does apply**, and it is the mid-migration state that makes it
apply: the add-ons "remain necessary" for the nodes Auto Mode is not running, so make them EKS managed
add-ons rather than self-managed manifests, and take them out only when the last non-Auto-Mode node goes.

**On a Fargate-only cluster do the CoreDNS half only.** Creating the `vpc-cni` or `kube-proxy` add-on
there achieves nothing — neither is deployed to Fargate nodes and the CNI version on a Fargate node is
AWS's — so the whole of this fix is:

```bash
aws eks create-addon --cluster-name <CLUSTER> --region <REGION> --addon-name coredns
# over a self-managed CoreDNS this may need --resolve-conflicts OVERWRITE: see the caveat above
# and, because Fargate schedules only what a profile matches, give CoreDNS a profile and restart it:
aws eks create-fargate-profile --cluster-name <CLUSTER> --region <REGION> \
  --fargate-profile-name coredns --pod-execution-role-arn <POD_EXECUTION_ROLE_ARN> \
  --selectors namespace=kube-system,labels={k8s-app=kube-dns} --subnets <PRIVATE_SUBNET_IDS>
kubectl rollout restart -n kube-system deployment coredns
```

The profile and restart are the steps AWS documents for running CoreDNS on Fargate-only compute; without
them the CoreDNS pods stay `Pending` and nothing in the cluster resolves DNS, which is a larger outage than
the add-on question this finding is about.

---

## CronJob workload shape

<!-- This question -- a CronJob concurrency check -- sits under a heading that describes it, not under "Business Continuity" or
     "Change Management", which it is not about. DELETING A `##` HEADING HAS TO BE
     CHECKED BY HAND, because nothing checks it for you. The renderer's prose defect
     fires on a question block that a `## ` heading had to TERMINATE, so deleting such
     a heading removes the DETECTOR along with the terminator: the two blocks then
     merge SILENTLY, at exit 0 with no defect, the area's prose absorbed into the
     preceding question's "How to fix" panel. A heading is safe to delete only where
     the preceding question's block already ends with `---` before it, which is what
     bounds a remediation -- verify that before deleting any `##`, and do not expect a
     failing run to tell you. Nothing parses these `##` lines (the renderer keys on
     `### <id>: <title>` only), so the heading's only job is to tell a reader what is
     under it. -->

### ope-18: Do CronJobs set a concurrency policy other than the default Allow?

**Detection:** 🔬 AUTO-DETECTABLE

> With the default `concurrencyPolicy: Allow`, a run that is still going when the next schedule fires gets a second Job beside it, so slow runs pile up concurrently.

**Commands:**
```bash
kubectl get cronjobs -A -o json
# Check spec.concurrencyPolicy (the history limits are not graded: the API server defaults them)
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `concurrencyPolicy: Forbid` (skip a run while the previous one is still active) or `Replace` (stop the running Job and start the new one) on each CronJob. The history limits need no change to pass: the API server already stores `successfulJobsHistoryLimit: 3` and `failedJobsHistoryLimit: 1` when a CronJob omits them.

---

## EKS upgrade-readiness insights

<!-- This heading names what `ope-20` reports: the UPGRADE_READINESS insights AWS publishes
     for the cluster. It measures nothing about capacity, headroom or growth, so it does not
     sit under "Capacity Planning", which heads the NEXT question (`ope-19`, below) because
     that is what `ope-19` is about. Question order in this file is not meaningful --
     `score.sh` reads only the first fenced bash block and the report orders questions itself
     -- so putting a question under the right heading is a heading change and nothing more.
     Nothing parses these `##` lines; the heading's only job is to tell a reader what is under
     it. -->

### ope-20: Do the EKS upgrade-readiness insights AWS computes for this cluster all pass?

**Detection:** 🔬 AUTO-DETECTABLE

> Amazon EKS scans the cluster's control-plane audit logs once a day and publishes an `UPGRADE_READINESS`
> insight per check — deprecated API usage, add-on version compatibility, and kubelet/kube-proxy version
> skew against the next Kubernetes release. It costs nothing and is already running; an insight in
> `ERROR` is a concrete blocker on the next upgrade, named by AWS rather than inferred here.

**Commands:**
```bash
aws eks list-insights --cluster-name <CLUSTER> --region <REGION>
aws eks describe-insight --id <ID> --cluster-name <CLUSTER> --region <REGION>   # affected resources
```

**Analysis:** ratio of `UPGRADE_READINESS` insights whose status is `PASSING`, over all of them.
`na` when AWS reports none. Insights in other categories are listed as context and not graded — this
question is about upgrade readiness only.

**Note on freshness and scope.** The status reflects a **30-day rolling window** over the audit logs, so a
deprecated API that was fixed yesterday can still read `ERROR` until the last matching log entry ages out;
and an insight can read `UNKNOWN` when the control-plane audit log AWS reads it from is not enabled
(`ope-6`). Neither is re-derived here — the verdict is AWS's own, reported as found.

**Remediation:** Read the failing insight with `describe-insight`, which names the affected resources.
Deprecated-API findings mean updating the manifests or charts that call the removed version before
upgrading; add-on compatibility findings mean updating the add-on first (see `lens-7`); version-skew
findings mean bringing nodes up to a supported skew from the control plane.

---

## Capacity Planning

### ope-19: Do you perform regular capacity planning reviews to ensure your EKS cluster can handle projected growth, seasonal traffic spikes, and maintain adequate resource headroom for scaling?

**Detection:** ✋ ASK USER

> Evaluate proactive capacity planning practices to prevent resource exhaustion and ensure optimal cluster performance.

**Remediation:** Conduct quarterly capacity reviews using Prometheus metrics. Set alerts at 70% CPU/memory utilization. Plan for 30% headroom above peak usage.

---

## Fargate Profile Management

### fargate-1: Are Fargate profile namespace selectors specific (not just default/kube-system)?

**Detection:** 🔬 AUTO-DETECTABLE

> Specific selectors prevent unintended workloads from running on Fargate.

**Commands:**
```bash
aws eks describe-fargate-profile --cluster-name <CLUSTER> --fargate-profile-name <PROFILE> --region <REGION>
# A profile passes when no selector takes all of default or kube-system: every selector names another
# namespace (wildcards count by what they match) or carries labels. Selectors are OR-ed, so one broad
# selector makes the whole profile broad.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Use specific namespace selectors in Fargate profiles instead of broad defaults. Where a profile has to select `default` or `kube-system`, add labels to that selector — for CoreDNS on a Fargate-only cluster, `namespace=kube-system,labels={k8s-app=kube-dns}`. A profile's selectors are OR-ed — a pod that matches any one of them runs on Fargate — so one label-less `default` or `kube-system` selector captures every pod in that namespace even when the profile's other selectors are specific.

---

### fargate-2: Do Fargate pods have CPU and memory resource requests defined?

**Detection:** 🔬 AUTO-DETECTABLE

> Fargate uses requests for pod sizing — missing requests waste capacity.

**Commands:**
```bash
kubectl get pods -A -o json
# For Fargate pods, check resources.requests on containers
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add CPU and memory resource requests to all Fargate pod containers. Fargate uses requests for pod sizing — missing requests waste capacity and money.

---

### fargate-4: Is the Fargate built-in log router configured with a log destination?

**Detection:** 🔬 AUTO-DETECTABLE

> Fargate pods have no node to run a log agent on, so AWS runs the log router **for you**: "Amazon EKS
> on Fargate offers a built-in log router based on Fluent Bit. This means that you don't explicitly run
> a Fluent Bit container as a sidecar, but Amazon runs it for you. All that you have to do is configure
> the log router." Without that configuration, Fargate pod logs go nowhere — there is no node-level
> fallback to catch them.

**Commands:**
```bash
kubectl get configmap aws-logging -n aws-observability -o json
kubectl get namespace aws-observability -o jsonpath='{.metadata.labels}'
# Passes when output.conf holds an [OUTPUT] section, no value holds a section other than [FILTER], [OUTPUT] or [PARSER], the values total at most 5,300 characters, and the namespace carries aws-observability: enabled. AWS: "At least one supported Output plugin has to
# be provided in the ConfigMap to enable logging. Filter and Parser aren't required."
```

**Analysis:** Boolean on the log destination, not a percentage:
- an `[OUTPUT]` plugin is declared and the namespace carries `aws-observability: enabled` → `all`
- an `[OUTPUT]` plugin is declared but the namespace lacks that label → `some` (AWS requires the label)
- the ConfigMap exists but declares no `[OUTPUT]` (a commented-out `# [OUTPUT]` is not one), or carries a section other than `[FILTER]`, `[OUTPUT]` or `[PARSER]` (such as `[SERVICE]` or `[INPUT]`), or its values exceed 5,300 characters → `some` (Fargate ships nothing; the config is inert or rejected)
- no ConfigMap, but pods on Fargate nodes run a `fluent` sidecar → `most` (works, but not the documented path; a log-agent DaemonSet on EC2 nodes does not count, because DaemonSets do not run on Fargate)
- neither → `none`
- no Fargate profiles → `na`

**Remediation:** Create the namespace and ConfigMap AWS looks for. The ConfigMap **must** be named
`aws-logging` in namespace `aws-observability`, and the namespace **must** carry the label
`aws-observability: enabled`. Two things decide whether this works, and both come before the command:

- **You substitute the Region and cluster name yourself, and nothing checks that you did.** AWS's
  instruction for this ConfigMap is to "replace every `example value` with your own values", and for the
  CloudWatch example "The parameters under `[OUTPUT]` are required". Fargate validates the section names,
  the required keys inside them (`Name`, `match`) and the plugin name against its supported list — it does
  not validate the values. So a ConfigMap left holding a `<REGION>` placeholder is **accepted**: the pod
  starts, its annotations show logging enabled, and nothing is ever delivered. That is the failure most
  easily mistaken for success here. `${ENV_VAR}` is not an escape either — AWS: "Environment variables
  such as `${ENV_VAR}` aren't allowed in the `ConfigMap`" — so the substitution has to happen before the
  manifest reaches the cluster, which is what the two shell variables below are for.
- **The change reaches new pods only.** AWS: "Amazon EKS Fargate logging doesn't support dynamic
  configuration of a `ConfigMap`. Any changes to a `ConfigMap` are applied to new Pods only. Changes
  aren't applied to existing Pods." Budget the pod recycle as part of this change, not as a follow-up:
  until the pods are replaced, the cluster keeps shipping exactly what it shipped before.

```bash
REGION='<REGION>'; CLUSTER='<CLUSTER>'   # edit this line FIRST — nothing else substitutes these

# The namespace, applied on its own. (Two heredocs rather than one manifest with a YAML document
# separator: a line of three dashes inside this block would end the report's remediation extraction and
# the rest of this fix would never reach the reader.)
kubectl apply -f - <<'EOF'
kind: Namespace
apiVersion: v1
metadata:
  name: aws-observability
  labels:
    aws-observability: enabled
EOF

# The ConfigMap. This heredoc is deliberately UNQUOTED, so the shell expands $REGION and $CLUSTER before
# kubectl sees the manifest and the ConfigMap that lands holds literal values, not variable references.
kubectl apply -f - <<EOF
kind: ConfigMap
apiVersion: v1
metadata:
  name: aws-logging
  namespace: aws-observability
data:
  output.conf: |
    [OUTPUT]
        Name cloudwatch_logs
        Match   kube.*
        region $REGION
        log_group_name /aws/eks/$CLUSTER/fargate
        log_stream_prefix from-fluent-bit-
        auto_create_group true
EOF

# Read back what actually landed. This is the check that catches the silent failure: neither an angle
# bracket nor a dollar sign should appear in the output.
kubectl get configmap aws-logging -n aws-observability -o jsonpath="{.data.output\.conf}"

# Then recycle the pods that are meant to start logging — see the second bullet above.
kubectl rollout restart -n <NAMESPACE> deployment <DEPLOYMENT>
```

Then grant the **Fargate pod execution role** permission to write to the destination — the log router
runs under that role, not the pod's service account.

Constraints worth knowing before you write the config:

- Only `[FILTER]`, `[OUTPUT]` and `[PARSER]` sections are accepted, under the matching keys
  (`filters.conf`, `output.conf`, `parsers.conf`). Fargate manages `Service` and `Input`; supplying
  either is rejected.
- The ConfigMap cannot exceed **5,300 characters**, and `${ENV_VAR}` substitution is not allowed (which
  is why the values are substituted by the shell above, before the manifest is applied).
- Indentation has to be consistent within each of `filters.conf`, `output.conf` and `parsers.conf`, and
  AWS requires key-value pairs to be "indented more than directives" — the template above already is.
- Supported outputs: `cloudwatch`, `cloudwatch_logs`, `es`, `firehose`, `kinesis_firehose`, `kinesis`.
- To check whether it took effect: `kubectl describe pod <name>` and read the annotations. A failure
  shows as `Logging: LoggingDisabled: LOGGING_CONFIGMAP_NOT_FOUND`.
- There must be network egress from the cluster VPC to the log destination — relevant if you have
  narrowed the cluster security group's egress (see `net-4`).

> **Not the sidecar path.** Fargate's log router is built in and needs no Fluent Bit **sidecar**, and
> **FireLens** (with `amazon/aws-for-fluent-bit`) is an **Amazon ECS** feature that does not apply to EKS.

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-1: Is Node Problem Detector deployed for node health monitoring?

**Detection:** 🔬 AUTO-DETECTABLE

> NPD detects node-level issues like kernel deadlocks and filesystem corruption.
> **AWS's own component for this is the EKS node monitoring agent, and it arrives by three documented
> routes — any of them scores `all` here where it is running on at least one node.** From `node-health.html`: the node monitoring agent and automatic
> node repair "are automatically enabled with EKS Auto Mode compute", and "For other EKS compute types, you
> can add the node monitoring agent as an EKS add-on or you can manage it with Kubernetes tooling such as
> Helm." So the three paths are (1) every EC2 node is an Auto Mode node, (2) the
> **`eks-node-monitoring-agent`** EKS managed add-on is enabled — "The Amazon EKS add-on name is
> `eks-node-monitoring-agent`" — or (3) a self-managed DaemonSet, which is where `node-problem-detector`
> fits. Route 2 is the one to reach for on a standard cluster: it is AWS's supported path, it needs no extra
> IAM permissions, and its signals are what `automatic node repair` consumes to replace a bad node
> (`NodeCondition`s `KernelReady`, `NetworkingReady`, `StorageReady`, `ContainerRuntimeReady`,
> `AcceleratedHardwareReady`). A cluster running route 2 with no NPD DaemonSet is **not** a finding.
> **Each route is credited only where it is actually running.** Route 2 counts when `describe-addon`
> reports `eks-node-monitoring-agent` `ACTIVE` with no health issues and the cluster has at least one Linux
> EC2 or hybrid node for its DaemonSet to run on, not merely when the name is in `list-addons`: a `CREATE_FAILED` add-on carrying an `AccessDenied` health issue installs no DaemonSet, so
> crediting its name would report node-problem detection on a cluster that has none. Route 3 needs at least
> one ready pod in the DaemonSet, for the same reason — a `node-problem-detector` scaled to zero detects
> nothing. A broken route 2 does not veto route 3: the routes are still tried in order, so a cluster with a
> failed add-on and a working `node-problem-detector` DaemonSet still scores `all` off the DaemonSet. Route 3
> also credits an `eks-node-monitoring-agent` DaemonSet installed with the Helm chart, but not the one the
> add-on itself deploys: while the add-on is listed, its status decides.
> **An all-Auto-Mode cluster already has this below the pod layer**, so it scores `all` with no DaemonSet:
> AWS ships "the node monitoring agent and automatic node repair … automatically enabled with EKS Auto Mode
> compute", and asking such a cluster for a `node-problem-detector` pod is asking it to duplicate something
> it already runs in the node image.
> **The agent rides in the Auto Mode node's AMI, so the credit is per node, not per cluster.** AWS says as
> much in the other direction: "EKS Auto Mode compute includes the node monitoring agent. For other EKS
> compute types, you can add the node monitoring agent as an EKS add-on or you can manage it with
> Kubernetes tool[ing]" — it does not arrive by itself. So this scores `all` only when **every** EC2 node
> carries `eks.amazonaws.com/compute-type: auto`. On a **mixed-mode** cluster the managed-node-group nodes have
> no detection and no automatic repair unless something was deployed for them, so the question falls back to
> measuring the DaemonSet — a mixed-mode cluster that **has** deployed NPD still scores `all` — and the `none`
> finding names how many nodes are covered by the AMI and how many are not.
> **EKS Hybrid Nodes:** EKS Hybrid Nodes are judged here. The EKS node monitoring agent is on the AWS list of add-ons validated for hybrid nodes, so the question is answerable and is graded normally.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# Look for eks-node-monitoring-agent — AWS's supported path on any non-Fargate compute type
aws eks describe-addon --cluster-name <CLUSTER> --region <REGION> \
  --addon-name eks-node-monitoring-agent --query "addon.{status:status,issues:health.issues[].code}"
# the name in the list is not the answer: ACTIVE with no health issue is
kubectl get daemonsets -A -o json
# Look for node-problem-detector, or a self-managed node-monitoring-agent DaemonSet, with numberReady > 0
kubectl get nodes -L eks.amazonaws.com/compute-type
# every EC2 node "auto" -> the agent is in the AMI; a mix -> the others need the add-on or a DaemonSet
kubectl get nodes -o json | jq -r '.items[]|.metadata.name + " " +
  ([.status.conditions[]|select(.type|test("KernelReady|NetworkingReady|StorageReady|ContainerRuntimeReady"))
    |.type + "=" + .status]|join(" "))'
# These conditions only appear once the agent is running, so they are the end-to-end proof
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all` (same gate as `lens-2`)
- the `eks-node-monitoring-agent` EKS managed add-on, `ACTIVE` with no reported `health.issues` → `all`, on
  any compute type except Fargate
- a `node-problem-detector`/`npd` DaemonSet with at least one ready pod → `all` (the "manage it with
  Kubernetes tooling" path)

**Remediation:** Enable the EKS node monitoring agent as a managed add-on — the path AWS documents for
every compute type except Fargate, and the one that feeds automatic node repair:

```bash
aws eks create-addon --cluster-name <CLUSTER> --addon-name eks-node-monitoring-agent --region <REGION>
# it needs no additional IAM permissions. Then let node auto repair act on what it reports:
aws eks update-nodegroup-config --cluster-name <CLUSTER> --nodegroup-name <NODEGROUP> \
  --node-repair-config enabled=true --region <REGION>
```

`node-health.html`: automatic node repair works "with EKS managed node groups and Karpenter", and "When EKS
automatic node repair is enabled with the node monitoring agent installed, EKS automatic node repair reacts
to additional node conditions: `AcceleratedHardwareReady`, `ContainerRuntimeReady`, `KernelReady`,
`NetworkingReady`, and `StorageReady`." Without the agent it reacts only to `Ready`, deleted node objects
and instances that never join.

**Only if you need something the add-on does not report** should you run Node Problem Detector instead. Its
DaemonSet manifest runs as a ServiceAccount defined in `rbac.yaml` and mounts a ConfigMap defined in
`node-problem-detector-config.yaml`, and it names the previous release's image, so apply all three files
from the same release tag and then pin the image to that release:
`kubectl apply -f https://raw.githubusercontent.com/kubernetes/node-problem-detector/v0.8.20/deployment/rbac.yaml -f https://raw.githubusercontent.com/kubernetes/node-problem-detector/v0.8.20/deployment/node-problem-detector-config.yaml -f https://raw.githubusercontent.com/kubernetes/node-problem-detector/v0.8.20/deployment/node-problem-detector.yaml`,
then `kubectl -n kube-system set image daemonset/node-problem-detector node-problem-detector=registry.k8s.io/node-problem-detector/node-problem-detector:v0.8.20`.
Running both NPD and the add-on is duplication, not defence in depth.

**On a mixed-mode cluster the add-on is exactly the right fix** — it covers the non-Auto-Mode nodes, and the
Auto Mode nodes already carry the same agent in their AMI, so the fleet converges on one component. On an
all-Auto-Mode cluster there is nothing to deploy; AWS says so directly: "You do not need to install this
add-on on Amazon EKS Auto Mode clusters."

**On Fargate neither path applies** — the agent works on "any EKS compute types except for AWS Fargate".

---

### lens-7: Is the VPC CNI add-on managed, current, ACTIVE and free of reported health issues?

**Detection:** 🔬 AUTO-DETECTABLE

> Outdated CNI versions miss security patches and performance improvements.
> **An all-Auto-Mode cluster answers both halves of this question — current and healthy — without a
> `vpc-cni` add-on.** Current: pod networking ships in an AMI AWS owns, and "Generally, EKS releases a new
> AMI each week containing CVE and security fixes." Healthy: the node monitoring agent, "automatically
> enabled with EKS Auto Mode compute", publishes `NetworkingReady`, which "indicates whether the node's
> networking stack is functioning correctly (interfaces, routing, connectivity)". So a cluster whose EC2
> nodes all carry `eks.amazonaws.com/compute-type: auto` scores `all`, and there is no add-on version to
> read or update.
> **Both halves are node-scoped, so the credit stops at the Auto Mode nodes.** The weekly AMI is the Auto
> Mode node's AMI and the agent publishing `NetworkingReady` is enabled by Auto Mode **compute** — neither
> reaches a managed node group in the same cluster, where AWS says the add-on is still required: "if your
> cluster combines Auto mode with other compute options like self-managed EC2 instances, Managed Node
> Groups, or AWS Fargate, these add-ons remain necessary." On a **mixed-mode** cluster this therefore measures
> the `vpc-cni` add-on as on a standard cluster — present as a managed add-on is `all`, absent is `none` —
> because for the non-Auto-Mode nodes the add-on genuinely is the mechanism and its currency is genuinely
> the operator's.
> **A Fargate-only cluster also scores `all`, and here AWS is explicit:** "A version of the add-on is
> deployed with each Fargate node in your cluster, but you don't update it on Fargate nodes." There is no
> add-on version for you to read or raise, an empty add-on list is the expected shape, and
> `aws eks update-addon` has nothing to act on. The **healthy** half is not claimed from a node condition
> there: `NetworkingReady` comes from the EKS node monitoring agent, which AWS supports on "any EKS compute
> types except for AWS Fargate", so on Fargate this rests on who owns the component — AWS deploys, patches
> and replaces the Fargate node and the CNI version on it — rather than on a signal this review can read.
> **EKS Hybrid Nodes:** Not judged on an EKS Hybrid Node. AWS documents that the Amazon VPC CNI is not compatible with hybrid nodes and ships its `aws-node` DaemonSet with anti-affinity for the hybrid label, so there is no VPC CNI add-on version, status or health to read.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws eks describe-addon --cluster-name <CLUSTER> --addon-name vpc-cni --region <REGION>
# On an all-Auto-Mode or Fargate-only cluster this returns ResourceNotFoundException by design, and on
# Fargate that is the documented steady state, not a gap. Read the node population
# and the node conditions instead — the compute flag alone does not tell you which nodes are covered:
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
kubectl get nodes -L eks.amazonaws.com/compute-type
kubectl get nodes -o json | jq -r '.items[]|.metadata.name + " " +
  ([.status.conditions[]|select(.type=="NetworkingReady")|.status]|join(","))'
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all`, from the node population
  rather than the add-on version (same gate as `lens-2`); any non-Auto-Mode EC2 node → read the add-on
- nodes exist and none is an EC2 node (Fargate-only) → `all`, because AWS deploys the CNI with the Fargate
  node and the operator does not update it there; the add-on list is not read on that shape
- on the add-on path the verdict is NOT a percentage and NOT the bare presence of the name. It reads
  `.addonDetails[]` (from `describe-addon`) and `.addonTargets[]` (from `describe-addon-versions`), in this
  order, first match wins:
  - `vpc-cni` not in the add-on list → `none` (not an EKS managed add-on)
  - its detail was not collected → `most`, and the detail says so rather than claiming a version
  - `status` is not `ACTIVE` → `none`, naming the status
  - `health.issues` is non-empty → `some`, naming the issue codes
  - the offered-version list was not collected, or a version string does not parse → `most`, "currency
    was not assessed"
  - installed version ≥ `defaultVersion` → `all`
  - installed version older than `defaultVersion` and absent from the offered list → `some`: it cannot be
    updated in place from where it is
  - otherwise → `most`, reporting how many MINOR versions behind the default it is
- currency is decided by PARSING `vMAJOR.MINOR.PATCH[-eksbuild.N]` and comparing
tuples, not by position in the offered list: nothing guarantees the API returns
newest-first, and an index distance would count `-eksbuild.N` rebuilds as
releases

**Remediation:** Update the VPC CNI add-on to a version you name explicitly with `--addon-version`. This question measures against the version EKS marks as the default for the cluster's Kubernetes version, which is not always the newest offered; list it with `aws eks describe-addon-versions --addon-name vpc-cni --kubernetes-version <K8S_VERSION> --query 'addons[].addonVersions[?compatibilities[?defaultVersion]].addonVersion'` (drop `--query` to see every offered version). Move one minor version at a time, as AWS recommends, and keep your settings: `aws eks update-addon --cluster-name <name> --addon-name vpc-cni --addon-version <VERSION> --resolve-conflicts PRESERVE`. Do not use `OVERWRITE` for this: it resets any value you changed — `WARM_IP_TARGET`, prefix delegation, custom networking — to the EKS default on a live CNI.

**Not applicable to an EKS Hybrid Node** — the Amazon VPC CNI is not compatible with one, so there is no `vpc-cni` add-on to update for it. Keep the Cilium or Calico release the hybrid nodes actually run current instead; this review does not read its version.

**On an all-Auto-Mode cluster this command has nothing to act on** — there is no `vpc-cni` add-on, and AWS
rolls the networking capability forward with the weekly AMI. What is worth watching there is the
`NetworkingReady` condition per node (above) and, separately, IP headroom: `ope-10` explains why IPAM
metrics are off by default on Auto Mode, and `net-1` carries the free-address count for the cluster
subnets — an upper bound on prefix-delegation headroom rather than a measurement of it, for the reason
`ope-10` gives.

**On a mixed-mode cluster the command applies to the add-on serving the non-Auto-Mode nodes**, and keeping that
add-on current stays your job for as long as any of those nodes exist — the Auto Mode nodes moving to a
weekly AWS AMI does not carry the rest of the fleet with them.

**On a Fargate-only cluster there is nothing to update and nothing to install.** AWS ships a version of the
CNI with each Fargate node and states that you do not update it there, so `update-addon` and `create-addon`
are both wrong answers on this shape. If you later add EC2 or Auto Mode nodes, this question starts
measuring the add-on again, because those nodes do need it.

---
