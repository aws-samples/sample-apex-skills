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

**25 questions** — IaC, GitOps, monitoring, logging, upgrade management, managed node groups, EKS addons

Scoring is **deterministic** — run the scorer block below; each measured question prints
`all`/`most`/`some`/`none`/`na` from `jq`. Governance questions (process-only) emit `unknown` in `auto`
mode. The per-question sections that follow give rationale and remediation for writing findings.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data and ignore the
> "Ask the user this question" block. Use the prose for rationale and remediation wording only.

---

## Operational Excellence scorer — run verbatim

Requires `$WORK` (SKILL.md Step 2). Appends one JSONL line per question to `$WORK/results.jsonl`.
In `interactive` mode, replace each `g <id>` with `emit <id> governance <all|most|some|none|na> "<note>"`.

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
m ope-5 deployments 'if ([.items[]|select(.metadata.name|test("prometheus|grafana|cloudwatch"))]|length)>0 then "all~metrics stack" else "none~none" end'
m ope-6 cluster '([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]]|unique|length) as $ok| b($ok;5)+"~\($ok)/5 log types"'
m2 ope-7 daemonsets nodes 'input as $n|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0) then "na~no DaemonSets possible on Fargate compute" elif ([.items[]|select(.metadata.name|test("node-exporter"))]|length)>0 then "all~node-exporter" else "none~none" end'
m2 ope-8 daemonsets nodes 'input as $n|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0) then "na~DaemonSet log forwarding impossible on Fargate; fargate-4 scores the sidecar log router instead" elif ([.items[]|select(.metadata.name|test("fluent"))]|length)>0 then "all~log forwarder" else "none~none" end'
g ope-9
m ope-10 deployments 'if ([.items[]|select(.metadata.name|test("cni-metrics-helper"))]|length)>0 then "all~cni metrics helper" else "none~none" end'
m2 ope-11 cloudtrail cluster 'input as $cl|((($cl.cluster.arn//"")|split(":"))[3]//"") as $rg|((.trailList//[])|length) as $t|[(.trailList//[])[]|select((.IsMultiRegionTrail==true) or ((.HomeRegion//"")==$rg))] as $cov| if $t==0 then "none~no trail" elif ($cov|length)==0 then "none~\($t) trail(s) exist but none is multi-region or homed in \($rg)" else "all~\($cov|length)/\($t) trail(s) cover \($rg) (configuration only — IsLogging requires get-trail-status, which this review does not collect)" end'
m ope-12 cluster '"na~same signal as ope-6 (which already counts audit among the 5 log types) and sec-26 (deduplicated)"'
g ope-13
g ope-14
m3 ope-15 nodegroups cluster nodes 'input as $cl|input as $n|($cl.cluster.computeConfig.enabled==true) as $am|([$n.items[]?] as $nd|(($nd|length)>0) and ([$nd[]|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")]|length)==($nd|length)) as $fg| if $am then "all~auto mode" elif $fg then "na~fargate-only, node groups not applicable" elif ((.nodegroups//[])|length)>0 then "all~\((.nodegroups|length)) MNG" else "none~no MNG" end'
m2 ope-16 addons cluster 'input as $cl| if ($cl.cluster.computeConfig.enabled==true) then "na~auto mode delivers CNI/DNS/LB/storage as core components, not add-ons" else ((.addons//[]) as $a|([ "vpc-cni","coredns","kube-proxy"]|map(select(. as $x|$a|any(.==$x)))|length) as $ok| b($ok;3)+"~\($ok)/3 core addons") end'
m ope-17 jobs '[.items[]?] as $j|($j|length) as $t|([$j[]|select((.spec.activeDeadlineSeconds!=null) and ((.spec.backoffLimit//6)<=6))]|length) as $ok| if $t==0 then "na~no Jobs" else b($ok;$t)+"~\($ok)/\($t) Jobs bounded (activeDeadlineSeconds set, backoffLimit<=6)" end'
m ope-18 cronjobs '[.items[]?] as $c|($c|length) as $t|([$c[]|select(((.spec.concurrencyPolicy//"Allow")!="Allow") and (.spec.failedJobsHistoryLimit!=null))]|length) as $ok| if $t==0 then "na~no CronJobs" else b($ok;$t)+"~\($ok)/\($t) CronJobs guarded (concurrencyPolicy!=Allow, failedJobsHistoryLimit set)" end'
m fargate-1 fargate 'if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else "na~NOT ASSESSED: profile selectors require describe-fargate-profile, which this review does not collect — do not report this as satisfied or as not-applicable" end'
m2 fargate-2 fargate pods 'input as $p|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$p.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory)]|length) as $ok| if $t==0 then "na~no Fargate pods running" else b($ok;$t)+"~\($ok)/\($t) Fargate containers with cpu+memory requests" end) end'
m fargate-3 fargate 'if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else "na~NOT ASSESSED: pod execution roles require describe-fargate-profile, which this review does not collect — do not report this as satisfied or as not-applicable" end'
m2 fargate-4 fargate pods 'input as $p|if ((.fargateProfileNames//[])|length)==0 then "na~no fargate" else ([$p.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]=="fargate")] as $po|($po|length) as $t|([$po[]|select([.spec.containers[]?.name]|any(test("fluent")))]|length) as $ok| if $t==0 then "na~no Fargate pods running" else b($ok;$t)+"~\($ok)/\($t) Fargate pods with a log-router sidecar" end) end'
m2 lens-1 daemonsets nodes 'input as $n|([$n.items[]?|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2|(([$n.items[]?]|length)>0) as $any| if ($any and $ec2==0) then "na~no DaemonSets possible on Fargate compute" elif ([.items[]|select(.metadata.name|test("node-problem-detector|npd"))]|length)>0 then "all~NPD" else "none~none" end'
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
- "Doesn't apply" → `not-applicable`

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

