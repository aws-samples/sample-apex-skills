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

**25 questions** — IaC, GitOps, monitoring, logging, upgrade management, managed node groups, EKS addons

Scoring is **deterministic** — run the scorer block below; each measured question prints
`all`/`most`/`some`/`none`/`na` from `jq`. Governance questions (process-only) emit `unknown` in `auto`
mode. The per-question sections that follow give rationale and remediation for writing findings.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** They agree today — every `🔬 AUTO-DETECTABLE` section is emitted
> `measured` and every `✋ ASK USER` section is emitted `governance` — and if an edit ever makes them
> disagree, the SCORER IS AUTHORITATIVE: answer the question from the collected data. Use the prose
> for rationale and remediation wording only.

---

## Operational Excellence scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh operational-excellence "$WORK"` extracts this block and runs it. Do
not paste it into a shell: it defines shell functions (`emit`, `g`, `m`…) and calls them once per
question, and a Bash permission rule matches literal command text — so no rule can match a function name
and every call prompts, or fails outright under a no-prompt policy. Appends one JSONL line per question to
`$WORK/results.jsonl`.

The `m`/`m2`/`m3` thresholds are the determinism guarantee and are not yours to edit. In `interactive`
mode the governance answers arrive from `$WORK/governance.tsv`, which `score.sh` substitutes into the `g`
calls as it extracts them — see SKILL.md Step 6. Do not hand-edit a `g` call.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end;'
emit(){ printf '{"pillar":"operational-excellence","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Three inputs, for a question whose verdict depends on compute MODE as well as compute state:
# deciding whether "no managed node groups" is a finding needs the nodegroup list, the Auto Mode
# flag (cluster.json) and a Fargate signal (nodes.json) — on Auto Mode and Fargate the absence of
# node groups is correct by design, not drift. In jq, `input` yields f2 then f3 in order.
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

g ope-1
m2 ope-2 deployments addons 'input as $ad|[.items[].metadata.name] as $dn|($ad.addons//[]) as $ao|([ "aws-load-balancer-controller","external-dns","ebs-csi"]|map(select(. as $x|($dn|any(test($x))) or ($ao|any(test($x)))))|length) as $ok| b($ok;3)+"~\($ok)/3 integrations"'
m ope-3 deployments 'if ([.items[]|select((((.metadata.namespace//"")|test("argocd|argo-cd|flux-system|fluxcd")) or ((.metadata.name//"")|test("argocd|argo-cd|fluxcd"))) or (((.metadata.namespace//"")=="flux-system") and ((.metadata.name//"")|test("source-controller|kustomize-controller|helm-controller|notification-controller"))))]|length)>0 then "all~gitops present" else "none~no gitops" end'
g ope-4
# ope-5 searches DaemonSets and container IMAGES as well as Deployment names. CloudWatch Container
# Insights ships its agent as a DaemonSet, and Amazon Managed Prometheus is scraped by an ADOT collector
# -- both are legitimate, AWS-recommended monitoring that a Deployment-name-only search misses entirely,
# on a High-severity question.
# DUPLICATED PROGRAM -- EDIT BOTH OR NEITHER. The jq below is byte-identical to rel-13's, at
# references/reliability.md:67. Nothing enforces that; there is no shared definition and no test
# that compares them. If they drift, ONE cluster fact gets TWO verdicts: this pillar reports the cluster
# monitored while Reliability reports it unmonitored, both from the same deployments/daemonsets/pods
# files, and no report surface flags the contradiction -- the reader is left with two findings that
# cannot both be true. references/reliability.md's rel-16 documents that failure in its live form: its
# mesh pattern differs from the Security pillar's sec-27, so one cluster already gets two mesh verdicts.
m3 ope-5 deployments daemonsets pods 'input as $ds|input as $p|(([.items[]?|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))]|length) + ([$ds.items[]?|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry|node-exporter";"i"))]|length) + ([$p.items[]?|.spec.containers[]?.image|select(test("prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel";"i"))]|length)) as $n| if $n>0 then "all~\($n) monitoring workload(s)/image(s)" else "none~none" end'
m ope-6 cluster '([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]]|unique|length) as $ok| b($ok;5)+"~\($ok)/5 log types"'
m2 ope-7 daemonsets nodes 'input as $n|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0) then "na~no DaemonSets possible on Fargate compute" elif ([.items[]|select(.metadata.name|test("node-exporter"))]|length)>0 then "all~node-exporter" else "none~none" end'
m2 ope-8 daemonsets nodes 'input as $n|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0) then "na~DaemonSet log forwarding impossible on Fargate; fargate-4 scores the sidecar log router instead" elif ([.items[]|select(.metadata.name|test("fluent"))]|length)>0 then "all~log forwarder" else "none~none" end'
g ope-9
m ope-10 deployments 'if ([.items[]|select(.metadata.name|test("cni-metrics-helper"))]|length)>0 then "all~cni metrics helper" else "none~none" end'
m2 ope-11 cloudtrail cluster 'input as $cl|((($cl.cluster.arn//"")|split(":"))[3]//"") as $rg|((.trailList//[])|length) as $t|[(.trailList//[])[]|select((.IsMultiRegionTrail==true) or ((.HomeRegion//"")==$rg))] as $cov| if $t==0 then "none~no trail" elif ($cov|length)==0 then "none~\($t) trail(s) exist but none is multi-region or homed in \($rg)" else "all~\($cov|length)/\($t) trail(s) cover \($rg) (configuration only — IsLogging requires get-trail-status, which this review does not collect)" end'
m ope-12 cluster '"na~same signal as ope-6 (which already counts audit among the 5 log types) and sec-26 (deduplicated)"'
g ope-13
g ope-14
# ope-15 scores node COVERAGE. It used to pass on the mere existence of one managed node group, so a
# cluster with 1 MNG and everything else Karpenter-provisioned read as fully managed. Nodes in an MNG
# carry the eks.amazonaws.com/nodegroup label, so the ratio is measurable from data already collected.
# AUTO MODE ANSWERS `all`, NOT `na`, and the distinction is the point. `na` says "this question does not
# apply"; `all` says "the control is met". On an Auto Mode cluster the control IS met, by a mechanism
# AWS recommends over managed node groups: "EKS Auto Mode launches and manages the lifecycle of these
# EC2 instances, scaling and optimizing the data plane ... and automatically replacing any unhealthy
# nodes ... handles cluster upgrades and OS updates automatically by gracefully replacing the nodes"
# (aws.amazon.com/blogs/containers/getting-started-with-amazon-eks-auto-mode/), and Auto Mode nodes are
# one of the three EKS node types alongside managed node groups and self-managed nodes
# (docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html). Nothing about the node lifecycle
# is left to the operator, so scoring this `none` — as it did, for 0 managed node groups — marked a
# cluster down for using the newer AWS mechanism, and SKILL.md Step 3 already said the intent was `all`.
# This is deliberately NOT the `na` that ope-16, lens-7 and net-3 use for Auto Mode: there the SUBJECT
# is absent (there are no add-ons to manage, no prefix delegation to configure), so there is nothing to
# score. Here the subject — nodes — exists and is managed. `na` would also drop OpEx below the 50%
# coverage gate on an Auto Mode cluster and withhold the whole pillar band, which is a second reason it
# is the wrong state, though not the reason for choosing `all`.
# A hybrid cluster (Auto Mode PLUS managed or self-managed node groups) is supported by EKS and is not
# marked down here either; the managed-node-group and EC2 node counts are reported in the detail so the
# reader can see the mix. Auto Mode nodes carry no eks.amazonaws.com/nodegroup label, so a ratio over
# this denominator cannot separate them from genuinely self-managed nodes and must not pretend to.
m3 ope-15 nodegroups nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/nodegroup"]//"")!="")]|length) as $mng|((.nodegroups//[])|length) as $ng| if ($cl.cluster.computeConfig.enabled==true) then "all~EKS Auto Mode manages the node lifecycle (computeConfig.enabled=true): AWS launches, patches, upgrades and replaces the nodes, so a managed node group is not the mechanism here (\($t) EC2 node(s), \($ng) managed node group(s) alongside Auto Mode)" elif $t==0 then "na~no EC2 nodes" elif $ng==0 then "none~0 managed node groups (\($t) EC2 node(s) are self-managed or Karpenter-provisioned)" else b($mng;$t)+"~\($mng)/\($t) EC2 nodes in a managed node group (\($ng) MNG)" end'
m2 ope-16 addons cluster 'input as $cl| if ($cl.cluster.computeConfig.enabled==true) then "na~auto mode delivers CNI/DNS/LB/storage as core components, not add-ons" else ((.addons//[]) as $a|([ "vpc-cni","coredns","kube-proxy"]|map(select(. as $x|$a|any(.==$x)))|length) as $ok| b($ok;3)+"~\($ok)/3 core addons") end'
# ope-17 tests the fields its title names. It asked about `backoffLimit` and `completions` while testing
# `activeDeadlineSeconds` and `backoffLimit`, so a Job configured with exactly what the question asked for
# scored `none`. A deadline is an equally valid bound, so either satisfies the second half.
m ope-17 jobs '[.items[]?] as $j|($j|length) as $t|([$j[]|select((.spec.backoffLimit!=null) and ((.spec.completions!=null) or (.spec.activeDeadlineSeconds!=null)))]|length) as $ok| if $t==0 then "na~no Jobs" else b($ok;$t)+"~\($ok)/\($t) Jobs bounded (backoffLimit + completions or a deadline)" end'
m ope-18 cronjobs '[.items[]?] as $c|($c|length) as $t|([$c[]|select(((.spec.concurrencyPolicy//"Allow")!="Allow") and (.spec.failedJobsHistoryLimit!=null))]|length) as $ok| if $t==0 then "na~no CronJobs" else b($ok;$t)+"~\($ok)/\($t) CronJobs guarded (concurrencyPolicy!=Allow, failedJobsHistoryLimit set)" end'
# fargate-1 emits `unknown`, not `na`, when the data was never collected. `na` means "does not apply" and is
# excluded from scoring entirely, so using it for "we did not look" quietly inflated coverage -- and this
# question's own comment already said not to report it as not-applicable.
# fargate-1 is now MEASURED from describe-fargate-profile, not answered `na`. A selector naming only a
# namespace captures every pod in it, including ones that should run on EC2; adding labels makes the
# placement deliberate. This used to report `na~NOT ASSESSED`, which excluded it from scoring entirely --
# "we did not look" dressed up as "does not apply".
m2 fargate-1 fargate fargateprofiles 'input as $fp|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$fp.profiles[]?] as $ps|($ps|length) as $t|([$ps[]|select([.selectors[]?|select((.namespace//"")!="" and (((.labels//{})|length)>0))]|length>0)]|length) as $ok| if $t==0 then "none~fargate profiles exist but none could be described" else b($ok;$t)+"~\($ok)/\($t) profiles select by namespace AND labels" end) end'
# fargate-2 / fargate-4 — pod selection resolves POD -> NODE, not a pod label.
# These previously selected pods by `.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate"`.
# AWS documents `compute-type` on Fargate NODES; on a POD the only related label is
# `eks.amazonaws.com/fargate-profile`, and the docs describe that as a label YOU ADD to disambiguate
# when a pod matches several profiles — an input, not a guaranteed auto-applied output. So the old
# selector matched zero pods on a real Fargate cluster and silently no-op'd to `na`: a check that
# cannot match must not report success. Joining on `.spec.nodeName` uses the documented node label
# instead, which is what the fixtures and the rest of this skill already rely on.
m3 fargate-2 fargate pods nodes 'input as $p|input as $n|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")|.metadata.name]) as $fg|([$p.items[]?|select((.spec.nodeName//"") as $nn|$fg|index($nn))|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory)]|length) as $ok| if $t==0 then "na~no pods resolved to a Fargate node" else b($ok;$t)+"~\($ok)/\($t) fargate pod requests" end) end'
# fargate-3 emits `unknown`, not `na`, when the data was never collected. `na` means "does not apply" and is
# excluded from scoring entirely, so using it for "we did not look" quietly inflated coverage -- and this
# question's own comment already said not to report it as not-applicable.
# fargate-3 is now MEASURED. Every profile needs a pod execution role to run at all, so presence alone is
# a weak bar; sharing ONE role across every profile means any Fargate pod inherits every profile's
# permissions, which is the thing worth reporting.
m2 fargate-3 fargate fargateprofiles 'input as $fp|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$fp.profiles[]?] as $ps|($ps|length) as $t|([$ps[]|select(((.podExecutionRoleArn//"")|length)>0)]|length) as $ok|([$ps[]|.podExecutionRoleArn//""]|unique|length) as $distinct| if $t==0 then "none~fargate profiles exist but none could be described" elif $ok<$t then b($ok;$t)+"~\($ok)/\($t) profiles have a pod execution role" else (if $distinct>1 then "all~\($t)/\($t) profiles have a pod execution role (\($distinct) distinct)" else "most~\($t)/\($t) profiles have a pod execution role, but all share one — a per-profile role limits blast radius" end) end) end'
# fargate-4 — the DOCUMENTED Fargate logging mechanism is the built-in log router, configured by a
# ConfigMap named `aws-logging` in namespace `aws-observability`. AWS: "you don't explicitly run a
# Fluent Bit container as a sidecar, but Amazon runs it for you. All that you have to do is configure
# the log router." Crediting only a sidecar meant a correctly-configured cluster could never pass —
# and the ConfigMap was not even collected. A sidecar is still accepted as an alternative path.
# fargate-4 requires an [OUTPUT] section, not merely a non-empty ConfigMap. AWS: "At least one
# supported Output plugin has to be provided in the ConfigMap to enable logging. Filter and Parser
# aren't required to enable logging."
# (docs.aws.amazon.com/eks/latest/userguide/fargate-logging.html)
# Counting data keys credited a ConfigMap holding only filters.conf or parsers.conf as `all`, while
# Fargate ships no logs at all for it — a pass on a cluster with logging switched off. Also matched
# case-insensitively, because the same doc states "The keys are case-insensitive".
# fargate-4 requires the [OUTPUT] section under the `output.conf` KEY. It used to join every data value
# and grep for [OUTPUT] anywhere, so an [OUTPUT] placed under `filters.conf` scored `all` -- and AWS
# rejects that config, meaning logging is off. The rule ("[FILTER] must be under filters.conf", and the
# same for the others) is quoted in this file's own remediation; the detection did not implement it.
m3 fargate-4 fargate awslogging pods 'input as $cm|input as $p|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else (($cm.data//{}) as $d|(($d["output.conf"]//"")|test("\\[OUTPUT\\]";"i")) as $has_out|(($d|keys)|length) as $keys|([$p.items[]?|select([.spec.containers[]?.name]|any(test("fluent")))]|length) as $side| if $has_out then "all~aws-observability/aws-logging log router with an [OUTPUT] destination" elif $keys>0 then "some~aws-logging ConfigMap exists but declares no [OUTPUT] under output.conf, so Fargate ships no logs" elif $side>0 then "most~\($side) pod(s) run a fluent sidecar; Fargate has a built-in log router and the documented path is the aws-logging ConfigMap" else "none~no aws-logging ConfigMap in aws-observability and no fluent sidecar" end) end'
# lens-1 asks whether node problems are DETECTED, and Node Problem Detector is one way to do it. On an
# Auto Mode cluster AWS does it, so this answers `all` for the same reason ope-15 does — the control is
# met by an AWS-managed component, not inapplicable. AWS: "the node monitoring agent and automatic node
# repair ... are automatically enabled with EKS Auto Mode compute"
# (docs.aws.amazon.com/eks/latest/userguide/node-health.html); "Customers don't need to also install the
# NMA when using EKS Auto Mode, because it is included in the Auto Mode nodes' ... AMIs ... the feature
# is enabled by default and is always on"
# (aws.amazon.com/blogs/containers/amazon-eks-introduces-node-monitoring-and-auto-repair-capabilities/);
# and "Node monitoring agent" is listed among the capabilities Auto Mode delivers in place of add-ons
# (docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html). The agent runs as a systemd service in the
# AMI rather than a DaemonSet, so requiring a DaemonSet named node-problem-detector is asking an Auto
# Mode cluster to duplicate, as a pod, something it already runs below the pod layer. The Linux-only
# limitation on those features does not bite: Auto Mode nodes are Bottlerocket-based Linux.
m3 lens-1 daemonsets nodes cluster 'input as $n|input as $cl|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2|(([$n.items[]?]|length)>0) as $any| if ($cl.cluster.computeConfig.enabled==true) then "all~auto mode bakes the EKS node monitoring agent into the node AMI and enables automatic node repair by default, so node problem detection and node replacement are AWS-managed" elif ($any and $ec2==0) then "na~no DaemonSets possible on Fargate compute" elif ([.items[]|select(.metadata.name|test("node-problem-detector|npd"))]|length)>0 then "all~NPD" else "none~none" end'
g ope-19
m2 lens-7 addons cluster 'input as $cl| if ($cl.cluster.computeConfig.enabled==true) then "na~auto mode delivers CNI/DNS/LB/storage as core components, not add-ons" elif ((.addons//[])|any(.=="vpc-cni")) then "all~vpc-cni managed" else "none~not managed" end'
```

**Governance (interview in `interactive` mode):** ope-1 (IaC), ope-4 (templating), ope-9 (auth-failure
alarms), ope-13 (upgrade plan), ope-14 (non-prod test env), ope-19 (capacity planning).

---

## Infrastructure as Code

### ope-1: Do you provision your EKS cluster and worker nodes using Infrastructure as Code (IaC) tools such as Terraform, CloudFormation, or AWS CDK?

**Detection:** ✋ ASK USER

> IaC ensures reproducible, version-controlled infrastructure.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Adopt Terraform, CDK, or CloudFormation for cluster provisioning. Store all K8s manifests in Git and deploy via CI/CD pipelines.

---

### ope-2: Are AWS integrations (Load Balancer Controller, External DNS, EBS CSI Driver) deployed as EKS add-ons or controllers?

**Detection:** 🔬 AUTO-DETECTABLE

> AWS integrations enable Kubernetes-native management of AWS resources.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for: aws-load-balancer-controller, external-dns, ebs-csi
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy AWS Load Balancer Controller, External DNS, and EBS CSI Driver as Helm charts or EKS add-ons: `aws eks create-addon --cluster-name <name> --addon-name aws-ebs-csi-driver`.

---

### ope-3: Do you use GitOps workflows (ArgoCD, Flux) to minimize direct kubectl access?

**Detection:** 🔬 AUTO-DETECTABLE

> GitOps reduces human error and provides audit trails for all changes.

**Remediation:** Implement GitOps workflows (ArgoCD, Flux) to eliminate direct kubectl access. Restrict kubectl to break-glass scenarios only.

---

### ope-4: Are you using Helm charts or Kustomize for Kubernetes manifest templating?

**Detection:** ✋ ASK USER

> Templating enables consistent configuration across environments.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Adopt Helm for application packaging: `helm create <chart>`. Use values files per environment and store charts in a Helm repository.

---

## Centralized monitoring and logging

### ope-5: Are control plane metrics monitored using CloudWatch Container Insights or Prometheus?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. History: this remediation used to be one
     line — "enable CloudWatch Container Insights: aws eks create-addon --addon-name
     amazon-cloudwatch-observability" — with no --cluster-name/--region (would fail if pasted as
     given), no mention that the addon's pods need an IAM role before they can publish anything, and
     no verification. Found during a Fix-3 audit for the same defect class as ope-6/ope-11/rbac-1: a
     bare instruction with no working command, no prerequisite, no verification, on a High-severity
     question. Verified 2026-09-11 against
     docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html (required IAM
     permissions) and repost.aws/knowledge-center/eks-monitoring-cloudwatch-observability. -->

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

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. History: this remediation used to say
     "enable it in the EKS console" with no CLI, no mention that the update is asynchronous, and no
     retention guidance — the weakest remediation in the file on its highest-severity question. Now
     gives the exact update-cluster-config command, the describe-update poll (same pattern sec-38
     documents for its own async cluster update, in data-protection.md, so the skill teaches one
     pattern rather than two), and a put-retention-policy command so enabling `audit`/`api` on a busy
     control plane doesn't create open-ended CloudWatch Logs ingestion and storage cost. Verified
     2026-09-11 against docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html (exact
     command and log group name `/aws/eks/<cluster-name>/cluster`) and the CLI reference for
     `logs put-retention-policy`. -->

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

**Remediation:** `audit` in particular is usually the highest-volume of the five log types — AWS: "This
log type usually has the highest volume of log events" — and CloudWatch Logs charges for both ingestion
and storage of whatever you enable, with no cap unless you set one. Set retention as part of turning
logging on, not as a follow-up:

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

**Remediation:** Deploy Prometheus Node Exporter as a DaemonSet: `helm install node-exporter prometheus-community/prometheus-node-exporter`. Create Grafana dashboards for CPU, memory, disk.

---

### ope-8: Are application logs forwarded to a centralized system (Fluent Bit, Fluentd, CloudWatch)?

**Detection:** 🔬 AUTO-DETECTABLE

> Centralized logging enables cross-service troubleshooting and audit trails.

**Remediation:** Deploy Fluent Bit as a DaemonSet: `helm install fluent-bit fluent/fluent-bit --set output.cloudWatch.enabled=true`. Configure log routing to CloudWatch or Elasticsearch.

---

### ope-9: Have you created CloudWatch alarms or alerts for API server 403/401 responses?

**Detection:** ✋ ASK USER

> Monitoring auth failures detects unauthorized access attempts.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Create CloudWatch metric filters on EKS audit logs for 403/401 responses. Set alarms with SNS notifications for threshold breaches.

---

### ope-10: Is the CNI metrics helper deployed to monitor VPC CNI IP address allocation and ENI usage?

**Detection:** 🔬 AUTO-DETECTABLE

> CNI metrics prevent IP exhaustion which can cause pod scheduling failures.

**Remediation:** Deploy the CNI metrics helper: `kubectl apply -f https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.19.2/config/master/cni-metrics-helper.yaml`. Monitor IP allocation in CloudWatch.

---

### ope-11: Are you using AWS CloudTrail to audit EKS API calls and IRSA actions?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. History: this remediation used to say
     "enable it in all regions" with no command and no cost context, and told the reader to "create
     CloudTrail event selectors for EKS API calls and IRSA assume-role events" — both are management
     events and every trail records management events by default, so that instruction implied config
     work that a default trail doesn't need. Now gives the create-trail/start-logging commands, states
     the real cost model (first management-event copy per Region is free; data events are billed from
     the first event, with no free tier), and adds get-trail-status because the scorer's own comment
     says it checks configuration only and cannot see IsLogging. Verified 2026-09-11 against
     docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-trail-manage-costs.html and the CLI
     reference for create-trail/get-trail-status. -->

> CloudTrail provides API-level audit logging for compliance.

**Remediation:** A multi-region trail's default **management events** already cover EKS control-plane
API calls and IRSA's `sts:AssumeRoleWithWebIdentity` — no custom event selector is needed for either.
**Cost:** AWS delivers the first copy of management events in each Region free of charge, so one
multi-region trail costs nothing extra for management events alone — "if you have one trail that is
logging management events, there are no CloudTrail charges to log management events on that trail."
Data events are different: "For data events, all deliveries incur CloudTrail costs, including the
first" — so only turn on data events (S3 object-level, Lambda invoke, etc.) if you specifically need
that granularity, and expect an ongoing per-event charge with no free tier
(https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-trail-manage-costs.html):

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

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. History: this remediation used to say
     "enable it in the EKS console" and duplicate ope-6's fix in different words, even though the
     scorer for this id has always returned a flat `na~same signal as ope-6 (which already counts
     audit among the 5 log types) and sec-26 (deduplicated)` — it reads the same
     cluster.logging.clusterLogging field ope-6 and sec-26 already score and never computes an
     independent verdict from it. The old "Commands"/"Analysis: percentage-based scoring" boilerplate
     below it was therefore describing a calculation this question never performs, on a High-weighted
     question with no path to `all`/`none`. Rather than write a THIRD hand-maintained copy of the same
     enable-audit-logging procedure — three copies is a drift surface no test catches, and this
     project already has one drifted copy of its severity map — this cross-references ope-6 instead.
     2026-09-11. -->

> This question asks specifically about Kubernetes audit logging, but that fact is already measured
> twice elsewhere from the same `cluster.logging.clusterLogging` field: ope-6 counts `audit` among its
> 5 control plane log types, and sec-26 (Security pillar, governance-compliance) scores the same
> on/off fact again. Rather than compute a third verdict from one field, this question always answers
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

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Create a documented upgrade schedule aligned with the EKS version calendar. Test upgrades in non-prod first. Use `eksctl upgrade cluster` or Terraform.

---

### ope-14: Do you have a non-production test environment for validating EKS upgrades before production?

**Detection:** ✋ ASK USER

> Test environments prevent upgrade-related outages in production.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Create a dedicated staging EKS cluster in a separate AWS account. Test all upgrades and add-on updates there before applying to production.

---

### ope-15: Are worker nodes managed using EKS Managed Node Groups?

**Detection:** 🔬 AUTO-DETECTABLE

> Managed Node Groups automate node patching, updates, and replacement.
> **EKS Auto Mode satisfies this question without any node group.** It is one of the three EKS node
> types, and AWS launches, patches, upgrades and replaces its nodes for you — so a cluster with
> `computeConfig.enabled: true` scores `all` here, not `none`, and has nothing to migrate.

**Commands:**
```bash
aws eks list-nodegroups --cluster-name <CLUSTER> --region <REGION>
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Migrate self-managed nodes to EKS Managed Node Groups: `eksctl create nodegroup --cluster <name> --managed`. This automates patching and updates.

---

### ope-16: Are core EKS add-ons (VPC CNI, CoreDNS, kube-proxy) managed as EKS managed add-ons?

**Detection:** 🔬 AUTO-DETECTABLE

> EKS managed add-ons receive AWS-managed updates and configuration.

**Commands:**
```bash
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# Check for: vpc-cni, coredns, kube-proxy
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Migrate VPC CNI, CoreDNS, and kube-proxy to EKS managed add-ons: `aws eks create-addon --cluster-name <name> --addon-name vpc-cni`.

---

## Business Continuity

### ope-17: Are Kubernetes Jobs configured with backoffLimit and completions?

**Detection:** 🔬 AUTO-DETECTABLE

> Proper Job configuration prevents infinite retries and ensures completion tracking.

**Commands:**
```bash
kubectl get jobs -A -o json
# Check spec.backoffLimit and spec.completions
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add `backoffLimit` and `completions` to all Job specs. Example: `spec.backoffLimit: 3, spec.completions: 1`. This prevents infinite retries.

---

## Change Management

### ope-18: Are CronJobs configured with schedule, history limits, and concurrency policy?

**Detection:** 🔬 AUTO-DETECTABLE

> CronJob configuration prevents job accumulation and concurrent execution issues.

**Commands:**
```bash
kubectl get cronjobs -A -o json
# Check spec.concurrencyPolicy, successfulJobsHistoryLimit, failedJobsHistoryLimit
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Configure CronJobs with `concurrencyPolicy: Forbid`, `successfulJobsHistoryLimit: 3`, and `failedJobsHistoryLimit: 1` to prevent job accumulation.

---

## Capacity Planning

### ope-19: Do you perform regular capacity planning reviews to ensure your EKS cluster can handle projected growth, seasonal traffic spikes, and maintain adequate resource headroom for scaling?

**Detection:** ✋ ASK USER

> Evaluate proactive capacity planning practices to prevent resource exhaustion and ensure optimal cluster performance.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Conduct quarterly capacity reviews using Prometheus metrics. Set alerts at 70% CPU/memory utilization. Plan for 30% headroom above peak usage.

---

## Fargate Profile Management

### fargate-1: Are Fargate profile namespace selectors specific (not just default/kube-system)?

**Detection:** 🔬 AUTO-DETECTABLE

> Specific selectors prevent unintended workloads from running on Fargate.

**Commands:**
```bash
aws eks describe-fargate-profile --cluster-name <CLUSTER> --fargate-profile-name <PROFILE> --region <REGION>
# Check namespace selectors specificity
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Use specific namespace selectors in Fargate profiles instead of broad defaults. Target application namespaces with label selectors for fine-grained control.

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

### fargate-3: Do Fargate profiles use per-profile execution roles (not a shared role)?

**Detection:** 🔬 AUTO-DETECTABLE

> Per-profile roles enforce least-privilege for Fargate workloads.

**Commands:**
```bash
aws eks list-fargate-profiles + describe each
# Check podExecutionRoleArn uniqueness across profiles
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Create per-profile IAM execution roles with least-privilege policies. Avoid sharing a single role across all Fargate profiles.

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
# Passes when a value contains an [OUTPUT] section. AWS: "At least one supported Output plugin has to
# be provided in the ConfigMap to enable logging. Filter and Parser aren't required."
```

**Analysis:** Boolean on the log destination, not a percentage:
- an `[OUTPUT]` plugin is declared → `all`
- the ConfigMap exists but declares no `[OUTPUT]` → `some` (Fargate ships nothing; the config is inert)
- no ConfigMap, but pods run a `fluent` sidecar → `most` (works, but not the documented path)
- neither → `none`
- no Fargate profiles → `na`

**Remediation:** Create the namespace and ConfigMap AWS looks for. The ConfigMap **must** be named
`aws-logging` in namespace `aws-observability`, and the namespace **must** carry the label
`aws-observability: enabled`:

```bash
kubectl apply -f - <<'EOF'
kind: Namespace
apiVersion: v1
metadata:
  name: aws-observability
  labels:
    aws-observability: enabled
---
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
        region <REGION>
        log_group_name /aws/eks/<CLUSTER>/fargate
        log_stream_prefix from-fluent-bit-
        auto_create_group true
EOF
```

Then grant the **Fargate pod execution role** permission to write to the destination — the log router
runs under that role, not the pod's service account.

Constraints worth knowing before you write the config:

- Only `[FILTER]`, `[OUTPUT]` and `[PARSER]` sections are accepted, under the matching keys
  (`filters.conf`, `output.conf`, `parsers.conf`). Fargate manages `Service` and `Input`; supplying
  either is rejected.
- The ConfigMap cannot exceed **5,300 characters**, and `${ENV_VAR}` substitution is not allowed.
- Changes apply to **new pods only**. Existing pods keep the configuration they started with, so
  recycle them after editing.
- Supported outputs: `cloudwatch`, `cloudwatch_logs`, `es`, `firehose`, `kinesis_firehose`, `kinesis`.
- To check whether it took effect: `kubectl describe pod <name>` and read the annotations. A failure
  shows as `Logging: LoggingDisabled: LOGGING_CONFIGMAP_NOT_FOUND`.
- There must be network egress from the cluster VPC to the log destination — relevant if you have
  narrowed the cluster security group's egress (see `net-4`).

> **Not the sidecar path.** This question previously asked whether Fargate pods ran a Fluent Bit
> **sidecar** and its remediation prescribed `amazon/aws-for-fluent-bit` with **FireLens**. Both were
> wrong: Fargate's log router is built in and needs no sidecar, and FireLens is an **Amazon ECS**
> feature that does not apply to EKS. Round-1 corrected the detection but left this prose, so a
> non-passing `fargate-4` printed the wrong fix into the customer's report.

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

**Commands:**
```bash
kubectl get daemonsets -A -o json
# Look for node-problem-detector
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Node Problem Detector as a DaemonSet: `kubectl apply -f https://raw.githubusercontent.com/kubernetes/node-problem-detector/v0.8.20/deployment/node-problem-detector.yaml`.

---

### lens-7: Is the VPC CNI addon version current and healthy?

**Detection:** 🔬 AUTO-DETECTABLE

> Outdated CNI versions miss security patches and performance improvements.

**Commands:**
```bash
aws eks describe-addon --cluster-name <CLUSTER> --addon-name vpc-cni --region <REGION>
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Update the VPC CNI addon to the latest version: `aws eks update-addon --cluster-name <name> --addon-name vpc-cni --resolve-conflicts OVERWRITE`.

---
