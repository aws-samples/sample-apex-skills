#!/usr/bin/env bash
# Adapted from skills/eks-well-architected-review/assets/collect.sh at commit 7965ae3 (security pillar only). Keep in step by hand.
#
# Security posture collector. Collects, once, every file the posture scorers read into
# <workdir>/posture/ (0700, files 0600), then stops. Nothing here judges the data: posture_score.sh
# (the Well-Architected security pillar questions) and posture_extra.sh (the containment checks that
# pillar lacks) read these files, and posture_reduce.sh turns their tokens into <workdir>/posture.json.
#
# Usage:
#   posture_collect.sh --cluster <name> --region <region> --context <kubectl-context> \
#       [--work <dir, default ./eks-security-<cluster>-<UTC yyyymmddThhmmZ>>] [--profile <aws-profile>] \
#       [--kubeconfig <file>] [--preflight-only]
#
# READ-ONLY. AWS calls are describe-*, list-* and get-* reads (EC2 probes use --dry-run). Kubernetes
# calls are `kubectl get` and `kubectl auth can-i` only. Two named ConfigMaps are read
# (kube-system/aws-auth and kube-system/amazon-vpc-cni); no other ConfigMap and no credential object
# is ever read. The collected workload JSON still carries container env values and arguments, so treat
# the work dir as sensitive: keep it out of version control and remove it after the review.
#
# What differs from the Well-Architected collector, on purpose:
#  - only the files the security questions read, plus the ones the containment checks need
#    (guardduty.json, ecr-scanning.json, accessentries.json; instances.json is shared);
#  - a denied preflight probe does NOT abort the run. The matching file is not collected, the denial
#    is recorded in meta.json, and every check that needs that file reports `unknown`, which the
#    reducer's coverage gate counts. Only a failed eks:DescribeCluster or an unreachable Kubernetes
#    API stops the run (exit 2), because then nothing can be judged.
#
# Exit codes: 0 collected (some files may be missing, see meta.json errors); 2 usage or a refusal
# (one JSON line on stdout: {"ok":false,"code":"...","error":"..."}).
#
# IAM actions this script calls (exactly these): sts:GetCallerIdentity, eks:DescribeCluster,
# eks:ListAddons, eks:DescribeAddon, eks:ListPodIdentityAssociations, eks:ListAccessEntries,
# eks:ListAssociatedAccessPolicies, iam:ListOpenIDConnectProviders,
# ec2:DescribeInstances, ec2:DescribeVolumes, ec2:DescribeSecurityGroups, ecr:DescribeRepositories,
# ecr:GetRegistryScanningConfiguration, guardduty:ListDetectors, guardduty:GetDetector.
set -uo pipefail
umask 077
export AWS_PAGER=""
export AWS_DEFAULT_OUTPUT=json

die() {  # die <code> <message>: one JSON line on stdout, the message on stderr, exit 2
  printf 'posture_collect.sh: %s\n' "$2" >&2
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg c "$1" --arg e "$2" '{ok:false,code:$c,error:$e}'
  else
    printf '{"ok":false,"code":"%s","error":"see stderr"}\n' "$1"
  fi
  exit 2
}
usage() { die usage "usage: posture_collect.sh --cluster NAME --region REGION --context KUBECTL_CONTEXT [--work DIR] [--profile AWS_PROFILE] [--kubeconfig FILE] [--preflight-only]"; }

CLUSTER="${CLUSTER-}"; REGION="${REGION-}"; KCTX="${KCTX-}"; WORK="${WORK-}"; KCFG=""; PF_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --cluster) [ $# -ge 2 ] || usage; CLUSTER="$2"; shift 2 ;;
    --region)  [ $# -ge 2 ] || usage; REGION="$2";  shift 2 ;;
    --context) [ $# -ge 2 ] || usage; KCTX="$2";    shift 2 ;;
    --work)    [ $# -ge 2 ] || usage; WORK="$2";    shift 2 ;;
    --profile) [ $# -ge 2 ] || usage; export AWS_PROFILE="$2"
               # A profile must win over static keys in the environment, which the CLI would otherwise prefer.
               for _v in $(env | sed -nE 's/^(AWS_[A-Z_]*(ACCESS_KEY|ACCESS_KEY_ID|SESSION_TOKEN|SECURITY_TOKEN|ROLE_ARN|WEB_IDENTITY_TOKEN_FILE))=.*/\1/p'); do unset "$_v"; done
               shift 2 ;;
    --kubeconfig) [ $# -ge 2 ] || usage; KCFG="$2"; shift 2 ;;
    --preflight-only) PF_ONLY=1; shift ;;
    -h|--help) usage ;;
    *) die usage "unknown argument '$1'" ;;
  esac
