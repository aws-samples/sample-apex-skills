---
title: "⚡ Performance Efficiency"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/performance-efficiency.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/performance-efficiency.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/performance-efficiency.md). Edit the source, not this page.
:::

# ⚡ Performance Efficiency

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**12 questions** — Resource requests, instance types, VPA, scheduling, DNS optimization, traffic routing

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` in `auto`
mode. The per-question sections below give rationale and remediation.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data and ignore the
> "Ask the user this question" block. Use the prose for rationale and remediation wording only.

---

## Performance Efficiency scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh performance-efficiency "$WORK"` extracts this block and runs it. Do not paste it
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
emit(){ printf '{"pillar":"performance-efficiency","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

m perf-1 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory)]|length) as $ok| if $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) requests (workloads)" end'
m perf-2 deployments 'if ([.items[]|select(.metadata.name|test("vertical-pod-autoscaler|vpa-recommender|vpa"))]|length)>0 then "all~VPA" else "none~none" end'
# perf-3 — previous-generation instance share, pinned to AWS's ACTUAL published list.
# AWS, ec2/latest/instancetypes/instance-types.html "Previous generation instances":
#   General purpose  A1 | M1 | M2 | M3 | M4 | T1
#   Compute          C1 | C3 | C4
#   Memory           R3 | R4
#   Storage          I2
#   Accelerated      G3 | P3 | P3dn
# The previous pattern also flagged m5, c5, r5, t2, i3, d2, h1, x1, p2 and g2 — TEN families AWS lists
# as CURRENT generation. Because the report prints the words "current-generation" to a customer, that
# was a factual error in customer-facing output, not an internal threshold choice: an all-m5 fleet was
# told 0/N of its nodes were current generation.
# `[a-z]*` before the dot keeps suffixed members of a genuinely previous-gen family (p3dn, m3 variants)
# while `m[1-4]`/`c1|c3|c4`/`t1` deliberately exclude m5, c5 and t2.
m perf-3 nodes '[.items[]|.metadata.labels["node.kubernetes.io/instance-type"]//empty] as $it|($it|length) as $t|([$it[]|select(test("^(a1|m[1-4]|t1|c1|c3|c4|r3|r4|i2|g3|p3)[a-z]*\\."))]|length) as $old|($t-$old) as $ok| if ([.items[]]|length)==0 then "na~no nodes" elif $t==0 then "na~no instance types (serverless compute)" else b($ok;$t)+"~\($ok)/\($t) current-generation" end'
m perf-4 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) rolling"'
# perf-5 distinguishes SPREADING from PINNING. Any `affinity` used to satisfy it, so a plain nodeAffinity
# pinning every replica to one AZ or instance type scored `all` on a question about placement for
# performance AND availability -- the opposite of its intent. Only topologySpreadConstraints and
# podAntiAffinity spread; nodeAffinity alone is reported as pinning.
m perf-5 deployments '[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $d|($d|length) as $t|([$d[]|select(((.spec.template.spec.topologySpreadConstraints//[])|length)>0 or ((.spec.template.spec.affinity.podAntiAffinity//null)!=null))]|length) as $spread|([$d[]|select(((.spec.template.spec.topologySpreadConstraints//[])|length)==0 and ((.spec.template.spec.affinity.podAntiAffinity//null)==null) and ((.spec.template.spec.affinity.nodeAffinity//null)!=null))]|length) as $pinned| if $t==0 then "na~no workload Deployments" elif $pinned>0 and $spread==0 then "none~0/\($t) spread; \($pinned) deploy(s) use nodeAffinity only, which PINS placement rather than spreading it" else b($spread;$t)+"~\($spread)/\($t) deploys spread across failure domains" + (if $pinned>0 then " (\($pinned) pinned by nodeAffinity only)" else "" end) end'
m perf-6 nodes '([.items[]|.metadata.labels["node.kubernetes.io/instance-type"]//empty]|unique|length) as $d| if ([.items[]]|length)==0 then "na~no nodes" elif $d==0 then "na~no instance types (serverless compute)" elif $d>=3 then "all~\($d) types" elif $d==2 then "most~2 types" else "some~1 type" end'
g perf-7
m lens-5 pods '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $p|($p|length) as $t|([$p[]|select(.metadata.labels["app.kubernetes.io/name"])]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) std labels"'
# lens-6 — the pass set must EXCLUDE Amazon Linux 2. `test("Bottlerocket|Amazon Linux")` matched the
# string "Amazon Linux 2" and scored it `all`, so the skill awarded full marks for an AMI family that
# reached end of support on 2025-11-26 (last Kubernetes version 1.32) and receives no security
# patches. Matching `Amazon Linux 20[0-9][0-9]` accepts AL2023 and any future year-numbered Amazon
# Linux while rejecting bare "Amazon Linux 2" — and avoids hard-coding a version list that goes stale.
# AL2 is called out separately in the detail because it is a security finding, not just a non-pass:
# an unsupported node OS is materially different from Ubuntu or a custom AMI.
# lens-6 asks about the LINUX AMI families EKS supports (Bottlerocket, AL2023). Windows nodes are a
# separately-supported family this review does not assess, so they are excluded rather than counted as
# running an unsupported image -- a healthy Windows node used to fail this check and pull the pillar down.
m lens-6 nodes '[.items[]] as $all|([$all[]|select((.metadata.labels["kubernetes.io/os"]//"")=="windows")]|length) as $win|[$all[]|select(((.metadata.labels["kubernetes.io/os"]//"")=="windows")|not)] as $n|($n|length) as $t|([$n[]|.status.nodeInfo.osImage//""]) as $os|([$os[]|select(test("Bottlerocket|Amazon Linux 20[0-9][0-9]"))]|length) as $ok|([$os[]|select(test("Amazon Linux") and (test("Amazon Linux 20[0-9][0-9]")|not))]|length) as $al2| if $t==0 then (if $win>0 then "na~\($win) Windows node(s) only; Windows node pools are not assessed" else "na~no nodes" end) else b($ok;$t)+"~\($ok)/\($t) supported EKS AMI"+(if $al2>0 then ", \($al2) on Amazon Linux 2 (end of support 2025-11-26 — no security patches)" else "" end)+(if $win>0 then " (\($win) Windows node(s) excluded — not assessed)" else "" end) end'
m lens-8 pods '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $p|($p|length) as $t|([$p[]|select([.spec.dnsConfig.options[]?|select(.name=="ndots" and ((.value|tonumber?)//9)<=2)]|length>0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ndots<=2"'
# lens-9 credits `target-type: ip` as well as `externalTrafficPolicy: Local`. Both avoid the extra
# kube-proxy hop this question is about -- IP mode sends traffic straight to the pod -- so marking an
# IP-mode NLB down for not setting a flag irrelevant to its traffic path was a false finding.
m lens-9 services '[.items[]?|select(.spec.type=="LoadBalancer")] as $lb|($lb|length) as $t|([$lb[]|select(((.metadata.annotations//{})["service.beta.kubernetes.io/aws-load-balancer-nlb-target-type"]//(.metadata.annotations//{})["alb.ingress.kubernetes.io/target-type"]//"")=="ip")]|length) as $iptarget|([$lb[]|select(.spec.externalTrafficPolicy=="Local" or (((.metadata.annotations//{})["service.beta.kubernetes.io/aws-load-balancer-nlb-target-type"]//(.metadata.annotations//{})["alb.ingress.kubernetes.io/target-type"]//"")=="ip"))]|length) as $ok| if $t==0 then "na~no LoadBalancer services" else b($ok;$t)+"~\($ok)/\($t) avoid the extra hop" + (if $iptarget>0 then " (\($iptarget) via target-type: ip, where externalTrafficPolicy is moot)" else "" end) end'
m lens-10 services '[.items[]] as $s|($s|length) as $t|([$s[]|select((.metadata.annotations["service.kubernetes.io/topology-mode"]) or (.metadata.annotations["service.kubernetes.io/topology-aware-hints"]))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) topo routing"'
```

**Governance (interview in `interactive` mode):** perf-7 (node utilization — needs live metrics not in the
snapshot).

---

## Monitoring

### perf-1: Do containers have CPU and memory requests set for accurate scheduling?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource requests enable the scheduler to place pods on nodes with sufficient capacity.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].resources.requests for cpu and memory
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set CPU and memory requests on all containers based on actual usage. Use VPA recommendations: `kubectl get vpa -A -o jsonpath="{.items[*].status.recommendation}"` as a guide.

---

### perf-2: Is Vertical Pod Autoscaler (VPA) deployed for right-sizing resource requests?

**Detection:** 🔬 AUTO-DETECTABLE

> VPA recommends or automatically adjusts resource requests based on actual usage.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for vertical-pod-autoscaler deployment
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy VPA in recommendation mode to right-size resource requests without auto-applying changes.

---

### perf-3: Are appropriate EC2 instance types selected for the workload requirements?

**Detection:** 🔬 AUTO-DETECTABLE

> Instance type selection impacts performance, cost, and workload compatibility.

**Commands:**
```bash
kubectl get nodes -o json
# Check node.kubernetes.io/instance-type labels for type diversity
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Review instance types for workload fit. Use Graviton (m7g, c7g) for better price-performance. Match instance family to workload profile (compute, memory, general).

