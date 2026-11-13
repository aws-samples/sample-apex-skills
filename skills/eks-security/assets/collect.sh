#!/usr/bin/env bash
# eks-security collector: reads one EKS cluster once into a private work dir and builds
# inventory.json for match.py. Read-only: aws describe/list/get/batch-get calls and kubectl get
# (plus `kubectl auth can-i` in the preflight). It never runs anything inside a pod, never opens a
# tunnel to a pod and reads no credential objects.
#
# Usage:
#   collect.sh --cluster <name> --region <region> [--out <dir>] [--namespaces a,b]
#              [--skip-inspector] [--preflight-only]
#              [--context <kubectl context>] [--kubeconfig <file>] [--profile <aws profile>]
#              [--catalog <components.json>]
#
# A step that fails is recorded in meta.json "errors" and the matching inventory part is marked
# readable:false with a reason; the run goes on. Only an unreadable describe-cluster stops it.
# Exit: 0 collected (check meta.json errors), 2 usage or fatal error (one JSON line on stdout).
set -euo pipefail
umask 077
export AWS_PAGER="" AWS_DEFAULT_OUTPUT=json

fail() { # fail <code> <message>: one JSON line on stdout, message on stderr, exit 2
  printf 'collect.sh: %s\n' "$2" >&2
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg c "$1" --arg e "$2" '{ok:false,code:$c,error:$e}'
  else
    printf '{"ok":false,"code":"%s","error":"see stderr"}\n' "$1"
  fi
  exit 2
}
usage() { fail usage "usage: collect.sh --cluster NAME --region REGION [--out DIR] [--namespaces a,b] [--skip-inspector] [--preflight-only] [--context CTX] [--kubeconfig FILE] [--profile PROFILE] [--catalog FILE]"; }

CLUSTER=""; REGION=""; OUT=""; NAMESPACES=""; SKIP_INSPECTOR=0; PREFLIGHT_ONLY=0
KCTX=""; KCFG=""; CATALOG="$(cd -- "$(dirname -- "$0")" && pwd)/components.json"
while [ $# -gt 0 ]; do
  case "$1" in
    --cluster) [ $# -ge 2 ] || usage; CLUSTER="$2"; shift 2 ;;
    --region) [ $# -ge 2 ] || usage; REGION="$2"; shift 2 ;;
    --out) [ $# -ge 2 ] || usage; OUT="$2"; shift 2 ;;
    --namespaces) [ $# -ge 2 ] || usage; NAMESPACES="$2"; shift 2 ;;
    --skip-inspector) SKIP_INSPECTOR=1; shift ;;
    --preflight-only) PREFLIGHT_ONLY=1; shift ;;
    --context) [ $# -ge 2 ] || usage; KCTX="$2"; shift 2 ;;
    --kubeconfig) [ $# -ge 2 ] || usage; KCFG="$2"; shift 2 ;;
    --profile) [ $# -ge 2 ] || usage; export AWS_PROFILE="$2"; shift 2 ;;
    --catalog) [ $# -ge 2 ] || usage; CATALOG="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

for t in aws kubectl jq; do command -v "$t" >/dev/null 2>&1 || fail missing_tool "required tool not on PATH: $t"; done
printf '%s' "$CLUSTER" | grep -Eq '^[0-9A-Za-z][A-Za-z0-9_-]{0,99}$' || fail usage "--cluster is not a valid EKS cluster name"
printf '%s' "$REGION" | grep -Eq '^[a-z]{2}(-[a-z]+)+-[0-9]+$' || fail usage "--region is not a valid Region name"
NS_LIST=()
if [ -n "$NAMESPACES" ]; then
  NS_LIST=(kube-system)
  IFS=',' read -r -a _ns <<<"$NAMESPACES"
  for n in "${_ns[@]}"; do
    printf '%s' "$n" | grep -Eq '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$' || fail usage "--namespaces holds an invalid namespace name"
    [ "$n" = kube-system ] || NS_LIST+=("$n")
  done
fi
[ -z "$KCFG" ] || [ -r "$KCFG" ] || fail usage "--kubeconfig file is not readable"

TS="$(date -u +%Y%m%dT%H%MZ)"
[ -n "$OUT" ] || OUT="./eks-security-$CLUSTER-$TS"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac   # absolute, so no path can start with "-"
if [ -e "$OUT" ] || [ -L "$OUT" ]; then
  [ -d "$OUT" ] && [ ! -L "$OUT" ] && [ -z "$(ls -A -- "$OUT")" ] || fail out_exists "work dir exists and is not empty: $OUT (this script never writes over a previous run)"
fi
mkdir -p -- "$OUT" || fail out_dir "cannot make work dir $OUT"
chmod 700 -- "$OUT"
ERRS="$OUT/.errors.jsonl"; : >"$ERRS"
PF="$OUT/.preflight.jsonl"; : >"$PF"

KARGS=()
[ -z "$KCTX" ] || KARGS+=(--context "$KCTX")
[ -z "$KCFG" ] || KARGS+=(--kubeconfig "$KCFG")
kc() { kubectl ${KARGS[@]+"${KARGS[@]}"} "$@"; }

firstline() { grep -m1 -v '^[[:space:]]*$' "$1" 2>/dev/null | cut -c1-300 || true; }
classify() {
  case "$1" in
    *AccessDenied*|*UnauthorizedOperation*|*not\ authorized*|*explicit\ deny*|*Forbidden*|*forbidden*|*must\ be\ logged\ in*) echo denied ;;
    *ExpiredToken*|*InvalidClientTokenId*|*Unable\ to\ locate\ credentials*|*Token\ has\ expired*|*security\ token*|*getting\ credentials*) echo credentials ;;
    *ResourceNotFound*|*NotFound*|*not\ found*) echo not_found ;;
    *Throttl*|*Rate\ exceeded*|*TooManyRequests*) echo throttled ;;
    *) echo error ;;
  esac
}
rec_err() { jq -nc --arg s "$1" --arg c "$2" --arg m "$3" '{step:$s,code:$c,message:$m}' >>"$ERRS"; }
rec_pf() { jq -nc --arg p "$1" --arg v "$2" '{($p):$v}' >>"$PF"; }