done

# ── REQUIRED TOOLS, checked before anything else (a missing grep must not read as a bad cluster name) ──
_missing=""
for _t in aws kubectl jq grep sed awk tr cut sort date mkdir chmod mv cat base64 timeout sha256sum; do
  command -v "$_t" >/dev/null 2>&1 || _missing="$_missing $_t"
done
[ -z "$_missing" ] || die missing_tool "required tool(s) not found on PATH:$_missing. Nothing has been written."
jq -n '1 | IN(1)' >/dev/null 2>&1 || die jq_too_old "jq 1.6 or later is required (IN/1 is used by the scorers)."
unset _missing _t

# ── ARGUMENT VALIDATION, before the work dir is derived or touched ──
case "$CLUSTER" in *[[:cntrl:]]*) die bad_cluster "CLUSTER contains a control character." ;; esac
printf '%s' "$CLUSTER" | grep -Eq '^[0-9A-Za-z][A-Za-z0-9_-]{0,99}$' \
  || die bad_cluster "pass --cluster: an EKS cluster name (alphanumeric first, then letters, digits, hyphens, underscores; at most 100)."
printf '%s' "$REGION" | grep -Eq '^[a-z0-9-]{1,20}$' || die bad_region "pass --region: an AWS Region code such as us-west-2."
[ -n "$KCTX" ] || die bad_context "pass --context: the kubectl context for this cluster (do not rely on current-context)."
case "$KCTX" in *[[:cntrl:]]*) die bad_context "--context contains a control character." ;; esac
if [ -n "$KCFG" ]; then
  case "$KCFG" in *[[:cntrl:]]*) die bad_kubeconfig "--kubeconfig contains a control character." ;; esac
  [ -f "$KCFG" ] && [ -r "$KCFG" ] || die bad_kubeconfig "--kubeconfig '$KCFG' is not a readable file."
fi

# ── WORK DIRECTORY: <workdir> may already exist (the CVE collector shares it); posture/ must not ──
[ -n "$WORK" ] || WORK="$(pwd)/eks-security-$CLUSTER-$(date -u +%Y%m%dT%H%MZ)"
case "$WORK" in *[[:cntrl:]]*) die bad_work "--work contains a control character." ;; esac
case "$WORK" in /|"$HOME"|"$HOME/") die bad_work "refusing --work '$WORK': it is the filesystem root or your home directory." ;; esac
[ -L "$WORK" ] && die bad_work "refusing --work '$WORK': it is a symbolic link."
if [ -e "$WORK" ] && [ ! -d "$WORK" ]; then die bad_work "refusing --work '$WORK': it exists and is not a directory."; fi
if [ ! -d "$WORK" ]; then mkdir -p -- "$WORK" && chmod 700 -- "$WORK" || die bad_work "could not make '$WORK'."; fi
P="$WORK/posture"
# mkdir (not mkdir -p) fails on ANY existing entry at that name, a symlink included, so nothing planted is
# written through and an earlier collection is never overlaid: a stale file could otherwise satisfy a
# call that fails this time.
mkdir -m 700 -- "$P" 2>/dev/null || die work_in_use "refusing: '$P' already exists. This script never removes anything; pass --work with a new path."
KCACHE="$P/.kube-cache"

kctl() { kubectl --context "$KCTX" ${KCFG:+--kubeconfig "$KCFG"} --cache-dir "$KCACHE" "$@"; }
firstline() { grep -m1 -v '^[[:space:]]*$' "$1" 2>/dev/null | cut -c1-200; }

