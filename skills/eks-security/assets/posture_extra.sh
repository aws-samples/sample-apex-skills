#!/usr/bin/env bash
# Containment checks the Well-Architected security pillar does not have. Companion to posture_score.sh,
# with the same token format and the same bucket rule, so posture_reduce.sh reduces both.
#
# Usage:  posture_extra.sh <workdir>
#   Reads <workdir>/posture/*.json (written by posture_collect.sh) and appends one JSONL token per check to
#   <workdir>/posture/results-extra.jsonl:
#   {"pillar":"security","id":"SEC-POSTURE-<n>","track":"measured","state":"all|most|some|none|na|unknown",
#    "detail":"...","resources":{"pass":[...],"fail":[...],"context":[...]}}
#   A check whose input file was not collected emits `unknown` (never a pass).
#
# Each check exists because WAR's security pillar (commit 7965ae3) does not measure it:
#   SEC-POSTURE-55  IMDS hop limit 1 per node type   lens-11 reads HttpTokens only, not the hop limit
#   SEC-POSTURE-56  default-deny ingress per ns       sec-4 counts namespaces with ANY NetworkPolicy
#   SEC-POSTURE-57  egress control per ns             no WAR question reads pod egress policy
#   SEC-POSTURE-58  hostNetwork/hostPID/hostIPC pods  podsec-2/3 read privileged and hostPath only
#   SEC-POSTURE-59  authenticator log enabled         sec-26 reads the audit log type only
#   SEC-POSTURE-60  GuardDuty EKS Audit Log Monitoring sec-33 sees an agent or add-on, not the detector
#   SEC-POSTURE-61  GuardDuty Runtime Monitoring      (same) the detector feature, not the agent pod
#   SEC-POSTURE-62  ECR registry scanning, continuous lens-12 is always na: it does not read the registry config
#   SEC-POSTURE-63  images pinned by digest           sec-12 also passes an explicit tag, which can move
# Overlaps NOT added (WAR already measures them): public endpoint 0.0.0.0/0 (sec-2), PSA enforce labels
# (sec-11), cluster-admin bindings incl. service accounts (rbac-1), audit log (sec-26), privileged pods
# (podsec-2), hostPath (podsec-3), secrets envelope encryption with a customer key (sec-38), IMDSv2
# required (lens-11), workload identity (sec-6).
#
# Read-only: jq over local files only. GuardDuty is read as detector CONFIGURATION (ListDetectors,
# GetDetector, collected by posture_collect.sh); findings are never read.
set -uo pipefail
umask 077

WORK="${1:?usage: posture_extra.sh <workdir>}"
W="$WORK/posture"
[ -f "$W/cluster.json" ] || { echo "posture_extra.sh: $W has no cluster.json; run posture_collect.sh first" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "posture_extra.sh: jq not found on PATH" >&2; exit 2; }
OUTF="$W/results-extra.jsonl"
if [ -s "$OUTF" ]; then
  echo "posture_extra.sh: $OUTF already holds tokens; this work dir has been scored." >&2; exit 2
fi

# Same bucket rule as the WAR prelude b(): >=90% all, >=70% most, >0 some, 0 none, empty na.
# sysns: the allow-listed system namespaces, the same `^(kube-|amazon-)` filter the copied questions use.
X='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end; def sysns: test("^(kube-|amazon-)"); def blanksel: (. == null) or (((.matchLabels//{})|length)==0 and ((.matchExpressions//[])|length)==0); def ci($k): (.[$k] // .[($k[0:1]|ascii_downcase)+$k[1:]]);'

