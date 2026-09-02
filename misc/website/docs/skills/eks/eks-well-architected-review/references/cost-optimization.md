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

**13 questions** — Resource quotas, limit ranges, storage efficiency, idle resources, cost visibility,
chargeback tagging, VPC endpoints.

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` in `auto`
mode.

> ### What this pillar score measures — state this in the report
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
> So when reporting the Cost score, label it as cost hygiene and put the cluster's actual Spot,
> Graviton and version posture next to it. A bare number invites the reader to conclude "no cost
> levers taken", which the number does not say. Do **not** resolve this by folding the three levers
> into the scorer — that manufactures findings against clusters that are correct by design.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data and ignore the
> "Ask the user this question" block. Use the prose for rationale and remediation wording only.

---

## Cost Optimization scorer — run verbatim

Requires `$WORK` (SKILL.md Step 2). Appends one JSONL line per question to `$WORK/results.jsonl`.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end;'
emit(){ printf '{"pillar":"cost-optimization","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

m2 cost-1 resourcequotas namespaces 'input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns quota"'
m2 cost-2 limitranges namespaces 'input as $ns|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns limitrange"'
m2 cost-3 deployments hpa 'input as $h|(([.items[]|select(.metadata.name|test("keda"))]|length)>0) as $keda|(([$h.items[]?]|length)>0) as $used| if ($keda and $used) then "all~KEDA + active autoscalers" elif $keda then "some~KEDA installed but no autoscalers" elif $used then "some~HPA only, no event-driven scaling" else "none~none" end'
g cost-4
g cost-5
m cost-6 pv '[.items[]] as $p|($p|length) as $t|([$p[]|select(.status.phase!="Released" and .status.phase!="Available")]|length) as $ok| if $t==0 then "na~no PV" else b($ok;$t)+"~\($ok)/\($t) in-use" end'
m cost-7 cluster '(.cluster.tags//{}) as $t|(["project","environment|^env$","cost|billing","team|owner"]|map(select(. as $k|$t|to_entries|any(.key|test($k;"i"))))|length) as $ok| b($ok;4)+"~\($ok)/4 chargeback tag classes (project/environment/cost-centre/team)"'
m2 cost-8 volumes cluster 'input as $cl|($cl.cluster.name//"") as $cn|[.Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0)] as $v|($v|length) as $t|([$v[]|select(.State=="available")]|length) as $idle| if $t==0 then "na~no cluster-tagged volumes" elif $idle==0 then "all~no unattached cluster volumes" else b(($t-$idle);$t)+"~\($idle)/\($t) unattached (cluster vols)" end'
m cost-9 storageclasses '[.items[]|select((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|kubernetes\\.io/aws-ebs"))] as $s|($s|length) as $t|([$s[]|select(.parameters.type=="gp3")]|length) as $ok| if $t==0 then "na~no EBS StorageClass" else b($ok;$t)+"~\($ok)/\($t) gp3 EBS SC" end'
m lens-4 deployments 'if ([.items[]|select(.metadata.name|test("kubecost|opencost|cost-analyzer"))]|length)>0 then "all~cost tooling" else "none~none" end'
m2 lens-12 ecr pods 'input as $p|[$p.items[].spec.containers[]?.image|select(test("dkr.ecr"))|capture("amazonaws.com/(?<r>[^:@]+)").r] as $used|[.repositories[]?|select(.repositoryName as $rn|$used|index($rn))] as $r|($r|length) as $t|([$r[]|select(.imageScanningConfiguration.scanOnPush==true)]|length) as $ok| if $t==0 then "na~no cluster ECR repos" else b($ok;$t)+"~\($ok)/\($t) scan-on-push" end'
m2 lens-13 ecr pods 'input as $p|[$p.items[].spec.containers[]?.image|select(test("dkr.ecr"))|capture("amazonaws.com/(?<r>[^:@]+)").r] as $used|[.repositories[]?|select(.repositoryName as $rn|$used|index($rn))] as $r|($r|length) as $t|([$r[]|select(.imageTagMutability=="IMMUTABLE")]|length) as $ok| if $t==0 then "na~no cluster ECR repos" else b($ok;$t)+"~\($ok)/\($t) immutable" end'
m lens-16 vpcendpoints '[.VpcEndpoints[]?.ServiceName] as $sn|([ "s3","ecr.api","ecr.dkr","sts"]|map(select(. as $x|$sn|any(test($x+"$"))))|length) as $ok| b($ok;4)+"~\($ok)/4 endpoints"'
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

**Detection:** ✋ ASK USER

> Evaluate cost optimization through workload scheduling and scaling.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

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
- "Doesn't apply" → `not-applicable`

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
- "Doesn't apply" → `not-applicable`

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

**Remediation:** Clean up unused PVs: `kubectl delete pv <name>` for Released/Available PVs. Delete the underlying EBS volumes to stop incurring charges.

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

### cost-8: Are there unattached EBS volumes belonging to this cluster?

**Detection:** 🔬 AUTO-DETECTABLE — the scorer reads `volumes.json` (EC2), **not** `pv.json`.

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

**Detection:** ✋ ASK USER

> gp3 is 20% cheaper than gp2 with better baseline performance.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Migrate gp2 StorageClasses to gp3: update the StorageClass `parameters.type` to `gp3`. gp3 is 20% cheaper with better baseline performance.

---

## EKS Best Practices

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

### lens-12: Do ECR repositories have scan-on-push enabled?

**Detection:** 🔬 AUTO-DETECTABLE

> Image scanning detects vulnerabilities before deployment.

**Commands:**
```bash
aws ecr describe-repositories --region <REGION> --query "repositories[].imageScanningConfiguration.scanOnPush"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable scan-on-push for ECR repositories: `aws ecr put-image-scanning-configuration --repository-name <name> --image-scanning-configuration scanOnPush=true`.

---

### lens-13: Do ECR repositories use immutable image tags?

**Detection:** 🔬 AUTO-DETECTABLE

> Immutable tags prevent tag overwriting and ensure deployment reproducibility.

**Commands:**
```bash
aws ecr describe-repositories --region <REGION> --query "repositories[].imageTagMutability"
# Check for IMMUTABLE
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable immutable tags for ECR repositories: `aws ecr put-image-tag-mutability --repository-name <name> --image-tag-mutability IMMUTABLE`.

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