# ── PERMISSION PREFLIGHT: one small real read per action used. ok | denied | error ──
# Classification copied from the WAR collector: an authorization failure is `denied`, an expired or
# missing credential stops the run (no data can be trusted), anything else is `error` and the real call
# is still attempted.
PF_JSON='{}'
pf_set() { PF_JSON=$(printf '%s' "$PF_JSON" | jq -c --arg k "$1" --arg v "$2" '.[$k]=$v'); }
pf_classify() {
  case "$1" in
    *ExpiredToken*|*InvalidClientTokenId*|*AuthFailure*|*security\ token*|*SSO\ Token*|*sso\ session*|*Token\ has\ expired*|*NoCredentials*|*Unable\ to\ locate\ credentials*|*getting\ credentials*)
      echo expired ;;
    *UnauthorizedOperation*|*AccessDenied*|*not\ authorized*|*explicit\ deny*) echo denied ;;
    *DryRunOperation*|*ResourceNotFoundException*|*InvalidParameterException*) echo ok ;;
    *) echo error ;;
  esac
}
pf_aws() {  # pf_aws <action> <aws args...>
  local a="$1" e v; shift
  if e="$(timeout 30 aws "$@" --region "$REGION" 2>&1 >/dev/null)"; then v=ok; else v=$(pf_classify "$e"); fi
  [ "$v" = expired ] && die credentials_expired "AWS credentials are missing or expired (probe $a: $(printf '%s' "$e" | head -1 | cut -c1-120))."
  pf_set "$a" "$v"
}
pf_k8s() {  # pf_k8s <label> <verb> <resource> [args...]
  local l="$1" v; shift
  v="$(timeout 30 kubectl auth can-i "$@" --context "$KCTX" ${KCFG:+--kubeconfig "$KCFG"} --cache-dir "$KCACHE" 2>/dev/null | tail -1)"
  case "$v" in yes) pf_set "$l" ok ;; no) pf_set "$l" denied ;; *) pf_set "$l" error ;; esac
}

ACCOUNT=""
if _id="$(timeout 30 aws sts get-caller-identity --region "$REGION" 2>&1)"; then
  pf_set "sts:GetCallerIdentity" ok; ACCOUNT=$(printf '%s' "$_id" | jq -r '.Account // ""' 2>/dev/null)
else
  [ "$(pf_classify "$_id")" = expired ] && die credentials_expired "AWS credentials are missing or expired."
  pf_set "sts:GetCallerIdentity" "$(pf_classify "$_id")"
fi
pf_aws "eks:DescribeCluster"              eks describe-cluster --name "$CLUSTER"
pf_aws "eks:ListAddons"                   eks list-addons --cluster-name "$CLUSTER"
pf_aws "eks:ListPodIdentityAssociations"  eks list-pod-identity-associations --cluster-name "$CLUSTER"
pf_aws "eks:ListAccessEntries"            eks list-access-entries --cluster-name "$CLUSTER"
pf_aws "iam:ListOpenIDConnectProviders"   iam list-open-id-connect-providers
pf_aws "ecr:DescribeRepositories"         ecr describe-repositories --max-items 1
pf_aws "ecr:GetRegistryScanningConfiguration" ecr get-registry-scanning-configuration
pf_aws "guardduty:ListDetectors"          guardduty list-detectors
for _op in describe-instances describe-volumes describe-security-groups; do
  _act="ec2:$(printf '%s' "$_op" | awk -F- '{for(i=1;i<=NF;i++) printf toupper(substr($i,1,1)) substr($i,2)}')"
  _e="$(timeout 30 aws ec2 "$_op" --dry-run --region "$REGION" 2>&1)"; _v=$(pf_classify "$_e")
  [ "$_v" = expired ] && die credentials_expired "AWS credentials are missing or expired."
  pf_set "$_act" "$_v"