**Detection:** ✋ ASK USER

> GitOps reduces human error and provides audit trails for all changes.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

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
- "Doesn't apply" → `not-applicable`

**Remediation:** Adopt Helm for application packaging: `helm create <chart>`. Use values files per environment and store charts in a Helm repository.

---

## Centralized monitoring and logging

### ope-5: Are control plane metrics monitored using CloudWatch Container Insights or Prometheus?

**Detection:** ✋ ASK USER

> Control plane monitoring enables early detection of API server and etcd issues.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Deploy Prometheus + Grafana or enable CloudWatch Container Insights: `aws eks create-addon --addon-name amazon-cloudwatch-observability`.

---

### ope-6: Are EKS control plane logs (API server, audit, authenticator, controller manager, scheduler) enabled?

**Detection:** 🔬 AUTO-DETECTABLE

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

**Remediation:** Enable all 5 control plane log types in the EKS console (API server, audit, authenticator, controller manager, scheduler).

---

### ope-7: Are worker node metrics (CPU, memory, disk) monitored using Node Exporter or CloudWatch?

**Detection:** ✋ ASK USER

> Node monitoring enables capacity planning and early detection of resource exhaustion.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Deploy Prometheus Node Exporter as a DaemonSet: `helm install node-exporter prometheus-community/prometheus-node-exporter`. Create Grafana dashboards for CPU, memory, disk.

---

### ope-8: Are application logs forwarded to a centralized system (Fluent Bit, Fluentd, CloudWatch)?

**Detection:** ✋ ASK USER

> Centralized logging enables cross-service troubleshooting and audit trails.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

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
- "Doesn't apply" → `not-applicable`

**Remediation:** Create CloudWatch metric filters on EKS audit logs for 403/401 responses. Set alarms with SNS notifications for threshold breaches.

---

### ope-10: Is the CNI metrics helper deployed to monitor VPC CNI IP address allocation and ENI usage?

**Detection:** ✋ ASK USER

> CNI metrics prevent IP exhaustion which can cause pod scheduling failures.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Deploy the CNI metrics helper: `kubectl apply -f https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/master/config/master/cni-metrics-helper.yaml`. Monitor IP allocation in CloudWatch.

---

### ope-11: Are you using AWS CloudTrail to audit EKS API calls and IRSA actions?

**Detection:** ✋ ASK USER

> CloudTrail provides API-level audit logging for compliance.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Enable CloudTrail in all regions with S3 log delivery. Create CloudTrail event selectors for EKS API calls and IRSA assume-role events.

---

### ope-12: Is Kubernetes audit logging enabled to track API authorization decisions?

**Detection:** 🔬 AUTO-DETECTABLE

> Audit logs record who did what in the cluster for security and compliance.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.logging.clusterLogging[?enabled==`true`].types[]"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable audit logging via EKS console → Logging → Enable "Audit". Configure CloudWatch Insights to monitor authorization failures.

---

### ope-13: Do you have an ongoing upgrade plan aligned with the EKS Kubernetes version support lifecycle?

**Detection:** ✋ ASK USER

> Regular upgrades ensure security patches and feature access.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

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
- "Doesn't apply" → `not-applicable`

**Remediation:** Create a dedicated staging EKS cluster in a separate AWS account. Test all upgrades and add-on updates there before applying to production.

---

### ope-15: Are worker nodes managed using EKS Managed Node Groups?

**Detection:** 🔬 AUTO-DETECTABLE

> Managed Node Groups automate node patching, updates, and replacement.

**Commands:**
```bash
aws eks list-nodegroups --cluster-name <CLUSTER> --region <REGION>
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
- "Doesn't apply" → `not-applicable`

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

### fargate-4: Do Fargate pods have log router sidecars (Fluent Bit/FireLens) configured?

**Detection:** 🔬 AUTO-DETECTABLE

> Fargate pods need sidecar log routers since node-level logging is unavailable.

**Commands:**
```bash
kubectl get pods -A -o json
# For Fargate pods, check for fluent-bit sidecar container
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Fluent Bit as a sidecar container in Fargate pods for log forwarding. Use the `amazon/aws-for-fluent-bit` image with FireLens configuration.

---

## EKS Best Practices

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

**Remediation:** Deploy Node Problem Detector as a DaemonSet: `kubectl apply -f https://raw.githubusercontent.com/kubernetes/node-problem-detector/master/deployment/npd.yaml`.

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