# x <id> <file>... '<jq program>': the program prints {state, detail, pass?, fail?, context?}.
x(){ local id="$1"; shift; local fs=() m="" r
  while [ "$#" -gt 1 ]; do [ -f "$W/$1.json" ] || m="$m $1.json"; fs+=("$W/$1.json"); shift; done
  if [ -n "$m" ]; then
    r=$(jq -cn --arg d "not collected:$m (the read was denied or failed; see posture/meta.json errors), so this check was NOT measured" '{state:"unknown",detail:$d}')
  else
    r=$(jq -c "$X $1" "${fs[@]}" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed; a malformed collection file is NOT a finding. jq said: %s\n' "$id" "$r" >&2; exit 1; }
  fi
  printf '%s' "$r" | jq -c --arg id "$id" '
    if (.state|IN("all","most","some","none","na","unknown"))|not then error("bad state") else . end
    | {pillar:"security",id:$id,track:"measured",state,detail:(.detail//"")}
      + (if has("pass") or has("fail") then {resources:({pass:(.pass//[]),fail:(.fail//[])}+(if .context then {context} else {} end))} else {} end)' \
    >> "$OUTF" || { printf 'SCORER ABORT [%s]: the token was not emitted\n' "$id" >&2; exit 1; }
}

# ── SEC-POSTURE-55 node-credential: IMDS hop limit 1, per node type ──
# A hop limit of 2 lets every non-hostNetwork pod fetch an IMDSv2 token and so the node role's credentials.
# Pass per instance: metadata endpoint disabled, OR HttpTokens=required with HttpPutResponseHopLimit=1
# (the hop limit bounds only the IMDSv2 token response, so it protects nothing while IMDSv1 is allowed).
# Read off the running instance, not the launch template: the instance value is what is in effect for
# managed node groups, custom launch templates, Karpenter and EKS Auto Mode alike. AWS documents Auto Mode
# nodes as IMDSv2 with hop limit 1, not modifiable (docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html).
# hostNetwork pods reach IMDS at any hop limit; SEC-POSTURE-58 counts those.
x SEC-POSTURE-55 instances nodes '
  input as $nd
  | ([$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")|((.spec.providerID//"")|split("/")|last)]) as $auto
  | [.Reservations[]?.Instances[]?|select(((.State.Name//"")|IN("terminated","shutting-down"))|not)] as $all
  | [$all[]|select(((.Platform//"")|ascii_downcase)=="windows")] as $win
  | [$all[]|select(((.Platform//"")|ascii_downcase)!="windows")] as $i
  | def tag($k): ([.Tags[]?|select(.Key==$k)|.Value]|first);
    def kind: (.InstanceId as $id|if ($auto|index($id)) then "auto-mode" elif tag("eks:nodegroup-name") then "nodegroup:"+tag("eks:nodegroup-name") elif tag("karpenter.sh/nodepool") then "karpenter:"+tag("karpenter.sh/nodepool") else "self-managed-or-other" end);
    def ok: ((.MetadataOptions.HttpEndpoint//"enabled")=="disabled") or ((.MetadataOptions.HttpTokens//"")=="required" and (.MetadataOptions.HttpPutResponseHopLimit//0)==1);
    def n: (.InstanceId//"?")+" ["+kind+"] tokens="+((.MetadataOptions.HttpTokens//"?")|tostring)+" hop="+((.MetadataOptions.HttpPutResponseHopLimit//"?")|tostring);
  ($i|length) as $t | ([$i[]|select(ok)]|length) as $ok
  | ([$i[]|select(ok|not)|kind]|group_by(.)|map("\(.[0]) (\(length))")|join(", ")) as $bad
  | {state:b($ok;$t),
     detail:((if $t==0 then "no running Linux EC2 instance was collected for this cluster, so there is no instance metadata service to assess (Fargate and hybrid nodes have none)"
             else "\($ok)/\($t) Linux EC2 node instances block pod access to IMDS (HttpTokens=required with hop limit 1, or the endpoint disabled)"+(if $bad!="" then "; failing by node type: "+$bad else "" end)
               +"; read off the running instances, so launch-template, Karpenter and Auto Mode settings are judged as in effect" end)
             +(if ($win|length)>0 then " (\($win|length) Windows instance(s) not assessed)" else "" end)),
     pass:[$i[]|select(ok)|n], fail:[$i[]|select(ok|not)|n]}'

# ── SEC-POSTURE-56 lateral-movement: default-deny ingress NetworkPolicy per workload namespace ──
# Default deny = a NetworkPolicy selecting every pod (empty podSelector) whose policyTypes include Ingress
# (Ingress is implied when policyTypes is absent) and which allows no ingress rule. Objects only:
# whether the CNI enforces NetworkPolicy at all is the copied sec-4 (SEC-POSTURE-26).
x SEC-POSTURE-56 networkpolicies namespaces '
  input as $ns
  | [$ns.items[]?|(.metadata.name//"")|select(sysns|not)] as $n
  | ([.items[]?|select((.spec.podSelector|blanksel) and (((.spec.policyTypes//["Ingress"])|index("Ingress"))!=null) and (((.spec.ingress//[])|length)==0))|.metadata.namespace]|unique) as $dd
  | [$n[]|select(. as $x|$dd|index($x))] as $p
  | {state:b(($p|length);($n|length)),
     detail:(if ($n|length)==0 then "no workload namespaces" else "\($p|length)/\($n|length) workload namespaces carry a default-deny ingress NetworkPolicy (empty podSelector, Ingress, no ingress rule); objects only, enforcement is SEC-POSTURE-26 (WAR sec-4)" end),
     pass:$p, fail:($n-$p)}'

# ── SEC-POSTURE-57 lateral-movement: egress control per workload namespace ──
# A namespace counts when a NetworkPolicy selecting every pod lists Egress in policyTypes, so every pod's
# egress is limited to what the policies allow (a default deny plus a DNS allow is the common shape).
x SEC-POSTURE-57 networkpolicies namespaces '
  input as $ns
  | [$ns.items[]?|(.metadata.name//"")|select(sysns|not)] as $n
  | ([.items[]?|select((.spec.podSelector|blanksel) and (((.spec.policyTypes//[])|index("Egress"))!=null))|.metadata.namespace]|unique) as $eg
  | [$n[]|select(. as $x|$eg|index($x))] as $p
  | {state:b(($p|length);($n|length)),
     detail:(if ($n|length)==0 then "no workload namespaces" else "\($p|length)/\($n|length) workload namespaces limit egress for every pod (a NetworkPolicy with an empty podSelector and Egress in policyTypes); the allowed destinations are not judged, and enforcement is SEC-POSTURE-26 (WAR sec-4)" end),
     pass:$p, fail:($n-$p)}'

# ── SEC-POSTURE-58 privilege: no host namespaces outside the system namespaces ──
# hostNetwork, hostPID or hostIPC hands a pod the node's network (IMDS at any hop limit, node-local
# services), process table or IPC. Any such workload pod fails the check, as WAR's podsec-2 does for privileged.
x SEC-POSTURE-58 pods '
  [.items[]?|select((.metadata.namespace//"")|sysns|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $p
  | def hs: [(if .spec.hostNetwork==true then "hostNetwork" else empty end),(if .spec.hostPID==true then "hostPID" else empty end),(if .spec.hostIPC==true then "hostIPC" else empty end)];
    def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");
  [$p[]|select((hs|length)==0)] as $ok | [$p[]|select((hs|length)>0)] as $bad
  | {state:(if ($p|length)==0 then "na" elif ($bad|length)>0 then "none" else "all" end),
     detail:(if ($p|length)==0 then "no workload pods outside the system namespaces (kube-*, amazon-*)" elif ($bad|length)>0 then "\($ok|length)/\($p|length) workload pods use no host namespace; \($bad|length) pod(s) set hostNetwork, hostPID or hostIPC outside kube-* and amazon-*, and any such pod fails this check" else "\($ok|length)/\($p|length) workload pods use no host namespace (system namespaces kube-* and amazon-* are allow-listed)" end),
     pass:[$ok[]|n], fail:[$bad[]|n+" ("+(hs|join(","))+")"]}'

# ── SEC-POSTURE-59 detection: control plane authenticator log ──
# The authenticator log records which IAM principal mapped to which Kubernetes identity; the audit log
# alone (WAR sec-26) does not show the IAM side.
x SEC-POSTURE-59 cluster '
  ([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]?]|unique) as $on
  | {state:(if ($on|index("authenticator")) then "all" else "none" end),
     detail:("control plane log types enabled: "+(if ($on|length)==0 then "none" else ($on|join(", ")) end)+"; authenticator "+(if ($on|index("authenticator")) then "is on" else "is OFF, so IAM-to-Kubernetes identity mapping is not logged" end)),
     pass:(if ($on|index("authenticator")) then ["authenticator"] else [] end), fail:(if ($on|index("authenticator")) then [] else ["authenticator"] end)}'

# ── SEC-POSTURE-60/61 detection: GuardDuty detector configuration in this Region ──
# Feature names from the GuardDuty API (DetectorFeatureConfigurationResult): EKS_AUDIT_LOGS,
# RUNTIME_MONITORING (includes EKS) or the older EKS_RUNTIME_MONITORING; status ENABLED|DISABLED.
# Keys are read in either case (`Features` or `features`) because CLI and SDK spellings differ.
x SEC-POSTURE-60 guardduty '
  [.detectors[]?] as $d
  | [$d[]|select(((ci("Status"))//"")=="ENABLED")] as $on
  | [$on[]|select([(ci("Features"))[]?|select(((ci("Name"))//"")=="EKS_AUDIT_LOGS" and ((ci("Status"))//"")=="ENABLED")]|length>0)] as $p
  | {state:(if ($d|length)==0 then "none" elif ($p|length)>0 then "all" else "none" end),
     detail:((if ($d|length)==0 then "no GuardDuty detector in this Region, so EKS audit log threat detection is off" elif ($on|length)==0 then "the GuardDuty detector is not enabled" elif ($p|length)>0 then "GuardDuty EKS Audit Log Monitoring (EKS_AUDIT_LOGS) is ENABLED on the detector" else "GuardDuty is enabled but EKS Audit Log Monitoring (EKS_AUDIT_LOGS) is not ENABLED" end)+"; configuration only, findings are not read"),
     pass:[$p[]|(ci("DetectorId"))//"?"], fail:[$d[]|select(. as $x|($p|index($x))==null)|(ci("DetectorId"))//"?"]}'
x SEC-POSTURE-61 guardduty '
  [.detectors[]?] as $d
  | [$d[]|select(((ci("Status"))//"")=="ENABLED")] as $on
  | def rm: [(ci("Features"))[]?|select(((ci("Name"))//"")|IN("RUNTIME_MONITORING","EKS_RUNTIME_MONITORING"))|select(((ci("Status"))//"")=="ENABLED")];
    def agent: [(ci("Features"))[]?|select(((ci("Name"))//"")|IN("RUNTIME_MONITORING","EKS_RUNTIME_MONITORING"))|(ci("AdditionalConfiguration"))[]?|select(((ci("Name"))//"")=="EKS_ADDON_MANAGEMENT")|((ci("Status"))//"?")]|first;
  [$on[]|select((rm|length)>0)] as $p
  | {state:(if ($d|length)==0 then "none" elif ($p|length)>0 then "all" else "none" end),
     detail:((if ($d|length)==0 then "no GuardDuty detector in this Region, so runtime threat detection for EKS is off" elif ($p|length)>0 then "GuardDuty Runtime Monitoring is ENABLED (automated agent management EKS_ADDON_MANAGEMENT: "+(($p[0]|agent)//"not set")+"); whether the agent runs on every node is SEC-POSTURE-48 (WAR sec-33)" else "GuardDuty is "+(if ($on|length)==0 then "not enabled" else "enabled but Runtime Monitoring (RUNTIME_MONITORING or EKS_RUNTIME_MONITORING) is not ENABLED" end) end)+"; configuration only, findings are not read"),
     pass:[$p[]|(ci("DetectorId"))//"?"], fail:[$d[]|select(. as $x|($p|index($x))==null)|(ci("DetectorId"))//"?"]}'

# ── SEC-POSTURE-62 supply-chain: ECR registry scanning with continuous rescan ──
# The registry-level configuration decides what is scanned (WAR lens-12 notes the repository flag is
# deprecated and does not read this). all: ENHANCED with a CONTINUOUS_SCAN rule whose filter is `*`;
# some: ENHANCED with continuous scan on narrower filters only (which cluster repositories match is not
# resolved), or ENHANCED with on-push scanning only; none: BASIC scanning (no continuous rescan) or no rule.
x SEC-POSTURE-62 ecr-scanning '
  (.scanningConfiguration//{}) as $c | ($c.scanType//"BASIC") as $t | [$c.rules[]?] as $r
  | [$r[]|select(.scanFrequency=="CONTINUOUS_SCAN")] as $cs
  | ([$cs[]|.repositoryFilters[]?|.filter]|index("*")!=null) as $star
  | def rd: (.scanFrequency//"?")+" on "+([.repositoryFilters[]?|.filter]|join(","));
  {state:(if $t=="ENHANCED" and $star then "all" elif $t=="ENHANCED" and ($r|length)>0 then "some" else "none" end),
   detail:("registry scanType "+$t+"; rules: "+(if ($r|length)==0 then "none" else ([$r[]|rd]|join("; ")) end)
     +(if $t=="ENHANCED" and $star then "; every repository is rescanned continuously" elif $t=="ENHANCED" and ($cs|length)>0 then "; continuous rescan covers the filtered repositories only, and which of the cluster images those match was NOT resolved" elif $t=="ENHANCED" then "; no CONTINUOUS_SCAN rule, so images are not rescanned when new CVEs are published" else "; BASIC scanning has no continuous rescan" end)),
   pass:(if $t=="ENHANCED" then [$cs[]|rd] else [] end), fail:(if $t=="ENHANCED" then [$r[]|select(.scanFrequency!="CONTINUOUS_SCAN")|rd] else ["scanType "+$t] end)}'

# ── SEC-POSTURE-63 supply-chain: workload images pinned by digest ──
# Only an @sha256: digest is immutable; WAR sec-12 also accepts an explicit tag, which can be re-pointed.
x SEC-POSTURE-63 pods '
  [.items[]?|select((.metadata.namespace//"")|sysns|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pn|(.spec.containers[]?,.spec.initContainers[]?)|{n:($pn+" / "+(.name//"?")+" "+(.image//"?")),d:((.image//"")|test("@sha256:[0-9a-f]{64}$"))}] as $c
  | [$c[]|select(.d)] as $p
  | {state:b(($p|length);($c|length)),
     detail:(if ($c|length)==0 then "no workload containers outside kube-* and amazon-*" else "\($p|length)/\($c|length) workload containers and init containers reference their image by @sha256: digest (the pod spec as written; a tag resolved at pull time does not count)" end),
     pass:[$p[]|.n], fail:[($c-$p)[]|.n]}'

echo "posture_extra.sh: 9 checks scored into $OUTF" >&2
exit 0