done
# The two follow-on reads need an object to read; probe them only when the list names one.
_ad=$(timeout 30 aws eks list-addons --cluster-name "$CLUSTER" --region "$REGION" --query 'addons[0]' 2>/dev/null | jq -r '. // empty' 2>/dev/null)
[ -n "$_ad" ] && pf_aws "eks:DescribeAddon" eks describe-addon --cluster-name "$CLUSTER" --addon-name "$_ad"
_dt=$(timeout 30 aws guardduty list-detectors --region "$REGION" 2>/dev/null | jq -r '.DetectorIds[0] // empty' 2>/dev/null)
[ -n "$_dt" ] && pf_aws "guardduty:GetDetector" guardduty get-detector --detector-id "$_dt"
_pa=$(timeout 30 aws eks list-access-entries --cluster-name "$CLUSTER" --region "$REGION" 2>/dev/null | jq -r '.accessEntries[0] // empty' 2>/dev/null)
[ -n "$_pa" ] && pf_aws "eks:ListAssociatedAccessPolicies" eks list-associated-access-policies --cluster-name "$CLUSTER" --principal-arn "$_pa"
unset _op _act _e _v _ad _dt _id _pa

for _r in nodes namespaces persistentvolumes storageclasses clusterroles clusterrolebindings \
          validatingwebhookconfigurations mutatingwebhookconfigurations; do
  pf_k8s "kubernetes: list $_r" list "$_r"
done
for _r in pods deployments daemonsets ingresses networkpolicies serviceaccounts rolebindings; do
  pf_k8s "kubernetes: list $_r --all-namespaces" list "$_r" --all-namespaces
done
pf_k8s "kubernetes: get configmap/aws-auth -n kube-system" get configmap/aws-auth -n kube-system
pf_k8s "kubernetes: get configmap/amazon-vpc-cni -n kube-system" get configmap/amazon-vpc-cni -n kube-system
unset _r

pfv() { printf '%s' "$PF_JSON" | jq -r --arg k "$1" '.[$k] // "unprobed"'; }
[ "$(pfv eks:DescribeCluster)" = ok ] || die describe_cluster_failed "eks:DescribeCluster did not succeed ($(pfv eks:DescribeCluster)); nothing can be judged without it."
[ "$(pfv 'kubernetes: list namespaces')" = ok ] \
  || die kubernetes_unreachable "kubectl auth can-i list namespaces did not answer yes on context '$KCTX': RBAC does not grant this identity list namespaces (see read-only-access.md), the API endpoint is unreachable from here, the context names another cluster, or its token has expired."

ERRORS='[]'
err() { ERRORS=$(printf '%s' "$ERRORS" | jq -c --arg s "$1" --arg c "$2" --arg m "$3" '.+[{step:$s,code:$c,message:$m}]'); }
write_meta() {
  local files
  files=$(cd "$P" && for f in *.json; do [ -f "$f" ] && [ "$f" != meta.json ] && printf '%s %s\n' "$f" "$(sha256sum < "$f" | cut -d' ' -f1)"; done | jq -Rs 'split("\n")|map(select(length>0)|split(" ")|{key:.[0],value:.[1]})|from_entries')
  [ -n "$files" ] || files='{}'
  jq -n --arg cl "$CLUSTER" --arg rg "$REGION" --arg ac "$ACCOUNT" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     --arg av "$(aws --version 2>&1 | head -1)" --arg kv "$(kubectl version --client 2>/dev/null | head -1)" --arg jv "$(jq --version 2>&1)" \
     --argjson pf "$PF_JSON" --argjson er "$ERRORS" --argjson fs "$files" --argjson po "$PF_ONLY" \
     '{schema:"eks-security/posture-meta@1",cluster:$cl,region:$rg,account:$ac,collected_at:$at,
       preflight_only:($po==1),tool_versions:{aws:$av,kubectl:$kv,jq:$jv},preflight:$pf,errors:$er,files:$fs}' \
     > "$P/meta.json.tmp" && mv "$P/meta.json.tmp" "$P/meta.json"
}
if [ "$PF_ONLY" -eq 1 ]; then write_meta; jq -c '{ok:true,preflight:.preflight}' "$P/meta.json"; exit 0; fi

