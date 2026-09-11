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

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

Collect all cluster data **once** into a work directory with fixed filenames. Every scorer reads these
files, so this is the only step that touches the cluster. Run after identifying the cluster (name, region)
in Step 1 of `SKILL.md`.

**All data stays local. No external services are called.**

> **Hardening note (important).** Collection **fails loudly**. A transient auth blip, throttle, or
> permission error must never be silently turned into empty data — that produces a plausible-looking but
> *wrong* score (e.g. an unreachable data plane scored as "0 nodes"). The helpers below retry transient
> failures, write output only when the call actually succeeds with valid JSON, and abort at the end if any
> required file is missing or the cluster looks unreachable. Only a short enumerated list of optional
> resources may fall back to an empty list, and only when the error is specifically "resource type not
> found" — the list is in **Why it fails loud** below, kept in one place so the two cannot drift.
> **Do not score data that failed this gate.**

## Run it

```bash
export CLUSTER=<CLUSTER> REGION=<REGION> KCTX=<CLUSTER>
export WORK="$PWD/eks-war-$CLUSTER"
${CLAUDE_SKILL_DIR}/assets/collect.sh
```

**All three lines belong in one Bash call, and the invocation must stay exactly as written.**
`CLUSTER`, `REGION` and `KCTX` are read from `collect.sh`'s environment and it has no default for any of
the three — it exits naming the one that is missing rather than guessing; environment
variables do not survive from one Bash call to the next, but commands in the same call share one shell,
so the `export`s must sit directly above the script. `${CLAUDE_SKILL_DIR}` is substituted by Claude Code
into both the skill body and the Bash rules in `allowed-tools`, which is what lets
`Bash(${CLAUDE_SKILL_DIR}/assets/collect.sh)` match this line without a prompt — a Bash rule matches
literal command text, and quotes are not stripped, so re-quoting or re-spelling the path breaks the
match. `WORK` is optional (`collect.sh` defaults it to `./eks-war-$CLUSTER`); it is set here so the
later steps use the same path.

`assets/collect.sh` **is** the collection. This file documents what it gathers and why; it no longer
carries the commands, because the same text existing in two places is how the two drift apart.

Three reasons it is a script and not a fenced block you paste:

1. **The tool allowlist could not match a pasted block.** Every call went through a retry wrapper
   (`awsjson`, `kjson`, `kctl`), so the command text a permission rule sees begins with the *wrapper*
   name, not `aws` or `kubectl`. Bash permission rules match "everything before the first `*` as
   written", and the wrapper-strip list is fixed (`timeout`, `time`, `nice`, `nohup`, `stdbuf`,
   `command`, `builtin`, `noglob`, `xargs`) — shell functions are not on it. So a carefully narrowed
   allowlist matched almost nothing that actually ran, every line prompted, and the only way to stop the
   prompting was to re-grant `Bash(aws:*)` — restoring the destructive verbs the narrow list existed to
   withhold. One script is one grant, naming a file whose contents ship and can be read.
2. **`bash -n` could not check a pasted block.** The `<PLACEHOLDER>` tokens parse as shell redirects, so
   the shipped collection path had no syntax gate. It has one now — and that gate immediately caught an
   apostrophe inside a `${VAR:?…}` message swallowing a closing brace.
3. **It was duplicated.** The harness concatenated the fenced blocks to test them, so any drift between
   the prose and what was tested was invisible.

## What it collects

Into `$WORK`, one file per resource, canonical filenames the scorers read:

| Source | Files |
|---|---|
| `aws eks` | `cluster`, `nodegroups`, `addons`, `addon-<name>`, `nodegroup-<name>`, `fargate`, `fargateprofiles`, `podidentity` |
| `aws iam` | `oidcproviders` |
| `aws ec2` | `sg`, `subnets`, `nat`, `routetables`, `vpcendpoints`, `instances`, `volumes` |
| `aws ecr` / `cloudtrail` | `ecr`, `cloudtrail` |
| `kubectl` cluster-scoped | `nodes`, `namespaces`, `storageclasses`, `pv`, `clusterroles`, `clusterrolebindings`, `validatingwebhookconfigurations`, `mutatingwebhookconfigurations` |
| `kubectl` namespaced | `pods`, `deployments`, `statefulsets`, `daemonsets`, `services`, `ingresses`, `networkpolicies`, `hpa`, `pdb`, `serviceaccounts`, `pvc`, `resourcequotas`, `limitranges`, `cronjobs`, `jobs`, `rolebindings` |
| `kubectl` ConfigMaps | `awslogging` (`aws-observability/aws-logging` — Fargate's log-router config, read by `fargate-4`), `awsauth` (`kube-system/aws-auth` — the IAM-principal → RBAC-group map, i.e. the cluster-admin path that no ClusterRoleBinding check can see) |
| optional CRDs | `kyverno`, `constraints`, `constrainttemplates` (policy engines); `peerauthentications` (Istio, read by `sec-28`) |

`fargate` is the *list* of profile names; `fargateprofiles` is the merged `describe-fargate-profile`
detail for each name, and it is the only thing that can answer `fargate-1` and `fargate-3`. It is
`{"profiles":[]}` on a cluster with no Fargate profiles.

Two filenames, one collection: `validatingwebhooks.json` and `mutatingwebhooks.json` are plain `cp`
duplicates of `validatingwebhookconfigurations.json` and `mutatingwebhookconfigurations.json`, written
because scorers reference both spellings. The `*configurations.json` files are the collected ones; the
short names are never fetched separately and cannot hold different data.

## Why it fails loud

A transient auth blip, a throttle, or a permission error must never become empty data. An unreachable
data plane scored as "0 nodes" is a plausible-looking wrong answer, which is worse than a refusal.

- **`CLUSTER` and `REGION` are validated before anything is touched.** `$WORK` defaults to
  `$(pwd)/eks-war-$CLUSTER` and the script then clears `"$WORK"/*.json`, so an unvalidated cluster name
  reached a `rm` before EKS's own name check could ever run — `CLUSTER='./../../victim'` resolved `$WORK`
  outside any `eks-war-*` path. `CLUSTER` is now checked against EKS's own rule for
  `create-cluster --name` (alphanumeric start; alphanumerics, hyphens and underscores only; ≤100 chars)
  and `REGION` against a region-code charset, both before `$WORK` is derived. This, not the `Read`/`Edit`
  path globs in `SKILL.md`, is what keeps the work dir where it belongs: a script invoked through a Bash
  grant does its own file I/O, which no file-permission rule reaches. An explicitly exported `$WORK` is a
  caller's deliberate choice and is not path-restricted.
- The work dir is `chmod 700` on every run: the collected JSON carries the account id, IAM role and OIDC
  ARNs, security-group and subnet ids, and cluster tags.
- Required calls retry 3× with backoff and **write only on success with valid JSON**. A failure records a
  hard error; it never fabricates a file.
- Seven files may legitimately be **empty**, and no others: the three policy CRDs
  (`kyverno`, `constraints`, `constrainttemplates`), `peerauthentications` (no Istio), the two optional
  ConfigMaps (`awslogging`, `awsauth`), and `fargateprofiles` (no profiles to describe). For the CRDs and
  the ConfigMaps, empty is allowed only when the error is specifically "resource type not found". All
  seven must still exist and parse as JSON: a scorer aborts on an unopenable input rather than emit a
  truncated pillar.
- A validation gate at the end refuses to hand over the work dir unless every required file exists and
  parses, `cluster.version` is set, and `namespaces.json` is non-empty.
- **Cluster identity is bound.** `KCTX` is mandatory with no default, every `kubectl` call is routed
  through `--context "$KCTX"`, and collection aborts unless the kubeconfig endpoint for that context
  matches `.cluster.endpoint` from `describe-cluster`. Without this, the AWS half and the Kubernetes half
  could describe *different clusters* and still pass every downstream check.

**Do not score data that failed this gate.**
