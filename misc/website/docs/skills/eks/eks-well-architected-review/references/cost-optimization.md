---
title: "💰 Cost Optimization"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/cost-optimization.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/cost-optimization.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/cost-optimization.md). Edit the source, not this page.
:::

# 💰 Cost Optimization

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**11 questions** — Resource quotas, limit ranges, storage efficiency, idle resources, cost visibility,
chargeback tagging, VPC endpoints.

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` in `auto`
mode.

> ### What this pillar score measures — put this NEXT TO the number, every time the number appears
>
> **This score measures cost *hygiene*, not total cost efficiency.** The three largest levers on an EKS
> bill are **deliberately not scored here**, because each depends on intent the cluster cannot report:
>
> | Lever | Why not scored | Where it lives |
> |---|---|---|
> | **Spot vs On-Demand** | Spot under a stateful or latency-critical tier is *wrong*, not un-optimised. Keeping On-Demand can be the correct answer. | [cost-analysis.md](cost-analysis) Opportunity 2 |
> | **Graviton vs x86** | Blocked by container image architecture, which is not observable from `aws`/`kubectl`. | [cost-analysis.md](cost-analysis) Opportunity 1 |
> | **Extended Support surcharge** | Depends on today's date versus the EKS release calendar; scoring it would make the same cluster score differently on different days and break run-to-run determinism. | [cost-analysis.md](cost-analysis) Opportunity 7 |
>
> **Consequence you must disclose:** a cluster that has already taken every major lever — 100% Spot,
> 100% Graviton, on a current version — scores **exactly the same here** as one that has taken none.
> Verified: flipping a fixture to `EXTENDED` and dropping its version moves this pillar by **0**.
>
> **This is a placement requirement, not just a talking point.** "Mention cost hygiene somewhere in the
> conversation" does not satisfy this — the label and the three-lever posture line MUST sit immediately
> beside the Cost score **wherever that score is displayed**: in the chat response, in the written/Markdown
> report, and in the rendered HTML artifact that gets forwarded to the customer. A reader who sees only the
> number in the HTML — because the caveat landed in chat but not in the document, or landed once in an
> unrelated remediation bullet instead of next to the score — has been shown a "cost hygiene" score without
> being told it is one. Restate the cluster's actual Spot / Graviton / version posture (not just the word
> "hygiene") next to every rendering of the number, not once at the top of the report and not only in
> prose the reader has to go looking for. A bare number invites the reader to conclude "no cost levers
> taken", which the number does not say. Do **not** resolve this by folding the three levers into the
> scorer — that manufactures findings against clusters that are correct by design.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data and ignore the
> "Ask the user this question" block. Use the prose for rationale and remediation wording only.

---

## Cost Optimization scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh cost-optimization "$WORK"` extracts this block and runs it. Do not paste it
into a shell: it defines shell functions (`emit`, `g`, `m`…) and calls them once per question, and a Bash
permission rule matches literal command text — so no rule can match a function name and every call
prompts, or fails outright under a no-prompt policy. Appends one JSONL line per question to
`$WORK/results.jsonl`.