# ── RETRYING READERS: write only on success, so a failure leaves no plausible-looking empty file ──
awsjson() {  # awsjson <name> <action> -- <aws args...>
  local name="$1" act="$2" out="$P/$1.json" tmp="$P/.$1.json.tmp" n=0; shift 3
  if [ "$(pfv "$act")" = denied ]; then err "$name" denied "$act was denied in the preflight; $name.json not collected"; return 1; fi
  while :; do
    if timeout 120 aws "$@" --region "$REGION" >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then mv "$tmp" "$out"; return 0; fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then err "$name" error "$act failed 3 times: $(firstline "$tmp.err")"; return 1; fi
    sleep $((n*2))
  done
}
kjson() {  # kjson <name> <probe label|-> <kubectl get args...>
  local name="$1" lbl="$2" out="$P/$1.json" tmp="$P/.$1.json.tmp" n=0; shift 2
  if [ "$lbl" != - ] && [ "$(pfv "$lbl")" = denied ]; then err "$name" denied "$lbl was denied in the preflight; $name.json not collected"; return 1; fi
  while :; do
    if timeout 120 kubectl --context "$KCTX" ${KCFG:+--kubeconfig "$KCFG"} --cache-dir "$KCACHE" get "$@" -o json >"$tmp" 2>"$tmp.err" \
       && jq -e . "$tmp" >/dev/null 2>&1; then mv "$tmp" "$out"; return 0; fi
    if grep -qiE "the server doesn't have a resource type|could not find (the )?requested resource|Unknown resource|NotFound" "$tmp.err" 2>/dev/null; then
      [ "${KJ_OPTIONAL:-0}" = 1 ] || err "$name" not_found "kubectl get $* reports the resource type or object is absent"
      return 2   # genuinely absent; kjson_optional writes the empty document
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then err "$name" error "kubectl get $* failed 3 times: $(firstline "$tmp.err")"; return 1; fi
    sleep $((n*2))
  done
}
kjson_optional() {  # absent CRD or object -> the empty document is the correct answer
  local name="$1" empty="$2"; shift 2
  KJ_OPTIONAL=1 kjson "$name" "$@"; local rc=$?
  [ "$rc" -eq 2 ] && printf '%s\n' "$empty" > "$P/$name.json"
  return 0
}

# ── AWS SIDE ──
awsjson cluster eks:DescribeCluster -- eks describe-cluster --name "$CLUSTER" || die describe_cluster_failed "eks describe-cluster failed after the preflight passed."
jq -e '(.cluster.connectorConfig // null) == null' "$P/cluster.json" >/dev/null 2>&1 \
  || die connector_cluster "'$CLUSTER' is an EKS Connector registration, not an EKS cluster; its configuration is not readable here."

# Identity cross-check (WAR's): the kubectl context must point at THIS cluster, else every Kubernetes
# file describes another cluster under this cluster's name. Endpoint, then CA data, must match.
K_EP=$(kctl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)
A_EP=$(jq -r '.cluster.endpoint // empty' "$P/cluster.json")
[ -n "$K_EP" ] && [ "${K_EP%/}" = "${A_EP%/}" ] \
  || die context_mismatch "context '$KCTX' points at '${K_EP:-nothing}', but cluster '$CLUSTER' reports endpoint '${A_EP:-none}'. Pass the context for this cluster."
K_CA=$(kctl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null | tr -d '\n\r ')
A_CA=$(jq -r '.cluster.certificateAuthority.data // empty' "$P/cluster.json" | tr -d '\n\r ')
if [ -n "$K_CA" ] && [ -n "$A_CA" ] && [ "$K_CA" != "$A_CA" ]; then
  _kd=$(printf '%s' "$K_CA" | base64 -d 2>/dev/null | tr -d '\n\r '); _ad=$(printf '%s' "$A_CA" | base64 -d 2>/dev/null | tr -d '\n\r ')
  # A CA rotation's dual-trust bundle holds the cluster's CA among others: accept containment.
  [ -n "$_ad" ] || die context_mismatch "the cluster CA in cluster.json could not be decoded."
  case "$_kd" in *"$_ad"*) : ;; *) die context_mismatch "the CA in context '$KCTX' does not match cluster '$CLUSTER'." ;; esac
  unset _kd _ad
fi
VPC=$(jq -r '.cluster.resourcesVpcConfig.vpcId // empty' "$P/cluster.json")

