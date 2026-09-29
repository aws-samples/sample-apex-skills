#!/usr/bin/env bash
# Collect every file the scorers read, once, into $WORK. Fails loud: a transient auth blip, throttle or
# permission error must never become empty data, because a plausible-looking wrong score is worse than a
# refusal. Ends with a validation gate that refuses to hand over an incomplete work dir.
#
# Usage:
#   export CLUSTER=<cluster-name> REGION=<region> KCTX=<kubectl-context>
#   ${CLAUDE_SKILL_DIR}/assets/collect.sh     # writes into ./eks-war-$CLUSTER, or $WORK if set
#
# The three variables must be exported in the SAME command as the script: the Bash tool runs each
# command in a separate process, so an export in an earlier call is already gone. SKILL_DIR is no
# longer read -- see the note further down where the check used to be.
#
# WHY THIS IS A SCRIPT AND NOT A FENCED BLOCK IN references/workflow.md.
# It used to be seven fenced blocks the agent pasted into a shell. Three problems, all real:
#
#  1. The tool-permission allowlist could not match it. Every call went through a retry wrapper --
#     `awsjson`, `kjson`, `kctl` -- so the command text a permission rule sees begins with the WRAPPER
#     name, not `aws` or `kubectl`. Bash rules are literal prefix matches ("everything before the first
#     `*` as written") and the built-in wrapper-strip list is fixed (timeout/time/nice/nohup/stdbuf/
#     command/builtin/noglob/xargs) -- shell functions are not on it. So a carefully narrowed allowlist
#     of `Bash(aws eks describe-cluster:*)`-style grants matched almost nothing that actually ran, every
#     collection line prompted, and the only way to stop the prompting was to re-grant `Bash(aws:*)` --
#     re-opening the destructive verbs the narrow list existed to withhold. One script is one grant, and
#     the grant names a file whose contents ship and can be read.
#  2. `bash -n` could not check it. The blocks carry <PLACEHOLDER> tokens, which bash parses as
#     redirects, so the shipped collection path had no syntax gate at all.
#  3. It was duplicated. The harness concatenated the blocks to test them; any drift between the prose
#     blocks and what was tested was invisible.
#
# references/workflow.md now documents what is collected and why. This file is what runs.
set -uo pipefail
umask 077   # belt-and-suspenders alongside the `chmod 700 "$WORK"` below: every file this script
            # creates (results.jsonl, every *.json, every *.json.tmp) lands owner-only from the
            # moment it exists, not just after the fact. Every write this script makes is under
            # $WORK, so this narrows nothing outside it.

: "${CLUSTER:?export CLUSTER to the EKS cluster name}"
# No apostrophe in this message: inside ${VAR:?word} an unescaped ' opens a quote context and swallows
# the closing brace, so `cluster's` turned the whole file into a syntax error. Caught by `bash -n`, which
# is the gate the fenced-block form never had.

# ── CLUSTER NAME VALIDATION -- runs BEFORE $WORK is derived or touched ──────────────────────────────
# $WORK defaults to $(pwd)/eks-war-$CLUSTER below, and this script goes on to `rm -f "$WORK"/*.json` --
# all before the first AWS call, so EKS's own name validation (which would reject a bad name) never
# gets a chance to run first. Reproduced in a sandbox: CLUSTER='./../../victim' made $WORK resolve
# OUTSIDE any eks-war-* path and deleted a precious.json that was sitting there. In an agentic context
# CLUSTER can arrive from a prompt or a document, so this is a confused-deputy, not a typo hazard --
# validated here against EKS's own constraint on `aws eks create-cluster --name`: "can contain only
# alphanumeric characters (case-sensitive), hyphens, and underscores... must start with an alphanumeric
# character... can not be longer than 100 characters."
if ! printf '%s' "$CLUSTER" | grep -Eq '^[0-9A-Za-z][A-Za-z0-9_-]*$'; then
  echo "collect.sh: CLUSTER is not a valid EKS cluster name -- it must start with an alphanumeric" \
    "character and contain only alphanumeric characters, hyphens and underscores (the same rule" \
    "\`aws eks create-cluster --name\` enforces). Refusing before \$WORK is derived or touched." >&2
  exit 1
fi
if [ "${#CLUSTER}" -gt 100 ]; then
  echo "collect.sh: CLUSTER is ${#CLUSTER} characters -- EKS cluster names can not be longer than 100" \
    "characters. Refusing before \$WORK is derived or touched." >&2
  exit 1
fi

: "${REGION:?export REGION to the AWS region the cluster is in}"
# REGION is never used to build a path or filename -- every use below is a quoted --region "$REGION"
# argument forwarded through awsjson's "$@" (never re-parsed by a shell), so it cannot cause the path
# traversal an unvalidated CLUSTER could. It is not the confused-deputy vector CLUSTER is, so it does
# not need CLUSTER's rule -- but a loose charset check still catches garbage (newlines, quotes, an
# accidentally-pasted ARN) before it burns three retries per AWS call for a single typo.
if ! printf '%s' "$REGION" | grep -Eq '^[a-z0-9-]{1,20}$'; then
  echo "collect.sh: REGION does not look like an AWS region code (lowercase letters, digits and" \
    "hyphens only, e.g. us-east-1). Refusing." >&2
  exit 1
fi

