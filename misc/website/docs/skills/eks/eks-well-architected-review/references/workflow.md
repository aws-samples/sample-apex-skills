---
title: "Data Collection Reference"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/workflow.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/workflow.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/workflow.md). Edit the source, not this page.
:::

# Data Collection Reference

Collect all cluster data **once** into a work directory with fixed filenames. Every scorer reads these
files, so this is the only step that touches the cluster. Run after identifying the cluster (name, region)
in Step 1 of `SKILL.md`.

**All data stays local. No external services are called.**

> **Hardening note (important).** Collection **fails loudly**. A transient auth blip, throttle, or
> permission error must never be silently turned into empty data — that produces a plausible-looking but
> *wrong* score (e.g. an unreachable data plane scored as "0 nodes"). The helpers below retry transient
> failures, write output only when the call actually succeeds with valid JSON, and abort at the end if any
> required file is missing or the cluster looks unreachable. Genuinely-absent CRDs (Kyverno/Gatekeeper) are
> the *only* thing allowed to fall back to an empty list, and only when the error is specifically
> "resource type not found". **Do not score data that failed this gate.**

Set up the work directory and collection helpers first:

```bash
set -uo pipefail
export WORK="$(pwd)/eks-war-<CLUSTER>"; mkdir -p "$WORK"; : > "$WORK/results.jsonl"
# SKILL_DIR is the skill's own directory, so Steps 7 and 8 can invoke assets/reduce.sh and
# assets/render-report.py from ANY working directory. `python3 assets/render-report.py` only worked
# when the shell happened to be sitting in the skill root, which is not where $WORK is.
#
# It has to be SET, not derived. A fenced block copied into a shell has no file identity --
# ${BASH_SOURCE[0]} is empty -- so deriving the path from this file's own location silently resolves to
# the wrong directory. Step 1 of SKILL.md exports it; this only checks the export happened and points
# somewhere real, because the alternative is discovering it in Step 8 after the whole collection ran.
export SKILL_DIR="${SKILL_DIR:?export SKILL_DIR to the absolute path of the eks-well-architected-review directory (the one containing assets/ and references/) — see SKILL.md Step 1}"
[ -x "$SKILL_DIR/assets/reduce.sh" ] && [ -f "$SKILL_DIR/assets/render-report.py" ] || {
  echo "SKILL_DIR=$SKILL_DIR does not contain assets/reduce.sh and assets/render-report.py." >&2
  echo "Point it at the skill directory itself, not its parent and not \$WORK." >&2
  return 1 2>/dev/null || exit 1; }
# Clear any PREVIOUS run's collection before starting. `awsjson`/`kjson` only ever write on
# success, so a stale file from an earlier run silently satisfies a call that fails this time —
# and the validation gate, whose entire purpose is to refuse un-collected data, then passes on
# data that was never collected. This bites a re-run after any partial failure.
rm -f "$WORK"/*.json
export CLUSTER=<CLUSTER> REGION=<REGION>
export AWS_PAGER=""            # never page
# export AWS_PROFILE=<PROFILE> # uncomment if you use a named profile

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

# kjson_optional <outfile> <kubectl get-args...> : for maybe-absent CRDs. Falls back to an empty
# list ONLY when the resource type does not exist (CRD not installed). Any other error is hard.
kjson_optional() {
  local out="$1"; shift
  local tmp="$out.tmp"
  if kctl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
    mv "$tmp" "$out"; rm -f "$tmp.err"; return 0
  fi
  if grep -qiE "the server doesn't have a resource type|could not find (the )?requested resource|Unknown resource|NotFound" "$tmp.err" 2>/dev/null; then
    echo '{"items":[]}' >"$out"; rm -f "$tmp" "$tmp.err"; return 0   # CRD genuinely absent → empty is correct
  fi
  echo "ERROR: kubectl --context $KCTX get $* failed (not a missing-CRD error): $(firstline "$tmp.err")" >&2
  rm -f "$tmp" "$tmp.err"; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); return 1
}
```

## EKS cluster configuration

```bash
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
[ "$COLLECT_ERRORS" -eq 0 ] || { echo "Aborting collection." >&2; return 1 2>/dev/null || exit 1; }
[ -n "$VPC" ] || { echo "ERROR: could not read VPC id from cluster.json — aborting (cluster describe failed?)" >&2; COLLECT_ERRORS=$((COLLECT_ERRORS+1)); }

# per nodegroup / addon (detail only; not read by scorers, so best-effort with a warning)
for NG in $(jq -r '.nodegroups[]?' "$WORK/nodegroups.json"); do
  aws eks describe-nodegroup --cluster-name "$CLUSTER" --nodegroup-name "$NG" --region "$REGION" --output json > "$WORK/nodegroup-$NG.json" 2>/dev/null \
    || echo "WARN: nodegroup detail $NG not collected (non-fatal)" >&2; done
for A in $(jq -r '.addons[]?' "$WORK/addons.json"); do
  aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$A" --region "$REGION" --output json > "$WORK/addon-$A.json" 2>/dev/null \
    || echo "WARN: addon detail $A not collected (non-fatal)" >&2; done
```

## Kubernetes resources

Cluster-scoped (required — a failure here is what silently produced "0 nodes" before):

```bash
for R in nodes namespaces storageclasses pv clusterroles clusterrolebindings \
         validatingwebhookconfigurations mutatingwebhookconfigurations; do
  kjson "$WORK/$R.json" "$R"; done
```