if awsjson addons eks:ListAddons -- eks list-addons --cluster-name "$CLUSTER"; then
  jq '. + {addonDetails: []}' "$P/addons.json" > "$P/.addons.m" && mv "$P/.addons.m" "$P/addons.json"
  for A in $(jq -r '.addons[]?' "$P/addons.json"); do
    printf '%s' "$A" | grep -Eq '^[a-z0-9-]{1,100}$' || continue
    if timeout 60 aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$A" --region "$REGION" > "$P/.ad.json" 2>/dev/null \
       && jq -e . "$P/.ad.json" >/dev/null 2>&1; then
      jq -s '.[0] + {addonDetails: (.[0].addonDetails + [.[1].addon | objects])}' "$P/addons.json" "$P/.ad.json" > "$P/.addons.m" \
        && mv "$P/.addons.m" "$P/addons.json"
    else
      err addons error "eks describe-addon $A failed; its namespace is unknown to sec-10"
    fi
  done
  rm -f -- "$P/.ad.json"
fi
awsjson podidentity   eks:ListPodIdentityAssociations -- eks list-pod-identity-associations --cluster-name "$CLUSTER"
# Access entries (SEC-POSTURE-64): the list, then each entry's associated access policies. Written only
# when every entry was read, so a partial list never passes. A CONFIG_MAP-only cluster has no access
# entries: an empty document says so (its aws-auth mapping is read for SEC-POSTURE-10).
AUTHMODE=$(jq -r '.cluster.accessConfig.authenticationMode // empty' "$P/cluster.json")
if [ "$AUTHMODE" = CONFIG_MAP ]; then
  printf '{"authenticationMode":"CONFIG_MAP","accessEntries":[],"associations":[]}\n' > "$P/accessentries.json"
elif awsjson .ae-list eks:ListAccessEntries -- eks list-access-entries --cluster-name "$CLUSTER"; then
  if [ "$(pfv eks:ListAssociatedAccessPolicies)" = denied ]; then
    err accessentries denied "eks:ListAssociatedAccessPolicies was denied in the preflight; accessentries.json not collected"
  else
    printf '{"associations":[]}\n' > "$P/.ae.json"
    _ae_ok=1
    for PA in $(jq -r '.accessEntries[]?' "$P/.ae-list.json"); do
      if ! printf '%s' "$PA" | grep -Eq '^arn:aws[a-z-]*:iam::[0-9]{12}:[A-Za-z0-9+=,.@_/-]{1,512}$'; then
        _ae_ok=0; err accessentries error "access entry principal '$(printf '%s' "$PA" | cut -c1-120)' is not an IAM ARN; not read"; continue
      fi
      if timeout 60 aws eks list-associated-access-policies --cluster-name "$CLUSTER" --principal-arn "$PA" --region "$REGION" > "$P/.ae1.json" 2>/dev/null \
         && jq -e . "$P/.ae1.json" >/dev/null 2>&1; then
        jq -s --arg p "$PA" '{associations: (.[0].associations + [{principalArn:$p, associatedAccessPolicies:(.[1].associatedAccessPolicies // [])}])}' \
          "$P/.ae.json" "$P/.ae1.json" > "$P/.ae.m" && mv "$P/.ae.m" "$P/.ae.json"
      else
        _ae_ok=0; err accessentries error "eks list-associated-access-policies failed for $PA"
      fi
    done
    [ "$_ae_ok" -eq 1 ] && jq -s --arg m "${AUTHMODE:-unknown}" '{authenticationMode:$m, accessEntries:(.[0].accessEntries // []), associations:.[1].associations}' \
      "$P/.ae-list.json" "$P/.ae.json" > "$P/accessentries.json"
  fi
  rm -f -- "$P/.ae-list.json" "$P/.ae.json" "$P/.ae1.json" "$P/.ae.m"
fi
awsjson oidcproviders iam:ListOpenIDConnectProviders  -- iam list-open-id-connect-providers
if [ -n "$VPC" ]; then
  awsjson sg ec2:DescribeSecurityGroups -- ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC"
else
  err sg error "cluster.json carries no vpcId; sg.json not collected"
fi
awsjson ecr           ecr:DescribeRepositories -- ecr describe-repositories
awsjson ecr-scanning  ecr:GetRegistryScanningConfiguration -- ecr get-registry-scanning-configuration