The `m`/`m2`/`m3`/`m4` thresholds are the determinism guarantee and are not yours to edit. In
`interactive` mode the governance answers arrive from `$WORK/governance.tsv`, which `score.sh`
substitutes into the `g` calls as it extracts them — see SKILL.md Step 6. Do not hand-edit a `g` call.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end;'
emit(){ printf '{"pillar":"cost-optimization","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

# lens-12 / lens-13 (ECR scan-on-push, immutable image tags) MOVED to the Security scorer in
# security/identity-access.md. They are supply-chain controls -- the EKS Best Practices Guides
# place both under Security, Image Security -- and scoring them here meant an unscanned image
# registry pulled down a customer's COST score, where a reader looking to cut spend would find
# two findings that save nothing. Moving rather than annotating, because the annotation would
# have documented the misattribution instead of removing it.
m2 cost-1 resourcequotas namespaces 'input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns quota"'
m2 cost-2 limitranges namespaces 'input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns limitrange"'
# cost-3 asks about OFF-PEAK scale-down -- nights and weekends. Load-based autoscaling does not do that:
# an HPA at minReplicas still runs those replicas all night. It used to score `all` for "KEDA present +
# any HPA active", neither of which establishes a schedule. A scheduled scale-down shows up as a CronJob;
# KEDA's cron scaler lives in a ScaledObject, which is not collected, so KEDA alone is `some` with the
# reason stated.
m3 cost-3 deployments hpa cronjobs 'input as $h|input as $cj|(([.items[]|select(.metadata.name|test("keda";"i"))]|length)>0) as $keda|([$h.items[]?]|length>0) as $hpa|([$cj.items[]?|select((.metadata.name|test("scale|shutdown|nightly|offpeak|off-peak";"i")))]|length) as $sched| if $sched>0 then "all~\($sched) scheduled scale-down CronJob(s)" + (if $keda then " + KEDA" else "" end) elif $keda then "some~KEDA installed, but no schedule-driven scale-down found (KEDA cron scalers are configured in ScaledObjects, which this review does not collect)" elif $hpa then "some~HPA only: scales on load, not on a clock, so idle nights and weekends still run at minimum replicas" else "none~no autoscaling" end'
g cost-4
g cost-5
m cost-6 pv '[.items[]] as $p|($p|length) as $t|([$p[]|select(.status.phase!="Released" and .status.phase!="Available")]|length) as $ok| if $t==0 then "na~no PV" else b($ok;$t)+"~\($ok)/\($t) in-use" end'
m cost-7 cluster '(.cluster.tags//{}) as $t|(["project","environment|^env$","cost|billing","team|owner"]|map(select(. as $k|$t|to_entries|any(.key|test($k;"i"))))|length) as $ok| b($ok;4)+"~\($ok)/4 chargeback tag classes (project/environment/cost-centre/team)"'
# cost-8 emits PASSES/total, like every sibling detection. It used to emit FAILURES/total
# ("1/4 unattached") while its own bucket call already scored passes -- b(($t-$idle);$t) -- so the
# state and the detail were counted in opposite directions. The renderer cross-checks each
# resource list against the ratio in the detail, so that guaranteed a false DISAGREEMENT whenever
# $idle != $t-$idle, and worse, a false AGREEMENT at the exact midpoint: 2 idle of 4 read 2/4
# from both sides while measuring opposite things. The `$idle==0` special case is gone too --
# it emitted prose with no ratio, which skipped the cross-check on the majority of real clusters,
# i.e. precisely the ones where a scoping bug would be invisible.
# Volume scoping is shared with sec-21 and with _vol_is_ours() in assets/render-report.py; EDIT ALL
# THREE OR NONE. `describe-volumes` is account- and region-wide with no filter, so this predicate is the
# only thing keeping another cluster's disks out of the score. A bare `.Value==$cn` used to be accepted:
# an unrelated volume tagged `Name=<cluster>` then counted as a cluster volume, turning `all` (1/1) into
# `some` (1/2) on a High-severity question. Both clauses now bind the cluster NAME to a cluster-ish key.
m2 cost-8 volumes cluster 'input as $cl|($cl.cluster.name//"") as $cn|[.Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0)] as $v|($v|length) as $t|([$v[]|select(.State=="available")]|length) as $idle| if $t==0 then "na~no cluster-tagged volumes" else b(($t-$idle);$t)+"~\($t-$idle)/\($t) attached (cluster vols)" end'
# cost-9 tests BOTH halves of its title. It asked about "gp3, Delete reclaim policy" while reading only
# `.parameters.type`, so a gp3 StorageClass with `reclaimPolicy: Retain` -- which leaves EBS volumes
# behind on every PVC delete, the exact leak cost-8 reports -- scored identically to a correct one.
# reclaimPolicy defaults to Delete when unset, which is why the default is spelled out here.
m cost-9 storageclasses '[.items[]?|select(((.provisioner//"")|test("ebs|aws-ebs")) or ((.parameters.type//"")|test("^(gp2|gp3|io1|io2|st1|sc1)$")))] as $sc|($sc|length) as $t|([$sc[]|select(((.parameters.type//"")=="gp3") and ((.reclaimPolicy//"Delete")=="Delete"))]|length) as $ok| if $t==0 then "na~no EBS StorageClasses" else b($ok;$t)+"~\($ok)/\($t) gp3 with Delete reclaim" end'
m lens-4 deployments 'if ([.items[]|select(.metadata.name|test("kubecost|opencost|cost-analyzer"))]|length)>0 then "all~cost tooling" else "none~none" end'
# lens-16 uses endswith(), not a regex. `test("ecr.api$")` treated `.` as "any character", so it
# matched by luck; escaping the dots instead meant counting backslashes through the markdown and
# shell layers, which is how `ecr.api` and `ecr.dkr` silently stopped matching. A literal suffix
# comparison has no escaping to get wrong.
m lens-16 vpcendpoints '[.VpcEndpoints[]?.ServiceName] as $sn|([ "s3","ecr.api","ecr.dkr","sts"]|map(select(. as $x|$sn|any(endswith("."+$x))))|length) as $ok| b($ok;4)+"~\($ok)/4 endpoints"'
```

**Governance (interview in `interactive` mode):** cost-4 (cross-AZ/region data-transfer monitoring),
cost-5 (storage requested-vs-used efficiency — needs in-pod usage).

---

## Cost Effective Resources

### cost-1: Are ResourceQuotas configured for namespaces to prevent resource over-consumption?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource quotas enforce cost governance by limiting what each team can consume.

**Commands:**
```bash
kubectl get resourcequotas -A -o json
kubectl get namespaces -o json
# Count quotas vs namespaces
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Apply ResourceQuotas per namespace: `kubectl create quota <name> -n <ns> --hard=cpu=4,memory=8Gi,pods=20`. This prevents any team from over-consuming.

---

### cost-2: Are LimitRanges configured for namespaces to set default resource constraints?

**Detection:** 🔬 AUTO-DETECTABLE

> LimitRanges ensure containers without explicit requests/limits get sensible defaults.

**Commands:**
```bash
kubectl get limitranges -A -o json
kubectl get namespaces -o json
# Count limit ranges vs namespaces
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Apply LimitRanges per namespace: `kubectl apply -f` a LimitRange with default CPU/memory requests and limits for containers without explicit values.

---

### cost-3: Do you proactively optimize Pod hours by scaling down or terminating unnecessary Pods during off-peak hours, nights, and weekends?

**Detection:** 🔬 AUTO-DETECTABLE

> Evaluate cost optimization through workload scheduling and scaling.

**Remediation:** Implement pod scaling schedules using KEDA or CronJobs to scale down non-critical workloads during off-peak hours, nights, and weekends.

---

### cost-4: Are you proactively monitoring and measuring data transfer costs between Availability Zones, regions, and to the internet?

**Detection:** ✋ ASK USER

> Assess monitoring and optimization of network data transfer costs.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Monitor cross-AZ data transfer using VPC Flow Logs and Cost Explorer. Use topology-aware routing to keep traffic within the same AZ where possible.

---

### cost-5: Is storage provisioning efficient (requested capacity vs provisioned capacity)?

**Detection:** ✋ ASK USER

> Over-provisioned storage wastes money on unused EBS capacity.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Right-size storage PVC requests to match actual usage. Use `kubectl exec` to check filesystem usage inside pods and adjust PVC sizes accordingly.

---

## Expenditure and Usage Awareness

### cost-6: Are PersistentVolumes actively used (no Released or Available volumes)?

**Detection:** 🔬 AUTO-DETECTABLE

> Unused PVs continue to incur EBS costs even when no workload is using them.

**Commands:**
```bash
kubectl get pv -o json
# Check status.phase for Released or Available
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Snapshot anything you are not certain about first — `cost-8` and
[cost-analysis.md](cost-analysis) both require this before a volume delete, and a PV delete usually
implies one. Then remove the PV and its backing volume:

```bash
kubectl get pv <name> -o jsonpath='{.spec.claimRef}{"\n"}{.spec.csi.volumeHandle}{"\n"}'
aws ec2 create-snapshot --volume-id <vol-id> --description "pre-delete <name>" --region <REGION>
kubectl delete pv <name>
aws ec2 delete-volume --volume-id <vol-id> --region <REGION>   # only after the snapshot completes
```

> **If `kubectl delete pv` hangs in `Terminating`**, the PV carries the
> `kubernetes.io/pv-protection` finalizer and Kubernetes is waiting for the controller to clear it.
> That normally means the PV is still bound, or the CSI driver is unavailable. Fix the cause — delete
> the PVC that still references it, or restore the driver — rather than reaching for
> `kubectl patch pv <name> -p '{"metadata":{"finalizers":null}}'`. Stripping the finalizer removes the
> Kubernetes object while leaving the EBS volume behind, which converts a tidy-up into exactly the
> orphaned-and-billing volume `cost-8` reports.

---

### cost-7: Are cost allocation tags applied to the EKS cluster for chargeback?

**Detection:** 🔬 AUTO-DETECTABLE

> Cost tags enable attribution of EKS spend to teams, projects, or environments.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.tags"
# Look for cost/project/environment tags
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Apply cost allocation tags to the EKS cluster: `aws eks tag-resource --resource-arn <arn> --tags Team=<team>,Project=<project>,CostCenter=<cc>`.

---

### cost-8: Are the cluster's EBS volumes all attached (none idle and still billing)?

**Detection:** 🔬 AUTO-DETECTABLE — the scorer reads `volumes.json` (EC2), **not** `pv.json`.

> **Phrasing note.** This question used to read "Are there unattached EBS volumes belonging to this
> cluster?", where a *yes* was bad while the state `all` means good — inverted against every sibling
> question. The detection now reports how many of the cluster's volumes are attached, counting what
> passed like every sibling question does, so the title matches what a passing result means.

> An EBS volume in `State: available` is attached to nothing and still bills at full rate. These
> usually outlive a deleted PVC whose StorageClass had `reclaimPolicy: Retain`, or a node that was
> replaced without cleanup.
>
> **Scope matters.** `describe-volumes` is collected region-wide with no filter, so the scorer
> narrows to volumes tagged for THIS cluster (`kubernetes.io/cluster/<name>`, or any tag whose
> value is the cluster name). In the reference capture only 4 of 11 volumes in the region belong to
> the cluster — an unscoped read bills this cluster for another cluster's idle disks, and names
> them by VolumeId in the report.

**Remediation:** List the cluster's unattached volumes, confirm each is genuinely orphaned (check
`Tags` for a `kubernetes.io/created-for/pvc/name`), snapshot anything you are unsure about, then
delete:

```bash
aws ec2 describe-volumes --region <REGION> \
  --filters Name=status,Values=available Name=tag-value,Values=<CLUSTER> \
  --query "Volumes[].{Id:VolumeId,Size:Size,Created:CreateTime,Tags:Tags}"
```

Related but distinct: `Released`/`Available` **PersistentVolumes** are a Kubernetes-object concern
covered by `cost-6`. A Released PV normally leaves its EBS volume `available`, so the two findings
often appear together — report them as one root cause, not two.

---

## FinOps

### cost-9: Are StorageClasses configured with cost-optimized volume types (gp3, Delete reclaim policy)?

**Detection:** 🔬 AUTO-DETECTABLE

> gp3 storage is about 20% cheaper than gp2 per GiB, and below ~1,000 GiB it is also faster at baseline.
> **Above that size it is a performance downgrade unless you provision IOPS.** gp2's baseline scales at
> 3 IOPS/GiB, so it passes gp3's flat 3,000 IOPS at 1,000 GiB and keeps climbing to 16,000 — a 4 TiB gp2
> volume gets 12,000 baseline IOPS that a default gp3 volume would cut to 3,000.

**Remediation:** Set `parameters.type: gp3` on the gp2 StorageClasses, and set `reclaimPolicy: Delete`
unless the volumes are meant to outlive their claims.