---

### perf-4: Do deployments use RollingUpdate strategy for zero-downtime updates?

**Detection:** 🔬 AUTO-DETECTABLE

> Rolling updates maintain performance during deployments by keeping pods available.

**Remediation:** Set `strategy.type: RollingUpdate` on all Deployments with appropriate `maxUnavailable` and `maxSurge` values for zero-downtime updates.

---

### perf-5: Are pod affinity, anti-affinity, or topology spread constraints configured?

**Detection:** 🔬 AUTO-DETECTABLE

> Scheduling constraints optimize pod placement for performance and availability.

**Remediation:** Configure pod affinity/anti-affinity and topology spread constraints to optimize pod placement across nodes and zones.

---

## Resource Optimization

### perf-6: Is there diversity in EC2 instance types across node groups?

**Detection:** 🔬 AUTO-DETECTABLE

> Instance type diversity reduces Spot interruption risk and improves bin-packing.

**Remediation:** Use multiple instance types across node groups to improve bin-packing and reduce Spot interruption risk. Mix instance families (m5, m6i, m7g).

---

## Network Performance

### perf-7: Are node CPU and memory resources being utilized efficiently (requests vs capacity)?

**Detection:** ✋ ASK USER

> Low utilization indicates over-provisioning; high utilization risks resource contention.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Right-size nodes based on actual utilization. Target 60-80% CPU and memory utilization. Use Karpenter for automatic instance type selection.

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-5: Do pods use Kubernetes standard labels (app.kubernetes.io/name)?