Namespaced (collected with `-A`, required):

```bash
for R in pods deployments statefulsets daemonsets services ingresses networkpolicies hpa pdb \
         serviceaccounts pvc resourcequotas limitranges cronjobs jobs rolebindings; do
  kjson "$WORK/$R.json" "$R" -A; done
```

Canonical short names used by the scorers (aliases created for convenience):

```bash
ln -sf validatingwebhookconfigurations.json "$WORK/validatingwebhooks.json"
ln -sf mutatingwebhookconfigurations.json "$WORK/mutatingwebhooks.json"
# Kyverno / Gatekeeper policies — optional CRDs; empty only when the CRD is not installed
# EKS Fargate's documented log router is NOT a sidecar. AWS: "you don't explicitly run a Fluent Bit
# container as a sidecar, but Amazon runs it for you. All that you have to do is configure the log
# router" — via a ConfigMap named `aws-logging` in the namespace `aws-observability`. Without collecting
# it, `fargate-4` can never credit a correctly-configured Fargate cluster. Optional-style because its
# absence is a legitimate finding, not a collection failure.
kjson_optional "$WORK/awslogging.json" configmap aws-logging -n aws-observability

kjson_optional "$WORK/kyverno.json"           clusterpolicies.kyverno.io
kjson_optional "$WORK/constraints.json"       constraints -A
kjson_optional "$WORK/constrainttemplates.json" constrainttemplates
```

## AWS infrastructure

```bash
awsjson "$WORK/sg.json"           -- aws ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/subnets.json"      -- aws ec2 describe-subnets         --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/nat.json"          -- aws ec2 describe-nat-gateways     --filter Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/routetables.json"  -- aws ec2 describe-route-tables    --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/vpcendpoints.json" -- aws ec2 describe-vpc-endpoints   --filters Name=vpc-id,Values="$VPC" --region "$REGION" --output json
awsjson "$WORK/instances.json"    -- aws ec2 describe-instances       --filters Name=tag:kubernetes.io/cluster/"$CLUSTER",Values=owned,shared --region "$REGION" --output json
awsjson "$WORK/volumes.json"      -- aws ec2 describe-volumes         --region "$REGION" --output json
awsjson "$WORK/ecr.json"          -- aws ecr describe-repositories    --region "$REGION" --output json
awsjson "$WORK/cloudtrail.json"   -- aws cloudtrail describe-trails   --region "$REGION" --output json
```

## Validation gate (run before scoring)

This is the safeguard: it refuses to let you score incomplete or fabricated data. If it prints
`COLLECTION FAILED`, fix credentials/connectivity and re-run collection — **do not proceed to scoring**.

```bash
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
for r in kyverno constraints constrainttemplates awslogging; do
  [ -f "$WORK/$r.json" ] && jq -e . "$WORK/$r.json" >/dev/null 2>&1 \
    || INVALID="$INVALID $r.json(missing/unparseable; write '{\"items\":[]}' if the CRD is absent)"
done

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
  return 1 2>/dev/null || exit 1
fi
echo "OK: $(ls "$WORK"/*.json | wc -l | tr -d ' ') files collected and validated. Safe to score."
```

## Canonical filenames the scorers read

`cluster.json`, `nodegroups.json`, `addons.json`, `fargate.json`, `podidentity.json`,
`oidcproviders.json`, `nodes.json`, `pods.json`,
`deployments.json`, `statefulsets.json`, `daemonsets.json`, `services.json`, `ingresses.json`,
`networkpolicies.json`, `hpa.json`, `pdb.json`, `namespaces.json`, `serviceaccounts.json`,
`clusterroles.json`, `clusterrolebindings.json`, `rolebindings.json`, `storageclasses.json`, `pvc.json`,
`pv.json`, `resourcequotas.json`, `limitranges.json`, `cronjobs.json`, `jobs.json`,
`validatingwebhooks.json`, `mutatingwebhooks.json`, `kyverno.json`, `constraints.json`,
`constrainttemplates.json`, `sg.json`, `subnets.json`, `nat.json`, `routetables.json`,
`vpcendpoints.json`, `instances.json`, `volumes.json`, `ecr.json`, `cloudtrail.json`.

## Error handling — what counts as absent vs failed

- **Legitimately absent** → empty list / `na` / `none` (correct): a resource type that exists but has
  no objects (kubectl returns `{"items":[]}` with exit 0), or an optional CRD that isn't installed
  (handled by `kjson_optional`). Scorers still apply their `// empty` / `// []` guards on top of this.
- **Failed collection** → hard error, and the validation gate **aborts** before scoring: any `aws`/`kubectl`
  call that exits non-zero after retries (auth expiry, throttling, missing IAM/RBAC permission, network),
  a truncated/invalid-JSON file, a missing `cluster.version`, or an empty `namespaces.json` (a reachable
  cluster always has `kube-system`). These conditions previously slipped through as empty data and skewed
  scores; they now stop the run with a clear message.

## Pillar & analysis references

- [operational-excellence.md](operational-excellence), [reliability.md](reliability),
  [performance-efficiency.md](performance-efficiency), [cost-optimization.md](cost-optimization)
- Security: [identity-access.md](security/identity-access), [data-protection.md](security/data-protection),
  [network.md](security/network), [workload-security.md](security/workload-security),
  [governance-compliance.md](security/governance-compliance)
- [cost-analysis.md](cost-analysis)
