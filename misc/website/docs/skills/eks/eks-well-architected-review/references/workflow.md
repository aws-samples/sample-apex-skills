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

**Collected files are written only to the work directory, and the rendered report makes no network
requests.** Collection calls the AWS and Kubernetes APIs, and whatever this review prints or reads
(cluster ARNs, the account id, scores, findings) enters the conversation like any other tool output.

> **Hardening note (important).** Collection **fails loudly**. A transient auth blip, throttle, or
> permission error must never be silently turned into empty data — that produces a plausible-looking but
> *wrong* score (e.g. an unreachable data plane scored as "0 nodes"). The collector's helpers retry transient
> failures, write output only when the call actually succeeds with valid JSON, and abort at the end if any
> required file is missing or the cluster looks unreachable. Only a short enumerated list of optional
> resources may fall back to an empty document, and only when the error is specifically "the resource
> does not exist" — the list is in **Why it fails loud** below, kept in one place so the two cannot
> drift. An EC2 *list* API that has gone quiet is **not** on that list and never will be; see
> *Auto Mode hides instances and volumes from the list APIs*. **Do not score data that failed this gate.**

## Table of Contents

1. [Run it](#run-it)
2. [What it collects](#what-it-collects)
   - [Auto Mode hides instances and volumes from the list APIs](#auto-mode-hides-instances-and-volumes-from-the-list-apis)
3. [Why it fails loud](#why-it-fails-loud)
4. [What counts as "an EKS cluster" here](#what-counts-as-an-eks-cluster-here)
5. [Read-only, grants and the work directory](#read-only-grants-and-the-work-directory)
6. [Why parameters are arguments](#why-parameters-are-arguments)
7. [Permission preflight and the read-only IAM policy](#permission-preflight-and-the-read-only-iam-policy)
8. [Which surfaces are machine-generated](#which-surfaces-are-machine-generated)
9. [Step 1 detail: binding the review to one cluster](#step-1-detail-binding-the-review-to-one-cluster)
10. [Step 2 detail: the kubeconfig, the parameters, the work directory and the exit status](#step-2-detail-the-kubeconfig-the-parameters-the-work-directory-and-the-exit-status)
11. [Step 3 detail: the seven mode labels, and why the numbers set no flags](#step-3-detail-the-seven-mode-labels-and-why-the-numbers-set-no-flags)
12. [Step 4 detail: why the gates are shaped this way](#step-4-detail-why-the-gates-are-shaped-this-way)
13. [Step 5 detail: the `resources` key](#step-5-detail-the-resources-key)
14. [Step 5 detail: how `score.sh` runs the scorer blocks, and why there is no drift detection](#step-5-detail-how-scoresh-runs-the-scorer-blocks-and-why-there-is-no-drift-detection)
15. [Step 7 detail: `-o`, four more refusals, and where severity lives](#step-7-detail--o-four-more-refusals-and-where-severity-lives)
16. [Step 8 detail: themes, the internal report, resource lists and what the renderer reads](#step-8-detail-themes-the-internal-report-resource-lists-and-what-the-renderer-reads)
17. [Step 8 detail: if the renderer exits non-zero](#step-8-detail-if-the-renderer-exits-non-zero)
18. [Markdown-only report](#markdown-only-report)
19. [Scoring model detail: buckets, states, bands and pillar weights](#scoring-model-detail-buckets-states-bands-and-pillar-weights)
20. [Platform-credited answers](#platform-credited-answers)
21. [Report content read from SKILL.md and from this file](#report-content-read-from-skillmd-and-from-this-file)

---

## Run it

```bash
${CLAUDE_SKILL_DIR}/assets/collect.sh --cluster <CLUSTER> --region <REGION> --context <CLUSTER> \
  --work "$PWD/eks-war-<CLUSTER>" [--profile <PROFILE>]
```

**The invocation must stay exactly as written.** `--cluster`, `--region` and `--context` are required —
`collect.sh` has no default for any of the three and exits naming the one that is missing rather than
guessing. They are arguments rather than exported variables so the workflow needs no `export` grant at
all; see *Why parameters are arguments* below. The same three are also read from the environment
(`CLUSTER`/`REGION`/`KCTX`) when the flags are omitted. `${CLAUDE_SKILL_DIR}` is substituted by Claude Code
into both the skill body and the Bash rules in `allowed-tools`, which is what lets
`Bash(${CLAUDE_SKILL_DIR}/assets/collect.sh)` match this line without a prompt — a Bash rule matches
literal command text, and quotes are not stripped, so re-quoting or re-spelling the path breaks the
match. `WORK` is optional (`collect.sh` defaults it to `./eks-war-$CLUSTER`); it is set here so the
later steps use the same path.

`assets/collect.sh` **is** the collection. This file documents what it gathers and why; it does not
carry the commands, because the same text existing in two places is how the two drift apart.

Three reasons it is a script and not a fenced block you paste:

1. **The tool allowlist cannot match a pasted block.** Every call goes through a retry wrapper
   (`awsjson`, `kjson`, `kctl`), so the command text a permission rule sees begins with the *wrapper*
   name, not `aws` or `kubectl`. Bash permission rules match "everything before the first `*` as
   written", and the wrapper-strip list is fixed (`timeout`, `time`, `nice`, `nohup`, `stdbuf`,
   `command`, `builtin`, `noglob`, `xargs`) — shell functions are not on it. So a carefully narrowed
   allowlist would match almost nothing that actually runs, every line would prompt, and the only way to
   stop the prompting would be to re-grant `Bash(aws:*)` — restoring the destructive verbs the narrow list
   exists to withhold. One script is one grant, naming a file whose contents ship and can be read.
2. **`bash -n` cannot check a pasted block.** The `<PLACEHOLDER>` tokens parse as shell redirects, so
   a pasted collection path has no syntax gate. The script has one: `bash -n` catches, for example, an
   apostrophe inside a `${VAR:?…}` message swallowing a closing brace.
3. **A pasted block would be a second copy.** The prose and the commands that actually run would drift
   apart, and nothing would show it.

## What it collects

Into `$WORK`, one file per resource, canonical filenames the scorers read:

| Source | Files |
|---|---|
| `aws eks` | `cluster`, `nodegroups`, `addons`, `fargate`, `fargateprofiles`, `podidentity`, `insights` — `addons` carries merged per-object detail, see below |
| `aws iam` | `oidcproviders` |
| `aws ec2` | `sg`, `subnets`, `nat`, `routetables`, `vpcendpoints`, `instances`, `volumes` — the last two are a list call **merged with** an instance-id / volume-id call, see *Auto Mode hides instances and volumes from the list APIs* below |
| `aws ecr` / `cloudtrail` | `ecr`, `cloudtrail` |
| `kubectl` cluster-scoped | `nodes`, `namespaces`, `storageclasses`, `pv`, `clusterroles`, `clusterrolebindings`, `validatingwebhookconfigurations`, `mutatingwebhookconfigurations` |
| `kubectl` namespaced | `pods`, `deployments`, `statefulsets`, `daemonsets`, `services`, `ingresses`, `networkpolicies`, `hpa`, `pdb`, `serviceaccounts`, `pvc`, `resourcequotas`, `limitranges`, `cronjobs`, `jobs`, `rolebindings` |
| `kubectl` ConfigMaps | `awslogging` (`aws-observability/aws-logging` — Fargate's log-router config, read by `fargate-4`), `awsauth` (`kube-system/aws-auth` — the IAM-principal → RBAC-group map, i.e. the cluster-admin path that no ClusterRoleBinding check can see), `vpccniconfig` (`kube-system/amazon-vpc-cni` — the ConfigMap that enables the EKS Auto Mode Network Policy Controller, read by `sec-4`) |
| optional CRDs | `kyverno`, `constraints`, `constrainttemplates` (policy engines); `nodeclasses` (`nodeclasses.eks.amazonaws.com` — Auto Mode NodeClasses, whose `spec.networkPolicy` and `spec.advancedNetworking.ipv4PrefixSize` are read by `sec-4` and `net-3` rather than assumed) |

`fargate` is the *list* of profile names; `fargateprofiles` is the merged `describe-fargate-profile`
detail for each name, and it is the only thing that can answer `fargate-1` (`rel-1` and `lens-14` also read the profiles' subnets from it). It is
`{"profiles":[]}` on a cluster with no Fargate profiles.

`nodegroups.json` is the name list from `list-nodegroups` (`.nodegroups`) and nothing more; no
`describe-nodegroup` detail is collected. **`addons.json` follows the same two-part shape** as the Fargate
files, in one file — `.addons` is the name list, `.addonDetails` every `describe-addon` response — which is what
lets `lens-7` read `addonVersion`, `status` and `health.issues` instead of answering from the name alone.
`addons.json` also carries `.addonTargets`, one entry per installed add-on holding the versions EKS offers
for this cluster's Kubernetes version plus that add-on's `defaultVersion`. **No order is promised or
relied on**: `lens-7` measures currency by parsing `vMAJOR.MINOR.PATCH[-eksbuild.N]` and comparing
tuples, not by list position. Comparing positions would silently assume the API returns
newest-first and report the index distance as a release count — the list interleaves `-eksbuild.N`
rebuilds, so that count would overstate the gap several-fold. `insights.json` is
`aws eks list-insights`, the upgrade-readiness checks EKS recomputes daily from the control-plane audit
logs, graded by `ope-20`.
A scorer can only name a *fixed* filename, and `addon-<name>.json` is variable, so those per-object
files are **not written**: their content would be byte-identical to the matching merged entry, and the
merged array is the only form a scorer can read. A name present in `.addons` with no matching
`.addonDetails` entry is a collection gap and the collector refuses over it.

### Auto Mode hides instances and volumes from the list APIs

`eks/latest/userguide/automode-learn-instances.html`: "Beginning April 22, 2026, new Amazon EC2 managed
instances and associated resources (for example, EC2 launch templates, EBS volumes, and network
interfaces (ENIs)) created by EKS Auto Mode are hidden from EC2 console views and `describe` API list
operations by default. Managed resources that already existed in your account before that date remain
visible."

That date is past. A single `describe-instances --filters …` therefore returns **nothing** on an Auto
Mode cluster, and an empty-but-valid document would sail through collection — so `lens-11` (IMDSv2),
`sec-21` (EBS encryption) and `cost-8` (idle volumes), **weight 3 each**, would silently answer `na` off a
zero denominator. Because `na` removes a question from the *denominator*, the cluster nobody could see
would score *better* than one that was fully audited.

`collect.sh` therefore collects each of the two files twice and merges, deduplicating by `InstanceId` /
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
(`whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html`): "On EKS Auto Mode nodes, the
root and data Amazon EBS volumes are encrypted and configured to be deleted upon termination of the
instance" — but **`cost-8` reporting no idle volumes on an Auto Mode cluster is not proof that there are
none.** Say so when you report it. Secondly, `cost-8` scopes volumes by cluster *tag* or PersistentVolume, so an
id-recovered volume that only a node attachment ties to the cluster is collected and not counted there (attached, it could only pass); `sec-21` also counts a volume attached to one of the cluster's EC2 nodes, so it leaves out only an untagged volume that no PV names and no node holds.

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

**The exit status distinguishes the two kinds of refusal.** `2` is a usage error, `3` means the *cluster*
is permanently out of scope (an EKS Connector cluster — see below), and `1` is everything else: a refusal
about *this run*, which a re-authentication, a policy, a different `--work` path or a corrected
`--context` can clear. *Step 2 detail* below carries the same table for the agent.

- **An EKS Connector cluster is refused in the preflight, before anything is collected.** A cluster
  *registered* with EKS through the Connector is someone else's conformant Kubernetes cluster made visible
  in the EKS console; AWS does not run its control plane, and `describe-cluster` returns `name`, `arn`,
  `createdAt`, `status`, `tags` and `connectorConfig` but no `version`, `resourcesVpcConfig`, `logging`,
  `encryptionConfig` or `computeConfig`. Scoring it would report each of those absences as a
  misconfiguration, so the refusal exits `3` and names the one call that tells the two kinds apart.
  **It is detected in the permission preflight, which calls `eks:DescribeCluster` anyway**, and that
  placement is the whole point. Checked after collection begins, it would never fire on the documented
  workflow: `aws eks update-kubeconfig` *succeeds* on a
  Connector cluster, writing `certificate-authority-data: ""` and `server: null`, so `kubectl` falls back
  to `localhost:8080`, all 27 Kubernetes probes go UNKNOWN, and the Kubernetes-half refusal would exit
  first with three likely causes that are all false — one of them advising the `update-kubeconfig` that
  has just succeeded. It would also have written `cluster.json` before refusing, which is exactly the
  "unfinished collection" marker the work-directory guard refuses on, so a second run of the identical
  command would report an interrupted collection and lose the only message that matters. The same check remains
  after `describe-cluster` is collected as a backstop for the one case that can still reach it — the
  preflight's own probe not settling — and that copy says which file it left behind.
- **`CLUSTER` and `REGION` are validated before `$WORK` is derived from them.** `$WORK` defaults to
  `$(pwd)/eks-war-$CLUSTER`, so an unvalidated cluster name would decide where the script writes —
  `CLUSTER='./../../victim'` would resolve `$WORK` outside the intended tree. `CLUSTER` is checked against
  EKS's own rule for `create-cluster --name` (alphanumeric start; alphanumerics, hyphens and underscores
  only; ≤100 chars) and `REGION` against a region-code charset, both before `$WORK` is derived. This, not
  the `Read`/`Edit` path globs in `SKILL.md`, is what keeps the work dir where it belongs: a script
  invoked through a Bash grant does its own file I/O, which no file-permission rule reaches.
- **Nothing is ever deleted, and only a previous run's output is refused.** `$WORK` may sit beside
  unrelated files (any `*.json` inside `$WORK` must be valid JSON other than null/false); it is refused when it already holds `.collection.json` (a **completed** collection),
  `cluster.json` without it (an **unfinished** one — `cluster.json` is the first file any run writes), or a
  **non-empty** `results.jsonl` (scored output); also when it is `/`, `$HOME`, or not a directory. The
  refusal names which of the three it found, because they mean different things. The reason is that the
  script does not clear anything: a stale file from an earlier run would otherwise satisfy a call that
  fails this time, and the validation gate would pass on data that was never collected. Re-running a
  cluster means moving the old directory aside or passing a new `--work` path.
  An **empty** `results.jsonl` is deliberately not a marker. `collect.sh` does not create one, and a
  refusal keyed on that file's mere presence would let a run that fails partway leave behind a marker
  (if anything created it) that blocks its own retry — citing a file holding nothing. `score.sh` appends
  with `>>` and tolerates an absent file, so nothing needs the file created before
  scoring.
- A work dir the script creates is `chmod 700`; one a caller pre-created is left at the mode they chose.
  Either way `umask 077` lands every file owner-only — the collected JSON carries the account id, IAM role
  and OIDC ARNs, security-group and subnet ids, and cluster tags.
- Required calls retry 3× with backoff and **write only on success with valid JSON**. A failure records a
  hard error; it never fabricates a file.
- Eight files may legitimately be **empty**, and no others: the three policy CRDs
  (`kyverno`, `constraints`, `constrainttemplates`), `nodeclasses` (no Auto Mode NodeClass CRD), the three optional ConfigMaps (`awslogging`, `awsauth`, `vpccniconfig`), and
  `fargateprofiles` (no profiles to describe). For the CRDs and the ConfigMaps, empty is allowed only
  when the error is specifically "resource does not exist". All eight must still exist and parse as JSON:
  a scorer aborts on an unopenable input rather than emit a truncated pillar.
- **`instances` and `volumes` are not on that list, and the collector enforces it.** If `nodes.json`
  holds non-Fargate nodes and collection still ends with zero EC2 instances, or with any such node's
  instance missing from `instances.json`, or with any EBS volume id the collected instances and
  PersistentVolumes reference missing from `volumes.json`, that is a collection gap and the gate refuses
  — through the same not-collected mechanism a missing required file uses. The only ids exempt are the
  ones EC2 answered as not existing (a Node or PersistentVolume briefly outliving its instance or volume).
  It is not a finding, because `lens-11`, `sec-21` and `cost-8` would answer `0/0` or grade a subset as if
  it were the whole fleet. A Fargate-only cluster
  legitimately has zero EC2 instances and does not trip this: Fargate nodes are backed by no instance.
- A validation gate at the end refuses to hand over the work dir unless every required file exists and
  parses, `cluster.version` is set, and `namespaces.json` is non-empty.
- **Cluster identity is bound.** `KCTX` is mandatory with no default, every `kubectl` call is routed
  through `--context "$KCTX"` (and `--cache-dir "$WORK/.kube-cache"`, so kubectl's own cache stays in the
  work dir rather than `~/.kube/cache`, plus `--kubeconfig` when one is passed — SKILL.md Step 1 writes it
  into the work dir), and collection aborts unless the kubeconfig's trust material for that
  context **contains** the CA `describe-cluster` reports in `.cluster.certificateAuthority.data`. AWS
  creates a CA for each EKS cluster, so a CA match identifies the cluster; an endpoint URL identifies only
  the route, so comparing URLs would refuse every legitimate indirection — SSM tunnel,
  `kubectl proxy`, `/etc/hosts`, egress proxy — including the private-endpoint posture `sec-2` rewards.
  **The comparison is containment, per certificate, not equality of the whole file** — AWS's CA-rotation
  guidance is that clients should "trust a CA bundle rather than pin to a single CA certificate", because
  during a rotation's dual trust period the bundle legitimately carries two CAs. Requiring byte-equality
  would pin a single CA and refuse a healthy cluster mid-rotation as "two different clusters"; EKS
  rotates automatically if you do not. Same cluster by another route is accepted with a note, a bundle
  carrying the cluster's CA is accepted with a note naming the count, and a different cluster is still
  refused — including a two-CA bundle belonging to one. Relaxing the route costs nothing, because
  `kubectl` performs its own TLS handshake against that CA on every call — this check stops the review
  grading the wrong cluster, it does not secure the transport. Without this, the AWS half and the
  Kubernetes half could describe *different clusters* and still pass every downstream check.

**Do not score data that failed this gate.**

## What counts as "an EKS cluster" here

**Explicitly out of scope, and not silently.** This block is report content too — `render-report.py`
prints it beside the other boundary disclosures, so the reader of the HTML sees the same platform scope
you do:

<!-- SCOPE-PLATFORMS:BEGIN — read verbatim by assets/render-report.py. One `- ` bullet per platform;
     continuation lines indented two spaces; `**bold**` and `` `code` `` only, no other markup. -->
- **Judged: Amazon EKS on AWS only** — both compute modes, in any mix. EKS Auto Mode
  (`computeConfig.enabled`) and EC2 compute: managed node groups, self-managed nodes and Fargate
  profiles. A cluster combining Auto Mode with EC2 node groups is **mixed-mode**, and several questions
  have a dedicated mixed-mode branch so they describe both node populations instead of crediting one and
  ignoring the other.
- **Not judged: Windows nodes** — this skill supports Linux nodes only. A Windows node (label
  `kubernetes.io/os=windows`, or the kubelet's reported operating system when that label is absent) is
  excluded from every question that judges a node population: it leaves the numerator and the
  denominator alike, and wherever any were excluded the detail says how many, so no ratio shrinks
  silently. Pods that declare Windows — `spec.os.name`, a nodeSelector of `windows` on `kubernetes.io/os` or the deprecated `beta.kubernetes.io/os`, any `node.kubernetes.io/windows-build` nodeSelector, or a
  required node affinity in which one term admits Windows nodes and no term admits a Linux node, read on those
  three labels (preferred affinity does not count), on the pod or on its DaemonSet's pod template — are
  excluded from the pod questions the same way. A question whose whole population was Windows answers Not Applicable,
  marked **NOT ASSESSED**, never a pass. Nothing about a Windows node is assessed: not its AMI, its hardening, GMSA, or the Windows parts of the CNI.
- **Judged, with the node population partitioned: EKS Hybrid Nodes** (`remoteNetworkConfig`) —
  on-premises or other-cloud machines joined to an EKS control plane. A hybrid node is not an EC2
  instance, so it is not in the **EC2 denominator** of any node-scoped question. Where a question grades
  a property of *nodes*, hybrid nodes are named separately and never called EC2 nodes — `ope-15` excludes
  them from its denominator and its detail says so, and `ope-7` lists them only as context.
  A node counts as EC2 when it is neither Fargate nor hybrid. **Hybrid is not
  the label OR the `providerID`.** The `providerID` **decides** and the label only breaks a tie:
  `eks-hybrid:` means hybrid, an `aws:` `providerID` **vetoes** the label, and the label
  (`eks.amazonaws.com/compute-type=hybrid`) is read only when no `providerID` contradicts it. That
  asymmetry matters: `nodeadm` writes the `providerID`, while the label is an ordinary
  label anyone with node-patch RBAC can set, so under OR the mutable signal alone would be enough: labelling
  two real EC2 nodes `compute-type=hybrid` would drop them out of every node question and turn `lens-14`'s
  NAT-redundancy failure into a pass.
- **What a hybrid node is NOT judged on, and why each is Not Applicable rather than a failure.** `rel-1`
  (**High**): an on-premises machine has no AWS Availability Zone, so that question instead grades the
  `topology.kubernetes.io/zone` fault domains the operator declares from the kubelet, and says so when
  none are set. `ope-15`: a hybrid node joins through a `HYBRID_LINUX` access entry and cannot be placed
  in a managed node group, so an **all**-hybrid fleet is `na` — no node lifecycle there for AWS to take
  over. On a **mixed** fleet the question still counts it, in a denominator of *nodes*: `4/8 node(s) have
  an AWS-managed node lifecycle` names both populations rather than crediting the Auto Mode half and
  dropping the other. `rel-4`: neither Cluster Autoscaler nor Karpenter can create or remove one.
  `perf-3`, `perf-6`, `lens-6`: there is no instance type to read a generation from or diversify, and AWS
  publishes no EKS-optimized AMI for a hybrid node. `lens-14`: it does not egress through this VPC.
  `ope-10`, `lens-7`, `sec-4`, `net-3`: the Amazon VPC CNI is not compatible with hybrid nodes and its
  `aws-node` DaemonSet carries anti-affinity for the hybrid label, so there is no VPC CNI on one to read
  a version, a network-policy agent or a prefix-delegation setting from. `ope-2` and `sec-21`: Amazon EBS
  volumes and the EBS CSI driver are not compatible either, so block storage leaves `ope-2`'s denominator
  and `sec-21` states that hybrid nodes are outside its volume measurement.
- **What a hybrid node IS still judged on.** Everything that is not about being an EC2 instance. `ope-7`,
  `ope-8`, `lens-1` and `lens-2` ask whether a DaemonSet exists, and a DaemonSet does schedule onto a
  hybrid node, so those are graded normally; of the four only `ope-7` publishes an evidence list, and there
  each hybrid node is labelled `(EKS Hybrid Node)` rather than dropped. `ope-16` grades the two core
  add-ons that apply (`coredns`, `kube-proxy`) out of two rather than three. `sec-30` still runs its
  security-group measurement and reports the hybrid nodes **NOT ASSESSED** inside it — a hybrid node has
  no EC2 security group, so no rule in that measurement governs SSH to it; its `sshd` is real and is
  yours to restrict. Every control-plane, RBAC, workload and governance question is unaffected.
- **Auto Mode plus hybrid nodes is its own shape, and the all-Auto-Mode shortcuts do not fire on it.**
  Several questions short-circuit when *every* EC2 node is an EKS Auto Mode node, on the grounds that AWS
  then owns the thing being asked about. Removing hybrid nodes from the EC2 denominator makes that
  condition **easier** to satisfy, so each of those gates additionally requires that there be no hybrid
  node — otherwise a cluster with two on-premises machines would be graded as if AWS managed every node
  on it. The report header
  also names the combination (`EKS Auto Mode + EKS Hybrid Nodes`) rather than just `EKS Auto Mode`.
- **An all-hybrid cluster can sit right at Operational Excellence's coverage gate.** That gate is per
  pillar: where fewer than half a pillar's questions are applicable (`$ac*2 < $tot`) that pillar reports
  `INSUFFICIENT` in place of a number, and several Operational Excellence questions are `na` on hybrid
  nodes. If Operational Excellence goes `INSUFFICIENT`, the headline score is not withheld — it becomes
  the equal-weight average of the four pillars that remain. Two pillars short of a number is what
  withholds the overall.
- **On a mixed cluster the EC2 nodes are graded and the hybrid count is disclosed.** Where hybrid nodes
  left a denominator, the detail says how many were excluded, so a reader never sees a ratio that
  silently shrank. **What is still not judged at all:** the CNI a hybrid node actually runs (Cilium or
  Calico), its storage, its host OS patch level, and any fault domain beyond the labels the operator
  chose to set — none of those is collected. Such a cluster is **not refused**.
- **Not judged: EKS Anywhere** — a different product with its own control plane, not a cluster in an AWS
  account. `aws eks describe-cluster` has nothing to return, so collection cannot reach one.
- **Not judged: EKS Connector clusters** (`connectorConfig`) — a conformant Kubernetes cluster running
  elsewhere, *registered* with EKS for console visibility rather than run by it. `describe-cluster`
  returns no `version`, `resourcesVpcConfig`, `logging`, `encryptionConfig` or `computeConfig`, so
  scoring one would report those absences as misconfiguration. `collect.sh` refuses such a cluster up
  front — normally before it has collected anything — rather than publishing that.
<!-- SCOPE-PLATFORMS:END -->

## Read-only, grants and the work directory

> **Nothing is deleted, locally either.** `collect.sh` collects into one directory and leaves it alone:
> the collected JSON, `results.jsonl`, `scores.json`, `report.html` and every scratch file the scripts
> write all land there and stay. Step 1 creates that directory owner-only (`mkdir -p -m 700`); `collect.sh`
> creates it only if it is missing, and `chmod 700`s it only then. It **refuses** rather than collect into one that already holds a previous run's
> output — see **the work directory** below. No script here calls `rm`, `unlink` or any other deletion: when writing the report fails, `render-report.py` leaves its half-written `<report>.part` in place and names it in the error. Two steps do overwrite their own output when re-run on the same path: `reduce.sh -o` rewrites `scores.json`, and `render-report.py` truncates its `<report>.part` and moves it over the previous report (`os.replace`).
>
> **`allowed-tools` grants four scripts and the handful of bare `aws`/`kubectl`/`jq`
> commands and the one `mkdir` the workflow runs directly — no other Bash.** The bulk of the work happens inside
> `assets/collect.sh`, `assets/score.sh`, `assets/reduce.sh` and `assets/render-report.py`, all of which
> ship and can be read before you approve them. That is the point: one reviewable grant per script beats
> a long list of command prefixes.
>
> **Requires `jq` 1.6 or newer.** `collect.sh` refuses up front if the `jq` on PATH lacks `IN` or `walk`,
> both 1.6 builtins that `reduce.sh`'s gates and the policy-engine detections use. It probes the builtins
> rather than parsing `jq --version`, because distributions backport and rename — Amazon Linux 2 ships
> `jq-1.5` alongside 1.6. Without the check the symptom is a single scorer aborting mid-review, several
> steps from the cause.
>
> `allowed-tools` **grants; it never restricts.** A command it does not cover is not blocked — it falls
> through to the normal permission flow, which prompts in the interactive modes and is denied outright in
> `dontAsk`, where an unattended run lives. So an unmatched command in this workflow is a bug, not a
> safety feature. Every command in SKILL.md's steps is written in the form its grant spells, with one
> disclosed exception — the Step 5 scorer blocks, at the end of this section.
>
> Do not widen it to `Bash(aws:*) Bash(kubectl:*)`: that pre-authorises `delete-cluster` and `kubectl
> delete` on a cluster the operator may well believe is only being looked at. A list of narrow
> `Bash(aws eks describe-cluster:*)`-style grants over pasted collection commands looks safer but is
> **worse in practice**: collection runs through retry wrappers, so the command text a permission rule
> sees begins with the wrapper name, the narrow grants match almost nothing, every call prompts, and the
> only escape from the prompting is to re-grant `Bash(aws:*)`. A guard that produces prompt fatigue is a
> guard that gets switched off.
>
> **The script paths are `${CLAUDE_SKILL_DIR}` in the grant and `${CLAUDE_SKILL_DIR}` in SKILL.md's body, and
> that identity is the whole mechanism.** Claude Code substitutes `${CLAUDE_SKILL_DIR}` in two places —
> the skill's markdown content and the Bash rules in `allowed-tools` — precisely so a skill can run a
> bundled script without a prompt. Both sides expand to the same absolute path, so the rule matches the
> command SKILL.md's body tells you to run. Keep them character-identical: a Bash rule matches literal command
> text, and quotes are not stripped (`Bash(git push *)` does not match `git 'push' origin main`), so
> re-quoting or re-spelling an invocation stops it matching and puts the prompt back. Both sides are
> written unquoted, which is the form the documented example uses; a skill directory path containing a
> space would still word-split once the shell has it. The substitution applies to Bash rules only, which
> is why the `Read`/`Edit` rules below use a path glob rather than the variable.
>
> **`Read`/`Edit` are scoped too.** `Read` covers the skill's own tree, to load `references/`, and any
> directory whose name starts `eks-war-`, anywhere on the path, with everything below it: the work dir
> and its collected JSON, but equally any other directory so named, a checkout of this skill included.
> `Edit` covers only one file name directly inside such a directory — `analysis.md` (Step 8), the one
> file SKILL.md's body has you write — so it reaches neither the collected
> JSON nor a checkout's `assets/` and `references/`. Granted bare, they would
> authorise every file the process can reach, `~/.aws/credentials` and `~/.ssh` included, inside a
> frontmatter whose whole argument is narrow grants. `Edit`, not `Write`: Claude Code checks file
> permissions against `Edit(path)` and `Read(path)` rules only, accepts a `Write(path)` rule without
> ever consulting it, and warns about it at startup — so a `Write(//**/eks-war-*/**)` rule on this line
> would do nothing at all.
>
> **Those four rules scope the native `Read`/`Write`/`Edit` tools, and nothing else.** A script invoked
> through a Bash grant does its own file I/O as a subprocess, which no `Read`/`Edit` rule reaches: what
> `collect.sh` writes and where `render-report.py -o` writes are decided inside those programs, not by
> the glob. So a work dir renamed off `eks-war-*` does **not** prompt — `collect.sh` still writes it.
> **Confinement of the work dir is therefore `collect.sh`'s own job, and it does both halves:** it
> validates `$CLUSTER` before that name is used to build `$WORK` — an unvalidated `$CLUSTER` would itself be
> the escape, since `$WORK` is derived from it — and it validates the resulting `$WORK`, however it
> arrived (`--work`, an exported `WORK`, or the default), before creating or `chmod`-ing it. That second
> half compares against `/` and `$HOME` **canonically**, not as strings. A string compare would refuse
> `--work "$HOME"` and nothing else: `--work "$HOME/"`, `"$HOME/."`, `"$HOME/x/.."`, a symlink pointing
> at `$HOME`, and a bare `--work .` run from `$HOME` would all spell their way past it and write the
> collection into the home directory the check exists to protect. `collect.sh` *clears* nothing and
> deletes nothing. Its own working files — the preflight's `.eks-war-preflight.XXXXXX/` directory, kubectl's
> `.kube-cache/` (every `kubectl` call it makes passes `--cache-dir` there), each
> call's `.tmp`/`.err`, the `.ng`/`.ad`/`.av`/`.fp` merge scratch, `.collection.json.tmp` — stay in `$WORK`.
> Each is a dot-name or ends in `.tmp`/`.err`, so no `*.json` glob in the collector matches it; `reduce.sh`
> and `render-report.py` open only files they name; and none is one of the three markers the work-dir
> guard refuses on, so a leftover blocks no retry. See WORK DIRECTORY in `collect.sh`. Two of
> the grants above are the wide ones and it is worth naming them:
> `Bash(jq:*)` can read any file this process can reach, and `render-report.py -o` can write anywhere
> the process can write. Both are read-then-write-one-file tools rather than destructive verbs, but
> "narrow grants" describes the `aws`/`kubectl` list, not these. Two specifics worth stating rather than
> leaving to be discovered: `jq -n '$ENV'` prints the whole environment, so under environment-variable
> credentials `Bash(jq:*)` reads `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` — and any other secret
> the calling agent happens to carry — without a further prompt; "can read any file" understates it. And
> the skill's own `jq` use is a fixed set SKILL.md's body names (Step 3, Step 7, and the expressions in
> `references/cost-analysis.md` that Step 5 runs); the scorer blocks' `jq` is not part of that set,
> because those run inside `score.sh` under its own grant rather than being pasted into a shell.
>
> `aws eks update-kubeconfig` writes only to a local kubeconfig, never to AWS. Step 1 passes it
> `--kubeconfig eks-war-<CLUSTER>/kubeconfig`, so it writes a kubeconfig inside the work directory and
> leaves the shared `~/.kube/config` untouched. The grant is `Bash(aws eks update-kubeconfig:*)`, so it
> authorises any `--kubeconfig <path>`: it can write a YAML file anywhere this process can write, and
> without the flag it writes `~/.kube/config`, overwriting an existing context of the same `--alias`.
> `Bash(mkdir -p -m 700 eks-war-*)` creates the work directory owner-only in Step 1, before anything is
> written into it; it matches on that prefix, so it can create any directory whose first argument starts
> `eks-war-`, and further arguments after it.
>
> **Where a run writes: inside the work directory, and nowhere else.** Step 1 creates it, the kubeconfig
> and kubectl's cache (`--cache-dir eks-war-<CLUSTER>/.kube-cache`) go into it, and every `kubectl` call
> `collect.sh` makes passes the same `--kubeconfig` and `--cache-dir`. The expected exception is the AWS
> CLI's own cache: the `aws` CLI — both the skill's own `aws` calls and the `aws eks get-token` that the
> kubeconfig's `exec` block runs for every `kubectl` call — may write under `~/.aws/cli/cache` (any call,
> whatever the credential type, once that directory exists) and `~/.aws/sso/cache` for SSO profiles. That
> is the AWS CLI's own state, not a file of this review, and nothing in the skill redirects it.
>
> **The work directory: one folder, created fresh, never cleared.** `$WORK` defaults to
> `./eks-war-$CLUSTER` and holds everything this review produces. It may sit **beside unrelated files** —
> the skill itself, notes, whatever you keep there (any `*.json` inside `$WORK` must be valid JSON other than null/false). `collect.sh` refuses, naming the path and the rule,
> only when `$WORK` already holds **output from a previous run of this review**, and when it is `/`, your
> `$HOME`, or an existing non-directory. It never deletes. Three markers, and the refusal says which one
> it found, because the three mean different things: `.collection.json` (written only at the very end) is
> a **completed** collection; `cluster.json` without it — the first file any run writes — is an
> **unfinished** one; a **non-empty** `results.jsonl` is scored output. An empty `results.jsonl` is not a
> marker: `collect.sh` does not create that file at all, and refusing on one would wedge a work directory
> against the commonest case there is — a run that failed partway and is retried.
>
> **Refusing, rather than deleting, is what keeps the invariant.** `awsjson`/`kjson` only write
> on success, so a stale file from an earlier run could otherwise satisfy a call that fails this time —
> and the validation gate, whose whole purpose is to refuse un-collected data, would then pass on data
> that was never collected. Clearing `$WORK/*.json` before the first AWS call would also prevent that,
> but only with an ownership rule to make the delete safe, and such a rule can still admit
> a directory holding an unrelated `results.jsonl` and clear the `.json` files beside it. Refusing
> needs no such rule: nothing is destroyed, so nothing has to be proven safe to
> destroy. **Re-running a cluster therefore means moving the old directory aside (or passing `--work`
> with a new path) rather than letting the script erase it.**
>
> **A required parameter is validated before anything touches the disk.** `KCTX`, `CLUSTER` and
> `REGION` are all checked before `$WORK` is created or `chmod`-ed, so a run that is going to be
> refused for a missing kube-context is refused before `$WORK` is created or its mode is
> changed.
>
> **There is no `export` grant, and there must not be one.** `Bash(export CLUSTER=*)` or `Bash(export
> WORK=*)` would authorise an `export` preamble at the top of a workflow block. A Bash rule is a literal prefix match on
> everything before its first `*`, so `Bash(export CLUSTER=*)` matches every trailing assignment on the
> same line — `export CLUSTER=x PATH=/tmp/evil:$PATH` matches, and this script resolves `aws` and
> `kubectl` through `PATH`. Narrowing cannot express the rule either: `Bash(export WORK=*eks-war-*)`
> collapses to the prefix `export WORK=` and grants exactly what the wide rule grants. So the parameters
> are arguments instead — an argument cannot set an environment variable.
> `collect.sh` still validates `$CLUSTER` against EKS's naming rule and `$WORK` against the
> work-directory rule, because it also accepts them from the environment.
>
> **The Step 5 pillar scorer blocks cannot be covered by a Bash grant directly, and `assets/score.sh`
> is why that does not matter.** Each block defines shell functions (`emit`, `g`, `m`, `m2`, …) and then
> calls them dozens of times; a Bash rule matches literal command text, so `m sec-1 cluster '…'` can never
> match a rule and every call would fall through to the permission prompt — so an unattended run
> could not reach a score at all. `score.sh` extracts the shipped fenced block and runs it, so the single
> grant `Bash(${CLAUDE_SKILL_DIR}/assets/score.sh:*)` covers all of it and the detections still live in the
> markdown where a reader sees them. Do not "solve" that problem by re-granting `Bash(aws:*)` or
> `Bash(kubectl:*)` — the scorers call neither; they only read `$WORK/*.json`.

## Why parameters are arguments

> **Every command in SKILL.md's steps passes its parameters as arguments, and that is a security property, not a
> style choice.** Each of its blocks is one Bash call and environment variables do not survive to the next, so
> the alternative would be to open every block with `export CLUSTER=… REGION=… KCTX=…` plus
> `export WORK=…`, authorised by a grant such as `Bash(export CLUSTER=*)`. There is **no** such grant,
> and nothing in this workflow exports anything.
>
> **Why there is no `export` grant.** A Bash rule is a literal prefix match on everything before its first
> `*`, so `Bash(export CLUSTER=*)` would have the prefix `export CLUSTER=` and match *every trailing
> assignment on the same line* — including `PATH=`, `HTTP_PROXY=` and `AWS_SHARED_CREDENTIALS_FILE=`.
> Since `collect.sh` resolves `aws` and `kubectl` through `PATH`, `export CLUSTER=x PATH=/tmp/evil:$PATH`
> would be a pre-authorised path to running an attacker-supplied binary: every `aws` call of the
> collection would run a planted `aws`. A grant for an `export` is never "one shell builtin that sets a
> variable" — one `export` line can set any number. An argument cannot set an
> environment variable, so passing parameters as flags closes the vector at the source instead of
> validating it afterwards, and needs no grant at all.

## Permission preflight and the read-only IAM policy

The preflight's scratch goes in `$WORK`. Without the preflight, a role short one action would discover
that partway through collection, after retries had burned minutes and after part of `$WORK` had already
been written.

How each half is probed, and why not `iam:SimulatePrincipalPolicy` — simulate needs `iam:SimulatePrincipalPolicy`, a permission a restricted role is unlikely to hold, and
it simulates rather than performs the call — AWS's own guidance is to "check your policies against
your live AWS environment after testing using the policy simulator". It also omits resource control
policies (RCPs). It DOES evaluate SCPs, including their condition keys and resource scoping, so that
is not a reason against it:

| Half | Probe |
|---|---|
| EC2 (8 actions) | `--dry-run` → `DryRunOperation` (authorized) / `UnauthorizedOperation` (denied). Exact verdict, no work performed |
| `eks`/`iam`/`ecr`/`cloudtrail`/`sts`/`pricing` (15 actions) | one cheap page-capped real call each. The two per-object `eks:Describe*` probes take an id from the matching `List` call, and are **skipped** when that list is empty — collection only calls them per listed name, so there is nothing to authorise. AWS documents `ClientException` for those operations as covering both "an IAM principal that doesn't have permissions" *and* "specifying an identifier that is not valid", so a made-up name could not tell a denial from the probe's own bad input; a real id removes the ambiguity |
| Kubernetes (27 probes) | `kubectl auth can-i` — a SelfSubjectAccessReview, always permitted and authoritative. **Each probe matches the call it stands for, in verb *and* scope**, because a pass that does not is worse than no pass: 8 cluster-scoped `list`s; 16 `list … --all-namespaces`, since the collector reads those with `-A` and a probe without it only answers for the context's default namespace; and 3 `get`s on the named ConfigMaps in their own namespaces (`aws-auth` and `amazon-vpc-cni` in `kube-system`, `aws-logging` in `aws-observability`), which is how the collector reads them — never as a list. `list` and `get` are separate RBAC verbs, so probing `list configmaps` would have refused a role scoped to exactly what this review reads |

All probes run in parallel, under a single hard timeout for the whole preflight (`PF_TIMEOUT`, 45s by
default). Run serially they would cost enough that an operator would look for a way to skip it, and a
preflight people disable protects nobody. Once its probes can run, it refuses in five cases, and only these five (before any probe runs, a preflight that cannot create its own temporary directory inside `$WORK` refuses with exit 1 — Step 2's table):

- **the cluster is out of scope** — `eks:DescribeCluster` is probed here anyway, so its response is read
  rather than discarded, and a `connectorConfig` in it means an **EKS Connector** cluster: out of scope
  permanently, **exit 3**, checked *before* the four permission cases below because scope beats
  permissions. If that call answered, the credentials are neither expired nor denied for it, and no
  re-authentication or policy can make the cluster in scope. Nothing is collected. This is also
  the only case the *rest* of the preflight cannot catch: a Connector kubeconfig sends every `kubectl`
  probe to `localhost:8080`, so the fourth case below would otherwise fire first and blame the network;
- a **proven denial** — the action or Kubernetes read came back unauthorized;
- **credentials that are expired or invalid** — a different problem with a different remedy, so it says
  so rather than reporting a permissions gap;
- **no probe settling at all** — the cluster or the credentials are unreachable, and proceeding would walk
  into every collection call blocking for as long as the probe just did;
- **one whole half settling nowhere** — every Kubernetes probe unsettled while AWS answered, or the
  reverse. This is the common shape of the previous case, not a rare one: a private API endpoint with no
  tunnel from here, or a `--context` naming another cluster, leaves all 27 Kubernetes probes unsettled
  while the ~23 AWS probes sail through. The all-or-nothing rule above stays quiet on that, so the run
  would proceed into 26 `kubectl` calls that each block as long as the probe did before the validation
  gate refused anyway. Each half is judged on its own probes, so neither can be carried by the other's
  passes, and the refusal names the half and its likely causes.

Anything short of those — a throttle, a network blip, any single non-authorization error — is reported and
allowed through, so a transient failure cannot block a run that would have succeeded; collection's own
fail-loud gate still catches it. A pass therefore means "nothing was denied and everything applicable
settled", not "collection is guaranteed to succeed". The scope case is the one exception that needs a
second line of defence, because allowing an unsettled `DescribeCluster` through also means allowing a
Connector cluster through: the same `connectorConfig` check therefore runs again once `cluster.json` has
been collected, and that copy names the file it left behind.

**The Kubernetes half is the one that surprises people: the built-in `view` ClusterRole is not
sufficient.** It does not cover `clusterroles`, `clusterrolebindings`,
`rolebindings`, `validatingwebhookconfigurations`, `mutatingwebhookconfigurations`, `persistentvolumes`
or `storageclasses` — all collected. Do not read that as a closed list: the preflight runs all 27
Kubernetes probes and names whichever are denied, which is the authority. `AmazonEKSAdminViewPolicy`
(`arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminViewPolicy`) covers them; note AWS documents that
it also grants read on Kubernetes **Secrets**, which this skill never collects. The collected workload JSON does hold every container's literal env values and arguments, so treat the work directory as credential material: keep it out of version control and delete it after the review.

The AWS half needs these 23 actions, and every one is a `Describe*`/`List*`/`Get*` read.

**19 of the 23 are called by `collect.sh`'s collection. Four are probed by its preflight and never called
after it:** `sts:GetCallerIdentity` and `eks:ListClusters` are the Prerequisites check and Step 1's cluster
listing, which you run before `collect.sh`; `ec2:DescribeInstanceTypeOfferings` and `pricing:GetProducts`
are used only by the deeper cost analysis in `references/cost-analysis.md`, which you run after scoring
to inform the narrative. They are in the policy and in the preflight because they are part of the
documented workflow — but be aware that a role permitted everything collection calls, and nothing more, is
still **refused** by the preflight for lacking `eks:ListClusters`, `ec2:DescribeInstanceTypeOfferings` or
`pricing:GetProducts` (`sts:GetCallerIdentity` needs no permission, so it cannot be the cause). That is
deliberate rather than accidental (a pass should mean the whole documented workflow is available), and those
three are where the preflight's AWS half is stricter than the collector.

**What `aws iam simulate-custom-policy` does and does not establish, because it is easy to over-claim.**
Simulated against the policy below, all 23 actions evaluate to `allowed` and `eks:DeleteCluster`
evaluates to `implicitDeny` — so the policy grants what this review calls and nothing that writes. That
is the whole of what simulate establishes. It does **not** confirm an action name is real: a misspelled
name returns `implicitDeny`, the identical verdict a real action the policy omits returns, and a
misspelling *inside* the policy is accepted silently — a document granting `eks:DescribeClusterr`
simulates without error and simply fails to grant `eks:DescribeCluster` (both measured). Nor does
simulate say anything about an action being read-only; it answers "does this policy allow X", not "does
X mutate". Read-only comes from the verb and from AWS's service-authorization reference.

So the real guarantees are elsewhere: the list is derived from the collector's own invocations rather
than maintained by hand, and `collect.sh`'s preflight probes **every one of the 23 for real** against the
live account — which is what would catch drift between this policy and what the code calls.

```json
{"Version":"2012-10-17","Statement":[{
 "Sid":"EksWarReviewReadOnly","Effect":"Allow","Resource":"*","Action":[
  "eks:ListClusters","eks:DescribeCluster","eks:ListNodegroups","eks:ListAddons",
  "eks:DescribeAddon","eks:DescribeAddonVersions","eks:ListInsights",
  "eks:ListFargateProfiles","eks:DescribeFargateProfile","eks:ListPodIdentityAssociations",
  "ec2:DescribeInstances","ec2:DescribeVolumes","ec2:DescribeSecurityGroups","ec2:DescribeSubnets",
  "ec2:DescribeNatGateways","ec2:DescribeRouteTables","ec2:DescribeVpcEndpoints",
  "ec2:DescribeInstanceTypeOfferings","iam:ListOpenIDConnectProviders","ecr:DescribeRepositories",
  "cloudtrail:DescribeTrails","sts:GetCallerIdentity","pricing:GetProducts"]}]}
```

`eks:AccessKubernetesApi` is deliberately **not** in that list: it is required for the AWS console's
Resources view, not for `kubectl`, which authenticates through the kubeconfig `exec` plugin calling
`aws eks get-token`.

## Which surfaces are machine-generated

Know which surface you are reading:

| Surface | Machine-generated? |
|---|---|
| `results.jsonl`, `scores.json` | **yes** — fixed `jq`, no judgement |
| `report.html` (via `assets/render-report.py`) | **yes** — scores copied from `scores.json`, resource lists copied from the scorer's own `resources` (see Step 8); byte-identical for the same work dir |
| Anything you type in chat, or a hand-written markdown report | **no** — agent-transcribed |
| Cost opportunities, action-plan ordering, remediation prose | **no** — your judgement, deliberately |

## Step 1 detail: binding the review to one cluster

The work directory is created first, owner-only (`-m 700`), because everything after it writes into it:
the kubeconfig, kubectl's discovery and HTTP cache, and in Step 2 the whole collection. `collect.sh`
leaves the mode of a directory it did not create as it finds it, so the `-m 700` in Step 1 is what makes the
collected account and IAM identifiers private. `-p` makes re-running Step 1 harmless; an existing
directory keeps the mode it already has. Neither file Step 1 writes is one of the markers `collect.sh`
refuses on, so Step 2 collects into this directory normally.

`--alias <CLUSTER>` makes the context name equal to the cluster name. That is what `KCTX` is set to in
`--context` on every `kubectl` call and `--context` on `collect.sh` — one string, so the two halves of
the review cannot drift apart. Substitute the literal name in Step 1's commands rather than `$KCTX`: they run
before any preamble and need no variable.

The three bundled scripts are invoked as `${CLAUDE_SKILL_DIR}/assets/…`. There is nothing to export for
them: Claude Code substitutes that variable into both the command and its grant, so the paths resolve
from any working directory without a prompt.

The AWS half of this review comes from `describe-cluster`; the Kubernetes half comes from whatever
`kubectl` points at. If those are different clusters the review still completes and still passes the
validation gate — every required file present and valid JSON — but the report names one cluster while
grading another's workloads. `assets/collect.sh` therefore verifies that both halves are the same cluster
before collecting, and routes every `kubectl` call it makes through `--context "$KCTX"`. It compares the
cluster **CA certificate** — `.cluster.certificateAuthority.data` from `describe-cluster` against the
kubeconfig's `certificate-authority-data` — because a CA identifies the cluster while an endpoint URL
identifies only the route to it. It does not compare endpoint URLs, which would refuse every legitimate
indirection: a private-endpoint cluster reached over an SSM tunnel presents `https://127.0.0.1:6443` in
the kubeconfig, as do `kubectl proxy`, an `/etc/hosts` override and an egress proxy. That would make this
skill unable to review the very posture its own `sec-2` rewards — turn the public endpoint off and the
review would stop working. Same cluster by a different route is **accepted with a note naming both
addresses**; a different cluster is refused: AWS creates a CA for each EKS cluster, so a CA match
identifies the cluster.

**The match is containment, per certificate — not equality of the whole file — and that is required, not
a convenience.** AWS's CA-rotation guidance is explicit that clients should "trust a CA bundle rather than
pin to a single CA certificate… CA pinning (strict validation against a single CA) is not recommended, as
it will cause failures when the trust bundle is updated," and it applies that to any client-side TLS
configuration reaching the API server. During a rotation's **dual trust period** the kubeconfig
legitimately carries two CAs, the outgoing and the successor. An equality test over the concatenated file
would refuse a perfectly healthy cluster and report it as "two different clusters" — and EKS
rotates the CA automatically if the operator does not, so that would be a matter of time rather than of
misuse. Collection accepts the kubeconfig when the cluster's in-use CA is **among** the certificates
it trusts, notes the count when there is more than one, and still refuses a bundle that belongs to a
different cluster.

**Relaxing the route costs nothing, because the CA is not this check's only enforcement:** `kubectl`
performs its own TLS handshake against that same CA on every API call, so a proxy that cannot present a
certificate signed by it cannot serve the connection at all. This check exists to stop the review
silently grading the wrong cluster, not to secure the transport. A kubeconfig carrying no
embedded CA (`insecure-skip-tls-verify`) cannot be identity-checked and is refused.

## Step 2 detail: the kubeconfig, the parameters, the work directory and the exit status

`--kubeconfig` points every `kubectl` call `collect.sh` makes at the kubeconfig Step 1 wrote into the
work directory. Without it `kubectl` reads `KUBECONFIG` or `~/.kube/config`, which it only reads, so a
caller who keeps its own kubeconfig can leave the flag off.

`collect.sh` takes `CLUSTER`, `REGION` and `KCTX` from `--cluster`, `--region` and `--context`, falling
back to environment variables of those names, and has no defaults for any of them. All three are validated before
anything is created — a missing one costs you nothing but the run. It validates the cluster name before
deriving `$WORK` from it, and takes `$WORK` from `--work` or the environment if set, otherwise
`./eks-war-$CLUSTER` — the same path `--work` names in SKILL.md Step 2. **`$WORK` may sit beside unrelated files (any `*.json` inside `$WORK` must be valid JSON other than null/false), but must not already hold a previous
run:** the script never deletes, so it refuses rather than collect on top of an earlier collection. That
means **re-running a cluster needs the previous directory moved aside, or a new `--work`
path** — the refusal names the path and the rule.

The exit status says whether retrying can ever help:

| Exit | Meaning | What to do |
|---|---|---|
| `0` | collected and validated | continue to Step 3 |
| `2` | **the command line could not be parsed** — a flag given without its value, an unknown flag, or `-h`/`--help`, which prints usage and stops on purpose. A *missing* `--cluster`/`--region`/`--context` is **not** this case — that is `1` | re-issue the command exactly as written in SKILL.md Step 2 |
| `3` | **the cluster is permanently out of scope** — `describe-cluster` returned a `connectorConfig`, so it is an **EKS Connector** cluster: someone else's Kubernetes cluster registered with EKS for console visibility, not one AWS runs. See *What counts as "an EKS cluster" here* | stop. No retry and no permission change helps. Normally nothing has been collected; if the refusal came after collection started it says so and names the file it left |
| `1` | **everything else, and all of it about this run rather than the cluster**: a required parameter was not supplied (`--cluster`, `--region` and `--context` have no defaults and each names itself), the cluster name, region, `--work` path or `--kubeconfig` file failed validation, the preflight found a denial or expired credentials or could not create its own temporary directory, `$WORK` already holds a previous run, the kubeconfig's context presents a different cluster's CA than `--name`, a required call failed, or the validation gate found the collection incomplete | read the message — each names its own remedy (supply the flag, re-authenticate, attach the policy, move the work dir, fix `--context`) and re-run |

`3` is the only status that says the *input* is out of scope; `2` means the invocation never parsed;
everything else is `1` and the message names what to change. None of them leaves a partial collection that
a later step could score.

## Step 3 detail: the seven mode labels, and why the numbers set no flags

`render-report.py`'s seven possible strings, in the order it tests them:

| Label | When |
|---|---|
| `EKS Auto Mode` | `computeConfig.enabled` is true and no node is hybrid |
| `EKS Auto Mode + EKS Hybrid Nodes` | `computeConfig.enabled` is true and at least one node is hybrid |
| `Fargate only` | Fargate profiles exist and every node is a Fargate node |
| `EKS Hybrid Nodes` | every node is a hybrid node |
| `Fargate + EKS Hybrid Nodes` | Fargate and hybrid nodes, and no EC2 node |
| `Standard` / `Standard + EKS Hybrid Nodes` | anything else, with the suffix when any node is hybrid |

**The numbers Step 3 prints set no flags and the scorers do not read them.** Every mode-dependent question decides
applicability inside its own `jq`, from the same collected files: `fargate-4` returns `na` when
`fargateProfileNames` is empty, and `ope-15` returns `na` when no node is an EC2 node. There is no
`$AUTO_MODE` and no `$EC2_NODES` — no scorer reads a shell variable other than `$WORK`, and a flag
exported here would silently do nothing. Recomputing per question is also what
keeps the detection and its published `jq` the same text, which is the determinism guarantee.

## Step 4 detail: why the gates are shaped this way

The viability and liveness gates live in the reducer alone because two copies can disagree: prose in SKILL.md plus Python in the renderer would
let the HTML withhold a dead cluster's score while the reducer still emitted a number, so the chat and
markdown paths would publish the number the report itself refuses to.

`nodes_total == 0` is sufficient on its own. Requiring zero nodes **and** zero workload pods would
let a cluster with no nodes but declared pods escape both gates — viability would want zero pods, and
liveness needs at least one node to inspect — and publish a full numeric score. Pods without nodes are
manifests, not running software.

**A 0-node cluster (no Linux node) is still worth reviewing, and the pillar numbers are published for it.** A cluster
mid-setup or scaled to zero is a legitimate target, and the operator building it is the reader this
review should serve best — withholding all five pillar numbers would leave them a banner and a count.
So report the numbers, and label every one of them `declared configuration only`. State in the same
breath that **they are not comparable to a running cluster's and must not be plotted beside one**: every
question the missing objects would have failed becomes `na` and leaves the denominator, so the emptier
the cluster, the fewer ways its score can be pulled down. That hazard is a reason to label the numbers,
not to hide them. The **overall** stays withheld, because one headline number for a cluster nothing runs
on is the claim that cannot be made honestly.

**Judge only what is running, but do not filter the denominators.** These are different things and
conflating them inverts the score. Do **not** restrict the ratio detections to `Running` pods: a cluster
where 10 of 15 pods are `Pending` for want of schedulable resources would then score `perf-1` as
`5/5 = all` — a perfect result on resource requests, for a cluster that cannot schedule its workload.
`CrashLoopBackOff` also reports `phase: Running`, so phase filtering would not even catch the commonest
failure. Withhold the headline instead.

**This is a disclosure, not a refusal** in the `NOT HEALTHY` and warning cases. A cluster mid-deploy or
mid-upgrade legitimately shows Pending pods and NotReady nodes, and a batch cluster legitimately sits at
zero running pods between jobs. Say what was observed and let the reader judge.

## Step 5 detail: the `resources` key

**The five keys of the SKILL.md Step 5 example, in that order, are the whole record for 66 of the 132 questions. The other 66 carry a
sixth, and a consumer must not assume exactly five.** When a question's reference file carries an `rl`
line immediately above its `m` line, the scorer also names the objects it counted and `emit()` appends
`resources` — always last, after `detail`:

```
{"pillar":"cost-optimization","id":"cost-1","track":"measured","state":"none","detail":"0/4 ns cpu/memory quota","resources":{"pass":[],"fail":["default","keda","keda-demo","monitoring"]}}
```

`resources` holds `pass` and `fail`, each an array of strings, and may add, always in this order:
`context`, an array of strings naming objects a check looked at without grading; `kind`, `"field"` or
`"existence"`, which picks the caveat printed beside the list; `excluded`, a whole-number count of
objects deliberately left unnamed, which the report turns into a disclosure sentence when nonzero; and
`context_only`, only ever `true`: a cluster setting or node fact settled the verdict, so the list is not
checked against its count. `rl` keeps those six keys and drops any other. Three states, deliberately
distinguishable: **no `resources` key** means the question publishes no list by design (a cluster-flag
question has no objects to name); **`"resources":null`** means `rl` ran and its name expression failed on
this cluster's data — `rl` cannot abort a question, so the verdict is unaffected, but "the list broke
here" and "nobody wrote a list for this" call for different actions; an **object** means the lists. The 66
ids are countable (`grep -h '^rl ' references/*.md references/*/*.md`) rather than listed here, because a
second copy of that list is one more thing to keep in step.

**The five-key prefix and its order are fixed, deliberately**, so anything that parses the five-key
record also parses this one — `reduce.sh` reads only those five and ignores `resources` entirely. What
breaks is code that counts keys, pins a key set, or treats an unrecognised key as corruption. Step 8's
renderer is the only consumer of `resources`.

## Step 5 detail: how `score.sh` runs the scorer blocks, and why there is no drift detection

`score.sh` does not carry a copy of the detections. It extracts the first fenced `bash` block — the
`## <Pillar> scorer` block — from the reference file below and runs it, so what executes is exactly what
a reader sees. It refuses a block that does not define `emit()`, so a per-question `**Commands:**` or
`**Remediation:**` snippet can never be executed by mistake; some of those delete PersistentVolumes.

| Pillar | Block extracted from |
|---|---|
| Operational Excellence | [references/operational-excellence.md](operational-excellence) |
| Security — all 57 questions in one block | [references/security/identity-access.md](security/identity-access) |
| Reliability | [references/reliability.md](reliability) |
| Performance Efficiency | [references/performance-efficiency.md](performance-efficiency) |
| Cost Optimization | [references/cost-optimization.md](cost-optimization) |

The other four security files (data-protection, network, workload-security, governance-compliance) hold
per-question rationale and remediation you load when writing findings; they carry no scorer block.

**Do not paste the blocks into a shell instead.** Pasting them cannot be
authorised: each block defines shell functions (`emit`, `g`, `rl`, and the `m`-family `m`, `m2`, `m3`,
`m4`, `m5`, `m6`, `m7` — no single block defines all ten) and then calls them 198 times across the five
blocks as `m sec-1 cluster '…'`: 103 `m`-family calls, 29 `g` and 66 `rl`. To count them yourself, from the
skill root, `grep -hE '^(m[0-9]*|g|rl) ' references/*.md references/*/*.md | wc -l` — count with `wc -l`,
not `grep -c`, since `grep -c` over a glob prints one count per file and never the total, and the globs
resolve only from the skill root, not from `assets/`. A Bash permission rule matches literal
command text, so no rule can match a shell-function name — every one of those calls would fall through to the
normal permission flow, prompting interactively and failing outright under a no-prompt policy, so an
unattended run could not reach a score. The same wrapper-function problem is why collection lives in
`collect.sh`, and why scoring lives in `score.sh`. One grant per `score.sh` invocation covers all
of it, and the detections still live in the markdown a reader sees, so what executes is what you can read.

**This review has no drift detection.** A spot
check of a few settings is not drift detection — nothing stores a prior state to compare against. Such a
check would duplicate a scored question, or contradict it (a NetworkPolicy or PDB row passing on
"more than zero covered" while `sec-4`/`rel-2` grade the ratio would show a High-severity gap green),
or map only to a governance question the report declines to assess. A
"N of N passing" headline would then undercut the actual verdict. Real drift detection needs a stored previous run
to diff against. A single review therefore cannot say whether a finding is new, and must not imply it: report the state observed, not a trend.

## Step 7 detail: `-o`, four more refusals, and where severity lives

`-o` is used, not a `> "$WORK/scores.json"` redirect, for two reasons.
A redirect is performed by the *calling* shell before the reducer starts, so no `umask` inside the
reducer could reach the file: `scores.json` would land mode 644 while every file `collect.sh` writes is
600, and `scores.json` is one of the two files most likely to be pasted into a ticket. And a redirect
that is never optional is easy to omit, which leaves a **0-byte** `scores.json` whose failure surfaces two
steps later as a renderer complaint. `-o` does **not** make that write atomic. Refusals at the gates
above the write leave an existing `scores.json` alone — measured, eight different gate refusals each
left a good 3400-byte one byte for byte as it was. But the final stage is `cat > $WORK/scores.json`,
and `cat` truncates that file as the pipeline **starts**, before the upstream `jq` has produced a
byte — so a failure **anywhere in that pipeline** lands on the file, including an upstream one where
`cat` itself succeeds and writes nothing. Measured: a `jq` failure upstream took that
same 3400-byte `scores.json` to **0 bytes** at exit 2, and the same failure in a work dir that held
no `scores.json` left a 0-byte one behind. What the operator sees is four lines of `jq` and **no
`reduce.sh:` message at all** — a `jq: error (at $WORK/nodes.json:1): …` naming the file, then the
bare `jq: invalid JSON text passed to --argjson`, then two `Use jq --help` usage lines. A write that
cannot finish leaves a **truncated** file rather than an empty one: under a 2048-byte file limit the
run died on `SIGXFSZ` at exit **153** with 2048 of those 3400 bytes on disk — a prefix that opens
with a complete and correct `"technical_overall"`, so it reads like a real score to anyone who
eyeballs the top of it, but that no tool accepts: `jq -e .`, `python3 json.load` and
`render-report.py` all reject it. Passing no `-o`
still prints to stdout, so a redirect-based caller still works.

- **The collection fingerprint.** `collect.sh` writes `$WORK/.collection.json` at the end of a
  successful collection — a per-file sha256 of everything it collected, plus a digest over those lines.
  `reduce.sh` recomputes it and refuses an absent, malformed or non-matching fingerprint, naming which
  files were *modified* or *removed since collection*. Every question was answered from the files as
  they were then; scoring the current ones would publish a number for one cluster state under the
  evidence of another. A work dir with no fingerprint is either from a collection that itself refused —
  read the collector's message, do not score it — or one assembled by hand. Re-collect and re-score all
  five pillars; there is no flag to skip this.
- **The `pillar` and `track` enums.** Both are matched downstream by exact, case-sensitive string
  equality, so a misspelling is not a wrong answer but a missing one: the record drops out of the
  numerator *and* the denominator at exit 0 with no warning. The legal values are the scorers' own —
  the five `emit()` literals and `measured`/`governance` — so anything else is refused rather than
  silently dropped.
- **`state` against the ratio in its own `detail`.** A measuring scorer splits one `b($ok;$t)` result
  into both halves of the record, so `"state":"all"` beside `"detail":"0/8 …"` cannot be a legitimate
  record — yet the arithmetic uses the state while the reader uses the ratio, and the disagreement is
  invisible. The gate extracts the committed `B='def b(…)'` line from `references/` rather than keeping
  a second copy, and asserts there is exactly one distinct definition across the five scorer files.
  **It is bounded to the `measured` track, and that bound is correctness, not convenience:** the
  invariant is a property of the `m`…`m7` helpers, where both halves come from the same `b()` call. A
  governance record has no such relationship — `g` emits `unknown` and `b()` never runs — so there is
  no second projection to cross-check.
- **The severity source.** The weights are not in the reducer; it parses
  [references/severity.md](severity) on every run, on the same principle as `b()` above,
  and publishes what it parsed in `scores.json` under `severity` for the renderer to label findings
  with. A row's weight is the tier of the **nearest preceding** `### High`/`### Medium`/`### Low`
  heading, so any edit changing which heading that is changes the score. The reducer therefore requires
  every tier heading to own exactly one well-formed table (`| ID | … |` header, `|----|` separator, then
  at least one data row), and refuses: a missing or unreadable file; a first cell that is not a question
  id (or a ` / `-list or a `fargate-1..2` range), or an **empty** first cell; **a table no tier heading
  opens** — a heading deleted, or retyped into something that is not `### High`/`### Medium`/`### Low`, or
  a blank line / HTML comment / code fence splitting a table; **a table not beginning
  with its header row, or a heading owning no data rows** — a heading inserted into, or just above, an
  existing table (left unrefused, one inserted `### Low` would silently re-tier the rows below it up to the next heading at
  exit 0); **a table line that does not begin with `|`, or one indented four or more columns** — the first
  is *usually* invisible in the rendered file (un-piping a **data** row renders byte-identically to pristine,
  measured at four positions) but not always: un-piping a line whose first cell is `ID` *adds* a visible row,
  so the reducer reports that case separately and prescribes no repair. The second is *usually* visible as a
  `<pre><code>` block with rows missing, but not always either: indenting the **delimiter** row emits no
  `<pre>` at all and instead turns the whole table into one paragraph of literal pipes. Neither claim is
  safe as a blanket one, and each refusal states what it measured for the line it read. Also refused: an
  **unterminated code fence** — an unclosed `` ``` `` before the tables renders the whole document as 0
  tables and 0 rows in both renderers while the weight map stays correct, so the reducer tracks fence state
  (same character, run at least as long, no info string on the closer) and refuses before anything is parsed;
  a count would not do, since `` ``` `` does not close `~~~`;
  **carriage returns** in the file, in four distinct shapes with four different messages — CRLF endings,
  bare-CR endings, *mixed* endings where only some lines are CR-terminated, and a `\r` *inside* a line —
  of which the bare-CR case is a parse failure (awk sees runs of lines as one record) and the interior case is
  refused on its own terms, while CRLF and mixed endings are hygiene refusals — the reducer strips carriage
  returns before matching, and an all-CRLF copy of a well-formed file was measured to produce the identical map
  and the identical rendered file. **Every arm prescribes the same two-stage repair, and its locale is
  pinned on both stages**: `LC_ALL=C awk '{sub(/\r$/,"")} 1' f | LC_ALL=C tr '\r' '\n'` — the form the
  reducer's own messages emit. Drop either `LC_ALL=C` and one invalid byte aborts that stage mid-stream
  while the `> fixed` redirection keeps only what had been written — measured on a CRLF copy with one
  Windows-1252 byte in a data cell, under half the file survives, and the reducer then refuses it too. It
  does **not** cover every case and it is not all the messages prescribe: where a carriage return sits
  immediately before an interior `|` the command splits that row instead of restoring it and the reducer
  still refuses (measured: that row comes out as two lines), which is why the interior arm prescribes per-line deletion
  first and the two hygiene arms offer `LC_ALL=C tr -d '\r'` as an equal alternative. Neither single-step
  command is safe on every carriage-return shape — each destroys the document on some
  shape — and a predicate choosing between them per file would have to be right on all of them. Also: an id with two rows; a question in
  `results.jsonl` with no row; and a row naming a question nothing emits. **Every refusal names a line
  number**, and none asserts an edit the parser holds no evidence for; whether it also *quotes* the line
  depends on whether the line's text is what is wrong with it (`references/severity.md` states which four
  refusals name a line and quote nothing, and why). Where a quoted line holds characters a terminal does not
  display, the message names the character and its byte offset.
  **There is no fallback weight** — a default such as `// 2` would let a row documented Low
  be scored Medium without a word. What no gate can catch is any edit that leaves every heading
  owning a complete table while changing which heading is nearest to a row — retyping a heading into
  *another valid tier heading* (`### Medium` → `### Low`: exit 0, zero complaints, every row under it re-weighted)
  and moving a row are two instances — because that is how a deliberate re-tiering is expressed: **read a
  `severity.md` diff as a score change.** If a gate fires, fix the table; do not work around it by
  editing the reducer.

**Which tier each question is in lives in exactly one place:
[references/severity.md](severity).** `assets/reduce.sh` parses its `### High` /
`### Medium` / `### Low` tables on every run and weights the score with what it finds, then publishes the
parsed map in `scores.json` under `severity`; `assets/render-report.py` reads it back from there for the
risk-weight chips and the improvement-plan ordering. Neither script assigns a question to a tier, so **to
change a question's severity, edit that table and nothing else** — and the weight the report labels a
finding with is by construction the weight its score was computed from. The reducer refuses (exit 1) if
that file is missing or unreadable, if a table is not owned by exactly one tier heading, if a row is
unreadable, if an id has two rows, if a scored question has no row, or if a row names a question nothing
emits; there is no fallback weight.

## Step 8 detail: themes, the internal report, resource lists and what the renderer reads

`-B` stops `python3` writing bytecode caches: without it, Apple's command-line-tools `python3` writes
them under `~/Library/Caches/com.apple.python`, outside the work directory.

`${CLAUDE_SKILL_DIR}` is what makes the bare `assets/...` form unnecessary: that resolves only when the
shell happens to be sitting in the skill root, which is not where `$WORK` is. The renderer finds
`references/` from its own file location, so nothing has to point it there. `-o` is an argument, not a
shell redirect, so the file it names is written by the program itself and no `Edit` rule is consulted
for it.

`--theme auto` (default) ships both token sets, starts from the reader's `prefers-color-scheme`, and
puts a **light/dark toggle in the top right** that remembers the choice in `localStorage`. All four
states (base light, OS dark, OS-dark-but-pinned-light, pinned dark) are resolved by CSS, so the
report is correct before any script runs; the toggle button ships `hidden` and is revealed by the
inline script, so a viewer with JavaScript stripped sees no dead control.

Use `--theme dark` or `--theme light` to **pin** one — no toggle, no script — for when the file is
emailed, attached to a ticket, or printed and the reader's OS setting is not yours to predict.

The report's specificity is deliberate: it is what lets a reader verify a finding instead of trusting it. It also
describes the environment to anyone who receives the file, so the account ID and resource identifiers
should be masked before it leaves the cluster owner's circle. Identifiers for resources *outside* the
reviewed cluster are reported as counts, not named, so the report does not widen its own blast radius.
**`results.jsonl` is not numbers-only either.** The 66 records carrying
`resources` (Step 5) name namespaces, ClusterRole and ServiceAccount names, pod / Job / CronJob /
DaemonSet / StatefulSet names, PV and PVC names, CloudTrail trail names, and EC2 instance and EBS volume
ids — the same identifiers the rendered HTML shows. The collected JSON beside it is
identifier-rich too, but `results.jsonl` reads like a scoreboard and is the file most likely to be pasted
into a ticket as "just the scores", so say *the work directory* is internal, not just `report.html`.
`--both` writes the light file plus a pinned `-dark` sibling. `--no-toggle` keeps `auto` behaviour
but ships no script at all.

Still one file either way: the toggle adds ~20 lines of inline JavaScript and two inline SVG icons.
No `src`, no `@import`, no `fetch` — verifiable by grepping the output file, because a report that
reached the network on open would break the skill's "the report makes no network requests" contract.

**Each finding carries a named resource list.** "3/3 core addons" is a claim the reader cannot check;
`coredns, kube-proxy, vpc-cni` is one they can verify in seconds. The scoping error to watch for in a
check like these is a *correct count over the wrong set* — an unrelated security group, another cluster's
volumes, AWS-installed Deployments counted as the operator's. The lists make that visible, and they
also name what was **excluded** and by which rule — the mechanism, not a verdict on it — so a reader
who thinks the scoping is wrong can see the rule and say so.

Wherever a check reports an `N/M` count the renderer recomputes it from the list and **marks the finding
unverified, banners it at the top of the report, and exits non-zero** on any disagreement — a list that
contradicts its score would be worse than no list.

**Every list has ONE provenance: the scorer that produced the verdict.** The question's reference file
carries an `rl <id> <files> '<program>'` line directly above its `m` line, and that program names the
objects the `m` line counted. Countable, not declared: `grep -c '^rl ' references/*.md
references/*/*.md`.

**Be exact about what the tick proves.** The comparison is `rl`'s own counts against the `m` line's
ratio one line below it, in the same file, and the two jq programs repeat the same scope filter and the
same pass predicate. So it catches drift between those two adjacent copies — and nothing else. **A
scoping error is present in both copies and is structurally invisible to it.** The panel therefore says
"these are the objects the check itself counted", never "they agree": do not read the tick as a
confirmation it cannot give.

**"They agree" would be worse than imprecise.** A second implementation of each check — say in
Python in the renderer, re-reading the same collected files to re-derive the list — would look like
independent verification without being one. Nothing would force the two to agree, and a list naming a
different set from the one its own verdict counted — a security group open to `0.0.0.0/0` among the
**passes** beneath a red Fail, or 3 objects named under a verdict built from 13 — hides behind any
detail carrying no `N/M`, where the count comparison never runs. That is why every list comes from the
scorer's own `rl` line and nowhere else.
A second reading is only a check if
something forces the two to agree.

No arrangement of lists can catch a rule that scopes the wrong set. The *correct count over the wrong set*
bug is caught by **reading the excluded list**, which is why the excluded list names its rule and never
certifies it.
A question with no `rl` line simply shows no list.

Where a check is boolean or reads a field rather than counting objects, there is no total to recompute
against, and the panel says so in those words instead of showing a tick. That distinction is the point:
a check the report *cannot* cross-check must not look as though it did.

Panel order is deliberate: *why it matters* → *what we found* → *how to fix* → *how this was measured*
(nested, collapsed). The verbatim `jq` serves a narrow audience — auditing the tool, disputing a
finding, maintaining the skill — so it sits last rather than pushing the fix out of view.

**No JSON export.** Scraping the rendered HTML for all findings and parsing an equivalent JSON blob
differ by well under a millisecond, so a second artifact buys nothing for a program; and an LLM reads
the whole file regardless, so an embedded copy would only add tokens. Rows instead carry
`data-qid` / `data-state` / `data-severity` / `data-pillar` attributes, which makes scraping reliable at
zero cost.

It reads `scores.json`, `results.jsonl` and the collected cluster JSON, and emits one
self-contained file — no network requests, no external CSS or JS, so it opens offline and no data
leaves the machine. Styling is the [Cloudscape Design System](https://cloudscape.aws.dev): Amazon
Ember with the documented monospace fallback for IDs and measured values, container/table/status
indicator/badge/alert surfaces, and the light **and** dark token sets wired to
`prefers-color-scheme`. Question text is read from the `references/` files, so it cannot drift from
the scorers.

It also reads **SKILL.md** for text it must reproduce rather than paraphrase: the
framework-areas-with-no-question list and the narrower-gaps paragraph (*Framework areas with no question
at all*), the score disclosure, and the platform-credit note in its two cases (*What the report must
disclose about the score*) — and **this file** for the platform-scope bullets (*What counts as "an EKS
cluster" here*, above). Six marker pairs, named `NOT-ASSESSED-AREAS`,
`NOT-ASSESSED-NARROWER`, `SCOPE-PLATFORMS`, `SCORE-DISCLOSURE`, `PLATFORM-CREDIT-NOTE` and
`PLATFORM-CREDIT-NONE`. Each is
printed verbatim, so the boundary of what was checked and the caveats on the number reach the customer's
copy instead of staying in the maintainer's. A shorter list in the report than in SKILL.md or this file is a bug: the
renderer exits non-zero if a block is missing.

Every **score** in the HTML is copied from `scores.json` and `results.jsonl` — the renderer never
recomputes one and does not check the scores in `scores.json` against `results.jsonl`, so re-run
`reduce.sh` after any re-score; if a score from a fresh reduce looks wrong, look upstream at the scorer,
not the renderer. The **resource lists are not derived
either** — they are read straight from each record's `resources` key, which the scorer's own `rl` line
produced from the same collected files as its verdict. Three things the renderer does derive itself: the
thin-evidence marker (under 70% of the questions that can apply on this cluster answered — structurally
inapplicable questions such as `fargate-*` on non-Fargate compute are left out, so the marker can be absent
at a published coverage below 70%), the Immediate/Short-term/Strategic tiering (severity weight ×
how far short the state fell), and the rating and risk labels (mapped from the score). A list that contradicts its score
therefore means one of the two halves is wrong and neither is presumed right — hence the banner and the
non-zero exit instead of a chosen winner.

## Step 8 detail: if the renderer exits non-zero

The `wrote …` line is printed with `flush=True` precisely so its order against stderr is reliable under a pipe,
where stdout is block-buffered and stderr is not.

**Before any `wrote …` line** it refused the inputs and wrote no report: a missing or malformed
`scores.json`, a work dir that does not match its own collection fingerprint, an unreadable collected
file, a `-o` target that is a directory, whose parent is missing or unwritable, or whose path the
filesystem will not accept at all. Fix the input and re-run. A write that fails part-way prints `could not write …` and leaves what it wrote at `<report>.part`, named in that line; the `-o` path itself is untouched. Do not hand-write the HTML instead.

**One exception, and it is the only one: a line containing `WARNING` is not a refusal.** The renderer
prints `render-report: WARNING …` when it cannot parse a scorer line in a reference file, and those
appear ahead of `wrote …` because that parsing happens before the write. So a run can print
`render-report: WARNING …` and still go on to write a complete report and exit 0. Apply the rule above to
`render-report:` lines that do **not** contain `WARNING`.

**After a `wrote …` line** the report exists, names the problem in a banner, and is still wrong in a way
you must repeat in chat. There are exactly five causes, each printed as its own `ERROR:` block on
stderr:

| stderr block | What happened |
|---|---|
| `N finding(s) have a resource list that contradicts the count their detection reported` | A question's `resources` list and its own `N/M` detail disagree (e.g. `sec-21: resource list says 4/5 but the check counted 4/4`). One of the two halves is wrong and neither is presumed right. |
| `N block(s) of report content could not be read from SKILL.md` (or `… from references/workflow.md`, or both names joined by `and`, in either order) | A `<!-- NAME:BEGIN -->`/`END` pair in SKILL.md — or, for `SCOPE-PLATFORMS`, in this file — is missing or empty, so a **disclosure about what the review did not check** is absent from the report. There is deliberately no shorter fallback text. |
| `N problem(s) with question remediation text` | A question's "How to fix" panel is **missing or corrupted** — either absent entirely, or filled with text the parser mis-bounded. Both are the worst thing this parser can do quietly, on a High-severity finding, and the two are told apart per entry below. **`N` counts problems, not questions,** and one problem can stand for many: an entry reading `(whole file)` or `(all questions)` covers every question in that file or directory, and one reading `N … question(s)` covers exactly those ids. Causes — the first two **corrupt** the panel, leaving it present but wrong; the rest leave it **absent** — no panel at all, or, where that finding is *also* contradicted, the withheld notice in its place — and a reader cannot tell the absent case from a question that legitimately has no fix: an unclosed ``` fence inside a remediation (that question's fix renders partly as preformatted text); a missing `---` after a block (the following section bleeds into the panel); a `**Remediation:**` marker edited into a form the parser cannot read; a reference file or the whole `--references` directory unreadable; questions being scored that the references do not define; or measured questions with an actionable verdict carrying no remediation at all. The last three usually mean `--references` points somewhere wrong, or a directory beneath it is unreadable — check that before re-running. |
| `N scorer call(s) whose prelude definition could not be extracted, so the report prints a program that will not run` | A scorer calls a helper defined in a block-local prelude (`b(`, `ishy`, `hyx`, `gkenf`) and the "Exact command used" panel could not find that definition, so the program it prints stops with `b/2 is not defined` if a reader pastes it — the audit trail for that verdict is broken, not the verdict. The prelude assignment must read `NAME='def ...'` all on one line, with no leading space, nothing between the quote and `def`, and nothing after the closing quote; this applies to `B=` as much as to `PE=`. Measured on each of the five pillar files: one space before its single `B='` line lists every scorer or `rl` line in that file whose program names a helper `B` defines, once per helper named, so `N` depends on the file and one broken prelude stands for many questions. |
| `the regex/heuristic disclosure set changed -- N lost, N gained` | The set of questions whose detection decides by matching a pattern against a resource **name**, namespace, image or add-on id no longer matches `_DISCLOSED_EXPECTED` in `assets/render-report.py`. A **lost** entry is the one that matters: that question's evidence panel has silently dropped the caveat saying a tool that does the job under a name the pattern does not know is reported as absent — the classification is read off the scorer's own jq, so either a detection changed or its reference file could not be read. A **gained** entry is a question that has started deciding by name and now needs that caveat confirmed. Update `_DISCLOSED_EXPECTED` only when the change was intended. |

For all five: name the affected ids and say the report flags them as untrustworthy. Summarising such a
run as clean is the one failure these checks exist to prevent.

**One limit of the remediation check, worth knowing before you trust a clean run.** It asks for remediation only
where the verdict is *actionable* — a measured question whose state is not `all` (already done) or `na`
(does not apply). Neither owes the reader a fix. Two consequences: an `na` question's fix text can go
missing with no diagnostic even though `na` **does** render a panel (the thinner the cluster, the more
questions are `na` — and the most fall on a cluster this skill scores `NOT VIABLE`, so the gap
is widest exactly where the review establishes least); and because **the verdict** is a property of the
cluster, not of the reference files, the same damaged references tree can flag on one cluster and pass
silently on another — which questions are `na` differs from one cluster to the next. **A clean
run is evidence the references were intact for that cluster, not that they are intact.**

## Markdown-only report

1. **Header** — cluster, region, K8s version, node count, mode.

2. **Executive Summary** — technical overall (or `NOT VIABLE` / `WITHHELD`), the pillar table, top 3 priorities.
3. **Coverage & method** — for each pillar: `score (coverage: applicable/total)`. State that governance
   questions were Not Assessed.
4. **Detailed findings per pillar** — critical / improvement / passing, each citing the question id and the
   `detail` from its JSONL line.
5. **Cost Opportunities** — from cost-analysis.md. Label the Cost pillar score as **cost hygiene**
   and state, next to it, that Spot, Graviton and Extended Support are reported here as narrative
   opportunities and are **not** in that score, together with the cluster's actual posture on all
   three. A bare Cost number reads as "no cost levers taken", which it does not measure — a 100%
   Spot + Graviton cluster scores identically to one on neither. See the disclosure block at the top
   of [references/cost-optimization.md](cost-optimization).
6. **Governance** — the list of Not Assessed questions.
7. **Action Plan** — immediate / short-term / strategic.

Report header block:

```
EKS Well-Architected Review — <cluster>
Region: <region> | Kubernetes: <version> | Mode: <the renderer's label, one of the seven strings in Step 3>
Linux nodes: <count> (<ready> Ready) | Workload pods: <count> (<running> Running)   # from liveness, always shown

Technical Score: <.technical_overall verbatim>
# A number with its Rating, or the withholding string exactly as the reducer emitted it:
#   "NOT VIABLE — no data plane" | "NOT HEALTHY — no Linux node is Ready"
#   "WITHHELD (insufficient pillar coverage)"
# Never substitute liveness.suppressed_overall here.

| Pillar                  | Score        | Coverage | Risk (from score) |
|-------------------------|--------------|----------|--------|
| Operational Excellence  | X/100        | a/t      | LOW    |
| Security                | X/100        | a/t      | MEDIUM |
| Reliability             | X/100        | a/t      | HIGH   |
| Performance Efficiency  | X/100        | a/t      | LOW    |
| Cost Optimization       | X/100        | a/t      | MEDIUM |

Governance: Not Assessed
```

## Scoring model detail: buckets, states, bands and pillar weights

- **Bucket rule** (inside every detection): percentage ≥90 → `all`, ≥70 → `most`, >0 → `some`, 0 → `none`;
  boolean/presence true → `all`, false → `none`; nothing applicable to measure → `na`. `podsec-1` to
  `podsec-5` are not banded: one offending container or pod answers `none`, and only zero answers `all`.
- **State → score:** all=100, most=75, some=50, none=0. `na` and `unknown` are excluded.
  A control that is entirely absent earns nothing — there is no participation floor. `unknown` is legal
  on the **governance track only**; a measured record carrying it is a bug, and the reducer refuses it.
- **`na` is the only not-applicable token**, on both the measured and the governance track. Not
  `not-applicable`, not `n/a`, not an empty state. The reducer validates the enum before it scores
  anything, and any other spelling costs you the whole reduce step: it prints `illegal state value(s) …
  legal: all most some none na; unknown is legal on the governance track ONLY` and exits 1, having
  written nothing. Fix the scorer that emitted it rather than re-running.
  `na` is excluded from **both** the numerator and the denominator — it does not dilute the score,
  it leaves the question out of it, and the coverage figure is what discloses how many were left out. (A
  nonzero score for `none` would put a hard floor under every pillar and compress
  populated clusters into a narrow band regardless of how bad they were.)
- **A band can be bought with Low-severity items — never read one as a risk summary.** Weights are
  relative *within* a pillar, so where the Lows outnumber the Highs they dominate: Performance
  Efficiency's 8 Low questions carry 8 of its 15 severity points against 3 for its one High question
  (`perf-1`, resource requests). Clearing only the Lows lifts that pillar from Poor to Good — and the
  Risk column, being the score restated, from HIGH to LOW — while `perf-1` still reports most containers
  with no requests at all. Report the High-severity findings directly; the band summarises the
  arithmetic, not the exposure.
- **Pillars are averaged equally although they are not comparable in size — disclose this.** The five hold
  9 to 42 measured questions — 9 to 41 that can ever apply, since the retired `sec-31` is always Not
  Applicable — and 15 to 89 reachable severity points (Performance Efficiency 15, Cost 18,
  Operational Excellence 33, Reliability 44, Security 89), and each still contributes one fifth of the
  overall. A question's pull on the headline is its weight ÷ its pillar's weight ÷ 5, so one
  Medium-severity Cost question moves it several times as far as one High-severity Security question:
  `cost-1` (ResourceQuotas, 2 of Cost's 18) pulls over three times as hard as `sec-2` (the Kubernetes API
  server open to `0.0.0.0/0`, 3 of Security's 89). **Take priority from severity weight** — what the
  report's Top priorities and improvement plan are ordered by — never from what would move the number most.

## Platform-credited answers

**Platform-credited answers must be counted too, per pillar and in total.** On an EKS Auto Mode cluster
some questions pass because AWS manages that function, not because anything on the cluster was measured.
Each credit is fair and documented in its own panel, but the count is what the reader cannot see — and it
is load-bearing, not cosmetic: on an all-Auto-Mode cluster, four of Operational
Excellence's answered questions can be platform credits — `ope-15`, `ope-16`, `lens-1`, `lens-7` — and
at 13 of 18 answered, removing them takes coverage from 72% to 50%, which is exactly the publication gate: the gate
withholds at `applicable*2 < total`, so 9 of 18 still publishes and 8 of 18 does not. One more credit and
the pillar would publish no number at all. That is how little slack the count is hiding. **The count
is computed from `results.jsonl`, never from a hand-maintained list of ids** — such a list would drift
the moment a scorer gained or lost an Auto Mode branch. A record is a platform credit when all four of
these hold:

1. `track == "measured"`;
2. `state` is `all` or `most` — the states the report shows as a pass;
3. its `detail` mentions Auto Mode (case-insensitive `auto mode`), the only platform the scorers grant
   credit for today; and
4. its `detail` does **not** begin with a measured ratio (`^\s*\d+\s*/\s*\d+`). A leading `N/M` is what
   `b()` emits when the question counted objects, so such a question passed on its own measurement even
   where the detail also names Auto Mode: `sec-21`'s `11/11 encrypted (cluster vols) — every EC2 node is an
   EKS Auto Mode node …` is measured, while `sec-30`'s `every EC2 node is an EKS Auto Mode node, where SSH
   and the SSM agent are not available at all …` is credited. `sec-4`'s mixed-mode caveat (`— but 3 of 4
   EC2 nodes are EKS Auto Mode nodes, whose enforcement is … not enabled …`) never reaches rule 4: that
   answer is capped at `some` wherever its ratio would bucket higher, so rule 2 already keeps it out.
   Rule 4 is what separates `sec-21` from records that clear rules
   1–3 with no leading ratio — `lens-1`, `lens-2`, `lens-3`, `lens-7`, `ope-15`, `ope-16`, `rel-4` and `sec-30`
   are examples, and they are counted. Those ids illustrate the rule; trust the rule, not the list.

The per-pillar denominator is that pillar's `applicable` in `scores.json` (on a fresh reduce, the count of
its measured records with a state other than `na`; the renderer does not re-check it); the total is the sum
across the five pillars. Coverage without the
credits is `floor((applicable − credited) × 100 / total)`, the reducer's own formula with the credits
removed from the numerator.

## Report content read from SKILL.md and from this file

**SKILL.md's *Framework areas with no question at all* list is report content, not maintainer notes.** `assets/render-report.py` reads the lines between
the `NOT-ASSESSED-AREAS` markers and the `NOT-ASSESSED-NARROWER` markers in SKILL.md and prints all of them in
the report's method section, so the reader sees the same boundary you do. Edit the list in SKILL.md and the
report follows. A gap that lives only in SKILL.md is a gap the reader takes for a pass — a report that
carried the Sustainability item alone would leave "incident response", "failure management", "service
quotas" and "financial management" nowhere in the rendered HTML, beside a Security score that looks
complete.

The two bullets in §*Scoring model detail: buckets, states, bands and pillar weights* — pillars averaged equally, and a band that can be bought with Low-severity items —
are findings about this skill's own arithmetic, and they are worth nothing if the maintainer is the only
one who reads them. `assets/render-report.py` prints the paragraph between the `SCORE-DISCLOSURE` markers
**verbatim, directly under the headline score**, on every report. Edit it in SKILL.md and the report follows.

All six marked blocks — `SCORE-DISCLOSURE`, `PLATFORM-CREDIT-NOTE`,
`PLATFORM-CREDIT-NONE` and the two scope blocks under *Framework areas with no question at all* in
SKILL.md, and `SCOPE-PLATFORMS` under *What counts as "an EKS cluster" here* in this file — are
**required** report inputs, not optional ones. A missing or empty marker pair is a renderer error: it must
say so in the report and exit non-zero rather than fall back to a shorter disclosure, because printing
less than the skill says is the defect these blocks exist to close.