# WORK is deliberately NOT put through CLUSTER's character allowlist: unlike CLUSTER, an explicitly
# exported WORK is a caller choosing a directory on purpose, and a directory path legitimately
# contains slashes ($WORK is often an absolute path). The vulnerability this section closes is CLUSTER
# flowing UNVALIDATED into WORK's default ($(pwd)/eks-war-$CLUSTER); that path is closed above, before
# this line runs, regardless of whether WORK ends up defaulted or explicit. `${WORK:-default}` also
# already treats an explicitly-exported EMPTY string the same as unset, so `WORK=""` cannot make the
# rm below target `$(pwd)/*.json` by accident.
export WORK="${WORK:-$(pwd)/eks-war-$CLUSTER}"; mkdir -p "$WORK"
# Restrictive from the moment it exists: the collected JSON contains the account id, IAM role and
# OIDC ARNs, security-group and subnet ids, and cluster tags. `chmod`, not just an early `umask`, so a
# work dir left over from a run before this fix (or one a caller pre-created) is tightened on every
# run, not only on first creation.
chmod 700 "$WORK"
: > "$WORK/results.jsonl"
# There is deliberately no SKILL_DIR check here any more, and nothing in this script needs one.
#
# It used to demand `export SKILL_DIR=<abs path>` and refuse without it, so that Steps 7 and 8 could
# invoke assets/reduce.sh and assets/render-report.py from any working directory -- the bare
# `assets/...` form only resolved when the shell happened to be sitting in the skill root, which is
# not where $WORK is. This script never invoked either of them; it only validated the export on their
# behalf, to fail early rather than after a whole collection had run.
#
# SKILL.md now writes those invocations as `${CLAUDE_SKILL_DIR}/assets/...`, which Claude Code
# substitutes in both the skill body and the Bash rules in `allowed-tools` -- so the path arrives
# already absolute and there is nothing left to export or to check. Keeping the requirement after that
# change would refuse every run that followed the current instructions, which no longer tell anyone to
# export it. reduce.sh reads no SKILL_DIR at all, and render-report.py finds references/ from its own
# __file__, so neither downstream step depends on it either.
# Clear any PREVIOUS run's collection before starting. `awsjson`/`kjson` only ever write on
# success, so a stale file from an earlier run silently satisfies a call that fails this time —
# and the validation gate, whose entire purpose is to refuse un-collected data, then passes on
# data that was never collected. This bites a re-run after any partial failure.
rm -f "$WORK"/*.json

export AWS_PAGER=""            # never page
# AWS_PROFILE is honoured if the caller exports it; this script never sets it.

COLLECT_ERRORS=0              # incremented on any hard failure; checked by the validation gate

# ── CLUSTER IDENTITY BINDING (REQUIRED) ────────────────────────────────────────────────────────────
# The AWS half of this review comes from `aws eks describe-cluster --name $CLUSTER`, and the
# Kubernetes half from whatever `kubectl` happens to point at. NOTHING previously tied those together.
# A reviewer with several clusters in their kubeconfig could collect the control-plane facts from
# cluster A and every pod, node and RBAC object from cluster B, and the validation gate would pass:
# every REQUIRED file present, all valid JSON, `cluster.version` set, `namespaces.json` non-empty. The
# resulting report names cluster A and grades cluster B's workloads.
#
# KCTX is mandatory and has no default. `kubectl config current-context` is deliberately NOT used as a
# fallback: an unattended run would then silently inherit whatever context was last selected, which is
# the failure this binding exists to prevent.
export KCTX="${KCTX:?set KCTX to the kubectl context for this cluster — e.g. export KCTX=\$(kubectl config current-context)}"

# kctl : every kubectl call in this file goes through here, so the context cannot be forgotten on one
# of them. A binding enforced on some calls is not a binding.
kctl() { kubectl --context "$KCTX" "$@"; }

# firstline <file> : the first NON-EMPTY line of a captured stderr.
# `head -1` loses the reason whenever stderr opens with a blank line or a deprecation warning,
# leaving the operator with "ERROR: failed to collect volumes.json:" and no cause — which is
# nearly as unhelpful as no message at all. Observed for real on a denied ec2:DescribeVolumes.
firstline() { grep -m1 -v '^[[:space:]]*$' "$1" 2>/dev/null; }

# awsjson <outfile> -- <aws ...> : required AWS call. Retries (3x, backoff), writes only on
# success + valid JSON, otherwise records a hard error. Never fabricates data.
awsjson() {
  local out="$1"; shift; [ "${1:-}" = "--" ] && shift
  local tmp="$out.tmp" n=0
  while :; do
    if "$@" >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "$out"; rm -f "$tmp.err"; return 0
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then
      echo "ERROR: failed to collect $(basename "$out"): $(firstline "$tmp.err")" >&2
      rm -f "$tmp" "$tmp.err"; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1
    fi
    sleep $((n*2))
  done
}

# awsjson_detail <outfile> -- <aws ...> : DETAIL-ONLY AWS call. No scorer reads these files, so a
# failure is a warning and never fatal -- but it must also leave NO ARTIFACT.
# `aws ... > "$WORK/addon-$A.json" || echo WARN` did not: bash creates the redirect target BEFORE
# running the command, so a denied call left a 0-byte addon-*.json behind, and the blanket
# `jq -e .` scan in the validation gate then threw away a collection in which every REQUIRED file was
# present and valid. Observed for real on a read-only role holding eks:List* but not
# eks:DescribeAddon/eks:DescribeNodegroup -- those are commonly scoped out separately from the List
# calls -- which printed three "(non-fatal)" warnings and then "COLLECTION FAILED". A best-effort
# call whose failure discards the whole run is not best-effort. Writes via a `.tmp` path (which the
# gate's `*.json` glob does not match) and promotes it only on success + valid JSON.
awsjson_detail() {
  local out="$1"; shift; [ "${1:-}" = "--" ] && shift
  local tmp="$out.tmp"
  if "$@" >"$tmp" 2>/dev/null && jq -e . "$tmp" >/dev/null 2>&1; then
    mv "$tmp" "$out"; return 0
  fi
  rm -f "$tmp"; return 1                   # no partial file for the validation gate to trip over
}

# kjson <outfile> <kubectl get-args...> : required kubectl call. A cluster with no objects of a
# type returns exit 0 with {"items":[]} — that is a valid empty, kept as-is. A non-zero exit
# (auth/throttle/RBAC) is retried, then recorded as a hard error. Never fabricates data.
kjson() {
  local out="$1"; shift
  local tmp="$out.tmp" n=0
  while :; do
    if kctl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "$out"; rm -f "$tmp.err"; return 0
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then
      echo "ERROR: kubectl --context $KCTX get $* failed: $(firstline "$tmp.err")" >&2
      rm -f "$tmp" "$tmp.err"; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1
    fi
    sleep $((n*2))
  done
}

# kjson_optional_doc <outfile> <empty-doc> <kubectl get-args...> : for maybe-absent CRDs and objects.
# Falls back to <empty-doc> ONLY when the resource genuinely does not exist. Any other error is hard.
#
# <empty-doc> is a parameter because the two absent shapes are not the same shape. A LIST get returns
# `{"items":[]}`, so that is what its absence must look like; a SINGLE-OBJECT get (`get configmap
# amazon-vpc-cni`) returns one ConfigMap object, and normalising its absence to `{"items":[]}` hands the
# scorer a document of a type it never sees on a cluster where the object exists. `{}` keeps
# `.data["enable-network-policy"]` reading null either way, which is the point.
kjson_optional_doc() {
  local out="$1" empty="$2"; shift 2
  local tmp="$out.tmp"
  if kctl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
    mv "$tmp" "$out"; rm -f "$tmp.err"; return 0
  fi
  if grep -qiE "the server doesn't have a resource type|could not find (the )?requested resource|Unknown resource|NotFound" "$tmp.err" 2>/dev/null; then
    printf '%s\n' "$empty" >"$out"; rm -f "$tmp" "$tmp.err"; return 0   # genuinely absent → empty is correct
  fi
  echo "ERROR: kubectl --context $KCTX get $* failed (not a missing-resource error): $(firstline "$tmp.err")" >&2
  rm -f "$tmp" "$tmp.err"; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1
}

# kjson_optional <outfile> <kubectl get-args...> : the list-shaped case, unchanged for its six callers.
kjson_optional() {
  local out="$1"; shift
  kjson_optional_doc "$out" '{"items":[]}' "$@"
}
awsjson "$WORK/cluster.json"    -- aws eks describe-cluster       --name "$CLUSTER" --region "$REGION" --output json
awsjson "$WORK/nodegroups.json" -- aws eks list-nodegroups        --cluster-name "$CLUSTER" --region "$REGION" --output json
awsjson "$WORK/addons.json"     -- aws eks list-addons            --cluster-name "$CLUSTER" --region "$REGION" --output json
awsjson "$WORK/fargate.json"    -- aws eks list-fargate-profiles  --cluster-name "$CLUSTER" --region "$REGION" --output json

# EKS Pod Identity associations. REQUIRED, not optional: Pod Identity is the mechanism AWS now
# recommends over IRSA, and it uses NO ServiceAccount annotation — associations live only in the
# EKS API. Without this call, `sec-6` (High) sees a correctly-built Pod Identity cluster as having
# no workload identity at all and reports a false High-severity finding.
awsjson "$WORK/podidentity.json" -- aws eks list-pod-identity-associations --cluster-name "$CLUSTER" --region "$REGION" --output json

# The IAM OIDC identity provider. REQUIRED, and deliberately NOT treated as optional.
# `cluster.identity.oidc.issuer` is populated on EVERY EKS cluster — it is the *input* to
# `aws iam create-open-id-connect-provider`, not evidence that the provider exists. The provider is
# a separate IAM resource, so scoring OIDC/IRSA off the issuer alone is a pass that cannot fail.
# Note this is an ACCOUNT-scoped call (iam:ListOpenIDConnectProviders), unlike everything else here.
# It must still fail loud: if a denial were substituted with an empty list, `sec-18` (High) would
# report "no IAM OIDC provider" on a cluster that has one — a false finding is worse than a refusal.
awsjson "$WORK/oidcproviders.json" -- aws iam list-open-id-connect-providers --output json

export VPC=$(jq -r '.cluster.resourcesVpcConfig.vpcId // empty' "$WORK/cluster.json")

# ── IDENTITY CROSS-CHECK: does $KCTX actually point at $CLUSTER? ────────────────────────────────────
# Runs HERE — after cluster.json exists, before the first `kubectl get` — so a mismatch costs one AWS
# call rather than a full collection and a wrong report.
#
# Compare API server ENDPOINTS, not context names. A context name is user-renameable and often not the
# cluster ARN, so matching on it produces false alarms; the endpoint is assigned by EKS and unique per
# cluster. `kubectl config view --minify` resolves the server URL for the selected context only.
K_ENDPOINT=$(kubectl --context "$KCTX" config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)
A_ENDPOINT=$(jq -r '.cluster.endpoint // empty' "$WORK/cluster.json")
if [ -z "$K_ENDPOINT" ] || [ -z "$A_ENDPOINT" ]; then
  echo "ERROR: cannot verify cluster identity — kubeconfig server='$K_ENDPOINT', describe-cluster endpoint='$A_ENDPOINT'." >&2
  echo "       Refusing to collect: an unverified binding is how the AWS half and the kubectl half end up" >&2
  echo "       describing different clusters." >&2
  COLLECT_ERRORS=$((COLLECT_ERRORS+1))
elif [ "${K_ENDPOINT%/}" != "${A_ENDPOINT%/}" ]; then
  echo "ERROR: CLUSTER MISMATCH — refusing to collect." >&2
  echo "       kubectl context '$KCTX' points at : $K_ENDPOINT" >&2
  echo "       aws describe-cluster '$CLUSTER' is: $A_ENDPOINT" >&2
  echo "       The report would name '$CLUSTER' while grading a different cluster's workloads." >&2
  echo "       Fix with: aws eks update-kubeconfig --name $CLUSTER --region $REGION --alias $CLUSTER" >&2
  COLLECT_ERRORS=$((COLLECT_ERRORS+1))
else
  echo "OK: kubectl context '$KCTX' and cluster '$CLUSTER' both resolve to $A_ENDPOINT"
fi
# Abort now rather than at the validation gate: every kubectl call after this point would collect the
# wrong cluster's data, and the gate cannot tell whose data it is looking at.
[ "$COLLECT_ERRORS" -eq 0 ] || { echo "Aborting collection." >&2; exit 1; }
[ -n "$VPC" ] || { echo "ERROR: could not read VPC id from cluster.json — aborting (cluster describe failed?)" >&2; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); }

# per nodegroup / addon (detail only; not read by scorers, so best-effort with a warning).
# Routed through awsjson_detail so a failure leaves no artifact -- see the comment on that helper.
for NG in $(jq -r '.nodegroups[]?' "$WORK/nodegroups.json"); do
  awsjson_detail "$WORK/nodegroup-$NG.json" -- aws eks describe-nodegroup --cluster-name "$CLUSTER" --nodegroup-name "$NG" --region "$REGION" --output json \
    || echo "WARN: nodegroup detail $NG not collected (non-fatal; no scorer reads it)" >&2; done
for A in $(jq -r '.addons[]?' "$WORK/addons.json"); do
  awsjson_detail "$WORK/addon-$A.json" -- aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$A" --region "$REGION" --output json \
    || echo "WARN: addon detail $A not collected (non-fatal; no scorer reads it)" >&2; done
# Fargate profile detail, merged into ONE file the scorers read. fargate-1 (selector specificity) and
# fargate-3 (pod execution roles) used to answer `na~NOT ASSESSED` because this call was never made --
# claiming "not applicable" for something the review simply had not looked at, which is excluded from
# scoring and so silently inflated coverage. Required, not best-effort: if there are profiles, their
# detail is the only way to answer two questions that would otherwise pretend to be inapplicable.
echo '{"profiles":[]}' > "$WORK/fargateprofiles.json"
for FP in $(jq -r '.fargateProfileNames[]?' "$WORK/fargate.json"); do
  if awsjson "$WORK/.fp.json" -- aws eks describe-fargate-profile --cluster-name "$CLUSTER" --fargate-profile-name "$FP" --region "$REGION" --output json; then
    jq -s '{profiles: (.[0].profiles + [.[1].fargateProfile])}' "$WORK/fargateprofiles.json" "$WORK/.fp.json" > "$WORK/.fpm.json" \
      && mv "$WORK/.fpm.json" "$WORK/fargateprofiles.json"
  fi
done
rm -f "$WORK/.fp.json"
for R in nodes namespaces storageclasses pv clusterroles clusterrolebindings \
         validatingwebhookconfigurations mutatingwebhookconfigurations; do
  kjson "$WORK/$R.json" "$R"; done
for R in pods deployments statefulsets daemonsets services ingresses networkpolicies hpa pdb \
         serviceaccounts pvc resourcequotas limitranges cronjobs jobs rolebindings; do
  kjson "$WORK/$R.json" "$R" -A; done
# cp, not `ln -sf`: the scorers read these under both names, and a copy needs no symlink support and
# no `ln` in the tool allowlist. The symlinks also broke silently if $WORK was moved or archived, since
# they were written relative to the directory.
cp "$WORK/validatingwebhookconfigurations.json" "$WORK/validatingwebhooks.json"
cp "$WORK/mutatingwebhookconfigurations.json" "$WORK/mutatingwebhooks.json"
# Kyverno / Gatekeeper policies — optional CRDs; empty only when the CRD is not installed
# EKS Fargate's documented log router is NOT a sidecar. AWS: "you don't explicitly run a Fluent Bit
# container as a sidecar, but Amazon runs it for you. All that you have to do is configure the log
# router" — via a ConfigMap named `aws-logging` in the namespace `aws-observability`. Without collecting
# it, `fargate-4` can never credit a correctly-configured Fargate cluster. Optional-style because its
# absence is a legitimate finding, not a collection failure.
kjson_optional "$WORK/awslogging.json" configmap aws-logging -n aws-observability
# aws-auth maps IAM principals to Kubernetes RBAC groups. An entry granting system:masters is a
# full-cluster takeover path via IAM, and it is invisible to a ClusterRoleBinding check: the binding
# names the GROUP system:masters, which is a legitimate built-in, while the aws-auth ConfigMap decides
# who is IN that group. rbac-1 therefore reads this file as its second input, alongside
# clusterrolebindings.json -- sec-17 still only reads accessConfig.authenticationMode.
#
# This file used to be collected and read by nothing at all, which is worse than not collecting it: the
# comment here described the exact attack path as the reason for collecting it, so the gap read as
# coverage. Optional because a cluster on API-only auth legitimately has no aws-auth ConfigMap, and its
# absence must leave rbac-1 exactly as it was rather than manufacture a finding.
kjson_optional "$WORK/awsauth.json" configmap aws-auth -n kube-system
# PeerAuthentication decides whether a service mesh actually ENFORCES mTLS. Istio defaults to PERMISSIVE
# (plaintext still accepted), so sidecar presence alone does not answer sec-28. Optional: the CRD is
# absent on any cluster without Istio.
kjson_optional "$WORK/peerauthentications.json" peerauthentications.security.istio.io -A

kjson_optional "$WORK/kyverno.json"           clusterpolicies.kyverno.io
kjson_optional "$WORK/constraints.json"       constraints -A
kjson_optional "$WORK/constrainttemplates.json" constrainttemplates

# ── TWO AUTO MODE OBJECTS WHERE ABSENCE *IS* THE ANSWER ─────────────────────────────────────────────
# Both go through the optional helper, and the contrast with the two EC2 calls further down is the
# crux of this whole change -- they look like the same situation and are opposites:
#
#   * An EC2 list call that comes back empty on an Auto Mode cluster is a BLIND INSTRUMENT. Nothing
#     about the cluster changed; the API stopped reporting. Scoring that as "no instances, no volumes"
#     invents three findings, so it is repaired below and, if it cannot be repaired, REFUSED.
#   * A ConfigMap or a CRD that is not there IS the measurement. No `amazon-vpc-cni` ConfigMap means
#     the Network Policy Controller was never enabled; no NodeClass means no Auto Mode NodeClass was
#     ever created. Both are exactly what the operator wants to be told. Turning either into a
#     collection error would refuse an entire review over a correct answer.
#
# So these two exit 0 with a normalised empty document and never touch the not-collected machinery --
# while a Forbidden or a connection failure still fails loud, because the helper only accepts
# "resource does not exist" as grounds for an empty.

# The amazon-vpc-cni ConfigMap. https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html,
# "Step 1: Enable Network Policy Controller", verbatim:
#   "To use network policies with EKS Auto Mode, you first need to enable the Network Policy Controller
#    by applying a ConfigMap to your cluster."
# and the manifest it then shows is `metadata.name: amazon-vpc-cni`, `namespace: kube-system`,
# `data.enable-network-policy-controller: "true"`.
# https://docs.aws.amazon.com/eks/latest/best-practices/autosecure.html shows the OTHER spelling of the
# same switch -- the same ConfigMap name and namespace with `enable-network-policy: "true"` -- and adds:
#   "It's also required to define the Network Policy support is configured in the Node Class, as
#    illustrated here:"
# followed by a NodeClass carrying `networkPolicy`/`networkPolicyEventLogs`. Two spellings and a second
# object to correlate is precisely why what gets collected is the whole ConfigMap rather than a
# pre-digested boolean: `sec-4` reads both keys out of this one file, and the NodeClass out of the next.
kjson_optional_doc "$WORK/vpccniconfig.json" '{}' configmap amazon-vpc-cni -n kube-system

# Auto Mode NodeClasses. https://docs.aws.amazon.com/eks/latest/userguide/create-node-class.html
# documents `spec.networkPolicy` ("networkPolicy: DefaultAllow  # or DefaultDeny") and, under
# `spec.advancedNetworking`:
#   "ipv4PrefixSize is default to Auto which is prefix and fallback to secondary IP. \"32\" is the
#    secondary IP mode."
# Both are defaults an operator may have overridden, and `sec-4` and `net-3` must read the value rather
# than assert the default. Cluster-scoped, so no `-A`. `{"items":[]}` when the CRD is absent, which is
# every cluster that is not in Auto Mode.
kjson_optional "$WORK/nodeclasses.json" nodeclasses.eks.amazonaws.com
awsjson "$WORK/sg.json"           -- aws ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/subnets.json"      -- aws ec2 describe-subnets         --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/nat.json"          -- aws ec2 describe-nat-gateways     --filter Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/routetables.json"  -- aws ec2 describe-route-tables    --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/vpcendpoints.json" -- aws ec2 describe-vpc-endpoints   --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
# ── EC2 INSTANCES AND VOLUMES: THE LIST APIs WENT BLIND ON EKS AUTO MODE ────────────────────────────
# These two were one list-form call each. On an EKS Auto Mode cluster both now return an empty set, and
# an empty-but-valid document passed every check this script made -- so `lens-11` (IMDSv2), `sec-21`
# (EBS encryption) and `cost-8` (idle volumes), all weight 3, silently became `na` with no error and no
# note in the report. `b()` renders a zero denominator as `na~0/0 IMDSv2`, which reads like a
# measurement rather than an absence, and `na` removes a question from the DENOMINATOR -- so the cluster
# nobody could see scored BETTER than one that was fully audited.
#
# https://docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html, "Managed resource
# visibility", verbatim:
#   "Beginning April 22, 2026, new Amazon EC2 managed instances and associated resources (for example,
#    EC2 launch templates, EBS volumes, and network interfaces (ENIs)) created by EKS Auto Mode are
#    hidden from EC2 console views and `describe` API list operations by default. Managed resources that
#    already existed in your account before that date remain visible."
# That date is past, so a review run today hits this by default on any Auto Mode cluster whose nodes
# were launched after it. The same page, verbatim, gives the ways through:
#   "Even when managed resources are hidden from EC2 console views and list APIs, you can still view EKS
#    Auto Mode instances through:" ... "Kubernetes APIs (for example, `kubectl get nodes`)." ...
#   "Direct EC2 API queries by instance ID (for example, `describe-instances --instance-ids
#    i-0123456789abcdef0`)." ... "The `DescribeInstances` API with the `include-managed-resources`
#    parameter."
# It also documents the account-wide setting that would restore the list APIs -- deliberately NOT used
# or suggested here: changing it is a write to an account setting, and this skill only ever looks.
#
# WHY NOT `--include-managed-resources`. The API parameter is real; the EC2 API Reference documents it
# on both operations, e.g.
# https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
#   "IncludeManagedResources: Indicates whether to include managed resources in the output. If this
#    parameter is set to `true`, the output includes resources that are managed by AWS services, even if
#    managed resource visibility is set to hidden."
# The CLI does not expose it yet. Tested 2026-09-11 against
# `aws-cli/2.34.30 Python/3.14.7 Darwin/25.6.0 source/arm64`:
#   $ aws ec2 describe-instances --include-managed-resources --max-items 1
#   aws: [ERROR]: Unknown options: --include-managed-resources
# A skill cannot dictate the operator's CLI version, so everything below is built on the instance-ID
# path, which works on every version. The negative result is recorded here rather than left as folklore:
# when a CLI ships the flag, this block collapses back to two calls, and a maintainer should be able to
# see why the complicated version existed.
#
# HOW THE ID PATH WORKS.
#  - Instance IDs come from `nodes.json`, already collected above. `.spec.providerID` on an EC2-backed
#    node ends in the instance id, and on an Auto Mode node the node NAME is the instance id --
#    https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
#    "Lastly, Auto Mode nodes use the EC2 instance ID as the Kubernetes node name." Both are read and
#    only strings matching `^i-<hex>$` survive. That filter is load-bearing twice over: a Fargate
#    providerID is a different shape (`aws:///<az>/fargate-ip-10-0-4-122...`) and ONE unusable id fails
#    the whole `describe-instances` call, taking every good id down with it; and node objects are
#    cluster data rather than local input, so the anchored hex-only pattern is also what makes the
#    deliberately-unquoted `$batch` expansion below safe -- no surviving id can hold a space, a quote,
#    a semicolon or a glob character.
#  - Volume IDs come from the instances just collected (`BlockDeviceMappings[].Ebs.VolumeId`) and from
#    `pv.json` (`spec.csi.volumeHandle`, plus the legacy `spec.awsElasticBlockStore.volumeID`), keeping
#    only `^vol-<hex>$` -- an EFS volumeHandle (`fs-0123::fsap-4567`) must not reach `describe-volumes`
#    for the same all-or-nothing reason.
#  - The list call is KEPT and merged with, never replaced: it still finds cluster instances that are
#    not currently nodes -- a stopped instance, one that never joined, a leftover from a scaled-in
#    nodegroup -- which the id path cannot see because they are in nobody's `nodes.json`. Merging
#    dedupes by `InstanceId`/`VolumeId` and preserves `{"Reservations":[...]}` and `{"Volumes":[...]}`
#    exactly, because that is the shape the scorers read.
#
# THE RESIDUAL GAP, DISCLOSED RATHER THAN CLOSED. An Auto Mode EBS volume that is attached to nothing
# and backs no PersistentVolume has no id discoverable from `nodes.json` or `pv.json`, so it stays
# invisible and `cost-8` cannot count it. For NODE volumes that should not arise --
# https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
# says "On EKS Auto Mode nodes, the root and data Amazon EBS volumes are encrypted and configured to be
# deleted upon termination of the instance" -- but a volume created by something else and left behind
# can still hide. references/workflow.md tells the reader the same thing, because `cost-8` reporting no
# idle volumes on an Auto Mode cluster must not be read as proof that there are none.
# Second-order limit worth knowing: `cost-8` and `sec-21` then scope volumes by cluster TAG, so an
# ID-recovered volume that carries no cluster tag is collected but still not counted. Collection's job
# ends at making it visible; the tag scoping lives in the scorers.
#
# CHUNKING. The id form cannot be page-sized:
# https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html says of MaxResults
# "You cannot specify this parameter and the instance IDs parameter in the same request", while the same
# page warns "We strongly recommend using only paginated requests. Unpaginated requests are susceptible
# to throttling and timeouts." The only lever left is the length of the id list itself, so it is chunked
# -- which also keeps a several-hundred-node cluster's argv well clear of the OS argument limit.
EC2_ID_CHUNK=100

# merge_instances / merge_volumes <base> <add> : <base> plus everything in <add> it does not already
# have, first occurrence winning. The list call's copy of an instance is therefore the one kept, and the
# output order is a pure function of the input order, which is what keeps two runs byte-identical.
# Each new instance stays inside its own reservation so `OwnerId`/`ReservationId` survive; a reservation
# left with no instances is dropped rather than emitted empty.
# The `.InstanceId as $id | ($have | index($id))` dance is not stylistic: inside `A | index(B)`, `B` is
# evaluated with `.` rebound to `A`, so the obvious `$have | index(.InstanceId)` reads `.InstanceId` off
# the ARRAY and dies with "Cannot index array with string". Bind the id before the pipe.
merge_instances() {
  jq -s '.[0] as $a | .[1] as $b
    | ([$a.Reservations[]?.Instances[]?.InstanceId] | map(select(. != null))) as $have
    | {Reservations: (($a.Reservations // [])
        + [ $b.Reservations[]?
            | .Instances = [ .Instances[]?
                             | select(.InstanceId as $id | ($have | index($id)) == null) ]
            | select((.Instances | length) > 0) ])}' "$1" "$2"
}
merge_volumes() {
  jq -s '.[0] as $a | .[1] as $b
    | ([$a.Volumes[]?.VolumeId] | map(select(. != null))) as $have
    | {Volumes: (($a.Volumes // [])
        + [ $b.Volumes[]? | select(.VolumeId as $id | ($have | index($id)) == null) ])}' "$1" "$2"
}

# augment_by_ids <target> <ec2-subcommand> <id-flag> <merge-fn> <count-jq> <id...> : top up <target>
# with id-form calls, in chunks, merging each chunk in as it arrives.
#
# BEST-EFFORT ON PURPOSE, and this is the one judgement call in the block. A hard error here would be
# indistinguishable from a denied list call -- which is already a refusal, since the list call above it
# uses `awsjson` -- and would make an id-path hiccup fatal on clusters that never needed the id path at
# all. What actually matters is whether the run ended up with any instances/volumes on a cluster that
# plainly has some, and that is asserted on the MERGED result by the canaries in the validation gate.
# So: warn here (with the reason, not just "failed"), refuse there.
#
# Writes through a dot-prefixed temp, like the Fargate merge above, because bash creates a redirect
# target before running the command: a plain `> "$WORK/x.json"` on a denied call leaves a 0-byte
# x.json that the gate's `*.json` scan then rejects, discarding an otherwise complete collection.
# A leading dot keeps the temp out of that glob, and it is removed either way.

# ids_call <target> <ec2-subcommand> <id-flag> <merge-fn> <id...> : one id-form call, merged on success.
# Returns 0 on merge, 1 on anything else, and leaves $IDS_CALL_ERR set to the first stderr line so the
# caller can decide whether the failure is worth splitting up.
ids_call() {
  local target="$1" sub="$2" flag="$3" mergefn="$4"; shift 4
  local base tmp merged rc=1
  base=$(basename "$target" .json); tmp="$WORK/.$base-add.json"; merged="$WORK/.$base-merged.json"
  IDS_CALL_ERR=""
  # "$@" is expanded unquoted-per-word by the caller; here each id is already its own parameter, so
  # "$@" is correct and no re-splitting happens.
  if aws ec2 "$sub" "$flag" "$@" --region "$REGION" --output json >"$tmp" 2>"$tmp.err" \
     && jq -e . "$tmp" >/dev/null 2>&1; then
    if "$mergefn" "$target" "$tmp" >"$merged" && jq -e . "$merged" >/dev/null 2>&1; then
      mv "$merged" "$target"; rc=0
    else
      IDS_CALL_ERR="could not merge the response into $base.json"
    fi
  else
    IDS_CALL_ERR="$(firstline "$tmp.err")"
  fi
  rm -f "$tmp" "$tmp.err" "$merged"
  return "$rc"
}

augment_by_ids() {
  local target="$1" sub="$2" flag="$3" mergefn="$4" cexpr="$5"; shift 5
  local base batch id one
  local n=0 i=0 calls=0 fails=0 total=$# before after
  base=$(basename "$target" .json)
  [ "$total" -gt 0 ] || return 0
  before=$(jq "$cexpr" "$target" 2>/dev/null || echo 0)
  batch=""
  for id in "$@"; do
    batch="$batch $id"; n=$((n+1)); i=$((i+1))
    if [ "$n" -ge "$EC2_ID_CHUNK" ] || [ "$i" -eq "$total" ]; then
      calls=$((calls+1))
      # $batch is intentionally unquoted: it must word-split into one argv element per id. Safe only
      # because every id was matched against an anchored hex-only pattern before it got here.
      if ! ids_call "$target" "$sub" "$flag" "$mergefn" $batch; then
        echo "WARN: aws ec2 $sub $flag (chunk $calls, $n id(s)) returned no usable data:" \
             "$IDS_CALL_ERR" >&2
        fails=$((fails+1))
        # ONE unusable id fails the whole call and takes every good id with it. The realistic cause is
        # not a bug but a race: a Node object briefly outlives its instance during a scale-in, so its
        # id is gone by the time this runs -- and on an Auto Mode cluster, where the list call
        # contributes nothing, that single stale id would otherwise empty the file and make the
        # validation gate refuse a review of a perfectly healthy cluster. So when EC2 says an id is the
        # problem, retry the chunk one id at a time and keep the ones that resolve. Gated on the error
        # naming an id, deliberately: a throttle or a denial applies to every id equally and re-asking
        # per id would just multiply it.
        if [ "$n" -gt 1 ] && printf '%s' "$IDS_CALL_ERR" \
             | grep -qE 'Invalid(InstanceID|Volume|ParameterValue)'; then
          echo "      retrying those $n id(s) individually -- EC2 named an id, so the rest may be fine" >&2
          for one in $batch; do
            calls=$((calls+1))
            ids_call "$target" "$sub" "$flag" "$mergefn" "$one" || fails=$((fails+1))
          done
        fi
      fi
      batch=""; n=0
    fi
  done
  after=$(jq "$cexpr" "$target" 2>/dev/null || echo 0)
  echo "OK: $base.json: $before from the list call, $((after - before)) added by $flag" \
       "($total id(s), $calls call(s), $fails of them failed)"
}

awsjson "$WORK/instances.json"    -- aws ec2 describe-instances       --filters Name=tag:kubernetes.io/cluster/"$CLUSTER",Values=owned,shared --region "$REGION" --output json
# Only augment a file the list call actually produced. If that call hard-failed, COLLECT_ERRORS is
# already set and the gate will refuse; writing this file from the id path alone would convert a
# refusal into a partial answer nobody asked for.
if [ -f "$WORK/instances.json" ]; then
  # `select(. != "")` before `split` is not defensive padding: `"" | split("/")` is `[]`, `last` on that
  # is null, and `test` on null aborts the whole program -- which would have left $NODE_IIDS empty and
  # skipped the id path in silence, the exact failure mode this section exists to remove. A node with no
  # `providerID` at all (a Windows node in one of the harness fixtures) reaches that path for real.
  NODE_IIDS=$(jq -r '[ .items[]? | (.spec.providerID // ""), (.metadata.name // "") ]
                     | map(select(type == "string" and . != "") | split("/") | last)
                     | map(select(test("^i-[0-9a-f]{8,}$")))
                     | unique | .[]' "$WORK/nodes.json" 2>/dev/null)
  # Unquoted on purpose (word-splitting into separate ids); see augment_by_ids.
  augment_by_ids "$WORK/instances.json" describe-instances --instance-ids merge_instances \
                 '[.Reservations[]?.Instances[]?] | length' $NODE_IIDS
fi

awsjson "$WORK/volumes.json"      -- aws ec2 describe-volumes         --region "$REGION" --output json
if [ -f "$WORK/volumes.json" ]; then
  # Derived AFTER the instance merge above, so an Auto Mode node recovered by id also contributes its
  # root and data volume ids here. https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
  # on VolumeId.N: "The volume IDs. If not specified, then all volumes are included in the response."
  VOL_IDS=$(jq -rs '[ (.[0] | .Reservations[]?.Instances[]?.BlockDeviceMappings[]?.Ebs.VolumeId?),
                      (.[1] | .items[]? | (.spec.csi.volumeHandle?, .spec.awsElasticBlockStore.volumeID?)) ]
                    | map(select(type == "string" and . != "") | split("/") | last)
                    | map(select(test("^vol-[0-9a-f]{8,}$")))
                    | unique | .[]' "$WORK/instances.json" "$WORK/pv.json" 2>/dev/null)
  augment_by_ids "$WORK/volumes.json" describe-volumes --volume-ids merge_volumes \
                 '[.Volumes[]?] | length' $VOL_IDS
fi
awsjson "$WORK/ecr.json"          -- aws ecr describe-repositories    --region "$REGION" --output json
awsjson "$WORK/cloudtrail.json"   -- aws cloudtrail describe-trails   --region "$REGION" --output json
INVALID=""
for f in "$WORK"/*.json; do
  [ -L "$f" ] && continue                                   # skip the two symlink aliases
  jq -e . "$f" >/dev/null 2>&1 || INVALID="$INVALID $(basename "$f")"
done

# Every file a scorer reads MUST exist and parse. A file that was never collected
# is indistinguishable from "the cluster has none of these" once scoring starts,
# which silently pins the dependent questions to "none" and deflates the score.
# Listing them explicitly is what makes an un-run collection command a hard error.
REQUIRED="cluster nodegroups addons fargate podidentity oidcproviders nodes pods
deployments statefulsets daemonsets services ingresses networkpolicies hpa pdb
namespaces serviceaccounts clusterroles clusterrolebindings rolebindings
storageclasses pv pvc resourcequotas limitranges cronjobs jobs
validatingwebhookconfigurations mutatingwebhookconfigurations sg subnets nat
routetables vpcendpoints instances volumes ecr cloudtrail"
for r in $REQUIRED; do
  [ -f "$WORK/$r.json" ] || { INVALID="$INVALID $r.json(NOT COLLECTED)"; continue; }
  jq -e . "$WORK/$r.json" >/dev/null 2>&1 || INVALID="$INVALID $r.json(unparseable)"
done
# The Kyverno/Gatekeeper CRDs and the Fargate log-router ConfigMap are the only legitimately-EMPTY
# files, but each must still exist as valid JSON so the scorers can read it. awslogging is here and
# not in REQUIRED because the ConfigMap is genuinely absent on most clusters — but absent-as-an-object
# and absent-as-a-file are different things: fargate-4 reads it through m3, which ABORTS the whole
# Operational Excellence block on an unopenable input. A truncated pillar does not fail loudly, it
# emits fewer questions and the reducer scores what arrived: 16 questions instead of 19, coverage 62%,
# which still clears the 50% gate. So the pillar publishes a plausible number off two-thirds of its
# evidence. That is the exact failure this gate exists to prevent, and it was reachable purely because
# a newly-collected file was never added to either list.
for r in kyverno constraints constrainttemplates awslogging awsauth peerauthentications fargateprofiles \
         vpccniconfig nodeclasses; do
  [ -f "$WORK/$r.json" ] && jq -e . "$WORK/$r.json" >/dev/null 2>&1 \
    || INVALID="$INVALID $r.json(missing/unparseable; write '{\"items\":[]}' if the CRD is absent)"
done

# ── COLLECTION-GAP CANARIES: instances.json and volumes.json may NOT be silently empty ──────────────
# Neither file is in the may-be-empty list above, and references/workflow.md says the same in prose, so
# the rule and the code cannot drift. An empty `instances.json` on a cluster whose nodes ARE EC2
# instances is not a finding, it is the blind list API described in the Auto Mode note further up: the
# id path above exists to repair it, and when the repair does not land, this refuses instead of
# publishing `na~0/0 IMDSv2`. Recorded through $INVALID -- the same not-collected mechanism the REQUIRED
# loop uses -- so this script still has exactly one way of refusing.
if [ -f "$WORK/nodes.json" ] && [ -f "$WORK/instances.json" ]; then
  # "EC2 node" = any node that is not Fargate. Fargate nodes carry a `fargate-` providerID and the
  # `eks.amazonaws.com/compute-type=fargate` label, and they are backed by no EC2 instance at all, so a
  # Fargate-only cluster legitimately has zero instances and must not trip this.
  EC2_NODES=$(jq '[ .items[]?
                    | select(((((.spec.providerID // "") | test("/fargate-"))
                               or (.metadata.labels["eks.amazonaws.com/compute-type"] == "fargate"))
                              | not)) ] | length' "$WORK/nodes.json" 2>/dev/null || echo 0)
  INST_TOTAL=$(jq '[.Reservations[]?.Instances[]?] | length' "$WORK/instances.json" 2>/dev/null || echo 0)
  if [ "${EC2_NODES:-0}" -gt 0 ] && [ "${INST_TOTAL:-0}" -eq 0 ]; then
    INVALID="$INVALID instances.json(NOT COLLECTED: ${EC2_NODES} non-Fargate node(s) in nodes.json but"
    INVALID="$INVALID zero EC2 instances -- EKS Auto Mode hides managed instances from list APIs and the"
    INVALID="$INVALID instance-id fallback also came back empty; lens-11/sec-21/cost-8 would score 0/0)"
  fi
fi
if [ -f "$WORK/volumes.json" ] && [ -f "$WORK/instances.json" ] && [ -f "$WORK/pv.json" ]; then
  # $VOL_IDS is exactly the set of ids the id path asked about -- block devices on the collected
  # instances plus PV volume handles -- so counting it needs no second, drifting expression. It is also
  # deliberately shape-based rather than driver-based: EKS Auto Mode's CSI driver is
  # `ebs.csi.eks.amazonaws.com`, not `ebs.csi.aws.com`, so a `.spec.csi.driver ==` test would be blind
  # to exactly the clusters this canary exists for, while a `vol-…` volumeHandle is an EBS volume under
  # any driver name.
  EBS_EXPECTED=0
  for v in ${VOL_IDS:-}; do EBS_EXPECTED=$((EBS_EXPECTED+1)); done
  VOL_TOTAL=$(jq '[.Volumes[]?] | length' "$WORK/volumes.json" 2>/dev/null || echo 0)
  if [ "${EBS_EXPECTED:-0}" -gt 0 ] && [ "${VOL_TOTAL:-0}" -eq 0 ]; then
    INVALID="$INVALID volumes.json(NOT COLLECTED: ${EBS_EXPECTED} EBS volume id(s) are referenced by the"
    INVALID="$INVALID collected instances or PersistentVolumes but describe-volumes returned none --"
    INVALID="$INVALID same Auto Mode visibility cause; sec-21/cost-8 would score 0/0)"
  fi
fi

# semantic canaries that catch a silent auth/throttle failure the per-call checks might miss
[ -n "$(jq -r '.cluster.version // empty' "$WORK/cluster.json" 2>/dev/null)" ] \
  || INVALID="$INVALID cluster.json(no .cluster.version)"
[ "$(jq '.items|length' "$WORK/namespaces.json" 2>/dev/null || echo 0)" -gt 0 ] \
  || INVALID="$INVALID namespaces.json(empty→cluster unreachable?)"

if [ "$COLLECT_ERRORS" -gt 0 ] || [ -n "$INVALID" ]; then
  echo "COLLECTION FAILED — do NOT score this data." >&2
  [ "$COLLECT_ERRORS" -gt 0 ] && echo "  $COLLECT_ERRORS hard collection error(s) reported above (auth / throttle / permission)." >&2
  [ -n "$INVALID" ] && echo "  invalid or empty:$INVALID" >&2
  echo "  Fix credentials/connectivity (e.g. re-run 'aws eks update-kubeconfig', check the profile/region)," >&2
  echo "  then re-run the collection blocks. Scoring against this data would be incorrect." >&2
  exit 1
fi
echo "OK: $(ls "$WORK"/*.json | wc -l | tr -d ' ') files collected and validated. Safe to score."
