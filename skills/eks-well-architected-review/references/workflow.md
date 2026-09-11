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
> resources may fall back to an empty document, and only when the error is specifically "the resource
> does not exist" — the list is in **Why it fails loud** below, kept in one place so the two cannot
> drift. An EC2 *list* API that has gone quiet is **not** on that list and never will be; see
> *Auto Mode hides instances and volumes from the list APIs*. **Do not score data that failed this gate.**

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
| `aws ec2` | `sg`, `subnets`, `nat`, `routetables`, `vpcendpoints`, `instances`, `volumes` — the last two are a list call **merged with** an instance-id / volume-id call, see *Auto Mode hides instances and volumes from the list APIs* below |
| `aws ecr` / `cloudtrail` | `ecr`, `cloudtrail` |
| `kubectl` cluster-scoped | `nodes`, `namespaces`, `storageclasses`, `pv`, `clusterroles`, `clusterrolebindings`, `validatingwebhookconfigurations`, `mutatingwebhookconfigurations` |
| `kubectl` namespaced | `pods`, `deployments`, `statefulsets`, `daemonsets`, `services`, `ingresses`, `networkpolicies`, `hpa`, `pdb`, `serviceaccounts`, `pvc`, `resourcequotas`, `limitranges`, `cronjobs`, `jobs`, `rolebindings` |
| `kubectl` ConfigMaps | `awslogging` (`aws-observability/aws-logging` — Fargate's log-router config, read by `fargate-4`), `awsauth` (`kube-system/aws-auth` — the IAM-principal → RBAC-group map, i.e. the cluster-admin path that no ClusterRoleBinding check can see), `vpccniconfig` (`kube-system/amazon-vpc-cni` — the ConfigMap that enables the EKS Auto Mode Network Policy Controller, read by `sec-4`) |
| optional CRDs | `kyverno`, `constraints`, `constrainttemplates` (policy engines); `peerauthentications` (Istio, read by `sec-28`); `nodeclasses` (`nodeclasses.eks.amazonaws.com` — Auto Mode NodeClasses, whose `spec.networkPolicy` and `spec.advancedNetworking.ipv4PrefixSize` are read by `sec-4` and `net-3` rather than assumed) |

`fargate` is the *list* of profile names; `fargateprofiles` is the merged `describe-fargate-profile`
detail for each name, and it is the only thing that can answer `fargate-1` and `fargate-3`. It is
`{"profiles":[]}` on a cluster with no Fargate profiles.

### Auto Mode hides instances and volumes from the list APIs

`eks/latest/userguide/automode-learn-instances.html`: "Beginning April 22, 2026, new Amazon EC2 managed
instances and associated resources (for example, EC2 launch templates, EBS volumes, and network
interfaces (ENIs)) created by EKS Auto Mode are hidden from EC2 console views and `describe` API list
operations by default. Managed resources that already existed in your account before that date remain
visible."

That date is past. A single `describe-instances --filters …` therefore returns **nothing** on an Auto
Mode cluster, and an empty-but-valid document used to sail through collection — so `lens-11` (IMDSv2),
`sec-21` (EBS encryption) and `cost-8` (idle volumes), **weight 3 each**, silently answered `na` off a
zero denominator. Because `na` removes a question from the *denominator*, the cluster nobody could see
scored *better* than one that was fully audited.

`collect.sh` now collects each of the two files twice and merges, deduplicating by `InstanceId` /
`VolumeId` and preserving the `{"Reservations":[…]}` / `{"Volumes":[…]}` shape the scorers read:

- the **list** call, kept because it still finds cluster instances that are not currently nodes (a
  stopped instance, one that never joined, a leftover from a scaled-in nodegroup);
- an **id** call — the same page's remedy, "Direct EC2 API queries by instance ID (for example,
  `describe-instances --instance-ids i-0123456789abcdef0`)" — with instance ids taken from
  `nodes.json` (`spec.providerID`, and the node name, which on Auto Mode *is* the instance id) and
  volume ids from the collected instances' `BlockDeviceMappings[].Ebs.VolumeId` plus `pv.json`'s
  `spec.csi.volumeHandle`. Only `i-…`/`vol-…` shapes are passed: a Fargate `providerID` is a different
  shape and one unusable id fails the whole call. Ids are chunked, because the id form cannot be
  page-sized (`MaxResults`: "You cannot specify this parameter and the instance IDs parameter in the
  same request").

The third documented remedy, "The `DescribeInstances` API with the `include-managed-resources`
parameter", is **not** used: `aws-cli/2.34.30` rejects the flag (`aws: [ERROR]: Unknown options:
--include-managed-resources`) and a skill cannot dictate the operator's CLI version. The account-wide
managed-resource *visibility setting* would also fix this, and is deliberately neither changed nor
suggested as a prerequisite — this skill only looks.

**What this still cannot see, stated plainly.** An Auto Mode EBS volume that is attached to nothing and
backs no PersistentVolume has no id to discover, so it stays invisible and `cost-8` cannot count it. For
node volumes that should not arise — the EKS Auto Mode security whitepaper
(`security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html`): "On EKS Auto Mode nodes, the
root and data Amazon EBS volumes are encrypted and configured to be deleted upon termination of the
instance" — but **`cost-8` reporting no idle volumes on an Auto Mode cluster is not proof that there are
none.** Say so when you report it. Secondly, `cost-8` and `sec-21` scope volumes by cluster *tag*, so an
id-recovered volume carrying no cluster tag is collected and still not counted.

**Absence of an object is a finding; a blind API is not.** These two EC2 calls fail loud (below), while
`vpccniconfig` and `nodeclasses` normalise to an empty document at exit 0. That is not an
inconsistency, it is the whole distinction: nothing changed in a cluster whose EC2 list call went quiet,
whereas a missing `amazon-vpc-cni` ConfigMap really does mean the Network Policy Controller was never
enabled, and no NodeClass really does mean none was ever created. A Forbidden or a connection failure on
either of those two still fails loud — only "the resource does not exist" earns an empty.

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
- Nine files may legitimately be **empty**, and no others: the three policy CRDs
  (`kyverno`, `constraints`, `constrainttemplates`), `peerauthentications` (no Istio), `nodeclasses` (no
  Auto Mode NodeClass CRD), the three optional ConfigMaps (`awslogging`, `awsauth`, `vpccniconfig`), and
  `fargateprofiles` (no profiles to describe). For the CRDs and the ConfigMaps, empty is allowed only
  when the error is specifically "resource does not exist". All nine must still exist and parse as JSON:
  a scorer aborts on an unopenable input rather than emit a truncated pillar.
- **`instances` and `volumes` are not on that list, and the collector enforces it.** If `nodes.json`
  holds non-Fargate nodes and collection still ends with zero EC2 instances, or the collected instances
  and PersistentVolumes reference EBS volumes and `describe-volumes` returned none, that is a collection
  gap and the gate refuses — through the same not-collected mechanism a missing required file uses. It is
  not a finding, because `lens-11`, `sec-21` and `cost-8` would answer `0/0`. A Fargate-only cluster
  legitimately has zero EC2 instances and does not trip this: Fargate nodes are backed by no instance.
- A validation gate at the end refuses to hand over the work dir unless every required file exists and
  parses, `cluster.version` is set, and `namespaces.json` is non-empty.
- **Cluster identity is bound.** `KCTX` is mandatory with no default, every `kubectl` call is routed
  through `--context "$KCTX"`, and collection aborts unless the kubeconfig endpoint for that context
  matches `.cluster.endpoint` from `describe-cluster`. Without this, the AWS half and the Kubernetes half
  could describe *different clusters* and still pass every downstream check.

**Do not score data that failed this gate.**
