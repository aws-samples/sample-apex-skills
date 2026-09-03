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
# Clear any PREVIOUS run's collection before starting. `awsjson`/`kjson` only ever write on
# success, so a stale file from an earlier run silently satisfies a call that fails this time —
# and the validation gate, whose entire purpose is to refuse un-collected data, then passes on
# data that was never collected. This bites a re-run after any partial failure.
rm -f "$WORK"/*.json
export CLUSTER=<CLUSTER> REGION=<REGION>
export AWS_PAGER=""            # never page
# export AWS_PROFILE=<PROFILE> # uncomment if you use a named profile

COLLECT_ERRORS=0              # incremented on any hard failure; checked by the validation gate

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
    if kubectl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "$out"; rm -f "$tmp.err"; return 0
    fi
    n=$((n+1))
    if [ "$n" -ge 3 ]; then
      echo "ERROR: kubectl get $* failed: $(firstline "$tmp.err")" >&2
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
  if kubectl get "$@" -o json >"$tmp" 2>"$tmp.err" && jq -e . "$tmp" >/dev/null 2>&1; then
    mv "$tmp" "$out"; rm -f "$tmp.err"; return 0
  fi
  if grep -qiE "the server doesn't have a resource type|could not find (the )?requested resource|Unknown resource|NotFound" "$tmp.err" 2>/dev/null; then
    echo '{"items":[]}' >"$out"; rm -f "$tmp" "$tmp.err"; return 0   # CRD genuinely absent → empty is correct
  fi
  echo "ERROR: kubectl get $* failed (not a missing-CRD error): $(firstline "$tmp.err")" >&2
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
# The Kyverno/Gatekeeper CRD files are the ONLY legitimately-empty ones, but they
# must still exist as valid JSON so the scorers can read them.
for r in kyverno constraints constrainttemplates; do
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