# call <out> <step> <command...>: writes <out> only on success with valid JSON, else records the error.
call() {
  local out="$1" step="$2" n=0 e="" c=""; shift 2
  while :; do
    if "$@" >"$out.tmp" 2>"$out.err" && jq -e . "$out.tmp" >/dev/null 2>&1; then
      mv -f -- "$out.tmp" "$out"; rm -f -- "$out.err"; return 0
    fi
    e="$(firstline "$out.err")"; [ -n "$e" ] || e="no output or invalid JSON"
    c="$(classify "$e")"; n=$((n+1))
    case "$c" in denied|credentials|not_found) break ;; esac
    [ "$n" -lt 3 ] || break
    sleep $((n*2))
  done
  rm -f -- "$out.tmp" "$out.err"
  rec_err "$step" "$c" "$e"; return 1
}

# ---- preflight -------------------------------------------------------------------------------
probe_aws() { # probe_aws <label> <command...>
  local lbl="$1" e; shift
  if e="$("$@" 2>&1 >/dev/null)"; then rec_pf "$lbl" ok; return 0; fi
  case "$e" in *DryRunOperation*) rec_pf "$lbl" ok; return 0 ;; esac
  if [ "$(classify "$e")" = denied ]; then rec_pf "$lbl" denied; else rec_pf "$lbl" error; fi
  rec_err "preflight:$lbl" "$(classify "$e")" "$(printf '%s' "$e" | grep -m1 -v '^[[:space:]]*$' | cut -c1-300 || true)"
  return 1
}
probe_k8s() { # probe_k8s <resource> [namespace]
  local r="$1" ns="${2:-}" v scope=(--all-namespaces) lbl
  [ -z "$ns" ] || scope=(-n "$ns")
  case "$r" in nodes|namespaces|clusterrolebindings) scope=() ;; esac
  lbl="k8s:list $r${ns:+ -n $ns}"
  v="$(kc auth can-i list "$r" ${scope[@]+"${scope[@]}"} 2>&1 | tail -1 || true)"
  case "$v" in
    yes) rec_pf "$lbl" ok ;;
    no*) rec_pf "$lbl" denied ;;
    *) rec_pf "$lbl" error; rec_err "preflight:$lbl" "$(classify "$v")" "$(printf '%s' "$v" | cut -c1-300)" ;;
  esac
}
pf_state() { # pf_state <label> -> ok|denied|error|absent
  jq -rs --arg p "$1" 'map(select(has($p)))[0][$p] // "absent"' "$PF"
}