**Two things to know before you book the saving:**

1. **A StorageClass governs only volumes created after you change it.** Existing gp2 volumes keep their
   type, so this change saves nothing on current storage until each volume is migrated (snapshot and
   restore onto a gp3 volume, or create a new PVC on the gp3 class and copy). Nothing in this review
   counts those existing volumes, so treat the saving as applying to future growth.
2. **For any volume at or above ~1,000 GiB, provision `iops: min(size × 3, 16000)`** (and matching
   `throughput`) on the gp3 class, or you trade a 20% storage saving for a baseline IOPS cut. Cap it:
   gp2's baseline stops climbing at 16,000 IOPS, reached at 5,334 GiB, and every larger gp2 volume gets
   the same 16,000 ([EBS User Guide](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html),
   verified 2026-09-11) — provisioning `size × 3` uncapped past that point asks gp3 for more IOPS than
   gp2 ever delivered, and you pay for IOPS gp2 never had. Provisioned IOPS above the free 3,000 carry
   their own charge, which erodes part of that 20% — so on large volumes this is a deliberate trade, not
   a free win.

See the gp2/gp3 crossover detail in [cost-analysis.md](cost-analysis).

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-4: Is cost visibility tooling (Kubecost/OpenCost) deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> Cost visibility enables chargeback and optimization decisions.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for kubecost or opencost
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Kubecost or OpenCost for cost visibility: `helm install kubecost kubecost/cost-analyzer` or deploy OpenCost via Helm.

---



### lens-16: Are VPC endpoints configured for S3, ECR, and STS?

**Detection:** 🔬 AUTO-DETECTABLE

> VPC endpoints reduce NAT Gateway costs and improve security for AWS API calls.

**Commands:**
```bash
aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<VPC_ID> --region <REGION>
# Look for s3, ecr.api, ecr.dkr, sts service names
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Create VPC endpoints for S3, ECR (.api and .dkr), and STS to reduce NAT Gateway costs and improve security for AWS API calls.

---