# GuardDuty: configuration only (ListDetectors, GetDetector). Findings are never read.
if awsjson .gd-list guardduty:ListDetectors -- guardduty list-detectors; then
  printf '{"detectors":[]}\n' > "$P/.gd.json"
  _gd_ok=1
  for D in $(jq -r '.DetectorIds[]?' "$P/.gd-list.json"); do
    printf '%s' "$D" | grep -Eq '^[A-Za-z0-9]{1,300}$' || continue
    if timeout 60 aws guardduty get-detector --detector-id "$D" --region "$REGION" > "$P/.gd1.json" 2>/dev/null && jq -e . "$P/.gd1.json" >/dev/null 2>&1; then
      jq -s --arg d "$D" '{detectors: (.[0].detectors + [(.[1] + {DetectorId:$d})])}' "$P/.gd.json" "$P/.gd1.json" > "$P/.gd.m" && mv "$P/.gd.m" "$P/.gd.json"
    else
      _gd_ok=0; err guardduty error "guardduty get-detector $D failed"
    fi
  done
  [ "$_gd_ok" -eq 1 ] && mv "$P/.gd.json" "$P/guardduty.json"
  rm -f -- "$P/.gd1.json" "$P/.gd.json" "$P/.gd-list.json"
fi

# ── KUBERNETES SIDE ──
for R in nodes namespaces storageclasses clusterroles clusterrolebindings \
         validatingwebhookconfigurations mutatingwebhookconfigurations; do
  kjson "$R" "kubernetes: list $R" "$R"
done
kjson pv "kubernetes: list persistentvolumes" persistentvolumes
for R in pods deployments daemonsets ingresses networkpolicies serviceaccounts rolebindings; do
  kjson "$R" "kubernetes: list $R --all-namespaces" "$R" -A
done
[ -f "$P/validatingwebhookconfigurations.json" ] && mv "$P/validatingwebhookconfigurations.json" "$P/validatingwebhooks.json"
[ -f "$P/mutatingwebhookconfigurations.json" ]   && mv "$P/mutatingwebhookconfigurations.json" "$P/mutatingwebhooks.json"
kjson_optional awsauth      '{}' "kubernetes: get configmap/aws-auth -n kube-system" configmap aws-auth -n kube-system
kjson_optional vpccniconfig '{}' "kubernetes: get configmap/amazon-vpc-cni -n kube-system" configmap amazon-vpc-cni -n kube-system
kjson_optional kyverno             '{"items":[]}' - clusterpolicies.kyverno.io
kjson_optional constraints         '{"items":[]}' - constraints -A
kjson_optional constrainttemplates '{"items":[]}' - constrainttemplates
kjson_optional nodeclasses         '{"items":[]}' - nodeclasses.eks.amazonaws.com