ACCOUNT=""
if probe_aws sts:GetCallerIdentity aws sts get-caller-identity --region "$REGION"; then
  ACCOUNT="$(aws sts get-caller-identity --region "$REGION" --query Account --output text 2>/dev/null || true)"
fi
if ! call "$OUT/cluster.json" describe-cluster aws eks describe-cluster --name "$CLUSTER" --region "$REGION"; then
  rec_pf eks:DescribeCluster "$(jq -rs 'last.code // "error"' "$ERRS")"
  _m="$(jq -rs 'last.message // ""' "$ERRS")"; rm -f -- "$ERRS" "$PF"
  fail cluster_unreadable "aws eks describe-cluster failed for $CLUSTER in $REGION: $_m"
fi
rec_pf eks:DescribeCluster ok
probe_aws eks:ListAddons aws eks list-addons --cluster-name "$CLUSTER" --region "$REGION" || true
probe_aws eks:ListNodegroups aws eks list-nodegroups --cluster-name "$CLUSTER" --region "$REGION" || true
probe_aws eks:ListInsights aws eks list-insights --cluster-name "$CLUSTER" --region "$REGION" || true
probe_aws ec2:DescribeInstances aws ec2 describe-instances --dry-run --max-results 5 --region "$REGION" || true
probe_aws ec2:DescribeImages aws ec2 describe-images --dry-run --owners self --region "$REGION" || true
probe_aws ecr:GetRegistryScanningConfiguration aws ecr get-registry-scanning-configuration --region "$REGION" || true
[ "$SKIP_INSPECTOR" -eq 1 ] || probe_aws inspector2:BatchGetAccountStatus aws inspector2 batch-get-account-status --region "$REGION" || true
[ "$SKIP_INSPECTOR" -eq 1 ] || probe_aws inspector2:ListFindings aws inspector2 list-findings --region "$REGION" --max-results 1 || true
probe_k8s nodes
for r in pods daemonsets deployments statefulsets; do
  if [ ${#NS_LIST[@]} -eq 0 ]; then probe_k8s "$r"; else for n in "${NS_LIST[@]}"; do probe_k8s "$r" "$n"; done; fi
done

AWS_V="$(aws --version 2>&1 | head -1 || true)"
KC_V="$(kubectl version --client -o json 2>/dev/null | jq -r '.clientVersion.gitVersion // ""' 2>/dev/null || true)"
JQ_V="$(jq --version 2>&1 || true)"
write_meta() {
  jq -n --arg cl "$CLUSTER" --arg rg "$REGION" --arg ac "$ACCOUNT" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg av "$AWS_V" --arg kv "$KC_V" --arg jv "$JQ_V" --slurpfile pf "$PF" --slurpfile er "$ERRS" \
    '{schema:"eks-security/inventory@1",cluster:$cl,region:$rg,account:$ac,collected_at:$at,
      tool_versions:{aws:$av,kubectl:$kv,jq:$jv},preflight:($pf|add // {}),errors:$er}' >"$OUT/meta.json"
}
if [ "$PREFLIGHT_ONLY" -eq 1 ]; then
  write_meta; rm -f -- "$OUT/cluster.json" "$ERRS" "$PF"
  jq -c '{ok:([.preflight|to_entries[]|select(.key|startswith("k8s:"))|.value=="ok"]|all),preflight_only:true,preflight:.preflight,errors:(.errors|length)}' "$OUT/meta.json"
  exit 0
fi

# ---- collection ------------------------------------------------------------------------------
K8S_VER="$(jq -r '.cluster.version // ""' "$OUT/cluster.json")"
ST_ADDONS=error; ST_NODES=error; ST_WL=error

# add-ons: list, then describe each, then the available versions for the installed names
if call "$OUT/.addon-list.json" list-addons aws eks list-addons --cluster-name "$CLUSTER" --region "$REGION"; then
  ST_ADDONS=ok; : >"$OUT/.addons.jsonl"; : >"$OUT/.addon-versions.jsonl"
  for a in $(jq -r '.addons[]? | select(test("^[a-z0-9][a-z0-9-]*$"))' "$OUT/.addon-list.json"); do
    if call "$OUT/.ad.json" "describe-addon:$a" aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$a" --region "$REGION"; then
      jq -c '.addon | {name:.addonName,version:.addonVersion,status:.status} + (if .configurationValues then {configurationValues} else {} end)' "$OUT/.ad.json" >>"$OUT/.addons.jsonl"
    else
      jq -nc --arg n "$a" --arg c "$(jq -rs 'last.code' "$ERRS")" '{name:$n,version:null,status:null,read_error:(if $c == "denied" or $c == "not_found" then $c else "unparsed" end)}' >>"$OUT/.addons.jsonl"
    fi
    if [ -n "$K8S_VER" ] && call "$OUT/.av.json" "describe-addon-versions:$a" aws eks describe-addon-versions --addon-name "$a" --kubernetes-version "$K8S_VER" --region "$REGION"; then
      jq -c '.addons[]?' "$OUT/.av.json" >>"$OUT/.addon-versions.jsonl"
    fi
  done
  jq -s . "$OUT/.addons.jsonl" >"$OUT/addons.json"
  jq -s '{addons:.}' "$OUT/.addon-versions.jsonl" >"$OUT/addon-versions.json"
elif [ "$(jq -rs 'last.code' "$ERRS")" = denied ]; then ST_ADDONS=denied; fi

# managed node groups
if call "$OUT/.ng-list.json" list-nodegroups aws eks list-nodegroups --cluster-name "$CLUSTER" --region "$REGION"; then
  : >"$OUT/.ng.jsonl"
  for g in $(jq -r '.nodegroups[]? | select(test("^[A-Za-z0-9][A-Za-z0-9_-]*$"))' "$OUT/.ng-list.json"); do
    if call "$OUT/.ng.json" "describe-nodegroup:$g" aws eks describe-nodegroup --cluster-name "$CLUSTER" --nodegroup-name "$g" --region "$REGION"; then
      jq -c '.nodegroup' "$OUT/.ng.json" >>"$OUT/.ng.jsonl"
    fi
  done
  jq -s . "$OUT/.ng.jsonl" >"$OUT/nodegroups.json"
fi

# nodes
if call "$OUT/nodes.json" kubectl-get-nodes kc get nodes -o json; then ST_NODES=ok
elif [ "$(jq -rs 'last.code' "$ERRS")" = denied ]; then ST_NODES=denied; fi

# workloads: all namespaces, or kube-system plus the named ones
if [ ${#NS_LIST[@]} -eq 0 ]; then
  if call "$OUT/workloads.json" kubectl-get-workloads kc get pods,daemonsets,deployments,statefulsets -A -o json; then ST_WL=ok
  elif [ "$(jq -rs 'last.code' "$ERRS")" = denied ]; then ST_WL=denied; fi
else
  : >"$OUT/.wl.jsonl"; ok_any=0
  for n in "${NS_LIST[@]}"; do
    if call "$OUT/.wl.json" "kubectl-get-workloads:$n" kc get pods,daemonsets,deployments,statefulsets -n "$n" -o json; then
      ok_any=1; jq -c '.items[]?' "$OUT/.wl.json" >>"$OUT/.wl.jsonl"
    fi
  done
  if [ "$ok_any" -eq 1 ]; then ST_WL=ok; jq -s '{apiVersion:"v1",kind:"List",items:.}' "$OUT/.wl.jsonl" >"$OUT/workloads.json"
  elif [ "$(jq -rs 'last.code' "$ERRS")" = denied ]; then ST_WL=denied; fi
fi

# EC2 instances behind the nodes, then their AMIs (filters, so a node gone mid-run is not an error)
if [ "$ST_NODES" = ok ]; then
  : >"$OUT/.inst.jsonl"
  while read -r ids; do
    [ -n "$ids" ] || continue
    if call "$OUT/.in.json" describe-instances aws ec2 describe-instances --region "$REGION" --filters "Name=instance-id,Values=$ids"; then
      jq -c '.Reservations[]?' "$OUT/.in.json" >>"$OUT/.inst.jsonl"
    fi
  done < <(jq -r '[.items[]?.spec.providerID // empty | capture("/(?<id>i-[0-9a-f]+)$").id] | unique | _nwise(100) | join(",")' "$OUT/nodes.json")
  # Auto Mode instances can be hidden from list and filter calls; a lookup by instance id still returns them
  # (EKS User Guide automode-learn-instances.html, "Managed resource visibility"). One id per call.
  seen="$(jq -r '.Instances[]?.InstanceId' "$OUT/.inst.jsonl")"
  while read -r id; do
    [ -n "$id" ] || continue
    if call "$OUT/.in.json" "describe-instances:$id" aws ec2 describe-instances --region "$REGION" --instance-ids "$id"; then
      jq -c '.Reservations[]?' "$OUT/.in.json" >>"$OUT/.inst.jsonl"
    fi
  done < <(jq -r --arg seen "$seen" '($seen | split("\n")) as $s | [.items[]?.spec.providerID // empty | capture("/(?<id>i-[0-9a-f]+)$").id] | unique | .[] | select(IN($s[]) | not)' "$OUT/nodes.json")
  jq -s '{Reservations:.}' "$OUT/.inst.jsonl" >"$OUT/instances.json"
  amis="$(jq -r '[.Reservations[].Instances[].ImageId // empty] | unique | join(",")' "$OUT/instances.json")"
  if [ -n "$amis" ]; then
    # --include-deprecated: by default a deprecated AMI (an old one) is left out of the response
    call "$OUT/images.json" describe-images aws ec2 describe-images --region "$REGION" --include-deprecated --filters "Name=image-id,Values=$amis" || true
  fi
fi

call "$OUT/ecr-scanning.json" get-registry-scanning-configuration aws ecr get-registry-scanning-configuration --region "$REGION" || true
call "$OUT/insights.json" list-insights aws eks list-insights --cluster-name "$CLUSTER" --region "$REGION" || true

# Inspector: findings only for this account's ECR images that this cluster's pods run
insp_skip() { jq -n --arg r "$1" '{skipped:$r}' >"$OUT/inspector-findings.json"; }
if [ "$SKIP_INSPECTOR" -eq 1 ]; then insp_skip "--skip-inspector given"
elif [ "$ST_WL" != ok ]; then insp_skip "workloads not readable, so the in-use images are not known"
elif [ -z "$ACCOUNT" ]; then insp_skip "account id not known (sts get-caller-identity failed)"
elif ! call "$OUT/.insp-status.json" inspector-status aws inspector2 batch-get-account-status --region "$REGION"; then
  insp_skip "inspector2 batch-get-account-status failed: $(jq -rs 'last.code' "$ERRS")"
else
  st="$(jq -r '.accounts[0].resourceState.ecr.status // "UNKNOWN"' "$OUT/.insp-status.json")"
  if [ "$st" != ENABLED ]; then insp_skip "Amazon Inspector ECR scanning is not enabled in $REGION (status $st)"
  else
    reg="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/"
    jq -c --arg reg "$reg" '
      [.items[]? | select(.kind=="Pod") | ((.status.containerStatuses // []) + (.status.initContainerStatuses // []))[]
        | select((.image // "") | startswith($reg))
        | {repo: (.image | ltrimstr($reg) | sub("[@:].*$";"")),
           digest: ((.imageID // "") | (capture("(?<d>sha256:[0-9a-f]{64})").d) // null)}] as $c
      | {digests: ([$c[] | .digest // empty] | unique), repos: ([$c[] | select(.digest == null) | .repo] | unique)}' \
      "$OUT/workloads.json" >"$OUT/.insp-targets.json"
    : >"$OUT/.insp.jsonl"; insp_ok=1
    while read -r f; do
      [ -n "$f" ] || continue
      if call "$OUT/.if.json" inspector-list-findings aws inspector2 list-findings --region "$REGION" --filter-criteria "$f"; then
        jq -c '.findings[]?' "$OUT/.if.json" >>"$OUT/.insp.jsonl"
      else insp_ok=0; fi
    done < <(jq -c '
      def eq: {comparison:"EQUALS",value:.};
      ([.digests | _nwise(10) | select(length>0) | {ecrImageHash: map(eq)}]
       + [.repos | _nwise(10) | select(length>0) | {ecrImageRepositoryName: map(eq)}])[]
      | . + {findingStatus:[("ACTIVE"|eq)]}' "$OUT/.insp-targets.json")
    jq -s --argjson ok "$insp_ok" --slurpfile t "$OUT/.insp-targets.json" \
      '{findings: (unique_by(.findingArn)), complete: ($ok==1), queried: $t[0]}' "$OUT/.insp.jsonl" >"$OUT/inspector-findings.json"
  fi
fi

# ---- inventory.json --------------------------------------------------------------------------
NULLF="$OUT/.null.json"; printf 'null\n' >"$NULLF"
pick() { if [ -s "$1" ]; then printf '%s' "$1"; else printf '%s' "$NULLF"; fi; }
CAT="$NULLF"
if [ -r "$CATALOG" ] && jq -e '.components | type == "array"' "$CATALOG" >/dev/null 2>&1; then CAT="$CATALOG"
else rec_err catalog error "components.json not readable or has no components list: $CATALOG"; fi

if jq -n \
  --arg cl "$CLUSTER" --arg rg "$REGION" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg st_addons "$ST_ADDONS" --arg st_nodes "$ST_NODES" --arg st_wl "$ST_WL" --arg reg "${reg:-}" \
  --slurpfile c "$(pick "$OUT/cluster.json")" --slurpfile ad "$(pick "$OUT/addons.json")" \
  --slurpfile nd "$(pick "$OUT/nodes.json")" --slurpfile wl "$(pick "$OUT/workloads.json")" \
  --slurpfile ins "$(pick "$OUT/instances.json")" --slurpfile img "$(pick "$OUT/images.json")" --slurpfile insp "$(pick "$OUT/inspector-findings.json")" \
  --slurpfile cat "$CAT" '
  def tag_of: sub("@sha256:.*$";"") | (split("/") | last) as $l | if ($l | test(":")) then ($l | split(":") | last) else null end;
  def dig: if . == null then null else (capture("(?<d>sha256:[0-9a-f]{64})").d // null) end;
  ($c[0].cluster // {}) as $cj
  | (($cj.computeConfig.enabled // false) == true) as $auto
  | ($cat[0].components // []) as $catc
  | ([$catc[] | {key: .id, value: .}] | from_entries) as $catm
  | ([$wl[0].items[]? | select(.kind == "Pod")]) as $pods
  | ([$wl[0].items[]? | select(.kind == "DaemonSet" or .kind == "Deployment" or .kind == "StatefulSet")]) as $ctrl
  | ([$ins[0].Reservations[]?.Instances[]? | {key: .InstanceId, value: .ImageId}] | from_entries) as $amis
  | ([$img[0].Images[]? | {key: .ImageId, value: .CreationDate}] | from_entries) as $amidates
  # images in use, one entry per image reference and digest
  | ([$pods[] | . as $p
      | ((.status.containerStatuses // []) + (.status.initContainerStatuses // [])) as $sts
      | ((.spec.containers // []) + (.spec.initContainers // []))[]
      | . as $ct
      | {image: .image,
         digest: ((if (.image | test("@sha256:")) then .image else ([$sts[] | select(.name == $ct.name)][0].imageID) end) | dig),
         workload: ($p.metadata.namespace + "/" + (($p.metadata.ownerReferences // [])[0] // {kind:"Pod",name:$p.metadata.name}
                     | (.kind | ascii_downcase) + "/" + .name))}]
     | group_by([.image, .digest])
     | map({image: .[0].image, digest: .[0].digest, pinned_by_digest: (.[0].image | test("@sha256:")),
            workloads: (map(.workload) | unique)})) as $imgs
  | (if ($insp[0] | type) == "object" and ($insp[0] | has("findings")) then $insp[0].findings else null end) as $ifs
  | ($imgs | map(. as $im
      | if $ifs == null then . + {inspector: {skipped: ($insp[0].skipped // "not collected")}}
        elif ($im.image // "") | startswith($reg) | not then
          . + {inspector: {skipped: ("image host is not " + ($reg | rtrimstr("/")) + " (another account, Region or registry host)")}}
        elif ($insp[0].complete == true) | not then
          . + {inspector: {skipped: "inspector2 list-findings failed for some targets; see meta.json errors"}}
        elif if $im.digest != null then ($insp[0].queried.digests // []) | any(.[]; . == $im.digest) | not
             else ($insp[0].queried.repos // []) | any(.[]; . == ($im.image | ltrimstr($reg) | sub("[@:].*$";""))) | not end then
          . + {inspector: {skipped: "image not queried: no running container reports it (pod has no containerStatuses)"}}
        else ([$ifs[] | select(any(.resources[]?.details.awsEcrContainerImage; . as $r |
                 (($im.digest != null) and .imageHash == $im.digest)
                 or (($im.digest == null) and ($im.image | sub("[@:][^/]*$";"") | endswith("/" + $r.repositoryName))
                     and (($im.image | tag_of) as $t | $t != null and ((.imageTags // []) | index($t)) != null))))]
              | map({id: (.packageVulnerabilityDetails.vulnerabilityId // .title), severity: .severity,
                     package: (.packageVulnerabilityDetails.vulnerablePackages[0].name // ""),
                     installed: (.packageVulnerabilityDetails.vulnerablePackages[0].version // ""),
                     fixed: (.packageVulnerabilityDetails.vulnerablePackages[0].fixedInVersion // "")})) as $f
             | . + {inspector: ({critical: ([$f[] | select(.severity == "CRITICAL")] | length),
                                high: ([$f[] | select(.severity == "HIGH")] | length), findings: $f}
                    + (if ($f|length)==0 then {note:"0 ACTIVE findings returned; whether Inspector scanned this image was not read (coverage is not collected)"} else {} end))}
        end)) as $images
  # control plane
  | [{id: "k8s:control-plane", kind: "control-plane", name: "kubernetes", version: $cj.version,
      platform_version: $cj.platformVersion, managed_by: "aws", where: ["cluster"], readable: ($cj.version != null),
      reason: (if $cj.version == null then "unparsed" else null end)}] as $cp
  # one component per catalog read spec, from the controllers in workloads.json
  | def img_read($e; $r; $id):
      [$ctrl[] | select(($r.namespace == null or .metadata.namespace == $r.namespace)
                        and ($r.workload == null or ((.kind | ascii_downcase) + "/" + .metadata.name) == $r.workload))
       | . as $w | ((.spec.template.spec.containers // []) + (.spec.template.spec.initContainers // []))[]
       | select($r.container == null or .name == $r.container)
       | (.image | sub("@sha256:.*$";"") | sub(":[^/:]*$";"")) as $repo
       | select($r.image_repos == null or any($r.image_repos[]; . as $s | $repo == $s or ($repo | endswith("/" + $s))))
       | {ns: $w.metadata.namespace, wl: (($w.kind | ascii_downcase) + "/" + $w.metadata.name), image: .image}]
      | to_entries[] | .key as $i | .value as $m
      | ($m.image | tag_of) as $tag
      | ($imgs | map(select(.image == $m.image and .digest != null))[0].digest // ($m.image | dig)) as $d
      | {id: (if $i == 0 then $id else ($id + "@" + $m.ns + "/" + $m.wl) end), kind: "container-image",
         name: ($r.container // ($m.image | sub("[@:][^/]*$";"") | split("/") | last)), image: $m.image,
         version: (if $tag == null or $tag == "latest" then null else $tag end), digest: $d,
         namespace: $m.ns, workload: $m.wl, addon: ($r.addon // null),
         managed_by: "customer", where: [$m.ns + "/" + $m.wl],
         readable: ($tag != null and $tag != "latest"),
         reason: (if $tag == "latest" then "tag_latest" elif $tag == null then (if ($m.image | test("@sha256:")) then "digest_only" else "unparsed" end) else null end)};
    def unread($e; $kind; $why): {id: $e.id, kind: $kind, name: ($e.read.name // $e.read.container // $e.id), version: null,
      managed_by: "customer", where: [], readable: false, reason: (if $why == "denied" then "denied" else "unparsed" end)};
    def has_img_read($r): $r != null and $r.kind == "container-image" and (($r.workload // $r.container // $r.image_repos) != null);
  # EKS add-ons: installed add-on, else its self-managed fallback read, else unreadable when add-ons could not be listed
    ([$ad[0][]? | {id: ("addon:" + .name), kind: "eks-addon", name: .name, version: .version, managed_by: "customer",
                   where: ["cluster"], readable: (.version != null), reason: (if .version == null then (.read_error // "unparsed") else null end)}]) as $installed
  | ([$installed[] | .name]) as $inames
  | ([$catc[] | . as $e | select($e.read.kind == "eks-addon" and (($inames | index($e.read.name)) | not))
      | if $st_wl == "ok" and has_img_read($e.read.fallback) then
          ([img_read($e; $e.read.fallback; $e.id)] | if length > 0 then .[] elif $st_addons != "ok" then unread($e; "eks-addon"; $st_addons) else empty end)
        elif $st_addons != "ok" then unread($e; "eks-addon"; $st_addons)
        else empty end]) as $fallbacks
  | ($installed + $fallbacks) as $addons
  # self-managed component images named by the catalog
  | ([$catc[] | select(has_img_read(.read)) | . as $e
      | if $st_wl == "ok" then img_read($e; $e.read; $e.id) else unread($e; "container-image"; $st_wl) end]) as $selfm
  # node OS groups
  | (if $st_nodes != "ok" then
       [{id: "node-os:unread", kind: "node-os", os_image: null, kernel: null, kubelet: null, runtime: null, ami: null, ami_created: null,
         nodes: [], node_created: {}, oldest_node_created: null, managed_by: "customer", where: [], readable: false,
         reason: (if $st_nodes == "denied" then "denied" else "unparsed" end)}]
     else
       [$nd[0].items[]? | (.metadata.labels // {}) as $lb
        | (($lb["eks.amazonaws.com/compute-type"] // "") == "auto") as $isauto
        | {group: (if $isauto then ($lb["karpenter.sh/nodepool"] // "auto-mode")
                   elif $lb["eks.amazonaws.com/nodegroup"] then $lb["eks.amazonaws.com/nodegroup"] else "self-managed" end),
           auto: $isauto, name: .metadata.name, created: .metadata.creationTimestamp,
           os: .status.nodeInfo.osImage, kernel: .status.nodeInfo.kernelVersion, kubelet: .status.nodeInfo.kubeletVersion,
           runtime: .status.nodeInfo.containerRuntimeVersion,
           ami: ($amis[((.spec.providerID // "") | (capture("/(?<id>i-[0-9a-f]+)$").id // ""))] // null)}]
       | group_by(.group) | map(. as $g | group_by([.os, .kernel, .kubelet, .runtime, .ami]) | to_entries
         | map(.key as $i | .value as $v
           | {id: ("node-os:" + $g[0].group + (if $i == 0 then "" else "/" + ($i + 1 | tostring) end)), kind: "node-os",
              os_image: $v[0].os, kernel: $v[0].kernel, kubelet: $v[0].kubelet, runtime: $v[0].runtime, ami: $v[0].ami,
              ami_created: (if $v[0].ami then $amidates[$v[0].ami] else null end),
              nodes: ($v | map(.name)), node_created: ($v | map({key: .name, value: .created}) | from_entries),
              oldest_node_created: ($v | map(.created) | min),
              managed_by: (if $v[0].auto then "aws-auto-mode" else "customer" end), where: [$g[0].group],
              readable: ($v[0].os != null), reason: (if $v[0].os == null then "unparsed" else null end)}))
       | add // []
     end) as $nodeos
  # Auto Mode: catalog components AWS manages on Auto Mode nodes
  | (if $auto then [$catc[] | select(.auto_mode_managed == true and (.read.kind == "eks-addon" or .read.kind == "container-image"))
       | {id: (.id + "@auto-mode"), kind: (.read.kind // "aws-managed"), name: (.read.name // .read.container // .id),
          version: null, managed_by: "aws-auto-mode", where: ["auto-mode-nodes"], readable: true, reason: null}]
     else [] end) as $autoc
  | ($cp + $addons + $selfm + $nodeos + $autoc) as $comps
  | {schema: "eks-security/inventory@1", cluster: $cl, region: $rg, collected_at: $at,
     control_plane: {version: $cj.version, platform_version: $cj.platformVersion, auto_mode: $auto,
                     endpoint_public: ($cj.resourcesVpcConfig.endpointPublicAccess // null),
                     public_cidrs: ($cj.resourcesVpcConfig.publicAccessCidrs // [])},
     components: $comps, images: $images,
     coverage: {components_total: ($comps | length), components_readable: ([$comps[] | select(.readable)] | length)}}
  ' >"$OUT/inventory.json.tmp" 2>"$OUT/inventory.err"; then mv -f -- "$OUT/inventory.json.tmp" "$OUT/inventory.json"
else rec_err build-inventory error "$(firstline "$OUT/inventory.err")"; fi
rm -f -- "$OUT/inventory.err" "$OUT/inventory.json.tmp"

write_meta
rm -f -- "$OUT"/.[a-z]*.json "$OUT"/.[a-z]*.jsonl
chmod 600 -- "$OUT"/*.json 2>/dev/null || true
[ -s "$OUT/inventory.json" ] || fail inventory_failed "inventory.json was not built; see meta.json errors in $OUT"
jq -c --arg d "$OUT" '{ok:true,workdir:$d,errors:(.errors|length),preflight_not_ok:([.preflight|to_entries[]|select(.value!="ok")|.key])}' "$OUT/meta.json"