**Detection:** 🔬 AUTO-DETECTABLE

> Standard labels enable consistent service discovery and monitoring.

**Commands:**
```bash
kubectl get pods -A -o json
# Check for app.kubernetes.io/name label
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add Kubernetes standard labels to all pods: `app.kubernetes.io/name`, `app.kubernetes.io/version`, `app.kubernetes.io/component`.

---

### lens-6: Do nodes use a SUPPORTED EKS-optimized AMI (Amazon Linux 2023 or Bottlerocket)?

**Detection:** 🔬 AUTO-DETECTABLE

> EKS-optimized AMIs are tuned for Kubernetes performance and security — but only while AWS still
> publishes them. An AMI family past end of support is a security finding, not a performance one.

**Commands:**
```bash
kubectl get nodes -o json
# status.nodeInfo.osImage — "Bottlerocket OS ..." / "Amazon Linux 2023..." pass; "Amazon Linux 2" does NOT
```

**Amazon Linux 2 is NOT a pass.** AWS *"ended support for Amazon EKS optimized Amazon Linux 2 AMIs on
November 26, 2025"*; Kubernetes **1.32 was the last version** for which EKS released them, and they
*"no longer receive software updates, security patches, or bug fixes from AWS"*. They are also
unavailable on 1.33+. This question previously matched the substring `Amazon Linux`, which "Amazon
Linux 2" satisfies, so a fleet of unpatched AL2 nodes scored `all` — the skill both recommended and
rewarded an end-of-life OS. Read that as: if you see AL2, it is the finding, and it outranks anything
else in this pillar.

**Analysis:** percentage of nodes on a supported family:
- ≥90% → `all` · ≥70% → `most` · >0% → `some` · 0% → `none` · no nodes → `na`
- Pass set: `Bottlerocket OS *`, `Amazon Linux 20xx` (AL2023 and later). The year match deliberately
  avoids a hard-coded version list that goes stale the next time AWS ships a release.
- The detail names the AL2 node count separately, because an unsupported node OS is materially
  different from Ubuntu or a deliberate custom AMI.

**Remediation:** move worker nodes to **Bottlerocket** (minimal, image-based, and the lowest-effort
option under Karpenter/Auto Mode) or **Amazon Linux 2023**. Both are current EKS-optimized families.
- Managed node groups: set `amiType` to `BOTTLEROCKET_x86_64` / `BOTTLEROCKET_ARM_64` or
  `AL2023_x86_64_STANDARD` / `AL2023_ARM_64_STANDARD`, then roll the group.
- Karpenter: set `amiFamily: Bottlerocket` or `AL2023` on the EC2NodeClass (`amiFamily: AL2` is the
  deprecated path).
- AL2 → AL2023 is **not** a drop-in swap: AL2023 bootstraps with `nodeadm` and a YAML config schema
    instead of `/etc/eks/bootstrap.sh`, requires VPC CNI ≥ 1.16.2, and enforces IMDSv2. Both AL2023 and
    Bottlerocket EKS-optimized AMIs carry the `imds-support: v2.0` AMI attribute (`aws ec2
    describe-images`, verified live 2026-09-11), which on its own launches instances at `HttpTokens:
    required` and `HttpPutResponseHopLimit: 2` — one hop further than the plain EC2 default of 1, and
    enough for a pod off the host network to still reach IMDS. **Karpenter is not the permissive path
    here.** Its `EC2NodeClass` explicitly defaults `httpPutResponseHopLimit` back down to **1**, to block
    IMDS access from containers not on the host network (karpenter.sh NodeClasses reference, verified
    live 2026-09-11) — so an AL2 → AL2023 move under Karpenter does not loosen the hop limit unless the
    operator's `EC2NodeClass` overrides that default. **A managed node group is the case that actually
    needs checking.** AWS documents AL2023 managed node groups as defaulting to hop 1 with no launch
    template and hop 2 once a launch template names a custom AMI (EKS User Guide, "Upgrade from Amazon
    Linux 2 to Amazon Linux 2023," verified live 2026-09-11) — but that split does not hold uniformly
    across AMI families: verified live against this project's own cluster (`my-eks-cluster`,
    `ap-southeast-5`), its Bottlerocket-based managed node group has **no** user-specified launch
    template, yet the launch template EKS generated for it carries `HttpPutResponseHopLimit: 2`, and
    every resulting instance reports `HttpTokens: required`, hop 2. Don't infer the hop limit from AMI
    family or provisioning mechanism — read `MetadataOptions.HttpPutResponseHopLimit` off the actual
    instances. Say this in the report; a migration presented as trivial will fail.
- EKS Auto Mode manages the node OS itself, so this question is not an action item there.

---

### lens-8: Do pods override CoreDNS ndots to ≤2 for faster DNS resolution?

**Detection:** 🔬 AUTO-DETECTABLE

> Default ndots=5 causes unnecessary DNS lookups for external domains.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.dnsConfig.options for ndots <= 2
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Override CoreDNS ndots in pod specs: add `dnsConfig.options: [{name: ndots, value: "2"}]` to reduce unnecessary DNS search domain lookups.

---

### lens-9: Do LoadBalancer services use externalTrafficPolicy: Local?

**Detection:** 🔬 AUTO-DETECTABLE

> Local policy preserves client IPs and avoids extra network hops.

**Commands:**
```bash
kubectl get services -A -o json
# Check LoadBalancer services for externalTrafficPolicy: Local
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `externalTrafficPolicy: Local` on LoadBalancer services to preserve client IPs and avoid extra network hops across nodes.

---

### lens-10: Are services configured with topology-aware routing?

**Detection:** 🔬 AUTO-DETECTABLE

> Topology routing keeps traffic in-zone to reduce latency and cross-AZ costs.

**Commands:**
```bash
kubectl get services -A -o json
# Check annotation service.kubernetes.io/topology-mode
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable topology-aware routing: add annotation `service.kubernetes.io/topology-mode: Auto` to services for in-zone traffic routing.

---