# ── EC2 INSTANCES AND VOLUMES ──
# The tag-filtered list misses EKS Auto Mode instances, so every instance id named by a node is fetched
# by id as well (WAR's augment), in chunks of 100.
merge_by() {  # merge_by <file> <new> <kind: instances|volumes>
  if [ "$3" = instances ]; then
    jq -s '([.[0].Reservations[]?.Instances[]?.InstanceId]) as $h | {Reservations: ((.[0].Reservations//[]) + [.[1].Reservations[]? | .Instances=[.Instances[]?|select(.InstanceId as $i|($h|index($i))==null)] | select((.Instances|length)>0)])}' "$1" "$2"
  else
    jq -s '([.[0].Volumes[]?.VolumeId]) as $h | {Volumes: ((.[0].Volumes//[]) + [.[1].Volumes[]? | select(.VolumeId as $i|($h|index($i))==null)])}' "$1" "$2"
  fi
}
by_ids() {  # by_ids <name> <ec2 op> <flag> <kind> <ids...>
  local name="$1" op="$2" flag="$3" kind="$4" batch="" n=0 id one; shift 4
  [ -f "$P/$name.json" ] || return 0
  for id in "$@" ""; do
    [ -n "$id" ] && { batch="$batch $id"; n=$((n+1)); }
    if { [ "$n" -ge 100 ] || [ -z "$id" ]; } && [ "$n" -gt 0 ]; then
      # shellcheck disable=SC2086
      if timeout 120 aws ec2 "$op" "$flag" $batch --region "$REGION" > "$P/.ids.json" 2>"$P/.ids.err" && jq -e . "$P/.ids.json" >/dev/null 2>&1; then
        merge_by "$P/$name.json" "$P/.ids.json" "$kind" > "$P/.ids.m" && mv "$P/.ids.m" "$P/$name.json"
      elif [ "$n" -gt 1 ] && grep -qE 'InvalidInstanceID\.(NotFound|Malformed)' "$P/.ids.err" 2>/dev/null; then
        # One instance id EC2 does not return (a Node object that outlived its instance (EC2 drops a terminated
        # instance from DescribeInstances after usually under an hour) or a just-launched id EC2 does not yet
        # return) or a malformed one fails the whole call and takes every good id with it. EC2 named an
        # id, so retry one id at a time and keep the ones that resolve; the one-id call logs each id that still
        # fails. A throttle or a denial applies to every id, so it is not re-asked per id.
        for one in $batch; do by_ids "$name" "$op" "$flag" "$kind" "$one"; done
      else
        err "$name" error "ec2 $op by id failed for $n id(s)$([ "$n" -eq 1 ] && printf ' (%s)' "${batch# }"): $(firstline "$P/.ids.err")"
      fi
      batch=""; n=0
    fi
  done
  rm -f -- "$P/.ids.json" "$P/.ids.err"
}
if awsjson instances ec2:DescribeInstances -- ec2 describe-instances --filters "Name=tag:kubernetes.io/cluster/$CLUSTER,Values=owned,shared"; then
  NODE_IIDS=$(jq -r '[.items[]? | (.spec.providerID // ""), (.metadata.name // "")] | map(select(type=="string" and .!="") | split("/") | last) | map(select(test("^i-[0-9a-f]{8,}$"))) | unique | .[]' "$P/nodes.json" 2>/dev/null)
  MISSING=$(for i in $NODE_IIDS; do jq -e --arg i "$i" '[.Reservations[]?.Instances[]?.InstanceId]|index($i)' "$P/instances.json" >/dev/null 2>&1 || printf '%s\n' "$i"; done)
  # shellcheck disable=SC2086
  by_ids instances describe-instances --instance-ids instances $MISSING
fi
if awsjson volumes ec2:DescribeVolumes -- ec2 describe-volumes; then
  VOL_IDS=$(jq -rs '[(.[0]|.Reservations[]?.Instances[]?.BlockDeviceMappings[]?.Ebs.VolumeId?), (.[1]|.items[]?|(.spec.csi.volumeHandle?, .spec.awsElasticBlockStore.volumeID?))] | map(select(type=="string" and .!="")|split("/")|last) | map(select(test("^vol-[0-9a-f]{8,}$"))) | unique | .[]' "$P/instances.json" "$P/pv.json" 2>/dev/null)
  MISSING=$(for v in $VOL_IDS; do jq -e --arg v "$v" '[.Volumes[]?.VolumeId]|index($v)' "$P/volumes.json" >/dev/null 2>&1 || printf '%s\n' "$v"; done)
  # shellcheck disable=SC2086
  by_ids volumes describe-volumes --volume-ids volumes $MISSING
fi

# ── VALIDATION: every written file parses; the two that every judgement needs exist ──
for f in "$P"/*.json; do
  [ -f "$f" ] || continue
  jq -e . "$f" >/dev/null 2>&1 || { err "$(basename "$f" .json)" unparsable "$(basename "$f") is not valid JSON; removed from the set"; mv -- "$f" "$f.bad"; }
done
[ -f "$P/namespaces.json" ] && [ "$(jq '.items|length' "$P/namespaces.json" 2>/dev/null || echo 0)" -gt 0 ] \
  || die kubernetes_unreachable "namespaces.json is missing or empty: the Kubernetes API did not answer."
rm -rf -- "$KCACHE"
write_meta
jq -c --arg d "$P" '{ok:true,dir:$d,files:(.files|keys),errors:.errors}' "$P/meta.json"
exit 0
