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

**12 questions** — Resource requests, instance types, VPA, scheduling, DNS optimization, traffic routing

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` in `auto`
mode. The per-question sections below give rationale and remediation.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data and ignore the
> "Ask the user this question" block. Use the prose for rationale and remediation wording only.

---

## Performance Efficiency scorer — run verbatim

Requires `$WORK` (SKILL.md Step 2). Appends one JSONL line per question to `$WORK/results.jsonl`.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end;'
emit(){ printf '{"pillar":"performance-efficiency","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

m perf-1 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory)]|length) as $ok| if $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) requests (workloads)" end'
m perf-2 deployments 'if ([.items[]|select(.metadata.name|test("vertical-pod-autoscaler|vpa-recommender|vpa"))]|length)>0 then "all~VPA" else "none~none" end'
# perf-3 — previous-generation instance share. The family group MUST allow suffix letters before the
# size separator: written as `...|m[1-5])\.` the pattern only matched the bare family, so every
# suffixed previous-gen type escaped and was counted as CURRENT generation — m5d, m5n, m5zn, c5a, c5d,
# c5n, r5b, r5d, r5n, i3en and p3dn, eleven real families, all inflating the score. `[a-z]*` closes it.
# Two deliberate narrowings that come with that change:
#   - `t[12]`, not `t[1-3]`: t3 is CURRENT generation. The old pattern flagged `t3` while `t3a` and
#     `t4g` escaped, so one family was scored three different ways.
#   - `g[23]`, not `g[34]`: g4dn is not previous generation, and with `[a-z]*` it would now match.
m perf-3 nodes '[.items[]|.metadata.labels["node.kubernetes.io/instance-type"]//empty] as $it|($it|length) as $t|([$it[]|select(test("^(a1|m[1-5]|c[1-5]|r[3-5]|t[12]|i[23]|d2|h1|x1|p[23]|g[23])[a-z]*\\."))]|length) as $old|($t-$old) as $ok| if ([.items[]]|length)==0 then "na~no nodes" elif $t==0 then "na~no instance types (serverless compute)" else b($ok;$t)+"~\($ok)/\($t) current-generation" end'
m perf-4 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) rolling"'
m perf-5 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select(.spec.template.spec.affinity or ((.spec.template.spec.topologySpreadConstraints//[])|length>0))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) scheduling"'
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
m lens-6 nodes '[.items[]] as $n|($n|length) as $t|([$n[]|.status.nodeInfo.osImage//""]) as $os|([$os[]|select(test("Bottlerocket|Amazon Linux 20[0-9][0-9]"))]|length) as $ok|([$os[]|select(test("Amazon Linux") and (test("Amazon Linux 20[0-9][0-9]")|not))]|length) as $al2| if $t==0 then "na~no nodes" else b($ok;$t)+"~\($ok)/\($t) supported EKS AMI"+(if $al2>0 then ", \($al2) on Amazon Linux 2 (end of support 2025-11-26 — no security patches)" else "" end) end'
m lens-8 pods '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $p|($p|length) as $t|([$p[]|select([.spec.dnsConfig.options[]?|select(.name=="ndots" and ((.value|tonumber?)//9)<=2)]|length>0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ndots<=2"'
m lens-9 services '[.items[]|select(.spec.type=="LoadBalancer")] as $s|($s|length) as $t|([$s[]|select(.spec.externalTrafficPolicy=="Local")]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) LB local"'
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

**Detection:** ✋ ASK USER

> Rolling updates maintain performance during deployments by keeping pods available.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Set `strategy.type: RollingUpdate` on all Deployments with appropriate `maxUnavailable` and `maxSurge` values for zero-downtime updates.

---

### perf-5: Are pod affinity, anti-affinity, or topology spread constraints configured?

**Detection:** ✋ ASK USER

> Scheduling constraints optimize pod placement for performance and availability.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

**Remediation:** Configure pod affinity/anti-affinity and topology spread constraints to optimize pod placement across nodes and zones.

---

## Resource Optimization

### perf-6: Is there diversity in EC2 instance types across node groups?

**Detection:** ✋ ASK USER

> Instance type diversity reduces Spot interruption risk and improves bin-packing.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `not-applicable`

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
- "Doesn't apply" → `not-applicable`

**Remediation:** Right-size nodes based on actual utilization. Target 60-80% CPU and memory utilization. Use Karpenter for automatic instance type selection.

---

## EKS Best Practices

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
  instead of `/etc/eks/bootstrap.sh`, requires VPC CNI ≥ 1.16.2, and enforces IMDSv2 with a hop limit
  of 1 — so a container that reads instance metadata needs `HttpPutResponseHopLimit` raised in the
  launch template. Say this in the report; a migration presented as trivial will fail.
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
