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

The `m`/`m2`/`m3`/`m4` thresholds are the determinism guarantee and are not yours to edit. In `interactive`
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
# Four inputs, for `ope-2`: two of its three integration slots are EKS Auto Mode CAPABILITIES
# rather than installed objects, so the verdict needs the Deployment list, the add-on list, the
# StorageClass list (an Auto Mode block-storage capability provisions nothing without one) and
# cluster.json for the capability flags. Copied byte-for-byte from the `m4` in
# references/security/identity-access.md -- same abort-on-jq-failure semantics, same emit call. Two
# copies of one helper is a drift surface; if you change either, change both.
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

g ope-1
# ope-2 credits each of its three integration slots SEPARATELY, and on EKS Auto Mode two of them are
# cluster capabilities rather than installed objects. The old form matched three name patterns against
# Deployment names and add-on names only, so an Auto Mode cluster scored `none` 0/3 for not installing
# what AWS already runs for it. The denominator is still 3 and the credit is per capability, on its own
# flag -- the three Auto Mode capability flags are separate fields and a cluster can have any subset of
# them. Sources, documentation only:
#   LOAD BALANCER SLOT -- credited when cluster.kubernetesNetworkConfig.elasticLoadBalancing.enabled is
#   true. docs.aws.amazon.com/eks/latest/userguide/auto-configure-nlb.html -- "EKS Auto Mode handles
#   Network Load Balancer provisioning by default for all services of type LoadBalancer - no additional
#   controller installation or configuration is required."
#   BLOCK STORAGE SLOT -- credited when cluster.storageConfig.blockStorage.enabled is true AND a
#   StorageClass with provisioner `ebs.csi.eks.amazonaws.com` exists. BOTH conditions, because
#   docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html says "EKS Auto Mode does not
#   create a `StorageClass` for you. You must create a `StorageClass` referencing
#   `ebs.csi.eks.amazonaws.com` to use the storage capability of EKS Auto Mode" -- the capability is on
#   but unusable without one, and crediting the flag alone would pass a cluster that can provision
#   nothing. That the controller itself is AWS's to run is documented at
#   docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html -- "You do not need to install the Amazon EBS
#   CSI controller on EKS Auto Mode clusters."
#   EXTERNAL-DNS SLOT -- STAYS MEASURED. external-dns is not an Auto Mode capability and appears in none
#   of the replaced-component lists, so its absence is a genuine gap and the detail names it as one. A
#   faithful Auto Mode cluster with a StorageClass and no external-dns therefore reads `some` 2/3, not
#   `all`: this question is not a blanket Auto Mode pass.
# The `N/3` in the detail is safe here and nowhere else in this change: ope-2 has no extractor in
# render-report.py's RESOURCES table, so resource_agreement() has nothing to cross-check it against.
m4 ope-2 deployments addons storageclasses cluster 'input as $ad|input as $sc|input as $cl|[.items[]?|.metadata.name] as $dn|(($ad.addons)//[]) as $ao|(($dn|any(test("aws-load-balancer-controller"))) or ($ao|any(test("aws-load-balancer-controller")))) as $lbdep|(($dn|any(test("ebs-csi"))) or ($ao|any(test("ebs-csi")))) as $stdep|(($dn|any(test("external-dns"))) or ($ao|any(test("external-dns")))) as $dnsdep|(($cl.cluster.kubernetesNetworkConfig.elasticLoadBalancing.enabled)==true) as $autolb|(($cl.cluster.storageConfig.blockStorage.enabled)==true) as $autobs|([$sc.items[]?|select((.provisioner//"")=="ebs.csi.eks.amazonaws.com")]|length>0) as $autosc|($lbdep or $autolb) as $lbok|($stdep or ($autobs and $autosc)) as $stok|([$lbok,$stok,$dnsdep]|map(select(.))|length) as $ok|[(if $lbdep then "aws-load-balancer-controller deployed" elif $autolb then "Auto Mode load balancing (kubernetesNetworkConfig.elasticLoadBalancing.enabled=true)" else empty end),(if $stdep then "an EBS CSI driver is deployed" elif ($autobs and $autosc) then "Auto Mode block storage (storageConfig.blockStorage.enabled=true) plus a StorageClass on ebs.csi.eks.amazonaws.com" else empty end),(if $dnsdep then "external-dns deployed" else empty end)] as $cred|[(if $lbok then empty else "no load balancer controller" end),(if $stok then empty else (if ($autobs and ($autosc|not)) then "Auto Mode block storage is enabled but no StorageClass references ebs.csi.eks.amazonaws.com, so nothing can be provisioned" else "no EBS CSI driver" end) end),(if $dnsdep then empty else "external-dns" end)] as $gap| b($ok;3)+"~\($ok)/3 integrations; credited: \(if ($cred|length)>0 then ($cred|join(", ")) else "none" end); gap: \(if ($gap|length)>0 then ($gap|join(", ")) else "none" end)"'
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
# ope-10 answers `na` ON AUTO MODE -- and this is the ONE Auto Mode conversion in this file that is NOT
# a credit. The question asks whether the CNI metrics helper is deployed TO MONITOR VPC CNI IP
# allocation and ENI usage. On Auto Mode the object is gone AND the outcome is not delivered by default,
# so `none` and `all` are both wrong: `none` would print a remediation that cannot be followed, `all`
# would claim visibility the operator does not have. `na` plus a reason naming the documented path is
# the honest answer. Sources, documentation only:
#   docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html -- "With Amazon EKS Auto Mode, you
#   don't need to install or upgrade networking add-ons. Auto Mode includes pod networking and load
#   balancing capabilities." There is therefore no VPC CNI DaemonSet on the node for a metrics helper to
#   read, which is why the old `kubectl apply -f .../cni-metrics-helper.yaml` remediation could not work.
#   docs.aws.amazon.com/eks/latest/userguide/auto-managed-component-logs.html lists "Pod networking -
#   VPC CNI IP Address Management" among the AWS-managed component log sources, then states: "EKS Auto
#   managed component logs (such as Compute, Block storage, Load balancing, and IPAM) require separate
#   configuration through log delivery", with the log type "AUTO_MODE_IPAM_LOGS". Off by default,
#   obtainable through CloudWatch Vended Logs delivery -- so the visibility is genuinely ABSENT, not
#   inapplicable, and the prose below gives that three-step setup alongside the standard-cluster path.
# THIS COSTS THE OPERATOR SOMETHING REAL, and the prose says so rather than dressing it up: IP-exhaustion
# pressure is invisible by default, and per docs.aws.amazon.com/eks/latest/userguide/auto-networking.html
# Auto Mode "defaults to using prefix delegation (/28 prefixes)", so each node reserves a block of subnet
# IPs and subnet pressure is HIGHER, not lower. `net-1` is the remaining headroom signal.
# SCOPE OF THE GATE: EVERY EC2 NODE MUST BE AN AUTO MODE NODE, not merely the cluster flag. The gate used
# to be `computeConfig.enabled` alone, which made a HYBRID cluster (Auto Mode alongside a managed or
# self-managed node group) answer `na` -- while its non-Auto-Mode nodes were provably still running the VPC
# CNI DaemonSet that the detail said did not exist. AWS supports that mix and says the add-ons stay:
#   docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html -- "However, if your cluster combines Auto
#   mode with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate,
#   these add-ons remain necessary."
#   docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html -- "AWS suggests running either
#   EKS Auto Mode or self-managed Karpenter. You can install both during a migration or in an advanced
#   configuration." So a hybrid cluster is a real configuration, not an error state.
# The membership test is the documented label -- docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html's
# supported-label table, "| eks.amazonaws.com/compute-type | auto | Identifies EKS Auto Mode managed nodes |",
# and docs.aws.amazon.com/eks/latest/userguide/associate-workload.html, "EKS Auto Mode nodes have set the
# value of the label `eks.amazonaws.com/compute-type` to `auto`." SIBLING GATE, deliberately byte-comparable
# with lens-2 and lens-3 in references/reliability.md and with ope-16, lens-1 and lens-7 below: Fargate nodes
# out of the denominator, and $t>0 required so an empty cluster is never vacuously credited. Change one,
# change all six.
# On a hybrid cluster the question now FALLS THROUGH to measuring the helper, which is the right evidence:
# `aws-node` is on the non-Auto-Mode nodes, so the cni-metrics-helper is genuinely deployable for them and
# its absence is a genuine gap. The Auto Mode nodes' share of that visibility still needs the
# AUTO_MODE_IPAM_LOGS delivery, and the hybrid arm's detail says both things.
# COVERAGE COUPLING -- DO NOT LAND THIS `na` WITHOUT ope-16 AND lens-7's `all`, AND NOTE THAT ALL THREE ARE
# NOW CONDITIONAL ON THE NODE POPULATION, not on the cluster flag. reduce.sh withholds a pillar when
# applicable*2 < total, and Operational Excellence measures 19 questions. On an ALL-AUTO-MODE cluster this
# `na` removes one question from the applicable pool (10 -> 9 of 19 = 47%, WITHHELD) and the ope-16 +
# lens-7 conversions add two back (11 of 19 = 57%, published) -- measured on automode-faithful. Splitting
# them deletes the whole Operational Excellence band from the report. On a HYBRID cluster the coupling is
# slack in the safe direction: all three fall through to measurement, so the applicable pool GROWS to 12 of
# 19 (63%) and no withholding is possible. The dangerous edit is therefore still the same one -- narrowing
# ope-16 or lens-7 back to `na` on an all-Auto-Mode cluster while leaving this `na` in place.
m3 ope-10 deployments nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "na~auto mode manages VPC CNI IP and ENI allocation itself: every EC2 node is an Auto Mode node (eks.amazonaws.com/compute-type=auto), so there is no VPC CNI DaemonSet for a cni-metrics-helper to instrument and it cannot be deployed. The equivalent visibility is the AUTO_MODE_IPAM_LOGS log type, which stays off until you configure CloudWatch Vended Logs delivery for it" elif ([.items[]|select(.metadata.name|test("cni-metrics-helper"))]|length)>0 then "all~cni metrics helper" elif ($cl.cluster.computeConfig.enabled==true) then "none~Auto Mode compute is enabled but only \($auto) of \($t) EC2 nodes are Auto Mode nodes; the rest still run the VPC CNI DaemonSet, so a cni-metrics-helper is deployable for them and none is deployed — and the Auto Mode nodes need the AUTO_MODE_IPAM_LOGS delivery on top of that" else "none~none" end'
m2 ope-11 cloudtrail cluster 'input as $cl|((($cl.cluster.arn//"")|split(":"))[3]//"") as $rg|((.trailList//[])|length) as $t|[(.trailList//[])[]|select((.IsMultiRegionTrail==true) or ((.HomeRegion//"")==$rg))] as $cov| if $t==0 then "none~no trail" elif ($cov|length)==0 then "none~\($t) trail(s) exist but none is multi-region or homed in \($rg)" else "all~\($cov|length)/\($t) trail(s) cover \($rg) (configuration only — IsLogging requires get-trail-status, which this review does not collect)" end'
m ope-12 cluster '"na~same signal as ope-6 (which already counts audit among the 5 log types) and sec-26 (deduplicated)"'
g ope-13
g ope-14
# ope-15 scores node COVERAGE. It used to pass on the mere existence of one managed node group, so a
# cluster with 1 MNG and everything else Karpenter-provisioned read as fully managed. Nodes in an MNG
# carry the eks.amazonaws.com/nodegroup label, so the ratio is measurable from data already collected.
# AUTO MODE ANSWERS `all`, NOT `na`, and the distinction is the point. `na` says "this question does not
# apply"; `all` says "the control is met". On an Auto Mode cluster the control IS met, by a mechanism
# AWS recommends over managed node groups. Source, documentation only:
# docs.aws.amazon.com/eks/latest/userguide/automode.html -- "Auto scaling: Relying on Karpenter auto
# scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to be
# deployed to run those Pods. As workloads are terminated, EKS Auto Mode dynamically disrupts and
# terminates nodes when they are no longer needed"; "Upgrades: ... EKS Auto Mode enforces a 21-day
# maximum node lifetime to ensure up-to-date software and APIs"; and Auto Mode "Chooses an appropriate
# AMI that's configured with many services needed to run your workloads without intervention". Auto Mode
# nodes are one of the three EKS node types alongside managed node groups and self-managed nodes
# (docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html). Nothing about the node lifecycle
# is left to the operator, so scoring this `none` — as it did, for 0 managed node groups — marked a
# cluster down for using the newer AWS mechanism, and SKILL.md Step 3 already said the intent was `all`.
# ope-16 and lens-7 below now answer `all` on Auto Mode for exactly this reason -- they used to say `na`,
# on the argument that the SUBJECT was absent (no add-ons to manage), and that confused "no object to
# count" with "outcome unmet". `na` is still right where the outcome genuinely is not delivered: net-3
# (no prefix delegation to configure) and ope-10 (the IPAM visibility Auto Mode does not hand over by
# default). Here the subject — nodes — exists and is managed. `na` would also drop OpEx below the 50%
# coverage gate on an Auto Mode cluster and withhold the whole pillar band, which is a second reason it
# is the wrong state, though not the reason for choosing `all`.
# A HYBRID CLUSTER IS NOT GIVEN THE ALL-AUTO-MODE ANSWER, and this question does NOT take the same
# all-nodes-auto gate as ope-16 / ope-10 / lens-1 / lens-7. Those four credit a NODE-SCOPED CAPABILITY, so
# a node without the capability must not inherit it. This one asks something different -- are the worker
# nodes MANAGED -- and on a hybrid cluster every node genuinely is managed, just not all by the same
# mechanism: AWS owns the lifecycle of the Auto Mode nodes and owns the lifecycle of the managed-node-group
# nodes. So `all` can be the right band here where it is wrong there, and the band is decided by
# ARITHMETIC over the nodes rather than by the cluster flag: managed = (Auto Mode nodes UNION
# node-group nodes), counted as a union so a node carrying both labels is never double-counted, over every
# EC2 node. What was indefensible was the flag arm's DETAIL -- "a managed node group is not the mechanism
# here" -- printed for a cluster where a managed node group was the mechanism for 2 of its 3 nodes. The
# hybrid arm names both populations with their counts instead, and a genuinely SELF-MANAGED node still
# fails: it is in neither population, so it lowers $man/$t and the band with it. A cluster whose Auto Mode
# flag is on but whose nodes carry neither label scores `none` here, correctly -- nothing is managing them.
# Sources for counting an Auto Mode node as managed, documentation only:
# docs.aws.amazon.com/eks/latest/userguide/automode.html -- "Auto scaling: Relying on Karpenter auto
# scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to be
# deployed to run those Pods"; "Upgrades: ... EKS Auto Mode enforces a 21-day maximum node lifetime".
# For counting the coexistence as legitimate rather than as drift:
# docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html -- "AWS suggests running either
# EKS Auto Mode or self-managed Karpenter. You can install both during a migration or in an advanced
# configuration."
# NO LEADING `N/M` RATIO ON ANY ARM REACHED WITH computeConfig.enabled=true. render-report.py's
# `_res_ope15` short-circuits on the cluster flag and emits a one-line `kind: field` panel (1 pass, 0
# fail), so a detail beginning "3/3" would be compared against that 1/1 and reported as a DISAGREEMENT.
# The hybrid arm therefore leads with prose and spells its counts with "of" rather than "/". The
# standard-cluster arm keeps its "\($mng)/\($t)" because the extractor takes its ratio path there and the
# two agree. `_res_ope15` still prints the Auto-Mode-only claim on a hybrid cluster; that is a
# render-report.py fix, not a scorer one.
m3 ope-15 nodegroups nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/nodegroup"]//"")!="")]|length) as $mng|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|([$ec2[]|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto") or ((.metadata.labels["eks.amazonaws.com/nodegroup"]//"")!=""))]|length) as $man|((.nodegroups//[])|length) as $ng| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "all~EKS Auto Mode manages the node lifecycle and every EC2 node is an Auto Mode node (eks.amazonaws.com/compute-type=auto): AWS launches, patches, upgrades and replaces them, so a managed node group is not the mechanism here (\($t) EC2 node(s), \($ng) managed node group(s) alongside Auto Mode)" elif $t==0 then "na~no EC2 nodes" elif ($cl.cluster.computeConfig.enabled==true) then b($man;$t)+"~Auto Mode is enabled on the cluster but not on every EC2 node: Auto Mode manages \($auto) of \($t), a managed node group manages \($mng) (\($ng) MNG), so \($man) of \($t) have an AWS-managed node lifecycle"+(if $man<$t then "; the other \($t-$man) are self-managed or Karpenter-provisioned and are what this question asks you to migrate" else "" end) elif $ng==0 then "none~0 managed node groups (\($t) EC2 node(s) are self-managed or Karpenter-provisioned)" else b($mng;$t)+"~\($mng)/\($t) EC2 nodes in a managed node group (\($ng) MNG)" end'
# ope-16 ANSWERS `all` ON AUTO MODE, not `na`, by exactly the argument ope-15 makes above -- read that
# comment first. The `na` this replaces was half right and half wrong: right that the add-on OBJECTS are
# gone, so there is nothing to count; wrong that the OUTCOME is unmet. The question asks whether the core
# add-ons are EKS-MANAGED, and AWS running those functions as service functionality is a stronger form of
# the same outcome, not an inapplicable one. Source, documentation only:
# docs.aws.amazon.com/eks/latest/userguide/auto-upgrade.html -- "Additionally, you no longer need to
# update components like: Amazon VPC CNI / AWS Load Balancer Controller / CoreDNS / `kube-proxy` /
# Karpenter / AWS EBS CSI driver" ... "EKS Auto Mode replaces these components with service
# functionality." The same page keeps the operator responsible for "Amazon EKS Add-ons" they install
# themselves, which is why the standard-cluster arm below is untouched: an Auto Mode cluster that also
# installs its own add-ons still owns those.
# THE GATE IS EVERY EC2 NODE, NOT THE CLUSTER FLAG. `computeConfig.enabled` says Auto Mode is on for the
# CLUSTER; it does not say every node is an Auto Mode node, and the add-ons Auto Mode replaces are replaced
# only on the nodes that are. AWS is explicit that on a mixed cluster they are still needed:
# docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html -- "However, if your cluster combines Auto mode
# with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate, these
# add-ons remain necessary." So the old flag gate printed "there is no add-on version left for the operator
# to manage" about a cluster whose `coredns`, `kube-proxy` and `vpc-cni` add-ons were sitting in the
# collected add-on list, load-bearing for its managed-node-group nodes. SIBLING GATE of lens-2 and lens-3
# (references/reliability.md) and of ope-10, lens-1 and lens-7 here -- same shape, same wording, same label
# test from docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html ("| eks.amazonaws.com/compute-type
# | auto | Identifies EKS Auto Mode managed nodes |"), same Fargate exclusion, same $t>0 guard. Change one,
# change all six.
# On a hybrid cluster it falls through to MEASURING the three add-ons, which is exactly the right evidence:
# they remain necessary, so whether they are EKS-managed add-ons is a real question with a real answer.
# NO RATIO IN ANY DETAIL REACHED WITH computeConfig.enabled=true, deliberately. render-report.py's
# `_res_addons` short-circuits on the cluster flag and emits a one-line `kind: field` panel (1 pass, 0
# fail), so ANY detail beginning "N/3" on such a cluster -- the all-Auto-Mode arm or the hybrid one -- would
# be compared against that 1/1 and reported as a DISAGREEMENT. Hence two measuring arms with the same
# `b($ok;3)` band and different wording: the hybrid arm leads with prose and spells the count with "of",
# and only the plain standard-cluster arm keeps the comparable "\($ok)/3" form, where the extractor takes
# its ratio path and the two agree. `_res_addons` still prints the Auto-Mode-only claim on a hybrid
# cluster, and still lists vpc-cni/coredns/kube-proxy as failing on an all-Auto-Mode one under an `all`
# verdict; teaching it the node-population branch (as `_res_rel4` already has one) is a render-report.py
# fix, not a scorer one.
m3 ope-16 addons nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|((.addons//[]) as $a|(["vpc-cni","coredns","kube-proxy"]|map(select(. as $x|$a|any(.==$x)))|length) as $ok| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "all~auto mode replaces the VPC CNI, CoreDNS and kube-proxy add-ons with service functionality that AWS updates, so these components are AWS-managed and there is no add-on version left for the operator to manage" elif ($cl.cluster.computeConfig.enabled==true) then b($ok;3)+"~Auto Mode is enabled but only \($auto) of \($t) EC2 nodes are Auto Mode nodes, so vpc-cni, coredns and kube-proxy remain necessary for the rest: \($ok) of the 3 are EKS managed add-ons" else b($ok;3)+"~\($ok)/3 core addons" end)'
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
# met by an AWS-managed component, not inapplicable. Sources, documentation only:
# docs.aws.amazon.com/eks/latest/userguide/node-health.html -- "the node monitoring agent and automatic
# node repair ... are automatically enabled with EKS Auto Mode compute" and, decisively, "EKS Auto Mode
# compute includes the node monitoring agent. For other EKS compute types, you can add the node
# monitoring agent as an EKS add-on or you can manage it with Kubernetes tool[ing]";
# docs.aws.amazon.com/eks/latest/userguide/automode.html -- "Managed Components: EKS Auto Mode includes
# Kubernetes and AWS cloud features as core components that would otherwise have to be managed as
# add-ons. This includes built-in support for Pod IP address assignments, Pod network policies, local DNS
# services, GPU plug-ins, health checkers, and EBS CSI storage." So on Auto Mode the agent ships with the
# node rather than as a workload, and requiring a DaemonSet named node-problem-detector is asking an Auto
# Mode cluster to duplicate, as a pod, something it already runs below the pod layer. The Linux-only
# limitation on those features does not bite: Auto Mode nodes are Bottlerocket-based Linux.
# THE GATE IS EVERY EC2 NODE, NOT THE CLUSTER FLAG. The agent is in the Auto Mode node's AMI, so it is on
# the nodes that ARE Auto Mode nodes and on no others -- the same node-health.html sentence quoted above
# says so in the other direction: "For other EKS compute types, you can add the node monitoring agent as an
# EKS add-on or you can manage it with Kubernetes tool[ing]", i.e. it does not arrive by itself. Crediting
# it from `computeConfig.enabled` handed a hybrid cluster's managed-node-group nodes a detection mechanism
# they demonstrably did not have. Auto Mode and non-Auto-Mode nodes legitimately coexist --
# docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html -- "AWS suggests running either EKS
# Auto Mode or self-managed Karpenter. You can install both during a migration or in an advanced
# configuration" -- so this is an ordinary cluster shape, not an error. SIBLING GATE of lens-2 and lens-3
# (references/reliability.md) and of ope-10, ope-15's all-auto arm and lens-7 here: same label test from
# docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html ("| eks.amazonaws.com/compute-type | auto |
# Identifies EKS Auto Mode managed nodes |"), Fargate excluded, $t>0 required so an empty cluster is never
# vacuously credited. Change one, change all six. On a hybrid cluster the question falls through to the
# two non-Auto-Mode paths below -- the honest test, since those are exactly how the non-Auto-Mode nodes
# would get this -- and a hybrid cluster that HAS one of them still scores `all` because the arms are
# ordered with both detection paths ahead of the hybrid arm, as lens-2's DaemonSet test is.
# THREE PATHS, NOT ONE, and the middle one was missing entirely. This used to detect the agent ONLY as a
# DaemonSet named node-problem-detector|npd, so a STANDARD cluster that enabled node monitoring the way AWS
# documents -- as an EKS managed add-on -- scored `none` and was told to install something it already runs.
# The string `eks-node-monitoring-agent` appeared nowhere in this whole references/ tree. Found on a live
# Standard cluster (computeConfig.enabled=false) whose add-on list carries `eks-node-monitoring-agent` and
# which has no NPD DaemonSet: a false finding, not a near miss. Sources, documentation only:
#   docs.aws.amazon.com/eks/latest/userguide/node-health.html -- "To help with maintaining healthy nodes in
#   EKS clusters, EKS offers the node monitoring agent and automatic node repair. These features are
#   automatically enabled with EKS Auto Mode compute. You can also use automatic node repair with EKS
#   managed node groups and Karpenter, and can use the EKS node monitoring agent with any EKS compute types
#   except for AWS Fargate", and "EKS Auto Mode compute includes the node monitoring agent. For other EKS
#   compute types, you can add the node monitoring agent as an EKS add-on or you can manage it with
#   Kubernetes tooling such as Helm." Three documented paths, one per arm below.
#   docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html -- "The node monitoring
#   agent Amazon EKS add-on can detect additional node health issues. These extra health signals can also be
#   leveraged by the optional node auto repair feature to automatically replace nodes as needed" ... "You do
#   not need to install this add-on on Amazon EKS Auto Mode clusters" ... "The Amazon EKS add-on name is
#   `eks-node-monitoring-agent`." That last sentence is the exact string matched below; it is matched with
#   `==` rather than a regex because an EKS add-on name is an exact API value, not a fuzzy label.
#   docs.aws.amazon.com/eks/latest/userguide/node-health-nma.html -- "The EKS node monitoring agent is
#   deployed as a DaemonSet. When you deploy it as an EKS add-on..." -- so the add-on and the hand-managed
#   DaemonSet are the same component by two delivery routes, which is why both score `all`.
# ON A HYBRID CLUSTER THE ADD-ON IS THE ARM THAT MATTERS: it covers precisely the non-Auto-Mode nodes that
# the re-gate above stops crediting from the AMI, so the two changes together make the hybrid answer correct
# rather than merely honest. The add-on arm's detail says which nodes each mechanism covers when the cluster
# is in that state.
# NEEDS THE ADD-ON LIST, hence m4 rather than m3 -- the same helper ope-2 uses, reused rather than a sixth
# copy of a wrapper. Input order matches ope-2's: `.` is f1, then `input` yields f2, f3, f4.
# KNOWN LIMIT, recorded rather than silently expanded: node-health.html's Important callout says "The node
# monitoring agent and node auto repair are only available on Linux. These features aren't available on
# Windows." Neither the add-on arm nor the DaemonSet arm subtracts Windows nodes, so a mixed Linux/Windows
# cluster with either path scores `all` while its Windows nodes are uncovered. That is pre-existing
# behaviour of the DaemonSet arm, not something the add-on arm introduces, and no fixture exercises it (no
# scenario carries either path on Windows nodes); fixing it needs a Windows-node carve-out and a fixture to
# prove it, which is a separate change.
m4 lens-1 daemonsets nodes addons cluster 'input as $n|input as $a|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(([$n.items[]?]|length)>0) as $any| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "all~auto mode bakes the EKS node monitoring agent into the node AMI of every EC2 node (eks.amazonaws.com/compute-type=auto) and enables automatic node repair by default, so node problem detection and node replacement are AWS-managed" elif ($any and $t==0) then "na~no DaemonSets possible on Fargate compute" elif ((($a.addons)//[])|any(.=="eks-node-monitoring-agent")) then "all~the EKS node monitoring agent is enabled as the eks-node-monitoring-agent EKS managed add-on, which AWS deploys as a DaemonSet"+(if ($cl.cluster.computeConfig.enabled==true) then " across the \($t - $auto) EC2 node(s) that are not Auto Mode nodes"+(if $auto>0 then ", while the remaining \($auto) node(s) carry the agent in the node AMI" else "" end) else " on the Linux nodes in this cluster" end) elif ([.items[]|select(.metadata.name|test("node-problem-detector|npd"))]|length)>0 then "all~NPD" elif ($cl.cluster.computeConfig.enabled==true) then "none~Auto Mode compute is enabled but only \($auto) of \($t) EC2 nodes carry the node monitoring agent in their AMI; the rest have no node-problem detection and no automatic node repair, and neither the eks-node-monitoring-agent add-on nor a node-problem-detector DaemonSet covers them" else "none~none" end'
g ope-19
# lens-7 ANSWERS `all` ON AUTO MODE, not `na`, on the same gate and for the same reason as ope-16 above.
# The question has two halves and Auto Mode answers both. CURRENT:
# docs.aws.amazon.com/eks/latest/userguide/automode-learn-instances.html -- "Generally, EKS releases a new
# AMI each week containing CVE and security fixes", on an image the same page says "AWS determines"; the
# pod networking capability ships in that AMI rather than as a versioned add-on the operator upgrades
# (docs.aws.amazon.com/eks/latest/userguide/auto-upgrade.html -- "EKS Auto Mode replaces these components
# with service functionality"). HEALTHY:
# docs.aws.amazon.com/eks/latest/userguide/node-health.html -- "NetworkingReady indicates whether the
# node's networking stack is functioning correctly (interfaces, routing, connectivity)", a condition set
# by the node monitoring agent, which that page says is among the features "automatically enabled with EKS
# Auto Mode compute". So the CNI's currency and its health are both reported and both AWS-managed.
# Prose detail with no ratio, for the same extractor reason as ope-16: lens-7's extractor looks for
# `vpc-cni` in the add-on list and finds nothing on an Auto Mode cluster.
# THE GATE IS EVERY EC2 NODE, NOT THE CLUSTER FLAG, for the same reason ope-16's is. Both halves of the
# credit are node-scoped: the weekly AMI is the AUTO MODE node's AMI, and `NetworkingReady` is published by
# the node monitoring agent, which node-health.html says is "automatically enabled with EKS Auto Mode
# compute" -- i.e. on Auto Mode compute, not on a managed node group in the same cluster. And on a mixed
# cluster the add-on is still the mechanism for the other nodes:
# docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html -- "However, if your cluster combines Auto mode
# with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate, these
# add-ons remain necessary." So a hybrid cluster falls through to the `vpc-cni` add-on test, which is the
# right evidence there: the DaemonSet and its add-on genuinely exist and their currency is genuinely the
# operator's. SIBLING GATE of lens-2 and lens-3 (references/reliability.md) and of ope-10, ope-16 and lens-1
# here -- same documented label, same Fargate exclusion, same $t>0 guard. Change one, change all six.
# Neither Auto-Mode-reachable arm carries a ratio, so `_res_lens7` -- which short-circuits on the cluster
# flag -- has nothing to compare and no DISAGREEMENT can fire. It does still print the Auto-Mode-only claim
# on a hybrid cluster, which is a render-report.py fix, not a scorer one.
m3 lens-7 addons nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "all~auto mode delivers pod networking as service functionality on every EC2 node (eks.amazonaws.com/compute-type=auto), on an AWS-managed AMI that EKS refreshes weekly with CVE and security fixes, and reports the node networking stack health as the NetworkingReady node condition" elif ((.addons//[])|any(.=="vpc-cni")) then "all~vpc-cni managed" elif ($cl.cluster.computeConfig.enabled==true) then "none~Auto Mode compute is enabled but only \($auto) of \($t) EC2 nodes get pod networking from the Auto Mode AMI; the rest need the vpc-cni add-on, which is not installed as an EKS managed add-on" else "none~not managed" end'
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
> **On EKS Auto Mode, two of these three are cluster capabilities rather than workloads**, and each is
> credited on its own flag — not as one blanket pass. Load balancing counts when
> `kubernetesNetworkConfig.elasticLoadBalancing.enabled` is true, because AWS: "EKS Auto Mode handles
> Network Load Balancer provisioning by default for all services of type LoadBalancer - no additional
> controller installation or configuration is required." Block storage counts when
> `storageConfig.blockStorage.enabled` is true **and** a `StorageClass` references
> `ebs.csi.eks.amazonaws.com`, because AWS: "EKS Auto Mode does not create a `StorageClass` for you" —
> the capability is on but provisions nothing without one. `external-dns` is not an Auto Mode
> capability, so it stays measured and its absence is a real gap on any cluster.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for: aws-load-balancer-controller, external-dns, ebs-csi
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# The two Auto Mode capabilities, each its own field — a cluster can have either, both or neither:
aws eks describe-cluster --name <CLUSTER> --region <REGION> \
  --query 'cluster.{lb:kubernetesNetworkConfig.elasticLoadBalancing.enabled,storage:storageConfig.blockStorage.enabled}'
kubectl get storageclass -o json    # the storage slot also needs a class on ebs.csi.eks.amazonaws.com
```

**Analysis:** Three slots, one point each, denominator always 3:
- load balancing: `aws-load-balancer-controller` deployed/installed as an add-on, **or** Auto Mode load balancing enabled
- block storage: an `ebs-csi` controller deployed/installed as an add-on, **or** Auto Mode block storage enabled **with** a `StorageClass` on `ebs.csi.eks.amazonaws.com`
- `external-dns`: deployed or installed as an add-on — no capability substitutes for it
- 3/3 → `all`, 2/3 → `some`, 1/3 → `some`, 0/3 → `none` (the `b()` bands: ≥90% `all`, ≥70% `most`, >0% `some`)

**Remediation:** On a standard cluster, deploy the missing pieces as Helm charts or EKS add-ons —
`aws eks create-addon --cluster-name <CLUSTER> --region <REGION> --addon-name aws-ebs-csi-driver` for
block storage, and the AWS Load Balancer Controller chart for ingress/NLB provisioning.

**On an Auto Mode cluster, do not install what AWS already runs** — the load balancer controller and the
EBS CSI controller are service functionality there, and adding your own is a migration problem, not a
fix. Two things are still yours:

```bash
# 1. If storageConfig.blockStorage.enabled is true but no StorageClass names the Auto Mode provisioner,
#    the capability provisions nothing. Create one (see also sec-25 for the encryption parameter):
kubectl apply -f - <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: auto-ebs-sc
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.eks.amazonaws.com
volumeBindingMode: WaitForFirstConsumer
parameters:
  type: gp3
  encrypted: "true"
EOF

# 2. external-dns is the one slot with no Auto Mode equivalent. Install it and give it a Route 53 role
#    (Pod Identity — see sec-6), or accept that DNS records are managed outside the cluster.
```

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
     permissions). A repost.aws knowledge-center article was cited here in an earlier draft and has been
     removed: this skill's source hierarchy admits the service documentation, and repost articles -- like
     blog posts -- are neither versioned with the service nor authoritative for a default. -->

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
> **On an all-Auto-Mode cluster this scores `na`, and that is not a pass.** There is no VPC CNI DaemonSet
> to instrument — AWS: "With Amazon EKS Auto Mode, you don't need to install or upgrade networking
> add-ons" — so the helper cannot be deployed. But the visibility it provides is not delivered either:
> AWS lists "Pod networking - VPC CNI IP Address Management" among its managed component log sources
> and then says "EKS Auto managed component logs (such as Compute, Block storage, Load balancing, and
> IPAM) require separate configuration through log delivery". **The operator loses something real
> here:** IP-exhaustion pressure is invisible until they configure that delivery, and Auto Mode
> "defaults to using prefix delegation (/28 prefixes)", so every node reserves a block of subnet
> addresses and subnet pressure is **higher** than on a standard cluster, not lower. Until the IPAM logs
> are on, `net-1` (free IPs left in the cluster subnets) is the only headroom signal in this report.
> **`na` requires that EVERY EC2 node is an Auto Mode node** — every one carrying
> `eks.amazonaws.com/compute-type: auto`, with Fargate nodes excluded and at least one EC2 node present.
> On a **hybrid** cluster the `na` would be a false statement about the cluster in front of you: the
> non-Auto-Mode nodes still run the `aws-node` VPC CNI DaemonSet, AWS says so ("if your cluster combines
> Auto mode with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS
> Fargate, these add-ons remain necessary"), and the helper is deployable for them. So a hybrid cluster is
> **measured**: no `cni-metrics-helper` Deployment is a real `none`, and the finding names how many nodes
> are Auto Mode nodes so the reader can see that both fixes below apply at once — the DaemonSet path for
> the non-Auto-Mode nodes, the log-delivery path for the Auto Mode ones.

**Remediation:** Which fix applies depends on the compute mode — the two are not interchangeable, **and on
a hybrid cluster you need both**: the helper covers the nodes that still run the VPC CNI DaemonSet, and
`AUTO_MODE_IPAM_LOGS` covers the Auto Mode nodes. Neither one covers the whole fleet on its own.

**Standard cluster (VPC CNI runs as a DaemonSet).** Deploy the helper and read the metrics in CloudWatch:

```bash
kubectl apply -f https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.19.2/config/master/cni-metrics-helper.yaml
# then alarm on the published CloudWatch metrics, e.g. awscni_total_ip_addresses vs awscni_assigned_ip_addresses
```

**EKS Auto Mode.** The command above cannot work: there is no `aws-node` DaemonSet to scrape. Ask AWS
for the equivalent stream instead — the `AUTO_MODE_IPAM_LOGS` log type, delivered through CloudWatch
Vended Logs in three API calls:

```bash
# 0. the destination must exist first — this one is a log group; an S3 bucket or Firehose stream works too
aws logs create-log-group --region <REGION> --log-group-name /aws/eks/<CLUSTER>/ipam
aws logs put-retention-policy --region <REGION> --log-group-name /aws/eks/<CLUSTER>/ipam --retention-in-days 30

# 1. name the cluster capability as a delivery source
aws logs put-delivery-source --region <REGION> --name <CLUSTER>-ipam --log-type AUTO_MODE_IPAM_LOGS \
  --resource-arn arn:aws:eks:<REGION>:<ACCOUNT_ID>:cluster/<CLUSTER>

# 2. name where the logs go, and keep the ARN it returns
aws logs put-delivery-destination --region <REGION> --name <CLUSTER>-ipam-dest \
  --delivery-destination-configuration destinationResourceArn=arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:/aws/eks/<CLUSTER>/ipam \
  --query 'deliveryDestination.arn' --output text

# 3. pair the two — <DEST_ARN> is the ARN printed by step 2, not a name
aws logs create-delivery --region <REGION> --delivery-source-name <CLUSTER>-ipam \
  --delivery-destination-arn <DEST_ARN>
```

The other three Auto Mode log types — `AUTO_MODE_COMPUTE_LOGS`, `AUTO_MODE_BLOCK_STORAGE_LOGS`,
`AUTO_MODE_LOAD_BALANCING_LOGS` — are configured the same way, each as its own delivery source. This is
billed as CloudWatch Vended Logs delivery plus storage at the destination, and the destination may need
a resource policy allowing delivery, so treat it as a change with a cost and a permissions step, not a
switch. Control plane logging (`ope-6`) does **not** cover any of these.

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
> types, and AWS launches, patches, upgrades and replaces its nodes for you — so a cluster whose EC2
> nodes are all Auto Mode nodes scores `all` here, not `none`, and has nothing to migrate.
> **On a hybrid cluster the answer comes from counting nodes, not from reading the cluster flag.** This
> question asks whether the worker nodes are **managed**, and both mechanisms manage: a node counts as
> managed if it carries `eks.amazonaws.com/compute-type: auto` **or** `eks.amazonaws.com/nodegroup`. So a
> cluster running Auto Mode alongside a managed node group can legitimately score `all` — every node has
> an AWS-owned lifecycle — and the finding names **both** populations with their counts rather than
> claiming "a managed node group is not the mechanism here" about nodes for which it plainly is. A
> genuinely **self-managed** node is in neither population, still lowers the ratio, and is what the
> remediation below is addressed to. A cluster with the Auto Mode flag on whose nodes carry neither label
> scores `none`: nothing is managing them, whatever the flag says.

**Commands:**
```bash
aws eks list-nodegroups --cluster-name <CLUSTER> --region <REGION>
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
# The flag above is not the answer on its own — count the nodes each mechanism owns:
kubectl get nodes -L eks.amazonaws.com/compute-type,eks.amazonaws.com/nodegroup
# "auto" in the first column or any value in the second = managed. Blank in both = self-managed.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- the denominator is EC2 nodes (Fargate excluded); a node passes if it is an Auto Mode node **or** in a
  managed node group, so an all-Auto-Mode cluster and a fully-node-grouped one both reach `all`, and a
  hybrid cluster's band is the union of the two populations over the whole EC2 node set

**Remediation:** Migrate self-managed nodes to EKS Managed Node Groups: `eksctl create nodegroup --cluster <name> --managed`. This automates patching and updates.

**On a hybrid cluster, scope this to the nodes the finding names as self-managed** — the Auto Mode nodes
and the existing node-group nodes are already covered and are not what the command above is for. Whether
you migrate the remainder into a node group or into Auto Mode is a choice; AWS notes that running Auto Mode
next to self-managed Karpenter is a migration or advanced configuration rather than a steady state, so
converging on one mechanism is worth planning even when this question already reads `all`.

---

### ope-16: Are core EKS add-ons (VPC CNI, CoreDNS, kube-proxy) managed as EKS managed add-ons?

**Detection:** 🔬 AUTO-DETECTABLE

> EKS managed add-ons receive AWS-managed updates and configuration.
> **An all-Auto-Mode cluster satisfies this question with no add-ons at all**, the same way `ope-15`
> satisfies the managed-node-group question with no node group. AWS: "Additionally, you no longer need to
> update components like: Amazon VPC CNI / AWS Load Balancer Controller / CoreDNS / `kube-proxy` /
> Karpenter / AWS EBS CSI driver … EKS Auto Mode replaces these components with service functionality."
> The question asks whether these components are EKS-managed; AWS running them below the add-on layer is
> a stronger form of that outcome, so a cluster whose EC2 nodes all carry
> `eks.amazonaws.com/compute-type: auto` scores `all` here and has nothing to migrate. Any add-on the
> operator installs **on top of** Auto Mode is still theirs to update — AWS lists "Amazon EKS Add-ons"
> under what you remain responsible for.
> **On a hybrid cluster the add-ons are not replaced and this question is measured normally.** AWS is
> explicit: "However, if your cluster combines Auto mode with other compute options like self-managed EC2
> instances, Managed Node Groups, or AWS Fargate, these add-ons remain necessary." So `vpc-cni`, `coredns`
> and `kube-proxy` are still load-bearing for the non-Auto-Mode nodes, and whether each is an EKS managed
> add-on is a real question with a real answer — counted out of three exactly as on a standard cluster,
> with the finding noting how many nodes are Auto Mode nodes. Reading `all` off the cluster flag here
> would print "there is no add-on version left for the operator to manage" about add-ons sitting in the
> cluster's own add-on list.

**Commands:**
```bash
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# Check for: vpc-cni, coredns, kube-proxy
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
# true is NOT the whole answer — the add-ons are replaced only on nodes that are Auto Mode nodes:
kubectl get nodes -L eks.amazonaws.com/compute-type
# every EC2 node "auto" -> an empty add-on list is the expected shape, not a gap
# a mix -> the three add-ons remain necessary, and the count out of three is the answer
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all`, from the node population
  rather than the add-on count (Fargate nodes excluded from that test, and a cluster with no EC2 node never
  satisfies it); any non-Auto-Mode EC2 node → count the three add-ons as on a standard cluster

**Remediation:** Migrate VPC CNI, CoreDNS, and kube-proxy to EKS managed add-ons: `aws eks create-addon --cluster-name <name> --addon-name vpc-cni`.

**On an all-Auto-Mode cluster there is nothing to do here, and installing these add-ons is a regression** —
they would run alongside the service functionality that already provides them. If you are migrating a
standard cluster to Auto Mode, the add-ons come out as part of that move, not into it.

**On a hybrid cluster the command above does apply**, and it is the mid-migration state that makes it
apply: the add-ons "remain necessary" for the nodes Auto Mode is not running, so make them EKS managed
add-ons rather than self-managed manifests, and take them out only when the last non-Auto-Mode node goes.

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
> **AWS's own component for this is the EKS node monitoring agent, and it arrives by three documented
> routes — any of them scores `all` here.** From `node-health.html`: the node monitoring agent and automatic
> node repair "are automatically enabled with EKS Auto Mode compute", and "For other EKS compute types, you
> can add the node monitoring agent as an EKS add-on or you can manage it with Kubernetes tooling such as
> Helm." So the three paths are (1) every EC2 node is an Auto Mode node, (2) the
> **`eks-node-monitoring-agent`** EKS managed add-on is enabled — "The Amazon EKS add-on name is
> `eks-node-monitoring-agent`" — or (3) a self-managed DaemonSet, which is where `node-problem-detector`
> fits. Route 2 is the one to reach for on a standard cluster: it is AWS's supported path, it needs no extra
> IAM permissions, and its signals are what `automatic node repair` consumes to replace a bad node
> (`NodeCondition`s `KernelReady`, `NetworkingReady`, `StorageReady`, `ContainerRuntimeReady`,
> `AcceleratedHardwareReady`). A cluster running route 2 with no NPD DaemonSet is **not** a finding.
> **An all-Auto-Mode cluster already has this below the pod layer**, so it scores `all` with no DaemonSet:
> AWS ships "the node monitoring agent and automatic node repair … automatically enabled with EKS Auto Mode
> compute", and asking such a cluster for a `node-problem-detector` pod is asking it to duplicate something
> it already runs in the node image.
> **The agent rides in the Auto Mode node's AMI, so the credit is per node, not per cluster.** AWS says as
> much in the other direction: "EKS Auto Mode compute includes the node monitoring agent. For other EKS
> compute types, you can add the node monitoring agent as an EKS add-on or you can manage it with
> Kubernetes tool[ing]" — it does not arrive by itself. So this scores `all` only when **every** EC2 node
> carries `eks.amazonaws.com/compute-type: auto`. On a **hybrid** cluster the managed-node-group nodes have
> no detection and no automatic repair unless something was deployed for them, so the question falls back to
> measuring the DaemonSet — a hybrid cluster that **has** deployed NPD still scores `all` — and the `none`
> finding names how many nodes are covered by the AMI and how many are not.

**Commands:**
```bash
aws eks list-addons --cluster-name <CLUSTER> --region <REGION>
# Look for eks-node-monitoring-agent — AWS's supported path on any non-Fargate compute type
kubectl get daemonsets -A -o json
# Look for node-problem-detector, or a self-managed node-monitoring-agent DaemonSet
kubectl get nodes -L eks.amazonaws.com/compute-type
# every EC2 node "auto" -> the agent is in the AMI; a mix -> the others need the add-on or a DaemonSet
kubectl get nodes -o json | jq -r '.items[]|.metadata.name + " " +
  ([.status.conditions[]|select(.type|test("KernelReady|NetworkingReady|StorageReady|ContainerRuntimeReady"))
    |.type + "=" + .status]|join(" "))'
# These conditions only appear once the agent is running, so they are the end-to-end proof
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all` (same gate as `lens-2`)
- the `eks-node-monitoring-agent` EKS managed add-on → `all`, on any compute type except Fargate
- a `node-problem-detector`/`npd` DaemonSet → `all` (the "manage it with Kubernetes tooling" path)

**Remediation:** Enable the EKS node monitoring agent as a managed add-on — the path AWS documents for
every compute type except Fargate, and the one that feeds automatic node repair:

```bash
aws eks create-addon --cluster-name <CLUSTER> --addon-name eks-node-monitoring-agent --region <REGION>
# it needs no additional IAM permissions. Then let node auto repair act on what it reports:
aws eks update-nodegroup-config --cluster-name <CLUSTER> --nodegroup-name <NODEGROUP> \
  --node-repair-config enabled=true --region <REGION>
```

`node-health.html`: automatic node repair works "with EKS managed node groups and Karpenter", and "When EKS
automatic node repair is enabled with the node monitoring agent installed, EKS automatic node repair reacts
to additional node conditions: `AcceleratedHardwareReady`, `ContainerRuntimeReady`, `KernelReady`,
`NetworkingReady`, and `StorageReady`." Without the agent it reacts only to `Ready`, deleted node objects
and instances that never join.

**Only if you need something the add-on does not report** should you run Node Problem Detector instead:
`kubectl apply -f https://raw.githubusercontent.com/kubernetes/node-problem-detector/v0.8.20/deployment/node-problem-detector.yaml`.
Running both is duplication, not defence in depth.

**On a hybrid cluster the add-on is exactly the right fix** — it covers the non-Auto-Mode nodes, and the
Auto Mode nodes already carry the same agent in their AMI, so the fleet converges on one component. On an
all-Auto-Mode cluster there is nothing to deploy; AWS says so directly: "You do not need to install this
add-on on Amazon EKS Auto Mode clusters."

**On Fargate neither path applies** — the agent works on "any EKS compute types except for AWS Fargate" —
and on Windows nodes neither does: "The node monitoring agent and node auto repair are only available on
Linux."

---

### lens-7: Is the VPC CNI addon version current and healthy?

**Detection:** 🔬 AUTO-DETECTABLE

> Outdated CNI versions miss security patches and performance improvements.
> **An all-Auto-Mode cluster answers both halves of this question — current and healthy — without a
> `vpc-cni` add-on.** Current: pod networking ships in an AMI AWS owns, and "Generally, EKS releases a new
> AMI each week containing CVE and security fixes." Healthy: the node monitoring agent, "automatically
> enabled with EKS Auto Mode compute", publishes `NetworkingReady`, which "indicates whether the node's
> networking stack is functioning correctly (interfaces, routing, connectivity)". So a cluster whose EC2
> nodes all carry `eks.amazonaws.com/compute-type: auto` scores `all`, and there is no add-on version to
> read or update.
> **Both halves are node-scoped, so the credit stops at the Auto Mode nodes.** The weekly AMI is the Auto
> Mode node's AMI and the agent publishing `NetworkingReady` is enabled by Auto Mode **compute** — neither
> reaches a managed node group in the same cluster, where AWS says the add-on is still required: "if your
> cluster combines Auto mode with other compute options like self-managed EC2 instances, Managed Node
> Groups, or AWS Fargate, these add-ons remain necessary." On a **hybrid** cluster this therefore measures
> the `vpc-cni` add-on as on a standard cluster — present as a managed add-on is `all`, absent is `none` —
> because for the non-Auto-Mode nodes the add-on genuinely is the mechanism and its currency is genuinely
> the operator's.

**Commands:**
```bash
aws eks describe-addon --cluster-name <CLUSTER> --addon-name vpc-cni --region <REGION>
# On an all-Auto-Mode cluster this returns ResourceNotFoundException by design. Read the node population
# and the node conditions instead — the compute flag alone does not tell you which nodes are covered:
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
kubectl get nodes -L eks.amazonaws.com/compute-type
kubectl get nodes -o json | jq -r '.items[]|.metadata.name + " " +
  ([.status.conditions[]|select(.type=="NetworkingReady")|.status]|join(","))'
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all`, from the node population
  rather than the add-on version (same gate as `lens-2`); any non-Auto-Mode EC2 node → read the add-on

**Remediation:** Update the VPC CNI addon to the latest version: `aws eks update-addon --cluster-name <name> --addon-name vpc-cni --resolve-conflicts OVERWRITE`.

**On an all-Auto-Mode cluster this command has nothing to act on** — there is no `vpc-cni` add-on, and AWS
rolls the networking capability forward with the weekly AMI. What is worth watching there is the
`NetworkingReady` condition per node (above) and, separately, IP headroom: `ope-10` explains why IPAM
metrics are off by default on Auto Mode and `net-1` carries the subnet headroom number.

**On a hybrid cluster the command applies to the add-on serving the non-Auto-Mode nodes**, and keeping that
add-on current stays your job for as long as any of those nodes exist — the Auto Mode nodes moving to a
weekly AWS AMI does not carry the rest of the fleet with them.

---
